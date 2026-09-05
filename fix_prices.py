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
  預設每輪 150 檔（平日）／300 檔（六日）（避免 Yahoo 限流）。亂序抓取，多輪全覆蓋。
  傳入批次上限可覆寫（2026-09-01：stock_update.py 平日 10:00 傳 300 加速全覆蓋，
  18:05 run_daily_advice.py 不傳維持預設，避免一天 600 檔觸發限流）。
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


def _batch_size(override: int | None = None) -> int:
    """六日（無開盤）加量補齊，平日維持小批防限流。

    2026-08-24：使用者要求六日也更新股票資訊。六日台股休市、全球流量低，
    Yahoo 限流風險小，放大到 300 檔加速全覆蓋；平日維持 150 檔防限流。
    2026-09-01：允許命令列覆寫（stock_update.py 平日 10:00 傳 300，
    18:05 run_daily_advice 不傳維持平日 150），避免 10:00+18:05 皆 300 觸發限流。
    """
    if override is not None:
        return override
    weekday = datetime.now().weekday()  # 0=一 ... 5=六, 6=日
    return 300 if weekday >= 5 else MAX_PER_RUN


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # ①優先補「目前無價格」的股票。ETF 類(005x/006x)優先，避免永遠被擠掉。
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

    batch = _batch_size(int(sys.argv[1]) if len(sys.argv) > 1 else None)
    codes = (etf_zero + other_zero)[:batch]

    # ②額度未滿 → 按 last_updated 最舊的補（維持全庫資料新鮮度，每日輪替更新）
    if len(codes) < batch:
        stale = [
            r[0]
            for r in cur.execute(
                "SELECT stock_code FROM market_snapshot "
                "WHERE (paused IS NOT 1 OR paused IS NULL) AND current_price > 0 "
                "ORDER BY last_updated ASC LIMIT ?",
                (batch - len(codes),),
            ).fetchall()
        ]
        codes += stale

    # ③全覆蓋保護：無檔可更新時優雅退出（避免 ZeroDivisionError，2026-08-24 修）
    if not codes:
        print("[DONE] 全量已覆蓋，本輪無需更新")
        conn.close()
        return

    print(f"本次：缺價 {len(etf_zero + other_zero)} 檔 + 補舊 {max(0, len(codes) - len(etf_zero + other_zero))} 檔 (共 {len(codes)} 檔)")

    updated = failed = delisted = 0
    for code in codes[:batch]:
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
