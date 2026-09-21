import json

import pytest

import config_loader


def test_config_loads():
    cfg = config_loader.load()
    assert cfg["domain"] == "한국 대중음악 1992~현재"


def test_config_does_not_duplicate_schema():
    """설계서 9.3 — schema.py 가 단일 진실 공급원이다.
       config 에 rel_triples 를 복사하면 언젠가 불일치한다."""
    raw = json.loads(open("config.json", encoding="utf-8").read())
    assert "rel_triples" not in raw.get("schema", {})


def test_config_has_no_api_keys():
    """실제 키 값(sk-..., AIza...)이 없어야 한다. env_keys 에 담기는
       'OPENAI_API_KEY' 같은 환경변수 *이름*은 비밀이 아니라 llm_factory 가
       .env 에서 실제 키를 찾을 때 쓰는 참조이므로 금지 대상이 아니다."""
    raw = open("config.json", encoding="utf-8").read()
    for forbidden in ("sk-", "AIza"):
        assert forbidden not in raw


def test_seed_titles_match_declared_count():
    cfg = config_loader.load()
    assert len(cfg["collect"]["seed_titles"]) == 19


def test_quota_eras_match_schema():
    import schema
    cfg = config_loader.load()
    assert cfg["scope"]["quota_eras"] == schema.QUOTA_ERAS


def test_validate_raises_when_bridge_relation_unknown():
    cfg = config_loader.load()
    cfg["retrieval"]["quota_exempt_relations"] = ["NOT_A_RELATION"]
    with pytest.raises(ValueError, match="NOT_A_RELATION"):
        config_loader.validate(cfg)
