import asyncio
import logging
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.brokers.base import BrokerAdapter, SubscribeResultCode
from app.data_sources.base import BondInfo
from app.shared.models import Account, Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
CIRCUIT_BREAK_THRESHOLD = 3


class Executor:
    def __init__(self, session: AsyncSession, dry_run: bool = False, adapter_pool: dict | None = None):
        self._session = session
        self._dry_run = dry_run
        self._adapter_pool = adapter_pool  # Optional ref to module-level pool for session invalidation

    async def run_all_accounts(
        self,
        accounts: list[Account],
        adapters: dict[int, BrokerAdapter],
        bonds: list[BondInfo],
        trade_date: date,
        max_concurrent: int = 1,
    ) -> None:
        # max_concurrent defaults to 1: AsyncSession is NOT safe for concurrent
        # use across coroutines — multiple accounts must be serialized.
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_one(account: Account):
            if account.circuit_broken:
                logger.warning("Account %s circuit broken, skipping", account.name)
                return
            adapter = adapters.get(account.id)
            if adapter is None:
                logger.warning("No adapter for account %s", account.name)
                return
            async with semaphore:
                await self.run_for_account(account, adapter, bonds, trade_date)

        await asyncio.gather(*[run_one(a) for a in accounts])

    async def run_for_account(
        self,
        account: Account,
        adapter: BrokerAdapter,
        bonds: list[BondInfo],
        trade_date: date,
    ) -> None:
        # Fetch today's existing orders for dedup
        existing_orders = await adapter.query_today_orders()
        existing_codes = {o.bond_code for o in existing_orders}

        for bond in bonds:
            await self._subscribe_one(account, adapter, bond, trade_date, existing_codes)

    async def _subscribe_one(
        self,
        account: Account,
        adapter: BrokerAdapter,
        bond: BondInfo,
        trade_date: date,
        existing_codes: set[str],
    ) -> None:
        # Idempotency: check DB record
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.trade_date == trade_date,
                Subscription.account_id == account.id,
                Subscription.bond_code == bond.bond_code,
            )
        )
        existing_sub = result.scalar_one_or_none()
        if existing_sub and existing_sub.status in (
            SubscriptionStatus.SUBMITTED,
            SubscriptionStatus.RECONCILED,
            SubscriptionStatus.SKIPPED,
        ):
            logger.info("Skip %s for account %s (already %s)", bond.bond_code, account.name, existing_sub.status)
            return

        # Idempotency: check broker-side orders
        if bond.bond_code in existing_codes:
            logger.info("Skip %s for account %s (found in today's broker orders)", bond.bond_code, account.name)
            await self._upsert_sub(account.id, bond, trade_date, SubscriptionStatus.SKIPPED, "broker order exists")
            return

        if self._dry_run:
            logger.info("[DRY-RUN] Would subscribe %s for account %s", bond.bond_code, account.name)
            await self._upsert_sub(account.id, bond, trade_date, SubscriptionStatus.SKIPPED, "dry-run")
            return

        # Mark as SUBMITTING
        sub = await self._upsert_sub(account.id, bond, trade_date, SubscriptionStatus.SUBMITTING, None)

        amount = await adapter.max_subscribe_amount(bond.bond_code)
        sub_result = await adapter.subscribe_bond(bond.bond_code, amount)

        if sub_result.code == SubscribeResultCode.SUCCESS:
            sub.status = SubscriptionStatus.SUBMITTED
            sub.error = None
            account.consecutive_failures = 0
        elif sub_result.code == SubscribeResultCode.SESSION_EXPIRED:
            # Invalidate pool entry so next run triggers re-login
            if self._adapter_pool is not None:
                self._adapter_pool.pop(account.id, None)
                logger.warning(
                    "Session expired for account %s, evicted from pool", account.name
                )
            if sub_result.retryable and sub.retry_count < MAX_RETRIES:
                sub.status = SubscriptionStatus.UNKNOWN
                sub.error = sub_result.message
                sub.retry_count += 1
            else:
                sub.status = SubscriptionStatus.FAILED
                sub.error = sub_result.message
                account.consecutive_failures += 1
                if account.consecutive_failures >= CIRCUIT_BREAK_THRESHOLD:
                    account.circuit_broken = True
                    logger.error("Circuit broken for account %s", account.name)
        elif sub_result.retryable and sub.retry_count < MAX_RETRIES:
            sub.status = SubscriptionStatus.UNKNOWN
            sub.error = sub_result.message
            sub.retry_count += 1
        else:
            sub.status = SubscriptionStatus.FAILED
            sub.error = sub_result.message
            account.consecutive_failures += 1
            if account.consecutive_failures >= CIRCUIT_BREAK_THRESHOLD:
                account.circuit_broken = True
                logger.error("Circuit broken for account %s", account.name)

        await self._session.commit()
        logger.info(
            "Account %s bond %s → %s",
            account.name, bond.bond_code, sub.status,
        )

    async def _upsert_sub(
        self, account_id: int, bond: BondInfo, trade_date: date,
        status: SubscriptionStatus, error: str | None,
    ) -> Subscription:
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.trade_date == trade_date,
                Subscription.account_id == account_id,
                Subscription.bond_code == bond.bond_code,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            sub = Subscription(
                trade_date=trade_date,
                bond_code=bond.bond_code,
                bond_name=bond.bond_name,
                account_id=account_id,
                status=status,
                error=error,
            )
            self._session.add(sub)
        else:
            sub.status = status
            sub.error = error
        await self._session.commit()
        return sub
