"""Run the cleaner and a fake schema extraction without network or API keys."""

import asyncio
from pathlib import Path

from pydantic import BaseModel

from smart_miner import DocumentCleaner, StructuredExtractor
from smart_miner.crawler.fetcher import FetchedPage


class ExampleSummary(BaseModel):
    headline: str


async def mock_generate(clean_text: str) -> dict:
    return {"headline": "Catalog"}


async def main() -> None:
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/static.html"
    page = FetchedPage(fixture.read_text(encoding="utf-8"),
                       "https://example.test/catalog/")
    document = DocumentCleaner().clean(page)
    print(document.markdown)
    summary = await StructuredExtractor(mock_generate, ExampleSummary).extract(document)
    print("\nValidated offline output:", summary.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
