# grid_strategy_controller.py
import pandas as pd 
import time
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.cycle_tracker import CycleTracker
from strategy.volatility_manager import VolatilityManager
from strategy.grid_generator import GridGenerator
from strategy.order_executor import OrderExecutor
from strategy.grid_display import GridDisplay
from analytics.volume_filter import VolumeFilter
from analytics.technical_indicators import TechnicalIndicators
from analytics.fee_calculator import FeeCalculator

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
        self.client = client

        # Load grid/trailing parameters from config
        grid_cfg = self.cfg.get_grid_config()
        # Read directly from YAML - defaults match strategy_config.yaml exactly
        self.trailing_enabled = grid_cfg.get("trailing_enabled", True)
        self.trailing_direction = grid_cfg.get("trailing_direction", "both")
        self.trailing_threshold_pct = grid_cfg.get("trailing_threshold_pct", 0.75) / 100
        self.trailing_ma_period = grid_cfg.get("trailing_ma_period", 20)

        # Restore or initialize state
        st = self.state.get_strategy_status()
        self.grid_levels = st.get("grid_levels", [])
        self.current_regime = st.get("current_regime", None)
        self.regime_strength_history = st.get("regime_strength_history", [])
        self.grid_generated = st.get("grid_generated", False)
        self.force_regenerate = False
        self.total_capital = 0.0
        self.capital_per_grid = 0.0
        
        # Additional grid settings from YAML
        self.total_capital_usage_pct = grid_cfg.get("total_capital_usage_pct", 100.0) / 100
        self.rebalance_threshold_pct = grid_cfg.get("rebalance_threshold_pct", 2.0) / 100
        self.auto_rebalance = grid_cfg.get("auto_rebalance", True)
        
        # Initialize components
        self.cycle_tracker = CycleTracker(self.logger, self.cfg)
        self.volatility_manager = VolatilityManager(self.cfg, self.logger)
        self.grid_generator = GridGenerator(self.cfg, self.logger)
        self.fee_calculator = FeeCalculator(self.cfg, self.logger)
        self.order_executor = OrderExecutor(self.cfg, self.logger, self.pm, self.client, self.risk)
        # Pass fee calculator to order executor after initialization
        self.order_executor.fee_calculator = self.fee_calculator
        self.grid_display = GridDisplay(self.cfg)
        self.volume_filter = VolumeFilter(self.cfg, self.logger, self.client)
        self.technical_indicators = TechnicalIndicators(self.cfg, self.logger)
        
        # Set total capital in risk manager when initialized
        if hasattr(self, 'total_capital') and self.total_capital > 0:
            self.risk.set_total_capital(self.total_capital)
        
        # Restore grid level tracking state
        self.order_executor.bought_levels = set(st.get("bought_levels", []))
        self.order_executor.sold_levels = set(tuple(pair) for pair in st.get("sold_levels", []))
    
    def compute_indicators(self, df):
        """Add moving averages or other indicators to your DataFrame."""
        df[f'ma_{self.trailing_ma_period}'] = df['close'].rolling(self.trailing_ma_period).mean()
        return df

    def define_parameters(self, df_ind):
        """Define base grid parameters based on current market price with volatility adjustments."""
        params = self.grid_generator.define_parameters(df_ind, self.volatility_manager)
        self.adjusted_capital_per_grid = params.get('adjusted_capital_per_grid', 10.0)
        return params
    
    def generate_grid_levels(self, current_price):
        """Simple method to generate grid levels for dashboard display."""
        grid_cfg = self.cfg.get_grid_config()
        grid_spacing_pct = grid_cfg.get('grid_spacing_pct', 0.5) / 100
        
        # Apply volatility adjustments if available
        if hasattr(self, 'adjusted_capital_per_grid'):
            spacing_pct = grid_spacing_pct * 0.7
        else:
            spacing_pct = grid_spacing_pct
        
        grid_levels = self.grid_generator.generate_grid_levels(current_price, spacing_pct)
        
        # Add quantity to each level - use config base_order_quantity
        trading_cfg = self.cfg.get_trading_config()
        base_quantity = trading_cfg.get('base_order_quantity', 0.001)
        for level in grid_levels:
            level['quantity'] = base_quantity
        
        return grid_levels

    def generate_grid(self, adjusted_params):
        """Generate new grid levels with optimal spacing."""
        center_price = adjusted_params['center_price']
        grid_spacing_pct = adjusted_params['grid_spacing_pct']
        
        grid_levels = self.grid_generator.generate_grid_levels(center_price, grid_spacing_pct)
        
        # Add quantity to each level - use config base_order_quantity
        trading_cfg = self.cfg.get_trading_config()
        base_quantity = trading_cfg.get('base_order_quantity', 0.001)
        for level in grid_levels:
            level['quantity'] = base_quantity
        
        # Sort by price (lowest to highest)
        grid_levels.sort(key=lambda x: x['price'])
        self.grid_levels = grid_levels
        
        # Print current grid levels to console
        self.grid_display.print_grid_levels(grid_levels, center_price)
        
        return grid_levels

    def print_grid_levels(self, current_price):
        """Print current grid levels in a clean table format."""
        self.grid_display.print_grid_levels(self.grid_levels, current_price)

    def print_trade_update(self, executed_level, side, current_price):
        """Print a compact update showing which level was executed and remaining levels."""
        current_position = self.pm.get_position_summary().get('current_position')
        self.grid_display.print_trade_update(
            executed_level, side, current_price, self.grid_levels,
            self.order_executor.bought_levels, self.order_executor.sold_levels, current_position
        )

    def print_compact_grid_status(self, current_price):
        """Print a compact grid status showing only the nearest levels."""
        self.grid_display.print_compact_grid_status(self.grid_levels, current_price)

    def calculate_order_quantity(self, price):
        """Calculate order quantity based on volatility-adjusted capital allocation per grid."""
        # Use volatility-adjusted capital allocation if available
        if hasattr(self, 'adjusted_capital_per_grid'):
            capital_per_grid_pct = self.adjusted_capital_per_grid / 100
        else:
            grid_cfg = self.cfg.get_grid_config()
            capital_per_grid_pct = grid_cfg.get('capital_per_grid_pct', 10.0) / 100
        
        if self.total_capital == 0:
            try:
                account_info = self.client.get_account()
                usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                                    if asset['asset'] == 'USDT'][0])
                # Apply total capital usage percentage from YAML
                self.total_capital = usdt_balance * self.total_capital_usage_pct
            except Exception as e:
                self.logger.log_error(f"Failed to get account balance - stopping bot", {"error": str(e)})
                raise Exception(f"Cannot access account balance: {e}. Bot stopped for safety.")
        
        self.capital_per_grid = self.total_capital * capital_per_grid_pct
        quantity = self.capital_per_grid / price
        return round(quantity, 6)

    def initialize_capital(self, initial_capital=None):
        """Initialize total capital for grid allocation."""
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
        
        # Update risk manager with actual capital
        self.risk.set_total_capital(self.total_capital)

    def check_account_balance(self):
        """Check account balance for trading."""
        try:
            account_info = self.client.get_account()
            usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                               if asset['asset'] == 'USDT'][0])
            
            min_usdt_required = self.total_capital * 0.1
            
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

    def maybe_trail_grid(self, price, df_ind):
        """Shift grid up/down based on trailing logic and moving averages."""
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
            print(f"[TRAILING GRID] Shifting grid to new center: {ma_val}")
            execution_status = self.order_executor.get_execution_status()
            self.state.update_grid_state(
                grid_levels=self.grid_levels,
                bought_levels=list(execution_status['bought_levels']),
                sold_levels=[list(pair) for pair in execution_status['sold_levels']],
                regime=self.current_regime,
                regime_history=self.regime_strength_history,
                grid_generated=True
            )
            self.logger.log_signal("grid_shift", {
                "center": ma_val,
                "timestamp": datetime.now().isoformat()
            })

    def should_rebalance_grid(self, current_price):
        """Check if grid should be rebalanced based on config settings."""
        if not self.auto_rebalance or not self.grid_levels:
            return False
        
        # Find current grid center
        sorted_levels = sorted(self.grid_levels, key=lambda x: x['price'])
        grid_center = sorted_levels[len(sorted_levels)//2]['price']
        
        # Calculate deviation from center
        price_deviation_pct = abs(current_price - grid_center) / grid_center
        
        if price_deviation_pct > self.rebalance_threshold_pct:
            self.logger.log_signal("rebalance_needed", {
                "current_price": current_price,
                "grid_center": grid_center,
                "deviation_pct": price_deviation_pct * 100,
                "threshold_pct": self.rebalance_threshold_pct * 100
            })
            return True
        
        return False

    def _check_stop_losses(self, current_price):
        """Check individual position stop losses from YAML config."""
        risk_cfg = self.cfg.get_risk_config()
        stop_loss_pct = risk_cfg.get('stop_loss_pct', 10.0) / 100
        
        current_position = self.pm.get_position_summary().get('current_position')
        if not current_position:
            return  # No position to protect
        
        quantity = current_position.get('quantity', 0)
        buy_price = current_position.get('buy_price', 0)
        
        if quantity <= 0 or buy_price <= 0:
            return
        
        # Calculate current loss percentage
        loss_pct = (buy_price - current_price) / buy_price
        
        if loss_pct >= stop_loss_pct:
            print(f"\n🚨 STOP LOSS TRIGGERED! 🚨")
            print(f"   Loss: {loss_pct*100:.2f}% (Limit: {stop_loss_pct*100:.2f}%)")
            print(f"   Position: {quantity:.6f} BTC @ ${buy_price:.2f}")
            print(f"   Current: ${current_price:.2f}")
            print(f"   Executing emergency sell...")
            
            try:
                # Execute emergency market sell
                trading_cfg = self.cfg.get_trading_config()
                symbol = trading_cfg.get('symbol', 'BTCUSDT')
                
                api_cfg = self.cfg.get_api_config()
                is_testnet = api_cfg.get('testnet', True)
                
                if is_testnet:
                    print(f"🧪 [TESTNET STOP LOSS] Selling {quantity:.6f} BTC @ ${current_price:.2f}")
                else:
                    order_result = self.client.order_market_sell(
                        symbol=symbol,
                        quantity=quantity
                    )
                    print(f"💰 [LIVE STOP LOSS] Order ID: {order_result.get('orderId')}")
                
                # Record the loss with risk manager
                pnl = (current_price - buy_price) * quantity
                if self.risk:
                    self.risk.record_trade_result(pnl, f"STOP_LOSS_{int(current_price)}")
                
                # Update position manager
                self.pm.sell(quantity, current_price, timestamp=datetime.now())
                
                # Log the stop loss event
                self.logger.log_signal("stop_loss_executed", {
                    "buy_price": buy_price,
                    "sell_price": current_price,
                    "quantity": quantity,
                    "loss_pct": loss_pct * 100,
                    "pnl": pnl
                })
                
                # Save stop loss trade to persistence
                stop_loss_trade = {
                    'symbol': symbol,
                    'side': 'SELL',
                    'quantity': quantity,
                    'price': current_price,
                    'order_id': f"STOP_LOSS_{int(current_price)}",
                    'grid_level': 0,  # Stop loss doesn't have a grid level
                    'timestamp': datetime.now().isoformat(),
                    'trade_type': 'STOP_LOSS',
                    'pnl': pnl,
                    'notes': f"Stop loss triggered at {loss_pct*100:.2f}% loss"
                }
                
                if hasattr(self.order_executor, 'trade_persistence'):
                    self.order_executor.trade_persistence.save_trade(stop_loss_trade)
                
                print(f"   ✅ Stop loss executed - Loss: ${pnl:.2f}")
                
            except Exception as e:
                print(f"   ❌ Stop loss execution failed: {e}")
                self.logger.log_error("Stop loss execution failed", {"error": str(e)})

    def _is_high_risk_situation(self):
        """Check if current situation qualifies as high risk based on YAML config."""
        risk_cfg = self.cfg.get_risk_config()
        risk_status = self.risk.get_risk_status()
        
        # Define high risk thresholds (more conservative than emergency stops)
        high_risk_drawdown_pct = 80  # 80% of max drawdown limit
        high_risk_daily_loss_pct = 70  # 70% of daily loss limit
        high_risk_consecutive_losses = max(1, self.risk.max_consecutive_losses - 2)  # 2 less than max
        
        # Check drawdown risk
        drawdown_risk_pct = risk_status.get('risk_pct_used', {}).get('drawdown', 0)
        if drawdown_risk_pct >= high_risk_drawdown_pct:
            return True
        
        # Check daily loss risk
        daily_loss_risk_pct = risk_status.get('risk_pct_used', {}).get('daily_loss', 0)
        if daily_loss_risk_pct >= high_risk_daily_loss_pct:
            return True
        
        # Check consecutive losses
        consecutive_losses = risk_status.get('consecutive_losses', 0)
        if consecutive_losses >= high_risk_consecutive_losses:
            return True
        
        # Check if we have a position with significant unrealized loss
        current_position = self.pm.get_position_summary().get('current_position')
        if current_position:
            quantity = current_position.get('quantity', 0)
            buy_price = current_position.get('buy_price', 0)
            
            if quantity > 0 and buy_price > 0:
                # Get current price for unrealized loss calculation
                try:
                    ticker = self.client.get_symbol_ticker(symbol='BTCUSDT')
                    current_price = float(ticker['price'])
                    unrealized_loss_pct = (buy_price - current_price) / buy_price
                    
                    # If unrealized loss is approaching stop loss, it's high risk
                    stop_loss_threshold = risk_cfg.get('stop_loss_pct', 10.0) / 100
                    if unrealized_loss_pct >= (stop_loss_threshold * 0.7):  # 70% of stop loss
                        return True
                        
                except Exception:
                    pass  # If we can't get price, don't consider it high risk
        
        return False

    def polling_loop(self, poll_interval=5):
        """Main k-line polling with real-time monitoring display"""
        print(f"\n🔄 STARTING REAL-TIME MONITORING (Poll every {poll_interval}s)")
        print("="*80)
        
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                start_time = datetime.now()
                
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
                
                # 2. Check for stop losses first (CRITICAL SAFETY)
                self._check_stop_losses(current_price)
                
                # 2.5. Check volume filter from YAML config
                trading_cfg = self.cfg.get_trading_config()
                symbol = trading_cfg.get('symbol', 'BTCUSDT')
                volume_allowed, volume_reason, volume_data = self.volume_filter.should_allow_trading(symbol)
                
                if not volume_allowed:
                    print(f"   📊 VOLUME FILTER: {volume_reason}")
                    print(f"   ⚠️  Trading blocked due to insufficient volume")
                    
                # 3. Check grid status and entry opportunities
                print("🏗️  Analyzing grid positions...")
                if self.grid_levels:
                    buy_opportunities, sell_opportunities = self.order_executor.get_trading_opportunities(self.grid_levels, current_price)
                    
                    # Check volatility conditions before trading
                    if hasattr(self, 'data') and self.data is not None:
                        pause_conditions = self.volatility_manager.should_pause_trading(self.data)
                        
                        if pause_conditions['pause_all']:
                            print(f"   🛑 TRADING PAUSED: {pause_conditions['reason']}")
                            print(f"   ⚠️  Extreme market conditions detected - protecting capital")
                        else:
                            # ⚠️ CRITICAL: Check risk manager before any trades
                            trade_allowed, risk_reason = self.risk.check_trade_allowed()
                            
                            # Check pause_on_high_risk setting
                            risk_cfg = self.cfg.get_risk_config()
                            pause_on_high_risk = risk_cfg.get('pause_on_high_risk', True)
                            
                            if not trade_allowed:
                                print(f"   🛑 TRADING BLOCKED: {risk_reason}")
                                print(f"   📊 Risk Manager is protecting your capital")
                                
                                # Check if we should pause due to high risk
                                if pause_on_high_risk and self._is_high_risk_situation():
                                    print(f"   ⚠️  HIGH RISK MODE: Trading paused per YAML config")
                                    print(f"   🛡️  pause_on_high_risk: true - Waiting for safer conditions")
                            elif not volume_allowed:
                                print(f"   📊 VOLUME CHECK FAILED: {volume_reason}")
                                print(f"   ⚠️  Trading blocked - volume_filter: true in YAML config")
                            else:
                                # Add current price to technical indicators history
                                self.technical_indicators.add_price_data(current_price)
                                
                                if buy_opportunities:
                                    print(f"   🟢 BUY Opportunities: {', '.join(buy_opportunities)}")
                                    try:
                                        # Check technical indicators for BUY signals
                                        buy_allowed, buy_reason = self.technical_indicators.should_allow_trading_by_indicators(current_price, 'BUY')
                                        if buy_allowed:
                                            executed_buys = self.order_executor.execute_buy_orders(self.grid_levels, current_price)
                                            for executed in executed_buys:
                                                self.print_trade_update(executed['level'], 'BUY', current_price)
                                        else:
                                            print(f"   📈 TECHNICAL INDICATORS: {buy_reason}")
                                    except Exception as e:
                                        self.logger.log_error(f"Buy execution failed: {e}", {
                                            "current_price": current_price,
                                            "opportunities": len(buy_opportunities)
                                        })
                                        print(f"   ❌ BUY execution error: {e}")
                                
                                if sell_opportunities:
                                    print(f"   🔴 SELL Opportunities: {', '.join(sell_opportunities)}")
                                    try:
                                        # Check technical indicators for SELL signals
                                        sell_allowed, sell_reason = self.technical_indicators.should_allow_trading_by_indicators(current_price, 'SELL')
                                        if sell_allowed:
                                            executed_sells = self.order_executor.execute_sell_orders(self.grid_levels, current_price, self.cycle_tracker)
                                            for executed in executed_sells:
                                                self.print_trade_update(executed['level'], 'SELL', current_price)
                                        else:
                                            print(f"   📈 TECHNICAL INDICATORS: {sell_reason}")
                                    except Exception as e:
                                        self.logger.log_error(f"Sell execution failed: {e}", {
                                            "current_price": current_price,
                                            "opportunities": len(sell_opportunities)
                                        })
                                        print(f"   ❌ SELL execution error: {e}")
                    else:
                        # ⚠️ CRITICAL: Check risk manager before any trades (non-volatility path)
                        trade_allowed, risk_reason = self.risk.check_trade_allowed()
                        
                        if not trade_allowed:
                            print(f"   🛑 TRADING BLOCKED: {risk_reason}")
                            print(f"   📊 Risk Manager is protecting your capital")
                        elif not volume_allowed:
                            print(f"   📊 VOLUME CHECK FAILED: {volume_reason}")
                            print(f"   ⚠️  Trading blocked - volume_filter: true in YAML config")
                        else:
                            # Add current price to technical indicators history
                            self.technical_indicators.add_price_data(current_price)
                            
                            if buy_opportunities:
                                print(f"   🟢 BUY Opportunities: {', '.join(buy_opportunities)}")
                                try:
                                    # Check technical indicators for BUY signals
                                    buy_allowed, buy_reason = self.technical_indicators.should_allow_trading_by_indicators(current_price, 'BUY')
                                    if buy_allowed:
                                        executed_buys = self.order_executor.execute_buy_orders(self.grid_levels, current_price)
                                        for executed in executed_buys:
                                            self.print_trade_update(executed['level'], 'BUY', current_price)
                                    else:
                                        print(f"   📈 TECHNICAL INDICATORS: {buy_reason}")
                                except Exception as e:
                                    self.logger.log_error(f"Buy execution failed: {e}", {
                                        "current_price": current_price,
                                        "opportunities": len(buy_opportunities)
                                    })
                                    print(f"   ❌ BUY execution error: {e}")
                            
                            if sell_opportunities:
                                print(f"   🔴 SELL Opportunities: {', '.join(sell_opportunities)}")
                                try:
                                    # Check technical indicators for SELL signals
                                    sell_allowed, sell_reason = self.technical_indicators.should_allow_trading_by_indicators(current_price, 'SELL')
                                    if sell_allowed:
                                        executed_sells = self.order_executor.execute_sell_orders(self.grid_levels, current_price, self.cycle_tracker)
                                        for executed in executed_sells:
                                            self.print_trade_update(executed['level'], 'SELL', current_price)
                                    else:
                                        print(f"   📈 TECHNICAL INDICATORS: {sell_reason}")
                                except Exception as e:
                                    self.logger.log_error(f"Sell execution failed: {e}", {
                                        "current_price": current_price,
                                        "opportunities": len(sell_opportunities)
                                    })
                                    print(f"   ❌ SELL execution error: {e}")
                    
                    if not buy_opportunities and not sell_opportunities:
                        print(f"   ⏳ No entry signals - Price ${current_price:,.2f} between grid levels")
                        self.print_compact_grid_status(current_price)
                
                else:
                    print("   ⚠️  No grid levels configured - generating grid...")
                
                # 3. Portfolio and performance status
                self.grid_display.print_portfolio_status(self.client, self.total_capital, self.cycle_tracker)
                
                # 4. Risk monitoring
                self.grid_display.print_risk_status(self.risk)
                
                # 5. Active orders status
                self.grid_display.print_active_orders_status(
                    self.grid_levels, 
                    self.order_executor.bought_levels, 
                    self.order_executor.sold_levels
                )
                
                # 6. Trade statistics and recent trades
                self.grid_display.print_trade_statistics(
                    self.order_executor.trade_persistence
                )
                self.grid_display.print_recent_trades(
                    self.order_executor.trade_persistence, limit=2
                )
                
                # 7. Volume filter status
                self.grid_display.print_volume_status(
                    self.volume_filter, symbol
                )
                
                # 8. Technical indicators status
                self.grid_display.print_technical_indicators_status(
                    self.technical_indicators, current_price
                )
                
                # 9. Fee analysis
                self.grid_display.print_fee_analysis(self.fee_calculator)
                
                # 10. Next action indicator
                elapsed_time = (datetime.now() - start_time).total_seconds()
                print(f"\n⏱️  Cycle completed in {elapsed_time:.2f}s")
                print(f"⏳ Next check in {poll_interval}s...")
                print("="*80)
                
                # Sleep with countdown
                for remaining in range(poll_interval, 0, -1):
                    if remaining % 10 == 0 or remaining <= 5:
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
        
        poll_interval = trading_cfg.get("poll_interval", 5)
        self.polling_loop(poll_interval=poll_interval)

    def get_grid_status(self):
        execution_status = self.order_executor.get_execution_status()
        current_position = self.pm.get_position_summary().get('current_position')
        position_qty = current_position.get('quantity', 0) if current_position else 0
        
        return {
            'total_levels': len(self.grid_levels) if self.grid_levels else 0,
            'bought_levels': execution_status['total_bought'],
            'completed_trades': execution_status['total_sold'],
            'current_regime': self.current_regime,
            'grid_generated': self.grid_generated,
            'position': position_qty
        }