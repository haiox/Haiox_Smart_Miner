"""Conservative, explicitly heuristic access-barrier detection."""
import re

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None


def barrier_reason(page):
    if BeautifulSoup is not None:
        soup = BeautifulSoup(page.html, "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        text = soup.get_text(" ", strip=True).casefold()
        title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
        heading = soup.h1.get_text(" ", strip=True).casefold() if soup.h1 else ""
        challenge = soup.select_one(
            'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], '
            '.g-recaptcha, .h-captcha, #challenge-form, #cf-challenge-running'
        )
    else:
        clean_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page.html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", clean_html).casefold()
        title_m = re.search(r"<title[^>]*>(.*?)</title>", page.html, flags=re.DOTALL | re.IGNORECASE)
        title = title_m.group(1).strip().casefold() if title_m else ""
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", page.html, flags=re.DOTALL | re.IGNORECASE)
        heading = h1_m.group(1).strip().casefold() if h1_m else ""
        challenge = bool(re.search(r'recaptcha|hcaptcha|challenge-form|cf-challenge-running', page.html, flags=re.IGNORECASE))

    phrases = r"verify (?:that )?you are (?:a )?human|complete the captcha|checking your browser|confirm you are human"
    if challenge or re.search(phrases, text) or title in {"just a moment...", "access denied"}:
        return "CAPTCHA_OR_CHALLENGE"
    if page.status_code in {401, 403, 429}:
        return "ACCESS_BLOCKED"
    # Some sites return an error document with HTTP 200 and enough navigation
    # text to pass ordinary content-length checks. Keep this conservative:
    # an article discussing HTTP errors should not be rejected.
    error_titles = {"404", "404 not found", "page not found", "not found", "error 404"}
    if title in error_titles or heading in error_titles:
        return "SOFT_ERROR_PAGE"
    if title.startswith(("access denied - ", "access denied | ")):
        return "ACCESS_BLOCKED"
    return None
