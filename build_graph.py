"""규칙 · 트랙리스트 · LLM 3원 추출 → 단일 정규화 패스 → 그래프 저장."""
import json
import sys
from collections import Counter
from pathlib import Path

import config_loader
import extract_llm
import graph_io
import llm_factory
import normalize as nz
import rules
import schema
import tracklist

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 시드 중 개별 아티스트·그룹·레이블이 아니라 시상식·차트 프로그램·장르
# 개관 문서인 것만 고른다. 카테고리 부분 문자열 매칭은 시도했으나
# '한국대중음악상'은 '음악상'이지 '시상식'이 아니고, '엠카운트다운'은
# '텔레비전 프로그램'이지 '음악 프로그램'이 아니며, 반대로 'K-pop'은
# 거의 모든 아이돌 그룹 문서의 'K-pop 음악 그룹' 분류에 걸려 52건 중
# 22건을 교량 문서로 잘못 분류했다(실측). 제목 정확 일치로 바꾼다.
BRIDGE_DOC_TITLES = {"한국대중음악상", "골든 디스크 어워즈", "가요톱10", "엠카운트다운", "K-pop"}


def parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].removeprefix("# ").strip()
    cats = [c.strip() for c in lines[2].removeprefix("분류:").split(",") if c.strip()]
    body = text.split("\n\n", 2)[-1]
    return {"title": title, "categories": cats, "body": body, "path": path}


def infer_doc_type(cats: list[str]) -> str:
    votes = rules.vote_types_from_categories(cats)
    if not votes:
        return "기타"
    return max(votes, key=votes.get)


def main(max_docs: int | None = None) -> None:
    cfg = config_loader.load()
    config_loader.validate(cfg)
    out_dir = Path(cfg["paths"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    docs = [parse_doc(p) for p in sorted(Path(cfg["paths"]["docs_dir"]).glob("*.md"))]
    if max_docs:
        docs = docs[:max_docs]
    print(f"문서 {len(docs)}건")

    # 1) 규칙 추출 — LLM 비용 0
    rule_triples: list[dict] = []
    types: dict[str, str] = {}
    for d in docs:
        rule_triples += rules.apply(d["title"], d["categories"])
        votes = rules.vote_types_from_categories(d["categories"])
        if votes:
            types[d["title"]] = max(votes, key=votes.get)
    print(f"규칙 삼중항 {len(rule_triples)}건")

    # 2) 트랙리스트 추출 — LLM 비용 0
    track_triples: list[dict] = []
    for d in docs:
        if infer_doc_type(d["categories"]) == "Album":
            track_triples += tracklist.parse(d["title"], d["body"])
    print(f"트랙리스트 삼중항 {len(track_triples)}건")

    # 3) LLM 추출
    llm = llm_factory.get_llm("extract", cfg)
    bc = cfg["build"]
    chunks: list[tuple[str, str]] = []
    bridge_chunks: list[tuple[str, str]] = []
    for d in docs:
        header = extract_llm.chunk_header(d["title"], infer_doc_type(d["categories"]),
                                          d["categories"])
        is_bridge = d["title"] in BRIDGE_DOC_TITLES
        for ch in extract_llm.split_doc(d["body"], bc["max_doc_chars"],
                                        bc["chunk_chars"], bc["chunk_overlap"]):
            (bridge_chunks if is_bridge else chunks).append((d["title"], header + ch))
    print(f"청크 {len(chunks) + len(bridge_chunks)}개 "
          f"(교량 문서 {len(bridge_chunks)}개)")

    llm_triples, qstats = extract_llm.extract_chunks(
        extract_llm.make_transformer(llm, is_bridge_doc=False),
        chunks, bc["workers"], out_dir / "raw_triples.json", cfg)
    if bridge_chunks:
        bt, bstats = extract_llm.extract_chunks(
            extract_llm.make_transformer(llm, is_bridge_doc=True),
            bridge_chunks, bc["workers"], out_dir / "raw_triples_bridge.json", cfg)
        llm_triples += bt
        qstats["quote_total"] += bstats["quote_total"]
        qstats["quote_kept"] += bstats["quote_kept"]
        qstats["quote_pass_rate"] = (qstats["quote_kept"] /
                                     max(qstats["quote_total"], 1))
        qstats["quote_failed_samples"] += bstats["quote_failed_samples"]
    llm_triples = extract_llm.dedupe_within_doc(llm_triples)
    print(f"LLM 삼중항 {len(llm_triples)}건 "
          f"(quote 통과율 {qstats['quote_pass_rate']:.1%})")

    for t in llm_triples:
        if t.get("h_type"):
            types.setdefault(t["h"], t["h_type"])
        if t.get("t_type"):
            types.setdefault(t["t"], t["t_type"])

    # 4) 단일 정규화 패스
    g, report = nz.merge_triples(rule_triples + track_triples + llm_triples,
                                 cfg, types)
    nz.add_derived_edges(g)
    nz.annotate_hubs(g, cfg["retrieval"]["hub_degree_threshold"])
    print(f"그래프: 노드 {g.number_of_nodes()} · 간선 {g.number_of_edges()}")

    graph_io.write_json(g, out_dir / "graph.json")
    graph_io.write_graphml(g, out_dir / "graph.graphml")

    stats = {
        "docs": len(docs),
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "edges_by_relation": dict(Counter(d["relation"] for _, _, d in g.edges(data=True))),
        "edges_by_origin": dict(Counter("+".join(sorted(d["origins"]))
                                        for _, _, d in g.edges(data=True))),
        "nodes_by_type": dict(Counter(d["type"] for _, d in g.nodes(data=True))),
        "quote": qstats,
        "normalize_report": {k: (v[:30] if isinstance(v, list) else v)
                             for k, v in report.items()},
    }
    (out_dir / "build_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("build_stats.json 기록 완료")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(max_docs=n)
