"""Tests for BarrierDetector & BarrierReport (Subsystem 20: Modern Barrier Diagnostics)."""

import unittest
from types import SimpleNamespace

from smart_miner.crawler.barriers import BarrierDetector, barrier_reason


class BarrierDetectorTests(unittest.TestCase):
    def test_clean_page_returns_no_barrier(self):
        page = SimpleNamespace(
            html="<html><head><title>Clean Article</title></head><body><h1>Welcome</h1><p>Full content text.</p></body></html>",
            status_code=200,
        )
        report = BarrierDetector.detect(page)
        self.assertFalse(report.is_blocked)
        self.assertEqual(report.barrier_type, "NONE")
        self.assertEqual(report.suggested_action, "PROCEED")
        self.assertIsNone(barrier_reason(page))

    def test_cloudflare_turnstile_detection(self):
        page = SimpleNamespace(
            html='<html><body><script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script><div class="cf-turnstile"></div></body></html>',
            status_code=200,
        )
        report = BarrierDetector.detect(page)
        self.assertTrue(report.is_blocked)
        self.assertEqual(report.barrier_type, "CLOUDFLARE_TURNSTILE")
        self.assertEqual(report.suggested_action, "ACTIVATE_STEALTH")

    def test_cloudflare_managed_challenge_detection(self):
        page = SimpleNamespace(
            html='<html><body><div id="cf-challenge-running">Checking your browser before accessing the site...</div></body></html>',
            status_code=200,
        )
        report = BarrierDetector.detect(page)
        self.assertTrue(report.is_blocked)
        self.assertEqual(report.barrier_type, "CLOUDFLARE_CHALLENGE")
        self.assertEqual(report.suggested_action, "ACTIVATE_STEALTH")

    def test_datadome_detection(self):
        page = SimpleNamespace(
            html='<html><body><iframe src="https://geo.captcha-delivery.com/captcha/?initialCid=123"></iframe></body></html>',
            status_code=200,
        )
        report = BarrierDetector.detect(page)
        self.assertTrue(report.is_blocked)
        self.assertEqual(report.barrier_type, "DATADOME")
        self.assertEqual(report.suggested_action, "ROTATE_IP")

    def test_aws_waf_detection(self):
        page = SimpleNamespace(
            html='<html><body><script src="https://token.awswaf.com/token.js"></script></body></html>',
            status_code=200,
        )
        report = BarrierDetector.detect(page)
        self.assertTrue(report.is_blocked)
        self.assertEqual(report.barrier_type, "AWS_WAF")
        self.assertEqual(report.suggested_action, "ROTATE_IP")

    def test_http_403_and_429_access_blocked(self):
        page403 = SimpleNamespace(html="Forbidden", status_code=403)
        report403 = BarrierDetector.detect(page403)
        self.assertTrue(report403.is_blocked)
        self.assertEqual(report403.barrier_type, "ACCESS_BLOCKED")
        self.assertEqual(report403.suggested_action, "ROTATE_IP")

        page429 = SimpleNamespace(html="Too Many Requests", status_code=429)
        report429 = BarrierDetector.detect(page429)
        self.assertTrue(report429.is_blocked)
        self.assertEqual(report429.barrier_type, "ACCESS_BLOCKED")

    def test_legacy_backward_compatibility(self):
        cf_page = SimpleNamespace(
            html='<html><body><div id="challenge-form">Please confirm you are human</div></body></html>',
            status_code=200,
        )
        self.assertEqual(barrier_reason(cf_page), "CAPTCHA_OR_CHALLENGE")


if __name__ == "__main__":
    unittest.main()
