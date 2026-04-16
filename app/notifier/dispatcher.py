"""Thin notification dispatcher — reads channel config from env, fires-and-forgets."""

import logging
import os

from app.notifier.base import NotifyChannel, NotifyMessage

logger = logging.getLogger(__name__)

_channels: list[NotifyChannel] | None = None


def _get_channels() -> list[NotifyChannel]:
    global _channels
    if _channels is not None:
        return _channels
    channels: list[NotifyChannel] = []
    feishu_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if feishu_url:
        from app.notifier.feishu import FeishuChannel

        channels.append(FeishuChannel(feishu_url))
    _channels = channels
    return _channels


async def notify(msg: NotifyMessage) -> None:
    """Send msg via all configured channels. Never raises."""
    for ch in _get_channels():
        try:
            await ch.send_deduped(msg)
        except Exception as exc:
            logger.error("Notification channel error: %s", exc)
