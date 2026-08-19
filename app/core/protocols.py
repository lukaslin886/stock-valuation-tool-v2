"""Protocol 介面定義模組。

定義系統中所有核心抽象介面，供依賴注入與模組解耦使用。
所有介面使用 typing.Protocol 實作，支援結構化子型別（structural subtyping）。

Protocols:
    - DataSourceProtocol: 資料來源抽象介面
    - CacheProtocol: 快取層抽象介面
    - CircuitBreakerProtocol: 斷路器抽象介面
    - LLMBackendProtocol: LLM 後端抽象介面
    - BrokerAdapterProtocol: 券商 API 抽象介面
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class DataSourceProtocol(Protocol):
    """資料來源抽象介面。

    定義外部資料來源（Yahoo Finance、FinMind、FinLab 等）的統一存取合約。
    所有資料來源實作必須遵循此介面，以支援透過 DI Container 的替換與測試。

    Properties:
        source_name: 資料來源名稱標識符
        is_available: 資料來源目前是否可用

    Methods:
        is_ready: 檢查資料來源是否已就緒可供查詢
        get_stock_price: 取得指定期間的股價資料
        get_financial_data: 取得指定年數的財報資料
        get_stock_info: 取得股票基本資訊
    """

    @property
    def source_name(self) -> str:
        """資料來源名稱。

        Returns:
            資料來源的唯一標識符字串，例如 "yahoo_finance"、"finmind"、"finlab"。
        """
        ...

    @property
    def is_available(self) -> bool:
        """資料來源目前是否可用。

        用於快速判斷該來源是否處於可服務狀態（例如斷路器未開啟、API 金鑰有效）。

        Returns:
            True 表示來源可用，False 表示暫時不可用。
        """
        ...

    def is_ready(self) -> bool:
        """檢查資料來源是否已就緒可供查詢。

        與 is_available 不同，此方法可執行更深入的健康檢查
        （例如測試網路連線、驗證 API 金鑰有效性）。

        Returns:
            True 表示已就緒可供查詢，False 表示尚未就緒。
        """
        ...

    def get_stock_price(
        self, stock_code: str, start_date: datetime, end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """取得指定期間的股價資料。

        Args:
            stock_code: 股票代碼（例如 "2330"、"AAPL"）。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            包含 OHLCV 欄位的 DataFrame，若查詢失敗則回傳 None。
            DataFrame 欄位應包含：date, open, high, low, close, volume。

        Raises:
            DataSourceError: 當資料來源發生不可恢復的錯誤時。
        """
        ...

    def get_financial_data(
        self, stock_code: str, years: int = 5
    ) -> Optional[pd.DataFrame]:
        """取得指定年數的財報資料。

        Args:
            stock_code: 股票代碼。
            years: 回溯年數，預設為 5 年。

        Returns:
            包含財報欄位的 DataFrame，若查詢失敗則回傳 None。
            DataFrame 欄位應包含：period, revenue, eps, roe, pe_ratio 等。

        Raises:
            DataSourceError: 當資料來源發生不可恢復的錯誤時。
        """
        ...

    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """取得股票基本資訊。

        Args:
            stock_code: 股票代碼。

        Returns:
            包含公司基本資訊的字典，若查詢失敗則回傳 None。
            字典應包含：stock_name, industry, market, shares_outstanding 等。

        Raises:
            DataSourceError: 當資料來源發生不可恢復的錯誤時。
        """
        ...


@runtime_checkable
class CacheProtocol(Protocol):
    """快取層抽象介面。

    定義快取操作的統一合約，支援記憶體快取與持久化快取的實作。
    所有快取實作必須遵循此介面以支援透過 DI Container 的替換。

    Methods:
        get: 依鍵值取得快取條目
        set: 設定快取條目（可指定 TTL）
        delete: 刪除指定鍵值的快取條目
        invalidate_prefix: 批次失效具有特定前綴的條目
        stats: 取得快取統計資訊
    """

    def get(self, key: str) -> Optional[Any]:
        """依鍵值取得快取條目。

        Args:
            key: 快取鍵值字串。

        Returns:
            快取的值（淺複製），若鍵值不存在或已過期則回傳 None。
        """
        ...

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """設定快取條目。

        Args:
            key: 快取鍵值字串。
            value: 要快取的值。
            ttl: 存活時間（秒）。若為 None 則使用預設 TTL。
        """
        ...

    def delete(self, key: str) -> None:
        """刪除指定鍵值的快取條目。

        Args:
            key: 要刪除的快取鍵值字串。
        """
        ...

    def invalidate_prefix(self, prefix: str) -> int:
        """批次失效具有特定前綴的所有快取條目。

        用於清除特定股票代碼相關的所有快取，例如
        ``invalidate_prefix("2330:")`` 會刪除所有以 "2330:" 開頭的條目。

        Args:
            prefix: 鍵值前綴字串。

        Returns:
            被刪除的條目數量。
        """
        ...

    def stats(self) -> Dict[str, int]:
        """取得快取統計資訊。

        Returns:
            包含統計數據的字典，至少包含：
            - hit_count: 快取命中次數
            - miss_count: 快取未命中次數
            - eviction_count: 因容量限制被驅逐的次數
        """
        ...


@runtime_checkable
class CircuitBreakerProtocol(Protocol):
    """斷路器抽象介面。

    實作斷路器模式，保護系統免受外部服務連續失敗的影響。
    狀態機：closed -> open（連續失敗達閾值）-> half_open（冷卻後）-> closed（探測成功）。

    Properties:
        state: 目前斷路器狀態

    Methods:
        record_success: 記錄一次成功的請求
        record_failure: 記錄一次失敗的請求
        allow_request: 判斷目前是否允許發送請求
        reset: 重置斷路器至初始關閉狀態
    """

    @property
    def state(self) -> str:
        """目前斷路器狀態。

        Returns:
            狀態字串，為以下三者之一：
            - "closed": 正常運作，允許所有請求
            - "open": 斷路器開啟，拒絕所有請求
            - "half_open": 半開狀態，允許一次探測性請求
        """
        ...

    def record_success(self) -> None:
        """記錄一次成功的請求。

        在 half_open 狀態下記錄成功會將斷路器重置為 closed 狀態。
        在 closed 狀態下記錄成功會重置失敗計數器。
        """
        ...

    def record_failure(self) -> None:
        """記錄一次失敗的請求。

        在 closed 狀態下，若 60 秒內累計失敗達 5 次，將轉為 open 狀態。
        在 half_open 狀態下記錄失敗會立即回到 open 狀態。
        """
        ...

    def allow_request(self) -> bool:
        """判斷目前是否允許發送請求。

        Returns:
            True 表示允許發送請求，False 表示應跳過該來源。
        """
        ...

    def reset(self) -> None:
        """重置斷路器至初始關閉狀態。

        清除所有失敗記錄與計時器，恢復為 closed 狀態。
        """
        ...


@runtime_checkable
class LLMBackendProtocol(Protocol):
    """LLM 後端抽象介面。

    定義大型語言模型後端的統一呼叫合約。
    支援透過 DI Container 注入不同的 LLM 提供者（OpenAI、Anthropic、本地模型等）。

    Methods:
        generate: 依據提示詞產生文字回應
    """

    def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        """依據提示詞產生文字回應。

        Args:
            prompt: 輸入提示詞文字。
            max_tokens: 回應的最大 token 數量，預設為 2000。

        Returns:
            LLM 產生的文字回應。

        Raises:
            TimeoutError: 當 API 呼叫逾時（超過 30 秒）時。
            DataSourceError: 當 LLM API 發生不可恢復的錯誤時。
        """
        ...


@runtime_checkable
class BrokerAdapterProtocol(Protocol):
    """券商 API 抽象介面。

    定義券商交易系統的統一操作合約。
    本介面為未來整合實際券商 API 預留擴充點，
    目前可搭配 Paper Trading 模式使用。

    Methods:
        query_balance: 查詢帳戶餘額
        place_order: 下單委託
        cancel_order: 取消委託
    """

    def query_balance(self) -> Dict[str, float]:
        """查詢帳戶餘額。

        Returns:
            包含帳戶餘額資訊的字典，至少包含：
            - available_cash: 可用現金
            - total_market_value: 持股總市值
            - total_assets: 總資產
        """
        ...

    def place_order(
        self, stock_code: str, action: str, quantity: int, price: float
    ) -> Dict[str, Any]:
        """下單委託。

        Args:
            stock_code: 股票代碼。
            action: 交易方向，"buy" 或 "sell"。
            quantity: 委託股數。
            price: 委託價格。

        Returns:
            包含委託結果的字典，至少包含：
            - order_id: 委託單號
            - status: 委託狀態（"submitted", "filled", "rejected"）
            - message: 狀態說明訊息

        Raises:
            ValidationError: 當委託參數不合法時（例如數量為負、價格為零）。
        """
        ...

    def cancel_order(self, order_id: str) -> bool:
        """取消委託。

        Args:
            order_id: 要取消的委託單號。

        Returns:
            True 表示取消成功，False 表示取消失敗（例如委託已成交）。
        """
        ...
