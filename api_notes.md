# ASDA Grocery API - Reverse Engineering Notes

## API Surfaces

### 1. ASDA API (`api2.asda.com`)
- **Purpose**: Regulars, orders, customer profile
- **Auth Headers**:
  - `ocp-apim-subscription-key: bc042eff107c4bca87dccb19ae707d16`
  - `x-correlation-id: <uuid>`
  - `x-apisession-id: <uuid>`
  - Cookie: `ADB2C.AUTH_TOKEN` (JWT from Azure AD B2C)
- **Known Endpoints**:
  - `GET /external/subs/v1/product/regulars` — user's regular products (returns product_id + quantity)
  - `GET /external/ghs/order/v1/list?olderOrderLimit=6` — order history
  - `GET /external/customers/v1/profile?type=noncard` — customer profile

### 2. Salesforce Commerce Cloud Proxy (`www.asda.com/mobify/proxy/ghs-api/`)
- **Purpose**: Baskets, customers, checkout, product lists
- **Proxies to**: `ohwhuw6h.api.commercecloud.salesforce.com`
- **Auth**: Bearer token (SLAS JWT) in `authorization` header
- **Key IDs**:
  - Organization: `f_ecom_bjgs_prd`
  - Site: `ASDA_GROCERIES`
  - SFCC Client ID: `e68ca36d-6516-4704-b705-06b74f85ef2e` (from JWT)
- **Known Endpoints**:
  - `GET /customer/shopper-customers/v1/organizations/{org}/customers/{customerId}/product-lists?siteId=ASDA_GROCERIES`
  - `GET /customer/shopper-customers/v1/organizations/{org}/customers/{customerId}/baskets?siteId=ASDA_GROCERIES`
  - `GET /customer/shopper-customers/v1/organizations/{org}/customers/{customerId}?siteId=ASDA_GROCERIES`
  - `PATCH /customer/shopper-customers/v1/organizations/{org}/customers/{customerId}?siteId=ASDA_GROCERIES`
  - `PUT /checkout/shopper-baskets/v1/organizations/{org}/baskets/{basketId}/customer?siteId=ASDA_GROCERIES`
  - `PUT /shopper/shopper-context/v1/organizations/{org}/shopper-context/{shopperId}?siteId=ASDA_GROCERIES`

### 3. Algolia Product Search
- **App ID**: `8I6WSKCCNV`
- **API Key**: `03e4272048dd17f771da37b57ff8a75e` (search-only, public)
- **Index**: `ASDA_PRODUCTS`
- **Endpoint**: `POST /1/indexes/ASDA_PRODUCTS/query`
- **Product attributes available**: STATUS, BRAND, CIN (product ID), NAME, AVG_RATING, RATING_COUNT,
  PRICES.EN (PRICE, WASPRICE, PRICEPERUOM, OFFER type), SALES_TYPE, MAX_QTY, STOCK.<storeId>,
  IS_FROZEN, IS_BWS, PROMOS, PACK_SIZE, PRIMARY_TAXONOMY (CAT, DEPT, AISLE, SHELF), IMAGE_ID, etc.
- **Store/Region ID**: `4619` (used in STOCK filtering and store-specific queries)

### 4. Store OCAPI
- `GET /mobify/proxy/ghs-store-ocapi/s/Sites-ASDA_GROCERIES-Site/dw/shop/v23_2/stores/(4619)?client_id=8dfc5903-ef23-4e14-a4c3-a4493040adac`

### 5. Other
- **Criteo Retail Media**: Used for sponsored product placements
- **Amplience CDN**: Navigation and content delivery
- **Store static data**: `GET https://ghs-mm.asda.com/static/4619.json`

## Auth Flow

1. User logs in via Azure AD B2C (`login.asda.com`) with Cloudflare Turnstile captcha
2. OAuth2 authorization code flow → redirect to `/shopper/callback`
3. Tokens set as cookies:
   - `ADB2C.AUTH_TOKEN` — JWT (30min expiry)
   - `ADB2C.REFRESH_TOKEN` — for token renewal
   - `SLAS.CUSTOMER_ID` — Salesforce customer ID
   - `SLAS.REFRESH_TOKEN` — Salesforce refresh token
4. SLAS Bearer token used for SFCC API calls (same 30min expiry window)

## Key Identifiers
- Azure AD B2C Client ID: `8121a3d6-3e1c-4992-9b43-c0bf555159f5`
- SFCC Org: `f_ecom_bjgs_prd`
- SFCC Client ID: `e68ca36d-6516-4704-b705-06b74f85ef2e`
- Store OCAPI Client ID: `8dfc5903-ef23-4e14-a4c3-a4493040adac`
- Site ID: `ASDA_GROCERIES`
- Store/Region: `4619`
