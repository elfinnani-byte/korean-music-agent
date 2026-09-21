"""LLMGraphTransformer 호출 · quote 원문 대조 · 캐시.

주의: langchain-experimental 은 유지보수가 중단됐다. 이 PC 에서는
langchain-classic 이 함께 설치돼 있어 import 가 되지만, 새 환경에서
'No module named langchain.graphs' 가 나면 requirements 의
langchain-classic 이 빠진 것이다. 그래도 안 되면 langchain-neo4j 의
동명 클래스로 갈아탄다 — 생성자 시그니처가 같다."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import schema


def squeeze(s: str) -> str:
    return re.sub(r"[\s\"'「」<>《》]", "", s)


def verify_quote(quote: str, chunk_text: str) -> bool:
    """근거 문장이 원문 청크에 실재하는지 확인한다.
       공백·따옴표만 제거해 비교한다. 그 이상 느슨하게 하면
       검증이 통과 도장으로 전락한다."""
    if not quote or not quote.strip():
        return False
    return squeeze(quote) in squeeze(chunk_text)


def filter_by_quote(triples: list[dict], chunk_text: str) -> tuple[list[dict], dict]:
    kept, failed = [], []
    for t in triples:
        quotes = t.get("quotes") or []
        if any(verify_quote(q, chunk_text) for q in quotes):
            kept.append(t)
        else:
            failed.append(t)
    total = len(triples)
    return kept, {
        "total": total,
        "kept": len(kept),
        "pass_rate": (len(kept) / total) if total else 1.0,
        "failed_samples": failed[:10],
    }


def dedupe_within_doc(triples: list[dict]) -> list[dict]:
    """청크가 겹쳐 같은 사실이 두 번 추출되면 count 가 부푼다.
       같은 문서 안에서 (h, r, t) 와 quote 가 같으면 한 번만 센다."""
    seen: set[tuple] = set()
    out = []
    for t in triples:
        key = (t["h"], t["r"], t["t"], tuple(sorted(t.get("quotes", []))),
               tuple(sorted(t.get("sources", []))))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def cache_key(chunk_text: str, schema_version: str, prompt_version: str,
              model_id: str, extraction_version: str) -> str:
    """청크 해시만 쓰면 스키마·프롬프트·모델을 바꿔도 옛 결과가 나온다.
       바꾼 것이 반영되지 않았는데 반영된 줄 아는 것이 가장 나쁜 실패다."""
    chunk_sha = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
    joined = "|".join([chunk_sha, schema_version, prompt_version,
                       model_id, extraction_version])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def schema_version() -> str:
    payload = json.dumps([sorted(schema.NODE_TYPES.items()),
                          sorted(schema.REL_TRIPLES)], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def prompt_version() -> str:
    return hashlib.sha256(
        schema.EXTRACTION_INSTRUCTIONS.encode("utf-8")).hexdigest()[:12]


def chunk_header(title: str, doc_type: str, categories: list[str]) -> str:
    """LLMGraphTransformer 는 metadata 를 프롬프트에 넣지 않는다.
       빠뜨리면 다른 아티스트의 곡이 엉뚱한 문서에 붙는다."""
    return (f"[문서 제목] {title}\n"
            f"[문서 유형] {doc_type}\n"
            f"[주요 분류] {', '.join(categories[:6])}\n"
            f"[본문]\n")


def split_doc(body: str, max_doc_chars: int, chunk_chars: int,
              overlap: int) -> list[str]:
    """max_doc_chars 는 원문을 잘라 버리는 값이 아니라 LLM 입력 상한이다.
       data/docs 의 원문은 그대로 두고 여기서만 앞부분을 취한다."""
    text = body[:max_doc_chars]
    step = chunk_chars - overlap
    return [text[i:i + chunk_chars] for i in range(0, len(text), step) if text[i:i + chunk_chars].strip()]


def make_transformer(llm, is_bridge_doc: bool = False):
    from langchain_experimental.graph_transformers import LLMGraphTransformer

    instructions = schema.EXTRACTION_INSTRUCTIONS
    if is_bridge_doc:
        instructions += schema.BRIDGE_DOC_EXTRA
    return LLMGraphTransformer(
        llm=llm,
        allowed_nodes=list(schema.NODE_TYPES),
        allowed_relationships=schema.REL_TRIPLES,
        strict_mode=True,
        node_properties=["year"],
        relationship_properties=["year", "role", "cover", "former", "quote"],
        additional_instructions=instructions,
    )


def extract_chunks(transformer, chunks: list[tuple[str, str]], workers: int,
                   cache_path: Path, cfg: dict) -> tuple[list[dict], dict]:
    """chunks 는 (문서제목, 청크텍스트) 목록.
       청크마다 try/except 로 실패를 격리하고 실패 ID 를 기록한다."""
    from langchain_core.documents import Document

    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    sv, pv = schema_version(), prompt_version()
    model_id = cfg["llm"]["profiles"]["extract"]["model"]
    ev = cfg["build"]["extraction_version"]
    failures: list[str] = []

    def one(item):
        title, text = item
        key = cache_key(text, sv, pv, model_id, ev)
        if key in cache:
            return key, cache[key], None
        try:
            docs = transformer.convert_to_graph_documents([Document(page_content=text)])
            triples = []
            for gd in docs:
                for rel in gd.relationships:
                    props = dict(getattr(rel, "properties", {}) or {})
                    quote = props.pop("quote", "")
                    triples.append({
                        "h": rel.source.id, "h_type": rel.source.type,
                        "r": rel.type,
                        "t": rel.target.id, "t_type": rel.target.type,
                        "props": props, "origins": ["llm"], "agreement": 0.8,
                        "sources": [title], "quotes": [quote] if quote else [],
                    })
            kept, stats = filter_by_quote(triples, text)
            return key, {"triples": kept, "quote_stats": stats}, None
        except Exception as exc:
            return key, {"triples": [], "quote_stats": {"total": 0, "kept": 0,
                                                        "pass_rate": 1.0,
                                                        "failed_samples": []}}, \
                   f"{title}: {type(exc).__name__} {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, chunks))

    all_triples, total, kept, samples = [], 0, 0, []
    for key, payload, err in results:
        cache[key] = payload
        all_triples += payload["triples"]
        qs = payload["quote_stats"]
        total += qs["total"]
        kept += qs["kept"]
        samples += qs["failed_samples"]
        if err:
            failures.append(err)

    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return all_triples, {
        "quote_total": total, "quote_kept": kept,
        "quote_pass_rate": (kept / total) if total else 1.0,
        "quote_failed_samples": samples[:10],
        "chunk_failures": failures,
    }
