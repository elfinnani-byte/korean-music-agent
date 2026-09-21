"""graph.json 이 정준 런타임 그래프. graphml 은 제출·시각화용 파생물."""
import json
import os
import re
from pathlib import Path

import networkx as nx

SCALAR = (str, int, float, bool)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def write_json(g: nx.MultiDiGraph, path: Path) -> None:
    payload = {
        "nodes": [{"id": n, **d} for n, d in g.nodes(data=True)],
        "edges": [{"h": u, "t": v, **d} for u, v, d in g.edges(data=True)],
    }
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))


def read_json(path: Path) -> nx.MultiDiGraph:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    g = nx.MultiDiGraph()
    for node in payload["nodes"]:
        nid = node.pop("id")
        g.add_node(nid, **node)
    for edge in payload["edges"]:
        h, t = edge.pop("h"), edge.pop("t")
        g.add_edge(h, t, **edge)
    return g


def _xml_safe(s: str) -> str:
    """LLM 추출 quote 에 XML이 담지 못하는 제어 문자가 섞여 들어올 수 있다.
       graph.json(정준본)은 그대로 두고, graphml(파생본)에서만 제거한다."""
    return CONTROL_CHARS.sub("", s)


def _flatten(d: dict) -> dict:
    """graphml 은 스칼라만 저장한다. 리스트는 조인하고 None 은 생략한다."""
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            out[k] = _xml_safe("|".join(str(x) for x in v))
        elif isinstance(v, dict):
            if v:
                out[k] = _xml_safe(json.dumps(v, ensure_ascii=False))
        elif isinstance(v, str):
            out[k] = _xml_safe(v)
        elif isinstance(v, SCALAR):
            out[k] = v
        else:
            out[k] = _xml_safe(str(v))
    return out


def write_graphml(g: nx.MultiDiGraph, path: Path) -> None:
    flat = nx.MultiDiGraph()
    for n, d in g.nodes(data=True):
        flat.add_node(n, **_flatten(d))
    for u, v, d in g.edges(data=True):
        flat.add_edge(u, v, **_flatten(d))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(flat, path, encoding="utf-8")


def _atomic_write(path: Path, text: str) -> None:
    """OneDrive 동기화 폴더에서 Streamlit 이 파일을 잡고 있는 동안
       덮어쓰기가 실패할 수 있다. 임시 파일에 쓰고 교체한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def round_trip_ok(g: nx.MultiDiGraph, path: Path) -> tuple[bool, list[str]]:
    """P5 관문에서 쓴다. 저장 후 다시 읽어 수가 맞는지 본다."""
    back = nx.read_graphml(path)
    problems = []
    if back.number_of_nodes() != g.number_of_nodes():
        problems.append(f"노드 수 불일치 {back.number_of_nodes()} != {g.number_of_nodes()}")
    if back.number_of_edges() != g.number_of_edges():
        problems.append(f"간선 수 불일치 {back.number_of_edges()} != {g.number_of_edges()}")
    return not problems, problems
