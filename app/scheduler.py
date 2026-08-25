"""Data update scheduler for automated market and financial refresh jobs."""

from __future__ import annotations

from datetime import datetime
from time import sleep
from typing import Any, Callable, Dict, List, Optional

import streamlit as st
from pydantic import BaseModel, Field

from app.data.manager import DataManagerV2
from app.market_scanner import MarketScanner

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # pragma: no cover
    BackgroundScheduler = None
    CronTrigger = None


class SchedulerConfig(BaseModel):
    """Configuration for automated data refresh jobs."""

    timezone: str = "Asia/Taipei"
    daily_price_hour: int = Field(default=18, ge=0, le=23)
    daily_price_minute: int = Field(default=0, ge=0, le=59)
    quarterly_financial_hour: int = Field(default=6, ge=0, le=23)
    quarterly_financial_minute: int = Field(default=0, ge=0, le=59)
    quarterly_months: str = "1,4,7,10"
    quarterly_day: int = Field(default=1, ge=1, le=31)
    financial_years: int = Field(default=5, ge=1, le=20)


class DataUpdateScheduler:
    """Wrap APScheduler for market price and financial cache refresh jobs."""

    def __init__(
        self,
        data_manager: Optional[DataManagerV2] = None,
        config: Optional[SchedulerConfig] = None,
        scheduler: Optional[Any] = None,
        market_scanner_factory: Optional[Callable[[], MarketScanner]] = None,
        stock_list_provider: Optional[Callable[[], List[Dict[str, str]]]] = None,
        data_manager_factory: Optional[Callable[[], DataManagerV2]] = None,
    ) -> None:
        """Initialize scheduler dependencies."""
        self.config = config or SchedulerConfig()
        if data_manager_factory is not None:
            self.data_manager = data_manager_factory()
        else:
            self.data_manager = data_manager or DataManagerV2()
        self._market_scanner_factory = market_scanner_factory or (lambda: MarketScanner())
        self._stock_list_provider = stock_list_provider or self._default_stock_list_provider

        if scheduler is not None:
            self.scheduler = scheduler
        elif BackgroundScheduler is None:
            self.scheduler = None
        else:
            self.scheduler = BackgroundScheduler(timezone=self.config.timezone)

    def register_default_jobs(self) -> None:
        """Register daily market price and quarterly financial refresh jobs."""
        if not self.scheduler:
            return
            
        self.scheduler.add_job(
            self.run_daily_price_update,
            trigger=self._build_daily_price_trigger(),
            id="daily_price_update",
            name="Daily Market Snapshot Update",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.run_quarterly_financial_update,
            trigger=self._build_quarterly_financial_trigger(),
            id="quarterly_financial_update",
            name="Quarterly Financial Cache Refresh",
            replace_existing=True,
        )

    def start_scheduler(self) -> bool:
        """Start the background scheduler."""
        if not self.scheduler:
            return False
        if not self.scheduler.running:
            self.scheduler.start()
        return True

    def stop_scheduler(self) -> bool:
        """Shutdown the background scheduler."""
        if not self.scheduler:
            return False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            # Re-initialize to allow restart later if needed
            self.scheduler = BackgroundScheduler(timezone=self.config.timezone)
            self.register_default_jobs()
        return True

    def get_all_jobs_status(self) -> List[Dict[str, str]]:
        """Return registered jobs in a format main.py expects."""
        if not self.scheduler:
            return []
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": str(job.next_run_time) if job.next_run_time else "None",
                }
            )
        return jobs

    def run_daily_price_update(self) -> int:
        """Refresh market snapshot."""
        stock_list = self._stock_list_provider()
        if not stock_list:
            return 0

        scanner = self._market_scanner_factory()
        scanner.update_market_snapshot(stock_list)
        return len(stock_list)

    def run_quarterly_financial_update(self) -> int:
        """Refresh financial cache."""
        stock_list = self._stock_list_provider()
        if not stock_list:
            return 0

        processed_count = 0
        for stock in stock_list:
            stock_code = stock.get("stock_id") or stock.get("stock_code")
            if not stock_code:
                continue

            self.data_manager.cache.clear_cache(cache_type="financial", stock_code=stock_code)
            self.data_manager.get_financial_data(stock_code, years=self.config.financial_years)
            processed_count += 1

        return processed_count

    def _build_daily_price_trigger(self) -> Any:
        return CronTrigger(
            hour=self.config.daily_price_hour,
            minute=self.config.daily_price_minute,
        )

    def _build_quarterly_financial_trigger(self) -> Any:
        return CronTrigger(
            month=self.config.quarterly_months,
            day=self.config.quarterly_day,
            hour=self.config.quarterly_financial_hour,
            minute=self.config.quarterly_financial_minute,
        )

    def _default_stock_list_provider(self) -> List[Dict[str, str]]:
        stocks_df = self.data_manager.get_all_stocks()
        if stocks_df is None or stocks_df.empty:
            return []

        stock_list = []
        for _, row in stocks_df.iterrows():
            stock_code = row.get("stock_id") or row.get("stock_code")
            stock_name = row.get("stock_name", "")
            if stock_code:
                stock_list.append({"stock_id": str(stock_code), "stock_name": str(stock_name)})
        return stock_list


def get_or_create_scheduler(data_manager: Optional[DataManagerV2] = None) -> DataUpdateScheduler:
    """獲取或建立全域排程器實例"""
    if 'data_scheduler' not in st.session_state:
        scheduler = DataUpdateScheduler(data_manager=data_manager)
        scheduler.register_default_jobs()
        # Note: We don't start it immediately, wait for user to toggle in UI
        st.session_state.data_scheduler = scheduler
    return st.session_state.data_scheduler
