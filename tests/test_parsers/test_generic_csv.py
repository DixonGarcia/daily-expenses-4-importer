"""Tests for Generic CSV parser."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from daily_expenses_importer.parsers.generic_csv import GenericCsvParser
from daily_expenses_importer.parsers.base import TransactionType


def test_generic_csv_parses_standard_csv(tmp_path: Path):
    content = """Date,Description,Amount
2026-08-01,Supermarket,-45.50
2026-08-02,Salary,1200.00
2026-08-03,Gas Station,-30.00
"""
    file_path = tmp_path / "generic.csv"
    file_path.write_text(content, encoding="utf-8")

    parser = GenericCsvParser()
    assert parser.supports(file_path, file_path.read_bytes())

    txs = parser.parse(file_path)
    assert len(txs) == 3

    assert txs[0].date == date(2026, 8, 1)
    assert txs[0].amount == Decimal("45.50")
    assert txs[0].tx_type == TransactionType.EXPENSE
    assert txs[0].description == "Supermarket"

    assert txs[1].date == date(2026, 8, 2)
    assert txs[1].amount == Decimal("1200.00")
    assert txs[1].tx_type == TransactionType.INCOME

    assert txs[2].date == date(2026, 8, 3)
    assert txs[2].amount == Decimal("30.00")
