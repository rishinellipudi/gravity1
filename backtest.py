from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytz
from loguru import logger

import config
from utils.logger import setup_logger
from core.historical_feed import HistoricalFeed
from core.indicators import compute_vwap_bands, compute_slope_normalized, compute_atr_ratio
from core.state_machine import SymbolState, State
from core.sim_broker import SimBroker
from core.position_tracker import PositionTracker
from core.results import Results, Trade

EST = pytz.timezone("America/New_York")
BAR_COLS = ["open", "high", "low", "close", "volume"]
MIN_BARS = config.ATR_SLOW + config.SLOPE_LOOKBACK  # bars needed before indicators are valid


def run_backtest() -> None:
    setup_logger(f"backtest_{config.BACKTEST_START}_{config.BACKTEST_END}")
    logger.info(
        f"Backtest: {config.BACKTEST_START} → {config.BACKTEST_END} | "
        f"symbols={config.SYMBOLS} | size=${config.TRADE_DOLLAR_AMOUNT:.0f}"
    )

    feed    = HistoricalFeed()
    broker  = SimBroker()
    results = Results()

    for session_date in pd.bdate_range(config.BACKTEST_START, config.BACKTEST_END):
        date_obj = session_date.date()

        all_bars: dict[str, pd.DataFrame] = {}
        for symbol in config.SYMBOLS:
            df = feed.fetch_session_bars(symbol, date_obj)
            if not df.empty:
                all_bars[symbol] = df

        if not all_bars:
            logger.debug(f"{date_obj}: no market data, skipping")
            continue

        all_ts = sorted(set().union(*[set(df.index) for df in all_bars.values()]))
        if not all_ts:
            continue

        # Per-session state — everything resets each day
        states:       dict[str, SymbolState] = {s: SymbolState(s) for s in config.SYMBOLS}
        position:     PositionTracker        = PositionTracker()
        session_bars: dict[str, pd.DataFrame] = {
            s: pd.DataFrame(columns=BAR_COLS) for s in config.SYMBOLS
        }
        pending:       dict | None = None   # fill queued for next bar's open
        current_entry: dict | None = None   # tracks open trade metadata for results

        logger.info(f"--- {date_obj} ({len(all_ts)} bars) ---")

        for ts in all_ts:
            ts_est = ts if ts.tzinfo else EST.localize(ts)

            # ── 1. Execute any pending fill at this bar's open ───────────────
            if pending is not None:
                sym = pending["symbol"]
                if sym in all_bars and ts in all_bars[sym].index:
                    fill_price = float(all_bars[sym].loc[ts, "open"])

                    if pending["type"] == "enter":
                        shares = broker.shares_for_dollar_amount(fill_price)
                        position.open(sym, pending["direction"], fill_price, shares, shares * fill_price)
                        current_entry = {
                            "symbol":      sym,
                            "direction":   pending["direction"],
                            "entry_price": fill_price,
                            "shares":      shares,
                            "entry_ts":    ts_est,
                        }

                    elif pending["type"] == "exit" and not position.is_flat:
                        pnl = position.close(fill_price, pending["reason"])
                        results.record(Trade(
                            symbol=current_entry["symbol"],
                            direction=current_entry["direction"],
                            entry_price=current_entry["entry_price"],
                            exit_price=fill_price,
                            shares=current_entry["shares"],
                            pnl=pnl,
                            entry_time=current_entry["entry_ts"],
                            exit_time=ts_est,
                            exit_reason=pending["reason"],
                        ))
                        current_entry = None
                pending = None

            # ── 2. Append this bar to session buffers ────────────────────────
            for symbol in config.SYMBOLS:
                if symbol in all_bars and ts in all_bars[symbol].index:
                    row = all_bars[symbol].loc[[ts]]
                    session_bars[symbol] = pd.concat([session_bars[symbol], row])

            # ── 3. EOD: flatten at this bar's close, then end the session ────
            is_eod = (
                ts_est.hour == config.SESSION_END[0]
                and ts_est.minute >= config.SESSION_END[1]
            )
            if is_eod:
                if not position.is_flat:
                    sym = position.current.symbol
                    exit_price = (
                        float(all_bars[sym].loc[ts, "close"])
                        if sym in all_bars and ts in all_bars[sym].index
                        else position.current.entry_price
                    )
                    pnl = position.close(exit_price, "EOD")
                    if current_entry:
                        results.record(Trade(
                            symbol=current_entry["symbol"],
                            direction=current_entry["direction"],
                            entry_price=current_entry["entry_price"],
                            exit_price=exit_price,
                            shares=current_entry["shares"],
                            pnl=pnl,
                            entry_time=current_entry["entry_ts"],
                            exit_time=ts_est,
                            exit_reason="EOD",
                        ))
                break  # nothing more to do this session

            # ── 4. Run state machines ────────────────────────────────────────
            enter_signals: list[tuple[str, str]] = []  # (symbol, action)
            exit_signal:   tuple[str, str] | None = None

            for symbol in config.SYMBOLS:
                if symbol not in all_bars or ts not in all_bars[symbol].index:
                    continue
                bars_so_far = session_bars[symbol]
                if len(bars_so_far) < MIN_BARS:
                    continue

                bars  = compute_vwap_bands(bars_so_far)
                last  = bars.iloc[-1]
                slope = float(compute_slope_normalized(bars).iloc[-1])
                ratio = float(compute_atr_ratio(bars).iloc[-1])

                import math
                if math.isnan(slope) or math.isnan(ratio):
                    continue

                # Non-active symbols don't drive exits while in a position
                if not position.is_flat and symbol != position.current.symbol:
                    continue

                action = states[symbol].on_bar(
                    close=float(last["close"]), vwap=float(last["vwap"]), sd=float(last["sd"]),
                    upper1=float(last["upper1"]), lower1=float(last["lower1"]),
                    upper2=float(last["upper2"]), lower2=float(last["lower2"]),
                    slope_norm=slope, atr_ratio=ratio,
                )

                if action in ("enter_long", "enter_short") and position.is_flat:
                    enter_signals.append((symbol, action))
                elif action in ("exit", "stop") and not position.is_flat:
                    exit_signal = (symbol, "TP" if action == "exit" else "SL")

            # Exit takes priority; can't enter and exit on same bar
            if exit_signal:
                sym, reason = exit_signal
                pending = {"type": "exit", "symbol": sym, "reason": reason}

            elif enter_signals and position.is_flat:
                # Pick the symbol furthest from VWAP in SD units
                best_sym    = max(enter_signals, key=lambda x: abs(states[x[0]].break_deviation))[0]
                best_action = dict(enter_signals)[best_sym]

                # Revert any other symbols that also transitioned to IN_POSITION
                for sym, _ in enter_signals:
                    if sym != best_sym:
                        states[sym].force_reset()

                direction = "long" if best_action == "enter_long" else "short"
                pending = {"type": "enter", "symbol": best_sym, "direction": direction}

        logger.info(f"{date_obj} done | running P&L: ${results.cumulative_pnl:.2f}")

    results.print_summary()

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"trades_{config.BACKTEST_START}_{config.BACKTEST_END}.csv"
    results.save_csv(out_path)


if __name__ == "__main__":
    run_backtest()
