import logging
from datetime import date
from app.data_sources.base import BondInfo, DataSource

logger = logging.getLogger(__name__)


class ScraperSource(DataSource):
    """
    Web scraping fallback. Scrapes 集思录 / 东方财富 for today's subscription list.
    Currently returns empty list (stub). Implement when AKShare is unavailable.
    """
    name = "scraper"

    async def fetch(self, trade_date: date) -> list[BondInfo]:
        logger.warning("ScraperSource not yet implemented, returning empty list")
        return []
