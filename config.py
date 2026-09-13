import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file (with override=True to prioritize .env)
load_dotenv(override=True)

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MY_TELEGRAM_USER_ID = int(os.getenv("MY_TELEGRAM_USER_ID", "0"))

SETTINGS_FILE = "settings.json"

def get_default_settings():
    raw_sources = os.getenv("SOURCE_CHANNELS", "")
    sources = [s.strip() for s in raw_sources.split(",") if s.strip()]
    return {
        "source_channels": sources if sources else ["@computersssd"],
        "target_channel": os.getenv("TARGET_CHANNEL_ID", "@BLESSCOMPUTER"),
        "price_markup": 0,  # e.g. +2000 or -1000 Birr
        "broker_phone": os.getenv("BROKER_PHONE", "0932439212"),
        "broker_handle": os.getenv("BROKER_TELEGRAM_HANDLE", "@cooking_candy")
    }

def load_settings():
    defaults = get_default_settings()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            print(f"[Config Warning] Failed to load settings.json: {e}")
    return defaults

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Config Error] Failed to save settings.json: {e}")

# Dynamic settings state
settings_state = load_settings()

def get_source_channels():
    return settings_state.get("source_channels", [])

def add_source_channel(channel: str):
    channel = channel.strip()
    if not channel.startswith("@") and not channel.startswith("-100"):
        channel = "@" + channel
    channels = settings_state.get("source_channels", [])
    if channel not in channels:
        channels.append(channel)
        settings_state["source_channels"] = channels
        save_settings(settings_state)
        return True
    return False

def remove_source_channel(channel: str):
    channel = channel.strip()
    channels = settings_state.get("source_channels", [])
    matched = [c for c in channels if c.lower() == channel.lower() or c.lower() == f"@{channel.lower()}"]
    if matched:
        for m in matched:
            channels.remove(m)
        settings_state["source_channels"] = channels
        save_settings(settings_state)
        return True
    return False

def get_price_markup():
    return settings_state.get("price_markup", 0)

def set_price_markup(markup: int):
    settings_state["price_markup"] = markup
    save_settings(settings_state)

def get_broker_phone():
    return settings_state.get("broker_phone", "0932439212")

def set_broker_phone(phone: str):
    settings_state["broker_phone"] = phone.strip()
    save_settings(settings_state)

def get_broker_handle():
    return settings_state.get("broker_handle", "@cooking_candy")

def set_broker_handle(handle: str):
    handle = handle.strip()
    if not handle.startswith("@"):
        handle = "@" + handle
    settings_state["broker_handle"] = handle
    save_settings(settings_state)

def get_target_channel():
    return settings_state.get("target_channel", os.getenv("TARGET_CHANNEL_ID", "@BLESSCOMPUTER"))

def set_target_channel(channel: str):
    channel = channel.strip()
    if not channel.startswith("@") and not channel.startswith("-100"):
        channel = "@" + channel
    settings_state["target_channel"] = channel
    save_settings(settings_state)
