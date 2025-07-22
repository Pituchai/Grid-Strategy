from datetime import datetime

class PositionManager:
    """
    Manages positions, P&L, and trade tracking.
    Logs all trades using EventLogger.
    """

    def __init__(self, event_logger):
        self.logger = event_logger
        self.positions = []  # Each item: {'buy_price', 'quantity', 'timestamp'}
        self.closed_positions = []  # Track closed for history
        self.current_position = None

    def track_position(self, buy_price, quantity, timestamp=None):
        """Open a new position (buy)."""
        timestamp = timestamp or datetime.now().isoformat()
        self.current_position = {
            "buy_price": buy_price,
            "quantity": quantity,
            "timestamp": timestamp
        }
        self.positions.append(self.current_position.copy())
        # Log the trade
        self.logger.log_trade({
            "symbol": "",
            "side": "buy",
            "qty": quantity,
            "price": buy_price,
            "timestamp": timestamp
        })

    def update_position(self, action, price, quantity, timestamp=None):
        """Update the current position (action='buy' or 'sell')."""
        timestamp = timestamp or datetime.now().isoformat()
        if action == "buy":
            # Add to the position (averaging down)
            if self.current_position:
                total_qty = self.current_position["quantity"] + quantity
                avg_price = ((self.current_position["buy_price"] * self.current_position["quantity"]) + (price * quantity)) / total_qty
                self.current_position["buy_price"] = avg_price
                self.current_position["quantity"] = total_qty
            else:
                self.track_position(price, quantity, timestamp)
            self.logger.log_trade({
                "symbol": "",
                "side": "buy",
                "qty": quantity,
                "price": price,
                "timestamp": timestamp
            })
        elif action == "sell":
            # Close or reduce position
            if not self.current_position or self.current_position["quantity"] < quantity:
                raise ValueError("Not enough position to sell.")
            pnl = (price - self.current_position["buy_price"]) * quantity
            self.logger.log_trade({
                "symbol": "",
                "side": "sell",
                "qty": quantity,
                "price": price,
                "timestamp": timestamp,
                "pnl": pnl
            })
            self.current_position["quantity"] -= quantity
            if self.current_position["quantity"] == 0:
                # Move to closed positions
                self.closed_positions.append(self.current_position.copy())
                self.current_position = None
        else:
            raise ValueError("Action must be 'buy' or 'sell'")

    def calculate_pnl(self, current_price=None):
        """Calculate realized and unrealized P&L."""
        realized = 0
        for pos in self.closed_positions:
            pnl = (pos.get("sell_price", pos["buy_price"]) - pos["buy_price"]) * pos["quantity"]
            realized += pnl
        unrealized = 0
        if self.current_position and current_price is not None:
            unrealized = (current_price - self.current_position["buy_price"]) * self.current_position["quantity"]
        return {"realized": realized, "unrealized": unrealized}

    def get_position_summary(self):
        """Return current and closed positions summary."""
        return {
            "current_position": self.current_position,
            "closed_positions": self.closed_positions
        }

    def reset_position(self):
        """Reset all position tracking (danger: clears history)."""
        self.positions = []
        self.closed_positions = []
        self.current_position = None
