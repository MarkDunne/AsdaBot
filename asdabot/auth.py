"""Authentication — token management and automatic refresh."""

import sys
import time

import httpx

from asdabot.config import (
    SFCC_ORG,
    SFCC_PROXY_BASE,
    load_tokens,
    save_tokens,
)

SLAS_CLIENT_ID = "e68ca36d-6516-4704-b705-06b74f85ef2e"
TOKEN_REFRESH_URL = f"{SFCC_PROXY_BASE}/shopper/auth/v1/organizations/{SFCC_ORG}/oauth2/token"


def _require_tokens() -> dict:
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run 'asda auth import' first.")
        sys.exit(1)
    return tokens


def _is_token_expired(tokens: dict) -> bool:
    expires_at = tokens.get("expires_at", 0)
    # Refresh 60 seconds before actual expiry
    return time.time() > (expires_at - 60)


def refresh_tokens() -> dict:
    """Refresh SLAS tokens using the refresh token.

    This also refreshes the ADB2C token (returned as idp_access_token).
    Returns the updated token dict.
    """
    tokens = _require_tokens()
    refresh_token = tokens.get("SLAS.REFRESH_TOKEN")
    if not refresh_token:
        print("No refresh token available. Run 'asda auth import' first.")
        sys.exit(1)

    resp = httpx.post(
        TOKEN_REFRESH_URL,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "origin": "https://www.asda.com",
            "referer": "https://www.asda.com/",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": SLAS_CLIENT_ID,
        },
    )
    resp.raise_for_status()
    data = resp.json()

    updated = {
        "SLAS.AUTH_TOKEN": f"Bearer {data['access_token']}",
        "SLAS.REFRESH_TOKEN": data["refresh_token"],
        "SLAS.CUSTOMER_ID": data["customer_id"],
        "SLAS.USID": data["usid"],
        "ADB2C.AUTH_TOKEN": data.get("idp_access_token", ""),
        "expires_at": time.time() + data["expires_in"],
        "refresh_token_expires_at": time.time() + data["refresh_token_expires_in"],
    }
    save_tokens(updated)
    return updated


def ensure_valid_tokens() -> dict:
    """Return valid tokens, refreshing automatically if expired."""
    tokens = _require_tokens()
    if _is_token_expired(tokens):
        tokens = refresh_tokens()
    return tokens


def get_slas_bearer_token() -> str:
    """Get a valid SLAS bearer token, refreshing if needed."""
    tokens = ensure_valid_tokens()
    token = tokens.get("SLAS.AUTH_TOKEN", "")
    if token.startswith("Bearer "):
        token = token[7:]
    return token


def get_adb2c_token() -> str:
    """Get a valid ADB2C token, refreshing if needed."""
    tokens = ensure_valid_tokens()
    return tokens.get("ADB2C.AUTH_TOKEN", "")


def get_customer_id() -> str:
    tokens = ensure_valid_tokens()
    return tokens.get("SLAS.CUSTOMER_ID", "")


def import_tokens_interactive():
    """Import tokens by pasting cookie values from browser dev tools."""
    print("Open Chrome DevTools on asda.com → Application → Cookies")
    print("Copy the values for each cookie when prompted.\n")

    cookie_names = [
        "SLAS.AUTH_TOKEN",
        "SLAS.REFRESH_TOKEN",
        "SLAS.CUSTOMER_ID",
        "SLAS.USID",
    ]

    tokens = {}
    for name in cookie_names:
        value = input(f"  {name}: ").strip()
        if value:
            tokens[name] = value

    if not tokens.get("SLAS.REFRESH_TOKEN"):
        print("Error: SLAS.REFRESH_TOKEN is required.")
        sys.exit(1)

    # Immediately refresh to get a full token set including ADB2C
    save_tokens(tokens)
    print("Refreshing tokens...")
    updated = refresh_tokens()
    print(f"Authenticated as customer {updated['SLAS.CUSTOMER_ID']}")
    print("Refresh token valid for 90 days (until refresh_token_expires_at)")
