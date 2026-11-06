"""Indian cost stack for backtesting.

Implements the Indian equity cost model:
- Brokerage: min(0.03%, ₹20) per order (typical discount broker)
- STT: 0.025% on sell side only
- Exchange charges: NSE 0.00325% on turnover
- SEBI charges: ₹10 per crore (0.0001%) on turnover
- Stamp duty: 0.003% on buy side
- GST: 18% on (brokerage + exchange + SEBI charges)

All rates are configurable via IndianCostConfig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class IndianCostConfig:
    """Configuration for the Indian equity cost stack.

    All percentages are expressed as fractions (e.g., 0.0003 = 0.03%).
    """

    # Brokerage: min(rate * turnover, cap) per order
    brokerage_rate: float = 0.0003       # 0.03%
    brokerage_cap: float = 20.0          # ₹20 max per order

    # STT: charged on sell side only
    stt_rate: float = 0.00025            # 0.025% on sell

    # Exchange charges (NSE): on total turnover (buy + sell)
    exchange_rate: float = 0.0000325     # 0.00325%

    # SEBI charges: ₹10 per crore = 0.0001% on turnover
    sebi_rate: float = 0.000001          # 0.0001%

    # Stamp duty: on buy side only
    stamp_duty_rate: float = 0.00003     # 0.003% on buy

    # GST on (brokerage + exchange + sebi)
    gst_rate: float = 0.18               # 18%

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brokerage_rate": self.brokerage_rate,
            "brokerage_cap": self.brokerage_cap,
            "stt_rate": self.stt_rate,
            "exchange_rate": self.exchange_rate,
            "sebi_rate": self.sebi_rate,
            "stamp_duty_rate": self.stamp_duty_rate,
            "gst_rate": self.gst_rate,
        }


class CostModel:
    """Computes transaction costs for Indian equity trades.

    Usage:
        cost_model = CostModel(IndianCostConfig())
        buy_cost = cost_model.compute_buy_cost(price=100.0, qty=10)
        sell_cost = cost_model.compute_sell_cost(price=105.0, qty=10)
    """

    def __init__(self, config: IndianCostConfig | None = None) -> None:
        self.config = config or IndianCostConfig()

    def _brokerage(self, turnover: float) -> float:
        """Brokerage = min(rate * turnover, cap)."""
        return min(self.config.brokerage_rate * turnover, self.config.brokerage_cap)

    def compute_buy_cost(self, price: float, qty: int) -> float:
        """Total cost for a buy order (in ₹).

        Buy side costs: brokerage + exchange + SEBI + stamp duty + GST
        (STT is sell-side only in equity delivery/intraday)
        """
        turnover = price * qty
        brokerage = self._brokerage(turnover)
        exchange = self.config.exchange_rate * turnover
        sebi = self.config.sebi_rate * turnover
        stamp = self.config.stamp_duty_rate * turnover
        gst = self.config.gst_rate * (brokerage + exchange + sebi)
        return brokerage + exchange + sebi + stamp + gst

    def compute_sell_cost(self, price: float, qty: int) -> float:
        """Total cost for a sell order (in ₹).

        Sell side costs: brokerage + STT + exchange + SEBI + GST
        (stamp duty is buy-side only)
        """
        turnover = price * qty
        brokerage = self._brokerage(turnover)
        stt = self.config.stt_rate * turnover
        exchange = self.config.exchange_rate * turnover
        sebi = self.config.sebi_rate * turnover
        gst = self.config.gst_rate * (brokerage + exchange + sebi)
        return brokerage + stt + exchange + sebi + gst

    def compute_round_trip_cost(self, buy_price: float, sell_price: float, qty: int) -> float:
        """Total cost for a round trip (buy + sell)."""
        return self.compute_buy_cost(buy_price, qty) + self.compute_sell_cost(sell_price, qty)

    def cost_drag_pct(self, price: float, qty: int) -> float:
        """Cost as a percentage of turnover for a round trip at the same price."""
        cost = self.compute_round_trip_cost(price, price, qty)
        turnover = price * qty * 2  # buy + sell turnover
        return cost / turnover if turnover > 0 else 0.0
