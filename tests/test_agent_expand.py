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


def test_expand_per_node_out_keeps_highest_scored_edges_not_first_in_graph_order():
    """실측 버그: per_node_out 절단을 점수 계산 '이전'에 원시 순서
       그대로 걸면(g.out_edges(nid)[:8]), 정작 필요한 간선이 그래프
       삽입 순서상 9번째라는 이유만으로 점수 한 번 못 매겨 보고
       통째로 사라진다. 지드래곤(out-degree 9)의 MEMBER_OF 간선이
       정확히 이렇게 사라져 골든셋 Q10이 실패했다. gap_rels 우선순위
       1.3배를 받는 관계는, 그래프 삽입 순서가 몇 번째든 8개 안에
       들어야 한다."""
    g = nx.MultiDiGraph()
    g.add_node("artist:a", name="a", type="Artist", norm="a")
    g.add_node("group:target", name="target", type="Group", norm="target")
    # MEMBER_OF 를 마지막(9번째)에 추가해 삽입 순서상 최하위로 둔다
    for i in range(8):
        g.add_node(f"song:{i}", name=str(i), type="Song", norm=str(i))
        g.add_edge("artist:a", f"song:{i}", relation="PERFORMED", origins=["rule"], agreement=1.0)
    g.add_edge("artist:a", "group:target", relation="MEMBER_OF", origins=["rule"], agreement=1.0)

    state = {"frontier": ["artist:a"], "visited": ["artist:a"], "seeds": ["artist:a"],
             "triples": [], "trace": [], "gap_rels": ["MEMBER_OF"], "radius": 1}
    out = agent.expand_one_hop(g, state, CFG)
    rels = {t["rel"] for t in out["trace"]}
    assert "MEMBER_OF" in rels, "삽입 순서상 9번째라고 점수도 못 매겨 보고 잘리면 안 된다"


def test_expand_per_node_out_does_not_drop_quota_exempt_candidates():
    """실측 버그: per_node_out 절단이 quota_exempt_origins/relations 를
       전혀 모른 채 점수만으로 상위 N개를 자른다. _select_within_budget()
       의 면제 로직은 이미 여기서 잘려 나간 후보에는 적용될 기회조차
       없다 - '규칙 기원이라 상한 면제'라는 설계가 이 단계에서는
       지켜지지 않는다. 골든셋 Q22("빅뱅은 몇 년대에 데뷔한 그룹인가?")
       재평가에서, 규칙 기원 WON 간선들이 많아 DEBUTED_IN(비면제, 저점수)
       이 per_node_out 에 잘리면서 실제로 이 패턴이 재현됐다."""
    g = nx.MultiDiGraph()
    g.add_node("artist:a", name="a", type="Artist", norm="a")
    g.add_node("era:target", name="target", type="Era", norm="target")
    # 비면제(origin=llm) 고득점 후보 5개가 per_node_out=3 안을 채운다
    for i in range(5):
        g.add_node(f"song:{i}", name=str(i), type="Song", norm=str(i))
        g.add_edge("artist:a", f"song:{i}", relation="PERFORMED", origins=["llm"], agreement=1.0)
    # 면제(origin=rule) 후보 1개는 점수가 가장 낮아 순위로는 꼴찌다
    g.add_edge("artist:a", "era:target", relation="DEBUTED_IN", origins=["rule"], agreement=0.3)

    cfg = {**CFG, "retrieval": {**CFG["retrieval"], "per_node_out": 3}}
    state = {"frontier": ["artist:a"], "visited": ["artist:a"], "seeds": ["artist:a"],
             "triples": [], "trace": [], "gap_rels": [], "radius": 1}
    out = agent.expand_one_hop(g, state, cfg)
    rels = {t["rel"] for t in out["trace"]}
    assert "DEBUTED_IN" in rels, "규칙 기원(면제 대상)은 per_node_out 절단에서도 살아남아야 한다"


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
