"""
Grid generation and management utilities.
Extracted from GridStrategyController for better organization.
"""
from datetime import datetime


class GridGenerator:
    """Handles grid level generation and management."""
    
    def __init__(self, config_manager, event_logger):
        self.cfg = config_manager
        self.logger = event_logger
        
    def generate_grid_levels(self, current_price, volatility_adjusted_spacing=None):
        """
        Generate grid levels for dashboard display.
        """
        grid_cfg = self.cfg.get_grid_config()
        base_spacing_pct = grid_cfg.get('grid_spacing_pct', 0.5) / 100
        levels = grid_cfg.get('levels', 10)
        
        # Use volatility adjusted spacing if provided
        spacing_pct = volatility_adjusted_spacing or base_spacing_pct
        
        grid_levels = []
        
        # Generate buy levels (below current price)
        for i in range(1, (levels // 2) + 1):
            buy_price = current_price * (1 - (spacing_pct * i))
            grid_levels.append({
                'price': buy_price,
                'side': 'BUY',
                'level': -i,
                'status': 'pending'
            })
        
        # Generate sell levels (above current price)
        for i in range(1, (levels // 2) + 1):
            sell_price = current_price * (1 + (spacing_pct * i))
            grid_levels.append({
                'price': sell_price,
                'side': 'SELL', 
                'level': i,
                'status': 'pending'
            })
        
        # Sort by price (lowest to highest)
        grid_levels.sort(key=lambda x: x['price'])
        
        self.logger.log_signal("grid_generated", {
            "center_price": current_price,
            "total_levels": len(grid_levels),
            "price_range": f"{grid_levels[0]['price']:.2f} - {grid_levels[-1]['price']:.2f}",
            "spacing_pct": spacing_pct * 100
        })
        
        return grid_levels
    
    def define_parameters(self, df_ind, volatility_manager=None):
        """
        Define base grid parameters based on current market price with volatility adjustments.
        """
        current_price = df_ind['close'].iloc[-1]
        grid_cfg = self.cfg.get_grid_config()
        
        # Base parameters from config
        base_grid_range_pct = grid_cfg.get('grid_range_pct', 2.5) / 100
        base_grid_spacing_pct = grid_cfg.get('grid_spacing_pct', 0.5) / 100
        levels = grid_cfg.get('levels', 10)
        base_capital_per_grid = grid_cfg.get('capital_per_grid_pct', 10.0)
        
        # Get volatility-adjusted parameters if volatility manager is provided
        if volatility_manager:
            vol_params = volatility_manager.get_adjusted_grid_params(
                base_grid_spacing_pct * 100,  # Convert back to percentage
                base_capital_per_grid,
                df_ind
            )
            
            # Apply volatility adjustments
            grid_spacing_pct = vol_params['adjusted_spacing_pct'] / 100  # Convert to decimal
            adjusted_capital_per_grid = vol_params['adjusted_position_size']
            
            print(f"📊 Volatility Analysis:")
            print(f"   Regime: {volatility_manager.get_regime_description(vol_params['regime'])}")
            print(f"   Volatility Ratio: {vol_params['volatility_ratio']:.4f}")
            print(f"   Spacing Adjustment: {base_grid_spacing_pct*100:.2f}% → {vol_params['adjusted_spacing_pct']:.2f}%")
            print(f"   Position Adjustment: {base_capital_per_grid:.1f}% → {adjusted_capital_per_grid:.1f}%")
        else:
            grid_spacing_pct = base_grid_spacing_pct
            adjusted_capital_per_grid = base_capital_per_grid
        
        grid_range_pct = base_grid_range_pct
        
        # Calculate grid boundaries
        upper_bound = current_price * (1 + grid_range_pct)
        lower_bound = current_price * (1 - grid_range_pct)
        
        return {
            'center_price': current_price,
            'upper_bound': upper_bound,
            'lower_bound': lower_bound,
            'grid_spacing_pct': grid_spacing_pct,
            'levels': levels,
            'range_pct': grid_range_pct,
            'adjusted_capital_per_grid': adjusted_capital_per_grid
        }