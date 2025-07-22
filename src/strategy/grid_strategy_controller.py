# grid_strategy_controller.py
import pandas as pd 
import time
from datetime import datetime

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
        Define base grid parameters.
        """
        # (implement your logic here)
        pass

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
        Generate new grid levels, set self.grid_levels.
        """
        # (implement your logic here)
        pass

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
        Main k-line polling, indicator computation, trailing grid check,
        regime/grid updates, and trade execution.
        """
        while True:
            # 1. Fetch latest data
            # 2. Compute indicators (e.g., moving averages)
            # 3. Run trailing grid logic (maybe_trail_grid)
            # 4. Run regime detection and grid adjustments if needed
            # 5. Execute trades as per grid/logic
            # 6. Save state/log as needed
            # 7. Sleep until next poll
            time.sleep(poll_interval)
            # (implement these steps)

    def start_trading(self, historic_days=1, simulation_mode=False):
        print("="*60)
        print("INITIALIZING TRAILING GRID STRATEGY")
        print("="*60)
        # Fetch historical data, compute initial indicators, etc.
        # (your initialization code)
        self.polling_loop(poll_interval=self.cfg.get_trading_config().get("poll_interval", 5))

    def get_grid_status(self):
        return {
            'total_levels': len(self.grid_levels) if self.grid_levels else 0,
            'bought_levels': len(self.bought_levels),
            'completed_trades': len(self.sold_levels),
            'current_regime': self.current_regime,
            'grid_generated': self.grid_generated,
            'position': self.position
        }
