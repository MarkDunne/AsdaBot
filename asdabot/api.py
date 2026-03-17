"""ASDA API clients for authenticated operations via SFCC proxy."""

import time
import uuid

import httpx

from asdabot.auth import get_customer_id, get_slas_bearer_token
from asdabot.config import SFCC_ORG, SFCC_PROXY_BASE, SITE_ID

TIMEOUT = 30.0


def _headers() -> dict:
    return {
        "authorization": f"Bearer {get_slas_bearer_token()}",
        "content-type": "application/json",
        "correlation-id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0",
        "referer": "https://www.asda.com/",
        "origin": "https://www.asda.com",
    }


def _url(path: str) -> str:
    """Build a full SFCC proxy URL from a relative path."""
    return f"{SFCC_PROXY_BASE}/{path}?siteId={SITE_ID}"


def _basket_path(basket_id: str, suffix: str = "") -> str:
    return f"checkout/shopper-baskets/v1/organizations/{SFCC_ORG}/baskets/{basket_id}{suffix}"


def _customer_path(suffix: str = "") -> str:
    cid = get_customer_id()
    return f"customer/shopper-customers/v1/organizations/{SFCC_ORG}/customers/{cid}{suffix}"


# -- Basket --


def get_basket_id() -> str:
    resp = httpx.get(_url(_customer_path("/baskets")), headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    baskets = resp.json().get("baskets", [])
    if baskets:
        return baskets[0]["basketId"]
    raise RuntimeError("No active basket. Add an item on the website first.")


def ensure_basket_ready():
    """Associate customer with basket — required before PATCH operations."""
    basket_id = get_basket_id()
    resp = httpx.put(
        _url(_basket_path(basket_id, "/customer")), headers=_headers(), json={}, timeout=TIMEOUT
    )
    resp.raise_for_status()


def get_basket() -> dict:
    resp = httpx.get(_url(_basket_path(get_basket_id())), headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def add_to_basket(product_id: str, quantity: int = 1, price: float = 0.0) -> dict:
    basket_id = get_basket_id()
    body = [{"productId": product_id, "itemId": "", "quantity": quantity, "price": price}]
    resp = httpx.post(
        _url(_basket_path(basket_id, "/items")), headers=_headers(), json=body, timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def remove_from_basket(item_id: str) -> dict:
    basket_id = get_basket_id()
    resp = httpx.delete(
        _url(_basket_path(basket_id, f"/items/{item_id}")), headers=_headers(), timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def clear_basket() -> dict:
    """Remove all items from the basket."""
    basket = get_basket()
    result = basket
    for item in basket.get("productItems", []):
        result = remove_from_basket(item["itemId"])
    return result


# -- Delivery Slots --


def _patch_basket(body: dict, retries: int = 3) -> dict:
    """PATCH the basket with retry for transient 400s."""
    ensure_basket_ready()
    basket_id = get_basket_id()
    url = _url(_basket_path(basket_id))
    for attempt in range(retries):
        resp = httpx.patch(url, headers=_headers(), json=body, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 400 and attempt < retries - 1:
            time.sleep(1)
            continue
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise RuntimeError(f"Basket PATCH failed ({resp.status_code}): {detail}")
    return {}


def get_delivery_slots(address: dict, start_date: str, end_date: str) -> dict:
    return _patch_basket(
        {
            "c_deliverySlotListing": True,
            "c_deliveryMethod": "delivery",
            "c_slotStartDate": start_date,
            "c_slotEndDate": end_date,
            "c_deliveryLocation": address,
        }
    )


def book_slot(slot_id: str, shipping_address: dict) -> dict:
    return _patch_basket(
        {
            "c_slotId": slot_id,
            "c_shipments": [
                {
                    "shipmentId": "me",
                    "shippingMethod": {"id": "ASDADelivery"},
                    "shippingAddress": shipping_address,
                }
            ],
        }
    )


# -- Orders --


def get_orders() -> dict:
    resp = httpx.get(_url(_customer_path("/orders")), headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()
