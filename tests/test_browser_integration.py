"""Opt-in local HTTP/AJAX integration test, requiring Playwright Chromium."""
import functools
import os
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from smart_miner.crawler.fetcher import PageFetcher
from smart_miner.pipeline.orchestrator import CrawlOrchestrator


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(os.getenv('SMART_MINER_BROWSER_TESTS') == '1', 'opt-in local Chromium integration')
class LocalBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_ajax_fetch_clean_pipeline(self):
        handler = functools.partial(QuietHandler, directory=str(Path(__file__).parent / 'fixtures'))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            static_url = f'http://127.0.0.1:{server.server_port}/static.html'
            static = await CrawlOrchestrator().run(static_url, min_text_length=0)
            self.assertTrue(static['success'], static['error'])
            self.assertEqual(static['routing']['strategy'], 'static')
            self.assertEqual(static['document']['source_url'], static_url)
            url = f'http://127.0.0.1:{server.server_port}/ajax.html'
            result = await CrawlOrchestrator(PageFetcher(wait_selector='[data-ready="true"]')).run(url)
            self.assertTrue(result['success'], result['error'])
            self.assertEqual(result['routing']['strategy'], 'dynamic')
            self.assertIn('| Laptop | 12 |', result['document']['markdown'])
            self.assertIn(f'http://127.0.0.1:{server.server_port}/item/1', result['document']['markdown'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
