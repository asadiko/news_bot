# 📰 NewsBot

Telegram news aggregator bot. Monitors RSS feeds for keywords and posts matching articles to a channel.

---

## Features

- ⚡ **Concurrent async fetching** — all feeds fetched simultaneously
- 🗄️ **JSON database** — lightweight, no external DB needed
- 🧹 **Auto-purge** — old seen links cleaned up automatically
- 🔍 **Smart keyword matching** — word-boundary aware, any language
- 📡 **Admin commands** — add/remove keywords and feeds live via Telegram
- 🐳 **Docker ready** — one command deploy
- 🚀 **Free deployment** — works on Railway, Render, Fly.io

---

## Setup

### 1. Configure

Edit `config.py`:
```python
TOKEN = "your_bot_token"          # from @BotFather
CHANNEL_ID = "@YourChannel"       # your channel username
ADMIN_IDS = [123456789]           # your Telegram user ID (get from @userinfobot)
```

Edit `data.json` to set your initial keywords and feeds (or add them via bot commands later).

### 2. Install & Run Locally

```bash
pip install -r requirements.txt
python bot.py
```

---

## Free Deployment Options

### 🚂 Railway (Recommended — easiest)

1. Push code to a GitHub repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Set environment variables:
   - `TOKEN` = your bot token
   - `CHANNEL_ID` = @YourChannel
4. Deploy — done. Free tier gives 500 hours/month.

> **Persistent storage on Railway:** Add a Volume mount at `/app` so `data.json` survives redeploys.

### 🎨 Render

1. Push to GitHub
2. Go to [render.com](https://render.com) → New → Web Service → Docker
3. Set env vars: `TOKEN`, `CHANNEL_ID`
4. Free tier available (spins down after inactivity — not ideal for bots)

### 🪂 Fly.io

```bash
fly launch
fly secrets set TOKEN=your_token CHANNEL_ID=@channel
fly deploy
```

Free tier: 3 shared VMs. Good for bots.

### 🐳 Any VPS with Docker

```bash
docker build -t newsbot .
docker run -d \
  -e TOKEN=your_token \
  -e CHANNEL_ID=@YourChannel \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  newsbot
```

---

## Using Environment Variables (recommended for deployment)

Instead of hardcoding in `config.py`, you can modify it to read from env:

```python
import os
TOKEN = os.environ.get("TOKEN", "fallback_token")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@NEWSforEMB")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(",") if os.environ.get("ADMIN_IDS") else []))
```

---

## Admin Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/keywords` | List current keywords |
| `/addkeyword <word>` | Add a keyword (any language) |
| `/removekeyword <word>` | Remove a keyword |
| `/feeds` | List all RSS feeds |
| `/addfeed <url>` | Add an RSS feed URL |
| `/removefeed <url>` | Remove an RSS feed |
| `/stats` | Show bot statistics |
| `/runnow` | Trigger immediate news check |

---

## File Structure

```
newsbot/
├── bot.py            # Main bot + scheduler + commands
├── fetcher.py        # Async RSS fetching + keyword matching
├── db.py             # JSON database layer
├── config.py         # Settings
├── data.json         # Keywords, feeds, seen links (auto-managed)
├── requirements.txt
├── Dockerfile
├── railway.toml
└── .gitignore
```
