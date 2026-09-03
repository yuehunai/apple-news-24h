"""Deterministic article-level event reconciliation.

The crawler's source-specific matcher remains a fast seed generator. This
module then treats every seed as provisional: structured article identities
split incompatible actions and reconcile compatible cross-source coverage
without relying on publication-specific title keywords.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations
import re
import unicodedata
from typing import Callable, Iterable, Sequence, TypeVar

from .event_identity import (
    EVIDENCE_BACKED_COMPONENTS,
    COMPONENT_PATTERNS,
    EventIdentity,
    LEAD_IDENTITY_COMPONENTS,
    PRODUCT_PATTERNS,
    is_direct_apple_product_lifecycle_action,
    is_direct_first_party_named_object_change,
    is_material_apple_device_operational_deployment,
    is_third_party_app_action_on_apple_platform,
    primary_assertion_components,
    quantified_apple_company_performance_subject,
)
from .event_matcher import FIRST_PARTY_SERVICE_PRODUCTS, identity_pair_decision


ArticleT = TypeVar("ArticleT")


STRUCTURED_EVIDENCE_KEY_PREFIXES = (
    "structured-canonical-title:",
    "structured-attributed-measure:",
    "structured-component-measure:",
    "structured-component-period:",
    "structured-entity-component:",
    "structured-legal-settlement:",
    "structured-claim-status:",
    "structured-market-result:",
)


@dataclass(frozen=True)
class ReconciliationProfile:
    event_keys: frozenset[str]
    boundary_keys: frozenset[str]
    exact_facets: frozenset[str] = frozenset()
    separation_keys: frozenset[str] = frozenset()
    defer_reason: str = ""
    category_hint: str = ""
    observed_category: str = ""
    hard_boundary: str = ""
    identity: EventIdentity | None = None
    relevance_tier: str = "strong"
    trusted_direct_action: bool = False
    promotion_reason: str = ""


_GENERIC_SUBJECT_WORDS = {
    "a",
    "an",
    "apple",
    "bigger",
    "everything",
    "if",
    "ios",
    "macos",
    "message",
    "new",
    "next",
    "report",
    "some",
    "the",
    "these",
    "this",
    "watchos",
}


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip()


def _canonical_title(value: str) -> str:
    """Remove publisher chrome while preserving the reported headline."""
    title = _normalized(value)
    publisher_suffix = (
        r"\s+(?:[-|]\s*)?(?:apple\s+苹果\s+-\s+)?"
        r"(?:9to5mac|appleinsider|cnbeta(?:\.com)?|macrumors|the\s+verge|"
        r"it\s*之家|快科技|爱范儿)\.?$"
    )
    previous = ""
    while title != previous:
        previous = title
        title = re.sub(publisher_suffix, "", title).strip(" -|")
    return title


def _contains(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def _has_absolute_calendar_date(value: str) -> bool:
    text = _normalized(value)
    return bool(
        re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", text)
        or re.search(
            r"\b(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?\b",
            text,
        )
        or re.search(r"\b\d{1,2}\s+月\s*\d{1,2}\s*[日号]\b", text)
    )


def _primary_assertion_scope(title: str, lead: str) -> tuple[str, str]:
    """Return title and first substantive lead sentence for action identity.

    Later lead sentences often summarize related supply-chain, legal, or product
    context.  They remain useful as facts, but must not redefine the article's
    primary action and bridge otherwise independent events.
    """
    title_scope = _normalized(title)
    lead_scope = re.split(
        r"(?:[。！？]|(?<=[.!?])\s+)",
        _normalized(lead),
        maxsplit=1,
    )[0]
    return title_scope, f"{title_scope}. {lead_scope}".strip()


def _named_transit_card_subject(value: str) -> str:
    """Return a stable named-card subject without publisher-specific aliases."""
    text = _normalized(value)
    chinese_matches = list(
        re.finditer(r"([\u4e00-\u9fff]{2,12})(?=交通卡)", text)
    )
    if chinese_matches:
        subject = chinese_matches[-1].group(1)
        for marker in ("上线", "支持", "添加", "推出", "开通", "接入", "新增"):
            if marker in subject:
                subject = subject.rsplit(marker, 1)[-1]
        # Chinese transit brands commonly end in 通 (for example a city-branded
        # pass). Keep the distinctive terminal name instead of a preceding city
        # or launch phrase that another headline may omit.
        if subject.endswith("通") and len(subject) > 3:
            subject = subject[-3:]
        elif len(subject) > 6:
            subject = subject[-6:]
        if len(subject) >= 2:
            return subject
    english_match = re.search(
        r"\b([a-z][a-z0-9' -]{1,32})\s+transit\s+card\b",
        text,
    )
    if not english_match:
        return ""
    subject = english_match.group(1)
    subject = re.sub(
        r"^(?:apple|iphone|wallet|now|finally|adds?|supports?|launches?|gets?)\s+",
        "",
        subject,
    ).strip(" -")
    return re.sub(r"[^a-z0-9]+", "-", subject).strip("-")


def _reported_hardware_launch_subjects(
    title: str,
    identity: EventIdentity,
) -> set[str]:
    """Return title products tied to one concrete reported launch window."""
    text = _normalized(title)
    launch_window = re.compile(
        r"\b(?:days? away|within (?:the )?(?:next )?few days|coming days|"
        r"set to launch before|could launch before|launch before|"
        r"(?:launch|release|ship|arrive|debut).{0,24}(?:next month|"
        r"in (?:september|october)|by (?:late )?(?:september|october))|"
        r"(?:expected|scheduled|reportedly set).{0,20}(?:launch|release|arrive))\b|"
        r"(?:未来几天|数日)(?:之)?内.{0,8}(?:发布|推出|亮相)|"
        r"(?:发布|推出|亮相).{0,8}(?:未来几天|数日)(?:之)?内|"
        r"(?:发布会|活动)(?:之)?前.{0,8}(?:发布|推出|亮相)|"
        r"(?:发布|推出|亮相).{0,8}(?:发布会|活动)(?:之)?前|"
        r"(?:有望|预计|计划|最快).{0,24}(?:\d{1,2}\s*月|下月|明年)"
        r".{0,18}(?:发布|推出|亮相|上市)|"
        r"(?:\d{1,2}\s*月|下月|明年).{0,18}(?:发布|推出|亮相|上市)"
    )
    aliases = {
        "airpods": (r"(?<![a-z0-9])airpods?(?![a-z0-9])",),
        "apple-home-hub": (r"(?<![a-z0-9])(?:apple\s+)?home\s+hub(?![a-z0-9])", r"家庭中枢"),
        "apple-tv-hardware": (r"(?<![a-z0-9])apple\s+tv(?:\s+4k)?(?![a-z0-9])",),
        "apple-watch": (r"(?<![a-z0-9])apple\s+watch(?![a-z0-9])",),
        "beats": (r"(?<![a-z0-9])beats(?![a-z0-9])",),
        "foldable-iphone": (r"(?<![a-z0-9])iphone\s+(?:fold|ultra)(?![a-z0-9])", r"折叠屏?\s*iphone"),
        "homepod": (r"(?<![a-z0-9])homepod(?![a-z0-9])",),
        "imac": (r"(?<![a-z0-9])imac(?![a-z0-9])",),
        "ipad": (r"(?<![a-z0-9])ipad(?![a-z0-9])",),
        "ipad-air": (r"(?<![a-z0-9])ipad\s+air(?![a-z0-9])",),
        "ipad-mini": (r"(?<![a-z0-9])ipad\s+mini(?![a-z0-9])",),
        "ipad-pro": (r"(?<![a-z0-9])ipad\s+pro(?![a-z0-9])",),
        "iphone": (r"(?<![a-z0-9])iphone(?![a-z0-9])",),
        "mac-mini": (r"(?<![a-z0-9])mac\s+mini(?![a-z0-9])",),
        "mac-pro": (r"(?<![a-z0-9])mac\s+pro(?![a-z0-9])",),
        "mac-studio": (r"(?<![a-z0-9])mac\s+studio(?![a-z0-9])",),
        "macbook": (r"(?<![a-z0-9])macbook(?:\s+(?:air|pro))?(?![a-z0-9])",),
        "vision-pro": (r"(?<![a-z0-9])vision\s+pro(?![a-z0-9])",),
    }
    subjects: set[str] = set()
    for product in identity.title_products:
        for alias in aliases.get(product, ()):
            for match in re.finditer(alias, text):
                suffix = text[match.end() : min(len(text), match.end() + 52)]
                prefix = text[max(0, match.start() - 52) : match.start()]
                launch_before_product = re.search(
                    r"(?:within (?:the )?(?:next )?few days|coming days|未来几天|数日|"
                    r"20\d{2}\s*q[1-4]|\d{1,2}\s*月|明年(?:第?[一二三四1-4]季度)?)"
                    r".{0,24}(?:launch|release|发布|推出|亮相)"
                    r"(?:(?:\s+(?:a|the|new))|(?:\s*新款))?\s*$",
                    prefix,
                )
                direct_launch_before_product = bool(
                    not re.search(r"\bbefore\s*$", prefix)
                    and re.search(
                        r"\b(?:could|will|may|might|plans? to|expected to|set to)?\s*"
                        r"(?:launch|release|debut|ship|announce)"
                        r"(?:\s+(?:one|two|three|a|the|new|next|fresh))*\s*$",
                        prefix,
                    )
                )
                if launch_window.search(suffix) or launch_before_product or direct_launch_before_product:
                    subjects.add(product)
                    break
            if product in subjects:
                break
    return subjects


def _short_lead_scope(lead: str, *, sentences: int = 2, limit: int = 900) -> str:
    """Return a bounded lead window for high-specificity typed assertions."""
    parts = re.split(
        r"(?:[。！？]|(?<=[.!?])\s+)",
        _normalized(lead),
        maxsplit=sentences,
    )
    return " ".join(part for part in parts[:sentences] if part).strip()[:limit]


def _subject_tokens(title: str, identity: EventIdentity) -> set[str]:
    subjects = set(identity.title_named_subjects or identity.named_subjects)
    lower = _normalized(title)
    possessive = re.match(r"^([a-z][a-z0-9.+-]{1,36})'s\b", lower)
    if possessive:
        subjects.add(possessive.group(1))
    leading = re.match(
        r"^([a-z][a-z0-9.+-]{1,36})(?:\s+(?:ceo|briefly|app|update|firmware|browser))\b",
        lower,
    )
    if leading:
        subjects.add(leading.group(1))
    # Latin product or company names remain stable in translated Chinese
    # headlines and are useful when no language-independent facet exists.
    for token in re.findall(r"\b[a-z][a-z0-9.+-]{2,30}\b", lower[:100]):
        if token not in _GENERIC_SUBJECT_WORDS:
            subjects.add(token)
            break
    return {subject for subject in subjects if subject not in _GENERIC_SUBJECT_WORDS}


def _display_metrics(text: str) -> set[str]:
    metrics = set()
    for value in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:-?inch|inches|英寸|寸)", text):
        normalized = value.rstrip("0").rstrip(".") if "." in value else value
        metrics.add(normalized)
    return metrics


def _evidence_measurements(title: str, lead: str) -> set[str]:
    """Normalize typed quantities from the headline and primary assertion.

    Measurements are evidence, not topics.  They only reconcile articles when
    paired with an independently extracted subject/component projection, so a
    shared date or model number cannot become an event boundary by itself.
    """
    lead_sentences = re.split(
        r"(?:[。！？]|(?<=[.!?])\s+)",
        _normalized(lead),
        maxsplit=2,
    )
    evidence_lead = " ".join(lead_sentences[:2])
    scope = f"{_normalized(title)}. {evidence_lead}"
    values: set[str] = set()
    for value in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%", scope):
        normalized = value.rstrip("0").rstrip(".") if "." in value else value
        values.add(f"percent:{normalized}")
    for value in re.findall(r"(?<!\d)(20\d{2})(?!\d)", scope):
        values.add(f"year:{value}")
    quarter_patterns = (
        r"(?<!\d)(20\d{2})\s*年?\s*[- ]?q([1-4])(?!\d)",
        r"\bq([1-4])\s*(20\d{2})\b",
        r"(?<!\d)(20\d{2})\s*年?\s*第?([一二三四1234])季度",
    )
    chinese_quarters = {"一": "1", "二": "2", "三": "3", "四": "4"}
    for index, pattern in enumerate(quarter_patterns):
        for match in re.finditer(pattern, scope):
            first, second = match.groups()
            if index == 1:
                quarter, year = first, second
            else:
                year, quarter = first, second
            quarter = chinese_quarters.get(quarter, quarter)
            values.add(f"period:{year}-q{quarter}")
    years = {
        match.group(1)
        for match in re.finditer(r"(?<!\d)(20\d{2})(?!\d)", scope)
    }
    quarters = {
        chinese_quarters.get(
            match.group(1) or match.group(2),
            match.group(1) or match.group(2),
        )
        for match in re.finditer(r"\bq([1-4])\b|第?([一二三四1234])季度", scope)
        if (match.group(1) or match.group(2))
    }
    if len(years) == 1 and len(quarters) == 1:
        values.add(f"period:{next(iter(years))}-q{next(iter(quarters))}")
    for value in re.findall(
        r"(?<!\d)(\d{1,3})(?:st|nd|rd|th)?[\s-]+(?:year|anniversary)|"
        r"(?<!\d)(\d{1,3})\s*周年",
        scope,
    ):
        values.add(f"anniversary:{next(part for part in value if part)}")
    number_words = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }
    for match in re.finditer(
        r"(?<!\d)(\d{1,2})\s*(?:-?layer|层)|"
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten)(?:-layer|\s+layers?)\b|"
        r"([一二三四五六七八九十])\s*层",
        scope,
    ):
        chinese_numbers = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }
        raw = match.group(1) or number_words.get(match.group(2), "") or chinese_numbers[match.group(3)]
        values.add(f"layers:{raw}")
    currency_patterns = (
        ("usd", r"(?:us\s*)?\$\s*(\d[\d,]*(?:\.\d+)?)\s*(billion|million|bn|b|m)?\b"),
        ("usd", r"(\d+(?:\.\d+)?)\s*万\s*美元"),
        ("usd", r"(\d+(?:\.\d+)?)\s*亿\s*美元"),
        ("eur", r"€\s*(\d[\d,]*(?:\.\d+)?)"),
        ("gbp", r"£\s*(\d[\d,]*(?:\.\d+)?)"),
    )
    for currency, pattern in currency_patterns:
        for match in re.finditer(pattern, scope):
            raw = match.group(1).replace(",", "")
            amount = float(raw)
            if "万" in match.group(0):
                amount *= 10000
            elif "亿" in match.group(0):
                amount *= 100000000
            elif len(match.groups()) > 1 and match.group(2):
                scale = match.group(2)
                amount *= 1000000000 if scale in {"billion", "bn", "b"} else 1000000
            normalized = str(int(amount)) if amount.is_integer() else str(amount)
            values.add(f"money:{currency}:{normalized}")
    if "十亿美元" in scope:
        values.add("money:usd:1000000000")
    return values


def _claim_components(identity: EventIdentity) -> set[str]:
    """Return typed predicates while excluding product/version metadata."""
    return {
        component
        for component in identity.components
        if ":" not in component
        and component
        not in {
            "hardware-product-roadmap",
            "roadmap-projection",
        }
    }


def _document_subject_token(value: str) -> str:
    """Return a stable integration target from a first-party document title."""
    value = _normalized(value).strip(" .,:;!?()[]{}\"'“”‘’《》")
    value = re.sub(r"(?:大模型|模型|扩展|服务)$", "", value).strip()
    # Chinese reports may write a partner plus its model as one token while
    # the first-party page itself names only the model. Normalize common
    # organization prefixes, but keep the model name data-driven.
    for prefix in (
        "阿里巴巴",
        "字节跳动",
        "openai",
        "google",
        "microsoft",
        "阿里",
        "百度",
        "腾讯",
        "字节",
        "谷歌",
        "微软",
    ):
        if value.startswith(prefix) and len(value.removeprefix(prefix)) >= 2:
            value = value.removeprefix(prefix).strip()
            break
    value = re.sub(r"^(?:旗下的?|的)", "", value).strip()
    value = re.sub(r"^(?:接入|使用|调用|集成|整合|配合|联动)", "", value).strip()
    if not value or value in {
        "apple",
        "apple intelligence",
        "apple 智能",
        "siri",
        "mac",
        "功能",
        "页面",
        "手册",
        "文档",
    }:
        return ""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff+.-]+", "-", value).strip("-")


def _document_integration_subject(text: str) -> str:
    candidates: list[str] = []
    for pattern in (
        r"(?:使用|接入|调用|集成|整合|配合|联动)\s*"
        r"(?P<name>[\u4e00-\u9fff]{2,14}?|[a-z][a-z0-9+.-]{1,30})"
        r"(?=\s*(?:大模型|模型|扩展|服务|使用手册|手册|页面|工作|[\"'“”‘’《》]|$))",
        r"(?:删除|移除|撤下|下线|恢复|替换|更正)\s*"
        r"(?P<name>[\u4e00-\u9fff]{2,14}?|[a-z][a-z0-9+.-]{1,30})"
        r"(?=\s*(?:使用手册|用户手册|操作手册|支持文档|支持页面|文档|手册|页面))",
        r"\b(?:use|using|integrates? with|works? with|powered by)\s+"
        r"(?P<name>[a-z][a-z0-9+.-]{1,30})(?=\s|[\"'.,:;!?)]|$)",
    ):
        candidates.extend(match.group("name") for match in re.finditer(pattern, text, re.I))
    for candidate in reversed(candidates):
        token = _document_subject_token(candidate)
        if token:
            return token
    return ""


def first_party_document_lifecycle_key(
    title: str,
    text: str,
    identity: EventIdentity,
) -> str:
    """Identify reports about one first-party page appearing and later changing."""
    title = _normalized(title)
    text = _normalized(text)
    if not _contains(
        text,
        "support document",
        "support page",
        "user guide",
        "user manual",
        "documentation",
        "apple support",
        "apple website",
        "apple's website",
        "apple.com",
        "支持文档",
        "使用手册",
        "用户手册",
        "操作手册",
        "苹果官网",
        "苹果中国官网",
    ):
        return ""
    if not _contains(
        text,
        "appears",
        "appeared",
        "surfaced",
        "published",
        "added",
        "updated",
        "documented",
        "removed",
        "deleted",
        "withdrawn",
        "pulled",
        "restored to",
        "replaced",
        "corrected",
        "现身",
        "出现",
        "上线",
        "新增",
        "更新",
        "删除",
        "删了",
        "撤下",
        "下线",
        "恢复为",
        "替换",
        "更正",
    ):
        return ""
    if not _contains(title, "apple", "苹果") and identity.scope != "apple-direct":
        return ""
    subject = _document_integration_subject(text)
    if not subject:
        return ""
    preferred_products = (
        "apple-intelligence",
        "icloud-private-relay",
        "icloud",
        "siri",
        "app-store",
        "apple-wallet",
        "apple-music",
        "apple-tv",
        "macos",
        "ios",
        "ipados",
        "watchos",
        "visionos",
    )
    product = next((value for value in preferred_products if value in identity.products), "")
    if not product:
        return ""
    return f"apple-document-lifecycle:{product}:{subject}"


def _title_fact_signatures(title: str, lead: str) -> set[str]:
    """Return exact, title-led subject/action signatures for reconciliation.

    These signatures are deliberately narrower than topic facets.  A product
    name alone is never a signature: the title or short lead must also expose
    the concrete changed object, material, finish set, generation, or program
    operation.  This lets exact cross-source matches override seed boundaries
    without reopening fuzzy all-pairs clustering.
    """
    title = _normalized(title)
    lead = _normalized(lead)[:900]
    text = f"{title}. {lead}"
    signatures: set[str] = set()

    foldable_iphone = bool(
        re.search(
            r"\b(?:foldable|folding)\s+(?:apple\s+)?iphone\b|"
            r"\biphone\s+(?:fold|ultra)\b|(?:折叠屏?|折叠式)\s*(?:iphone|苹果手机)|"
            r"(?:iphone|苹果首款手机).{0,12}(?:折叠屏?|折叠式)",
            text,
        )
        or (
            re.search(r"折叠屏?|折叠式", text)
            and re.search(r"\biphone\s+(?:fold|ultra)\b|iphone", text)
        )
    )
    if foldable_iphone:
        finish_aliases = {
            "black": (r"\bblack\b", "黑色"),
            "dark-blue": (r"\bdark[ -]blue\b", "深蓝色", "深蓝"),
            "gold": (r"\bgold(?:en)?\b", "金色"),
            "silver": (r"\bsilver\b", "银色"),
            "white": (r"\bwhite\b", "白色"),
        }
        clauses = [part.strip() for part in re.split(r"(?<=[.!?。！？;；])\s*", text) if part.strip()]
        for clause in clauses:
            finishes = {
                finish
                for finish, aliases in finish_aliases.items()
                if any(
                    re.search(alias, clause) if alias.startswith(r"\b") else alias in clause
                    for alias in aliases
                )
            }
            finish_context = bool(
                re.search(r"\b(?:colors?|colou?rs?|finishes?|choice of)\b|配色|颜色|色款", clause)
            )
            if finish_context and len(finishes) >= 2:
                signatures.add(f"finish-set:foldable-iphone:{','.join(sorted(finishes))}")
                break

        generation_match = re.search(
            r"\b(?:third|3rd)[ -]generation\b|\bthird[ -]gen\b|"
            r"\b(?:iphone\s+(?:fold|ultra)\s*3)\b|(?:第三代|第\s*3\s*代)",
            text,
        )
        roadmap_context = bool(
            re.search(
                r"\b(?:roadmap|planning|plans?|planned|generation|2028)\b|"
                r"路线图|规划|计划|第三代|第\s*3\s*代",
                text,
            )
        )
        if generation_match and roadmap_context:
            signatures.add("future-generation-roadmap:foldable-iphone:g3")

    apple_watch = bool(re.search(r"(?<![a-z0-9])apple\s*watch\b|苹果\s*watch", text))
    if apple_watch and re.search(r"\bceramic\b|陶瓷", text):
        signatures.add("case-material:apple-watch:ceramic")
    if apple_watch:
        redesign = bool(re.search(r"\b(?:redesign|rethink|form[ -]factor|revamp)\b|重新设计|重新思考|产品形态|形态重构|大改版", text))
        form_factor = bool(re.search(r"\bround(?:ed)?\s+(?:screen|display|model)\b|\bscreenless\b|圆(?:形|屏)|无屏", text))
        if redesign:
            signatures.add("form-factor-redesign:apple-watch")
        if redesign and form_factor:
            signatures.add("form-factor-redesign:apple-watch:round-or-screenless")

    apple_upgrade = bool(re.search(r"\bapple\s+upgrade\b|苹果\s*upgrade", text))
    device_data_preload = bool(
        re.search(
            r"\b(?:preload|pre-load|preloaded|pre-loaded)\b.{0,80}\b(?:icloud|backup|data)\b|"
            r"\b(?:icloud|backup|data)\b.{0,80}\b(?:preload|pre-load|preloaded|pre-loaded)\b|"
            r"(?:预载|预装|装好).{0,40}(?:icloud|备份|用户数据|数据)|"
            r"(?:icloud|备份|用户数据).{0,40}(?:预载|预装|装好)",
            text,
        )
    )
    if apple_upgrade and device_data_preload:
        signatures.add("program-operation:apple-upgrade:device-data-preload")

    return signatures


def _quoted_subjects(value: str) -> list[str]:
    """Read paired quotation marks, never possessive apostrophes."""
    matches = re.finditer(
        r'《([^》\n]{1,90})》|“([^”\n]{1,90})”|'
        r'‘((?:[^’\n]|(?<=\w)’(?=\w)){1,90})’(?!\w)|'
        r'"([^"\n]{1,90})"|(?<!\w)\'((?:[^\'\n]|(?<=\w)\'(?=\w)){1,90})\'(?!\w)',
        value,
    )
    return [next(part for part in match.groups() if part).strip() for match in matches]


def _headline_content_claim(title: str, lead: str) -> tuple[str, str] | None:
    """Bind a trailer/review headline to its work, not a background release."""
    title_text = _canonical_title(title)
    action = (
        "trailer" if re.search(r"\b(?:trailer|teaser)\b|预告片", title_text)
        else "reviews" if re.search(r"\breviews?\b|影评|口碑", title_text)
        else ""
    )
    if not action:
        return None
    # Preserve case for unquoted titles, and do not cross sentence boundaries.
    primary_lead = re.split(r"[。！？]|(?<=[.!?])\s+", lead, maxsplit=2)
    scopes = [title, *primary_lead[:2]]
    name = r"[A-Z][A-Za-z0-9'’&-]*(?:[ \t]+[A-Za-z0-9'’&-]+){0,7}?"
    patterns = (
        rf"(?i:\b(?:contender|winner|title)\s*:\s*)(?P<name>{name})(?=[.,;!?]|$)",
        rf"(?i:\bapple\s+tv\s+premieres?\s+)(?P<name>{name})"
        r"(?i:(?=\s+(?:this|next|on|in)\b|[,.;!?]|$))",
        rf"(?i:\b(?:film|movie|documentary|series)\s+(?:called\s+|titled\s+)?)"
        rf"(?P<name>{name})(?=[,.;!?]|$)",
    )
    for scope in scopes:
        # Work quotes must be attached to a content noun/action. Award names
        # and review pull-quotes are not film identifiers.
        for quoted in _quoted_subjects(scope):
            prefix = scope[:scope.find(quoted)]
            if re.search(
                r"\b(?:film|movie|documentary|series|trailer\s+for|reviews?\s+(?:for|of))\s*[\"'“‘]$",
                prefix, re.I,
            ):
                return re.sub(r"[^a-z0-9]+", "-", _normalized(quoted)).strip("-"), action
        for pattern in patterns:
            match = re.search(pattern, scope)
            if match:
                subject = re.sub(r"[^a-z0-9]+", "-", _normalized(match.group("name"))).strip("-")
                if subject not in _GENERIC_SUBJECT_WORDS | {"apple-tv"}:
                    return subject, action
    return None


def _content_work_assertion(title: str, lead: str) -> tuple[str, str] | None:
    """Return a title-led Apple TV work and action without using publisher data."""
    # Key-fact evidence follows the lead in callers. Keep enough bounded text
    # to reach a source-attributed production fact without scanning page chrome.
    headline_claim = _headline_content_claim(title, lead)
    if headline_claim:
        return headline_claim
    raw = f"{title}. {lead[:2200]}"
    titled_schedule = re.search(
        r"《(?P<local>[^》]{1,80})》.{0,36}(?:定档|首播|上线|开播)",
        title,
    )
    if titled_schedule:
        localized_alias = re.search(
            rf"《{re.escape(titled_schedule.group('local'))}》\s*[（(]"
            r"(?P<subject>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,7})[)）]",
            lead,
            re.I,
        )
        if localized_alias:
            subject = re.sub(
                r"[^a-z0-9]+",
                "-",
                _normalized(localized_alias.group("subject")),
            ).strip("-")
            if subject and subject not in _GENERIC_SUBJECT_WORDS:
                return subject, "premiere-schedule"
    scheduled_work_patterns = (
        r"\b(?:series|film|movie|drama|comedy)\s*[-—:]\s*"
        r"(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s*"
        r"[-—,]\s*(?:coming|premier(?:e|es|ing)|debut(?:s|ing)?)\b",
        r"《[^》]{1,80}》\s*[（(](?P<subject>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,7})[)）]"
        r".{0,50}(?:定档|首播|上线)",
        r"\b(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"premieres?\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"january|february|march|april|may|june|july|august|september|october|november|december)",
    )
    for pattern in scheduled_work_patterns:
        scheduled_work = re.search(pattern, raw, re.I)
        if not scheduled_work:
            continue
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(scheduled_work.group("subject")),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "premiere-schedule"
    casting_match = re.search(
        r"\b(?P<subject>[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){1,4})\s+"
        r"(?:is\s+)?(?:confirmed|cast|joins?)\s+as\s+(?:a\s+)?(?:guest\s+)?star\b|"
        r"(?P<subject_cn>[A-Za-z][A-Za-z'’.-]+(?:\s+[A-Za-z][A-Za-z'’.-]+){1,4})"
        r".{0,35}(?:确认|确定).{0,18}(?:客串|加盟|出演)",
        title,
        re.I,
    )
    if casting_match:
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(casting_match.group("subject") or casting_match.group("subject_cn")),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "casting"
    season_subject_match = re.search(
        r"^['\"“‘]?(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)"
        r"['\"”’]?\s+season\s+\d+\b",
        title,
        re.I,
    )
    if (
        season_subject_match
        and re.search(
            r"\b(?:filming|production|shooting)\b.{0,90}"
            r"\b(?:begin|begins|start|starts|kick[ -]?off|set|scheduled|date)\b|"
            r"\b(?:begin|begins|start|starts|kick[ -]?off|set|scheduled)\b.{0,90}"
            r"\b(?:filming|production|shooting)\b",
            raw,
            re.I,
        )
    ):
        season_subject_text = re.sub(
            r"^.*?\b(?:reveals?|confirms?|shares?|says?)\s+",
            "",
            season_subject_match.group("subject"),
            flags=re.I,
        )
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(season_subject_text),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "production-update"
    season_production_match = re.search(
        r"\b(?P<subject>[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"season\s+\d+\b.{0,65}\b(?:begins?\s+filming|starts?\s+filming|"
        r"filming\s+(?:begins?|starts?)|enters?\s+production|production\s+(?:begins?|starts?))\b",
        raw,
        re.I,
    )
    if not season_production_match:
        season_production_match = re.search(
            r"《[^》]{1,60}》\s*[（(](?P<subject>[A-Za-z0-9'’.-]+(?:\s+[A-Za-z0-9'’.-]+){0,7})[)）]"
            r".{0,55}第\s*(?:\d+|[一二三四五六七八九十]+)\s*季.{0,45}"
            r"(?:开拍|启动拍摄|启动制作|开始制作|进入制作|拍摄.{0,30}启动)",
            raw,
            re.I,
        )
    if season_production_match:
        subject_text = re.sub(
            r"^.*?\b(?:reveals?|confirms?|shares?|says?)\s+",
            "",
            season_production_match.group("subject"),
            flags=re.I,
        )
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(subject_text),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "production-update"
    if (
        re.search(r"(?<![a-z0-9])f1(?![a-z0-9])|formula\s+1|一级方程式", raw, re.I)
        and re.search(
            r"\b(?:viewership|audience|ratings?|analytics|viewing\s+(?:minutes?|data))\b|"
            r"(?:收视|观众|观看量|观看时长|收视数据|观众数据)",
            raw,
            re.I,
        )
    ):
        return "f1", "viewership-analysis"
    season_trailer_match = re.search(
        r"\b(?:apple(?:\s+tv)?\s+)?(?:releases?|released|shares?|shared|unveils?|unveiled)\s+"
        r"(?:a\s+|the\s+|new\s+|first\s+)*"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"season\s+\d+\s+(?:trailer|teaser)\b",
        raw,
        re.I,
    )
    if season_trailer_match:
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(season_trailer_match.group(1)),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "trailer"
    viewing_record_match = re.search(
        r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)\s+"
        r"season\s+\d+\b.{0,90}\b(?:biggest\s+(?:launch|premiere)|"
        r"viewing\s+record|premiere\s+record|most[- ]watched)\b",
        title,
        re.I,
    )
    if viewing_record_match:
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(viewing_record_match.group(1)),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "viewing-record"
    trailer_for_match = re.search(
        r"\bApple(?:\s+TV)?\s+(?:releases?|released|shares?|shared|publishes?|unveils?)\s+"
        r"(?:a\s+|the\s+|new\s+|first\s+)*"
        r"(?:trailer|teaser)\s+for\s+"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)"
        r"(?=(?:['’]s)?\s+(?:second|third|fourth|fifth|final|\d+(?:st|nd|rd|th)?)\s+season\b|\s*[-:,.]|$)",
        title,
        re.I,
    )
    if trailer_for_match:
        subject_name = re.sub(r"['’]s$", "", trailer_for_match.group(1), flags=re.I)
        subject = re.sub(r"[^a-z0-9]+", "-", _normalized(subject_name)).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "trailer"
    season_progress_match = re.search(
        r"\b(?:reveals?|confirms?|shares?|says?)\s+"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,5}?)\s+"
        r"season\s+\d+\b.{0,70}\b(?:milestone|filming|production|shooting|progress)\b",
        title,
        re.I,
    )
    if season_progress_match:
        subject = re.sub(r"[^a-z0-9]+", "-", _normalized(season_progress_match.group(1))).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "production-update"
    continuation_hint = re.search(
        r"\b(?:hints?|suggests?|signals?)\s+(?:at\s+)?(?:more|future)\s+"
        r"[\"'“‘]?([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)[\"'”’]?\s+seasons?\b",
        title,
        re.I,
    )
    if continuation_hint:
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(continuation_hint.group(1)),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "continuation"
    title_match = re.search(
        r"\bApple\s+TV\s+(?:releases?|shares?|unveils?)\s+(?:a\s+|new\s+)*"
        r"([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7})\s+"
        r"(trailer|teaser)\b",
        title,
        re.I,
    )
    if title_match:
        subject = re.sub(r"[^a-z0-9]+", "-", _normalized(title_match.group(1))).strip("-")
        if subject:
            return subject, title_match.group(2).lower()
    for quoted_trailer_pattern in (
        r'\btrailer\s+for\s+["“]([^"”]{1,80}?)[,]?["”]',
        r"\btrailer\s+for\s+['‘]([^'’]{1,80}?)[,]?['’]",
    ):
        quoted_trailer = re.search(quoted_trailer_pattern, raw, re.I)
        if not quoted_trailer:
            continue
        subject = re.sub(r"[^a-z0-9]+", "-", _normalized(quoted_trailer.group(1))).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "trailer"
    release_work_match = re.search(
        r"\b([A-Z][A-Za-z0-9'’.-]+(?:\s+[A-Z][A-Za-z0-9'’.-]+){1,7})"
        r"(?=\s+(?:will\s+stream\s+on|for|on)\s+Apple\s+TV\b|[,，]\s*(?:by|由)\b)",
        raw,
    )
    if release_work_match:
        subject = re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(release_work_match.group(1)),
        ).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, "new-project"
    patterns = (
        (
            r"\bfuture\s+([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,7})\s+seasons?\b",
            "continuation",
        ),
        (
            r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,7})\s+could\s+continue\b",
            "continuation",
        ),
        (
            r"\btrailer\s+for\s+([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7}?)(?=\s*[,.:;!?]|\s+(?:which|that)\b|$)",
            "trailer",
        ),
        (
            r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7})['’]s\s+"
            r"(?:second|third|fourth|final|\d+(?:st|nd|rd|th)?)\s+season\s+premieres?\b",
            "season-premiere",
        ),
        (
            r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z0-9'’.-]+){0,7})\s+"
            r"(?:premieres?|debuts?)\s+(?:on|at)\s+Apple\s+TV\b",
            "premiere",
        ),
    )
    for pattern, action in patterns:
        match = re.search(pattern, raw, re.I)
        if not match:
            continue
        subject = re.sub(r"[^a-z0-9]+", "-", _normalized(match.group(1))).strip("-")
        if subject and subject not in _GENERIC_SUBJECT_WORDS:
            return subject, action
    return None


def _product_lifecycle_subjects(text: str, identity: EventIdentity) -> set[str]:
    """Return concrete products affected by an official lifecycle-list action."""
    subjects: set[str] = set()
    if re.search(r"(?<![a-z0-9])iphone\s*x(?![a-z0-9])", text):
        subjects.add("iphone-x")
    for generation in re.findall(r"(?<![a-z0-9])iphone\s*(\d{1,2})(?!\d)", text):
        subjects.add(f"iphone-{generation}")
    if re.search(r"\bmacbook\s+pro\b|macbook\s*pro|苹果笔记本", text):
        subjects.add("macbook-pro")
    if re.search(r"\bmacbook\s+air\b|macbook\s*air", text):
        subjects.add("macbook-air")
    if re.search(r"\bipad\s+mini\b|ipad\s*mini", text):
        subjects.add("ipad-mini")
    if re.search(r"\bipad\s+pro\b|ipad\s*pro", text):
        subjects.add("ipad-pro")
    if not subjects and re.search(r"\bmacs?\b|(?:三|3)\s*款\s*mac", text):
        subjects.add("mac")
    if not subjects:
        subjects |= {
            product
            for product in identity.title_products
            if product in {
                "airpods",
                "apple-watch",
                "homepod",
                "imac",
                "ipad",
                "iphone",
                "mac-mini",
                "mac-pro",
                "mac-studio",
                "macbook",
                "vision-pro",
            }
        }
    return subjects


def _first_party_facility_subject(text: str) -> str:
    if _contains(
        text,
        "apple education center",
        "apple educational center",
        "苹果教育中心",
    ):
        return "education-center"
    if _contains(text, "apple developer center", "苹果开发者中心"):
        return "developer-center"
    if _contains(
        text,
        "innovation center",
        "innovation centre",
        "research center",
        "research centre",
        "engineering center",
        "engineering centre",
        "创新中心",
        "研发中心",
        "工程中心",
    ):
        return "innovation-center"
    if _contains(
        text,
        "apple advanced manufacturing center",
        "苹果先进制造中心",
    ):
        return "manufacturing-center"
    manufacturing = _contains(
        text,
        "manufacturing",
        "factory",
        "production line",
        "制造",
        "工厂",
        "生产线",
    )
    training = _contains(
        text,
        "training",
        "education courses",
        "training school",
        "培训",
        "教育课程",
        "培训学校",
    )
    if _contains(text, "advanced manufacturing center", "先进制造中心"):
        return "manufacturing-center"
    if _contains(text, "manufacturing center", "制造中心"):
        return "manufacturing-center"
    if _contains(text, "developer center", "开发者中心"):
        return "developer-center"
    if _contains(
        text,
        "education center",
        "educational center",
        "training center",
        "learning center",
        "education programme center",
        "education program center",
        "教育中心",
        "培训中心",
        "学习中心",
    ):
        return "education-center"
    if manufacturing and training:
        return "manufacturing-center"
    return ""


def _first_party_facility_location(title: str) -> str:
    """Return a title-owned facility location without relying on a region table."""
    title_text = _normalized(title)
    patterns = (
        r"\b(?:center|centre|facility|school|campus)\s+in\s+([a-z][a-z .'-]{2,30})$",
        r"\bin\s+([a-z][a-z .'-]{2,30})\s+(?:gets?|opens?|welcomes?|with)\b",
        r"\bin\s+([a-z][a-z .'-]{2,30})$",
        r"在([^，。,:：]{2,18}?)(?:设立|建立|落地|开设|启用).{0,16}(?:中心|学校|园区)",
    )
    for pattern in patterns:
        match = re.search(pattern, title_text, re.I)
        if not match:
            continue
        location = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "-", match.group(1)).strip("-")
        if location:
            return location
    return ""


def _hardware_accessory_evaluation_claim(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> tuple[str, str] | None:
    """Return a product/accessory pair for one compatibility evaluation.

    Testing, considering, and deciding not to ship an accessory are successive
    descriptions of the same prototype decision, not separate product events.
    The relation is derived from the title and short lead so unrelated product
    background cannot create the claim.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return None
    if re.search(
        r"\b(?:obsolete|vintage)\b.{0,36}\b(?:products?\s+)?list\b|"
        r"(?:过时|复古|停产).{0,18}(?:产品)?(?:名单|列表)|"
        r"(?:列入|进入).{0,20}(?:过时|复古|停产)(?:产品)?(?:名单|列表)",
        _normalized(title),
        re.I,
    ):
        return None
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    if len(products) != 1:
        return None
    text = f"{_normalized(title)}. {_normalized(lead)[:700]}"
    accessory = ""
    for name, pattern in (
        ("stylus", r"\b(?:apple\s+pencil|stylus|digital\s+pen)\b|(?:触控笔|手写笔)"),
        ("keyboard", r"\b(?:magic\s+keyboard|keyboard)\b|(?:妙控键盘|键盘)"),
        ("controller", r"\b(?:game\s+controller|controller)\b|(?:游戏手柄|控制器)"),
    ):
        if re.search(pattern, text, re.I):
            accessory = name
            break
    if not accessory:
        return None
    evaluation = bool(
        re.search(
            r"\b(?:test(?:ed|ing)?|prototype|consider(?:ed|ing)?|evaluate(?:d|s|ing)?|"
            r"support(?:ed|s|ing)?|compatib(?:le|ility)|not\s+expected\s+to\s+(?:ship|launch)|"
            r"won['’]t\s+(?:ship|launch|support)|will\s+not\s+(?:ship|launch|support))\b|"
            r"(?:测试|原型|考虑|评估|支持|兼容|不会|不太可能|无缘).{0,24}"
            r"(?:量产|推出|发布|上市|支持|兼容)?",
            text,
            re.I,
        )
    )
    if not evaluation:
        return None
    return next(iter(products)), accessory


def _hardware_component_adoption_claims(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> set[tuple[str, str]]:
    """Return title-owned product/component adoption relations.

    This normalizes wording such as "first with", "will use", and "expected
    with" while keeping supplier orders, cost analyses, and generic component
    background outside the relation.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return set()
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    if len(products) != 1:
        return set()
    if identity.title_actions & {"supply-production", "price-change", "legal"}:
        return set()
    text = f"{_normalized(title)}. {_normalized(lead)[:700]}"
    title_components = {
        component
        for component in identity.title_components
        if ":" not in component
    }
    adoption = bool(
        re.search(
            r"\b(?:first|debut|adopt(?:s|ed|ing)?|use(?:s|d|ing)?|feature(?:s|d|ing)?|"
            r"equip(?:ped|s)?|come(?:s)?\s+with|launch(?:es|ed|ing)?\s+with|"
            r"expected\b.{0,45}\b(?:with|to\s+use|to\s+feature))\b|"
            r"(?:首次|首度|改用|采用|搭载|配备|换用|将用|预计).{0,36}"
            r"(?:推出|发布|搭载|采用|配备|屏幕|面板|芯片|传感器|摄像头|电池|调制解调器)?",
            text,
            re.I,
        )
        or (
            title_components
            and identity.title_actions
            & {
                "delay-roadmap",
                "product-launch",
                "product-refresh",
                "retail-availability",
            }
        )
    )
    if not adoption:
        return set()
    physical_markers = (
        "display",
        "panel",
        "camera",
        "sensor",
        "battery",
        "modem",
        "processor",
        "chip",
        "memory",
        "case-material",
        "glass",
        "thermal",
        "speaker",
        "keyboard",
    )
    components = {
        component
        for component in title_components
        if any(marker in component for marker in physical_markers)
    }
    if re.fullmatch(r"apple\s+.+\s+roadmap\s+update", _normalized(title)):
        components |= {
            component
            for component, terms in COMPONENT_PATTERNS
            if ":" not in component
            and any(marker in component for marker in physical_markers)
            and _contains(text, *terms)
        }
    product = next(iter(products))
    return {(product, component) for component in components}


def _app_store_impersonation_subject(title: str, lead: str) -> str:
    """Return the legitimate app named by an App Store impersonation incident."""
    text = f"{_normalized(title)}. {_normalized(lead)[:500]}"
    if not (
        _contains(text, "app store", "应用商店", "苹果商店")
        and _contains(text, "counterfeit", "impersonat", "fake", "copycat", "山寨", "仿冒", "假冒", "盗版")
    ):
        return ""
    patterns = (
        r"(?:统一平台|official\s+platform)\s*[(（]\s*(?:简称)?\s*[“\"‘']?"
        r"([a-z0-9\u4e00-\u9fff.+-]{2,30}(?:\s*app)?)\s*[”\"’']?\s*[)）]",
        r"(?:简称|abbreviated\s+as)\s*[“\"‘']?"
        r"([a-z0-9\u4e00-\u9fff.+-]{2,30})(?:\s*app)?[”\"’']?",
        r"(?:^|[，,:：。])\s*([a-z0-9\u4e00-\u9fff.+-]{2,30})(?:\s*app)?\s*官方(?:回应|表示|称)",
        r"(?:盗版|山寨版?|仿冒|假冒)[“\"‘']([^”\"’']{2,40})[”\"’']",
        r"(?:正版|官方)(?:\s*app)?[“\"‘']([^”\"’']{2,40})[”\"’']",
        r"(?:名为)\s*[“\"‘']?([a-z0-9\u4e00-\u9fff.+-]{2,30})(?:\s*app)?[”\"’']?",
    )
    ignored = {"app", "政务", "应用", "软件", "相关部门", "苹果应用商店"}
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        subject = re.sub(r"[^a-z0-9\u4e00-\u9fff.+-]+", "-", _normalized(match.group(1))).strip("-")
        subject = re.sub(r"(?:-?app)$", "", subject).strip("-")
        if subject and subject not in ignored:
            return subject
    return ""


def _canonical_supplier_entities(text: str) -> set[str]:
    aliases = {
        "boe": ("boe", "京东方"),
        "foxconn": ("foxconn", "鸿海", "富士康"),
        "lg-display": ("lg display", "lg 显示", "乐金显示"),
        "samsung-display": ("samsung display", "三星显示"),
        "tsmc": ("tsmc", "台积电"),
    }
    return {
        canonical
        for canonical, values in aliases.items()
        if _contains(text, *values)
    }


def _structured_assertion_keys(
    title: str,
    lead: str,
    identity: EventIdentity,
    evidence: str = "",
    regions: Iterable[str] = (),
) -> tuple[set[str], set[str], set[str]]:
    """Build subject/predicate assertions used before broad topic similarity."""
    title_scope, primary_scope = _primary_assertion_scope(title, lead)
    text = primary_scope
    short_lead = _short_lead_scope(lead)
    evidence_scope = f"{title_scope}. {short_lead} {_normalized(evidence)[:1600]}".strip()
    event_keys: set[str] = set()
    boundaries: set[str] = set()
    separation: set[str] = set()

    first_party_services = set(identity.products) & _SOFTWARE_FIRST_PARTY_PRODUCTS
    access_queue = bool(
        re.search(
            r"\b(?:waitlist|waiting\s+list|access\s+queue|wait\s+in\s+line|"
            r"wait\s+for\s+access)\b|(?:候补名单|访问队列|排队机制|排队访问)",
            evidence_scope,
            re.I,
        )
    )
    if first_party_services and access_queue:
        service_subject = "siri-ai" if "siri" in first_party_services else sorted(first_party_services)[0]
        event_keys.add(f"structured-assertion:{service_subject}:access-waitlist")
        boundaries.add(f"structured-subject:{service_subject}")
        separation |= {
            f"assertion-subject:{service_subject}",
            "assertion-action:access-waitlist",
        }

    advertising_rollout = bool(
        re.search(r"\b(?:ad|ads|advertising|sponsored listings?)\b|(?:广告|推广内容)", evidence_scope, re.I)
        and re.search(
            r"\b(?:live|launch(?:es|ed)?|roll(?:s|ed|ing)?\s+out|begin(?:s|ning)?|"
            r"start(?:s|ed|ing)?|available)\b|(?:上线|推出|开始投放|正式投放)",
            evidence_scope,
            re.I,
        )
    )
    if len(first_party_services) == 1 and advertising_rollout:
        service_subject = next(iter(first_party_services))
        event_keys.add(f"structured-assertion:{service_subject}:advertising-rollout")
        boundaries.add(f"structured-subject:{service_subject}")
        separation |= {
            f"assertion-subject:{service_subject}",
            "assertion-action:advertising-rollout",
        }

    os_platforms = set(identity.title_products) & {
        "ios",
        "ipados",
        "macos",
        "watchos",
        "tvos",
        "visionos",
    }
    if not os_platforms and "apple-watch" in identity.title_products:
        os_platforms.add("watchos")
    os_components = {
        component
        for component in identity.components
        if component.startswith("os-component:")
    }
    if os_platforms and os_components and "feature-change" in identity.actions:
        for platform in os_platforms:
            for component in os_components:
                subject = component.removeprefix("os-component:")
                event_keys.add(
                    f"structured-assertion:os-feature:{platform}:{subject}:feature-change"
                )
                separation.add(f"os-feature-subject:{platform}:{subject}")

    iphone_generation = next(
        (
            component.removeprefix("product-generation:iphone-")
            for component in identity.components
            if component.startswith("product-generation:iphone-")
        ),
        "",
    )
    base_iphone = any(
        component.startswith("iphone-model:") and component.endswith("-base")
        for component in identity.components
    ) or bool(
        re.search(
            r"\b(?:base|standard)(?:\s+model)?\s+iphone\s*\d{1,2}\b|"
            r"\biphone\s*\d{1,2}\s+(?:base|standard)(?:\s+model)?\b|"
            r"(?:标准版|基础款).{0,18}iphone\s*\d{1,2}|"
            r"iphone\s*\d{1,2}.{0,18}(?:标准版|基础款)",
            text,
        )
    )
    title_has_release_schedule_action = bool(
        re.search(
            r"\b(?:skip(?:s|ping|ped)?.{0,36}\blaunch|"
            r"not\s+(?:be\s+)?released\s+until|won't\s+launch\s+alongside|"
            r"will\s+not\s+launch\s+alongside|release\w*\s+separately|"
            r"split\s+(?:the\s+)?launch|delay(?:ed|s|ing)?|postpone(?:d|s)?|push(?:ed|es)?)\b|"
            r"(?:拆分|分批|推迟|延期|延后).{0,28}(?:发布|登场|推出)|"
            r"(?:发布|登场|推出).{0,28}(?:拆分|分批|推迟|延期|延后)",
            title_scope,
        )
    )
    sparse_supplier_confirmation = bool(
        re.search(r"\b20\d{2}\b", title_scope)
        and _contains(title_scope, "launch", "release", "发布", "登场", "推出")
        and _contains(evidence_scope, "apple supplier", "pegatron", "和硕", "供应商")
        and _contains(evidence_scope, "separately", "early 20", "until next year", "分批", "明年", "推迟", "延期")
    )
    split_release_schedule = bool(
        iphone_generation
        and base_iphone
        and (title_has_release_schedule_action or sparse_supplier_confirmation)
    )
    if split_release_schedule:
        subject = f"iphone-{iphone_generation}-base"
        event_keys.add(f"structured-assertion:{subject}:split-release-schedule")
        boundaries.add(f"structured-subject:{subject}")
        separation |= {
            f"assertion-subject:{subject}",
            "assertion-action:product-release-delay",
        }

    if "product-release-delay" in identity.components and "iphone" in identity.products:
        generation_match = re.search(r"(?<![a-z0-9])iphone\s*(\d{1,2})(?!\d)", text)
        base_model = bool(
            re.search(
                r"\b(?:base|standard)(?:\s+model)?\s+iphone\s*\d{1,2}\b|"
                r"\biphone\s*\d{1,2}\s+(?:base|standard)(?:\s+model)?\b|"
                r"(?:标准版|基础款).{0,18}iphone\s*\d{1,2}|"
                r"iphone\s*\d{1,2}.{0,18}(?:标准版|基础款)",
                text,
            )
        )
        period_pattern = (
            r"\b(spring|fall|autumn)\s+(20\d{2})\b|"
            r"(20\d{2})\s*年\s*(春季|秋季)|"
            r"\b(next\s+spring|next\s+fall|next\s+autumn)\b|"
            r"(明年春季|明年秋季)"
        )
        delay_period_pattern = (
            r"(?:delay(?:ed|s|ing)?|postpone(?:d|s)?|push(?:ed|es)?|"
            r"move(?:d|s)?\s+to|推迟|延期|延后).{0,80}?(?:" + period_pattern + r")"
        )
        period_match = None
        for clause in re.split(r"[，,。.!?！？;；]", text):
            if not re.search(r"\b(?:base|standard)\b|标准版|基础款", clause):
                continue
            period_match = re.search(delay_period_pattern, clause)
            if period_match is not None:
                break
        if period_match is None:
            period_match = re.search(delay_period_pattern, text)
        period_group_offset = 0
        if period_match is None:
            period_match = re.search(period_pattern, text)
        if generation_match and period_match:
            season_aliases = {"春季": "spring", "秋季": "fall", "明年春季": "next-spring", "明年秋季": "next-fall"}
            if period_match.group(1 + period_group_offset):
                period = f"{period_match.group(1 + period_group_offset).replace('autumn', 'fall')}-{period_match.group(2 + period_group_offset)}"
            elif period_match.group(3 + period_group_offset):
                period = f"{season_aliases[period_match.group(4 + period_group_offset)]}-{period_match.group(3 + period_group_offset)}"
            elif period_match.group(5 + period_group_offset):
                period = period_match.group(5 + period_group_offset).replace(" ", "-").replace("autumn", "fall")
            else:
                period = season_aliases[period_match.group(6 + period_group_offset)]
            model = "base" if base_model else "unspecified"
            generation = generation_match.group(1)
            key = f"structured-assertion:iphone-{generation}-{model}:release-delay:{period}"
            event_keys.add(key)
            boundaries.add(f"structured-subject:iphone-{generation}-{model}")
            separation |= {
                f"assertion-subject:iphone-{generation}-{model}",
                "assertion-action:product-release-delay",
            }

    if (_contains(text, "private relay", "icloud 专用代理") or re.search(r"icloud.{0,8}专用代理", text)) and _contains(
        text, "class action", "class-action", "集体诉讼"
    ):
        key = "structured-assertion:icloud-private-relay:class-action"
        event_keys.add(key)
        boundaries.add("structured-subject:icloud-private-relay")
        separation |= {"assertion-subject:icloud-private-relay", "assertion-action:class-action"}

    primary_lead = primary_scope.removeprefix(f"{title_scope}. ")
    content = _content_work_assertion(title, f"{lead}. {evidence[:1200]}")
    if content and (
        "apple-tv" in identity.products
        or _contains(evidence_scope, "apple tv", "apple tv+", "apple tv plus")
        or (
            identity.scope == "apple-direct"
            and re.match(r"^apple\b", title_scope)
        )
    ):
        subject, action = content
        event_keys.add(f"structured-assertion:apple-tv:{subject}:{action}")
        boundaries.add(f"structured-subject:apple-tv:{subject}")
        separation |= {f"content-title:{subject}", f"content-action:{action}"}

    apple_tv_viewing_record = bool(
        ("apple-tv" in identity.products or _contains(primary_scope, "apple tv", "apple tv+"))
        and _contains(
            primary_scope,
            "viewing record",
            "premiere record",
            "biggest launch",
            "biggest premiere",
            "highest viewing",
            "最高收视",
            "首播纪录",
            "观看纪录",
            "最大首播",
        )
    )
    season = re.search(
        r"\bseason\s*(\d+)\b|第\s*(\d+|[一二三四五六七八九十])\s*季",
        primary_scope,
    )
    if apple_tv_viewing_record and season and not (
        content and content[1] != "viewing-record"
    ):
        season_number = next(value for value in season.groups() if value)
        season_number = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }.get(season_number, season_number)
        event_keys.add(
            f"structured-assertion:apple-tv:season-{season_number}:viewing-record"
        )
        separation.add("content-action:viewing-record")

    # Normalize ordinal release wording from the title and first two lead
    # sentences. This covers sparse headlines such as "Seventh iOS ... Betas"
    # and "corresponding public betas" whose lead identifies the fifth wave.
    release_evidence = f"{title_scope}. {short_lead}"
    os_release_generation = re.search(
        r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
        r"(?:\s+[a-z][a-z-]+){0,2}\s+(\d{1,2})(?:\.\d+){0,2}\b",
        release_evidence,
    )
    ordinal_words = {
        "one": "1", "first": "1", "two": "2", "second": "2",
        "three": "3", "third": "3", "four": "4", "fourth": "4",
        "five": "5", "fifth": "5", "six": "6", "sixth": "6",
        "seven": "7", "seventh": "7", "eight": "8", "eighth": "8",
        "nine": "9", "ninth": "9", "ten": "10", "tenth": "10",
    }
    public_stage = re.search(
        r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|"
        r"seven|seventh|eight|eighth|nine|ninth|ten|tenth)\s+"
        r"public\s+betas?\b|"
        r"第\s*(\d+)\s*个?\s*公测版",
        release_evidence,
    )
    beta_stage = re.search(r"\bbeta\s*(\d+)\b", release_evidence)
    ordinal_stage = re.search(
        r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|"
        r"seven|seventh|eight|eighth|nine|ninth|ten|tenth)\b"
        r"(?!\s+(?:hours?|days?|weeks?|months?|years?)\b).{0,100}\bbetas?\b|"
        r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|"
        r"seven|seventh|eight|eighth|nine|ninth|ten|tenth)\s+public\s+beta\s+rollout\b",
        release_evidence,
    )
    stage_number = ""
    if public_stage:
        public_value = next(value for value in public_stage.groups() if value)
        stage_number = ordinal_words.get(public_value, public_value)
    elif beta_stage:
        stage_number = beta_stage.group(1)
    elif ordinal_stage:
        stage_number = ordinal_words.get(
            next(value for value in ordinal_stage.groups() if value),
            "",
        )
    release_announcement_title = bool(
        re.search(
            r"\b(?:apple\s+)?(?:releases?|seeds?|rolls?\s+out|ships?)\b"
            r".{0,100}\bbetas?\b|"
            r"\b(?:new\s+)?(?:public|developer)\s+betas?\b.{0,55}"
            r"\b(?:available|released|land|arrive)\b|"
            r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b"
            r".{0,100}\b(?:developer\s+)?betas?\b.{0,35}\b(?:land|released|arrive)\b|"
            r"(?:苹果)?.{0,35}(?:开发者预览版|公测版|测试版).{0,25}(?:发布|推送|上线)",
            title_scope,
        )
    )
    detail_declares_release_candidate = bool(
        re.search(r"\brelease candidates?\b|\brc\s*\d*\b|候选发布版|发布候选版", short_lead)
    )
    if (
        os_release_generation
        and stage_number
        and release_announcement_title
        and not detail_declares_release_candidate
        and re.search(
            r"\b(?:beta|betas|public beta|developer beta)\b",
            release_evidence,
        )
    ):
        generation = os_release_generation.group(1)
        stage = f"beta-{stage_number}"
        event_keys.add(f"apple-os-release-wave:{generation}:{stage}")
        boundaries.add(f"apple-os-release-wave:{generation}:{stage}")
        for platform in sorted(
            set(re.findall(r"\b(ios|ipados|macos|watchos|tvos|visionos)\b", release_evidence))
        ):
            event_keys.add(f"apple-os-platform-release-wave:{platform}:{stage}")
        separation.add("predicate:os-release-announcement")

    classic_catalog_addition = bool(
        not content
        and ("apple-tv" in identity.products or _contains(primary_scope, "apple tv", "apple tv+"))
        and _contains(
            primary_scope,
            "classic movies",
            "classic films",
            "经典影片",
            "经典电影",
            "经典片库",
        )
        and _contains(
            primary_scope,
            "adds",
            "added",
            "gains",
            "collection",
            "catalog",
            "stream for free",
            "no extra cost",
            "新增",
            "加入",
            "片库",
            "免费观看",
            "无需额外付费",
        )
    )
    if classic_catalog_addition:
        key = "structured-assertion:apple-tv:classic-movie-catalog:addition"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-tv:classic-movie-catalog")
        separation |= {
            "content-title:classic-movie-catalog",
            "content-action:catalog-addition",
        }

    lifecycle_action = bool(
        (
            _contains(
                title_scope,
                "obsolete",
                "vintage products list",
                "obsolete products list",
                "停产产品",
                "停产名单",
                "过时产品",
                "过时名单",
                "复古产品",
                "复古名单",
            )
            or re.search(r"停产[\"'”’]?[\s·]*产品", title_scope)
        )
        and _contains(
            evidence_scope,
            "apple",
            "苹果",
            "repairs",
            "parts",
            "service",
            "维修",
            "零件",
            "服务",
        )
    )
    if lifecycle_action:
        lifecycle_subjects = _product_lifecycle_subjects(evidence_scope, identity)
        for subject in lifecycle_subjects:
            event_keys.add(
                f"structured-assertion:product-lifecycle:{subject}:obsolete"
            )
            separation.add(f"assertion-subject:product-lifecycle:{subject}")
        boundaries.add("structured-action:product-lifecycle-obsolete")
        separation.add("assertion-action:product-lifecycle-obsolete")

    third_party_software_fix = bool(
        _contains(evidence_scope, "linux", "kernel", "内核")
        and _contains(title_scope, "fix", "patch", "power", "功耗", "修复", "根治")
        and identity.title_products
    )
    if third_party_software_fix:
        boundaries.add("structured-action:third-party-software-fix")
        separation.add("assertion-action:third-party-software-fix")

    facility_subject = _first_party_facility_subject(evidence_scope)
    facility_opening = bool(
        facility_subject
        and identity.scope == "apple-direct"
        and (
            _contains(
                title_scope,
                "announces",
                "announced",
                "establishes",
                "established",
                "sets up",
                "set up",
                "expands",
                "opens",
                "opened",
                "opening",
                "launches",
                "宣布",
                "设立",
                "建立",
                "落地",
                "扩展",
                "扩大",
                "开设",
                "启用",
                "揭幕",
                "落成",
            )
            or (
                re.search(
                    r"\bnew\s+(?:apple\s+)?(?:education|educational|training|learning)\s+center\b|"
                    r"(?:全新|首个|新建?)(?:苹果)?(?:教育|培训|学习)中心",
                    title_scope,
                    re.I,
                )
                and _contains(
                    evidence_scope,
                    "apple announced",
                    "apple has announced",
                    "苹果宣布",
                    "苹果公司宣布",
                )
            )
            or (
                _contains(title_scope, "visits", "tours", "参观", "到访")
                and _contains(
                    evidence_scope,
                    "opens",
                    "opened",
                    "opening",
                "new center",
                "new factory",
                "new facility",
                "training school",
                "manufacturing school",
                "开设",
                "启用",
                "揭幕",
                "新中心",
                "新工厂",
                "新设施",
                "培训学校",
                "制造学校",
                )
            )
        )
    )
    if facility_opening:
        title_location = _first_party_facility_location(title)
        region_values = sorted(
            region for region in regions if region and region != "multi-region"
        )
        facility_products = sorted(identity.products & _HARDWARE_FIRST_PARTY_PRODUCTS)
        if facility_subject == "manufacturing-center" and len(facility_products) == 1:
            qualifier = f"product-{facility_products[0]}"
        else:
            qualifier = (
                (region_values[0] if len(region_values) == 1 else "")
                or title_location
            )
        qualifier_suffix = f":{qualifier}" if qualifier else ""
        key = (
            f"structured-assertion:apple-facility:{facility_subject}:opening"
            f"{qualifier_suffix}"
        )
        event_keys.add(key)
        boundaries.add(f"structured-subject:apple-facility:{facility_subject}")
        separation |= {
            f"assertion-subject:apple-facility:{facility_subject}",
            "assertion-action:facility-opening",
        }

    app_store_ratings_fraud = bool(
        "app-store" in identity.products
        and _contains(evidence_scope, "rating", "ratings", "review", "reviews", "评分", "评论")
        and _contains(
            evidence_scope,
            "fraud",
            "fake",
            "misleading",
            "欺诈",
            "虚假",
            "误导",
        )
        and _contains(
            evidence_scope,
            "developer",
            "reported",
            "feedback",
            "undetected",
            "开发者",
            "反馈",
            "举报",
            "未发现",
        )
    )
    if app_store_ratings_fraud:
        key = "structured-assertion:app-store:ratings-review-fraud:developer-report"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:ratings-review-fraud")
        separation |= {
            "assertion-subject:app-store:ratings-review-fraud",
            "assertion-action:developer-fraud-report",
        }

    spyware_warning = bool(
        identity.scope == "apple-direct"
        and _contains(evidence_scope, "spyware", "间谍软件")
        and _contains(
            evidence_scope,
            "warning",
            "warnings",
            "threat notification",
            "threat notifications",
            "警报",
            "警告",
            "威胁通知",
        )
        and _contains(title_scope, "apple", "苹果")
    )
    if spyware_warning:
        key = "structured-assertion:apple-security:mercenary-spyware:threat-warning"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-security:mercenary-spyware")
        separation |= {
            "assertion-subject:apple-security:mercenary-spyware",
            "assertion-action:threat-warning",
        }

    recording_indicator_patent = bool(
        _contains(evidence_scope, "apple glasses", "苹果 glasses", "苹果智能眼镜")
        and _contains(evidence_scope, "patent", "专利")
        and _contains(evidence_scope, "recording", "record", "录制", "录像")
        and _contains(
            evidence_scope,
            "chime",
            "audio alert",
            "audible",
            "notification",
            "提示音",
            "音频提示",
            "声音提醒",
        )
    )
    if recording_indicator_patent:
        key = "structured-assertion:apple-glasses:recording-indicator:patent"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-glasses:recording-indicator")
        separation |= {
            "assertion-subject:apple-glasses:recording-indicator",
            "assertion-action:patent-disclosure",
        }

    foldable_us_first_rollout = bool(
        (
            "foldable-iphone" in identity.products
            or _contains(evidence_scope, "foldable iphone", "iphone ultra", "折叠屏 iphone", "折叠屏iphone")
        )
        and _contains(
            evidence_scope,
            "us only at launch",
            "launch only in the us",
            "only in the us",
            "launch in the us first",
            "us first",
            "prioritize the us",
            "staggered market rollout",
            "优先供应美国",
            "首批优先",
            "美国市场首发",
            "分区域阶梯上市",
        )
    )
    if foldable_us_first_rollout:
        key = "structured-assertion:foldable-iphone:staggered-us-first-rollout"
        event_keys.add(key)
        boundaries.add("structured-subject:foldable-iphone:regional-rollout")
        separation |= {
            "assertion-subject:foldable-iphone:regional-rollout",
            "assertion-action:staggered-us-first-rollout",
        }

    iphone_pro_model = re.search(
        r"(?<![a-z0-9])iphone\s*(\d{1,2})\s*pro(?:\s*(max))?(?![a-z0-9])",
        evidence_scope,
    )
    oled_panel_cost_reduction = bool(
        iphone_pro_model
        and _contains(evidence_scope, "oled", "display panel", "screen panel", "屏幕", "面板")
        and _contains(evidence_scope, "cost", "price", "成本", "价格", "报价")
        and _contains(
            evidence_scope,
            "lower",
            "lowest",
            "decrease",
            "decline",
            "cut",
            "falls",
            "压价",
            "下降",
            "降低",
            "低至",
            "最低价",
        )
    )
    if oled_panel_cost_reduction:
        model = f"iphone-{iphone_pro_model.group(1)}-pro"
        if iphone_pro_model.group(2):
            model += "-max"
        key = f"structured-assertion:{model}:oled-panel-cost:reduction"
        event_keys.add(key)
        boundaries.add(f"structured-subject:{model}:oled-panel-cost")
        separation |= {
            f"assertion-subject:{model}:oled-panel-cost",
            "assertion-action:component-cost-reduction",
        }

    app_store_external_commission = bool(
        ("app-store" in identity.products or _contains(evidence_scope, "epic"))
        and _contains(
            evidence_scope,
            "external purchase",
            "outside the app store",
            "off-app store",
            "linking outside",
            "links outside",
            "linked-out",
            "purchases made outside",
            "external payment",
            "外链",
            "外部购买",
            "外链购买",
            "外部支付",
        )
        and _contains(evidence_scope, "commission", "fee", "佣金", "抽成", "费率")
    )
    title_led_court_timing_action = bool(
        _contains(title_scope, "supreme court", "scotus", "最高法院")
        and _contains(
            title_scope,
            "delay",
            "pause",
            "stay",
            "24 hours",
            "one day",
            "晚一天",
            "延期",
            "暂停",
            "批准",
        )
    )
    commission_proposal = bool(
        app_store_external_commission
        and not title_led_court_timing_action
        and _contains(
            primary_scope,
            "proposes",
            "proposal",
            "proposed",
            "files",
            "filed",
            "submits",
            "submitted",
            "拟推行",
            "提交",
            "方案",
        )
    )
    if commission_proposal:
        key = "structured-assertion:app-store:external-purchase-commission:proposal"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:external-purchase-commission")
        separation |= {
            "assertion-subject:app-store:external-purchase-commission",
            "assertion-action:commission-proposal",
            "legal-stage:proposal-filing",
        }

    purchased_content_upgrade = (
        "apple-tv" in identity.products
        and _contains(text, "4k")
        and _contains(
            text,
            "purchased tv show",
            "purchased tv shows",
            "tv show purchases",
            "已购剧集",
            "已购内容",
        )
        and _contains(
            text,
            "free upgrade",
            "free 4k",
            "4k upgrade",
            "免费升级",
            "无需额外付费",
        )
    )
    if purchased_content_upgrade:
        key = "structured-assertion:apple-tv:purchased-content:4k-entitlement-upgrade"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-tv:purchased-content")
        separation |= {
            "assertion-subject:apple-tv:purchased-content",
            "assertion-action:entitlement-upgrade",
        }

    wallet_trade_in_quote = (
        "apple-wallet" in identity.products
        and "trade-in-valuation" in identity.components
        and _contains(text, "90 days", "90-day", "90 天", "90天")
    )
    if wallet_trade_in_quote:
        key = "structured-assertion:apple-wallet:trade-in-quote:90-day-validity"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-wallet:trade-in-quote")
        separation |= {
            "assertion-subject:apple-wallet:trade-in-quote",
            "assertion-action:trade-in-valuation-validity",
        }

    siri_publisher_license = (
        "siri" in identity.products
        and _contains(text, "publisher", "publishers", "news content", "出版商", "新闻内容", "资讯内容")
        and _contains(
            text,
            "license",
            "licensing",
            "content deal",
            "publisher deal",
            "paid partnership",
            "pay publishers",
            "talks",
            "许可协议",
            "内容合作",
            "付费",
            "支付",
            "洽谈",
        )
    )
    if siri_publisher_license:
        key = "structured-assertion:siri:publisher-news-content:licensing"
        event_keys.add(key)
        boundaries.add("structured-subject:siri:publisher-news-content")
        separation |= {
            "assertion-subject:siri:publisher-news-content",
            "assertion-action:content-licensing",
        }

    app_store_supreme_court_pause = (
        "app-store" in identity.products
        and not commission_proposal
        and _contains(text, "supreme court", "scotus", "最高法院")
        and _contains(
            text,
            "24 hours",
            "24-hour",
            "one day",
            "temporary pause",
            "administrative stay",
            "extension",
            "delay",
            "晚一天",
            "暂停",
            "延期",
            "推迟",
        )
    )
    if app_store_supreme_court_pause:
        key = "structured-assertion:app-store:supreme-court:administrative-pause"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:supreme-court")
        separation |= {
            "assertion-subject:app-store:supreme-court",
            "assertion-action:administrative-pause",
        }

    app_store_court_stay_denial = bool(
        ("app-store" in identity.products or _contains(evidence_scope, "epic"))
        and not commission_proposal
        and _contains(text, "supreme court", "scotus", "最高法院")
        and _contains(text, "denies", "denied", "rejects", "rejected", "驳回", "拒绝")
        and _contains(text, "stay", "pause", "delay", "延期", "暂停", "推迟")
    )
    if app_store_court_stay_denial:
        key = "structured-assertion:app-store:supreme-court:stay-denial"
        event_keys.add(key)
        boundaries.add("structured-subject:app-store:supreme-court")
        separation |= {
            "assertion-subject:app-store:supreme-court",
            "assertion-action:court-stay-denial",
            "legal-stage:court-stay-denial",
        }

    supplier_entities = _canonical_supplier_entities(text)
    display_products = identity.title_products & {"ipad", "ipad-air", "ipad-mini", "ipad-pro", "iphone"}
    if supplier_entities and display_products and _contains(text, "oled", "display", "panel", "面板", "显示"):
        for supplier in supplier_entities:
            for product in display_products:
                event_keys.add(f"structured-assertion:display-supplier:{supplier}:{product}")
                separation.add(f"assertion-subject:display-supplier:{supplier}:{product}")
        separation.add("assertion-action:supplier-qualification")

    if display_products and _contains(text, "oled", "display", "panel", "面板", "屏幕") and _contains(
        text, "stocking up", "increase orders", "increased orders", "additional orders", "增订", "增加订单", "追加订单"
    ):
        separation.add("assertion-action:component-stockpiling")

    apple_ai = "apple-intelligence" in identity.products or _contains(
        text, "apple intelligence", "apple 智能", "国行 ai", "国行ai"
    )
    regional_code_evidence = apple_ai and _contains(text, "china", "chinese", "国行", "中国") and _contains(
        text, "code", "reference", "string", "identifier", "代码", "踪迹", "痕迹", "线索"
    )
    if regional_code_evidence and identity.content_form != "roundup":
        key = "structured-assertion:apple-intelligence:china:code-evidence"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-intelligence:china")
        separation |= {"assertion-subject:apple-intelligence:china", "assertion-action:code-evidence"}

    iphone_code_subject = bool(
        identity.products & {"iphone", "foldable-iphone"}
        or re.search(r"(?<![a-z0-9])iphone(?![a-z0-9])|苹果.{0,4}(?:手机|新机)", text)
    )
    unreleased_status = bool(
        _contains(text, "unreleased", "not yet released", "未发布", "尚未发布", "未发新机")
    )
    enumerated_iphone_set = bool(
        re.search(
            r"\b(?:six|\d+)\s+(?:unreleased\s+)?iphone|"
            r"(?:六|6)\s*款.{0,18}(?:iphone|苹果.{0,4}(?:手机|新机))|"
            r"(?:iphone|苹果.{0,4}(?:手机|新机)).{0,18}(?:六|6)\s*款",
            text,
        )
    )
    unreleased_model_code_set = bool(
        iphone_code_subject
        and _contains(text, "code", "identifier", "代码", "代号", "系统文件")
        and unreleased_status
        and enumerated_iphone_set
    )
    if unreleased_model_code_set:
        event_keys.add("structured-assertion:iphone:unreleased-model-code-set")
        separation |= {"assertion-subject:iphone-code-model-set", "assertion-action:code-evidence"}

    if "icloud" in identity.products and _contains(text, "icloud+", "icloud plus", "icloud storage") and _contains(
        text, "perk", "benefit", "unlock", "higher tier", "2tb", "权益", "解锁", "高阶", "高级"
    ):
        event_keys.add("structured-assertion:icloud-plus:tier-entitlements")
        separation |= {"assertion-subject:icloud-plus", "assertion-action:tier-entitlement-change"}

    anniversary_iphone = _contains(evidence_scope, "20th-anniversary", "20th anniversary", "20 周年", "20周年", "二十周年")
    anniversary_generation = "product-generation:iphone-20" in identity.components
    anniversary_glass_display = bool(
        (anniversary_iphone or anniversary_generation)
        and "iphone" in identity.products
        and _contains(
            evidence_scope,
            "glass",
            "rounded",
            "rounder",
            "玻璃",
            "bezel",
            "边框",
            "曲面",
            "圆润",
        )
        and _contains(
            evidence_scope,
            "display", "screen", "design", "redesign", "on track", "remain", "cancel",
            "look like", "thinner", "屏", "设计", "外观", "更薄", "仍在推进", "没有取消",
        )
    )
    if anniversary_glass_display:
        key = "structured-assertion:iphone-anniversary-redesign:glass-display"
        event_keys.add(key)
        boundaries.add("structured-subject:iphone-anniversary-redesign")
        separation |= {"assertion-subject:iphone-anniversary-redesign", "assertion-action:glass-display-redesign"}

    display_inventory_buffer = bool(
        _contains(evidence_scope, "oled", "display panel", "screen panel", "显示屏", "面板")
        and _contains(evidence_scope, "inventory", "buffer", "stock", "储备", "备货", "库存", "供应缓冲")
        and _contains(evidence_scope, "4 weeks", "four weeks", "4 周", "4周", "四周")
        and _contains(evidence_scope, "6 weeks", "six weeks", "6 周", "6周", "六周")
        and _contains(evidence_scope, "extend", "increase", "longer", "延长", "增加", "加大")
    )
    if display_inventory_buffer:
        key = "structured-assertion:apple-display-inventory:buffer-extension"
        event_keys.add(key)
        boundaries.add("structured-subject:apple-display-inventory")
        separation |= {
            "assertion-subject:apple-display-inventory",
            "assertion-action:inventory-buffer-extension",
        }

    foldable_cover_protector_leak = bool(
        "foldable-iphone" in identity.products
        and _contains(
            evidence_scope,
            "screen protector",
            "protective film",
            "cover display protector",
            "外屏贴膜",
            "屏幕贴膜",
            "保护膜",
            "贴膜",
        )
        and (
            _contains(evidence_scope, "screen protector", "屏幕贴膜")
            or _contains(
                evidence_scope,
                "cover display",
                "cover-display",
                "outer display",
                "front display",
                "外屏",
                "正面屏幕",
            )
        )
        and _contains(
            evidence_scope,
            "screen protector",
            "protective film",
            "images",
            "video",
            "图片",
            "视频",
            "贴膜",
            "保护膜",
        )
    )
    if foldable_cover_protector_leak:
        key = "structured-assertion:foldable-iphone:cover-display-protector-leak"
        event_keys.add(key)
        boundaries.add("structured-subject:foldable-iphone:cover-display-protector")
        separation |= {
            "assertion-subject:foldable-iphone-cover-display-protector",
            "assertion-action:display-shape-leak",
        }

    reference_image_authentication = bool(
        (identity.products & {"iphone", "ios"} or _contains(evidence_scope, "iphone", "ios"))
        and _contains(evidence_scope, "photo", "photos", "image", "照片", "图像")
        and (
            _contains(
                evidence_scope,
                "apple reference image",
                "reference image",
                "reference mode",
                "provenance",
            )
            or (
                _contains(evidence_scope, "authenticat", "prove", "verify", "认证", "验证", "证明")
                and _contains(evidence_scope, "taken", "altered", "metadata", "拍摄", "修改", "元数据")
            )
        )
    )
    if reference_image_authentication:
        key = "structured-assertion:iphone-camera:reference-image-authentication"
        event_keys.add(key)
        boundaries.add("structured-subject:iphone-camera:reference-image")
        separation |= {
            "assertion-subject:iphone-camera:reference-image",
            "assertion-action:photo-authentication",
        }

    impersonation_subject = _app_store_impersonation_subject(title, short_lead)
    if impersonation_subject:
        key = f"structured-assertion:app-store:{impersonation_subject}:impersonation-incident"
        event_keys.add(key)
        boundaries.add(f"structured-subject:app-store:{impersonation_subject}")
        separation |= {
            f"assertion-subject:app-store:{impersonation_subject}",
            "assertion-action:app-impersonation-incident",
        }

    foldable = "foldable-iphone" in identity.products
    if foldable and _contains(text, "called", "named", "name", "称为", "名称", "命名"):
        key = "structured-assertion:foldable-iphone:product-naming"
        event_keys.add(key)
        boundaries.add("structured-subject:foldable-iphone")
        separation |= {"assertion-subject:foldable-iphone", "assertion-action:product-naming"}

    supplier_terms = ("memory", "dram", "nand", "ram", "内存", "存储", "闪存")
    capacity_terms = (
        "capacity", "shortage", "constraint", "restriction", "crunch", "maxed out",
        "unavailable", "产能", "短缺", "限制", "紧缺", "供给受限",
    )
    negotiation_terms = (
        "negot", "talks", "bid", "low price", "rejected", "offer",
        "谈判", "洽谈", "议价", "压价", "拒绝", "报价",
    )
    cost_pattern = re.compile(
        r"\b(?:bill of materials|bom|component cost|manufacturing cost|costs? apple)\b|"
        r"(?:零部件|物料|制造|生产)?成本.{0,18}(?:上涨|增加|大增|暴涨|提高|预计)"
    )
    direct_product_price_pattern = re.compile(
        r"\b(?:apple|iphone|ipad|mac(?:book| mini| studio| pro)?|product)s?\b.{0,32}"
        r"(?:price increases?|price hikes?|get(?:s|ting)? more expensive)|"
        r"(?:苹果产品|iphone|ipad|mac).{0,24}(?:涨价|售价上调|价格上调|提价)|"
        r"(?:涨价|售价上调|价格上调).{0,24}(?:苹果产品|iphone|ipad|mac)"
    )

    def supplier_actions(scope: str) -> set[str]:
        if not _contains(scope, *supplier_terms):
            return set()
        actions: set[str] = set()
        if _contains(scope, *capacity_terms):
            actions.add("assertion-action:supplier-capacity-constraint")
        if _contains(scope, *negotiation_terms):
            actions.add("assertion-action:supplier-price-negotiation")
        if cost_pattern.search(scope) and not direct_product_price_pattern.search(scope):
            actions.add("assertion-action:product-component-cost-forecast")
        return actions

    # A concrete headline action is authoritative. Fall back to the first lead
    # sentence only when the headline itself does not identify the action.
    separation |= supplier_actions(title_scope) or supplier_actions(primary_scope)

    if "apple-pay" in identity.products and _contains(text, "launch", "roll out", "上线", "推出") and _contains(
        text, "india", "country", "market", "印度", "地区", "市场"
    ):
        event_keys.add("structured-assertion:apple-pay:regional-launch")
        separation |= {"assertion-subject:apple-pay", "assertion-action:regional-launch"}

    personnel_departure = _contains(text, "retiring", "retires", "retirement", "leaving", "steps down", "退休", "离职", "卸任")
    if personnel_departure:
        person = ""
        for pattern in (
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}?)\s+(?:is\s+)?(?:retiring|retires|leaving|steps down)\b",
            r"\b(?:Chief|VP|Vice President)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
        ):
            match = re.search(pattern, title)
            if match:
                person = re.sub(r"[^a-z0-9]+", "-", _normalized(match.group(1))).strip("-")
                break
        if person:
            event_keys.add(f"structured-assertion:apple-personnel:{person}:departure")
            separation |= {f"assertion-subject:apple-personnel:{person}", "assertion-action:personnel-departure"}
        if identity.products & {"apple-pay", "apple-wallet", "apple-card"}:
            event_keys.add("structured-assertion:apple-pay-wallet:personnel-departure")
            separation |= {"assertion-subject:apple-pay-wallet", "assertion-action:personnel-departure"}

    personnel_appointment = (
        _contains(text, "hire", "hires", "hired", "appoint", "appoints", "appointed", "picks up", "任命", "聘任", "招募")
        and _contains(
            text,
            "vice president",
            "head of",
            "executive",
            "chief",
            "副总裁",
            "负责人",
            "主管",
            "高管",
        )
    )
    if personnel_appointment:
        person = ""
        for pattern in (
            r"\b(?:hires?|hired|appoints?|appointed|picks?\s+up)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b",
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+as\s+(?:new\s+)?(?:head|vice president|chief)\b",
            r"(?:任命|聘任|招募)\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,2})\s*(?:为|担任)",
        ):
            match = re.search(pattern, title)
            if match:
                person = re.sub(r"[^a-z0-9]+", "-", _normalized(match.group(1))).strip("-")
                break
        if person:
            key = f"structured-assertion:apple-personnel:{person}:appointment"
            event_keys.add(key)
            boundaries.add(f"structured-subject:apple-personnel:{person}")
            separation.add(f"assertion-subject:apple-personnel:{person}")
        if _contains(text, "government affairs", "政府事务"):
            role_key = "structured-assertion:apple-personnel:government-affairs-lead:appointment"
            event_keys.add(role_key)
            boundaries.add("structured-subject:apple-personnel:government-affairs-lead")
            separation.add("assertion-subject:apple-personnel:government-affairs-lead")
        separation.add("assertion-action:personnel-appointment")

    patent_disclosure = _contains(title_scope, "patent", "patents", "专利")
    if patent_disclosure:
        separation.add("assertion-action:patent-disclosure")
        notification_focus = _contains(
            text,
            "notification summary",
            "notification summaries",
            "interruptions",
            "focus mode",
            "通知摘要",
            "减少中断",
            "专注模式",
            "打扰",
            "发出通知",
        )
        if notification_focus:
            key = "structured-assertion:apple-patent:notification-interruption-management"
            event_keys.add(key)
            boundaries.add("structured-subject:apple-patent:notification-interruption-management")
            separation.add("assertion-subject:apple-patent:notification-interruption-management")

    birthday_feature = bool(
        "ios" in identity.products
        and _contains(text, "birthday", "生日")
        and _contains(text, "reminder", "fireworks", "call", "提醒", "烟花", "通话")
    )
    if birthday_feature:
        event_keys.add("structured-assertion:ios-phone:birthday-reminder")
        separation |= {"assertion-subject:ios-phone", "assertion-action:birthday-reminder"}

    back_to_school_extension = bool(
        _contains(text, "back to school", "返校季", "教育优惠")
        and _contains(text, "extend", "extended", "extension", "延长", "延期")
        and re.search(r"\b(?:september|august)\s+\d{1,2}\b|\d{1,2}\s*月\s*\d{1,2}\s*日", text)
    )
    if back_to_school_extension:
        event_keys.add("structured-assertion:apple-back-to-school:date-extension")
        separation |= {"assertion-subject:apple-back-to-school", "assertion-action:date-extension"}

    product_storage_spec = bool(
        identity.title_products & {"iphone", "ipad", "mac", "macbook"}
        and re.search(r"\b\d+\s*(?:gb|tb)\b|\d+\s*(?:gb|tb)|\d+\s*[gt]b|\d+\s*gb|\d+\s*tb", text)
        and _contains(text, "starts at", "base storage", "storage capacity", "维持", "起步", "基础存储", "容量")
    )
    if product_storage_spec:
        separation.add("assertion-action:product-storage-specification")

    return event_keys, boundaries, separation


def _event_staff_support(text: str) -> bool:
    return (
        _contains(text, "lottery", "抽签")
        and _contains(text, "staff", "employee", "retail worker", "零售员工", "门店员工", "员工")
        and _contains(text, "event", "发布会", "现场支持", "现场支援")
    )


def _event_preparation(text: str) -> bool:
    return (
        _contains(text, "september", "9 月", "九月")
        and _contains(text, "event", "发布会")
        and _contains(
            text,
            "prepar",
            "getting ready",
            "revealed a clue",
            "lottery",
            "staff support",
            "employee support",
            "筹备",
            "准备",
            "抽签",
            "员工支援",
            "现场支援",
            "现场支持",
        )
    )


def _event_format_plan(text: str) -> bool:
    return (
        _contains(text, "event", "keynote", "iphone launch", "发布会", "新品活动")
        and _contains(
            text,
            "pre-recorded",
            "prerecorded",
            "pre recorded",
            "live presentation",
            "live on stage",
            "live segment",
            "live elements",
            "hybrid format",
            "录播",
            "预录",
            "现场直播",
            "现场环节",
            "混合方案",
            "混合形式",
        )
        and _contains(
            text,
            "report",
            "reported",
            "likely",
            "unlikely",
            "expected",
            "could be",
            "will likely",
            "消息称",
            "报道称",
            "预计",
            "大概率",
            "可能",
        )
    )


def _apple_first_party_home_camera_roadmap(title: str, text: str) -> bool:
    """Identify one first-party Apple Home camera roadmap action."""
    title_has_apple_platform = _contains(
        title,
        "apple",
        "ios",
        "苹果",
    )
    apple_camera = bool(
        re.search(
            r"(?:apple|苹果).{0,45}(?:home security camera|security camera|家用安防摄像头|安防摄像头)",
            text,
        )
        or re.search(
            r"(?:home security camera|security camera|家用安防摄像头|安防摄像头).{0,45}(?:apple|苹果)",
            text,
        )
    )
    roadmap_action = _contains(
        text,
        "launch",
        "debut",
        "coming soon",
        "rumored",
        "roadmap",
        "推出",
        "登场",
        "有望",
        "传闻",
        "路线图",
    )
    return title_has_apple_platform and apple_camera and roadmap_action


def _third_party_app_availability_without_platform_change(
    title: str,
    lead: str,
) -> bool:
    """Return true when an OS name is context for a third-party app action.

    A version number alone must not transfer action ownership from an app or
    service vendor to Apple.  A first-party API, policy, or platform-capability
    change remains eligible because the title explicitly assigns that action
    to Apple or the platform.
    """
    third_party_subject = bool(
        re.search(
            r"\bthird[- ]party\b.{0,24}\b(?:apps?|services?)\b|"
            r"(?:第三方).{0,18}(?:应用|服务|聊天机器人)",
            title,
            re.I,
        )
    )
    availability_action = bool(
        re.search(
            r"\b(?:available|availability|arrives?|coming|supports?|integrates?|"
            r"adds?\s+support|works?\s+with)\b|"
            r"(?:接入|上线|可用|支持|适配|兼容)",
            title,
            re.I,
        )
    )
    first_party_platform_change = bool(
        re.search(
            r"\b(?:apple|ios|ipados|macos|watchos|tvos|visionos|carplay)\b"
            r".{0,42}\b(?:opens?|enables?|introduces?|adds?|changes?|updates?|"
            r"expands?)\b.{0,42}\b(?:api|framework|policy|platform|third[- ]party\s+app\s+support)\b|"
            r"(?:苹果|ios|ipados|macos|watchos|tvos|visionos|carplay)"
            r".{0,32}(?:开放|启用|引入|新增|调整|更新|扩展)"
            r".{0,32}(?:接口|框架|政策|平台能力|第三方应用支持)",
            f"{title}. {lead}",
            re.I,
        )
    )
    return third_party_subject and availability_action and not first_party_platform_change


def _versioned_os_feature_report(text: str, identity: EventIdentity) -> bool:
    title = text.split(". ", 1)[0]
    lead = text.split(". ", 1)[1] if ". " in text else ""
    if _third_party_app_availability_without_platform_change(title, lead):
        return False
    proposal_pattern = (
        r"\b(?:i|we)\s+(?:would|should|wish(?:ed)?\s+(?:apple\s+)?would)\s+"
        r"(?:change|add|remove|redesign|fix|improve)\b|"
        r"\bapple\s+(?:should|needs?\s+to|ought\s+to)\s+"
        r"(?:change|add|remove|redesign|fix|improve)\b|"
        r"(?:我|我们)(?:会|希望|认为苹果应当|认为苹果应该).{0,24}"
        r"(?:改变|新增|移除|重设计|修复|改进)"
    )
    proposal_or_wishlist = bool(
        re.search(proposal_pattern, title, re.I)
    )
    asserted_title_scope = re.sub(proposal_pattern, "", title, flags=re.I)
    asserted_current_change = bool(
        re.search(
            r"\b(?:adds?|added|adding|brings?|brought|changes?|changed|changing|"
            r"updates?|updated|updating|upgrades?|upgraded|upgrading|removes?|removed|"
            r"redesigns?|redesigned|fixes?|fixed|expands?|expanded)\b|"
            r"(?:新增|加入|带来|调整|更改|更新|升级|移除|重设计|修复|扩展)",
            asserted_title_scope,
            re.I,
        )
    )
    if proposal_or_wishlist and not asserted_current_change:
        return False
    security_bulletin = _contains(
        title,
        "security fix",
        "security fixes",
        "security flaw",
        "security flaws",
        "cve",
        "vulnerabilities",
        "安全修复",
        "安全漏洞",
        "漏洞",
    )
    release_announcement = bool(
        re.search(
            r"\b(?:releas(?:e|es|ed|ing)|ships?|shipped|now available|rolls out|land|lands)\b|"
            r"(?:发布|推送|正式版)",
            title,
        )
        or _lead_asserts_first_party_release(lead)
    )
    if security_bulletin and not release_announcement:
        return False
    title_os = identity.title_products & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    versioned_title = bool(
        re.search(
            r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+\d+(?:\.\d+){0,2}\b",
            title,
            flags=re.IGNORECASE,
        )
        or any(component.startswith("os-wave:") for component in identity.components)
        or any(component.startswith("os-wave-platform:") for component in identity.components)
        or (
            release_announcement
            and re.search(
                r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
                r"(?:\s+[a-z][a-z-]+){0,2}\s+\d+(?:\.\d+){0,2}\b",
                text,
                flags=re.IGNORECASE,
            )
        )
    )
    numbered_incremental = bool(
        re.search(
            r"\bbeta\s*\d+\b|"
            r"(?:开发者预览版|开发者测试版|测试版)\s*beta?\s*\d+|"
            r"第\s*\d+\s*(?:个|版)?\s*(?:开发者)?测试版",
            title,
        )
    )
    explicit_feature_change = "feature-change" in identity.title_actions
    direct_first_party_lead_change = bool(
        re.search(
            r"\bapple\s+(?:(?:is|has|will|plans?\s+to|continues?\s+to)\s+)?"
            r"(?:adds?|adding|brings?|bringing|changes?|changing|updates?|updating|"
            r"redesigns?|redesigning|integrates?|integrating|moves?|moving)\b|"
            r"(?:苹果).{0,35}(?:新增|加入|带来|调整|更改|更新|重设计|整合|移入)",
            lead,
            re.I,
        )
    )
    current_change = bool(
        explicit_feature_change
        or direct_first_party_lead_change
        or release_announcement
        or (
            identity.content_form == "news"
            and _contains(
                title,
                "feature",
                "features",
                "change",
                "changes",
                "功能",
                "变化",
            )
        )
        or (
            numbered_incremental
            and _contains(
                title,
                "what's new",
                "everything new",
                "new in",
                "feature",
                "features",
                "changes",
                "功能",
                "变化",
                "更新",
                "发布",
                "测试版",
            )
        )
        or (
            identity.content_form == "news"
            and re.search(
                r"\b(?:releas(?:e|es|ed|ing)|ships?|shipped|seeds|now available|rolls out|land|lands)\b|"
                r"(?:发布|推送)",
                title,
            )
        )
    )
    return bool(
        title_os
        and identity.scope == "apple-direct"
        and versioned_title
        and current_change
    )


def _versioned_shared_resource_operation(title: str, lead: str) -> tuple[str, str] | None:
    """Bind a cross-device operation to its OS version and shared resource."""
    title_text, primary_scope = _primary_assertion_scope(title, lead)
    version = re.search(
        r"(?<![a-z0-9])(ios|ipados|macos|watchos|tvos|visionos)\s*"
        r"(\d+(?:\.\d+){0,2})(?![0-9.])", title_text,
    )
    if not version or not re.search(r"\b(?:new|adds?|introduces?)\b|新增|加入|全新", title_text):
        return None
    devices = sorted(set(re.findall(
        r"(?<![a-z0-9])(iphone|ipad|mac|macbook|apple watch|vision pro)s?(?![a-z0-9])",
        primary_scope,
    )))
    cross_device = re.search(
        r"\b(?:two|multiple|both)\s+(?:\w+\s+)?(?:iphones|ipads|macs|macbooks|devices|watches)\b|"
        r"\b(?:between|across)\b.{0,60}\bdevices\b|"
        r"(?:两|多)(?:台|部|个)\s*(?:iphone|ipad|mac|设备|手机|电脑)", primary_scope,
    )
    resources = {
        name for name, pattern in (
            ("phone-number", r"(?:phone|telephone)\s+number|(?:esim|手机|电话)?号码"),
            ("account", r"account|账户|账号"),
            ("session", r"session|会话"),
        )
        if re.search(
            rf"\bsame\s+(?:{pattern})|(?:共用|共享)?(?:同一个|同一|一个)\s*(?:{pattern})",
            primary_scope,
        )
    }
    switching = re.search(r"\bswitch(?:ing)?\b|切换", primary_scope)
    negated = re.search(
        r"\b(?:cannot|can't|does not|will not)\s+switch\b|(?:不能|无法|不支持).{0,8}切换",
        primary_scope,
    )
    if devices and cross_device and len(resources) == 1 and switching and not negated:
        device_subject = "+".join(device.replace(" ", "-") for device in devices)
        return (
            f"{version.group(1)}-{version.group(2)}:{device_subject}:{next(iter(resources))}",
            "cross-device-switch",
        )
    return None


def _versioned_os_feature_scope(text: str, identity: EventIdentity) -> str:
    title, _, lead = text.partition(". ")
    operation = _versioned_shared_resource_operation(title, lead)
    if operation:
        subject, predicate = operation
        return f"apple-os-feature-scope:{subject}:{predicate}"
    if not _versioned_os_feature_report(text, identity):
        return ""
    text_parts = text.split(". ", 1)
    title = text_parts[0]
    lead = text_parts[1] if len(text_parts) == 2 else ""
    release_lead = bool(
        not identity.title_actions
        and _lead_asserts_first_party_release(lead)
    )
    release_title = _contains(
        title,
        "release",
        "released",
        "now available",
        "rolls out",
        "land",
        "lands",
        "发布",
        "推送",
        "正式版",
    ) or release_lead
    release_waves = sorted(
        component
        for component in identity.components
        if component.startswith("os-wave:")
    )
    concrete_title_components = {
        component
        for component in identity.title_components
        if component.startswith("os-component:")
        or component in LEAD_IDENTITY_COMPONENTS
    }
    title_describes_feature = _contains(
        title,
        "what's new",
        "everything new",
        "new feature",
        "new features",
        "changes",
        "功能",
        "变化",
        "更新汇总",
        "new icon",
        "new icons",
        "redesigned icon",
        "redesigned icons",
        "新图标",
        "图标重设计",
    )
    platform_release_waves = sorted(
        component
        for component in identity.components
        if component.startswith("os-wave-platform:")
    )
    if not release_waves:
        version_match = re.search(
            r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+(\d+(?:\.\d+){0,2})\b",
            text,
            flags=re.IGNORECASE,
        )
        beta_match = re.search(r"\bbeta\s*(\d+)\b", title)
        if version_match and release_title:
            stage = f"beta-{beta_match.group(1)}" if beta_match else "final"
            release_waves = [f"os-wave:{version_match.group(1)}:{stage}"]
    if not release_waves and platform_release_waves and release_title and not title_describes_feature:
        platform_wave = platform_release_waves[0].removeprefix("os-wave-platform:")
        return f"apple-os-platform-release-wave:{platform_wave}"
    if release_waves and (
        (release_waves[0].endswith(":final") and release_title)
        or (not concrete_title_components and not title_describes_feature)
    ):
        wave = release_waves[0].removeprefix("os-wave:")
        if wave.endswith(":final"):
            os_family = sorted(
                identity.title_products
                & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
            )[0]
            platform_family = "mobile" if os_family in {"ios", "ipados"} else os_family
            return f"apple-os-release-wave:{wave}:{platform_family}"
        return f"apple-os-release-wave:{wave}"
    os_family = sorted(
        identity.title_products & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    )[0]
    feature_wave = ""
    if release_waves:
        feature_wave = release_waves[0].removeprefix("os-wave:")
    elif platform_release_waves:
        feature_wave = platform_release_waves[0].removeprefix("os-wave-platform:")
    else:
        version_match = re.search(
            r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+(\d+(?:\.\d+){0,2})\b",
            title,
            flags=re.IGNORECASE,
        )
        beta_match = re.search(r"\bbeta\s*(\d+)\b", title)
        if version_match:
            stage = f"beta-{beta_match.group(1)}" if beta_match else "current"
            feature_wave = f"{version_match.group(1)}:{stage}"
    if identity.content_form == "roundup" and feature_wave:
        return f"apple-os-feature-roundup:{os_family}:{feature_wave}"
    icon_change = bool(
        re.search(
            r"\b(?:new|redesigned|updated|changed)\s+(?:[a-z]+\s+){0,3}icons?\b|"
            r"\bicons?\b.{0,36}\b(?:redesign(?:ed)?|update(?:d)?|change(?:d)?)\b|"
            r"(?:新增|启用|带来|采用|更换|重设计|重新设计|调整|更新).{0,24}图标|"
            r"图标.{0,24}(?:新增|启用|重设计|重新设计|调整|更新)",
            title,
        )
    )
    if icon_change and feature_wave:
        return f"apple-os-feature-scope:{os_family}:{feature_wave}:component:app-icons"
    components = sorted(
        component
        for component in identity.title_components
        if component.startswith("os-component:")
    )
    if not components:
        component_patterns = (
            ("messages", ("messages", "信息 app", "信息应用")),
            ("camera", ("camera app", "相机 app", "相机应用")),
            ("mail", ("mail", "邮件 app", "邮件应用")),
            ("notes", ("notes", "备忘录")),
            ("weather", ("weather", "天气 app", "天气应用")),
            ("shortcuts", ("shortcuts", "快捷指令")),
            ("wallet", ("wallet", "钱包 app", "钱包应用")),
            ("maps", ("maps", "地图 app", "地图应用")),
            ("safari", ("safari",)),
            ("photos", ("photos", "照片 app", "照片应用")),
            ("settings", ("settings", "设置 app", "系统设置")),
            ("control-center", ("control center", "控制中心")),
            ("lock-screen", ("lock screen", "锁屏")),
            ("home-screen", ("home screen", "主屏幕")),
        )
        components = [
            f"os-component:{name}"
            for name, terms in component_patterns
            if _contains(title, *terms)
        ]
    if not components:
        components = sorted(identity.components & LEAD_IDENTITY_COMPONENTS)
    if not components:
        components = sorted(
            component
            for component in identity.title_components
            if not component.startswith(
                (
                    "apple-silicon-generation:",
                    "iphone-family:",
                    "iphone-line:",
                    "iphone-model:",
                    "macbook-model:",
                    "primary-intent:",
                    "product-generation:",
                    "report-attribution:",
                )
            )
        )
    title_subject_products = sorted(
        identity.title_products
        - {"ios", "ipados", "macos", "watchos", "tvos", "visionos", "iphone", "ipad", "mac"}
    )
    primary_names = identity.title_named_subjects or {
        subject for subject in identity.named_subjects
        if subject.replace("-", " ") in _primary_assertion_scope("", lead)[1]
    }
    branded_named_subjects = {
        subject
        for subject in primary_names
        if subject.startswith("apple-")
    }
    named_subject_candidates = {
        subject.removeprefix("apple-")
        for subject in (branded_named_subjects or primary_names)
        if subject
        not in {
            "airpods",
            "apple-tv",
            "apple-watch",
            "homekit",
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "safari",
            "siri",
            "vision-pro",
        }
    }
    named_subjects = sorted(
        subject
        for subject in named_subject_candidates
        if not any(
            other != subject and other.startswith(f"{subject}-")
            for other in named_subject_candidates
        )
    )
    if len(components) == 1:
        subject = f"component:{components[0]}"
    elif len(named_subjects) == 1:
        subject = f"named:{named_subjects[0]}"
    elif len(title_subject_products) == 1:
        subject = f"product:{title_subject_products[0]}"
    else:
        subject = "multi-feature"
    return f"apple-os-feature-scope:{os_family}:{subject}"


def _broad_component_supply_outlook(text: str) -> bool:
    title = text.split(". ", 1)[0]
    return bool(
        not _contains(title, "apple", "iphone", "ipad", "mac", "苹果")
        and _contains(title, "ram", "memory", "dram", "nand", "内存", "存储")
        and _contains(
            title,
            "worldwide",
            "global",
            "industry",
            "sold out",
            "capacity",
            "shortage",
            "全球",
            "行业",
            "售罄",
            "产能",
            "短缺",
        )
    )


def _supplier_market_without_apple_action(text: str, identity: EventIdentity) -> bool:
    title = text.split(". ", 1)[0]
    return bool(
        not _contains(title, "apple", "iphone", "ipad", "mac", "苹果")
        and identity.scope != "apple-direct"
        and _contains(
            title,
            "supplier",
            "supply",
            "capacity",
            "production",
            "order",
            "供应",
            "产能",
            "供货",
            "订单",
            "长鑫",
            "长江存储",
            "cxmt",
            "ymtc",
        )
        and _contains(
            title,
            "price",
            "capacity",
            "production",
            "order",
            "supply",
            "价格",
            "产能",
            "量产",
            "订单",
            "供货",
            "锁产能",
        )
    )


def _measured_applied_research_key(text: str, identity: EventIdentity) -> str:
    products = sorted(identity.title_products & {"vision-pro", "apple-watch", "airpods", "iphone", "ipad", "mac", "macbook"})
    if not products or not _contains(
        text,
        "peer-reviewed",
        "peer reviewed",
        "study",
        "clinical trial",
        "同行评审",
        "研究显示",
        "临床试验",
    ):
        return ""
    if not _contains(
        text,
        "using vision pro",
        "used vision pro",
        "wore vision pro",
        "primary display",
        "using apple watch",
        "using airpods",
        "using iphone",
        "使用 vision pro",
        "佩戴 vision pro",
        "作为主要显示设备",
        "使用 apple watch",
        "使用 airpods",
        "使用 iphone",
    ):
        return ""
    minute_values = sorted(
        {
            value.rstrip("0").rstrip(".")
            for value in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:minutes?|分钟)", text)
        },
        key=lambda value: float(value),
    )
    percentages = sorted(
        {
            value.rstrip("0").rstrip(".")
            for value in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", text)
        },
        key=lambda value: float(value),
    )
    metric = "-".join(minute_values[:2]) if len(minute_values) >= 2 else (percentages[0] if percentages else "")
    if not metric:
        return ""
    domain = "clinical-workflow" if _contains(text, "surgery", "operation", "procedure", "手术", "临床") else "measured-use"
    return f"apple-product-research:{products[0]}:{domain}:{metric}"


def _product_driven_market_forecast_key(text: str, identity: EventIdentity) -> str:
    products = sorted(identity.title_products & {"foldable-iphone", "iphone", "ipad", "macbook", "apple-watch", "airpods", "vision-pro"})
    if not products:
        return ""
    if not _contains(text, "market", "shipments", "sales", "市场", "出货量", "销量"):
        return ""
    if not _contains(
        text,
        "forecast",
        "expected to grow",
        "expected to rise",
        "driving the increase",
        "main driver",
        "due to",
        "预测",
        "预计增长",
        "重要驱动力",
        "主要驱动力",
        "推动增长",
    ):
        return ""
    percentages = sorted(
        {
            value.rstrip("0").rstrip(".")
            for value in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", text)
        },
        key=lambda value: float(value),
    )
    if not percentages:
        return ""
    market = "foldable" if _contains(text, "foldable", "折叠屏", "折叠 iphone") else "product-segment"
    return f"apple-market:{market}:{products[0]}:{percentages[0]}"


def _annual_sales_metric(text: str) -> bool:
    return bool(
        re.search(r"\bannual\b.{0,32}\b(?:sales|revenue)\b", text)
        or re.search(r"(?:年度|年)(?:销售额|营收)|(?:销售额|营收).{0,8}(?:年度|全年|首次突破)", text)
    )


def _multi_product_price_forecast(text: str) -> bool:
    product_patterns = (
        r"\biphone\b",
        r"\bipad\b",
        r"\bmac(?:book)?\b",
        r"\bapple watch\b|苹果手表",
        r"\bairpods\b",
        r"\bvision pro\b",
        r"\bhomepod\b",
        r"\bapple tv\b",
    )
    product_count = sum(bool(re.search(pattern, text)) for pattern in product_patterns)
    return (
        product_count >= 2
        and _contains(text, "price", "prices", "expensive", "涨价", "提价", "价格上调", "售价上调")
        and _contains(
            text,
            "expected",
            "likely",
            "forecast",
            "rumor",
            "could",
            "may",
            "预计",
            "预期",
            "可能",
            "分析师",
            "爆料",
        )
    )


def _bug_bounty_submission_limit(text: str) -> bool:
    return (
        _contains(text, "bug bounty", "漏洞赏金")
        and _contains(
            text,
            "limit",
            "quota",
            "cooldown",
            "clogging",
            "flood",
            "配额",
            "限制",
            "冷静期",
            "堵塞",
            "泛滥",
        )
        and _contains(text, "submission", "report", "提交", "报告")
    )


def _icloud_private_relay_leak(text: str) -> bool:
    return (
        _contains(text, "private relay", "icloud 专用代理", "icloud+隐私", "icloud+ 隐私")
        and _contains(text, "leak", "expose", "vulnerability", "漏洞", "泄露", "暴露", "风险")
        and _contains(
            text,
            "real ip",
            "ip address",
            "dns",
            "真实ip",
            "真实 ip",
            "网络信息",
        )
    )


def _webkit_proxy_leak(text: str) -> bool:
    return (
        "webkit" in text
        and _contains(text, "leak", "expose", "vulnerability", "漏洞", "泄露", "风险")
        and _contains(
            text,
            "proxy",
            "private relay",
            "dns",
            "webtransport",
            "代理",
            "网络信息",
            "ip",
        )
    )


def _app_store_removal_stage(text: str) -> str:
    explicit_store_surface = _contains(text, "app store", "应用商店", "苹果应用商店")
    explicit_apple_app_removal = bool(
        re.search(
            r"\bapple\b.{0,24}\b(?:remov(?:es|ed|al)?|pull(?:s|ed)?|yank(?:s|ed)?|delist(?:s|ed)?)\b"
            r".{0,30}\b(?:app|application)\b|"
            r"(?:苹果).{0,16}(?:下架|移除|撤下).{0,16}(?:应用|app)",
            text,
        )
    )
    if not (
        (explicit_store_surface or explicit_apple_app_removal)
        and _contains(text, "remov", "pull", "yank", "delist", "下架", "移除", "撤下")
    ):
        return ""
    if _contains(
        text,
        "extortion",
        "planted",
        "manipulated",
        "weaponized",
        "alleged",
        "alleges",
        "勒索",
        "设局",
        "操纵",
        "植入",
        "武器化",
        "指控",
    ):
        return "followup-allegation"
    return "initial-removal"


def _app_store_subjects(title: str, identity: EventIdentity) -> set[str]:
    ignored = _GENERIC_SUBJECT_WORDS | {
        "app",
        "apple",
        "briefly",
        "cnbeta",
        "com",
        "content",
        "csam",
        "im",
        "illegal",
        "material",
        "removed",
        "removal",
        "store",
        "why",
    }
    object_match = re.search(
        r"(?:remove(?:s|d)?|pull(?:s|ed)?|yank(?:s|ed)?|ban(?:s|ned|ning)?)\s+"
        r"([a-z][a-z0-9.+-]{2,30})\s+(?:from|off)\b",
        title,
    )
    if not object_match:
        object_match = re.search(
            r"(?:remove(?:s|d)?|pull(?:s|ed)?|yank(?:s|ed)?|ban(?:s|ned|ning)?)\s+"
            r"([a-z][a-z0-9.+-]{2,30})(?:\b|[?？])",
            title,
        )
    if not object_match:
        object_match = re.search(
            r"(?:下架|移除|撤下)\s*(?:了)?\s*"
            r"([A-Za-z][A-Za-z0-9.+-]{2,30})(?:\b|[?？])",
            title,
        )
    if object_match and object_match.group(1) not in ignored:
        return {object_match.group(1)}
    leading_subject = re.match(
        r"^([A-Za-z][A-Za-z0-9.+-]{2,30})(?:\s|[：:，,])",
        title,
    )
    if leading_subject and leading_subject.group(1) not in ignored:
        return {leading_subject.group(1)}
    subjects = _subject_tokens(title, identity)
    return {
        subject
        for subject in subjects
        if subject not in ignored
        and subject in identity.title_named_subjects
    }


def _reconciliation_content_form(title: str, identity: EventIdentity) -> str:
    if re.search(
        r"\b(?:event|keynote)\b.{0,18}\b(?:countdown|preview|what to expect)\b|"
        r"(?:发布会|活动).{0,14}(?:倒计时|前瞻|新品展望)",
        title,
    ):
        return "event_preview"
    if identity.content_form != "news":
        return identity.content_form
    if re.search(
        r"\beverything\b.{0,48}\bexpected to (?:announce|launch|release|unveil)\b|"
        r"\b(?:features?|upgrades?|changes?)\b.{0,45}\b(?:rumored|reported) for years\b|"
        r"(?:全部|所有|新品).{0,16}(?:汇总|盘点)|(?:传闻|爆料).{0,12}(?:汇总|盘点)|"
        r"(?:结合|根据).{0,36}(?:多方|此前).{0,24}(?:汇总|总结|盘点)|"
        r"(?:汇总|总结|盘点).{0,14}(?:核心亮点|已有信息|此前传闻|爆料)",
        title,
    ):
        return "roundup"
    return "news"


def _legal_action_stage_text(text: str) -> str:
    if (
        _contains(
            text,
            "court revives",
            "court revived",
            "appeals court revives",
            "appeals court restored",
            "case can proceed",
            "case may proceed",
            "lawsuit can proceed",
            "lawsuit may proceed",
            "恢复审理",
            "恢复诉讼",
            "案件继续推进",
            "诉讼继续推进",
            "推翻驳回裁定",
        )
        or re.search(
            r"\b(?:court|appeals court|panel)\b.{0,45}"
            r"\b(?:reviv(?:es|ed)|restore(?:s|d)|reinstate(?:s|d)|resurrect(?:s|ed))\b"
            r".{0,45}\b(?:case|lawsuit|claim)\b",
            text,
            re.I,
        )
    ):
        return "case-revival"
    if (
        _contains(
            text,
            "opposition to the motion to dismiss",
            "asks the court to deny",
            "asked the court to deny",
            "should be denied",
            "hits back at",
            "fires back at",
        )
        or re.search(
            r"\b(?:opposition to|denying)\b.{0,55}"
            r"\b(?:dismissal|motion to dismiss|request for dismissal)\b",
            text,
        )
        or re.search(
            r"(?:反驳|反对|要求法院拒绝|要求法院驳回).{0,28}"
            r"(?:驳回诉讼|撤诉|驳回动议|驳回申请|撤销诉讼)",
            text,
        )
    ):
        return "dismissal-opposition"
    if _contains(
        text,
        "motion to dismiss",
        "moves to dismiss",
        "asks the judge to dismiss",
        "asks judge to dismiss",
        "to be dismissed",
        "wants apple's lawsuit dismissed",
        "wants the lawsuit dismissed",
        "motion filed yesterday to dismiss",
        "asked a federal judge to toss out",
        "seeks dismissal",
        "request to dismiss",
        "申请驳回",
        "请求驳回",
        "要求驳回",
    ) or re.search(r"(?:请求|要求|申请).{0,12}法官.{0,12}驳回", text):
        return "dismissal-request"
    if (
        _contains(text, "discovery", "response deadline", "filing deadline", "答辩期限", "取证")
        and _contains(text, "delay", "delays", "delayed", "extend", "extended", "延期", "延长")
    ):
        return "case-schedule"
    if _contains(text, "delay", "delays", "delayed", "delaying", "拖延", "延误") and _contains(
        text,
        "lawsuit",
        "legal battle",
        "case",
        "诉讼",
        "法律纠纷",
        "案件",
        "法律战",
    ):
        return "case-schedule"
    if _contains(text, "extension", "extended", "延期", "延长") and _contains(
        text, "lawsuit", "legal battle", "case", "诉讼", "法律纠纷", "案件"
    ):
        return "case-schedule"
    if _contains(
        text,
        "preliminary injunction",
        "temporary injunction",
        "seeks an injunction",
        "moves for injunction",
        "demands injunction",
        "临时禁令",
        "初步禁令",
        "申请禁令",
        "请求禁令",
    ):
        return "injunction-request"
    if (
        _contains(text, "court ruled", "judge ruled", "法官驳回", "法院裁定", "缩小诉讼")
        or re.search(r"\b(?:court|judge)\b.{0,28}\b(?:dismissed|narrowed|stricken)\b", text)
    ):
        return "court-ruling"
    if _contains(
        text,
        "settlement talks",
        "settlement negotiation",
        "settle the lawsuit",
        "和解谈判",
        "讨论和解",
    ):
        return "settlement-talks"
    if _contains(
        text,
        "public rebuttal",
        "rebuttal",
        "rebuts",
        "refutes",
        "published a response",
        "posts rebuttal",
        "responded to",
        "responds to",
        "response to",
        "no evidence supporting",
        "court of public opinion",
        "公开回应",
        "发布回应",
        "否认指控",
        "反驳",
        "回应苹果",
    ):
        return "public-response"
    if re.search(r"回应.{0,24}(?:诉讼|纠纷|案件|指控|苹果)", text):
        return "public-response"
    return ""


def _legal_action_stage(title: str, lead: str) -> str:
    return _legal_action_stage_text(f"{title}. {lead}")


def _legal_title_parties(title: str) -> set[str]:
    parties = set()
    for match in re.finditer(
        r"\b(?:against|with|in)\s+([a-z][a-z0-9.+-]+(?:\s+[a-z][a-z0-9.+-]+){0,2})['’]s\s+"
        r"(?:case|lawsuit|response)\b",
        title,
    ):
        party = re.sub(r"\s+", "-", match.group(1)).strip("-")
        if party not in {"apple", "the", "its"}:
            parties.add(party)
    leading = re.match(r"^([a-z][a-z0-9.+-]+(?:\s+[a-z][a-z0-9.+-]+){0,2})['’]s\b", title)
    if leading:
        party = re.sub(r"\s+", "-", leading.group(1))
        if party not in {"apple", "the", "its"}:
            parties.add(party)
    return parties


def _component_values(identity: EventIdentity, prefix: str) -> set[str]:
    return {
        component.split(":", 1)[1]
        for component in identity.title_components
        if component.startswith(prefix)
    }


def _content_screening_subject(title: str, lead: str) -> str:
    raw = f"{title}. {lead}"
    action_named = re.search(
        r"\b([A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?(?:\s+[A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?){0,5})\s+"
        r"(?:is\s+going\s+to\s+(?:the\s+)?movies|will\s+be\s+shown|is\s+coming\s+to\s+(?:the\s+)?cinema)\b",
        raw,
    )
    if action_named:
        value = _normalized(action_named.group(1)).replace("'", "")
        return re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    quoted = re.search(r"[\"“]([^\"”]{3,70})[\"”]", raw)
    if not quoted:
        quoted = re.search(
            r"['‘]([A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?(?:\s+[A-Z][A-Za-z0-9]+(?:['’][A-Za-z]+)?){0,8})['’]",
            raw,
        )
    if quoted:
        value = _normalized(quoted.group(1)).replace("'", "")
        return re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    named = re.search(
        r"\b(?:show|screen|screening(?:s)?(?:\s+for)?|series)\s+"
        r"([A-Z][A-Za-z0-9'’ -]{2,60}?)(?=\s+(?:at|in|on|for)\b|[.,;])",
        raw,
    )
    if named:
        value = _normalized(named.group(1)).replace("'", "")
        return re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return ""


def _product_separation_keys(identity: EventIdentity) -> set[str]:
    products = set(identity.title_products)
    hardware_specific = bool(
        any(
            component.startswith((
                "iphone-model:",
                "iphone-family:",
                "macbook-model:",
                "display-size:",
            ))
            for component in identity.title_components
        )
        or identity.title_components
        & {"largest-iphone-display", "oled-display", "camera-system"}
    )
    if not hardware_specific:
        return set()
    families = set()
    if products & {"iphone", "foldable-iphone"}:
        families.add("iphone")
    if products & {"mac", "macbook", "imac", "mac-mini", "mac-studio", "mac-pro"}:
        families.add("mac")
    for product in products & {"ipad", "ipad-air", "ipad-mini", "ipad-pro", "apple-watch", "airpods", "apple-tv", "vision-pro"}:
        families.add(product)
    return {f"product-family:{family}" for family in families}


def _predicate_separation_keys(identity: EventIdentity) -> set[str]:
    """Return coarse title-led predicate classes for rejecting mixed seed groups.

    These classes describe what the article asserts about its subject. They do
    not merge articles on their own; they only keep an accepted legacy seed
    from treating two explicit, incompatible assertions as one event.
    """
    products = set(identity.title_products)
    components = set(identity.title_components)
    assertion_components = set(identity.components)
    actions = set(identity.title_actions)
    keys: set[str] = set()
    software_products = {
        "app-store",
        "apple-books",
        "apple-intelligence",
        "apple-music",
        "apple-sports",
        "apple-tv",
        "apple-wallet",
        "carplay",
        "icloud",
        "ios",
        "ipados",
        "macos",
        "safari",
        "siri",
        "tvos",
        "visionos",
        "watchos",
        "xcode",
    }
    hardware_products = {
        "airpods",
        "apple-tv-hardware",
        "apple-watch",
        "foldable-iphone",
        "imac",
        "ipad",
        "ipad-air",
        "ipad-mini",
        "ipad-pro",
        "iphone",
        "mac",
        "mac-mini",
        "mac-pro",
        "mac-studio",
        "macbook",
        "vision-pro",
    }
    if products & software_products and "feature-change" in actions:
        keys.add("predicate:platform-feature-change")
    if components & {"display-panel", "oled-display"}:
        keys.add("predicate:hardware-component-development")
    if (
        products & hardware_products
        and (
            components
            & {
                "hardware-product-roadmap",
                "product-release-delay",
                "roadmap-projection",
            }
            or actions & {"delay-roadmap", "project-cancellation"}
        )
    ):
        keys.add("predicate:hardware-product-roadmap")
    if "component-cost-analysis" in assertion_components:
        keys.add("predicate:hardware-component-cost")
    if "price-change" in actions:
        keys.add("predicate:retail-price-change")
    if actions & {"claim-denial", "project-cancellation"}:
        keys.add("predicate:claim-status")
    if any(
        component.startswith("component-supplier-sourcing:")
        for component in assertion_components
    ) or "component-supplier-sourcing" in assertion_components:
        keys.add("predicate:component-supplier-sourcing")
    if "hardware-shipment-plan-change" in assertion_components:
        keys.add("predicate:hardware-shipment-plan-change")
    elif "hardware-market-performance" in components:
        keys.add("predicate:hardware-market-performance")
    return keys


def _title_predicate_separation_keys(title: str) -> set[str]:
    """Extract concrete title predicates that generic product actions miss."""
    title_text = _canonical_title(title)
    keys: set[str] = set()
    if _apple_event_invitation_interpretation_context(title):
        keys.add("primary-claim-predicate:event-invitation-feature-interpretation")
    if re.search(
        r"\b(?:packaging box|retail packaging|retail box|product box)\b|"
        r"(?:包装盒|零售包装盒|产品包装盒)",
        title_text,
    ):
        keys.add("primary-claim-predicate:retail-packaging-disclosure")
    if re.search(
        r"\b(?:colors?|finishes?|colourways?)\b.{0,24}"
        r"\b(?:revealed|unveiled|leaked|lineup)\b|"
        r"(?:配色|颜色|外观色).{0,20}(?:揭晓|曝光|流出|阵容|新增)",
        title_text,
    ):
        keys.add("primary-claim-predicate:finish-lineup-disclosure")
    if re.search(
        r"\b(?:apple\s+)?(?:event|keynote)\b.{0,70}"
        r"(?:date|time|schedule|announce|announcement|take place)|"
        r"(?:苹果)?(?:发布会|活动).{0,55}(?:日期|时间|日程|官宣|举行)",
        title_text,
        re.I,
    ):
        keys.add("primary-claim-predicate:event-schedule-announcement")
    if re.search(
        r"\b(?:price|prices|pricing)\b.{0,55}"
        r"(?:rise|increase|higher|forecast|estimate|might|may|could|guess)|"
        r"(?:涨价|提价|价格|售价).{0,45}(?:预计|预估|预测|可能|或|上调|上涨|提高)",
        title_text,
        re.I,
    ):
        keys.add("primary-claim-predicate:retail-price-forecast")
    if re.search(
        r"\b(?:features?|capabilities)\b.{0,36}\b(?:won't|will not|may not|missing|lack)\b|"
        r"\b(?:won't|will not|may not|missing|lack)\b.{0,36}\b(?:features?|capabilities)\b|"
        r"(?:缺少|不会有|不具备|无缘).{0,30}(?:功能|特性)|"
        r"(?:功能|特性).{0,30}(?:缺少|不会有|不具备|无缘)",
        title_text,
        re.I,
    ):
        keys.add("primary-claim-predicate:feature-absence-analysis")
    return keys


def _title_proves_first_party_subject(title: str, identity: EventIdentity) -> bool:
    """Require explicit title ownership before promoting an initially weak item."""
    return identity.action_owner == "apple"


def _weak_topic_separation_key(title: str) -> str:
    if _contains(title, "dram", "ram", "memory", "nand", "内存", "存储", "闪存"):
        return "weak-topic:memory-market"
    if _contains(title, "2nm", "3nm", "chip", "soc", "semiconductor", "芯片", "制程", "半导体"):
        return "weak-topic:semiconductor-roadmap"
    if _contains(title, "app", "application", "应用", "微信"):
        return "weak-topic:third-party-app"
    if _contains(title, "ai model", "llm", "大模型", "ai 模型"):
        return "weak-topic:third-party-ai-model"
    return ""


def _changed_object_patterns() -> dict[str, tuple[str, str]]:
    """Return the existing bilingual changed-object classifier patterns."""
    return {
        "case-material": (
            r"\b(?:ceramic|titanium|aluminum|aluminium|stainless steel|case material|housing material)\b",
            r"(?:陶瓷|钛金属|钛合金|铝合金|不锈钢|表壳材质|机身材质|外壳材质)",
        ),
        "processor": (
            r"\b(?:processor|chipset|soc|s\d{1,2}\s+chip|m\d(?:\s+(?:pro|max|ultra))?\s+chip)\b",
            r"(?:处理器|芯片|soc)",
        ),
        "display": (
            r"\b(?:display panel|oled display|oled panel|mini-led|microled|refresh rate)\b",
            r"(?:屏幕|显示屏|面板|刷新率)",
        ),
        "camera": (
            r"\b(?:camera|sensor|aperture|telephoto|lens)\b",
            r"(?:相机|摄像头|传感器|光圈|长焦|镜头|主摄|超广角|双摄|单摄|影像)",
        ),
        "battery": (r"\b(?:battery|charging|mah)\b", r"(?:电池|续航|充电|毫安时)"),
        "modem": (r"\b(?:modem|baseband|cellular chip)\b", r"(?:调制解调器|基带|蜂窝芯片)"),
        "memory-storage": (r"\b(?:ram|memory|dram|nand|storage)\b", r"(?:内存|存储|闪存)"),
        "thermal-design": (
            r"\b(?:vapor chamber|thermal design|cooling system|heat spreader)\b",
            r"(?:均热板|散热设计|散热系统)",
        ),
        "retail-packaging": (
            r"\b(?:packaging box|retail packaging|retail box|product box)\b",
            r"(?:包装盒|零售包装盒|产品包装盒)",
        ),
        "finish-color": (
            r"\b(?:color|colors|colour|colours|finish|finishes|colourway|colourways)\b",
            r"(?:配色|颜色|机身色|外观色)",
        ),
    }


def _changed_object_separation_keys(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> set[str]:
    """Extract the concrete object changed by a product report.

    A shared product family is not an event identity. Only the headline and
    first lead sentence are used, preventing background specification lists
    from creating artificial conflicts.
    """
    if not identity.title_products:
        return set()
    scope = f"{_normalized(title)}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    return {
        f"changed-object:{name}"
        for name, alternatives in _changed_object_patterns().items()
        if any(re.search(pattern, scope, re.I) for pattern in alternatives)
    }


def _primary_title_changed_object(title: str) -> str:
    """Return the first concrete changed object named by the headline."""
    title_text = _normalized(title)
    matches: list[tuple[int, str]] = []
    for name, alternatives in _changed_object_patterns().items():
        for pattern in alternatives:
            match = re.search(pattern, title_text, re.I)
            if match:
                matches.append((match.start(), name))
                break
    for pattern in (r"\bdisplays?\b", r"显示器"):
        match = re.search(pattern, title_text, re.I)
        if match:
            matches.append((match.start(), "display"))
            break
    return min(matches)[1] if matches else ""


def _primary_title_changed_object_measure(title: str) -> tuple[str, str]:
    """Return a headline's first changed object and adjacent count, if present."""
    title_text = _normalized(title)
    object_name = _primary_title_changed_object(title_text)
    if not object_name:
        return "", ""
    patterns = list(_changed_object_patterns()[object_name])
    if object_name == "display":
        patterns.extend((r"\bdisplays?\b", r"显示器"))
    object_matches = [
        match
        for pattern in patterns
        for match in [re.search(pattern, title_text, re.I)]
        if match
    ]
    if not object_matches:
        return "", ""
    object_match = min(object_matches, key=lambda match: match.start())
    prefix = title_text[max(0, object_match.start() - 14) : object_match.start()]
    count_match = re.search(
        r"(?:^|[^a-z0-9])"
        r"(?P<count>\d{1,3}|one|two|three|four|five|six|seven|eight|"
        r"一|二|两|三|四|五|六|七|八)\s*(?:[-－]|台|个|颗|款)?\s*$",
        prefix,
        re.I,
    )
    if not count_match:
        return "", ""
    count_map = {
        "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8",
        "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8",
    }
    raw_count = count_match.group("count").lower()
    return object_name, count_map.get(raw_count, raw_count)


def _title_product_period_keys(title: str, identity: EventIdentity) -> set[str]:
    """Project a title-level product roadmap period without making it a merge key."""
    title_text = _normalized(title)
    years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", title_text))
    if len(years) != 1 or not identity.title_products:
        return set()
    year = next(iter(years))
    season = ""
    if re.search(r"\bspring\b|春季", title_text):
        season = "spring"
    elif re.search(r"\b(?:fall|autumn)\b|秋季", title_text):
        season = "fall"
    elif re.search(r"\b(?:first half|h1|1h)\b|上半年", title_text):
        season = "h1"
    elif re.search(r"\b(?:second half|h2|2h)\b|下半年", title_text):
        season = "h2"
    period = f"{year}-{season}" if season else year
    return {
        f"product-period:{product}:{period}"
        for product in _primary_title_subjects(identity)
        if product in identity.title_products
    }


def _first_party_content_claim(
    title: str,
    lead: str,
    identity: EventIdentity,
    evidence: str = "",
) -> tuple[str, str] | None:
    """Return a named first-party content subject and its concrete action."""
    title_text = _canonical_title(title)
    owned_film_title = bool(re.search(
        r"\bapple's\s+(?:new\s+)?(?:film|movie|documentary|series)\b|"
        r"苹果.{0,8}(?:电影|影片|纪录片|剧集)", title_text,
    ))
    if "apple-tv" not in identity.title_products and not owned_film_title:
        return None
    headline_claim = _headline_content_claim(title, lead)
    if headline_claim:
        return headline_claim
    rights_scope = f"{title}. {lead[:700]}"
    rights_action = bool(
        re.search(
            r"\b(?:apple tv\s+)?(?:acquires?|acquired|buys?|bought|(?:has|have) picked up|picks? up|"
            r"secures?)\b.{0,90}\b(?:rights?|streaming|series|show|film|movie|comedy)\b|"
            r"\b(?:worldwide|global)(?:\s+streaming)?\s+rights?\b|"
            r"(?:apple tv|苹果 tv).{0,36}(?:买下|购得|收购|取得|拿下).{0,36}"
            r"(?:版权|播映权|流媒体权利|剧集|影片|电影)",
            rights_scope,
            re.I,
        )
    )
    if rights_action:
        subject_candidates = [
            candidate.strip()
            for candidate in _quoted_subjects(rights_scope)
            if candidate.strip().lower() not in {"apple tv", "apple tv+"}
        ]
        for pattern in (
            r"(?:worldwide|global)(?:\s+streaming)?\s+rights?\s+to\s+"
            r"(?:the\s+)?(?:(?:bbc|british)\s+)?"
            r"(?:(?:comedy|series|drama|film|movie|show)\s+)?"
            r"([A-Z][A-Za-z0-9'’:&.-]*(?:\s+[A-Z][A-Za-z0-9'’:&.-]*){0,7})",
            r"\b(?:comedy\s+series|comedy|series|drama|film|movie|show)\s*,?\s*"
            r"([A-Z][A-Za-z0-9'’:&.-]*(?:\s+[A-Z][A-Za-z0-9'’:&.-]*){0,7})",
        ):
            match = re.search(pattern, rights_scope)
            if match:
                subject_candidates.append(match.group(1).strip())
        if subject_candidates:
            ignored_subjects = {
                "apple tv",
                "bbc",
                "british",
                "global streaming",
                "worldwide rights",
            }
            raw_subject = next(
                (
                    candidate
                    for candidate in subject_candidates
                    if _normalized(candidate) not in ignored_subjects
                ),
                "",
            )
            subject = re.sub(r"[^a-z0-9]+", "-", raw_subject.lower()).strip("-")
            if subject:
                return subject, "rights-acquisition"
    match = re.match(
        r"^apple tv\s+['\"](?P<subject>[^'\"]{2,90})['\"]\s+"
        r"(?P<action>release|return|renewal|trailer release)\b",
        title_text,
    )
    if not match:
        match = re.match(
            r"^(?:(?:emmy|award)[- ]winning\s+)?(?P<subject>[a-z0-9][a-z0-9 '&:.-]{1,80}?)\s+"
            r"(?P<action>returns?|premieres?|debuts?|releases?)\s+(?:to|on)\s+apple tv\b",
            title_text,
        )
    if match:
        raw_subject = re.sub(
            r"(?:['’]s\s+)?(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th))\s+season$",
            "",
            match.group("subject"),
            flags=re.I,
        ).strip()
        raw_action = match.group("action")
        action = (
            "return"
            if raw_action.startswith("return")
            else "release"
            if raw_action.startswith(("premier", "debut", "release"))
            else raw_action.replace(" ", "-")
        )
    else:
        content_scope = _normalized(f"{lead[:900]} {evidence[:1200]}")
        title_is_content_story = bool(
            re.search(
                r"\b(?:series|drama|thriller|film|movie|documentary|show|season)\b|"
                r"(?:剧集|剧|惊悚片|电影|影片|纪录片|节目|新季)",
                title_text,
            )
        )
        first_party_content_action = bool(
            _contains(
                content_scope,
                "according to apple tv",
                "apple tv announced",
                "apple tv reveals",
                "apple tv revealed",
                "apple tv orders",
                "apple tv ordered",
                "apple tv 宣布",
                "苹果 tv 宣布",
            )
            and _contains(
                content_scope,
                "premiere",
                "premieres",
                "debut",
                "debuts",
                "global debut",
                "ordered",
                "orders",
                "首播",
                "上线",
                "预订",
            )
            or re.search(
                r"\bapple tv\b.{0,48}\b(?:announces?|reveals?|unveils?|orders?)\b|"
                r"\bapple tv\b.{0,48}(?:宣布|公布|揭晓|预订)",
                title_text,
            )
        )
        if not (title_is_content_story and first_party_content_action):
            return None
        quoted_subjects = [
            candidate.strip()
            for candidate in _quoted_subjects(f"{lead} {evidence}")
            if candidate.strip().lower() not in {"apple tv", "apple tv+"}
        ]
        if not quoted_subjects:
            return None
        raw_subject = quoted_subjects[0]
        action = "release"

    subject = re.sub(r"[^a-z0-9]+", "-", raw_subject.lower()).strip("-")
    if not subject:
        return None
    return subject, action


def _legal_case_key(identity: EventIdentity) -> str:
    topics = set(identity.case_topics)
    topic_terms = {
        token
        for topic in topics
        for token in topic.split("-")
    }
    counterparties = {
        party
        for party in identity.counterparties
        if party not in topic_terms and party not in {"apple", "secrets", "lawsuit"}
    }
    parts = sorted(counterparties | topics)
    if not topics and identity.products:
        parts = sorted(identity.products)
    return ":".join(parts)


def _retrospective_explainer_without_new_action(title: str, text: str) -> bool:
    title_text = _canonical_title(title)
    return bool(
        re.match(r"^(?:how|why)\s+apple\b", title_text)
        and re.search(
            r"\b(?:last\s+(?:week|month|year)|previously|earlier|already)\b|"
            r"(?:上周|上月|去年|此前|早前|已经)",
            text,
        )
        and re.search(
            r"\b(?:had|has|have)\s+(?:already\s+)?appeared\s+in\s+previous\b|"
            r"\b(?:previously reported|already reported|no new reporting|"
            r"not new information)\b|"
            r"\b(?:all|most)\b.{0,80}\b(?:references?|identifiers?|assets?)\b"
            r".{0,80}\b(?:appeared|reported|disclosed)\b.{0,30}\bprevious\b|"
            r"(?:此前已经|早已).{0,40}(?:出现|报道|披露)|"
            r"(?:没有|并无)新增(?:消息|信息|动作)",
            text,
        )
    )


def _apple_event_schedule_title(title: str) -> bool:
    title_text = _canonical_title(title)
    return bool(
        re.search(r"\b(?:apple|iphone)\s+(?:event|keynote)\b", title_text)
        or re.search(
            r"\bapple\b.{0,70}\b(?:announces?|unveils?|confirms?)\b"
            r".{0,70}\b(?:event|keynote)\b|"
            r"\bapple\b.{0,70}\b(?:event|keynote)\b.{0,50}"
            r"\b(?:announces?|confirmed?|scheduled?)\b",
            title_text,
        )
        or re.search(
            r"苹果(?:\s*20\d{2})?\s*(?:春季|秋季)?\s*(?:新品|iphone)?\s*发布会|"
            r"苹果.{0,24}特别活动",
            title_text,
        )
    )


def _apple_event_campaign_title_context(title: str) -> bool:
    """Return true when the headline itself owns a current Apple event action."""
    title_text = _canonical_title(title)
    explicit_campaign_asset = bool(
        re.search(
            r"\b(?:event\s+)?(?:tagline|slogan|theme|hashtag|hashmoji)\b|"
            r"\bcustom\s+apple\s+logo\b|"
            r"(?:发布会)?(?:标语|口号|主题|话题标签|哈希表情|定制苹果标志)",
            title_text,
        )
    )
    explicit_schedule = bool(
        re.search(
            r"\b(?:event|keynote)\b|发布会|苹果.{0,24}特别活动",
            title_text,
        )
        and re.search(
            r"\b(?:announc(?:e|es|ed|ement)|confirm(?:s|ed)?|schedule(?:s|d)?|"
            r"sets?\s+(?:the\s+)?date|dated?\s+for)\b|"
            r"(?:官宣|确认|定档|宣布.{0,12}(?:日期|时间)|公布.{0,12}(?:日期|时间))",
            title_text,
        )
    )
    return explicit_campaign_asset or explicit_schedule


def _apple_event_invitation_interpretation_context(title: str, lead: str = "") -> bool:
    """Identify media interpretation of event artwork, not Apple's event action."""
    title_text = _canonical_title(title)
    invitation_subject = bool(
        re.search(
            r"\b(?:apple\s+)?(?:event\s+)?(?:invite|invitation|logo|artwork|graphic)\b|"
            r"(?:苹果)?(?:发布会|活动)?(?:邀请函|标志|logo|图案|视觉)",
            title_text,
            re.I,
        )
    )
    interpretation_action = bool(
        re.search(
            r"\b(?:hints?|suggests?|teases?|clues?|interprets?|reads?\s+into)\b|"
            r"(?:暗示|解读|玄机|剧透|线索|指向|卖点)",
            title_text,
            re.I,
        )
    )
    product_feature = bool(
        re.search(
            r"\b(?:iphone|ipad|mac|apple\s+watch|airpods)\b|"
            r"(?:苹果)?(?:手机|平板|电脑|手表|耳机)|(?:光圈|相机|配色|颜色)",
            f"{title_text} {_short_lead_scope(lead, sentences=1, limit=360)}",
            re.I,
        )
    )
    return invitation_subject and interpretation_action and product_feature


def _apple_event_invitation_interpretation_key(
    title: str,
    lead: str,
    identity: EventIdentity,
    changed_objects: Iterable[str],
) -> str:
    if not _apple_event_invitation_interpretation_context(title, lead):
        return ""
    products = sorted(
        identity.title_products
        & {
            "airpods",
            "apple-watch",
            "foldable-iphone",
            "ipad",
            "iphone",
            "mac",
            "macbook",
        }
    )
    objects = sorted(
        value.removeprefix("changed-object:")
        for value in changed_objects
        if value.startswith("changed-object:")
    )
    if not products:
        return ""
    count_scope = f"{_normalized(title)} {_short_lead_scope(lead, sentences=1, limit=360)}"
    count_aliases = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "一": "1",
        "两": "2",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
    }
    count_match = re.search(
        r"\b(one|two|three|four|five|[1-5])\b"
        r"(?:\s+[a-z0-9-]+){0,6}\s+"
        r"(?:features?|clues?|details?|selling\s+points?)\b|"
        r"([一二两三四五1-5])\s*(?:大|项|个)?(?:卖点|功能|特性|细节|线索)",
        count_scope,
        re.I,
    )
    if count_match:
        count_value = next(value for value in count_match.groups() if value)
        count_value = count_aliases.get(count_value.lower(), count_value)
        qualifier = f"count-{count_value}"
    elif objects:
        qualifier = "+".join(objects)
    else:
        return ""
    return (
        "primary-claim:apple-event-invitation:"
        f"{'+'.join(products)}:feature-interpretation:{qualifier}"
    )


def _apple_event_occurrence_keys(title: str, lead: str) -> set[str]:
    """Project timezone-tolerant calendar anchors for one announced event.

    Regional reports can name the same keynote as September 9 or September 10.
    Adjacent calendar aliases are safe here because the title must itself be an
    event announcement or a campaign asset published in the same 24-hour run.
    """
    if (
        not _apple_event_campaign_title_context(title)
        or _apple_event_invitation_interpretation_context(title, lead)
    ):
        return set()
    scope = _normalized(f"{title} {lead[:700]}")
    month_days: set[tuple[int, int]] = set()
    month_numbers = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    english_date = (
        r"(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?"
    )
    for match in re.finditer(
        rf"(?:\b(?:event|keynote)\b.{{0,70}}\b{english_date}\b|"
        rf"\b{english_date}\b.{{0,70}}\b(?:event|keynote)\b)",
        scope,
    ):
        values = [value for value in match.groups() if value]
        month_days.add((month_numbers[values[0]], int(values[1])))
    chinese_date = r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    for match in re.finditer(
        rf"(?:(?:发布会|特别活动).{{0,70}}{chinese_date}|"
        rf"{chinese_date}.{{0,70}}(?:发布会|特别活动))",
        scope,
    ):
        values = [value for value in match.groups() if value]
        month_days.add((int(values[0]), int(values[1])))

    keys: set[str] = set()
    for month, day in month_days:
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        keys.add(f"apple-event-occurrence:{month:02d}-{day:02d}")
        if day > 1:
            keys.add(f"apple-event-occurrence:{month:02d}-{day - 1:02d}")
        if day < 31:
            keys.add(f"apple-event-occurrence:{month:02d}-{day + 1:02d}")
    return keys


def _apple_event_campaign_key(title: str, lead: str) -> str:
    """Return a campaign key shared by an event announcement and its assets.

    Product overlap is deliberately insufficient. A campaign must expose a
    reusable name or tagline in an event announcement, localized slogan,
    hashtag, or hashmoji context. This keeps purchase surveys and product
    rumors outside the campaign while allowing source-specific follow-ups to
    contribute facts to the same announced event.
    """
    if (
        not _apple_event_campaign_title_context(title)
        or _apple_event_invitation_interpretation_context(title, lead)
    ):
        return ""
    raw_scope = " ".join(part for part in (title, lead[:700]) if part)
    scope = _normalized(raw_scope)
    campaign_context = bool(
        re.search(r"\b(?:apple\s+)?(?:event|keynote)\b|(?:苹果)?发布会", scope)
        or re.search(r"\b(?:hashtag|hashmoji)\b|(?:话题标签|哈希表情)", scope)
    )
    if not campaign_context:
        return ""

    candidates: list[str] = []
    campaign_patterns = (
        (r"[‘“\"]([^’”\"]{4,60})[’”\"]", title),
        (r":\s*'([^']{4,60})'\s*$", title),
        (r"\b(?:event|keynote)\s*:\s*['\"]?([a-z][a-z0-9 &-]{3,48})", title),
        (r"\bapple(?:'s)?\s+([a-z][a-z0-9 &-]{3,48}?)\s+hashmoji\b", title),
        (
            r"\b(?:localized?|localised?)\s+(?:the\s+)?([a-z][a-z0-9 &-]{3,48}?)\s+"
            r"(?:event\s+)?(?:tagline|slogan)\b",
            raw_scope,
        ),
        (
            r"\b(?:with|under|using|featuring)?\s*(?:the\s+)?(?:event\s+)?"
            r"(?:tagline|slogan)\b[^‘“\"']{0,48}[‘“\"']([^’”\"']{4,60})[’”\"']",
            raw_scope,
        ),
    )
    for pattern, value in campaign_patterns:
        candidates.extend(match.group(1) for match in re.finditer(pattern, value, re.I))

    ignored = {
        "apple",
        "apple event",
        "event",
        "iphone event",
        "iphone ultra",
        "keynote",
    }
    for candidate in candidates:
        label = _normalized(candidate).strip(" '\"-:,.!?，。！？：")
        label = re.sub(r"^(?:the\s+|apple(?:'s)?\s+)", "", label)
        words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", label)
        if not (2 <= len(words) <= 8):
            continue
        if label in ignored or _contains(
            label,
            "iphone",
            "ipad",
            "macbook",
            "foldable",
            "apple watch",
        ):
            continue
        slug = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "-", label).strip("-")
        if slug:
            return f"apple-event-campaign:{slug}"
    return ""


def _editorial_or_third_party_claim_reason(
    title: str,
    text: str,
    identity: EventIdentity,
) -> str:
    """Resolve headline ownership before Apple product terms can promote it."""
    title_text = _canonical_title(title)
    if quantified_apple_company_performance_subject(title, text):
        return ""
    if _retrospective_explainer_without_new_action(title_text, text):
        return "analysis or explanation without a new title-led Apple action"
    tutorial_title = bool(
        re.match(
            r"^(?:(?:\d+|ten)\s+)?(?:ways?\s+to|how\s+to|when\s+to|"
            r"tips?\s+(?:to|for)|guide\s+to)\b|^(?:如何|怎么|怎样|何时|\d+\s*个?技巧)",
            title_text,
        )
    )
    if tutorial_title:
        return "editorial tutorial without a new Apple action"
    if identity.content_form == "tutorial":
        return "editorial tutorial or settings advice without a new Apple action"
    if identity.content_form == "user_anecdote":
        return "editorial single-user workaround without a new Apple action"
    product_comparison = bool(
        re.search(r"\bvs\.?\b|\bversus\b|(?:对比|横评)", title_text)
        and re.search(
            r"\b(?:iphone|ipad|mac(?:book| mini| studio| pro)?|airpods|apple watch)\b|"
            r"(?:苹果)?(?:手机|平板|电脑|耳机|手表)",
            title_text,
        )
        and not re.search(
            r"\b(?:lawsuit|court|judge|settlement|sues?|filings?|report|study|"
            r"leaks?|reveals?|discloses?|regulatory)\b|"
            r"(?:诉讼|法院|法官|和解|起诉|文件|报告|研究|泄露|曝光|披露|监管)",
            title_text,
        )
    )
    if product_comparison:
        return "editorial product comparison or buying advice without a new Apple action"
    reported_event_schedule = bool(
        _apple_event_schedule_title(title_text)
        and re.search(
            r"\b(?:september|october)\s+\d{1,2}\b|"
            r"\b\d{1,2}/\d{1,2}\b|"
            r"\d{1,2}\s*月\s*\d{1,2}\s*日",
            text,
        )
        and re.search(
            r"\b(?:according to|reports?|reported|published|claims?|sources? say|bloomberg|gurman|"
            r"leaker|leaks?|rumou?rs?)\b|"
            r"(?:据.{0,20}(?:报道|消息|透露)|报道称|报道分析|消息称|爆料|"
            r"多方消息|多方爆料|外媒分析|发文.{0,12}分析)",
            text,
        )
    )
    if identity.content_form == "analysis" and not reported_event_schedule and not re.search(
        r"\b(?:announces?|launches?|releases?|introduces?|adds?|expands?|changes?|"
        r"updates?|raises?|lowers?|opens?|closes?|acquires?|sues?|settles?|"
        r"is\s+(?:launching|releasing|adding|expanding|changing|updating|testing)|"
        r"will\s+(?:launch|release|add|expand|change|update))\b|"
        r"(?:宣布|推出|发布|新增|扩展|调整|更新|涨价|降价|开放|关闭|收购|起诉|和解)",
        title_text,
    ):
        return "analysis or explanation without a new title-led Apple action"
    routine_refurb_roundup = bool(
        _contains(title_text, "refurb store", "refurbished store", "官翻", "翻新商店")
        and _contains(title_text, "offers", "deals", "discount", "save", "more", "优惠", "折扣", "降价")
        and not _contains(
            title_text,
            "adds",
            "expands",
            "launches",
            "new configurations",
            "新增",
            "扩展",
            "上架新配置",
        )
    )
    if routine_refurb_roundup:
        return "editorial deal roundup without a new Apple action"
    anniversary_recap = bool(
        re.search(
            r"\bturns?\s+(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b|"
            r"\b(?:celebrates?|marks?)\s+(?:its\s+)?\d{1,3}(?:st|nd|rd|th)?\s+anniversary\b|"
            r"(?:迎来|问世|发布|诞生|庆祝).{0,12}\d{1,3}\s*周年",
            title_text,
        )
    )
    title_current_action = bool(
        re.search(
            r"\b(?:announces?|launches?|releases?|introduces?|adds?|expands?|"
            r"opens?)\b|(?:宣布|推出|发布|新增|扩展|开放)",
            title_text,
        )
    )
    if anniversary_recap and not title_current_action:
        return "anniversary or retrospective recap without a new Apple action"
    comparison_to_apple = bool(
        re.search(
            r"\b(?:catch(?:es|ing)?\s+up(?:\s+to|\s+with)?|"
            r"close[sd]?\s+the\s+gap\s+with|outpace[sd]?|outperform[sd]?|"
            r"beats?\s+out|rival[sd]?|versus|vs\.?)\s+"
            r"(?:apple|iphone|ipad|mac(?:book|os)?|safari|watchos|tvos|visionos)\b|"
            r"(?:追赶|赶超|媲美|对标|对比|挑战|超越)"
            r"[^，。,:;；]{0,14}(?:苹果|iphone|ipad|mac|safari)|"
            r"(?:把|将)(?:苹果|iphone|ipad|mac|safari)"
            r"[^，。,:;；]{0,12}(?:甩在身后|压过|击败)|"
            r"\bleaves?\s+(?:apple|iphone|ipad|mac)\s+behind\b",
            title,
            re.I,
        )
    )
    direct_apple_title = bool(
        re.search(r"^(?:apple(?:'s|’s)?|苹果)", title_text)
        or re.search(r"^(?:how|why)\s+apple\b", title_text)
        or re.search(r"^[^:：]{2,32}[：:]\s*(?:apple(?:'s)?|苹果)", title_text)
        or re.search(
            r"^(?:report|leak|code|sources?|消息|报道|泄露|代码|文件|爆料)"
            r"[^。.!?]{0,32}(?:apple(?:'s|’s)?|苹果)",
            title_text,
        )
    )
    if (
        not direct_apple_title
        and comparison_to_apple
    ):
        return "non-Apple primary subject using Apple only as comparison context"
    primary_clause, separator, trailing_clause = title_text.partition(":")
    if not separator:
        primary_clause, separator, trailing_clause = title_text.partition("：")
    apple_subject = re.compile(
        r"\b(?:apple|iphone|ipad|mac(?:book|os)?|airpods|watchos|tvos|visionos|safari)\b|苹果",
        re.I,
    )
    attributed_report_prefix = any(
        component.startswith("report-attribution:")
        for component in identity.components
    )
    if (
        separator
        and title_current_action
        and not attributed_report_prefix
        and not apple_subject.search(primary_clause)
        and apple_subject.search(trailing_clause)
    ):
        return "non-Apple primary subject using Apple only as comparison context"

    retrospective_hands_on = bool(
        identity.content_form in {"hands_on", "review"}
        and re.search(
            r"\b(?:revisiting|revisit|looking\s+back|look\s+back|throwback|"
            r"resharing|from\s+20\d{2})\b|(?:回顾|重温|旧款|往年体验|重新分享)",
            title_text,
        )
    )
    if retrospective_hands_on:
        return f"editorial {identity.content_form.replace('_', ' ')} without a new Apple action"

    attributed_reporting = _contains(
        title_text,
        "report",
        "reported",
        "sources",
        "filing",
        "document",
        "according to",
        "报道称",
        "消息称",
        "文件显示",
        "爆料",
    )
    first_person_editorial = bool(
        re.search(
            r"\b(?:i|we)\s+(?:would|could|want|wish|would\s+like)\b.{0,70}"
            r"\b(?:change|fix|see|remove|add)\b|"
            r"\bone\s+(?:design\s+)?decision\b.{0,55}\bi\s+would\s+change\b|"
            r"(?:我|我们).{0,24}(?:希望|想要|会去|建议).{0,24}(?:改变|修改|加入|移除)",
            title_text,
        )
    )
    if first_person_editorial and not attributed_reporting:
        return "opinion or commentary without a new Apple action"

    future_recap_question = bool(
        re.search(
            r"\b(?:which|what|where)\b.{0,55}\b(?:is|are|comes?|coming)\s+next\??$|"
            r"(?:哪些|什么|哪里).{0,30}(?:下一批|接下来|即将).{0,20}[?？]?$",
            title_text,
        )
    )
    current_action = bool(
        identity.title_actions
        or _contains(
            title_text,
            "announces",
            "launches",
            "releases",
            "adds",
            "expands",
            "宣布",
            "推出",
            "发布",
            "新增",
            "扩展",
        )
    )
    if future_recap_question and not current_action:
        return "editorial future-support recap without a new Apple action"

    if (
        _contains(title_text, "archive", "档案", "存档", "历史刊物", "往期杂志")
        and _contains(text, "past", "history", "issues", "历史", "往期", "旧刊")
        and not _contains(
            title_text,
            "apple launches",
            "apple releases",
            "apple opens",
            "苹果推出",
            "苹果发布",
            "苹果开放",
        )
    ):
        return "third-party archive or retrospective without a new Apple action"

    third_party_builder = bool(
        not re.match(r"^(?:apple(?:'s)?|苹果)", title_text)
        and _contains(title_text, "ios", "ipados", "macos", "watchos", "visionos", "iphone", "ipad", "mac")
        and re.search(
            r"\b(?:developer|editor|author|user|outlet|publication)\b.{0,75}"
            r"\b(?:builds?|built|creates?|created|develops?|developed|made)\b.{0,45}"
            r"\b(?:app|tool|utility|widget|driver)\b|"
            r"(?:外媒|媒体|编辑|作者|开发者|用户|网友).{0,70}"
            r"(?:开发|制作|打造|编写).{0,45}(?:应用|工具|程序|组件|驱动)",
            title_text,
        )
    )
    if third_party_builder:
        return "third-party developer utility using an Apple platform without an Apple action"
    return ""


def _unsupported_third_party_reason(
    title: str,
    text: str,
    identity: EventIdentity,
    exact_facets: frozenset[str],
    relevance_tier: str,
    trusted_direct_action: bool,
) -> str:
    if _official_apple_store_transaction_option_action(title, text):
        return ""
    if "consumer-purchase-intent" in identity.title_components:
        return "consumer purchase-intent survey without a direct Apple action"
    if (
        identity.scope == "unknown"
        and not identity.title_products
        and not trusted_direct_action
        and not re.match(
            r"^(?:apple(?:'s)?|iphone|ipad|ios|ipados|mac(?:book|os)?|"
            r"watchos|tvos|visionos|airpods|icloud|safari|siri|carplay|"
            r"xcode|app store|beats\b|苹果)",
            _normalized(title),
        )
    ):
        return "non-Apple primary subject with Apple only in background context"
    if (
        _third_party_platform_app_action(title, text)
        and not is_material_apple_device_operational_deployment(title, text)
    ):
        return "third-party software action on an Apple platform without a direct Apple action"
    if _third_party_accessory_action(title, text):
        return "third-party accessory without an Apple product or platform change"
    if (
        "non-apple-component-market-background" in identity.facets
        and not _measured_apple_market_result_keys(title, text, text)
    ):
        return "broad multi-vendor market report without a measured Apple result"
    claim_reason = _editorial_or_third_party_claim_reason(title, text, identity)
    if claim_reason:
        versioned_editorial_feature = bool(
            claim_reason == "analysis or explanation without a new title-led Apple action"
            and _versioned_os_feature_report(text, identity)
        )
        if versioned_editorial_feature:
            claim_reason = ""
        false_non_apple_owner_signal = claim_reason.startswith(
            "non-Apple primary subject"
        ) and trusted_direct_action
        if claim_reason and not false_non_apple_owner_signal:
            return claim_reason
    if relevance_tier == "ecosystem" or trusted_direct_action:
        return ""
    if _versioned_os_feature_report(text, identity):
        return ""
    if _broad_component_supply_outlook(text):
        return "broad component supply outlook without a direct Apple action"
    if _supplier_market_without_apple_action(text, identity):
        return "supplier market story without a direct Apple procurement or product action"
    if (
        re.match(
            r"^(?!apple(?:'s)?\b|beats\b)[a-z][a-z0-9.+-]{1,36}['’]s\b.{0,65}"
            r"\b(?:adapter|accessory|case|charger|controller|dock|keyboard|stand)\b",
            text,
        )
        and _contains(text, "iphone", "ipad", "mac", "apple watch", "airpods")
    ):
        return "third-party accessory without an Apple product or platform change"
    if (
        _contains(text, "jailbreak", "jailbroken", "越狱", "民间开发者")
        and _contains(text, "virtual machine", "virtualization", "macos on ipad", "虚拟机", "iPad 用上 macOS")
    ):
        return "unsupported third-party jailbreak or virtualization tool"
    if (
        _contains(text, "benchmark", "benchmarks", "跑分", "性能表现", "不及", "对比")
        and _contains(text, "than macbook", "macbook pro", "苹果快", "apple macbook")
        and not _contains(text, "apple report", "apple announced", "苹果宣布", "苹果发布")
    ):
        return "competitor benchmark with Apple comparison context"
    if (
        _contains(text, "carplay")
        and _contains(text, "third-party", "app", "boat", "boats", "yacht", "游艇", "船")
        and not _contains(
            text,
            "apple adds",
            "apple changes",
            "apple announced",
            "ios adds",
            "ios changes",
            "苹果新增",
            "苹果宣布",
            "ios 新增",
        )
    ):
        return "third-party CarPlay availability without a platform change"
    content_form = _reconciliation_content_form(text, identity)
    if content_form == "event_preview":
        return "editorial event preview without a new Apple action"
    if any(component.startswith("os-wave:") for component in identity.components):
        return ""
    if content_form == "roundup":
        exact_current_action = bool(
            len(exact_facets) == 1
            and identity.title_actions
        )
        if not exact_current_action:
            return "editorial roundup without a new Apple action"
    if exact_facets:
        # A concrete, crawler-verified Apple action outranks weaker editorial
        # cues when the article itself is not an explicit roundup.
        return ""
    if content_form in {
        "buying_advice",
        "deal",
        "podcast",
        "poll",
        "roundup",
        "tutorial",
        "user_anecdote",
    }:
        return f"editorial {content_form.replace('_', ' ')} without a new Apple action"
    if re.match(r"^(?:no,|yes,|why\b|my\b)", text) and not identity.title_actions:
        return "opinion or commentary without a new Apple action"
    if re.match(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果).{2,60}\bexperience shows\b", text):
        return "competitor experience commentary without a new Apple action"
    if identity.scope == "third-party-context":
        return "third-party title context without a direct Apple action"
    return ""


def _hard_third_party_boundary(text: str, defer_reason: str) -> str:
    if not defer_reason:
        return ""
    if defer_reason.startswith("broad component supply"):
        return "broad-component-supply-outlook"
    if defer_reason.startswith("supplier market story"):
        return "independent-supplier-market-story"
    if defer_reason.startswith("broad multi-vendor market"):
        return "independent-multi-vendor-market-report"
    if re.match(
        r"^(?!apple\b|iphone\b|ipad\b|ios\b|mac(?:book|os)?\b|苹果).{2,55}'s\s+"
        r"(?:latest\s+)?(?:ios|ipados|macos|watchos|carplay|iphone|ipad|mac)\s+"
        r"(?:app\s+)?(?:update|release|version|feature)\b",
        text,
    ):
        return "independent-third-party-platform-update"
    if defer_reason.startswith("third-party ") or defer_reason.startswith((
        "editorial ",
        "competitor benchmark",
        "anniversary or retrospective",
        "unsupported third-party",
        "third-party CarPlay",
        "third-party employer asset disposal",
        "opinion or commentary",
        "reader poll",
        "competitor experience",
    )):
        return "independent-third-party-action"
    return ""


def _official_refurbished_store_action(text: str) -> bool:
    return bool(
        _contains(
            text,
            "certified refurbished store",
            "apple refurbished store",
            "online refurbished store",
            "official refurbished",
            "苹果官方翻新",
            "苹果认证翻新",
            "苹果翻新商店",
            "官翻",
        )
        and _contains(
            text,
            "adds",
            "added",
            "adding",
            "expands",
            "updates",
            "updated",
            "available",
            "began selling",
            "started selling",
            "上架",
            "新增",
            "开售",
            "扩充",
        )
    )


def _official_apple_store_transaction_option_action(title: str, lead: str) -> bool:
    """Recognize a material checkout change on Apple's own retail surface.

    A bank, wallet, or credit provider can own the announcement while the
    changed capability belongs to Apple Store checkout. This is different
    from a third-party app merely becoming available on an Apple platform.
    """
    text = _normalized(f"{title}. {lead[:900]}")
    official_store = bool(
        re.search(
            r"\b(?:apple\s+online\s+store|apple\s+store\s+online(?:\s+store)?)\b|"
            r"苹果\s*apple\s*store\s*在线商店|苹果在线商店",
            text,
        )
    )
    if not official_store or _contains(text, "app store", "应用商店"):
        return False
    transaction_option = _contains(
        text,
        "payment option",
        "payment method",
        "pay with",
        "checkout",
        "financing",
        "installment",
        "interest-free",
        "interest free",
        "credit card",
        "debit card",
        "付款选项",
        "支付方式",
        "结账",
        "分期",
        "免息",
        "信用卡",
        "借记卡",
    )
    buyer_can_use = bool(
        re.search(
            r"\b(?:customers?|users?|shoppers?)\b.{0,90}\b(?:can|may|able\s+to)\b"
            r".{0,90}\b(?:pay|choose|select|use|finance|buy|purchase)\b|"
            r"(?:用户|消费者|顾客).{0,90}(?:可|可以|能够|选择).{0,90}"
            r"(?:付款|支付|分期|免息|购买|选购)",
            text,
        )
    )
    apple_retail_purchase = bool(
        re.search(
            r"\b(?:buy|buying|purchase|purchasing|order|ordering)\b.{0,80}"
            r"\b(?:iphone|ipad|mac|apple\s+watch|airpods)\b|"
            r"(?:购买|选购|下单).{0,80}(?:iphone|ipad|mac|apple\s*watch|airpods|苹果产品)",
            text,
        )
    )
    return transaction_option and buyer_can_use and apple_retail_purchase


def _canonical_first_party_action_keys(
    identity: EventIdentity,
) -> set[str]:
    """Project a direct title claim onto a source-independent event key.

    The projection intentionally uses only action classes whose subject can be
    established without article-body context. This lets translations and
    differently worded headlines reconcile while keeping product roundups and
    multi-action stories out of the same bucket.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return set()
    actions = identity.title_actions & {
        "catalog-expansion",
        "commercial-launch",
        "leadership-transition",
        "model-development",
        "withdrawal",
    }
    if not actions:
        actions = identity.actions & {
            "catalog-expansion",
            "commercial-launch",
            "leadership-transition",
            "model-development",
            "withdrawal",
        }
    if not actions:
        return set()

    subjects: set[str] = set()
    if "official-refurbished-catalog" in identity.components:
        subjects.add("official-refurbished-catalog")
    if "apple-leadership" in identity.components:
        subjects.add("apple-leadership")
    direct_products = identity.title_products & {
        "apple-intelligence",
        "apple-maps",
        "iphone",
    }
    if len(direct_products) == 1:
        subjects |= direct_products
    if not subjects:
        return set()
    return {
        f"canonical-apple-action:{subject}:{action}"
        for subject in subjects
        for action in actions
    }


def _editorial_source_proves_current_first_party_action(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> bool:
    """Let editorial framing carry an independently stated Apple action."""
    if (
        identity.content_form not in {"hands_on", "review"}
        or identity.scope != "apple-direct"
        or not identity.title_products
    ):
        return False
    lead_scope = _short_lead_scope(lead, sentences=2, limit=520)
    lead_scope = re.sub(
        r"^[^。.!?]{0,40}(?:消息|讯)[,，:：]?\s*",
        "",
        lead_scope,
    )
    first_party_owner = bool(
        re.search(
            r"^(?:apple(?:'s|’s)?|apple\s+(?:officially|today)|苹果(?:公司|官方)?)"
            r".{0,90}\b(?:launch(?:ed|es)?|release(?:d|s)?|introduc(?:ed|es)?|"
            r"list(?:ed|s)?|made\s+available|lower(?:ed|s)?|rais(?:ed|es)?)\b|"
            r"^(?:苹果(?:公司|官方)?).{0,90}(?:上架|发布|推出|开售|上市|降价|涨价|调价)",
            lead_scope,
            re.I,
        )
    )
    current_action = bool(
        identity.title_actions & {"price-change", "product-launch", "retail-availability"}
        or re.search(
            r"\b(?:now\s+available|launch(?:ed|es)?|release(?:d|s)?|introduc(?:ed|es)?|"
            r"list(?:ed|s)?|lower(?:ed|s)?|rais(?:ed|es)?\s+(?:the\s+)?price)\b|"
            r"(?:近日|今日|现已).{0,24}(?:上架|发布|推出|开售|上市)|"
            r"(?:价格|售价).{0,16}(?:下调|上调|降至|涨至)|(?:降价|涨价|调价)",
            f"{_normalized(title)} {lead_scope}",
            re.I,
        )
    )
    return first_party_owner and current_action


def _third_party_platform_app_action(
    title: str,
    lead: str,
) -> tuple[str, str, str] | None:
    """Identify a third-party software owner separately from its Apple target."""
    title_text = _normalized(title)
    if re.match(
        r"^(?:apple(?:'s)?|苹果|ios\b|ipados\b|macos\b|watchos\b|tvos\b|visionos\b)",
        title_text,
    ):
        return None
    platform = next(
        (
            value
            for value, terms in (
                (
                    "macos",
                    (
                        "mac app",
                        "macos",
                        "for mac",
                        "on mac",
                        "on the mac",
                        "to mac",
                        "mac端",
                        "mac 端",
                        "mac 应用",
                        "mac 客户端",
                        "mac 桌面端",
                        "mac 原生版",
                        "mac 版",
                        "登陆 mac",
                        "登陆mac",
                    ),
                ),
                (
                    "ios",
                    (
                        "ios app",
                        "for iphone",
                        "to iphone",
                        "iphone 应用",
                        "ios 应用",
                        "ios版",
                        "ios 版",
                    ),
                ),
                ("ipados", ("ipados app", "for ipad", "to ipad", "ipad 应用")),
                ("watchos", ("watchos app", "apple watch app", "watch 应用")),
                ("visionos", ("visionos app", "vision pro app", "vision pro 应用")),
                ("tvos", ("tvos app", "apple tv app", "apple tv 应用")),
            )
            if _contains(title_text, *terms)
        ),
        "",
    )
    software_subject = bool(
        re.search(
            r"\b(?:app|application|client|game|integration|plugin|utility|messages?|imessages?)\b|"
            r"(?:应用|客户端|桌面端|原生版|游戏|插件|工具)|"
            r"(?:ios|ipados|macos|watchos|visionos|tvos)\s*版",
            title_text,
        )
        or _contains(title_text, "imessage", "messages", "信息应用", "信息”应用")
    )
    if not platform or not software_subject:
        return None
    if not _contains(
        title_text,
        "add",
        "adds",
        "added",
        "gain",
        "gains",
        "update",
        "updates",
        "can read",
        "can now read",
        "can send",
        "can now send",
        "control",
        "controls",
        "can control",
        "can now control",
        "launch",
        "release",
        "available",
        "getting",
        "comes to",
        "arrives",
        "support",
        "supports",
        "新增",
        "更新",
        "接入",
        "集成",
        "支持",
        "控制",
        "读取",
        "发送",
        "开放",
        "推出",
        "发布",
        "上线",
        "登陆",
        "登录",
    ):
        return None

    capitalized = re.findall(
        r"(?<![A-Za-z0-9])"
        r"[A-Z][A-Za-z0-9.+-]*(?:\s+[A-Z][A-Za-z0-9.+-]*){0,2}"
        r"(?![A-Za-z0-9])",
        title,
    )
    rejected = {
        "app",
        "apple",
        "apple tv",
        "iphone",
        "ipad",
        "mac",
        "macos",
        "watchos",
        "vision pro",
    }
    product_terms = {"airpods", "iphone", "ipad", "macbook", "homepod", "vision pro"}
    named = [
        re.sub(
            r"\s+(?:can(?:\s+now)?|will|adds?|updates?|launches?|releases?|arrives?|gets?)\b.*$",
            "",
            value,
            flags=re.I,
        )
        for value in capitalized
        if _normalized(value) not in rejected
        and not _normalized(value).startswith(("apple ", "mac ", "ios "))
        and not any(term in _normalized(value) for term in product_terms)
    ]
    # Prefer the leading publisher/product name. Later capitalized phrases are
    # commonly feature names (for example screen sharing or dictation), not
    # the owner of the app. If a later candidate extends the same leading
    # owner token, retain that fuller product name across translated headlines.
    owner = ""
    if named:
        first_root = _normalized(named[0]).split()[0]
        same_owner = [
            value
            for value in named
            if _normalized(value).split()[0] == first_root
        ]
        owner = max(same_owner, key=lambda value: (len(value.split()), len(value)))
    if not owner:
        owner = re.split(
            r"\b(?:is getting|comes? to|launch(?:es|ed)?|releases?|arrives?)\b|"
            r"(?:推出|发布|上线|登陆|登录)",
            title_text,
            maxsplit=1,
        )[0].strip(" :-—–")
    owner_slug = re.sub(r"[^\w]+", "-", _normalized(owner)).strip("-")
    rejected_slugs = {re.sub(r"[^a-z0-9]+", "-", value).strip("-") for value in rejected}
    if not owner_slug or owner_slug in rejected_slugs or owner_slug.startswith("apple-"):
        return None
    target = "platform"
    if _contains(title_text, "messages", "imessage", "信息应用", "信息”应用", "信息 app"):
        target = "messages"
    elif _contains(title_text, "carplay"):
        target = "carplay"
    return owner_slug, platform, target


def _third_party_accessory_action(title: str, text: str) -> bool:
    """Return true when a vendor accessory merely targets Apple devices."""
    title_text = _normalized(title)
    if re.match(r"^(?:apple(?:'s)?|苹果(?:官方)?)(?:\b|\s)", title_text):
        return False
    primary_clause, separator, compatibility_clause = title_text.partition(":")
    if not separator:
        primary_clause, separator, compatibility_clause = title_text.partition("：")
    compatibility_only_launch = bool(
        separator
        and not re.search(
            r"\b(?:apple|iphone|ipad|mac(?:book)?|airpods|homepod|apple watch)\b|苹果",
            primary_clause,
        )
        and re.search(
            r"\b(?:launch(?:es|ed)?|release(?:s|d)?|goes? on sale|now available)\b|"
            r"(?:推出|发布|开售|上市|发售|现已开卖)",
            primary_clause,
        )
        and re.search(
            r"\b(?:supports?|compatible with|works with|integrates? with)\b.{0,30}"
            r"\b(?:apple home|homekit|iphone|ipad|mac|apple watch|homepod)\b|"
            r"(?:支持|兼容|适配|接入|可接入|原生支持).{0,24}"
            r"(?:apple home|homekit|iphone|ipad|mac|apple watch|homepod|苹果 home|苹果家庭)",
            compatibility_clause,
        )
    )
    if compatibility_only_launch:
        return True
    accessory_subject = bool(
        re.search(
            r"\b(?:adapter|case|charger|charging stand|controller|dock|keyboard|"
            r"power bank|screen protector|stand)\b|"
            r"(?:充电器|充电基座|充电宝|保护壳|保护套|转接器|适配器|支架|键盘|手柄)",
            title_text,
        )
    )
    apple_target = _contains(
        title_text,
        "iphone",
        "ipad",
        "macbook",
        "airpods",
        "apple watch",
        "ios",
    )
    vendor_action = _contains(
        title_text,
        "launch",
        "release",
        "hands-on",
        "compatible",
        "support",
        "推出",
        "发布",
        "首发",
        "开箱",
        "兼容",
        "适配",
        "支持",
    )
    official_apple_action = _contains(
        title_text,
        "apple launches",
        "apple releases",
        "apple unveils",
        "苹果推出",
        "苹果发布",
        "苹果上架",
        "苹果官方",
    )
    return bool(accessory_subject and apple_target and vendor_action and not official_apple_action)


def _leading_project_subject(title: str) -> str:
    """Extract a bounded project name that owns a compatibility milestone."""
    match = re.match(
        r"^([a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,3}?)"
        r"(?=(?:\s+(?:near(?:s|ing)?|approach(?:es|ing)?|adds?|gets?|gains?|"
        r"releases?|ships?|supports?|brings?))|(?:\s*(?:即将|将|已|接近|支持|适配)))",
        _normalized(title),
    )
    if not match:
        return ""
    subject = match.group(1).strip()
    ignored = {
        "apple",
        "apple silicon",
        "iphone",
        "ipad",
        "linux",
        "mac",
        "macbook",
        "report",
    }
    if subject in ignored:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", subject).strip("-")


def _platform_compatibility_milestone(
    title: str,
    lead: str,
    evidence: str,
    identity: EventIdentity,
) -> tuple[str, str, str] | None:
    """Project a project/platform/version milestone across language variants."""
    scope = f"{_normalized(title)}. {_normalized(lead)[:700]} {_normalized(evidence)[:900]}"
    project = _leading_project_subject(title)
    generation_match = re.search(r"(?<![a-z0-9])m([1-9])(?:\s|$|[^a-z0-9])", _normalized(title))
    compatibility = bool(
        re.search(
            r"\b(?:support|compatib(?:le|ility)|enablement|driver)\b|"
            r"(?:支持|适配|兼容|驱动)",
            scope,
        )
    )
    apple_platform = bool(
        re.search(r"\bapple\s+silicon\b|\bapple['’]?s\s+m[1-9]\b|苹果.{0,12}m[1-9](?:\s*系列)?\s*芯片", scope)
        or any(
            component.startswith("apple-silicon-generation:")
            for component in identity.components
        )
    )
    if not (project and generation_match and compatibility and apple_platform):
        return None
    if re.search(
        r"\b(?:near(?:s|ing)?|almost|close\s+to|coming\s+soon)\b.{0,48}"
        r"\b(?:release|ship|availability)\b|"
        r"(?:即将|接近|几乎).{0,30}(?:发布|推出|可用)",
        scope,
    ):
        milestone = "release-imminent"
    elif re.search(
        r"\b(?:released|shipped|now\s+available)\b|(?:正式发布|现已可用|已经发布)",
        scope,
    ):
        milestone = "released"
    else:
        milestone = "support-development"
    return project, f"apple-silicon-m{generation_match.group(1)}", milestone


def _repair_cost_estimate(
    title: str,
    lead: str,
    evidence: str,
    identity: EventIdentity,
) -> tuple[str, str, str] | None:
    """Project a named product/component/amount repair-cost estimate."""
    title_scope = _normalized(title)
    evidence_scope = f"{title_scope}. {_normalized(lead)[:750]} {_normalized(evidence)[:1400]}"
    repair_action = bool(
        re.search(
            r"\b(?:repair|replacement|replace|service\s+fee)\b|"
            r"(?:维修|更换|换屏|维修费用|维修费)",
            evidence_scope,
        )
    )
    if not repair_action:
        return None
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    if len(products) != 1:
        return None
    component = ""
    if re.search(r"\b(?:inner\s+)?(?:display|screen)\b|(?:内屏|屏幕|显示屏)", evidence_scope):
        component = "display"
    elif re.search(r"\bbattery\b|电池", evidence_scope):
        component = "battery"
    if not component:
        return None
    repair_matches = list(
        re.finditer(r"\b(?:repair|replacement|replace)\b|(?:维修|更换|换屏)", evidence_scope)
    )
    amount_matches = list(
        re.finditer(
            r"\$\s*([\d,]{2,})|([\d,]{2,})\s*(?:usd|u\.s\.\s*dollars?|美元)",
            evidence_scope,
        )
    )
    amount = ""
    if repair_matches and amount_matches:
        for candidate in amount_matches:
            distance = min(
                abs(candidate.start() - repair.start())
                for repair in repair_matches
            )
            local_context = evidence_scope[
                max(0, candidate.start() - 60) : candidate.end() + 60
            ]
            whole_product_price = bool(
                re.search(
                    r"\b(?:starting|launch|retail)\s+price\b|"
                    r"(?:起售价|整机(?:定价|售价)|新机售价|手机售价)",
                    local_context,
                )
            )
            if distance <= 180 and not whole_product_price:
                amount = (candidate.group(1) or candidate.group(2)).replace(",", "")
                break
    if not amount:
        return None
    product = next(iter(products))
    return f"{product}-{component}", "repair-cost-estimate", f"usd-{amount}"


def _unreleased_hardware_launch_roadmap(
    title: str,
    lead: str,
    identity: EventIdentity,
) -> tuple[str, str] | None:
    """Bind a launch and its year to one primary assertion, not body background."""
    title_scope = _normalized(title)
    lead_scope = _normalized(lead)[:700]
    if lead_scope.startswith(title_scope):
        lead_scope = lead_scope[len(title_scope):].lstrip(" .:-：")
    lead_scope = re.split(r"[。！？]|(?<=[.!?])\s+", lead_scope, maxsplit=1)[0]
    products = identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    named_apple_glasses = bool(re.search(
        r"(?:\bapple(?:'s)?\b|苹果).{0,28}(?:smart\s+glasses|ai\s+glasses|智能眼镜|ai\s*眼镜)",
        title_scope,
    ))
    if named_apple_glasses:
        products = {"apple-glasses"}
    if len(products) != 1:
        return None
    title_year = re.search(r"\b(20(?:2[6-9]|3\d))\b", title_scope)
    first_party_subject = bool(
        re.search(r"\bapple(?:'s)?\b|苹果", title_scope)
        and identity.scope == "apple-direct"
    )
    launch_pattern = (
        r"\b(?:launch(?:es|ed|ing)?|reveal(?:s|ed|ing)?|unveil(?:s|ed|ing)?|"
        r"debut(?:s|ed|ing)?|ship(?:s|ped|ping)?|release(?:s|d|ing)?)\b|"
        r"(?:发布|推出|亮相|揭晓|发售|上市|出货)"
    )
    title_launch_action = bool(re.search(launch_pattern, title_scope))
    future_year = next((
        year for assertion in (title_scope, lead_scope)
        if re.search(launch_pattern, assertion)
        and (year := re.search(r"\b(20(?:2[6-9]|3\d))\b", assertion))
    ), None)
    future_modality = bool(
        re.search(
            r"\b(?:will|plans?\s+to|expected\s+to|set\s+to|next\s+year|"
            r"as\s+soon\s+as|reportedly)\b|"
            r"(?:计划|预计|有望|将于|即将|明年|据称|传闻)",
            title_scope,
        )
    )
    future_title_action = bool(
        future_modality
        or (title_year and title_launch_action)
    )
    if not (
        first_party_subject
        and future_year
        and future_title_action
    ):
        return None
    return next(iter(products)), future_year.group(1)


def _finish_alternative_relations(title: str, lead: str, evidence: str, generation: str) -> set[str]:
    """Identify the disputed finishes, never a shared lineup count alone."""
    aliases = {
        "black": r"\bblack\b|黑色",
        "white": r"\bwhite\b|白色",
        "silver": r"\bsilver\b|银色",
        "gold": r"\bgold\b|金色",
        "blue": r"\bblue\b|蓝色|天空蓝|天蓝",
        "red": r"\bred\b|红色",
        "green": r"\bgreen\b|绿色",
        "pink": r"\bpink\b|粉色",
        "purple": r"\bpurple\b|紫色",
    }

    def finishes(clause: str) -> tuple[set[str], set[str]]:
        present, excluded = set(), set()
        for name, pattern in aliases.items():
            for match in re.finditer(pattern, clause):
                prefix = clause[max(0, match.start() - 32):match.start()]
                if re.search(r"\b(?:without|excluding|no|not)\s+$|(?:没有|不含|无含|取消|不提供)\s*$", prefix):
                    excluded.add(name)
                else:
                    present.add(name)
        return present, excluded

    title_text, primary = _primary_assertion_scope(title, lead)
    _, excluded = finishes(primary)
    present = set()
    clauses = re.split(r"[。！？]|(?<=[.!?])\s+", _normalized(f"{title}. {lead[:900]} {evidence[:1200]}"))
    for clause in clauses:
        models = set(re.findall(r"iphone\s*(\d{1,2})(?!\d)", clause))
        if models - {generation} or re.search(r"\b(?:last year|previous|previously|back in)\b|去年|上一代|此前", clause):
            continue
        values, _ = finishes(clause)
        present |= values
    relations = {",".join(sorted((left, right))) for left in excluded for right in present - excluded}
    # An indirect dispute can name mutually exclusive alternatives without
    # endorsing either. That is the same attribute question as the part leak.
    if re.search(r"\b(?:whether|battle|disagree|conflicting)\b|争议|分歧", title_text):
        for left, right in combinations(aliases, 2):
            a, b = aliases[left], aliases[right]
            if re.search(rf"(?:{a})\s+(?:or|还是)\s+(?:{b})|(?:{b})\s+(?:or|还是)\s+(?:{a})", title_text):
                relations.add(",".join(sorted((left, right))))
    return relations


def _primary_claim_projection(
    title: str,
    lead: str,
    identity: EventIdentity,
    regions: Iterable[str],
    evidence: str = "",
) -> tuple[set[str], set[str], set[str], str, bool]:
    """Return a title-led subject/predicate frame for sparse cross-source news.

    Legacy topic matching is intentionally recall-oriented and can place nearby
    Apple stories in one provisional seed. These keys describe the concrete
    claim made by the headline and first substantive lead, so reconciliation
    can require positive identity instead of treating missing conflicts as
    proof that two reports are the same.
    """
    title_text, text = _primary_assertion_scope(title, lead)
    full_title_text = _canonical_title(title)
    claim_evidence = f"{text} {_normalized(evidence)[:1400]}".strip()
    extended_claim_evidence = (
        f"{full_title_text} {_normalized(lead)[:1600]} {_normalized(evidence)[:1400]}"
    ).strip()
    event_keys: set[str] = set()
    boundaries: set[str] = set()
    separation: set[str] = set()
    category_hint = ""
    trusted_direct_action = False

    def add_claim(
        subject: str,
        predicate: str,
        *,
        qualifier: str = "",
        category: str = "",
        trusted: bool = True,
    ) -> None:
        nonlocal category_hint, trusted_direct_action
        suffix = f":{qualifier}" if qualifier else ""
        event_keys.add(f"primary-claim:{subject}:{predicate}{suffix}")
        boundaries.add(f"primary-claim-subject:{subject}")
        separation.add(f"primary-claim-subject:{subject}")
        separation.add(f"primary-claim-predicate:{predicate}")
        if category:
            category_hint = category
        trusted_direct_action = trusted_direct_action or trusted

    shared_resource_operation = _versioned_shared_resource_operation(title, lead)
    if shared_resource_operation:
        subject, predicate = shared_resource_operation
        add_claim(subject, predicate, category="software_systems")

    # A disclosure must identify the disputed attribute values. Equal counts
    # and generic component names are not evidence of the same report.
    finish_topic = _primary_title_changed_object(full_title_text) == "finish-color" or (
        not _primary_title_changed_object(full_title_text)
        and re.search(r"\b(?:colors?|colours?|finishes?)\b", text)
    )
    finish_disclosure = bool(
        finish_topic
        and re.search(r"\b(?:leaks?|leaked|leakers?|rumou?rs?)\b|泄露|爆料|曝光", full_title_text)
    )
    finish_models = sorted(
        c.removeprefix("iphone-family:")
        for c in identity.title_components if c.startswith("iphone-family:")
    )
    if finish_disclosure and len(finish_models) == 1:
        generation = finish_models[0].split("-", 1)[0]
        for relation in _finish_alternative_relations(title, lead, evidence, generation):
            add_claim(
                f"iphone-{finish_models[0]}", "finish-lineup-disclosure",
                qualifier=f"alternatives:{relation}", category="hardware_products",
            )
            separation.add(f"finish-alternatives:{relation}")

    direct_title_subject = bool(
        identity.scope == "apple-direct"
        or re.search(r"^(?:apple(?:'s|’s)?|苹果)", title_text)
        or re.search(
            r"^(?:report|leak|code|sources?|消息|报道|泄露|代码|文件|爆料)"
            r"[^。.!?]{0,32}(?:apple(?:'s|’s)?|苹果)",
            title_text,
        )
    )

    first_party_rename_product = next(
        iter(
            identity.title_products
            & {
                "app-store",
                "apple-books",
                "apple-maps",
                "apple-music",
                "apple-sports",
                "apple-tv",
                "apple-wallet",
                "icloud",
                "safari",
            }
        ),
        "",
    )
    title_owned_rename = bool(
        first_party_rename_product
        and is_direct_first_party_named_object_change(full_title_text, lead)
    )
    rename_target = ""
    if title_owned_rename:
        for pattern in (
            r"\b(?:use|uses|using|display|displays|show|shows|label|labels|mark|marks)\b"
            r"[^'\"“”]{0,50}['\"“]([^'\"“”]{2,60})['\"”][^.!?]{0,40}"
            r"\binstead\s+of\b",
            r"\bbring(?:s|ing)?\s+up\b[^.!?]{0,100}\b(?:if|when)\b[^.!?]{0,60}"
            r"\bsearch(?:es|ing)?\s+(?:for\s+)?['\"“]([^'\"“”]{2,60})['\"”]",
            r"\b(?:update|updates|updated|change|changes|changed|rename|renames|renamed)\b"
            r"[^'\"“”]{0,50}['\"“][^'\"“”]{2,60}['\"”]\s+(?:to|as)\s+"
            r"['\"“]([^'\"“”]{2,60})['\"”]",
            r"(?:改名为|更名为|重命名为|改称|标注为|显示为)\s*[“\"]([^”\"]{2,30})[”\"]",
            r"\b(?:rename|renames|renamed|renaming|relabel|relabels|relabeled|relabeling)\b"
            r"[^'\"“”]{0,80}['\"“]([^'\"“”]{2,60})['\"”]",
            r"\b(?:change(?:s|d)?|rename(?:s|d)?|relabel(?:s|ed)?)\b[^。.!?]{0,90}?"
            r"\bto\s+([a-z][a-z0-9 .'-]{2,50}?)(?=\s+(?:as|for|in)\b|[,.;!?]|$)",
            r"\b(?:display|displays|show|shows)\s+([a-z][a-z0-9 .'-]{2,50}?)\s+instead\s+of\b",
            r"(?:改名为|更名为|重命名为|改称|标注为|显示为)([^，。！？:：\s]{2,30})",
        ):
            match = re.search(pattern, extended_claim_evidence, re.I)
            if not match:
                continue
            rename_target = re.sub(
                r"[^a-z0-9\u3400-\u9fff]+",
                "-",
                _normalized(match.group(1)),
            ).strip("-")
            if rename_target:
                break
    if first_party_rename_product and rename_target:
        add_claim(
            f"first-party-app-{first_party_rename_product}",
            "named-object-rename",
            qualifier=rename_target,
            category="software_systems",
            trusted=True,
        )
        named_object_classes = (
            ("lake", r"\blake\b|湖"),
            ("gulf", r"\bgulf\b|海湾|湾"),
            ("river", r"\briver\b|河"),
            ("sea", r"\bsea\b|海"),
            ("mountain", r"\bmount(?:ain)?\b|山"),
            ("island", r"\bisland\b|岛"),
            ("road", r"\b(?:road|street|avenue|highway)\b|(?:道路|公路|街道|大街)"),
            ("airport", r"\bairport\b|机场"),
            ("station", r"\bstation\b|车站"),
            ("park", r"\bpark\b|公园"),
            ("city", r"\bcity\b|城市|市"),
            ("country", r"\bcountry\b|国家|国"),
        )
        named_object_class = next(
            (
                object_class
                for object_class, pattern in named_object_classes
                if re.search(pattern, full_title_text, re.I)
            ),
            "",
        )
        explicit_regions = sorted(set(regions) - {"multi-region"})
        if named_object_class and explicit_regions:
            event_keys.add(
                f"primary-claim:first-party-app-{first_party_rename_product}:"
                f"named-object-rename-class:{named_object_class}:"
                f"{','.join(explicit_regions)}"
            )

    explicit_catalog_scale = bool(
        re.search(
            r"\b(?:10|ten|eleven|11)\+?\s+(?:products?|devices?|models?)\b|"
            r"(?:10|十|11|十一)(?:余|多|\+)?\s*款(?:在售)?(?:产品|设备|机型)",
            title_text,
            re.I,
        )
        and len(identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS) >= 2
    )
    catalog_withdrawal = bool(
        (identity.scope == "apple-direct" or _contains(title_text, "apple", "苹果"))
        and re.search(
            r"\b(?:discontinu(?:e|es|ed|ing)|withdraw(?:s|n|ing)?|remove(?:s|d|ing)?|"
            r"drop(?:s|ped|ping)?|retire(?:s|d|ing)?)\b|"
            r"(?:下架|停售|停产|停止销售|退出在售阵容|移出产品线)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:products?|devices?|models?|lineup|catalog)\b|"
            r"(?:多款|款设备|款(?:在售)?产品|产品阵容|在售阵容|官网产品)",
            title_text,
            re.I,
        )
        and (
            len(_bounded_evidence_products(claim_evidence)) >= 2
            or explicit_catalog_scale
        )
    )
    if catalog_withdrawal:
        add_claim(
            "apple-product-catalog",
            "multi-product-withdrawal-forecast",
            category="hardware_products",
            trusted=True,
        )

    executive_farewell = bool(
        re.search(
            r"\b(?:signs?\s+off|farewell|thanks?\s+(?:apple\s+)?staff)\b|"
            r"\b(?:comments?|responds?|response|message|memo|letter|email|note|post|writes?|says?|remarks?)\b"
            r".{0,48}\b(?:final|last)\s+day\b|"
            r"\b(?:final|last)\s+day\b.{0,48}"
            r"\b(?:comments?|responds?|response|message|memo|letter|email|note|post|writes?|says?|remarks?)\b|"
            r"(?:告别.{0,8}(?:信|内部信)|最后一封.{0,12}内部信|告别员工|感谢员工)|"
            r"(?:最后一天).{0,30}(?:回应|致信|发信|内部信|备忘录|发文|留言|感谢|告别)|"
            r"(?:回应|致信|发信|内部信|备忘录|发文|留言|感谢|告别).{0,30}(?:最后一天)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:ceo|chief executive|tim cook|john ternus)\b|"
            r"(?:首席执行官|库克|特努斯)",
            title_text,
            re.I,
        )
    )
    if executive_farewell:
        add_claim(
            "apple-leadership",
            "executive-farewell-communication",
            category="software_systems",
            trusted=True,
        )

    company_hall_award = bool(
        _contains(title_text, "apple", "苹果")
        and re.search(
            r"\b(?:induct(?:ed|s)?|honou?red|recognized|named)\b|"
            r"(?:入选|获表彰|获授|列入)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:creative|brand)\s+hall\s+of\s+fame\b|"
            r"(?:创意|品牌)名人堂",
            title_text,
            re.I,
        )
    )
    if company_hall_award:
        add_claim(
            "apple-brand",
            "hall-of-fame-induction",
            category="software_systems",
            trusted=True,
        )

    personnel_role_change = bool(
        re.search(r"\bphil\s+schiller\b|菲尔[·・.\s]*席勒", title_text, re.I)
        and re.search(
            r"\b(?:steps?\s+(?:down|back)|scales?\s+back|no\s+longer\s+working|"
            r"leav(?:es|ing)\s+(?:his\s+)?(?:biggest\s+)?(?:job|jobs|duties))\b|"
            r"(?:卸任|退出|不再负责|缩减|淡出).{0,24}(?:职责|工作|管理|负责人)?",
            title_text,
            re.I,
        )
    )
    if personnel_role_change:
        add_claim(
            "apple-personnel-phil-schiller",
            "role-reduction",
            category="software_systems",
            trusted=True,
        )

    executive_profile_asset_update = bool(
        re.search(r"\b(?:ceo|chief executive)\b|(?:首席执行官|ceo)", title_text, re.I)
        and re.search(
            r"\b(?:profile\s+(?:photo|image)|avatar|headshot)\b|(?:头像|个人资料图片)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:replac(?:e|es|ed|ing)|updat(?:e|es|ed|ing)|swap(?:s|ped|ping)?)\b|"
            r"(?:更换|替换|更新)",
            title_text,
            re.I,
        )
    )
    if executive_profile_asset_update:
        add_claim(
            "apple-leadership",
            "ceo-social-profile-image-update",
            category="software_systems",
            trusted=True,
        )

    executive_social_account = bool(
        re.search(r"(?<![a-z])ceo(?![a-z])|\bchief executive\b|首席执行官", title_text, re.I)
        and re.search(
            r"\b(?:on|joins?|opens?|launches?|starts?)\s+(?:an?\s+)?(?:x|twitter|weibo)\b|"
            r"\bfirst\s+(?:post|message)\b|"
            r"(?:入驻|开通|启用|开).{0,18}(?:微博|社交账号|社交平台|x\s*平台)|"
            r"(?:首条|第一条).{0,10}(?:博文|帖子|消息|动态)",
            title_text,
            re.I,
        )
    )
    if executive_social_account:
        add_claim(
            "apple-leadership",
            "ceo-social-account-launch",
            category="software_systems",
            trusted=True,
        )

    official_follow_change = bool(
        re.search(r"(?:apple|苹果).{0,8}(?:官方|official).{0,16}(?:账号|社媒|account)", title_text)
        and re.search(r"取关|唯一关注|取消关注|\bunfollows?\b|\bonly\s+follows?\b", title_text)
        and re.search(r"ceo|首席执行官", title_text)
    )
    if official_follow_change:
        add_claim("apple-corporate-social-account", "ceo-follow-change", category="software_systems")

    executive_compensation_signal = bool(
        re.search(
            r"\b(?:salary|compensation|equity award|stock award)\b|"
            r"(?:薪酬|年薪|工资|股权奖励|股票奖励)",
            title_text,
            re.I,
        )
        or re.search(
            r"\bpaying\b.{1,64}\bto\s+(?:run|lead|serve\s+as\s+(?:the\s+)?ceo)\b|"
            r"\b(?:what|how\s+much)\b.{0,40}\bpay(?:ing)?\b.{0,40}"
            r"\b(?:ceo|chief executive)\b",
            title_text,
            re.I,
        )
    )
    executive_compensation = executive_compensation_signal and bool(
        re.search(r"\b(?:apple|ceo|chief executive)\b|(?:苹果|首席执行官)", title_text, re.I)
        or re.search(r"\b(?:new\s+)?ceo\b|(?:新任\s*ceo|首席执行官)", text, re.I)
    )
    if executive_compensation:
        add_claim(
            "apple-leadership",
            "ceo-compensation-disclosure",
            category="software_systems",
            trusted=True,
        )

    executive_memo_title_signal = bool(
        re.search(
            r"\b(?:memo|letter|email)\b|"
            r"\baddresses?\s+(?:apple\s+)?staff\b|"
            r"(?:内部信|公开信|全员信|备忘录|致员工|致全体员工)",
            full_title_text,
            re.I,
        )
        or (
            re.search(
                r"\b(?:teases?|promises?|says?)\b.{0,45}\b(?:launch|event|products?)\b|"
                r"(?:放话|预告|透露).{0,32}(?:下周|新品|发布|活动)",
                full_title_text,
                re.I,
            )
            and re.search(
                r"\b(?:memo|letter|email)\b|(?:内部信|公开信|全员信|备忘录)",
                extended_claim_evidence,
                re.I,
            )
        )
    )
    first_executive_employee_memo = bool(
        executive_memo_title_signal
        and
        re.search(
            r"\b(?:memo|letter|email|message)\b.{0,42}\b(?:employees?|staff|company[- ]wide)\b|"
            r"\b(?:employees?|staff|company[- ]wide)\b.{0,42}\b(?:memo|letter|email|message)\b|"
            r"(?:首封|第一封|全员|内部).{0,24}(?:内部信|公开信|信件|备忘录|邮件)|"
            r"(?:内部信|公开信|备忘录|全员信).{0,20}(?:首封|第一封|上任)|"
            r"(?:发给|致).{0,16}(?:全体|全员|内部).{0,12}(?:员工|职员).{0,12}(?:公开信|信件|备忘录|邮件)",
            extended_claim_evidence,
            re.I,
        )
        and re.search(
            r"\b(?:first\s+day|first\s+(?:company[- ]wide\s+)?memo|new\s+(?:apple\s+)?ceo)\b|"
            r"(?:首封|第一封|上任|新(?:任)?\s*ceo|(?:正式)?(?:出任|接任|就任).{0,20}(?:苹果)?\s*ceo)",
            extended_claim_evidence,
            re.I,
        )
        and re.search(
            r"\b(?:ceo|chief executive)\b|(?:首席执行官|ceo)",
            extended_claim_evidence,
            re.I,
        )
    )
    if first_executive_employee_memo:
        add_claim(
            "apple-leadership",
            "ceo-first-employee-memo",
            category="software_systems",
            trusted=True,
        )

    corporate_services_role_exit = bool(
        re.search(
            r"\b(?:apple|former\s+apple|ex-apple)\b.{0,44}\b(?:cfo|executive|luca\s+maestri)\b|"
            r"\b(?:luca\s+maestri|cfo|executive)\b.{0,44}\bapple\b|"
            r"(?:苹果).{0,32}(?:首席财务官|高管|马斯特里)|(?:马斯特里).{0,32}(?:苹果|首席财务官|高管)",
            full_title_text,
            re.I,
        )
        and re.search(
            r"\bcorporate services\b|企业服务(?:部门|职责)?",
            extended_claim_evidence,
            re.I,
        )
        and re.search(
            r"\b(?:isn['’]?t\s+running|no\s+longer\s+runs?|step(?:s|ped|ping)?\s+down|leaves?|exits?)\b|"
            r"(?:卸任|退出|不再负责|离任)",
            extended_claim_evidence,
            re.I,
        )
    )
    if corporate_services_role_exit:
        add_claim(
            "apple-corporate-services",
            "role-exit",
            category="software_systems",
            trusted=True,
        )

    inbox_accessory_policy_denial = bool(
        _contains(full_title_text, "apple", "iphone", "苹果")
        and _contains(
            full_title_text,
            "charger",
            "earpods",
            "in-box accessories",
            "充电头",
            "充电器",
            "耳机",
            "随盒配件",
        )
        and (
            re.search(
                r"\b(?:den(?:y|ies|ied)|no\s+(?:notice|policy|change)|not\s+restor(?:e|ing))\b|"
                r"(?:否认|辟谣|没有通知|未发布通知|并未恢复|不再附赠)",
                full_title_text,
                re.I,
            )
            or (
                re.search(r"\b(?:official\s+response|responds?)\b|官方回应", full_title_text, re.I)
                and re.search(
                    r"\b(?:den(?:y|ies|ied)|no\s+(?:notice|policy|change)|not\s+restor(?:e|ing))\b|"
                    r"(?:否认|辟谣|没有.{0,10}通知|未发布.{0,10}(?:通知|政策)|并未恢复|没有.{0,10}政策变更)",
                    extended_claim_evidence,
                    re.I,
                )
            )
        )
    )
    if inbox_accessory_policy_denial:
        add_claim(
            "iphone-in-box-accessories",
            "policy-denial",
            category="hardware_products",
            trusted=True,
        )

    foldable_magsafe_support = bool(
        "foldable-iphone" in identity.title_products
        and _contains(title_text, "magsafe", "磁吸充电")
        and re.search(
            r"\b(?:has|have|support(?:s|ed|ing)?|include(?:s|d)?)\b|"
            r"(?:支持|配备|搭载|有望支持)",
            title_text,
            re.I,
        )
    )
    if foldable_magsafe_support:
        add_claim(
            "foldable-iphone",
            "magsafe-support",
            category="hardware_products",
            trusted=True,
        )

    mac_intel_support_removal = bool(
        _contains(claim_evidence, "mac", "mac app store", "mac 开发者")
        and _contains(title_text, "intel", "英特尔", "arm64")
        and re.search(
            r"\b(?:drop|remove|end|stop|phase\s+out).{0,20}\bsupport(?:ing)?\b|"
            r"\barm64[- ]only\b|"
            r"(?:移除|停止|终止|放弃).{0,16}(?:支持|兼容)|仅支持\s*arm64",
            title_text,
            re.I,
        )
    )
    if mac_intel_support_removal:
        add_claim(
            "mac-developer-distribution",
            "intel-support-removal",
            category="software_systems",
            trusted=True,
        )

    legal_openai_response = bool(
        _contains(title_text, "openai")
        and _contains(claim_evidence, "trade secret", "trade-secret", "商业机密", "商业秘密")
        and re.search(
            r"\b(?:den(?:y|ies|ied)|reject(?:s|ed)?|responds?|response)\b|"
            r"\b(?:mess|problem)\b.{0,36}\b(?:apple['’]?s\s+own\s+making|of\s+apple['’]?s\s+own\s+making)\b|"
            r"\bnot\s+our\s+fault\b|"
            r"(?:否认|回应).{0,28}(?:窃取|窃密|指控|商业机密|商业秘密)|"
            r"(?:自己造成|一手造成).{0,18}(?:混乱|问题)|"
            r"(?:自身|自己).{0,12}(?:应为|应该为).{0,18}(?:混乱|问题).{0,8}负责",
            title_text,
            re.I,
        )
    )
    if legal_openai_response:
        add_claim(
            "apple-openai-trade-secret-case",
            "response-filing",
            category="hardware_products",
            trusted=True,
        )

    legal_evidence_disclosure = bool(
        not legal_openai_response
        and (
            re.search(
                r"^apple\b.{0,30}\b(?:accuses?|alleges?|claims?)\b.{0,40}\bopenai\b"
                r".{0,60}\b(?:destroy(?:ed|ing|uction)?|withhold(?:s|ing)?)\b.{0,20}\bevidence\b",
                title_text,
                re.I,
            )
            or (
                _contains(claim_evidence, "openai")
                and _contains(
                    claim_evidence,
                    "trade secret",
                    "trade-secret",
                    "商业机密",
                    "商业秘密",
                )
                and re.search(
                    r"\b(?:new|shocking|forensic)\s+evidence\b|"
                    r"\b(?:stolen|theft|destroy(?:ed|ing|uction))\b.{0,42}\bevidence\b|"
                    r"^apple\s+(?:says?|alleges?|claims?).{0,100}"
                    r"\b(?:stolen|theft|destroy(?:ed|ing|uction))\b|"
                    r"(?:新证据|惊人证据|震撼证据|取证证据|销毁证据)",
                    claim_evidence,
                    re.I,
                )
            )
        )
    )
    if legal_evidence_disclosure:
        add_claim(
            "apple-openai-trade-secret-case",
            "evidence-disclosure",
            category="hardware_products",
            trusted=True,
        )

    mac_desktop_ai_timing = bool(
        _contains(claim_evidence, "mac mini", "mini / studio", "mini/studio")
        and _contains(claim_evidence, "mac studio", "mini / studio", "mini/studio")
        and _contains(
            claim_evidence,
            "unusual timing",
            "unusually timed",
            "early launch",
            "launched early",
            "early announcement",
            "提前发布",
            "提前更新",
            "上新",
        )
        and _contains(
            claim_evidence,
            "ai demand",
            "enterprise demand",
            "enterprise appetite",
            "strong demand",
            "ai hardware",
            "ai 需求",
            "企业需求",
            "ai 硬件",
        )
        or bool(
            _contains(claim_evidence, "mac mini", "mini / studio", "mini/studio")
            and _contains(claim_evidence, "mac studio", "mini / studio", "mini/studio")
            and _contains(
                title_text,
                "unusual timing",
                "unusually timed",
                "all about ai",
                "提前发布",
                "提前更新",
                "提前上新",
            )
            and _contains(title_text, "ai", "人工智能")
        )
    )
    if mac_desktop_ai_timing:
        add_claim(
            "apple-mac-mini-studio",
            "ai-demand-accelerated-refresh",
            category="hardware_products",
            trusted=True,
        )

    if identity.content_form == "news":
        compatibility_milestone = _platform_compatibility_milestone(
            title,
            lead,
            evidence,
            identity,
        )
        if compatibility_milestone:
            project, platform_generation, milestone = compatibility_milestone
            add_claim(
                f"third-party-platform-{project}-{platform_generation}",
                milestone,
                category="software_systems",
                trusted=False,
            )

        repair_cost = _repair_cost_estimate(title, lead, evidence, identity)
        if repair_cost:
            repair_subject, repair_predicate, repair_amount = repair_cost
            add_claim(
                repair_subject,
                repair_predicate,
                qualifier=repair_amount,
                category="hardware_products",
                trusted=True,
            )

        hardware_roadmap = _unreleased_hardware_launch_roadmap(
            title,
            lead,
            identity,
        )
        if hardware_roadmap:
            roadmap_product, roadmap_year = hardware_roadmap
            add_claim(
                roadmap_product,
                "launch-roadmap",
                qualifier=roadmap_year,
                category="hardware_products",
                trusted=True,
            )

    normalized_regions = {
        region for region in regions if region and region != "multi-region"
    }
    disaster_relief_action = bool(
        normalized_regions
        and (
            identity.scope == "apple-direct"
            or _contains(text, "apple", "苹果")
        )
        and re.search(
            r"\b(?:donat(?:e|es|ed|ion)|pledges?|aid)\b.{0,70}"
            r"\b(?:relief|rebuilding|recovery|victims?)\b|"
            r"\b(?:relief|rebuilding|recovery)\b.{0,70}"
            r"\b(?:donat(?:e|es|ed|ion)|pledges?|aid)\b|"
            r"(?:捐款|捐助|援助|提供援助).{0,50}(?:救援|救灾|重建|灾后恢复)|"
            r"(?:救援|救灾|重建|灾后恢复).{0,50}(?:捐款|捐助|援助|提供援助)",
            text,
        )
        and re.search(
            r"\b(?:floods?|mudslides?|earthquakes?|wildfires?|typhoons?|hurricanes?)\b|"
            r"(?:洪水|洪灾|山洪|泥石流|地震|山火|台风|飓风|自然灾害)",
            text,
        )
    )
    if disaster_relief_action:
        for region in sorted(normalized_regions):
            add_claim(
                f"apple-disaster-relief-{region}",
                "donation",
                category="software_systems",
                trusted=True,
            )

    preorder_scope = f"{title_text}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    preorder_action = bool(
        re.search(r"\bpre[- ]?orders?\b|(?:预购|预售)", title_text)
        and re.search(
            r"\b(?:may|might|could|will|reportedly|expected to|set to)\b|"
            r"(?:可能|或将|预计|据称|消息称|报道)",
            preorder_scope,
        )
    )
    preorder_date = ""
    preorder_date_scope = f"{preorder_scope}. {_normalized(evidence)[:1400]}"
    month_names = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    english_date = re.search(
        r"\bpre[- ]?orders?\b[^。.!?]{0,100}\b("
        + "|".join(month_names)
        + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        preorder_date_scope,
    )
    chinese_date = re.search(
        r"(?:预购|预售)[^。！？]{0,70}(\d{1,2})\s*月\s*(\d{1,2})\s*日|"
        r"(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。！？]{0,70}(?:预购|预售)",
        preorder_date_scope,
    )
    iso_date = re.search(
        r"\bpre[- ]?orders?\b[^。.!?]{0,80}\b(?:20\d{2}-)?(\d{1,2})-(\d{1,2})\b",
        preorder_date_scope,
    )
    if english_date:
        preorder_date = f"{month_names[english_date.group(1)]:02d}-{int(english_date.group(2)):02d}"
    elif chinese_date:
        month = chinese_date.group(1) or chinese_date.group(3)
        day = chinese_date.group(2) or chinese_date.group(4)
        preorder_date = f"{int(month):02d}-{int(day):02d}"
    elif iso_date:
        preorder_date = f"{int(iso_date.group(1)):02d}-{int(iso_date.group(2)):02d}"
    if not preorder_date:
        avoided_date = re.search(
            r"\b(?:sidestep|avoid|move away from)\b[^。.!?]{0,45}\b("
            + "|".join(month_names)
            + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b[^。.!?]{0,65}"
            r"\b(?:moving|pushing|delaying)\b[^。.!?]{0,35}"
            r"\b(?:to saturday|to the next day|by a day)\b",
            preorder_date_scope,
        )
        if avoided_date:
            shifted = date(
                2000,
                month_names[avoided_date.group(1)],
                int(avoided_date.group(2)),
            ) + timedelta(days=1)
            preorder_date = f"{shifted.month:02d}-{shifted.day:02d}"
    if preorder_action and preorder_date:
        component_subjects = [
            f"{namespace}-{component.split(':', 1)[1]}"
            for prefix, namespace in (
                ("iphone-model:", "iphone"),
                ("iphone-family:", "iphone"),
                ("macbook-model:", "macbook"),
            )
            for component in sorted(identity.title_components)
            if component.startswith(prefix)
        ]
        preorder_subject = component_subjects[0] if component_subjects else ""
        if not preorder_subject and len(identity.title_products) == 1:
            preorder_subject = next(iter(identity.title_products))
        if preorder_subject:
            add_claim(
                preorder_subject,
                "preorder-schedule",
                qualifier=preorder_date,
                category="hardware_products",
                trusted=True,
            )

    historical_auction_scope = f"{title_text}. {_short_lead_scope(lead, sentences=1, limit=420)}"
    historical_actor = (
        "steve-jobs"
        if re.search(r"\bsteve jobs\b|乔布斯", historical_auction_scope)
        else ""
    )
    artifact_patterns = (
        ("science-project", r"\bscience (?:fair )?project\b|科学(?:展览|实验|展会)?项目"),
        ("business-card", r"\bbusiness card\b|名片"),
        ("signed-letter", r"\bsigned (?:fan )?letter\b|签名.{0,8}信(?:件)?"),
        ("apple-1", r"\bapple[- ]?1\b|apple-1|苹果一号"),
        ("prototype", r"\bprototype\b|原型机"),
    )
    historical_artifact = next(
        (
            name
            for name, pattern in artifact_patterns
            if re.search(pattern, historical_auction_scope)
        ),
        "",
    )
    historical_auction_action = bool(
        historical_actor
        and historical_artifact
        and re.search(
            r"\b(?:auction(?:ed)?|sells?|sold)\b|(?:拍卖|成交|落槌)",
            historical_auction_scope,
        )
    )
    if historical_auction_action:
        add_claim(
            f"apple-history-{historical_actor}-{historical_artifact}",
            "auction-sale",
            category="hardware_products",
            trusted=True,
        )

    mac_mini_scope = f"{title_text} {_normalized(lead)[:520]}"
    if "mac-mini" in identity.title_products:
        has_unfulfilled_or_recent_status = bool(
            re.search(
                r"\b(?:pending|recent|unfulfilled)\b|"
                r"\b(?:has|have)\s+(?:yet|not)\s+to\s+ship\b|"
                r"\bnot\s+yet\s+shipped\b|"
                r"(?:尚未|还未|未).{0,8}发货|待发货|近期",
                mac_mini_scope,
            )
        )
        has_order_subject = bool(
            re.search(r"\borders?\b|(?:订单|订购)", mac_mini_scope)
            or has_unfulfilled_or_recent_status
            and re.search(
                r"\b(?:customers?|purchases?|buyers?)\b|(?:客户|用户|网友|买家)",
                mac_mini_scope,
            )
        )
        has_free_terms = _contains(
            mac_mini_scope,
            "for free",
            "free upgrade",
            "at no additional cost",
            "no additional cost",
            "without a price increase",
            "at no charge",
            "price unchanged",
            "免费",
            "无需额外付费",
            "不会产生任何额外费用",
            "价格不变",
        )
        has_upgrade_action = _contains(
            mac_mini_scope,
            "upgrade",
            "upgrading",
            "replace",
            "replacing",
            "replaced",
            "升级",
            "更换",
            "替换",
        )
        pending_order_upgrade = bool(
            has_order_subject
            and has_unfulfilled_or_recent_status
            and has_free_terms
            and has_upgrade_action
        )
        if pending_order_upgrade:
            add_claim(
                "mac-mini",
                "pending-order-free-upgrade",
                category="hardware_products",
                trusted=True,
            )

        display_capability = bool(
            _contains(
                title_text,
                "external display",
                "external displays",
                "display support",
                "外接显示",
                "显示能力",
            )
            and (
                re.search(r"\b(?:\d+k|\d{2,3}\s*hz)\b", title_text)
                or _contains(title_text, "support", "supports", "支持")
            )
        )
        if display_capability:
            add_claim(
                "mac-mini",
                "external-display-capability",
                category="hardware_products",
                trusted=True,
            )

        preorder_launch = bool(
            re.search(r"\bpre[- ]?orders?\b|(?:接受|开启|开放|开始).{0,8}预购|今日预购", title_text)
        )
        if preorder_launch:
            add_claim(
                "mac-mini",
                "retail-preorder",
                category="hardware_products",
                trusted=True,
            )

        current_price_change = bool(
            re.search(
                r"\b(?:price|prices|pricing)\b.{0,28}\b(?:rise|rises|rose|increase[sd]?|hike[sd]?)\b|"
                r"\b(?:raise[sd]?|increase[sd]?|hike[sd]?)\b.{0,28}\b(?:price|prices|pricing)\b|"
                r"(?:涨到|涨至|涨为|售价升至|起售价升至|价格升至).{0,12}\d|"
                r"(?:涨价|提价|上调价格|上调售价)",
                title_text,
            )
        )
        if current_price_change and not pending_order_upgrade:
            add_claim(
                "mac-mini",
                "retail-price-change",
                category="hardware_products",
                trusted=True,
            )

    component_leak_scope = f"{title_text} {_normalized(lead)[:420]}"
    if "foldable-iphone" in identity.title_products and _contains(
        component_leak_scope,
        "motherboard",
        "motherboards",
        "logic board",
        "logic boards",
        "主板",
        "逻辑板",
    ) and _contains(
        component_leak_scope,
        "leak",
        "leaked",
        "leakers",
        "purported",
        "show off",
        "shown",
        "曝光",
        "泄露",
        "流出",
        "疑似",
    ):
        add_claim(
            "foldable-iphone",
            "component-leak",
            qualifier="logic-board",
            category="hardware_products",
            trusted=True,
        )

    if "consumer-purchase-intent" in identity.title_components:
        product_subjects = sorted(identity.title_products)
        percentage_match = re.search(
            r"(?<!\d)(\d+(?:\.\d+)?)\s*%",
            title_text,
        )
        if product_subjects and percentage_match:
            interest_value = float(percentage_match.group(1))
            negative_interest = bool(
                re.search(
                    r"\b(?:aren['’]?t|are\s+not|not|no)\s+(?:at\s+all\s+)?interested\b|"
                    r"\bno\s+interest\b|(?:没兴趣|不感兴趣|无意购买|没有兴趣)",
                    title_text,
                )
            )
            if negative_interest:
                interest_value = max(0.0, 100.0 - interest_value)
            normalized_interest = (
                str(int(interest_value))
                if interest_value.is_integer()
                else f"{interest_value:.2f}".rstrip("0").rstrip(".")
            )
            add_claim(
                product_subjects[0],
                "consumer-purchase-intent-survey",
                qualifier=f"positive-interest-{normalized_interest}",
                category="hardware_products",
                trusted=True,
            )

    wallet_documents = sorted(
        component.removeprefix("wallet-document:")
        for component in identity.title_components
        if component.startswith("wallet-document:")
    )
    if "apple-wallet" in identity.title_products and wallet_documents:
        wallet_action = (
            "regional-availability"
            if _contains(
                title_text,
                "launches in",
                "launched in",
                "new state",
                "available in",
                "上线",
                "新增支持",
                "成为第",
            )
            else "document-feature-change"
        )
        for wallet_document in wallet_documents:
            add_claim(
                f"apple-wallet-{wallet_document}",
                wallet_action,
                category="software_systems",
                trusted=True,
            )

    spotlight_support_guidance = bool(
        "spotlight-index-preparation" in identity.components
        and _contains(
            text,
            "support document",
            "support article",
            "apple explains",
            "apple says",
            "支持文档",
            "苹果回应",
            "苹果解释",
        )
        and _contains(text, "index", "indexing", "索引")
    )
    if spotlight_support_guidance:
        add_claim(
            "spotlight-index-preparation",
            "support-guidance-publication",
            category="software_systems",
            trusted=True,
        )

    apple_support_ai_rollout = bool(
        _contains(
            text,
            "apple support",
            "support phone line",
            "apl-care",
            "苹果支持热线",
            "苹果客服热线",
        )
        and _contains(
            text,
            "generative ai assistant",
            "ai voice assistant",
            "ai assistant",
            "生成式 ai 助手",
            "ai 语音助手",
        )
        and _contains(
            text,
            "rolling out",
            "now uses",
            "now answers",
            "now connects",
            "connects you with",
            "routes calls to",
            "available",
            "上线",
            "启用",
            "接听",
        )
    )
    if apple_support_ai_rollout:
        add_claim(
            "apple-support",
            "generative-ai-assistant-rollout",
            category="software_systems",
            trusted=True,
        )

    genlock_capability = bool(
        "genlock" in identity.components
        and identity.products & {"mac", "mac-mini", "mac-studio", "mac-pro", "macbook"}
        and _contains(
            text,
            "adds genlock",
            "add genlock",
            "genlock support",
            "support genlock",
            "支持 genlock",
            "新增 genlock",
        )
    )
    if genlock_capability:
        add_claim(
            "apple-mac-genlock",
            "capability-support",
            category="hardware_products",
            trusted=True,
        )

    store_app_assistant = bool(
        _contains(claim_evidence, "apple store app", "apple store 应用")
        and _contains(
            claim_evidence,
            "shopping assistant",
            "virtual assistant",
            "ai assistant",
            "购物助手",
            "虚拟助手",
            "ai 助手",
        )
        and _contains(
            claim_evidence,
            "preview",
            "testing",
            "rolling out",
            "rollout",
            "available",
            "上线",
            "测试",
            "预览",
            "开放",
        )
    )
    if store_app_assistant:
        add_claim(
            "apple-store-app",
            "shopping-assistant-preview",
            category="software_systems",
            trusted=True,
        )

    safari_feature_set = bool(
        re.search(r"\bios\s*(\d{1,2})(?:\.\d+){0,2}\b", claim_evidence)
        and _contains(claim_evidence, "safari")
        and _contains(
            title_text,
            "features",
            "new in safari",
            "safari changes",
            "safari feature",
            "safari 浏览器前瞻",
            "safari 前瞻",
            "safari 新功能",
            "safari 功能",
        )
    )
    if safari_feature_set:
        ios_generation = re.search(r"\bios\s*(\d{1,2})", claim_evidence).group(1)
        add_claim(
            f"ios-{ios_generation}-safari",
            "feature-set",
            category="software_systems",
            trusted=True,
        )

    executive_transition_interview = bool(
        re.search(
            r"\b(?:ceo|chief executive|tim cook|john ternus)\b|"
            r"(?:首席执行官|库克|特努斯|ceo)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:interview|reflects?|looks?\s+back|discusses?\s+(?:his|her)\s+legacy)\b|"
            r"(?:接受采访|专访|回顾|谈及).{0,24}(?:经历|任期|遗产|管理)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:before\s+(?:leaving|stepping\s+down)|final\s+days?)\b|"
            r"(?:卸任前|离任前|交接前)",
            title_text,
            re.I,
        )
    )
    if executive_transition_interview:
        add_claim(
            "apple-leadership",
            "transition-interview",
            category="software_systems",
            trusted=True,
        )

    leadership_transition = bool(
        not executive_farewell
        and not executive_transition_interview
        and (
            (
                _contains(title_text, "tim cook", "库克")
                and _contains(
                    title_text,
                    "step down",
                    "steps down",
                    "farewell",
                    "going away",
                    "replaced steve jobs",
                    "卸任",
                    "告别",
                    "欢送",
                    "接任",
                    "继任",
                    "take over",
                )
            )
            or (
                identity.scope == "apple-direct"
                and re.search(r"ceo|首席执行官", title_text, re.I)
                and re.search(
                    r"\b(?:assume(?:s|d|ing)?|become(?:s|ing)?|start(?:s|ing)?\s+as|"
                    r"succeed(?:s|ed|ing)?|take(?:s|n|ing)?\s+over|"
                    r"is\s+now(?:\s+apple['’]?s)?(?:\s+the)?\s+ceo)\b|"
                    r"(?:上任|就任|出任|接任|继任|接棒|正式履职|正式出任)",
                    title_text,
                    re.I,
                )
            )
        )
    )
    if leadership_transition:
        add_claim(
            "apple-leadership",
            "ceo-transition",
            category="software_systems",
            trusted=True,
        )
    if (
        first_executive_employee_memo
        or inbox_accessory_policy_denial
        or executive_profile_asset_update
        or executive_social_account
        or official_follow_change
    ):
        event_keys.discard("primary-claim:apple-leadership:ceo-transition")
        separation.discard("primary-claim-predicate:ceo-transition")
        if inbox_accessory_policy_denial:
            category_hint = "hardware_products"
        else:
            category_hint = "software_systems"

    transit_card_subject = _named_transit_card_subject(title_text) or _named_transit_card_subject(text)
    transit_card_availability = bool(
        transit_card_subject
        and _contains(text, "apple wallet", "苹果钱包", "iphone")
        and _contains(
            text,
            "available",
            "availability",
            "add",
            "support",
            "launch",
            "上线",
            "添加",
            "支持",
            "推出",
            "开通",
        )
    )
    if transit_card_availability:
        add_claim(
            f"apple-wallet-transit-card:{transit_card_subject}",
            "availability",
            category="software_systems",
            trusted=True,
        )

    hardware_products = identity.title_products & {
        "airpods",
        "apple-home-hub",
        "apple-tv-hardware",
        "apple-watch",
        "beats",
        "foldable-iphone",
        "homepod",
        "imac",
        "ipad",
        "ipad-air",
        "ipad-mini",
        "ipad-pro",
        "iphone",
        "mac",
        "mac-mini",
        "mac-pro",
        "mac-studio",
        "macbook",
        "vision-pro",
    }
    projected_roadmap_title = bool(
        re.fullmatch(r"apple\s+.+\s+roadmap\s+update", title_text)
    )
    launch_claim_scope = text if projected_roadmap_title else title_text
    launch_subjects = _reported_hardware_launch_subjects(launch_claim_scope, identity)
    explicit_launch_timing_report = bool(
        len(hardware_products) == 1
        and re.search(
            r"\b(?:release|launch|shipping|availability)\s+(?:timing|window|date)\b|"
            r"(?:发售|上市|开售|出货).{0,14}(?:时间|窗口|日期)|"
            r"(?:预计|预估|据称|报道称).{0,20}(?:本月|下月|\d{1,2}\s*月|20\d{2})"
            r".{0,16}(?:发售|上市|开售|出货)",
            title_text,
            re.I,
        )
        and re.search(
            r"\b(?:next\s+week|next\s+month|in\s+(?:september|october)|"
            r"by\s+(?:late\s+)?(?:september|october)|20\d{2})\b|"
            r"(?:本月|下月|\d{1,2}\s*月|20\d{2}\s*年)",
            claim_evidence,
            re.I,
        )
    )
    if explicit_launch_timing_report:
        launch_subjects |= hardware_products
    if (
        projected_roadmap_title
        and len(hardware_products) == 1
        and re.search(
            r"\b(?:expected|scheduled|reported|reportedly|could|will|plans? to)\b"
            r".{0,36}\b(?:launch|release|ship|arrive|debut|announce)\b|"
            r"(?:据称|报道称|消息称|有望|预计|计划|最快|届时).{0,36}"
            r"(?:发布|推出|亮相|上市)",
            text,
            re.I,
        )
    ):
        launch_subjects |= hardware_products
    for launch_subject in sorted(launch_subjects):
        add_claim(
            launch_subject,
            "reported-launch-window",
            category="hardware_products",
            trusted=True,
        )

    concrete_schedule_date = bool(
        re.search(
            r"\b(?:september|october)\s+\d{1,2}\b|"
            r"\b\d{1,2}/\d{1,2}\b|"
            r"\d{1,2}\s*月\s*\d{1,2}\s*日",
            claim_evidence,
        )
    )
    schedule_reporting_signal = bool(
        re.search(
            r"\b(?:according to|reports?|reported|published|claims?|sources? say|bloomberg|gurman|"
            r"leaker|leaks?|rumou?rs?)\b|"
            r"(?:据.{0,20}(?:报道|消息|透露)|报道称|消息称|爆料|多方消息|多方爆料)",
            claim_evidence,
        )
        or concrete_schedule_date
    )
    event_schedule_subject = bool(
        _apple_event_schedule_title(title_text)
        and not _apple_event_invitation_interpretation_context(title, lead)
        and schedule_reporting_signal
        and _contains(
            claim_evidence,
            "when",
            "date",
            "take place",
            "september",
            "9月",
            "定档",
            "举办",
            "举行",
            "邀请函",
        )
    )
    event_schedule_period = "annual"
    if re.search(r"\b(?:september|october)\b|(?:9|10)\s*月", claim_evidence):
        event_schedule_period = "fall"
    elif re.search(r"\b(?:march|april)\b|(?:3|4)\s*月", claim_evidence):
        event_schedule_period = "spring"
    if event_schedule_subject:
        add_claim(
            f"apple-iphone-{event_schedule_period}-event",
            "schedule-forecast",
            category="hardware_products",
            trusted=True,
        )

    external_product_evaluation = bool(
        hardware_products
        and re.search(
            r"\b(?:people|testers?|users?)\b.{0,55}"
            r"(?:outside (?:of )?apple|who(?:'ve| have) used|early|external)|"
            r"\b(?:early|external)\s+testers?\b|"
            r"\b(?:outside (?:of )?apple|early|external)\b.{0,55}"
            r"(?:used|tested|handled|hands-on|feedback|impressions?)|"
            r"(?:苹果)?外部.{0,35}(?:体验|使用|上手|测试)|"
            r"(?:早期|外部)(?:体验者|测试者|用户).{0,35}(?:评价|反馈|体验)|"
            r"(?:上手体验|体验反馈).{0,30}(?:评价|好评|短板|缺少)",
            claim_evidence,
            re.I,
        )
    )
    if external_product_evaluation:
        for product in sorted(hardware_products):
            add_claim(
                product,
                "external-product-evaluation",
                category="hardware_products",
                trusted=direct_title_subject,
            )

    retail_home_launch_preparation = bool(
        re.search(r"\b(?:apple\s+)?(?:retail\s+)?stores?\b|(?:苹果)?(?:零售店|门店)", title_text)
        and re.search(
            r"\b(?:prepar(?:e|es|ed|ing|ation)?|rearrang(?:e|es|ed|ing)?|"
            r"layout|display|merchandis(?:e|es|ed|ing)?|refresh(?:es|ed|ing)?|changes?)\b|"
            r"(?:准备|调整|重组|改版|布局|陈列|展区)",
            title_text,
        )
        and re.search(
            r"\b(?:home\s+products?|smart[- ]home|homepod|apple\s+tv)\b|"
            r"(?:家庭设备|家居产品|智能家居|homepod|apple\s*tv)",
            claim_evidence,
        )
    )
    if retail_home_launch_preparation:
        add_claim(
            "apple-retail-home",
            "store-layout-launch-preparation",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    retrospective_asset_recap = _retrospective_explainer_without_new_action(
        title_text,
        claim_evidence,
    )
    beta_asset_disclosure = bool(
        direct_title_subject
        and not retrospective_asset_recap
        and re.search(
            r"\b(?:beta|release candidate|rc|system update)\b|(?:测试版|候选版|系统更新)",
            claim_evidence,
        )
        and re.search(
            r"\b(?:accident(?:al|ally)|unintended|mistakenly|leak(?:s|ed)?|"
            r"expos(?:e|es|ed)|included|bundled)\b|(?:意外|误|泄露|曝光|误带|包含)",
            claim_evidence,
        )
        and re.search(
            r"\b(?:product plans?|product identifiers?|product videos?|demo videos?|"
            r"future products?|unannounced product information|assets?)\b|"
            r"(?:产品计划|产品标识|产品视频|演示视频|未发布产品|未公布产品信息|"
            r"未公开(?:功能|产品资料)|资源)",
            claim_evidence,
        )
    )
    if beta_asset_disclosure:
        add_claim(
            "apple-system-build",
            "unintended-product-asset-disclosure",
            category="software_systems",
            trusted=True,
        )

    current_hardware_details_report = bool(
        direct_title_subject
        and hardware_products
        and identity.content_form == "news"
        and re.search(
            r"\b(?:hidden|new|additional|technical)?\s*"
            r"(?:details?|specifications?|specs?|configurations?)\b|"
            r"(?:隐藏|新增|更多|技术)?(?:细节|规格|配置)(?:曝光|披露|公开)?",
            title_text,
            re.I,
        )
    )
    if current_hardware_details_report:
        generation = next(
            (
                component.removeprefix("apple-silicon-generation:")
                for component in identity.components
                if component.startswith("apple-silicon-generation:")
            ),
            "",
        )
        for product in sorted(hardware_products):
            add_claim(
                product,
                "technical-details-disclosure",
                qualifier=generation,
                category="hardware_products",
                trusted=True,
            )

    current_hardware_refresh_report = bool(
        direct_title_subject
        and hardware_products
        and not any(key.startswith("primary-claim:") for key in event_keys)
        and any(
            component.startswith("apple-silicon-generation:")
            for component in identity.title_components
        )
        and identity.content_form == "news"
        and re.search(
            r"\b(?:will|expected|coming|launch|release|ship|before the end of|this year)\b|"
            r"(?:将|预计|有望|即将|年内|年底前|今年).{0,24}(?:推出|发布|上市|到来)?",
            claim_evidence,
        )
    )
    if current_hardware_refresh_report:
        generation = next(
            (
                component.removeprefix("apple-silicon-generation:")
                for component in identity.components
                if component.startswith("apple-silicon-generation:")
            ),
            "",
        )
        for product in sorted(hardware_products):
            add_claim(
                product,
                "generation-product-refresh",
                qualifier=generation,
                category="hardware_products",
                trusted=True,
            )

    supplier_component_classes = {
        component.removeprefix("component-supplier-sourcing:")
        for component in identity.title_components
        if component.startswith("component-supplier-sourcing:")
    }
    if supplier_component_classes and direct_title_subject:
        if re.search(
            r"\b(?:block|ban|stop|reject|deny|restriction)\b|"
            r"(?:叫停|阻止|禁止|否决|拒绝|限制)",
            title_text,
        ):
            sourcing_predicate = "component-procurement-policy-block"
        elif re.search(
            r"\b(?:allow|approve|approval|clear|authorize)\b|"
            r"(?:放行|允许|批准|授权|获准)",
            title_text,
        ):
            sourcing_predicate = "component-procurement-policy-approval"
        elif re.search(
            r"\b(?:priority supply|priority allocation|orders? booked|allocation)\b|"
            r"(?:优先供货|优先拿货|订单排至|订单已排至|分配)",
            title_text,
        ):
            sourcing_predicate = "component-order-allocation"
        elif re.search(
            r"\b(?:talks?|negotiat|bidding)\b|(?:洽谈|谈判|议价|压价)",
            title_text,
        ):
            sourcing_predicate = "component-supplier-negotiation"
        else:
            sourcing_predicate = "component-procurement"
        for component_class in sorted(supplier_component_classes):
            add_claim(
                f"apple-{component_class}-sourcing",
                sourcing_predicate,
                category="hardware_products",
                trusted=True,
            )

    apple_music_ai_label_action = bool(
        "apple-music" in identity.products
        and _contains(
            claim_evidence,
            "ai-generated",
            "ai generated",
            "ai content",
            "artificial intelligence",
            "机器生成",
            "ai 生成",
        )
        and _contains(
            claim_evidence,
            "label",
            "labels",
            "labeled",
            "labelled",
            "transparency tag",
            "disclosure",
            "标注",
            "标签",
            "披露",
        )
        and _contains(
            claim_evidence,
            "require",
            "required",
            "mandatory",
            "must",
            "will soon",
            "强制",
            "要求",
            "必须",
            "年底",
        )
    )
    if apple_music_ai_label_action:
        add_claim(
            "apple-music-ai-content",
            "mandatory-disclosure-label",
            category="software_systems",
            trusted=direct_title_subject or identity.scope == "apple-direct",
        )

    workforce_reduction = bool(
        re.search(r"\bapple(?:['’]s)?\b|苹果", title_text)
        and _contains(
            claim_evidence,
            "layoff",
            "layoffs",
            "laid off",
            "lays off",
            "job cuts",
            "cuts jobs",
            "cutting jobs",
            "laying off",
            "trims staff",
            "trimming staff",
            "guts",
            "裁员",
            "裁撤",
            "裁减",
            "裁掉",
        )
    )
    if workforce_reduction:
        workforce_subject = ""
        if (
            identity.products & {"vision-pro", "visionos"}
            or _contains(
            claim_evidence,
            "vision group",
            "vision products",
            "vr team",
            "vision 业务组",
            "vr 研发团队",
            )
        ) or (
            _contains(claim_evidence, "vr", "vision")
            and _contains(
                claim_evidence,
                "team",
                "group",
                "division",
                "department",
                "organization",
                "团队",
                "部门",
                "业务组",
                "组织",
            )
        ):
            workforce_subject = "apple-vision-group"
        else:
            direct_units = sorted(
                identity.title_products
                or {
                    product
                    for product in identity.products
                    if product not in {"apple", "ios", "macos"}
                }
            )
            if len(direct_units) == 1:
                workforce_subject = f"apple-{direct_units[0].removeprefix('apple-')}-group"
        if workforce_subject:
            add_claim(
                workforce_subject,
                "workforce-reduction",
                category="hardware_products",
                trusted=True,
            )

    iphone_launch_schedule = bool(
        "iphone" in identity.products
        and _contains(
            text,
            "won't launch",
            "will not launch",
            "missing from",
            "pushed to",
            "delayed until",
            "launch schedule",
            "缺席",
            "不会发布",
            "延后",
            "推迟",
            "发布节奏",
        )
        and _contains(
            text,
            "september",
            "next month",
            "early 20",
            "first quarter",
            "march",
            "9 月",
            "9月",
            "明年",
            "第一季度",
            "3 月",
            "3月",
        )
    )
    if iphone_launch_schedule:
        model_subjects = sorted(
            component
            for component in identity.title_components
            if component.startswith("iphone-model:")
        )
        generation_subjects = sorted(
            component
            for component in identity.title_components
            if component.startswith("product-generation:iphone-")
        )
        launch_subject = next(iter(model_subjects or generation_subjects), "iphone")
        add_claim(
            launch_subject,
            "launch-schedule-change",
            category="hardware_products",
            trusted=direct_title_subject or identity.scope == "apple-direct",
        )

    market_result_keys = _measured_apple_market_result_keys(title, lead, evidence)
    if market_result_keys:
        event_keys |= market_result_keys
        separation.add("primary-claim-predicate:measured-apple-market-result")
        market_scopes = {
            tuple(key.split(":")[1:4])
            for key in market_result_keys
            if key.startswith("structured-market-result:")
        }
        market_regions = {region for _firm, region, _period in market_scopes}
        market_firms = {firm for firm, _region, _period in market_scopes}
        if len(market_regions) == 1 and len(market_firms) == 1:
            separation.add(
                "market-report-scope:"
                f"{next(iter(market_firms))}:{next(iter(market_regions))}"
            )
        category_hint = "hardware_products"
        trusted_direct_action = True

    title_products = sorted(identity.title_products)
    production_subjects = list(title_products)
    if re.search(
        r"\b(?:foldable|folding)\s+(?:apple\s+)?iphone\b|"
        r"(?:折叠屏|折叠式)\s*iphone|iphone\s*(?:ultra|fold)",
        text,
    ):
        production_subjects = ["foldable-iphone"]
    production_volume = re.search(
        r"(?<!\d)(\d{1,4}(?:\.\d+)?)\s*(million|万)\s*(?:units?|台)?",
        text,
    )
    production_action = bool(
        identity.actions & {"supply-production"}
        or _contains(
            text,
            "production target",
            "production goal",
            "orders to",
            "order target",
            "units this year",
            "产量目标",
            "生产目标",
            "年产目标",
            "订单上调",
        )
    )
    if len(production_subjects) == 1 and production_volume and production_action:
        value = float(production_volume.group(1))
        multiplier = 1_000_000 if production_volume.group(2) == "million" else 10_000
        normalized_units = str(int(value * multiplier))
        add_claim(
            production_subjects[0],
            "production-target",
            qualifier=f"units-{normalized_units}",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    if re.search(r"\bsiri\s+remote\b|siri\s*remote\s*遥控器", text) and _contains(
        text,
        "new",
        "next",
        "upgraded",
        "upgrade",
        "upcoming",
        "code hints",
        "identifier",
        "新一代",
        "新款",
        "升级款",
        "代码",
        "标识",
        "曝光",
    ):
        add_claim(
            "siri-remote",
            "hardware-refresh",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    if (
        "apple-home-hub" in identity.title_products
        and _contains(
            text,
            "widget gallery",
            "smart stack",
            "widget support",
            "widget mirroring",
            "小组件图库",
            "小组件库",
            "智能叠放",
            "小组件镜像",
            "支持小组件",
            "搭载小组件",
        )
    ):
        add_claim(
            "apple-home-hub",
            "widget-capability",
            category="software_systems",
            trusted=direct_title_subject,
        )

    cashback_percent = re.search(
        r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%[^。.!?]{0,40}"
        r"(?:daily cash|cash\s*back|cashback|返现)|"
        r"(?:daily cash|cash\s*back|cashback|返现)[^。.!?]{0,40}"
        r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%",
        text,
    )
    if "apple-card" in identity.title_products and cashback_percent:
        percentage = cashback_percent.group(1) or cashback_percent.group(2)
        add_claim(
            "apple-card",
            "cashback-offer",
            qualifier=f"percent-{percentage}",
            category="software_systems",
            trusted=direct_title_subject,
        )

    app_store_subject = (
        "app-store" in identity.title_products
        or _contains(text, "app store", "应用商店")
        or (
            re.match(r"^(?:apple|苹果)", title_text)
            and _contains(
                text,
                "business terms for apps",
                "commercial terms for apps",
                "应用商业条款",
            )
        )
    )
    app_store_distribution_policy = bool(
        _contains(text, "app store", "应用商店", "app marketplaces", "应用市场")
        and _contains(
            text,
            "alternative app marketplace",
            "alternative app marketplaces",
            "third-party app marketplace",
            "third-party app marketplaces",
            "web distribution",
            "external links",
            "third-party payment",
            "third-party platforms",
            "第三方应用商店",
            "替代应用市场",
            "网页分发",
            "外部链接",
            "第三方支付",
            "第三方平台",
        )
        and _contains(
            text,
            "change",
            "changes",
            "agreement",
            "allow",
            "adding",
            "调整",
            "落地",
            "协议",
            "允许",
            "开放",
        )
    )
    if app_store_distribution_policy:
        region_values = {
            region for region in regions if region and region != "multi-region"
        }
        if _contains(text, "brazil", "巴西"):
            region_values.add("brazil")
        qualifier = ",".join(sorted(region_values)) or "global"
        add_claim(
            "app-store",
            "distribution-payment-policy-change",
            qualifier=qualifier,
            category="software_systems",
            trusted=direct_title_subject or identity.scope == "apple-direct",
        )
    app_store_terms = bool(
        app_store_subject
        and _contains(
            claim_evidence,
            "terms",
            "rules",
            "app store changes",
            "fees",
            "fee structure",
            "external payments",
            "business terms",
            "商业条款",
            "应用商业条款",
            "新规",
            "费率",
            "收费",
            "收费结构",
            "外部支付",
        )
        and _contains(
            claim_evidence,
            "overhaul",
            "change",
            "changes",
            "changed",
            "updated",
            "revised",
            "adjusted",
            "new",
            "lower",
            "unified",
            "settle",
            "settles",
            "squashes",
            "announces",
            "调整",
            "变更",
            "新条款",
            "新规",
            "降低",
            "统一",
            "宣布",
        )
        and (
            _contains(claim_evidence, "european union", " eu ", "europe", "欧盟", "欧洲")
            or bool({region for region in regions if region and region != "multi-region"})
        )
    )
    if app_store_terms:
        region_values = {
            region for region in regions if region and region != "multi-region"
        }
        if _contains(claim_evidence, "european union", " eu ", "europe", "欧盟", "欧洲"):
            region_values.add("europe")
        qualifier = ",".join(sorted(region_values)) or "global"
        add_claim(
            "app-store",
            "commercial-terms-change",
            qualifier=qualifier,
            category="software_systems",
            trusted=True,
        )

    app_store_commission_context = bool(
        _contains(claim_evidence, "app store", "应用商店")
        and _contains(
            claim_evidence,
            "commission revenue",
            "commission income",
            "commission",
            "佣金收入",
            "佣金",
        )
    )
    app_store_commission_pressure_title = bool(
        _contains(
            title_text,
            "commission revenue",
            "app store revenue",
            "commission income",
            "make any commission",
            "regulated away",
            "佣金收入",
            "服务收入",
            "佣金",
        )
        or (
            _contains(title_text, "services business", "service revenue", "服务业务", "服务收入")
            and app_store_commission_context
        )
    )
    commission_revenue_pressure = bool(
        (app_store_subject or (direct_title_subject and app_store_commission_context))
        and app_store_commission_pressure_title
        and _contains(
            claim_evidence,
            "down",
            "decline",
            "declining",
            "fall",
            "falling",
            "danger",
            "may not",
            "pressure",
            "erosion",
            "下降",
            "下滑",
            "冲击",
            "侵蚀",
            "无法收取",
            "可能不再",
        )
    )
    if commission_revenue_pressure:
        add_claim(
            "app-store",
            "commission-revenue-pressure",
            category="software_systems",
            trusted=direct_title_subject,
        )
        if (
            _contains(
                claim_evidence,
                "regulator",
                "regulatory",
                "regulation",
                "反垄断",
                "监管",
            )
            and _contains(
                claim_evidence,
                "services business",
                "services growth",
                "service revenue",
                "services revenue",
                "服务业务",
                "服务收入",
            )
        ):
            add_claim(
                "apple-services",
                "regulatory-financial-impact",
                category="software_systems",
                trusted=direct_title_subject,
            )

    if (
        not mac_intel_support_removal
        and _contains(text, "app store", "应用商店")
        and _contains(
            title_text,
            "pulls",
            "pulled",
            "removes",
            "removed",
            "delists",
            "delisted",
            "下架",
            "移除",
            "撤下",
        )
    ):
        add_claim(
            "app-store",
            "app-enforcement-removal",
            category="software_systems",
            trusted=direct_title_subject,
        )

    airpods_generation = re.search(
        r"\bairpods\s*(\d{1,2})\b|airpods\s*第?\s*(\d{1,2})\s*代",
        title_text,
    )
    if airpods_generation and _contains(
        text,
        "model",
        "models",
        "identifier",
        "identifiers",
        "referenced",
        "code",
        "型号",
        "标识",
        "代码",
        "曝光",
    ):
        generation = airpods_generation.group(1) or airpods_generation.group(2)
        add_claim(
            f"airpods-generation-{generation}",
            "model-identifier-leak",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    camera_airpods_title_action = bool(
        (
            direct_title_subject
            or re.match(r"^airpods?\b", title_text)
        )
        and _contains(
            title_text,
            "leak",
            "demo",
            "code",
            "rumor",
            "learned",
            "detect",
            "capture",
            "delay",
            "delayed",
            "曝光",
            "演示",
            "代码",
            "传闻",
            "功能揭晓",
            "延期",
            "延至",
        )
    )
    if (
        "airpods" in identity.title_products
        and camera_airpods_title_action
        and _contains(
            text,
            "leak",
            "leaked",
            "demo",
            "video",
            "code",
            "codename",
            "launch",
            "delay",
            "delayed",
            "on track",
            "naming",
            "named",
            "rumor",
            "rumors",
            "learned",
            "detect people",
            "capture",
            "曝光",
            "演示",
            "视频",
            "代码",
            "代号",
            "推出",
            "延期",
            "延至",
            "命名",
        )
        and (
            re.search(
                r"\bcamera(?:-equipped)?\s+airpods?\b|"
                r"\bairpods?\b[^。.!?]{0,28}\bcameras?\b",
                text,
            )
            or re.search(
                r"(?:摄像头|相机)[^。！？]{0,20}airpods|"
                r"airpods[^。！？]{0,20}(?:摄像头|相机)",
                text,
            )
        )
    ):
        add_claim(
            "camera-airpods",
            "product-capability-leak",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    macbook_generation = re.search(r"\b(m\d)\s+macbook\s+pro\b", text)
    if (
        macbook_generation
        and _contains(
            claim_evidence,
            "gpu",
            "memory bandwidth",
            "vapor chamber",
            "thermal",
            "内存带宽",
            "均热板",
            "散热",
        )
    ):
        add_claim(
            f"{macbook_generation.group(1)}-macbook-pro",
            "product-specification-report",
            category="hardware_products",
            trusted=True,
        )

    apple_pay_rollout = bool(
        "apple-pay" in identity.products
        and _contains(
            text,
            "begin accepting",
            "launching apple pay",
            "apple pay rollout",
            "adding apple pay",
            "apple pay is coming",
            "support apple pay",
            "支持 apple pay",
            "接入 apple pay",
            "开始支持 apple pay",
        )
    )
    if apple_pay_rollout:
        actor_aliases = (
            ("walmart", ("walmart", "沃尔玛")),
            ("sams-club", ("sam's club", "sams club", "山姆会员商店", "山姆")),
        )
        actors = {
            canonical
            for canonical, aliases in actor_aliases
            if _contains(text, *aliases)
        }
        retailer = "walmart" if "walmart" in actors else next(iter(actors), "")
        if retailer:
            add_claim(
                f"retailer-{retailer}-apple-pay",
                "platform-rollout",
                category="software_systems",
                trusted=True,
            )

    if (
        "tvos" in identity.title_products
        and "siri" in identity.title_products
        and _contains(
            text,
            "siri ai",
            "siri 条目",
            "siri entry",
            "siri app",
            "siri 应用",
        )
    ):
        add_claim(
            "tvos-siri",
            "ai-capability",
            category="software_systems",
            trusted=direct_title_subject,
        )

    if (
        identity.title_products
        & {"app-store", "apple-music", "apple-tv", "icloud"}
        and (
            _contains(
                title_text,
                "outage",
                "experiencing issues",
                "service issues",
                "service interruption",
                "服务中断",
                "出现故障",
                "服务问题",
                "宕机",
            )
            or re.search(
                r"\b(?:is|are|currently|services?)\s+down\b|"
                r"(?:服务|系统).{0,10}(?:不可用|中断|故障)",
                title_text,
            )
        )
    ):
        add_claim(
            "apple-online-services",
            "service-outage",
            category="software_systems",
            trusted=direct_title_subject,
        )

    if (
        "ipad" in identity.title_products
        and _contains(text, "patent", "专利")
        and _contains(text, "camera control", "相机控制", "相机按键")
    ):
        add_claim(
            "ipad-camera-control",
            "patent-disclosure",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    iphone_model = next(
        (
            component.removeprefix("iphone-model:")
            for component in identity.title_components
            if component.startswith("iphone-model:")
        ),
        "",
    )
    if (
        iphone_model
        and _contains(claim_evidence, "variable aperture", "可变光圈")
        and _contains(claim_evidence, "exclusive", "only", "独占", "独享")
    ):
        add_claim(
            f"iphone-{iphone_model}-camera",
            "exclusive-variable-aperture",
            category="hardware_products",
            trusted=direct_title_subject,
        )

    doj_antitrust_response = bool(
        _contains(text, "department of justice", " doj ", "司法部")
        and _contains(text, "antitrust", "反垄断")
        and _contains(
            title_text,
            "responds",
            "rejects",
            "rebuts",
            "refutes",
            "反驳",
            "驳斥",
            "回应",
        )
    )
    if doj_antitrust_response:
        add_claim(
            "apple-doj-antitrust-case",
            "legal-response",
            category="software_systems",
            trusted=direct_title_subject,
        )

    regulatory_service_impact = bool(
        _contains(text, "antitrust", "regulator", "regulatory", "反垄断", "监管机构")
        and _contains(text, "services business", "service revenue", "服务业务", "服务收入")
        and _contains(
            title_text,
            "erodes",
            "erosion",
            "hits",
            "impact",
            "pressure",
            "侵蚀",
            "冲击",
            "影响",
            "打压",
        )
    )
    if regulatory_service_impact:
        add_claim(
            "apple-services",
            "regulatory-financial-impact",
            category="software_systems",
            trusted=direct_title_subject,
        )

    regulatory_meeting = bool(
        _contains(
            text,
            "virtual meeting",
            "constructive talks",
            "constructive meeting",
            "held talks",
            "举行建设性会谈",
            "建设性虚拟会晤",
            "举行建设性虚拟会晤",
        )
        and _contains(
            text,
            "eu tech chief",
            "european commission",
            "digital markets act",
            " dma ",
            "欧盟科技主管",
            "欧盟委员会",
            "欧盟科技事务负责人",
        )
        and _contains(text, "siri", "ai tools", "ai 工具", "新版 siri")
        and _contains(text, "tim cook", "库克")
    )
    if regulatory_meeting:
        add_claim(
            "apple-eu-ai-interoperability",
            "regulatory-meeting",
            category="software_systems",
            trusted=True,
        )

    award_evidence = f"{title_text}. {_normalized(lead)[:900]}"
    executive_award = bool(
        _contains(award_evidence, "person of the year", "年度人物")
        and _contains(award_evidence, "award", "recognized", "named", "获奖", "授予")
        and _contains(award_evidence, "cannes lions", "戛纳狮子")
        and _contains(award_evidence, "apple tv", "apple music", "苹果服务")
    )
    if executive_award:
        add_claim(
            "apple-services-executive",
            "industry-award",
            category="software_systems",
            trusted=True,
        )

    third_party_app_action = _third_party_platform_app_action(title, lead)
    if third_party_app_action:
        owner, platform, target = third_party_app_action
        add_claim(
            f"third-party-software-{owner}-{target}",
            "platform-software-action",
            qualifier=platform,
            category="software_systems",
            trusted=False,
        )

    home_hub_subject = bool(
        "apple-home-hub" in identity.title_products
        or identity.title_named_subjects & {"homepad", "homehub", "home-hub"}
        or _contains(title_text, "homepad", "home hub", "homehub")
        or (
            re.match(r"^(?:apple(?:'s|’s)?|苹果)", title_text)
            and _contains(title_text, "home automation", "smart home", "家庭自动化", "智能家居")
            and identity.named_subjects & {"homepad", "homehub", "home-hub"}
        )
    )
    if home_hub_subject and _contains(
        claim_evidence,
        "widget gallery",
        "smart stack",
        "widget support",
        "widget mirroring",
        "小组件图库",
        "小组件库",
        "智能叠放",
        "小组件镜像",
        "支持小组件",
        "搭载小组件",
    ) and _contains(claim_evidence, "code", "macos", "代码", "文件"):
        add_claim(
            "apple-home-hub",
            "widget-capability",
            category="software_systems",
            trusted=True,
        )

    home_hub_profile_switching = bool(
        home_hub_subject
        and _contains(claim_evidence, "apple", "苹果", "macos")
        and _contains(
            claim_evidence,
            "user profile",
            "user profiles",
            "profile switching",
            "switch personal profiles",
            "automatic profile switching",
            "switch profiles",
            "profile selection",
            "personal content",
            "different content depending",
            "用户配置",
            "用户资料",
            "个人内容",
            "切换个人配置",
            "切换不同账号",
            "切换账号",
            "切换用户",
            "个人资料切换",
        )
        and _contains(
            claim_evidence,
            "face",
            "facial",
            "camera",
            "ambient sensing",
            "识别人脸",
            "识别面容",
            "摄像头",
            "环境感知",
        )
    )
    if home_hub_profile_switching:
        add_claim(
            "apple-home-hub",
            "identity-personalization",
            category="software_systems",
            trusted=True,
        )

    lifecycle_action = bool(
        _contains(
            claim_evidence,
            "deprecated",
            "deprecates",
            "to be removed",
            "will be removed",
            "being removed",
            "弃用",
            "将移除",
            "未来会移除",
        )
    )
    utility_matches = re.findall(
        r"(?:deprecat(?:e|es|ed|ing)|弃用|标记弃用)[^。.!?]{0,35}?"
        r"(?<![a-z0-9])([a-z][a-z0-9_.+-]{3,30})(?![a-z0-9])",
        claim_evidence,
    )
    if not utility_matches:
        utility_matches = re.findall(
            r"(?<![a-z0-9])([a-z][a-z0-9_.+-]{3,30})(?![a-z0-9])"
            r"\s+(?:is|was|has been|will be)\s+(?:officially\s+)?deprecated\b",
            claim_evidence,
        )
    if not utility_matches:
        utility_matches = re.findall(
            r"(?<![a-z0-9])([a-z][a-z0-9_.+-]{3,30})(?![a-z0-9])"
            r"[^。.!?]{0,35}?(?:to be removed|will be removed|弃用|将移除|未来会移除)",
            claim_evidence,
        )
    utility_candidates = [
        token
        for token in utility_matches
        if token
        not in {
            "apple",
            "deprecated",
            "diskutil",
            "image",
            "macos",
            "removed",
            "tool",
            "utility",
        }
    ]
    if (
        lifecycle_action
        and _contains(claim_evidence, "macos", "ios", "ipados", "watchos", "tvos", "visionos")
        and utility_candidates
    ):
        utility = utility_candidates[0]
        add_claim(
            f"apple-os-utility-{utility}",
            "lifecycle-deprecation",
            category="software_systems",
            trusted=direct_title_subject or _contains(claim_evidence, "apple", "苹果"),
        )

    apple_server_subject = bool(
        _contains(
            claim_evidence,
            "apple's ai server",
            "apple ai server",
            "apple server",
            "private cloud compute server",
            "苹果 ai 服务器",
            "苹果服务器",
            "苹果自研服务器",
        )
    )
    server_hardware_reveal = bool(
        apple_server_subject
        and _contains(
            claim_evidence,
            "first look",
            "inside",
            "internal layout",
            "internal structure",
            "photos show",
            "内部结构",
            "内部布局",
            "首曝",
            "首次曝光",
        )
        and _contains(
            claim_evidence,
            "server",
            "hardware",
            "chassis",
            "rack",
            "2u",
            "服务器",
            "硬件",
            "机架",
            "机箱",
        )
    )
    if server_hardware_reveal:
        add_claim(
            "apple-ai-server",
            "internal-hardware-reveal",
            category="hardware_products",
            trusted=True,
        )

    if (
        "apple-store-app" in identity.products
        and "shopping-assistant" in identity.components
    ):
        category_hint = "software_systems"

    beats_model = re.search(r"\bbeats\s*(\d{2,4})(?!\d)", title_text)
    if beats_model and _contains(
        text,
        "listing",
        "retail",
        "spec",
        "leak",
        "anc",
        "ipx",
        "零售",
        "规格",
        "泄露",
        "曝光",
        "降噪",
        "防水",
    ):
        add_claim(
            f"beats-model-{beats_model.group(1)}",
            "product-specification-leak",
            category="hardware_products",
            trusted=True,
        )

    if re.search(
        r"\b(?:unidentified|unknown|unreleased)\s+(?:apple\s+)?(?:device|product)\s+identifiers?\b|"
        r"(?:未识别|未知|未发布).{0,12}(?:设备|产品).{0,8}(?:标识|型号)|"
        r"(?:设备|产品).{0,8}(?:标识|型号).{0,12}(?:未识别|未知)",
        title_text,
    ) and _contains(text, "macos", "system code", "code", "系统代码", "代码"):
        add_claim(
            "apple-unreleased-device-identifiers",
            "code-disclosure",
            category="hardware_products",
            trusted=True,
        )

    return (
        event_keys,
        boundaries,
        separation,
        category_hint,
        trusted_direct_action,
    )


def _product_anniversary_milestone(title: str) -> tuple[str, str] | None:
    milestone = re.search(
        r"\bturns?\s+(\d{1,3})\b|"
        r"\bmarks?\s+(?:its\s+)?(\d{1,3})(?:st|nd|rd|th)?\s+anniversary\b|"
        r"\bcelebrates?\s+(?:its\s+)?(\d{1,3})(?:st|nd|rd|th)?\s+anniversary\b|"
        r"(?:问世|发布|诞生|迎来|庆祝).{0,10}?(\d{1,3})\s*周年|"
        r"(\d{1,3})\s*周年(?:纪念)?.{0,10}?(?:问世|发布|诞生|迎来|庆祝)",
        title,
    )
    if not milestone:
        return None
    years = next((value for value in milestone.groups() if value), "")
    candidates: list[tuple[int, str]] = []
    for product, aliases in PRODUCT_PATTERNS:
        for alias in aliases:
            position = title.rfind(alias, 0, milestone.end())
            if position >= 0 and milestone.start() - position <= 80:
                candidates.append((position, product))
    if not candidates:
        return None
    _position, product = max(candidates)
    return product, years


def _measured_apple_market_result_keys(
    title: str,
    lead: str,
    evidence: str,
) -> set[str]:
    """Project quantified Apple market results with their report context."""
    title_scope = _normalized(title)
    primary_lead = _primary_assertion_scope("", lead)[1]
    title_or_lead_owns_result = any(
        _contains(scope, "apple", "iphone", "苹果")
        and _contains(
            scope,
            "market share",
            "shipments",
            "sales",
            "best selling",
            "best-selling",
            "份额",
            "出货量",
            "销量",
            "畅销",
            "销量榜",
        )
        for scope in (title_scope, primary_lead)
    )
    if not title_or_lead_owns_result:
        title_or_lead_owns_result = bool(
            _contains(primary_lead, "apple", "iphone", "苹果")
            and re.search(
                r"\b(?:grew|growth|rose|increased|gained|outperformed)\b|"
                r"(?:增长|上升|提升|逆势|扩大)",
                primary_lead,
                re.I,
            )
            and re.search(
                r"(?:apple|iphone|苹果).{0,90}(?:\d+(?:\.\d+)?\s*%|"
                r"market share|shipments|sales|份额|出货量|销量)",
                _normalized(evidence),
                re.I,
            )
        )
    if not title_or_lead_owns_result:
        return set()
    scope = _normalized(". ".join(part for part in (title, lead, evidence) if part))
    firm = next(
        (
            name
            for name, aliases in (
                ("counterpoint", ("counterpoint",)),
                ("canalys", ("canalys",)),
                ("idc", (" idc ", "idc report", "idc 报告")),
                ("omdia", ("omdia",)),
                ("trendforce", ("trendforce",)),
            )
            if _contains(f" {scope} ", *aliases)
        ),
        "",
    )
    if not firm or not _contains(
        scope,
        "market share",
        "shipments",
        "sales",
        "best selling",
        "best-selling",
        "份额",
        "出货量",
        "销量",
        "畅销",
        "销量榜",
    ):
        return set()

    region_aliases = (
        ("europe", ("europe", "european", "欧洲")),
        ("latin-america", ("latin america", "latam", "拉美", "拉丁美洲")),
        ("india", ("india", "印度")),
        ("china", ("china", "中国")),
        ("global", ("global", "worldwide", "world's", "worlds", "全球")),
    )
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?:[。！？]|(?<=[.!?])\s+)", scope)
        if sentence.strip()
    ]
    current_regions: set[str] = set()
    current_period = ""
    current_quarter = ""
    keys: set[str] = set()
    for sentence in sentences:
        sentence_regions = {
            region
            for region, aliases in region_aliases
            if _contains(sentence, *aliases)
        }
        if sentence_regions:
            current_regions = sentence_regions
        period_match = re.search(
            r"(?<!\d)(20\d{2})\s*(?:年\s*)?[- ]?q([1-4])(?!\d)",
            sentence,
        )
        if not period_match:
            period_match = re.search(
                r"(?<!\d)q([1-4])\s*(20\d{2})(?!\d)",
                sentence,
            )
            if period_match:
                current_quarter = f"q{period_match.group(1)}"
                current_period = f"{period_match.group(2)}-q{period_match.group(1)}"
        else:
            current_quarter = f"q{period_match.group(2)}"
            current_period = f"{period_match.group(1)}-q{period_match.group(2)}"
        if not period_match:
            quarter_match = re.search(
                r"\b(first|second|third|fourth) quarter\b|第?([一二三四1234])季度",
                sentence,
            )
            year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", sentence)
            if quarter_match:
                quarter_map = {
                    "first": "1", "second": "2", "third": "3", "fourth": "4",
                    "一": "1", "二": "2", "三": "3", "四": "4",
                }
                raw_quarter = quarter_match.group(1) or quarter_match.group(2)
                current_quarter = f"q{quarter_map.get(raw_quarter, raw_quarter)}"
                if year_match:
                    current_period = f"{year_match.group(1)}-{current_quarter}"
            else:
                compact_quarter = re.search(r"(?<!\d)q([1-4])(?!\d)", sentence)
                if compact_quarter:
                    current_quarter = f"q{compact_quarter.group(1)}"
                    if year_match:
                        current_period = f"{year_match.group(1)}-{current_quarter}"
        if not current_regions or not (current_period or current_quarter):
            continue
        if not _contains(sentence, "apple", "iphone", "苹果"):
            continue
        percentages = {
            value.rstrip("0").rstrip(".") if "." in value else value
            for value in re.findall(
                r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?(?:\s+points?)?)",
                sentence,
            )
        }
        first_place_result = bool(
            re.search(
                r"\b(?:world(?:'s)?|global(?:ly)?)\s+(?:best[- ]selling|top[- ]selling)\b|"
                r"\b(?:topped|led|leads|ranked first|ranks first|number one|no\.\s*1)\b|"
                r"(?:全球)?(?:最畅销|销量第一|排名第一|稳居第一|位居第一|登顶|霸榜)",
                sentence,
            )
        )
        for region in current_regions:
            for percentage in percentages:
                for period in {current_period, current_quarter} - {""}:
                    keys.add(
                        "structured-market-result:"
                        f"{firm}:{region}:{period}:apple-percent:{percentage}"
                    )
            if first_place_result:
                for period in {current_period, current_quarter} - {""}:
                    keys.add(
                        "structured-market-result:"
                        f"{firm}:{region}:{period}:apple-rank:1"
                    )
    return keys


_SOFTWARE_FIRST_PARTY_PRODUCTS = {
    "app-store",
    "apple-arcade",
    "apple-books",
    "apple-card",
    "apple-fitness",
    "apple-intelligence",
    "apple-maps",
    "apple-music",
    "apple-one",
    "apple-pay",
    "apple-sports",
    "apple-store-app",
    "apple-tv",
    "apple-wallet",
    "carplay",
    "icloud",
    "ios",
    "ipados",
    "macos",
    "safari",
    "shazam",
    "siri",
    "tvos",
    "visionos",
    "watchos",
    "xcode",
}

_HARDWARE_FIRST_PARTY_PRODUCTS = {
    "airpods",
    "airtag",
    "apple-glasses",
    "apple-home-hub",
    "apple-power-adapter",
    "apple-watch",
    "beats",
    "foldable-iphone",
    "homepod",
    "imac",
    "ipad",
    "ipad-air",
    "ipad-mini",
    "ipad-pro",
    "iphone",
    "mac",
    "mac-mini",
    "mac-pro",
    "mac-studio",
    "macbook",
    "magic-keyboard",
    "polishing-cloth",
    "vision-pro",
}

_ACTION_EQUIVALENCE = {
    "availability-expansion": "availability-expansion",
    "catalog-expansion": "availability-expansion",
    "commercial-launch": "availability",
    "content-release": "content-release",
    "feature-change": "product-change",
    "official-communication": "official-communication",
    "price-change": "price-change",
    "product-disclosure": "disclosure",
    "product-launch": "availability",
    "product-refresh": "product-change",
    "retail-availability": "availability",
}

_SPECIFIC_FIRST_PARTY_PRODUCTS = {
    "apple-home-hub",
    "apple-power-adapter",
    "magic-keyboard",
    "polishing-cloth",
}

_PRECISE_HARDWARE_PRODUCT_LINES = {
    "apple-home-hub",
    "apple-power-adapter",
    "foldable-iphone",
    "imac",
    "ipad-air",
    "ipad-mini",
    "ipad-pro",
    "mac-mini",
    "mac-pro",
    "mac-studio",
    "magic-keyboard",
    "polishing-cloth",
    "vision-pro",
}


def _structured_title_action_classes(identity: EventIdentity) -> set[str]:
    raw_actions = set(identity.title_actions)
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not raw_actions
    ):
        raw_actions = set(identity.actions)
    classes = {
        _ACTION_EQUIVALENCE.get(action, action)
        for action in raw_actions
    }
    if (
        "product-launch" in identity.title_actions
        and "feature-change" not in identity.title_actions
    ):
        classes.discard("product-change")
    return classes


def _lead_asserts_first_party_release(lead: str) -> bool:
    """Return true only when the first lead sentence owns an Apple release."""
    first_lead = _primary_assertion_scope("", lead)[1]
    return bool(
        re.search(
            r"\bapple\b.{0,48}\b(?:is\s+announcing|are\s+announcing|announced|"
            r"introduces|introduced|launches|launched|unveils|unveiled|releases|released)\b|"
            r"苹果.{0,36}(?:发布|推出|揭晓|上线|开售|登场)(?!的)",
            first_lead,
        )
    )


def _bounded_evidence_products(value: str) -> set[str]:
    """Resolve known first-party products from the bounded article evidence.

    Headlines sometimes use a descriptive product label (for example, a
    display instead of its established hub name), while the lead names the
    canonical product.  Reuse the identity vocabulary here instead of adding
    source-specific headline aliases.  Possessives are normalized because
    English leads commonly say ``Apple's`` where product aliases say
    ``Apple``.
    """
    scope = _normalized(value)
    scope = re.sub(r"\bapple's\b", "apple", scope)
    products: set[str] = set()
    for product, aliases in PRODUCT_PATTERNS:
        for alias in aliases:
            normalized_alias = _normalized(alias)
            if not normalized_alias:
                continue
            if re.fullmatch(r"[a-z0-9][a-z0-9 .+/-]*", normalized_alias):
                direct_alias = re.search(
                    rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])",
                    scope,
                )
                possessive_alias = None
                if normalized_alias.startswith("apple "):
                    product_phrase = normalized_alias.removeprefix("apple ")
                    possessive_alias = re.search(
                        rf"(?<![a-z0-9])its\s+{re.escape(product_phrase)}(?![a-z0-9])",
                        scope,
                    )
                if direct_alias or possessive_alias:
                    products.add(product)
                    break
            elif normalized_alias in scope:
                products.add(product)
                break
    return products


def _structured_title_subjects(
    identity: EventIdentity,
    evidence_products: Iterable[str] = (),
) -> set[str]:
    subjects = set(identity.title_products & _SPECIFIC_FIRST_PARTY_PRODUCTS)
    subjects |= {
        component
        for component in identity.title_components
        if component.startswith("apple-silicon-generation:")
        or component in {
            "genlock",
            "keyboard-key-labels",
            "maps-advertising",
            "private-cloud-compute-server",
        }
    }
    if identity.scope == "apple-direct" and identity.content_form == "news":
        lead_products = set(identity.products & _SPECIFIC_FIRST_PARTY_PRODUCTS)
        lead_products |= set(evidence_products) & _SPECIFIC_FIRST_PARTY_PRODUCTS
        if not subjects and len(lead_products) == 1:
            subjects |= lead_products
        trusted_components = {
            component
            for component in identity.components
            if component.startswith("apple-silicon-generation:")
            or component
            in {
                "genlock",
                "keyboard-key-labels",
                "maps-advertising",
                "private-cloud-compute-server",
            }
        }
        if not subjects and len(trusted_components) == 1:
            subjects |= trusted_components
    return subjects


def _primary_title_subjects(identity: EventIdentity) -> set[str]:
    """Return the title entity that owns the concrete action.

    A named first-party product outranks chips, features, and other supporting
    components in the same headline. When no product is named, a concrete
    title component can own the action itself. This distinction prevents a
    legacy recall seed from treating a product launch and an accessory update
    as one event merely because their bodies share launch-day context.
    """
    if identity.title_products:
        subjects = set(identity.title_products)
        platform_context = {
            "ios",
            "ipados",
            "macos",
            "watchos",
            "tvos",
            "visionos",
        }
        specific_products = subjects - platform_context
        first_party_services = specific_products & _SOFTWARE_FIRST_PARTY_PRODUCTS
        if first_party_services:
            subjects = first_party_services
        if "security" in identity.actions:
            platform_aliases = {
                "iphone": "ios",
                "ipad": "ipados",
                "apple-watch": "watchos",
                "apple-tv": "tvos",
                "vision-pro": "visionos",
                "mac": "macos",
                "macbook": "macos",
                "imac": "macos",
                "mac-mini": "macos",
                "mac-studio": "macos",
                "mac-pro": "macos",
            }
            subjects |= {
                platform_aliases[subject]
                for subject in tuple(subjects)
                if subject in platform_aliases
            }
        return subjects
    return {
        component
        for component in identity.title_components
        if component.startswith("apple-silicon-generation:")
        or component in EVIDENCE_BACKED_COMPONENTS
        or component
        in {
            "genlock",
            "keyboard-key-labels",
            "maps-advertising",
            "private-cloud-compute-server",
        }
    }


def _direct_title_subject_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Reject a recall seed that joins different first-party action owners."""
    left_identity = left.identity
    right_identity = right.identity
    if left_identity is None or right_identity is None:
        return False
    if (
        left_identity.scope != "apple-direct"
        or right_identity.scope != "apple-direct"
        or left_identity.content_form != "news"
        or right_identity.content_form != "news"
    ):
        return False
    if left.exact_facets & right.exact_facets:
        return False
    pair_assertions = {
        key
        for key in left.event_keys | right.event_keys
        if key.startswith("structured-assertion:")
    }
    if (
        identity_pair_decision(left_identity, right_identity) == "match"
        and not pair_assertions
    ):
        return False
    if (
        left_identity.title_products & right_identity.title_products
        and left_identity.title_components & right_identity.title_components
    ):
        return False
    left_release_stages = {
        key.rsplit(":", 1)[-1]
        for key in left.event_keys
        if key.startswith(
            ("apple-os-release-wave:", "apple-os-platform-release-wave:")
        )
    }
    right_release_stages = {
        key.rsplit(":", 1)[-1]
        for key in right.event_keys
        if key.startswith(
            ("apple-os-release-wave:", "apple-os-platform-release-wave:")
        )
    }
    release_platform_products = {
        "ios",
        "iphone",
        "ipados",
        "ipad",
        "macos",
        "mac",
        "watchos",
        "apple-watch",
        "tvos",
        "apple-tv",
        "visionos",
        "vision-pro",
    }
    if (
        left_release_stages
        and left_release_stages == right_release_stages
        and bool(left_identity.title_products)
        and bool(right_identity.title_products)
        and left_identity.title_products <= release_platform_products
        and right_identity.title_products <= release_platform_products
        and "predicate:os-release-announcement" in left.separation_keys
        and "predicate:os-release-announcement" in right.separation_keys
    ):
        return False
    left_subjects = _primary_title_subjects(left_identity)
    right_subjects = _primary_title_subjects(right_identity)
    if not left_subjects or not right_subjects or not left_subjects.isdisjoint(right_subjects):
        return False
    shared_keys = left.event_keys & right.event_keys
    platform_subjects = {
        "ios",
        "iphone",
        "ipados",
        "ipad",
        "macos",
        "mac",
        "macbook",
        "imac",
        "mac-mini",
        "mac-studio",
        "mac-pro",
        "watchos",
        "apple-watch",
        "tvos",
        "apple-tv",
        "visionos",
        "vision-pro",
    }
    for key in shared_keys:
        if key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:")):
            release_predicate = "predicate:os-release-announcement"
            left_assertions = {
                candidate
                for candidate in left.event_keys
                if candidate.startswith("structured-assertion:")
            }
            right_assertions = {
                candidate
                for candidate in right.event_keys
                if candidate.startswith("structured-assertion:")
            }
            independent_actions = {
                "claim-denial",
                "delay-roadmap",
                "legal",
                "price-change",
                "project-cancellation",
                "transaction",
            }
            if (
                release_predicate in left.separation_keys
                and release_predicate in right.separation_keys
                and left_assertions == right_assertions
                and not (left_identity.title_actions & independent_actions)
                and not (right_identity.title_actions & independent_actions)
            ):
                return False
            if left_subjects | right_subjects <= platform_subjects:
                return False
            continue
        if key.startswith(("canonical-apple-action:", "primary-claim:", "structured-assertion:")):
            return False
    return True


def _direct_title_action_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Split a concrete capability report from a generic launch report.

    Action vocabularies vary heavily across sources and languages, so disjoint
    action labels alone are never a conflict.  The only safe asymmetric case is
    when one title asserts a changed product object while the other reports only
    the product lifecycle, and no precise identity key proves they are the same
    event.
    """
    left_identity = left.identity
    right_identity = right.identity
    if left_identity is None or right_identity is None:
        return False
    if (
        left_identity.scope != "apple-direct"
        or right_identity.scope != "apple-direct"
        or left_identity.content_form != "news"
        or right_identity.content_form != "news"
        or left.exact_facets & right.exact_facets
    ):
        return False
    if identity_pair_decision(left_identity, right_identity) == "match":
        return False
    left_subjects = _primary_title_subjects(left_identity)
    right_subjects = _primary_title_subjects(right_identity)
    if not left_subjects or not right_subjects or not (left_subjects & right_subjects):
        return False
    left_actions = _structured_title_action_classes(left_identity)
    right_actions = _structured_title_action_classes(right_identity)
    if not left_actions or not right_actions:
        return False
    shared_keys = left.event_keys & right.event_keys
    if any(
        key.startswith(
            (
                "canonical-apple-action:",
                "structured-assertion:",
                "structured-title-product-update:",
            )
        )
        for key in shared_keys
    ):
        return False
    if any(
        key.startswith(
            (
                "apple-firmware:",
                "apple-os-release-wave:",
                "canonical-apple-action:",
                "primary-claim:",
                "structured-assertion:",
                "structured-title-product-update:",
                "structured-title-product-release:",
            )
        )
        for key in shared_keys
    ):
        return False
    if any(
        key.startswith("product-period:")
        for key in left.separation_keys & right.separation_keys
    ):
        return False

    def is_concrete_change(profile: ReconciliationProfile, actions: set[str]) -> bool:
        return "product-change" in actions and any(
            key.startswith("changed-object:")
            for key in profile.separation_keys
        )

    def is_pure_lifecycle(actions: set[str]) -> bool:
        return bool(actions) and actions <= {"availability", "availability-expansion"}

    return bool(
        (is_concrete_change(left, left_actions) and is_pure_lifecycle(right_actions))
        or (is_concrete_change(right, right_actions) and is_pure_lifecycle(left_actions))
    )


def _structured_category_hint(
    identity: EventIdentity,
    direct_subjects: Iterable[str] = (),
) -> str:
    if (
        identity.scope == "apple-direct"
        and "first-party-accessibility-guidance" in identity.components
    ):
        return "software_systems"
    direct_subjects = set(direct_subjects) or _structured_title_subjects(identity)
    direct_action = bool(_structured_title_action_classes(identity))
    if identity.action_owner != "apple" and not (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and direct_subjects
        and direct_action
    ):
        return ""
    if (
        "apple-operated-activity-challenge" in identity.facets
        or "apple-watch-activity-challenge" in identity.title_named_subjects
    ):
        return "software_systems"
    if identity.title_components & {
        "financed-device-restriction",
        "genlock",
        "keyboard-key-labels",
    }:
        return "hardware_products"
    products = set(identity.title_products) | set(direct_subjects)
    if products & _SOFTWARE_FIRST_PARTY_PRODUCTS:
        return "software_systems"
    if products & _HARDWARE_FIRST_PARTY_PRODUCTS:
        return "hardware_products"
    if any(
        component.startswith("apple-silicon-generation:")
        for component in identity.title_components
    ):
        return "hardware_products"
    if "private-cloud-compute-server" in direct_subjects:
        return "software_systems"
    return ""


def build_reconciliation_profile(
    *,
    title: str,
    lead: str,
    identity: EventIdentity,
    exact_facets: Iterable[str],
    regions: Iterable[str],
    relevance_tier: str = "strong",
    relevance_reason: str = "",
    trusted_direct_action: bool = False,
    event_kind: str = "",
    evidence: str = "",
) -> ReconciliationProfile:
    caller_trusted_direct_action = trusted_direct_action
    title_text = _normalized(title)
    text = f"{title_text}. {_normalized(lead)[:900]}"
    editorial_first_party_action = _editorial_source_proves_current_first_party_action(
        title,
        lead,
        identity,
    )
    exact = frozenset(exact_facets)
    # Facets remain inputs to the existing domain matcher.  They are not
    # automatically cross-event keys: even a precise facet can describe more
    # than one action in a busy news cycle.
    event_keys: set[str] = set()
    boundary_keys: set[str] = set()
    separation_keys = _product_separation_keys(identity)
    company_performance_subject = quantified_apple_company_performance_subject(
        title,
        lead,
    )
    if company_performance_subject:
        event_key = f"structured-company-performance:{company_performance_subject}"
        event_keys.add(event_key)
        boundary_keys.add(event_key)
        separation_keys.add("primary-claim-predicate:quantified-company-performance")
        trusted_direct_action = True
    separation_keys |= _predicate_separation_keys(identity)
    separation_keys |= _title_predicate_separation_keys(title)
    changed_object_keys = _changed_object_separation_keys(title, lead, identity)
    separation_keys |= changed_object_keys
    separation_keys |= _title_product_period_keys(title, identity)
    evidence_products = _bounded_evidence_products(
        f"{_normalized(lead)[:900]} {_normalized(evidence)[:1200]}"
    )
    primary_evidence_products = _bounded_evidence_products(
        " ".join(
            (
                _primary_assertion_scope("", lead)[1],
                _primary_assertion_scope("", evidence)[1],
            )
        )
    )
    structured_title_subjects = _structured_title_subjects(
        identity,
        primary_evidence_products or evidence_products,
    )
    category_hint = _structured_category_hint(identity, structured_title_subjects)
    if company_performance_subject:
        category_hint = "software_systems"
    if editorial_first_party_action and len(identity.title_products) == 1:
        editorial_product = next(iter(identity.title_products))
        editorial_update_key = f"structured-title-product-update:{editorial_product}"
        event_keys.add(editorial_update_key)
        boundary_keys.add(editorial_update_key)
        if editorial_product in _HARDWARE_FIRST_PARTY_PRODUCTS or editorial_product == "polishing-cloth":
            category_hint = "hardware_products"
    content_form = _reconciliation_content_form(title_text, identity)
    third_party_app_availability = (
        _third_party_app_availability_without_platform_change(title_text, lead)
        or is_third_party_app_action_on_apple_platform(title_text, lead)
    )
    if (
        content_form == "news"
        and len(primary_evidence_products & _HARDWARE_FIRST_PARTY_PRODUCTS) >= 3
        and not identity.title_products
        and not identity.title_components
        and len(identity.actions) >= 2
        and not exact
    ):
        # A title without a concrete subject cannot own several unrelated
        # product/action pairs found only in its body. Treat it as an editorial
        # summary so it cannot bridge the product events it recaps.
        content_form = "roundup"
    projected_hardware_roadmap = bool(
        re.fullmatch(r"apple\s+.+\s+roadmap\s+update", title_text)
        and identity.scope == "apple-direct"
        and identity.title_products
        & {
            "airpods",
            "apple-home-hub",
            "apple-tv",
            "apple-watch",
            "beats",
            "foldable-iphone",
            "homepod",
            "imac",
            "ipad",
            "iphone",
            "mac",
            "mac-mini",
            "mac-pro",
            "mac-studio",
            "macbook",
            "vision-pro",
        }
    )

    canonical_title = _canonical_title(title_text)
    if content_form == "news" and len(canonical_title) >= 18:
        canonical_title_key = f"structured-canonical-title:{canonical_title}"
        event_keys.add(canonical_title_key)
        boundary_keys.add(canonical_title_key)

    accessory_evaluation = _hardware_accessory_evaluation_claim(
        title_text,
        lead,
        identity,
    )
    if accessory_evaluation:
        product, accessory = accessory_evaluation
        accessory_key = (
            f"canonical-apple-action:{product}:{accessory}-compatibility-evaluation"
        )
        event_keys.add(accessory_key)
        boundary_keys.add(f"structured-subject:{product}:{accessory}")
        separation_keys |= {
            f"primary-claim-subject:{product}:{accessory}",
            "primary-claim-predicate:accessory-compatibility-evaluation",
        }
        category_hint = "hardware_products"

    for product, component in _hardware_component_adoption_claims(
        title_text,
        lead,
        identity,
    ):
        component_key = f"canonical-apple-action:{product}:{component}-adoption"
        event_keys.add(component_key)
        boundary_keys.add(f"structured-subject:{product}:{component}")
        separation_keys |= {
            f"primary-claim-subject:{product}:{component}",
            "primary-claim-predicate:hardware-component-adoption",
        }
        category_hint = "hardware_products"

    structured_title_actions = _structured_title_action_classes(identity)
    primary_changed_object, primary_changed_measure = (
        _primary_title_changed_object_measure(title_text)
    )
    changed_object_subjects = _primary_title_subjects(identity)
    if (
        content_form == "news"
        and identity.scope == "apple-direct"
        and len(changed_object_subjects) == 1
        and primary_changed_object
        and primary_changed_measure
    ):
        changed_subject = next(iter(changed_object_subjects))
        changed_object_key = (
            f"structured-measure:{changed_subject}:{primary_changed_object}:"
            f"count:{primary_changed_measure}"
        )
        event_keys.add(changed_object_key)
    structured_action_owner = bool(
        not third_party_app_availability
        and (
            identity.action_owner == "apple"
            or (
                identity.scope == "apple-direct"
                and identity.content_form == "news"
                and structured_title_subjects & _SPECIFIC_FIRST_PARTY_PRODUCTS
                and structured_title_actions
            )
        )
    )
    if (
        structured_action_owner
        and content_form == "news"
        and structured_title_subjects
        and structured_title_actions
    ):
        for subject in sorted(structured_title_subjects):
            for action in sorted(structured_title_actions):
                event_keys.add(f"structured-title-action:{subject}:{action}")
                boundary_keys.add(f"structured-title-subject:{subject}")
        if structured_title_subjects & _SPECIFIC_FIRST_PARTY_PRODUCTS and structured_title_actions & {
            "availability",
            "availability-expansion",
            "delay-roadmap",
            "price-change",
            "product-change",
        }:
            for subject in sorted(structured_title_subjects & _SPECIFIC_FIRST_PARTY_PRODUCTS):
                event_keys.add(f"structured-title-product-update:{subject}")
                boundary_keys.add(f"structured-title-subject:{subject}")
    release_subjects = identity.title_products & _PRECISE_HARDWARE_PRODUCT_LINES
    generic_refresh_title = bool(
        identity.title_actions
        and identity.title_actions <= {"feature-change", "product-refresh"}
        and not changed_object_keys
    )
    lead_release_action = _lead_asserts_first_party_release(lead)
    release_action = bool(
        "market-report" not in identity.title_actions
        and (
            "product-launch" in identity.title_actions
        or (
            lead_release_action
            and (not identity.title_actions or generic_refresh_title)
        )
        )
    )
    release_action_owner = bool(
        structured_action_owner
        or (
            identity.scope == "apple-direct"
            and content_form == "news"
            and lead_release_action
            and not identity.title_actors
            and identity.title_products <= release_subjects
        )
    )
    if (
        release_action_owner
        and content_form == "news"
        and len(release_subjects) == 1
        and release_action
    ):
        release_subject = next(iter(release_subjects))
        event_keys.add(f"structured-title-product-release:{release_subject}")
        boundary_keys.add(f"structured-title-subject:{release_subject}")

    macos_maintenance_branches: set[str] = set()
    if "macos" in title_text and re.search(
        r"\b(?:updates?|security fixes?|now available)\b|(?:更新|修复)",
        title_text,
    ):
        macos_maintenance_branches.update(
            match.group(1)
            for match in re.finditer(
                r"\bmacos\s+([a-z][a-z-]{2,})\b",
                title_text,
            )
        )
        macos_maintenance_branches.update(
            match.group(1)
            for match in re.finditer(
                r"(?:&|/|\band\b)\s*([a-z][a-z-]{2,})"
                r"(?=\s+(?:\d+(?:\.\d+){1,2}|updates?|now\b|available\b|更新|修复|$))",
                title_text,
            )
        )
        macos_maintenance_branches -= {
            "macos",
            "new",
            "older",
            "security",
            "software",
            "system",
            "update",
        }
    if len(macos_maintenance_branches) >= 2:
        branch_key = "-".join(sorted(macos_maintenance_branches))
        maintenance_key = f"canonical-apple-action:macos-maintenance:{branch_key}"
        event_keys.add(maintenance_key)
        boundary_keys.add(maintenance_key)
        separation_keys.add("action:os-maintenance-update")
        category_hint = "software_systems"

    if projected_hardware_roadmap:
        assertion_events: set[str] = set()
        assertion_boundaries: set[str] = set()
        assertion_separation: set[str] = set()
        category_hint = "hardware_products"
        separation_keys.add("predicate:hardware-product-roadmap")
    else:
        assertion_events, assertion_boundaries, assertion_separation = _structured_assertion_keys(
            title,
            lead,
            identity,
            evidence,
            regions,
        )
    event_keys |= assertion_events
    boundary_keys |= assertion_boundaries
    separation_keys |= assertion_separation
    if any(key.startswith("structured-assertion:apple-tv:") for key in assertion_events):
        category_hint = "software_systems"
    canonical_action_keys = _canonical_first_party_action_keys(identity)
    event_keys |= canonical_action_keys
    boundary_keys |= canonical_action_keys
    separation_keys |= {
        f"action:{key.rsplit(':', 1)[-1]}"
        for key in canonical_action_keys
    }
    (
        primary_claim_events,
        primary_claim_boundaries,
        primary_claim_separation,
        primary_claim_category,
        primary_claim_trusted,
    ) = _primary_claim_projection(title, lead, identity, regions, evidence)
    dominant_primary_claim_subjects = {
        "primary-claim:apple-leadership:ceo-transition": "apple-leadership",
        "primary-claim:apple-leadership:transition-interview": "apple-leadership",
        "primary-claim:apple-leadership:ceo-first-employee-memo": "apple-leadership",
        "primary-claim:apple-leadership:ceo-social-account-launch": "apple-leadership",
        "primary-claim:apple-leadership:ceo-social-profile-image-update": "apple-leadership",
        "primary-claim:iphone-in-box-accessories:policy-denial": "iphone-in-box-accessories",
        "primary-claim:apple-openai-trade-secret-case:response-filing": "apple-openai-trade-secret-case",
        "primary-claim:apple-openai-trade-secret-case:evidence-disclosure": "apple-openai-trade-secret-case",
    }
    dominant_primary_claims = primary_claim_events & dominant_primary_claim_subjects.keys()
    ceo_transition_claim = "primary-claim:apple-leadership:ceo-transition"
    if ceo_transition_claim in dominant_primary_claims and len(primary_claim_events) > 1:
        # A regulatory meeting, document, or other concrete action can mention
        # the succession as context. In that case the generic transition key
        # must not replace the more specific primary claim.
        dominant_primary_claims = set(dominant_primary_claims)
        dominant_primary_claims.discard(ceo_transition_claim)
    if dominant_primary_claims:
        # A concrete document, policy response, legal filing stage, or formal
        # lifecycle action owns the event. Product guesses and background
        # transitions found elsewhere in the page may enrich facts, but must
        # not remain as alternate merge bridges.
        event_keys = set(dominant_primary_claims)
        dominant_subjects = {
            dominant_primary_claim_subjects[key]
            for key in dominant_primary_claims
        }
        dominant_predicates = {
            key.rsplit(":", 1)[-1]
            for key in dominant_primary_claims
        }
        boundary_keys = {
            f"primary-claim-subject:{subject}"
            for subject in dominant_subjects
        }
        separation_keys = {
            key
            for key in primary_claim_separation
            if key.startswith("primary-claim-")
            and (
                key.removeprefix("primary-claim-predicate:") in dominant_predicates
                or key.removeprefix("primary-claim-subject:") in dominant_subjects
            )
        }
    else:
        event_keys |= primary_claim_events
        boundary_keys |= primary_claim_boundaries
        separation_keys |= primary_claim_separation
    if primary_claim_category:
        category_hint = primary_claim_category
    trusted_direct_action = trusted_direct_action or primary_claim_trusted
    executive_farewell_key = (
        "primary-claim:apple-leadership:executive-farewell-communication"
    )
    if executive_farewell_key in primary_claim_events:
        event_keys.discard(
            "canonical-apple-action:apple-leadership:leadership-transition"
        )
        boundary_keys.discard(
            "canonical-apple-action:apple-leadership:leadership-transition"
        )
        separation_keys.discard("action:leadership-transition")
    invitation_interpretation_key = _apple_event_invitation_interpretation_key(
        title,
        lead,
        identity,
        changed_object_keys,
    )
    if invitation_interpretation_key:
        event_keys.add(invitation_interpretation_key)
        boundary_keys.add(invitation_interpretation_key)
        separation_keys |= {
            "primary-claim-subject:apple-event-invitation",
            "primary-claim-predicate:event-invitation-feature-interpretation",
        }
        category_hint = "hardware_products"
        trusted_direct_action = True
    event_campaign_key = "" if invitation_interpretation_key else _apple_event_campaign_key(title, lead)
    if event_campaign_key:
        event_keys.add(event_campaign_key)
        boundary_keys.add(event_campaign_key)
        separation_keys.add("primary-claim-subject:apple-event-campaign")
        category_hint = "hardware_products"
        trusted_direct_action = True
    event_occurrence_keys = (
        set() if invitation_interpretation_key else _apple_event_occurrence_keys(title, lead)
    )
    if event_occurrence_keys:
        event_keys |= event_occurrence_keys
        boundary_keys |= event_occurrence_keys
        separation_keys.add("primary-claim-subject:apple-event-campaign")
        category_hint = "hardware_products"
        trusted_direct_action = True
    content_claim = _first_party_content_claim(title, lead, identity, evidence)
    if content_claim:
        content_subject, content_action = content_claim
        content_key = f"primary-claim:apple-tv-content:{content_subject}:{content_action}"
        event_keys.add(content_key)
        boundary_keys.add(f"content-title:{content_subject}")
        separation_keys |= {
            f"content-title:{content_subject}",
            f"content-action:{content_action}",
        }
        category_hint = "software_systems"
        trusted_direct_action = True
    hardware_products = identity.title_products & {
        "airpods",
        "apple-home-hub",
        "apple-tv",
        "apple-watch",
        "beats",
        "foldable-iphone",
        "homepod",
        "imac",
        "ipad",
        "iphone",
        "mac",
        "mac-mini",
        "mac-pro",
        "mac-studio",
        "macbook",
        "vision-pro",
    }
    if changed_object_keys and hardware_products:
        category_hint = "hardware_products"
    structured_direct_assertion = bool(
        any(key.startswith("structured-assertion:") for key in assertion_events)
    )
    direct_product_lifecycle_action = is_direct_apple_product_lifecycle_action(
        title,
        f"{lead} {evidence}",
    )
    if direct_product_lifecycle_action:
        lifecycle_scope = f"{title_text} {_normalized(lead)[:900]} {_normalized(evidence)[:1200]}"
        lifecycle_subjects = _product_lifecycle_subjects(lifecycle_scope, identity)
        for subject in lifecycle_subjects:
            event_keys.add(
                f"structured-assertion:product-lifecycle:{subject}:obsolete"
            )
            separation_keys.add(f"assertion-subject:product-lifecycle:{subject}")
        boundary_keys.add("structured-action:product-lifecycle-obsolete")
        separation_keys.add("assertion-action:product-lifecycle-obsolete")
        category_hint = "hardware_products"
    title_owned_direct_action = bool(
        identity.action_owner == "apple"
        and not third_party_app_availability
        and content_form == "news"
        and identity.title_actions
        and not projected_hardware_roadmap
    )
    security_ids = {
        match.lower()
        for match in re.findall(
            r"\bCVE-\d{4}-\d{4,7}\b",
            f"{text} {_normalized(evidence)}",
            flags=re.IGNORECASE,
        )
    }
    if security_ids and identity.scope in {"apple-direct", "unknown"} and (
        identity.title_products
        & {"ios", "ipados", "mac", "macos", "watchos", "tvos", "visionos", "safari"}
        or _contains(text, "apple", "苹果")
    ):
        for security_id in security_ids:
            event_keys.add(f"apple-security:cve:{security_id}")
            boundary_keys.add(f"apple-security:cve:{security_id}")
        separation_keys.add("action:security-vulnerability")
        category_hint = "software_systems"
    security_components = {
        component.removeprefix("os-component:")
        for component in identity.components
        if component.startswith("os-component:")
    }
    if security_components and "security" in identity.actions and (
        identity.scope in {"apple-direct", "unknown"}
        or identity.title_products
        & {"ios", "ipados", "mac", "macos", "watchos", "tvos", "visionos", "safari"}
    ):
        for component in security_components:
            event_keys.add(f"apple-security:os-component:{component}")
            boundary_keys.add(f"apple-security:os-component:{component}")
        separation_keys.add("action:security-vulnerability")
        category_hint = "software_systems"
    cross_platform_message_reply = bool(
        identity.scope == "apple-direct"
        and "ios" in identity.title_products
        and _contains(
            title_text,
            "replying to android texts",
            "reply to android texts",
            "green bubble",
            "安卓绿色气泡",
            "绿色气泡信息",
            "回复安卓消息",
            "回复安卓",
        )
    )
    if cross_platform_message_reply:
        event_keys.add("apple-messages:cross-platform-inline-reply")
        boundary_keys.add("apple-messages:cross-platform-inline-reply")
        separation_keys.add("action:cross-platform-message-reply")
        category_hint = "software_systems"
    chip_performance_report = bool(
        identity.scope == "apple-direct"
        and re.search(r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b", title_text)
        and _contains(
            title_text,
            "performance",
            "speed",
            "faster",
            "efficiency",
            "efficient",
            "power consumption",
            "性能",
            "速度",
            "能效",
            "功耗",
        )
        and not (identity.title_actions & {"price-change"})
    )
    if chip_performance_report:
        chip_names = {
            re.sub(r"\s+", "-", match.lower())
            for match in re.findall(
                r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b",
                title_text,
            )
        }
        for chip_name in chip_names:
            event_keys.add(f"apple-chip-performance:{chip_name}")
            boundary_keys.add(f"apple-chip-performance:{chip_name}")
        separation_keys.add("action:chip-performance-report")
        category_hint = "hardware_products"
    tracking_transparency_policy_action = bool(
        _contains(
            text,
            "app tracking transparency",
            "tracking transparency",
            "att consent",
            "att prompt",
            "广告数据授权规则",
            "广告跟踪授权",
            "应用跟踪透明度",
        )
        and (
            "regulation" in identity.actions
            or _contains(
                text,
                "regulator",
                "regulatory",
                "agreement",
                "ordered",
                "comply",
                "监管",
                "协议",
                "同意",
                "要求",
                "合规",
            )
        )
    )
    if tracking_transparency_policy_action:
        event_keys.add("apple-platform-policy:app-tracking-transparency:regulatory-change")
        boundary_keys.add("apple-platform-policy:app-tracking-transparency")
        separation_keys.add("action:platform-policy-regulatory-change")
        category_hint = "software_systems"
    os_signing_closure = bool(
        re.search(
            r"\b(?:stops?|stopped|ceases?|ceased)\s+signing\b|"
            r"\bno\s+longer\s+signs?\b|"
            r"(?:停止签署|停止签名|关闭.{0,12}签名(?:验证|通道)?)",
            title_text,
        )
    )
    if os_signing_closure:
        signing_versions = {
            match.group(1)
            for match in re.finditer(
                r"(?:\bios\s*)?(\d{2,3}(?:\.\d+){1,2})\b",
                title_text,
            )
        }
        for version in signing_versions:
            event_keys.add(f"apple-os-signing-closure:ios:{version}")
        boundary_keys.add("apple-os-signing-closure:ios")
        separation_keys.add("action:os-signing-closure")
        category_hint = "software_systems"
    official_apple_store_transaction_option_action = (
        _official_apple_store_transaction_option_action(title, lead)
    )
    if official_apple_store_transaction_option_action:
        boundary_keys.add("apple-store-retail:transaction-option")
        separation_keys.add("action:official-retail-transaction-option")
        category_hint = "hardware_products"
    first_party_service_capability_signal = ""
    if (
        "apple-fitness" in identity.title_products
        and _contains(
            text,
            "live production",
            "live-to-tape",
            "live sessions",
            "live content",
            "multi-camera",
            "直播制作",
            "直播内容",
            "直播健身",
            "多机位录播",
        )
        and _contains(
            text,
            "job listing",
            "job opening",
            "hiring",
            "recruiting",
            "producer",
            "招聘信息",
            "招聘",
            "制片人",
        )
    ):
        first_party_service_capability_signal = (
            "canonical-apple-action:apple-fitness:live-production-hiring"
        )
    elif (
        "apple-wallet" in identity.title_products
        and _contains(
            text,
            "driver's license",
            "drivers license",
            "driver license",
            "mobile id",
            "digital id",
            "数字驾照",
            "电子驾照",
            "数字身份证",
            "移动身份证",
        )
        and _contains(
            text,
            "expand",
            "expands",
            "expanding",
            "coming to",
            "launch",
            "support to follow",
            "more states",
            "扩展",
            "扩大",
            "新增",
            "上线",
            "支持",
            "更多州",
        )
    ):
        first_party_service_capability_signal = (
            "canonical-apple-action:apple-wallet:digital-id-regional-expansion"
        )
    if first_party_service_capability_signal:
        event_keys.add(first_party_service_capability_signal)
        boundary_keys.add(first_party_service_capability_signal)
        separation_keys.add("action:first-party-service-capability-signal")
        category_hint = "software_systems"
    versioned_os_compatibility_action = bool(
        identity.scope == "apple-direct"
        and "os-compatibility" in identity.facets
        and identity.title_products
        & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
        and identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
    )
    if versioned_os_compatibility_action:
        boundary_keys.add("apple-os-compatibility:device-feature-matrix")
        separation_keys.add("action:os-device-feature-compatibility")
        category_hint = "software_systems"
    if any(
        key.startswith(
            (
                "structured-assertion:apple-display-inventory:",
                "structured-assertion:apple-facility:",
                "structured-assertion:apple-glasses:",
                "structured-assertion:iphone-anniversary-redesign:",
                "structured-assertion:iphone-",
                "structured-assertion:product-lifecycle:",
            )
        )
        for key in assertion_events
    ):
        category_hint = "hardware_products"
    if any(
        key.startswith(
            (
                "structured-assertion:app-store:",
                "structured-assertion:apple-patent:notification-",
                "structured-assertion:iphone-camera:reference-image-",
            )
        )
        for key in assertion_events
    ):
        category_hint = "software_systems"

    document_lifecycle_key = first_party_document_lifecycle_key(title_text, text, identity)
    if document_lifecycle_key:
        event_keys.add(document_lifecycle_key)
        boundary_keys.add(document_lifecycle_key)
        separation_keys.add(f"title-fact:{document_lifecycle_key}")
        separation_keys.add("action:first-party-document-lifecycle")
        category_hint = "software_systems"

    for signature in _title_fact_signatures(title_text, lead):
        key = f"title-fact:{signature}"
        event_keys.add(key)
        boundary_keys.add(key)
        separation_keys.add(key)

    primary_lead = re.split(
        r"(?:[。！？]|(?<=[.!?])\s+)",
        _normalized(lead),
        maxsplit=1,
    )[0]
    measurements = _evidence_measurements(title_text, lead)
    claim_components = _claim_components(identity) | {
        component
        for component in primary_assertion_components(primary_lead)
        if ":" not in component
    }
    claim_products = {
        product.removeprefix("apple-")
        for product in (identity.title_products or identity.products)
        if product
    }
    product_aliases = claim_products | {
        "apple",
        "iphone",
        "ipad",
        "mac",
        "macbook",
    }
    attributed_entities = {
        component.removeprefix("report-attribution:")
        for component in identity.components
        if component.startswith("report-attribution:")
    } | {
        subject.removeprefix("apple-")
        for subject in identity.named_subjects
        if subject.removeprefix("apple-") not in product_aliases
        and subject not in _GENERIC_SUBJECT_WORDS
    }
    non_calendar_measurements = {
        measurement
        for measurement in measurements
        if not measurement.startswith("year:")
    }
    claim_status_actions = identity.title_actions & {
        "claim-denial",
        "project-cancellation",
    }
    if claim_status_actions:
        status_subjects = sorted(
            identity.title_products
            or identity.title_actors
            or identity.title_named_subjects
        )
        status_measurements = sorted(
            measurement
            for measurement in non_calendar_measurements
            if measurement.startswith(("anniversary:", "money:"))
        )
        for subject in status_subjects:
            for measurement in status_measurements:
                event_keys.add(
                    f"structured-claim-status:{subject}:{measurement}"
                )
    for entity in attributed_entities:
        for product in claim_products:
            for measurement in non_calendar_measurements:
                event_keys.add(
                    f"structured-attributed-measure:{entity}:{product}:{measurement}"
                )
    for component in claim_components:
        for product in claim_products:
            if (
                not exact
                and component in LEAD_IDENTITY_COMPONENTS
                and component in primary_assertion_components(primary_lead)
            ):
                event_keys.add(f"structured-component:{component}:{product}")
            for entity in attributed_entities:
                event_keys.add(
                    f"structured-entity-component:{entity}:{product}:{component}"
                )
            for measurement in non_calendar_measurements:
                event_keys.add(
                    f"structured-component-measure:{component}:{product}:{measurement}"
                )
    supplier_component_classes = {
        component.removeprefix("component-supplier-sourcing:")
        for component in identity.components
        if component.startswith("component-supplier-sourcing:")
    }
    supplier_entity_stopwords = {
        "cpu",
        "dram",
        "gpu",
        "lcd",
        "nand",
        "oled",
        "ram",
        "soc",
    }
    supplier_entities = {
        subject
        for subject in identity.named_subjects
        if subject not in supplier_entity_stopwords
        and not subject.startswith(("a20", "m6", "m7", "m8"))
    }
    for component_class in supplier_component_classes:
        for supplier_entity in supplier_entities:
            event_keys.add(
                f"structured-supplier-action:{component_class}:{supplier_entity}"
            )
    calendar_measurements = {
        measurement
        for measurement in measurements
        if measurement.startswith("year:")
    }
    for left_component, right_component in combinations(sorted(claim_components), 2):
        for measurement in calendar_measurements:
            event_keys.add(
                "structured-component-period:"
                f"{left_component}+{right_component}:{measurement}"
            )
    if (
        event_kind == "legal_antitrust"
        or "legal" in identity.actions
        or identity.case_topics
        or identity.counterparties
    ):
        for measurement in measurements:
            if measurement.startswith("money:"):
                event_keys.add(f"structured-legal-settlement:{measurement}")
    removal_stage = _app_store_removal_stage(f"{title_text}. {primary_lead}")
    app_store_removal_context = bool(
        "app-store" in identity.products
        or _contains(
            f"{title_text}. {primary_lead}",
            "app store",
            "apple app store",
            "应用商店",
            "苹果应用商店",
        )
        or re.search(
            r"\bapple\b.{0,32}\b(?:pull(?:s|ed)?|remove(?:s|d)?|delist(?:s|ed)?)\b"
            r".{0,36}\b(?:app|application)\b|"
            r"(?:苹果).{0,28}(?:下架|移除|撤下).{0,28}(?:应用|\bapp\b)|"
            r"(?:应用|\bapp\b).{0,28}(?:遭|被).{0,12}(?:苹果).{0,12}(?:下架|移除|撤下)",
            f"{title_text}. {primary_lead}",
            re.I,
        )
    )
    support_capability_removal = any(
        key.endswith(
            (
                ":intel-support-removal",
                ":platform-support-removal",
                ":compatibility-support-removal",
            )
        )
        for key in primary_claim_events
    )
    if removal_stage and app_store_removal_context and not support_capability_removal:
        removal_subjects = _app_store_subjects(title_text, identity)
        removal_attributions = {
            component.removeprefix("report-attribution:")
            for component in identity.components
            if component.startswith("report-attribution:")
        }
        incident_event_keys = {
            key
            for key in event_keys
            if key.startswith("structured-assertion:app-store:")
        }
        incident_event_keys |= {
            f"app-store-removal-report:{attribution}:{removal_stage}"
            for attribution in removal_attributions
        }
        incident_boundaries = {
            key
            for key in boundary_keys
            if key.startswith("structured-subject:app-store:")
        }
        event_keys = incident_event_keys | {
            f"app-store-removal:{subject}:{removal_stage}"
            for subject in removal_subjects
        }
        boundary_keys = incident_boundaries | {
            f"app-store-removal:{subject}"
            for subject in removal_subjects
        }

    region_values = sorted(region for region in regions if region != "multi-region")
    if _annual_sales_metric(text):
        region_key = ",".join(region_values) or "global"
        event_keys.add(f"apple-market:annual-sales:{region_key}")
        boundary_keys.add("apple-market:annual-sales")
        category_hint = "hardware_products"

    if content_form != "roundup" and _multi_product_price_forecast(text):
        event_keys.add("apple-market:multi-product-price-forecast")
        boundary_keys.add("apple-market:multi-product-price-forecast")
        category_hint = "hardware_products"

    trade_in_change = bool(
        (
            "trade-in-valuation" in identity.components
            or re.search(r"\btrade[ -]in\s+(?:value|values|offer|offers|estimate|estimates|deal|deals)\b", text)
            or _contains(text, "以旧换新", "折抵价", "折抵估值")
        )
        and (
            "price-change" in identity.actions
            or _contains(text, "raises", "increases", "updates", "adjusts", "sweetens", "bumps", "上调", "提高", "调整", "下调", "升值")
        )
        and _contains(title_text, "apple", "iphone", "ipad", "mac", "苹果")
    )
    if trade_in_change:
        event_keys.add("apple-retail:trade-in-valuation-change")
        boundary_keys.add("apple-retail:trade-in-valuation-change")
        separation_keys.add("action:trade-in-valuation-change")
        category_hint = "hardware_products"

    if (
        _contains(
            title_text,
            "premium smartphone market",
            "high-end smartphone market",
            "高端智能手机市场",
            "高端手机市场",
            "全球高端手机市场",
        )
        and (
            _contains(text, "market share", "share", "份额", "accounted for", "占据")
            or re.search(r"\bholds?\s+\d+(?:\.\d+)?\s*%", text)
        )
        and _contains(title_text, "apple", "iphone", "苹果")
    ):
        event_keys.add("apple-market:premium-smartphone-share")
        boundary_keys.add("apple-market:premium-smartphone-share")
        separation_keys.add("action:measured-market-share")
        category_hint = "hardware_products"

    generations = _component_values(identity, "iphone-generation:") | {
        value.removeprefix("iphone-")
        for value in _component_values(identity, "product-generation:")
        if value.startswith("iphone-")
    }
    title_supply_constraint = _contains(
        title_text,
        "dram",
        "ram supply",
        "memory shortage",
        "limited availability",
        "scrambling to secure memory",
        "sell out fast",
        "量产遇挑战",
        "紧急抢购内存",
        "内存短缺",
        "供货受限",
    )
    supply_constraint = bool(
        generations
        and title_supply_constraint
        and _contains(text, "dram", "ram", "memory", "内存")
        and _contains(
            text,
            "shortage",
            "limited availability",
            "supply constraint",
            "holding up",
            "sell out fast",
            "scrambling to secure",
            "production challenge",
            "短缺",
            "供货受限",
            "供应受限",
            "量产遇挑战",
            "紧急抢购",
        )
    )
    if supply_constraint:
        for generation in generations:
            event_keys.add(f"apple-supply:iphone-{generation}:memory-constraint")
        if _contains(text, "a20"):
            event_keys.add("apple-supply:a20:memory-constraint")
        boundary_keys.add("apple-supply:iphone-memory-constraint")
        separation_keys.add("action:product-supply-constraint")
        category_hint = "hardware_products"

    a20_memory_constraint = bool(
        _contains(text, "a20")
        and _contains(text, "dram", "ram", "memory", "内存")
        and _contains(
            text,
            "cannot be packaged",
            "unable to package",
            "packaging backlog",
            "without memory chips",
            "holding up",
            "无法封装",
            "无内存芯片搭配",
            "积压",
        )
    )
    if a20_memory_constraint:
        event_keys.add("apple-supply:a20:memory-constraint")
        boundary_keys.add("apple-supply:iphone-memory-constraint")
        separation_keys.add("action:product-supply-constraint")
        category_hint = "hardware_products"

    memory_suppliers = {
        supplier
        for supplier, aliases in {
            "cxmt": ("cxmt", "changxin", "长鑫"),
            "ymtc": ("ymtc", "yangtze memory", "长江存储"),
        }.items()
        if _contains(text, *aliases)
    }
    title_memory_negotiation = bool(
        _contains(title_text, "apple", "iphone", "苹果")
        and _contains(title_text, "bid", "leverage", "denies", "talks", "negot", "筹码", "谈判", "议价", "压价", "定价权")
    )
    title_has_apple_subject = _contains(title_text, "apple", "iphone", "苹果", "库克")
    if memory_suppliers and (
        title_memory_negotiation
        or (
            title_has_apple_subject
            and
            any(alias in title_text for aliases in {
                "cxmt": ("cxmt", "changxin", "长鑫"),
                "ymtc": ("ymtc", "yangtze memory", "长江存储"),
            }.values() for alias in aliases)
            and _contains(text, "talks", "negot", "procure", "source", "buy", "洽谈", "谈判", "采购", "议价")
        )
    ):
        event_keys.add("apple-sourcing:memory:china-suppliers:negotiation")
        boundary_keys.add("apple-sourcing:memory-negotiation")
        separation_keys.add("action:memory-supplier-negotiation")
        category_hint = "hardware_products"

    memory_policy_action = bool(
        memory_suppliers
        and _contains(text, "white house", "trump", "特朗普", "白宫")
        and _contains(text, "apple", "iphone", "苹果", "cook", "库克")
        and _contains(text, "petition", "lobby", "allow", "approval", "reject", "游说", "允许", "批准", "拒绝")
    )
    if memory_policy_action:
        event_keys.add("apple-policy:restricted-memory-supplier-approval")
        boundary_keys.add("apple-policy:restricted-memory-supplier-approval")
        separation_keys.add("action:memory-supplier-policy")
        category_hint = "hardware_products"

    macbook_models = _component_values(identity, "macbook-model:")
    refurbished_store_action = _official_refurbished_store_action(text)
    macbook_roadmap_action = bool(
        not refurbished_store_action
        and (relevance_tier != "weak" or trusted_direct_action)
        and content_form == "news"
        and (
            identity.actions & {"delay-roadmap", "pilot-testing"}
            or (
                _contains(
                    title_text,
                    "upgrade options",
                    "coming",
                    "coming soon",
                    "upcoming",
                    "路线图",
                    "即将",
                    "将推出",
                    "来袭",
                    "首发",
                )
                and _contains(
                    text,
                    "report",
                    "plans",
                    "expected",
                    "rumored",
                    "this fall",
                    "消息称",
                    "据称",
                    "计划",
                    "预计",
                    "传闻",
                    "今秋",
                )
            )
        )
    )
    if macbook_models and refurbished_store_action:
        event_keys.add("canonical-apple-action:official-refurbished-catalog:catalog-expansion")
        boundary_keys.add("canonical-apple-action:official-refurbished-catalog:catalog-expansion")
        for model in macbook_models:
            event_keys.add(f"apple-retail:refurbished:macbook-{model}")
        boundary_keys.add("apple-retail:refurbished-macbook")
        separation_keys.add("action:official-refurbished-availability")
        category_hint = "hardware_products"
    elif macbook_models and macbook_roadmap_action:
        for model in macbook_models:
            event_keys.add(f"apple-roadmap:macbook-{model}")
            separation_keys.add(f"product-model:macbook-{model}")
        boundary_keys.add("apple-roadmap:macbook")
        separation_keys.add("action:product-roadmap")
        category_hint = "hardware_products"

    anniversary_milestone = _product_anniversary_milestone(title_text)
    if anniversary_milestone:
        product, years = anniversary_milestone
        event_keys.add(f"apple-product-anniversary:{product}:{years}")
        boundary_keys.add(f"apple-product-anniversary:{product}")
        separation_keys.add("action:product-anniversary")
        category_hint = "hardware_products"

    screening_subject = _content_screening_subject(title, lead)
    if (
        screening_subject
        and "apple-tv" in identity.products
        and _contains(text, "theater", "theatre", "cinema", "screening", "screenings", "影院", "放映")
    ):
        event_keys.add(f"apple-tv-content:{screening_subject}:screening")
        boundary_keys.add("apple-tv-content:screening")
        separation_keys.add(f"content-title:{screening_subject}")

    if _bug_bounty_submission_limit(text):
        event_keys.add("apple-security:bug-bounty-submission-limit")
        boundary_keys.add("apple-security:bug-bounty-submission-limit")

    if _icloud_private_relay_leak(text) or _webkit_proxy_leak(text):
        event_keys.add("apple-security:webkit-private-relay-network-leak")
        boundary_keys.add("apple-security:webkit-private-relay-network-leak")

    applied_research_key = _measured_applied_research_key(text, identity)
    if applied_research_key:
        event_keys.add(applied_research_key)
        boundary_keys.add(":".join(applied_research_key.split(":")[:3]))
        category_hint = "hardware_products"

    market_forecast_key = _product_driven_market_forecast_key(text, identity)
    if market_forecast_key:
        event_keys.add(market_forecast_key)
        boundary_keys.add(":".join(market_forecast_key.split(":")[:3]))
        category_hint = "hardware_products"

    # Existing exact action facets are stronger than a generic OS/version
    # scope. Let the exact facet reconcile translations and headline variants
    # instead of creating competing feature identities for the same action.
    os_feature_scope = _versioned_os_feature_scope(text, identity)
    if exact and os_feature_scope and not os_feature_scope.startswith("apple-os-release-wave:"):
        os_feature_scope = ""
    if os_feature_scope:
        event_keys.add(os_feature_scope)
        boundary_keys.add(os_feature_scope)
        if os_feature_scope.startswith("apple-os-release-wave:"):
            for platform_wave in sorted(
                component.removeprefix("os-wave-platform:")
                for component in identity.components
                if component.startswith("os-wave-platform:")
            ):
                event_keys.add(
                    f"apple-os-platform-release-wave:{platform_wave}"
                )

    report_attributions = sorted(
        component.removeprefix("report-attribution:")
        for component in identity.components
        if component.startswith("report-attribution:")
    )
    report_subjects = sorted(
        component
        for component in identity.components
        if component.startswith(
            (
                "iphone-model:",
                "iphone-family:",
                "macbook-model:",
                "product-generation:",
            )
        )
    )
    report_components = sorted(
        component
        for component in identity.components & LEAD_IDENTITY_COMPONENTS
        if not component.startswith("primary-intent:")
    )
    if report_attributions and report_subjects and report_components:
        for attribution in report_attributions:
            for subject in report_subjects:
                for component in report_components:
                    event_keys.add(
                        f"structured-report:{attribution}:{subject}:{component}"
                    )

    structured_components = sorted(
        identity.components & (LEAD_IDENTITY_COMPONENTS | EVIDENCE_BACKED_COMPONENTS)
    )
    structured_subjects = sorted(
        subject
        for subject in identity.named_subjects
        if subject
        not in {
            "apple",
            "apple-vision",
            "iphone",
            "ipad",
            "mac",
            "macbook",
        }
    )
    canonical_subjects = {
        subject.removeprefix("apple-")
        for subject in structured_subjects
        if subject.startswith("apple-")
    }
    canonical_subjects = {
        subject
        for subject in canonical_subjects
        if not any(
            other != subject and other.startswith(f"{subject}-")
            for other in canonical_subjects
        )
    }
    product_subjects = {
        subject.removeprefix("apple-")
        for subject in structured_subjects
        if subject.startswith("apple-")
    }
    product_subjects = {
        subject
        for subject in product_subjects
        if not any(
            other != subject and subject.startswith(f"{other}-")
            for other in product_subjects
        )
    }
    explicit_first_party_subjects = {
        subject.removeprefix("apple-")
        for subject in identity.title_named_subjects
        if subject.startswith("apple-")
    } | {
        component.removeprefix("evidence-named-subject:apple-")
        for component in identity.components
        if component.startswith("evidence-named-subject:apple-")
    }
    product_aliases = {
        product.removeprefix("apple-")
        for product in identity.products | identity.title_products
    }
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not identity.counterparties
        and not identity.case_topics
    ):
        for subject in sorted(product_subjects & explicit_first_party_subjects):
            if "-" in subject and subject not in product_aliases:
                event_keys.add(f"structured-first-party-subject:{subject}")
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not identity.counterparties
        and not identity.case_topics
        and canonical_subjects
        and identity.title_actions
    ):
        for subject in sorted(canonical_subjects):
            for action in sorted(identity.title_actions):
                event_keys.add(f"structured-subject-action:{subject}:{action}")
    if (
        identity.scope == "apple-direct"
        and identity.content_form == "news"
        and not identity.counterparties
        and not identity.case_topics
        and not any(
            component.startswith(("os-wave:", "os-wave-platform:"))
            for component in identity.components
        )
        and product_subjects
        and identity.title_products
    ):
        for subject in sorted(product_subjects):
            for product in sorted(identity.title_products):
                normalized_product = product.removeprefix("apple-")
                if (
                    subject == product
                    or subject == normalized_product
                    or subject.endswith(f"-{product}")
                ):
                    continue
                event_keys.add(f"structured-subject-product:{subject}:{product}")
    if structured_components and identity.title_products:
        for component in structured_components:
            for product in sorted(identity.title_products):
                if not report_attributions:
                    event_keys.add(
                        f"structured-component:{component}:{product}"
                    )
                for subject in structured_subjects:
                    event_keys.add(
                        f"structured-component:{component}:{product}:{subject}"
                    )

    if _apple_first_party_home_camera_roadmap(title_text, text):
        event_keys.add("apple-home:first-party-security-camera-roadmap")
        boundary_keys.add("apple-home:first-party-security-camera-roadmap")
        separation_keys.add("action:first-party-home-camera-roadmap")
        category_hint = "software_systems"

    event_staff_support = _event_staff_support(text)
    event_preparation = _event_preparation(text)
    event_format_plan = _event_format_plan(text)
    if event_staff_support:
        event_keys.add("apple-event:staff-support-lottery")
        boundary_keys.add("apple-event:staff-support-lottery")
    if event_staff_support or event_preparation or event_format_plan:
        event_keys.add("apple-event:september-operations")
        boundary_keys.add("apple-event:september-operations")

    if "airpods" in text and _contains(text, "firmware", "固件") and _contains(
        text,
        "beta",
        "testing",
        "developer",
        "测试版",
        "公测",
        "开发者",
    ):
        event_keys.add("apple-firmware:airpods-beta")
        boundary_keys.add("apple-firmware:airpods-beta")

    display_metrics = _display_metrics(text)
    anniversary_display = bool(
        re.search(
            r"\b20th\s+anniversary\b|\btwentieth\s+anniversary\b|"
            r"\biphone\s*20\b|20\s*周年|二十周年",
            text,
        )
    )
    if (
        (display_metrics or _contains(text, "larger screen", "larger display", "更大尺寸屏幕", "屏幕尺寸增大"))
        and _contains(text, "iphone")
        and _contains(text, "display", "screen", "屏幕")
        and _contains(text, "rumor", "leak", "prototype", "testing", "传闻", "爆料", "测试")
    ):
        event_keys |= {
            f"iphone-display-rumor:size:{metric}"
            for metric in display_metrics
        }
        boundary_keys.add("iphone-display-rumor")
        separation_keys.add("product-family:iphone")
        if anniversary_display:
            event_keys.add("iphone-display-rumor:anniversary-size-change")

    legal_case = _legal_case_key(identity)
    legal_stage = _legal_action_stage(title_text, text[len(title_text) :])
    legal_parties = sorted(
        (identity.counterparties - {"secrets", "lawsuit"})
        | _legal_title_parties(title_text)
    )
    if not legal_case and legal_parties:
        legal_case = ":".join(legal_parties)
    direct_legal_action = bool(
        legal_stage
        and legal_case
        and _contains(title_text, "apple", "苹果")
    )
    if (
        ("legal" in identity.actions or "apple-hardware-trade-secret-lawsuit" in exact)
        and legal_case
        and legal_stage
        and (relevance_tier != "weak" or trusted_direct_action or direct_legal_action)
    ):
        event_keys.add(f"apple-legal:{legal_case}:{legal_stage}")
        event_keys |= {
            f"apple-legal-party:{party}:{legal_stage}"
            for party in legal_parties
        }
        boundary_keys.add(f"apple-legal-case:{legal_case}")
        boundary_keys |= {
            f"apple-legal-party:{party}"
            for party in legal_parties
        }
        separation_keys |= {
            f"legal-party:{party}"
            for party in legal_parties
        }
        separation_keys.add(f"legal-stage:{legal_stage}")

    primary_intents = {
        component
        for component in identity.title_components
        if component.startswith("primary-intent:")
    }
    separation_keys |= {
        f"action:{intent.split(':', 1)[1]}"
        for intent in primary_intents
        if intent.split(":", 1)[1]
        in {"product-price-change", "product-supply-constraint", "memory-supplier-policy", "compute-capacity-risk"}
    }
    if "feature-change" in identity.title_actions and identity.title_products:
        separation_keys.add("action:feature-change")

    if (
        content_form == "event_preview"
        and not event_format_plan
        and "primary-claim:apple-product-catalog:multi-product-withdrawal-forecast"
        not in primary_claim_events
    ):
        # Background facts in an editorial preview must not impersonate the
        # concrete actions they recap.
        event_keys.clear()
        boundary_keys.clear()

    unverified_final_os_schedule = bool(
        any(
            component.startswith(("os-wave:", "os-wave-platform:"))
            and component.endswith(":final")
            for component in identity.components
        )
        and "retail-availability" in identity.title_actions
        and not _lead_asserts_first_party_release(title_text)
        and not _lead_asserts_first_party_release(lead)
        and not _has_absolute_calendar_date(
            f"{title_text}. {_primary_assertion_scope('', lead)[1]}"
        )
    )
    versioned_os_action = bool(
        _versioned_os_feature_report(text, identity)
        and not unverified_final_os_schedule
    )
    current_generation_product_report = any(
        ":generation-product-refresh" in key
        for key in primary_claim_events
    )
    current_beta_asset_disclosure = any(
        ":unintended-product-asset-disclosure" in key
        for key in primary_claim_events
    )
    current_event_schedule_report = any(
        ":schedule-forecast" in key
        for key in primary_claim_events
    )
    release_announcement_keys = {
        key
        for key in event_keys
        if key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:"))
    }
    if versioned_os_action and release_announcement_keys:
        separation_keys.add("predicate:os-release-announcement")
    editorial_inference_without_new_reporting = bool(
        unverified_final_os_schedule
        or (
            not editorial_first_party_action
            and
            not versioned_os_action
            and not versioned_os_compatibility_action
            and not current_generation_product_report
            and not current_beta_asset_disclosure
            and not current_event_schedule_report
            and not event_format_plan
            and not exact
            and not structured_direct_assertion
            and content_form
            in {
                "analysis",
                "buying_advice",
                "deal",
                "event_preview",
                "hands_on",
                "podcast",
                "poll",
                "review",
                "roundup",
                "third_party_spotlight",
                "tutorial",
                "user_anecdote",
            }
        )
    )
    trusted_direct_action = bool(
        not editorial_inference_without_new_reporting
        and (
            caller_trusted_direct_action
            or title_owned_direct_action
            or direct_product_lifecycle_action
            or (primary_claim_trusted and content_form == "news")
            or (bool(content_claim) and content_form == "news")
            or (
                (trusted_direct_action or structured_direct_assertion)
                and _title_proves_first_party_subject(title_text, identity)
            )
            or editorial_first_party_action
        )
    )
    measured_apple_market_action = any(
        key.startswith("structured-market-result:")
        and ":apple-percent:" in key
        for key in event_keys
    )
    structural_direct_action = (
        trusted_direct_action
        or measured_apple_market_action
        or versioned_os_action
        or tracking_transparency_policy_action
        or bool(first_party_service_capability_signal)
        or official_apple_store_transaction_option_action
        or versioned_os_compatibility_action
        or direct_product_lifecycle_action
    )
    promotion_reason = ""
    if versioned_os_action:
        promotion_reason = "current versioned Apple OS release or feature report"
    elif versioned_os_compatibility_action:
        promotion_reason = "current Apple OS device and feature compatibility matrix"
    elif first_party_service_capability_signal:
        promotion_reason = "title-led first-party service capability action"
    elif official_apple_store_transaction_option_action:
        promotion_reason = "official Apple Store checkout or financing option change"
    elif measured_apple_market_action:
        promotion_reason = "measured Apple market result with report, region, period, and value"
    elif direct_product_lifecycle_action:
        promotion_reason = "official Apple product lifecycle and repair-support change"
    elif trusted_direct_action:
        promotion_reason = "title-led direct Apple action confirmed by structured identity"
    elif editorial_first_party_action:
        promotion_reason = "current first-party Apple action independently stated by editorial source"
    defer_reason = _unsupported_third_party_reason(
        title,
        text,
        identity,
        exact,
        relevance_tier,
        structural_direct_action,
    )
    if third_party_app_availability and not defer_reason:
        defer_reason = (
            "third-party app availability without an Apple platform change"
        )
    if event_format_plan:
        # A concrete, currently reported operating format is itself the event
        # action; an analytical headline angle must not demote that evidence.
        defer_reason = ""
    if direct_product_lifecycle_action:
        defer_reason = ""
    if editorial_first_party_action:
        defer_reason = ""
    if (
        not event_format_plan
        and not company_performance_subject
        and _retrospective_explainer_without_new_action(
            title,
            f"{text}. {_normalized(evidence)[:1800]}",
        )
    ):
        defer_reason = "analysis or explanation without a new title-led Apple action"
    if (
        not defer_reason
        and relevance_tier == "weak"
        and relevance_reason.startswith("broad multi-vendor market")
    ):
        defer_reason = relevance_reason
    hard_boundary = _hard_third_party_boundary(text, defer_reason)
    if editorial_inference_without_new_reporting:
        if not defer_reason:
            defer_reason = (
                f"editorial {content_form.replace('_', ' ')} without a new Apple action"
            )
        hard_boundary = "editorial-inference-without-new-reporting"
    if defer_reason:
        structural_direct_action = False
    resolved_relevance_tier = relevance_tier
    if defer_reason:
        resolved_relevance_tier = "weak"
    elif relevance_tier == "weak" and structural_direct_action:
        resolved_relevance_tier = "strong"
    if (
        not hard_boundary
        and not structural_direct_action
        and resolved_relevance_tier == "weak"
        and "legal" not in identity.actions
        and relevance_reason.startswith(
            (
                "third-party AI model",
                "third-party app update",
                "third-party employer asset disposal",
                "analysis repackaging",
                "non-Apple component or industry",
                "non-Apple primary subject",
                "non-Apple title action",
                "third-party or non-Apple subject",
            )
        )
    ):
        hard_boundary = "independent-non-apple-or-editorial-action"
    if resolved_relevance_tier == "weak":
        weak_topic = _weak_topic_separation_key(title_text)
        if weak_topic:
            separation_keys.add(weak_topic)
    supplier_workforce_action = bool(
        _contains(
            title_text,
            "hire",
            "hires",
            "hiring",
            "recruit",
            "recruits",
            "recruiting",
            "招聘",
            "扩招",
            "招工",
            "增聘",
        )
        and identity.title_products
    )
    supplier_operating_result = bool(
        _contains(text, "ship", "ships", "shipped", "shipment", "shipments", "出货", "供应")
        and _contains(text, "supplier", "display", "panel", "component", "供应商", "面板", "零部件")
        and bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|million|billion)\b|\d+(?:\.\d+)?\s*(?:万|亿|%)", text))
    )
    if supplier_workforce_action:
        separation_keys.add("primary-claim-predicate:supplier-workforce-expansion")
    if supplier_operating_result:
        separation_keys.add("primary-claim-predicate:supplier-operating-result")
    title_owned_versioned_os_feature = bool(
        event_kind == "os_app"
        and re.match(
            r"^(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+)*\b",
            title_text,
            re.I,
        )
        and not (
            re.search(
                r"\b(?:hint(?:s|ed)?\s+at|reveal(?:s|ed)?|leak(?:s|ed)?|code\s+(?:shows?|suggests?))\b|"
                r"(?:代码|文件).{0,18}(?:暗示|曝光|泄露)",
                title_text,
                re.I,
            )
            and identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        )
    )
    if primary_claim_category:
        # A title-led concrete claim owns the event category. Later generic
        # product/background rules may enrich the profile, but must not turn a
        # system disclosure into hardware (or a procurement action into
        # software) based on incidental entities in the article body.
        category_hint = primary_claim_category
    elif title_owned_versioned_os_feature:
        category_hint = "software_systems"
    elif any(
        key.startswith("structured-assertion:apple-facility:education-center:opening")
        for key in event_keys
    ):
        category_hint = "software_systems"
    elif any(
        key.startswith("structured-assertion:apple-facility:")
        for key in event_keys
    ):
        category_hint = "hardware_products"
    elif (
        identity.title_products & _HARDWARE_FIRST_PARTY_PRODUCTS
        and any(
            key.startswith("structured-title-action:apple-silicon-generation:")
            for key in event_keys
        )
    ):
        category_hint = "hardware_products"
    return ReconciliationProfile(
        event_keys=frozenset(event_keys),
        boundary_keys=frozenset(boundary_keys),
        exact_facets=exact,
        separation_keys=frozenset(separation_keys),
        defer_reason=defer_reason,
        category_hint=category_hint,
        hard_boundary=hard_boundary,
        identity=identity,
        relevance_tier=resolved_relevance_tier,
        trusted_direct_action=structural_direct_action,
        promotion_reason=promotion_reason,
    )


def _profiles_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    if any(
        key.startswith("primary-claim:")
        for key in left.event_keys & right.event_keys
    ):
        # Exact primary claims encode both canonical subject and concrete
        # action. They are stronger identity evidence than incidental product
        # names or background actors elsewhere in either page.
        return False
    if _direct_title_subject_conflict(left, right):
        return True
    if _direct_title_action_conflict(left, right):
        return True
    if _weak_editorial_profile(left) != _weak_editorial_profile(right):
        return True
    if left.identity is not None and right.identity is not None:
        shared_action_keys = {
            key
            for key in left.event_keys & right.event_keys
            if key.startswith(
                (
                    "apple-os-release-wave:",
                    "canonical-apple-action:",
                    "structured-assertion:",
                )
            )
        }
        if (
            (left.identity.content_form == "roundup")
            != (right.identity.content_form == "roundup")
            and not (left.exact_facets & right.exact_facets)
            and not shared_action_keys
        ):
            return True
        left_services = left.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        right_services = right.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        if (
            left_services
            and right_services
            and left_services.isdisjoint(right_services)
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_release = {
        key for key in left.event_keys if key.startswith("apple-os-release-wave:")
    }
    right_release = {
        key for key in right.event_keys if key.startswith("apple-os-release-wave:")
    }
    left_features = {
        key for key in left.event_keys if key.startswith("apple-os-feature-scope:")
    }
    right_features = {
        key for key in right.event_keys if key.startswith("apple-os-feature-scope:")
    }
    shared_non_os_keys = {
        key
        for key in left.event_keys & right.event_keys
        if not key.startswith(("apple-os-release-wave:", "apple-os-feature-scope:"))
    }
    if (
        not shared_non_os_keys
        and ((left_release and right_features) or (right_release and left_features))
    ):
        return True
    shared_boundaries = left.boundary_keys & right.boundary_keys
    if shared_boundaries and left.event_keys and right.event_keys and not (left.event_keys & right.event_keys):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary):
        hard_boundary = left.hard_boundary or right.hard_boundary
        if hard_boundary == "independent-third-party-action":
            return True
        if not (left.event_keys & right.event_keys):
            return True
    return False


def _explicit_property_value_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    """Contradictory property values outrank an otherwise shared quantity."""
    left_values = {key for key in left.separation_keys if key.startswith("finish-alternatives:")}
    right_values = {key for key in right.separation_keys if key.startswith("finish-alternatives:")}
    return bool(left_values and right_values and left_values.isdisjoint(right_values))


def _weak_editorial_profile(profile: ReconciliationProfile) -> bool:
    identity = profile.identity
    return bool(
        profile.relevance_tier == "weak"
        and not profile.trusted_direct_action
        and identity is not None
        and identity.content_form
        in {
            "analysis",
            "buying_advice",
            "deal",
            "hands_on",
            "podcast",
            "review",
            "roundup",
            "third_party_spotlight",
            "tutorial",
            "user_anecdote",
        }
    )


def _near_identifier(left_value: str, right_value: str) -> bool:
    if left_value == right_value:
        return True
    if min(len(left_value), len(right_value)) < 6:
        return False
    if abs(len(left_value) - len(right_value)) > 1:
        return False
    shorter, longer = sorted((left_value, right_value), key=len)
    if len(shorter) == len(longer):
        return sum(a != b for a, b in zip(shorter, longer)) <= 1
    mismatch = 0
    short_index = 0
    for character in longer:
        if short_index < len(shorter) and shorter[short_index] == character:
            short_index += 1
            continue
        mismatch += 1
        if mismatch > 1:
            return False
    return True


def _content_work_profile(profile: ReconciliationProfile) -> tuple[set[str], set[str]]:
    titles = {
        key.removeprefix("content-title:")
        for key in profile.separation_keys
        if key.startswith("content-title:")
    }
    actions = {
        key.removeprefix("content-action:")
        for key in profile.separation_keys
        if key.startswith("content-action:")
    }
    return titles, actions


def _compatible_content_work_profiles(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    left_titles, left_actions = _content_work_profile(left)
    right_titles, right_actions = _content_work_profile(right)
    return bool(
        left_titles
        and right_titles
        and any(
            _near_identifier(left_title, right_title)
            for left_title in left_titles
            for right_title in right_titles
        )
        and left_actions | right_actions <= {"new-project", "premiere-schedule"}
    )


def _explicit_separation_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    """Keep explicit product/action boundaries authoritative during reunion."""
    for disclosure, other in ((left, right), (right, left)):
        if (
            "primary-claim-predicate:finish-lineup-disclosure" in disclosure.separation_keys
            and "primary-claim-predicate:finish-lineup-disclosure" not in other.separation_keys
            and other.identity is not None
            and "product-launch" in other.identity.title_actions
        ):
            return True
    left_content_titles = {
        key.removeprefix("content-title:")
        for key in left.separation_keys
        if key.startswith("content-title:")
    }
    right_content_titles = {
        key.removeprefix("content-title:")
        for key in right.separation_keys
        if key.startswith("content-title:")
    }
    related_content_title = any(
        _near_identifier(left_title, right_title)
        for left_title in left_content_titles
        for right_title in right_content_titles
    )
    if related_content_title:
        content_actions = {
            key.removeprefix("content-action:")
            for key in left.separation_keys | right.separation_keys
            if key.startswith("content-action:")
        }
        if content_actions <= {"new-project", "premiere-schedule"}:
            return False

    def market_regions(profile: ReconciliationProfile) -> set[str]:
        return {
            key.split(":", 4)[2]
            for key in profile.event_keys
            if key.startswith("structured-market-result:")
            and len(key.split(":", 4)) == 5
        }

    left_market_regions = market_regions(left)
    right_market_regions = market_regions(right)
    if (
        left_market_regions
        and right_market_regions
        and left_market_regions.isdisjoint(right_market_regions)
    ):
        return True
    shared_release_keys = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:"))
    }
    if (
        shared_release_keys
        and "predicate:os-release-announcement" in left.separation_keys
        and "predicate:os-release-announcement" in right.separation_keys
    ):
        return False
    left_facility_assertions = {
        key
        for key in left.event_keys
        if key.startswith("structured-assertion:apple-facility:")
    }
    right_facility_assertions = {
        key
        for key in right.event_keys
        if key.startswith("structured-assertion:apple-facility:")
    }
    if bool(left_facility_assertions) != bool(right_facility_assertions):
        return True
    shared_assertions = {
        key
        for key in left.event_keys & right.event_keys
        if key.startswith("structured-assertion:")
    }
    if shared_assertions:
        return False

    def pending_order_predicates(profile: ReconciliationProfile) -> set[str]:
        return {
            key.removeprefix("primary-claim-predicate:")
            for key in profile.separation_keys
            if key.startswith("primary-claim-predicate:pending-order-")
        }

    left_pending_order = pending_order_predicates(left)
    right_pending_order = pending_order_predicates(right)
    if left_pending_order != right_pending_order and (
        left_pending_order or right_pending_order
    ):
        return True
    for namespace in (
        "assertion-subject:",
        "assertion-action:",
        "content-title:",
        "content-action:",
        "os-feature-subject:",
        "primary-claim-subject:",
        "primary-claim-predicate:",
        "changed-object:",
        "finish-alternatives:",
        "product-family:",
        "product-model:",
        "legal-party:",
        "market-report-scope:",
    ):
        left_values = {
            key for key in left.separation_keys if key.startswith(namespace)
        }
        right_values = {
            key for key in right.separation_keys if key.startswith(namespace)
        }
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    left_assertion_actions = {
        key.removeprefix("assertion-action:")
        for key in left.separation_keys
        if key.startswith("assertion-action:")
    }
    right_assertion_actions = {
        key.removeprefix("assertion-action:")
        for key in right.separation_keys
        if key.startswith("assertion-action:")
    }
    left_title_actions = {
        key.removeprefix("action:")
        for key in left.separation_keys
        if key.startswith("action:")
    }
    right_title_actions = {
        key.removeprefix("action:")
        for key in right.separation_keys
        if key.startswith("action:")
    }
    left_predicates = {
        key.removeprefix("predicate:")
        for key in left.separation_keys
        if key.startswith("predicate:")
    }
    right_predicates = {
        key.removeprefix("predicate:")
        for key in right.separation_keys
        if key.startswith("predicate:")
    }
    lifecycle_action = "product-lifecycle-obsolete"
    if (
        lifecycle_action in left_assertion_actions
        and lifecycle_action not in right_assertion_actions
    ) or (
        lifecycle_action in right_assertion_actions
        and lifecycle_action not in left_assertion_actions
    ):
        return True
    return False


def _release_wave_parts(key: str) -> tuple[str, str, str]:
    value = key.removeprefix("apple-os-release-wave:")
    parts = value.split(":", 2)
    version, stage = parts[:2]
    return version, stage, parts[2] if len(parts) == 3 else ""


def _release_waves_conflict(
    left_release: set[str],
    right_release: set[str],
) -> bool:
    if not left_release or not right_release or not left_release.isdisjoint(right_release):
        return False
    return not all(
        left_stage == right_stage
        and (
            not left_platform
            or not right_platform
            or left_platform == right_platform
        )
        and (
            left_version == right_version
            or left_version.startswith(f"{right_version}.")
            or right_version.startswith(f"{left_version}.")
        )
        for left_key in left_release
        for right_key in right_release
        for left_version, left_stage, left_platform in [_release_wave_parts(left_key)]
        for right_version, right_stage, right_platform in [_release_wave_parts(right_key)]
    )


def _profile_release_stages(profile: ReconciliationProfile) -> set[str]:
    stages: set[str] = set()
    for key in profile.event_keys:
        if key.startswith("apple-os-release-wave:"):
            _version, stage, _platform = _release_wave_parts(key)
            stages.add(stage)
        elif key.startswith("apple-os-platform-release-wave:"):
            _platform, stage = key.removeprefix(
                "apple-os-platform-release-wave:"
            ).split(":", 1)
            stages.add(stage)
    return stages


def _profile_release_channels(profile: ReconciliationProfile) -> set[str]:
    identity = profile.identity
    if identity is None:
        return set()
    return {
        component.removeprefix("os-release-channel:")
        for component in identity.components
        if component.startswith("os-release-channel:")
    }


def _profile_release_conflict(
    left: ReconciliationProfile,
    right: ReconciliationProfile,
) -> bool:
    left_release = {
        key for key in left.event_keys if key.startswith("apple-os-release-wave:")
    }
    right_release = {
        key for key in right.event_keys if key.startswith("apple-os-release-wave:")
    }
    if _release_waves_conflict(left_release, right_release):
        return True
    left_stages = _profile_release_stages(left)
    right_stages = _profile_release_stages(right)
    if left_stages and right_stages and left_stages.isdisjoint(right_stages):
        return True
    left_channels = _profile_release_channels(left)
    right_channels = _profile_release_channels(right)
    return bool(
        left_channels
        and right_channels
        and left_channels.isdisjoint(right_channels)
    )


def _seed_profiles_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    """Return only conflicts strong enough to split an accepted seed event."""
    if _direct_title_subject_conflict(left, right):
        return True
    if _direct_title_action_conflict(left, right):
        return True
    if _weak_editorial_profile(left) != _weak_editorial_profile(right):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary):
        hard_boundary = left.hard_boundary or right.hard_boundary
        if hard_boundary == "independent-third-party-action":
            return True
    catalog_lifecycle_key = (
        "primary-claim:apple-product-catalog:multi-product-withdrawal-forecast"
    )
    if (catalog_lifecycle_key in left.event_keys) != (
        catalog_lifecycle_key in right.event_keys
    ):
        # A catalog-wide withdrawal is one aggregate lifecycle action. Product
        # names in its enumerated list cannot attach it to a single-model
        # launch, specification, or availability story before exact reunion.
        return True
    if (
        left.relevance_tier == "weak"
        and right.relevance_tier == "weak"
        and left.identity is not None
        and right.identity is not None
        and left.identity.scope == "third-party-context"
        and right.identity.scope == "third-party-context"
        and not (left.event_keys & right.event_keys)
        and not (left.exact_facets & right.exact_facets)
    ):
        left_specific_subjects = (
            left.identity.named_subjects
            | left.identity.actors
            | left.identity.counterparties
        ) - left.identity.title_products
        right_specific_subjects = (
            right.identity.named_subjects
            | right.identity.actors
            | right.identity.counterparties
        ) - right.identity.title_products
        if not (left_specific_subjects & right_specific_subjects):
            return True
    if _explicit_separation_conflict(left, right):
        return True
    campaign_prefixes = ("apple-event-campaign:", "apple-event-occurrence:")
    left_event_campaigns = {
        key for key in left.event_keys if key.startswith(campaign_prefixes)
    }
    right_event_campaigns = {
        key for key in right.event_keys if key.startswith(campaign_prefixes)
    }
    if bool(left_event_campaigns) != bool(right_event_campaigns):
        # A campaign announcement or official campaign asset is not the same
        # action as a survey, rumor, buying guide, or product forecast that
        # happens to mention the products expected at that event.
        companion = right if left_event_campaigns else left
        if (
            "primary-claim-predicate:event-schedule-announcement"
            not in companion.separation_keys
        ):
            return True
    if (
        left_event_campaigns
        and right_event_campaigns
        and left_event_campaigns.isdisjoint(right_event_campaigns)
    ):
        return True
    left_legal_stages = {
        key for key in left.separation_keys if key.startswith("legal-stage:")
    }
    right_legal_stages = {
        key for key in right.separation_keys if key.startswith("legal-stage:")
    }
    if (
        left_legal_stages
        and right_legal_stages
        and left_legal_stages.isdisjoint(right_legal_stages)
        and not (
            left.event_keys
            & right.event_keys
            & {
                "primary-claim:apple-openai-trade-secret-case:evidence-disclosure"
            }
        )
    ):
        return True
    left_firmware = {
        key for key in left.boundary_keys if key.startswith("apple-firmware:")
    }
    right_firmware = {
        key for key in right.boundary_keys if key.startswith("apple-firmware:")
    }
    if bool(left_firmware) != bool(right_firmware):
        other = right if left_firmware else left
        other_identity = other.identity
        if other_identity is not None and "airpods" not in other_identity.title_products:
            return True
    left_release = {
        key for key in left.event_keys if key.startswith("apple-os-release-wave:")
    }
    right_release = {
        key for key in right.event_keys if key.startswith("apple-os-release-wave:")
    }
    if _profile_release_conflict(left, right):
        return True
    if left.identity is not None and right.identity is not None:
        left_form = left.identity.content_form
        right_form = right.identity.content_form
        shared_action_keys = {
            key
            for key in left.event_keys & right.event_keys
            if key.startswith(
                (
                    "apple-os-release-wave:",
                    "canonical-apple-action:",
                    "structured-assertion:",
                )
            )
        }
        if (
            (left_form == "roundup") != (right_form == "roundup")
            and not (left.exact_facets & right.exact_facets)
            and not shared_action_keys
        ):
            return True
        left_services = left.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        right_services = right.identity.title_products & FIRST_PARTY_SERVICE_PRODUCTS
        if (
            left_services
            and right_services
            and left_services.isdisjoint(right_services)
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_primary_subjects = {
        key
        for key in left.boundary_keys
        if key.startswith("primary-claim-subject:")
    }
    right_primary_subjects = {
        key
        for key in right.boundary_keys
        if key.startswith("primary-claim-subject:")
    }
    left_event_schedule = (
        "primary-claim-predicate:event-schedule-announcement"
        in left.separation_keys
    )
    right_event_schedule = (
        "primary-claim-predicate:event-schedule-announcement"
        in right.separation_keys
    )
    if left_event_schedule != right_event_schedule and not (left.event_keys & right.event_keys):
        companion = right if left_event_schedule else left
        if companion.identity is not None and companion.identity.title_products:
            return True
    if (
        left_primary_subjects
        and right_primary_subjects
        and left_primary_subjects.isdisjoint(right_primary_subjects)
        and not (left.event_keys & right.event_keys)
    ):
        return True
    left_os_features = {
        key
        for key in left.event_keys
        if key.startswith("apple-os-feature-scope:")
    }
    right_os_features = {
        key
        for key in right.event_keys
        if key.startswith("apple-os-feature-scope:")
    }
    if (
        ((left_primary_subjects and right_os_features)
         or (right_primary_subjects and left_os_features))
        and not (left.event_keys & right.event_keys)
    ):
        return True
    if left_primary_subjects != right_primary_subjects and not (left.event_keys & right.event_keys):
        categories = {
            left.category_hint or left.observed_category,
            right.category_hint or right.observed_category,
        }
        if (
            categories == {"hardware_products", "software_systems"}
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_generic_roadmap = any(
        re.fullmatch(r"structured-canonical-title:apple .+ roadmap update", key)
        for key in left.event_keys
    )
    right_generic_roadmap = any(
        re.fullmatch(r"structured-canonical-title:apple .+ roadmap update", key)
        for key in right.event_keys
    )
    if (
        left_generic_roadmap != right_generic_roadmap
        and not (left.event_keys & right.event_keys)
    ):
        concrete = right if left_generic_roadmap else left
        concrete_primary_subjects = (
            right_primary_subjects if left_generic_roadmap else left_primary_subjects
        )
        if (
            concrete_primary_subjects
            or (concrete.category_hint or concrete.observed_category)
            and (concrete.category_hint or concrete.observed_category)
            != (
                (left.category_hint or left.observed_category)
                if left_generic_roadmap
                else (right.category_hint or right.observed_category)
            )
        ):
            return True
    if left.exact_facets & right.exact_facets:
        return False
    if left.event_keys & right.event_keys:
        return False
    left_assertions = {
        key for key in left.event_keys if key.startswith("structured-assertion:")
    }
    right_assertions = {
        key for key in right.event_keys if key.startswith("structured-assertion:")
    }
    if left_assertions and right_assertions and left_assertions.isdisjoint(right_assertions):
        return True
    left_features = {
        key for key in left.event_keys if key.startswith("apple-os-feature-scope:")
    }
    right_features = {
        key for key in right.event_keys if key.startswith("apple-os-feature-scope:")
    }
    left_roundups = {
        key for key in left.event_keys if key.startswith("apple-os-feature-roundup:")
    }
    right_roundups = {
        key for key in right.event_keys if key.startswith("apple-os-feature-roundup:")
    }
    if bool(left_release) != bool(right_release):
        non_release = right if left_release else left
        if (
            non_release.identity is not None
            and non_release.identity.actions
            & {"legal", "regulation", "security", "transaction"}
            and not (left.event_keys & right.event_keys)
        ):
            return True
    if (left_release and right_features) or (right_release and left_features):
        return True
    if (
        (left_roundups and (right_release or right_features))
        or (right_roundups and (left_release or left_features))
    ):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary):
        hard_boundary = left.hard_boundary or right.hard_boundary
        if hard_boundary == "independent-third-party-action":
            return True
        if not (left.event_keys & right.event_keys):
            return True
    if left.identity is not None and right.identity is not None:
        left_identity = left.identity
        right_identity = right.identity
        shared_specific_subject = bool(
            (left_identity.named_subjects & right_identity.named_subjects)
            or (left_identity.counterparties & right_identity.counterparties)
            or (left_identity.case_topics & right_identity.case_topics)
            or (left_identity.title_products & right_identity.title_products)
        )
        if "legal" in left_identity.actions & right_identity.actions:
            left_legal_subjects = (
                left_identity.named_subjects
                | left_identity.counterparties
                | left_identity.case_topics
                | left_identity.title_products
            )
            right_legal_subjects = (
                right_identity.named_subjects
                | right_identity.counterparties
                | right_identity.case_topics
                | right_identity.title_products
            )
            if (
                left_legal_subjects
                and right_legal_subjects
                and left_legal_subjects.isdisjoint(right_legal_subjects)
            ):
                return True
        high_signal_actions = {"legal", "regulation", "security", "transaction"}
        left_actions = left_identity.actions & high_signal_actions
        right_actions = right_identity.actions & high_signal_actions
        if (
            left_actions
            and right_actions
            and left_actions.isdisjoint(right_actions)
            and not shared_specific_subject
            and not (left.event_keys & right.event_keys)
            and not (left.exact_facets & right.exact_facets)
        ):
            return True
    left_policy_boundaries = {
        key for key in left.boundary_keys if key.startswith("apple-platform-policy:")
    }
    right_policy_boundaries = {
        key for key in right.boundary_keys if key.startswith("apple-platform-policy:")
    }
    left_incident_boundaries = {
        key for key in left.boundary_keys if key.startswith("structured-subject:")
    }
    right_incident_boundaries = {
        key for key in right.boundary_keys if key.startswith("structured-subject:")
    }
    if (
        (
            left_policy_boundaries
            and right_incident_boundaries
            or right_policy_boundaries
            and left_incident_boundaries
        )
        and not (left.event_keys & right.event_keys)
        and not (left.exact_facets & right.exact_facets)
    ):
        return True
    if (
        left.hard_boundary
        and right.hard_boundary
        and left.hard_boundary != right.hard_boundary
        and not (left.event_keys & right.event_keys)
    ):
        return True
    left_os_scopes = {
        boundary
        for boundary in left.boundary_keys
        if boundary.startswith("apple-os-feature-scope:")
    }
    right_os_scopes = {
        boundary
        for boundary in right.boundary_keys
        if boundary.startswith("apple-os-feature-scope:")
    }
    if left_os_scopes and right_os_scopes and left_os_scopes.isdisjoint(right_os_scopes):
        return True
    for namespace in (
        "title-fact:",
        "product-family:",
        "product-model:",
        "legal-party:",
        "legal-stage:",
        "action:",
        "predicate:",
        "weak-topic:",
    ):
        left_values = {
            key for key in left.separation_keys if key.startswith(namespace)
        }
        right_values = {
            key for key in right.separation_keys if key.startswith(namespace)
        }
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    shared_boundaries = left.boundary_keys & right.boundary_keys
    staged_boundaries = {
        boundary
        for boundary in shared_boundaries
        if boundary.startswith(("app-store-removal:", "apple-legal-case:", "apple-legal-party:"))
    }
    return bool(
        staged_boundaries
        and left.event_keys
        and right.event_keys
        and not (left.event_keys & right.event_keys)
    )


def _stable_article_key(article: object) -> tuple[str, str, str]:
    return (
        str(getattr(article, "url", "")),
        str(getattr(article, "source", "")),
        str(getattr(article, "title", "")),
    )


def _event_key_namespace(key: str) -> str:
    for prefix in (
        "structured-first-party-subject:",
        "structured-attributed-measure:",
        "structured-component-measure:",
        "structured-component-period:",
        "structured-entity-component:",
        "structured-legal-settlement:",
        "structured-claim-status:",
        "structured-market-result:",
        "structured-subject-product:",
        "structured-subject-action:",
        "structured-component:",
        "structured-report:",
        "apple-os-release-wave:",
        "apple-os-platform-release-wave:",
        "apple-os-feature-roundup:",
        "apple-os-feature-scope:",
    ):
        if key.startswith(prefix):
            return prefix
    return key.split(":", 1)[0] + ":"


def supported_reconciliation_event_keys(
    profiles: Sequence[ReconciliationProfile],
) -> set[str]:
    """Return exact keys supported by a coherent, possibly sparse source group."""
    union = {key for profile in profiles for key in profile.event_keys}
    supported: set[str] = set()
    for key in union:
        if key.startswith(("apple-event-campaign:", "apple-event-occurrence:")):
            if all(
                any(
                    candidate.startswith(
                        ("apple-event-campaign:", "apple-event-occurrence:")
                    )
                    for candidate in profile.event_keys
                )
                for profile in profiles
            ):
                supported.add(key)
            continue
        if key.startswith("structured-canonical-title:"):
            if all(key in profile.event_keys for profile in profiles):
                supported.add(key)
            continue
        if key.startswith("apple-os-release-wave:"):
            conflicting = any(
                {
                    candidate
                    for candidate in profile.event_keys
                    if candidate.startswith("apple-os-release-wave:")
                }
                and key not in profile.event_keys
                for profile in profiles
            )
            if not conflicting:
                supported.add(key)
            continue
        if key.startswith("structured-"):
            if key.startswith(STRUCTURED_EVIDENCE_KEY_PREFIXES):
                supported.add(key)
                continue
            namespace = _event_key_namespace(key)
            if all(
                not {
                    candidate
                    for candidate in profile.event_keys
                    if _event_key_namespace(candidate) == namespace
                }
                or key in profile.event_keys
                for profile in profiles
            ):
                supported.add(key)
            continue
        if key.startswith("primary-claim:"):
            namespace = _event_key_namespace(key)
            if all(
                not {
                    candidate
                    for candidate in profile.event_keys
                    if _event_key_namespace(candidate) == namespace
                }
                or key in profile.event_keys
                for profile in profiles
            ):
                supported.add(key)
            continue
        if all(not profile.event_keys or key in profile.event_keys for profile in profiles):
            supported.add(key)
    return supported


def _reunite_exact_relation_groups(
    groups: Sequence[Sequence[ArticleT]],
    profiles: dict[int, ReconciliationProfile],
) -> list[list[ArticleT]]:
    """Reconcile exact headline relations after broad seed cleanup.

    Recall seeds can temporarily attach a precise capability report to a
    launch, price, or roundup article.  Later cleanup correctly removes those
    passengers, but the first reconciliation pass has already elapsed.  This
    final pass only rejoins clean groups whose every member carries the same
    exact subject/object/value relation and whose structured profiles do not
    conflict.
    """
    reconciled = [list(group) for group in groups if group]

    def exact_relations(group: Sequence[ArticleT]) -> set[str]:
        if not group:
            return set()
        return {
            key
            for key in supported_reconciliation_event_keys(
                [profiles[id(article)] for article in group]
            )
            if key.startswith(
                (
                    "structured-measure:",
                    "structured-component-measure:",
                    "structured-attributed-measure:",
                    "structured-market-result:",
                    "canonical-apple-action:",
                    "primary-claim:",
                )
            )
        }

    changed = True
    while changed:
        changed = False
        for left_index, right_index in combinations(range(len(reconciled)), 2):
            left_group = reconciled[left_index]
            right_group = reconciled[right_index]
            if not left_group or not right_group:
                continue
            if not (exact_relations(left_group) & exact_relations(right_group)):
                continue
            shared_relations = exact_relations(left_group) & exact_relations(right_group)
            authoritative_action_relation = any(
                key.startswith(
                    (
                        "structured-attributed-measure:",
                        "structured-market-result:",
                        "canonical-apple-action:",
                        "primary-claim:",
                    )
                )
                for key in shared_relations
            )
            if any(
                _profile_release_conflict(profiles[id(left)], profiles[id(right)])
                or _explicit_property_value_conflict(profiles[id(left)], profiles[id(right)])
                or (
                    not authoritative_action_relation
                    and (
                        _profiles_conflict(profiles[id(left)], profiles[id(right)])
                        or (
                            profiles[id(left)].identity is not None
                            and profiles[id(right)].identity is not None
                            and identity_pair_decision(
                                profiles[id(left)].identity,
                                profiles[id(right)].identity,
                            )
                            == "conflict"
                        )
                    )
                )
                for left in left_group
                for right in right_group
            ):
                continue
            reconciled[left_index] = sorted(
                [*left_group, *right_group],
                key=_stable_article_key,
            )
            reconciled[right_index] = []
            changed = True
            break
        if changed:
            continue
    return [group for group in reconciled if group]


def resolve_reconciliation_outcome(
    profile: ReconciliationProfile,
    *,
    observed_tier: str,
    observed_reason: str,
    observed_category: str,
) -> tuple[str, str, str]:
    """Resolve relevance and category once from the structured profile."""
    category = profile.category_hint or observed_category
    if profile.defer_reason and observed_tier not in {"weak", "ecosystem"}:
        return "weak", profile.defer_reason, category
    if (
        observed_tier == "weak"
        and profile.trusted_direct_action
        and not profile.hard_boundary
    ):
        return (
            "strong",
            profile.promotion_reason
            or "title-led direct Apple action confirmed by structured identity",
            category,
        )
    structured_first_party_override = any(
        key.startswith(
            (
                "structured-assertion:app-store:",
                "structured-assertion:apple-tv:",
                "structured-assertion:iphone-camera:reference-image-",
            )
        )
        for key in profile.event_keys
    )
    if (
        observed_tier == "weak"
        and not profile.hard_boundary
        and structured_first_party_override
    ):
        return (
            "strong",
            "structured first-party Apple action confirmed by article evidence",
            category,
        )
    if profile.defer_reason and observed_tier == "weak":
        return "weak", profile.defer_reason, category
    return observed_tier, observed_reason, category


def reconcile_articles(
    articles: Sequence[ArticleT],
    *,
    profile_for: Callable[[ArticleT], ReconciliationProfile],
    initial_groups: Sequence[Sequence[ArticleT]],
) -> tuple[tuple[ArticleT, ...], ...]:
    """Split recall-oriented seeds, then reunite exact event identities."""
    ordered = sorted(articles, key=_stable_article_key)
    profiles = {id(article): profile_for(article) for article in ordered}

    def explicit_identity_conflict(
        left_profile: ReconciliationProfile,
        right_profile: ReconciliationProfile,
    ) -> bool:
        left = left_profile.identity
        right = right_profile.identity
        if left is None or right is None:
            return False
        shared_event_keys = left_profile.event_keys & right_profile.event_keys
        if any(
            key.startswith("primary-claim:apple-")
            and key.endswith(":schedule-forecast")
            for key in shared_event_keys
        ):
            # Product lineups are supporting facts in event-date coverage. Two
            # reports may name different subsets of the same launch slate while
            # asserting the same event schedule.
            return False
        left_generations = {
            component
            for component in left.title_components
            if component.startswith("product-generation:")
        }
        right_generations = {
            component
            for component in right.title_components
            if component.startswith("product-generation:")
        }
        if (
            left_generations
            and right_generations
            and left_generations.isdisjoint(right_generations)
        ):
            return True
        left_foldable = "foldable-iphone" in left.title_products
        right_foldable = "foldable-iphone" in right.title_products
        if left_foldable != right_foldable and (
            left_generations or right_generations
        ):
            return True
        left_is_analyst_action = "analyst-target-action" in left.title_components
        right_is_analyst_action = "analyst-target-action" in right.title_components
        if left_is_analyst_action != right_is_analyst_action:
            return True
        def predicate_classes(identity: EventIdentity) -> set[str]:
            title_components = identity.title_components
            if "component-cost-analysis" in title_components:
                return {"component-cost-analysis"}
            if "immersive-live-video" in identity.components:
                return {"immersive-live-content"}
            if "apple-tv-sports-schedule" in (
                left_profile.exact_facets if identity is left else right_profile.exact_facets
            ):
                return {"content-schedule"}
            if title_components & {"display-panel", "oled-display"}:
                return {"component-development"}
            if title_components & {"hardware-market-performance", "memory-supply"}:
                return {"supply-or-shipment-outlook"}
            product_specific = any(
                component.startswith(
                    (
                        "apple-silicon-generation:",
                        "iphone-family:",
                        "iphone-model:",
                        "macbook-model:",
                        "product-generation:",
                    )
                )
                for component in title_components
            )
            if (
                product_specific
                and identity.title_actions & {"delay-roadmap", "feature-change", "pilot-testing"}
            ):
                return {"product-roadmap"}
            return set()

        left_components = predicate_classes(left)
        right_components = predicate_classes(right)
        predicate_conflict = bool(
            left_components
            and right_components
            and left_components.isdisjoint(right_components)
        )
        if predicate_conflict:
            authoritative_shared_keys = {
                key
                for key in shared_event_keys
                if not (
                    ":multi-" in key
                    or ":product-segment:" in key
                    or key.endswith(":market-summary")
                )
            }
            return not authoritative_shared_keys
        if shared_event_keys:
            return False
        if left_profile.exact_facets & right_profile.exact_facets:
            return False
        return False

    def split_seed_group(seed: Sequence[ArticleT]) -> list[list[ArticleT]]:
        def seed_conflicts(left: ArticleT, right: ArticleT) -> bool:
            left_profile = profiles[id(left)]
            right_profile = profiles[id(right)]
            if (
                getattr(left, "source", "")
                and getattr(left, "source", "") == getattr(right, "source", "")
                and getattr(left, "url", "") != getattr(right, "url", "")
            ):
                shared_keys = supported_reconciliation_event_keys(
                    [left_profile, right_profile]
                )
                shared_action_keys = {
                    key
                    for key in shared_keys
                    if not key.startswith("structured-canonical-title:")
                }
                pair_identity_match = bool(
                    left_profile.identity is not None
                    and right_profile.identity is not None
                    and identity_pair_decision(
                        left_profile.identity,
                        right_profile.identity,
                    )
                    == "match"
                )
                exact_relation = bool(
                    left_profile.exact_facets & right_profile.exact_facets
                )
                shared_changed_object = {
                    key
                    for key in left_profile.separation_keys
                    & right_profile.separation_keys
                    if key.startswith("changed-object:")
                }
                shared_product_boundary = {
                    key
                    for key in left_profile.separation_keys
                    & right_profile.separation_keys
                    if key.startswith(("product-family:", "product-model:"))
                }
                same_product_change = bool(
                    shared_changed_object and shared_product_boundary
                )
                if (
                    not shared_action_keys
                    and not pair_identity_match
                    and not exact_relation
                    and not same_product_change
                ):
                    # Separate stories from one publisher need positive event
                    # evidence. Generic product or generation components are
                    # not sufficient to make two URLs the same event.
                    return True
            return _seed_profiles_conflict(
                left_profile,
                right_profile,
            ) or explicit_identity_conflict(left_profile, right_profile)

        split_groups: list[list[ArticleT]] = []
        for article in sorted(seed, key=_stable_article_key):
            candidates = [
                group
                for group in split_groups
                if all(not seed_conflicts(article, existing) for existing in group)
            ]
            if not candidates:
                split_groups.append([article])
                continue
            matched = max(
                candidates,
                key=lambda group: (
                    sum(
                        len(
                            profiles[id(article)].event_keys
                            & profiles[id(existing)].event_keys
                        )
                        for existing in group
                    ),
                    -len(group),
                    tuple(_stable_article_key(existing) for existing in group),
                ),
            )
            matched.append(article)
        return split_groups

    groups: list[list[ArticleT]] = []
    seen: set[int] = set()
    for seed in sorted(
        initial_groups,
        key=lambda group: tuple(
            _stable_article_key(article)
            for article in sorted(group, key=_stable_article_key)
        ),
    ):
        unique_seed = [article for article in seed if id(article) not in seen]
        seen.update(id(article) for article in unique_seed)
        split_seed = split_seed_group(unique_seed)
        groups.extend(split_seed)
    groups.extend([[article] for article in ordered if id(article) not in seen])
    def supported_event_keys(group: Sequence[ArticleT]) -> set[str]:
        return supported_reconciliation_event_keys(
            [profiles[id(article)] for article in group]
        )

    known_report_entities = {
        component.removeprefix("report-attribution:")
        for profile in profiles.values()
        if profile.identity is not None
        for component in profile.identity.components
        if component.startswith("report-attribution:")
    }
    parent = list(range(len(groups)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def merge_roots(left_index: int, right_index: int) -> bool:
        left_root = root(left_index)
        right_root = root(right_index)
        if left_root == right_root:
            return False
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        groups[left_root] = sorted(
            [*groups[left_root], *groups[right_root]],
            key=_stable_article_key,
        )
        groups[right_root] = []
        parent[right_root] = left_root
        return True

    def union(left_index: int, right_index: int) -> bool:
        left_root = root(left_index)
        right_root = root(right_index)
        if left_root == right_root:
            return False
        left_group = groups[left_root]
        right_group = groups[right_root]
        join_keys = supported_event_keys(left_group) & supported_event_keys(right_group)
        if not join_keys:
            return False
        join_namespaces = {_event_key_namespace(key) for key in join_keys}
        cross_product_release_join = any(
            key.startswith(("apple-os-release-wave:", "apple-os-platform-release-wave:"))
            for key in join_keys
        )
        assertion_join = any(
            key.startswith("structured-assertion:") for key in join_keys
        )
        event_campaign_join = any(
            key.startswith(("apple-event-campaign:", "apple-event-occurrence:"))
            for key in join_keys
        )
        canonical_action_join = any(
            key.startswith(
                (
                    "apple-event-campaign:",
                    "apple-event-occurrence:",
                    "canonical-apple-action:",
                    "primary-claim:",
                )
            )
            for key in join_keys
        )
        structured_product_update_join = any(
            key.startswith(
                (
                    "structured-title-product-update:",
                    "structured-title-product-release:",
                )
            )
            for key in join_keys
        )
        evidence_join = any(
            key.startswith(STRUCTURED_EVIDENCE_KEY_PREFIXES)
            for key in join_keys
        )
        for left in left_group:
            for right in right_group:
                left_profile = profiles[id(left)]
                right_profile = profiles[id(right)]
                # Generic evidence keys (for example the same component and
                # year) are corroboration, not ownership. Only a matching
                # canonical action or concrete assertion may override legacy
                # topic/relevance noise; otherwise unrelated products can be
                # bridged by shared supply-chain background.
                release_action_join = bool(
                    cross_product_release_join
                    and "predicate:os-release-announcement"
                    in left_profile.separation_keys
                    and "predicate:os-release-announcement"
                    in right_profile.separation_keys
                )
                authoritative_claim_join = bool(
                    canonical_action_join
                    or assertion_join
                    or structured_product_update_join
                    or release_action_join
                )
                if _profile_release_conflict(left_profile, right_profile):
                    return False
                if (
                    _profiles_conflict(left_profile, right_profile)
                    or _explicit_separation_conflict(left_profile, right_profile)
                ) and not authoritative_claim_join:
                    return False
                pair_identity_conflict = (
                    left_profile.identity is not None
                    and right_profile.identity is not None
                    and identity_pair_decision(
                        left_profile.identity,
                        right_profile.identity,
                    )
                    == "conflict"
                )
                if (
                    pair_identity_conflict
                    and not cross_product_release_join
                    and not evidence_join
                    and not assertion_join
                    and not canonical_action_join
                    and not structured_product_update_join
                    and len(join_namespaces) < 2
                ):
                    return False
                explicit_conflict = explicit_identity_conflict(
                    left_profile,
                    right_profile,
                )
                if not explicit_conflict:
                    continue
                if event_campaign_join:
                    continue
                left_identity = left_profile.identity
                right_identity = right_profile.identity
                analyst_action_conflict = bool(
                    left_identity
                    and right_identity
                    and (
                        "analyst-target-action" in left_identity.title_components
                    )
                    != (
                        "analyst-target-action" in right_identity.title_components
                    )
                )
                if evidence_join and not analyst_action_conflict:
                    continue
                if assertion_join:
                    continue
                if cross_product_release_join:
                    continue
                left_namespaces = {
                    _event_key_namespace(key) for key in left_profile.event_keys
                }
                right_namespaces = {
                    _event_key_namespace(key) for key in right_profile.event_keys
                }
                # Exact reconciliation keys join coherent groups through their
                # matching identity projection. A sparse source that describes
                # the same event through another projection must not veto that
                # join; competing identities in the joining namespace still do.
                if (
                    left_namespaces & join_namespaces
                    and right_namespaces & join_namespaces
                ):
                    exact_pair_action_join = any(
                        key in left_profile.event_keys
                        and key in right_profile.event_keys
                        and key.startswith(
                            (
                                "canonical-apple-action:",
                                "primary-claim:",
                                "structured-assertion:",
                            )
                        )
                        for key in join_keys
                    )
                    if exact_pair_action_join:
                        continue
                    return False
        return merge_roots(left_root, right_root)

    # Exact identities can become newly supported after two sparse source
    # groups merge. Rebuild the key graph until no root changes so a campaign
    # name, a localized date, or another exact alias can bridge transitively
    # without depending on source order. Each successful pass reduces the root
    # count, which bounds the loop and keeps this post-fetch work small.
    exact_groups_changed = True
    while exact_groups_changed:
        exact_groups_changed = False
        key_buckets: dict[str, list[int]] = {}
        for index, group in enumerate(groups):
            if not group or root(index) != index:
                continue
            for key in supported_event_keys(group):
                if key.startswith("structured-entity-component:"):
                    entity = key.split(":", 2)[1]
                    if entity not in known_report_entities:
                        continue
                key_buckets.setdefault(key, []).append(index)
        for key in sorted(key_buckets):
            members = key_buckets[key]
            if not members:
                continue
            # A conflicting first member must not block two later compatible
            # members from reconciling. Treat each exact key bucket as a graph
            # and let the existing conflict gates decide every possible edge.
            for left_index, right_index in combinations(members, 2):
                exact_groups_changed = union(left_index, right_index) or exact_groups_changed

    # Localized work names occasionally differ by one transcription character.
    # Reconcile those only when every member still names the same Apple TV work
    # and the action remains the initial project/premiere announcement. Later
    # trailers, renewals, casting, and production updates keep hard boundaries.
    for left_index, right_index in combinations(range(len(groups)), 2):
        left_root = root(left_index)
        right_root = root(right_index)
        if left_root == right_root or not groups[left_root] or not groups[right_root]:
            continue
        left_profiles = [profiles[id(article)] for article in groups[left_root]]
        right_profiles = [profiles[id(article)] for article in groups[right_root]]
        if not all(_content_work_profile(profile)[0] for profile in [*left_profiles, *right_profiles]):
            continue
        if not all(
            any(_compatible_content_work_profiles(left, right) for right in right_profiles)
            for left in left_profiles
        ):
            continue
        if not all(
            any(_compatible_content_work_profiles(left, right) for left in left_profiles)
            for right in right_profiles
        ):
            continue
        merge_roots(left_root, right_root)

    def group_release_stages(group: Sequence[ArticleT]) -> set[str]:
        return {
            component.rsplit(":", 1)[-1]
            for article in group
            for component in (profiles[id(article)].identity.components if profiles[id(article)].identity else ())
            if component.startswith("os-wave-platform:")
        }

    def article_platform_release_stages(article: ArticleT) -> set[tuple[str, str]]:
        identity = profiles[id(article)].identity
        if identity is None:
            return set()
        signatures: set[tuple[str, str]] = set()
        for component in identity.components:
            match = re.fullmatch(r"os-wave-platform:([^:]+):(.+)", component)
            if match:
                signatures.add((match.group(1), match.group(2)))
        return signatures

    def group_release_waves(group: Sequence[ArticleT]) -> set[tuple[str, str]]:
        waves: set[tuple[str, str]] = set()
        for article in group:
            for key in profiles[id(article)].event_keys:
                match = re.fullmatch(r"apple-os-release-wave:([^:]+):([^:]+)", key)
                if match:
                    waves.add((match.group(1), match.group(2)))
        return waves

    # A release headline can identify an OS by codename while omitting the
    # numeric generation. Attach it to a numbered release train only when the
    # current candidate set has exactly one compatible version for that beta
    # stage. Ambiguous simultaneous legacy/current trains remain separate.
    active_roots = [index for index, group in enumerate(groups) if group and root(index) == index]
    for unknown_index in active_roots:
        unknown_root = root(unknown_index)
        unknown_group = groups[unknown_root]
        if not unknown_group or group_release_waves(unknown_group):
            continue
        stages = group_release_stages(unknown_group)
        if len(stages) != 1:
            continue
        stage = next(iter(stages))
        unknown_signatures = set().union(
            *(article_platform_release_stages(article) for article in unknown_group)
        )
        if not unknown_signatures:
            continue
        candidates: list[tuple[int, str]] = []
        for candidate_index in active_roots:
            candidate_root = root(candidate_index)
            if candidate_root == unknown_root or not groups[candidate_root]:
                continue
            if not any(
                article_platform_release_stages(article) & unknown_signatures
                for article in groups[candidate_root]
            ):
                continue
            matching_versions = {
                version
                for version, candidate_stage in group_release_waves(groups[candidate_root])
                if candidate_stage == stage
            }
            candidates.extend((candidate_root, version) for version in matching_versions)
        versions = {version for _, version in candidates}
        candidate_roots = {candidate for candidate, _ in candidates}
        if len(versions) != 1 or not candidate_roots:
            continue
        largest_size = max(len(groups[candidate]) for candidate in candidate_roots)
        largest_candidates = {
            candidate
            for candidate in candidate_roots
            if len(groups[candidate]) == largest_size
        }
        if len(largest_candidates) != 1:
            continue
        candidate_root = next(iter(largest_candidates))
        candidate_anchors = [
            article
            for article in groups[candidate_root]
            if article_platform_release_stages(article) & unknown_signatures
        ]
        if not candidate_anchors:
            continue
        if any(
            _profile_release_conflict(profiles[id(left)], profiles[id(right)])
            or (
                "predicate:os-release-announcement"
                not in profiles[id(left)].separation_keys
            )
            or (
                "predicate:os-release-announcement"
                not in profiles[id(right)].separation_keys
            )
            for left in unknown_group
            for right in candidate_anchors
        ):
            continue
        # The candidate was selected by a unique version/stage and a matching
        # platform anchor above. Merge the roots directly so unrelated product
        # identities elsewhere in the already-built cross-platform wave cannot
        # veto this validated sparse attachment.
        merge_roots(unknown_root, candidate_root)
    groups = [group for index, group in enumerate(groups) if group and root(index) == index]
    release_checked_groups: list[list[ArticleT]] = []
    release_input_groups: list[list[ArticleT]] = []
    for group in groups:
        campaign_articles = [
            article
            for article in group
            if any(
                key.startswith(("apple-event-campaign:", "apple-event-occurrence:"))
                or key == "primary-claim:apple-iphone-fall-event:schedule-forecast"
                for key in profiles[id(article)].event_keys
            )
        ]
        campaign_keys = supported_event_keys(campaign_articles)
        coherent_campaign_subset = bool(
            len(campaign_articles) >= 2
            and any(
                key.startswith(("apple-event-campaign:", "apple-event-occurrence:"))
                or key == "primary-claim:apple-iphone-fall-event:schedule-forecast"
                for key in campaign_keys
            )
        )
        if coherent_campaign_subset:
            release_checked_groups.append(
                sorted(campaign_articles, key=_stable_article_key)
            )
            campaign_ids = {id(article) for article in campaign_articles}
            remaining = [article for article in group if id(article) not in campaign_ids]
            if remaining:
                release_input_groups.append(remaining)
            continue
        release_input_groups.append(group)

    for group in release_input_groups:
        supported_group_keys = supported_event_keys(group)
        coherent_os_release_wave = bool(
            any(
                key.startswith("apple-os-release-wave:")
                for key in supported_group_keys
            )
            and all(
                "predicate:os-release-announcement"
                in profiles[id(article)].separation_keys
                for article in group
            )
        )
        if coherent_os_release_wave:
            # A cross-platform OS release train is already a concrete event.
            # Hardware release cleanup must not reinterpret a Vision Pro token
            # as a product launch and peel codename-only OS reports back out.
            release_checked_groups.append(group)
            continue
        coherent_event_campaign = any(
            key.startswith(("apple-event-campaign:", "apple-event-occurrence:"))
            for key in supported_group_keys
        )
        if coherent_event_campaign:
            # A localized date, an announced campaign name, and its official
            # social assets are alternate projections of one Apple event. The
            # generic product-release hitchhiker pass must not split that
            # already-reconciled campaign back into product-specific fragments.
            release_checked_groups.append(group)
            continue
        common_primary_claims = {
            key
            for key in profiles[id(group[0])].event_keys
            if key.startswith("primary-claim:")
            and all(key in profiles[id(article)].event_keys for article in group[1:])
        }
        if common_primary_claims:
            release_checked_groups.append(group)
            continue
        release_keys = {
            key
            for article in group
            for key in profiles[id(article)].event_keys
            if key.startswith("structured-title-product-release:")
        }
        if len(release_keys) != 1:
            release_checked_groups.append(group)
            continue
        release_key = next(iter(release_keys))
        anchors = [
            article
            for article in group
            if release_key in profiles[id(article)].event_keys
            and not any(
                key.startswith("primary-claim:")
                and not any(
                    marker in key
                    for marker in (
                        ":generation-product-refresh:",
                        ":reported-launch-window",
                    )
                )
                for key in profiles[id(article)].event_keys
            )
        ]
        if not anchors:
            anchors = [
                article
                for article in group
                if release_key in profiles[id(article)].event_keys
            ]
        anchor_event_keys = {
            key
            for article in anchors
            for key in profiles[id(article)].event_keys
        }
        anchor_exact_facets = {
            facet
            for article in anchors
            for facet in profiles[id(article)].exact_facets
        }
        anchor_separation_keys = {
            key
            for article in anchors
            for key in profiles[id(article)].separation_keys
        }
        anchor_action_classes = {
            action
            for article in anchors
            for action in (
                _structured_title_action_classes(profiles[id(article)].identity)
                if profiles[id(article)].identity is not None
                else set()
            )
        }
        anchor_products = {
            product
            for article in anchors
            for product in (
                profiles[id(article)].identity.products
                if profiles[id(article)].identity is not None
                else set()
            )
        }
        anchor_changed_objects = {
            key
            for article in anchors
            for key in profiles[id(article)].separation_keys
            if key.startswith("changed-object:")
        }
        hitchhikers: list[ArticleT] = []
        compatible_sparse: list[ArticleT] = []
        for article in group:
            if article in anchors:
                continue
            profile = profiles[id(article)]
            identity = profile.identity
            shared_event_keys = profile.event_keys & anchor_event_keys
            changed_objects = {
                key
                for key in profile.separation_keys
                if key.startswith("changed-object:")
            }
            title_actions = identity.title_actions if identity is not None else set()
            independent_title_action = bool(
                title_actions
                & {
                    "delay-roadmap",
                    "feature-change",
                    "platform-integration",
                    "price-change",
                    "supply-production",
                }
            )
            independent_structured_action = bool(
                identity
                and "product-change" in _structured_title_action_classes(identity)
            )
            explicit_sub_event = bool(
                any(
                    key.startswith(
                        (
                            "changed-object:",
                            "primary-claim-predicate:",
                            "predicate:hardware-product-roadmap",
                        )
                    )
                    for key in profile.separation_keys
                )
                or independent_title_action
                or independent_structured_action
                or any(
                    key.startswith("structured-assertion:")
                    for key in profile.event_keys
                )
            )
            refresh_detail_objects = {
                "changed-object:finish-color",
                "changed-object:processor",
                "changed-object:thermal-design",
            }
            generation_refresh_match = bool(
                any(
                    key.startswith("primary-claim:")
                    and ":generation-product-refresh:" in key
                    for key in shared_event_keys
                )
                and changed_objects <= refresh_detail_objects
                and "predicate:hardware-product-roadmap" not in profile.separation_keys
                and not title_actions
                & {"platform-integration", "price-change", "supply-production"}
            )
            reported_launch_match = bool(
                any(
                    key.startswith("primary-claim:")
                    and ":reported-launch-window" in key
                    for key in shared_event_keys
                )
                and changed_objects
                and changed_objects & anchor_changed_objects
            )
            product_period_match = bool(
                any(
                    key.startswith("product-period:")
                    for key in profile.separation_keys & anchor_separation_keys
                )
                and changed_objects <= refresh_detail_objects
                and not title_actions
                & {"platform-integration", "price-change", "supply-production"}
            )
            corroborated_product_update = any(
                key.startswith(
                    (
                        "apple-os-platform-release-wave:",
                        "apple-os-release-wave:",
                        "canonical-apple-action:",
                        "structured-assertion:",
                        "structured-component:",
                        "title-fact:",
                        "structured-title-product-update:",
                    )
                )
                for key in shared_event_keys
            ) or bool(
                profile.exact_facets & anchor_exact_facets
            ) or any(
                key.startswith("title-fact:")
                for key in profile.separation_keys & anchor_separation_keys
            ) or generation_refresh_match or reported_launch_match or product_period_match or bool(
                not explicit_sub_event
                and any(key.startswith("primary-claim:") for key in shared_event_keys)
            ) or bool(
                identity
                and "supply-production" in anchor_action_classes
                and "supply-production" in _structured_title_action_classes(identity)
                and identity.products & anchor_products & _PRECISE_HARDWARE_PRODUCT_LINES
            )
            if corroborated_product_update:
                compatible_sparse.append(article)
                continue
            if explicit_sub_event:
                hitchhikers.append(article)
            else:
                compatible_sparse.append(article)
        release_checked_groups.append(
            sorted([*anchors, *compatible_sparse], key=_stable_article_key)
        )
        if hitchhikers:
            hitchhiker_buckets: dict[str, list[ArticleT]] = {}
            for article in hitchhikers:
                profile = profiles[id(article)]
                identity = profile.identity
                title_actions = identity.title_actions if identity is not None else set()
                changed_objects = sorted(
                    key
                    for key in profile.separation_keys
                    if key.startswith("changed-object:")
                )
                if (
                    "predicate:hardware-product-roadmap" in profile.separation_keys
                    or "delay-roadmap" in title_actions
                ):
                    bucket = "roadmap"
                elif "price-change" in title_actions:
                    bucket = "price"
                elif "supply-production" in title_actions:
                    bucket = "supply"
                elif "platform-integration" in title_actions:
                    bucket = "platform"
                elif changed_objects:
                    # A source may mention secondary component differences in
                    # its body.  Release-hitchhiker splitting must follow the
                    # headline's primary changed object so those details do not
                    # split otherwise identical cross-language capability
                    # reports into separate events.
                    primary_changed_object = _primary_title_changed_object(
                        getattr(article, "title", "")
                    )
                    bucket = "change:" + (
                        primary_changed_object
                        or ",".join(changed_objects)
                    )
                elif identity is not None and "product-change" in _structured_title_action_classes(identity):
                    bucket = "product-change"
                else:
                    bucket = "other"
                hitchhiker_buckets.setdefault(bucket, []).append(article)
            for bucket in sorted(hitchhiker_buckets):
                release_checked_groups.extend(
                    split_seed_group(hitchhiker_buckets[bucket])
                )
    groups = _reunite_exact_relation_groups(
        [group for group in release_checked_groups if group],
        profiles,
    )

    groups.sort(key=lambda group: tuple(_stable_article_key(article) for article in group))
    return tuple(tuple(group) for group in groups)
