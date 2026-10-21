"""Unit & integration tests for Subsystem 13: JSON-LD Entity Graph Resolver."""

import unittest
from bs4 import BeautifulSoup

from smart_miner.pipeline.jsonld import (
    JSONLDResolver,
    ResolvedEntityGraph,
    ArticleEntity,
    ProductEntity,
    FAQItem,
)
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


class JSONLDResolverUnitTests(unittest.TestCase):
    def setUp(self):
        self.resolver = JSONLDResolver()

    def test_unroll_nested_graphs(self):
        raw = [
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "Organization", "name": "Haiox Labs"},
                    {"@type": "WebSite", "name": "Haiox AI Portal"},
                ],
            },
            {"@type": "Person", "name": "AIrash"},
        ]
        graph = self.resolver.resolve(raw)
        self.assertEqual(graph.total_nodes, 3)
        self.assertEqual(graph.nodes_by_type.get("Organization"), 1)
        self.assertEqual(graph.nodes_by_type.get("WebSite"), 1)
        self.assertEqual(graph.nodes_by_type.get("Person"), 1)

    def test_resolve_id_cross_references(self):
        raw = [
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@id": "https://haiox.ai/#article-1",
                        "@type": "TechArticle",
                        "headline": "Zero-Trust Web Scraping Architecture",
                        "author": {"@id": "https://haiox.ai/#author-hatef"},
                    },
                    {
                        "@id": "https://haiox.ai/#author-hatef",
                        "@type": "Person",
                        "name": "Hatef",
                    },
                ],
            }
        ]
        graph = self.resolver.resolve(raw)
        self.assertEqual(len(graph.articles), 1)
        article = graph.articles[0]
        self.assertEqual(article.headline, "Zero-Trust Web Scraping Architecture")
        self.assertEqual(article.author, "Hatef")

    def test_circular_reference_protection(self):
        # A points to B, B points back to A
        raw = [
            {
                "@id": "https://example.com/nodeA",
                "@type": "Thing",
                "name": "Node A",
                "rel": {"@id": "https://example.com/nodeB"},
            },
            {
                "@id": "https://example.com/nodeB",
                "@type": "Thing",
                "name": "Node B",
                "rel": {"@id": "https://example.com/nodeA"},
            },
        ]
        # Must resolve without recursion error
        graph = self.resolver.resolve(raw)
        self.assertEqual(graph.total_nodes, 2)

    def test_canonical_article_parsing(self):
        raw = [
            {
                "@type": "NewsArticle",
                "headline": "Smart Miner Phase 2 Release",
                "description": "Advanced structural parsing engine.",
                "author": [{"name": "AIrash"}],
                "publisher": {"name": "Haiox"},
                "datePublished": "2026-10-21T03:30:00Z",
                "dateModified": "2026-10-21T03:45:00Z",
            }
        ]
        graph = self.resolver.resolve(raw)
        self.assertEqual(len(graph.articles), 1)
        art = graph.articles[0]
        self.assertEqual(art.headline, "Smart Miner Phase 2 Release")
        self.assertEqual(art.description, "Advanced structural parsing engine.")
        self.assertEqual(art.author, "AIrash")
        self.assertEqual(art.publisher, "Haiox")
        self.assertEqual(art.date_published, "2026-10-21T03:30:00Z")
        self.assertEqual(art.date_modified, "2026-10-21T03:45:00Z")

    def test_canonical_product_parsing(self):
        raw = [
            {
                "@type": "Product",
                "name": "DePIN Edge Node Miner",
                "description": "High-throughput edge intelligence miner.",
                "sku": "HX-NODE-001",
                "offers": {
                    "@type": "Offer",
                    "price": "499.99",
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock",
                },
                "aggregateRating": {
                    "@type": "AggregateRating",
                    "ratingValue": "4.9",
                    "reviewCount": "128",
                },
            }
        ]
        graph = self.resolver.resolve(raw)
        self.assertEqual(len(graph.products), 1)
        prod = graph.products[0]
        self.assertEqual(prod.name, "DePIN Edge Node Miner")
        self.assertEqual(prod.sku, "HX-NODE-001")
        self.assertEqual(prod.price, 499.99)
        self.assertEqual(prod.currency, "USD")
        self.assertEqual(prod.availability, "InStock")
        self.assertEqual(prod.rating_value, 4.9)
        self.assertEqual(prod.review_count, 128)

    def test_canonical_faq_parsing(self):
        raw = [
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": "How does Smart Miner prevent hallucinations?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "<p>It parses structured data and normalizes tables without LLM guesswork.</p>",
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Is SSRF protection enabled?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "Yes, all target IPs are pre-audited in zero-trust memory.",
                        },
                    },
                ],
            }
        ]
        graph = self.resolver.resolve(raw)
        self.assertEqual(len(graph.faqs), 2)
        self.assertEqual(graph.faqs[0].question, "How does Smart Miner prevent hallucinations?")
        self.assertEqual(graph.faqs[0].answer, "It parses structured data and normalizes tables without LLM guesswork.")
        self.assertEqual(graph.faqs[1].question, "Is SSRF protection enabled?")
        self.assertEqual(graph.faqs[1].answer, "Yes, all target IPs are pre-audited in zero-trust memory.")

    def test_canonical_breadcrumbs_sorting(self):
        raw = [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 2, "name": "Documentation"},
                    {"@type": "ListItem", "position": 1, "name": "Home"},
                    {"@type": "ListItem", "position": 3, "name": "Smart Miner"},
                ],
            }
        ]
        graph = self.resolver.resolve(raw)
        self.assertEqual(graph.breadcrumbs, ["Home", "Documentation", "Smart Miner"])


class JSONLDResolverIntegrationTests(unittest.TestCase):
    def test_document_cleaner_integration_and_pydantic_roundtrip(self):
        html = """
        <!DOCTYPE html>
        <html>
            <head>
                <title>Schema Store Page</title>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@graph": [
                        {
                            "@type": "Product",
                            "name": "Enterprise AI Orchestrator License",
                            "offers": {"price": "1499.00", "priceCurrency": "USD"}
                        },
                        {
                            "@type": "FAQPage",
                            "mainEntity": [
                                {
                                    "@type": "Question",
                                    "name": "What is Haiox Trilogy?",
                                    "acceptedAnswer": {"@type": "Answer", "text": "Smart Miner, MultiAgent, and Orchestrator."}
                                }
                            ]
                        }
                    ]
                }
                </script>
            </head>
            <body>
                <main>
                    <h1>Product Details</h1>
                    <p>Enterprise grade autonomous systems for large scale data mining and multi-agent coordination.</p>
                </main>
            </body>
        </html>
        """
        page = FetchedPage(
            html=html,
            source_url="https://haiox.ai/store",
            status_code=200,
        )
        cleaner = DocumentCleaner()
        doc = cleaner.clean(page)

        self.assertIsInstance(doc.json_ld_graph, ResolvedEntityGraph)
        self.assertEqual(doc.json_ld_graph.total_nodes, 2)
        self.assertEqual(len(doc.json_ld_graph.products), 1)
        self.assertEqual(doc.json_ld_graph.products[0].name, "Enterprise AI Orchestrator License")
        self.assertEqual(doc.json_ld_graph.products[0].price, 1499.00)
        self.assertEqual(len(doc.json_ld_graph.faqs), 1)
        self.assertEqual(doc.json_ld_graph.faqs[0].question, "What is Haiox Trilogy?")

        # Complete Pydantic JSON Roundtrip Verification
        dumped = doc.model_dump_json()
        validated = CleanDocument.model_validate_json(dumped)
        self.assertEqual(validated, doc)
        self.assertEqual(validated.json_ld_graph.products[0].currency, "USD")


if __name__ == "__main__":
    unittest.main()
