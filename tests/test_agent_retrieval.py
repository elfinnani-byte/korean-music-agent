import networkx as nx
import agent

CFG = {"retrieval": {
    "hub_degree_threshold": 25, "degree_penalty_exponent": 0.5,
    "per_relation": 10, "per_node_out": 8, "max_triples": 200,
    "radius": 2, "max_radius": 3,
    "quota_exempt_origins": ["rule", "tracklist"],
    "quota_exempt_relations": ["INFLUENCED", "COVERED", "PRODUCED", "WROTE", "FOUNDED"],
    "origin_base_score": {"rule": 1.0, "llm+rule": 1.1, "tracklist": 1.0,
                          "derived": 0.9, "llm": 0.8},
}}


def _three_hop_chain():
    g = nx.MultiDiGraph()
    g.add_node("artist:박진영", name="박진영", type="Artist", norm="박진영")
    g.add_node("label:jyp", name="JYP 엔터테인먼트", type="Label", norm="jyp엔터테인먼트")
    g.add_node("group:straykids", name="Stray Kids", type="Group", norm="straykids")
    g.add_node("song:district9", name="District 9", type="Song", norm="district9")
    g.add_edge("artist:박진영", "label:jyp", relation="FOUNDED", origins=["rule"], agreement=1.0)
    g.add_edge("group:straykids", "label:jyp", relation="SIGNED_TO", origins=["rule"], agreement=1.0)
    g.add_edge("group:straykids", "song:district9", relation="PERFORMED", origins=["llm"], agreement=0.8)
    return g


def test_run_retrieval_reaches_third_hop_when_gap_remains():
    g = _three_hop_chain()
    required = [["FOUNDED"], ["SIGNED_TO"], ["PERFORMED"]]
    out = agent.run_retrieval(g, seeds=["artist:박진영"], required_rels=required, cfg=CFG)
    rels = {t["r"] for t in out["triples"]}
    assert {"FOUNDED", "SIGNED_TO", "PERFORMED"} <= rels
    assert out["radius_used"] >= 2  # 순방향/역방향 섞인 3홉이라 반경이 늘어야 닿는다


def test_run_retrieval_stops_early_when_gap_resolved_at_radius_1():
    g = nx.MultiDiGraph()
    g.add_node("artist:a", name="a", type="Artist", norm="a")
    g.add_node("group:b", name="b", type="Group", norm="b")
    g.add_edge("artist:a", "group:b", relation="MEMBER_OF", origins=["rule"], agreement=1.0)
    out = agent.run_retrieval(g, seeds=["artist:a"], required_rels=[["MEMBER_OF"]], cfg=CFG)
    assert out["radius_used"] == 1


def test_run_retrieval_gives_up_at_max_radius_with_gap_reported():
    """고립 노드 하나만 두면 첫 홉에서 프런티어가 곧장 비어 버려
       '프런티어 소진'과 '반경 소진'을 구분하지 못한다. 체인을 3홉 이상
       이어 둬 반경이 실제로 다 찰 때까지 프런티어가 남아 있게 한다."""
    g = nx.MultiDiGraph()
    for name in ("a", "b", "c", "d"):
        g.add_node(f"artist:{name}", name=name, type="Artist", norm=name)
    g.add_edge("artist:a", "artist:b", relation="COLLABORATED_WITH", origins=["rule"], agreement=1.0)
    g.add_edge("artist:b", "artist:c", relation="COLLABORATED_WITH", origins=["rule"], agreement=1.0)
    g.add_edge("artist:c", "artist:d", relation="COLLABORATED_WITH", origins=["rule"], agreement=1.0)
    out = agent.run_retrieval(g, seeds=["artist:a"], required_rels=[["WON"]], cfg=CFG)
    assert out["radius_used"] == CFG["retrieval"]["max_radius"]
    assert out["gap_rels"] == [["WON"]]
