# risk_manager.py

class RiskManager:
    """
    Handles risk controls, position sizing, and safety checks
    for the trading strategy.
    """

    def __init__(self, config_manager, position_manager=None):
        self.config = config_manager
        self.position_manager = position_manager  # can be None if not needed

    def validate_trade_size(self, quantity, price):
        """
        Check that the trade size is within allowed min/max bounds and notional.
        """
        trading_cfg = self.config.get_trading_config()
        min_qty = trading_cfg.get("min_order_quantity", 0.0001)
        max_qty = trading_cfg.get("max_order_quantity", 100)
        min_notional = trading_cfg.get("min_notional", 0)
        notional = quantity * price

        if not (min_qty <= quantity <= max_qty):
            raise ValueError(f"Trade size {quantity} out of allowed bounds [{min_qty}, {max_qty}]")
        if notional < min_notional:
            raise ValueError(f"Trade notional {notional} below minimum {min_notional}")

    def check_position_limits(self, current_position):
        """
        Ensure position does not exceed configured risk limits.
        Expects current_position as dict with at least 'quantity' and 'buy_price'.
        """
        risk_cfg = self.config.get_risk_config()
        max_exposure_pct = risk_cfg.get("max_exposure_pct", 100) / 100
        total_capital = risk_cfg.get("total_capital", 10000)  # You may want to pass this dynamically

        position_value = (current_position.get("quantity", 0) * current_position.get("buy_price", 0))
        if position_value > total_capital * max_exposure_pct:
            raise ValueError(
                f"Position value ${position_value:.2f} exceeds allowed max exposure (${total_capital * max_exposure_pct:.2f})"
            )

    def calculate_max_exposure(self):
        """
        Return max allowable position value, based on config.
        """
        risk_cfg = self.config.get_risk_config()
        max_exposure_pct = risk_cfg.get("max_exposure_pct", 100) / 100
        total_capital = risk_cfg.get("total_capital", 10000)
        return total_capital * max_exposure_pct

    def emergency_stop_check(self, current_price, entry_price, threshold_pct=10):
        """
        Returns True if loss exceeds the threshold percent, otherwise False.
        """
        if entry_price == 0:
            return False
        loss_pct = 100 * (entry_price - current_price) / entry_price
        if loss_pct >= threshold_pct:
            print(f"[EMERGENCY STOP] Loss {loss_pct:.2f}% exceeds threshold ({threshold_pct}%)!")
            return True
        return False

    # Optional: you may want a global kill switch method
    def emergency_stop(self, reason="Manual stop triggered!"):
        print(f"[EMERGENCY STOP] {reason}")
        raise SystemExit
