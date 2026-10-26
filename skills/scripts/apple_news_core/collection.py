"""Collection transport, cache, and detail recall; no final event decisions."""
from __future__ import annotations
from dataclasses import replace
from functools import lru_cache
import html
import concurrent.futures
from html.parser import HTMLParser
import hashlib
import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
import json
import re
import shutil
import ssl
import time
import urllib.parse
import xml.etree.ElementTree as ET
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from .article_processing import strip_tags
from .models import Candidate, Source, FetchSettings, ReconciliationProfile
from .event_identity import PRODUCT_PATTERNS, high_confidence_direct_apple_action, _compiled_rule


def limit_page_candidates(candidates: list[Candidate], limit: int,
                          eligible: Callable[[Candidate], bool]) -> list[Candidate]:
    """Spend a crowded page's budget on eligible discovery before filler.

    Eligibility grants detail inspection, not a relevance tier. Keep page order
    and the existing cap; unrelated links cannot hide later eligible reports.
    """
    if len(candidates) <= limit:
        return candidates
    selected, remainder = [], []
    for index, candidate in enumerate(candidates):
        (selected if eligible(candidate) else remainder).append(index)
        if len(selected) == limit:
            break
    indices = sorted((selected + remainder)[:limit])
    return [candidates[index] for index in indices]


class _ListingLeadParser(HTMLParser):
    """Read the first text paragraph inside one card's content container."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.owner_depth = 0
        self.paragraph = None
        self.summary = ''
        self.closed = False

    def handle_starttag(self, tag, attrs):
        if self.closed or self.summary:
            return
        if tag == 'div':
            self.owner_depth += 1
            if self.depth:
                self.depth += 1
            elif 'js-contentInner' in dict(attrs).get('class', '').split():
                self.depth = 1
        if tag == 'p' and self.depth:
            self.paragraph = []

    def handle_data(self, data):
        if self.depth and self.paragraph is not None:
            self.paragraph.append(data)

    def handle_endtag(self, tag):
        if self.closed:
            return
        if tag == 'p' and self.paragraph is not None:
            text = ' '.join(''.join(self.paragraph).split())
            if text and not self.summary:
                self.summary = text[:1200]
            self.paragraph = None
        if tag == 'div' and self.depth:
            self.depth -= 1
            if not self.depth:
                self.closed = True
                self.paragraph = None
        if tag == 'div' and self.owner_depth:
            self.owner_depth -= 1
            if not self.owner_depth:
                self.closed = True
                self.paragraph = None


def supplement_macrumors_index_candidates(
    page_url: str, first_text: str | None, first_candidates: list[Candidate],
    window_start: datetime | None, limit: int,
    fetch_page: Callable[[str], str | None],
    parse_page: Callable[[str, str], list[Candidate]],
    parse_time: Callable[[str], datetime | None], diagnostics: dict[str, Any],
) -> list[Candidate]:
    """Follow the index's next links until its dated articles cover the window.

    Sidebar dates and links inside articles cannot establish list coverage.
    Keep the existing page candidate budget, including first-page discoveries.
    """
    parts = urllib.parse.urlsplit(page_url)
    if (window_start is None or parts.hostname not in {'www.macrumors.com', 'macrumors.com'}
            or parts.path not in {'', '/'}):
        return []
    current_url, body = page_url, first_text
    seen, visited = {c.url for c in first_candidates}, {page_url}
    extra, pages, reason = [], 0, 'candidate-budget'
    while True:
        if body is None:
            reason = 'request-failed'
            break
        body = _compiled_rule(r'<(script|style)\b[^>]*>.*?</\1\s*>', re.I | re.S).sub('', body)
        main = _compiled_rule(r'<main\b[^>]*>(.*?)</main>', re.I | re.S).search(body)
        content, rows = main.group(1) if main else '', []
        cards = list(_compiled_rule(r'<article\b[^>]*>.*?</article>', re.I | re.S).finditer(content))
        for card in cards:
            heading = _compiled_rule(r'<h[1-3]\b[^>]*>.*?</h[1-3]>', re.I | re.S).search(card.group())
            stamp = _compiled_rule(r'''<time\b[^>]*datetime\s*=\s*['"]([^'"]+)''', re.I).search(card.group())
            links = parse_page(heading.group(), current_url) if heading else []
            if links:
                summary = ''
                owned = _compiled_rule(r'''<div\b[^>]*data-io-article-url\s*=\s*['"]([^'"]+)['"][^>]*>''', re.I).search(card.group())
                if owned and urllib.parse.urljoin(current_url, html.unescape(owned.group(1))) == links[0].url:
                    parser = _ListingLeadParser()
                    parser.feed(card.group()[owned.start():])
                    summary = parser.summary
                rows.append(replace(links[0], summary=summary,
                                    feed_time_raw=html.unescape(stamp.group(1)) if stamp else '',
                                    publication_time_raw=html.unescape(stamp.group(1)) if stamp else ''))
        if not rows:
            reason = 'empty-page'
            break
        new = [c for c in rows if c.url not in seen]
        if pages and not new:
            reason = 'no-progress'
            break
        complete = len(new) <= max(0, limit - len(seen))
        for candidate in rows:
            if candidate.url in seen or len(seen) < limit:
                extra.append(candidate)
                seen.add(candidate.url)
        dates = [parse_time(c.feed_time_raw) for c in rows]
        if (complete and len(rows) == len(cards) and all(d is not None and d.utcoffset() is not None for d in dates)
                and all(a >= b for a, b in zip(dates, dates[1:])) and dates[-1] <= window_start):
            reason = 'window-covered'
            break
        if not complete or len(seen) >= limit:
            break
        next_url = None
        outside_articles = _compiled_rule(r'<article\b[^>]*>.*?</article>', re.I | re.S).sub('', content)
        navigation = ' '.join(m.group() for m in _compiled_rule(r'<nav\b[^>]*>.*?</nav>', re.I | re.S).finditer(outside_articles))
        for anchor in _compiled_rule(r'<a\b[^>]*>', re.I).finditer(navigation):
            rel = _compiled_rule(r'''\brel\s*=\s*['"]([^'"]+)''', re.I).search(anchor.group())
            href = _compiled_rule(r'''\bhref\s*=\s*['"]([^'"]+)''', re.I).search(anchor.group())
            if not rel or 'next' not in rel.group(1).lower().split() or not href:
                continue
            url = urllib.parse.urljoin(current_url, html.unescape(href.group(1)))
            target = urllib.parse.urlsplit(url)
            if (target.scheme == parts.scheme and target.netloc == parts.netloc
                    and _compiled_rule(r'/[1-9]\d*/').fullmatch(target.path)
                    and not target.query and not target.fragment and url not in visited):
                next_url = url
                break
        if next_url is None:
            reason = 'pagination-unavailable'
            break
        visited.add(next_url)
        current_url, body = next_url, fetch_page(next_url)
        pages += 1
    diagnostics.setdefault('source_listing_pagination', {})[page_url] = {
        'additional_pages': pages, 'additional_candidates': len(seen) - len({c.url for c in first_candidates}),
        'stop_reason': reason,
    }
    if reason != 'window-covered':
        diagnostics.setdefault('collection_warnings', []).append({
            'source': 'MacRumors', 'url': page_url, 'reason': reason, 'coverage': 'unconfirmed',
        })
    return extra


def supplement_ithome_tag_candidates(
    page_url: str, first_text: str | None, first_candidates: list[Candidate],
    window_start: datetime | None, limit: int,
    fetch_page: Callable[[str], str | None],
    parse_page: Callable[[str, str], list[Candidate]],
    parse_time: Callable[[str], datetime | None], diagnostics: dict[str, Any],
) -> list[Candidate]:
    """Follow the published tag-list protocol within the existing page budget."""
    parts = urllib.parse.urlsplit(page_url)
    if (window_start is None or parts.hostname not in {'www.ithome.com', 'ithome.com'}
            or not parts.path.startswith('/tags/')):
        return []
    keyword = urllib.parse.unquote(parts.path[len('/tags/'):].strip('/'))
    if not keyword or '/' in keyword:
        return []
    rows, extra = first_candidates, []
    seen = {c.url for c in rows}
    page, reason = 0, 'candidate-budget'
    request_attempts, empty_page_retries, last_page_count = 0, 0, None
    complete_page = True

    def covers_window(page_rows: list[Candidate]) -> bool:
        dates = []
        for candidate in page_rows:
            value = parse_time(candidate.feed_time_raw)
            if value is not None and value.utcoffset() is not None:
                dates.append(value)
        # A pinned or unordered old item must not prematurely end discovery.
        return bool(dates and len(dates) == len(page_rows)
            and all(a >= b for a, b in zip(dates, dates[1:])) and dates[-1] <= window_start)

    protocol_available = bool(first_text and '/category/tagpage?' in first_text)
    if not protocol_available:
        reason = ('request-failed' if first_text is None else
                  'window-covered' if covers_window(rows) else 'pagination-unavailable')
    while protocol_available and len(seen) < limit:
        if covers_window(rows):
            reason = 'window-covered'
            break
        page += 1
        endpoint = urllib.parse.urlunsplit((parts.scheme, parts.netloc, '/category/tagpage',
            urllib.parse.urlencode({'keyword': keyword, 'page': page}), ''))
        rows = []
        for attempt in range(2):
            request_attempts += 1
            response = fetch_page(endpoint)
            if response is None:
                reason = 'request-failed'
                break
            try:
                payload = json.loads(response)
                content = payload['content']
                if payload.get('success') is not True or not isinstance(content.get('html'), str):
                    raise ValueError('invalid listing response')
            except (ValueError, KeyError, TypeError, AttributeError):
                reason = 'invalid-response'
                break
            last_page_count = content.get('count')
            # The endpoint can transiently return success with no list before
            # the window is covered. Re-fetch once without advancing the page.
            if attempt == 0 and last_page_count == 0 and not content['html'].strip():
                empty_page_retries += 1
                time.sleep(0.5)
                continue
            rows = parse_page(content['html'], endpoint)
            break
        if reason in {'request-failed', 'invalid-response'}:
            break
        if not rows:
            reason = 'empty-page'
            break
        new = [c for c in rows if c.url not in seen]
        if not new:
            reason = 'no-progress'
            break
        remaining = max(0, limit - len(seen))
        complete_page = len(new) <= remaining
        for candidate in new[:remaining]:
            seen.add(candidate.url)
            extra.append(candidate)
    if reason == 'candidate-budget' and complete_page and covers_window(rows):
        reason = 'window-covered'
    diagnostics.setdefault('source_listing_pagination', {})[page_url] = {
        'additional_pages': page, 'additional_candidates': len(extra), 'stop_reason': reason,
        'request_attempts': request_attempts, 'empty_page_retries': empty_page_retries,
        'last_page_count': last_page_count,
    }
    if reason != 'window-covered':
        diagnostics.setdefault('collection_warnings', []).append({
            'source': 'IT之家', 'url': page_url, 'reason': reason, 'coverage': 'unconfirmed',
        })
    return extra


def recover_ithome_calendar_candidates(
    window_start: datetime, limit: int, fetch_page: Callable[[str], str | None],
    parse_page: Callable[[str, str], list[Candidate]],
    parse_time: Callable[[str], datetime | None], diagnostics: dict[str, Any],
    *, window_end: datetime | None = None,
) -> list[Candidate]:
    """Recover an unconfirmed tag/home listing via the site's dated calendar.

    The default calendar contains only the latest rows. Follow its published
    date URL template, consume consecutive complete dated pages and require
    chronological timestamps reaching the window start. Never infer coverage
    from an empty response, an unrelated old link, or a truncated budget.
    """
    root = 'https://www.ithome.com/list/'
    index = fetch_page(root)
    date = _compiled_rule(r'var\s+date\s*=\s*[\x27"](\d{4}-\d{2}-\d{2})[\x27"]').search(index or '')
    protocol = _compiled_rule(r'_LISTPAGE_URL_REG_\s*=\s*[\x27"]\$Y-\$M-\$D\.html[\x27"]').search(index or '')
    day = datetime.strptime(date.group(1), '%Y-%m-%d').date() if date and protocol else None
    result, seen, pages, reason = [], set(), 0, 'pagination-unavailable'
    if day is not None and (window_end is None
            or day != window_end.astimezone(timezone(timedelta(hours=8))).date()):
        day, reason = None, 'stale-calendar-index'
    while day is not None:
        url = root + day.isoformat() + '.html'
        body = fetch_page(url)
        pages += 1
        listing = _compiled_rule(r'<ul\b[^>]*class=[\x27"]datel[\x27"][^>]*>(.*?)</ul>', re.S).search(body or '')
        cards = _compiled_rule(r'<li\b[^>]*>.*?</li>', re.S).findall(listing.group(1)) if listing else []
        if not cards:
            reason = 'request-failed' if body is None else 'empty-page'
            break
        dates, rows = [], []
        for card in cards:
            stamp = _compiled_rule(r'data-ot=[\x27"]([^\x27"]+)[\x27"]').search(card)
            value = parse_time(stamp.group(1)) if stamp else None
            if value is None or value.utcoffset() is None or value.date() != day:
                reason = 'invalid-date'
                break
            dates.append(value)
            if value > window_start:
                rows.extend(replace(c, feed_time_raw=stamp.group(1), publication_time_raw=stamp.group(1))
                            for c in parse_page(card, url))
        if len(dates) != len(cards) or any(a < b for a, b in zip(dates, dates[1:])):
            reason = 'invalid-date-order'
            break
        new = [c for c in rows if c.url not in seen]
        if len(seen) + len({c.url for c in new}) > limit:
            reason = 'candidate-budget'
            break
        for candidate in new:
            if candidate.url not in seen:
                seen.add(candidate.url)
                result.append(candidate)
        if dates[-1] <= window_start:
            reason = 'window-covered'
            break
        day -= timedelta(days=1)
    diagnostics['ithome_calendar_recovery'] = {
        'pages': pages, 'candidates': len(result), 'stop_reason': reason,
    }
    if reason == 'window-covered':
        warnings = diagnostics.get('collection_warnings', [])
        recovered = [w for w in warnings if w.get('source') == 'IT之家']
        diagnostics.setdefault('recovered_listing_warnings', []).extend(recovered)
        diagnostics['collection_warnings'] = [w for w in warnings if w.get('source') != 'IT之家']
    return result


def supplement_mydrivers_category_candidates(
    page_url: str, first_text: str | None, first_candidates: list[Candidate],
    window_start: datetime | None, limit: int,
    fetch_page: Callable[[str], str | None],
    parse_page: Callable[[str, str], list[Candidate]],
    parse_time: Callable[[str], datetime | None], diagnostics: dict[str, Any],
) -> list[Candidate]:
    """Follow a category's dated body list, not its rotating shared sidebar."""
    parts = urllib.parse.urlsplit(page_url)
    if (window_start is None or parts.hostname != 'news.mydrivers.com'
            or parts.path not in {'/pingguo.html', '/jiadianshuma.html'}):
        return []
    selector = _compiled_rule(r'''<input\b[^>]*\bid=['"]hidcld['"][^>]*>''', re.I).search(first_text or '')
    value = _compiled_rule(r'''\bvalue=['"](\d+)['"]''').search(selector.group()) if selector else None
    listing = _compiled_rule(r'''<ul\b[^>]*\bid=['"]newsleft_1['"][^>]*>(.*?)</ul>''', re.I | re.S).search(first_text or '')
    body = listing.group(1) if listing else ''
    seen, extra, pages = {c.url for c in first_candidates}, [], 0
    reason = 'request-failed' if first_text is None else 'pagination-unavailable'
    while value and int(value.group(1)) > 0 and body:
        rows, ids = [], []
        cards = [card for card in _compiled_rule(r'<li\b[^>]*>.*?</li>', re.I | re.S).findall(body)
                 if _compiled_rule(r'news_title_\d+').search(card)]
        for card in cards:
            heading = _compiled_rule(r'<h3\b[^>]*>.*?</h3>', re.I | re.S).search(card)
            stamp = _compiled_rule(r'''<span\b[^>]*\bclass=['"]time['"][^>]*>(.*?)</span>''', re.I | re.S).search(card)
            article_id = _compiled_rule(r'news_title_(\d+)').search(card)
            links = parse_page(heading.group(), page_url) if heading else []
            if links and article_id:
                rows.append(replace(links[0], feed_time_raw=strip_tags(stamp.group(1)) if stamp else '',
                                    publication_time_raw=strip_tags(stamp.group(1)) if stamp else ''))
                ids.append(article_id.group(1))
        new = [c for c in rows if c.url not in seen]
        if not rows or (pages and not new):
            reason = 'empty-page' if not rows else 'no-progress'
            break
        complete = len(new) <= max(0, limit - len(seen))
        for candidate in rows:
            if candidate.url in seen or len(seen) < limit:
                extra.append(candidate)
                seen.add(candidate.url)
        dates = [parse_time(c.feed_time_raw) for c in rows]
        if (complete and len(rows) == len(cards) and all(d is not None and d.utcoffset() is not None for d in dates)
                and all(a >= b for a, b in zip(dates, dates[1:])) and dates[-1] <= window_start):
            reason = 'window-covered'
            break
        if not complete or len(seen) >= limit:
            reason = 'candidate-budget'
            break
        category = int(value.group(1))
        protocol = 'getdatelist20200820.aspx' if category > 1000 else 'getdatelist_search.aspx'
        endpoint = 'https://blog.mydrivers.com/news/' + protocol + '?' + urllib.parse.urlencode({
            'ac': category - 1000 if category > 1000 else category, 'timeks': '', 'timeend': '',
            'page': pages + 2, 'minid': ids[-1], 'callback': 'NewsList'})
        response = fetch_page(endpoint)
        pages += 1
        if response is None:
            reason = 'request-failed'
            break
        wrapped = _compiled_rule(r'\s*NewsList\((.*)\);?\s*', re.S).fullmatch(response)
        try:
            payload = json.loads(wrapped.group(1))['data'][0] if wrapped else None
            body = payload['html']
            if not isinstance(body, str):
                raise ValueError('invalid listing body')
        except (ValueError, KeyError, TypeError, IndexError):
            reason = 'invalid-response'
            break
        if not body.strip():
            reason = 'empty-page'
            break
    diagnostics.setdefault('source_listing_pagination', {})[page_url] = {
        'additional_pages': pages, 'additional_candidates': len(seen) - len({c.url for c in first_candidates}),
        'stop_reason': reason,
    }
    if reason != 'window-covered':
        diagnostics.setdefault('collection_warnings', []).append({
            'source': '快科技', 'url': page_url, 'reason': reason, 'coverage': 'unconfirmed',
        })
    return extra


def price_observation_needs_detail(title: str) -> bool:
    """A reported market direction needs a body check, even beside a subsidy."""
    return bool(_compiled_rule(r'破发|跌破(?:首发|发售|上市)价|below\s+(?:its\s+)?(?:launch|retail)\s+price', re.I).search(title)
                and not _compiled_rule(r'领券|到手价|券后|购买推荐|coupon|buying\s+guide', re.I).search(title))


def market_summary_needs_detail(title: str) -> bool:
    """Market reports may put Apple's observed result only in their body.

    This grants a detail fetch, never relevance or an Apple market result.
    Component prices, individual product shipping and shopping lists are not
    market-result reports.
    """
    if _compiled_rule(r'guide|deals?|coupons?|教程|促销|优惠|选购', re.I).search(title):
        return False
    if (_compiled_rule(r'美股|美国股市|\b(?:s&p\s*500|nasdaq|dow\s+jones|wall\s+street)\b', re.I).search(title)
            and _compiled_rule(r'收[涨跌盘]|齐[涨跌]|指数.{0,12}(?:涨|跌)|\b(?:close[sd]?|rose|fell|slumps?|rall(?:y|ies))\b', re.I).search(title)):
        return True
    return bool(_compiled_rule(r'(?<![a-z0-9])(?:pc|personal computers?|smartphones?|tablets?|wearables?)(?![a-z0-9])|个人电脑|(?:智能)?手机(?:市场)?|平板电脑|可穿戴', re.I).search(title)
        and _compiled_rule(r'\b(?:shipments?|market\s+share|unit\s+sales)\b|出货(?:量)?|市场份额|市占', re.I).search(title))

def is_navigation_url(url: str, source: Source | None = None) -> bool:
    parts = urllib.parse.urlsplit(url)
    if (not parts.path.strip('/')
            or re.search(r"/(?:tags?|categor(?:y|ies))(?:/|$)", parts.path, re.I)
            or (parts.hostname or '').startswith('forums.')):
        return True
    if source is not None:
        for entry in (*source.pages, *source.feeds, *source.wordpress_posts_apis):
            listing = urllib.parse.urlsplit(entry)
            if (parts.hostname, parts.path.rstrip('/')) == (listing.hostname, listing.path.rstrip('/')):
                return True
    return False


def source_article_url_allowed(url: str, source: Source) -> bool:
    """Keep navigation out of article discovery, regardless of link label."""
    if is_navigation_url(url, source):
        return False
    parts = urllib.parse.urlsplit(url)
    if source.name == "AppleInsider":
        # Product hubs and price catalogues are navigation; nested reviews and
        # tips remain article candidates regardless of their eventual tier.
        if parts.hostname == 'prices.appleinsider.com' or _compiled_rule(
                r'/inside(?:/[^/]+(?:/(?:videos|reviews|best|vs))?)?/?$', re.I).fullmatch(parts.path):
            return False
    if source.name != "Apple Newsroom":
        return True
    return (
        parts.scheme in {"http", "https"}
        and parts.hostname in source.domains
        and re.fullmatch(
            r"/(?:[a-z]{2,4}(?:-[a-z]{2})?/){0,2}newsroom/\d{4}/(?:0[1-9]|1[0-2])/[^/]+/?",
            parts.path, re.I,
        ) is not None
    )

def build_sources(now_local: datetime) -> list[Source]:
    dates = [now_local.date(), (now_local - timedelta(days=1)).date()]
    macrumors_pages = ["https://www.macrumors.com/", "https://www.macrumors.com/guide/"]
    nine_pages = ["https://9to5mac.com/"]
    for date in dates:
        macrumors_pages.append(
            f"https://www.macrumors.com/{date.year}/{date.month:02d}/{date.day:02d}/"
        )
        nine_pages.append(f"https://9to5mac.com/{date.year}/{date.month:02d}/{date.day:02d}/")

    return [
        Source(
            name="MacRumors",
            default_tz="America/Los_Angeles",
            feeds=["https://feeds.macrumors.com/MacRumors-All"],
            pages=macrumors_pages,
            domains=("macrumors.com", "www.macrumors.com"),
        ),
        Source(
            name="9to5Mac",
            default_tz="America/Los_Angeles",
            feeds=["https://9to5mac.com/feed/"],
            wordpress_posts_apis=[
                "https://9to5mac.com/wp-json/wp/v2/posts?per_page=100&_embed=wp:term&_fields=link,date_gmt,date,title,excerpt,_links.wp:term,_embedded.wp:term"
            ],
            pages=nine_pages,
            domains=("9to5mac.com",),
        ),
        Source(
            name="AppleInsider",
            default_tz="America/New_York",
            feeds=["https://appleinsider.com/rss/news/"],
            pages=["https://appleinsider.com/news"],
            domains=("appleinsider.com",),
        ),
        Source(
            name="The Verge",
            default_tz="America/New_York",
            feeds=[
                "https://www.theverge.com/rss/index.xml",
                "https://www.theverge.com/rss/apple/index.xml",
            ],
            pages=["https://www.theverge.com/apple", "https://www.theverge.com/tech"],
            domains=("theverge.com", "www.theverge.com"),
        ),
        Source(
            name="Apple Newsroom",
            default_tz="America/Los_Angeles",
            feeds=["https://www.apple.com/newsroom/rss-feed.rss"],
            pages=["https://www.apple.com/newsroom/"],
            domains=("apple.com", "www.apple.com"),
        ),
        Source(
            name="IT之家",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ithome.com/rss/"],
            pages=[
                "https://www.ithome.com/",
                "https://www.ithome.com/apple/",
                "https://www.ithome.com/tags/%E8%8B%B9%E6%9E%9C/",
            ],
            domains=("ithome.com", "www.ithome.com"),
        ),
        Source(
            name="爱范儿",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ifanr.com/feed", "http://live.ifanr.com/feed"],
            pages=["https://www.ifanr.com/"],
            domains=("ifanr.com", "www.ifanr.com", "live.ifanr.com"),
        ),
        Source(
            name="快科技",
            default_tz="Asia/Shanghai",
            feeds=["https://rss.mydrivers.com/opml.xml"],
            pages=["https://news.mydrivers.com/", "https://news.mydrivers.com/pingguo.html",
                   "https://news.mydrivers.com/jiadianshuma.html"],
            domains=("mydrivers.com", "news.mydrivers.com", "www.mydrivers.com"),
        ),
        Source(
            name="cnBeta",
            default_tz="Asia/Shanghai",
            feeds=["https://www.cnbeta.com.tw/backend.php"],
            pages=["https://www.cnbeta.com.tw/"],
            domains=("cnbeta.com.tw", "www.cnbeta.com.tw"),
        ),
    ]


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@contextmanager
def run_resource_locks(cache_dir: Path, output_paths: tuple[Path, ...]):
    """Fail immediately on overlapping local run resources; never queue runs."""
    import fcntl
    cache = cache_dir.expanduser().resolve(strict=False)
    targets = {cache}
    for path in output_paths:
        expanded = path.expanduser()
        targets.add(expanded.resolve(strict=False))
        targets.add(expanded.with_name(f".{expanded.name}.tmp").resolve(strict=False))
    lock_root = Path(tempfile.gettempdir()) / f"apple-news-24h-run-locks-{os.getuid()}"
    canonical_locks = lock_root.resolve(strict=False)
    if (cache == canonical_locks or cache in canonical_locks.parents
            or any(canonical_locks == path or canonical_locks in path.parents for path in targets)):
        raise RuntimeError("Run resources overlap the external lock directory")
    if lock_root.is_symlink():
        raise RuntimeError("Refusing a symlinked run lock directory")
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Readers of directory ancestors coexist. Clearing that directory requires
    # its exclusive lock, so a nested cache/output cannot be destroyed by it.
    modes = {parent: fcntl.LOCK_SH for target in targets for parent in target.parents}
    modes.update({target: fcntl.LOCK_EX for target in targets})
    held = []
    try:
        for resource, mode in sorted(modes.items(), key=lambda item: str(item[0])):
            name = hashlib.sha256(str(resource).encode("utf-8")).hexdigest() + ".lock"
            descriptor = os.open(lock_root / name, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            handle = os.fdopen(descriptor, "a+b")
            try:
                fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise RuntimeError(f"Run resource is already in use: {resource}") from exc
            except BaseException:
                handle.close()
                raise
            held.append(handle)
        yield
    finally:
        for handle in reversed(held):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        # Keep inode names stable. Unlinking them would let a second process
        # create a new inode while a first process still owns the old lock.


def prepare_cache_dir(cache_dir: Path, diagnostics: dict[str, Any], *,
    default_cache_dir: Path, marker_filename: str, now: Callable[[], datetime],
) -> Path:
    """Create a dedicated per-run cache directory and clear stale responses safely."""
    cache_dir = cache_dir.expanduser()
    resolved = cache_dir.resolve(strict=False)
    default_resolved = default_cache_dir.resolve(strict=False)
    diagnostics["cache"] = {
        "path": str(cache_dir),
        "resolved_path": str(resolved),
        "cleared_at": now().isoformat(),
        "removed_entries": 0,
        "marker": marker_filename,
    }

    unsafe_targets = {Path("/").resolve(), Path("/tmp").resolve(strict=False)}
    try:
        unsafe_targets.add(Path.home().resolve())
    except Exception:
        pass
    if resolved in unsafe_targets:
        raise RuntimeError(f"Refusing to use unsafe cache directory: {cache_dir}")
    if cache_dir.exists() and cache_dir.is_symlink():
        raise RuntimeError(f"Refusing to clear symlinked cache directory: {cache_dir}")
    if cache_dir.exists() and not cache_dir.is_dir():
        raise RuntimeError(f"Cache path exists but is not a directory: {cache_dir}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    marker_path = cache_dir / marker_filename
    is_default_cache = resolved == default_resolved
    has_marker = marker_path.exists()
    existing_entries = list(cache_dir.iterdir())
    if not is_default_cache and not has_marker and existing_entries:
        raise RuntimeError(
            "Refusing to clear a non-default cache directory without the "
            f"{marker_filename} marker: {cache_dir}"
        )

    removed_entries = 0
    for entry in existing_entries:
        if entry.name == marker_filename:
            continue
        try:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed_entries += 1
        except FileNotFoundError:
            continue

    marker_path.write_text(
        "This directory is managed by apple-news-24h and is cleared at each run.\n",
        encoding="utf-8",
    )
    diagnostics["cache"]["removed_entries"] = removed_entries
    return cache_dir


def decode_response(raw: bytes, content_type: str | None) -> str:
    charset = None
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
    if charset is None:
        head = raw[:2048].decode("ascii", errors="ignore")
        match = re.search(r"charset=['\"]?([A-Za-z0-9._-]+)", head, re.I)
        if match:
            charset = match.group(1)
    for encoding in [charset, "utf-8", "gb18030", "latin-1"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


@lru_cache(maxsize=1)
def _https_context() -> ssl.SSLContext:
    """Declare urllib's HTTP protocol consistently across Python versions."""
    context = ssl.create_default_context()
    context.set_alpn_protocols(["http/1.1"])
    return context


def fetch_url(
    url: str,
    cache_dir: Path,
    diagnostics: dict[str, Any],
    timeout: float | None = None,
    retries: int | None = None,
    *, settings: FetchSettings, now: Callable[[], datetime], method: str = 'GET',
) -> str | None:
    url = iri_to_uri(url)
    timeout = settings.timeout if timeout is None else timeout
    retries = settings.retries if retries is None else retries
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key(url if method == 'GET' else method + ' ' + url)}.json"
    last_error = ""

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": settings.user_agent},
                data=b'' if method == 'POST' else None, method=method)
            with urllib.request.urlopen(req, timeout=timeout, context=_https_context()) as response:
                raw = response.read(settings.max_response_bytes)
                text = decode_response(raw, response.headers.get("content-type"))
                payload = {
                    "url": url,
                    "fetched_at": now().isoformat(),
                    "status": getattr(response, "status", None),
                    "text": text,
                }
                if method != 'GET':
                    payload['method'] = method
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                return text
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))

    diagnostics.setdefault("failed_fetches", []).append({"url": url, "error": last_error})
    return None


def iri_to_uri(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%:@")
    query = urllib.parse.quote(parts.query, safe="=&?/%:@,+")
    fragment = urllib.parse.quote(parts.fragment, safe="=&?/%:@,+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def direct_apple_report_needs_detail(identity, *, has_lead: bool) -> bool:
    """Title-owned reports survive URL labels and incidental vendor mentions.

    This admits detail verification, not publication. Actual deals, episodes
    and third-party actions do not get this exception from background Apple
    names; the downstream source profile still owns relevance.
    """
    return high_confidence_direct_apple_action(identity) or bool(
                identity.scope == "apple-direct" and identity.title_products
                and identity.content_form == "news"
                and identity.action_owner in {"apple", "apple-target", "unknown"}
                and (has_lead or identity.title_actions))


def sparse_apple_subject_needs_detail(identity, *, has_lead: bool, event_kind: str,
                                      title: str = "", has_publication_time: bool = False) -> bool:
    """Recall a sparse Apple article without using its date as a news verdict."""
    title_text = title.strip()
    if title_text.casefold() in {'apple', '苹果', '苹果公司'} or re.search(r"之家$|\bcases\b|"
                 r"\b(?:vs\.?|versus)\b|"
                 r"^(?:how to|hard reset|force restart)\b|"
                 r"[:：]\s*(?:record|apply|reset|restart|enable|disable|customize)\b", title_text, re.I):
        # These phrases describe navigation or instructions, not a missing lead
        # for a particular newly reported action. Other admission evidence is
        # evaluated by the caller; this only withholds the sparse-topic escape.
        return False
    if not has_publication_time and re.search(
            r"(?:指南|技巧|教程)$|\b(?:guide|tips)\b", title_text, re.I):
        return False
    if title and identity is not None and any(
        re.fullmatch(r"(?:(?:the|apple)\s+|苹果\s*)?" + re.escape(alias)
                     + r"(?:\s*(?:\d+(?:\.\d+)*[a-z]?|pro|max|air|mini|ultra|se|plus|studio|duo))*", title.strip(), re.I)
        for product, aliases in PRODUCT_PATTERNS if product in identity.title_products
        for alias in aliases
    ):
        return False
    # A first-party device can be the host of third-party software. An RSS
    # excerpt disappearing must not turn that device capability into an app
    # vendor's action before its detail page has been inspected.
    device_host = bool(not has_lead and event_kind == 'third_party_ecosystem'
        and identity is not None and any(
        _compiled_rule(r'^(?:(?:the|apple[\x27’]s)\s+|苹果的?)?' + re.escape(alias)
            + r'(?:\s*(?:\d+(?:\.\d+)*|pro|max|air|mini|ultra|se|plus|duo))*\s*'
              r'(?:(?:now|can)\s+)?(?:runs?|supports?|hosts?|(?:现已|可以|可)?(?:运行|支持))\s*'
              r'(?:third[ -]party\s+apps?\b|第三方(?:应用|app))', re.I).search(title_text)
        for product, aliases in PRODUCT_PATTERNS if product in identity.title_products
        for alias in aliases))
    return bool((not has_lead or has_publication_time)
                and identity is not None and identity.scope == "apple-direct"
                and identity.content_form == "news"
                and identity.action_owner in {"unknown", "apple", "apple-target"}
                and (event_kind != "third_party_ecosystem" or device_host))



def current_apple_role_interview_needs_detail(title: str, lead: str, identity) -> bool:
    """Recall a locally attributed interview without guessing the person's name.

    This establishes a reason to fetch the report, not its final news value.
    A product comparison made by a different company's executive is insufficient.
    """
    if identity is None or not identity.title_products or not lead.strip():
        return False
    opening = re.split(r"[。!?]|(?<=[.])\s+", lead, maxsplit=1)[0]
    role = re.search(
        r"\bApple['’]s\s+(?:(?:new|current|incoming)\s+)?"
        r"(?:CEO|chief executive(?: officer)?|president|(?:senior )?vice president)\s+"
        r"([A-Z][A-Za-z’'-]+(?:\s+[A-Z][A-Za-z’'-]+){1,3})(?=\s+[a-z]|[,，])",
        opening,
    )
    if not role or role.group(1).casefold() not in title.casefold():
        return False
    action = opening[role.end():]
    if re.search(r"\b(?:previously|formerly|last year|never|did not|will|might|could)\b", action, re.I):
        return False
    return bool(re.search(r"\b(?:interview(?:ed)?|sat down|spoke with|talked with)\b", action, re.I))

def detail_recall_weight(profile: ReconciliationProfile, source_tier: str | None, *, has_lead: bool, title: str = "") -> int:
    """Preserve discovery breadth without granting an editorial outcome.

    A known Apple topic can deserve a detail fetch even when its sparse title,
    index page, or editorial form cannot establish an independent news action.
    Unknown third-party subjects receive no automatic topic bonus.
    """
    identity = profile.identity
    sparse_apple_topic = (
        sparse_apple_subject_needs_detail(identity, has_lead=has_lead, event_kind=profile.event_kind_hint, title=title)
        and not profile.defer_reason and not profile.hard_boundary
        and profile.event_kind_hint != "third_party_ecosystem"
    )
    bound_action = bool(profile.bound_claim and profile.bound_claim.subject
                        and profile.bound_claim.action and profile.bound_claim.object
                        and profile.bound_claim.evidence_spans)
    title_action = bool(identity is not None and identity.title_products and identity.title_actions
                        and identity.scope == "apple-direct" and identity.content_form == "news"
                        and identity.action_owner in {"apple", "apple-target", "unknown"})
    measured_result = bool(identity is not None
                           and "hardware-market-performance" in identity.title_components
                           and any(key.startswith("structured-component-measure:hardware-market-performance:")
                                   for key in profile.event_keys))
    if (source_tier == "strong" and (bound_action or measured_result)
            and not profile.defer_reason and not profile.hard_boundary):
        return 70
    if (source_tier == "strong" and title_action
            and not profile.defer_reason and not profile.hard_boundary):
        # Source-local bindings and concrete headline actions both outrank a
        # retained topic. A generic support flag without an action cannot.
        return 60
    if sparse_apple_topic:
        return 40
    return 40 if source_tier == "strong" else 30 if source_tier == "ecosystem" else 0


def xml_text(element: ET.Element, names: set[str]) -> str:
    return strip_tags(xml_text_raw(element, names))


def xml_text_raw(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        name = child.tag.rsplit("}", 1)[-1].lower()
        if name in names and child.text:
            return child.text
    return ""



def source_context_terms(raw_html: str, categories: list[str]) -> str:
    terms: list[str] = []

    def add(value: str) -> None:
        normalized = html.unescape(value).strip().lower()
        if not normalized:
            return
        normalized = normalized.replace("_", "-")
        for part in _compiled_rule(r"[,;/|]+", 0).split(normalized, 0):
            part = part.strip()
            if not part or part == "news":
                continue
            plain = part.replace("-", " ")
            if plain not in terms:
                terms.append(plain)

    for category in categories:
        add(category)
    for match in _compiled_rule(r"""data-layer-postcategory\s*=\s*['"]([^'"]+)['"]""", re.I).finditer(raw_html):
        add(match.group(1))
    return " ".join(terms)



def atom_link(element: ET.Element) -> str:
    for child in list(element):
        name = child.tag.rsplit("}", 1)[-1].lower()
        if name == "link":
            href = child.attrib.get("href")
            rel = child.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                return href.strip()
    return ""



def parse_xml_feed(text: str, source: Source, feed_url: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return candidates

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name == "opml":
        return candidates

    for item in root.iter():
        name = item.tag.rsplit("}", 1)[-1].lower()
        if name not in {"item", "entry"}:
            continue
        title = xml_text(item, {"title"})
        link = xml_text(item, {"link"})
        if not link:
            link = atom_link(item)
        raw_summary = xml_text_raw(item, {"description", "summary", "content", "encoded"})
        summary = strip_tags(raw_summary)
        published = xml_text(item, {"pubdate", "published", "updated", "dc:date"})
        categories = [
            strip_tags(child.text)
            for child in list(item)
            if child.tag.rsplit("}", 1)[-1].lower() == "category" and child.text
        ]
        context = source_context_terms(raw_summary, categories)
        if title and link:
            candidates.append(
                Candidate(
                    source=source.name,
                    url=urllib.parse.urljoin(feed_url, link),
                    title=title,
                    summary=summary,
                    feed_time_raw=published,
                    publication_time_raw=xml_text(item, {"pubdate", "published"}),
                    discovered_from=feed_url,
                    context=context,
                )
            )
    return candidates



def wordpress_rendered_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("rendered", "document_title", "raw"):
            rendered = value.get(key)
            if isinstance(rendered, str) and rendered.strip():
                return strip_tags(rendered)
        return ""
    if isinstance(value, str):
        return strip_tags(value)
    return ""



def wordpress_utc_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    if _compiled_rule(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", 0).fullmatch(cleaned):
        return f"{cleaned}+00:00"
    return cleaned



def parse_wordpress_posts_api(text: str, source: Source, api_url: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return candidates
    if not isinstance(payload, list):
        return candidates

    for item in payload:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if not isinstance(link, str) or not link.strip():
            continue
        title = wordpress_rendered_text(item.get("title"))
        summary = wordpress_rendered_text(item.get("excerpt"))
        if not title:
            continue
        context_terms: list[str] = []
        embedded = item.get("_embedded")
        if isinstance(embedded, dict):
            term_groups = embedded.get("wp:term")
            if isinstance(term_groups, list):
                for group in term_groups:
                    if not isinstance(group, list):
                        continue
                    for term in group:
                        if not isinstance(term, dict):
                            continue
                        for key in ("name", "slug"):
                            value = term.get(key)
                            if isinstance(value, str) and value.strip():
                                context_terms.append(strip_tags(value).replace("-", " "))
        feed_time_raw = wordpress_utc_timestamp(item.get("date_gmt")) or wordpress_utc_timestamp(
            item.get("date")
        )
        candidates.append(
            Candidate(
                source=source.name,
                url=urllib.parse.urljoin(api_url, html.unescape(link.strip())),
                title=title,
                summary=summary,
                feed_time_raw=feed_time_raw,
                publication_time_raw=feed_time_raw,
                discovered_from=api_url,
                context=" ".join(dict.fromkeys(context_terms)),
            )
        )
    return candidates



def parse_opml_feed_urls(text: str, limit: int) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    urls: list[str] = []
    for outline in root.iter():
        xml_url = outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl")
        if xml_url and xml_url.startswith(("http://", "https://")) and xml_url not in urls:
            urls.append(xml_url)
    return urls[:limit]



def same_domain(url: str, domains: tuple[str, ...]) -> bool:
    if not domains:
        return True
    host = urllib.parse.urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)



def extract_listing_metadata(text: str, page_url: str, source: Source) -> dict[str, dict[str, str]]:
    if source.name == 'IT之家':
        return extract_ithome_listing_metadata(text, page_url, source)
    if source.name != 'The Verge':
        return {}
    match = _compiled_rule(r'''<script\b[^>]*\bid\s*=\s*['"]__NEXT_DATA__['"][^>]*>(.*?)</script\s*>''', re.I | re.S).search(text)
    if not match:
        return {}
    try:
        state = json.loads(match.group(1))
    except ValueError:
        return {}
    for key in ('props', 'pageProps', 'hydration', 'responses'):
        if not isinstance(state, dict):
            return {}
        state = state.get(key)
    if not isinstance(state, list):
        return {}
    metadata = {}
    for response in state:
        rows = response
        for key in ('data', 'node', 'categoryLayoutPosts', 'nodes'):
            rows = rows.get(key) if isinstance(rows, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get('__typename') != 'PostResourceType':
                continue
            url = row.get('permalink')
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')) or not same_domain(url, source.domains):
                continue
            dek = row.get('dek')
            summary = dek.get('html') if isinstance(dek, dict) else None
            published = row.get('publishedAt')
            # Only this article's publication field may guide discovery.
            # Related posts and modification times cannot fill missing data.
            metadata[normalize_url(url)] = {
                'summary': strip_tags(summary) if isinstance(summary, str) else '',
                'feed_time_raw': published if isinstance(published, str) else '',
                'publication_time_raw': published if isinstance(published, str) else '',
            }
    return metadata


def extract_ithome_listing_metadata(text: str, page_url: str, source: Source) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for item_match in _compiled_rule(r"(?is)<li\b[^>]*>.*?</li>", 0).finditer(text):
        item_html = item_match.group(0)
        summary = ""
        summary_match = _compiled_rule(r"""(?is)<div\b(?=[^>]*class\s*=\s*['"][^'"]*\bm\b[^'"]*['"])[^>]*>(.*?)</div>""", 0).search(item_html)
        if summary_match:
            summary = strip_tags(summary_match.group(1))
        feed_time_raw = ""
        time_match = _compiled_rule(r"""data-ot\s*=\s*['"]([^'"]+)['"]""", re.I).search(item_html)
        if time_match:
            feed_time_raw = html.unescape(time_match.group(1)).strip()
        if not summary and not feed_time_raw:
            continue
        for link_match in _compiled_rule(r"(?is)<a\b([^>]+)>(.*?)</a>", 0).finditer(item_html):
            attrs, label_html = link_match.groups()
            href_match = _compiled_rule(r"""href\s*=\s*['"]([^'"]+)['"]""", re.I).search(attrs)
            if not href_match:
                continue
            label = strip_tags(label_html)
            if not label or len(label) < 8:
                continue
            url = urllib.parse.urljoin(page_url, html.unescape(href_match.group(1)))
            if not url.startswith(("http://", "https://")):
                continue
            if not same_domain(url, source.domains):
                continue
            metadata[normalize_url(url)] = {"summary": summary, "feed_time_raw": feed_time_raw,
                                            "publication_time_raw": feed_time_raw}
    return metadata



def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [
        (key, value)
        for key, value in query
        if not key.lower().startswith(("utm_", "fbclid", "gclid"))
    ]
    clean_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            clean_query,
            "",
        )
    )


def fetch_detail_page_texts(
    candidates: list[Candidate],
    cache_dir: Path,
    diagnostics: dict[str, Any], *, fetch: Callable, max_workers: int,
) -> list[str | None]:
    if not candidates:
        diagnostics["detail_fetch_workers"] = 0
        diagnostics["detail_fetch_retry_count"] = 0
        diagnostics["detail_fetch_retry_recovered"] = 0
        return []
    workers = min(max_workers, len(candidates))
    diagnostics["detail_fetch_workers"] = workers
    results: list[str | None] = [None] * len(candidates)

    def fetch_one(
        index: int,
        candidate: Candidate,
        retries: int | None,
    ) -> tuple[int, str | None, list[dict[str, Any]]]:
        local_diagnostics: dict[str, Any] = {"failed_fetches": []}
        page_text = fetch(
            candidate.url,
            cache_dir,
            local_diagnostics,
            retries=retries,
        )
        return index, page_text, list(local_diagnostics.get("failed_fetches", []))

    def run_pass(
        indexes: list[int],
        *,
        retries: int | None,
    ) -> dict[int, list[dict[str, Any]]]:
        pass_failures: dict[int, list[dict[str, Any]]] = {}
        if not indexes:
            return pass_failures
        pass_workers = min(max_workers, len(indexes))
        if pass_workers <= 1:
            for index in indexes:
                candidate = candidates[index]
                try:
                    result_index, page_text, local_failures = fetch_one(
                        index,
                        candidate,
                        retries,
                    )
                except Exception as exc:
                    page_text = None
                    result_index = index
                    local_failures = [
                        {
                            "url": candidate.url,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    ]
                results[result_index] = page_text
                if page_text is None:
                    pass_failures[result_index] = local_failures
            return pass_failures

        with concurrent.futures.ThreadPoolExecutor(max_workers=pass_workers) as executor:
            future_map = {
                executor.submit(fetch_one, index, candidates[index], retries): index
                for index in indexes
            }
            for future in concurrent.futures.as_completed(future_map):
                index = future_map[future]
                try:
                    result_index, page_text, local_failures = future.result()
                except Exception as exc:
                    candidate = candidates[index]
                    result_index = index
                    page_text = None
                    local_failures = [
                        {
                            "url": candidate.url,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    ]
                results[result_index] = page_text
                if page_text is None:
                    pass_failures[result_index] = local_failures
        return pass_failures

    first_failures = run_pass(list(range(len(candidates))), retries=None)
    retry_indexes = sorted(first_failures)
    diagnostics["detail_fetch_retry_count"] = len(retry_indexes)
    retry_failures = run_pass(retry_indexes, retries=0)
    recovered_indexes = [index for index in retry_indexes if results[index] is not None]
    diagnostics["detail_fetch_retry_recovered"] = len(recovered_indexes)
    if recovered_indexes:
        diagnostics.setdefault("transient_detail_fetches", []).extend(
            failure
            for index in recovered_indexes
            for failure in first_failures.get(index, [])
        )
    terminal_failures = [
        failure
        for index in retry_indexes
        if results[index] is None
        for failure in (
            retry_failures.get(index)
            or first_failures.get(index)
            or [
                {
                    "url": candidates[index].url,
                    "error": "detail fetch failed without an exception record",
                }
            ]
        )
    ]
    diagnostics.setdefault("failed_fetches", []).extend(terminal_failures)
    return results



_discovery_executor = ContextVar('discovery_executor', default=None)


def fetch_discovery_pages(urls, fetch: Callable) -> list:
    """Share the run's network slots, including nested feeds, in input order."""
    executor = _discovery_executor.get()
    return list(executor.map(fetch, urls)) if executor is not None else [fetch(url) for url in urls]


def collect_candidates_from_sources(
    sources: list[Source],
    cache_dir: Path,
    diagnostics: dict[str, Any], *, collect: Callable, max_workers: int,
    window_start_utc: datetime | None = None,
    window_end_utc: datetime | None = None,
) -> list[Candidate]:
    """Discover independent sources concurrently while preserving source order."""
    if not sources:
        diagnostics["source_discovery_workers"] = 0
        return []
    workers = min(max_workers, len(sources))
    diagnostics["source_discovery_workers"] = workers
    options = {'window_start_utc': window_start_utc} if window_start_utc is not None else {}
    if window_end_utc is not None:
        options['window_end_utc'] = window_end_utc
    if workers <= 1:
        return [
            candidate
            for source in sources
            for candidate in collect(source, cache_dir, diagnostics, **options)
        ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as transport, \
            concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        def discover(source):
            token = _discovery_executor.set(transport)
            try:
                return collect(source, cache_dir, diagnostics, **options)
            finally:
                _discovery_executor.reset(token)
        per_source = executor.map(
            discover,
            sources,
        )
        return [candidate for candidates in per_source for candidate in candidates]
