"""外部資料來源適配器模組。

提供台股估值工具所使用的外部資料來源實作，包含：
- BaseDataSource: 資料來源基礎抽象類別
- FinMindSource: FinMind API 資料來源（含速率限制與斷路器）
- FinLabSource: FinLab API 資料來源（含斷路器）

所有資料來源皆實作 DataSourceProtocol 介面，可透過 DI Container 互換。
"""

from app.infra.sources.base import BaseDataSource
from app.infra.sources.finlab_source import FinLabSource
from app.infra.sources.finmind_source import FinMindSource

__all__ = [
    "BaseDataSource",
    "FinLabSource",
    "FinMindSource",
]
