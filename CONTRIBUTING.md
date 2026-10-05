# Contributing to Haiox Smart Miner

Thank you for helping improve the public core. Keep pull requests focused on
one reproducible behavior, and include a small fixture or test when fixing a
router, cleaner or barrier-detection bug.

1. Install Python 3.11+ and `python -m pip install -e ".[browser]"`.
2. Run `python -m unittest discover -s tests -v` before submitting a PR.
3. For an opt-in local browser check, run `python -m playwright install chromium`
   and set `SMART_MINER_BROWSER_TESTS=1` before running the test suite.
4. Describe the page shape that triggered the problem; use synthetic or
   permissioned fixtures. Do not include private content, live keys, cookies,
   authentication headers or third-party copyrighted pages in a fixture.

The core intentionally has no Streamlit deployment configuration, provider
credential or unrestricted public URL endpoint. Please discuss changes to that
boundary before implementing them.
