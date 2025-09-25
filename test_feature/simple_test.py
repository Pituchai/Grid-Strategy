#!/usr/bin/env python3
"""Simple test to check component initialization"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("🧪 SIMPLE COMPONENT TEST")
print("=" * 50)

try:
    print("1. Testing ConfigManager...")
    from config_manager import ConfigManager
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategy_config.yaml")
    cfg = ConfigManager(config_path)
    print("✅ ConfigManager OK")
    
    print("2. Testing EventLogger...")
    from src.eventlog.event_logger import EventLogger
    logger = EventLogger(cfg, log_dir="logs", log_filename="simple_test.csv")
    print("✅ EventLogger OK")
    
    print("3. Testing PositionManager...")
    from src.position.position_manager import PositionManager
    pm = PositionManager(logger)
    print("✅ PositionManager OK")
    
    print("4. Testing StrategyState...")
    from src.strategy.strategy_state import StrategyState
    state = StrategyState("simple_test_state.json")
    print("✅ StrategyState OK")
    
    print("5. Testing RiskManager...")
    from src.strategy.risk_manager import RiskManager
    risk = RiskManager(cfg, logger, pm)
    print("✅ RiskManager OK")
    
    print("\n🎉 ALL COMPONENTS INITIALIZED SUCCESSFULLY!")
    
except Exception as e:
    print(f"❌ Error at step: {e}")
    import traceback
    traceback.print_exc()