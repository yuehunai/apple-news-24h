# Collection and source coverage

Use only the relevant section for a collection failure, publication-time dispute or manual fallback. Normal drafting does not require this file.

## Sources

The crawler uses nine primary sources. Check a failed source through its own public discovery paths; do not substitute unrelated stories.

| Source | Discovery paths | Default timezone |
| --- | --- | --- |
| MacRumors | `https://feeds.macrumors.com/MacRumors-All`, homepage and its published chronological next-page links | America/Los_Angeles |
| 9to5Mac | `https://9to5mac.com/feed/`, `https://9to5mac.com/wp-json/wp/v2/posts` | America/Los_Angeles |
| AppleInsider | `https://appleinsider.com/rss/news/`, news listing | America/New_York |
| The Verge | `https://www.theverge.com/rss/index.xml`, `https://www.theverge.com/rss/apple/index.xml`, Apple and Tech channel pages | America/New_York |
| Apple Newsroom | `https://www.apple.com/newsroom/rss-feed.rss` | America/Los_Angeles |
| IT之家 | `https://www.ithome.com/rss/`, `https://www.ithome.com/apple/`, `https://www.ithome.com/tags/%E8%8B%B9%E6%9E%9C/`, public dated news calendar | Asia/Shanghai |
| 爱范儿 | `https://www.ifanr.com/feed`, `http://live.ifanr.com/feed` | Asia/Shanghai |
| 快科技 | `https://rss.mydrivers.com/opml.xml`, homepage, Apple and consumer-electronics category lists | Asia/Shanghai |
| cnBeta | `https://www.cnbeta.com.tw/backend.php` | Asia/Shanghai |

Use explicit page offsets/ISO timestamps ahead of these defaults. Supplemental mainstream Chinese sources such as 新浪科技/财经、网易科技、36氪 may recover a primary-source story whose page is unavailable; preserve their actual URL and attribution.

## Window and publication

Each invocation fixes a fresh current time `T` and the interval `(T - hours, T]`. Compare reliable publication times in UTC; display the requested or detected local timezone. Do not move this window during review.

Use publisher-owned article publication metadata, an article-scoped time element or another source-specific publication field. Listing/card/feed timestamps guide discovery and can be a marked fallback when detail publication is unavailable. A modified timestamp, event/preorder date in prose, sidebar date or video upload time is not article publication. Apple Newsroom requires its own publication date; do not substitute modified, video-upload or feed-update timestamps. A reliable date-only Newsroom value is lower precision, not an invented time of day.

The action's date and the article's date serve different purposes: a current report can cover an older ongoing action. A recap does not become a new action merely through republication. Do not redetermine a merged report's window from a background date or an old linked source. Preserve substantive explicitly dated updates as updates, without treating arbitrary page modification as news.

## Source coverage

A completed empty or suspiciously sparse first result requires the same crawler command rerun with network approval. If still sparse, use `--include-diagnostics` to inspect source/detail counts, `failed_sources`, `failed_fetches` and `low_confidence_articles`. Healthy sources can legitimately produce no eligible items.

Read `collection_warnings` even in a nonempty result. A failed source or failed primary discovery paths remain unconfirmed even if a supplementary archive supplies some articles. HTTP 200 or an empty parsed listing does not establish that the window contains no news. A complete traversal needs dated chronological rows through the window start; failed, repeated, unordered or truncated pages leave coverage unconfirmed. A recovered alternate path does not prove the publisher indexes every accessible article.

- **MacRumors:** follow only the article list's published same-site numeric continuation pages. Match each card to its own title, first substantive paragraph and date; sidebar dates cannot establish traversal.
- **IT之家:** follow the tag page's actual pagination protocol. Before reaching the window start, retry an empty successful response once; if still unconfirmed, the public calendar can recover consecutive dated pages. Its index must match the fixed window end in the source timezone. Empty/stale/unordered/budget-truncated pages are not proof of coverage. The homepage likewise gets one retry after an empty parsed response. Keep any remaining limitation visible.
- **快科技:** OPML subfeeds and category body lists complement rotating sidebars. Follow the published cursor/page protocol through dated rows. Article publication metadata takes precedence over dates in its prose.
- **The Verge:** article links must use their own structured list object's publication time and description, not related-card or modification fields.
- **AppleInsider:** news articles, including nested tips/reviews, undergo normal screening; product hubs, video indexes and price catalogs are navigation. A browser-accessible page can still fail crawler retrieval. Inspect capture status and recover the needed text through an available public page without fabricating successful collection.

Candidate discovery is broader than eligibility. A short first-party product headline does not need an RSS summary or a particular action verb to merit detail inspection. Navigation pages, price catalogs and periodic publisher roundup indexes are not standalone articles. Deduplicate candidates before applying the crawler's existing budgets; do not change limits, concurrency or retry settings during a brief run.

## Fallback

For a specific gap, try the source feed/listing, published category/date archive or public API, then a domain-and-date search, then a relevant supplemental source. Check actual publication times within the fixed window. A card or excerpt must retain its own source identity; neighboring text cannot complete it. When full text remains unavailable, use supported captured facts and record the gap in working notes. Do not fill a missing source with weak content or old news.

If the crawler itself is unavailable, collect manually with the same fixed window and policy. Save source URLs, publication times/timezones, reporting subjects, material facts and decisions as Markdown evidence. Do not fabricate crawler JSON. Complete the same eligibility, grouping and writing checks before returning the brief.

## Cache and output

Every invocation collects anew. The crawler clears its managed cache at startup; cached responses are diagnostic evidence, not proof of freshness for a later run. Follow the script's current cache default (`tempfile.gettempdir()/apple-news-24h`) or an explicit invocation path; never assume a fixed `/tmp` location.

Wait for actual process completion and read this invocation's saved JSON, not stdout, an old file or a scaffold. Cover all events and required fragments through focused reads; there is no requirement to print the entire JSON at once. Store working records and checked paragraphs beside the current output. Keep collection limitations in notes, not the final news bullets.
