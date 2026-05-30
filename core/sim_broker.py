import math
import config


class SimBroker:
    def shares_for_dollar_amount(self, price: float) -> int:
        """Floor divide — never over-allocate the fixed dollar amount."""
        return max(1, math.floor(config.TRADE_DOLLAR_AMOUNT / price))
