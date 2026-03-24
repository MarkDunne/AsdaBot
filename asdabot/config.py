"""Configuration and persistent state for ASDA API access."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "asdabot"
ENV_FILE = CONFIG_DIR / ".env"
ACCOUNT_FILE = CONFIG_DIR / "account.json"
BROWSER_STATE_DIR = CONFIG_DIR / "browser-state"

load_dotenv(ENV_FILE)

# Algolia (public)
ALGOLIA_APP_ID = "8I6WSKCCNV"
ALGOLIA_API_KEY = "03e4272048dd17f771da37b57ff8a75e"
ALGOLIA_INDEX = "ASDA_PRODUCTS"

# SFCC proxy
SFCC_PROXY_BASE = "https://www.asda.com/mobify/proxy/ghs-api"
SFCC_ORG = "f_ecom_bjgs_prd"
SITE_ID = "ASDA_GROCERIES"

# ASDA customer profile API (Cloudflare-protected, only callable from browser)
PROFILE_API_URL = "https://api2.asda.com/external/customers/v1/profile?type=noncard"
PROFILE_API_KEY = "bc042eff107c4bca87dccb19ae707d16"

# Used for search stock levels before login — any valid store works
FALLBACK_STORE_ID = "4619"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_account() -> dict | None:
    return json.loads(ACCOUNT_FILE.read_text()) if ACCOUNT_FILE.exists() else None


def save_account(account: dict):
    ensure_config_dir()
    ACCOUNT_FILE.write_text(json.dumps(account, indent=2))


def get_store_id() -> str:
    account = load_account()
    if account:
        return account.get("store_id", FALLBACK_STORE_ID)
    return FALLBACK_STORE_ID


def get_card_cvv() -> str:
    return os.environ.get("ASDA_CARD_CVV", "")
