from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import backoff
import focused_news
import news_classifier
import news_collector
import news_db
import news_reporter


class FakeClient:
    def __init__(self, payload):
        class Responses:
            def __init__(self):
                self.calls = []

            def create(inner_self, **kwargs):
                inner_self.calls.append(kwargs)
                return SimpleNamespace(output_text=json.dumps(payload))

        self.responses = Responses()


class FakeRateLimitError(Exception):
    def __init__(self, retry_after=None):
        super().__init__("429 rate limited")
        self.status_code = 429
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = str(retry_after)


def post(number, blogger="Belghast", blog="Tales of the Aggronaut"):
    return {
        "id": number,
        "feed_url": "https://example.test/feed",
        "guid": f"guid-{number}",
        "url": f"https://example.test/posts/{number}",
        "title": f"Post {number}",
        "blogger": blogger,
        "blog_name": blog,
        "published_at": "2026-07-20T12:00:00+00:00",
        "full_text": "A sufficiently detailed article body. " * 30,
    }


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.db"
        news_db.initialize(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def add_classified(self, number, topic):
        item = post(number)
        news_db.add_post(item, retention_days=7, db_path=self.db)
        with news_db.connect(self.db) as con:
            post_id = con.execute(
                "SELECT id FROM news_posts WHERE guid = ?", (item["guid"],)
            ).fetchone()["id"]
        news_db.save_classifications(
            post_id,
            [{"topic_id": topic, "relevance": 0.9, "rationale": "match"}],
            db_path=self.db,
        )
        return post_id

    def test_existing_report_table_is_migrated_for_html_supplements(self):
        legacy = Path(self.temp.name) / "legacy.db"
        with news_db.connect(legacy) as con:
            con.execute(
                """
                CREATE TABLE news_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    output_path TEXT
                )
                """
            )
        news_db.initialize(legacy)
        with news_db.connect(legacy) as con:
            columns = {
                row["name"] for row in con.execute(
                    "PRAGMA table_info(news_reports)"
                )
            }
        self.assertTrue({
            "summary", "topic_name", "edition_date", "body_json", "public_url"
        }.issubset(columns))

    def test_rotation_prefers_never_published_topic_without_miscounting(self):
        for i in range(1, 3):
            self.add_classified(i, "mmorpgs")
        for i in range(3, 5):
            self.add_classified(i, "blogging")
        with news_db.connect(self.db) as con:
            con.execute(
                "INSERT INTO news_reports(topic_id,title,markdown,generated_at) VALUES(?,?,?,?)",
                ("mmorpgs", "Old", "body", "2026-07-01T00:00:00+00:00"),
            )
        eligible = news_db.eligible_topics(2, db_path=self.db)
        self.assertEqual([r["topic_id"] for r in eligible], ["blogging", "mmorpgs"])
        self.assertEqual([r["available_count"] for r in eligible], [2, 2])

    def test_only_referenced_posts_are_consumed(self):
        first = self.add_classified(1, "mmorpgs")
        second = self.add_classified(2, "mmorpgs")
        news_db.save_report(
            "mmorpgs", "Report", "body", [first], "report.md", db_path=self.db
        )
        with news_db.connect(self.db) as con:
            rows = con.execute("SELECT id, full_text FROM news_posts ORDER BY id").fetchall()
        self.assertIsNone(rows[0]["full_text"])
        self.assertIsNotNone(rows[1]["full_text"])
        self.assertEqual([rows[0]["id"], rows[1]["id"]], [first, second])

    def test_post_timestamps_are_normalized_to_utc(self):
        item = post(1)
        item["published_at"] = "2026-07-20T08:00:00-04:00"
        news_db.add_post(item, retention_days=7, db_path=self.db)
        with news_db.connect(self.db) as con:
            stored = con.execute(
                "SELECT published_at, expires_at FROM news_posts WHERE guid = ?",
                (item["guid"],),
            ).fetchone()
        self.assertEqual(stored["published_at"], "2026-07-20T12:00:00+00:00")
        self.assertEqual(stored["expires_at"], "2026-07-27T12:00:00+00:00")

    def test_invalid_published_timestamp_is_not_stored(self):
        item = post(1)
        item["published_at"] = "not a timestamp"
        news_db.add_post(item, retention_days=7, db_path=self.db)
        with news_db.connect(self.db) as con:
            stored = con.execute(
                "SELECT published_at FROM news_posts WHERE guid = ?", (item["guid"],)
            ).fetchone()
        self.assertIsNone(stored["published_at"])

    def test_topic_inventory_counts_only_available_posts(self):
        first = self.add_classified(1, "mmorpgs")
        self.add_classified(2, "mmorpgs")
        self.add_classified(3, "blogging")
        news_db.save_report(
            "mmorpgs", "Report", "body", [first], "report.md", db_path=self.db
        )
        inventory = {
            row["topic_id"]: row["available_count"]
            for row in news_db.topic_inventory(db_path=self.db)
        }
        self.assertEqual(inventory, {"blogging": 1, "mmorpgs": 1})


class ModelTests(unittest.TestCase):
    def test_classifier_uses_mocked_gpt_response(self):
        client = FakeClient({"posts": [{"post_id": 7, "topics": [{
            "topic_id": "mmorpgs", "relevance": 0.95, "rationale": "It is about an MMO."
        }]}]})
        result = news_classifier.classify_batch(
            [post(7)],
            [{"id": "mmorpgs", "name": "MMORPGs", "description": "MMOs"}],
            client=client,
        )
        self.assertEqual(result["posts"][0]["topics"][0]["topic_id"], "mmorpgs")
        self.assertEqual(len(client.responses.calls), 1)

    def test_classifier_retries_after_429_with_graduated_backoff(self):
        payload = {"posts": [{"post_id": 7, "topics": []}]}

        class Responses:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise FakeRateLimitError()
                return SimpleNamespace(output_text=json.dumps(payload))

        client = SimpleNamespace(responses=Responses())
        with patch.object(backoff.time, "sleep") as sleep:
            result = news_classifier.classify_batch(
                [post(7)],
                [{"id": "mmorpgs", "name": "MMORPGs", "description": "MMOs"}],
                client=client,
            )
        self.assertEqual(result, payload)
        self.assertEqual(client.responses.calls, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2.0, 4.0])

    def test_reporter_validates_source_markers_and_builds_references(self):
        result = {
            "title": "Signals from New Eden",
            "summary": "[[P1]] reports from beyond the grave.",
            "body": ["The afterlife has terrible latency, according to [[P1]]."],
            "used_source_ids": ["P1"],
        }
        validated, used = news_reporter.validate_report(result, [post(1)])
        references = news_reporter.references_for_report(validated, [post(1)])
        segments = news_reporter.segment_text(validated["summary"], references)
        self.assertEqual(used, [1])
        self.assertEqual(references[0]["blogger"], "Belghast")
        self.assertEqual(references[0]["blog_name"], "Tales of the Aggronaut")
        self.assertEqual(segments[0]["reference"]["url"], "https://example.test/posts/1")

    def test_reporter_rejects_declared_but_unmarked_source(self):
        result = {
            "title": "Bad source list",
            "summary": "A broad introduction.",
            "body": ["Only [[P1]] is actually referenced."],
            "used_source_ids": ["P1", "P2"],
        }
        with self.assertRaisesRegex(ValueError, "do not match"):
            news_reporter.validate_report(result, [post(1), post(2)])

    def test_reporter_rejects_unknown_source_marker(self):
        result = {
            "title": "Unknown source",
            "summary": "[[P9]] reports something.",
            "body": ["A complete paragraph."],
            "used_source_ids": ["P9"],
        }
        with self.assertRaisesRegex(ValueError, "unknown"):
            news_reporter.validate_report(result, [post(1)])

    def test_reporter_rejects_duplicate_declared_source(self):
        result = {
            "title": "Duplicate source",
            "summary": "[[P1]] reports something.",
            "body": ["More context from [[P1]]."],
            "used_source_ids": ["P1", "P1"],
        }
        with self.assertRaisesRegex(ValueError, "duplicates"):
            news_reporter.validate_report(result, [post(1)])

    def test_reporter_requires_complete_prose(self):
        result = {
            "title": "Incomplete",
            "summary": "",
            "body": [],
            "used_source_ids": ["P1"],
        }
        with self.assertRaisesRegex(ValueError, "title, summary"):
            news_reporter.validate_report(result, [post(1)])

    def test_fake_clients_do_not_share_call_history(self):
        first = FakeClient({"posts": []})
        second = FakeClient({"posts": []})
        first.responses.create()
        self.assertEqual(len(first.responses.calls), 1)
        self.assertEqual(len(second.responses.calls), 0)


def time_tuple(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).timetuple()


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.db"

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def parsed(timestamp):
        entry = SimpleNamespace(
            id="item-1", link="https://example.test/item-1", title="A Post",
            published_parsed=time_tuple(timestamp),
        )
        return SimpleNamespace(entries=[entry], bozo=False, etag="etag-1", modified=None)

    def patches(self, timestamp):
        return (
            patch.object(news_collector, "load_feeds", return_value=[{
                "name": "Example Blog", "blogger": "Example", "url": "https://example.test/feed"
            }]),
            patch.object(news_collector.feedparser, "parse", return_value=self.parsed(timestamp)),
            patch.object(news_collector, "fetch_readable", return_value=("A Post", "body " * 200)),
        )

    def test_first_ordinary_run_does_not_mine_backlog(self):
        old = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).timestamp())
        feeds, parser, fetch = self.patches(old)
        with feeds, parser, fetch as mocked_fetch:
            stats = news_collector.collect(db_path=self.db)
        self.assertEqual(stats["stored"], 0)
        mocked_fetch.assert_not_called()

    def test_explicit_backlog_seed_stores_full_text(self):
        recent = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).timestamp())
        feeds, parser, fetch = self.patches(recent)
        with feeds, parser, fetch:
            stats = news_collector.collect(db_path=self.db, backlog_days=7)
        self.assertEqual(stats["stored"], 1)
        with news_db.connect(self.db) as con:
            row = con.execute("SELECT full_text FROM news_posts").fetchone()
        self.assertGreater(len(row["full_text"]), 500)

    def test_existing_post_is_not_fetched_again(self):
        recent = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).timestamp())
        news_db.initialize(self.db)
        news_db.add_post(
            {
                **post(1),
                "feed_url": "https://example.test/feed",
                "guid": "item-1",
                "url": "https://example.test/item-1",
            },
            retention_days=7,
            db_path=self.db,
        )
        feeds, parser, fetch = self.patches(recent)
        with self.assertLogs("focused_news.collector", level="DEBUG") as logs, \
                feeds, parser, fetch as mocked_fetch:
            stats = news_collector.collect(db_path=self.db, backlog_days=7)
        self.assertEqual(stats["stored"], 0)
        mocked_fetch.assert_not_called()
        self.assertTrue(any("already cached" in message for message in logs.output))

    def test_backlog_seed_still_ignores_entries_older_than_retention_window(self):
        old = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).timestamp())
        feeds, parser, fetch = self.patches(old)
        with feeds, parser, fetch as mocked_fetch:
            stats = news_collector.collect(db_path=self.db, backlog_days=30, retention_days=7)
        self.assertEqual(stats["stored"], 0)
        mocked_fetch.assert_not_called()

    def test_fetch_readable_retries_after_429_then_succeeds(self):
        rate_limited = SimpleNamespace(status_code=429, headers={}, text="", raise_for_status=lambda: None)
        success = SimpleNamespace(
            status_code=200,
            headers={},
            text="<html><head><title>Readable Title</title></head><body><p>body</p></body></html>",
            raise_for_status=lambda: None,
        )

        with patch.object(news_collector.requests, "get", side_effect=[rate_limited, success]) as get, \
                patch.object(backoff.time, "sleep") as sleep:
            title, body = news_collector.fetch_readable("https://example.test/item-1")

        self.assertEqual(title, "Readable Title")
        self.assertTrue(body)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(2.0)

    def test_fetch_readable_uses_retry_after_header_on_429(self):
        rate_limited = SimpleNamespace(status_code=429, headers={"Retry-After": "7"}, text="", raise_for_status=lambda: None)
        success = SimpleNamespace(
            status_code=200,
            headers={},
            text="<html><head><title>Readable Title</title></head><body><p>body</p></body></html>",
            raise_for_status=lambda: None,
        )

        with patch.object(news_collector.requests, "get", side_effect=[rate_limited, success]), \
                patch.object(backoff.time, "sleep") as sleep:
            news_collector.fetch_readable("https://example.test/item-1")

        sleep.assert_called_once_with(7.0)


class OrchestrationTests(unittest.TestCase):
    def test_supplement_template_renders_escaped_prose_and_references(self):
        references = [{
            "source_id": "P1",
            "post_id": 1,
            "blogger": "Belghast",
            "blog_name": "Tales of the Aggronaut",
            "title": "Post 1",
            "url": "https://example.test/posts/1",
            "published_at": "2026-07-20T12:00:00+00:00",
        }]
        output = focused_news.render_supplement(
            {
                "title": "Signals from New Eden",
                "summary": "[[P1]] sees a pattern.",
                "body": ["A <script>alert('no')</script> remains text beside [[P1]]."],
                "edition_date": "2026-07-21",
                "topic_name": "MMORPGs",
            },
            references,
        )
        self.assertIn("<h1>Signals from New Eden</h1>", output)
        self.assertIn("Belghast on Tales of the Aggronaut</a>", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertNotIn("<script>alert", output)
        self.assertIn("<h2>Posts Discussed</h2>", output)

    def test_parser_accepts_verbose_flag(self):
        args = focused_news.parser().parse_args(["--verbose"])
        self.assertTrue(args.verbose)

    def test_logging_defaults_to_warnings_and_verbose_enables_debug(self):
        self.addCleanup(focused_news.configure_logging, False)
        focused_news.configure_logging(False)
        self.assertEqual(focused_news.LOGGER.level, 30)
        focused_news.configure_logging(True)
        self.assertEqual(focused_news.LOGGER.level, 10)

    def test_removed_topic_is_skipped_for_next_configured_topic(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            news_db.initialize(database)
            with patch.object(focused_news, "BLOGROLLS_DIR", Path(directory)), \
                    patch.object(
                        news_db,
                        "eligible_topics",
                        return_value=[
                            {"topic_id": "removed"},
                            {"topic_id": "technology"},
                        ],
                    ), patch.object(
                        news_classifier,
                        "load_topics",
                        return_value=[{"id": "technology", "name": "Technology"}],
                    ), patch.object(
                        news_db, "candidate_posts", return_value=[post(1)]
                    ), patch.object(
                        news_reporter,
                        "generate_report",
                        return_value={
                            "title": "Tech Report",
                            "summary": "[[P1]] reports.",
                            "body": ["A thoughtful body from [[P1]]."],
                            "used_source_ids": ["P1"],
                        },
                    ) as generate, patch.object(
                        focused_news, "render_saved_supplements"
                    ), patch.object(news_db, "save_report") as save:
                output = focused_news.generate_if_ready(
                    db_path=database,
                    topics_path="topics.yaml",
                    output_dir=directory,
                    threshold=1,
                )
        self.assertIsNotNone(output)
        today = dt.date.today()
        expected_parent = Path(directory) / f"{today:%Y}" / f"{today:%m}"
        self.assertEqual(output.parent, expected_parent)
        self.assertTrue(output.name.startswith(f"deep-dive-{today.isoformat()}-"))
        self.assertEqual(output.suffix, ".html")
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[0], "Technology")
        self.assertEqual(save.call_args.args[0], "technology")


if __name__ == "__main__":
    unittest.main()
