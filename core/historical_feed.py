from datetime import datetime, timedelta
from datetime import date as DateType
import pandas as pd
import pytz
from loguru import logger
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import config

EST = pytz.timezone("America/New_York")
BAR_COLS = ["open", "high", "low", "close", "volume"]


class HistoricalFeed:
    def __init__(self):
        self._client = StockHistoricalDataClient(config.API_KEY, config.API_SECRET)

    def fetch_session_bars(self, symbol: str, session_date: DateType) -> pd.DataFrame:
        """
        Fetch 5-min bars for one symbol on one trading day,
        filtered to session window [SESSION_START, SESSION_END].
        Returns DataFrame with float columns open/high/low/close/volume,
        indexed by timezone-aware EST timestamps.
        """
        session_start = EST.localize(datetime(
            session_date.year, session_date.month, session_date.day,
            config.SESSION_START[0], config.SESSION_START[1],
        ))
        session_end = EST.localize(datetime(
            session_date.year, session_date.month, session_date.day,
            config.SESSION_END[0], config.SESSION_END[1],
        ))
        # Request a few minutes past session end so Alpaca includes the 12:55 bar
        fetch_end = session_end + timedelta(minutes=4)

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(config.BAR_TIMEFRAME_MINUTES, TimeFrameUnit.Minute),
            start=session_start,
            end=fetch_end,
        )

        try:
            bars = self._client.get_stock_bars(req)
            df = bars.df
        except Exception as e:
            logger.warning(f"{symbol} {session_date}: fetch failed — {e}")
            return pd.DataFrame(columns=BAR_COLS)

        if df is None or df.empty:
            return pd.DataFrame(columns=BAR_COLS)

        # alpaca-py returns MultiIndex (symbol, timestamp)
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        if df.empty:
            return pd.DataFrame(columns=BAR_COLS)

        # Normalise to EST-aware index
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(EST)

        # Clip to session window
        df = df[(df.index >= session_start) & (df.index <= session_end)]

        return df[BAR_COLS].astype(float)
