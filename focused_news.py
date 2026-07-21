"""Command-line entry point for focused blog-community news reports."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
from pathlib import Path

import news_classifier
import news_collector
import news_db
import news_reporter


LOGGER = logging.getLogger("focused_news")


def configure_logging(verbose: bool) -> None:
    """Configure focused-news console logging without changing other loggers."""
    LOGGER.setLevel(logging.DEBUG if verbose else logging.WARNING)
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        LOGGER.addHandler(handler)
    for handler in LOGGER.handlers:
        handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    LOGGER.propagate = False

def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def generate_if_ready(
    *,
    db_path: str | Path,
    topics_path: str | Path,
    output_dir: str | Path,
    threshold: int = 12,
    candidate_limit: int = 15,
    client=None,
    model: str = "gpt-5",
) -> Path | None:
    eligible = news_db.eligible_topics(threshold, db_path=db_path)
    if not eligible:
        LOGGER.debug("No topic has reached the %d-post threshold.", threshold)
        return None
    topic_map = {t["id"]: t for t in news_classifier.load_topics(topics_path)}
    selected = next(
        ((row["topic_id"], topic_map[row["topic_id"]])
         for row in eligible if row["topic_id"] in topic_map),
        None,
    )
    if selected is None:
        LOGGER.warning("Eligible database topics are absent from %s; no report generated.", topics_path)
        return None
    topic_id, topic = selected
    posts = news_db.candidate_posts(topic_id, candidate_limit, db_path=db_path)
    LOGGER.debug(
        "Selected %s (%s) with %d candidate posts.", topic["name"], topic_id, len(posts)
    )
    result = news_reporter.generate_report(topic["name"], posts, client=client, model=model)
    markdown, used_ids = news_reporter.validate_and_render(result, posts)
    LOGGER.debug(
        "Validated report using %d posts; %d candidates omitted.",
        len(used_ids),
        len(posts) - len(used_ids),
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().isoformat()
    path = output_dir / f"{date}-{slugify(result['title'])}.md"
    # Write first; consume posts only after a valid report is safely present.
    path.write_text(f"# {result['title']}\n\n{markdown}", encoding="utf-8")
    news_db.save_report(
        topic_id,
        result["title"],
        markdown,
        used_ids,
        str(path),
        db_path=db_path,
    )
    LOGGER.debug("Wrote focused report to %s.", path)
    return path


def run(args) -> Path | None:
    news_db.initialize(args.database)
    expired = news_db.expire_text(db_path=args.database)
    LOGGER.debug("Expired cached article text for %d posts.", expired)
    collection = news_collector.collect(
        feeds_path=args.feeds,
        db_path=args.database,
        retention_days=args.retention_days,
        backlog_days=args.backlog_days,
    )
    LOGGER.debug(
        "Collection complete: %d feeds, %d eligible entries, %d new posts, %d errors.",
        collection["feeds"], collection["entries"], collection["stored"],
        len(collection["errors"]),
    )
    classified = news_classifier.classify_pending(
        db_path=args.database,
        topics_path=args.topics,
        batch_size=args.batch_size,
        model=args.model,
    )
    LOGGER.debug("Classified %d new posts.", classified)

    topics = news_classifier.load_topics(args.topics)
    inventory = {
        row["topic_id"]: row["available_count"]
        for row in news_db.topic_inventory(db_path=args.database)
    }
    LOGGER.debug("Topic inventory (threshold %d):", args.threshold)
    for topic in topics:
        LOGGER.debug("  %-24s %d / %d", topic["name"], inventory.get(topic["id"], 0), args.threshold)
    return generate_if_ready(
        db_path=args.database,
        topics_path=args.topics,
        output_dir=args.output_dir,
        threshold=args.threshold,
        candidate_limit=args.candidate_limit,
        model=args.model,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--database", default="blogroll.db")
    result.add_argument("--feeds", default="feeds.yaml")
    result.add_argument("--topics", default="news_topics.yaml")
    result.add_argument("--output-dir", default="news_reports")
    result.add_argument("--retention-days", type=int, default=7)
    result.add_argument("--backlog-days", type=int, help="Explicitly seed this many days of feed history")
    result.add_argument("--threshold", type=int, default=12)
    result.add_argument("--candidate-limit", type=int, default=15)
    result.add_argument("--batch-size", type=int, default=12)
    result.add_argument("--model", default="gpt-5")
    result.add_argument("--verbose", action="store_true", help="Show collection, classification, and topic progress")
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    configure_logging(args.verbose)
    output = run(args)
    print(output if output else "No topic is ready for a focused report.")
