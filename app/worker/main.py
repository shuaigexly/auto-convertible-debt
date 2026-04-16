"""APScheduler worker — orchestrates daily bond subscription pipeline."""

import asyncio
import json
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.brokers.mock_broker import MockBroker
from app.brokers.tongtongxin import TonghuashunBroker
from app.calendar_service import CalendarService
from app.data_sources.aggregator import BondAggregator
from app.data_sources.akshare_source import AKShareSource
from app.data_sources.base import BondInfo
from app.data_sources.manual_source import ManualSource
from app.shared.crypto import decrypt, get_keys_from_env
from app.shared.db import _get_session_factory
from app.shared.models import Account, BondSnapshot
from app.worker.executor import Executor
from app.worker.reconciler import Reconciler

logger = logging.getLogger(__name__)
calendar = CalendarService()


def _get_adapter(account: Account):
    if account.broker == "mock":
        return MockBroker()
    return TonghuashunBroker()


def _decrypt_creds(account: Account) -> dict:
    primary_key, old_key = get_keys_from_env()
    plaintext = decrypt(account.credentials_enc, primary_key, old_key)
    return json.loads(plaintext)


async def job_snapshot() -> None:
    today = date.today()
    if not calendar.is_trading_day(today):
        logger.info("job_snapshot: %s is not a trading day, skip", today)
        return
    async with _get_session_factory()() as session:
        sources = [AKShareSource(), ManualSource(session)]
        agg = BondAggregator(sources)
        confirmed, pending = await agg.aggregate(today)
        for bond in confirmed:
            snap = BondSnapshot(
                trade_date=today,
                bond_code=bond.bond_code,
                bond_name=bond.bond_name,
                market=bond.market,
                source=bond.source,
                confirmed=True,
            )
            session.add(snap)
        for bond in pending:
            snap = BondSnapshot(
                trade_date=today,
                bond_code=bond.bond_code,
                bond_name=bond.bond_name,
                market=bond.market,
                source=bond.source,
                confirmed=False,
            )
            session.add(snap)
        await session.commit()
    logger.info(
        "job_snapshot: saved %d confirmed, %d pending",
        len(confirmed),
        len(pending),
    )


async def job_warmup() -> None:
    today = date.today()
    if not calendar.is_trading_day(today):
        return
    async with _get_session_factory()() as session:
        result = await session.execute(select(Account).where(Account.enabled.is_(True)))
        accounts = result.scalars().all()
    for account in accounts:
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


async def _run_subscribe(trade_date: date) -> None:
    """Inner subscribe logic, shared by job_subscribe and job_retry."""
    async with _get_session_factory()() as session:
        result = await session.execute(select(Account).where(Account.enabled.is_(True)))
        accounts = result.scalars().all()
        adapters = {account.id: _get_adapter(account) for account in accounts}
        snaps_result = await session.execute(
            select(BondSnapshot).where(
                BondSnapshot.trade_date == trade_date,
                BondSnapshot.confirmed.is_(True),
            )
        )
        snaps = snaps_result.scalars().all()
        bonds = [
            BondInfo(
                bond_code=snap.bond_code,
                bond_name=snap.bond_name or "",
                market=snap.market or "SZ",
                trade_date=trade_date,
                source=snap.source or "akshare",
            )
            for snap in snaps
        ]
        executor = Executor(session)
        await executor.run_all_accounts(accounts, adapters, bonds, trade_date)


async def job_subscribe() -> None:
    today = date.today()
    if not calendar.is_trading_day(today):
        return
    await _run_subscribe(today)
    logger.info("job_subscribe: done for %s", today)


async def job_retry() -> None:
    today = date.today()
    if not calendar.is_trading_day(today):
        return
    await _run_subscribe(today)
    logger.info("job_retry: done for %s", today)


async def job_reconcile() -> None:
    today = date.today()
    if not calendar.is_trading_day(today):
        return
    async with _get_session_factory()() as session:
        result = await session.execute(select(Account).where(Account.enabled.is_(True)))
        accounts = result.scalars().all()
    for account in accounts:
        adapter = _get_adapter(account)
        async with _get_session_factory()() as session:
            reconciler = Reconciler(session)
            await reconciler.reconcile_account(account, adapter, today)
    logger.info("job_reconcile: done for %s", today)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(job_snapshot, "cron", hour=8, minute=50, id="snapshot")
    scheduler.add_job(job_warmup, "cron", hour=9, minute=20, id="warmup")
    scheduler.add_job(job_subscribe, "cron", hour=9, minute=30, second=5, id="subscribe")
    scheduler.add_job(job_retry, "cron", hour=9, minute=35, id="retry_1")
    scheduler.add_job(job_retry, "cron", hour=10, minute=0, id="retry_2")
    scheduler.add_job(job_reconcile, "cron", hour=14, minute=30, id="reconcile")
    return scheduler


async def main() -> None:
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started. Jobs: %s", [job.id for job in scheduler.get_jobs()])
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
