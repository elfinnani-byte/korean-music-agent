import networkx as nx
import evaluate as ev


class _FakeRouteLLM:
    def invoke(self, prompt):
        class R:
            content = '{"route": "local", "required_rels": [["MEMBER_OF"]]}'
        return R()


class _FakeAnswerLLM:
    def invoke(self, prompt):
        class R:
            content = "답: 서태지와 아이들\n경로: 양현석 -[MEMBER_OF]-> 서태지와 아이들\n근거: (양현석, MEMBER_OF, 서태지와 아이들)"
        return R()


class _FakeJudgeLLM:
    def invoke(self, prompt):
        class R:
            content = "1.0"
        return R()


def _g():
    g = nx.MultiDiGraph()
    g.add_node("artist:양현석", name="양현석", type="Artist", norm="양현석")
    g.add_node("group:서태지와아이들", name="서태지와 아이들", type="Group", norm="서태지와아이들")
    g.add_edge("artist:양현석", "group:서태지와아이들", relation="MEMBER_OF", origins=["rule"], agreement=1.0)
    return g


ITEM = {
    # 질문에 개체명을 직접 넣는다 — find_seeds() 의 정확매칭으로 찾게
    # 하기 위해서다. 대명사만 쓰면 LLM 폴백까지 가는데, _FakeRouteLLM 은
    # route_question() 용 JSON만 흉내 내므로 find_seeds() 의
    # entities:[...] 형식과 맞지 않아 시드를 못 찾는다(실측). 실제
    # 골든셋 문항도 전부 개체명을 직접 쓴다 — 대명사 질문은 없다.
    "id": "Q_test", "question": "양현석은 어느 그룹 멤버인가?", "hops": 1,
    "route": "local", "split": "tuned", "answer_type": "single",
    "answer": "서태지와 아이들", "answer_aliases": [], "seed_hint": ["양현석"],
    "expected_paths": [[{"hop": 1, "rel": "MEMBER_OF", "dir": "out", "to_type": "Group"}]],
    "expected_triples": [["양현석", "MEMBER_OF", "서태지와 아이들"]],
    "evidence": [{"doc": "x.md", "quote": "..."}],
}


def test_evaluate_item_fills_all_layers(tmp_path):
    cfg = {"retrieval": {"radius": 2, "max_radius": 3, "hub_degree_threshold": 25,
                         "degree_penalty_exponent": 0.5, "per_relation": 10,
                         "per_node_out": 8, "max_triples": 200, "max_seeds": 3,
                         "quota_exempt_origins": ["rule"], "quota_exempt_relations": [],
                         "origin_base_score": {"rule": 1.0, "llm": 0.8, "llm+rule": 1.1,
                                               "tracklist": 1.0, "derived": 0.9}},
           "eval": {"judge_repeats": 1},
           "paths": {"output_dir": str(tmp_path)}}
    result = ev.evaluate_item(ITEM, g=_g(), cfg=cfg, route_llm=_FakeRouteLLM(),
                              answer_llm=_FakeAnswerLLM(), judge_llm=_FakeJudgeLLM())
    assert result["failure_layer"] == "ok"
    assert result["idx"]["exact"] == 1.0
    assert result["scores"] == [1.0]


def test_hop_summary_table_groups_by_hops():
    """rows 는 evaluate_item() 의 실제 반환 형태를 그대로 쓴다 — idx 는
       중첩 딕셔너리(idx["exact"])이지 평평한 idx_exact 키가 아니다."""
    rows = [{"hops": 1, "idx": {"exact": 1.0}, "triple_recall": 1.0,
             "path_prefix_recall": 1.0, "score": 1.0},
            {"hops": 2, "idx": {"exact": 0.0}, "triple_recall": 0.5,
             "path_prefix_recall": 0.5, "score": 0.0}]
    table = ev.hop_summary_table(rows)
    assert table[1]["n"] == 1 and table[2]["n"] == 1
    assert table[1]["avg_score"] == 1.0


def test_hop_summary_table_excludes_none_scores_from_average():
    """심판 실패(score=None)를 평균에 0으로 섞으면 API 장애가 모델
       성능으로 둔갑한다(설계서 6.3) — 평균에서 아예 제외해야 한다."""
    rows = [{"hops": 1, "idx": {"exact": 1.0}, "triple_recall": 1.0,
             "path_prefix_recall": 1.0, "score": 1.0},
            {"hops": 1, "idx": {"exact": 1.0}, "triple_recall": 1.0,
             "path_prefix_recall": 1.0, "score": None}]
    table = ev.hop_summary_table(rows)
    assert table[1]["avg_score"] == 1.0
