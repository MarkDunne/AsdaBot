# asdabot

A CLI for fully autonomous grocery shopping on ASDA. Search products, manage your basket, book delivery slots, and place orders — all from the terminal.

## How it works

- **Search & basket**: Direct API calls to ASDA's Algolia search index and Salesforce Commerce Cloud backend
- **Delivery slots**: API-driven slot listing and booking
- **Payment**: Headless [Camoufox](https://github.com/nickolaj-jepsen/camoufox) browser (anti-detect Firefox) handles the Ingenico payment flow, including CVV entry and 3DS
- **Auth**: OAuth2 tokens with 90-day rolling refresh — log in once, stay authenticated for months

## Setup

```bash
# Install
uv sync
uv run camoufox fetch

# One-time login — opens a browser, you log in to ASDA
uv run asda auth login

# Set your delivery address (interactive)
uv run asda address set

# Set your card CVV
echo "ASDA_CARD_CVV=1234" > ~/.config/asdabot/.env
```

## Usage

```bash
# Search for products
uv run asda search "milk"

# Build your basket
uv run asda basket add 165468          # Add by product CIN
uv run asda basket add 166781 -q 2    # Add 2x eggs
uv run asda basket show               # View basket

# Book a delivery slot
uv run asda slots list                 # See available slots
uv run asda slots book <SLOT_ID>       # Book one

# Place the order
uv run asda checkout -y                # Headless browser checkout
uv run asda orders                     # Verify it went through
```

## All commands

| Command | Description |
|---------|-------------|
| `search <query>` | Search products (no auth needed) |
| `basket show` | View current basket |
| `basket add <CIN>` | Add product to basket |
| `basket remove <ITEM_ID>` | Remove item from basket |
| `basket clear` | Clear all items |
| `slots list` | List available delivery slots (max 3 days) |
| `slots book <SLOT_ID>` | Book a delivery slot |
| `checkout -y` | Place order via headless browser |
| `orders` | Show recent orders |
| `auth login` | Open browser for login (one-time) |
| `auth status` | Check token expiry |
| `auth refresh` | Manually refresh tokens |
| `address set` | Set delivery address (interactive) |
| `address show` | Show saved address |

## Architecture

```
                    ┌─────────────┐
                    │   Algolia   │  Product search (public API)
                    └──────┬──────┘
                           │
┌──────────┐    ┌──────────┴──────────┐    ┌─────────────────┐
│ asdabot  │───>│   SFCC Proxy API    │───>│  Salesforce CC   │
│   CLI    │    │  (basket, slots,    │    │  (commerce       │
│          │    │   orders)           │    │   backend)       │
└────┬─────┘    └─────────────────────┘    └─────────────────┘
     │
     │ checkout only
     v
┌──────────┐    ┌─────────────────────┐
│ Camoufox │───>│  Ingenico/Worldline │  Payment processing
│ (headless│    │  (hosted iframe)    │  CVV + 3DS + device
│  Firefox)│    └─────────────────────┘  fingerprint
└──────────┘
```

## Auth lifecycle

- **Access tokens** expire every 30 minutes — auto-refreshed transparently
- **Refresh tokens** last 90 days with a rolling window — each refresh resets the clock
- **Browser session** (Camoufox profile) persists Cloudflare clearance and ASDA login cookies
- As long as you use the CLI at least once every 90 days, no re-login needed

## Configuration

All config lives in `~/.config/asdabot/`:

| File | Purpose |
|------|---------|
| `tokens.json` | SLAS/ADB2C auth tokens |
| `address.json` | Delivery address |
| `.env` | Secrets (CVV) |
| `browser-state/` | Camoufox persistent browser profile |

## Technical notes

See [api_notes.md](api_notes.md) for detailed reverse engineering notes on ASDA's API surface, auth flow, payment system, and the headless browser challenges we solved.

## Limitations

- **One basket per customer** — ASDA's SFCC backend enforces this
- **Slot queries limited to 4-day window** — API rejects wider ranges
- **Payment requires browser** — Ingenico's device fingerprinting can't be replicated via API
- **Cancellation status** — SFCC doesn't reflect cancellations made on the ASDA website
- **Browser session expiry** — if Camoufox session expires, run `asda auth login` again
