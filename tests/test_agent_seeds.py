import networkx as nx
import agent


def _g():
    g = nx.MultiDiGraph()
    g.add_node("group:빅뱅", name="빅뱅", type="Group", norm="빅뱅")
    g.add_node("artist:지드래곤", name="지드래곤", type="Artist", norm="지드래곤")
    g.add_node("label:yg엔터테인먼트", name="YG 엔터테인먼트", type="Label", norm="yg엔터테인먼트")
    return g


def test_exact_match_prefers_longer_name_to_avoid_substring_false_positive():
    g = _g()
    seeds = agent.find_seeds(g, "지드래곤이 소속된 그룹이 수상한 시상식은?", cfg={"retrieval": {"max_seeds": 3}})
    assert "artist:지드래곤" in seeds


def test_partial_match_uses_normalized_substring():
    g = _g()
    seeds = agent.find_seeds(g, "YG엔터테인먼트는 어떤 회사인가?", cfg={"retrieval": {"max_seeds": 3}})
    assert "label:yg엔터테인먼트" in seeds


def test_llm_fallback_returns_empty_when_extracted_entity_not_in_graph():
    """LLM 이 개체명을 뽑아도 그래프에 그 이름이 없으면(오추출·범위 밖
       인물) 빈 리스트를 낸다 — 없는 이름을 억지로 시드에 넣지 않는다."""
    g = _g()

    class FakeLLM:
        def invoke(self, prompt):
            class R:
                content = '{"entities": ["존재하지않는사람"]}'
            return R()

    seeds = agent.find_seeds(g, "그 사람은 언제 데뷔했나요?", cfg={"retrieval": {"max_seeds": 3}}, llm=FakeLLM())
    assert seeds == []


def test_llm_fallback_resolves_extracted_entity_against_graph():
    g = _g()

    class FakeLLM:
        def invoke(self, prompt):
            class R:
                content = '{"entities": ["빅뱅"]}'
            return R()

    seeds = agent.find_seeds(g, "그 그룹 빅뱅은 언제 데뷔했나요?", cfg={"retrieval": {"max_seeds": 3}}, llm=FakeLLM())
    assert seeds == ["group:빅뱅"]
