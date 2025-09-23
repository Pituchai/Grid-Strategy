#!/usr/bin/env python3
"""
Quick account balance checker
"""
import json
import sys
import os
from binance.client import Client

def check_balance():
    # Load API keys (try multiple locations)
    secrets_paths = [
        '../secrets.json',  # From scripts/ directory
        'secrets.json',     # From project root
        os.path.join(os.path.dirname(__file__), '..', 'secrets.json')  # Absolute path
    ]
    
    api_key = None
    api_secret = None
    
    for secrets_path in secrets_paths:
        try:
            with open(secrets_path, 'r') as f:
                secrets = json.load(f)
                api_key = secrets.get('api_key')
                api_secret = secrets.get('api_secret')
                print(f"✅ Found secrets.json at: {secrets_path}")
                break
        except FileNotFoundError:
            continue
    
    if not api_key or not api_secret:
        print("❌ secrets.json not found in any expected location!")
        print("📁 Expected locations:")
        for path in secrets_paths:
            print(f"   - {os.path.abspath(path)}")
        print("\n💡 Create secrets.json in project root with:")
        print("""{
  "api_key": "your_binance_api_key",
  "api_secret": "your_binance_secret_key"
}""")
        return
    
    # Initialize client (testnet by default)
    client = Client(api_key, api_secret, testnet=True)
    
    try:
        print("🔍 Checking Account Balance...")
        print("=" * 40)
        
        account_info = client.get_account()
        
        # Show main balances
        important_assets = ['USDT', 'BTC', 'ETH']
        
        for asset in important_assets:
            balance_info = [b for b in account_info['balances'] if b['asset'] == asset]
            if balance_info:
                free = float(balance_info[0]['free'])
                locked = float(balance_info[0]['locked'])
                total = free + locked
                
                if total > 0:
                    print(f"💰 {asset}: {total:.6f} (Free: {free:.6f}, Locked: {locked:.6f})")
        
        # Show all non-zero balances
        print("\n📊 All Non-Zero Balances:")
        print("-" * 40)
        
        for balance in account_info['balances']:
            free = float(balance['free'])
            locked = float(balance['locked'])
            total = free + locked
            
            if total > 0:
                print(f"   {balance['asset']}: {total:.8f}")
        
        print(f"\n🌐 Trading on: {'Testnet' if client.PRIVATE_API_VERSION else 'Live'}")
        
    except Exception as e:
        print(f"❌ Error checking balance: {e}")

if __name__ == "__main__":
    check_balance()