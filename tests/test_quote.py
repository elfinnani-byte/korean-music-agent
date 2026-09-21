import extract_llm as ex


def test_verify_accepts_exact_quote():
    chunk = "1996년 YG 엔터테인먼트를 설립하였다."
    assert ex.verify_quote("1996년 YG 엔터테인먼트를 설립하였다.", chunk)


def test_verify_ignores_whitespace_and_quotes_only():
    chunk = "1996년  YG 엔터테인먼트를 설립하였다."
    assert ex.verify_quote('"1996년 YG 엔터테인먼트를 설립하였다."', chunk)


def test_verify_rejects_paraphrase():
    """모델이 아는 지식으로 채운 관계는 이 대조를 통과하지 못한다."""
    chunk = "1996년 YG 엔터테인먼트를 설립하였다."
    assert not ex.verify_quote("양현석이 1996년에 YG를 만들었다", chunk)


def test_verify_rejects_empty_quote():
    assert not ex.verify_quote("", "아무 본문")


def test_filter_drops_failing_triples_and_reports_rate():
    chunk = "아이유는 2008년에 데뷔하였다."
    triples = [
        {"h": "아이유", "r": "DEBUTED_IN", "t": "2000s",
         "quotes": ["아이유는 2008년에 데뷔하였다."]},
        {"h": "아이유", "r": "INFLUENCED", "t": "누군가",
         "quotes": ["본문에 없는 문장이다."]},
    ]
    kept, stats = ex.filter_by_quote(triples, chunk)
    assert len(kept) == 1
    assert stats["pass_rate"] == 0.5
    assert len(stats["failed_samples"]) == 1


def test_cache_key_changes_with_prompt_version():
    a = ex.cache_key("본문", "schema-v1", "prompt-v1", "gpt", "v1")
    b = ex.cache_key("본문", "schema-v1", "prompt-v2", "gpt", "v1")
    assert a != b, "프롬프트를 고쳤는데 캐시가 옛 결과를 돌려주면 안 된다"


def test_chunk_overlap_duplicates_are_collapsed():
    triples = [
        {"h": "A", "r": "WROTE", "t": "B", "quotes": ["같은 문장"], "sources": ["문서1"]},
        {"h": "A", "r": "WROTE", "t": "B", "quotes": ["같은 문장"], "sources": ["문서1"]},
    ]
    assert len(ex.dedupe_within_doc(triples)) == 1
