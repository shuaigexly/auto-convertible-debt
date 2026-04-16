import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_trigger_snapshot_calls_job():
    from app.web.main import app
    with patch("app.web.api.trigger.job_snapshot", new_callable=AsyncMock) as mock_job:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/trigger/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        assert data["job"] == "snapshot"
        mock_job.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_subscribe_calls_job():
    from app.web.main import app
    with patch("app.web.api.trigger.job_subscribe", new_callable=AsyncMock) as mock_job:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/trigger/subscribe")
        assert resp.status_code == 200
        assert resp.json()["job"] == "subscribe"
        mock_job.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_reconcile_calls_job():
    from app.web.main import app
    with patch("app.web.api.trigger.job_reconcile", new_callable=AsyncMock) as mock_job:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/trigger/reconcile")
        assert resp.status_code == 200
        assert resp.json()["job"] == "reconcile"
        mock_job.assert_called_once()
