"""
視圖模組
包含所有 Streamlit 頁面視圖的實作
"""

from .dcf_valuation import show_dcf_valuation
from .backtest import show_backtest
from .risk_analysis import show_risk_analysis
from .comprehensive_report import show_comprehensive_report
from .market_screener import show_market_screener
from .new_opportunities import show_new_opportunities
from .growth_optimizer import show_growth_optimizer

__all__ = [
    "show_dcf_valuation",
    "show_backtest",
    "show_risk_analysis",
    "show_comprehensive_report",
    "show_market_screener",
    "show_new_opportunities",
    "show_growth_optimizer",
]
