"""표기 정리 · 타입 투표 · 병합 · 동일성 정책 · 파생 간선.
   규칙·트랙리스트·LLM 삼중항을 모두 합친 뒤 단 한 번만 돌린다."""
import re
import unicodedata

import schema

PAREN_QUALIFIER = re.compile(
    r"\s*\((?:음악\s*그룹|음반|노래|가수|작곡가|영화|드라마|배우|기업|\d{4}년\s*음반)\)\s*$"
)
BRACKETS = re.compile(r"[\[\]〈〉《》「」『』\"']")
PARTICLE_AFTER_BRACKET = re.compile(
    r"(?<=[)\]〉》」』])\s*(?:은|는|이|가|을|를|의|에|와|과|도|만|로|으로)$"
)
BARE_YEAR = re.compile(r"^\d{3,4}년?$")
ERAS_LOWER = {e.lower() for e in schema.ERAS}


def clean_name(s: str) -> str:
    """괄호 한정어와 대괄호를 제거하고, 닫는 괄호 뒤에 붙은 조사만 뗀다.
       맨 이름에서 조사를 떼면 '거짓말이야'가 '거짓말'이 된다."""
    s = s.strip()
    s = PARTICLE_AFTER_BRACKET.sub("", s)
    s = PAREN_QUALIFIER.sub("", s)
    s = BRACKETS.sub("", s)
    return s.strip()


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", clean_name(s)).lower()
    return re.sub(r"[\s·\-_]", "", s)


def is_junk(name: str, ntype: str) -> bool:
    n = clean_name(name)
    if len(n) < 2:
        return True
    if n in schema.STOPWORDS:
        return True
    if ntype not in schema.NODE_TYPES:
        return True
    if BARE_YEAR.match(n) and schema.NODE_TYPES.get(ntype) == "attribute":
        return True
    if ntype == "Era" and n.lower() not in ERAS_LOWER:
        return True
    return False


RULE_VOTE_WEIGHT = 5
CONTEXT_TYPES = {"Song", "Album"}
TYPE_ORDER = {t: i for i, t in enumerate(schema.NODE_TYPES)}


def vote_type(llm_votes: dict[str, int], rule_votes: dict[str, int]) -> str:
    """분류 기반 규칙 투표에 가중치 5, LLM 투표에 1.
       동점이면 엔티티 패밀리를 우선한다."""
    score: dict[str, int] = {}
    for t, n in llm_votes.items():
        score[t] = score.get(t, 0) + n
    for t, n in rule_votes.items():
        score[t] = score.get(t, 0) + n * RULE_VOTE_WEIGHT
    if not score:
        raise ValueError("타입 투표가 비어 있다")
    best = max(score.values())
    tied = [t for t, v in score.items() if v == best]
    entity = [t for t in tied if schema.NODE_TYPES.get(t) == "entity"]
    pool = entity or tied
    return sorted(pool, key=lambda t: TYPE_ORDER.get(t, 99))[0]


def node_id(name: str, ntype: str, context: str | None) -> str:
    """Song·Album 은 제목만으로 동일성이 서지 않는다(설계서 4.3).
       맥락(대표 수행자 또는 수록 앨범)을 ID 에 넣어 동명이곡을 가른다."""
    key = norm_key(name)
    if ntype in CONTEXT_TYPES:
        return f"{ntype.lower()}:{key}:{norm_key(context) if context else '_'}"
    return f"{ntype.lower()}:{key}"


def can_merge_songs(a: dict, b: dict) -> bool:
    """제목이 같은 두 곡을 합쳐도 되는가.
       제목은 필요조건일 뿐 충분조건이 아니다."""
    if a["performers"] & b["performers"]:
        return True
    if a["albums"] & b["albums"]:
        return True
    if a["quotes"] & b["quotes"]:
        return True
    return False


def canonical_symmetric(a: tuple[str, str], b: tuple[str, str]):
    """대칭 관계의 정준 방향을 정한다. (이름, 타입) 두 쌍을 받는다.
       타입을 먼저 보는 이유는 이름만으로 정렬하면 스키마에 없는
       튜플이 나올 수 있기 때문이다."""
    key = lambda x: (TYPE_ORDER.get(x[1], 99), norm_key(x[0]))
    return tuple(sorted([a, b], key=key))


import networkx as nx


def _relation_implied_types() -> dict[tuple[str, str], str]:
    """관계마다 h·t 타입이 스키마 전체에서 하나로 고정되는 경우만 등록한다.
       SIGNED_TO/FOUNDED->Label, WON->Award, HAS_GENRE->Genre,
       FORMED_IN/DEBUTED_IN/RELEASED_IN->Era 처럼 대상이 폐쇄 어휘라
       LLM이 우연히 같은 문자열로 언급하지 않으면 types 사전에 절대
       등록되지 않는다. 그 결과 이런 관계의 간선이 통째로 드롭됐다
       (실측: 52건 코퍼스에서 FORMED_IN/DEBUTED_IN/RELEASED_IN 0건 생존)."""
    by_rel_h: dict[str, set[str]] = {}
    by_rel_t: dict[str, set[str]] = {}
    for h_type, rel, t_type in schema.REL_TRIPLES:
        by_rel_h.setdefault(rel, set()).add(h_type)
        by_rel_t.setdefault(rel, set()).add(t_type)
    implied: dict[tuple[str, str], str] = {}
    for rel, types_ in by_rel_h.items():
        if len(types_) == 1:
            implied[(rel, "h")] = next(iter(types_))
    for rel, types_ in by_rel_t.items():
        if len(types_) == 1:
            implied[(rel, "t")] = next(iter(types_))
    return implied


RELATION_IMPLIED_TYPES = _relation_implied_types()


def _context_of(triple: dict, side: str) -> str | None:
    """Song·Album 노드의 맥락을 삼중항에서 유추한다."""
    if side == "t" and triple["r"] in ("PERFORMED", "RELEASED", "WROTE", "PRODUCED"):
        return triple["h"]
    if side == "t" and triple["r"] == "CONTAINS":
        return triple["h"]
    if side == "h" and triple["r"] == "CONTAINS":
        return None
    return None


def merge_triples(triples: list[dict], cfg: dict,
                  types: dict[str, str]) -> tuple[nx.MultiDiGraph, dict]:
    """삼중항을 그래프로 합친다. 정규화는 규칙·트랙리스트·LLM 을
       모두 합친 뒤 단 한 번만 돌린다."""
    overrides = cfg["normalize"]["entity_type_overrides"]
    g = nx.MultiDiGraph()
    report = {"dropped_junk": [], "type_conflicts": [], "symmetric_collapsed": 0}

    def ensure(name: str, triple: dict, side: str) -> str | None:
        ntype = (overrides.get(clean_name(name)) or types.get(name)
                 or RELATION_IMPLIED_TYPES.get((triple["r"], side)))
        if ntype is None or is_junk(name, ntype):
            report["dropped_junk"].append(name)
            return None
        nid = node_id(name, ntype, _context_of(triple, side))
        if nid not in g:
            g.add_node(nid, name=clean_name(name), type=ntype,
                       norm=norm_key(name), aliases=[])
        elif g.nodes[nid]["type"] != ntype:
            report["type_conflicts"].append((name, g.nodes[nid]["type"], ntype))
        return nid

    for tri in triples:
        rel = tri["r"]
        h_name, t_name = tri["h"], tri["t"]

        if rel in schema.SYMMETRIC_RELATIONS:
            ha = (h_name, overrides.get(clean_name(h_name)) or types.get(h_name, "Artist"))
            tb = (t_name, overrides.get(clean_name(t_name)) or types.get(t_name, "Artist"))
            (h_name, _), (t_name, _) = canonical_symmetric(ha, tb)

        h = ensure(h_name, tri, "h")
        t = ensure(t_name, tri, "t")
        if h is None or t is None or h == t:
            continue

        existing = None
        for _, tgt, key, data in g.edges(h, keys=True, data=True):
            if tgt == t and data["relation"] == rel:
                existing = (key, data)
                break

        if existing is None:
            g.add_edge(h, t, relation=rel, props=dict(tri.get("props", {})),
                       origins=list(tri.get("origins", [])),
                       agreement=tri.get("agreement", 0.8),
                       count=1,
                       sources=list(tri.get("sources", [])),
                       quotes=list(tri.get("quotes", [])))
        else:
            _, data = existing
            data["count"] += 1
            for o in tri.get("origins", []):
                if o not in data["origins"]:
                    data["origins"].append(o)
            if {"rule", "llm"} <= set(data["origins"]):
                data["agreement"] = 1.0
            else:
                data["agreement"] = min(1.0, data["agreement"] + 0.05)
            for q in tri.get("quotes", []):
                if q not in data["quotes"]:
                    data["quotes"].append(q)
            for s in tri.get("sources", []):
                if s not in data["sources"]:
                    data["sources"].append(s)
            data["props"].update(tri.get("props", {}))

    for nid in list(g.nodes):
        g.nodes[nid]["degree"] = g.degree(nid)
    return g, report


def add_derived_edges(g: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """COVERED 파생. 같은 Song 에 원곡 PERFORMED 와 리메이크 PERFORMED 가
       함께 붙으면 (리메이크 가수, COVERED, 원곡 가수) 를 만든다.

       LABELMATE_OF 는 의도적으로 만들지 않는다."""
    by_song: dict[str, dict[str, list[str]]] = {}
    for u, v, data in g.edges(data=True):
        if data["relation"] != "PERFORMED":
            continue
        bucket = by_song.setdefault(v, {"orig": [], "cover": []})
        is_cover = bool(data.get("props", {}).get("cover"))
        bucket["cover" if is_cover else "orig"].append(u)

    for song, sides in by_song.items():
        for coverer in sides["cover"]:
            for original in sides["orig"]:
                if coverer == original:
                    continue
                g.add_edge(coverer, original, relation="COVERED",
                           props={"via_song": g.nodes[song]["name"]},
                           origins=["derived"], agreement=0.8, count=1,
                           sources=list({*g.nodes[song].get("aliases", []),
                                         g.nodes[song]["name"]}),
                           quotes=[])
    return g


def annotate_hubs(g: nx.MultiDiGraph, threshold: int) -> None:
    for nid in g.nodes:
        deg = g.degree(nid)
        g.nodes[nid]["degree"] = deg
        g.nodes[nid]["is_hub"] = deg > threshold
