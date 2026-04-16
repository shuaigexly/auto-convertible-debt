import logging
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.data_sources.base import BondInfo, DataSource
from app.shared.models import BondSnapshot

logger = logging.getLogger(__name__)


class ManualSource(DataSource):
    name = "manual"

    def __init__(self, session: AsyncSession):
        self._session = session

    async def fetch(self, trade_date: date) -> list[BondInfo]:
        result = await self._session.execute(
            select(BondSnapshot).where(
                BondSnapshot.trade_date == trade_date,
                BondSnapshot.source == "manual",
                BondSnapshot.confirmed.is_(True),
            )
        )
        rows = result.scalars().all()
        return [
            BondInfo(
                bond_code=r.bond_code,
                bond_name=r.bond_name or "",
                market=r.market or "SZ",
                trade_date=trade_date,
                source="manual",
            )
            for r in rows
        ]
