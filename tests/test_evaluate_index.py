import networkx as nx
import evaluate as ev


def _g():
    g = nx.MultiDiGraph()
    g.add_node("artist:양현석", name="양현석", type="Artist", norm="양현석")
    g.add_node("group:서태지와아이들", name="서태지와 아이들", type="Group", norm="서태지와아이들")
    g.add_node("label:yg", name="YG 엔터테인먼트", type="Label", norm="yg엔터테인먼트")
    g.add_edge("artist:양현석", "group:서태지와아이들", relation="MEMBER_OF", origins=["rule"], agreement=1.0)
    g.add_edge("label:yg", "artist:양현석", relation="SIGNED_TO", origins=["rule"], agreement=1.0)  # 방향이 뒤집힌 예시
    return g


def test_exact_match_when_triple_exists_as_is():
    g = _g()
    assert ev.index_level(g, "양현석", "MEMBER_OF", "서태지와 아이들") == "exact"


def test_relaxed_when_any_relation_connects_but_not_the_expected_one():
    g = _g()
    assert ev.index_level(g, "양현석", "FOUNDED", "YG 엔터테인먼트") == "relaxed"


def test_node_when_only_both_entities_exist():
    g = _g()
    g.add_node("award:골든디스크", name="골든디스크", type="Award", norm="골든디스크")
    assert ev.index_level(g, "양현석", "WON", "골든디스크") == "node"


def test_none_when_an_entity_is_missing():
    g = _g()
    assert ev.index_level(g, "없는사람", "MEMBER_OF", "서태지와 아이들") == "none"


def test_index_score_reduces_expected_triples_to_best_level_each():
    g = _g()
    result = ev.index_score(g, [["양현석", "MEMBER_OF", "서태지와 아이들"],
                               ["없는사람", "WON", "골든디스크"]])
    assert result["exact"] == 0.5
    assert result["none"] == 0.5
