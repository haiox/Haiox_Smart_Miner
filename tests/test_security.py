"""Tests for zero-trust URL validation, SSRF protection, and network isolation."""

import unittest
from unittest.mock import AsyncMock, patch

from smart_miner import route
from smart_miner.crawler.fetcher import PageFetcher
from smart_miner.crawler.security import (
    SecurityError,
    is_public_ip,
    validate_url_target,
)


class SSRFValidationTests(unittest.TestCase):
    def test_loopback_addresses_are_rejected(self):
        loopback_urls = [
            "http://127.0.0.1",
            "http://127.0.0.1:80",
            "http://127.0.0.100:80/secret",
            "http://localhost",
            "http://localhost:80",
            "http://[::1]",
            "http://[::1]:80",
        ]
        for url in loopback_urls:
            with self.subTest(url=url):
                with self.assertRaises(SecurityError) as ctx:
                    validate_url_target(url)
                self.assertEqual(str(ctx.exception), "NON_PUBLIC_ADDRESS")

    def test_private_rfc1918_addresses_are_rejected(self):
        private_urls = [
            "http://10.0.0.1",
            "http://10.255.255.255",
            "http://172.16.0.1",
            "http://172.31.255.255",
            "http://192.168.0.1",
            "http://192.168.1.100:80/admin",
        ]
        for url in private_urls:
            with self.subTest(url=url):
                with self.assertRaises(SecurityError) as ctx:
                    validate_url_target(url)
                self.assertEqual(str(ctx.exception), "NON_PUBLIC_ADDRESS")

    def test_cloud_metadata_link_local_addresses_are_rejected(self):
        metadata_urls = [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://169.254.1.1",
        ]
        for url in metadata_urls:
            with self.subTest(url=url):
                with self.assertRaises(SecurityError) as ctx:
                    validate_url_target(url)
                self.assertEqual(str(ctx.exception), "NON_PUBLIC_ADDRESS")

    def test_invalid_and_dangerous_schemes_are_rejected(self):
        dangerous_urls = [
            "file:///etc/passwd",
            "file:///c:/windows/win.ini",
            "ftp://files.example.com",
            "gopher://evil.com",
            "data:text/html,payload",
            "javascript:alert(1)",
            "ws://socket.example.com",
        ]
        for url in dangerous_urls:
            with self.subTest(url=url):
                with self.assertRaises(SecurityError) as ctx:
                    validate_url_target(url)
                self.assertEqual(str(ctx.exception), "INVALID_SCHEME")

    def test_disallowed_ports_are_rejected(self):
        disallowed_ports = [
            "http://example.com:22",
            "http://example.com:25",
            "http://example.com:3306",
            "http://example.com:6379",
            "http://example.com:8080",
            "http://example.com:9200",
        ]
        for url in disallowed_ports:
            with self.subTest(url=url):
                with self.assertRaises(SecurityError) as ctx:
                    validate_url_target(url)
                self.assertEqual(str(ctx.exception), "DISALLOWED_PORT")

    def test_allow_private_urls_bypass_for_local_testing(self):
        local_url = "http://127.0.0.1:80/test"
        result = validate_url_target(local_url, allow_private=True)
        self.assertEqual(result, local_url)

    def test_is_public_ip_classification(self):
        self.assertFalse(is_public_ip("127.0.0.1"))
        self.assertFalse(is_public_ip("::1"))
        self.assertFalse(is_public_ip("10.1.2.3"))
        self.assertFalse(is_public_ip("192.168.1.1"))
        self.assertFalse(is_public_ip("172.20.0.1"))
        self.assertFalse(is_public_ip("169.254.169.254"))
        self.assertFalse(is_public_ip("224.0.0.1"))
        self.assertFalse(is_public_ip("0.0.0.0"))
        # Public IP addresses
        self.assertTrue(is_public_ip("8.8.8.8"))
        self.assertTrue(is_public_ip("1.1.1.1"))
        self.assertTrue(is_public_ip("93.184.216.34"))


class OrchestratorSecurityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_blocks_loopback_target_with_safe_reason(self):
        result = await route("http://127.0.0.1:80/status")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["routing"]["reason_codes"], ["NON_PUBLIC_ADDRESS"])
        self.assertIsNone(result["document"])

    async def test_route_blocks_cloud_metadata_with_safe_reason(self):
        result = await route("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["routing"]["reason_codes"], ["NON_PUBLIC_ADDRESS"])

    async def test_route_blocks_file_scheme(self):
        result = await route("file:///etc/hosts")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["routing"]["reason_codes"], ["INVALID_SCHEME"])

    async def test_route_blocks_internal_port(self):
        result = await route("http://example.com:6379")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["routing"]["reason_codes"], ["DISALLOWED_PORT"])


if __name__ == "__main__":
    unittest.main()
