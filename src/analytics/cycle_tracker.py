import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class CycleTracker:
    """
    Tracks grid trading cycles and profitability metrics.
    Monitors the 0.35% target profit per cycle and daily performance.
    """
    
    def __init__(self, event_logger, config_manager):
        self.logger = event_logger
        self.cfg = config_manager
        self.cycles = []
        self.current_cycle = None
        self.daily_stats = {}
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.total_fees_paid = 0.0
        self.fees_saved_bnb = 0.0
        self.losing_cycles = 0
        self.winning_cycles = 0
        self.max_drawdown = 0.0
        self.current_drawdown = 0.0
        
        # Load performance targets from config
        perf_cfg = self.cfg.get_performance_config() if hasattr(self.cfg, 'get_performance_config') else {}
        self.target_profit_per_cycle = perf_cfg.get('expected_profit_per_cycle_pct', 0.35) / 100
        self.daily_target_profit = perf_cfg.get('daily_target_profit_pct', 4.375) / 100
        self.target_cycles_per_day = perf_cfg.get('target_cycles_per_day', 12)
        
    def start_new_cycle(self, initial_price: float, grid_levels: List[Dict]):
        """
        Start tracking a new trading cycle.
        """
        cycle_id = f"cycle_{int(time.time())}"
        
        self.current_cycle = {
            'id': cycle_id,
            'start_time': datetime.now(),
            'start_price': initial_price,
            'grid_levels': len(grid_levels),
            'orders_placed': 0,
            'orders_filled': 0,
            'buy_orders': [level for level in grid_levels if level['side'] == 'BUY'],
            'sell_orders': [level for level in grid_levels if level['side'] == 'SELL'],
            'gross_profit': 0.0,
            'fees_paid': 0.0,
            'net_profit': 0.0,
            'profit_pct': 0.0,
            'status': 'active',
            'fills': []
        }
        
        self.logger.log_signal("cycle_started", {
            "cycle_id": cycle_id,
            "start_price": initial_price,
            "grid_levels": len(grid_levels),
            "timestamp": self.current_cycle['start_time'].isoformat()
        })
        
        return cycle_id
    
    def record_order_fill(self, order_id: str, side: str, price: float, quantity: float, 
                         fee: float, fee_asset: str = 'USDT'):
        """
        Record when a grid order gets filled.
        """
        if not self.current_cycle:
            return
            
        fill_data = {
            'order_id': order_id,
            'timestamp': datetime.now(),
            'side': side,
            'price': price,
            'quantity': quantity,
            'fee': fee,
            'fee_asset': fee_asset,
            'value': price * quantity
        }
        
        self.current_cycle['fills'].append(fill_data)
        self.current_cycle['orders_filled'] += 1
        self.current_cycle['fees_paid'] += fee
        
        # Track BNB fee savings
        # Calculate standard fees
        if fee_asset == 'USDT':
            fees_cfg = self.cfg.get_fees_config() if hasattr(self.cfg, 'get_fees_config') else {}
            base_fee_rate = fees_cfg.get('maker_fee_pct', 0.1) / 100
            fee_amount = (price * quantity) * base_fee_rate
            self.total_fees += fee_amount
        
        self.logger.log_signal("order_filled", {
            "cycle_id": self.current_cycle['id'],
            "order_id": order_id,
            "side": side,
            "price": price,
            "quantity": quantity,
            "fee": fee,
            "fee_asset": fee_asset
        })
        
        # Check if cycle is complete
        self._check_cycle_completion()
    
    def _check_cycle_completion(self):
        """
        Check if the current cycle has completed (buy-sell pair matched).
        """
        if not self.current_cycle:
            return
            
        fills = self.current_cycle['fills']
        buy_fills = [f for f in fills if f['side'] == 'BUY']
        sell_fills = [f for f in fills if f['side'] == 'SELL']
        
        # Simple completion check: at least one buy and one sell
        if len(buy_fills) > 0 and len(sell_fills) > 0:
            self._complete_cycle()
    
    def _complete_cycle(self):
        """
        Mark the current cycle as complete and calculate profits.
        """
        if not self.current_cycle:
            return
            
        cycle = self.current_cycle
        cycle['end_time'] = datetime.now()
        cycle['duration'] = cycle['end_time'] - cycle['start_time']
        cycle['status'] = 'completed'
        
        # Calculate profits
        buy_fills = [f for f in cycle['fills'] if f['side'] == 'BUY']
        sell_fills = [f for f in cycle['fills'] if f['side'] == 'SELL']
        
        total_buy_value = sum(f['value'] for f in buy_fills)
        total_sell_value = sum(f['value'] for f in sell_fills)
        
        cycle['gross_profit'] = total_sell_value - total_buy_value
        cycle['net_profit'] = cycle['gross_profit'] - cycle['fees_paid']
        
        # Calculate profit percentage based on capital used
        if total_buy_value > 0:
            cycle['profit_pct'] = (cycle['net_profit'] / total_buy_value) * 100
        
        # Update totals and track wins/losses
        if cycle['net_profit'] > 0:
            self.total_profit += cycle['net_profit']
            self.winning_cycles += 1
            # Reset drawdown on profit
            self.current_drawdown = 0.0
        else:
            self.total_loss += abs(cycle['net_profit'])
            self.losing_cycles += 1
            # Update drawdown tracking
            self.current_drawdown += abs(cycle['net_profit'])
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown
        
        self.total_fees_paid += cycle['fees_paid']
        
        # Add to cycles history
        self.cycles.append(cycle)
        
        # Update daily stats
        self._update_daily_stats(cycle)
        
        self.logger.log_signal("cycle_completed", {
            "cycle_id": cycle['id'],
            "duration_minutes": cycle['duration'].total_seconds() / 60,
            "gross_profit": cycle['gross_profit'],
            "net_profit": cycle['net_profit'],
            "profit_pct": cycle['profit_pct'],
            "fees_paid": cycle['fees_paid'],
            "target_met": cycle['profit_pct'] >= (self.target_profit_per_cycle * 100)
        })
        
        # Reset current cycle
        self.current_cycle = None
    
    def _update_daily_stats(self, completed_cycle):
        """
        Update daily performance statistics.
        """
        today = completed_cycle['end_time'].date()
        
        if today not in self.daily_stats:
            self.daily_stats[today] = {
                'cycles_completed': 0,
                'gross_profit': 0.0,
                'net_profit': 0.0,
                'fees_paid': 0.0,
                'avg_profit_per_cycle': 0.0,
                'target_cycles_met': 0,
                'daily_target_met': False
            }
        
        daily = self.daily_stats[today]
        daily['cycles_completed'] += 1
        daily['gross_profit'] += completed_cycle['gross_profit']
        daily['net_profit'] += completed_cycle['net_profit']
        daily['fees_paid'] += completed_cycle['fees_paid']
        daily['avg_profit_per_cycle'] = daily['net_profit'] / daily['cycles_completed']
        
        # Check if cycle met target
        if completed_cycle['profit_pct'] >= (self.target_profit_per_cycle * 100):
            daily['target_cycles_met'] += 1
        
        # Check if daily target is met
        daily['daily_target_met'] = (daily['net_profit'] / self.total_capital) >= self.daily_target_profit
        
        self.logger.log_signal("daily_stats_updated", {
            "date": today.isoformat(),
            "cycles_completed": daily['cycles_completed'],
            "net_profit": daily['net_profit'],
            "target_cycles_met": daily['target_cycles_met'],
            "daily_target_met": daily['daily_target_met']
        })
    
    def get_performance_summary(self) -> Dict:
        """
        Get comprehensive performance summary.
        """
        total_cycles = len(self.cycles)
        successful_cycles = len([c for c in self.cycles if c['profit_pct'] >= (self.target_profit_per_cycle * 100)])
        
        avg_profit_per_cycle = sum(c['net_profit'] for c in self.cycles) / total_cycles if total_cycles > 0 else 0
        avg_profit_pct = sum(c['profit_pct'] for c in self.cycles) / total_cycles if total_cycles > 0 else 0
        
        net_pnl = self.total_profit - self.total_loss
        win_rate = (self.winning_cycles / total_cycles * 100) if total_cycles > 0 else 0
        
        return {
            'total_cycles': total_cycles,
            'winning_cycles': self.winning_cycles,
            'losing_cycles': self.losing_cycles,
            'win_rate': win_rate,
            'successful_cycles': successful_cycles,
            'success_rate': (successful_cycles / total_cycles * 100) if total_cycles > 0 else 0,
            'total_gross_profit': self.total_profit,
            'total_gross_loss': self.total_loss,
            'total_net_pnl': net_pnl,
            'total_fees_paid': self.total_fees_paid,
            'fees_saved_bnb': self.fees_saved_bnb,
            'max_drawdown': self.max_drawdown,
            'current_drawdown': self.current_drawdown,
            'profit_factor': (self.total_profit / self.total_loss) if self.total_loss > 0 else float('inf'),
            'avg_profit_per_cycle': avg_profit_per_cycle,
            'avg_profit_pct': avg_profit_pct,
            'target_profit_pct': self.target_profit_per_cycle * 100,
            'daily_stats': dict(self.daily_stats),
            'current_cycle_active': self.current_cycle is not None,
            'risk_metrics': {
                'max_consecutive_losses': self._calculate_max_consecutive_losses(),
                'avg_loss_per_losing_cycle': self.total_loss / self.losing_cycles if self.losing_cycles > 0 else 0,
                'largest_single_loss': self._get_largest_single_loss()
            }
        }
    
    def _calculate_max_consecutive_losses(self) -> int:
        """Calculate maximum consecutive losing cycles."""
        if not self.cycles:
            return 0
            
        max_consecutive = 0
        current_consecutive = 0
        
        for cycle in self.cycles:
            if cycle['net_profit'] < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
                
        return max_consecutive
    
    def _get_largest_single_loss(self) -> float:
        """Get the largest single cycle loss."""
        if not self.cycles:
            return 0.0
            
        losses = [cycle['net_profit'] for cycle in self.cycles if cycle['net_profit'] < 0]
        return abs(min(losses)) if losses else 0.0
    
    def check_risk_alerts(self) -> List[Dict]:
        """Check for risk alert conditions."""
        alerts = []
        
        # Max drawdown alert
        risk_cfg = self.cfg.get_risk_config()
        max_drawdown_pct = risk_cfg.get('max_drawdown_pct', 15.0)
        
        if self.current_drawdown > 0:
            drawdown_pct = (self.current_drawdown / (self.total_profit + self.total_loss)) * 100
            if drawdown_pct > max_drawdown_pct:
                alerts.append({
                    'type': 'MAX_DRAWDOWN_EXCEEDED',
                    'message': f'Current drawdown {drawdown_pct:.2f}% exceeds limit {max_drawdown_pct}%',
                    'severity': 'HIGH',
                    'current_value': drawdown_pct,
                    'limit': max_drawdown_pct
                })
        
        # Consecutive losses alert
        consecutive_losses = self._calculate_max_consecutive_losses()
        if consecutive_losses >= 5:
            alerts.append({
                'type': 'CONSECUTIVE_LOSSES',
                'message': f'{consecutive_losses} consecutive losing cycles detected',
                'severity': 'MEDIUM',
                'current_value': consecutive_losses,
                'limit': 5
            })
        
        # Win rate alert
        if len(self.cycles) >= 10:
            win_rate = (self.winning_cycles / len(self.cycles)) * 100
            if win_rate < 60:  # Grid strategies should have high win rate
                alerts.append({
                    'type': 'LOW_WIN_RATE',
                    'message': f'Win rate {win_rate:.1f}% below expected threshold',
                    'severity': 'MEDIUM',
                    'current_value': win_rate,
                    'limit': 60.0
                })
        
        return alerts
    
    def export_performance_data(self, filepath: str):
        """
        Export performance data to JSON file.
        """
        data = {
            'export_timestamp': datetime.now().isoformat(),
            'performance_summary': self.get_performance_summary(),
            'cycles_history': [
                {
                    **cycle,
                    'start_time': cycle['start_time'].isoformat(),
                    'end_time': cycle['end_time'].isoformat() if cycle.get('end_time') else None,
                    'duration': str(cycle['duration']) if cycle.get('duration') else None
                }
                for cycle in self.cycles
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        self.logger.log_signal("performance_exported", {
            "filepath": filepath,
            "cycles_exported": len(self.cycles)
        })