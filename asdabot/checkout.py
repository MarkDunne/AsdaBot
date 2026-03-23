"""Browser checkout via Camoufox.

Camoufox is an anti-detect Firefox browser that passes Cloudflare Turnstile.
Uses virtual display (Xvfb) on Linux to avoid headless detection.
CVV is loaded from ~/.config/asdabot/.env (ASDA_CARD_CVV).
"""

import contextlib
import sys

from camoufox.sync_api import Camoufox

from asdabot.auth import ensure_valid_tokens, refresh_tokens
from asdabot.config import BROWSER_STATE_DIR, ensure_config_dir, get_card_cvv, save_tokens

ASDA_BASE = "https://www.asda.com"
ORDER_SUMMARY_URL = f"{ASDA_BASE}/groceries/checkout/order-summary"
ORDER_CONFIRMATION_PATH = "/groceries/checkout/order-confirmation"
CAMOUFOX_PROFILE = str(BROWSER_STATE_DIR / "camoufox-profile")

TOKEN_COOKIE_NAMES = (
    "SLAS.AUTH_TOKEN",
    "SLAS.REFRESH_TOKEN",
    "SLAS.CUSTOMER_ID",
    "SLAS.USID",
    "ADB2C.AUTH_TOKEN",
)


def _camoufox(headless: bool = True):
    # Virtual display (Xvfb) on Linux avoids Cloudflare headless detection.
    mode = "virtual" if headless and sys.platform == "linux" else headless
    return Camoufox(headless=mode, persistent_context=True, user_data_dir=CAMOUFOX_PROFILE)


def _find_ingenico_frame(page):
    """Find the Ingenico payment iframe by name or URL."""
    return page.frame(name="htpIframe0") or next(
        (f for f in page.frames if "ingenico" in (f.url or "")), None
    )


def browser_login() -> bool:
    """Open Camoufox for manual login. Saves session state and extracts tokens."""
    ensure_config_dir()
    BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

    print("Launching browser for ASDA login...")
    print("Log in to your ASDA account in the browser window.")
    print("Once you see the homepage with your name, press Enter here.\n")

    with _camoufox(headless=False) as context:
        page = context.new_page()
        page.goto(ASDA_BASE, wait_until="networkidle", timeout=60000)
        input("Press Enter after you've logged in...")

        token_map = {
            c["name"]: c["value"]
            for c in context.cookies([f"{ASDA_BASE}/"])
            if c["name"] in TOKEN_COOKIE_NAMES
        }

    if not token_map.get("SLAS.REFRESH_TOKEN"):
        return False

    save_tokens(token_map)
    with contextlib.suppress(Exception):
        refresh_tokens()
    return True


def place_order_via_browser(headless: bool = True) -> dict:
    """Place an order using Camoufox. Fills CVV from .env and clicks confirm."""
    if not BROWSER_STATE_DIR.exists():
        return {"success": False, "error": "No browser session. Run 'asda auth login' first."}

    cvv = get_card_cvv()
    if not cvv:
        return {"success": False, "error": "Set ASDA_CARD_CVV in ~/.config/asdabot/.env"}

    ensure_valid_tokens()

    try:
        with _camoufox(headless=headless) as context:
            page = context.new_page()
            page.goto(ORDER_SUMMARY_URL, wait_until="networkidle", timeout=30000)

            if "login.asda.com" in page.url:
                return {"success": False, "error": "Session expired. Run 'asda auth login'."}

            with contextlib.suppress(Exception):
                page.locator('button:has-text("Accept All")').click(timeout=3000)
                page.wait_for_timeout(500)

            # Scroll to load payment section and Ingenico iframe
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(3000)

            frame = _find_ingenico_frame(page)
            if not frame:
                return {"success": False, "error": "Ingenico payment iframe not found."}

            # Fill CVV and wait for confirm button to enable
            cvv_input = frame.locator('input[aria-label="Card verification code"]')
            cvv_input.wait_for(state="visible", timeout=10000)
            cvv_input.fill(cvv)
            page.wait_for_timeout(1000)

            page.wait_for_function(
                """() => {
                    const btn = document.querySelector('[data-testid="os-confirm-order-btn"]');
                    return btn && !btn.disabled;
                }""",
                timeout=10000,
            )
            page.locator('button[data-testid="os-confirm-order-btn"]').click()

            page.wait_for_url(f"**{ORDER_CONFIRMATION_PATH}**", timeout=45000)
            page.wait_for_load_state("networkidle", timeout=10000)
            return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
