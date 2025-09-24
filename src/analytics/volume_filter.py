"""
Volume filtering based on YAML configuration.
Validates market conditions before allowing trades.
"""
from datetime import datetime, timedelta


class VolumeFilter:
    """Handles volume-based trading filters from YAML configuration."""
    
    def __init__(self, config_manager, event_logger, client):
        self.cfg = config_manager
        self.logger = event_logger
        self.client = client
        
        # Load advanced configuration
        advanced_cfg = self.cfg.get_advanced_config()
        self.volume_filter_enabled = advanced_cfg.get('volume_filter', True)
        self.min_volume_24h = advanced_cfg.get('min_volume_24h', 1000000)
        
        # Cache for volume data (to avoid excessive API calls)
        self.volume_cache = {}
        self.cache_expiry = None
        self.cache_duration_minutes = 5  # Cache volume data for 5 minutes
    
    def should_allow_trading(self, symbol='BTCUSDT'):
        """
        Check if trading should be allowed based on volume filters from YAML.
        Returns (allowed: bool, reason: str, volume_data: dict)
        """
        if not self.volume_filter_enabled:
            return True, "Volume filter disabled", {}
        
        try:
            # Get 24h volume data
            volume_data = self._get_24h_volume_data(symbol)
            
            # Check minimum volume requirement
            volume_24h = volume_data.get('volume', 0)
            
            if volume_24h < self.min_volume_24h:
                reason = f"Volume ${volume_24h:,.0f} below minimum ${self.min_volume_24h:,.0f}"
                self.logger.log_signal("volume_filter_blocked", {
                    "symbol": symbol,
                    "current_volume": volume_24h,
                    "minimum_required": self.min_volume_24h,
                    "reason": reason
                })
                return False, reason, volume_data
            
            # Volume check passed
            return True, f"Volume OK: ${volume_24h:,.0f}", volume_data
            
        except Exception as e:
            self.logger.log_error("Volume filter check failed", {
                "symbol": symbol,
                "error": str(e)
            })
            # On error, allow trading (fail-safe approach)
            return True, f"Volume check failed: {str(e)}", {}
    
    def _get_24h_volume_data(self, symbol):
        """Get 24h volume data with caching to reduce API calls."""
        now = datetime.now()
        
        # Check if we have valid cached data
        if (self.cache_expiry and now < self.cache_expiry and 
            symbol in self.volume_cache):
            return self.volume_cache[symbol]
        
        try:
            # Get 24h ticker statistics
            ticker_24h = self.client.get_ticker(symbol=symbol)
            
            volume_data = {
                'symbol': symbol,
                'volume': float(ticker_24h.get('volume', 0)),
                'quote_volume': float(ticker_24h.get('quoteVolume', 0)),
                'price_change_pct': float(ticker_24h.get('priceChangePercent', 0)),
                'high_24h': float(ticker_24h.get('highPrice', 0)),
                'low_24h': float(ticker_24h.get('lowPrice', 0)),
                'timestamp': now.isoformat()
            }
            
            # Cache the data
            self.volume_cache[symbol] = volume_data
            self.cache_expiry = now + timedelta(minutes=self.cache_duration_minutes)
            
            return volume_data
            
        except Exception as e:
            # Return minimal data structure on error
            return {
                'symbol': symbol,
                'volume': 0,
                'quote_volume': 0,
                'error': str(e),
                'timestamp': now.isoformat()
            }
    
    def get_volume_status(self, symbol='BTCUSDT'):
        """Get current volume status for dashboard display."""
        if not self.volume_filter_enabled:
            return {
                'enabled': False,
                'status': 'DISABLED',
                'message': 'Volume filtering disabled in config'
            }
        
        allowed, reason, volume_data = self.should_allow_trading(symbol)
        
        return {
            'enabled': True,
            'status': 'PASS' if allowed else 'BLOCKED',
            'message': reason,
            'current_volume': volume_data.get('volume', 0),
            'minimum_required': self.min_volume_24h,
            'volume_ratio': volume_data.get('volume', 0) / self.min_volume_24h if self.min_volume_24h > 0 else 0,
            'quote_volume': volume_data.get('quote_volume', 0),
            'price_change_24h': volume_data.get('price_change_pct', 0)
        }
    
    def update_config_from_yaml(self):
        """Reload volume filter settings from YAML (for live config updates)."""
        advanced_cfg = self.cfg.get_advanced_config()
        old_enabled = self.volume_filter_enabled
        old_min_volume = self.min_volume_24h
        
        self.volume_filter_enabled = advanced_cfg.get('volume_filter', True)
        self.min_volume_24h = advanced_cfg.get('min_volume_24h', 1000000)
        
        # Log changes
        if old_enabled != self.volume_filter_enabled or old_min_volume != self.min_volume_24h:
            self.logger.log_signal("volume_filter_config_updated", {
                "volume_filter_enabled": self.volume_filter_enabled,
                "min_volume_24h": self.min_volume_24h,
                "previous_enabled": old_enabled,
                "previous_min_volume": old_min_volume
            })
    
    def get_volume_analysis(self, symbol='BTCUSDT', hours_back=24):
        """Get detailed volume analysis for the symbol."""
        try:
            volume_data = self._get_24h_volume_data(symbol)
            
            analysis = {
                'symbol': symbol,
                'period_hours': hours_back,
                'volume_btc': volume_data.get('volume', 0),
                'volume_usdt': volume_data.get('quote_volume', 0),
                'meets_minimum': volume_data.get('volume', 0) >= self.min_volume_24h,
                'volume_vs_minimum_pct': (volume_data.get('volume', 0) / self.min_volume_24h * 100) if self.min_volume_24h > 0 else 0,
                'price_volatility_24h': volume_data.get('price_change_pct', 0),
                'high_24h': volume_data.get('high_24h', 0),
                'low_24h': volume_data.get('low_24h', 0)
            }
            
            # Determine volume health
            if analysis['volume_vs_minimum_pct'] >= 200:
                analysis['volume_health'] = 'EXCELLENT'
            elif analysis['volume_vs_minimum_pct'] >= 150:
                analysis['volume_health'] = 'GOOD'
            elif analysis['volume_vs_minimum_pct'] >= 100:
                analysis['volume_health'] = 'ADEQUATE'
            elif analysis['volume_vs_minimum_pct'] >= 50:
                analysis['volume_health'] = 'LOW'
            else:
                analysis['volume_health'] = 'VERY_LOW'
            
            return analysis
            
        except Exception as e:
            return {
                'symbol': symbol,
                'error': str(e),
                'volume_health': 'UNKNOWN'
            }