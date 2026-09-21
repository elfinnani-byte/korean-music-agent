import evaluate as ev


def test_tokenize_falls_back_to_char_bigram_when_morpheme_unavailable(monkeypatch):
    monkeypatch.setattr(ev, "_kiwi", None)
    toks = ev.tokenize("서태지와 아이들")
    assert toks == ["서태", "태지", "지와", "와 ", " 아", "아이", "이들"]


def test_chunk_corpus_splits_by_char_length():
    chunks = ev.chunk_corpus([("문서1", "가" * 1000)], chunk_chars=800)
    assert len(chunks) == 2
    assert chunks[0][0] == "문서1"


def test_bm25_search_ranks_matching_chunk_first():
    chunks = [("a", "서태지와 아이들은 1992년에 데뷔했다"),
              ("b", "오늘 날씨는 맑고 화창하다")]
    ranked = ev.bm25_search("서태지와 아이들은 언제 데뷔했는가", chunks, k=2)
    assert ranked[0][0] == "a"
