# inject_key.py

import json
from config_manager import ConfigManager

# Read secret keys from JSON
with open("secrets.json") as f:
    secrets = json.load(f)

# Load your config.yaml with ConfigManager
cfg = ConfigManager("config.yaml")

# Update the keys in your YAML
cfg.update_runtime_config("api", "api_key", secrets["api_key"])
cfg.update_runtime_config("api", "api_secret", secrets["api_secret"])

print("✓ API keys updated in config.yaml")