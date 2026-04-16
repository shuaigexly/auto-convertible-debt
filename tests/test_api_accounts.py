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
