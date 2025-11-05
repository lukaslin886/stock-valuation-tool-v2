"""
風險模型模組

提供各種風險分析工具：
- 滑動風險 (Slippage Risk)
- VaR 風險值
- 其他風險指標
"""

from .slippage_model import SlippageModel

__all__ = ['SlippageModel']
