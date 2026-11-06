"""Tests for atlas.quant.data module."""


import pytest

from atlas.quant.data import DataLoader, ParquetCollector, YFinanceLoader, load_bars


class TestYFinanceLoader:
    def test_yfinance_loader_creation(self):
        loader = YFinanceLoader()
        assert loader.cache_dir is None

    def test_yfinance_loader_with_cache(self, tmp_path):
        loader = YFinanceLoader(cache_dir=str(tmp_path))
        assert loader.cache_dir == tmp_path

    def test_yfinance_loader_get_available_symbols(self):
        loader = YFinanceLoader()
        symbols = loader.get_available_symbols()
        assert isinstance(symbols, list)
        assert len(symbols) > 0
        assert "^NSEI" in symbols
        assert "RELIANCE.NS" in symbols

    def test_yfinance_loader_timeframe_map(self):
        loader = YFinanceLoader()
        assert "1m" in loader.TIMEFRAME_MAP
        assert "5m" in loader.TIMEFRAME_MAP
        assert "15m" in loader.TIMEFRAME_MAP
        assert "1h" in loader.TIMEFRAME_MAP
        assert "1d" in loader.TIMEFRAME_MAP

    def test_yfinance_loader_max_lookback(self):
        loader = YFinanceLoader()
        assert loader.MAX_LOOKBACK_DAYS["1m"] == 7
        assert loader.MAX_LOOKBACK_DAYS["1d"] == 7300


class TestParquetCollector:
    def test_parquet_collector_creation(self, tmp_path):
        collector = ParquetCollector(output_dir=str(tmp_path))
        assert collector.output_dir == tmp_path
        assert collector.timeframe == "1m"
        assert len(collector.symbols) > 0

    def test_parquet_collector_custom_symbols(self, tmp_path):
        collector = ParquetCollector(
            output_dir=str(tmp_path),
            symbols=["RELIANCE.NS", "TCS.NS"],
            timeframe="5m",
        )
        assert collector.symbols == ["RELIANCE.NS", "TCS.NS"]
        assert collector.timeframe == "5m"


class TestLoadBars:
    def test_load_bars_convenience_function(self):
        # This tests the convenience function which uses YFinanceLoader
        # We can't easily test without network, so just verify it exists
        assert callable(load_bars)


class TestDataLoaderInterface:
    def test_data_loader_is_abstract(self):
        with pytest.raises(TypeError):
            DataLoader()
