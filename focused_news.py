"""Command-line entry point for focused blog-community news reports."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import news_classifier
import news_collector
import news_db
import news_reporter


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
        return None
    topic_id = eligible[0]["topic_id"]
    topic_map = {t["id"]: t for t in news_classifier.load_topics(topics_path)}
    topic = topic_map[topic_id]
    posts = news_db.candidate_posts(topic_id, candidate_limit, db_path=db_path)
    result = news_reporter.generate_report(topic["name"], posts, client=client, model=model)
    markdown, used_ids = news_reporter.validate_and_render(result, posts)

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
    return path


def run(args) -> Path | None:
    news_db.initialize(args.database)
    news_db.expire_text(db_path=args.database)
    news_collector.collect(
        feeds_path=args.feeds,
        db_path=args.database,
        retention_days=args.retention_days,
        backlog_days=args.backlog_days,
    )
    news_classifier.classify_pending(
        db_path=args.database,
        topics_path=args.topics,
        batch_size=args.batch_size,
        model=args.model,
    )
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
    return result


if __name__ == "__main__":
    output = run(parser().parse_args())
    print(output if output else "No topic is ready for a focused report.")

