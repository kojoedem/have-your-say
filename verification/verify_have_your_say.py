import time
from playwright.sync_api import sync_playwright

def run_cuj(page, is_mobile=False):
    # Set viewport size
    if is_mobile:
        page.set_viewport_size({"width": 375, "height": 667})
    else:
        page.set_viewport_size({"width": 1280, "height": 800})

    # Register dialog listener
    page.on("dialog", lambda dialog: dialog.accept())

    print("Navigating to http://localhost:8000")
    page.goto("http://localhost:8000")
    page.wait_for_timeout(1000)

    # 1. Login flow
    print("Filling phone number")
    page.locator("#phone").fill("+15555551234")
    page.wait_for_timeout(500)

    print("Requesting OTP")
    page.locator("#request-otp-btn").click()
    page.wait_for_timeout(1000)

    # Read the mock OTP code from the banner
    print("Retrieving OTP code")
    otp_code = page.locator("#mock-otp-value").text_content()
    print(f"Retrieved OTP: {otp_code}")

    print("Filling and verifying OTP")
    page.locator("#code").fill(otp_code)
    page.wait_for_timeout(500)
    page.locator("#verify-otp-btn").click()
    page.wait_for_timeout(2000)

    # We should now be on the App main feed screen!
    print("Taking feed screenshot...")
    screenshot_prefix = "mobile" if is_mobile else "desktop"
    page.screenshot(path=f"/app/verification/screenshots/{screenshot_prefix}_feed.png")

    # 2. Test App Logo Settings click/touch
    print("Clicking logo to open Settings Modal")
    page.locator("#app-logo-btn").click()
    page.wait_for_timeout(1000)

    print(f"Taking {screenshot_prefix} settings modal screenshot...")
    page.screenshot(path=f"/app/verification/screenshots/{screenshot_prefix}_modal.png")

    print("Closing Settings Modal")
    # Click the close button (the 'x' button inside the modal)
    page.locator("#settings-modal button").first.click()
    page.wait_for_timeout(1000)

    if is_mobile:
        # 3. Test Twitter-style Tab Navigation
        print("Switching to Trending mobile tab")
        page.locator("#mobile-tab-trending").click()
        page.wait_for_timeout(1000)

        print("Taking mobile trending tab screenshot...")
        page.screenshot(path="/app/verification/screenshots/mobile_trending.png")

        print("Switching back to Home/Feed tab")
        page.locator("#mobile-tab-feed").click()
        page.wait_for_timeout(1000)

    page.wait_for_timeout(1000)
    print("CUJ completed successfully!")

if __name__ == "__main__":
    with sync_playwright() as p:
        print("--- RUNNING DESKTOP JOURNEY ---")
        browser = p.chromium.launch(headless=True)
        # Use desktop context
        context_desktop = browser.new_context(
            record_video_dir="/app/verification/videos"
        )
        page_desktop = context_desktop.new_page()
        try:
            run_cuj(page_desktop, is_mobile=False)
        finally:
            context_desktop.close()

        print("\n--- RUNNING MOBILE JOURNEY ---")
        # Use mobile context (mimicking an iPhone-like screen)
        context_mobile = browser.new_context(
            record_video_dir="/app/verification/videos",
            viewport={"width": 375, "height": 667},
            is_mobile=True
        )
        page_mobile = context_mobile.new_page()
        try:
            run_cuj(page_mobile, is_mobile=True)
        finally:
            context_mobile.close()
            browser.close()
