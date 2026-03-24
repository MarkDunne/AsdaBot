"""CLI entry point for asdabot."""

import json as jsonlib
import time
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from asdabot import api, auth, search
from asdabot.auth import AuthError, require_account
from asdabot.config import get_store_id, load_account

app = typer.Typer(help="ASDA Grocery CLI — search, browse, and manage your basket.")
console = Console()


def _require_address() -> dict:
    account = require_account()
    addr = account.get("address", {})
    if not addr or not addr.get("address1"):
        console.print("[red]No address on account. Check your ASDA account settings.[/red]")
        raise typer.Exit(1)
    return addr


def _format_price(price, offer: str = "") -> str:
    s = f"£{price:.2f}" if isinstance(price, int | float) else str(price)
    if offer and offer != "List":
        s = f"[bold]{s}[/bold] ({offer})"
    return s


# -- Auth --

auth_app = typer.Typer(help="Manage authentication.")
app.add_typer(auth_app, name="auth")


@auth_app.command("login")
def auth_login():
    """Open browser to log in. Saves session state, tokens, and delivery address."""
    from asdabot.checkout import browser_login

    account = browser_login()
    if not account:
        console.print("[red]Could not extract tokens. Did you log in?[/red]")
        raise typer.Exit(1)

    addr = account.get("address", {})
    console.print("[green]Login successful![/green]")
    console.print(f"  Store: {account.get('store_id', '?')}")
    if addr.get("address1"):
        console.print(
            f"  Address: {addr['address1']}, {addr.get('address2', '')}, "
            f"{addr.get('city', '')}, {addr.get('postcode', '')}"
        )


@auth_app.command("status")
def auth_status():
    """Show current auth status and token expiry."""
    account = load_account()
    if not account:
        console.print("[red]Not authenticated. Run 'asdabot auth login'.[/red]")
        return

    tokens = account.get("tokens", {})
    now = time.time()
    expires_at = tokens.get("expires_at", 0)
    refresh_expires_at = tokens.get("refresh_expires_at", 0)

    if expires_at and expires_at > now:
        access = f"[green]valid[/green] ({int((expires_at - now) // 60)}m)"
    else:
        access = "[yellow]expired[/yellow] (will auto-refresh)"

    if refresh_expires_at and refresh_expires_at > now:
        refresh = f"[green]valid[/green] ({int((refresh_expires_at - now) // 86400)}d)"
    else:
        refresh = "[red]expired — run 'asdabot auth login'[/red]"

    console.print(f"Customer: [bold]{tokens.get('customer_id', '?')}[/bold]")
    console.print(f"Access token: {access}")
    console.print(f"Refresh token: {refresh}")
    console.print(f"Store: {account.get('store_id', '?')}")

    addr = account.get("address", {})
    if addr.get("address1"):
        console.print(
            f"Address: {addr['address1']}, {addr.get('city', '')}, {addr.get('postcode', '')}"
        )


@auth_app.command("refresh")
def auth_refresh():
    """Manually refresh tokens."""
    account = auth.refresh_tokens()
    console.print(
        f"[green]Refreshed.[/green] Customer: {account['tokens']['customer_id']}"
    )


# -- Search --


def _get_description(product: dict) -> str:
    """Extract a short description from SFCC product detail."""

    bb = product.get("c_BRANDBANK_JSON", {})
    if isinstance(bb, str):
        bb = jsonlib.loads(bb)
    return bb.get("regulatedProductName", "") or bb.get("productMarketing", "") or ""


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n"),
    detail: bool = typer.Option(False, "--detail", "-d", help="Include descriptions"),
):
    """Search for products."""
    results = search.search_products(query, hits_per_page=limit)
    hits = results.get("hits", [])
    if not hits:
        console.print(f"[yellow]No results for '{query}'[/yellow]")
        return

    # Optionally enrich with product descriptions
    details = {}
    if detail:
        cins = [str(h.get("CIN", "")) for h in hits]
        details = api.get_product_details(cins)

    store_id = get_store_id()
    table = Table(title=f"Search: {query} ({results.get('nbHits', 0)} total)")
    table.add_column("CIN", style="dim")
    table.add_column("Name")
    table.add_column("Brand", style="cyan")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Per Unit", justify="right", style="dim")
    table.add_column("Pack", style="dim")
    table.add_column("Stock", justify="center")
    if detail:
        table.add_column("Description", style="dim")

    for hit in hits:
        prices = hit.get("PRICES", {}).get("EN", {})
        stock = hit.get("STOCK", {})
        stock_val = stock.get(store_id, 0) if isinstance(stock, dict) else 0
        cin = str(hit.get("CIN", ""))

        row = [
            cin,
            hit.get("NAME", ""),
            hit.get("BRAND", ""),
            _format_price(prices.get("PRICE", ""), prices.get("OFFER", "")),
            prices.get("PRICEPERUOMFORMATTED", ""),
            hit.get("PACK_SIZE", ""),
            "[green]Y[/green]" if stock_val > 0 else "[red]N[/red]",
        ]
        if detail:
            row.append(_get_description(details.get(cin, {})))
        table.add_row(*row)

    console.print(table)


@app.command("product")
def product_cmd(
    product_id: str = typer.Argument(..., help="Product CIN"),
):
    """Show full product details."""

    details = api.get_product_details([product_id])
    product = details.get(product_id)
    if not product:
        console.print(f"[red]Product {product_id} not found.[/red]")
        raise typer.Exit(1)

    bb = product.get("c_BRANDBANK_JSON", {})
    if isinstance(bb, str):
        bb = jsonlib.loads(bb)

    console.print(f"\n[bold]{product.get('name', '?')}[/bold]")
    console.print(f"  CIN: {product_id}")
    console.print(f"  Brand: {product.get('brand', '?')}")
    console.print(f"  Price: £{product.get('price', 0):.2f}")

    if desc := bb.get("regulatedProductName", ""):
        console.print(f"  Description: {desc}")
    if marketing := bb.get("productMarketing", ""):
        console.print(f"  Info: {marketing}")
    if features := bb.get("features", []):
        console.print(f"  Features: {', '.join(features)}")
    if storage := bb.get("storage", ""):
        console.print(f"  Storage: {storage}")
    if nutrition := bb.get("nutrition", []):
        nutr_str = ", ".join(
            f"{n['nutrient']}: {n['values'][0]}" for n in nutrition[:6] if n.get("values")
        )
        console.print(f"  Nutrition (per 100ml): {nutr_str}")
    console.print()


# -- Basket --

basket_app = typer.Typer(help="Manage your shopping basket.")
app.add_typer(basket_app, name="basket")


@basket_app.command("clear")
def basket_clear():
    """Clear all items from the basket."""
    api.clear_basket()
    console.print("[green]Basket cleared.[/green]")


@basket_app.command("show")
def basket_show():
    """Show current basket contents."""
    data = api.get_basket()
    items = data.get("productItems", [])
    if not items:
        console.print("[yellow]Basket is empty.[/yellow]")
        return

    table = Table(title=f"Basket ({len(items)} items)")
    table.add_column("CIN", style="dim")
    table.add_column("Item ID", style="dim")
    table.add_column("Name")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Pack", style="dim")

    for item in items:
        table.add_row(
            item.get("productId", ""),
            item.get("itemId", ""),
            item.get("productName", ""),
            str(item.get("quantity", 0)),
            f"£{item.get('price', 0):.2f}",
            item.get("c_packSize", ""),
        )

    console.print(table)
    console.print(f"\n[bold]Total: £{data.get('orderTotal', 0):.2f}[/bold]")


@basket_app.command("add")
def basket_add(
    product_id: str = typer.Argument(..., help="Product CIN"),
    quantity: int = typer.Option(1, "--qty", "-q"),
):
    """Add a product to basket."""
    hits = search.lookup_products([product_id]).get("hits", [])
    if not hits:
        console.print(f"[red]Product {product_id} not found.[/red]")
        raise typer.Exit(1)

    hit = hits[0]
    price = hit.get("PRICES", {}).get("EN", {}).get("PRICE", 0)
    console.print(f"Adding {quantity}x {hit.get('NAME', '?')} (£{price:.2f})...")

    result = api.add_to_basket(product_id, quantity=quantity, price=price)
    console.print(
        f"[green]Done![/green] Basket: {int(result.get('c_totalQty', 0))} items, "
        f"£{result.get('orderTotal', 0):.2f}"
    )


@basket_app.command("remove")
def basket_remove(
    item_id: str = typer.Argument(..., help="Item ID from 'basket show'"),
):
    """Remove an item from basket."""
    result = api.remove_from_basket(item_id)
    console.print(
        f"[green]Removed.[/green] Basket: {int(result.get('c_totalQty', 0))} items, "
        f"£{result.get('orderTotal', 0):.2f}"
    )


# -- Slots --

slots_app = typer.Typer(help="View and book delivery slots.")
app.add_typer(slots_app, name="slots")


@slots_app.command("list")
def slots_list(
    days: int = typer.Option(3, "--days", "-d", help="Days to show (max 3)"),
):
    """List available delivery slots."""
    addr = _require_address()
    days = min(days, 3)

    tomorrow = datetime.now(tz=UTC) + timedelta(days=1)
    start = tomorrow.strftime("%Y-%m-%dT00:00:00Z")
    end = (tomorrow + timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")

    console.print(f"Fetching slots for {addr['address1']}, {addr['city']}...")
    data = api.get_delivery_slots(addr, start, end)
    slot_days = data.get("c_deliverySlotsData", {}).get("slot_days", [])

    if not slot_days:
        console.print("[yellow]No slot data returned.[/yellow]")
        return

    available = [
        (day.get("slot_date", "")[:10], slot)
        for day in slot_days
        for slot in day.get("slots", [])
        if slot.get("available")
    ]

    table = Table(title="Available Delivery Slots", show_lines=True)
    table.add_column("#", style="bold")
    table.add_column("Date")
    table.add_column("Time")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Slot ID", style="dim", overflow="fold")

    for i, (date_str, slot) in enumerate(available, 1):
        price = slot.get("final_price", slot.get("slot_price", "?"))
        table.add_row(
            str(i),
            date_str,
            f"{slot['start_time'][11:16]}-{slot['end_time'][11:16]}",
            f"£{price}" if price else "Free",
            slot.get("slot_id", ""),
        )

    console.print(table)
    console.print(f"\n{len(available)} slots available")


@slots_app.command("book")
def slots_book(
    slot_id: str = typer.Argument(..., help="Full slot ID to book"),
):
    """Book a delivery slot."""
    addr = _require_address()
    console.print("Booking slot...")
    result = api.book_slot(slot_id, addr)

    booked = result.get("c_asdaBookedSlotDetail", {})
    if booked:
        s, e = booked.get("start_time", ""), booked.get("end_time", "")
        console.print(
            f"[green]Booked![/green] {s[:10]} {s[11:16]}-{e[11:16]}, "
            f"£{booked.get('final_price', '?')}"
        )
    else:
        console.print("[green]Slot booking sent.[/green]")


# -- Checkout --


@app.command("checkout")
def checkout(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation"),
):
    """Place the order using a headless browser for payment."""
    from asdabot.checkout import place_order_via_browser

    basket = api.get_basket()
    items = basket.get("productItems", [])
    booked_slot = basket.get("c_asdaBookedSlotDetail", {})

    if not items:
        console.print("[red]Basket is empty.[/red]")
        raise typer.Exit(1)
    if not booked_slot:
        console.print("[red]No slot booked. Run 'asdabot slots book' first.[/red]")
        raise typer.Exit(1)

    s = booked_slot.get("start_time", "")
    e = booked_slot.get("end_time", "")

    console.print("\n[bold]Order Summary[/bold]")
    for item in items:
        console.print(
            f"  {item.get('quantity', 1)}x {item.get('productName', '?')} "
            f"- £{item.get('price', 0):.2f}"
        )
    console.print(
        f"  Delivery: {s[:10]} {s[11:16]}-{e[11:16]} (£{booked_slot.get('final_price', '?')})"
    )
    console.print(f"  [bold]Total: £{basket.get('orderTotal', 0):.2f}[/bold]\n")

    if not confirm and not typer.confirm("Place this order?"):
        raise typer.Exit(0)

    console.print("Placing order...")
    result = place_order_via_browser()

    if result["success"]:
        orders = api.get_orders().get("data", [])
        order_no = orders[0].get("orderNo", "?") if orders else "?"
        console.print(f"\n[bold green]Order placed! #{order_no}[/bold green]")
    else:
        console.print(f"\n[red]Checkout failed: {result.get('error', '?')}[/red]")
        raise typer.Exit(1)


# -- Orders --


@app.command("orders")
def orders_cmd():
    """Show recent orders."""

    order_list = api.get_orders().get("data", [])
    if not order_list:
        console.print("[yellow]No recent orders.[/yellow]")
        return

    table = Table(title="Recent Orders")
    table.add_column("Order No")
    table.add_column("Status")
    table.add_column("Payment")
    table.add_column("Delivery Slot")
    table.add_column("Total", justify="right", style="green")

    for order in order_list:
        total = order.get("orderTotal", 0)
        status = order.get("status", "")
        payment = order.get("c_ingenicoOgoneStatusCategory", "")

        slot = order.get("c_asdaBookedSlotDetail", "{}")
        if isinstance(slot, str):
            slot = jsonlib.loads(slot)
        slot_start = slot.get("start_time", "")
        slot_str = f"{slot_start[:10]} {slot_start[11:16]}" if slot_start else ""

        status_style = {"created": "green", "failed": "red"}.get(status, "")
        table.add_row(
            str(order.get("orderNo", "")),
            f"[{status_style}]{status}[/{status_style}]" if status_style else status,
            payment.lower() if payment else "",
            slot_str,
            f"£{total:.2f}" if total else "?",
        )

    console.print(table)


def main():
    try:
        app()
    except AuthError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None
