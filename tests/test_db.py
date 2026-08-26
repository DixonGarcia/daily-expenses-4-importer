"""Tests for Database module."""

from decimal import Decimal
from daily_expenses_importer.core.db import Database


def test_merchant_rules(temp_db: Database):
    temp_db.add_rule(pattern="Amazon", category="Compras", description="Amazon US")
    rule = temp_db.find_rule("COMPRA EN AMAZON PRIME")
    assert rule is not None
    assert rule.category == "Compras"
    assert rule.description == "Amazon US"


def test_processed_transactions_and_status(temp_db: Database):
    ref = "TEST-REF-001"
    assert not temp_db.is_processed(ref)

    temp_db.mark_processed(ref, Decimal("15.50"), "Test Purchase", "Comida", status="synced")
    assert temp_db.is_processed(ref)
    assert temp_db.get_transaction_status(ref) == "synced"

    # Mark as failed
    temp_db.mark_processed(ref, Decimal("15.50"), "Test Purchase", "Comida", status="failed", overwrite=True)
    assert not temp_db.is_processed(ref)  # failed is not considered successfully processed
    assert temp_db.get_transaction_status(ref) == "failed"
