"""Browser checkout via Camoufox.

Camoufox is an anti-detect Firefox browser that passes Cloudflare Turnstile.
Uses virtual display (Xvfb) on Linux to avoid headless detection.
CVV is loaded from ~/.config/asdabot/.env (ASDA_CARD_CVV).
"""

import contextlib
import json
import sys

from camoufox.sync_api import Camoufox

from asdabot.auth import ensure_valid_tokens, refresh_tokens
from asdabot.config import (
    BROWSER_STATE_DIR,
    FALLBACK_STORE_ID,
    PROFILE_API_KEY,
    PROFILE_API_URL,
    ensure_config_dir,
    get_card_cvv,
    save_account,
)

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


def _fetch_profile(page) -> dict:
    """Fetch ASDA customer profile from within the browser (passes Cloudflare)."""
    raw = page.evaluate(
        """async ([url, key]) => {
            const resp = await fetch(url, {
                headers: {
                    'ocp-apim-subscription-key': key,
                    'request_origin': 'asdaNewCo_gi',
                    'content-type': 'application/json',
                },
                credentials: 'include',
            });
            return await resp.text();
        }""",
        [PROFILE_API_URL, PROFILE_API_KEY],
    )
    return json.loads(raw)


def _build_account(cookies: dict, profile_response: dict) -> dict:
    """Build account dict from browser cookies and profile API response."""
    profile = profile_response.get("profile", {})
    info = profile.get("additionalInfo", {})
    addresses = profile_response.get("addresses", [])
    default_addr = next(
        (a for a in addresses if a.get("default")), addresses[0] if addresses else {}
    )

    return {
        "tokens": {
            "slas_auth": cookies.get("SLAS.AUTH_TOKEN", ""),
            "slas_refresh": cookies.get("SLAS.REFRESH_TOKEN", ""),
            "customer_id": cookies.get("SLAS.CUSTOMER_ID", ""),
            "usid": cookies.get("SLAS.USID", ""),
            "adb2c_auth": cookies.get("ADB2C.AUTH_TOKEN", ""),
        },
        "store_id": info.get("cnc_store_id", FALLBACK_STORE_ID),
        "address": {
            "address1": default_addr.get("line1", ""),
            "address2": default_addr.get("line2", ""),
            "city": default_addr.get("city", ""),
            "postcode": default_addr.get("postcode", "").replace(" ", ""),
            "latitude": default_addr.get("latitude", ""),
            "longitude": default_addr.get("longitude", ""),
            "address_type": default_addr.get("addressType", "House"),
            "crm_address_id": default_addr.get("crmAddressId", ""),
            "first_name": info.get("firstName", ""),
            "last_name": info.get("lastName", ""),
        },
    }


def browser_login() -> dict | None:
    """Open Camoufox for manual login. Saves account (tokens + profile + address)."""
    ensure_config_dir()
    BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

    print("Launching browser for ASDA login...")
    print("Log in to your ASDA account in the browser window.")
    print("Once you see the homepage with your name, press Enter here.\n")

    with _camoufox(headless=False) as context:
        page = context.new_page()
        page.goto(ASDA_BASE, wait_until="networkidle", timeout=60000)
        input("Press Enter after you've logged in...")

        cookies = {
            c["name"]: c["value"]
            for c in context.cookies([f"{ASDA_BASE}/"])
            if c["name"] in TOKEN_COOKIE_NAMES
        }

        if not cookies.get("SLAS.REFRESH_TOKEN"):
            return None

        profile_response = _fetch_profile(page)

    account = _build_account(cookies, profile_response)
    save_account(account)

    with contextlib.suppress(Exception):
        refresh_tokens()

    return account


def place_order_via_browser(headless: bool = True) -> dict:
    """Place an order using Camoufox. Fills CVV from .env and clicks confirm."""
    if not BROWSER_STATE_DIR.exists():
        return {"success": False, "error": "No browser session. Run 'asdabot auth login' first."}

    cvv = get_card_cvv()
    if not cvv:
        return {"success": False, "error": "Set ASDA_CARD_CVV in ~/.config/asdabot/.env"}

    ensure_valid_tokens()

    try:
        with _camoufox(headless=headless) as context:
            page = context.new_page()
            page.goto(ORDER_SUMMARY_URL, wait_until="networkidle", timeout=30000)

            if "login.asda.com" in page.url:
                return {"success": False, "error": "Session expired. Run 'asdabot auth login'."}

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

            # Race: confirmation page vs Chakra error modal
            result = page.wait_for_function(
                """() => {
                    if (window.location.pathname.includes('/order-confirmation')) {
                        return { ok: true };
                    }
                    const modal = document.querySelector(
                        'section[role="dialog"][aria-modal="true"]'
                    );
                    if (modal) {
                        const body = modal.querySelector('[id*="body"]');
                        const text = (body || modal).innerText.trim();
                        // Ignore the "Confirming your order" loading modal
                        if (!text || text.toLowerCase().includes('confirming')) {
                            return null;
                        }
                        return { ok: false, error: text };
                    }
                    return null;
                }""",
                timeout=45000,
            )
            outcome = result.json_value()

            if not outcome["ok"]:
                error = outcome.get("error", "Payment failed.")
                return {"success": False, "error": error}

            page.wait_for_load_state("networkidle", timeout=10000)
            return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
