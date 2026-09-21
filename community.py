"""Louvain 커뮤니티 탐지 + 집계 프로필 + LLM 요약. 전역 검색(route=='global')용.
   속성 노드(Genre·Era)가 걸린 간선은 가중치를 감쇠한다 — 감쇠하지 않으면
   장르 허브가 그래프 전체를 한 덩어리로 묶는다."""
import sys
from collections import Counter

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import networkx as nx


def edge_weight(g, u: str, v: str, data: dict, attr_weight: float) -> float:
    touches_attr = (g.nodes[u]["type"] in ("Genre", "Era") or g.nodes[v]["type"] in ("Genre", "Era"))
    return data["agreement"] * (attr_weight if touches_attr else 1.0)


def detect_communities(g, attr_weight: float, resolution: float, min_size: int, seed: int) -> list[set]:
    und = nx.Graph()
    for u, v, data in g.edges(data=True):
        w = edge_weight(g, u, v, data, attr_weight)
        if und.has_edge(u, v):
            und[u][v]["weight"] += w
        else:
            und.add_edge(u, v, weight=w)
    comms = nx.community.louvain_communities(und, weight="weight", resolution=resolution, seed=seed)
    return [c for c in comms if len(c) >= min_size]


def profile_community(g, node_ids: set) -> dict:
    """LLM 에는 노드 나열이 아니라 이 집계 프로필만 넘긴다."""
    sub_nodes = [(nid, g.nodes[nid]) for nid in node_ids]
    artists = [d["name"] for _, d in sub_nodes if d["type"] == "Artist"]
    groups = [d["name"] for _, d in sub_nodes if d["type"] == "Group"]
    genres = Counter()
    eras = set()
    rel_count = Counter()
    n_edges = 0
    for u, v, data in g.edges(data=True):
        if u in node_ids and v in node_ids:
            n_edges += 1
            rel_count[data["relation"]] += 1
            if g.nodes[v]["type"] == "Genre":
                genres[g.nodes[v]["name"]] += 1
            if g.nodes[v]["type"] == "Era":
                eras.add(g.nodes[v]["name"])
    return {
        "size": len(node_ids), "n_edges": n_edges, "n_artists": len(artists) + len(groups),
        "top_artists": artists[:10], "top_groups": groups[:10],
        "genre_distribution": dict(genres.most_common(5)),
        "era_span": sorted(eras), "relation_composition": dict(rel_count.most_common(8)),
    }


def summarize_community(profile: dict, llm) -> dict:
    prompt = (
        "아래는 한국 대중음악 그래프의 한 커뮤니티(밀집 연결 부분집합)의 집계 정보다. "
        "이 정보만으로 title·summary·findings(리스트) 를 JSON으로 작성하라. "
        "정보에 없는 구체적 개체명을 지어내지 마라.\n\n"
        f"{profile}\n\n"
        '형식: {"title": "...", "summary": "...", "findings": ["...", "..."]}'
    )
    resp = llm.invoke(prompt)
    import json
    import re
    m = re.search(r"\{.*\}", resp.content, re.S)
    return json.loads(m.group(0)) if m else {"title": "", "summary": "", "findings": []}


def build_reports(g, cfg: dict, llm) -> list[dict]:
    c = cfg["community"]
    comms = detect_communities(g, c["attr_weight"], c["resolution"], c["min_size"], c["seed"])
    reports = []
    for comm in comms:
        profile = profile_community(g, comm)
        summary = summarize_community(profile, llm)
        reports.append({**summary, "profile": profile})
    return reports
