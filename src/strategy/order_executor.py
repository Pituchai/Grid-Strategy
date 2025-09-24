"""
Order execution logic.
Extracted from GridStrategyController for better organization.
"""
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.trade_persistence import TradePersistence


class OrderExecutor:
    """Handles order execution and grid level tracking."""
    
    def __init__(self, config_manager, event_logger, position_manager, client, risk_manager=None):
        self.cfg = config_manager
        self.logger = event_logger
        self.pm = position_manager
        self.client = client
        self.risk_manager = risk_manager
        
        # Grid level tracking - centralized here
        self.bought_levels = set()  # Track bought grid levels by level number
        self.sold_levels = set()    # Track sold grid levels by (level, price) tuple
        
        # Initialize trade persistence
        self.trade_persistence = TradePersistence(self.cfg, self.logger)
        
    def execute_buy_orders(self, grid_levels, current_price):
        """Execute buy orders when price hits grid levels."""
        trading_cfg = self.cfg.get_trading_config()
        symbol = trading_cfg.get('symbol', 'BTCUSDT')
        base_currency = trading_cfg.get('base_currency', 'BTC')
        quote_currency = trading_cfg.get('quote_currency', 'USDT')
        base_quantity = trading_cfg.get('base_order_quantity', 0.001)
        
        # Validate symbol matches currencies
        expected_symbol = f"{base_currency}{quote_currency}"
        if symbol != expected_symbol:
            self.logger.log_signal("symbol_currency_mismatch", {
                "symbol": symbol,
                "expected": expected_symbol,
                "base_currency": base_currency,
                "quote_currency": quote_currency
            })
        
        executed_orders = []
        
        for level in grid_levels:
            if (level['side'] == 'BUY' and 
                current_price <= level['price'] and 
                level['level'] not in self.bought_levels):
                
                try:
                    # Check if testnet mode or simulation
                    api_cfg = self.cfg.get_api_config()
                    is_testnet = api_cfg.get('testnet', True)
                    
                    if is_testnet:
                        # Simulate the buy order
                        print(f"🧪 [TESTNET BUY] Level {level['level']} @ ${level['price']:,.2f}")
                        order_result = {
                            'orderId': f"SIM_{level['level']}_{int(current_price)}",
                            'status': 'FILLED',
                            'executedQty': str(base_quantity),
                            'fills': [{'price': str(level['price']), 'qty': str(base_quantity)}]
                        }
                    else:
                        # Real buy order using config settings
                        print(f"💰 [LIVE BUY] Level {level['level']} @ ${level['price']:,.2f}")
                        
                        # Use order settings from YAML config
                        order_type = trading_cfg.get('order_type', 'LIMIT')
                        time_in_force = trading_cfg.get('time_in_force', 'GTC')
                        
                        if order_type == 'MARKET':
                            order_result = self.client.order_market_buy(
                                symbol=symbol,
                                quantity=base_quantity
                            )
                        else:  # LIMIT order
                            order_result = self.client.create_order(
                                symbol=symbol,
                                side='BUY',
                                type=order_type,
                                timeInForce=time_in_force,
                                quantity=base_quantity,
                                price=f"{level['price']:.2f}"
                            )
                    
                    if order_result.get('status') == 'FILLED':
                        # Update position via position manager (single source of truth)
                        self.pm.buy(base_quantity, level['price'], timestamp=datetime.now())
                        
                        # Track bought level
                        self.bought_levels.add(level['level'])
                        
                        # Set total capital in Risk Manager for proper calculations
                        if self.risk_manager and hasattr(self.cfg, 'total_capital'):
                            self.risk_manager.set_total_capital(getattr(self.cfg, 'total_capital', 10000))
                        
                        # Calculate fees using fee calculator if available
                        trade_value = level['price'] * base_quantity
                        calculated_fee = 0.0
                        if hasattr(self, 'fee_calculator') and self.fee_calculator:
                            fee_info = self.fee_calculator.calculate_order_fee(trade_value, 'LIMIT')
                            calculated_fee = fee_info['final_fee']
                            # Record fee payment for tracking
                            self.fee_calculator.record_fee_payment(calculated_fee, 'USDT', 'LIMIT')
                        
                        # Log the trade
                        trade_data = {
                            'symbol': symbol,
                            'side': 'BUY',
                            'quantity': base_quantity,
                            'price': level['price'],
                            'order_id': order_result.get('orderId'),
                            'grid_level': level['level'],
                            'timestamp': datetime.now().isoformat(),
                            'trade_type': 'GRID',
                            'pnl': 0  # No P&L on buy orders
                        }
                        
                        self.logger.log_trade(trade_data)
                        
                        # Save trade to persistence system (CSV export)
                        self.trade_persistence.save_trade(trade_data)
                        
                        executed_orders.append({
                            'level': level,
                            'side': 'BUY',
                            'order_result': order_result
                        })
                        
                        print(f"   ✅ BUY executed - Level {level['level']}")
                        
                except Exception as e:
                    self.logger.log_error(f"Buy order failed at level {level['level']}", {
                        'level': level['level'],
                        'price': level['price'],
                        'error': str(e)
                    })
                    print(f"   ❌ BUY failed: {e}")
        
        return executed_orders

    def execute_sell_orders(self, grid_levels, current_price, cycle_tracker=None):
        """Execute sell orders when price hits grid levels."""
        trading_cfg = self.cfg.get_trading_config()
        symbol = trading_cfg.get('symbol', 'BTCUSDT')
        base_quantity = trading_cfg.get('base_order_quantity', 0.001)
        
        executed_orders = []
        
        for level in grid_levels:
            if (level['side'] == 'SELL' and 
                current_price >= level['price'] and 
                (level['level'], level['price']) not in self.sold_levels):
                
                # Check if we have position to sell
                current_position = self.pm.get_position_summary().get('current_position')
                if not current_position or current_position.get('quantity', 0) < base_quantity:
                    print(f"   ⚠️  Insufficient position to sell at level {level['level']}")
                    continue
                
                try:
                    # Check if testnet mode or simulation
                    api_cfg = self.cfg.get_api_config()
                    is_testnet = api_cfg.get('testnet', True)
                    
                    if is_testnet:
                        # Simulate the sell order
                        print(f"🧪 [TESTNET SELL] Level {level['level']} @ ${level['price']:,.2f}")
                        order_result = {
                            'orderId': f"SIM_{level['level']}_{int(current_price)}",
                            'status': 'FILLED',
                            'executedQty': str(base_quantity),
                            'fills': [{'price': str(level['price']), 'qty': str(base_quantity)}]
                        }
                    else:
                        # Real sell order using config settings
                        print(f"💰 [LIVE SELL] Level {level['level']} @ ${level['price']:,.2f}")
                        
                        # Use order settings from YAML config
                        order_type = trading_cfg.get('order_type', 'LIMIT')
                        time_in_force = trading_cfg.get('time_in_force', 'GTC')
                        
                        if order_type == 'MARKET':
                            order_result = self.client.order_market_sell(
                                symbol=symbol,
                                quantity=base_quantity
                            )
                        else:  # LIMIT order
                            order_result = self.client.create_order(
                                symbol=symbol,
                                side='SELL',
                                type=order_type,
                                timeInForce=time_in_force,
                                quantity=base_quantity,
                                price=f"{level['price']:.2f}"
                            )
                    
                    if order_result.get('status') == 'FILLED':
                        # Update position via position manager (single source of truth)
                        self.pm.sell(base_quantity, level['price'], timestamp=datetime.now())
                        
                        # Calculate P&L for risk tracking
                        current_position = self.pm.get_position_summary().get('current_position')
                        if current_position:
                            buy_price = current_position.get('buy_price', level['price'])
                            pnl = (level['price'] - buy_price) * base_quantity
                            
                            # Record trade result with Risk Manager
                            if self.risk_manager:
                                trade_id = f"SELL_{level['level']}_{order_result.get('orderId')}"
                                self.risk_manager.record_trade_result(pnl, trade_id)
                                print(f"   💰 P&L: ${pnl:.2f} (Buy: ${buy_price:.2f} → Sell: ${level['price']:.2f})")
                        
                        # Track sold level
                        self.sold_levels.add((level['level'], level['price']))
                        
                        # Calculate fees using fee calculator if available
                        trade_value = level['price'] * base_quantity
                        calculated_fee = 0.0
                        if hasattr(self, 'fee_calculator') and self.fee_calculator:
                            fee_info = self.fee_calculator.calculate_order_fee(trade_value, 'LIMIT')
                            calculated_fee = fee_info['final_fee']
                            # Record fee payment for tracking
                            self.fee_calculator.record_fee_payment(calculated_fee, 'USDT', 'LIMIT')
                            
                            # Adjust P&L calculation to include fees if configured
                            if 'pnl' in locals() and self.fee_calculator.include_fees_in_calculation:
                                # Subtract fees from both buy and sell (approximate)
                                buy_fee_approx = (buy_price * base_quantity) * (self.fee_calculator.maker_fee_pct)
                                total_fees = calculated_fee + buy_fee_approx
                                pnl = pnl - total_fees
                                print(f"   💸 Fees: ${total_fees:.3f} (Buy: ${buy_fee_approx:.3f} + Sell: ${calculated_fee:.3f})")
                        
                        # Log the trade with P&L
                        trade_data = {
                            'symbol': symbol,
                            'side': 'SELL',
                            'quantity': base_quantity,
                            'price': level['price'],
                            'order_id': order_result.get('orderId'),
                            'grid_level': level['level'],
                            'timestamp': datetime.now().isoformat(),
                            'trade_type': 'GRID',
                            'pnl': pnl if 'pnl' in locals() else 0
                        }
                        
                        self.logger.log_trade(trade_data)
                        
                        # Save trade to persistence system (CSV export)
                        self.trade_persistence.save_trade(trade_data)
                        
                        # Check if this completes a cycle
                        if cycle_tracker:
                            cycle_tracker.check_cycle_completion(
                                'sell', level['price'], base_quantity
                            )
                        
                        executed_orders.append({
                            'level': level,
                            'side': 'SELL',
                            'order_result': order_result
                        })
                        
                        print(f"   ✅ SELL executed - Level {level['level']}")
                        
                except Exception as e:
                    self.logger.log_error(f"Sell order failed at level {level['level']}", {
                        'level': level['level'],
                        'price': level['price'],
                        'error': str(e)
                    })
                    print(f"   ❌ SELL failed: {e}")
        
        return executed_orders
    
    def get_trading_opportunities(self, grid_levels, current_price):
        """Get current buy and sell opportunities based on grid levels and current price."""
        buy_opportunities = []
        sell_opportunities = []
        
        for level in grid_levels:
            level_price = level['price']
            level_side = level['side']
            level_num = level['level']
            
            if level_side == 'BUY' and current_price <= level_price:
                if level_num not in self.bought_levels:
                    buy_opportunities.append(f"Level {level_num} @ ${level_price:,.2f}")
            
            elif level_side == 'SELL' and current_price >= level_price:
                if (level_num, level_price) not in self.sold_levels:
                    sell_opportunities.append(f"Level {level_num} @ ${level_price:,.2f}")
        
        return buy_opportunities, sell_opportunities
    
    def get_execution_status(self):
        """Get current execution status."""
        return {
            'bought_levels': list(self.bought_levels),
            'sold_levels': list(self.sold_levels),
            'total_bought': len(self.bought_levels),
            'total_sold': len(self.sold_levels)
        }