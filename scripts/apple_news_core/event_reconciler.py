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

from .event_identity import EventIdentity, LEAD_IDENTITY_COMPONENTS, PRODUCT_PATTERNS


ArticleT = TypeVar("ArticleT")


@dataclass(frozen=True)
class ReconciliationProfile:
    event_keys: frozenset[str]
    boundary_keys: frozenset[str]
    separation_keys: frozenset[str] = frozenset()
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


def _versioned_os_feature_report(text: str, identity: EventIdentity) -> bool:
    title = text.split(". ", 1)[0]
    title_os = identity.title_products & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    return bool(
        len(title_os) == 1
        and identity.scope == "apple-direct"
        and (
            "feature-change" in identity.title_actions
            or _contains(title, "feature", "features", "功能", "变化", "更新")
        )
        and re.search(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+)?\b", title)
    )


def _versioned_os_feature_scope(text: str, identity: EventIdentity) -> str:
    if not _versioned_os_feature_report(text, identity):
        return ""
    title = text.split(". ", 1)[0]
    os_family = sorted(
        identity.title_products & {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    )[0]
    components = sorted(
        component
        for component in identity.title_components
        if component.startswith("os-component:")
    )
    if not components:
        component_patterns = (
            ("messages", ("messages", "信息 app", "信息应用")),
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
    title_subject_products = sorted(
        identity.title_products
        - {"ios", "ipados", "macos", "watchos", "tvos", "visionos", "iphone", "ipad", "mac"}
    )
    if len(title_subject_products) == 1:
        subject = f"product:{title_subject_products[0]}"
    elif len(components) == 1:
        subject = f"component:{components[0]}"
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
    if defer_reason.startswith("broad component supply"):
        return "broad-component-supply-outlook"
    if defer_reason.startswith("supplier market story"):
        return "independent-supplier-market-story"
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
) -> ReconciliationProfile:
    title_text = _normalized(title)
    text = f"{title_text}. {_normalized(lead)[:900]}"
    exact = frozenset(exact_facets)
    # Facets remain inputs to the existing domain matcher.  They are not
    # automatically cross-event keys: even a precise facet can describe more
    # than one action in a busy news cycle.
    event_keys: set[str] = set()
    boundary_keys: set[str] = set()
    separation_keys = _product_separation_keys(identity)
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
        for model in macbook_models:
            event_keys.add(f"apple-retail:refurbished:macbook-{model}")
            separation_keys.add(f"product-model:macbook-{model}")
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

    os_feature_scope = _versioned_os_feature_scope(text, identity)
    if os_feature_scope:
        event_keys.add(os_feature_scope)
        boundary_keys.add(os_feature_scope)

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

    if content_form == "event_preview" and not event_format_plan:
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
    if (
        not hard_boundary
        and relevance_tier == "weak"
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
    if relevance_tier == "weak":
        weak_topic = _weak_topic_separation_key(title_text)
        if weak_topic:
            separation_keys.add(weak_topic)
    return ReconciliationProfile(
        event_keys=frozenset(event_keys),
        boundary_keys=frozenset(boundary_keys),
        separation_keys=frozenset(separation_keys),
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
    if left.event_keys & right.event_keys:
        return False
    if bool(left.hard_boundary) != bool(right.hard_boundary) and not (left.event_keys & right.event_keys):
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
    for namespace in ("product-family:", "product-model:", "legal-party:", "action:", "weak-topic:"):
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
