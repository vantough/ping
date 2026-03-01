#!/usr/bin/env python3
"""
Ping Bot - Monitors other Telegram bots and reports their status.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config helpers ────────────────────────────────────────────────────────────
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config.json"))


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return json.load(f)
    return {
        "bots": {},
        "channel_id": None,
        "status_message_id": None,
    }


def save_config(cfg: dict) -> None:
    with CONFIG_PATH.open("w") as f:
        json.dump(cfg, f, indent=2)


# ── Status helpers ────────────────────────────────────────────────────────────

def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def build_status_text(cfg: dict) -> str:
    now = time.time()
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🤖 <b>Bot Status Dashboard</b>",
        f"<i>Updated: {updated} UTC</i>\n",
    ]

    if not cfg["bots"]:
        lines.append("No bots configured yet. Use /add to add one.")
    else:
        for username, info in cfg["bots"].items():
            status = info.get("status", "UNKNOWN")
            emoji = "🟢" if status == "ACTIVE" else ("🔴" if status == "INACTIVE" else "⚪")
            uptime_start = info.get("uptime_start")
            downtime_start = info.get("downtime_start")
            interval = info.get("interval", 30)

            if status == "ACTIVE" and uptime_start:
                duration = fmt_duration(now - uptime_start)
                state_line = f"  ⏱ Uptime: <code>{duration}</code>"
            elif status == "INACTIVE" and downtime_start:
                duration = fmt_duration(now - downtime_start)
                state_line = f"  ⏱ Down for: <code>{duration}</code>"
            else:
                state_line = "  ⏱ Status: <code>checking…</code>"

            lines.append(
                f"{emoji} <b>@{username}</b>\n"
                f"  Status: <code>{status}</code>\n"
                f"{state_line}\n"
                f"  Ping every: <code>{interval}s</code>"
            )

    return "\n".join(lines)


# ── Ping logic ────────────────────────────────────────────────────────────────

async def ping_bot(token: str) -> bool:
    try:
        async with Bot(token) as b:
            await asyncio.wait_for(b.get_me(), timeout=8)
        return True
    except Exception:
        return False


async def ping_loop(app: Application) -> None:
    while True:
        cfg = load_config()
        now = time.time()
        changed = False

        for username, info in cfg["bots"].items():
            interval = info.get("interval", 30)
            last_check = info.get("last_check", 0)
            if now - last_check < interval:
                continue

            token = info.get("token")
            if not token:
                continue

            is_up = await ping_bot(token)
            prev_status = info.get("status", "UNKNOWN")
            new_status = "ACTIVE" if is_up else "INACTIVE"

            info["last_check"] = now
            info["status"] = new_status

            if new_status != prev_status:
                if new_status == "ACTIVE":
                    info["uptime_start"] = now
                    info.pop("downtime_start", None)
                else:
                    info["downtime_start"] = now
                    info.pop("uptime_start", None)

            if new_status == "ACTIVE" and not info.get("uptime_start"):
                info["uptime_start"] = now
            if new_status == "INACTIVE" and not info.get("downtime_start"):
                info["downtime_start"] = now

            changed = True

        if changed:
            save_config(cfg)

        # Update pinned channel message
        channel_id = cfg.get("channel_id")
        msg_id = cfg.get("status_message_id")
        if channel_id and cfg["bots"]:
            text = build_status_text(cfg)
            try:
                if msg_id:
                    await app.bot.edit_message_text(
                        chat_id=channel_id,
                        message_id=msg_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    msg = await app.bot.send_message(
                        chat_id=channel_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                    )
                    cfg["status_message_id"] = msg.message_id
                    save_config(cfg)
                    try:
                        await app.bot.pin_chat_message(chat_id=channel_id, message_id=msg.message_id)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Could not update status message: {e}")

        await asyncio.sleep(5)


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 <b>Ping Bot</b>\n\n"
        "I monitor your Telegram bots and report their status.\n\n"
        "<b>Commands:</b>\n"
        "/add <code>&lt;username&gt; &lt;token&gt; [interval_seconds]</code> — add a bot\n"
        "/remove <code>&lt;username&gt;</code> — remove a bot\n"
        "/list — list all monitored bots\n"
        "/status — show current status\n"
        "/setchannel <code>&lt;channel_id&gt;</code> — set status dashboard channel\n"
        "/help — show this message",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /add <code>&lt;username&gt; &lt;token&gt; [interval_seconds]</code>\n"
            "Example: <code>/add mybot 123456:ABC-DEF 30</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    username = args[0].lstrip("@")
    token = args[1]
    try:
        interval = int(args[2]) if len(args) > 2 else 30
        interval = max(10, interval)
    except ValueError:
        await update.message.reply_text("Interval must be a number (seconds, minimum 10).")
        return

    msg = await update.message.reply_text("🔍 Validating token…")
    is_valid = await ping_bot(token)
    if not is_valid:
        await msg.edit_text("❌ Could not reach that bot with the provided token. Please check and try again.")
        return

    cfg = load_config()
    cfg["bots"][username] = {
        "token": token,
        "interval": interval,
        "status": "UNKNOWN",
        "last_check": 0,
    }
    save_config(cfg)
    await msg.edit_text(
        f"✅ <b>@{username}</b> added! Pinging every <code>{interval}s</code>.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /remove <code>&lt;username&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    username = ctx.args[0].lstrip("@")
    cfg = load_config()
    if username not in cfg["bots"]:
        await update.message.reply_text(f"❌ @{username} is not in the monitored list.")
        return

    del cfg["bots"][username]
    save_config(cfg)
    await update.message.reply_text(f"✅ @{username} removed from monitoring.")


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = load_config()
    if not cfg["bots"]:
        await update.message.reply_text("No bots configured. Use /add to add one.")
        return

    lines = ["<b>Monitored bots:</b>\n"]
    for username, info in cfg["bots"].items():
        status = info.get("status", "UNKNOWN")
        emoji = "🟢" if status == "ACTIVE" else ("🔴" if status == "INACTIVE" else "⚪")
        lines.append(f"{emoji} @{username} — every {info.get('interval', 30)}s — <code>{status}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = load_config()
    text = build_status_text(cfg)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_setchannel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /setchannel <code>&lt;channel_id&gt;</code>\n"
            "Example: <code>/setchannel -1001234567890</code>\n\n"
            "Make sure this bot is an admin in that channel.",
            parse_mode=ParseMode.HTML,
        )
        return

    channel_id_str = ctx.args[0]
    try:
        channel_id = int(channel_id_str)
    except ValueError:
        channel_id = channel_id_str

    try:
        test_msg = await ctx.bot.send_message(chat_id=channel_id, text="🔧 Setting up status dashboard…")
        await test_msg.delete()
    except Exception as e:
        await update.message.reply_text(
            f"❌ Could not post to that channel: {e}\n\nMake sure I'm an admin there."
        )
        return

    cfg = load_config()
    cfg["channel_id"] = channel_id
    cfg["status_message_id"] = None
    save_config(cfg)
    await update.message.reply_text(
        f"✅ Status dashboard will be posted to <code>{channel_id}</code>.",
        parse_mode=ParseMode.HTML,
    )


async def unknown_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Unknown command. Use /help to see available commands.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("setchannel", cmd_setchannel))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))

    async def _start_ping(app: Application) -> None:
        asyncio.create_task(ping_loop(app))

    app.post_init = _start_ping

    logger.info("Starting Ping Bot…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
