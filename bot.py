import os
import sys
import asyncio
import logging

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

import config
from gemini_service import process_post_with_gemini

# ----------------------------------------------------
# Colored / Styled End-to-End Logger Setup
# ----------------------------------------------------
class CustomFormatter(logging.Formatter):
    def format(self, record):
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        prefix = f"[{record.levelname}]"
        return f"{timestamp} {prefix} {record.getMessage()}"

logger = logging.getLogger("BrokerBot")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)

# ----------------------------------------------------
# Global Bot State
# ----------------------------------------------------
pending_posts = {}
user_states = {}  # user_id -> {"action": str, "post_id": str}
post_counter = 0

TEMP_MEDIA_DIR = "temp_media"
os.makedirs(TEMP_MEDIA_DIR, exist_ok=True)

bot = TelegramClient('broker_bot_session', config.API_ID, config.API_HASH)

user_client = None
if config.API_ID and config.API_HASH:
    user_client = TelegramClient('broker_user_session', config.API_ID, config.API_HASH)

def has_downloadable_media(event):
    """Check if the event contains actual downloadable photo or document media."""
    return bool(event.photo or event.document)

def get_post_link(event):
    """Constructs direct t.me link to the original source post for broker reference."""
    try:
        chat = getattr(event, 'chat', None)
        msg_id = getattr(event.message, 'id', 0) if getattr(event, 'message', None) else 0
        username = getattr(chat, 'username', None)
        
        if username:
            return f"https://t.me/{username}/{msg_id}"
        elif chat and getattr(chat, 'id', None):
            raw_id = str(chat.id).replace("-100", "").replace("-", "")
            return f"https://t.me/c/{raw_id}/{msg_id}"
    except Exception as e:
        logger.error(f"Error building post link: {e}")
    return None

def truncate_text(text, max_len=1020):
    """Safely truncates text to fit Telegram caption or message limits."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len-4] + "\n..."

def cleanup_media_paths(post_data):
    """Safely removes local temporary media files when post is discarded or published."""
    media_paths = post_data.get("media_paths") or post_data.get("media_path")
    if isinstance(media_paths, str):
        media_paths = [media_paths]
    elif not media_paths:
        media_paths = []
    for p in media_paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

async def send_post_preview(chat_id, media_paths, text, buttons):
    """Safely sends post preview to chat (supports single photo or multi-photo album)."""
    if isinstance(media_paths, str):
        media_paths = [media_paths] if media_paths else []
    elif not media_paths:
        media_paths = []

    valid_paths = [p for p in media_paths if p and os.path.exists(p)]

    if not valid_paths:
        safe_txt = truncate_text(text, 4000)
        return await bot.send_message(chat_id, safe_txt, buttons=buttons)

    safe_cap = truncate_text(text, 1020)
    if len(valid_paths) == 1:
        return await bot.send_file(chat_id, valid_paths[0], caption=safe_cap, buttons=buttons)
    else:
        # Multi-photo album preview!
        await bot.send_file(chat_id, valid_paths, caption=safe_cap)
        return await bot.send_message(chat_id, "👇 **Use the buttons below to control this post:**", buttons=buttons)

async def publish_to_channel(target_ch, media_paths, text):
    """Safely publishes single photo or multi-photo album to target channel."""
    if isinstance(media_paths, str):
        media_paths = [media_paths] if media_paths else []
    elif not media_paths:
        media_paths = []

    valid_paths = [p for p in media_paths if p and os.path.exists(p)]

    if not valid_paths:
        safe_txt = truncate_text(text, 4000)
        return await bot.send_message(target_ch, safe_txt)

    safe_cap = truncate_text(text, 1020)
    if len(valid_paths) == 1:
        return await bot.send_file(target_ch, valid_paths[0], caption=safe_cap)
    else:
        # Multi-photo album published to target channel!
        msgs = await bot.send_file(target_ch, valid_paths, caption=safe_cap)
        return msgs[0] if isinstance(msgs, list) else msgs

async def safe_edit_preview(event, media_paths, full_preview, buttons):
    """Safely edits preview message with media or text, respecting Telegram limits."""
    if isinstance(media_paths, str):
        media_paths = [media_paths] if media_paths else []
    elif not media_paths:
        media_paths = []

    valid_paths = [p for p in media_paths if p and os.path.exists(p)]

    try:
        if valid_paths and len(valid_paths) == 1:
            safe_text = truncate_text(full_preview, 1020)
            await bot.edit_message(event.chat_id, event.message_id, text=safe_text, buttons=buttons, file=valid_paths[0])
        else:
            safe_text = truncate_text(full_preview, 4000)
            await event.edit(safe_text, buttons=buttons)
    except Exception as e:
        logger.error(f"[EDIT ERROR] Failed to edit preview: {e}")
        try:
            safe_text = truncate_text(full_preview, 4000)
            await event.edit(safe_text, buttons=buttons)
        except Exception:
            pass

# ----------------------------------------------------
# Dynamic UI Text & Button Builders
# ----------------------------------------------------
def build_main_menu_text():
    channels = config.get_source_channels()
    markup = config.get_price_markup()
    phone = config.get_broker_phone()
    handle = config.get_broker_handle()
    target = config.get_target_channel()

    channels_str = ", ".join(channels) if channels else "None"
    markup_str = f"+{markup:,} Birr" if markup > 0 else (f"{markup:,} Birr" if markup < 0 else "0 Birr")

    return (
        "🤖 **TELEGRAM BROKER BOT - CONTROL DASHBOARD**\n"
        "------------------------------------------\n"
        f"📡 **Monitored Channels**: `{channels_str}`\n"
        f"📢 **Target Channel**: `{target}`\n"
        f"💰 **Price Markup**: `{markup_str}`\n"
        f"📞 **Phone**: `{phone}`\n"
        f"💬 **Handle**: `{handle}`\n"
        "------------------------------------------\n"
        "Tap any button below to edit settings or manage posts!"
    )

def build_main_menu_buttons():
    return [
        [
            Button.inline("📡 Monitored Channels", data="menu:channels"),
            Button.inline("📢 Target Channel", data="menu:target")
        ],
        [
            Button.inline("💰 Price Markup", data="menu:markup"),
            Button.inline("📞 Broker Contact", data="menu:contact")
        ],
        [
            Button.inline("🔄 Reload Listeners", data="menu:reload"),
            Button.inline("ℹ️ Help / Info", data="menu:help")
        ]
    ]

def build_post_action_buttons(post_id, current_markup, source_link=None):
    btns = [
        [
            Button.inline("🚀 Post to Channel", data=f"pub:{post_id}"),
            Button.inline("✏️ Custom Edit Text", data=f"edit_txt:{post_id}")
        ],
        [
            Button.inline("➕ +1000", data=f"mark:{post_id}:1000"),
            Button.inline("➕ +2000", data=f"mark:{post_id}:2000"),
            Button.inline("➕ +3000", data=f"mark:{post_id}:3000"),
            Button.inline("0 Original", data=f"mark:{post_id}:0")
        ],
        [
            Button.inline("🔄 Re-Run Gemini AI", data=f"rerun:{post_id}"),
            Button.inline("❌ Discard", data=f"disc:{post_id}")
        ]
    ]
    if source_link:
        btns.append([
            Button.url("🔗 Open Original Source Post", url=source_link)
        ])
    return btns

# ----------------------------------------------------
# Telegram Bot Handlers
# ----------------------------------------------------
@bot.on(events.NewMessage(pattern=r"(?i)^/(start|menu|settings|help)"))
async def start_handler(event):
    user_states.pop(event.sender_id, None)
    logger.info(f"[USER] 👤 User {event.sender_id} accessed bot control panel.")
    try:
        await event.respond(build_main_menu_text(), buttons=build_main_menu_buttons())
    except Exception as e:
        logger.error(f"[START ERROR] Failed to send main menu: {e}")
        await event.respond("🤖 **Telegram Broker Bot Menu**", buttons=build_main_menu_buttons())

@bot.on(events.NewMessage(pattern=r"^/channels$"))
async def list_channels_handler(event):
    channels = config.get_source_channels()
    ch_list = "\n".join([f"• `{c}`" for c in channels]) if channels else "No channels monitored."
    await event.respond(f"📡 **Monitored Channels:**\n\n{ch_list}\n\nAdd: `/addchannel @username`\nRemove: `/removechannel @username`")

@bot.on(events.NewMessage(pattern=r"^/addchannel\s+(.+)"))
async def add_channel_cmd(event):
    channel = event.pattern_match.group(1).strip()
    added = config.add_source_channel(channel)
    if added:
        logger.info(f"[CONFIG] ➕ Added source channel: {channel}")
        await event.respond(f"✅ Added `{channel}` to source channels!\nReloading listeners...")
        await restart_channel_listeners()
    else:
        await event.respond(f"⚠️ `{channel}` is already in your source channels.")

@bot.on(events.NewMessage(pattern=r"^/removechannel\s+(.+)"))
async def remove_channel_cmd(event):
    channel = event.pattern_match.group(1).strip()
    removed = config.remove_source_channel(channel)
    if removed:
        logger.info(f"[CONFIG] ➖ Removed source channel: {channel}")
        await event.respond(f"🗑️ Removed `{channel}` from source channels!\nReloading listeners...")
        await restart_channel_listeners()
    else:
        await event.respond(f"⚠️ Channel `{channel}` was not found in your list.")

@bot.on(events.NewMessage(pattern=r"^/(setmarkup|markup)(\s+[\+\-]?\d+)?$"))
async def markup_cmd(event):
    match = event.pattern_match.group(2)
    if match:
        try:
            val = int(match.strip().replace("+", ""))
            config.set_price_markup(val)
            logger.info(f"[CONFIG] 💰 Price markup updated to: {val:+} Birr")
            await event.respond(f"✅ Price markup updated to **{val:+} Birr**!")
            return
        except ValueError:
            pass
    
    current = config.get_price_markup()
    await event.respond(
        f"💰 **Current Price Markup**: `{current:+} Birr`\n\n"
        "To change, use: `/setmarkup 2000` (adds +2000 Birr)\n"
        "Or use `/setmarkup 0` for original price."
    )

channel_album_buffers = {}
user_album_buffers = {}

# ----------------------------------------------------
# Private Message & Interactive Prompt State Handler
# ----------------------------------------------------
@bot.on(events.NewMessage(func=lambda e: e.is_private and not e.text.startswith("/")))
async def private_message_handler(event):
    sender_id = event.sender_id
    text = (event.text or event.message.message or "").strip()

    # Check if user is in an active interactive prompt state
    if sender_id in user_states:
        state = user_states.pop(sender_id)
        action = state.get("action")

        if action == "add_channel":
            added = config.add_source_channel(text)
            if added:
                logger.info(f"[CONFIG] ➕ Added channel: {text}")
                await event.respond(f"✅ **Added channel `{text}`!**\nReloading active listeners...")
                await restart_channel_listeners()
            else:
                await event.respond(f"⚠️ Channel `{text}` is already monitored.")
            await event.respond(build_main_menu_text(), buttons=build_main_menu_buttons())
            return

        elif action == "edit_phone":
            config.set_broker_phone(text)
            logger.info(f"[CONFIG] 📱 Updated phone to: {text}")
            await event.respond(f"✅ **Updated broker phone number to `{text}`!**")
            await event.respond(build_main_menu_text(), buttons=build_main_menu_buttons())
            return

        elif action == "edit_handle":
            config.set_broker_handle(text)
            logger.info(f"[CONFIG] 👤 Updated handle to: {text}")
            await event.respond(f"✅ **Updated broker Telegram handle to `{text}`!**")
            await event.respond(build_main_menu_text(), buttons=build_main_menu_buttons())
            return

        elif action == "edit_target":
            config.set_target_channel(text)
            logger.info(f"[CONFIG] 📢 Updated target channel to: {text}")
            await event.respond(f"✅ **Updated target channel to `{text}`!**")
            await event.respond(build_main_menu_text(), buttons=build_main_menu_buttons())
            return

        elif action == "edit_markup":
            try:
                val = int(text.replace("+", "").replace(",", ""))
                config.set_price_markup(val)
                logger.info(f"[CONFIG] 💰 Updated markup to: {val:+} Birr")
                await event.respond(f"✅ **Price markup set to `{val:+} Birr`!**")
            except ValueError:
                await event.respond("❌ Invalid number. Markup was not changed.")
            await event.respond(build_main_menu_text(), buttons=build_main_menu_buttons())
            return

        elif action == "edit_post_text":
            post_id = state.get("post_id")
            if post_id in pending_posts:
                post_data = pending_posts[post_id]
                post_data["text"] = text
                source_link = post_data.get("source_link")
                markup = post_data.get("markup", 0)

                logger.info(f"[PREVIEW] ✏️ User manually edited text for post {post_id}")
                await event.respond("✅ **Post text updated!** Here is the updated preview:")

                link_info = f"🔗 **Original Link**: {source_link}\n" if source_link else ""
                preview_header = f"📝 **MODIFIED POST PREVIEW (Custom Text):**\n{link_info}" + "------------------------------------------\n\n"
                full_preview = preview_header + text
                buttons = build_post_action_buttons(post_id, markup, source_link=source_link)

                media_paths = post_data.get("media_paths") or post_data.get("media_path")
                await send_post_preview(event.chat_id, media_paths, full_preview, buttons)
            else:
                await event.respond("⚠️ Post session expired.")
            return

    # Normal post processing for manual forwards or raw post text (album grouping support)
    grouped_id = event.grouped_id
    if grouped_id:
        if grouped_id in user_album_buffers:
            user_album_buffers[grouped_id]["events"].append(event)
            return
        else:
            user_album_buffers[grouped_id] = {"events": [event]}
            await asyncio.sleep(1.2)
            buf_data = user_album_buffers.pop(grouped_id, None)
            if not buf_data:
                return
            events = buf_data["events"]
    else:
        events = [event]

    raw_text = ""
    for e in events:
        t = (e.text or getattr(e.message, 'message', '') or "").strip()
        if t:
            raw_text = t
            break

    if not raw_text and not any(has_downloadable_media(e) for e in events):
        await event.respond("⚠️ Please send a message with text or media caption.")
        return

    first_event = events[0]
    logger.info(f"[MANUAL] 📩 Received manual post forward/album from User {first_event.sender_id} ({len(events)} items)")
    status_msg = await first_event.respond("⚡ Processing post with Google Gemini AI...")

    media_paths = []
    for idx, e in enumerate(events):
        if has_downloadable_media(e):
            try:
                logger.info(f"[MEDIA] 🖼️ Downloading album photo {idx+1}/{len(events)}...")
                p = await e.download_media(file=TEMP_MEDIA_DIR)
                if p:
                    media_paths.append(p)
                    logger.info(f"[MEDIA] ✅ Downloaded photo: {p}")
            except Exception as ex:
                logger.error(f"[MEDIA ERROR] ❌ Failed to download album photo: {ex}")

    markup = config.get_price_markup()
    logger.info(f"[GEMINI] 🧠 Processing post with Gemini AI (Price Markup: {markup:+} Birr)...")
    modified_text = process_post_with_gemini(raw_text, custom_markup=markup)
    logger.info("[GEMINI] ✅ Formatting complete!")

    global post_counter
    post_counter += 1
    post_id = f"post_{post_counter}"
    source_link = get_post_link(first_event)
    
    pending_posts[post_id] = {
        "raw_text": raw_text,
        "text": modified_text,
        "media_paths": media_paths,
        "markup": markup,
        "source_link": source_link
    }

    buttons = build_post_action_buttons(post_id, markup, source_link=source_link)

    try:
        await status_msg.delete()
    except Exception:
        pass
    
    link_info = f"🔗 **Original Link**: {source_link}\n" if source_link else ""
    preview_header = f"📝 **MODIFIED POST PREVIEW (by Gemini AI):**\n{link_info}" + "------------------------------------------\n\n"
    full_preview = preview_header + modified_text

    await send_post_preview(first_event.chat_id, media_paths, full_preview, buttons)
    logger.info(f"[PREVIEW] 📲 Sent preview (ID: {post_id}) with {len(media_paths)} photos to user.")

# ----------------------------------------------------
# Callback Query Handler (Interactive Button Logic)
# ----------------------------------------------------
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")
    sender_id = event.sender_id

    # 1. Main Menu Navigation Callbacks
    if data.startswith("menu:"):
        section = data.split(":", 1)[1]
        
        if section == "channels":
            channels = config.get_source_channels()
            text = "📡 **MONITORED SOURCE CHANNELS**\n" + "─"*35 + "\n"
            if channels:
                for c in channels:
                    text += f"• `{c}`\n"
            else:
                text += "No channels configured.\n"

            btns = [
                [Button.inline("➕ Add New Source Channel", data="prompt:add_channel")]
            ]
            # Dynamic Delete Buttons per channel
            if channels:
                for c in channels:
                    btns.append([Button.inline(f"❌ Remove {c}", data=f"rm_ch:{c}")])
            
            btns.append([Button.inline("🔙 Back to Main Menu", data="menu:main")])
            await event.edit(text, buttons=btns)
            return

        elif section == "target":
            target = config.get_target_channel()
            text = (
                "📢 **TARGET CHANNEL CONFIGURATION**\n"
                + "─"*35 + "\n"
                f"Current Target Channel: `{target}`\n\n"
                "Approved posts will be published to this channel."
            )
            btns = [
                [Button.inline("📢 Change Target Channel", data="prompt:edit_target")],
                [Button.inline("🔙 Back to Main Menu", data="menu:main")]
            ]
            await event.edit(text, buttons=btns)
            return

        elif section == "markup":
            current = config.get_price_markup()
            markup_str = f"+{current:,} Birr" if current > 0 else (f"{current:,} Birr" if current < 0 else "0 Birr")
            text = (
                f"💰 **PRICE MARKUP CONFIGURATION**\n"
                + "─"*35 + "\n"
                f"Current Price Markup: **{markup_str}**\n\n"
                "Tap a preset below to change global markup or set a custom amount:"
            )
            btns = [
                [
                    Button.inline("0 Birr (Original)", data="setm:0"),
                    Button.inline("+500 Birr", data="setm:500"),
                    Button.inline("+1,000 Birr", data="setm:1000")
                ],
                [
                    Button.inline("+1,500 Birr", data="setm:1500"),
                    Button.inline("+2,000 Birr", data="setm:2000"),
                    Button.inline("+2,500 Birr", data="setm:2500")
                ],
                [
                    Button.inline("+3,000 Birr", data="setm:3000"),
                    Button.inline("+5,000 Birr", data="setm:5000"),
                    Button.inline("-1,000 Birr", data="setm:-1000")
                ],
                [
                    Button.inline("✏️ Set Custom Amount", data="prompt:edit_markup"),
                    Button.inline("🔙 Back to Main Menu", data="menu:main")
                ]
            ]
            await event.edit(text, buttons=btns)
            return

        elif section == "contact":
            phone = config.get_broker_phone()
            handle = config.get_broker_handle()
            text = (
                f"📞 **BROKER CONTACT DETAILS**\n"
                + "─"*35 + "\n"
                f"• Phone Number: `{phone}`\n"
                f"• Telegram Handle: `{handle}`\n"
            )
            btns = [
                [
                    Button.inline("📱 Edit Phone Number", data="prompt:edit_phone"),
                    Button.inline("👤 Edit Telegram Handle", data="prompt:edit_handle")
                ],
                [Button.inline("🔙 Back to Main Menu", data="menu:main")]
            ]
            await event.edit(text, buttons=btns)
            return

        elif section == "reload":
            await event.answer("🔄 Reloading channel listeners...", alert=True)
            await restart_channel_listeners()
            await event.edit("✅ Channel listeners reloaded!", buttons=[[Button.inline("🔙 Back to Menu", data="menu:main")]])
            return

        elif section == "help":
            help_text = (
                "ℹ️ **BOT HELP & COMMANDS**\n"
                + "─"*35 + "\n"
                "• `/menu` or `/start`: Open main control panel\n"
                "• `/channels`: View monitored source channels\n"
                "• `/addchannel @username`: Add a source channel\n"
                "• `/removechannel @username`: Remove a source channel\n"
                "• `/setmarkup 2000`: Set global price markup (+2000 Birr)\n\n"
                "💡 Simply forward any laptop listing to this chat to test Gemini formatting!"
            )
            await event.edit(help_text, buttons=[[Button.inline("🔙 Back to Main Menu", data="menu:main")]])
            return

        elif section == "main":
            await event.edit(build_main_menu_text(), buttons=build_main_menu_buttons())
            return

    # 2. Dynamic Interactive Prompts (Add channel, edit phone, etc.)
    elif data.startswith("prompt:"):
        action = data.split(":", 1)[1]
        user_states[sender_id] = {"action": action}

        prompts = {
            "add_channel": "📥 **Send the username or ID of the channel to add** (e.g. `@channelname`):",
            "edit_phone": "📞 **Send your new broker phone number** (e.g. `+251 91 100 0000`):",
            "edit_handle": "👤 **Send your new Telegram handle** (e.g. `@my_new_handle`):",
            "edit_target": "📢 **Send your new target channel username** (e.g. `@my_target_channel`):",
            "edit_markup": "💰 **Send the custom markup amount in Birr** (e.g. `2500` or `-1000`):"
        }
        prompt_msg = prompts.get(action, "Please send your input:")
        await event.respond(prompt_msg)
        await event.answer("Waiting for input...")
        return

    # 3. Dynamic Remove Channel Callback
    elif data.startswith("rm_ch:"):
        ch = data.split(":", 1)[1]
        config.remove_source_channel(ch)
        logger.info(f"[CONFIG] ➖ Removed channel {ch} via button")
        await event.answer(f"Removed {ch}!")
        await restart_channel_listeners()
        
        # Refresh channels menu
        channels = config.get_source_channels()
        text = "📡 **MONITORED SOURCE CHANNELS**\n" + "─"*35 + "\n"
        if channels:
            for c in channels:
                text += f"• `{c}`\n"
        else:
            text += "No channels configured.\n"

        btns = [[Button.inline("➕ Add New Source Channel", data="prompt:add_channel")]]
        if channels:
            for c in channels:
                btns.append([Button.inline(f"❌ Remove {c}", data=f"rm_ch:{c}")])
        btns.append([Button.inline("🔙 Back to Main Menu", data="menu:main")])
        await event.edit(text, buttons=btns)
        return

    # 4. Set Markup Preset Callback
    elif data.startswith("setm:"):
        val = int(data.split(":", 1)[1])
        config.set_price_markup(val)
        logger.info(f"[CONFIG] 💰 Set global price markup to {val:+} Birr via menu preset")
        await event.answer(f"Price markup set to {val:+} Birr!")
        await event.edit(build_main_menu_text(), buttons=build_main_menu_buttons())
        return

    # 5. Post Action Callbacks (Publish, Discard, Edit, Change Markup, Rerun)
    parts = data.split(":")
    action = parts[0]
    post_id = parts[1]

    if post_id not in pending_posts:
        await event.answer("⚠️ This post preview has expired or already been published.", alert=True)
        return

    post_data = pending_posts[post_id]
    media_path = post_data.get("media_paths") or post_data.get("media_path")

    if action == "pub":
        target_ch = config.get_target_channel()
        if not target_ch:
            await event.answer("❌ Target Channel is not configured!", alert=True)
            return

        logger.info(f"[PUBLISH] 🚀 Publishing post {post_id} to target channel {target_ch}...")
        try:
            pub_msg = await publish_to_channel(target_ch, media_path, post_data["text"])
            logger.info(f"[PUBLISH] ✅ Successfully published post {post_id} to {target_ch}!")

            # Extract published message link
            published_link = None
            try:
                msg_id = getattr(pub_msg, 'id', None)
                if isinstance(pub_msg, list) and len(pub_msg) > 0:
                    msg_id = getattr(pub_msg[0], 'id', None)
                if msg_id:
                    target_clean = str(target_ch).strip()
                    if target_clean.startswith("@"):
                        published_link = f"https://t.me/{target_clean[1:]}/{msg_id}"
                    elif target_clean.startswith("https://t.me/"):
                        published_link = f"{target_clean}/{msg_id}"
                    else:
                        raw_id = target_clean.replace("-100", "").replace("-", "")
                        published_link = f"https://t.me/c/{raw_id}/{msg_id}"
            except Exception as e:
                logger.error(f"[LINK ERROR] Failed to construct published post link: {e}")

            source_link = post_data.get("source_link")
            post_text = post_data["text"]

            published_header = f"✅ **PUBLISHED TO TARGET CHANNEL (`{target_ch}`)**\n"
            if published_link:
                published_header += f"📍 **Published Post**: {published_link}\n"
            if source_link:
                published_header += f"🔗 **Original Source**: {source_link}\n"
            published_header += "------------------------------------------\n\n"

            full_published_preview = published_header + post_text

            pub_btns = []
            if published_link:
                pub_btns.append([Button.url(f"📢 View Published Post in {target_ch}", url=published_link)])
            if source_link:
                pub_btns.append([Button.url("🔗 Open Original Source Post", url=source_link)])

            await safe_edit_preview(event, media_path, full_published_preview, pub_btns)
            await event.answer("✅ Published successfully!")
            
            cleanup_media_paths(post_data)
            pending_posts.pop(post_id, None)

        except Exception as e:
            logger.error(f"[PUBLISH ERROR] ❌ Failed to publish post: {e}")
            await event.edit(f"❌ **Failed to publish:** {e}")

    elif action == "disc":
        logger.info(f"[DISCARD] 🗑️ User discarded post preview {post_id}")
        await event.edit("🗑️ **Post preview discarded.**")
        await event.answer("Discarded.")
        
        cleanup_media_paths(post_data)
        pending_posts.pop(post_id, None)

    elif action == "edit_txt":
        user_states[sender_id] = {"action": "edit_post_text", "post_id": post_id}
        await event.respond("✏️ **Please send the updated text for this post:**")
        await event.answer("Waiting for text...")
        return

    elif action == "rerun":
        await event.answer("🔄 Re-running Gemini AI processing...")
        raw_text = post_data["raw_text"]
        markup = post_data.get("markup", config.get_price_markup())
        
        new_text = process_post_with_gemini(raw_text, custom_markup=markup)
        post_data["text"] = new_text

        source_link = post_data.get("source_link")
        link_info = f"🔗 **Original Link**: {source_link}\n" if source_link else ""
        preview_header = f"📝 **MODIFIED POST PREVIEW (Re-run Gemini):**\n{link_info}" + "─"*30 + "\n\n"
        full_preview = preview_header + new_text
        buttons = build_post_action_buttons(post_id, markup, source_link=source_link)

        await safe_edit_preview(event, media_path, full_preview, buttons)

    elif action == "mark":
        new_markup = int(parts[2])
        logger.info(f"[PREVIEW] 🔄 Updating post {post_id} preview with price markup: {new_markup:+} Birr")
        await event.answer(f"Updating price with {new_markup:+} Birr...")

        raw_text = post_data["raw_text"]
        new_text = process_post_with_gemini(raw_text, custom_markup=new_markup)
        post_data["text"] = new_text
        post_data["markup"] = new_markup

        source_link = post_data.get("source_link")
        link_info = f"🔗 **Original Link**: {source_link}\n" if source_link else ""
        preview_header = f"📝 **MODIFIED POST PREVIEW (Markup: {new_markup:+} Birr):**\n{link_info}" + "─"*30 + "\n\n"
        full_preview = preview_header + new_text
        buttons = build_post_action_buttons(post_id, new_markup, source_link=source_link)

        await safe_edit_preview(event, media_path, full_preview, buttons)

# ----------------------------------------------------
# Channel Listener Logic
# ----------------------------------------------------
async def handle_source_channel_post(event):
    grouped_id = getattr(event, 'grouped_id', None)

    if grouped_id:
        if grouped_id not in channel_album_buffers:
            channel_album_buffers[grouped_id] = []
            channel_album_buffers[grouped_id].append(event)
            await asyncio.sleep(1.2)
            events = channel_album_buffers.pop(grouped_id, [])
        else:
            channel_album_buffers[grouped_id].append(event)
            return
    else:
        events = [event]

    if not events:
        return

    # Extract text from whichever event carries caption text in the album
    raw_text = ""
    for e in events:
        t = (e.text or e.message.message or "").strip()
        if t:
            raw_text = t
            break

    first_event = events[0]
    chat_username = getattr(first_event.chat, 'username', None)
    chat_name = f"@{chat_username}" if chat_username else (getattr(first_event.chat, 'title', None) or str(first_event.chat_id))
    logger.info(f"[LISTEN] 📡 New post detected from source channel: {chat_name} (ID: {first_event.chat_id}) ({len(events)} items)")

    media_paths = []
    for idx, e in enumerate(events):
        if has_downloadable_media(e):
            try:
                logger.info(f"[MEDIA] 🖼️ Downloading channel post media photo/document {idx+1}/{len(events)}...")
                p = await e.download_media(file=TEMP_MEDIA_DIR)
                if p:
                    media_paths.append(p)
                    logger.info(f"[MEDIA] ✅ Downloaded photo: {p}")
            except Exception as ex:
                logger.error(f"[MEDIA ERROR] ❌ Failed to download media: {ex}")

    markup = config.get_price_markup()
    logger.info(f"[GEMINI] 🧠 Rewriting channel post with Gemini AI (Price Markup: {markup:+} Birr)...")
    modified_text = process_post_with_gemini(raw_text, custom_markup=markup)
    logger.info("[GEMINI] ✅ Text processing complete!")

    global post_counter
    post_counter += 1
    post_id = f"auto_{post_counter}"
    source_link = get_post_link(first_event)
    
    pending_posts[post_id] = {
        "raw_text": raw_text,
        "text": modified_text,
        "media_paths": media_paths,
        "markup": markup,
        "source_link": source_link
    }

    buttons = build_post_action_buttons(post_id, markup, source_link=source_link)

    link_info = f"🔗 **Original Post Link**: {source_link}\n" if source_link else ""
    preview_text = (
        f"🔔 **NEW CHANNEL POST DETECTED!**\n"
        f"📍 **Source Channel**: `{chat_name}`\n"
        f"{link_info}"
        + "─"*35 + "\n\n"
        + modified_text
    )

    if config.MY_TELEGRAM_USER_ID:
        try:
            await send_post_preview(config.MY_TELEGRAM_USER_ID, media_paths, preview_text, buttons)
            logger.info(f"[PREVIEW] 📲 Delivered post preview (ID: {post_id}) with {len(media_paths)} photos to User {config.MY_TELEGRAM_USER_ID}")
        except Exception as e:
            logger.error(f"[PREVIEW ERROR] ❌ Failed to send preview: {e}")

# Dynamic Channel Listener Registration
channel_handler_ref = None

async def restart_channel_listeners():
    global channel_handler_ref
    if not user_client:
        return

    channels = config.get_source_channels()
    logger.info(f"[LISTEN] 🔄 Reloading channel listener for channels: {channels}")

    if channel_handler_ref:
        try:
            user_client.remove_event_handler(channel_handler_ref)
        except Exception:
            pass

    if channels:
        @user_client.on(events.NewMessage(chats=channels))
        async def channel_listener(event):
            await handle_source_channel_post(event)
        
        channel_handler_ref = channel_listener
        logger.info(f"[LISTEN] ✅ Listener active on {len(channels)} channel(s): {channels}")

# ----------------------------------------------------
# Cloud / Render Health Check Web Server
# ----------------------------------------------------
async def handle_http_health_check(reader, writer):
    try:
        await reader.read(1024)
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n\r\n"
            b"OK"
        )
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def start_dummy_web_server():
    """Binds to PORT environment variable so Render Web Service marks deployment as Healthy/Live."""
    port_str = os.environ.get("PORT")
    if not port_str:
        return None
    try:
        port = int(port_str)
        server = await asyncio.start_server(handle_http_health_check, "0.0.0.0", port)
        logger.info(f"[HTTP] 🌐 Health check web server running on 0.0.0.0:{port}")
        return server
    except Exception as e:
        logger.warning(f"[HTTP] Failed to start health check server: {e}")
        return None

# ----------------------------------------------------
# Main Startup
# ----------------------------------------------------
async def main():
    logger.info("="*50)
    logger.info("🚀 STARTING TELEGRAM BROKER AUTOMATION BOT")
    logger.info("="*50)
    
    # Start health check server if running on Render / Cloud Web Service
    await start_dummy_web_server()

    await bot.start(bot_token=config.BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"[BOT CLIENT] ✅ Bot @{me.username} is connected and ready.")

    if user_client:
        await user_client.start()
        logger.info("[USER CLIENT] ✅ Connected user account for channel socket listening.")
        await restart_channel_listeners()

    logger.info("[STATUS] 🟢 Bot is fully online and ready! Press Ctrl+C to stop.")
    logger.info("="*50)
    
    tasks = [bot.run_until_disconnected()]
    if user_client:
        tasks.append(user_client.run_until_disconnected())

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
