import asyncio
import unittest
from smart_miner.batch.queue import DomainRateLimiter, BatchCrawlManager, JobStatus


class BatchQueueTests(unittest.TestCase):
    def test_domain_rate_limiter_domain_parsing(self):
        limiter = DomainRateLimiter()
        self.assertEqual(limiter._get_domain("https://haiox.ai/article"), "haiox.ai")
        self.assertEqual(limiter._get_domain("http://sub.domain.com:8080/path"), "sub.domain.com:8080")
        self.assertEqual(limiter._get_domain("not-a-url"), "unknown")

    def test_domain_rate_limiter_acquire_and_release(self):
        async def _run():
            limiter = DomainRateLimiter(min_interval_seconds=0.01, max_domain_concurrency=2)
            domain = await limiter.acquire("https://example.com/page1")
            self.assertEqual(domain, "example.com")
            limiter.release(domain)

        asyncio.run(_run())

    def test_batch_crawl_manager_job_lifecycle(self):
        async def _run():
            manager = BatchCrawlManager(worker_concurrency=2)
            job = manager.create_job(["https://site1.com", "https://site2.com"])
            self.assertEqual(job.status, JobStatus.QUEUED)
            self.assertEqual(job.total_urls, 2)
            self.assertEqual(manager.get_job(job.job_id), job)

            async def mock_crawler(target_url: str):
                return {"url": target_url, "status": "success", "title": f"Title for {target_url}"}

            completed_job = await manager.execute_job(job.job_id, mock_crawler)
            self.assertEqual(completed_job.status, JobStatus.COMPLETED)
            self.assertEqual(len(completed_job.results), 2)
            self.assertEqual(completed_job.completed_urls, 2)
            self.assertIsNotNone(completed_job.completed_at)

        asyncio.run(_run())

    def test_batch_crawl_manager_handles_exceptions(self):
        async def _run():
            manager = BatchCrawlManager(worker_concurrency=1)
            job = manager.create_job(["https://failing-site.com"])

            async def mock_failing_crawler(target_url: str):
                raise RuntimeError("DNS Lookup Timeout")

            completed_job = await manager.execute_job(job.job_id, mock_failing_crawler)
            self.assertEqual(completed_job.status, JobStatus.FAILED)
            self.assertEqual(len(completed_job.errors), 1)
            self.assertIn("DNS Lookup Timeout", completed_job.errors[0]["error"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
