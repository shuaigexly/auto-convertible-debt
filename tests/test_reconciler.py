import pytest
from datetime import date
from unittest.mock import AsyncMock
from app.worker.reconciler import Reconciler
from app.brokers.base import Order, OrderStatus
from app.shared.models import Account, Subscription, SubscriptionStatus
from app.shared.crypto import encrypt
import os, json


@pytest.mark.asyncio
async def test_reconciler_marks_unknown_as_reconciled_when_order_found(db_session):
    os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=")
    key = os.environ["ENCRYPTION_KEY"]
    creds = encrypt(json.dumps({}), key)

    account = Account(name="rec_test", broker="mock", credentials_enc=creds, enabled=True)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    today = date(2025, 4, 16)
    sub = Subscription(
        trade_date=today,
        bond_code="330001",
        bond_name="C债",
        account_id=account.id,
        status=SubscriptionStatus.UNKNOWN,
    )
    db_session.add(sub)
    await db_session.commit()

    mock_adapter = AsyncMock()
    mock_adapter.query_today_orders.return_value = [
        Order(bond_code="330001", trade_date=today, status=OrderStatus.FILLED),
    ]

    reconciler = Reconciler(session=db_session)
    await reconciler.reconcile_account(account, mock_adapter, today)

    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.RECONCILED
