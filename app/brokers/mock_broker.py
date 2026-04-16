import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo
from app.brokers.base import (
    BrokerAdapter, HealthStatus, Order, OrderStatus, SubscribeResult, SubscribeResultCode,
)

logger = logging.getLogger(__name__)


class MockBroker(BrokerAdapter):
    """
    In-memory broker for dry-run mode and tests.
    Records subscribe calls without hitting any real API.
    """
    broker_name = "mock"

    def __init__(self):
        self._logged_in = True
        self._orders: list[Order] = []

    def check_session(self) -> bool:
        return self._logged_in

    async def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True, message="mock always healthy")

    async def login(self, credentials: dict) -> bool:
        self._logged_in = True
        return True

    def logout(self) -> None:
        self._logged_in = False

    async def get_balance(self) -> float:
        return 100_000.0

    async def max_subscribe_amount(self, bond_code: str) -> int:
        return 1000

    async def subscribe_bond(self, bond_code: str, amount: int) -> SubscribeResult:
        logger.info("[DRY-RUN] Would subscribe %s × %d", bond_code, amount)
        self._orders.append(Order(
            bond_code=bond_code,
            trade_date=datetime.now(ZoneInfo("Asia/Shanghai")).date(),
            status=OrderStatus.PENDING,
            raw="mock",
        ))
        return SubscribeResult(code=SubscribeResultCode.SUCCESS, message="dry-run success")

    async def query_today_orders(self) -> list[Order]:
        return list(self._orders)
