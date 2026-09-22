# 한국 대중음악 GraphRAG 에이전트 (1992~현재)

한국어 위키백과로 지식그래프를 만들고, LangGraph 에이전트가 그 그래프를 직접 순회해 질문에 답한다. 근거가 부족하면 추측 대신 기권한다.

---

## 📌 목차 (Table of Contents)
- [프로젝트 소개](#-프로젝트-소개)
- [주요 기능](#-주요-기능)
- [시작하기 (Getting Started)](#-시작하기-getting-started)
- [사용법 (Usage)](#-사용법-usage)
- [기술 Stack](#-기술-stack)
- [기여하기 (Contributing)](#-기여하기-contributing)
- [라이선스 (License)](#-라이선스-license)

---

## 📖 프로젝트 소개

일반적인 RAG는 원문 청크를 검색해 근거로 쓴다. 이 프로젝트는 그 대신 **지식그래프를 직접 만들고, 에이전트가 그 그래프를 홉 단위로 순회하며 답을 찾는다** — "A가 세운 회사에 소속된 B는 누구인가?" 같은 다중홉 질문에서 원문 검색만으로는 놓치기 쉬운 관계를 그래프 경로로 명시적으로 추적하기 위해서다.

도메인은 한국 대중음악, 1992년(서태지와 아이들 데뷔) 이후로 좁혔다 — 위키 문서 밀도를 실측해 본 결과, 더 이른 시기까지 다루면 그래프가 시대별로 끊어진 섬이 되기 때문이다. 위키 문서 52건에서 노드 1,683개·간선 2,402개짜리 그래프를 만들고, 이 그래프를 LangGraph 기반 에이전트가 순회한다.

가장 신경 쓴 부분은 **환각 방지**다. 그래프에서 필요한 관계를 못 찾으면 LLM을 아예 호출하지 않고 기권하고(비용 0), 답변 생성 프롬프트에도 근거 밖 고유명사 사용을 금지해 이중으로 막는다. 이 판단이 실제로 맞았는지는 색인·탐색·생성 3계층으로 나눠 측정하고, 별도로 떼어 둔 홀드아웃 10문항으로 1회만 검증했다(재평가로 파라미터를 다시 튜닝하면 검증 의미가 없어지므로, 결과가 낮게 나와도 다시 건드리지 않는 게 원칙이다).

Aiffel AI Agent 과정 실습 과제로 만들었다. 자세한 설계 근거·측정 결과·한계는 [REPORT.md](REPORT.md)에 있다.

## ✨ 주요 기능

- [x] 위키 문서 자동 수집 + 규칙·정규식·LLM 3원 추출로 지식그래프 구축
- [x] LangGraph 에이전트가 반경·예산·허브 회피 규칙을 지키며 그래프를 순회해 답변 생성
- [x] 근거 부족 시 추측 대신 기권 (코드층·프롬프트층 2중 방어)
- [x] 3계층 평가(색인 → 탐색 → 생성) + BM25 베이스라인 대조 + 튜닝/홀드아웃 분리 검증
- [x] Streamlit 챗봇 데모 — 자연어 답변, 순회 경로, 근거 삼중항 표, 인터랙티브 지식그래프 시각화

## 🚀 시작하기 (Getting Started)

### Prerequisites (사전 준비)
- Python 3.11 이상 (개발·테스트는 3.14 기준)
- OpenAI API 키 (필수), Google (Gemini) API 키 (선택 — 없어도 OpenAI만으로 전부 동작)

### Installation (설치 방법)
```bash
# 레포지토리 클론
git clone https://github.com/elfinnani-byte/korean-music-agent.git

# 프로젝트 디렉터리 이동
cd korean-music-agent

# 가상환경 생성 및 활성화
python -m venv .venv
.venv\Scripts\activate          # Windows

# 패키지 설치
pip install -r requirements.txt
```

`.env` 파일을 만들고 API 키를 넣는다 (`.env.example` 참고):
```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

## 💡 사용법 (Usage)

그래프는 이미 `output/graph.json`에 빌드되어 있으므로 바로 데모를 실행할 수 있다.

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`이 열린다. 예시 질문 버튼을 누르면 바로 결과를 볼 수 있다. API 키가 없어도 그래프 로드·통계·예시 목록까지는 뜬다 — 실제 질의(라우팅 폴백·답변 생성)에만 키가 필요하다.

처음부터 다시 빌드하거나 평가를 재현하려면:

```bash
python collect_docs.py      # 위키 문서 수집 (data/docs/*.md)
python build_graph.py       # 그래프 구축 (output/graph.json, build_stats.json)
python -m pytest            # 전체 테스트 (193개)
```

`evaluate.py`의 함수들(`evaluate_item`, `sweep`, `hop_summary_table` 등)로 평가를 재현할 수 있다. 실제 LLM 호출이 발생하므로 비용이 든다 — 자세한 절차는 [REPORT.md](REPORT.md) 9절을 참고한다.

### 파일 구조

```
config.json         프로바이더·모델·탐색 파라미터·평가 설정
schema.py            노드/관계 스키마, 정규화 규칙, 프롬프트
llm_factory.py        LLM 프로바이더 팩토리 (타임아웃·재시도 포함)
normalize.py          개체명 정규화
wiki_client.py, tracklist.py, rules.py   수집·추출 보조 모듈
collect_docs.py        위키 문서 수집
build_graph.py          그래프 구축 파이프라인
agent.py                 LangGraph 에이전트 (ask() 가 최종 진입점)
evaluate.py               평가 파이프라인 (3계층: 색인/탐색/생성)
community.py               커뮤니티 탐지 + 전역 검색 리포트 (선택 확장)
freeze_holdout.py           홀드아웃 동결 지문 계산·검증
app.py                       Streamlit 챗봇 데모
data/                          문서(docs/*.md), 골든셋, 매니페스트
output/                        그래프, 빌드/평가 결과, 실행 로그(runs.jsonl)
tests/                         pytest 테스트 193개
```

## 🛠 기술 Stack

- **에이전트**: LangGraph, LangChain (OpenAI GPT-4.1 / Google Gemini)
- **그래프**: NetworkX
- **검색 대조군**: rank-bm25, kiwipiepy (한국어 형태소 분석)
- **데모**: Streamlit, Plotly (인터랙티브 그래프 시각화)
- **평가·테스트**: pytest (193개), LLM-judge 기반 3계층 평가

## 🤝 기여하기 (Contributing)

개인 학습 과제로 시작한 프로젝트지만, 개선 제안이나 버그 리포트는 언제든 환영한다.

1. 이 레포지토리를 Fork 합니다.
2. 새 브랜치를 생성합니다 (`git checkout -b feature/amazing-feature`).
3. 변경사항을 Commit 합니다 (`git commit -m 'Add some amazing feature'`).
4. 브랜치에 Push 합니다 (`git push origin feature/amazing-feature`).
5. Pull Request를 오픈합니다.

## 📄 라이선스 (License)

별도 라이선스가 아직 지정되지 않았다. 재사용하고 싶다면 이슈로 문의해 달라.

## 한계

- 일부 다중홉 질문에서 그래프 허브(연결이 매우 많은 노드)로 가는 정당한 경로가 감점 때문에 기권으로 이어지는 경우가 있다. 자세한 사례는 `output/failure_notes.md`를 참고한다.
- 데모 사이드바에서 탐색 파라미터(반경·예산 등)를 조정할 수 있지만, 홀드아웃 평가는 `config.json`에 동결된 값 하나로만 1회 실행했다.
- `relation_gap()`이 필요한 관계가 "어딘가에 하나라도 있으면" 충족으로 판정한다 — `answer_type: set`처럼 정답이 여러 개인 질문(예: 그룹 멤버 목록)에서 하나만 찾고도 탐색이 조기 종료될 수 있다. 재평가 중 새로 발견했고, gap 판정 로직 자체를 바꿔야 하는 더 큰 작업이라 v2 과제로 남겼다(REPORT.md 9절, `output/failure_notes.md` Q02).
