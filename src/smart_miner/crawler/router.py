import re
from html.parser import HTMLParser
from typing import Any, Dict, List

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # The standard-library parser below is the fallback.
    BeautifulSoup = None

LOW_TEXT_DIVERSITY_THRESHOLD = 0.2
MIN_WORDS_FOR_DIVERSITY_CHECK = 20


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and data.strip():
            self.parts.append(data)


def _extract_visible_text(html: str) -> str:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        return soup.get_text(separator=" ", strip=True)

    parser = _VisibleTextParser()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def evaluate_content_quality(text: str, min_text_length: int = 600) -> Dict[str, Any]:
    """Return deterministic quality signals used by the routing decision."""
    if min_text_length < 0:
        raise ValueError("min_text_length must be non-negative")

    visible_character_count = len(text.strip())
    words = re.findall(r"\b[\w'-]+\b", text.casefold(), flags=re.UNICODE)
    word_count = len(words)
    unique_word_ratio = len(set(words)) / word_count if word_count else 0.0
    minimum_word_count = max(1, min_text_length // 12) if min_text_length else 0

    reason_codes: List[str] = []
    if visible_character_count < min_text_length:
        reason_codes.append("INSUFFICIENT_VISIBLE_TEXT")
    if word_count < minimum_word_count:
        reason_codes.append("INSUFFICIENT_WORD_COUNT")
    if (
        word_count >= MIN_WORDS_FOR_DIVERSITY_CHECK
        and unique_word_ratio < LOW_TEXT_DIVERSITY_THRESHOLD
    ):
        reason_codes.append("LOW_TEXT_DIVERSITY")

    return {
        "accepted": not reason_codes,
        "reason_codes": reason_codes,
        "visible_character_count": visible_character_count,
        "word_count": word_count,
        "unique_word_ratio": round(unique_word_ratio, 4),
    }


async def fetch_static(url: str) -> str:
    """Compatibility wrapper returning visible text."""
    from .fetcher import PageFetcher
    from .barriers import barrier_reason
    page = await PageFetcher().fetch_static(url)
    if barrier_reason(page) or page.status_code >= 400:
        raise ValueError("Page blocked or HTTP error")
    return _extract_visible_text(page.html)


async def fetch_dynamic(url: str) -> str:
    """Compatibility wrapper returning visible text."""
    from .fetcher import PageFetcher
    from .barriers import barrier_reason
    page = await PageFetcher().fetch_dynamic(url)
    if barrier_reason(page) or page.status_code >= 400:
        raise ValueError("Page blocked or HTTP error")
    return _extract_visible_text(page.html)


async def route(url: str, min_text_length: int = 600, *, wait_selector=None,
                browser_timeout_ms=30000) -> Dict[str, Any]:
    """v1.2 keys and plain text, plus reusable document and barrier status."""
    from .fetcher import PageFetcher
    if __package__ == "crawler":
        from pipeline.orchestrator import CrawlOrchestrator
    else:
        from ..pipeline.orchestrator import CrawlOrchestrator
    return await CrawlOrchestrator(PageFetcher(wait_selector, browser_timeout_ms)).run(
        url, min_text_length=min_text_length)
