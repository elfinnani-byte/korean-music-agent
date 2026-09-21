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


def test_run_retrieval_none_hub_threshold_override_actually_disables_hub_blocking():
    """실측 버그: hub_degree_threshold_override=None 을 'override 없음'과
       구별하지 못하면, 스윕 격자의 '차단 없음' 칸이 그냥 기본 임계값으로
       조용히 되돌아간다. None 을 명시적으로 넘기면 실제로 허브 차단이
       꺼져야 한다."""
    g = nx.MultiDiGraph()
    g.add_node("label:hub", name="허브사", type="Label", norm="허브사")
    g.add_node("group:target", name="target", type="Group", norm="target")
    for i in range(30):
        g.add_node(f"artist:{i}", name=str(i), type="Artist", norm=str(i))
        g.add_edge(f"artist:{i}", "label:hub", relation="SIGNED_TO", origins=["rule"], agreement=1.0)
    g.add_edge("label:hub", "group:target", relation="FOUNDED", origins=["rule"], agreement=1.0)

    capped = agent.run_retrieval(g, seeds=["artist:0"], required_rels=[["FOUNDED"]], cfg=CFG,
                                 hub_degree_threshold_override=25)
    uncapped = agent.run_retrieval(g, seeds=["artist:0"], required_rels=[["FOUNDED"]], cfg=CFG,
                                   hub_degree_threshold_override=None)
    assert capped["gap_rels"] == [["FOUNDED"]], "허브(hub)를 경유하지 못해 FOUNDED 를 못 찾아야 한다"
    assert uncapped["gap_rels"] == [], "차단을 껐으면 허브를 지나 FOUNDED 를 찾아야 한다"


def test_run_retrieval_boosts_required_relation_on_first_hop():
    """실측 버그: gap_rels 는 expand_one_hop() 이 끝난 *뒤에* triples 로부터
       계산되는데, 1홉째는 그 계산이 아직 한 번도 안 돈 시점이라
       state['gap_rels'] 가 빈 리스트로 시작한다. edge_score() 의 필수
       관계 우선순위(1.3배)는 이 gap_rels 멤버십으로 판정하므로, 정확히
       씨앗에서 뻗어나가는 1홉째에서는 필수 관계도 가산점을 못 받고
       degree_penalty 가 큰(차수 높은) 꼬리 노드로 가는 필수 간선이
       per_node_out 컷오프 밖으로 밀려날 수 있다(실측: 지드래곤->빅뱅
       MEMBER_OF, 빅뱅 차수 87). required_rels 를 첫 홉 전에 gap_rels 로
       미리 심어 둬야 한다."""
    g = nx.MultiDiGraph()
    g.add_node("artist:seed", name="seed", type="Artist", norm="seed")
    g.add_node("song:d1", name="d1", type="Song", norm="d1")
    g.add_node("song:d2", name="d2", type="Song", norm="d2")
    g.add_node("award:req", name="req", type="Award", norm="req")
    g.add_node("artist:other1", name="other1", type="Artist", norm="other1")
    g.add_node("artist:other2", name="other2", type="Artist", norm="other2")
    g.add_node("artist:other3", name="other3", type="Artist", norm="other3")
    g.add_node("artist:other4", name="other4", type="Artist", norm="other4")
    # d1, d2 는 차수 2(경쟁 간선 없이 흔한 관계), req 는 차수 3(필수 관계지만
    # 허브 감점을 더 받는 꼬리 노드) 이 되도록 곁가지 간선을 하나씩 더 단다.
    g.add_edge("artist:seed", "song:d1", relation="PERFORMED", origins=["llm"], agreement=1.0)
    g.add_edge("artist:other1", "song:d1", relation="PERFORMED", origins=["llm"], agreement=1.0)
    g.add_edge("artist:seed", "song:d2", relation="PERFORMED", origins=["llm"], agreement=1.0)
    g.add_edge("artist:other2", "song:d2", relation="PERFORMED", origins=["llm"], agreement=1.0)
    g.add_edge("artist:seed", "award:req", relation="WON", origins=["llm"], agreement=1.0)
    g.add_edge("artist:other3", "award:req", relation="WON", origins=["llm"], agreement=1.0)
    g.add_edge("artist:other4", "award:req", relation="WON", origins=["llm"], agreement=1.0)

    cfg = {**CFG, "retrieval": {**CFG["retrieval"], "per_node_out": 2, "hub_degree_threshold": 25}}
    out = agent.run_retrieval(g, seeds=["artist:seed"], required_rels=[["WON"]], cfg=cfg)
    assert out["gap_rels"] == [], "필수 관계(WON)가 1홉째 가산점을 받아 per_node_out 컷오프 안에 들어야 한다"


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
