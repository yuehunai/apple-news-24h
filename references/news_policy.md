# Apple 24-Hour News Policy

## Sources

Primary English sources:

- MacRumors: `https://feeds.macrumors.com/MacRumors-All`
- 9to5Mac: `https://9to5mac.com/feed/`
- AppleInsider: `https://appleinsider.com/rss/news/`
- The Verge: `https://www.theverge.com/rss/index.xml`, `https://www.theverge.com/rss/apple/index.xml`, plus Apple and Tech channel pages when RSS is sparse
- Apple Newsroom: `https://www.apple.com/newsroom/rss-feed.rss`

Primary Chinese sources:

- IT之家: `https://www.ithome.com/rss/`, `https://www.ithome.com/apple/`, `https://www.ithome.com/tags/%E8%8B%B9%E6%9E%9C/`
- 爱范儿: `https://www.ifanr.com/feed`, `http://live.ifanr.com/feed`
- 快科技: `https://rss.mydrivers.com/opml.xml`
- cnBeta: `https://www.cnbeta.com.tw/backend.php`

Supplemental fallback sources:

- 新浪科技 / 新浪财经
- 网易科技
- 36氪
- Other mainstream Chinese technology pages when a primary source references a story but the primary page is unavailable.

## Default Timezones

- MacRumors: `America/Los_Angeles`
- 9to5Mac: `America/Los_Angeles`
- AppleInsider: `America/New_York`
- The Verge: prefer page metadata; default to `America/New_York` if needed
- Apple Newsroom: prefer ISO/UTC metadata; default to `America/Los_Angeles` if needed
- Chinese sources: `Asia/Shanghai`

When a detail page provides an explicit timezone or ISO offset, always trust that over the source default.

Apple Newsroom special rule: use the article-level `NewsArticle.datePublished` or visible Newsroom publication date as the authority. Do not use `dateModified`, `article:modified_time`, page `lastmod`, RSS update time, or `VideoObject.uploadDate` to include a page in the current window, because Newsroom often refreshes those fields for media or page updates on older stories. Date-only Newsroom publication values are interpreted conservatively at midday in the Newsroom default timezone and should be labeled as date-only/low precision in diagnostics when needed.

## Candidate Discovery

Use RSS/Atom first. If a required source fails or looks sparse:

1. Try the source homepage, Apple/channel pages, and date archive pages for both the current local date and previous local date.
2. Search the site for Apple product and system terms: Apple, iPhone, iPad, Mac, macOS, iOS, watchOS, visionOS, AirPods, Apple Watch, Apple Intelligence, Siri, App Store, iCloud, Apple Music, Apple TV, CarPlay.
3. Use web search with `site:<domain>` and the current/previous local date.
4. For Chinese daily digests such as morning briefings, extract only Apple-specific subitems and treat them as candidates.

When feeds or pages expose source-side category hints, keep those hints as candidate context. Category labels such as Apple TV, Apple Music, App Store, iMessage, Apple Wallet, or equivalent Chinese terms may establish Apple service context for a story whose title is otherwise too short or brand-light. Use that context for relevance, event kind, and detail-page prioritization, but do not print raw category labels as standalone facts.

When a candidate is selected for detail-page fetching but that detail request fails, do not automatically discard the story if it is not an Apple Newsroom page and the feed or listing already provides a parseable timestamp plus useful summary/context. The crawler may keep the item as a low-confidence discovery fallback and record it in `selected_detail_fetch_failures` and `source_discovery_fallback_counts`. This is a reliability fallback for transient detail-page failures; it is not a substitute for detail-page time verification when the detail page is available.

## Cache Handling

The script cache is only for inspecting the current run's successful HTTP responses. By default, the crawler uses `apple-news-24h` under Python's platform temporary directory, clears the directory at startup, and writes a marker file plus fresh responses. For automation runs, write the full JSON result with a fixed `--output` path; the script writes this file after cache cleanup and uses atomic replacement. Use `--cache-dir` when an automation needs a predictable cache location. Do not read old cache files as source material or use cache contents to decide whether an event is inside the current 24-hour window.

## Inclusion Rules

Keep new or materially updated news about:

- OS releases, beta/RC updates, security fixes, vulnerabilities, enterprise fixes, platform policy changes.
- CarPlay is an Apple platform. iOS/WWDC-era CarPlay feature, API, Siri, media-interface, AirPlay, navigation, or platform-behavior changes are software/system news even when the article discusses third-party apps; routine third-party CarPlay app availability remains `weak` unless Apple changes the platform, policy, approval, or interoperability behavior.
- Apple services: Apple Music, TV+, Arcade, iCloud, Apple One, App Store, Apple Pay, Apple Card, Apple Intelligence, Siri.
- Hardware and accessories: iPhone, iPad, Mac, Apple Watch, AirPods, Vision Pro, HomePod, official accessories, Apple silicon, modems, displays, cameras, and supply-chain production shifts. Include Apple official accessory availability changes such as Apple Store removal, regional unavailability, discontinuation, suspected discontinuation, or official Apple Store/Apple online store availability for third-party accessories, and treat them as hardware/product news even if the article mentions third-party headset, glasses, or broader market context.
- Health/accessibility features and country availability changes.
- Company actions tied to Apple products/services, including legal, regulatory, donations, partnerships, executive changes, retail/product availability, and regional business moves.
- WWDC-related events when they pass the normal relevance and time-window rules, including keynote, schedule, OS-preview, developer, Apple executive, attendee gift/swag, badge, sticker, Developer app, mascot, and official conference-material stories. Do not downgrade or omit them merely because they look light, promotional, or less important than product rumors.
- Apple research where Apple publishes, presents, previews, or showcases papers/studies at a recognized technical or academic venue, requiring anchors such as research, paper, study, CVPR, computer vision, or equivalent Chinese terms; generic AI strategy or WWDC positioning is not enough by itself. Include medical or health research where Apple Watch, Apple Health, ResearchKit, or Apple-collected health/activity/sensor data is central to a newly published or materially updated study, requiring both an Apple health data/product anchor and a research/study anchor; do not include generic sleep tips, wellness guides, or app usage advice.
- Apple messaging-platform and third-party Apple-platform availability stories when they include a concrete Apple platform/action anchor: Apple Messages for Business, iMessage, or Messages capability changes must combine a concrete Apple messaging-platform anchor, an AI agent/assistant or similar capability anchor, and a positive approval, integration, or availability action, and must not be promoted when that context is negated, such as "not integrated with iMessage" or "没有接入 iMessage". Third-party app, service, carrier offer, or utility availability on an Apple platform or App Store remains `weak` unless Apple approval, Apple platform policy, Apple interoperability, or a direct Apple product/service change makes it stronger.

Exclude:

- Deals, coupons, affiliate roundups, routine buying guides, how-to/tutorial content.
- Opinion-only commentary without new facts.
- Podcast/newsletter episodes unless the article adds new reporting.
- Reviews and hands-on articles unless they disclose a new product fact or policy.
- Simple rewrites or reposts without new details.

Do not let exclusion rules hide a clear Apple-subject event. Competitor, third-party, or partner names in the body should not by themselves weaken or exclude a story whose main subject and lead action is about Apple OS/platform changes, Apple services, Apple official accessories, Apple legal actions, Apple developer tools, or Apple ecosystem interoperability, even when the article supplies Google, Samsung, Meta, Amazon, or other market background. Keep the existing exclusions for routine deals, affiliate roundups, and non-Apple product stories, but include official Apple Card, Apple Pay, App Store, Apple services, and Apple retail/customer acquisition promotions when they reveal a new or materially changed Apple business offer; these are service/business news, not ordinary affiliate deals, and summaries should include value, eligibility, timing, source confidence, and unresolved terms.

Do not promote third-party or competitor comparison/marketing stories just because they mention an Apple product, Apple chip-like model string, Apple-like ambiguous term, benchmark result, or macOS/iOS compatibility. Bare model names such as `M3` or `C1` only count as Apple anchors when the surrounding context clearly identifies Apple silicon or an Apple product; `Swift` only counts as an Apple anchor when the surrounding context clearly identifies Apple's programming language, developer tools, or Apple platform development. Rival marketing, buying advice, `vs`/comparison pieces, benchmark/performance comparisons where Apple chips or products are only reference points, hands-on reviews, weekly recaps, generic consumer-electronics safety stories, and third-party XR or smart-glasses stories using Apple, iPhone, or Vision Pro mainly as market comparison should remain `weak` unless they contain a new Apple action, direct Apple policy/platform change, Apple Vision product-roadmap news, or concrete Apple ecosystem interoperability. These comparison items must not merge into direct Apple hardware, pricing, or supply-chain events.

Marketing language should not override material first-party hardware news. Apple or Beats unreleased hardware sightings are eligible hardware/product events when the report includes concrete product details such as model or product-line clues, FCC/certification records, design or color changes, availability or release timing, or other hardware facts. Pure ads, celebrity campaigns, social posts, sponsorships, and commercial promos that lack those product details remain excluded or `weak`.

Routine third-party accessory or consumer-electronics stories that only mention Apple-platform compatibility, such as a dock, charger, hub, monitor, keyboard, or other accessory supporting macOS, iOS, iPhone, iPad, or Mac, should remain `weak` unless the article's subject is Apple/Beats hardware, an official Apple accessory, an unreleased first-party hardware detail, Apple Store availability, Apple certification/policy, or a direct Apple platform action. Do not let these compatibility mentions merge with unrelated OS, security, or support-document events.

During fact extraction, remove article-tail service affiliate blocks and related-link headline clusters before summarization. Examples include Apple service price rows such as `Apple Music - $10.99/mo after free trial`, short title-only related links, site breadcrumb/ICP boilerplate, and same-site recommendation titles. These fragments can mention Apple products and numbers, but they should not create facts, classifications, or event merges.

## Relevance Tiers

Keep candidate discovery broad. After detail-page verification, classify events by relevance tier:

- `strong`: direct Apple product, service, platform, retail, research, legal, regulatory, supply-chain, security, or company action.
- `ecosystem`: third-party or competitor action with a concrete Apple ecosystem effect, such as AirDrop/Quick Share interoperability or direct App Store platform compatibility.
- `weak`: Apple is mainly used as context, comparison, or device target, such as routine third-party Vision Pro apps, competitor hardware comparisons, or unrelated non-Apple apps.
- Local AI apps, third-party utilities, or competitor services that merely run on iPhone, iPad, or Mac should remain `weak` unless the article describes a direct Apple platform change, Apple approval/integration, or concrete Apple ecosystem interoperability.
- Third-party apps/services that are simply listed on or compatible with an Apple platform should be retained for JSON traceability as `weak`, not promoted into the final brief by default.
- Third-party accessories or consumer-electronics products that only cite Apple-platform compatibility should also remain `weak`; keep them in JSON traceability, but do not promote them into the final brief as Apple hardware news unless a direct Apple/Beats or Apple-platform action is the subject.

Final Markdown briefs include `strong` and `ecosystem` events. `weak` events may remain in JSON `deferred_events` for inspection so broad coverage is preserved without adding low-value items to the brief.

## Event-Level Merge Rules

Use crawler event groups as the starting point, then merge or split by the same standard used for the final brief. Treat each eligible JSON `event.id` as a hard boundary by default: one event becomes one bullet, and separate events must not be recombined with transition phrases such as `另有`, `同时`, `同一轮更新`, or `同属` merely to shorten the brief.

Merge articles or final bullets only after source review shows duplicate coverage of the same core subject and action: the same product, app, service, content title, ranking/chart, playlist, subscription offer, component, feature, policy, legal/company move, hardware item, region rollout, or official announcement. Shared Apple context, OS version, WWDC timing, product family, Apple Intelligence theme, source timing, broad event kind, generic Apple TV/Apple Music/Apple One service context, or generic terms such as Apple, App Store, developer, legal, regulation, Vision Pro, or AI are never enough.

Split a group before writing when it has `merge_warnings`, mixed event kinds or relevance tiers, incompatible regions, multiple primary subjects, multiple concrete actions, or a broad recap article bridging specific reports. Use source titles and `key_facts` to assign facts to separate events.

For Apple Messages for Business or iMessage AI-agent stories, merge cross-source coverage only when the stories share a specific entity such as Poke, or when they share the messaging-platform anchor plus AI-agent and approval/integration action anchors. Do not merge those stories with generic local AI apps or third-party tools just because they mention iPhone, Mac, AI, or Messages in passing.

For Vision Pro stories where Apple's headset is the core tool behind a third-party professional, enterprise, medical, training, theme-park, or spatial/immersive experience, preserve the concrete project or venue as the event subject. Merge cross-source coverage that shares the same project/entity, but do not merge it with unrelated Vision Pro rumors, Apple hardware sightings, Beats/headphone stories, or other items merely because they share Apple, Vision Pro, publication timing, or generic action words.

Preserve granular events during high-volume WWDC, OS-preview, and roadmap windows. Built-in apps, OS components, platform APIs, developer tools, service/content items, hardware rumors, regional rollouts, compatibility lists, feature lists, security/support-document changes, and third-party accessory compatibility stories stay separate when their concrete action differs. For example, Mail search, Weather forecasts, Safari browser features, Messages drawing/Markup changes, Notes features, Shortcuts generation, Recovery mode, Apple Wallet, Xcode integration, Apple TV Remote, App Store subscriptions, Apple TV season renewals, Apple Music playlists, Apple One or credit-card offers, watchOS app removal, iOS input-method changes, CarPlay route-sharing APIs, Terminal paste protection, device color/mockup rumors, and Beats/headphone hardware sightings are separate topics unless the sources explicitly report one combined change. Hardware roadmap items also stay split by concrete product and action: iPhone Air successor timing, foldable iPhone render leaks, iPhone Pro design rumors, future device testing lists, component changes, and tag/list pages must not merge solely because they share Apple, iPhone, future-year, or roadmap context.

If the brief is long, condense wording inside each event bullet. Never shorten the brief by creating theme bullets that span independent JSON events, and never drop concrete details from `title`, `summary`, or `key_facts`.

Before extracting summary and key facts, remove source-tail affiliate recommendation blocks that follow the real article body. Common anchors include `My favorite Apple accessory recommendations`, `Worth checking out on Amazon`, `Chance's favorites`, `Official Apple Store on Amazon`, `Amazon Prime Day`, `Best Apple Watch and iPhone accessories`, and `Best ... accessories/deals`. Do not remove the actual body before those anchors.

Use the earliest precise public timestamp among merged articles to decide whether the event is inside the 24-hour window. If a later article has a clearly timestamped `Update:` with substantive new information, treat that update as a new candidate event.

## Final Brief Style

- Chinese output.
- Two sections only: `软件与系统`, `硬件与产品`.
- Each item should integrate important details into readable prose.
- Use each event's `key_facts` before writing the brief; they are mandatory source material extracted generically from numeric paragraphs, list items, tables, and feature lists, not optional background. Preserve material enumerations from official sources, including fraud/safety report figures, App Store review counts, eligible countries or regions, device model lists, feature names, terms, dates, rollout limits, localized features, input methods, regional rollouts, compatibility lists, feature lists, and other implementation details surfaced in `title`, `summary`, or `key_facts`; compress phrasing when needed, but do not collapse the list into a vague summary.
- Coverage comes before brevity: include every eligible event, not just a hand-picked top set. Treat JSON `events` as an eligible-event queue and as the default unit for final bullets, not as loose source material for freeform recombination; a smaller event that has a concrete Apple product, system, service, local-language, regional-availability, developer-platform, privacy/security, health/accessibility, or built-in-app change must still appear in the final brief when it passed inclusion. Do not drop eligible granular events just because a same-day major OS, WWDC, service, or platform story is more prominent; when volume is high, shorten wording within each event's bullet instead of combining independent events into broad theme paragraphs.
- Prefer 3-5 substantial Chinese sentences per item when source detail supports it.
- Source links go only at the end of each item: `（来源：[MacRumors](...), [9to5Mac](...)）`
- Retain any source link that contributes independent facts, feature lists, compatibility details, implementation details, local context, or materially different framing unless another retained source fully duplicates those same details.
- Do not append diagnostics, methodology notes, source-by-source explanations, run status, network permission notes, cache paths, memory-update status, event-grouping/debug judgments, or any other operational note. When you split a mixed or suspicious cluster, write the resulting item as a clean standalone news brief; never say it was `mismerged`, `mistakenly merged`, `被误并入`, `误聚类`, or similar.
