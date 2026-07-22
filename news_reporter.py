"""Generate and validate attributed focused-news Markdown."""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path

from openai import OpenAI

from backoff import run_with_429_backoff


SOURCE_LINK_RE = re.compile(r"\[([^\]]+)\]\(source:(P\d+)\)")


LOGGER = logging.getLogger("focused_news.reporter")


REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "markdown": {"type": "string"},
        "used_source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "markdown", "used_source_ids"],
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
                "Write a cohesive Markdown news feature, not a list of summaries. Find the strongest "
                "narrative threads across the supplied articles, compare viewpoints, and give enough "
                "context to make readers want to visit the originals without making them redundant. "
                "Attribute every source-derived claim. Each reference must name both the configured "
                "blogger and blog using exactly this link form: [BLOGGER on BLOG](source:SOURCE_ID). "
                "Do not invent facts, consensus, quotations, names, or links. Avoid long quotations. "
                "A candidate need not be used, but used_source_ids must list exactly every source link "
                "present in the Markdown. Include a final 'Posts discussed' section containing the same "
                "attributed source links and the supplied article titles."
            ),
            input=f"TOPIC: {topic_name}\n\nCANDIDATE ARTICLES:\n{packet}",
            text={
                "format": {
                    "type": "json_schema",
                    "name": "FocusedNewsReport",
                    "schema": REPORT_SCHEMA,
                    "strict": True,
                }
            },
            metadata={"prompt_cache_key": "focused-news-report-v1"},
        ),
        logger=LOGGER,
        description=f"generating focused-news report for {topic_name}",
    )
    return json.loads(response.output_text)


def validate_and_render(result: dict, posts) -> tuple[str, list[int]]:
    """Validate source attribution and replace source URLs with real URLs."""
    _, sources = build_source_packet(posts)
    markdown = result["markdown"]
    links = SOURCE_LINK_RE.findall(markdown)
    linked_ids = {sid for _, sid in links}
    declared_list = list(result["used_source_ids"])
    if len(declared_list) != len(set(declared_list)):
        raise ValueError(f"Declared sources contain duplicates: {declared_list}")
    declared_ids = set(declared_list)
    if linked_ids != declared_ids:
        raise ValueError(
            f"Source links {sorted(linked_ids)} do not match declared sources {sorted(declared_ids)}"
        )
    if not linked_ids:
        raise ValueError("Report contains no attributed sources")
    unknown = linked_ids - sources.keys()
    if unknown:
        raise ValueError(f"Report referenced unknown sources: {sorted(unknown)}")

    seen_labels: dict[str, set[str]] = {sid: set() for sid in linked_ids}
    for label, sid in links:
        seen_labels[sid].add(label)
    for sid in linked_ids:
        post = sources[sid]
        expected = f"{post['blogger']} on {post['blog_name']}"
        if seen_labels[sid] != {expected}:
            raise ValueError(
                f"Attribution for {sid} must be exactly {expected!r}; got {sorted(seen_labels[sid])}"
            )

    def replace(match: re.Match) -> str:
        label, sid = match.groups()
        safe_label = html.escape(label)
        safe_url = html.escape(str(sources[sid]["url"]), quote=True)
        return (
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
            f"{safe_label}</a>"
        )

    rendered = SOURCE_LINK_RE.sub(replace, markdown).strip() + "\n"
    used_post_ids = [sources[sid]["id"] for sid in sorted(linked_ids)]
    return rendered, used_post_ids
