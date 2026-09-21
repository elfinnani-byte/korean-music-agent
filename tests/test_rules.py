import rules


def _find(triples, rel):
    return [t for t in triples if t["r"] == rel]


def test_r07_matches_real_award_category_format():
    """실측한 실제 분류는 '수상 음악가'로 끝난다.
       '수상'으로 끝나는 패턴은 한 건도 잡지 못한다."""
    out = rules.apply("서태지와 아이들", ["골든디스크 본상 수상 음악가"])
    won = _find(out, "WON")
    assert len(won) == 1
    assert won[0]["h"] == "서태지와 아이들"
    assert won[0]["t"] == "골든디스크"
    assert won[0]["props"]["award_category"] == "본상"


def test_r07_requires_award_lexicon():
    out = rules.apply("아무개", ["올해의 인물상 수상 음악가"])
    assert _find(out, "WON") == []


def test_r08_reverses_direction():
    """'아이유의 음반' 분류가 붙은 문서는 앨범이고, 캡처값이 head 다."""
    out = rules.apply("Palette", ["아이유의 음반"])
    rel = _find(out, "RELEASED")[0]
    assert rel["h"] == "아이유" and rel["t"] == "Palette"


def test_r09_reverses_direction():
    out = rules.apply("좋은 날", ["아이유의 노래"])
    rel = _find(out, "PERFORMED")[0]
    assert rel["h"] == "아이유" and rel["t"] == "좋은 날"


def test_r04_produces_formed_in_not_debuted_in():
    out = rules.apply("서태지와 아이들", ["1991년 결성된 음악 그룹"])
    assert _find(out, "FORMED_IN")
    assert _find(out, "DEBUTED_IN") == []


def test_r03_produces_debuted_in_with_year_prop():
    out = rules.apply("아이유", ["2008년 데뷔"])
    rel = _find(out, "DEBUTED_IN")[0]
    assert rel["t"] == "2000s" and rel["props"]["year"] == 2008


def test_r01_requires_genre_lexicon():
    ok = rules.apply("신승훈", ["대한민국의 발라드 가수"])
    assert _find(ok, "HAS_GENRE")[0]["t"] == "발라드"
    bad = rules.apply("아무개", ["대한민국의 여자 가수"])
    assert _find(bad, "HAS_GENRE") == []


def test_r07_recognizes_mnet_award_category_english_prefix():
    """실측 버그: 코퍼스의 실제 분류는 'Mnet 아시안 뮤직 어워드
       올해의 가수상 수상 음악가'(영문 'Mnet' 접두)인데
       AWARD_CANON 은 '엠넷 아시안 뮤직 어워드'만 등록돼 있어
       52건 코퍼스에서 이 시상식 WON 이 0건이었다."""
    out = rules.apply("빅뱅", ["Mnet 아시안 뮤직 어워드 올해의 가수상 수상 음악가"])
    won = _find(out, "WON")
    assert len(won) == 1
    assert won[0]["t"] == "엠넷 아시안 뮤직 어워드"
    assert won[0]["props"]["award_category"] == "올해의 가수상"


def test_r02_requires_label_lexicon():
    ok = rules.apply("보아", ["SM 엔터테인먼트 소속"])
    assert _find(ok, "SIGNED_TO")[0]["t"] == "SM 엔터테인먼트"
    bad = rules.apply("아무개", ["무슨무슨 소속"])
    assert _find(bad, "SIGNED_TO") == []


def test_blacklisted_categories_produce_nothing():
    out = rules.apply("아무개", ["서울대학교 동문", "생존 인물", "1990년 출생"])
    assert out == []


def test_no_rule_produces_signed_to_from_album_category():
    """초안의 R11 은 '지구레코드의 음반'을 SIGNED_TO 로 만들어
       타입이 맞지 않았다. 제거됐는지 확인한다."""
    out = rules.apply("어떤음반", ["SM 엔터테인먼트의 음반"])
    assert _find(out, "SIGNED_TO") == []
