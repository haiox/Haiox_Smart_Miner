import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from smart_miner.api.app import app


class ApiEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_root_endpoint(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["version"], "2.0.0")
        self.assertEqual(data["status"], "operational")

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("uptime_stats", data)

    def test_metrics_prometheus_endpoint(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("haiox_smart_miner_requests_total", resp.text)
        self.assertIn("text/plain", resp.headers["content-type"])

    @patch("smart_miner.api.app.route", new_callable=AsyncMock)
    def test_crawl_single_success(self, mock_route):
        mock_route.return_value = {
            "status": "success",
            "document": {"title": "Test Title", "markdown": "# Title"},
            "evidence": {"document_sha256": "123456"},
            "routing": {"mode": "static"},
            "raw_bytes": 500,
        }
        payload = {"url": "https://haiox.ai", "dynamic": False}
        resp = self.client.post("/v1/crawl", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["document"]["title"], "Test Title")

    @patch("smart_miner.api.app.route", new_callable=AsyncMock)
    def test_crawl_single_failure_handled(self, mock_route):
        mock_route.return_value = {
            "status": "failed",
            "error": "NON_PUBLIC_ADDRESS",
            "routing": {"reason_codes": ["NON_PUBLIC_ADDRESS"]},
        }
        payload = {"url": "http://127.0.0.1"}
        resp = self.client.post("/v1/crawl", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error"], "NON_PUBLIC_ADDRESS")

    @patch("smart_miner.api.app.route", new_callable=AsyncMock)
    def test_batch_crawl_lifecycle(self, mock_route):
        mock_route.return_value = {
            "status": "success",
            "document": {"title": "Batch Target"},
        }
        payload = {"urls": ["https://site1.com", "https://site2.com"]}
        post_resp = self.client.post("/v1/crawl/batch", json=payload)
        self.assertEqual(post_resp.status_code, 200)
        job_data = post_resp.json()
        self.assertIn("job_id", job_data)
        self.assertEqual(job_data["total_urls"], 2)

        # Query batch status
        job_id = job_data["job_id"]
        get_resp = self.client.get(f"/v1/crawl/batch/{job_id}")
        self.assertEqual(get_resp.status_code, 200)
        status_data = get_resp.json()
        self.assertEqual(status_data["job_id"], job_id)

    def test_batch_crawl_not_found(self):
        resp = self.client.get("/v1/crawl/batch/non-existent-uuid")
        self.assertEqual(resp.status_code, 404)

    @patch("smart_miner.api.app.route", new_callable=AsyncMock)
    def test_crawl_stream_sse(self, mock_route):
        mock_route.return_value = {
            "status": "success",
            "document": {"title": "Streamed Doc"},
        }
        resp = self.client.get("/v1/crawl/stream?url=https://haiox.ai")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])
        self.assertIn("STARTED", resp.text)
        self.assertIn("COMPLETED", resp.text)


if __name__ == "__main__":
    unittest.main()
