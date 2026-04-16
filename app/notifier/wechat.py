import logging
import httpx
from app.notifier.base import NotifyChannel, NotifyMessage

logger = logging.getLogger(__name__)

class WechatChannel(NotifyChannel):
    def __init__(self, webhook_url: str):
        self._url = webhook_url

    async def send(self, msg: NotifyMessage) -> None:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {msg.title}\n{msg.body}",
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._url, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("WeChat webhook failed [%s]: %s", msg.title, exc)
                raise
        logger.info("WeChat notification sent: %s", msg.title)
