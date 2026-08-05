"""Deterministic article-level event reconciliation.

The crawler retains its mature source-specific matcher as a seed generator.
This module adds only explicit action boundaries and exact-key reconciliation,
so generic similarity cannot reopen an accepted group or create A-B-C bridges.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Callable, Iterable, Sequence, TypeVar

from .event_identity import EventIdentity


ArticleT = TypeVar("ArticleT")


@dataclass(frozen=True)
class ReconciliationProfile:
    event_keys: frozenset[str]
    boundary_keys: frozenset[str]
    defer_reason: str = ""
    category_hint: str = ""
    hard_boundary: str = ""


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


def _contains(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


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
    if not (
        _contains(text, "app store", "应用商店", "apple", "苹果")
        and _contains(text, "remov", "pull", "yank", "delist", "下架")
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
    }
    object_match = re.search(
        r"(?:remove(?:s|d)?|pull(?:s|ed)?|yank(?:s|ed)?)\s+"
        r"([a-z][a-z0-9.+-]{2,30})\s+(?:from|off)\b",
        title,
    )
    if object_match and object_match.group(1) not in ignored:
        return {object_match.group(1)}
    candidates = [
        token
        for token in re.findall(r"(?<![a-z0-9])([a-z][a-z0-9.+-]{2,30})(?![a-z0-9])", title)
        if token not in ignored
    ]
    if candidates:
        return {candidates[0]}
    subjects = _subject_tokens(title, identity)
    return {subject for subject in subjects if subject not in ignored}


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
    if _contains(
        text,
        "dismissed",
        "narrowed",
        "stricken",
        "court ruled",
        "judge ruled",
        "法官驳回",
        "法院裁定",
        "缩小诉讼",
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
    return ""


def _legal_action_stage(title: str, lead: str) -> str:
    return _legal_action_stage_text(title) or _legal_action_stage_text(lead)


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


def _unsupported_third_party_reason(
    text: str,
    identity: EventIdentity,
    exact_facets: frozenset[str],
    relevance_tier: str,
    trusted_direct_action: bool,
) -> str:
    if relevance_tier == "ecosystem" or trusted_direct_action:
        return ""
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
    if content_form in {"buying_advice", "deal", "podcast", "poll", "roundup", "tutorial"}:
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
    if re.match(
        r"^(?!apple\b|iphone\b|ipad\b|ios\b|mac(?:book|os)?\b|苹果).{2,55}'s\s+"
        r"(?:latest\s+)?(?:ios|ipados|macos|watchos|carplay|iphone|ipad|mac)\s+"
        r"(?:app\s+)?(?:update|release|version|feature)\b",
        text,
    ):
        return "independent-third-party-platform-update"
    if defer_reason.startswith((
        "editorial ",
        "competitor benchmark",
        "third-party accessory",
        "unsupported third-party",
        "third-party CarPlay",
        "opinion or commentary",
        "competitor experience",
    )):
        return "independent-third-party-action"
    return ""


def build_reconciliation_profile(
    *,
    title: str,
    lead: str,
    identity: EventIdentity,
    exact_facets: Iterable[str],
    regions: Iterable[str],
    relevance_tier: str = "strong",
    trusted_direct_action: bool = False,
) -> ReconciliationProfile:
    title_text = _normalized(title)
    text = f"{title_text}. {_normalized(lead)[:900]}"
    exact = frozenset(exact_facets)
    # Facets remain inputs to the existing domain matcher.  They are not
    # automatically cross-event keys: even a precise facet can describe more
    # than one action in a busy news cycle.
    event_keys: set[str] = set()
    boundary_keys: set[str] = set()
    category_hint = ""
    content_form = _reconciliation_content_form(title_text, identity)

    removal_stage = _app_store_removal_stage(text)
    if removal_stage:
        removal_subjects = _app_store_subjects(title_text, identity) or {"unknown-app"}
        event_keys = {
            f"app-store-removal:{subject}:{removal_stage}"
            for subject in removal_subjects
        }
        boundary_keys = {
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

    if _bug_bounty_submission_limit(text):
        event_keys.add("apple-security:bug-bounty-submission-limit")
        boundary_keys.add("apple-security:bug-bounty-submission-limit")

    if _webkit_proxy_leak(text):
        event_keys.add("apple-security:webkit-proxy-leak")
        boundary_keys.add("apple-security:webkit-proxy-leak")

    if _event_staff_support(text):
        event_keys = {"apple-event:staff-support-lottery"}
        boundary_keys = {"apple-event:staff-support-lottery"}
    if _event_preparation(text):
        event_keys.add("apple-event:september-preparation")
        boundary_keys.add("apple-event:september-preparation")

    if "airpods" in text and _contains(text, "firmware", "固件") and _contains(
        text,
        "beta",
        "testing",
        "developer",
        "测试版",
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
        if anniversary_display:
            event_keys.add("iphone-display-rumor:anniversary-size-change")

    legal_case = _legal_case_key(identity)
    legal_stage = _legal_action_stage(title_text, text[len(title_text) :])
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
        legal_parties = sorted(identity.counterparties - {"secrets", "lawsuit"})
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

    if content_form == "event_preview":
        # Background facts in an editorial preview must not impersonate the
        # concrete actions they recap.
        event_keys.clear()
        boundary_keys.clear()

    defer_reason = _unsupported_third_party_reason(
        text,
        identity,
        exact,
        relevance_tier,
        trusted_direct_action,
    )
    hard_boundary = _hard_third_party_boundary(text, defer_reason)
    return ReconciliationProfile(
        event_keys=frozenset(event_keys),
        boundary_keys=frozenset(boundary_keys),
        defer_reason=defer_reason,
        category_hint=category_hint,
        hard_boundary=hard_boundary,
    )


def _profiles_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    shared_boundaries = left.boundary_keys & right.boundary_keys
    if shared_boundaries and left.event_keys and right.event_keys and not (left.event_keys & right.event_keys):
        return True
    if bool(left.hard_boundary) != bool(right.hard_boundary) and not (left.event_keys & right.event_keys):
        return True
    return False


def _seed_profiles_conflict(left: ReconciliationProfile, right: ReconciliationProfile) -> bool:
    """Return only conflicts strong enough to split an accepted seed event."""
    if bool(left.hard_boundary) != bool(right.hard_boundary) and not (left.event_keys & right.event_keys):
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


def reconcile_articles(
    articles: Sequence[ArticleT],
    *,
    profile_for: Callable[[ArticleT], ReconciliationProfile],
    initial_groups: Sequence[Sequence[ArticleT]],
) -> tuple[tuple[ArticleT, ...], ...]:
    """Reconcile accepted seed groups without reopening broad clustering."""
    ordered = sorted(articles, key=_stable_article_key)
    profiles = {id(article): profile_for(article) for article in ordered}

    def split_seed_group(seed: Sequence[ArticleT]) -> list[list[ArticleT]]:
        # The seed groups have already passed the crawler's mature domain
        # rules.  Reconciliation may split them only on a new, explicit
        # boundary (for example an initial removal versus a later allegation,
        # or a third-party app update attached to an Apple platform feature).
        # Treating every lower-level identity disagreement as a split here
        # regresses intentional release-wave and cross-platform grouping.
        def seed_conflicts(left: ArticleT, right: ArticleT) -> bool:
            return _seed_profiles_conflict(profiles[id(left)], profiles[id(right)])

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

    def common_event_keys(group: Sequence[ArticleT]) -> set[str]:
        keyed = [set(profiles[id(article)].event_keys) for article in group]
        if not keyed or any(not keys for keys in keyed):
            return set()
        return set.intersection(*keyed)

    # Cross-event reconciliation is intentionally key-indexed.  Scanning every
    # event pair after each merge is cubic and invites similarity bridges; only
    # an exact action key may override a seed split.
    key_buckets: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        for key in common_event_keys(group):
            key_buckets.setdefault(key, []).append(index)
    parent = list(range(len(groups)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = root(left_index)
        right_root = root(right_index)
        if left_root == right_root:
            return
        left_group = groups[left_root]
        right_group = groups[right_root]
        if any(
            _profiles_conflict(profiles[id(left)], profiles[id(right)])
            for left in left_group
            for right in right_group
        ):
            return
        if right_root < left_root:
            left_root, right_root = right_root, left_root
            left_group, right_group = right_group, left_group
        groups[left_root] = sorted([*left_group, *right_group], key=_stable_article_key)
        groups[right_root] = []
        parent[right_root] = left_root

    for key in sorted(key_buckets):
        members = key_buckets[key]
        if not members:
            continue
        anchor = members[0]
        for member in members[1:]:
            union(anchor, member)
            anchor = root(anchor)
    groups = [group for index, group in enumerate(groups) if group and root(index) == index]

    groups.sort(key=lambda group: tuple(_stable_article_key(article) for article in group))
    return tuple(tuple(group) for group in groups)
