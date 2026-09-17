"""Playwright automation engine for Daily Expenses 4 (dailyexpenses4.com).

Simulates user interaction with the Angular SPA at https://dailyexpenses4.com:
  - Account selector:  <app-selector-account>
  - Category selector: <app-selector-category>
  - Date & Time:       <app-date-time-picker> (mat-calendar + ngb-timepicker)
  - Save button:       button.save-movement-button
  - Self-healing state recovery on errors.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from rich.console import Console

from daily_expenses_importer.core.logger import log_tx_failed, log_tx_loaded
from daily_expenses_importer.parsers.base import TransactionType

console = Console()

_APP_URL = "https://dailyexpenses4.com"
_MODAL_ID = "#ModalAddMovements"
_DEFAULT_SESSION_FILE = Path("data/session_cookies.json")

# Multi-lingual month name mappings (Spanish, English, Portuguese, French, German, Italian)
_ALL_MONTHS: dict[str, int] = {
    # Spanish / Español
    "ENE": 1, "ENERO": 1,
    "FEB": 2, "FEBRERO": 2,
    "MAR": 3, "MARZO": 3,
    "ABR": 4, "ABRIL": 4,
    "MAY": 5, "MAYO": 5,
    "JUN": 6, "JUNIO": 6,
    "JUL": 7, "JULIO": 7,
    "AGO": 8, "AGOSTO": 8,
    "SEP": 9, "SEPTIEMBRE": 9, "SET": 9, "SETIEMBRE": 9,
    "OCT": 10, "OCTUBRE": 10,
    "NOV": 11, "NOVIEMBRE": 11,
    "DIC": 12, "DICIEMBRE": 12,

    # English
    "JAN": 1, "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APR": 4, "APRIL": 4,
    "JUNE": 6,
    "JULY": 7,
    "AUG": 8, "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,

    # Portuguese / Português
    "FEV": 2, "FEVEREIRO": 2,
    "MAI": 5, "MAIO": 5,
    "SETEMBRO": 9,
    "OUT": 10, "OUTUBRO": 10,
    "DEZ": 12, "DEZEMBRO": 12,
    "JANEIRO": 1, "MARÇO": 3, "MARCO": 3, "JUNHO": 6, "JULHO": 7,

    # French / Français
    "JANV": 1, "JANVIER": 1,
    "FÉVR": 2, "FEVR": 2, "FÉVRIER": 2, "FEVRIER": 2,
    "MARS": 3,
    "AVR": 4, "AVRIL": 4,
    "JUIN": 6,
    "JUIL": 7, "JUILLET": 7,
    "AOÛT": 8, "AOUT": 8,
    "DÉC": 12, "DEC": 12, "DÉCEMBRE": 12, "DECEMBRE": 12,

    # German / Deutsch
    "MÄR": 3, "MÄRZ": 3, "MARZ": 3,
    "OKT": 10, "OKTOBER": 10,

    # Italian / Italiano
    "GEN": 1, "GENNAIO": 1,
    "MAG": 5, "MAGGIO": 5,
    "GIU": 6, "GIUGNO": 6,
    "LUG": 7, "LUGLIO": 7,
    "OTT": 10, "OTTOBRE": 10,
}


def _session_file_path(config: dict) -> Path:
    auth_cfg = config.get("auth", {})
    return Path(auth_cfg.get("session_file", str(_DEFAULT_SESSION_FILE)))


def _is_logged_in(page: Page) -> bool:
    """Check whether the app is showing the authenticated UI."""
    try:
        page.wait_for_selector(
            "app-navbar, [routerlink='/movements'], a[href*='movements'], a[href*='home'], .navbar",
            timeout=6_000,
        )
        return True
    except Exception:
        nav_link = page.get_by_role("link", name=re.compile(r"Movimientos|Movements|Inicio|Home", re.IGNORECASE))
        return nav_link.count() > 0


def _manual_login(playwright_instance: Playwright, session_file: Path) -> tuple[Browser, BrowserContext]:
    """Open a headed browser for the user to log in manually."""
    console.print(
        "\n[bold yellow]🔑 First-time login required.[/bold yellow]\n"
        "A browser window will open. Sign in with Google / Email in Daily Expenses 4.\n"
        "[dim](Credentials are entered directly into the browser; they are never logged or stored.)[/dim]\n"
        "Press [bold green]Enter[/bold green] in this terminal once you see the app home screen."
    )
    browser = playwright_instance.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{_APP_URL}/home", wait_until="domcontentloaded", timeout=30_000)
    try:
        input()  # Wait for user confirmation in terminal
    except (EOFError, KeyboardInterrupt):
        console.print("[yellow]Non-interactive input detected. Verifying login state...[/yellow]")

    if not _is_logged_in(page):
        browser.close()
        raise RuntimeError(
            "Could not confirm login. Make sure you are on the app home screen before pressing Enter."
        )

    session_file.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(session_file))
    console.print("[green]✅ Session saved successfully — future runs will be automatic.[/green]")
    return browser, context


def get_authenticated_context(
    playwright_instance: Playwright,
    session_file: Path = _DEFAULT_SESSION_FILE,
    headless: bool = True,
    slow_mo: int = 0,
) -> tuple[Browser, BrowserContext]:
    """Return (browser, context) with an active authenticated session."""
    session_path = Path(session_file)
    if session_path.exists():
        try:
            content = session_path.read_text(encoding="utf-8").strip()
            if content and content != "[]":
                browser = playwright_instance.chromium.launch(headless=headless, slow_mo=slow_mo)
                context = browser.new_context(storage_state=str(session_path))
                page = context.new_page()
                page.goto(f"{_APP_URL}/home", wait_until="domcontentloaded", timeout=20_000)
                if _is_logged_in(page):
                    page.close()
                    return browser, context
                console.print("[yellow]⚠️ Session expired or invalid — re-authenticating...[/yellow]")
                browser.close()
        except Exception:
            pass

    return _manual_login(playwright_instance, session_path)


# ---------------------------------------------------------------------------
# Self-healing & State Recovery
# ---------------------------------------------------------------------------

def recover_page_state(page: Page) -> None:
    """Safely reset page state: close open modals, clear stuck backdrops, restore clean slate."""
    try:
        modal = page.locator(_MODAL_ID)
        if modal.is_visible():
            close_btn = modal.locator(
                "button.btn-close, [aria-label='Close'], button"
            ).filter(has_text=re.compile(r"Cancelar|Cancel|Close", re.IGNORECASE))
            if close_btn.count() > 0:
                close_btn.first.click()
                page.wait_for_timeout(200)
            else:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
    except Exception:
        pass

    # Remove any stuck backdrops
    try:
        page.evaluate("""
            document.querySelectorAll('.modal-backdrop, .cdk-overlay-backdrop').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
        """)
    except Exception:
        pass

    page.wait_for_timeout(200)


def _open_movement_modal(page: Page) -> None:
    """Ensure clean state and open the Add Movement modal."""
    recover_page_state(page)

    modal = page.locator(_MODAL_ID)
    if not modal.is_visible():
        if "/movements" not in page.url and "/home" not in page.url:
            movimientos_link = page.get_by_role("link", name=re.compile(r"Movimientos|Movements|Inicio|Home", re.IGNORECASE))
            if movimientos_link.count() > 0:
                movimientos_link.first.click()
                page.wait_for_timeout(400)

        fab_btn = page.locator(
            "button.btn-circle-lg, button.btn-floating, button.floating-action-button, button.btn-primary:has(img[src*='icon-add']), button:has(i.bi-plus), button.btn-add-movement"
        ).or_(page.get_by_role("button").filter(has_text=re.compile(r"^\s*\+\s*$")))

        if fab_btn.count() > 0:
            fab_btn.last.click()

        try:
            modal.wait_for(state="visible", timeout=8_000)
        except Exception:
            # Fallback retry click
            if fab_btn.count() > 0:
                fab_btn.last.click()
            modal.wait_for(state="visible", timeout=8_000)

    page.wait_for_timeout(150)


# ---------------------------------------------------------------------------
# Date & Time Picker Helpers
# ---------------------------------------------------------------------------

def _parse_calendar_header(text: str) -> tuple[int, int] | None:
    """Extract (year, month_number) from mat-calendar header text."""
    if not text:
        return None
    upper = text.strip().upper()
    match = re.search(r"\b(20\d\d)\b", upper)
    year = int(match.group(1)) if match else date.today().year

    # Sort month names by length descending to match full names first
    for name, month_num in sorted(_ALL_MONTHS.items(), key=lambda x: len(x[0]), reverse=True):
        if name in upper:
            return (year, month_num)
    return None


def _parse_time_12h(time_str: str) -> tuple[int, int, str]:
    """Parse a time string (e.g. '18:14:47' or '08:35') into (hour_12, minute, meridian)."""
    if not time_str:
        now = datetime.now()
        hour_24 = now.hour
        minute = now.minute
    else:
        try:
            parts = time_str.strip().split(":")
            hour_24 = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            return (12, 0, "AM")

    is_pm = hour_24 >= 12
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12
    meridian = "PM" if is_pm else "AM"
    return (hour_12, minute, meridian)


def _set_date_and_time(modal, target_date: date, target_time: str = "") -> None:
    """Set exact date and time in the <app-date-time-picker> component."""
    date_btn = modal.locator("app-date-time-picker button.btn, app-date-time-picker button[data-bs-toggle='dropdown'], app-date-time-picker button")
    if date_btn.count() == 0:
        return

    date_btn.first.click()
    modal.page.wait_for_timeout(250)

    # 1. Month / Year navigation in mat-calendar
    target_year = target_date.year
    target_month = target_date.month

    for _ in range(24):
        header_btn = modal.locator("mat-calendar button.mat-calendar-period-button")
        if header_btn.count() == 0:
            break
        header_text = header_btn.first.inner_text()
        current = _parse_calendar_header(header_text)
        if not current:
            break

        curr_year, curr_month = current
        if (curr_year, curr_month) == (target_year, target_month):
            break

        if (curr_year, curr_month) > (target_year, target_month):
            prev_btn = modal.locator("mat-calendar button.mat-calendar-previous-button, mat-calendar button[aria-label*='Previous'], mat-calendar button[aria-label*='Anterior']")
            if prev_btn.count() > 0:
                prev_btn.first.click()
                modal.page.wait_for_timeout(100)
        else:
            next_btn = modal.locator("mat-calendar button.mat-calendar-next-button, mat-calendar button[aria-label*='Next'], mat-calendar button[aria-label*='Siguiente']")
            if next_btn.count() > 0:
                next_btn.first.click()
                modal.page.wait_for_timeout(100)

    # 2. Select specific day
    day_cell = modal.locator("mat-calendar button.mat-calendar-body-cell").filter(
        has_text=re.compile(rf"^\s*{target_date.day}\s*$")
    ).or_(
        modal.locator(f"mat-calendar button[aria-label*='{target_date.day} ']")
    ).first

    if day_cell.count() > 0:
        day_cell.click()
        modal.page.wait_for_timeout(150)

    # 3. Set time in ngb-timepicker if present
    hour_12, minute, target_meridian = _parse_time_12h(target_time)

    hour_input = modal.locator("ngb-timepicker input[aria-label*='Hour'], ngb-timepicker input[aria-label*='Hora'], ngb-timepicker .ngb-tp-hour input")
    if hour_input.count() > 0:
        hour_input.first.click()
        hour_input.first.fill(f"{hour_12:02d}")

    minute_input = modal.locator("ngb-timepicker input[aria-label*='Minute'], ngb-timepicker input[aria-label*='Minuto'], ngb-timepicker .ngb-tp-minute input")
    if minute_input.count() > 0:
        minute_input.first.click()
        minute_input.first.fill(f"{minute:02d}")

    meridian_btn = modal.locator("ngb-timepicker .ngb-tp-meridian button")
    if meridian_btn.count() > 0:
        current_meridian = meridian_btn.first.inner_text().strip().upper()
        if target_meridian in ("AM", "PM") and current_meridian != target_meridian:
            meridian_btn.first.click()

    modal.page.wait_for_timeout(150)

    # 4. Confirm picker
    ok_btn = modal.locator("app-date-time-picker button").filter(has_text=re.compile(r"Aceptar|Ok|Confirm|Guardar", re.IGNORECASE))
    if ok_btn.count() > 0:
        ok_btn.first.click()
        modal.page.wait_for_timeout(150)


# ---------------------------------------------------------------------------
# Movement Loaders
# ---------------------------------------------------------------------------

def _select_account(modal, page: Page, account_name: str) -> None:
    """Select account in <app-selector-account> component."""
    if not account_name:
        return
    acc_btn = modal.locator("app-selector-account button")
    if acc_btn.count() > 0:
        acc_btn.first.click()
        page.wait_for_timeout(200)
        account_item = modal.locator("app-selector-account .dropdown-menu .item-list, app-selector-account .dropdown-item").filter(
            has_text=re.compile(re.escape(account_name), re.IGNORECASE)
        ).first
        if account_item.count() > 0:
            account_item.click()
        else:
            modal.get_by_text(account_name, exact=False).first.click()
        page.wait_for_timeout(150)


def _select_category(modal, page: Page, category_name: str) -> None:
    """Select category in <app-selector-category> component."""
    if not category_name:
        return
    cat_btn = modal.locator("app-selector-category button")
    if cat_btn.count() > 0:
        cat_btn.first.click()
        page.wait_for_timeout(200)
        category_item = modal.locator("app-selector-category .dropdown-menu .item-list, app-selector-category .dropdown-item").filter(
            has_text=re.compile(re.escape(category_name), re.IGNORECASE)
        ).first
        if category_item.count() > 0:
            category_item.click()
        else:
            modal.get_by_text(category_name, exact=False).first.click()
        page.wait_for_timeout(150)


def load_expense(
    page: Page,
    amount: Decimal | float | int,
    description: str,
    category: str,
    account: str,
    expense_date: date,
    expense_time: str = "",
) -> None:
    """Load a single expense into Daily Expenses 4."""
    _open_movement_modal(page)
    modal = page.locator(_MODAL_ID)

    # 1. Amount
    amount_field = modal.locator("input.quantity, input[type='number'], input[formcontrolname='quantity']").first
    amount_field.wait_for(state="visible", timeout=6_000)
    amount_field.click()
    amount_field.fill(f"{amount:.2f}" if isinstance(amount, (Decimal, float)) else str(amount))

    # 2. Account
    _select_account(modal, page, account)

    # 3. Category
    _select_category(modal, page, category)

    # 4. Description
    desc_field = modal.locator("textarea, input[formcontrolname='description']").first
    if desc_field.count() > 0:
        desc_field.fill(description)

    # 5. Date & Time
    _set_date_and_time(modal, target_date=expense_date, target_time=expense_time)

    # 6. Save button
    save_btn = modal.locator("button.save-movement-button, button[type='submit']").or_(
        modal.locator("button").filter(has_text=re.compile(r"Save|Guardar", re.IGNORECASE))
    ).first
    save_btn.click()

    # Wait for modal to dismiss cleanly
    try:
        modal.wait_for(state="hidden", timeout=8_000)
    except Exception:
        # Check if saved or if validation error occurred
        if modal.is_visible():
            recover_page_state(page)
            raise RuntimeError(f"Modal did not close after save for '{description}'.")

    page.wait_for_timeout(250)
    log_tx_loaded("EXPENSE", str(amount), description, category, account)


def load_transfer(
    page: Page,
    from_account: str,
    to_account: str,
    amount: Decimal | float | int,
    transfer_date: date,
    transfer_time: str = "",
    description: str = "Transfer",
) -> None:
    """Load an account-to-account transfer into Daily Expenses 4."""
    _open_movement_modal(page)
    modal = page.locator(_MODAL_ID)

    # Switch to Transfer tab (supports both English and Spanish UI)
    transfer_tab = modal.locator(
        "a:has-text('Transfer'), a:has-text('Transferencia'), button:has-text('Transfer'), button:has-text('Transferencia'), .nav-link:has-text('Transfer'), .nav-link:has-text('Transferencia')"
    ).first
    if transfer_tab.is_visible():
        transfer_tab.click()
        page.wait_for_timeout(200)

    # 1. Amount
    amount_field = modal.locator("input.quantity, input[type='number'], input[formcontrolname='quantity']").first
    amount_field.click()
    amount_field.fill(f"{amount:.2f}" if isinstance(amount, (Decimal, float)) else str(amount))

    # 2. From Account
    from_btn = modal.locator("app-selector-account-from button, select[formcontrolname='accountFrom']").first
    if from_btn.is_visible():
        if from_btn.evaluate("el => el.tagName.toLowerCase()") == "select":
            from_btn.select_option(label=from_account)
        else:
            from_btn.click()
            page.wait_for_timeout(150)
            modal.locator("app-selector-account-from .dropdown-item, app-selector-account-from .item-list").filter(
                has_text=re.compile(re.escape(from_account), re.IGNORECASE)
            ).first.click()

    # 3. To Account
    to_btn = modal.locator("app-selector-account-to button, select[formcontrolname='accountTo']").first
    if to_btn.is_visible():
        if to_btn.evaluate("el => el.tagName.toLowerCase()") == "select":
            to_btn.select_option(label=to_account)
        else:
            to_btn.click()
            page.wait_for_timeout(150)
            modal.locator("app-selector-account-to .dropdown-item, app-selector-account-to .item-list").filter(
                has_text=re.compile(re.escape(to_account), re.IGNORECASE)
            ).first.click()

    # 4. Description
    desc_field = modal.locator("textarea, input[formcontrolname='description']").first
    if desc_field.count() > 0:
        desc_field.fill(description)

    # 5. Date & Time
    _set_date_and_time(modal, target_date=transfer_date, target_time=transfer_time)

    # 6. Save
    save_btn = modal.locator("button.save-movement-button, button[type='submit']").or_(
        modal.locator("button").filter(has_text=re.compile(r"Save|Guardar", re.IGNORECASE))
    ).first
    save_btn.click()

    try:
        modal.wait_for(state="hidden", timeout=8_000)
    except Exception:
        recover_page_state(page)
        raise RuntimeError(f"Modal did not close after transfer save for '{description}'.")

    page.wait_for_timeout(250)
    log_tx_loaded("TRANSFER", str(amount), description, "Transfer", f"{from_account} -> {to_account}")


def load_movement(page: Page, record: dict, default_account: str) -> None:
    """Unified movement loader dispatching to Expense or Transfer."""
    tx = record.get("tx")
    amt = record.get("amount", Decimal("0"))
    desc = record.get("description", "")
    cat = record.get("category", "Other")
    target_acc = record.get("target_account") or default_account
    tx_date = record.get("date", date.today())
    tx_time = record.get("time", "")

    tx_type = record.get("tx_type") or (tx.tx_type if tx else TransactionType.EXPENSE)

    if tx_type == TransactionType.TRANSFER:
        src_acc = record.get("source_account") or default_account
        load_transfer(
            page,
            from_account=src_acc,
            to_account=target_acc,
            amount=amt,
            transfer_date=tx_date,
            transfer_time=tx_time,
            description=desc,
        )
    else:
        load_expense(
            page,
            amount=amt,
            description=desc,
            category=cat,
            account=target_acc,
            expense_date=tx_date,
            expense_time=tx_time,
        )


def run_automation(
    records: list[dict],
    default_account: str,
    config: dict,
    headless: bool = True,
    slow_mo: int = 0,
) -> dict[str, list[dict]]:
    """Execute Playwright automation for a list of movement records with self-healing error recovery."""
    session_file = _session_file_path(config)
    results = {"synced": [], "failed": []}

    with sync_playwright() as pw:
        browser, context = get_authenticated_context(
            pw, session_file=session_file, headless=headless, slow_mo=slow_mo
        )
        page = context.new_page()
        page.goto(f"{_APP_URL}/home", wait_until="domcontentloaded", timeout=25_000)
        try:
            page.wait_for_selector("app-navbar, [routerlink='/movements']", timeout=8_000)
        except Exception:
            pass

        for idx, rec in enumerate(records, 1):
            desc = rec.get("description", "")
            amt = rec.get("amount", Decimal("0"))
            cat = rec.get("category", "")
            acc = rec.get("target_account", default_account)
            ref = rec.get("reference", "")

            console.print(f"   → [{idx}/{len(records)}] {desc} (${amt:.2f}) [{cat or acc}]...", end=" ")
            try:
                load_movement(page, rec, default_account=default_account)
                console.print("[bold green]✅[/bold green]")
                results["synced"].append(rec)
            except Exception as exc:
                console.print(f"[bold red]❌ {exc}[/bold red]")
                log_tx_failed(ref, desc, str(exc))
                rec_failed = dict(rec)
                rec_failed["error"] = str(exc)
                results["failed"].append(rec_failed)
                # Self-healing: reset page state to prevent cascading failures
                recover_page_state(page)

        browser.close()

    return results
