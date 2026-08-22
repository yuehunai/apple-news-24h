# apple-news-24h

**English** | [简体中文](README.zh-CN.md)

A Codex skill and standalone Python crawler for generating a recent 24-hour Apple software and hardware news brief.

The skill discovers candidates from selected English and Chinese technology sources, verifies article detail-page timestamps, normalizes timezones through UTC, groups duplicate coverage at event level, and outputs a two-section Chinese brief: `软件与系统` and `硬件与产品`.

## Status

This project is experimental. News sites change markup, feeds can fail, and inclusion rules need ongoing maintenance. Treat the output as a structured brief draft that still benefits from editorial review.

## Latest Update

### 1.60.0 - 2026-08-22

- Added pre-reconciliation claim projection for multi-title first-party service pages, requiring local named-subject, concrete-action, and supporting-fact evidence so independent Apple TV releases stay separate without creating synthetic children from background text.
- Made the structured reconciler authoritative for article relevance and category, with changed-object identities for hardware components, finishes, retail packaging, platform rollouts, supplier actions, and measured market reports so aggregate summaries cannot reclassify or bridge unrelated events.
- Improved event boundaries for same-publisher reports, third-party Apple-platform utilities, regional market measurements, current product milestones, retrospective hands-on articles, and direct Apple Pay, AirPods, MacBook Pro, Apple Watch, and organizational actions.
- Removed the duplicated group-level relevance reclassification path and related legacy helpers from the main crawler, reducing conflicting post-processing while keeping recall-oriented discovery groups as proposals for structured reconciliation.
- Updated fallback policy guidance and expanded regression coverage from 1,124 to 1,152 tests; concurrent live validation preserved identical per-source discovery counts and all 59 source URLs while reducing runtime from 55.3 to 51.7 seconds, and clean-agent validation produced zero merge warnings with all 42 main and deferred event IDs uniquely accounted for.

## What It Does

- Collects recent Apple-related software, systems, services, hardware, accessories, health, research, legal, and company-action news.
- Uses RSS/Atom first, then source pages and fallback discovery where configured.
- Opens article detail pages to verify precise publication times whenever possible.
- Converts article times to UTC for the 24-hour window comparison.
- Deduplicates multiple reports into event-level items.
- Labels event kind and relevance tier so broad discovery can preserve weak Apple-adjacent candidates without polluting the final brief.
- Extracts key numeric facts, lists, feature names, countries, terms, eligibility details, and rollout limits for richer summaries.
- Emits Markdown or JSON.

## Architecture

- `scripts/apple_news_24h.py` handles source discovery, page fetching, timestamp verification, article extraction, event orchestration, and Markdown/JSON rendering.
- `scripts/apple_news_core/article_projector.py` projects a source page into independently reportable first-party content claims only when each child has a local named subject, concrete action, and supporting facts, preventing both mixed service events and synthetic children derived from background text.
- `scripts/apple_news_core/event_identity.py` converts article titles and leads into structured event identities covering products, components, actors, actions, regions, legal cases, content forms, and named subjects. Body text is used only as constrained supporting evidence so related links and background paragraphs cannot redefine the event.
- `scripts/apple_news_core/event_matcher.py` compares those identities with conservative product, component, action, region, legal-case, and subject compatibility rules. Keeping this decision layer pure makes same-event clustering independently testable and easier to maintain.
- `scripts/apple_news_core/event_reconciler.py` preserves accepted seed clusters, applies explicit action boundaries, and merges exact cross-source event signatures without allowing generic similarity or transitive bridges to reopen settled groups.
- `tests/test_event_identity_architecture.py` and the dated reconciliation suites through `tests/test_20260822_authoritative_event_pipeline.py` provide focused regression coverage for identity extraction, matching, structured assertion reconciliation, action ownership, claim projection, changed-object boundaries, seed evidence, and relevance tiers; the existing crawler tests continue to verify discovery, parsing, clustering, rendering, and source cleanup end to end.

## What It Does Not Do

- It is not an Apple official project.
- It does not provide investment, legal, medical, or product-purchase advice.
- It does not guarantee complete coverage when sources block requests, feeds are delayed, or pages change structure.
- It should not be used to republish full articles or cached source pages.

## Installation As A Codex Skill

Clone the repository directly into your Codex skills directory:

```bash
git clone https://github.com/yuehunai/apple-news-24h "$CODEX_HOME/skills/apple-news-24h"
```

If `CODEX_HOME` is not set, Codex commonly uses `~/.codex`:

```bash
git clone https://github.com/yuehunai/apple-news-24h ~/.codex/skills/apple-news-24h
```

You can also give this repository URL to Codex and ask it to install the skill automatically:

```text
https://github.com/yuehunai/apple-news-24h
```

Then invoke it explicitly, or call it directly from an automation:

```text
$apple-news-24h
```

The skill intentionally disables implicit invocation in `agents/openai.yaml`, so ordinary Apple or technology conversations should not trigger it automatically.

## CLI Usage

The crawler uses only the Python standard library.

Markdown output:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format markdown
```

JSON output:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

JSON keeps included brief items in `events`. Weak Apple-adjacent candidates, such as third-party app stories or competitor comparisons that do not describe a direct Apple action, may be kept in `deferred_events` for review. Event objects can include `event_kind`, `relevance_tier`, `relevance_reason`, `regions`, and `merge_warnings`.

JSON output may also include `final_brief_queue`, `required_final_brief_titles`, `final_brief_markdown`, and an adjacent `*.brief.md` file when `--output` is used. These are coverage checklists for automation agents; draft the final brief from full `events` summaries, `key_facts`, and source links.

Diagnostics for debugging source failures:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json --include-diagnostics
```

Useful options:

- `--hours 24`: lookback window.
- `--timezone auto`: detect system timezone; pass an IANA timezone such as `America/Los_Angeles` to force one.
- `--format markdown|json`: choose final output format.
- `--cache-dir PATH`: save successful HTTP responses for current-run inspection.
- `--output PATH`: atomically write full output to a file and print only a compact status JSON.
- `--include-diagnostics`: include failed fetches, source failures, selected-detail fetch failures, discovery fallback counts, and low-confidence timestamp notes.

By default, the cache directory is `apple-news-24h` under Python's platform temporary directory. The crawler clears that directory at startup and writes a marker file plus current-run responses. Old cache files must not be used as a freshness fallback.

## Network Permission

The crawler needs live network access to fetch feeds, channel pages, and article pages. In sandboxed agent environments, the first run may fail with DNS or network-permission errors. If the result is empty or suspiciously sparse, this skill will first rerun the same command with network approval. If it still fails, it will inspect diagnostics or use fallback discovery. Make sure your sandbox network setting is at least Auto Review or a more permissive mode.

## Sources

Primary sources include MacRumors, 9to5Mac, AppleInsider, The Verge, Apple Newsroom, IT之家, 爱范儿, 快科技, and cnBeta. Supplemental fallback sources include 新浪科技/财经, 网易科技, 36氪, and other mainstream Chinese technology pages when needed.

See `references/news_policy.md` for source URLs, default timezones, inclusion rules, exclusion rules, event merge rules, and fallback handling.

## Tests

Run the offline test suite:

```bash
python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
python3 -m py_compile scripts/apple_news_24h.py scripts/apple_news_core/event_identity.py scripts/apple_news_core/event_matcher.py scripts/apple_news_core/event_reconciler.py
```

Live smoke tests are intentionally separate from CI because they depend on network access and third-party site availability.

## Legal And Attribution

This project is not affiliated with, endorsed by, or sponsored by Apple Inc. Apple, iPhone, iPad, Mac, Apple Watch, AirPods, Vision Pro, and other Apple product names are trademarks of Apple Inc.

The crawler fetches publicly available feeds and pages. Users are responsible for complying with source websites' terms, robots policies, rate limits, copyright rules, and applicable laws. Do not publish cached source pages or long verbatim excerpts from articles.

## License

MIT. See `LICENSE`.
