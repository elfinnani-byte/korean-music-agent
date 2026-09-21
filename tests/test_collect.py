from pathlib import Path

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


def test_era_from_categories_reads_decade_category_for_solo_artists():
    """솔로 아티스트는 'YYYY년 데뷔' 대신 'YYYY년대 가수'를 갖는 경우가
       많다. 아이유·보아·신승훈 실제 카테고리로 확인한 문제다."""
    assert cd.era_from_categories(["1990년대 가수", "대한민국의 남자 가수"]) == "1990s"


def test_era_from_categories_picks_earliest_decade_when_career_spans_many():
    """신승훈처럼 1990s+2000s+2010s 가 모두 붙은 경우 데뷔에 가까운
       가장 이른 연대를 골라야 한다. 최근 연대를 고르면 활동 시작이
       사라져 세대 앵커 역할을 못 한다."""
    cats = ["2010년대 가수", "1990년대 가수", "2000년대 가수"]
    assert cd.era_from_categories(cats) == "1990s"


def test_era_from_categories_prefers_exact_debut_over_decade_category():
    cats = ["2008년 데뷔", "2000년대 가수", "2010년대 가수"]
    assert cd.era_from_categories(cats) == "2000s"


def test_rank_candidates_prefers_multi_seed_targets():
    links = {"시드A": ["X", "Y"], "시드B": ["Y", "Z"], "시드C": ["Y"]}
    ranked = cd.rank_candidates(links)
    assert ranked[0][0] == "Y"
    assert ranked[0][1] == 3


def test_quota_fills_each_era_before_overflow():
    cands = [("a", "2020s"), ("b", "2020s"), ("c", "2020s"), ("d", "1990s")]
    picked = cd.apply_era_quota(cands, per_era_min=1, target=3)
    assert "d" in picked, "쿼터가 없으면 문서가 많은 최근 연대로 쏠린다"


def test_quota_tops_up_from_existing_counts_instead_of_from_zero():
    """시드 문서가 이미 어떤 연대를 채웠다면, 그 연대에서 또 per_era_min 만큼
       새로 뽑을 필요가 없다. 남는 자리는 아직 못 채운 연대로 가야 한다.
       target 을 빡빡하게 둬서 오버플로우 단계가 결과를 가리지 않게 한다."""
    cands = [("a", "1990s"), ("c", "2020s")]
    picked = cd.apply_era_quota(cands, per_era_min=1, target=1,
                                existing_counts={"1990s": 1})
    assert picked == ["c"], (
        "1990s 는 시드가 이미 1건 채웠으므로 그 몫을 2020s 로 넘겨야 한다"
    )


def test_save_doc_sanitizes_windows_invalid_characters(tmp_path):
    """콜론이 Windows NTFS 대체 데이터 스트림 구문과 충돌해 파일이 잘린다.
       'Feel gHood Muzik : The 8th Wonder' 로 실제로 겪은 문제다."""
    cd.save_doc(tmp_path, "Feel gHood Muzik : The 8th Wonder", ["힙합"], "본문")
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0
    for bad in '<>:"/\\|?*':
        assert bad not in files[0].name


def test_save_doc_still_replaces_space_and_slash():
    name = cd.safe_filename("아이유/2010s 활동")
    assert " " not in name and "/" not in name
