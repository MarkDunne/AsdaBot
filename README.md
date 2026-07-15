# AsdaBot

Grocery shopping on ASDA from the terminal. CLI + Claude Code Plugin.

AsdaBot handles everything up to payment — search, basket, delivery slots — then opens ASDA's checkout in your browser for you to review and pay. It never touches your card details.

Below is Claude Code using the tool to order ingredients for a lasagna.

<img src="docs/demo.svg" alt="AsdaBot demo" />

## Prerequisites

- An existing ASDA Groceries account with a saved delivery address
- A Chromium-based browser (Chrome, Edge, Brave, or Chromium) for the one-time login — checkout opens in your default browser, whichever that is

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
asdabot auth login # Opens a browser window — log in to ASDA
```

A normal browser window opens (no automation flags — Cloudflare rejects logins otherwise). Log in with "Keep me signed in" ticked and press Enter in the terminal; asdabot then reads the session invisibly and fetches your delivery address and store.

The session lasts 90 days and rolls forward on every use, so in practice you log in once.

## Usage

```bash
asdabot search "milk"
asdabot basket add-many 165468 166781   # add several products in one request
asdabot basket show
asdabot slots list
asdabot slots book 3                    # book by row # from the latest list
asdabot checkout                        # opens ASDA checkout in your browser to pay
```

## Claude Code Plugin

Works as a [Claude Code plugin](https://code.claude.com/docs/en/plugins.md) — Claude searches, builds the basket, and books the slot; payment always stays with you in the browser.

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
| `basket add-many <CIN> ...` | Add multiple products in one request |
| `basket remove <CIN \| ITEM_ID>` | Remove item from basket (by product CIN or basket item ID) |
| `basket clear` | Clear all items |
| `slots list` | List available delivery slots (max 3 days) |
| `slots book <N \| SLOT_ID>` | Book a delivery slot (by row # from the latest `slots list`, or full slot ID) |
| `checkout` | Review the order and open ASDA checkout in your browser to pay |
| `orders` | Show recent orders with payment status |
| `auth login` | Open browser for login (one-time) |
| `auth status` | Check token expiry and account info |
| `auth refresh` | Manually refresh tokens |

## How it works

AsdaBot uses your existing ASDA account to search products, manage your basket, and book delivery slots — all from the terminal via ASDA's APIs. Login happens in a real browser window with no automation attached; once you've logged in, asdabot reads the session cookies from the browser profile invisibly and refreshes tokens automatically from then on. Checkout opens ASDA's own payment page in your browser — you review the order and pay there yourself.

Basket totals shown by `basket show` and `checkout` break out items vs delivery & fees (the slot price plus ASDA's small-basket fee, if any).

Config is stored in `~/.config/asdabot/`.

## Security and Disclaimer

**This is an unofficial tool. It is not affiliated with, endorsed by, or supported by ASDA or Walmart.** Use it at your own risk. It automates a real shopping account.

- **Payment is always manual.** asdabot never sees, stores, or enters your card details — payment happens on ASDA's own checkout page in your browser.
- **Auth tokens** are stored in `~/.config/asdabot/account.json`. Only expiry times appear in CLI output.
- Restrict file permissions: `chmod 600 ~/.config/asdabot/account.json`
