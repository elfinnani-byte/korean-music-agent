import agent


def test_select_top_reports_picks_highest_keyword_overlap():
    reports = [{"title": "댄스 아이돌 계보", "summary": "2010년대 댄스 아이돌", "findings": []},
              {"title": "포크 인디", "summary": "1990년대 포크 록", "findings": []}]
    top = agent.select_top_reports("2010년대 댄스 아이돌 흐름을 알려줘", reports, k=1)
    assert top[0]["title"] == "댄스 아이돌 계보"


def test_reduce_reports_concatenates_summaries_as_context():
    reports = [{"title": "A", "summary": "s1", "findings": ["f1"]}]
    context = agent.reduce_reports(reports)
    assert "A" in context and "s1" in context and "f1" in context


def test_compiled_graph_app_runs_global_route_through_map_reduce(tmp_path):
    """build_graph_app() 이 n_global_map/n_global_reduce 없이 global 을
       바로 n_insufficient 로 보내던 것을 ask() 와 맞춰 고쳤다 — 두
       구현이 갈라지면 데모(app.py)가 ask() 로 확인한 것과 다르게
       동작한다."""
    import json
    import networkx as nx

    (tmp_path / "community_reports.json").write_text(
        json.dumps([{"title": "댄스 아이돌 계보", "summary": "2010년대 댄스 아이돌 흐름",
                    "findings": ["f1"]}], ensure_ascii=False),
        encoding="utf-8")

    class RouteLLM:
        def invoke(self, prompt):
            class R:
                content = '{"route": "global", "required_rels": []}'
            return R()

    class AnswerLLM:
        def invoke(self, prompt):
            class R:
                content = "답: 2010년대 댄스 아이돌이 주류였다\n경로: 전역\n근거: 커뮤니티 보고서"
            return R()

    cfg = {"retrieval": {"radius": 2, "max_radius": 3, "hub_degree_threshold": 25,
                         "degree_penalty_exponent": 0.5, "per_relation": 10,
                         "per_node_out": 8, "max_triples": 200, "max_seeds": 3,
                         "quota_exempt_origins": ["rule"], "quota_exempt_relations": [],
                         "origin_base_score": {"rule": 1.0, "llm": 0.8, "llm+rule": 1.1,
                                               "tracklist": 1.0, "derived": 0.9}},
           "paths": {"output_dir": str(tmp_path)}}
    sg = agent.build_graph_app(g=nx.MultiDiGraph(), cfg=cfg, route_llm=RouteLLM(), answer_llm=AnswerLLM())
    compiled = sg.compile()
    result = compiled.invoke(agent.initial_state("2010년대 댄스 아이돌 흐름을 알려줘"))
    assert result["route"] == "global"
    assert result["decision"] == "answer"
    assert result["reports"][0]["title"] == "댄스 아이돌 계보"
