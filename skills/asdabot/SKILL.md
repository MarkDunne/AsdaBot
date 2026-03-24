---
name: asdabot
description: Use the asdabot CLI to manage ASDA grocery shopping. Use when the user asks to search for groceries, add items to basket, check delivery slots, place an order, or manage their ASDA grocery account. Trigger phrases include "order groceries", "ASDA", "delivery slot", "shopping list", "add to basket", "weekly shop".
---

# asdabot — ASDA Grocery CLI

The `asdabot` command must be available on PATH. Install with `uv tool install asdabot` or `pipx install asdabot`.

## Prerequisites

- ASDA account with a saved delivery address and payment card.
- One-time setup: `asdabot auth login` — opens a browser, user logs in manually. Saves tokens, address, and store automatically.
- User has configured `~/.config/asdabot/.env`
- Check auth with `asdabot auth status`. Refresh tokens last 90 days (rolling).

## Command Reference

### Search (no auth needed)
```bash
asdabot search "chicken"           # Search products
asdabot search "milk" -n 5         # Limit results
asdabot search "eggs" -d           # Include product descriptions
```
- The CIN column (first) is the product ID used for `basket add`.

### Product Details
```bash
asdabot product <CIN>              # Full product info (description, nutrition, storage)
```

### Basket
```bash
asdabot basket show                # View basket
asdabot basket add <CIN>           # Add product by CIN
asdabot basket add <CIN> -q 3     # Add with quantity
asdabot basket remove <ITEM_ID>   # Remove by item ID
asdabot basket clear               # Clear all items
```
- ASDA allows **one basket per customer**. Use `basket clear` to start fresh.
- Multiple `basket add` calls can be run in parallel.

### Delivery Slots
```bash
asdabot slots list                 # List slots (default 3 days)
asdabot slots list -d 2            # List slots for 2 days
asdabot slots book <SLOT_ID>       # Book a slot
```
- **Max `-d` value is 3.** ASDA limits queries to a 4-day window. Do NOT pass 4+.
- Slot IDs are long base64 strings — copy the **full** ID.
- Slot IDs encode the delivery address. Re-list after changing address.

### Checkout
```bash
asdabot checkout -y                # Place order (headless browser)
```
- **Always use `-y` flag** — the interactive prompt blocks non-interactive contexts.
- **CRITICAL: Before running checkout, show the user the order summary and get explicit approval in chat.** Run `asdabot basket show` first, present items and total, ask user to confirm.
- Uses Camoufox (anti-detect Firefox) headlessly to handle the Ingenico payment flow.
- Requires: items in basket, a booked slot, `~/.config/asdabot/.env` configured, and a saved card and address on the ASDA account.

### Orders
```bash
asdabot orders                     # Show recent orders with payment status
```

### Auth
```bash
asdabot auth status                # Check token expiry and account info
asdabot auth refresh               # Manually refresh tokens
asdabot auth login                 # One-time: open browser for login (interactive)
```
- Access tokens auto-refresh (30min expiry, 90-day rolling refresh token).
- `auth login` is **interactive** — tell the user to run it in their terminal.
- Login fetches delivery address and store ID from the ASDA account automatically.

## Typical Order Flow

```bash
# 1. Search and build basket
asdabot basket clear
asdabot search "semi skimmed milk"
asdabot basket add 165468
asdabot search "eggs"
asdabot basket add 166781
asdabot basket show

# 2. Find and book a delivery slot
asdabot slots list
asdabot slots book <SLOT_ID>

# 3. Review and place the order
asdabot basket show              # Show summary to user, ask for approval
asdabot checkout -y              # Only after user confirms in chat
```

## Weekly Shop Shortcut

If the user asks to "do the weekly shop" or "order my regulars":
1. `asdabot basket clear`
2. Search and add each item the user wants
3. `asdabot slots list` — find a slot
4. `asdabot slots book <SLOT_ID>`
5. Show basket summary, get user approval
6. `asdabot checkout -y`

## Important Notes

- **Checkout places a real order and charges real money.** Always get user approval first.
- Never run `checkout -y` without explicit user confirmation in chat.
- Config: `~/.config/asdabot/` (account.json, .env, browser-state/).
- Only one basket at a time — no parallel orders.
- If checkout fails with "Session expired", user needs to run `asdabot auth login` again.

## Architecture

- Search: Algolia API (no auth, public keys)
- Basket/Slots/Orders: Salesforce Commerce Cloud (SFCC) API via proxy
- Auth: SLAS OAuth2 with 90-day rolling refresh tokens
- Payment: Camoufox headless browser → Ingenico hosted tokenization iframe

## Self-Correcting

Any time a command fails due to incorrect syntax, wrong flags, API changes, or a misunderstanding, update this skill with the correct approach before continuing. Prefer fixing incorrect examples over adding new sections.
