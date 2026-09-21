import json
import networkx as nx
import agent


class _FakeRouteLLM:
    def invoke(self, prompt):
        class R:
            content = '{"route": "reject", "required_rels": []}'
        return R()


class _FakeAnswerLLM:
    def invoke(self, prompt):
        class R:
            content = "답: 서태지와 아이들\n경로: 양현석 -[MEMBER_OF, in]-> 서태지와 아이들\n근거: (양현석, MEMBER_OF, 서태지와 아이들)"
        return R()


def _g():
    g = nx.MultiDiGraph()
    g.add_node("artist:양현석", name="양현석", type="Artist", norm="양현석")
    g.add_node("group:서태지와아이들", name="서태지와 아이들", type="Group", norm="서태지와아이들")
    g.add_edge("artist:양현석", "group:서태지와아이들", relation="MEMBER_OF", origins=["rule"], agreement=1.0)
    return g


def _base_cfg(tmp_path):
    return {"retrieval": {"radius": 2, "max_radius": 3, "hub_degree_threshold": 25,
                          "degree_penalty_exponent": 0.5, "per_relation": 10,
                          "per_node_out": 8, "max_triples": 200, "max_seeds": 3,
                          "quota_exempt_origins": ["rule"], "quota_exempt_relations": [],
                          "origin_base_score": {"rule": 1.0, "llm": 0.8, "llm+rule": 1.1,
                                                "tracklist": 1.0, "derived": 0.9}},
           "paths": {"output_dir": str(tmp_path)}}


def test_reject_route_never_calls_answer_llm(tmp_path):
    called = {"n": 0}

    class Boom:
        def invoke(self, prompt):
            called["n"] += 1
            raise AssertionError("reject 인데 답변 LLM 을 불렀다")

    result = agent.ask("오늘 서울 날씨는?", g=_g(), cfg=_base_cfg(tmp_path),
                       route_llm=_FakeRouteLLM(), answer_llm=Boom())
    assert result["decision"] == "abstain"
    assert result["llm_answer_called"] is False
    assert called["n"] == 0


def test_local_route_writes_json_serializable_run_log(tmp_path):
    class RouteLLM:
        def invoke(self, prompt):
            raise AssertionError("규칙이 판정 가능한 질문이라 LLM 을 부르면 안 된다")

    result = agent.ask("서태지와 아이들의 멤버는 누구인가?", g=_g(), cfg=_base_cfg(tmp_path),
                       route_llm=RouteLLM(), answer_llm=_FakeAnswerLLM())
    assert result["route"] == "local"
    assert result["decision"] == "answer"

    log_path = tmp_path / "runs.jsonl"
    assert log_path.exists()
    line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    json.loads(line)  # 직렬화 실패하면 예외


def test_compiled_graph_app_runs_end_to_end_without_extra_arg_type_error(tmp_path):
    """LangGraph 는 컴파일된 노드를 항상 node(state) 한 인자로만 부른다.
       g·cfg·llm 을 노드 시그니처에 얹으면 컴파일은 되지만 invoke() 에서
       TypeError 가 난다 — 컴파일 성공과 실행 가능은 다른 것이다."""
    class RouteLLM:
        def invoke(self, prompt):
            raise AssertionError("규칙이 판정 가능한 질문이라 LLM 을 부르면 안 된다")

    sg = agent.build_graph_app(g=_g(), cfg=_base_cfg(tmp_path),
                               route_llm=RouteLLM(), answer_llm=_FakeAnswerLLM())
    compiled = sg.compile()
    result = compiled.invoke(agent.initial_state("서태지와 아이들의 멤버는 누구인가?"))
    assert result["route"] == "local"
    assert result["decision"] == "answer"
