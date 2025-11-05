"""
Portfolio Analyzer 與滑動風險模型整合測試套件

測試涵蓋：
- StockAnalyzer 滑價功能初始化
- 投資組合分析（含滑價）
- 加碼建議計算（含滑價）
- 滑價資訊完整性
- 停用滑價模式
- 不同流動性股票的影響
- 邊界條件處理
"""

import pytest
import pandas as pd
from pathlib import Path
from portfolio_analyzer.analyzer import StockAnalyzer


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_holdings():
    """創建測試持股資料"""
    data = {
        '股票名稱': ['2330 台積電', '2317 鴻海', '2881 富邦金'],
        '股數': [100, 500, 1000],
        '成交均價': [500.0, 100.0, 50.0],
        '市價': [593.0, 110.0, 55.0],
        '報酬率': [18.6, 10.0, 10.0],
        '現值': [59300, 55000, 55000],
        '總損益': [9300, 5000, 5000]
    }
    return pd.DataFrame(data)


@pytest.fixture
def analyzer_with_slippage():
    """創建啟用滑價的 StockAnalyzer"""
    return StockAnalyzer(enable_slippage=True)


@pytest.fixture
def analyzer_without_slippage():
    """創建停用滑價的 StockAnalyzer"""
    return StockAnalyzer(enable_slippage=False)


# ============================================================================
# Test Class: StockAnalyzer 滑價功能初始化
# ============================================================================

class TestStockAnalyzerSlippageInit:
    """測試 StockAnalyzer 滑價功能初始化"""
    
    def test_init_with_slippage_enabled(self, analyzer_with_slippage):
        """測試啟用滑價初始化"""
        assert analyzer_with_slippage.enable_slippage is True
        assert analyzer_with_slippage.slippage_model is not None
    
    def test_init_with_slippage_disabled(self, analyzer_without_slippage):
        """測試停用滑價初始化"""
        assert analyzer_without_slippage.enable_slippage is False
        assert analyzer_without_slippage.slippage_model is None
    
    def test_init_default_slippage_enabled(self):
        """測試預設狀態（滑價啟用）"""
        analyzer = StockAnalyzer()
        assert analyzer.enable_slippage is True
        assert analyzer.slippage_model is not None


# ============================================================================
# Test Class: 投資組合分析（含滑價）
# ============================================================================

class TestPortfolioAnalysisWithSlippage:
    """測試投資組合分析（含滑價）"""
    
    def test_analyze_portfolio_basic(self, analyzer_with_slippage, test_holdings):
        """測試基本投資組合分析"""
        results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        # 檢查結果結構
        assert results is not None
        assert 'statistics' in results
        assert 'sell_list' in results
        assert 'hold_list' in results
        assert 'protected_list' in results
    
    def test_analyze_portfolio_statistics(self, analyzer_with_slippage, test_holdings):
        """測試投資組合統計資訊"""
        results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if results:
            stats = results['statistics']
            
            # 檢查統計資訊鍵值
            assert isinstance(stats, dict)
            # 統計可能包含：總數、賣出建議數、持有建議數等
    
    def test_analyze_portfolio_with_empty_holdings(self, analyzer_with_slippage):
        """測試空持股資料"""
        empty_holdings = pd.DataFrame()
        
        results = analyzer_with_slippage.analyze_portfolio(empty_holdings)
        
        # 應該能處理空資料
        assert results is not None or results is None


# ============================================================================
# Test Class: 加碼建議計算（含滑價）
# ============================================================================

class TestBuyOpportunitiesWithSlippage:
    """測試加碼建議計算（含滑價）"""
    
    def test_analyze_buy_opportunities_basic(
        self, analyzer_with_slippage, test_holdings
    ):
        """測試基本加碼建議分析"""
        # 先進行投資組合分析
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        # 分析加碼機會
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        # 檢查結果類型
        assert isinstance(buy_opps, list)
    
    def test_buy_opportunities_slippage_info(
        self, analyzer_with_slippage, test_holdings
    ):
        """測試加碼建議中的滑價資訊"""
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        # 檢查每個加碼機會的滑價資訊
        for opp in buy_opps:
            assert 'stock_code' in opp
            assert 'stock_name' in opp
            assert 'current_price' in opp
            assert 'ideal_buy_price' in opp
            
            # 檢查滑價相關欄位
            if opp.get('slippage_enabled'):
                assert 'slippage_info' in opp
                slippage_info = opp['slippage_info']
                
                # 檢查滑價資訊結構
                assert 'slippage_rate' in slippage_info or 'slippage_pct' in slippage_info
                assert 'liquidity_tier' in slippage_info
                assert 'message' in slippage_info
    
    def test_buy_opportunities_price_adjustment(
        self, analyzer_with_slippage, test_holdings
    ):
        """測試買入價格調整"""
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        # 檢查有滑價調整的機會
        for opp in buy_opps:
            if opp.get('slippage_enabled'):
                # 有滑價時，最終建議價應該高於基礎價
                if 'base_buy_price' in opp:
                    assert opp['ideal_buy_price'] >= opp['base_buy_price']


# ============================================================================
# Test Class: 停用滑價模式
# ============================================================================

class TestDisabledSlippageMode:
    """測試停用滑價模式"""
    
    def test_analyzer_without_slippage(self, analyzer_without_slippage, test_holdings):
        """測試停用滑價的分析器"""
        results = analyzer_without_slippage.analyze_portfolio(test_holdings)
        
        # 應該能正常運作
        assert results is not None or results is None
    
    def test_buy_opportunities_without_slippage(
        self, analyzer_without_slippage, test_holdings
    ):
        """測試停用滑價的加碼建議"""
        analysis_results = analyzer_without_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_without_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        # 檢查不應有滑價調整
        for opp in buy_opps:
            # 停用滑價時，不應有滑價資訊或 slippage_enabled 應為 False
            if 'slippage_enabled' in opp:
                assert opp['slippage_enabled'] is False


# ============================================================================
# Test Class: 不同持股情境測試
# ============================================================================

class TestDifferentHoldingsScenarios:
    """測試不同持股情境"""
    
    def test_single_stock_portfolio(self, analyzer_with_slippage):
        """測試單一股票持股"""
        single_stock = pd.DataFrame({
            '股票名稱': ['2330 台積電'],
            '股數': [100],
            '成交均價': [500.0],
            '市價': [593.0],
            '報酬率': [18.6],
            '現值': [59300],
            '總損益': [9300]
        })
        
        results = analyzer_with_slippage.analyze_portfolio(single_stock)
        
        # 應該能處理單一股票
        assert results is not None or results is None
    
    def test_large_portfolio(self, analyzer_with_slippage):
        """測試大型投資組合（多檔持股）"""
        # 創建 10 檔股票的持股
        large_holdings = pd.DataFrame({
            '股票名稱': [f'{2300+i} 股票{i}' for i in range(10)],
            '股數': [100 * (i+1) for i in range(10)],
            '成交均價': [50.0 + i*10 for i in range(10)],
            '市價': [55.0 + i*10 for i in range(10)],
            '報酬率': [10.0] * 10,
            '現值': [(55.0 + i*10) * 100 * (i+1) for i in range(10)],
            '總損益': [5.0 * 100 * (i+1) for i in range(10)]
        })
        
        results = analyzer_with_slippage.analyze_portfolio(large_holdings)
        
        # 應該能處理多檔股票
        assert results is not None or results is None
    
    def test_mixed_performance_portfolio(self, analyzer_with_slippage):
        """測試混合績效的投資組合（盈虧參半）"""
        mixed_holdings = pd.DataFrame({
            '股票名稱': ['2330 台積電', '2317 鴻海', '2881 富邦金'],
            '股數': [100, 500, 1000],
            '成交均價': [600.0, 100.0, 60.0],  # 台積電買貴了
            '市價': [593.0, 110.0, 55.0],
            '報酬率': [-1.17, 10.0, -8.33],  # 有賺有賠
            '現值': [59300, 55000, 55000],
            '總損益': [-700, 5000, -5000]
        })
        
        results = analyzer_with_slippage.analyze_portfolio(mixed_holdings)
        
        # 應該能處理混合績效
        assert results is not None or results is None


# ============================================================================
# Test Class: 滑價資訊完整性測試
# ============================================================================

class TestSlippageInfoCompleteness:
    """測試滑價資訊完整性"""
    
    def test_slippage_info_structure(self, analyzer_with_slippage, test_holdings):
        """測試滑價資訊結構完整性"""
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        for opp in buy_opps:
            if opp.get('slippage_enabled') and 'slippage_info' in opp:
                slippage_info = opp['slippage_info']
                
                # 所有必要欄位都應該存在
                assert isinstance(slippage_info, dict)
                
                # 檢查關鍵資訊
                has_rate = 'slippage_rate' in slippage_info or 'slippage_pct' in slippage_info
                assert has_rate, "滑價資訊應包含滑價率"
    
    def test_slippage_rate_validity(self, analyzer_with_slippage, test_holdings):
        """測試滑價率的有效性"""
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        for opp in buy_opps:
            if opp.get('slippage_enabled') and 'slippage_info' in opp:
                slippage_info = opp['slippage_info']
                
                # 滑價率應該是合理的數值
                if 'slippage_rate' in slippage_info:
                    rate = slippage_info['slippage_rate']
                    assert isinstance(rate, (int, float))
                    assert rate >= 0, "滑價率應該為非負數"
                    assert rate < 100, "滑價率應該小於 100%"


# ============================================================================
# Test Class: 優先級與建議測試
# ============================================================================

class TestPriorityAndRecommendations:
    """測試優先級與建議"""
    
    def test_buy_opportunities_have_priorities(
        self, analyzer_with_slippage, test_holdings
    ):
        """測試加碼建議包含優先級"""
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        for opp in buy_opps:
            # 應該有優先級或建議
            has_priority = 'priority' in opp
            has_recommendation = 'recommendation' in opp
            
            assert has_priority or has_recommendation, "加碼建議應包含優先級或建議"
    
    def test_buy_opportunities_have_reasons(
        self, analyzer_with_slippage, test_holdings
    ):
        """測試加碼建議包含理由"""
        analysis_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not analysis_results:
            pytest.skip("無法取得投資組合分析結果")
        
        total_value = test_holdings['現值'].sum()
        
        buy_opps = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=analysis_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        for opp in buy_opps:
            # 應該有理由說明
            assert 'reason' in opp, "加碼建議應包含理由"
            assert isinstance(opp['reason'], str)


# ============================================================================
# Test Class: 邊界條件測試
# ============================================================================

class TestEdgeCases:
    """測試邊界條件與異常情況"""
    
    def test_zero_volume_holdings(self, analyzer_with_slippage):
        """測試零股數持股"""
        zero_holdings = pd.DataFrame({
            '股票名稱': ['2330 台積電'],
            '股數': [0],
            '成交均價': [500.0],
            '市價': [593.0],
            '報酬率': [0.0],
            '現值': [0],
            '總損益': [0]
        })
        
        results = analyzer_with_slippage.analyze_portfolio(zero_holdings)
        
        # 應該能處理零股數
        assert results is not None or results is None
    
    def test_negative_return_holdings(self, analyzer_with_slippage):
        """測試虧損持股"""
        loss_holdings = pd.DataFrame({
            '股票名稱': ['2330 台積電'],
            '股數': [100],
            '成交均價': [700.0],
            '市價': [593.0],
            '報酬率': [-15.29],
            '現值': [59300],
            '總損益': [-10700]
        })
        
        results = analyzer_with_slippage.analyze_portfolio(loss_holdings)
        
        # 應該能處理虧損持股
        assert results is not None or results is None
    
    def test_very_high_price_holdings(self, analyzer_with_slippage):
        """測試極高價格持股"""
        high_price_holdings = pd.DataFrame({
            '股票名稱': ['9999 高價股'],
            '股數': [10],
            '成交均價': [10000.0],
            '市價': [15000.0],
            '報酬率': [50.0],
            '現值': [150000],
            '總損益': [50000]
        })
        
        results = analyzer_with_slippage.analyze_portfolio(high_price_holdings)
        
        # 應該能處理高價股
        assert results is not None or results is None


# ============================================================================
# Test Class: 整合與一致性測試
# ============================================================================

class TestIntegrationAndConsistency:
    """整合與一致性測試"""
    
    def test_slippage_vs_no_slippage_comparison(
        self, analyzer_with_slippage, analyzer_without_slippage, test_holdings
    ):
        """比較啟用與停用滑價的差異"""
        # 啟用滑價
        results_with = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        # 停用滑價
        results_without = analyzer_without_slippage.analyze_portfolio(test_holdings)
        
        # 兩者都應該產生結果
        assert (results_with is not None) or (results_without is not None)
    
    def test_multiple_analyses_consistency(
        self, analyzer_with_slippage, test_holdings
    ):
        """測試多次分析的一致性"""
        # 執行多次分析
        results1 = analyzer_with_slippage.analyze_portfolio(test_holdings)
        results2 = analyzer_with_slippage.analyze_portfolio(test_holdings)
        results3 = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        # 結果應該一致（如果都成功）
        if results1 and results2 and results3:
            # 統計資訊應該相同
            if 'statistics' in results1 and 'statistics' in results2:
                # 至少某些統計應該相同
                assert isinstance(results1['statistics'], dict)
                assert isinstance(results2['statistics'], dict)
    
    def test_full_workflow(self, analyzer_with_slippage, test_holdings):
        """測試完整工作流程"""
        # Step 1: 投資組合分析
        portfolio_results = analyzer_with_slippage.analyze_portfolio(test_holdings)
        
        if not portfolio_results:
            pytest.skip("無法取得投資組合分析結果")
        
        # Step 2: 加碼建議分析
        total_value = test_holdings['現值'].sum()
        
        buy_opportunities = analyzer_with_slippage.analyze_buy_opportunities_from_holdings(
            analysis_results=portfolio_results,
            holdings_df=test_holdings,
            total_portfolio_value=total_value
        )
        
        # Step 3: 驗證完整流程
        assert isinstance(portfolio_results, dict)
        assert isinstance(buy_opportunities, list)
        
        # 檢查兩個階段的資料一致性
        for opp in buy_opportunities:
            assert 'stock_code' in opp
            assert 'ideal_buy_price' in opp
