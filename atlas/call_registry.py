"""Call registry module for ATLAS - append-only registry of trading calls.

This module provides an append-only JSONL registry for recording trading calls
before outcomes are known, enabling proper forward-looking evaluation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DuplicateCallError(ValueError):
    """Raised when attempting to append a call with an existing ID."""
    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Call:
    """Frozen dataclass representing a registered trading call."""
    id: str
    created_at: datetime
    origin: str
    symbol: str
    side: str  # "BUY" or "SELL"
    stop: float
    target: float
    horizon_bars: int
    confidence: Optional[float]
    rationale: str = ""
    snapshot_id: Optional[str] = None
    timeframe: str = "1d"

    def __post_init__(self):
        # Validate timezone-aware datetime
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

        # Validate side
        if self.side not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {self.side}")

        # Validate prices
        if self.stop <= 0 or self.target <= 0:
            raise ValueError("stop and target must be positive")

        # Validate horizon
        if self.horizon_bars < 1:
            raise ValueError("horizon_bars must be >= 1")

        # Validate confidence
        if self.confidence is not None and not (0 <= self.confidence <= 1):
            raise ValueError("confidence must be in [0, 1] or None")

        # Validate symbol format
        if not (self.symbol.endswith(".NS") or self.symbol.endswith(".BO")):
            raise ValueError("symbol must end with .NS or .BO")

        # Validate BUY/SELL price relationships
        if self.side == "BUY" and not (self.stop < self.target):
            raise ValueError("BUY requires stop < target")
        if self.side == "SELL" and not (self.target < self.stop):
            raise ValueError("SELL requires target < stop")


# ---------------------------------------------------------------------------
# Registry functions
# ---------------------------------------------------------------------------

def _validate_call(call: Call, universe: Optional[tuple[str, ...]] = None) -> None:
    """Validate a call before appending.

    Args:
        call: Call to validate.
        universe: Optional universe of allowed symbols.

    Raises:
        ValueError: If validation fails.
    """
    # Universe check
    if universe is not None and call.symbol not in universe:
        raise ValueError(f"Symbol {call.symbol} not in universe")

    # The Call.__post_init__ handles most validation


def append_call(call: Call, path: str, universe: Optional[tuple[str, ...]] = None) -> None:
    """Append a call to the registry file.

    Args:
        call: Call to append.
        path: Path to registry file (JSONL).
        universe: Optional universe for symbol validation.

    Raises:
        DuplicateCallError: If call.id already exists in registry.
        ValueError: If validation fails.
    """
    _validate_call(call, universe)

    # Check for duplicate ID
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing = json.loads(line)
                    if existing.get("id") == call.id:
                        raise DuplicateCallError(f"Call with id {call.id} already exists")
                except json.JSONDecodeError:
                    continue

    # Convert to dict for JSON serialization
    call_dict = asdict(call)
    call_dict["created_at"] = call.created_at.isoformat()

    # Append to file (create if doesn't exist)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(call_dict, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_calls(path: str) -> list[Call]:
    """Read all calls from the registry file.

    Args:
        path: Path to registry file (JSONL).

    Returns:
        List of Call objects in order of registration.
    """
    if not os.path.exists(path):
        return []

    calls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # Convert ISO string back to datetime
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                calls.append(Call(**data))
            except (json.JSONDecodeError, ValueError, TypeError):
                # Skip malformed lines
                continue

    return calls