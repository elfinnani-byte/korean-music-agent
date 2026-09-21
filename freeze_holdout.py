"""홀드아웃 동결 지문 계산·검증. 플래그가 아니라 해시로 동결을 증명한다."""
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import extract_llm


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _config_hash(path: Path) -> str:
    """config.json 의 eval.holdout 필드를 제외하고 해시한다. 이 필드
       자체가 지문(이 함수의 결과)을 담는 자리라, 포함해서 해시하면
       지문을 config.json 에 써넣는 순간 파일이 바뀌어 스스로도 검증을
       통과 못하는 자기참조 모순이 생긴다(실측)."""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(cfg.get("eval"), dict) and "holdout" in cfg["eval"]:
        cfg["eval"]["holdout"] = None
    canonical = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_fingerprint(config_path: Path, goldenset_path: Path, graph_path: Path,
                        commit_hash: str) -> dict:
    kst = timezone(timedelta(hours=9))
    return {
        "frozen": True,
        "frozen_at": datetime.now(kst).isoformat(),
        "freeze_commit": commit_hash,
        "config_hash": _config_hash(config_path),
        "schema_version": extract_llm.schema_version(),
        "prompt_version": extract_llm.prompt_version(),
        "goldenset_hash": _sha256_file(goldenset_path),
        "graph_hash": _sha256_file(graph_path),
    }


def verify_fingerprint(frozen: dict, config_path: Path, goldenset_path: Path,
                       graph_path: Path) -> tuple[bool, list[str]]:
    """evaluate.py 가 홀드아웃을 돌리기 전에 부른다. 하나라도 어긋나면
       실행을 거부하고 무엇이 달라졌는지 출력한다."""
    problems = []
    current = {
        "config_hash": _config_hash(config_path),
        "goldenset_hash": _sha256_file(goldenset_path),
        "graph_hash": _sha256_file(graph_path),
        "schema_version": extract_llm.schema_version(),
        "prompt_version": extract_llm.prompt_version(),
    }
    for key, cur_val in current.items():
        if frozen.get(key) != cur_val:
            problems.append(f"{key} 불일치: 동결={frozen.get(key)} 현재={cur_val}")
    return not problems, problems
