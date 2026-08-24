"""fix_prices.py — 分批亂序更新股價（修復版 2026-08-22）

原本問題：
  1. suffix 誤判：`startswith('00')` 把 ETF(0050) 誤判成 .TWO → 404 → 永遠 0
  2. DB 路徑硬編碼相對路徑 `app/data/`，依賴 cwd（跨機陷阱，鐵則 8）
  3. 下市股每次重試浪費額度

修復：
  1. 正確 suffix：先試 .TW，失敗再試 .TWO（ETF/上市/上櫃都覆蓋）
  2. 跨機路徑：用 _onedrive_root() 解析 DB
  3. 只寫有效值（price > 0 才 UPDATE），下市股標記 deleted→跳過

用法：python fix_prices.py [批次上限]
  預設每輪 150 檔（避免 Yahoo 限流）。亂序抓取，多輪全覆蓋。
"""
import os
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import requests


def _onedrive_root() -> Path:
    """跨機 OneDrive 根目錄解析 (5070Ti=E:, ACER=D:; 鐵則 8)"""
    for v in ("ONEDRIVE", "ONEDRIVECONSUMER"):
        p = os.environ.get(v)
        if p and Path(p).exists():
            return Path(p)
    for d in "CDEFGH":
        if Path(f"{d}:\\OneDrive").exists():
            return Path(f"{d}:\\OneDrive")
    raise RuntimeError("OneDrive 根目錄未找到")


# 定位到 stock-valuation-tool 目錄（腳本所在），DB 用絕對路徑
SCRIPT_DIR = _onedrive_root() / "CLINE_PROJECT" / "projects" / "Finance" / "stock-valuation-tool"
DB_PATH = SCRIPT_DIR / "app" / "data" / "market_scan.db"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_PER_RUN = 150  # 每日小批，防限流（測試可覆寫此值）
REQUEST_TIMEOUT = 5


def fetch_price(code: str):
    """抓股價：先 .TW 後 .TWO fallback。回傳價格或 None。返回 (price, suffix)。"""
    for suffix in (".TW", ".TWO"):
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{suffix}",
                headers=HEADERS, timeout=REQUEST_TIMEOUT,
            )
            if r.status_code == 200:
                meta = r.json()["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                if price and price > 0:
                    return price, suffix
        except Exception:
            pass
    return None, None


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 優先補「目前無價格」的股票。ETF 類(005x/006x)優先，避免永遠被擠掉。
    # ETF 是使用者最常看的，每輪必抓；其餘 0 檔亂序補。
    etf_zero = [
        r[0]
        for r in cur.execute(
            "SELECT stock_code FROM market_snapshot "
            "WHERE (paused IS NOT 1 OR paused IS NULL) AND current_price <= 0 "
            "AND (stock_code LIKE '005%' OR stock_code LIKE '006%')"
        ).fetchall()
    ]
    other_zero = [
        r[0]
        for r in cur.execute(
            "SELECT stock_code FROM market_snapshot "
            "WHERE (paused IS NOT 1 OR paused IS NULL) AND current_price <= 0 "
            "AND NOT (stock_code LIKE '005%' OR stock_code LIKE '006%')"
        ).fetchall()
    ]
    random.shuffle(etf_zero)
    random.shuffle(other_zero)
    # ETF 全抓 + 其他 0 檔補到 MAX_PER_RUN
    codes = etf_zero + other_zero[: max(0, MAX_PER_RUN - len(etf_zero))]
    print(f"本次：ETF優先 {len(etf_zero)} 檔 + 其他0檔 {len(codes) - len(etf_zero)} 檔 (共 {len(codes)} 檔)")

    updated = failed = delisted = 0
    for code in codes[:MAX_PER_RUN]:
        try:
            price, suffix = fetch_price(code)
            if price:
                cur.execute(
                    "UPDATE market_snapshot SET current_price = ?, last_updated = ? WHERE stock_code = ?",
                    (price, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), code),
                )
                updated += 1
            else:
                # 兩者都失敗：可能下市，標記 paused 避免每次重試
                cur.execute(
                    "UPDATE market_snapshot SET paused = 1 WHERE stock_code = ? AND current_price <= 0",
                    (code,),
                )
                delisted += 1
        except Exception:
            failed += 1

        if updated % 50 == 0 and updated > 0:
            conn.commit()

    conn.commit()
    conn.close()
    print(
        f"[DONE] 本次成功 {updated} 檔，失敗/無資料 {failed + delisted} 檔"
        f"（累計嘗試率 {(updated + failed + delisted) / len(codes) * 100:.0f}%）"
    )
    print(f"      已標記 {delisted} 檔為暫停（可能下市/無資料）")


if __name__ == "__main__":
    main()
