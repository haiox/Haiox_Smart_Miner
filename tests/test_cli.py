import unittest
from unittest.mock import patch, AsyncMock
from smart_miner.cli import build_parser, main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_parser_crawl_defaults(self):
        args = self.parser.parse_args(["crawl", "https://haiox.ai"])
        self.assertEqual(args.command, "crawl")
        self.assertEqual(args.url, "https://haiox.ai")
        self.assertFalse(args.dynamic)
        self.assertEqual(args.format, "markdown")
        self.assertEqual(args.fingerprint, "chrome_windows")

    def test_parser_crawl_flags(self):
        args = self.parser.parse_args([
            "crawl", "https://haiox.ai",
            "--dynamic",
            "--format", "json",
            "-o", "output.json",
            "-v",
        ])
        self.assertTrue(args.dynamic)
        self.assertEqual(args.format, "json")
        self.assertEqual(args.output, "output.json")
        self.assertTrue(args.verbose)

    def test_parser_serve_defaults(self):
        args = self.parser.parse_args(["serve"])
        self.assertEqual(args.command, "serve")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8000)

    def test_parser_benchmark_defaults(self):
        args = self.parser.parse_args(["benchmark"])
        self.assertEqual(args.command, "benchmark")
        self.assertEqual(args.phase, "all")

    @patch("smart_miner.cli.route", new_callable=AsyncMock)
    def test_cli_crawl_execution_success(self, mock_route):
        mock_route.return_value = {
            "status": "success",
            "document": {
                "title": "Mock Title",
                "markdown": "# Mock Title\nContent",
                "author": "Hatef",
                "reading_time_minutes": 2,
            },
            "evidence": {
                "document_sha256": "abcdef123456",
                "chunks": [],
            },
            "routing": {"mode": "static"},
        }
        ret = main(["crawl", "https://example.com", "--format", "summary"])
        self.assertEqual(ret, 0)
        mock_route.assert_called_once()

    @patch("smart_miner.cli.route", new_callable=AsyncMock)
    def test_cli_crawl_execution_failure(self, mock_route):
        mock_route.return_value = {
            "status": "failed",
            "error": "SSRF Blocked: Loopback target",
        }
        ret = main(["crawl", "http://127.0.0.1"])
        self.assertEqual(ret, 2)


if __name__ == "__main__":
    unittest.main()
