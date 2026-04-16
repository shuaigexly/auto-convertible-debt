import os
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from app.web.main import app


@pytest.mark.asyncio
async def test_list_accounts_empty():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def override_get_db():
        yield mock_session

    from app.shared.db import get_db
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/accounts/")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_account():
    from app.shared.models import Account
    from datetime import datetime

    mock_account = MagicMock(spec=Account)
    mock_account.id = 1
    mock_account.name = "test"
    mock_account.broker = "mock"
    mock_account.enabled = True
    mock_account.circuit_broken = False
    mock_account.consecutive_failures = 0
    mock_account.created_at = datetime(2025, 4, 16, 9, 0, 0)

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    # After refresh, make the session return the mock_account when needed
    # The endpoint adds `account` to session and returns it — we intercept
    # by capturing what was added and making refresh work
    added_accounts = []
    original_add = mock_session.add

    def capture_add(obj):
        added_accounts.append(obj)

    mock_session.add = capture_add

    async def mock_refresh(obj):
        # Set attributes on the actual object added
        obj.id = 1
        obj.name = "test"
        obj.broker = "mock"
        obj.enabled = True
        obj.circuit_broken = False
        obj.consecutive_failures = 0
        obj.created_at = datetime(2025, 4, 16, 9, 0, 0)

    mock_session.refresh = mock_refresh

    async def override_get_db():
        yield mock_session

    from app.shared.db import get_db
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.web.api.accounts.get_keys_from_env", return_value=("key1", None)):
        with patch("app.web.api.accounts.encrypt", return_value="encrypted_creds"):
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/api/accounts/",
                        json={"name": "test", "broker": "mock", "credentials_plain": '{"user": "u"}'},
                    )
                assert resp.status_code == 201
                data = resp.json()
                assert data["name"] == "test"
                assert data["broker"] == "mock"
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_enable_account_not_found():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)

    async def override_get_db():
        yield mock_session

    from app.shared.db import get_db
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch("/api/accounts/999/enable")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_account_create_invalid_json_credentials():
    """credentials_plain 不是合法 JSON 时应抛出 ValidationError。"""
    from pydantic import ValidationError
    from app.shared.schemas import AccountCreate

    with pytest.raises(ValidationError, match="credentials_plain must be valid JSON"):
        AccountCreate(name="x", broker="mock", credentials_plain="not-json")


def test_account_create_non_object_json():
    """credentials_plain 是 JSON 数组时应抛出 ValidationError。"""
    from pydantic import ValidationError
    from app.shared.schemas import AccountCreate

    with pytest.raises(ValidationError, match="JSON object"):
        AccountCreate(name="x", broker="mock", credentials_plain='["a","b"]')


def test_account_create_valid_json():
    """合法 JSON 对象应通过验证。"""
    from app.shared.schemas import AccountCreate

    obj = AccountCreate(name="x", broker="mock", credentials_plain='{"user":"u","pass":"p"}')
    assert obj.credentials_plain == '{"user":"u","pass":"p"}'


def test_account_create_invalid_broker():
    """未知 broker 类型应触发 ValidationError。"""
    from pydantic import ValidationError
    from app.shared.schemas import AccountCreate

    with pytest.raises(ValidationError, match="broker must be one of"):
        AccountCreate(name="x", broker="unknown_broker", credentials_plain='{"k":"v"}')


def test_account_create_valid_broker():
    """合法 broker 名称应通过验证。"""
    from app.shared.schemas import AccountCreate

    for broker in ("mock", "miniqmt", "tonghuashun"):
        obj = AccountCreate(name="x", broker=broker, credentials_plain='{"k":"v"}')
        assert obj.broker == broker


@pytest.mark.asyncio
async def test_delete_account_with_subscriptions_returns_409():
    """有申购记录时删除账户应返回 409。"""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    mock_session = AsyncMock()
    mock_account = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_account)
    mock_session.delete = AsyncMock()
    mock_session.commit = AsyncMock(side_effect=SAIntegrityError(None, None, Exception("fk")))
    mock_session.rollback = AsyncMock()

    async def override_get_db():
        yield mock_session

    from app.shared.db import get_db
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/accounts/1")
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_key_middleware_blocks_without_key(monkeypatch):
    """API_KEY 设置后，未携带 X-API-Key 的请求应返回 401。"""
    import importlib
    monkeypatch.setenv("API_KEY", "secret-key-123")
    # Reload web.main so the middleware picks up the new env var
    import app.web.main as web_main
    importlib.reload(web_main)
    test_app = web_main.app

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/accounts/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_middleware_allows_with_correct_key(monkeypatch):
    """携带正确 X-API-Key 的请求应通过。"""
    import importlib
    monkeypatch.setenv("API_KEY", "secret-key-456")
    import app.web.main as web_main
    importlib.reload(web_main)
    test_app = web_main.app

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def override_get_db():
        yield mock_session

    from app.shared.db import get_db
    test_app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/api/accounts/", headers={"X-API-Key": "secret-key-456"})
        assert resp.status_code == 200
    finally:
        test_app.dependency_overrides.clear()
