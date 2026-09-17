"""Tests for Web Automator calendar, language, and time parsing utilities."""

from datetime import date
from daily_expenses_importer.core.web_automator import (
    _parse_calendar_header,
    _parse_time_12h,
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
