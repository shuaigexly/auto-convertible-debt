import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.notifier.base import NotifyMessage, should_send, _DEDUP_CACHE, _DEDUP_WINDOW
from app.notifier.feishu import FeishuChannel
from app.notifier.wechat import WechatChannel
from app.notifier.email_sender import EmailChannel
from datetime import datetime, timedelta


def test_should_send_first_time():
    _DEDUP_CACHE.clear()
    msg = NotifyMessage(title="T1", body="B1")
    assert should_send(msg) is True


def test_should_send_no_write_without_send():
    """should_send() alone does not write to cache — only send_deduped does."""
    _DEDUP_CACHE.clear()
    msg = NotifyMessage(title="T2b", body="B2b")
    assert should_send(msg) is True
    assert should_send(msg) is True  # still True because cache was not written


def test_should_send_allows_after_window():
    _DEDUP_CACHE.clear()
    msg = NotifyMessage(title="T3", body="B3")
    import hashlib
    key = hashlib.md5(f"{msg.title}{msg.body}".encode()).hexdigest()
    # backdate the cache entry
    _DEDUP_CACHE[key] = datetime.utcnow() - timedelta(minutes=31)
    assert should_send(msg) is True


@pytest.mark.asyncio
async def test_feishu_channel_posts_to_webhook():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.notifier.feishu.httpx.AsyncClient", return_value=mock_client):
        ch = FeishuChannel("https://fake.feishu.webhook")
        await ch.send(NotifyMessage(title="Test", body="Body"))

    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[0][0] == "https://fake.feishu.webhook"


@pytest.mark.asyncio
async def test_wechat_channel_posts_to_webhook():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.notifier.wechat.httpx.AsyncClient", return_value=mock_client):
        ch = WechatChannel("https://fake.wechat.webhook")
        await ch.send(NotifyMessage(title="Test", body="Body"))

    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_email_channel_calls_smtp():
    msg = NotifyMessage(title="Subject", body="Body text")
    ch = EmailChannel("smtp.test.com", 465, "user@test.com", "pass", ["recv@test.com"])

    with patch("app.notifier.email_sender.smtplib.SMTP_SSL") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        await ch.send(msg)

    mock_smtp.login.assert_called_once_with("user@test.com", "pass")
    mock_smtp.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_send_deduped_skips_duplicate():
    _DEDUP_CACHE.clear()
    msg = NotifyMessage(title="Dup", body="Same")
    send_spy = AsyncMock()

    class _Ch(FeishuChannel):
        async def send(self, m):
            await send_spy(m)

    ch = _Ch("https://x")
    await ch.send_deduped(msg)
    await ch.send_deduped(msg)  # duplicate — should not call send again
    assert send_spy.call_count == 1


@pytest.mark.asyncio
async def test_send_deduped_writes_cache_on_success():
    _DEDUP_CACHE.clear()
    msg = NotifyMessage(title="Dup2", body="Same2")
    send_spy = AsyncMock()

    class _Ch(FeishuChannel):
        async def send(self, m):
            await send_spy(m)

    ch = _Ch("https://x")
    await ch.send_deduped(msg)  # writes cache
    await ch.send_deduped(msg)  # suppressed
    assert send_spy.call_count == 1
