"""Tests for Web Automator calendar, language, and time parsing utilities."""

from datetime import date
from unittest.mock import MagicMock

from daily_expenses_importer.core.web_automator import (
    _parse_calendar_header,
    _parse_time_12h,
    _select_account,
    _select_category,
)


class TestParseCalendarHeader:
    """Test multi-lingual and multi-format month header extraction for mat-calendar."""

    # Spanish
    def test_parses_spanish_short_and_full(self):
        assert _parse_calendar_header("AGO 2026") == (2026, 8)
        assert _parse_calendar_header("AGOSTO 2026") == (2026, 8)
        assert _parse_calendar_header("ENE 2026") == (2026, 1)
        assert _parse_calendar_header("ENERO 2026") == (2026, 1)
        assert _parse_calendar_header("DIC 2026") == (2026, 12)
        assert _parse_calendar_header("DICIEMBRE 2026") == (2026, 12)
        assert _parse_calendar_header("SETIEMBRE 2026") == (2026, 9)

    # English
    def test_parses_english_short_and_full(self):
        assert _parse_calendar_header("AUG 2026") == (2026, 8)
        assert _parse_calendar_header("AUGUST 2026") == (2026, 8)
        assert _parse_calendar_header("JAN 2026") == (2026, 1)
        assert _parse_calendar_header("JANUARY 2026") == (2026, 1)
        assert _parse_calendar_header("OCTOBER 2026") == (2026, 10)
        assert _parse_calendar_header("DECEMBER 2026") == (2026, 12)

    # Portuguese
    def test_parses_portuguese(self):
        assert _parse_calendar_header("FEV 2026") == (2026, 2)
        assert _parse_calendar_header("FEVEREIRO 2026") == (2026, 2)
        assert _parse_calendar_header("SETEMBRO 2026") == (2026, 9)
        assert _parse_calendar_header("OUTUBRO 2026") == (2026, 10)
        assert _parse_calendar_header("DEZEMBRO 2026") == (2026, 12)

    # French
    def test_parses_french(self):
        assert _parse_calendar_header("JANV 2026") == (2026, 1)
        assert _parse_calendar_header("FÉVRIER 2026") == (2026, 2)
        assert _parse_calendar_header("AOÛT 2026") == (2026, 8)
        assert _parse_calendar_header("DÉCEMBRE 2026") == (2026, 12)

    # German
    def test_parses_german(self):
        assert _parse_calendar_header("MÄRZ 2026") == (2026, 3)
        assert _parse_calendar_header("OKTOBER 2026") == (2026, 10)

    # Invalid / Edge cases
    def test_returns_none_on_empty_or_invalid(self):
        assert _parse_calendar_header("") is None
        assert _parse_calendar_header("UNKNOWN MONTH") is None


class TestParseTime12h:
    """Test 12-hour time conversion from various string formats."""

    def test_parses_morning_time(self):
        assert _parse_time_12h("08:35") == (8, 35, "AM")
        assert _parse_time_12h("08:35:12.450") == (8, 35, "AM")

    def test_parses_afternoon_and_evening_time(self):
        assert _parse_time_12h("14:20") == (2, 20, "PM")
        assert _parse_time_12h("18:14:47") == (6, 14, "PM")
        assert _parse_time_12h("23:59") == (11, 59, "PM")

    def test_parses_noon_and_midnight(self):
        assert _parse_time_12h("12:00") == (12, 0, "PM")
        assert _parse_time_12h("00:00") == (12, 0, "AM")
        assert _parse_time_12h("00:15") == (12, 15, "AM")

    def test_fallback_for_empty_time(self):
        h, m, mer = _parse_time_12h("")
        assert 1 <= h <= 12
        assert 0 <= m <= 59
        assert mer in ("AM", "PM")


class TestSelectAccount:
    """Test account selection in both new modal and legacy dropdown."""

    def test_select_account_new_modal(self):
        modal = MagicMock()
        page = MagicMock()
        legacy_locator = MagicMock()
        legacy_locator.count.return_value = 0

        acc_btn = MagicMock()
        acc_trigger = MagicMock()
        acc_trigger.or_.return_value.first = acc_btn
        modal.locator.side_effect = lambda sel, *args, **kwargs: (
            legacy_locator if "app-selector-account" in sel else acc_trigger
        )

        acc_modal = MagicMock()
        page.locator.return_value = acc_modal

        row_item = MagicMock()
        row_item.count.return_value = 1
        filtered_locator = MagicMock()
        filtered_locator.first = row_item
        acc_modal.locator.return_value.filter.return_value = filtered_locator
        acc_modal.is_visible.return_value = False

        _select_account(modal, page, "Binance")

        acc_btn.click.assert_called()
        acc_modal.wait_for.assert_called_with(state="visible", timeout=6000)
        row_item.click.assert_called()

    def test_select_account_legacy(self):
        modal = MagicMock()
        page = MagicMock()
        legacy_locator = MagicMock()
        legacy_locator.count.return_value = 1
        legacy_btn = MagicMock()
        legacy_locator.first = legacy_btn

        dropdown_item = MagicMock()
        dropdown_item.count.return_value = 1

        item_locator = MagicMock()
        item_locator.filter.return_value.first = dropdown_item

        def modal_locator_mock(sel, *args, **kwargs):
            if "app-selector-account button" in sel:
                return legacy_locator
            if "dropdown-menu" in sel:
                return item_locator
            return MagicMock()

        modal.locator.side_effect = modal_locator_mock

        _select_account(modal, page, "Binance")

        legacy_btn.click.assert_called()
        dropdown_item.click.assert_called()


class TestSelectCategory:
    """Test category selection in both new modal and legacy dropdown."""

    def test_select_category_new_modal(self):
        modal = MagicMock()
        page = MagicMock()
        legacy_locator = MagicMock()
        legacy_locator.count.return_value = 0

        cat_btn = MagicMock()
        cat_trigger = MagicMock()
        cat_trigger.or_.return_value.first = cat_btn
        modal.locator.side_effect = lambda sel, *args, **kwargs: (
            legacy_locator if "app-selector-category" in sel else cat_trigger
        )

        cat_modal = MagicMock()
        page.locator.return_value = cat_modal

        row_item = MagicMock()
        row_item.count.return_value = 1
        filtered_locator = MagicMock()
        filtered_locator.first = row_item
        cat_modal.locator.return_value.filter.return_value = filtered_locator
        cat_modal.is_visible.return_value = False

        _select_category(modal, page, "Comida")

        cat_btn.click.assert_called()
        cat_modal.wait_for.assert_called_with(state="visible", timeout=6000)
        row_item.click.assert_called()

    def test_select_category_legacy(self):
        modal = MagicMock()
        page = MagicMock()
        legacy_locator = MagicMock()
        legacy_locator.count.return_value = 1
        legacy_btn = MagicMock()
        legacy_locator.first = legacy_btn

        dropdown_item = MagicMock()
        dropdown_item.count.return_value = 1

        item_locator = MagicMock()
        item_locator.filter.return_value.first = dropdown_item

        def modal_locator_mock(sel, *args, **kwargs):
            if "app-selector-category button" in sel:
                return legacy_locator
            if "dropdown-menu" in sel:
                return item_locator
            return MagicMock()

        modal.locator.side_effect = modal_locator_mock

        _select_category(modal, page, "Comida")

        legacy_btn.click.assert_called()
        dropdown_item.click.assert_called()
