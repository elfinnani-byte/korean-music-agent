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


import json
import re

import schema


def route_by_rule(question: str) -> tuple[str | None, str | None, list[list[str]] | None]:
    """규칙 1차 판정. 확신이 없으면 (None, None, None)을 반환해
       route_question() 이 LLM 폴백을 부르게 한다."""
    if any(h in question for h in schema.GLOBAL_HINTS):
        return "global", "rule", []
    if any(h in question for h in schema.VECTOR_HINTS):
        # 벡터 인덱스가 없어 path 로 강등한다. required_rels 를 비우는
        # 이유는 서술형 질의가 어떤 관계를 요구하는지 규칙으로 알 수
        # 없어서이고, 빈 required_rels 는 relation_gap() 에서 공백 없음으로
        # 처리돼 n_build_context 를 그대로 통과한다.
        return "path", "rule", []

    matched: list[list[str]] = []
    for pattern, rels in schema.CUE_TO_RELATIONS.items():
        if re.search(pattern, question):
            matched.append(rels)
    if not matched:
        return None, None, None
    route = "local" if len(matched) == 1 else "path"
    return route, "rule", matched


def _parse_route_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"라우터 LLM 응답에서 JSON 을 찾지 못함: {text[:200]}")
    return json.loads(m.group(0))


def route_question(question: str, cfg: dict, llm=None) -> RAGState:
    state = initial_state(question)
    route, by, rels = route_by_rule(question)
    if route is not None:
        state["route"], state["route_by"], state["required_rels"] = route, by, rels
        return state

    prompt = schema.ROUTE_LLM_PROMPT.format(
        relation_names=", ".join(schema.allowed_relationship_names()),
        question=question,
    )
    resp = llm.invoke(prompt)
    parsed = _parse_route_json(resp.content)
    state["route"] = parsed.get("route", "reject")
    state["route_by"] = "llm"
    state["required_rels"] = parsed.get("required_rels", [])
    return state


import normalize as nz


def find_seeds(g, question: str, cfg: dict, llm=None) -> list[str]:
    """정확매칭 -> 부분매칭 -> (0건일 때만) LLM.
       LLM 단계가 설계서의 '퍼지 매칭'을 겸한다 — 편집 거리 기반 문자열
       유사도 대신 LLM에게 질문에서 개체명을 직접 뽑게 하고, 뽑힌 문자열을
       다시 그래프에 정규화 대조한다. 한국어 조사·표기 변형(대소문자·
       띄어쓰기)에는 이쪽이 편집 거리보다 안정적이다."""
    max_seeds = cfg["retrieval"]["max_seeds"]

    exact = [nid for nid, d in g.nodes(data=True)
             if len(d["name"]) >= 2 and d["name"] in question]
    if exact:
        exact.sort(key=lambda nid: -len(g.nodes[nid]["name"]))
        return exact[:max_seeds]

    qnorm = nz.norm_key(question)
    partial = [nid for nid, d in g.nodes(data=True)
               if len(d["norm"]) >= 2 and d["norm"] in qnorm]
    if partial:
        partial.sort(key=lambda nid: -len(g.nodes[nid]["norm"]))
        return partial[:max_seeds]

    if llm is None:
        return []
    resp = llm.invoke(f"다음 질문에서 언급된 고유명사(인물·그룹·곡·앨범·회사)만 "
                       f"JSON으로 뽑아라. 형식: {{\"entities\": [\"...\"]}}\n\n질문: {question}")
    parsed = _parse_route_json(resp.content)
    found = []
    for ent in parsed.get("entities", []):
        ent_norm = nz.norm_key(ent)
        for nid, d in g.nodes(data=True):
            if d["norm"] == ent_norm and nid not in found:
                found.append(nid)
    return found[:max_seeds]


def is_hub(g, nid: str, threshold: int) -> bool:
    """허브 판정은 저장된 is_hub 속성이 아니라 그때그때 차수로 계산한다.
       graph.json 의 is_hub 는 빌드 시점 임계값(25)으로 굳어 있어, 스윕이
       다른 임계값을 시도해도 반영되지 않기 때문이다."""
    return g.degree(nid) > threshold


def edge_score(g, tail_id: str, edge: dict, state: dict, cfg: dict) -> float:
    origin_key = "+".join(sorted(edge["origins"])) if isinstance(edge.get("origins"), list) \
        else edge.get("origins", "llm")
    base = cfg["retrieval"]["origin_base_score"].get(origin_key, 0.8)
    exp = cfg["retrieval"]["degree_penalty_exponent"]
    pen = 1.0 / (1.0 + g.degree(tail_id) ** exp)
    rel = edge["relation"]
    if rel in state.get("gap_rels", []):
        prio = 1.3
    elif rel in schema.BRIDGE_RELATIONS:
        prio = 1.15
    else:
        prio = 1.0
    return base * edge["agreement"] * pen * prio
