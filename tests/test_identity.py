import normalize as nz


def test_type_vote_gives_rules_weight_five():
    """분류 기반 규칙 투표가 LLM 투표를 압도해야 그룹·인물 혼동을 막는다."""
    assert nz.vote_type(llm_votes={"Artist": 4}, rule_votes={"Group": 1}) == "Group"


def test_type_vote_prefers_entity_on_tie():
    assert nz.vote_type(llm_votes={"Genre": 1, "Song": 1}, rule_votes={}) == "Song"


def test_node_id_includes_context_for_song():
    a = nz.node_id("Butter", "Song", context="방탄소년단")
    b = nz.node_id("Butter", "Song", context="다른가수")
    assert a != b, "제목만으로 합치면 없는 리메이크가 생긴다"


def test_node_id_without_context_is_stable():
    assert nz.node_id("Butter", "Song", context=None) == nz.node_id("Butter", "Song", None)


def test_entity_nodes_merge_by_name_only():
    """Artist·Group·Label 은 맥락 없이 이름으로 합친다."""
    assert nz.node_id("아이유", "Artist", context="a") == nz.node_id("아이유", "Artist", "b")


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
    g.add_node("song:붉은노을:이문세", name="붉은 노을", type="Song")
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
