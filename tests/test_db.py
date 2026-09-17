"""Tests for Database module."""

from decimal import Decimal
from daily_expenses_importer.core.db import Database


def test_merchant_rules(temp_db: Database):
    temp_db.add_rule(pattern="Amazon", category="Merchandise", description="Amazon US")
    rule = temp_db.find_rule("COMPRA EN AMAZON PRIME")
    assert rule is not None
    assert rule.category == "Merchandise"
    assert rule.description == "Amazon US"


def test_processed_transactions_and_status(temp_db: Database):
    ref = "TEST-REF-001"
    assert not temp_db.is_processed(ref)

    temp_db.mark_processed(ref, Decimal("15.50"), "Test Purchase", "Dining", status="synced")
    assert temp_db.is_processed(ref)
    assert temp_db.get_transaction_status(ref) == "synced"

    # Mark as failed
    temp_db.mark_processed(ref, Decimal("15.50"), "Test Purchase", "Dining", status="failed", overwrite=True)
    assert not temp_db.is_processed(ref)  # failed is not considered successfully processed
    assert temp_db.get_transaction_status(ref) == "failed"


def test_merchant_rules_with_regex(temp_db: Database):
    temp_db.add_rule(pattern=r"^UBER\s*\*(TRIP|EATS)", category="Transportation", description="Uber", is_regex=True)
    rule = temp_db.find_rule("UBER *TRIP 12345 SAN FRANCISCO")
    assert rule is not None
    assert rule.is_regex is True
    assert rule.category == "Transportation"
    assert rule.description == "Uber"

    # Does not match non-matching string
    assert temp_db.find_rule("LYFT TRIP") is None


def test_database_context_manager(tmp_path):
    db_file = tmp_path / "ctx_test.db"
    with Database(db_file) as db:
        db.add_rule("Test", "Category", "Desc")
        assert db.find_rule("Test") is not None
