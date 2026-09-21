import normalize as nz


def test_clean_name_strips_paren_qualifier():
    assert nz.clean_name("빅뱅 (음악 그룹)") == "빅뱅"
    assert nz.clean_name("유영진 (작곡가)") == "유영진"


def test_clean_name_strips_particle_only_after_bracket():
    assert nz.clean_name("《붉은 노을》은") == "붉은 노을"


def test_clean_name_never_strips_particle_from_bare_name():
    """맨 이름에서 조사를 떼면 곡 제목이 파손된다."""
    assert nz.clean_name("거짓말이야") == "거짓말이야"
    assert nz.clean_name("내가") == "내가"
    assert nz.clean_name("너와 나의") == "너와 나의"


def test_norm_key_ignores_spacing_and_case():
    assert nz.norm_key("에스엠 엔터테인먼트") == nz.norm_key("에스엠엔터테인먼트")
    assert nz.norm_key("NewJeans") == nz.norm_key("newjeans")


def test_is_junk_rejects_stopwords_and_short_names():
    assert nz.is_junk("음악", "Genre")
    assert nz.is_junk("가", "Artist")
    assert not nz.is_junk("아이유", "Artist")


def test_is_junk_drops_bare_year_only_for_attribute_family():
    assert nz.is_junk("1992", "Genre")
    assert not nz.is_junk("1992", "Song"), "《1992》 같은 곡 제목을 지키기 위함"
