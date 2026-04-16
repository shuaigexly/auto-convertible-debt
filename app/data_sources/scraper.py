import logging
from datetime import date

import httpx

from app.data_sources.base import BondInfo, DataSource

logger = logging.getLogger(__name__)


class EastMoneySource(DataSource):
    name = "eastmoney"

    _url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    _params = {
        "reportName": "RPT_BOND_CB_LIST",
        "columns": "ALL",
        "sortColumns": "PUBLIC_START_DATE",
        "sortTypes": "-1",
        "pageSize": "50",
        "pageNumber": "1",
        "source": "WEB",
        "client": "WEB",
    }

    async def fetch(self, trade_date: date) -> list[BondInfo]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self._url, params=self._params)
                response.raise_for_status()
            payload = response.json()
            rows = payload.get("result", {}).get("data", [])
            bonds = []
            trade_date_str = trade_date.isoformat()
            for row in rows:
                value_date = str(row.get("VALUE_DATE", "")).split(" ")[0]
                if value_date != trade_date_str:
                    continue
                code = str(row.get("CORRECODE", "")).strip()
                if not code:
                    continue
                bonds.append(BondInfo(
                    bond_code=code,
                    bond_name=str(row.get("SECURITY_NAME_ABBR", "")).strip(),
                    market="SH" if code.startswith("7") else "SZ",
                    trade_date=trade_date,
                    source=self.name,
                ))
            logger.info("EastMoney returned %d bonds for %s", len(bonds), trade_date)
            return bonds
        except Exception as e:
            logger.warning("EastMoney fetch failed: %s", e)
            return []


class JisiluSource(DataSource):
    name = "jisilu"

    _url = "https://www.jisilu.cn/webapi/cb/pre/"
    _params = {"history": "N"}
    _headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.jisilu.cn/",
    }

    async def fetch(self, trade_date: date) -> list[BondInfo]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self._url,
                    params=self._params,
                    headers=self._headers,
                )
                response.raise_for_status()
            payload = response.json()
            rows = payload.get("data", [])
            bonds = []
            trade_date_str = trade_date.isoformat()
            for row in rows:
                if row.get("apply_date") != trade_date_str:
                    continue
                code = str(row.get("apply_cd", "")).strip()
                if not code:
                    continue
                bonds.append(BondInfo(
                    bond_code=code,
                    bond_name=str(row.get("bond_nm", "")).strip(),
                    market="SH" if code.startswith("7") else "SZ",
                    trade_date=trade_date,
                    source=self.name,
                ))
            logger.info("Jisilu returned %d bonds for %s", len(bonds), trade_date)
            return bonds
        except Exception as e:
            logger.warning("Jisilu fetch failed: %s", e)
            return []
