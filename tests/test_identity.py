import normalize as nz


def test_type_vote_gives_rules_weight_five():
    """분류 기반 규칙 투표가 LLM 투표를 압도해야 그룹·인물 혼동을 막는다."""
    assert nz.vote_type(llm_votes={"Artist": 4}, rule_votes={"Group": 1}) == "Group"


def test_type_vote_prefers_entity_on_tie():
    assert nz.vote_type(llm_votes={"Genre": 1, "Song": 1}, rule_votes={}) == "Song"


def test_node_id_includes_context_for_song():
    a = nz.node_id("Butter", "Song", context="방탄소년단")
    b = nz.node_id("Butter", "Song", context="다른가수")
    assert a != b, "제목만으로 합치면 없는 리메이크가 생긴다"


def test_node_id_without_context_is_stable():
    assert nz.node_id("Butter", "Song", context=None) == nz.node_id("Butter", "Song", None)


def test_entity_nodes_merge_by_name_only():
    """Artist·Group·Label 은 맥락 없이 이름으로 합친다."""
    assert nz.node_id("아이유", "Artist", context="a") == nz.node_id("아이유", "Artist", "b")


def test_can_merge_songs_requires_shared_evidence():
    x = {"performers": {"방탄소년단"}, "albums": set(), "quotes": {"q1"}}
    y = {"performers": {"방탄소년단"}, "albums": set(), "quotes": set()}
    z = {"performers": {"다른가수"}, "albums": set(), "quotes": {"q2"}}
    assert nz.can_merge_songs(x, y)
    assert not nz.can_merge_songs(x, z)


def test_canonical_symmetric_orders_by_type_then_name():
    a = nz.canonical_symmetric(("나가수", "Artist"), ("가그룹", "Group"))
    b = nz.canonical_symmetric(("가그룹", "Group"), ("나가수", "Artist"))
    assert a == b, "정준화는 입력 순서와 무관해야 한다"
    assert a[0][1] == "Artist", "타입 순서를 먼저 본다"
