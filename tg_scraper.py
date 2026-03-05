"""
tg_scraper.py — Scrapes public Telegram channels via t.me/s/<channel>
No Telegram API credentials needed — uses the public web preview.
Falls back gracefully if a channel is private or unavailable.
"""

import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup
from config import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

TG_WEB_BASE = "https://t.me/s/{channel}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


async def fetch_tg_channel(session: aiohttp.ClientSession, channel: str) -> list[dict]:
    """
    Scrape recent posts from a public Telegram channel.
    Returns list of {title, link, summary, source} dicts.
    """
    url = TG_WEB_BASE.format(channel=channel)
    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with session.get(url, timeout=timeout, headers=HEADERS) as resp:
            if resp.status != 200:
                logger.warning(f"TG channel @{channel} returned HTTP {resp.status}")
                return []
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message_wrap")

        if not messages:
            logger.warning(f"TG channel @{channel}: no messages found (private or empty?)")
            return []

        results = []
        for msg in messages:
            # Extract message text
            text_div = msg.find("div", class_="tgme_widget_message_text")
            text = _clean(text_div.get_text(" ", strip=True)) if text_div else ""

            if not text:
                continue

            # Extract message URL (permalink)
            link_tag = msg.find("a", class_="tgme_widget_message_date")
            link = link_tag["href"] if link_tag and link_tag.get("href") else url

            # Use first 100 chars of text as title
            title = text[:100] + ("..." if len(text) > 100 else "")

            results.append({
                "title": title,
                "link": link,
                "summary": text,
                "source": f"@{channel}",
            })

        logger.info(f"@{channel}: scraped {len(results)} messages")
        return results

    except asyncio.TimeoutError:
        logger.warning(f"Timeout scraping TG channel @{channel}")
        return []
    except aiohttp.ClientError as e:
        logger.warning(f"Network error scraping @{channel}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error scraping @{channel}: {e}")
        return []


async def fetch_all_tg_channels(channels: list[str], keywords: list[str]) -> list[dict]:
    """
    Concurrently scrape all Telegram channels and return keyword-matched posts.
    """
    if not channels or not keywords:
        return []

    from fetcher import _matches_keywords  # reuse keyword matching logic

    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_tg_channel(session, ch) for ch in channels]
        all_results = await asyncio.gather(*tasks, return_exceptions=False)

    seen_links = set()
    matched = []
    for channel_posts in all_results:
        for post in channel_posts:
            link = post["link"]
            if link in seen_links:
                continue
            seen_links.add(link)
            if _matches_keywords(post["title"], post["summary"], keywords):
                matched.append(post)

    logger.info(f"TG channels: {sum(len(r) for r in all_results)} posts scraped, {len(matched)} matched.")
    return matched
