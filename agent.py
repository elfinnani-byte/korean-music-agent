"""LangGraph 기반 RAG 에이전트. n_route 부터 n_synthesize/n_insufficient 까지.

State 원칙 둘.
1. 모든 필드는 JSON 직렬화 가능해야 한다. visited 를 set 으로 두면
   LangGraph 체크포인트와 runs.jsonl 기록에서 둘 다 깨진다. 중복 확인은
   함수 안 지역 변수 set 으로 하고, State 에 나가는 것은 list 다.
2. 관계 공백 필드는 gap_rels 하나로만 부른다. required_rels 는 라우터가
   산출한 요구 사항이고 gap_rels 는 그중 아직 못 채운 것으로, 둘은 다른 값이다.
"""
import sys
from typing import Literal, TypedDict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class RAGState(TypedDict, total=False):
    question: str
    route: Literal["local", "path", "global", "vector", "reject"]
    route_by: Literal["rule", "llm"]
    seeds: list[str]
    radius: int
    required_rels: list[list[str]]
    gap_rels: list[str]
    triples: list[dict]
    trace: list[dict]
    frontier: list[str]
    visited: list[str]
    reports: list[dict]
    context: str
    answer: str | None
    sources: list[str]
    decision: Literal["answer", "abstain"]
    abstain_reason: str | None
    llm_answer_called: bool
    stats: dict


def initial_state(question: str) -> RAGState:
    return {
        "question": question, "route": "reject", "route_by": "rule",
        "seeds": [], "radius": 0, "required_rels": [], "gap_rels": [],
        "triples": [], "trace": [], "frontier": [], "visited": [],
        "reports": [], "context": "", "answer": None, "sources": [],
        "decision": "abstain", "abstain_reason": None,
        "llm_answer_called": False, "stats": {},
    }


def relation_gap(state: dict) -> list[list[str]]:
    """required_rels 의 OR 그룹 중 하나도 확보하지 못한 그룹만 반환한다."""
    have = {t["r"] for t in state.get("triples", [])}
    gaps = []
    for group in state.get("required_rels", []):
        if not any(rel in have for rel in group):
            gaps.append(group)
    return gaps


import json
import re

import schema


def route_by_rule(question: str) -> tuple[str | None, str | None, list[list[str]] | None]:
    """규칙 1차 판정. 확신이 없으면 (None, None, None)을 반환해
       route_question() 이 LLM 폴백을 부르게 한다."""
    if any(h in question for h in schema.GLOBAL_HINTS):
        return "global", "rule", []
    if any(h in question for h in schema.VECTOR_HINTS):
        # 벡터 인덱스가 없어 path 로 강등한다. required_rels 를 비우는
        # 이유는 서술형 질의가 어떤 관계를 요구하는지 규칙으로 알 수
        # 없어서이고, 빈 required_rels 는 relation_gap() 에서 공백 없음으로
        # 처리돼 n_build_context 를 그대로 통과한다.
        return "path", "rule", []

    matched: list[list[str]] = []
    for pattern, rels in schema.CUE_TO_RELATIONS.items():
        if re.search(pattern, question):
            matched.append(rels)
    if not matched:
        return None, None, None
    route = "local" if len(matched) == 1 else "path"
    return route, "rule", matched


def _parse_route_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"라우터 LLM 응답에서 JSON 을 찾지 못함: {text[:200]}")
    return json.loads(m.group(0))


def route_question(question: str, cfg: dict, llm=None) -> RAGState:
    state = initial_state(question)
    route, by, rels = route_by_rule(question)
    if route is not None:
        state["route"], state["route_by"], state["required_rels"] = route, by, rels
        return state

    prompt = schema.ROUTE_LLM_PROMPT.format(
        relation_names=", ".join(schema.allowed_relationship_names()),
        question=question,
    )
    resp = llm.invoke(prompt)
    parsed = _parse_route_json(resp.content)
    state["route"] = parsed.get("route", "reject")
    state["route_by"] = "llm"
    state["required_rels"] = parsed.get("required_rels", [])
    return state


import normalize as nz


def find_seeds(g, question: str, cfg: dict, llm=None) -> list[str]:
    """정확매칭 -> 부분매칭 -> (0건일 때만) LLM.
       LLM 단계가 설계서의 '퍼지 매칭'을 겸한다 — 편집 거리 기반 문자열
       유사도 대신 LLM에게 질문에서 개체명을 직접 뽑게 하고, 뽑힌 문자열을
       다시 그래프에 정규화 대조한다. 한국어 조사·표기 변형(대소문자·
       띄어쓰기)에는 이쪽이 편집 거리보다 안정적이다."""
    max_seeds = cfg["retrieval"]["max_seeds"]

    exact = [nid for nid, d in g.nodes(data=True)
             if len(d["name"]) >= 2 and d["name"] in question]
    if exact:
        exact.sort(key=lambda nid: -len(g.nodes[nid]["name"]))
        return exact[:max_seeds]

    qnorm = nz.norm_key(question)
    partial = [nid for nid, d in g.nodes(data=True)
               if len(d["norm"]) >= 2 and d["norm"] in qnorm]
    if partial:
        partial.sort(key=lambda nid: -len(g.nodes[nid]["norm"]))
        return partial[:max_seeds]

    if llm is None:
        return []
    resp = llm.invoke(f"다음 질문에서 언급된 고유명사(인물·그룹·곡·앨범·회사)만 "
                       f"JSON으로 뽑아라. 형식: {{\"entities\": [\"...\"]}}\n\n질문: {question}")
    parsed = _parse_route_json(resp.content)
    found = []
    for ent in parsed.get("entities", []):
        ent_norm = nz.norm_key(ent)
        for nid, d in g.nodes(data=True):
            if d["norm"] == ent_norm and nid not in found:
                found.append(nid)
    return found[:max_seeds]


def is_hub(g, nid: str, threshold: int | None) -> bool:
    """허브 판정은 저장된 is_hub 속성이 아니라 그때그때 차수로 계산한다.
       graph.json 의 is_hub 는 빌드 시점 임계값(25)으로 굳어 있어, 스윕이
       다른 임계값을 시도해도 반영되지 않기 때문이다.
       threshold=None 은 '차단 없음'이다(설계서 6.2 스윕 격자의 네
       번째 칸) — 차수가 아무리 높아도 허브로 치지 않는다."""
    if threshold is None:
        return False
    return g.degree(nid) > threshold


def edge_score(g, tail_id: str, edge: dict, state: dict, cfg: dict) -> float:
    origin_key = "+".join(sorted(edge["origins"])) if isinstance(edge.get("origins"), list) \
        else edge.get("origins", "llm")
    base = cfg["retrieval"]["origin_base_score"].get(origin_key, 0.8)
    exp = cfg["retrieval"]["degree_penalty_exponent"]
    pen = 1.0 / (1.0 + g.degree(tail_id) ** exp)
    rel = edge["relation"]
    if rel in state.get("gap_rels", []):
        prio = 1.3
    elif rel in schema.BRIDGE_RELATIONS:
        prio = 1.15
    else:
        prio = 1.0
    return base * edge["agreement"] * pen * prio


def _select_within_budget(candidates: list[tuple], cfg: dict) -> list[tuple]:
    """candidates: (score, direction, head_id, tail_id, rel, edge_data) 리스트.
       점수 내림차순으로 관계별 상한(per_relation)과 전체 상한(max_triples)을
       적용한다. 교량 관계와 규칙 기원은 관계별 상한에서 면제한다 — 흔한
       관계(SIGNED_TO 등)에 밀려 사라지면 안 된다."""
    per_relation = cfg["retrieval"]["per_relation"]
    max_triples = cfg["retrieval"]["max_triples"]
    exempt_rels = set(cfg["retrieval"]["quota_exempt_relations"])
    exempt_origins = set(cfg["retrieval"]["quota_exempt_origins"])

    ordered = sorted(candidates, key=lambda c: -c[0])
    rel_count: dict[str, int] = {}
    selected = []
    for score, direction, h, t, rel, data in ordered:
        if len(selected) >= max_triples:
            break
        origins = data.get("origins", [])
        exempt = rel in exempt_rels or any(o in exempt_origins for o in origins)
        if not exempt and rel_count.get(rel, 0) >= per_relation:
            continue
        rel_count[rel] = rel_count.get(rel, 0) + 1
        selected.append((score, direction, h, t, rel, data))
    return selected


def expand_one_hop(g, state: dict, cfg: dict) -> dict:
    """프런티어에서 한 홉 확장한다. 순방향(out)·역방향(in) 간선을 모두 본다.
       반환값은 state 에 병합할 부분 갱신(triples·trace·frontier·visited)이다.

       visited 에 이번 홉의 프런티어 자신을 먼저 합쳐 둔다. 안 그러면 jyp 를
       확장하다가 jyp 로 들어오는 간선(u -> jyp)을 볼 때 jyp 가 아직
       visited 에 없어 new_frontier 에 자기 자신을 다시 넣는 버그가 생긴다
       — 이미 확장을 마친 노드가 다음 홉에 다시 프런티어로 등장해 같은
       간선을 반복 방문하게 된다."""
    visited = set(state["visited"]) | set(state["frontier"])
    seeds = set(state["seeds"])
    threshold = cfg["retrieval"]["hub_degree_threshold"]
    per_node_out = cfg["retrieval"]["per_node_out"]

    candidates: list[tuple] = []
    for nid in state["frontier"]:
        if is_hub(g, nid, threshold) and nid not in seeds:
            continue  # 허브는 시드가 아니면 확장 시작점으로 쓰지 않는다
        out_edges = list(g.out_edges(nid, data=True))[:per_node_out]
        for _, v, data in out_edges:
            e = {"origins": data["origins"], "agreement": data["agreement"], "relation": data["relation"]}
            candidates.append((edge_score(g, v, e, state, cfg), "out", nid, v, data["relation"], data))
        in_edges = list(g.in_edges(nid, data=True))[:per_node_out]
        for u, _, data in in_edges:
            e = {"origins": data["origins"], "agreement": data["agreement"], "relation": data["relation"]}
            candidates.append((edge_score(g, nid, e, state, cfg), "in", u, nid, data["relation"], data))

    selected = _select_within_budget(candidates, cfg)

    new_triples, new_trace, new_frontier = [], [], []
    hop_no = state["radius"]
    for score, direction, h, t, rel, data in selected:
        h_name, t_name = g.nodes[h]["name"], g.nodes[t]["name"]
        new_triples.append({"h": h_name, "r": rel, "t": t_name})
        new_trace.append({"hop": hop_no, "head": h_name, "rel": rel, "tail": t_name,
                          "dir": direction, "origin": "+".join(sorted(data["origins"])),
                          "score": round(score, 4)})
        for nid in (h, t):
            if nid in visited or nid in new_frontier:
                continue
            ntype = g.nodes[nid]["type"]
            if ntype in schema.NON_EXPANDING_TYPES:
                continue  # Genre·Era 는 근거로만 쓰고 프런티어에 넣지 않는다
            new_frontier.append(nid)

    return {
        "triples": state["triples"] + new_triples,
        "trace": state["trace"] + new_trace,
        "frontier": new_frontier,
        "visited": sorted(visited),
    }


_UNSET = object()  # None 자체가 '차단 없음'이라는 유효한 값이라 '지정 안 함'과 구별해야 한다


def run_retrieval(g, seeds: list[str], required_rels: list[list[str]], cfg: dict,
                  max_radius_override: int | None = None,
                  hub_degree_threshold_override: int | None = _UNSET,
                  per_relation_override: int | None = None,
                  max_triples_override: int | None = None) -> dict:
    """expand_one_hop 을 반경이 다하거나 관계 공백이 없어질 때까지 반복한다.
       LLM 을 부르지 않는 순수 함수다 — P7 스윕이 override 인자로 파라미터를
       바꿔 가며 이 함수를 직접 호출한다.

       hub_degree_threshold_override 만 기본값이 _UNSET(미지정)이다. 다른
       override 들은 None 이 곧 '지정 안 함'이라 문제없지만, 이 값은
       None 자체가 스윕 격자의 '차단 없음' 칸을 뜻하는 유효한 값이라
       '지정 안 함'과 같은 기호로 겹치면 '차단 없음'을 요청해도 조용히
       기본 임계값으로 되돌아가는 버그가 생긴다(실측)."""
    local_cfg = {**cfg, "retrieval": {**cfg["retrieval"]}}
    if max_radius_override is not None:
        local_cfg["retrieval"]["max_radius"] = max_radius_override
    if hub_degree_threshold_override is not _UNSET:
        local_cfg["retrieval"]["hub_degree_threshold"] = hub_degree_threshold_override
    if per_relation_override is not None:
        local_cfg["retrieval"]["per_relation"] = per_relation_override
    if max_triples_override is not None:
        local_cfg["retrieval"]["max_triples"] = max_triples_override

    state = {"triples": [], "trace": [], "frontier": list(seeds),
             "visited": [], "seeds": list(seeds), "gap_rels": []}
    max_radius = local_cfg["retrieval"]["max_radius"]
    radius = 1
    while True:
        state["radius"] = radius
        upd = expand_one_hop(g, state, local_cfg)
        state = {**state, **upd}
        gaps = relation_gap({"required_rels": required_rels, "triples": state["triples"]})
        state["gap_rels"] = [r for group in gaps for r in group]
        if not gaps or radius >= max_radius or not state["frontier"]:
            break
        radius += 1

    return {"triples": state["triples"], "trace": state["trace"],
            "radius_used": radius, "gap_rels": gaps}


def build_context(triples: list[dict]) -> tuple[str, list[str]]:
    """삼중항을 관계별로 묶어 텍스트화한다. 출처(등장한 개체명 전체)를
       함께 반환해 답변 프롬프트의 '근거 밖 개체 금지' 검사에 쓴다."""
    by_rel: dict[str, list[dict]] = {}
    for t in triples:
        by_rel.setdefault(t["r"], []).append(t)
    lines = []
    sources: set[str] = set()
    for rel, group in by_rel.items():
        lines.append(f"[{rel}]")
        for t in group:
            lines.append(f"  ({t['h']}, {rel}, {t['t']})")
            sources.add(t["h"]); sources.add(t["t"])
    return "\n".join(lines), sorted(sources)


def insufficient_answer(gap_rels: list[str]) -> str:
    """관계 공백이 남으면 LLM 을 아예 부르지 않고 이 문자열을 그대로 낸다.
       토큰도 아끼고 환각도 원천 차단한다(코드층 방어)."""
    rels = ", ".join(gap_rels) if gap_rels else "알 수 없음"
    return f"근거가 부족합니다. 이 자료만으로는 확인할 수 없습니다.\n(미확보 관계: {rels})"


def synthesize(question: str, context: str, sources: list[str], llm) -> tuple[str, str, bool]:
    """근거 전용 프롬프트로 답한다(프롬프트층 방어). 반환: (답변, decision, llm_answer_called).
       코드층 게이트를 통과한 뒤에만 호출되므로 llm_answer_called 는 언제나 True다."""
    prompt = (f"{schema.ANSWER_SYSTEM_PROMPT}\n\n"
              f"[근거 삼중항]\n{context}\n\n[질문]\n{question}")
    resp = llm.invoke(prompt)
    text = resp.content
    decision = "abstain" if "근거가 부족합니다" in text else "answer"
    return text, decision, True


import json as _json
from pathlib import Path


def ask(question: str, g, cfg: dict, route_llm=None, answer_llm=None) -> RAGState:
    """LangGraph 없이 설계서 5.2 토폴로지를 직접 조립한 함수형 파이프라인이다.
       각 노드는 이미 위에서 순수 함수로 만들었으므로, LangGraph StateGraph 는
       이 함수 안에서 조건 분기를 그대로 옮긴 얇은 오케스트레이션일 뿐이다 —
       조건 분기 로직 자체를 이중으로 유지하지 않기 위해 이 함수 하나가
       정본이고, build_graph_app() 는 이 함수를 감싼 LangGraph 어댑터다."""
    state = route_question(question, cfg, llm=route_llm)

    if state["route"] == "reject":
        state["decision"] = "abstain"
        state["abstain_reason"] = "out_of_scope"
        state["llm_answer_called"] = False
        state["answer"] = insufficient_answer([])
        _log_run(state, cfg)
        return state

    if state["route"] == "global":
        report_path = Path(cfg["paths"]["output_dir"]) / "community_reports.json"
        if not report_path.exists():
            state["decision"] = "abstain"
            state["abstain_reason"] = "no_supported_path"
            state["llm_answer_called"] = False
            state["answer"] = "커뮤니티 보고서가 아직 생성되지 않았습니다. community.build_reports() 를 먼저 실행하세요."
            _log_run(state, cfg)
            return state
        reports = _json.loads(report_path.read_text(encoding="utf-8"))
        top = select_top_reports(question, reports, k=5)
        state["reports"] = top
        context = reduce_reports(top)
        answer, decision, called = synthesize(question, context, [], answer_llm)
        state["context"], state["answer"], state["decision"], state["llm_answer_called"] = \
            context, answer, decision, called
        if decision == "abstain":
            state["abstain_reason"] = "no_supported_path"
        _log_run(state, cfg)
        return state

    state["seeds"] = find_seeds(g, question, cfg, llm=route_llm)
    if not state["seeds"]:
        state["decision"] = "abstain"
        state["abstain_reason"] = "no_supported_path"
        state["llm_answer_called"] = False
        state["answer"] = insufficient_answer([r for group in state["required_rels"] for r in group])
        _log_run(state, cfg)
        return state

    ret = run_retrieval(g, state["seeds"], state["required_rels"], cfg)
    state["triples"], state["trace"] = ret["triples"], ret["trace"]
    state["radius"] = ret["radius_used"]
    gap_rels_flat = [r for group in ret["gap_rels"] for r in group]

    if gap_rels_flat:
        state["decision"] = "abstain"
        state["abstain_reason"] = "no_supported_path"
        state["llm_answer_called"] = False
        state["answer"] = insufficient_answer(gap_rels_flat)
        _log_run(state, cfg)
        return state

    context, sources = build_context(state["triples"])
    state["context"], state["sources"] = context, sources
    answer, decision, called = synthesize(question, context, sources, answer_llm)
    state["answer"], state["decision"], state["llm_answer_called"] = answer, decision, called
    if decision == "abstain":
        state["abstain_reason"] = "no_supported_path"
    _log_run(state, cfg)
    return state


def _log_run(state: dict, cfg: dict) -> None:
    out_dir = Path(cfg["paths"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "runs.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(state, ensure_ascii=False) + "\n")


def build_graph_app(g, cfg: dict, route_llm=None, answer_llm=None):
    """LangGraph StateGraph 어댑터. ask() 의 조건 분기를 그래프 엣지로
       옮긴다 — 데모(app.py)에서 trace 를 노드 단위로 시각화하려면
       StateGraph 객체가 필요하기 때문에 별도로 노출한다.

       그래프·설정·LLM은 그래프를 짓는 이 시점에 노드 클로저 안으로
       미리 묶어 둔다. LangGraph 는 컴파일된 그래프의 각 노드를 항상
       node(state) 한 인자로만 호출하므로, cfg 처럼 매 호출 바뀌지
       않는 값을 노드 시그니처에 얹으면 실행 시점에 TypeError 가 난다."""
    from langgraph.graph import END, START, StateGraph

    def n_route(state):
        return route_question(state["question"], cfg, llm=route_llm)

    def n_find_seeds(state):
        seeds = find_seeds(g, state["question"], cfg, llm=route_llm)
        return {**state, "seeds": seeds}

    def n_retrieve(state):
        ret = run_retrieval(g, state["seeds"], state["required_rels"], cfg)
        gap_rels_flat = [r for group in ret["gap_rels"] for r in group]
        return {**state, "triples": ret["triples"], "trace": ret["trace"],
                "radius": ret["radius_used"], "gap_rels": gap_rels_flat}

    def n_build_context(state):
        context, sources = build_context(state["triples"])
        return {**state, "context": context, "sources": sources}

    def n_synthesize(state):
        answer, decision, called = synthesize(state["question"], state["context"],
                                              state["sources"], answer_llm)
        reason = "no_supported_path" if decision == "abstain" else None
        return {**state, "answer": answer, "decision": decision,
                "llm_answer_called": called, "abstain_reason": reason}

    def n_insufficient(state):
        reason = state.get("abstain_reason") or "no_supported_path"
        gap = state.get("gap_rels", [])
        return {**state, "decision": "abstain", "abstain_reason": reason,
                "llm_answer_called": False, "answer": insufficient_answer(gap)}

    def n_global_map(state):
        report_path = Path(cfg["paths"]["output_dir"]) / "community_reports.json"
        if not report_path.exists():
            return {**state, "reports": [], "abstain_reason": "no_supported_path"}
        reports = _json.loads(report_path.read_text(encoding="utf-8"))
        return {**state, "reports": select_top_reports(state["question"], reports, k=5)}

    def n_global_reduce(state):
        context = reduce_reports(state["reports"])
        return {**state, "context": context, "sources": []}

    sg = StateGraph(RAGState)
    sg.add_node("n_route", n_route)
    sg.add_node("n_find_seeds", n_find_seeds)
    sg.add_node("n_retrieve", n_retrieve)
    sg.add_node("n_build_context", n_build_context)
    sg.add_node("n_synthesize", n_synthesize)
    sg.add_node("n_insufficient", n_insufficient)
    sg.add_node("n_global_map", n_global_map)
    sg.add_node("n_global_reduce", n_global_reduce)

    sg.add_edge(START, "n_route")
    sg.add_conditional_edges("n_route", lambda s: s["route"],
                             {"local": "n_find_seeds", "path": "n_find_seeds",
                              "global": "n_global_map", "vector": "n_find_seeds",
                              "reject": "n_insufficient"})
    sg.add_conditional_edges("n_find_seeds", lambda s: "ok" if s["seeds"] else "empty",
                             {"ok": "n_retrieve", "empty": "n_insufficient"})
    sg.add_conditional_edges("n_retrieve", lambda s: "gap" if s["gap_rels"] else "ok",
                             {"gap": "n_insufficient", "ok": "n_build_context"})
    sg.add_conditional_edges("n_global_map", lambda s: "ok" if s["reports"] else "empty",
                             {"ok": "n_global_reduce", "empty": "n_insufficient"})
    sg.add_edge("n_global_reduce", "n_synthesize")
    sg.add_edge("n_build_context", "n_synthesize")
    sg.add_edge("n_synthesize", END)
    sg.add_edge("n_insufficient", END)
    return sg


def select_top_reports(question: str, reports: list[dict], k: int = 5) -> list[dict]:
    """질문과 커뮤니티 보고서의 키워드 중첩으로 상위 k 건을 고른다.
       LLM 을 부르지 않는다(설계서 5.1 n_global_map 은 'LLM 없음')."""
    import re

    q_tokens = set(re.findall(r"[가-힣]{2,}", question))
    scored = []
    for r in reports:
        text = r["title"] + " " + r["summary"]
        r_tokens = set(re.findall(r"[가-힣]{2,}", text))
        overlap = len(q_tokens & r_tokens)
        scored.append((overlap, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]]


def reduce_reports(reports: list[dict]) -> str:
    lines = []
    for r in reports:
        lines.append(f"[{r['title']}] {r['summary']}")
        for f in r.get("findings", []):
            lines.append(f"  - {f}")
    return "\n".join(lines)
