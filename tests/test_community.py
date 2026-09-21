import networkx as nx
import community as cm


def _g():
    g = nx.MultiDiGraph()
    for i in range(5):
        g.add_node(f"artist:{i}", name=str(i), type="Artist")
    g.add_node("genre:댄스", name="댄스", type="Genre")
    for i in range(4):
        g.add_edge(f"artist:{i}", f"artist:{i+1}", relation="COLLABORATED_WITH",
                   origins=["rule"], agreement=1.0)
        g.add_edge(f"artist:{i}", "genre:댄스", relation="HAS_GENRE",
                   origins=["rule"], agreement=1.0)
    return g


def test_edge_weight_decays_attribute_touching_edges():
    g = _g()
    w_normal = cm.edge_weight(g, "artist:0", "artist:1", {"agreement": 1.0}, attr_weight=0.3)
    w_attr = cm.edge_weight(g, "artist:0", "genre:댄스", {"agreement": 1.0}, attr_weight=0.3)
    assert w_attr < w_normal


def test_detect_communities_skips_communities_smaller_than_min_size():
    g = _g()
    comms = cm.detect_communities(g, attr_weight=0.3, resolution=1.0, min_size=4, seed=42)
    for c in comms:
        assert len(c) >= 4


def test_profile_community_has_aggregate_fields_not_raw_node_list():
    """이 목적은 profile_community() 출력 형태만 확인하는 것이다(크기
       필터 자체는 위 테스트가 이미 검증). 6개 노드짜리 이 그래프는
       Louvain 이 3+3 으로 쪼개(실측) min_size=4 를 통과하는 커뮤니티가
       없으므로, 이 테스트에서만 3으로 낮춰 실제로 나오는 커뮤니티를 쓴다."""
    g = _g()
    comms = cm.detect_communities(g, attr_weight=0.3, resolution=1.0, min_size=3, seed=42)
    profile = cm.profile_community(g, comms[0])
    for k in ("size", "n_edges", "n_artists", "top_artists", "top_groups",
              "genre_distribution", "era_span", "relation_composition"):
        assert k in profile
