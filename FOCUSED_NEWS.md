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

Topic definitions are deliberately editable in `news_topics.yaml`. Article
text expires relative to its publication date (or discovery date when no
publication date is available). Metadata remains for deduplication and report
history after the cached text is removed.

## Command-line reference

All options are optional. Run `python focused_news.py --help` for the compact
CLI summary.

### `--database PATH`

Selects the SQLite database file. The default is `blogroll.db`, allowing
Focused News and Daily Blogroll to share one database file while using separate
tables. Focused News creates and accesses only tables beginning with `news_`.

Example:

```sh
python focused_news.py --database test-news.db
```

Using a separate database is useful for experimentation. Changing databases
also changes feed polling history, cached articles, classifications, and report
history because SQLite is the application's sole source of truth.

### `--feeds PATH`

Selects the YAML feed configuration. The default is `feeds.yaml`, shared with
Daily Blogroll. Focused News uses each enabled feed's URL, blog name, blogger
name, and `skip` setting. It does not use Daily Blogroll's required-feed or
per-feed selection rules.

```sh
python focused_news.py --feeds feeds-experimental.yaml
```

### `--topics PATH`

Selects the controlled topic configuration. The default is
`news_topics.yaml`. Each topic has an ID, display name, and description sent to
GPT during classification. GPT may assign zero, one, or several configured
topics to a post, but cannot invent topic IDs outside this file.

Removing a topic does not delete its historical classifications. Such a topic
is ignored when choosing a new report. Renaming a topic's display name is safe;
changing its ID makes it a different topic.

### `--output-dir PATH`

Selects the destination for generated Markdown reports. The default is
`news_reports`. The directory is created when needed. No file is written when
no topic reaches the threshold or when report validation fails.

```sh
python focused_news.py --output-dir draft-reports
```

### `--retention-days NUMBER`

Controls how long full article text remains eligible, measured from the post's
publication time. The default is 7 days. If no usable publication time exists,
the discovery time is used. After expiry, full text is removed while metadata
is retained for deduplication and history.

This value should normally be at least as large as `--backlog-days`. For a
fourteen-day experiment, use both options together:

```sh
python focused_news.py --backlog-days 14 --retention-days 14
```

Increasing retention on a later run does not extend posts already stored with
an earlier expiry date.

### `--backlog-days NUMBER`

Explicitly asks the collector to consider feed entries published within the
preceding number of days. It has no default. Without it, the first run records
feed polling state without silently mining older entries; later runs collect
newly published entries.

This option depends on how much history each RSS or Atom feed exposes. A
fourteen-day request cannot recover posts from a feed that publishes only its
five most recent entries.

Backlog seeding does not force a report. Posts are still classified normally,
and nothing is generated unless one topic reaches `--threshold`.

### `--threshold NUMBER`

Sets the minimum number of unused, unexpired posts that must match one topic
before it becomes eligible for a report. The default is 12. Only topic matches
with relevance of at least 0.6 count.

```sh
python focused_news.py --threshold 6
```

If several topics qualify, the application chooses the one least recently
reported. A topic never previously reported takes precedence over one with
report history. If no topic qualifies, no fallback or general report is
generated and no posts are marked used.

### `--candidate-limit NUMBER`

Limits how many matching full articles are sent to GPT when writing a report.
The default is 15. Candidates are ordered by topic relevance and then recency.

This is distinct from the threshold. With a threshold of 6 and a candidate
limit of 15, six matches make the topic eligible, but GPT may receive as many
as fifteen available matches so it can find the strongest narrative and omit
weak or redundant candidates. To cap the report input at six posts, set both
values to 6.

Only candidates actually referenced and linked in the validated report are
marked used. Omitted candidates remain available until used later or expired.

### `--batch-size NUMBER`

Controls how many unclassified posts are included in each GPT classification
request. The default is 12. It affects the number and size of classification
API calls, not report eligibility.

For example, 30 unclassified posts with `--batch-size 10` produce three
classification calls. Whether a report is written still depends on how many of
those posts match the same topic and reach `--threshold`.

Smaller batches mean more API calls with smaller prompts. Larger batches mean
fewer calls with larger prompts and structured responses. Leave the default
unchanged unless classification requests become too large or unreliable.

### `--model MODEL`

Selects the OpenAI model used for both classification and report generation.
The default is `gpt-5`. The configured model must support the Responses API and
the structured JSON schemas used by the application.

Changing models can affect classification consistency, narrative quality,
context capacity, latency, and API cost. Previously stored classifications are
not automatically recalculated after a model change.

### `--verbose`

Enables detailed console logging. It takes no value:

```sh
python focused_news.py --verbose
```

Verbose mode reports feed checks, disabled feeds, cache hits, stored and
too-short articles, GPT classification batches, expired-text and collection
totals, topic inventory against the threshold, the selected topic, candidate
and referenced counts, and the Markdown output path. Article text and complete
GPT prompts are not logged. Fetch and parsing warnings remain visible without
verbose mode.

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
