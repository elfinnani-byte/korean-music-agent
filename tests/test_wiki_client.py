import pytest

import wiki_client


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    """첫 호출들은 429 를 내고 그 다음 200 을 내는 가짜 세션."""

    def __init__(self, fail_times: int, retry_after: str | None = None):
        self.fail_times = fail_times
        self.retry_after = retry_after
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            h = {"Retry-After": self.retry_after} if self.retry_after else {}
            return FakeResponse(429, headers=h)
        return FakeResponse(200, {"ok": True})


def test_retries_on_429_then_succeeds(monkeypatch):
    slept = []
    monkeypatch.setattr(wiki_client.time, "sleep", lambda s: slept.append(s))
    c = wiki_client.WikiClient(session=FakeSession(fail_times=2), delay_sec=0)
    assert c.api({"action": "query"}) == {"ok": True}
    assert len(slept) == 2
    assert slept[1] > slept[0], "지수 백오프이므로 대기가 길어져야 한다"


def test_respects_retry_after_header(monkeypatch):
    slept = []
    monkeypatch.setattr(wiki_client.time, "sleep", lambda s: slept.append(s))
    c = wiki_client.WikiClient(session=FakeSession(fail_times=1, retry_after="7"), delay_sec=0)
    c.api({"action": "query"})
    assert slept == [7.0]


def test_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(wiki_client.time, "sleep", lambda s: None)
    c = wiki_client.WikiClient(session=FakeSession(fail_times=99), delay_sec=0, max_attempts=3)
    with pytest.raises(wiki_client.RateLimited):
        c.api({"action": "query"})


def test_user_agent_is_ascii_only():
    c = wiki_client.WikiClient(session=FakeSession(0), delay_sec=0)
    c.user_agent.encode("ascii")  # 한글이 들어가면 여기서 터진다
