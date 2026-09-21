import goldenset_check as gc

ITEM = {
    "id": "Q05", "question": "...", "hops": 2, "era_cross": False,
    "route": "path", "split": "tuned", "era_span": ["1990s"],
    "answer_type": "single", "answer": "YG 엔터테인먼트",
    "answer_aliases": ["YG"], "expected_behavior": "answer",
    "seed_hint": ["서태지와 아이들"],
    "expected_paths": [[
        {"hop": 1, "rel": "MEMBER_OF", "dir": "in", "to_type": "Artist"},
        {"hop": 2, "rel": "FOUNDED", "dir": "out", "to_type": "Label"},
    ]],
    "expected_triples": [["양현석", "MEMBER_OF", "서태지와 아이들"],
                         ["양현석", "FOUNDED", "YG 엔터테인먼트"]],
    "evidence": [{"doc": "서태지와 아이들.md", "quote": "..."}],
}


def test_valid_item_passes():
    assert gc.check_item(ITEM) == []


def test_hops_must_equal_shortest_path_length():
    bad = {**ITEM, "hops": 3}
    errs = gc.check_item(bad)
    assert any("hops" in e for e in errs)


def test_none_type_must_have_null_answer_and_reason():
    bad = {**ITEM, "id": "Q23", "answer_type": "none", "hops": None,
           "expected_paths": [], "expected_triples": [], "evidence": [],
           "expected_behavior": "abstain"}
    errs = gc.check_item(bad)
    assert any("abstain_reason" in e for e in errs)

    ok = {**bad, "answer": None, "abstain_reason": "no_supported_path"}
    assert gc.check_item(ok) == []


def test_path_must_be_realizable_in_schema():
    """(Label, FOUNDED, Song) 는 스키마에 없다. 여기서 막아야
       나중에 낮은 점수가 시스템 탓인지 문항 탓인지 가릴 수 있다."""
    bad = {**ITEM, "expected_paths": [[
        {"hop": 1, "rel": "FOUNDED", "dir": "out", "to_type": "Song"}
    ]], "hops": 1}
    errs = gc.check_item(bad)
    assert any("스키마" in e for e in errs)


def test_set_type_requires_partial_credit():
    bad = {**ITEM, "answer_type": "set", "answer_set": ["a", "b"]}
    errs = gc.check_item(bad)
    assert any("partial_credit" in e for e in errs)


def test_collection_counts_are_enforced():
    items = [{**ITEM, "id": f"Q{i:02d}"} for i in range(1, 25)]
    errs = gc.check_collection(items)
    assert any("25" in e for e in errs)


def test_duplicate_ids_are_caught():
    items = [{**ITEM, "id": "Q01"}, {**ITEM, "id": "Q01"}]
    errs = gc.check_collection(items)
    assert any("중복" in e for e in errs)
