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


def test_extract_text_passes_through_plain_string():
    class R:
        content = "1.0"
    assert llm_factory.extract_text(R()) == "1.0"


def test_extract_text_joins_google_content_block_list():
    """실측 버그: gemini-3.8-flash 는 content 를 평범한 문자열이 아니라
       [{'type':'text','text':'1.0','extras':{...}}] 형태의 블록 리스트로
       돌려줄 때가 있다. OpenAI 는 평범한 문자열이라 이 차이를 몰랐다가
       실제 P8 평가 실행에서 TypeError 로 처음 드러났다."""
    class R:
        content = [{"type": "text", "text": "1.0", "extras": {"signature": "..."}}]
    assert llm_factory.extract_text(R()) == "1.0"


def test_extract_text_joins_multiple_blocks_with_newline():
    class R:
        content = [{"type": "text", "text": "첫 줄"}, {"type": "text", "text": "둘째 줄"}]
    assert llm_factory.extract_text(R()) == "첫 줄\n둘째 줄"


def test_extract_text_skips_non_text_blocks():
    class R:
        content = [{"type": "text", "text": "본문"}, {"type": "thinking", "thinking": "숨은 추론"}]
    assert llm_factory.extract_text(R()) == "본문"
