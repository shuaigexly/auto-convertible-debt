import logging
from datetime import date
from app.data_sources.base import BondInfo, DataSource

logger = logging.getLogger(__name__)


class AKShareSource(DataSource):
    name = "akshare"

    async def fetch(self, trade_date: date) -> list[BondInfo]:
        try:
            import akshare as ak
            df = ak.bond_zh_cov(subscribe="1")  # subscribe=1: today's subscription bonds
            bonds = []
            for _, row in df.iterrows():
                code = str(row.get("申购代码", "")).strip()
                name = str(row.get("债券简称", "")).strip()
                if not code:
                    continue
                market = "SH" if code.startswith(("7", "1")) else "SZ"
                bonds.append(BondInfo(
                    bond_code=code,
                    bond_name=name,
                    market=market,
                    trade_date=trade_date,
                    source=self.name,
                ))
            logger.info("AKShare returned %d bonds for %s", len(bonds), trade_date)
            return bonds
        except Exception as e:
            logger.warning("AKShare fetch failed: %s", e)
            return []
