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


def test_config_has_origin_base_score_matching_join_convention():
    """build_stats.json 의 edges_by_origin 은 '+'.join(sorted(origins))로
       키를 만든다 — 알파벳 정렬이라 'llm+rule'이지 'rule+llm'이 아니다."""
    cfg = config_loader.load()
    scores = cfg["retrieval"]["origin_base_score"]
    assert scores["llm+rule"] == 1.1
    assert "rule+llm" not in scores


def test_config_has_genre_hop_exception_for_vector_route():
    cfg = config_loader.load()
    g = cfg["retrieval"]["genre_hop_in_vector_route"]
    assert g["allowed"] is True
    assert g["max_hops"] == 1


def test_config_has_eval_sweep_grid_matching_design_doc():
    cfg = config_loader.load()
    sweep = cfg["eval"]["sweep"]
    assert sweep["max_radius"] == [2, 3, 4]
    assert sweep["hub_degree_threshold"] == [15, 25, 40, None]
    assert sweep["per_relation"] == [5, 10, 20]
    assert sweep["max_triples"] == [100, 200, 400]


def test_config_has_frozen_holdout_fingerprint():
    """Task 21(P9)에서 실제로 동결한 뒤에는 이 슬롯이 채워져 있어야 한다 -
       빈 슬롯 존재만 확인하던 이전 버전은 동결 전 상태를 검증했다."""
    cfg = config_loader.load()
    h = cfg["eval"]["holdout"]
    assert h["frozen"] is True
    for k in ("frozen_at", "freeze_commit", "config_hash", "schema_version",
              "prompt_version", "goldenset_hash", "graph_hash"):
        assert h[k]


def test_validate_rejects_non_alphabetical_origin_key():
    cfg = config_loader.load()
    cfg["retrieval"]["origin_base_score"]["rule+llm"] = 1.1
    with pytest.raises(ValueError, match="알파벳 정렬"):
        config_loader.validate(cfg)
