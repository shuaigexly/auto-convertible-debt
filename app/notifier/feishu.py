import logging
import httpx
from app.notifier.base import NotifyChannel, NotifyMessage

logger = logging.getLogger(__name__)

class FeishuChannel(NotifyChannel):
    def __init__(self, webhook_url: str):
        self._url = webhook_url

    async def send(self, msg: NotifyMessage) -> None:
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": msg.title,
                        "content": [[{"tag": "text", "text": msg.body}]],
                    }
                }
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._url, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("Feishu webhook failed [%s]: %s", msg.title, exc)
                raise
        logger.info("Feishu notification sent: %s", msg.title)
