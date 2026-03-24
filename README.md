# AsdaBot

Autonomous grocery shopping on ASDA from the terminal.

## Prerequisites

You need an existing ASDA Groceries account with:
- A saved delivery address
- A saved payment card

## Install

```bash
git clone https://github.com/MarkDunne/AsdaBot
cd AsdaBot
uv sync
```

## Setup

```bash
uv run asdabot auth login       # Opens browser — log in to ASDA
echo "ASDA_CARD_CVV=1234" > ~/.config/asdabot/.env
```

Login automatically fetches your delivery address and store from your ASDA account.

## Usage

```bash
uv run asdabot search "milk"
uv run asdabot basket add 165468
uv run asdabot slots list
uv run asdabot slots book <SLOT_ID>
uv run asdabot checkout -y
```

## Claude Code plugin

Works as a [Claude Code plugin](https://code.claude.com/docs/en/plugins.md) — Claude can manage your grocery shopping autonomously.

```bash
claude --plugin-dir /path/to/AsdaBot
```

## Commands

All commands are run as `uv run asdabot <command>`.

| Command | Description |
|---------|-------------|
| `search <query>` | Search products (no auth needed) |
| `search <query> -d` | Search with product descriptions |
| `product <CIN>` | Full product details by CIN (Customer Item Number) |
| `basket show` | View current basket |
| `basket add <CIN>` | Add product to basket |
| `basket remove <ITEM_ID>` | Remove item from basket |
| `basket clear` | Clear all items |
| `slots list` | List available delivery slots (max 3 days) |
| `slots book <SLOT_ID>` | Book a delivery slot |
| `checkout -y` | Place order via headless browser |
| `orders` | Show recent orders with payment status |
| `auth login` | Open browser for login (one-time) |
| `auth status` | Check token expiry and account info |
| `auth refresh` | Manually refresh tokens |

## Architecture

```
                    ┌─────────────┐
                    │   Algolia   │  Product search (public API)
                    └──────┬──────┘
                           │
┌──────────┐    ┌──────────┴──────────┐    ┌─────────────────┐
│ asdabot  │───>│   SFCC Proxy API    │───>│  Salesforce CC  │
│   CLI    │    │  (basket, slots,    │    │  (commerce      │
│          │    │   orders)           │    │   backend)      │
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

- **Search & basket**: Direct API calls to ASDA's Algolia search index and Salesforce Commerce Cloud (SFCC) backend
- **Delivery slots**: API-driven slot listing and booking
- **Payment**: Headless [Camoufox](https://github.com/daijro/camoufox) (anti-detect Firefox) handles the Ingenico payment flow including CVV (Card Verification Value) entry and 3D Secure authentication
- **Auth**: OAuth2 tokens with 90-day rolling refresh — log in once, stay authenticated for months

### Auth lifecycle

- **Access tokens** expire every 30 minutes — auto-refreshed transparently
- **Refresh tokens** last 90 days with a rolling window — each refresh resets the clock
- **Browser session** (Camoufox profile) persists Cloudflare clearance and ASDA login cookies

### Configuration

All config lives in `~/.config/asdabot/`:

| File | Purpose |
|------|---------|
| `account.json` | Auth tokens, store ID, and delivery address |
| `.env` | Secrets (CVV) |
| `browser-state/` | Camoufox persistent browser profile |

### Server deployment

On a headless Linux server, Camoufox uses a virtual display (Xvfb) automatically — no GUI needed for checkout. Install `xvfb` (`apt install xvfb`) and the CLI handles the rest.

For the one-time login, use noVNC to access the browser remotely:
```bash
apt install xvfb x11vnc novnc
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
x11vnc -display :99 -nopw -listen 0.0.0.0 -forever &
websockify --web=/usr/share/novnc 6080 localhost:5900 &
uv run asdabot auth login  # Complete login via http://server:6080/vnc.html
```

## Technical notes

See [docs/asda_api_notes.md](docs/asda_api_notes.md) for detailed reverse engineering notes on ASDA's API surface, auth flow, payment system, and the headless browser challenges we solved.

## Limitations

- One basket per customer — ASDA's backend enforces this
- Slot queries limited to a 4-day window
- Payment requires a browser — Ingenico's device fingerprinting can't be replicated via API
- SFCC doesn't reflect cancellations made on the ASDA website
- If the Camoufox session expires, run `asdabot auth login` again
