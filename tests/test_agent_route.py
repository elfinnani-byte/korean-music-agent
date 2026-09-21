import agent


def test_rule_pass_maps_single_cue_to_local():
    route, by, rels = agent.route_by_rule("이 그룹의 멤버는 누구인가?")
    assert route == "local" and by == "rule"
    assert rels == [["MEMBER_OF"]]


def test_rule_pass_maps_multiple_cues_to_path():
    route, by, rels = agent.route_by_rule("이 사람이 설립한 회사에 소속된 그룹의 멤버는?")
    assert route == "path"
    assert ["FOUNDED"] in rels and ["SIGNED_TO"] in rels and ["MEMBER_OF"] in rels


def test_rule_pass_maps_covered_cue_to_or_group():
    route, by, rels = agent.route_by_rule("이 곡을 리메이크한 사람은?")
    assert rels == [["COVERED", "PERFORMED"]]


def test_rule_pass_maps_global_hint():
    route, by, rels = agent.route_by_rule("한국 대중음악의 전체적인 흐름은?")
    assert route == "global"


def test_rule_pass_demotes_vector_hint_to_path():
    """벡터 인덱스가 없으므로 서술형 질의는 path 로 강등한다. required_rels
       는 비워 둔다 — 어떤 관계를 요구하는지 알 수 없기 때문이다."""
    route, by, rels = agent.route_by_rule("이 그룹 음악의 분위기를 설명해줘")
    assert route == "path" and rels == []


def test_rule_pass_returns_none_when_nothing_matches():
    assert agent.route_by_rule("오늘 서울의 날씨는 어떤가요?") == (None, None, None)


def test_rule_pass_disambiguates_sosok_as_member_of_when_followed_by_group():
    """실측 버그: '소속'은 중의적이다 — '~에 소속된 그룹은'(사람->그룹,
       MEMBER_OF)과 'OO 기획사에 소속된 [그룹이름]'(그룹->회사,
       SIGNED_TO)이 똑같이 '소속'을 쓴다. 골든셋 Q10('지드래곤이
       소속된 그룹이...')이 SIGNED_TO로만 잘못 매핑돼 MEMBER_OF 간선이
       우선순위에서 밀려 사라졌다. '소속된 그룹'이 바로 붙어 있을
       때만 MEMBER_OF 이고, 그 사이에 회사·그룹 이름이 끼면(예:
       '기획사에 소속된 Stray Kids') SIGNED_TO 다."""
    route, by, rels = agent.route_by_rule("지드래곤이 소속된 그룹이 수상한 시상식 두 곳은?")
    flat = [r for group in rels for r in group]
    assert "MEMBER_OF" in flat
    assert "SIGNED_TO" not in flat


def test_rule_pass_keeps_signed_to_when_group_name_intervenes():
    route, by, rels = agent.route_by_rule("박진영이 설립한 기획사에 소속된 Stray Kids의 데뷔 타이틀곡은?")
    flat = [r for group in rels for r in group]
    assert "SIGNED_TO" in flat
    assert "MEMBER_OF" not in flat


def test_route_question_uses_rule_pass_first_without_calling_llm():
    called = {"n": 0}

    class FakeLLM:
        def invoke(self, prompt):
            called["n"] += 1
            raise AssertionError("규칙이 판정했으면 LLM 을 부르면 안 된다")

    state = agent.route_question("이 그룹의 멤버는 누구인가?", cfg={}, llm=FakeLLM())
    assert state["route"] == "local" and state["route_by"] == "rule"
    assert called["n"] == 0


def test_route_question_falls_back_to_llm_when_rule_uncertain():
    class FakeLLM:
        def invoke(self, prompt):
            class R:
                content = '{"route": "reject", "required_rels": []}'
            return R()

    state = agent.route_question("오늘 서울의 날씨는 어떤가요?", cfg={}, llm=FakeLLM())
    assert state["route"] == "reject" and state["route_by"] == "llm"
