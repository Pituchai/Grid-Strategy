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
        required_sections = ['api', 'grid', 'risk', 'trading', 'performance', 'fees', 'advanced', 'logging']
        for section in required_sections:
            if section not in self.config:
                raise KeyError(f"Missing required config section: '{section}'")

        # API section should exist but keys can be empty (loaded from secrets.json)
        api = self.config['api']
        # We don't require API keys in the config file as they come from secrets.json

        # Grid config sanity
        grid = self.config['grid']
        levels = grid.get('levels', 1)
        grid_spacing_pct = grid.get('grid_spacing_pct', 0.5)  # Updated for centralized config
        
        if levels is not None and levels <= 0:
            raise ValueError("Grid 'levels' must be a positive number")
        if grid_spacing_pct is not None and grid_spacing_pct <= 0:
            raise ValueError("Grid 'grid_spacing_pct' must be a positive number")

        # Risk limits
        risk = self.config['risk']
        max_exposure = risk.get('max_exposure_pct', 50)
        if max_exposure is not None and not (0 < max_exposure <= 100):
            raise ValueError("Risk 'max_exposure_pct' must be between 0 and 100")

        # Trading parameters
        trading = self.config['trading']
        base_order_quantity = trading.get('base_order_quantity', 0.001)  # Updated for centralized config
        if base_order_quantity is not None and base_order_quantity <= 0:
            raise ValueError("Trading 'base_order_quantity' must be positive")

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
    
    def get_performance_config(self) -> dict:
        """Return performance tracking parameters."""
        return self.config.get('performance', {})
    
    def get_fees_config(self) -> dict:
        """Return fee structure and optimization parameters."""
        return self.config.get('fees', {})
    
    def get_advanced_config(self) -> dict:
        """Return advanced configuration parameters."""
        return self.config.get('advanced', {})
    
    def get_logging_config(self) -> dict:
        """Return logging and monitoring parameters."""
        return self.config.get('logging', {})

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
      
    

