# Linkwarden Telegram Bot

A Telegram bot that integrates with Linkwarden to save bookmarks directly from Telegram.

## Features

- Save links to your Linkwarden collection
- Rate limiting to prevent abuse
- SSRF protection for safe URL handling
- Configurable logging and limits

## Installation

### Using Docker

#### 1. Clone the repository

```bash
git clone https://github.com/orguetta/linkwarden-telegram-bot.git
cd linkwarden-telegram-bot
```

#### 2. Copy the example env file

```bash
cp example.env .env
```

#### 3. Edit the .env file and set the required environment variables

```bash
TELEGRAM_TOKEN=your_bot_token
LINKWARDEN_API_URL=https://your-linkwarden-instance.com
LINKWARDEN_API_KEY=your_api_key
LINKWARDEN_COLLECTION_ID=your_collection_id
```

#### 4. Build and run with Docker Compose

```bash
docker-compose up -d
```

### Manual Installation

```bash
pip install -r requirements.txt
```

### Set up environment variables

```bash
export TELEGRAM_TOKEN=your_bot_token
export LINKWARDEN_API_URL=https://your-linkwarden-instance.com
export LINKWARDEN_API_KEY=your_api_key
export LINKWARDEN_COLLECTION_ID=your_collection_id
```

### Run the bot

```bash
python bot.py
```

## Usage

### Adding Links

Send a message containing links to the bot. The bot will automatically extract HTTP/HTTPS URLs and add them to your specified Linkwarden collection.

### Example

1. Send a message to the bot:

```
Check out this cool website: https://example.com
```

2. The bot will respond:

```
Added 1 link(s) to Linkwarden
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_TOKEN` | Yes | - | Telegram bot token from BotFather |
| `LINKWARDEN_API_URL` | Yes | - | Linkwarden server URL |
| `LINKWARDEN_API_KEY` | Yes | - | Linkwarden API key |
| `LINKWARDEN_COLLECTION_ID` | Yes | - | Target collection ID |
| `LOG_LEVEL` | No | `WARNING` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `RATE_LIMIT_THRESHOLD` | No | `10` | Max messages per user per window |
| `RATE_LIMIT_WINDOW` | No | `60` | Rate limit window in seconds |
| `MAX_MESSAGE_SIZE` | No | `51200` | Max message size in bytes |
| `MAX_LINKS_PER_MESSAGE` | No | `10` | Max links per message |
| `ALLOW_LOCAL_LINKWARDEN` | No | `false` | Allow localhost/private API URLs |

## Badges

![Build Status](https://img.shields.io/github/actions/workflow/status/orguetta/linkwarden-telegram-bot/docker-publish.yml?branch=main)
![License](https://img.shields.io/github/license/orguetta/linkwarden-telegram-bot)
