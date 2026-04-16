import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from app.worker.executor import Executor
from app.brokers.base import SubscribeResult, SubscribeResultCode
from app.brokers.mock_broker import MockBroker
from app.data_sources.base import BondInfo
from app.shared.models import Account, Subscription, SubscriptionStatus


@pytest.mark.asyncio
async def test_executor_skips_already_subscribed_bond(db_session):
    """Idempotency: existing SUBMITTED record prevents re-submission."""
    from app.shared.crypto import encrypt
    import os, json
    os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=")
    key = os.environ["ENCRYPTION_KEY"]
    creds = encrypt(json.dumps({"exe_path": ""}), key)

    account = Account(name="test", broker="mock", credentials_enc=creds, enabled=True)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    today = date(2025, 4, 16)
    existing = Subscription(
        trade_date=today,
        bond_code="110001",
        bond_name="A债",
        account_id=account.id,
        status=SubscriptionStatus.SUBMITTED,
    )
    db_session.add(existing)
    await db_session.commit()

    mock_adapter = MockBroker()
    subscribe_spy = AsyncMock(return_value=SubscribeResult(code=SubscribeResultCode.SUCCESS))
    mock_adapter.subscribe_bond = subscribe_spy

    executor = Executor(session=db_session, dry_run=False)
    bonds = [BondInfo("110001", "A债", "SH", today, "test")]
    await executor.run_for_account(account, mock_adapter, bonds, today)

    subscribe_spy.assert_not_called()


@pytest.mark.asyncio
async def test_executor_records_success(db_session):
    from app.shared.crypto import encrypt
    import os, json
    os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=")
    key = os.environ["ENCRYPTION_KEY"]
    creds = encrypt(json.dumps({"exe_path": ""}), key)

    account = Account(name="test2", broker="mock", credentials_enc=creds, enabled=True)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    today = date(2025, 4, 16)
    mock_adapter = MockBroker()
    executor = Executor(session=db_session, dry_run=False)
    bonds = [BondInfo("220001", "B债", "SZ", today, "test")]
    await executor.run_for_account(account, mock_adapter, bonds, today)

    from sqlalchemy import select
    result = await db_session.execute(
        select(Subscription).where(
            Subscription.account_id == account.id,
            Subscription.bond_code == "220001",
        )
    )
    sub = result.scalar_one_or_none()
    assert sub is not None
    assert sub.status == SubscriptionStatus.SUBMITTED


@pytest.mark.asyncio
async def test_executor_session_expired_evicts_pool(db_session):
    """SESSION_EXPIRED 结果应清除 adapter_pool 中对应账户条目。"""
    from app.shared.crypto import encrypt
    import os, json
    os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=")
    key = os.environ["ENCRYPTION_KEY"]
    creds = encrypt(json.dumps({"exe_path": ""}), key)

    account = Account(name="test_expire", broker="mock", credentials_enc=creds, enabled=True)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    today = date(2025, 4, 16)
    mock_adapter = MockBroker()
    mock_adapter.subscribe_bond = AsyncMock(
        return_value=SubscribeResult(code=SubscribeResultCode.SESSION_EXPIRED, message="expired")
    )
    mock_adapter.query_today_orders = AsyncMock(return_value=[])

    pool = {account.id: mock_adapter}
    executor = Executor(session=db_session, dry_run=False, adapter_pool=pool)
    bonds = [BondInfo("330001", "C债", "SH", today, "test")]
    await executor.run_for_account(account, mock_adapter, bonds, today)

    # Pool entry should have been cleared
    assert account.id not in pool
