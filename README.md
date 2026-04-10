# Science News Bot

A Telegram bot that fetches science articles from RSS feeds daily, uses Claude AI to pick the top 5 most interesting ones, and posts a formatted digest to your Telegram channel.

---

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/settings/keys)
- A Telegram bot token (see below)
- A Telegram channel where your bot is an admin

---

## Step 1 — Create a Telegram Bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (pick a name and username).
3. BotFather will give you a token like `123456789:ABCdef...` — copy it.

## Step 2 — Get your Channel ID

**Option A — public channel:**
Your channel ID is simply its username with an `@` prefix, e.g. `@mysciencechannel`.

**Option B — private channel (numeric ID):**
1. Forward any message from the private channel to [@userinfobot](https://t.me/userinfobot).
2. It will reply with a chat ID that looks like `-1001234567890`.

Then **add your bot as an administrator** of the channel with permission to post messages:
- Open the channel → Edit → Administrators → Add Admin → search for your bot.

## Step 3 — Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Step 4 — Configure secrets

```bash
cp .env.example .env
```

Edit `.env` and fill in the three required values:

```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHANNEL_ID=@mysciencechannel
```

Optionally change `DIGEST_TIME` (default `09:00`, 24-hour format, server local time).

## Step 5 — Run

**Start the scheduler** (posts every day at the configured time):
```bash
python bot.py
```

**Send one digest immediately** (great for testing):
```bash
python bot.py --now
```

---

## Project structure

```
science-news-aggregator/
├── bot.py          # Entry point; scheduler loop
├── fetcher.py      # RSS feed fetching and HTML stripping
├── ai.py           # Claude API call: ranking + plain-language summaries
├── publisher.py    # Telegram message formatting and posting
├── .env.example    # Secret template
├── requirements.txt
└── README.md
```

## RSS sources

| Source | Feed |
|---|---|
| ScienceDaily | Top science |
| ScienceDaily Space | Space & time |
| NASA | Breaking news |
| arXiv | cs.AI preprints |
| arXiv | Physics preprints |
| Nature | nature.com |
| PubMed | Trending research |

Up to 5 articles are fetched per feed. All articles are passed to Claude, which selects the 5 most broadly interesting ones and writes plain-language explanations.

## Digest format

```
🔬 Daily Science Digest — April 9, 2026

🧬 Title of article
Brief AI-written explanation here.
Read more

... (5 articles total)
```

## Troubleshooting

- **Bot not posting** — confirm the bot is an admin in the channel with "Post Messages" permission.
- **`chat not found` error** — double-check `TELEGRAM_CHANNEL_ID` (include the `@` for public channels).
- **Claude returns invalid JSON** — usually a transient API issue; re-run with `--now` to retry.
- **Feed fetch warnings** — some feeds (e.g. Nature) require a valid User-Agent; `feedparser` sends one by default, but corporate proxies may block it.
