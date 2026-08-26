"""Command-line interface entry point for Daily Expenses 4 Importer."""

import argparse
import sys
import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path
import questionary
from rich.console import Console
from rich.table import Table

from daily_expenses_importer.core.db import Database
from daily_expenses_importer.core.classifier import classify
from daily_expenses_importer.core.logger import log_session_start, log_session_end
from daily_expenses_importer.parsers import detect_parser, get_parser
from daily_expenses_importer.parsers.base import NormalizedTransaction, TransactionType

console = Console()
_DEFAULT_DB_PATH = Path("data/importer.db")
_DEFAULT_CONFIG_PATH = Path("data/config.toml")

DEFAULT_CATEGORIES = [
    "Autopista", "Bebidas", "Comida", "Diversión", "Gasolina", "Hijo",
    "Hogar", "Mascota", "Mercancía", "Otros", "Personales", "Propinas",
    "Restaurante", "Ropa", "Salud", "Servicios", "Supermercado",
    "Transporte", "Vehículo", "Viajes", "Vivienda",
]


def _load_config(config_path: Path) -> dict:
    if config_path.exists():
        try:
            return tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to read {config_path}: {e}. Using defaults.[/yellow]")
    return {}


def _print_summary(records: list[dict]) -> None:
    table = Table(title="Transactions to Import", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", width=12)
    table.add_column("Type", width=10)
    table.add_column("Description", width=26)
    table.add_column("Category / Details", width=22)
    table.add_column("Amount (USD)", justify="right", width=14)

    total_usd = Decimal("0")
    for idx, r in enumerate(records, 1):
        tx: NormalizedTransaction = r["tx"]
        amt = r["amount_usd"]
        total_usd += amt
        tx_type_str = "Expense" if tx.tx_type == TransactionType.EXPENSE else "Transfer" if tx.tx_type == TransactionType.TRANSFER else "Refund"
        cat_or_details = r.get("category", "")
        if tx.tx_type == TransactionType.TRANSFER:
            cat_or_details = f"{r.get('source_account', '')} -> {r.get('target_account', '')}"

        table.add_row(
            str(idx),
            tx.date.strftime("%Y-%m-%d"),
            tx_type_str,
            r["description"],
            cat_or_details,
            f"${amt:.2f}",
        )

    table.add_section()
    table.add_row("Total", "", "", f"{len(records)} transactions", "", f"${total_usd:.2f}", style="bold")
    console.print(table)


def run(
    input_path: Path,
    account_name: str | None = None,
    dry_run: bool = False,
    headless: bool = True,
    config_path: Path = _DEFAULT_CONFIG_PATH,
) -> None:
    """Run the import pipeline for an input file."""
    log_session_start(input_path, dry_run=dry_run)
    console.rule("[bold blue]🏦 Daily Expenses 4 Importer[/bold blue]")

    config = _load_config(config_path)
    db = Database(_DEFAULT_DB_PATH)

    # 1. Detect and parse
    parser = detect_parser(input_path)
    console.print(f"📄 Detected parser: [bold green]{parser.name}[/bold green] for [cyan]{input_path.name}[/cyan]")
    raw_txs = parser.parse(input_path)
    console.print(f"Found [bold]{len(raw_txs)}[/bold] transactions in statement.")

    # 2. Deduplicate
    new_txs = [t for t in raw_txs if not db.is_processed(t.reference)]
    skipped_count = len(raw_txs) - len(new_txs)
    if skipped_count > 0:
        console.print(f"[dim]⏭️ {skipped_count} already imported or skipped.[/dim]")

    if not new_txs:
        console.print("[bold green]✅ Nothing new to import.[/bold green]")
        log_session_end(len(raw_txs), synced=0, failed=0, skipped=skipped_count)
        return

    # 3. Resolve target account
    target_account = account_name
    if not target_account:
        acc_cfg = config.get("accounts", {}).get("default", {})
        target_account = acc_cfg.get("name", "Personal Checking")

    categories = config.get("categories", DEFAULT_CATEGORIES)
    classified_records: list[dict] = []

    # 4. Interactive classification loop
    for idx, tx in enumerate(new_txs, 1):
        console.print(f"\n[dim]Transaction [{idx}/{len(new_txs)}][/dim]")
        console.print(f"  📅 Date: [bold]{tx.date.strftime('%d/%m/%Y')}[/bold] | Amount: [bold green]${tx.amount:.2f} USD[/bold green]")
        console.print(f"  📝 Raw: [cyan]{tx.raw_description}[/cyan]")

        # Handle Transfers
        if tx.tx_type == TransactionType.TRANSFER:
            choice = questionary.select(
                f"Transfer detected ({tx.source_account or 'Checking'} -> {target_account}):",
                choices=[
                    f"✅ Import Transfer (${tx.amount:.2f})",
                    "⏭️ Skip this transfer",
                ],
            ).ask()
            if choice and choice.startswith("✅"):
                classified_records.append({
                    "tx": tx,
                    "amount_usd": tx.amount,
                    "description": tx.description,
                    "category": "",
                    "source_account": tx.source_account or "BanPa Personal",
                    "target_account": tx.target_account or target_account,
                })
            else:
                db.mark_processed(tx.reference, 0, tx.description, status="skipped")
            continue

        # Handle Expenses
        match = classify(tx.description, db)
        if match:
            choice = questionary.select(
                f"Rule matched: [{match.category}] \"{match.description}\"",
                choices=[
                    f"✅ Accept ({match.category} / {match.description})",
                    "✏️ Edit category/description",
                    "⏭️ Skip (e.g. recurring subscription)",
                ],
            ).ask()
            if choice and choice.startswith("✅"):
                classified_records.append({
                    "tx": tx,
                    "amount_usd": tx.amount,
                    "description": match.description,
                    "category": match.category,
                    "target_account": target_account,
                })
                continue
            elif choice and choice.startswith("⏭️"):
                db.mark_processed(tx.reference, 0, tx.description, status="skipped")
                continue

        # Manual classification prompt
        choice = questionary.select(
            f"Action for: \"{tx.description}\" (${tx.amount:.2f} USD)",
            choices=[
                "🏷️ Select Category & Description",
                "⏭️ Skip this transaction (recurring subscription / other)",
            ],
        ).ask()

        if choice and choice.startswith("🏷️"):
            cat = questionary.select("Select Category:", choices=categories).ask() or "Otros"
            desc = questionary.text("Edit Description:", default=tx.description).ask() or tx.description
            save_rule = questionary.confirm("Save rule for future occurrences?", default=True).ask()
            if save_rule:
                db.add_rule(pattern=desc, category=cat, description=desc)

            classified_records.append({
                "tx": tx,
                "amount_usd": tx.amount,
                "description": desc,
                "category": cat,
                "target_account": target_account,
            })
        else:
            db.mark_processed(tx.reference, 0, tx.description, status="skipped")

    if not classified_records:
        console.print("[green]No transactions selected to import.[/green]")
        return

    # 5. Summary and confirmation
    console.print()
    _print_summary(classified_records)

    if dry_run:
        console.print("\n[yellow]🔍 Dry-run complete. No changes made to Daily Expenses 4.[/yellow]")
        return

    proceed = questionary.confirm(
        f"\nLoad {len(classified_records)} transactions into Daily Expenses 4 now?",
        default=True,
    ).ask()

    if not proceed:
        console.print("[dim]Aborted by user.[/dim]")
        return

    # 6. Web automation sync
    from daily_expenses_importer.core.web_automator import (
        get_authenticated_context,
        load_expense,
        load_transfer,
        _session_file_path,
    )
    from playwright.sync_api import sync_playwright

    session_file = _session_file_path(config)
    synced = []
    failed = []

    with sync_playwright() as pw:
        browser, context = get_authenticated_context(pw, session_file=session_file, headless=headless)
        page = context.new_page()
        page.goto("https://dailyexpenses4.com", wait_until="domcontentloaded", timeout=25_000)
        try:
            page.wait_for_selector("app-navbar, [routerlink='/movements']", timeout=10_000)
        except Exception:
            pass

        for idx, rec in enumerate(classified_records, 1):
            tx: NormalizedTransaction = rec["tx"]
            amt = rec["amount_usd"]
            desc = rec["description"]
            try:
                console.print(f"   → [{idx}/{len(classified_records)}] {desc} (${amt:.2f})...", end=" ")
                if tx.tx_type == TransactionType.TRANSFER:
                    load_transfer(
                        page,
                        from_account=rec["source_account"],
                        to_account=rec["target_account"],
                        amount=amt,
                        transfer_date=tx.date,
                        transfer_time=tx.time,
                        description=desc,
                    )
                else:
                    load_expense(
                        page,
                        amount_usd=amt,
                        description=desc,
                        category=rec["category"],
                        account=rec["target_account"],
                        expense_date=tx.date,
                        expense_time=tx.time,
                    )
                console.print("[bold green]✅[/bold green]")
                db.mark_processed(tx.reference, amt, desc, rec.get("category", ""), status="synced", overwrite=True)
                synced.append(rec)
            except Exception as e:
                console.print(f"[bold red]❌ {e}[/bold red]")
                db.mark_processed(tx.reference, amt, desc, rec.get("category", ""), status="failed", overwrite=True)
                failed.append(rec)

        browser.close()

    console.print(f"\n[bold green]Sync finished: {len(synced)} successful, {len(failed)} failed.[/bold green]")
    log_session_end(len(raw_txs), synced=len(synced), failed=len(failed), skipped=skipped_count)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="daily-expenses-importer",
        description="Automated bank statement & credit card importer for Daily Expenses 4.",
    )
    parser.add_argument("-i", "--input", type=Path, required=True, help="Path to bank statement file (.csv, .xls, .xlsx)")
    parser.add_argument("-a", "--account", type=str, default=None, help="Target account name in Daily Expenses 4")
    parser.add_argument("-v", "--visible", "--gui", "--headed", action="store_true", help="Show browser window during sync")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Parse and classify without uploading")
    parser.add_argument("-c", "--config", type=Path, default=_DEFAULT_CONFIG_PATH, help="Path to config.toml")

    args = parser.parse_args()
    if not args.input.exists():
        console.print(f"[bold red]Error: Input file '{args.input}' not found.[/bold red]")
        sys.exit(1)

    run(
        input_path=args.input,
        account_name=args.account,
        dry_run=args.dry_run,
        headless=not args.visible,
        config_path=args.config,
    )


if __name__ == "__main__":
    main()
