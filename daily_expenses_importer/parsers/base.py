"""Base data structures and abstract interface for all bank statement parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path


class TransactionType(str, Enum):
    """Normalized transaction types recognized by the importer."""
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    REFUND = "refund"


@dataclass(frozen=True)
class NormalizedTransaction:
    """Normalized financial transaction independent of bank source."""
    reference: str
    date: date
    time: str
    amount: Decimal
    currency: str
    description: str
    raw_description: str
    tx_type: TransactionType = TransactionType.EXPENSE
    category: str | None = None
    source_account: str | None = None
    target_account: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base class for all file parsers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable identifier for this parser."""
        ...

    @abstractmethod
    def supports(self, file_path: Path, sample_bytes: bytes) -> bool:
        """Return True if this parser can handle the given file."""
        ...

    @abstractmethod
    def parse(self, file_path: Path) -> list[NormalizedTransaction]:
        """Parse the input file and return a list of normalized transactions."""
        ...
