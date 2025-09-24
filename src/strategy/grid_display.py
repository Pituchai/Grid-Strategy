"""
Grid display and monitoring utilities.
Extracted from GridStrategyController for better organization.
"""


class GridDisplay:
    """Handles grid display and monitoring output."""
    
    def __init__(self, config_manager):
        self.cfg = config_manager
    
    def print_grid_levels(self, grid_levels, current_price):
        """
        Print current grid levels in a clean table format.
        """
        if not grid_levels:
            print("🏗️  No grid levels available")
            return
        
        print(f"\n🎯 CURRENT GRID LEVELS (BTC: ${current_price:,.2f})")
        print("=" * 70)
        print(f"{'Level':<6} | {'Side':<4} | {'Price':<12} | {'Status'}")
        print("-" * 70)
        
        for level in sorted(grid_levels, key=lambda x: x['level']):
            price = level['price']
            
            # Determine status based on current price
            if level['side'] == 'BUY':
                status = "🟢 READY" if current_price <= price else "⏳ WAIT"
            else:
                status = "🔴 READY" if current_price >= price else "⏳ WAIT"
            
            print(f"{level['level']:>5} | {level['side']:<4} | ${price:>10,.2f} | {status}")
        
        # Summary
        buy_levels = [l for l in grid_levels if l['side'] == 'BUY']
        sell_levels = [l for l in grid_levels if l['side'] == 'SELL']
        ready_buys = len([l for l in buy_levels if current_price <= l['price']])
        ready_sells = len([l for l in sell_levels if current_price >= l['price']])
        
        print("-" * 70)
        print(f"📊 Total: {len(grid_levels)} levels | Buy: {len(buy_levels)} | Sell: {len(sell_levels)}")
        print(f"🟢 Ready: {ready_buys + ready_sells} levels | Buy: {ready_buys} | Sell: {ready_sells}")
        print("=" * 70)

    def print_trade_update(self, executed_level, side, current_price, grid_levels, bought_levels, sold_levels, current_position):
        """
        Print a compact update showing which level was executed and remaining levels.
        """
        print(f"\n📈 TRADE UPDATE - {side} Level {executed_level['level']} EXECUTED")
        print("-" * 50)
        
        # Show remaining ready levels
        buy_ready = []
        sell_ready = []
        
        for level in grid_levels:
            if level['side'] == 'BUY' and current_price <= level['price'] and level['level'] not in bought_levels:
                buy_ready.append(level)
            elif level['side'] == 'SELL' and current_price >= level['price'] and (level['level'], level['price']) not in sold_levels:
                sell_ready.append(level)
        
        print(f"🟢 Ready BUY levels: {len(buy_ready)}")
        for level in sorted(buy_ready, key=lambda x: x['level'])[:3]:  # Show top 3
            print(f"   L{level['level']}: ${level['price']:,.2f}")
        
        print(f"🔴 Ready SELL levels: {len(sell_ready)}")
        for level in sorted(sell_ready, key=lambda x: x['level'])[:3]:  # Show top 3
            print(f"   L{level['level']}: ${level['price']:,.2f}")
        
        position_qty = current_position.get('quantity', 0) if current_position else 0
        print(f"💰 Current Position: {position_qty:.6f} BTC")
        print("-" * 50)

    def print_compact_grid_status(self, grid_levels, current_price):
        """
        Print a compact grid status showing only the nearest levels.
        """
        if not grid_levels:
            return
        
        print("   📋 Current Grid Levels:")
        
        # Find levels close to current price (within 2% up and down)
        close_levels = []
        for level in grid_levels:
            distance_pct = abs(level['price'] - current_price) / current_price * 100
            if distance_pct <= 2.0:  # Show levels within 2%
                close_levels.append(level)
        
        # If no close levels, show 4 nearest on each side
        if not close_levels:
            sorted_levels = sorted(grid_levels, key=lambda x: abs(x['price'] - current_price))
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
    
    def print_portfolio_status(self, client, total_capital, cycle_tracker):
        """Print portfolio and performance status."""
        print("💰 Portfolio Status:")
        
        # Show account balance
        try:
            account_info = client.get_account()
            usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                               if asset['asset'] == 'USDT'][0])
            btc_balance = float([asset['free'] for asset in account_info['balances'] 
                               if asset['asset'] == 'BTC'][0])
            print(f"   💵 USDT Balance: ${usdt_balance:,.2f}")
            print(f"   ₿  BTC Balance: {btc_balance:.6f} BTC")
        except Exception as e:
            print(f"   ❌ Balance fetch error: {e}")
        
        performance = cycle_tracker.get_performance_summary()
        print(f"   📊 Strategy Capital: ${total_capital:,.2f}")
        print(f"   📊 Completed Cycles: {performance['total_cycles']}")
        print(f"   📈 Current P&L: ${performance['total_net_pnl']:.2f}")
        print(f"   🎯 Win Rate: {performance['win_rate']:.1f}%")
    
    def print_risk_status(self, risk_manager):
        """Print risk monitoring status."""
        print("🛡️  Risk Status:")
        risk_status = risk_manager.get_risk_status()
        print(f"   📉 Current Drawdown: ${risk_status.get('current_drawdown', 0):.2f}")
        print(f"   🚨 Consecutive Losses: {risk_status.get('consecutive_losses', 0)}")
        print(f"   ✅ Risk Level: {'HIGH' if risk_status.get('high_risk_mode') else 'NORMAL'}")
    
    def print_active_orders_status(self, grid_levels, bought_levels, sold_levels):
        """Print active orders status."""
        print("📋 Active Orders:")
        if grid_levels:
            active_buys = len([l for l in grid_levels if l['side'] == 'BUY' and l['level'] not in bought_levels])
            active_sells = len([l for l in grid_levels if l['side'] == 'SELL' and (l['level'], l['price']) not in sold_levels])
            print(f"   📊 Active BUY Orders: {active_buys}")
            print(f"   📊 Active SELL Orders: {active_sells}")
        else:
            print("   ⏳ No active orders - grid not initialized")
    
    def print_trade_statistics(self, trade_persistence):
        """Print trade statistics from persistence system."""
        if not trade_persistence:
            return
            
        stats = trade_persistence.get_performance_summary()
        
        print("📈 Trade Statistics:")
        print(f"   📊 Total Trades: {stats['total_trades']}")
        print(f"   💰 Total P&L: ${stats['total_pnl']:.2f}")
        print(f"   🎯 Win Rate: {stats['win_rate']:.1f}%")
        print(f"   ✅ Winning: {stats['winning_trades']} | ❌ Losing: {stats['losing_trades']}")
        
        if stats['total_trades'] > 0:
            print(f"   📈 Avg P&L/Trade: ${stats['avg_pnl_per_trade']:.2f}")
        
        if stats.get('csv_file_path'):
            print(f"   📄 CSV Export: {stats['csv_file_path'].split('/')[-1]}")
    
    def print_logging_configuration(self, event_logger):
        """Print logging configuration status from YAML config."""
        if not event_logger:
            return
            
        config = event_logger.get_logging_configuration_summary()
        
        print("📝 Logging Configuration:")
        print(f"   📁 Directory: {config['log_directory']}")
        print(f"   📊 Log Level: {config['main_log_level']} (Console: {config['console_log_level']})")
        print(f"   💾 Max Size: {config['max_log_size_mb']}MB | Backups: {config['backup_count']}")
        
        # Export settings
        csv_icon = "✅" if config['export_trades_csv'] else "❌"
        charts_icon = "✅" if config['create_performance_charts'] else "❌"
        monitoring_icon = "✅" if config['real_time_monitoring'] else "❌"
        
        print(f"   {csv_icon} CSV Export | {charts_icon} Performance Charts | {monitoring_icon} Real-time Monitor")
        
        # Alert settings
        if config['enable_email_alerts']:
            print(f"   📧 Email Alerts: ENABLED")
        else:
            print(f"   📧 Email Alerts: DISABLED")
    
    def print_technical_indicators_status(self, technical_indicators, current_price=None):
        """Print technical indicators status from YAML config."""
        if not technical_indicators:
            return
            
        status = technical_indicators.get_indicator_status_summary()
        
        if not status['enabled']:
            print(f"📈 Technical Indicators: ⚪ DISABLED ({status['message']})")
            return
        
        print("📈 Technical Indicators:")
        print(f"   📊 Data Points: {status['price_history_length']} prices collected")
        print(f"   ⚙️  Config: RSI({status['config']['rsi_oversold']}/{status['config']['rsi_overbought']}) | MACD({status['config']['macd_periods']})")
        
        if current_price and status.get('signals'):
            signals = status['signals']
            overall_icon = "🟢" if signals['overall_signal'] == 'BUY' else "🔴" if signals['overall_signal'] == 'SELL' else "⚪"
            print(f"   {overall_icon} Overall Signal: {signals['overall_signal']}")
            
            # Individual indicators
            indicators_line = []
            for indicator, signal in [('RSI', signals['rsi_signal']), ('MACD', signals['macd_signal']), 
                                    ('BB', signals['bb_signal']), ('MA', signals['ma_signal'])]:
                icon = "🟢" if signal == 'BUY' else "🔴" if signal == 'SELL' else "⚪"
                indicators_line.append(f"{icon}{indicator}")
            
            print(f"   📊 Signals: {' | '.join(indicators_line)}")
            
            # Show key values if available
            details = signals.get('details', {})
            if 'rsi' in details:
                rsi_val = details['rsi']['value']
                print(f"   📈 RSI: {rsi_val:.1f} (OS:{status['config']['rsi_oversold']}/OB:{status['config']['rsi_overbought']})")
        else:
            print(f"   ⏳ Insufficient data for signal generation")
    
    def print_fee_analysis(self, fee_calculator):
        """Print fee analysis and optimization from YAML config."""
        if not fee_calculator:
            return
            
        analysis = fee_calculator.get_fee_analysis_summary()
        
        print("💰 Fee Analysis:")
        config = analysis['configuration']
        print(f"   📊 Maker Fee: {config['maker_fee_pct']:.3f}% | Taker Fee: {config['taker_fee_pct']:.3f}%")
        
        # Fee discount status
        if config['use_fee_discount']:
            effective_rate = analysis['optimization']['effective_maker_rate']
            print(f"   💸 Fee Discount: ACTIVE ({config['fee_discount_pct']:.1f}% off) | Effective: {effective_rate:.3f}%")
        else:
            print(f"   💸 Fee Discount: DISABLED")
        
        # Fee tracking
        tracking = analysis['fee_tracking']
        if tracking['fee_payments_count'] > 0:
            print(f"   💳 Total Fees Paid: ${tracking['total_fees_paid']:.2f} ({tracking['fee_payments_count']} trades)")
            print(f"   💲 Avg Fee/Trade: ${tracking['avg_fee_per_trade']:.3f}")
            
            if tracking['total_fee_savings'] > 0:
                print(f"   💰 Total Savings: ${tracking['total_fee_savings']:.2f}")
        else:
            print(f"   💳 No fee payments recorded yet")
        
        # Optimization info
        opt = analysis['optimization']
        if opt['maker_vs_taker_difference'] > 0:
            print(f"   📈 Maker Advantage: {opt['maker_vs_taker_difference']:.3f}% lower than taker fees")
        
        # Fee calculation setting
        if config['include_fees_in_calculation']:
            print(f"   ✅ Fees included in P&L calculations")
        else:
            print(f"   ⚪ Fees NOT included in P&L calculations")
    
    def print_recent_trades(self, trade_persistence, limit=3):
        """Print recent trades from persistence system."""
        if not trade_persistence:
            return
            
        recent_trades = trade_persistence.get_trade_history(limit=limit)
        if not recent_trades:
            return
            
        print(f"📋 Recent Trades (Last {min(len(recent_trades), limit)}):")
        for trade in recent_trades[-limit:]:
            pnl_str = f"${trade['pnl']:.2f}" if trade['pnl'] != 0 else "--"
            trade_type_icon = "🛑" if trade['trade_type'] == 'STOP_LOSS' else "🔄"
            print(f"   {trade_type_icon} {trade['side']} L{trade['grid_level']} @ ${trade['price']:.2f} | P&L: {pnl_str}")
    
    def print_volume_status(self, volume_filter, symbol='BTCUSDT'):
        """Print volume filter status from YAML config."""
        if not volume_filter:
            return
            
        volume_status = volume_filter.get_volume_status(symbol)
        
        print("📊 Volume Status:")
        if volume_status['enabled']:
            status_icon = "✅" if volume_status['status'] == 'PASS' else "🚫"
            print(f"   {status_icon} Filter: {volume_status['status']} | {volume_status['message']}")
            
            current_vol = volume_status.get('current_volume', 0)
            min_vol = volume_status.get('minimum_required', 0)
            ratio = volume_status.get('volume_ratio', 0)
            
            print(f"   📈 24h Volume: ${current_vol:,.0f} (Min: ${min_vol:,.0f})")
            print(f"   📊 Ratio: {ratio:.1f}x minimum | Quote Vol: ${volume_status.get('quote_volume', 0):,.0f}")
            
            price_change = volume_status.get('price_change_24h', 0)
            change_icon = "📈" if price_change >= 0 else "📉"
            print(f"   {change_icon} 24h Change: {price_change:+.2f}%")
        else:
            print(f"   ⚪ {volume_status['message']}")
    
    def print_performance_targets(self, cycle_tracker):
        """Print performance targets progress from YAML config."""
        if not cycle_tracker:
            return
            
        perf_data = cycle_tracker.get_performance_vs_targets()
        
        if perf_data.get('performance_logging') == 'disabled':
            print("📈 Performance Tracking: ⚪ DISABLED (log_performance: false in YAML)")
            return
        
        print("📈 Performance vs Targets:")
        
        # Daily cycle progress
        daily = perf_data['daily_targets']
        cycles_completed = daily['completed_cycles']
        cycles_target = daily['target_cycles']
        cycles_progress = daily['cycles_progress_pct']
        cycles_remaining = daily['cycles_remaining']
        
        progress_icon = "🎯" if cycles_progress >= 100 else "📊"
        print(f"   {progress_icon} Daily Cycles: {cycles_completed}/{cycles_target} ({cycles_progress:.0f}%) | {cycles_remaining} remaining")
        
        # Cycle quality
        quality = perf_data['cycle_quality']
        target_success_rate = quality['target_success_rate_pct']
        target_profit = quality['target_profit_per_cycle_pct']
        cycles_meeting_target = quality['cycles_meeting_target']
        
        quality_icon = "✅" if target_success_rate >= 70 else "⚠️" if target_success_rate >= 50 else "❌"
        print(f"   {quality_icon} Cycle Quality: {cycles_meeting_target} meeting {target_profit:.2f}% target ({target_success_rate:.0f}% success)")
        
        # Profit tracking
        profit = perf_data['profit_tracking']
        daily_profit = profit['current_daily_profit']
        avg_profit = profit['avg_profit_per_cycle']
        
        profit_icon = "💰" if daily_profit > 0 else "📉" if daily_profit < 0 else "➡️"
        print(f"   {profit_icon} Today's P&L: ${daily_profit:.2f} | Avg/Cycle: ${avg_profit:.2f}")