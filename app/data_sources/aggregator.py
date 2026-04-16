import asyncio
import logging
from datetime import date
from app.data_sources.base import BondInfo, DataSource

logger = logging.getLogger(__name__)


class BondAggregator:
    """
    Fetches from all sources in parallel.
    A bond is 'confirmed' if it appears in >= 2 sources.
    A bond seen in only 1 source goes to 'pending' (requires human confirmation).
    """

    def __init__(self, sources: list[DataSource]):
        self._sources = sources

    async def aggregate(self, trade_date: date) -> tuple[list[BondInfo], list[BondInfo]]:
        results = await asyncio.gather(
            *[s.fetch(trade_date) for s in self._sources],
            return_exceptions=True,
        )
        seen: dict[str, list[BondInfo]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Source fetch error: %s", result)
                continue
            for bond in result:
                seen.setdefault(bond.bond_code, []).append(bond)
        confirmed, pending = [], []
        for code, infos in seen.items():
            if len(infos) >= 2:
                confirmed.append(infos[0])
            else:
                pending.append(infos[0])
        logger.info(
            "Aggregated %d confirmed, %d pending for %s",
            len(confirmed),
            len(pending),
            trade_date,
        )
        return confirmed, pending
