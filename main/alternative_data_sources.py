#!/usr/bin/env python3
"""
📊 ALTERNATIVE CRYPTOCURRENCY DATA SOURCES
Multiple methods to get historical crypto data with better coverage than Yahoo Finance
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import time

def get_binance_data(symbol="BTCUSDT", interval="5m", start_date="2023-01-01", end_date=None):
    """
    Get historical data from Binance API directly
    - Can get years of 5-minute data by chaining requests
    - Free to use
    """
    print(f"📊 Fetching {symbol} data from Binance API ({interval} interval)...")
    
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    # Convert dates to timestamps
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    
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
            
            response = requests.get(base_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                    
                all_data.extend(data)
                current_ts = data[-1][6] + 1  # Next start time
                
                print(f"   📥 Fetched {len(data)} candles (Total: {len(all_data)})")
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


def get_ccxt_data(exchange='binance', symbol='BTC/USDT', timeframe='5m', days_back=365):
    """
    Get data using CCXT library (multiple exchanges)
    """
    try:
        import ccxt
        print(f"📊 Fetching {symbol} data from {exchange} via CCXT ({timeframe} timeframe)...")
        
        # Initialize exchange
        exchange_class = getattr(ccxt, exchange)
        exchange_instance = exchange_class()
        
        # Calculate start time
        since = int((datetime.now() - timedelta(days=days_back)).timestamp() * 1000)
        
        # Fetch OHLCV data
        ohlcv = exchange_instance.fetch_ohlcv(symbol, timeframe, since)
        
        if ohlcv:
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            print(f"✅ CCXT data fetched: {len(df)} candles")
            print(f"📅 Period: {df.index[0]} to {df.index[-1]}")
            print(f"📈 Price range: ${df['Close'].min():,.2f} - ${df['Close'].max():,.2f}")
            
            return df
        else:
            print("❌ No data received from CCXT")
            return pd.DataFrame()
            
    except ImportError:
        print("❌ CCXT library not installed. Install with: pip install ccxt")
        return pd.DataFrame()
    except Exception as e:
        print(f"❌ Error fetching CCXT data: {e}")
        return pd.DataFrame()


def get_cryptocompare_data(symbol='BTC', days_back=365, interval='minute'):
    """
    Get data from CryptoCompare API
    """
    print(f"📊 Fetching {symbol} data from CryptoCompare ({interval} interval)...")
    
    try:
        # Determine API endpoint and limit
        if interval == 'minute':
            endpoint = 'histominute'
            limit = min(2000, days_back * 24 * 60)  # Max 2000 per request
        elif interval == 'hour':
            endpoint = 'histohour' 
            limit = min(2000, days_back * 24)
        else:  # daily
            endpoint = 'histoday'
            limit = min(2000, days_back)
        
        url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
        params = {
            'fsym': symbol,
            'tsym': 'USD',
            'limit': limit,
            'toTs': int(datetime.now().timestamp())
        }
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            if data['Response'] == 'Success':
                candles = data['Data']['Data']
                
                df = pd.DataFrame(candles)
                df['timestamp'] = pd.to_datetime(df['time'], unit='s')
                df.set_index('timestamp', inplace=True)
                
                # Rename columns for backtesting compatibility
                df.rename(columns={
                    'open': 'Open',
                    'high': 'High',
                    'low': 'Low', 
                    'close': 'Close',
                    'volumeto': 'Volume'
                }, inplace=True)
                
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                
                print(f"✅ CryptoCompare data fetched: {len(df)} candles")
                print(f"📅 Period: {df.index[0]} to {df.index[-1]}")
                print(f"📈 Price range: ${df['Close'].min():,.2f} - ${df['Close'].max():,.2f}")
                
                return df
            else:
                print(f"❌ CryptoCompare API error: {data.get('Message', 'Unknown error')}")
                return pd.DataFrame()
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"❌ Error fetching CryptoCompare data: {e}")
        return pd.DataFrame()


def download_kaggle_dataset(dataset_name="jessevent/all-crypto-currencies"):
    """
    Download cryptocurrency dataset from Kaggle
    Requires Kaggle API setup
    """
    try:
        import kaggle
        print(f"📊 Downloading {dataset_name} from Kaggle...")
        
        # Download dataset
        kaggle.api.dataset_download_files(dataset_name, path='./data/', unzip=True)
        
        print("✅ Kaggle dataset downloaded to ./data/ folder")
        print("💡 Look for Bitcoin CSV files in the data folder")
        
        return True
        
    except ImportError:
        print("❌ Kaggle library not installed. Install with: pip install kaggle")
        print("💡 Also need to setup Kaggle API credentials")
        return False
    except Exception as e:
        print(f"❌ Error downloading Kaggle dataset: {e}")
        return False


def test_all_sources():
    """Test all alternative data sources"""
    print("🧪 TESTING ALL ALTERNATIVE DATA SOURCES")
    print("=" * 60)
    
    # Test 1: Binance API (2 years of 5-minute data)
    print("\n1️⃣ Testing Binance API (last 30 days, 5m)...")
    binance_data = get_binance_data(
        symbol="BTCUSDT", 
        interval="5m", 
        start_date="2025-08-25",  # Last 30 days
        end_date="2025-09-25"
    )
    
    if not binance_data.empty:
        print(f"   ✅ Binance: {len(binance_data)} candles")
    
    # Test 2: CCXT (if available)
    print("\n2️⃣ Testing CCXT library...")
    ccxt_data = get_ccxt_data(days_back=30)  # Last 30 days
    
    if not ccxt_data.empty:
        print(f"   ✅ CCXT: {len(ccxt_data)} candles")
    
    # Test 3: CryptoCompare
    print("\n3️⃣ Testing CryptoCompare API...")
    cc_data = get_cryptocompare_data(days_back=30, interval='minute')
    
    if not cc_data.empty:
        print(f"   ✅ CryptoCompare: {len(cc_data)} candles")
    
    # Test 4: Kaggle (just check if possible)
    print("\n4️⃣ Testing Kaggle dataset availability...")
    download_kaggle_dataset()
    
    print(f"\n📊 SUMMARY:")
    print(f"   Binance API: {'✅' if not binance_data.empty else '❌'}")
    print(f"   CCXT: {'✅' if not ccxt_data.empty else '❌'}")  
    print(f"   CryptoCompare: {'✅' if not cc_data.empty else '❌'}")


if __name__ == "__main__":
    test_all_sources()