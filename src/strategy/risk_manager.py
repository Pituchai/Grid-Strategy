# risk_manager.py
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class RiskManager:
    """
    Enhanced risk controls with comprehensive loss tracking and safety checks.
    Monitors drawdown, consecutive losses, daily limits, and emergency stops.
    """

    def __init__(self, config_manager, event_logger, position_manager=None):
        self.config = config_manager
        self.logger = event_logger
        self.position_manager = position_manager
        
        # Risk tracking
        self.daily_pnl = {}
        self.consecutive_losses = 0
        self.current_drawdown = 0.0
        self.max_drawdown_today = 0.0
        self.emergency_stop_triggered = False
        self.last_reset_date = datetime.now().date()
        
        # Load risk limits
        risk_cfg = self.config.get_risk_config()
        self.max_drawdown_pct = risk_cfg.get('max_drawdown_pct', 15.0)
        self.daily_loss_limit_pct = risk_cfg.get('daily_loss_limit_pct', 10.0)
        self.max_consecutive_losses = risk_cfg.get('max_consecutive_losses', 5)
        self.emergency_stop_enabled = risk_cfg.get('emergency_stop_enabled', True)

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

    def record_trade_result(self, pnl: float, trade_id: str = None):
        """
        Record the P&L result of a completed trade for risk monitoring.
        """
        today = datetime.now().date()
        
        # Reset daily tracking if new day
        if today != self.last_reset_date:
            self._reset_daily_tracking()
        
        # Update daily P&L
        if today not in self.daily_pnl:
            self.daily_pnl[today] = 0.0
        self.daily_pnl[today] += pnl
        
        # Track consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
            self.current_drawdown += abs(pnl)
            self.max_drawdown_today = max(self.max_drawdown_today, self.current_drawdown)
        else:
            self.consecutive_losses = 0
            self.current_drawdown = max(0, self.current_drawdown - pnl)  # Reduce drawdown by profit
        
        # Log the result
        self.logger.log_signal("trade_result_recorded", {
            "pnl": pnl,
            "trade_id": trade_id,
            "consecutive_losses": self.consecutive_losses,
            "current_drawdown": self.current_drawdown,
            "daily_pnl": self.daily_pnl[today]
        })
        
        # Check risk limits
        self._check_risk_limits()
    
    def _reset_daily_tracking(self):
        """Reset daily risk tracking for a new day."""
        self.last_reset_date = datetime.now().date()
        self.max_drawdown_today = 0.0
        # Keep consecutive losses across days for more conservative approach
        
        self.logger.log_signal("daily_risk_reset", {
            "date": self.last_reset_date.isoformat(),
            "previous_day_pnl": sum(self.daily_pnl.values()) if self.daily_pnl else 0
        })
    
    def _check_risk_limits(self):
        """
        Check all risk limits and trigger emergency stop if necessary.
        """
        alerts = []
        today = datetime.now().date()
        
        if not self.emergency_stop_enabled:
            return alerts
        
        # Check daily loss limit
        today_pnl = self.daily_pnl.get(today, 0.0)
        if today_pnl < 0:  # Only check if we have losses
            risk_cfg = self.config.get_risk_config()
            total_capital = getattr(self, 'total_capital', risk_cfg.get('total_capital', 10000))
            daily_loss_limit = total_capital * (self.daily_loss_limit_pct / 100)
            
            if abs(today_pnl) >= daily_loss_limit:
                alert = {
                    'type': 'DAILY_LOSS_LIMIT',
                    'severity': 'CRITICAL',
                    'message': f'Daily loss ${abs(today_pnl):.2f} exceeds limit ${daily_loss_limit:.2f}',
                    'action': 'EMERGENCY_STOP'
                }
                alerts.append(alert)
                self._trigger_emergency_stop("Daily loss limit exceeded", alert)
        
        # Check maximum drawdown
        if self.current_drawdown > 0:
            risk_cfg = self.config.get_risk_config()
            total_capital = getattr(self, 'total_capital', risk_cfg.get('total_capital', 10000))
            max_drawdown_limit = total_capital * (self.max_drawdown_pct / 100)
            
            if self.current_drawdown >= max_drawdown_limit:
                alert = {
                    'type': 'MAX_DRAWDOWN',
                    'severity': 'CRITICAL', 
                    'message': f'Drawdown ${self.current_drawdown:.2f} exceeds limit ${max_drawdown_limit:.2f}',
                    'action': 'EMERGENCY_STOP'
                }
                alerts.append(alert)
                self._trigger_emergency_stop("Maximum drawdown exceeded", alert)
        
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            alert = {
                'type': 'CONSECUTIVE_LOSSES',
                'severity': 'HIGH',
                'message': f'{self.consecutive_losses} consecutive losses (limit: {self.max_consecutive_losses})',
                'action': 'PAUSE_TRADING'
            }
            alerts.append(alert)
            # Don't emergency stop, just alert for consecutive losses
            
        # Log alerts
        for alert in alerts:
            self.logger.log_signal("risk_alert", alert)
            
        return alerts
    
    def _trigger_emergency_stop(self, reason: str, alert_data: dict = None):
        """
        Trigger emergency stop with comprehensive logging.
        """
        if self.emergency_stop_triggered:
            return  # Already triggered
            
        self.emergency_stop_triggered = True
        
        self.logger.log_signal("emergency_stop_triggered", {
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "daily_pnl": self.daily_pnl,
            "consecutive_losses": self.consecutive_losses,
            "current_drawdown": self.current_drawdown,
            "alert_data": alert_data
        })
        
        print(f"\n🚨 EMERGENCY STOP TRIGGERED! 🚨")
        print(f"Reason: {reason}")
        print(f"Time: {datetime.now().isoformat()}")
        if alert_data:
            print(f"Details: {alert_data['message']}")
        print(f"All trading has been halted for safety!")
        
        # In a real implementation, you would cancel all open orders here
        # and potentially close positions depending on your strategy
        
        raise SystemExit(f"Emergency stop: {reason}")
    
    def check_trade_allowed(self) -> tuple[bool, str]:
        """
        Check if new trades are allowed based on current risk status.
        Returns (allowed: bool, reason: str)
        """
        if self.emergency_stop_triggered:
            return False, "Emergency stop is active"
        
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, f"Too many consecutive losses ({self.consecutive_losses})"
        
        # Check daily loss limit
        today = datetime.now().date()
        if today != self.last_reset_date:
            self._reset_daily_tracking()
            
        today_pnl = self.daily_pnl.get(today, 0.0)
        if today_pnl < 0:
            risk_cfg = self.config.get_risk_config()
            total_capital = getattr(self, 'total_capital', risk_cfg.get('total_capital', 10000))
            daily_loss_limit = total_capital * (self.daily_loss_limit_pct / 100)
            
            if abs(today_pnl) >= daily_loss_limit * 0.8:  # 80% of limit as warning
                return False, f"Approaching daily loss limit (${abs(today_pnl):.2f}/${daily_loss_limit:.2f})"
        
        return True, "Trading allowed"
    
    def get_risk_status(self) -> Dict:
        """
        Get comprehensive risk status report.
        """
        today = datetime.now().date()
        today_pnl = self.daily_pnl.get(today, 0.0)
        
        risk_cfg = self.config.get_risk_config()
        total_capital = getattr(self, 'total_capital', risk_cfg.get('total_capital', 10000))
        
        return {
            'emergency_stop_active': self.emergency_stop_triggered,
            'consecutive_losses': self.consecutive_losses,
            'max_consecutive_allowed': self.max_consecutive_losses,
            'current_drawdown': self.current_drawdown,
            'max_drawdown_limit': total_capital * (self.max_drawdown_pct / 100),
            'daily_pnl': today_pnl,
            'daily_loss_limit': total_capital * (self.daily_loss_limit_pct / 100),
            'max_drawdown_today': self.max_drawdown_today,
            'trading_allowed': self.check_trade_allowed()[0],
            'risk_pct_used': {
                'drawdown': (self.current_drawdown / (total_capital * (self.max_drawdown_pct / 100))) * 100,
                'daily_loss': (abs(today_pnl) / (total_capital * (self.daily_loss_limit_pct / 100))) * 100 if today_pnl < 0 else 0
            }
        }

    def set_total_capital(self, capital: float):
        """Set the total capital for risk calculations."""
        self.total_capital = capital

    def emergency_stop(self, reason="Manual stop triggered!"):
        """Manual emergency stop."""
        self._trigger_emergency_stop(reason)
