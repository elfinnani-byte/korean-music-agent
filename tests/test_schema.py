import schema


def test_node_types_are_nine_with_two_families():
    assert len(schema.NODE_TYPES) == 9
    assert set(schema.NODE_TYPES.values()) == {"entity", "attribute"}
    assert schema.NODE_TYPES["Genre"] == "attribute"
    assert schema.NODE_TYPES["Era"] == "attribute"


def test_relation_names_are_eighteen_and_tuples_are_forty():
    names = {r for _, r, _ in schema.REL_TRIPLES}
    assert len(names) == 18, sorted(names)
    assert len(schema.REL_TRIPLES) == 40


def test_every_tuple_endpoint_is_a_declared_node_type():
    """LLMGraphTransformer 는 튜플의 첫·마지막 원소가 allowed_nodes 에
       없으면 거부한다. 선언 단계에서 막는다."""
    for h, r, t in schema.REL_TRIPLES:
        assert h in schema.NODE_TYPES, f"{h} in ({h},{r},{t})"
        assert t in schema.NODE_TYPES, f"{h} in ({h},{r},{t})"


def test_bridge_relations_are_five_and_exclude_collaboration():
    assert set(schema.BRIDGE_RELATIONS) == {
        "INFLUENCED", "COVERED", "PRODUCED", "WROTE", "FOUNDED"
    }
    assert "COLLABORATED_WITH" not in schema.BRIDGE_RELATIONS


def test_collaboration_has_all_four_type_combinations():
    """대칭 정준화가 (Group, ..., Artist) 를 만들 수 있으므로
       네 조합이 모두 선언돼 있어야 strict_mode 에서 거부되지 않는다."""
    combos = {(h, t) for h, r, t in schema.REL_TRIPLES if r == "COLLABORATED_WITH"}
    assert combos == {("Artist", "Artist"), ("Artist", "Group"),
                      ("Group", "Artist"), ("Group", "Group")}


def test_formed_in_is_separate_from_debuted_in():
    rels = {r for _, r, _ in schema.REL_TRIPLES}
    assert "FORMED_IN" in rels and "DEBUTED_IN" in rels


def test_never_merge_pairs_block_same_family_collisions():
    assert frozenset({"Artist", "Group"}) in schema.NEVER_MERGE_PAIRS
    assert frozenset({"Album", "Song"}) in schema.NEVER_MERGE_PAIRS
