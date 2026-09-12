# Telegram Broker Bot with Google Gemini AI

An automated Telegram bot that listens to source Telegram channels, automatically strips competitor details/phone numbers, extracts item specifications using **Google Gemini AI**, inserts your broker contact details, and provides a 1-click preview button to post directly to your channel!

---

## 🌟 Key Features

1. **Auto Channel Listener**: Real-time MTProto listener that detects new posts in source channels as soon as they are published.
2. **Gemini AI Content Transformer**:
   - Strips old sender headers, timestamps, photo counters.
   - Strips seller phone numbers & competitor links.
   - Standardizes specs with structured emojis.
   - Appends your broker phone number & Telegram handle.
3. **Manual Forward Handler**: Forward ANY message directly to your Bot in private chat to get instant Gemini formatting.
4. **1-Click Approval UI**: Interactive Telegram buttons (`[ 🚀 Post to My Channel ]`, `[ ❌ Discard ]`).
5. **Media Support**: Automatically keeps original photos/media attached to the post.

---

## 🛠️ Quick Setup Guide

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure `.env` File

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Fill in your API keys in `.env`:

- `TELEGRAM_API_ID` & `TELEGRAM_API_HASH`: Get from [my.telegram.org](https://my.telegram.org)
- `TELEGRAM_BOT_TOKEN`: Get from [@BotFather](https://t.me/BotFather) on Telegram
- `GEMINI_API_KEY`: Get free from [Google AI Studio](https://aistudio.google.com/)
- `MY_TELEGRAM_USER_ID`: Your Telegram numeric User ID (get from [@userinfobot](https://t.me/userinfobot))
- `TARGET_CHANNEL_ID`: Your channel username (e.g. `@my_broker_channel`)
- `BROKER_PHONE`: Your contact phone number
- `BROKER_TELEGRAM_HANDLE`: Your Telegram handle (e.g. `@my_broker_username`)
- `SOURCE_CHANNELS`: Comma-separated list of target source channels to auto-listen (e.g. `@source_chan1, @source_chan2`)

---

## 🚀 Running the Bot

```bash
python bot.py
```

### Testing with Manual Forward:
1. Open your Bot on Telegram.
2. Send `/start`.
3. Forward any post (like the laptop listing) to your Bot.
4. The bot will return a Gemini-formatted preview with `[🚀 Post to My Channel]` button!
