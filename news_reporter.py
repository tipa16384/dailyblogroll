"""Generate and validate attributed focused-news supplement content."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from backoff import run_with_429_backoff


SOURCE_TOKEN_RE = re.compile(r"\[\[(P\d+)\]\]")


LOGGER = logging.getLogger("focused_news.reporter")


REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "body": {
            "type": "array",
            "items": {"type": "string"},
        },
        "used_source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "body", "used_source_ids"],
    "additionalProperties": False,
}


def source_id(post_id: int) -> str:
    return f"P{post_id}"


def build_source_packet(posts) -> tuple[str, dict[str, object]]:
    sources = {source_id(p["id"]): p for p in posts}
    packet = []
    for sid, post in sources.items():
        packet.append(
            f"SOURCE {sid}\nBLOGGER: {post['blogger']}\nBLOG: {post['blog_name']}\n"
            f"TITLE: {post['title']}\nPUBLISHED: {post['published_at'] or 'unknown'}\n"
            f"ARTICLE:\n{post['full_text']}"
        )
    return "\n\n---\n\n".join(packet), sources


def generate_report(topic_name: str, posts, *, client=None, model: str = "gpt-5") -> dict:
    client = client or OpenAI()
    packet, _ = build_source_packet(posts)
    response = run_with_429_backoff(
        lambda: client.responses.create(
            model=model,
            instructions=(
                "You are the pleasant, clear newscaster for a community of independent blogs. "
                "Write a cohesive news feature, not a list of summaries. Find the strongest "
                "narrative threads across the supplied articles, compare viewpoints, and give "
                "enough context to make readers want to visit the originals without making them "
                "redundant. Return a title, a summary of no more than 100 words, and the article "
                "body as an ordered array of ordinary prose paragraphs. Do not add section "
                "headings, a references section, Markdown, or HTML. Attribute every source-derived "
                "claim. Wherever an attribution belongs, emit only the source marker in this exact "
                "form: [[SOURCE_ID]]. The application will expand it to the configured blogger and "
                "blog name. Do not spell out or alter the attribution yourself. Do not invent facts, "
                "consensus, quotations, names, or links. Avoid long quotations. A candidate need not "
                "be used, but used_source_ids must list exactly every distinct source marker present "
                "in the summary and body."
            ),
            input=f"TOPIC: {topic_name}\n\nCANDIDATE ARTICLES:\n{packet}",
            text={
                "format": {
                    "type": "json_schema",
                    "name": "FocusedNewsSupplement",
                    "schema": REPORT_SCHEMA,
                    "strict": True,
                }
            },
            metadata={"prompt_cache_key": "focused-news-supplement-v1"},
        ),
        logger=LOGGER,
        description=f"generating focused-news supplement for {topic_name}",
    )
    return json.loads(response.output_text)


def validate_report(result: dict, posts) -> tuple[dict, list[int]]:
    """Validate source markers and return normalized, structured supplement data."""
    _, sources = build_source_packet(posts)
    title = result["title"].strip()
    summary = result["summary"].strip()
    body = [paragraph.strip() for paragraph in result["body"] if paragraph.strip()]
    if not title or not summary or not body:
        raise ValueError("Report must contain a title, summary, and at least one body paragraph")

    text = "\n".join([summary, *body])
    linked_ids = set(SOURCE_TOKEN_RE.findall(text))
    declared_list = list(result["used_source_ids"])
    if len(declared_list) != len(set(declared_list)):
        raise ValueError(f"Declared sources contain duplicates: {declared_list}")
    declared_ids = set(declared_list)
    if linked_ids != declared_ids:
        raise ValueError(
            f"Source markers {sorted(linked_ids)} do not match declared sources "
            f"{sorted(declared_ids)}"
        )
    if not linked_ids:
        raise ValueError("Report contains no attributed sources")
    unknown = linked_ids - sources.keys()
    if unknown:
        raise ValueError(f"Report referenced unknown sources: {sorted(unknown)}")

    normalized = {
        "title": title,
        "summary": summary,
        "body": body,
        "used_source_ids": declared_list,
    }
    used_post_ids = [int(sources[sid]["id"]) for sid in declared_list]
    return normalized, used_post_ids


def references_for_report(result: dict, posts) -> list[dict]:
    """Build trusted reference data in the model-declared order."""
    _, sources = build_source_packet(posts)
    return [
        {
            "source_id": sid,
            "post_id": int(sources[sid]["id"]),
            "blogger": sources[sid]["blogger"],
            "blog_name": sources[sid]["blog_name"],
            "title": sources[sid]["title"],
            "url": sources[sid]["url"],
            "published_at": sources[sid]["published_at"],
        }
        for sid in result["used_source_ids"]
    ]


def segment_text(text: str, references: list[dict]) -> list[dict]:
    """Split model prose into escaped text and trusted attribution segments."""
    reference_map = {reference["source_id"]: reference for reference in references}
    segments = []
    position = 0
    for match in SOURCE_TOKEN_RE.finditer(text):
        if match.start() > position:
            segments.append({"text": text[position:match.start()]})
        segments.append({"reference": reference_map[match.group(1)]})
        position = match.end()
    if position < len(text):
        segments.append({"text": text[position:]})
    return segments


def expand_source_names(text: str, references: list[dict]) -> str:
    """Expand source markers to attribution text for non-link contexts."""
    reference_map = {reference["source_id"]: reference for reference in references}

    def replace(match: re.Match) -> str:
        reference = reference_map[match.group(1)]
        return f"{reference['blogger']} on {reference['blog_name']}"

    return SOURCE_TOKEN_RE.sub(replace, text)
