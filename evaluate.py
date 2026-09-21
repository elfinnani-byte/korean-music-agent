"""3계층 평가: 색인(①) · 검색(②) · 생성(③). 앞의 두 계층은 LLM 비용이 0이다."""
import sys
from collections import Counter

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import normalize as nz


def _find_node(g, name: str) -> str | None:
    target = nz.norm_key(name)
    for nid, d in g.nodes(data=True):
        if d["norm"] == target:
            return nid
    return None


def index_level(g, h_name: str, rel: str, t_name: str) -> str:
    """exact: (h,r,t) 그대로 존재. relaxed: h-t 사이 임의 관계 존재.
       node: h·t 노드만 각각 존재. none: 하나라도 없음."""
    h, t = _find_node(g, h_name), _find_node(g, t_name)
    if h is None or t is None:
        return "none"
    for _, v, data in g.out_edges(h, data=True):
        if v == t and data["relation"] == rel:
            return "exact"
    for _, v, data in g.out_edges(h, data=True):
        if v == t:
            return "relaxed"
    for u, _, data in g.in_edges(h, data=True):
        if u == t:
            return "relaxed"
    return "node"


def index_score(g, expected_triples: list[list[str]]) -> dict[str, float]:
    if not expected_triples:
        return {"exact": 1.0, "relaxed": 1.0, "node": 1.0, "none": 0.0}
    levels = [index_level(g, h, r, t) for h, r, t in expected_triples]
    n = len(levels)
    counts = Counter(levels)
    # relaxed·node 는 exact 를 포함한 누적 비율로 보고한다(하나라도 그 이상이면 카운트)
    exact = counts["exact"] / n
    relaxed = (counts["exact"] + counts["relaxed"]) / n
    node = (counts["exact"] + counts["relaxed"] + counts["node"]) / n
    none = counts["none"] / n
    return {"exact": exact, "relaxed": relaxed, "node": node, "none": none}


import itertools

import agent


def path_prefix_recall(expected_paths: list[list[dict]], trace: list[dict]) -> tuple[float, int | None, int]:
    """대안 경로마다 시드에서부터 (rel, dir) 순서로 trace 를 따라가고
       가장 높은 접두 재현율을 취한다.
       반환: (최대 접두 재현율, 그 경로의 최초 실패 홉, 선택된 대안 인덱스)."""
    best_recall, best_break, best_idx = 0.0, 1, 0
    for idx, path in enumerate(expected_paths):
        matched = 0
        for i, step in enumerate(path):
            if i < len(trace) and trace[i]["rel"] == step["rel"] and trace[i]["dir"] == step["dir"]:
                matched += 1
            else:
                break
        recall = matched / len(path) if path else 1.0
        if recall > best_recall:
            best_recall = recall
            best_break = None if matched == len(path) else matched + 1
            best_idx = idx
    return best_recall, best_break, best_idx


def triple_recall(triples: list[dict], expected_triples: list[list[str]]) -> float:
    if not expected_triples:
        return 1.0
    have = {(t["h"], t["r"], t["t"]) for t in triples}
    hit = sum(1 for h, r, t in expected_triples if (h, r, t) in have)
    return hit / len(expected_triples)


def sweep(g, items: list[dict], cfg: dict) -> list[dict]:
    """설계서 6.2 의 4축 격자를 LLM 없이 돈다. seed_hint 를 시드로 직접
       쓴다 — 이 계층은 라우팅·시드 탐색이 아니라 순수 검색만 잰다."""
    grid = cfg["eval"]["sweep"]
    axes = list(itertools.product(grid["max_radius"], grid["hub_degree_threshold"],
                                  grid["per_relation"], grid["max_triples"]))
    rows = []
    for max_radius, hub_th, per_rel, max_tri in axes:
        recalls = []
        for it in items:
            if it.get("answer_type") == "none":
                continue
            seeds = []
            for hint in it["seed_hint"]:
                nid = _find_node(g, hint)
                if nid:
                    seeds.append(nid)
            if not seeds:
                recalls.append(0.0)
                continue
            required = [[step["rel"] for step in path] for path in it["expected_paths"][:1]]
            required = [[r] for group in required for r in group]  # 보수적으로 AND 근사
            ret = agent.run_retrieval(g, seeds, required, cfg,
                                      max_radius_override=max_radius,
                                      hub_degree_threshold_override=hub_th,
                                      per_relation_override=per_rel,
                                      max_triples_override=max_tri)
            recalls.append(triple_recall(ret["triples"], it["expected_triples"]))
        rows.append({"max_radius": max_radius, "hub_degree_threshold": hub_th,
                     "per_relation": per_rel, "max_triples": max_tri,
                     "avg_triple_recall": sum(recalls) / len(recalls) if recalls else 0.0,
                     "n_items": len(recalls)})
    return rows
