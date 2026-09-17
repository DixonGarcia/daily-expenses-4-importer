"""Tests for Generic Excel (.xlsx) parser and multi-sheet setup templates."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from daily_expenses_importer.core.template_generator import generate_excel_template
from daily_expenses_importer.parsers.generic_excel import GenericExcelParser
from daily_expenses_importer.parsers.base import TransactionType


def test_generic_excel_parses_generated_template(tmp_path: Path):
    template_file = tmp_path / "test_template.xlsx"
    generate_excel_template(template_file)

    parser = GenericExcelParser()
    assert parser.supports(template_file, b"")

    txs = parser.parse(template_file)
    assert len(txs) == 5

    # 1. Expense row
    assert txs[0].date == date(2026, 9, 15)
    assert txs[0].time == "14:30:00"
    assert txs[0].description == "Supermarket Groceries"
    assert txs[0].category == "Groceries"
    assert txs[0].amount == Decimal("45.5")
    assert txs[0].tx_type == TransactionType.EXPENSE
    assert txs[0].target_account == "Checking Account"

    # 2. Income row
    assert txs[1].date == date(2026, 9, 16)
    assert txs[1].time == "09:15:00"
    assert txs[1].category == "Income"
    assert txs[1].amount == Decimal("1500")
    assert txs[1].tx_type == TransactionType.INCOME

    # 3. Transfer row
    assert txs[2].date == date(2026, 9, 17)
    assert txs[2].time == "18:20:00"
    assert txs[2].tx_type == TransactionType.TRANSFER
    assert txs[2].source_account == "Checking Account"
    assert txs[2].target_account == "Credit Card"
    assert txs[2].amount == Decimal("120")
