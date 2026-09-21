"""P5 차단 관문. 구조적 건강성과 문항별 답변 가능성을 따로 본다."""
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import networkx as nx

import config_loader
import graph_io
import normalize as nz
import schema

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def largest_component_ratio(g: nx.MultiDiGraph) -> float:
    if g.number_of_nodes() == 0:
        return 0.0
    comps = list(nx.weakly_connected_components(g))
    return max(len(c) for c in comps) / g.number_of_nodes()


def bridge_edge_count(g: nx.MultiDiGraph) -> int:
    return sum(1 for _, _, d in g.edges(data=True)
               if d.get("relation") in schema.BRIDGE_RELATIONS)


def _name_index(g: nx.MultiDiGraph) -> dict[str, str]:
    return {nz.norm_key(d["name"]): n for n, d in g.nodes(data=True)}


def item_reachable(g: nx.MultiDiGraph, item: dict) -> bool:
    """기대 삼중항의 개체가 그래프에 실재하고 서로 이어져 있는가."""
    idx = _name_index(g)
    und = g.to_undirected()
    for h, _, t in item.get("expected_triples", []):
        hid, tid = idx.get(nz.norm_key(h)), idx.get(nz.norm_key(t))
        if hid is None or tid is None:
            return False
        if not nx.has_path(und, hid, tid):
            return False
    return True


def era_cross_matrix(g: nx.MultiDiGraph) -> dict[str, int]:
    """연대 × 연대 간선 교차 행렬. 0인 칸이 세대 단절 지점이다."""
    era_of: dict[str, str] = {}
    for u, v, d in g.edges(data=True):
        if d.get("relation") in ("DEBUTED_IN", "FORMED_IN", "RELEASED_IN"):
            era_of[u] = g.nodes[v]["name"]
    out: Counter[str] = Counter()
    for u, v, _ in g.edges(data=True):
        a, b = era_of.get(u), era_of.get(v)
        if a and b and a != b:
            out["|".join(sorted([a, b]))] += 1
    return dict(out)


def verdict(component_ratio: float, reachable_rate: float,
            bridge_edges: int, gates: dict) -> dict:
    reasons = []
    if component_ratio < gates["min_largest_component_ratio"]:
        reasons.append(f"전체 연결성: 최대 컴포넌트 {component_ratio:.2%} < "
                       f"{gates['min_largest_component_ratio']:.0%} "
                       f"(추출·정규화를 의심한다)")
    if bridge_edges < gates["min_bridge_edges"]:
        reasons.append(f"교량 간선 {bridge_edges} < {gates['min_bridge_edges']}")
    if reachable_rate < 1.0:
        reasons.append(f"골든셋 경로 실현 가능성 {reachable_rate:.0%} "
                       f"(문서를 표적 수집한다)")
    return {"passed": not reasons, "reasons": reasons}


def main() -> None:
    cfg = config_loader.load()
    out_dir = Path(cfg["paths"]["output_dir"])
    g = graph_io.read_json(out_dir / "graph.json")
    items = json.loads(Path(cfg["paths"]["goldenset"]).read_text(encoding="utf-8"))["items"]

    positives = [i for i in items if i.get("answer_type") != "none"]
    reachable = [i["id"] for i in positives if item_reachable(g, i)]
    rate = len(reachable) / max(len(positives), 1)

    ratio = largest_component_ratio(g)
    bridges = bridge_edge_count(g)
    v = verdict(ratio, rate, bridges, cfg["gates"]["graph"])

    deg = sorted(g.degree, key=lambda x: x[1], reverse=True)[:20]
    print("=== P5 그래프 관문 ===")
    print(f"노드 {g.number_of_nodes()} · 간선 {g.number_of_edges()}")
    print(f"최대 약연결요소 {ratio:.2%} · 교량 간선 {bridges}")
    print(f"골든셋 경로 실현 {len(reachable)}/{len(positives)} ({rate:.0%})")
    print("\n차수 상위 20 (허브 감사):")
    for nid, d in deg:
        print(f"  {d:>4}  {g.nodes[nid]['type']:<8} {g.nodes[nid]['name']}")
    print("\n연대 교차 행렬:", era_cross_matrix(g))

    ok, problems = graph_io.round_trip_ok(g, out_dir / "graph.graphml")
    if not ok:
        v["passed"] = False
        v["reasons"] += [f"graphml 왕복 실패: {p}" for p in problems]

    print("\n판정:", "PASS" if v["passed"] else "FAIL")
    for r in v["reasons"]:
        print("  -", r)
    if not v["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
