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
