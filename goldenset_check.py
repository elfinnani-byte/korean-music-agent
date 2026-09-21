"""골든셋의 구조·경로 실현 가능성·근거 실재를 검사한다.
   P2 관문. 여기를 통과하지 못한 문항은 폐기한다."""
import json
import sys
from collections import Counter
from pathlib import Path

import schema

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

EXPECTED_HOPS = {1: 6, 2: 9, 3: 7, None: 3}
EXPECTED_SPLIT = {"tuned": 15, "holdout": 10}
VALID_ROUTES = {"local", "path", "global", "vector", "reject"}
VALID_ABSTAIN = {"no_supported_path", "out_of_scope"}


def _path_is_realizable(path: list[dict]) -> str | None:
    """각 홉의 (관계, 방향, 도착 타입) 이 스키마에 실재하는지 본다."""
    for step in path:
        rel, direction, to_type = step["rel"], step["dir"], step["to_type"]
        if direction == "out":
            ok = any(r == rel and t == to_type for _, r, t in schema.REL_TRIPLES)
        else:
            ok = any(r == rel and h == to_type for h, r, _ in schema.REL_TRIPLES)
        if not ok:
            return f"스키마에 없는 홉: {rel} {direction} -> {to_type}"
    return None


def check_item(item: dict) -> list[str]:
    errs: list[str] = []
    atype = item.get("answer_type")

    if item.get("route") not in VALID_ROUTES:
        errs.append(f"{item['id']}: 알 수 없는 route {item.get('route')}")

    if atype == "none":
        if item.get("answer") is not None:
            errs.append(f"{item['id']}: answer_type=none 이면 answer 는 null 이어야 한다")
        if item.get("expected_behavior") != "abstain":
            errs.append(f"{item['id']}: expected_behavior 는 abstain 이어야 한다")
        if item.get("abstain_reason") not in VALID_ABSTAIN:
            errs.append(f"{item['id']}: abstain_reason 이 없거나 알 수 없다")
        if item.get("expected_triples") or item.get("evidence"):
            errs.append(f"{item['id']}: none 문항의 expected_triples·evidence 는 비어야 한다")
        return errs

    if atype == "set" and "partial_credit" not in item:
        errs.append(f"{item['id']}: set 문항에 partial_credit 기준이 없다")
    if atype == "single" and not item.get("answer"):
        errs.append(f"{item['id']}: single 문항에 answer 가 없다")

    paths = item.get("expected_paths") or []
    if not paths:
        errs.append(f"{item['id']}: expected_paths 가 비어 있다")
        return errs

    shortest = min(len(p) for p in paths)
    if item.get("hops") != shortest:
        errs.append(f"{item['id']}: hops={item.get('hops')} 인데 "
                    f"최단 경로 길이는 {shortest} 다")

    for i, p in enumerate(paths):
        problem = _path_is_realizable(p)
        if problem:
            errs.append(f"{item['id']} 경로{i}: {problem}")

    if not item.get("evidence"):
        errs.append(f"{item['id']}: evidence 가 비어 있다")
    return errs


def check_collection(items: list[dict]) -> list[str]:
    errs: list[str] = []
    if len(items) != 25:
        errs.append(f"문항 수가 {len(items)} 다. 25 여야 한다")

    ids = [i["id"] for i in items]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        errs.append(f"ID 중복: {dup}")
    missing = sorted({f"Q{n:02d}" for n in range(1, 26)} - set(ids))
    if missing:
        errs.append(f"누락 ID: {missing}")

    hops = Counter(i.get("hops") for i in items)
    for k, expected in EXPECTED_HOPS.items():
        if hops.get(k, 0) != expected:
            errs.append(f"hops={k} 문항이 {hops.get(k, 0)}건이다. {expected}건이어야 한다")

    splits = Counter(i.get("split") for i in items)
    for k, expected in EXPECTED_SPLIT.items():
        if splits.get(k, 0) != expected:
            errs.append(f"{k} 묶음이 {splits.get(k, 0)}건이다. {expected}건이어야 한다")

    for item in items:
        errs += check_item(item)
    return errs


def check_evidence_exists(items: list[dict], docs_dir: Path) -> list[str]:
    """인용문이 실제 문서에 글자 그대로 있는지 본다.
       설계 단계에서 지어 넣은 인용문을 여기서 걸러낸다."""
    errs = []
    for item in items:
        for ev in item.get("evidence", []):
            path = docs_dir / ev["doc"]
            if not path.exists():
                errs.append(f"{item['id']}: 문서 없음 {ev['doc']}")
                continue
            body = path.read_text(encoding="utf-8")
            squeezed = "".join(body.split())
            if "".join(ev["quote"].split()) not in squeezed:
                errs.append(f"{item['id']}: 인용문이 원문에 없다 — {ev['quote'][:30]}...")
    return errs


def main() -> None:
    import config_loader
    cfg = config_loader.load()
    items = json.loads(Path(cfg["paths"]["goldenset"]).read_text(encoding="utf-8"))["items"]

    errs = check_collection(items)
    errs += check_evidence_exists(items, Path(cfg["paths"]["docs_dir"]))

    print("=== P2 골든셋 검증 ===")
    print(f"문항 {len(items)}건")
    print("홉 분포:", dict(Counter(i.get('hops') for i in items)))
    print("묶음:", dict(Counter(i.get('split') for i in items)))
    print("세대 교차:", sum(1 for i in items if i.get("era_cross")))
    if errs:
        print(f"\n오류 {len(errs)}건:")
        for e in errs:
            print("  -", e)
        raise SystemExit(1)
    print("\n판정: PASS")


if __name__ == "__main__":
    main()
