import evaluate as ev


class _FakeJudge:
    def __init__(self, score_text):
        self.score_text = score_text

    def invoke(self, prompt):
        class R:
            content = self.score_text
        return R()


def test_judge_score_parses_numeric_response():
    assert ev.judge_score("q", "a", "gold", "evidence", _FakeJudge("1.0")) == 1.0
    assert ev.judge_score("q", "a", "gold", "evidence", _FakeJudge("점수는 0.5 입니다")) == 0.5


def test_judge_score_returns_none_on_unparsable_response():
    """심판 실패는 0 이 아니라 None 으로 기록한다. 0 으로 넣으면 API 장애가
       모델 성능으로 둔갑한다."""
    assert ev.judge_score("q", "a", "gold", "evidence", _FakeJudge("모르겠습니다")) is None


def test_classify_failure_stops_at_first_matching_layer():
    item = {"route": "local"}
    assert ev.classify_failure(item, route_actual="path", idx={"exact": 1.0},
                               ret={"seeds": ["x"], "triple_recall": 1.0},
                               gen={"decision": "answer", "score": 1.0}) == "routing"


def test_classify_failure_detects_abstain_layer_separately_from_generation():
    """근거는 완전한데(idx.exact==1) 기권했다면 generation 이 아니라
       abstain(과기권)이다 — 환각 방지 장치가 만든 결과이지 답변 품질
       문제가 아니다."""
    item = {"route": "local"}
    result = ev.classify_failure(item, route_actual="local", idx={"exact": 1.0},
                                 ret={"seeds": ["x"], "triple_recall": 1.0},
                                 gen={"decision": "abstain", "score": 0.0})
    assert result == "abstain"


def test_classify_failure_returns_ok_when_everything_passes():
    item = {"route": "local"}
    result = ev.classify_failure(item, route_actual="local", idx={"exact": 1.0},
                                 ret={"seeds": ["x"], "triple_recall": 1.0},
                                 gen={"decision": "answer", "score": 1.0})
    assert result == "ok"
