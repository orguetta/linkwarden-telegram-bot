import os
import logging
import time
import asyncio
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.error import Conflict, TelegramError, TimedOut, NetworkError
import requests
import re
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from collections import defaultdict
from datetime import datetime, timedelta

# Set up logging
logging_level = os.environ.get('LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging_level)
logger = logging.getLogger(__name__)

# Environment variables - validate at startup
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
LINKWARDEN_API_URL = os.environ.get('LINKWARDEN_API_URL')
LINKWARDEN_API_KEY = os.environ.get('LINKWARDEN_API_KEY')
LINKWARDEN_COLLECTION_ID = os.environ.get('LINKWARDEN_COLLECTION_ID')

# Validate required environment variables
if not all([TELEGRAM_TOKEN, LINKWARDEN_API_URL, LINKWARDEN_API_KEY, LINKWARDEN_COLLECTION_ID]):
    logger.error("Missing required environment variables: TELEGRAM_TOKEN, LINKWARDEN_API_URL, LINKWARDEN_API_KEY, LINKWARDEN_COLLECTION_ID")
    sys.exit(1)

# Rate limiting: max 10 messages per user per minute
RATE_LIMIT_THRESHOLD = int(os.environ.get('RATE_LIMIT_THRESHOLD', 10))
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', 60))  # seconds
user_message_history = defaultdict(list)

# Message size limit (50KB)
MAX_MESSAGE_SIZE = int(os.environ.get('MAX_MESSAGE_SIZE', 51200))

# Configure requests to retry on failure
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# SSRF protection: validate Linkwarden API URL
def validate_api_url() -> None:
    """Validate that LINKWARDEN_API_URL is safe and well-formed."""
    try:
        parsed = urlparse(LINKWARDEN_API_URL)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
        if not parsed.hostname:
            raise ValueError("Invalid URL: no hostname")
        # Reject private/local APIs unless explicitly enabled
        if parsed.hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):  # nosec B104
            allow_local = os.environ.get('ALLOW_LOCAL_LINKWARDEN', 'false').lower() == 'true'
            if not allow_local:
                raise ValueError("Local Linkwarden instances not allowed. Set ALLOW_LOCAL_LINKWARDEN=true to enable.")
    except Exception as e:
        logger.error(f"Invalid LINKWARDEN_API_URL: {e}")
        sys.exit(1)

validate_api_url()

async def start(update: Update, context: CallbackContext) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, 
                                   text="Send me a message with links, and I'll add them to Linkwarden!")

def extract_links(text: str) -> list:
    """Extract URLs from text using urllib.parse for better validation."""
    import ipaddress
    
    # Simple pattern to identify potential URLs
    url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
    matches = url_pattern.findall(text)
    
    valid_urls = []
    for url in matches:
        try:
            # Validate URL structure
            parsed = urlparse(url)
            
            # Reject non-http/https
            if parsed.scheme not in ('http', 'https'):
                continue
            
            # Reject URLs without hostname
            if not parsed.hostname:
                continue
            
            hostname = parsed.hostname.lower()
            
            # Reject private/local addresses (SSRF protection)
            blocked_hosts = {
                'localhost', '127.0.0.1', '0.0.0.0', '::1', '::',  # nosec B104
                '169.254.169.254'  # AWS metadata service
            }
            
            if hostname in blocked_hosts:
                logger.debug(f"Rejected blocked hostname: {hostname}")
                continue
            
            # Reject private IP ranges
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    logger.debug(f"Rejected private IP: {hostname}")
                    continue
            except ValueError:
                # Not an IP, continue with hostname validation
                pass
            
            # Additional validation: reject known internal TLDs
            if hostname.endswith(('.local', '.internal', '.localhost', '.test', '.invalid')):
                logger.debug(f"Rejected internal TLD: {hostname}")
                continue
            
            valid_urls.append(url)
        except Exception as e:
            logger.debug(f"Invalid URL rejected: {e}")
            continue
    
    return valid_urls

def add_to_linkwarden(url: str) -> bool:
    """Add link to Linkwarden with validation and error handling."""
    headers = {
        'Authorization': f'Bearer {LINKWARDEN_API_KEY}',
        'Content-Type': 'application/json',
        'User-Agent': 'linkwarden-telegram-bot/1.0',  # Identify bot
        'Accept': 'application/json',
    }
    data = {
        'url': url,
        'collectionId': LINKWARDEN_COLLECTION_ID,
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = http.post(
                f'{LINKWARDEN_API_URL}/api/v1/links',
                json=data,
                headers=headers,
                timeout=10,
                verify=True  # Always verify SSL certificates
            )
            response.raise_for_status()
            
            # Validate response structure
            try:
                resp_json = response.json()
                if 'id' not in resp_json:
                    logger.warning(f"Unexpected API response: missing 'id' field")
                    return False
            except ValueError:
                logger.warning(f"Unexpected API response format")
                return False
            
            logger.info(f"Successfully added link to Linkwarden")
            return True
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed: Timeout. Retrying...")
                time.sleep(2 ** attempt)
            else:
                logger.error(f"Failed to add link after {max_retries} attempts: Timeout")
                return False
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error occurred while adding link")
            return False
        except requests.exceptions.SSLError:
            logger.error(f"SSL certificate verification failed for Linkwarden API")
            return False
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error(f"Authentication failed: Invalid API key")
            elif response.status_code == 403:
                logger.error(f"Authorization failed: Check API key permissions")
            else:
                logger.error(f"HTTP {response.status_code} error occurred")
            return False
        except requests.RequestException:
            logger.error(f"Failed to add link to Linkwarden")
            return False

def check_rate_limit(user_id: int) -> bool:
    """Check if user has exceeded rate limit."""
    now = datetime.now()
    cutoff_time = now - timedelta(seconds=RATE_LIMIT_WINDOW)
    
    # Remove old messages outside the window
    user_message_history[user_id] = [
        msg_time for msg_time in user_message_history[user_id]
        if msg_time > cutoff_time
    ]
    
    # Check if over limit
    if len(user_message_history[user_id]) >= RATE_LIMIT_THRESHOLD:
        return False
    
    # Add current message
    user_message_history[user_id].append(now)
    return True

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle incoming messages with rate limiting and validation."""
    user_id = update.effective_user.id
    
    # Rate limiting check
    if not check_rate_limit(user_id):
        await send_message_with_retry(update, context, "⚠️ Rate limit exceeded. Max 10 messages per minute.")
        logger.warning(f"User {user_id} exceeded rate limit")
        return
    
    # Message size validation
    message = update.message.text
    if not message or len(message) > MAX_MESSAGE_SIZE:
        await send_message_with_retry(update, context, "⚠️ Message too large or empty. Please send smaller messages.")
        return
    
    # Check for suspicious patterns (basic injection detection)
    if any(pattern in message.lower() for pattern in ['javascript:', 'data:', 'vbscript:', 'file://']):
        await send_message_with_retry(update, context, "⚠️ Suspicious content detected. Only HTTP/HTTPS URLs are supported.")
        logger.warning(f"User {user_id} attempted to send suspicious content")
        return

    links = extract_links(message)
    
    if not links:
        await send_message_with_retry(update, context, "No links found in the message.")
        return

    # Limit number of links per message (prevent spam)
    MAX_LINKS_PER_MESSAGE = int(os.environ.get('MAX_LINKS_PER_MESSAGE', 10))
    if len(links) > MAX_LINKS_PER_MESSAGE:
        await send_message_with_retry(
            update, context,
            f"⚠️ Too many links. Maximum {MAX_LINKS_PER_MESSAGE} links per message."
        )
        logger.warning(f"User {user_id} sent {len(links)} links (limit: {MAX_LINKS_PER_MESSAGE})")
        return

    successful_links = 0
    failed_links = 0

    for link in links:
        if add_to_linkwarden(link):
            successful_links += 1
        else:
            failed_links += 1

    response = f"✅ Added {successful_links} link(s) to Linkwarden"
    if failed_links:
        response += f"\n\n⚠️ Failed to add {failed_links} link(s)"

    await send_message_with_retry(update, context, response)

async def send_message_with_retry(update: Update, context: CallbackContext, text: str, max_retries: int = 3) -> None:
    for attempt in range(max_retries):
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
            return
        except TimedOut as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(f"Failed to send message after {max_retries} attempts: {e}")
                raise

async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    if isinstance(context.error, (TimedOut, NetworkError)):
        logger.info("Network error occurred. The message might have been sent despite the error.")
    elif update and update.effective_chat:
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, 
                                           text="An error occurred. The developer has been notified.")
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    while True:
        try:
            application.run_polling(timeout=10, poll_interval=10)  # Set poll_interval to 10 seconds
        except Conflict:
            logger.error("Conflict error occurred. Waiting before restarting...")
            time.sleep(30)
        except NetworkError as e:
            logger.error(f"Network error occurred: {e}. Restarting...")
            time.sleep(10)
        except TelegramError as e:
            logger.error(f"TelegramError occurred: {e}. Waiting before restarting...")
            time.sleep(30)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}. Exiting...")
            break

if __name__ == '__main__':
    main()
