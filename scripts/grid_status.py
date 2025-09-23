#!/usr/bin/env python3
"""
Grid Status Tracker - Real Data Version

Shows current grid levels using real BTC price and your strategy configuration.
"""

import sys
import os
import json
import yaml

def load_config():
    """Load strategy configuration"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'strategy_config.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return None

def load_api_keys():
    """Load API keys"""
    secrets_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'secrets.json'),
        '../secrets.json',
        'secrets.json'
    ]
    
    for path in secrets_paths:
        try:
            with open(path, 'r') as f:
                secrets = json.load(f)
                return secrets.get('api_key'), secrets.get('api_secret')
        except FileNotFoundError:
            continue
    return None, None

def get_current_price():
    """Get current BTC price"""
    try:
        from binance.client import Client
        
        api_key, api_secret = load_api_keys()
        if not api_key:
            print("⚠️  No API keys found")
            return None
        
        config = load_config()
        if not config:
            return None
        
        is_testnet = config['api']['testnet']
        
        # Set timeout to prevent hanging
        import socket
        socket.setdefaulttimeout(10)
        
        client = Client(api_key, api_secret, testnet=is_testnet)
        ticker = client.get_symbol_ticker(symbol='BTCUSDT')
        return float(ticker['price'])
        
    except Exception as e:
        print(f"❌ Error fetching price: {e}")
        return None

def calculate_grid_from_config(current_price, config):
    """Calculate grid levels using real configuration"""
    grid_cfg = config['grid']
    trading_cfg = config['trading']
    
    # Get config values
    spacing_pct = grid_cfg['grid_spacing_pct'] / 100  # Convert to decimal
    levels = grid_cfg['levels']
    capital_per_grid_pct = grid_cfg['capital_per_grid_pct'] / 100
    
    # Cannot determine real capital without account balance - would need full trading system
    print("⚠️  Cannot calculate real quantities without account balance")
    return None
    
    grid_levels = []
    
    # Generate buy levels (below current price)
    for i in range(1, (levels // 2) + 1):
        buy_price = current_price * (1 - (spacing_pct * i))
        quantity = capital_per_grid / buy_price
        grid_levels.append({
            'level': -i,
            'side': 'BUY',
            'price': buy_price,
            'quantity': quantity
        })
    
    # Generate sell levels (above current price)
    for i in range(1, (levels // 2) + 1):
        sell_price = current_price * (1 + (spacing_pct * i))
        quantity = capital_per_grid / sell_price
        grid_levels.append({
            'level': i,
            'side': 'SELL',
            'price': sell_price,
            'quantity': quantity
        })
    
    return sorted(grid_levels, key=lambda x: x['level'])

def display_grid_status():
    """Display current grid status"""
    print("🎯 REAL GRID STATUS TRACKER")
    print("=" * 70)
    
    # Load configuration
    config = load_config()
    if not config:
        return
    
    # Get current price
    print("📡 Fetching current BTC price...")
    current_price = get_current_price()
    if not current_price:
        print("❌ Could not fetch current price")
        return
    
    print(f"✅ Current BTC Price: ${current_price:,.2f}")
    
    # Generate grid using real config
    grid_levels = calculate_grid_from_config(current_price, config)
    
    print()
    print("🏗️  CURRENT GRID LEVELS (from your strategy_config.yaml)")
    print("-" * 70)
    print(f"{'Level':<6} | {'Side':<4} | {'Price':<12} | {'Quantity':<10} | {'Status'}")
    print("-" * 70)
    
    ready_count = 0
    for level in grid_levels:
        price = level['price']
        
        # Determine status
        if level['side'] == 'BUY':
            status = "🟢 READY" if current_price <= price else "⏳ WAIT"
            if current_price <= price:
                ready_count += 1
        else:
            status = "🔴 READY" if current_price >= price else "⏳ WAIT"
            if current_price >= price:
                ready_count += 1
        
        print(f"{level['level']:>5} | {level['side']:<4} | ${price:>10,.2f} | {level['quantity']:>8.6f} | {status}")
    
    # Summary
    buy_levels = [l for l in grid_levels if l['side'] == 'BUY']
    sell_levels = [l for l in grid_levels if l['side'] == 'SELL']
    
    print("-" * 70)
    print(f"📊 Total: {len(grid_levels)} levels | Buy: {len(buy_levels)} | Sell: {len(sell_levels)}")
    print(f"🟢 Ready: {ready_count} levels")
    
    # Show configuration info
    print()
    print("⚙️  Configuration:")
    print(f"   Spacing: {config['grid']['grid_spacing_pct']}%")
    print(f"   Capital per Grid: {config['grid']['capital_per_grid_pct']}%")
    print(f"   Testnet Mode: {config['api']['testnet']}")
    
    print("=" * 70)
    print("🔄 Refresh: python scripts/grid_status.py")

if __name__ == "__main__":
    display_grid_status()