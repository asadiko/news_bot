"""
fetcher.py — Async RSS feed fetching and keyword matching.
"""

import asyncio
import logging
import re
import feedparser
import aiohttp
from config import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def _clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()


def _matches_keywords(title: str, summary: str, keywords: list[str]) -> bool:
    text = (title + " " + summary).lower()
    for kw in keywords:
        kw_lower = kw.lower()
        if len(kw_lower) <= 5:
            if re.search(r"\b" + re.escape(kw_lower) + r"\b", text):
                return True
        else:
            if kw_lower in text:
                return True
    return False


def _parse_feed_content(content: bytes, url: str) -> list[dict]:
    """Parse feed bytes with fallback for malformed XML (strips illegal chars)."""
    parsed = feedparser.parse(content)

    # If bozo but entries exist, use them anyway (many valid feeds have minor XML issues)
    if parsed.bozo and not parsed.entries:
        try:
            text = content.decode("utf-8", errors="replace")
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
            parsed = feedparser.parse(text)
        except Exception:
            pass

    results = []
    for entry in parsed.entries:
        link = entry.get("link", "").strip()
        title = _clean_html(entry.get("title", "")).strip()
        summary = _clean_html(entry.get("summary", entry.get("description", ""))).strip()
        if not link or not title:
            continue
        results.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source": parsed.feed.get("title", url),
        })
    return results


async def fetch_feed(session: aiohttp.ClientSession, url: str) -> list[dict]:
    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
            if resp.status != 200:
                logger.warning(f"Feed {url} → HTTP {resp.status}")
                return []
            content = await resp.read()
        return _parse_feed_content(content, url)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ({REQUEST_TIMEOUT_SECONDS}s): {url}")
        return []
    except aiohttp.ClientConnectorError as e:
        logger.warning(f"DNS/connection error: {url}")
        return []
    except aiohttp.ClientError as e:
        logger.warning(f"Network error: {url} — {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return []


async def check_feed(url: str) -> dict:
    """
    Test a single feed URL. Returns status dict with ok, entries, error.
    Used by /checkfeeds command.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
                if resp.status != 200:
                    return {"ok": False, "entries": 0, "error": f"HTTP {resp.status}"}
                content = await resp.read()
        items = _parse_feed_content(content, url)
        return {"ok": len(items) > 0, "entries": len(items), "error": None}
    except asyncio.TimeoutError:
        return {"ok": False, "entries": 0, "error": "Timeout"}
    except aiohttp.ClientConnectorError:
        return {"ok": False, "entries": 0, "error": "DNS/connection failed"}
    except Exception as e:
        return {"ok": False, "entries": 0, "error": str(e)[:60]}


async def fetch_all_feeds(feed_urls: list[str], keywords: list[str]) -> list[dict]:
    if not feed_urls or not keywords:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        tasks = [fetch_feed(session, url) for url in feed_urls]
        all_results = await asyncio.gather(*tasks)

    seen_links: set[str] = set()
    matched = []
    for feed_items in all_results:
        for item in feed_items:
            link = item["link"]
            if link in seen_links:
                continue
            seen_links.add(link)
            if _matches_keywords(item["title"], item["summary"], keywords):
                matched.append(item)

    total = sum(len(r) for r in all_results)
    logger.info(f"RSS: {total} articles from {len(feed_urls)} feeds → {len(matched)} matched")
    return matched
