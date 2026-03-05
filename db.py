"""
db.py — JSON-based persistent store.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from filelock import FileLock

DB_PATH = "data.json"
LOCK_PATH = DB_PATH + ".lock"
logger = logging.getLogger(__name__)


def _load() -> dict:
    if not os.path.exists(DB_PATH):
        return {"initialized": False, "keywords": [], "feeds": [], "tg_channels": [], "sent_links": {}}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _with_lock(fn):
    def wrapper(*args, **kwargs):
        lock = FileLock(LOCK_PATH, timeout=10)
        with lock:
            return fn(*args, **kwargs)
    return wrapper


# ─── Init flag ───────────────────────────────────────────────────────────────

@_with_lock
def is_initialized() -> bool:
    """True after the very first flood-prevention cycle has run."""
    return _load().get("initialized", False)

@_with_lock
def set_initialized() -> None:
    data = _load()
    data["initialized"] = True
    _save(data)


# ─── Sent Links ──────────────────────────────────────────────────────────────

@_with_lock
def is_sent(link: str) -> bool:
    return link in _load().get("sent_links", {})

@_with_lock
def mark_sent(link: str) -> None:
    data = _load()
    data.setdefault("sent_links", {})[link] = datetime.utcnow().isoformat()
    _save(data)

@_with_lock
def bulk_mark_sent(links: list) -> None:
    data = _load()
    ts = datetime.utcnow().isoformat()
    store = data.setdefault("sent_links", {})
    for link in links:
        store[link] = ts
    _save(data)

@_with_lock
def purge_old_links(max_age_days: int = 30) -> int:
    data = _load()
    store = data.get("sent_links", {})
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    before = len(store)
    data["sent_links"] = {
        link: ts for link, ts in store.items()
        if datetime.fromisoformat(ts) > cutoff
    }
    removed = before - len(data["sent_links"])
    if removed > 0:
        _save(data)
        logger.info(f"Purged {removed} old sent links.")
    return removed

@_with_lock
def get_sent_count() -> int:
    return len(_load().get("sent_links", {}))


# ─── Keywords ────────────────────────────────────────────────────────────────

@_with_lock
def get_keywords() -> list:
    return _load().get("keywords", [])

@_with_lock
def add_keyword(kw: str) -> bool:
    data = _load()
    kws = data.setdefault("keywords", [])
    if kw.lower() in [k.lower() for k in kws]:
        return False
    kws.append(kw)
    _save(data)
    return True

@_with_lock
def remove_keyword(kw: str) -> bool:
    data = _load()
    kws = data.get("keywords", [])
    new_kws = [k for k in kws if k.lower() != kw.lower()]
    if len(new_kws) == len(kws):
        return False
    data["keywords"] = new_kws
    _save(data)
    return True


# ─── Feeds ───────────────────────────────────────────────────────────────────

@_with_lock
def get_feeds() -> list:
    return _load().get("feeds", [])

@_with_lock
def add_feed(url: str) -> bool:
    data = _load()
    feeds = data.setdefault("feeds", [])
    if url in feeds:
        return False
    feeds.append(url)
    _save(data)
    return True

@_with_lock
def remove_feed(url: str) -> bool:
    data = _load()
    feeds = data.get("feeds", [])
    new_feeds = [f for f in feeds if f != url]
    if len(new_feeds) == len(feeds):
        return False
    data["feeds"] = new_feeds
    _save(data)
    return True


# ─── Telegram Channels ───────────────────────────────────────────────────────

@_with_lock
def get_tg_channels() -> list:
    return _load().get("tg_channels", [])

@_with_lock
def add_tg_channel(username: str) -> bool:
    username = username.lstrip("@")
    data = _load()
    channels = data.setdefault("tg_channels", [])
    if username.lower() in [c.lower() for c in channels]:
        return False
    channels.append(username)
    _save(data)
    return True

@_with_lock
def remove_tg_channel(username: str) -> bool:
    username = username.lstrip("@")
    data = _load()
    channels = data.get("tg_channels", [])
    new = [c for c in channels if c.lower() != username.lower()]
    if len(new) == len(channels):
        return False
    data["tg_channels"] = new
    _save(data)
    return True
