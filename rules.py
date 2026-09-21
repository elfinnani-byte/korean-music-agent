"""위키 분류에서 삼중항을 뽑는 규칙 R01~R10.
   LLM 비용이 0이고 방향이 결정적이라 먼저 만든다."""
import re

import schema

GENRE_SUFFIX = r"(?:음악가|가수|밴드|그룹|듀오|연주자)"

R01 = re.compile(rf"^대한민국의\s*(.+?)\s*{GENRE_SUFFIX}$")
R02 = re.compile(r"^(.+?)\s*소속(?:\s*(?:음악가|가수|아티스트))?$")
R03 = re.compile(r"^(\d{4})년\s*데뷔(?:\s*(?:음악가|가수|그룹))?$")
R04 = re.compile(r"^(\d{4})년\s*(?:결성|설립)(?:된\s*음악\s*그룹)?$")
R05 = re.compile(r"^(\d{4})년\s*(?:음반|앨범)$")
R06 = re.compile(r"^(\d{4})년\s*(?:노래|싱글)$")
R07 = re.compile(r"^(?P<award>.+?)\s*(?P<cat>[가-힣]*상)?\s*수상\s*"
                 r"(?:음악가|가수|그룹|자|작)?$")
R08 = re.compile(r"^(.+?)의\s*(?:음반|정규 음반|스튜디오 음반)$")
R09 = re.compile(r"^(.+?)의\s*(?:노래|싱글)$")
R10 = re.compile(r"^(.+?)의\s*(?:일원|멤버)$")

BLACKLIST = [re.compile(p) for p in schema.CATEGORY_BLACKLIST]
LABEL_SUFFIX = re.compile(schema.LABEL_SUFFIX)


def _triple(h, r, t, *, props=None, source="", confidence=0.95):
    return {"h": h, "r": r, "t": t, "props": props or {},
            "origins": ["rule"], "agreement": confidence,
            "sources": [source], "quotes": []}


def _canon_award(name: str) -> str | None:
    """AWARD 사전을 통과해야 채택한다. 통과 못 하면 '본상'이
       시상식 이름으로 잘못 잡히는 등의 오류가 난다."""
    n = name.strip()
    return schema.AWARD_CANON.get(n)


def _canon_genre(name: str) -> str | None:
    return schema.GENRE_CANON.get(name.strip())


def _canon_label(name: str) -> str | None:
    n = name.strip()
    return n if LABEL_SUFFIX.search(n) else None


def apply(doc_title: str, categories: list[str]) -> list[dict]:
    out: list[dict] = []
    for cat in categories:
        c = cat.strip()
        if any(b.search(c) for b in BLACKLIST):
            continue

        if (m := R01.match(c)) and (g := _canon_genre(m.group(1))):
            out.append(_triple(doc_title, "HAS_GENRE", g, source=doc_title))
            continue
        if (m := R02.match(c)) and (lab := _canon_label(m.group(1))):
            out.append(_triple(doc_title, "SIGNED_TO", lab, source=doc_title))
            continue
        if m := R03.match(c):
            y = int(m.group(1))
            out.append(_triple(doc_title, "DEBUTED_IN", schema.era_of_year(y),
                               props={"year": y}, source=doc_title, confidence=1.0))
            continue
        if m := R04.match(c):
            y = int(m.group(1))
            out.append(_triple(doc_title, "FORMED_IN", schema.era_of_year(y),
                               props={"year": y}, source=doc_title, confidence=0.9))
            continue
        if m := (R05.match(c) or R06.match(c)):
            y = int(m.group(1))
            out.append(_triple(doc_title, "RELEASED_IN", schema.era_of_year(y),
                               props={"year": y}, source=doc_title, confidence=1.0))
            continue
        if m := R07.match(c):
            award = _canon_award(m.group("award"))
            if award:
                props = {}
                if m.group("cat"):
                    props["award_category"] = m.group("cat")
                out.append(_triple(doc_title, "WON", award, props=props,
                                   source=doc_title, confidence=0.9))
            continue
        if m := R08.match(c):
            out.append(_triple(m.group(1), "RELEASED", doc_title, source=doc_title))
            continue
        if m := R09.match(c):
            out.append(_triple(m.group(1), "PERFORMED", doc_title, source=doc_title))
            continue
        if m := R10.match(c):
            out.append(_triple(doc_title, "MEMBER_OF", m.group(1), source=doc_title))
            continue
    return out


TYPE_RULES = [
    (re.compile(r"(보이 밴드|걸 그룹|아이돌 그룹|음악 그룹|음악 밴드|\d인조)"), "Group"),
    (re.compile(r"(음악가|가수|싱어송라이터|작곡가|작사가|음악 프로듀서)"), "Artist"),
    (re.compile(r"(음반$|정규 음반|스튜디오 음반|컴필레이션 음반|EP$)"), "Album"),
    (re.compile(r"(노래$|싱글$|주제가)"), "Song"),
    (re.compile(r"(음반 기획사|연예 기획사|음반사|레이블)"), "Label"),
    (re.compile(r"(음악 시상식|시상식)"), "Award"),
    (re.compile(r"(음악 프로그램|텔레비전 음악)"), "Program"),
]


def vote_types_from_categories(categories: list[str]) -> dict[str, int]:
    """분류는 간선뿐 아니라 타입 투표에도 참여한다.
       그룹·인물 혼동의 1차 방어선이다."""
    votes: dict[str, int] = {}
    for cat in categories:
        for pat, ntype in TYPE_RULES:
            if pat.search(cat):
                votes[ntype] = votes.get(ntype, 0) + 1
    return votes
