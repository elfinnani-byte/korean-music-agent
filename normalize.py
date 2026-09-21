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
