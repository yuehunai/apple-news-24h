# Changelog

All notable changes to this project will be documented here.

## 0.6.0 - 2026-06-09

- Added preferred article-body extraction for 9to5Mac and similar pages so related-card or sidebar markup does not replace the real story body.
- Added diagnostics and low-confidence discovery fallback for selected detail pages that fail after candidate selection, preserving useful feed/listing items with parseable timestamps.
- Improved high-volume OS and WWDC coverage by raising the detail-page limit and broadening action matching for feature additions, compatibility changes, customization, and developer beta stories.
- Improved key-fact extraction for short list and table rows so feature lists, implementation options, and localized product details survive into summaries.
- Updated skill and source-policy guidance to treat JSON `events` as an eligible-event queue, retain granular product/platform changes, and preserve source links that add independent details.
- Added regression tests for preferred article-body selection and detail-fetch fallback after candidate selection.

## 0.5.0 - 2026-06-08

- Added IT之家 listing metadata extraction so Apple channel and tag pages can pass article summaries and `data-ot` timestamps into candidate filtering.
- Improved duplicate candidate handling by preserving the richest same-URL discovery item instead of keeping the first sparse homepage link.
- Improved WWDC relevance and detail-page priority so conference materials, attendee gifts, badges, stickers, Developer app items, mascots, and official event stories are not dropped as lightweight items.
- Improved IT之家 article cleanup by suppressing mandatory ad-disclosure text from summaries and `key_facts`.
- Updated skill and source-policy guidance to wait for long live crawls, including runs over 5 minutes, before judging results or starting diagnostics.
- Added regression tests for IT之家 listing summaries, richer duplicate candidates, WWDC priority, ad-disclosure filtering, and related-page noise suppression.

## 0.4.0 - 2026-06-05

- Added feed and page context extraction so source categories such as Apple TV can keep service-content stories in the final brief even when titles omit Apple branding.
- Improved Apple Messages for Business and iMessage AI-agent relevance with guarded platform/action matching, negation handling, and cross-source event merging for Poke-style coverage.
- Kept broad discovery while deferring weak third-party local AI app stories that only target iPhone or Mac, rather than describing a direct Apple action.
- Improved article cleanup for IT之家 and similar pages by suppressing related-post blocks, site footers, and related-title fragments from `key_facts`.
- Updated skill guidance so `$apple-news-24h` final responses contain only the two-section brief, with no run status, diagnostics, cache notes, or permission commentary.
- Added regression tests for Apple TV source context, messages-platform matching and merging, third-party AI app deferral, IT之家 noise filtering, and final source-link behavior.

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
