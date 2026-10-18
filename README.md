# apple-news-24h

**English** | [简体中文](README.zh-CN.md)

A Codex skill and standalone Python crawler for generating a recent 24-hour Apple software and hardware news brief.

The crawler discovers candidates from selected English and Chinese technology sources, verifies article detail-page timestamps where available, normalizes timezones through UTC, and groups coverage by the reported action. It produces structured evidence and coverage scaffolds; the skill uses these results to write the final Chinese brief under `软件与系统` and `硬件与产品`.

## Status

This project is experimental. News sites change markup, feeds can fail, and inclusion rules need ongoing maintenance. Treat the output as a structured brief draft that still benefits from editorial review.

## Latest Update

### 2.1.3 - 2026-10-18

- Improved preorder grouping for internal walk-in instructions and attributed stock forecasts while keeping Apple's demand statements, delivery observations, production reports and resale measurements tied to their own actions.
- Unified weekly device-sales identity in one source-bound implementation; normalized device names, quantities and week notation while preserving region, reporting period, cumulative versus weekly scope, forecast stage and separate reports.
- Improved carrier pricing ownership for provider-specific currencies, monthly charges and plan-based free access without borrowing another carrier's background price.
- Improved first-party accessory construction and local operating-condition coverage in mixed articles; kept third-party app adaptations, accessory-tool withdrawals and personal deployment tutorials from becoming Apple announcements.
- Improved company-event classification for current executive appearances and legal appointments, preventing biographical leadership changes or litigation background from overriding the reported action.
- Updated the reporting policy and added 17 regression tests; the full offline suite passes 2,715 tests with existing assertions preserved.
- Kept the standard-library runtime, CLI, JSON schema, nine primary sources, collection budgets, relevance tiers, two brief sections and explicit-only skill invocation.

## What It Does

- Collects recent Apple-related software, systems, services, hardware, accessories, health, research, legal, and company-action news.
- Uses RSS/Atom first, then source pages and fallback discovery where configured.
- Opens article detail pages to verify precise publication times whenever possible.
- Converts article times to UTC for the 24-hour window comparison.
- Deduplicates multiple reports into event-level items.
- Labels event kind and relevance tier so broad discovery can preserve weak Apple-adjacent candidates without polluting the final brief.
- Extracts key numeric facts, lists, feature names, countries, terms, eligibility details, rollout limits, and source-linked nonnumeric mechanisms or conditions for richer summaries.
- Emits Markdown or JSON.

## Architecture

The crawler separates collection, source evidence, event decisions, and output assembly. A source can support several independent actions; each projected claim keeps its local evidence, while unresolved material remains available for review.

- `skills/scripts/apple_news_24h.py` is the CLI and pipeline coordinator. It prepares source facts and assembles JSON and Markdown from the reconciled event and fact plans.
- `skills/scripts/apple_news_core/collection.py` owns source definitions, URL normalization, HTTP/cache utilities, resource locks and concurrent discovery/detail scheduling; `article_processing.py` handles article text cleanup, timestamp parsing and captured evidence preparation. The CLI supplies fetch functions, budgets and the runtime clock.
- `models.py` defines shared data. `event_identity.py` binds concrete subjects and actions to their source evidence, and `article_projector.py` separates supported claims while retaining unassigned source material.
- `event_matcher.py` provides the common pair decision. `event_reconciler.py` forms groups and resolves relevance, category, and source-attributed fact plans. Output assembly consumes those decisions instead of running a second grouping or relevance engine.
- `tests/` covers discovery, time parsing, cache handling, event boundaries, fact attribution, and output. Fixed-input replay checks and live collection validation serve different purposes; saved pages do not prove current discovery or network health.

## What It Does Not Do

- It is not an Apple official project.
- It does not provide investment, legal, medical, or product-purchase advice.
- It does not guarantee complete coverage when sources block requests, feeds are delayed, or pages change structure.
- It should not be used to republish full articles or cached source pages.

## Installation As A Codex Skill

Clone the repository and link its `skills` directory into your Codex skills directory:

```bash
git clone https://github.com/yuehunai/apple-news-24h apple-news-24h
mkdir -p "$CODEX_HOME/skills"
ln -s "$PWD/apple-news-24h/skills" "$CODEX_HOME/skills/apple-news-24h"
```

If `CODEX_HOME` is not set, Codex commonly uses `~/.codex`:

```bash
git clone https://github.com/yuehunai/apple-news-24h apple-news-24h
mkdir -p ~/.codex/skills
ln -s "$PWD/apple-news-24h/skills" ~/.codex/skills/apple-news-24h
```

You can also give this repository URL to Codex and ask it to install the skill automatically:

```text
https://github.com/yuehunai/apple-news-24h
```

Then invoke it explicitly, or call it directly from an automation:

```text
$apple-news-24h
```

The skill intentionally disables implicit invocation in `skills/agents/openai.yaml`, so ordinary Apple or technology conversations should not trigger it automatically.

## CLI Usage

Run the crawler on macOS or Linux with Python 3.9 or later. It uses only the standard library; resource locking requires POSIX `fcntl`, so native Windows is not currently supported. The CLI produces structured material for the brief; it does not invoke a language model to write the finished Chinese paragraphs.

Markdown output:

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format markdown
```

JSON output:

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

JSON keeps included brief items in `events`. Weak Apple-adjacent candidates, such as third-party app stories or competitor comparisons that do not describe a direct Apple action, may be kept in `deferred_events` for review. Event objects can include `event_kind`, `relevance_tier`, `relevance_reason`, `regions`, and `merge_warnings`.

If a source listing stops before its window coverage is confirmed, `collection_warnings` appears in JSON and the file-output status even without `--include-diagnostics`. A healthy event count does not resolve that source gap; follow the documented source fallback and retain any unresolved limitation in review notes.

JSON also exposes evidence for attribution and coverage review:

| Field | Purpose |
| --- | --- |
| `source_evidence` | Captured source units and publication evidence, linked by `evidence_id`; retained even when an unresolved source produces no event. |
| `fact_sources[].origins` | Source support and, when available, exact unit spans for each event fact. |
| `evidence_dispositions` | Recorded destinations of projected or unresolved source material. |
| `final_brief_queue` | Event candidates and unresolved fragments requiring a decision. `capture_status: discovery-only` flags a source for which full text was unavailable; it does not promote the item. |

Required flags ask for a decision, not automatic inclusion. `required_final_brief_titles`, `final_brief_markdown`, and an adjacent `*.brief.md` are coverage scaffolds, not the finished brief. Write from source-supported summaries and facts, checking independent actions, material qualifications and each bullet's supporting URLs.

For source-bound reports, binding and news eligibility are separate decisions. App-publisher charts, device benchmarks, operating-feature inventories, media invitations and current company-responsibility interviews preserve unresolved ownership for evidence review instead of assigning a weak tier. A qualified invitation with an unresolved event date remains an event with a specific `merge_warnings` reason; it cannot authorize a same-event merge. Other report families retain their existing processing rules. Grouping uses the source-owned action and its identity qualifiers; generated titles and measurement values alone do not establish a shared event.

Version 2.1.1 keeps the CLI, JSON fields and relevance tiers from 2.1.0. Consumers should tolerate additional fields; corrected grouping can change event membership, IDs and classifications.

Diagnostics for debugging source failures:

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json --include-diagnostics
```

Useful options:

- `--hours 24`: lookback window.
- `--timezone auto`: detect system timezone; pass an IANA timezone such as `America/Los_Angeles` to force one.
- `--format markdown|json`: choose crawler output format.
- `--cache-dir PATH`: save successful HTTP responses for current-run inspection.
- `--output PATH`: atomically write full output to a file and print only a compact status JSON.
- `--include-diagnostics`: include failed fetches, source failures, selected-detail fetch failures, discovery fallback counts, and low-confidence timestamp notes.

By default, the cache directory is `apple-news-24h` under Python's platform temporary directory. The crawler clears that directory at startup and writes a marker file plus current-run responses. Old cache files must not be used as a freshness fallback.

Runs that share a cache or output resource fail on a lock conflict. Use distinct `--cache-dir` and `--output` paths for independent runs; keep saved evidence outside the managed cache.

## Network Permission

The crawler needs live network access to fetch feeds, channel pages, and article pages. In sandboxed agent environments, the first run may fail with DNS or network-permission errors. If the result is empty or suspiciously sparse, the skill reruns the same command with the required network approval, then inspects diagnostics or follows the documented fallback if needed.

Network permission does not prevent a site from returning an access block or browser challenge. The standard-library HTTP client does not execute challenge-page JavaScript; some sources may therefore have only discovery excerpts. Review their capture markers before treating the available text as a complete article.

## Sources

Primary sources include MacRumors, 9to5Mac, AppleInsider, The Verge, Apple Newsroom, IT之家, 爱范儿, 快科技, and cnBeta. Supplemental fallback sources include 新浪科技/财经, 网易科技, 36氪, and other mainstream Chinese technology pages when needed.

See `skills/references/news_policy.md` for source URLs, default timezones, inclusion rules, exclusion rules, event merge rules, and fallback handling.

## Tests

Run the offline test suite:

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m compileall -q skills/scripts
```

The writable bytecode-cache directory avoids repeated compilation in environments where the default cache is not writable. For fixed-input replay and same-window live comparisons, see [tests/REPLAY.md](tests/REPLAY.md). Replay cannot establish current source availability; live checks remain separate from CI because they depend on network access and third-party sites.

## Legal And Attribution

This project is not affiliated with, endorsed by, or sponsored by Apple Inc. Apple, iPhone, iPad, Mac, Apple Watch, AirPods, Vision Pro, and other Apple product names are trademarks of Apple Inc.

The crawler fetches publicly available feeds and pages. Users are responsible for complying with source websites' terms, robots policies, rate limits, copyright rules, and applicable laws. Do not publish cached source pages or long verbatim excerpts from articles.

## License

MIT. See `LICENSE`.
