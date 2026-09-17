"""Tests for Generic CSV parser and standard template format."""

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


def test_generic_csv_parses_template_format(tmp_path: Path):
    content = """date,description,category,amount,type,account
2026-09-15 14:30:00,Supermarket Groceries,Groceries,45.50,expense,Checking Account
2026-09-16 09:15:00,Monthly Salary Deposit,Income,1500.00,income,Checking Account
2026-09-17 18:20:00,Credit Card Payment,Transfer,120.00,transfer,Checking Account -> Credit Card
2026-09-18 11:45:00,Pharmacy & Medicine,Healthcare,12.30,expense,Checking Account
"""
    file_path = tmp_path / "template.csv"
    file_path.write_text(content, encoding="utf-8")

    parser = GenericCsvParser()
    assert parser.supports(file_path, file_path.read_bytes())

    txs = parser.parse(file_path)
    assert len(txs) == 4

    # Row 1: Expense with Category & Time
    assert txs[0].date == date(2026, 9, 15)
    assert txs[0].time == "14:30:00"
    assert txs[0].description == "Supermarket Groceries"
    assert txs[0].category == "Groceries"
    assert txs[0].amount == Decimal("45.50")
    assert txs[0].tx_type == TransactionType.EXPENSE
    assert txs[0].target_account == "Checking Account"

    # Row 2: Income
    assert txs[1].date == date(2026, 9, 16)
    assert txs[1].time == "09:15:00"
    assert txs[1].category == "Income"
    assert txs[1].amount == Decimal("1500.00")
    assert txs[1].tx_type == TransactionType.INCOME

    # Row 3: Transfer with Source -> Target
    assert txs[2].date == date(2026, 9, 17)
    assert txs[2].time == "18:20:00"
    assert txs[2].tx_type == TransactionType.TRANSFER
    assert txs[2].source_account == "Checking Account"
    assert txs[2].target_account == "Credit Card"
    assert txs[2].amount == Decimal("120.00")


def test_generic_csv_parses_spanish_headers_and_comma_decimals(tmp_path: Path):
    content = """Fecha;Concepto;Rubro;Monto;Tipo
15/09/2026 13:00;Restaurante Almuerzo;Restaurante;25,80;gasto
16/09/2026 10:00;Honorarios Profesionales;Otros;850,00;ingreso
"""
    file_path = tmp_path / "spanish.csv"
    file_path.write_text(content, encoding="utf-8")

    parser = GenericCsvParser()
    txs = parser.parse(file_path)
    assert len(txs) == 2

    assert txs[0].date == date(2026, 9, 15)
    assert txs[0].description == "Restaurante Almuerzo"
    assert txs[0].category == "Restaurante"
    assert txs[0].amount == Decimal("25.80")
    assert txs[0].tx_type == TransactionType.EXPENSE

    assert txs[1].date == date(2026, 9, 16)
    assert txs[1].amount == Decimal("850.00")
    assert txs[1].tx_type == TransactionType.INCOME
