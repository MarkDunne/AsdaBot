"""Product search via Algolia's public REST API — no auth required."""

import json
import time
from urllib.parse import urlencode

import httpx

from asdabot.config import ALGOLIA_API_KEY, ALGOLIA_APP_ID, ALGOLIA_INDEX, get_store_id

SEARCH_URL = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"

PRODUCT_ATTRIBUTES = [
    "STATUS",
    "BRAND",
    "CIN",
    "NAME",
    "AVG_RATING",
    "RATING_COUNT",
    "PRICES.EN",
    "SALES_TYPE",
    "MAX_QTY",
    "STOCK",
    "IS_FROZEN",
    "IS_BWS",
    "PROMOS.EN",
    "PACK_SIZE",
    "PRIMARY_TAXONOMY",
    "IMAGE_ID",
    "PRODUCT_TYPE",
]


def _query(params: dict) -> dict:
    resp = httpx.post(
        SEARCH_URL,
        headers={
            "x-algolia-application-id": ALGOLIA_APP_ID,
            "x-algolia-api-key": ALGOLIA_API_KEY,
        },
        json={"params": urlencode(params)},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _build_filters(store_id: str) -> str:
    now = int(time.time())
    return (
        "(STATUS:A OR STATUS:I) "
        "AND NOT DISPLAY_ONLINE:false "
        f"AND NOT UNTRAITED_STORES:{store_id} "
        f"AND (IS_FTO=0 OR PURCHASE_END_DATE_FTO > {now}) "
        "AND (NOT PRIMARY_TAXONOMY.SHELF_ID:1215685231732 "
        "AND NOT SECONDARY_TAXONOMY.SHELF_ID:1215685231732) "
        f"AND (START_DATE<{now} OR CS_YES=1) "
        f"AND END_DATE>{now}"
    )


def search_products(
    query: str,
    hits_per_page: int = 20,
    page: int = 0,
    store_id: str | None = None,
) -> dict:
    store_id = store_id or get_store_id()
    return _query(
        {
            "query": query,
            "hitsPerPage": hits_per_page,
            "page": page,
            "attributesToRetrieve": json.dumps(PRODUCT_ATTRIBUTES),
            "filters": _build_filters(store_id),
            "optionalFilters": json.dumps([f"STOCK.{store_id}:1<score=50000>"]),
            "facets": json.dumps(
                ["BRAND", "PRIMARY_TAXONOMY.DEPT_NAME", "PRIMARY_TAXONOMY.AISLE_NAME"]
            ),
        }
    )


def lookup_products(
    product_ids: list[str],
    store_id: str | None = None,
) -> dict:
    """Look up specific products by CIN (product ID)."""
    store_id = store_id or get_store_id()
    cin_filter = " OR ".join(f"CIN:'{pid}'" for pid in product_ids)
    now = int(time.time())
    filters = (
        f"({cin_filter}) "
        "AND (STATUS:A OR STATUS:I) "
        "AND NOT DISPLAY_ONLINE:false "
        f"AND NOT UNTRAITED_STORES:{store_id} "
        f"AND (IS_FTO=0 OR PURCHASE_END_DATE_FTO > {now}) "
        f"AND (START_DATE<{now} OR CS_YES=1) "
        f"AND END_DATE>{now}"
    )
    return _query(
        {
            "query": "",
            "hitsPerPage": len(product_ids),
            "attributesToRetrieve": json.dumps(PRODUCT_ATTRIBUTES),
            "filters": filters,
        }
    )
