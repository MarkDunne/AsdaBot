"""CLI entry point for asdabot."""

import time
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from asdabot import api, auth, search
from asdabot.config import (
    build_delivery_location,
    build_shipping_address,
    load_address,
    load_tokens,
    save_address,
)

app = typer.Typer(help="ASDA Grocery CLI — search, browse, and manage your basket.")
console = Console()


def _require_address() -> dict:
    addr = load_address()
    if not addr:
        console.print("[red]No address saved. Run 'asda address set' first.[/red]")
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
    """Open browser to log in. Saves session state and auth tokens."""
    from asdabot.checkout import browser_login

    if browser_login():
        console.print("[green]Login successful! Tokens and browser state saved.[/green]")
    else:
        console.print("[red]Could not extract tokens. Did you log in?[/red]")


@auth_app.command("status")
def auth_status():
    """Show current auth status and token expiry."""
    tokens = load_tokens()
    if not tokens:
        console.print("[red]Not authenticated. Run 'asda auth login'.[/red]")
        return

    now = time.time()
    expires_at = tokens.get("expires_at", 0)
    refresh_expires_at = tokens.get("refresh_token_expires_at", 0)

    if expires_at and expires_at > now:
        access = f"[green]valid[/green] ({int((expires_at - now) // 60)}m)"
    else:
        access = "[yellow]expired[/yellow] (will auto-refresh)"

    if refresh_expires_at and refresh_expires_at > now:
        refresh = f"[green]valid[/green] ({int((refresh_expires_at - now) // 86400)}d)"
    else:
        refresh = "[red]expired — run 'asda auth login'[/red]"

    console.print(f"Customer: [bold]{tokens.get('SLAS.CUSTOMER_ID', '?')}[/bold]")
    console.print(f"Access token: {access}")
    console.print(f"Refresh token: {refresh}")


@auth_app.command("refresh")
def auth_refresh():
    """Manually refresh tokens."""
    tokens = auth.refresh_tokens()
    console.print(f"[green]Refreshed.[/green] Customer: {tokens['SLAS.CUSTOMER_ID']}")


# -- Address --

address_app = typer.Typer(help="Manage delivery address.")
app.add_typer(address_app, name="address")


@address_app.command("set")
def address_set(
    address1: str = typer.Option(..., prompt=True),
    address2: str = typer.Option("", prompt=True),
    city: str = typer.Option(..., prompt=True),
    postcode: str = typer.Option(..., prompt=True),
    latitude: str = typer.Option(..., prompt=True),
    longitude: str = typer.Option(..., prompt=True),
    first_name: str = typer.Option(..., prompt=True),
    last_name: str = typer.Option(..., prompt=True),
    crm_address_id: str = typer.Option("", prompt="CRM Address ID (from browser)"),
):
    """Set delivery address."""
    pc = postcode.replace(" ", "")
    save_address(
        {
            "address1": address1,
            "address2": address2,
            "city": city,
            "countryCode": "GB",
            "postalCode": pc,
            "stateCode": "United Kingdom",
            "firstName": first_name,
            "lastName": last_name,
            "asdaLatitude": latitude,
            "asdaLongitude": longitude,
            "asdaPostcode": pc,
            "asdaAddressType": "House",
            "asdaCrmAddressId": crm_address_id,
        }
    )
    console.print(f"[green]Address saved:[/green] {address1}, {city}, {postcode}")


@address_app.command("show")
def address_show():
    """Show saved delivery address."""
    addr = load_address()
    if not addr:
        console.print("[yellow]No address saved. Run 'asda address set'.[/yellow]")
        return
    console.print(
        f"{addr['address1']}, {addr.get('address2', '')}, "
        f"{addr['city']}, {addr.get('postalCode', '')}"
    )


# -- Search --


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """Search for products."""
    results = search.search_products(query, hits_per_page=limit)
    hits = results.get("hits", [])
    if not hits:
        console.print(f"[yellow]No results for '{query}'[/yellow]")
        return

    table = Table(title=f"Search: {query} ({results.get('nbHits', 0)} total)")
    table.add_column("CIN", style="dim")
    table.add_column("Name")
    table.add_column("Brand", style="cyan")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Per Unit", justify="right", style="dim")
    table.add_column("Pack", style="dim")
    table.add_column("Stock", justify="center")

    for hit in hits:
        prices = hit.get("PRICES", {}).get("EN", {})
        stock = hit.get("STOCK", {})
        stock_val = stock.get("4619", 0) if isinstance(stock, dict) else 0
        table.add_row(
            str(hit.get("CIN", "")),
            hit.get("NAME", ""),
            hit.get("BRAND", ""),
            _format_price(prices.get("PRICE", ""), prices.get("OFFER", "")),
            prices.get("PRICEPERUOMFORMATTED", ""),
            hit.get("PACK_SIZE", ""),
            "[green]Y[/green]" if stock_val > 0 else "[red]N[/red]",
        )

    console.print(table)


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
    data = api.get_delivery_slots(build_delivery_location(addr), start, end)
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
    result = api.book_slot(slot_id, build_shipping_address(addr))

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
        console.print("[red]No slot booked. Run 'asda slots book' first.[/red]")
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
        console.print(f"\n[bold green]Order placed! #{result.get('order_no', '?')}[/bold green]")
    else:
        console.print(f"\n[red]Checkout failed: {result.get('error', '?')}[/red]")
        raise typer.Exit(1)


# -- Orders --


@app.command("orders")
def orders_cmd():
    """Show recent orders."""
    import json as jsonlib

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
    app()
