from config.config_manager import ConfigManager
from eventlog.event_logger import EventLogger
from position.position_manager import PositionManager
from strategy.risk_manager import RiskManager
from strategy.strategy_state import StrategyState

def test_foundation():
 # 1. Initialize core components
    cfg = ConfigManager("config/config.yaml")
    logger = EventLogger(cfg)
    pm = PositionManager(logger)
    ss = StrategyState()
    risk = RiskManager(cfg, pm)

    # 2. Example usage (replace with your actual strategy logic)
    # -- Update strategy state --
    ss.update_grid_state([10000,10500,11000], [10500], [])
    
    # -- Example: Risk checks --
    current_position = pm.get_position_summary()["current_position"]
    if current_position:
        risk.check_position_limits(current_position)
        risk.validate_trade_size(0.1, current_position["buy_price"])
        risk.emergency_stop_check(current_price=9000, entry_price=current_position["buy_price"])

    # -- Save & load state --
    ss.save_state()
    ss.load_state()
    print(ss.get_strategy_status())
if __name__ == "__main__":
    test_foundation()
