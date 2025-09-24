"""
Trade persistence and CSV export functionality.
Handles saving trade history based on YAML configuration.
"""
import csv
import os
from datetime import datetime
from typing import Dict, List


class TradePersistence:
    """Handles saving and exporting trade data based on YAML configuration."""
    
    def __init__(self, config_manager, event_logger):
        self.cfg = config_manager
        self.logger = event_logger
        
        # Get logging configuration
        logging_cfg = self.cfg.get_logging_config()
        self.export_trades_csv = logging_cfg.get('export_trades_csv', True)
        self.save_trades = self.cfg.get_performance_config().get('save_trades', True) if hasattr(self.cfg, 'get_performance_config') else True
        self.log_directory = logging_cfg.get('log_directory', 'logs')
        
        # Ensure logs directory exists
        os.makedirs(self.log_directory, exist_ok=True)
        
        # Trade history storage
        self.trade_history = []
        self.csv_file_path = os.path.join(self.log_directory, 'trade_history.csv')
        
        # Initialize CSV file with headers if needed
        if self.export_trades_csv:
            self._initialize_csv_file()
    
    def _initialize_csv_file(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.csv_file_path):
            headers = [
                'timestamp', 'trade_id', 'symbol', 'side', 'quantity', 'price',
                'grid_level', 'order_id', 'pnl', 'fees', 'trade_type', 'notes'
            ]
            with open(self.csv_file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(headers)
            
            self.logger.log_signal("csv_trade_file_initialized", {
                "file_path": self.csv_file_path,
                "headers": headers
            })
    
    def save_trade(self, trade_data: Dict):
        """
        Save a trade to both memory and CSV (if enabled).
        
        trade_data should contain:
        - timestamp, symbol, side, quantity, price
        - grid_level, order_id, trade_type
        - Optional: pnl, fees, notes
        """
        if not self.save_trades:
            return
        
        # Standardize trade data
        standardized_trade = {
            'timestamp': trade_data.get('timestamp', datetime.now().isoformat()),
            'trade_id': trade_data.get('trade_id', f"{trade_data.get('side')}_{trade_data.get('grid_level')}_{int(datetime.now().timestamp())}"),
            'symbol': trade_data.get('symbol', 'BTCUSDT'),
            'side': trade_data.get('side', 'UNKNOWN'),
            'quantity': float(trade_data.get('quantity', 0)),
            'price': float(trade_data.get('price', 0)),
            'grid_level': trade_data.get('grid_level', 0),
            'order_id': trade_data.get('order_id', ''),
            'pnl': float(trade_data.get('pnl', 0)),
            'fees': float(trade_data.get('fees', 0)),
            'trade_type': trade_data.get('trade_type', 'GRID'),
            'notes': trade_data.get('notes', '')
        }
        
        # Add to memory
        self.trade_history.append(standardized_trade)
        
        # Export to CSV if enabled
        if self.export_trades_csv:
            self._append_to_csv(standardized_trade)
        
        # Log the save
        self.logger.log_signal("trade_saved", {
            "trade_id": standardized_trade['trade_id'],
            "side": standardized_trade['side'],
            "price": standardized_trade['price'],
            "pnl": standardized_trade['pnl']
        })
    
    def _append_to_csv(self, trade_data: Dict):
        """Append a single trade to the CSV file."""
        try:
            with open(self.csv_file_path, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([
                    trade_data['timestamp'],
                    trade_data['trade_id'], 
                    trade_data['symbol'],
                    trade_data['side'],
                    trade_data['quantity'],
                    trade_data['price'],
                    trade_data['grid_level'],
                    trade_data['order_id'],
                    trade_data['pnl'],
                    trade_data['fees'],
                    trade_data['trade_type'],
                    trade_data['notes']
                ])
        except Exception as e:
            self.logger.log_error("Failed to write trade to CSV", {
                "error": str(e),
                "csv_path": self.csv_file_path
            })
    
    def get_trade_history(self, limit: int = None) -> List[Dict]:
        """Get trade history from memory."""
        if limit:
            return self.trade_history[-limit:]
        return self.trade_history.copy()
    
    def get_performance_summary(self) -> Dict:
        """Get basic performance summary from saved trades."""
        if not self.trade_history:
            return {
                'total_trades': 0,
                'total_pnl': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_fees': 0
            }
        
        total_trades = len(self.trade_history)
        total_pnl = sum(trade['pnl'] for trade in self.trade_history)
        total_fees = sum(trade['fees'] for trade in self.trade_history)
        winning_trades = len([t for t in self.trade_history if t['pnl'] > 0])
        losing_trades = len([t for t in self.trade_history if t['pnl'] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_fees': total_fees,
            'avg_pnl_per_trade': total_pnl / total_trades if total_trades > 0 else 0,
            'csv_file_path': self.csv_file_path if self.export_trades_csv else None
        }
    
    def export_performance_report(self, file_path: str = None):
        """Export a detailed performance report to CSV."""
        if not file_path:
            file_path = os.path.join(self.log_directory, f'performance_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        
        summary = self.get_performance_summary()
        
        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            
            # Write summary section
            writer.writerow(['PERFORMANCE SUMMARY'])
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Total Trades', summary['total_trades']])
            writer.writerow(['Total P&L', f"${summary['total_pnl']:.2f}"])
            writer.writerow(['Winning Trades', summary['winning_trades']])
            writer.writerow(['Losing Trades', summary['losing_trades']])
            writer.writerow(['Win Rate', f"{summary['win_rate']:.1f}%"])
            writer.writerow(['Total Fees', f"${summary['total_fees']:.2f}"])
            writer.writerow(['Avg P&L per Trade', f"${summary['avg_pnl_per_trade']:.2f}"])
            writer.writerow([])
            
            # Write detailed trades
            writer.writerow(['DETAILED TRADES'])
            writer.writerow(['Timestamp', 'Side', 'Price', 'Quantity', 'P&L', 'Grid Level', 'Type'])
            
            for trade in self.trade_history:
                writer.writerow([
                    trade['timestamp'],
                    trade['side'],
                    f"${trade['price']:.2f}",
                    f"{trade['quantity']:.6f}",
                    f"${trade['pnl']:.2f}",
                    trade['grid_level'],
                    trade['trade_type']
                ])
        
        self.logger.log_signal("performance_report_exported", {
            "file_path": file_path,
            "total_trades": summary['total_trades'],
            "total_pnl": summary['total_pnl']
        })
        
        return file_path