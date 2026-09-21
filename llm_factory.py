"""프로바이더 팩토리. config 는 어떤 모델을 쓸지만 정하고 키는 .env 에서 온다."""
import importlib
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDERS = {
    "openai": ("langchain_openai", "ChatOpenAI"),
    "google": ("langchain_google_genai", "ChatGoogleGenerativeAI"),
    "anthropic": ("langchain_anthropic", "ChatAnthropic"),
}


def get_llm(profile: str, cfg: dict, override: dict | None = None):
    spec = {**cfg["llm"]["profiles"][profile], **(override or {})}
    provider = spec["provider"]
    env_key = cfg["llm"]["env_keys"][provider]
    if not os.getenv(env_key):
        raise RuntimeError(
            f"[{profile}] {provider} 를 쓰려면 .env 에 {env_key} 가 필요합니다."
        )
    mod, cls = PROVIDERS[provider]
    Chat = getattr(importlib.import_module(mod), cls)
    kwargs = {"model": spec["model"], "temperature": spec["temperature"]}
    if "max_tokens" in spec:
        # 프로바이더별 파라미터 이름 차이를 여기서 흡수한다
        key = "max_output_tokens" if provider == "google" else "max_tokens"
        kwargs[key] = spec["max_tokens"]
    return Chat(**kwargs)


def extract_text(resp) -> str:
    """resp.content 를 항상 평범한 문자열로 돌려준다.
       OpenAI 는 content 가 문자열이지만, Google(gemini-3.8-flash 등)은
       [{'type':'text','text':'...', 'extras':{...}}] 같은 콘텐츠 블록
       리스트로 돌려줄 때가 있다(실측: P8 평가 실행 중 TypeError 로
       처음 드러남). 텍스트가 아닌 블록(예: 'thinking')은 건너뛴다."""
    content = resp.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def provider_status(cfg: dict, ping: bool = True) -> dict[str, str]:
    """absent | configured | available | failed
       키 문자열이 있는 것과 실제로 호출되는 것은 다르다. 오타 난 키를
       정상으로 노출하지 않기 위해 상태를 나눈다."""
    out: dict[str, str] = {}
    for provider, env_key in cfg["llm"]["env_keys"].items():
        if not os.getenv(env_key):
            out[provider] = "absent"
            continue
        if not ping:
            out[provider] = "configured"
            continue
        try:
            profile = next(
                p for p, s in cfg["llm"]["profiles"].items() if s["provider"] == provider
            )
            get_llm(profile, cfg).invoke("안녕")
            out[provider] = "available"
        except Exception:
            out[provider] = "failed"
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    import config_loader
    cfg = config_loader.load()
    for provider, state in provider_status(cfg).items():
        print(f"{provider}: {state}")
