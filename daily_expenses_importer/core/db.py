"""SQLite database for merchant rules and processed transactions."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class MerchantRule:
    id: int
    pattern: str
    category: str
    description: str
    is_regex: bool = False


class Database:
    """Manages SQLite storage for merchant rules and transaction state."""

    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS merchant_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    is_regex INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS processed_transactions (
                    reference TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL,
                    amount_usd REAL NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'synced'
                )
            """)

    def find_rule(self, description: str) -> MerchantRule | None:
        """Find matching rule for a given merchant description."""
        cur = self._connection.execute("SELECT id, pattern, category, description, is_regex FROM merchant_rules")
        desc_lower = description.lower()
        for row in cur.fetchall():
            pattern = row["pattern"].lower()
            if pattern in desc_lower:
                return MerchantRule(
                    id=row["id"],
                    pattern=row["pattern"],
                    category=row["category"],
                    description=row["description"],
                    is_regex=bool(row["is_regex"]),
                )
        return None

    def add_rule(self, pattern: str, category: str, description: str, is_regex: bool = False) -> None:
        """Add or update a merchant rule."""
        with self._connection:
            self._connection.execute("""
                INSERT INTO merchant_rules (pattern, category, description, is_regex)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pattern) DO UPDATE SET
                    category = excluded.category,
                    description = excluded.description,
                    is_regex = excluded.is_regex
            """, (pattern, category, description, int(is_regex)))

    def is_processed(self, reference: str) -> bool:
        """Return True if transaction was successfully synced or skipped."""
        cur = self._connection.execute("SELECT status FROM processed_transactions WHERE reference = ?", (reference,))
        row = cur.fetchone()
        if not row:
            return False
        return row["status"] in {"synced", "skipped"}

    def get_transaction_status(self, reference: str) -> str | None:
        cur = self._connection.execute("SELECT status FROM processed_transactions WHERE reference = ?", (reference,))
        row = cur.fetchone()
        return row["status"] if row else None

    def mark_processed(
        self,
        reference: str,
        amount_usd: Decimal | float | int,
        description: str,
        category: str = "",
        status: str = "synced",
        overwrite: bool = False,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        amt_float = float(amount_usd)
        with self._connection:
            if overwrite:
                self._connection.execute("""
                    INSERT INTO processed_transactions (reference, processed_at, amount_usd, description, category, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(reference) DO UPDATE SET
                        processed_at = excluded.processed_at,
                        amount_usd = excluded.amount_usd,
                        description = excluded.description,
                        category = excluded.category,
                        status = excluded.status
                """, (reference, now_iso, amt_float, description, category, status))
            else:
                self._connection.execute("""
                    INSERT OR IGNORE INTO processed_transactions (reference, processed_at, amount_usd, description, category, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (reference, now_iso, amt_float, description, category, status))

    def list_processed(self, status: str | None = None) -> list[dict]:
        if status:
            cur = self._connection.execute("SELECT * FROM processed_transactions WHERE status = ?", (status,))
        else:
            cur = self._connection.execute("SELECT * FROM processed_transactions")
        return [dict(r) for r in cur.fetchall()]
