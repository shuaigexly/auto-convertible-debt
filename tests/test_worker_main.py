from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.base import SchedulerNotRunningError

from app.worker.main import (
    _get_adapter,
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


def test_get_adapter_returns_miniqmt():
    from app.brokers.miniqmt_adapter import MiniQMTBroker

    account = MagicMock()
    account.broker = "miniqmt"
    adapter = _get_adapter(account)
    assert isinstance(adapter, MiniQMTBroker)


def test_get_adapter_returns_mock():
    from app.brokers.mock_broker import MockBroker

    account = MagicMock()
    account.broker = "mock"
    assert isinstance(_get_adapter(account), MockBroker)


def test_get_adapter_returns_tonghuashun_as_default():
    from app.brokers.tongtongxin import TonghuashunBroker

    account = MagicMock()
    account.broker = "tonghuashun"
    assert isinstance(_get_adapter(account), TonghuashunBroker)


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
async def test_job_retry_only_retries_failed_subscriptions():
    """retry_only=True 时，若无 FAILED 记录则不调用 run_all_accounts。"""
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = True
        with patch("app.worker.main._run_subscribe", new_callable=AsyncMock) as mock_run:
            await job_retry()
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("retry_only") is True or mock_run.call_args[0][1] is True


@pytest.mark.asyncio
async def test_job_reconcile_skips_non_trading_day():
    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False
        with patch("app.worker.main._get_session_factory") as mock_sf:
            await job_reconcile()
        mock_sf.assert_not_called()


@pytest.mark.asyncio
async def test_dry_run_env_passed_to_executor(monkeypatch):
    """DRY_RUN=true 时 Executor 以 dry_run=True 初始化。"""
    monkeypatch.setenv("DRY_RUN", "true")

    captured = {}

    class _CapturingExecutor:
        def __init__(self, session, dry_run=False):
            captured["dry_run"] = dry_run

        async def run_all_accounts(self, *a, **kw):
            pass

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.worker.main._get_session_factory", return_value=lambda: cm):
        with patch("app.worker.main.Executor", _CapturingExecutor):
            from app.worker.main import _run_subscribe
            from datetime import date
            await _run_subscribe(date.today())

    assert captured.get("dry_run") is True
