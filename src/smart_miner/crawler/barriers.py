"""Conservative, explicitly heuristic access-barrier detection."""
import re
from bs4 import BeautifulSoup


def barrier_reason(page):
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
