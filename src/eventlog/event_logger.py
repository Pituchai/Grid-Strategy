import os
import csv
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from logging.handlers import RotatingFileHandler

class EventLogger:
    """
    Enhanced event logger for comprehensive grid trading monitoring.
    Supports multiple log formats, rotation, and advanced analytics.
    """
    
    def _convert_for_json(self, value):
        """Convert numpy/pandas types to JSON serializable types"""
        import numpy as np
        
        if isinstance(value, dict):
            return {k: self._convert_for_json(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._convert_for_json(v) for v in value]
        elif isinstance(value, np.integer):
            return int(value)
        elif isinstance(value, np.floating):
            return float(value)
        elif isinstance(value, np.ndarray):
            return value.tolist()
        elif hasattr(value, 'item'):  # pandas scalars
            return value.item()
        return value
    
    def __init__(self, config_manager=None, log_dir="logs", log_filename="events.csv"):
        self.config = config_manager
        
        # Load logging configuration from YAML
        if config_manager and hasattr(config_manager, 'get_logging_config'):
            log_cfg = config_manager.get_logging_config()
            self.log_dir = log_cfg.get('log_directory', 'logs')
            self.max_log_size_mb = log_cfg.get('max_log_size_mb', 50)
            self.backup_count = log_cfg.get('backup_count', 5)
            self.main_log_level = log_cfg.get('main_log_level', 'INFO')
            self.console_log_level = log_cfg.get('console_log_level', 'INFO')
            self.enable_email_alerts = log_cfg.get('enable_email_alerts', False)
            self.create_performance_charts = log_cfg.get('create_performance_charts', True)
            self.export_trades_csv = log_cfg.get('export_trades_csv', True)
            self.real_time_monitoring = log_cfg.get('real_time_monitoring', True)
        else:
            # Default values if no config manager
            self.log_dir = log_dir
            self.max_log_size_mb = 50
            self.backup_count = 5
            self.main_log_level = 'INFO'
            self.console_log_level = 'INFO'
            self.enable_email_alerts = False
            self.create_performance_charts = True
            self.export_trades_csv = True
            self.real_time_monitoring = True
        
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Initialize multiple log files
        self.csv_file = os.path.join(self.log_dir, log_filename)
        self.json_file = os.path.join(self.log_dir, "events.json")
        self.performance_file = os.path.join(self.log_dir, "performance.json")
        self.risk_file = os.path.join(self.log_dir, "risk_events.json")
        
        # Initialize structured logging
        self._init_structured_logging()
        self._init_csv_file()
        
        # Performance tracking
        self.session_start = datetime.now()
        self.events_count = {
            'trades': 0, 'signals': 0, 'errors': 0, 'risk_alerts': 0,
            'grid_operations': 0, 'cycle_completions': 0
        }

    def _init_structured_logging(self):
        """Initialize structured logging with YAML configuration."""
        # Create main logger with YAML-configured level
        self.logger = logging.getLogger('GridTrading')
        self.logger.setLevel(getattr(logging, self.main_log_level.upper(), logging.INFO))
        
        # Clear any existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Create rotating file handler with YAML settings
        log_file = os.path.join(self.log_dir, 'grid_trading.log')
        max_bytes = self.max_log_size_mb * 1024 * 1024
        handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=self.backup_count
        )
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Add console handler with YAML-configured level
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.console_log_level.upper(), logging.INFO))
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Log configuration loaded
        self.logger.info(f"Logging configured: Main={self.main_log_level}, Console={self.console_log_level}")
        self.logger.info(f"Log directory: {self.log_dir}, Max size: {self.max_log_size_mb}MB, Backup count: {self.backup_count}")
    
    def _init_csv_file(self):
        """Initialize enhanced CSV log file."""
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "session_id", "event_type", "event_subtype",
                    "symbol", "side", "quantity", "price", "order_id",
                    "grid_level", "cycle_id", "pnl", "fee", "fee_asset",
                    "risk_level", "message", "data_json", "error"
                ])

    def log_trade(self, trade_data: Dict[str, Any]):
        """Log trading events with enhanced data."""
        self.events_count['trades'] += 1
        self._write_enhanced_event("trade", "execution", trade_data)
        self.logger.info(f"TRADE: {trade_data.get('side', 'N/A')} {trade_data.get('quantity', 0)} at ${trade_data.get('price', 0)}")

    def log_grid_operation(self, operation_type: str, data: Dict[str, Any]):
        """Log grid-specific operations."""
        self.events_count['grid_operations'] += 1
        self._write_enhanced_event("grid", operation_type, data)
        self.logger.info(f"GRID_{operation_type.upper()}: {data.get('message', 'Grid operation executed')}")

    def log_cycle_event(self, cycle_event: str, data: Dict[str, Any]):
        """Log trading cycle events."""
        if cycle_event == 'completed':
            self.events_count['cycle_completions'] += 1
        self._write_enhanced_event("cycle", cycle_event, data)
        self.logger.info(f"CYCLE_{cycle_event.upper()}: {data.get('message', f'Cycle {cycle_event}')}")

    def log_risk_event(self, risk_type: str, data: Dict[str, Any]):
        """Log risk management events."""
        self.events_count['risk_alerts'] += 1
        risk_level = data.get('severity', 'MEDIUM')
        
        # Write to risk-specific log
        self._write_risk_event(risk_type, data)
        
        # Write to main event log
        self._write_enhanced_event("risk", risk_type, data)
        
        # Log with appropriate level
        if risk_level == 'CRITICAL':
            self.logger.critical(f"RISK_CRITICAL: {data.get('message', 'Critical risk event')}")
        elif risk_level == 'HIGH':
            self.logger.error(f"RISK_HIGH: {data.get('message', 'High risk event')}")
        else:
            self.logger.warning(f"RISK_{risk_level}: {data.get('message', 'Risk event')}")

    def log_performance_event(self, perf_type: str, data: Dict[str, Any]):
        """Log performance-related events."""
        self._write_performance_event(perf_type, data)
        self._write_enhanced_event("performance", perf_type, data)
        self.logger.info(f"PERFORMANCE_{perf_type.upper()}: {data.get('message', 'Performance event')}")

    def log_signal(self, signal_type: str, data: Dict[str, Any]):
        """Enhanced signal logging."""
        self.events_count['signals'] += 1
        enhanced_data = {"signal_type": signal_type, **data}
        self._write_enhanced_event("signal", signal_type, enhanced_data)
        self.logger.info(f"SIGNAL_{signal_type.upper()}: {data.get('message', 'Signal generated')}")

    def log_error(self, error_info: Any, context: Dict[str, Any] = None):
        """Enhanced error logging with context."""
        self.events_count['errors'] += 1
        
        if isinstance(error_info, dict):
            error_msg = error_info.get("error", str(error_info))
        else:
            error_msg = str(error_info)
        
        error_data = {
            "error": error_msg,
            "context": context or {},
            "stack_trace": getattr(error_info, '__traceback__', None)
        }
        
        self._write_enhanced_event("error", "exception", error_data)
        self.logger.error(f"ERROR: {error_msg}")

    def _write_enhanced_event(self, event_type: str, event_subtype: str, data: Dict[str, Any]):
        """Write event to enhanced CSV format."""
        timestamp = datetime.now()
        session_id = getattr(self, 'session_id', timestamp.strftime('%Y%m%d_%H%M%S'))
        
        # Enhanced row structure
        row = {
            "timestamp": timestamp.isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "event_subtype": event_subtype,
            "symbol": data.get("symbol", ""),
            "side": data.get("side", ""),
            "quantity": data.get("quantity", ""),
            "price": data.get("price", ""),
            "order_id": data.get("order_id", ""),
            "grid_level": data.get("level", data.get("grid_level", "")),
            "cycle_id": data.get("cycle_id", ""),
            "pnl": data.get("pnl", data.get("net_profit", "")),
            "fee": data.get("fee", data.get("fees_paid", "")),
            "fee_asset": data.get("fee_asset", ""),
            "risk_level": data.get("severity", data.get("risk_level", "")),
            "message": data.get("message", ""),
            "data_json": json.dumps({k: self._convert_for_json(v) for k, v in data.items() if k not in [
                "symbol", "side", "quantity", "price", "order_id", "level", 
                "cycle_id", "pnl", "fee", "fee_asset", "severity", "message"
            ]}),
            "error": data.get("error", "")
        }
        
        # Write to CSV only if enabled in YAML config
        if self.export_trades_csv:
            header = [
                "timestamp", "session_id", "event_type", "event_subtype",
                "symbol", "side", "quantity", "price", "order_id",
                "grid_level", "cycle_id", "pnl", "fee", "fee_asset", 
                "risk_level", "message", "data_json", "error"
            ]
            
            with open(self.csv_file, "a", newline='') as f:
                writer = csv.writer(f)
                writer.writerow([row.get(h, "") for h in header])
        
        # Also write to JSON log
        self._write_json_event(event_type, event_subtype, data, timestamp)

    def _write_json_event(self, event_type: str, event_subtype: str, data: Dict[str, Any], timestamp: datetime):
        """Write structured JSON event to proper JSON array."""
        event = {
            "timestamp": timestamp.isoformat(),
            "session_id": getattr(self, 'session_id', timestamp.strftime('%Y%m%d_%H%M%S')),
            "event_type": event_type,
            "event_subtype": event_subtype,
            "data": data
        }
        
        # Convert all values to JSON serializable format
        serializable_event = {k: self._convert_for_json(v) for k, v in event.items()}
        
        # Read existing events or initialize empty array
        events = []
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        events = json.loads(content)
            except (json.JSONDecodeError, FileNotFoundError):
                events = []
        
        # Add new event
        events.append(serializable_event)
        
        # Write back as proper JSON array
        with open(self.json_file, "w") as f:
            json.dump(events, f, indent=2)

    def _write_risk_event(self, risk_type: str, data: Dict[str, Any]):
        """Write risk event to dedicated risk log."""
        risk_event = {
            "timestamp": datetime.now().isoformat(),
            "risk_type": risk_type,
            "severity": data.get("severity", "MEDIUM"),
            "message": data.get("message", ""),
            "current_value": data.get("current_value"),
            "limit": data.get("limit"),
            "action": data.get("action", "NONE"),
            "data": data
        }
        
        # Convert all values to JSON serializable format
        serializable_event = {k: self._convert_for_json(v) for k, v in risk_event.items()}
        
        # Read existing events or initialize empty array
        events = []
        if os.path.exists(self.risk_file):
            try:
                with open(self.risk_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        events = json.loads(content)
            except (json.JSONDecodeError, FileNotFoundError):
                events = []
        
        # Add new event
        events.append(serializable_event)
        
        # Write back as proper JSON array
        with open(self.risk_file, "w") as f:
            json.dump(events, f, indent=2)

    def _write_performance_event(self, perf_type: str, data: Dict[str, Any]):
        """Write performance event to dedicated performance log."""
        perf_event = {
            "timestamp": datetime.now().isoformat(),
            "performance_type": perf_type,
            "metrics": data,
            "session_duration": str(datetime.now() - self.session_start)
        }
        
        with open(self.performance_file, "a") as f:
            # Convert all values to JSON serializable format
            serializable_event = {k: self._convert_for_json(v) for k, v in perf_event.items()}
            f.write(json.dumps(serializable_event) + "\n")

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive event report."""
        session_duration = datetime.now() - self.session_start
        
        # Count events from CSV
        csv_counts = {"trade": 0, "signal": 0, "error": 0, "risk": 0, "grid": 0, "cycle": 0}
        if os.path.exists(self.csv_file):
            with open(self.csv_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    event_type = row.get("event_type", "")
                    if event_type in csv_counts:
                        csv_counts[event_type] += 1

        return {
            "session_start": self.session_start.isoformat(),
            "session_duration": str(session_duration),
            "events_count": self.events_count,
            "csv_counts": csv_counts,
            "total_events": sum(self.events_count.values()),
            "log_files": {
                "csv": self.csv_file,
                "json": self.json_file,
                "performance": self.performance_file,
                "risk": self.risk_file,
                "main_log": os.path.join(self.log_dir, 'grid_trading.log')
            }
        }

    def get_recent_events(self, event_type: str = None, hours: int = 1) -> List[Dict[str, Any]]:
        """Get recent events from JSON log."""
        events = []
        if not os.path.exists(self.json_file):
            return events
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with open(self.json_file, "r") as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    event_time = datetime.fromisoformat(event["timestamp"])
                    
                    if event_time > cutoff_time:
                        if event_type is None or event["event_type"] == event_type:
                            events.append(event)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        
        return sorted(events, key=lambda x: x["timestamp"], reverse=True)

    def get_risk_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get risk events summary."""
        if not os.path.exists(self.risk_file):
            return {"total_risk_events": 0, "by_severity": {}, "by_type": {}}
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        by_severity = {}
        by_type = {}
        total = 0
        
        with open(self.risk_file, "r") as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    event_time = datetime.fromisoformat(event["timestamp"])
                    
                    if event_time > cutoff_time:
                        total += 1
                        severity = event.get("severity", "UNKNOWN")
                        risk_type = event.get("risk_type", "UNKNOWN")
                        
                        by_severity[severity] = by_severity.get(severity, 0) + 1
                        by_type[risk_type] = by_type.get(risk_type, 0) + 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        
        return {
            "total_risk_events": total,
            "by_severity": by_severity,
            "by_type": by_type,
            "time_window_hours": hours
        }

    def export_session_data(self, output_file: str):
        """Export complete session data."""
        session_data = {
            "session_info": {
                "start_time": self.session_start.isoformat(),
                "end_time": datetime.now().isoformat(),
                "duration": str(datetime.now() - self.session_start)
            },
            "events_summary": self.generate_report(),
            "risk_summary": self.get_risk_summary(),
            "recent_events": self.get_recent_events(hours=24)
        }
        
        with open(output_file, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)
            
        self.logger.info(f"Session data exported to: {output_file}")
    
    def should_send_email_alert(self, alert_type: str) -> bool:
        """Check if email alerts are enabled for this type."""
        if not self.enable_email_alerts:
            return False
        
        # Load alert settings from YAML config
        if self.config and hasattr(self.config, 'get_logging_config'):
            log_cfg = self.config.get_logging_config()
            if alert_type == 'profit_milestone':
                return log_cfg.get('alert_on_profit_milestone', True)
            elif alert_type == 'risk_events':
                return log_cfg.get('alert_on_risk_events', True)
        
        return False
    
    def should_create_performance_charts(self) -> bool:
        """Check if performance chart generation is enabled."""
        return self.create_performance_charts
    
    def is_real_time_monitoring_enabled(self) -> bool:
        """Check if real-time monitoring is enabled."""
        return self.real_time_monitoring
    
    def get_logging_configuration_summary(self) -> dict:
        """Get current logging configuration summary."""
        return {
            'log_directory': self.log_dir,
            'max_log_size_mb': self.max_log_size_mb,
            'backup_count': self.backup_count,
            'main_log_level': self.main_log_level,
            'console_log_level': self.console_log_level,
            'enable_email_alerts': self.enable_email_alerts,
            'create_performance_charts': self.create_performance_charts,
            'export_trades_csv': self.export_trades_csv,
            'real_time_monitoring': self.real_time_monitoring
        }
