# Changelog

All notable changes to this project will be documented here.

## 1.18.0 - 2026-07-03

- Improved weak filtering for third-party adapters, MagSafe cases, reference timelines, explainer videos, install-preparation guides, public procurement responses, and third-party browser/security stories that only use Apple devices or platforms as context.
- Improved event clustering boundaries for iCloud+ perks, Apple price and stock reactions, iPhone production-plan responses, foldable-iPhone production targets, and iPhone modem vs. NAND/storage leak details.
- Added iPhone Photography Awards handling so cross-source award coverage stays eligible, merges correctly, and remains classified as a hardware/product ecosystem story.
- Fixed foldable iPhone 10-million-unit production/order reports so sources merge when they share the same production target while remaining separate from panel-share, price, and broader roadmap background.
- Updated fallback policy guidance for tutorial exclusions, third-party Apple-adjacent noise, and high-volume hardware/price event boundaries.
- Added regression coverage for weak third-party noise, iPhone Photography Awards, iCloud+ perks, price/stock/production separation, modem vs. NAND leaks, and foldable iPhone production-order merging.

## 1.17.0 - 2026-07-02

- Added stronger direct iPhone hardware rumor handling so battery-capacity, SIM/eSIM, and supplier-leak details stay in `events` instead of `deferred_events`.
- Improved foldable iPhone panel-market clustering so Counterpoint-style panel share and shipment reports merge across sources while production-target and pricing roadmap stories remain separate.
- Fixed MacBook price and shipment market reports so they no longer merge with M-series MacBook roadmap events.
- Updated fallback policy guidance for iPhone hardware specs, foldable panel-market boundaries, and MacBook price/roadmap separation.
- Added regression coverage for iPhone data-leak details, foldable panel reports, direct iPhone battery rumors, and MacBook price/roadmap boundaries.

## 1.16.0 - 2026-07-01

- Improved deferred-event recovery for direct Apple legal and regulatory stories, including Apple/Epic Supreme Court coverage and Siri AI / EU DMA meeting reports.
- Improved event clustering so Tim Cook / EU Siri AI reports merge across software, policy, and leadership angles while keeping distinct App Store legal matters separate.
- Improved weak filtering for product commentary and analysis posts, keeping MacBook Ultra opinion-style articles out of required final-brief events while preserving source-backed hardware roadmap rumors.
- Improved Apple Pay and App Store payment classification so Apple Pay wording, fee percentages, or `interest` in legal articles no longer demote App Store litigation into third-party financial-service candidates.
- Updated fallback policy guidance for Siri AI / EU DMA regulatory meetings, App Store legal appeals, product commentary exclusions, and high-volume event boundaries.
- Added regression coverage for Siri AI / EU DMA event merging, Epic Supreme Court relevance, product-analysis weak filtering, competitor display-panel background handling, and related clustering safeguards.

## 1.15.0 - 2026-06-30

- Improved 9to5Mac discovery by preserving WordPress category and tag context from the posts API, restoring coverage for Apple TV+ content stories and OS update reports that were previously under-ranked.
- Improved OS release clustering with version-train, release-channel, beta-number, RC, final-release, and security-update facets so current betas, legacy RCs, public security releases, and support-document explanations stay separate unless they describe the same rollout.
- Improved hardware roadmap and data-leak clustering so A20 Pro packaging, iPhone 18 Pro feature rumors, iPhone Ultra or iPhone Air roadmap items, supplier leaks, and price or memory-supply stories remain separate when their concrete Apple action differs.
- Added source-level filtering for 爱范儿 `早报` pages and kept IT之家 `IT早报` filtering aligned, reducing daily-brief roundup noise without reducing standalone Apple article discovery.
- Updated skill and fallback policy guidance so automation agents account for every required brief item, keep eligible Apple services/content stories, and merge only duplicate coverage of the same subject and action.
- Added regression coverage for 9to5Mac API context, OS release boundaries, Apple strategic transactions, service/content inclusion, daily-brief filtering, hardware-data-leak classification, and high-volume roadmap clustering.

## 1.14.0 - 2026-06-29

- Added source-level filtering for IT之家 `IT早报` pages so daily link roundups are skipped during candidate discovery while standalone IT之家 Apple articles remain eligible.
- Improved Apple product price clustering by separating reseller or retailer retroactive order price-difference disputes from official Apple price increases and supplier cost-pass-through stories.
- Improved weak filtering for non-Apple price-follow-up rumors, including third-party drone or competitor price-change stories that mention Apple only as market context.
- Refined price-topic facet selection so title-led Apple pricing events keep concrete detail facets without merging unrelated cost, supplier, or retail actions.
- Updated fallback policy guidance and regression coverage for IT之家 daily-brief filtering, retroactive reseller adjustments, and non-Apple price follow-up handling.

## 1.13.0 - 2026-06-28

- Improved weak filtering for non-Apple primary subjects and ambiguous Apple-like terms so Safari vehicle names, non-Tim-Cook place names, third-party chip launches, Plex pricing, third-party browser usage on Mac, and similar Apple-adjacent references do not enter final events.
- Improved price-heavy hardware clustering by splitting restricted-memory-supplier approval, external reactions, supplier cost-pass-through disputes, official refurbished availability, future product price forecasts, and broad component-shortage background into separate event families.
- Improved `key_facts` extraction and event-level fact retention for short structured list items, preserving full compatibility or device-support lists such as iPadOS unsupported iPad model lists.
- Improved source cleanup for MyDrivers/快科技 related-news blocks so article-tail recommendation titles do not pollute summaries, key facts, or merge anchors.
- Updated skill and fallback policy guidance for empty-category checks, granular pricing actions, ambiguous Apple terms, and structured short-list preservation.
- Added regression coverage for non-Apple incidental context, ambiguous Apple terms, restricted memory supplier approval, price follow-up splitting, short list facts, and MyDrivers related-news cleanup.

## 1.12.1 - 2026-06-27

- Added stronger final-brief coverage metadata to `final_brief_queue`, `required_final_brief_titles`, `final_brief_coverage`, status JSON, and the adjacent `*.brief.md` scaffold so every eligible JSON event remains a hard brief boundary.
- Improved omission guidance so automation agents do not drop eligible `events` items merely because they are single-source, speculative, rumor-framed, lower-profile, competitor-adjacent, or less prominent than same-day major news.
- Updated skill and fallback policy wording to preserve single-source Apple hardware roadmap or product-development rumors when the crawler has already classified them as included events.
- Added regression coverage for single-source speculative hardware events such as the MacRumors Apple iRing report to ensure they stay visible in required brief checklists.

## 1.12.0 - 2026-06-27

- Improved candidate relevance for Apple relief donations and Apple Books/App Store platform-trust stories, including AI-generated knockoffs, fraud, copyright, and review/enforcement issues that mention other stores only as background.
- Refined hardware roadmap clustering by product family so MacBook/M-series reports, iPhone/A-series RAM reports, future iPhone price forecasts, smart-ring rumors, and broad Apple silicon timelines stay separate unless they describe the same Apple product action.
- Split official refurbished-store or retail availability from Apple product price/cost-pressure clusters while preserving current price increases, Micron or supplier context, Apple responses, and memory/storage shortage facts in the correct pricing event.
- Added company-organization handling for Apple executive departures and OpenAI poaching reports without letting CEO, Gurman/Bloomberg, product-design, or industrial-design background reclassify hardware roadmap stories.
- Added regression coverage for donation discovery, Apple Books platform trust, 9to5Mac promo-tail cleanup, smart-ring roadmap relevance, multi-vendor chip background deferral, product-family merge boundaries, and retail-vs-price event splitting.

## 1.11.0 - 2026-06-26

- Improved Apple product price-increase handling with dynamic `key_facts` limits, structured price-change buckets, market and analyst reaction facts, follow-up scope facts, and compact official responses so large pricing clusters retain material numeric details.
- Improved structured list extraction so long product tables from Chinese and English sources keep later rows such as Vision Pro, HomePod, Apple TV, regional price changes, and related product-scope details instead of being truncated.
- Improved relevance and clustering for Apple online-store status, official refurbished product availability, third-party platform updates that directly improve Apple-device interoperability, and Apple hardware price or promotion follow-ups while keeping routine retail deals weak.
- Tightened price-event fact filtering so unrelated high-number paragraphs such as Siri/prompt, podcast, buying-guide, or deal text do not enter pricing summaries.
- Updated fallback policy and skill guidance for high-volume pricing, official store or refurbished stories, third-party platform interoperability, structured fact preservation, and manual recovery of direct Apple events.
- Added regression coverage for price-event key facts, structured price lists, store and refurbished handling, interoperability updates, price/promotion separation, weak deal filtering, and large-cluster fact retention.

## 1.10.0 - 2026-06-25

- Improved Apple OLED and display-panel supply-chain handling so broad multi-product panel allocation, foldable-iPhone panel production, and foldable-iPhone launch timing stay as separate hardware events.
- Improved first-party Apple OS, built-in app, Siri/Apple Intelligence, and support-document classification so body background such as Apple TV hardware, Wallet, App Store, or third-party calendars no longer overrides the title's main Apple action.
- Updated weak-relevance handling for non-Apple app launches on iOS, iPadOS, macOS, watchOS, Apple Watch, iPhone, iPad, Mac, or App Store so routine platform availability stays in `deferred_events`.
- Improved cross-language clustering for Swift Package Index and developer ecosystem infrastructure while preserving weak-noise filtering for buying guides, opinion pieces, surveillance/device-tracking stories, and third-party device-management services.
- Updated fallback source policy for display-panel product scope, first-party software priority, and non-Apple platform-availability stories.
- Added regression coverage for OLED scope separation, support-document and Siri classification, Calendar updates, third-party iOS app deferral, Swift Package Index merging, and weak Apple-adjacent filtering.

## 1.9.0 - 2026-06-24

- Added Apple strategic transaction, merger, acquisition, and buyout relevance handling so direct Apple counterparty reports such as Apple/Disney merger discussions stay eligible.
- Improved cross-language clustering for strategic transaction stories by requiring the same transaction counterparty and concrete action before merging reports.
- Improved Apple developer ecosystem detection so Swift, package-index, open-source developer infrastructure, and similar projects joining Apple remain in `events`.
- Improved early candidate relevance for Apple hardware roadmap and supply-chain stories so MacBook display-panel planning and RFI reports are not dropped before detail parsing.
- Updated source policy guidance for strategic transactions and developer ecosystem infrastructure while keeping routine speculation and unrelated third-party stories excluded.
- Added regression coverage for strategic transaction eligibility and merging, developer ecosystem infrastructure, and hardware roadmap candidate gating.

## 1.8.0 - 2026-06-23

- Added final-brief coverage scaffolding with `final_brief_queue`, `required_final_brief_titles`, `final_brief_markdown`, and adjacent `*.brief.md` output so automation agents can verify every eligible JSON event before writing the Chinese brief.
- Improved 9to5Mac and high-volume OS discovery with WordPress posts API parsing, current-window guide eligibility, OS component/action detection, and stronger handling for beta roundups, productivity apps, widgets, AirPort Utility, and Apple TV Remote style platform changes.
- Improved Chinese roundup and listing handling by splitting distinct Apple subitems into separate article variants while preventing unrelated digest headings, competitor paragraphs, or non-Apple market context from becoming Apple events.
- Improved relevance classification for Apple company and services leadership, design-team organization changes, Apple executive service stories, Apple TV hardware versus content, Apple product price increases, broad hardware roadmaps, foldable iPhone supply-chain items, and Apple-specific market reports.
- Updated weak-relevance and exclusion rules for third-party security software promos, routine retailer discounts, broad multi-vendor market reports, non-Apple research using Apple products as context, competitor product comparisons, and accessory compatibility stories.
- Added regression coverage for coverage scaffolds, 9to5Mac API discovery, OS micro-events, roundup splitting, Apple Wallet Digital ID, company leadership clustering, service-executive merging, hardware roadmap grouping, price/cost separation, and weak-noise filtering.

## 1.7.0 - 2026-06-20

- Added CarPlay platform-feature handling so iOS CarPlay updates stay in the main software brief instead of being deferred as routine third-party app availability.
- Improved event clustering for Apple pricing, visionOS device-specific AI features, watchOS compatibility, and iPhone parts factory contamination reports across English and Chinese sources.
- Updated weak-relevance handling for competitor benchmark comparisons, third-party accessories and displays, HomePod-alternative reviews, third-party app beta updates, buying-advice posts, and tag pages.
- Kept broad source discovery intact while moving weak Apple-adjacent items to deferred JSON traceability instead of final brief events.
- Added regression coverage for CarPlay, benchmark comparisons, price-buying advice, third-party accessory and app updates, tag pages, visionOS M5 features, and factory contamination clustering.

## 1.6.0 - 2026-06-19

- Improved Apple service-content clustering so Apple TV series updates, F1 free-streaming news, Apple Music charts, and separate production-status items no longer collapse into one service bucket.
- Added Apple Music top-artist chart facets and cross-language anchors so MacRumors, AppleInsider, and cnBeta follow-ups merge into one event when they cover the same historical ranking.
- Tightened Apple-term handling so `Swift` only counts as an Apple signal in programming or developer contexts, preventing non-Apple Swift Observatory coverage from entering `events`.
- Deferred third-party XR and smart-glasses comparison stories that use Apple, iPhone, or Vision Pro mainly as market context while preserving Apple Vision product-roadmap coverage.
- Improved cross-source event grouping for A12/A13 BootROM exploits, Find My location-sharing controls, and Brazil App Store policy changes without reducing source discovery breadth.
- Added regression tests for service de-clustering, Apple Music chart merging, Swift context scoring, third-party XR deferral, and weak Apple-adjacent filtering.

## 1.5.0 - 2026-06-18

- Added specific hardware-roadmap facets and conservative mixed-topic splitting so iPhone Air successor reports, foldable iPhone render leaks, and related tag/list pages no longer collapse into one event.
- Improved iOS performance coverage by merging data-rich 40-plus optimization reports across 9to5Mac, IT之家, and 快科技 while keeping unrelated future-hardware testing separate.
- Improved Apple product price-increase clustering with cross-language price, cost, memory, storage, and Tim Cook anchors, while suppressing misleading multi-region warnings for one global pricing event.
- Focused IT之家-style roundup articles on their Apple-specific item so unrelated daily-brief topics do not dominate titles, summaries, or `key_facts`.
- Added cached term, topic-facet, and research-candidate checks to keep event consolidation responsive during high-volume crawls.
- Added regression tests for roundup focusing, summary-level performance merging, product-price clustering, hardware-roadmap splitting, and region-warning handling.

## 1.4.0 - 2026-06-17

- Improved official Apple Store accessory handling so third-party accessories newly available through Apple channels are treated as hardware/product news without promoting routine retailer deals.
- Tightened Apple services and content clustering so Apple TV renewals, Apple Music playlists, Apple One offers, and credit-card perks remain separate unless they share title-level entities.
- Improved source cleanup for 9to5Mac and IT之家 by trimming additional promotional sections, generic service subscription boilerplate, and unrelated page/sidebar content before summaries and `key_facts`.
- Fixed parsing for long fractional ISO timestamps such as IT之家 `data-ot` values with seven decimal places.
- Preserved material Apple service-offer facts, including subscription prices, discounts, eligibility terms, and card benefits, while filtering generic subscription templates.
- Added regression tests for official accessory availability, service de-clustering, source cleanup, service-offer facts, IT之家 article scope, and long ISO timestamp parsing.

## 1.3.0 - 2026-06-16

- Improved event classification so iPhone Mirroring feature updates are treated as OS/app changes instead of broad compatibility stories.
- Added a dedicated macOS Terminal paste-protection signal so support-document and security coverage stays separate from macOS beta or filesystem update events.
- Deferred routine third-party accessory and consumer-electronics stories that only mention Apple-platform compatibility, while preserving official Apple/Beats hardware and direct Apple-platform actions.
- Tightened final-brief guidance around `event.id` boundaries so independent JSON events are not recombined with transition phrases to shorten long briefs.
- Updated `SKILL.md` and `references/news_policy.md` with aligned fallback rules for accessory compatibility, security/support-document changes, and granular event grouping.
- Added regression tests for iPhone Mirroring classification, Terminal security de-clustering, and third-party dock compatibility deferral.

## 1.2.0 - 2026-06-14

- Improved relevance scoring so Apple OS support and compatibility changes, Apple vehicle-project asset sales, and unreleased Beats hardware sightings stay eligible while routine recaps, buying advice, competitor comparisons, and generic safety stories remain deferred.
- Tightened Apple-term handling so bare chip-like names such as `M3` or `C1` only count as Apple anchors when nearby context identifies Apple silicon or Apple products.
- Improved event clustering for MacBook thermal defects versus MacBook Ultra display rumors, iPhone material or biometric rumors, iPhone Ultra foldable reports, Beats sightings, and hardware-adjacent company actions.
- Improved source cleanup by filtering Apple service affiliate rows, Chinese site boilerplate, and same-site related-link headline fragments before `summary`, `key_facts`, classification, and merging.
- Updated `SKILL.md` and `references/news_policy.md` to keep final briefs free of diagnostics, debug grouping notes, and source-processing commentary while preserving granular eligible events.
- Added regression tests for OS support-drop relevance, competitor-marketing deferral, Beats hardware handling, Apple Car asset sales, affiliate cleanup, related-link noise, and new merge guards.

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
