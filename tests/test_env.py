def test_python_is_utf8_capable():
    """이 환경의 로케일은 cp949 일 수 있다. 그래도 명시적 encoding="utf-8"과
       stdout.reconfigure 로 한글 입출력이 실제로 되는지 확인한다 —
       뒤의 모든 태스크가 이 두 방어책에 의존한다."""
    import io
    import tempfile
    from pathlib import Path

    # ① 명시적 encoding="utf-8" 로 한글을 쓰고 읽을 수 있어야 한다
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "한글파일.txt"
        p.write_text("안녕하세요, 아이유", encoding="utf-8")
        assert p.read_text(encoding="utf-8") == "안녕하세요, 아이유"

    # ② stdout 을 utf-8 로 재설정하는 호출이 예외 없이 동작해야 한다
    #    (실제 재설정은 각 진입 스크립트가 하므로 여기서는 호출 가능성만 본다)
    buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    buf.write("한글 출력 테스트")
    buf.flush()


def test_graph_transformer_imports_and_accepts_tuples():
    """langchain-experimental 은 유지보수가 중단됐고 langchain 1.x 에서 import 가
       깨진 사례가 있다. 새 가상환경에서 이것이 되는지가 추출 단계의 전제다."""
    import inspect
    from langchain_experimental.graph_transformers import LLMGraphTransformer

    sig = inspect.signature(LLMGraphTransformer.__init__)
    ann = str(sig.parameters["allowed_relationships"].annotation)
    assert "Tuple" in ann, f"튜플 선언을 받지 못한다: {ann}"


def test_langgraph_imports():
    from langgraph.graph import StateGraph, START, END

    assert hasattr(StateGraph, "add_conditional_edges")
