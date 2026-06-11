# apple-news-24h

**English** | [简体中文](README.zh-CN.md)

A Codex skill and standalone Python crawler for generating a recent 24-hour Apple software and hardware news brief.

The skill discovers candidates from selected English and Chinese technology sources, verifies article detail-page timestamps, normalizes timezones through UTC, groups duplicate coverage at event level, and outputs a two-section Chinese brief: `软件与系统` and `硬件与产品`.

## Status

This project is experimental. News sites change markup, feeds can fail, and inclusion rules need ongoing maintenance. Treat the output as a structured brief draft that still benefits from editorial review.

## Latest Update

### 1.0.0 - 2026-06-11

This is the first formal major release. The skill matured during the WWDC news surge, which acted as a real pressure test: unusually dense Apple coverage exposed weak spots in discovery, clustering, and final-brief compression, and drove the fixes and hardening included in this version.

- Improved OS and WWDC micro-event clustering with component-level facets for communication frameworks, FaceTime camera features, Time Machine/AFP changes, boot-volume detection, Rosetta support, and Mac hardware reliability reports.
- Tightened final-brief guidance so separate JSON `events` stay as separate bullets unless source review confirms duplicate coverage of the same core event.
- Improved direct Apple-subject handling so competitor, third-party, or partner background no longer suppresses Apple OS, developer-tool, legal, service, official-accessory, or ecosystem-interoperability stories.
- Kept source cleanup details in fallback policy while simplifying `SKILL.md` to emphasize automation workflow and final-output constraints.
- Added regression tests for developer-tool relevance, official accessory availability, in-window detail selection, third-party deferral, and OS-component de-clustering.

## What It Does

- Collects recent Apple-related software, systems, services, hardware, accessories, health, research, legal, and company-action news.
- Uses RSS/Atom first, then source pages and fallback discovery where configured.
- Opens article detail pages to verify precise publication times whenever possible.
- Converts article times to UTC for the 24-hour window comparison.
- Deduplicates multiple reports into event-level items.
- Labels event kind and relevance tier so broad discovery can preserve weak Apple-adjacent candidates without polluting the final brief.
- Extracts key numeric facts, lists, feature names, countries, terms, eligibility details, and rollout limits for richer summaries.
- Emits Markdown or JSON.

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
python3 -m py_compile scripts/apple_news_24h.py
```

Live smoke tests are intentionally separate from CI because they depend on network access and third-party site availability.

## Legal And Attribution

This project is not affiliated with, endorsed by, or sponsored by Apple Inc. Apple, iPhone, iPad, Mac, Apple Watch, AirPods, Vision Pro, and other Apple product names are trademarks of Apple Inc.

The crawler fetches publicly available feeds and pages. Users are responsible for complying with source websites' terms, robots policies, rate limits, copyright rules, and applicable laws. Do not publish cached source pages or long verbatim excerpts from articles.

## License

MIT. See `LICENSE`.
