# apple-news-24h

**English** | [简体中文](README.zh-CN.md)

A Codex skill and standalone Python crawler for generating a recent 24-hour Apple software and hardware news brief.

The crawler discovers candidates from selected English and Chinese technology sources, verifies article detail-page timestamps where available, normalizes timezones through UTC, and groups coverage by the reported action. It produces structured evidence and coverage scaffolds; the skill uses these results to write the final Chinese brief under `软件与系统` and `硬件与产品`.

## Status

This project is experimental. News sites change markup, feeds can fail, and inclusion rules need ongoing maintenance. Treat the output as a structured brief draft that still benefits from editorial review.

## Latest Update

### 2.3.1 - 2026-10-26

- Improved detail admission for reported price movements even when a headline also mentions a subsidy, while keeping retail offers distinct from observed market prices.
- Improved source-bound teardown and durability-test grouping across languages and device names, preserving observers, methods and current actions; prevented legacy repair classifications from overriding an established teardown action.
- Improved relevance and sections for built-in capabilities, support documents, focused operating observations and device faults, while keeping unrelated hardware ports and general commentary outside independent Apple news.
- Improved joint prototype identities and roadmap boundaries so concrete actions are not merged through a shared product family; distinguished current disclosures from historical reports, conditional speculation and absent or denied actions.
- Improved supplier-response attribution to the actual speaker, product and current statement, preventing historical order adjustments from taking over the report and keeping an explicit denial distinct from no response.
- Added a standard-library clause recorder for source-linked wording, references, revisions and final assembly; updated the skill to save each source's propositions before merging equivalents, without delegating semantic decisions to the tool.
- Added 34 regression tests and real-source fixtures while preserving existing assertions; all 3,088 offline tests pass, and fresh same-window live comparison showed no collection-time regression.
- Kept the standard-library runtime, CLI, existing JSON fields, nine primary sources, collection budgets and concurrency, relevance tiers, two brief sections and explicit-only skill invocation.

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
- `skills/scripts/brief_records.py` supports the skill's writing stage by saving Chinese clauses and source-unit references, retaining edit history and assembling checked clauses with their supporting links. It does not decide eligibility, grouping, semantic equivalence or factual completeness. Its usage is documented in `skills/references/brief-records.md`.
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
| `events[].claims`, `deferred_events[].claims` | Where present, source-bound subjects, actions, objects, qualifiers and evidence spans; use these before display titles when resolving boundaries. |
| `source_evidence` | Captured source units and publication evidence, linked by `evidence_id`; retained even when an unresolved source produces no event. |
| `fact_sources[].origins` | Source support and, when available, exact unit spans for each event fact. |
| `evidence_dispositions` | Recorded destinations of projected or unresolved source material. |
| `final_brief_queue` | Event candidates and unresolved fragments requiring a decision. `capture_status: discovery-only` flags a source for which full text was unavailable; it does not promote the item. |

Required flags ask for a decision, not automatic inclusion. Source-fragment entries in `required_final_brief_titles` now set `separate_bullet_by_default: false`; each fragment still requires review, and a new bullet needs an independently eligible reporting subject. `required_final_brief_titles`, `final_brief_markdown`, and an adjacent `*.brief.md` are coverage scaffolds, not the finished brief. Write from source-supported summaries and facts, checking independent actions, material qualifications and each bullet's supporting URLs.

For source-bound reports, binding and news eligibility are separate decisions. Migrated report families, including app-publisher charts, device benchmarks, operating-feature inventories, media invitations, regulatory-access proposals and locally bound market or retail actions, preserve unresolved ownership for evidence review instead of assigning a weak tier. A qualified invitation with an unresolved event date remains an event with a specific `merge_warnings` reason; it cannot authorize a same-event merge. Other report families retain their existing processing rules. Grouping uses the source-owned action and its identity qualifiers; generated titles and measurement values alone do not establish a shared event.

Passages in `source_evidence` not covered by displayed summaries, selected facts or explicit exclusions remain available for review, even when their source produces no event or deferred candidate. This can increase review material without adding events; it does not establish complete site coverage. For incomplete IT Home listings, the crawler can traverse public date directories within the existing budget; recovered listing failures remain in diagnostics. Publisher indexes can still omit articles, so successful traversal does not guarantee complete discovery.

Version 2.3.1 retains the existing CLI, JSON fields and relevance tiers. Event IDs incorporate bound action identity so distinct actions sharing a URL or title do not collide. Consumers should tolerate additional fields and changes to event membership, IDs and classifications across versions.

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

The policy index at `skills/references/news_policy.md` links to four focused references: eligibility and categories, grouping, evidence and writing, and collection recovery. `SKILL.md` routes each stage directly to the needed reference; ordinary drafting does not require reading collection or implementation details. A source-bound fact or required review fragment does not by itself qualify as a separate news item.

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
