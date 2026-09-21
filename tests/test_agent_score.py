import networkx as nx
import agent

CFG = {"retrieval": {
    "hub_degree_threshold": 25, "degree_penalty_exponent": 0.5,
    "origin_base_score": {"rule": 1.0, "llm+rule": 1.1, "tracklist": 1.0,
                          "derived": 0.9, "llm": 0.8},
}}


def _g_with_degree(tail_degree):
    g = nx.MultiDiGraph()
    g.add_node("a"); g.add_node("t")
    for i in range(tail_degree):
        g.add_node(f"n{i}")
        g.add_edge(f"n{i}", "t", relation="X")
    return g


def test_high_agreement_rule_edge_scores_higher_than_low_agreement_llm_edge():
    g = _g_with_degree(1)
    rule_edge = {"origins": ["rule"], "agreement": 1.0, "relation": "MEMBER_OF"}
    llm_edge = {"origins": ["llm"], "agreement": 0.8, "relation": "MEMBER_OF"}
    state = {"gap_rels": []}
    s_rule = agent.edge_score(g, "t", rule_edge, state, CFG)
    s_llm = agent.edge_score(g, "t", llm_edge, state, CFG)
    assert s_rule > s_llm


def test_high_degree_tail_is_penalized():
    low = _g_with_degree(1)
    high = _g_with_degree(50)
    edge = {"origins": ["rule"], "agreement": 1.0, "relation": "MEMBER_OF"}
    state = {"gap_rels": []}
    assert agent.edge_score(low, "t", edge, state, CFG) > agent.edge_score(high, "t", edge, state, CFG)


def test_gap_relation_gets_priority_boost():
    g = _g_with_degree(1)
    edge = {"origins": ["rule"], "agreement": 1.0, "relation": "WON"}
    filled = agent.edge_score(g, "t", edge, {"gap_rels": []}, CFG)
    gapped = agent.edge_score(g, "t", edge, {"gap_rels": ["WON"]}, CFG)
    assert gapped > filled


def test_bridge_relation_gets_smaller_boost_than_gap_when_not_gap():
    g = _g_with_degree(1)
    bridge_edge = {"origins": ["rule"], "agreement": 1.0, "relation": "INFLUENCED"}
    normal_edge = {"origins": ["rule"], "agreement": 1.0, "relation": "MEMBER_OF"}
    state = {"gap_rels": []}
    assert agent.edge_score(g, "t", bridge_edge, state, CFG) > agent.edge_score(g, "t", normal_edge, state, CFG)


def test_is_hub_recomputed_live_not_from_stored_attribute():
    """graph.json 의 is_hub 는 빌드 시점 임계값으로 굳어 있다. 스윕이 다른
       임계값을 넘기면 저장된 값이 아니라 그 임계값으로 다시 판정해야 한다."""
    g = _g_with_degree(30)
    g.nodes["t"]["is_hub"] = False  # 저장된 값은 일부러 틀리게 둔다
    assert agent.is_hub(g, "t", threshold=25) is True
    assert agent.is_hub(g, "t", threshold=40) is False
