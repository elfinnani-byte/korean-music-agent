import networkx as nx
import agent

CFG = {"retrieval": {
    "hub_degree_threshold": 25, "degree_penalty_exponent": 0.5,
    "per_relation": 10, "per_node_out": 8, "max_triples": 200,
    "quota_exempt_origins": ["rule", "tracklist"],
    "quota_exempt_relations": ["INFLUENCED", "COVERED", "PRODUCED", "WROTE", "FOUNDED"],
    "origin_base_score": {"rule": 1.0, "llm+rule": 1.1, "tracklist": 1.0,
                          "derived": 0.9, "llm": 0.8},
}}


def _chain_graph():
    g = nx.MultiDiGraph()
    g.add_node("artist:양현석", name="양현석", type="Artist", norm="양현석")
    g.add_node("group:서태지와아이들", name="서태지와 아이들", type="Group", norm="서태지와아이들")
    g.add_node("label:yg", name="YG 엔터테인먼트", type="Label", norm="yg엔터테인먼트")
    g.add_node("era:1990s", name="1990s", type="Era", norm="1990s")
    g.add_edge("artist:양현석", "group:서태지와아이들", relation="MEMBER_OF",
               origins=["rule"], agreement=1.0)
    g.add_edge("artist:양현석", "label:yg", relation="FOUNDED",
               origins=["llm"], agreement=0.8)
    g.add_edge("group:서태지와아이들", "era:1990s", relation="FORMED_IN",
               origins=["rule"], agreement=1.0)
    return g


def test_expand_records_trace_with_hop_and_direction():
    g = _chain_graph()
    state = {"frontier": ["artist:양현석"], "visited": ["artist:양현석"],
             "seeds": ["artist:양현석"], "triples": [], "trace": [],
             "gap_rels": [], "radius": 1}
    out = agent.expand_one_hop(g, state, CFG)
    rels = {t["rel"] for t in out["trace"]}
    assert "MEMBER_OF" in rels and "FOUNDED" in rels


def test_expand_never_puts_non_expanding_types_in_new_frontier():
    """Era·Genre 는 근거로 제시되지만 경유지가 되지 않는다."""
    g = _chain_graph()
    state = {"frontier": ["group:서태지와아이들"], "visited": ["artist:양현석", "group:서태지와아이들"],
             "seeds": ["artist:양현석"], "triples": [], "trace": [],
             "gap_rels": [], "radius": 1}
    out = agent.expand_one_hop(g, state, CFG)
    assert "era:1990s" not in out["frontier"]


def test_expand_skips_hub_nodes_as_expansion_source_unless_seed():
    g = nx.MultiDiGraph()
    g.add_node("label:hub", name="허브사", type="Label", norm="허브사")
    for i in range(30):
        g.add_node(f"artist:{i}", name=str(i), type="Artist", norm=str(i))
        g.add_edge(f"artist:{i}", "label:hub", relation="SIGNED_TO", origins=["rule"], agreement=1.0)
    state = {"frontier": ["label:hub"], "visited": ["label:hub"],
             "seeds": [], "triples": [], "trace": [], "gap_rels": [], "radius": 1}
    out = agent.expand_one_hop(g, state, CFG)
    assert out["trace"] == [], "허브를 경유지로 삼아 30명을 전부 끌고 오면 안 된다"


def test_expand_allows_hub_node_when_it_is_a_seed():
    g = nx.MultiDiGraph()
    g.add_node("label:hub", name="허브사", type="Label", norm="허브사")
    for i in range(30):
        g.add_node(f"artist:{i}", name=str(i), type="Artist", norm=str(i))
        g.add_edge(f"artist:{i}", "label:hub", relation="SIGNED_TO", origins=["rule"], agreement=1.0)
    state = {"frontier": ["label:hub"], "visited": ["label:hub"],
             "seeds": ["label:hub"], "triples": [], "trace": [], "gap_rels": [], "radius": 1}
    out = agent.expand_one_hop(g, state, CFG)
    assert len(out["trace"]) > 0, "시드일 때는 SM 소속 가수는? 같은 질문에 답해야 한다"


def test_expand_respects_per_relation_cap_but_exempts_bridge_relations():
    """PERFORMED 간선은 origins=['llm']로 둔다 — ['rule']을 쓰면
       quota_exempt_origins 자체에 걸려 상한이 면제되므로(규칙 기원은
       관계와 무관하게 항상 면제), '교량 관계라서 면제됐는가'를 제대로
       가르지 못한다."""
    g = nx.MultiDiGraph()
    g.add_node("artist:a", name="a", type="Artist", norm="a")
    for i in range(15):
        g.add_node(f"song:{i}", name=str(i), type="Song", norm=str(i))
        g.add_edge("artist:a", f"song:{i}", relation="PERFORMED", origins=["llm"], agreement=1.0)
    for i in range(15):
        g.add_node(f"art:{i}", name=f"art{i}", type="Artist", norm=f"art{i}")
        g.add_edge("artist:a", f"art:{i}", relation="INFLUENCED", origins=["llm"], agreement=1.0)
    cfg = {**CFG, "retrieval": {**CFG["retrieval"], "per_relation": 5, "per_node_out": 100}}
    state = {"frontier": ["artist:a"], "visited": ["artist:a"], "seeds": ["artist:a"],
             "triples": [], "trace": [], "gap_rels": [], "radius": 1}
    out = agent.expand_one_hop(g, state, cfg)
    performed = [t for t in out["trace"] if t["rel"] == "PERFORMED"]
    influenced = [t for t in out["trace"] if t["rel"] == "INFLUENCED"]
    assert len(performed) == 5, "PERFORMED 는 교량 관계가 아니므로 per_relation 상한이 걸려야 한다"
    assert len(influenced) == 15, "INFLUENCED 는 교량 관계라 상한에서 면제돼야 한다"
