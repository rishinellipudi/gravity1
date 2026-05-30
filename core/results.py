import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from loguru import logger


@dataclass
class Trade:
    symbol: str
    direction: str        # 'long' or 'short'
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str      # 'TP', 'SL', 'EOD'


class Results:
    def __init__(self):
        self.trades: list[Trade] = []
        self.cumulative_pnl: float = 0.0

    def record(self, trade: Trade) -> None:
        self.trades.append(trade)
        self.cumulative_pnl += trade.pnl

    def print_summary(self) -> None:
        if not self.trades:
            logger.info("No trades recorded.")
            return

        winners = [t for t in self.trades if t.pnl > 0]
        losers  = [t for t in self.trades if t.pnl <= 0]
        by_reason = {"TP": 0, "SL": 0, "EOD": 0}
        for t in self.trades:
            by_reason[t.exit_reason] = by_reason.get(t.exit_reason, 0) + 1

        win_rate = len(winners) / len(self.trades) * 100
        avg_win  = sum(t.pnl for t in winners) / len(winners) if winners else 0.0
        avg_loss = sum(t.pnl for t in losers)  / len(losers)  if losers  else 0.0
        profit_factor = (
            abs(sum(t.pnl for t in winners)) / abs(sum(t.pnl for t in losers))
            if losers and sum(t.pnl for t in losers) != 0 else float("inf")
        )
        rr_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else float("inf")

        # Max drawdown from equity curve
        equity = [0.0]
        for t in self.trades:
            equity.append(equity[-1] + t.pnl)
        peak, max_dd = equity[0], 0.0
        for e in equity:
            peak = max(peak, e)
            max_dd = max(max_dd, peak - e)

        logger.info("=" * 52)
        logger.info("  BACKTEST RESULTS")
        logger.info("=" * 52)
        logger.info(f"  Total trades    : {len(self.trades)}")
        logger.info(f"  Win rate        : {win_rate:.1f}%  ({len(winners)}W / {len(losers)}L)")
        logger.info(f"  Total P&L       : ${self.cumulative_pnl:.2f}")
        logger.info(f"  Avg winner      : ${avg_win:.2f}")
        logger.info(f"  Avg loser       : ${avg_loss:.2f}")
        logger.info(f"  R:R ratio       : {rr_ratio:.2f}")
        logger.info(f"  Profit factor   : {profit_factor:.2f}")
        logger.info(f"  Max drawdown    : ${max_dd:.2f}")
        logger.info(f"  Exits — TP:{by_reason['TP']}  SL:{by_reason['SL']}  EOD:{by_reason['EOD']}")
        logger.info("=" * 52)

    def save_csv(self, path: Path) -> None:
        fieldnames = [
            "entry_time", "exit_time", "symbol", "direction",
            "entry_price", "exit_price", "shares", "pnl", "exit_reason",
        ]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in self.trades:
                writer.writerow({
                    "entry_time":  t.entry_time.strftime("%Y-%m-%d %H:%M %Z"),
                    "exit_time":   t.exit_time.strftime("%Y-%m-%d %H:%M %Z"),
                    "symbol":      t.symbol,
                    "direction":   t.direction,
                    "entry_price": f"{t.entry_price:.4f}",
                    "exit_price":  f"{t.exit_price:.4f}",
                    "shares":      t.shares,
                    "pnl":         f"{t.pnl:.2f}",
                    "exit_reason": t.exit_reason,
                })
        logger.info(f"Trade log saved → {path}")
