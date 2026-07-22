"""GPT-backed multi-label classification of collected posts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from openai import OpenAI

from backoff import run_with_429_backoff
import news_db


LOGGER = logging.getLogger("focused_news.classifier")

def load_topics(path: str | Path = "news_topics.yaml") -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["topics"]


def classification_schema(topic_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "posts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "post_id": {"type": "integer"},
                        "topics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "topic_id": {"type": "string", "enum": topic_ids},
                                    "relevance": {"type": "number", "minimum": 0, "maximum": 1},
                                    "rationale": {"type": "string"},
                                },
                                "required": ["topic_id", "relevance", "rationale"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["post_id", "topics"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["posts"],
        "additionalProperties": False,
    }


def classify_batch(posts, topics: list[dict], client=None, model: str = "gpt-5") -> dict:
    client = client or OpenAI()
    topic_text = "\n".join(
        f"- {t['id']}: {t['name']} — {t['description']}" for t in topics
    )
    post_text = "\n\n".join(
        f"POST {p['id']}\nTITLE: {p['title']}\nBLOGGER: {p['blogger']}\n"
        f"BLOG: {p['blog_name']}\nTEXT:\n{p['full_text'][:4000]}"
        for p in posts
    )
    response = run_with_429_backoff(
        lambda: client.responses.create(
            model=model,
            instructions=(
                "Classify blog posts for a future thematic news report. Apply zero or more "
                "topics to each post. Prefer precision: a passing mention is not a match. "
                "Use multiple topics only when each is substantively important."
            ),
            input=f"TOPICS:\n{topic_text}\n\nPOSTS:\n{post_text}",
            text={
                "format": {
                    "type": "json_schema",
                    "name": "FocusedNewsClassifications",
                    "schema": classification_schema([t["id"] for t in topics]),
                    "strict": True,
                }
            },
            metadata={"prompt_cache_key": "focused-news-classification-v1"},
        ),
        logger=LOGGER,
        description="classifying focused-news posts",
    )
    return json.loads(response.output_text)


def classify_pending(
    *,
    db_path: str | Path = "blogroll.db",
    topics_path: str | Path = "news_topics.yaml",
    batch_size: int = 12,
    client=None,
    model: str = "gpt-5",
) -> int:
    topics = load_topics(topics_path)
    total = 0
    while True:
        posts = news_db.unclassified_posts(batch_size, db_path)
        if not posts:
            return total
        LOGGER.debug("Classifying a GPT batch of %d posts.", len(posts))
        result = classify_batch(posts, topics, client=client, model=model)
        expected = {p["id"] for p in posts}
        returned = {item["post_id"] for item in result["posts"]}
        if returned != expected:
            raise ValueError(f"Classification IDs did not match input: expected {expected}, got {returned}")
        for item in result["posts"]:
            news_db.save_classifications(item["post_id"], item["topics"], db_path=db_path)
            LOGGER.debug(
                "Post %s classified into %d topics.", item["post_id"], len(item["topics"])
            )
            total += 1
