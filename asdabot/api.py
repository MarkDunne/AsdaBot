"""ASDA API clients for authenticated operations."""

import time
import uuid

import httpx

from asdabot.auth import get_adb2c_token, get_customer_id, get_slas_bearer_token
from asdabot.config import (
    ASDA_API_BASE,
    ASDA_API_SUBSCRIPTION_KEY,
    SFCC_ORG,
    SFCC_PROXY_BASE,
    SITE_ID,
)

TIMEOUT = 30.0


def _sfcc_headers() -> dict:
    return {
        "authorization": f"Bearer {get_slas_bearer_token()}",
        "content-type": "application/json",
        "correlation-id": str(uuid.uuid4()),
        "x-apisession-id": str(uuid.uuid4()),
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "referer": "https://www.asda.com/",
        "origin": "https://www.asda.com",
    }


def _asda_api_headers() -> dict:
    return {
        "ocp-apim-subscription-key": ASDA_API_SUBSCRIPTION_KEY,
        "x-correlation-id": str(uuid.uuid4()),
        "x-apisession-id": str(uuid.uuid4()),
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "referer": "https://www.asda.com/",
        "origin": "https://www.asda.com",
    }


def _asda_api_cookies() -> dict:
    return {"ADB2C.AUTH_TOKEN": get_adb2c_token()}


def _basket_url(basket_id: str) -> str:
    return (
        f"{SFCC_PROXY_BASE}/checkout/shopper-baskets/v1"
        f"/organizations/{SFCC_ORG}/baskets/{basket_id}"
        f"?siteId={SITE_ID}"
    )


# -- Basket --


def get_baskets() -> dict:
    customer_id = get_customer_id()
    url = (
        f"{SFCC_PROXY_BASE}/customer/shopper-customers/v1"
        f"/organizations/{SFCC_ORG}/customers/{customer_id}"
        f"/baskets?siteId={SITE_ID}"
    )
    resp = httpx.get(url, headers=_sfcc_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_basket_id() -> str:
    baskets = get_baskets()
    if baskets.get("baskets"):
        return baskets["baskets"][0]["basketId"]
    raise RuntimeError("No active basket found. Add an item on the website first.")


def ensure_basket_ready():
    """Associate the customer with the basket — required before slot/checkout operations.

    The browser does this on every page load. Without it, PATCH operations
    on the basket can fail with 400.
    """
    basket_id = get_basket_id()
    url = (
        f"{SFCC_PROXY_BASE}/checkout/shopper-baskets/v1"
        f"/organizations/{SFCC_ORG}/baskets/{basket_id}"
        f"/customer?siteId={SITE_ID}"
    )
    resp = httpx.put(url, headers=_sfcc_headers(), json={}, timeout=TIMEOUT)
    resp.raise_for_status()


def clear_basket() -> dict:
    """Remove all items from the current basket.

    SFCC only allows one basket per customer, so we can't create a new one.
    Instead we clear the existing basket by removing all items.
    """
    basket = get_basket()
    items = basket.get("productItems", [])
    result = basket
    for item in items:
        result = remove_from_basket(item["itemId"])
    return result


def get_basket() -> dict:
    basket_id = get_basket_id()
    resp = httpx.get(_basket_url(basket_id), headers=_sfcc_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def add_to_basket(product_id: str, quantity: int = 1, price: float = 0.0) -> dict:
    basket_id = get_basket_id()
    url = (
        f"{SFCC_PROXY_BASE}/checkout/shopper-baskets/v1"
        f"/organizations/{SFCC_ORG}/baskets/{basket_id}"
        f"/items?siteId={SITE_ID}"
    )
    body = [{"productId": product_id, "itemId": "", "quantity": quantity, "price": price}]
    resp = httpx.post(url, headers=_sfcc_headers(), json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def remove_from_basket(item_id: str) -> dict:
    basket_id = get_basket_id()
    url = (
        f"{SFCC_PROXY_BASE}/checkout/shopper-baskets/v1"
        f"/organizations/{SFCC_ORG}/baskets/{basket_id}"
        f"/items/{item_id}?siteId={SITE_ID}"
    )
    resp = httpx.delete(url, headers=_sfcc_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# -- Delivery Slots --


def _patch_basket_with_retry(body: dict, max_retries: int = 3) -> dict:
    """PATCH the basket with retry logic for transient 400 errors."""
    ensure_basket_ready()
    basket_id = get_basket_id()
    for attempt in range(max_retries):
        resp = httpx.patch(
            _basket_url(basket_id),
            headers=_sfcc_headers(),
            json=body,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 400 and attempt < max_retries - 1:
            time.sleep(1)
            continue
        # Final attempt or non-400 error — raise with details
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        raise RuntimeError(f"Basket PATCH failed ({resp.status_code}): {detail}")
    return {}  # unreachable


def get_delivery_slots(
    address: dict,
    start_date: str,
    end_date: str,
) -> dict:
    """Fetch available delivery slots for an address and date range.

    address should have: address1, address2, city, countryCode,
                         asdaLatitude, asdaLongitude, asdaPostcode
    Dates should be ISO format: "2026-03-16T00:00:00Z"
    """
    body = {
        "c_deliverySlotListing": True,
        "c_deliveryMethod": "delivery",
        "c_slotStartDate": start_date,
        "c_slotEndDate": end_date,
        "c_deliveryLocation": address,
    }
    return _patch_basket_with_retry(body)


def book_slot(slot_id: str, shipping_address: dict) -> dict:
    """Book a delivery slot with full shipping address."""
    body = {
        "c_slotId": slot_id,
        "c_shipments": [
            {
                "shipmentId": "me",
                "shippingMethod": {"id": "ASDADelivery"},
                "shippingAddress": shipping_address,
            }
        ],
    }
    return _patch_basket_with_retry(body)


# -- Checkout --


def set_billing_address(billing_address: dict) -> dict:
    basket_id = get_basket_id()
    url = (
        f"{SFCC_PROXY_BASE}/checkout/shopper-baskets/v1"
        f"/organizations/{SFCC_ORG}/baskets/{basket_id}"
        f"/billing-address?siteId={SITE_ID}&useAsShipping=false"
    )
    resp = httpx.put(url, headers=_sfcc_headers(), json=billing_address, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def add_payment_instrument(card_token: str, billing_address_id: str) -> dict:
    basket_id = get_basket_id()
    url = (
        f"{SFCC_PROXY_BASE}/checkout/shopper-baskets/v1"
        f"/organizations/{SFCC_ORG}/baskets/{basket_id}"
        f"/payment-instruments?siteId={SITE_ID}"
    )
    body = {
        "paymentMethodId": "INGENICO_OGONE_CARD",
        "c_savedCardToProfile": True,
        "c_removeCurrentCards": True,
        "c_isFromDeliveryPass": False,
        "c_billingAddressId": billing_address_id,
    }
    resp = httpx.post(url, headers=_sfcc_headers(), json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def place_order() -> dict:
    """Place the order from the current basket."""
    basket_id = get_basket_id()
    url = (
        f"{SFCC_PROXY_BASE}/checkout/shopper-orders/v1"
        f"/organizations/{SFCC_ORG}/orders?siteId={SITE_ID}"
    )
    body = {
        "basketId": basket_id,
        "c_screenHeight": 1440,
        "c_screenWidth": 3440,
        "c_colorDepth": 24,
        "c_timezoneOffsetUtcMinutes": 0,
    }
    resp = httpx.post(url, headers=_sfcc_headers(), json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# -- Regulars & Orders --


def get_regulars() -> dict:
    """Get regular products. Falls back gracefully if Cloudflare blocks."""
    url = f"{ASDA_API_BASE}/external/subs/v1/product/regulars"
    resp = httpx.get(url, headers=_asda_api_headers(), cookies=_asda_api_cookies(), timeout=TIMEOUT)
    if resp.status_code == 425 or "challenge-platform" in resp.text:
        raise RuntimeError(
            "api2.asda.com is blocked by Cloudflare. "
            "This endpoint requires a browser session cookie (cf_clearance). "
            "Try browsing asda.com first, or use 'asda search' instead."
        )
    resp.raise_for_status()
    return resp.json()


def get_orders() -> dict:
    """Get recent orders via SFCC proxy."""
    customer_id = get_customer_id()
    url = (
        f"{SFCC_PROXY_BASE}/customer/shopper-customers/v1"
        f"/organizations/{SFCC_ORG}/customers/{customer_id}"
        f"/orders?siteId={SITE_ID}"
    )
    resp = httpx.get(url, headers=_sfcc_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()
