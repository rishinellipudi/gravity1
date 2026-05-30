import numpy as np
import pandas as pd
import config


def compute_vwap_bands(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Session-anchored VWAP with ±1 SD and ±2 SD bands.
    bars must have columns: open, high, low, close, volume
    Returns bars with added columns: vwap, sd, upper1, lower1, upper2, lower2
    """
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3
    cum_tv = (typical * bars["volume"]).cumsum()
    cum_v  = bars["volume"].cumsum()
    vwap   = cum_tv / cum_v

    # Rolling variance of typical price weighted by volume (session-anchored)
    cum_tv2 = (typical ** 2 * bars["volume"]).cumsum()
    variance = (cum_tv2 / cum_v) - vwap ** 2
    variance = variance.clip(lower=0)  # floating point can produce tiny negatives
    sd = np.sqrt(variance)

    result = bars.copy()
    result["vwap"]   = vwap
    result["sd"]     = sd
    result["upper1"] = vwap + config.ENTRY_SD * sd
    result["lower1"] = vwap - config.ENTRY_SD * sd
    result["upper2"] = vwap + config.STOP_SD  * sd
    result["lower2"] = vwap - config.STOP_SD  * sd
    return result


def compute_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    """
    Wilder's ATR over `period` bars.
    Returns a Series aligned to bars.index.
    """
    high  = bars["high"]
    low   = bars["low"]
    close = bars["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Seed with simple mean for first window, then Wilder smoothing
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return atr


def compute_slope_normalized(bars: pd.DataFrame) -> pd.Series:
    """
    VWAP slope over SLOPE_LOOKBACK bars, normalized by ATR(14).
    slope = (VWAP[t] - VWAP[t - lookback]) / lookback / ATR14[t]
    """
    vwap   = bars["vwap"]
    atr14  = compute_atr(bars, config.ATR_SLOW)
    raw_slope = (vwap - vwap.shift(config.SLOPE_LOOKBACK)) / config.SLOPE_LOOKBACK
    return (raw_slope / atr14).replace([np.inf, -np.inf], np.nan)


def compute_atr_ratio(bars: pd.DataFrame) -> pd.Series:
    """ATR(3) / ATR(14)"""
    return compute_atr(bars, config.ATR_FAST) / compute_atr(bars, config.ATR_SLOW)


def deviation_in_sd_units(close: float, vwap: float, sd: float) -> float:
    """How many SDs is `close` away from VWAP. Signed: positive = above."""
    if sd == 0:
        return 0.0
    return (close - vwap) / sd
