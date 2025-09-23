#!/usr/bin/env python3
"""
Quick Setup Script for Dynamic Grid Trading Strategy
"""

import os
import json
import subprocess
import sys

def install_dependencies():
    """Install required Python packages."""
    print("📦 Installing dependencies...")
    
    packages = [
        "pandas", "numpy", "python-binance", "matplotlib", 
        "seaborn", "watchdog", "schedule"
    ]
    
    for package in packages:
        try:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        except subprocess.CalledProcessError:
            print(f"❌ Failed to install {package}")
            return False
    
    print("✅ All dependencies installed successfully!")
    return True

def create_secrets_template():
    """Create secrets.json template."""
    secrets_path = "secrets.json"
    
    if os.path.exists(secrets_path):
        print("📄 secrets.json already exists")
        return True
    
    template = {
        "api_key": "your_binance_api_key_here",
        "api_secret": "your_binance_secret_key_here"
    }
    
    try:
        with open(secrets_path, 'w') as f:
            json.dump(template, f, indent=2)
        
        print(f"📄 Created {secrets_path} template")
        print("🔑 Please add your Binance API keys!")
        print("💡 Since you're using a pseudo account, use the same keys for both testnet and live")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create secrets.json: {e}")
        return False

def create_directories():
    """Create necessary directories."""
    directories = ["logs", "charts", "config", "examples", "scripts"]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"📁 Directory ready: {directory}")
    
    return True

def verify_setup():
    """Verify the setup is complete."""
    print("\n🔍 Verifying setup...")
    
    checks = []
    
    # Check Python version
    if sys.version_info >= (3, 7):
        checks.append("✅ Python version OK")
    else:
        checks.append("❌ Python 3.7+ required")
    
    # Check key files exist
    key_files = [
        "strategy_config.yaml",
        "main/safe_testnet_demo.py", 
        "scripts/check_balance.py"
    ]
    
    for file_path in key_files:
        if os.path.exists(file_path):
            checks.append(f"✅ {file_path}")
        else:
            checks.append(f"❌ Missing: {file_path}")
    
    # Check secrets.json
    if os.path.exists("secrets.json"):
        try:
            with open("secrets.json", 'r') as f:
                secrets = json.load(f)
            
            if secrets.get("api_key", "").startswith("your_"):
                checks.append("⚠️  secrets.json needs your API keys")
            else:
                checks.append("✅ secrets.json configured")
                
        except:
            checks.append("❌ secrets.json invalid")
    else:
        checks.append("❌ secrets.json missing")
    
    for check in checks:
        print(check)
    
    return all("✅" in check for check in checks)

def main():
    """Main setup function."""
    print("🎯 Dynamic Grid Trading Strategy Setup")
    print("=" * 50)
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Setup failed - dependency installation error")
        return
    
    print()
    
    # Create directories
    if not create_directories():
        print("❌ Setup failed - directory creation error")
        return
    
    print()
    
    # Create secrets template
    if not create_secrets_template():
        print("❌ Setup failed - secrets template error")
        return
    
    print()
    
    # Verify setup
    setup_ok = verify_setup()
    
    print("\n" + "=" * 50)
    
    if setup_ok:
        print("🎉 Setup completed successfully!")
        print("\n🚀 Next steps:")
        print("1. Add your testnet API keys to secrets.json")
        print("2. cd examples && python safe_testnet_demo.py")
    else:
        print("⚠️  Setup completed with warnings")
        print("Please check the issues above and fix them")
    
    print("\n📚 Full instructions in README.md")

if __name__ == "__main__":
    main()