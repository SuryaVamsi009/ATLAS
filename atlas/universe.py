"""Universe module for ATLAS - fetches and caches NSE index constituents.

This module provides functionality to fetch the Nifty 200 / Nifty 500
constituents from NSE's published CSV files, parse them, and cache locally.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UniverseUnavailable(Exception):
    """Raised when universe cannot be fetched and no cache exists."""
    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Universe:
    """Frozen dataclass representing a cached universe."""
    symbols: tuple[str, ...]
    index: str
    as_of: date
    source: str
    from_cache: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# UNVERIFIED: confirm these endpoints still serve CSVs on nseindia.com before relying on them.
NSE_BASE_URL = "https://nsearchives.nseindia.com/content/indices"
INDEX_FILES = {
    "nifty200": "ind_nifty200list.csv",
    "nifty500": "ind_nifty500list.csv",
}
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; ATLAS/1.0; +https://github.com/SuryaVamsi009/ATLAS)"


# ---------------------------------------------------------------------------
# Pure parsing function
# ---------------------------------------------------------------------------

def parse_constituents(text: str) -> list[str]:
    """Parse NSE constituents CSV text and return Yahoo tickers.

    Args:
        text: CSV text with a 'Symbol' column (case-insensitive).
              Optional 'Series' column - if present, only 'EQ' series kept.

    Returns:
        List of Yahoo tickers (e.g., 'RELIANCE.NS'), uppercase, trimmed,
        deduplicated, preserving order.

    Raises:
        ValueError: If 'Symbol' column is missing or result is empty.
    """
    if not text or not text.strip():
        raise ValueError("Empty CSV text")

    # Check if it's HTML/error page
    text_stripped = text.strip()
    if text_stripped.startswith("<") or text_stripped.startswith("<?xml"):
        raise ValueError("Received HTML/error page instead of CSV")

    # Parse CSV
    reader = csv.DictReader(text_stripped.splitlines())
    if not reader.fieldnames:
        raise ValueError("No columns found in CSV")

    # Find Symbol column (case-insensitive)
    symbol_col = None
    series_col = None
    for col in reader.fieldnames:
        if col.lower() == "symbol":
            symbol_col = col
        elif col.lower() == "series":
            series_col = col

    if symbol_col is None:
        raise ValueError("Missing 'Symbol' column in CSV")

    symbols = []
    seen = set()

    for row in reader:
        symbol = row.get(symbol_col, "").strip().upper()
        if not symbol:
            continue

        # Filter by Series if column exists
        if series_col:
            series = row.get(series_col, "").strip().upper()
            if series != "EQ":
                continue

        # Convert to Yahoo ticker format
        yahoo_ticker = f"{symbol}.NS"

        if yahoo_ticker not in seen:
            seen.add(yahoo_ticker)
            symbols.append(yahoo_ticker)

    if not symbols:
        raise ValueError("No valid symbols found after parsing")

    return symbols


# ---------------------------------------------------------------------------
# HTTP fetch function
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = 30) -> str:
    """Fetch URL with browser-like headers.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Response text.

    Raises:
        URLError: On network error.
        HTTPError: On HTTP error status.
    """
    req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def _cache_paths(cache_dir: str, index: str, as_of: date) -> tuple[Path, Path]:
    """Get cache file paths for a given index and date."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    csv_file = cache_path / f"{index}_{as_of.isoformat()}.csv"
    meta_file = cache_path / f"{index}_{as_of.isoformat()}.json"
    return csv_file, meta_file


def _find_latest_cache(cache_dir: str, index: str) -> Optional[tuple[Path, Path, date]]:
    """Find the most recent cache files for an index."""
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return None

    csv_files = list(cache_path.glob(f"{index}_*.csv"))
    if not csv_files:
        return None

    # Sort by date in filename (newest first)
    csv_files.sort(reverse=True)
    latest_csv = csv_files[0]

    # Extract date from filename
    try:
        date_str = latest_csv.stem.replace(f"{index}_", "")
        as_of = date.fromisoformat(date_str)
    except ValueError:
        return None

    meta_file = latest_csv.with_suffix(".json")
    if not meta_file.exists():
        return None

    return latest_csv, meta_file, as_of


def _write_cache(cache_dir: str, index: str, as_of: date, csv_text: str, source: str) -> None:
    """Write cache files atomically."""
    csv_file, meta_file = _cache_paths(cache_dir, index, as_of)

    # Write CSV first
    csv_file.write_text(csv_text, encoding="utf-8")

    # Write metadata
    meta = {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "index": index,
        "as_of": as_of.isoformat(),
    }
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _read_cache(cache_dir: str, index: str, as_of: date) -> tuple[str, dict]:
    """Read cache files."""
    csv_file, meta_file = _cache_paths(cache_dir, index, as_of)
    csv_text = csv_file.read_text(encoding="utf-8")
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    return csv_text, meta


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_universe(
    index: str = "nifty200",
    cache_dir: str = "data/universe",
    fetch: Callable[[str], str] = http_get,
    now: Optional[date] = None,
) -> Universe:
    """Fetch and cache NSE index constituents.

    Args:
        index: Index name ('nifty200' or 'nifty500').
        cache_dir: Directory for cache files.
        fetch: HTTP fetch function (injected for testing).
        now: Current date (injected for testing). Defaults to today.

    Returns:
        Universe dataclass with symbols, index, as_of, source, from_cache.

    Raises:
        ValueError: If index is not supported.
        UniverseUnavailable: If fetch fails and no cache exists.
    """
    if index not in INDEX_FILES:
        raise ValueError(f"Unsupported index: {index}. Supported: {list(INDEX_FILES.keys())}")

    if now is None:
        now = date.today()

    filename = INDEX_FILES[index]
    url = f"{NSE_BASE_URL}/{filename}"

    try:
        # Attempt to fetch
        csv_text = fetch(url)

        # Parse first to validate
        symbols = parse_constituents(csv_text)

        # Write cache on success
        _write_cache(cache_dir, index, now, csv_text, url)

        return Universe(
            symbols=tuple(symbols),
            index=index,
            as_of=now,
            source=url,
            from_cache=False,
        )

    except (URLError, HTTPError, ValueError) as e:
        # Fetch failed - try cache
        latest = _find_latest_cache(cache_dir, index)
        if latest is None:
            raise UniverseUnavailable(
                f"Failed to fetch {index} from {url} and no cache available: {e}"
            ) from e

        csv_file, meta_file, as_of = latest
        csv_text, meta = _read_cache(cache_dir, index, as_of)

        # Parse cached data
        symbols = parse_constituents(csv_text)

        import logging
        logging.warning(
            f"Using cached universe for {index} from {as_of} (source: {meta.get('source', 'unknown')})"
        )

        return Universe(
            symbols=tuple(symbols),
            index=index,
            as_of=as_of,
            source=meta.get("source", url),
            from_cache=True,
        )