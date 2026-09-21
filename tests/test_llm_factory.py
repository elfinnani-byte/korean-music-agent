import pytest

import llm_factory


def test_missing_key_raises_korean_message(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm_factory.get_llm("extract", {"llm": {
            "profiles": {"extract": {"provider": "openai", "model": "x", "temperature": 0}},
            "env_keys": {"openai": "OPENAI_API_KEY"},
        }})


def test_status_reports_configured_when_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    cfg = {"llm": {"env_keys": {"openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}}}
    st = llm_factory.provider_status(cfg, ping=False)
    assert st["openai"] == "configured"
    assert st["google"] == "absent"
