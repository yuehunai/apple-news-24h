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
- Apple services: Apple Music, TV+, Arcade, iCloud, Apple One, App Store, Apple Pay, Apple Card, Apple Intelligence, Siri.
- Hardware and accessories: iPhone, iPad, Mac, Apple Watch, AirPods, Vision Pro, HomePod, official accessories, Apple silicon, modems, displays, cameras, supply-chain production shifts.
- Health/accessibility features and country availability changes.
- Company actions tied to Apple products/services, including legal, regulatory, donations, partnerships, executive changes, retail/product availability, and regional business moves.
- WWDC-related events when they pass the normal relevance and time-window rules, including keynote, schedule, OS-preview, developer, Apple executive, attendee gift/swag, badge, sticker, Developer app, mascot, and official conference-material stories. Do not downgrade or omit them merely because they look light, promotional, or less important than product rumors.
- Apple research disclosures where Apple publishes, presents, previews, or showcases research papers/studies at a recognized technical or academic venue. Require concrete anchors such as research, paper, study, CVPR, computer vision, or equivalent Chinese terms; generic AI strategy or WWDC positioning is not enough by itself.
- Medical or health research where Apple Watch, Apple Health, ResearchKit, or Apple-collected health/activity/sensor data is central to a newly published or materially updated study. Require both an Apple health data/product anchor and a research/study anchor; do not include generic sleep tips, wellness guides, or app usage advice.
- Apple Messages for Business, iMessage, or Messages platform capability changes when the story combines a concrete Apple messaging-platform anchor, an AI agent/assistant or similar capability anchor, and a positive approval, integration, or availability action. Do not promote stories where that platform/action context is negated, such as "not integrated with iMessage" or "没有接入 iMessage".

Exclude:

- Deals, coupons, affiliate roundups, routine buying guides, how-to/tutorial content.
- Opinion-only commentary without new facts.
- Podcast/newsletter episodes unless the article adds new reporting.
- Reviews and hands-on articles unless they disclose a new product fact or policy.
- Simple rewrites or reposts without new details.

Exception: include official Apple Card, Apple Pay, App Store, Apple services, and Apple retail/customer acquisition promotions when the story reveals a new or materially changed Apple business offer. These are service/business news, not ordinary affiliate deals, and summaries should include value, eligibility, timing, source confidence, and unresolved terms.

## Relevance Tiers

Keep candidate discovery broad. After detail-page verification, classify events by relevance tier:

- `strong`: direct Apple product, service, platform, retail, research, legal, regulatory, supply-chain, security, or company action.
- `ecosystem`: third-party or competitor action with a concrete Apple ecosystem effect, such as AirDrop/Quick Share interoperability or direct App Store platform compatibility.
- `weak`: Apple is mainly used as context, comparison, or device target, such as routine third-party Vision Pro apps, competitor hardware comparisons, or unrelated non-Apple apps.
- Local AI apps, third-party utilities, or competitor services that merely run on iPhone, iPad, or Mac should remain `weak` unless the article describes a direct Apple platform change, Apple approval/integration, or concrete Apple ecosystem interoperability.

Final Markdown briefs include `strong` and `ecosystem` events. `weak` events may remain in JSON `deferred_events` for inspection so broad coverage is preserved without adding low-value items to the brief.

## Event-Level Merge Rules

Merge articles when they describe the same core event:

- Same product/function/service plus same action, such as release, rollout, expansion, legal action, production test, policy change.
- Same version number or country rollout.
- Same original report repeated by other outlets with little added information.

Do not merge articles solely because they share generic tokens such as Apple, App Store, developer, legal, or regulation. When event kind or region-specific markers conflict, keep the articles as separate events and surface `merge_warnings` in JSON if a grouped event still looks mixed.

For Apple Messages for Business or iMessage AI-agent stories, merge cross-source coverage only when the stories share a specific entity such as Poke, or when they share the messaging-platform anchor plus AI-agent and approval/integration action anchors. Do not merge those stories with generic local AI apps or third-party tools just because they mention iPhone, Mac, AI, or Messages in passing.

Use the earliest precise public timestamp among merged articles to decide whether the event is inside the 24-hour window. If a later article has a clearly timestamped `Update:` with substantive new information, treat that update as a new candidate event.

## Final Brief Style

- Chinese output.
- Two sections only: `软件与系统`, `硬件与产品`.
- Each item should integrate important details into readable prose.
- Use each event's `key_facts` before writing the brief. These facts are extracted generically from numeric paragraphs, list items, tables, and feature lists; they are not optional background.
- Preserve material enumerations from official sources. Examples of enumeration types include fraud/safety report figures, App Store review counts, eligible countries or regions, device model lists, feature names, terms, dates, and rollout limits. Compress phrasing when needed, but do not collapse the list into a vague summary.
- Coverage comes before brevity: include every eligible event, not just a hand-picked top set.
- Treat JSON `events` as an eligible-event queue, not as a ranking of top stories. A smaller event that has a concrete Apple product, system, service, local-language, regional-availability, developer-platform, privacy/security, health/accessibility, or built-in-app change must still appear in the final brief when it passed inclusion.
- Do not drop eligible granular events just because a same-day major OS, WWDC, service, or platform story is more prominent. When volume is high, combine related events into one fuller bullet with distinct subfacts, but preserve each event's concrete change and source link.
- If compressing a long brief, merge adjacent eligible events by shared product/version/theme instead of removing localized features, input methods, regional rollouts, compatibility lists, feature lists, or other implementation details surfaced in `title`, `summary`, or `key_facts`.
- Prefer 2-4 substantial Chinese sentences per item when source detail supports it.
- Source links go only at the end of each item: `（来源：[MacRumors](...), [9to5Mac](...)）`
- Retain any source link that contributes independent facts, feature lists, compatibility details, implementation details, local context, or materially different framing unless another retained source fully duplicates those same details.
- Do not append diagnostics, methodology notes, source-by-source explanations, run status, network permission notes, cache paths, or memory-update status.
