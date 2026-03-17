"""Authentication — token management and automatic refresh."""

import sys
import time

import httpx

from asdabot.config import SFCC_ORG, SFCC_PROXY_BASE, load_tokens, save_tokens

SLAS_CLIENT_ID = "e68ca36d-6516-4704-b705-06b74f85ef2e"
TOKEN_REFRESH_URL = f"{SFCC_PROXY_BASE}/shopper/auth/v1/organizations/{SFCC_ORG}/oauth2/token"


def refresh_tokens() -> dict:
    """Refresh SLAS tokens. Also refreshes ADB2C via idp_access_token."""
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run 'asda auth login' first.")
        sys.exit(1)

    refresh_token = tokens.get("SLAS.REFRESH_TOKEN")
    if not refresh_token:
        print("No refresh token. Run 'asda auth login' first.")
        sys.exit(1)

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
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run 'asda auth login' first.")
        sys.exit(1)
    expires_at = tokens.get("expires_at", 0)
    if time.time() > (expires_at - 60):
        tokens = refresh_tokens()
    return tokens


def get_slas_bearer_token() -> str:
    """Get a valid SLAS bearer token, refreshing if needed."""
    token = ensure_valid_tokens().get("SLAS.AUTH_TOKEN", "")
    return token.removeprefix("Bearer ")


def get_customer_id() -> str:
    return ensure_valid_tokens().get("SLAS.CUSTOMER_ID", "")
