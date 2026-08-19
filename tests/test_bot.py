import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

# Set required environment variables before importing bot
os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('LINKWARDEN_API_URL', 'https://linkwarden.example.com')
os.environ.setdefault('LINKWARDEN_API_KEY', 'test-api-key')
os.environ.setdefault('LINKWARDEN_COLLECTION_ID', '1')

from bot import (
    extract_links,
    add_to_linkwarden,
    handle_message,
    start,
    send_message_with_retry,
    error_handler,
    check_rate_limit,
    user_message_history,
    RATE_LIMIT_THRESHOLD,
)


@pytest.fixture
def mock_update():
    mock = MagicMock()
    mock.effective_chat.id = 12345
    mock.effective_user.id = 100
    mock.message.text = "Check out this link: https://example.com"
    return mock


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


class TestExtractLinks:
    def test_extracts_basic_urls(self):
        text = "Here are some links: https://example.com and http://test.com"
        links = extract_links(text)
        assert links == ["https://example.com", "http://test.com"]

    def test_rejects_localhost(self):
        links = extract_links("Visit http://localhost/admin")
        assert links == []

    def test_rejects_private_ip(self):
        links = extract_links("Visit http://192.168.1.1/admin")
        assert links == []

    def test_rejects_loopback(self):
        links = extract_links("Visit http://127.0.0.1/admin")
        assert links == []

    def test_rejects_aws_metadata(self):
        links = extract_links("Visit http://169.254.169.254/latest/meta-data/")
        assert links == []

    def test_rejects_internal_tld(self):
        links = extract_links("Visit http://myserver.local/file")
        assert links == []

    def test_no_links(self):
        links = extract_links("No links here")
        assert links == []

    def test_multiple_links(self):
        text = "https://a.com https://b.com http://c.org/path?q=1"
        links = extract_links(text)
        assert len(links) == 3

    def test_rejects_empty_hostname(self):
        links = extract_links("https:///path")
        assert links == []


class TestAddToLinkwarden:
    @patch('bot.http.post')
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'id': 1, 'url': 'https://example.com'}
        mock_post.return_value = mock_resp

        result = add_to_linkwarden("https://example.com")
        assert result is True

    @patch('bot.http.post')
    def test_failure_500(self, mock_post):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError(response=mock_resp)
        mock_post.return_value = mock_resp

        result = add_to_linkwarden("https://example.com")
        assert result is False

    @patch('bot.http.post')
    def test_failure_connection_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError()

        result = add_to_linkwarden("https://example.com")
        assert result is False

    @patch('bot.http.post')
    def test_failure_ssl_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.SSLError()

        result = add_to_linkwarden("https://example.com")
        assert result is False

    @patch('bot.time.sleep', return_value=None)
    @patch('bot.http.post')
    def test_retry_on_timeout(self, mock_post, mock_sleep):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'id': 1}
        mock_post.side_effect = [
            req.exceptions.Timeout(),
            req.exceptions.Timeout(),
            mock_resp,
        ]

        result = add_to_linkwarden("https://example.com")
        assert result is True
        assert mock_post.call_count == 3

    @patch('bot.http.post')
    def test_response_without_id(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'url': 'https://example.com'}
        mock_post.return_value = mock_resp

        result = add_to_linkwarden("https://example.com")
        assert result is False

    @patch('bot.http.post')
    def test_auth_failure(self, mock_post):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError(response=mock_resp)
        mock_post.return_value = mock_resp

        result = add_to_linkwarden("https://example.com")
        assert result is False


class TestRateLimit:
    def setup_method(self):
        user_message_history.clear()

    def test_allows_within_limit(self):
        assert check_rate_limit(999) is True

    def test_blocks_over_limit(self):
        for _ in range(RATE_LIMIT_THRESHOLD):
            check_rate_limit(888)
        assert check_rate_limit(888) is False

    def test_different_users_independent(self):
        for _ in range(RATE_LIMIT_THRESHOLD):
            check_rate_limit(777)
        assert check_rate_limit(666) is True


class TestHandleMessage:
    @pytest.mark.asyncio
    @patch('bot.add_to_linkwarden', return_value=True)
    @patch('bot.send_message_with_retry', new_callable=AsyncMock)
    @patch('bot.check_rate_limit', return_value=True)
    async def test_successful_links(self, mock_rate, mock_send, mock_add, mock_update, mock_context):
        await handle_message(mock_update, mock_context)
        mock_send.assert_called_once()
        call_text = mock_send.call_args[0][2]
        assert "1 link(s)" in call_text

    @pytest.mark.asyncio
    @patch('bot.send_message_with_retry', new_callable=AsyncMock)
    @patch('bot.check_rate_limit', return_value=True)
    async def test_no_links(self, mock_rate, mock_send, mock_update, mock_context):
        mock_update.message.text = "No links here"
        await handle_message(mock_update, mock_context)
        mock_send.assert_called_once_with(mock_update, mock_context, "No links found in the message.")

    @pytest.mark.asyncio
    @patch('bot.send_message_with_retry', new_callable=AsyncMock)
    async def test_rate_limited(self, mock_send, mock_update, mock_context):
        with patch('bot.check_rate_limit', return_value=False):
            await handle_message(mock_update, mock_context)
        mock_send.assert_called_once()
        assert "Rate limit" in mock_send.call_args[0][2]

    @pytest.mark.asyncio
    @patch('bot.send_message_with_retry', new_callable=AsyncMock)
    @patch('bot.check_rate_limit', return_value=True)
    async def test_empty_message(self, mock_rate, mock_send, mock_update, mock_context):
        mock_update.message.text = ""
        await handle_message(mock_update, mock_context)
        mock_send.assert_called_once()
        assert "too large or empty" in mock_send.call_args[0][2].lower()

    @pytest.mark.asyncio
    @patch('bot.send_message_with_retry', new_callable=AsyncMock)
    @patch('bot.check_rate_limit', return_value=True)
    async def test_suspicious_content(self, mock_rate, mock_send, mock_update, mock_context):
        mock_update.message.text = "javascript:alert(1)"
        await handle_message(mock_update, mock_context)
        mock_send.assert_called_once()
        assert "Suspicious" in mock_send.call_args[0][2]

    @pytest.mark.asyncio
    @patch('bot.send_message_with_retry', new_callable=AsyncMock)
    @patch('bot.check_rate_limit', return_value=True)
    async def test_too_many_links(self, mock_rate, mock_send, mock_update, mock_context):
        links = " ".join([f"https://site{i}.com" for i in range(15)])
        mock_update.message.text = links
        await handle_message(mock_update, mock_context)
        mock_send.assert_called_once()
        assert "Too many links" in mock_send.call_args[0][2]


class TestSendMessageWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self, mock_update, mock_context):
        await send_message_with_retry(mock_update, mock_context, "hello")
        mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self, mock_update, mock_context):
        from telegram.error import TimedOut
        mock_context.bot.send_message.side_effect = [TimedOut(), TimedOut(), None]
        await send_message_with_retry(mock_update, mock_context, "hello")
        assert mock_context.bot.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, mock_update, mock_context):
        from telegram.error import TimedOut
        mock_context.bot.send_message.side_effect = TimedOut()
        with pytest.raises(TimedOut):
            await send_message_with_retry(mock_update, mock_context, "hello", max_retries=2)
        assert mock_context.bot.send_message.call_count == 2


class TestErrorHandler:
    @pytest.mark.asyncio
    async def test_logs_error(self, mock_update, mock_context):
        mock_context.error = Exception("Test error")
        await error_handler(mock_update, mock_context)
        mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_no_message(self, mock_update, mock_context):
        from telegram.error import TimedOut
        mock_context.error = TimedOut()
        await error_handler(mock_update, mock_context)
        mock_context.bot.send_message.assert_not_called()


class TestStart:
    @pytest.mark.asyncio
    async def test_start_sends_welcome(self, mock_update, mock_context):
        await start(mock_update, mock_context)
        mock_context.bot.send_message.assert_called_once()
        text = mock_context.bot.send_message.call_args[1]['text']
        assert "Linkwarden" in text
