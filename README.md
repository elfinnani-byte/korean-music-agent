# 한국 대중음악 GraphRAG 에이전트 (1992~현재)

한국어 위키백과에서 수집한 문서로 지식그래프를 구축하고, LangGraph 기반 에이전트가
그 그래프를 순회하며 질문에 답한다. 근거가 부족하면 추측 대신 기권한다.

자세한 설계 근거·측정 결과·한계는 [REPORT.md](REPORT.md)를 참고한다.

## 빠른 시작

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

`.env` 파일을 만들고 API 키를 넣는다 (`.env.example` 참고):

```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

그래프는 이미 `output/graph.json`에 빌드되어 있으므로 바로 데모를 실행할 수 있다.

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`이 열린다. 예시 질문 버튼을 누르면 바로
결과를 볼 수 있다. API 키가 없어도 그래프 로드·통계·예시 목록까지는 뜬다 —
실제 질의(라우팅 폴백·답변 생성)에만 키가 필요하다.

fork/clone 뒤 새 가상환경에서 위 순서 그대로 실행해 확인했다(`pip install` →
`pytest` 193개 통과 → `app.py` import 정상 — 아래 "실행 확인" 참고).

## 처음부터 다시 빌드하려면

```bash
python collect_docs.py      # 위키 문서 수집 (data/docs/*.md)
python build_graph.py       # 그래프 구축 (output/graph.json, build_stats.json)
python -m pytest            # 전체 테스트 (193개)
```

`evaluate.py`의 함수들(`evaluate_item`, `sweep`, `hop_summary_table` 등)로
평가를 재현할 수 있다. 실제 LLM 호출이 발생하므로 비용이 든다 — 자세한 절차는
REPORT.md 9절을 참고한다.

## 파일 구조

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

---

## 피어 리뷰 체크포인트

아래는 PRT(Peer Review Template)의 5개 항목과 이 저장소에서 확인할 수 있는
근거를 1:1로 연결한 것이다.

### 1. 실행 가능성

- 실행 결과: `output/runs.jsonl`(모든 질의 실행 로그), `output/eval.json` /
  `output/eval_holdout.json`(평가 결과), `screenshots/`(데모 캡처 2장)
- 직접 실행 확인: fork 없이 새 clone + 새 venv에서 `pip install -r
  requirements.txt` → `pytest`(193 passed) → `python -c "import app"`(키 없이도
  임포트 성공)까지 이 세션에서 직접 재현해 확인했다.
- 막힐 수 있는 지점: `.env` 없이 사이드바에서 실제 질의를 누르면
  `RuntimeError`로 어떤 키가 없는지 명시한다(추측성 크래시가 아니다).

### 2. 아키텍처 가독성

- 그래프 구조: REPORT.md 6절에 Mermaid 다이어그램. 노드 이름 자체가 역할을
  말한다 — `n_route`(라우팅) → `n_find_seeds`(시드 찾기) → `n_retrieve`(그래프
  홉 확장) → `n_build_context`(컨텍스트 조립) → `n_synthesize`(답변 생성),
  조건부로 `n_insufficient`(기권) / `n_global_map`·`n_global_reduce`(전역 검색).
- 왜 LangGraph `StateGraph`가 아니라 `ask()`(순수 함수)가 정본인가:
  `agent.py`의 `ask()` 자체가 이 이유를 주석으로 남겨 뒀다 — 조건 분기 로직을
  이중으로 유지하지 않기 위해서다. `build_graph_app()`은 같은 분기를 LangGraph
  어댑터로 감싸기만 한다.
- 궁금할 만한 부분: `edge_score()`의 `base * agreement * degree_penalty *
  priority` 4항 곱셈 — REPORT.md 7절에 각 항의 존재 이유가 있다.

### 3. 측정 가능성

- 숫자: REPORT.md 최상단 결과 요약표(노드/간선 수, quote 통과율, 홉수별
  재현율·생성 점수, BM25 대조, 튜닝/홀드아웃 격차, 기권 정확도).
- 측정 방법: `judging_rules.md`(채점 기준 원본), REPORT.md 9절(3계층 평가:
  색인→탐색→생성), 골든셋 25문항(`data/goldenset.json`, 튜닝 15 + 홀드아웃 10).
- 전/후 비교: (1) P7 파라미터 스윕 — `hub_degree_threshold=None`이 `=25`보다
  평균 재현율 0.326 대 0.295로 약간 높음(`output/sweep.json`, 108칸). (2) 튜닝
  대 홀드아웃 — 0.733 대 0.800(REPORT.md 9절). (3) 버그 수정 전/후 — 튜닝
  15문항을 실제로 재평가해 평균 0.667 → 0.733으로 올랐다(REPORT.md 9절
  "재평가: 전/후 비교"). **개선과 회귀를 함께 적는다**: 문항별로 뜯어보면
  진짜 개선 1건(Q22, 버그 수정으로 할루시네이션 없이 정답)과 진짜 회귀
  1건(Q02, 새로 드러난 한계)이 섞여 있고, 나머지 변동 다수는 코드 동작이
  아니라 `judge_repeats=1`의 채점 변동성이다 — 평균 숫자 하나만 보지 않고
  이 구분을 REPORT.md·`judging_rules.md`에 그대로 남겼다.

### 4. 견고성

- 에러 처리: `llm_factory.get_llm()`은 API 키가 없으면 어떤 프로바이더·어떤
  환경변수가 빠졌는지 한국어로 명시해 실패한다(추측성 크래시 대신). 빈 결과
  (시드 없음, 근거 없음)는 각각 `abstain_reason`이 있는 명시적 상태로
  귀결된다 — 예외를 삼키지 않는다.
- 폭주 방지: 그래프 탐색 루프(`run_retrieval`의 `while True`)는
  `max_radius`(기본 3)로 반드시 종료된다. 관계별 예산(`per_relation`)·전체
  예산(`max_triples`)·노드당 확장 상한(`per_node_out`)이 모두 있다. LLM
  호출에는 `request_timeout`(90초)·`max_retries`(3회)가 실제로 연결돼
  있다(방금 이 리뷰 준비 중 config에는 있지만 클라이언트에 전달되지 않던
  버그를 발견해 고쳤다 — `llm_factory.py`, TDD로 검증).
- 이상한 입력 테스트: 골든셋에 의도적 함정 3문항이 있다 — 도메인 밖 질문("오늘
  서울의 날씨는?"), 미래 시점 질문("NewJeans가 2030년에 발표한 음반은?"),
  답이 없는 비교 질문. 홀드아웃 실행에서 3/3 모두 정확히 기권했다(REPORT.md
  결과 요약표의 "기권 정확도").

### 5. 작업 추적성

- 커밋 히스토리가 작업 흔적이다 — 이 프로젝트는 별도 `CLAUDE.md` 없이 커밋
  메시지 자체에 원인·수정 근거를 적는 방식을 썼다. 예: `fix: run_retrieval()
  이 1홉째에 gap_rels 를 비워 둬 필수 관계 가산점이 무효화되던 버그`,
  `fix: config_hash 자기참조 모순 수정 + 홀드아웃 동결 재기록` — 각 커밋
  메시지에 "무엇을 어떻게 실측했고 왜 고쳤는지"가 들어 있다.
- 고친 부분 추적: `git log --oneline`으로 전체 흐름을 볼 수 있고,
  `output/failure_notes.md`는 실행 중 발견한 버그 7개(경로 재현율 계산,
  예산 절단 순서, "소속" 중의성, 1홉째 가산점 누락, 동결 지문 자기참조,
  LLM 타임아웃/재시도 미연결, 예산 면제 기준 누락)를 각각 원인·근거·수정
  여부까지 서술했고, 고치지 않고 한계로 남긴 것(`relation_gap()`의
  "하나만 찾아도 충분" 판정)도 숨기지 않았다.

## 한계

- 일부 다중홉 질문에서 그래프 허브(연결이 매우 많은 노드)로 가는 정당한 경로가
  감점 때문에 기권으로 이어지는 경우가 있다. 자세한 사례는
  `output/failure_notes.md`를 참고한다.
- 데모 사이드바에서 탐색 파라미터(반경·예산 등)를 조정할 수 있지만, 홀드아웃
  평가는 `config.json`에 동결된 값 하나로만 1회 실행했다.
- `relation_gap()`이 필요한 관계가 "어딘가에 하나라도 있으면" 충족으로
  판정한다 — `answer_type: set`처럼 정답이 여러 개인 질문(예: 그룹
  멤버 목록)에서 하나만 찾고도 탐색이 조기 종료될 수 있다. 재평가 중
  새로 발견했고, gap 판정 로직 자체를 바꿔야 하는 더 큰 작업이라
  v2 과제로 남겼다(REPORT.md 9절, `output/failure_notes.md` Q02).
