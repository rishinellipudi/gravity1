import os
from dotenv import load_dotenv

load_dotenv()

# --- Alpaca credentials (used for historical data fetching) ---
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# --- Instruments ---
SYMBOLS = ["QQQ"]

# --- Session window (EST) ---
SESSION_START = (10, 0)   # 10:00 AM
SESSION_END   = (14, 30)  # 2:30 PM — EOD flatten

# --- Bar timeframe ---
BAR_TIMEFRAME_MINUTES = 5

# --- Sizing ---
TRADE_DOLLAR_AMOUNT = 1_000.0

# --- VWAP SD band thresholds ---
ENTRY_SD = 1.0
STOP_SD  = 1.5

# --- Entry filter thresholds ---
MAX_SLOPE_NORMALIZED = 0.05
MAX_ATR_RATIO        = 0.90

# --- ATR periods (on 5-min bars) ---
ATR_FAST = 3
ATR_SLOW = 14
SLOPE_LOOKBACK = 5

# --- State machine ---
COOLDOWN_BARS = 3
MAX_HOLD_BARS = 24
STALL_CHECK_BARS = 6
MIN_PROGRESS_PCT = 0.25

# --- Backtest date range ---
BACKTEST_START = "2024-01-01"
BACKTEST_END   = "2026-04-30"

# --- Logging ---
LOG_LEVEL = "INFO"
