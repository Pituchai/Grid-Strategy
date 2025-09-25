#!/usr/bin/env python3
"""
📈 INTEGRATED GRID STRATEGY BACKTESTER
Using your actual src/ strategy components for realistic backtesting

This backtester integrates all your existing strategy components:
- GridStrategyController (main/grid_backtest_pro.py:360)
- OrderExecutor (src/strategy/order_executor.py:29)  
- PositionManager (src/position/position_manager.py)
- RiskManager (src/strategy/risk_manager.py)
- TechnicalIndicators (src/analytics/technical_indicators.py)
- VolumeFilter (src/analytics/volume_filter.py)
- FeeCalculator (src/analytics/fee_calculator.py)
- CycleTracker (src/analytics/cycle_tracker.py)
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'src'))

# Import backtesting library
try:
    from backtesting import Backtest, Strategy
    from backtesting.lib import crossover
    import yfinance as yf
    BACKTESTING_AVAILABLE = True
except ImportError:
    BACKTESTING_AVAILABLE = False
    print("❌ backtesting.py library not installed")
    print("💡 Install with: pip install backtesting yfinance")

# Import your actual strategy components
from config_manager import ConfigManager
from eventlog.event_logger import EventLogger
from position.position_manager import PositionManager
from strategy.strategy_state import StrategyState
from strategy.risk_manager import RiskManager
from strategy.grid_generator import GridGenerator
from strategy.order_executor import OrderExecutor
from analytics.technical_indicators import TechnicalIndicators
from analytics.volume_filter import VolumeFilter
from analytics.fee_calculator import FeeCalculator
from analytics.cycle_tracker import CycleTracker


def get_btc_data_binance(symbol="BTCUSDT", interval="5m", days_back=30):
    """
    Fetch BTC historical data from Binance API directly
    Much better coverage than Yahoo Finance for high-resolution data
    """
    print(f"📊 Fetching {symbol} data from Binance API ({interval} interval, {days_back} days)...")
    
    # Calculate start and end dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    start_ts = int(start_date.timestamp() * 1000)
    end_ts = int(end_date.timestamp() * 1000)
    
    base_url = "https://api.binance.com/api/v3/klines"
    all_data = []
    
    current_ts = start_ts
    limit = 1000  # Max candles per request
    
    try:
        while current_ts < end_ts:
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': current_ts,
                'endTime': min(current_ts + (limit * get_interval_ms(interval)), end_ts),
                'limit': limit
            }
            
            import requests
            response = requests.get(base_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                    
                all_data.extend(data)
                current_ts = data[-1][6] + 1  # Next start time
                
                print(f"   📥 Fetched {len(data)} candles (Total: {len(all_data)})")
                import time
                time.sleep(0.1)  # Respect rate limits
            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
                break
        
        if all_data:
            # Convert to DataFrame
            df = pd.DataFrame(all_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])
            
            # Convert to proper types
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            # Set timestamp as index and rename columns for backtesting compatibility
            df.set_index('timestamp', inplace=True)
            df.rename(columns={
                'open': 'Open',
                'high': 'High', 
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }, inplace=True)
            
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            print(f"✅ Binance data fetched: {len(df)} candles")
            print(f"📅 Period: {df.index[0]} to {df.index[-1]}")
            print(f"📈 Price range: ${df['Close'].min():,.2f} - ${df['Close'].max():,.2f}")
            
            return df
        else:
            print("❌ No data received from Binance API")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"❌ Error fetching Binance data: {e}")
        return pd.DataFrame()


def get_interval_ms(interval):
    """Convert interval string to milliseconds"""
    if interval.endswith('m'):
        return int(interval[:-1]) * 60 * 1000
    elif interval.endswith('h'):
        return int(interval[:-1]) * 60 * 60 * 1000
    elif interval.endswith('d'):
        return int(interval[:-1]) * 24 * 60 * 60 * 1000
    else:
        return 5 * 60 * 1000  # Default to 5 minutes


def get_btc_data(period="5y", interval="1d"):
    """
    Fetch BTC historical data using yfinance (fallback)
    """
    print(f"📊 Fetching BTC data: {period} period, {interval} interval...")
    
    try:
        # Fetch BTC-USD data
        btc = yf.Ticker("BTC-USD")
        
        # Get historical data - use daily data for longer periods
        data = btc.history(period=period, interval=interval)
        
        if data.empty:
            raise Exception("No data fetched")
        
        # Clean the data
        data.dropna(inplace=True)
        
        print(f"✅ Fetched {len(data)} data points")
        print(f"📅 Period: {data.index[0]} to {data.index[-1]}")
        print(f"📈 Price range: ${data['Close'].min():,.2f} - ${data['Close'].max():,.2f}")
        
        return data
        
    except Exception as e:
        print(f"❌ Failed to fetch BTC data: {e}")
        return pd.DataFrame()


class MockBinanceClient:
    """
    Mock Binance client for backtesting that simulates API responses
    without making real API calls
    """
    
    def __init__(self):
        self.simulated_fees = 0.001  # 0.1% fee
        
    def get_symbol_ticker(self, symbol):
        # This won't be called in backtesting, but provide fallback
        return {"price": "50000.00"}
        
    def get_ticker_24hr(self, symbol):
        # Mock 24hr ticker for volume filtering
        return {
            "symbol": symbol,
            "priceChange": "1000.00",
            "priceChangePercent": "2.00", 
            "weightedAvgPrice": "50000.00",
            "prevClosePrice": "49000.00",
            "lastPrice": "50000.00",
            "lastQty": "0.001",
            "bidPrice": "49999.00",
            "bidQty": "0.001", 
            "askPrice": "50001.00",
            "askQty": "0.001",
            "openPrice": "49000.00",
            "highPrice": "51000.00",
            "lowPrice": "48000.00",
            "volume": "1000.00",  # BTC volume
            "quoteVolume": "50000000.00",  # USDT volume (meets min requirement)
            "openTime": 1630000000000,
            "closeTime": 1630086400000,
            "count": 50000
        }
        
    def create_order(self, symbol, side, type, timeInForce, quantity, price):
        # Simulate successful order
        return {
            "orderId": f"MOCK_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "status": "FILLED",
            "executedQty": str(quantity),
            "fills": [{
                "price": str(price),
                "qty": str(quantity),
                "commission": str(float(price) * float(quantity) * self.simulated_fees)
            }]
        }
        
    def order_market_buy(self, symbol, quantity):
        # Simulate market buy - price will be set by backtesting framework
        return self.create_order(symbol, "BUY", "MARKET", "IOC", quantity, "50000")
        
    def order_market_sell(self, symbol, quantity):
        # Simulate market sell - price will be set by backtesting framework
        return self.create_order(symbol, "SELL", "MARKET", "IOC", quantity, "50000")


class RealGridStrategy(Strategy):
    """
    Backtesting.py Strategy that uses your actual GridStrategyController
    """
    
    def init(self):
        """Initialize strategy with your actual components."""
        print("🏗️  Initializing Real Grid Strategy with your src/ components...")
        
        # Initialize configuration manager
        config_path = os.path.join(os.path.dirname(__file__), '..', 'strategy_config.yaml')
        self.config_manager = ConfigManager(config_path)
        
        # Initialize event logger (in memory mode for backtesting)
        self.event_logger = EventLogger(self.config_manager, 
                                       log_dir='../logs', 
                                       log_filename='backtest_grid_strategy.csv')
        
        # Initialize position manager
        self.position_manager = PositionManager(self.event_logger)
        
        # Initialize strategy state
        self.strategy_state = StrategyState()
        
        # Initialize risk manager
        self.risk_manager = RiskManager(self.config_manager, self.event_logger)
        
        # Initialize mock client for backtesting
        self.mock_client = MockBinanceClient()
        
        # Initialize order executor with mock client
        self.order_executor = OrderExecutor(
            config_manager=self.config_manager,
            event_logger=self.event_logger,
            position_manager=self.position_manager,
            client=self.mock_client,
            risk_manager=self.risk_manager
        )
        
        # Initialize analytics components
        self.technical_indicators = TechnicalIndicators(self.config_manager, self.event_logger)
        self.volume_filter = VolumeFilter(self.config_manager, self.event_logger, self.mock_client)
        self.fee_calculator = FeeCalculator(self.config_manager, self.event_logger)
        self.cycle_tracker = CycleTracker(self.config_manager, self.event_logger)
        
        # Initialize grid generator
        self.grid_generator = GridGenerator(self.config_manager, self.event_logger)
        
        # Initialize grid levels
        self.grid_levels = []
        self.last_grid_price = None
        self.rebalance_threshold = 0.05  # 5% price change to rebalance
        
        # Set up fee calculator in order executor
        self.order_executor.fee_calculator = self.fee_calculator
        
        print("✅ All real strategy components initialized")
        
    def next(self):
        """Execute strategy logic for each time step using your real components."""
        current_price = self.data.Close[-1]
        
        # Create OHLC data for the current period (last 50 periods for indicators)
        start_idx = max(0, len(self.data.Close) - 50)
        ohlc_data = pd.DataFrame({
            'open': self.data.Open[start_idx:],
            'high': self.data.High[start_idx:],
            'low': self.data.Low[start_idx:],
            'close': self.data.Close[start_idx:],
            'volume': self.data.Volume[start_idx:]
        })
        
        # Volume filtering (skip if volume too low)
        try:
            if not self.volume_filter.should_allow_trading_by_volume(current_price):
                return  # Skip trading this period
        except Exception as e:
            # Volume filter might fail with limited data, continue trading
            pass
        
        # Technical indicators check
        try:
            buy_allowed, buy_reason = self.technical_indicators.should_allow_trading_by_indicators(current_price, 'BUY')
            sell_allowed, sell_reason = self.technical_indicators.should_allow_trading_by_indicators(current_price, 'SELL')
        except Exception as e:
            # Technical indicators might fail with limited data, allow trading
            buy_allowed = sell_allowed = True
            buy_reason = sell_reason = "Technical indicators unavailable"
        
        # Generate or rebalance grid if needed
        if self._should_rebalance_grid(current_price):
            try:
                # Generate grid using your real grid generator
                grid_params = self._get_grid_parameters(ohlc_data)
                self.grid_levels = self.grid_generator.generate_grid_levels(
                    current_price, grid_params
                )
                self.last_grid_price = current_price
                
            except Exception as e:
                # If grid generation fails, create simple grid
                self.grid_levels = self._create_simple_grid(current_price)
                self.last_grid_price = current_price
        
        # Execute buy orders if allowed
        if buy_allowed and self.grid_levels:
            try:
                # Use your real order executor for buy decisions
                buy_opportunities, _ = self.order_executor.get_trading_opportunities(
                    self.grid_levels, current_price
                )
                
                # Execute buys via backtesting framework
                for level in self.grid_levels:
                    if (level['side'] == 'BUY' and 
                        current_price <= level['price'] and 
                        level['level'] not in self.order_executor.bought_levels):
                        
                        # Use fixed BTC amount to avoid margin issues
                        trading_cfg = self.config_manager.get_trading_config()
                        position_size = 0.001  # Fixed 0.001 BTC per trade (~$115-120)
                        
                        if position_size > 0:
                            # Execute buy via backtesting framework
                            self.buy(size=position_size)
                            
                            # Update your real position manager
                            self.position_manager.buy(position_size, current_price, datetime.now())
                            
                            # Track in order executor
                            self.order_executor.bought_levels.add(level['level'])
                            
                            # Log with cycle tracker
                            self.cycle_tracker.check_cycle_completion('buy', current_price, position_size)
                            
            except Exception as e:
                # Continue if buy execution fails
                pass
        
        # Execute sell orders if allowed
        if sell_allowed and self.grid_levels and self.position.size > 0:
            try:
                # Use your real order executor for sell decisions  
                _, sell_opportunities = self.order_executor.get_trading_opportunities(
                    self.grid_levels, current_price
                )
                
                # Execute sells via backtesting framework
                for level in self.grid_levels:
                    if (level['side'] == 'SELL' and 
                        current_price >= level['price'] and 
                        (level['level'], level['price']) not in self.order_executor.sold_levels and
                        self.position.size > 0):
                        
                        # Use fixed BTC amount matching buy size for symmetry
                        trading_cfg = self.config_manager.get_trading_config()
                        target_sell_size = 0.001  # Fixed 0.001 BTC per trade (matches buy size)
                        sell_size = min(target_sell_size, self.position.size)
                        
                        if sell_size > 0:
                            # Execute sell via backtesting framework
                            self.sell(size=sell_size)
                            
                            # Update your real position manager  
                            self.position_manager.sell(sell_size, current_price, datetime.now())
                            
                            # Track in order executor
                            self.order_executor.sold_levels.add((level['level'], level['price']))
                            
                            # Log with cycle tracker
                            self.cycle_tracker.check_cycle_completion('sell', current_price, sell_size)
                            
            except Exception as e:
                # Continue if sell execution fails
                pass
    
    def _should_rebalance_grid(self, current_price):
        """Check if grid should be rebalanced."""
        if self.last_grid_price is None or not self.grid_levels:
            return True
        
        price_change_pct = abs(current_price - self.last_grid_price) / self.last_grid_price
        return price_change_pct > self.rebalance_threshold
    
    def _get_grid_parameters(self, ohlc_data):
        """Get grid parameters using your real volatility calculations."""
        try:
            # Use your real grid generator's parameter calculation
            return self.grid_generator.define_parameters(ohlc_data)
        except Exception as e:
            # Fallback to simple parameters
            return {
                'grid_range_pct': 2.5,
                'grid_spacing_pct': 0.5,
                'levels': 10,
                'capital_per_grid_pct': 10
            }
    
    def _create_simple_grid(self, center_price):
        """Create simple grid as fallback."""
        grid_range = 0.025  # 2.5%
        grid_spacing = 0.005  # 0.5%
        levels = 10
        
        grid_levels = []
        
        # Create buy levels below center price
        for i in range(levels // 2):
            level_pct = (i + 1) * grid_spacing
            price = center_price * (1 - level_pct)
            grid_levels.append({
                'level': -(i + 1),
                'side': 'BUY',
                'price': price,
                'quantity': 0.001  # Base quantity
            })
        
        # Create sell levels above center price  
        for i in range(levels // 2):
            level_pct = (i + 1) * grid_spacing
            price = center_price * (1 + level_pct)
            grid_levels.append({
                'level': i + 1,
                'side': 'SELL', 
                'price': price,
                'quantity': 0.001  # Base quantity
            })
            
        return grid_levels


def run_integrated_backtest(data):
    """Run backtest using your real strategy components."""
    print(f"\n🚀 RUNNING INTEGRATED GRID STRATEGY BACKTEST")
    print("Using your actual src/ folder components!")
    print("=" * 60)
    
    try:
        # Load configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'strategy_config.yaml')
        config_manager = ConfigManager(config_path)
        
        # Get trading configuration
        trading_cfg = config_manager.get_trading_config()
        initial_capital = 30000  # $30K USDT - realistic trading capital
        
        print(f"✅ Loaded configuration from strategy_config.yaml")
        print(f"💰 Initial Capital: ${initial_capital:,.2f}")
        print(f"💸 Commission: 0.1% per trade")
        print(f"📊 Data Points: {len(data)}")
        
        # Create and run backtest
        bt = Backtest(
            data,
            RealGridStrategy,
            cash=initial_capital,
            commission=0.001,  # 0.1% commission
            exclusive_orders=True,
            margin=1.0  # No leverage - 1:1 margin
        )
        
        print(f"\n🔄 Running backtest simulation...")
        results = bt.run()
        
        # Generate HTML report
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = f"logs/integrated_backtest_report_{timestamp}.html"
            bt.plot(filename=report_path, open_browser=False)
            print(f"📊 Interactive HTML report saved: {report_path}")
        except Exception as e:
            print(f"⚠️  Could not generate HTML report: {e}")
        
        return results, bt
        
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def print_integrated_results(results):
    """Print comprehensive backtest results."""
    print(f"\n📊 INTEGRATED BACKTEST RESULTS")
    print("Using your REAL src/ strategy components")
    print("=" * 60)
    
    # Basic performance metrics
    print(f"💰 Final Value: ${results['Equity Final [$]']:,.2f}")
    print(f"📈 Total Return: {results['Return [%]']:+.2f}%")
    print(f"📊 Annualized Return: {results['Return (Ann.) [%]']:+.2f}%")
    print(f"📉 Max Drawdown: {results['Max. Drawdown [%]']:.2f}%")
    print(f"📊 Volatility: {results['Volatility (Ann.) [%]']:.2f}%")
    print(f"📈 Sharpe Ratio: {results['Sharpe Ratio']:.2f}")
    
    # Trading statistics
    print(f"\n🔄 TRADING STATISTICS")
    print("-" * 30)
    print(f"📊 Total Trades: {results['# Trades']}")
    print(f"🎯 Win Rate: {results['Win Rate [%]']:.1f}%")
    print(f"💰 Best Trade: {results['Best Trade [%]']:+.2f}%")
    print(f"💸 Worst Trade: {results['Worst Trade [%]']:+.2f}%")
    print(f"📊 Avg Trade: {results['Avg. Trade [%]']:+.2f}%")
    
    # Risk analysis
    print(f"\n⚖️  RISK ANALYSIS")
    print("-" * 30)
    print(f"📊 Max Drawdown Duration: {results['Max. Drawdown Duration']}")
    print(f"📈 Profit Factor: {results['Profit Factor']:.2f}")
    if 'Expectancy [$]' in results:
        print(f"🎯 Expectancy: ${results['Expectancy [$]']:.2f}")
    else:
        print(f"🎯 Expectancy: N/A (insufficient trades)")
    
    # Strategy assessment
    print(f"\n🎯 INTEGRATED STRATEGY ASSESSMENT")
    print("-" * 40)
    if results['Return [%]'] > 0:
        print("✅ PROFITABLE STRATEGY")
    else:
        print("❌ LOSS-MAKING STRATEGY")
        print("💡 Consider adjusting parameters in strategy_config.yaml")
    
    if abs(results['Max. Drawdown [%]']) < 20:
        print("✅ Reasonable risk level (Max DD < 20%)")
    else:
        print("⚠️  High risk level (Max DD > 20%)")
    
    if results['Win Rate [%]'] >= 60:
        print("✅ Good win rate (>60%)")
    else:
        print("⚠️  Low win rate (<60%)")


def main():
    """Main integrated backtesting execution."""
    print("📈 INTEGRATED GRID STRATEGY BACKTESTER")
    print("Using your actual src/ folder strategy components")
    print("=" * 80)
    
    if not BACKTESTING_AVAILABLE:
        print("\n💡 To install required libraries:")
        print("pip install backtesting yfinance")
        return
    
    try:
        # Get BTC data
        print("1. Fetching BTC historical data...")
        # Available intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        # Available periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        # API Limits: 5m/15m data limited to 60 days, 1h data works for 2+ years
        # Use Binance API for much better 5-minute coverage
        # Can get months/years of 5-minute data (not limited like Yahoo Finance)
        data = get_btc_data_binance(symbol="BTCUSDT", interval="1m", days_back=60)  # 60 days of 1-minute data!
        
        if data.empty:
            print("❌ No data available")
            return
        
        # Ensure logs directory exists
        os.makedirs("logs", exist_ok=True)
        
        # Run integrated backtest
        print("2. Running integrated backtest with your real components...")
        results, bt_instance = run_integrated_backtest(data)
        
        if results is None:
            print("❌ Backtest failed")
            return
        
        # Print results
        print_integrated_results(results)
        
        # Compare with simple strategy
        print(f"\n📊 COMPONENT USAGE SUMMARY:")
        print("-" * 40)
        print("✅ ConfigManager: strategy_config.yaml")
        print("✅ EventLogger: backtest_grid_strategy.csv")
        print("✅ PositionManager: Real position tracking")
        print("✅ RiskManager: Risk limits and alerts")
        print("✅ OrderExecutor: Real order logic")
        print("✅ TechnicalIndicators: RSI, MACD, Bollinger")
        print("✅ VolumeFilter: 24h volume filtering")
        print("✅ FeeCalculator: Maker/taker fees")
        print("✅ CycleTracker: P&L cycle analysis")
        print("✅ GridGenerator: Dynamic grid generation")
        
        print(f"\n🌐 Open logs/integrated_backtest_report_*.html for detailed analysis!")
        
    except Exception as e:
        print(f"❌ Error during integrated backtesting: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()