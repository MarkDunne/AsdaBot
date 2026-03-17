"""Browser checkout via Camoufox.

Camoufox is an anti-detect Firefox browser that passes Cloudflare Turnstile.
CVV is loaded from ~/.config/asdabot/.env (ASDA_CARD_CVV).
"""

import contextlib
import re
import time

from camoufox.sync_api import Camoufox

from asdabot.auth import ensure_valid_tokens
from asdabot.config import BROWSER_STATE_DIR, ensure_config_dir, get_card_cvv

ASDA_BASE = "https://www.asda.com"
ORDER_SUMMARY_URL = f"{ASDA_BASE}/groceries/checkout/order-summary"
ORDER_CONFIRMATION_PATH = "/groceries/checkout/order-confirmation"

CAMOUFOX_PROFILE = str(BROWSER_STATE_DIR / "camoufox-profile")


def _browser_state_exists() -> bool:
    return BROWSER_STATE_DIR.exists()


def browser_login() -> bool:
    """Open Camoufox for manual login. Saves session state and extracts tokens."""
    ensure_config_dir()
    BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

    print("Launching browser for ASDA login...")
    print("Log in to your ASDA account in the browser window.")
    print("Once you see the homepage with your name, press Enter here.\n")

    with Camoufox(
        headless=False,
        persistent_context=True,
        user_data_dir=CAMOUFOX_PROFILE,
    ) as context:
        page = context.new_page()
        page.goto(ASDA_BASE, wait_until="networkidle", timeout=60000)

        input("Press Enter after you've logged in...")

        cookies = context.cookies(["https://www.asda.com"])
        token_map = {}
        for cookie in cookies:
            if cookie["name"] in (
                "SLAS.AUTH_TOKEN",
                "SLAS.REFRESH_TOKEN",
                "SLAS.CUSTOMER_ID",
                "SLAS.USID",
                "ADB2C.AUTH_TOKEN",
                "ADB2C.REFRESH_TOKEN",
            ):
                token_map[cookie["name"]] = cookie["value"]

    if not token_map.get("SLAS.REFRESH_TOKEN"):
        return False

    import httpx

    from asdabot.auth import SLAS_CLIENT_ID, TOKEN_REFRESH_URL
    from asdabot.config import save_tokens

    resp = httpx.post(
        TOKEN_REFRESH_URL,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "Mozilla/5.0",
            "origin": "https://www.asda.com",
            "referer": "https://www.asda.com/",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_map["SLAS.REFRESH_TOKEN"],
            "client_id": SLAS_CLIENT_ID,
        },
    )

    if resp.status_code == 200:
        data = resp.json()
        save_tokens(
            {
                "SLAS.AUTH_TOKEN": f"Bearer {data['access_token']}",
                "SLAS.REFRESH_TOKEN": data["refresh_token"],
                "SLAS.CUSTOMER_ID": data["customer_id"],
                "SLAS.USID": data["usid"],
                "ADB2C.AUTH_TOKEN": data.get("idp_access_token", ""),
                "expires_at": time.time() + data["expires_in"],
                "refresh_token_expires_at": time.time() + data["refresh_token_expires_in"],
            }
        )
        return True

    save_tokens(token_map)
    print("Warning: could not refresh tokens. You may need to run 'auth login' again.")
    return True


def place_order_via_browser(headless: bool = True) -> dict:
    """Place an order using Camoufox. Fills CVV from .env and clicks confirm."""
    if not _browser_state_exists():
        return {
            "success": False,
            "error": "No browser session. Run 'asda auth login' first.",
        }

    cvv = get_card_cvv()
    if not cvv:
        return {
            "success": False,
            "error": "No CVV configured. Set ASDA_CARD_CVV in ~/.config/asdabot/.env",
        }

    ensure_valid_tokens()

    try:
        with Camoufox(
            headless=headless,
            persistent_context=True,
            user_data_dir=CAMOUFOX_PROFILE,
        ) as context:
            page = context.new_page()
            page.goto(ORDER_SUMMARY_URL, wait_until="networkidle", timeout=30000)

            if "login.asda.com" in page.url:
                return {
                    "success": False,
                    "error": "Session expired. Run 'asda auth login' again.",
                }

            # Dismiss cookie consent
            with contextlib.suppress(Exception):
                page.locator('button:has-text("Accept All")').click(timeout=3000)
                page.wait_for_timeout(500)

            # Scroll down to load the payment section and Ingenico iframe
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(3000)

            # The CVV field is inside the Ingenico hosted tokenization iframe
            ingenico_frame = page.frame(name="htpIframe0")
            if not ingenico_frame:
                # Fallback: find by URL pattern
                for frame in page.frames:
                    if "ingenico" in (frame.url or ""):
                        ingenico_frame = frame
                        break

            if not ingenico_frame:
                return {
                    "success": False,
                    "error": "Ingenico payment iframe not found.",
                }

            # Fill CVV in the iframe — target by aria-label
            cvv_input = ingenico_frame.locator(
                'input[aria-label="Card verification code"]'
            )
            cvv_input.wait_for(state="visible", timeout=10000)
            cvv_input.fill(cvv)
            page.wait_for_timeout(1000)

            # Wait for confirm button to become enabled after CVV entry
            confirm_btn = page.locator('button[data-testid="os-confirm-order-btn"]')
            page.wait_for_function(
                """() => {
                    const btn = document.querySelector('[data-testid="os-confirm-order-btn"]');
                    return btn && !btn.disabled;
                }""",
                timeout=10000,
            )

            confirm_btn.click()

            # Wait for confirmation page
            page.wait_for_url(f"**{ORDER_CONFIRMATION_PATH}**", timeout=45000)
            page.wait_for_load_state("networkidle", timeout=10000)

            # Extract order number
            order_no = ""
            order_text = page.text_content("body") or ""
            match = re.search(r"(7\d{13,15})", order_text)
            if match:
                order_no = match.group(1)

            return {"success": True, "order_no": order_no}

    except Exception as e:
        return {"success": False, "error": str(e)}
