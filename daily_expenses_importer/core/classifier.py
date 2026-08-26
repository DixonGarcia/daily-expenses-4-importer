"""Merchant classifier and rule matching."""

from dataclasses import dataclass
from daily_expenses_importer.core.db import Database, MerchantRule


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    description: str
    is_rule_match: bool


def classify(description: str, db: Database) -> ClassificationResult | None:
    rule = db.find_rule(description)
    if rule:
        return ClassificationResult(
            category=rule.category,
            description=rule.description,
            is_rule_match=True,
        )
    return None
