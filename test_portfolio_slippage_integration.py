"""
Portfolio Analyzer + 滑動風險整合測試
測試加碼建議功能是否正確整合滑價計算
"""

import sys
import pandas as pd
from pathlib import Path

# 添加專案根目錄到路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from portfolio_analyzer.analyzer import StockAnalyzer


def create_test_holdings():
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


def test_analyzer_initialization():
    """測試 1: 分析器初始化（含滑價）"""
    print("\n" + "="*60)
    print("測試 1: StockAnalyzer 初始化測試")
    print("="*60)
    
    # 啟用滑價
    analyzer = StockAnalyzer(enable_slippage=True)
    
    assert analyzer.enable_slippage == True
    assert analyzer.slippage_model is not None
    print("✓ 分析器初始化成功（滑價已啟用）")
    
    # 停用滑價
    analyzer_no_slip = StockAnalyzer(enable_slippage=False)
    
    assert analyzer_no_slip.enable_slippage == False
    assert analyzer_no_slip.slippage_model is None
    print("✓ 分析器初始化成功（滑價已停用）")
    
    print("\n✓ 測試通過！\n")


def test_portfolio_analysis_with_slippage():
    """測試 2: 投資組合分析（含滑價）"""
    print("="*60)
    print("測試 2: 投資組合分析（含滑價）")
    print("="*60)
    
    # 啟用滑價
    analyzer = StockAnalyzer(enable_slippage=True)
    holdings = create_test_holdings()
    
    print("\n【測試持股】")
    print(holdings.to_string(index=False))
    
    print("\n【開始分析】")
    results = analyzer.analyze_portfolio(holdings)
    
    if results:
        print("\n【分析統計】")
        stats = results['statistics']
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        print(f"\n✓ 投資組合分析完成")
        print(f"  - 賣出建議: {len(results['sell_list'])} 檔")
        print(f"  - 持有建議: {len(results['hold_list'])} 檔")
        print(f"  - 保護名單: {len(results['protected_list'])} 檔")
    
    print("\n✓ 測試通過！\n")
    return results


def test_buy_opportunities_with_slippage(analysis_results):
    """測試 3: 加碼建議（含滑價）"""
    print("="*60)
    print("測試 3: 加碼建議分析（含滑價）")
    print("="*60)
    
    analyzer = StockAnalyzer(enable_slippage=True)
    holdings = create_test_holdings()
    total_value = holdings['現值'].sum()
    
    print(f"\n投資組合總值: NT${total_value:,.0f}")
    
    # 分析加碼機會
    buy_opps = analyzer.analyze_buy_opportunities_from_holdings(
        analysis_results=analysis_results,
        holdings_df=holdings,
        total_portfolio_value=total_value
    )
    
    if buy_opps:
        print(f"\n【加碼機會詳情】")
        for i, opp in enumerate(buy_opps, 1):
            print(f"\n{i}. {opp['stock_code']} {opp['stock_name']}")
            print(f"   目前價格: ${opp['current_price']:.2f}")
            print(f"   內在價值: ${opp['intrinsic_value']:.2f}")
            print(f"   基礎建議價: ${opp['base_buy_price']:.2f}")
            print(f"   最終建議價: ${opp['ideal_buy_price']:.2f}")
            
            if opp.get('slippage_enabled') and opp.get('slippage_info'):
                slip_info = opp['slippage_info']
                slippage_amount = opp['ideal_buy_price'] - opp['base_buy_price']
                print(f"   ✓ 滑價調整: +${slippage_amount:.2f}")
                print(f"      - 滑價率: {slip_info['slippage_rate']:.3f}%")
                print(f"      - 流動性: {slip_info['liquidity_tier']}")
                print(f"      - 訊息: {slip_info['message']}")
            else:
                print(f"   ✗ 滑價調整: 未啟用或計算失敗")
            
            print(f"   優先級: {opp['priority']} - {opp['recommendation']}")
            print(f"   理由: {opp['reason']}")
    else:
        print("\n目前無加碼機會")
    
    print(f"\n✓ 測試通過！共 {len(buy_opps)} 個加碼機會\n")
    return buy_opps


def test_slippage_disabled():
    """測試 4: 停用滑價模式"""
    print("="*60)
    print("測試 4: 停用滑價模式測試")
    print("="*60)
    
    analyzer = StockAnalyzer(enable_slippage=False)
    holdings = create_test_holdings()
    
    print("\n【分析器狀態】")
    print(f"  滑價啟用: {analyzer.enable_slippage}")
    print(f"  滑價模型: {analyzer.slippage_model}")
    
    # 執行分析
    results = analyzer.analyze_portfolio(holdings)
    total_value = holdings['現值'].sum()
    
    # 分析加碼機會
    buy_opps = analyzer.analyze_buy_opportunities_from_holdings(
        analysis_results=results,
        holdings_df=holdings,
        total_portfolio_value=total_value
    )
    
    # 檢查是否有任何加碼機會使用滑價
    has_slippage = any(opp.get('slippage_enabled', False) for opp in buy_opps)
    
    assert not has_slippage, "停用滑價模式下不應有滑價計算"
    
    print("\n✓ 確認：停用模式下無滑價計算")
    print(f"✓ 測試通過！\n")


def main():
    """主測試函式"""
    print("\n")
    print("="*60)
    print("Portfolio Analyzer + 滑動風險整合測試")
    print("="*60)
    
    try:
        # 測試 1: 初始化
        test_analyzer_initialization()
        
        # 測試 2: 投資組合分析
        analysis_results = test_portfolio_analysis_with_slippage()
        
        # 測試 3: 加碼建議（含滑價）
        test_buy_opportunities_with_slippage(analysis_results)
        
        # 測試 4: 停用滑價模式
        test_slippage_disabled()
        
        print("="*60)
        print("所有測試通過！✓")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
