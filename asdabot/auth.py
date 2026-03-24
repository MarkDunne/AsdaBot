"""Authentication — token management and automatic refresh."""

import time

import httpx

from asdabot.config import SFCC_ORG, SFCC_PROXY_BASE, load_account, save_account

SLAS_CLIENT_ID = "e68ca36d-6516-4704-b705-06b74f85ef2e"
TOKEN_REFRESH_URL = f"{SFCC_PROXY_BASE}/shopper/auth/v1/organizations/{SFCC_ORG}/oauth2/token"


class AuthError(Exception):
    """Raised when authentication is missing or invalid."""


def require_account() -> dict:
    """Load account or raise AuthError if not logged in."""
    account = load_account()
    if not account:
        raise AuthError("Not logged in. Run 'asdabot auth login' first.")
    return account


def refresh_tokens() -> dict:
    """Refresh SLAS tokens. Returns updated account."""
    account = require_account()
    tokens = account.get("tokens", {})

    refresh_token = tokens.get("slas_refresh")
    if not refresh_token:
        raise AuthError("No refresh token. Run 'asdabot auth login' first.")

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

    account["tokens"] = {
        "slas_auth": f"Bearer {data['access_token']}",
        "slas_refresh": data["refresh_token"],
        "customer_id": data["customer_id"],
        "usid": data["usid"],
        "adb2c_auth": data.get("idp_access_token", ""),
        "expires_at": time.time() + data["expires_in"],
        "refresh_expires_at": time.time() + data["refresh_token_expires_in"],
    }
    save_account(account)
    return account


def ensure_valid_tokens() -> dict:
    """Return valid account, refreshing tokens if expired."""
    account = require_account()
    tokens = account.get("tokens", {})
    if time.time() > (tokens.get("expires_at", 0) - 60):
        account = refresh_tokens()
    return account


def get_slas_bearer_token() -> str:
    """Get a valid SLAS bearer token, refreshing if needed."""
    tokens = ensure_valid_tokens().get("tokens", {})
    return tokens.get("slas_auth", "").removeprefix("Bearer ")


def get_customer_id() -> str:
    return ensure_valid_tokens().get("tokens", {}).get("customer_id", "")
