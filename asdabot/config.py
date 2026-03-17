"""Configuration and persistent state for ASDA API access."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "asdabot"
ENV_FILE = CONFIG_DIR / ".env"
TOKEN_FILE = CONFIG_DIR / "tokens.json"
ADDRESS_FILE = CONFIG_DIR / "address.json"
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
DEFAULT_STORE_ID = "4619"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def _save_json(path: Path, data: dict):
    ensure_config_dir()
    path.write_text(json.dumps(data, indent=2))


def load_tokens() -> dict | None:
    return _load_json(TOKEN_FILE)


def save_tokens(tokens: dict):
    _save_json(TOKEN_FILE, tokens)


def load_address() -> dict | None:
    return _load_json(ADDRESS_FILE)


def save_address(address: dict):
    _save_json(ADDRESS_FILE, address)


def get_card_cvv() -> str:
    return os.environ.get("ASDA_CARD_CVV", "")


def build_delivery_location(addr: dict) -> dict:
    """Build the delivery location dict for slot queries."""
    return {
        "address1": addr["address1"],
        "address2": addr.get("address2", ""),
        "city": addr["city"],
        "countryCode": "GB",
        "asdaLatitude": addr["asdaLatitude"],
        "asdaLongitude": addr["asdaLongitude"],
        "asdaPostcode": addr["asdaPostcode"],
    }


def build_shipping_address(addr: dict) -> dict:
    """Build the full shipping address dict for slot booking."""
    return {
        "address1": addr["address1"],
        "address2": addr.get("address2", ""),
        "city": addr["city"],
        "countryCode": "GB",
        "postalCode": addr["postalCode"],
        "stateCode": "United Kingdom",
        "firstName": addr["firstName"],
        "lastName": addr["lastName"],
        "custom": {
            "asdaCrmAddressId": addr.get("asdaCrmAddressId", ""),
            "asdaAddressType": addr.get("asdaAddressType", "House"),
            "asdaDeliveryNote": "",
            "asdaLatitude": addr["asdaLatitude"],
            "asdaLongitude": addr["asdaLongitude"],
            "asdaIsPrimaryAddress": True,
        },
    }
