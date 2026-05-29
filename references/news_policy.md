# Apple 24-Hour News Policy

## Sources

Primary English sources:

- MacRumors: `https://feeds.macrumors.com/MacRumors-All`
- 9to5Mac: `https://9to5mac.com/feed/`
- AppleInsider: `https://appleinsider.com/rss/news/`
- The Verge: `https://www.theverge.com/rss/index.xml`, plus Apple channel pages when RSS is sparse
- Apple Newsroom: `https://www.apple.com/newsroom/rss-feed.rss`

Primary Chinese sources:

- IT之家: `https://www.ithome.com/rss/`
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

## Cache Handling

The script cache is only for inspecting the current run's successful HTTP responses. By default, the crawler uses `apple-news-24h` under Python's platform temporary directory, clears the directory at startup, and writes a marker file plus fresh responses. For automation runs, write the full JSON result with a fixed `--output` path; the script writes this file after cache cleanup and uses atomic replacement. Use `--cache-dir` when an automation needs a predictable cache location. Do not read old cache files as source material or use cache contents to decide whether an event is inside the current 24-hour window.

## Inclusion Rules

Keep new or materially updated news about:

- OS releases, beta/RC updates, security fixes, vulnerabilities, enterprise fixes, platform policy changes.
- Apple services: Apple Music, TV+, Arcade, iCloud, Apple One, App Store, Apple Pay, Apple Card, Apple Intelligence, Siri.
- Hardware and accessories: iPhone, iPad, Mac, Apple Watch, AirPods, Vision Pro, HomePod, official accessories, Apple silicon, modems, displays, cameras, supply-chain production shifts.
- Health/accessibility features and country availability changes.
- Company actions tied to Apple products/services, including legal, regulatory, donations, partnerships, executive changes, retail/product availability, and regional business moves.
- Apple research disclosures where Apple publishes, presents, previews, or showcases research papers/studies at a recognized technical or academic venue. Require concrete anchors such as research, paper, study, CVPR, computer vision, or equivalent Chinese terms; generic AI strategy or WWDC positioning is not enough by itself.
- Medical or health research where Apple Watch, Apple Health, ResearchKit, or Apple-collected health/activity/sensor data is central to a newly published or materially updated study. Require both an Apple health data/product anchor and a research/study anchor; do not include generic sleep tips, wellness guides, or app usage advice.

Exclude:

- Deals, coupons, affiliate roundups, routine buying guides, how-to/tutorial content.
- Opinion-only commentary without new facts.
- Podcast/newsletter episodes unless the article adds new reporting.
- Reviews and hands-on articles unless they disclose a new product fact or policy.
- Simple rewrites or reposts without new details.

Exception: include official Apple Card, Apple Pay, App Store, Apple services, and Apple retail/customer acquisition promotions when the story reveals a new or materially changed Apple business offer. These are service/business news, not ordinary affiliate deals, and summaries should include value, eligibility, timing, source confidence, and unresolved terms.

## Event-Level Merge Rules

Merge articles when they describe the same core event:

- Same product/function/service plus same action, such as release, rollout, expansion, legal action, production test, policy change.
- Same version number or country rollout.
- Same original report repeated by other outlets with little added information.

Use the earliest precise public timestamp among merged articles to decide whether the event is inside the 24-hour window. If a later article has a clearly timestamped `Update:` with substantive new information, treat that update as a new candidate event.

## Final Brief Style

- Chinese output.
- Two sections only: `软件与系统`, `硬件与产品`.
- Each item should integrate important details into readable prose.
- Use each event's `key_facts` before writing the brief. These facts are extracted generically from numeric paragraphs, list items, tables, and feature lists; they are not optional background.
- Preserve material enumerations from official sources. Examples of enumeration types include fraud/safety report figures, App Store review counts, eligible countries or regions, device model lists, feature names, terms, dates, and rollout limits. Compress phrasing when needed, but do not collapse the list into a vague summary.
- Coverage comes before brevity: include every eligible event, not just a hand-picked top set.
- Prefer 2-4 substantial Chinese sentences per item when source detail supports it.
- Source links go only at the end of each item: `（来源：[MacRumors](...), [9to5Mac](...)）`
- Do not append diagnostics, methodology notes, or source-by-source explanations.
