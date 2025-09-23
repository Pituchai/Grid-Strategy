#!/usr/bin/env python3
"""
Volatility-Based Grid Management

Conservative volatility detection and grid spacing adjustment for risk management.
Focuses on protecting the grid strategy during extreme market conditions.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta


class VolatilityManager:
    """
    Conservative volatility-based regime detection for grid trading.
    Adjusts grid spacing and position sizes based on market volatility,
    without trying to predict direction.
    """
    
    def __init__(self, config_manager=None, event_logger=None):
        self.cfg = config_manager
        self.logger = event_logger
        
        # Volatility thresholds (conservative)
        self.volatility_thresholds = {
            'very_low': 0.015,    # 1.5% daily volatility
            'low': 0.025,         # 2.5% daily volatility  
            'normal': 0.040,      # 4.0% daily volatility
            'high': 0.060,        # 6.0% daily volatility
            'very_high': 0.080    # 8.0% daily volatility
        }
        
        # Grid spacing multipliers
        self.spacing_multipliers = {
            'very_low': 0.7,      # Tighter spacing in calm markets
            'low': 0.85,          # Slightly tighter
            'normal': 1.0,        # Normal spacing
            'high': 1.3,          # Wider spacing in volatile markets
            'very_high': 1.6      # Much wider spacing in chaos
        }
        
        # Position size multipliers  
        self.position_multipliers = {
            'very_low': 1.1,      # Slightly larger positions when safe
            'low': 1.0,           # Normal positions
            'normal': 1.0,        # Normal positions
            'high': 0.8,          # Smaller positions when risky
            'very_high': 0.6      # Much smaller positions in chaos
        }
        
        # History for trend analysis
        self.volatility_history = []
        self.price_history = []
        
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range (ATR) for volatility measurement."""
        if len(df) < period + 1:
            return 0.0
        
        # Calculate True Range
        df = df.copy()
        df['prev_close'] = df['close'].shift(1)
        
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        
        df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # Calculate ATR (Simple Moving Average of True Range)
        atr = df['true_range'].rolling(window=period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else 0.0
    
    def calculate_volatility_ratio(self, df: pd.DataFrame) -> float:
        """Calculate volatility ratio (ATR / Current Price)."""
        if df.empty:
            return 0.0
        
        current_price = df['close'].iloc[-1]
        atr = self.calculate_atr(df, period=14)
        
        if current_price <= 0:
            return 0.0
        
        volatility_ratio = atr / current_price
        return volatility_ratio
    
    def classify_volatility_regime(self, volatility_ratio: float) -> str:
        """Classify market volatility into regimes."""
        thresholds = self.volatility_thresholds
        
        if volatility_ratio >= thresholds['very_high']:
            return 'very_high'
        elif volatility_ratio >= thresholds['high']:
            return 'high'
        elif volatility_ratio >= thresholds['normal']:
            return 'normal'
        elif volatility_ratio >= thresholds['low']:
            return 'low'
        else:
            return 'very_low'
    
    def get_adjusted_grid_params(self, base_spacing_pct: float, 
                                base_position_size: float, 
                                df: pd.DataFrame) -> Dict[str, float]:
        """Get volatility-adjusted grid parameters."""
        
        # Calculate current volatility
        volatility_ratio = self.calculate_volatility_ratio(df)
        regime = self.classify_volatility_regime(volatility_ratio)
        
        # Get multipliers
        spacing_multiplier = self.spacing_multipliers[regime]
        position_multiplier = self.position_multipliers[regime]
        
        # Calculate adjusted parameters
        adjusted_spacing = base_spacing_pct * spacing_multiplier
        adjusted_position_size = base_position_size * position_multiplier
        
        # Store history
        self.volatility_history.append({
            'timestamp': datetime.now(),
            'volatility_ratio': volatility_ratio,
            'regime': regime,
            'spacing_multiplier': spacing_multiplier,
            'position_multiplier': position_multiplier
        })
        
        # Keep only last 100 records
        if len(self.volatility_history) > 100:
            self.volatility_history.pop(0)
        
        # Log the adjustment
        if self.logger:
            self.logger.log_signal("volatility_adjustment", {
                "volatility_ratio": volatility_ratio,
                "regime": regime,
                "original_spacing_pct": base_spacing_pct,
                "adjusted_spacing_pct": adjusted_spacing,
                "spacing_multiplier": spacing_multiplier,
                "position_multiplier": position_multiplier,
                "atr_value": self.calculate_atr(df, 14),
                "current_price": df['close'].iloc[-1] if not df.empty else 0
            })
        
        return {
            'adjusted_spacing_pct': adjusted_spacing,
            'adjusted_position_size': adjusted_position_size,
            'volatility_ratio': volatility_ratio,
            'regime': regime,
            'spacing_multiplier': spacing_multiplier,
            'position_multiplier': position_multiplier
        }
    
    def should_pause_trading(self, df: pd.DataFrame) -> Dict[str, bool]:
        """Conservative check for extreme conditions requiring trading pause."""
        if df.empty:
            return {'pause_all': False, 'pause_buys': False, 'pause_sells': False}
        
        volatility_ratio = self.calculate_volatility_ratio(df)
        
        # Only pause in EXTREME conditions
        pause_all = volatility_ratio > 0.12  # 12% daily volatility (black swan events)
        
        # Check for rapid price movement (gap detection)
        if len(df) >= 2:
            current_price = df['close'].iloc[-1]
            prev_price = df['close'].iloc[-2]
            price_change_pct = abs(current_price - prev_price) / prev_price
            
            # Pause if single-period move > 5%
            if price_change_pct > 0.05:
                pause_all = True
        
        result = {
            'pause_all': pause_all,
            'pause_buys': False,  # Conservative: don't pause individual sides
            'pause_sells': False,
            'reason': f'extreme_volatility_{volatility_ratio:.4f}' if pause_all else None
        }
        
        if pause_all and self.logger:
            self.logger.log_signal("trading_paused", {
                "volatility_ratio": volatility_ratio,
                "reason": "extreme_market_conditions",
                "threshold_exceeded": "12% daily volatility"
            })
        
        return result
    
    def get_volatility_summary(self) -> Dict[str, any]:
        """Get summary of recent volatility data."""
        if not self.volatility_history:
            return {'status': 'no_data'}
        
        recent = self.volatility_history[-10:]  # Last 10 readings
        
        avg_volatility = np.mean([r['volatility_ratio'] for r in recent])
        current_regime = recent[-1]['regime'] if recent else 'unknown'
        regime_stability = len(set(r['regime'] for r in recent))  # Lower = more stable
        
        return {
            'current_regime': current_regime,
            'avg_volatility_ratio': avg_volatility,
            'regime_stability': regime_stability,
            'readings_count': len(recent),
            'current_spacing_multiplier': recent[-1]['spacing_multiplier'] if recent else 1.0,
            'current_position_multiplier': recent[-1]['position_multiplier'] if recent else 1.0,
            'status': 'active'
        }
    
    def get_regime_description(self, regime: str) -> str:
        """Get human-readable description of volatility regime."""
        descriptions = {
            'very_low': '🟢 Very Low Volatility - Calm markets, tighter grids',
            'low': '🟡 Low Volatility - Stable conditions, slightly tighter grids', 
            'normal': '⚪ Normal Volatility - Standard grid operation',
            'high': '🟠 High Volatility - Wider grids, smaller positions',
            'very_high': '🔴 Very High Volatility - Much wider grids, reduced exposure'
        }
        return descriptions.get(regime, '❓ Unknown volatility regime')


# Utility function for easy integration
def get_volatility_adjusted_params(df: pd.DataFrame, base_spacing: float, 
                                 base_position: float, config_manager=None, 
                                 logger=None) -> Dict[str, float]:
    """Convenience function to get volatility-adjusted parameters."""
    vm = VolatilityManager(config_manager, logger)
    return vm.get_adjusted_grid_params(base_spacing, base_position, df)


if __name__ == "__main__":
    # Example usage with dummy data
    import matplotlib.pyplot as plt
    
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=100, freq='H')
    np.random.seed(42)
    
    # Simulate price data with varying volatility
    price_data = []
    price = 50000
    
    for i in range(100):
        # Simulate different volatility periods
        if i < 30:
            volatility = 0.002  # Low vol
        elif i < 60:
            volatility = 0.008  # High vol  
        else:
            volatility = 0.004  # Normal vol
            
        change = np.random.normal(0, volatility)
        price *= (1 + change)
        price_data.append(price)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': price_data,
        'high': [p * 1.01 for p in price_data],
        'low': [p * 0.99 for p in price_data],
        'close': price_data,
        'volume': [1000] * 100
    })
    
    # Test volatility manager
    vm = VolatilityManager()
    
    print("🧪 Testing Volatility Manager")
    print("=" * 40)
    
    # Test different periods
    for period in [30, 60, 90]:
        test_df = df.iloc[:period]
        params = vm.get_adjusted_grid_params(0.5, 1000, test_df)
        
        print(f"\nPeriod {period}:")
        print(f"  Regime: {params['regime']}")
        print(f"  Volatility Ratio: {params['volatility_ratio']:.4f}")
        print(f"  Adjusted Spacing: {params['adjusted_spacing_pct']:.3f}%")
        print(f"  Position Multiplier: {params['position_multiplier']:.2f}")