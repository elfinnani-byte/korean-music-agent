"""도메인 스키마의 단일 진실 공급원. config.json 은 이것을 복사하지 않고 검증만 한다."""

NODE_TYPES: dict[str, str] = {
    "Artist": "entity", "Group": "entity", "Album": "entity", "Song": "entity",
    "Label": "entity", "Award": "entity", "Program": "entity",
    "Genre": "attribute", "Era": "attribute",
}

ENTITY_TYPES = [t for t, f in NODE_TYPES.items() if f == "entity"]
ATTRIBUTE_TYPES = [t for t, f in NODE_TYPES.items() if f == "attribute"]

REL_TRIPLES: list[tuple[str, str, str]] = [
    # 구조 백본
    ("Artist", "MEMBER_OF", "Group"),
    ("Group", "SUBUNIT_OF", "Group"),
    ("Artist", "SIGNED_TO", "Label"),
    ("Group", "SIGNED_TO", "Label"),
    ("Artist", "FOUNDED", "Label"),
    ("Artist", "RELEASED", "Album"),
    ("Group", "RELEASED", "Album"),
    ("Album", "CONTAINS", "Song"),
    ("Artist", "PERFORMED", "Song"),
    ("Group", "PERFORMED", "Song"),
    # 세대 교량
    ("Artist", "WROTE", "Song"),
    ("Artist", "PRODUCED", "Album"),
    ("Artist", "PRODUCED", "Song"),
    ("Artist", "PRODUCED", "Group"),
    ("Artist", "INFLUENCED", "Artist"),
    ("Artist", "INFLUENCED", "Group"),
    ("Group", "INFLUENCED", "Artist"),
    ("Group", "INFLUENCED", "Group"),
    ("Artist", "COVERED", "Artist"),
    ("Artist", "COVERED", "Group"),
    ("Group", "COVERED", "Artist"),
    ("Group", "COVERED", "Group"),
    # 협업 (교량 아님)
    ("Artist", "COLLABORATED_WITH", "Artist"),
    ("Artist", "COLLABORATED_WITH", "Group"),
    ("Group", "COLLABORATED_WITH", "Artist"),
    ("Group", "COLLABORATED_WITH", "Group"),
    # 속성
    ("Artist", "HAS_GENRE", "Genre"),
    ("Group", "HAS_GENRE", "Genre"),
    ("Album", "HAS_GENRE", "Genre"),
    ("Song", "HAS_GENRE", "Genre"),
    ("Artist", "DEBUTED_IN", "Era"),
    ("Group", "DEBUTED_IN", "Era"),
    ("Group", "FORMED_IN", "Era"),
    ("Album", "RELEASED_IN", "Era"),
    ("Song", "RELEASED_IN", "Era"),
    ("Artist", "WON", "Award"),
    ("Group", "WON", "Award"),
    ("Album", "WON", "Award"),
    ("Song", "WON", "Award"),
    # 조건부 — P4 관문 조건 미달 시 Program 과 함께 제거
    ("Song", "TOPPED_ON", "Program"),
]

BRIDGE_RELATIONS = ["INFLUENCED", "COVERED", "PRODUCED", "WROTE", "FOUNDED"]
NON_EXPANDING_TYPES = ["Genre", "Era"]
SYMMETRIC_RELATIONS = ["COLLABORATED_WITH"]

NEVER_MERGE_PAIRS: set[frozenset[str]] = {
    frozenset({"Artist", "Group"}),
    frozenset({"Album", "Song"}),
    frozenset({"Group", "Album"}),
    frozenset({"Artist", "Album"}),
    frozenset({"Label", "Group"}),
}

ERAS = ["1980s 이전", "1990s", "2000s", "2010s", "2020s"]
QUOTA_ERAS = ["1990s", "2000s", "2010s", "2020s"]


def era_of_year(year: int) -> str:
    """연도를 연대 칸으로 옮긴다. 범위 밖 과거는 한 칸으로 묶는다."""
    if year < 1990:
        return "1980s 이전"
    if year < 2000:
        return "1990s"
    if year < 2010:
        return "2000s"
    if year < 2020:
        return "2010s"
    return "2020s"


def allowed_relationship_names() -> list[str]:
    return sorted({r for _, r, _ in REL_TRIPLES})


def validate() -> None:
    """P0 관문. 스키마 자체의 자기모순을 잡는다."""
    for h, r, t in REL_TRIPLES:
        if h not in NODE_TYPES or t not in NODE_TYPES:
            raise ValueError(f"선언되지 않은 노드 타입: ({h}, {r}, {t})")
    if len(REL_TRIPLES) != len(set(REL_TRIPLES)):
        raise ValueError("REL_TRIPLES 에 중복 튜플이 있다")
    for rel in BRIDGE_RELATIONS + SYMMETRIC_RELATIONS:
        if rel not in allowed_relationship_names():
            raise ValueError(f"선언되지 않은 관계: {rel}")
