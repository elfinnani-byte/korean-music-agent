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
    "Mnet 아시안 뮤직 어워드": "엠넷 아시안 뮤직 어워드",
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
    r"(개신교|천주교|불교|무종교)",
    r"(위키|문서|목록$|동음이의)", r"본관", r"국적",
    r"(배우|영화|드라마|예능|방송인|정치인|기업인)",
]
# 주의: "^대한민국의 (남자|여자)" 패턴을 넣지 않는다. "대한민국의 여자 가수"처럼
# 성별+직업이 결합된 카테고리는 이 도메인에서 가장 흔한 실제 카테고리이고,
# is_music_doc() 은 카테고리 하나만 걸려도 문서 전체를 버리므로 그 패턴을 쓰면
# 솔로 아티스트 문서 대부분이 코퍼스에서 빠진다. "여자"·"남자"가 Genre 로 잘못
# 채택되는 것은 R01 규칙의 GENRE_CANON 화이트리스트가 막는다(캡처값이 사전에
# 없으면 간선 자체를 안 만든다). 배우·방송인 같은 비음악 카테고리는 위의
# 별도 항목이 이미 걸러낸다.

EXTRACTION_INSTRUCTIONS = f"""당신은 1992년 이후 한국 대중음악의 지식그래프를 만든다. 아래 규칙을 반드시 지켜라.

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
9. 연도가 나오면 반드시 연대 관계를 만들어라.
   - 개인·그룹이 "YYYY년 데뷔"했다는 문장 -> DEBUTED_IN, year=YYYY
   - 그룹이 "YYYY년 결성/설립"됐다는 문장 -> FORMED_IN, year=YYYY
   - 음반·곡이 "YYYY년 발매"됐다는 문장 -> RELEASED_IN, year=YYYY
   세 관계 모두 tail 노드는 다음 다섯 값 중 정확히 하나여야 한다. 한국어로
   "1990년대"라고 쓰지 말고 반드시 이 영문 표기 그대로 써라:
   {", ".join(repr(e) for e in ERAS)}
   (1980년 이전 연도는 "{ERAS[0]}"를 쓴다. 예: 1988년 -> "{ERAS[0]}",
   1996년 -> "{ERAS[1]}", 2003년 -> "{ERAS[2]}", 2013년 -> "{ERAS[3]}",
   2022년 -> "{ERAS[4]}".)

[근거]
10. 모든 관계에 quote 를 반드시 붙여라. quote 는 그 관계를 말하고 있는
    본문의 문장을 글자 그대로 복사한 것이어야 한다. 요약하거나 다듬지 마라.
    본문에서 그 문장을 찾을 수 없다면 그 관계를 아예 만들지 마라.

[금지]
11. 본문에 없는 사실을 추론하거나 보충하지 마라. 사전 지식을 쓰지 마라.
12. "가수", "음악", "한국", "그룹", "앨범", "노래" 같은 일반 명사를 노드로 만들지 마라.
13. 숫자(판매량, 순위)를 노드로 만들지 마라. 단, 9번 규칙의 연대 관계는 예외다.
14. 배우 활동, 예능 프로그램, 사생활, 병역, 학력은 전부 무시하라.
"""

BRIDGE_DOC_EXTRA = """
[이 문서에 대한 추가 지시]
이 문서는 여러 세대의 아티스트를 한 자리에서 다룬다.
세대 간 영향 관계(INFLUENCED)와 수상 관계(WON), 음악방송 1위 기록(TOPPED_ON)을
최우선으로 추출하라.
"""

# 에이전트 라우팅 단서어와 프롬프트. 도메인 어휘이므로 schema.py 에 둔다
# (config.json 은 튜닝 가능한 수치만 담는다는 9.3 원칙과 같은 이유).

CUE_TO_RELATIONS: dict[str, list[str]] = {
    "멤버|일원|구성원": ["MEMBER_OF"],
    "유닛|서브유닛": ["SUBUNIT_OF"],
    "소속|소속사": ["SIGNED_TO"],
    "설립|세운|창립": ["FOUNDED"],
    r"데뷔(?!곡)": ["DEBUTED_IN"],  # '데뷔곡'은 데뷔 시점이 아니라 노래를 가리키는 명사구다
    "결성|창단": ["FORMED_IN"],
    "발매|나온|수록된 음반": ["RELEASED_IN"],
    "수상|받은 상|탄 상": ["WON"],
    "작곡|작사|만든 곡": ["WROTE"],
    "프로듀|제작": ["PRODUCED"],
    "수록|실린|타이틀곡": ["CONTAINS"],
    "리메이크|커버|다시 불": ["COVERED", "PERFORMED"],
    "영향": ["INFLUENCED"],
    "장르|계열": ["HAS_GENRE"],
    "함께|협업|피처링": ["COLLABORATED_WITH"],
    "1위|차트": ["TOPPED_ON"],
}
GLOBAL_HINTS = ["전체적으로", "어떤 집단", "흐름", "지형", "전반", "계보"]
VECTOR_HINTS = ["분위기", "느낌", "어떤 음악", "설명해", "무엇이 특별", "평가"]

ANSWER_SYSTEM_PROMPT = """아래 [근거 삼중항]에 등장하는 개체명만 사용하여 답하라.
근거에 없는 사람 이름, 그룹명, 곡명, 앨범명, 회사명을 단 하나도 쓰지 마라.
연도는 근거의 year 값에 있는 것만 쓰고, 없으면 연도를 언급하지 마라.
개수를 맞추려고 근거 밖의 항목을 채우지 마라.
답을 근거로부터 유도할 수 없으면 정확히 "근거가 부족합니다"라고만 답하라.

답변 형식:
답: <한 문장>
경로: <시드> -[관계]-> <중간> -[관계]-> <답>
근거: 사용한 삼중항만 (h, r, t) 형태로 나열"""

ROUTE_LLM_PROMPT = """질문을 다음 다섯 경로 중 하나로 분류한다.
- local: 개체 하나에 대한 단순 사실 질의 (예: 이 사람 소속은?)
- path: 여러 관계를 거쳐야 답이 나오는 질의 (예: A가 세운 회사에 소속된 B는?)
- global: 특정 개체가 아니라 도메인 전체의 경향·흐름을 묻는 질의
- vector: 분위기·느낌처럼 구조화된 관계로 답할 수 없는 서술형 질의
- reject: 한국 대중음악 1992~현재 도메인과 무관한 질의

질문에서 언급된 관계(예: 소속·설립·수상)가 있으면 그 이름도 스키마 관계명으로 뽑는다.
스키마 관계명: {relation_names}

아래 JSON 형식으로만 답하라. 다른 말은 절대 덧붙이지 마라.
{{"route": "local|path|global|vector|reject", "required_rels": [["REL1"], ["REL2", "REL3"]]}}
required_rels 의 안쪽 리스트는 OR 그룹이다(그중 하나만 있으면 충분). 관계가 필요 없으면 빈 리스트.

질문: {question}"""

JUDGE_PROMPT = """아래는 질문, 모델이 낸 답, 정답, 정답의 원문 근거다.
답이 정답과 실질적으로 같은 사실을 말하면 1.0, 부분적으로만 맞으면 0.5,
틀렸거나 근거 없는 내용을 지어냈으면 0.0을 매긴다.
정답이 "기권해야 함"으로 표시돼 있다면, 모델이 구체적인 답을 지어내지 않고
근거 부족을 인정했을 때만 1.0이고 무엇이든 구체적으로 답했으면 0.0이다.

질문: {question}
모델의 답: {model_answer}
정답: {gold_answer}
원문 근거: {evidence}

숫자만 정확히 하나 출력하라 (1.0 또는 0.5 또는 0.0). 다른 말은 쓰지 마라."""
