"""
Grid_Strategy.py

A modular grid trading strategy for Binance Spot (testnet/live), with live k-line polling.
Wraps data fetching, indicator computation, regime detection, grid generation,
backtesting, and live trading into a single class.

Includes deprecation warning filter and position tracking for entry/exit clarity.
Enhanced with grid layer display functionality and FIXED GRID implementation.

Fixed Grid Version - Grid levels remain stable unless major regime changes occur.
"""

from binance.client import Client
import numpy as np
import pandas as pd
import requests
import datetime
import time
import warnings
warnings.filterwarnings(
    "ignore",
    message="Parsing dates involving a day of month without a year specified"
)


class GridStrategy:
    def __init__(self,
                 api_key,
                 api_secret,
                 symbol='BTCUSDT',
                 interval='15m',  # 15-minute bars for grid strategy
                 method='percentage',
                 use_atr=False,
                 order_quantity=0.001,
                 poll_interval=5,
                 testnet=True,
                 simulation_mode=False,
                 regime_change_threshold=0.3,
                 grid_range_multiplier=1.5
                    ):  # New parameter for regime change sensitivity
        """
        Initialize the grid strategy.
        """
        self.symbol = symbol
        self.interval = interval
        self.method = method
        self.use_atr = use_atr
        self.order_qty = order_quantity
        self.poll_interval = poll_interval
        self.last_kline_time = None
        self.stop_trading = False
        self.simulation_mode = simulation_mode
        self.regime_change_threshold = regime_change_threshold
        self.grid_range_multiplier = grid_range_multiplier

        # Track executed grid orders to prevent duplicates
        self.bought_levels = set()
        self.sold_levels = set()
        self.position = 0.0  # current net position in base asset (BTC)

        
        
        # Grid stability tracking
        self.current_regime = None
        self.regime_strength_history = []
        self.grid_generated = False
        self.force_regenerate = False  # Manual trigger flag

        # Binance client
        self.client = Client(api_key, api_secret, tld='com', testnet=testnet)

        # data holders
        self.data = None         # DataFrame of klines with 'Complete' flag
        self.df_ind = None
        self.base_params = None
        self.adjusted_params = None
        self.grid_levels = None

    def get_historical(self, days_back=1):
        """
        Fetch historical klines for warm-up.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        past = now - datetime.timedelta(days=days_back)
        bars = self.client.get_historical_klines(
            symbol=self.symbol,
            interval=self.interval,
            start_str=past.isoformat(),
            end_str=None,
            limit=1000
        )
        df = pd.DataFrame(bars)
        df['date'] = pd.to_datetime(df[0], unit='ms')
        df.columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count',
            'taker_base', 'taker_quote', 'ignore', 'date'
        ]
        df.set_index('date', inplace=True)
        for c in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df['Complete'] = [True]*(len(df)-1) + [False]
        self.data = df
        self.last_kline_time = df.index[-1]
        return df

    def compute_indicators(self):
        df = self.data.copy()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100/(1 + gain/loss))
        self.df_ind = df
        return df

    def define_parameters(self):
        df = self.df_ind
        center = df['close'].tail(100).mean()
        if self.method == 'percentage':
            if self.use_atr:
                high_low = df['high']-df['low']
                tr = pd.concat([
                    high_low,
                    (df['high']-df['close'].shift()).abs(),
                    (df['low']-df['close'].shift()).abs()
                ], axis=1).max(axis=1)
                step = tr.rolling(14).mean().tail(100).mean()
            else:
                step = center * 0.01 * self.grid_range_multiplier
            levels = 10
        else:
            step, levels = 500, 10
        self.base_params = {
            'center_price': center,
            'grid_step_size': step,
            'num_levels': levels
        }
        return self.base_params

    def detect_regime(self):
        df = self.df_ind.tail(24)
        if len(df) < 24:
            return 'sideways', {}
        last = df.iloc[-1]
        price = last['close']
        sma20, sma50, sma200 = last['sma_20'], last['sma_50'], last['sma_200']
        rsi = last['rsi']
        macd, sig = last['macd'], last['macd_signal']
        wnd = min(10, len(df)-1)
        slope20 = (df['sma_20'].iloc[-1] - df['sma_20'].iloc[-wnd]) / wnd
        slope50 = (df['sma_50'].iloc[-1] - df['sma_50'].iloc[-wnd]) / wnd
        tests = [price > sma20, price > sma50, price > sma200,
                 sma20 > sma50, sma50 > sma200,
                 macd > sig, df['macd'].iloc[-1] > df['macd'].iloc[-5],
                 slope20 > 0, slope50 > 0, rsi > 50]
        cnt = sum(tests)
        regime = 'bullish' if cnt >= 7 else 'bearish' if cnt <= 3 else 'sideways'
        info = {
            'price': price,
            'regime_strength': cnt/10,
            'rsi_extreme': 'overbought' if rsi > 90 else 'oversold' if rsi < 10 else None
        }
        return regime, info

    def adjust_grid(self, regime, info):
        bp = self.base_params.copy()
        c = bp['center_price']
        step = bp['grid_step_size']
        lvl = bp['num_levels']
        if regime == 'bullish':
            bp.update({'center_price': c*0.98, 'grid_step_size': step*1.2,
                       'buy_levels': int(lvl*1.5), 'sell_levels': int(lvl*0.7)})
        elif regime == 'bearish':
            bp.update({'center_price': c*1.02, 'grid_step_size': step*1.2,
                       'buy_levels': int(lvl*0.7), 'sell_levels': int(lvl*1.5)})
        else:
            bp.update({'grid_step_size': step*0.8,
                      'buy_levels': lvl, 'sell_levels': lvl})
        if info.get('rsi_extreme') == 'overbought':
            bp['sell_levels'] = int(bp['sell_levels']*0.8)
        if info.get('rsi_extreme') == 'oversold':
            bp['buy_levels'] = int(bp['buy_levels']*0.8)
        self.adjusted_params = bp
        return bp

    def generate_grid(self):
        ap = self.adjusted_params
        cp, step = ap['center_price'], ap['grid_step_size']
        buy, sell = ap['buy_levels'], ap['sell_levels']
        levels = [
            cp - i*step for i in range(1, buy+1)] + [cp + i*step for i in range(1, sell+1)]
        levels.sort()
        self.grid_levels = levels
        return levels

    def print_grid_layers(self, current_price=None):
        """
        Print all grid layers with their status and layer numbers.
        Shows which levels are available for buying, bought and waiting to sell, etc.
        """
        if not self.grid_levels:
            print("No grid levels generated yet.")
            return

        print("\n" + "="*80)
        print(f"GRID LAYERS - {self.symbol}")
        print("="*80)

        if current_price:
            print(f"Current Price: {current_price:.6f}")

        center_price = self.adjusted_params.get('center_price', 0)
        print(f"Center Price:  {center_price:.6f}")
        print(f"Position:      {self.position:.6f} {self.symbol[:3]}")
        print("-"*80)

        # Sort levels and assign layer numbers
        sorted_levels = sorted(self.grid_levels)

        for i, level in enumerate(sorted_levels, 1):
            # Determine status
            if level in self.bought_levels:
                # Check if this bought level has a corresponding sell target
                higher_levels = [l for l in sorted_levels if l > level]
                if higher_levels:
                    sell_target = higher_levels[0]
                    if (level, sell_target) in self.sold_levels:
                        status = "COMPLETED"
                        action = f"(Bought at {level:.6f}, Sold at {sell_target:.6f})"
                    else:
                        status = "HOLD"
                        action = f"(Bought, Target: {sell_target:.6f})"
                else:
                    status = "HOLD"
                    action = "(Bought, No sell target)"
            else:
                if current_price and level < current_price:
                    status = "BUY READY"
                    action = "(Available for buying)"
                elif current_price and level > current_price:
                    status = "SELL LEVEL"
                    action = "(Above current price)"
                else:
                    status = "AVAILABLE"
                    action = "(Waiting)"

            # Color coding for better visibility
            if status == "BUY READY":
                print(f"Layer {i:2d}: {level:10.6f} | 🟢 {status:12} {action}")
            elif status == "HOLD":
                print(f"Layer {i:2d}: {level:10.6f} | 🟡 {status:12} {action}")
            elif status == "COMPLETED":
                print(f"Layer {i:2d}: {level:10.6f} | ✅ {status:12} {action}")
            elif status == "SELL LEVEL":
                print(f"Layer {i:2d}: {level:10.6f} | 🔴 {status:12} {action}")
            else:
                print(f"Layer {i:2d}: {level:10.6f} | ⚪ {status:12} {action}")

        print("-"*80)
        print(
            f"Total Layers: {len(sorted_levels)} | Bought: {len(self.bought_levels)} | Completed&Sold: {len(self.sold_levels)}")
        print("="*80 + "\n")

    def execute_grid_trades(self, price, simulation_mode=False):
            """
            FIXED: Enhanced grid trade execution with proper sell logic
            """
            if not self.adjusted_params or not self.grid_levels:
                print("[WARNING] No grid parameters or levels available")
                return

            center_price = self.adjusted_params['center_price']
            # 0.1% price tolerance for triggering orders
            price_tolerance = center_price * 0.001

            print(f"[TRADE CHECK] Price: {price:.2f} | Position: {self.position:.6f} BTC")
            if self.bought_levels:
                print(f"[TRADE CHECK] Bought levels waiting to sell: {sorted(self.bought_levels)}")

            # ✨ Partial‐sell: limit to one sell per execution cycle
            sells_this_cycle = 0
            max_sells = 1

            # ===== BUY logic (levels below center_price) =====
            for lvl in self.grid_levels:
                if lvl < center_price and price <= (lvl + price_tolerance) and lvl not in self.bought_levels:
                    try:
                        if simulation_mode:
                            print(f"[SIM BUY] Would buy at level {lvl:.6f} @ price {price:.6f}")
                            order = {"status": "FILLED", "executedQty": str(self.order_qty)}
                        else:
                            order = self.client.order_market_buy(
                                symbol=self.symbol,
                                quantity=self.order_qty
                            )

                        if order.get("status") == "FILLED":
                            self.bought_levels.add(lvl)
                            self.position += self.order_qty
                            mode = "[SIM BUY]" if simulation_mode else "[BUY]"
                            print(f"{mode} executed at {lvl:.6f} @ {price:.6f} | New pos: {self.position:.6f} BTC")

                    except Exception as e:
                        print(f"[ERROR] Buy order failed at level {lvl:.6f}: {e}")
                        continue

            # ===== SELL logic (next higher level) =====
            for bought_lvl in sorted(self.bought_levels):
                if sells_this_cycle >= max_sells:
                    break

                higher_levels = [l for l in self.grid_levels if l > bought_lvl]
                if not higher_levels:
                    continue

                sell_target = higher_levels[0]
                print(f"[SELL CHECK] Target sell level: {sell_target:.6f} (Current price: {price:.6f})")

                should_sell = price >= (sell_target - price_tolerance)
                not_sold_yet = (bought_lvl, sell_target) not in self.sold_levels
                print(f"[SELL CHECK] Should sell: {should_sell} | Not sold yet: {not_sold_yet}")

                if should_sell and not_sold_yet:
                    try:
                        if simulation_mode:
                            print(f"[SIM SELL] Would sell at {sell_target:.6f} @ price {price:.6f}")
                            order = {"status": "FILLED", "executedQty": str(self.order_qty)}
                        else:
                            order = self.client.order_market_sell(
                                symbol=self.symbol,
                                quantity=self.order_qty
                            )

                        if order.get("status") == "FILLED":
                            self.sold_levels.add((bought_lvl, sell_target))
                            self.position -= self.order_qty
                            self.bought_levels.discard(bought_lvl)
                            sells_this_cycle += 1
                            mode = "[SIM SELL]" if simulation_mode else "[SELL]"
                            print(f"{mode} executed at {sell_target:.6f} @ {price:.6f} | New pos: {self.position:.6f} BTC")
                            print(f"[SELL COMPLETE] Removed {bought_lvl:.6f} from bought_levels")

                    except Exception as e:
                        print(f"[ERROR] Sell order failed at level {sell_target:.6f}: {e}")
                        continue
                else:
                    if not should_sell:
                        print(f"[SELL WAIT] Price {price:.6f} not high enough for target {sell_target:.6f}")
                    if not not_sold_yet:
                        print(f"[SELL FINISH] Already sold this pair: {bought_lvl:.6f} -> {sell_target:.6f}")


    def debug_sell_status(self, current_price):
        """
        Debug function to show detailed sell status WITH formatted grid layers
        """
        print(f"\n{'='*60}")
        print(f"DYNAMIC GRID - SELL STATUS DEBUG")
        print(f"{'='*60}")
        print(f"Current Price: {current_price:.6f}")
        print(f"Current Position: {self.position:.6f} BTC")
        print(
            f"Center Price: {self.adjusted_params.get('center_price', 0):.6f}")
        print(f"-" * 60)

        print(f"Bought Levels ({len(self.bought_levels)}):")
        for bought_lvl in sorted(self.bought_levels):
            print(f"  - {bought_lvl:.6f}")

        print(f"Completed Sales ({len(self.sold_levels)}):")
        for sale in sorted(self.sold_levels):
            buy_price, sell_price = sale
            profit = (sell_price - buy_price) * self.order_qty
            print(
                f"  - Bought: {buy_price:.6f} -> Sold: {sell_price:.6f} (Profit: ${profit:.2f})")

        # ADD THE FORMATTED GRID LAYERS HERE
        print(f"\nFORMATTED GRID LAYERS:")
        print(f"-" * 80)

        if self.grid_levels:
            sorted_levels = sorted(self.grid_levels)

            for i, level in enumerate(sorted_levels, 1):
                # Determine status
                if level in self.bought_levels:
                    higher_levels = [l for l in sorted_levels if l > level]
                    if higher_levels:
                        sell_target = higher_levels[0]
                        if (level, sell_target) in self.sold_levels:
                            status = "COMPLETED"
                            action = f"(Bought at {level:.6f}, Sold at {sell_target:.6f})"
                        else:
                            status = "HOLD"
                            action = f"(Bought, Target: {sell_target:.6f})"
                    else:
                        status = "HOLD"
                        action = "(Bought, No sell target)"
                else:
                    if current_price and level < current_price:
                        status = "BUY READY"
                        action = "(Available for buying)"
                    elif current_price and level > current_price:
                        status = "SELL LEVEL"
                        action = "(Above current price)"
                    else:
                        status = "AVAILABLE"
                        action = "(Waiting)"

                # Color coding for better visibility
                if status == "BUY READY":
                    print(
                        f"Layer {i:2d}: {level:10.6f} | 🟢 {status:12} {action}")
                elif status == "HOLD":
                    print(
                        f"Layer {i:2d}: {level:10.6f} | 🟡 {status:12} {action}")
                elif status == "COMPLETED":
                    print(
                        f"Layer {i:2d}: {level:10.6f} | ✅ {status:12} {action}")
                elif status == "SELL LEVEL":
                    print(
                        f"Layer {i:2d}: {level:10.6f} | 🔴 {status:12} {action}")
                else:
                    print(
                        f"Layer {i:2d}: {level:10.6f} | ⚪ {status:12} {action}")

        print(f"{'='*60}\n")

    def force_sell_check(self, current_price):
        """
        Manual function to check what should be selling right now
        """
        print(
            f"\n[FORCE SELL CHECK] Analyzing sell opportunities at price {current_price:.6f}")

        if not self.bought_levels:
            print("[FORCE SELL CHECK] No bought positions to sell")
            return

        price_tolerance = self.adjusted_params.get(
            'center_price', current_price) * 0.001

        for bought_lvl in sorted(self.bought_levels):
            higher_levels = sorted(
                [l for l in self.grid_levels if l > bought_lvl])

            if higher_levels:
                sell_target = higher_levels[0]
                should_sell = current_price >= (sell_target - price_tolerance)
                already_sold = (bought_lvl, sell_target) in self.sold_levels

                print(f"[FORCE SELL CHECK] Bought: {bought_lvl:.6f}")
                print(f"[FORCE SELL CHECK] Target: {sell_target:.6f}")
                print(f"[FORCE SELL CHECK] Current: {current_price:.6f}")
                print(f"[FORCE SELL CHECK] Should sell: {should_sell}")
                print(f"[FORCE SELL CHECK] Already sold: {already_sold}")
                print(
                    f"[FORCE SELL CHECK] Difference: {current_price - sell_target:.6f}")
                print("-" * 40)

    def should_regenerate_grid(self, new_regime, new_strength):
        """
        Determine if grid should be regenerated based on regime changes.
        """
        if self.force_regenerate:
            print("[MANUAL TRIGGER] Grid regeneration forced")
            self.force_regenerate = False
            return True

        if not self.grid_generated:
            print("[STARTUP] Initial grid generation")
            return True

        # Major regime change detection
        if self.current_regime and new_regime != self.current_regime:
            print(f"[REGIME CHANGE] {self.current_regime} -> {new_regime}")
            return True

        # Significant strength change detection
        if len(self.regime_strength_history) >= 5:
            avg_strength = sum(self.regime_strength_history[-5:]) / 5
            strength_change = abs(new_strength - avg_strength)
            if strength_change > self.regime_change_threshold:
                print(
                    f"[STRENGTH CHANGE] Average: {avg_strength:.2f} -> Current: {new_strength:.2f} (Change: {strength_change:.2f})")
                return True

        return False

    def force_grid_regeneration(self):
        """
        Manually trigger grid regeneration on next poll.
        """
        self.force_regenerate = True
        print("[MANUAL] Grid regeneration will occur on next poll")

    def update_regime_tracking(self, regime, strength):
        """
        Update regime tracking variables.
        """
        self.current_regime = regime
        self.regime_strength_history.append(strength)

        # Keep only last 10 strength values
        if len(self.regime_strength_history) > 10:
            self.regime_strength_history.pop(0)

    def polling_loop(self):
        """
        Poll for new completed klines, update grid, and trade.
        """
        print("Starting live k-line polling. Ctrl+C to stop.")
        poll_count = 0
        current_price = None

        # Get initial current price from the most recent kline
        try:
            klines = self.client.get_klines(
                symbol=self.symbol, interval=self.interval, limit=1)
            if klines:
                current_price = float(klines[0][4])  # close price
        except Exception as e:
            print(f"[WARNING] Could not fetch initial price: {e}")

        try:
            while not self.stop_trading:
                poll_count += 1

                # Get current kline data for real-time price
                klines = self.client.get_klines(
                    symbol=self.symbol, interval=self.interval, limit=2)

                if klines:
                    # Update current price from the latest (incomplete) kline
                    # close price of current kline
                    current_price = float(klines[-1][4])

                    # Periodic detailed status (moved BEFORE new kline processing)
                    if poll_count % 30 == 0:
                        self.debug_sell_status(current_price)

                    # Regular status updates - REMOVED force_sell_check from here
                    if poll_count % 10 == 0:
                        price_str = f"{current_price:.6f}" if current_price else "N/A"
                        grid_status = "FIXED" if self.grid_generated else "PENDING"
                        print(
                            f"{'*' * 10} Poll {poll_count} | Price: {price_str} | Grid: {grid_status} | Regime: {self.current_regime} {'*' * 10}")
                    else:
                        price_str = f"{current_price:.2f}" if current_price else "N/A"
                        print(f"Current price of BTC is {price_str}")

                    # NEW KLINE PROCESSING - This is where the real action happens
                    if len(klines) >= 2:
                        completed = klines[-2]
                        time_ms = completed[0]
                        ts = datetime.datetime.fromtimestamp(
                            time_ms/1000, tz=datetime.timezone.utc)
                        ts = ts.replace(tzinfo=None)

                        if self.last_kline_time is None or ts > self.last_kline_time:
                            print(
                                f"\n[NEW KLINE] Processing completed kline at {ts}")

                            # Add new completed kline row, updating core columns
                            open_price = float(completed[1])
                            high_price = float(completed[2])
                            low_price = float(completed[3])
                            close_price = float(completed[4])
                            volume = float(completed[5])

                            # Construct a partial row dict for key columns
                            new_row = {
                                'open': open_price,
                                'high': high_price,
                                'low': low_price,
                                'close': close_price,
                                'volume': volume,
                                'Complete': True
                            }

                            # Append new row to data DataFrame
                            self.data = pd.concat([
                                self.data,
                                pd.DataFrame(new_row, index=[ts])
                            ], axis=0)

                            # Always recompute indicators for regime detection
                            self.compute_indicators()
                            self.define_parameters()
                            regime, info = self.detect_regime()

                            # Check if grid regeneration is needed
                            should_regenerate = self.should_regenerate_grid(
                                regime, info['regime_strength'])

                            if should_regenerate:
                                print(
                                    f"\n[GRID REGENERATION] Updating grid structure...")
                                self.adjust_grid(regime, info)
                                self.generate_grid()
                                self.grid_generated = True
                                print(
                                    f"[GRID UPDATED] New grid with {len(self.grid_levels)} levels generated")

                                # Print new grid layers
                                self.print_grid_layers(
                                    current_price=close_price)
                            else:
                                print(
                                    f"[GRID STABLE] Using existing grid | Regime: {regime} | Strength: {info['regime_strength']:.2f}")

                            # Update regime tracking regardless of regeneration
                            self.update_regime_tracking(
                                regime, info['regime_strength'])

                            # IMPROVED: Execute trades with proper diagnostic flow
                            if self.grid_levels:
                                # First, run diagnostic check if we have positions to analyze
                                if self.bought_levels:
                                    print(
                                        f"\n[PRE-TRADE ANALYSIS] Checking {len(self.bought_levels)} bought positions before executing trades:")
                                    self.force_sell_check(close_price)

                                # Then execute the actual trades
                                print(
                                    f"[TRADE EXECUTION] Executing grid trades at price {close_price:.6f}")
                                self.execute_grid_trades(
                                    close_price, simulation_mode=self.simulation_mode)

                                # Post-trade summary
                                if self.bought_levels or self.sold_levels:
                                    print(
                                        f"[POST-TRADE] Position: {self.position:.6f} BTC | Active: {len(self.bought_levels)} | Completed: {len(self.sold_levels)}")

                            self.last_kline_time = ts

                        else:
                            # No new kline data - show periodic status while waiting
                            if poll_count % 50 == 0:  # Every 50 checks, show a status update
                                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                                price_str = f"{current_price:.6f}" if current_price else "N/A"
                                grid_status = f"{len(self.grid_levels)} levels" if self.grid_levels else "Not generated"
                                print(
                                    f"\n[{current_time}] Waiting for new kline | Price: {price_str} | Position: {self.position:.6f} BTC | Grid: {grid_status}")

                                # Optional: Quick sell check even when no new kline (for missed opportunities)
                                if self.bought_levels and current_price:
                                    print(
                                        f"[WAITING STATUS] Checking if any sells should trigger at current price {current_price:.6f}")
                                    self.force_sell_check(current_price)

                    time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print(f"\n{'='*60}")
            print("Polling stopped by user.")
            final_price = f"{current_price:.6f}" if current_price else "N/A"
            print(f"Final Price: {final_price}")
            print(f"Final Position: {self.position:.6f} BTC")
            print(f"Final Regime: {self.current_regime}")
            print(
                f"Grid Levels: {len(self.grid_levels) if self.grid_levels else 0}")
            print(f"Total Polls: {poll_count}")

            # Final diagnostic check
            if self.bought_levels and current_price:
                print(f"\nFINAL SELL STATUS:")
                self.force_sell_check(current_price)

            print(f"{'='*60}")

    def start_trading(self, historic_days=1):
        """
        Warm-up then enter live polling.
        """
        print("="*60)
        print("INITIALIZING FIXED GRID STRATEGY")
        print("="*60)

        self.get_historical(days_back=historic_days)
        self.compute_indicators()
        self.define_parameters()
        regime, info = self.detect_regime()

        # Generate initial grid - this will be the stable grid
        self.adjust_grid(regime, info)
        self.generate_grid()
        self.grid_generated = True
        self.update_regime_tracking(regime, info['regime_strength'])

        print(f"INITIAL SETUP COMPLETE:")
        print(f"- Regime: {regime}")
        print(f"- Strength: {info['regime_strength']:.2f}")
        print(f"- Grid Levels: {len(self.grid_levels)}")
        print(f"- Regeneration Threshold: {self.regime_change_threshold}")
        print("="*60)

        # Print initial grid setup
        if self.df_ind is not None and not self.df_ind.empty:
            current_price = self.df_ind['close'].iloc[-1]
            self.print_grid_layers(current_price=current_price)

        self.polling_loop()

    def get_grid_status(self):
        """
        Return current grid status information.
        """
        return {
            'total_levels': len(self.grid_levels) if self.grid_levels else 0,
            'bought_levels': len(self.bought_levels),
            'completed_trades': len(self.sold_levels),
            'current_regime': self.current_regime,
            'grid_generated': self.grid_generated,
            'position': self.position
        }


# Example usage
if __name__ == "__main__":
    import cred3
    strat = GridStrategy(
        api_key=cred3.api_key,
        api_secret=cred3.secret_key,
        symbol='BTCUSDT',
        interval='1m',
        method='percentage',
        use_atr=False,
        order_quantity=0.001,
        poll_interval=5,
        testnet=True,  # Set to True for testnet
        simulation_mode=True,  # Set to True for testing without real trades
        # Adjust sensitivity (0.1 = very sensitive, 0.5 = less sensitive)
        regime_change_threshold=0.3
    )
    strat.start_trading(historic_days=0.5)
