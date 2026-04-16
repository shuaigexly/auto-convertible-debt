import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.brokers.base import (
    BrokerAdapter,
    HealthStatus,
    Order,
    OrderStatus,
    SubscribeResult,
    SubscribeResultCode,
)

logger = logging.getLogger(__name__)


class MiniQMTBroker(BrokerAdapter):
    broker_name = "miniqmt"

    def __init__(self):
        self._trader = None
        self._account = None
        self._connected = False

    def check_session(self) -> bool:
        return self._connected

    async def healthcheck(self) -> HealthStatus:
        try:
            from xtquant.xttrader import XtQuantTrader  # noqa: F401
            from xtquant.xttype import StockAccount  # noqa: F401

            return HealthStatus(ok=True, message="xtquant available")
        except ImportError:
            return HealthStatus(ok=False, message="xtquant not installed")

    async def login(self, credentials: dict) -> bool:
        loop = asyncio.get_running_loop()

        def _login() -> bool:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount

            path = str(credentials.get("path", "")).strip()
            account_id = str(credentials.get("account_id", "")).strip()
            session_id = credentials.get("session_id")
            if not path or not account_id or session_id is None:
                raise ValueError("path, account_id and session_id are required")

            trader = XtQuantTrader(path, int(session_id))
            trader.start()
            connect_result = trader.connect()
            if connect_result != 0:
                raise RuntimeError(f"connect failed: {connect_result}")

            account = StockAccount(account_id)
            subscribe = getattr(trader, "subscribe", None)
            if callable(subscribe):
                subscribe_result = subscribe(account)
                if subscribe_result not in (None, 0):
                    raise RuntimeError(f"subscribe failed: {subscribe_result}")

            self._trader = trader
            self._account = account
            self._connected = True
            return True

        try:
            result = await loop.run_in_executor(None, _login)
            logger.info("MiniQMT login succeeded")
            return result
        except Exception as e:
            logger.error("MiniQMT login failed: %s", e)
            self.logout()
            return False

    def logout(self) -> None:
        trader = self._trader
        self._trader = None
        self._account = None
        self._connected = False

        if trader is not None:
            try:
                stop = getattr(trader, "stop", None)
                if callable(stop):
                    stop()
            except Exception as e:
                logger.warning("MiniQMT stop failed: %s", e)

    async def get_balance(self) -> float:
        if not self._connected or self._trader is None or self._account is None:
            return 0.0

        loop = asyncio.get_running_loop()

        def _get_balance() -> float:
            asset = self._trader.query_stock_asset(self._account)
            if asset is None:
                return 0.0
            return float(getattr(asset, "cash", 0.0) or 0.0)

        try:
            return await loop.run_in_executor(None, _get_balance)
        except Exception as e:
            logger.warning("MiniQMT get_balance failed: %s", e)
            return 0.0

    async def max_subscribe_amount(self, bond_code: str) -> int:
        return 1000

    async def subscribe_bond(self, bond_code: str, amount: int) -> SubscribeResult:
        if not self._connected or self._trader is None or self._account is None:
            return SubscribeResult(
                code=SubscribeResultCode.SESSION_EXPIRED,
                message="not logged in",
            )

        stock_code = self._to_stock_code(bond_code)
        loop = asyncio.get_running_loop()

        def _subscribe() -> int:
            from xtquant import xtconstant

            price_type = getattr(xtconstant, "BROKER_PRICE_PROP_SUBSCRIBE", 54)
            return self._trader.order_stock(
                self._account,
                stock_code,
                xtconstant.STOCK_BUY,
                amount,
                price_type,
                0.0,
            )

        try:
            order_id = await loop.run_in_executor(None, _subscribe)
            raw = str(order_id)
            logger.info("MiniQMT subscribe_bond %s result: %s", stock_code, raw)
            if isinstance(order_id, int) and order_id > 0:
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
            logger.error("MiniQMT subscribe_bond %s error: %s", stock_code, msg)
            code = self._map_error(msg)
            return SubscribeResult(code=code, message=msg, raw_response=msg)

    async def query_today_orders(self) -> list[Order]:
        if not self._connected or self._trader is None or self._account is None:
            return []

        loop = asyncio.get_running_loop()

        def _query_orders():
            return self._trader.query_stock_orders(self._account, cancelable_only=False) or []

        try:
            orders_raw = await loop.run_in_executor(None, _query_orders)
            orders = []
            for item in orders_raw:
                stock_code = str(getattr(item, "stock_code", "") or "")
                status_code = int(getattr(item, "order_status", -1))
                orders.append(Order(
                    bond_code=self._strip_market_suffix(stock_code),
                    trade_date=datetime.now(ZoneInfo("Asia/Shanghai")).date(),
                    status=self._map_order_status(status_code),
                    raw=str(item),
                ))
            return orders
        except Exception as e:
            logger.warning("MiniQMT query_today_orders failed: %s", e)
            raise

    def _to_stock_code(self, bond_code: str) -> str:
        code = str(bond_code).strip().upper()
        if "." in code:
            return code
        if code.startswith(("110", "113")):
            market = "SH"
        elif code.startswith(("123", "128")):
            market = "SZ"
        else:
            logger.warning(
                "_to_stock_code: unrecognized bond code prefix %s, defaulting to SZ", code
            )
            market = "SZ"
        return f"{code}.{market}"

    def _strip_market_suffix(self, stock_code: str) -> str:
        return stock_code.split(".", 1)[0].strip()

    def _map_order_status(self, status_code: int) -> OrderStatus:
        if status_code in (48, 49, 50):
            return {
                48: OrderStatus.PENDING,
                49: OrderStatus.CANCELLED,
                50: OrderStatus.FILLED,
            }[status_code]
        if status_code in (51, 52, 55):
            return OrderStatus.PENDING
        if status_code in (53, 54):
            return OrderStatus.CANCELLED
        if status_code == 56:
            return OrderStatus.FILLED
        return OrderStatus.UNKNOWN

    def _map_error(self, message: str) -> SubscribeResultCode:
        if any(keyword in message for keyword in ("已申购", "重复", "已委托", "已存在")):
            return SubscribeResultCode.ALREADY_SUBSCRIBED
        if any(keyword in message for keyword in ("风控", "限制", "禁止", "不允许")):
            return SubscribeResultCode.RISK_CONTROL
        if any(keyword in message for keyword in ("未连接", "断开", "失效", "登录", "session")):
            return SubscribeResultCode.SESSION_EXPIRED
        if any(keyword in message.lower() for keyword in ("timeout", "network", "socket", "connect")):
            return SubscribeResultCode.NETWORK_ERROR
        if any(keyword in message for keyword in ("网络", "超时", "连接")):
            return SubscribeResultCode.NETWORK_ERROR
        return SubscribeResultCode.UNKNOWN
