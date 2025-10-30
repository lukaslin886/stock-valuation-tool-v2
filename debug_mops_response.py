"""
調試 MOPS 回應內容
"""

import requests
from datetime import datetime

# MOPS 股本異動表 URL
BASE_URL = "https://mops.twse.com.tw"
url = f"{BASE_URL}/server-java/t05st10_ifrs"

# 當前日期
now = datetime.now()
minguo_year = now.year - 1911
month = now.month

params = {
    'step': '1',
    'TYPEK': 'sii',  # sii=上市
    'year': str(minguo_year),
    'month': f"{month:02d}",
    'firstin': '1'
}

print(f"查詢參數:")
print(f"  - 民國年: {minguo_year}")
print(f"  - 月份: {month:02d}")
print(f"  - URL: {url}")
print(f"  - Params: {params}")
print("\n" + "="*80)

try:
    response = requests.get(
        url,
        params=params,
        timeout=20,
        verify=False,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    )
    
    print(f"HTTP 狀態: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"內容長度: {len(response.content)} bytes")
    print("\n" + "="*80)
    
    # 處理編碼
    response.encoding = 'utf-8'
    content = response.content.decode('utf-8', errors='ignore')
    
    # 顯示前 2000 字元
    print("回應內容（前 2000 字元）:")
    print("="*80)
    print(content[:2000])
    print("="*80)
    
    # 檢查關鍵字
    keywords = ['公司代號', '普通股股數', '流通在外', 'table', 'TABLE']
    print("\n關鍵字檢查:")
    for keyword in keywords:
        count = content.count(keyword)
        print(f"  - '{keyword}': {count} 次")
    
    # 儲存完整內容到檔案
    output_file = f"mops_response_{minguo_year}_{month:02d}.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"\n✓ 完整回應已儲存到: {output_file}")
    
except Exception as e:
    print(f"✗ 請求失敗: {str(e)}")
    import traceback
    traceback.print_exc()
