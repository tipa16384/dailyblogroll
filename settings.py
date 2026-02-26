from pathlib import Path

# Site configuration
SITE_HOST = "westkarana.xyz"
AUTHOR_EMAIL = "brendahol@gmail.com"

# File paths and directories
ROOT = Path(__file__).parent
STATE_PATH = ROOT / "data" / "state.json"
BLOGROLLS_DIR = ROOT / "docs"
DB_PATH = "blogroll.db"
CFG_PATH = "feeds.yaml"
BLOG_TEMPLATE = "newspapertemplate.html"

# OpenAI system prompt
SYSTEM = """You are compiling a 'Daily Blogroll'—a terse, link-heavy roundup.
Style: one sentence per item (max ~25 words), credit the blog by name, add a quick take in a casual, conversational but concise manner.
Do not invent facts or quotes; stay within provided excerpts. You are given a suggested category per blog, but can override it if you feel another fits better, as the
author might have changed focus. Categories are: Gaming, Tech, Writing, General. Do not mention the source, title, url or category in the one-liner. You may
refer to the author by name if given. If the post mentions a certain game, technology, or other subject, make sure to mention that in the one-liner.
If the post covers many different games, books, characters or other subjects, have the one-liner refer to the gist rather than one specific item.
Return JSON with an array 'items': [{source, title, url, one_liner, category}].
"""

# JSON schema for OpenAI response
SCHEMA = {
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": {"type": "string"},
          "title":  {"type": "string"},
          "one_liner": {"type": "string", "maxLength": 200},
          "category": {"type": "string"}
        },
        "required": ["source", "one_liner", "title", "category"],
        "additionalProperties": False
      }
    }
  },
  "required": ["items"],
  "additionalProperties": False
}