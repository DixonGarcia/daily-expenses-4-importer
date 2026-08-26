"""Tests for Classifier module."""

from daily_expenses_importer.core.db import Database
from daily_expenses_importer.core.classifier import classify


def test_classifier_finds_rule(temp_db: Database):
    temp_db.add_rule(pattern="Netflix", category="Servicios", description="Netflix Mensual")
    result = classify("COMPRA (RETAIL)NETFLIX.COM", temp_db)
    assert result is not None
    assert result.is_rule_match is True
    assert result.category == "Servicios"
    assert result.description == "Netflix Mensual"
