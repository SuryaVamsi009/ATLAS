"""
RiskVerdict module for the ATLAS architecture (L4 - Decision & Risk).

This module implements the RiskVerdict engine that validates trading
proposals from L3 (Analysis & Signal Generation) against risk rules
before approval for execution by L5 (Execution & Management).

The engine is model-agnostic and has no AI provider dependencies.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum

# Ensure atlas submodules are importable when this file is loaded directly
_AtlasDir = os.path.dirname(os.path.abspath(__file__))
if _AtlasDir not in sys.path:
    sys.path.insert(0, _AtlasDir)

from decision_proposal import DecisionProposal
from state_snapshot import StateSnapshot


class VetoReason(Enum):
    """Enum representing the possible veto reasons from risk checks."""
    SIZE_OK = "size_ok"
    LOSS_OK = "loss_ok"
    HOURS_OK = "hours_ok"
    SYMBOL_OK = "symbol_ok"
    CONFIDENCE_OK = "confidence_ok"
    NONE = None

    def __bool__(self) -> bool:
        """Return False for valid (OK) reasons, True for None."""
        return self is VetoReason.NONE


@dataclass
class RiskVerdict:
    """
    Result of a risk verification run.

    Attributes:
        approved: True only if ALL 5 checks pass.
        final_qty: Adjusted quantity after risk checks.
        final_stop: Adjusted stop price after risk checks.
        veto_reason: The first failing check name, or None if all pass.
        checks: Dict of 5 boolean checks: size_ok, loss_ok, hours_ok, symbol_ok, confidence_ok.
    """
    approved: bool
    final_qty: float
    final_stop: float
    veto_reason: VetoReason | None
    checks: dict[str, bool]


def _check_size_ok(proposal: DecisionProposal, context: dict[str, Any]) -> tuple[bool, float]:
    """
    Check: size_hint respects max position limits.

    The size_hint should not exceed max_position_size as a fraction of equity.

    Returns:
        (passed, adjusted_qty) tuple. If check passes, adjusted_qty = size_hint * equity.
        If check fails, adjusted_qty is the max allowed quantity.
    """
    max_position_size = context.get("max_position_size", 1.0)
    equity = context.get("equity", 10000.0)
    size_hint = proposal.size_hint

    if size_hint > max_position_size:
        adjusted_qty = max_position_size * equity
        return False, adjusted_qty

    return True, size_hint * equity


def _check_loss_ok(proposal: DecisionProposal, snapshot: StateSnapshot, context: dict[str, Any]) -> tuple[bool, float]:
    """
    Check: unrealised_pnl + proposed loss stays within daily/weekly limits.

    Uses snapshot.account.daily_pnl and snapshot.position.unrealised_pnl
    to check against max_daily_loss and max_weekly_loss from context.

    Returns:
        (passed, adjusted_qty) tuple. If check fails, adjusted_qty is reduced
        to stay within limits. If check passes, adjusted_qty = size_hint * equity.
    """
    daily_loss_limit = context.get("max_daily_loss", 1000.0)
    weekly_loss_limit = context.get("max_weekly_loss", 5000.0)
    equity = context.get("equity", 10000.0)

    unrealised_pnl = snapshot.position.get("unrealised_pnl", 0.0)
    at_risk = proposal.size_hint * equity
    proposed_loss = at_risk

    total_loss = unrealised_pnl + proposed_loss

    # Check daily limit
    if total_loss > daily_loss_limit:
        allowed_at_risk = daily_loss_limit - unrealised_pnl
        if allowed_at_risk > 0:
            adjusted_qty = (allowed_at_risk / equity) * proposal.size_hint
        else:
            adjusted_qty = 0.0
        return False, adjusted_qty

    # Check weekly limit
    if total_loss > weekly_loss_limit:
        allowed_at_risk = weekly_loss_limit - unrealised_pnl
        if allowed_at_risk > 0:
            adjusted_qty = (allowed_at_risk / equity) * proposal.size_hint
        else:
            adjusted_qty = 0.0
        return False, adjusted_qty

    return True, proposal.size_hint * equity


def _check_hours_ok(context: dict[str, Any]) -> tuple[bool, None]:
    """
    Check: trading hours are valid (within 09:15-15:30 IST market hours).

    Uses current_time from context, expected to be aware IST timezone.

    Returns:
        (passed, None) tuple - hours check doesn't adjust quantity.
    """
    current_time = context.get("current_time")

    if current_time is None:
        return False, None

    if current_time.tzinfo is None:
        ist_time = current_time + timedelta(hours=5, minutes=30)
    else:
        ist_time = current_time

    market_open = time(9, 15)
    market_close = time(15, 30)

    current_time_only = ist_time.time()

    if current_time_only < market_open or current_time_only > market_close:
        return False, None

    return True, None


def _check_symbol_ok(symbol: str, allowed_symbols: list[str]) -> tuple[bool, float]:
    """
    Check: symbol is in allowed watchlist.

    Returns:
        (passed, adjusted_qty) tuple. If check fails, adjusted_qty = 0.0.
        If check passes, adjusted_qty = 1.0 (caller will use original qty).
    """
    if symbol not in allowed_symbols:
        return False, 0.0
    return True, 1.0


def _check_confidence_ok(confidence: float, min_confidence: float, max_confidence: float) -> tuple[bool, float]:
    """
    Check: confidence is above threshold and not excessively high without reason.

    Returns:
        (passed, factor) tuple. factor is multiplied by the proposed quantity.
        If check passes (within range), factor = 1.0.
        If confidence < min_confidence, factor = 0.0.
        If confidence > max_confidence, factor = max_confidence / confidence.
    """
    if confidence < min_confidence:
        return False, 0.0

    if confidence > max_confidence:
        factor = max_confidence / confidence
        return False, factor

    return True, 1.0


def verify(proposal: DecisionProposal, snapshot: StateSnapshot, context: dict[str, Any]) -> RiskVerdict:
    """
    Verify a DecisionProposal against risk rules and return a RiskVerdict.

    Runs the 5 checks (from ATLAS doc/L4):
    1. size_ok: size_hint respects max position limits
    2. loss_ok: unrealised_pnl + proposed loss stays within daily/weekly limits
    3. hours_ok: trading hours are valid (within 09:15-15:30 IST market hours)
    4. symbol_ok: symbol is in allowed watchlist
    5. confidence_ok: confidence is above threshold and not excessively high

    Args:
        proposal: The DecisionProposal to verify.
        snapshot: The StateSnapshot with current market state.
        context: Dict with risk context parameters.

    Returns:
        A RiskVerdict instance with approval status, adjusted values, and check results.
    """
    # Extract context values with defaults
    max_position_size = context.get("max_position_size", 1.0)
    max_daily_loss = context.get("max_daily_loss", 1000.0)
    max_weekly_loss = context.get("max_weekly_loss", 5000.0)
    min_confidence = context.get("min_confidence", 0.3)
    max_confidence = context.get("max_confidence", 0.9)
    allowed_symbols = context.get("allowed_symbols", [])
    current_time = context.get("current_time")
    equity = context.get("equity", snapshot.account.get("equity", 10000.0))
    symbol = snapshot.symbol

    # Run all 5 checks in order, collecting pass/fail and adjusted quantities
    size_pass, size_qty = _check_size_ok(proposal, context)
    loss_pass, loss_qty = _check_loss_ok(proposal, snapshot, context)
    hours_pass, _ = _check_hours_ok(context)
    symbol_pass, symbol_factor = _check_symbol_ok(symbol, allowed_symbols)
    conf_pass, conf_factor = _check_confidence_ok(proposal.confidence, min_confidence, max_confidence)

    checks: dict[str, bool] = {
        "size_ok": size_pass,
        "loss_ok": loss_pass,
        "hours_ok": hours_pass,
        "symbol_ok": symbol_pass,
        "confidence_ok": conf_pass,
    }

    # Determine veto_reason: first failing check name
    veto_reason: VetoReason | None = None
    if not size_pass:
        veto_reason = VetoReason.SIZE_OK
    elif not loss_pass:
        veto_reason = VetoReason.LOSS_OK
    elif not hours_pass:
        veto_reason = VetoReason.HOURS_OK
    elif not symbol_pass:
        veto_reason = VetoReason.SYMBOL_OK
    elif not conf_pass:
        veto_reason = VetoReason.CONFIDENCE_OK
    else:
        veto_reason = VetoReason.NONE

    # approved: True only if ALL 5 checks pass
    approved = all(checks.values())

    # Calculate final_qty: start with base size_hint * equity
    final_qty = proposal.size_hint * equity
    final_stop = proposal.stop_hint if proposal.stop_hint is not None else 0.0

    # Apply adjustments based on veto reason
    if veto_reason == VetoReason.SIZE_OK:
        final_qty = size_qty
    elif veto_reason == VetoReason.LOSS_OK:
        final_qty = loss_qty
    elif veto_reason == VetoReason.CONFIDENCE_OK:
        final_qty = proposal.size_hint * equity * conf_factor
    elif veto_reason == VetoReason.SYMBOL_OK:
        final_qty = 0.0
    # If veto_reason is NONE (all passed), final_qty stays as size_hint * equity

    # final_stop: use proposal.stop_hint if available, else 0.0
    if proposal.stop_hint is not None:
        final_stop = proposal.stop_hint
    else:
        final_stop = 0.0

    return RiskVerdict(
        approved=approved,
        final_qty=final_qty,
        final_stop=final_stop,
        veto_reason=veto_reason,
        checks=checks,
    )