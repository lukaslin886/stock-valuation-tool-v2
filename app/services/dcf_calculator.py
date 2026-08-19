"""DCF 股票估值計算器（服務層重構版）。

基於現金流量折現法（Discounted Cash Flow），參考巴菲特價值投資理念。
本模組為 app/dcf_calculator.py 的重構版本，改進項目：
- 依賴注入：透過建構子接收 DataPipeline，不直接實例化
- 美股支援：依據 Market enum 自動切換市場預設參數
- 型別安全：完整型別標註，回傳 DCFResult Pydantic 模型
- 情境分析：保守/中性/樂觀三情境比較與敏感性分析

Note:
    舊版 app/dcf_calculator.py 保留作為向下相容層，不予刪除。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.models.financial import DCFResult
from app.core.models.stock import Market, detect_market


# ---------------------------------------------------------------------------
# 市場預設參數
# ---------------------------------------------------------------------------

_MARKET_PARAMS: Dict[Market, Dict[str, float]] = {
    Market.TW: {
        "risk_free_rate": 0.04,
        "risk_premium": 0.04,
        "inflation_rate": 0.03,
        "perpetual_growth": 0.02,
    },
    Market.TWO: {
        "risk_free_rate": 0.04,
        "risk_premium": 0.04,
        "inflation_rate": 0.03,
        "perpetual_growth": 0.02,
    },
    Market.US: {
        "risk_free_rate": 0.045,
        "risk_premium": 0.05,
        "inflation_rate": 0.025,
        "perpetual_growth": 0.025,
    },
}


def _get_market_params(market: Market) -> Dict[str, float]:
    """取得指定市場的預設 DCF 參數。

    Args:
        market: 市場別列舉值。

    Returns:
        包含 risk_free_rate、risk_premium、inflation_rate、perpetual_growth 的字典。
    """
    return _MARKET_PARAMS.get(market, _MARKET_PARAMS[Market.TW]).copy()


# ---------------------------------------------------------------------------
# DCFCalculator 服務類別
# ---------------------------------------------------------------------------


class DCFCalculator:
    """DCF 股票估值計算器（服務層）。

    透過依賴注入接收 DataPipeline（可選），並依據市場別自動切換
    預設參數。計算結果以 DCFResult Pydantic 模型回傳，確保型別安全。

    Attributes:
        data_pipeline: 資料管線實例（可為 None，表示無需從外部取得資料）。
        default_params: 目前使用的預設參數字典。

    Example:
        >>> from app.services.dcf_calculator import DCFCalculator
        >>> calc = DCFCalculator()
        >>> result = calc.calculate_dcf_value(
        ...     current_price=973.0,
        ...     current_eps=32.34,
        ...     growth_rates=[0.23, 0.12],
        ...     market=Market.TW,
        ... )
        >>> result.intrinsic_value > 0
        True
    """

    def __init__(
        self,
        data_pipeline: Optional[Any] = None,
        market: Market = Market.TW,
    ) -> None:
        """初始化 DCF 計算器。

        Args:
            data_pipeline: DataPipeline 實例，透過 DI 注入。
                若為 None 則計算器僅執行本地計算，不從外部取得資料。
            market: 預設市場別，決定初始預設參數組合。
                可在 calculate_dcf_value 呼叫時覆寫。
        """
        self.data_pipeline = data_pipeline
        self.default_params: Dict[str, float] = _get_market_params(market)
        self._market = market

    # ------------------------------------------------------------------
    # 公開方法
    # ------------------------------------------------------------------

    def calculate_dcf_value(
        self,
        current_price: float,
        current_eps: float,
        growth_rates: List[float],
        discount_rate: Optional[float] = None,
        years: int = 10,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        market: Optional[Market] = None,
        data_source: Optional[str] = None,
        weighting_method: Optional[str] = None,
    ) -> DCFResult:
        """計算 DCF 股票內在價值。

        使用現金流量折現法預測未來現金流，加上終值後折現為內在價值。

        Args:
            current_price: 目前股價（須 > 0）。
            current_eps: 當前每股盈餘（可為負，但負值將導致內在價值為負）。
            growth_rates: 成長率列表，至少包含一個元素。
                若提供兩個元素，第一個為 1-5 年成長率，第二個為 6-10 年成長率。
            discount_rate: 折現率。若為 None 則以 CAPM 模型計算。
            years: 預測年數，預設 10 年。
            stock_code: 股票代碼（可選，用於結果標識）。
            stock_name: 股票名稱（可選，用於結果標識）。
            market: 市場別。若提供則覆寫建構子設定的預設參數。
                若為 None 且提供 stock_code，將嘗試自動偵測市場別。
            data_source: 資料來源描述（可選）。
            weighting_method: 成長率計算方法（可選，紀錄用）。

        Returns:
            DCFResult Pydantic 模型，包含完整的估值結果。

        Raises:
            ValueError: 當 current_price <= 0 或 growth_rates 為空時。
        """
        # 參數驗證
        if current_price <= 0:
            raise ValueError("current_price 必須大於 0")
        if not growth_rates:
            raise ValueError("growth_rates 不得為空")

        # 決定市場參數
        effective_market = self._resolve_market(market, stock_code)
        params = _get_market_params(effective_market)

        # 計算折現率
        if discount_rate is None:
            discount_rate = self._calculate_capm_rate(params)

        # 預測未來現金流
        cash_flows = self._project_cash_flows(current_eps, growth_rates, years)

        # 計算現金流現值
        present_values = self._calculate_present_values(cash_flows, discount_rate)

        # 計算終值
        terminal_value = self._calculate_terminal_value(
            cash_flows, discount_rate, params["perpetual_growth"]
        )

        # 計算總價值（內在價值）
        intrinsic_value = sum(present_values) + terminal_value

        # 計算潛在獲利率
        upside_potential = (intrinsic_value - current_price) / current_price

        # 產生投資建議
        recommendation = self._get_investment_recommendation(upside_potential)

        # 組裝 DCFResult
        result = DCFResult(
            stock_code=stock_code or "",
            stock_name=stock_name or "",
            current_price=current_price,
            intrinsic_value=intrinsic_value,
            upside_potential=upside_potential,
            discount_rate=discount_rate,
            growth_rates=growth_rates,
            terminal_value=terminal_value,
            recommendation=recommendation,
            calculated_at=datetime.now(),
            data_source=data_source or "",
        )

        return result

    def calculate_scenario_comparison(
        self,
        current_price: float,
        current_eps: float,
        base_growth_rates: List[float],
        discount_rate: Optional[float] = None,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        market: Optional[Market] = None,
        data_source: Optional[str] = None,
        weighting_method: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """計算三種情境（保守、中性、樂觀）的 DCF 估值比較。

        保守情境：成長率降低 30%（下限 -50%）。
        中性情境：使用當前設定的成長率。
        樂觀情境：成長率增加 30%（上限 +50%）。

        Args:
            current_price: 目前股價。
            current_eps: 當前每股盈餘。
            base_growth_rates: 基準成長率列表。
            discount_rate: 折現率（若為 None 則 CAPM 計算）。
            stock_code: 股票代碼（可選）。
            stock_name: 股票名稱（可選）。
            market: 市場別（可選）。
            data_source: 資料來源描述（可選）。
            weighting_method: 成長率計算方法（可選）。

        Returns:
            包含三種情境結果的字典，鍵為情境名稱，值為包含
            DCFResult 與 metadata 的字典。
        """
        effective_market = self._resolve_market(market, stock_code)
        params = _get_market_params(effective_market)

        if discount_rate is None:
            discount_rate = self._calculate_capm_rate(params)

        scenarios: Dict[str, Dict[str, Any]] = {
            "conservative": {
                "name": "保守",
                "growth_rates": [
                    max(-0.5, base_growth_rates[0] * 0.7),
                    max(-0.5, base_growth_rates[1] * 0.7)
                    if len(base_growth_rates) > 1
                    else max(-0.5, base_growth_rates[0] * 0.7),
                ],
                "color": "#ef5350",
                "description": "成長率降低 30%",
            },
            "neutral": {
                "name": "中性",
                "growth_rates": base_growth_rates,
                "color": "#42a5f5",
                "description": "使用當前設定的成長率",
            },
            "optimistic": {
                "name": "樂觀",
                "growth_rates": [
                    min(0.5, base_growth_rates[0] * 1.3),
                    min(0.5, base_growth_rates[1] * 1.3)
                    if len(base_growth_rates) > 1
                    else min(0.5, base_growth_rates[0] * 1.3),
                ],
                "color": "#66bb6a",
                "description": "成長率增加 30%",
            },
        }

        results: Dict[str, Dict[str, Any]] = {}
        for key, scenario_data in scenarios.items():
            dcf_result = self.calculate_dcf_value(
                current_price=current_price,
                current_eps=current_eps,
                growth_rates=scenario_data["growth_rates"],
                discount_rate=discount_rate,
                stock_code=stock_code,
                stock_name=stock_name,
                market=effective_market,
                data_source=data_source,
                weighting_method=weighting_method,
            )
            results[key] = {
                "name": scenario_data["name"],
                "result": dcf_result,
                "color": scenario_data["color"],
                "description": scenario_data["description"],
            }

        return results

    def sensitivity_analysis(
        self,
        current_price: float,
        current_eps: float,
        base_growth_rates: List[float],
        discount_rate: Optional[float] = None,
        market: Optional[Market] = None,
        stock_code: Optional[str] = None,
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """執行敏感性分析，對成長率與折現率進行交叉測試。

        測試三種成長率情境（悲觀 -20%、基準、樂觀 +20%）
        搭配三種折現率（8%、11%、14%），共九種組合。

        Args:
            current_price: 目前股價。
            current_eps: 當前每股盈餘。
            base_growth_rates: 基準成長率列表。
            discount_rate: 折現率（此處不使用，僅為 API 相容性保留）。
            market: 市場別（可選）。
            stock_code: 股票代碼（可選）。

        Returns:
            巢狀字典結構：{情境名稱: {折現率描述: {內在價值, 潛在獲利率}}}。
        """
        effective_market = self._resolve_market(market, stock_code)

        growth_scenarios: List[List[float]] = [
            [base_growth_rates[0] * 0.8, base_growth_rates[1] * 0.8]
            if len(base_growth_rates) > 1
            else [base_growth_rates[0] * 0.8],
            base_growth_rates,
            [base_growth_rates[0] * 1.2, base_growth_rates[1] * 1.2]
            if len(base_growth_rates) > 1
            else [base_growth_rates[0] * 1.2],
        ]
        scenario_names = ["pessimistic", "base", "optimistic"]
        discount_scenarios = [0.08, 0.11, 0.14]

        results: Dict[str, Dict[str, Dict[str, float]]] = {}
        for i, growth in enumerate(growth_scenarios):
            scenario_key = scenario_names[i]
            results[scenario_key] = {}
            for disc_rate in discount_scenarios:
                dcf_result = self.calculate_dcf_value(
                    current_price=current_price,
                    current_eps=current_eps,
                    growth_rates=growth,
                    discount_rate=disc_rate,
                    market=effective_market,
                    stock_code=stock_code,
                )
                rate_key = f"discount_{disc_rate:.0%}"
                results[scenario_key][rate_key] = {
                    "intrinsic_value": dcf_result.intrinsic_value,
                    "upside_potential": dcf_result.upside_potential,
                }

        return results

    def calculate_growth_rate(self, eps_history: List[float]) -> float:
        """從歷史 EPS 序列計算年化成長率。

        使用複合年均成長率（CAGR）公式計算。
        若所有 EPS 相同，回傳 0。

        Args:
            eps_history: 歷史 EPS 序列，由舊到新排列。至少需要 2 個元素。

        Returns:
            年化成長率（小數形式，例如 0.15 表示 15%）。

        Raises:
            ValueError: 當 eps_history 少於 2 個元素時。
        """
        if len(eps_history) < 2:
            raise ValueError("eps_history 至少需要 2 個元素")

        first_eps = eps_history[0]
        last_eps = eps_history[-1]
        n_years = len(eps_history) - 1

        # 若首尾 EPS 相同，成長率為 0
        if first_eps == last_eps:
            return 0.0

        # 若起始 EPS 為 0 或負數，無法計算 CAGR
        if first_eps <= 0:
            if last_eps <= 0:
                return 0.0
            # 從負轉正，使用簡單平均成長
            total_growth = (last_eps - first_eps) / abs(first_eps) if first_eps != 0 else 0.0
            return total_growth / n_years

        # 標準 CAGR
        growth_rate = (last_eps / first_eps) ** (1.0 / n_years) - 1.0
        return growth_rate

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _resolve_market(
        self, market: Optional[Market], stock_code: Optional[str]
    ) -> Market:
        """決定有效市場別。

        優先順序：明確指定 > 由 stock_code 偵測 > 建構子預設。

        Args:
            market: 明確指定的市場別（可為 None）。
            stock_code: 股票代碼（可為 None）。

        Returns:
            最終使用的 Market 列舉值。
        """
        if market is not None:
            return market
        if stock_code:
            return detect_market(stock_code)
        return self._market

    def _calculate_capm_rate(self, params: Optional[Dict[str, float]] = None) -> float:
        """使用 CAPM 模型計算折現率。

        折現率 = 無風險利率 + 風險溢酬 + 通膨率。

        Args:
            params: 市場參數字典。若為 None 則使用實例預設參數。

        Returns:
            計算出的折現率（小數形式）。
        """
        p = params or self.default_params
        return p["risk_free_rate"] + p["risk_premium"] + p["inflation_rate"]

    def _project_cash_flows(
        self,
        current_eps: float,
        growth_rates: List[float],
        years: int,
    ) -> List[float]:
        """預測未來各年度現金流。

        1-5 年使用第一個成長率，6-10 年使用第二個成長率。
        若 growth_rates 僅有一個元素，則所有年度皆使用同一成長率。

        Args:
            current_eps: 當前每股盈餘。
            growth_rates: 成長率列表。
            years: 預測年數。

        Returns:
            各年度預測現金流列表。
        """
        # 確保至少有兩個成長率
        rates = list(growth_rates)
        while len(rates) < 2:
            rates.append(rates[-1] if rates else 0.08)

        cash_flows: List[float] = []
        current_year_eps = current_eps

        # 1-5 年
        for _ in range(1, min(6, years + 1)):
            current_year_eps *= 1 + rates[0]
            cash_flows.append(current_year_eps)

        # 6-10 年
        for _ in range(6, years + 1):
            current_year_eps *= 1 + rates[1]
            cash_flows.append(current_year_eps)

        return cash_flows

    def _calculate_present_values(
        self,
        cash_flows: List[float],
        discount_rate: float,
    ) -> List[float]:
        """計算各年度現金流的現值。

        Args:
            cash_flows: 各年度預測現金流列表。
            discount_rate: 折現率。

        Returns:
            各年度現金流折現後的現值列表。
        """
        return [cf / ((1 + discount_rate) ** year) for year, cf in enumerate(cash_flows, 1)]

    def _calculate_terminal_value(
        self,
        cash_flows: List[float],
        discount_rate: float,
        perpetual_growth: float,
    ) -> float:
        """計算終值（Terminal Value）並折現至現值。

        使用永續成長模型：TV = CF_last * (1 + g) / (r - g)，
        再折現至第 0 年。

        Args:
            cash_flows: 各年度預測現金流列表。
            discount_rate: 折現率。
            perpetual_growth: 永續成長率。

        Returns:
            折現後的終值。若現金流為空或折現率 <= 永續成長率，回傳 0。
        """
        if not cash_flows:
            return 0.0

        last_cash_flow = cash_flows[-1]

        # 避免除以零或負數
        if discount_rate <= perpetual_growth:
            return 0.0

        terminal_value = last_cash_flow * (1 + perpetual_growth) / (discount_rate - perpetual_growth)

        # 折現到現值
        years = len(cash_flows)
        present_terminal_value = terminal_value / ((1 + discount_rate) ** years)

        return present_terminal_value

    def _get_investment_recommendation(self, upside_potential: float) -> str:
        """根據潛在獲利率產生投資建議文字。

        Args:
            upside_potential: 潛在獲利率（小數形式，如 0.3 表示 30%）。

        Returns:
            投資建議字串。
        """
        if upside_potential > 0.5:
            return "強烈推薦 - 具有顯著低估機會"
        elif upside_potential > 0.3:
            return "推薦 - 具有投資價值"
        elif upside_potential > 0.1:
            return "考慮 - 視市場情況決定"
        elif upside_potential > -0.1:
            return "觀望 - 價格接近內在價值"
        else:
            return "不推薦 - 可能被高估"
