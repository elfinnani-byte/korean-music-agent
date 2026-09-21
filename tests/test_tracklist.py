import tracklist

BODY = """아이유의 정규 앨범이다.

수록곡

1. 밤편지 (3:32)
2. 팔레트 - 4:01
3. 이름에게
4. 사랑이 잘

각주

1. 어떤 각주다
"""


def test_parses_numbered_tracks():
    out = tracklist.parse("Palette", BODY)
    titles = [t["t"] for t in out]
    assert titles == ["밤편지", "팔레트", "이름에게", "사랑이 잘"]


def test_sets_album_as_head_and_track_number():
    out = tracklist.parse("Palette", BODY)
    assert out[0]["h"] == "Palette"
    assert out[0]["r"] == "CONTAINS"
    assert out[0]["props"]["track_no"] == 1


def test_stops_at_next_section():
    """각주 절의 번호 목록을 수록곡으로 먹으면 안 된다."""
    out = tracklist.parse("Palette", BODY)
    assert all("각주" not in t["t"] for t in out)
    assert len(out) == 4


def test_returns_empty_when_no_tracklist_section():
    assert tracklist.parse("어떤앨범", "그냥 본문이다.") == []
