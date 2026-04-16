from contextlib import suppress
from unittest.mock import patch

import pytest
from apscheduler.schedulers.base import SchedulerNotRunningError

from app.worker.main import (
    create_scheduler,
    job_reconcile,
    job_retry,
    job_snapshot,
    job_subscribe,
    job_warmup,
)


def test_create_scheduler_has_expected_jobs():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}

    assert job_ids == {
        "snapshot",
        "warmup",
        "subscribe",
        "retry_1",
        "retry_2",
        "reconcile",
    }

    with suppress(SchedulerNotRunningError):
        scheduler.shutdown()


@pytest.mark.asyncio
async def test_job_snapshot_skips_non_trading_day():
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False
        with patch("app.worker.main._get_session_factory") as mock_sf:
            await job_snapshot()
        mock_sf.assert_not_called()


@pytest.mark.asyncio
async def test_job_warmup_skips_non_trading_day():
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False
        with patch("app.worker.main._get_session_factory") as mock_sf:
            await job_warmup()
        mock_sf.assert_not_called()


@pytest.mark.asyncio
async def test_job_subscribe_skips_non_trading_day():
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False
        with patch("app.worker.main._get_session_factory") as mock_sf:
            await job_subscribe()
        mock_sf.assert_not_called()


@pytest.mark.asyncio
async def test_job_retry_skips_non_trading_day():
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False
        with patch("app.worker.main._get_session_factory") as mock_sf:
            await job_retry()
        mock_sf.assert_not_called()


@pytest.mark.asyncio
async def test_job_reconcile_skips_non_trading_day():
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False
        with patch("app.worker.main._get_session_factory") as mock_sf:
            await job_reconcile()
        mock_sf.assert_not_called()
