import evaluate as ev

TRACE = [
    {"hop": 1, "head": "양현석", "rel": "MEMBER_OF", "tail": "서태지와 아이들", "dir": "in"},
    {"hop": 2, "head": "양현석", "rel": "FOUNDED", "tail": "YG 엔터테인먼트", "dir": "out"},
]


def test_path_prefix_recall_full_match_returns_1():
    paths = [[{"hop": 1, "rel": "MEMBER_OF", "dir": "in", "to_type": "Artist"},
              {"hop": 2, "rel": "FOUNDED", "dir": "out", "to_type": "Label"}]]
    recall, break_hop, idx = ev.path_prefix_recall(paths, TRACE)
    assert recall == 1.0 and break_hop is None and idx == 0


def test_path_prefix_recall_breaks_at_second_hop():
    paths = [[{"hop": 1, "rel": "MEMBER_OF", "dir": "in", "to_type": "Artist"},
              {"hop": 2, "rel": "WON", "dir": "out", "to_type": "Award"}]]
    recall, break_hop, idx = ev.path_prefix_recall(paths, TRACE)
    assert recall == 0.5 and break_hop == 2


def test_path_prefix_recall_takes_max_over_alternatives():
    """대안 경로가 여럿이면 최댓값을 취한다 — 옳은 다른 길로 도달한 실행이
       오답으로 채점되면 안 된다."""
    wrong = [{"hop": 1, "rel": "WON", "dir": "out", "to_type": "Award"}]
    right = [{"hop": 1, "rel": "MEMBER_OF", "dir": "in", "to_type": "Artist"},
             {"hop": 2, "rel": "FOUNDED", "dir": "out", "to_type": "Label"}]
    recall, break_hop, idx = ev.path_prefix_recall([wrong, right], TRACE)
    assert recall == 1.0 and idx == 1


def test_path_prefix_recall_searches_within_hop_not_by_flat_position():
    """실측 버그: trace 는 한 홉에서 찾은 '모든' 간선을 담는다(예: 빅뱅
       노드에서 WON·HAS_GENRE·WON·WON·... 이 DEBUTED_IN 보다 먼저 옴,
       점수 내림차순이기 때문). trace[i] 를 곧바로 '기대 경로의 i번째
       홉'으로 취급하면, 같은 홉에 관련 없는 간선이 여럿 있을 때마다
       거의 항상 0홉에서 끊긴 것처럼 나온다 — 실제로는 hop=1 안에
       기대한 관계가 있는데도 그렇다. hop 번호로 걸러 그 안에서
       찾아야 한다."""
    trace = [
        {"hop": 1, "head": "빅뱅", "rel": "WON", "tail": "멜론 뮤직 어워드", "dir": "out"},
        {"hop": 1, "head": "빅뱅", "rel": "HAS_GENRE", "tail": "댄스", "dir": "out"},
        {"hop": 1, "head": "빅뱅", "rel": "DEBUTED_IN", "tail": "2000s", "dir": "out"},
        {"hop": 1, "head": "빅뱅", "rel": "WON", "tail": "골든디스크", "dir": "out"},
    ]
    paths = [[{"hop": 1, "rel": "DEBUTED_IN", "dir": "out", "to_type": "Era"}]]
    recall, break_hop, idx = ev.path_prefix_recall(paths, trace)
    assert recall == 1.0 and break_hop is None


def test_path_prefix_recall_still_breaks_when_hop_truly_missing():
    trace = [{"hop": 1, "head": "빅뱅", "rel": "WON", "tail": "멜론 뮤직 어워드", "dir": "out"}]
    paths = [[{"hop": 1, "rel": "DEBUTED_IN", "dir": "out", "to_type": "Era"}]]
    recall, break_hop, idx = ev.path_prefix_recall(paths, trace)
    assert recall == 0.0 and break_hop == 1


def test_triple_recall_counts_expected_triples_present_in_final_triples():
    triples = [{"h": "양현석", "r": "MEMBER_OF", "t": "서태지와 아이들"}]
    expected = [["양현석", "MEMBER_OF", "서태지와 아이들"], ["양현석", "FOUNDED", "YG 엔터테인먼트"]]
    assert ev.triple_recall(triples, expected) == 0.5


def test_sweep_grid_runs_without_llm_and_reports_recall_per_combo(tmp_path):
    import networkx as nx
    g = nx.MultiDiGraph()
    g.add_node("artist:a", name="a", type="Artist", norm="a")
    g.add_node("group:b", name="b", type="Group", norm="b")
    g.add_edge("artist:a", "group:b", relation="MEMBER_OF", origins=["rule"], agreement=1.0)
    items = [{"id": "Q01", "answer_type": "single", "seed_hint": ["a"],
              "expected_triples": [["a", "MEMBER_OF", "b"]],
              "expected_paths": [[{"hop": 1, "rel": "MEMBER_OF", "dir": "out", "to_type": "Group"}]]}]
    cfg = {"retrieval": {"radius": 2, "max_radius": 3, "hub_degree_threshold": 25,
                         "degree_penalty_exponent": 0.5, "per_relation": 10,
                         "per_node_out": 8, "max_triples": 200,
                         "quota_exempt_origins": ["rule"], "quota_exempt_relations": [],
                         "origin_base_score": {"rule": 1.0, "llm": 0.8, "llm+rule": 1.1,
                                               "tracklist": 1.0, "derived": 0.9}},
           "eval": {"sweep": {"max_radius": [2, 3], "hub_degree_threshold": [25],
                              "per_relation": [10], "max_triples": [200]}}}
    result = ev.sweep(g, items, cfg)
    assert len(result) == 2  # max_radius 축 2칸, 나머지 각 1칸
    assert all("avg_triple_recall" in row for row in result)
