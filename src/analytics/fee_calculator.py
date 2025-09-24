"""
Fee calculation and optimization based on YAML configuration.
Handles maker/taker fees, discounts, and optimization strategies.
"""
from typing import Dict, Tuple, Optional
from datetime import datetime


class FeeCalculator:
    """Handles fee calculations and optimization from YAML configuration."""
    
    def __init__(self, config_manager, event_logger):
        self.cfg = config_manager
        self.logger = event_logger
        
        # Load fee configuration from YAML
        fees_cfg = self.cfg.get_fees_config()
        self.maker_fee_pct = fees_cfg.get('maker_fee_pct', 0.1) / 100
        self.taker_fee_pct = fees_cfg.get('taker_fee_pct', 0.1) / 100
        self.use_fee_discount = fees_cfg.get('use_fee_discount', False)
        self.fee_discount_pct = fees_cfg.get('fee_discount_pct', 0.0) / 100
        self.min_fee_balance = fees_cfg.get('min_fee_balance', 0.0)
        self.include_fees_in_calculation = fees_cfg.get('include_fees_in_calculation', True)
        
        # Fee tracking
        self.total_fees_paid = 0.0
        self.total_fee_savings = 0.0
        self.fee_payments_count = 0
        
        self.logger.log_signal("fee_calculator_initialized", {
            "maker_fee_pct": self.maker_fee_pct * 100,
            "taker_fee_pct": self.taker_fee_pct * 100,
            "use_fee_discount": self.use_fee_discount,
            "fee_discount_pct": self.fee_discount_pct * 100,
            "include_fees_in_calculation": self.include_fees_in_calculation
        })
    
    def calculate_order_fee(self, order_value: float, order_type: str = 'LIMIT', 
                           fee_asset: str = 'USDT') -> Dict[str, float]:
        """Calculate fee for a trading order based on YAML configuration."""
        # Determine base fee rate
        if order_type in ['LIMIT', 'LIMIT_MAKER']:
            base_fee_rate = self.maker_fee_pct
            fee_type = 'MAKER'
        else:  # MARKET, STOP_LOSS, etc.
            base_fee_rate = self.taker_fee_pct
            fee_type = 'TAKER'
        
        # Calculate base fee
        base_fee = order_value * base_fee_rate
        
        # Apply discount if enabled
        if self.use_fee_discount:
            discount_amount = base_fee * self.fee_discount_pct
            final_fee = base_fee - discount_amount
            fee_savings = discount_amount
        else:
            final_fee = base_fee
            fee_savings = 0.0
        
        return {
            'base_fee': base_fee,
            'final_fee': final_fee,
            'fee_savings': fee_savings,
            'fee_rate': base_fee_rate,
            'fee_type': fee_type,
            'fee_asset': fee_asset,
            'order_value': order_value,
            'discount_applied': self.use_fee_discount
        }
    
    def calculate_grid_order_fees(self, grid_levels: list, current_price: float, 
                                 base_quantity: float) -> Dict:
        """Calculate total fees for all potential grid orders."""
        total_buy_fees = 0.0
        total_sell_fees = 0.0
        buy_orders_count = 0
        sell_orders_count = 0
        
        for level in grid_levels:
            order_value = level['price'] * base_quantity
            fee_info = self.calculate_order_fee(order_value, 'LIMIT')
            
            if level['side'] == 'BUY':
                total_buy_fees += fee_info['final_fee']
                buy_orders_count += 1
            else:  # SELL
                total_sell_fees += fee_info['final_fee']
                sell_orders_count += 1
        
        total_fees = total_buy_fees + total_sell_fees
        
        return {
            'total_fees': total_fees,
            'total_buy_fees': total_buy_fees,
            'total_sell_fees': total_sell_fees,
            'buy_orders_count': buy_orders_count,
            'sell_orders_count': sell_orders_count,
            'avg_fee_per_order': total_fees / len(grid_levels) if grid_levels else 0,
            'fees_as_pct_of_capital': 0  # Will be calculated by caller
        }
    
    def record_fee_payment(self, fee_amount: float, fee_asset: str = 'USDT', 
                          order_type: str = 'LIMIT'):
        """Record a fee payment for tracking and analysis."""
        self.total_fees_paid += fee_amount
        self.fee_payments_count += 1
        
        # Calculate savings if discount is applied
        if self.use_fee_discount:
            # Reverse calculate what the fee would have been without discount
            original_fee = fee_amount / (1 - self.fee_discount_pct)
            savings = original_fee - fee_amount
            self.total_fee_savings += savings
        
        self.logger.log_signal("fee_payment_recorded", {
            "fee_amount": fee_amount,
            "fee_asset": fee_asset,
            "order_type": order_type,
            "total_fees_paid": self.total_fees_paid,
            "total_fee_savings": self.total_fee_savings,
            "payments_count": self.fee_payments_count
        })
    
    def calculate_net_profit_with_fees(self, gross_profit: float, 
                                      trade_fees: float) -> Dict[str, float]:
        """Calculate net profit including fees based on YAML settings."""
        if not self.include_fees_in_calculation:
            return {
                'net_profit': gross_profit,
                'fees_deducted': 0.0,
                'fees_included': False,
                'message': 'Fee inclusion disabled in YAML config'
            }
        
        net_profit = gross_profit - trade_fees
        
        return {
            'net_profit': net_profit,
            'fees_deducted': trade_fees,
            'fees_included': True,
            'gross_profit': gross_profit,
            'fee_impact_pct': (trade_fees / gross_profit * 100) if gross_profit > 0 else 0
        }
    
    def optimize_order_type_for_fees(self, current_price: float, 
                                   target_price: float, side: str) -> str:
        """Suggest optimal order type to minimize fees."""
        price_difference_pct = abs(current_price - target_price) / current_price * 100
        
        # If we can use LIMIT orders (not immediate execution needed)
        if price_difference_pct > 0.1:  # More than 0.1% away from current price
            return 'LIMIT'  # Use maker fee (usually lower)
        else:
            # Too close to current price, might need market order
            if self.maker_fee_pct <= self.taker_fee_pct:
                return 'LIMIT'  # Still try for maker fee
            else:
                return 'MARKET'  # Use market order if taker fee is better
    
    def get_fee_optimization_recommendations(self, trading_volume_24h: float = 0) -> Dict:
        """Get recommendations for fee optimization based on YAML config and trading volume."""
        recommendations = {
            'current_config': {
                'maker_fee': f"{self.maker_fee_pct * 100:.3f}%",
                'taker_fee': f"{self.taker_fee_pct * 100:.3f}%",
                'discount_enabled': self.use_fee_discount,
                'discount_rate': f"{self.fee_discount_pct * 100:.1f}%"
            },
            'recommendations': [],
            'potential_savings': 0.0
        }
        
        # Recommendation 1: Prefer LIMIT orders for lower fees
        if self.maker_fee_pct < self.taker_fee_pct:
            savings_pct = ((self.taker_fee_pct - self.maker_fee_pct) / self.taker_fee_pct) * 100
            recommendations['recommendations'].append({
                'type': 'ORDER_TYPE',
                'suggestion': 'Use LIMIT orders instead of MARKET orders when possible',
                'potential_savings': f"{savings_pct:.1f}% on fees",
                'implementation': 'Grid strategy already uses LIMIT orders by default'
            })
        
        # Recommendation 2: Fee discount optimization
        if not self.use_fee_discount and self.fee_discount_pct > 0:
            recommendations['recommendations'].append({
                'type': 'DISCOUNT',
                'suggestion': 'Enable fee discount if you meet the requirements',
                'potential_savings': f"{self.fee_discount_pct * 100:.1f}% fee reduction",
                'implementation': 'Set use_fee_discount: true in YAML config'
            })
        
        # Recommendation 3: Volume-based fee tiers
        if trading_volume_24h > 100000:  # High volume threshold
            recommendations['recommendations'].append({
                'type': 'VOLUME_TIER',
                'suggestion': 'Consider VIP fee tiers for high volume trading',
                'potential_savings': 'Up to 50% fee reduction',
                'implementation': 'Contact exchange for VIP account status'
            })
        
        return recommendations
    
    def get_fee_analysis_summary(self) -> Dict:
        """Get comprehensive fee analysis based on current settings and history."""
        return {
            'configuration': {
                'maker_fee_pct': self.maker_fee_pct * 100,
                'taker_fee_pct': self.taker_fee_pct * 100,
                'use_fee_discount': self.use_fee_discount,
                'fee_discount_pct': self.fee_discount_pct * 100,
                'include_fees_in_calculation': self.include_fees_in_calculation
            },
            'fee_tracking': {
                'total_fees_paid': self.total_fees_paid,
                'total_fee_savings': self.total_fee_savings,
                'fee_payments_count': self.fee_payments_count,
                'avg_fee_per_trade': self.total_fees_paid / max(self.fee_payments_count, 1)
            },
            'optimization': {
                'maker_vs_taker_difference': (self.taker_fee_pct - self.maker_fee_pct) * 100,
                'discount_active': self.use_fee_discount,
                'effective_maker_rate': (self.maker_fee_pct * (1 - self.fee_discount_pct)) * 100 if self.use_fee_discount else self.maker_fee_pct * 100
            }
        }
    
    def estimate_daily_fees(self, daily_trading_volume: float, 
                           maker_ratio: float = 0.8) -> Dict[str, float]:
        """Estimate daily fees based on expected trading volume and maker/taker ratio."""
        maker_volume = daily_trading_volume * maker_ratio
        taker_volume = daily_trading_volume * (1 - maker_ratio)
        
        base_maker_fees = maker_volume * self.maker_fee_pct
        base_taker_fees = taker_volume * self.taker_fee_pct
        base_total_fees = base_maker_fees + base_taker_fees
        
        if self.use_fee_discount:
            discount_amount = base_total_fees * self.fee_discount_pct
            final_total_fees = base_total_fees - discount_amount
        else:
            discount_amount = 0.0
            final_total_fees = base_total_fees
        
        return {
            'daily_trading_volume': daily_trading_volume,
            'maker_volume': maker_volume,
            'taker_volume': taker_volume,
            'base_total_fees': base_total_fees,
            'discount_amount': discount_amount,
            'final_total_fees': final_total_fees,
            'fees_as_pct_of_volume': (final_total_fees / daily_trading_volume * 100) if daily_trading_volume > 0 else 0,
            'maker_ratio': maker_ratio
        }