"""Baseline strategies for backtest comparison.

- BuyAndHoldBaseline: buys at the first bar and holds to the end
- RandomEntryBaseline: enters at random bars; should lose roughly the cost drag
  (serves as a sanity check that the cost model is working)
"""

from __future__ import annotations

import random
from typing import Any

from atlas.quant.backtest.engine import BacktestConfig, BacktestEngine, BacktestResult


class BuyAndHoldBaseline:
    """Buy at the first tradeable bar and hold until the end."""

    def __init__(self, symbol: str = "^NSEI") -> None:
        self.symbol = symbol
        self._entered = False

    def make_strategy_fn(self):
        """Return a strategy callback for BacktestEngine.run()."""
        entered = {"done": False}

        def strategy_fn(history: list[list[float]], idx: int, context: dict[str, Any]) -> dict[str, Any] | None:
            if entered["done"]:
                return None
            # Buy with all available cash at the first tradeable bar
            bar = history[-1]
            price = bar[4]  # close
            cash = context["cash"]
            # Estimate qty we can afford (leave room for costs ~0.1%)
            qty = int(cash / (price * 1.001))
            if qty <= 0:
                return None
            entered["done"] = True
            return {"symbol": self.symbol, "side": "BUY", "qty": qty}

        return strategy_fn

    def run(self, bars: list[list[float]], config: BacktestConfig | None = None, warmup: int = 50) -> BacktestResult:
        cfg = config or BacktestConfig()
        engine = BacktestEngine(cfg)
        return engine.run(bars, self.make_strategy_fn(), warmup=warmup)


class RandomEntryBaseline:
    """Enters at random bars with random direction.

    Expected result: loses roughly the cost drag (each round trip costs ~0.1-0.2%).
    This serves as a sanity check that the cost model is calibrated correctly.
    """

    def __init__(
        self,
        symbol: str = "^NSEI",
        entry_probability: float = 0.05,
        hold_bars: int = 10,
        seed: int = 42,
    ) -> None:
        self.symbol = symbol
        self.entry_probability = entry_probability
        self.hold_bars = hold_bars
        self.rng = random.Random(seed)

    def make_strategy_fn(self):
        """Return a strategy callback for BacktestEngine.run()."""
        state = {"entry_bar": -1, "side": None}

        def strategy_fn(history: list[list[float]], idx: int, context: dict[str, Any]) -> dict[str, Any] | None:
            # If in a position, exit after hold_bars
            if state["entry_bar"] >= 0:
                if idx - state["entry_bar"] >= self.hold_bars:
                    side = "SELL" if state["side"] == "BUY" else "BUY"
                    state["entry_bar"] = -1
                    state["side"] = None
                    pos = context["positions"].get(self.symbol)
                    if pos:
                        return {"symbol": self.symbol, "side": side, "qty": pos["qty"]}
                return None

            # Random entry
            if self.rng.random() < self.entry_probability:
                side = "BUY" if self.rng.random() < 0.5 else "SELL"
                bar = history[-1]
                price = bar[4]
                cash = context["cash"]
                qty = int(cash * 0.5 / (price * 1.001))  # use 50% of cash
                if qty <= 0:
                    return None
                state["entry_bar"] = idx
                state["side"] = side
                return {"symbol": self.symbol, "side": side, "qty": qty}
            return None

        return strategy_fn

    def run(self, bars: list[list[float]], config: BacktestConfig | None = None, warmup: int = 50) -> BacktestResult:
        cfg = config or BacktestConfig()
        engine = BacktestEngine(cfg)
        return engine.run(bars, self.make_strategy_fn(), warmup=warmup)
