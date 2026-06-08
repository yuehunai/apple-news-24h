---
name: apple-news-24h
description: Use this skill only when explicitly invoked as $apple-news-24h or by an automation that asks for the reusable Apple 24-hour news brief. Do not use it implicitly in ordinary Apple, technology, or news conversations.
---

# Apple 24-Hour News Brief

## Purpose

Generate a recent 24-hour Apple software and hardware news brief for automation runs. The skill discovers candidates from fixed English and Chinese technology sources, verifies detail-page timestamps, deduplicates event-level coverage, and produces a clean brief with two sections: `软件与系统` and `硬件与产品`.

This skill must not be invoked implicitly. Use it only when the prompt explicitly names `$apple-news-24h` or an automation is configured to run this skill.

## Quick Start

Run the bundled crawler first:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

For a direct Markdown draft:

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format markdown
```

Use `--include-diagnostics` only while debugging. Diagnostics are not part of the final user-visible brief. When `--output` is set, stdout prints only a short status JSON and the full result is written atomically to the output file. The cache directory is for saving successful responses for inspection; by default it is `apple-news-24h` under Python's platform temporary directory. The script clears that cache directory at startup before writing the current run's responses, and old cached pages must never be used as a freshness fallback. Use `--cache-dir` and `--output` when an automation needs fixed paths.

JSON output uses `events` as the default final-brief candidate list. `events` contains `strong` Apple stories plus `ecosystem` stories that have a concrete Apple ecosystem impact, such as AirDrop/Quick Share interoperability. Weak Apple-adjacent stories are preserved in `deferred_events` for inspection and should not be added to the final brief unless source review shows the crawler clearly misclassified a direct Apple action.

## Network Permission

The crawler requires live network access because it fetches RSS feeds, source home/channel pages, and article detail pages. In sandboxed Codex runs, the first attempt may be blocked across all sources with DNS or network-permission errors. If that happens, do not accept the empty result and do not switch to the reference document as the answer source. Immediately rerun the same crawler command while requesting network approval.

For automations, run this skill in a context where network access can be approved automatically or explicitly. If the first run returns zero events, both final sections are empty, or the output is clearly suspiciously sparse, assume network permission is the most likely cause and immediately rerun the same crawler command while requesting network approval. Only if that approved rerun is still empty or suspiciously sparse should you rerun with `--include-diagnostics` and check `failed_sources`, `failed_fetches`, and `low_confidence_articles`.

Only after a live approved run still cannot collect enough source pages should you read `references/news_policy.md` and follow its fallback workflow: open source home/channel pages, date archives, site search, and web search. The reference document is procedural guidance, not a news source, and old cached pages must not be used as a substitute for current 24-hour collection.

## Workflow

1. Run the crawler with JSON output and a fixed `--output` path; read that file for the full event list and metadata.
2. The crawler prepares the cache directory first. By default it uses `apple-news-24h` under Python's platform temporary directory, clears previous files, and keeps only the current run's cache plus the marker file. For deterministic automation paths, set `--cache-dir` explicitly.
3. Wait for the crawler command to finish before judging the result. When there are many source pages or slow detail-page responses, a live crawl can legitimately run for more than 5 minutes. This is normal; do not interrupt the process, kill the script, inspect partial output, or switch to diagnostics merely because the command is taking a long time.
4. If the first completed run returns no events, both categories are empty, or the result is clearly too sparse, do not start diagnostics yet. Rerun the same crawler command immediately while requesting network approval.
5. If the approved rerun is still empty or suspiciously sparse, rerun with `--include-diagnostics` and check `failed_sources`, `failed_fetches`, and `low_confidence_articles`.
6. If important required sources still failed after the approved rerun and diagnostics pass, use the fallback rules in `references/news_policy.md`: try the site homepage/channel page, site search, and web search for the current and previous local dates.
7. Use `events` as the starting point for the final brief. Check `deferred_events` only as a review queue for weak Apple-adjacent stories; do not include those items unless they are clearly misclassified direct Apple product/service/company actions.
8. Use event-level grouping from the JSON as the starting point, then merge or split events when the same product/function/action was incorrectly clustered.
   - Use `event_kind`, `regions`, `relevance_tier`, and `merge_warnings` as the first clues for cluster review.
   - If `merge_warnings` indicates mixed event kinds, mixed relevance tiers, or multiple incompatible region markers, inspect the source titles and split the item when it combines distinct events.
   - Do not merge articles solely because they share broad tokens such as Apple, App Store, developer, legal, regulation, Vision Pro, or AI.
   - Treat each event's `key_facts` field as mandatory source material for the brief. It preserves numeric facts, listed features, country/region lists, terms, eligibility, and other enumerated details from source pages.
   - Do not replace a source's data list or feature list with a vague sentence such as "Apple highlighted several protections/features." You may compress wording, but keep the actual material numbers and listed items.
9. Produce the final brief in Chinese:
   - Start with `**软件与系统**`, then `**硬件与产品**`.
   - Coverage comes before brevity. Include every event in `events` that passes the rules unless it clearly matches an exclusion rule; do not silently shorten the brief to only a few top stories.
   - Before finalizing, compare the event count in JSON against the number of bullets you wrote. If you skipped an `events` item, it must be because of a clear exclusion rule, not because it looked niche, less important, competitor-adjacent, or third-party-adjacent.
   - Include `strong` and `ecosystem` events. Keep `weak` events out of the final brief by default; they belong in `deferred_events` for traceability.
   - Do not omit `ecosystem` items such as AirDrop/Quick Share interoperability. They are intentionally in `events` because they materially affect the Apple ecosystem.
   - Each item should read like a daily news brief, with important details integrated in the body.
   - Each item must include the important details that make the story useful: what changed, affected product/service/version/model, key numbers or countries when available, rollout status, uncertainty, and practical significance.
   - For official Apple announcements, reports, and feature launches, preserve all material enumerated figures and feature names surfaced in `key_facts`; do not omit later paragraphs just because the lead already summarizes the story.
   - Avoid overly short summaries. Prefer 2-4 substantial Chinese sentences per item when the source material supports it. If the crawler's summary is too thin, open the event's source pages and enrich the item before final output.
   - Put sources only at the end of each item, in parentheses, and keep each source as a Markdown link using `event.sources[].url`, for example `（来源：[MacRumors](...), [9to5Mac](...)）`. Never replace source links with plain source names.
   - Do not add diagnostics, methodology notes, or extra closing explanation.
   - The assistant's final response after `$apple-news-24h` must contain only the two-section brief. Do not append run status, network permission notes, rerun history, cache paths, diagnostics, memory-update status, or any other operational note.
   - If a category is empty, write: `在指定时间窗口内，该分类下没有发现符合条件的新闻。`

## Rules

- The time window is `(T - hours, T]`, where `T` is the current system time.
- The script defaults to system timezone detection. Use `--timezone <IANA name>` only when an automation needs to force a timezone.
- Final inclusion is based on detail-page precise time whenever available. Feed/list times are discovery hints and fallback timestamps, not the preferred final authority.
- For Apple Newsroom pages, use the article's `NewsArticle.datePublished` or visible publication date as the publication authority. Do not use Newsroom `dateModified`, `article:modified_time`, generic page `lastmod`, or `VideoObject.uploadDate` to pull an older article into the 24-hour window.
- Convert all article times to UTC before comparison, then render local display times in the detected timezone.
- Keep only Apple software, services, operating systems, hardware, accessories, health features, Apple business actions, and closely related regulatory/legal/company developments.
- Keep WWDC-related events when they pass the crawler's normal relevance and time-window rules, including keynote, schedule, OS-preview, developer, Apple executive, attendee gift/swag, badge, sticker, Developer app, mascot, and official conference-material stories. Do not downgrade or omit them merely because they look light, promotional, or less important than product rumors.
- Keep Apple research disclosures when Apple is publishing, presenting, previewing, or showcasing research papers/studies at a recognized technical or academic venue such as CVPR. Require concrete research anchors such as `research`, `paper`, `study`, `CVPR`, `computer vision`, or equivalent Chinese terms; do not treat generic AI/WWDC positioning as a research-disclosure event by itself.
- Keep medical/health research stories when Apple Watch, Apple Health, ResearchKit, or other Apple health data is a core subject of a newly published or materially updated study. Require both a concrete Apple health data/product anchor and a research/study anchor; generic wellness tips, app advice, or sleep guides are not enough.
- Exclude tutorials, buying guides, routine deals, pure roundups without new information, podcasts without new reporting, and simple reposts.
- Do not treat official Apple Card, Apple Pay, App Store, Apple services, or Apple retail/customer acquisition promotions as routine deal posts when they reveal a new or materially changed Apple business offer. Include them with enough terms, eligibility, value, timing, and uncertainty details.

For detailed source configuration, default site timezones, category rules, and fallback handling, see `references/news_policy.md`.
