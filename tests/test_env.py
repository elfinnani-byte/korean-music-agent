import sys


def test_python_is_utf8_capable():
    assert sys.getdefaultencoding() == "utf-8"


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
