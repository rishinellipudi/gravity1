from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from loguru import logger
import config


class State(IntEnum):
    WAITING        = 0
    BREAK_DETECTED = 1
    IN_POSITION    = 2
    STOPPED_OUT    = 3


@dataclass
class SymbolState:
    symbol: str
    state: State = State.WAITING

    # Direction of the detected break: +1 = price above upper1, -1 = below lower1
    break_direction: int = 0

    # SD units of the break that triggered State 1 (used for signal selection)
    break_deviation: float = 0.0

    cooldown_bars_remaining: int = 0
    bars_in_position: int = 0
    entry_close: float = 0.0

    def on_bar(self, close: float, vwap: float, sd: float,
               upper1: float, lower1: float, upper2: float, lower2: float,
               slope_norm: float, atr_ratio: float) -> str | None:
        """
        Process one completed bar. Returns an action string or None:
          'enter_long', 'enter_short', 'exit', 'stop'
        """
        if self.state == State.WAITING:
            return self._check_break(close, upper1, lower1, sd, vwap)

        if self.state == State.BREAK_DETECTED:
            return self._check_reentry(close, upper1, lower1, slope_norm, atr_ratio)

        if self.state == State.IN_POSITION:
            return self._check_exit(close, vwap, upper2, lower2)

        if self.state == State.STOPPED_OUT:
            return self._check_cooldown(close, upper1, lower1)

        return None

    # ------------------------------------------------------------------
    def _check_break(self, close, upper1, lower1, sd, vwap):
        from core.indicators import deviation_in_sd_units
        if close > upper1:
            self.break_direction = +1
            self.break_deviation = deviation_in_sd_units(close, vwap, sd)
            self.state = State.BREAK_DETECTED
            logger.debug(f"{self.symbol} | State 0→1 | break UP {self.break_deviation:.2f} SD")
        elif close < lower1:
            self.break_direction = -1
            self.break_deviation = deviation_in_sd_units(close, vwap, sd)
            self.state = State.BREAK_DETECTED
            logger.debug(f"{self.symbol} | State 0→1 | break DN {self.break_deviation:.2f} SD")
        return None

    def _check_reentry(self, close, upper1, lower1, slope_norm, atr_ratio):
        re_entered = (
            (self.break_direction == +1 and close <= upper1) or
            (self.break_direction == -1 and close >= lower1)
        )
        if not re_entered:
            return None

        slope_ok = abs(slope_norm) < config.MAX_SLOPE_NORMALIZED
        ratio_ok = atr_ratio < config.MAX_ATR_RATIO

        if slope_ok and ratio_ok:
            if self.break_direction == +1:
                self.state = State.WAITING
                logger.debug(f"{self.symbol} | State 1→0 | short skipped (long-only mode)")
                return None
            self.entry_close = close
            self.state = State.IN_POSITION
            logger.info(f"{self.symbol} | State 1→2 | enter_long | slope={slope_norm:.4f} ratio={atr_ratio:.3f}")
            return "enter_long"
        else:
            self.state = State.WAITING
            logger.debug(
                f"{self.symbol} | State 1→0 | filters failed "
                f"slope_ok={slope_ok} ratio_ok={ratio_ok}"
            )
            return None

    def _check_exit(self, close, vwap, upper2, lower2):
        self.bars_in_position += 1
        logger.debug(f"{self.symbol} | State 2 | bars_in_position={self.bars_in_position}")

        if self.bars_in_position == config.STALL_CHECK_BARS:
            total_distance = abs(vwap - self.entry_close)
            if total_distance > 0:
                price_moved = (
                    (self.entry_close - close) if self.break_direction == +1
                    else (close - self.entry_close)
                )
                progress = price_moved / total_distance
                if progress < config.MIN_PROGRESS_PCT:
                    self.state = State.WAITING
                    self.bars_in_position = 0
                    self.entry_close = 0.0
                    logger.info(f"{self.symbol} | State 2→0 | stall exit | progress={progress:.1%}")
                    return "exit"

        if self.bars_in_position >= config.MAX_HOLD_BARS:
            self.state = State.WAITING
            self.bars_in_position = 0
            self.entry_close = 0.0
            logger.info(f"{self.symbol} | State 2→0 | timeout after {config.MAX_HOLD_BARS} bars")
            return "exit"

        hit_tp = (
            (self.break_direction == +1 and close <= vwap) or
            (self.break_direction == -1 and close >= vwap)
        )
        hit_sl = (
            (self.break_direction == +1 and close >= upper2) or
            (self.break_direction == -1 and close <= lower2)
        )

        if hit_sl:
            self.state = State.STOPPED_OUT
            self.cooldown_bars_remaining = config.COOLDOWN_BARS
            self.bars_in_position = 0
            self.entry_close = 0.0
            logger.info(f"{self.symbol} | State 2→3 | stop hit at {close:.2f}")
            return "stop"

        if hit_tp:
            self.state = State.WAITING
            self.bars_in_position = 0
            self.entry_close = 0.0
            logger.info(f"{self.symbol} | State 2→0 | TP hit at {close:.2f}")
            return "exit"

        return None

    def _check_cooldown(self, close, upper1, lower1):
        self.cooldown_bars_remaining -= 1
        if self.cooldown_bars_remaining > 0:
            logger.debug(f"{self.symbol} | State 3 | cooldown {self.cooldown_bars_remaining} bars left")
            return None

        inside_band = lower1 <= close <= upper1
        if inside_band:
            self.state = State.WAITING
            logger.debug(f"{self.symbol} | State 3→0 | cooldown done, price inside band")
        return None

    def force_reset(self):
        """Called by session controller at EOD flatten."""
        self.state = State.WAITING
        self.break_direction = 0
        self.break_deviation = 0.0
        self.cooldown_bars_remaining = 0
        self.bars_in_position = 0
        self.entry_close = 0.0
