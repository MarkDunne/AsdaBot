"""CLI entry point for asdabot."""

import time
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from asdabot import api, auth, search
from asdabot.config import load_address, load_tokens, save_address

app = typer.Typer(help="ASDA Grocery CLI — search, browse, and manage your basket.")
console = Console()


# -- Auth commands --

auth_app = typer.Typer(help="Manage authentication.")
app.add_typer(auth_app, name="auth")


@auth_app.command("login")
def auth_login():
    """Open Chrome to log in. Saves session state and auth tokens."""
    from asdabot.checkout import browser_login

    success = browser_login()
    if success:
        console.print("[green]Login successful! Tokens and browser state saved.[/green]")
        console.print("You can now use 'asda checkout' for fully headless orders.")
    else:
        console.print(
            "[red]Could not extract tokens. Make sure you logged in before closing Chrome.[/red]"
        )


@auth_app.command("import")
def auth_import():
    """Import auth tokens manually (fallback if login doesn't work)."""
    auth.import_tokens_interactive()


@auth_app.command("status")
def auth_status():
    """Show current auth status and token expiry."""
    tokens = load_tokens()
    if not tokens:
        console.print("[red]Not authenticated. Run 'asda auth import' first.[/red]")
        return

    customer_id = tokens.get("SLAS.CUSTOMER_ID", "unknown")
    expires_at = tokens.get("expires_at", 0)
    refresh_expires_at = tokens.get("refresh_token_expires_at", 0)

    now = time.time()

    if expires_at:
        access_remaining = expires_at - now
        if access_remaining > 0:
            access_str = f"[green]valid[/green] ({int(access_remaining // 60)}m remaining)"
        else:
            access_str = "[yellow]expired[/yellow] (will auto-refresh)"
    else:
        access_str = "[yellow]unknown expiry[/yellow]"

    if refresh_expires_at:
        refresh_remaining = refresh_expires_at - now
        refresh_days = int(refresh_remaining // 86400)
        if refresh_remaining > 0:
            refresh_str = f"[green]valid[/green] ({refresh_days} days remaining)"
        else:
            refresh_str = "[red]expired — re-login required[/red]"
    else:
        refresh_str = "[yellow]unknown expiry[/yellow]"

    console.print(f"Customer ID: [bold]{customer_id}[/bold]")
    console.print(f"Access token: {access_str}")
    console.print(f"Refresh token: {refresh_str}")


@auth_app.command("refresh")
def auth_refresh():
    """Manually refresh tokens."""
    tokens = auth.refresh_tokens()
    console.print(f"[green]Tokens refreshed.[/green] Customer: {tokens['SLAS.CUSTOMER_ID']}")


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
    """Set delivery address for slot booking and checkout."""
    address = {
        "address1": address1,
        "address2": address2,
        "city": city,
        "countryCode": "GB",
        "postalCode": postcode.replace(" ", ""),
        "stateCode": "United Kingdom",
        "firstName": first_name,
        "lastName": last_name,
        "asdaLatitude": latitude,
        "asdaLongitude": longitude,
        "asdaPostcode": postcode.replace(" ", ""),
        "asdaAddressType": "House",
        "asdaCrmAddressId": crm_address_id,
    }
    save_address(address)
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


def _require_address() -> dict:
    addr = load_address()
    if not addr:
        console.print("[red]No address saved. Run 'asda address set' first.[/red]")
        raise typer.Exit(1)
    return addr


# -- Search --


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query, e.g. 'milk'"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
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
        price = prices.get("PRICE", "")
        per_uom = prices.get("PRICEPERUOMFORMATTED", "")
        offer = prices.get("OFFER", "")

        price_str = f"£{price:.2f}" if isinstance(price, int | float) else str(price)
        if offer and offer not in ("List",):
            price_str = f"[bold]{price_str}[/bold] ({offer})"

        stock = hit.get("STOCK", {})
        stock_val = stock.get("4619", 0) if isinstance(stock, dict) else 0
        stock_str = "[green]Y[/green]" if stock_val > 0 else "[red]N[/red]"

        table.add_row(
            str(hit.get("CIN", "")),
            hit.get("NAME", ""),
            hit.get("BRAND", ""),
            price_str,
            per_uom,
            hit.get("PACK_SIZE", ""),
            stock_str,
        )

    console.print(table)


# -- Regulars --


@app.command("regulars")
def regulars():
    """Show your regular products with details."""
    data = api.get_regulars()
    products = data.get("products", [])

    if not products:
        console.print("[yellow]No regulars found.[/yellow]")
        return

    product_ids = [p["product_id"] for p in products]
    quantities = {p["product_id"]: p["quantity"] for p in products}
    details = search.lookup_products(product_ids)
    hits = {h["CIN"]: h for h in details.get("hits", [])}

    table = Table(title=f"Your Regulars ({len(products)} items)")
    table.add_column("CIN", style="dim")
    table.add_column("Name")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Pack", style="dim")

    for pid in product_ids:
        hit = hits.get(pid, {})
        prices = hit.get("PRICES", {}).get("EN", {})
        price = prices.get("PRICE", "?")
        price_str = f"£{price:.2f}" if isinstance(price, int | float) else str(price)

        table.add_row(
            pid,
            hit.get("NAME", "(unknown)"),
            str(quantities[pid]),
            price_str,
            hit.get("PACK_SIZE", ""),
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
    table.add_column("Product ID", style="dim")
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
    product_id: str = typer.Argument(..., help="Product CIN to add"),
    quantity: int = typer.Option(1, "--qty", "-q", help="Quantity"),
):
    """Add a product to basket."""
    details = search.lookup_products([product_id])
    hits = details.get("hits", [])
    if not hits:
        console.print(f"[red]Product {product_id} not found.[/red]")
        raise typer.Exit(1)

    hit = hits[0]
    price = hit.get("PRICES", {}).get("EN", {}).get("PRICE", 0)
    name = hit.get("NAME", "Unknown")

    console.print(f"Adding {quantity}x {name} (£{price:.2f})...")
    result = api.add_to_basket(product_id, quantity=quantity, price=price)

    total = result.get("orderTotal", 0)
    total_qty = result.get("c_totalQty", 0)
    console.print(f"[green]Done![/green] Basket: {int(total_qty)} items, £{total:.2f}")


@basket_app.command("remove")
def basket_remove(
    item_id: str = typer.Argument(..., help="Item ID to remove (from 'basket show')"),
):
    """Remove an item from basket by item ID."""
    console.print(f"Removing item {item_id}...")
    result = api.remove_from_basket(item_id)
    total = result.get("orderTotal", 0)
    total_qty = result.get("c_totalQty", 0)
    console.print(f"[green]Done![/green] Basket: {int(total_qty)} items, £{total:.2f}")


# -- Slots --

slots_app = typer.Typer(help="View and book delivery slots.")
app.add_typer(slots_app, name="slots")


@slots_app.command("list")
def slots_list(
    days: int = typer.Option(3, "--days", "-d", help="Number of days to show (max 3)"),
):
    """List available delivery slots. ASDA limits queries to a 4-day window."""
    addr = _require_address()

    if days > 3:
        console.print("[yellow]ASDA limits slot queries to 4 days. Capping at 3.[/yellow]")
        days = 3

    now = datetime.now(tz=UTC)
    # Start from tomorrow to maximise the window
    tomorrow = now + timedelta(days=1)
    start = tomorrow.strftime("%Y-%m-%dT00:00:00Z")
    end = (tomorrow + timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")

    delivery_location = {
        "address1": addr["address1"],
        "address2": addr.get("address2", ""),
        "city": addr["city"],
        "countryCode": "GB",
        "asdaLatitude": addr["asdaLatitude"],
        "asdaLongitude": addr["asdaLongitude"],
        "asdaPostcode": addr["asdaPostcode"],
    }

    console.print(f"Fetching slots for {addr['address1']}, {addr['city']}...")
    data = api.get_delivery_slots(delivery_location, start, end)
    slot_days = data.get("c_deliverySlotsData", {}).get("slot_days", [])

    if not slot_days:
        console.print("[yellow]No slot data returned.[/yellow]")
        return

    table = Table(title="Available Delivery Slots", show_lines=True)
    table.add_column("#", style="bold")
    table.add_column("Date")
    table.add_column("Time")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Slot ID", style="dim", overflow="fold")

    available_slots = []
    for day in slot_days:
        date_str = day.get("slot_date", "")[:10]
        for slot in day.get("slots", []):
            if not slot.get("available", False):
                continue
            available_slots.append((date_str, slot))

    for i, (date_str, slot) in enumerate(available_slots, 1):
        start_time = slot.get("start_time", "")[11:16]
        end_time = slot.get("end_time", "")[11:16]
        price = slot.get("final_price", slot.get("slot_price", "?"))
        slot_id = slot.get("slot_id", "")

        table.add_row(
            str(i),
            date_str,
            f"{start_time}-{end_time}",
            f"£{price}" if price else "Free",
            slot_id,
        )

    console.print(table)
    console.print(f"\n{len(available_slots)} slots available")
    console.print("\nTo book: [bold]asda slots book <slot_id>[/bold]")


@slots_app.command("book")
def slots_book(
    slot_id: str = typer.Argument(..., help="Full slot ID to book"),
):
    """Book a delivery slot."""
    addr = _require_address()

    shipping_address = {
        "address1": addr["address1"],
        "address2": addr.get("address2", ""),
        "city": addr["city"],
        "countryCode": "GB",
        "postalCode": addr["postalCode"],
        "stateCode": "United Kingdom",
        "firstName": addr["firstName"],
        "lastName": addr["lastName"],
        "custom": {
            "asdaCrmAddressId": addr.get("asdaCrmAddressId", ""),
            "asdaAddressType": addr.get("asdaAddressType", "House"),
            "asdaDeliveryNote": "",
            "asdaLatitude": addr["asdaLatitude"],
            "asdaLongitude": addr["asdaLongitude"],
            "asdaIsPrimaryAddress": True,
        },
    }

    console.print("Booking slot...")
    result = api.book_slot(slot_id, shipping_address)

    booked = result.get("c_asdaBookedSlotDetail", {})
    if booked:
        start = booked.get("start_time", "")
        end = booked.get("end_time", "")
        price = booked.get("final_price", "?")
        console.print(
            f"[green]Slot booked![/green] {start[:10]} {start[11:16]}-{end[11:16]}, £{price}"
        )
    else:
        console.print("[green]Slot booking request sent.[/green]")


# -- Checkout --


@app.command("checkout")
def checkout(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Place the order using a headless browser for payment."""
    from asdabot.checkout import place_order_via_browser

    basket = api.get_basket()
    items = basket.get("productItems", [])
    order_total = basket.get("orderTotal", 0)
    booked_slot = basket.get("c_asdaBookedSlotDetail", {})

    if not items:
        console.print("[red]Basket is empty. Add items first.[/red]")
        raise typer.Exit(1)

    if not booked_slot:
        console.print("[red]No slot booked. Run 'asda slots book' first.[/red]")
        raise typer.Exit(1)

    slot_start = booked_slot.get("start_time", "")
    slot_end = booked_slot.get("end_time", "")
    slot_price = booked_slot.get("final_price", "?")

    console.print("\n[bold]Order Summary[/bold]")
    console.print(f"  Items: {len(items)}")
    for item in items:
        console.print(
            f"    {item.get('quantity', 1)}x {item.get('productName', '?')} "
            f"- £{item.get('price', 0):.2f}"
        )
    delivery_str = f"{slot_start[:10]} {slot_start[11:16]}-{slot_end[11:16]} (£{slot_price})"
    console.print(f"  Delivery: {delivery_str}")
    console.print(f"  [bold]Total: £{order_total:.2f}[/bold]\n")

    if not confirm:
        proceed = typer.confirm("Place this order?")
        if not proceed:
            console.print("Order cancelled.")
            raise typer.Exit(0)

    console.print("Placing order...")
    result = place_order_via_browser()

    if result["success"]:
        order_no = result.get("order_no", "unknown")
        console.print(f"\n[bold green]Order placed! Order #{order_no}[/bold green]")
    else:
        console.print(f"\n[red]Checkout failed: {result.get('error', 'unknown')}[/red]")
        raise typer.Exit(1)


# -- Orders --


@app.command("orders")
def orders_cmd():
    """Show recent orders."""
    data = api.get_orders()
    order_list = data.get("data", [])

    if not order_list:
        console.print("[yellow]No recent orders.[/yellow]")
        return

    table = Table(title="Recent Orders")
    table.add_column("Order No")
    table.add_column("Status")
    table.add_column("Date")
    table.add_column("Total", justify="right", style="green")

    for order in order_list:
        order_total = order.get("orderTotal", 0)
        created = order.get("creationDate", "")[:10]
        table.add_row(
            str(order.get("orderNo", "")),
            order.get("status", ""),
            created,
            f"£{order_total:.2f}" if order_total else "?",
        )

    console.print(table)


def main():
    app()
