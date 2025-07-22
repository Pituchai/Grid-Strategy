import os
import csv
from datetime import datetime

class EventLogger:
    def __init__(self, config_manager, log_dir="logs", log_filename="events.csv"):
        self.config = config_manager
        os.makedirs(log_dir, exist_ok=True)
        self.csv_file = os.path.join(log_dir, log_filename)
        self._init_csv_file()

    def _init_csv_file(self):
        # Write header row if file doesn't exist
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "type",
                    "symbol", "side", "qty", "price",
                    "signal_type", "reason", "confidence", "error"
                ])

    def log_trade(self, trade_data):
        self._write_event("trade", trade_data)

    def log_signal(self, signal_type, data):
        self._write_event("signal", {"signal_type": signal_type, **data})

    def log_error(self, error_info):
        if isinstance(error_info, dict):
            err = error_info.get("error", str(error_info))
        else:
            err = str(error_info)
        self._write_event("error", {"error": err})

    def _write_event(self, event_type, data):
        row = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "symbol": "",
            "side": "",
            "qty": "",
            "price": "",
            "signal_type": "",
            "reason": "",
            "confidence": "",
            "error": "",
        }
        row.update(data)
        header = [
            "timestamp", "type", "symbol", "side", "qty", "price",
            "signal_type", "reason", "confidence", "error"
        ]
        with open(self.csv_file, "a", newline='') as f:
            writer = csv.writer(f)
            writer.writerow([row.get(h, "") for h in header])

    def generate_report(self):
        counts = {"trade": 0, "signal": 0, "error": 0}
        if not os.path.exists(self.csv_file):
            return counts
        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = row["type"]
                if t in counts:
                    counts[t] += 1
        return counts
