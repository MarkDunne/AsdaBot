# ASDA Grocery API - Reverse Engineering Notes

## API Surfaces

### 1. ASDA API (`api2.asda.com`)
- **Purpose**: Regulars, orders, customer profile
- **Auth Headers**:
  - `ocp-apim-subscription-key: bc042eff...`
  - `x-correlation-id: <uuid>`
  - `x-apisession-id: <uuid>`
  - Cookie: `ADB2C.AUTH_TOKEN` (JWT from Azure AD B2C)
- **Known Endpoints**:
  - `GET /external/subs/v1/product/regulars` — user's regular products
  - `GET /external/ghs/order/v1/list?olderOrderLimit=6` — order history
  - `GET /external/customers/v1/profile?type=noncard` — customer profile
- **Limitation**: Protected by Cloudflare. Returns 425 challenge from CLI.
  Not usable for regulars/orders — use SFCC proxy instead.

### 2. Salesforce Commerce Cloud Proxy (`www.asda.com/mobify/proxy/ghs-api/`)
- **Purpose**: Baskets, customers, checkout, slots, orders
- **Proxies to**: `ohwhuw6h.api.commercecloud.salesforce.com`
- **Auth**: Bearer token (SLAS JWT) in `authorization` header
- **Key IDs**:
  - Organization: `f_ecom_bjgs_prd`
  - Site: `ASDA_GROCERIES`
  - SFCC Client ID: `e68ca36d-6516-4704-b705-06b74f85ef2e`
- **Known Endpoints**:
  - `GET .../customers/{id}/baskets` — list baskets
  - `GET .../customers/{id}/orders` — order history (works without Cloudflare)
  - `POST .../baskets/{id}/items` — add items to basket
  - `DELETE .../baskets/{id}/items/{itemId}` — remove item
  - `PATCH .../baskets/{id}` — update basket (slots, slot booking, checkout prep)
  - `PUT .../baskets/{id}/customer` — associate customer with basket (required before PATCH ops)
  - `PUT .../baskets/{id}/billing-address` — set billing address
  - `POST .../baskets/{id}/payment-instruments` — attach payment
  - `POST .../orders` — place order
  - `GET .../orders/{orderNo}` — get order details
- **Important**: Only ONE basket allowed per customer. Cannot create a second.
- **Important**: Must call `PUT .../baskets/{id}/customer` before any PATCH operations
  on a new basket, otherwise get 400 errors.

### 3. Algolia Product Search
- **App ID**: `8I6WSKCCNV`
- **API Key**: `03e4272048dd17f771da37b57ff8a75e` (search-only, public)
- **Index**: `ASDA_PRODUCTS` (also `Products_query_suggestions`)
- **Endpoint**: `POST /1/indexes/ASDA_PRODUCTS/query`
- **Multi-index**: `POST /1/indexes/*/queries`
- **Product attributes**: STATUS, BRAND, CIN, NAME, AVG_RATING, RATING_COUNT,
  PRICES.EN (PRICE, WASPRICE, PRICEPERUOM, OFFER), SALES_TYPE, MAX_QTY,
  STOCK.<storeId>, IS_FROZEN, IS_BWS, PROMOS, PACK_SIZE, PRIMARY_TAXONOMY, IMAGE_ID
- **Store/Region ID**: `4619` (default), `4582` (Stevenage — used for Hitchin deliveries)
- **Filters**: Must include status, date range, store exclusions. See `search.py`.

## Auth Flow

### Initial Login
1. User logs in via Azure AD B2C (`login.asda.com`) with Cloudflare Turnstile
2. OAuth2 authorization code flow → redirect to `/shopper/callback`
3. Tokens set as cookies:
   - `ADB2C.AUTH_TOKEN` — JWT (30min expiry)
   - `ADB2C.REFRESH_TOKEN`
   - `SLAS.AUTH_TOKEN` — SFCC Bearer token (30min)
   - `SLAS.REFRESH_TOKEN` — 90 days, rotating
   - `SLAS.CUSTOMER_ID`, `SLAS.USID`

### Token Refresh
- **Endpoint**: `POST /shopper/auth/v1/organizations/{org}/oauth2/token`
- **Body**: `grant_type=refresh_token&refresh_token=...&client_id=...`
- **Returns**: New access_token (30min), new refresh_token (90 days, rotating),
  idp_access_token (ADB2C token — refreshed automatically!)
- **Rotating tokens**: Each refresh invalidates the old refresh token and returns
  a new one. Must save the new refresh token immediately.
- **90-day rolling window**: As long as you refresh at least once every 90 days,
  the session persists indefinitely.

## Delivery Slots

### Get Available Slots
- `PATCH .../baskets/{id}` with body:
  ```json
  {
    "c_deliverySlotListing": true,
    "c_deliveryMethod": "delivery",
    "c_slotStartDate": "2026-03-17T00:00:00Z",
    "c_slotEndDate": "2026-03-20T00:00:00Z",
    "c_deliveryLocation": {
      "address1": "...", "city": "...", "countryCode": "GB",
      "asdaLatitude": "...", "asdaLongitude": "...", "asdaPostcode": "..."
    }
  }
  ```
- **Max date range: 4 days.** API rejects anything wider.
- Response includes `c_deliverySlotsData.slot_days[].slots[]` with:
  `slot_id`, `start_time`, `end_time`, `available`, `slot_price`, `final_price`

### Book a Slot
- `PATCH .../baskets/{id}` with body:
  ```json
  {
    "c_slotId": "<base64 slot ID>",
    "c_shipments": [{
      "shipmentId": "me",
      "shippingMethod": {"id": "ASDADelivery"},
      "shippingAddress": { ... full address with custom fields ... }
    }]
  }
  ```
- Slot IDs are base64-encoded and include the basket ID, address, and time window.
  They are address-specific — re-list after changing address.

## Checkout / Payment Flow

### Full Browser Checkout Sequence (captured)
1. `PATCH /baskets/{id}` — get delivery slots
2. `PATCH /baskets/{id}` — book slot + set shipping address
3. `PATCH /baskets/{id}/shipments/me` — update shipment
4. `PATCH /baskets/{id}` — checkout prep (Ingenico token collection, device payload)
5. `PUT /baskets/{id}/billing-address` — set billing address
6. `POST /baskets/{id}/payment-instruments` — attach payment (with ~42KB device payload)
7. `POST /orders` — `{"basketId": "..."}` creates the order

### Payment (Ingenico/Worldline)
- ASDA uses **Ingenico Hosted Tokenization** (payment.direct.ingenico.com)
- Card tokens stored as `creditCardToken` (e.g. `3412653ae602fa41005`)
- The hosted tokenization renders in an iframe (`name="htpIframe0"`)
- CVV input is inside the iframe: `input[aria-label="Card verification code"]`
- The `c_devicePayload` (~42KB encrypted blob) is generated by Ingenico's JS SDK
- **Without the device payload, payment fails** (order status: "failed")

### Why Pure API Checkout Fails
- ASDA's custom Ingenico SFCC cartridge requires hosted tokenization session + device fingerprint
- The open-source Ingenico SFCC cartridge (GitHub) is a different/older version
- ASDA's custom attributes (`c_devicePayload`, `c_ingenicoTokenCollection`,
  `c_ingenicoOgonePaymentIsZeroAuth`) don't exist in the open-source version
- No "merchant-initiated transaction" code path exists

### Working Solution: Camoufox Headless Browser
- **Camoufox** (anti-detect Firefox, `pip install camoufox`) passes Cloudflare Turnstile
- Persistent context (`user_data_dir`) preserves login session across runs
- Flow: navigate to order-summary → find Ingenico iframe → fill CVV → click Confirm
- CVV field is in iframe `name="htpIframe0"`, targetable via
  `page.frame(name="htpIframe0").locator('input[aria-label="Card verification code"]')`
- Button `data-testid="os-confirm-order-btn"` enables after CVV is filled
- Confirmation page URL contains `/groceries/checkout/order-confirmation`

### Headless Browser Findings (what didn't work)
- **Playwright's Chromium**: Flagged by Cloudflare Turnstile
- **Playwright with `channel="chrome"`**: Adds `--enable-automation` flags, detected
- **Chrome `--headless=new`**: ASDA's React SPA renders blank page
- **Chrome with `--user-data-dir`**: Session cookies don't persist between launches
- **Camoufox (Firefox-based)**: Works! Passes Cloudflare, sessions persist, SPA renders

## Orders

- SFCC orders endpoint returns `status` (`created`, `failed`) but does NOT track cancellations
- Cancellations happen in ASDA's OMS, not reflected back in SFCC
- Useful custom fields on orders:
  - `c_ingenicoOgoneStatusCategory` — payment status (e.g. `AUTHORIZED`, `PENDING_CAPTURE`)
  - `c_asdaBookedSlotDetail` — JSON with delivery slot times
  - `c_asdaAmendCutoffDateTime` — deadline to amend the order
  - `c_ingenicoOgoneIsCancellable` — whether order can be cancelled
  - `c_asda_oms_exported` — whether order has been sent to ASDA's OMS

## Key Identifiers
- Azure AD B2C Client ID: `8121a3d6-...`
- SFCC Org: `f_ecom_bjgs_prd`
- SFCC Client ID (SLAS): `e68ca36d-...`
- Store OCAPI Client ID: `8dfc5903-...`
- Site ID: `ASDA_GROCERIES`
- SLAS Token Refresh URL: `.../shopper/auth/v1/organizations/f_ecom_bjgs_prd/oauth2/token`
- Ingenico iframe name: `htpIframe0`
- Confirm order button: `button[data-testid="os-confirm-order-btn"]`
