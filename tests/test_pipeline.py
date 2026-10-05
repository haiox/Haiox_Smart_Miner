import unittest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel, ValidationError
from smart_miner.crawler.fetcher import FetchedPage, PageFetcher
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.pipeline.extractor import StructuredExtractor
from smart_miner.pipeline.orchestrator import CrawlOrchestrator

FIXTURES = Path(__file__).parent / "fixtures"


class Items(BaseModel):
    count: int


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def page(self, name="static.html", status=200):
        return FetchedPage((FIXTURES / name).read_text(encoding="utf-8"),
                           "https://example.test/catalog/", status)

    def test_clean_structure_links_jsonld_and_sizes(self):
        page = self.page()
        doc = DocumentCleaner().clean(page)
        self.assertIn("# Catalog", doc.markdown)
        self.assertIn("https://example.test/item/1", doc.markdown)
        self.assertIn("| Name | Price |", doc.markdown)
        self.assertIn("| Laptop | 12 |", doc.markdown)
        self.assertNotIn("trackingNoise", doc.extraction_text())
        self.assertEqual(doc.json_ld[0]["@type"], "Product")
        self.assertEqual(doc.input_character_count, len(page.html))
        self.assertEqual(doc.output_character_count, len(doc.extraction_text()))
        self.assertEqual(doc.markdown.count("Navigation"), 1)
        self.assertEqual(CleanDocument.model_validate_json(doc.model_dump_json()), doc)

    def test_demo_cleaner_prefers_article_over_navigation(self):
        page = FetchedPage(
            '<title>News</title><nav>menu noise</nav><article>'
            '<h1>Headline</h1><p>' + ('Article detail. ' * 30) +
            '</p></article><footer>footer noise</footer>',
            'https://example.test/story')
        doc = DocumentCleaner(prefer_main=True).clean(page)
        self.assertIn('Article detail.', doc.markdown)
        self.assertNotIn('menu noise', doc.markdown)
        self.assertEqual(doc.title, 'News')

    def test_script_heavy_main_does_not_hide_real_body(self):
        page = FetchedPage(
            '<main><script>' + ('placeholder data ' * 40) + '</script></main>'
            '<section><h1>Actual content</h1><p>' + ('Useful page text. ' * 30) +
            '</p></section>', 'https://example.test/')
        doc = DocumentCleaner(prefer_main=True).clean(page)
        self.assertIn('Useful page text.', doc.markdown)

    def test_structured_data_recovers_js_shell_with_clear_provenance(self):
        page = FetchedPage(
            '<title>Example</title><main><script>loading</script></main>'
            '<script type="application/ld+json">'
            '{"@graph":[{"@type":"WebPage","description":"' +
            ('Source-provided description. ' * 15) + '"}]}'
            '</script>', 'https://example.test/')
        doc = DocumentCleaner(prefer_main=True).clean(page)
        self.assertIn('Structured data supplied by the website', doc.markdown)
        self.assertIn('STRUCTURED_DATA_FALLBACK', doc.warnings)
        initial = DocumentCleaner(prefer_main=True).clean(
            page, structured_fallback=False)
        self.assertNotIn('STRUCTURED_DATA_FALLBACK', initial.warnings)
        self.assertEqual(initial.markdown, '')

    def test_cookie_notice_uses_richer_source_metadata(self):
        page = FetchedPage(
            '<div>This website uses cookies. Cookie Settings Accept All</div>'
            '<script type="application/ld+json">'
            '{"@graph":[{"@type":"FAQPage","mainEntity":[{'
            '"@type":"Question","name":"What does it do?",'
            '"acceptedAnswer":{"@type":"Answer","text":"' +
            ('Source answer about the service. ' * 20) + '"}}]}]}'
            '</script>', 'https://example.test/')
        doc = DocumentCleaner(prefer_main=True).clean(page)
        self.assertIn('What does it do?', doc.markdown)
        self.assertNotIn('Cookie Settings', doc.markdown)
        self.assertIn('STRUCTURED_DATA_FALLBACK', doc.warnings)

    def test_merged_cells_and_repeated_rows_preserved(self):
        page = FetchedPage('<table><tr><th colspan="2">Group</th></tr>'
                           '<tr><td>A</td><td>1</td></tr><tr><td>A</td><td>1</td></tr></table>',
                           'https://example.test')
        doc = DocumentCleaner().clean(page)
        self.assertIn('colspan="2"', doc.markdown)
        self.assertEqual(doc.markdown.count('<td>A</td>'), 2)

    def test_literal_pipe_does_not_create_an_extra_column(self):
        doc = DocumentCleaner().clean(FetchedPage(
            '<table><tr><th>Name</th><th>Value</th></tr>'
            '<tr><td>A|B</td><td>3</td></tr></table>', 'https://example.test'))
        self.assertIn('<td>A|B</td><td>3</td>', doc.markdown)

    async def test_reextract_without_fetch_and_schema_validation(self):
        fetcher = MagicMock()
        fetcher.fetch_static = AsyncMock(return_value=self.page())
        generate = AsyncMock(return_value='{"count": 2}')
        extractor = StructuredExtractor(generate, Items)
        result = await CrawlOrchestrator(fetcher).run('https://example.test', 0, extractor)
        self.assertTrue(result['success'])
        doc = CleanDocument.model_validate(result['document'])
        self.assertEqual((await extractor.extract(doc)).count, 2)
        fetcher.fetch_static.assert_awaited_once()
        self.assertEqual(generate.await_count, 2)
        self.assertNotIn('<script', generate.call_args.args[0])
        generate.return_value = '{"count": "invalid"}'
        with self.assertRaises(ValidationError):
            await extractor.extract(doc)

    async def test_blocked_never_calls_llm_or_browser(self):
        for status in (200, 403):
            fetcher = MagicMock()
            fetcher.fetch_static = AsyncMock(return_value=self.page('blocked.html', status))
            fetcher.fetch_dynamic = AsyncMock()
            extractor = MagicMock(extract=AsyncMock())
            result = await CrawlOrchestrator(fetcher).run('https://example.test', extractor=extractor)
            self.assertFalse(result['success'])
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(result['text'], '')
            self.assertIsNone(result['document'])
            extractor.extract.assert_not_awaited()
            fetcher.fetch_dynamic.assert_not_awaited()

    async def test_soft_404_with_http_200_never_calls_llm(self):
        fetcher = MagicMock()
        fetcher.fetch_static = AsyncMock(return_value=self.page('soft_404.html'))
        fetcher.fetch_dynamic = AsyncMock()
        extractor = MagicMock(extract=AsyncMock())
        result = await CrawlOrchestrator(fetcher).run(
            'https://example.test/missing', min_text_length=300,
            extractor=extractor, require_clean_content=True,
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['routing']['reason_codes'], ['SOFT_ERROR_PAGE'])
        self.assertIsNone(result['document'])
        extractor.extract.assert_not_awaited()
        fetcher.fetch_dynamic.assert_not_awaited()

    def test_article_about_404_is_not_a_soft_error(self):
        page = FetchedPage(
            '<title>Understanding 404 errors</title>'
            '<h1>How websites handle a 404 response</h1>'
            '<p>This article explains HTTP errors.</p>',
            'https://example.test/article', 200,
        )
        document = DocumentCleaner().clean(page)
        self.assertIn('HTTP errors', document.markdown)

    async def test_dynamic_barrier_and_plain_http_failure(self):
        fetcher = MagicMock(fetch_static=AsyncMock(return_value=FetchedPage('short', 'https://example.test')),
                            fetch_dynamic=AsyncMock(return_value=self.page('blocked.html')))
        generate = AsyncMock()
        result = await CrawlOrchestrator(fetcher).run('https://example.test', extractor=StructuredExtractor(generate, Items))
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(result['routing']['fallback_used'])
        generate.assert_not_awaited()
        fetcher.fetch_static.return_value = FetchedPage('server failure', 'https://example.test', 500)
        result = await CrawlOrchestrator(fetcher).run('https://example.test')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['routing']['reason_codes'], ['HTTP_STATUS_500'])

    async def test_fetch_failures_have_safe_specific_reasons(self):
        fetcher = MagicMock(fetch_static=AsyncMock(side_effect=ValueError('PAGE_TOO_LARGE')))
        result = await CrawlOrchestrator(fetcher).run('https://example.test')
        self.assertEqual(result['routing']['reason_codes'], ['PAGE_TOO_LARGE'])
        fetcher.fetch_static.side_effect = httpx.ReadTimeout('private URL must not leak')
        result = await CrawlOrchestrator(fetcher).run('https://example.test')
        self.assertEqual(result['routing']['reason_codes'], ['FETCH_TIMEOUT'])
        self.assertNotIn('private URL', str(result))

    async def test_forced_browser_skips_static_fetch(self):
        fetcher = MagicMock(fetch_static=AsyncMock(),
                            fetch_dynamic=AsyncMock(return_value=self.page()))
        result = await CrawlOrchestrator(fetcher).run(
            'https://example.test', force_dynamic=True)
        self.assertTrue(result['success'])
        self.assertEqual(result['routing']['strategy'], 'dynamic')
        fetcher.fetch_static.assert_not_awaited()
        fetcher.fetch_dynamic.assert_awaited_once()

    async def test_empty_cleaned_static_falls_back_instead_of_claiming_success(self):
        shell = FetchedPage('<main><script>' + ('fake words ' * 80) +
                            '</script></main>', 'https://example.test/')
        real = FetchedPage('<main><h1>Loaded</h1><p>' +
                           ' '.join(f'Content item{i} explains detail{i}.'
                                    for i in range(40)) + '</p></main>',
                           'https://example.test/')
        fetcher = MagicMock(fetch_static=AsyncMock(return_value=shell),
                            fetch_dynamic=AsyncMock(return_value=real))
        result = await CrawlOrchestrator(
            fetcher, cleaner=DocumentCleaner(prefer_main=True)).run(
                'https://example.test/', min_text_length=300,
                require_clean_content=True)
        self.assertTrue(result['success'])
        self.assertEqual(result['routing']['strategy'], 'dynamic')
        self.assertIn('Content item0 explains detail0.', result['document']['markdown'])

    async def test_metadata_is_used_only_after_automatic_browser_attempt(self):
        source = FetchedPage(
            '<main><script>app shell</script></main>'
            '<script type="application/ld+json">'
            '{"@type":"WebPage","description":"' +
            ('Source description. ' * 30) + '"}'
            '</script>', 'https://example.test/')
        cookie = FetchedPage(
            '<div>This website uses cookies. Cookie Settings Accept All</div>',
            'https://example.test/')
        fetcher = MagicMock(fetch_static=AsyncMock(return_value=source),
                            fetch_dynamic=AsyncMock(return_value=cookie))
        result = await CrawlOrchestrator(
            fetcher, cleaner=DocumentCleaner(prefer_main=True)).run(
                'https://example.test/', min_text_length=300,
                require_clean_content=True)
        self.assertTrue(result['success'])
        self.assertEqual(result['routing']['strategy'], 'metadata')
        self.assertTrue(result['routing']['browser_attempted'])
        self.assertIn('Source description.', result['document']['markdown'])
        fetcher.fetch_dynamic.assert_awaited_once()

    def test_captcha_article_is_not_automatically_blocked(self):
        doc = DocumentCleaner().clean(FetchedPage('<h1>How CAPTCHA works</h1><p>A technical article.</p>', 'https://example.test'))
        self.assertIn('CAPTCHA', doc.markdown)

    def test_base_lists_invalid_jsonld_hidden_and_unsafe_links(self):
        page = FetchedPage('<head><base href="/docs/"></head><h2>Guide</h2>'
                           '<ul><li><a href="page">Read</a></li></ul>'
                           '<p hidden>secret fixture text</p><a href="javascript:bad()">Bad</a>'
                           '<script type="application/ld+json">invalid</script>',
                           'https://example.test/redirected/')
        doc = DocumentCleaner().clean(page)
        self.assertIn('## Guide', doc.markdown)
        self.assertIn('https://example.test/docs/page', doc.markdown)
        self.assertNotIn('secret fixture text', doc.extraction_text())
        self.assertNotIn('javascript:', doc.markdown)
        self.assertEqual(doc.warnings, ['INVALID_JSON_LD'])

    async def test_failed_extraction_keeps_reusable_document(self):
        fetcher = MagicMock(fetch_static=AsyncMock(return_value=self.page()))
        extractor = StructuredExtractor(AsyncMock(return_value='invalid json'), Items)
        result = await CrawlOrchestrator(fetcher).run('https://example.test', 0, extractor)
        self.assertFalse(result['success'])
        self.assertIsNotNone(result['document'])
        self.assertEqual(result['error'], 'ValidationError')

    async def test_legacy_fetch_wrappers_return_text(self):
        from smart_miner.crawler.router import fetch_static, fetch_dynamic
        with patch.object(PageFetcher, 'fetch_static', AsyncMock(return_value=self.page())), \
             patch.object(PageFetcher, 'fetch_dynamic', AsyncMock(return_value=self.page())):
            self.assertIn('Catalog', await fetch_static('https://example.test'))
            self.assertIn('Catalog', await fetch_dynamic('https://example.test'))

    @patch('smart_miner.crawler.fetcher.httpx.AsyncClient')
    async def test_http_transport_preserves_html_final_url_and_tls(self, client_type):
        client = AsyncMock()
        client.get.return_value = MagicMock(text='<h1>Final</h1>', url='https://example.test/final', status_code=200)
        client_type.return_value.__aenter__.return_value = client
        page = await PageFetcher().fetch_static('https://example.test/start')
        self.assertEqual(page.source_url, 'https://example.test/final')
        self.assertEqual(page.html, '<h1>Final</h1>')
        client_type.assert_called_once_with(follow_redirects=True)

    @patch('smart_miner.crawler.fetcher.async_playwright')
    async def test_browser_timeout_still_closes_browser(self, factory):
        browser = AsyncMock()
        page = AsyncMock()
        browser.new_context.return_value.new_page.return_value = page
        page.goto.side_effect = TimeoutError()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        factory.return_value.__aenter__ = AsyncMock(return_value=playwright)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with self.assertRaises(TimeoutError):
            await PageFetcher().fetch_dynamic('https://example.test')
        browser.close.assert_awaited_once()
