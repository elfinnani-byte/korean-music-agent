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

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

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
    """지식그래프 뷰. streamlit-agraph(vis.js 임베드)로 먼저 만들었으나,
       expander+tabs 안에 접힌 채로 마운트되면 컴포넌트가 높이를 0으로
       측정해 버리고 나중에 펼쳐도 다시 재기 않는 문제를 실측으로 확인했다
       (그 과정에서 CSS 폭 값 오류·null 좌표 직렬화·key 미전달·vis-network
       옵션 오류까지 5개를 고쳤지만 이 마지막 문제는 컴포넌트 라이브러리
       자체의 마운트-시점 높이 감지 한계였다). 드래그는 못 하지만 확대/축소·
       호버가 되고 Streamlit 네이티브 위젯이라 탭/expander 안에서도 항상
       정상적으로 그려지는 Plotly로 바꿨다."""
    triples = state["triples"]
    if not triples:
        st.caption("표시할 근거 삼중항이 없습니다.")
        return

    used = parse_used_triples(state["answer"]) if state["decision"] != "abstain" else set()
    seed_names = {g.nodes[s]["name"] for s in state.get("seeds", []) if s in g.nodes}
    used_node_names = {h for h, r, t in used} | {t for h, r, t in used}

    nx_g = nx.DiGraph()
    for t in triples:
        nx_g.add_edge(t["h"], t["t"], relation=t["r"],
                      is_used=(t["h"], t["r"], t["t"]) in used)
    pos = nx.spring_layout(nx_g, seed=42, k=1.4 / max(len(nx_g.nodes()) ** 0.5, 1))

    used_edge_x, used_edge_y = [], []
    other_edge_x, other_edge_y = [], []
    mid_x, mid_y, mid_text = [], [], []
    for u, v, d in nx_g.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        target = (used_edge_x, used_edge_y) if d["is_used"] else (other_edge_x, other_edge_y)
        target[0].extend([x0, x1, None])
        target[1].extend([y0, y1, None])
        if d["is_used"]:
            mid_x.append((x0 + x1) / 2)
            mid_y.append((y0 + y1) / 2)
            mid_text.append(d["relation"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=other_edge_x, y=other_edge_y, mode="lines",
                             line=dict(width=1, color="#D0D0D0", dash="dot"),
                             hoverinfo="none", showlegend=False))
    fig.add_trace(go.Scatter(x=used_edge_x, y=used_edge_y, mode="lines",
                             line=dict(width=2.5, color="#D62728"),
                             hoverinfo="none", name="답변에 실제로 사용된 관계"))
    fig.add_trace(go.Scatter(x=mid_x, y=mid_y, mode="text", text=mid_text,
                             textfont=dict(size=10, color="#D62728"),
                             hoverinfo="none", showlegend=False))

    for node_type, color in TYPE_COLORS.items():
        xs, ys, labels, sizes, line_widths, line_colors = [], [], [], [], [], []
        for n in nx_g.nodes():
            if NAME_TO_TYPE.get(n, "Unknown") != node_type:
                continue
            x, y = pos[n]
            xs.append(x); ys.append(y); labels.append(n)
            is_seed = n in seed_names
            sizes.append(28 if is_seed else (20 if n in used_node_names else 14))
            line_widths.append(3 if is_seed else 1)
            line_colors.append("#D62728" if is_seed else "#FFFFFF")
        if not xs:
            continue
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text", text=labels, textposition="top center",
            textfont=dict(size=10),
            marker=dict(size=sizes, color=color, line=dict(width=line_widths, color=line_colors)),
            name=node_type,
        ))

    fig.update_layout(
        title=f"노드 {nx_g.number_of_nodes()}개 · 엣지 {nx_g.number_of_edges()}개 · "
              f"굵은 빨간 테두리=시드 · 빨간 선=답변에 사용된 근거",
        showlegend=True, height=480, margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
    )
    st.plotly_chart(fig, use_container_width=True, key=key)


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
