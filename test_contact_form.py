# test_contact_form.py
import os, sys, time, traceback
from pathlib import Path

LOG = Path("form_test_log.txt")

def log(msg):
    print(msg, flush=True)
    LOG.open("a", encoding="utf-8").write(msg + "\n")

def need(name, default=None):
    v = os.getenv(name, default)
    if v is None or v == "":
        log(f"Missing required env var: {name}")
        sys.exit(2)
    return v

TEST_URL = need("TEST_URL")                      # e.g., https://primeshinehousecleaning.com/contact/
SUCCESS_SELECTOR = need("SUCCESS_SELECTOR")      # e.g., text=Thank you, or a CSS like .wpcf7-mail-sent-ok
TEST_EMAIL = os.getenv("TEST_EMAIL", "qa@example.com")

# Common fallback selectors. You can override via env if needed.
SEL_NAME = os.getenv("SEL_NAME", 'input[name="name"], input#name, input[name="your-name"]')
SEL_EMAIL = os.getenv("SEL_EMAIL", 'input[name="email"], input#email, input[name="your-email"]')
SEL_PHONE = os.getenv("SEL_PHONE", 'input[name="phone"], input#phone, input[name="tel"], input[name="your-phone"]')
SEL_MESSAGE = os.getenv("SEL_MESSAGE", 'textarea[name="message"], textarea#message, textarea[name="your-message"]')
SEL_SUBMIT = os.getenv("SEL_SUBMIT", 'button[type="submit"], input[type="submit"]')

FORM_NAME = os.getenv("FORM_NAME", "QA Test")
FORM_PHONE = os.getenv("FORM_PHONE", "555-000-1234")
FORM_MESSAGE = os.getenv("FORM_MESSAGE", f"Automated test {int(time.time())}")

def main():
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    start = time.time()
    log("=== Contact form test started ===")
    log(f"URL: {TEST_URL}")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()

            page.goto(TEST_URL, timeout=60000)
            log("Page loaded")

            # Fill fields best-effort
            for sel, val in [
                (SEL_NAME, FORM_NAME),
                (SEL_EMAIL, TEST_EMAIL),
                (SEL_PHONE, FORM_PHONE),
                (SEL_MESSAGE, FORM_MESSAGE),
            ]:
                try:
                    page.fill(sel, val, timeout=5000)
                    log(f"Filled {sel}")
                except PwTimeout:
                    log(f"Optional field not found: {sel}")

            # Submit
            try:
                page.click(SEL_SUBMIT, timeout=10000)
                log("Clicked submit")
            except PwTimeout:
                log(f"Submit button not found: {SEL_SUBMIT}")
                raise

            # Prove success
            try:
                if SUCCESS_SELECTOR.lower().startswith("text="):
                    page.get_by_text(SUCCESS_SELECTOR[5:]).wait_for(timeout=20000, state="visible")
                else:
                    page.wait_for_selector(SUCCESS_SELECTOR, timeout=20000, state="visible")
                log("Success selector found")
            except PwTimeout:
                log("Did not see success selector in time")
                raise

            # Artifacts
            page.screenshot(path="form_test_screenshot.png", full_page=True)
            Path("form_test_source.html").write_text(page.content(), encoding="utf-8")

            log(f"=== PASS in {time.time()-start:.1f}s ===")
            return 0

    except Exception as e:
        # Try to capture artifacts even on failure
        try:
            page.screenshot(path="form_test_screenshot.png", full_page=True)
            Path("form_test_source.html").write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        log("ERROR:\n" + "".join(traceback.format_exception(e)))
        log("=== FAIL ===")
        return 1

if __name__ == "__main__":
    sys.exit(main())


Add contact form test script

