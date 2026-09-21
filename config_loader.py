"""config.json 을 읽고 schema.py 와 어긋나지 않는지 검사한다."""
import json
from pathlib import Path

import schema

CONFIG_PATH = Path(__file__).parent / "config.json"


def load(path: Path | None = None) -> dict:
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate(cfg: dict) -> None:
    """config 가 스키마에 없는 이름을 쓰고 있지 않은지 본다.
       두 곳에서 사람이 따로 고치다 어긋나는 것을 여기서 잡는다."""
    schema.validate()

    known = set(schema.allowed_relationship_names())
    for rel in cfg["retrieval"]["quota_exempt_relations"]:
        if rel not in known:
            raise ValueError(f"config 의 quota_exempt_relations 에 없는 관계: {rel}")

    if cfg["scope"]["eras"] != schema.ERAS:
        raise ValueError("config 의 eras 가 schema.ERAS 와 다르다")
    if cfg["scope"]["quota_eras"] != schema.QUOTA_ERAS:
        raise ValueError("config 의 quota_eras 가 schema.QUOTA_ERAS 와 다르다")

    for name, ntype in cfg["normalize"]["entity_type_overrides"].items():
        if ntype not in schema.NODE_TYPES:
            raise ValueError(f"entity_type_overrides 의 알 수 없는 타입: {name} -> {ntype}")

    origin_keys = set(cfg["retrieval"]["origin_base_score"])
    if "rule+llm" in origin_keys:
        raise ValueError(
            "origin_base_score 키는 알파벳 정렬 결합('llm+rule')이어야 한다. "
            "build_stats.json 의 edges_by_origin 이 그렇게 키를 만든다"
        )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    c = load()
    validate(c)
    print("config 검증 통과")
    print("  시드:", len(c["collect"]["seed_titles"]), "건")
    print("  관계:", len(schema.allowed_relationship_names()), "종 /",
          len(schema.REL_TRIPLES), "튜플")
