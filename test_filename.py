"""測試投資建議簡稱轉換功能"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def get_recommendation_short_name(recommendation: str) -> str:
    """
    將投資建議轉換為簡短名稱，用於檔案命名
    
    Args:
        recommendation: 完整的投資建議文字
        
    Returns:
        簡短的投資建議名稱
    """
    # 注意：必須先檢查「不推薦」和「不建議」，避免被「推薦」子字串誤判
    if "不推薦" in recommendation or "不建議" in recommendation:
        return "不建議"
    elif "強烈推薦" in recommendation:
        return "強烈推薦"
    elif "推薦" in recommendation:
        return "推薦買入"
    elif "考慮" in recommendation:
        return "可考慮"
    else:
        return "不建議"

print("測試投資建議轉換：")
print("-" * 50)

test_cases = [
    "強烈推薦買入，目前價格被嚴重低估",
    "推薦買入，有一定的投資價值",
    "可考慮，但需密切關注",
    "不推薦 - 可能被高估",  # 新增：測試「不推薦」案例
    "不建議投資，風險過高"
]

for case in test_cases:
    short_name = get_recommendation_short_name(case)
    print(f"{case[:20]:20s} -> {short_name}")

print("-" * 50)
print("✓ 功能測試完成")

# 模擬檔案名稱
stock_code = "2330"
stock_name = "台積電"
date = "20251028"

print("\n檔案名稱範例：")
print("-" * 50)
for case in test_cases:
    short_name = get_recommendation_short_name(case)
    filename = f"{stock_code}_{stock_name}_{short_name}_{date}"
    print(f"PDF: {filename}.pdf")
    print(f"Excel: {filename}.xlsx")
    print()
