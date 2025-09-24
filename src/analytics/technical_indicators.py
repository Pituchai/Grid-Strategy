"""
Technical indicators for grid trading strategy.
RSI, MACD, and other indicators based on YAML configuration.
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime


class TechnicalIndicators:
    """Handles technical indicator calculations from YAML configuration."""
    
    def __init__(self, config_manager, event_logger):
        self.cfg = config_manager
        self.logger = event_logger
        
        # Load technical indicator settings from YAML
        advanced_cfg = self.cfg.get_advanced_config()
        self.use_technical_indicators = advanced_cfg.get('use_technical_indicators', False)
        self.rsi_oversold = advanced_cfg.get('rsi_oversold', 30)
        self.rsi_overbought = advanced_cfg.get('rsi_overbought', 70)
        self.rsi_period = advanced_cfg.get('rsi_period', 14)
        
        # Additional indicator settings (with defaults)
        self.macd_fast_period = advanced_cfg.get('macd_fast_period', 12)
        self.macd_slow_period = advanced_cfg.get('macd_slow_period', 26)
        self.macd_signal_period = advanced_cfg.get('macd_signal_period', 9)
        
        # Bollinger Bands
        self.bb_period = advanced_cfg.get('bollinger_period', 20)
        self.bb_std_dev = advanced_cfg.get('bollinger_std_dev', 2)
        
        # Moving averages
        self.sma_short_period = advanced_cfg.get('sma_short_period', 10)
        self.sma_long_period = advanced_cfg.get('sma_long_period', 50)
        
        # Price history cache for calculations
        self.price_history = []
        self.max_history_length = 200  # Keep last 200 price points
        
        if self.use_technical_indicators:
            self.logger.log_signal("technical_indicators_enabled", {
                "rsi_oversold": self.rsi_oversold,
                "rsi_overbought": self.rsi_overbought,
                "rsi_period": self.rsi_period,
                "macd_settings": {
                    "fast": self.macd_fast_period,
                    "slow": self.macd_slow_period,
                    "signal": self.macd_signal_period
                }
            })
    
    def add_price_data(self, price: float, timestamp: datetime = None):
        """Add new price data point for indicator calculations."""
        if not self.use_technical_indicators:
            return
            
        price_point = {
            'price': price,
            'timestamp': timestamp or datetime.now()
        }
        
        self.price_history.append(price_point)
        
        # Keep only recent history
        if len(self.price_history) > self.max_history_length:
            self.price_history = self.price_history[-self.max_history_length:]
    
    def calculate_rsi(self, period: int = None) -> Optional[float]:
        """Calculate RSI (Relative Strength Index)."""
        if not self.use_technical_indicators:
            return None
            
        period = period or self.rsi_period
        if len(self.price_history) < period + 1:
            return None
            
        prices = [point['price'] for point in self.price_history[-(period + 1):]]
        deltas = np.diff(prices)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def calculate_macd(self) -> Optional[Dict[str, float]]:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        if not self.use_technical_indicators:
            return None
            
        if len(self.price_history) < self.macd_slow_period:
            return None
            
        prices = np.array([point['price'] for point in self.price_history])
        
        # Calculate EMAs
        ema_fast = self._calculate_ema(prices, self.macd_fast_period)
        ema_slow = self._calculate_ema(prices, self.macd_slow_period)
        
        if ema_fast is None or ema_slow is None:
            return None
            
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line (EMA of MACD line)
        # For simplicity, using SMA instead of EMA for signal
        if len(self.price_history) >= self.macd_slow_period + self.macd_signal_period:
            recent_macd_values = [macd_line] * self.macd_signal_period  # Simplified
            signal_line = np.mean(recent_macd_values)
            histogram = macd_line - signal_line
        else:
            signal_line = 0
            histogram = 0
        
        return {
            'macd_line': float(macd_line),
            'signal_line': float(signal_line),
            'histogram': float(histogram)
        }
    
    def _calculate_ema(self, prices: np.array, period: int) -> Optional[float]:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return None
            
        alpha = 2.0 / (period + 1)
        ema = prices[0]  # Start with first price
        
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
            
        return float(ema)
    
    def calculate_bollinger_bands(self) -> Optional[Dict[str, float]]:
        """Calculate Bollinger Bands."""
        if not self.use_technical_indicators:
            return None
            
        if len(self.price_history) < self.bb_period:
            return None
            
        prices = np.array([point['price'] for point in self.price_history[-self.bb_period:]])
        
        sma = np.mean(prices)
        std = np.std(prices)
        
        upper_band = sma + (self.bb_std_dev * std)
        lower_band = sma - (self.bb_std_dev * std)
        
        return {
            'upper_band': float(upper_band),
            'middle_band': float(sma),
            'lower_band': float(lower_band),
            'bandwidth': float(upper_band - lower_band)
        }
    
    def calculate_moving_averages(self) -> Optional[Dict[str, float]]:
        """Calculate Simple Moving Averages."""
        if not self.use_technical_indicators:
            return None
            
        result = {}
        
        if len(self.price_history) >= self.sma_short_period:
            short_prices = [point['price'] for point in self.price_history[-self.sma_short_period:]]
            result['sma_short'] = float(np.mean(short_prices))
            
        if len(self.price_history) >= self.sma_long_period:
            long_prices = [point['price'] for point in self.price_history[-self.sma_long_period:]]
            result['sma_long'] = float(np.mean(long_prices))
        
        return result if result else None
    
    def get_trading_signals(self, current_price: float) -> Dict[str, str]:
        """Generate trading signals based on technical indicators."""
        if not self.use_technical_indicators:
            return {'status': 'DISABLED', 'message': 'Technical indicators disabled in YAML config'}
        
        signals = {
            'overall_signal': 'NEUTRAL',
            'rsi_signal': 'NEUTRAL',
            'macd_signal': 'NEUTRAL',
            'bb_signal': 'NEUTRAL',
            'ma_signal': 'NEUTRAL',
            'details': {}
        }
        
        # RSI signals
        rsi = self.calculate_rsi()
        if rsi is not None:
            if rsi <= self.rsi_oversold:
                signals['rsi_signal'] = 'BUY'
            elif rsi >= self.rsi_overbought:
                signals['rsi_signal'] = 'SELL'
            
            signals['details']['rsi'] = {
                'value': rsi,
                'oversold_level': self.rsi_oversold,
                'overbought_level': self.rsi_overbought
            }
        
        # MACD signals
        macd = self.calculate_macd()
        if macd is not None:
            if macd['histogram'] > 0 and macd['macd_line'] > macd['signal_line']:
                signals['macd_signal'] = 'BUY'
            elif macd['histogram'] < 0 and macd['macd_line'] < macd['signal_line']:
                signals['macd_signal'] = 'SELL'
                
            signals['details']['macd'] = macd
        
        # Bollinger Bands signals
        bb = self.calculate_bollinger_bands()
        if bb is not None:
            if current_price <= bb['lower_band']:
                signals['bb_signal'] = 'BUY'
            elif current_price >= bb['upper_band']:
                signals['bb_signal'] = 'SELL'
                
            signals['details']['bollinger_bands'] = bb
        
        # Moving Average signals
        ma = self.calculate_moving_averages()
        if ma is not None and 'sma_short' in ma and 'sma_long' in ma:
            if ma['sma_short'] > ma['sma_long']:
                signals['ma_signal'] = 'BUY'
            elif ma['sma_short'] < ma['sma_long']:
                signals['ma_signal'] = 'SELL'
                
            signals['details']['moving_averages'] = ma
        
        # Determine overall signal (simple majority vote)
        buy_signals = sum(1 for sig in [signals['rsi_signal'], signals['macd_signal'], 
                                       signals['bb_signal'], signals['ma_signal']] if sig == 'BUY')
        sell_signals = sum(1 for sig in [signals['rsi_signal'], signals['macd_signal'], 
                                        signals['bb_signal'], signals['ma_signal']] if sig == 'SELL')
        
        if buy_signals > sell_signals:
            signals['overall_signal'] = 'BUY'
        elif sell_signals > buy_signals:
            signals['overall_signal'] = 'SELL'
        
        return signals
    
    def should_allow_trading_by_indicators(self, current_price: float, side: str) -> Tuple[bool, str]:
        """Check if trading should be allowed based on technical indicators."""
        if not self.use_technical_indicators:
            return True, "Technical indicators disabled"
        
        signals = self.get_trading_signals(current_price)
        
        # Allow trading if indicators don't strongly oppose the trade
        if side == 'BUY':
            if signals['overall_signal'] == 'SELL':
                return False, f"Technical indicators suggest SELL (RSI: {signals['rsi_signal']}, MACD: {signals['macd_signal']})"
        elif side == 'SELL':
            if signals['overall_signal'] == 'BUY':
                return False, f"Technical indicators suggest BUY (RSI: {signals['rsi_signal']}, MACD: {signals['macd_signal']})"
        
        return True, f"Technical indicators: {signals['overall_signal']}"
    
    def get_indicator_status_summary(self) -> Dict:
        """Get current status of all technical indicators."""
        if not self.use_technical_indicators:
            return {
                'enabled': False,
                'message': 'Technical indicators disabled in YAML configuration'
            }
        
        current_price = self.price_history[-1]['price'] if self.price_history else 0
        signals = self.get_trading_signals(current_price)
        
        return {
            'enabled': True,
            'price_history_length': len(self.price_history),
            'signals': signals,
            'config': {
                'rsi_oversold': self.rsi_oversold,
                'rsi_overbought': self.rsi_overbought,
                'rsi_period': self.rsi_period,
                'macd_periods': f"{self.macd_fast_period}/{self.macd_slow_period}/{self.macd_signal_period}"
            }
        }