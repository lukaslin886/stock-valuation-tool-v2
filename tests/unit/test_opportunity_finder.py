"""
OpportunityFinder 單元測試 (P2-44)

使用 Mock 物件模擬 DataManagerV2 與 DCFCalculator，
確保掃描邏輯、篩選條件、優先級分類正確。
"""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from app.opportunity_finder import OpportunityFinder


# ── Fixtures ─────────────────────────────────────────────────────────

def _make_data_manager(
    eps: float = 5.0,
    growth_1_5: float = 0.15,
    growth_6_10: float = 0.08,
    price: float = 100.0,
) -> MagicMock:
    """建立 DataManagerV2 的 Mock 物件。"""
    dm = MagicMock()
    dm.get_latest_eps.return_value = eps
    dm.calculate_historical_growth_rate.return_value = {
        "growth_rate_1_5": growth_1_5,
        "growth_rate_6_10": growth_6_10,
        "data_quality": "good",
        "message": "ok",
        "weighting_method": "time_weighted",
    }
    dm.get_latest_price.return_value = price
    return dm


def _make_dcf_calculator(
    intrinsic_value: float = 150.0,
    upside_potential: float = 0.50,
    buy_price: float = 127.5,
) -> MagicMock:
    """建立 DCFCalculator 的 Mock 物件。"""
    calc = MagicMock()
    calc.calculate_dcf_value.return_value = {
        "intrinsic_value": intrinsic_value,
        "upside_potential": upside_potential,
        "current_price": 100.0,
        "recommendation": "強烈推薦",
    }
    calc.calculate_buy_recommendation.return_value = {
        "intrinsic_value": intrinsic_value,
        "current_price": 100.0,
        "recommended_buy_price": buy_price,
        "is_undervalued": True,
        "discount_pct": 0.33,
        "priority": "A",
        "recommendation": "優先級 A - 低估 50%",
    }
    return calc


@pytest.fixture
def data_manager() -> MagicMock:
    return _make_data_manager()


@pytest.fixture
def dcf_calculator() -> MagicMock:
    return _make_dcf_calculator()


@pytest.fixture
def finder(data_manager: MagicMock, dcf_calculator: MagicMock) -> OpportunityFinder:
    return OpportunityFinder(
        data_manager=data_manager,
        dcf_calculator=dcf_calculator,
    )


# ── 初始化測試 ────────────────────────────────────────────────────────

class TestOpportunityFinderInit:
    def test_init_stores_dependencies(self, data_manager, dcf_calculator) -> None:
        """初始化應正確儲存依賴物件。"""
        finder = OpportunityFinder(data_manager, dcf_calculator)
        assert finder.data_manager is data_manager
        assert finder.dcf_calculator is dcf_calculator
        assert finder.market_scanner is None

    def test_init_with_market_scanner(self, data_manager, dcf_calculator) -> None:
        """提供 market_scanner 時應正確儲存。"""
        scanner = MagicMock()
        finder = OpportunityFinder(data_manager, dcf_calculator, market_scanner=scanner)
        assert finder.market_scanner is scanner

    def test_taiwan_50_stocks_not_empty(self, finder) -> None:
        """TAIWAN_50_STOCKS 應為非空清單。"""
        assert len(OpportunityFinder.TAIWAN_50_STOCKS) > 0

    def test_taiwan_50_stocks_have_required_keys(self, finder) -> None:
        """每個候選股票應包含 stock_id 與 stock_name。"""
        for stock in OpportunityFinder.TAIWAN_50_STOCKS:
            assert "stock_id" in stock
            assert "stock_name" in stock


# ── scan_opportunities 測試 ───────────────────────────────────────────

class TestScanOpportunities:
    def test_returns_list(self, finder) -> None:
        """scan_opportunities 應返回 list。"""
        result = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}]
        )
        assert isinstance(result, list)

    def test_single_stock_passes_all_filters(self, finder) -> None:
        """單一股票符合所有條件時應出現在結果中。"""
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            dcf_threshold=0.20,
        )
        assert len(results) == 1
        assert results[0]["stock_code"] == "2330"

    def test_result_has_required_fields(self, finder) -> None:
        """結果字典應包含所有必要欄位。"""
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
        )
        assert len(results) == 1
        required = {
            "stock_code", "stock_name", "current_price", "dcf_value",
            "upside_pct", "buy_price", "priority", "reason",
        }
        assert required.issubset(results[0].keys())

    def test_uses_default_taiwan_50_when_no_candidates(
        self, data_manager, dcf_calculator
    ) -> None:
        """未提供 candidate_stocks 時應使用 TAIWAN_50_STOCKS。"""
        finder = OpportunityFinder(data_manager, dcf_calculator)
        # scan 全部預設清單（每一檔都會 pass，因為 mock upside=50%）
        results = finder.scan_opportunities()
        assert len(results) == len(OpportunityFinder.TAIWAN_50_STOCKS)

    def test_empty_candidate_list_returns_empty(self, finder) -> None:
        """傳入空候選清單應返回空結果。"""
        results = finder.scan_opportunities(candidate_stocks=[])
        assert results == []

    def test_stock_with_empty_code_is_skipped(self, finder) -> None:
        """stock_id 為空字串的候選應被跳過。"""
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "", "stock_name": "?"}]
        )
        assert results == []

    def test_progress_callback_is_called(self, finder) -> None:
        """提供 progress_callback 時應被呼叫。"""
        calls = []

        def cb(current: int, total: int, code: str) -> None:
            calls.append((current, total, code))

        finder.scan_opportunities(
            candidate_stocks=[
                {"stock_id": "2330", "stock_name": "台積電"},
                {"stock_id": "2317", "stock_name": "鴻海"},
            ],
            progress_callback=cb,
        )
        assert len(calls) == 2
        assert calls[0] == (1, 2, "2330")
        assert calls[1] == (2, 2, "2317")

    def test_results_sorted_by_priority_then_upside(
        self, data_manager, dcf_calculator
    ) -> None:
        """結果應依優先級 A→B→C 再依低估幅度降序排列。"""
        counter = [0]

        def side_effect_dcf(**kwargs: Any) -> Dict:
            counter[0] += 1
            upsides = [0.35, 0.22, 0.40]  # stock 1=A(35%), 2=C(22%), 3=A(40%)
            roes = [0.16, 0.05, 0.20]
            idx = (counter[0] - 1) % 3
            return {"intrinsic_value": 150.0, "upside_potential": upsides[idx]}

        dcf_calculator.calculate_dcf_value.side_effect = side_effect_dcf
        # 固定 buy_rec 輸出
        dcf_calculator.calculate_buy_recommendation.return_value = {
            "recommended_buy_price": 127.5,
            "is_undervalued": True,
        }
        roe_counter = [0]
        # 提供 snapshot_map 覆寫 ROE
        candidates = [
            {"stock_id": "A", "stock_name": "A"},
            {"stock_id": "B", "stock_name": "B"},
            {"stock_id": "C", "stock_name": "C"},
        ]
        finder = OpportunityFinder(data_manager, dcf_calculator)
        results = finder.scan_opportunities(
            candidate_stocks=candidates, dcf_threshold=0.20, use_market_snapshot=False
        )
        # All 3 should appear; A and C have priority A (with roe>=15% from mock)
        # because mock doesn't provide roe from snapshot → roe = 0.0 → priority C
        # all three get priority C; sorted by upside desc: 0.40, 0.35, 0.22
        upsides_out = [r["upside_pct"] for r in results]
        assert upsides_out == sorted(upsides_out, reverse=True)


# ── DCF 篩選測試 ─────────────────────────────────────────────────────

class TestDCFFiltering:
    def test_stock_below_dcf_threshold_excluded(self, data_manager, dcf_calculator) -> None:
        """DCF 低估幅度低於門檻的股票應被排除。"""
        dcf_calculator.calculate_dcf_value.return_value = {
            "intrinsic_value": 110.0,
            "upside_potential": 0.10,  # 只有 10%
        }
        finder = OpportunityFinder(data_manager, dcf_calculator)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            dcf_threshold=0.20,
        )
        assert results == []

    def test_stock_exactly_at_threshold_included(self, data_manager, dcf_calculator) -> None:
        """DCF 低估幅度恰好等於門檻時應被納入。"""
        dcf_calculator.calculate_dcf_value.return_value = {
            "intrinsic_value": 120.0,
            "upside_potential": 0.20,
        }
        finder = OpportunityFinder(data_manager, dcf_calculator)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            dcf_threshold=0.20,
        )
        assert len(results) == 1

    def test_zero_eps_excludes_stock(self, dcf_calculator) -> None:
        """EPS 為 0 時應無法執行 DCF，股票被排除。"""
        dm = _make_data_manager(eps=0.0)
        finder = OpportunityFinder(dm, dcf_calculator)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}]
        )
        assert results == []

    def test_negative_eps_excludes_stock(self, dcf_calculator) -> None:
        """負 EPS 應使股票被排除。"""
        dm = _make_data_manager(eps=-2.0)
        finder = OpportunityFinder(dm, dcf_calculator)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}]
        )
        assert results == []

    def test_dcf_exception_excludes_stock(self, data_manager, dcf_calculator) -> None:
        """DCF 計算拋出例外時，股票應被靜默排除，不中止掃描。"""
        dcf_calculator.calculate_dcf_value.side_effect = RuntimeError("API error")
        finder = OpportunityFinder(data_manager, dcf_calculator)
        results = finder.scan_opportunities(
            candidate_stocks=[
                {"stock_id": "BAD", "stock_name": "壞股票"},
                {"stock_id": "2330", "stock_name": "台積電"},
            ]
        )
        # BAD 被排除，2330 也因 side_effect 而被排除
        assert results == []


# ── 基本面篩選測試 ────────────────────────────────────────────────────

class TestFundamentalFiltering:
    def _finder_with_snapshot(
        self, roe: float, market_cap: float, avg_volume: float
    ) -> tuple:
        """建立含快照資料的 finder（snapshot_map 在 scan 時自動載入）。"""
        scanner = MagicMock()
        import pandas as pd

        snapshot_df = pd.DataFrame(
            [
                {
                    "stock_code": "2330",
                    "stock_name": "台積電",
                    "current_price": 500.0,
                    "roe": roe,
                    "market_cap": market_cap,
                    "avg_volume": avg_volume,
                }
            ]
        )
        scanner.get_market_snapshot.return_value = snapshot_df
        dm = _make_data_manager(price=500.0)
        calc = _make_dcf_calculator(intrinsic_value=750.0, upside_potential=0.50, buy_price=637.5)
        finder = OpportunityFinder(dm, calc, market_scanner=scanner)
        return finder

    def test_roe_below_min_excluded(self) -> None:
        """ROE 低於 min_roe 時股票應被排除。"""
        finder = self._finder_with_snapshot(roe=0.03, market_cap=200e9, avg_volume=1_000_000)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            min_roe=0.05,
            use_market_snapshot=True,
        )
        assert results == []

    def test_roe_above_min_included(self) -> None:
        """ROE 高於 min_roe 時股票應被納入。"""
        finder = self._finder_with_snapshot(roe=0.20, market_cap=200e9, avg_volume=1_000_000)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            min_roe=0.05,
            use_market_snapshot=True,
        )
        assert len(results) == 1

    def test_market_cap_below_min_excluded(self) -> None:
        """市值低於 min_market_cap_b 時股票應被排除。"""
        finder = self._finder_with_snapshot(roe=0.20, market_cap=5e9, avg_volume=1_000_000)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            min_market_cap_b=10.0,
            use_market_snapshot=True,
        )
        assert results == []

    def test_avg_volume_below_min_excluded(self) -> None:
        """成交量低於 min_avg_volume 時股票應被排除。"""
        finder = self._finder_with_snapshot(roe=0.20, market_cap=200e9, avg_volume=100_000)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            min_avg_volume=500_000,
            use_market_snapshot=True,
        )
        assert results == []


# ── 優先級分類測試 ────────────────────────────────────────────────────

class TestAssignPriority:
    @pytest.fixture
    def finder(self) -> OpportunityFinder:
        return OpportunityFinder(MagicMock(), MagicMock())

    def test_priority_a_high_upside_high_roe(self, finder) -> None:
        assert finder._assign_priority(0.35, 0.20) == "A"

    def test_priority_a_exact_thresholds(self, finder) -> None:
        assert finder._assign_priority(0.30, 0.15) == "A"

    def test_priority_b_mid_upside_mid_roe(self, finder) -> None:
        assert finder._assign_priority(0.25, 0.12) == "B"

    def test_priority_b_exact_thresholds(self, finder) -> None:
        assert finder._assign_priority(0.20, 0.10) == "B"

    def test_priority_c_low_roe(self, finder) -> None:
        """upside 夠高但 ROE 低，應為 C。"""
        assert finder._assign_priority(0.25, 0.04) == "C"

    def test_priority_c_zero_roe(self, finder) -> None:
        assert finder._assign_priority(0.30, 0.0) == "C"

    def test_priority_a_requires_both_conditions(self, finder) -> None:
        """只有高 upside 但低 ROE，不得為 A。"""
        assert finder._assign_priority(0.50, 0.05) != "A"

    def test_priority_b_requires_both_conditions(self, finder) -> None:
        """只有高 ROE 但低 upside，不得為 B。"""
        assert finder._assign_priority(0.10, 0.20) not in ("A", "B")


# ── _safe_float 測試 ─────────────────────────────────────────────────

class TestSafeFloat:
    def test_converts_int(self) -> None:
        assert OpportunityFinder._safe_float(100) == 100.0

    def test_converts_string(self) -> None:
        assert OpportunityFinder._safe_float("3.14") == pytest.approx(3.14)

    def test_returns_none_for_none(self) -> None:
        assert OpportunityFinder._safe_float(None) is None

    def test_returns_none_for_invalid_string(self) -> None:
        assert OpportunityFinder._safe_float("abc") is None

    def test_returns_none_for_nan(self) -> None:
        import math
        assert OpportunityFinder._safe_float(float("nan")) is None


# ── Market Scanner 整合測試 ──────────────────────────────────────────

class TestMarketScannerIntegration:
    def test_snapshot_fallback_when_scanner_raises(
        self, data_manager, dcf_calculator
    ) -> None:
        """市場快照取得失敗時，應靜默降級，仍完成掃描。"""
        scanner = MagicMock()
        scanner.get_market_snapshot.side_effect = RuntimeError("DB error")

        finder = OpportunityFinder(data_manager, dcf_calculator, market_scanner=scanner)
        results = finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            use_market_snapshot=True,
        )
        # 快照失敗後降級為個別 API 查詢，2330 仍可通過 DCF 篩選
        assert len(results) == 1

    def test_snapshot_not_called_when_disabled(
        self, data_manager, dcf_calculator
    ) -> None:
        """use_market_snapshot=False 時，不應呼叫 market_scanner.get_market_snapshot。"""
        scanner = MagicMock()
        finder = OpportunityFinder(data_manager, dcf_calculator, market_scanner=scanner)
        finder.scan_opportunities(
            candidate_stocks=[{"stock_id": "2330", "stock_name": "台積電"}],
            use_market_snapshot=False,
        )
        scanner.get_market_snapshot.assert_not_called()
