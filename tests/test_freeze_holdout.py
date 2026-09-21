import json

import freeze_holdout as fh


def test_fingerprint_computes_all_seven_fields(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "goldenset.json").write_text("[]", encoding="utf-8")
    (tmp_path / "graph.json").write_text("{}", encoding="utf-8")
    fp = fh.compute_fingerprint(config_path=tmp_path / "config.json",
                                goldenset_path=tmp_path / "goldenset.json",
                                graph_path=tmp_path / "graph.json",
                                commit_hash="abc123")
    for k in ("config_hash", "goldenset_hash", "graph_hash", "schema_version",
              "prompt_version", "freeze_commit", "frozen_at"):
        assert fp[k]


def test_verify_fingerprint_rejects_mismatch(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{}", encoding="utf-8")
    frozen = {"config_hash": fh._config_hash(p), "goldenset_hash": "x",
             "graph_hash": "x", "schema_version": "x", "prompt_version": "x"}
    p.write_text('{"changed": true}', encoding="utf-8")
    ok, problems = fh.verify_fingerprint(frozen, config_path=p,
                                         goldenset_path=p, graph_path=p)
    assert ok is False
    assert any("config" in prob for prob in problems)


def test_verify_fingerprint_accepts_after_fingerprint_embedded_into_same_config(tmp_path):
    """실측 버그: config_hash 를 config.json 전체 바이트로 잡으면, 그 지문을
       실제 운용 절차대로 config.json 자신의 eval.holdout 필드에 써넣는
       순간 파일 내용이 바뀌어 스스로도 검증을 통과하지 못하는 자기참조
       모순이 생긴다(실측: 동결 직후 verify_fingerprint 가 config_hash
       불일치로 항상 실패했다). eval.holdout 필드는 해시 계산에서
       제외해야 한다."""
    config_path = tmp_path / "config.json"
    goldenset_path = tmp_path / "goldenset.json"
    graph_path = tmp_path / "graph.json"
    config_path.write_text(json.dumps({"a": 1, "eval": {"holdout": {}}}), encoding="utf-8")
    goldenset_path.write_text("[]", encoding="utf-8")
    graph_path.write_text("{}", encoding="utf-8")

    fp = fh.compute_fingerprint(config_path, goldenset_path, graph_path, commit_hash="abc")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["eval"]["holdout"] = fp
    config_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    ok, problems = fh.verify_fingerprint(fp, config_path, goldenset_path, graph_path)
    assert ok is True, problems
