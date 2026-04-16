from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from abc import ABC, abstractmethod
import hashlib
import threading

@dataclass
class NotifyMessage:
    title: str
    body: str
    level: str = "info"  # "info" | "warning" | "error"

_DEDUP_CACHE: dict[str, datetime] = {}
_DEDUP_WINDOW = timedelta(minutes=30)
_DEDUP_LOCK = threading.Lock()


def _dedup_key(msg: NotifyMessage) -> str:
    return hashlib.md5(f"{msg.title}{msg.body}".encode()).hexdigest()


def should_send(msg: NotifyMessage) -> bool:
    """Return True if message has not been sent within the dedup window."""
    key = _dedup_key(msg)
    now = datetime.now(timezone.utc)
    with _DEDUP_LOCK:
        expired = [cache_key for cache_key, sent_at in _DEDUP_CACHE.items() if now - sent_at >= _DEDUP_WINDOW]
        for cache_key in expired:
            del _DEDUP_CACHE[cache_key]
        last = _DEDUP_CACHE.get(key)
        return not (last and now - last < _DEDUP_WINDOW)


class NotifyChannel(ABC):
    @abstractmethod
    async def send(self, msg: NotifyMessage) -> None:
        """Send message unconditionally."""
        ...

    async def send_deduped(self, msg: NotifyMessage) -> None:
        """Send only if not a duplicate within 30 min. Records send only on success."""
        if not should_send(msg):
            return
        await self.send(msg)
        key = _dedup_key(msg)
        with _DEDUP_LOCK:
            _DEDUP_CACHE[key] = datetime.now(timezone.utc)
