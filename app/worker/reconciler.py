import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerAdapter, OrderStatus
from app.notifier.base import NotifyMessage
from app.notifier.dispatcher import notify
from app.shared.models import Account, Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)


class Reconciler:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def reconcile_account(
        self, account: Account, adapter: BrokerAdapter, trade_date: date
    ) -> None:
        try:
            broker_orders = await adapter.query_today_orders()
            submitted_codes = {
                o.bond_code for o in broker_orders
                if o.status in (
                    OrderStatus.FILLED,
                    OrderStatus.PENDING,
                    OrderStatus.UNKNOWN,
                )
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

            pending_notifications: list[NotifyMessage] = []
            for sub in subs:
                if sub.bond_code in submitted_codes:
                    sub.status = SubscriptionStatus.RECONCILED
                    logger.info(
                        "Reconciled %s for account %s", sub.bond_code, account.name
                    )
                else:
                    sub.status = SubscriptionStatus.FAILED
                    sub.error = "not found in broker orders during reconciliation"
                    logger.warning(
                        "Bond %s not found in broker orders for account %s",
                        sub.bond_code, account.name,
                    )
                    pending_notifications.append(
                        NotifyMessage(
                            title=f"对账失败: {sub.bond_code}",
                            body=f"账户 {account.name} 债券 {sub.bond_code} 未出现在券商委托记录中",
                            level="warning",
                        )
                    )

            await self._session.commit()
            for message in pending_notifications:
                await notify(message)
        except Exception:
            await self._session.rollback()
            raise
