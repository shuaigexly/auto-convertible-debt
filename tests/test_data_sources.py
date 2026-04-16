import sys
import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock
from app.data_sources.base import BondInfo
from app.data_sources.akshare_source import AKShareSource
from app.data_sources.manual_source import ManualSource

_MOCK_AKSHARE = MagicMock()


@pytest.mark.asyncio
async def test_akshare_source_returns_bonds_on_success():
    mock_df = MagicMock()
    mock_df.iterrows.return_value = iter([
        (0, {"申购代码": "754321", "债券简称": "测试转债"}),
    ])
    _MOCK_AKSHARE.bond_zh_cov.return_value = mock_df
    with patch.dict("sys.modules", {"akshare": _MOCK_AKSHARE}):
        src = AKShareSource()
        results = await src.fetch(date(2025, 4, 16))
    assert len(results) == 1
    assert results[0].bond_code == "754321"
    assert results[0].market == "SH"  # "754321" starts with "7" → SH
    assert results[0].source == "akshare"


@pytest.mark.asyncio
async def test_akshare_source_returns_empty_on_error():
    mock_ak = MagicMock()
    mock_ak.bond_zh_cov.side_effect = Exception("network error")
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        src = AKShareSource()
        results = await src.fetch(date(2025, 4, 16))
    assert results == []


@pytest.mark.asyncio
async def test_manual_source_returns_confirmed_bonds(db_session):
    from app.shared.models import BondSnapshot
    snap = BondSnapshot(
        trade_date=date(2025, 4, 16),
        bond_code="123456",
        bond_name="手动债",
        market="SH",
        source="manual",
        confirmed=True,
    )
    db_session.add(snap)
    await db_session.commit()

    src = ManualSource(db_session)
    results = await src.fetch(date(2025, 4, 16))
    assert any(b.bond_code == "123456" for b in results)
