"""Generate Deep Dive supplements from recent independent-blog posts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import news_classifier
import news_collector
import news_db
import news_reporter
from settings import BLOGROLLS_DIR, ROOT


LOGGER = logging.getLogger("focused_news")
TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


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


def output_url(path: Path) -> str:
    """Return a root-relative site URL for a file beneath the docs directory."""
    try:
        relative = path.resolve().relative_to(BLOGROLLS_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Supplement output must be inside the site directory {BLOGROLLS_DIR}"
        ) from None
    return "/" + relative.as_posix()


def project_path(path: str | Path) -> Path:
    """Resolve project-relative paths independently of the launch directory."""
    result = Path(path)
    return result if result.is_absolute() else ROOT / result


def unique_output_path(output_dir: Path, date: str, title: str) -> Path:
    slug = slugify(title) or "supplement"
    base = output_dir / f"deep-dive-{date}-{slug}.html"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = base.with_name(f"{base.stem}-{counter}{base.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def friendly_date(value: str) -> str:
    day = dt.date.fromisoformat(value)
    return f"{day:%A}, {day.day} {day:%B} {day:%Y}"


def render_supplement(
    report: dict,
    references: list[dict],
    *,
    previous=None,
    next_report=None,
) -> str:
    """Render a supplement from trusted metadata and escaped prose segments."""
    template = TEMPLATE_ENV.get_template("supplementtemplate.html")
    variables = {
        "front_matter": {
            "title": report["title"],
            "date": report["edition_date"],
            "friendly_date": friendly_date(report["edition_date"]),
            "category": report["topic_name"],
        },
        "summary": news_reporter.segment_text(report["summary"], references),
        "body": [
            news_reporter.segment_text(paragraph, references)
            for paragraph in report["body"]
        ],
        "references": references,
    }
    if previous is not None:
        variables["previous"] = {
            "title": previous["title"],
            "url": previous["public_url"],
        }
    if next_report is not None:
        variables["next"] = {
            "title": next_report["title"],
            "url": next_report["public_url"],
        }
    return template.render(vars=variables)


def write_rendered_supplement(path: Path, output: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(output, encoding="utf-8")
    temporary.replace(path)


def render_saved_supplements(*, db_path: str | Path) -> None:
    """Rebuild supplement navigation from the database source of truth."""
    reports = news_db.published_reports(db_path=db_path)
    for index, row in enumerate(reports):
        references = [
            {
                "source_id": news_reporter.source_id(post["id"]),
                "post_id": post["id"],
                "blogger": post["blogger"],
                "blog_name": post["blog_name"],
                "title": post["title"],
                "url": post["url"],
                "published_at": post["published_at"],
            }
            for post in news_db.report_references(row["id"], db_path=db_path)
        ]
        report = {
            "title": row["title"],
            "summary": row["summary"],
            "body": json.loads(row["body_json"]),
            "edition_date": row["edition_date"],
            "topic_name": row["topic_name"],
        }
        output = render_supplement(
            report,
            references,
            previous=reports[index - 1] if index > 0 else None,
            next_report=reports[index + 1] if index + 1 < len(reports) else None,
        )
        write_rendered_supplement(project_path(row["output_path"]), output)


def generate_if_ready(
    *,
    db_path: str | Path,
    topics_path: str | Path,
    output_dir: str | Path,
    threshold: int = 6,
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
    report, used_ids = news_reporter.validate_report(result, posts)
    references = news_reporter.references_for_report(report, posts)
    LOGGER.debug(
        "Validated report using %d posts; %d candidates omitted.",
        len(used_ids),
        len(posts) - len(used_ids),
    )

    output_dir = project_path(output_dir)
    today = dt.date.today()
    dated_dir = output_dir / f"{today:%Y}" / f"{today:%m}"
    date = today.isoformat()
    path = unique_output_path(dated_dir, date, report["title"])
    public_url = output_url(path)
    previous = news_db.latest_published_report(db_path=db_path)
    render_data = {
        **report,
        "edition_date": date,
        "topic_name": topic["name"],
    }
    # Write first; consume posts only after a valid report is safely present.
    write_rendered_supplement(
        path,
        render_supplement(render_data, references, previous=previous),
    )
    try:
        news_db.save_report(
            topic_id,
            report["title"],
            report["body"],
            used_ids,
            str(path),
            summary=report["summary"],
            topic_name=topic["name"],
            edition_date=date,
            public_url=public_url,
            db_path=db_path,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    try:
        render_saved_supplements(db_path=db_path)
    except Exception:
        LOGGER.exception("Could not rebuild Deep Dive navigation")
    LOGGER.debug("Wrote focused report to %s.", path)
    return path


def run(args) -> Path | None:
    news_db.initialize(args.database)
    try:
        render_saved_supplements(db_path=args.database)
    except Exception:
        LOGGER.exception("Could not refresh existing Deep Dive pages")
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
    result.add_argument("--output-dir", default="docs/deep-dives")
    result.add_argument("--retention-days", type=int, default=10, help="Expire posts older than this many days")
    result.add_argument("--backlog-days", type=int, help="Explicitly seed this many days of feed history")
    result.add_argument("--threshold", type=int, default=6, help="Minimum number of posts required to generate a report")
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
