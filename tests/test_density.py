import density_gate as dg


def test_cross_mentions_counts_other_doc_titles_in_body():
    docs = {
        "아이유": "아이유는 김광석의 노래를 리메이크했다.",
        "김광석": "김광석은 가수다.",
        "빅뱅": "빅뱅은 YG 엔터테인먼트 소속이다.",
        "YG 엔터테인먼트": "회사다.",
    }
    counts = dg.cross_mentions(docs)
    assert counts["아이유"] == 1
    assert counts["빅뱅"] == 1
    assert counts["김광석"] == 0


def test_cross_mentions_ignores_self_reference():
    docs = {"아이유": "아이유는 아이유다.", "빅뱅": "무관"}
    assert dg.cross_mentions(docs)["아이유"] == 0


def test_long_range_pairs_only_counts_distant_eras():
    docs = {"A": "B 를 언급", "B": "무관"}
    eras = {"A": "1990s", "B": "2010s"}
    assert dg.long_range_pairs(docs, eras) == 1

    eras_near = {"A": "1990s", "B": "2000s"}
    assert dg.long_range_pairs(docs, eras_near) == 0


def test_verdict_fails_when_any_criterion_missed():
    v = dg.verdict({"docs": 70, "per_era": {"1990s": 5}, "avg_cross": 4.0,
                    "multi_seed_ratio": 0.5, "long_range": 12},
                   {"min_docs": 70, "min_docs_per_era": 14,
                    "min_avg_cross_mentions": 3.0, "min_multi_seed_ratio": 0.4,
                    "min_long_range_pairs": 10})
    assert v["passed"] is False
    assert any("1990s" in r for r in v["reasons"])


def test_verdict_only_checks_quota_eras_not_out_of_scope_buckets():
    """per_era 에는 '1980s 이전'과 null(시상식·소속사처럼 데뷔 연도가 없는
       시드)도 섞여 나온다. 이 둘은 QUOTA_ERAS 가 아니므로 14건 기준을
       적용하면 안 된다 — 애초에 그만큼 모을 이유도 대상도 아니다."""
    v = dg.verdict({"docs": 70, "per_era": {"1990s": 14, "2000s": 14,
                                            "2010s": 14, "2020s": 14,
                                            "1980s 이전": 1, "null": 6},
                    "avg_cross": 4.0, "multi_seed_ratio": 0.5, "long_range": 12},
                   {"min_docs": 70, "min_docs_per_era": 14,
                    "min_avg_cross_mentions": 3.0, "min_multi_seed_ratio": 0.4,
                    "min_long_range_pairs": 10})
    assert v["passed"] is True, v["reasons"]
