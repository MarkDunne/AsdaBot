# AsdaBot

Autonomous grocery shopping on ASDA from the terminal.

## Prerequisites

You need an existing ASDA Groceries account with:
- A saved delivery address
- A saved payment card

## Install

```bash
uv tool install asdabot
```

Or run directly without installing:

```bash
uvx asdabot search "milk"
```

## Setup

```bash
asdabot auth login # Opens browser — log in to ASDA
echo "ASDA_CARD_CVV=1234" > ~/.config/asdabot/.env # Store your CVV code for payment automation
```

Login automatically fetches your delivery address and store from your ASDA account.

## Usage

```bash
asdabot search "milk"
asdabot basket add 165468
asdabot slots list
asdabot slots book <SLOT_ID>
asdabot checkout
```

## Claude Code Plugin

Works as a [Claude Code plugin](https://code.claude.com/docs/en/plugins.md) — Claude can manage your grocery shopping autonomously.

```
/plugin marketplace add MarkDunne/AsdaBot
/plugin install asdabot@asdabot
```

Or for local development:

```bash
claude --plugin-dir /path/to/AsdaBot
```

## Commands

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

Checkout and login both require a browser. On a headless Linux server, install `xvfb` (`apt install xvfb`) — Camoufox uses it as a virtual display.

For the one-time login, either authenticate locally and copy the config:

```bash
asdabot auth login                                  # On your local machine
scp -r ~/.config/asdabot/ server:~/.config/asdabot/
```

Or use SSH X forwarding to run the login browser on the server:

```bash
ssh -X server
asdabot auth login  # Browser opens on your local display
```

## Security and Disclaimer

**This is an unofficial tool. It is not affiliated with, endorsed by, or supported by ASDA or Walmart.** Use it at your own risk. It automates a real shopping account and places real orders with real money.

**Sensitive data handling:**

- **CVV** is stored in plaintext in `~/.config/asdabot/.env`. It is only used to fill the Ingenico payment iframe in the browser and is never logged, printed, or transmitted by asdabot itself.
- **Auth tokens** are stored in plaintext in `~/.config/asdabot/account.json`. Only token expiry times are shown in CLI output, never the tokens themselves.
- **Claude Code plugin caveat.** While asdabot does not include sensitive data in its CLI output, there is no guarantee that Claude will not independently read config files such as `.env` or `account.json`. Claude Code has access to your filesystem and may read files at its own discretion.

**Recommendations:**

- Restrict file permissions: `chmod 600 ~/.config/asdabot/.env ~/.config/asdabot/account.json`
- Do not commit `~/.config/asdabot/` to version control
- Review your basket before confirming checkout — `asdabot checkout -y` places a real order immediately with no confirmation prompt

## Technical notes

See [docs/asda_api_notes.md](docs/asda_api_notes.md) for detailed reverse engineering notes on ASDA's API surface, auth flow, payment system, and the headless browser challenges we solved.

## Limitations

- One basket per customer — ASDA's backend enforces this
- Slot queries limited to a 4-day window
- Payment requires a browser — Ingenico's device fingerprinting can't be replicated via API
- SFCC doesn't reflect cancellations made on the ASDA website
- If the Camoufox session expires, run `asdabot auth login` again
