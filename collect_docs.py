"""시드에서 2홉으로 넓혀 코퍼스를 모은다.
   수집은 느리고 위키 내용이 바뀌면 결과가 달라지므로 build_graph.py 와 분리한다.
   한 번 모으면 고정하고 커밋한다."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import config_loader
import schema
from wiki_client import WikiClient

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

MUSIC_HINTS = ("음악", "가수", "음반", "노래", "밴드", "그룹", "아이돌",
               "힙합", "작곡", "작사", "프로듀서", "시상식", "싱글", "데뷔")
BLACKLIST = [re.compile(p) for p in schema.CATEGORY_BLACKLIST]
YEAR_DEBUT = re.compile(r"^(\d{4})년\s*데뷔")
YEAR_FORMED = re.compile(r"^(\d{4})년\s*(?:결성|설립)")
YEAR_ALBUM = re.compile(r"^(\d{4})년\s*(?:음반|노래|싱글)")
# 솔로 아티스트는 'YYYY년 데뷔' 대신 'YYYY년대 가수' 를 갖는 경우가 많다
# (예: 아이유·보아·신승훈). 정확한 데뷔 연도가 없을 때의 대안이다.
DECADE_CATEGORY = re.compile(r"^(\d{4})년대\s*(?:가수|음악가|아이돌|그룹|밴드)$")


def is_music_doc(title: str, cats: list[str]) -> bool:
    if any(b.search(c) for c in cats for b in BLACKLIST):
        return False
    if "동음이의" in title or "목록" in title:
        return False
    return any(h in c for c in cats for h in MUSIC_HINTS)


def era_from_categories(cats: list[str]) -> str | None:
    """데뷔 연도를 우선하고 없으면 연대 카테고리·결성·발매 연도로 대신한다.
       설계서 3.2 — 데뷔와 결성은 다른 사건이므로 어느 쪽을 썼는지 구분해 둔다.

       솔로 아티스트는 정확한 'YYYY년 데뷔'가 아니라 'YYYY년대 가수' 를
       갖는 경우가 많다(아이유·보아·신승훈 실제 카테고리로 확인). 활동
       기간이 여러 연대에 걸치면(신승훈: 1990s+2000s+2010s) 데뷔에 가까운
       가장 이른 연대를 고른다 — 최근 연대를 고르면 세대 앵커 역할을 잃는다."""
    for c in cats:
        m = YEAR_DEBUT.match(c)
        if m:
            return schema.era_of_year(int(m.group(1)))

    decade_years = [int(m.group(1)) for c in cats if (m := DECADE_CATEGORY.match(c))]
    if decade_years:
        return schema.era_of_year(min(decade_years))

    for pat in (YEAR_FORMED, YEAR_ALBUM):
        for c in cats:
            m = pat.match(c)
            if m:
                return schema.era_of_year(int(m.group(1)))
    return None


def rank_candidates(links_by_seed: dict[str, list[str]]) -> list[tuple[str, int]]:
    """여러 시드가 함께 가리킨 문서를 앞에 둔다.
       둘을 잇는다는 것이 곧 다리라는 뜻이다."""
    counter: Counter[str] = Counter()
    for seed, links in links_by_seed.items():
        for t in set(links):
            counter[t] += 1
    return counter.most_common()


def apply_era_quota(candidates: list[tuple[str, str]], per_era_min: int,
                    target: int, existing_counts: dict[str, int] | None = None) -> list[str]:
    """연대 쿼터를 먼저 채운 뒤 남는 자리를 순위대로 채운다.
       쿼터가 없으면 문서가 많은 2010~20년대로 쏠려 1990년대가 빈다.

       existing_counts 는 시드 문서가 이미 채운 연대별 건수다. 이미 채운
       연대에서 또 per_era_min 만큼 새로 뽑으면 target 이 그만큼 낭비되고,
       정작 부족한 다른 연대로 갈 몫이 줄어든다."""
    existing_counts = existing_counts or {}
    picked: list[str] = []
    by_era: dict[str, list[str]] = {}
    for title, era in candidates:
        by_era.setdefault(era, []).append(title)

    for era in schema.QUOTA_ERAS:
        need = max(per_era_min - existing_counts.get(era, 0), 0)
        picked += by_era.get(era, [])[:need]
    for title, _ in candidates:
        if len(picked) >= target:
            break
        if title not in picked:
            picked.append(title)
    return picked[:target]


WINDOWS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_filename(title: str) -> str:
    """Windows NTFS 에서 파일명으로 못 쓰는 문자를 전부 치환한다.
       콜론은 특히 위험하다 — 대체 데이터 스트림 구문으로 해석돼
       'Feel gHood Muzik : The 8th Wonder' 가 콜론 앞부분만 남고 잘렸다."""
    return WINDOWS_INVALID_CHARS.sub("_", title.replace(" ", "_"))


def save_doc(out_dir: Path, title: str, cats: list[str], body: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(title) + ".md"
    text = f"# {title}\n\n분류: {', '.join(cats)}\n\n{body}\n"
    (out_dir / fname).write_text(text, encoding="utf-8")


def main() -> None:
    cfg = config_loader.load()
    config_loader.validate(cfg)
    cc = cfg["collect"]
    client = WikiClient(delay_sec=cc["request_delay_sec"],
                        max_attempts=cc["retry"]["max_attempts"],
                        backoff_base=cc["retry"]["backoff_base_sec"],
                        user_agent=cc["user_agent"])
    out_dir = Path(cfg["paths"]["docs_dir"])

    seeds: list[str] = []
    for raw in cc["seed_titles"]:
        title = cc["redirect_map"].get(raw, raw)
        resolved = client.resolve_title(title)
        if resolved is None:
            print(f"  [시드 해소 실패] {raw}")
            continue
        seeds.append(resolved)
    print(f"시드 {len(seeds)}건 해소 완료")

    # 시드는 2홉 순위와 무관하게 반드시 코퍼스에 포함한다. 시드를 링크로만
    # 다루면 서로 링크하는 시드만 우연히 살아남고, 시상식·소속사처럼
    # 세대 교량 역할을 하도록 고른 시드가 코퍼스에서 통째로 빠질 수 있다.
    saved: list[dict] = []
    saved_titles: set[str] = set()
    dropped_short = 0
    seed_cats_map = client.categories_bulk(seeds)
    for title in seeds:
        cats = seed_cats_map.get(title, [])
        body = client.extract(title)
        if len(body) < cc["min_body_chars"]:
            dropped_short += 1
            print(f"  [시드 본문 부족] {title} ({len(body)}자)")
            continue
        era = era_from_categories(cats)  # 시상식·소속사 등은 None 이어도 저장한다
        save_doc(out_dir, title, cats, body)
        saved_titles.add(title)
        saved.append({"title": title, "era": era, "categories": cats,
                      "chars": len(body), "source": "seed"})
        print(f"  저장 {len(saved):>3}. {title} ({len(body)}자) [시드]")

    links_by_seed = {s: client.links(s, cc["link_limit_per_seed"]) for s in seeds}
    ranked = rank_candidates(links_by_seed)
    multi = [t for t, n in ranked if n >= 2 and t not in saved_titles]
    print(f"2홉 후보 {len(ranked)}건, 그중 2개 이상 시드가 가리키고 "
          f"시드가 아닌 것 {len(multi)}건")

    # candidate_pool_cap 을 넘기면 뒤쪽 후보가 분류 확인조차 못 받고 버려진다.
    # 실제로 959건 중 상위 600건만 보다가 1990s·2020s 연대 쿼터를 못 채운
    # 적이 있어, 후보 전체가 들어가도록 여유 있게 잡는다.
    cats_map = client.categories_bulk(multi[:cc["candidate_pool_cap"]])
    survivors: list[tuple[str, str]] = []
    for title, cats in cats_map.items():
        if title in saved_titles or not is_music_doc(title, cats):
            continue
        era = era_from_categories(cats)
        if era is None:
            continue
        survivors.append((title, era))
    print(f"분류 필터 통과 {len(survivors)}건")

    remaining_target = max(cc["target_docs"] - len(saved), 0)
    existing_era_counts = Counter(d["era"] for d in saved if d["era"])
    chosen = apply_era_quota(survivors, cc["per_era_min"], remaining_target,
                             existing_era_counts)
    era_of = dict(survivors)

    for title in chosen:
        body = client.extract(title)
        if len(body) < cc["min_body_chars"]:
            dropped_short += 1
            continue
        save_doc(out_dir, title, cats_map.get(title, []), body)
        saved_titles.add(title)
        saved.append({"title": title, "era": era_of.get(title),
                      "categories": cats_map.get(title, []), "chars": len(body),
                      "source": "2hop"})
        print(f"  저장 {len(saved):>3}. {title} ({len(body)}자)")

    stats = {
        "document_count": len(saved),
        "document_count_by_era": dict(Counter(d["era"] for d in saved)),
        "short_document_dropped": dropped_short,
        "seed_count": len(seeds),
        "request_count": client.request_count,
        "retry_count": client.retry_count,
        "docs": saved,
    }
    Path(cfg["paths"]["manifest"]).write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n연대별 분포:", stats["document_count_by_era"])
    print(f"총 {len(saved)}건 저장, 재시도 {client.retry_count}회")


if __name__ == "__main__":
    main()
