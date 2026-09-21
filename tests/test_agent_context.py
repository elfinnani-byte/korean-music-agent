import agent


def test_build_context_groups_triples_by_relation():
    triples = [{"h": "양현석", "r": "MEMBER_OF", "t": "서태지와 아이들"},
               {"h": "양현석", "r": "FOUNDED", "t": "YG 엔터테인먼트"}]
    context, sources = agent.build_context(triples)
    assert "MEMBER_OF" in context and "FOUNDED" in context
    assert "양현석" in context and "YG 엔터테인먼트" in context


def test_insufficient_answer_names_missing_relations_without_calling_llm():
    answer = agent.insufficient_answer(gap_rels=["WON"])
    assert "근거가 부족합니다" in answer
    assert "WON" in answer
