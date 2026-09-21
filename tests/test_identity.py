import normalize as nz


def test_type_vote_gives_rules_weight_five():
    """분류 기반 규칙 투표가 LLM 투표를 압도해야 그룹·인물 혼동을 막는다."""
    assert nz.vote_type(llm_votes={"Artist": 4}, rule_votes={"Group": 1}) == "Group"


def test_type_vote_prefers_entity_on_tie():
    assert nz.vote_type(llm_votes={"Genre": 1, "Song": 1}, rule_votes={}) == "Song"


def test_song_nodes_merge_by_title_regardless_of_referring_relation():
    """실측 버그: 맥락을 '이 삼중항의 수행자'로 잡으면 같은 곡이
       WROTE(작사가)·PERFORMED(가수)·RELEASED(음반) 등 관계마다
       다른 맥락을 얻어 여러 노드로 쪼개졌다('강남스타일' 4개 노드,
       COVERED 파생 0건). 실제 코퍼스에 동명이곡 충돌 증거가 없고
       Song·Album은 타입 접두사로 이미 다른 타입과 충돌하지 않으므로
       제목만으로 합친다."""
    assert nz.node_id("Butter", "Song") == nz.node_id("Butter", "Song")


def test_song_and_album_never_collide_even_with_same_title():
    """타입 접두사가 다르므로 동명 Song·Album 은 여전히 분리된다
       (SOLO DAY 곡과 SOLO DAY 음반 같은 실제 사례)."""
    assert nz.node_id("SOLO DAY", "Song") != nz.node_id("SOLO DAY", "Album")


def test_entity_nodes_merge_by_name_only():
    """Artist·Group·Label 은 이름으로 합친다."""
    assert nz.node_id("아이유", "Artist") == nz.node_id("아이유", "Artist")


def test_can_merge_songs_requires_shared_evidence():
    x = {"performers": {"방탄소년단"}, "albums": set(), "quotes": {"q1"}}
    y = {"performers": {"방탄소년단"}, "albums": set(), "quotes": set()}
    z = {"performers": {"다른가수"}, "albums": set(), "quotes": {"q2"}}
    assert nz.can_merge_songs(x, y)
    assert not nz.can_merge_songs(x, z)


def test_canonical_symmetric_orders_by_type_then_name():
    a = nz.canonical_symmetric(("나가수", "Artist"), ("가그룹", "Group"))
    b = nz.canonical_symmetric(("가그룹", "Group"), ("나가수", "Artist"))
    assert a == b, "정준화는 입력 순서와 무관해야 한다"
    assert a[0][1] == "Artist", "타입 순서를 먼저 본다"


import networkx as nx


def _tri(h, r, t, **kw):
    base = {"h": h, "r": r, "t": t, "props": {}, "origins": ["llm"],
            "agreement": 0.8, "sources": ["문서"], "quotes": ["근거"]}
    base.update(kw)
    return base


def test_merge_promotes_agreement_when_rule_and_llm_agree():
    g, _ = nz.merge_triples([
        _tri("아이유", "SIGNED_TO", "EDAM엔터테인먼트", origins=["llm"]),
        _tri("아이유", "SIGNED_TO", "EDAM엔터테인먼트", origins=["rule"], agreement=0.95),
    ], {"normalize": {"entity_type_overrides": {}}},
        types={"아이유": "Artist", "EDAM엔터테인먼트": "Label"})
    e = list(g.edges(data=True))[0][2]
    assert set(e["origins"]) == {"rule", "llm"}
    assert e["agreement"] == 1.0


def test_symmetric_relation_stored_once():
    g, _ = nz.merge_triples([
        _tri("가그룹", "COLLABORATED_WITH", "나가수"),
        _tri("나가수", "COLLABORATED_WITH", "가그룹"),
    ], {"normalize": {"entity_type_overrides": {}}},
        types={"가그룹": "Group", "나가수": "Artist"})
    assert g.number_of_edges() == 1


def test_covered_edge_is_derived_from_cover_flag():
    g = nx.MultiDiGraph()
    g.add_node("song:붉은노을:이문세", name="붉은 노을", type="Song", norm="붉은노을")
    g.add_node("artist:이문세", name="이문세", type="Artist")
    g.add_node("group:빅뱅", name="빅뱅", type="Group")
    g.add_edge("artist:이문세", "song:붉은노을:이문세", relation="PERFORMED",
               props={"cover": False}, origins=["llm"], agreement=0.8,
               sources=["이문세"], quotes=["q"])
    g.add_edge("group:빅뱅", "song:붉은노을:이문세", relation="PERFORMED",
               props={"cover": True, "year": 2008}, origins=["llm"], agreement=0.8,
               sources=["빅뱅"], quotes=["q"])

    nz.add_derived_edges(g)
    covered = [(u, v, d) for u, v, d in g.edges(data=True) if d["relation"] == "COVERED"]
    assert len(covered) == 1
    assert covered[0][0] == "group:빅뱅" and covered[0][1] == "artist:이문세"
    assert covered[0][2]["origins"] == ["derived"]


def test_covered_edge_bridges_song_nodes_that_happen_to_differ_by_id():
    """방어 테스트: node_id() 는 이제 제목만으로 합치므로 이 시나리오가
       merge_triples() 경로로는 더 이상 발생하지 않는다(예전에는 Song
       맥락이 '이 삼중항의 수행자'였던 탓에 '붉은 노을'이 song:...:이문세
       와 song:...:빅뱅 두 노드로 쪼개져 COVERED 파생이 52건 코퍼스에서
       0건이었다). add_derived_edges() 가 제목(norm)으로 묶는 것 자체는
       node_id() 변경과 무관하게 옳으므로, 노드 ID가 우연히 달라도
       제목이 같으면 여전히 이어야 한다는 것을 별도로 지킨다."""
    g = nx.MultiDiGraph()
    g.add_node("song:붉은노을:이문세", name="붉은 노을", type="Song", norm="붉은노을")
    g.add_node("song:붉은노을:빅뱅", name="붉은 노을", type="Song", norm="붉은노을")
    g.add_node("artist:이문세", name="이문세", type="Artist")
    g.add_node("group:빅뱅", name="빅뱅", type="Group")
    g.add_edge("artist:이문세", "song:붉은노을:이문세", relation="PERFORMED",
               props={}, origins=["llm"], agreement=0.8,
               sources=["이문세"], quotes=["q"])
    g.add_edge("group:빅뱅", "song:붉은노을:빅뱅", relation="PERFORMED",
               props={"cover": "2008"}, origins=["llm"], agreement=0.8,
               sources=["빅뱅"], quotes=["q"])

    nz.add_derived_edges(g)
    covered = [(u, v, d) for u, v, d in g.edges(data=True) if d["relation"] == "COVERED"]
    assert len(covered) == 1
    assert covered[0][0] == "group:빅뱅" and covered[0][1] == "artist:이문세"


def test_merge_infers_type_from_relation_when_unknown():
    """실측 버그: FORMED_IN/DEBUTED_IN/RELEASED_IN 대상('1990s' 등)은
       LLM이 영문 연대 코드를 우연히 쓰지 않는 한 types 사전에 없어서
       간선 전체가 통째로 드롭됐다(52건 코퍼스에서 0건 생존). WON도
       규칙만으로 얻은 시상식 이름이 같은 이유로 부분 드롭됐다.
       스키마상 관계마다 대상 타입이 하나로 고정돼 있으므로
       (SIGNED_TO/FOUNDED->Label, WON->Award, HAS_GENRE->Genre,
       FORMED_IN/DEBUTED_IN/RELEASED_IN->Era) types 사전에 없어도
       관계에서 타입을 추론해야 한다."""
    # 헤드(아티스트·그룹) 타입은 실제 파이프라인에서 문서 자체의 분류
    # 투표로 채워진다. 이 테스트가 재현하는 버그는 테일(연대·시상식·
    # 레이블처럼 자기 문서가 없는 폐쇄 어휘) 쪽이므로 헤드 타입은
    # 미리 채워 둔다.
    types = {"서태지와 아이들": "Group", "아이유": "Artist",
             "빅뱅": "Group", "보아": "Artist"}
    g, report = nz.merge_triples([
        _tri("서태지와 아이들", "FORMED_IN", "1990s", props={"year": 1991}),
        _tri("아이유", "DEBUTED_IN", "2000s", props={"year": 2008}),
        _tri("빅뱅", "WON", "골든디스크"),
        _tri("보아", "SIGNED_TO", "SM 엔터테인먼트"),
    ], {"normalize": {"entity_type_overrides": {}}}, types=types)
    assert g.number_of_edges() == 4
    assert g.nodes["era:1990s"]["type"] == "Era"
    assert g.nodes["award:골든디스크"]["type"] == "Award"
    assert g.nodes["label:sm엔터테인먼트"]["type"] == "Label"
    assert report["dropped_junk"] == []


def test_labelmate_edges_are_never_created():
    """SM 소속 30명이면 435개 간선이 생겨 그래프를 오염시킨다."""
    g = nx.MultiDiGraph()
    for who in ("a", "b", "c"):
        g.add_node(f"artist:{who}", name=who, type="Artist")
        g.add_edge(f"artist:{who}", "label:sm", relation="SIGNED_TO",
                   props={}, origins=["rule"], agreement=1.0,
                   sources=["x"], quotes=[])
    g.add_node("label:sm", name="SM", type="Label")
    before = g.number_of_edges()
    nz.add_derived_edges(g)
    assert g.number_of_edges() == before
