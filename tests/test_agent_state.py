import agent


def test_relation_gap_returns_or_groups_with_no_match():
    """required_rels 는 OR 그룹의 리스트다. 그룹 안 하나라도 확보되면
       그 그룹은 공백이 아니다."""
    state = {
        "required_rels": [["MEMBER_OF"], ["COVERED", "PERFORMED"]],
        "triples": [{"h": "a", "r": "MEMBER_OF", "t": "b"},
                    {"h": "c", "r": "PERFORMED", "t": "d"}],
    }
    assert agent.relation_gap(state) == []


def test_relation_gap_reports_unmet_or_group():
    state = {
        "required_rels": [["MEMBER_OF"], ["WON"]],
        "triples": [{"h": "a", "r": "MEMBER_OF", "t": "b"}],
    }
    assert agent.relation_gap(state) == [["WON"]]


def test_relation_gap_empty_required_is_never_a_gap():
    """required_rels 가 비어 있으면(예: reject 경로) 공백도 없다."""
    assert agent.relation_gap({"required_rels": [], "triples": []}) == []


def test_initial_state_is_json_serializable():
    """visited 는 set 이 아니라 list 여야 한다 — LangGraph 체크포인트와
       runs.jsonl 기록에서 둘 다 깨진다."""
    import json
    state = agent.initial_state("아무 질문")
    json.dumps(state, ensure_ascii=False)
    assert isinstance(state["visited"], list)
    assert isinstance(state["frontier"], list)
