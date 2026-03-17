"""Configuration and token management for ASDA API access."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "asdabot"
ENV_FILE = CONFIG_DIR / ".env"

# Load secrets from .env
load_dotenv(ENV_FILE)
TOKEN_FILE = CONFIG_DIR / "tokens.json"
ADDRESS_FILE = CONFIG_DIR / "address.json"
BROWSER_STATE_DIR = CONFIG_DIR / "browser-state"

# Algolia (public, no auth needed)
ALGOLIA_APP_ID = "8I6WSKCCNV"
ALGOLIA_API_KEY = "03e4272048dd17f771da37b57ff8a75e"
ALGOLIA_INDEX = "ASDA_PRODUCTS"

# ASDA API
ASDA_API_BASE = "https://api2.asda.com"
ASDA_API_SUBSCRIPTION_KEY = "bc042eff107c4bca87dccb19ae707d16"

# Salesforce Commerce Cloud (via proxy)
SFCC_PROXY_BASE = "https://www.asda.com/mobify/proxy/ghs-api"
SFCC_ORG = "f_ecom_bjgs_prd"
SITE_ID = "ASDA_GROCERIES"

# Default store
DEFAULT_STORE_ID = "4619"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def save_tokens(tokens: dict):
    ensure_config_dir()
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def load_tokens() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    return json.loads(TOKEN_FILE.read_text())


def save_address(address: dict):
    ensure_config_dir()
    ADDRESS_FILE.write_text(json.dumps(address, indent=2))


def load_address() -> dict | None:
    if not ADDRESS_FILE.exists():
        return None
    return json.loads(ADDRESS_FILE.read_text())


def get_card_cvv() -> str:
    return os.environ.get("ASDA_CARD_CVV", "")
