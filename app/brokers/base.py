from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import ClassVar


class SubscribeResultCode(str, Enum):
    SUCCESS = "SUCCESS"
    ALREADY_SUBSCRIBED = "ALREADY_SUBSCRIBED"
    RISK_CONTROL = "RISK_CONTROL"      # Not retryable
    SESSION_EXPIRED = "SESSION_EXPIRED"  # Retryable after re-login
    NETWORK_ERROR = "NETWORK_ERROR"    # Retryable
    UNKNOWN = "UNKNOWN"


@dataclass
class SubscribeResult:
    code: SubscribeResultCode
    message: str = ""
    raw_response: str = ""
    retryable: bool = field(init=False)

    def __post_init__(self):
        self.retryable = self.code in (
            SubscribeResultCode.NETWORK_ERROR,
            SubscribeResultCode.SESSION_EXPIRED,
            SubscribeResultCode.UNKNOWN,
        )


class OrderStatus(str, Enum):
    PENDING = "委托中"
    FILLED = "已成交"
    CANCELLED = "已撤销"
    UNKNOWN = "未知"


@dataclass
class Order:
    bond_code: str
    trade_date: date
    status: OrderStatus
    raw: str = ""


@dataclass
class HealthStatus:
    ok: bool
    message: str = ""


class BrokerAdapter(ABC):
    broker_name: ClassVar[str] = "base"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "__abstractmethods__", None) and cls.broker_name == "base":
            raise TypeError(f"{cls.__name__} must define broker_name class attribute")

    @abstractmethod
    def check_session(self) -> bool:
        """Return True if current session is valid (no network call required)."""
        ...

    @abstractmethod
    async def healthcheck(self) -> HealthStatus:
        """Attempt lightweight check: login page accessible, screenshot OK."""
        ...

    @abstractmethod
    async def login(self, credentials: dict) -> bool:
        """
        Attempt login with provided credentials dict.
        Returns True on success.
        """
        ...

    @abstractmethod
    def logout(self) -> None: ...

    @abstractmethod
    async def get_balance(self) -> float: ...

    @abstractmethod
    async def max_subscribe_amount(self, bond_code: str) -> int:
        """Return max units allowed for this bond subscription (usually 1000 for retail)."""
        ...

    @abstractmethod
    async def subscribe_bond(self, bond_code: str, amount: int) -> SubscribeResult: ...

    @abstractmethod
    async def query_today_orders(self) -> list[Order]:
        """Return all orders placed today for dedup/reconciliation."""
        ...
