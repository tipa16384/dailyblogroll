# Focused News

`focused_news.py` generates occasional Deep Dive supplements for Daily
Blogroll. It remains a separate command, reuses `feeds.yaml`, and stores
everything it owns in tables whose names begin with `news_` in the shared
`blogroll.db` file. `blogroll.py` reads completed supplement metadata only when
building the current `index.html`.

The application:

1. polls the configured feeds and temporarily caches cleaned article text;
2. assigns zero or more configured topics to each new post;
3. waits until a topic has at least six unused, unexpired matches;
4. chooses the eligible topic that was reported least recently;
5. asks GPT for a title, short deck, and cohesive newscaster-style paragraphs;
6. renders a permanent HTML supplement through Jinja; and
7. consumes only posts that the validated report actually attributes and links.

The focused-news command should run before `blogroll.py`. If it publishes a new
supplement, the current Daily Blogroll index promotes it with a `New` marker.
If it publishes nothing, the index continues to link the most recent
supplement. Dated Daily Blogroll archives never receive this promotion.

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

Selects the destination for generated HTML supplements. The default is
`docs/deep-dives`, beneath the static site root. The directory is created when
needed. No file is written when no topic reaches the threshold or when report
validation fails.

```sh
python focused_news.py --output-dir docs/experimental-deep-dives
```

The output directory must be inside `docs`, because the stored public URL is
derived from its location relative to that site root. Supplements are arranged
by year and month:

```text
docs/deep-dives/2026/07/deep-dive-2026-07-23-signals-from-new-eden.html
```

Each page is rendered with `templates/supplementtemplate.html`, uses the
existing Daily Blogroll stylesheet, and receives title, edition date, topic,
summary, body paragraphs, references, and Deep Dive navigation as Jinja data.
The database retains the structured body so previous/next navigation can be
rebuilt without parsing generated HTML.

### `--retention-days NUMBER`

Controls how long full article text remains eligible, measured from the post's
publication time. The default is 10 days. If no usable publication time exists,
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
before it becomes eligible for a report. The default is 6. Only topic matches
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
and referenced counts, and the HTML output path. Article text and complete GPT
prompts are not logged. Fetch and parsing warnings remain visible without
verbose mode.

## Attribution safety

GPT references candidates with internal markers such as:

```text
[[P42]]
```

Before writing a report to the database, the application verifies that every
source ID exists and that the declared source list exactly matches the markers
in the summary and body. Jinja expands every marker into a link labeled with
the configured blogger and blog. The final reference list is constructed from
the database rather than generated prose. Model text is HTML-escaped. A failed
validation consumes no posts and does not update topic history.

## Publishing and navigation

Completed supplement records store the title, summary, topic name, edition
date, structured body, filesystem path, and public URL. The associated
`news_report_posts` rows preserve the posts used for attribution and the
reference list.

Each focused-news run rebuilds the previous/next links for all HTML supplements
from the database, which also repairs an interrupted earlier update. Legacy
Markdown reports remain in report history but are not placed in the HTML
supplement navigation chain.

When `blogroll.py` runs, its dated archive and mutable index are rendered
separately. Only `index.html` receives the latest supplement data. If there are
no fresh Daily Blogroll posts, `blogroll.py` refreshes the existing index
promotion without creating or modifying a dated archive.

## Tests

Tests use the standard-library `unittest` runner and mock feed fetching and GPT
responses. They do not make paid API calls:

```sh
python -m unittest discover -s tests -v
```
