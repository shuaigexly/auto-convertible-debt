import logging
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.brokers.base import BrokerAdapter, OrderStatus
from app.shared.models import Account, Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)


class Reconciler:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def reconcile_account(
        self, account: Account, adapter: BrokerAdapter, trade_date: date
    ) -> None:
        broker_orders = await adapter.query_today_orders()
        submitted_codes = {
            o.bond_code for o in broker_orders
            if o.status in (OrderStatus.FILLED, OrderStatus.PENDING)
        }

        result = await self._session.execute(
            select(Subscription).where(
                Subscription.account_id == account.id,
                Subscription.trade_date == trade_date,
                Subscription.status.in_([
                    SubscriptionStatus.SUBMITTED,
                    SubscriptionStatus.UNKNOWN,
                ]),
            )
        )
        subs = result.scalars().all()

        for sub in subs:
            if sub.bond_code in submitted_codes:
                sub.status = SubscriptionStatus.RECONCILED
                logger.info("Reconciled %s for account %s", sub.bond_code, account.name)
            else:
                sub.status = SubscriptionStatus.FAILED
                sub.error = "not found in broker orders during reconciliation"
                logger.warning(
                    "Bond %s not found in broker orders for account %s",
                    sub.bond_code, account.name,
                )

        await self._session.commit()
