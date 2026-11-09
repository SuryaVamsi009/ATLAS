"""Tests for atlas.universe module."""

from __future__ import annotations

import pytest
from urllib.error import URLError

from atlas.universe import (
    parse_constituents,
    fetch_universe,
    UniverseUnavailable,
)


# ---------------------------------------------------------------------------
# parse_constituents tests
# ---------------------------------------------------------------------------

def test_parse_constituents_basic():
    """Test basic parsing with Symbol column."""
    csv_text = """Symbol,Series
RELIANCE,EQ
TCS,EQ
INFY,EQ
"""
    result = parse_constituents(csv_text)
    assert result == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def test_parse_constituents_m_and_m():
    """Test M&M symbol parses intact."""
    csv_text = """Symbol,Series
M&M,EQ
BAJAJ-AUTO,EQ
"""
    result = parse_constituents(csv_text)
    assert "M&M.NS" in result
    assert "BAJAJ-AUTO.NS" in result


def test_parse_constituents_be_series_dropped():
    """Test BE series symbols are dropped."""
    csv_text = """Symbol,Series
RELIANCE,EQ
SOMEBE,BE
TCS,EQ
"""
    result = parse_constituents(csv_text)
    assert result == ["RELIANCE.NS", "TCS.NS"]


def test_parse_constituents_duplicates_removed():
    """Test duplicate symbols are removed, order preserved."""
    csv_text = """Symbol,Series
RELIANCE,EQ
TCS,EQ
RELIANCE,EQ
INFY,EQ
"""
    result = parse_constituents(csv_text)
    assert result == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def test_parse_constituents_no_series_column():
    """Test parsing works without Series column."""
    csv_text = """Symbol
RELIANCE
TCS
INFY
"""
    result = parse_constituents(csv_text)
    assert result == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def test_parse_constituents_case_insensitive_headers():
    """Test column headers are case-insensitive."""
    csv_text = """symbol,series
RELIANCE,EQ
TCS,EQ
"""
    result = parse_constituents(csv_text)
    assert result == ["RELIANCE.NS", "TCS.NS"]


def test_parse_constituents_html_error_rejected():
    """Test HTML/error page is rejected."""
    html = "<html><body>Error</body></html>"
    with pytest.raises(ValueError, match="HTML/error page"):
        parse_constituents(html)


def test_parse_constituents_empty_raises():
    """Test empty CSV raises ValueError."""
    with pytest.raises(ValueError, match="Empty CSV"):
        parse_constituents("")


def test_parse_constituents_missing_symbol_column():
    """Test missing Symbol column raises ValueError."""
    csv_text = """Name,Series
RELIANCE,EQ
"""
    with pytest.raises(ValueError, match="Missing 'Symbol' column"):
        parse_constituents(csv_text)


def test_parse_constituents_empty_result_raises():
    """Test empty result after parsing raises ValueError."""
    csv_text = """Symbol,Series
,EQ
"""
    with pytest.raises(ValueError, match="No valid symbols"):
        parse_constituents(csv_text)


# ---------------------------------------------------------------------------
# fetch_universe tests (with mocked fetch)
# ---------------------------------------------------------------------------

def test_fetch_universe_success(monkeypatch, tmp_path):
    """Test successful fetch writes cache and returns from_cache=False."""
    csv_text = """Symbol,Series
RELIANCE,EQ
TCS,EQ
"""

    def mock_fetch(url):
        assert "nifty200" in url
        return csv_text

    universe = fetch_universe(
        index="nifty200",
        cache_dir=str(tmp_path / "universe"),
        fetch=mock_fetch,
        now=date(2024, 1, 15),
    )

    assert universe.symbols == ("RELIANCE.NS", "TCS.NS")
    assert universe.index == "nifty200"
    assert universe.as_of == date(2024, 1, 15)
    assert universe.from_cache is False
    assert "nsearchives.nseindia.com" in universe.source

    # Check cache files exist
    cache_files = list((tmp_path / "universe").glob("*"))
    assert len(cache_files) == 2  # .csv and .json


def test_fetch_universe_failure_with_cache(monkeypatch, tmp_path):
    """Test fetch failure returns cached data with from_cache=True."""
    cache_dir = tmp_path / "universe"
    cache_dir.mkdir(parents=True)

    # Pre-populate cache
    csv_text = """Symbol,Series
RELIANCE,EQ
TCS,EQ
"""
    (cache_dir / "nifty200_2024-01-10.csv").write_text(csv_text)
    (cache_dir / "nifty200_2024-01-10.json").write_text(
        '{"source": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv", "fetched_at": "2024-01-10T10:00:00", "index": "nifty200", "as_of": "2024-01-10"}'
    )

    def mock_fetch(url):
        raise URLError("Network error")

    universe = fetch_universe(
        index="nifty200",
        cache_dir=str(cache_dir),
        fetch=mock_fetch,
        now=date(2024, 1, 15),
    )

    assert universe.symbols == ("RELIANCE.NS", "TCS.NS")
    assert universe.from_cache is True
    assert universe.as_of == date(2024, 1, 10)


def test_fetch_universe_failure_no_cache_raises(monkeypatch, tmp_path):
    """Test fetch failure with no cache raises UniverseUnavailable."""
    def mock_fetch(url):
        raise URLError("Network error")

    with pytest.raises(UniverseUnavailable):
        fetch_universe(
            index="nifty200",
            cache_dir=str(tmp_path / "universe"),
            fetch=mock_fetch,
            now=date(2024, 1, 15),
        )


def test_fetch_universe_bad_download_preserves_good_cache(monkeypatch, tmp_path):
    """Test bad download (invalid CSV) leaves good cache untouched."""
    cache_dir = tmp_path / "universe"
    cache_dir.mkdir(parents=True)

    # Good cache
    good_csv = """Symbol,Series
RELIANCE,EQ
TCS,EQ
"""
    (cache_dir / "nifty200_2024-01-10.csv").write_text(good_csv)
    (cache_dir / "nifty200_2024-01-10.json").write_text(
        '{"source": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv", "fetched_at": "2024-01-10T10:00:00", "index": "nifty200", "as_of": "2024-01-10"}'
    )

    def mock_fetch(url):
        return "<html>Error</html>"  # Invalid CSV

    universe = fetch_universe(
        index="nifty200",
        cache_dir=str(cache_dir),
        fetch=mock_fetch,
        now=date(2024, 1, 15),
    )

    # Should return cached data
    assert universe.symbols == ("RELIANCE.NS", "TCS.NS")
    assert universe.from_cache is True
    assert universe.as_of == date(2024, 1, 10)

    # Cache should be unchanged
    assert (cache_dir / "nifty200_2024-01-10.csv").read_text() == good_csv


def test_fetch_universe_unsupported_index_raises():
    """Test unsupported index raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported index"):
        fetch_universe(index="nifty100", fetch=lambda u: "")


# Need to import date for tests
from datetime import date