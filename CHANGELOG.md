# Changelog

All notable changes to this project will be documented here.

## 0.3.0 - 2026-06-04

- Added event metadata and relevance tiers, including `event_kind`, `relevance_tier`, `relevance_reason`, `regions`, `merge_warnings`, and JSON `deferred_events`.
- Kept broad discovery while separating final-brief events from weak Apple-adjacent candidates such as competitor comparisons, routine third-party app stories, evergreen guide pages, and ordinary product ads.
- Improved event clustering so AirDrop/Quick Share interoperability, Apple Wallet feature rumors, OS compatibility rumors, hardware rumors, App Store legal/regulatory actions, and developer-center news do not collapse into unrelated events.
- Updated skill guidance to require Markdown source links, preserve all eligible `events`, include `strong` and `ecosystem` items, and keep `weak` items out of the final brief by default.
- Added regression tests for relevance tiers, ecosystem interoperability, Apple Wallet clustering, Markdown source links, weak-candidate deferral, guide-page filtering, and category assignment.

## 0.2.0 - 2026-06-02

- Expanded source discovery with deeper channel-page scanning, The Verge Apple RSS, and IT之家 Apple channel/tag pages.
- Improved relevance detection for Apple market data, shipment reports, Apple TV+ rankings and original films, Apple retail-store news, research stories, and service updates.
- Added support for slash-formatted Chinese timestamps such as `2026/6/1 21:46:34`.
- Improved summary quality by preserving important numeric facts, lists, feature names, rollout details, eligibility rules, and official-data bullets while suppressing unrelated page headings.
- Added regression tests for source configuration, late channel links, timestamp parsing, Apple Store categorization, and expanded relevance rules.

## 0.1.0 - 2026-05-29

- Initial open-source release.
- Added Codex skill metadata, reusable crawler script, source policy reference, and offline tests.
- Added bilingual English and Simplified Chinese README documentation.
- Supports Markdown and JSON output, automatic timezone detection, UTC window comparison, current-run cache cleanup, event-level grouping, and key-fact extraction.
- Includes rules for Apple research disclosures, Apple health-data research, Apple Newsroom publication-time handling, official service promotions, and common exclusion patterns.
