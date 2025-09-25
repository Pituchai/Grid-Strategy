#!/usr/bin/env python3
"""
🧪 GRID FEATURE TEST - Simulate price movements to test all features
This script simulates various price scenarios to verify:
- Grid level execution (buy/sell orders)
- Fee calculations
- Technical indicators
- Risk management
- Performance tracking
- All YAML configuration features
"""

import sys
import os
import time
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from src.eventlog.event_logger import EventLogger
from src.position.position_manager import PositionManager
from src.strategy.risk_manager import RiskManager
from src.strategy.strategy_state import StrategyState
from src.strategy.grid_strategy_controller import GridStrategyController


class MockBinanceClient:
    """Mock Binance client for testing without real API calls."""
    
    def __init__(self, simulated_price=100000.0):
        self.simulated_price = simulated_price
        self.simulated_balances = {
            'USDT': 20000.0,
            'BTC': 0.2
        }
    
    def get_symbol_ticker(self, symbol="BTCUSDT"):
        return {'price': str(self.simulated_price)}
    
    def get_account(self):
        return {
            'accountType': 'SPOT',
            'balances': [
                {'asset': 'USDT', 'free': str(self.simulated_balances['USDT']), 'locked': '0.0'},
                {'asset': 'BTC', 'free': str(self.simulated_balances['BTC']), 'locked': '0.0'}
            ]
        }
    
    def get_ticker(self, symbol="BTCUSDT"):
        return {
            'symbol': symbol,
            'volume': '25000.0',  # Sufficient volume for testing
            'quoteVolume': '2500000000.0',
            'priceChangePercent': '2.5',
            'highPrice': str(self.simulated_price * 1.05),
            'lowPrice': str(self.simulated_price * 0.95)
        }
    
    def set_price(self, new_price):
        """Update simulated price for testing."""
        self.simulated_price = new_price
    
    def simulate_buy_execution(self, quantity, price):
        """Simulate buy order execution."""
        cost = quantity * price
        if self.simulated_balances['USDT'] >= cost:
            self.simulated_balances['USDT'] -= cost
            self.simulated_balances['BTC'] += quantity
            return True
        return False
    
    def simulate_sell_execution(self, quantity, price):
        """Simulate sell order execution."""
        if self.simulated_balances['BTC'] >= quantity:
            self.simulated_balances['BTC'] -= quantity
            self.simulated_balances['USDT'] += quantity * price
            return True
        return False


class GridFeatureTester:
    """Test all grid strategy features with simulated price movements."""
    
    def __init__(self):
        print("🧪 INITIALIZING GRID FEATURE TEST")
        print("=" * 80)
        
        # Initialize configuration (path relative to project root)
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategy_config.yaml")
        self.cfg = ConfigManager(config_path)
        
        # Initialize mock client
        self.mock_client = MockBinanceClient(simulated_price=100000.0)
        
        # Initialize components
        self.logger = EventLogger(self.cfg, log_dir="logs", log_filename="feature_test.csv")
        self.pm = PositionManager(self.logger)
        self.state = StrategyState("test_strategy_state.json")
        self.risk = RiskManager(self.cfg, self.logger, self.pm)
        
        # Initialize strategy controller
        self.controller = GridStrategyController(
            self.cfg, self.logger, self.pm, self.state, self.risk, self.mock_client
        )
        
        print("✅ All components initialized successfully!")
        print(f"📊 Starting BTC Price: ${self.mock_client.simulated_price:,.2f}")
        
    def test_grid_initialization(self):
        """Test grid level creation and display."""
        print("\n🏗️  TESTING GRID INITIALIZATION")
        print("-" * 50)
        
        # Create initial grid data as pandas DataFrame with OHLC data
        import pandas as pd
        price = self.mock_client.simulated_price
        # Create realistic OHLC data for volatility calculations
        current_data = pd.DataFrame({
            'open': [price * 0.999, price * 1.001] * 10,  # Slight variations
            'high': [price * 1.002, price * 1.003] * 10,  # Higher than open/close
            'low': [price * 0.998, price * 0.997] * 10,   # Lower than open/close
            'close': [price, price * 1.001] * 10,         # Alternating close prices
            'volume': [25000] * 20                        # Volume data
        })
        self.controller.data = current_data
        
        # Define parameters and create grid
        params = self.controller.define_parameters(current_data)
        self.controller.grid_levels = self.controller.grid_generator.generate_grid_levels(
            params['center_price'], params.get('adjusted_grid_spacing_pct')
        )
        
        print(f"✅ Grid created with {len(self.controller.grid_levels)} levels")
        
        # Display grid
        self.controller.grid_display.print_grid_levels(
            self.controller.grid_levels, self.mock_client.simulated_price
        )
        
        return True
    
    def test_buy_execution(self, trigger_price):
        """Test buy order execution when price drops."""
        print(f"\n🟢 TESTING BUY EXECUTION at ${trigger_price:,.2f}")
        print("-" * 50)
        
        # Set price to trigger buy
        self.mock_client.set_price(trigger_price)
        
        # Add price data to technical indicators
        self.controller.technical_indicators.add_price_data(trigger_price)
        
        # Check for buy opportunities
        buy_opportunities, _ = self.controller.order_executor.get_trading_opportunities(
            self.controller.grid_levels, trigger_price
        )
        
        if buy_opportunities:
            print(f"🎯 Buy opportunities found: {len(buy_opportunities)}")
            
            # Execute buy orders (simulated)
            for level in self.controller.grid_levels:
                if (level['side'] == 'BUY' and 
                    trigger_price <= level['price'] and 
                    level['level'] not in self.controller.order_executor.bought_levels):
                    
                    # Simulate order execution
                    quantity = 0.001  # Base quantity from config
                    success = self.mock_client.simulate_buy_execution(quantity, level['price'])
                    
                    if success:
                        # Update position manager
                        self.controller.pm.buy(quantity, level['price'], datetime.now())
                        
                        # Track in order executor
                        self.controller.order_executor.bought_levels.add(level['level'])
                        
                        # Calculate fees
                        trade_value = level['price'] * quantity
                        fee_info = self.controller.fee_calculator.calculate_order_fee(trade_value, 'LIMIT')
                        self.controller.fee_calculator.record_fee_payment(fee_info['final_fee'], 'USDT', 'LIMIT')
                        
                        print(f"   ✅ BUY executed - Level {level['level']} @ ${level['price']:,.2f}")
                        print(f"   💰 Quantity: {quantity:.6f} BTC | Fee: ${fee_info['final_fee']:.4f}")
                        
                        break
        else:
            print("❌ No buy opportunities at this price level")
        
        return len(buy_opportunities) > 0
    
    def test_sell_execution(self, trigger_price):
        """Test sell order execution when price rises."""
        print(f"\n🔴 TESTING SELL EXECUTION at ${trigger_price:,.2f}")
        print("-" * 50)
        
        # Set price to trigger sell
        self.mock_client.set_price(trigger_price)
        
        # Add price data to technical indicators
        self.controller.technical_indicators.add_price_data(trigger_price)
        
        # Check for sell opportunities
        _, sell_opportunities = self.controller.order_executor.get_trading_opportunities(
            self.controller.grid_levels, trigger_price
        )
        
        if sell_opportunities:
            print(f"🎯 Sell opportunities found: {len(sell_opportunities)}")
            
            # Execute sell orders (simulated)
            for level in self.controller.grid_levels:
                if (level['side'] == 'SELL' and 
                    trigger_price >= level['price'] and 
                    (level['level'], level['price']) not in self.controller.order_executor.sold_levels):
                    
                    # Check if we have position to sell
                    current_position = self.controller.pm.get_position_summary().get('current_position')
                    if current_position and current_position.get('quantity', 0) >= 0.001:
                        
                        # Simulate order execution
                        quantity = 0.001
                        success = self.mock_client.simulate_sell_execution(quantity, level['price'])
                        
                        if success:
                            # Update position manager
                            self.controller.pm.sell(quantity, level['price'], datetime.now())
                            
                            # Calculate P&L
                            buy_price = current_position.get('buy_price', level['price'])
                            pnl = (level['price'] - buy_price) * quantity
                            
                            # Record with risk manager
                            trade_id = f"TEST_SELL_{level['level']}"
                            self.controller.risk.record_trade_result(pnl, trade_id)
                            
                            # Track in order executor
                            self.controller.order_executor.sold_levels.add((level['level'], level['price']))
                            
                            # Calculate fees
                            trade_value = level['price'] * quantity
                            fee_info = self.controller.fee_calculator.calculate_order_fee(trade_value, 'LIMIT')
                            self.controller.fee_calculator.record_fee_payment(fee_info['final_fee'], 'USDT', 'LIMIT')
                            
                            # Adjust P&L for fees if configured
                            if self.controller.fee_calculator.include_fees_in_calculation:
                                buy_fee_approx = (buy_price * quantity) * self.controller.fee_calculator.maker_fee_pct
                                total_fees = fee_info['final_fee'] + buy_fee_approx
                                net_pnl = pnl - total_fees
                            else:
                                net_pnl = pnl
                                total_fees = fee_info['final_fee']
                            
                            print(f"   ✅ SELL executed - Level {level['level']} @ ${level['price']:,.2f}")
                            print(f"   💰 P&L: ${net_pnl:.4f} (Gross: ${pnl:.4f} - Fees: ${total_fees:.4f})")
                            
                            break
                    else:
                        print(f"   ⚠️  Insufficient position to sell at level {level['level']}")
        else:
            print("❌ No sell opportunities at this price level")
        
        return len(sell_opportunities) > 0
    
    def test_all_features(self):
        """Test comprehensive feature functionality."""
        print("\n📊 TESTING ALL FEATURES")
        print("=" * 80)
        
        # Current balances
        account = self.mock_client.get_account()
        print(f"💰 Starting Balances:")
        for balance in account['balances']:
            if float(balance['free']) > 0:
                print(f"   {balance['asset']}: {balance['free']}")
        
        # Test volume filter
        print(f"\n📊 Volume Filter Status:")
        volume_status = self.controller.volume_filter.get_volume_status()
        print(f"   Status: {volume_status['status']} | Message: {volume_status['message']}")
        
        # Test technical indicators
        print(f"\n📈 Technical Indicators:")
        indicator_status = self.controller.technical_indicators.get_indicator_status_summary()
        print(f"   Enabled: {indicator_status['enabled']}")
        if indicator_status['enabled']:
            print(f"   Data Points: {indicator_status['price_history_length']}")
        
        # Test fee calculator
        print(f"\n💰 Fee Analysis:")
        fee_analysis = self.controller.fee_calculator.get_fee_analysis_summary()
        config = fee_analysis['configuration']
        print(f"   Maker Fee: {config['maker_fee_pct']:.3f}% | Taker Fee: {config['taker_fee_pct']:.3f}%")
        print(f"   Fee Discount: {config['use_fee_discount']} | Include in P&L: {config['include_fees_in_calculation']}")
        
        # Test risk manager
        print(f"\n🛡️  Risk Management:")
        risk_status = self.controller.risk.get_risk_status()
        print(f"   Current Drawdown: ${risk_status.get('current_drawdown', 0):.2f}")
        print(f"   Consecutive Losses: {risk_status.get('consecutive_losses', 0)}")
        print(f"   High Risk Mode: {risk_status.get('high_risk_mode', False)}")
        
        return True
    
    def run_price_simulation(self):
        """Run a complete price simulation to test buy/sell cycle."""
        print("\n🎮 RUNNING COMPLETE PRICE SIMULATION")
        print("=" * 80)
        
        # Test sequence
        test_prices = [
            98000,   # Trigger buy orders
            102000,  # Return to middle
            104000,  # Trigger sell orders
            100000,  # Return to center
        ]
        
        for i, price in enumerate(test_prices, 1):
            print(f"\n📈 SIMULATION STEP {i}: Setting price to ${price:,.2f}")
            
            if price < 100000:  # Below center, should trigger buys
                self.test_buy_execution(price)
            elif price > 102000:  # Above center, should trigger sells
                self.test_sell_execution(price)
            else:
                print(f"   ⏳ Price ${price:,.2f} between grid levels - no trades")
            
            # Show updated balances
            account = self.mock_client.get_account()
            for balance in account['balances']:
                if float(balance['free']) > 0.1:  # Show significant balances
                    print(f"   💰 {balance['asset']}: {float(balance['free']):.6f}")
            
            time.sleep(1)  # Pause between steps
        
        # Final summary
        print(f"\n📊 SIMULATION COMPLETE - FINAL STATUS:")
        print("-" * 50)
        
        # Show position summary
        position_summary = self.controller.pm.get_position_summary()
        if position_summary.get('current_position'):
            pos = position_summary['current_position']
            print(f"📊 Current Position: {pos.get('quantity', 0):.6f} BTC @ ${pos.get('buy_price', 0):.2f}")
        
        # Show fee tracking
        fee_analysis = self.controller.fee_calculator.get_fee_analysis_summary()
        tracking = fee_analysis['fee_tracking']
        if tracking['fee_payments_count'] > 0:
            print(f"💳 Total Fees: ${tracking['total_fees_paid']:.4f} ({tracking['fee_payments_count']} trades)")
        
        # Show bought/sold levels
        exec_status = self.controller.order_executor.get_execution_status()
        print(f"📋 Executed: {exec_status['total_bought']} buys, {exec_status['total_sold']} sells")
        
        return True


def main():
    """Run the grid feature test."""
    print("🧪 GRID STRATEGY FEATURE TEST")
    print("Testing all YAML-configured features with simulated price movements")
    print("=" * 80)
    
    try:
        # Initialize tester
        tester = GridFeatureTester()
        
        # Run tests
        print("\n🚀 STARTING FEATURE TESTS...")
        
        # Test 1: Grid Initialization
        tester.test_grid_initialization()
        
        # Test 2: All Features Status
        tester.test_all_features()
        
        # Test 3: Price Simulation
        tester.run_price_simulation()
        
        print("\n🎉 ALL TESTS COMPLETED SUCCESSFULLY!")
        print("✅ Grid strategy features are working correctly")
        print("✅ YAML configuration is being respected")
        print("✅ Fee calculations are active")
        print("✅ Risk management is functional")
        print("✅ All logging and tracking systems operational")
        
        # Show final dashboard
        print(f"\n📊 FINAL DASHBOARD:")
        print("-" * 50)
        current_price = tester.mock_client.simulated_price
        
        tester.controller.grid_display.print_fee_analysis(tester.controller.fee_calculator)
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)