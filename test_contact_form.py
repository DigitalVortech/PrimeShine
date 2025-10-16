# test_contact_form.py
import os, sys, time, traceback, re, json
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

# Field selectors (Elementor + fallbacks)
SEL_NAME = os.getenv("SEL_NAME", 'input[id^="form-field-name"], input[name*="name" i], input[autocomplete="name"]')
SEL_EMAIL = os.getenv("SEL_EMAIL", '#form-field-email, input[name*="email" i]')
SEL_PHONE = os.getenv("SEL_PHONE", '#form-field-phone, input[name*="phone" i], input[type="tel"]')
SEL_MESSAGE = os.getenv("SEL_MESSAGE", '#form-field-message, textarea[name*="message" i]')
SEL_SUBMIT = os.getenv("SEL_SUBMIT", '.elementor-form button[type="submit"], button[type="submit"], input[type="submit"]')

# Known success/error containers (CSS-only)
SUCCESS_BOXES = ".elementor-message-success, .wpforms-confirmation-container, .gform_confirmation_message, .wpcf7 form.sent .wpcf7-response-output"
ERROR_BOXES = ".elementor-message-danger, .wpforms-error-container, .wpcf7 form.invalid .wpcf7-response-output, .gform_validation_errors"

# Broader success phrases
SUCCESS_RE = re.compile(r"(thank|success|sent|received|we['’]ll be in touch|we will be in touch|message has been)", re.I)

def main():
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    t0 = time.time()
    log("=== Contact form test started ===")
    log(f"URL: {TEST_URL}")

    try:
        with sync_playwright() as pw:
            # Use a real desktop UA & args to look less “headless”
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/123.0.0.0 Safari/537.36"),
                viewport={"width": 1366, "height": 900},
            )
            page = ctx.new_page()

            # Capture console & network for debugging
            network_log = []
            def on_req(req): 
                if "admin-ajax.php" in req.url or "elementor" in req.url:
                    network_log.append({"type":"request", "url":req.url, "method":req.method, "post_data":req.post_data or ""})
            def on_res(res):
                if "admin-ajax.php" in res.url or "elementor" in res.url:
                    try:
                        body = res.text()[:2000]
                    except Exception:
                        body = "<non-text>"
                    network_log.append({"type":"response", "url":res.url, "status":res.status, "body":body})
            page.on("request", on_req)
            page.on("response", on_res)

            page.goto(TEST_URL, timeout=60000)
            log("Page loaded")

            # Fill fields (best effort) and scroll into view first
            for sel, val in [
                (SEL_NAME, FORM_NAME),
                (SEL_EMAIL, TEST_EMAIL),
                (SEL_PHONE, FORM_PHONE),
                (SEL_MESSAGE, FORM_MESSAGE),
            ]:
                try:
                    page.locator(sel).first.scroll_into_view_if_needed(timeout=3000)
                    page.fill(sel, val, timeout=5000)
                    log(f"Filled {sel}")
                except PwTimeout:
                    log(f"Optional field not found: {sel}")

            # Submit
            try:
                page.locator(SEL_SUBMIT).first.scroll_into_view_if_needed(timeout=3000)
                page.click(SEL_SUBMIT, timeout=10000)
                log("Clicked submit")
            except PwTimeout:
                log(f"Submit button not found: {SEL_SUBMIT}")
                raise

            # Let async/AJAX settle
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # Try several success signals with generous timeouts
            passed = False

            # 1) Known success containers
            if not passed:
                try:
                    page.locator(SUCCESS_BOXES).first.wait_for(timeout=15000, state="visible")
                    log("Success: Found a known success container.")
                    passed = True
                except PwTimeout:
                    log("Known success containers not found.")

            # 2) Any text node matching common success phrases
            if not passed:
                try:
                    page.get_by_text(SUCCESS_RE).first.wait_for(timeout=10000, state="visible")
                    log("Success: Found generic success text on page.")
                    passed = True
                except PwTimeout:
                    log("No generic success text found.")

            # 3) Check if the submit button is disabled or form is hidden (Elementor sometimes hides form)
            if not passed:
                try:
                    btn = page.locator(SEL_SUBMIT).first
                    disabled = btn.is_disabled()
                    hidden = not btn.is_visible()
                    log(f"Submit state after click — disabled:{disabled} hidden:{hidden}")
                    if hidden:
                        log("Heuristic success: form submit button is hidden (form likely replaced).")
                        passed = True
                except Exception:
                    pass

            # 4) Inspect network for Elementor AJAX success
            if not passed and network_log:
                try:
                    for item in network_log:
                        if item.get("type") == "response" and isinstance(item.get("body"), str):
                            body = item["body"]
                            if ("success" in body.lower() and "error" not in body.lower()) or SUCCESS_RE.search(body):
                                log("Success: AJAX response indicates success.")
                                passed = True
                                break
                except Exception:
                    pass

            # If still not passed, look for explicit error containers to help debugging
            if not passed:
                try:
                    page.locator(ERROR_BOXES).first.wait_for(timeout=2000, state="visible")
                    log("Detected an error message after submit (validation/spam).")
                except PwTimeout:
                    log("No explicit error container detected.")

            # Save artifacts & network log
            try:
                page.screenshot(path="form_test_screenshot.png", full_page=True)
                Path("form_test_source.html").write_text(page.content(), encoding="utf-8")
                Path("form_test_network.json").write_text(json.dumps(network_log, indent=2), encoding="utf-8")
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

