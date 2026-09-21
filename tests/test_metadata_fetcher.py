from pathlib import Path
from daily_expenses_importer.core.metadata_fetcher import load_cached_metadata, save_cached_metadata


def test_save_and_load_cached_metadata(tmp_path: Path):
    cache_file = tmp_path / "subdir" / "metadata.json"
    data = {
        "accounts": ["Account 1", "Account 2"],
        "expense_categories": ["Food", "Transport"],
        "income_categories": ["Salary", "Investments"],
        "fetched_at": "2026-09-21T18:00:00Z"
    }

    # Before saving, should return None
    assert load_cached_metadata(cache_file) is None

    # Save
    save_cached_metadata(data, cache_path=cache_file)
    assert cache_file.exists()

    # Load
    loaded = load_cached_metadata(cache_file)
    assert loaded == data
    assert loaded["accounts"] == ["Account 1", "Account 2"]
    assert loaded["expense_categories"] == ["Food", "Transport"]
    assert loaded["income_categories"] == ["Salary", "Investments"]


def test_load_cached_metadata_corrupt_file(tmp_path: Path):
    cache_file = tmp_path / "metadata.json"
    cache_file.write_text("{ corrupt json ...", encoding="utf-8")

    assert load_cached_metadata(cache_file) is None
