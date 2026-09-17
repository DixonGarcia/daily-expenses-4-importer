"""Parser registry and auto-detection mechanism."""

from pathlib import Path
from daily_expenses_importer.parsers.base import BaseParser, NormalizedTransaction, TransactionType
from daily_expenses_importer.parsers.generic_csv import GenericCsvParser
from daily_expenses_importer.parsers.generic_excel import GenericExcelParser

_AVAILABLE_PARSERS: list[BaseParser] = [
    GenericExcelParser(),
    GenericCsvParser(),
]


def get_parser(name: str) -> BaseParser | None:
    """Find a parser by its identifier name."""
    for p in _AVAILABLE_PARSERS:
        if p.name == name:
            return p
    return None


def detect_parser(file_path: Path) -> BaseParser:
    """Auto-detect the most suitable parser for the input file.

    Raises:
        ValueError: If no registered parser supports the file.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sample_bytes = b""
    try:
        with open(file_path, "rb") as f:
            sample_bytes = f.read(8192)
    except Exception:
        pass

    for p in _AVAILABLE_PARSERS:
        if p.supports(file_path, sample_bytes):
            return p

    raise ValueError(f"No compatible parser found for file: {file_path.name}")
