"""Product search via Algolia — no auth required."""

import time

from algoliasearch.search.client import SearchClientSync

from asdabot.config import ALGOLIA_API_KEY, ALGOLIA_APP_ID, ALGOLIA_INDEX, get_store_id

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
    client = SearchClientSync(ALGOLIA_APP_ID, ALGOLIA_API_KEY)
    try:
        result = client.search_single_index(
            index_name=ALGOLIA_INDEX,
            search_params={
                "query": query,
                "hitsPerPage": hits_per_page,
                "page": page,
                "attributesToRetrieve": PRODUCT_ATTRIBUTES,
                "filters": _build_filters(store_id),
                "optionalFilters": [f"STOCK.{store_id}:1<score=50000>"],
                "facets": [
                    "BRAND",
                    "PRIMARY_TAXONOMY.DEPT_NAME",
                    "PRIMARY_TAXONOMY.AISLE_NAME",
                ],
            },
        )
        return result.to_dict()
    finally:
        client.close()


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
    client = SearchClientSync(ALGOLIA_APP_ID, ALGOLIA_API_KEY)
    try:
        result = client.search_single_index(
            index_name=ALGOLIA_INDEX,
            search_params={
                "query": "",
                "hitsPerPage": len(product_ids),
                "attributesToRetrieve": PRODUCT_ATTRIBUTES,
                "filters": filters,
            },
        )
        return result.to_dict()
    finally:
        client.close()
