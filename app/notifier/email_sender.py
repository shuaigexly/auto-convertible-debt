import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from app.notifier.base import NotifyChannel, NotifyMessage

logger = logging.getLogger(__name__)

class EmailChannel(NotifyChannel):
    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str, to_addrs: list[str]):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._to_addrs = to_addrs

    def _send_sync(self, msg: NotifyMessage) -> None:
        mime = MIMEText(msg.body, "plain", "utf-8")
        mime["Subject"] = msg.title
        mime["From"] = self._username
        mime["To"] = ", ".join(self._to_addrs)
        with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port) as smtp:
            smtp.login(self._username, self._password)
            smtp.sendmail(self._username, self._to_addrs, mime.as_string())

    async def send(self, msg: NotifyMessage) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_sync, msg)
        logger.info("Email notification sent: %s", msg.title)
