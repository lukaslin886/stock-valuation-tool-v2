"""Tests for fix_prices.py repair (2026-08-22).

Validates the two critical fixes:
  1. Surfix fallback: .TW first, then .TWO (correctly handles ETF 0050 + 上櫃股)
  2. Only-write-valid: never writes 0 (price must be > 0)
"""
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Load fix_prices.py without executing main()
# 修正：tests/test_fix_prices.py → ../.. 才是 stock-valuation-tool/
FIX_PY = Path(__file__).resolve().parents[1] / "fix_prices.py"
spec = importlib.util.spec_from_file_location("fix_prices", FIX_PY)
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


def _mock_response(price_or_status):
    """Build a fake requests.get return."""
    resp = Mock()
    if isinstance(price_or_status, int):
        resp.status_code = price_or_status
        return resp
    resp.status_code = 200
    resp.json.return_value = {"chart": {"result": [{"meta": {"regularMarketPrice": price_or_status}}]}}
    return resp


class TestFetchPriceSurfix:
    def test_0050_etf_uses_TW(self):
        """0050 ETF 應先用 .TW（修復前誤判 .TWO → 404）."""
        with patch.object(fix.requests, "get", side_effect=[
            _mock_response(104.65),   # .TW 成功
            _mock_response(404),      # .TWO 不應被呼叫（但 fallback 備用）
        ]) as mock_get:
            price, suffix = fix.fetch_price("0050")
        assert price == 104.65
        assert suffix == ".TW"
        # 確保第一個嘗試是 .TW
        assert str(mock_get.call_args_list[0][0][0]).endswith(".TW")

    def test_general_tw_success(self):
        """一般上市股 (2330) 用 .TW 直接成功，不 fallback."""
        with patch.object(fix.requests, "get", return_value=_mock_response(2410.0)) as mock_get:
            price, suffix = fix.fetch_price("2330")
        assert price == 2410.0
        assert suffix == ".TW"
        mock_get.assert_called_once()

    def test_otc_falls_back_to_TWO(self):
        """上櫃股若 .TW 404，應 fallback 到 .TWO."""
        with patch.object(fix.requests, "get", side_effect=[
            _mock_response(404),   # .TW 404
            _mock_response(65.0),  # .TWO 成功
        ]) as mock_get:
            price, suffix = fix.fetch_price("1259")
        assert price == 65.0
        assert suffix == ".TWO"
        assert mock_get.call_count == 2

    def test_both_fail_returns_none(self):
        """兩者都失敗應回傳 None（不寫 0）."""
        with patch.object(fix.requests, "get", side_effect=[
            _mock_response(404),
            _mock_response(404),
        ]):
            price, suffix = fix.fetch_price("1262")
        assert price is None
        assert suffix is None

    def test_zero_price_not_returned(self):
        """若 API 回傳 0 價格，應視為無效（防 0）."""
        with patch.object(fix.requests, "get", side_effect=[
            _mock_response(0),     # .TW 回 0 → 無效
            _mock_response(52.4),  # .TWO 回有效
        ]):
            price, suffix = fix.fetch_price("9999")
        assert price == 52.4  # 不採納 0，用 .TWO

    def test_exception_returns_none(self):
        """requests 異常應回 None，不崩潰."""
        with patch.object(fix.requests, "get", side_effect=Exception("network")):
            price, suffix = fix.fetch_price("2330")
        assert price is None
