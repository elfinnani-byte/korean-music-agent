"""MediaWiki API 호출만 담당한다. 선별 로직은 collect_docs.py 에 있다."""
import time

import requests

API = "https://ko.wikipedia.org/w/api.php"


class RateLimited(RuntimeError):
    pass


class WikiClient:
    def __init__(self, session=None, delay_sec: float = 1.0,
                 max_attempts: int = 5, backoff_base: float = 2.0,
                 user_agent: str = "my-graph-agent/1.0 (educational project)"):
        self.session = session or requests.Session()
        self.delay_sec = delay_sec
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.user_agent = user_agent
        self.request_count = 0
        self.retry_count = 0

    def api(self, params: dict) -> dict:
        """0.3초 간격은 실제로 429 에 막힌 값이다. 기본 1.0초에
           지수 백오프와 Retry-After 존중을 더한다."""
        params = {**params, "format": "json", "formatversion": 2}
        for attempt in range(self.max_attempts):
            self.request_count += 1
            resp = self.session.get(
                API, params=params,
                headers={"User-Agent": self.user_agent}, timeout=30,
            )
            if resp.status_code == 200:
                if self.delay_sec:
                    time.sleep(self.delay_sec)
                return resp.json()
            if resp.status_code in (429, 503):
                self.retry_count += 1
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra else self.backoff_base ** (attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
        raise RateLimited(f"{self.max_attempts}회 재시도 후에도 실패: {params.get('titles')}")

    def resolve_title(self, title: str) -> str | None:
        """리다이렉트와 동음이의를 해소한다. 동음이의 문서면 None."""
        data = self.api({"action": "query", "titles": title,
                         "redirects": 1, "prop": "categories",
                         "clshow": "!hidden", "cllimit": 50})
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None
        page = pages[0]
        cats = [c["title"].removeprefix("분류:") for c in page.get("categories", [])]
        if any("동음이의" in c for c in cats):
            return None
        return page["title"]

    def links(self, title: str, limit: int = 300) -> list[str]:
        """본문 링크(ns=0). 틀에서 온 링크도 섞이므로 후보 상한으로만 쓴다."""
        out: list[str] = []
        cont: dict = {}
        while len(out) < limit:
            data = self.api({"action": "query", "titles": title, "prop": "links",
                             "plnamespace": 0, "pllimit": 500, **cont})
            pages = data.get("query", {}).get("pages", [])
            if not pages:
                break
            out += [l["title"] for l in pages[0].get("links", [])]
            if "continue" not in data:
                break
            cont = data["continue"]
        return out[:limit]

    def categories_bulk(self, titles: list[str]) -> dict[str, list[str]]:
        """분류는 20건씩 묶어 받을 수 있다. 본문보다 먼저 이것으로 거른다."""
        out: dict[str, list[str]] = {}
        for i in range(0, len(titles), 20):
            batch = titles[i:i + 20]
            data = self.api({"action": "query", "titles": "|".join(batch),
                             "prop": "categories", "clshow": "!hidden", "cllimit": 500})
            for page in data.get("query", {}).get("pages", []):
                out[page["title"]] = [
                    c["title"].removeprefix("분류:") for c in page.get("categories", [])
                ]
        return out

    def extract(self, title: str) -> str:
        """exlimit 이 1 이라 문서당 한 번씩 받아야 한다.
           여러 titles 를 주면 첫 문서 외에는 빈 문자열이 온다."""
        data = self.api({"action": "query", "titles": title,
                         "prop": "extracts", "explaintext": 1})
        pages = data.get("query", {}).get("pages", [])
        return pages[0].get("extract", "") if pages else ""
