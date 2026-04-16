from dataclasses import dataclass
from datetime import date
from abc import ABC, abstractmethod


@dataclass
class BondInfo:
    bond_code: str    # e.g. "110085"
    bond_name: str    # e.g. "华能转债"
    market: str       # "SH" or "SZ"
    trade_date: date
    source: str


class DataSource(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch(self, trade_date: date) -> list[BondInfo]:
        """Return list of bonds available for subscription on trade_date."""
        ...
