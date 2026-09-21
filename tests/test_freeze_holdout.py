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
    frozen = {"config_hash": fh._sha256_file(p), "goldenset_hash": "x",
             "graph_hash": "x", "schema_version": "x", "prompt_version": "x"}
    p.write_text('{"changed": true}', encoding="utf-8")
    ok, problems = fh.verify_fingerprint(frozen, config_path=p,
                                         goldenset_path=p, graph_path=p)
    assert ok is False
    assert any("config" in prob for prob in problems)
