# Strategy Hypotheses

Each strategy must have its hypothesis documented before testing. This file records the hypothesis, expected behavior, and validation criteria.

---

## 1. Opening Range Breakout (ORB)

**Hypothesis**: The first 15-30 minutes of trading establish a range. A breakout above the opening range high (for longs) or below the opening range low (for shorts) with volume confirmation signals a directional move that persists for the session.

**Parameters**:
- Opening range period: 15 minutes (9:15-9:30 IST) or 30 minutes (9:15-9:45 IST)
- Breakout threshold: 0.1% above high / below low
- Volume filter: Current bar volume > 1.5x average of opening range bars
- Stop: Opening range low (long) / high (short)
- Target: 2x risk (R:R = 2:1)
- Horizon: Intraday (force flat by 15:15 IST)

**Expected Edge**: Momentum continuation after range breakout in trending markets.

**Failure Modes**:
- False breakouts in choppy/range-bound markets
- Gap openings that invalidate the range
- Low volume breakouts that reverse

**Validation Criteria**:
- Net-of-cost hit rate > 50% (after ~0.11% round-trip cost)
- Average R > 0.5
- Deflated Sharpe > 1.0
- Cost drag < 30% of gross returns

---

## 2. VWAP Reversion

**Hypothesis**: Price tends to revert to VWAP (Volume Weighted Average Price) during the session. Deviations beyond 1-2 standard deviations from VWAP represent mean-reversion opportunities.

**Parameters**:
- VWAP calculation: Session VWAP from 9:15 IST
- Entry: Price > VWAP + 1.5σ (short) or Price < VWAP - 1.5σ (long)
- σ: Rolling 20-bar standard deviation of (price - VWAP)
- Stop: 1.5x entry distance from VWAP
- Target: VWAP (mean reversion)
- Horizon: Intraday (force flat by 15:15 IST)
- Filter: Only trade in first 2 hours (9:15-11:15 IST) for stronger mean reversion

**Expected Edge**: Institutional algorithms anchor to VWAP; retail flow creates temporary deviations.

**Failure Modes**:
- Strong trending days where price doesn't revert
- News-driven moves that shift fair value
- Low liquidity periods with noisy VWAP

**Validation Criteria**:
- Net-of-cost hit rate > 55%
- Average R > 0.3
- Deflated Sharpe > 0.8
- Works best in low-trend regimes (ADX < 25)

---

## 3. Gap Fade

**Hypothesis**: Overnight gaps (open vs previous close) often fill during the session as market makers balance order flow. Fading the gap direction at the open with a tight stop captures this reversion.

**Parameters**:
- Gap threshold: |Open - Prev Close| / Prev Close > 0.5%
- Direction: Fade the gap (short gap up, long gap down)
- Entry: Market open (9:15 IST)
- Stop: 0.5% beyond entry (tight)
- Target: Previous close (gap fill) or 50% gap fill
- Horizon: 60 minutes (force flat by 10:15 IST)
- Filter: Gap > 1% uses wider stop (1%), target at 50% fill

**Expected Edge**: Overnight emotional moves reverse as liquidity returns.

**Failure Modes**:
- Earnings/news gaps that continue trending
- Market-wide gap-and-go days
- Low float stocks with persistent gaps

**Validation Criteria**:
- Net-of-cost hit rate > 50%
- Average R > 0.4
- Deflated Sharpe > 0.8
- Gap fill rate > 60% for gaps < 1%

---

## Validation Framework

All strategies evaluated using:
- **Purged walk-forward splits**: 70% train, 15% embargo, 15% test
- **Hold-out period**: Most recent 3 months untouched until final validation
- **Trial log**: `quant/trials.jsonl` records every strategy configuration tested
- **Deflated Sharpe**: Adjusts for multiple testing across all trials
- **2× Cost stress test**: Doubles round-trip cost to verify robustness
- **Baselines**: Buy-and-hold and random-entry must lose ~cost drag

**Decision Rule**: If no strategy survives validation (deflated Sharpe < 1.0 after 2× cost stress), report plainly: "No edge survives validation."