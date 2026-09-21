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


GENRE_CANON: dict[str, str] = {
    "락": "록", "롹": "록", "록 음악": "록", "록": "록",
    "모던 포크": "포크", "포크": "포크", "포크 록": "포크 록",
    "성인가요": "트로트", "트로트": "트로트",
    "발라드": "발라드",
    "랩": "힙합", "한국 힙합": "힙합", "힙합": "힙합",
    "알앤비": "리듬 앤 블루스", "R&B": "리듬 앤 블루스",
    "리듬 앤 블루스": "리듬 앤 블루스",
    "댄스 음악": "댄스", "댄스": "댄스",
    "케이팝": "K-pop", "K-pop": "K-pop",
    "메탈": "헤비 메탈", "헤비 메탈": "헤비 메탈",
    "인디": "인디", "인디 록": "인디 록",
    "일렉트로닉": "일렉트로닉", "재즈": "재즈", "소울": "소울",
}

AWARD_CANON: dict[str, str] = {
    "한국대중음악상": "한국대중음악상",
    "골든디스크": "골든디스크", "골든디스크상": "골든디스크",
    "골든 디스크 어워즈": "골든디스크",
    "서울가요대상": "서울가요대상", "하이원 서울가요대상": "서울가요대상",
    "엠넷 아시안 뮤직 어워드": "엠넷 아시안 뮤직 어워드",
    "MAMA": "엠넷 아시안 뮤직 어워드",
    "멜론 뮤직 어워드": "멜론 뮤직 어워드",
}

LABEL_SUFFIX = r"(엔터테인먼트|뮤직|레코드|레코즈|컴퍼니|미디어|프로덕션|기획|음반사)"

STOPWORDS = {
    "대한민국", "한국", "음악", "가수", "그룹", "밴드", "앨범", "음반", "노래",
    "서울", "여자", "남자", "사람", "활동", "데뷔", "아이돌", "멤버",
}

CATEGORY_BLACKLIST = [
    r"동문$", r"출신$", r"^생존 인물$", r"^\d{4}년 출생$", r"^\d{4}년 사망$",
    r"^대한민국의 (남자|여자)", r"(개신교|천주교|불교|무종교)",
    r"(위키|문서|목록$|동음이의)", r"본관", r"국적",
    r"(배우|영화|드라마|예능|방송인|정치인|기업인)",
]

EXTRACTION_INSTRUCTIONS = """당신은 1992년 이후 한국 대중음악의 지식그래프를 만든다. 아래 규칙을 반드시 지켜라.

[개체 구분]
1. 개인 음악가는 Artist, 밴드·듀오·아이돌 그룹은 Group 이다. 절대 섞지 마라.
2. 문서 유형이 "그룹"이면 본문의 "이들", "멤버들", "팀"은 그 그룹을 가리킨다.
   문서 유형이 "인물"이면 "그는/그녀는"은 그 인물을 가리킨다.
3. 앨범과 곡이 같은 이름이면 두 개의 별도 노드로 만들고 타입을 명시하라.

[관계]
4. 소속 관계는 SIGNED_TO(head=Artist 또는 Group, tail=Label),
   설립 관계는 FOUNDED(head=Artist, tail=Label)다. 둘을 혼동하지 마라.
5. "~의 영향을 받았다"는 (영향을 준 쪽, INFLUENCED, 영향을 받은 쪽) 방향이다.
6. 리메이크·커버는 새 관계를 만들지 말고, 리메이크한 가수와 원곡 사이에
   PERFORMED 관계를 만들고 cover=true, year=<리메이크 연도> 를 기록하라.
7. 작사·작곡·편곡은 모두 WROTE 이며 role 속성에 "작사"/"작곡"/"편곡" 을 기록하라.
8. 과거 소속·탈퇴 멤버는 관계를 만들되 former=true 를 기록하라.

[근거]
9. 모든 관계에 quote 를 반드시 붙여라. quote 는 그 관계를 말하고 있는
   본문의 문장을 글자 그대로 복사한 것이어야 한다. 요약하거나 다듬지 마라.
   본문에서 그 문장을 찾을 수 없다면 그 관계를 아예 만들지 마라.

[금지]
10. 본문에 없는 사실을 추론하거나 보충하지 마라. 사전 지식을 쓰지 마라.
11. "가수", "음악", "한국", "그룹", "앨범", "노래" 같은 일반 명사를 노드로 만들지 마라.
12. 숫자(판매량, 순위)를 노드로 만들지 마라.
13. 배우 활동, 예능 프로그램, 사생활, 병역, 학력은 전부 무시하라.
"""

BRIDGE_DOC_EXTRA = """
[이 문서에 대한 추가 지시]
이 문서는 여러 세대의 아티스트를 한 자리에서 다룬다.
세대 간 영향 관계(INFLUENCED)와 수상 관계(WON), 음악방송 1위 기록(TOPPED_ON)을
최우선으로 추출하라.
"""
