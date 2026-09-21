"""Streamlit 챗봇 데모. 질문 -> 자연어 답변, 각 턴 아래 경로/근거/동적 그래프/원문을 펼쳐 볼 수 있다.
   실행: streamlit run app.py"""
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import re
from pathlib import Path

import streamlit as st
import streamlit_agraph
from streamlit_agraph import Node, Edge, Config

import agent
import config_loader
import graph_io
import llm_factory

st.set_page_config(page_title="한국 대중음악 GraphRAG", layout="wide")

ROOT = Path(__file__).parent

# 실제 LLM 호출까지 끝까지 돌려 decision == "answer" 로 끝나는 것까지 확인한
# 문항만 예시로 쓴다. gap_rels 가 비어도(=그래프에서 관계 자체는 찾아도)
# 기권하는 경우가 있었다 - 예: "양현석이 설립한 기획사에 소속된 그룹은?"은
# 규칙 라우터가 SIGNED_TO·FOUNDED 를 둘 다 '양현석 근처에서 찾았는지'만
# 독립적으로 확인하고, 그 둘이 실제로 같은 회사를 거쳐 연결되는지는
# 확인하지 않는다. 그 결과 "양현석 SIGNED_TO YG"(양현석 자신이 그 소속
# 아티스트라는 별개 사실)까지 근거로 딸려 들어오고, 정작 'YG 소속 그룹'
# 노드는 하나도 못 찾은 채 두 조건만 만족한 것으로 통과해 버린다. LLM 은
# 이 근거로 실제 그룹 이름을 만들어낼 수 없으니 (올바르게) 기권한다 -
# 라우팅이 '두 관계가 같은 중간 노드를 거쳐 사슬로 이어지는지'까지는
# 검증하지 못하는 한계다. 3홉 이상 체인이나 그룹/시대(Era) 노드처럼
# 차수가 높은 허브를 반드시 거치는 질문도 허브 감점(degree_penalty)
# 때문에 기권하기 쉬워 제외했다 - output/failure_notes.md의 Q10/Q15 참고.
GOOD_EXAMPLES = [
    "서태지와 아이들의 멤버는 누구인가?",
    "빅뱅이 2008년에 리메이크한 '붉은 노을'의 원곡을 부른 가수는 누구인가?",
    "동방신기는 어느 기획사에 소속되어 있는가?",
    "빅뱅이 수상한 시상식은 어디인가?",
]


@st.cache_resource
def load_cfg():
    return config_loader.load(ROOT / "config.json")


@st.cache_resource
def load_graph():
    return graph_io.read_json(ROOT / "output" / "graph.json")


cfg = load_cfg()
g = load_graph()

TYPE_COLORS = {
    "Artist": "#4C78A8", "Group": "#F58518", "Album": "#54A24B", "Song": "#EECA3B",
    "Label": "#B279A2", "Award": "#FF9DA6", "Genre": "#9D755D", "Era": "#BAB0AC",
    "Program": "#72B7B2", "Unknown": "#CCCCCC",
}


@st.cache_resource
def load_name_to_type():
    return {d.get("name", n): d.get("type", "Unknown") for n, d in g.nodes(data=True)}


NAME_TO_TYPE = load_name_to_type()


def agraph_with_key(nodes, edges, config, key: str):
    """streamlit_agraph.agraph() 는 내부적으로 key 를 받는 컴포넌트를 감싸고도
       공개 함수에서 key 인자를 흘려보내지 않는다. 채팅 턴마다 그래프를 여러 개
       그리면 동일한 자동생성 ID로 StreamlitDuplicateElementId 가 난다(실측).
       원본 agraph() 와 동일한 본문에 key 만 추가해 턴별로 고유하게 만든다."""
    nodes_data = [n.to_dict() for n in nodes]
    edges_data = [e.to_dict() for e in edges]
    data_json = json.dumps({"nodes": nodes_data, "edges": edges_data})
    config_json = json.dumps(config.__dict__)
    return streamlit_agraph._agraph(data=data_json, config=config_json, key=key)


def _to_polite(sentence: str) -> str:
    """ANSWER_SYSTEM_PROMPT 에 존댓말 지시를 넣어도 LLM이 항상 따르지는
       않는다(실측: "이문세가 '붉은 노을'의 원곡을 불렀다." 처럼 반말이 섞여
       나옴). 화면에 보여주기 직전 결정적으로 보정한다 - '~다/~였다/~이다'로
       끝나는 문장을 '~습니다/~입니다'로 바꾼다. 이미 '~요'나 '~니다'로
       끝나면 손대지 않는다. 명사 나열처럼 '다'로 안 끝나는 문장은 그대로
       둔다(어색한 변환보다 무처리가 낫다)."""
    s = sentence.rstrip()
    trailing = ""
    if s and s[-1] in ".!?":
        trailing, s = s[-1], s[:-1]
    if re.search(r"(요|습니다|ㅂ니다)$", s):
        return sentence
    if s.endswith("이다"):
        s = s[:-2] + "입니다"
    elif s.endswith("다") and len(s) >= 2:
        s = s[:-1] + "습니다"
    else:
        return sentence
    return s + trailing


def natural_answer(state: dict) -> str:
    """state['answer']는 채점기(judge)가 파싱하기 좋도록 '답: .../경로: .../근거: ...'
       형식으로 나온다(agent.ANSWER_SYSTEM_PROMPT). '답:' 줄은 존댓말로 쓰도록
       프롬프트에 지시해 뒀다 - freeze_holdout.prompt_version()은 추출 프롬프트만
       해시하므로 이 프롬프트를 바꿔도 동결된 홀드아웃 지문에는 영향이 없다.
       화면에는 '답:' 줄만 보여주고, 경로·근거는 이미 아래 별도 섹션(순회
       경로/근거 삼중항)에서 보여준다."""
    if state["decision"] == "abstain":
        reason = state.get("abstain_reason")
        if reason == "out_of_scope":
            return "이 질문은 한국 대중음악(1992~현재) 주제를 벗어나 답변드릴 수 없어요."
        return "그래프에서 확인 가능한 근거가 부족해서, 추측 대신 답변을 보류할게요."
    m = re.search(r"답:\s*(.+)", state["answer"])
    text = m.group(1).split("\n")[0].strip() if m else state["answer"].strip()
    return _to_polite(text)


def parse_used_triples(answer_text: str) -> set[tuple[str, str, str]]:
    """ANSWER_SYSTEM_PROMPT 가 '근거: (h, r, t), ...' 형식을 강제하므로, 이 줄을
       파싱하면 탐색은 됐지만 최종 답변엔 인용되지 않은 삼중항과 실제로 답을
       뒷받침한 삼중항을 구분할 수 있다."""
    m = re.search(r"근거:\s*(.+)", answer_text, re.S)
    if not m:
        return set()
    used = set()
    for h, r, t in re.findall(r"\(([^,()]+),\s*([^,()]+),\s*([^()]+)\)", m.group(1)):
        used.add((h.strip(), r.strip(), t.strip()))
    return used


def render_graph(state: dict, key: str):
    """드래그·확대·물리 시뮬레이션이 되는 실제 인터랙티브 지식그래프(온톨로지)
       뷰다. 정적 이미지가 아니라 vis.js 캔버스를 그대로 내장한다(streamlit-agraph).
       노드는 스키마 타입별로 색을 칠하고, ANSWER_SYSTEM_PROMPT 가 강제하는
       '근거: (h, r, t), ...' 줄을 파싱해 실제로 답변에 인용된 노드·엣지만
       빨간 테두리/빨간 선으로 강조한다 — 탐색은 됐지만 답변엔 안 쓰인 나머지는
       옅게 표시해 구분한다."""
    triples = state["triples"]
    if not triples:
        st.caption("표시할 근거 삼중항이 없습니다.")
        return

    used = parse_used_triples(state["answer"]) if state["decision"] != "abstain" else set()
    seed_names = {g.nodes[s]["name"] for s in state.get("seeds", []) if s in g.nodes}

    node_ids = set()
    nodes, edges = [], []
    used_node_names = {h for h, r, t in used} | {t for h, r, t in used}
    for t in triples:
        for name in (t["h"], t["t"]):
            if name in node_ids:
                continue
            node_ids.add(name)
            node_type = NAME_TO_TYPE.get(name, "Unknown")
            is_seed = name in seed_names
            is_used_node = name in used_node_names
            # x/y/fixed는 시드 노드에만 넣는다 - 나머지에 x=None/y=None을
            # 명시적으로 넘기면 그대로 null이 직렬화되어 vis.js가 좌표를
            # NaN으로 계산해 캔버스 전체가 빈 화면으로 보이는 버그가 있었다(실측).
            extra = {"fixed": True, "x": 0, "y": 0} if is_seed else {}
            nodes.append(Node(
                id=name, label=name,
                size=20 if is_seed else (14 if is_used_node else 9),
                color=TYPE_COLORS.get(node_type, TYPE_COLORS["Unknown"]),
                borderWidth=4 if is_seed else (2 if is_used_node else 1),
                borderWidthSelected=5,
                font={"color": "#D62728" if is_used_node else "#666666", "size": 12},
                **extra,
            ))
        is_used_edge = (t["h"], t["r"], t["t"]) in used
        edges.append(Edge(
            source=t["h"], target=t["t"], label=t["r"],
            color="#D62728" if is_used_edge else "#D0D0D0",
            width=3 if is_used_edge else 1,
        ))

    st.caption(
        "🔴 굵은 빨간 테두리 = 질문의 시드 개체(화면 중앙 고정) · 빨간 선/글자 = 답변에 실제로 인용된 근거 · "
        "회색 = 탐색은 됐지만 최종 답변엔 안 쓰인 삼중항. "
        "노드를 드래그하거나 휠로 확대/축소할 수 있습니다."
    )
    legend_types = sorted({NAME_TO_TYPE.get(n, "Unknown") for n in node_ids})
    legend_html = " &nbsp;·&nbsp; ".join(
        f'<span style="color:{TYPE_COLORS.get(t, TYPE_COLORS["Unknown"])}">●</span> {t}'
        for t in legend_types
    )
    st.markdown(legend_html, unsafe_allow_html=True)

    # width="100%" 를 Config 에 그대로 넘기면 내부에서 f"{width}px" 로 조립돼
    # "100%px" 라는 무효 CSS 값이 되어 캔버스 크기 계산이 어긋난다(실측: 노드
    # 하나가 화면을 가득 채우는 버그) - 반드시 숫자(px)로만 넘긴다.
    config = Config(width=760, height=480, directed=True, physics=True,
                    hierarchical=False, collapsible=False)
    config.physics["stabilization"]["iterations"] = 300
    agraph_with_key(nodes, edges, config, key=key)


def render_turn_details(state: dict, key_prefix: str):
    tab1, tab2, tab3, tab4 = st.tabs(["지식그래프", "순회 경로", "근거 삼중항", "원문 문서"])

    with tab1:
        render_graph(state, key=f"graph_{key_prefix}")

    with tab2:
        if state["trace"]:
            by_hop: dict[int, list] = {}
            for t in state["trace"]:
                by_hop.setdefault(t["hop"], []).append(t)
            for hop in sorted(by_hop):
                st.markdown(f"**{hop}홉**")
                for t in by_hop[hop]:
                    arrow = "<-" if t["dir"] == "in" else "->"
                    st.text(f"{t['head']} {arrow}[{t['rel']}]{arrow} {t['tail']} "
                           f"(origin={t['origin']}, score={t['score']:.3f})")
        else:
            st.caption("탐색된 경로가 없습니다.")

    with tab3:
        if state["triples"]:
            st.dataframe(
                [{"h": t["h"], "relation": t["r"], "t": t["t"]} for t in state["triples"]],
                use_container_width=True,
            )
        else:
            st.caption("근거 삼중항이 없습니다.")

    with tab4:
        if state.get("sources"):
            for name in state["sources"][:5]:
                doc_path = ROOT / "data" / "docs" / f"{name}.md"
                with st.expander(name):
                    if doc_path.exists():
                        st.markdown(doc_path.read_text(encoding="utf-8")[:3000])
                    else:
                        st.caption("원문 파일을 찾지 못했습니다 (근거 개체가 곡/앨범 등 자체 문서가 없는 개체일 수 있습니다).")
        else:
            st.caption("표시할 출처 문서가 없습니다.")


# ---------- 사이드바 ----------
with st.sidebar:
    st.header("설정")
    provider = st.selectbox("답변 모델 프로바이더", ["openai", "google"], index=0)
    default_model = cfg["llm"]["profiles"]["answer"]["model"] if provider == "openai" else "gemini-3.8-flash"
    model_name = st.text_input("모델 이름", value=default_model)

    st.subheader("탐색 파라미터")
    max_radius = st.slider("max_radius (최대 홉)", 1, 4, 2)
    per_relation = st.slider("per_relation (관계별 예산)", 1, 30, cfg["retrieval"]["per_relation"])
    max_triples = st.slider("max_triples (전체 예산)", 20, 400, cfg["retrieval"]["max_triples"], step=20)
    hub_off = st.checkbox("허브 차단 끄기 (hub_degree_threshold=None)", value=False)

    st.subheader("그래프 통계")
    st.metric("노드", g.number_of_nodes())
    st.metric("간선", g.number_of_edges())
    bs_path = ROOT / "output" / "build_stats.json"
    if bs_path.exists():
        bs = json.loads(bs_path.read_text(encoding="utf-8"))
        st.caption(f"문서 {bs['docs']}건 · quote 통과율 {bs['quote']['quote_pass_rate']:.1%}")

    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.rerun()

# ---------- 메인: 챗봇 ----------
st.title("한국 대중음악 GraphRAG 에이전트 (1992~현재)")
st.caption("지식그래프 기반 질의응답 — 실제로 탄 경로와 근거 삼중항을 답변과 함께 보여줍니다.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


def run_question(question: str):
    run_cfg = {**cfg, "retrieval": {**cfg["retrieval"],
               "max_radius": max_radius, "per_relation": per_relation,
               "max_triples": max_triples,
               "hub_degree_threshold": None if hub_off else cfg["retrieval"]["hub_degree_threshold"]}}
    try:
        route_llm = llm_factory.get_llm("extract", cfg)
        answer_llm = llm_factory.get_llm("answer", cfg, override={"provider": provider, "model": model_name})
    except RuntimeError as e:
        st.session_state.messages.append({"role": "assistant", "content": f"설정 오류: {e}", "state": None})
        return
    state = agent.ask(question, g, run_cfg, route_llm=route_llm, answer_llm=answer_llm)
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.messages.append({"role": "assistant", "content": natural_answer(state), "state": state})


# 채팅 기록 렌더링
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant" and msg.get("state"):
            state = msg["state"]
            badge = "🟡 기권" if state["decision"] == "abstain" else "🟢 답변"
            st.caption(f"{badge} · 경로: {state['route']} (판정: {state['route_by']})")
            with st.expander("경로 · 근거 · 그래프 · 원문 보기"):
                render_turn_details(state, key_prefix=f"turn{i}")

# 예시 질문 (실제 평가에서 정답으로 확인된 문항만)
st.markdown("💡 **예시 질문**")
cols = st.columns(len(GOOD_EXAMPLES))
for col, ex in zip(cols, GOOD_EXAMPLES):
    if col.button(ex, key=f"ex_{ex}", use_container_width=True):
        st.session_state.pending_question = ex

typed = st.chat_input("질문을 입력하세요")
if typed:
    st.session_state.pending_question = typed

if st.session_state.pending_question:
    q = st.session_state.pending_question
    st.session_state.pending_question = None
    with st.spinner("그래프를 탐색하고 답변을 생성하는 중..."):
        run_question(q)
    st.rerun()
