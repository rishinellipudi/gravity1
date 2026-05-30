import sys
from pathlib import Path
from loguru import logger
import config

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logger(session_date: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    logger.add(
        LOG_DIR / f"{session_date}.log",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",
    )
