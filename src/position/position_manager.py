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
        """Open a new position (buy). Use buy() method instead for consistency."""
        # Deprecated: Use buy() method for consistency
        self.buy(quantity, buy_price, timestamp)

    def update_position(self, action, price, quantity, timestamp=None):
        """Update the current position. Use buy()/sell() methods instead for consistency."""
        # Deprecated: Use buy() and sell() methods directly
        if action == "buy":
            self.buy(quantity, price, timestamp)
        elif action == "sell":
            self.sell(quantity, price, timestamp)
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

    def buy(self, quantity, price, timestamp=None):
        """Execute a buy order and update position."""
        timestamp = timestamp or datetime.now().isoformat()
        
        # Add to the position (averaging down)
        if self.current_position:
            total_qty = self.current_position["quantity"] + quantity
            avg_price = ((self.current_position["buy_price"] * self.current_position["quantity"]) + (price * quantity)) / total_qty
            self.current_position["buy_price"] = avg_price
            self.current_position["quantity"] = total_qty
        else:
            # Create new position
            self.current_position = {
                "buy_price": price,
                "quantity": quantity,
                "timestamp": timestamp
            }
            self.positions.append(self.current_position.copy())
        
        # Log the trade
        self.logger.log_trade({
            "symbol": "",
            "side": "buy",
            "qty": quantity,
            "price": price,
            "timestamp": timestamp
        })
    
    def sell(self, quantity, price, timestamp=None):
        """Execute a sell order and update position."""
        timestamp = timestamp or datetime.now().isoformat()
        
        # Close or reduce position
        if not self.current_position or self.current_position["quantity"] < quantity:
            raise ValueError("Not enough position to sell.")
        
        pnl = (price - self.current_position["buy_price"]) * quantity
        
        # Log the trade
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

    def reset_position(self):
        """Reset all position tracking (danger: clears history)."""
        self.positions = []
        self.closed_positions = []
        self.current_position = None
