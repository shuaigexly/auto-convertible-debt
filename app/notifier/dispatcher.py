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

    wechat_url = os.environ.get("WECHAT_WEBHOOK_URL", "")
    if wechat_url:
        from app.notifier.wechat import WechatChannel

        channels.append(WechatChannel(wechat_url))

    smtp_host = os.environ.get("SMTP_HOST", "")
    if smtp_host:
        from app.notifier.email_sender import EmailChannel

        smtp_port = int(os.environ.get("SMTP_PORT", "465"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        notify_email_to = os.environ.get("NOTIFY_EMAIL_TO", "")
        to_addrs = [addr.strip() for addr in notify_email_to.split(",") if addr.strip()]
        if to_addrs:
            channels.append(EmailChannel(smtp_host, smtp_port, smtp_user, smtp_pass, to_addrs))

    _channels = channels
    return _channels


async def notify(msg: NotifyMessage) -> None:
    """Send msg via all configured channels. Never raises."""
    for ch in _get_channels():
        try:
            await ch.send_deduped(msg)
        except Exception as exc:
            logger.error("Notification channel error: %s", exc)
