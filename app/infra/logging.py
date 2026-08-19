"""結構化日誌系統模組。

提供 JSON 格式結構化日誌、檔案輪替、環境切換支援。
支援開發環境（DEBUG + console + file）與生產環境（INFO + file only）。

環境變數：
    STOCK_TOOL_ENV: development 或 production（預設 development）
    LOG_LEVEL: DEBUG / INFO / WARNING / ERROR（覆寫環境預設值）

Usage::

    from app.infra.logging import get_logger, get_stock_logger

    logger = get_logger(__name__)
    logger.info("應用程式啟動")

    stock_logger = get_stock_logger(__name__, "2330")
    stock_logger.info("取得股價資料成功")
"""

import json
import logging
import logging.handlers
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

_DEFAULT_LOG_DIR = "logs"
_DEFAULT_LOG_FILE = "stock_tool.log"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5
_ENV_VAR_NAME = "STOCK_TOOL_ENV"
_LOG_LEVEL_VAR = "LOG_LEVEL"

_ENV_DEVELOPMENT = "development"
_ENV_PRODUCTION = "production"

# 模組層級鎖，確保 handler 配置的執行緒安全
_config_lock = threading.Lock()
_configured_loggers: Dict[str, logging.Logger] = {}


# ---------------------------------------------------------------------------
# StructuredFormatter
# ---------------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    """結構化 JSON 日誌格式化器。

    將 LogRecord 轉為 JSON 字串，包含固定欄位：
    timestamp、level、module、function、message、stock_code、source。
    若 LogRecord 帶有例外資訊，則附加 exception 欄位。

    Attributes:
        None（無額外公開屬性）
    """

    def format(self, record: logging.LogRecord) -> str:
        """格式化日誌記錄為 JSON 字串。

        Args:
            record: Python logging 的 LogRecord 物件。

        Returns:
            JSON 格式的日誌字串（ensure_ascii=False 以支援中文）。
        """
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
            "stock_code": getattr(record, "stock_code", None),
            "source": getattr(record, "source", None),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


# ---------------------------------------------------------------------------
# StockLoggerAdapter
# ---------------------------------------------------------------------------


class StockLoggerAdapter(logging.LoggerAdapter):
    """帶有股票代碼上下文的 LoggerAdapter。

    自動將 stock_code 注入每條日誌記錄的 extra 欄位，
    使 StructuredFormatter 可將其序列化至 JSON。

    Attributes:
        extra: 包含 stock_code 與 source 的字典。
    """

    def __init__(
        self,
        logger: logging.Logger,
        stock_code: str,
        source: Optional[str] = None,
    ) -> None:
        """初始化 StockLoggerAdapter。

        Args:
            logger: 底層 Logger 實例。
            stock_code: 股票代碼（如 "2330"、"AAPL"）。
            source: 資料來源名稱（如 "yahoo_finance"），可選。
        """
        extra: Dict[str, Any] = {
            "stock_code": stock_code,
            "source": source,
        }
        super().__init__(logger, extra)

    def process(
        self, msg: str, kwargs: Any
    ) -> tuple:
        """將 extra 上下文注入 kwargs。

        Args:
            msg: 日誌訊息。
            kwargs: 傳遞給 Logger 方法的關鍵字引數。

        Returns:
            包含原始訊息與更新後 kwargs 的 tuple。
        """
        # 確保 extra 字典存在，並合併 adapter 層級的上下文
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


# ---------------------------------------------------------------------------
# 內部輔助函式
# ---------------------------------------------------------------------------


def _get_environment() -> str:
    """取得目前執行環境。

    Returns:
        "development" 或 "production"。
    """
    env = os.environ.get(_ENV_VAR_NAME, _ENV_DEVELOPMENT).lower().strip()
    if env in (_ENV_DEVELOPMENT, _ENV_PRODUCTION):
        return env
    return _ENV_DEVELOPMENT


def _get_log_level() -> int:
    """依環境與環境變數決定日誌等級。

    優先使用 LOG_LEVEL 環境變數；若未設定，
    開發環境預設 DEBUG、生產環境預設 INFO。

    Returns:
        logging 模組的等級常數（如 logging.DEBUG）。
    """
    explicit_level = os.environ.get(_LOG_LEVEL_VAR, "").upper().strip()
    if explicit_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return getattr(logging, explicit_level)

    env = _get_environment()
    if env == _ENV_PRODUCTION:
        return logging.INFO
    return logging.DEBUG


def _ensure_log_directory() -> Path:
    """確保日誌目錄存在，不存在時自動建立。

    Returns:
        日誌目錄的 Path 物件。
    """
    log_dir = Path(_DEFAULT_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _create_file_handler() -> logging.handlers.RotatingFileHandler:
    """建立具有輪替功能的檔案 handler。

    配置：
    - 每檔 10 MB
    - 保留 5 個歷史檔
    - UTF-8 編碼
    - 使用 StructuredFormatter

    Returns:
        已配置好的 RotatingFileHandler 實例。
    """
    log_dir = _ensure_log_directory()
    log_path = log_dir / _DEFAULT_LOG_FILE

    handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(StructuredFormatter())
    return handler


def _create_console_handler() -> logging.StreamHandler:
    """建立 console handler（僅開發環境使用）。

    使用 StructuredFormatter 保持輸出一致性。

    Returns:
        已配置好的 StreamHandler 實例。
    """
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    return handler


def _configure_logger(name: str) -> logging.Logger:
    """配置指定名稱的 logger。

    根據環境自動配置：
    - 開發環境：DEBUG，console + file
    - 生產環境：INFO，file only

    此函式為執行緒安全（透過 _config_lock）。

    Args:
        name: Logger 名稱（通常為模組名 __name__）。

    Returns:
        已配置好的 Logger 實例。
    """
    with _config_lock:
        # 若已配置過，直接回傳
        if name in _configured_loggers:
            return _configured_loggers[name]

        logger = logging.getLogger(name)
        log_level = _get_log_level()
        logger.setLevel(log_level)

        # 避免重複新增 handler（例如模組被 reload 時）
        if not logger.handlers:
            env = _get_environment()

            # 檔案 handler（開發、生產皆有）
            file_handler = _create_file_handler()
            file_handler.setLevel(log_level)
            logger.addHandler(file_handler)

            # Console handler（僅開發環境）
            if env == _ENV_DEVELOPMENT:
                console_handler = _create_console_handler()
                console_handler.setLevel(log_level)
                logger.addHandler(console_handler)

        # 防止日誌向上傳播至 root logger 造成重複輸出
        logger.propagate = False

        _configured_loggers[name] = logger
        return logger


# ---------------------------------------------------------------------------
# 公開工廠函式
# ---------------------------------------------------------------------------


def get_logger(module_name: str) -> logging.Logger:
    """取得已配置的結構化 Logger 實例。

    Args:
        module_name: 模組名稱，建議傳入 ``__name__``。

    Returns:
        已配置好的 Logger 實例，支援 StructuredFormatter 格式化輸出。

    Example::

        from app.infra.logging import get_logger

        logger = get_logger(__name__)
        logger.info("處理完成", extra={"stock_code": "2330"})
    """
    return _configure_logger(module_name)


def get_stock_logger(
    module_name: str,
    stock_code: str,
    source: Optional[str] = None,
) -> StockLoggerAdapter:
    """取得帶有股票代碼上下文的 LoggerAdapter。

    每條日誌自動帶入 stock_code 與 source 欄位，
    無需在每次呼叫時手動傳入 extra。

    Args:
        module_name: 模組名稱，建議傳入 ``__name__``。
        stock_code: 股票代碼（如 "2330"、"AAPL"）。
        source: 資料來源名稱（如 "yahoo_finance"），可選。

    Returns:
        StockLoggerAdapter 實例。

    Example::

        from app.infra.logging import get_stock_logger

        logger = get_stock_logger(__name__, "2330", source="finmind")
        logger.info("取得籌碼資料成功")
        # JSON 輸出自動包含 "stock_code": "2330", "source": "finmind"
    """
    logger = _configure_logger(module_name)
    return StockLoggerAdapter(logger, stock_code=stock_code, source=source)
