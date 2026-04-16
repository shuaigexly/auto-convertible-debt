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


@pytest.mark.asyncio
async def test_executor_risk_control_sets_retry_count_to_max(db_session):
    """RISK_CONTROL 失败应将 retry_count 设为 MAX_RETRIES，防止 retry job 无限重试。"""
    from app.shared.crypto import encrypt
    from app.worker.executor import MAX_RETRIES
    import os, json
    os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=")
    key = os.environ["ENCRYPTION_KEY"]
    creds = encrypt(json.dumps({"exe_path": ""}), key)

    account = Account(name="test_risk", broker="mock", credentials_enc=creds, enabled=True)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    today = date(2025, 4, 16)
    mock_adapter = MockBroker()
    mock_adapter.subscribe_bond = AsyncMock(
        return_value=SubscribeResult(code=SubscribeResultCode.RISK_CONTROL, message="risk control")
    )
    mock_adapter.query_today_orders = AsyncMock(return_value=[])

    executor = Executor(session=db_session, dry_run=False)
    bonds = [BondInfo("440001", "D债", "SH", today, "test")]
    await executor.run_for_account(account, mock_adapter, bonds, today)

    from sqlalchemy import select
    result = await db_session.execute(
        select(Subscription).where(
            Subscription.account_id == account.id,
            Subscription.bond_code == "440001",
        )
    )
    sub = result.scalar_one_or_none()
    assert sub is not None
    assert sub.status == SubscriptionStatus.FAILED
    assert sub.retry_count == MAX_RETRIES  # 非重试类失败不得被 retry job 再次选取


@pytest.mark.asyncio
async def test_executor_retryable_failure_leaves_retry_count_below_max(db_session):
    """SESSION_EXPIRED 等 retryable 失败后，retry_count 应 < MAX_RETRIES，
    使 retry job 能选到该记录进行重试。"""
    from app.shared.crypto import encrypt
    from app.worker.executor import MAX_RETRIES
    import os, json
    os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=")
    key = os.environ["ENCRYPTION_KEY"]
    creds = encrypt(json.dumps({"exe_path": ""}), key)

    account = Account(name="test_retryable", broker="mock", credentials_enc=creds, enabled=True)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    today = date(2025, 4, 16)
    mock_adapter = MockBroker()
    mock_adapter.subscribe_bond = AsyncMock(
        return_value=SubscribeResult(code=SubscribeResultCode.SESSION_EXPIRED, message="session expired")
    )
    mock_adapter.query_today_orders = AsyncMock(return_value=[])

    pool = {account.id: mock_adapter}
    executor = Executor(session=db_session, dry_run=False, adapter_pool=pool)
    bonds = [BondInfo("550001", "E债", "SZ", today, "test")]
    await executor.run_for_account(account, mock_adapter, bonds, today)

    from sqlalchemy import select
    result = await db_session.execute(
        select(Subscription).where(
            Subscription.account_id == account.id,
            Subscription.bond_code == "550001",
        )
    )
    sub = result.scalar_one_or_none()
    assert sub is not None
    assert sub.status == SubscriptionStatus.FAILED
    # retry_count 应 < MAX_RETRIES，使 retry job 能选到此记录重试
    assert sub.retry_count < MAX_RETRIES
    assert sub.retry_count == 1  # 初次失败后为 1，< MAX_RETRIES = 2


def test_miniqmt_to_stock_code_sh_trading():
    """SH 交易代码 110xxx/113xxx → .SH 后缀。"""
    from app.brokers.miniqmt_adapter import MiniQMTBroker
    b = MiniQMTBroker()
    assert b._to_stock_code("110001") == "110001.SH"
    assert b._to_stock_code("113001") == "113001.SH"


def test_miniqmt_to_stock_code_sz_trading():
    """SZ 交易代码 123xxx/128xxx → .SZ 后缀。"""
    from app.brokers.miniqmt_adapter import MiniQMTBroker
    b = MiniQMTBroker()
    assert b._to_stock_code("123001") == "123001.SZ"
    assert b._to_stock_code("128001") == "128001.SZ"


def test_miniqmt_to_stock_code_sh_subscription():
    """SH 申购代码 730xxx → .SH 后缀（修复前会错误路由到 .SZ）。"""
    from app.brokers.miniqmt_adapter import MiniQMTBroker
    b = MiniQMTBroker()
    assert b._to_stock_code("730888") == "730888.SH"


def test_miniqmt_to_stock_code_already_suffixed():
    """已带市场后缀时直接返回。"""
    from app.brokers.miniqmt_adapter import MiniQMTBroker
    b = MiniQMTBroker()
    assert b._to_stock_code("110001.SH") == "110001.SH"
