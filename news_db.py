"""SQLite persistence for the focused-news application.

All tables are deliberately prefixed with ``news_``.  The module shares the
database file with Daily Blogroll but neither reads nor modifies its tables.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Iterable

from settings import DB_PATH


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def initialize(db_path: str | Path = DB_PATH) -> None:
    with connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS news_feeds (
                feed_url TEXT PRIMARY KEY,
                etag TEXT,
                modified TEXT,
                last_checked_at TEXT,
                last_success_at TEXT
            );

            CREATE TABLE IF NOT EXISTS news_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT NOT NULL,
                guid TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                blogger TEXT NOT NULL,
                blog_name TEXT NOT NULL,
                published_at TEXT,
                discovered_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                full_text TEXT,
                classified_at TEXT,
                UNIQUE(feed_url, guid),
                UNIQUE(url)
            );

            CREATE TABLE IF NOT EXISTS news_post_topics (
                post_id INTEGER NOT NULL REFERENCES news_posts(id) ON DELETE CASCADE,
                topic_id TEXT NOT NULL,
                relevance REAL NOT NULL CHECK(relevance >= 0 AND relevance <= 1),
                rationale TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(post_id, topic_id)
            );

            CREATE TABLE IF NOT EXISTS news_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id TEXT NOT NULL,
                title TEXT NOT NULL,
                markdown TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                output_path TEXT
            );

            CREATE TABLE IF NOT EXISTS news_report_posts (
                report_id INTEGER NOT NULL REFERENCES news_reports(id) ON DELETE CASCADE,
                post_id INTEGER NOT NULL REFERENCES news_posts(id),
                PRIMARY KEY(report_id, post_id)
            );

            CREATE INDEX IF NOT EXISTS news_posts_classification_idx
                ON news_posts(classified_at, expires_at);
            CREATE INDEX IF NOT EXISTS news_post_topics_topic_idx
                ON news_post_topics(topic_id, relevance);
            CREATE INDEX IF NOT EXISTS news_reports_topic_idx
                ON news_reports(topic_id, generated_at);
            """
        )


def upsert_feed_state(
    feed_url: str,
    *,
    etag: str | None,
    modified: str | None,
    success: bool,
    db_path: str | Path = DB_PATH,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO news_feeds(feed_url, etag, modified, last_checked_at, last_success_at)
            VALUES (?, ?, ?, ?, CASE WHEN ? THEN ? ELSE NULL END)
            ON CONFLICT(feed_url) DO UPDATE SET
                etag = COALESCE(excluded.etag, news_feeds.etag),
                modified = COALESCE(excluded.modified, news_feeds.modified),
                last_checked_at = excluded.last_checked_at,
                last_success_at = CASE WHEN ? THEN excluded.last_checked_at
                                       ELSE news_feeds.last_success_at END
            """,
            (feed_url, etag, modified, now, success, now, success),
        )


def get_feed_state(feed_url: str, db_path: str | Path = DB_PATH) -> sqlite3.Row | None:
    with connect(db_path) as con:
        return con.execute(
            "SELECT * FROM news_feeds WHERE feed_url = ?", (feed_url,)
        ).fetchone()


def post_exists(
    feed_url: str,
    guid: str,
    url: str,
    db_path: str | Path = DB_PATH,
) -> bool:
    with connect(db_path) as con:
        return con.execute(
            """SELECT 1 FROM news_posts
               WHERE url = ? OR (feed_url = ? AND guid = ?)""",
            (url, feed_url, guid),
        ).fetchone() is not None


def add_post(post: dict, *, retention_days: int, db_path: str | Path = DB_PATH) -> bool:
    discovered = dt.datetime.now(dt.timezone.utc)
    retention_start = discovered
    if post.get("published_at"):
        try:
            published = dt.datetime.fromisoformat(post["published_at"])
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            retention_start = min(discovered, published)
        except ValueError:
            pass
    expires = retention_start + dt.timedelta(days=retention_days)
    with connect(db_path) as con:
        cur = con.execute(
            """
            INSERT OR IGNORE INTO news_posts(
                feed_url, guid, url, title, blogger, blog_name, published_at,
                discovered_at, expires_at, full_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post["feed_url"], post["guid"], post["url"], post["title"],
                post["blogger"], post["blog_name"], post.get("published_at"),
                discovered.isoformat(), expires.isoformat(), post["full_text"],
            ),
        )
        return cur.rowcount == 1


def unclassified_posts(limit: int = 50, db_path: str | Path = DB_PATH) -> list[sqlite3.Row]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(db_path) as con:
        return con.execute(
            """
            SELECT * FROM news_posts
            WHERE classified_at IS NULL AND full_text IS NOT NULL AND expires_at > ?
            ORDER BY discovered_at, id LIMIT ?
            """,
            (now, limit),
        ).fetchall()


def save_classifications(
    post_id: int,
    topics: Iterable[dict],
    *,
    db_path: str | Path = DB_PATH,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(db_path) as con:
        con.execute("DELETE FROM news_post_topics WHERE post_id = ?", (post_id,))
        con.executemany(
            """
            INSERT INTO news_post_topics(post_id, topic_id, relevance, rationale)
            VALUES (?, ?, ?, ?)
            """,
            [
                (post_id, t["topic_id"], float(t["relevance"]), t.get("rationale", ""))
                for t in topics
            ],
        )
        con.execute(
            "UPDATE news_posts SET classified_at = ? WHERE id = ?", (now, post_id)
        )


def eligible_topics(
    threshold: int = 12,
    *,
    min_relevance: float = 0.6,
    db_path: str | Path = DB_PATH,
) -> list[sqlite3.Row]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(db_path) as con:
        return con.execute(
            """
            SELECT pt.topic_id, COUNT(*) AS available_count,
                   (SELECT MAX(r.generated_at) FROM news_reports r
                    WHERE r.topic_id = pt.topic_id) AS last_generated_at
            FROM news_post_topics pt
            JOIN news_posts p ON p.id = pt.post_id
            LEFT JOIN news_report_posts rp ON rp.post_id = p.id
            WHERE rp.post_id IS NULL
              AND p.full_text IS NOT NULL
              AND p.expires_at > ?
              AND pt.relevance >= ?
            GROUP BY pt.topic_id
            HAVING COUNT(*) >= ?
            ORDER BY last_generated_at IS NOT NULL, last_generated_at, pt.topic_id
            """,
            (now, min_relevance, threshold),
        ).fetchall()


def candidate_posts(
    topic_id: str,
    limit: int = 15,
    *,
    min_relevance: float = 0.6,
    db_path: str | Path = DB_PATH,
) -> list[sqlite3.Row]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(db_path) as con:
        return con.execute(
            """
            SELECT p.*, pt.relevance, pt.rationale
            FROM news_posts p
            JOIN news_post_topics pt ON pt.post_id = p.id
            LEFT JOIN news_report_posts rp ON rp.post_id = p.id
            WHERE pt.topic_id = ? AND pt.relevance >= ?
              AND rp.post_id IS NULL AND p.full_text IS NOT NULL
              AND p.expires_at > ?
            ORDER BY pt.relevance DESC, p.published_at DESC, p.id DESC
            LIMIT ?
            """,
            (topic_id, min_relevance, now, limit),
        ).fetchall()


def save_report(
    topic_id: str,
    title: str,
    markdown: str,
    post_ids: Iterable[int],
    output_path: str,
    *,
    db_path: str | Path = DB_PATH,
) -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    ids = list(dict.fromkeys(post_ids))
    with connect(db_path) as con:
        cur = con.execute(
            """INSERT INTO news_reports(topic_id, title, markdown, generated_at, output_path)
               VALUES (?, ?, ?, ?, ?)""",
            (topic_id, title, markdown, now, output_path),
        )
        report_id = int(cur.lastrowid)
        con.executemany(
            "INSERT INTO news_report_posts(report_id, post_id) VALUES (?, ?)",
            [(report_id, post_id) for post_id in ids],
        )
        con.executemany(
            "UPDATE news_posts SET full_text = NULL WHERE id = ?",
            [(post_id,) for post_id in ids],
        )
        return report_id


def expire_text(*, db_path: str | Path = DB_PATH) -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(db_path) as con:
        cur = con.execute(
            "UPDATE news_posts SET full_text = NULL WHERE expires_at <= ? AND full_text IS NOT NULL",
            (now,),
        )
        return cur.rowcount
