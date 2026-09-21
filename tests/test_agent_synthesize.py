import agent


class _FakeAnswerLLM:
    def __init__(self, text):
        self.text = text
        self.last_prompt = None

    def invoke(self, prompt):
        self.last_prompt = prompt

        class R:
            content = self.text
        return R()


def test_synthesize_includes_context_and_guard_rules_in_prompt():
    llm = _FakeAnswerLLM("답: YG 엔터테인먼트\n경로: 양현석 -[FOUNDED]-> YG 엔터테인먼트\n근거: (양현석, FOUNDED, YG 엔터테인먼트)")
    answer, decision, called = agent.synthesize("누가 YG를 세웠나?", "[FOUNDED]\n  (양현석, FOUNDED, YG 엔터테인먼트)",
                                                ["양현석", "YG 엔터테인먼트"], llm)
    assert "개체명만" in llm.last_prompt
    assert decision == "answer"
    assert called is True


def test_synthesize_detects_abstain_phrase_as_abstain_decision():
    llm = _FakeAnswerLLM("근거가 부족합니다")
    answer, decision, called = agent.synthesize("질문", "[MEMBER_OF]\n  (a, MEMBER_OF, b)", ["a", "b"], llm)
    assert decision == "abstain"
    assert called is True  # LLM 을 불렀다는 사실 자체는 기록해야 한다(코드층 기권과 구분)
