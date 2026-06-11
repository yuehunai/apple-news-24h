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

For automations, run this skill in a context where network access can be approved automatically or explicitly. If the first run returns zero events, both final sections are empty, or the output is clearly suspiciously sparse, assume network permission is the most likely cause and immediately rerun the same crawler command while requesting network approval. Only if that approved rerun is still empty or suspiciously sparse should you rerun with `--include-diagnostics` and check `failed_sources`, `failed_fetches`, `selected_detail_fetch_failures`, `source_detail_selection_counts`, `source_discovery_fallback_counts`, and `low_confidence_articles`.

Only after a live approved run still cannot collect enough source pages should you read `references/news_policy.md` and follow its fallback workflow: open source home/channel pages, date archives, site search, and web search. The reference document is procedural guidance, not a news source, and old cached pages must not be used as a substitute for current 24-hour collection.

## Workflow

1. Run the crawler with JSON output and a fixed `--output` path; read that file for the full event list and metadata.
2. Wait for the crawler command to finish before judging the result. A live crawl can legitimately run for more than 5 minutes when there are many source pages or slow detail-page responses; do not interrupt it, inspect partial output, or switch to diagnostics merely because it is taking a long time.
3. If the completed result is empty or clearly suspiciously sparse, rerun the same crawler command while requesting network approval before starting diagnostics.
4. If the approved rerun is still empty or suspiciously sparse, rerun with `--include-diagnostics` and inspect `failed_sources`, `failed_fetches`, `selected_detail_fetch_failures`, `source_detail_selection_counts`, `source_discovery_fallback_counts`, and `low_confidence_articles`.
5. If important required sources still failed after diagnostics, follow `references/news_policy.md` for fallback discovery through source home/channel pages, date archives, site search, and web search for the current and previous local dates.
6. Use JSON `events` as the final-brief queue. Review `deferred_events` only for clearly misclassified direct Apple actions; otherwise leave weak Apple-adjacent stories out of the brief.
7. Review event clusters before writing. Use `event_kind`, `regions`, `relevance_tier`, and `merge_warnings` to split incorrectly merged events or combine genuinely duplicate events according to the rules below.
8. Write the final Chinese brief from the reviewed events and output only the two requested sections.

## Rules

### Time And Source Authority

- The time window is `(T - hours, T]`, where `T` is the current system time.
- The script defaults to system timezone detection. Use `--timezone <IANA name>` only when an automation needs to force a timezone.
- Convert all article times to UTC before comparison, then render local display times in the detected timezone.
- Final inclusion is based on detail-page precise time whenever available. Feed/list times are discovery hints and fallback timestamps, not the preferred final authority.
- If a selected non-Newsroom detail page fails to fetch but the feed or listing candidate already has a parseable timestamp plus useful summary/context, the crawler may keep it as a low-confidence discovery fallback. Inspect `selected_detail_fetch_failures` and `source_discovery_fallback_counts` when diagnosing sparse results.
- For Apple Newsroom pages, use the article's `NewsArticle.datePublished` or visible publication date as the publication authority. Do not use Newsroom `dateModified`, `article:modified_time`, generic page `lastmod`, or `VideoObject.uploadDate` to pull an older article into the 24-hour window.

### Inclusion And Exclusion

- Keep only Apple software, services, operating systems, hardware, accessories, health features, Apple business actions, and closely related regulatory/legal/company developments.
- Include `strong` and `ecosystem` events. Keep `weak` events out of the final brief by default; they belong in `deferred_events` for traceability. Do not omit `ecosystem` items such as AirDrop/Quick Share interoperability when they materially affect the Apple ecosystem.
- Keep WWDC-related events when they pass the crawler's normal relevance and time-window rules, including keynote, schedule, OS-preview, developer, Apple executive, attendee gift/swag, badge, sticker, Developer app, mascot, and official conference-material stories. Do not downgrade or omit them merely because they look light, promotional, or less important than product rumors.
- Keep Apple research disclosures when Apple is publishing, presenting, previewing, or showcasing research papers/studies at a recognized technical or academic venue such as CVPR. Require concrete research anchors such as `research`, `paper`, `study`, `CVPR`, `computer vision`, or equivalent Chinese terms; do not treat generic AI/WWDC positioning as a research-disclosure event by itself.
- Keep medical/health research stories when Apple Watch, Apple Health, ResearchKit, or other Apple health data is a core subject of a newly published or materially updated study. Require both a concrete Apple health data/product anchor and a research/study anchor; generic wellness tips, app advice, or sleep guides are not enough.
- Exclude tutorials, buying guides, routine deals, pure roundups without new information, podcasts without new reporting, and simple reposts.
- Do not let competitor, third-party, or partner background terms override a clear Apple-subject story. If the title or article lead is about an Apple platform, Apple OS, Apple service, Apple official accessory, Apple legal action, or Apple developer tool, classify by that Apple action. Routine deals, affiliate roundups, and non-Apple product stories remain excluded even when they mention Apple products.
- Do not treat official Apple Card, Apple Pay, App Store, Apple services, or Apple retail/customer acquisition promotions as routine deal posts when they reveal a new or materially changed Apple business offer. Include them with enough terms, eligibility, value, timing, and uncertainty details.
- Treat Apple official accessory availability changes, including Apple Store removal, regional unavailability, discontinuation, or suspected discontinuation, as hardware/product news rather than routine retail or third-party market background.

### Event Grouping And Coverage

- Use event-level grouping from JSON as the starting point, then merge or split events when the same product/function/action was incorrectly clustered.
- If `merge_warnings` indicates mixed event kinds, mixed relevance tiers, or multiple incompatible region markers, inspect source titles and split the item when it combines distinct events.
- Do not merge articles solely because they share broad tokens such as Apple, App Store, developer, legal, regulation, Vision Pro, or AI.
- During high-volume WWDC or OS-preview runs, preserve distinct micro-events instead of merging by broad OS/version context alone. Treat specific topic anchors such as App Store policy, App Store subscriptions/discovery, Apple Music, Apple TV Remote, AirPods firmware/settings, Sidecar touch, iPhone Mirroring, macOS performance/user-feedback reports, system wallpapers, AI wallpapers, OS adoption stats, Apple Wallet, MacBook memory/local-AI spec reports, and iPad/iPhone carrier data plans as separate event topics unless the sources clearly describe the same concrete change.
- Do not allow broad multi-platform OS summaries or recap articles to bridge unrelated specific events. A watchOS app removal, iOS input-method change, Apple Wallet feature, Xcode/developer-tool integration, or other concrete platform action must stay separate unless another source reports that same product/component/action.
- Treat each JSON `events` item as the default unit for one final bullet, not as loose source material for freeform recombination. Include every eligible event unless it clearly matches an exclusion rule.
- Do not omit eligible granular events merely because they are part of a larger OS, WWDC, service, or platform news cycle. Keep them as separate final bullets unless source review shows two JSON events are duplicate coverage of the same core product/function/action.
- Do not combine separate JSON `events` into one final bullet merely to make the brief shorter or more thematic. Shared product family, OS version, WWDC context, Apple Intelligence context, roadmap context, or source timing is not enough to combine events.
- When condensing a long brief, shorten wording inside each event's bullet. Do not condense by building broad theme bullets that span independent hardware roadmap/interface clues, hardware specification or memory/AI-capability rumors, OS feature changes, built-in app changes, service policy changes, app/service launches, or platform API changes.
- Keep distinct built-in apps, OS components, and platform capabilities in separate bullets when their concrete action differs, even if they share the same OS version or Apple Intelligence context. For example, a Notes feature update, a Shortcuts workflow builder, a device Recovery mode, and a CarPlay route-sharing API are separate events unless the sources explicitly report one combined change.
- Do not condense by dropping localized features, input methods, regional rollouts, compatibility lists, feature lists, or other concrete implementation details that appear in `title`, `summary`, or `key_facts`.

### Final Brief Style

- Start with `**软件与系统**`, then `**硬件与产品**`.
- Each item should read like a daily news brief, with important details integrated in the body.
- Treat each event's `key_facts` field as mandatory source material. It preserves numeric facts, listed features, country/region lists, terms, eligibility, and other enumerated details from source pages.
- Do not replace a source's data list or feature list with a vague sentence such as "Apple highlighted several protections/features." You may compress wording, but keep the actual material numbers and listed items.
- For official Apple announcements, reports, and feature launches, preserve all material enumerated figures and feature names surfaced in `key_facts`; do not omit later paragraphs just because the lead already summarizes the story.
- Before finalizing, compare the event count in JSON against the number of bullets you wrote. If you skipped an `events` item, it must be because of a clear exclusion rule, not because it looked niche, less important, competitor-adjacent, third-party-adjacent, or less prominent than same-day major news.
- If the bullet count is lower than the number of eligible JSON `events`, the difference must come only from explicit duplicate-event merges after source review. Do not create combined theme paragraphs that cover multiple independent JSON events.
- Prefer 2-4 substantial Chinese sentences per item when source detail supports it. If the crawler's summary is too thin, open the event's source pages and enrich the item before final output.
- Retain any source link that contributes independent facts, feature lists, compatibility details, implementation details, local context, or materially different framing unless another retained source fully duplicates those same details.
- Put sources only at the end of each item, in parentheses, and keep each source as a Markdown link using `event.sources[].url`, for example `（来源：[MacRumors](...), [9to5Mac](...)）`. Never replace source links with plain source names.
- Do not add diagnostics, methodology notes, source-by-source explanations, run status, network permission notes, rerun history, cache paths, memory-update status, or any other operational note.
- The assistant's final response after `$apple-news-24h` must contain only the two-section brief.
- If a category is empty, write: `在指定时间窗口内，该分类下没有发现符合条件的新闻。`

For detailed source configuration, default site timezones, category rules, and fallback handling, see `references/news_policy.md`.
