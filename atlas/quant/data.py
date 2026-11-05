"""Data loader interface and implementations for ATLAS quant layer.

Provides a swappable data source interface with yfinance intraday as the
initial implementation, plus a 1-minute collector that writes partitioned
parquet for Nifty 50 with gap/duplicate/timezone checks.
"""

from __future__ import annotations

import abc
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# Suppress yfinance warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")


# ---------------------------------------------------------------------------
# Data Loader Interface
# ---------------------------------------------------------------------------

class DataLoader(abc.ABC):
    """Abstract base class for data loaders.

    All data loaders must implement the load method to fetch OHLCV bars
    for a given symbol, timeframe, and date range.
    """

    @abc.abstractmethod
    def load(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[List[float]]:
        """Load historical OHLCV bars.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE.NS", "NIFTY 50")
            timeframe: Bar timeframe (e.g., "1m", "5m", "15m", "1h", "1d")
            start: Start datetime (inclusive)
            end: End datetime (exclusive)

        Returns:
            List of bars in format [timestamp_ms, open, high, low, close, volume]
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols from this data source."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# YFinance Loader Implementation
# ---------------------------------------------------------------------------

class YFinanceLoader(DataLoader):
    """YFinance data loader for intraday and daily data.

    Supports timeframes: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo
    Note: yfinance intraday data is limited to last 7 days for 1m, 60 days for 5m/15m/30m/60m
    """

    # Map our timeframe strings to yfinance intervals
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "60m",
        "1d": "1d",
        "5d": "5d",
        "1wk": "1wk",
        "1mo": "1mo",
    }

    # Maximum lookback days per timeframe (yfinance limits)
    MAX_LOOKBACK_DAYS = {
        "1m": 7,
        "2m": 60,
        "5m": 60,
        "15m": 60,
        "30m": 60,
        "60m": 730,  # ~2 years
        "1h": 730,
        "1d": 7300,  # ~20 years
        "5d": 7300,
        "1wk": 7300,
        "1mo": 7300,
    }

    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize the YFinance loader.

        Args:
            cache_dir: Optional directory to cache downloaded data as parquet
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[List[float]]:
        """Load historical OHLCV bars from yfinance.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE.NS", "^NSEI" for Nifty 50)
            timeframe: Bar timeframe (e.g., "1m", "5m", "15m", "1h", "1d")
            start: Start datetime (inclusive)
            end: End datetime (exclusive)

        Returns:
            List of bars in format [timestamp_ms, open, high, low, close, volume]
        """
        # Check cache first
        if self.cache_dir:
            cached = self._load_from_cache(symbol, timeframe, start, end)
            if cached is not None:
                return cached

        # Validate timeframe
        if timeframe not in self.TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(self.TIMEFRAME_MAP.keys())}")

        yf_interval = self.TIMEFRAME_MAP[timeframe]

        # Check lookback limit
        max_days = self.MAX_LOOKBACK_DAYS.get(timeframe, 730)
        days_requested = (end - start).days
        if days_requested > max_days:
            # Adjust start to respect limit
            start = end - timedelta(days=max_days)
            print(f"Warning: Adjusted start date to {start} (max {max_days} days for {timeframe})")

        # Fetch from yfinance
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(
                start=start,
                end=end,
                interval=yf_interval,
                auto_adjust=False,  # Keep raw prices
                actions=False,
            )

            if hist.empty:
                return []

            # Convert to our bar format: [timestamp_ms, open, high, low, close, volume]
            bars = []
            for idx, row in hist.iterrows():
                # yfinance returns timezone-aware timestamps; convert to UTC ms
                if idx.tzinfo is not None:
                    ts_ms = int(idx.timestamp() * 1000)
                else:
                    # Assume UTC if naive
                    ts_ms = int(idx.replace(tzinfo=datetime.utcnow().astimezone().tzinfo).timestamp() * 1000)

                bars.append([
                    ts_ms,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]),
                ])

            # Cache if enabled
            if self.cache_dir and bars:
                self._save_to_cache(symbol, timeframe, bars)

            return bars

        except Exception as e:
            print(f"Error fetching data for {symbol} {timeframe}: {e}")
            return []

    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols (Nifty 50 components + index)."""
        # Nifty 50 symbols with .NS suffix for yfinance
        nifty50 = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
            "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
            "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
            "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS", "NESTLEIND.NS", "POWERGRID.NS",
            "NTPC.NS", "TECHM.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", "HCLTECH.NS",
            "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "GRASIM.NS", "JSWSTEEL.NS",
            "ONGC.NS", "BPCL.NS", "CIPLA.NS", "DRREDDY.NS", "EICHERMOT.NS",
            "HEROMOTOCO.NS", "INDUSINDBK.NS", "BAJAJFINSV.NS", "TATACONSUM.NS",
            "DIVISLAB.NS", "APOLLOHOSP.NS", "BRITANNIA.NS", "SHRIRAMFIN.NS",
            "SBILIFE.NS", "HDFCLIFE.NS", "M&M.NS", "TATASTEEL.NS", "HINDALCO.NS",
        ]
        # Add Nifty 50 index
        return ["^NSEI"] + nifty50

    def _get_cache_path(self, symbol: str, timeframe: str) -> Path:
        """Get cache file path for symbol/timeframe."""
        safe_symbol = symbol.replace(".", "_").replace("^", "").replace("/", "_")
        return self.cache_dir / f"{safe_symbol}_{timeframe}.parquet"

    def _load_from_cache(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Optional[List[List[float]]]:
        """Load bars from cache if available and covers the requested range."""
        if not self.cache_dir:
            return None

        cache_path = self._get_cache_path(symbol, timeframe)
        if not cache_path.exists():
            return None

        try:
            df = pd.read_parquet(cache_path)
            if df.empty:
                return None

            # Filter by date range
            start_ms = int(start.timestamp() * 1000)
            end_ms = int(end.timestamp() * 1000)

            mask = (df["timestamp"] >= start_ms) & (df["timestamp"] < end_ms)
            filtered = df[mask]

            if filtered.empty:
                return None

            return filtered[["timestamp", "open", "high", "low", "close", "volume"]].values.tolist()

        except Exception:
            return None

    def _save_to_cache(self, symbol: str, timeframe: str, bars: List[List[float]]) -> None:
        """Save bars to cache as parquet."""
        if not self.cache_dir or not bars:
            return

        cache_path = self._get_cache_path(symbol, timeframe)

        try:
            df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df.to_parquet(cache_path, index=False)
        except Exception as e:
            print(f"Warning: Failed to cache data for {symbol} {timeframe}: {e}")


# ---------------------------------------------------------------------------
# Parquet Collector for Nifty 50 1-minute data
# ---------------------------------------------------------------------------

class ParquetCollector:
    """Collects 1-minute bars for Nifty 50 and writes partitioned parquet files.

    Features:
    - Incremental collection (appends new bars)
    - Gap detection (missing minutes)
    - Duplicate detection
    - Timezone validation (IST)
    - Partitioned by date for efficient querying
    """

    def __init__(
        self,
        output_dir: str,
        symbols: Optional[List[str]] = None,
        timeframe: str = "1m",
    ):
        """Initialize the collector.

        Args:
            output_dir: Directory to write partitioned parquet files
            symbols: List of symbols to collect (default: Nifty 50 + index)
            timeframe: Timeframe to collect (default: "1m")
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.symbols = symbols or YFinanceLoader().get_available_symbols()
        self.timeframe = timeframe
        self.loader = YFinanceLoader()

        # Track collection stats
        self.stats = {
            "total_bars": 0,
            "gaps_detected": 0,
            "duplicates_removed": 0,
            "timezone_errors": 0,
        }

    def collect(
        self,
        start: datetime,
        end: datetime,
        incremental: bool = True,
    ) -> Dict[str, Any]:
        """Collect 1-minute bars for all symbols and write partitioned parquet.

        Args:
            start: Start datetime (inclusive)
            end: End datetime (exclusive)
            incremental: If True, append to existing files; if False, overwrite

        Returns:
            Dict with collection statistics
        """
        all_stats = {
            "symbols_processed": 0,
            "total_bars_written": 0,
            "gaps_detected": 0,
            "duplicates_removed": 0,
            "timezone_errors": 0,
            "errors": [],
        }

        for symbol in self.symbols:
            try:
                bars = self.loader.load(symbol, self.timeframe, start, end)
                if not bars:
                    continue

                # Validate and clean bars
                cleaned_bars, symbol_stats = self._validate_and_clean_bars(bars, symbol)

                if not cleaned_bars:
                    continue

                # Write partitioned parquet
                bars_written = self._write_partitioned_parquet(symbol, cleaned_bars, incremental)

                all_stats["symbols_processed"] += 1
                all_stats["total_bars_written"] += bars_written
                all_stats["gaps_detected"] += symbol_stats["gaps"]
                all_stats["duplicates_removed"] += symbol_stats["duplicates"]
                all_stats["timezone_errors"] += symbol_stats["timezone_errors"]

            except Exception as e:
                all_stats["errors"].append(f"{symbol}: {str(e)}")

        return all_stats

    def _validate_and_clean_bars(
        self,
        bars: List[List[float]],
        symbol: str,
    ) -> Tuple[List[List[float]], Dict[str, int]]:
        """Validate bars for gaps, duplicates, and timezone issues.

        Args:
            bars: Raw bars from loader
            symbol: Symbol name for logging

        Returns:
            Tuple of (cleaned_bars, stats_dict)
        """
        if not bars:
            return [], {"gaps": 0, "duplicates": 0, "timezone_errors": 0}

        df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Convert timestamp to datetime for validation
        df["dt"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["dt_ist"] = df["dt"].dt.tz_convert("Asia/Kolkata")

        stats = {"gaps": 0, "duplicates": 0, "timezone_errors": 0}

        # Check for timezone issues (should be IST market hours 09:15-15:30)
        market_open = df["dt_ist"].dt.time >= pd.Timestamp("09:15").time()
        market_close = df["dt_ist"].dt.time <= pd.Timestamp("15:30").time()
        in_market_hours = market_open & market_close

        # Count bars outside market hours (excluding pre/post market if any)
        outside_hours = (~in_market_hours).sum()
        if outside_hours > 0:
            stats["timezone_errors"] = int(outside_hours)
            # Filter to market hours only
            df = df[in_market_hours].copy()

        # Sort by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Detect duplicates (same timestamp)
        dup_mask = df.duplicated(subset=["timestamp"], keep="first")
        if dup_mask.any():
            stats["duplicates"] = int(dup_mask.sum())
            df = df[~dup_mask].reset_index(drop=True)

        # Detect gaps (missing minutes during market hours)
        if len(df) > 1:
            # Expected 1-minute frequency
            expected_diff = pd.Timedelta(minutes=1)
            actual_diffs = df["dt_ist"].diff().dropna()
            gap_mask = actual_diffs > expected_diff * 1.5  # Allow 1.5x for minor delays
            stats["gaps"] = int(gap_mask.sum())

        # Return cleaned bars
        cleaned = df[["timestamp", "open", "high", "low", "close", "volume"]].values.tolist()
        return cleaned, stats

    def _write_partitioned_parquet(
        self,
        symbol: str,
        bars: List[List[float]],
        incremental: bool,
    ) -> int:
        """Write bars to partitioned parquet files by date.

        Partition structure: output_dir/symbol/date=YYYY-MM-DD/data.parquet

        Args:
            symbol: Symbol name
            bars: Cleaned bars
            incremental: Whether to append to existing partitions

        Returns:
            Number of bars written
        """
        if not bars:
            return 0

        df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["dt"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["dt_ist"] = df["dt"].dt.tz_convert("Asia/Kolkata")
        df["date"] = df["dt_ist"].dt.date.astype(str)

        total_written = 0

        # Group by date and write each partition
        for date_str, group in df.groupby("date"):
            symbol_dir = self.output_dir / symbol.replace(".", "_").replace("^", "")
            partition_dir = symbol_dir / f"date={date_str}"
            partition_dir.mkdir(parents=True, exist_ok=True)

            partition_file = partition_dir / "data.parquet"

            # Prepare data for writing (drop helper columns)
            write_df = group[["timestamp", "open", "high", "low", "close", "volume"]].copy()

            if incremental and partition_file.exists():
                # Read existing and append
                try:
                    existing = pd.read_parquet(partition_file)
                    # Combine and deduplicate
                    combined = pd.concat([existing, write_df], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
                    combined = combined.sort_values("timestamp").reset_index(drop=True)
                    combined.to_parquet(partition_file, index=False)
                    total_written += len(combined) - len(existing)
                except Exception:
                    # If read fails, overwrite
                    write_df.to_parquet(partition_file, index=False)
                    total_written += len(write_df)
            else:
                write_df.to_parquet(partition_file, index=False)
                total_written += len(write_df)

        return total_written

    def read_partition(
        self,
        symbol: str,
        date: str,
    ) -> List[List[float]]:
        """Read bars for a specific symbol and date from partitioned parquet.

        Args:
            symbol: Symbol name
            date: Date string in YYYY-MM-DD format

        Returns:
            List of bars for that date
        """
        symbol_dir = self.output_dir / symbol.replace(".", "_").replace("^", "")
        partition_file = symbol_dir / f"date={date}" / "data.parquet"

        if not partition_file.exists():
            return []

        try:
            df = pd.read_parquet(partition_file)
            return df[["timestamp", "open", "high", "low", "close", "volume"]].values.tolist()
        except Exception:
            return []

    def read_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> List[List[float]]:
        """Read bars for a symbol across a date range.

        Args:
            symbol: Symbol name
            start: Start datetime (inclusive)
            end: End datetime (exclusive)

        Returns:
            List of bars in the range
        """
        all_bars = []
        current_date = start.date()
        end_date = end.date()

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            bars = self.read_partition(symbol, date_str)
            if bars:
                # Filter by exact time range
                start_ms = int(start.timestamp() * 1000)
                end_ms = int(end.timestamp() * 1000)
                filtered = [b for b in bars if start_ms <= b[0] < end_ms]
                all_bars.extend(filtered)
            current_date += timedelta(days=1)

        return all_bars


# ---------------------------------------------------------------------------
# Convenience function for quick data loading
# ---------------------------------------------------------------------------

def load_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    cache_dir: Optional[str] = None,
) -> List[List[float]]:
    """Convenience function to load bars using YFinanceLoader.

    Args:
        symbol: Trading symbol
        timeframe: Bar timeframe
        start: Start datetime
        end: End datetime
        cache_dir: Optional cache directory

    Returns:
        List of bars
    """
    loader = YFinanceLoader(cache_dir=cache_dir)
    return loader.load(symbol, timeframe, start, end)


if __name__ == "__main__":
    # Quick test
    from datetime import datetime, timedelta

    loader = YFinanceLoader()
    end = datetime.now()
    start = end - timedelta(days=5)

    # Test with Nifty 50 index
    bars = loader.load("^NSEI", "1d", start, end)
    print(f"Loaded {len(bars)} daily bars for Nifty 50")
    if bars:
        print(f"First bar: {bars[0]}")
        print(f"Last bar: {bars[-1]}")

    # Test with a stock
    bars = loader.load("RELIANCE.NS", "1h", start, end)
    print(f"\nLoaded {len(bars)} hourly bars for RELIANCE")
    if bars:
        print(f"First bar: {bars[0]}")
        print(f"Last bar: {bars[-1]}")