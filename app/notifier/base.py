from dataclasses import dataclass
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import hashlib

@dataclass
class NotifyMessage:
    title: str
    body: str
    level: str = "info"  # "info" | "warning" | "error"

_DEDUP_CACHE: dict[str, datetime] = {}
_DEDUP_WINDOW = timedelta(minutes=30)

def should_send(msg: NotifyMessage) -> bool:
    """Return True if message should be sent (not a duplicate within 30 min)."""
    key = hashlib.md5(f"{msg.title}{msg.body}".encode()).hexdigest()
    now = datetime.utcnow()
    last = _DEDUP_CACHE.get(key)
    if last and now - last < _DEDUP_WINDOW:
        return False
    _DEDUP_CACHE[key] = now
    return True

class NotifyChannel(ABC):
    @abstractmethod
    async def send(self, msg: NotifyMessage) -> None:
        """Send message unconditionally."""
        ...

    async def send_deduped(self, msg: NotifyMessage) -> None:
        """Send only if not a duplicate within 30 min."""
        if should_send(msg):
            await self.send(msg)
