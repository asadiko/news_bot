"""
bot.py — Main entry point.

Startup: scheduler waits full interval, NO fetch on start.

First cycle ever (initialized=False in DB):
  - Mark all current articles as seen silently (flood prevention)
  - Set initialized=True in DB — never happens again even after restarts

All subsequent cycles:
  - Fetch → find unseen → post → mark sent ONLY after confirmed send

/runnow always posts (bypasses first-cycle check).
"""

import asyncio
import logging
import html
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

import db
from fetcher import fetch_all_feeds
from tg_scraper import fetch_all_tg_channels
from config import (
    TOKEN, CHANNEL_ID, ADMIN_IDS,
    CHECK_INTERVAL_MINUTES, MAX_MESSAGES_PER_CYCLE,
    MESSAGE_DELAY_SECONDS, MAX_DB_AGE_DAYS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

HELP_TEXT = (
    "🤖 <b>NewsBot — Embassy Baltic Monitor</b>\n"
    "Monitors RSS feeds and Telegram channels for keywords,\n"
    f"posts matches to {CHANNEL_ID} every {CHECK_INTERVAL_MINUTES} minutes.\n\n"
    "<b>📌 Keywords</b>\n"
    "  /keywords — list all active keywords\n"
    "  /addkeyword &lt;word&gt; — add keyword (any language)\n"
    "  /removekeyword &lt;word&gt; — remove keyword\n\n"
    "<b>📡 RSS Feeds</b>\n"
    "  /feeds — list all RSS feeds\n"
    "  /addfeed &lt;url&gt; — add RSS URL\n"
    "  /removefeed &lt;url&gt; — remove feed\n"
    "  /checkfeeds — test all feeds, show which are alive\n\n"
    "<b>📲 Telegram Channels</b>\n"
    "  /channels — list monitored TG channels\n"
    "  /addchannel &lt;@username&gt; — monitor a public channel\n"
    "  /removechannel &lt;@username&gt; — stop monitoring\n\n"
    "<b>ℹ️ Info</b>\n"
    "  /stats — show bot statistics\n"
    "  /runnow — trigger a news check immediately\n"
    "  /help — show this message\n\n"
    "⚠️ <b>Bot must be admin of the channel to post!</b>"
)


# ─── Admin Guard ─────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS

async def guard(message: Message) -> bool:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ You are not authorized.")
        return False
    return True


# ─── Core fetch ──────────────────────────────────────────────────────────────

async def _fetch_matching() -> list:
    """Fetch all sources and return keyword-matching articles."""
    keywords = db.get_keywords()
    feeds = db.get_feeds()
    tg_channels = db.get_tg_channels()

    if not keywords:
        return []

    async def _empty(): return []

    rss_task = fetch_all_feeds(feeds, keywords) if feeds else _empty()
    tg_task = fetch_all_tg_channels(tg_channels, keywords) if tg_channels else _empty()

    rss_articles, tg_posts = await asyncio.gather(rss_task, tg_task)
    return rss_articles + tg_posts


async def _post_articles(new_articles: list) -> int:
    """Post articles to channel. Returns count successfully sent."""
    sent = 0
    for article in new_articles:
        if sent >= MAX_MESSAGES_PER_CYCLE:
            logger.info(f"Rate limit ({MAX_MESSAGES_PER_CYCLE}/cycle) — rest next cycle.")
            break
        try:
            title = html.escape(article["title"])
            link = article["link"]
            source = html.escape(article.get("source", ""))
            text = f"📰 <b>{title}</b>\n\n🔗 {link}"
            if source:
                text += f"\n\n<i>— {source}</i>"
            await bot.send_message(CHANNEL_ID, text, parse_mode="HTML", disable_web_page_preview=False)
            db.mark_sent(article["link"])  # only mark AFTER confirmed send
            sent += 1
            await asyncio.sleep(MESSAGE_DELAY_SECONDS)
        except Exception as e:
            logger.error(f"Send failed (will retry next cycle): {e}")
    return sent


# ─── Scheduled cycle ─────────────────────────────────────────────────────────

async def run_news_cycle():
    """Called by scheduler every CHECK_INTERVAL_MINUTES."""
    if not db.get_keywords():
        logger.warning("No keywords — skipping.")
        return

    all_articles = await _fetch_matching()
    if not all_articles:
        logger.info("No matching articles.")
        return

    new_articles = [a for a in all_articles if not db.is_sent(a["link"])]
    if not new_articles:
        logger.info("No new articles (all seen).")
        return

    # Very first cycle ever: silently mark to avoid channel flood
    if not db.is_initialized():
        db.bulk_mark_sent([a["link"] for a in new_articles])
        db.set_initialized()
        logger.info(
            f"First cycle: silently marked {len(new_articles)} existing articles. "
            f"Next cycle in {CHECK_INTERVAL_MINUTES} min will post new ones."
        )
        return

    sent = await _post_articles(new_articles)
    logger.info(f"Cycle done: {sent} posted, {len(new_articles) - sent} pending.")
    db.purge_old_links(MAX_DB_AGE_DAYS)


# ─── Commands ────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not await guard(message): return
    await message.answer(HELP_TEXT, parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not await guard(message): return
    await message.answer(HELP_TEXT, parse_mode="HTML")

@dp.message(Command("keywords"))
async def cmd_keywords(message: Message):
    if not await guard(message): return
    kws = db.get_keywords()
    if not kws:
        await message.answer("No keywords. Use /addkeyword to add one.")
        return
    lines = "\n".join(f"  {i+1}. {html.escape(k)}" for i, k in enumerate(kws))
    await message.answer(f"🔍 <b>Keywords ({len(kws)}):</b>\n{lines}", parse_mode="HTML")

@dp.message(Command("addkeyword"))
async def cmd_addkeyword(message: Message):
    if not await guard(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /addkeyword &lt;keyword&gt;", parse_mode="HTML")
        return
    kw = parts[1].strip()
    if db.add_keyword(kw):
        await message.answer(f"✅ Added: <code>{html.escape(kw)}</code>", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Already exists: <code>{html.escape(kw)}</code>", parse_mode="HTML")

@dp.message(Command("removekeyword"))
async def cmd_removekeyword(message: Message):
    if not await guard(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /removekeyword &lt;keyword&gt;", parse_mode="HTML")
        return
    kw = parts[1].strip()
    if db.remove_keyword(kw):
        await message.answer(f"✅ Removed: <code>{html.escape(kw)}</code>", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Not found: <code>{html.escape(kw)}</code>", parse_mode="HTML")

@dp.message(Command("feeds"))
async def cmd_feeds(message: Message):
    if not await guard(message): return
    feeds = db.get_feeds()
    if not feeds:
        await message.answer("No feeds. Use /addfeed to add one.")
        return
    lines = "\n".join(f"  {i+1}. <code>{html.escape(f)}</code>" for i, f in enumerate(feeds))
    await _send_long(message, f"📡 <b>RSS Feeds ({len(feeds)}):</b>\n{lines}")

@dp.message(Command("addfeed"))
async def cmd_addfeed(message: Message):
    if not await guard(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().startswith("http"):
        await message.answer("Usage: /addfeed &lt;https://...&gt;", parse_mode="HTML")
        return
    url = parts[1].strip()
    if db.add_feed(url):
        await message.answer(f"✅ Feed added:\n<code>{html.escape(url)}</code>", parse_mode="HTML")
    else:
        await message.answer("⚠️ Already in the list.")

@dp.message(Command("removefeed"))
async def cmd_removefeed(message: Message):
    if not await guard(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /removefeed &lt;url&gt;", parse_mode="HTML")
        return
    if db.remove_feed(parts[1].strip()):
        await message.answer("✅ Feed removed.")
    else:
        await message.answer("⚠️ Not found. Use /feeds to see the list.")

@dp.message(Command("checkfeeds"))
async def cmd_checkfeeds(message: Message):
    if not await guard(message): return
    feeds = db.get_feeds()
    if not feeds:
        await message.answer("No feeds to check.")
        return
    from fetcher import check_feed
    await message.answer(f"🔍 Checking {len(feeds)} feeds...")
    results = await asyncio.gather(*[check_feed(url) for url in feeds])
    ok, fail = [], []
    for url, res in zip(feeds, results):
        short = url.replace("https://","").replace("http://","")[:60]
        if res["ok"]:
            ok.append(f"✅ {short} ({res['entries']} entries)")
        else:
            fail.append(f"❌ {short} — {res['error']}")
    text = f"<b>Feed Check ({len(feeds)} total)</b>"
    if ok:
        text += f"\n\n<b>✅ Working ({len(ok)}):</b>\n" + "\n".join(f"  {l}" for l in ok)
    if fail:
        text += f"\n\n<b>❌ Failed ({len(fail)}):</b>\n" + "\n".join(f"  {l}" for l in fail)
        text += "\n\n💡 /removefeed &lt;url&gt; to clean up."
    await _send_long(message, text)

@dp.message(Command("channels"))
async def cmd_channels(message: Message):
    if not await guard(message): return
    channels = db.get_tg_channels()
    if not channels:
        await message.answer("No TG channels. Use /addchannel.")
        return
    lines = "\n".join(f"  {i+1}. @{html.escape(c)}" for i, c in enumerate(channels))
    await message.answer(f"📲 <b>Telegram Channels ({len(channels)}):</b>\n{lines}", parse_mode="HTML")

@dp.message(Command("addchannel"))
async def cmd_addchannel(message: Message):
    if not await guard(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /addchannel &lt;@username&gt;", parse_mode="HTML")
        return
    username = parts[1].strip().lstrip("@")
    if db.add_tg_channel(username):
        await message.answer(
            f"✅ Monitoring: <code>@{html.escape(username)}</code>\n"
            "⚠️ Only <b>public</b> channels work.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Already monitoring @{html.escape(username)}", parse_mode="HTML")

@dp.message(Command("removechannel"))
async def cmd_removechannel(message: Message):
    if not await guard(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /removechannel &lt;@username&gt;", parse_mode="HTML")
        return
    username = parts[1].strip().lstrip("@")
    if db.remove_tg_channel(username):
        await message.answer(f"✅ Removed: @{html.escape(username)}", parse_mode="HTML")
    else:
        await message.answer("⚠️ Not found. Use /channels.")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not await guard(message): return
    await message.answer(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"  • Articles seen: <b>{db.get_sent_count()}</b>\n"
        f"  • Initialized: <b>{'Yes' if db.is_initialized() else 'No (first cycle pending)'}</b>\n"
        f"  • Keywords: <b>{len(db.get_keywords())}</b>\n"
        f"  • RSS feeds: <b>{len(db.get_feeds())}</b>\n"
        f"  • TG channels: <b>{len(db.get_tg_channels())}</b>\n"
        f"  • Check interval: every <b>{CHECK_INTERVAL_MINUTES} min</b>\n"
        f"  • Posting to: <b>{CHANNEL_ID}</b>",
        parse_mode="HTML"
    )

@dp.message(Command("runnow"))
async def cmd_runnow(message: Message):
    if not await guard(message): return
    await message.answer("🔄 Fetching news now...")

    all_articles = await _fetch_matching()
    if not all_articles:
        await message.answer("No matching articles found.")
        return

    new_articles = [a for a in all_articles if not db.is_sent(a["link"])]
    if not new_articles:
        await message.answer(f"No new articles — {len(all_articles)} found but all already seen.")
        return

    # /runnow always posts — it sets initialized if needed too
    if not db.is_initialized():
        db.set_initialized()

    sent = await _post_articles(new_articles)
    await message.answer(
        f"✅ Done: <b>{sent}</b> posted, <b>{len(new_articles) - sent}</b> pending.\n"
        f"Total articles seen: <b>{db.get_sent_count()}</b>",
        parse_mode="HTML"
    )


# ─── Helper ──────────────────────────────────────────────────────────────────

async def _send_long(message: Message, text: str):
    if len(text) <= 4096:
        await message.answer(text, parse_mode="HTML")
        return
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 4000:
            await message.answer(chunk.strip(), parse_mode="HTML")
            chunk = line
        else:
            chunk += "\n" + line
    if chunk:
        await message.answer(chunk.strip(), parse_mode="HTML")


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_news_cycle, "interval", minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()
    logger.info(
        f"Bot started | Channel: {CHANNEL_ID} | "
        f"First scheduled check in {CHECK_INTERVAL_MINUTES} min"
    )
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
