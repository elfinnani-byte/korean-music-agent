"""P1.5 차단 관문. 추출 전에 코퍼스가 멀티홉을 받칠 수 있는지 본다.

여기서 재는 것은 '문서 사이의 언급'이지 '추출된 그래프의 연결성'이 아니다.
둘은 다르다. 그래프 연결성은 P5(graph_gate.py)가 따로 본다."""
import json
import sys
from itertools import combinations
from pathlib import Path

import config_loader
import schema

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ERA_ORDER = ["1980s 이전", "1990s", "2000s", "2010s", "2020s"]


def load_docs(docs_dir: Path) -> dict[str, str]:
    out = {}
    for f in sorted(docs_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        title = text.splitlines()[0].removeprefix("# ").strip()
        body = text.split("\n\n", 2)[-1]
        out[title] = body
    return out


def cross_mentions(docs: dict[str, str]) -> dict[str, int]:
    """다른 문서의 제목을 본문에서 몇 번 언급하는가.
       자기 자신은 세지 않는다."""
    titles = list(docs)
    return {
        t: sum(1 for other in titles if other != t and other in body)
        for t, body in docs.items()
    }


def long_range_pairs(docs: dict[str, str], eras: dict[str, str]) -> int:
    """두 칸 이상 떨어진 연대끼리 서로 언급하는 문서 쌍의 수."""
    idx = {e: i for i, e in enumerate(ERA_ORDER)}
    n = 0
    for a, b in combinations(docs, 2):
        ea, eb = eras.get(a), eras.get(b)
        if ea is None or eb is None:
            continue
        if abs(idx.get(ea, 0) - idx.get(eb, 0)) < 2:
            continue
        if b in docs[a] or a in docs[b]:
            n += 1
    return n


def verdict(measured: dict, gates: dict) -> dict:
    reasons = []
    if measured["docs"] < gates["min_docs"]:
        reasons.append(f"문서 수 {measured['docs']} < {gates['min_docs']}")
    # per_era 에는 '1980s 이전'(범위 밖)과 null(시상식·소속사 등 데뷔 연도가
    # 없는 시드)도 섞여 나온다. QUOTA_ERAS 가 아닌 칸은 14건 기준 대상이
    # 아니다 — 애초에 그만큼 모을 이유도 대상도 아니다.
    for era in schema.QUOTA_ERAS:
        cnt = measured["per_era"].get(era, 0)
        if cnt < gates["min_docs_per_era"]:
            reasons.append(f"{era} 문서 {cnt} < {gates['min_docs_per_era']}")
    if measured["avg_cross"] < gates["min_avg_cross_mentions"]:
        reasons.append(f"평균 상호 언급 {measured['avg_cross']:.2f} < "
                       f"{gates['min_avg_cross_mentions']}")
    if measured["multi_seed_ratio"] < gates["min_multi_seed_ratio"]:
        reasons.append(f"다중 시드 비율 {measured['multi_seed_ratio']:.2f} < "
                       f"{gates['min_multi_seed_ratio']}")
    if measured["long_range"] < gates["min_long_range_pairs"]:
        reasons.append(f"장거리 연대 쌍 {measured['long_range']} < "
                       f"{gates['min_long_range_pairs']}")
    return {"passed": not reasons, "reasons": reasons, "measured": measured}


def main() -> None:
    cfg = config_loader.load()
    docs = load_docs(Path(cfg["paths"]["docs_dir"]))
    manifest = json.loads(Path(cfg["paths"]["manifest"]).read_text(encoding="utf-8"))
    eras = {d["title"]: d["era"] for d in manifest["docs"]}

    cm = cross_mentions(docs)
    measured = {
        "docs": len(docs),
        "per_era": manifest["document_count_by_era"],
        "avg_cross": sum(cm.values()) / max(len(cm), 1),
        "multi_seed_ratio": sum(1 for v in cm.values() if v >= 2) / max(len(cm), 1),
        "long_range": long_range_pairs(docs, eras),
    }
    v = verdict(measured, cfg["gates"]["density"])

    Path(cfg["paths"]["output_dir"], "collect_stats.json").write_text(
        json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== P1.5 밀도 관문 ===")
    for k, val in measured.items():
        print(f"  {k}: {val}")
    print("\n판정:", "PASS" if v["passed"] else "FAIL")
    for r in v["reasons"]:
        print("  -", r)
    if not v["passed"]:
        print("\n시드를 고치거나 범위를 좁혀 P1 으로 되돌아간다. 추출을 시작하지 않는다.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
