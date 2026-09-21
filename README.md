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

브라우저에서 `http://localhost:8501`이 열린다. 사이드바 아래 예시 질문 버튼을
누르면 바로 결과를 볼 수 있다.

## 처음부터 다시 빌드하려면

```bash
python collect_docs.py      # 위키 문서 수집 (data/docs/*.md)
python build_graph.py       # 그래프 구축 (output/graph.json, build_stats.json)
python -m pytest            # 전체 테스트 (190개)
```

`evaluate.py`의 함수들(`evaluate_item`, `sweep`, `hop_summary_table` 등)로
평가를 재현할 수 있다. 실제 LLM 호출이 발생하므로 비용이 든다 — 자세한 절차는
REPORT.md 9절을 참고한다.

## 파일 구조

```
config.json         프로바이더·모델·탐색 파라미터·평가 설정
schema.py            노드/관계 스키마, 정규화 규칙, 프롬프트
llm_factory.py        LLM 프로바이더 팩토리
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
tests/                         pytest 테스트 190개
```

## 한계

- 일부 다중홉 질문에서 그래프 허브(연결이 매우 많은 노드)로 가는 정당한 경로가
  감점 때문에 기권으로 이어지는 경우가 있다. 자세한 사례는
  `output/failure_notes.md`를 참고한다.
- 데모 사이드바에서 탐색 파라미터(반경·예산 등)를 조정할 수 있지만, 홀드아웃
  평가는 `config.json`에 동결된 값 하나로만 1회 실행했다.
