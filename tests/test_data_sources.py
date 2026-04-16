import sys
import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock
from app.data_sources.base import BondInfo, DataSource
from app.data_sources.akshare_source import AKShareSource
from app.data_sources.manual_source import ManualSource
from app.data_sources.scraper import EastMoneySource, JisiluSource

_MOCK_AKSHARE = MagicMock()


@pytest.mark.asyncio
async def test_akshare_source_returns_bonds_on_success():
    mock_df = MagicMock()
    mock_df.iterrows.return_value = iter([
        (0, {"网上申购代码": "754321", "债券简称": "测试转债", "交易市场": "上交所"}),
    ])
    _MOCK_AKSHARE.bond_cov_issue_cninfo.return_value = mock_df
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
    mock_ak.bond_cov_issue_cninfo.side_effect = Exception("network error")
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


@pytest.mark.asyncio
async def test_aggregator_confirms_bond_seen_in_two_sources():
    from app.data_sources.aggregator import BondAggregator

    class _FakeSource(DataSource):
        name = "fake"

        def __init__(self, bonds):
            self._bonds = bonds

        async def fetch(self, trade_date):
            return self._bonds

    bond_a = BondInfo(bond_code="123456", bond_name="债A", market="SH", trade_date=date(2025, 4, 16), source="s1")
    bond_b = BondInfo(bond_code="123456", bond_name="债A", market="SH", trade_date=date(2025, 4, 16), source="s2")

    agg = BondAggregator([_FakeSource([bond_a]), _FakeSource([bond_b])])
    confirmed, pending = await agg.aggregate(date(2025, 4, 16))
    assert any(b.bond_code == "123456" for b in confirmed)
    assert not any(b.bond_code == "123456" for b in pending)


@pytest.mark.asyncio
async def test_aggregator_sends_single_source_to_pending():
    from app.data_sources.aggregator import BondAggregator

    class _FakeSource(DataSource):
        name = "fake"

        def __init__(self, bonds):
            self._bonds = bonds

        async def fetch(self, trade_date):
            return self._bonds

    bond_only_one = BondInfo(bond_code="654321", bond_name="债B", market="SZ", trade_date=date(2025, 4, 16), source="s1")

    agg = BondAggregator([_FakeSource([bond_only_one]), _FakeSource([])])
    confirmed, pending = await agg.aggregate(date(2025, 4, 16))
    assert not any(b.bond_code == "654321" for b in confirmed)
    assert any(b.bond_code == "654321" for b in pending)


@pytest.mark.asyncio
async def test_eastmoney_source_returns_bonds_on_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "data": [
                {
                    "VALUE_DATE": "2026-04-16 00:00:00",
                    "CORRECODE": "371210",
                    "SECURITY_NAME_ABBR": "金杨转债",
                    "BOND_CODE": "123210",
                },
                {
                    "VALUE_DATE": "2026-04-15 00:00:00",
                    "CORRECODE": "754321",
                    "SECURITY_NAME_ABBR": "非当日转债",
                    "BOND_CODE": "113210",
                },
            ]
        }
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        src = EastMoneySource()
        results = await src.fetch(date(2026, 4, 16))

    assert len(results) == 1
    assert results[0].bond_code == "371210"
    assert results[0].bond_name == "金杨转债"
    assert results[0].market == "SZ"
    assert results[0].source == "eastmoney"


@pytest.mark.asyncio
async def test_jisilu_source_returns_bonds_on_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "apply_date": "2026-04-16",
                "apply_cd": "754321",
                "bond_nm": "测试转债",
                "ration_cd": "113210",
            },
            {
                "apply_date": "2026-04-15",
                "apply_cd": "371210",
                "bond_nm": "非当日转债",
                "ration_cd": "123210",
            },
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        src = JisiluSource()
        results = await src.fetch(date(2026, 4, 16))

    assert len(results) == 1
    assert results[0].bond_code == "754321"
    assert results[0].bond_name == "测试转债"
    assert results[0].market == "SH"
    assert results[0].source == "jisilu"
