import json
import os

class StrategyState:
    def __init__(self, state_file="strategy_state.json"):
        self.state_file = state_file
        self.state = {
            "grid_levels": [],
            "bought_levels": [],
            "sold_levels": [],
            "current_regime" : None,
            "regime_strength_history":[],
            "grid_generated": {}
        }
        self.load_state()

    def save_state(self, new_state=None):
        """Update and save State"""
        if new_state:
            self.state.update(new_state)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load state: {e}")

    def update_grid_state(self, grid_levels, bought_levels, sold_levels,regime,regime_history,grid_generated):
        self.state["grid_levels"] = grid_levels
        self.state["bought_levels"] = list(bought_levels)
        self.state["sold_levels"] = [list(pair) for pair in sold_levels]
        self.state["current_regime"] = regime
        self.state["regime_strength_history"] = regime_history
        self.state["grid_generated"] = grid_generated
        self.save_state()

    def get_strategy_status(self):
        """Return summary of strategy state."""
        return self.state
