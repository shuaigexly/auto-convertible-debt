from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.base import SchedulerNotRunningError

from app.worker.main import (
    _adapter_pool,
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
        def __init__(self, session, dry_run=False, adapter_pool=None):
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


@pytest.mark.asyncio
async def test_warmup_stores_adapter_in_pool():
    """job_warmup 登录成功后应将适配器存入 _adapter_pool。"""
    _adapter_pool.clear()

    mock_adapter = AsyncMock()
    mock_adapter.healthcheck = AsyncMock(return_value=MagicMock(ok=True))
    mock_adapter.login = AsyncMock(return_value=True)
    mock_adapter.check_session = MagicMock(return_value=True)

    fake_account = MagicMock()
    fake_account.id = 99
    fake_account.broker = "mock"

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fake_account])))
        )
    )
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = True
        with patch("app.worker.main._get_session_factory", return_value=lambda: cm):
            with patch("app.worker.main._get_adapter", return_value=mock_adapter):
                with patch("app.worker.main._decrypt_creds", return_value={}):
                    await job_warmup()

    assert 99 in _adapter_pool
    assert _adapter_pool[99] is mock_adapter


@pytest.mark.asyncio
async def test_run_subscribe_reuses_pooled_adapter():
    """_run_subscribe 应复用 _adapter_pool 中已登录的适配器。"""
    from datetime import date

    mock_adapter = AsyncMock()
    mock_adapter.check_session = MagicMock(return_value=True)

    fake_account = MagicMock()
    fake_account.id = 42
    fake_account.broker = "mock"

    _adapter_pool[42] = mock_adapter

    session_mock = AsyncMock()
    # accounts query
    accounts_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fake_account]))))
    # snaps query
    snaps_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    session_mock.execute = AsyncMock(side_effect=[accounts_result, snaps_result])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=False)

    executor_mock = AsyncMock()
    executor_mock.run_all_accounts = AsyncMock()

    with patch("app.worker.main._get_session_factory", return_value=lambda: cm):
        with patch("app.worker.main.Executor", return_value=executor_mock):
            with patch("app.worker.main._get_adapter") as mock_get_adapter:
                from app.worker.main import _run_subscribe
                await _run_subscribe(date.today())
                # _get_adapter should NOT be called since pool has the adapter
                mock_get_adapter.assert_not_called()

    _adapter_pool.clear()


@pytest.mark.asyncio
async def test_job_reconcile_uses_pooled_adapter():
    """job_reconcile 应复用 _adapter_pool 中已登录的适配器，不重新创建。"""
    _adapter_pool.clear()

    mock_adapter = AsyncMock()
    mock_adapter.check_session = MagicMock(return_value=True)

    fake_account = MagicMock()
    fake_account.id = 77
    fake_account.broker = "mock"

    _adapter_pool[77] = mock_adapter

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fake_account])))
        )
    )
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_reconciler = AsyncMock()
    mock_reconciler.reconcile_account = AsyncMock()

    with patch("app.worker.main.calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = True
        with patch("app.worker.main._get_session_factory", return_value=lambda: cm):
            with patch("app.worker.main.Reconciler", return_value=mock_reconciler):
                with patch("app.worker.main._get_adapter") as mock_get_adapter:
                    await job_reconcile()
                    # _get_adapter should NOT be called since pool has the adapter
                    mock_get_adapter.assert_not_called()

    mock_reconciler.reconcile_account.assert_called_once()
    call_args = mock_reconciler.reconcile_account.call_args
    assert call_args[0][0] is fake_account
    assert call_args[0][1] is mock_adapter
    _adapter_pool.clear()
