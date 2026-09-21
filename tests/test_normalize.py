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


def test_is_junk_rejects_era_names_outside_closed_vocabulary():
    """실측 버그: 프롬프트로 정확한 연대 코드를 지시해도 LLM이 가끔
       서술절이나 '가요톱10_1990S' 같은 합성 문자열을 Era 타입으로
       내놓는다. Era 는 schema.ERAS 다섯 값만 허용한다.

       대소문자는 가린다 — LLM이 '1990S'(대문자 S)로 쓰는 경우가
       실제로 더 흔했고, node_id()의 norm_key()가 이미 소문자로
       합치므로 여기서 대소문자로 거부하면 오히려 정상 값까지
       통째로 드롭된다(실측: DEBUTED_IN 82건 -> 0건)."""
    assert not nz.is_junk("2010s", "Era")
    assert not nz.is_junk("2010S", "Era"), "LLM이 대문자 S로 쓴 정상 값까지 거부하면 안 된다"
    assert not nz.is_junk("1980s 이전", "Era")
    assert nz.is_junk("가요톱10_1990S", "Era")
    assert nz.is_junk("21세기 데뷔한 가수 중 최초의 기록", "Era")
