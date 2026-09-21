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
import schema


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


import math
from pathlib import Path

try:
    from kiwipiepy import Kiwi
    _kiwi = Kiwi()
except Exception:
    _kiwi = None


def tokenize(text: str) -> list[str]:
    """형태소 분석기를 1순위로 쓰고 실패하면 문자 2-gram 으로 폴백한다.
       공백 분리는 한국어 BM25 재현율을 반토막 낸다(설계서 6.6)."""
    if _kiwi is not None:
        return [t.form for t in _kiwi.tokenize(text) if not t.tag.startswith("S")]
    return [text[i:i + 2] for i in range(len(text) - 1)]


def chunk_corpus(docs: list[tuple[str, str]], chunk_chars: int = 800) -> list[tuple[str, str]]:
    chunks = []
    for title, body in docs:
        for i in range(0, len(body), chunk_chars):
            chunks.append((title, body[i:i + chunk_chars]))
    return chunks


def bm25_search(query: str, chunks: list[tuple[str, str]], k: int = 6,
                k1: float = 1.5, b: float = 0.75) -> list[tuple[str, str, float]]:
    q_terms = tokenize(query)
    doc_terms = [tokenize(body) for _, body in chunks]
    n = len(chunks)
    avgdl = sum(len(d) for d in doc_terms) / n if n else 0
    df: dict[str, int] = {}
    for terms in doc_terms:
        for term in set(terms):
            df[term] = df.get(term, 0) + 1

    scores = []
    for (title, body), terms in zip(chunks, doc_terms):
        tf: dict[str, int] = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1
        dl = len(terms)
        score = 0.0
        for term in q_terms:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            freq = tf[term]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / max(avgdl, 1)))
        scores.append((title, body, score))
    scores.sort(key=lambda x: -x[2])
    return scores[:k]


def load_corpus_chunks(docs_dir: str, chunk_chars: int = 800) -> list[tuple[str, str]]:
    docs = []
    for p in sorted(Path(docs_dir).glob("*.md")):
        text = p.read_text(encoding="utf-8")
        body = text.split("\n\n", 2)[-1]
        title = text.splitlines()[0].removeprefix("# ").strip()
        docs.append((title, body))
    return chunk_corpus(docs, chunk_chars)


def baseline_answer(question: str, chunks: list[tuple[str, str]], cfg: dict, llm) -> tuple[str, list[str]]:
    """같은 답변 프롬프트 뼈대를 쓰되 근거를 삼중항 대신 원문 청크로 준다.
       공정성 조건(설계서 6.6): 같은 코퍼스·같은 청크 크기·같은 LLM·같은
       프롬프트 뼈대·같은 심판."""
    k = cfg["eval"]["baseline"]["k"]
    hits = bm25_search(question, chunks, k=k)
    context = "\n\n".join(f"[출처: {title}]\n{body}" for title, body, _ in hits)
    sources = [title for title, _, _ in hits]
    prompt = (f"{schema.ANSWER_SYSTEM_PROMPT}\n\n[근거 원문 청크]\n{context}\n\n[질문]\n{question}")
    resp = llm.invoke(prompt)
    return resp.content, sources


import re


def judge_score(question: str, model_answer: str, gold_answer: str,
                evidence: str, llm) -> float | None:
    prompt = schema.JUDGE_PROMPT.format(question=question, model_answer=model_answer,
                                        gold_answer=gold_answer, evidence=evidence)
    resp = llm.invoke(prompt)
    m = re.search(r"\b(1\.0|0\.5|0\.0)\b", resp.content)
    return float(m.group(1)) if m else None


def classify_failure(item: dict, route_actual: str, idx: dict, ret: dict, gen: dict) -> str:
    """앞 조건이 걸리면 뒤는 보지 않는다. 순서를 고정한다(설계서 6.4)."""
    if route_actual != item["route"]:
        return "routing"
    if not ret["seeds"]:
        return "seeding"
    if idx["exact"] < 1.0:
        return "index"
    if ret["triple_recall"] < 1.0:
        return "retrieval"
    if gen["decision"] == "abstain" and idx["exact"] == 1.0:
        return "abstain"
    if gen["score"] is not None and gen["score"] < 1.0:
        return "generation"
    return "ok"


LAYER_3_MAP = {"index": "색인", "routing": "탐색", "seeding": "탐색", "retrieval": "탐색",
               "abstain": "생성", "generation": "생성", "ok": "정상"}


import statistics

import agent as _agent


def evaluate_item(item: dict, g, cfg: dict, route_llm, answer_llm, judge_llm,
                  chunks: list[tuple[str, str]] | None = None) -> dict:
    result = _agent.ask(item["question"], g=g, cfg=cfg, route_llm=route_llm, answer_llm=answer_llm)

    idx = index_score(g, item.get("expected_triples", []))
    t_recall = triple_recall(result["triples"], item.get("expected_triples", []))
    p_recall, break_hop, matched_idx = (path_prefix_recall(item["expected_paths"], result["trace"])
                                        if item.get("expected_paths") else (1.0, None, 0))

    evidence = " ".join(e["quote"] for e in item.get("evidence", []))
    gold = item.get("answer") or "기권해야 함"
    scores = []
    for _ in range(cfg["eval"]["judge_repeats"]):
        s = judge_score(item["question"], result["answer"], gold, evidence, judge_llm)
        scores.append(s)
    valid_scores = [s for s in scores if s is not None]

    gen = {"decision": result["decision"],
          "score": statistics.mean(valid_scores) if valid_scores else None}
    ret = {"seeds": result["seeds"], "triple_recall": t_recall}
    layer = classify_failure(item, result["route"], idx, ret, gen)

    baseline = None
    if chunks is not None:
        b_answer, b_sources = baseline_answer(item["question"], chunks, cfg, answer_llm)
        b_scores = [judge_score(item["question"], b_answer, gold, evidence, judge_llm)
                   for _ in range(cfg["eval"]["judge_repeats"])]
        b_valid = [s for s in b_scores if s is not None]
        baseline = {"answer": b_answer, "score": statistics.mean(b_valid) if b_valid else None}

    return {"id": item["id"], "hops": item.get("hops"), "era_cross": item.get("era_cross"),
           "route_expected": item["route"], "route_actual": result["route"],
           "idx": idx, "triple_recall": t_recall, "path_prefix_recall": p_recall,
           "break_hop": break_hop, "matched_path_index": matched_idx,
           "decision": result["decision"], "llm_answer_called": result["llm_answer_called"],
           "scores": scores, "score": gen["score"], "failure_layer": layer,
           "layer3": LAYER_3_MAP[layer], "baseline": baseline}


def hop_summary_table(rows: list[dict]) -> dict[int, dict]:
    """rows 는 evaluate_item() 의 반환값 그대로다 — idx 는 중첩
       딕셔너리이고 score 는 심판 전원 실패 시 None 일 수 있다.
       None 은 평균에서 제외한다(0으로 섞지 않는다, 설계서 6.3)."""
    by_hop: dict[int, list[dict]] = {}
    for r in rows:
        by_hop.setdefault(r["hops"], []).append(r)
    table = {}
    for hops, group in by_hop.items():
        scored = [r["score"] for r in group if r["score"] is not None]
        table[hops] = {
            "n": len(group),
            "avg_idx_exact": sum(r["idx"]["exact"] for r in group) / len(group),
            "avg_triple_recall": sum(r["triple_recall"] for r in group) / len(group),
            "avg_path_prefix_recall": sum(r["path_prefix_recall"] for r in group) / len(group),
            "avg_score": sum(scored) / len(scored) if scored else None,
        }
    return table
