from __future__ import annotations
from dataclasses import dataclass
from loguru import logger


@dataclass
class Position:
    symbol: str
    direction: str      # 'long' or 'short'
    entry_price: float
    shares: int
    dollar_size: float


class PositionTracker:
    def __init__(self):
        self._position: Position | None = None

    @property
    def is_flat(self) -> bool:
        return self._position is None

    @property
    def current(self) -> Position | None:
        return self._position

    def open(self, symbol: str, direction: str, entry_price: float,
             shares: int, dollar_size: float) -> None:
        if self._position is not None:
            logger.warning(f"PositionTracker.open called while already holding {self._position.symbol}")
            return
        self._position = Position(symbol, direction, entry_price, shares, dollar_size)
        logger.info(
            f"Position opened | {symbol} {direction} | "
            f"{shares} shares @ {entry_price:.2f} | ${dollar_size:.0f}"
        )

    def close(self, exit_price: float, reason: str) -> float:
        if self._position is None:
            logger.warning("PositionTracker.close called with no open position")
            return 0.0
        pos = self._position
        if pos.direction == "long":
            pnl = (exit_price - pos.entry_price) * pos.shares
        else:
            pnl = (pos.entry_price - exit_price) * pos.shares
        logger.info(
            f"Position closed | {pos.symbol} {pos.direction} | "
            f"exit={exit_price:.2f} | P&L=${pnl:.2f} | reason={reason}"
        )
        self._position = None
        return pnl
