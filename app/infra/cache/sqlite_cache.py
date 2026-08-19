"""SQLite Cache 模組。

提供 SQLite 持久化快取層，整合複合索引、參數化查詢、WAL 模式與連線池。
支援 market_snapshot、chip_data、trade_signals、paper_trades 四張資料表，
維持向下相容性（既有 SQLite 檔案可直接使用）。

核心特性：
    - WAL 模式：允許並行讀取，減少寫入鎖定
    - 連線池：check_same_thread=False + threading.Lock 保障執行緒安全
    - 複合索引：stock_code、last_updated、pe_ratio、roe、dividend_yield
    - 參數化查詢：SQL 層面過濾（非 Python 逐列過濾）
    - ANALYZE：寫入後更新查詢計畫統計
    - 30 天過期標記：查詢結果附帶 stale 警告
    - 向下相容：既有 SQLite 資料庫直接可用

Usage::

    from app.infra.cache.sqlite_cache import SQLiteCache

    cache = SQLiteCache("market_scan.db")
    results = cache.filter_stocks(pe_max=20, roe_min=10)
    cache.close()
"""

import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from app.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

_STALE_DAYS = 30
"""超過此天數未更新的記錄視為過期。"""

_ISO_FORMAT = "%Y-%m-%d %H:%M:%S"
"""SQLite 中日期時間欄位的格式。"""


# ---------------------------------------------------------------------------
# SQL Schema 定義
# ---------------------------------------------------------------------------

_CREATE_MARKET_SNAPSHOT_TABLE = """
CREATE TABLE IF NOT EXISTS market_snapshot (
    stock_code TEXT NOT NULL,
    stock_name TEXT DEFAULT '',
    current_price REAL DEFAULT 0,
    pe_ratio REAL DEFAULT 0,
    roe REAL DEFAULT 0,
    dividend_yield REAL DEFAULT 0,
    market_cap REAL DEFAULT 0,
    price_position REAL DEFAULT 0,
    fundamental_score REAL DEFAULT 0,
    fundamental_grade TEXT DEFAULT '',
    last_updated TEXT NOT NULL,
    PRIMARY KEY (stock_code)
);
"""

_CREATE_CHIP_DATA_TABLE = """
CREATE TABLE IF NOT EXISTS chip_data (
    stock_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    foreign_buy INTEGER DEFAULT 0,
    foreign_sell INTEGER DEFAULT 0,
    trust_buy INTEGER DEFAULT 0,
    trust_sell INTEGER DEFAULT 0,
    dealer_buy INTEGER DEFAULT 0,
    dealer_sell INTEGER DEFAULT 0,
    last_updated TEXT NOT NULL,
    PRIMARY KEY (stock_code, trade_date)
);
"""

_CREATE_TRADE_SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    trigger_description TEXT,
    suggested_price_low REAL,
    suggested_price_high REAL,
    generated_at TEXT NOT NULL,
    consumed_at TEXT,
    status TEXT DEFAULT 'pending'
);
"""

_CREATE_PAPER_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    signal_id INTEGER REFERENCES trade_signals(id),
    executed_at TEXT NOT NULL,
    notes TEXT
);
"""

_CREATE_INDEXES = [
    # market_snapshot 複合索引
    """CREATE INDEX IF NOT EXISTS idx_snapshot_filters
       ON market_snapshot(pe_ratio, roe, dividend_yield, last_updated);""",
    """CREATE INDEX IF NOT EXISTS idx_snapshot_code_updated
       ON market_snapshot(stock_code, last_updated);""",
    # chip_data 索引
    """CREATE INDEX IF NOT EXISTS idx_chip_stock_date
       ON chip_data(stock_code, trade_date DESC);""",
    # trade_signals 索引
    """CREATE INDEX IF NOT EXISTS idx_signals_status
       ON trade_signals(status, generated_at DESC);""",
    """CREATE INDEX IF NOT EXISTS idx_signals_stock
       ON trade_signals(stock_code, generated_at DESC);""",
    # paper_trades 索引
    """CREATE INDEX IF NOT EXISTS idx_paper_trades_stock
       ON paper_trades(stock_code, executed_at DESC);""",
]


# ---------------------------------------------------------------------------
# FilterResult 資料結構
# ---------------------------------------------------------------------------


class FilterResult:
    """篩選結果容器，附帶過期警告資訊。

    Attributes:
        rows: 查詢結果列表，每列為欄位名稱到值的字典。
        stale_codes: 超過 30 天未更新的股票代碼集合。
        has_stale: 是否包含過期記錄。
        warning: 過期警告訊息（若有過期記錄）。
    """

    def __init__(
        self,
        rows: List[Dict[str, Any]],
        stale_codes: Optional[List[str]] = None,
    ) -> None:
        """初始化 FilterResult。

        Args:
            rows: 查詢結果列表。
            stale_codes: 過期股票代碼列表。
        """
        self.rows = rows
        self.stale_codes = stale_codes or []
        self.has_stale = len(self.stale_codes) > 0
        self.warning: Optional[str] = None
        if self.has_stale:
            codes_str = ", ".join(self.stale_codes[:10])
            suffix = (
                f" ...等共 {len(self.stale_codes)} 檔"
                if len(self.stale_codes) > 10
                else ""
            )
            self.warning = (
                f"[STALE] 以下股票資料超過 {_STALE_DAYS} 天未更新，"
                f"可能已過時: {codes_str}{suffix}"
            )


# ---------------------------------------------------------------------------
# SQLiteCache 主類別
# ---------------------------------------------------------------------------


class SQLiteCache:
    """SQLite 持久化快取層。

    提供 market_snapshot、chip_data、trade_signals、paper_trades 資料表的
    讀寫操作，整合 WAL 模式、連線池、複合索引與參數化查詢。

    初始化時自動建立資料表與索引（IF NOT EXISTS），確保向下相容性。
    既有 SQLite 資料庫檔案可直接被新版系統讀取而無需遷移。

    Args:
        db_path: SQLite 資料庫檔案路徑，預設 "market_scan.db"。
        time_func: 時間函式，預設 time.time。可注入自訂函式以利測試。

    Example::

        cache = SQLiteCache("market_scan.db")
        result = cache.filter_stocks(pe_max=20, roe_min=10)
        if result.has_stale:
            print(result.warning)
        for row in result.rows:
            print(row["stock_code"], row["pe_ratio"])
        cache.close()
    """

    def __init__(
        self,
        db_path: str = "market_scan.db",
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化 SQLiteCache。

        建立連線、啟用 WAL 模式、建立資料表與索引。

        Args:
            db_path: SQLite 資料庫檔案路徑。
            time_func: 取得目前時間的函式（epoch seconds）。
        """
        self._db_path = db_path
        self._time_func = time_func
        self._lock = threading.Lock()
        self._closed = False

        # 建立連線（check_same_thread=False 允許跨執行緒使用）
        self._conn = self._create_connection()

        # 初始化 schema
        self._initialize_schema()

        logger.info(
            "SQLiteCache initialized: %s (WAL mode)",
            db_path,
        )

    # ------------------------------------------------------------------
    # 連線管理
    # ------------------------------------------------------------------

    def _create_connection(self) -> sqlite3.Connection:
        """建立 SQLite 連線並啟用 WAL 模式。

        Returns:
            已配置好的 sqlite3.Connection 實例。
        """
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        # 啟用 WAL 模式
        conn.execute("PRAGMA journal_mode=WAL;")
        # 啟用外來鍵約束
        conn.execute("PRAGMA foreign_keys=ON;")
        # 設定較短的 busy timeout 避免長時間阻塞
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    @contextmanager
    def _get_cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """取得帶鎖保護的 cursor。

        以 context manager 形式提供 cursor，自動 commit 或 rollback。

        Yields:
            sqlite3.Cursor 實例。

        Raises:
            RuntimeError: 快取已關閉時。
        """
        if self._closed:
            raise RuntimeError("SQLiteCache already closed")
        with self._lock:
            cursor = self._conn.cursor()
            try:
                yield cursor
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cursor.close()

    def _initialize_schema(self) -> None:
        """初始化資料表與索引。

        使用 IF NOT EXISTS 確保向下相容性，
        既有資料庫不會受到影響。
        """
        with self._get_cursor() as cursor:
            cursor.execute(_CREATE_MARKET_SNAPSHOT_TABLE)
            cursor.execute(_CREATE_CHIP_DATA_TABLE)
            cursor.execute(_CREATE_TRADE_SIGNALS_TABLE)
            cursor.execute(_CREATE_PAPER_TRADES_TABLE)
            for index_sql in _CREATE_INDEXES:
                cursor.execute(index_sql)

    def close(self) -> None:
        """關閉資料庫連線。

        關閉後任何操作將引發 RuntimeError。
        """
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True
                logger.info("SQLiteCache closed: %s", self._db_path)

    def __enter__(self) -> "SQLiteCache":
        """支援 context manager 用法。"""
        return self

    def __exit__(self, *args: Any) -> None:
        """離開 context manager 時自動關閉連線。"""
        self.close()

    # ------------------------------------------------------------------
    # Market Snapshot 操作
    # ------------------------------------------------------------------

    def filter_stocks(
        self,
        pe_min: Optional[float] = None,
        pe_max: Optional[float] = None,
        roe_min: Optional[float] = None,
        roe_max: Optional[float] = None,
        dividend_yield_min: Optional[float] = None,
        dividend_yield_max: Optional[float] = None,
        market_cap_min: Optional[float] = None,
        stock_codes: Optional[List[str]] = None,
        limit: int = 500,
    ) -> FilterResult:
        """使用參數化查詢篩選股票。

        在 SQL 層面執行多條件過濾，非 Python 逐列過濾。
        查詢結果會標記超過 30 天未更新的記錄為過期。

        Args:
            pe_min: 本益比下限（含）。
            pe_max: 本益比上限（含）。
            roe_min: ROE 下限（含）。
            roe_max: ROE 上限（含）。
            dividend_yield_min: 殖利率下限（含）。
            dividend_yield_max: 殖利率上限（含）。
            market_cap_min: 市值下限（億）（含）。
            stock_codes: 限定查詢的股票代碼列表。
            limit: 回傳筆數上限，預設 500。

        Returns:
            FilterResult 物件，包含查詢結果與過期警告。
        """
        conditions: List[str] = []
        params: List[Any] = []

        if pe_min is not None:
            conditions.append("pe_ratio >= ?")
            params.append(pe_min)
        if pe_max is not None:
            conditions.append("pe_ratio <= ?")
            params.append(pe_max)
        if roe_min is not None:
            conditions.append("roe >= ?")
            params.append(roe_min)
        if roe_max is not None:
            conditions.append("roe <= ?")
            params.append(roe_max)
        if dividend_yield_min is not None:
            conditions.append("dividend_yield >= ?")
            params.append(dividend_yield_min)
        if dividend_yield_max is not None:
            conditions.append("dividend_yield <= ?")
            params.append(dividend_yield_max)
        if market_cap_min is not None:
            conditions.append("market_cap >= ?")
            params.append(market_cap_min)
        if stock_codes:
            placeholders = ",".join("?" for _ in stock_codes)
            conditions.append(f"stock_code IN ({placeholders})")
            params.extend(stock_codes)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT stock_code, stock_name, current_price, pe_ratio,
                   roe, dividend_yield, market_cap, price_position,
                   fundamental_score, fundamental_grade, last_updated
            FROM market_snapshot
            {where_clause}
            ORDER BY fundamental_score DESC
            LIMIT ?
        """
        params.append(limit)

        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()

        # 轉換為字典列表並標記過期記錄
        rows: List[Dict[str, Any]] = []
        stale_codes: List[str] = []
        stale_threshold = self._get_stale_threshold()

        for raw_row in raw_rows:
            row_dict = dict(zip(columns, raw_row))
            last_updated_str = row_dict.get("last_updated", "")
            is_stale = self._check_stale(last_updated_str, stale_threshold)
            row_dict["stale"] = is_stale
            if is_stale:
                stale_codes.append(row_dict["stock_code"])
            rows.append(row_dict)

        return FilterResult(rows=rows, stale_codes=stale_codes)

    def upsert_snapshot(self, record: Dict[str, Any]) -> None:
        """寫入或更新單筆 market_snapshot 記錄。

        使用 INSERT OR REPLACE 實作 upsert 語意。

        Args:
            record: 包含 stock_code 與其他欄位的字典。
        """
        now_str = self._now_iso()
        sql = """
            INSERT OR REPLACE INTO market_snapshot
            (stock_code, stock_name, current_price, pe_ratio, roe,
             dividend_yield, market_cap, price_position,
             fundamental_score, fundamental_grade, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record.get("stock_code", ""),
            record.get("stock_name", ""),
            record.get("current_price", 0),
            record.get("pe_ratio", 0),
            record.get("roe", 0),
            record.get("dividend_yield", 0),
            record.get("market_cap", 0),
            record.get("price_position", 0),
            record.get("fundamental_score", 0),
            record.get("fundamental_grade", ""),
            record.get("last_updated", now_str),
        )
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)

    def bulk_upsert_snapshots(
        self, records: List[Dict[str, Any]]
    ) -> int:
        """批次寫入或更新 market_snapshot 記錄。

        寫入完成後自動執行 ANALYZE 更新查詢計畫統計。

        Args:
            records: 包含 stock_code 與其他欄位的字典列表。

        Returns:
            成功寫入的記錄數量。
        """
        if not records:
            return 0

        now_str = self._now_iso()
        sql = """
            INSERT OR REPLACE INTO market_snapshot
            (stock_code, stock_name, current_price, pe_ratio, roe,
             dividend_yield, market_cap, price_position,
             fundamental_score, fundamental_grade, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows_data = []
        for record in records:
            rows_data.append((
                record.get("stock_code", ""),
                record.get("stock_name", ""),
                record.get("current_price", 0),
                record.get("pe_ratio", 0),
                record.get("roe", 0),
                record.get("dividend_yield", 0),
                record.get("market_cap", 0),
                record.get("price_position", 0),
                record.get("fundamental_score", 0),
                record.get("fundamental_grade", ""),
                record.get("last_updated", now_str),
            ))

        with self._get_cursor() as cursor:
            cursor.executemany(sql, rows_data)
            count = cursor.rowcount

        # 寫入後執行 ANALYZE 更新查詢計畫統計
        self._run_analyze()

        logger.info(
            "bulk_upsert_snapshots: %d records written, ANALYZE executed",
            len(records),
        )
        return len(records)

    def get_snapshot(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """取得單支股票的 market_snapshot 記錄。

        Args:
            stock_code: 股票代碼。

        Returns:
            包含所有欄位的字典（含 stale 旗標），若不存在回傳 None。
        """
        sql = """
            SELECT stock_code, stock_name, current_price, pe_ratio,
                   roe, dividend_yield, market_cap, price_position,
                   fundamental_score, fundamental_grade, last_updated
            FROM market_snapshot
            WHERE stock_code = ?
        """
        with self._get_cursor() as cursor:
            cursor.execute(sql, (stock_code,))
            row = cursor.fetchone()

        if row is None:
            return None

        columns = [
            "stock_code", "stock_name", "current_price", "pe_ratio",
            "roe", "dividend_yield", "market_cap", "price_position",
            "fundamental_score", "fundamental_grade", "last_updated",
        ]
        row_dict = dict(zip(columns, row))
        stale_threshold = self._get_stale_threshold()
        row_dict["stale"] = self._check_stale(
            row_dict.get("last_updated", ""), stale_threshold
        )
        return row_dict

    def get_stale_stocks(self) -> List[str]:
        """取得所有超過 30 天未更新的股票代碼。

        Returns:
            過期的股票代碼列表。
        """
        threshold_str = self._get_stale_threshold_iso()
        sql = """
            SELECT stock_code FROM market_snapshot
            WHERE last_updated < ?
            ORDER BY last_updated ASC
        """
        with self._get_cursor() as cursor:
            cursor.execute(sql, (threshold_str,))
            rows = cursor.fetchall()
        return [row[0] for row in rows]

    def delete_snapshot(self, stock_code: str) -> bool:
        """刪除指定股票的 market_snapshot 記錄。

        Args:
            stock_code: 股票代碼。

        Returns:
            True 表示成功刪除，False 表示記錄不存在。
        """
        sql = "DELETE FROM market_snapshot WHERE stock_code = ?"
        with self._get_cursor() as cursor:
            cursor.execute(sql, (stock_code,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Chip Data 操作
    # ------------------------------------------------------------------

    def upsert_chip_data(self, record: Dict[str, Any]) -> None:
        """寫入或更新單筆籌碼資料。

        Args:
            record: 包含 stock_code、trade_date 與買賣超欄位的字典。
        """
        now_str = self._now_iso()
        sql = """
            INSERT OR REPLACE INTO chip_data
            (stock_code, trade_date, foreign_buy, foreign_sell,
             trust_buy, trust_sell, dealer_buy, dealer_sell, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record.get("stock_code", ""),
            record.get("trade_date", ""),
            record.get("foreign_buy", 0),
            record.get("foreign_sell", 0),
            record.get("trust_buy", 0),
            record.get("trust_sell", 0),
            record.get("dealer_buy", 0),
            record.get("dealer_sell", 0),
            record.get("last_updated", now_str),
        )
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)

    def bulk_upsert_chip_data(
        self, records: List[Dict[str, Any]]
    ) -> int:
        """批次寫入或更新籌碼資料。

        寫入完成後自動執行 ANALYZE 更新查詢計畫統計。

        Args:
            records: 籌碼資料字典列表。

        Returns:
            成功寫入的記錄數量。
        """
        if not records:
            return 0

        now_str = self._now_iso()
        sql = """
            INSERT OR REPLACE INTO chip_data
            (stock_code, trade_date, foreign_buy, foreign_sell,
             trust_buy, trust_sell, dealer_buy, dealer_sell, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows_data = []
        for record in records:
            rows_data.append((
                record.get("stock_code", ""),
                record.get("trade_date", ""),
                record.get("foreign_buy", 0),
                record.get("foreign_sell", 0),
                record.get("trust_buy", 0),
                record.get("trust_sell", 0),
                record.get("dealer_buy", 0),
                record.get("dealer_sell", 0),
                record.get("last_updated", now_str),
            ))

        with self._get_cursor() as cursor:
            cursor.executemany(sql, rows_data)

        self._run_analyze()
        logger.info(
            "bulk_upsert_chip_data: %d records written", len(records)
        )
        return len(records)

    def get_chip_data(
        self,
        stock_code: str,
        days: int = 60,
    ) -> List[Dict[str, Any]]:
        """取得指定股票近 N 天的籌碼資料。

        Args:
            stock_code: 股票代碼。
            days: 回溯天數，預設 60 天。

        Returns:
            按交易日期降序排列的籌碼資料列表。
        """
        sql = """
            SELECT stock_code, trade_date, foreign_buy, foreign_sell,
                   trust_buy, trust_sell, dealer_buy, dealer_sell,
                   last_updated
            FROM chip_data
            WHERE stock_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
        """
        with self._get_cursor() as cursor:
            cursor.execute(sql, (stock_code, days))
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    # ------------------------------------------------------------------
    # Trade Signals 操作
    # ------------------------------------------------------------------

    def insert_signal(self, signal: Dict[str, Any]) -> int:
        """新增交易訊號。

        Args:
            signal: 包含訊號欄位的字典。

        Returns:
            新增記錄的 id。
        """
        sql = """
            INSERT INTO trade_signals
            (stock_code, signal_type, confidence, trigger_description,
             suggested_price_low, suggested_price_high, generated_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            signal.get("stock_code", ""),
            signal.get("signal_type", "hold"),
            signal.get("confidence", 0),
            signal.get("trigger_description", ""),
            signal.get("suggested_price_low"),
            signal.get("suggested_price_high"),
            signal.get("generated_at", self._now_iso()),
            signal.get("status", "pending"),
        )
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid or 0

    def get_pending_signals(
        self, stock_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """取得待處理的交易訊號。

        Args:
            stock_code: 限定特定股票代碼（可選）。

        Returns:
            待處理訊號的列表（按產生時間降序）。
        """
        if stock_code:
            sql = """
                SELECT id, stock_code, signal_type, confidence,
                       trigger_description, suggested_price_low,
                       suggested_price_high, generated_at, status
                FROM trade_signals
                WHERE status = 'pending' AND stock_code = ?
                ORDER BY generated_at DESC
            """
            params: Tuple[Any, ...] = (stock_code,)
        else:
            sql = """
                SELECT id, stock_code, signal_type, confidence,
                       trigger_description, suggested_price_low,
                       suggested_price_high, generated_at, status
                FROM trade_signals
                WHERE status = 'pending'
                ORDER BY generated_at DESC
            """
            params = ()

        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    def consume_signal(self, signal_id: int) -> bool:
        """將訊號標記為已消費。

        Args:
            signal_id: 訊號 ID。

        Returns:
            True 表示成功，False 表示訊號不存在或已消費。
        """
        now_str = self._now_iso()
        sql = """
            UPDATE trade_signals
            SET status = 'consumed', consumed_at = ?
            WHERE id = ? AND status = 'pending'
        """
        with self._get_cursor() as cursor:
            cursor.execute(sql, (now_str, signal_id))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Paper Trades 操作
    # ------------------------------------------------------------------

    def insert_paper_trade(self, trade: Dict[str, Any]) -> int:
        """新增模擬交易記錄。

        Args:
            trade: 包含交易欄位的字典。

        Returns:
            新增記錄的 id。
        """
        sql = """
            INSERT INTO paper_trades
            (stock_code, action, quantity, price, signal_id,
             executed_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            trade.get("stock_code", ""),
            trade.get("action", "buy"),
            trade.get("quantity", 0),
            trade.get("price", 0),
            trade.get("signal_id"),
            trade.get("executed_at", self._now_iso()),
            trade.get("notes"),
        )
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid or 0

    def get_paper_trades(
        self, stock_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """取得模擬交易記錄。

        Args:
            stock_code: 限定特定股票代碼（可選）。

        Returns:
            交易記錄列表（按執行時間降序）。
        """
        if stock_code:
            sql = """
                SELECT id, stock_code, action, quantity, price,
                       signal_id, executed_at, notes
                FROM paper_trades
                WHERE stock_code = ?
                ORDER BY executed_at DESC
            """
            params: Tuple[Any, ...] = (stock_code,)
        else:
            sql = """
                SELECT id, stock_code, action, quantity, price,
                       signal_id, executed_at, notes
                FROM paper_trades
                ORDER BY executed_at DESC
            """
            params = ()

        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    # ------------------------------------------------------------------
    # CacheProtocol 相容介面
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """依鍵值取得快取條目（CacheProtocol 相容）。

        此方法將 key 解讀為 stock_code，查詢 market_snapshot。

        Args:
            key: 快取鍵值（stock_code）。

        Returns:
            market_snapshot 記錄字典，若不存在回傳 None。
        """
        return self.get_snapshot(key)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """設定快取條目（CacheProtocol 相容）。

        此方法將 value 解讀為 market_snapshot 記錄字典並寫入。

        Args:
            key: 快取鍵值（stock_code）。
            value: market_snapshot 記錄字典。
            ttl: 未使用（SQLite 快取使用 last_updated 管理過期）。
        """
        if isinstance(value, dict):
            record = dict(value)
            record.setdefault("stock_code", key)
            self.upsert_snapshot(record)

    def delete(self, key: str) -> None:
        """刪除快取條目（CacheProtocol 相容）。

        Args:
            key: 快取鍵值（stock_code）。
        """
        self.delete_snapshot(key)

    def invalidate_prefix(self, prefix: str) -> int:
        """批次失效具有特定前綴的快取條目（CacheProtocol 相容）。

        刪除 stock_code 以 prefix 開頭的所有 market_snapshot 記錄。

        Args:
            prefix: stock_code 前綴。

        Returns:
            被刪除的記錄數量。
        """
        sql = "DELETE FROM market_snapshot WHERE stock_code LIKE ?"
        pattern = f"{prefix}%"
        with self._get_cursor() as cursor:
            cursor.execute(sql, (pattern,))
            return cursor.rowcount

    def stats(self) -> Dict[str, int]:
        """取得快取統計資訊（CacheProtocol 相容）。

        Returns:
            包含 total_snapshots、stale_count、total_signals、
            total_paper_trades 的字典。
        """
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM market_snapshot"
            )
            total_snapshots = cursor.fetchone()[0]

            threshold_str = self._get_stale_threshold_iso()
            cursor.execute(
                "SELECT COUNT(*) FROM market_snapshot WHERE last_updated < ?",
                (threshold_str,),
            )
            stale_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM trade_signals")
            total_signals = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM paper_trades")
            total_paper_trades = cursor.fetchone()[0]

        return {
            "total_snapshots": total_snapshots,
            "stale_count": stale_count,
            "total_signals": total_signals,
            "total_paper_trades": total_paper_trades,
        }

    # ------------------------------------------------------------------
    # 內部輔助方法
    # ------------------------------------------------------------------

    def _run_analyze(self) -> None:
        """執行 ANALYZE 更新 SQLite 查詢計畫統計資訊。

        此方法在批次寫入後呼叫，確保查詢最佳化器有最新統計。
        """
        with self._lock:
            try:
                self._conn.execute("ANALYZE;")
                self._conn.commit()
            except sqlite3.Error as e:
                logger.warning("ANALYZE failed: %s", str(e))

    def _now_iso(self) -> str:
        """取得目前時間的 ISO 格式字串。

        Returns:
            格式為 "YYYY-MM-DD HH:MM:SS" 的時間字串。
        """
        dt = datetime.fromtimestamp(self._time_func(), tz=timezone.utc)
        return dt.strftime(_ISO_FORMAT)

    def _get_stale_threshold(self) -> float:
        """取得過期判斷的時間門檻值（epoch seconds）。

        Returns:
            30 天前的 epoch timestamp。
        """
        return self._time_func() - (_STALE_DAYS * 24 * 3600)

    def _get_stale_threshold_iso(self) -> str:
        """取得過期判斷的 ISO 格式時間門檻。

        Returns:
            30 天前的 ISO 格式時間字串。
        """
        threshold_ts = self._get_stale_threshold()
        dt = datetime.fromtimestamp(threshold_ts, tz=timezone.utc)
        return dt.strftime(_ISO_FORMAT)

    def _check_stale(
        self, last_updated_str: str, stale_threshold: float
    ) -> bool:
        """檢查記錄是否已過期。

        Args:
            last_updated_str: last_updated 欄位的 ISO 格式字串。
            stale_threshold: 過期門檻的 epoch timestamp。

        Returns:
            True 表示已過期（超過 30 天未更新）。
        """
        if not last_updated_str:
            return True
        try:
            dt = datetime.strptime(last_updated_str, _ISO_FORMAT)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp() < stale_threshold
        except (ValueError, TypeError):
            # 無法解析的日期視為過期
            return True
