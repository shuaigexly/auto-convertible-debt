import logging
from datetime import date
from app.data_sources.base import BondInfo, DataSource

logger = logging.getLogger(__name__)


class AKShareSource(DataSource):
    name = "akshare"

    async def fetch(self, trade_date: date) -> list[BondInfo]:
        try:
            import akshare as ak
            date_str = trade_date.strftime("%Y%m%d")
            df = ak.bond_cov_issue_cninfo(start_date=date_str, end_date=date_str)
            bonds = []
            for _, row in df.iterrows():
                code = str(row.get("网上申购代码", "")).strip()
                name = str(row.get("债券简称", "")).strip()
                if not code:
                    continue
                market_raw = str(row.get("交易市场", "")).strip()
                if market_raw == "上交所":
                    market = "SH"
                elif market_raw == "深交所":
                    market = "SZ"
                else:
                    market = "SH" if code.startswith("7") else "SZ"
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
