"""Structural article cleanup and lossless source evidence, without news decisions."""
from __future__ import annotations
from functools import lru_cache
import hashlib
import email.utils
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Callable, Iterable
from .models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference

@lru_cache(maxsize=128)
def _compiled_markup_rule(pattern: str, flags: int = 0):
    """Reuse markup rule programs, never article text or extraction results."""
    return re.compile(pattern, flags)


def newsletter_navigation_noise(value: str) -> bool:
    """Discard newsletter UI and signup prompts, never the bare topic word."""
    if "newsletter" not in value.lower():
        return False
    return bool(_compiled_markup_rule(
        r"^\s*(?:(?:daily|weekly|our|the|email)\s+)*newsletter(?:\s+(?:signup|sign-up|subscription))?[.!:]?\s*$|"
        r"^\s*(?:please\s+)?(?:subscribe|sign\s+up|join\s+(?:our|the)|get\s+(?:our|the)|"
        r"receive\s+(?:our|the))\b[^.!?]{0,120}\bnewsletter\b|"
        r"^\s*our\s+(?:free\s+|daily\s+|weekly\s+)?newsletter\b[^.!?]{0,120}"
        r"\b(?:inbox|delivered|sign\s+up|subscribe)\b", re.I).search(value))


def strip_tags(value: str) -> str:
    value = _compiled_markup_rule(r"(?is)<script\b.*?</script>", 0).sub(" ", value, 0)
    value = _compiled_markup_rule(r"(?is)<style\b.*?</style>", 0).sub(" ", value, 0)
    value = _compiled_markup_rule(r"(?is)<[^>]+>", 0).sub(" ", value, 0)
    value = html.unescape(value)
    return _compiled_markup_rule(r"\s+", 0).sub(" ", value, 0).strip()


def visible_element_text(text: str, element_id: str) -> str:
    """Read a named visible field, ignoring markup examples and inactive content."""
    class FieldParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack: list[tuple[str, bool, bool]] = []
            self.parts: list[str] = []
            self.found = False

        def handle_starttag(self, tag, attrs):
            blocked = tag in {"script", "style", "template", "pre", "code"} or bool(
                self.stack and self.stack[-1][1])
            selected = bool(self.stack and self.stack[-1][2])
            if not blocked and not self.found and dict(attrs).get("id") == element_id:
                selected = self.found = True
            if tag not in EvidenceTextExtractor.void_tags:
                self.stack.append((tag, blocked, selected))

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break

        def handle_data(self, data):
            if self.stack and self.stack[-1][2] and not self.stack[-1][1]:
                self.parts.append(data)

    parser = FieldParser()
    parser.feed(text)
    return " ".join(" ".join(parser.parts).split())


def json_ld_objects(text: str) -> list[Any]:
    objects: list[Any] = []
    for match in _compiled_markup_rule(r"(?is)<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", 0).finditer(text):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            raw = _compiled_markup_rule(r"(?is)^\s*<!--|-->\s*$", 0).sub("", raw, 0).strip()
            try:
                objects.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return objects


def iter_json_ld_nodes(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_json_ld_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_json_ld_nodes(item)


def json_type_names(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    raw_type = value.get("@type")
    if isinstance(raw_type, str):
        return {raw_type}
    if isinstance(raw_type, list):
        return {item for item in raw_type if isinstance(item, str)}
    return set()


def structured_article_body_html(text: str, source_name: str) -> str:
    """Return a clean body scope when a source exposes authoritative articleBody data."""
    if source_name != "The Verge":
        return text
    for obj in json_ld_objects(text):
        for node in iter_json_ld_nodes(obj):
            if not isinstance(node, dict):
                continue
            if not ({"NewsArticle", "Article"} & json_type_names(node)):
                continue
            raw_body = node.get("articleBody")
            if not isinstance(raw_body, str):
                continue
            body = strip_tags(raw_body).strip()
            # Remove serialized wrappers before sentence splitting can separate
            # a descriptive caption from its trailing media URL.
            for start, end in reversed(inline_media_marker_spans(body)):
                body = body[:start] + " " + body[end:]
            if len(body) < 100:
                continue
            paragraphs = [part.strip() for part in _compiled_markup_rule(r"\n{2,}", 0).split(body, 0) if part.strip()]
            if len(paragraphs) == 1:
                paragraphs = [
                    part.strip()
                    for part in _compiled_markup_rule(r"(?<=[.!?。！？])\s+", 0).split(body, 0)
                    if part.strip()
                ]
            return "<article>" + "".join(
                f"<p>{html.escape(part)}</p>" for part in paragraphs
            ) + "</article>"
    return text


def meta_content(text: str, names: list[str]) -> str:
    for name in names:
        pattern = (
            r"(?is)<meta\b(?=[^>]*(?:property|name|itemprop)=['\"]"
            + re.escape(name)
            + r"['\"])[^>]*content=['\"]([^'\"]+)['\"][^>]*>"
        )
        match = _compiled_markup_rule(pattern).search(text)
        if match:
            return html.unescape(match.group(1)).strip()
        pattern = (
            r"(?is)<meta\b(?=[^>]*content=['\"]([^'\"]+)['\"])[^>]*"
            r"(?:property|name|itemprop)=['\"]"
            + re.escape(name)
            + r"['\"][^>]*>"
        )
        match = _compiled_markup_rule(pattern).search(text)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def extract_title(text: str, fallback: str) -> str:
    title = meta_content(text, ["og:title", "twitter:title"])
    if title:
        return strip_tags(title)
    h1 = _compiled_markup_rule(r"(?is)<h1[^>]*>(.*?)</h1>", 0).search(text)
    if h1:
        return strip_tags(h1.group(1))
    title_tag = _compiled_markup_rule(r"(?is)<title[^>]*>(.*?)</title>", 0).search(text)
    if title_tag:
        return strip_tags(title_tag.group(1))
    return fallback.strip()


TRAILING_PROMO_SECTION_PATTERNS = (
    r"my\s+top\s+deals\b",
    r"my\s+favorite\s+(?:apple\s+)?(?:deals|offers)\b"
    r"(?:\s+(?:right\s+now|today|this\s+week))?",
    r"my\s+favorite\s+apple\s+accessory\s+recommendations",
    r"my\s+favorite\s+(?:carplay|iphone|ipad|mac|apple\s+watch|apple\s+tv|vision\s+pro|airpods|apple)(?:\s+(?:\d+[a-z]?|pro|max|air|mini|ultra|plus)){0,4}\s+accessories",
    r"my\s+favorite\s+(?:iphone|ipad|mac|apple\s+watch|apple\s+tv|vision\s+pro|airpods|apple)\s+links",
    r"worth\s+checking\s+out\s+on\s+amazon",
    r"one\s+of\s+the\s+(?:easiest|best)\s+ways\s+to\s+buy\b[^<\n]{0,180}\b(?:via|on)\s+amazon",
    r"chance(?:'|’|&#8217;|&rsquo;)s\s+favorites",
    r"do\s+more\s+with\s+your\s+apple\s+products",
    r"official\s+apple\s+store\s+on\s+amazon",
    r"amazon\s+prime\s+day\s+\d{4}",
    r"(?:prime\s+day\s+)?savings\s+on\s+apple\s+gear",
    r"apple\s+gear\s+savings",
    r"shop\s+at\s+apple\s+with\s+\d{1,2}%\s+discount\s+on\s+certified\s+refurbished",
    r"certified\s+refurbished\s+(?:apple\s+)?products?\s+\d{1,2}%\s+off\s+at\s+apple\.com",
    r"best\s+[a-z0-9+,&'’\-\s]{2,90}\s+accessories\b",
    r"best\s+(?:iphone|ipad|mac|airpods|apple\s+tv\s+4k|apple\s+watch(?:\s+and\s+iphone)?|iphone\s+and\s+apple\s+watch|vision\s+pro|apple)\s+"
    r"(?:accessories|deals\s+and\s+accessories)",
)


def remove_trailing_promo_sections(text: str) -> str:
    """Cut 9to5-style affiliate recommendation blocks after the real article body."""
    earliest: int | None = None
    for pattern in TRAILING_PROMO_SECTION_PATTERNS:
        match = _compiled_markup_rule(pattern, re.I).search(text)
        if not match:
            continue
        leading_text = strip_tags(text[: match.start()])
        if len(leading_text) < 120:
            continue
        earliest = match.start() if earliest is None else min(earliest, match.start())
    if earliest is None:
        return text
    return text[:earliest]


def remove_article_end_tail_sections(text: str) -> str:
    """Cut source footer/recommendation text after explicit article-end markers."""
    earliest: int | None = None
    for pattern in [
        r"【\s*本文结束\s*】",
        r"\b本文结束\b",
    ]:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        leading_text = strip_tags(text[: match.start()])
        if len(leading_text) < 80:
            continue
        earliest = match.start() if earliest is None else min(earliest, match.start())
    if earliest is None:
        return text
    return text[:earliest]


def is_linked_sponsor_paragraph(fragment: str) -> bool:
    plain = strip_tags(fragment)
    return bool(_compiled_markup_rule(r"\b(?:is\s+(?:exclusively\s+)?brought\s+to\s+you\s+by|sponsored\s+by)\b", re.I).search(plain)
        and _compiled_markup_rule(r"(?is)<a\b[^>]*>.*?\b(?:request|start|claim|try)\b.*?\btrial\b.*?</a>", 0).search(fragment))


def source_description_without_editorial_prefix(text: str, description: str) -> str:
    """Trim a proven sponsor prefix only at an actual retained body boundary.

    The raw metadata remains in captured evidence. News following the prefix
    is preserved, including when the metadata excerpt contains extra detail.
    """
    description = strip_tags(description)
    if not any(word in description.casefold() for word in ("brought", "sponsored")):
        return description
    sponsors = [strip_tags(m.group()) for m in _compiled_markup_rule(r"(?is)<p\b[^>]*>.*?</p>", 0).finditer(text)
                if is_linked_sponsor_paragraph(m.group())]
    def normalized_prefix(value):
        return _compiled_markup_rule(r"\s+([.,!?])", 0).sub(r"\1", value.casefold(), 0)
    if not any(normalized_prefix(description).startswith(normalized_prefix(_compiled_markup_rule(r"(?<=[.!?])\s+", 0).split(p, 1)[0])) for p in sponsors):
        return description
    for match in _compiled_markup_rule(r"(?is)<p\b[^>]*>(.*?)</p>", 0).finditer(article_scope(text)):
        body = strip_tags(match.group(1))
        first = _compiled_markup_rule(r"(?<=[.!?。！？])\s+", 0).split(body, 1)[0]
        if len(first) < 40:
            continue
        found = re.search(re.escape(first), description, re.I)
        if found:
            return description[found.start():]
    # A metadata excerpt can stop inside the already established sponsor
    # paragraph. It has no news suffix to retain: let the caller use the clean
    # body, while capture continues to preserve the original raw metadata.
    excerpt = normalized_prefix(description).rstrip(".… ")
    if excerpt and any(normalized_prefix(p).startswith(excerpt) for p in sponsors):
        return ""
    return description


def remove_noise_blocks(text: str) -> str:
    text = remove_article_end_tail_sections(remove_trailing_promo_sections(text))
    cleaned = _compiled_markup_rule(r"(?is)<!--\s*相关文章\s*-->.*?(?=<!--\s*评论\s*-->|<div\b[^>]+id=['\"]post_comm['\"]|</article>|</main>|$)", 0).sub(" ", text, 0)
    cleaned = _compiled_markup_rule(r"(?is)<div\b(?=[^>]*class=['\"][^'\"]*related_post[^'\"]*['\"])[^>]*>.*?"
        r"(?=<!--\s*评论\s*-->|<div\b[^>]+id=['\"]post_comm['\"]|</article>|</main>|$)", 0).sub(" ", cleaned, 0)
    cleaned = _compiled_markup_rule(r"(?is)<div\b(?=[^>]*id=['\"]fls['\"])[^>]*>.*?(?:</div>|$)", 0).sub(" ", cleaned, 0)
    cleaned = _compiled_markup_rule(r"(?is)<p\b(?=[^>]*(?:class|id)=['\"][^'\"]*(?:ad-tips|advertis|newsletter|subscribe)[^'\"]*['\"])[^>]*>.*?</p>", 0).sub(" ", cleaned, 0)
    # A native paragraph can be an explicit sponsor message even without an
    # advertising class. Require the sponsorship relation and linked CTA;
    # a news sentence discussing trials or sponsored features is not enough.
    cleaned = _compiled_markup_rule(r"(?is)<p\b[^>]*>.*?</p>", 0).sub(lambda match: " " if is_linked_sponsor_paragraph(match.group()) else match.group(), cleaned, 0)
    noisy_attr = (
        r"(?:related|recirc|recommend|featured|newsletter|subscribe|comment|"
        r"advertis|ad-container|affiliate|post-nav|sharedaddy|social|share|"
        r"navs_newsinfo|xg_newsinfo)"
    )
    pattern = (
        r"(?is)<(?P<tag>aside|section|div|nav)\b(?=[^>]*(?:class|id)=['\"][^'\"]*"
        + noisy_attr
        + r"[^'\"]*['\"])[^>]*>.*?</(?P=tag)>"
    )
    previous = None
    for _ in range(4):
        if cleaned == previous:
            break
        previous = cleaned
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = remove_article_end_tail_sections(remove_trailing_promo_sections(cleaned))
    # An explicit related-reading section is navigation, not article evidence.
    marker = _compiled_markup_rule(r'(?is)<(?:p|h[1-6])\b[^>]*>\s*(?:<strong[^>]*>)?\s*(?:相关阅读|相关文章|延伸阅读|Related (?:Articles|Stories|Reading))\s*[:：]?\s*(?:</strong>)?\s*[:：]?\s*</(?:p|h[1-6])>', 0).search(cleaned)
    return cleaned[:marker.start()] if marker else cleaned


PREFERRED_CONTENT_CLASS_FRAGMENTS = (
    "post-content",
    "post_content",
    "entry-content",
    "article-content",
    "article-body",
    "article__body",
    "single__content",
    "story-content",
    "pagebody-copy",
    "article-copy",
    "body-copy",
    "news_info",
)


def balanced_element_inner(text: str, start_index: int, tag_name: str) -> str:
    start_match = re.match(rf"(?is)<{tag_name}\b[^>]*>", text[start_index:])
    if not start_match:
        return ""
    inner_start = start_index + start_match.end()
    depth = 1
    for match in re.finditer(rf"(?is)</?{tag_name}\b[^>]*>", text[inner_start:]):
        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return text[inner_start : inner_start + match.start()]
        elif not token.endswith("/>"):
            depth += 1
    return text[inner_start:]


def preferred_content_scope(text: str) -> str:
    candidates: list[tuple[int, str]] = []
    pattern = _compiled_markup_rule(r"(?is)<(?P<tag>div|section|article|main)\b(?P<attrs>[^>]*)>", 0)
    for match in pattern.finditer(text):
        attrs = match.group("attrs").lower()
        if not any(fragment in attrs for fragment in PREFERRED_CONTENT_CLASS_FRAGMENTS):
            continue
        inner = balanced_element_inner(text, match.start(), match.group("tag").lower())
        if not inner:
            continue
        plain = strip_tags(remove_noise_blocks(inner))
        paragraph_score = len(_compiled_markup_rule(r"(?is)<(?:p|li)\b", 0).findall(inner)) * 200
        heading_penalty = 250 if "sidebar" in attrs or "is-clickable-card" in attrs else 0
        score = paragraph_score + min(len(plain), 4000) - heading_penalty
        if len(plain) >= 80:
            candidates.append((score, inner))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return remove_noise_blocks(candidates[0][1])


def article_scope(text: str) -> str:
    # Remove non-content before looking for paragraph/container markup: script
    # strings can themselves contain HTML and must never become source prose.
    text = _compiled_markup_rule(r'(?is)<(script|style)\b[^>]*>.*?</\1\s*>', 0).sub(' ', text, 0)
    preferred = preferred_content_scope(text)
    if preferred:
        return preferred
    for tag in ["article", "main"]:
        match = re.search(rf"(?is)<{tag}\b[^>]*>(.*?)</{tag}>", text)
        if match:
            return remove_noise_blocks(match.group(1))
    return remove_noise_blocks(text)



class EvidenceTextExtractor(HTMLParser):
    """Keep every nonempty structural unit, including short lists and naked text."""
    block_tags = {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
                  'pre', 'div', 'section', 'article', 'main', 'ul', 'ol', 'table', 'tr'}
    ignored_tags = {'script', 'style', 'nav', 'aside', 'footer', 'form', 'button', 'noscript'}
    void_tags = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
    caption_class = _compiled_markup_rule(r'(?:^|[-_])(?:image|media|photo|figure)[-_]+caption(?:$|[-_])', re.I)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.units: list[tuple[str, str, str]] = []
        self.stack: list[str] = []
        self.caption_stack: list[bool] = []
        self.parts: list[str] = []
        self.caption_text = False
        self.body_text = False
        self.kind = 'text'
        self.table_number = 0
        self.row = False
        self.container = ''

    def flush(self):
        value = _compiled_markup_rule(r'\s+', 0).sub(' ', ''.join(self.parts), 0).strip(' |\t\n')
        if value:
            container = ('caption' if self.caption_text and not self.body_text
                         and not self.container else self.container)
            self.units.append((self.kind, value, container))
        self.parts = []
        self.caption_text = False
        self.body_text = False

    def handle_starttag(self, tag, attrs):
        if any(t in self.ignored_tags for t in self.stack):
            if tag not in self.void_tags:
                self.stack.append(tag)
                self.caption_stack.append(self.caption_stack[-1] if self.caption_stack else False)
            return
        attributes = dict(attrs)
        caption = (tag == 'figcaption' or any(self.caption_class.search(marker)
                   for marker in (attributes.get('class') or '').split()))
        if tag in self.ignored_tags:
            self.flush()
        elif tag == 'br':
            self.parts.append(' ')
        elif tag in self.block_tags and not self.row:
            self.flush()
            # Paragraph/layout wrappers do not turn a list member into prose.
            self.kind = 'li' if tag in {'p', 'div', 'section'} and 'li' in self.stack else tag
            if tag == 'table':
                self.table_number += 1
            if tag == 'tr':
                self.row = True
                self.container = f'table:{self.table_number}'
        if tag not in self.void_tags:
            self.stack.append(tag)
            self.caption_stack.append(caption or (self.caption_stack[-1]
                if self.caption_stack else False))

    def handle_endtag(self, tag):
        ignored = any(t in self.ignored_tags for t in self.stack)
        if not ignored:
            if self.row and tag in {'th', 'td'}:
                self.parts.append(' | ')
            elif tag == 'tr':
                self.flush()
                self.row = False
                self.container = ''
            elif tag in self.block_tags and not self.row:
                self.flush()
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]
            del self.caption_stack[index:]
        if not self.row:
            self.kind = next((t for t in reversed(self.stack) if t in self.block_tags), 'text')
            if self.kind in {'p', 'div', 'section'} and 'li' in self.stack:
                self.kind = 'li'

    def handle_data(self, data):
        if not any(t in self.ignored_tags for t in self.stack):
            self.parts.append(data)
            if data.strip():
                if self.caption_stack and self.caption_stack[-1]:
                    self.caption_text = True
                else:
                    self.body_text = True

    def close(self):
        super().close()
        self.flush()



def release_history_unit_ids(evidence: ArticleEvidence) -> frozenset[str]:
    """Locate an explicitly labelled release-history appendix, retaining raw units."""
    heading = _compiled_markup_rule(
        r"(?:附\s*.{0,60}(?:发布历史|历史版本)|(?:appendix\s*:\s*)?"
        r"(?:(?:iOS|iPadOS|macOS|watchOS|tvOS|visionOS|HomePod)[\w\s./]*\s+)?release\s+history)\s*[:：]?", re.I)
    row = _compiled_markup_rule(
        r"^\s*20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\s*[:：]\s*"
        r"(?:iOS|iPadOS|macOS|watchOS|tvOS|visionOS|HomePod)(?:\s+Software)?\s+"
        r"\d[\w.\s-]*\([A-Za-z0-9.]+\)\s*", re.I)
    result, section = set(), []
    for index, unit in enumerate(evidence.units):
        if unit.kind in {'h2', 'h3', 'h4', 'h5', 'h6', 'p'} and heading.fullmatch(unit.text.strip()):
            previous = evidence.units[index - 1].text if index else ""
            current_requirements = (_compiled_markup_rule(r"following|如下|以下|下列", re.I).search(previous)
                and _compiled_markup_rule(r"support|eligib|require|支持|适用|要求", re.I).search(previous))
            section = [] if current_requirements else [unit.unit_id]
        elif section and unit.kind in {'p', 'li', 'tr'} and row.fullmatch(unit.text):
            section.append(unit.unit_id)
            result.update(section)
        else:
            if (section and unit.kind in {'p', 'li', 'tr'}
                    and _compiled_markup_rule(r"^\s*20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}").search(unit.text)
                    and _compiled_markup_rule(r"support|eligib|require|支持|适用|要求", re.I).search(unit.text)):
                result.difference_update(section)
            section = []
    return frozenset(result)


def editorial_list_unit_ids(evidence: ArticleEvidence) -> frozenset[str]:
    """Identify credited people/navigation in a locally introduced podcast footer."""
    description = ""
    credits = False
    result = set()
    for unit in evidence.units:
        text = unit.text.strip()
        if unit.kind in {"p", "text"}:
            # A publisher's recurring programme description and subscription
            # invitation establish the editorial purpose; a news mention does not.
            description = text if (_compiled_markup_rule(r"\bis\s+(?:a|an)\b.{0,100}\bpodcast\b", re.I).search(text)
                and _compiled_markup_rule(r"\bsubscribe\s+(?:to|via|on)\b", re.I).search(text)) else ""
            credits = False
        elif unit.kind in {"h2", "h3", "h4", "h5", "h6"}:
            credits = bool(description and _compiled_markup_rule(r"(?:hosts?|presenters?|subscribe|subscriptions?)[ :]*", re.I).fullmatch(text))
        elif unit.kind == "li" and credits:
            bare = bool(_compiled_markup_rule(r"[^.!?。！？;；:=]{2,100}", 0).fullmatch(text))
            destination = _compiled_markup_rule(r"\s+on\s+", re.I).split(text, 1)
            credited = not _compiled_markup_rule(r"\d", 0).search(text) and text.casefold() in description.casefold()
            navigation = len(destination) == 2 and destination[1].casefold() in description.casefold()
            if bare and (credited or navigation):
                result.add(unit.unit_id)
        elif unit.kind != "li":
            credits = False
            description = ""
    return frozenset(result)



class EvidenceMarkupFilter(HTMLParser):
    """Remove explicit template subtrees while their ancestors are still present."""
    noise_class = _compiled_markup_rule(r'(?:^|[-_\s])(?:related|recirc|recommend(?:ed|ation)?|newsletter|subscribe|'
        r'visitor-promo|ad-container|ad-disclaimer|disclaimer-affiliate|advertisement|'
        r'post-nav|sharedaddy|social-share)(?:[-_\s]|$)', re.I)

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool, bool]] = []
        self.canonical_urls: list[str] = []

    def suppressed(self):
        return bool(self.stack and self.stack[-1][1])

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if not self.suppressed() and tag == 'link' and 'canonical' in (attributes.get('rel') or '').lower().split():
            if attributes.get('href'):
                self.canonical_urls.append(attributes['href'])
        markers = ' '.join(attributes.get(key) or '' for key in ('class', 'id'))
        # Match the template element's own class, never an ancestor layout
        # modifier such as body.layout-no-footer-desktop.
        template = tag in {'div', 'section', 'footer'} and any(
            _compiled_markup_rule(r'^(?:linkback|footer|byline)(?:[-_]|$)', re.I).match(marker)
            for marker in markers.split())
        template = template or (tag in {'a', 'div', 'p', 'section'} and bool(
            {'tougao-user', 'topic-bar'} & set(markers.split())))
        media_caption = any(_compiled_markup_rule(r'(?:^|[-_])media[-_]+caption(?:$|[-_])', re.I).search(marker)
                            for marker in markers.split())
        # Keep the caption's descriptive prose. Only its explicit attribution
        # element is metadata, not every sentence mentioning an image.
        media_credit = tag == 'cite' and any(entry[2] for entry in self.stack)
        suppressed = self.suppressed() or tag in EvidenceTextExtractor.ignored_tags or template or media_credit or bool(self.noise_class.search(markers))
        # data-nosnippet alone is not advertising; legitimate body limits may use it.
        if not suppressed:
            self.parts.append(self.get_starttag_text())
        if tag not in EvidenceTextExtractor.void_tags:
            self.stack.append((tag, suppressed, media_caption))

    def handle_endtag(self, tag):
        if not self.suppressed():
            self.parts.append(f'</{tag}>')
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.suppressed():
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data(f'&{name};')

    def handle_charref(self, name):
        self.handle_data(f'&#{name};')

    def handle_comment(self, data):
        if not self.suppressed():
            self.parts.append(f'<!--{data}-->')


def evidence_url_key(value: str, page_url: str) -> str:
    parts = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, html.unescape(value)))
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith(('utm_', 'fbclid', 'gclid'))]
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
        urllib.parse.unquote(parts.path).rstrip('/'), urllib.parse.urlencode(sorted(query)), ''))


def jsonld_page_references(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [ref for item in value for ref in jsonld_page_references(item)]
    if isinstance(value, dict):
        return [ref for key in ('@id', 'url') for ref in jsonld_page_references(value.get(key))]
    return []


def current_jsonld_article_bodies(text: str, page_url: str, canonical_urls: list[str]) -> list[str]:
    """Accept page-matching Article nodes, or a single otherwise unlabelled body."""
    page_keys = {evidence_url_key(value, page_url) for value in [page_url, *canonical_urls]}
    matching: list[str] = []
    unlabelled: list[str] = []
    for obj in json_ld_objects(text):
        for node in iter_json_ld_nodes(obj):
            if not isinstance(node, dict) or not ({'Article', 'NewsArticle'} & json_type_names(node)):
                continue
            body = node.get('articleBody')
            if not isinstance(body, str) or not body.strip():
                continue
            refs = jsonld_page_references(node.get('url')) + jsonld_page_references(node.get('mainEntityOfPage'))
            if not refs:
                identifier = node.get('@id')
                if isinstance(identifier, str) and identifier.startswith(('http://', 'https://', '/', '#')):
                    refs = [identifier]
            if refs:
                if all(evidence_url_key(ref, page_url) in page_keys for ref in refs):
                    matching.append(body)
            else:
                unlabelled.append(body)
    # Multiple unlabelled articles cannot all be attributed to the current URL.
    return matching or (unlabelled if len(unlabelled) == 1 else [])


def evidence_body_scope(text: str, *, filtered: bool = False) -> str:
    """Use whole structural containers; never score by paragraph count or length."""
    if not filtered:
        parser = EvidenceMarkupFilter()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
    fragments = []
    covered_until = 0
    for match in _compiled_markup_rule(r'(?is)<(?P<tag>div|section)\b(?P<attrs>[^>]*)>', 0).finditer(text):
        if match.start() < covered_until:
            continue
        if any(fragment in match.group('attrs').lower() for fragment in PREFERRED_CONTENT_CLASS_FRAGMENTS):
            inner = balanced_element_inner(text, match.start(), match.group('tag').lower())
            fragments.append(inner)
            covered_until = match.end() + len(inner)
    if fragments:
        return remove_noise_blocks('\n'.join(fragments))
    for tag in ('article', 'main'):
        match = re.search(rf'(?is)<{tag}\b[^>]*>', text)
        if match:
            return remove_noise_blocks(balanced_element_inner(text, match.start(), tag))
    return remove_noise_blocks(text)


class EmbeddedReferenceExtractor(HTMLParser):
    """Capture embedded objects in the selected body, without fetching them.

    Positions are element ordinals in the cleaned body, not text spans or
    offsets into the original response. The original start tag is retained.
    """
    def __init__(self, origin):
        super().__init__(convert_charrefs=True)
        self.origin = origin
        self.stack = []
        self.ordinal = 0
        self.references = []

    def handle_starttag(self, tag, attrs):
        self.ordinal += 1
        attrs = dict(attrs)
        raw_url = attrs.get('src' if tag == 'iframe' else 'href', '')
        embedded = tag == 'iframe' or (tag == 'a' and any(
            t == 'blockquote' and 'twitter-tweet' in c.split() for t, c in self.stack))
        if embedded and raw_url:
            try:
                parts = urllib.parse.urlsplit(raw_url)
                host = (parts.hostname or '').lower()
            except ValueError:
                parts = urllib.parse.urlsplit('')
                host = ''
            object_id = ''
            if host in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'}:
                match = _compiled_markup_rule(r'/[^/]+/status/(\d+)/?', 0).fullmatch(parts.path)
                object_id = match.group(1) if match else ''
            elif host == 'platform.twitter.com' and parts.path.lower() == '/embed/tweet.html':
                value = urllib.parse.parse_qs(parts.query).get('id', [''])[0]
                object_id = value if value.isdigit() else ''
            if object_id:
                self.references.append(EmbeddedReference('x', object_id, raw_url,
                    self.origin, self.ordinal, self.get_starttag_text()))
        if tag not in EvidenceTextExtractor.void_tags:
            self.stack.append((tag, attrs.get('class', '')))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def capture_article_evidence(
    source: str, url: str, text: str | None, fallback_title: str,
    discovery_lead: str = '', publication_candidates: tuple[PublicationEvidence, ...] = (),
) -> ArticleEvidence:
    """Capture clean source units before all semantic selection; no action inference."""
    article_id = hashlib.sha256(f'{source}\0{url}'.encode()).hexdigest()[:24]
    title = extract_title(text, fallback_title) if text is not None else fallback_title
    raw_lead = meta_content(text, ['og:description', 'twitter:description', 'description', 'Description']) if text is not None else discovery_lead
    segments: list[tuple[str, str]] = []
    if text is not None:
        page = EvidenceMarkupFilter()
        page.feed(text)
        page.close()
        for body in current_jsonld_article_bodies(text, url, page.canonical_urls):
            # Preserve paragraph/newline boundaries instead of flattening articleBody.
            if not _compiled_markup_rule(r'<(?:p|div|li|table|article)\b', re.I).search(body):
                body = ''.join(f'<p>{html.escape(part)}</p>' for part in body.splitlines() if part.strip())
            body_markup = EvidenceMarkupFilter()
            body_markup.feed(body)
            body_markup.close()
            segments.append(('jsonld:articleBody', remove_noise_blocks(''.join(body_markup.parts))))
        segments.append(('html', evidence_body_scope(''.join(page.parts), filtered=True)))
    elif discovery_lead:
        segments.append(('discovery', f'<p>{html.escape(discovery_lead)}</p>'))
    units = []
    references = []
    prior_origins: set[str] = set()
    for origin, body in segments:
        embedded = EmbeddedReferenceExtractor(origin + ":body")
        embedded.feed(body)
        embedded.close()
        references.extend(embedded.references)
        parser = EvidenceTextExtractor()
        parser.feed(body)
        parser.close()
        segment_texts = set()
        for ordinal, (kind, value, container) in enumerate(parser.units):
            if value in prior_origins:
                continue
            segment_texts.add(value)
            key = f'{article_id}\0{origin}\0{ordinal}\0{kind}\0{value}'
            unit_id = hashlib.sha256(key.encode()).hexdigest()[:24]
            units.append(EvidenceUnit(unit_id, kind, value, origin, ordinal, container))
        prior_origins.update(segment_texts)
    if not raw_lead:
        raw_lead = next((unit.text for unit in units if unit.kind not in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr'}), '')
    return ArticleEvidence(article_id, source, url, title, strip_tags(raw_lead), '', tuple(units),
                           publication_candidates, extraction_path='detail' if text is not None else 'discovery_fallback',
                           discovery_title=fallback_title, discovery_lead=discovery_lead,
                           embedded_references=tuple(references))


def capture_article_title_evidence(source: str, url: str, title: str,
                                   summary: str = '', facts: tuple[str, ...] = ()) -> ArticleEvidence:
    """Preserve actual Article input fields, never reconstruct a fetched body."""
    article_id = hashlib.sha256(f'{source}\0{url}'.encode()).hexdigest()[:24]
    units = []
    fields = [('title', 'article:title', title), ('summary', 'article:summary', summary)]
    fields.extend(('selected_fact', f'article:key_facts:{index}', fact) for index, fact in enumerate(facts))
    for kind, origin, text in fields:
        if not text:
            continue
        unit_id = hashlib.sha256(f'{article_id}\0{origin}\0{0}\0{kind}\0{text}'.encode()).hexdigest()[:24]
        units.append(EvidenceUnit(unit_id, kind, text, origin, 0))
    return ArticleEvidence(article_id, source, url, title, '', '', tuple(units),
                           extraction_path='article_input', discovery_lead=summary)


@lru_cache(maxsize=32768)
def clean_sentence(value: str) -> str:
    value = strip_tags(value)
    value = _compiled_markup_rule(r"\s+", 0).sub(" ", value, 0).strip()
    value = _compiled_markup_rule(r"\s+([,.;:!?])", 0).sub(r"\1", value, 0)
    return value



def ascii_lexical_term_present(text: str, term: str) -> bool:
    offset = 0
    while True:
        index = text.find(term, offset)
        if index < 0:
            return False
        end = index + len(term)
        if (
            (index == 0 or not (text[index - 1].isascii() and text[index - 1].isalnum()))
            and (end == len(text) or not (text[end].isascii() and text[end].isalnum()))
        ):
            return True
        offset = index + 1



@lru_cache(maxsize=16384)
def term_present(text: str, term: str) -> bool:
    normalized = term.lower()
    if normalized == "wwdc":
        search_text = text.lower()
        offset = 0
        while True:
            index = search_text.find("wwdc", offset)
            if index < 0:
                return False
            end = index + 4
            while end < len(search_text) and end - index < 8 and search_text[end].isdigit():
                end += 1
            if (
                (index == 0 or not (search_text[index - 1].isascii() and search_text[index - 1].isalnum()))
                and (end == len(search_text) or not (search_text[end].isascii() and search_text[end].isalnum()))
            ):
                return True
            offset = index + 1
    if not term.isascii():
        return term in text
    return ascii_lexical_term_present(text, normalized)



@lru_cache(maxsize=4096)
def normalized_term_tuple(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term.lower() for term in terms)



@lru_cache(maxsize=32768)
def cached_score_terms(lower: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term_present(lower, term))



def score_terms(text: str, terms: Iterable[str]) -> int:
    lower = text.lower()
    normalized_terms = normalized_term_tuple(tuple(terms))
    return cached_score_terms(lower, normalized_terms)



def inline_media_marker_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Locate serialized media metadata and shopping cards, not ordinary prose."""
    spans = []
    for match in _compiled_markup_rule(r"\[\s*(?P<kind>Image|Video|Product):\s*(?P<caption>[^\[\]]*?)\s*(?P<url>https?://[^\s\[\]]+)\s*\]", re.I).finditer(text):
        caption = match.group("caption")
        if match.group('kind').lower() == 'product' or not caption.strip():
            spans.append(match.span())
        else:
            # Caption prose remains original text; only its serialization label
            # and trailing resource address are metadata.
            spans.append((match.start(), match.start("caption")))
            spans.append((match.end("caption"), match.end()))
    return tuple(spans)


def clean_fact_text(value: str) -> str:
    value = strip_tags(value)
    for start, end in reversed(inline_media_marker_spans(value)):
        value = value[:start] + " " + value[end:]
    value = _compiled_markup_rule(r"\s+", 0).sub(" ", value, 0).strip()
    value = _compiled_markup_rule(r"^(?:App Review|Account Fraud|Ratings and Reviews|Payment and Credit Card Fraud|Keeping Kids Safe)\s+", 0).sub("", value, 0)
    value = _compiled_markup_rule(r"\s+([,.;:!?])", 0).sub(r"\1", value, 0)
    return value



def add_unique_text(
    parts: list[str],
    seen: set[str],
    value: str,
    max_chars: int = 900,
    min_chars: int = 35,
) -> bool:
    cleaned = clean_fact_text(value)
    if len(cleaned) > max_chars:
        sentences = _compiled_markup_rule(r"(?<=[.!?。！？])\s+", 0).split(cleaned, 0)
        shortened = ""
        for sentence in sentences:
            next_value = f"{shortened} {sentence}".strip()
            if len(next_value) > max_chars:
                break
            shortened = next_value
        cleaned = shortened or cleaned[:max_chars].rstrip()
    if len(cleaned) < min_chars:
        return False
    compact = _compiled_markup_rule(r"[^0-9a-z\u4e00-\u9fff]+", 0).sub(" ", cleaned.lower(), 0).strip()
    if not compact:
        return False
    key = compact[:180]
    for existing in seen:
        if key in existing or existing in key:
            return False
    parts.append(cleaned)
    seen.add(key)
    return True



def is_roundup_article_title(title: str) -> bool:
    lower = title.lower()
    return score_terms(
        lower,
        [
            "早报",
            "科技早报",
            "科技早参",
            "每日早报",
            "daily brief",
            "daily briefing",
            "morning brief",
            "morning briefing",
            "roundup",
        ],
    ) > 0



def clean_roundup_item_text(value: str) -> str:
    cleaned = clean_fact_text(value)
    cleaned = _compiled_markup_rule(r">>\s*查看详情", 0).sub("", cleaned, 0)
    cleaned = _compiled_markup_rule(r"^\d{1,2}[、.．]\s*", 0).sub("", cleaned, 0)
    return clean_fact_text(cleaned)



def split_roundup_item_candidates(value: str) -> list[str]:
    cleaned = clean_roundup_item_text(value)
    if not cleaned:
        return []
    rough_parts = _compiled_markup_rule(r"[；;]\s*|(?=\b\d{1,2}[、.．])|(?=\s\d{1,2}[、.．])", 0).split(cleaned, 0)
    parts: list[str] = []
    for part in rough_parts:
        part = clean_roundup_item_text(part)
        if len(part) >= 18:
            parts.append(part)
    return parts or [cleaned]



def roundup_title_from_item(value: str) -> str:
    cleaned = clean_roundup_item_text(value)
    first_sentence = _compiled_markup_rule(r"(?<=[.!?。！？])\s+", 0).split(cleaned, 0)[0]
    first_sentence = _compiled_markup_rule(r"\s*>>\s*查看详情.*$", 0).sub("", first_sentence, 0)
    if len(first_sentence) <= 140:
        return first_sentence
    return first_sentence[:137].rstrip() + "..."


def find_json_key(value: Any, keys: set[str]) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str):
                return item
        for item in value.values():
            found = find_json_key(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_json_key(item, keys)
            if found:
                return found
    return ""



class ArticleTextExtractor(HTMLParser):
    block_tags = {"p", "li", "h2", "h3", "tr", "blockquote"}
    div_class_fragments = (
        "pagebody-copy",
        "article-copy",
        "body-copy",
        "entry-content",
        "post-content",
        "story-content",
    )
    void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.units: list[tuple[str, str]] = []
        self._capture_tag: str | None = None
        self._capture_kind = ""
        self._depth = 0
        self._parts: list[str] = []

    def _is_block(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in self.block_tags:
            return True
        if tag != "div":
            return False
        classes = " ".join(value or "" for name, value in attrs if name.lower() == "class")
        return any(fragment in classes for fragment in self.div_class_fragments)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._capture_tag:
            if tag == "br":
                self._parts.append(" ")
            elif tag in {"td", "th"} and self._capture_kind == "tr" and self._parts:
                self._parts.append(" | ")
            if tag not in self.void_tags:
                self._depth += 1
            return
        if self._is_block(tag, attrs):
            self._capture_tag = tag
            self._capture_kind = tag
            self._depth = 1
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture_tag:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = _compiled_markup_rule(r"\s+", 0).sub(" ", "".join(self._parts), 0).strip()
        min_len = 20 if self._capture_kind in {"li", "tr"} else 30
        if len(text) >= min_len:
            self.units.append((self._capture_kind, html.unescape(text)))
        self._capture_tag = None
        self._capture_kind = ""
        self._parts = []



def extract_text_units(text: str) -> list[tuple[str, str]]:
    scoped_text = article_scope(text)
    parser = ArticleTextExtractor()
    try:
        parser.feed(scoped_text)
    except Exception:
        parser.units = []
    units = parser.units
    if units:
        return units

    fallback_units: list[tuple[str, str]] = []
    for match in _compiled_markup_rule(r"(?is)<(?P<tag>p|li|h2|h3|tr)\b[^>]*>(?P<body>.*?)</(?P=tag)>", 0).finditer(scoped_text):
        cleaned = strip_tags(match.group("body"))
        min_len = 20 if match.group("tag").lower() in {"li", "tr"} else 30
        if len(cleaned) >= min_len:
            fallback_units.append((match.group("tag").lower(), cleaned))
    return fallback_units



def split_fact_candidates(tag: str, value: str) -> list[str]:
    if tag in {"li", "tr"} or len(value) <= 700:
        return [value]
    parts = [
        cleaned
        for part in _compiled_markup_rule(r"(?<=[.!?。！？])\s+", 0).split(value, 0)
        if (cleaned := clean_fact_text(part))
    ]
    return parts or [value]



def combine_summaries(primary: str, secondary: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in [primary, secondary]:
        cleaned = clean_sentence(value)
        if not cleaned:
            continue
        for sentence in _compiled_markup_rule(r"(?<=[.!?。！？])\s+", 0).split(cleaned, 0):
            sentence = clean_sentence(sentence)
            if not sentence:
                continue
            key = sentence.lower()[:120]
            if key in seen:
                continue
            parts.append(sentence)
            seen.add(key)
            if len(parts) >= 8:
                break
    return " ".join(parts)



def _publication_time_markup(text: str) -> str:
    """Remove explicit non-publication time elements before any date fallback."""
    attributes = _compiled_markup_rule(
        r'''\b(?:itemprop|property|class)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''', re.I)
    role = _compiled_markup_rule(r"(?:^|[^a-z])(?:datemodified|uploaddate|modified|updated|lastmod)(?:$|[^a-z])", re.I)
    return _compiled_markup_rule(r"(?is)<time\b([^>]*)>(.*?)</time>", 0).sub(
        lambda match: '' if any(role.search(' '.join(value or '' for value in attr.groups()))
            for attr in attributes.finditer(match.group(1))) else match.group(), text)


def _publication_visible_markup(text: str) -> str:
    """Keep the primary article and its preceding byline, not following cards."""
    article = _compiled_markup_rule(r'(?is)<article\b[^>]*>', 0).search(text)
    if article:
        return text[:article.end()] + balanced_element_inner(text, article.start(), 'article')
    return text


PUBLICATION_DATE_PATTERNS = [
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}(?:,)?\s+"
    r"(?:at\s+)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|AM|PM)?\s*"
    r"(?:PST|PDT|PT|EST|EDT|ET|GMT|UTC|[+-]\d{2}:?\d{2})?",
    r"(?:\d{4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*日\s*"
    r"\d{1,2}[:：]\d{2}(?:[:：]\d{2})?",
    r"\d{4}/\d{1,2}/\d{1,2}\s+"
    r"\d{1,2}:\d{2}(?::\d{2})?",
    r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2})?"
    r"(?:Z|[+-]\d{2}:?\d{2})?",
]

def publication_visible_fields(text: str) -> list[tuple[str, str]]:
    """Read locally marked publication fields in document order."""
    published_role = _compiled_markup_rule(r'(?:^|[^a-z])(?:datepublished|datecreated|published|pubdate|pubtime|byline|dateline|post-date|article-date)(?:$|[^a-z])', re.I)
    excluded = _compiled_markup_rule(r'(?:^|[^a-z])(?:modified|updated|datemodified|uploaddate|related|recommendations|story-card|event-date|startdate|enddate)(?:$|[^a-z])', re.I)
    label = _compiled_markup_rule(r'^\s*(?:published|posted)\b|^\s*(?:发布时间|发布日期|发布于|发表于)', re.I)
    updated = _compiled_markup_rule(r'\b(?:last\s+)?updated\b|更新时间|最后更新|更新于', re.I)
    dates = _compiled_markup_rule('(?:' + '|'.join(PUBLICATION_DATE_PATTERNS) + ')', re.I)
    weekday = _compiled_markup_rule(r'^\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[,\s]+', re.I)

    class PublicationParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.fields = [], []
            self.position = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            attributes = ' '.join(attrs.get(key, '') for key in ('id', 'class', 'itemprop', 'property'))
            parent = self.stack[-1] if self.stack else None
            blocked = (tag in {'script', 'style', 'template', 'pre', 'code', 'nav', 'aside', 'footer'}
                       or bool(excluded.search(attributes))
                       or any(value.rstrip('/').rsplit('/', 1)[-1] == 'Event' for value in attrs.get('itemtype', '').split())
                       or bool(parent and parent['blocked']))
            marked = bool(published_role.search(attributes))
            # Only a publication label/byline can own a nested time. A generic
            # metadata container does not turn its article prose into a byline.
            context = marked or bool(parent and (parent['context'] or parent['label']))
            prose = tag in {'p', 'blockquote', 'li', 'a'} or bool(parent and parent['prose'])
            if tag not in EvidenceTextExtractor.void_tags:
                self.stack.append(dict(tag=tag, blocked=blocked, marked=marked, context=context, prose=prose,
                    timestamp=attrs.get('datetime', '') if tag == 'time' else '', parts=[], children=False,
                    label=False, position=self.position))
                self.position += 1
                if parent:
                    parent['children'] = True

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

        def handle_data(self, data):
            if self.stack and not self.stack[-1]['blocked']:
                node = self.stack[-1]
                if not node['parts'] and label.search(data):
                    node['label'] = True
                node['parts'].append(data)

        def handle_endtag(self, tag):
            index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]['tag'] == tag), None)
            if index is None:
                return
            node = self.stack[index]
            del self.stack[index:]
            value = ' '.join(' '.join(node['parts']).split())
            if node['blocked']:
                return
            if self.stack:
                self.stack[-1]['parts'].append(value)
            value = updated.split(value, maxsplit=1)[0].strip()
            plain = weekday.sub('', value)
            standalone = (not node['prose'] and not node['children'] and bool(dates.fullmatch(plain)))
            time_field = node['tag'] == 'time' and (node['context'] or standalone)
            if time_field or node['marked'] or node['label'] or standalone:
                # Keep the first date of this publication field. A second date
                # may describe an update or an event, not another publication.
                match = dates.search(value)
                if time_field and node['timestamp'] and (value or node['marked']):
                    self.fields.append((node['position'], node['timestamp'], value))
                elif match:
                    self.fields.append((node['position'], '', match.group()))

    parser = PublicationParser()
    parser.feed(_publication_visible_markup(text)[:120_000])
    return [(stamp, value) for _, stamp, value in sorted(parser.fields)]


def extract_time_candidates(text: str, source_name: str = '') -> list[tuple[str, str]]:
    text = _publication_time_markup(text)
    candidates: list[tuple[str, str]] = []
    if source_name == 'IT之家':
        published = visible_element_text(text, 'pubtime_baidu')
        if published:
            candidates.append((published, 'source publication field'))
    if source_name == '快科技':
        # This publisher's article metadata is a publication timestamp, unlike
        # preorder/release dates mentioned in the article's prose.
        for script in _compiled_markup_rule(r'<script\b[^>]*>(.*?)</script>', re.I | re.S).finditer(text):
            # Preserve quoted values while removing inactive comment text.
            code = _compiled_markup_rule(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|/\*.*?\*/|//[^\r\n]*''', re.S).sub(
                lambda match: match.group(1) or ' ', script.group(1))
            published = _compiled_markup_rule(r"(?:^|[;\r\n])\s*var\s+g_PostDateStr\s*=\s*new\s+Date\(\s*['\"]"
                r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)['\"]\s*\)", 0).search(code)
            if published:
                candidates.append((published.group(1), 'source publication metadata'))
                break
    for obj in json_ld_objects(text):
        found = find_json_key(obj, {"datePublished", "dateCreated"})
        if found:
            candidates.append((found, "json-ld datePublished"))

    for names, label in [
        (
            [
                "article:published_time",
                "article:published",
                "datePublished",
                "date",
                "pubdate",
                "publish_date",
                "dc.date",
                "dc.date.issued",
            ],
            "meta published",
        ),
    ]:
        found = meta_content(text, names)
        if found:
            candidates.append((found, label))

    fields = publication_visible_fields(text)
    for timestamp, value in fields:
        if timestamp:
            candidates.append((timestamp, "time datetime"))
            if value:
                candidates.append((value, "time text"))
    text_only = " ".join(value for _timestamp, value in fields)
    body_dates = sorted((match.start(), match.group(0))
        for pattern in PUBLICATION_DATE_PATTERNS
        for match in _compiled_markup_rule(pattern, re.I).finditer(text_only))
    for _, raw in body_dates:
        if (raw, "body date pattern") not in candidates:
            candidates.append((raw, "body date pattern"))
        if len(candidates) > 20:
            break
    return candidates



def extract_apple_newsroom_time_candidates(text: str) -> list[tuple[str, str, bool]]:
    """Return Apple Newsroom publication candidates only.

    Newsroom pages often refresh dateModified and VideoObject uploadDate when
    media assets change. Those values are not the article's publication time.
    """
    text = _publication_time_markup(text)
    candidates: list[tuple[str, str, bool]] = []
    for obj in json_ld_objects(text):
        for node in iter_json_ld_nodes(obj):
            if not isinstance(node, dict):
                continue
            type_names = json_type_names(node)
            if "NewsArticle" not in type_names and "Article" not in type_names:
                continue
            raw = node.get("datePublished") or node.get("dateCreated")
            if isinstance(raw, str) and raw.strip():
                candidates.append((raw, "apple newsroom datePublished", True))

    for names, label in [
        (
            [
                "article:published_time",
                "article:published",
                "datePublished",
                "pubdate",
                "publish_date",
                "dc.date",
                "dc.date.issued",
            ],
            "apple newsroom meta published",
        ),
    ]:
        found = meta_content(text, names)
        if found:
            candidates.append((found, label, True))

    text = _publication_visible_markup(text)
    visible_date = _compiled_markup_rule(r"(?is)<[^>]+class=['\"][^'\"]*category-eyebrow__date[^'\"]*['\"][^>]*>(.*?)</[^>]+>", 0).search(text)
    if visible_date:
        cleaned = strip_tags(visible_date.group(1))
        if cleaned:
            candidates.append((cleaned, "apple newsroom visible date", True))

    for timestamp, value in publication_visible_fields(text):
        if timestamp:
            candidates.append((timestamp, "apple newsroom time datetime", True))
            if value:
                candidates.append((value, "apple newsroom time text", True))
    return candidates


TIMEZONE_ABBREVIATIONS = {
    "UTC": timezone.utc,
    "GMT": timezone.utc,
    "Z": timezone.utc,
    "PST": timezone(timedelta(hours=-8), "PST"),
    "PDT": timezone(timedelta(hours=-7), "PDT"),
    "MST": timezone(timedelta(hours=-7), "MST"),
    "MDT": timezone(timedelta(hours=-6), "MDT"),
    "CST": timezone(timedelta(hours=-6), "CST"),
    "CDT": timezone(timedelta(hours=-5), "CDT"),
    "EST": timezone(timedelta(hours=-5), "EST"),
    "EDT": timezone(timedelta(hours=-4), "EDT"),
}


GENERIC_TIMEZONES = {
    "PT": "America/Los_Angeles",
    "ET": "America/New_York",
}


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def zoneinfo_or_none(name: str | None) -> Any:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None
    except Exception:
        return None


def tz_from_token(token: str | None, default_tz_name: str) -> Any:
    if token:
        normalized = token.upper().replace(".", "")
        if normalized.startswith(("+", "-")):
            compact = normalized.replace(":", "")
            if _compiled_markup_rule(r"[+-]\d{4}", 0).fullmatch(compact):
                sign = 1 if compact[0] == "+" else -1
                hours = int(compact[1:3])
                minutes = int(compact[3:5])
                return timezone(sign * timedelta(hours=hours, minutes=minutes))
        if normalized in TIMEZONE_ABBREVIATIONS:
            return TIMEZONE_ABBREVIATIONS[normalized]
        if normalized in GENERIC_TIMEZONES:
            tz = zoneinfo_or_none(GENERIC_TIMEZONES[normalized])
            if tz is not None:
                return tz
    tz = zoneinfo_or_none(default_tz_name)
    return tz or timezone.utc


def localize_naive(value: datetime, default_tz_name: str, tz_token: str | None = None) -> datetime:
    return value.replace(tzinfo=tz_from_token(tz_token, default_tz_name))


def parse_datetime_value(raw_value: str, default_tz_name: str, *,
                         current_year: Callable[[], int] = lambda: datetime.now().year) -> datetime | None:
    if not raw_value:
        return None
    raw = html.unescape(strip_tags(raw_value))
    raw = raw.replace("\xa0", " ")
    raw = _compiled_markup_rule(r"\s+", 0).sub(" ", raw, 0).strip()
    raw = _compiled_markup_rule(r"^(Published|Updated|Posted|Last updated)\s*:?\s*", re.I).sub("", raw, 0)
    raw = raw.strip(" -|")

    iso_match = _compiled_markup_rule(r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?", 0).search(raw)
    if iso_match:
        iso_text = iso_match.group(0).replace("Z", "+00:00")
        if "T" not in iso_text:
            iso_text = iso_text.replace(" ", "T", 1)
        if _compiled_markup_rule(r"[+-]\d{4}$", 0).search(iso_text):
            iso_text = f"{iso_text[:-2]}:{iso_text[-2:]}"
        iso_text = _compiled_markup_rule(r"(\.\d{6})\d+(?=(?:[+-]\d{2}:?\d{2})?$)", 0).sub(r"\1", iso_text, 0)
        try:
            parsed = datetime.fromisoformat(iso_text)
            if parsed.tzinfo is None:
                parsed = localize_naive(parsed, default_tz_name)
            return parsed
        except ValueError:
            pass

    slash_match = _compiled_markup_rule(r"(\d{4})/(\d{1,2})/(\d{1,2})\s+"
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?", 0).search(raw)
    if slash_match:
        year_s, month_s, day_s, hour_s, minute_s, second_s = slash_match.groups()
        parsed = datetime(
            int(year_s),
            int(month_s),
            int(day_s),
            int(hour_s),
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name)

    month_pattern = (
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)"
    )
    natural_match = re.search(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*"
        + month_pattern
        + r"\s+(\d{1,2}),?\s+(\d{4})(?:,)?(?:\s+(?:at\s+)?)?"
        + r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
        + r"(a\.?m\.?|p\.?m\.?|AM|PM)?\s*([A-Z]{1,4}|[+-]\d{2}:?\d{2})?",
        raw,
        re.I,
    )
    if natural_match:
        month_name, day_s, year_s, hour_s, minute_s, second_s, ampm, tz_token = (
            natural_match.groups()
        )
        hour = int(hour_s)
        if ampm:
            ampm_clean = ampm.lower().replace(".", "")
            if ampm_clean == "pm" and hour != 12:
                hour += 12
            elif ampm_clean == "am" and hour == 12:
                hour = 0
        parsed = datetime(
            int(year_s),
            MONTHS[month_name.lower().rstrip(".")],
            int(day_s),
            hour,
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name, tz_token)

    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed:
            if parsed.tzinfo is None:
                parsed = localize_naive(parsed, default_tz_name)
            return parsed
    except Exception:
        pass

    chinese_match = _compiled_markup_rule(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*"
        r"(\d{1,2})[:：](\d{2})(?:[:：](\d{2}))?", 0).search(raw)
    if chinese_match:
        year_s, month_s, day_s, hour_s, minute_s, second_s = chinese_match.groups()
        year = int(year_s) if year_s else current_year()
        parsed = datetime(
            year,
            int(month_s),
            int(day_s),
            int(hour_s),
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name)

    numeric_match = _compiled_markup_rule(r"(\d{1,2})/(\d{1,2})/(\d{4})[,\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
        r"(a\.?m\.?|p\.?m\.?|AM|PM)?\s*([A-Z]{1,4}|[+-]\d{2}:?\d{2})?", re.I).search(raw)
    if numeric_match:
        month_s, day_s, year_s, hour_s, minute_s, second_s, ampm, tz_token = (
            numeric_match.groups()
        )
        hour = int(hour_s)
        if ampm:
            ampm_clean = ampm.lower().replace(".", "")
            if ampm_clean == "pm" and hour != 12:
                hour += 12
            elif ampm_clean == "am" and hour == 12:
                hour = 0
        parsed = datetime(
            int(year_s),
            int(month_s),
            int(day_s),
            hour,
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name, tz_token)

    return None


def parse_date_only_value(raw_value: str, default_tz_name: str) -> datetime | None:
    if not raw_value:
        return None
    raw = html.unescape(strip_tags(raw_value))
    raw = raw.replace("\xa0", " ")
    raw = _compiled_markup_rule(r"\s+", 0).sub(" ", raw, 0).strip()
    raw = raw.strip(" -|")
    iso_match = _compiled_markup_rule(r"\b(\d{4})-(\d{2})-(\d{2})(?:Z)?\b", 0).search(raw)
    if iso_match:
        year_s, month_s, day_s = iso_match.groups()
        parsed = datetime(int(year_s), int(month_s), int(day_s), 12, 0, 0)
        return localize_naive(parsed, default_tz_name)

    month_pattern = (
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)"
    )
    natural_match = re.search(
        month_pattern + r"\s+(\d{1,2}),?\s+(\d{4})",
        raw,
        re.I,
    )
    if natural_match:
        month_name, day_s, year_s = natural_match.groups()
        parsed = datetime(
            int(year_s),
            MONTHS[month_name.lower().rstrip(".")],
            int(day_s),
            12,
            0,
            0,
        )
        return localize_naive(parsed, default_tz_name)
    return None
