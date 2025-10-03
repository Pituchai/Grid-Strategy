#!/usr/bin/env python3
"""
Grid State Manager - File-based persistence for grid trading strategy
Maintains state between runs using JSON files.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import shutil


class GridStateManager:
    """
    Manages persistent storage of grid trading state using JSON files.
    
    Handles:
    - Grid levels and configuration
    - Position tracking (bought/sold levels)  
    - Portfolio balances and statistics
    - Risk manager state
    - Trading history and metrics
    """
    
    def __init__(self, state_dir: str = "persistence", backup_count: int = 5):
        """
        Initialize the state manager.
        
        Args:
            state_dir: Directory to store state files
            backup_count: Number of backup files to keep
        """
        self.state_dir = os.path.abspath(state_dir)
        self.backup_count = backup_count
        
        # State file paths
        self.grid_state_file = os.path.join(self.state_dir, "grid_state.json")
        self.portfolio_state_file = os.path.join(self.state_dir, "portfolio_state.json")
        self.trading_stats_file = os.path.join(self.state_dir, "trading_stats.json")
        self.risk_state_file = os.path.join(self.state_dir, "risk_state.json")
        
        # Ensure state directory exists
        os.makedirs(self.state_dir, exist_ok=True)
        
        print(f"✅ GridStateManager initialized - State directory: {self.state_dir}")
    
    def _create_backup(self, file_path: str) -> None:
        """Create a timestamped backup of the state file."""
        if not os.path.exists(file_path):
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.backup_{timestamp}"
        
        try:
            shutil.copy2(file_path, backup_path)
            
            # Clean up old backups
            self._cleanup_old_backups(file_path)
            
        except Exception as e:
            print(f"⚠️  Failed to create backup for {file_path}: {e}")
    
    def _cleanup_old_backups(self, file_path: str) -> None:
        """Remove old backup files, keeping only the most recent ones."""
        try:
            dir_path = os.path.dirname(file_path)
            base_name = os.path.basename(file_path)
            
            # Find all backup files for this state file
            backup_files = []
            for file in os.listdir(dir_path):
                if file.startswith(f"{base_name}.backup_"):
                    backup_files.append(os.path.join(dir_path, file))
            
            # Sort by modification time (newest first)
            backup_files.sort(key=os.path.getmtime, reverse=True)
            
            # Remove old backups beyond the backup count
            for old_backup in backup_files[self.backup_count:]:
                os.remove(old_backup)
                
        except Exception as e:
            print(f"⚠️  Failed to cleanup old backups: {e}")
    
    def _save_json_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """Safely save data to JSON file with backup."""
        try:
            # Create backup of existing file
            self._create_backup(file_path)
            
            # Add metadata
            data_with_metadata = {
                'timestamp': datetime.now().isoformat(),
                'version': '1.0',
                'data': data
            }
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = f"{file_path}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data_with_metadata, f, indent=2, default=str)
            
            # Atomic rename
            os.rename(temp_file, file_path)
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to save {file_path}: {e}")
            return False
    
    def _load_json_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Safely load data from JSON file."""
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, 'r') as f:
                content = json.load(f)
            
            # Handle both new format (with metadata) and old format (direct data)
            if isinstance(content, dict) and 'data' in content:
                return content['data']
            else:
                # Old format - return as is
                return content
                
        except Exception as e:
            print(f"❌ Failed to load {file_path}: {e}")
            return None
    
    # ========== GRID STATE PERSISTENCE ==========
    
    def save_grid_state(self, 
                       grid_levels: List[Dict], 
                       bought_levels: set, 
                       sold_levels: set,
                       current_regime: str = None,
                       grid_center_price: float = None,
                       **kwargs) -> bool:
        """
        Save current grid state to persistent storage.
        
        Args:
            grid_levels: List of grid level dictionaries
            bought_levels: Set of bought level indices
            sold_levels: Set of sold level tuples (level, price)
            current_regime: Current market regime
            grid_center_price: Center price of the grid
            **kwargs: Additional state data
        """
        state_data = {
            'grid_levels': grid_levels,
            'bought_levels': list(bought_levels),
            'sold_levels': [list(pair) for pair in sold_levels],
            'current_regime': current_regime,
            'grid_center_price': grid_center_price,
            'grid_generated': True,
            'last_updated': datetime.now().isoformat(),
            **kwargs
        }
        
        success = self._save_json_file(self.grid_state_file, state_data)
        if success:
            print(f"💾 Grid state saved - {len(grid_levels)} levels, {len(bought_levels)} bought")
        
        return success
    
    def load_grid_state(self) -> Optional[Dict[str, Any]]:
        """Load grid state from persistent storage."""
        state_data = self._load_json_file(self.grid_state_file)
        
        if state_data:
            # Convert sold_levels back to set of tuples
            if 'sold_levels' in state_data:
                state_data['sold_levels'] = set(tuple(pair) for pair in state_data['sold_levels'])
            
            # Convert bought_levels back to set
            if 'bought_levels' in state_data:
                state_data['bought_levels'] = set(state_data['bought_levels'])
            
            print(f"📂 Grid state loaded - {len(state_data.get('grid_levels', []))} levels")
            return state_data
        
        print("📂 No existing grid state found")
        return None
    
    # ========== PORTFOLIO STATE PERSISTENCE ==========
    
    def save_portfolio_state(self, 
                           usdt_balance: float,
                           btc_balance: float, 
                           total_capital: float,
                           capital_per_grid: float,
                           **kwargs) -> bool:
        """Save portfolio state to persistent storage."""
        portfolio_data = {
            'usdt_balance': usdt_balance,
            'btc_balance': btc_balance,
            'total_capital': total_capital,
            'capital_per_grid': capital_per_grid,
            'last_updated': datetime.now().isoformat(),
            **kwargs
        }
        
        success = self._save_json_file(self.portfolio_state_file, portfolio_data)
        if success:
            print(f"💾 Portfolio state saved - USDT: ${usdt_balance:,.2f}, BTC: {btc_balance:.6f}")
        
        return success
    
    def load_portfolio_state(self) -> Optional[Dict[str, Any]]:
        """Load portfolio state from persistent storage."""
        portfolio_data = self._load_json_file(self.portfolio_state_file)
        
        if portfolio_data:
            print(f"📂 Portfolio state loaded - Capital: ${portfolio_data.get('total_capital', 0):,.2f}")
            return portfolio_data
        
        print("📂 No existing portfolio state found")
        return None
    
    # ========== TRADING STATISTICS PERSISTENCE ==========
    
    def save_trading_stats(self,
                          total_trades: int,
                          total_pnl: float,
                          win_rate: float,
                          winning_trades: int,
                          losing_trades: int,
                          completed_cycles: int,
                          **kwargs) -> bool:
        """Save trading statistics to persistent storage."""
        stats_data = {
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'completed_cycles': completed_cycles,
            'last_updated': datetime.now().isoformat(),
            **kwargs
        }
        
        success = self._save_json_file(self.trading_stats_file, stats_data)
        if success:
            print(f"💾 Trading stats saved - {total_trades} trades, ${total_pnl:.2f} P&L")
        
        return success
    
    def load_trading_stats(self) -> Optional[Dict[str, Any]]:
        """Load trading statistics from persistent storage."""
        stats_data = self._load_json_file(self.trading_stats_file)
        
        if stats_data:
            print(f"📂 Trading stats loaded - {stats_data.get('total_trades', 0)} trades")
            return stats_data
        
        print("📂 No existing trading stats found")
        return None
    
    # ========== RISK STATE PERSISTENCE ==========
    
    def save_risk_state(self,
                       current_drawdown: float,
                       max_drawdown: float,
                       daily_loss: float,
                       consecutive_losses: int,
                       **kwargs) -> bool:
        """Save risk manager state to persistent storage."""
        risk_data = {
            'current_drawdown': current_drawdown,
            'max_drawdown': max_drawdown,
            'daily_loss': daily_loss,
            'consecutive_losses': consecutive_losses,
            'last_updated': datetime.now().isoformat(),
            **kwargs
        }
        
        success = self._save_json_file(self.risk_state_file, risk_data)
        if success:
            print(f"💾 Risk state saved - Drawdown: ${current_drawdown:.2f}")
        
        return success
    
    def load_risk_state(self) -> Optional[Dict[str, Any]]:
        """Load risk manager state from persistent storage."""
        risk_data = self._load_json_file(self.risk_state_file)
        
        if risk_data:
            print(f"📂 Risk state loaded - Max drawdown: ${risk_data.get('max_drawdown', 0):.2f}")
            return risk_data
        
        print("📂 No existing risk state found")
        return None
    
    # ========== COMPREHENSIVE STATE OPERATIONS ==========
    
    def save_complete_state(self, strategy_controller) -> bool:
        """
        Save complete strategy state from the controller.
        
        Args:
            strategy_controller: GridStrategyController instance
        """
        try:
            # 1. Save grid state
            execution_status = strategy_controller.order_executor.get_execution_status()
            grid_success = self.save_grid_state(
                grid_levels=strategy_controller.grid_levels,
                bought_levels=execution_status['bought_levels'],
                sold_levels=execution_status['sold_levels'],
                current_regime=strategy_controller.current_regime,
                grid_center_price=getattr(strategy_controller, 'grid_center_price', None)
            )
            
            # 2. Save portfolio state
            try:
                account_info = strategy_controller.client.get_account()
                usdt_balance = float([asset['free'] for asset in account_info['balances'] 
                                    if asset['asset'] == 'USDT'][0])
                btc_balance = float([asset['free'] for asset in account_info['balances'] 
                                   if asset['asset'] == 'BTC'][0])
            except:
                usdt_balance = 0.0
                btc_balance = 0.0
            
            portfolio_success = self.save_portfolio_state(
                usdt_balance=usdt_balance,
                btc_balance=btc_balance,
                total_capital=strategy_controller.total_capital,
                capital_per_grid=strategy_controller.capital_per_grid
            )
            
            # 3. Save trading statistics
            performance = strategy_controller.cycle_tracker.get_performance_summary()
            stats_success = self.save_trading_stats(
                total_trades=performance.get('total_cycles', 0),
                total_pnl=performance.get('total_net_pnl', 0.0),
                win_rate=performance.get('win_rate', 0.0),
                winning_trades=performance.get('winning_cycles', 0),
                losing_trades=performance.get('losing_cycles', 0),
                completed_cycles=performance.get('total_cycles', 0)
            )
            
            # 4. Save risk state
            risk_status = strategy_controller.risk.get_risk_status()
            risk_success = self.save_risk_state(
                current_drawdown=risk_status.get('current_drawdown', 0.0),
                max_drawdown=risk_status.get('max_drawdown_reached', 0.0),
                daily_loss=risk_status.get('daily_loss', 0.0),
                consecutive_losses=risk_status.get('consecutive_losses', 0)
            )
            
            overall_success = grid_success and portfolio_success and stats_success and risk_success
            
            if overall_success:
                print("✅ Complete strategy state saved successfully")
            else:
                print("⚠️  Some state components failed to save")
            
            return overall_success
            
        except Exception as e:
            print(f"❌ Failed to save complete state: {e}")
            return False
    
    def load_complete_state(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Load complete strategy state.
        
        Returns:
            Dictionary containing all loaded state components
        """
        return {
            'grid_state': self.load_grid_state(),
            'portfolio_state': self.load_portfolio_state(),
            'trading_stats': self.load_trading_stats(),
            'risk_state': self.load_risk_state()
        }
    
    def clear_all_state(self) -> bool:
        """Clear all persistent state (for reset/testing purposes)."""
        try:
            state_files = [
                self.grid_state_file,
                self.portfolio_state_file, 
                self.trading_stats_file,
                self.risk_state_file
            ]
            
            for file_path in state_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            print("🗑️  All persistent state cleared")
            return True
            
        except Exception as e:
            print(f"❌ Failed to clear state: {e}")
            return False
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get a summary of current persistent state."""
        state_files = [
            ('Grid State', self.grid_state_file),
            ('Portfolio State', self.portfolio_state_file),
            ('Trading Stats', self.trading_stats_file),
            ('Risk State', self.risk_state_file)
        ]
        
        summary = {}
        for name, file_path in state_files:
            if os.path.exists(file_path):
                try:
                    stat_info = os.stat(file_path)
                    summary[name] = {
                        'exists': True,
                        'size': stat_info.st_size,
                        'modified': datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                    }
                except:
                    summary[name] = {'exists': True, 'size': 0, 'modified': 'unknown'}
            else:
                summary[name] = {'exists': False}
        
        return summary