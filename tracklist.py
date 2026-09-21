"""수록곡 섹션을 정규식으로 파싱한다. origin 은 tracklist, agreement 는 1.0."""
import re

SECTION_HEAD = re.compile(r"^\s*(수록곡|트랙 리스트|수록 곡|트랙리스트)\s*$", re.M)
TRACK_LINE = re.compile(
    r"^\s*(\d{1,2})[.)]\s*[\"「<]?([^\"」>\n(]{1,40}?)[\"」>]?\s*"
    r"(?:\([^)]*\))?\s*(?:-|–|—)?\s*(?:\d{1,2}:\d{2})?\s*$"
)
# 다음 섹션의 시작으로 볼 한 줄짜리 제목
NEXT_SECTION = re.compile(r"^\s*(각주|외부 링크|참고|평가|수상|같이 보기)\s*$")


def parse(album_title: str, body: str) -> list[dict]:
    m = SECTION_HEAD.search(body)
    if not m:
        return []
    out: list[dict] = []
    for line in body[m.end():].splitlines():
        if NEXT_SECTION.match(line):
            break
        tm = TRACK_LINE.match(line)
        if not tm:
            continue
        no, title = int(tm.group(1)), tm.group(2).strip()
        if not title:
            continue
        out.append({
            "h": album_title, "r": "CONTAINS", "t": title,
            "props": {"track_no": no},
            "origins": ["tracklist"], "agreement": 1.0,
            "sources": [album_title], "quotes": [line.strip()],
        })
    return out
