"""
Theme definitions - sv_ttk handles actual widget styling.
These are only for reference or non-ttk widgets.
"""
from dataclasses import dataclass


@dataclass
class Theme:
    """Theme colors for reference - sv_ttk provides actual widget styling."""
    
    # Message bubbles (tk widgets need colors)
    bubble_self_bg: str = "#005fb8"
    bubble_self_fg: str = "#ffffff"
    bubble_other_bg: str = "#2d2d2d"
    bubble_other_fg: str = "#ffffff"
    
    # Reference colors (sv_ttk uses its own)
    accent: str = "#0078d4"
    text_primary: str = "#ffffff"
    text_secondary: str = "#cccccc"


class WinUI3Styles:
    """Spacing and sizing constants."""
    
    SPACE_4 = 4
    SPACE_8 = 8
    SPACE_12 = 12
    SPACE_16 = 16
    SPACE_24 = 24
    SPACE_32 = 32
    
    RADIUS_4 = 4
    RADIUS_6 = 6
    RADIUS_8 = 8


# Backward compatibility
ModernStyles = WinUI3Styles
