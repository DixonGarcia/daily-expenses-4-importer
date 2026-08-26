"""Playwright automation engine for Daily Expenses 4 (dailyexpenses4.com)."""

import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from daily_expenses_importer.core.logger import get_logger, log_tx_failed, log_tx_loaded

_APP_URL = "https://dailyexpenses4.com"
_SESSION_FILE = Path("data/session_cookies.json")

_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _session_file_path(config: dict) -> Path:
    auth_cfg = config.get("auth", {})
    return Path(auth_cfg.get("session_file", str(_SESSION_FILE)))


def get_authenticated_context(
    playwright: Playwright,
    session_file: Path = _SESSION_FILE,
    headless: bool = True,
) -> tuple[Browser, BrowserContext]:
    """Return an authenticated browser context, or prompt manual login on first run."""
    session_path = Path(session_file)
    browser = playwright.chromium.launch(headless=headless)

    if session_path.exists():
        try:
            cookies = json.loads(session_path.read_text(encoding="utf-8"))
            context = browser.new_context()
            context.add_cookies(cookies)
            print("✅ Session restored successfully.")
            return browser, context
        except Exception:
            print("⚠️ Session file corrupted. Re-authenticating...")

    # First-time headed login
    browser.close()
    print("\n🔐 First time setup: Opening browser for Google Sign-In...")
    headed_browser = playwright.chromium.launch(headless=False)
    context = headed_browser.new_context()
    page = context.new_page()
    page.goto(_APP_URL)

    print("👉 Please log in to Daily Expenses 4 in the browser window.")
    try:
        page.wait_for_selector("app-navbar, [routerlink='/movements'], .navbar", timeout=120_000)
    except Exception:
        headed_browser.close()
        raise TimeoutError("Login timed out after 2 minutes.")

    # Save session cookies
    cookies = context.cookies()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    print(f"✅ Session saved to {session_path}.")
    return headed_browser, context


def _ensure_modal_closed(page: Page) -> None:
    modal = page.locator("#ModalAddMovements")
    if modal.is_visible():
        close_btn = modal.locator(".modal-header button.btn-close, .modal-header button.close")
        if close_btn.count() > 0 and close_btn.first.is_visible():
            close_btn.first.click()
            page.wait_for_timeout(300)


def _open_movement_modal(page: Page) -> None:
    _ensure_modal_closed(page)
    fab = page.locator(".btn-add-movement, button:has(i.bi-plus-lg), button:has(i.fa-plus), button.floating-btn")
    if fab.count() == 0 or not fab.first.is_visible():
        fab = page.locator("button:has-text('+'), button.btn-primary:has-text('Agregar')")

    fab.first.click()
    page.wait_for_selector("#ModalAddMovements", state="visible", timeout=10_000)
    page.wait_for_timeout(200)


def _parse_time_12h(time_str: str) -> tuple[str, str, str]:
    if not time_str:
        now = datetime.now()
        hour_12 = now.strftime("%I")
        minute = now.strftime("%M")
        period = now.strftime("%p")
        return hour_12, minute, period

    parts = time_str.split(":")
    h = int(parts[0])
    m = parts[1] if len(parts) > 1 else "00"
    period = "PM" if h >= 12 else "AM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12:02d}", f"{int(m):02d}", period


def _select_date_in_calendar(page: Page, target_date: date) -> None:
    date_btn = page.locator("#ModalAddMovements button.btn-date, #ModalAddMovements [aria-label*='fecha' i], #ModalAddMovements button:has(i.bi-calendar)")
    if date_btn.count() == 0 or not date_btn.first.is_visible():
        date_btn = page.locator("#ModalAddMovements .input-group button").first

    date_btn.click()
    page.wait_for_selector("ngb-datepicker", state="visible", timeout=5_000)

    # Navigate to target month & year
    for _ in range(24):
        header_el = page.locator("ngb-datepicker-navigation-select, ngb-datepicker .ngb-dp-navigation-select, ngb-datepicker .ngb-dp-month-name")
        header_text = header_el.first.inner_text().strip().lower() if header_el.count() > 0 else ""

        current_month = None
        current_year = None
        for m_name, m_num in _SPANISH_MONTHS.items():
            if m_name in header_text:
                current_month = m_num
                break
        year_match = re.search(r"\b(20\d\d)\b", header_text)
        if year_match:
            current_year = int(year_match.group(1))

        if current_month == target_date.month and current_year == target_date.year:
            break

        if current_year and current_month:
            if (current_year, current_month) > (target_date.year, target_date.month):
                page.locator("ngb-datepicker button[aria-label='Previous month'], ngb-datepicker button[title='Previous month'], ngb-datepicker button:has(i.bi-chevron-left)").first.click()
            else:
                page.locator("ngb-datepicker button[aria-label='Next month'], ngb-datepicker button[title='Next month'], ngb-datepicker button:has(i.bi-chevron-right)").first.click()
            page.wait_for_timeout(100)

    # Click day cell
    day_cell = page.locator(f"ngb-datepicker .ngb-dp-day:not(.disabled) [aria-label*='{target_date.day}'], ngb-datepicker div.btn-light:text-is('{target_date.day}')")
    day_cell.first.click()
    page.wait_for_timeout(150)


def load_expense(
    page: Page,
    amount_usd: Decimal | float | int,
    description: str,
    category: str,
    account: str,
    expense_date: date,
    expense_time: str = "",
) -> None:
    """Load a single expense into Daily Expenses 4."""
    _open_movement_modal(page)
    modal = page.locator("#ModalAddMovements")

    # 1. Amount
    amt_input = modal.locator("input[formcontrolname='quantity'], input.quantity, input[type='number']").first
    amt_input.fill(str(amount_usd))

    # 2. Description
    desc_input = modal.locator("input[formcontrolname='description'], input.description, input[placeholder*='descripción' i]").first
    desc_input.fill(description)

    # 3. Category
    if category:
        cat_btn = modal.locator("button[formcontrolname='category'], button:has-text('Categoría'), .btn-category").first
        if cat_btn.is_visible():
            cat_btn.click()
            page.wait_for_selector(".modal-category, .category-list", timeout=3000)
            page.locator(f".category-item:has-text('{category}'), button:text-is('{category}')").first.click()

    # 4. Account
    if account:
        acc_select = modal.locator("select[formcontrolname='account'], select.account")
        if acc_select.count() > 0 and acc_select.first.is_visible():
            acc_select.first.select_option(label=account)

    # 5. Date & Time
    _select_date_in_calendar(page, expense_date)

    # 6. Save
    save_btn = modal.locator("button.btn-save, button[type='submit']:has-text('Guardar'), button:has-text('Aceptar')").first
    save_btn.click()

    # Wait for modal to dismiss
    modal.wait_for(state="hidden", timeout=10_000)
    page.wait_for_timeout(300)
    log_tx_loaded("EXPENSE", str(amount_usd), description, category, account)


def load_transfer(
    page: Page,
    from_account: str,
    to_account: str,
    amount: Decimal | float | int,
    transfer_date: date,
    transfer_time: str = "",
    description: str = "Transferencia",
) -> None:
    """Load a transfer between two accounts in Daily Expenses 4."""
    _open_movement_modal(page)
    modal = page.locator("#ModalAddMovements")

    # Click Transfer tab
    transfer_tab = modal.locator("a:has-text('Transferencia'), button:has-text('Transferencia'), .nav-link:has-text('Transferencia')").first
    if transfer_tab.is_visible():
        transfer_tab.click()
        page.wait_for_timeout(200)

    # 1. Amount
    amt_input = modal.locator("input[formcontrolname='quantity'], input.quantity, input[type='number']").first
    amt_input.fill(str(amount))

    # 2. From Account
    from_select = modal.locator("select[formcontrolname='accountFrom'], select.account-from").first
    if from_select.is_visible():
        from_select.select_option(label=from_account)

    # 3. To Account
    to_select = modal.locator("select[formcontrolname='accountTo'], select.account-to").first
    if to_select.is_visible():
        to_select.select_option(label=to_account)

    # 4. Description / Note
    desc_input = modal.locator("input[formcontrolname='description'], input.description").first
    if desc_input.is_visible():
        desc_input.fill(description)

    # 5. Date
    _select_date_in_calendar(page, transfer_date)

    # 6. Save
    save_btn = modal.locator("button.btn-save, button[type='submit']:has-text('Guardar')").first
    save_btn.click()

    modal.wait_for(state="hidden", timeout=10_000)
    page.wait_for_timeout(300)
    log_tx_loaded("TRANSFER", str(amount), description, "Transferencia", f"{from_account} -> {to_account}")
