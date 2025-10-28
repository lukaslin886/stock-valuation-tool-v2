"""
清除快取
"""

from app.data import DataManager
import os

# 清除 SQLite 快取
cache_file = "data/cache.db"
if os.path.exists(cache_file):
    os.remove(cache_file)
    print(f"✓ 已刪除 {cache_file}")
else:
    print(f"  {cache_file} 不存在")

print("快取已清除")
