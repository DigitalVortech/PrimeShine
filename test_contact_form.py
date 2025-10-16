# test_contact_form.py
import os, sys, time, traceback, re
from pathlib import Path

LOG = Path("form_test_log.txt")

def log(msg):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

TEST_URL = os.getenv("TEST_URL")
if not TEST_URL:
    log("Missing required env var: TEST_URL")
    sys.exit(2)

# Test data
TEST_EMAIL = os.getenv("TEST_EMAIL", "qa@example.com")
FORM_NAME = os.getenv("FORM_NAME", "QA Test")
FORM_PHONE = os.getenv("FORM_PHONE", "555-000-1234")
FORM_MESSAGE = os.getenv("FORM_MESSAGE", f"Automated test {int(time.time())}")
SUCCESS_TEXT = os.getenv("SUCCESS_TEXT", "thank")  # case-insensitive

# Field selectors (Elementor + fallbacks)
SEL_NAME = os.getenv("SEL_NAME", 'input[id^="form-field-name"], input[name*="name" i], input[autocomplete="name"]')
SEL_EMAIL = os.getenv("SEL_EMAIL", '#form-field-email, input[name*="email" i]')
SEL_PHONE = os.getenv("SEL_PHONE", '#form-field-phone, input[name*="phone" i], input[type="tel"]')
SEL_MESSAGE = os.getenv("SEL_MESSAGE", '#form-field-message, textarea[name*="message" i]')
SEL_SUBMIT = os.getenv("SEL_SUBMIT", '.elementor-form button[type="submit"], button[type="submit"], input[type="submit"]')

# Known success/error containers (CSS-only)
SUCCESS_BOXES = ".elementor-message-success, .wpforms-confirmation-container, .gform_confirmation_message, .wpcf7 form.sent .wpcf7-response-output"
ERROR_BOXES = ".elementor-message-danger, .wpforms-error-container, .wpcf7 form.invalid .wpcf7-response-output, .gform_validation_errors"

def main():
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    t0 = time.time()
    log("=== Contact form test started ===")
    log(f"URL: {TEST_URL}")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()

            page.goto(TEST_URL, timeout=60000)
            log("Page loaded")

            # Fill fields (best effort)
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

            # Give the form a moment to process network calls
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            passed = False

            # 1) URL contains success text (e.g., thank-you page)
            try:
                page.wait_for_url(re.compile(SUCCESS_TEXT, re.I), timeout=5000)
                log(f"Success: URL contains '{SUCCESS_TEXT}'.")
                passed = True
            except PwTimeout:
                log("No success redirect; checking DOM...")

            # 2) Known success containers (pure CSS)
            if not passed:
                try:
                    page.locator(SUCCESS_BOXES).first.wait_for(timeout=10000, state="visible")
                    log("Success: Found a known success container.")
                    passed = True
                except PwTimeout:
                    log("Known success containers not found.")

            # 3) ARIA alert containing success text
            if not passed:
                try:
                    loc = page.get_by_role("alert").filter(has_text=re.compile(SUCCESS_TEXT, re.I))
                    loc.first.wait_for(timeout=5000, state="visible")
                    log("Success: Found an ARIA alert with success text.")
                    passed = True
                except PwTimeout:
                    log("No ARIA alert with success text.")

            # 4) Any visible text that contains success text
            if not passed:
                try:
                    page.get_by_text(re.compile(SUCCESS_TEXT, re.I)).first.wait_for(timeout=5000, state="visible")
                    log("Success: Found generic success text on page.")
                    passed = True
                except PwTimeout:
                    log("No generic success text found.")

            # If still not passed, look for explicit error containers to help debugging
            if not passed:
                try:
                    page.locator(ERROR_BOXES).first.wait_for(timeout=1000, state="visible")
                    log("Detected an error message after submit (validation/spam).")
                except PwTimeout:
                    log("No explicit error container detected.")

            # Save artifacts either way
            try:
                page.screenshot(path="form_test_screenshot.png", full_page=True)
                Path("form_test_source.html").write_text(page.content(), encoding="utf-8")
            except Exception:
                pass

            if passed:
                dur = time.time() - t0
                log(f"=== PASS in {dur:.1f}s ===")
                return 0
            else:
                log("=== FAIL (no success signal) ===")
                return 1

    except Exception as e:
        try:
            page.screenshot(path="form_test_screenshot.png", full_page=True)
            Path("form_test_source.html").write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        log("ERROR:\n" + "".join(traceback.format_exception(e)))
        log("=== FAIL (exception) ===")
        return 1

if __name__ == "__main__":
    sys.exit(main())

