# AsdaBot

Autonomous grocery shopping on ASDA from the terminal.

<img src="docs/demo.svg" alt="AsdaBot demo" />

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
| `basket add-many <CIN> ...` | Add multiple products in one request |
| `basket remove <ITEM_ID>` | Remove item from basket |
| `basket clear` | Clear all items |
| `slots list` | List available delivery slots (max 3 days) |
| `slots book <SLOT_ID>` | Book a delivery slot |
| `checkout -y` | Place order via headless browser |
| `orders` | Show recent orders with payment status |
| `auth login` | Open browser for login (one-time) |
| `auth status` | Check token expiry and account info |
| `auth refresh` | Manually refresh tokens |

## How it works

AsdaBot uses your existing ASDA account to search products, manage your basket, book delivery slots, and place orders — all from the terminal. Login is handled through a browser session; subsequent operations use ASDA's APIs directly. Payment at checkout is processed via a headless browser.

Config is stored in `~/.config/asdabot/`.

## Security and Disclaimer

**This is an unofficial tool. It is not affiliated with, endorsed by, or supported by ASDA or Walmart.** Use it at your own risk. It automates a real shopping account and places real orders with real money.

- **CVV** is stored in `~/.config/asdabot/.env` and is only used to complete payment in the browser — never logged or transmitted by asdabot.
- **Auth tokens** are stored in `~/.config/asdabot/account.json`. Only expiry times appear in CLI output.
- Restrict file permissions: `chmod 600 ~/.config/asdabot/.env ~/.config/asdabot/account.json`
- Review your basket before confirming checkout — `asdabot checkout -y` places a real order immediately
