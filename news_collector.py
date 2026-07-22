"""Feed discovery and full-article collection for focused news."""

from __future__ import annotations

import calendar
import datetime as dt
import email.utils
import logging
import time
from pathlib import Path

import feedparser
import requests
import yaml
from markdownify import markdownify
from readability import Document

from backoff import run_with_429_backoff
import news_db


USER_AGENT = "DailyBlogrollFocusedNews/0.1 (+https://westkarana.xyz/)"
LOGGER = logging.getLogger("focused_news.collector")


def load_feeds(path: str | Path = "feeds.yaml") -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["feeds"]


def entry_timestamp(entry) -> int | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, key, None)
        if value:
            return calendar.timegm(value)
    for key in ("published", "updated"):
        value = getattr(entry, key, None)
        if value:
            try:
                parsed = email.utils.parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                return int(parsed.timestamp())
            except (TypeError, ValueError):
                pass
    return None


def fetch_readable(url: str, timeout: int = 20) -> tuple[str, str]:
    def load_response():
        response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if response.status_code == 429:
            raise requests.HTTPError("429 Too Many Requests", response=response)
        response.raise_for_status()
        return response

    response = run_with_429_backoff(
        load_response,
        logger=LOGGER,
        description=f"fetching article {url}",
    )
    document = Document(response.text)
    title = (document.title() or "").strip()
    body = markdownify(document.summary()).strip()
    if len(body) < 200:
        body = markdownify(response.text).strip()
    return title, body


def collect(
    *,
    feeds_path: str | Path = "feeds.yaml",
    db_path: str | Path = "blogroll.db",
    retention_days: int = 7,
    backlog_days: int | None = None,
    min_chars: int = 500,
) -> dict:
    """Collect unseen posts.

    ``backlog_days`` is intentionally explicit.  With it omitted, a feed with
    no focused-news polling history starts at the current time and does not
    silently mine its backlog.
    """
    news_db.initialize(db_path)
    now_ts = int(time.time())
    retention_cutoff = now_ts - retention_days * 86400
    backlog_cutoff = now_ts - backlog_days * 86400 if backlog_days is not None else None
    stats = {"feeds": 0, "entries": 0, "stored": 0, "errors": []}

    feeds = load_feeds(feeds_path)
    LOGGER.debug("Checking %d configured feeds.", len(feeds))
    for feed in feeds:
        if feed.get("skip", False):
            LOGGER.debug("Skipping disabled feed %s.", feed.get("name", feed.get("url", "unknown")))
            continue
        feed_url = feed["url"]
        feed_name = feed.get("name", feed_url)
        LOGGER.debug("Checking %s.", feed_name)
        state = news_db.get_feed_state(feed_url, db_path)
        first_poll = state is None
        kwargs = {}
        if state and backlog_days is None:
            if state["etag"]:
                kwargs["etag"] = state["etag"]
            if state["modified"]:
                kwargs["modified"] = state["modified"]
        try:
            parsed = feedparser.parse(feed_url, **kwargs)
            stats["feeds"] += 1
            if getattr(parsed, "bozo", False) and not parsed.entries:
                raise ValueError(str(getattr(parsed, "bozo_exception", "feed parse failed")))

            # Never fetch feed entries older than the retention window.
            effective_cutoff = retention_cutoff
            if backlog_cutoff is not None:
                effective_cutoff = max(effective_cutoff, backlog_cutoff)

            # First ordinary poll establishes the DB checkpoint without mining.
            if first_poll and backlog_days is None:
                effective_cutoff = now_ts

            for entry in parsed.entries:
                timestamp = entry_timestamp(entry)
                if effective_cutoff is not None and (timestamp is None or timestamp < effective_cutoff):
                    continue
                stats["entries"] += 1
                url = getattr(entry, "link", "")
                guid = getattr(entry, "id", None) or url
                if not url or not guid:
                    LOGGER.debug("%s: skipped entry without URL or GUID.", feed_name)
                    continue
                if news_db.post_exists(feed_url, guid, url, db_path):
                    LOGGER.debug("%s: already cached; skipped %s.", feed_name, url)
                    continue
                try:
                    readable_title, body = fetch_readable(url)
                    if len(body) < min_chars:
                        LOGGER.debug("%s: article was too short; skipped %s.", feed_name, url)
                        continue
                    published = (
                        dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()
                        if timestamp else None
                    )
                    inserted = news_db.add_post(
                        {
                            "feed_url": feed_url,
                            "guid": guid,
                            "url": url,
                            "title": (getattr(entry, "title", "") or readable_title or "(untitled)").strip(),
                            "blogger": feed.get("blogger") or feed.get("name") or "Unknown",
                            "blog_name": feed.get("name") or feed_url,
                            "published_at": published,
                            "full_text": body,
                        },
                        retention_days=retention_days,
                        db_path=db_path,
                    )
                    stats["stored"] += int(inserted)
                    if inserted:
                        LOGGER.debug("%s: stored %s.", feed_name, url)
                except Exception as exc:  # keep one broken article from blocking its feed
                    message = f"{url}: {exc}"
                    stats["errors"].append(message)
                    LOGGER.warning("Article fetch failed: %s", message)

            modified = getattr(parsed, "modified", None)
            if modified and not isinstance(modified, str):
                modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT", modified)
            news_db.upsert_feed_state(
                feed_url,
                etag=getattr(parsed, "etag", None),
                modified=modified,
                success=True,
                db_path=db_path,
            )
        except Exception as exc:
            message = f"{feed_url}: {exc}"
            stats["errors"].append(message)
            LOGGER.warning("Feed check failed: %s", message)
            news_db.upsert_feed_state(
                feed_url, etag=None, modified=None, success=False, db_path=db_path
            )
    return stats
