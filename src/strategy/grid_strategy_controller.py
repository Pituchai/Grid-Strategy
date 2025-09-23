# grid_strategy_controller.py
import pandas as pd 
import time
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.cycle_tracker import CycleTracker
from strategy.volatility_manager import VolatilityManager

class GridStrategyController:
    """
    Main controller for a Trailing Grid Trading Bot.
    Ties together all modules and handles dynamic, trailing grid logic.
    """

    def __init__(self, config_manager, event_logger, position_manager, strategy_state, risk_manager, client):
        self.cfg = config_manager
        self.logger = event_logger
        self.pm = position_manager
        self.state = strategy_state
        self.risk = risk_manager
        self.client = client  # Binance (or other) API client

        # Load and set grid/trailing parameters from config
        grid_cfg = self.cfg.get_grid_config()
        self.trailing_enabled = grid_cfg.get("trailing_enabled", True)
        self.trailing_direction = grid_cfg.get("trailing_direction", "up")
        self.trailing_threshold_pct = grid_cfg.get("trailing_threshold_pct", 0.03)
        self.trailing_ma_period = grid_cfg.get("trailing_ma_period", 50)

        # Restore or initialize state
        st = self.state.get_strategy_status()
        self.grid_levels = st.get("grid_levels", [])
        self.bought_levels = set(st.get("bought_levels", []))
        self.sold_levels = set(tuple(pair) for pair in st.get("sold_levels", []))
        self.current_regime = st.get("current_regime", None)
        self.regime_strength_history = st.get("regime_strength_history", [])
        self.grid_generated = st.get("grid_generated", False)
        self.force_regenerate = False
        self.position = 0.0
        self.total_capital = 0.0
        self.capital_per_grid = 0.0
        
        # Initialize cycle tracking
        self.cycle_tracker = CycleTracker(self.logger, self.cfg)
        
        # Initialize volatility management
        self.volatility_manager = VolatilityManager(self.cfg, self.logger)
    
    # ---- Load the Historical Data from binance ----
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


    # ---- INDICATOR/STRATEGY METHODS ----
    def compute_indicators(self, df):
        """
        Add moving averages or other indicators to your DataFrame.
        """
        # Example (uses pandas):
        df[f'ma_{self.trailing_ma_period}'] = df['close'].rolling(self.trailing_ma_period).mean()
        return df

    def define_parameters(self, df_ind):
        """
        Define base grid parameters based on current market price with volatility adjustments.
        """
        current_price = df_ind['close'].iloc[-1]
        grid_cfg = self.cfg.get_grid_config()
        
        # Base parameters from config
        base_grid_range_pct = grid_cfg.get('grid_range_pct', 2.5) / 100
        base_grid_spacing_pct = grid_cfg.get('grid_spacing_pct', 0.5) / 100
        levels = grid_cfg.get('levels', 10)
        base_capital_per_grid = grid_cfg.get('capital_per_grid_pct', 10.0)
        
        # Get volatility-adjusted parameters
        vol_params = self.volatility_manager.get_adjusted_grid_params(
            base_grid_spacing_pct * 100,  # Convert back to percentage
            base_capital_per_grid,
            df_ind
        )
        
        # Apply volatility adjustments
        grid_spacing_pct = vol_params['adjusted_spacing_pct'] / 100  # Convert to decimal
        adjusted_capital_per_grid = vol_params['adjusted_position_size']
        
        print(f"📊 Volatility Analysis:")
        print(f"   Regime: {self.volatility_manager.get_regime_description(vol_params['regime'])}")
        print(f"   Volatility Ratio: {vol_params['volatility_ratio']:.4f}")
        print(f"   Spacing Adjustment: {base_grid_spacing_pct*100:.2f}% → {vol_params['adjusted_spacing_pct']:.2f}%")
        print(f"   Position Adjustment: {base_capital_per_grid:.1f}% → {adjusted_capital_per_grid:.1f}%")
        
        # Store adjusted values for use in quantity calculation
        self.adjusted_capital_per_grid = adjusted_capital_per_grid
        
        grid_range_pct = base_grid_range_pct
        
        # Calculate grid boundaries
        upper_bound = current_price * (1 + grid_range_pct)
        lower_bound = current_price * (1 - grid_range_pct)
        
        return {
            'center_price': current_price,
            'upper_bound': upper_bound,
            'lower_bound': lower_bound,
            'grid_spacing_pct': grid_spacing_pct,
            'levels': levels,
            'range_pct': grid_range_pct
        }
    
    def generate_grid_levels(self, current_price):
        """
        Simple method to generate grid levels for dashboard display.
        """
        grid_cfg = self.cfg.get_grid_config()
        grid_spacing_pct = grid_cfg.get('grid_spacing_pct', 0.5) / 100
        levels = grid_cfg.get('levels', 10)
        
        # Apply volatility adjustments if available
        if hasattr(self, 'adjusted_capital_per_grid'):
            spacing_pct = grid_spacing_pct * 0.7  # Use adjusted spacing from volatility manager
        else:
            spacing_pct = grid_spacing_pct
        
        grid_levels = []
        
        # Generate buy levels (below current price)
        for i in range(1, (levels // 2) + 1):
            buy_price = current_price * (1 - (spacing_pct * i))
            grid_levels.append({
                'price': buy_price,
                'side': 'BUY',
                'level': -i,
                'quantity': self.calculate_order_quantity(buy_price),
                'status': 'pending'
            })
        
        # Generate sell levels (above current price)
        for i in range(1, (levels // 2) + 1):
            sell_price = current_price * (1 + (spacing_pct * i))
            grid_levels.append({
                'price': sell_price,
                'side': 'SELL', 
                'level': i,
                'quantity': self.calculate_order_quantity(sell_price),
                'status': 'pending'
            })
        
        return grid_levels

    def detect_regime(self, df_ind):
        """
        Detect market regime (bull, bear, sideways).
        """
        # (implement your logic here)
        pass

    def adjust_grid(self, base_params, regime, info):
        """
        Adjust grid parameters based on regime and info.
        """
        # (implement your logic here)
        pass

    def generate_grid(self, adjusted_params):
        """
        Generate new grid levels with optimal 0.5% spacing.
        Creates 10 levels with 5 buy orders below center and 5 sell orders above.
        """
        center_price = adjusted_params['center_price']
        grid_spacing_pct = adjusted_params['grid_spacing_pct']
        levels = adjusted_params['levels']
        
        # Generate grid levels symmetrically around center
        grid_levels = []
        
        # Generate 5 levels below center (buy orders)
        for i in range(1, (levels // 2) + 1):
            buy_price = center_price * (1 - (grid_spacing_pct * i))
            grid_levels.append({
                'price': buy_price,
                'side': 'BUY',
                'level': -i,
                'quantity': self.calculate_order_quantity(buy_price),
                'status': 'pending'
            })
        
        # Generate 5 levels above center (sell orders)  
        for i in range(1, (levels // 2) + 1):
            sell_price = center_price * (1 + (grid_spacing_pct * i))
            grid_levels.append({
                'price': sell_price,
                'side': 'SELL', 
                'level': i,
                'quantity': self.calculate_order_quantity(sell_price),
                'status': 'pending'
            })
        
        # Sort by price (lowest to highest)
        grid_levels.sort(key=lambda x: x['price'])
        self.grid_levels = grid_levels
        
        self.logger.log_signal("grid_generated", {
            "center_price": center_price,
            "total_levels": len(grid_levels),
            "price_range": f"{grid_levels[0]['price']:.2f} - {grid_levels[-1]['price']:.2f}",
            "spacing_pct": grid_spacing_pct * 100
        })
        
        # Print current grid levels to console
        self.print_grid_levels(center_price)
        
        return grid_levels

    def print_grid_levels(self, current_price):
        """
        Print current grid levels in a clean table format.
        """
        if not self.grid_levels:
            print("🏗️  No grid levels available")
            return
        
        print(f"\n🎯 CURRENT GRID LEVELS (BTC: ${current_price:,.2f})")
        print("=" * 70)
        print(f"{'Level':<6} | {'Side':<4} | {'Price':<12} | {'Quantity':<10} | {'Status'}")
        print("-" * 70)
        
        for level in sorted(self.grid_levels, key=lambda x: x['level']):
            price = level['price']
            
            # Determine status based on current price
            if level['side'] == 'BUY':
                status = "🟢 READY" if current_price <= price else "⏳ WAIT"
            else:
                status = "🔴 READY" if current_price >= price else "⏳ WAIT"
            
            print(f"{level['level']:>5} | {level['side']:<4} | ${price:>10,.2f} | {level['quantity']:>8.6f} | {status}")
        
        # Summary
        buy_levels = [l for l in self.grid_levels if l['side'] == 'BUY']
        sell_levels = [l for l in self.grid_levels if l['side'] == 'SELL']
        ready_buys = len([l for l in buy_levels if current_price <= l['price']])
        ready_sells = len([l for l in sell_levels if current_price >= l['price']])
        
        print("-" * 70)
        print(f"📊 Total: {len(self.grid_levels)} levels | Buy: {len(buy_levels)} | Sell: {len(sell_levels)}")
        print(f"🟢 Ready: {ready_buys + ready_sells} levels | Buy: {ready_buys} | Sell: {ready_sells}")
        print("=" * 70)

    def print_trade_update(self, executed_level, side, current_price):
        """
        Print a compact update showing which level was executed and remaining levels.
        """
        print(f"\n📈 TRADE UPDATE - {side} Level {executed_level['level']} EXECUTED")
        print("-" * 50)
        
        # Show remaining ready levels
        buy_ready = []
        sell_ready = []
        
        for level in self.grid_levels:
            if level['side'] == 'BUY' and current_price <= level['price'] and level['level'] not in self.bought_levels:
                buy_ready.append(level)
            elif level['side'] == 'SELL' and current_price >= level['price'] and (level['level'], level['price']) not in self.sold_levels:
                sell_ready.append(level)
        
        print(f"🟢 Ready BUY levels: {len(buy_ready)}")
        for level in sorted(buy_ready, key=lambda x: x['level'])[:3]:  # Show top 3
            print(f"   L{level['level']}: ${level['price']:,.2f}")
        
        print(f"🔴 Ready SELL levels: {len(sell_ready)}")
        for level in sorted(sell_ready, key=lambda x: x['level'])[:3]:  # Show top 3
            print(f"   L{level['level']}: ${level['price']:,.2f}")
        
        print(f"💰 Current Position: {self.position:.6f} BTC")
        print("-" * 50)

    def print_compact_grid_status(self, current_price):
        """
        Print a compact grid status showing only the nearest levels.
        """
        if not self.grid_levels:
            return
        
        print("   📋 Current Grid Levels:")
        
        # Find levels close to current price (within 1% up and down)
        close_levels = []
        for level in self.grid_levels:
            distance_pct = abs(level['price'] - current_price) / current_price * 100
            if distance_pct <= 2.0:  # Show levels within 2%
                close_levels.append(level)
        
        # If no close levels, show 2 nearest on each side
        if not close_levels:
            sorted_levels = sorted(self.grid_levels, key=lambda x: abs(x['price'] - current_price))
            close_levels = sorted_levels[:4]  # Show 4 nearest levels
        
        # Sort by level number
        close_levels.sort(key=lambda x: x['level'])
        
        for level in close_levels:
            price = level['price']
            distance = price - current_price
            distance_pct = distance / current_price * 100
            
            # Status
            if level['side'] == 'BUY':
                status = "🟢 READY" if current_price <= price else "⏳ WAIT"
            else:
                status = "🔴 READY" if current_price >= price else "⏳ WAIT"
            
            print(f"      L{level['level']:2d} | {level['side']:<4} | ${price:8,.2f} | {distance_pct:+5.2f}% | {status}")

    def calculate_order_quantity(self, price):
        """
        Calculate order quantity based on volatility-adjusted capital allocation per grid.
        """
        # Use volatility-adjusted capital allocation if available
        if hasattr(self, 'adjusted_capital_per_grid'):
            capital_per_grid_pct = self.adjusted_capital_per_grid / 100
        else:
            # Fallback to base config
            grid_cfg = self.cfg.get_grid_config()
            capital_per_grid_pct = grid_cfg.get('capital_per_grid_pct', 10.0) / 100
        
        if self.total_capital == 0:
            # Get account balance to determine total capital
            try:
                account_info = self.client.get_account()
                usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                                    if asset['asset'] == 'USDT'][0])
                self.total_capital = usdt_balance
            except Exception as e:
                self.logger.log_error(f"Failed to get account balance - stopping bot", {"error": str(e)})
                raise Exception(f"Cannot access account balance: {e}. Bot stopped for safety.")
        
        self.capital_per_grid = self.total_capital * capital_per_grid_pct
        quantity = self.capital_per_grid / price
        
        # Round to appropriate precision for BTC (6 decimal places)
        quantity = round(quantity, 6)
        
        return quantity

    def initialize_capital(self, initial_capital=None):
        """
        Initialize total capital for grid allocation.
        """
        if initial_capital:
            self.total_capital = initial_capital
        else:
            try:
                account_info = self.client.get_account()
                usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                                    if asset['asset'] == 'USDT'][0])
                self.total_capital = usdt_balance
            except Exception as e:
                self.logger.log_error(f"Failed to initialize capital - stopping bot", {"error": str(e)})
                raise Exception(f"Cannot access account balance for capital initialization: {e}. Bot stopped for safety.")
        
        grid_cfg = self.cfg.get_grid_config()
        capital_per_grid_pct = grid_cfg.get('capital_per_grid_pct', 10.0) / 100
        self.capital_per_grid = self.total_capital * capital_per_grid_pct
        
        self.logger.log_signal("capital_initialized", {
            "total_capital": self.total_capital,
            "capital_per_grid": self.capital_per_grid,
            "allocation_pct": capital_per_grid_pct * 100
        })

    def check_account_balance(self):
        """
        Check account balance for trading.
        """
        try:
            account_info = self.client.get_account()
            usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                               if asset['asset'] == 'USDT'][0])
            
            min_usdt_required = self.total_capital * 0.1  # 10% of capital as minimum
            
            if usdt_balance < min_usdt_required:
                self.logger.log_signal("low_balance_warning", {
                    "current_balance": usdt_balance,
                    "minimum_required": min_usdt_required
                })
                return False
            
            return True
            
        except Exception as e:
            self.logger.log_signal("balance_check_error", {"error": str(e)})
            return False

    def place_grid_order(self, grid_level):
        """
        Place an order for a specific grid level with standard fee handling.
        """
        try:
            # Check account balance before placing order
            if not self.check_account_balance():
                self.logger.log_signal("order_skipped", {
                    "reason": "insufficient_balance",
                    "level": grid_level['level']
                })
                return False
            
            trading_cfg = self.cfg.get_trading_config()
            
            order_params = {
                'symbol': trading_cfg.get('symbol', 'BTCUSDT'),
                'side': grid_level['side'],
                'type': 'LIMIT',
                'timeInForce': 'GTC',
                'quantity': grid_level['quantity'],
                'price': f"{grid_level['price']:.2f}",
                'newOrderRespType': 'FULL'
            }
            
            order_result = self.client.create_order(**order_params)
            
            # Calculate standard fees
            fees_cfg = self.cfg.get_fees_config() if hasattr(self.cfg, 'get_fees_config') else {}
            base_fee = fees_cfg.get('maker_fee_pct', 0.1) / 100
            estimated_fee = (grid_level['price'] * grid_level['quantity']) * base_fee
            
            self.logger.log_signal("order_placed", {
                "order_id": order_result['orderId'],
                "side": grid_level['side'],
                "price": grid_level['price'],
                "quantity": grid_level['quantity'],
                "level": grid_level['level'],
                "estimated_fee": estimated_fee
            })
            
            grid_level['order_id'] = order_result['orderId']
            grid_level['status'] = 'placed'
            
            return True
            
        except Exception as e:
            self.logger.log_signal("order_error", {
                "level": grid_level['level'],
                "error": str(e)
            })
            return False

    def maybe_trail_grid(self, price, df_ind):
        """
        Shift grid up/down based on trailing logic and moving averages.
        """
        if not self.trailing_enabled:
            return

        ma_val = df_ind[f"ma_{self.trailing_ma_period}"].iloc[-1]
        grid_center = self.grid_levels[len(self.grid_levels)//2] if self.grid_levels else ma_val
        threshold = grid_center * (1 + self.trailing_threshold_pct)

        should_shift = False
        if self.trailing_direction in ("up", "both") and price > threshold:
            should_shift = True
        if self.trailing_direction in ("down", "both") and price < grid_center * (1 - self.trailing_threshold_pct):
            should_shift = True

        if should_shift:
            # Re-center grid and regenerate
            print(f"[TRAILING GRID] Shifting grid to new center: {ma_val}")
            # Regenerate grid with new center, e.g.:
            # new_params = self.define_parameters_with_center(ma_val)
            # self.adjust_grid(new_params, regime, info)
            # self.generate_grid(new_adjusted_params)
            # Save state
            self.state.update_grid_state(
                grid_levels=self.grid_levels,
                bought_levels=self.bought_levels,
                sold_levels=self.sold_levels,
                regime=self.current_regime,
                regime_history=self.regime_strength_history,
                grid_generated=True
            )
            self.logger.log_signal("grid_shift", {
                "center": ma_val,
                "timestamp": datetime.now().isoformat()
            })

    # ---- CONTROLLER LOGIC ----
    # ...keep your existing methods, and fill in as needed...
    # should_regenerate_grid, force_grid_regeneration, update_regime_tracking,
    # execute_grid_trades, force_sell_check, print_grid_layers, debug_sell_status, etc.

    # ---- MAIN LOOP ----
    def polling_loop(self, poll_interval=5):
        """
        Main k-line polling with real-time monitoring display
        """
        print(f"\n🔄 STARTING REAL-TIME MONITORING (Poll every {poll_interval}s)")
        print("="*80)
        
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                start_time = datetime.now()
                
                # Real-time status header
                print(f"\n📊 CYCLE #{cycle_count} | {start_time.strftime('%H:%M:%S')} | Poll Interval: {poll_interval}s")
                print("-" * 80)
                
                # 1. Fetch latest market data
                print("🔍 Fetching current market data...")
                try:
                    ticker = self.client.get_symbol_ticker(symbol='BTCUSDT')
                    current_price = float(ticker['price'])
                    print(f"   📈 Current BTC Price: ${current_price:,.2f}")
                except Exception as e:
                    print(f"   ❌ Market data fetch failed: {e}")
                    current_price = 0
                
                # 2. Check grid status and entry opportunities
                print("🏗️  Analyzing grid positions...")
                if self.grid_levels:
                    buy_opportunities = []
                    sell_opportunities = []
                    
                    for level in self.grid_levels:
                        level_price = level['price']
                        level_side = level['side']
                        level_num = level['level']
                        
                        if level_side == 'BUY' and current_price <= level_price:
                            if level_num not in self.bought_levels:
                                buy_opportunities.append(f"Level {level_num} @ ${level_price:,.2f}")
                        
                        elif level_side == 'SELL' and current_price >= level_price:
                            if (level_num, level_price) not in self.sold_levels:
                                sell_opportunities.append(f"Level {level_num} @ ${level_price:,.2f}")
                    
                    # Check volatility conditions before trading
                    if hasattr(self, 'data') and self.data is not None:
                        pause_conditions = self.volatility_manager.should_pause_trading(self.data)
                        
                        if pause_conditions['pause_all']:
                            print(f"   🛑 TRADING PAUSED: {pause_conditions['reason']}")
                            print(f"   ⚠️  Extreme market conditions detected - protecting capital")
                        else:
                            if buy_opportunities:
                                print(f"   🟢 BUY Opportunities: {', '.join(buy_opportunities)}")
                                # EXECUTE BUY ORDERS
                                self._execute_buy_orders(current_price)
                            
                            if sell_opportunities:
                                print(f"   🔴 SELL Opportunities: {', '.join(sell_opportunities)}")
                                # EXECUTE SELL ORDERS
                                self._execute_sell_orders(current_price)
                    else:
                        if buy_opportunities:
                            print(f"   🟢 BUY Opportunities: {', '.join(buy_opportunities)}")
                            # EXECUTE BUY ORDERS
                            self._execute_buy_orders(current_price)
                        
                        if sell_opportunities:
                            print(f"   🔴 SELL Opportunities: {', '.join(sell_opportunities)}")
                            # EXECUTE SELL ORDERS
                            self._execute_sell_orders(current_price)
                    
                    if not buy_opportunities and not sell_opportunities:
                        print(f"   ⏳ No entry signals - Price ${current_price:,.2f} between grid levels")
                        # Show current grid levels status
                        self.print_compact_grid_status(current_price)
                
                else:
                    print("   ⚠️  No grid levels configured - generating grid...")
                
                # 3. Portfolio and performance status
                print("💰 Portfolio Status:")
                
                # Show account balance
                try:
                    account_info = self.client.get_account()
                    usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                                       if asset['asset'] == 'USDT'][0])
                    btc_balance = float([asset['free'] for asset in account_info['balances'] 
                                       if asset['asset'] == 'BTC'][0])
                    print(f"   💵 USDT Balance: ${usdt_balance:,.2f}")
                    print(f"   ₿  BTC Balance: {btc_balance:.6f} BTC")
                except Exception as e:
                    print(f"   ❌ Balance fetch error: {e}")
                
                performance = self.cycle_tracker.get_performance_summary()
                print(f"   📊 Strategy Capital: ${self.total_capital:,.2f}")
                print(f"   📊 Completed Cycles: {performance['total_cycles']}")
                print(f"   📈 Current P&L: ${performance['total_net_pnl']:.2f}")
                print(f"   🎯 Win Rate: {performance['win_rate']:.1f}%")
                
                # 4. Risk monitoring
                print("🛡️  Risk Status:")
                risk_status = self.risk.get_risk_status()
                print(f"   📉 Current Drawdown: ${risk_status.get('current_drawdown', 0):.2f}")
                print(f"   🚨 Consecutive Losses: {risk_status.get('consecutive_losses', 0)}")
                print(f"   ✅ Risk Level: {'HIGH' if risk_status.get('high_risk_mode') else 'NORMAL'}")
                
                # 5. Active orders status (simulation)
                print("📋 Active Orders:")
                if hasattr(self, 'grid_levels') and self.grid_levels:
                    active_buys = len([l for l in self.grid_levels if l['side'] == 'BUY' and l['level'] not in self.bought_levels])
                    active_sells = len([l for l in self.grid_levels if l['side'] == 'SELL' and (l['level'], l['price']) not in self.sold_levels])
                    print(f"   📊 Active BUY Orders: {active_buys}")
                    print(f"   📊 Active SELL Orders: {active_sells}")
                else:
                    print("   ⏳ No active orders - grid not initialized")
                
                # 6. Next action indicator
                elapsed_time = (datetime.now() - start_time).total_seconds()
                print(f"\n⏱️  Cycle completed in {elapsed_time:.2f}s")
                print(f"⏳ Next check in {poll_interval}s...")
                print("="*80)
                
                # Sleep with countdown (optional - shows bot is alive)
                for remaining in range(poll_interval, 0, -1):
                    if remaining % 10 == 0 or remaining <= 5:  # Show countdown for last 5 seconds or every 10s
                        print(f"\r💤 Sleeping... {remaining}s remaining    ", end='', flush=True)
                        time.sleep(1)
                    else:
                        time.sleep(1)
                print(f"\r🔄 Waking up for next cycle...              ")
                
            except KeyboardInterrupt:
                print(f"\n\n⏹️  Trading stopped by user")
                break
            except Exception as e:
                print(f"❌ Error in polling cycle: {e}")
                print(f"   Continuing in {poll_interval}s...")
                time.sleep(poll_interval)

    def start_trading(self, historic_days=1, simulation_mode=False):
        print("="*60)
        print("INITIALIZING TRAILING GRID STRATEGY")
        print("="*60)
        
        # Show strategy configuration
        trading_cfg = self.cfg.get_trading_config()
        grid_cfg = self.cfg.get_grid_config()
        print(f"📊 Trading Symbol: {trading_cfg.get('symbol', 'BTCUSDT')}")
        print(f"🏗️  Grid Levels: {grid_cfg.get('levels', 10)}")
        print(f"📈 Grid Range: ±{grid_cfg.get('grid_range_pct', 2.5)}%")
        print(f"💰 Capital per Grid: ${self.capital_per_grid:,.2f}")
        print(f"⏱️  Poll Interval: {trading_cfg.get('poll_interval', 5)}s")
        
        if simulation_mode:
            print("🧪 SIMULATION MODE - No real trades executed")
        else:
            print("🚨 LIVE TRADING MODE - Real money at risk!")
        
        print("\n🚀 Starting real-time monitoring...")
        
        # Start the real-time polling loop
        poll_interval = trading_cfg.get("poll_interval", 5)
        self.polling_loop(poll_interval=poll_interval)

    def _execute_buy_orders(self, current_price: float):
        """Execute buy orders when price hits grid levels."""
        trading_cfg = self.cfg.get_trading_config()
        symbol = trading_cfg.get('symbol', 'BTCUSDT')
        base_quantity = trading_cfg.get('base_order_quantity', 0.001)
        
        for level in self.grid_levels:
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
                        # Real buy order
                        print(f"💰 [LIVE BUY] Level {level['level']} @ ${level['price']:,.2f}")
                        order_result = self.client.order_market_buy(
                            symbol=symbol,
                            quantity=base_quantity
                        )
                    
                    if order_result.get('status') == 'FILLED':
                        # Update position via position manager
                        self.pm.buy(base_quantity, level['price'], timestamp=datetime.now())
                        
                        # Track bought level
                        self.bought_levels.add(level['level'])
                        self.position += base_quantity
                        
                        # Log the trade
                        self.logger.log_trade({
                            'symbol': symbol,
                            'side': 'BUY',
                            'quantity': base_quantity,
                            'price': level['price'],
                            'order_id': order_result.get('orderId'),
                            'grid_level': level['level'],
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        print(f"   ✅ BUY executed - Position: {self.position:.6f} BTC")
                        
                        # Show updated grid status after trade
                        self.print_trade_update(level, 'BUY', current_price)
                        
                except Exception as e:
                    self.logger.log_error(f"Buy order failed at level {level['level']}", {
                        'level': level['level'],
                        'price': level['price'],
                        'error': str(e)
                    })
                    print(f"   ❌ BUY failed: {e}")

    def _execute_sell_orders(self, current_price: float):
        """Execute sell orders when price hits grid levels."""
        trading_cfg = self.cfg.get_trading_config()
        symbol = trading_cfg.get('symbol', 'BTCUSDT')
        base_quantity = trading_cfg.get('base_order_quantity', 0.001)
        
        for level in self.grid_levels:
            if (level['side'] == 'SELL' and 
                current_price >= level['price'] and 
                (level['level'], level['price']) not in self.sold_levels):
                
                # Check if we have position to sell
                if self.position < base_quantity:
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
                        # Real sell order
                        print(f"💰 [LIVE SELL] Level {level['level']} @ ${level['price']:,.2f}")
                        order_result = self.client.order_market_sell(
                            symbol=symbol,
                            quantity=base_quantity
                        )
                    
                    if order_result.get('status') == 'FILLED':
                        # Update position via position manager
                        self.pm.sell(base_quantity, level['price'], timestamp=datetime.now())
                        
                        # Track sold level
                        self.sold_levels.add((level['level'], level['price']))
                        self.position -= base_quantity
                        
                        # Log the trade
                        self.logger.log_trade({
                            'symbol': symbol,
                            'side': 'SELL',
                            'quantity': base_quantity,
                            'price': level['price'],
                            'order_id': order_result.get('orderId'),
                            'grid_level': level['level'],
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        # Check if this completes a cycle
                        self.cycle_tracker.check_cycle_completion(
                            'sell', level['price'], base_quantity
                        )
                        
                        print(f"   ✅ SELL executed - Position: {self.position:.6f} BTC")
                        
                        # Show updated grid status after trade
                        self.print_trade_update(level, 'SELL', current_price)
                        
                except Exception as e:
                    self.logger.log_error(f"Sell order failed at level {level['level']}", {
                        'level': level['level'],
                        'price': level['price'],
                        'error': str(e)
                    })
                    print(f"   ❌ SELL failed: {e}")

    def get_grid_status(self):
        return {
            'total_levels': len(self.grid_levels) if self.grid_levels else 0,
            'bought_levels': len(self.bought_levels),
            'completed_trades': len(self.sold_levels),
            'current_regime': self.current_regime,
            'grid_generated': self.grid_generated,
            'position': self.position
        }
