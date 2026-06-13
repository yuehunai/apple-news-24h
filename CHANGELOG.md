# Changelog

All notable changes to this project will be documented here.

## 1.1.0 - 2026-06-13

- Improved event clustering with more specific topic facets for built-in app changes, Safari, Messages, Weather, input methods, Beats/headphone sightings, iPhone color mockups, and Vision Pro spatial-experience projects.
- Fixed Vision Pro professional and immersive-experience coverage so cross-source Disney/EPCOT reports merge together while unrelated Beats or hardware-rumor stories stay separate.
- Tightened merge scoring by ignoring generic publication and source words such as Apple, published, showcase, dates, and Chinese equivalents when deciding whether events are duplicates.
- Improved 9to5Mac article cleanup by removing additional article-tail affiliate recommendation blocks before summary and `key_facts` extraction.
- Updated `SKILL.md` and `references/news_policy.md` guidance to preserve granular high-volume Apple events while keeping fallback merge rules aligned with crawler behavior.
- Added regression tests for the new clustering facets, Vision Pro cross-language merging, Beats separation, and source-tail promotion cleanup.

## 1.0.1 - 2026-06-12

- Improved `SKILL.md` guidance by consolidating inclusion/exclusion, event grouping, `key_facts`, and final bullet-count rules without narrowing coverage.
- Updated `references/news_policy.md` to match the skill guidance while retaining fallback-specific messaging, third-party availability, affiliate cleanup, and timestamp guidance.
- Tightened final-brief instructions around one eligible JSON `events` item per bullet, duplicate-only merging, and preserving concrete details from `title`, `summary`, and `key_facts`.
- Kept crawler and runtime behavior unchanged; this release is documentation-only and uses the existing verification suite.

## 1.0.0 - 2026-06-11

- Improved OS and WWDC micro-event clustering with component-level facets for communication frameworks, FaceTime camera features, Time Machine/AFP changes, boot-volume detection, Rosetta support, and Mac hardware reliability reports.
- Tightened final-brief guidance so separate JSON `events` stay as separate bullets unless source review confirms duplicate coverage of the same core event.
- Improved direct Apple-subject handling so competitor, third-party, or partner background no longer suppresses Apple OS, developer-tool, legal, service, official-accessory, or ecosystem-interoperability stories.
- Kept source cleanup details in fallback policy while simplifying `SKILL.md` to emphasize automation workflow and final-output constraints.
- Added regression tests for developer-tool relevance, official accessory availability, in-window detail selection, third-party deferral, and OS-component de-clustering.

## 0.7.0 - 2026-06-10

- Added guarded third-party Apple-platform availability handling so routine app or service listings stay in `deferred_events` while direct Apple platform approvals and interoperability stories remain eligible.
- Improved high-volume WWDC and OS-preview clustering with topic facets for App Store policy, subscription bundles, discovery, Apple services, AirPods firmware and settings, Sidecar, iPhone Mirroring, wallpapers, macOS performance feedback, and MacBook memory or local-AI reports.
- Improved final-brief guidance so hardware roadmap clues, hardware specification rumors, OS feature changes, service policy changes, and app or service launches stay separate when condensing long briefs.
- Improved source cleanup by trimming article-tail affiliate recommendation blocks before summary and `key_facts` extraction.
- Fixed macOS performance feedback classification so performance and bug wording remains in software/system coverage instead of security or hardware buckets.
- Added regression tests for third-party deferral, affiliate cleanup, micro-event clustering, macOS performance classification, MacBook memory/local-AI splitting, and final source-link behavior.

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
