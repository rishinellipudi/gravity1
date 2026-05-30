from __future__ import annotations
from loguru import logger
from core.state_machine import SymbolState, State


def select_best_signal(states: dict[str, SymbolState]) -> SymbolState | None:
    """
    Among all instruments currently in State.BREAK_DETECTED,
    return the one with the largest absolute deviation from VWAP.
    Returns None if no instrument is ready.
    """
    candidates = [
        s for s in states.values()
        if s.state == State.BREAK_DETECTED
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda s: abs(s.break_deviation))
    logger.debug(
        f"Signal selector: best={best.symbol} deviation={best.break_deviation:.2f} SD "
        f"from {[f'{s.symbol}:{s.break_deviation:.2f}' for s in candidates]}"
    )
    return best
