"""LangGraph 기반 RAG 에이전트. n_route 부터 n_synthesize/n_insufficient 까지.

State 원칙 둘.
1. 모든 필드는 JSON 직렬화 가능해야 한다. visited 를 set 으로 두면
   LangGraph 체크포인트와 runs.jsonl 기록에서 둘 다 깨진다. 중복 확인은
   함수 안 지역 변수 set 으로 하고, State 에 나가는 것은 list 다.
2. 관계 공백 필드는 gap_rels 하나로만 부른다. required_rels 는 라우터가
   산출한 요구 사항이고 gap_rels 는 그중 아직 못 채운 것으로, 둘은 다른 값이다.
"""
import sys
from typing import Literal, TypedDict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class RAGState(TypedDict, total=False):
    question: str
    route: Literal["local", "path", "global", "vector", "reject"]
    route_by: Literal["rule", "llm"]
    seeds: list[str]
    radius: int
    required_rels: list[list[str]]
    gap_rels: list[str]
    triples: list[dict]
    trace: list[dict]
    frontier: list[str]
    visited: list[str]
    reports: list[dict]
    context: str
    answer: str | None
    sources: list[str]
    decision: Literal["answer", "abstain"]
    abstain_reason: str | None
    llm_answer_called: bool
    stats: dict


def initial_state(question: str) -> RAGState:
    return {
        "question": question, "route": "reject", "route_by": "rule",
        "seeds": [], "radius": 0, "required_rels": [], "gap_rels": [],
        "triples": [], "trace": [], "frontier": [], "visited": [],
        "reports": [], "context": "", "answer": None, "sources": [],
        "decision": "abstain", "abstain_reason": None,
        "llm_answer_called": False, "stats": {},
    }


def relation_gap(state: dict) -> list[list[str]]:
    """required_rels 의 OR 그룹 중 하나도 확보하지 못한 그룹만 반환한다."""
    have = {t["r"] for t in state.get("triples", [])}
    gaps = []
    for group in state.get("required_rels", []):
        if not any(rel in have for rel in group):
            gaps.append(group)
    return gaps
