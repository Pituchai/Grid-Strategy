#!/usr/bin/env python3
"""
Simple Grid Strategy Backtest - Direct Implementation
No external backtesting library, just your real strategy components
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import time

# Simple backtest without complex imports
import yaml

def get_binance_data(symbol="BTCUSDT", interval="1m", days_back=60):
    """Fetch Bitcoin data from Binance API"""
    print(f"📊 Fetching {symbol} data from Binance API ({interval} interval, {days_back} days)...")
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_back)
    
    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)
    
    base_url = "https://api.binance.com/api/v3/klines"
    all_data = []
    
    current_ts = start_ts
    limit = 1000
    
    interval_ms = 60 * 1000  # 1 minute
    
    try:
        while current_ts < end_ts:
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': current_ts,
                'endTime': min(current_ts + (limit * interval_ms), end_ts),
                'limit': limit
            }
            
            response = requests.get(base_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                    
                all_data.extend(data)
                current_ts = data[-1][6] + 1
                
                print(f"   📥 Fetched {len(data)} candles (Total: {len(all_data)})")
                time.sleep(0.1)
            else:
                print(f"❌ Error: {response.status_code}")
                break
        
        if all_data:
            df = pd.DataFrame(all_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df.set_index('timestamp', inplace=True)
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            print(f"✅ Data fetched: {len(df)} candles")
            print(f"📅 Period: {df.index[0]} to {df.index[-1]}")
            print(f"📈 Price range: ${df['close'].min():,.2f} - ${df['close'].max():,.2f}")
            
            return df
        else:
            print("❌ No data received")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return pd.DataFrame()


class SimplePortfolio:
    """Simple portfolio tracking for direct backtesting"""
    
    def __init__(self, initial_cash=30000):
        self.cash = initial_cash
        self.btc_position = 0.0
        self.initial_cash = initial_cash
        self.trades = []
        
    def buy_btc(self, quantity, price, timestamp):
        """Buy Bitcoin"""
        cost = quantity * price
        if self.cash >= cost:
            self.cash -= cost
            self.btc_position += quantity
            
            self.trades.append({
                'timestamp': timestamp,
                'side': 'BUY',
                'quantity': quantity,
                'price': price,
                'value': cost,
                'cash_after': self.cash,
                'btc_after': self.btc_position
            })
            return True
        return False
    
    def sell_btc(self, quantity, price, timestamp):
        """Sell Bitcoin"""
        if self.btc_position >= quantity:
            proceeds = quantity * price
            self.cash += proceeds
            self.btc_position -= quantity
            
            self.trades.append({
                'timestamp': timestamp,
                'side': 'SELL',
                'quantity': quantity,
                'price': price,
                'value': proceeds,
                'cash_after': self.cash,
                'btc_after': self.btc_position
            })
            return True
        return False
    
    def get_total_value(self, current_btc_price):
        """Get total portfolio value"""
        btc_value = self.btc_position * current_btc_price
        return self.cash + btc_value
    
    def get_profit(self, current_btc_price):
        """Get total profit"""
        return self.get_total_value(current_btc_price) - self.initial_cash


def run_simple_backtest():
    """Run simple grid strategy backtest"""
    print("🚀 SIMPLE GRID STRATEGY BACKTEST")
    print("=" * 50)
    
    # Get data
    data = get_binance_data(days_back=60)
    if data.empty:
        print("❌ No data available")
        return
    
    # Read config directly from YAML
    config_path = '../strategy_config.yaml'
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    portfolio = SimplePortfolio(initial_cash=30000)
    
    # Grid parameters from config
    trading_cfg = config['trading']
    grid_cfg = config['grid']
    
    base_quantity = trading_cfg.get('base_order_quantity', 0.013)  # Use your YAML setting
    grid_range_pct = grid_cfg.get('grid_range_pct', 2.5) / 100
    grid_spacing_pct = grid_cfg.get('grid_spacing_pct', 0.5) / 100
    levels = grid_cfg.get('levels', 10)
    
    print(f"📊 Grid Config:")
    print(f"   Range: ±{grid_range_pct*100:.1f}%")
    print(f"   Spacing: {grid_spacing_pct*100:.1f}%")
    print(f"   Levels: {levels}")
    print(f"   Quantity per trade: {base_quantity} BTC")
    
    # Track executed levels
    bought_levels = set()
    sold_levels = set()
    
    # Process each candle
    print(f"\n🔄 Processing {len(data)} candles...")
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        current_price = row['close']
        
        # Create grid levels every 1000 candles or at start
        if i % 1000 == 0 or i == 0:
            center_price = current_price
            grid_levels = []
            
            # Create buy levels (below current price)
            for level in range(1, levels//2 + 1):
                buy_price = center_price * (1 - level * grid_spacing_pct)
                grid_levels.append({
                    'level': f'buy_{level}',
                    'side': 'BUY',
                    'price': buy_price
                })
            
            # Create sell levels (above current price)
            for level in range(1, levels//2 + 1):
                sell_price = center_price * (1 + level * grid_spacing_pct)
                grid_levels.append({
                    'level': f'sell_{level}',
                    'side': 'SELL',
                    'price': sell_price
                })
        
        # Execute trades
        for level in grid_levels:
            level_id = level['level']
            
            # Execute buy orders
            if (level['side'] == 'BUY' and 
                current_price <= level['price'] and 
                level_id not in bought_levels):
                
                if portfolio.buy_btc(base_quantity, current_price, timestamp):
                    bought_levels.add(level_id)
                    print(f"✅ BUY {base_quantity} BTC @ ${current_price:,.2f} | Level: {level_id}")
            
            # Execute sell orders  
            elif (level['side'] == 'SELL' and
                  current_price >= level['price'] and
                  level_id not in sold_levels and
                  portfolio.btc_position >= base_quantity):
                
                if portfolio.sell_btc(base_quantity, current_price, timestamp):
                    sold_levels.add(level_id)
                    profit = (current_price - data['close'].iloc[max(0, i-100):i].mean()) * base_quantity
                    print(f"💰 SELL {base_quantity} BTC @ ${current_price:,.2f} | Level: {level_id} | Est. P&L: ${profit:.2f}")
    
    # Final results
    final_price = data['close'].iloc[-1]
    final_value = portfolio.get_total_value(final_price)
    total_profit = portfolio.get_profit(final_price)
    total_return = (total_profit / portfolio.initial_cash) * 100
    
    print(f"\n📊 BACKTEST RESULTS")
    print("=" * 30)
    print(f"💰 Initial Capital: ${portfolio.initial_cash:,.2f}")
    print(f"💵 Final Cash: ${portfolio.cash:,.2f}")
    print(f"₿  Final BTC: {portfolio.btc_position:.6f} BTC")
    print(f"💎 BTC Value: ${portfolio.btc_position * final_price:,.2f}")
    print(f"🎯 Total Value: ${final_value:,.2f}")
    print(f"📈 Total Profit: ${total_profit:,.2f}")
    print(f"📊 Total Return: {total_return:.2f}%")
    print(f"🔄 Total Trades: {len(portfolio.trades)}")
    
    # Trade breakdown
    buy_trades = [t for t in portfolio.trades if t['side'] == 'BUY']
    sell_trades = [t for t in portfolio.trades if t['side'] == 'SELL']
    
    print(f"📊 Buy Orders: {len(buy_trades)}")
    print(f"📊 Sell Orders: {len(sell_trades)}")
    
    if sell_trades:
        print(f"\n💰 Recent Profitable Sells:")
        for trade in sell_trades[-5:]:
            print(f"   {trade['timestamp'].strftime('%m-%d %H:%M')} | ${trade['price']:,.2f} | {trade['quantity']:.6f} BTC")
    
    return total_profit, total_return


if __name__ == "__main__":
    profit, return_pct = run_simple_backtest()