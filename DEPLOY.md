# How to deploy the Bulgarian Flashcards Bot

## Step 1 — Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts, pick a name and username (e.g. `BulgarianFlashcardsBot`)
4. BotFather will give you a **token** like `7123456789:AAF...` — copy it

---

## Step 2 — Deploy on Render.com (free, always-on)

1. Go to [render.com](https://render.com) and create a free account
2. Click **New → Web Service**
3. Connect your GitHub account and push this folder as a repository  
   *(or use "Deploy from Git URL" if you already have it on GitHub)*
4. Render auto-detects `render.yaml` — confirm the service settings
5. Under **Environment Variables**, add:
   - `BOT_TOKEN` → paste your token from BotFather
   - `WEBHOOK_URL` → Render will show you the public URL for your service
     (looks like `https://bulgarian-flashcards-bot.onrender.com`)
     Set `WEBHOOK_URL` to that exact URL.
6. Click **Create Web Service** → Render builds and starts the bot

> **Free tier note:** Render free services spin down after 15 min of no traffic.  
> To keep it always awake, use [UptimeRobot](https://uptimerobot.com) (free)  
> to ping your service URL every 5 minutes.

---

## Alternative: Railway.app

1. Go to [railway.app](https://railway.app) and log in with GitHub
2. **New Project → Deploy from GitHub repo**
3. Set environment variables:
   - `BOT_TOKEN` → your token
   - Leave `WEBHOOK_URL` empty (Railway will use polling mode automatically)
4. Deploy — Railway gives 500 free hours/month

---

## Local testing

```bash
pip install -r requirements.txt
set BOT_TOKEN=your_token_here   # Windows
python bot.py
```

The bot will use polling mode locally (no WEBHOOK_URL needed).

---

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome screen + main menu |
| `/menu` | Show main menu |
| `/stats` | Show your learning progress |

## Features

- **25 categories**, ~1500 words
- **Flashcard mode** — tap to reveal, mark known/unknown
- **Quiz mode** — 4-choice multiple choice
- **Random word** — instant vocabulary lookup
- **Progress tracking** — per-user stats
