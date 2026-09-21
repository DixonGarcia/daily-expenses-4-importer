"""Command-line interface entry point for Daily Expenses 4 Importer."""

from __future__ import annotations

import argparse
import csv
import sys
import tomllib
from decimal import Decimal
from pathlib import Path
import questionary
from rich.console import Console
from rich.table import Table

from daily_expenses_importer.core.db import Database
from daily_expenses_importer.core.classifier import classify
from daily_expenses_importer.core.logger import log_session_start, log_session_end
from daily_expenses_importer.core.metadata_fetcher import (
    fetch_app_metadata,
    save_cached_metadata,
    load_cached_metadata,
)
from daily_expenses_importer.core.template_generator import (
    DEFAULT_CATEGORIES,
    generate_excel_template,
    generate_csv_template,
)
from daily_expenses_importer.core.web_automator import run_automation
from daily_expenses_importer.parsers import detect_parser
from daily_expenses_importer.parsers.base import NormalizedTransaction, TransactionType

console = Console()
_DEFAULT_DB_PATH = Path("data/importer.db")
_DEFAULT_CONFIG_PATH = Path("data/config.toml")


def _load_config(config_path: Path) -> dict:
    if config_path.exists():
        try:
            return tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to read {config_path}: {e}. Using defaults.[/yellow]")
    return {}


def _print_summary(records: list[dict]) -> None:
    table = Table(title="Transactions to Import", show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Category / Account", style="green")
    table.add_column("Amount", justify="right", style="bold yellow", no_wrap=True)

    total_expenses = Decimal("0")
    total_income = Decimal("0")
    total_transfers = Decimal("0")

    for idx, r in enumerate(records, 1):
        tx: NormalizedTransaction = r["tx"]
        amt = r["amount"]
        if tx.tx_type == TransactionType.EXPENSE:
            total_expenses += amt
            tx_type_str = "Expense"
        elif tx.tx_type == TransactionType.INCOME:
            total_income += amt
            tx_type_str = "Income"
        elif tx.tx_type == TransactionType.TRANSFER:
            total_transfers += amt
            tx_type_str = "Transfer"
        else:
            tx_type_str = "Refund"

        cat_or_acc = r.get("category", "")
        if tx.tx_type == TransactionType.TRANSFER:
            cat_or_acc = f"{r.get('source_account', '')} -> {r.get('target_account', '')}"

        table.add_row(
            str(idx),
            tx.date.strftime("%Y-%m-%d"),
            tx_type_str,
            r["description"],
            cat_or_acc,
            f"${amt:.2f}",
        )

    table.add_section()
    if total_expenses > Decimal("0"):
        table.add_row("", "Expenses", "", "", "", f"-${total_expenses:.2f}", style="bold red")
    if total_income > Decimal("0"):
        table.add_row("", "Income", "", "", "", f"+${total_income:.2f}", style="bold green")
    if total_transfers > Decimal("0"):
        table.add_row("", "Transfers", "", "", "", f"${total_transfers:.2f}", style="bold cyan")
    table.add_row("", "Total", "", f"{len(records)} movements", "", f"${(total_expenses + total_income + total_transfers):.2f}", style="bold")
    console.print(table)


def _print_failed_table(failed_records: list[dict]) -> None:
    table = Table(title="⚠️ Failed Movements", show_header=True, header_style="bold red", expand=True)
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Amount", justify="right", style="yellow", no_wrap=True)
    table.add_column("Error Reason", style="bold red")

    for idx, r in enumerate(failed_records, 1):
        tx: NormalizedTransaction = r["tx"]
        amt = r["amount"]
        err = r.get("error", "Unknown error")
        table.add_row(
            str(idx),
            tx.date.strftime("%Y-%m-%d"),
            r["description"],
            f"${amt:.2f}",
            err,
        )
    console.print(table)


def _export_failed_csv(failed_records: list[dict], export_path: Path) -> None:
    """Export failed records to a CSV file matching the Accounting Ledger template format."""
    with open(export_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "description", "expense", "income", "category", "account"])
        for r in failed_records:
            tx: NormalizedTransaction = r["tx"]
            acc_str = r.get("target_account", "")
            if tx.tx_type == TransactionType.TRANSFER:
                acc_str = f"{r.get('source_account', '')} -> {r.get('target_account', '')}"

            time_str = f" {tx.time}" if tx.time else " 12:00:00"
            date_time_str = f"{tx.date.strftime('%Y-%m-%d')}{time_str}"

            if tx.tx_type == TransactionType.INCOME:
                expense_val = ""
                income_val = f"{r['amount']:.2f}"
            else:
                expense_val = f"{r['amount']:.2f}"
                income_val = ""

            writer.writerow([
                date_time_str,
                r["description"],
                expense_val,
                income_val,
                r.get("category", ""),
                acc_str,
            ])
    console.print(f"[bold green]💾 Exported {len(failed_records)} failed movements to: {export_path}[/bold green]")


def generate_templates(target_dir: Path = Path("."), sync_first: bool = False, config: dict | None = None) -> None:
    """Create sample template.xlsx and template.csv in target directory, optionally syncing live metadata."""
    if sync_first:
        console.print("[bold cyan]🔄 Syncing accounts and categories from Daily Expenses 4 before generating...[/bold cyan]")
        try:
            metadata = fetch_app_metadata(config=config, headless=True)
            save_cached_metadata(metadata)
            console.print("[green]✅ Successfully fetched live accounts and categories.[/green]")
        except Exception as exc:
            console.print(f"[yellow]⚠️ Could not sync live metadata: {exc}. Using existing cache or defaults.[/yellow]")

    cached = load_cached_metadata()
    if cached:
        acc_count = len(cached.get("accounts", []))
        exp_count = len(cached.get("expense_categories", []))
        inc_count = len(cached.get("income_categories", []))
        console.print(
            f"[dim]ℹ️ Using synced metadata from Daily Expenses 4: "
            f"{acc_count} accounts, {exp_count} expense categories, {inc_count} income categories.[/dim]"
        )

    xlsx_path = target_dir / "template.xlsx"
    csv_path = target_dir / "template.csv"

    generate_excel_template(xlsx_path)
    generate_csv_template(csv_path)

    console.print(f"[bold green]✅ Templates created successfully (Accounting Ledger format):[/bold green]")
    console.print(f"  📊 Excel (Setup & Movements sheets):  [cyan]{xlsx_path.resolve()}[/cyan]")
    console.print(f"  📄 Plain CSV:                         [cyan]{csv_path.resolve()}[/cyan]\n")
    console.print("Fill either file with your movements and run:")
    console.print(f"  [cyan]daily-expenses-importer -i {xlsx_path.name}[/cyan]  (or [cyan]-i {csv_path.name}[/cyan])\n")


def sync_metadata_command(config: dict | None = None, visible: bool = False) -> None:
    """CLI command to sync accounts and categories from Daily Expenses 4 and display them."""
    console.print("───────────────── 🔄 Syncing Daily Expenses 4 Metadata ─────────────────")
    try:
        data = fetch_app_metadata(config=config, headless=not visible)
        save_cached_metadata(data)
    except Exception as exc:
        console.print(f"[bold red]❌ Failed to sync metadata: {exc}[/bold red]")
        return

    accounts = data.get("accounts", [])
    expense_cats = data.get("expense_categories", [])
    income_cats = data.get("income_categories", [])

    # Display results in structured tables
    acc_table = Table(title="🏦 Active Accounts", show_header=True, header_style="bold cyan")
    acc_table.add_column("#", style="dim", justify="right", width=4)
    acc_table.add_column("Account Name", style="bold green")
    for idx, acc in enumerate(accounts, 1):
        acc_table.add_row(str(idx), acc)
    console.print(acc_table)
    console.print()

    cat_table = Table(title="🏷️ Categories", show_header=True, header_style="bold cyan")
    cat_table.add_column("Expense Categories (Gastos)", style="yellow")
    cat_table.add_column("Income Categories (Ingresos)", style="green")

    max_rows = max(len(expense_cats), len(income_cats))
    for i in range(max_rows):
        exp_val = expense_cats[i] if i < len(expense_cats) else ""
        inc_val = income_cats[i] if i < len(income_cats) else ""
        cat_table.add_row(exp_val, inc_val)
    console.print(cat_table)

    console.print(f"\n[bold green]✅ Synced metadata saved to: data/metadata.json[/bold green]")
    console.print("[dim]Next template generation with --template will use these exact names.[/dim]\n")


def run(
    input_path: Path,
    account_name: str | None = None,
    dry_run: bool = False,
    headless: bool = True,
    config_path: Path = _DEFAULT_CONFIG_PATH,
) -> None:
    """Run the import pipeline with interactive classification, resilient web loading, and failure retry."""
    log_session_start(input_path, dry_run=dry_run)
    console.rule("[bold blue]🏦 Daily Expenses 4 Importer[/bold blue]")

    config = _load_config(config_path)
    db = Database(_DEFAULT_DB_PATH)

    # 1. Detect and parse
    parser = detect_parser(input_path)
    console.print(f"📄 Parser: [bold green]{parser.name}[/bold green] | File: [cyan]{input_path.name}[/cyan]")
    raw_txs = parser.parse(input_path)
    console.print(f"Found [bold]{len(raw_txs)}[/bold] movements in file.")

    # 2. Deduplicate
    new_txs = [t for t in raw_txs if not db.is_processed(t.reference)]
    skipped_count = len(raw_txs) - len(new_txs)
    if skipped_count > 0:
        console.print(f"[dim]⏭️ {skipped_count} already imported or skipped in past runs.[/dim]")

    if not new_txs:
        console.print("[bold green]✅ Nothing new to import.[/bold green]")
        log_session_end(len(raw_txs), synced=0, failed=0, skipped=skipped_count)
        return

    # 3. Resolve target account & categories
    target_account = account_name
    if not target_account:
        acc_cfg = config.get("accounts", {}).get("default", {})
        target_account = acc_cfg.get("name", "Checking Account")

    categories = config.get("categories", DEFAULT_CATEGORIES)
    classified_records: list[dict] = []

    # 4. Classification loop (automatic if category already present in CSV, else interactive)
    for idx, tx in enumerate(new_txs, 1):
        rec_category = tx.category or ""
        rec_desc = tx.description
        rec_acc = tx.target_account or target_account
        rec_src_acc = tx.source_account or "Checking Account"

        # If it's a Transfer
        if tx.tx_type == TransactionType.TRANSFER:
            classified_records.append({
                "tx": tx,
                "amount": tx.amount,
                "description": rec_desc,
                "category": "",
                "source_account": rec_src_acc,
                "target_account": rec_acc,
                "reference": tx.reference,
                "date": tx.date,
                "time": tx.time,
                "tx_type": TransactionType.TRANSFER,
            })
            continue

        # If CSV already specified a category, use it directly!
        if rec_category:
            classified_records.append({
                "tx": tx,
                "amount": tx.amount,
                "description": rec_desc,
                "category": rec_category,
                "target_account": rec_acc,
                "reference": tx.reference,
                "date": tx.date,
                "time": tx.time,
                "tx_type": tx.tx_type,
            })
            continue

        # Check saved rules in DB
        match = classify(rec_desc, db)
        if match:
            choice = questionary.select(
                f"Rule matched for [{rec_desc}]: {match.category} / {match.description}",
                choices=[
                    f"✅ Accept ({match.category} / {match.description})",
                    "✏️ Edit category or description",
                    "⏭️ Skip this transaction",
                ],
            ).ask()
            if choice is None:
                console.print("\n[dim]Import aborted by user.[/dim]")
                return
            if choice.startswith("✅"):
                classified_records.append({
                    "tx": tx,
                    "amount": tx.amount,
                    "description": match.description,
                    "category": match.category,
                    "target_account": rec_acc,
                    "reference": tx.reference,
                    "date": tx.date,
                    "time": tx.time,
                    "tx_type": tx.tx_type,
                })
                continue
            elif choice.startswith("⏭️"):
                db.mark_processed(tx.reference, 0, rec_desc, status="skipped")
                continue

        # Manual classification prompt
        console.print(f"\n[dim]Transaction [{idx}/{len(new_txs)}][/dim]")
        console.print(f"  📅 Date: [bold]{tx.date.strftime('%d/%m/%Y')}[/bold] | Amount: [bold green]${tx.amount:.2f}[/bold green]")
        console.print(f"  📝 Description: [cyan]{tx.description}[/cyan]")

        choice = questionary.select(
            f"Action for: \"{tx.description}\" (${tx.amount:.2f})",
            choices=[
                "🏷️ Select Category & Description",
                "⏭️ Skip this transaction",
            ],
        ).ask()

        if choice is None:
            console.print("\n[dim]Import aborted by user.[/dim]")
            return

        if choice.startswith("🏷️"):
            cat = questionary.select("Select Category:", choices=categories).ask()
            if cat is None:
                console.print("\n[dim]Import aborted by user.[/dim]")
                return
            desc = questionary.text("Edit Description:", default=tx.description).ask()
            if desc is None:
                console.print("\n[dim]Import aborted by user.[/dim]")
                return
            save_rule = questionary.confirm("Save rule for future occurrences?", default=True).ask()
            if save_rule is None:
                console.print("\n[dim]Import aborted by user.[/dim]")
                return
            if save_rule:
                db.add_rule(pattern=desc, category=cat, description=desc)

            classified_records.append({
                "tx": tx,
                "amount": tx.amount,
                "description": desc,
                "category": cat,
                "target_account": rec_acc,
                "reference": tx.reference,
                "date": tx.date,
                "time": tx.time,
                "tx_type": tx.tx_type,
            })
        elif choice.startswith("⏭️"):
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
        f"\nLoad {len(classified_records)} movements into Daily Expenses 4 now?",
        default=True,
    ).ask()

    if not proceed:
        console.print("[dim]Aborted by user.[/dim]")
        return

    # 6. Web automation sync & Retry Loop
    console.print("\n[bold blue]🚀 Starting web sync with Daily Expenses 4...[/bold blue]")
    current_batch = list(classified_records)
    all_synced: list[dict] = []
    all_failed: list[dict] = []

    while current_batch:
        results = run_automation(
            records=current_batch,
            default_account=target_account,
            config=config,
            headless=headless,
        )

        batch_synced = results.get("synced", [])
        batch_failed = results.get("failed", [])

        # Mark successes in DB
        for r in batch_synced:
            tx = r["tx"]
            db.mark_processed(
                reference=tx.reference,
                amount_usd=r["amount"],
                description=r["description"],
                category=r.get("category", ""),
                status="synced",
                overwrite=True,
            )
            all_synced.append(r)

        # Mark failures in DB
        for r in batch_failed:
            tx = r["tx"]
            db.mark_processed(
                reference=tx.reference,
                amount_usd=r["amount"],
                description=r["description"],
                category=r.get("category", ""),
                status="failed",
                overwrite=True,
            )

        if not batch_failed:
            all_failed = []
            break

        all_failed = batch_failed
        console.print()
        _print_failed_table(all_failed)

        retry_choice = questionary.confirm(
            f"⚠️ {len(all_failed)} movements failed to sync. Do you want to retry them now?",
            default=True,
        ).ask()

        if retry_choice:
            console.print(f"\n[bold yellow]🔄 Retrying {len(all_failed)} failed movements...[/bold yellow]")
            current_batch = [dict(r) for r in all_failed]
        else:
            break

    # 7. Final wrap up & optional export of failed items
    console.print(f"\n[bold green]✅ Sync finished: {len(all_synced)} successful, {len(all_failed)} failed.[/bold green]")
    log_session_end(len(raw_txs), synced=len(all_synced), failed=len(all_failed), skipped=skipped_count)

    if all_failed:
        export_choice = questionary.confirm(
            f"Save the {len(all_failed)} remaining failed movements to 'failed_movements.csv' for later retry?",
            default=True,
        ).ask()
        if export_choice:
            _export_failed_csv(all_failed, Path("failed_movements.csv"))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="daily-expenses-importer",
        description="Automated bank statement & CSV importer for Daily Expenses 4.",
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=None,
        help="Path to bank statement file (.csv, .xls, .xlsx, .tsv)",
    )
    parser.add_argument(
        "-t", "--template",
        action="store_true",
        help="Generate Accounting Ledger 'template.xlsx' and 'template.csv'",
    )
    parser.add_argument(
        "-s", "--sync-metadata",
        action="store_true",
        help="Fetch active accounts and categories from Daily Expenses 4 and save to local cache",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="When used with --template, fetch fresh metadata from Daily Expenses 4 before generating",
    )
    parser.add_argument(
        "-a", "--account",
        type=str,
        default=None,
        help="Target account name in Daily Expenses 4 (e.g. 'Personal Checking')",
    )
    parser.add_argument(
        "-v", "--visible", "--gui", "--headed",
        action="store_true",
        help="Show browser window during automation",
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Parse and classify without uploading to Daily Expenses 4",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=_DEFAULT_CONFIG_PATH,
        help="Path to config.toml",
    )

    args = parser.parse_args()

    if args.sync_metadata:
        cfg = _load_config(args.config)
        sync_metadata_command(config=cfg, visible=args.visible)
        return

    if args.template:
        cfg = _load_config(args.config)
        generate_templates(sync_first=args.sync, config=cfg)
        return

    if not args.input:
        parser.print_help()
        console.print("\n[yellow]👉 Tip: Run with `--template` to generate ready-to-use Excel and CSV templates.[/yellow]")
        sys.exit(1)

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
