# ping 🤖

A Telegram bot that monitors other Telegram bots and reports their uptime status.

## Features

- Pings configured bots at a set interval (minimum 10s) using the Telegram `getMe` API
- Marks each bot as **ACTIVE** or **INACTIVE**
- Posts and continuously updates a live status dashboard in a configured channel
- Fully manageable via the bot's DM — no server access needed after setup
- Config persisted in `config.json`

## Setup

### 1. Create the bot

Talk to [@BotFather](https://t.me/BotFather), create a new bot, and grab the token.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run

```bash
BOT_TOKEN=your_token_here python bot.py
```

Or with a `.env` file (using `python-dotenv`):

```
BOT_TOKEN=your_token_here
```

## Bot Commands

| Command | Description |
|---|---|
| `/add <username> <token> [interval]` | Add a bot to monitor. Interval defaults to 30s (min 10s). |
| `/remove <username>` | Remove a bot from monitoring. |
| `/list` | List all monitored bots. |
| `/status` | Show current status of all bots inline. |
| `/setchannel <channel_id>` | Set the channel where the live dashboard is posted. |
| `/help` | Show command reference. |

## Channel Dashboard

Once you `/setchannel`, the bot will post a single message in that channel and keep editing it with live status updates every few seconds. The message is also pinned automatically.

Make sure the Ping Bot is an **admin** in the channel with permission to post and pin messages.

## Config file

`config.json` is created automatically. Example structure:

```json
{
  "bots": {
    "mybot": {
      "token": "123456:ABC-DEF",
      "interval": 30,
      "status": "ACTIVE",
      "uptime_start": 1709000000.0,
      "last_check": 1709001234.0
    }
  },
  "channel_id": -1001234567890,
  "status_message_id": 42
}
```

## Docker (optional)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t ping-bot .
docker run -d -e BOT_TOKEN=your_token -v $(pwd)/config.json:/app/config.json ping-bot
```
