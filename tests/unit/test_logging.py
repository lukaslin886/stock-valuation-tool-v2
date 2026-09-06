"""結構化日誌系統單元測試。

驗證 StructuredFormatter、get_logger、get_stock_logger、
環境切換、RotatingFileHandler 配置等核心功能。
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.infra.logging import (
    StructuredFormatter,
    StockLoggerAdapter,
    _configured_loggers,
    _get_environment,
    _get_log_level,
    get_logger,
    get_stock_logger,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_loggers():
    """每次測試前清除已配置的 logger，避免交叉汙染。"""
    _configured_loggers.clear()
    # 移除可能殘留的 handlers
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith("test_logging_"):
            logger = logging.getLogger(name)
            logger.handlers.clear()
    yield
    _configured_loggers.clear()


@pytest.fixture
def temp_log_dir(monkeypatch: pytest.MonkeyPatch):
    """將日誌目錄指向專案內暫存目錄以避免 Windows tmp_path 權限問題。"""
    import app.infra.logging as log_module

    # 使用專案內部的 .test_logs 目錄
    test_dir = Path(__file__).resolve().parent.parent.parent / ".test_logs"
    monkeypatch.setattr(log_module, "_DEFAULT_LOG_DIR", str(test_dir))
    yield test_dir
    # 清理
    import shutil

    if test_dir.exists():
        shutil.rmtree(test_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# StructuredFormatter 測試
# ---------------------------------------------------------------------------


class TestStructuredFormatter:
    """StructuredFormatter 格式化測試。"""

    def test_basic_format_produces_valid_json(self) -> None:
        """基本格式化應產出有效的 JSON 字串。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="測試訊息",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "測試訊息"
        assert parsed["module"] == "test"
        assert "timestamp" in parsed

    def test_includes_stock_code_when_present(self) -> None:
        """當 LogRecord 帶有 stock_code 屬性時應包含在 JSON 中。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="取得資料",
            args=None,
            exc_info=None,
        )
        record.stock_code = "2330"  # type: ignore[attr-defined]
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["stock_code"] == "2330"

    def test_stock_code_none_when_absent(self) -> None:
        """當 LogRecord 無 stock_code 屬性時應為 null。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="警告",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["stock_code"] is None

    def test_includes_source_field(self) -> None:
        """source 欄位正確序列化。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="debug",
            args=None,
            exc_info=None,
        )
        record.source = "yahoo_finance"  # type: ignore[attr-defined]
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["source"] == "yahoo_finance"

    def test_includes_exception_info(self) -> None:
        """例外資訊應附加至 JSON 的 exception 欄位。"""
        formatter = StructuredFormatter()
        try:
            raise ValueError("測試例外")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="錯誤發生",
            args=None,
            exc_info=exc_info,
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "測試例外" in parsed["exception"]

    def test_function_name_in_output(self) -> None:
        """funcName 欄位應正確出現在 JSON 中。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
            func="my_function",
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["function"] == "my_function"

    def test_chinese_message_not_escaped(self) -> None:
        """中文訊息不應被 ASCII 轉義。"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="取得台積電股價資料",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)

        # 中文字元應直接出現，不應被 \\uXXXX 轉義
        assert "取得台積電股價資料" in result


# ---------------------------------------------------------------------------
# 環境偵測與日誌等級測試
# ---------------------------------------------------------------------------


class TestEnvironmentDetection:
    """環境偵測與日誌等級配置測試。"""

    def test_multiple_loggers_share_one_rotating_file_handler(
        self, temp_log_dir: Path
    ) -> None:
        """多個 logger 共享同一個 log 檔案 handler，避免 Windows 重命名衝突。"""
        logger_a = get_logger("test_logging_a")
        logger_b = get_logger("test_logging_b")

        rotating_handlers = [
            h
            for h in logger_a.handlers + logger_b.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        unique_handlers = {id(handler) for handler in rotating_handlers}

        assert len(unique_handlers) == 1
        assert Path(next(iter(rotating_handlers)).baseFilename) == temp_log_dir / "stock_tool.log"

    def test_default_environment_is_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """未設定 STOCK_TOOL_ENV 時預設為 development。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        assert _get_environment() == "development"

    def test_production_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """STOCK_TOOL_ENV=production 時回傳 production。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "production")
        assert _get_environment() == "production"

    def test_invalid_env_falls_back_to_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """無效環境值回退至 development。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "staging")
        assert _get_environment() == "development"

    def test_development_default_level_is_debug(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """開發環境預設 DEBUG。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        assert _get_log_level() == logging.DEBUG

    def test_production_default_level_is_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """生產環境預設 INFO。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "production")
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        assert _get_log_level() == logging.INFO

    def test_explicit_log_level_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOG_LEVEL 環境變數覆寫環境預設值。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "production")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        assert _get_log_level() == logging.WARNING


# ---------------------------------------------------------------------------
# get_logger 測試
# ---------------------------------------------------------------------------


class TestGetLogger:
    """get_logger 工廠函式測試。"""

    def test_returns_logger_instance(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_logger 應回傳 Logger 實例。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        logger = get_logger("test_logging_basic")
        assert isinstance(logger, logging.Logger)

    def test_same_name_returns_same_logger(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """相同名稱多次呼叫應回傳同一實例。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        logger1 = get_logger("test_logging_same")
        logger2 = get_logger("test_logging_same")
        assert logger1 is logger2

    def test_development_has_console_handler(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """開發環境應包含 StreamHandler。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "development")
        logger = get_logger("test_logging_dev_console")
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types

    def test_production_has_no_console_handler(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """生產環境不應包含 StreamHandler。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "production")
        logger = get_logger("test_logging_prod_no_console")
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler not in handler_types

    def test_has_rotating_file_handler(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """應包含 RotatingFileHandler。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        logger = get_logger("test_logging_file_handler")
        handler_types = [type(h) for h in logger.handlers]
        assert logging.handlers.RotatingFileHandler in handler_types

    def test_rotating_handler_config(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RotatingFileHandler 應配置 10MB 與 5 個備份。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        logger = get_logger("test_logging_rotate_config")
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                assert handler.maxBytes == 10 * 1024 * 1024
                assert handler.backupCount == 5
                break
        else:
            pytest.fail("未找到 RotatingFileHandler")

    def test_creates_log_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """日誌目錄不存在時應自動建立。"""
        import app.infra.logging as log_module

        unique_dir = tmp_path / ".test_logs_create"

        monkeypatch.setattr(log_module, "_DEFAULT_LOG_DIR", str(unique_dir))
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)

        assert not unique_dir.exists()
        get_logger("test_logging_mkdir")
        assert unique_dir.exists()

    def test_log_propagation_disabled(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """logger.propagate 應為 False 避免重複輸出。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        logger = get_logger("test_logging_propagate")
        assert logger.propagate is False


# ---------------------------------------------------------------------------
# get_stock_logger 測試
# ---------------------------------------------------------------------------


class TestGetStockLogger:
    """get_stock_logger 工廠函式測試。"""

    def test_returns_adapter_instance(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_stock_logger 應回傳 StockLoggerAdapter 實例。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        adapter = get_stock_logger("test_logging_adapter", "2330")
        assert isinstance(adapter, StockLoggerAdapter)

    def test_adapter_carries_stock_code(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adapter 應攜帶 stock_code。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        adapter = get_stock_logger("test_logging_code", "2330")
        assert adapter.extra["stock_code"] == "2330"

    def test_adapter_carries_source(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adapter 應攜帶 source。"""
        monkeypatch.delenv("STOCK_TOOL_ENV", raising=False)
        adapter = get_stock_logger(
            "test_logging_source", "AAPL", source="yahoo_finance"
        )
        assert adapter.extra["source"] == "yahoo_finance"

    def test_adapter_log_output_contains_stock_code(
        self, temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """透過 adapter 記錄的日誌應包含 stock_code。"""
        monkeypatch.setenv("STOCK_TOOL_ENV", "development")
        adapter = get_stock_logger(
            "test_logging_adapter_output", "2330", source="finmind"
        )

        # 加入一個記錄 handler 來捕獲輸出
        captured: list[str] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(self.format(record))

        capture_handler = CaptureHandler()
        capture_handler.setFormatter(StructuredFormatter())
        adapter.logger.addHandler(capture_handler)

        try:
            adapter.info("取得資料成功")
            assert len(captured) == 1
            parsed = json.loads(captured[0])
            assert parsed["stock_code"] == "2330"
            assert parsed["source"] == "finmind"
            assert parsed["message"] == "取得資料成功"
        finally:
            adapter.logger.removeHandler(capture_handler)
