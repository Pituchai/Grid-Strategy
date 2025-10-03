#!/usr/bin/env python3
"""
Quick profit analysis from backtest logs
"""
import pandas as pd
import os

def analyze_backtest_profit():
    """Analyze profit from backtest CSV logs"""
    
    # Check trade history CSV if it exists
    trade_file = "logs/trade_history.csv"
    backtest_file = "logs/backtest_grid_strategy.csv"
    
    print("💰 PROFIT ANALYSIS")
    print("=" * 50)
    
    # Try to read trade history first
    if os.path.exists(trade_file):
        print(f"📊 Reading {trade_file}...")
        try:
            trades_df = pd.read_csv(trade_file)
            if not trades_df.empty:
                print(f"   Found {len(trades_df)} trades")
                
                # Calculate total P&L if pnl column exists
                if 'pnl' in trades_df.columns:
                    total_pnl = trades_df['pnl'].sum()
                    print(f"   Total P&L: ${total_pnl:.2f}")
                    
                    # Show buy vs sell counts
                    buy_count = len(trades_df[trades_df['side'].str.upper() == 'BUY'])
                    sell_count = len(trades_df[trades_df['side'].str.upper() == 'SELL'])
                    print(f"   Buy orders: {buy_count}")
                    print(f"   Sell orders: {sell_count}")
                    
                    # Show recent trades
                    print(f"\n📈 Recent trades:")
                    print(trades_df.tail(10)[['timestamp', 'side', 'quantity', 'price', 'pnl']].to_string())
                    
                return trades_df
            else:
                print("   Trade history file is empty")
        except Exception as e:
            print(f"   Error reading trade history: {e}")
    
    # Check backtest logs
    if os.path.exists(backtest_file):
        print(f"\n📊 Reading {backtest_file}...")
        try:
            backtest_df = pd.read_csv(backtest_file)
            if not backtest_df.empty:
                print(f"   Found {len(backtest_df)} log entries")
                
                # Filter trade executions
                trades = backtest_df[backtest_df['event_type'] == 'trade']
                if not trades.empty:
                    print(f"   Trade executions: {len(trades)}")
                    
                    # Calculate total P&L from trade executions
                    if 'pnl' in trades.columns:
                        trades['pnl'] = pd.to_numeric(trades['pnl'], errors='coerce')
                        total_pnl = trades['pnl'].sum()
                        print(f"   Total P&L from logs: ${total_pnl:.2f}")
                        
                        # Show buy vs sell
                        buy_trades = trades[trades['side'] == 'buy']
                        sell_trades = trades[trades['side'] == 'sell']
                        print(f"   Buy executions: {len(buy_trades)}")
                        print(f"   Sell executions: {len(sell_trades)}")
                        
                        # Show profit breakdown
                        profitable_sells = sell_trades[sell_trades['pnl'] > 0]
                        losing_sells = sell_trades[sell_trades['pnl'] < 0]
                        print(f"   Profitable sells: {len(profitable_sells)} (Total: ${profitable_sells['pnl'].sum():.2f})")
                        print(f"   Losing sells: {len(losing_sells)} (Total: ${losing_sells['pnl'].sum():.2f})")
                    
                    # Show recent trade executions
                    print(f"\n📈 Recent trade executions:")
                    recent_trades = trades.tail(10)
                    for _, trade in recent_trades.iterrows():
                        side = trade.get('side', 'N/A')
                        price = trade.get('price', 'N/A')
                        pnl = trade.get('pnl', 0)
                        print(f"   {side.upper()} @ ${float(price):,.2f} | P&L: ${float(pnl):.3f}")
                        
                return backtest_df
            else:
                print("   Backtest log file is empty")
        except Exception as e:
            print(f"   Error reading backtest logs: {e}")
    
    print("\n❌ No trade data found")
    return None

if __name__ == "__main__":
    analyze_backtest_profit()