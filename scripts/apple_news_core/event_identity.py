"""Title-led event identity and relevance guards.

The crawler's detail body is intentionally not authoritative here. Bodies are
useful for facts, but related links and background paragraphs can mention many
unrelated Apple products. Event identity therefore comes from the title first
and only falls back to a short lead when the title is sparse.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable


@dataclass(frozen=True)
class EventIdentity:
    products: frozenset[str]
    components: frozenset[str]
    actors: frozenset[str]
    title_products: frozenset[str]
    title_components: frozenset[str]
    title_actors: frozenset[str]
    actions: frozenset[str]
    title_actions: frozenset[str]
    facets: frozenset[str]
    counterparties: frozenset[str]
    case_topics: frozenset[str]
    named_subjects: frozenset[str]
    content_form: str
    scope: str

    @property
    def specific_anchors(self) -> frozenset[str]:
        return (
            self.products
            | self.components
            | self.actors
            | self.facets
            | self.counterparties
            | self.case_topics
            | self.named_subjects
        )


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip()


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


APPLE_TITLE_TERMS = (
    "apple",
    "iphone",
    "ipad",
    "ios",
    "ipados",
    "macbook",
    "macos",
    "watchos",
    "tvos",
    "visionos",
    "airpods",
    "icloud",
    "safari",
    "siri",
    "carplay",
    "xcode",
    "app store",
    "apple wallet",
    "苹果",
)


PRODUCT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ios", ("ios",)),
    ("ipados", ("ipados",)),
    ("macos", ("macos",)),
    ("watchos", ("watchos",)),
    ("tvos", ("tvos",)),
    ("visionos", ("visionos",)),
    ("foldable-iphone", ("foldable iphone", "folding iphone", "iphone fold", "iphone ultra", "折叠屏 iphone", "折叠 iphone", "折叠屏iphone", "折叠iphone")),
    ("iphone", ("iphone",)),
    ("ipad-mini", ("ipad mini", "ipadmini")),
    ("ipad-air", ("ipad air", "ipadair")),
    ("ipad-pro", ("ipad pro", "ipadpro")),
    ("ipad", ("ipad",)),
    ("macbook", ("macbook",)),
    ("mac", ("macos", " mac ", "mac 电脑", "苹果电脑")),
    ("apple-watch", ("apple watch", "watchos", "苹果手表")),
    ("airpods", ("airpods",)),
    ("vision-pro", ("vision pro", "visionos")),
    ("apple-tv", ("apple tv", "tvos", "苹果 tv", "苹果电视")),
    ("apple-sports", ("apple sports", "apple's sports app", "apple’s sports app", "苹果 sports")),
    ("apple-books", ("apple books", "苹果图书")),
    ("apple-arcade", ("apple arcade", "苹果 arcade")),
    ("apple-music", ("apple music", "苹果音乐")),
    ("apple-one", ("apple one",)),
    ("icloud", ("icloud",)),
    ("safari", ("safari", "webkit")),
    ("siri", ("siri",)),
    ("app-store", ("app store", "应用商店")),
    ("apple-wallet", ("apple wallet", "苹果钱包", "数字车钥匙")),
    ("xcode", ("xcode",)),
    ("carplay", ("carplay",)),
    ("apple-intelligence", ("apple intelligence", "apple 智能", "apple智能", "苹果智能", "苹果 ai", "苹果ai")),
)


COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hide-my-email", ("hide my email", "隐藏我的邮件", "隐藏我的电子邮件", "隐藏电子邮件")),
    ("vapor-chamber", ("vapor chamber", "vapor cooling", "vapour chamber", "均热板", "vc 散热", "vc散热")),
    ("oled-display", ("oled", "有机发光")),
    ("refurbished", ("refurbished", "refurb", "官方翻新", "官翻", "翻新机", "翻新")),
    ("server-chip", ("server chip", "server silicon", "服务器芯片")),
    ("model-quantization", ("model quantization", "quantization technology", "量化 ai", "ai 量化", "量化技术")),
    ("privacy-vulnerability", ("privacy flaw", "privacy vulnerability", "security flaw", "安全漏洞", "隐私漏洞")),
    ("thermal-design", ("thermal", "cooling", "散热", "冷却")),
    ("display-panel", ("display panel", "oled panel", "显示面板", "oled 面板", "oled面板")),
    ("car-key", ("car key", "car keys", "digital car key", "数字车钥匙", "车钥匙")),
    ("market-cap", ("market cap", "market capitalization", "most valuable company", "市值", "最有价值公司")),
    (
        "customer-loyalty",
        (
            "loyalty rate",
            "customer loyalty",
            "user loyalty",
            "switching to android",
            "switching from android",
            "android switchers",
            "same-platform upgrade",
            "同平台升级",
            "用户忠诚度",
            "忠诚度",
            "不愿换阵营",
            "用户画像",
            "转换用户比例",
            "用户转换比例",
            "转入比例",
        ),
    ),
    (
        "price-upgrade-behavior",
        (
            "slow upgrade cycles",
            "slower upgrade cycles",
            "upgrade frequency",
            "purchase behavior",
            "购买行为",
            "升级频率",
            "换机周期",
        ),
    ),
    (
        "spotlight-index-preparation",
        (
            "spotlight index to prepare",
            "spotlight indexing in ios",
            "optimizes the spotlight index",
            "optimize the spotlight index",
            "spotlight 索引",
            "spotlight索引",
        ),
    ),
    ("camera-system", ("variable aperture", "imx905", "可变光圈", "影像规格", "主摄")),
    ("recovery-mode", ("recovery screen", "recovery mode", "recovery assistant", "恢复界面", "恢复模式", "恢复助理")),
    (
        "dual-battery",
        (
            "two batteries",
            "dual battery",
            "dual-battery",
            "multiple internal batteries",
            "multiple iphone batteries",
            "multi-battery",
            "双电芯",
            "双电池",
            "多块电池",
            "多电池",
        ),
    ),
    (
        "office-real-estate",
        (
            "office building",
            "office lease",
            "leased office",
            "leases office",
            "office space",
            "another office",
            "new office",
            "办公楼",
            "办公空间",
            "新办公室",
            "新增办公室",
        ),
    ),
    (
        "writing-tools",
        ("writing tools", "write with siri", "写作工具", "siri 内容创作", "siri ai 内容创作"),
    ),
    ("app-catalog-metrics", ("new apps", "app submissions", "app catalog", "新上架应用", "应用提交", "应用数量")),
    ("nudify-apps", ("nudify", "nonconsensual undressing", "undressing apps", "ai 脱衣", "ai脱衣", "脱衣应用", "脱衣 app")),
    ("gambling-apps", ("gambling apps", "gambling app", "博彩应用", "博彩 app", "博彩app", "赌博应用")),
    ("future-price-forecast", ("price forecast", "expected price increase", "may raise", "could raise", "预计涨价", "预判", "或涨价", "提价后")),
    (
        "memory-supply",
        (
            "dram order",
            "dram orders",
            "memory order",
            "memory orders",
            "memory shortage",
            "memory supply",
            "priority dram",
            "内存订单",
            "内存短缺",
            "内存供应",
            "存储短缺",
            "dram 订单",
            "优先拿货",
            "优先供货",
        ),
    ),
    (
        "memory-supplier-sourcing",
        (
            "seeking memory",
            "memory supplier talks",
            "talks with cxmt",
            "testing cxmt",
            "procure cxmt",
            "找长鑫",
            "洽谈采购",
            "测试长鑫",
            "寻求长鑫",
        ),
    ),
    (
        "memory-order-allocation",
        (
            "orders booked through",
            "orders booked until",
            "priority supply",
            "priority allocation",
            "订单已排至",
            "订单排至",
            "产能已被预订",
            "优先拿货",
            "优先供货",
        ),
    ),
    (
        "memory-policy-restriction",
        (
            "lawmakers call to block",
            "lawmakers demand a review",
            "national security threat",
            "议员紧急叫停",
            "议员要求审查",
            "威胁国家安全",
        ),
    ),
)

EVIDENCE_BACKED_COMPONENTS = {
    # Release-note features can sit just beyond a site's repeated title/deck.
    # Only narrowly named components belong here; broad hardware or service
    # terms in later facts must not redefine an event.
    "spotlight-index-preparation",
}


ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("legal", ("lawsuit", "court", "class action", "legal action", "legal battle", "legal dispute", "legal letter", "antitrust case", "settlement", "trial", "诉讼", "起诉", "法院", "法庭", "对簿公堂", "集体诉讼", "法律纠纷", "律师函", "反垄断", "和解谈判")),
    (
        "security",
        (
            "vulnerability",
            "security flaw",
            "privacy flaw",
            "malware",
            "stealer",
            "trojan",
            "spyware",
            "ransomware",
            "漏洞",
            "安全问题",
            "隐私问题",
            "恶意软件",
            "窃密",
            "木马",
            "勒索",
        ),
    ),
    ("regulation", ("regulator", "regulatory", "approved", "approval", "filing", "registered", "fine", "ordered to remove", "demand to pull", "investigation", "备案", "获批", "监管", "罚款", "合规", "检方要求", "要求下架", "下架")),
    ("transaction", ("acquire", "acquisition", "merger", "partner", "partnership", "evaluate", "evaluation", "talks", "lease", "leases", "leased", "leasing", "收购", "合作", "接洽", "评估", "洽谈", "租赁", "租下", "承租")),
    ("supply-production", ("order", "orders", "supplier", "supply", "production", "mass production", "manufacture", "量产", "订单", "供应商", "供货", "生产")),
    ("investment-capacity", ("investment", "invest", "plant", "plants", "fab", "factory", "capacity", "扩产", "投资", "工厂", "晶圆厂", "产能")),
    ("retail-availability", ("selling", "available", "store", "refurbished", "launch", "release", "上架", "开售", "发售", "上市", "官翻", "翻新")),
    ("delay-roadmap", ("delay", "delayed", "roadmap", "reportedly", "rumor", "expected", "target", "推迟", "延期", "路线图", "传闻", "预计", "计划")),
    ("feature-change", ("adds", "added", "changes", "changed", "improves", "improved", "removes", "removed", "upgrade", "update", "new feature", "makes", "新增", "加入", "改进", "升级", "移除", "更新", "调整")),
    ("price-change", ("price increase", "price increases", "price hike", "raises price", "raises prices", "increases subscription prices", "costs $", "涨价", "提价", "上调价格", "上调售价", "降价")),
    ("market-report", ("market report", "survey", "cirp report", "cirp", "调查报告", "报告显示")),
    ("market-ranking", ("most valuable company", "market capitalization", "market cap", "市值最高", "市值")),
    ("pilot-testing", ("is testing", "are testing", "testing", "pilot", "piloting", "trialing", "试点", "测试")),
    (
        "content-release",
        (
            "unveils new film",
            "unveils film",
            "coming to apple tv",
            "dated for apple tv",
            "stream on apple tv",
            "streaming on apple tv",
            "hits apple tv",
            "premieres on apple tv",
            "is to screen",
            "will screen",
            "to apple arcade",
            "for apple arcade",
            "through apple arcade",
            "推出电影",
            "推出影片",
            "上架 apple tv",
            "上线 apple tv",
            "登陆 apple tv",
            "登陆 apple arcade",
            "上线 apple arcade",
        ),
    ),
    (
        "platform-trust",
        (
            "counterfeit",
            "counterfeits",
            "fake books",
            "fake ebooks",
            "fake versions",
            "ai fakes",
            "ai-generated fake",
            "impersonation",
            "pirated books",
            "盗版书",
            "仿冒书",
            "冒牌书",
            "假冒作品",
            "伪造作品",
            "ai 生成的盗版",
        ),
    ),
    (
        "project-cancellation",
        (
            "cancelled",
            "canceled",
            "cancelling",
            "canceling",
            "scrapped",
            "abandoned",
            "unreleased",
            "not to release",
            "decided not to release",
            "discontinued the project",
            "砍掉",
            "取消",
            "未发布",
            "未能发布",
            "搁置",
            "放弃该项目",
        ),
    ),
)


UMBRELLA_FACETS = {
    "apple-legal-proceeding",
    "built-in-app-change",
    "hardware-roadmap",
    "os-release-beta",
    "system-summary",
}

CROSS_PRODUCT_IDENTITY_FACETS = {
    "apple-cross-device-pairing-api",
    "apple-device-battery-regulation",
    "apple-education-promotion",
    "final-cut-camera-update",
}

DIRECT_IDENTITY_FACETS = {
    "app-store-policy",
    "apple-memory-supplier-sourcing",
    "apple-restricted-memory-supplier-approval",
    "apple-wallet-car-key-partner-support",
}


def _extract_patterns(text: str, patterns: tuple[tuple[str, tuple[str, ...]], ...]) -> set[str]:
    return {name for name, aliases in patterns if _contains_any(text, aliases)}


GENERIC_NAMED_SUBJECTS = {
    "ai",
    "apple",
    "apple-intelligence",
    "apple-store",
    "extreme",
    "genius-bar",
    "iphone",
    "ipad",
    "ios",
    "mac-pro",
    "mac-studio",
    "report",
    "system",
    "tool",
    "wwdc",
}


def _subject_slug(value: str) -> str:
    value = _normalized(value).strip(" .,:;!?()[]{}")
    value = re.sub(r"[^a-z0-9+.-]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def _valid_named_subject(value: str) -> str | None:
    value = re.sub(r"\s+", " ", value).strip(" .,:;!?()[]{}\"'“”‘’")
    if not value or len(value) > 48:
        return None
    if len(value.split()) > 5:
        return None
    slug = _subject_slug(value)
    if len(slug) < 3 or slug in GENERIC_NAMED_SUBJECTS:
        return None
    if not re.search(r"[a-z]", slug) and not re.fullmatch(r"[a-z]{1,4}\d{3,5}", slug):
        return None
    return slug


def _canonical_named_subject(value: str) -> str | None:
    slug = _valid_named_subject(value)
    if not slug:
        return None
    for suffix in ("-stealer", "-loader", "-trojan", "-spyware", "-malware", "-ransomware"):
        if slug.endswith(suffix) and len(slug) > len(suffix) + 3:
            slug = slug[: -len(suffix)]
            break
    return slug


def _valid_quoted_subject(value: str) -> str | None:
    subject = _canonical_named_subject(value)
    if not subject:
        return None
    original = value.strip()
    if re.fullmatch(r"(?:M\d+\s+Extreme|[A-Z]{1,4}\d{3,5})", original, re.I):
        return subject
    if re.fullmatch(r"[A-Z][A-Za-z0-9+.-]*(?:\s+[A-Z][A-Za-z0-9+.-]*)+", original):
        return subject
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9+.-]*", original):
        return subject
    return None


def _valid_content_title(value: str) -> str | None:
    value = re.sub(r"\s+", " ", value).strip(" .,:;!?()[]{}\"'“”‘’—-")
    if not value or len(value) > 64 or len(value.split()) > 8:
        return None
    words = value.split()
    if len(words) < 2:
        return None
    connectors = {"a", "an", "and", "at", "for", "from", "in", "is", "my", "no", "not", "of", "on", "the", "to", "with"}
    significant = [word for word in words if word.lower().strip(".:,+-") not in connectors]
    if not significant or not all(re.match(r"^[A-Z][A-Za-z0-9+.'-]*$", word) for word in significant):
        return None
    return _canonical_named_subject(value)


def _named_subjects(title: str, lead: str, evidence: Iterable[str] = ()) -> set[str]:
    """Extract rare title/lead anchors without treating reporter names as event identity."""
    identity_lead = re.split(
        r"(?:\bbackground(?: paragraphs?| context)?\b|\bpreviously\b|\bmeanwhile\b|"
        r"背景(?:段落|信息|资料)?|此前(?:报道|消息)?|与此同时)",
        lead[:700],
        maxsplit=1,
        flags=re.I,
    )[0]
    scoped = f"{title} {identity_lead}"
    subjects: set[str] = set()

    for match in re.finditer(r"[\"'“‘]([^\"'“”‘’\n]{2,48})[\"'”’]", scoped):
        subject = _valid_quoted_subject(match.group(1))
        if subject:
            subjects.add(subject)

    named_pattern = re.compile(
        r"(?:called|named|codenamed|known as|名为|代号(?:分别)?为?)\s*[\"'“‘]?"
        r"([A-Z][A-Za-z0-9+.-]*(?:\s+[A-Z][A-Za-z0-9+.-]*){0,3})"
    )
    for match in named_pattern.finditer(scoped):
        subject = _canonical_named_subject(match.group(1))
        if subject:
            subjects.add(subject)

    for match in re.finditer(
        r"(?<![A-Za-z0-9])(?:M\d+\s+Extreme|[A-Z]{1,4}\d{3,5})(?![A-Za-z0-9])",
        scoped,
        re.I,
    ):
        subject = _canonical_named_subject(match.group(0))
        if subject:
            subjects.add(subject)

    for match in re.finditer(
        r"(?<![A-Za-z0-9])(?:A\d{1,2}\s*Pro|M\d{1,2}(?:\s*(?:Pro|Max|Ultra|Extreme))?)(?![A-Za-z0-9])",
        scoped,
        re.I,
    ):
        subject = _canonical_named_subject(match.group(0))
        if subject:
            subjects.add(subject)

    for match in re.finditer(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9+.-]*\b", scoped):
        subject = _canonical_named_subject(match.group(0))
        if subject:
            subjects.add(subject)

    for pattern in (
        r"[（(]([A-Z][A-Za-z0-9+.'-]*(?:\s+(?:[A-Za-z][A-Za-z0-9+.'-]*)){1,7})[)）]",
        r"(?:book|film|movie|series|title|follow-up)[^。.!?\n]{0,36}[—-]\s*([A-Z][A-Za-z0-9+.'-]*(?:\s+[A-Za-z][A-Za-z0-9+.'-]*){1,7})\s*[—-]",
        r"\bbook\s+([A-Z][A-Za-z0-9+.'-]*(?:\s+[A-Za-z][A-Za-z0-9+.'-]*){1,7})(?=\s+(?:on|in|from|within|was|is)\b)",
    ):
        for match in re.finditer(pattern, scoped):
            subject = _valid_content_title(match.group(1))
            if subject:
                subjects.add(subject)
    return subjects


def _collapse_product_hierarchy(products: set[str]) -> set[str]:
    if "foldable-iphone" in products:
        products.discard("iphone")
    if products & {"ipad-mini", "ipad-air", "ipad-pro"}:
        products.discard("ipad")
    return products


def _normalized_os_version(value: str) -> str:
    parts = value.split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


def _title_named_actors(title: str) -> set[str]:
    excluded = {
        "ai",
        "a20",
        "apple",
        "airpods",
        "ceo",
        "cnbeta",
        "com",
        "ios",
        "ipad",
        "iphone",
        "it",
        "lg",
        "nfc",
        "nand",
        "dram",
        "ram",
        "suv",
        "suvs",
        "usa",
        "usb",
        "wwdc",
        "macrumors",
        "macbook",
        "oled",
        "pro",
        "report",
        "the",
    }
    actors = {
        token.lower()
        for token in re.findall(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9.-]{2,})(?![A-Za-z0-9])", title)
        if token.lower() not in excluded
        and (
            (token.isupper() and 3 <= len(token) <= 10)
            or (not token.isupper() and any(character.isupper() for character in token[1:]))
        )
    }
    for token in ("tsmc", "prismml", "baltra", "openai", "roblox", "samsung", "signal ring"):
        if token in _normalized(title):
            actors.add(token)
    return actors


def _legal_counterparties(title: str, lead: str, facets: Iterable[str]) -> set[str]:
    text = f"{_normalized(title)} {_normalized(lead)[:420]}"
    counterparties = {
        facet.removeprefix("legal-counterparty-")
        for facet in facets
        if facet.startswith("legal-counterparty-")
    }
    aliases = (
        ("doj", (" doj ", "department of justice", "justice department", "美国司法部", "司法部")),
        ("openai", ("openai",)),
        ("epic", ("epic games", "epic")),
        ("eu", ("european commission", "欧盟委员会")),
        ("cma", ("competition and markets authority", " cma ", "英国竞争与市场管理局")),
    )
    padded = f" {text} "
    for name, terms in aliases:
        if _contains_any(padded, terms):
            counterparties.add(name)
    return counterparties


def _legal_case_topics(title: str, lead: str, facets: Iterable[str]) -> set[str]:
    text = f"{_normalized(title)} {_normalized(lead)[:520]}"
    topics: set[str] = set()
    aliases = (
        ("antitrust", ("antitrust", "anti-monopoly", "反垄断", "垄断诉讼")),
        ("trade-secret", ("trade secret", "trade-secret", "商业机密", "商业秘密", "窃取机密")),
        ("privacy", ("privacy", "hide my email", "隐私", "隐藏我的邮件", "隐藏电子邮件")),
        ("patent", ("patent", "专利")),
    )
    for name, terms in aliases:
        if _contains_any(text, terms):
            topics.add(name)
    if "apple-hardware-trade-secret-lawsuit" in facets:
        topics.add("trade-secret")
    return topics


def _content_form(title: str, lead: str = "") -> str:
    lower = _normalized(title)
    lead_lower = _normalized(lead)[:700]
    if re.search(r"\b(?:podcast|episode|overtime)\b", lower) or (
        re.search(
            r"\b(?:podcast episode|weekly podcast|video-first podcast|"
            r"(?:on\s+)?this week['’]s episode of (?:the )?.{0,80}?podcast|"
            r"episode of (?:the )?.{0,80}?podcast)\b",
            lead_lower,
        )
        and not re.search(r"\b(?:launches|releases|updates|adds|announces)\b", lower)
    ):
        return "podcast"
    if re.search(r"\b(?:here['’]s the fix|troubleshooting guide|fix seems to work)\b|故障排查|解决办法", lower):
        return "tutorial"
    if (
        "poll" in lower
        or re.match(r"^(?:what|which|would|will|should)\b.*\?", lower)
        or re.search(r"(?:vote|投票|你会怎么|你会如何|你是否).*[?？]?$", lower)
    ):
        return "poll"
    if re.search(
        r"\b(?:rumors? point to|everything we know|"
        r"what to expect|these \d+ (?:new )?(?:features|changes)|"
        r"\d+ rumored features|best .+ to try)\b|传闻汇总|功能汇总|值得期待的\s*\d+",
        lower,
    ) or re.match(
        r"^(?:everything new|here['’]s what['’]s new|what['’]s new with)\b",
        lower,
    ) or "更新汇总" in lower or (
        re.search(r"\bcoming\b.{0,42}\bwith (?:these|\d+) (?:rumored )?new features\b", lower)
        and re.search(r"\b(?:recaps?|previously reported|rumored so far|no new reporting)\b|汇总此前|此前传闻|无新增", lead_lower)
    ):
        return "roundup"
    if re.match(r"^(?:is|are) .+ worth it\b", lower) or re.search(r"值不值得|是否值得", lower):
        return "analysis"
    if re.search(
        r"\b(?:weekend deals?|daily deals?|best deals?|deal roundup|prime day|shopping guide)\b|"
        r"\b(?:up to\s+)?[$£€¥]\s*\d+(?:[.,]\d+)?\s+off\b|"
        r"(?:周末|每日|今日)?(?:优惠|好价|促销)(?:汇总|合集)?",
        lower,
    ):
        return "deal"
    if re.search(r"\b(?:discounts?|markdowns?|savings?|sale)\b", lower) and re.search(
        r"[$£€¥]\s*\d|\b\d+(?:\.\d+)?\s*%|\bup to\b|\boff\b",
        lower,
    ):
        return "deal"
    if re.search(
        r"\b(?:should(?:n['’]t| not)? (?:buy|wait|upgrade)|should you (?:buy|wait|upgrade)|"
        r"buy now or wait|upgrade now or wait|why you should(?:n['’]t| not)? wait|"
        r"before you buy|buying advice|buying guide)\b|"
        r"(?:该不该|要不要|是否应该)(?:买|等|升级)|买还是等|购买建议|换机建议",
        lower,
    ):
        return "buying_advice"
    if re.search(r"\b(?:indie app spotlight|app spotlight|app pick)\b|(?:应用|app)推荐", lower):
        return "third_party_spotlight"
    if re.search(
        r"^(?:analyst|analysis|opinion|commentary)\b|"
        r"^(?:分析师|机构观点|评论)[：:]|(?:分析师|评论人士).{0,24}(?:认为|称|表示)|"
        r"\b(?:now\s+)?(?:even\s+)?more valuable\b|\bbetter value\b|(?:更有价值|更划算)",
        lower,
    ):
        return "analysis"
    if re.search(r"\b(?:hands-on|hands on|first impressions?)\b|(?:公测版|测试版)?.{0,10}(?:上手|体验)", lower):
        return "hands_on"
    return "news"


def _title_scope(title: str, lead: str) -> str:
    title_lower = _normalized(title)
    lead_lower = _normalized(lead)[:600]
    apple_in_title = _contains_any(title_lower, APPLE_TITLE_TERMS)
    first_party_prefix = bool(
        re.match(
            r"^(?:apple(?:'s)?|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods|icloud|safari|siri|carplay|xcode|app store|苹果|传苹果|消息称苹果|报道称苹果)",
            title_lower,
        )
    )
    direct_target = bool(
        re.search(
            r"(?:sues?|sued|fines?|threatens?|investigates?|orders?|blocks?|approves?|起诉|罚款|调查|要求|批准).{0,45}(?:apple|苹果)",
            title_lower,
        )
    )
    comparison = bool(
        re.search(
            r"(?:better than|versus|\bvs\.?\b|rival(?:s|ing)?|compared (?:with|to)|beats?|"
            r"overtakes?|surpasses?|dethrones?|exceeds?|挑战|对标|媲美|优于|胜过|超越|超过|力压|"
            r"接近|相当于|追平)"
            r".{0,50}(?:apple|iphone|ipad|mac|airpods|苹果)",
            title_lower,
        )
    )
    platform_only = bool(
        re.search(
            r"(?:app|game|service|client|tool|browser|software|ring|headset).{0,55}(?:on|for|to) (?:iphone|ipad|mac|apple watch)\b",
            title_lower,
        )
        or re.search(
            r"(?:应用|游戏|服务|客户端|工具|浏览器|软件|戒指|头显).{0,28}(?:登陆|上线|支持|适配).{0,16}(?:iphone|ipad|mac|苹果平台)",
            title_lower,
        )
    )
    if first_party_prefix:
        return "apple-direct"
    if comparison:
        return "third-party-context"
    if direct_target:
        return "apple-direct"
    if apple_in_title:
        if platform_only and not title_lower.startswith(tuple(APPLE_TITLE_TERMS)):
            return "third-party-context"
        return "apple-direct"
    return "unknown"


def is_non_apple_title_context(title: str, lead: str) -> bool:
    """Return true only when Apple is comparison, compatibility, or list context."""
    return _title_scope(title, lead) == "third-party-context"


def is_non_apple_comparison_title(title: str) -> bool:
    title_lower = _normalized(title)
    if bool(
        re.match(
            r"^(?:apple(?:'s)?|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods|icloud|safari|siri|carplay|xcode|app store|苹果)",
            title_lower,
        )
    ):
        return False
    return bool(
        re.search(
            r"(?:better than|versus|\bvs\.?\b|rival(?:s|ing)?|compared (?:with|to)|beats?|挑战|对标|媲美|优于|胜过).{0,50}(?:apple|iphone|ipad|mac|airpods|苹果)",
            title_lower,
        )
    )


def is_direct_first_party_feature_change(title: str, lead: str) -> bool:
    title_lower = _normalized(title)
    lead_lower = _normalized(lead)[:800]
    if _title_scope(title, lead) != "apple-direct":
        return False
    if not _extract_patterns(f"{title_lower} {lead_lower}", ACTION_PATTERNS) & {"feature-change"}:
        return False
    first_party_feature = _extract_patterns(title_lower, PRODUCT_PATTERNS) & {
        "apple-books",
        "apple-music",
        "apple-sports",
        "apple-tv",
        "icloud",
        "safari",
        "siri",
        "app-store",
        "xcode",
        "carplay",
        "apple-intelligence",
    }
    versioned_platform = bool(
        re.search(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*\d", title_lower)
    )
    return bool(first_party_feature or versioned_platform)


def high_confidence_direct_apple_action(identity: EventIdentity) -> bool:
    """Return true when title-led semantics prove a direct Apple action."""
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return False
    if "market-cap" in identity.components and "market-ranking" in identity.actions:
        return True
    if "customer-loyalty" in identity.components and "market-report" in identity.actions:
        return True
    if identity.facets & DIRECT_IDENTITY_FACETS:
        return True
    if "car-key" in identity.components:
        return True
    if "memory-supply" in identity.components and "supply-production" in identity.actions:
        return True
    if "office-real-estate" in identity.components and "transaction" in identity.actions:
        return True
    if "writing-tools" in identity.components and identity.products & {"mac", "macos", "siri"}:
        return True
    if "app-catalog-metrics" in identity.components and "app-store" in identity.products:
        return True
    if identity.products & {"apple-books", "apple-sports"} and identity.actions & {
        "feature-change",
        "platform-trust",
        "retail-availability",
    }:
        return True
    if "app-store" in identity.products and identity.actions & {"legal", "regulation"}:
        return True
    return False


def build_event_identity(
    title: str,
    lead: str,
    facets: Iterable[str] = (),
    identity_evidence: Iterable[str] = (),
) -> EventIdentity:
    identity_evidence = tuple(identity_evidence)
    title_lower = _normalized(title)
    lead_lower = _normalized(lead)[:900]
    content_form = _content_form(title, lead)
    title_products = _collapse_product_hierarchy(_extract_patterns(title_lower, PRODUCT_PATTERNS))
    if re.search(r"\bipad\s*\d+\b|\b(?:base|entry-level) ipad\b|(?:入门版|基础款)\s*ipad", title_lower):
        title_products.discard("ipad")
        title_products.add("ipad-base")
    products = set(title_products)
    if not products and content_form != "roundup":
        products = _collapse_product_hierarchy(
            _extract_patterns(f"{title_lower} {lead_lower[:260]}", PRODUCT_PATTERNS)
        )
    direct_service_products = {
        "apple-arcade",
        "apple-books",
        "apple-music",
        "apple-one",
        "apple-sports",
        "apple-tv",
        "icloud",
    }
    if content_form != "roundup" and not (title_products & direct_service_products):
        products |= _extract_patterns(lead_lower[:260], PRODUCT_PATTERNS) & direct_service_products
    title_components = _extract_patterns(title_lower, COMPONENT_PATTERNS)
    components = set(title_components)
    if not components and content_form != "roundup":
        components = _extract_patterns(
            f"{title_lower} {lead_lower[:420]}", COMPONENT_PATTERNS
        )
    if not components and content_form != "roundup" and identity_evidence:
        for evidence_item in identity_evidence[:6]:
            components |= (
                _extract_patterns(_normalized(evidence_item)[:420], COMPONENT_PATTERNS)
                & EVIDENCE_BACKED_COMPONENTS
            )
    identity_scope = f"{title_lower} {lead_lower[:700]}"
    if "office-real-estate" in components:
        office_places: set[str] = set()
        office_scope = f"{title} {lead[:420]}"
        for match in re.finditer(
            r"(?:\b(?:in|at|near)\s+|[（(])([A-Z][A-Za-z.-]{3,30})(?:\b|[)）])",
            office_scope,
        ):
            place = _subject_slug(match.group(1))
            if place and place not in {
                "apple",
                "avenue",
                "building",
                "california",
                "company",
                "office",
                "street",
            }:
                office_places.add(f"office-place:{place}")
        components |= office_places
        title_components |= {
            component
            for component in office_places
            if component.removeprefix("office-place:") in title_lower
        }
    base_terms = ("base iphone", "standard iphone", "基础款 iphone", "基础款iphone", "标准版 iphone", "标准版iphone")
    delay_terms = (
        "delay",
        "delayed",
        "postpone",
        "next year launch",
        "推迟",
        "延期",
        "延后",
        "放到明年",
        "改在明年",
        "明年初发布",
    )
    margin_terms = (
        "pro",
        "high-margin",
        "high margin",
        "higher-margin",
        "premium",
        "高利润",
        "利润更高",
        "利润较高",
        "高端",
    )
    title_targets_release_mix = (
        _contains_any(title_lower, base_terms) and _contains_any(title_lower, delay_terms)
    ) or _contains_any(title_lower, margin_terms)
    if (
        title_targets_release_mix
        and _contains_any(identity_scope, base_terms)
        and _contains_any(identity_scope, delay_terms)
        and _contains_any(identity_scope, margin_terms)
    ):
        components.add("product-release-mix")
    title_actions = _extract_patterns(title_lower, ACTION_PATTERNS)
    actions = set(title_actions)
    if content_form != "roundup":
        actions |= _extract_patterns(lead_lower[:500], ACTION_PATTERNS)
    if re.search(r"\bsu(?:e|es|ed|ing)\b", title_lower):
        title_actions.add("legal")
        actions.add("legal")
    elif re.search(r"\bsu(?:e|es|ed|ing)\b", lead_lower[:500]):
        actions.add("legal")
    price_change_pattern = (
        r"\b(?:raise[sd]?|increase[sd]?|hike[sd]?)\b.{0,36}\b(?:price|prices|pricing|cost|costs)\b|"
        r"\b(?:bump(?:s|ed)?|put(?:s)?|push(?:es|ed)?|send(?:s|ing)?)\b.{0,20}\b(?:up|higher)\b.{0,24}\b(?:price|prices|pricing|cost|costs)\b|"
        r"\b(?:bump(?:s|ed)?|put(?:s)?|push(?:es|ed)?)\s+up\s+(?:the\s+)?(?:price|prices|pricing|cost|costs)\b|"
        r"\b(?:price|prices|pricing|cost|costs)\b.{0,24}\b(?:rise|rises|increase[sd]?|hike[sd]?)\b|"
        r"(?:上调|提高|调高|调整).{0,24}(?:价格|售价|订阅价)|(?:价格|售价).{0,18}(?:上调|上涨|提高)"
    )
    if re.search(price_change_pattern, title_lower):
        title_actions.add("price-change")
        actions.add("price-change")
    elif re.search(price_change_pattern, lead_lower[:220]):
        actions.add("price-change")
    actors = _title_named_actors(title)
    if not actors:
        actors = _title_named_actors(f"{title} {lead[:180]}")
    specific_facets = {
        facet
        for facet in facets
        if facet not in UMBRELLA_FACETS
        and not facet.startswith("platform-")
        and not facet.startswith("os-release-")
    }
    release_versions = sorted(
        _normalized_os_version(facet.removeprefix("os-release-version-").replace("-", "."))
        for facet in facets
        if facet.startswith("os-release-version-")
    )
    if not release_versions:
        release_versions = sorted(
            {
                _normalized_os_version(match.group(1))
                for match in re.finditer(
                    r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)?)\b",
                    f"{title_lower} {lead_lower[:260]}",
                )
            }
        )
    main_title = re.split(r"[\[\(（【]", title_lower, maxsplit=1)[0]
    title_is_public_beta = bool(
        re.search(r"\bpublic betas?\b|公测(?:版|测试版)?", main_title)
    )
    title_has_explicit_beta_number = bool(
        re.search(r"\bbeta\s*\d+\b|测试版\s*\d+|第\s*\d+\s*(?:个|版)?\s*测试版", main_title)
    )
    numbered_beta_stages = sorted(
        facet.removeprefix("os-release-")
        for facet in facets
        if re.fullmatch(r"os-release-beta-\d+", facet)
    )
    if not numbered_beta_stages:
        release_scope = f"{main_title} {lead_lower[:220]}"
        beta_match = re.search(r"\bbeta\s*(\d+)\b", release_scope)
        if beta_match:
            numbered_beta_stages = [f"beta-{beta_match.group(1)}"]
        else:
            ordinal_numbers = {
                "one": "1",
                "first": "1",
                "two": "2",
                "second": "2",
                "three": "3",
                "third": "3",
                "four": "4",
                "fourth": "4",
                "five": "5",
                "fifth": "5",
                "six": "6",
                "sixth": "6",
            }
            ordinal_match = re.search(
                r"\b(?:round|developer beta)\s+(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth)\b",
                release_scope,
            )
            if ordinal_match:
                numbered_beta_stages = [f"beta-{ordinal_numbers[ordinal_match.group(1)]}"]
        if not numbered_beta_stages:
            chinese_number_map = {
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
            chinese_match = re.search(
                r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*(?:开发者)?测试版",
                release_scope,
            )
            if chinese_match:
                raw_number = chinese_match.group(1)
                number = raw_number if raw_number.isdigit() else chinese_number_map.get(raw_number)
                if number:
                    numbered_beta_stages = [f"beta-{number}"]
    title_is_release_wave = bool(
        re.search(
            r"\b(?:releases?|released|seeds?|seeded|rolls? out|now available|is here|are out now|arrives?|revised|surfaces?|is coming soon|are coming soon|coming next week)\b|"
            r"\bstarts?\s+round\b|\bversion\s*2\s+update\b|"
            r"(?:即将发布|最快.{0,8}发布|发布|推送|释出|修订版)|(?:正式版|候选版).{0,12}上线",
            main_title,
        )
    )
    if "os-release-rc" in facets:
        release_stages = ["rc"]
    elif "os-release-final" in facets:
        release_stages = ["final"]
    elif (title_is_public_beta and not title_has_explicit_beta_number) or (
        "os-release-public-beta" in facets and not numbered_beta_stages
    ):
        release_stages = ["public-beta"]
    else:
        release_stages = numbered_beta_stages
    if release_versions and release_stages and title_is_release_wave:
        components.add(f"os-wave:{release_versions[0]}:{release_stages[0]}")
    if release_stages and title_is_release_wave:
        platform_names = {
            match.group(1)
            for match in re.finditer(
                r"\b(ios|ipados|macos|watchos|tvos|visionos)\b",
                main_title,
            )
        }
        for platform in platform_names:
            components.add(f"os-wave-platform:{platform}:{release_stages[0]}")
    return EventIdentity(
        products=frozenset(products),
        components=frozenset(components),
        actors=frozenset(actors),
        title_products=frozenset(title_products),
        title_components=frozenset(title_components),
        title_actors=frozenset(_title_named_actors(title)),
        actions=frozenset(actions),
        title_actions=frozenset(title_actions),
        facets=frozenset(specific_facets),
        counterparties=frozenset(
            _legal_counterparties(title, "" if content_form == "roundup" else lead, facets)
        ),
        case_topics=frozenset(
            _legal_case_topics(title, "" if content_form == "roundup" else lead, facets)
        ),
        named_subjects=frozenset(
            _named_subjects(
                title,
                "" if content_form == "roundup" else lead,
                () if content_form == "roundup" else identity_evidence,
            )
        ),
        content_form=content_form,
        scope=_title_scope(title, lead),
    )
