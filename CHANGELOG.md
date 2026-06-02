# Changelog

All notable changes to this project will be documented here.

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
