"""依賴注入容器模組。

提供輕量級 DI Container 實作，支援 singleton 與 transient 兩種生命週期管理。
設計決策：使用自製容器（基於 dict 註冊表）而非第三方套件，因專案規模適中，
Protocol + 簡單工廠模式已足夠。

支援循環依賴偵測：當 resolve 過程中偵測到同一介面正在解析中（表示存在循環
依賴鏈），會拋出明確的錯誤訊息。

Typical usage::

    from app.container import Container, Lifetime, setup_container

    container = setup_container()
    cache = container.resolve(CacheProtocol)
    pipeline = container.resolve(DataPipeline)

Requirements: 1.1, 1.2, 1.4
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Callable, Dict, Set, Type


class Lifetime(Enum):
    """服務生命週期列舉。

    Attributes:
        SINGLETON: 單例模式，整個容器生命週期內只建立一個實例。
        TRANSIENT: 瞬態模式，每次解析都建立新的實例。
    """

    SINGLETON = "singleton"
    TRANSIENT = "transient"


class CircularDependencyError(Exception):
    """循環依賴錯誤。

    當 resolve 過程中偵測到介面已在解析堆疊中（形成循環依賴鏈）時拋出。

    Attributes:
        interface: 觸發循環的介面型別。
        chain: 解析鏈路中涉及的所有介面型別。
    """

    def __init__(self, interface: Type, chain: list[Type]) -> None:
        """初始化循環依賴錯誤。

        Args:
            interface: 觸發循環偵測的介面型別。
            chain: 從解析起點到循環點的完整介面鏈路。
        """
        self.interface = interface
        self.chain = chain
        chain_names = " -> ".join(t.__name__ for t in chain)
        super().__init__(
            f"[FAIL] 偵測到循環依賴: {chain_names} -> {interface.__name__}"
        )


class Container:
    """輕量級依賴注入容器。

    透過介面（Protocol/ABC）註冊與解析服務，支援 singleton 與 transient
    兩種生命週期策略。提供 override 機制供測試時替換為 mock 物件。
    內建循環依賴偵測，當工廠函式觸發解析已在堆疊中的介面時拋出明確錯誤。

    Attributes:
        _registry: 介面到 (工廠函式, 生命週期) 的映射表。
        _singletons: 已建立的 singleton 實例快取。
        _resolving: 目前正在解析中的介面集合（用於偵測循環依賴）。
        _resolve_chain: 目前解析鏈路（用於錯誤訊息）。
    """

    def __init__(self) -> None:
        """初始化空的 DI 容器。"""
        self._registry: Dict[Type, tuple[Callable[..., Any], Lifetime]] = {}
        self._singletons: Dict[Type, Any] = {}
        self._resolving: Set[Type] = set()
        self._resolve_chain: list[Type] = []

    def register(
        self,
        interface: Type,
        factory: Callable[..., Any],
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None:
        """註冊服務至容器。

        Args:
            interface: 服務的抽象介面型別（通常為 Protocol 或 ABC）。
            factory: 建立服務實例的工廠函式（無參數呼叫）。
            lifetime: 服務生命週期，預設為 SINGLETON。

        Raises:
            TypeError: 當 interface 不是型別或 factory 不可呼叫時。
        """
        if not isinstance(interface, type):
            raise TypeError(
                f"interface 必須為型別，收到: {type(interface).__name__}"
            )
        if not callable(factory):
            raise TypeError(
                f"factory 必須為可呼叫物件，收到: {type(factory).__name__}"
            )
        self._registry[interface] = (factory, lifetime)

    def resolve(self, interface: Type) -> Any:
        """解析服務實例。

        根據註冊的生命週期策略回傳對應的服務實例：
        - SINGLETON：首次呼叫時建立實例並快取，後續呼叫回傳同一實例（is identity）。
        - TRANSIENT：每次呼叫都建立新實例。

        內建循環依賴偵測：若工廠函式執行過程中再次 resolve 已在解析堆疊中的介面，
        會拋出 CircularDependencyError。

        Args:
            interface: 要解析的服務介面型別。

        Returns:
            該介面對應的服務實例。

        Raises:
            KeyError: 當指定介面尚未註冊時。
            CircularDependencyError: 當偵測到循環依賴時。
        """
        if interface not in self._registry:
            raise KeyError(f"Service not registered: {interface}")

        # 若已有 singleton 快取（含 override 設定），直接回傳
        if interface in self._singletons:
            return self._singletons[interface]

        # 循環依賴偵測
        if interface in self._resolving:
            raise CircularDependencyError(
                interface=interface,
                chain=list(self._resolve_chain),
            )

        factory, lifetime = self._registry[interface]

        # 進入解析堆疊
        self._resolving.add(interface)
        self._resolve_chain.append(interface)
        try:
            instance = factory()
        finally:
            # 無論成功或失敗，都要離開解析堆疊
            self._resolving.discard(interface)
            self._resolve_chain.pop()

        if lifetime == Lifetime.SINGLETON:
            self._singletons[interface] = instance

        return instance

    def override(self, interface: Type, instance: Any) -> None:
        """覆寫服務實例（測試專用）。

        將指定介面直接綁定至提供的實例，後續 resolve 將回傳此實例，
        忽略原本註冊的工廠函式。常用於測試時注入 mock 物件。

        Args:
            interface: 要覆寫的服務介面型別。
            instance: 用於替換的實例（通常為 mock 物件）。
        """
        self._singletons[interface] = instance

    def reset(self) -> None:
        """清除所有 singleton 快取。

        保留註冊表不變，僅清除已建立的 singleton 實例。
        下次 resolve 時會重新呼叫工廠函式建立新實例。
        常用於測試之間的狀態隔離。
        """
        self._singletons.clear()

    def is_registered(self, interface: Type) -> bool:
        """檢查指定介面是否已註冊。

        Args:
            interface: 要檢查的服務介面型別。

        Returns:
            True 表示已註冊，False 表示尚未註冊。
        """
        return interface in self._registry


def setup_container() -> Container:
    """建立並回傳已配置的 DI 容器，註冊所有服務。

    依據環境變數配置服務實例，包含：
    - 快取層（MemoryCache、SQLiteCache）
    - 韌性元件（CircuitBreaker x3、RateLimiter、BatchDownloader）
    - 資料來源（YFinanceSource、FinMindSource、FinLabSource）
    - 資料管線（DataPipeline）
    - 應用服務（DCFCalculator、MarketScannerService、ChipAnalyzer、
      LLMAnalyzer、TradeSignalEngine、PaperTrader）

    環境變數：
        DATABASE_PATH: SQLite 資料庫路徑，預設 "app/data/market_scan.db"。
        FINMIND_TOKEN: FinMind API token。
        FINLAB_API_TOKEN: FinLab API token。
        LLM_BACKEND: LLM 後端選擇（"openai" / "anthropic" / None）。
        OPENAI_API_KEY: OpenAI API 金鑰（LLM_BACKEND=openai 時需要）。

    Returns:
        已完成所有服務註冊的 Container 實例。
    """
    from app.infra.cache.memory_cache import MemoryCache
    from app.infra.cache.sqlite_cache import SQLiteCache
    from app.infra.data_pipeline import DataPipeline
    from app.infra.error_handler import ErrorHandler
    from app.infra.resilience.batch_downloader import BatchDownloader
    from app.infra.resilience.circuit_breaker import CircuitBreaker
    from app.infra.resilience.rate_limiter import FinMindRateLimiter
    from app.infra.sources.finlab_source import FinLabSource
    from app.infra.sources.finmind_source import FinMindSource
    from app.infra.sources.yfinance_source import YFinanceSource
    from app.services.chip_analyzer import ChipAnalyzer
    from app.services.dcf_calculator import DCFCalculator
    from app.services.llm_analyzer import LLMAnalyzer
    from app.services.market_scanner import MarketScannerService
    from app.services.trade_engine import PaperTrader, TradeSignalEngine

    container = Container()

    # ------------------------------------------------------------------
    # 1. 快取層
    # ------------------------------------------------------------------

    container.register(
        MemoryCache,
        lambda: MemoryCache(max_size=200),
        Lifetime.SINGLETON,
    )

    db_path = os.environ.get("DATABASE_PATH", "app/data/market_scan.db")
    container.register(
        SQLiteCache,
        lambda: SQLiteCache(db_path=db_path),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 2. 韌性元件 - Circuit Breakers（每個外部來源各一）
    # ------------------------------------------------------------------

    # 以字串鍵搭配具名 class 作為介面，避免三者共用同一型別衝突。
    # 使用 type() 動態建立標記型別作為註冊鍵。
    _YahooCB = type("_YahooCB", (), {})
    _FinMindCB = type("_FinMindCB", (), {})
    _FinLabCB = type("_FinLabCB", (), {})

    container.register(
        _YahooCB,
        lambda: CircuitBreaker(source_name="yahoo_finance"),
        Lifetime.SINGLETON,
    )
    container.register(
        _FinMindCB,
        lambda: CircuitBreaker(source_name="finmind"),
        Lifetime.SINGLETON,
    )
    container.register(
        _FinLabCB,
        lambda: CircuitBreaker(source_name="finlab"),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 3. Rate Limiter（FinMind 專用）
    # ------------------------------------------------------------------

    container.register(
        FinMindRateLimiter,
        lambda: FinMindRateLimiter(
            max_tokens=10,
            refill_rate=2.0,
            circuit_breaker=container.resolve(_FinMindCB),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 4. Batch Downloader
    # ------------------------------------------------------------------

    container.register(
        BatchDownloader,
        lambda: BatchDownloader(
            batch_size=50,
            max_workers=5,
            batch_delay=1.0,
            timeout_seconds=30.0,
            max_consecutive_failures=3,
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 5. Error Handler
    # ------------------------------------------------------------------

    container.register(
        ErrorHandler,
        lambda: ErrorHandler(),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 6. 資料來源
    # ------------------------------------------------------------------

    container.register(
        YFinanceSource,
        lambda: YFinanceSource(
            circuit_breaker=container.resolve(_YahooCB),
        ),
        Lifetime.SINGLETON,
    )

    finmind_token = os.environ.get("FINMIND_TOKEN", "")
    container.register(
        FinMindSource,
        lambda: FinMindSource(
            token=finmind_token,
            rate_limiter=container.resolve(FinMindRateLimiter),
            circuit_breaker=container.resolve(_FinMindCB),
        ),
        Lifetime.SINGLETON,
    )

    finlab_token = os.environ.get("FINLAB_API_TOKEN", "")
    container.register(
        FinLabSource,
        lambda: FinLabSource(
            token=finlab_token,
            circuit_breaker=container.resolve(_FinLabCB),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 7. Data Pipeline
    # ------------------------------------------------------------------

    container.register(
        DataPipeline,
        lambda: DataPipeline(
            sources=[
                container.resolve(FinLabSource),
                container.resolve(YFinanceSource),
                container.resolve(FinMindSource),
            ],
            memory_cache=container.resolve(MemoryCache),
            sqlite_cache=container.resolve(SQLiteCache),
            error_handler=container.resolve(ErrorHandler),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 8. 應用服務 - DCF Calculator
    # ------------------------------------------------------------------

    container.register(
        DCFCalculator,
        lambda: DCFCalculator(
            data_pipeline=container.resolve(DataPipeline),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 9. 應用服務 - Market Scanner
    # ------------------------------------------------------------------

    container.register(
        MarketScannerService,
        lambda: MarketScannerService(
            data_pipeline=container.resolve(DataPipeline),
            batch_downloader=container.resolve(BatchDownloader),
            sqlite_cache=container.resolve(SQLiteCache),
            error_handler=container.resolve(ErrorHandler),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 10. 應用服務 - Chip Analyzer
    # ------------------------------------------------------------------

    container.register(
        ChipAnalyzer,
        lambda: ChipAnalyzer(
            data_pipeline=container.resolve(DataPipeline),
            sqlite_cache=container.resolve(SQLiteCache),
            error_handler=container.resolve(ErrorHandler),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 11. 應用服務 - LLM Analyzer（依環境變數切換後端）
    # ------------------------------------------------------------------

    def _create_llm_analyzer() -> LLMAnalyzer:
        """依據 LLM_BACKEND 環境變數建立 LLMAnalyzer 實例。"""
        llm_backend_name = os.environ.get("LLM_BACKEND")
        llm_backend = None

        if llm_backend_name == "openai":
            try:
                from app.services.llm_backends.openai_backend import (
                    OpenAIBackend,
                )

                api_key = os.environ.get("OPENAI_API_KEY", "")
                llm_backend = OpenAIBackend(api_key=api_key)
            except ImportError:
                pass
        elif llm_backend_name == "anthropic":
            try:
                from app.services.llm_backends.anthropic_backend import (
                    AnthropicBackend,
                )

                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
                llm_backend = AnthropicBackend(api_key=api_key)
            except ImportError:
                pass

        return LLMAnalyzer(
            llm_backend=llm_backend,
            data_pipeline=container.resolve(DataPipeline),
        )

    container.register(
        LLMAnalyzer,
        _create_llm_analyzer,
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 12. 應用服務 - Trade Signal Engine
    # ------------------------------------------------------------------

    container.register(
        TradeSignalEngine,
        lambda: TradeSignalEngine(
            sqlite_cache=container.resolve(SQLiteCache),
        ),
        Lifetime.SINGLETON,
    )

    # ------------------------------------------------------------------
    # 13. 應用服務 - Paper Trader
    # ------------------------------------------------------------------

    container.register(
        PaperTrader,
        lambda: PaperTrader(
            sqlite_cache=container.resolve(SQLiteCache),
        ),
        Lifetime.SINGLETON,
    )

    return container
