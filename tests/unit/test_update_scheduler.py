"""Unit tests for automated data update scheduling."""

from unittest.mock import Mock

from app.update_scheduler import DataUpdateScheduler, SchedulerConfig


class TestDataUpdateScheduler:
    """Test APScheduler wrapper behavior."""

    def test_register_default_jobs(self) -> None:
        """Scheduler should register both daily and quarterly jobs."""
        scheduler_mock = Mock()
        scheduler_mock.get_jobs.return_value = []

        update_scheduler = DataUpdateScheduler(scheduler=scheduler_mock)
        update_scheduler._build_daily_price_trigger = Mock(return_value="daily-trigger")
        update_scheduler._build_quarterly_financial_trigger = Mock(return_value="quarterly-trigger")

        update_scheduler.register_default_jobs()

        assert scheduler_mock.add_job.call_count == 2
        first_call = scheduler_mock.add_job.call_args_list[0]
        second_call = scheduler_mock.add_job.call_args_list[1]
        assert first_call.kwargs["id"] == "daily_price_update"
        assert first_call.kwargs["trigger"] == "daily-trigger"
        assert second_call.kwargs["id"] == "quarterly_financial_update"
        assert second_call.kwargs["trigger"] == "quarterly-trigger"

    def test_run_daily_price_update(self) -> None:
        """Daily update should pass stock universe to the market scanner."""
        scheduler_mock = Mock()
        scheduler_mock.get_jobs.return_value = []
        scanner_mock = Mock()
        stock_list = [{"stock_id": "2330", "stock_name": "台積電"}]

        update_scheduler = DataUpdateScheduler(
            scheduler=scheduler_mock,
            market_scanner_factory=lambda: scanner_mock,
            stock_list_provider=lambda: stock_list,
        )

        processed = update_scheduler.run_daily_price_update()

        assert processed == 1
        scanner_mock.update_market_snapshot.assert_called_once_with(stock_list)

    def test_run_quarterly_financial_update(self) -> None:
        """Quarterly update should clear financial cache and refresh each stock."""
        scheduler_mock = Mock()
        scheduler_mock.get_jobs.return_value = []
        manager_mock = Mock()
        stock_list = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_code": "2317", "stock_name": "鴻海"},
        ]

        update_scheduler = DataUpdateScheduler(
            scheduler=scheduler_mock,
            data_manager_factory=lambda: manager_mock,
            stock_list_provider=lambda: stock_list,
            config=SchedulerConfig(financial_years=3),
        )

        processed = update_scheduler.run_quarterly_financial_update()

        assert processed == 2
        manager_mock.cache.clear_cache.assert_any_call(
            cache_type="financial",
            stock_code="2330",
        )
        manager_mock.cache.clear_cache.assert_any_call(
            cache_type="financial",
            stock_code="2317",
        )
        manager_mock.get_financial_data.assert_any_call("2330", years=3)
        manager_mock.get_financial_data.assert_any_call("2317", years=3)

    def test_default_stock_list_provider(self) -> None:
        """Default provider should normalize DataFrame columns into stock dictionaries."""
        import pandas as pd

        scheduler_mock = Mock()
        scheduler_mock.get_jobs.return_value = []
        manager_mock = Mock()
        manager_mock.get_all_stocks.return_value = pd.DataFrame(
            {
                "stock_id": ["2330", "2317"],
                "stock_name": ["台積電", "鴻海"],
            }
        )

        update_scheduler = DataUpdateScheduler(
            scheduler=scheduler_mock,
            data_manager_factory=lambda: manager_mock,
        )

        stock_list = update_scheduler._default_stock_list_provider()

        assert stock_list == [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2317", "stock_name": "鴻海"},
        ]