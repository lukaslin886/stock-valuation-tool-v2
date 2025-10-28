"""
完整功能測試
"""

from app.data_manager import DataManager

print("=" * 60)
print("FinLab 整合測試")
print("=" * 60)

# 初始化
dm = DataManager()

print("\n=== 測試 1: 獲取財務數據（應使用 FinMind）===")
data = dm.get_financial_data('2330', years=2, force_update=True)
print(f"\n✓ 獲取到 {len(data)} 筆財務數據")
if len(data) > 0:
    print("\n前10筆數據:")
    print(data.head(10))
    print(f"\n欄位: {list(data.columns)}")
else:
    print("✗ 無法獲取財務數據")

print("\n" + "=" * 60)
print("測試完成")
print("=" * 60)

# 顯示資料源使用統計
print("\n資料源使用統計:")
for source, count in dm.data_source_stats.items():
    print(f"  {source}: {count}")
