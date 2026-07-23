from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import blogroll
import focused_news
import news_db


def stored_post(number: int) -> dict:
    return {
        "feed_url": "https://example.test/feed",
        "guid": f"guid-{number}",
        "url": f"https://example.test/posts/{number}",
        "title": f"Post {number}",
        "blogger": f"Blogger {number}",
        "blog_name": f"Blog {number}",
        "published_at": "2026-07-20T12:00:00+00:00",
        "full_text": "Article body " * 100,
    }


class SupplementNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "test.db"
        news_db.initialize(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def add_report(self, number: int, title: str, edition_date: str) -> Path:
        item = stored_post(number)
        news_db.add_post(item, retention_days=30, db_path=self.db)
        with news_db.connect(self.db) as con:
            post_id = con.execute(
                "SELECT id FROM news_posts WHERE guid = ?", (item["guid"],)
            ).fetchone()["id"]
        path = self.root / f"deep-dive-{number}.html"
        news_db.save_report(
            "technology",
            title,
            [f"Report prose from [[P{post_id}]]."],
            [post_id],
            str(path),
            summary=f"Summary from [[P{post_id}]].",
            topic_name="Technology",
            edition_date=edition_date,
            public_url=f"/deep-dives/deep-dive-{number}.html",
            db_path=self.db,
        )
        return path

    def test_saved_supplements_receive_independent_previous_next_navigation(self):
        first = self.add_report(1, "First Report", "2026-07-20")
        second = self.add_report(2, "Second Report", "2026-07-22")

        focused_news.render_saved_supplements(db_path=self.db)

        first_html = first.read_text(encoding="utf-8")
        second_html = second.read_text(encoding="utf-8")
        self.assertIn("Next Deep Dive", first_html)
        self.assertIn("Second Report", first_html)
        self.assertNotIn("Previous Deep Dive", first_html)
        self.assertIn("Previous Deep Dive", second_html)
        self.assertIn("First Report", second_html)
        self.assertNotIn("Next Deep Dive", second_html)
        self.assertEqual(
            news_db.latest_published_report(db_path=self.db)["title"],
            "Second Report",
        )

    def test_saved_supplement_paths_resolve_from_project_root(self):
        self.add_report(1, "Relative Report", "2026-07-20")
        relative_path = Path("docs/deep-dives/relative.html")
        with news_db.connect(self.db) as con:
            con.execute(
                "UPDATE news_reports SET output_path = ?",
                (str(relative_path),),
            )

        with patch.object(focused_news, "ROOT", self.root):
            focused_news.render_saved_supplements(db_path=self.db)

        output = self.root / relative_path
        self.assertTrue(output.exists())
        self.assertIn("Relative Report", output.read_text(encoding="utf-8"))


class BlogrollPromotionTests(unittest.TestCase):
    def test_latest_context_expands_source_markers_for_index_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "test.db"
            supplement_path = root / "deep-dive.html"
            supplement_path.write_text("published", encoding="utf-8")
            news_db.initialize(database)
            item = stored_post(1)
            news_db.add_post(item, retention_days=30, db_path=database)
            with news_db.connect(database) as con:
                post_id = con.execute(
                    "SELECT id FROM news_posts WHERE guid = ?", (item["guid"],)
                ).fetchone()["id"]
            news_db.save_report(
                "technology",
                "A Current Report",
                [f"Body from [[P{post_id}]]."],
                [post_id],
                str(supplement_path),
                summary=f"Today, [[P{post_id}]] considers the news.",
                topic_name="Technology",
                edition_date="2026-07-23",
                public_url="/deep-dives/current.html",
                db_path=database,
            )

            with patch.object(blogroll, "DB_PATH", database):
                context = blogroll.latest_supplement_context(
                    dt.date(2026, 7, 23)
                )

            self.assertEqual(
                context["summary"],
                "Today, Blogger 1 on Blog 1 considers the news.",
            )
            self.assertTrue(context["is_new"])

    def test_latest_context_resolves_relative_output_path_from_project_root(self):
        report = {
            "id": 1,
            "title": "Relative Report",
            "summary": "A current summary.",
            "topic_name": "Technology",
            "edition_date": "2026-07-23",
            "public_url": "/deep-dives/relative.html",
            "output_path": "docs/deep-dives/relative.html",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / report["output_path"]
            output.parent.mkdir(parents=True)
            output.write_text("published", encoding="utf-8")
            with patch.object(blogroll, "ROOT", root), patch.object(
                blogroll.news_db, "initialize"
            ), patch.object(
                blogroll.news_db,
                "latest_published_report",
                return_value=report,
            ), patch.object(
                blogroll.news_db,
                "report_references",
                return_value=[],
            ):
                context = blogroll.latest_supplement_context(
                    dt.date(2026, 7, 23)
                )

        self.assertEqual(context["title"], "Relative Report")

    def test_dated_archive_omits_promotion_while_index_includes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            supplement = {
                "title": "Signals from New Eden",
                "summary": "Bloggers compare the week's changes.",
                "topic": "MMORPGs",
                "date": dt.date.today().isoformat(),
                "url": "/deep-dives/signals.html",
                "is_new": True,
            }
            items = [{
                "source": "Example Blog",
                "url": "https://example.test/post",
                "one_liner": "Example publishes a new post.",
                "category": "General",
            }]

            with patch.object(blogroll, "BLOGROLLS_DIR", output), patch.object(
                blogroll, "latest_supplement_context", return_value=supplement
            ):
                archive_path, _ = blogroll.render_html("Daily Blogroll", items)

            archive = archive_path.read_text(encoding="utf-8")
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("latest-deep-dive", archive)
            self.assertIn('id="latest-deep-dive"', index)
            self.assertIn("Signals from New Eden", index)
            self.assertIn("deep-dive-new", index)

    def test_existing_index_promotion_can_refresh_without_a_new_blogroll(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "index.html").write_text(
                '<html><body><div class="newspaper-container"></div></body></html>',
                encoding="utf-8",
            )
            supplement = {
                "title": "Fresh Deep Dive",
                "summary": "A new supplement.",
                "topic": "Blogging",
                "date": "2026-07-23",
                "url": "/deep-dives/fresh.html",
                "is_new": True,
            }

            with patch.object(blogroll, "BLOGROLLS_DIR", output), patch.object(
                blogroll, "latest_supplement_context", return_value=supplement
            ):
                blogroll.refresh_index_supplement()

            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="latest-deep-dive"', index)
            self.assertIn("Fresh Deep Dive", index)


if __name__ == "__main__":
    unittest.main()
