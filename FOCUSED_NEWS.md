# Focused News

`focused_news.py` is an experimental companion to Daily Blogroll. It does not
import or alter `blogroll.py`, `db.py`, their state file, or their existing
SQLite tables. It reuses `feeds.yaml` and stores everything it owns in tables
whose names begin with `news_` in the same `blogroll.db` file.

The application:

1. polls the configured feeds and temporarily caches cleaned article text;
2. assigns zero or more configured topics to each new post;
3. waits until a topic has at least twelve unused, unexpired matches;
4. chooses the eligible topic that was reported least recently;
5. asks GPT to write a cohesive, newscaster-style Markdown feature; and
6. consumes only posts that the validated report actually attributes and links.

## Running it

Set `OPENAI_API_KEY`, install `requirements.txt`, and run:

```sh
python focused_news.py
```

The first ordinary run establishes feed polling state in SQLite without mining
old entries. To intentionally seed the initial pool with up to seven days of
feed history, run:

```sh
python focused_news.py --backlog-days 7
```

Use verbose mode while evaluating collection and topic accumulation:

```sh
python focused_news.py --backlog-days 7 --verbose
```

Verbose output includes per-feed cache decisions, GPT batch progress, expired
text counts, topic inventory against the report threshold, report selection,
source usage, and the output path. Fetch and parsing errors are logged even
without verbose mode.

Reports are written to `news_reports/` by default. Relevant options include:

```text
--database blogroll.db
--feeds feeds.yaml
--topics news_topics.yaml
--output-dir news_reports
--retention-days 7
--threshold 12
--candidate-limit 15
--batch-size 12
--model gpt-5
--verbose
```

Topic definitions are deliberately editable in `news_topics.yaml`. Article
text expires relative to its publication date (or discovery date when no
publication date is available). Metadata remains for deduplication and report
history after the cached text is removed.

## Attribution safety

GPT references candidates with internal links such as:

```markdown
[Belghast on Tales of the Aggronaut](source:P42)
```

Before writing a report to the database, the application verifies that every
source ID exists, its label exactly matches the configured blogger and blog,
and the declared source list matches the links in the article. It then replaces
the internal target with the original post URL. A failed validation consumes no
posts and does not update topic history.

## Tests

Tests use the standard-library `unittest` runner and mock feed fetching and GPT
responses. They do not make paid API calls:

```sh
python -m unittest discover -s tests -v
```
