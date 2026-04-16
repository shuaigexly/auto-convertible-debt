"""APScheduler worker — orchestrates daily bond subscription pipeline."""

import asyncio
import json
import logging
import os
import signal
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.brokers.base import BrokerAdapter
from app.brokers.miniqmt_adapter import MiniQMTBroker
from app.brokers.mock_broker import MockBroker
from app.brokers.tongtongxin import TonghuashunBroker
from app.calendar_service import CalendarService
from app.data_sources.aggregator import BondAggregator
from app.data_sources.akshare_source import AKShareSource
from app.data_sources.base import BondInfo
from app.data_sources.manual_source import ManualSource
from app.data_sources.scraper import EastMoneySource, JisiluSource
from app.notifier.base import NotifyMessage
from app.notifier.dispatcher import notify
from app.shared.crypto import decrypt, get_keys_from_env
from app.shared.db import _get_engine, _get_session_factory
from app.shared.models import Account, BondSnapshot, Subscription, SubscriptionStatus
from app.worker.executor import Executor, MAX_RETRIES
from app.worker.reconciler import Reconciler

logger = logging.getLogger(__name__)
calendar = CalendarService()
_TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# Module-level adapter pool: account_id → logged-in BrokerAdapter
# Populated by job_warmup; consumed by _run_subscribe.
_adapter_pool: dict[int, BrokerAdapter] = {}


def _get_adapter(account: Account) -> BrokerAdapter:
    if account.broker == "mock":
        return MockBroker()
    if account.broker == "miniqmt":
        return MiniQMTBroker()
    if account.broker == "tonghuashun":
        return TonghuashunBroker()
    raise ValueError(f"Unknown broker: {account.broker!r} for account {account.id}")


def _decrypt_creds(account: Account) -> dict:
    primary_key, old_key = get_keys_from_env()
    plaintext = decrypt(account.credentials_enc, primary_key, old_key)
    return json.loads(plaintext)


async def job_snapshot() -> None:
    today = datetime.now(_TZ_SHANGHAI).date()
    if not calendar.is_trading_day(today):
        logger.info("job_snapshot: %s is not a trading day, skip", today)
        return
    async with _get_session_factory()() as session:
        sources = [
            AKShareSource(),
            EastMoneySource(),
            JisiluSource(),
            ManualSource(session),
        ]
        agg = BondAggregator(sources)
        confirmed, pending = await agg.aggregate(today)
        saved = 0
        for bond, is_confirmed in [(b, True) for b in confirmed] + [(b, False) for b in pending]:
            # Check-before-insert to handle idempotent double-triggers.
            existing = await session.execute(
                select(BondSnapshot).where(
                    BondSnapshot.trade_date == today,
                    BondSnapshot.bond_code == bond.bond_code,
                    BondSnapshot.source == bond.source,
                )
            )
            existing_snap = existing.scalars().first()
            if existing_snap is not None:
                if not existing_snap.confirmed and is_confirmed:
                    existing_snap.confirmed = True
                    existing_snap.bond_name = bond.bond_name or existing_snap.bond_name
                    existing_snap.market = bond.market or existing_snap.market
                    saved += 1
                continue
            snap = BondSnapshot(
                trade_date=today,
                bond_code=bond.bond_code,
                bond_name=bond.bond_name,
                market=bond.market,
                source=bond.source,
                confirmed=is_confirmed,
            )
            session.add(snap)
            saved += 1
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning("job_snapshot: IntegrityError on commit (concurrent run?), rolled back")
            return
    logger.info(
        "job_snapshot: saved %d new records (%d confirmed, %d pending)",
        saved, len(confirmed), len(pending),
    )


async def job_warmup() -> None:
    today = datetime.now(_TZ_SHANGHAI).date()
    if not calendar.is_trading_day(today):
        logger.info("job_warmup: %s is not a trading day, skip", today)
        return
    async with _get_session_factory()() as session:
        result = await session.execute(select(Account).where(Account.enabled.is_(True)))
        accounts = result.scalars().all()
        for account in accounts:
            try:
                adapter = _get_adapter(account)
                health = await adapter.healthcheck()
                if not health.ok:
                    logger.warning(
                        "job_warmup: account %s broker unhealthy: %s",
                        account.id,
                        health.message,
                    )
                    continue
                creds = _decrypt_creds(account)
                ok = await adapter.login(creds)
                if not ok:
                    logger.warning("job_warmup: login failed for account %s", account.id)
                    await notify(NotifyMessage(
                        title=f"登录失败: 账户 {account.id}",
                        body=f"job_warmup 账户 {account.id} ({account.broker}) 登录失败",
                        level="warning",
                    ))
                    continue
                _adapter_pool[account.id] = adapter
                logger.info("job_warmup: account %s logged in and pooled", account.id)
            except Exception as exc:
                logger.exception("job_warmup: failed for account %s: %s", account.id, exc)
                continue


async def _run_subscribe(trade_date: date, retry_only: bool = False) -> None:
    """Inner subscribe logic. retry_only=True 时只重试 FAILED+retryable 委托。"""
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    async with _get_session_factory()() as session:
        result = await session.execute(select(Account).where(Account.enabled.is_(True)))
        accounts = result.scalars().all()

        # Reuse pooled adapters from warmup; fall back to fresh login if missing.
        adapters: dict[int, BrokerAdapter] = {}
        for a in accounts:
            adapter = _adapter_pool.get(a.id)
            if adapter is None or not adapter.check_session():
                try:
                    adapter = _get_adapter(a)
                except ValueError as exc:
                    logger.error(
                        "_run_subscribe: unknown broker for account %s: %s", a.id, exc
                    )
                    continue
                try:
                    creds = _decrypt_creds(a)
                except Exception as exc:
                    logger.error(
                        "_run_subscribe: failed to decrypt credentials for account %s: %s",
                        a.id,
                        exc,
                    )
                    continue
                ok = await adapter.login(creds)
                if ok:
                    _adapter_pool[a.id] = adapter
                    logger.info("_run_subscribe: re-logged in account %s", a.id)
                else:
                    logger.warning("_run_subscribe: login failed for account %s, skipping", a.id)
                    continue
            adapters[a.id] = adapter

        snaps_result = await session.execute(
            select(BondSnapshot).where(
                BondSnapshot.trade_date == trade_date,
                BondSnapshot.confirmed.is_(True),
            )
        )
        snaps = snaps_result.scalars().all()

        if retry_only:
            # 只保留本日有 FAILED 且 retryable 记录的债券代码
            failed_result = await session.execute(
                select(Subscription.bond_code).where(
                    Subscription.trade_date == trade_date,
                    Subscription.status == SubscriptionStatus.FAILED,
                    Subscription.retry_count < MAX_RETRIES,
                ).distinct()
            )
            retryable_codes = {row[0] for row in failed_result.all()}
            snaps = [s for s in snaps if s.bond_code in retryable_codes]
            if not snaps:
                logger.info("job_retry: no retryable failed subscriptions for %s", trade_date)
                return

        bonds = [
            BondInfo(
                bond_code=s.bond_code,
                bond_name=s.bond_name or "",
                market=s.market or "SZ",
                trade_date=trade_date,
                source=s.source or "akshare",
            )
            for s in snaps
        ]
        executor = Executor(session, dry_run=dry_run, adapter_pool=_adapter_pool)
        try:
            await executor.run_all_accounts(accounts, adapters, bonds, trade_date)
        except Exception as exc:
            logger.error("_run_subscribe failed for %s: %s", trade_date, exc)
            raise


async def job_subscribe() -> None:
    today = datetime.now(_TZ_SHANGHAI).date()
    if not calendar.is_trading_day(today):
        logger.info("job_subscribe: %s is not a trading day, skip", today)
        return
    await _run_subscribe(today)
    logger.info("job_subscribe: done for %s", today)


async def job_retry() -> None:
    today = datetime.now(_TZ_SHANGHAI).date()
    if not calendar.is_trading_day(today):
        logger.info("job_retry: %s is not a trading day, skip", today)
        return
    await _run_subscribe(today, retry_only=True)
    logger.info("job_retry: done for %s", today)


async def job_reconcile() -> None:
    today = datetime.now(_TZ_SHANGHAI).date()
    if not calendar.is_trading_day(today):
        logger.info("job_reconcile: %s is not a trading day, skip", today)
        return
    async with _get_session_factory()() as session:
        result = await session.execute(select(Account).where(Account.enabled.is_(True)))
        accounts = result.scalars().all()
        reconciler = Reconciler(session)
        for account in accounts:
            # Reuse pooled (logged-in) adapter; fall back to fresh login if missing.
            adapter = _adapter_pool.get(account.id)
            if adapter is None or not adapter.check_session():
                try:
                    adapter = _get_adapter(account)
                except ValueError as exc:
                    logger.error(
                        "job_reconcile: unknown broker for account %s: %s", account.id, exc
                    )
                    continue
                try:
                    creds = _decrypt_creds(account)
                except Exception as exc:
                    logger.error(
                        "job_reconcile: failed to decrypt credentials for account %s: %s",
                        account.id,
                        exc,
                    )
                    continue
                ok = await adapter.login(creds)
                if ok:
                    _adapter_pool[account.id] = adapter
                    logger.info("job_reconcile: re-logged in account %s", account.id)
                else:
                    logger.warning(
                        "job_reconcile: login failed for account %s, skipping", account.id
                    )
                    continue
            try:
                await reconciler.reconcile_account(account, adapter, today)
            except Exception as exc:
                logger.error("job_reconcile: failed for account %s: %s", account.id, exc)
    logger.info("job_reconcile: done for %s", today)


def _on_job_error(event) -> None:
    logger.error(
        "Scheduler job [%s] failed: %s",
        event.job_id,
        event.exception,
        exc_info=event.traceback,
    )


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    scheduler.add_job(job_snapshot, "cron", hour=8, minute=50, id="snapshot")
    scheduler.add_job(job_warmup, "cron", hour=9, minute=20, id="warmup")
    scheduler.add_job(job_subscribe, "cron", hour=9, minute=30, second=5, id="subscribe")
    scheduler.add_job(job_retry, "cron", hour=9, minute=35, id="retry_1")
    scheduler.add_job(job_retry, "cron", hour=10, minute=0, id="retry_2")
    scheduler.add_job(job_reconcile, "cron", hour=14, minute=30, id="reconcile")
    return scheduler


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    scheduler = create_scheduler()

    def _handle_sigterm() -> None:
        logger.info("Received SIGTERM, shutting down gracefully.")
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    except NotImplementedError:
        logger.warning("SIGTERM handler is not supported on this platform")

    scheduler.start()
    logger.info("Scheduler started. Jobs: %s", [job.id for job in scheduler.get_jobs()])
    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                continue
    except (KeyboardInterrupt, SystemExit):
        stop_event.set()
    finally:
        scheduler.shutdown()
        for acc_id, adapter in list(_adapter_pool.items()):
            try:
                adapter.logout()
                logger.info("main: logged out adapter for account %s", acc_id)
            except Exception as exc:
                logger.warning("main: logout failed for account %s: %s", acc_id, exc)
        _adapter_pool.clear()
        await _get_engine().dispose()
        try:
            loop.remove_signal_handler(signal.SIGTERM)
        except NotImplementedError:
            pass
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
