import networkx as nx
import graph_gate as gg


def _chain():
    g = nx.MultiDiGraph()
    g.add_node("artist:a", name="A", type="Artist")
    g.add_node("group:b", name="B", type="Group")
    g.add_node("label:c", name="C", type="Label")
    g.add_edge("artist:a", "group:b", relation="MEMBER_OF")
    g.add_edge("artist:a", "label:c", relation="FOUNDED")
    return g


def test_largest_component_ratio():
    g = _chain()
    g.add_node("artist:z", name="Z", type="Artist")
    assert gg.largest_component_ratio(g) == 0.75


def test_bridge_edge_count():
    assert gg.bridge_edge_count(_chain()) == 1  # FOUNDED 만 교량


def test_goldenset_reachable_checks_actual_graph():
    """스키마상 가능해도 실제 그래프에 개체가 없으면 답할 수 없다."""
    g = _chain()
    item = {"id": "Q01", "expected_triples": [["A", "MEMBER_OF", "B"]]}
    assert gg.item_reachable(g, item)

    missing = {"id": "Q02", "expected_triples": [["없는사람", "MEMBER_OF", "B"]]}
    assert not gg.item_reachable(g, missing)


def test_verdict_separates_two_criteria():
    v = gg.verdict(component_ratio=0.6, reachable_rate=1.0, bridge_edges=30,
                   gates={"min_largest_component_ratio": 0.85, "min_bridge_edges": 20})
    assert v["passed"] is False
    assert any("연결성" in r for r in v["reasons"])
    assert not any("경로" in r for r in v["reasons"])
