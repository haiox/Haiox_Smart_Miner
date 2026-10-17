"""Haiox Smart Miner - Review & Exploration Dashboard (Streamlit Demo).

Interactive UI to test the hybrid crawler, SSRF security shield, barrier
detection, document cleaner, structured evidence generation and optional
OpenRouter AI schema extraction.
"""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
import streamlit as st

# Ensure src is on path for local execution
src_path = Path(__file__).resolve().parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

try:
    from smart_miner import CleanDocument, DocumentCleaner, StructuredExtractor, route
    from smart_miner.crawler.security import is_public_ip, validate_url_target
except ImportError:
    st.error("Smart Miner package not found. Run: pip install -e .")
    st.stop()

st.set_page_config(
    page_title="Haiox Smart Miner ⚡ Review",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #888888;
        margin-bottom: 1.5rem;
    }
    .security-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background-color: #0d2b1d;
        border: 1px solid #198754;
        color: #75b798;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-header">⚡ Haiox Smart Miner Review <span class="security-badge">🛡️ SSRF Shield Active</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">Bedrock Ingestion Engine for the Haiox Agent Trilogy · Validated Extraction, Zero-Trust Transport & Evidence Generation</div>',
    unsafe_allow_html=True,
)

# Sidebar: Controls & Configuration
with st.sidebar:
    st.header("⚙️ Crawler Configuration")
    min_length = st.slider("Min Text Length (Chars)", min_value=100, max_value=2000, value=600, step=50)
    prefer_main = st.checkbox("Prefer Main Article Region", value=True)
    force_dynamic = st.checkbox("Force Browser Fallback (Dynamic)", value=False)
    allow_private = st.checkbox("Allow Private URLs (Dev/Test only)", value=False, help="Enable only for local test servers.")
    wait_selector = st.text_input("Custom Wait Selector (Optional)", value="")

    st.divider()
    st.header("🤖 OpenRouter AI Extraction (Optional)")
    default_openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if hasattr(st, "secrets") and "OPENROUTER_API_KEY" in st.secrets:
        default_openrouter_key = st.secrets["OPENROUTER_API_KEY"]
    openrouter_key = st.text_input(
        "OpenRouter API Key",
        value=default_openrouter_key,
        type="password",
        help="Optional. Used to test structured schema extraction using LLMs.",
    )
    selected_model = st.selectbox(
        "Extraction Model",
        options=[
            "deepseek/deepseek-chat",
            "qwen/qwen-2.5-72b-instruct",
            "google/gemini-2.0-flash-001",
        ],
        index=0,
    )

    st.divider()
    st.markdown("### 🏛️ Haiox Ecosystem")
    st.markdown(
        """
        - **Smart Miner:** Bedrock Ingestion Engine
        - **[Haiox MultiAgent](https://github.com/haiox/Haiox_MultiAgent):** Verification Pipeline
        - **[Haiox Orchestrator](https://github.com/haiox/Haiox-Orchestrator-Architecture):** Governed Workflow
        """
    )
    st.caption("Nightly Build Dashboard · v1.3.1 (Night 1)")

# Main URL Input Area
col_url, col_btn = st.columns([5, 1])
with col_url:
    target_url = st.text_input(
        "Target URL",
        placeholder="https://example.com/article",
        label_visibility="collapsed",
    )
with col_btn:
    mine_clicked = st.button("🚀 Mine Page", use_container_width=True, type="primary")

# Presets including SSRF test cases
st.caption("Quick test presets: "
           "`https://en.wikipedia.org/wiki/Web_scraping` · "
           "`http://127.0.0.1:80/secret` (SSRF Test) · "
           "`http://169.254.169.254/latest/meta-data/` (Cloud Metadata Test)")

# Pydantic Schema for extraction test
class ArticleSummary(BaseModel):
    headline: str = Field(description="Primary title or core topic")
    key_points: list[str] = Field(description="3-5 bullet points summarizing facts")
    confidence_score: float = Field(default=0.9, description="Confidence in source factual consistency")


if mine_clicked and target_url:
    with st.spinner("Executing Smart Miner pipeline (Validate URL → Fetch → Barriers → Clean)..."):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(
                route(
                    target_url,
                    min_text_length=min_length,
                    wait_selector=wait_selector if wait_selector else None,
                    allow_private_urls=allow_private,
                )
            )
        except Exception as e:
            res = {
                "success": False,
                "status": "failed",
                "error": str(e),
                "routing": {"reason_codes": [type(e).__name__], "timing_ms": {"total": 0.0}},
            }
        finally:
            loop.close()

    status = res.get("status", "failed")
    routing = res.get("routing", {})
    strategy = routing.get("strategy", "unknown")
    timings = routing.get("timing_ms", {})
    total_time = timings.get("total", 0.0)
    reasons = routing.get("reason_codes", [])

    # SSRF Banner if blocked
    if any(code in {"NON_PUBLIC_ADDRESS", "INVALID_SCHEME", "DISALLOWED_PORT"} for code in reasons):
        st.error(
            f"🛡️ **Zero-Trust Security Shield Blocked Target!** "
            f"Reason: `{reasons[0]}`. Access to private/internal network targets is strictly prevented."
        )

    # Metrics Bar
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Status", status.upper(), delta="Accepted" if status == "ok" else "-Rejected",
                  delta_color="normal" if status == "ok" else "inverse")
    with m2:
        st.metric("Strategy", strategy.upper(), help="Static (HTTPX), Dynamic (Playwright), or Metadata")
    with m3:
        st.metric("Total Latency", f"{total_time:.1f} ms",
                  help=f"Static: {timings.get('static', 0)}ms | Dynamic: {timings.get('dynamic', 0)}ms")
    with m4:
        in_chars = res.get("document", {}).get("input_character_count", 0) if res.get("document") else 0
        out_chars = res.get("document", {}).get("output_character_count", 0) if res.get("document") else len(res.get("text", ""))
        compression = f"{((1 - out_chars / in_chars) * 100):.1f}%" if in_chars > 0 else "0.0%"
        st.metric("Noise Removed", compression, help=f"Input: {in_chars:,} chars → Output: {out_chars:,} chars")

    st.divider()

    # Detailed Inspection Tabs
    t_preview, t_markdown, t_metadata, t_evidence, t_ai, t_diagnostics = st.tabs([
        "📖 Clean Content View",
        "📝 Raw Markdown",
        "🏷️ Metadata & JSON-LD",
        "🛡️ Trilogy Evidence Record",
        "🤖 AI Schema Extraction",
        "🔍 Routing Diagnostics",
    ])

    with t_preview:
        if res.get("document") and res["document"].get("markdown"):
            st.markdown(res["document"]["markdown"], unsafe_allow_html=True)
        elif res.get("text"):
            st.text(res["text"])
        else:
            st.warning(f"No document content returned. Reason codes: {reasons}")

    with t_markdown:
        if res.get("document"):
            st.code(res["document"].get("markdown", ""), language="markdown")
        else:
            st.info("No markdown generated.")

    with t_metadata:
        if res.get("document"):
            doc = res["document"]
            st.write("**Document Title:**", doc.get("title", "N/A"))
            st.write("**Source URL:**", doc.get("source_url", target_url))
            st.write("**Warnings:**", doc.get("warnings", []))
            st.write("**JSON-LD Structured Records:**")
            st.json(doc.get("json_ld", []))
        else:
            st.info("No metadata available.")

    with t_evidence:
        st.markdown("#### Evidence Artifact for Haiox Orchestrator & MultiAgent")
        st.caption("Normalized context-grounding packet with content hash and source provenance.")
        doc_data = res.get("document") or {}
        content = doc_data.get("markdown") or res.get("text", "")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""

        evidence_record = {
            "source_url": target_url,
            "provenance": {
                "strategy": strategy,
                "content_hash": f"sha256:{content_hash}",
                "timing_ms": timings,
                "status": status,
                "security_verified": not any(c in {"NON_PUBLIC_ADDRESS", "INVALID_SCHEME"} for c in reasons),
            },
            "grounding_summary": {
                "title": doc_data.get("title", ""),
                "char_count": len(content),
                "estimated_tokens": max(1, len(content) // 4),
            },
            "content_preview": content[:400] + ("..." if len(content) > 400 else ""),
        }
        st.json(evidence_record)

    with t_ai:
        st.markdown("#### Provider-Independent Schema Validation")
        if not openrouter_key:
            st.info("💡 To test live AI schema extraction, enter your OpenRouter API Key in the sidebar.")
        elif not res.get("document"):
            st.warning("A clean document is required before schema extraction can run.")
        else:
            if st.button("✨ Run Structured Extraction via OpenRouter", type="secondary"):
                with st.spinner(f"Extracting schema using `{selected_model}`..."):
                    async def openrouter_generate(prompt_text: str) -> dict:
                        headers = {
                            "Authorization": f"Bearer {openrouter_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://haiox-smart-miner-review.streamlit.app/",
                            "X-Title": "Haiox Smart Miner",
                        }
                        sys_prompt = (
                            "You are a factual extractor. Return ONLY valid JSON matching this schema: "
                            + json.dumps(ArticleSummary.model_json_schema())
                        )
                        payload = {
                            "model": selected_model,
                            "messages": [
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": prompt_text[:8000]},
                            ],
                            "response_format": {"type": "json_object"},
                        }
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.post(
                                "https://openrouter.ai/api/v1/chat/completions",
                                headers=headers,
                                json=payload,
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            content = data["choices"][0]["message"]["content"]
                            return json.loads(content)

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        clean_doc = CleanDocument.model_validate(res["document"])
                        extractor = StructuredExtractor(openrouter_generate, ArticleSummary)
                        extracted = loop.run_until_complete(extractor.extract(clean_doc))
                        st.success("Extraction Validated against Pydantic ArticleSummary!")
                        st.json(extracted.model_dump())
                    except Exception as err:
                        st.error(f"Extraction failed: {err}")
                    finally:
                        loop.close()

    with t_diagnostics:
        st.markdown("#### Engine Diagnostics & Routing Decision")
        st.json({
            "routing": routing,
            "status": res.get("status"),
            "error": res.get("error"),
            "security_shield": "ACTIVE",
        })
