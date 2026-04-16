"""
同花顺 (Tonghuashun) broker adapter via easytrader.
Requires 同花顺 client installed on the host machine.
In Docker: NOT supported (easytrader requires a running GUI client).
Use this adapter only in local/non-Docker deployments.
For Docker, use a Playwright-based adapter instead.
"""
import logging
from datetime import date
from app.brokers.base import (
    BrokerAdapter, HealthStatus, Order, OrderStatus, SubscribeResult, SubscribeResultCode,
)

logger = logging.getLogger(__name__)


class TonghuashunBroker(BrokerAdapter):
    broker_name = "tonghuashun"

    def __init__(self):
        self._trader = None
        self._logged_in = False

    def check_session(self) -> bool:
        return self._logged_in

    async def healthcheck(self) -> HealthStatus:
        try:
            import easytrader  # noqa — confirm package available
            return HealthStatus(ok=True, message="easytrader available")
        except ImportError:
            return HealthStatus(ok=False, message="easytrader not installed")

    async def login(self, credentials: dict) -> bool:
        """
        credentials = {"exe_path": "/path/to/同花顺.exe", "comm_password": "..."}
        Returns True on success, False on failure.
        """
        try:
            import easytrader
            self._trader = easytrader.use("ths")
            self._trader.connect(
                exe_path=credentials.get("exe_path", ""),
                comm_password=credentials.get("comm_password", ""),
            )
            self._logged_in = True
            logger.info("同花顺 login succeeded")
            return True
        except Exception as e:
            logger.error("同花顺 login failed: %s", e)
            self._logged_in = False
            return False

    def logout(self) -> None:
        self._trader = None
        self._logged_in = False

    async def get_balance(self) -> float:
        """Returns available balance in yuan (可用金额)."""
        if not self._trader:
            return 0.0
        try:
            bal = self._trader.balance
            return float(bal.get("可用金额", 0))
        except Exception as e:
            logger.warning("get_balance failed: %s", e)
            return 0.0

    async def max_subscribe_amount(self, bond_code: str) -> int:
        return 1000  # Standard retail convertible bond limit

    async def subscribe_bond(self, bond_code: str, amount: int) -> SubscribeResult:
        if not self._trader or not self._logged_in:
            return SubscribeResult(
                code=SubscribeResultCode.SESSION_EXPIRED,
                message="not logged in",
            )
        try:
            result = self._trader.buy(bond_code, price=0, amount=amount)
            raw = str(result)
            logger.info("subscribe_bond %s result: %s", bond_code, raw)
            # easytrader returns list of dicts on success
            if result and isinstance(result, list):
                return SubscribeResult(
                    code=SubscribeResultCode.SUCCESS,
                    message="success",
                    raw_response=raw,
                )
            return SubscribeResult(
                code=SubscribeResultCode.UNKNOWN,
                message="unexpected response",
                raw_response=raw,
            )
        except Exception as e:
            msg = str(e)
            logger.error("subscribe_bond %s error: %s", bond_code, msg)
            if "风控" in msg or "限制" in msg:
                return SubscribeResult(code=SubscribeResultCode.RISK_CONTROL, message=msg)
            return SubscribeResult(
                code=SubscribeResultCode.NETWORK_ERROR,
                message=msg,
                raw_response=msg,
            )

    async def query_today_orders(self) -> list[Order]:
        if not self._trader:
            return []
        try:
            orders_df = self._trader.today_entrusts
            orders = []
            for _, row in orders_df.iterrows():
                raw_status = str(row.get("状态", ""))
                # Map Chinese status strings to OrderStatus enum
                if raw_status == "委托中":
                    status = OrderStatus.PENDING
                elif raw_status == "已成交":
                    status = OrderStatus.FILLED
                elif raw_status == "已撤销":
                    status = OrderStatus.CANCELLED
                else:
                    status = OrderStatus.UNKNOWN
                orders.append(Order(
                    bond_code=str(row.get("证券代码", "")),
                    trade_date=date.today(),
                    status=status,
                    raw=str(row.to_dict()),
                ))
            return orders
        except Exception as e:
            logger.warning("query_today_orders failed: %s", e)
            return []
