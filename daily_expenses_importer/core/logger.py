"""Structured execution logger writing to tmp/importer.log."""

import logging
from datetime import datetime
from pathlib import Path

_LOG_PATH = Path("tmp/importer.log")
_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _logger = logging.getLogger("daily_expenses_importer")
    _logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)
    return _logger


def log_session_start(input_file: Path, dry_run: bool = False) -> None:
    lg = get_logger()
    lg.info("=" * 60)
    lg.info(f"IMPORT SESSION STARTED: {input_file.name} (Dry Run: {dry_run})")
    lg.info("=" * 60)


def log_tx_loaded(ref: str, amount: str, description: str, category: str, account: str) -> None:
    get_logger().info(f"SYNCED -> Ref: {ref} | ${amount} | [{category}] {description} | Account: {account}")


def log_tx_failed(ref: str, description: str, error: str) -> None:
    get_logger().error(f"FAILED -> Ref: {ref} | {description} | Error: {error}")


def log_session_end(total: int, synced: int, failed: int, skipped: int) -> None:
    lg = get_logger()
    lg.info(f"SESSION FINISHED: Total: {total} | Synced: {synced} | Failed: {failed} | Skipped: {skipped}")
    lg.info("=" * 60)
