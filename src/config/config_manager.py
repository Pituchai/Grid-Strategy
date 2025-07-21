import json
import yaml
import os


class ConfigManager:
    """
    Load and validate configuration parameters for the grid trading strategy.
    Supports JSON and YAML formats.
    """
      
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = {}
        self.load_config()
        self.validate_parameters()

    def load_config(self):
        """
        Read the config file (JSON or YAML) and populate self.config.
        """
        if not os.path.isfile(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        ext = os.path.splitext(self.config_path)[1].lower()
        with open(self.config_path, 'r') as f:
            if ext in ('.yaml', '.yml'):
                self.config = yaml.safe_load(f)
            elif ext == '.json':
                self.config = json.load(f)
            else:
                raise ValueError("Unsupported config format. Use .json, .yaml, or .yml")

    def validate_parameters(self):
        """
        Ensure required sections and keys exist and have valid types/ranges.
        """
        required_sections = ['api', 'grid', 'risk', 'trading']
        for section in required_sections:
            if section not in self.config:
                raise KeyError(f"Missing required config section: '{section}'")

        # Example check: API keys
        api = self.config['api']
        if not api.get('api_key') or not api.get('api_secret'):
            raise ValueError("API credentials (api_key & api_secret) must be provided")

        # Grid config sanity
        grid = self.config['grid']
        if grid.get('levels') <= 0 or grid.get('step_size') <= 0:
            raise ValueError("Grid 'levels' and 'step_size' must be positive numbers")

        # Risk limits
        risk = self.config['risk']
        if not (0 < risk.get('max_exposure_pct', 0) <= 100):
            raise ValueError("Risk 'max_exposure_pct' must be between 0 and 100")

        # Trading parameters
        trading = self.config['trading']
        if trading.get('order_quantity') <= 0:
            raise ValueError("Trading 'order_quantity' must be positive")

    def get_api_config(self) -> dict:
        """Return API configuration: keys, endpoints, etc."""
        return self.config.get('api', {})

    def get_grid_config(self) -> dict:
        """Return grid generation parameters."""
        return self.config.get('grid', {})

    def get_risk_config(self) -> dict:
        """Return risk management parameters."""
        return self.config.get('risk', {})

    def get_trading_config(self) -> dict:
        """Return trading execution parameters."""
        return self.config.get('trading', {})

    def update_runtime_config(self, section: str, key: str, value):
        """
        Dynamically update a config value at runtime and persist if needed.
        """
        if section not in self.config:
            raise KeyError(f"Unknown config section: {section}")
        self.config[section][key] = value

        # Optionally, write back to file
        ext = os.path.splitext(self.config_path)[1].lower()
        with open(self.config_path, 'w') as f:
            if ext in ('.yaml', '.yml'):
                yaml.safe_dump(self.config, f)
            else:
                json.dump(self.config, f, indent=2)
      
    

