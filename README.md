# 🎯 Dynamic Grid Trading Strategy

**Optimal Profitable Configuration**: ±2.5% range, 0.50% spacing, 10 grids, 10% capital per grid

**Expected Performance**: 0.35% per cycle → 3.5-5.25% daily → 77-115% monthly returns

**Smart Features**: Volatility-based grid adjustment, real-time monitoring, comprehensive analytics

## 🚀 Quick Start Guide

### 1️⃣ **Setup API Keys (TESTNET/)**

Create `secrets.json` in the project root:

```json
{
  "api_key": "your_binance_api_key",
  "api_secret": "your_binance_secret_key"
}
```

💡 **For pseudo accounts**: Use the same keys for both testnet and live trading  
🔗 **For real testnet**: Get separate keys from https://testnet.binance.vision/

### 2️⃣ **Install Dependencies**

```bash
pip install pandas numpy binance-python matplotlib seaborn watchdog schedule
```

### 3️⃣ **Run Safe Testnet Demo**

```bash
cd main
python safe_testnet_demo.py
```

This will:
- ✅ Connect to Binance testnet
- ✅ Show grid configuration with your optimal settings
- ✅ Display performance projections
- ✅ Demonstrate all safety features

### 4️⃣ **Check Account Balance**

Verify your account before trading:
```bash
# Check account balance and connection
python scripts/check_balance.py
```

### 5️⃣ **Monitor Trading**

Your trading activity is automatically logged:
- **Trade events**: `logs/events.json` 
- **Performance data**: Built into the bot
- **Grid updates**: Displayed in real-time during trading

## ⚙️ **Configuration System**

### 🎯 **Centralized Configuration** (`strategy_config.yaml`)
**Edit this ONE file to control your entire trading strategy!**

- **API settings**: Testnet/live mode, base URL
- **Trading config**: Symbol (BTCUSDT), order settings, timing
- **Grid strategy**: Range (±2.5%), spacing (0.50%), levels (10)
- **Performance targets**: 0.35% per cycle, 4.375% daily
- **Risk management**: Drawdown limits, loss protection
- **Fee optimization**: Standard fee handling
- **Advanced features**: Technical indicators, monitoring
- **Logging settings**: Real-time monitoring, alerts

**Key Benefits:**
- ✅ Single source of truth for all settings
- ✅ Easy switching between testnet/live
- ✅ Built-in documentation and presets
- ✅ No API keys stored (loaded from secrets.json)

## 📊 **Optimal Strategy Configuration**

```
Trading Pair: BTCUSDT (Bitcoin/USDT)
Grid Range: ±2.5% (total 5%)
Grid Spacing: 0.50%
Number of Grids: 10
Capital per Grid: 10%
Fee Optimization: Standard rates
Expected Net Profit: 0.35% per cycle
Daily Target: 10-15 cycles
Daily Net Profit: 3.5-5.25%
Monthly Net: 77-115% (22 trading days)
```

## 🛡️ **Safety Features**

### ✅ **Comprehensive Loss Tracking**
- Individual cycle P&L monitoring
- Consecutive loss alerts (5+ cycles)
- Win rate tracking (>60% target)
- Maximum drawdown limits (15%)
- Daily loss limits (10%)

### ✅ **Risk Management**
- **Emergency stops** when limits exceeded
- **Real-time alerts** for critical events
- **Testnet protection** prevents real money loss
- **Balance monitoring** for optimal trading
- **Volatility-based grid adjustment** for market protection

### ✅ **Professional Logging**
- Multi-format logs (CSV, JSON, structured)
- Real-time monitoring and alerts
- Performance analytics and reporting
- Automated log rotation and archival

## 📁 **Project Structure**

```
DynamicGridStrategy/
├── 🎯 strategy_config.yaml       # CENTRALIZED CONFIG (edit here!)
├── 🔧 config_manager.py         # Configuration loader
├── 🎮 main/                      # Main execution scripts
│   └── safe_testnet_demo.py     # Start here!
├── 📊 src/                       # Core implementation
│   ├── analytics/               # Performance tracking
│   ├── eventlog/               # Event logging
│   ├── position/               # Position management
│   └── strategy/               # Grid trading logic
├── 🛠️ scripts/                  # Utility scripts
│   └── check_balance.py        # Account balance checker
├── 📜 logs/                     # All log files
│   ├── events.csv              # Trading events
│   ├── risk_events.json        # Risk monitoring
│   └── performance.json        # Performance metrics
└── 🔐 secrets.json             # API keys (gitignored)
```

## 🎯 **Step-by-Step Execution**

### Phase 1: Testing (MANDATORY)
1. **Setup testnet API keys**
2. **Run testnet demo** (`safe_testnet_demo.py`)
3. **Monitor for several days** on testnet
4. **Check logs** in `logs/events.json`
5. **Verify all safety features** work correctly

### Phase 2: Live Trading (Only after thorough testing)
1. **Switch to live API keys** in `secrets.json`
2. **Update config** (`testnet: false` in config)
3. **Start with small capital** (test with $100-500)
4. **Monitor closely** via console output
5. **Scale up gradually** as confidence builds

## 📈 **Performance Monitoring**

### Real-time Grid Monitoring
```bash
# Grid levels are displayed automatically when running the bot:
cd main
python safe_testnet_demo.py

# The bot shows:
# - Initial grid setup with all levels and status
# - Trade updates when orders execute  
# - Remaining ready levels after each trade
```

### Account & Balance Monitoring
```bash
# Check account balance
python scripts/check_balance.py

# Real-time log monitoring
python scripts/manage_logs.py --monitor
```

### Generate Reports
```bash
# Daily performance
python scripts/manage_logs.py --report --days 1

# Weekly analysis  
python scripts/manage_logs.py --analyze --days 7

# Create visual charts
python scripts/manage_logs.py --charts
```

### System Health
```bash
# Overall status
python scripts/manage_logs.py --status

# Recent activity
python scripts/manage_logs.py --tail 100
```

## ⚠️ **Important Safety Notes**

1. **🧪 ALWAYS test on testnet first!**
2. **💰 Start with small amounts** ($100-500)
3. **📊 Monitor performance closely** 
4. **🚨 Respect stop-loss limits** 
5. **💰 Monitor account balance** regularly
6. **📱 Set up alerts** for critical events

## 🎛️ **Management Commands**

### Account Monitoring
| Command | Purpose |
|---------|---------|
| `check_balance.py` | Account balance checker |
| `main/safe_testnet_demo.py` | Grid levels displayed during trading |

### Log Files
| File | Purpose |
|------|---------|
| `logs/events.json` | All trading events and signals |
| `logs/grid_trading.log` | Main trading log |

## 🆘 **Troubleshooting**

### Common Issues:
1. **API connection errors** → Check keys and network
2. **Insufficient balance** → Add USDT to account
3. **Permission errors** → Check file permissions
4. **Missing dependencies** → Run pip install commands

### Support:
- Check logs in `logs/events.json`
- Review console output during trading
- Check account balance with `scripts/check_balance.py`
