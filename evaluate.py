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
