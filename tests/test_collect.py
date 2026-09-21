import collect_docs as cd


def test_music_doc_accepts_music_category():
    assert cd.is_music_doc("아이유", ["대한민국의 여자 가수", "2008년 데뷔"])


def test_music_doc_rejects_blacklisted_category():
    assert not cd.is_music_doc("아무개", ["서울대학교 동문", "생존 인물"])


def test_music_doc_rejects_non_music():
    assert not cd.is_music_doc("어떤 영화", ["2019년 영화", "대한민국의 영화"])


def test_era_from_categories_reads_debut_year():
    assert cd.era_from_categories(["2008년 데뷔", "대한민국의 가수"]) == "2000s"


def test_era_from_categories_falls_back_to_formation():
    assert cd.era_from_categories(["1991년 결성된 음악 그룹"]) == "1990s"


def test_era_from_categories_returns_none_when_unknown():
    assert cd.era_from_categories(["대한민국의 가수"]) is None


def test_rank_candidates_prefers_multi_seed_targets():
    links = {"시드A": ["X", "Y"], "시드B": ["Y", "Z"], "시드C": ["Y"]}
    ranked = cd.rank_candidates(links)
    assert ranked[0][0] == "Y"
    assert ranked[0][1] == 3


def test_quota_fills_each_era_before_overflow():
    cands = [("a", "2020s"), ("b", "2020s"), ("c", "2020s"), ("d", "1990s")]
    picked = cd.apply_era_quota(cands, per_era_min=1, target=3)
    assert "d" in picked, "쿼터가 없으면 문서가 많은 최근 연대로 쏠린다"
