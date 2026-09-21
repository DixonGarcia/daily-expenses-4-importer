"""Fetches and synchronizes user accounts and categories from Daily Expenses 4."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
from rich.console import Console

from daily_expenses_importer.core.web_automator import get_authenticated_context, _session_file_path

console = Console()
_DEFAULT_METADATA_PATH = Path("data/metadata.json")


def fetch_app_metadata(
    config: dict | None = None,
    headless: bool = True,
) -> dict:
    """Connect to Daily Expenses 4 and extract active accounts, expense categories, and income categories."""
    config = config or {}
    session_file = _session_file_path(config)

    with sync_playwright() as pw:
        browser, context = get_authenticated_context(pw, session_file=session_file, headless=headless)
        page = context.new_page()

        # -------------------------------------------------------------
        # 1. Accounts Extraction (/accounts)
        # -------------------------------------------------------------
        console.print("   → Fetching accounts from Daily Expenses 4...")
        page.goto("https://dailyexpenses4.com/accounts", wait_until="networkidle", timeout=30_000)

        active_accounts: list[str] = []
        for h5 in page.locator("h5").all():
            text = h5.inner_text().strip()
            classes = h5.get_attribute("class") or ""
            # Filter accounts by presence of currency lines or structure
            if text and ("\n" in text or "USD" in text or "EUR" in text):
                is_strike = "strike" in classes
                name = text.split("\n")[0].strip()
                if not is_strike and name and name not in active_accounts:
                    active_accounts.append(name)

        # -------------------------------------------------------------
        # 2. Categories Extraction (/categories)
        # -------------------------------------------------------------
        console.print("   → Fetching income and expense categories...")
        page.goto("https://dailyexpenses4.com/categories", wait_until="networkidle", timeout=30_000)

        income_categories: list[str] = []
        expense_categories: list[str] = []

        scrollables = page.locator(".scrollable").all()
        if len(scrollables) >= 2:
            income_categories = [
                t.strip() for t in scrollables[0].locator("h5").all_inner_texts()
                if t.strip() and len(t.strip()) < 40
            ]
            expense_categories = [
                t.strip() for t in scrollables[1].locator("h5").all_inner_texts()
                if t.strip() and len(t.strip()) < 40
            ]
        else:
            # Fallback for alternative screen layouts
            all_cats = [
                t.strip() for t in page.locator("h5.gray").all_inner_texts()
                if t.strip() and len(t.strip()) < 40
            ]
            expense_categories = all_cats

        browser.close()

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "accounts": active_accounts,
        "expense_categories": sorted(list(set(expense_categories))),
        "income_categories": sorted(list(set(income_categories))),
    }


def load_cached_metadata(cache_path: Path = _DEFAULT_METADATA_PATH) -> dict | None:
    """Load metadata from local JSON cache if available."""
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_cached_metadata(metadata: dict, cache_path: Path = _DEFAULT_METADATA_PATH) -> None:
    """Save metadata to local JSON cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
