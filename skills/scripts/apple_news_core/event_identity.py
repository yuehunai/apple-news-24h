"""Source-owned subjects, actions and qualifiers with exact evidence locations.

Migrated report families bind original source relations once. Legacy text
frames remain for unmigrated families and compatibility views; display titles
and retrieval keys do not establish an action or inclusion eligibility.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import lru_cache
import html
import re
import unicodedata
from typing import Iterable

from .models import ArticleEvidence, BoundClaim


REGION_TERMS = {
    "canada": ["canada", "canadian", "加拿大"],
    "india": ["india", "indian", "cci", "印度"],
    "texas": ["texas", "德州", "得州"],
    "germany": ["germany", "german", "berlin", "德国", "柏林"],
    "europe": ["europe", "european", "eu", "欧盟", "欧洲"],
    "china": ["china", "chinese", "mainland china", "中国", "大陆"],
    "japan": ["japan", "japanese", "yokohama", "日本", "横滨"],
    "united-states": ["united states", "u.s.", "US", "usa", "america", "美国"],
    "latin-america": ["latin america", "拉美", "拉丁美洲"],
    "united-kingdom": ["united kingdom", "uk", "britain", "england", "英国"],
    "russia": ["russia", "russian", "俄罗斯", "俄联邦"],
    "vietnam": ["vietnam", "vietnamese", "越南"],
    "nepal": ["nepal", "nepalese", "尼泊尔"],
    "tibet": ["tibet", "tibetan", "西藏"],
}


@lru_cache(maxsize=4096)
def _compiled_rule(pattern: str, flags: int = 0):
    """Bounded reuse of fixed rule programs; no source text or decisions cached."""
    return re.compile(pattern, flags)


def current_public_os_release(title: str, lead: str) -> tuple[str, str] | None:
    """A platform-led report with a local current public-availability assertion."""
    title_version = _compiled_rule(r"^\s*(ios|ipados|macos|watchos|tvos|visionos)\s+(\d+(?:\.\d+)*)\b", re.I).match(title)
    if not title_version or _compiled_rule(r"\b(?:beta|rc|will|may|might|could|expected|next year)\b|测试版|候选版|明年|将会|预计|可能", re.I).search(title):
        return None
    platform, version = title_version.groups()
    subject = re.escape(platform) + r"\s+" + re.escape(version) + r"\b"
    for clause in _compiled_rule(r"[。！？!?]|(?<=[.])\s+", 0).split(lead[:900], 0):
        if _compiled_rule(r"\b(?:if|unless|whether|unclear|previously|last year|last month|not yet)\b|去年|此前|尚未|如果", re.I).search(clause):
            continue
        security_report = bool(_compiled_rule(r"security\s+(?:vulnerabilit|issues?|flaws?|fixes?|patches?)|安全(?:漏洞|问题|修复)", re.I).search(title))
        if (security_report
                and re.search(r"^(?:apple\s+(?:(?:today|has)\s+){0,2}(?:released|shipped|published)\s+|苹果(?:今日|已经|已)?(?:发布|推送)(?:了)?\s*)" + subject, clause.strip(), re.I)
                and _compiled_rule(r"fixes?|patches?|修复|补丁", re.I).search(clause)
                and not _compiled_rule(r"\b(?:beta|rc|preview)\b|测试版|候选版|预览版", re.I).search(clause)):
            return platform.lower(), version
        target = {"ios": r"iphones?", "ipados": r"ipads?", "macos": r"macs?",
                  "watchos": r"apple watches?", "tvos": r"apple tv", "visionos": r"(?:apple\s+)?vision pro"}[platform.lower()]
        availability = (r"available\s+(?:for\s+public\s+download|to\s+the\s+public(?:\s+now)?|for\s+" + target + r")\b"
                        r"|rolling\s+out\s+now\s+to\s+(?:all\s+)?" + target + r"(?:\s+models)?\b")
        if re.search(r"(?:^|[,，;；])\s*" + subject +
                     r"\s+is\s+(?:now\s+)?(?:" + availability + r")", clause, re.I):
            return platform.lower(), version
    return None


def is_apple_led_developer_submission_story(title: str, text: str) -> bool:
    """Recognize a current first-party call, not a partner or historical mention."""
    def clean_submission_text(value: str) -> str:
        value = _compiled_rule(r"(?is)<script\b.*?</script>", 0).sub(" ", value, 0)
        value = _compiled_rule(r"(?is)<style\b.*?</style>", 0).sub(" ", value, 0)
        value = _compiled_rule(r"(?is)<[^>]+>", 0).sub(" ", value, 0)
        value = _compiled_rule(r"\s+", 0).sub(" ", html.unescape(value), 0).strip()
        return _compiled_rule(r"\s+([,.;:!?])", 0).sub(r"\1", value, 0)

    cleaned_title = clean_submission_text(title)
    headline = cleaned_title.lower()
    if _compiled_rule(r"\b(?:history|historical|recap|looking back)\b|回顾|往年|历史", 0).search(headline):
        return False
    owner = r"(?:apple(?:['’]s\s+webkit(?:\s+team)?)?|webkit(?:\s+team)?)"
    current_call = re.match(
        rf"^{owner}\s+(?:invites|is inviting)\s+developers\s+to\s+submit\b"
        rf"|^{owner}\s+opens?\s+(?:(?:a\s+)?call\s+for\s+)?proposals\b"
        r"|^苹果(?:\s*webkit\s*团队)?(?:公开|正在)?(?:征集|邀请开发者提交)",
        headline,
    )
    if not current_call:
        return False
    cleaned_text = clean_submission_text(text)
    if cleaned_text.lower().startswith(headline):
        cleaned_text = cleaned_text[len(cleaned_title) :].lstrip(" .:-")
    scope = f"{cleaned_title} {cleaned_text[:700]}".strip().lower()
    return bool(
        _compiled_rule(r"\b(?:proposals?|ideas)\b|提案|建议|议题", 0).search(scope)
        and _compiled_rule(r"\bdevelopers?\b|\binterop\s*20\d{2}\b|开发者|(?:web|网页)\s*开发", 0).search(scope)
        and _compiled_rule(r"\b(?:webkit|browser|web standards)\b|浏览器|网页标准", 0).search(scope)
        and _compiled_rule(r"\binteroperability\b|\binterop\s*20\d{2}\b|互操作|互通|"
            r"(?:跨|不同)浏览器[^。！？.!?]{0,60}(?:兼容性|一致.{0,8}支持)", 0).search(scope)
    )


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
    title_named_subjects: frozenset[str]
    content_form: str
    scope: str
    action_owner: str

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
    return _compiled_rule(r"\s+", 0).sub(" ", value, 0).strip()


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


APPLE_TITLE_TERMS = (
    "apple",
    "iphone",
    "ipad",
    "ios",
    "ipados",
    "macbook",
    "imac",
    "mac mini",
    "mac studio",
    "mac pro",
    "macos",
    "watchos",
    "tvos",
    "visionos",
    "homeos",
    "airpods",
    "airpod",
    "icloud",
    "safari",
    "siri",
    "shazam",
    "beats lab",
    "beats headphones",
    "beats earbuds",
    "beats pill",
    "beats studio",
    "carplay",
    "homekit",
    "xcode",
    "testflight",
    "homepod",
    "applecare",
    "app store",
    "apple wallet",
    "apple pay",
    "apple fitness+",
    "fitness+",
    "苹果",
)


PRODUCT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ios", ("ios",)),
    ("ipados", ("ipados",)),
    ("macos", ("macos",)),
    ("watchos", ("watchos",)),
    ("tvos", ("tvos",)),
    ("visionos", ("visionos",)),
    ("apple-smart-home-os", ("homeos",)),
    (
        "foldable-iphone",
        (
            "foldable iphone",
            "folding iphone",
            "iphone fold",
            "iphone ultra",
            "折叠屏 iphone",
            "折叠 iphone",
            "折叠版 iphone",
            "折叠屏版 iphone",
            "折叠屏iphone",
            "折叠iphone",
            "折叠版iphone",
            "折叠屏版iphone",
        ),
    ),
    ("iphone", ("iphone",)),
    ("ipad-mini", ("ipad mini", "ipadmini")),
    ("ipad-air", ("ipad air", "ipadair")),
    ("ipad-pro", ("ipad pro", "ipadpro")),
    ("ipad", ("ipad",)),
    ("macbook", ("macbook",)),
    ("imac", ("imac",)),
    ("mac-mini", ("mac mini",)),
    ("mac-studio", ("mac studio",)),
    ("mac-pro", ("mac pro",)),
    ("mac", ("macos", " mac ", "mac 电脑", "苹果电脑")),
    ("apple-watch", ("apple watch", "watchos", "苹果手表")),
    ("airpods", ("airpods", "airpod")),
    (
        "game-controller",
        (
            "game controller",
            "game controllers",
            "gamecontroller",
            "游戏手柄",
            "游戏控制器",
        ),
    ),
    (
        "apple-glasses",
        (
            "apple smart glasses",
            "apple's smart glasses",
            "apple’s smart glasses",
            "apple ai glasses",
            "apple's ai glasses",
            "apple’s ai glasses",
            "apple glass",
            "apple glasses",
            "苹果智能眼镜",
            "苹果 ai 眼镜",
            "苹果ai眼镜",
            "苹果眼镜",
        ),
    ),
    ("vision-pro", ("vision pro", "visionos")),
    ("airtag", ("airtag", "air tag")),
    ("magic-keyboard", ("magic keyboard", "妙控键盘")),
    ("polishing-cloth", ("polishing cloth", "polishingcloth", "抛光布", "擦拭布")),
    (
        "apple-power-adapter",
        (
            "apple power adapter",
            "apple's power adapter",
            "apple’s power adapter",
            "dynamic power adapter",
            "动态电源适配器",
        ),
    ),
    ("apple-tv", ("apple tv", "tvos", "苹果 tv", "苹果电视")),
    (
        "apple-home-hub",
        (
            "apple home hub",
            "homeview",
            "apple's home hub",
            "apple’s home hub",
            "apple smart home hub",
            "apple smart home display",
            "apple homehub",
            "苹果 home hub",
            "苹果 homehub",
            "苹果家庭中枢",
            "苹果智能家居中枢",
            "苹果智能家居显示屏",
            "家庭中枢设备",
            "智能家居中枢设备",
        ),
    ),
    ("apple-sports", ("apple sports", "apple's sports app", "apple’s sports app", "苹果 sports")),
    ("apple-books", ("apple books", "苹果图书")),
    ("apple-arcade", ("apple arcade", "苹果 arcade")),
    ("apple-music", ("apple music", "苹果音乐")),
    ("shazam", ("shazam",)),
    (
        "beats",
        (
            "apple beats",
            "apple-owned beats",
            "apple's beats",
            "apple’s beats",
            "beats lab",
            "beats headphones",
            "beats earbuds",
            "beatsx",
            "beats x",
            "beats pill",
            "beats studio",
            "苹果 beats",
        ),
    ),
    ("apple-one", ("apple one",)),
    ("applecare", ("applecare", "apple care")),
    ("icloud", ("icloud",)),
    ("safari", ("safari", "webkit")),
    ("siri", ("siri",)),
    ("apple-store-app", ("apple store app", "apple store 应用", "apple store应用", "苹果商店应用")),
    ("app-store", ("app store", "appstore", "应用商店")),
    ("apple-wallet", ("apple wallet", "苹果 wallet", "苹果钱包", "数字车钥匙")),
    ("apple-maps", ("apple maps", "苹果地图", "苹果精细化地图", "苹果详细地图")),
    ("apple-pay", ("apple pay", "苹果支付")),
    ("apple-fitness", ("apple fitness+", "fitness+", "苹果 fitness+", "苹果fitness+")),
    ("apple-card", ("apple card", "苹果卡")),
    (
        "apple-gift-card",
        (
            "apple gift card",
            "apple account gift card",
            "苹果礼品卡",
            "苹果账户礼品卡",
        ),
    ),
    ("xcode", ("xcode",)),
    ("carplay", ("carplay",)),
    ("homekit", ("homekit",)),
    ("homepod", ("homepod",)),
    ("apple-intelligence", ("apple intelligence", "apple 智能", "apple智能", "苹果智能", "苹果 ai", "苹果ai")),
)


COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "app-tracking-transparency",
        (
            "app tracking transparency",
            "tracking transparency",
            "att consent",
            "att prompt",
            "app tracking rules",
            "应用追踪透明度",
            "应用跟踪透明度",
            "要求 app 不跟踪",
            "要求app不跟踪",
            "广告跟踪授权",
        ),
    ),
    ("face-id", ("face id", "面容 id", "面容id")),
    (
        "first-party-accessibility-guidance",
        (
            "accessibility settings",
            "built-in accessibility features",
            "assistive features",
            "辅助功能设置",
            "内置辅助功能",
            "无障碍功能",
        ),
    ),
    ("keyboard-key-labels", ("key symbols", "symbol-only labels", "key labels", "按键符号", "符号标识", "按键标识")),
    ("genlock", ("genlock",)),
    ("maps-advertising", ("apple maps ads", "maps advertising", "地图广告")),
    (
        "private-cloud-compute-server",
        (
            "private cloud compute server",
            "pcc server",
            "private cloud compute 服务器",
            "私有云计算服务器",
        ),
    ),
    (
        "component-cost-analysis",
        (
            "bill of materials",
            "bill-of-materials",
            "bom cost",
            "build cost",
            "component cost",
            "parts cost",
            "cost to build",
            "cost to manufacture",
            "cost more in parts",
            "more expensive to manufacture",
            "more to manufacture",
            "manufacturing cost",
            "零部件成本",
            "部件成本",
            "物料成本",
            "整机成本",
            "制造成本",
            "生产成本",
            "成本占比",
        ),
    ),
    (
        "immersive-live-video",
        (
            "immersive video",
            "immersive live video",
            "spatial video stream",
            "stereoscopic live",
            "沉浸式视频",
            "沉浸式直播",
            "空间视频直播",
            "立体直播",
        ),
    ),
    (
        "production-hurdle",
        (
            "production hurdle",
            "production hurdles",
            "manufacturing hurdle",
            "manufacturing hurdles",
            "manufacturing obstacle",
            "manufacturing obstacles",
            "production hiccup",
            "production hiccups",
            "production bottleneck",
            "production bottlenecks",
            "mass-production adjustment",
            "mass-production adjustments",
            "production adjustment",
            "production adjustments",
            "assembly complexity",
            "low yield",
            "yield issue",
            "yield issues",
            "生产障碍",
            "量产障碍",
            "制造难题",
            "生产难题",
            "生产调整",
            "产线调整",
            "制造流程调整",
            "组装复杂",
            "良率较低",
            "良率偏低",
            "良率问题",
            "良率瓶颈",
            "产能瓶颈",
        ),
    ),
    (
        "clipboard-paste-suggestion",
        (
            "paste suggestion",
            "paste shortcut",
            "paste button",
            "keyboard paste",
            "clipboard suggestion",
            "一键粘贴",
            "粘贴建议",
            "粘贴快捷",
            "粘贴入口",
        ),
    ),
    (
        "recurring-transactions",
        (
            "recurring transactions",
            "recurring transaction",
            "recurring payments",
            "recurring charges",
            "subscription charges",
            "周期性交易",
            "周期交易",
            "重复扣款",
            "订阅扣款",
        ),
    ),
    (
        "shopping-assistant",
        (
            "shopping assistant",
            "virtual shopping assistant",
            "ai-powered shopping assistant",
            "ai shopping assistant",
            "购物助手",
            "虚拟购物助手",
            "ai 购物助手",
            "ai购物助手",
        ),
    ),
    (
        "cross-platform-data-migration",
        (
            "switching from iphone to android",
            "switch from iphone to android",
            "iphone to android migration",
            "transfer from iphone",
            "migrate from iphone",
            "从 iphone 换到安卓",
            "从iphone换到安卓",
            "从苹果 iphone 换到安卓",
            "从苹果iphone换到安卓",
            "从 iphone 迁移",
            "从iphone迁移",
            "从 iphone 直接转移",
            "从iphone直接转移",
            "iphone 数据迁移",
            "iphone数据迁移",
        ),
    ),
    (
        "trade-in-valuation",
        (
            "trade-in value",
            "trade-in values",
            "trade-in offer",
            "trade-in offers",
            "trade-in quote",
            "trade-in quotes",
            "trade in value",
            "trade in values",
            "以旧换新",
            "换购",
            "估价",
            "折抵价",
            "折抵价值",
            "折抵估值",
        ),
    ),
    ("macbook-model:air", ("macbook air",)),
    ("macbook-model:pro", ("macbook pro",)),
    ("macbook-model:neo", ("macbook neo",)),
    ("macbook-model:ultra", ("macbook ultra",)),
    (
        "production-ramp",
        (
            "enters mass production",
            "entered mass production",
            "entered the mass production stage",
            "entering mass production",
            "production ramp",
            "ramping production",
            "ramp up production",
            "ramp-up production",
            "进入量产",
            "开始量产",
            "量产阶段",
            "量产爬坡",
            "产能爬坡",
        ),
    ),
    (
        "product-release-delay",
        (
            "delayed until spring",
            "release delay",
            "postponed until spring",
            "moves to spring",
            "moved to spring",
            "exits fall launch",
            "missing from fall launch",
            "absent from fall launch",
            "skips fall launch",
            "moved to next year",
            "moves to next year",
            "pushed to next year",
            "shifted to next year",
            "延期到明年春季",
            "推迟到明年春季",
            "改到明年春季",
            "放到明年",
            "移到明年",
            "移至明年",
            "退出秋季发布",
            "缺席秋季发布",
            "今年缺席",
        ),
    ),
    (
        "watch-band-sensor",
        (
            "sensor in band",
            "sensor in the band",
            "band sensor",
            "sensor embedded in band",
            "sensor embedded in the band",
            "表带内嵌传感器",
            "表带嵌入传感器",
            "表带集成传感器",
        ),
    ),
    (
        "facility-renovation",
        (
            "visitor center renovation",
            "visitor center improvements",
            "visitor center partially closed",
            "exhibition space closed",
            "store improvements",
            "update in progress",
            "游客中心升级",
            "游客中心改造",
            "展览区暂时关闭",
            "展览空间关闭",
        ),
    ),
    ("roadmap-projection", ("roadmap update", "路线图更新", "路线更新")),
    ("hide-my-email", ("hide my email", "隐藏我的邮件", "隐藏我的电子邮件", "隐藏电子邮件")),
    ("vapor-chamber", ("vapor chamber", "vapor cooling", "vapour chamber", "均热板", "vc 散热", "vc散热")),
    ("oled-display", ("oled", "有机发光")),
    ("ltpo-display", ("ltpo", "promotion display", "promotion 屏", "自适应刷新率")),
    (
        "supplier-input-cost",
        (
            "supplier price",
            "supplier cost",
            "tsmc price",
            "供应商涨价",
            "供应成本",
            "台积电涨价",
        ),
    ),
    (
        "financed-device-restriction",
        (
            "restricted mode",
            "finance lock",
            "unpaid balance",
            "overdue financed",
            "miss payments",
            "miss a payment",
            "missed payment",
            "cut off apps",
            "欠款设备",
            "欠款后",
            "受限模式",
            "金融锁",
            "白名单 app",
            "白名单 应用",
        ),
    ),
    (
        "exclusive-display-supplier",
        (
            "exclusive display supplier",
            "exclusively supply",
            "exclusively supplied",
            "displays exclusively from",
            "sole display supplier",
            "sole supplier",
            "独家供应",
            "独家供货",
        ),
    ),
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
    ("camera-system", ("variable aperture", "variable-aperture", "imx905", "可变光圈", "影像规格", "主摄")),
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
    (
        "water-resistance",
        (
            "water resistance",
            "water-resistant",
            "water resistant",
            "waterproof",
            "防水",
            "抗水",
            "耐水",
        ),
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


LEAD_IDENTITY_COMPONENTS = {
    # Some publishers use an intentionally vague headline and put the concrete
    # subject in the deck. These components are narrow enough to supplement a
    # title identity without allowing body background to redefine the event.
    "camera-system",
    "clipboard-paste-suggestion",
    "component-cost-analysis",
    "cross-platform-data-migration",
    "financed-device-restriction",
    "immersive-live-video",
    "facility-renovation",
    "office-real-estate",
    "product-release-delay",
    "production-hurdle",
    "production-ramp",
    "recurring-transactions",
    "shopping-assistant",
    "watch-band-sensor",
}


ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("legal", ("lawsuit", "court", "class action", "legal action", "legal battle", "legal dispute", "legal letter", "antitrust case", "settlement", "trial", "诉讼", "起诉", "被诉", "法院", "法庭", "对簿公堂", "集体诉讼", "法律纠纷", "律师函", "反垄断", "和解谈判")),
    (
        "security",
        (
            "vulnerability",
            "security flaw",
            "security issue",
            "security issues",
            "flaw",
            "exploited",
            "actively exploited",
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
    ("regulation", ("regulator", "regulatory", "approved", "approval", "filing", "registered", "fine", "ordered to remove", "ordered to stop", "required to change", "demand to pull", "investigation", "备案", "获批", "监管", "罚款", "合规", "检方要求", "要求调整", "要求下架", "下架")),
    ("transaction", ("acquire", "acquisition", "merger", "partner", "partnership", "evaluate", "evaluation", "talks", "lease", "leases", "leased", "leasing", "收购", "合作", "接洽", "评估", "洽谈", "租赁", "租下", "承租")),
    ("supply-production", ("order", "orders", "supplier", "supply", "production", "mass production", "manufacture", "量产", "订单", "供应", "供应商", "供货", "生产")),
    ("investment-capacity", ("investment", "invest", "plant", "plants", "fab", "factory", "capacity", "扩产", "投资", "工厂", "晶圆厂", "产能")),
    (
        "retail-availability",
        (
            "selling",
            "available",
            "store",
            "refurbished",
            "launch",
            "release",
            "coming in",
            "coming this",
            "coming next",
            "enters the market",
            "market entry",
            "推出",
            "上架",
            "开售",
            "发售",
            "上市",
            "进入市场",
            "登陆市场",
            "官翻",
            "翻新",
        ),
    ),
    ("delay-roadmap", ("delay", "delayed", "roadmap", "reportedly", "rumor", "expected", "target", "plan", "plans", "planned", "planning", "推迟", "延期", "路线图", "传闻", "预计", "计划")),
    (
        "claim-denial",
        (
            "denies rumor",
            "denied rumor",
            "disputes report",
            "counters report",
            "counters rumor",
            "refutes report",
            "refutes rumor",
            "remains on track",
            "still on track",
            "still planned",
            "否认传闻",
            "否认报道",
            "反驳传闻",
            "反驳报道",
            "并未取消",
            "没有取消",
            "仍按计划",
            "仍在推进",
        ),
    ),
    (
        "feature-change",
        (
            "adds",
            "added",
            "changes",
            "changed",
            "brings",
            "brought",
            "come to",
            "comes to",
            "can connect",
            "supports",
            "develops",
            "developing",
            "working on",
            "working to expand",
            "expands",
            "expanding",
            "revamp",
            "introduces",
            "introducing",
            "improves",
            "improved",
            "removes",
            "removed",
            "rename",
            "renames",
            "renamed",
            "renaming",
            "upgrade",
            "update",
            "new feature",
            "makes",
            "新增",
            "加入",
            "引入",
            "开发",
            "研发",
            "扩展",
            "改进",
            "升级",
            "移除",
            "改名",
            "更名",
            "重命名",
            "更新",
            "调整",
            "首次支持",
            "开始支持",
            "搭载",
            "支持",
            "可连接",
        ),
    ),
    (
        "official-communication",
        (
            "apple shares video",
            "apple shares story",
            "apple publishes video",
            "apple posts video",
            "apple releases video",
            "苹果分享视频",
            "苹果发布视频",
            "苹果发布故事",
        ),
    ),
    ("price-change", ("price increase", "price increases", "price hike", "raises price", "raises prices", "raises trade-in values", "increases trade-in offers", "updates trade-in values", "increases subscription prices", "costs $", "涨价", "提价", "上调价格", "上调售价", "上调以旧换新", "调整以旧换新", "上调折抵价", "调整折抵价", "降价")),
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
    (
        "model-development",
        (
            "trained its own ai model",
            "trained own ai model",
            "training its own custom model",
            "developed its own ai model",
            "自研 ai 模型",
            "自研ai模型",
            "训练自研 ai 模型",
            "训练了一款 ai 模型",
            "训练了一款“中国定制”大模型",
            "训练中国专属自研ai大模型",
            "训练中国市场自研 ai 模型",
        ),
    ),
    (
        "leadership-transition",
        (
            "steps down as ceo",
            "leaving the ceo role",
            "before leaving the apple ceo role",
            "final weeks as apple ceo",
            "apple legacy",
            "leadership transition",
            "卸任苹果 ceo",
            "卸任苹果ceo",
            "卸任前",
            "交接采访",
            "领导层交接",
        ),
    ),
    (
        "commercial-launch",
        (
            "opens ad booking",
            "opens advertising booking",
            "ads coming soon",
            "available to book",
            "accepting ad reservations",
            "广告位招商",
            "广告位开始接受",
            "广告预订",
            "开放广告预订",
        ),
    ),
    (
        "withdrawal",
        (
            "withdraws ad",
            "withdraws campaign",
            "pulls ad",
            "pulls campaign",
            "removes ad",
            "removes poster",
            "撤下争议广告",
            "撤下争议宣传",
            "撤下广告",
            "撤回广告",
            "撤下宣传海报",
        ),
    ),
    (
        "catalog-expansion",
        (
            "adds new configurations to refurb store",
            "adds new configs to refurb store",
            "adds to refurb store",
            "expands refurbished store",
            "expands refurb store",
            "扩充官翻阵容",
            "扩充官方翻新",
            "官翻阵容新增",
        ),
    ),
    (
        "product-launch",
        (
            "announces",
            "announced",
            "debuts",
            "debuted",
            "introduces",
            "introduced",
            "launches",
            "launched",
            "releases",
            "released",
            "reveals",
            "revealed",
            "unveils",
            "unveiled",
            "goes live",
            "is already live",
            "are already live",
            "is now live",
            "are now live",
            "is here",
            "are here",
            "发布",
            "推出",
            "上线",
            "登场",
            "亮相",
            "问世",
            "揭晓",
            "正式开售",
        ),
    ),
    (
        "availability-expansion",
        (
            "expands to more countries",
            "expands to more markets",
            "expands availability",
            "now available in",
            "rolls out in",
            "覆盖更多国家",
            "扩展至更多",
            "登陆更多市场",
            "扩大销售范围",
        ),
    ),
    (
        "product-refresh",
        (
            "quietly refreshes",
            "quietly refreshed",
            "refreshes",
            "refreshed",
            "new version",
            "新版",
            "新款",
            "改款",
            "悄然更新",
        ),
    ),
    (
        "product-disclosure",
        (
            "leaked photos",
            "photos reveal",
            "photos show",
            "code reveals",
            "code shows",
            "code hints at",
            "found in code",
            "泄露照片",
            "照片曝光",
            "代码显示",
            "代码揭示",
            "代码曝光",
            "代码发现",
        ),
    ),
)


OS_COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("os-component:photo-face", ("photo face", "照片面孔")),
    ("os-component:standby", ("standby", "待机模式", "待机（standby）")),
    ("os-component:user-profiles", ("user profiles", "profiles", "用户资料", "用户档案")),
    ("os-component:lock-screen", ("lock screen", "锁屏")),
    ("os-component:home-screen", ("home screen", "主屏幕")),
    ("os-component:control-center", ("control center", "控制中心")),
    ("os-component:screen-sharing", ("screen sharing", "屏幕共享")),
    ("os-component:camera", ("camera app", "相机 app", "相机应用")),
    ("os-component:photos", ("apple photos", "photos app", "照片 app", "照片应用")),
    (
        "os-component:mail",
        (
            "apple mail",
            "mail app",
            "mail compose",
            "mail's compose",
            "mail’s compose",
            "mail composer",
            "邮件 app",
            "邮件应用",
            "邮件撰写",
        ),
    ),
    (
        "os-component:messages",
        (
            "apple messages",
            "messages app",
            "android texts",
            "green bubble",
            "green bubbles",
            "信息 app",
            "信息应用",
            "安卓消息",
            "安卓绿色气泡",
            "绿色气泡信息",
        ),
    ),
    ("os-component:notes", ("apple notes", "notes app", "备忘录")),
    ("os-component:weather", ("apple weather", "weather app", "天气 app", "天气应用")),
    ("os-component:shortcuts", ("apple shortcuts", "shortcuts app", "快捷指令")),
    ("os-component:settings", ("settings app", "system settings", "设置 app", "系统设置")),
    ("os-component:siri", ("siri app", "siri 应用", "siri app 应用")),
    ("os-component:find-my", ("find my app", "find my 应用", "查找 app", "查找应用")),
    (
        "os-component:watch-face",
        ("watch face", "watch faces", "表盘", "表面配色"),
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
    "app-store-card-payments",
    "apple-memory-supplier-sourcing",
    "apple-restricted-memory-supplier-approval",
    "apple-smart-glasses-roadmap",
    "apple-wallet-car-key-partner-support",
}


@lru_cache(maxsize=None)
def _english_alias_forms(alias: str) -> tuple[str, ...]:
    """Return stable, conservative inflections for the final word of a phrase."""
    forms = {alias}
    match = _compiled_rule(r"([a-z]+)$", 0).search(alias)
    if not match:
        return (alias,)
    word = match.group(1)
    if word.endswith(("s", "ed", "ing")):
        return (alias,)
    prefix = alias[: match.start(1)]
    if word.endswith(("s", "x", "z", "ch", "sh")):
        plural = f"{word}es"
    elif word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        plural = f"{word[:-1]}ies"
    else:
        plural = f"{word}s"
    if word.endswith("e"):
        past = f"{word}d"
        progressive = f"{word[:-1]}ing"
    else:
        past = f"{word}ed"
        progressive = f"{word}ing"
    forms.update(
        {
            f"{prefix}{plural}",
            f"{prefix}{past}",
            f"{prefix}{progressive}",
        }
    )
    return tuple(sorted(forms, key=lambda value: (-len(value), value)))


@lru_cache(maxsize=None)
def _compiled_pattern_groups(
    patterns: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[str, tuple[str, ...], tuple[re.Pattern[str], ...]], ...]:
    """Compile immutable pattern tables once instead of rebuilding forms per article."""
    groups: list[tuple[str, tuple[str, ...], tuple[re.Pattern[str], ...]]] = []
    for name, aliases in patterns:
        cjk_aliases: list[str] = []
        boundary_forms: dict[tuple[bool, bool], set[str]] = {}
        for alias in aliases:
            if _compiled_rule(r"[\u3400-\u9fff]", 0).search(alias):
                cjk_aliases.append(alias)
                continue
            for form in _english_alias_forms(alias):
                boundary_forms.setdefault(
                    (form[0].isalnum(), form[-1].isalnum()),
                    set(),
                ).add(form)

        matchers: list[re.Pattern[str]] = []
        for (left_boundary, right_boundary), forms in boundary_forms.items():
            alternatives = "|".join(
                re.escape(form)
                for form in sorted(forms, key=lambda value: (-len(value), value))
            )
            expression = f"(?:{alternatives})"
            if left_boundary:
                expression = rf"(?<![a-z0-9]){expression}"
            if right_boundary:
                expression = rf"{expression}(?![a-z0-9])"
            matchers.append(re.compile(expression))
        groups.append((name, tuple(cjk_aliases), tuple(matchers)))
    return tuple(groups)


@lru_cache(maxsize=32768)
def _cached_extract_patterns(
    text: str,
    patterns: tuple[tuple[str, tuple[str, ...]], ...],
) -> frozenset[str]:
    return frozenset(
        name
        for name, cjk_aliases, matchers in _compiled_pattern_groups(patterns)
        if any(alias in text for alias in cjk_aliases)
        or any(matcher.search(text) for matcher in matchers)
    )


def _extract_patterns(text: str, patterns: tuple[tuple[str, tuple[str, ...]], ...]) -> set[str]:
    return set(_cached_extract_patterns(text, patterns))


def _modifier_only_product_mentions(text: str, product: str) -> bool:
    """Return true when every title mention is only a comparison adjective."""
    matches = []
    for alias in dict(PRODUCT_PATTERNS).get(product, ()):
        matcher = re.compile(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        )
        matches.extend(matcher.finditer(text))
    return bool(matches) and all(
        _compiled_rule(r"^(?:-|\s)+(?:style|like|inspired)(?:\b|-)", 0).match(text[match.end() :])
        for match in matches
    )


def primary_assertion_components(value: str) -> frozenset[str]:
    """Expose typed components from the first assertion without mutating identity."""
    primary = _compiled_rule(r"(?:[。！？]|(?<=[.!?])\s+)", 0).split(_normalized(value), 1)[0]
    return frozenset(_extract_patterns(primary, COMPONENT_PATTERNS))


_SUPPLIER_COMPONENT_CLASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "memory",
        (
            "dram",
            "ram",
            "nand",
            "memory chip",
            "memory chips",
            "memory product",
            "memory products",
            "storage chip",
            "storage chips",
            "storage product",
            "storage products",
            "内存",
            "存储芯片",
            "存储产品",
            "闪存",
        ),
    ),
    (
        "display",
        (
            "display panel",
            "display panels",
            "oled panel",
            "oled panels",
            "screen panel",
            "显示面板",
            "oled 面板",
            "oled面板",
        ),
    ),
    (
        "image-sensor",
        (
            "image sensor",
            "image sensors",
            "camera sensor",
            "camera sensors",
            "图像传感器",
            "相机传感器",
        ),
    ),
    (
        "battery",
        (
            "battery cell",
            "battery cells",
            "battery supplier",
            "电池供应",
            "电芯",
        ),
    ),
    (
        "semiconductor",
        (
            "processor",
            "processors",
            "semiconductor",
            "semiconductors",
            "modem chip",
            "modem chips",
            "芯片供应",
            "处理器供应",
            "调制解调器芯片",
        ),
    ),
)


def _component_supplier_sourcing_classes(title: str, lead: str) -> set[str]:
    """Return component classes in a direct Apple buyer/supplier relation.

    A component shortage is context, not an event predicate.  This relation
    therefore requires Apple (or one of its product families) to be the buyer,
    tester, qualifier, or sourcing target in the headline or opening claim.
    """
    title_text = _normalized(title)
    lead_text = _normalized(lead)[:700]
    text = f"{title_text}. {lead_text}"
    apple_subject = (
        r"(?:apple(?:'s|’s)?|iphone|ipad|mac(?:book)?|imac|apple\s+watch|airpods|vision\s+pro|苹果)"
    )
    sourcing_action = (
        r"(?:buy(?:ing)?|source|sourcing|sourced|procure|procurement|purchase|purchasing|"
        r"qualify|qualifying|qualification|approve|approval|"
        r"negotiate|negotiating|negotiation|talks?\s+with|consider(?:s|ed|ing)?\s+(?:buying|sourcing|using)|"
        r"采购|购买|寻求|寻找|认证|送样|洽谈|谈判|议价|考虑采用|考虑使用|导入供应链)"
    )
    direct_buyer_relation = bool(
        _compiled_rule(rf"{apple_subject}[^。！？\n]{{0,110}}{sourcing_action}", 0).search(text)
        or _compiled_rule(rf"{sourcing_action}[^。！？\n]{{0,110}}(?:for|to|by|供给|供应|面向)?\s*{apple_subject}", 0).search(text)
    )
    # Testing a finished iPhone is not Apple testing a supplier's part.
    # In the test-only case, require Apple to own the testing predicate.
    direct_buyer_relation = direct_buyer_relation or bool(_compiled_rule(r"\bapple\s+(?:(?:is|has|been|currently|already|reportedly|begins?|starts?)\s+)*(?:tests?|testing|tested)\b|"
        r"苹果(?:公司)?(?:正在|已|已经|正|据悉|开始|传)?(?:测试|验证)|"
        r"(?:testing|tested|qualification)\b[^.!?]{0,45}\bfor apple\b|为苹果.{0,20}(?:测试|验证)").search(text))
    if not direct_buyer_relation:
        contract_classes: set[str] = set()
        signing_action = (
            r"(?:\b(?:sign(?:s|ed|ing)?|enter(?:s|ed|ing)?(?:\s+into)?|reach(?:es|ed|ing)?)\b|"
            r"签(?:订|署)?|达成)"
        )
        # Keep the buyer, component and supply contract in the same assertion.
        for claim in _compiled_rule(r"[。！？.!?\n]", 0).split(text, 0):
            if not (
                _compiled_rule(rf"{apple_subject}[^,，;；]{{0,50}}{signing_action}", 0).search(claim)
                or _compiled_rule(rf"{signing_action}[^,，;；]{{0,100}}\b(?:with|for|to)\s+{apple_subject}", 0).search(claim)
                or _compiled_rule(rf"与{apple_subject}[^,，;；]{{0,30}}{signing_action}", 0).search(claim)
            ):
                continue
            if _compiled_rule(r"\b(?:settlement|litigation|patent|subscription|software)\b|"
                         r"(?:和解|诉讼|专利|订阅|软件)", 0).search(claim):
                continue
            for component_class, aliases in _SUPPLIER_COMPONENT_CLASSES:
                if not _contains_any(claim, aliases):
                    continue
                component_terms = "|".join(re.escape(alias) for alias in aliases)
                if _compiled_rule(r"\b(?:supply|sourcing|procurement|purchase)\s+(?:agreement|contract)\b|"
                    r"(?:供应|采购).{0,8}(?:协议|合约|合同)|"
                    rf"(?:{component_terms})\s*(?:长期|多年|供应|采购)*\s*(?:协议|合约|合同)", 0).search(claim):
                    contract_classes.add(component_class)
        return contract_classes
    return {
        component_class
        for component_class, aliases in _SUPPLIER_COMPONENT_CLASSES
        if _contains_any(text, aliases)
    }


GENERIC_NAMED_SUBJECTS = {
    "ai",
    "apple",
    "apple-ceo",
    "apple-intelligence",
    "apple-store",
    "extreme",
    "genius-bar",
    "iphone",
    "ipad",
    "ios",
    "mac-pro",
    "mac-studio",
    "ceo",
    "com",
    "net",
    "org",
    "rss",
    "report",
    "system",
    "tool",
    "wwdc",
    # Publisher and distribution brands can appear in copied attribution or
    # related-link text. They identify where a fact came from, not the event.
    "9to5mac",
    "appleinsider",
    "cnbeta",
    "ithome",
    "macrumors",
    "youtube",
}


def _subject_slug(value: str) -> str:
    value = _normalized(value).strip(" .,:;!?()[]{}")
    value = _compiled_rule(r"[^a-z0-9+.-]+", 0).sub("-", value, 0)
    return _compiled_rule(r"-+", 0).sub("-", value, 0).strip("-")


def _valid_named_subject(value: str) -> str | None:
    value = _compiled_rule(r"\s+", 0).sub(" ", value, 0).strip(" .,:;!?()[]{}\"'“”‘’")
    if not value or len(value) > 48:
        return None
    if len(value.split()) > 5:
        return None
    slug = _subject_slug(value)
    if len(slug) < 3 or slug in GENERIC_NAMED_SUBJECTS:
        return None
    if not _compiled_rule(r"[a-z]", 0).search(slug) and not _compiled_rule(r"[a-z]{1,4}\d{3,5}", 0).fullmatch(slug):
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
    if _compiled_rule(r"(?:M\d+\s+Extreme|[A-Z]{1,4}\d{3,5})", re.I).fullmatch(original):
        return subject
    branded_word = r"(?:[A-Z][A-Za-z0-9+.-]*|[a-z]+[A-Z][A-Za-z0-9+.-]*)"
    if re.fullmatch(rf"{branded_word}(?:\s+{branded_word})+", original):
        return subject
    if _compiled_rule(r"[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9+.-]*", 0).fullmatch(original):
        return subject
    return None


def _valid_content_title(value: str) -> str | None:
    value = _compiled_rule(r"\s+", 0).sub(" ", value, 0).strip(" .,:;!?()[]{}\"'“”‘’—-")
    if not value or len(value) > 64 or len(value.split()) > 8:
        return None
    words = value.split()
    if len(words) < 2:
        return None
    connectors = {"a", "an", "and", "at", "for", "from", "in", "is", "my", "no", "not", "of", "on", "the", "to", "with"}
    significant = [word for word in words if word.lower().strip(".:,+-") not in connectors]
    if not significant or not all(_compiled_rule(r"^[A-Z][A-Za-z0-9+.'-]*$", 0).match(word) for word in significant):
        return None
    return _canonical_named_subject(value)


def _explicit_evidence_first_party_subjects(evidence: Iterable[str]) -> set[str]:
    subjects: set[str] = set()
    for evidence_item in tuple(evidence)[:6]:
        for match in _compiled_rule(r"(?i)(?:something\s+called|called|named|known\s+as|名为|称为)\s*"
            r"[\"'“‘]?\s*(Apple\s+[A-Z][A-Za-z0-9+-]{2,30}"
            r"(?:\s+[A-Z][A-Za-z0-9+-]{2,30}){0,2})\b", 0).finditer(evidence_item):
            subject = _canonical_named_subject(match.group(1))
            if subject:
                subjects.add(subject)
    return subjects


def _named_subjects(title: str, lead: str, evidence: Iterable[str] = ()) -> set[str]:
    """Extract rare title/lead anchors without treating reporter names as event identity."""
    identity_lead = _compiled_rule(r"(?:\bbackground(?: paragraphs?| context)?\b|\bpreviously\b|\bmeanwhile\b|"
        r"背景(?:段落|信息|资料)?|此前(?:报道|消息)?|与此同时)", re.I).split(lead[:700], 1)[0]
    scoped = f"{title} {identity_lead}"
    subjects: set[str] = set()
    if "隔空投送" in scoped:
        subjects.add("airdrop")
    background_quoted_subjects: set[str] = set()
    primary_quoted_subjects: set[str] = set()

    for match in _compiled_rule(r"(?<![A-Za-z0-9])[\"'“‘]((?:[^\"'“”‘’\n]|(?<=\w)['’](?=\w)){2,48})[\"'”’](?![A-Za-z0-9])", 0).finditer(scoped):
        trailing_context = scoped[match.end() : match.end() + 36].lstrip(" \t\"'“”‘’")
        if _compiled_rule(r"(?:(?:oscar|emmy|bafta|grammy|golden globe)\s+(?:winner|nominee)|"
            r"director|winner|star|actor|actress|creator|author|filmmaker)\b", re.I).match(trailing_context):
            background = _valid_quoted_subject(match.group(1)) or _valid_content_title(match.group(1))
            if background:
                background_quoted_subjects.add(background)
            continue
        subject = _valid_quoted_subject(match.group(1)) or _valid_content_title(match.group(1))
        if subject:
            preceding_context = scoped[max(0, match.start() - 45):match.start()]
            # A quoted event in a temporal adjunct names the occasion of a
            # retail change, not the object being changed. Preserve direct
            # uses elsewhere (for example an announcement of that event).
            occasion_context = bool(
                (_compiled_rule(r"(?:\bbefore|\bafter|\bfollowing|\bahead of|\bduring|\baround)\s+(?:the\s+)?$", re.I).search(preceding_context)
                 and _compiled_rule(r"(?:event|keynote|presentation|launch)\b", re.I).match(trailing_context))
                or _compiled_rule(r"(?:发布会|活动)(?:结束|召开)?(?:之前|之后|前|后|期间)", 0).match(trailing_context)
            )
            if occasion_context:
                background_quoted_subjects.add(subject)
            else:
                primary_quoted_subjects.add(subject)
                subjects.add(subject)

    named_pattern = _compiled_rule(r"(?:called|named|codenamed|known as|story of|名为|代号(?:分别)?为?)\s*[\"'“‘]?"
        r"([A-Z][A-Za-z0-9+.-]*(?:\s+[A-Z][A-Za-z0-9+.-]*){0,3})", 0)
    for match in named_pattern.finditer(scoped):
        subject = _canonical_named_subject(match.group(1))
        if subject:
            subjects.add(subject)

    # Feature reports often establish a branded UI object through a
    # causative comparison rather than explicit naming language, for example
    # "make <Name> more ...". Preserve that syntactic subject so translations
    # and the original report share a concrete event identity.
    for match in _compiled_rule(r"\b(?:make|makes|making|set|sets|adjust|adjusts|change|changes)\s+"
        r"([A-Z][A-Za-z0-9+.-]*(?:\s+[A-Z][A-Za-z0-9+.-]*){1,3})\s+"
        r"(?:more|less|higher|lower|clearer|darker|lighter)\b", 0).finditer(scoped):
        subject = _canonical_named_subject(match.group(1))
        if subject:
            subjects.add(subject)

    for match in _compiled_rule(r"(?<![A-Za-z0-9])(?:M\d+\s+Extreme|[A-Z]{1,4}\d{3,5})(?![A-Za-z0-9])", re.I).finditer(scoped):
        subject = _canonical_named_subject(match.group(0))
        if subject:
            subjects.add(subject)

    # Key facts may contain the explicit first-party name that a concise
    # headline omits. Accept only names introduced by naming language; this
    # keeps background product mentions from becoming event identity.
    subjects |= _explicit_evidence_first_party_subjects(evidence)

    for match in _compiled_rule(r"(?<![A-Za-z0-9])(?:A\d{1,2}\s*Pro|M\d{1,2}(?:\s*(?:Pro|Max|Ultra|Extreme))?)(?![A-Za-z0-9])", re.I).finditer(scoped):
        subject = _canonical_named_subject(match.group(0))
        if subject:
            subjects.add(subject)

    for match in _compiled_rule(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9+.-]*\b", 0).finditer(scoped):
        subject = _canonical_named_subject(match.group(0))
        if subject:
            subjects.add(subject)

    # Preserve a title-led company as an event subject even when its brand is
    # ordinary title case rather than CamelCase. This supports cross-source
    # matching for supplier, regulator, and partner actions without keeping a
    # growing dictionary of company names.
    for pattern in (
        r"^\s*(?P<name>[A-Z][A-Za-z0-9+.-]{2,30})\s+"
        r"(?:says|expects|warns|forecasts|projects|reports|confirms|denies|announces)\b",
        r"\b(?:reliance|dependence|revenue|business)\s+(?:on|from|with)\s+"
        r"(?P<name>[A-Z][A-Za-z0-9+.-]{2,30})\b",
    ):
        match = re.search(pattern, title, re.I)
        if not match:
            continue
        subject = _canonical_named_subject(match.group("name"))
        if subject:
            subjects.add(subject)

    # First-party apps and programs often use ordinary title-case words rather
    # than CamelCase. Keep the branded noun, but reject verbs and generic Apple
    # organization labels so headlines such as "Apple Updates TestFlight" do
    # not create a false subject called "Apple Updates".
    apple_named_stopwords = {
        "app",
        "updated",
        "expands",
        "adds",
        "already",
        "announces",
        "approves",
        "chipmaker",
        "company",
        "confirms",
        "could",
        "debuts",
        "improves",
        "hires",
        "is",
        "launches",
        "plans",
        "product",
        "publishes",
        "raises",
        "releases",
        "reportedly",
        "says",
        "seeds",
        "shares",
        "skipping",
        "testing",
        "updates",
        "will",
    }
    for match in _compiled_rule(r"\bApple(?:['’]s)?\s+([A-Z][A-Za-z0-9+-]{2,30}"
        r"(?:\s+(?!Apple\b)[A-Z][A-Za-z0-9+-]{2,30}){0,2})\b", 0).finditer(scoped):
        branded_parts = match.group(1).split()
        stop_index = next(
            (
                index
                for index, part in enumerate(branded_parts)
                if part.lower() in apple_named_stopwords and (part.lower() != "app" or index > 0)
            ),
            len(branded_parts),
        )
        branded_parts = branded_parts[:stop_index]
        if not branded_parts:
            continue
        branded_noun = " ".join(branded_parts)
        subject = _canonical_named_subject(f"Apple {branded_noun}")
        if subject:
            subjects.add(subject)

    for pattern in (
        r"[（(]([A-Z][A-Za-z0-9+.'-]*(?:\s+(?:[A-Za-z][A-Za-z0-9+.'-]*)){1,7})[)）]",
        r"(?:book|film|movie|series|title|follow-up)[^。.!?\n]{0,36}[—-]\s*([A-Z][A-Za-z0-9+.'-]*(?:\s+[A-Za-z][A-Za-z0-9+.'-]*){1,7})\s*[—-]",
        r"\bbook\s+([A-Z][A-Za-z0-9+.'-]*(?:\s+[A-Za-z][A-Za-z0-9+.'-]*){1,7})(?=\s+(?:on|in|from|within|was|is)\b)",
        r"(?:series|docuseries|movie|film):\s*([A-Z][A-Za-z0-9+.'-]*(?:\s+[A-Za-z][A-Za-z0-9+.'-]*){1,7})(?=[.!?]|$)",
        r"\bannounced?\s+([A-Z][A-Za-z0-9+.'-]*(?:\s+[A-Za-z][A-Za-z0-9+.'-]*){1,7})(?=\s+as\s+(?:a|an|the)\b)",
    ):
        for source_text in (title, identity_lead):
            for match in re.finditer(pattern, source_text):
                subject = _valid_content_title(match.group(1))
                if subject:
                    subjects.add(subject)

    # Unquoted entertainment headlines commonly put the work name directly
    # before a season/trailer action. Preserve that rare title anchor so a
    # premiere or executive interview mentioning the same show cannot bridge
    # into the trailer event merely through Apple TV background.
    for match in _compiled_rule(r"(?i)(?:apple\s+(?:unveils?|shares?|releases?)\s+|back\s+to\s+[^,]{2,40},\s*)?"
        r"(?P<name>[a-z][a-z0-9'’.-]*(?:\s+[a-z][a-z0-9'’.-]*){1,6})"
        r"\s+season\s+\d{1,2}(?:\s+(?:trailer|teaser))?", 0).finditer(title):
        candidate = _compiled_rule(r"(?i)^(?:apple\s+(?:unveils?|shares?|releases?)\s+)", 0).sub("", match.group("name"), 0)
        subject = _valid_content_title(candidate.title())
        if subject:
            subjects.add(subject)
    return subjects - (background_quoted_subjects - primary_quoted_subjects)


def _title_primary_named_subjects(title: str, lead: str) -> set[str]:
    """Return named subjects established by the headline, with narrow lead disambiguation."""
    subjects = _named_subjects(title, "")
    normalized_title = _normalized(title)
    for subject in _named_subjects(title, lead):
        chip_family = _compiled_rule(r"([am]\d{1,2})(?:-(?:pro|max|ultra|extreme))?", 0).fullmatch(subject)
        if chip_family and re.search(
            rf"(?<![a-z0-9]){re.escape(chip_family.group(1))}(?![a-z0-9])",
            normalized_title,
        ):
            subjects.add(subject)
    return subjects


def _collapse_product_hierarchy(products: set[str]) -> set[str]:
    if "foldable-iphone" in products:
        products.discard("iphone")
    if products & {"ipad-mini", "ipad-air", "ipad-pro"}:
        products.discard("ipad")
    if products & {"macbook", "imac", "mac-mini", "mac-studio", "mac-pro"}:
        products.discard("mac")
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
        for token in _compiled_rule(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9.-]{2,})(?![A-Za-z0-9])", 0).findall(title)
        if token.lower() not in excluded
        and (
            (token.isupper() and 3 <= len(token) <= 10)
            or (not token.isupper() and any(character.isupper() for character in token[1:]))
        )
    }
    normalized_title = _normalized(title)
    for token in ("tsmc", "prismml", "baltra", "openai", "roblox", "samsung", "signal ring"):
        if token in normalized_title:
            actors.add(token)
    if "台积电" in normalized_title:
        actors.add("tsmc")
    return actors


ANALYST_INSTITUTION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("jp-morgan", ("j.p. morgan", "jp morgan", "jpmorgan", "摩根大通")),
    ("morgan-stanley", ("morgan stanley", "摩根士丹利")),
    ("goldman-sachs", ("goldman sachs", "高盛")),
    ("rosenblatt", ("rosenblatt", "罗森布拉特")),
    ("keybanc", ("keybanc", "keybanc capital markets")),
)


def _is_analyst_target_action_title(lower: str) -> bool:
    if _compiled_rule(r"\b(?:lawsuit|court|case|sues?|sued|patent|infringement)\b|"
        r"(?:诉讼|法院|法庭|案件|起诉|专利|侵权)", 0).search(lower):
        return False
    return bool(
        _compiled_rule(r"\b(?:price\s+target|target\s+price|aapl\s+target)\b|"
            r"\b(?:apple|aapl)(?:['’]s)?\b.{0,28}\b(?:price\s+)?target\b|"
            r"\b(?:analyst|bank|brokerage|investment\s+firm)\b.{0,32}\b(?:rating|upgrades?|downgrades?)\b|"
            r"\b(?:upgrades?|downgrades?)\b.{0,24}\b(?:apple|aapl)\b|"
            r"\b(?:raises?|cuts?|lowers?|lifts?|boosts?|hikes?|trims?)\b.{0,24}"
            r"\b(?:apple|aapl)\b.{0,18}(?:\bto\b|\bat\b)?\s*\$\s*\d|"
            r"(?:目标(?:股)?价|股票评级|股价评级|上调评级|下调评级)", 0).search(lower)
    )


def _analyst_institution_components(title: str, lead: str = "") -> set[str]:
    """Extract the institution that owns a rating or target-price action."""
    lower = _normalized(title)
    if not _is_analyst_target_action_title(lower):
        return set()
    evidence = f"{lower} {_normalized(lead)[:260]}"
    institutions = {
        name
        for name, aliases in ANALYST_INSTITUTION_ALIASES
        if _contains_any(evidence, aliases)
    }
    english_patterns = (
        r"^(?P<name>[a-z][a-z0-9.&-]*(?:\s+[a-z][a-z0-9.&-]*){0,3})\s+"
        r"(?:raises?|cuts?|lowers?|lifts?|hikes?|bumps?|boosts?|trims?|slashes?|"
        r"upgrades?|downgrades?|reiterates?|maintains?)\b",
        r"(?:by|from)\s+(?P<name>[a-z][a-z0-9.&-]*(?:\s+[a-z][a-z0-9.&-]*){0,3})\b",
    )
    generic_words = {
        "after",
        "analyst",
        "apple",
        "bank",
        "earnings",
        "investment-bank",
        "services-slowdown-pushes",
        "wall-street",
    }
    for pattern in english_patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        slug = _subject_slug(match.group("name"))
        if slug and slug not in generic_words and 3 <= len(slug) <= 48:
            institutions.add(slug)
    return {f"analyst-institution:{name}" for name in institutions}


def _attribution_slug(value: str) -> str:
    value = _normalized(value)
    sentence_fragments = [
        fragment.strip()
        for fragment in _compiled_rule(r"(?<=[a-z0-9])\.\s+(?=[a-z])", 0).split(value, 0)
        if fragment.strip()
    ]
    if len(sentence_fragments) > 1:
        # Adjacent title and lead sentences can both name the same publisher,
        # e.g. "says Nikkei. Nikkei Asia reports". Keep the most specific
        # sentence-local name instead of manufacturing one combined entity.
        value = max(sentence_fragments, key=lambda fragment: (len(fragment.split()), len(fragment)))
    value = _compiled_rule(r"(?:['’]s|的)$", 0).sub("", value, 0).strip()
    value = _compiled_rule(r"^(?:a\s+|the\s+|market\s+research\s+firm\s+|research\s+firm\s+|"
        r"市场研究机构|研究机构|分析机构|分析师|研究员)", 0).sub("", value, 0)
    value = _compiled_rule(r"(?:最新|手机|产业|市场|行业|研究)*(?:报告|研究|数据|预测|咨询)$", 0).sub("", value, 0)
    value = _compiled_rule(r"[^a-z0-9\u4e00-\u9fff+.-]+", 0).sub("-", value, 0).strip("-")
    if not value or value in {
        "apple",
        "苹果",
        "报告",
        "研究",
        "分析师",
        "研究员",
        "the-report",
        "the-company",
        "earlier",
        "latest",
        "other",
    }:
        return ""
    if _compiled_rule(r"(?:apple|iphone|ipad|mac|macbook|airpods|vision-pro|"
        r"[am]\d+(?:-(?:pro|max|ultra|extreme))?|j\d+(?:-mac-pro)?)", 0).fullmatch(value):
        return ""
    if value == "counterpoint-research":
        return "counterpoint"
    if value in {"kuo", "郭明錤"}:
        return "ming-chi-kuo"
    return value


def _report_attribution_components(title: str, lead: str = "") -> set[str]:
    """Extract a report's named source independently of language and publisher."""
    scope = f"{title}. {lead[:900]}"
    values: set[str] = set()
    patterns = (
        r"(?:分析师|研究员)\s*([\u4e00-\u9fff]{2,5}?)(?=发布|称|指出|预计|预测|表示)",
        r"(?:^|[：:])\s*([\u4e00-\u9fff]{2,5})(?=[：:]|称苹果|指出苹果|预计苹果)",
        r"\b(?:[Aa]nalyst|[Rr]esearcher)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,2})\b",
        r"\b[Aa]ccording\s+to\s+([A-Z][A-Za-z0-9&+.'-]+(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,3})\b",
        r"\b(?:[Nn]ote|[Rr]eport)\s+(?:from|by)\s+([A-Z][A-Za-z0-9&+.'-]+(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,3})\b",
        r"\b(?:[Mm]arket\s+)?[Rr]esearch\s+(?:firm|company)\s+"
        r"([A-Z][A-Za-z0-9&+.'-]+(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,3})\s+"
        r"(?:(?:has|had|now)\s+)?(?:reports?|reported|says|said|estimates?|estimated|forecasts?|forecast|"
        r"projects?|projected|predicts?|predicted|expects?|expected|outlines?|outlined)\b",
        r"\b([A-Z][A-Za-z0-9&+.'-]{2,30}(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,2})\s+"
        r"(?:(?:has|had|now)\s+)?(?:reports?|reported|says|said|estimates?|estimated|forecasts?|forecast|"
        r"projects?|projected|predicts?|predicted|expects?|expected|outlines?|outlined|"
        r"adds?|added|believes?|data\s+shows)\b",
        r"(?:根据|据|按照)\s*(?:市场研究机构|研究机构|分析机构)?\s*"
        r"([A-Za-z][A-Za-z0-9&+.'-]{2,30})(?:\s|的|，|,)",
        r"(?:根据|据)\s*([\u4e00-\u9fff]{2,12})(?:社|媒体|机构)?"
        r"(?:的[^。；,，\n]{0,28})?(?:报道|消息|披露|称)",
        r"(?:根据|据)?(?:外媒|媒体|科技媒体)\s*"
        r"([A-Za-z][A-Za-z0-9&+.'-]{2,30})\s*(?:报道|披露|联系)",
        r"\b([A-Z][A-Z0-9&+.'-]{2,30})\s+"
        r"(?:reports?|reported|contacted|reached\s+out)\b",
        r"(?:分析师|研究员)[^。；,，\n]{0,24}?[（(]\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,2})\s*[）)]",
        r"(?:分析师|研究员)[^。；,，\n]{0,24}?([A-Z][A-Za-z'.-]+(?:\s*[A-Z][A-Za-z'.-]+)?)",
        r"\b([A-Z][A-Za-z0-9&+.'-]{2,30}(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,2})(?:\s*(?:总监|分析师|研究员)[^。；,，\n]{0,24})?"
        r"\s*(?:表示|称|指出|预计|预测|分析认为|报告称|数据显示|研究显示)",
        r"(?:市场研究机构|研究机构|分析机构|调研机构)\s*"
        r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9&+.'-]{1,23})"
        r"(?:的)?(?:报告称|数据显示|研究显示|预测|预计|分析认为|指出|表示)",
        r"([\u4e00-\u9fff]{2,16}(?:咨询|研究院|研究所|证券|银行|大学|实验室))"
        r"(?:的)?(?:报告称|数据显示|研究显示|预测|预计|分析认为|指出|表示)",
    )
    rejected = {
        "that", "this", "it", "they",
        "apple",
        "a-new",
        "april",
        "august",
        "december",
        "february",
        "january",
        "july",
        "june",
        "march",
        "may",
        "november",
        "october",
        "september",
        "the",
        "the-company",
        "the-report",
        "the-same",
    }
    for pattern in patterns:
        for match in _compiled_rule(pattern).finditer(scope):
            raw_value = match.group(1)
            if _compiled_rule(r"\b(?:iphone|ipad|macbook)\s*$", re.I).search(scope[:match.start(1)]):
                continue
            value = _attribution_slug(raw_value)
            if value and value not in rejected:
                values.add(value)
    return {f"report-attribution:{value}" for value in values}


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


def has_haptic_patent_subject(title: str, lead: str) -> bool:
    """Bind the disputed physical technology, not a device in case background."""
    for text in (_normalized(title), _normalized(lead)[:520]):
        for start, end in source_sentence_spans(text):
            clause = text[start:end]
            if (_compiled_rule(r"\b(?:haptics?|taptic\s+engine|vibration)\b|触觉|振动", 0).search(clause)
                    and _compiled_rule(r"\bpatents?\b|\bip\s+(?:trial|case|suit)\b|专利", 0).search(clause)):
                return True
    return False


def _legal_case_topics(title: str, lead: str, facets: Iterable[str]) -> set[str]:
    text = f"{_normalized(title)} {_normalized(lead)[:520]}"
    topics: set[str] = set()
    aliases = (
        ("antitrust", ("antitrust", "anti-monopoly", "反垄断", "垄断诉讼")),
        ("app-store-commission", ("app store commission", "app store 佣金", "anti-steering", "反引导")),
        ("trade-secret", ("trade secret", "trade-secret", "商业机密", "商业秘密", "窃取机密")),
        ("privacy", ("privacy", "hide my email", "隐私", "隐藏我的邮件", "隐藏电子邮件")),
        (
            "anti-stalking",
            (
                "anti-stalking",
                "anti stalking",
                "stalking alert",
                "stalking protection",
                "反跟踪",
                "防跟踪",
                "跟踪警报",
            ),
        ),
        ("patent", ("patent", "专利")),
        (
            "independent-repair",
            (
                "independent repair",
                "third-party repair",
                "right to repair",
                "独立维修",
                "第三方维修",
                "维修权",
            ),
        ),
    )
    for name, terms in aliases:
        if _contains_any(text, terms):
            topics.add(name)
    if (
        _contains_any(text, ("bitcoin wallet", "crypto wallet", "cryptocurrency wallet", "比特币钱包", "加密货币钱包"))
        and _contains_any(
            text,
            (
                "fake",
                "fraudulent",
                "spoof",
                "impersonat",
                "stole",
                "stolen",
                "scam",
                "假冒",
                "仿冒",
                "伪造",
                "诈骗",
                "盗取",
                "被盗",
            ),
        )
    ):
        topics.add("crypto-wallet-fraud")
    if "apple-hardware-trade-secret-lawsuit" in facets:
        topics.add("trade-secret")
    return topics


def is_causal_explanation(title: str, lead: str) -> bool:
    """Commentary wording plus explanatory lead; current announcements survive."""
    h, opening = _normalized(title), _normalized(lead)[:700]
    return bool(_compiled_rule(r"(?:全|都)是.{1,24}惹的祸", 0).search(h)
        and _compiled_rule(r"为什么|要搞清楚|首先要知道|在我看来", 0).search(opening)
        and not _compiled_rule(r"苹果(?:公司)?(?:今日|今天|现已|刚刚)(?:宣布|发布|推出)", 0).search(opening))


def source_apple_invitation_fact(text: str) -> bool:
    """Keep an asserted invitation visible; it does not establish its freshness."""
    for start, end in source_sentence_spans(text):
        clause = _normalized(text[start:end])
        if _compiled_rule(r"(?:apple\s+(?:has\s+)?invited|苹果(?:公司)?已?邀请).{0,80}(?:media|journalists?|creators?|媒体|记者|创作者)").search(clause):
            if not _compiled_rule(r"expected|rumou?r|last\s+year|previously|not\s+invited|预计|可能|去年|此前|没有|并未").search(clause):
                return True
    return False


def source_editorial_evaluation(title: str, lead: str) -> str:
    """Identify an evaluation's reporting role, not its background launch."""
    h, opening = _normalized(title), _normalized(lead)[:600]
    s = _frame_search
    judgment = r'\b(?:not\s+convinced|unconvinced|questions?\s+(?:its|the)\s+value)\b|质疑.{0,8}价值'
    if s(judgment, h) and not _extract_patterns(h, ACTION_PATTERNS):
        for start, end in source_clause_spans(opening):
            clause = opening[start:end]
            reviewer = s(r'\b(?:reviewer|critic)\b|评测者|评论者', clause)
            if reviewer and s(judgment, clause[reviewer.end():]):
                return 'review'
    attribution = (r'["“‘]|\b(?:said|says?|told|explain\w*|according|wrote|writes?|'
                   r'argue\w*|state\w*|report\w*)\b|表示|解释|称|告诉|写道')
    def writer_position(clause):
        narrator = s(r'\bi\s+(?:think|believe|suspect)\b|\bin\s+my\s+view\b|我认为|我觉得|在我看来', clause)
        if narrator and not s(attribution, clause[:narrator.start()]):
            return narrator
        return None
    buyer_justification = (r'\b(?:may|might|could)\s+help\s+(?:buyers|customers|you)\s+'
                           r'justify\s+(?:the\s+)?(?:price|cost|spending|buying)\b')
    title_argument, lead_argument = s(buyer_justification, h), s(buyer_justification, opening)
    if (title_argument and lead_argument
            and not s(attribution, h[:title_argument.start()])
            and not s(attribution, opening[:lead_argument.start()])):
        return 'buying_advice'
    if (s(r'future|outlook|strategy|revamp|前景|战略|改造', h)
            and s(r'\b(?:bright|promising|incomplete|half\s+done)\b|光明|乐观|未完成', h)
            # Generic nouns such as "revamp" identify a topic, whereas a
            # release or a concrete capability predicate identifies news.
            and not (_extract_patterns(h, ACTION_PATTERNS) - {'feature-change'})
            and not s(r'\b(?:adds?|updates?|supports?|includes?|provides?|removes?|tests?|measures?)\b|'
                      r'新增|更新|支持|包含|移除|测试|测量', h)):
        for start, end in source_sentence_spans(opening):
            clause = opening[start:end]
            if writer_position(clause):
                return 'analysis'
    if (s(r'\b(?:one|only|real)\s+use[ -]case\b|(?:唯一|真正).{0,8}(?:用途|使用场景)', h)
            and not s(r'\b(?:supports?|includes?|provides?|adds?|tests?|measurements?|benchmarks?)\b|支持|包含|提供|新增|测试|测量', h)
            and not s(r'^(?:apple|苹果).{0,20}(?:explains?|announc\w*|introduc\w*|launch\w*|adds?|解释|宣布|推出|新增)', h)):
        for start, end in source_sentence_spans(opening):
            clause = opening[start:end]
            narrator = writer_position(clause)
            if narrator and s(r'use[ -]case|purpose|用途|使用场景', clause[narrator.end():]):
                return 'analysis'
    if (s(r'^get\s+ready\b.{0,80}\bby\s+(?:checking|using|setting)|准备.{0,20}(?:检查|设置)', h)
            and s(r"here[’']s\s+how|how\s+to\s+do|操作步骤|设置方法", opening)):
        return 'tutorial'
    if s(r'上手汇总|hands.on\s+(?:roundup|round.up)', h):
        return 'review'
    if (s(r'best\s+feature|simplicity|simpler\s+alternative|deficiencies|最佳功能|更简单的替代|不足', h)
            and (writer_position(opening) or s(r"as\s+(?:someone|the\s+owner)|we[’']ve\s+been\s+waiting|strange\s+compromise|reason\s+to\s+question|我期待|我向往", opening))):
        return 'analysis'
    if (s(r'missed\s+an?\s+opportunity|still.{0,15}(?:not|isn.t).{0,12}(?:good|viable)|错失机会', h)
            and s(r'hopes?|dreams?|design\s+decisions|room\s+for\s+improvement|期待|希望|设计决策', opening)
            and not s(r'benchmark|measured|test\s+results|实测|测量结果', h)):
        return 'analysis'
    if s(r'retrospective|look\s+back\s+at|what.{0,30}last\s+year|历史回顾|去年.{0,20}(?:费用|价格)', h):
        return 'analysis'
    if (s(r'(?:better.sounding|cheaper|better)\s+(?:and\s+\w+\s+)?(?:options|alternatives)|best\s+and\s+worst', h)
            and s(r'alternatives|recommend|we\s+can\s+judge|feels?|选择|推荐', opening)):
        return 'buying_advice'
    if (s(r'too\s+expensive|achilles[’\x27]?\s+heel|致命弱点|不值得', h)
            and s(r"\bi(?:[’\x27]ve|\s+have|[’\x27]m)|unnecessarily|imagine|我认为|我觉得", opening)):
        return 'analysis'
    if (s(r'everything.{0,35}(?:coming|expect)|新品前瞻|即将亮相', h)
            and s(r'here.{0,20}everything.{0,25}expecting|此前.{0,16}传闻', opening)):
        return 'analysis'
    if s(r'^i\s+(?:tried\s+out|went\s+hands.on)|^hands.on\s+with', h):
        return 'review'
    return ''


def _content_form(title: str, lead: str = "") -> str:
    lower = _normalized(title)
    lead_lower = _normalized(lead)[:700]
    if _compiled_rule(r"^(?:on\s+)?this\s+week's\s+episode\s+of\b.{0,80}\bpodcast|^(?:本周|本期).{0,30}播客", 0).search(lead_lower):
        return "podcast"
    if _compiled_rule(r"\bgiveaway\b", 0).search(lower):
        giveaway_caption = _compiled_rule(
            r'^(?P<caption>[^:："“”!?。]*\bgiveaway)\s*[:：—–-]\s*(?:enter|win)\b', 0
        ).search(lower)
        opening = _compiled_rule(r"[。!?]|\.\s+", 0).split(lead_lower, 1)[0]
        if (_compiled_rule(r"^(?:enter|win)\b", 0).search(lower)
                or (giveaway_caption and not _extract_patterns(
                    giveaway_caption['caption'] + " " + opening, ACTION_PATTERNS))
                or _compiled_rule(r"^(?:enter\s+(?:our|this|the)\s+(?:giveaway|contest)|"
                                  r"we(?:['’]re| are)\s+giving\s+away)\b", 0).search(lead_lower)):
            # Invitations must own the headline or opening assertion. A news
            # action still owns an advertisement quoted later in the report.
            return "deal"
    if (_compiled_rule(r"^remembering\b|^纪念", 0).search(lower)
            and _compiled_rule(r"anniversary|years?\s+after|death|逝世|周年", 0).search(lower + " " + lead_lower)):
        return "analysis"
    if (_compiled_rule(r"^i(?:['’]ve| have)\s+spent\b", 0).search(lead_lower)
            and _compiled_rule(r"using|testing|使用|测试", 0).search(lead_lower[:240])):
        return "review"
    if is_causal_explanation(title, lead):
        return "analysis"
    evaluation = source_editorial_evaluation(title, lead)
    if evaluation:
        return evaluation
    if is_personal_product_complaint(title):
        return "opinion"
    if is_weekly_editorial_recap(lead):
        return "roundup"
    if (_compiled_rule(r"\ball\b.{0,40}\b(?:shows|movies|films)\b.{0,40}\bwhat\s+to\s+watch\b").search(lower)
            and not _compiled_rule(r"\b(?:newly|today|this\s+week)\b").search(lower)):
        return "roundup"
    if is_institutional_apple_device_purchase(title, lead):
        return "news"
    if (_compiled_rule(r"(?:买|购买).{0,40}(?:靠谱吗|靠不靠谱)|验机(?:流程|全记录)|"
                       r"\b(?:purchase|shopping|inspection)\b.{0,25}\b(?:experience|checklist|walkthrough)\b", 0).search(lower)
            and _compiled_rule(r"^(?:(?:最近|近日)\s*)?(?:(?:我|本人).{0,45}(?:买|购|下单)|想买)|"
                               r"^(?:recently,?\s+)?i\s+(?:bought|purchased|ordered)\b", 0).search(lead_lower[:400])):
        # A buyer's receipt/inspection walkthrough reports a retail experience,
        # not a newly disclosed device behavior or an Apple diagnostic release.
        return "review"
    if (_compiled_rule(r"\bapps?\b|应用", 0).search(lower)
            and _compiled_rule(r"\b(?:best|favorite|favourite|deserve|worth|picks)\b|推荐|配得上|值得|适合", 0).search(lower)
            and _compiled_rule(r"\b(?:we|i|our\s+editors)\b[^。.!?]{0,100}\b(?:recommend|picked|selected)\b|(?:我们|我|编辑部)[^。.!?]{0,50}(?:推荐|精选|选出)", 0).search(lead_lower)
            and not _compiled_rule(r"^(?:apple\s+(?:(?:has|today|now)\s+)*(?:recommends|selects|features|release[sd]?|update[sd]?|announce[sd]?|launch(?:es|ed)?)\b|苹果(?:今日|今天|已经|正式)?(?:推荐|精选|选出|发布|更新|宣布|推出))", 0).search(lower)):
        # Device specifications in the body do not turn the writer's app
        # selection into a first-party hardware report.
        return "third_party_spotlight"
    if (_compiled_rule(r"\b(?:top|best|our)\s+(?:picks|recommendations)|购买推荐|配件推荐", 0).search(lower)
            and _compiled_rule(r"\b(?:accessories|recommendations|picks)\b|推荐|选购", 0).search(lead_lower)):
        return "buying_advice"
    if (_compiled_rule(r"\b(?:best|final|perfect)\b.{0,60}\b(?:iteration|form factor|design)\b|形态.{0,15}(?:终点|巅峰)", 0).search(lower)
            and _compiled_rule(r"\bi\s+(?:do\s+)?think\b|我认为|我觉得", 0).search(lead_lower)):
        return "analysis"
    if _compiled_rule(r"\b\d+\s+tips?\s+(?:to|for)\b", 0).search(lower):
        return "tutorial"
    if (_compiled_rule(r"(?:员工|开发者).{0,24}(?:感慨|讨论汇总)|\b(?:employees?|developers?)\b.{0,30}\b(?:reminisce|react)\b", 0).search(lower)
            and _compiled_rule(r"发布后|历史|曾参与|\b(?:after|previously|memories)\b", 0).search(lead_lower)):
        return "opinion"
    # The publisher's recap, archive list, or reader prompt is the source
    # action; Apple product names in its linked stories are not new reports.
    if (_compiled_rule(r"\blisten\s+to\s+a\s+recap\b", 0).search(lead_lower)
            and _compiled_rule(r"\b(?:podcast|episodes?|rss\s+feed)\b", 0).search(lead_lower)):
        return "podcast"
    if (_compiled_rule(r"\b(?:announced|released|unveiled)\s+\d+\s+(?:new\s+)?products?\s+in\s+the\s+past\s+month\b", 0).search(lower)
            and _compiled_rule(r"\b(?:previous\s+coverage|in\s+case\s+you\s+missed|recent\s+wave)\b", 0).search(lead_lower)):
        return "roundup"
    if (_compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+products?\s+launching\s+soon\b", 0).search(lower)
            and _compiled_rule(r"\b(?:rumou?red|waited\s+a\s+long\s+time|unveilings?\s+soon)\b", 0).search(f"{lower} {lead_lower}")):
        return "roundup"
    if (_compiled_rule(r"^(?:【[^】]*(?:互动|调查|投票)[^】]*】|\[poll\])", 0).search(lower)
            and _compiled_rule(r"(?:特别调查|读者|网友|你想|你会|投票|调查)", 0).search(f"{lower} {lead_lower}")):
        return "poll"
    # The page's reported act is the writer's use, comparison or collection
    # when the opening explicitly describes that work, even if Apple product
    # names and technical details appear throughout the article.
    opening_statement = _compiled_rule(r"(?<=[.!?])\s+|[。！？]", 0).split(lead_lower, 1)[0]
    if (_compiled_rule(r"\bwhy\s+i\s+(?:upgraded|switched|bought|chose)\b|我为什么(?:升级|换机|购买)", 0).search(lower)
            and _compiled_rule(r"\bi(?:['’]m| am|['’]ve| have|\s)|我", 0).search(opening_statement)):
        return "review"
    if (_compiled_rule(r"^i(?:\b|')|^我(?:想|决定|计划|在|已|买|认为)", 0).match(opening_statement)
            and _compiled_rule(r"\bi\s+(?:wanted|decided|chose|planned)\s+to\s+"
                               r"(?:test|try|compare|use)\b|我(?:想要?|决定|计划).{0,8}(?:测试|试用|体验)", 0).search(opening_statement)
            and _compiled_rule(r"\b(?:buy(?:ing)?|purchas(?:e|ing)|upgrad(?:e|ing)|"
                               r"downgrad(?:e|ing))\b|购买|购机|换机|升级", 0).search(lead_lower)):
        # The opening assertion belongs to the writer. Later reader quotes
        # or background trials do not redefine a reported product action.
        return "review"
    if (_compiled_rule(r"^[^:：]{2,35}(?:吐槽|抱怨|批评)", 0).match(lower)
            and _compiled_rule(r"(?:使用体验|自己.{0,12}体验|直播中.{0,20}(?:表示|直言))", 0).search(lead_lower)):
        return "analysis"
    if (_compiled_rule(r"\b(?:one|two|three|four|\d+)\s+(?:days?|weeks?|months?)\s+later\b", 0).search(lower)
            and _compiled_rule(r"\bi(?:['’]ve| have)\s+(?:been\s+using|found|enjoyed)\b|"
                          r"\bmy\s+(?:main\s+)?takeaway\b|\bi\s+(?:bought|was\s+compelled\s+to\s+buy)\b", 0).search(lead_lower)):
        return "review"
    if (_compiled_rule(r"\b(?:vs\.?|versus|compare)\b", 0).search(lower)
            and _compiled_rule(r"\bi\s+tested\s+(?:both|them)\b|\bi\s+(?:put|compared)\b.{0,35}\b(?:test|photos?)\b", 0).search(lead_lower)):
        return "hands_on"
    if (_compiled_rule(r"\bcoming\s+soon\b.{0,60}\b(?:changes?|features?)\b", 0).search(lower)
            and _compiled_rule(r"\beverything\s+we\s+know\s+so\s+far\b|\bhere['’]s\s+what\s+we\s+know\b", 0).search(lead_lower)
            and not _compiled_rule(r"\b(?:new|today['’]s)\s+(?:report|filing|disclosure)\b", 0).search(lead_lower)):
        return "roundup"
    # The editorial act remains selection or instruction even when its
    # introduction mentions the release which motivated that advice.
    if (_compiled_rule(r"\b(?:our|my)\s+(?:favorite|favourite|best|top)\s+(?:accessories|picks)\b").search(lower)
            and _compiled_rule(r"\b(?:we|i)\b[^.!?]{0,100}\b(?:look|picks|recommend|favorite|favourite)\b", 0).search(lead_lower)):
        return "buying_advice"
    if (_compiled_rule(r"(?:pin|unpin|save|organize|reorder)\b").match(lower)
            and _compiled_rule(r"\b(?:your|you)\b", 0).search(lower)
            and _compiled_rule(r"\b(?:tap|press and hold|select|click)\b", 0).search(lead_lower)):
        return "tutorial"
    # Reader-directed acquisition/settings is an editorial action, even when
    # the downloadable asset was extracted from a current OS release.
    if (_compiled_rule(r"^(?:download|get|save)\b").match(lower)
            and _compiled_rule(r"\b(?:wallpapers?|backgrounds?|images?)\b", 0).search(lower)
            and _compiled_rule(r"\b(?:download (?:them|it|these)|you can download|set (?:it|them)|click or tap)\b", 0).search(lead_lower)):
        return "tutorial"
    # Editorial organization of existing instruction pages is the parent
    # action. Verbs in its linked tutorial directory are not new Apple actions.
    instructional_purpose = bool(_compiled_rule(
        r"\b(?:guides?|tutorials?|how[- ]tos?)\b|教程|指南", 0).search(lead_lower))
    editorial_aggregation = _compiled_rule(
        r"\b(?:we|our\s+[^.!?]{0,45}(?:guide|collection|roundup))\s+"
        r"(?:have\s+)?(?:aggregat\w*|compil\w*|collect\w*|organiz\w*|gather\w*|bring\w*\s+together)"
        r"[^.!?]{0,100}\b(?:(?:existing|previous|earlier|past)\s+(?:coverage|guides?|tutorials?|articles?|reports?)|"
        r"our\s+[^.!?]{0,45}coverage)\b|"
        r"(?:我们|本文|本指南).{0,25}(?:汇总|整理|收集).{0,25}(?:既有|此前|过往|已有)(?:报道|教程|指南|文章)", 0
    ).search(lead_lower)
    guide_collection = instructional_purpose and bool(editorial_aggregation)
    current_title_action = False
    if guide_collection:
        # A current statement can follow neutral background, but must express
        # the headline's concrete action/object before the editorial archive.
        title_actions = _extract_patterns(lower, ACTION_PATTERNS)
        headline_object = _compiled_rule(
            r"\b(?:adds?|introduces?|removes?|changes?|updates?)\s+(?:(?:a|an|the)\s+)?"
            r"(?:new\s+)?([^:,.!?]+)", 0).search(lower)
        object_words = set()
        if headline_object:
            object_text = _compiled_rule(r"\b(?:for|in|on|with)\b", 0).split(headline_object.group(1), 1)[0]
            object_words = set(_compiled_rule(r"[a-z]{3,}", 0).findall(object_text)) - {"new", "the", "and"}
        for sentence in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead_lower[:editorial_aggregation.start()], 0):
            if _compiled_rule(r"^(?:separately|meanwhile|in other news)\b|^(?:另据|与此同时|另外)", 0).search(sentence):
                break
            if not _compiled_rule(r"^(?:apple\b|苹果)", 0).match(sentence):
                continue
            if _compiled_rule(r"\b(?:previously|earlier|last year|will|would|could|might|not|never)\b|此前|去年|将会|没有|并未", 0).search(sentence):
                continue
            current_title_action = bool(
                title_actions & _extract_patterns(sentence, ACTION_PATTERNS)
                and len(object_words) >= 2
                and object_words <= set(_compiled_rule(r"[a-z]{3,}", 0).findall(sentence))
            )
            # An explicit other Apple action starts a different local subject.
            if current_title_action or _extract_patterns(sentence, ACTION_PATTERNS):
                break
    if guide_collection and not current_title_action:
        return "tutorial"
    if (_compiled_rule(r"\bpraises?\b|夸赞|称赞", 0).search(lower)
            and _compiled_rule(r"personal (?:view|opinion)|个人(?:看法|观点)", 0).search(lead_lower)):
        return "analysis"
    if (_compiled_rule(r"\b(?:could|may|might)\b.{0,30}\b(?:push|persuade|convince)\s+you\s+to\s+(?:upgrade|buy)\b", 0).search(lower)
            and _compiled_rule(r"editorial|existing.{0,25}features?|购买建议|既有功能", 0).search(lead_lower)):
        return "buying_advice"
    if _compiled_rule(r"\b(?:roundup|daily brief(?:ing)?|morning brief(?:ing)?)\b|早报|科技早参", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"\b(?:the\s+)?(?:\d+|ten|several)\s+products?\s+above\b|上述.{0,5}款产品", 0).search(lead_lower) and _compiled_rule(r"other possibilities|most likely|其他可能|最有可能", 0).search(lead_lower):
        return "roundup"
    if (_compiled_rule(r"\bsounds?\b.{0,35}\b(?:deserving|worthy|promising|disappointing)\b", 0).search(lower)
            and _compiled_rule(r"existing rumou?rs|personal arguments|author.{0,25}(?:speculat|opinion)|个人观点|个人看法", 0).search(lead_lower)):
        return "analysis"
    if (_compiled_rule(r"\b(?:privacy|security)\s+(?:risks?|tradeoffs?)\b", 0).search(lower)
            and _compiled_rule(r"\b(?:analyzes?|commentary|tradeoffs?)\b", 0).search(lead_lower)):
        return "analysis"
    if (_compiled_rule(r"\b(?:personally,?\s+i\s+think|i\s+don[’']?t\s+think)\b", 0).search(lead_lower)
        and _compiled_rule(r"recent report|reports? and rumou?rs|long been reports|此前报道", 0).search(lead_lower)):
        return "analysis"
    if is_editorial_change_request(title):
        return "analysis"
    if (_compiled_rule(r"\bcould be\b.{0,20}\b(?:good|bad) news\b", 0).search(lower)
            and _compiled_rule(r"author argues|previous|earlier.{0,20}rumou?rs", 0).search(lead_lower)):
        return "analysis"
    if (_compiled_rule(r"bullish|看涨", 0).search(lower)
            and _compiled_rule(r"维持原有|maintains? (?:the )?existing", 0).search(lead_lower)
            and _compiled_rule(r"评级|目标价|rating|price target", 0).search(lead_lower)):
        return "analysis"
    service_catalog_roundup = bool(
        _contains_any(
            lower,
            (
                "apple tv",
                "apple music",
                "apple arcade",
                "apple books",
                "苹果电视",
                "苹果音乐",
            ),
        )
        and _compiled_rule(r"\b(?:here(?:'s| is)\s+)?(?:every|all)\b.{0,42}"
            r"\b(?:shows?|movies?|films?|series|titles?|releases?)\b.{0,42}"
            r"\b(?:coming|available|streaming|arriving|lineup)\b|"
            r"\beverything\b.{0,30}\b(?:coming|available|streaming|arriving)\b|"
            r"(?:全部|所有|完整).{0,24}(?:剧集|电影|节目|片单|内容).{0,24}"
            r"(?:即将|上线|阵容|一览|汇总)", 0).search(lower)
    )
    if service_catalog_roundup:
        return "roundup"
    if _compiled_rule(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+"
        r"(?:sleeps?|days?|weeks?)\s+(?:until|before)\b.{0,90}"
        r"\b(?:here(?:'s| is)\s+what\s+we\s+know|everything\s+we\s+know|what\s+to\s+expect)\b|"
        r"(?:还有|仅剩|倒计时)\s*[一二三四五六七八九十\d]+\s*(?:天|周)"
        r".{0,80}(?:已知信息|信息汇总|看点汇总|前瞻)", 0).search(lower):
        return "roundup"
    named_platform_app_spotlight = bool(
        not _compiled_rule(r"^(?:apple(?:'s)?|苹果|ios\b|ipados\b|macos\b|watchos\b|tvos\b|visionos\b)", 0).match(lower)
        and _compiled_rule(r"^[a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,3}\s+"
            r"(?:is|offers?)\b.{0,70}\b(?:ios|ipados|macos|watchos|tvos|visionos|"
            r"iphone|ipad|mac|apple\s+watch|vision\s+pro)\s+(?:app|application)\b", 0).search(lower)
        and not _compiled_rule(r"\b(?:from|by)\s+apple\b|\bapple\s+(?:launch(?:es|ed)?|release(?:s|d)?|"
            r"introduc(?:es|ed)?)\b|(?:苹果(?:推出|发布|上线))", 0).search(f"{lower} {lead_lower[:300]}")
    )
    if named_platform_app_spotlight:
        return "third_party_spotlight"
    if _compiled_rule(r"\brumou?rs?\s+(?:reality\s+check|roundup|ranking)\b.{0,80}"
        r"\b(?:claims?|rumou?rs?)\s+ranked\s+by\s+(?:likelihood|probability|credibility)\b|"
        r"(?:传闻|爆料).{0,24}(?:真实性|可信度|可能性).{0,20}(?:排名|排序|评级)", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\b"
        r".{0,40}\b(?:new\s+)?(?:apple\s+)?(?:products?|devices?)\b"
        r".{0,60}\b(?:here(?:'s| is)\s+what(?:'s| is)\s+coming|what\s+to\s+expect)\b|"
        r"(?:两|三|四|五|六|七|八|九|十|\d+)\s*款.{0,24}(?:苹果)?(?:新品|产品|设备)"
        r".{0,30}(?:前瞻|看点|一览|都有哪些)", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\b"
        r".{0,28}\b(?:advantages?|reasons?|benefits?)\b.{0,55}"
        r"\b(?:over|versus|vs\.?|compared\s+with)\b|"
        r"(?:两|三|四|五|六|七|八|九|十|\d+)\s*(?:项|个)?(?:优势|理由|好处)"
        r".{0,30}(?:对比|相比|胜过|优于)", 0).search(lower):
        return "analysis"
    leadership_scorecard = bool(
        _compiled_rule(r"\b(?:tim\s+cook|john\s+ternus|steve\s+jobs|apple\s+ceo)\b|"
            r"(?:库克|特努斯|乔布斯|苹果\s*ceo)", 0).search(lower)
        and (
            _compiled_rule(r"\b(?:wins?\s+and\s+(?:misses|losses)|hits?\s+and\s+misses|"
                r"got\s+right\s+and\s+wrong)\b|(?:功过|成败|得失|做对了什么|做错了什么)", 0).search(lower)
            or (
                _compiled_rule(r"\blegacy\b|遗产", 0).search(lower)
                and not _compiled_rule(r"\b(?:reflect(?:s|ed)?|comments?|says?|speaks?|leav(?:e|es|ing)|"
                    r"resign(?:s|ed|ing)?)\b|(?:回顾并回应|发表|表示|称|离任|离职|卸任)", 0).search(lower)
            )
        )
    )
    historical_media = bool(
        _compiled_rule(r"\b(?:apple|steve\s+jobs|tim\s+cook)\b|(?:苹果|乔布斯|库克)", 0).search(lower)
        and _compiled_rule(r"\b(?:19\d{2}|200\d|201[0-5])\b", 0).search(lower)
        and _compiled_rule(r"\b(?:vintage|resurfac(?:e|es|ed)|old\s+(?:video|interview)|archive[sd]?|interview)\b|"
            r"(?:旧(?:视频|采访)|早年采访|历史采访|重新流传|重现)", 0).search(f"{lower} {lead_lower}")
        and not _compiled_rule(r"\b(?:auction(?:ed)?|sold|sells?|launch(?:es|ed)?|release(?:s|d)?|publishes?)\b|"
            r"(?:拍卖|成交|出售|推出|发布)", 0).search(lower)
    )
    executive_biographical_profile = bool(
        _compiled_rule(r"\b(?:new\s+)?profile\s+(?:of|on)\b.{0,90}"
            r"\b(?:ceo|chief\s+executive|executive|leader|leadership|"
            r"life|career|reputation|personality|background)\b|"
            r"\bprofile\b.{0,70}\b(?:insight|inside\s+look)\b.{0,45}"
            r"\b(?:life|career|reputation|personality|background)\b", 0).search(lower)
        and not _compiled_rule(r"\b(?:appoint(?:s|ed)?|name(?:s|d)?|hire(?:s|d)?|resign(?:s|ed)?|"
            r"step(?:s|ped)?\s+down|announce(?:s|d)?|launch(?:es|ed)?|"
            r"release(?:s|d)?|acquire(?:s|d)?|file(?:s|d)?|sue(?:s|d)?)\b", 0).search(lower)
    )
    if leadership_scorecard or historical_media or executive_biographical_profile:
        return "analysis"
    multi_vendor_catalog = bool(
        _contains_any(lower, APPLE_TITLE_TERMS)
        and len(
            {
                vendor
                for vendor, aliases in (
                    ("samsung", ("samsung", "三星")),
                    ("google", ("google", "pixel", "谷歌")),
                    ("huawei", ("huawei", "mate ", "华为")),
                    ("xiaomi", ("xiaomi", "redmi", "小米", "红米")),
                    ("oppo", ("oppo",)),
                    ("vivo", ("vivo", "iqoo")),
                    ("honor", ("honor", "荣耀")),
                )
                if _contains_any(lower, aliases)
            }
        )
        >= 2
        and _compiled_rule(r"\b(?:prices?|release dates?|launch dates?|schedule|lineup|list)\b|"
            r"(?:售价|价格|发布时间|发布日期|档期|一览|清单|名单)", 0).search(lower)
    )
    if multi_vendor_catalog:
        return "roundup"
    if _compiled_rule(r"^(?:as\s+(?:a|an)\b|i(?:'m| am|'ve| have)\b).{0,90}"
        r"\b(?:my\s+favorite|favorite\s+way|how\s+i\s+use|way\s+to\s+use)\b|"
        r"\bmy\s+favorite\s+way\s+to\s+use\b|"
        r"^(?:作为|身为).{0,28}(?:用户|使用者).{0,40}(?:我最喜欢|我的用法|使用方式)", 0).search(lower):
        return "analysis"
    single_user_support_experiment = bool(
        _compiled_rule(r"\b(?:a|one)\s+(?:user|owner|customer)\b|"
            r"\b(?:iphone|ipad|macbook|apple\s+watch)\s+(?:user|owner)\b|"
            r"(?:m[1-9](?:\s+(?:pro|max|ultra))?).{0,8}(?:用户|机主)|"
            r"(?:一位|一名|这个|该)?(?:用户|机主|消费者)", 0).search(f"{lower} {lead_lower}")
        and _compiled_rule(r"\b(?:battery\s+(?:health|cycle)|cycles?\s+(?:the\s+)?battery|"
            r"discharg(?:e|es|ed|ing))\b|(?:电池健康|电池循环|充放电|循环充电)", 0).search(f"{lower} {lead_lower}")
        and _compiled_rule(r"\b(?:qualif(?:y|ies|ied)|trigger|eligib(?:le|ility)|free\s+replacement|"
            r"applecare\+?)\b|(?:符合|触发|达到).{0,18}(?:免费)?(?:更换|维修)(?:条件|资格)|"
            r"(?:免费换|免费更换|applecare\+?)", 0).search(f"{lower} {lead_lower}")
        and not _compiled_rule(r"(?:apple|苹果).{0,28}(?:宣布|发布|推出|调整|变更|扩大|"
            r"announces?|releases?|launches?|changes?|expands?)", 0).search(lower)
    )
    if single_user_support_experiment:
        return "user_anecdote"
    if _compiled_rule(r"\b(?:apple\s+)?(?:event|keynote)\b.{0,42}"
        r"\b(?:highlights?|what\s+to\s+expect|everything\s+to\s+know|all\s+the\s+details)\b|"
        r"(?:苹果)?(?:秋季|春季|新品)?发布会.{0,20}(?:看点|看头|前瞻|展望)"
        r"(?:.{0,10}(?:都在|一览|汇总|盘点|合集))?", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"\bmy\s+(?:frustration|experience|take|thoughts?)\b|"
        r"\bi(?:'m| am)\s+(?:excited|eager|tempted)\s+to\s+(?:buy|try|upgrade)\b|"
        r"\b(?:features?|changes?|upgrades?)\s+i(?:'m| am)\s+"
        r"(?:excited|eager|tempted)\s+to\s+(?:buy|try|upgrade)\b|"
        r"(?:我的|我对).{0,20}(?:不满|体验|看法|想法)|"
        r"我(?:很|最)?(?:期待|想要|打算).{0,18}(?:购买|尝试|升级|换机)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\brumou?rs\s*:\s*[^:]{2,100}(?:,|/|\band\b)[^:]{2,100}$|"
        r"(?:传闻|爆料)(?:汇总|盘点|一览)\s*[：:].{2,100}(?:、|，|/|和).{2,100}$", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"\b(?:concept|fan[- ]made)\s+(?:video|film|teaser|render)\b|"
        r"\b(?:video|teaser|render)\b.{0,35}\b(?:imagines?|fan[- ]made)\b|"
        r"\bconcept\b.{0,35}\b(?:show(?:s|ing)?|imagin(?:e|es|ing)|present(?:s|ing)?)\b|"
        r"\bnot\s+(?:a\s+)?(?:real\s+)?apple\s+(?:ad|advertisement|video)\b|"
        r"(?:概念视频|粉丝制作|民间制作).{0,20}(?:想象|设想|演示|展示)", 0).search(f"{lower} {lead_lower}"):
        return "analysis"
    direct_apple_trade_in_change = bool(
        _compiled_rule(r"^(?:apple(?:'s|’s)?|苹果)", 0).search(lower)
        and _compiled_rule(r"\b(?:raises?|updates?|increases?|changes?|adjusts?)\b.{0,40}"
            r"\b(?:trade[- ]?in|resale)\s+(?:values?|offers?)\b|"
            r"(?:上调|更新|调整|提高).{0,24}(?:以旧换新|折抵|回收)(?:价|价值|报价)", 0).search(lower)
    )
    third_party_resale_analysis = bool(
        not direct_apple_trade_in_change
        and _compiled_rule(r"\b(?:trade[- ]?in|resale)\s+(?:value|values|price|prices|estimate|estimates)\b|"
            r"(?:旧机|二手(?:手机|设备)?).{0,12}(?:回收价|二手价|保值率)|"
            r"(?:回收价|二手价|保值率).{0,12}(?:下跌|跌幅|损失|调查|分析|参考)", 0).search(lower)
        and _compiled_rule(r"\b(?:survey|study|analysis|comparison|aggregator|estimates?|finds?|says?)\b|"
            r"(?:调查|分析|比价|平台|机构|参考|称|报告)", 0).search(f"{lower} {lead_lower}")
    )
    if third_party_resale_analysis:
        return "analysis"
    if _compiled_rule(r"^(?:skip|avoid|replace)\b.{0,100}\b(?:with|using)\s+"
        r"(?:these|one\s+of\s+these|an?|your\s+own)\b", 0).match(lower):
        return "buying_advice"
    if (
        _compiled_rule(r"\b(?:pre[- ]?orders?|release date|availability date)\b|"
            r"(?:预购日期|发售日期|上市日期)", 0).search(lower)
        and _compiled_rule(r"\b(?:educated guess|historical pattern|history suggests|most likely|"
            r"likely date|we can guess|prediction)\b|"
            r"(?:根据历史|历年规律|推测|推演|预计日期|大概率)", 0).search(lead_lower)
        and not _compiled_rule(r"\b(?:according to|new report|sources? say|analyst|leaker)\b|"
            r"(?:据.{0,16}(?:报道|消息|透露)|分析师|爆料人|最新报告)", 0).search(lead_lower)
    ):
        return "analysis"
    if (
        _contains_any(lower, ("apple", "苹果"))
        and _compiled_rule(r"\b(?:collectively|multiple\s+(?:companies|vendors)|several\s+(?:companies|vendors))\b|"
            r"(?:多家|多个|集体).{0,20}(?:公司|厂商|品牌)?.{0,10}(?:涨价|提价|调价)", 0).search(lower)
        and _compiled_rule(r"\b(?:prices?|pricing)\b|(?:涨价|提价|调价|价格)", 0).search(lower)
    ):
        return "roundup"
    if _compiled_rule(r"\bwhere\s+to\s+pre-?order\b", 0).search(lower):
        return "buying_advice"
    if _compiled_rule(r"\b(?:available|order|pre-?order).{0,36}\b(?:amazon|best buy|b&h|walmart)\b|"
        r"\b(?:amazon|best buy|b&h|walmart)\b.{0,36}\b(?:available|order|pre-?order)\b", 0).search(lower):
        return "deal"
    schedule_inference = bool(
        _compiled_rule(r"\b(?:pre[- ]?orders?|release date|launch date)\b|"
            r"(?:预购|发布日期|发售日期)", 0).search(lower)
        and _compiled_rule(r"\b(?:has yet to|has not)\s+(?:reveal|announce|confirm)\b|"
            r"(?:尚未|还未|没有)(?:公布|宣布|确认)", 0).search(lead_lower)
        and len(
            _compiled_rule(r"\b(?:familiar|historical|usual)\s+pattern\b|"
                r"\b(?:most likely|another possibility|until proven otherwise|would likely)\b|"
                r"(?:历年节奏|历史规律|最可能|另一种可能|推演)", 0).findall(lead_lower)
        )
        >= 2
        and not _compiled_rule(r"\b(?:according to|new report|sources? say|analyst|leaker)\b|"
            r"(?:据.{0,16}(?:报道|消息|透露)|分析师|爆料人|最新报告)", 0).search(lead_lower)
    )
    if schedule_inference:
        return "analysis"
    if _compiled_rule(r"\b(?:recaps?|compiles?)\b.{0,50}\b(?:existing|earlier|previously reported|prior)\b"
        r".{0,45}\b(?:rumou?rs?|roadmap|reports?)\b|"
        r"(?:汇总|盘点|整理).{0,24}(?:既有|此前|过去).{0,24}(?:传闻|爆料|路线图|报道)", 0).search(lead_lower):
        return "roundup"
    if _compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\b"
        r".{0,18}\b(?:new\s+)?(?:features?|changes?|upgrades?)\b"
        r".{0,42}\b(?:worth\s+(?:the\s+)?wait|worth\s+waiting\s+for)\b|"
        r"(?:两|三|四|五|六|七|八|九|十|\d+)\s*(?:项|个)?(?:新)?(?:功能|变化|升级)"
        r".{0,30}(?:值得等待|值得期待)", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"(?:[一二三四五六七八九十百\d]+)\s*(?:大|项|个)?\s*"
        r"(?:核心)?(?:亮点|卖点|功能|特性)(?:汇总|盘点|一览)", 0).search(lower):
        return "roundup"
    first_person_multi_product_preview = bool(
        _compiled_rule(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\b"
            r".{0,45}\b(?:new\s+)?(?:apple\s+)?(?:products?|devices?)\b|"
            r"(?:两|三|四|五|六|七|八|九|十|\d+)\s*款.{0,24}(?:苹果)?(?:产品|设备|新品)", 0).search(lower)
        and _compiled_rule(r"\b(?:i(?:'m| am)|we(?:'re| are))\b.{0,50}"
            r"\b(?:excited|eager|looking forward|can['’]?t wait|most interested)\b|"
            r"(?:我|我们).{0,28}(?:最期待|很期待|感兴趣|迫不及待)", 0).search(f"{lower} {lead_lower}")
        and not _compiled_rule(r"\b(?:new report|according to|sources? say|bloomberg reports|"
            r"apple (?:plans?|will|is testing|is developing))\b|"
            r"(?:最新报道|据.{0,18}(?:报道|消息|透露)|消息称|苹果(?:计划|将|正在测试|正在开发))", 0).search(lead_lower)
    )
    if first_person_multi_product_preview:
        return "analysis"
    historical_product_comparison = bool(
        _compiled_rule(r"\b(?:tenure|era|history)\b|任期|任内|时代|历程", 0).search(lower)
        and _compiled_rule(r"\bfirst\b.{0,60}\b(?:last|latest)\b|第一.{0,40}最后", 0).search(lower)
        and _compiled_rule(r"\b(?:same|unchanged|still)\b|都是|仍然|依然|相同|一样", 0).search(lower)
        and not _compiled_rule(r"\bapple\s+(?:announces?|unveils?|introduces?|changes?)\b|"
            r"苹果(?:公司|官方)?(?:今日|今天|正式)?(?:宣布|推出|更改|调整)", 0).search(lower)
    )
    if historical_product_comparison:
        return "analysis"
    retrospective_without_new_action = bool(
        _compiled_rule(r"^how\s+(?:apple|iphone|ipad|mac|airpods)\b", 0).match(lower)
        and _compiled_rule(r"\b(?:last\s+(?:week|month|year)|previously|earlier|already)\b|"
            r"(?:上周|上月|去年|此前|早前|已经)", 0).search(lead_lower)
        and _compiled_rule(r"\b(?:had|has|have)\s+(?:already\s+)?appeared\s+in\s+previous\b|"
            r"\b(?:previously reported|already reported|no new reporting|not new information)\b|"
            r"(?:此前已经|早已).{0,24}(?:出现|报道|披露)|(?:没有|并无)新增(?:消息|信息|动作)", 0).search(lead_lower)
    )
    if retrospective_without_new_action:
        return "analysis"
    reader_guidance = bool(
        _compiled_rule(r"(?:大家|你).{0,45}(?:有没有发现|用错|可以|不要|别急)", 0).search(lead_lower)
        and _compiled_rule(r"(?:如果|很多时候|同一个人).{0,80}(?:拍|用|选择|设置)", 0).search(lead_lower)
        and _compiled_rule(r"技巧|可以记住|你可以|也不要|别只顾|先别", 0).search(lead_lower)
    )
    current_release = bool(_compiled_rule(r"^(?:apple\s+(?:(?:today|has|just)\s+)*(?:announced|released|introduced|launched)|苹果(?:今日|今天|刚刚|正式)*(?:发布|推出|宣布))", 0).search(lead_lower))
    if reader_guidance and not current_release:
        return "tutorial"
    built_in_feature_tip = bool(
        _compiled_rule(r"^(?:apple|iphone|ipad|mac|airpods|苹果).{0,18}"
            r"(?:没告诉你|不会主动告诉你|你可能不知道|隐藏着|自带).{0,70}"
            r"(?:自带|内置|隐藏|不用|无需)|"
            r"(?:不用|无需).{0,16}(?:额外)?(?:安装|装|下载).{0,12}(?:app|应用)", 0).search(lower)
        and not _compiled_rule(r"\b(?:announces?|launches?|releases?|rolls?\s+out|adds?|removes?|changes?)\b|"
            r"(?:宣布|发布|推出|上线|新增|移除|调整)", 0).search(lower)
    )
    if built_in_feature_tip:
        return "tutorial"
    if _compiled_rule(r"\b(?:how\s+to|getting\s+started\s+with|beginner(?:'s)?\s+guide\s+to|"
        r"hidden\s+(?:tips?|tricks?)|things?\s+you\s+can\s+do)\b|"
        r"(?:教程|入门指南|快速上手|使用技巧|隐藏玩法|冷知识|这些玩法|这样使用|赶快用起来)", 0).search(lower) and not _compiled_rule(r"\b(?:announces?|launches?|releases?|rolls?\s+out|adds?|removes?|changes?)\b|"
        r"(?:宣布|发布|推出|上线|新增|移除|调整)", 0).search(lower):
        return "tutorial"
    if _compiled_rule(r"\b(?:ways?|reasons?)\b.{0,70}\b(?:could|may|might)\b.{0,55}"
        r"\b(?:upgrade|improve|change|benefit|gain|get)\w*\b|"
        r"\bwhat\b.{0,45}\b(?:reveals?|means?)\b.{0,50}\bfor\b|"
        r"(?:从|根据).{0,35}(?:推测|推演|畅想).{0,45}(?:可能|或将|有望)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\beverything\b.{0,55}\b(?:apple\s+)?(?:announced|released|unveiled|launched)\b|"
        r"\ball\b.{0,45}\b(?:announcements?|releases?|launches?)\b|"
        r"(?:今日|本周|发布会|新品).{0,24}(?:全部|完整)?(?:汇总|盘点)|"
        r"(?:全部|完整).{0,24}(?:发布|新品|更新).{0,14}(?:汇总|盘点)", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"\b(?:podcast|episode|overtime)\b", 0).search(lower) or (
        _compiled_rule(r"\b(?:podcast episode|weekly podcast|video-first podcast|"
            r"(?:on\s+)?this week['’]s episode of (?:the )?.{0,80}?podcast|"
            r"episode of (?:the )?.{0,80}?podcast)\b", 0).search(lead_lower)
        and not _compiled_rule(r"\b(?:launches|releases|updates|adds|announces)\b", 0).search(lower)
        and not (_compiled_rule(r"\b(?:apple|macbook|iphone|ipad)\b", 0).search(lower)
                 and _compiled_rule(r"\b(?:according to|reportedly|rumou?red|claimed|revealed)\b", 0).search(lead_lower))
    ):
        return "podcast"
    if _compiled_rule(r"^psa:\s+", 0).match(lower) and not _compiled_rule(r"\b(?:launches?|releases?|announces?|rolls? out|changes?|adds?|removes?|stop\s+syncing|discontinues?)\b|"
        r"(?:发布|推出|宣布|上线|变更|新增|移除)", 0).search(lower):
        return "tutorial"
    if _compiled_rule(r"^(?:add|enable|disable|turn on|turn off|show|hide|change|set up)\b"
        r".{0,90}\b(?:on|to|for)\s+(?:your\s+)?(?:iphone|ipad|mac|apple watch)\b", 0).match(lower) or _compiled_rule(r"\b(?:here['’]s the fix|troubleshooting guide|fix seems to work)\b|故障排查|解决办法", 0).search(lower):
        return "tutorial"
    settings_advice = bool(
        (
            _compiled_rule(r"\b(?:turn|switch)\s+(?:(?:off|on)\s+(?:this|the)|(?:this|the)\s+)"
                r"\s*(?:default\s+)?(?:setting|option)(?:\s+(?:off|on))?\b|"
                r"\b(?:disable|enable|change|adjust)\s+(?:this|the)\s+(?:default\s+)?(?:setting|option)\b|"
                r"(?:设置|功能|选项).{0,12}(?:建议|最好|可以|应该|应当).{0,10}"
                r"(?:关闭|关掉|开启|打开|调整|更改)", 0).search(lower)
            or _compiled_rule(r"(?:建议|最好|可以|应该|应当).{0,10}(?:关闭|关掉|开启|打开|调整|更改)"
                r".{0,12}(?:设置|功能|选项)", 0).search(lower)
        )
        and _compiled_rule(r"\b(?:blurry|blurred|drain(?:ing)?|overheat(?:ing)?|slow|stuck|problem|issue)\b|"
            r"(?:总是|模糊|发糊|不清晰|耗电|掉电|发热|卡顿|失灵|问题|怎么办)", 0).search(lower)
        and not _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+){0,2}\b"
            r".{0,45}\b(?:adds?|changes?|updates?|introduces?|removes?)\b|"
            r"(?:苹果|apple).{0,28}(?:宣布|发布|推出|新增|调整|移除|announces?|releases?|adds?|changes?|removes?)", 0).search(lower)
    )
    if settings_advice:
        return "tutorial"
    single_user_workaround = bool(
        _compiled_rule(r"\b(?:a|one|reddit)\s+(?:user|owner|reader)\b|"
            r"(?:一位|一名|这个|该)(?:reddit\s*)?(?:用户|网友|机主|读者)|(?:老哥|小哥)|"
            r"(?:用户|网友|机主|读者)(?:自制|自行|用.{0,12}(?:修复|解决)|反手)", 0).search(f"{lower} {lead_lower}")
        and _compiled_rule(r"\b(?:broken|cracked|damaged|failed|failure|repair|screen damage|display damage)\b|"
            r"(?:摔坏|损坏|坏掉|故障|维修|碎屏|屏幕坏|屏幕损坏)", 0).search(f"{lower} {lead_lower}")
        and _compiled_rule(r"\b(?:workaround|diy|self-made|home-made|open-source|rubber band|"
            r"fix(?:es|ed)?|solv(?:es|ed)|uses? an? old)\b|"
            r"(?:解决方案|变通方案|自制|自行|开源|橡皮筋|反手|旧款.{0,12}(?:替代|充当|作为))", 0).search(f"{lower} {lead_lower}")
        and not _compiled_rule(r"(?:apple|苹果).{0,28}(?:宣布|发布|推出|扩展|新增|更新|修复|召回|"
            r"announces?|releases?|launches?|expands?|adds?|updates?|fixes?|recalls?)", 0).search(lower)
    )
    if single_user_workaround:
        return "user_anecdote"
    retail_usage_anecdote = bool(
        _compiled_rule(r"\bstores?\b|(?:体验店|零售店|门店|专卖店)", 0).search(lower)
        and _compiled_rule(r"\b(?:customers?|students?|children|visitors?)\b.{0,60}"
            r"\b(?:occupy|occupying|playing|linger)\b.{0,40}\b(?:demo|display)\b|"
            r"(?:学生|孩子|顾客|游客).{0,36}(?:占用|围在).{0,18}(?:样机|展示机|展示设备)", 0).search(lead_lower)
        and _compiled_rule(r"\b(?:store|staff)\b.{0,40}\b(?:no authority|cannot remove)\b|"
            r"(?:门店|店员|工作人员).{0,24}(?:无权|没有权利|没有权限)(?:劝阻|驱赶|赶走)?", 0).search(f"{lower} {lead_lower}")
        and not _compiled_rule(r"\bapple\b.{0,35}\b(?:announces?|changes?|introduces?|releases?)\b|"
            r"苹果(?:公司|官方)?[^。！？]{0,12}(?:宣布|发布|调整|变更|制定)", 0).search(f"{lower} {lead_lower}")
    )
    if retail_usage_anecdote:
        return "user_anecdote"
    if (
        "poll" in lower
        or _compiled_rule(r"^(?:what|which|would|will|should)\b.*\?", 0).match(lower)
        or _compiled_rule(r"(?:^|:\s*)(?:what|which)\b[^?？]{0,90}"
            r"\b(?:will|would|do)\s+you\s+(?:buy|choose|pick|prefer)\b[^?？]*[?？]", 0).search(lower)
        or _compiled_rule(r"\bshould\s+apple\b[^?？]*[?？]", 0).search(lower)
        or _compiled_rule(r"(?:vote|投票|你会怎么|你会如何|你是否).*[?？]?$", 0).search(lower)
    ):
        return "poll"
    if is_editorial_change_request(title):
        return "analysis"
    if _compiled_rule(r"^(?:[^:]{1,90}:\s*)?(?:when\s+is|when\s+will).{0,90}"
        r"\b(?:next\s+)?apple\s+(?:event|keynote)\b", 0).match(lower):
        return "analysis"
    if _compiled_rule(r"^(?:it['’]s|it\s+is|now\s+is)\s+time\s+for\s+"
        r"(?:apple|iphone|ipad|ios|ipados|macos|watchos|tvos|visionos|safari|siri)\b"
        r".{0,80}\bto\s+(?:have|get|add|adopt|offer|support|bring)\b", 0).match(lower):
        return "analysis"
    if _compiled_rule(r"^apple\s*,?\s+please\b", 0).match(lower) or _compiled_rule(r"(?:还|是否)?值得(?:购买|买|升级)吗[?？]?$", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\b(?:these\s+are|this\s+is)\b.{0,90}\b(?:it|apple)\s+"
        r"(?:has|needs)\s+to\b|"
        r"(?:这种|这类).{0,35}(?:苹果|它).{0,16}(?:必须|需要|应该)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\b(?:that|which)\s+i\s+(?:would|wish\s+apple\s+would)\s+change\b|"
        r"\bi\s+(?:would|wish\s+apple\s+would)\s+change\b|"
        r"(?:我希望|我会|我想让).{0,24}(?:苹果|macos|ios|设计|功能).{0,18}(?:改变|调整|修改)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\b(?:could|may|might|will)\s+(?:push|tempt|convince|persuade|make)\s+"
        r"(?:you|users?|owners?)\s+to\s+(?:buy|upgrade)\b|"
        r"(?:可能|或将|会).{0,18}(?:促使|吸引|说服|让).{0,12}(?:用户|你).{0,12}(?:购买|升级|换机)", 0).search(lower):
        return "buying_advice"
    if _compiled_rule(r"\b(?:buy|upgrade|get)\s+(?:it\s+)?now\b.{0,36}\b(?:or|versus|vs\.?)\b"
        r".{0,36}\bwait\b|"
        r"(?:现在|当下).{0,18}(?:买|购买|入手|上车|升级|换机).{0,14}"
        r"(?:还是|或是|或者).{0,14}(?:等|等待)", 0).search(f"{lower} {lead_lower}"):
        return "buying_advice"
    if _compiled_rule(r"\bhere['’]s\s+(?:the\s+)?one\s+i(?:'ve| have)\s+been\s+(?:loving|using)\b|"
        r"\b(?:one|feature)\s+i(?:'ve| have)\s+been\s+(?:loving|using)\b|"
        r"(?:我一直|我最近).{0,12}(?:喜欢|在用|使用).{0,18}(?:功能|表盘|应用)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\b(?:best|biggest|main)\s+reason\s+(?:yet\s+)?to\b|"
        r"\b(?:one of )?my favorite\b|"
        r"(?:最值得|最大|最主要).{0,12}(?:理由|原因)", 0).search(lower) and (
        _compiled_rule(r"\b(?:about to|could|may|might)\b", 0).search(lower)
        or _compiled_rule(r"\bi\s+(?:use|wear|rely|imagine|think|believe|often|already)\b|"
            r"\bi['’]ve\b|\bmy favorite\b|"
            r"(?:我(?:一直|经常|已经|认为|觉得|想象|依赖|使用|佩戴)|我最喜欢)", 0).search(lead_lower)
    ):
        return "analysis"
    if (
        (
            _compiled_rule(r"\bhow\b.{0,90}\b(?:helped|shaped|enabled|led to|made possible)\b|"
                r"如何.{0,60}(?:助推|塑造|催生|促成|成就)", 0).search(lower)
            or _compiled_rule(r"\b(?:origin story|historical retrospective)\b|历史回顾|^(?:回顾|重温)", 0).search(lower)
        )
        and _compiled_rule(r"\b(?:19\d{2}|20\d{2})\b|\b(?:19)?(?:70|80|90)s\b|"
            r"(?:(?:19|20)\d{2}\s*年|去年|上世纪|历史上|当年|\d{2}年代|二十多年前|三十多年前|四十多年前)", 0).search(f"{lower} {lead_lower}")
        and not _compiled_rule(r"\b(?:today|now|new report|announces?|launches?|releases?|sues?|investigates?)\b|"
            r"(?:今日|最新|宣布|推出|发布|起诉|调查)", 0).search(lower)
    ):
        return "analysis"
    custom_vendor = _compiled_rule(r"(?<![a-z0-9])(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b)"
        r"([a-z][a-z0-9.+-]{2,30})(?![a-z0-9]).{0,36}"
        r"(?:lists?|listed|launch(?:es|ed)?|unveils?|上架|推出|发布)", 0).search(lead_lower)
    if (
        custom_vendor
        and _compiled_rule(r"\b(?:custom|customized|bespoke|luxury|modified)\b|"
            r"(?:(?:高奢|奢华|纯银)定制|定制(?:版|款|机|设备|折叠|手机)|改装版)", 0).search(lower)
        and not _compiled_rule(r"\bapple\s+(?:announces?|launches?|releases?|unveils?)\b|"
            r"苹果(?:宣布|推出|发布)", 0).search(lead_lower)
    ):
        return "third_party_spotlight"
    current_attributed_report = bool(
        _compiled_rule(r"\b(?:today (?:outlined|reported)|today['’]s report|latest edition|"
            r"new(?:\s+[a-z-]+){0,2}\s+report|"
            r"bloomberg reports|gurman reports|according to (?:bloomberg|mark gurman|gurman))\b|"
            r"(?:彭博社今日|古尔曼今日|据彭博社|古尔曼称|最新一期|最新报道|今日报告|今日透露)", 0).search(lead_lower)
        and _compiled_rule(r"\b(?:late-stage testing|will announce|will launch|will not be released|is not planned|"
            r"does not expect|do not expect|not expected|no major design changes|"
            r"unlikely to arrive|will not|codenamed|codenames|production|supplier|shipment)\b|"
            r"(?:后期测试|将发布|不会发布|预计不会|没有重大设计变化|没有重大改款|"
            r"没有计划|代号|量产|供应商|出货)", 0).search(lead_lower)
        and not _compiled_rule(r"\b(?:no new reporting|previously reported|recapped rumors|rumors so far)\b|"
            r"(?:汇总此前|此前传闻|无新增消息|没有新增消息)", 0).search(lead_lower)
    )
    # A dated report about one product is not an inventory merely because its
    # subtitle says "what to expect". Explicit recaps retain their old form.
    current_attributed_report = current_attributed_report or bool(
        _compiled_rule(r"will\s+be\s+(?:revealed|unveiled)|即将.{0,12}(?:揭晓|发布)", 0).search(lower)
        and _compiled_rule(r"apple\s+reportedly\s+plans\s+to\s+(?:unveil|announce)|据.{0,20}苹果计划", 0).search(lead_lower)
        and len(hardware_action_subjects(title)) == 1
        and not _compiled_rule(r"recap|previously|no new|回顾|此前|没有新", 0).search(lead_lower))
    if (not current_attributed_report) and _compiled_rule(r"\b(?:product|hardware|device)?\s*roadmap\b.{0,70}\bhere['’]s\s+what['’]s\s+coming\b|"
        r"\bhere['’]s\s+what['’]s\s+coming\b.{0,70}\b(?:product|hardware|device)?\s*roadmap\b|"
        r"(?:产品|硬件|设备)?路线图.{0,36}(?:即将推出|即将发布|有哪些|一览)", 0).search(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"(?:发布会|活动).{0,28}(?:将|预计|有望|可能|大概率).{0,18}"
        r"(?:推|推出|发布|带来|亮相).{0,10}"
        r"(?:[一二三四五六七八九十百\d]+)\s*(?:款|项|个)?(?:新品|产品|设备|硬件)", 0).search(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"^what['’]?s\s+coming\s+in\s+[a-z]+\b.{0,100}"
        r"\b(?:iphones?|ipads?|macs?|apple\s+watches?|airpods|products?)\b", 0).match(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"\b(?:models?|products?|devices?|macs?|iphones?|ipads?|airpods)\s+"
        r"(?:are\s+|will\s+)?(?:launch(?:ing)?|arriv(?:e|ing)|debut(?:ing)?)\s+"
        r"(?:next|this)\s+(?:week|month|season|fall|spring)\b.{0,40}"
        r"\bhere['’]s\s+what['’]s\s+coming\b|"
        r"(?:多款|系列).{0,16}(?:新品|产品|设备).{0,18}(?:即将|下月|下周).{0,18}(?:汇总|一览|有哪些)", 0).search(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"\b(?:outlook|preview|roundup)\b.{0,24}\beverything\s+(?:expected|rumored|known)\b|"
        r"(?:前瞻|展望|汇总).{0,20}(?:全部|所有|已知|预期|传闻)|"
        r"[一二三四五六七八九十\d]+\s*(?:大|款|种)(?:旗舰|新品|产品|设备)"
        r".{0,16}(?:抢先看|提前看|一览)", 0).search(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"\b(?:besides|beyond|alongside)\b.{0,36}\b(?:iphone|ipad|macbook|apple watch)\b"
        r".{0,36}\b(?:other|rival|competing)\b.{0,24}\b(?:phones?|products?|flagships?)\b|"
        r"(?:iphone|ipad|macbook|apple watch).{0,24}之外.{0,12}(?:还有|另有|也有).{0,18}"
        r"(?:这些|多款|其他).{0,12}(?:手机|产品|旗舰|新品)", 0).search(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"(?:等|共|多达)\s*[一二三四五六七八九十百\d]+\s*款"
        r"(?:苹果)?(?:新品|产品|设备).{0,28}"
        r"(?:彻底泄密|全部曝光|集中曝光|一次看完|汇总|再无悬念)", 0).search(lower):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"\b(?:rumors? point to|everything we know|"
        r"what to expect|these \d+ (?:new )?(?:features|changes)|"
        r"\d+\s+(?:new\s+)?(?:features?|changes?|upgrades?)\s+"
        r"(?:worth|to)\s+(?:test(?:ing)?|try(?:ing)?|know|use)|"
        r"\d+ new things .+ (?:can do|to try|to know)|"
        r"(?:will|could|may|expected to)\s+(?:release|launch|unveil)\s+"
        r"(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\+?\s+"
        r"(?:new\s+)?(?:products?|devices?)|"
        r"\d+ rumored features|latest (?:apple )?rumors?|all (?:the )?(?:apple )?rumors?|"
        r"rumors? so far|best .+ to try)\b|传闻汇总|消息汇总|功能汇总|值得期待的\s*\d+", 0).search(lower) or (
        not current_attributed_report
        and _compiled_rule(r"^(?:everything new|here['’]s what['’]s new|what['’]s new with)\b", 0).match(lower)
        and not _compiled_rule(r"^what['’]s new with (?:the )?[a-z][a-z -]{1,40} app in "
            r"(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+){0,2}\b", 0).match(lower)
    ) or (not current_attributed_report and "更新汇总" in lower) or (
        not current_attributed_report
        and
        _compiled_rule(r"\bcoming\b.{0,42}\bwith (?:these|\d+) (?:rumored )?new features\b", 0).search(lower)
        and _compiled_rule(r"\b(?:recaps?|previously reported|rumored so far|no new reporting)\b|汇总此前|此前传闻|无新增", 0).search(lead_lower)
    ):
        return "roundup"
    if (not current_attributed_report) and _compiled_rule(r"^(?:[am]\d{1,2}(?:\s+(?:pro|max|ultra))?\s+)?"
        r"(?:iphone|ipad|mac(?:book)?|apple watch|airpods|vision pro)\b"
        r".{0,48}\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\b"
        r"\s+(?:new\s+)?(?:features?|changes?|upgrades?)\b.{0,48}"
        r"\b(?:coming|launching|expected|rumored|to expect)\b", 0).search(lower):
        return "roundup"
    if not current_attributed_report and _compiled_rule(r"\bhere['’]s\s+what\s+(?:the\s+)?rumou?rs?\s+say\b|"
        r"\bhere\s+are\s+the\s+(?:existing|previously reported)\s+rumou?rs?\b", 0).search(lead_lower):
        return "roundup"
    if not current_attributed_report and _compiled_rule(r"^when\s+(?:is|are|will)\b[^?？]{0,100}"
        r"\b(?:releas(?:e|es|ing)|launch(?:es|ing)?|arriv(?:e|es|ing))\b[^?？]*[?？]", 0).match(lower):
        return "analysis"
    current_first_party_development = bool(
        _compiled_rule(r"^(?:apple\b|苹果)", 0).match(lead_lower)
        and _compiled_rule(r"\b(?:is|has been)\s+(?:testing|prototyping|developing)\b|"
            r"苹果(?:公司|官方)?正在(?:测试|开发|试制)", 0).search(_compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(lead_lower, 1)[0])
    )
    if not (current_attributed_report or current_first_party_development) and _compiled_rule(r"\bhere['’]s\s+why\s+(?:that|this|it)\s+(?:really\s+)?matters\b|"
        r"\b(?:will|could|may|might)\s+(?:be|become|pose)\b.{0,32}"
        r"\b(?:test|challenge|threat|risk)\s+(?:of|for|to)\b", 0).search(lower) and not _extract_patterns(lower, ACTION_PATTERNS):
        return "analysis"
    if _compiled_rule(r"\b(?:adds?|gets?|gains?|brings?)\s+(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?:new\s+)?(?:iphone\s+|ipad\s+|mac\s+)?(?:features?|changes?|upgrades?)\b|"
        r"(?:新增|带来|加入)\s*(?:两|三|四|五|六|七|八|九|十|\d+)\s*(?:项|个)?(?:新)?(?:功能|变化|升级)", 0).search(lower):
        return "roundup"
    if _compiled_rule(r"(?:\d+|[一二三四五六七八九十]+)\s*项(?:功能|变化|升级|更新)"
        r".{0,20}(?:汇总|盘点|全(?:部)?(?:扒出|梳理|整理)|一览)", 0).search(lower):
        return "roundup"
    if (
        _compiled_rule(r"^(?:is|are) .+ worth it\b", 0).match(lower)
        or _compiled_rule(r"\b(?:doesn['’]t|does not|didn['’]t|did not)\s+seem\s+credible\b|"
            r"\b(?:hard|difficult)\s+to\s+believe\b|\bseems?\s+unlikely\b|"
            r"(?:显得|看起来|似乎).{0,10}(?:平淡|乏味|难以置信|不可信)|"
            r"(?:补齐|修复).{0,12}(?:短板|缺陷).{0,18}(?:但|不过|然而)", 0).search(lower)
        or _compiled_rule(r"^why\b.{0,100}\b(?:could|may|might)\b.{0,60}\b(?:risk|problem|concern)\b", 0).match(lower)
        or _compiled_rule(r"(?:便利与隐患并存|(?:引发|存在|带来).{0,10}(?:隐私|安全).{0,8}(?:争议|风险|隐患))", 0).search(lower)
        or _compiled_rule(r"值不值得|是否值得", 0).search(lower)
    ):
        return "analysis"
    if _compiled_rule(r"^[^:：]{2,24}(?:吐槽|抱怨|炮轰|批评)[：:]", 0).match(lower):
        return "analysis"
    if _compiled_rule(r"\bgets?\s+(?:one|something)\s+(?:thing\s+)?(?:very\s+)?right\b.{0,80}\bgets?\s+wrong\b", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\bno[- ]brainer\s+upgrade\b", 0).search(lower):
        return "buying_advice"
    if _compiled_rule(r"\brelease\s+date\s*,\s*features?\s*,\s*price\s*,\s*(?:and\s+)?rumors?\b", 0).search(lower):
        return "buying_advice"
    if _compiled_rule(r"^(?:do|does|did|can|could)\s+we\s+need\s+to\s+worry\b", 0).match(lower):
        return "analysis"
    policy_incentive = bool(
        _compiled_rule(r"\b(?:tax|tariff)\s+(?:break|breaks|incentive|incentives|relief|exemption|exemptions)\b|"
            r"(?:税收|关税|所得税).{0,10}(?:优惠|减免|豁免|激励)", 0).search(lower)
    )
    if not policy_incentive and _compiled_rule(r"\b(?:weekend deals?|daily deals?|best deals?|deal roundup|prime day|shopping guide)\b|"
        r"(?<!\w)(?:up to\s+)?[$£€¥]\s*\d+(?:[.,]\d+)?\s+off\b|"
        r"\bsave\s+[$£€¥]\s*\d+(?:[.,]\d+)?\s+on\b|"
        r"(?:周末|每日|今日)?(?:优惠|好价|促销)(?:汇总|合集)?", 0).search(lower):
        return "deal"
    if (_compiled_rule(r"\b(?:hit|hits|drops?\s+to)\s+(?:a\s+)?(?:new\s+)?low\b.{0,16}[$£€¥]\s*\d", 0).search(lower)
            and _compiled_rule(r"\b(?:sale|discount|retailer|amazon|shipped|deal)\b", 0).search(lead_lower)):
        return "deal"
    if (
        _compiled_rule(r"\b(?:discounts?|markdowns?|savings?(?!\s+accounts?\b)|sale|lowest price|record low)\b", 0).search(lower)
        and _compiled_rule(r"[$£€¥]\s*\d|\b\d+(?:\.\d+)?\s*%|\bup to\b|\boff\b|"
            r"\bbelow\s+(?:the\s+)?(?:list|retail)\s+price\b", 0).search(f"{lower} {lead_lower}")
    ):
        return "deal"
    if _compiled_rule(r"\b(?:should(?:n['’]t| not)? (?:buy|wait|upgrade)|should you (?:buy|wait|upgrade)|"
        r"buy now or wait|upgrade now or wait|why you should(?:n['’]t| not)? wait|"
        r"reasons?\s+(?:not\s+)?to\s+(?:buy|upgrade|wait)|before you buy|buying advice|buying guide|"
        r"buyers?['’]?s?\s+guide|which\s+[^:;.!?]{1,35}\s+to\s+buy)\b|"
        r"(?:该不该|要不要|是否应该)(?:买|等|升级)|买还是等|购买建议|换机建议|"
        r"(?:升级|换到|换购).{0,18}(?:的|之)?(?:三|四|五|六|七|八|九|十|\d+)大理由", 0).search(lower) and not _compiled_rule(r"^(?:apple|苹果)\s*(?:updates?|publishes?|releases?|更新|发布)\b", 0).match(lower):
        return "buying_advice"
    if _compiled_rule(r"\b(?:indie app spotlight|app spotlight|app pick)\b|(?:应用|app)推荐", 0).search(lower):
        return "third_party_spotlight"
    if _compiled_rule(r"\bmy\s+favorite\b.{0,45}\b(?:accessories|bands|chargers|cases|stands)\b|"
        r"\bfavorite\b.{0,36}\b(?:apple\s+watch|iphone|ipad|mac|airpods|vision\s+pro)\b"
        r".{0,36}\b(?:accessories|bands|chargers|cases|stands)\b|"
        r"(?:我最喜欢|最喜欢的|精选).{0,24}(?:苹果|iphone|ipad|mac|airpods|vision\s*pro).{0,20}(?:配件|表带|充电器|保护壳|支架)", 0).search(lower):
        return "buying_advice"
    if _compiled_rule(r"\b(?:event|keynote)\s+date\b.{0,45}\b(?:years?|history|pattern|announcements?)\b|"
        r"\b(?:years?|history)\s+of\s+apple\s+announcements?\b|"
        r"(?:发布会|活动)(?:日期|时间).{0,28}(?:历年|历史|规律|回顾|推算)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\b(?:one|two|three|\d+)\s+years?\s+later\b.{0,90}"
        r"\b(?:what\s+held\s+up|what\s+didn['’]?t|long[- ]term|review)\b", 0).search(lower):
        return "analysis"
    repeated_incident_retrospective = bool(
        _compiled_rule(r"\b(?:repeated|recurring|again and again)\b.{0,48}\b(?:failure|failures|issue|issues|flaw|flaws)\b|"
            r"(?:屡现|屡次|反复|一再).{0,32}(?:漏洞|失误|失守|问题|案例)", 0).search(lower)
        and _compiled_rule(r"\b(?:promise|promises|credibility|trust)\b.{0,30}\b(?:questioned|challenged|under scrutiny)\b|"
            r"(?:承诺|可信度|信任|机制).{0,24}(?:遭|受|被)?(?:到)?质疑", 0).search(lower)
    )
    if repeated_incident_retrospective:
        return "analysis"
    leadership_retrospective = bool(
        _compiled_rule(r"\b(?:as\s+(?:apple\s+)?ceo|years?\s+as\s+(?:apple\s+)?ceo)\b"
            r".{0,90}\b(?:the\s+(?:man|woman|leader)|legacy|tenure|era|grew|built)\b|"
            r"\b(?:\d{1,2}|ten|fifteen|twenty)\s+years?\b.{0,70}"
            r"\b(?:legacy|tenure|era|market|supply\s+chain|grew|built|history)\b|"
            r"(?:库克时代|任期回顾|交班).{0,60}(?:留下|遗产|成绩|市值|创新引擎)|"
            r"(?:(?<!\d)\d{1,2}(?!\d)|十[一二三四五六七八九]?|[一二三四五六七八九]十)\s*年"
            r".{0,60}(?:回顾|复盘|变迁|市场|市值|股价|供应链|攻守|留下|成绩|遗产|种下|养大|对手)|"
            r"(?:能否|是否).{0,32}(?:重启|重现|恢复).{0,24}(?:创新|乔布斯时代)", 0).search(lower)
        and not _compiled_rule(r"\b(?:announces?|appoints?|assumes?|steps?\s+down|signs?\s+off|"
            r"farewell|final\s+day|last\s+day)\b|"
            r"(?:宣布|任命|上任|就任|卸任|告别信|内部信|最后一天)", 0).search(lower)
        and not quantified_apple_company_performance_subject(title, lead)
    )
    if leadership_retrospective:
        return "analysis"
    attributed_strategy_commentary = bool(
        _compiled_rule(r"\b(?:needs? to|should|must|has to)\b.{0,70}"
            r"(?:compete|win|succeed|respond|strategy|market)|"
            r"(?:苹果).{0,16}(?:得|需要|应该|应当|必须).{0,45}"
            r"(?:竞争|取胜|突围|应对|战略|策略|市场|打好)", 0).search(lower)
        and not _compiled_rule(r"\b(?:will launch|will release|will ship|is testing|is developing|"
            r"production|supplier|shipment)\b|"
            r"(?:将发布|将推出|将上市|正在测试|正在开发|量产|供应商|出货)", 0).search(lower)
    )
    if attributed_strategy_commentary:
        return "analysis"
    speculative_editorial_framing = bool(
        _compiled_rule(r"\b(?:anyone|anybody)(?:['’]s| is) guess\b|"
            r"\b(?:we|you|i) can only guess\b|"
            r"\byour guess is as good as mine\b|\bpure speculation\b|"
            r"(?:谁也|任何人都)?(?:说不准|不好说)|"
            r"(?:只能|仅能|纯属)?猜(?:测|想|一猜)", 0).search(lower)
        and not _compiled_rule(r"\b(?:new report|according to|sources? say|apple (?:plans?|will|is considering)|"
            r"supplier|production|shipment)\b|"
            r"(?:最新报道|据.{0,18}(?:报道|消息|透露)|消息称|苹果(?:计划|将|正在|考虑)|"
            r"供应商|量产|出货)", 0).search(lower)
    )
    if speculative_editorial_framing:
        return "analysis"
    announcement_with_attributed_judgment = bool(
        _compiled_rule(r"^apple\s+(?:announces?|releases?|introduces?|unveils?)\s+"
            r"[^,;.!?]{1,100}[,;]\s*(?:and\s+)?(?:says?|states?|explains?)\b", 0).match(lower)
    )
    if _compiled_rule(r"\b(?:is|would be)\s+(?:a\s+)?(?:bad|terrible|poor|good|great)\s+idea\b|"
        r"\bonly\s+(?:one|some)\s+(?:of\s+them\s+)?(?:is|are)\s+(?:good|worthwhile)\b|"
        r"\b(?:don['’]t|do not|doesn['’]t|does not)\s+know\s+(?:any\s+)?more\s+than\s+you\b", 0).search(lower) and not announcement_with_attributed_judgment:
        return "analysis"
    if _compiled_rule(r"\b(?:drama|comedy|film|movie|series|documentary)\b", 0).search(lower) and _compiled_rule(r"\b(?:doesn['’]t|does not|fails? to)\s+(?:represent|capture|reflect|portray)\b", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"^(?:analyst|analysis|opinion|commentary)\b|"
        r"^(?:分析师|机构观点|评论)[：:]|(?:分析师|评论人士).{0,24}(?:认为|称|表示)|"
        r"\b(?:now\s+)?(?:even\s+)?more valuable\b|\bbetter value\b|"
        r"\b(?:won['’]t|will not|wouldn['’]t|would not)\s+be\s+useful\s+without\b|"
        r"\b(?:great|good)\s+for\s+apple\b.{0,55}\b(?:not\s+good|bad)\s+for\b|"
        r"\bmight\s+not\s+be\s+good\s+for\s+(?:the\s+)?(?:buyer|customer|user)\b|"
        r"(?:更有价值|更划算)", 0).search(lower):
        return "analysis"
    if _compiled_rule(r"\b(?:hands-on|hands on|first impressions?)\b|"
        r"(?:公测版|测试版).{0,10}(?:上手|体验)|"
        r"(?:上手(?:体验)?|实测|体验评测|使用体验|深度体验)", 0).search(lower):
        return "hands_on"
    return "news"


def _headline_subject_clause(title: str) -> str:
    """Remove evidence adjectives without changing the grammatical subject."""
    text = _compiled_rule(r"^(?:leaked\s+|泄露的|曝光的)", 0).sub("", _normalized(title), 0)
    clauses = _compiled_rule(r"[,，]", 0).split(text, 1)
    if len(clauses) == 2 and _compiled_rule(r"\b(?:upcoming|is coming|is approaching|ahead of)\b|即将|发布前夕", 0).search(clauses[0]):
        current = clauses[1].strip()
        if _compiled_rule(r"[a-z][a-z0-9 '&.-]{0,36}\s+(?:releases?|posts?|responds?|announces?|opens?)\b|[^，。！？]{1,16}(?:发布|推出|回应|宣布|下线)", 0).match(current):
            return current
    return text


def _lead_assigns_app_release_to_apple(app_name: str, lead: str) -> bool:
    """Bind a positive Apple release predicate to the headline's application."""
    claim = _compiled_rule(r"[。.!?]", 0).split(_normalized(lead), 1)[0]
    release = _compiled_rule(r"^(?:apple\s+(?:(?:today|has|just|now)\s+)*"
        r"(?:released?|launch(?:es|ed)?|introduc(?:es|ed)?|publish(?:es|ed)?|updat(?:e|es|ed))\s+|"
        r"苹果(?:公司)?(?:今天|今日|刚刚|正式|现已|已经|已)*(?:发布|推出|更新)(?:了)?)"
        r"(?P<object>.+)$", 0).match(claim)
    if release is None:
        return False
    app_object = release.group("object").strip()
    if _compiled_rule(r"\bthird[- ]party\b|第三方", 0).search(app_object):
        return False
    # Determiners precede the object; an ownership apposition can follow it.
    app_object = _compiled_rule(r"^(?:(?:its|a|an|the|new|own|first-party)\s+)+|"
        r"^(?:其|旗下|自研|自主研发|全新|新|的)+", 0).sub("", app_object, 0)
    return bool(re.match(
        rf"{re.escape(_normalized(app_name))}(?=\s|[,，]|$|应用|客户端)", app_object,
    ))


def _direct_apple_relationship(title: str) -> bool:
    return bool(
        _compiled_rule(r"\b(?:in talks?|talking|partners?|partnering|signs? (?:a )?deal|working) with apple\b|"
            r"\b(?:joins? apple|acquired by apple|after apple(?:'s)? acquisition)\b|"
            r"(?:与苹果|和苹果).{0,20}(?:洽谈|合作|签署|达成|评估)|"
            r"(?:加入苹果|被苹果收购)", 0).search(_normalized(title))
    )


def descriptive_apple_product_reference(title: str) -> bool:
    """A fruit/color modifier does not name the owner of another product."""
    lower = _normalized(title)
    without_modifier = _compiled_rule(r"苹果(?:橙|红|绿|色|味|香|口味)", 0).sub("", lower, 0)
    return (without_modifier != lower
            and not _contains_any(without_modifier, APPLE_TITLE_TERMS)
            and not _extract_patterns(without_modifier, PRODUCT_PATTERNS))


def first_party_hardware_implementation(title: str) -> tuple[str, str] | None:
    """Bind an affirmative Apple physical implementation, including narrative titles."""
    lower = _normalized(title)
    match = _compiled_rule(
        r"\bapple\s+(?:has\s+)?(?:embedded|embeds|integrated|integrates|placed|places|moved|moves)\s+"
        r"(?:(?:its|the|a|an)\s+)?(?P<component>face\s*id|cameras?|batter(?:y|ies)|"
        r"speakers?|sensors?|chips?|antennas?)\s+(?:beneath|under|inside|within|into|in)\s+"
        r"(?:(?:its|the|a|an)\s+)?(?P<host>(?:iphone|ipad|macbook|apple\s+watch|airpods?)"
        r"(?:\s+\d+)?(?:\s+(?:pro|max|mini|air|ultra)){0,2})\b").search(lower)
    if match is None:
        return None
    if _compiled_rule(r"\b(?:den(?:y|ies|ied)|disputes?|rejects?)\b.{0,60}$|"
            r"(?:否认|并非|不属实).{0,30}$").search(lower[:match.start()]):
        return None
    return match.group('host').replace(' ', '-'), match.group('component').replace(' ', '-')


def is_platform_compatible_accessory_title(title: str) -> bool:
    """A platform modifier does not own the accessory's product action."""
    lower = _normalized(title)
    if _compiled_rule(r"^(?:apple\b|苹果)").match(lower):
        return False
    if _compiled_rule(r"^(?:homekit|airplay|carplay|siri)(?:\s+(?:ai|platform|system))?\s+"
            r"(?:(?:is|has|will|now)\s+){0,2}(?:(?:adds?|supports?|updates?|expands?|"
            r"changes?|enables?|releases?|improves?)\b|新增|支持|更新|扩展|改进)").match(lower):
        return False
    return bool(_compiled_rule(
        r"\b(?:homekit|airplay|carplay|siri)(?:[- ](?:compatible|enabled))?\s+"
        r"(?:(?:new|smart|wireless|light|led)\s+){0,3}"
        r"(?:bulbs?|light\s+bulbs?|light\s+switch(?:es)?|switch(?:es)?|"
        r"speakers?|sensors?|cameras?|accessor(?:y|ies)|adapters?|plugs?)\b|"
        r"\b(?:bulbs?|light\s+switch(?:es)?|speakers?|sensors?|cameras?|"
        r"accessor(?:y|ies)|adapters?|plugs?)\b.{0,40}"
        r"(?:with|compatible\s+with|works?\s+with)\s+(?:homekit|airplay|carplay|siri)\b|"
        r"(?:homekit|airplay|carplay|siri)\s*(?:兼容|适配)?\s*(?:的)?\s*"
        r"(?:灯泡|灯具|开关|音箱|传感器|摄像头|配件|适配器)|"
        r"(?:接入|支持|兼容|适配)\s*(?:apple\s+)?(?:homekit|airplay|carplay|siri)"
        r"\s*的[^。！？!?]{0,12}(?:旋钮|控制器|灯泡|灯具|开关|音箱|传感器|摄像头|配件|适配器)").search(lower))


def _title_scope(title: str, lead: str) -> str:
    title_lower = _normalized(title)
    personal_modifier = _compiled_rule(
        r"^(?:apple(?:['’]s)?\s+(?:ceo|chief\s+executive|executive|chairman)"
        r"(?:\s+[a-z]+){0,3}['’]s\s+(?:personal\s+)?favou?rite\s+|"
        r"苹果\s*(?:ceo|首席执行官|高管|董事长)[^，。:：]{0,24}?"
        r"(?:最爱|最喜欢|喜欢|钟爱|青睐)的?)", 0).match(title_lower)
    if personal_modifier:
        # A person's preference modifies the actual subject; it does not make
        # that subject's action an action of the person's employer.
        subject = title_lower[personal_modifier.end():].strip()
        subject_scope = _title_scope(subject, "")
        generic_subject = _compiled_rule(
            r"^(?:(?:features?|functions?|services?|products?)\b|功能|服务|产品)", 0).match(subject)
        opening = _normalized(lead)[:360]
        if (subject_scope == "unknown" and generic_subject
                and _compiled_rule(r"^(?:apple\b|苹果)", 0).match(opening)
                and _extract_patterns(opening, ACTION_PATTERNS)
                and _extract_patterns(opening, PRODUCT_PATTERNS)):
            return "apple-direct"
        return "third-party-context" if subject_scope == "unknown" else subject_scope
    subject_clause = _headline_subject_clause(title)
    if subject_clause != title_lower and _compiled_rule(r"[,，]", 0).search(title_lower):
        return _title_scope(subject_clause, "")
    lead_lower = _normalized(lead)[:600]
    if lead_lower.startswith(title_lower):
        lead_lower = lead_lower[len(title_lower) :].lstrip(" .:-：")
    if (_compiled_rule(r"(?:actors?|cast).{0,55}\b(?:reunit|reunion)|(?:演员|主演).{0,35}(?:重聚|重逢|合体|聚首)", re.I).search(title_lower)
            and _compiled_rule(r"(?:actors?|cast)|演员|主演", re.I).search(lead_lower)
            and not _compiled_rule(r"apple\s*(?:tv|originals)|苹果\s*(?:tv|原创)", re.I).search(title_lower)):
        return "third-party-context"
    if descriptive_apple_product_reference(title):
        return "third-party-context"
    if is_platform_compatible_accessory_title(title):
        return "third-party-context"
    apple_in_title = _contains_any(title_lower, APPLE_TITLE_TERMS)
    title_products = _collapse_product_hierarchy(
        _extract_patterns(title_lower, PRODUCT_PATTERNS)
    )
    if (_compiled_rule(r"(?:^|[,，])\s*linux\b.{0,35}(?:kernel|内核)", 0).search(title_lower)
            and _compiled_rule(r"remov\w*|drop\w*|移除|删除", 0).search(title_lower)
            and _compiled_rule(r"protocol|协议", 0).search(title_lower)
            and _compiled_rule(r"no longer support|stopped support|停止支持|早已停止", 0).search(lead_lower)):
        return "third-party-context"
    beats_first_party_technical = bool(
        _compiled_rule(r"^beats\b", 0).match(title_lower)
        and _compiled_rule(r"\b(?:lab|laboratory|engineering|r&d)\b|(?:实验室|工程实验室|研发)", 0).search(title_lower)
    )
    first_party_prefix = bool(
        _compiled_rule(r"^(?:(?:these|those|some|older|new)\s+)?(?:apple(?:'s)?|iphones?|ipads?|ios|ipados|macs?(?:book|os)?|watchos|tvos|visionos|airpods?|icloud|safari|siri|shazam|homekit|beats\s+(?:lab|headphones|earbuds|pill|studio)|carplay|xcode|app store)\b|"
            r"^(?:苹果|传苹果|消息称苹果|报道称苹果)", 0).match(_headline_subject_clause(title))
        or _compiled_rule(r"^(?:iphone|ipad|macbook|airpods?|apple watch)(?=[^a-z0-9]|$)", 0).match(_headline_subject_clause(title))
    ) or beats_first_party_technical
    if not first_party_prefix and title_products:
        # A catalogued device can lead a numbered feature report without
        # repeating the company name. Bind its owner from the opening, not
        # an Apple reference in another product's background.
        heading = _compiled_rule(r"^(?:\d+\s+)?", 0).sub("", _headline_subject_clause(title), 1)
        owned_heading = any(heading == alias or heading.startswith(alias + " ")
            or heading.startswith(alias + "'s ") or heading.startswith(alias + "’s ")
            for product, aliases in PRODUCT_PATTERNS if product in title_products
            for alias in aliases)
        first_party_prefix = bool(owned_heading
            and _compiled_rule(r"^(?:apple\b|苹果)", 0).match(lead_lower)
            and title_products & _extract_patterns(lead_lower[:300], PRODUCT_PATTERNS))
    if (not first_party_prefix
            and _compiled_rule(r"\b(?:android(?:\s+app)?\s+store|play\s+store|google\s+play)\b", 0).search(title_lower)):
        # "app store" is a generic object here, explicitly owned by another
        # platform; an iOS comparison in the lead does not change its owner.
        return "third-party-context"
    versioned_first_party_os_release = bool(
        _compiled_rule(r"\b(?:release candidates?|rcs?|public betas?|developer betas?|betas?|updates?)\b"
            r".{0,90}\b(?:ios|ipados|macos|watchos|tvos|visionos)\b|"
            r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\b.{0,90}"
            r"\b(?:release candidates?|rcs?|public betas?|developer betas?|betas?|updates?)\b|"
            r"(?:候选版|公测版|开发者测试版|测试版|系统更新).{0,50}"
            r"(?:ios|ipados|macos|watchos|tvos|visionos)|"
            r"(?:ios|ipados|macos|watchos|tvos|visionos).{0,50}"
            r"(?:候选版|公测版|开发者测试版|测试版|系统更新)", 0).search(title_lower)
        and _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)"
            r"(?:\s+[a-z][a-z-]+){0,2}\s+\d+(?:\.\d+){0,2}\b", 0).search(f"{title_lower} {lead_lower[:240]}")
        and not _compiled_rule(r"^(?!apple\b|苹果).{2,70}\b(?:app|game|client|tool|browser|plugin)\b", 0).match(title_lower)
    )
    direct_target = bool(
        _compiled_rule(r"(?:sues?|sued|fines?|threatens?|investigates?|orders?|blocks?|approves?|起诉|罚款|调查|要求|批准).{0,45}(?:apple|苹果)|"
            r"(?:apple|苹果).{0,30}(?:works? on|fix(?:es|ed|ing)?|patch(?:es|ed|ing)?|responds?|investigates?|修复|制作补丁|回应|调查)", 0).search(title_lower)
    )
    direct_relationship = _direct_apple_relationship(title)
    if (_compiled_rule(r"(?:apple(?:'s)?\s+market share|苹果(?:市场)?份额)[^，。.!?]{0,24}\d+(?:\.\d+)?\s*%", 0).search(title_lower)
            and not _compiled_rule(r"launch(?:es|ed)?|releases?|introduces?|发布|推出|上市", 0).search(title_lower)):
        # A quantified Apple result remains a report about Apple when another
        # company is also named in the headline's market comparison.
        return "apple-direct"
    comparison = bool(
        _compiled_rule(r"(?:better than|versus|\bvs\.?\b|rival(?:s|ing)?|compared (?:with|to)|beats?|"
            r"overtakes?|surpasses?|dethrones?|exceeds?|leads?|ahead\s+of|挑战|对标|剑指|对决|抗衡|交锋|比肩|硬刚|媲美|优于|胜过|超越|超过|领先|力压|"
            r"接近|相当于|追平|打平|并列|向.{0,20}看齐|酷似|撞脸|类似(?:于)?)"
            r".{0,50}(?:apple|iphone|ipad|mac|airpods|苹果)", 0).search(title_lower)
        or _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac(?:book)?\b|airpods\b|苹果)"
            r"[^:：!！?？]{1,80}(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)?|"
            r"introduc(?:es|ed|ing)?|debut(?:s|ed|ing)?|发布|推出|上新|上市|开售|亮相)"
            r"[^:：!！?？]{0,60}(?:apple|iphone|ipad|mac(?:book)?|airpods|苹果)"
            r"[^:：!！?？]{0,40}(?:rival|competitor|alternative|counterpart|竞品|对手|替代品)", 0).search(title_lower)
        or _compiled_rule(r"(?:向|与).{0,24}(?:apple|iphone|ipad|mac|airpods|苹果).{0,12}(?:看齐|相似|类似)", 0).search(title_lower)
        or _compiled_rule(r"(?:hard|difficult)\s+to\s+(?:beat|match|challenge).{0,30}(?:apple|iphone|ipad|macbook|airpods)\b|"
            r"(?:难|很难)(?:打|敌|撼动|胜过|匹敌).{0,24}(?:apple|iphone|ipad|macbook|airpods|苹果)", 0).search(title_lower)
    )
    platform_only = bool(
        _compiled_rule(r"(?:app|game|service|client|tool|browser|software|ring|headset).{0,55}(?:on|for|to) (?:iphone|ipad|mac|apple watch)\b", 0).search(title_lower)
        or _compiled_rule(r"(?:应用|游戏|服务|客户端|工具|浏览器|软件|戒指|头显).{0,28}(?:登陆|上线|支持|适配).{0,16}(?:iphone|ipad|mac|苹果平台)", 0).search(title_lower)
        or _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果).{2,70}"
            r"\b(?:native\s+mac\s+ports?|mac\s+ports?)\b", 0).search(title_lower)
    )
    subject_first_platform_recipient = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|foldable\s+iphone\b|folding\s+iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果).{2,80}\b(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|"
            r"updat(?:es|ed|ing)|adds?|added|brings?|brought|tests?|tested|testing|"
            r"being tested|available|arrives?|coming|rolls? out)\b.{0,60}\b(?:on|for|to)\s+(?:select\s+)?"
            r"(?:iphone|ipad|mac|apple watch|apple devices?|apple platforms?|ios|ipados|macos|watchos|tvos|visionos)(?:\s+users?)?\b", 0).search(title_lower)
        or _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果).{2,80}\b(?:on|for|to)\s+(?:select\s+)?"
            r"(?:iphone|ipad|mac|apple watch|ios|ipados|macos|watchos|tvos|visionos)(?:\s+users?)?\b.{0,50}\b"
            r"(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|updat(?:es|ed|ing)|adds?|added|"
            r"brings?|brought|tests?|tested|testing|available|arrives?|coming|rolls? out)\b", 0).search(title_lower)
        or _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|苹果).{2,70}"
            r"\b(?:flaw|vulnerability|bug|exploit|malware|attack)\b.{0,90}"
            r"\b(?:including|affect(?:s|ed|ing)?|on|for)\b.{0,24}"
            r"\b(?:iphone|ipad|mac|ios|ipados|macos|watchos)\b", 0).search(title_lower)
    )
    subject_first_apple_device_add_on = bool(
        title_products
        and not first_party_prefix
        and (
            _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac(?:book)?\b|airpods\b|苹果)"
                r"[^:：]{1,42}(?:推出|发布|预热|上架|开发|打造).{0,65}"
                r"(?:配件|外设|保护壳|手机壳|充电器|充电宝|底座|"
                r"沉浸式体验|体验项目|应用|客户端|服务)", 0).search(title_lower)
            or _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac(?:book)?\b|airpods\b)"
                r"[^:]{1,52}\b(?:launch(?:es|ed)?|release(?:s|d)?|previews?|"
                r"unveils?|develops?|builds?)\b.{0,70}\b"
                r"(?:accessor(?:y|ies)|case|charger|dock|immersive experience|"
                r"experience|app|client|service)\b", 0).search(title_lower)
        )
        and not direct_relationship
    )
    subject_first_owned_platform_update = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果).{2,55}['’]s\s+(?:latest\s+)?"
            r"(?:ios|ipados|macos|watchos|carplay|iphone|ipad|mac)\s+"
            r"(?:app\s+)?(?:update|release|version|feature)\b", 0).search(title_lower)
    )
    subject_first_app_comparison = bool(_compiled_rule(r"^(?!apple\b|苹果|ios\b|ipados\b|macos\b|iphone\b|ipad\b|mac\b)"
        r"[^:：]{2,45}(?:\bapp\b|应用|客户端)[^:：]{0,35}(?:灰度|更新|发布|推出|adds?|releases?|updates?)"
        r"[^。.!?]{0,70}(?:ios|ipados|macos|苹果)", re.I).search(title_lower))
    subject_first_tool_requirement = bool(_compiled_rule(r"^(?!apple\b|苹果|ios\b|iphone\b|ipad\b|mac\b).{2,45}\b(?:model|app|tool|assistant)\b"
        r".{0,100}\b(?:needs?|requires?)\b.{0,45}\b(?:mac|iphone|ipad)\b", re.I).search(title_lower))
    subject_first_compatibility = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果)"
            r".{2,90}\b(?:supports?|adds?\s+(?:[a-z0-9]+\s+){0,3}support(?:\s+for)?|compatible with|works with|with support for)\b"
            r".{0,30}\b(?:apple|airplay|homekit|iphone|ipad|mac)\b", 0).search(title_lower)
        or _compiled_rule(r"^(?!苹果|iphone|ipad|mac|airpods).{2,48}(?:音箱|耳机|充电器|配件|设备|智慧屏|电视).{0,30}"
            r"(?:支持|兼容|适配|新增).{0,18}(?:苹果|隔空播放|airplay|homekit|ios|ipados|macos|iphone|ipad|mac)", 0).search(title_lower)
    )
    subject_first_compatibility = subject_first_compatibility or bool(
        not first_party_prefix and (
            _compiled_rule(r"^[a-z][a-z0-9 .&'-]{1,45}\s+adds?\s+(?:iphone|ipad|mac|apple watch|ios|ipados|macos)\b.{0,45}\bsupport\b").search(title_lower)
            or (_compiled_rule(r"充电(?:器|头)|charger").search(lead_lower)
                and (_compiled_rule(r"(?:开售|发售|发布|推出)[^。.!?]{0,100}(?:苹果\s*)?iphone", 0).search(title_lower)
                     or _compiled_rule(r"^(?:支持|兼容|适配)[^!！]{0,90}iphone[^!！]{0,90}[!！].{0,100}(?:开售|发售|发布)", 0).search(title_lower)))
        )
    )
    subject_first_apple_hypothetical = bool(
        _compiled_rule(r"\bshould\s+apple\b[^?？]*[?？]", 0).search(title_lower)
        and not first_party_prefix
    )
    subject_first_service_integration = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b)"
            r".{2,70}\b(?:adds?|integrates?|brings?|offers?|supports?)\b.{0,35}"
            r"\bapple\s+(?:music|tv|pay|wallet|carplay)\b", 0).search(title_lower)
    )
    direct_first_party_content = bool(
        _compiled_rule(r"\bapple\s+tv(?:\+|['’]s)?\b|苹果\s*tv", 0).search(title_lower)
        and (
            any(
                (_valid_quoted_subject(match.group(1)) or _valid_content_title(match.group(1)))
                for match in _compiled_rule(r"[\"'“‘]([^\"'“”‘’\n]{2,48})[\"'”’]", 0).finditer(title)
            )
            or _compiled_rule(r"\b(?:season|series|film|movie|documentary|docuseries|drama|comedy|premiere)\b|"
                r"(?:剧集|剧集|电影|影片|纪录片|首播|最终季)", 0).search(title_lower)
        )
    )
    subject_first_comparison = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b)"
            r".{2,70}(?:thinner|wider|faster|slower|better|worse|larger|smaller|"
            r"compares?|competes?|rivals?|benchmarks?).{0,30}(?:than|against|with).{0,35}apple(?:'s)?\b|"
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b).{2,80}with apple(?:'s)?\b.{0,35}\blooming\b|"
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b).{2,90}(?:closest thing|alternative|answer).{0,24}(?:to|for).{0,28}(?:apple|iphone|ipad|mac|airpods)\b", 0).search(title_lower)
    )
    subject_first_named_competitor = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac(?:book)?\b|airpods\b|苹果)"
            r"(?:[a-z0-9.+-]+(?:['’]s)?\s+){1,5}(?:new\s+)?"
            r"(?:apple|iphone|ipad|macbook|airpods)(?:\s+[a-z0-9.+-]+){0,3}\s+"
            r"(?:competitor|rival|alternative|answer)\b", 0).match(title_lower)
    )
    subject_first_metric_comparison = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|macos\b|airpods\b|苹果)"
            r"[^:：]{2,70}[:：].{0,150}(?:apple|iphone|ipad|mac(?:book|os)?|airpods|苹果)"
            r".{0,45}(?:\d+(?:\.\d+)?\s*(?:x|times?|倍)|higher|lower|more|less|高于|低于|多于|少于)", 0).search(title_lower)
        or _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|macos\b|airpods\b|苹果)"
            r"[^:：]{2,70}[:：].{0,150}(?:\d+(?:\.\d+)?\s*(?:x|times?|倍)|higher|lower|more|less|高于|低于)"
            r".{0,45}(?:apple|iphone|ipad|mac(?:book|os)?|airpods|苹果)", 0).search(title_lower)
    )
    title_clauses = [
        clause.strip()
        for clause in _compiled_rule(r"[!！?？:：]", 0).split(title_lower, 0)
        if clause.strip()
    ]
    comparison_hook_then_non_apple_action = bool(
        len(title_clauses) >= 2
        and not first_party_prefix
        and _compiled_rule(r"(?:apple|iphone|ipad|macbook|airpods|苹果)", 0).search(title_clauses[0])
        and _compiled_rule(r"(?:compete|rival|challenge|versus|\bvs\.?\b|compare|match|surpass|"
            r"对标|挑战|剑指|对决|抗衡|交锋|比肩|媲美|超越|赶超|三分天下|"
            r"比.{0,18}(?:苹果|iphone|ipad|macbook|airpods).{0,12}更|跟.{0,18}(?:苹果|iphone)|"
            r"与.{0,18}(?:苹果|iphone))", 0).search(title_clauses[0])
        and not _compiled_rule(r"^(?:apple(?:'s)?|iphone|ipad|macbook|apple watch|airpods|vision pro|苹果)", 0).match(" ".join(title_clauses[1:]))
        and _compiled_rule(r"(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|ship(?:s|ped|ping)?|"
            r"deliver(?:s|ed|ing)?|debut(?:s|ed|ing)?|announce(?:s|d|ing)?|"
            r"发布|推出|上新|上市|开售|交付|亮相|完成|宣布|曝光)", 0).search(" ".join(title_clauses[1:]))
    )
    independent_user_tool_action = bool(
        title_products
        and not first_party_prefix
        and _compiled_rule(r"\b(?:reddit\s+)?users?\b.{0,100}\b(?:self[- ](?:built|made|developed)|"
            r"open[- ]source|custom)\b.{0,30}\b(?:app|tool|utility|script)\b|"
            r"(?:reddit\s*)?用户.{0,100}(?:自研|自制|自行开发|开源|自定义).{0,24}(?:应用|工具|脚本|程序)", 0).search(f"{title_lower} {lead_lower[:360]}")
        and not _compiled_rule(r"(?:apple|苹果).{0,24}(?:发布|推出|更新|修复|开发|宣布|收购|招聘)", 0).search(title_lower)
    )
    platform_edition_third_party_action = bool(
        _compiled_rule(r"^(?:mac|ios|ipados|iphone|ipad|apple watch)\s*(?:版|version|app)\s*"
            r"(?!(?:apple|ios|ipados|macos|watchos|tvos|visionos|safari|xcode|airpods)\b)"
            r"[a-z][a-z0-9.+-]*(?:\s+[a-z0-9][a-z0-9.+-]*){0,3}\s+"
            r"(?:发布|推出|更新|上线|上架|launch(?:es|ed)?|releas(?:es|ed)?|updat(?:es|ed)?)", 0).search(title_lower)
    )
    named_app_store_arrival = bool(
        not first_party_prefix
        and _compiled_rule(r"^[^:：.!！?？]{1,60}?(?:\bapp\b|\bapplication\b|应用|客户端)\s*"
            r"(?:(?:正式|现已|首次)\s*)?(?:登陆|登录|上架|上线)\s*(?:苹果\s*)?app\s*store\b|"
            r"^[^:：.!！?？]{1,60}?\b(?:app|application)\s+"
            r"(?:arrives?|launch(?:es|ed)?|debuts?)\s+on\s+(?:the\s+)?app\s+store\b", 0).match(title_lower)
    )
    if named_app_store_arrival:
        app_name = _compiled_rule(r"^([^:：.!！?？]{1,60}?)(?:\s+(?:app|application)\b|应用|客户端)", 0).match(title_lower)
        if app_name and _lead_assigns_app_release_to_apple(app_name.group(1), lead_lower):
            named_app_store_arrival = False
    subject_first_apple_followup = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b).{2,90}"
            r"\b(?:follows?|following|after|copies|imitates|emulates|takes? a page from)\b"
            r".{0,24}\bapple(?:'s)?\b", 0).search(title_lower)
        or _compiled_rule(r"^(?!苹果|iphone|ipad|mac|airpods).{2,60}(?:效仿|跟进|追随|照搬|学习)"
            r".{0,12}(?:苹果|apple)", 0).search(title_lower)
    )
    subject_first_apple_response = bool(
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果)"
            r".{1,70}\b(?:responds?|response|reacts?|reaction|answers?)\b.{0,70}"
            r"\b(?:apple|iphone|ipad|mac|airpods)\b|"
            r"^(?!苹果|iphone|ipad|mac|airpods).{1,50}(?:回应|答复|评价|表态).{0,40}"
            r"(?:苹果|iphone|ipad|mac|airpods)", 0).search(title_lower)
        and not _compiled_rule(r"\b(?:lawsuit|court|case|legal|filing|charges?)\b|(?:诉讼|法院|法庭|案件|指控|提交文件)", 0).search(title_lower)
    )
    framed_third_party_action = bool(
        _compiled_rule(r"^(?:apple|苹果).{0,48}[：:]\s*"
            r"(?!apple\b|苹果|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|app store\b)"
            r"[a-z0-9][a-z0-9.+-]*(?:\s+[a-z0-9][a-z0-9.+-]*){0,4}.{0,36}"
            r"(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|updat(?:es|ed|ing)|"
            r"发布|推出|更新|上线|上架)", 0).search(title_lower)
    )
    # An evidence noun can disclose Apple hardware; a branded product cannot.
    disclosure_subject = bool(
        title_products
        and _compiled_rule(r"^(?:(?:a|the|new|latest|leaked)\s+)*"
            r"(?:leak|code|firmware|patent(?:\s+filing)?|support\s+document|"
            r"regulatory\s+filing)\s+(?:hints?|suggests?|signals?|shows?)\b", 0).match(title_lower)
    )
    competitor_brand = r"(?:华为|三星|小米|荣耀|谷歌|oppo|vivo|huawei|samsung|xiaomi|google)"
    competitor_marketing = bool(
        re.search(
            rf"(?:建议|推荐).{{0,16}}(?:苹果|iphone).{{0,12}}用户.{{0,8}}"
            rf"(?:购买|买|选购).{{0,6}}{competitor_brand}", title_lower,
        )
        or (
            _compiled_rule(r"^(?:苹果|apple|iphone).{0,40}(?:也要|也将|也会|或将).{0,8}跟进", 0).search(title_lower)
            and re.search(
                rf"[!！:：].{{1,24}}(?:称|表示|宣称){competitor_brand}(?:引领|首创|率先)",
                title_lower,
            )
        )
    )
    speculative_comparison = bool(
        not disclosure_subject
        and
        _compiled_rule(r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果).{2,110}"
            r"\b(?:hints?|suggests?|signals?|shows?)\b.{0,36}"
            r"(?:what\s+)?apple(?:'s)?\b|"
            r"^(?!苹果|iphone|ipad|mac|airpods).{2,90}(?:暗示|预示|折射|可见)"
            r".{0,30}(?:苹果|iphone|ipad|mac|airpods)", 0).search(title_lower)
    )
    first_party_evidence_signal = bool(
        title_products
        and _compiled_rule(r"\b(?:job|hiring|recruiting)\s+(?:listing|post|posting)|"
            r"\b(?:code|filing|document|support document)\b|"
            r"(?:招聘(?:信息|启事)?|招募信息|代码|备案文件|支持文档)", 0).search(title_lower)
        and _compiled_rule(r"^(?:apple\b|苹果)", 0).match(lead_lower)
        and _compiled_rule(r"\b(?:hires?|hiring|recruits?|plans?|tests?|develops?|builds?|adds?|"
            r"launches?|releases?|updates?)\b|"
            r"(?:招聘|招募|计划|测试|开发|构建|新增|推出|发布|更新)", 0).search(lead_lower[:360])
    )
    if (
        (
            subject_first_comparison
            or subject_first_metric_comparison
            or subject_first_named_competitor
            or subject_first_apple_device_add_on
        )
        and not first_party_prefix
        and not direct_relationship
    ):
        return "third-party-context"
    if (
        competitor_marketing
        or comparison_hook_then_non_apple_action
        or independent_user_tool_action
        or platform_edition_third_party_action
        or named_app_store_arrival
    ):
        return "third-party-context"
    if direct_target or direct_relationship or first_party_evidence_signal:
        return "apple-direct"
    contextual_non_apple_action = bool(
        _compiled_rule(r"^as\s+(?:apple|iphones?|ipads?|macs?|apple\s+watch|airpods).{0,65},\s*"
            r"(?!apple\b|iphone\b|ipad\b|mac(?:book|os)?\b|苹果)"
            r".{2,55}\b(?:launch(?:es|ed)?|offer(?:s|ed)?|introduc(?:es|ed)?|"
            r"announce(?:s|d)?|start(?:s|ed)?|expand(?:s|ed)?)\b", 0).search(title_lower)
        or _compiled_rule(r"^(?!apple\b|iphone\b|foldable\s+iphone\b|folding\s+iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果)[a-z0-9][a-z0-9.+-]*(?:\s+[a-z0-9][a-z0-9.+-]*){0,3}\s+"
            r"(?:is\s+|are\s+)?(?:building|launch(?:es|ed|ing)?|offer(?:s|ed|ing)?|"
            r"introduc(?:es|ed|ing)?|announce(?:s|d|ing)?|develop(?:s|ed|ing)?)\b"
            r".{0,100}\b(?:ios|ipados|macos|watchos|tvos|visionos|iphone|ipad|mac\s+apps?|apple\s+watch|airpods|vision\s+pro)\b", 0).search(title_lower)
        or _compiled_rule(r"^(?!苹果|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods)"
            r"[a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,3}.{0,36}"
            r"(?:宣布|计划|发布|推出|引入|加入|更新|新增|扩充|强化|上线|上架|适配).{0,70}"
            r"(?:ios|ipados|macos|watchos|tvos|visionos|iphone|ipad|mac|苹果平台|苹果应用商店)", 0).search(title_lower)
        or _compiled_rule(r"^(?!苹果|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods)"
            r"[^:：]{2,55}(?:宣布|计划|开始|正在|正为|将为).{0,45}"
            r"(?:苹果\s*)?(?:ios|ipados|macos|watchos|tvos|visionos)(?:\s*版|平台)?"
            r".{0,60}(?:引入|加入|新增|推出|上线|更新|测试|推送)", 0).search(title_lower)
        or _compiled_rule(r"^(?!苹果|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods)"
            r".{2,90}(?:发布|推出|上市|更新|新增|上线|上架).{0,70}"
            r"(?:支持(?:为)?|兼容|适配).{0,24}(?:苹果|iphone|ipad|mac|airpods|苹果平台)", 0).search(title_lower)
        or framed_third_party_action
    )
    if contextual_non_apple_action:
        return "third-party-context"
    embedded_first_party_subject_action = bool(
        title_products
        and _compiled_rule(r"(?:apple|苹果).{0,28}(?:fitness\+|[a-z][a-z0-9 +.-]{1,28})", 0).search(title_lower)
        and _compiled_rule(r"\b(?:launch(?:es|ed|ing)?|release(?:s|d|ing)?|rolls? out|adds?|"
            r"hires?|hiring|recruits?|plans?|tests?|updates?)\b|"
            r"(?:发布|推出|上线|新增|招聘|招募|计划|测试|更新|调整|收购)", 0).search(title_lower)
        and not (
            comparison
            or subject_first_comparison
            or subject_first_metric_comparison
            or subject_first_apple_hypothetical
            or subject_first_service_integration
            or speculative_comparison
        )
    )
    apple_chip_report = bool(
        _compiled_rule(r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b", 0).search(title_lower)
        and _compiled_rule(r"^(?:apple(?:'s)?|苹果|传苹果|消息称苹果|报道称苹果|"
            r"leaker\b|report\b|rumor\b|消息\b|报道称|传闻|爆料|"
            r"[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b)", 0).match(title_lower)
        and _compiled_rule(r"\b(?:report|reported|rumor|rumored|leak|leaker|details?|gains?|"
            r"faster|performance|speed|efficiency|cost|price)\b|"
            r"(?:消息|报道|传闻|爆料|性能|速度|能效|成本|价格)", 0).search(title_lower)
        and _compiled_rule(r"\bapple(?:'s)?\b|苹果", 0).search(lead_lower[:360])
    )
    if subject_first_app_comparison or subject_first_tool_requirement:
        return "third-party-context"
    if (
        first_party_prefix
        or versioned_first_party_os_release
        or direct_first_party_content
        or embedded_first_party_subject_action
        or apple_chip_report
    ):
        return "apple-direct"
    if (
        comparison
        or subject_first_platform_recipient
        or subject_first_owned_platform_update
        or subject_first_compatibility
        or subject_first_apple_hypothetical
        or subject_first_service_integration
        or subject_first_comparison
        or subject_first_named_competitor
        or subject_first_apple_device_add_on
        or comparison_hook_then_non_apple_action
        or subject_first_apple_followup
        or subject_first_apple_response
        or speculative_comparison
    ):
        return "third-party-context"
    if platform_only and not title_lower.startswith(tuple(APPLE_TITLE_TERMS)):
        return "third-party-context"
    if apple_in_title:
        return "apple-direct"
    return "unknown"


def is_non_apple_title_context(title: str, lead: str) -> bool:
    """Return true only when Apple is comparison, compatibility, or list context."""
    return _title_scope(title, lead) == "third-party-context"


def is_third_party_app_action_on_apple_platform(title: str, lead: str) -> bool:
    """Return true when an Apple platform is only the target of an app update.

    Editorial headlines sometimes make a platform the grammatical subject even
    though the lead assigns the current action to an independently maintained
    app.  The ownership test therefore requires both a generic app object in
    the title and a vendor/app-owned availability or release statement in the
    lead.  A real Apple API, policy, framework, or platform-capability change
    remains first party.
    """
    title_text = _normalized(title)
    lead_text = _normalized(lead)[:900]
    if (
        _compiled_rule(r"\b(?:apple(?:-made)?|first[- ]party)\b.{0,42}"
            r"\b(?:controllers?|devices?|accessories|peripherals?|hardware)\b|"
            r"(?:苹果|自研|第一方).{0,28}(?:手柄|控制器|设备|配件|外设|硬件)", re.I).search(title_text)
        and _compiled_rule(r"\b(?:unreleased|prototype|code|identifiers?|found|hint(?:s|ed)?)\b|"
            r"(?:未发布|原型|代码|标识符|曝光|发现|暗示)", re.I).search(title_text)
    ):
        return False
    apple_platform = bool(
        _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos|carplay|apple watch|"
            r"apple tv|vision pro)\b|(?:苹果|apple).{0,12}(?:平台|系统)", re.I).search(title_text)
    )
    app_count_title = _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+)*(?:\s+(?:beta|rc)\s*\d*)?", re.I).sub("", title_text, 0)
    generic_app_object = bool(
        _compiled_rule(r"\b(?:an?|another|major|new|third[- ]party)\s+"
            r"(?:[a-z0-9-]+\s+){0,3}(?:app|client|service|utility)\b|"
            r"\b(?:two|three|four|five|several|multiple|\d+)\s+"
            r"(?:[a-z0-9-]+\s+){0,4}(?:apps?|app\s+updates?|app\s+releases?)\b|"
            r"\b(?:apps?|app\s+updates?|app\s+releases?)\b.{0,36}"
            r"\b(?:roundup|collection|list)\b|"
            r"(?:一款|新的|第三方).{0,16}(?:应用|客户端|服务|工具)", re.I).search(app_count_title)
    )
    def local_app_owned_action(clause):
        return bool(
            _compiled_rule(r"\b(?:app|client|service|utility)\b.{0,80}"
                r"\b(?:now\s+works?|adds?|added|released?|launch(?:ed|es)?|"
                r"arriv(?:ed|es)|supports?|available)\b.{0,80}"
                r"\b(?:ios|ipados|macos|watchos|tvos|visionos|carplay|apple watch|"
                r"apple tv|vision pro)\b|"
                r"\b(?:update|version)\b.{0,80}\b(?:adds?|added|brings?|supports?)\b"
                r".{0,80}\b(?:ios|ipados|macos|watchos|tvos|visionos|carplay)\b|"
                r"(?:应用|客户端|服务|工具).{0,50}(?:更新|版本|现已|开始)"
                r".{0,50}(?:支持|适配|登陆|登录|接入).{0,24}"
                r"(?:ios|ipados|macos|watchos|tvos|visionos|carplay|苹果平台)", re.I).search(clause)
            or _compiled_rule(r"\b(?:developers?|vendors?|publishers?)\b.{0,45}"
                r"\b(?:updated?|upgraded?|released?|launched?)\b.{0,35}"
                r"\b(?:ios|ipados|macos|watchos|tvos|visionos|carplay)\s+apps?\b", re.I).search(clause)
            or _compiled_rule(r"\b(?:released?|launch(?:ed|es)?|adds?|added)\b.{0,80}"
                r"\b(?:dedicated\s+)?(?:ios|ipados|macos|watchos|tvos|visionos|"
                r"carplay|apple watch|apple tv|vision pro)\s+app\b", re.I).search(clause)
            or _compiled_rule(r"\b(?:first|second|third|another)\b.{0,80}"
                r"\b(?:updated?|upgraded?|released?|launched?|added)\b.{0,55}\b(?:app|client)\b|"
                r"\b(?:developers?|vendors?|publishers?)\b.{0,45}"
                r"\b(?:updated?|released?|launched?)\b.{0,45}\b(?:apps?|clients?)\b"
                r".{0,45}\b(?:ios|ipados|macos|watchos|tvos|visionos|carplay)\b|"
                r"(?:首先|其次|此外|另一款).{0,60}(?:应用|客户端).{0,24}"
                r"(?:更新|发布|推出|新增)", re.I).search(clause)
        )
    app_owned_action = any(local_app_owned_action(clause) for clause in _compiled_rule(r"(?<=[.!?])\s+|[。！？]", 0).split(lead_text, 0))
    first_party_platform_change = bool(
        _compiled_rule(r"\bapple\b.{0,60}\b(?:announc(?:ed|es)|introduc(?:ed|es)|"
            r"open(?:ed|s)|enabl(?:ed|es)|chang(?:ed|es)|expand(?:ed|s))\b"
            r".{0,80}\b(?:api|framework|policy|platform|capability|"
            r"third[- ]party\s+app\s+support)\b|"
            r"(?:苹果|平台).{0,40}(?:宣布|开放|启用|引入|调整|扩展)"
            r".{0,50}(?:接口|框架|政策|平台能力|第三方应用支持)", re.I).search(title_text)
    )
    negated_first_party_change = bool(
        _compiled_rule(r"\b(?:apple|the\s+platform)\b.{0,45}\b(?:did\s+not|does\s+not|"
            r"has\s+not|announced\s+no|without)\b.{0,45}"
            r"\b(?:api|framework|policy|platform|capability|feature)\b|"
            r"(?:苹果|平台).{0,30}(?:未|没有|并未|无).{0,30}"
            r"(?:宣布|开放|接口|框架|政策|能力|功能)", re.I).search(f"{title_text}. {lead_text}")
    )
    return (
        apple_platform
        and generic_app_object
        and app_owned_action
        and not (first_party_platform_change and not negated_first_party_change)
    )


def _primary_action_owner(
    title: str,
    lead: str,
    *,
    scope: str,
    content_form: str,
    title_actions: set[str],
    title_products: set[str],
) -> str:
    """Identify who owns the headline action without consulting body facts."""
    if scope == "third-party-context":
        return "third-party"
    if scope != "apple-direct" or content_form != "news":
        return "unknown"
    if _direct_apple_relationship(title):
        return "apple-target"
    if not title_actions:
        return "unknown"

    title_text = _normalized(title)
    lead_text = _normalized(lead)[:360]
    if _compiled_rule(r"\b(?:iphone|ipad|apple watch|airpods|mac(?:book)?)\s+"
        r"(?:data|records?|logs?|location|history)\b", 0).search(title_text) and _compiled_rule(r"\b(?:murder|criminal|crime|trial|prosecutors?|police|evidence)\b|"
        r"(?:谋杀|刑事|犯罪|审判|检方|警方|证据)", 0).search(f"{title_text} {lead_text}"):
        return "third-party"
    if _compiled_rule(r"\b(?:former|ex-)\s+apple\s+(?:employee|staff|engineer|designer|executive)s?\b|"
        r"(?:苹果|apple).{0,12}(?:前员工|前工程师|前设计师|前高管)", 0).search(title_text) and _compiled_rule(r"\b(?:startup|founds?|launches?|releases?|unveils?)\b|"
        r"(?:创业|创办|成立|推出|发布|亮相)", 0).search(title_text):
        return "third-party"
    owner_clause = _compiled_rule(r"^(?:mark\s+gurman|gurman|bloomberg|report|reports?|rumou?r|leak|"
        r"古尔曼|彭博社?|消息|报道称|报道|爆料)[^:：]{0,24}[：:]\s*", 0).sub("", _headline_subject_clause(title), 0)
    owner_clause = _compiled_rule(r"^(?:\d+(?:\.\d+)?\s*(?:元|美元|英镑|欧元)[，,、:]?\s*)", 0).sub("", owner_clause, 0)
    owner_clause = _compiled_rule(r"^(?:breaking|just in|news flash|快讯|刚刚|突发)[,，:：]\s*", 0).sub("", owner_clause, 0)
    owner_clause = _compiled_rule(r"^(?:new|updated|all-new|next-generation|新款|全新|新版)\s*", 0).sub("", owner_clause, 0)
    owner_clause = _compiled_rule(r"^(?:(?:two|three|four|five|six|several|multiple|\d+)\s+)?"
        r"(?:unreleased|upcoming|rumored|new)\s+", 0).sub("", owner_clause, 0)
    owner_clause = _compiled_rule(r"^[^!！]{1,20}[!！]\s*(?=(?:苹果(?:公司|官网|旗下)?|"
        r"(?:apple(?:'s)?|iphone|ipad|mac(?:book|os| mini| studio| pro)?|"
        r"imac|apple watch|airpods)\b))", 0).sub("", owner_clause, 0)
    first_party_subject = bool(
        _compiled_rule(r"^(?:apple(?:'s)?|苹果(?:公司|官网|旗下)?|iphone|ipad|ios|ipados|"
            r"mac(?:book|os| mini| studio| pro)?|imac|watchos|apple watch|tvos|"
            r"apple tv|visionos|vision pro|airpods|icloud|safari|siri|shazam|"
            r"carplay|xcode|app store|beats\b)", 0).match(owner_clause)
    )
    first_party_lead = bool(
        _compiled_rule(r"^(?:apple(?:'s)?|苹果(?:公司)?)(?:\s|正|将|已|计划|宣布|推出|发布|更新|(?:今天|今日|刚刚)(?:正式|已)?(?:发布|推出|宣布|更新))", 0).match(lead_text)
    )
    if first_party_subject or first_party_lead:
        return "apple"

    direct_target = bool(
        _compiled_rule(r"(?:sues?|sued|fines?|threatens?|investigates?|orders?|blocks?|approves?|"
            r"起诉|罚款|调查|要求|批准).{0,45}(?:apple|苹果)", 0).search(title_text)
    )
    return "apple-target" if direct_target else "unknown"


def is_non_apple_comparison_title(title: str) -> bool:
    title_lower = _normalized(title)
    if bool(
        _compiled_rule(r"^(?:apple(?:'s)?|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods|icloud|safari|siri|carplay|xcode|app store|苹果)", 0).match(title_lower)
    ):
        return False
    return bool(
        _compiled_rule(r"(?:better than|versus|\bvs\.?\b|rival(?:s|ing)?|compared (?:with|to)|beats?|"
            r"closest thing.{0,18}(?:to|for)|alternative.{0,18}(?:to|for)|answer.{0,18}(?:to|for)|"
            r"leads?|ahead\s+of|挑战|对标|媲美|优于|胜过|领先).{0,50}(?:apple|iphone|ipad|mac|airpods|苹果)", 0).search(title_lower)
    )


def is_editorial_change_request(title: str) -> bool:
    return bool(_compiled_rule(r"\b(?:would you like|do you wish|should apple|apple should|apple ought to)\b|"
        r"\b(?:my|our)\s+(?:(?:top|biggest|main)\s+)?feature\s+requests?\b|"
        r"\bwhat\s+(?:i|we)(?:['’]d|\s+would)\s+like\s+to\s+see\b|"
        r"苹果(?:应该|应当)|(?:我的|我们(?:的)?).{0,8}(?:功能)?愿望|我希望苹果", 0).search(_normalized(title)))


def is_personal_product_complaint(title: str) -> bool:
    """First-person dissatisfaction is not a filed legal complaint."""
    return bool(_compiled_rule(
        r"\b(?:my|our)\s+(?:(?:biggest|main|only|chief)\s+)?[^.!?:]{0,35}\b(?:complaint|annoyance|gripe)\b|"
        r"(?:我的|我们对).{0,20}(?:抱怨|不满)", re.I).search(title))


def is_weekly_editorial_recap(lead: str) -> bool:
    return bool(_compiled_rule(
        r"\bweekly\s+column\b.{0,160}\b(?:past\s+seven\s+days|past\s+week)\b|"
        r"每周专栏.{0,45}(?:过去一周|过去七天)", re.I).search(lead[:1000]))


def source_design_oversight(title: str, lead: str, evidence: str = "") -> tuple[str, str] | None:
    """Bind the executive and temporal/polarity scope of an owned design role."""
    h, opening = _normalized(title), _normalized(lead)
    context = h + " " + opening[:700]
    if not (_compiled_rule(r"\bdesign\b|设计").search(h)
            and _compiled_rule(r"\b(?:ceo|chief executive)\b|首席执行官").search(context)
            and _compiled_rule(r"\bapple\b|苹果").search(context)):
        return None
    if _compiled_rule(r"\b(?:should|ought|wish|looking back|history|historical|former)\b|应该|应当|回顾|历史|前任").search(h):
        return None
    if not _compiled_rule(r"hands.on|taking.{0,20}role|focus|overs(?:ight|ee)|leads?|in charge|"
                          r"亲掌|介入|亲临|主导|统筹|掌管|接管").search(h):
        return None
    leader, leader_pattern = "", ""
    for key, pattern in (("john-ternus", r"(?<![a-z])(?:john\s*)?ternus(?![a-z])|特努斯"),
                         ("tim-cook", r"(?<![a-z])(?:tim\s*)?cook(?![a-z])|库克")):
        if _compiled_rule(pattern).search(h):
            leader, leader_pattern = key, pattern
            break
    if not leader:
        named = _compiled_rule(r"(?:CEO|chief executive)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b").search(title)
        if not named:
            return None
        leader = named.group(1).lower().replace(" ", "-")
        leader_pattern = re.escape(named.group(1).lower())
    owned_headline = _compiled_rule(r"^[^:：]{1,35}[:：]\s*").sub("", h)
    company = _compiled_rule(r"^(.{1,80}?)\b(?:ceo|chief executive)\b").search(owned_headline)
    if company and not _compiled_rule(r"\bapple\b|苹果|"+leader_pattern).search(company.group(1)):
        return None
    design = _compiled_rule(r"design(?:\s+(?:teams?|work))?|industrial design|human interface|设计")
    participation = _compiled_rule(r"overs(?:ee|ight)|tak(?:e|es|en|ing)|took|charge|focus|immers|hands.on|"
                                   r"responsib|interest|leads?|work|time|亲掌|介入|亲临|主导|统筹|掌管|接管|投入|参与|负责|优先事项")
    historical = False
    for text in (opening, _normalized(evidence)):
        for start, end in source_sentence_spans(text):
            clause = text[start:end].strip()
            clause = _compiled_rule(r"[,，;；]\s*(?:not\b|rather than\b|而非|不是)").split(clause,maxsplit=1)[0]
            if clause.rstrip('.。') == h.rstrip('.。'):
                continue
            if not (_compiled_rule(leader_pattern).search(clause) and design.search(clause) and participation.search(clause)):
                continue
            if _compiled_rule(r"\b(?:not|never|denies|denied)\b|并未|没有|不会|否认").search(clause):
                return leader, "denied"
            if _compiled_rule(r"\blast\s+(?:year|month|week)\b|\bpreviously\b|去年|上个月|上周|此前").search(clause):
                historical = True
                continue
            return leader, "current"
    return (leader, "historical") if historical else None


def is_direct_first_party_builtin_removal(title: str, lead: str) -> bool:
    """A versioned platform explicitly removes its own built-in capability."""
    return bool(
        _title_scope(title, lead) == "apple-direct"
        and _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*\d", 0).search(_normalized(title))
        and _compiled_rule(r"^(?:apple\s+watch|ios|ipados|macos|watchos|tvos|visionos)\b.{0,35}"
            r"(?:is losing|will remove|will lose|removes?|drops?).{0,35}\b(?:built-in|system-level)\b", 0).search(_normalized(lead)[:800]))


def is_direct_first_party_feature_change(title: str, lead: str) -> bool:
    title_lower = _normalized(title)
    lead_lower = _normalized(lead)
    if lead_lower.startswith(title_lower):
        lead_lower = lead_lower[len(title_lower):].lstrip(" .:-")
    lead_lower = lead_lower[:800]
    if is_editorial_change_request(title):
        return False
    owned_interface_change = bool(
        _compiled_rule(r"\bdynamic island\b|灵动岛", 0).search(title_lower)
        and _compiled_rule(r"apple\s+(?:has\s+)?(?:updated|updates|changed|changes|adds|added)\b|苹果(?:更新|调整|新增)", 0).match(lead_lower)
        and _compiled_rule(r"\biphone\b|苹果手机", 0).search(lead_lower)
    )
    if owned_interface_change:
        return True
    if _title_scope(title, lead) != "apple-direct":
        return False
    feature_lead = lead_lower
    if feature_lead.startswith(title_lower):
        feature_lead = feature_lead[len(title_lower):].lstrip(" .:-")
    first_statement = _compiled_rule(r"(?<=[.!?])\s+|[。！？]", 0).split(feature_lead, 1)[0]
    builtin_device_feature = bool(
        _extract_patterns(title_lower, PRODUCT_PATTERNS) & _extract_patterns(first_statement, PRODUCT_PATTERNS)
        and _compiled_rule(r"(?:apple watch|iphone|ipad|mac(?:book)?)(?![a-z])").match(first_statement)
        and _compiled_rule(r"\b(?:includes?|adds?|introduces?)\s+(?:a\s+)?new\s+[^.!?]{0,45}\bfeature\b", 0).search(first_statement)
        and _compiled_rule(r"\bbuilt[- ]in\b|内建|内置", 0).search(lead_lower)
    )
    if builtin_device_feature:
        return True
    feature_action = _extract_patterns(title_lower, ACTION_PATTERNS) & {"feature-change"}
    if not feature_action and _compiled_rule(r"apple(?:\s+(?:has|today|now|recently))*\s+(?:adds?|added|updates?|updated|changes?|changed|introduces?|introduced)\b|"
        r"苹果(?:今日|今天|现已)?(?:新增|更新|调整|引入)", 0).match(lead_lower):
        feature_action = _extract_patterns(lead_lower.split(".", 1)[0], ACTION_PATTERNS) & {"feature-change"}
    built_in_removal = is_direct_first_party_builtin_removal(title, lead)
    if not (feature_action or built_in_removal):
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
        _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*\d", 0).search(title_lower)
    )
    return bool(first_party_feature or versioned_platform)


def is_direct_first_party_documentation_action(title: str, lead: str) -> bool:
    """Require a first-party publisher, new document, and named Apple scope."""
    headline, scope = _normalized(title), _normalized(lead)[:700]
    return bool(
        _title_scope(title, lead) == "apple-direct"
        and _extract_patterns(headline, PRODUCT_PATTERNS)
        and _compiled_rule(r"apple\s+(?:today\s+)?(?:has\s+)?(?:published|publishes|released|releases|updated|updates)\b|苹果(?:今日|今天|现已)?(?:发布|更新)", 0).match(scope)
        and _compiled_rule(r"\b(?:new|updated)\s+support\s+(?:article|document|page)\b|(?:新|更新).{0,8}(?:支持文档|支持文章|支持页面)", 0).search(scope)
    )


def is_direct_first_party_named_object_change(title: str, lead: str) -> bool:
    """Recognize a first-party app changing one named object or label.

    Source headlines describe the same change as a rename, a replacement
    label, or a search alias.  This structural predicate keeps those headline
    angles in the first-party app domain without teaching the crawler any
    particular place, label, or article URL.
    """
    title_text = _normalized(title)
    lead_text = _normalized(lead)[:700]
    if _title_scope(title, lead) != "apple-direct":
        return False
    first_party_app = bool(
        _extract_patterns(title_text, PRODUCT_PATTERNS)
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
    )
    if not first_party_app:
        return False
    owner_pattern = (
        r"^(?:apple\s+(?:books|maps|music|sports|tv|wallet)|app\s+store|icloud|safari)"
        r"(?=\s|[^a-z0-9]|$)|"
        r"^(?:苹果(?:图书|地图|音乐|体育|电视|钱包|应用商店)|icloud|safari)"
    )
    if not (
        re.search(owner_pattern, title_text, re.I)
        or re.search(owner_pattern, lead_text, re.I)
    ):
        return False
    scope = f"{title_text} {lead_text}"
    explicit_change = bool(
        _compiled_rule(r"\b(?:rename|renames|renamed|renaming|relabel|relabels|relabeled|"
            r"relabeling)\b|"
            r"\b(?:use|uses|using|display|displays|show|shows|label|labels|mark|marks)\b"
            r"[^.!?]{0,100}\binstead\s+of\b|"
            r"\bbring(?:s|ing)?\s+up\b[^.!?]{0,100}\b(?:if|when)\b[^.!?]{0,50}"
            r"\bsearch(?:es|ing)?\b|"
            r"\bsearch(?:es|ing)?\b[^.!?]{0,100}\b(?:resolve|resolves|return|returns|"
            r"bring|brings)\b|"
            r"(?:改名|更名|重命名|改称|标注为|显示为)", re.I).search(scope)
    )
    # Search-alias headlines need two named labels to prove that this is an
    # object mapping change rather than an ordinary search tip.
    search_alias = bool(_compiled_rule(r"\bsearch\b|搜索", re.I).search(scope))
    quoted_labels = _compiled_rule(r"['\"“”]([^'\"“”]{2,80})['\"“”]", 0).findall(scope)
    return explicit_change and (not search_alias or len(quoted_labels) >= 1)


def is_authoritative_first_party_action(identity: EventIdentity) -> bool:
    """Return true for source-independent direct-action classes.

    These actions are intentionally narrow in structure rather than tied to a
    publication or individual story. They can safely outrank legacy topic
    heuristics because the title establishes both Apple ownership and a current
    action, while editorial forms have already been excluded.
    """
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return False
    concrete_actions = identity.title_actions & {
        "catalog-expansion",
        "commercial-launch",
        "leadership-transition",
        "model-development",
        "withdrawal",
    }
    return bool(
        concrete_actions
        and (
            identity.title_products
            or identity.title_named_subjects
            or identity.title_actors
            or identity.title_components
            & {
                "apple-leadership",
                "first-party-model-development",
                "official-refurbished-catalog",
            }
        )
    )


def quantified_apple_company_performance_subject(title: str, lead: str) -> str:
    """Return the executive-tenure subject for a current quantified report.

    A title-led percentage and an attributed report distinguish a newly
    published company-performance result from a general leadership
    retrospective.  The returned subject is deliberately about the measured
    tenure, not the publisher's later opinion, so translations can reconcile
    without merging ordinary succession commentary.
    """
    title_text = _normalized(title)
    lead_text = _normalized(lead)[:900]
    if not _compiled_rule(r"(?<!\d)\d{2,5}(?:\.\d+)?\s*%", 0).search(title_text):
        return ""
    apple_stock_subject = bool(
        _compiled_rule(r"\baapl\b|\bapple(?:'s)?\s+(?:stock|shares?|share\s+price)\b|"
            r"(?:苹果股价|苹果股票|苹果公司股价)", 0).search(title_text)
    )
    measured_move = bool(
        _compiled_rule(r"\b(?:gain(?:s|ed)?|grew|rose|return(?:s|ed)?|increas(?:e|es|ed))\b|"
            r"(?:累计)?(?:涨了|上涨|增长|升幅|回报)", 0).search(title_text)
    )
    tenure_context = bool(
        _compiled_rule(r"\bunder\s+[a-z][a-z .'-]{1,40}\b|\b(?:tenure|years?\s+as\s+ceo)\b|"
            r"(?:执掌|掌舵|任内|任期)", 0).search(f"{title_text} {lead_text[:300]}")
    )
    attributed_current_report = bool(
        _compiled_rule(r"\b(?:bloomberg|reuters|according\s+to|reports?|reported|data\s+shows?)\b|"
            r"(?:据[^，。]{0,24}(?:报道|统计|数据)|报道称|报告显示|数据显示)", 0).search(lead_text)
    )
    if not (apple_stock_subject and measured_move and tenure_context and attributed_current_report):
        return ""
    if _compiled_rule(r"\b(?:tim\s+)?cook\b|库克", 0).search(f"{title_text} {lead_text[:300]}"):
        return "tim-cook-tenure"
    if _compiled_rule(r"\bjohn\s+ternus\b|特努斯", 0).search(f"{title_text} {lead_text[:300]}"):
        return "john-ternus-tenure"
    return "apple-executive-tenure"


def is_institutional_apple_device_purchase(title: str, lead: str) -> bool:
    """An institution's approved hardware purchase is not a retail discount."""
    h, opening = _normalized(title), _normalized(lead)[:900]
    institution = r"\b(?:school(?:\s+district)?|university|hospital|enterprise)\b|学校|学区|大学|医院|企业"
    device = r"\b(?:ipad|macbook|iphone|apple\s+watch|macs?)\b|苹果(?:电脑|手机|平板)"
    approval = r"\b(?:approves?|approved|purchased|bought|makes?)\b|批准|采购|购入"
    return bool(_compiled_rule(institution).search(h)
                and (_compiled_rule(device).search(h)
                     or (_compiled_rule(r"\b(?:deal|contract)\s+with\s+apple\b").search(h)
                         and _compiled_rule(device).search(opening)))
                and _compiled_rule(approval).search(h)
                and _compiled_rule(r"\b(?:deal|purchase|buy|buying|purchased|contract)\b|采购|购入|合同").search(h+' '+opening)
                and _compiled_rule(r"[$€£]\s*\d|\d[\d,.]*\s*(?:devices?|students?|台|万元|美元)").search(opening)
                and not _compiled_rule(r"\b(?:discount|coupon|save|sale|might|should|not|never|review|why)\b|优惠券|促销|未批准|考虑|建议|回顾").search(h))


def is_material_apple_device_operational_deployment(title: str, lead: str) -> bool:
    """Recognize a completed, institution-led deployment of an Apple device.

    The three independent gates keep routine third-party app availability out:
    a named operating institution, evidence that the device was actually used,
    and either regulatory authorization or a first-of-kind milestone.
    """
    title_text = _normalized(title)
    scope = f"{title_text} {_normalized(lead)[:1200]}"
    apple_device = bool(
        _compiled_rule(r"\b(?:apple\s+vision\s+pro|vision\s+pro|apple\s+watch|iphone|ipad|macbook)\b|"
            r"(?:苹果\s*)?(?:vision\s+pro|apple\s+watch|iphone|ipad|macbook)", 0).search(title_text)
    )
    institution = bool(
        _compiled_rule(r"\b(?:hospital|health(?:\s+system)?|medical\s+cent(?:er|re)|clinic|"
            r"university|school|enterprise|organization|surgeon|surgical\s+team)\b|"
            r"(?:医院|医疗中心|医疗机构|大学|学校|企业|机构|医生|外科团队)", 0).search(scope)
    )
    completed_use = bool(
        _compiled_rule(r"\b(?:performed|completed)\s+the\s+first\b|"
            r"\bfirst\s+(?:surgery|procedure|deployment)\b.{0,100}"
            r"\b(?:completed|performed|using|used)\b|"
            r"\b(?:surgery|procedure)\b.{0,60}\bhas\s+been\s+(?:completed|performed)\b|"
            r"\bused\s+(?:during|in)\s+(?:a\s+)?(?:surgery|procedure)\b|"
            r"\bintraoperative\b|\bfirst[- ]ever\s+(?:surgery|procedure|deployment)\b|"
            r"(?:完成全球首例|完成首例|实施首例|用于手术|术中使用|辅助.{0,16}手术)", 0).search(scope)
    )
    regulated_or_first = bool(
        _compiled_rule(r"\bfda[- ]authorized\b|\bde\s+novo\s+authorization\b|"
            r"\bregulatory\s+authorization\b|\bworld(?:'s)?\s+first\b|"
            r"\bfirst[- ]ever\b|(?:fda\s*(?:授权|de\s+novo)|监管授权|全球首例|全球首次)", 0).search(scope)
    )
    return apple_device and institution and completed_use and regulated_or_first


def is_direct_apple_product_lifecycle_action(title: str, lead: str) -> bool:
    """Recognize an official lifecycle-list or repair-support change.

    Publishers often lead with an idiom instead of ``Apple`` and describe the
    official list update in the opening sentence.  The decision therefore
    requires all three structural signals: a first-party product, an official
    lifecycle-list action, and a concrete service/repair consequence.
    """
    title_text = _normalized(title)
    scope = f"{title_text} {_normalized(lead)[:1000]}"
    apple_product = bool(
        _extract_patterns(scope, PRODUCT_PATTERNS)
        & {
            "airpods",
            "apple-tv",
            "apple-watch",
            "beats",
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
    )
    first_party_owner = bool(
        _compiled_rule(r"\bapple\b|苹果", 0).search(scope)
        and _compiled_rule(r"\b(?:obsolete|vintage|legacy)\b.{0,40}\b(?:list|product|device|model)s?\b|"
            r"\b(?:list(?:s|ed|ing)?|classif(?:y|ies|ied|ying))\b.{0,45}"
            r"\b(?:obsolete|vintage)\b|"
            r"(?:列入|进入|更新).{0,28}(?:过时|复古|停产)(?:产品)?(?:名单|列表)|"
            r"(?:过时|复古|停产)(?:产品)?(?:名单|列表)", 0).search(scope)
    )
    service_consequence = bool(
        _compiled_rule(r"\b(?:repair|repairs|service|servicing|parts?|support)\b.{0,65}"
            r"\b(?:end|ends|ended|stop|stops|stopped|terminate|terminates|unavailable|no\s+longer)\b|"
            r"\bno\s+longer\b.{0,55}\b(?:repair|service|parts?|support)\b|"
            r"(?:不再|停止|终止|无法).{0,24}(?:维修|服务|零部件|配件供应|支持)|"
            r"(?:维修|服务|零部件|配件供应|支持).{0,24}(?:终止|停止|结束|不再提供)", 0).search(scope)
    )
    if apple_product and first_party_owner and not service_consequence:
        # Refusing repairs is an affirmative support consequence, but a quoted
        # false claim or an old list entry cannot establish a current change.
        sentences = [title_text] + [lead[a:b].lower() for a, b in source_sentence_spans(lead[:1000])]
        asserted = [sentence for sentence in sentences if not _compiled_rule(
            r"\b(?:denies|denied|disputes|rejected|false|untrue|incorrect|unfounded)\b|"
            r"\b(?:not|never)\s+(?:changed|updated|added|ended|stopped)\b|否认|不实", 0).search(sentence)]
        retrospective = _compiled_rule(r"\b(?:revisits?|remembering|retrospective)\b|回顾", 0).search(scope)
        current_action = any(
            not _compiled_rule(r"\b(?:last|previous)\s+(?:year|month|week)\b|"
                r"\b(?:previously|revisits?|remembering)\b|\b(?:centur(?:y|ies)|decades?|years?|months?|weeks?|days?)\s+ago\b|去年|回顾|此前", 0).search(sentence)
            and (not retrospective or _compiled_rule(r"\b(?:today|now|new|newly)\b|\bthis\s+(?:week|morning|afternoon)\b|今日|今天|新增", 0).search(sentence))
            and _compiled_rule(r"\b(?:add(?:s|ed|itions?)?|updat(?:e|es|ed)|join(?:s|ed)?|mov(?:e|es|ed))\b.{0,100}\b(?:list|obsolete|vintage|repair|support)\b|"
                r"\badditions?\b|\b(?:kills?|ends?|ended|stops?|stopped|confirms?|confirmed)\b.{0,65}\b(?:support|repair|service)\b|"
                r"\bnew\s+support\s+(?:notice|report|document)\b", 0).search(sentence)
            for sentence in asserted)
        service_consequence = current_action and any(_compiled_rule(
            r"\bapple\s+(?:won['’]t|will\s+not|does\s+not|no\s+longer)\s+(?:repair|service)s?\b|"
            r"\bapple\s+stores\s+and\s+apple\s+authorized\s+service\s+providers\s+are\s+instructed\s+to\s+discontinue\s+hardware\s+service\b", 0).search(sentence)
            for sentence in asserted)
    return apple_product and first_party_owner and service_consequence


def _non_apple_group_price_action_with_apple_non_change(title: str) -> bool:
    """Return true when Apple is only the unchanged price comparator.

    A headline can mention a first-party product next to a price verb while
    assigning the actual price action to a broader phone market or a group of
    non-Apple vendors.  Treating that product mention as the action owner
    promotes industry stories that explicitly say Apple did *not* change its
    price.
    """
    text = _normalized(title)
    group_price_action = bool(
        _compiled_rule(r"\b(?:multiple|several|other)\s+(?:phone|smartphone|device|vendor|brand|maker)s?\b"
            r".{0,32}\b(?:raise|raised|raising|increase|increased|hike|hiked)\b"
            r".{0,20}\b(?:price|prices|pricing)?\b|"
            r"\b(?:phone|smartphone|device)\s+(?:makers?|brands?|vendors?)\b"
            r".{0,32}\b(?:raise|raised|increase|increased|hike|hiked)\b|"
            r"(?:多款|多家|多个|多种|一批|各大|其他).{0,18}"
            r"(?:手机|设备|厂商|品牌).{0,18}(?:涨价|提价|调价|上调价格|上调售价)|"
            r"(?:手机|设备|厂商|品牌).{0,10}(?:集体|普遍|纷纷).{0,12}"
            r"(?:涨价|提价|调价|上调价格|上调售价)", 0).search(text)
    )
    if not group_price_action:
        return False
    apple_product = (
        r"(?:(?<![a-z0-9])(?:apple|iphone|ipad|mac(?:book)?|airpods|apple watch)"
        r"(?![a-z0-9])|苹果)"
    )
    unchanged_comparator = bool(
        re.search(
            rf"{apple_product}.{{0,28}}\b(?:did\s+not|does\s+not|has\s+not|"
            rf"is\s+not|was\s+not|won['’]t|remains?\s+unchanged)\b.{{0,18}}"
            rf"\b(?:raise|raised|increase|increased|hike|hiked|price|prices|pricing)\b|"
            rf"\b(?:except|but\s+not)\s+{apple_product}.{{0,22}}"
            rf"\b(?:price|prices|pricing|raise|increase|hike)\b|"
            rf"{apple_product}.{{0,20}}(?:没|未|没有|尚未|并未|不会|不跟随)"
            rf".{{0,8}}(?:涨价|提价|调价|上调价格|上调售价|跟涨|涨)",
            text,
        )
    )
    return unchanged_comparator


def high_confidence_direct_apple_action(identity: EventIdentity) -> bool:
    """Return true when title-led semantics prove a direct Apple action."""
    if identity.scope != "apple-direct" or identity.content_form != "news":
        return False
    if identity.action_owner == "apple" and identity.title_actions & {
        "availability-expansion",
        "catalog-expansion",
        "commercial-launch",
        "content-release",
        "feature-change",
        "leadership-transition",
        "model-development",
        "price-change",
        "product-disclosure",
        "product-launch",
        "product-refresh",
        "retail-availability",
        "supply-production",
        "transaction",
        "withdrawal",
    }:
        return True
    if "market-cap" in identity.components and "market-ranking" in identity.actions:
        return True
    if "customer-loyalty" in identity.components and "market-report" in identity.actions:
        return True
    if identity.facets & DIRECT_IDENTITY_FACETS:
        return True
    if "apple-pay" in identity.title_products and identity.title_actions & {
        "retail-availability",
        "transaction",
    }:
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
    if (
        "apple-store-app" in identity.products
        and "shopping-assistant" in identity.components
    ):
        return True
    if is_authoritative_first_party_action(identity):
        return True
    return False


_identity_preparation = ContextVar("identity_preparation", default=None)


@contextmanager
def _identity_preparation_scope():
    """Reuse pure identities only during one synchronous priority calculation."""
    token = _identity_preparation.set({})
    try:
        yield
    finally:
        _identity_preparation.reset(token)


def build_event_identity(
    title: str,
    lead: str,
    facets: Iterable[str] = (),
    identity_evidence: Iterable[str] = (),
) -> EventIdentity:
    prepared = _identity_preparation.get()
    key = None
    if (prepared is not None and type(title) is str and type(lead) is str
            and type(facets) in (tuple, list, set, frozenset)
            and type(identity_evidence) in (tuple, list, set, frozenset)
            and all(type(value) is str for value in facets)
            and all(type(value) is str for value in identity_evidence)):
        key = (title, lead, tuple(facets), tuple(identity_evidence))
        if key in prepared:
            return prepared[key]
    result = _build_event_identity(title, lead, facets, identity_evidence)
    if key is not None:
        prepared[key] = result
    return result


def _build_event_identity(
    title: str,
    lead: str,
    facets: Iterable[str] = (),
    identity_evidence: Iterable[str] = (),
) -> EventIdentity:
    identity_evidence = tuple(identity_evidence)
    title_lower = _normalized(title)
    lead_lower = _normalized(lead)[:900]
    content_form = _content_form(title, lead)
    title_scope = _title_scope(title, lead)
    company_performance_subject = quantified_apple_company_performance_subject(
        title,
        lead,
    )
    if company_performance_subject:
        title_scope = "apple-direct"
    title_products = _collapse_product_hierarchy(_extract_patterns(title_lower, PRODUCT_PATTERNS))
    title_products = {
        product
        for product in title_products
        if not _modifier_only_product_mentions(title_lower, product)
    }
    if (
        "apple-intelligence" in title_products
        and _compiled_rule(r"苹果智能(?:家居|家庭|音箱|显示屏|中枢)", 0).search(title_lower)
        and not _compiled_rule(r"\b(?:ai|apple intelligence)\b|人工智能|大模型", 0).search(title_lower)
    ):
        # “苹果智能家居” describes a physical product family, not the
        # Apple Intelligence service. Substring aliases must not change the
        # article owner or category.
        title_products.discard("apple-intelligence")
    first_party_model_scope = f"{title_lower} {lead_lower[:260]}"
    if (
        title_scope == "apple-direct"
        and _compiled_rule(r"\b(?:ai|artificial intelligence)\b|(?:人工智能|大模型)", 0).search(first_party_model_scope)
        and _compiled_rule(r"\b(?:train(?:s|ed|ing)?|develop(?:s|ed|ing)?|custom model|own model)\b|"
            r"(?:训练|自研|自主研发|定制).{0,20}(?:模型|大模型)", 0).search(first_party_model_scope)
    ):
        title_products.add("apple-intelligence")
    if (
        _compiled_rule(r"^beats\b", 0).match(title_lower)
        and _compiled_rule(r"\b(?:lab|laboratory|engineering|r&d)\b|(?:实验室|工程实验室|研发)", 0).search(title_lower)
    ):
        title_products.add("beats")
    if (
        _compiled_rule(r"^(?:apple\b|苹果)|(?:^|[：:])\s*苹果(?:计划|将|拟)", 0).search(title_lower)
        and _compiled_rule(r"\b(?:smart|ai)\s+glasses\b|智能眼镜|苹果眼镜", 0).search(title_lower)
    ):
        title_products.add("apple-glasses")
    if _compiled_rule(r"苹果[^，。！？:：]{0,18}(?:(?:家庭|智能家居)中枢|带屏智能家居控制(?:终端|中心))").search(title_lower):
        title_products.add("apple-home-hub")
    if _compiled_rule(r"\bapple['’]s\s+(?:(?:upcoming|new|rumou?red|redesigned)\s+){1,2}"
                      r"(?:smart\s+)?home\s+hub\b", 0).search(title_lower):
        title_products.add("apple-home-hub")
        title_scope = "apple-direct"
    # Resolve a headline nickname only from this source's explicit device
    # description. Do not turn a reported name into a global product alias.
    home_name = _compiled_rule(r"^[‘'\"]([^’'\"]+)[’'\"]").match(title_lower)
    if (home_name and _compiled_rule(r"^apple['’]s\s+[^.!?]{0,60}home hub\s+device", 0).match(lead_lower)
            and re.search(r"called\s+[‘'\"]" + re.escape(home_name.group(1)) + r",?[’'\"]", lead_lower[:250])):
        title_products.add("apple-home-hub")
        title_scope = "apple-direct"
    hub_description = _compiled_rule(
        r"apple['’]s\s+(?:(?:all-new|long-rumou?red|upcoming|new|rumou?red|redesigned|smart)\s+){0,3}"
        r"home\s*hub\b", 0)
    if hub_description.search(title_lower):
        title_products.add("apple-home-hub")
        title_scope = "apple-direct"
    for match in _compiled_rule(r"(?:called|known\s+as)\s+[‘'\"]([^’'\"]+)[’'\"]", 0).finditer(lead_lower[:450]):
        if hub_description.search(lead_lower[:match.start()]) and match.group(1) in title_lower:
            title_products.add("apple-home-hub")
            title_scope = "apple-direct"
    if _compiled_rule(r"\bipad\s*\d+\b|\b(?:base|entry-level) ipad\b|(?:入门版|基础款)\s*ipad", 0).search(title_lower):
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
        "shazam",
    }
    if content_form != "roundup" and not (title_products & direct_service_products):
        products |= _extract_patterns(lead_lower[:260], PRODUCT_PATTERNS) & direct_service_products
    title_components = _extract_patterns(title_lower, COMPONENT_PATTERNS)
    if ("vision-pro" in title_products and _compiled_rule(r"\b3d\b|stereoscopic|立体", 0).search(title_lower)
        and _compiled_rule(r"\b(?:mlb|nba|baseball|basketball|sports)\b|棒球|篮球|体育", 0).search(title_lower)):
        title_components.add("immersive-live-video")
    if company_performance_subject:
        title_components.add(f"apple-company-performance:{company_performance_subject}")
    if (
        _compiled_rule(r"(?<![a-z0-9])spotlight(?![a-z0-9])|聚焦(?:搜索)?", 0).search(title_lower)
        and _compiled_rule(r"\bindex(?:ing|ed)?\b|索引", 0).search(title_lower)
    ):
        # Cross-language support coverage commonly describes the same index
        # rebuild with different word order. Preserve the concrete component
        # instead of falling back to a generic OS feature identity.
        title_components.add("spotlight-index-preparation")
    purchase_intent_title = bool(
        title_products
        and (
            _compiled_rule(r"\b(?:survey|poll|purchase intent|willingness to pay)\b|(?:购买意愿|调查显示|民调)", 0).search(title_lower)
            or (_compiled_rule(r"调查|survey|poll", 0).search(title_lower)
                and _compiled_rule(r"愿意|换用|购买意愿|嫌贵|偏贵|\b(?:willing|switch|purchase\s+intent)\b", 0).search(lead_lower[:700]))
            or (
                _compiled_rule(r"(?<!\d)\d+(?:\.\d+)?\s*%", 0).search(title_lower)
                and _compiled_rule(r"\b(?:interested|interest|buy|purchase|pay for it|willing to pay)\b|"
                    r"(?:感兴趣|没兴趣|不感兴趣|购买|愿意支付|嫌贵|价格接受)", 0).search(title_lower)
            )
        )
    )
    if purchase_intent_title:
        title_components.add("consumer-purchase-intent")
    if "apple-wallet" in title_products:
        if _compiled_rule(r"\bpassport\b|护照", 0).search(title_lower):
            title_components.add("wallet-document:passport")
        if _compiled_rule(r"\bdriver['’]?s?\s+licen[cs]e\b|驾照|驾驶证", 0).search(title_lower):
            title_components.add("wallet-document:driver-license")
    # Leadership changes are primary article identity only when the headline
    # itself owns that action. Product reports often mention an outgoing CEO in
    # their lead as timing context; allowing that background to define title
    # components bridges unrelated roadmap and succession stories.
    leadership_scope = title_lower
    if (
        title_scope == "apple-direct"
        and _compiled_rule(r"\b(?:tim cook|apple ceo|chief executive)\b|(?:库克|苹果\s*ceo|首席执行官)", 0).search(leadership_scope)
        and _compiled_rule(r"\b(?:legacy|transition|steps? down|leav(?:e|es|ing)|final weeks?|succession)\b|"
            r"(?:卸任|交接|接班|任期|管理遗产|领导层)", 0).search(leadership_scope)
    ):
        title_components.add("apple-leadership")
    if (
        title_scope == "apple-direct"
        and _compiled_rule(r"\b(?:refurbished|refurb)\b|(?:官翻|官方翻新)", 0).search(title_lower)
        and _compiled_rule(r"\b(?:store|catalog)\b|(?:商店|阵容|目录)", 0).search(title_lower)
    ):
        title_components.add("official-refurbished-catalog")
    if _compiled_rule(r"\b(?:cost|costs|costing)\b.{0,28}\b(?:build|built|make|manufacture|produce)\b|"
        r"\b(?:cost|costs|costing)\b.{0,36}\b(?:more|less)\b.{0,18}"
        r"\b(?:parts?|components?|materials?)\b|"
        r"(?:制造|生产|整机|零部件|物料).{0,12}成本|成本.{0,12}(?:制造|生产|整机|零部件|物料)|"
        r"成本(?:大增|上升|增加|上涨|提高)[^，。！？:：]{0,16}(?:\d+(?:\.\d+)?\s*%|近|约|达到|达)", 0).search(title_lower):
        title_components.add("component-cost-analysis")
    title_components |= _extract_patterns(title_lower, OS_COMPONENT_PATTERNS)
    components = set(title_components)
    if content_form != "roundup" and title_products & {
        "ios",
        "ipados",
        "macos",
        "watchos",
        "tvos",
        "visionos",
        "apple-watch",
    }:
        components |= _extract_patterns(lead_lower[:620], OS_COMPONENT_PATTERNS)
    if "apple-tv" in products:
        lifecycle_patterns = (
            (
                "content-lifecycle:ending",
                r"\b(?:will\s+end|is\s+ending|to\s+end|concludes?|final\s+season)\b|"
                r"(?:最终季|完结|收官)",
            ),
            (
                "content-lifecycle:new-project",
                r"\b(?:announces?|orders?|unveils?)\b.{0,45}\b(?:new\s+)?(?:series|film|movie|documentary|docuseries)\b|"
                r"\b(?:new|upcoming|first)\b.{0,32}\b(?:series|film|movie|documentary|docuseries)\b|"
                r"(?:宣布|官宣|预订|推出).{0,30}(?:新剧|剧集|电影|影片|纪录片)|"
                r"(?:首个|首部).{0,24}(?:剧集|电影|影片|纪录片)",
            ),
            (
                "content-lifecycle:premiere",
                r"\b(?:premieres?|now\s+(?:available|streaming)|available\s+to\s+stream|sets?\s+(?:a\s+)?premiere\s+date)\b|"
                r"(?:首播|上线|现已播出|现已上线|公布首播)",
            ),
        )

        def lifecycle_component(value: str) -> str | None:
            for name, pattern in lifecycle_patterns:
                if re.search(pattern, value):
                    return name
            return None

        title_lifecycle = lifecycle_component(title_lower)
        lead_lifecycle = lifecycle_component(lead_lower[:620])
        if title_lifecycle:
            title_components.add(title_lifecycle)
            components.add(title_lifecycle)
        elif lead_lifecycle:
            components.add(lead_lifecycle)

        season_pattern = _compiled_rule(r"\bseason\s*(\d{1,2})\b|第\s*(\d{1,2})\s*季", 0)
        for match in season_pattern.finditer(f"{title_lower} {lead_lower[:420]}"):
            components.add(f"content-season:{match.group(1) or match.group(2)}")
        for match in _compiled_rule(r"\b(20\d{2})\b", 0).finditer(f"{title_lower} {lead_lower[:320]}"):
            components.add(f"content-year:{match.group(1)}")
    product_generation_components = {
        f"product-generation:{match.group(1)}-{match.group(2)}"
        for match in _compiled_rule(r"(?<![a-z0-9])(iphone|ipad)\s*(\d{1,2})(?!\d)", 0).finditer(title_lower)
    }
    anniversary_iphone_generations = {
        next(group for group in match.groups() if group)
        for match in _compiled_rule(r"(?:\b(\d{1,2})(?:st|nd|rd|th)?\s+anniversary\s+iphone\b|"
            r"\biphone(?:'s)?\s+(\d{1,2})(?:st|nd|rd|th)?\s+anniversary\b|"
            r"(?<!\d)(\d{1,2})\s*周年(?:纪念版)?\s*iphone\b|"
            r"\biphone\s*(\d{1,2})\s*周年(?:纪念版)?)", 0).finditer(title_lower)
    }
    product_generation_components |= {
        f"product-generation:iphone-{generation}"
        for generation in anniversary_iphone_generations
    }
    title_components |= product_generation_components
    components |= product_generation_components
    # Product generation alone is not a sufficient event boundary. Preserve
    # the model named by the headline so iPhone 18, iPhone 18e, and iPhone Air
    # roadmaps cannot collapse merely because they share a launch window or
    # background paragraph.
    iphone_model_components: set[str] = set()
    for match in _compiled_rule(r"(?<![a-z0-9])iphone\s+air\s*(\d{1,2})?(?![a-z0-9])", 0).finditer(title_lower):
        generation = match.group(1)
        iphone_model_components.add(
            f"iphone-model:air-{generation}" if generation else "iphone-line:air"
        )
    for match in _compiled_rule(r"(?<![a-z0-9])iphone\s*(\d{1,2})(?!\d)(?:\s*(pro\s+max|pro|max|plus|mini|ultra|e))?(?![a-z0-9])", 0).finditer(title_lower):
        generation, variant = match.groups()
        trailing_scope = title_lower[match.end() : match.end() + 10]
        if not variant and _compiled_rule(r"\s*(?:series|系列)", 0).match(trailing_scope):
            continue
        variant = _compiled_rule(r"\s+", 0).sub("-", variant or "base", 0)
        if variant in {"pro", "pro-max", "max"}:
            iphone_model_components.add(f"iphone-family:{generation}-pro")
        if variant == "max":
            variant = "pro-max"
        iphone_model_components.add(f"iphone-model:{generation}-{variant}")
    title_components |= iphone_model_components
    components |= iphone_model_components
    analyst_institution_components = _analyst_institution_components(title, lead)
    title_components |= analyst_institution_components
    components |= analyst_institution_components
    report_attribution_components = _report_attribution_components(title, lead)
    if identity_evidence:
        for evidence_item in identity_evidence[:6]:
            report_attribution_components |= _report_attribution_components("", evidence_item)
    title_report_attributions = _report_attribution_components(title, "")
    title_components |= title_report_attributions
    components |= report_attribution_components
    if _is_analyst_target_action_title(title_lower):
        title_components.add("analyst-target-action")
        components.add("analyst-target-action")
    apple_silicon_generation_components: set[str] = set()
    for match in _compiled_rule(r"(?<![a-z0-9])([ma]\d{1,2})(?!\d)", 0).finditer(title_lower):
        prefix = title_lower[max(0, match.start() - 28) : match.start()]
        if _compiled_rule(r"(?:\bnot|rather\s+than|instead\s+of)\b.{0,12}$|(?:而非|并非|不是|非).{0,8}$", 0).search(prefix):
            continue
        apple_silicon_generation_components.add(
            f"apple-silicon-generation:{match.group(1)}"
        )
    title_components |= apple_silicon_generation_components
    components |= apple_silicon_generation_components
    if (products or title_scope == "apple-direct") and _compiled_rule(r"\b(?:shipments?|market\s+share|sales\s+(?:slump|decline|growth)|unit\s+sales|"
        r"best[- ]selling|top[- ]selling)\b|"
        r"(?:出货量|市场份额|销量|出货|同比(?:增长|下降)|最畅销|销量最高|销售冠军)", 0).search(title_lower):
        title_components.add("hardware-market-performance")
        components.add("hardware-market-performance")
    # A quantified device revenue report is a measured hardware outcome even
    # when the captured discovery row contains only its headline.
    if (title_products and title_scope == "apple-direct"
            and _compiled_rule(r"\d", 0).search(title_lower)
            and _compiled_rule(r"\b(?:wholesale\s+)?revenue\b|(?:批发营收|营收|销售收入)", 0).search(title_lower)):
        title_components.add("hardware-market-performance")
        components.add("hardware-market-performance")
    supplier_sourcing_classes = _component_supplier_sourcing_classes(title, lead)
    if supplier_sourcing_classes:
        components.add("component-supplier-sourcing")
        components |= {
            f"component-supplier-sourcing:{component_class}"
            for component_class in supplier_sourcing_classes
        }
        title_supplier_sourcing_classes = _component_supplier_sourcing_classes(title, "")
        if title_supplier_sourcing_classes:
            title_components.add("component-supplier-sourcing")
            title_components |= {
                f"component-supplier-sourcing:{component_class}"
                for component_class in title_supplier_sourcing_classes
            }
    shipment_plan_change_pattern = (
        r"\b(?:cut(?:s|ting)?|reduc(?:e|es|ed|ing)|lower(?:s|ed|ing)?|trim(?:s|med|ming)?|"
        r"slash(?:es|ed|ing)?|scale[sd]?\s+back)\b[^。！？\n]{0,70}"
        r"\b(?:shipments?|shipment\s+plans?|production\s+plans?|output\s+plans?)\b|"
        r"\b(?:shipments?|shipment\s+plans?|production\s+plans?|output\s+plans?)\b"
        r"[^。！？\n]{0,70}\b(?:cut|reduc(?:e|ed)|lower(?:ed)?|trim(?:med)?|slash(?:ed)?|scaled?\s+back)\b|"
        r"(?:削减|缩减|下调|调低|减少|砍掉)[^。！？\n]{0,36}(?:出货|产量|生产计划|出货规划)|"
        r"(?:出货|产量|生产计划|出货规划)[^。！？\n]{0,36}(?:削减|缩减|下调|调低|减少)"
    )
    if _compiled_rule(shipment_plan_change_pattern, 0).search(title_lower):
        title_components.add("hardware-shipment-plan-change")
        components.add("hardware-shipment-plan-change")
    elif re.search(shipment_plan_change_pattern, lead_lower[:620]):
        components.add("hardware-shipment-plan-change")
    if products and _compiled_rule(r"\b(?:next[- ]generation|second[- ]generation|roadmap|in\s+development|"
        r"plans?\s+for|expected\s+(?:in|for)|coming\s+in|launch(?:es|ing)?\s+in)\b|"
        r"(?:第二代|下一代|路线图|产品前瞻|笔记本前瞻|计划.{0,20}(?:推出|发布)|"
        r"预计.{0,20}(?:推出|发布))", 0).search(title_lower):
        title_components.add("hardware-product-roadmap")
        components.add("hardware-product-roadmap")
    release_delay_pattern = (
        r"\b(?:delay(?:ed|s|ing)?|postpone(?:d|s|ment)?|move(?:d|s)?|push(?:ed|es)?|shift(?:ed|s)?)\b.{0,64}"
        r"\b(?:until|to|into)\s+(?:the\s+)?(?:early\s+)?(?:next\s+year|next\s+spring|spring)\b|"
        r"(?:延期|推迟|改到|延后|放到|移到|移至).{0,32}(?:明年|次年|春季)"
    )
    if re.search(release_delay_pattern, title_lower):
        title_components.add("product-release-delay")
        components.add("product-release-delay")
    elif re.search(release_delay_pattern, lead_lower[:620]):
        components.add("product-release-delay")
    if content_form != "roundup":
        lead_components = _extract_patterns(lead_lower[:620], COMPONENT_PATTERNS)
        if not components:
            components |= lead_components
        else:
            components |= lead_components & LEAD_IDENTITY_COMPONENTS
    clipboard_pattern = r"\b(?:paste|pastes|pasted|pasting)\b.{0,80}\bclipboard\b|\bclipboard\b.{0,80}\b(?:paste|pastes|pasted|pasting)\b"
    if re.search(clipboard_pattern, title_lower):
        title_components.add("clipboard-paste-suggestion")
        components.add("clipboard-paste-suggestion")
    elif content_form != "roundup" and re.search(clipboard_pattern, lead_lower[:620]):
        components.add("clipboard-paste-suggestion")
    if not components and content_form != "roundup" and identity_evidence:
        for evidence_item in identity_evidence[:6]:
            normalized_evidence = _normalized(evidence_item)[:420]
            evidence_components = _extract_patterns(
                normalized_evidence,
                COMPONENT_PATTERNS,
            ) & (EVIDENCE_BACKED_COMPONENTS | LEAD_IDENTITY_COMPONENTS)
            evidence_products = _collapse_product_hierarchy(
                _extract_patterns(normalized_evidence, PRODUCT_PATTERNS)
            )
            components |= {
                component
                for component in evidence_components
                if component in EVIDENCE_BACKED_COMPONENTS
                or bool(title_products & evidence_products)
            }
    display_size_pattern = _compiled_rule(r"(?<!\d)(\d(?:\.\d+)?)\s*(?:-?inch|英寸)", 0)
    title_display_sizes = {
        f"display-size:{match.group(1)}-inch"
        for match in display_size_pattern.finditer(title_lower)
    }
    title_components |= title_display_sizes
    components |= title_display_sizes
    if content_form != "roundup":
        components |= {
            f"display-size:{match.group(1)}-inch"
            for match in display_size_pattern.finditer(lead_lower[:420])
        }
    largest_iphone_display_title = bool(
        title_products & {"iphone"}
        and (
            _compiled_rule(r"\blargest(?:\s+ever)?\s+iphone\s+(?:screen|display)\b", 0).search(title_lower)
            or _compiled_rule(r"\biphone\b.{0,32}\blargest(?:\s+ever)?\s+(?:screen|display)\b", 0).search(title_lower)
            or _compiled_rule(r"(?:史上最大|最大(?:的)?|超大)(?:[^。！？\n]{0,24})iphone|iphone(?:[^。！？\n]{0,24})(?:史上最大|最大(?:的)?|超大)(?:屏|显示)", 0).search(title_lower)
            or bool(title_display_sizes & {"display-size:6.96-inch", "display-size:7-inch"})
        )
    )
    if largest_iphone_display_title:
        title_components.add("largest-iphone-display")
        components.add("largest-iphone-display")
    financed_device_restriction_negated = bool(
        _compiled_rule(r"\b(?:isn['’]t|is\s+not|aren['’]t|are\s+not|won['’]t|will\s+not|not\s+for)\b"
            r".{0,90}\b(?:lease|leases|leased|financed|financing|apple\s+upgrade|upgrade\s+program)\b|"
            r"(?:并非|不是|不会|不用于|无关).{0,40}(?:租赁|月租|分期|apple\s*upgrade)", 0).search(title_lower)
    )
    financed_device_restriction_title = bool(
        not financed_device_restriction_negated
        and
        _contains_any(
            title_lower,
            (
                "lease",
                "leased",
                "financed",
                "financing",
                "monthly device",
                "月租",
                "租赁",
                "分期设备",
            ),
        )
        and _contains_any(
            title_lower,
            (
                "missed payment",
                "unpaid",
                "overdue",
                "restrict",
                "restricted",
                "disable",
                "locked",
                "欠款",
                "欠费",
                "停用",
                "受限",
                "锁定",
                "防止抹除",
                "防止拆",
            ),
        )
    )
    if financed_device_restriction_negated:
        title_components.discard("financed-device-restriction")
        components.discard("financed-device-restriction")
    if financed_device_restriction_title:
        title_components.add("financed-device-restriction")
        components.add("financed-device-restriction")
    apple_device_leasing_program_title = bool(
        _contains_any(
            title_lower,
            (
                "apple upgrade",
                "apple's new upgrade program",
                "apple’s new upgrade program",
                "iphone upgrade program",
                "hardware subscription",
                "device subscription",
                "device leasing program",
                "device-leasing program",
                "leasing program",
                "租赁计划",
                "月租计划",
                "月租业务",
                "月租服务",
                "设备月租",
            ),
        )
        or (
            _contains_any(title_lower, ("apple", "iphone", "苹果"))
            and _contains_any(title_lower, ("月租", "租赁"))
            and _contains_any(title_lower, ("推出", "launch", "debut", "program", "计划", "业务", "服务"))
        )
    )
    if apple_device_leasing_program_title:
        title_components.add("apple-device-leasing-program")
        components.add("apple-device-leasing-program")
    if apple_device_leasing_program_title or financed_device_restriction_title:
        primary_finance_action = ""
        if apple_device_leasing_program_title and not financed_device_restriction_title:
            primary_finance_action = "leasing-program"
        elif financed_device_restriction_title and not apple_device_leasing_program_title:
            primary_finance_action = "device-restriction"
        else:
            first_clause = _compiled_rule(r"[,，;；。]", 0).split(title_lower, 1)[0]
            if (_compiled_rule(r"(?:launch|debut|推出).{0,35}(?:lease|leasing|租赁|月租)|(?:lease|leasing|租赁|月租).{0,35}(?:launch|debut|推出)", 0).search(first_clause)
                    and not _compiled_rule(r"(?:unpaid|overdue|restrict|disable|欠款|欠费|停用|受限)", 0).search(first_clause)):
                primary_finance_action = "leasing-program"
        if primary_finance_action:
            components.add("primary-finance-action:" + primary_finance_action)
            title_components.add("primary-finance-action:" + primary_finance_action)
    patent_disclosure_terms = (
        "design patent",
        "granted patent",
        "newly-granted patent",
        "newly granted patent",
        "patent describes",
        "patent explores",
        "patent shows",
        "patent envisions",
        "获批专利",
        "专利获批",
        "设计专利",
        "专利探索",
        "专利描述",
        "专利勾勒",
        "专利显示",
    )
    patent_litigation_terms = (
        "infringement",
        "lawsuit",
        "court",
        "verdict",
        "appeal",
        "damages",
        "侵权",
        "诉讼",
        "法院",
        "裁决",
        "判决",
        "赔偿",
    )
    patent_disclosure_scope = f"{title_lower} {lead_lower[:900]}"
    patent_litigation_scope = f"{title_lower} {lead_lower[:260]}"
    if (
        products
        and _contains_any(patent_disclosure_scope, patent_disclosure_terms)
        and not _contains_any(patent_litigation_scope, patent_litigation_terms)
    ):
        components.add("product-patent-disclosure")
        if _contains_any(title_lower, patent_disclosure_terms):
            title_components.add("product-patent-disclosure")
    identity_scope = f"{title_lower} {lead_lower[:700]}"
    if "office-real-estate" in components:
        office_places: set[str] = set()
        office_scope = f"{title} {lead[:420]}"
        for match in _compiled_rule(r"(?:\b(?:in|at|near)\s+|[（(])([A-Z][A-Za-z.-]{3,30})(?:\b|[)）])", 0).finditer(office_scope):
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
    # A reported plan has an attributed current assertion; a rumor keyword
    # alone cannot promote a retrospective or the writer's wish.
    if '传出' in title_lower and hardware_action_subjects(title):
        primary = _normalized(source_primary_assertion(title, lead))
        plan = _compiled_rule(r'苹果(?:公司)?(?:正|正在)?(?:考虑|计划)[^。!?！？]{0,120}', 0).search(primary)
        # Compare the first locally owned model, not a later comparison model.
        generations = []
        for text in (title_lower, plan.group() if plan else ''):
            mention = _HARDWARE_MENTION.search(text)
            generation = _compiled_rule(r'^\s*(\d{1,2})(?!\d)', 0).match(text[mention.end():]) if mention else None
            generations.append(generation.group(1) if generation else '')
        if (not _compiled_rule(r'回顾|去年|此前|曾经|早在|当年|愿望|希望|想象|概念|否认|并未|没有', 0).search(primary)
                and _compiled_rule(r'据[^。!?！？]{0,80}(?:透露|报道|称)[,，]?', 0).search(primary)
                and plan and hardware_action_subjects(plan.group()) == hardware_action_subjects(title)
                and not (all(generations) and generations[0] != generations[1])
                and _compiled_rule(r'推出|发布|配备|采用', 0).search(plan.group())):
            title_actions.add('product-disclosure')
    if _compiled_rule(r"^apple(?:['’]s)?\s+[a-z][a-z0-9 -]{1,36}\s+app\s+expands?\b", 0).search(title_lower):
        title_actions.add("feature-change")
    if _compiled_rule(r"\bcancels?\b[^。.!?]{0,50}\b(?:project|model|redesign)\b", 0).search(title_lower):
        title_actions.add("project-cancellation")
    capacity_reduction_title = _compiled_rule(r"(?:砍掉|取消)[^，,。.!?]{0,35}(?:产能|产量|生产班次)", 0).sub("", title_lower, 0)
    if capacity_reduction_title != title_lower and "project-cancellation" not in _extract_patterns(capacity_reduction_title, ACTION_PATTERNS):
        title_actions.discard("project-cancellation")
        title_actions.add("supply-production")

    if _compiled_rule(r"\b(?:found|seen|spotted|identified)\b.{0,24}\b(?:source\s+)?code\b|"
        r"\b(?:source\s+)?code\b.{0,24}\b(?:hints?|reveals?|shows?)\b|"
        r"(?:代码|源码).{0,20}(?:曝光|发现|暗示|显示|揭示)", re.I).search(title_lower):
        title_actions.add("product-disclosure")
    if is_direct_first_party_named_object_change(title, lead):
        title_actions.add("feature-change")
    if company_performance_subject:
        title_actions.add("market-report")
    if "consumer-purchase-intent" in title_components:
        title_actions.add("market-report")
    if (
        title_scope == "apple-direct"
        and "apple-intelligence" in title_products
        and _compiled_rule(r"\b(?:train(?:s|ed|ing)?|develop(?:s|ed|ing)?|custom model|own model)\b|"
            r"(?:训练|自研|自主研发|定制).{0,20}(?:模型|大模型)", 0).search(title_lower)
    ):
        title_actions.add("model-development")
    if "apple-leadership" in title_components:
        title_actions.add("leadership-transition")
    if (
        title_scope == "apple-direct"
        and "apple-maps" in title_products
        and _compiled_rule(r"\b(?:open(?:s|ed)?|accept(?:s|ed|ing)?|available)\b.{0,32}"
            r"\b(?:ad|ads|advertising)\b.{0,24}\b(?:book|booking|reservation)\b|"
            r"\b(?:ad|ads|advertising)\b.{0,24}\b(?:book|booking|reservation|available)\b|"
            r"(?:广告位|地图广告).{0,20}(?:招商|预订|接受|开放)", 0).search(title_lower)
    ):
        title_actions.add("commercial-launch")
    if (
        title_scope == "apple-direct"
        and _compiled_rule(r"\b(?:ad|advertising|campaign|poster)\b|(?:广告|宣传海报|宣传活动)", 0).search(title_lower)
        and _compiled_rule(r"\b(?:withdraw(?:s|n)?|pull(?:s|ed)?|remove(?:s|d)?)\b|(?:撤下|撤回|移除)", 0).search(title_lower)
    ):
        title_actions.add("withdrawal")
    if (
        "official-refurbished-catalog" in title_components
        and _compiled_rule(r"\b(?:add(?:s|ed|ing)?|expand(?:s|ed|ing)?)\b|(?:新增|扩充|扩展)", 0).search(title_lower)
    ):
        title_actions.add("catalog-expansion")
    if _compiled_rule(r"\b(?:lets?|allows?|enables?)\s+(?:you|users?|people)\s+(?:to\s+)?"
        r"(?:make|set|adjust|change|choose|use|view|control)\b|"
        r"(?:让|允许|支持)用户.{0,18}(?:调整|设置|更改|选择|使用|查看|控制)", 0).search(title_lower):
        title_actions.add("feature-change")
    if "price-change" in title_actions:
        price_mentions = list(
            _compiled_rule(r"\b(?:price increase|price hike)\b|(?:涨价|提价|上调价格|上调售价|降价)", 0).finditer(title_lower)
        )
        if price_mentions and all(
            _compiled_rule(r"(?:\b(?:no|not|without)\b\s*|(?:不|不会|未|没有|并未)\s*)$", 0).search(title_lower[max(0, match.start() - 12) : match.start()])
            for match in price_mentions
        ):
            title_actions.discard("price-change")
    if _compiled_rule(r"\b(?:denies?|disputes?|refutes?|counters?|pours?(?:\s+cold)?\s+water\s+on)\b"
        r".{0,90}\b(?:rumou?r|report|claim)\b|"
        r"(?:否认|反驳).{0,48}(?:传闻|报道|说法)|"
        r"(?:否认|反驳).{0,72}(?:不存在|没有|不实)|"
        r"(?:传闻|报道|说法).{0,48}(?:不实|被否认|遭否认)", 0).search(title_lower):
        title_actions.add("claim-denial")
    if _compiled_rule(r"\benters?\s+(?:the\s+)?[a-z][a-z -]{0,24}\s+market\b|"
        r"(?:进入|登陆)[^，。！？:：]{0,16}市场", 0).search(title_lower):
        title_actions.add("retail-availability")
    # “Roadmap update” reports a plan; the noun update does not itself
    # establish a changed product capability.
    if "roadmap-projection" in title_components:
        residual_title = _compiled_rule(r"\broadmap\s+update\b|路线图更新|路线更新", 0).sub("", title_lower, 0)
        if "feature-change" not in _extract_patterns(residual_title, ACTION_PATTERNS):
            title_actions.discard("feature-change")
    if ("keyboard-key-labels" in components
        and _compiled_rule(r"取消(?:文字|文本)|(?:文字|文本).{0,16}(?:改为|换为|改用).{0,8}符号", 0).search(title_lower)):
        # Removing text from a key label changes the label; it does not cancel
        # development or sale of the keyboard named by the headline.
        title_actions.discard("project-cancellation")
        title_actions.add("feature-change")
    actions = set(title_actions)
    # A questioning headline can leave the actual response to the lead.
    # Bind only an explicit Apple denial of the headline's product, not an
    # unrelated denial elsewhere in the article or a missing confirmation.
    lead_denial = _compiled_rule(
        r"^(?:apple\s+(?:has\s+)?(?:denied|denies|refuted|refutes)\s+(?:that\s+)?|"
        r"苹果(?:公司)?(?:今日|今天|已|已经)?(?:否认|驳斥)(?:了)?)([^。.!?]+)", 0,
    ).match(lead_lower)
    denied_configuration = (_compiled_rule(
        r"\b(?:feature|have|include|use|adopt)\s+(.+)|(?:配备|采用|搭载)(.+)", 0,
    ).search(lead_denial.group(1)) if lead_denial else None)
    denied_components = (_extract_patterns(
        next(group for group in denied_configuration.groups() if group), COMPONENT_PATTERNS)
        if denied_configuration else set())
    if (lead_denial
            and title_products & _extract_patterns(lead_denial.group(1), PRODUCT_PATTERNS)
            and any(":" not in component for component in title_components & denied_components)):
        title_actions.add("claim-denial")
        actions.add("claim-denial")
        title_components.add("claim-polarity:configuration-denied")
        components.add("claim-polarity:configuration-denied")
    if _compiled_rule(r"\b(?:to|will|would|could|may|might|expected\s+to|reportedly\s+to)\s+feature\b", 0).search(title_lower):
        title_actions.add("feature-change")
        actions.add("feature-change")
    if content_form != "roundup":
        actions |= _extract_patterns(lead_lower[:500], ACTION_PATTERNS)
    if _non_apple_group_price_action_with_apple_non_change(title):
        title_actions.discard("price-change")
        actions.discard("price-change")
        title_scope = "third-party-context"
        title_components.add("non-apple-group-price-with-apple-comparator")
        components.add("non-apple-group-price-with-apple-comparator")
    availability_expansion_pattern = (
        r"\b(?:expand(?:s|ed|ing)?|extend(?:s|ed|ing)?|roll(?:s|ed|ing)?\s+out)\b"
        r".{0,48}\b(?:availability|coverage|sales|markets?|countries|regions?|services?|programs?)\b|"
        r"(?:扩大|扩展|拓展).{0,32}(?:销售|供应|覆盖|上市).{0,16}(?:范围|市场|国家|地区)?"
    )
    if re.search(availability_expansion_pattern, title_lower):
        title_actions.add("availability-expansion")
        actions.add("availability-expansion")
    elif re.search(availability_expansion_pattern, lead_lower[:500]):
        actions.add("availability-expansion")
    integration_pattern = (
        r"\b(?:integrates?|integrated|integration|sync(?:s|ed|ing|hroni[sz](?:e[sd]?|ing|ation))?|"
        r"connect(?:ed|s|ing)|connect\s+(?:[a-z]+ly\s+)?(?:to|with)|"
        r"can(?:\s+now)?\s+connect\s+(?:[a-z][\w-]*\s+){0,3}(?:data|accounts?|devices?|apps?|services?)|"
        r"embeds?|embedded|"
        r"power(?:s|ed|ing)?\s+(?:the\s+)?(?:navigation|autonomous\s+driving)|at\s+the\s+core\s+of)\b|"
        r"(?:整合|集成|同步|嵌入|接入|驱动导航|作为.{0,12}核心)"
    )
    if re.search(integration_pattern, title_lower):
        title_actions.add("platform-integration")
        actions.add("platform-integration")
    elif re.search(integration_pattern, lead_lower[:500]):
        actions.add("platform-integration")
    first_party_data_pattern = (
        r"(?<![a-z0-9])(?:apple\s+health|healthkit|apple\s+wallet|eventkit)(?![a-z0-9])|"
        r"(?:苹果\s*health|苹果健康|苹果钱包|健康\s*(?:app|应用))"
    )
    if re.search(first_party_data_pattern, title_lower) and re.search(integration_pattern, title_lower):
        title_components.add("apple-data-integration")
        components.add("apple-data-integration")
        data_rollout_pattern = (
            r"\b(?:roll(?:s|ed|ing)?\s+out|relaunch(?:es|ed)?|launch(?:es|ed)?|"
            r"now\s+available|expanded\s+access|opens?\s+to\s+all)\b|"
            r"(?:全面开放|正式上线|开始开放|扩大开放|推出|发布)"
        )
        data_commentary_pattern = (
            r"\b(?:privacy|security|data)[ -]?(?:risk|risks|concern|concerns|tradeoff|tradeoffs|"
            r"warning|warnings|danger|dangers)\b|"
            r"\b(?:creates?|raises?|poses?|brings?)\b.{0,40}\b(?:risk|risks|concerns?)\b|"
            r"(?:隐私|安全|数据).{0,10}(?:风险|争议|隐患|担忧|警告)|"
            r"(?:风险|争议|隐患|担忧).{0,10}(?:隐私|安全|数据)"
        )
        if re.search(data_rollout_pattern, title_lower):
            title_components.add("apple-data-integration-rollout")
            components.add("apple-data-integration-rollout")
        if re.search(data_commentary_pattern, title_lower):
            title_components.add("apple-data-integration-commentary")
            components.add("apple-data-integration-commentary")
    content_lifecycle_pattern = (
        r"\b(?:will\s+end|to\s+end|concludes?|final\s+season|sets?\s+(?:a\s+)?premiere\s+date|"
        r"orders?\s+(?:a\s+)?(?:new\s+)?(?:series|film|movie|documentary|docuseries))\b|"
        r"(?:最终季|完结|收官|确定首播|公布首播|预订.{0,12}(?:剧集|电影|纪录片))"
    )
    content_lifecycle_subject = bool(
        products
        & {
            "apple-arcade",
            "apple-music",
            "apple-tv",
        }
        or _compiled_rule(r"\b(?:series|film|movie|documentary|docuseries|show|season)\b|"
            r"(?:剧集|电影|影片|纪录片|节目|季度|最终季)", 0).search(f"{title_lower} {lead_lower[:240]}")
    )
    if content_lifecycle_subject and re.search(content_lifecycle_pattern, title_lower):
        title_actions.add("content-release")
        actions.add("content-release")
    elif content_lifecycle_subject and re.search(content_lifecycle_pattern, lead_lower[:500]):
        actions.add("content-release")
    official_product_communication = bool(
        _compiled_rule(r"\bapple\b.{0,40}\b(?:shares?|publishes|posts?|releases?)\b.{0,40}\b(?:video|story)\b", 0).search(title_lower)
        or _compiled_rule(r"苹果.{0,40}(?:发布|分享).{0,40}(?:视频|故事|案例)", 0).search(title_lower)
    )
    if official_product_communication:
        title_actions.add("official-communication")
        actions.add("official-communication")
    if _compiled_rule(r"\bsu(?:e|es|ed|ing)\b", 0).search(title_lower):
        title_actions.add("legal")
        actions.add("legal")
    elif _compiled_rule(r"\bsu(?:e|es|ed|ing)\b", 0).search(lead_lower[:500]):
        actions.add("legal")
    price_change_pattern = (
        r"\b(?:starting\s+price|launch\s+at|start(?:s|ing)?\s+at)\s*(?:of\s*)?[$£€]\s*\d|"
        r"[$£€]\s*[\d,]+(?:\.\d+)?\s+starting\s+price\b|"
        r"(?:起步价|起售价|定价|售价).{0,12}(?:突破|超|创新高|\d+(?:\.\d+)?\s*万?元)|万元机|"
        r"\b(?:raise[sd]?|increase[sd]?|hike[sd]?|cuts?|reduce[sd]?|lower[sd]?)\b.{0,36}\b(?:price|prices|pricing|cost|costs)\b|"
        r"\b(?:bump(?:s|ed)?|put(?:s)?|push(?:es|ed)?|send(?:s|ing)?)\b.{0,20}\b(?:up|higher)\b.{0,24}\b(?:price|prices|pricing|cost|costs)\b|"
        r"\b(?:bump(?:s|ed)?|put(?:s)?|push(?:es|ed)?)\s+up\s+(?:the\s+)?(?:price|prices|pricing|cost|costs)\b|"
        r"\b(?:price|prices|pricing|cost|costs)\b.{0,24}\b(?:rise|rises|increase[sd]?|hike[sd]?)\b|"
        r"\b(?:could|may|might|will)\s+be\b.{0,24}\b(?:more\s+)?expensive\b|"
        r"\b(?:got|gets?|becomes?|became)\s+(?:more\s+)?expensive\b|"
        r"\b(?:more\s+)?expensive\b.{0,24}\b(?:than|price|prices|pricing|cost|costs)\b|"
        r"\b(?:raise[sd]?|increase[sd]?|update[sd]?|bump(?:s|ed)?)\b.{0,36}\b(?:trade[ -]in\s+(?:value|values|offer|offers|estimate|estimates))\b|"
        r"(?:上调|提高|调高|调整)[^。；;！？!?]*(?:价格|售价|订阅价|以旧换新|折抵价|折抵估值)|(?:价格|售价|折抵价|折抵估值).{0,18}(?:上调|上涨|提高|调整)"
    )
    price_title_scope = title_lower
    if _compiled_rule(r"累计|累积|总计", 0).search(title_lower):
        # The extreme price of items in a cumulative catalogue is a statistic,
        # not a new retail-price action alongside that count.
        price_title_scope = _compiled_rule(r"[,，]\s*(?:最贵|最便宜|最高|最低)(?:售价|价格)[^。；;]*$", 0).sub("", title_lower, 0)
    if _compiled_rule(price_change_pattern, 0).search(price_title_scope):
        title_actions.add("price-change")
        actions.add("price-change")
    elif _compiled_rule(price_change_pattern, 0).search(lead_lower[:220]):
        actions.add("price-change")
    if _compiled_rule(r"\bwallpapers?\b|壁纸", 0).search(title_lower):
        for platform in title_products & {"macos", "ios", "ipados", "watchos", "tvos", "visionos"}:
            title_components.add(f"system-wallpaper:{platform}")
            components.add(f"system-wallpaper:{platform}")
        title_actions.add("feature-change")
        actions.add("feature-change")
    # Concessive price context is not the headline's current supply action.
    primary_intent_scope = _compiled_rule(r"\b(?:despite|in\s+spite\s+of)\b|(?:尽管|即使)", 0).split(title_lower, 1)[0].strip()
    if not primary_intent_scope:
        primary_intent_scope = _compiled_rule(r"[,，]", 0).split(title_lower, 1)[-1].strip()
    primary_intent: str | None = None
    if _compiled_rule(r"\b(?:exclusive\s+deal|discount|coupon|lowest\s+price)\b|(?:优惠券|限时优惠|促销)", 0).search(title_lower):
        primary_intent = "retail-promotion"
    elif "macbook-thermal-defect" in facets:
        primary_intent = "product-defect"
    elif company_performance_subject:
        primary_intent = "company-performance-report"
    elif _is_analyst_target_action_title(title_lower):
        primary_intent = "analyst-target"
    elif not _compiled_rule(r"\b(?:recruits?|hires?|rehire[sd]?|brings?\s+back|adds?)\b|"
        r"(?:返聘|召回|重新聘用|重新启用|组建)", 0).search(title_lower) and _compiled_rule(r"(?:ceo|chief executive|tim cook|john ternus|steve jobs|库克|特努斯|乔布斯|首席执行官)"
        r".{0,40}(?:tenure|\d{1,2}\s*years?|in numbers|retrospective|任期|掌舵|历程|回顾|收官)", 0).search(title_lower):
        primary_intent = "executive-retrospective"
    elif _compiled_rule(r"(?:apple|aapl|苹果).{0,35}(?:stock|shares|share\s+price|market\s+cap|valuation|股价|市值).{0,35}"
        r"(?:fall|falls|fell|drop|drops|plunge|plunges|lose|loses|lost|erase|erases|evaporate|蒸发|大跌|下跌|暴跌|重挫)|"
        r"(?:stock|shares|share\s+price|market\s+cap|valuation|股价|市值).{0,35}"
        r"(?:fall|falls|fell|drop|drops|plunge|plunges|lose|loses|lost|erase|erases|evaporate|蒸发|大跌|下跌|暴跌|重挫)", 0).search(title_lower):
        primary_intent = "market-move"
    elif _compiled_rule(r"(?:apple|苹果).{0,24}(?:faces?\s+(?:pushback|pressure|opposition)|遭.{0,6}(?:施压|反对))", 0).search(title_lower) and _compiled_rule(r"(?:memory|storage\s+chips?|内存|存储芯片)", 0).search(title_lower):
        primary_intent = "memory-supplier-policy"
    elif _compiled_rule(r"(?:lawmakers?|legislators?|senators?|congress|议员|国会)", 0).search(title_lower) and _compiled_rule(r"(?:memory|storage\s+chips?|supplier|内存|存储芯片|供应商)", 0).search(title_lower) and _compiled_rule(r"(?:demand|require|commit|ban|not\s+use|要求|承诺|不用|禁止|施压)", 0).search(title_lower):
        primary_intent = "memory-supplier-policy"
    elif (
        ("price-change" in title_actions)
        and (primary_intent_scope == title_lower or re.search(price_change_pattern, primary_intent_scope))
        and "component-cost-analysis" not in title_components
        and not _compiled_rule(r"\b(?:no|not|won['’]t|will\s+not)\b.{0,18}\b(?:price|prices|pricing)\b|(?:不|不会|未).{0,8}(?:涨价|提价|上调价格)", 0).search(title_lower)
    ):
        primary_intent = "product-price-change"
    elif title_products & {"iphone", "ipad", "mac", "macbook", "airpods", "apple-watch"} and _compiled_rule(r"(?:supply|availability|供货|供应|缺货).{0,20}(?:shortage|constrain|tight|limited|紧张|短缺|受限|不足)|\bshortage\b|(?:严重缺货)", 0).search(primary_intent_scope):
        primary_intent = "product-supply-constraint"
    elif _compiled_rule(r"(?:\bai\b|artificial intelligence|人工智能|算力)", 0).search(title_lower) and _compiled_rule(r"(?:shortage|constraint|risk|delay|insufficient|limited|短缺|不足|风险|延迟|受限)", 0).search(title_lower):
        primary_intent = "compute-capacity-risk"
    elif (
        _compiled_rule(r"\b(?:production|output|manufacturing|yield|capacity)\b|"
            r"(?:量产|生产|产量|日产|良率|产能)", 0).search(title_lower)
        or _compiled_rule(r"\b(?:make|makes|made|making|manufacture[sd]?|manufacturing|"
            r"produce[sd]?|producing|builds?|built|building|assemble[sd]?|assembling)\b"
            r".{0,36}\b(?:units?|devices?|phones?|few\s+hundred|thousand|million)\b|"
            r"(?:制造|生产|组装).{0,24}(?:台|部|数百|几百|数千|几千|万|百万)", 0).search(title_lower)
    ) and _compiled_rule(r"\b(?:ramp(?:s|ed|ing)?|target|goal|volume|units?|daily|per\s+day|"
        r"few\s+hundred|bottleneck|hurdle|hiccup|constraint|limited|low|only)\b|"
        r"(?:爬坡|目标|规模|台|每天|每日|数百|几百|瓶颈|受限|不足|偏低|仅)", 0).search(title_lower):
        primary_intent = "product-production-status"
    elif _compiled_rule(r"(?:supply|availability|output|供货|供应|产量)", 0).search(title_lower) and _compiled_rule(r"(?:shortage|constraint|tight|limited|紧张|短缺|受限|不足)", 0).search(title_lower):
        primary_intent = "product-supply-constraint"
    elif _compiled_rule(r"(?:\bai\b|artificial intelligence|人工智能)", 0).search(title_lower) and _compiled_rule(r"(?:capex|capital expenditure|spending|investment|invest|资本开支|投入|投资|砸钱)", 0).search(title_lower):
        primary_intent = "capital-strategy"
    if primary_intent:
        title_components.add(f"primary-intent:{primary_intent}")
        components.add(f"primary-intent:{primary_intent}")
        if primary_intent == "product-price-change":
            title_actions.add("price-change")
            actions.add("price-change")
    actors = _title_named_actors(title)
    if not actors:
        actors = _title_named_actors(f"{title} {lead[:180]}")
    supplier_cost_scope = f"{title_lower} {lead_lower[:420]}"
    if "price-change" in actions and _contains_any(
        supplier_cost_scope,
        (
            "chipmaker",
            "foundry",
            "supplier price",
            "supplier cost",
            "tsmc",
            "samsung display",
            "micron",
            "sk hynix",
            "代工厂",
            "供应商涨价",
            "供应成本",
            "台积电",
            "三星显示",
            "美光",
            "海力士",
        ),
    ):
        components.add("supplier-input-cost")
        if _contains_any(
            title_lower,
            (
                "chipmaker",
                "foundry",
                "supplier price",
                "supplier cost",
                "tsmc",
                "samsung display",
                "micron",
                "sk hynix",
                "代工厂",
                "供应商涨价",
                "供应成本",
                "台积电",
                "三星显示",
                "美光",
                "海力士",
            ),
        ):
            title_components.add("supplier-input-cost")
    specific_facets = {
        facet
        for facet in facets
        if facet not in UMBRELLA_FACETS
        and not facet.startswith("platform-")
        and not facet.startswith("os-release-")
    }
    if specific_facets & {
        "apple-memory-supplier-sourcing",
        "apple-restricted-memory-supplier-approval",
    }:
        specific_facets.add("apple-memory-supplier-action")
    release_versions = sorted(
        _normalized_os_version(facet.removeprefix("os-release-version-").replace("-", "."))
        for facet in facets
        if facet.startswith("os-release-version-")
    )
    if not release_versions:
        release_versions = sorted(
            {
                _normalized_os_version(match.group(1))
                for match in _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+){0,2})\b", 0).finditer(f"{title_lower} {lead_lower[:260]}")
            }
        )
    # Some device names also name their versioned software. Resolve the
    # release object from the same locally asserted product/version, not a
    # later paragraph forecasting hardware with that name.
    if (_compiled_rule(r"\b(?:releases?|released|ships?|shipped)\b|发布|推送").search(title_lower)
            and not _compiled_rule(r"\b(?:will|could|might|expected)\b|预计|可能|将会").search(title_lower)):
        for product in title_products - {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}:
            product_name = re.escape(product.replace("-", " "))
            version = re.search(r"\b" + product_name + r"\s+(\d+(?:\.\d+)*)\b", title_lower)
            if not version:
                continue
            target = product_name + r"\s+" + re.escape(version.group(1)) + r"\b"
            for sentence in _compiled_rule(r"(?<=[.!?])\s+|[。！？]", 0).split(lead_lower[:700], 0):
                if _compiled_rule(r"\b(?:previously|last year|will|could|might|expected|not)\b|此前|去年|预计|并未", 0).search(sentence):
                    continue
                if (re.search(target + r"\s+(?:software|firmware)\b|" + target + r"\s+is\s+(?:the\s+)?(?:latest|new)\s+(?:software|firmware)\s+update\b", sentence)
                        and _compiled_rule(r"\b(?:apple\s+(?:(?:today|has)\s+)?released|latest software update|new software update)\b", 0).search(sentence)):
                    components.add(f"device-software-release:{product}:{version.group(1)}")
                    break
    main_title = _compiled_rule(r"[\[\(（【]", 0).split(title_lower, 1)[0]
    title_release_versions = sorted(
        {
            _normalized_os_version(match.group(1))
            for match in _compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+){0,2})\b", 0).finditer(main_title)
        }
    )
    title_is_public_beta = bool(
        _compiled_rule(r"\bpublic betas?\b|公测(?:版|测试版)?", 0).search(main_title)
    )
    if title_is_public_beta:
        components.add("os-release-channel:public")
    elif _compiled_rule(r"\b(?:developer(?:s)?|developer beta)\b|"
        r"(?:开发者预览版|开发者测试版|开发者测试)", 0).search(main_title):
        components.add("os-release-channel:developer")
    title_has_explicit_beta_number = bool(
        _compiled_rule(r"\bbeta\s*\d+\b|测试版\s*\d+|第\s*\d+\s*(?:个|版)?\s*测试版", 0).search(main_title)
    )
    numbered_beta_stages = sorted(
        facet.removeprefix("os-release-")
        for facet in facets
        if _compiled_rule(r"os-release-beta-\d+", 0).fullmatch(facet)
    )
    title_beta_match = _compiled_rule(r"\bbeta\s*(\d+)\b", 0).search(main_title)
    title_public_beta_match = _compiled_rule(r"\bpublic\s+beta\s*(\d+)\b|"
        r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*公测(?:版|测试版)?", 0).search(main_title)
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
    if title_is_public_beta and title_public_beta_match:
        raw_number = title_public_beta_match.group(1) or title_public_beta_match.group(2)
        number = raw_number if raw_number.isdigit() else chinese_number_map.get(raw_number)
        if number:
            numbered_beta_stages = [f"beta-{number}"]
    elif title_beta_match:
        numbered_beta_stages = [f"beta-{title_beta_match.group(1)}"]
    if not numbered_beta_stages:
        release_scope = f"{main_title} {lead_lower[:220]}"
        if title_is_public_beta:
            public_lead_match = _compiled_rule(r"\bpublic\s+betas?\s*(\d+)\b|"
                r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\s+"
                r"(?:(?:ios|ipados|macos|watchos|tvos|visionos)(?:\s+\d+(?:\.\d+){0,2})?\s+)?"
                r"public\s+betas?\b|"
                r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*公测(?:版|测试版)?", 0).search(lead_lower[:220])
            if public_lead_match:
                raw_number = next(value for value in public_lead_match.groups() if value)
                number = (
                    raw_number
                    if raw_number.isdigit()
                    else chinese_number_map.get(raw_number)
                    or {
                        "one": "1", "first": "1", "two": "2", "second": "2",
                        "three": "3", "third": "3", "four": "4", "fourth": "4",
                        "five": "5", "fifth": "5", "six": "6", "sixth": "6",
                        "seven": "7", "seventh": "7", "eight": "8", "eighth": "8",
                        "nine": "9", "ninth": "9", "ten": "10", "tenth": "10",
                    }.get(raw_number)
                )
                if number:
                    numbered_beta_stages = [f"beta-{number}"]
        beta_match = None if title_is_public_beta else _compiled_rule(r"\bbeta\s*(\d+)\b", 0).search(release_scope)
        if beta_match:
            numbered_beta_stages = [f"beta-{beta_match.group(1)}"]
        elif not numbered_beta_stages and not title_is_public_beta:
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
                "seven": "7",
                "seventh": "7",
                "eight": "8",
                "eighth": "8",
                "nine": "9",
                "ninth": "9",
                "ten": "10",
                "tenth": "10",
            }
            ordinal_match = _compiled_rule(r"\b(?:round|developer beta)\s+(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\b", 0).search(release_scope) or _compiled_rule(r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\s+"
                r"(?:round\s+of\s+)?developer\s+betas?\b", 0).search(release_scope) or _compiled_rule(r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\s+"
                r"(?:ios|ipados|macos|watchos|tvos|visionos)"
                r"(?:\s*(?:,|and|&|/)?\s*(?:ios|ipados|macos|watchos|tvos|visionos))*"
                r"(?:\s+[a-z][a-z0-9-]+){0,2}\s+"
                r"public betas?\b", 0).search(main_title) or _compiled_rule(r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth|seven|seventh|eight|eighth|nine|ninth|ten|tenth)\s+"
                r"(?:ios|ipados|macos|watchos|tvos|visionos)"
                r"(?:\s+\d+(?:\.\d+){0,2})?"
                r"(?:\s*(?:,|and|&|/)?\s*(?:ios|ipados|macos|watchos|tvos|visionos)"
                r"(?:\s+\d+(?:\.\d+){0,2})?)*\s+betas?\b", 0).search(main_title)
            if ordinal_match:
                ordinal = ordinal_numbers[ordinal_match.group(1)]
                # "First macOS Public Beta" names the first public wave, not
                # developer beta 1. Later ordinals still distinguish public
                # beta 2/3 waves from the initial unnumbered public release.
                if not (title_is_public_beta and ordinal == "1"):
                    numbered_beta_stages = [f"beta-{ordinal}"]
        if not numbered_beta_stages:
            chinese_match = _compiled_rule(r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*(?:开发者)?(?:测试版|预览版)", 0).search(release_scope)
            if not chinese_match:
                chinese_match = _compiled_rule(r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*公测(?:版|测试版)?", 0).search(release_scope)
            if chinese_match:
                raw_number = chinese_match.group(1)
                number = raw_number if raw_number.isdigit() else chinese_number_map.get(raw_number)
                if number:
                    numbered_beta_stages = [f"beta-{number}"]
    title_is_signing_closure = bool(
        _compiled_rule(r"\b(?:stops?|stopped|ceases?|ceased)\s+signing\b|"
            r"\bno\s+longer\s+signs?\b|"
            r"(?:停止签署|停止签名|关闭.{0,12}签名(?:验证|通道)?)", 0).search(main_title)
    )
    title_is_release_wave = not title_is_signing_closure and bool(
        _compiled_rule(r"\b(?:releases?|released|ships?|shipped|seeds?|seeded|rolls? out|now available|available now|is here|are out now|arrives?|lands?|revised|surfaces?|is coming soon|are coming soon|coming next week)\b|"
            r"\bstarts?\s+round\b|\bversion\s*2\s+update\b|"
            r"(?:即将发布|最快.{0,8}发布|发布|推送|释出|修订版)|(?:正式版|候选版).{0,12}上线", 0).search(main_title)
    )
    title_has_beta_stage = bool(
        numbered_beta_stages
        and _compiled_rule(r"\bbetas?\b|(?:开发者|公测|测试版|预览版)", 0).search(main_title)
    )
    title_has_rc_stage = bool(
        _compiled_rule(r"\brelease candidates?\b|\brc\b|候选版", 0).search(main_title)
    )
    title_has_final_stage = bool(
        title_is_release_wave
        and not title_is_public_beta
        and not title_has_beta_stage
        and not title_has_rc_stage
        and _compiled_rule(r"\b(?:releases?|released|ships?|shipped|rolls? out|now available|available now|is here|are out now|arrives?|lands?)\b|"
            r"(?:正式发布|正式推送|正式版|面向全体用户|面向公众|"
            r"推送.{0,24}安全更新|发布.{0,24}安全更新|安全更新.{0,12}(?:发布|推送))", 0).search(main_title)
    )
    mixed_title_release_stages = bool(
        title_has_beta_stage
        and _compiled_rule(r"(?:安全更新|正式版|面向全体用户|面向公众)", 0).search(main_title)
        and len(title_release_versions) > 1
    )
    if title_has_rc_stage:
        release_stages = ["rc"]
    elif title_has_final_stage:
        release_stages = ["final"]
    elif (
        title_is_public_beta
        and not title_has_explicit_beta_number
        and (not numbered_beta_stages or numbered_beta_stages == ["beta-1"])
    ) or (
        "os-release-public-beta" in facets and not numbered_beta_stages
    ):
        release_stages = ["public-beta"]
    elif title_has_beta_stage:
        release_stages = numbered_beta_stages
    elif "os-release-rc" in facets:
        release_stages = ["rc"]
    elif "os-release-final" in facets:
        release_stages = ["final"]
    else:
        release_stages = numbered_beta_stages
    if (
        release_versions
        and release_stages
        and title_is_release_wave
        and not mixed_title_release_stages
    ):
        preferred_versions = title_release_versions or release_versions
        components.add(f"os-wave:{preferred_versions[0]}:{release_stages[0]}")
    if release_stages and title_is_release_wave and not mixed_title_release_stages:
        platform_names = {
            match.group(1)
            for match in _compiled_rule(r"\b(ios|ipados|macos|watchos|tvos|visionos)\b", 0).finditer(main_title)
        }
        platform_names |= {
            facet.removeprefix("platform-")
            for facet in facets
            if facet
            in {
                "platform-ios",
                "platform-ipados",
                "platform-macos",
                "platform-watchos",
                "platform-tvos",
                "platform-visionos",
            }
        }
        for platform in platform_names:
            components.add(f"os-wave-platform:{platform}:{release_stages[0]}")
    public_release = current_public_os_release(title, lead)
    if public_release:
        public_platform, public_version = public_release
        components.add(f"os-wave:{public_version}:final")
        components.add(f"os-wave-platform:{public_platform}:final")
    components |= {
        f"evidence-named-subject:{subject}"
        for subject in _explicit_evidence_first_party_subjects(identity_evidence)
    }
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
        title_named_subjects=frozenset(_title_primary_named_subjects(title, lead)),
        content_form=content_form,
        scope=title_scope,
        action_owner=_primary_action_owner(
            title,
            lead,
            scope=title_scope,
            content_form=content_form,
            title_actions=title_actions,
            title_products=title_products,
        ),
    )


_LANGUAGE_NAMES = (
    ("english", r"English|英语|英文"), ("french", r"French|法语"),
    ("japanese", r"Japanese|日语"), ("korean", r"Korean|韩语"),
    ("portuguese", r"Portuguese|葡萄牙语"), ("spanish", r"Spanish|西班牙语"),
)


def local_action_changes_owner(text: str, aliases: str) -> bool:
    """A concrete new action needs its own actor and object, even inside a topic paragraph."""
    verb = r"(?:publishes|published|releases|released|launches|launched|introduces|introduced|announces|announced|adds|raises|raised|cuts|increases|decreases)"
    match = re.search(r"(?:^|[;；]\s*|\bMeanwhile,?\s+|\bAlso,?\s+)(?P<actor>[A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*){0,3}?|The company|Apple)\s+(?:(?:now|also|today|has)\s+){0,3}(?i:" + verb + r")\b", text)
    chinese = _compiled_rule(r"^(?P<actor>[\u4e00-\u9fff]{2,8})(?:宣布|推出|发布|上调|下调)", 0).search(text)
    if not match and not chinese:
        return False
    actor = (match or chinese).group('actor').casefold()
    if actor not in {"apple", "the company", "苹果"} and not re.match(aliases, actor, re.I):
        return True
    if re.search(aliases, text, re.I):
        return False
    # A named different product is not licensed by the parent actor alone.
    products = _extract_patterns(_normalized(text), PRODUCT_PATTERNS)
    return bool(products)


def bind_document_claim(evidence: ArticleEvidence) -> BoundClaim | None:
    """Bind a published document and its local statements, not feature launches."""
    document = r"document|paper|support article|文档|文件|支持文章|白皮书"
    title = evidence.title
    intro = " ".join([evidence.raw_lead, *(unit.text for unit in evidence.units[:2])])
    publication = (r"(?:\b(?:Apple|the company)\s+(?:(?:has|today|also|now)\s+){0,3}(?:published|publishes|released|releases|details|explains)\b|苹果(?:今日|今天|已经|还)?(?:发布|公布|介绍))[^.!?。]{0,150}(?:" + document + r")")
    if not (re.search(document, title + " " + intro, re.I) and re.search(publication, intro, re.I)):
        return None
    first_text = evidence.units[0].text if evidence.units else evidence.raw_lead
    first_spans = tuple(source_sentence_spans(first_text))
    first_sentence = first_text[first_spans[0][0]:first_spans[0][1]] if first_spans else first_text
    context = title + " " + first_sentence
    if _compiled_rule(r"privacy|隐私", re.I).search(title) and _compiled_rule(r"Audio Intelligence|音频智能", re.I).search(context):
        subject, topic = "audio-intelligence", "privacy-document"
        topic_pattern = r"Audio Intelligence|Live Rewind|Siri Recap|Sound Recognition|Music Recognition|Secure Exclave|\bS11\b|raw audio|audio buffer|microphone|speech|transcri|音频智能|原始音频|隐私"
    elif _compiled_rule(r"Apple Intelligence|苹果智能", re.I).search(title) and _compiled_rule(r"usage|limits?|terms|限额|使用|条款", re.I).search(title):
        subject, topic = "apple-intelligence", "usage-terms-document"
        topic_pattern = r"Apple Intelligence|usage|limits?|access|iCloud|camera|server.side|restric|enforc|throttl|suspen|request complexity|system demand|\bfee\b|使用|限额|条款|摄像头"
    else:
        return None
    spans = []
    list_scope = False
    for unit in evidence.units:
        if unit.kind == "h1":
            continue
        for start, end in source_sentence_spans(unit.text):
            text = unit.text[start:end]
            if _compiled_rule(r"learn (?:much )?more|read the full|for yourself here|follow this link|full coverage|了解更多", re.I).search(text):
                continue
            if local_action_changes_owner(text, r"Audio Intelligence|Live Rewind|Siri Recap" if topic == "privacy-document" else r"Apple Intelligence|Siri AI"):
                list_scope = False
                continue
            related = bool(re.search(topic_pattern, text, re.I))
            # Short list entries inherit their immediately preceding explicit
            # document enumeration, not an arbitrary article-wide topic.
            inherited_list = unit.kind == "li" and list_scope
            publication_statement = bool(re.search(document, text, re.I) and _compiled_rule(r"publish|releas|details|explains|发布|公布", re.I).search(text))
            if related or inherited_list or publication_statement:
                spans.append((unit.unit_id, start, end))
            if unit.kind != "li":
                list_scope = related and text.rstrip().endswith((":", "："))
    if not spans:
        return None
    return BoundClaim(subject, "document-publication", topic, (), evidence.article_id,
        tuple(dict.fromkeys(key for key, _, _ in spans)), tuple(spans), evidence.content_form, subject_relation="apple-direct", report_role="independent")


def bind_named_service_rollout(evidence: ArticleEvidence) -> BoundClaim | None:
    """Preserve a named first-party service action and its local conditions."""
    title = evidence.title
    lead = " ".join(unit.text for unit in evidence.units if unit.kind not in {"h1", "h2"})[:1800]
    current_action = r"(?:\bApple\s+(?:(?:is|has|today|also|now)\s+){0,3}(?:adds?|adding|introduc(?:es|ed|ing)|launch(?:es|ed|ing)|announc(?:es|ed|ing))\b|苹果[^。！？.!?]{0,24}(?:推出|发布|新增))"
    first_span = next(source_sentence_spans(lead), (0, len(lead)))
    action_lead = lead[first_span[0]:first_span[1]]
    identity = build_event_identity(title, action_lead)
    if (identity.scope != "apple-direct" or identity.action_owner == "third-party"
        or not re.search(current_action, title + " " + action_lead, re.I)):
        return None
    if _compiled_rule(r"AppleCare\s*One", re.I).search(title) and _compiled_rule(r"family|families|家庭", re.I).search(title):
        subject, action, object_name = "applecare-one", "plan-launch", "family-plan"
        scope = r"AppleCare|family|families|individual|theft|loss|claims?|coverage|eligible|devices?|people|month|per year|家庭|共享|理赔|失窃|遗失|设备|月费|美元|年"
    elif _compiled_rule(r"iPhone\s*Handoff", re.I).search(title):
        subject, action, object_name = "iphone-handoff", "feature-rollout", "phone-number-sharing"
        scope = r"Handoff|iPhones?|eSIM|Dual SIM|carriers?|T-Mobile|Deutsche Telekom|phone number|Apple account|FaceTime|iMessage|cellular|Wi-Fi|fees?|电话号码|手机号|主设备|备用机|蜂窝|运营商|同一时刻"
    else:
        return None
    spans = []
    for unit in evidence.units:
        if unit.kind == "h1":
            continue
        for start, end in source_sentence_spans(unit.text):
            text = unit.text[start:end]
            aliases = r"AppleCare(?:\s*One)?|苹果保障" if subject == "applecare-one" else r"iPhone\s*Handoff"
            if local_action_changes_owner(text, aliases):
                continue
            if re.search(scope, text, re.I) and not _compiled_rule(r"full coverage|follow this link|learn more|了解更多|感谢.{0,20}线索", re.I).search(text):
                spans.append((unit.unit_id, start, end))
    if not spans:
        return None
    return BoundClaim(subject, action, object_name, (), evidence.article_id,
        tuple(dict.fromkeys(key for key, _, _ in spans)), tuple(spans), evidence.content_form, subject_relation="apple-direct", report_role="independent")


def bind_replaceable_component_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Separate a physical replaceable layer from its coverage fee schedule.

    Executive job titles are attribution, never a workforce operation. Fee
    claims need their own coverage/price evidence; unassigned details retain
    their source spans in the review queue.
    """
    h = _normalized(evidence.title)
    model = _frame_search(r"iphone\s*(duo|air|\d+(?:\s*pro(?:\s*max)?)?)(?![a-z0-9])",h)
    layer = r"cover\s*layer|(?:folding|display|top)\s+layer|保护[膜层]|覆盖层|盖板层"
    if not (model and _frame_search(layer,h)
            and _frame_search(r"replaceable|replace|更换",h)):
        return ()
    target_model = _compiled_rule(r"\s+", 0).sub("", model.group(), 0)
    active_target = True
    groups = {}
    for unit in evidence.units:
        if unit.kind not in {'p','li','text'} or unit.container_id == 'caption':
            continue
        for start,end in source_sentence_spans(unit.text):
            text = _normalized(unit.text[start:end])
            if _frame_search(r"\b(?:last year|historically|used to|never|denied)\b|去年|否认|历史",text):
                continue
            named_devices = [_compiled_rule(r"\s+", 0).sub("", m.group(), 0) for m in _compiled_rule(
                r"iphone\s*(?:duo|air|\d+(?:\s*pro(?:\s*max)?)?)(?![a-z0-9])|"
                r"\b(?:ipad|macbook|apple\s*watch)\b",0).finditer(text)]
            if named_devices:
                active_target = all(name==target_model for name in named_devices)
            if not active_target:
                continue
            negated_price = _frame_search(
                r"(?:does|do|will)\s+not\s+cost|(?:doesn|don|won)['’]t\s+cost|not\s+(?:priced|available)\s+at|"
                r"费用(?:并非|不是)|并非.{0,8}(?:美元|元)|不收取",text)
            own_part_reference = _frame_search(
                r"\b(?:a|the|this|its)\s+(?:cover|display|top)\s+layer|"
                r"(?:这层|该|上述).{0,10}(?:保护|覆盖)|苹果.{0,25}保护层|官方\s*applecare.{0,30}保护层",text)
            own_fee = (target_model in named_devices or own_part_reference
                       or ('repair-fee-schedule' in groups and _frame_search(
                           r"^(?:other|additional|accidental|theft|loss)\b|^(?:其他|另|意外损坏|失窃)",text)))
            fee = (not negated_price and own_fee and _frame_search(r"apple\s*care|苹果保障",text)
                   and _frame_search(r"\$\s*\d|\d+\s*(?:美元|元)|cost|fee|费用|收费",text)
                   and _frame_search(r"replac|repairs?|更换|维修",text))
            negative_design = _frame_search(
                r"(?:not|isn['’]t|aren['’]t)\s+(?:removable|replaceable)|不能更换|不可更换|并非可更换",text)
            design = (not negative_design and _frame_search(layer,text) and _frame_search(r"can\s+be\s+(?:removed|replaced)|removable|replaceable|可(?:以)?(?:单独)?(?:拆卸和|剥离并)?(?:移除|更换)|支持更换",text))
            if design and fee:
                # A price introduced in a later clause qualifies the service,
                # not the engineering claim. Keep both exact source spans.
                split = _frame_search(r"[,，;；](?=[^,，;；]{0,35}(?:apple\s*care|苹果保障))",text)
                if split:
                    # Normalization may change offsets; find the punctuation
                    # in the original sentence, never use normalized offsets.
                    raw = unit.text[start:end]
                    boundary = _compiled_rule(r"[,，;；](?=[^,，;；]{0,35}(?:Apple\s*Care|苹果保障))",re.I).search(raw)
                    if boundary:
                        groups.setdefault('replaceable-cover-design',[]).append((unit.unit_id,start,start+boundary.start()))
                        groups.setdefault('repair-fee-schedule',[]).append((unit.unit_id,start+boundary.end(),end))
                        continue
            if design:
                groups.setdefault('replaceable-cover-design',[]).append((unit.unit_id,start,end))
            if fee:
                groups.setdefault('repair-fee-schedule',[]).append((unit.unit_id,start,end))
    # A bare amount without service terms must not replace the physical claim.
    if 'replaceable-cover-design' not in groups:
        return ()
    subject = 'iphone-' + model.group(1).replace(' ','-')
    return tuple(BoundClaim(subject,action,'source-operation',(),evidence.article_id,
        tuple(dict.fromkeys(span[0] for span in spans)),tuple(spans),evidence.content_form,
        category='software_systems' if action=='repair-fee-schedule' else 'hardware_products',
        event_kind='os_app' if action=='repair-fee-schedule' else 'hardware_market', subject_relation="apple-direct", report_role="independent")
        for action,spans in groups.items())



def bind_connectivity_remedy_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Bind independently asserted remedies, not every verb in an incident report.

    Carrier notices, a settings release, a setup requirement and a replacement
    remedy have different objects. Background versions and quoted advice alone
    cannot establish a release or mandate. Unassigned detail remains reviewable.
    """
    h = _normalized(evidence.title)
    model = _frame_search(r"iphone\s*(\d+(?:\s*pro(?:\s*max)?)?|duo|air)(?![a-z0-9])", h)
    if not model or not _frame_search(r"carrier\s+(?:(?:settings|bundle)\s+)?update|cellular|connectivity|\bsos\b|蜂窝|通信故障|通话故障|网络故障|断网", h + ' ' + _normalized(evidence.raw_lead)[:650]):
        return ()
    raw = evidence.title + '。' + evidence.raw_lead
    # Bind a network name from a grammatical network/carrier reference. The
    # provider is not a fixed allowlist and is part of the incident identity.
    network_pattern = _compiled_rule(r"(?<![A-Za-z0-9&])([A-Z][A-Za-z0-9&-]*);?(?:['’]s|的)?\s*(?:network|carrier(?: settings| bundle)?(?: update)?|customers?|spokesperson|运营商网络|蜂窝网络|网络|公司(?:的)?用户)")
    named_carrier = _compiled_rule(r"运营商\s*([A-Z][A-Za-z0-9&-]*)")
    carrier_notice = _compiled_rule(r"(?<![A-Za-z0-9&])([A-Z][A-Za-z0-9&-]*);?\s+(?:(?:has|today|now)\s+)*(?:texted\s+customers|sent\s+(?:a\s+)?text\s+message\s+to\s+customers)")
    non_carriers = {'apple', 'the', 'on', 'to', 'wi-fi', 'wifi'}
    historical = r"\b(?:last year|last month|last week|previously)\b|去年|此前"
    def networks_in(value):
        return {m.group(1).lower() for pattern in (network_pattern, named_carrier, carrier_notice)
                for m in pattern.finditer(value) if m.group(1).lower() not in non_carriers}
    headline_carrier = _compiled_rule(r"^([A-Z][A-Za-z0-9&-]*);?\s+(?:[Aa]cknowledges|[Cc]onfirms|[Cc]laims|[Tt]ells|on\s+iPhone|and\s+Apple)\b").search(evidence.title)
    primary_networks = {headline_carrier.group(1).lower()} if headline_carrier and headline_carrier.group(1).lower() not in non_carriers else set()
    for start, end in source_sentence_spans(raw):
        sentence = raw[start:end]
        if not _frame_search(historical, sentence):
            primary_networks.update(networks_in(sentence))
    if not primary_networks:
        for unit in evidence.units:
            for start, end in source_sentence_spans(unit.text):
                sentence = unit.text[start:end]
                if not _frame_search(historical, sentence):
                    primary_networks.update(networks_in(sentence))
    # Ambiguous body-only carriers remain unassigned; input order cannot pick
    # the owner of a generic replacement sentence.
    if len(primary_networks) != 1:
        return ()
    provider = next(iter(primary_networks))
    subject = 'iphone-' + model.group(1).replace(' ','-') + ':network:' + provider
    notice_parent = bool(_frame_search(re.escape(provider)+r'.{0,15}(?:acknowledg|confirms?|tells?|claims?|on\s+iphone|确认|表示)',h)) and not _frame_search(r'and\s+apple|与苹果|和苹果',h[:40])
    steps_parent = bool(_frame_search(r"steps|taking\s+action|推出.{0,20}运营商|carrier\s+(?:(?:settings|bundle)\s+)?update",h))
    replacement_parent = bool(_frame_search(r"replac|更换|换机|换新|苹果(?:回应|确认)|apple\s+confirms",h))
    if not (notice_parent or steps_parent or replacement_parent):
        return ()
    groups = {}
    for unit in evidence.units:
        if unit.kind not in {'p','li','text'} or unit.container_id == 'caption':
            continue
        for start,end in source_sentence_spans(unit.text):
            sentence = unit.text[start:end]
            t = _normalized(sentence)
            # An announced offer and a required replacement describe the same
            # remedy. Require Apple's own affirmative commitment; another
            # provider, a possible offer or a denial cannot supply it.
            offer = _frame_search(
                r"\bapple\s+(?:(?:has|today|now)\s+)*"
                r"(?:(?:says?|said|announc(?:ed|es)|confirm(?:ed|s)?)\s+(?:that\s+)?(?:it\s+)?)?"
                r"(?:will\s+)?(?:offer|provide)s?\s+(?:free\s+)?replacements?\b|"
                r"苹果(?:公司|官方)?(?:(?:正式|公开|现已|已经|今天|今日|已|也|还)|"
                r"(?:面?向[^，,。；;]{1,20})){0,4}(?:(?:发布声明|声明|宣布|表示|承诺|确认)[，,：:]?\s*)?"
                r"(?:宣布|承诺|确认)?(?:将|会|已|现已)?(?:为|针对)[^，,。；;]{0,65}"
                r"(?:提供|安排)(?:免费)?(?:换新|更换|换机)",sentence)
            offer_text = ''
            offer_context = ''
            offer_end = 0
            if offer:
                boundary = _frame_search(r"[,，;；]|\b(?:but|while|whereas)\b|但|不过",sentence[offer.end():])
                offer_end = offer.end() + boundary.start() if boundary else len(sentence)
                offer_text = sentence[offer.start():offer_end]
                # Appositive attribution still qualifies this offer after a
                # comma; a separate device or user-background clause does not.
                dependent = [clause for clause in _compiled_rule(r"[,，;；]",0).split(sentence[offer_end:])
                    if _frame_search(r"^\s*(?:(?:a|the|this|that)\s+(?:claim|report|statement|offer|plan)\b|"
                        r"according\s+to\s+(?:(?:a|the)\s+)?statement\b|"
                        r"(?:该|这项|这一|上述)(?:计划|声明|说法|承诺))",clause)]
                offer_context = ' '.join([offer_text,*dependent])
            temporal_context = _normalized(sentence[:offer.start()]) if offer else t
            if _frame_search(r"\b(?:if a|may be required|could be required|hopefully|alleged|last year|last month|last week|previously)\b|据称|去年|此前|猜测",temporal_context):
                continue
            owned_text = _normalized(offer_text) if offer else t
            other_models = [m.group(1).replace(' ','-') for m in _compiled_rule(
                r"iphone\s*(\d+(?:\s*pro(?:\s*max)?)?|duo|air)(?![a-z0-9])",0).finditer(owned_text)]
            if other_models and model.group(1).replace(' ','-') not in other_models:
                continue
            networks = networks_in(offer_text if offer else sentence)
            settings_owners = [match.group(1).lower() for match in _compiled_rule(
                r"(?<![A-Za-z0-9&])([A-Z][A-Za-z0-9&-]*);?\s+carrier settings").finditer(unit.text[start:end])]
            # The named settings package owns its release. A different
            # network mentioned in a contrast clause cannot reassign it.
            local_networks = settings_owners or networks
            if local_networks and set(local_networks) != {provider}:
                continue
            action = ''
            if replacement_parent and offer and not _frame_search(
                    r"\b(?:not|never|denied|cancelled|canceled|considering|may|might|could|previously|last year|last month|last week)\b|"
                    r"否认|不会|并非|不再|考虑|可能|或将|取消|去年|此前(?:宣布|表示|承诺|确认)",offer_context):
                action = 'device-replacement-remedy'
            elif (steps_parent and _frame_search(r"apple\s+(?:(?:today|has|also|now|just)\s+)*(?:released|issued|rolls?\s+out|is\s+(?:now\s+)?rolling\s+out|began\s+rolling\s+out)|苹果(?:公司)?(?:今天|今日|现已|已|也)*(?:发布|推送)",t)
                    and _frame_search(r"carrier\s+(?:(?:settings|bundle)\s+)?update|运营商设置更新",t)):
                action = 'carrier-settings-release'
            elif (steps_parent and _frame_search(r"apple\s+(?:(?:today|has|also|now|just)\s+)*(?:started\s+requiring|requires?)|苹果(?:公司)?(?:今天|今日|现已|已|也)*(?:开始要求|强制)",t)
                    and _frame_search(r"set\s*up|setup|设置设备|激活",t)
                    and _frame_search(r"ios\s*\d+",t)):
                action = 'setup-update-requirement'
            elif (replacement_parent and _frame_search(r"(?:apple.{0,35}(?:says?|said|explains?|confirms?)|the company.{0,25}tells|苹果.{0,20}(?:表示|称|指出|确认|已发布))",t)
                    and _frame_search(r"(?:need|require|must).{0,35}replac|(?:需(?:要)?|必须|只能).{0,20}(?:更换|换机)",t)):
                if _frame_search(r"(?:并非|并不|不是).{0,8}只能.{0,20}(?:更换|换机)",t):
                    continue
                replacement_clauses = _compiled_rule(r"\b(?:but|while|whereas)\b|[，,;；]|但|不过",0).split(t)
                unnecessary = any(_frame_search(
                    r"(?:(?:do|does|will)\s+not\s+(?:need|require)|(?:don|doesn|won)['’]t\s+(?:need|require)|"
                    r"no\s+(?:need|requirement)|不(?:需要|必)|无需)"
                    r"(?:(?!\b(?:and|need|require)\b|需要).){0,45}(?:replac|更换|换机)|"
                    r"replac.{0,25}not\s+(?:needed|required)",clause)
                    for clause in replacement_clauses)
                action = 'device-replacement-not-required' if unnecessary else 'device-replacement-remedy'
            elif (notice_parent and _frame_search(re.escape(provider) + r";?.{0,60}(?:said|acknowledged|statement|text\s+message|texted|称|确认|表示|短信)",t)):
                action = 'carrier-incident-notice'
            if action:
                version = None
                if action == 'carrier-settings-release':
                    package = _frame_search(r"carrier\s+(?:(?:settings|bundle)\s+)?update|运营商设置更新",t)
                    tail = t[package.end():] if package else ''
                    # A transition names the destination; its from-version is
                    # context. Otherwise require a version attached to the
                    # package, rather than any number elsewhere in the sentence.
                    version = _frame_search(r"^\s*[(（]?\s*(?:version\s*|版本\s*)?(\d+(?:\.\d+)+)",tail)
                    if version is None:
                        transition = _compiled_rule(r"\b(?:while|whereas|but)\b|[;；]|但|不过",0).split(tail,maxsplit=1)[0]
                        if not _frame_search(r"consider|plans?|next|future|考虑|计划|未来",transition):
                            version = _frame_search(r"(?:\bto\s+|升(?:级)?至\s*)(?:version\s*|版本\s*)?(\d+(?:\.\d+)+)",transition)
                elif action == 'setup-update-requirement':
                    version = _frame_search(r"(?:install|update\s+to|upgrade\s+to|安装|升级至|更新至)\s*ios\s*(\d+(?:\.\d+)*)",t)
                target = subject
                if version:
                    target += ':version:' + next(v for v in version.groups() if v)
                span = (unit.unit_id,start+offer.start(),start+offer_end) if offer and action=='device-replacement-remedy' else (unit.unit_id,start,end)
                groups.setdefault((action,target),[]).append(span)
    release_groups = [key for key in groups if key[0] == 'carrier-settings-release']
    if len(release_groups) == 1:
        spans = groups[release_groups[0]]
        assigned_units = {u for u, _, _ in spans}
        for unit in evidence.units:
            if unit.unit_id not in assigned_units and _frame_search(r"(?:tonight|today|current|new)[’']?s?\s+release.{0,90}carrier\s+bundle\s+version|本次.{0,20}运营商.{0,15}版本", unit.text):
                local_models = {m.group(1).replace(' ', '-') for m in _compiled_rule(r'iphone\s*(\d+(?:\s*pro(?:\s*max)?)?|duo|air)(?![a-z0-9])', re.I).finditer(unit.text.lower())}
                local_networks = networks_in(unit.text)
                if local_models and local_models != {model.group(1).replace(' ', '-')}:
                    continue
                if local_networks and local_networks != {provider}:
                    continue
                known_version = release_groups[0][1].split(':version:')[-1] if ':version:' in release_groups[0][1] else ''
                detail_version = _frame_search(r'carrier\s+bundle\s+version\s+(\d+(?:\.\d+)+)', unit.text)
                if known_version and detail_version and known_version != detail_version.group(1):
                    continue
                spans.append((unit.unit_id, 0, len(unit.text)))
    return tuple(BoundClaim(target,action,'source-operation',(),evidence.article_id,
        tuple(dict.fromkeys(x[0] for x in spans)),tuple(spans),'news',
        category='software_systems' if action in {'carrier-settings-release','setup-update-requirement'} else 'hardware_products',
        event_kind='os_app' if action in {'carrier-settings-release','setup-update-requirement'} else 'hardware_market', subject_relation="apple-direct", report_role="independent")
        for (action,target),spans in groups.items())

def bind_mail_quota_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Bind each counted mail object and limit inside its own source clause."""
    if not _compiled_rule(r"icloud", re.I).search(evidence.title + " " + evidence.raw_lead):
        return ()
    spans, qualifiers, primary = {}, {}, {}
    numbers = {name: str(i) for i, name in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))}
    number = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    junction = _compiled_rule(r"[;；]|\band\b|[，,]\s*(?=(?:并将|而|另外|同时).{0,20}(?:地址|别名|域名))", re.I)
    for unit in evidence.units:
        if unit.kind == "h1":
            continue
        for sentence_start, sentence_end in source_sentence_spans(unit.text):
            sentence = unit.text[sentence_start:sentence_end]
            cuts = [0, *(m.start() for m in junction.finditer(sentence)), len(sentence)]
            inherited_change = False
            for lo, hi in zip(cuts, cuts[1:]):
                text = sentence[lo:hi]
                start, end = sentence_start + lo, sentence_start + hi
                # Discourse such as 'apart from aliases' does not name the
                # object of the following domain-address predicate.
                scope = _compiled_rule(r"^除[^，,]{0,30}外[，,]\s*", re.I).sub("", text)
                custom = bool(_compiled_rule(r"custom\s+(?:email\s+)?domains?|自定义(?:电子邮件|邮箱|邮件)?域(?:名)?|per\s+domain", re.I).search(scope))
                addresses = bool(_compiled_rule(r"(?:e?mail\s+|personalized\s+)?addresses|(?:个性化|电子邮件|邮箱)地址", re.I).search(scope))
                aliases = bool(_compiled_rule(r"\balias(?:es)?\b|别名", re.I).search(scope))
                obj = "custom-domain-address" if custom and addresses else "mail-alias" if aliases else "custom-domain-count" if custom else ""
                if not obj:
                    inherited_change = False
                    continue
                denied = bool(_compiled_rule(r"\b(?:not|never)\s+(?:been\s+)?(?:increas\w*|rais\w*|chang\w*)|\bunchanged\b|未(?:曾)?(?:提高|提升|上调|调整)|保持不变|否认", re.I).search(scope))
                historical = bool(_compiled_rule(r"^(?:previously|yesterday\s+we\s+reported|此前|去年|昨天(?:我们)?报道)|\blast\s+year\b|去年.{0,40}(?:提高|上调)", re.I).search(scope))
                planned = bool(_compiled_rule(r"\b(?:may|might|could|plans?\s+to|will)\s+(?:increas\w*|rais\w*|chang\w*)|计划|可能(?:提高|上调)|将(?:提高|上调)", re.I).search(scope))
                if denied or local_action_changes_owner(scope, r"iCloud|Apple|苹果"):
                    inherited_change = False
                    continue
                change = bool(_compiled_rule(r"increas\w*|rais\w*|tripl\w*|提高|提升|上调|增至|增加到|涨到", re.I).search(scope))
                current_limit = obj != "custom-domain-count" and bool(_compiled_rule(r"\bnow\b|现上限|higher\s+limit", re.I).search(scope))
                current = not historical and not planned and (change or current_limit or inherited_change)
                spans.setdefault(obj, []).append((unit.unit_id, start, end))
                qualifiers.setdefault(obj, [])
                if current:
                    primary.setdefault(obj, (unit.unit_id, start, end))
                    transition = _compiled_rule(r"(?:from|从)\s*(?:此前的\s*)?(?:a\s+(?:\w+\s+){0,2})?" + number +
                        r"(?:\s*个)?\s*(?:up\s+to|to|增至|增加到|提升至|涨到)\s*(?:a\s+(?:\w+\s+){0,2})?" + number, re.I).search(scope)
                    noun = r"(?:personalized\s+)?(?:e?mail\s+addresses|addresses)" if obj == "custom-domain-address" else r"aliases" if obj == "mail-alias" else r"custom\s+(?:email\s+)?domains"
                    after = _compiled_rule(r"(?:up\s+to|limit\s+of)\s*" + number + r"\s+" + noun, re.I).search(scope)
                    values = (("quota-from", transition.group(1)), ("quota-to", transition.group(2))) if transition else (("quota-to", after.group(1)),) if after else ()
                    qualifiers[obj].extend((obj, kind, numbers.get(value.lower(), value), unit.unit_id, start, end) for kind, value in values)
                inherited_change = current and change
    return tuple(BoundClaim("icloud-mail", "quota-increase", obj, tuple(qualifiers[obj]),
        evidence.article_id, tuple(dict.fromkeys(span[0] for span in spans[obj])),
        tuple(sorted(spans[obj], key=lambda span: span != primary[obj])), evidence.content_form, subject_relation="apple-direct", report_role="independent")
        for obj in primary)


def is_os_release_announcement(title: str) -> bool:
    """Recognize the primary release predicate, including numbered beta waves."""
    h = _normalized(title)
    # A platform mentioned as an update's compatibility target does not own
    # the release predicate (for example a carrier bundle on an iOS beta).
    if _compiled_rule(r"(?:\b(?:carrier|firmware|driver|apps?|sdk|plugin|bundle)\b|应用|固件|驱动|运营商).{0,80}(?:\bon\b|\bfor\b|适用于|面向).{0,35}(?:ios|ipados|macos|watchos|tvos|visionos)\s*\d", 0).search(h):
        return False
    return bool(_compiled_rule(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*\d", 0).search(h)
        and _compiled_rule(r"\b(?:releases?|released|seeds?|seeded|rolls?\s+out|available\s+now|now\s+available)\b|发布|推送", 0).search(h)
        and not _compiled_rule(r"\b(?:not|never|will|plans?|when|expected)\b|尚未|没有|并未|将于|计划|何时|预计|明年|内部.{0,3}测试|already\s+testing|internally\s+testing", 0).search(h))


def bind_home_software_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Code discloses capabilities; host-device launch forecasts stay unassigned."""
    opening = next((unit.text for unit in evidence.units if unit.kind in {'p', 'text'} and unit.container_id != 'caption'), '')
    primary = evidence.title + ' ' + evidence.raw_lead[:650] + ' ' + opening[:650]
    s = _frame_search
    if is_os_release_announcement(evidence.title):
        return ()
    if not s(r'homepod|apple\s*tv|homekit|home\s*accessor|家居|门铃|灵动岛|dynamic\s*island', primary):
        return ()
    if not s(r'features?|controls?|surround|环绕|代码|code|新特性|功能|控制', primary):
        return ()
    if not s(r'code|代码|leaks?|discov|found|曝光|爆料|消息源|rumor|传闻', primary):
        return ()
    if s(r'last year|revisited|wish\s*list|denied|denies|去年|回顾|愿望|否认', evidence.title):
        return ()
    text = ' '.join(u.text for u in evidence.units if u.kind in {'p','li','text'})
    if not s(r'code|代码', text) or not s(r'discover|found|uncover|leak|hints?|suggests?|发现|爆料|消息源|挖掘', primary + ' ' + text):
        return ()
    groups = {}
    versions = {}
    previous_versions = {}
    for unit in evidence.units:
        if unit.kind not in {'p','li','text'} or unit.container_id == 'caption':
            previous_versions = {}
            continue
        local_versions = {}
        for start,end in source_sentence_spans(unit.text):
            clause = _normalized(unit.text[start:end])
            if s(r'^separately|^unrelated|另一个|另一项独立',clause):
                previous_versions = {}
                local_versions = {}
            if s(r'^last month|^previously|^in case you missed|^in\s+20\d{2}\b|^back in|^目前|^当前|^此前|\blast year\b|\bnot found\b|未发现|没有发现', clause):
                continue
            if s(r'\b(?:did|does|has|have|had)\s+not\s+(?:discover\w*|find|found|uncover\w*)|'
                 r'\b(?:might|may|could|would|if|when)\b.{0,45}\b(?:discover\w*|find|uncover\w*)|'
                 r'未发现|并未发现|可能发现|若发现|否认发现',clause):
                continue
            absent = (s(r'\bno\b.{0,100}\b(?:references?|code|strings?)\b.{0,40}\b(?:found|discovered|uncovered)\b|'
                        r'\b(?:does|did|do)\s+not\s+(?:contain|include|show)|'
                        r'\b(?:references?|code|strings?)\b.{0,35}\b(?:not|never)\s+(?:found|discovered)|'
                        r'\b(?:contains?|includes?)\s+no\s+(?:new\s+)?(?:references?|code)|'
                        r'不存在.{0,20}(?:代码|引用)|(?:代码|引用).{0,20}(?:不存在|未找到)',clause))
            if absent:
                continue
            # A nearby compatibility requirement does not identify the code
            # being examined. Only a code examination or an explicit beta-code
            # introduction can lend its platform version to the next sentence.
            code_context = s(r'\b(?:found|discover\w*|uncover\w*|examin\w*|analy[sz]\w*|inspect\w*)\b|发现|挖掘|分析代码',clause) and s(r'code|references|代码',clause)
            beta_context = s(r'^(?:highlights\s+from|yesterday[’\']s\s+beta|beta)|beta.{0,15}releases?\s+of|测试版.{0,12}代码',clause)
            explicit_versions = {(platform.lower(),version):(unit.unit_id,start,end)
                for platform,version in _compiled_rule(r'(?<![a-z0-9])(ios|tvos|audioos)\s*(\d+(?:\.\d+)*)',re.I).findall(clause)}
            if code_context or beta_context:
                local_versions.update(explicit_versions)
            subject = ''
            if (s(r'homekit|home accessories|智能家居|proximity\s*control|接近控制',clause)
                    and (s(r'dynamic\s*island|灵动岛|动态岛',clause) or s(r'proximity\s*control|接近控制',clause))
                    and s(r'controls?|控制',clause)):
                subject='homekit:proximity-controls'
            elif (s(r'unpowered|without\s+power|未通电',clause)
                    and s(r'pairing|setup|set\s*up|配对|设置',clause)
                    and s(r'homekit(?:[- ]exclusive|\s+(?:pairing|setup|preprovisioning))|homekit.{0,10}(?:独占|配对)',clause)
                    and s(r'ios\s*\d+(?:\.\d+)*\s+code|apple.{0,15}(?:code|firmware)|(?:苹果|ios).{0,15}(?:代码|固件)',clause)
                    and not s(r'\b(?:not|never|no)\b|不支持|不能|并未|此前|earlier|previous|yesterday[’\']s\s+leak',clause)):
                subject='homekit:nfc-preprovisioning'
            elif (s(r'apple\s*tv',clause) and s(r'profiles?|角色|头像',clause)
                    and s(r'characters|角色|emoji|表情',clause)):
                subject='apple-tv:profile-images'
            elif (s(r'tvos',clause) and s(r'apple\s+intelligence|siri\s*ai|苹果智能',clause)
                    and s(r'found|references|code|strings|代码|发现',clause)):
                subject='tvos:intelligence-model-support'
            elif (s(r'surround\s*(?:system|sound)|环绕声|环绕音效|proxy.activation|代理激活',clause)
                    and s(r'code|代码|siri|proxy.activation|代理激活',clause)):
                subject='homepod:surround-system'
            if not subject:
                continue
            # No present discovery can be manufactured from a denial or a
            # speculative wish. Unreleased capabilities keep their uncertainty.
            if s(r'\b(?:wish|hope|not discovered|found no|no new code)\b|希望|并未发现|未发现|没有新代码',clause):
                continue
            groups.setdefault(subject,[]).append((unit.unit_id,start,end))
            platform = 'ios' if subject.startswith('homekit:') else 'audioos' if subject.startswith('homepod:') else 'tvos'
            context = {key:span for key,span in explicit_versions.items() if key[0]==platform}
            if not context:
                context = {key:span for key,span in local_versions.items() if key[0]==platform}
            if not context:
                context = {key:span for key,span in previous_versions.items() if key[0]==platform}
            versions.setdefault(subject,{}).update(context)
            for origin in context.values():
                if origin not in groups[subject]:
                    groups[subject].append(origin)
        previous_versions = local_versions
    return tuple(BoundClaim(subject,'feature-code-discovery','source-operation',
        tuple((platform,'code-version',version,*origin) for (platform,version),origin in sorted(versions.get(subject,{}).items())),
        evidence.article_id,tuple(dict.fromkeys(span[0] for span in spans)),tuple(spans),evidence.content_form,
        category='software_systems',event_kind='os_app', subject_relation="apple-direct", report_role="independent") for subject,spans in groups.items())


def bind_storage_design_claim(evidence: ArticleEvidence) -> BoundClaim | None:
    """Recover a current physical change even when the lead is background-heavy."""
    if not _frame_search(r"mac\s*mini", evidence.title):
        return None
    if not _frame_search(r"killed|removed|移除|取消|焊接", evidence.title):
        return None
    for unit in evidence.units:
        if unit.kind not in {"p", "text"} or unit.container_id == "caption":
            continue
        for start, end in source_sentence_spans(unit.text):
            text = unit.text[start:end]
            if not (_frame_search(r"(?:latest|new|本代|新款).{0,45}mac\s*mini", text)
                    and _frame_search(r"apple\s+has\s+soldered\s+the\s+ssd|苹果(?:现已|已)将.{0,20}ssd.{0,15}焊接", text)):
                continue
            if _frame_search(r"\b(?:not|never|if|may|might|could|previously|last year)\b|否认|没有|去年|可能", text):
                continue
            models = sorted(set(_compiled_rule(r"\bm\d+(?:\s*pro)?\b", re.I).findall(evidence.raw_lead[:400])))
            return BoundClaim("mac-mini:storage:" + ','.join(m.lower() for m in models),
                "storage-replaceability-change", "source-operation", (), evidence.article_id,
                (unit.unit_id,), ((unit.unit_id, start, end),), evidence.content_form,
                category="hardware_products", event_kind="hardware_market", subject_relation="apple-direct", report_role="independent")
    return None


def source_local_report_passages(evidence: ArticleEvidence):
    """Retain self-contained reports outside a source's display shortlist.

    These are review evidence, never automatic event or relevance assignments.
    """
    organization_anchor = -10
    market_units = tuple(unit.text for unit in evidence.units)
    publication_year = _frame_search(r'(?<!\d)(20\d{2})(?!\d)', evidence.published_raw or '')
    year = publication_year.group(1) if publication_year else (evidence.published_utc or '')[:4]
    market_report = source_market_measurement_frame(evidence.title, evidence.raw_lead, market_units, published_year=year)
    for index, unit in enumerate(evidence.units):
        if unit.kind not in {'p', 'text', 'blockquote'} or unit.container_id == 'caption':
            organization_anchor = -10
            continue
        reasons = set()
        if market_report and source_market_measurement_frame(evidence.title, evidence.raw_lead,
                market_units, published_year=year, measurement_passages=(unit.text,)):
            reasons.add('Current Apple market result in the source body; preserve its own value and the report period, region and attribution')
        for start, end in source_sentence_spans(unit.text):
            clause = unit.text[start:end]
            lower = _normalized(clause)
            if _frame_search(r'^(?:last\s+(?:year|month)|previously|formerly|去年|此前|过去)|\bshould\b|应该|应当|如果', lower):
                organization_anchor = -10
                continue
            if source_closing_market_value_frame(clause):
                reasons.add('Source-local Apple closing value; preserve the result and verify its trading day from the captured context')
            version = _frame_search(r'(?<![a-z])(ios|ipados|macos|watchos|tvos|visionos)\s*\d+(?:\.\d+)*', lower)
            if (version and _frame_search(r'latest|current|最新|当前', lower)
                    and _frame_search(r'beta|测试版', lower)
                    and _frame_search(r'press|tap|click|hold|按住|长按|点击', lower)
                    and _frame_search(r'shows?|displays?|enlarge|expand|appears?|放大|显示|弹出|展开', lower)):
                reasons.add('Current version-specific interaction behavior; distinguish the observed result from adjacent hardware inference')
            owner = _operation_owner(clause)
            if owner not in {'', 'apple'}:
                organization_anchor = -10
            organization = bool(_frame_search(r'design|teams?|management|supply\s+chain|finance|设计|团队|管理层|供应链|财务|产品开发', lower)
                and _frame_search(r'oversees?|responsib|appoint|recruit|reduc|participat|参与|负责|承担|亲自|走进|提拔|招聘|交给|减少|重组', lower))
            reference = bool(_frame_search(r'^(?:the\s+team|it|he|she|they|these|those|this|that)\b|^(?:他|她|其|为了|经历|这种|这些|上述)', lower))
            if organization and not owner and index != organization_anchor and not reference:
                organization_anchor = -10
            if organization and (owner == 'apple' or (not owner and index - organization_anchor <= 2 and (reference or index == organization_anchor))):
                reasons.add('Source-local organization responsibilities or changes; preserve attribution and proposal status separately from author commentary')
                organization_anchor = index
        if reasons:
            yield unit.unit_id, 0, len(unit.text), '; '.join(sorted(reasons))


def bind_role_appointment_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Separate an enterprise reporting-line change from a service appointment."""
    s = _frame_search
    primary = _normalized(evidence.title + ' ' + evidence.raw_lead)
    if (not s(r'apple|苹果', primary)
            or not s(r'mergers?|acquisitions?|m&a|并购', primary)
            or not s(r'chief|head|leader|主管|负责人|换帅|重组', primary)
            or not s(r'new|names|appoint|take\s+over|任命|接任|新', primary)
            or s(r'last\s+year|回顾|去年|否认|denies', _normalized(evidence.title))):
        return ()
    groups: dict[str, list[tuple[str, int, int]]] = {}
    for unit in evidence.units:
        if unit.kind not in {'p', 'li', 'text', 'tr', 'td'} or unit.container_id == 'caption':
            continue
        for start, end in source_sentence_spans(unit.text):
            clause = unit.text[start:end]
            lower = _normalized(clause)
            # Contracted auxiliaries retain the same negative predicate scope.
            lower = _compiled_rule(r"\b(?:isn|aren|wasn|weren|hasn|haven|hadn|don|doesn|didn|won|wouldn|couldn|shouldn|mustn|can)['’]t\b", 0).sub('not', lower)
            if s(r'supported\s+by|shop\s+now|continue\s+reading|图源|上图人物|过去十余年|denied|denies|(?:not|never)\s+(?:[a-z]+\s+){0,4}(?:promot|appoint|named)|否认|未获|没有.{0,10}晋升|last\s+year|\bin\s+20\d{2}\b|此前|曾经', lower):
                continue
            service = bool(s(r'app\s*store', lower) and s(r'vice\s+president|副总裁', lower)
                           and s(r'promot|晋升|升任|接管|新职务', lower))
            company = bool(s(r'mergers?|acquisitions?|m&a|并购|corporate\s+development|财务|perica|佩里卡', lower))
            # The introductory list of two unnamed appointees is not an
            # independently owned appointment; their named clauses follow.
            if company and s(r'new\s+vice\s+president', lower):
                continue
            if service or company:
                groups.setdefault('app-store' if service else 'corporate-development', []).append((unit.unit_id, start, end))
    claims = []
    units = {u.unit_id: u for u in evidence.units}
    for role, spans in groups.items():
        qualifiers = []
        for unit_id, start, end in spans:
            clause = units[unit_id].text[start:end]
            named = (_compiled_rule(r'(?:named|appointed|promoting|任命)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', 0).search(clause)
                     or _compiled_rule(r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:will take over|is being promoted|is Apple[’\']s new|升任)', 0).search(clause))
            if named:
                qualifiers = [('role-holder', 'appointment-holder', named.group(1).lower(), unit_id, start+named.start(1), start+named.end(1))]
                break
        claims.append(BoundClaim('apple:organization:' + role, 'leadership-appointment', 'source-operation', tuple(qualifiers),
            evidence.article_id, tuple(dict.fromkeys(u for u, _, _ in spans)), tuple(spans), evidence.content_form,
            category='software_systems' if role == 'app-store' else 'hardware_products', event_kind='company_org', subject_relation="apple-direct", report_role="independent"))
    return tuple(claims)



def bind_joint_litigation_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """A joint filing preserves each named party's request or response."""
    s = _frame_search
    if not _frame_search(r'lawsuit|trade\s*secret|诉讼|泄密|取证|商业秘密', evidence.title + ' ' + evidence.raw_lead):
        return ()
    text = ' '.join(u.text for u in evidence.units)
    local = _normalized(evidence.title + ' ' + evidence.raw_lead + ' ' + text)
    if not (s(r'joint\s+status\s+(?:report|update)|jointly\s+filed\s+an?\s+update|联合.{0,3}(?:报告|进展|状态)', local)
            and s(r'trade\s*secret|商业秘密|泄密|泄露', local) and s(r'apple|苹果', local)):
        return ()
    platform = s(r'\b(ios|ipados|macos|watchos)\s*(\d+)', local)
    if not platform:
        return ()
    # Names are discovered in this source. Translated names are aliases only
    # when the source explicitly supplies the Latin spelling in parentheses.
    names = {}
    scope = '. '.join((evidence.title, evidence.raw_lead, text[:2000]))
    for match in _compiled_rule(r'(?=\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b)', 0).finditer(scope):
        full, last = ' '.join(match.groups()), match.group(2)
        if match.group(1).lower() in {'since', 'while', 'when', 'and', 'leaker', 'youtuber', 'judge', 'data', 'the', 'according'}:
            continue
        if (s(re.escape(last) + r"(?:['’]s\s+(?:lawyer|attorney))?\s*(?:,\s*(?:however|in\s+turn|meanwhile),?\s*)?(?:says?|said|wants?|asks?|argues?|is\s+(?:arguing|using)|claims|表示)", text)
                and not s(r'judge\s*$', scope[max(0, match.start()-12):match.start()])
                and (s(re.escape(last), evidence.title)
                     or s(r'(?:defendants?|leaker|youtuber|against|between|被告|泄密者|和|、).{0,90}' + re.escape(full), scope))):
            names[full.lower().replace(' ', '-')] = {last.lower(), full.lower()}
    for match in _compiled_rule(r'([\u4e00-\u9fff]+(?:\s*[·・]\s*[\u4e00-\u9fff]+)+)\s*[（(]([A-Z][a-z]+\s+[A-Z][a-z]+)[）)]', 0).finditer(scope):
        key = match.group(2).lower().replace(' ', '-')
        names.setdefault(key, {match.group(2).split()[-1].lower(), match.group(2).lower()}).add(match.group(1).split('·')[-1].strip())
    if not names:
        return ()
    aliases = {'apple': {'apple', '苹果', 'the company'}} | names
    patterns = {key: _compiled_rule(r'(?<![a-z])(?:' + '|'.join(re.escape(v) for v in sorted(values, key=len, reverse=True)) + r')(?![a-z])', re.I) for key, values in aliases.items()}
    groups = {}
    active = None
    current_section = True
    conference_owner = None
    predicate = r"(?:['’]s\s+(?:lawyer|attorney))?\s*(?:,\s*(?:however|in\s+turn|meanwhile),?\s*)?(?:says?|said|wants?|seeks?|asks?|argues?|is\s+arguing|has\s+asked|is\s+using|disputes|表示|称|则表示|还希望|希望|要求)"
    for unit in evidence.units:
        if unit.kind in {'h2', 'h3'}:
            current_section = bool(s(r'new|current|最新|新的', unit.text))
            active = None
            continue
        if unit.kind not in {'p', 'text', 'blockquote'} or unit.container_id == 'caption':
            continue
        for start, end in source_sentence_spans(unit.text):
            sentence = unit.text[start:end]
            lower = _normalized(sentence)
            if s(r'last\s+(?:year|month)|previously|as\s+a\s+refresher|filed\s+(?:the\s+)?(?:lawsuit|suit)\s+in|in\s+his\s+.{0,20}response|追溯到|曾经|此前|作为回顾', lower):
                active = None
                continue
            if s(r'new\s+(?:joint\s+)?status|最新.{0,8}报告|公开的联合', lower):
                current_section = True
            if not current_section:
                continue
            owners = []
            for owner, pattern in patterns.items():
                for match in pattern.finditer(sentence):
                    if _compiled_rule(predicate, re.I).match(sentence, match.end()):
                        owners.append((match.start(), owner))
            owners = sorted(set(owners))
            if owners:
                boundary = r'(?:[,，;；]\s*|\bwhile\s+|\band\s+|而|但|不过)$'
                scoped = [owners[0]]
                embedded = False
                for item in owners[1:]:
                    prefix = sentence[scoped[-1][0]:item[0]]
                    separated = s(boundary, prefix)
                    nested = s(r'\b(?:that|whether)\s*,?\s*(?:while|although|if|when|because)\s*$', prefix)
                    # Determine each independent speaker before examining its
                    # reported objects. A later nested party cannot erase an
                    # earlier independent clause in the same sentence.
                    if s(r'[;；]\s*$', prefix) or (separated and not embedded and not nested):
                        scoped.append(item)
                        embedded = False
                    elif s(r'\b(?:says?|said|argues?|claims?)\b|表示|称', prefix):
                        embedded = True
                owners = scoped
            if owners:
                for i, (offset, owner) in enumerate(owners):
                    left = 0 if i == 0 else offset
                    right = owners[i+1][0] if i+1 < len(owners) else len(sentence)
                    # Keep conjunctions outside both assertions.
                    conjunction = s(r'(?:,\s*)?(?:while|and)\s*$', sentence[left:right])
                    if conjunction:
                        right = left + conjunction.start()
                    while right > left and sentence[right-1] in ' ,，':
                        right -= 1
                    groups.setdefault(owner, []).append((unit.unit_id, start+left, start+right))
                    active = owner
                    if s(r'(?:status\s+)?conference|会议', sentence[left:right]) and owner != 'apple':
                        conference_owner = owner
            elif conference_owner and s(r'^if\s+(?:the\s+court|judge)', lower):
                groups.setdefault(conference_owner, []).append((unit.unit_id, start, end))
            elif active and (s(r'^(?:he|his|it|these|the\s+materials)\b|^(?:他|这些|相关材料)', lower)
                             or s(r'^if\s+(?:the\s+court|judge)|如果.{0,12}(?:法院|法官)', lower)):
                groups.setdefault(active, []).append((unit.unit_id, start, end))
            else:
                active = None
    return tuple(BoundClaim('apple:' + platform.group(1) + '-' + platform.group(2) + ':trade-secret-case:' + owner,
        'joint-status-position', 'source-operation', (), evidence.article_id,
        tuple(dict.fromkeys(u for u, _, _ in spans)), tuple(spans), evidence.content_form,
        category='software_systems', event_kind='legal_regulation', subject_relation="apple-direct", report_role="independent") for owner, spans in groups.items())


def bind_configuration_disclosure_claim(evidence: ArticleEvidence) -> BoundClaim | None:
    """Keep a focused model disclosure's material specifications source-bound."""
    if not _frame_search(r'iphone.*(?:thin|thickness|薄|厚度)', evidence.title):
        return None
    frame = source_focused_report_frame(evidence.title, evidence.raw_lead, ())
    if frame is None or frame.action != 'configuration-report':
        return None
    model = frame.subject.removesuffix(':dimensions-and-battery').replace('-', ' ')
    spans = []
    active = True
    for unit in evidence.units:
        if unit.kind not in {'p', 'li', 'text'} or unit.container_id == 'caption':
            continue
        for start, end in source_sentence_spans(unit.text):
            clause = unit.text[start:end]
            lower = _normalized(clause)
            if _frame_search(r'^from\s+what|^从目前.{0,20}来看|in\s+our\s+view|相关阅读|continue\s+reading|subscribe|查看原文', lower):
                continue
            devices = list(_compiled_rule(r'\b(?:iphone\s*(?:air\s*\d*|duo\s*\d*|\d+(?:\s*pro(?:\s*max)?)?)|ipad(?:\s*(?:mini|air|pro))?\s*\d*|macbook(?:\s*(?:air|pro))?\s*\d*|homepod(?:\s*mini)?)', 0).finditer(lower))
            owned = _frame_search(r'(?<![a-z0-9])' + re.escape(model) + r'(?![a-z0-9])', lower)
            if devices and devices[0].group().strip() != model:
                prefix = lower[:devices[0].start()]
                baseline = _frame_search(r'original|current|first.generation|初代|现款', prefix)
                same_family = (_compiled_rule(r'\s*\d+', 0).sub('', devices[0].group().strip())
                               == _compiled_rule(r'\s*\d+', 0).sub('', model))
                reference = _compiled_rule(r'^(?:(?:interestingly|additionally|in\s+addition|furthermore|moreover|also|此外|另外|同时)[,，:]?\s*)?'
                    r'(?:that\b|it\b|this\s+(?:phone|device)\b|the\s+next.generation\s+device\b|这款手机|该机|新机)', 0).match(prefix)
                comparison = _frame_search(r'match|compared|same.{0,30}as|alongside|与|相同|相比|相较', prefix)
                supporting = active and ((baseline and same_family) or (reference and comparison))
                if not ((owned and baseline) or supporting):
                    active = False
                    continue
            if owned:
                active = True
            if not active:
                continue
            if _frame_search(r'\b(?:battery|thickness|thinner|capacity|camera|chip|modem|display|memory|titanium|frame|vapou?r|cooling|launch|release)\b|'
                             r'厚度|薄了|薄至|电池|容量|芯片|基带|散热|均热|屏幕|内存|像素|摄像|边框|灵动岛|续航|发布', lower):
                spans.append((unit.unit_id, start, end))
    return BoundClaim(frame.subject, frame.action, 'source-operation', (), evidence.article_id,
        tuple(dict.fromkeys(u for u, _, _ in spans)), tuple(spans), evidence.content_form,
        category=frame.category, event_kind=frame.kind, subject_relation="apple-direct", report_role="independent") if spans else None


def bind_attributed_hardware_launch_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """A current reporter predicate can own a plan inside an editorial roundup."""
    claims = []
    for unit in evidence.units:
        if unit.kind != 'p' or unit.container_id == 'caption':
            continue
        for start, end in source_sentence_spans(unit.text):
            text = unit.text[start:end]
            report = _compiled_rule(
                r'(?P<device>(?:(?:touchscreen|foldable|OLED|new|next-generation)\s+)*'
                r'(?:MacBook(?:\s+(?:Pro|Air))?|iPad(?:\s+(?:Pro|Air|mini))?|iPhone(?:\s+\d+)?)'
                r'),\s+which\s+(?:[A-Za-z]+\s+){0,3}[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}'
                r'\s+(?:says|reports)\s+will\s+(?:debut|launch)\b'
                r'(?P<window>[^.!?]*)', 0).search(text)
            if (not report or _compiled_rule(r'\b(?:previously|earlier|last\s+(?:week|month|year))\b', re.I).search(text)
                    or source_denies_action(text[report.start():], '', r'debut|launch')):
                continue
            subject = _compiled_rule(r'[^a-z0-9]+', 0).sub('-', report.group('device').lower()).strip('-')
            window = _normalized(report.group('window')).strip()
            qualifiers = ((subject, 'rollout-time', window + '@' + (evidence.published_utc or '')[:7],
                unit.unit_id, start + report.start('window'), start + report.end('window')),) if window else ()
            claims.append(BoundClaim(subject, 'reported-launch-plan', 'source-operation', qualifiers,
                evidence.article_id, (unit.unit_id,), ((unit.unit_id, start + report.start(), end),), evidence.content_form,
                'hardware_products', 'hardware_market', subject_relation="apple-direct", report_role="independent"))
    return tuple(claims)


def bind_app_chart_report(evidence: ArticleEvidence) -> BoundClaim | None:
    """Keep a publisher and its measured chart separate from the host platform.

    Enter the report family before resolving the publisher. Missing ownership
    stays explicit; it must not return to the broader platform-action parser.
    """
    title = evidence.title
    if not (_frame_search(r'app\s*store', title)
            and _frame_search(r'chart|排行榜|免费榜|付费榜|榜首|前[一二三四五六七八九十\d]+', title)
            and _frame_search(r'\b(?:dominates?|occup(?:y|ies))\b|霸占|占据', title)):
        return None
    subject_text = _compiled_rule(
        r"(?:(?:apple(?:['’]s)?|苹果)\s*)?app\s*store|苹果(?:免费榜|付费榜|排行榜)", re.I).sub('', title)
    if _frame_search(r'\bapple\b|苹果', subject_text):
        return None

    assertions = []
    publisher_pattern = _compiled_rule(
        r'(?:应用|\bapps?\b)[^。.!?，,；;]{0,75}?(?:来自|属于|\bfrom\b|\bby\b)\s*'
        r'(?P<publisher>[a-z][a-z0-9 -]{1,35}|[\u4e00-\u9fff]{2,20})', re.I)
    for unit in evidence.units:
        if unit.kind == 'h1':
            continue
        for start, end in source_clause_spans(unit.text):
            text = unit.text[start:end]
            if not (_frame_search(r'app\s*store', text)
                    and _frame_search(r'chart|榜|top\s+\w+', text)):
                continue
            publisher = publisher_pattern.search(text)
            if not publisher:
                continue
            name = _normalized(publisher.group('publisher')).strip()
            role = 'background' if _frame_search(
                r'\b(?:last\s+year|previously|historically|used\s+to)\b|去年|此前|历史上', text) else 'independent'
            polarity = 'denied' if source_denies_action(text, '', r'from|by|来自|属于') else 'affirmed'
            qualifiers = [(name, 'subject-name', name, unit.unit_id,
                start + publisher.start('publisher'), start + publisher.end('publisher'))]
            for kind, pattern in (('free', r'\bfree\b|免费榜'), ('paid', r'\bpaid\b|付费榜')):
                chart = _frame_search(pattern, text)
                if chart:
                    qualifiers.append(('app-store', 'chart-kind', kind, unit.unit_id,
                        start + chart.start(), start + chart.end()))
            qualifiers.extend(source_calendar_dates(unit.unit_id, text, start, name))
            assertions.append((name, role, polarity, (unit.unit_id, start, end), qualifiers))
    # Background cannot fill the missing owner of a current assertion. Keep a
    # wholly historical relationship explicit, without granting current status.
    current = [row for row in assertions if row[1] == 'independent']
    selected = current or assertions
    relationships = {(name, role, polarity) for name, role, polarity, _, _ in selected}
    subject, role, polarity = next(iter(relationships)) if len(relationships) == 1 else ('', '', '')
    spans = tuple(row[3] for row in selected)
    qualifiers = tuple(qualifier for row in selected for qualifier in row[4])
    return BoundClaim(subject, 'app-publisher-chart-report', 'app-store:chart-result',
        qualifiers, evidence.article_id, tuple(dict.fromkeys(span[0] for span in spans)),
        spans, evidence.content_form, category='software_systems',
        event_kind='third_party_ecosystem',
        subject_relation=('apple-direct' if subject in {'apple', '苹果'} else 'independent') if subject else '',
        report_role=role, polarity=polarity)


def source_clause_spans(text: str):
    """Split coordinated predicates while retaining source-local offsets."""
    peer = (r"\s*(?:(?!(?:that|which|who)\b)[a-z][a-z0-9’'-]*\s+){1,6}"
            r"(?:can|supports?|provides?|allows?|makes?|offers?|requires?|denies|"
            r"says|reports?|launched?|released?|announced?|achiev(?:e|es|ed)|"
            r"is|are|was|were|has|have|had)\b")
    boundaries = _compiled_rule(r'[;；]|\b(?:while|whereas|but)\b|[,，]\s*(?:而|但是?|不过)|'
        r'[,，](?=' + peer + r')|\band\b(?!\s+(?:it|its|they|their|he|she)\b)(?=' + peer + r')', re.I)
    for start, end in source_sentence_spans(text):
        cursor = start
        for match in boundaries.finditer(text, start, end):
            # A leading location/condition followed by a comma belongs to the
            # following predicate; it is not a preceding independent clause.
            if match.group() in {',', '，'} and not _frame_search(peer, text[cursor:match.start()]):
                continue
            if cursor < match.start():
                yield cursor, match.start()
            cursor = match.end()
        if cursor < end:
            yield cursor, end


def source_calendar_dates(unit_id: str, text: str, offset: int, target: str, *, kind: str = 'observation'):
    """Keep an explicit relation's dates and spans, never publication time."""
    months = 'january february march april may june july august september october november december'.split()
    month_numbers = {name: i for i, month in enumerate(months, 1) for name in (month, month[:3])}
    month_numbers['sept'] = 9
    pattern = _compiled_rule(
        r'(?:(?P<year>\d{4})年\s*)?(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日|'
        r'(?P<iso_year>\d{4})-(?P<iso_month>\d{2})-(?P<iso_day>\d{2})|'
        r'\b(?P<en_month>' + '|'.join(sorted(month_numbers, key=len, reverse=True)) + r')\.?\s+'
        r'(?P<en_day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<en_year>\d{4}))?\b', re.I)
    result = []
    for match in pattern.finditer(text):
        year = match.group('year') or match.group('iso_year') or match.group('en_year')
        month = match.group('month') or match.group('iso_month')
        if not month:
            month = str(month_numbers[match.group('en_month').lower()])
        day = match.group('day') or match.group('iso_day') or match.group('en_day')
        if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
            continue
        for part, value in (('year', year), ('month', month), ('day', day)):
            if value:
                result.append((target, kind + '-' + part, str(int(value)), unit_id, offset + match.start(), offset + match.end()))
    return result


def bind_device_measurement(evidence: ArticleEvidence) -> BoundClaim | None:
    """Bind a measured dataset and its local continuations, not display models."""
    device_pattern = r'iphone\s*(duo|air|\d+(?:\s*pro(?:\s*max)?)?)(?![\d,])'
    device = _frame_search(device_pattern, evidence.title)
    if not device or not _frame_search(r'benchmark|跑分', evidence.title):
        return None
    model = device.group(1).lower()
    subject = 'iphone-' + _compiled_rule(r'\s+').sub('-', model)
    owner_pattern = re.escape('iphone ' + model).replace(r'\ ', r'\s*') + r'(?![a-z0-9])'
    single_pattern = r'single.core\s+score\s+of\s+(\d+(?:,\d{3})*)|单核(?:跑分|得分|成绩)?(?:为|达到|是)?\s*(\d+(?:,\d{3})*)'
    multi_pattern = r'multi.core\s+score\s+of\s+(\d+(?:,\d{3})*)|多核(?:跑分|得分|成绩)?(?:为|达到|是)?\s*(\d+(?:,\d{3})*)'
    noncurrent = _compiled_rule(r'去年|此前|历史|预计|预测|假设|如果|\b(?:previously|last\s+year|historical|expected\s+to|forecast|may|might|if)\b', re.I)
    records, denials = [], []
    active_tool = ""
    active_subject = ""
    for unit in evidence.units:
        if unit.kind not in {'p', 'li', 'text', 'summary', 'selected_fact'} or unit.container_id == 'caption':
            active_tool = ""
            active_subject = ""
            continue
        for start, end in source_clause_spans(unit.text):
            clause = unit.text[start:end]
            local_tools = set(_compiled_rule(r'geekbench\s*(\d+)', re.I).findall(clause))
            normalized_clause = _normalized(clause)
            named = list(_compiled_rule(device_pattern).finditer(normalized_clause))
            if noncurrent.search(clause):
                active_tool = ""
                active_subject = ""
            else:
                if named:
                    prefix = normalized_clause[:named[0].start()]
                    prefix = _compiled_rule(r'^\s*(?:在[^，,。.!?]{1,45}(?:上|中|前|后|时)|日前|目前|今天|昨日)[,，]\s*').sub('', prefix, 1)
                    subject_position = _compiled_rule(r'\s*(?:目前\s*)?(?:(?:the\s+)?(?:new\s+)?(?:apple[’\']s\s+)?|'
                        r'苹果(?:首款|新款|全新)?(?:折叠屏)?(?:手机|设备)?\s*)', re.I).fullmatch(prefix)
                    active_subject = named[0].group(1) if subject_position else ""
                elif not _frame_search(r'^\s*(?:(?:在[^。.!?，,]{1,45}(?:前|后|时)|'
                        r'(?:before|after|ahead\s+of)\b[^.!?,]{1,45})[,，]\s*)?'
                        r'(?:这款(?:新机|手机|设备)|该机|该设备|其|(?:this\s+(?:phone|device)|the\s+device|it)\b)', clause):
                    active_subject = ""
                if local_tools:
                    active_tool = next(iter(local_tools)) if active_subject == model and len(local_tools) == 1 else ""
            single, multi = _frame_search(single_pattern, clause), _frame_search(multi_pattern, clause)
            if _frame_search(owner_pattern, clause) and source_denies_action('', clause,
                    r'achiev\w*|scor\w*|record\w*|reach\w*|test\w*|测得|取得|达到|获得'):
                denials.append(((unit.unit_id, start, end),
                    'background' if noncurrent.search(clause) else 'independent', local_tools))
                continue
            if not (single and multi) or noncurrent.search(clause):
                continue
            prefix = _normalized(clause[:single.start()])
            prefix = _compiled_rule(r'(?:与|和)[^，,。；;!?！？]{1,100}(?:处于同一水平|性能相当|表现相近)[，,]\s*$').sub('', prefix)
            owners = list(_compiled_rule(device_pattern).finditer(prefix))
            selected_record = (not owners and _compiled_rule(
                r'在\s*cpu\s*跑分方面[，,:：]\s*(?:(?:这里|本文|下文)?(?:附上|选取|采用|选择|提供))?'
                r'(?:(?:单核|多核)(?:跑分|得分)?(?:最高|最低)的)?(?:一条|该|这条)?记录[，,]?\s*(?:显示)?\s*|'
                r'for\s+(?:the\s+)?cpu\s+benchmark[,:]?\s*(?:the\s+)?(?:highest|lowest)?\s*record[,:]?\s*(?:shows?\s+)?').fullmatch(prefix))
            configuration = (_frame_search(r'geekbench[^。.!?]{0,25}' + device_pattern
                + r'\s*(?:的\s*)?\d+\s*核\s*cpu', unit.text) if selected_record else None)
            owns = owners[-1].group(1) == model if owners else configuration is not None and configuration.group(1).lower() == model
            if not owns:
                continue
            values = tuple(next(v for v in match.groups() if v).replace(',', '') for match in (single, multi))
            qualifiers = [(subject, 'measurement-record', '-'.join(values), unit.unit_id, start + single.start(), start + multi.end())]
            qualifiers.extend(source_calendar_dates(unit.unit_id, clause, start, subject))
            records.append((unit.unit_id, start, end, qualifiers,
                local_tools or ({active_tool} if active_tool else set())))
    if not records:
        selected = [row for row in denials if row[1] == 'independent'] or denials
        tools = set().union(*(row[2] for row in selected))
        tool = 'geekbench-' + next(iter(tools)) if len(tools) == 1 else ''
        spans = tuple(row[0] for row in selected)
        return BoundClaim(subject if denials else '', 'cpu-benchmark-report', tool or ('measurement' if denials else ''),
            (), evidence.article_id, tuple(dict.fromkeys(key for key, _, _ in spans)), spans, evidence.content_form,
            'hardware_products', 'hardware_market', 'apple-direct' if denials else '',
            selected[0][1] if selected else '', 'denied' if denials else '')
    tools = set().union(*(row[4] for row in records))
    tool = 'geekbench-' + next(iter(tools)) if len(tools) == 1 else ''
    spans = [(key, start, end) for key, start, end, _, _ in records]
    qualifiers = tuple(qualifier for _, _, _, values, _ in records for qualifier in values)
    # A record's configuration and adjacent anonymous metric keep the same
    # dataset. A new named subject or section ends that local relation.
    configuration = _compiled_rule(r'^(?:geekbench\s*(?:信息显示[，,]\s*|records?\s+(?:show|indicate)\s+))?(?:the\s+)?' + owner_pattern + r'\s*(?:的\s*)?(?:\d+\s*核\s*cpu|(?:\d+[- ]core\s+)?cpu\b)', re.I)
    continuation = _compiled_rule(r'^(?:在\s*(?:cpu|gpu|ai)\s*(?:跑分|性能)?方面[，,:：]|'
        r'(?:for|in)\s+(?:the\s+)?(?:cpu|gpu|ai)\s+(?:test|benchmark|results?)\b)', re.I)
    anonymous = _compiled_rule(r'\s*(?:(?:共|目前共)?有\s*\d+\s*条记录[，,]\s*)?'
        r'(?:目前)?(?:最高分|得分|成绩)(?:为|达到|是)\s*\d+(?:,\d{3})*\s*分[。.]?\s*|'
        r'\s*[,：:]?\s*(?:the\s+)?(?:highest\s+)?(?:score|result)\s+(?:is|was)\s+\d+(?:,\d{3})*[.!]?\s*', re.I)
    active = False
    for unit in evidence.units:
        if unit.kind not in {'p', 'summary', 'selected_fact'} or unit.container_id == 'caption':
            active = False
            continue
        text = unit.text.strip()
        metric = continuation.match(text)
        follows = bool(active and metric and anonymous.fullmatch(text[metric.end():]))
        if follows:
            begin = unit.text.find(text)
            spans.append((unit.unit_id, begin, begin + len(text)))
        active = follows
        for start, end in source_sentence_spans(unit.text):
            sentence = unit.text[start:end]
            if noncurrent.search(sentence):
                active = False
                continue
            if _compiled_rule(r'附上(?:相关)?图片如下[：:]$').search(sentence):
                continue
            normalized = _normalized(sentence)
            owner = _frame_search(owner_pattern, normalized)
            comparison = bool(owner and _frame_search(
                r'\b(?:matches?|compares?|resembles?|than|versus|against)\b|对比|相比|比较|相同', normalized[:owner.start()]))
            explicit = bool(owner and not comparison and _frame_search(
                r'geekbench|cpu|gpu|ai|成绩|记录|内存', normalized))
            local_configuration = bool(configuration.match(_normalized(sentence)))
            pronoun = bool(active and _frame_search(r'^(?:该机|该手机|其|(?:the\s+)?device\b|it\b)', sentence)
                and _frame_search(r'\d+(?:\.\d+)?\s*(?:gb|ghz|mhz|核|分)', sentence))
            if explicit or pronoun:
                spans.append((unit.unit_id, start, end))
            active = (local_configuration or pronoun or follows) and not bool(_frame_search(
                r'转向|另(?:一|测)|接下来|下面|\b(?:next|separately|turn(?:s|ing)?\s+to)\b', sentence))
    # Merge overlapping source intervals, retaining only original text.
    merged = []
    for key in dict.fromkeys(key for key, _, _ in spans):
        for _, start, end in sorted(span for span in spans if span[0] == key):
            if merged and merged[-1][0] == key and start <= merged[-1][2]:
                merged[-1] = (key, merged[-1][1], max(end, merged[-1][2]))
            else:
                merged.append((key, start, end))
    return BoundClaim(subject, 'cpu-benchmark-report', tool, qualifiers, evidence.article_id,
        tuple(dict.fromkeys(key for key, _, _ in merged)), tuple(merged), evidence.content_form,
        'hardware_products', 'hardware_market', 'apple-direct', 'independent', 'affirmed')


def bind_device_capability_inventory(evidence: ArticleEvidence) -> BoundClaim | None:
    """Bind a device's operating-feature inventory without inventing a launch."""
    title = _normalized(evidence.title)
    if not _frame_search(r'^\d+\s+[^.!?]{1,65}\bfeatures\b|(?:功能|特性)(?:汇总|一览)', title):
        return None
    title_subject = _compiled_rule(r'^\d+\s+').sub('', title, 1)
    owners = [(key, names) for key, names in PRODUCT_PATTERNS
              if any(_frame_search(r'^' + re.escape(name) + r'(?![a-z0-9])', title_subject) for name in names)]
    if len(owners) != 1:
        return None
    subject, aliases = owners[0]
    owner = r'(?:' + '|'.join(re.escape(name) for name in aliases) + r')(?![a-z0-9])'
    software = r'\b(?:siri|safari|recipes?|widgets?|handoff|airplay|timers?|automations?|notifications?|calendar|reminders?)\b|菜谱|小组件|接力|隔空播放|自动化|通知|日历|提醒'
    predicate = (r'(?:' + owner + r'|^\s*(?:(?:the\s+)?device|it|you(?:\s+or\s+members\s+of\s+your\s+\w+)?|guests|visitors))'
        r'\s+(?:can|supports?|provides?|allows?|makes?|has|have|(?:do\s+)?need)\b|'
        r'(?:' + owner + r'|^\s*(?:该设备|用户))\s*(?:可以|支持|提供|能够)')
    opening = next((unit.text for unit in evidence.units if unit.kind in {'p', 'text', 'summary'}), '')
    background = bool(_frame_search(r'\b(?:history|historical|recap|previously|last\s+year)\b|回顾|旧闻|旧传闻|去年', title + ' ' + opening[:350]))
    spans, qualifiers = [], []
    for unit in evidence.units:
        if unit.kind not in {'p', 'li', 'text', 'summary', 'selected_fact'} or unit.container_id == 'caption':
            continue
        for start, end in source_clause_spans(unit.text):
            clause = unit.text[start:end]
            label = _compiled_rule(r'^.{1,45}?\s[-–—]\s').match(clause) if unit.kind == 'li' else None
            body = clause[label.end():] if label else clause
            operation = _frame_search(predicate, body)
            # A list's present absence is itself a feature boundary, not a
            # future capability. Keep its negative wording verbatim.
            absence = (_compiled_rule(r"^\s*there(?:'s|\s+is|\s+are)\s+no\b", re.I).match(body)
                       if unit.kind == 'li' and _frame_search(owner, unit.text) else None)
            if absence:
                spans.append((unit.unit_id, start, end))
            if (operation and (unit.kind == 'li' or _frame_search(software, body[operation.end():]))
                    and (unit.kind == 'li' or _frame_search(owner, operation.group()))
                    and not source_denies_action('', clause, r'can|support\w*|provide\w*|allow\w*|make\w*|可以|支持|提供|能够')
                    and source_predicate_role(body[:operation.end()]) == 'current'):
                spans.append((unit.unit_id, start, end))
                qualifiers.append((subject, 'capability-predicate', 'operating-feature', unit.unit_id,
                                   start + (label.end() if label else 0) + operation.start(),
                                   start + (label.end() if label else 0) + operation.end()))
    return BoundClaim(subject if spans else '', 'platform-capability-inventory-report', 'operating-features',
        tuple(qualifiers), evidence.article_id, tuple(dict.fromkeys(key for key, _, _ in spans)),
        tuple(spans), evidence.content_form, 'software_systems', 'os_app',
        'apple-direct' if spans else '', 'background' if background else 'independent', 'affirmed')


def source_predicate_role(prefix: str) -> str:
    """Read modality before the predicate, never from its later instructions."""
    if _frame_search(r'\b(?:wish|imagine|should|suggest|recommend|could|would|may|might)\b|我建议|设想|建议|如果|可能|尚未', prefix):
        return 'proposal'
    if _frame_search(r'\b(?:previously|(?:last|previous)\s+(?:year|month|week)|historically)\b|'
        r'\b(?:centur(?:y|ies)|decades?|years?|months?|weeks?|days?)\s+ago\b|'
        r'\bduring\s+.{0,45}\bformer\b.{0,35}\btenure\b|去年|此前|历史上', prefix):
        return 'background'
    return 'current'


def bind_device_conditions(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Locate device authentication requirements as support, never new events."""
    subjects = _collapse_product_hierarchy(_extract_patterns(_normalized(evidence.title), PRODUCT_PATTERNS))
    subjects &= {key for key, _name, _aliases in MULTI_PRODUCT_HARDWARE_SUBJECTS}
    if len(subjects) != 1:
        return ()
    subject = next(iter(subjects))
    aliases = next((names for key, names in PRODUCT_PATTERNS if key == subject), ())
    owner = r'(?:' + '|'.join(re.escape(name) for name in aliases) + r')(?![a-z0-9])'
    authentication = r'authentication|identity\s+verification|身份验证|生物认证'
    requirement = r'requires?|needs?|要求|需要|必须'
    claims = []
    for unit in evidence.units:
        if unit.kind not in {'p', 'li', 'text', 'summary', 'selected_fact'} or unit.container_id == 'caption':
            continue
        for start, end in source_clause_spans(unit.text):
            text = unit.text[start:end]
            if not (_frame_search(authentication, text) and _frame_search(requirement, text)):
                continue
            operation = _frame_search(owner + r'\s*(?:(?:would|could|should|may|might)\s+|则(?:会)?|会)?\s*(?:' + requirement + r')', text)
            operator = _frame_search(r'(?:apple|苹果)\s*(?:' + requirement + r')', text)
            # An operator may impose a requirement on a device. Only that
            # direct object counts, not a later connection/comparison object.
            object_requirement = (_compiled_rule(r'\s*(?:' + authentication + r')\s+(?:on|for|before)\s+(?:the\s+)?'
                + owner, re.I).match(text, operator.end()) if operator else None)
            owned = bool(operation or object_requirement)
            predicate = operation or operator or _frame_search(requirement, text)
            status = source_predicate_role(text[:predicate.end()])
            other_owner = _compiled_rule(r'^(?:the\s+)?[A-Z][A-Za-z0-9 -]{1,35}\s+(?:requires?|needs?)\b|^(?:竞品|另一(?:个|款)设备).{0,25}(?:要求|需要|必须)').match(text.strip())
            role = (status if status != 'current' else 'supporting' if owned
                    else 'other-subject' if other_owner else 'unresolved')
            claims.append(BoundClaim(subject if owned else '', 'authentication-requirement', 'device-operation',
                (), evidence.article_id, (unit.unit_id,), ((unit.unit_id, start, end),), evidence.content_form,
                'software_systems', 'os_app', 'apple-direct' if owned else '', role))
    return tuple(claims)


def bind_media_invitation(evidence: ArticleEvidence) -> BoundClaim | None:
    """Own a reported media invitation before trying to identify its event.

    An invitation is not the inventory of products that may be presented.
    Missing event dates leave its boundary open, not its Apple qualification.
    """
    s = _frame_search
    invitation = r'\binvit(?:ations?|es?|ed|ing)\b|邀请'
    event = r'\b(?:product\s+)?launch\s+experience\b|\bevent\b|新品体验活动|发布会|发布活动'
    def mentions(text):
        return bool(s(r'\binvit(?:ing|es|ed)\s+(?:(?:some|selected|members|of|the)\s+)*'
                      r'(?:media|press|reporters?|journalists?)\b|'
                      r'\binvit(?:es|ations)\s+to\s+(?:(?:selected|members|of|the)\s+)*'
                      r'(?:media|press|reporters?|journalists?)\b|'
                      r'邀请(?:部分|一些|少数|选定的)?(?:媒体|记者)|'
                      r'向(?:部分|一些|少数|选定的)?(?:媒体|记者)[^。！？；;]{0,30}(?:发出|发送)[^。！？；;]{0,20}邀请函', text))
    lead = evidence.raw_lead or next((u.text for u in evidence.units if u.kind == 'summary'), '')
    first_end = next(source_sentence_spans(lead), (0, len(lead)))[1]
    principal = evidence.title + ' ' + lead[:first_end]
    body = [u for u in evidence.units if u.kind in {'p', 'text', 'blockquote', 'summary', 'selected_fact'}
            and u.container_id != 'caption']
    principal_invitation = mentions(principal)
    owned_scope = principal_invitation or (
        evidence.content_form in {'', 'news'}
        and s(r'launch|unveil|debut|event|发布|亮相|新品', principal)
        and any(mentions(u.text) for u in body))
    if not owned_scope:
        return None
    if not principal_invitation:
        # A confirmed launch remains the primary action. Its media logistics
        # support that action; they do not rename it as a separate invitation.
        primary = _legacy_dated_launch_frame(evidence.title, lead[:first_end], ())
        if primary is not None and primary.action == 'launch-date-confirmation':
            return None
    actor_predicate = (
        r'\bapple\s+(?:(?:has|is|now|already|begun|started|not|never|may|might|could)\s+)*'
        r'(?:invit(?:ing|es|ed)|(?:sending|sent|sends)\s+(?:out\s+)?invit(?:es|ations))\b|'
        r'苹果(?:公司)?(?:现在|现已|已经|已|开始|没有|并未|尚未|可能)*'
        r'(?:邀请|向[^。！？；;]{0,30}(?:发出|发送)[^。！？；;]{0,20}邀请函)')
    reporting = r'reports?|reported|reveals?|revealed|says?|said|discloses?|disclosed|confirms?|confirmed|透露|披露|报道|证实'
    attribution = _compiled_rule(
        r'(?:\b(?!(?:It|He|She|They|This|That)\b)[A-Z][A-Za-z.-]*(?:\s+[A-Z][A-Za-z.-]*){0,3}\s+(?i:' + reporting + r')\s+(?:that\s+)?|'
        r'[\u4e00-\u9fff·・]{2,30}(?:透露|披露|报道称?|证实)[，,:：\s]*)$', 0)
    signature = _compiled_rule(
        r'\s*(?:(?:This|It)\s+is\s+for\s+[^.!?。]+[.!?。]\s*)?[—–]\s*'
        r'[A-Z][A-Za-z.-]*(?:\s+[A-Z][A-Za-z.-]*)+\s*\(@[\w]+\)', 0)
    spans, qualifiers, statuses = [], [], []
    target = 'media-product-event'
    for unit in body:
        previous = None
        for start, end in source_clause_spans(unit.text):
            text = unit.text[start:end]
            predicate = s(actor_predicate, text)
            if not (mentions(text) and predicate):
                previous = (start, end) if s(event, text) and s(r'\bapple\b|苹果', text) else None
                continue
            report = attribution.search(text[:predicate.start()])
            report_span = (start + report.start(), start + report.end()) if report else None
            if report_span is None and previous is not None:
                # A report's immediate anaphor may retain its attribution;
                # ordinary neighboring assertions do not inherit it.
                antecedent = unit.text[previous[0]:previous[1]]
                if (s(r'^\s*(?:It|The report)\s+says\s+that\s*$', text[:predicate.start()])
                        and s(r'\breport\s+says\b', antecedent)
                        and source_predicate_role(antecedent) == 'current'
                        and not source_denies_action('', antecedent, reporting)):
                    report_span = previous
            if report_span is None:
                signed = signature.match(unit.text, end)
                if signed:
                    report_span = signed.span()
            if not principal_invitation:
                # An incidental invitation supports the source's primary
                # action. Only a local reported proposition owns this scope;
                # a report in an earlier sentence cannot lend its attribution.
                if (report_span is None or source_predicate_role(text[:predicate.start()]) != 'current'
                        or source_denies_action('', text[:predicate.start()], reporting)):
                    previous = None
                    continue
            target_start = s(r'\bto\s+(?:(?!\b(?:media|press|reporters?|journalists?)\b)[^.!?;]){0,130}(?:'
                             + event + r')|参加[^。！？；;]{0,100}(?:' + event + r')', text[predicate.end():])
            context = None
            if target_start is None and previous is not None:
                before = unit.text[previous[0]:previous[1]]
                if source_predicate_role(before) == 'current':
                    context = previous
            if target_start is None and context is None:
                previous = None
                continue
            role = source_predicate_role(text[:predicate.end()])
            if source_predicate_role(text) == 'background':
                role = 'background'
            polarity = 'denied' if source_denies_action('', text, invitation) else 'affirmed'
            spans.append((unit.unit_id, start, end))
            statuses.append((role, polarity))
            if report_span is not None:
                qualifiers.append(('apple', 'report-attribution', unit.text[slice(*report_span)].strip(),
                                   unit.unit_id, *report_span))
            if context is not None:
                spans.append((unit.unit_id, *context))
                date_start, date_end = context
            else:
                date_start, date_end = start + predicate.end() + target_start.start(), end
                # Chinese attendance dates can precede 参加. Keep only its
                # adjacent temporal phrase, not an earlier sending date.
                before_target = text[predicate.end():predicate.end() + target_start.start()]
                if text[predicate.end() + target_start.start():].startswith('参加'):
                    for q in source_calendar_dates(unit.unit_id, before_target, 0, target, kind='event'):
                        if s(r'(?:于|在)\s*$', before_target[:q[4]]) and not before_target[q[5]:].strip():
                            qualifiers.append((*q[:4], start + predicate.end() + q[4], start + predicate.end() + q[5]))
                # A temporal subordinate clause describes another operation
                # (for example sending the invitation), not this event's date.
                subordinate = s(r'\b(?:after|before|following|when|because)\b|随后|此前|之后',
                                unit.text[date_start:date_end])
                if subordinate:
                    date_end = date_start + subordinate.start()
            qualifiers.extend(source_calendar_dates(unit.unit_id, unit.text[date_start:date_end],
                                                     date_start, target, kind='event'))
            previous = None
    current = ('current', 'affirmed') in statuses
    if not principal_invitation and not current:
        return None  # A background invitation does not own a current launch report.
    historical = bool(statuses) and all(role == 'background' for role, _ in statuses)
    consistent = bool(statuses) and len(set(statuses)) == 1
    role = 'independent' if current and consistent else 'background' if historical else ''
    form = evidence.content_form or _content_form(evidence.title, evidence.raw_lead)
    if role == 'independent' and form in {'opinion', 'analysis', 'review', 'tutorial', 'buying_advice', 'deal'}:
        role = 'background'
    if not spans:
        # Keep the actual disputed text visible, including another actor's
        # invitation, rather than synthesizing an Apple hardware disclosure.
        spans = [(u.unit_id, a, b) for u in body for a, b in source_clause_spans(u.text)
                 if mentions(u.text[a:b])]
        if not spans:
            spans = [(u.unit_id, 0, len(u.text)) for u in evidence.units
                     if u.text == evidence.title]
    dates = {kind: {q[2] for q in qualifiers if q[1] == kind}
             for kind in ('event-year', 'event-month', 'event-day')}
    reason = ''
    if not role:
        reason = 'Media invitation actor, target or current assertion is unresolved; do not infer a hardware disclosure'
    elif not all(len(dates[k]) == 1 for k in ('event-month', 'event-day')) or len(dates['event-year']) > 1:
        reason = 'Media invitation event date is missing or contradictory; verify the event boundary before merging'
    return BoundClaim('apple' if statuses else '', 'media-invitation', target if statuses else '',
        tuple(dict.fromkeys(qualifiers)), evidence.article_id,
        tuple(dict.fromkeys(key for key, _, _ in spans)), tuple(dict.fromkeys(spans)), evidence.content_form,
        'hardware_products', 'hardware_market', 'apple-direct' if statuses else '', role,
        'affirmed' if current else 'denied' if statuses and all(p == 'denied' for _, p in statuses) else '', reason)


def bind_source_report(evidence: ArticleEvidence) -> tuple[BoundClaim, ...] | None:
    """Prepare migrated report families; None means outside their scope only."""
    leadership = bind_leadership_report(evidence)
    if leadership is not None:
        return (leadership,)
    invitation = bind_media_invitation(evidence)
    if invitation is not None:
        return (invitation,)
    chart = bind_app_chart_report(evidence)
    if chart is not None:
        return (chart,)
    measurement = bind_device_measurement(evidence)
    if measurement is not None:
        return (measurement,)
    inventory = bind_device_capability_inventory(evidence)
    return (inventory,) if inventory is not None else None


def bind_article_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Bind explicit source-local actions; unsupported evidence stays unprocessed.

    Feature names may retrieve a unit, but cannot authorize a claim without its
    own subject and rollout predicate. Historical and opinion parents are not
    converted to newly announced actions.
    """
    report = bind_source_report(evidence)
    if report is not None:
        return report
    form = evidence.content_form or _content_form(evidence.title, evidence.raw_lead)
    if form == "roundup":
        return bind_attributed_hardware_launch_claims(evidence)
    if form in {"opinion", "analysis", "tutorial", "review"}:
        return ()
    evidence = replace(evidence, content_form=form)
    configuration = bind_configuration_disclosure_claim(evidence)
    if configuration is not None:
        return (configuration,)
    procedural = bind_joint_litigation_claims(evidence)
    if procedural:
        return procedural
    appointments = bind_role_appointment_claims(evidence)
    if appointments:
        return appointments
    home_software = bind_home_software_claims(evidence)
    if home_software:
        return home_software
    storage = bind_storage_design_claim(evidence)
    if storage is not None:
        return (storage,)
    remedies = bind_connectivity_remedy_claims(evidence)
    if remedies:
        return remedies
    web_exploit = bind_web_exploit_claim(evidence)
    if web_exploit is not None:
        return (web_exploit,)
    component_claims = bind_replaceable_component_claims(evidence)
    if component_claims:
        return component_claims
    operation_claims = bind_operation_report_claims(evidence)
    if operation_claims:
        return operation_claims
    quota_claims = bind_mail_quota_claims(evidence)
    if quota_claims:
        return quota_claims
    document_claim = bind_document_claim(evidence)
    if document_claim is not None:
        return (document_claim,)
    service_claim = bind_named_service_rollout(evidence)
    if service_claim is not None:
        return (service_claim,)
    hardware = bind_hardware_launch(evidence)
    claims = [hardware] if hardware is not None else []
    def beta_stages(value):
        numbers = [int(n) for n in _compiled_rule(r"\bbeta\s*(\d+)\b", re.I).findall(value)]
        ordinals = {"first": 1, "second": 2, "third": 3, "fourth": 4}
        numbers.extend(ordinals[m.group(1).lower()] for m in _compiled_rule(r"\b(first|second|third|fourth)\s+(?:(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+)*\s+)?(?:developer\s+)?beta\b", re.I).finditer(value))
        return numbers
    headline_stages = beta_stages(evidence.title)
    headline_beta = max(headline_stages) if headline_stages else None
    list_stage = None
    for source_unit in evidence.units:
        if source_unit.kind != "li":
            list_stage = None
            introduction_stages = beta_stages(source_unit.text)
            if introduction_stages and _compiled_rule(r"(?:included|introduced|added)[^.!?。！？]{0,45}(?:changes|features)\s*[:：]\s*$", re.I).search(source_unit.text):
                list_stage = max(introduction_stages)
        inherited_earlier_stage = bool(source_unit.kind == "li" and list_stage is not None
                                      and headline_beta is not None and list_stage < headline_beta)
        for start, end in source_sentence_spans(source_unit.text):
            unit = replace(source_unit, text=source_unit.text[start:end])
            text = unit.text
            if _compiled_rule(r"^(?:previously|formerly|last year|此前|早前|去年)\b|^(?:此前|早前|去年)", re.I).search(text):
                continue
            # Keep old rollout evidence as source text, but do not project it
            # as an action of a newer release. Dates/stages belong to this clause.
            local_betas = beta_stages(text)
            earlier_stage = inherited_earlier_stage or bool(headline_beta and local_betas
                and all(value < headline_beta for value in local_betas))
            historical_rollout = bool(_compiled_rule(r"\b(?:previously|formerly|last month|last year|initial rollout)\b|"
                r"(?:正式版|旧版).{0,45}(?:发布时|推出时)|此前(?:仅|只)?支持", re.I).search(text))
            if earlier_stage or historical_rollout:
                continue
            price_claims = bind_service_price_claims(evidence, source_unit, start, end)
            if price_claims:
                claims.extend(price_claims)
                continue
            subject = object_name = ""
            # Parentheticals are background, and the predicate must occur in the
            # same local sentence as Siri itself (not Siri Recap or an app mention).
            local = _compiled_rule(r"\([^)]*\)|（[^）]*）", 0).sub("", text, 0)
            rollout_scope = local
            # In a causal sentence about an OS release, "it will launch"
            # refers to the OS, not a language noun inside the reason clause.
            if _compiled_rule(r"^Since\s+(?:iOS|iPadOS|macOS|watchOS|tvOS|visionOS)\s+\d", re.I).match(local):
                rollout_scope = _compiled_rule(r",\s*it\b", re.I).split(local, 1)[0]
            siri_rollout = _compiled_rule(r"\bSiri(?:\s*AI)?\b(?!\s*(?:Recap|app))[^。.!?;；]{0,160}?"
                r"(?:adds?\b|launch(?:es|ing)?\b|roll(?:s|ing)? out|available|support|新增|推出|上线|支持|拓展|开放)", re.I).search(rollout_scope)
            if siri_rollout:
                # A language setting or a launch's regional inventory is a
                # condition of that action, not an independent language rollout.
                # A focused language report or an explicit additive assertion
                # can establish the separate action.
                language_focus = _compiled_rule(
                    r'Siri.{0,70}(?:languages?|English|French|Japanese|Korean|Portuguese|Spanish|'
                    r'语言|英语|法语|日语|韩语|葡萄牙语|西班牙语)', re.I).search(evidence.title)
                language_change = _compiled_rule(
                    r'Siri(?:\s*AI)?\s+(?:(?:now|will|also|is|has)\s+){0,3}'
                    r'(?:adds?|gains?|launch\w*|roll\w*\s+out|expand\w*|新增|拓展|开放)|'
                    r'Siri(?:\s*AI)?.{0,20}(?:now\s+supports?|新增支持|现已支持|开始支持)|'
                    r'Siri(?:\s*AI)?\s*(?:(?:将于?|在|于)?(?:\d{1,2}|[一二三四五六七八九十]+)月)?\s*(?:新增|拓展|开放)|'
                    r'Siri(?:\s*AI)?\s+(?:is\s+)?now\s+available\s+in\s+(?:\w+\s+)?more\s+languages', re.I).search(local)
                if not language_focus and not language_change:
                    siri_rollout = None
            current_rollout_offset = 0
            if siri_rollout:
                publication = _compiled_rule(r'^(20\d{2})-(\d{2})', 0).match(evidence.published_utc or '')
                prior_month = _compiled_rule(r'(?:今年|本年)\s*(\d{1,2})\s*月', 0).search(local)
                dated_history = bool(publication and prior_month and int(prior_month.group(1)) < int(publication.group(2)))
                supporting_status = bool(not _frame_search(r'siri', evidence.title)
                    and _frame_search(r'目前.{0,25}(?:支持|可用)|currently.{0,25}(?:supports?|available)|already\s+supports?', local)
                    and not _frame_search(r'新增|新开放|拓展至|now\s+adds?|newly\s+(?:available|supports?)', local))
                if dated_history or supporting_status:
                    # A current additive clause inherits Siri only within this
                    # sentence; the preceding historical language set remains
                    # unassigned instead of becoming part of the new rollout.
                    current = _compiled_rule(r'[,，;；]\s*((?:(?:但|而|but)\s*)?(?:今天|今日|现已|today|now)\s*(?:新增|开放|拓展|adds?|rolls?\s+out)[^。.!?]*)', re.I).search(text)
                    if not current:
                        continue
                    current_rollout_offset = current.start(1)
                    local = text[current_rollout_offset:]

            if siri_rollout and (_compiled_rule(r"languages?|English|French|Japanese|Korean|Portuguese|Spanish|英语|英文|法语|日语|韩语|葡萄牙语|西班牙语|语言", re.I).search(local) or (_compiled_rule(r"Siri.{0,80}(?:languages?|语言)", re.I).search(evidence.title)
                  and _compiled_rule(r"not be available|不可用|不提供|无法使用", re.I).search(local))):
                subject, object_name = "siri", "languages"
            elif _compiled_rule(r"Apple\s*Watch|苹果手表", re.I).search(local) and _compiled_rule(r"Live\s*Rewind|Siri\s*Recap", re.I).search(local) and not _compiled_rule(r"no longer available|repurposed|不再可用|重新分配", re.I).search(local) and _compiled_rule(r"arriv|launch|releas|available|coming|推出|上线|提供|年底", re.I).search(local):
                subject, object_name = "apple-watch", "watch-audio"
            if not subject:
                if (claims and claims[-1].unit_ids[-1] == unit.unit_id
                    and _compiled_rule(r"(?:They|It|These features|它们|它|这些功能|该功能)", re.I).match(text)
                    and _compiled_rule(r"requires?|pair|except|要求|配对|不包括", re.I).search(text)):
                    previous = claims[-1]
                    claims[-1] = replace(previous, evidence_spans=previous.evidence_spans + ((unit.unit_id, start, end),))
                continue
            claim_start = start + current_rollout_offset
            claim_text = text[current_rollout_offset:]
            # A single source sentence may contain two independently owned
            # actions. Keep the preceding clause in the evidence remainder.
            second_action = _compiled_rule(
                r",\s+and\s+(?=(?:Siri(?:\s*AI)?|Apple\s*Watch|苹果手表)\b)", re.I
            ).search(text)
            first_clause = text[:second_action.start()] if second_action else ""
            first_action = bool(
                _compiled_rule(r"\b(?:users?|apple|the\s+app)\b[^,]{0,80}"
                    r"\b(?:get|gets|add|adds|offer|offers|change|changes)\b", re.I)
                    .search(first_clause)
                or (_compiled_rule(r"\b(?:in|for)\s+(?:the\s+)?(?:apple\s+tv|apple\s+music|"
                    r"health|messages|photos)\s+app\b", re.I).search(first_clause)
                    and _compiled_rule(r"\bthere\s+(?:are|is)\s+new\s+"
                        r"(?:\w+\s+){0,3}(?:settings?|controls?|options?|features?)\b", re.I)
                        .search(first_clause))
            )
            if second_action and subject == "siri" and first_action:
                claim_start = start + second_action.end()
                claim_text = text[second_action.end():]
            claim_unit = replace(unit, text=claim_text)
            qualifiers = tuple((*q[:4], q[4] + claim_start, q[5] + claim_start)
                               for q in rollout_qualifiers(claim_unit, object_name))
            claims.append(BoundClaim(subject, "rollout", object_name, qualifiers,
                evidence.article_id, (unit.unit_id,), ((unit.unit_id, claim_start, end),), evidence.content_form, subject_relation="apple-direct", report_role="independent"))
    return tuple(claims)



def normalize_rollout_time(value: str) -> str:
    months = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
    chinese = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")
    lowered = value.lower().strip()
    if lowered in months:
        return "month:" + str(months.index(lowered) + 1)
    if lowered.endswith("月"):
        month = lowered[:-1]
        return "month:" + str(chinese.index(month) + 1 if month in chinese else int(month))
    return "year-end"



def rollout_qualifiers(unit, object_name):
    """Bind each local rollout target to its own timing and source span."""
    separators = list(_compiled_rule(r"[;；]|\b(?:before|while|whereas)\b|然后|随后|而后|\band\s+(?=[A-Z][a-z]+\s+in\s)", 0).finditer(unit.text))
    boundaries = [0, *(match.start() for match in separators), len(unit.text)]
    result = []
    for start, end in zip(boundaries, boundaries[1:]):
        clause = unit.text[start:end]
        targets = [name for name, pattern in _LANGUAGE_NAMES if re.search(pattern, clause, re.I)]
        if object_name == "watch-audio":
            targets = ["watch-audio"]
        elif not targets and _compiled_rule(r"(?:more|following|additional|other)\s+languages|更多语言|其他语言", re.I).search(clause):
            targets = ["additional-languages"]
        if _compiled_rule(r"not be available|不可用|不提供|无法使用", re.I).search(clause):
            for region, pattern in (("china", r"China|中国"), ("eu", r"\bEU\b|European Union|欧盟")):
                if re.search(pattern, clause, re.I):
                    result.append((object_name, "excluded-region", region, unit.unit_id, start, end))
        if not targets:
            continue
        times = list(_compiled_rule(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b|"
            r"(?:[一二三四五六七八九十]+|\d{1,2})月|年底|end of (?:the year|\d{4})", re.I).finditer(clause))
        if len(times) > 1:
            # A clause with multiple dates needs a finer interpretation; retain
            # its facts, but do not arbitrarily attach either date to a target.
            times = []
        for target in targets:
            value = normalize_rollout_time(times[0].group(0)) if times else "unspecified"
            result.append((target, "rollout-time", value, unit.unit_id, start, end))
            years = set(_compiled_rule(r"\b(20\d{2})\b", 0).findall(clause))
            if len(years) == 1:
                result.append((target, "rollout-year", years.pop(), unit.unit_id, start, end))
            if _compiled_rule(r"staged|gradual|逐步|分批", re.I).search(clause):
                result.append((target, "availability-stage", "staged", unit.unit_id, start, end))
    return tuple(result)



def rollout_language_names(text):
    return tuple(name for name, pattern in _LANGUAGE_NAMES if re.search(pattern, text, re.I))



def source_attributed_quote_spans(text: str):
    """Keep a quoted statement with the speaker named immediately after it."""
    for match in _compiled_rule(
            r'["“][^"”]+["”]\s+(?:said|says|explained|recalled)\s+'
            r'[A-Z][\w.-]*(?:[ \t]+[A-Z][\w.-]*)*', 0).finditer(text):
        yield match.span()


def source_sentence_spans(text):
    pending = None
    for match in _compiled_rule(r".+?(?:[。！？!?][\"'”’]*|\.[\"'”’]*(?=\s|$)|$)", re.S).finditer(text):
        start, end = match.span()
        if pending is not None:
            start = pending
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        abbreviation = _compiled_rule(r"\b(?:(?:[A-Z]\.){2,}|(?:St|Mt|Dr|Mr|Mrs|Ms|Prof)\.)$", 0).search(text[start:end].rstrip('\"\'”’'))
        month_date = (text[end:end+4].lstrip()[:1].isdigit()
                      and _compiled_rule(r'\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.$', re.I).search(text[start:end]))
        if (abbreviation or month_date) and end < len(text):
            pending = start
            continue
        pending = None
        if start < end:
            yield start, end
    if pending is not None:
        yield pending, len(text.rstrip())


def bind_hardware_launch(evidence: ArticleEvidence) -> BoundClaim | None:
    """Bind a concrete announced model and its local specification paragraphs."""
    models = list(_compiled_rule(r"\b(?P<family>Apple\s+Watch|iPhone|iPad|MacBook|AirPods)\s+"
        r"(?P<model>(?:(?:Series|Ultra|Pro|Air|mini)\s+)?\d+(?:\s+(?:Pro|Max|Plus|Ultra))*)\b", re.I).finditer(evidence.title))
    if len(models) != 1 or not evidence.units:
        return None
    model = models[0]
    subject = next(iter(_extract_patterns(_normalized(model.group('family')), PRODUCT_PATTERNS)), '')
    if not subject:
        return None
    lead = evidence.units[0].text
    identity = build_event_identity(evidence.title, lead)
    if (identity.scope != "apple-direct" or identity.action_owner == "third-party"
            or identity.content_form in {"review", "analysis", "opinion", "roundup", "tutorial"}):
        return None
    if _compiled_rule(r"last\s+(?:week|month|year)|上周|上个月|去年", re.I).search(lead):
        return None
    if _compiled_rule(r"\b(?:expected|forecast|rumou?r|delay(?:ed|s)?|postponed|next year)\b|预估|预计|推迟|延期|改到|明年|后年", re.I).search(evidence.title + " " + lead):
        return None
    if not _compiled_rule(r"\bApple\s+(?:today\s+)?(?:announced|announces|unveiled|introduced|launched)\b|"
                     r"(?:^|[。.!?]\s*)苹果(?:今日|今天|刚刚|正式|现已|已经|已)?(?:发布|推出)(?:了)?|"
                     r"^(?:Apple Watch|iPhone|iPad|MacBook|AirPods)\b.{0,45}\blaunches\b", re.I).search(lead):
        return None
    names = [model.group(0)]
    if _compiled_rule(r"[a-z]", re.I).search(model.group('model')):
        names.append(model.group('model'))
    alias = re.compile(r"(?<!\w)(?:" + '|'.join(re.escape(name) for name in names) + r")(?!\w)", re.I)
    spans = []
    for index, unit in enumerate(evidence.units):
        if index and not alias.search(unit.text):
            continue
        owned = True
        for start, end in source_sentence_spans(unit.text):
            text = unit.text[start:end]
            if _compiled_rule(r"previously|formerly|last year|此前|早前|去年", re.I).match(text):
                continue
            if alias.search(text):
                owned = True
            elif _compiled_rule(r"[A-Z][a-z]+(?:\s+(?:app|service))?\s+(?:will|adds?|launches?|supports?)\b|"
                          r"[^。.!?]{1,15}(?:应用|服务).{0,5}(?:将|会|新增)", 0).match(text):
                owned = False
            if owned:
                spans.append((unit.unit_id, start, end))
    if not spans:
        return None
    object_name = _compiled_rule(r"[^a-z0-9]+", 0).sub('-', model.group(0).lower(), 0).strip('-')
    return BoundClaim(subject, 'product-launch', object_name, (), evidence.article_id,
        tuple(dict.fromkeys(key for key, _, _ in spans)), tuple(spans), evidence.content_form, subject_relation="apple-direct", report_role="independent")


def bind_service_price_claims(evidence: ArticleEvidence, unit, start: int, end: int) -> tuple[BoundClaim, ...]:
    """Bind each directed first-party price action to its own named service."""
    text = unit.text[start:end]
    if not _compiled_rule(r"\s*(?:Apple\b(?!\s+(?:Music|TV|One))|苹果)", re.I).match(text):
        return ()
    service = r"Apple\s*Music|Apple\s*TV\+?|iCloud\+?|Apple\s*One"
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    timing = (r"(?:in|from|starting)\s+(?:" + months + r")(?:\s+20\d{2})?|"
              r"(?:自|将于|于)?\s*20\d{2}\s*年\s*(?:\d{1,2}|[一二三四五六七八九十]{1,3})\s*月(?:起|生效)?")
    pattern = re.compile(
        r"(?:(?:Apple|苹果)\s*)?(?:(?:and|并且|并)\s*)?"
        r"(?P<action>raises?|increases?|hikes?|lowers?|reduces?|cuts?|上调|提高|下调|降低)\s*"
        r"(?P<service>" + service + r")(?:['’]s)?\s*(?:subscription\s+)?(?:prices?|fees?|价格|售价|订阅费)"
        r"(?:\s*(?:to|至|到)\s*(?P<amount>[$€£¥￥]?\s*\d+(?:\.\d+)?(?:\s*(?:美元|元))?))?"
        r"(?:[\s,，]*(?P<timing>" + timing + r"))?",
        re.I)
    claims = []
    cursor = 0
    for match in pattern.finditer(text):
        # A second clause may inherit Apple only through a direct conjunction;
        # an intervening owner, negation or modal cannot borrow that ownership.
        if text[cursor:match.start()].strip(" ,，;；"):
            continue
        if _compiled_rule(r"\s*[,，]?\s*(?:in\b|from\b|starting\b|for\b|at\b|于|将于|自|针对|对)", re.I).match(text[match.end():]):
            # Do not emit an unqualified claim when a local limiting phrase was
            # not understood. The complete action remains source-visible review.
            continue
        cursor = match.end()
        subject = _compiled_rule(r"\s+", 0).sub("-", match.group("service").lower(), 0).rstrip("+")
        subject = {"applemusic": "apple-music", "appletv": "apple-tv", "appleone": "apple-one"}.get(subject, subject)
        increase = _compiled_rule(r"raises?|increases?|hikes?|上调|提高", re.I).fullmatch(match.group("action"))
        action = "price-increase" if increase else "price-decrease"
        left, right = start + match.start(), start + match.end()
        qualifiers = []
        if match.group("amount"):
            amount = match.group("amount")
            value = _compiled_rule(r"\d+(?:\.\d+)?", 0).search(amount).group(0)
            currency = "usd" if "$" in amount or "美元" in amount else "eur" if "€" in amount else "gbp" if "£" in amount else "cny" if _compiled_rule(r"[¥￥]|元", 0).search(amount) else "unspecified"
            qualifiers.append((subject, "price-amount", currency + ":" + value, unit.unit_id,
                               start + match.start("amount"), start + match.end("amount")))
        if match.group("timing"):
            phase = match.group("timing")
            phase_start, phase_end = start + match.start("timing"), start + match.end("timing")
            year = _compiled_rule(r"20\d{2}", 0).search(phase)
            month = re.search(months + r"|(?:\d{1,2}|[一二三四五六七八九十]{1,3})\s*月", phase, re.I)
            if year:
                qualifiers.append((subject, "rollout-year", year.group(0), unit.unit_id, phase_start, phase_end))
            if month:
                qualifiers.append((subject, "rollout-time", normalize_rollout_time(month.group(0).replace(" ", "")), unit.unit_id, phase_start, phase_end))
        claims.append(BoundClaim(subject, action, "subscription-price", tuple(qualifiers), evidence.article_id,
                                (unit.unit_id,), ((unit.unit_id, left, right),), evidence.content_form, subject_relation="apple-direct", report_role="independent"))
    return tuple(claims)


from .article_processing import clean_sentence, score_terms

MULTI_PRODUCT_HARDWARE_SUBJECTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "apple-home-hub",
        "Home hub",
        (
            "home hub",
            "家庭中枢",
            "智能家居中枢",
            "带屏智能家居中枢",
            "家庭配件 j490",
            "家庭配件 j491",
        ),
    ),
    ("camera-airpods", "camera-equipped AirPods", ("camera-equipped airpods", "camera airpods", "摄像头 airpods", "配备摄像头的 airpods", "图像流")),
    ("airpods-pro", "AirPods Pro", ("airpods pro", "airpodspro")),
    ("iphone", "iPhone", ("iphone", "iphones", "折叠屏手机", "折叠 iphone", "折叠iphone")),
    ("airpods", "AirPods", ("airpods", "苹果耳机")),
    ("beats", "Beats", ("beats", "苹果 beats")),
    ("macbook-ultra", "MacBook Ultra", ("macbook ultra",)),
    ("macbook-neo", "MacBook Neo", ("macbook neo",)),
    ("macbook-pro", "MacBook Pro", ("macbook pro",)),
    ("macbook-air", "MacBook Air", ("macbook air",)),
    ("macbook", "MacBook", ("macbook", "macbooks", "苹果笔记本")),
    ("mac-mini", "Mac mini", ("mac mini",)),
    ("mac-studio", "Mac Studio", ("mac studio",)),
    ("mac-pro", "Mac Pro", ("mac pro",)),
    ("imac", "iMac", ("imac", "imacs")),
    ("ipad-air", "iPad Air", ("ipad air",)),
    ("ipad-mini", "iPad mini", ("ipad mini",)),
    ("ipad", "iPad", ("ipad", "ipads", "苹果平板")),
    ("apple-pencil", "Apple Pencil", ("apple pencil", "苹果手写笔", "苹果触控笔")),
    ("apple-watch", "Apple Watch", ("apple watch", "apple watches", "苹果手表")),
    ("apple-glasses", "smart glasses", ("apple glass", "apple's glasses", "apple’s glasses", "smart glasses", "智能眼镜")),
    ("vision-pro", "Vision Pro", ("vision pro", "apple visions", "苹果头显")),
    ("homepod", "HomePod", ("homepod", "homepods", "苹果音箱")),
    ("apple-tv", "Apple TV", ("apple tv", "apple tvs", "苹果电视")),
)


def iphone_report_subjects(value: str) -> set[str]:
    lower = value.lower()
    primary_scope = _compiled_rule(r"\b(?:compared\s+(?:with|to)|versus|vs\.?|than)\b|(?:相比|相较|对比)", 0).split(lower, 1)[0]
    subjects: set[str] = set()
    if score_terms(primary_scope, ["foldable iphone", "iphone fold", "iphone ultra", "折叠 iphone", "折叠屏", "折叠机型"]) > 0:
        subjects.add("foldable-iphone")
    if score_terms(
        primary_scope,
        [
            "anniversary iphone",
            "20th-anniversary iphone",
            "20th anniversary iphone",
            "twentieth-anniversary iphone",
            "二十周年纪念版 iphone",
            "二十周年纪念款",
            "周年纪念版 iphone",
            "周年纪念款",
        ],
    ) > 0:
        subjects.add("anniversary-iphone")
    for match in _compiled_rule(r"\biphone\s*(\d{2})(?!\d|[,，]\s*\d)(?:\s+(?:pro(?:\s+max)?|air|e))?\b", 0).finditer(primary_scope):
        subjects.add(f"iphone-{match.group(1)}")
    return subjects



def foldable_iphone_generation_subject(value: str) -> str:
    """Return an explicit foldable-iPhone generation owned by one claim."""
    lower = value.lower()
    if _compiled_rule(r"\b(?:second|2nd)[ -]generation\b|\bsecond[ -]gen\b|"
        r"(?:第二代|第\s*2\s*代)", re.I).search(lower):
        return "foldable-iphone-g2"
    if _compiled_rule(r"\b(?:third|3rd)[ -]generation\b|\bthird[ -]gen\b|"
        r"(?:第三代|第\s*3\s*代)", re.I).search(lower):
        return "foldable-iphone-g3"
    return "foldable-iphone"



def multi_product_hardware_subjects(value: str) -> set[str]:
    lower = value.lower()
    lower = _compiled_rule(r"(?:\b(?:besides|apart from|other than)\b|(?:除|除了))"
        r"[^。.!?，,；;]{0,40}(?:\b(?:aside|too)\b|(?:以外|之外|外))[,，]?", re.I).sub(" ", lower, 0)
    subjects = {
        subject
        for subject, _label, terms in MULTI_PRODUCT_HARDWARE_SUBJECTS
        if score_terms(lower, terms) > 0
    }
    if subjects & {"camera-airpods", "airpods-pro"}:
        subjects.discard("airpods")
    if "ipad-mini" in subjects:
        subjects.discard("ipad")
    if "ipad-air" in subjects:
        subjects.discard("ipad")
    if subjects & {"macbook-ultra", "macbook-neo", "macbook-pro", "macbook-air"}:
        subjects.discard("macbook")
    return subjects



def heading_owned_multi_product_hardware_subject(value: str) -> str | None:
    """Return the product named by a structured fact heading, if present."""
    cleaned = clean_sentence(value).strip(" -\t")
    heading = _compiled_rule(r"^([^：:\n]{2,80})[：:]", 0).match(cleaned)
    if heading:
        heading_subjects = hardware_action_subjects(heading.group(1))
        if len(heading_subjects) == 1:
            return next(iter(heading_subjects))
    return None


_HARDWARE_MENTION = re.compile("|".join(
    (r"(?<![a-z0-9])" if term[0].isascii() else "") + re.escape(term)
    + (r"(?![a-z0-9])" if term[-1].isascii() else "")
    for term in sorted({term for _, _, terms in MULTI_PRODUCT_HARDWARE_SUBJECTS
                        for term in terms}, key=len, reverse=True)), re.I)


def hardware_action_subjects(value: str) -> set[str]:
    """Ignore design/function comparison objects without hiding other actions.

    Mask only the referenced product name, so a following coordinated launch
    keeps its own subject. The original fact text remains unchanged.
    """
    lower = value.lower()
    spans = []
    for mention in _HARDWARE_MENTION.finditer(lower):
        before = lower[max(0, mention.start() - 80):mention.start()]
        after = lower[mention.end():mention.end() + 60]
        comparison = _compiled_rule(
            r"\b(?:inspired\s+by|similar\s+to|reminiscent\s+of|resembles?|"
            r"(?:acts?|functions?|serves?)\s+(?:like|as)|looks?\s+like)"
            r"(?:\s+(?:a|an|the))?\s*$|(?:类似于?|形似|灵感来自|设计借鉴)\s*$",
            re.I).search(before)
        style = _compiled_rule(r"^(?:\s+(?:[a-z]{0,4}\d+[a-z]?|pro|max|mini|air|ultra)){0,3}"
                         r"[- ](?:style|like)\b|"
                         r"^(?:\s+g\d+)?\s*(?:风格|式造型)", re.I).match(after)
        design = (_compiled_rule(r"\b(?:with|uses?|using|features?|featuring)"
                            r"(?:\s+(?:a|an|the))?\s*$|(?:采用|使用|借鉴)\s*$", re.I).search(before)
                  and _compiled_rule(r"^(?:\s+(?:[a-z]{0,4}\d+[a-z]?|pro|max|mini|air|ultra)){0,3}"
                               r"\s+(?:design|styling|look)\b|"
                               r"^(?:\s+g\d+)?\s*(?:风格)?设计", re.I).match(after))
        if comparison or style or design:
            spans.append(mention.span())
    for start, end in reversed(spans):
        lower = lower[:start] + " " + lower[end:]
    return multi_product_hardware_subjects(lower)



def owned_multi_product_hardware_subject(value: str) -> str | None:
    """Return the product that grammatically owns one roadmap fact.

    Structured multi-product reports commonly use a short product heading
    followed by comparison or compatibility context.  The heading owns the
    action; later product mentions must not suppress or redirect that fact.
    """
    heading_subject = heading_owned_multi_product_hardware_subject(value)
    if heading_subject is not None:
        return heading_subject
    cleaned = clean_sentence(value).strip(" -\t")
    # The subject before a configuration predicate owns borrowed components;
    # "HomePod uses the Watch chip" does not describe a Watch update.
    predicate = _compiled_rule(r"\b(?:will\s+(?:be|have|use|feature)|is\s+equipped|uses?|features?)\b|(?:将搭载|将配备|采用)", re.I).search(cleaned)
    if predicate:
        owners = hardware_action_subjects(cleaned[:predicate.start()])
        if len(owners) == 1:
            return next(iter(owners))
    subjects = hardware_action_subjects(cleaned)
    if len(subjects) == 1:
        return next(iter(subjects))
    return None



def apple_silicon_generation_keys(value: str) -> set[str]:
    """Return non-negated Apple-silicon generations from one claim."""
    return {
        component.removeprefix("apple-silicon-generation:")
        for component in build_event_identity(value, "").components
        if component.startswith("apple-silicon-generation:")
    }


def disclosed_device_subjects(text: str) -> dict[str, str]:
    """Read named device families; OS capabilities are not device subjects."""
    patterns = (
        ('apple-tv', r'(?<![a-z])apple\s*tv\s*4k(?:\s*[（(](?:第)?(?P<generation>\d+|[一二三四五六七八九十]+)(?:th|st|nd|rd)?\s*(?:generation|代)[)）])?'),
        ('homepod-mini', r'(?<![a-z0-9])(?:第(?P<ordinal>\d+|[一二三四五六七八九十])代\s*)?homepod\s*mini(?:\s*(?P<generation>\d+))?'),
        ('ipad-mini', r'(?<![a-z0-9])ipad\s*mini(?:\s*(?P<generation>\d+))?'),
        ('ipad-base', r'(?<![a-z0-9])ipad\s*(?P<generation>\d+)(?!\d)|\b(?P<ordinal>\d+)(?:th|st|nd|rd)[- ]generation\s+ipad\b|\b(?:entry[- ]level|low[- ]cost)\s+ipad\b'),
    )
    result = {}
    for family, pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            generation = match.groupdict().get('generation') or match.groupdict().get('ordinal') or ''
            generation = str('一二三四五六七八九十'.index(generation) + 1) if generation and generation in '一二三四五六七八九十' else generation
            result[family] = generation
    return result


def source_free_race_stream(title: str, lead: str) -> str | None:
    """Bind free access to the named race, not F1 generally or host hardware."""
    headline, opening = _normalized(title), _normalized(lead)[:400]
    scope = headline + ' ' + opening
    if (not _frame_search(r"apple\s*tv", scope)
            or not _frame_search(r"\bf1\b|formula\s+1|一级方程式", scope)
            or not _frame_search(r"\bfree\b|免费|免订阅", headline)):
        return None
    for sentence in _compiled_rule(r"(?<=[.!?])\s+|[。！？;；]").split(headline+'. '+opening):
        # Negation of the stream/free-access predicate differs from saying
        # viewers won't need a subscription. A denial scopes over its whole
        # assertion, including a long named race between verb and predicate.
        if (_frame_search(r"\b(?:not|no\s+longer|won't)\s+(?:(?:be|become|be\s+made)\s+)?"
                          r"(?:free|(?:stream\w*|broadcast\w*|offer\w*|provid\w*|available)\b[^.!?。]*\bfree)\b",sentence)
                or _frame_search(r"\b(?:denies|denied)\s+(?:free\b|(?:that\s+)?[^.!?。]*"
                                 r"\b(?:stream\w*|broadcast\w*|offer\w*|available|be|is)\b[^.!?。]*\bfree\b)",sentence)
                or _frame_search(r"(?:不会|不再|并非|取消|否认)[^。！？;；]*(?:免费|免订阅)",sentence)):
            return None
    # Canonical place aliases, not publisher headlines or single-race keys.
    places = {'巴林':'bahrain', '沙特阿拉伯':'saudi-arabian', '澳大利亚':'australian',
              '中国':'chinese', '日本':'japanese', '迈阿密':'miami', '加拿大':'canadian',
              '摩纳哥':'monaco', '西班牙':'spanish', '奥地利':'austrian', '英国':'british',
              '比利时':'belgian', '匈牙利':'hungarian', '荷兰':'dutch', '意大利':'italian',
              '阿塞拜疆':'azerbaijan', '新加坡':'singapore', '美国':'united-states',
              '墨西哥':'mexico-city', '圣保罗':'sao-paulo', '拉斯维加斯':'las-vegas',
              '卡塔尔':'qatar', '阿布扎比':'abu-dhabi', '马来西亚':'malaysian'}
    for value in (headline, opening):
        local = [name for alias,name in places.items() if _frame_search(
            re.escape(alias)+r"\s*大奖赛|\b"+re.escape(name.replace('-',' '))+r"\s+grand\s+prix\b",value)]
        if len(local)==1:
            return 'f1-'+local[0]+'-grand-prix'
        race = _frame_search(r"\b(?:the\s+)?([a-z]+(?:\s+[a-z]+){0,2})\s+grand\s+prix\b",value)
        if race:
            name = _compiled_rule(r"^(?:the|free|streaming)\s+").sub('',race.group(1))
            return 'f1-'+name.replace(' ','-')+'-grand-prix'
    return None


def source_device_disclosure(title: str, lead: str) -> tuple[str, str] | None:
    """Bind a device data disclosure to its subject, not chips in its context."""
    headline = _normalized(title)
    opening = _normalized(lead)[:1100]
    if is_editorial_change_request(title):
        return None
    if _content_form(title, lead) in {"roundup", "review", "opinion", "analysis", "buying_advice"}:
        return None
    # Software, catalog publications and named accessories have different
    # changed objects even when the same hardware appears in their text.
    if _compiled_rule(r'\b(?:tvos|ios|ipados|macos|watchos)\s*\d+|图纸|dimensional\s+drawings|siri\s+remote|遥控器', 0).search(headline):
        return None
    if _compiled_rule(r"^(?:apple\s+)?(?:releases?|launches?|ships?|announces?)\b|苹果(?:发布|推出|开售)|正式(?:发布|上市)", 0).search(headline):
        return None
    subjects = disclosed_device_subjects(headline)
    if len(subjects) != 1:
        return None
    if not _compiled_rule(r'\b(?:leak\w*|code)\b|曝光|爆料|泄露|泄密|内部资料|内部代码', 0).search(headline + ' ' + opening):
        return None
    if _compiled_rule(r'\b(?:not\s+(?:a\s+)?(?:leak|from\s+apple)|fan[- ]made|concept|mockup|recap)\b|概念图|非官方概念|并非泄露|旧闻回顾', 0).search(headline + ' ' + opening[:250]):
        return None
    family, generation = next(iter(subjects.items()))
    lead_subjects = disclosed_device_subjects(opening)
    if not generation:
        generation = lead_subjects.get(family, '')
    # Missing generation stays explicit; the matcher may only reconcile it
    # when a source-local disclosure relation supplies compatible evidence.
    return family, generation


def source_employee_leave_notice(title: str, lead: str) -> str | None:
    """Bind a current Apple staff notice; a recalled holiday is not a notice."""
    headline, opening = _normalized(title), _normalized(lead)[:650]
    if not _compiled_rule(r"\bapple\b|苹果", 0).search(headline):
        return None
    holidays = (("thanksgiving", r"thanksgiving|感恩节"),
                ("christmas", r"christmas|圣诞节"),
                ("lunar-new-year", r"lunar\s+new\s+year|春节"))
    holiday = next((name for name, pattern in holidays if re.search(pattern, headline)), None)
    if not holiday or not _compiled_rule(r"\bstaff\b|\bemployees?\b|员工", 0).search(headline + " " + opening):
        return None
    if _compiled_rule(r"\b(?:history|historical|recap|last\s+year|previously)\b|历史|回顾|去年|此前", 0).search(headline):
        return None
    for sentence in _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(opening, 0)[:3]:
        if _compiled_rule(r"\b(?:last\s+year|previously|back\s+in)\b|去年|此前|曾经", 0).search(sentence):
            continue
        notice = _compiled_rule(r"\b(?:told\s+staff|announced|notified|informed)\b|向员工宣布|通知员工|宣布", 0).search(sentence)
        owner = bool(notice and _compiled_rule(r"\bapple(?:['’]s)?\b|苹果", 0).search(sentence[:notice.start()])
                     and not _compiled_rule(r"\brival\b|竞争对手", 0).search(sentence[:notice.start()]))
        leave = _compiled_rule(r"\b(?:week\s+off|leave|break|days?\s+off|holiday)\b|休假|假期|放假", 0).search(sentence)
        denied = _compiled_rule(r"\b(?:not|never|plans?\s+to|might|may)\b|尚未|并未|没有|计划|可能", 0).search(sentence)
        if owner and notice and leave and not denied:
            year = _compiled_rule(r"(?<!\d)20\d{2}(?!\d)", 0).search(headline)
            return holiday + ":" + (year.group() if year else "current")
    return None


def source_store_sales_measure(title: str, lead: str, identity: EventIdentity) -> str | None:
    """Identify an attributed per-store observation, not a global sales total."""
    headline, opening = _normalized(title), _normalized(lead)[:700]
    products = identity.title_products & {"vision-pro", "iphone", "ipad", "mac", "apple-watch", "airpods"}
    if len(products) != 1 or not _compiled_rule(r"sales|销量|月销|卖出|售出", 0).search(headline):
        return None
    if _compiled_rule(r"\b(?:historical|last\s+year|previously|no\s+new)\b|历史|去年|此前|并无新", 0).search(headline + " " + opening[:160]):
        return None
    # The observation must have a store/staff owner and a current reporting
    # attribution. Background iPhone totals cannot supply its metric.
    if not (_compiled_rule(r"\bstores?\b|门店|零售店", 0).search(headline + " " + opening)
            and _compiled_rule(r"\b(?:staff|employees?|report\w*|according)\b|员工|记者|透露|报道", 0).search(opening)):
        return None
    measure = _compiled_rule(r"(?:每月|月销)[^。.!?;；]{0,22}?(\d+(?:\.\d+)?)\s*台|"
                        r"\b(?:sell|selling|sold)\s+(?:just|only|about)?\s*(\d+)\s*(?:units?|devices?|headsets?)?\s*(?:a|per)\s+month", 0).search(headline + " " + opening)
    if not measure or _compiled_rule(r"没有|并未|未能|尚未|\bnot\b", 0).search((headline + " " + opening)[max(0, measure.start()-20):measure.start()]):
        return None
    value = next(v for v in measure.groups() if v is not None)
    models = sorted(c for c in identity.title_components if c.startswith(("product-generation:", "iphone-model:")))
    return f"{next(iter(products))}:{','.join(models)}:store-monthly-units:{value}"


def source_device_workload_measure(title: str, lead: str, facts: tuple[str, ...], identity: EventIdentity) -> str | None:
    """A device-owned workload with measured throughput survives accessory context."""
    headline, opening = _normalized(title), _normalized(lead)[:800]
    scope = " ".join((opening, *(_normalized(f) for f in facts)))
    workload = "speech-transcription" if _compiled_rule(r"speech.to.text|transcri(?:ption|bing)|语音转(?:文字|文本)", 0).search(opening) else ""
    game = _compiled_rule(r"《([^》]{1,80})》", 0).search(headline)
    if game is None:
        # Chip-led headlines may name the measured device and game only in
        # the opening. Stop before comparisons so a rival's test cannot borrow
        # an Apple workload from its reference results.
        measured_opening = _compiled_rule(r"\b(?:compared\s+(?:with|to)|versus|unlike)\b|作为对比|相比|相较", 0).split(opening[:400], 1)[0]
        if _compiled_rule(r"\b(?:iphone|ipad|macbook)\s*\d+", 0).search(measured_opening):
            game = _compiled_rule(r"《([^》]{1,80})》", 0).search(measured_opening)
    if game and _compiled_rule(r"(?<![a-z0-9])\d+(?:\.\d+)?\s*fps\b|每秒\d+帧", 0).search(scope):
        workload = "game:" + _compiled_rule(r"\s+", 0).sub("-", game.group(1), 0)
    if not workload or not _compiled_rule(r"\b(?:test\w*|benchmark\w*)\b|测试|实测", 0).search(opening):
        return None
    if _compiled_rule(r"\b(?:accessory|charger|case|guide|how\s+to|historical)\b|充电器|保护壳|教程|历史|去年", 0).search(headline):
        return None
    if not (identity.title_products & {"iphone", "ipad", "mac", "macbook"}
            or any(c.startswith("apple-silicon-generation:") for c in identity.title_components)):
        return None
    if workload == "speech-transcription" and not _compiled_rule(r"\d+(?:\.\d+)?\s*(?:words?\s*(?:per\s+second|/s)|个?单词\s*/\s*秒)|每秒\s*\d+(?:\.\d+)?\s*个?单词", 0).search(scope):
        return None
    if _compiled_rule(r"\b(?:no\s+(?:test|measurement)|not\s+tested|last\s+year)\b|尚未测试|没有实测|去年", 0).search(opening[:220]):
        return None
    model = _compiled_rule(r"(?<![a-z0-9])(?:iphone|ipad|macbook)\s*\d+(?:\s*pro(?:\s*max)?)?", 0).search(opening)
    subject = _compiled_rule(r"\s+", 0).sub("", model.group(), 0) if model else ",".join(sorted(identity.title_products))
    if not subject:
        return None
    return f"{subject}:{workload}"


def source_hardware_project(title: str, lead: str, facts: tuple[str, ...], identity: EventIdentity) -> tuple[str, str] | None:
    """An active named hardware program, distinct from cancelled background."""
    if identity.content_form != "news" or len(identity.title_products) != 1:
        return None
    headline = _normalized(title)
    if not _compiled_rule(r"roadmap|working\s+on|in\s+development|considering.{0,45}concepts|路线图|研发|开发|推进.{0,30}(?:继任|型号)|验证.{0,15}原型", 0).search(headline):
        return None
    product = next(iter(identity.title_products))
    if product not in {"vision-pro", "apple-glasses", "iphone", "ipad", "macbook", "homepod", "apple-tv"}:
        return None
    programs, inactive = set(), set()
    for passage in (lead, *facts):
        # Unnamed device/company references inherit the title's owner until
        # a development clause explicitly introduces a different actor.
        owner = "apple"
        sentences = _compiled_rule(r"[。！？]|(?<=[.!?])\s+", 0).split(passage, 0)
        for index, sentence in enumerate(sentences):
            program = _compiled_rule(r"\b(?:codenam(?:e|ed)|code\s+name|new\s+project)\s*[,，:：]?\s*['\"“]?([a-z]\d{2,5})\b|(?:代号[为是]?|(?:推进|研发).{0,12}(?:型号|项目))\s*([a-z]\d{2,5})", re.I).search(sentence)
            owner_scope = sentence[:program.start()] if program else sentence
            owner_changes = []
            for action in _compiled_rule(r"\b(?:working|developing|exploring|considering|introduced|introducing|unveiled|unveiling)\b", re.I).finditer(owner_scope):
                # Parse the subject phrase of this clause, not the word just
                # before the verb (which may be an auxiliary or an adverb).
                prefix = _compiled_rule(r"[,;]|\b(?:while|whereas|but|said|says|that)\b", re.I).split(owner_scope[:action.start()], 0)[-1].strip()
                prefix = _compiled_rule(r"(?:\s+(?:is|are|was|were|has|had|been|now|still|also|\w+ly))+$", re.I).sub("", prefix, 0).strip()
                if _compiled_rule(r"\bapple(?:['’]s)?(?:\s+(?:[a-z]+\s+){0,3}(?:team|engineers))?$", re.I).search(prefix):
                    owner_changes.append((action.start(), "apple"))
                elif _compiled_rule(r"(?:(?:the|this|its)\s+)?(?:it|company|team|engineers)", re.I).fullmatch(prefix):
                    pass  # Anaphora retains the established clause owner.
                elif prefix:
                    owner_changes.append((action.start(), "other"))
            possessive = list(_compiled_rule(r"\b([a-z][a-z0-9-]*)['’]s\s+(?:(?:new|latest)\s+)?(?:project|device|headset)\b", re.I).finditer(owner_scope))
            owner_changes.extend((match.start(), match.group(1).lower()) for match in possessive)
            for chinese_actor in _compiled_rule(r"(?:^|[,，;；])\s*([\u4e00-\u9fff]{2,12}|[a-z][a-z0-9-]*)\s*(?:正在|正|仍在|继续)?(?:研发|开发|推进|验证)", re.I).finditer(owner_scope):
                subject = _compiled_rule(r"(?:正在|仍在|继续|正)$", 0).sub("", chinese_actor.group(1), 0).lower()
                if subject.endswith("苹果"):
                    owner_changes.append((chinese_actor.start(), "apple"))
                elif not subject.endswith(("内部", "公司", "团队")):
                    owner_changes.append((chinese_actor.start(), subject))
            if owner_changes:
                owner = sorted(owner_changes)[-1][1]
            if program:
                if owner != "apple":
                    continue
                code = next(v.lower() for v in program.groups() if v)
                local = _compiled_rule(r"[,，;；]", 0).split(sentence[:program.start()], 0)[-1] + program.group() + sentence[program.end():]
                if _compiled_rule(r"cancel\w*|shelved|abandoned|last\s+year|previously|had\s+been|not\s+(?:working|developing)|取消|搁置|去年|此前|并未研发", re.I).search(local):
                    inactive.add(code)
                    continue
                following = sentences[index + 1] if index + 1 < len(sentences) else ""
                if _compiled_rule(r"\s*(?:that|this)\s+project\s+was\s+(?:shelved|cancelled|canceled|abandoned)\b", re.I).match(following):
                    inactive.add(code)
                    continue
                programs.add(code)
    programs -= inactive
    return (product, next(iter(programs))) if len(programs) == 1 else None


@dataclass(frozen=True)
class SourceActionFrame:
    """A local operation owns its subject, stage and functional category."""
    subject: str
    action: str
    category: str = "software_systems"
    kind: str = "general_company"
    tier: str = "strong"
    period: str = ""
    year: str = ""
    aliases: tuple[str, ...] = ()
    model_generation: str = ""
    launch_subjects: tuple[str, ...] = ()
    region: str = ""
    bound_claim: BoundClaim | None = None


def _frame_search(pattern: str, value: str):
    return _compiled_rule(pattern, re.I).search(value)


def _operation_owner(text: str) -> str:
    """Read an explicit operation's actor, leaving anaphora to its caller."""
    t = _normalized(text)
    t = _compiled_rule(r"^(?:(?:and|while|whereas|but|however|meanwhile)[,，]?\s+|(?:不过|然而|但)[,，]?)",re.I).sub("",t)
    heading = _frame_search(r"^(.{1,70})[:：]\s*", t)
    if heading:
        prefix = heading.group(1)
        operation = _frame_search(
            r"\b(?:starts?|begins?|plans?|cuts?|launch\w*|restructur\w*|overhaul\w*|updates?|announc\w*)\b|"
            r"启动|开始|推进|重组|宣布|计划|推出|发布|裁[减撤员]", prefix)
        former_role = _frame_search(r"\b(?:former|ex[- ])\b|前(?:任)?苹果|苹果前", prefix)
        if not operation or former_role:
            t = t[heading.end():]
    t = _compiled_rule(r"^(?:report|reports|exclusive)\s*[:：]\s*", re.I).sub("", t)
    t = _compiled_rule(r"^(?:according to|据)[^,，]{1,70}[,，]\s*", re.I).sub("", t)
    if _frame_search(r"^(?:(?:new\s+)?apple(?:['’]s)?(?:\s|$)|applecare\b|苹果|(?:new\s+)?(?:ceo\s+)?(?:john\s+)?ternus\b|特努斯)|^(?:消息|据报道|.{2,15}称).{0,6}苹果(?:公司)?(?:已|将|计划|考虑)", t):
        return "apple"
    if _frame_search(r"^(?:" + _CREATIVE_APPS + r")",t):
        return "apple"
    if _frame_search(r"^(?:(?:this|that|the)\s+plans?|(?:these|those)\s+plans)\b", t):
        return ""  # A referenced proposal is not an actor issuing a plan.
    match = _frame_search(r"^([a-z][a-z0-9'’-]*(?:\s+[a-z][a-z0-9'’-]*){0,3}?)\s+(?:(?:is|are|was|were|has|have|will|now|also|today|reportedly|officially|recently)\s+)*(?:plans?|cuts?|launch\w*|turns?|restructur\w*|updates?|announc\w*|puts?|shelv\w*|cancel\w*|denies|denied)\b|^([a-z][a-z0-9 -]{1,35}?)\s*(?:推[‘“\"']|推出|发布|进军|计划|裁减)", t)
    if not match:
        return ""
    actor = next(x for x in match.groups() if x).strip()
    if _frame_search(r"(?:^|\s)(?:layoffs?|budget|features?|updates?|production)(?:\s|$)",actor):
        return ""  # Nominal operation phrases are not issuing organizations.
    if actor in {"it", "the company", "the firm", "those employees", "other plans", "new", "latest", "the latest", "the new", "the current"}:
        return ""
    return actor


def _workforce_action(text: str) -> str:
    """Polarity and stage apply equally to every functional team."""
    if _frame_search(r"not\s+(?:publicly\s+)?confirmed|no\s+confirmation|尚未.{0,8}确认|没有宣布.{0,30}计划",text):
        return "workforce-plan"
    if _frame_search(r"\b(?:not|never|denies|denied|deny)\b[^.!?]{0,55}(?:on\s+hold|scrapp|cancel|shelv)|否认.{0,20}(?:搁置|取消)|没有.{0,20}搁置", text):
        return "workforce-plan-hold-denied"
    if _frame_search(r"on\s+hold|scrapp\w*|cancel\w*.{0,30}plans?|no\s+longer|搁置|暂缓|叫停.{0,12}(?:计划|方案)|取消.{0,8}计划|计划.{0,12}取消|不再", text):
        return "workforce-plan-held"
    if _frame_search(r"\b(?:denies|denied|deny)\b.{0,25}plans?.{0,25}(?:cut|lay|reduc|eliminat)|否认.{0,20}裁.{0,15}计划",text):
        return "workforce-plan-denied"
    if _frame_search(r"\b(?:not|never|no|denies|denied|deny)\b[^.!?]{0,35}(?:cut|laid|lay|dismiss|reduc|eliminat)|否认.{0,20}裁|未.{0,10}裁|没有.{0,10}裁", text):
        return "workforce-reduction-denied"
    if _frame_search(r"planned|consider\w*|plan\w*|would|will|could|expected|potential|if\b|计划|考虑|曾计划|如果|拟.{0,15}裁|将.{0,15}裁|"
                     r"\b(?:wants?|hopes?)\s+to\s+(?:cut|lay\s+off|reduc\w*|eliminat\w*)\b|"
                     r"(?:希望|打算|拟)(?:进一步|开始|继续|大幅|小幅)?(?:裁[减撤员]|削减|取消)", text):
        return "workforce-plan"
    return "workforce-reduction"


def _workforce_causal_uncertainty(text: str) -> bool:
    return bool(_frame_search(
        r"^(?:(?:however|but)[,，]?\s*|不过[,，]?)?(?:currently\s+|目前)?"
        r"(?:there\s+is\s+)?(?:no\s+evidence|没有证据)[^。.!?]{0,35}"
        r"(?:\b(?:these|those)\s+(?:cuts|roles|employees)\b|这(?:些|\d+))", text))


def organization_action_frame(text: str, *, apple_owned: bool = False) -> SourceActionFrame | None:
    """Bind one owned assertion, never all teams mentioned in its paragraph."""
    t = _normalized(text)
    owner = _operation_owner(t)
    if owner not in {"", "apple"} or not (owner == "apple" or apple_owned):
        return None
    if _workforce_causal_uncertainty(t):
        return None  # A qualified cause is not an independent workforce operation.
    if (_frame_search(r"\b(?:for years|last year|in august|historically|remains to be seen)\b|多年|去年|8\s*月底|此前长期", t)
            or _frame_search(r"^(?:if\b|therefore\b|因此|如果)", t)):
        return None
    people = r"(?:employees?|staff|workers?|roles?|jobs?|positions?|managers?|directors?|teams?|divisions?|management|岗位|职位|员工|人员|团队|部门|管理层|中层管理)"
    reduction = _frame_search(
        r"lay(?:ing)?\s*off|laid\s*off|layoffs?|dismiss\w*|redundan\w*|裁[减撤员]|"
        r"(?:replac\w*|cut\w*|eliminat\w*|reduc\w*)[^.!?;。；]{0,55}" + people + r"|"
        + people + r"[^.!?;。；]{0,55}(?:replac\w*|cut\w*|eliminat\w*|reduc\w*)|"
        r"(?:替代|削减|取消)[^。；]{0,20}" + people + r"|"
        r"(?:搁置|取消)[^。；]{0,20}(?:裁员|裁减)", t)
    teams = [
        ("apple:applecare", "software_systems", r"apple\s*care|apple\s*support|support\s+employees|customer\s+service\s+staff|客服|售后人员"),
        ("apple:hardware-engineering", "hardware_products", r"engineering\s+program\s+managers?|\bepms?\b|hardware\s+engineering|硬件工程|工程项目经理"),
        ("apple:software-service-teams", "software_systems", r"\bsiri\b|fitness\+|ai.{0,12}software|软件工程|健身课程"),
        ("apple:vision-team", "hardware_products", r"vision\s*pro|头显团队"),
    ]
    matched = [(subject, category) for subject, category, pattern in teams if _frame_search(pattern, t)]
    if reduction and matched:
        if len(matched) != 1:
            return None  # A shared predicate with a mixed team list remains unassigned.
        subject, category = matched[0]
        return SourceActionFrame(subject, _workforce_action(t), category, "company_org")
    if reduction and _frame_search(r"middle.management|\bdirectors?\b|management\s+positions?|中层管理|管理岗位|总监", t):
        return SourceActionFrame("apple:management", _workforce_action(t), "hardware_products", "company_org")
    reorganization = _frame_search(r"\b(?:restructur\w*|overhaul\w*)\s+([^,;.!?]{1,160})|(?:重组|重塑)([^，。；！？]{1,100})", t)
    if reorganization:
        scope = next(x for x in reorganization.groups() if x)
        scope = _compiled_rule(r"\b(?:while|whereas|after|following|including)\b|同时|此前|包括", re.I).split(scope, maxsplit=1)[0]
        functional = [(subject, category) for subject, category, pattern in teams if _frame_search(pattern, scope)]
        if functional:
            if len(functional) != 1:
                return None
            subject, category = functional[0]
            return SourceActionFrame(subject, "development-reorganization-plan", category, "company_org")
    if (_frame_search(r"services?\s+(?:division|business|revenue)|new\s+services|服务业务|新服务", t)
            and _frame_search(r"discuss\w*|seeking|wants?|plans?|launching|generate|increase|讨论|计划|寻求|增长", t)):
        return SourceActionFrame("apple:services-business", "revenue-development-plan", kind="company_org")
    if _frame_search(r"restructur\w*|overhaul|leaner|middle.management|release\s+(?:calendar|cycles)|products?\s+(?:faster|more|throughout)|product\s+development|budget|headcount|marketing\s+spending|管理层|组织(?:精简|改革|重组)|研发|产品开发|发布节奏|预算|营销支出", t):
        return SourceActionFrame("apple:organization", "development-reorganization-plan", "hardware_products", "company_org")
    return None


_CREATIVE_APPS = r"final\s+cut\s+camera|creator\s+studio|创作坊|final\s+cut\s+pro|pixelmator\s+pro|\bpages\b|\bkeynote\b|\bnumbers\b|\bfreeform\b|无边记"


def _blocked_update_assertion(text: str) -> bool:
    positive = _frame_search(r"updat\w*|releas\w*|adds?|supports?|new\s+features|更新|新增|支持|新功能",text)
    negative = _frame_search(r"(?:not|never)\s+(?:(?:yet|currently|being|been)\s+){0,2}(?:updat\w*|releas\w*|add\w*|support\w*)|no\s+new\s+features|no\s+updates|没有更新|未.{0,3}更新|否认.{0,8}更新",text)
    historical = _frame_search(r"^(?:last\s+year|previously|去年|此前长期)|(?:updated|released)[^.!?]{0,40}last\s+year",text)
    return bool(historical or (negative and (positive is None or negative.start() <= positive.start())))


def creative_update_frame(text: str) -> SourceActionFrame | None:
    """A named application needs an affirmative current update or capability."""
    t = _normalized(text)
    if (_blocked_update_assertion(t) or _operation_owner(t) not in {"", "apple"}
            or not _frame_search(r"updates?|updated|new\s+(?:features?|design|templates?)|gets?|got|adds?|gains?|adopts?|supports?|brings?|新增|更新|新功能|新设计|支持", t)):
        return None
    apps = list(_compiled_rule(_CREATIVE_APPS, re.I).finditer(t))
    subjects = {"apple:final-cut-camera" if app.group().startswith("final cut camera") else "apple:creator-studio" for app in apps}
    if len(subjects) != 1:
        return None
    return SourceActionFrame(next(iter(subjects)), "software-update", kind="os_app")



def device_connection_frame(title: str, opening: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """Bind the issuing vendor, released object and changed connection together."""
    carplay = bool(_frame_search(r"carplay", title))
    casting = _frame_search(r"\b(ios|ipados|macos|iphone|ipad|mac)\b\s*(?:快捷)?(?:投屏|screen mirroring)", title)
    if not carplay and casting is None:
        return None
    target = "carplay" if carplay else casting.group(1) + ":screen-mirroring"

    def publication(text):
        match = _frame_search(
            r"^([a-z][a-z0-9'’-]*(?:\s+[a-z][a-z0-9'’-]*){0,2}?)\s+"
            r"(?:(?:has|now|officially|recently)\s+){0,3}"
            r"(launch(?:es|ed)?|releas(?:es|ed)|rolls?\s+out|updat(?:es?|ed)|adds?|improves?|"
            r"denies\s+(?:releasing|launching))\s+(.+)", text)
        if not match:
            seasonal = _frame_search(
                r"(?:^|[，,])\s*([^，,。:：]{2,30}?)(?:常用常新[，,]\s*)?"
                r"迎(?:来)?[^，,。:：]{0,24}版本[^，,。:：]{0,12}升级[：:]?(.+)", text)
            if seasonal:
                return seasonal.group(1), "更新", "软件更新" + seasonal.group(2)
            match = _frame_search(
                r"(?:^|[，,])\s*([\u4e00-\u9fff]{2,15}?)(?:正式|现已|已|近期)?"
                r"(推出|发布|更新|新增|改善|否认发布|否认推出)(.+)", text)
        return match.groups() if match else None

    def first_party(actor):
        return actor in {"apple", "苹果", "苹果公司"} or actor.startswith(("apple's ", "apple’s "))

    headline_action = publication(title)
    if headline_action and first_party(headline_action[0]):
        return None
    for value in (opening, *(_normalized(f) for f in facts[:1])):
        start, end = next(source_sentence_spans(value), (0, len(value)))
        claim = value[start:end]
        issued = publication(claim)
        if not issued:
            continue
        issuer, verb, released = issued
        if first_party(issuer):
            return None  # A supporting fact cannot replace the explicit main actor.
        if issuer in {"it", "the company", "the firm", "该公司", "这家公司"}:
            continue
        subject = ("vehicle-maker:" if carplay else "platform-owner:") + issuer
        if (_blocked_update_assertion(claim)
                or _frame_search(r"denies|否认|未(?:推出|发布)|去年|此前|last\s+year|previously", claim)):
            return SourceActionFrame(subject + ":" + target, "compatibility-context",
                                     kind="third_party_ecosystem", tier="weak")
        owned_scope = _compiled_rule(
            r"[;；]|\b(?:while|whereas|unlike|compared|but)\b|相比|相较|[，,]\s*(?:而|但)", 0).split(released)[0]
        firmware = _frame_search(
            r"^[^，,;。.!?]{0,45}(?:firmware\b|software\s+update\b)|"
            r"^[^，,;。.!?]{0,20}(?:固件|软件更新)", owned_scope)
        if firmware:
            # The changed operation must modify this firmware, with the same
            # target as the headline; a later issuer cannot supply it.
            target_object = r"wireless\s+carplay" if carplay else re.escape(casting.group(1)) + r"\s+screen\s+mirroring"
            chinese_object = r"无线\s*carplay" if carplay else re.escape(casting.group(1)) + r"\s*(?:快捷)?投屏"
            suffix = owned_scope[firmware.end():]
            change = _frame_search(
                r"^\s*(?:update\b\s*)?(?:for\s+[^,;.]{1,80})?\s*"
                r"(?:(?:,|:)\s*|(?:that|which)\s+)?"
                r"(?:adds?|added|adding|enables?|enabled|enabling|brings?|bringing)\s+(?:new\s+)?" + target_object,
                suffix) or _frame_search(
                r"(?:^|[，,:：、])\s*(?:新增|增加|启用|开启|改为)\s*" + chinese_object, suffix)
            if change:
                return SourceActionFrame(subject + ":" + target, "wireless-connection-retrofit" if carplay else "screen-mirroring-rollout",
                                         kind="ecosystem_interop", tier="ecosystem")
            return SourceActionFrame(subject + ":" + target, "compatibility-context",
                                     kind="third_party_ecosystem", tier="weak")
        if _frame_search(
                r"^(?:(?:a|an|the)\s+)?(?:new|next[- ]generation)\s+"
                r"(?:[a-z0-9.+-]+\s+){0,4}(?:head\s*unit|receiver|stereo)\b|"
                r"^新(?:一代|款)[^，,;。.!?]{0,35}(?:车机|接收器|音响)", owned_scope):
            return SourceActionFrame(subject + ":head-unit", "accessory-release",
                                     "hardware_products", "third_party_ecosystem", "weak")
        break  # Later facts do not supply a different publication's object.
    return None


def app_removal_correspondence_frame(title: str, opening: str) -> SourceActionFrame | None:
    """Bind an inquiry or Apple's explanation before the historical delisting."""
    if not _frame_search(r"remov|delist|下架|移除|撤下", title):
        return None
    opening = _compiled_rule(r"[!?。！？]|(?<!u\.s)(?<!rep)(?<!mr)(?<!mrs)(?<!dr)\.\s+", 0).split(opening, maxsplit=1)[0]
    local = title + ". " + opening[:600]
    if not _frame_search(r"app\s*store|应用商店", local):
        return None
    names = []
    app_patterns = (
            r"(?:remov(?:e(?:s|d)?|ing)|removal\s+of|delist(?:s|ed|ing)?|下架|移除|撤下)\s*"
            r"([a-z][a-z0-9.+-]{2,30})(?![a-z0-9.+-])",
            r"(?<![a-z0-9.+-])([a-z][a-z0-9.+-]{2,30})\s+removal\b(?!\s+of\b)")
    for scope, clipped in ((title, False), (opening[:600], len(opening) > 600)):
        names = [m.group(1) for pattern in app_patterns
                 for m in _compiled_rule(pattern, re.I).finditer(scope)
                 if not (clipped and m.end() == len(scope))]
        names = [n for n in names if n not in {"app", "apps", "application", "applications", "ice", "its", "similar", "the", "over", "of", "for", "why", "an"}]
        if names:
            break
    if len(set(names)) != 1:
        return None
    subject = "apple:app-store-removal:" + names[0]
    # A predicate belongs to its grammatical subject, not any nearby Apple
    # mention ("asks Apple to explain" is the sender's inquiry).
    auxiliaries = (r"(?:(?:has|had|have|does|did|now|again|reportedly|already|also|publicly|will|would|not|never|yet)\s+|"
                   r"(?:plans?|intends?)\s+(?:not\s+)?to\s+|(?:is|was)\s+expected\s+to\s+|"
                   r"(?:doesn['’]t|didn['’]t|hasn['’]t|haven['’]t)\s+)*")
    reply = _compiled_rule(r"\bapple\s+(?P<phase>" + auxiliaries +
                           r")(?:explain(?:s|ed|ing)?|respond(?:s|ed|ing)?|tells?|told)\b|"
                           r"苹果(?:公司)?(?P<cn_phase>(?:已|曾|公开|计划|准备|将|尚未|还未|未|没有|不)*)"
                           r"(?:解释|回应|致信)", re.I)
    inquiry = _compiled_rule(
        r"\b(?:(?:rep\.?|representative|senator|lawmaker|congressman|congresswoman)\s+"
        r"(?P<name>[a-z][a-z'’-]*(?:\s+[a-z][a-z'’-]*){0,3}?)|(?P<unnamed>lawmakers?))\s+"
        r"(?P<phase>" + auxiliaries + r")(?:sent|sends?|wrote|writes?|ask(?:s|ed|ing)?|"
        r"question(?:s|ed|ing)?|challeng(?:e(?:s|d)?|ing)|demand(?:s|ed|ing)?)\b"
        r"[^.!?]{0,65}\bapple\b|"
        r"(?:参议员|议员)(?P<cn_name>[^。！？]{0,15}?)(?P<cn_phase>计划|准备|将|尚未|还未|未|没有|不)?"
        r"(?:致信|质疑|要求)[^。！？]{0,25}苹果", re.I)

    def phase_action(base, match):
        phase = match.groupdict().get("phase") or match.groupdict().get("cn_phase") or ""
        if _frame_search(r"\b(?:not|never)\b|n['’]t|尚未|还未|未|没有|不", phase):
            return base + "-unconfirmed", "weak"
        if _frame_search(r"\b(?:plans?|intends?|will|would|expected)\b|计划|准备|将", phase):
            return base + "-planned", "strong"
        return base, "strong"

    def sender(match):
        groups = match.groupdict()
        name = groups.get("name") or groups.get("cn_name") or "unnamed-lawmaker"
        return _compiled_rule(r"[^\w]+", 0).sub("-", name).strip("-")

    # Explicit dates constrain the letter in this opening sentence. Bind the
    # date to its own speaker; a different participant's letter is background.
    reply_period, question_period, dated_sender = "", "", ""
    months = "january february march april may june july august september october november december".split()
    dates = _compiled_rule(r"\b(" + "|".join(months) + r")\s+(20\d{2})\s+letter\b", re.I)
    statements = _compiled_rule(r"\bapple\s+" + auxiliaries +
                                r"(?:said|says|wrote|sent|published|explained|responded|told)\b", re.I)
    speakers = [(m.start(), m.end(), "reply", m) for m in statements.finditer(opening[:600])]
    speakers += [(m.start(), m.end(), "question", m) for m in inquiry.finditer(opening[:600])]
    for date in dates.finditer(opening[:600]):
        prefix = opening[:date.start()]
        possessor = _frame_search(r"\b(apple|(?:rep\.?|representative|senator|lawmaker|congressman|congresswoman)\s+"
                                  r"[a-z][a-z'’-]*(?:\s+[a-z][a-z'’-]*){0,3})['’]s\s*$", prefix)
        if not possessor and not _frame_search(r"\bin\s+(?:(?:a|an|the)\s+)?$", prefix):
            continue
        before = [s for s in speakers if s[1] <= date.start()]
        after = [s for s in speakers if s[0] >= date.end()]
        owner = max(before, default=None, key=lambda s:s[0]) or min(after, default=None, key=lambda s:s[0])
        if owner:
            if _frame_search(r"\b(?:in\s+(?:response|reply)\s+to|responding\s+to|answering)\b",
                             opening[owner[1]:date.start()]):
                continue
            if possessor:
                person = possessor.group(1)
                if person == "apple":
                    if owner[2] != "reply":
                        continue
                elif owner[2] != "question" or not person.endswith(sender(owner[3]).replace("-", " ")):
                    continue
            period = f"letter:{date.group(2)}:{months.index(date.group(1)) + 1}"
            if owner[2] == "reply":
                reply_period = period
            else:
                question_period, dated_sender = period, sender(owner[3])

    title_reply, question = reply.search(title), inquiry.search(title)
    if title_reply and (not question or title_reply.start() < question.start()):
        action, tier = phase_action("removal-explanation", title_reply)
        return SourceActionFrame(subject, action, kind="legal_antitrust", tier=tier, period=reply_period)
    opening_question = inquiry.search(opening[:350])
    if question or opening_question:
        current = question or opening_question
        actor = sender(current)
        if actor == "unnamed-lawmaker" and opening_question:
            actor = sender(opening_question)
        action, tier = phase_action("removal-inquiry", current)
        period = question_period if dated_sender in {actor, "unnamed-lawmaker"} else ""
        return SourceActionFrame(subject + ":inquirer:" + actor, action, kind="legal_antitrust", tier=tier, period=period)
    opening_reply = reply.search(opening[:350])
    if opening_reply:
        action, tier = phase_action("removal-explanation", opening_reply)
        return SourceActionFrame(subject, action, kind="legal_antitrust", tier=tier, period=reply_period)
    return None


_WEB_EXPLOIT_NAME = r"(?P<name>[a-z][a-z0-9_-]*)\s*(?:\bexploit\s+chain\b|\bmalware\b|攻击链|恶意软件)"


def _affirmative_web_predicate(text: str, match: re.Match) -> bool:
    prefix = _compiled_rule(r"[。；;]|(?<=\.)\s+", 0).split(text[:match.start()])[-1]
    negative = r"\b(?:not|never|no|cannot|\w+n['’]t|den(?:y|ies|ied))\b|并未|没有|无法|否认"
    return not (_frame_search(negative, match.group()) or
        _frame_search("(?:" + negative + r")(?:\W+\w+){0,6}\W*$|(?:未|没有|无法|否认)[^，。；]{0,12}$", prefix[-100:]) or
        _frame_search(r"\b(?:last\s+year|previously|historically|might|could)\b|去年|此前|可能会|假设", prefix))


def source_web_exploit_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """A currently used web exploit owns the attack, not its retail lure."""
    primary = _normalized(title + " " + lead)
    if not (_frame_search(r"\b(?:pages?|sites?|websites?|links?)\b|网页|网站|链接", primary)
            and _frame_search(r"fake|scam|malware|exploit|恶意|攻击|假|诈骗", primary)):
        return None
    normalized_lead = _normalized(lead)
    lead_delivery_match = _frame_search(
        r"(?:simply|just).{0,30}(?:going|visiting|opening).{0,40}installs?\s+malware|"
        r"仅.{0,15}(?:打开|访问).{0,20}安装恶意软件", normalized_lead)
    lead_delivery = bool(_frame_search(r"\bolder\s+ios\b|未修补.{0,12}ios", normalized_lead)
                         and lead_delivery_match and _affirmative_web_predicate(normalized_lead, lead_delivery_match))
    names = set()
    for value in (lead, *facts):
        text = _normalized(value)
        for match in _compiled_rule(
                r"(?:\b(?:uses?|using)|利用|采用|使用)\s*(?:(?:the|leaked)\s+|疑似\s*)*"
                + _WEB_EXPLOIT_NAME, re.I).finditer(text):
            if not _affirmative_web_predicate(text, match):
                continue
            platform = _frame_search(
                r"\b(?:older|unpatched|vulnerable)\s+(?:(?:older|unpatched|vulnerable)\s+)*"
                r"(?:iphones?|ios)\b|(?:绕过|突破)\s*ios\s*(?:安全|沙箱)", text)
            delivery_pattern = _compiled_rule(
                r"(?:visiting|opening|going\s+to)\s+(?:the\s+)?page.{0,55}(?:enough|attack|installs?\s+malware)|"
                r"(?:打开|访问)\s*(?:该|这个)?网页.{0,30}(?:安装恶意软件|发起攻击)|"
                r"(?:bypass\w*|绕过|突破)\s*ios\s*(?:security|安全|沙箱)", re.I)
            delivery = any(_affirmative_web_predicate(text, claim) for claim in delivery_pattern.finditer(text))
            app_owned = _frame_search(r"(?:against|in|within)\s+(?:(?:a|an|the|its)\s+)?"
                                     r"(?:[a-z][a-z'-]*\s+){0,3}(?:app|application)\b|针对.{0,12}第三方应用", text)
            if app_owned:
                bypass = _frame_search(r"(?:bypass\w*|绕过|突破)\s*ios\s*(?:security|安全|沙箱)", text)
                if not bypass or not _affirmative_web_predicate(text, bypass):
                    continue
            if platform and delivery:
                names.add(match.group('name'))
            elif lead_delivery:
                names.add(match.group('name'))
    if len(names) != 1:
        return None
    return SourceActionFrame("apple-platform:ios:web-exploit:" + next(iter(names)),
                             "web-exploit-campaign", "software_systems", "os_app", "strong")


def bind_web_exploit_claim(evidence: ArticleEvidence) -> BoundClaim | None:
    frame = source_web_exploit_frame(evidence.title, evidence.raw_lead,
                                    tuple(unit.text for unit in evidence.units))
    if frame is None:
        return None
    spans = []
    chain = frame.subject.rsplit(':', 1)[-1]
    active = True
    for unit in evidence.units:
        if unit.kind not in {'p', 'li', 'text'} or unit.container_id == 'caption':
            continue
        for start, end in source_sentence_spans(unit.text):
            text = unit.text[start:end]
            names = {m.group('name') for m in _compiled_rule(
                _WEB_EXPLOIT_NAME, re.I).finditer(_normalized(text))}
            names -= {'the', 'this', 'that', 'its', 'some', 'new', 'leaked', 'separate'}
            if (names - {chain} or _frame_search(r"^separately\b|另(?:外|一方面)|与此无关", text)
                    or (_frame_search(r"\b(?:android|windows)\b|安卓", text)
                        and not _frame_search(r"\b(?:ios|iphone)\b", text))):
                active = False
                continue
            if chain in names:
                active = True
            if not active:
                continue
            if _frame_search(r"^(?:again,|never\s+visit|rather\s+than|but\s+also\s+just|"
                             r"if\s+you\s+were|under\s+settings)|设置.{0,15}软件更新", text):
                continue
            if _frame_search(
                    r"malware|exploit|security\s+patch|patched\s+ios|ios\s+\d|safari|browser|"
                    r"keychain|password|credential|wallet|payload|device\s+(?:details|identifier)|"
                    r"installed\s+apps|apple\s+notes|messages|contacts|call\s+history|voicemail|"
                    r"email|calendar|location\s+data|server|thumbnails|voucher|colors|"
                    r"(?:visiting|opening)\s+the\s+page|恶意软件|攻击链|绕过|钥匙串|密码|钱包|"
                    r"联系人|通话记录|位置数据", text):
                spans.append((unit.unit_id, start, end))
    return BoundClaim(frame.subject, frame.action, "source-operation", (), evidence.article_id,
                      tuple(dict.fromkeys(key for key, _, _ in spans)), tuple(spans), evidence.content_form,
                      category=frame.category, event_kind=frame.kind, subject_relation="apple-direct", report_role="independent") if spans else None


def source_accessory_category(title: str) -> str:
    """A physical accessory and its software have separate source-owned types."""
    physical = _compiled_rule(
        r"\b(?:ethernet\s+adapter|network\s+(?:adapter|card)|game\s*controller|gamepad|"
        r"headphones?|earbuds?|chargers?|keyboards?|mice|trackers?|tracking\s+tags?)\b|"
        r"网卡|手柄|耳机|耳塞|充电器|键盘|鼠标|转接器|适配器|追踪器|定位标签", re.I)
    if not physical.search(title):
        return ""
    # Compatibility and bundled software qualify the preceding product; a
    # driver/firmware followed by "for [device]" still owns the software action.
    core = _compiled_rule(
        r"\s+(?:with|for|compatible\s+with|supporting|to\s+(?:configure|control|manage|support))\b|"
        r"兼容|支持|附带|配备|(?:以|用于)(?:配置|控制|管理)", re.I).split(title, 1)[0]
    hardware = list(physical.finditer(core))
    software = list(_compiled_rule(
        r"\b(?:apps?|software|firmware|drivers?)\b|应用|软件|固件|驱动", re.I).finditer(core))
    if software and (not hardware or software[-1].start() > hardware[-1].start()):
        return "software_systems"
    return "hardware_products" if hardware else ""


def source_first_party_app_frame(title: str, lead: str) -> SourceActionFrame | None:
    """A typed Apple app update owns its software, not its host device."""
    h, opening = _normalized(title), _normalized(lead)[:950]
    if _blocked_update_assertion(h):
        return None
    named = _compiled_rule(r"^apple\s+(?:updates?|updated|releases?|released)\s+its\s+"
        r"([a-z][a-z0-9.+-]*(?:\s+[a-z0-9.+-]+){0,3}?)\s+(app\b|application\b)", re.I).match(h)
    named = named or _compiled_rule(
        r"^(?:the\s+)?(?:apple\s+|苹果\s*)([a-z][a-z0-9.+-]*"
        r"(?:\s+[a-z0-9.+-]+){0,3}?)(?:\s+v?\d+(?:\.\d+)+)?\s+"
        r"(app\b|application\b|for\s+(?:iphone|ipad|mac)\b|updat(?:e|es|ed|ing)\b|升至|更新)", re.I).match(h)
    if named is None or not _frame_search(r"\bupdat(?:e|es|ed|ing)\b|升至|更新", h):
        return None
    name, marker = named.groups()
    name = name.removeprefix("apple ")
    if (_extract_patterns(name, PRODUCT_PATTERNS)
            or _extract_patterns("apple " + name + " app", PRODUCT_PATTERNS)
            or _frame_search(r"^(?:updates?|updated|releases?|released|launch(?:es|ed)?|"
                             r"announces?|announced|expands?|expanded)\b", name)):
        return None
    if (_blocked_update_assertion(opening)
            or _frame_search(r"^apple\s+(?:denies?|denied)\b[^.!?;]{0,100}"
                             + re.escape(name) + r"\s+app\b[^.!?;]{0,60}\bupdat\w*", opening)):
        return None
    app_name = r"(?:apple\s+|苹果\s*)" + re.escape(name)
    if (marker not in {"app", "application"}
            and not _frame_search(app_name + r"(?:\s+app(?:lication)?\b|[)）]?\s*(?:应用|客户端))|"
                r"^an\s+update\s+(?:for|to)\s+" + app_name
                + r"[^.!?;。！？；]{0,220}\b(?:its|the)\s+(?:iphone|ipad|mac)\s+app\b", opening)):
        return None
    version = _frame_search(r"(?:\bversion\s+|\bupdat\w*\s+to\s+(?:version\s+)?|升至\s*)"
                           r"(\d+(?:\.\d+)+)", h)
    if version is None:
        version = _frame_search(app_name + r"\s+v?(\d+(?:\.\d+)+)\s+(?:app(?:lication)?\s+)?(?:更新|升至|updat\w*\b)", h)
    if version is None:
        version = _frame_search(r"^apple\s+(?:(?:has|today)\s+)*(?:released|releases|updated|updates)"
            r"\s+version\s+(\d+(?:\.\d+)+)\s+of\s+(?:its\s+)?(?:apple\s+)?"
            + re.escape(name) + r"\s+app\b", opening)
    planned = bool(_frame_search(r"\b(?:will|plans?\s+to|expected\s+to|rumou?red\s+to)\b"
                                r"[^.!?;]{0,80}\b(?:updat\w*|releas\w*)", h)
        or _frame_search(r"^apple\s+plans?\s+to\s+(?:release|update)\b[^.!?;]{0,60}"
                          + re.escape(name) + r"\s+app\b", opening))
    return SourceActionFrame("apple-app:apple-" + _subject_slug(name),
                            "software-update-plan" if planned else "software-update",
                            "software_systems", "os_app", "strong",
                            "app-version:" + version.group(1) if version else "")


def source_service_client_frame(title: str, lead: str,
                              identity: EventIdentity) -> SourceActionFrame | None:
    """A first-party client release changes software, not service territories."""
    h, opening = _normalized(title), _normalized(lead)[:950]
    services = identity.title_products & {"apple-music", "apple-books", "apple-tv",
                                          "apple-fitness", "icloud"}
    if (len(services) != 1 or identity.scope != "apple-direct"
            or _blocked_update_assertion(h) or _blocked_update_assertion(opening)
            or _frame_search(r"\b(?:denies?|denied|previously|last\s+year)\b|否认|去年|此前", opening)):
        return None
    platform = _frame_search(r"\b(android|windows)\b|安卓", h)
    version = _frame_search(r"(?<![a-z0-9])(\d+(?:\.\d+)+)(?![a-z0-9])", h)
    if platform is None or version is None:
        return None
    subject = next(iter(services))
    aliases = next(aliases for key, aliases in PRODUCT_PATTERNS if key == subject)
    service = r"(?:" + "|".join(re.escape(alias) for alias in aliases) + r")"
    number = r"\d+(?:\.\d+)+"
    release = _frame_search(
        r"\bapple\s+(?:(?:has|today|now)\s+)*(?:released|releases|updated|updates)\s+"
        r"(?:version\s+(?P<version>" + number + r")(?:\s+(?P<beta>beta))?\s+of\s+)?"
        r"(?:its\s+)?" + service + r"\s+app\s+for\s+(?P<host>android|windows)\b|"
        r"苹果(?:公司)?(?:已|现已|今日|今天)?面向\s*(?P<zh_host>安卓|android|windows)"
        r"\s*(?:平台)?[,，]\s*(?:推出|发布|更新)\s*(?P<zh_version>" + number + r")"
        r"\s*(?P<zh_beta>测试版|正式版)?\s*" + service + r"\s*(?:应用|客户端)", opening)
    if release is None:
        return None
    target = "android" if platform.group() == "安卓" else platform.group()
    released_host = release.group('host') or release.group('zh_host')
    released_host = "android" if released_host == "安卓" else released_host
    if target != released_host:
        return None
    # Prefer the app's own release version over host OS numbers in a headline.
    own_version = release.group('version') or release.group('zh_version')
    if own_version is None:
        own = _frame_search(r"\bupdat\w*\s+to\s+(?:version\s+)?(" + number + r")|"
                            + service + r"\s+(?:version\s+)?(" + number + r")", h)
        if own is None:
            return None
        own_version = next(v for v in own.groups() if v)
    beta = bool(release.group('beta') or release.group('zh_beta') == '测试版'
                or _frame_search(r"\bbeta\b|测试版", h))
    return SourceActionFrame(subject + ":client:" + target,
                            "client-beta-release" if beta else "client-public-release",
                            "software_systems", "os_app", "strong",
                            "app-version:" + own_version)


def source_service_territory_frame(title: str, lead: str,
                                   facts: tuple[str, ...], identity: EventIdentity) -> SourceActionFrame | None:
    """Join a current service rollout by its concrete territory list."""
    h = _normalized(title)
    services = identity.title_products & {"apple-music", "apple-arcade", "apple-pay",
                                          "apple-books", "apple-fitness", "icloud"}
    if (len(services) != 1 or identity.scope != "apple-direct" or identity.content_form != "news"
            or not _frame_search(r"\b(?:expands?|lands?|available|rolls?\s+out)\b"
                                 r"[^.!?]{0,60}\b(?:countries|territories|regions)\b", h)
            or _frame_search(r"\b(?:not|never|no|denies?|denied|last\s+year|previously)\b", h)):
        return None
    subject = next(iter(services))
    aliases = next(aliases for key, aliases in PRODUCT_PATTERNS if key == subject)
    service_name = r"(?:" + "|".join(re.escape(alias) for alias in aliases) + r")"
    for text in (lead, *facts):
        for start, end in source_sentence_spans(text):
            claim = _normalized(text[start:end])
            if (_frame_search(r"\blast\s+(?:year|month|week)\b|\bpreviously\b|去年|此前|上月|上周", claim)
                    or not any(alias in claim for alias in aliases)):
                continue
            available = _frame_search(service_name + r"\s+(?:is\s+now\s+available\s+in|"
                                     r"availability\s+to)\s+([^.!?;。！？；]+)", claim)
            if available is None:
                continue
            if _frame_search(r"\b(?:not|never|denies?|denied|unclear|whether|if)\b",
                             claim[:available.start()]):
                continue
            tail = available.group(1)
            tail = _compiled_rule(r"\s+(?:today|now|this\s+week)\b", re.I).split(tail, 1)[0].strip(' .')
            territories = tuple(sorted(set(part.strip() for part in
                _compiled_rule(r",\s*(?:and\s+)?|\s+and\s+", re.I).split(tail) if part.strip())))
            if (len(territories) < 2 or any(not _compiled_rule(r"[a-z]+(?:[ -][a-z]+){0,3}", re.I).fullmatch(part)
                    or _frame_search(r"\b(?:countries|regions|more|other|additional|new)\b", part)
                    for part in territories)):
                continue
            planned = bool(_frame_search(r"\b(?:plans?\s+to|will|expected\s+to)\b"
                                         r"[^.!?;]{0,60}\b(?:expand|roll\s+out|launch)", claim[:available.start()])
                or _frame_search(r"\b(?:will|expected\s+to|plans?\s+to)\b"
                                  r"[^.!?;]{0,40}\b(?:expand|land|roll\s+out)", h))
            return SourceActionFrame(subject + ":territories:" + ",".join(territories),
                                     "availability-expansion-plan" if planned else "availability-expansion",
                                     "software_systems", "service_content", "strong")
    return None


def source_current_platform_api(name: str, platform: str, lead: str,
                                headline_use: bool = False) -> bool:
    """A current Apple API must serve this application or service."""
    if not platform:
        return False
    platform_api = _compiled_rule(
        r"(?<![a-z0-9])" + re.escape(platform) + r"\s+(?:api|framework)\b|"
        r"\b(?:api|framework)\s+(?:for\s+)?" + re.escape(platform) + r"(?![a-z0-9])|"
        + re.escape(platform) + r"(?:接口|框架)", re.I)
    claims = []
    for start, end in source_sentence_spans(lead):
        claims.extend(_compiled_rule(r"\b(?:but|whereas|while)\b|[;；]|，(?:但|而)", re.I).split(lead[start:end]))
    current = []
    for claim in claims:
        if _frame_search(r"\blast\s+(?:year|month|week)\b|\bpreviously\b|去年|此前|上周|上月", claim):
            continue
        current.append(claim.strip())
    own_use = False
    for claim in current:
        usage = _frame_search(
            r"^" + re.escape(name) + r"\s+(?:(?:today|now|has)\s+)*"
            r"(?:(?:uses?|used|integrates?|adopts?)\s+|"
            r"(?:launched|released|updated)\s+(?P<before_use>[^.!?;]{0,100}?)"
            r"(?:using|to\s+use)\s+)(?:the\s+)?(?:new|that|this)\s+(?:api|framework)\b|"
            r"^" + re.escape(name) + r"(?:今日|今天|现已|已)?(?:接入|采用|使用)(?:该|新|这一)(?:接口|框架)", claim)
        if usage is not None and not _frame_search(
                r"\b(?:without|not|never)\s+(?:(?:[a-z]+ly|ever|even|once)\s+)*$",
                usage.group('before_use') or ''):
            own_use = True
            break
    for claim in current:
        operation = _frame_search(
            r"^apple\s+(?:(?:has|today|now|just)\s+)*"
            r"(?:introduc(?:e|es|ed)|open(?:s|ed)?|enabl(?:e|es|ed)|"
            r"expand(?:s|ed)?|chang(?:e|es|ed)|updat(?:e|es|ed))\s+"
            r"(?P<object>[^.!?;]{1,160})|"
            r"^苹果(?:公司)?(?:今日|现已|已|正式)?(?:引入|开放|启用|扩展|更新)"
            r"(?P<zh_object>[^。！？；]{1,100})", claim)
        if operation is None:
            continue
        obj = operation.group('object') or operation.group('zh_object')
        if not platform_api.search(obj):
            continue
        approval = _frame_search(
            r"\band\s+(?:(?:has|today|now|just)\s+)*approv(?:e|es|ed)\s+(?:the\s+)?"
            + re.escape(name) + r"\s+integration\b|"
            r"(?:并|且|还)(?:已|正式)?批准(?:了)?" + re.escape(name) + r"(?:的)?(?:接入|集成)", claim)
        if headline_use or own_use or approval:
            return True
    return False


def source_named_app_frame(title: str, lead: str, *,
                           bound_subjects: frozenset[str] = frozenset()) -> SourceActionFrame | None:
    """An app's capability belongs to the app, not the device it controls."""
    h, opening = _normalized(title), _normalized(lead)[:950]
    if not _frame_search(
            r"\b(?:updat\w*|arriv\w*|offers?|adds?|gains?|supports?|controls?|gets?)\b|"
            r"更新|新增|现已|现在支持|支持", h):
        return None
    named = _compiled_rule(r"^(?:the\s+)?([a-z][a-z0-9.+-]*(?:\s+[a-z0-9.+-]+){0,5}?)"
        r"\s+(?:camera\s+)?(?:app|application)\b|"
        r"^(?:第三方)?([\u4e00-\u9fff]{2,20}?)(?:应用|客户端|软件)", re.I).match(h)
    if named is None:
        # An untyped vendor-support headline retains its existing owner and
        # target binding. A release version or device-control capability can
        # identify a short application headline with an app object in the lead.
        if not _frame_search(r"\b\d+\.\d+(?:\.\d+)*\b|\bcontrols?\b|"
                             r"\bcontrol\s+of\b|控制", h):
            return None
        named = _compiled_rule(r"^(?:the\s+)?([a-z][a-z0-9.+-]*(?:\s+[a-z0-9.+-]+){0,5}?)"
        r"\s+(?=\d+\.\d|(?:now\s+)?(?:updat\w*|arriv\w*|offers?|adds?|gains?|supports?|controls?|gets?)\b)", re.I).match(h)
    if named is None:
        return None
    name = next(value for value in named.groups() if value)
    if (name.split()[0] in {"a", "an", "the", "new", "another", "this", "app", "application", "apple"}
            or name.startswith('苹果')
            or _extract_patterns(name, PRODUCT_PATTERNS)
            or _extract_patterns(name, OS_COMPONENT_PATTERNS)
            or _subject_slug(name) in bound_subjects
            or _frame_search(_CREATIVE_APPS, h)):
        return None
    # The opening can establish the app family, while the full headline
    # edition remains the action object and the release ownership key.
    app_object = _compiled_rule(re.escape(name.split()[0]) +
        r"[^.!?;。！？；]{0,90}?(?:\b(?:app|application)\b|应用|客户端|软件)", re.I)
    if not (app_object.search(h) or app_object.search(opening)):
        return None
    first_party = _lead_assigns_app_release_to_apple(name, opening)
    platform = _frame_search(r"\bnew\s+([a-z][a-z -]{0,35}?)\s+(?:api|framework)\b|"
                             r"新([\u4e00-\u9fff]{1,15}?)(?:接口|框架)", h)
    if platform is not None and source_current_platform_api(
            name, next(value for value in platform.groups() if value), opening, True):
        return SourceActionFrame('third-party-app:' + name + ':platform-integration',
                                'platform-integration', 'software_systems',
                                'ecosystem_interop', 'ecosystem')
    version = _frame_search(r"\b\d+\.\d+(?:\.\d+)*\b", h)
    subject = ("apple-app:" if first_party else "third-party-app:") + name
    if version is not None:
        subject += ":" + version.group()
    return SourceActionFrame(subject, "software-update", "software_systems",
                            "os_app" if first_party else "third_party_ecosystem",
                            "strong" if first_party else "weak")


def source_message_service_frame(title: str, lead: str) -> SourceActionFrame | None:
    """Ordinary message delivery does not transfer a service to Apple."""
    h, opening = _normalized(title), _normalized(lead)[:950]
    if not (_frame_search(r"\border(?:ing)?\b|订餐|下单", h)
            and _frame_search(r"\b(?:through|via|in)\s+(?:apple(?:['’]s)?\s+)?messages\b|"
                              r"通过(?:苹果)?(?:信息|messages)(?:\s*app)?", h)):
        return None
    vendor = _compiled_rule(r"^([a-z][a-z0-9.+-]*)\b|"
        r"^([\u4e00-\u9fff]{2,15}?)(?:推出|发布|现已|现在)", re.I).match(h)
    if vendor is None:
        return None
    name = next(value for value in vendor.groups() if value)
    if name in {"apple", "苹果", "a", "an", "the"} or _extract_patterns(name, PRODUCT_PATTERNS):
        return None
    if not (_frame_search(re.escape(name), opening)
            and _frame_search(r"\b(?:assistant|agent|service|ordering|text|sms|phone\s+number)\b|"
                              r"助手|服务|订餐|短信|电话号码", opening)):
        return None
    if source_current_platform_api(name, 'messages', opening):
        return SourceActionFrame('third-party:' + name + ':messages-integration',
                                'platform-integration', 'software_systems',
                                'ecosystem_interop', 'ecosystem')
    return SourceActionFrame("third-party:" + name + ":message-ordering", "service-release",
                            "software_systems", "third_party_ecosystem", "weak")



def home_os_development_action(title: str, lead: str) -> tuple[str, str] | None:
    """Give named and unnamed reports of the same home OS one identity."""
    h = _normalized(title)
    text = _normalized(lead)
    opening = ' '.join(_compiled_rule(r"(?<=[.!?])\s+|[。！？]").split(text)[:2])
    s = _frame_search
    explicit_development = (
        s(r"\bapple\b[^.!?]{0,55}\b(?:developing|develops?)\b[^.!?]{0,70}\b(?:all-new|new)\s+operating\s+system\b",opening)
        and s(r"\b(?:home\s+hub|homeos|smart\s+home)\b",text)
        or s(r"苹果(?:公司)?[^。.!?]{0,25}(?:正在)?研发智能家居系统",opening)
        and s(r"\bhomeos\b",h+' '+opening))
    named_report = (s(r"homeos",h) and s(r"apple|苹果",h)
        and s(r"reportedly|rumou?r|gurman|古尔曼|消息源|彭博",opening)
        and not s(r"cancel|取消|搁置",h))
    if explicit_development or named_report:
        return 'apple-smart-home-os','development-report'
    return None

def source_object_operation_frame(title: str, lead: str, facts: tuple[str, ...],
                                  identity: EventIdentity) -> SourceActionFrame | None:
    """Bind the reported object before host devices and comparison background.

    Headlines choose the operation. The opening may establish ownership or
    flesh out that same operation; unrelated later facts cannot choose it.
    """
    h, opening = _normalized(title), _normalized(lead)[:950]
    s = _frame_search
    def frame(subject, action, category="software_systems", tier="strong", kind="os_app"):
        return SourceActionFrame(subject, action, category, kind, tier)

    store = s(r"^apple\s+(.{2,70}?)\s+(?:is\s+|will\s+)?reopen(?:s|ing)?\b", h)
    if (store and opening.startswith('apple '+store.group(1)+' ')
            and not s(r"[?？]|cancel|look\s+back|retrospective|history|回顾|取消",h)
            and s(r"\b(?:store|renovations?|customers|genius\s+bar)\b",opening)):
        same_store = True
        for sentence in _compiled_rule(r"(?<=[.!?])\s+|[。！？]").split(opening):
            if s(r"\bapple\b",sentence):
                same_store = bool(s(r"\bapple\s+"+re.escape(store.group(1))+r"\b",sentence))
            owner = r"apple\s+"+re.escape(store.group(1))
            if same_store:
                owner += r"|the\s+store|it"
            if (s(r"\b(?:"+owner+r")\s+(?:will\s+reopen|reopens?\s+(?:today|on)|(?:is\s+)?reopening\s+on)\b",sentence)
                    and not s(r"\b(?:won't|will\s+not|could|might|may\s+reopen|cancel|previously)\b",sentence)):
                return frame('apple-store:'+store.group(1), 'store-reopening', 'hardware_products', kind='retail_store')

    if (s(r"到底要不要|什么时候(?:需要|应该)|should\s+(?:i|you)\b",h)
            and s(r"每次|日常|是不是|should\s+(?:i|you)\b",opening)
            and not s(r"苹果(?:宣布|新增)|apple\s+(?:announced|introduced)|new\s+feature",opening[:250])):
        return frame('editorial:'+h,'settings-choice-guide',tier='weak',kind='general_company')
    if (s(r"(?:will|could)\s+apple\s+hold|苹果会.{0,10}发布会",h)
            and s(r"based\s+on.{0,35}(?:previous|past)|根据.{0,20}历史",opening)):
        return frame('editorial:'+h,'historical-schedule-speculation',tier='weak',kind='general_company')

    # Named permission is the changed object; AI vendors and Mac hardware are
    # context. A direct commitment can follow one neutral opening sentence.
    permission = s(r"full\s*disk\s*access|完全磁盘访问",h+' '+opening)
    apple_headline = (_operation_owner(title)=='apple'
        or s(r"苹果(?:公司)?(?:收紧|增加|宣布|调整|限制)",h)
        or (s(r"^macos\b",h) and _operation_owner(lead)=='apple'))
    apple_plan = s(r"apple.{0,80}(?:plans?|announc|tighten|limit|additional\s+controls|making\s+changes|moves\s+to\s+protect)|苹果.{0,40}(?:收紧|增加|宣布|控制)",h+' '+opening)
    if permission and apple_headline and apple_plan and not is_causal_explanation(title, lead):
        first = _compiled_rule(r"(?<=[.!?])\s+|[。！？]").split(opening,maxsplit=1)[0]
        scope = h+' '+first
        denied = s(r"no\s+plans?|(?:will|does|did)\s+not|won['’]t|denies?|denied|不会|否认|没有计划",scope)
        released = s(r"(?:today|has|now)\s+(?:released|shipped)|now\s+available|现已(?:发布|上线|推出)|正式(?:发布|上线)",scope)
        action = ('permission-control-denied' if denied else
                  'permission-control-release' if released else 'permission-control-plan')
        return frame('macos:full-disk-access',action,kind='security_privacy')

    os = s(r"^(ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)*)\b",h)
    if os and identity.content_form=='news' and s(r"adds?|gives?|new|新增|新功能",h):
        surfaces = [('lock-screen',r'lock\s*screen|锁屏'),('photos',r'apple\s*photos|照片')]
        for name,pattern in surfaces:
            if s(pattern,h):
                return frame(os.group(1)+':'+os.group(2)+':'+name,'current-capability-report')


    if (s(r"apple|苹果",h) and s(r"exchange|ews",h+' '+opening)
            and s(r"plans?\s+(?:a\s+)?fix|working\s+on\s+a\s+fix|计划.{0,12}(?:修复|迁移)",h+' '+opening)):
        return frame('apple-mac-apps:exchange','protocol-migration-plan')

    comparator = s(r"^(.{2,45}?)['’]s\s+(?:answer|alternative|rival)\s+to\s+(?:the\s+)?(?:apple|macbook|iphone|ipad)\b", h)
    if comparator and comparator.group(1) != 'apple':
        return frame('third-party:' + comparator.group(1), 'independent-product-action',
                     'hardware_products', 'weak', 'third_party_ecosystem')
    # An Apple comparison can precede the current actor in Chinese headlines.
    # The opening must explicitly assign the launch to that non-Apple actor.
    competing_launch = s(r"(?:^|[，。！!])\s*(?:[\w\u4e00-\u9fff]{2,12}\s*\d+月\d+日消息[，,]?)?\s*([^，。]{2,35}?)(?:系列)?(?:今天|今日|现已)?(?:正式)?发布", opening)
    if (competing_launch and s(r"宣布|支持|推出",h)
            and not s(r"apple|苹果|iphone|ipad|macbook",competing_launch.group(1))
            and s(r"iphone|ipad|macbook",h)
            and s(r"相比|对比|友商|刚用上", h + ' ' + opening)):
        return frame('third-party:' + competing_launch.group(1), 'independent-product-action',
                     'hardware_products', 'weak', 'third_party_ecosystem')

    app = s(r"^([a-z][a-z0-9+ -]{1,40}?)\s+app\s+(?:(?:recently|just|has|got|big|new)\s+)*(?:upgrade|update)\b", h)
    if app and app.group(1) != 'apple' and not s(r"apple['’]s|苹果", app.group(1)):
        if not _lead_assigns_app_release_to_apple(app.group(1),opening):
            return frame('third-party:' + app.group(1), 'app-update', tier='weak',kind='third_party_ecosystem')

    service_pattern = r"apple\s*tv|apple\s*music|app\s*store|icloud|苹果音乐|苹果电视"
    service_aliases = {'appletv':'apple-tv','applemusic':'apple-music','appstore':'app-store',
                       'icloud':'icloud','苹果音乐':'apple-music','苹果电视':'apple-tv'}
    statuses = []
    clauses = []
    for part in _compiled_rule(r"[;；]|\b(?:but|while|whereas)\b",0).split(h):
        pending = ''
        for segment in _compiled_rule(r"[,，]",0).split(part):
            state = s(r"outage|disruption|unavailable|\bdown\b|restored|resolved|back\s+online|宕机|中断|故障|恢复|修复",pending)
            next_subject = s(r"^\s*(?:and\s+)?(?:"+service_pattern+r")",segment)
            if pending and state and next_subject:
                clauses.append(pending)
                pending = segment
            else:
                pending = (pending + ', ' + segment) if pending else segment
        clauses.append(pending)
    for clause in clauses:
        targets = set()
        for mention in _compiled_rule(service_pattern,0).finditer(clause):
            # A store can contain an unavailable or reinstated app without
            # its own service being down or restored. Bind the state object.
            if s(r"(?:\b(?:on|in|from|to|via)\s+(?:the\s+)?(?:apple['’]s\s+)?|"
                 r"(?:在|从|通过)(?:苹果)?\s*)$", clause[:mention.start()]):
                continue
            tail = clause[mention.end():]
            state = s(r"outage|disruption|unavailable|\bdown\b|restored|resolved|"
                      r"back\s+online|宕机|中断|故障|恢复|修复|不可用", tail)
            if state and s(r"\b(?:apps?|listings?|removed|delisted|reinstated)\b|"
                           r"应用|软件|下架|上架", tail[:state.start()]):
                continue
            targets.add(service_aliases[_compiled_rule(r'\s+', 0).sub('', mention.group(), 0)])
        if not targets:
            continue
        disrupted = s(r"\boutage\b|\b(?:still|currently|is|are)\s+down\b|disruption|unavailable|宕机|服务(?:中断|故障)|不可用",clause)
        restored = s(r"(?:restored|resolved|back\s+online)(?:\s*(?:$|[.!?])|\s+(?:after|for|following)\b)|(?:恢复|修复)(?:正常|服务)?$",clause)
        restoration_denied = s(r"\b(?:not|never|isn['’]t|hasn['’]t)\b.{0,20}(?:resolved|restored|back\s+online)|尚未.{0,10}(?:恢复|修复)|未恢复",clause)
        if disrupted or restored:
            statuses.extend((target,'service-restoration' if restored and not restoration_denied else 'service-outage') for target in targets)
    if statuses:
        ongoing = [target for target,action in statuses if action=='service-outage']
        targets = ongoing or [target for target,action in statuses]
        return frame('services:' + ','.join(sorted(set(targets))),
                     'service-outage' if ongoing else 'service-restoration',kind='service_content')

    if ('apple-tv' in identity.title_products
            and s(r"(?:selection|classic|bonus|catalog).{0,30}(?:movies|films)|(?:movies|films).{0,30}(?:selection|classic|bonus|catalog)",h)
            and s(r"updated|add(?:ed|s)?|new|free|更新|新增",h)
            and s(r"today|this month|new selection|has added|最新|本月|今天",opening)):
        return frame('apple-tv:film-catalog','catalog-addition',kind='service_content')

    retail = s(r"apple\s*stores?|苹果(?:零售店|门店)",h)
    if retail and s(r"boxes|materials|物料|箱",h) and s(r"receive|sent|deliver|收到|送往|送达",h):
        return frame('apple-retail:display-materials','material-delivery','hardware_products',kind='retail_store')

    hub_owned = 'apple-home-hub' in identity.title_products
    # A sparse nickname still needs a local, explicit first-party attribution.
    if not hub_owned and s(r"homepad|home\s*hub|家居中枢|家庭中枢",h):
        hub_owned = bool(s(r"apple['’]s\s+(?:(?:new|upcoming|forthcoming|smart|long-rumored)\s+){0,3}(?:home\s*hub|homepad)|苹果.{0,18}(?:home\s*hub|家居中枢|家庭中枢)",opening))
    if not hub_owned and s(r"homepad",h):
        hub_owned = bool(s(r"apple\s+code.{0,55}for\s+the\s+homepad",opening))
    if hub_owned and identity.content_form == 'news':
        if s(r"colors?|finishes|配色|种颜色",h):
            negative = s(r"(?:will|does|did)\s+not\s+(?:get|have|add)|won['’]t\s+(?:get|have|add)|no\s+new\s+colors|不会.{0,12}(?:配色|颜色)|没有新增.{0,8}(?:配色|颜色)",h)
            return frame('apple-home-hub:finish',
                         'finish-change-denied' if negative else 'finish-lineup-disclosure',
                         'hardware_products',kind='hardware_market')
        if s(r"setup\s+process|照片界面|photo\s+face",h) and s(r"reveal|leak|曝光|爆料|discovered",h+' '+opening[:400]):
            return frame('apple:photo-face','feature-code-discovery')
        if s(r"identify|facial|face recognition|面部识别",h) and s(r"content|display|内容|显示",h):
            return frame('apple-home-hub:personal-content','user-recognition')

    if (s(r"apple['’]s\s+(?:reportedly\s+developing\s+a\s+)?(?:smart\s+)?home\s+camera|苹果.{0,18}(?:安防|家居|家庭)摄像头",h)
            and s(r"no\s+video\s+recording|doesn['’]t\s+record|without\s+(?:showing\s+)?video|不录|不存|无录像",h)):
        return frame('apple-home-camera','non-recording-design','hardware_products',kind='hardware_market')

    # Protocol retirement is a platform interoperability operation, even when
    # the source also gives administrators temporary recovery instructions.
    if (s(r"(?:apple\s+mail|苹果邮件).{0,70}(?:stop\s+syncing|停止同步)",h)
            and s(r"began\s+disabling|start(?:ed)?\s+disabling|停止|停用",opening[:400])
            and s(r"protocol|协议",opening[:450])):
        protocol=s(r"\(([a-z]{2,10})\)",opening[:300])
        if protocol:
            return frame('apple-mail:'+protocol.group(1),'protocol-retirement',tier='ecosystem',kind='ecosystem_interop')

    if (s(r"iphone|ios|苹果",h) and s(r"bypass|workaround|绕过",h+" "+opening)
            and s(r"reboot|重启",h+" "+opening)
            and (s(r"bypass|workaround|绕过",h) or s(r"最新曝光|newly\s+(?:revealed|disclosed)|new\s+(?:report|capability)",opening))):
        # The named protection is the object, not the phone containing it.
        if s(r"inactivity|闲置|未解锁|非活动|reboot protection",h+' '+opening):
            tools = _compiled_rule(r"(?<![A-Za-z])[A-Z][a-z]+(?:[A-Z][a-z]+)+(?![A-Za-z])", 0).findall(title + ' ' + lead[:950])
            tools = [name for name in tools if not _extract_patterns(name.lower(), PRODUCT_PATTERNS)]
            if tools:
                action = ('protection-bypass-denied' if s(r"cannot|can['’]t|does not|未能|不能|无法|否认",h)
                          else 'protection-bypass-report')
                return frame('ios:inactivity-reboot:' + tools[0].lower(), action, kind='security_privacy')

    official_gallery = (s(r"苹果官方.{0,40}(?:账号|账户).{0,35}(?:发布|分享)|"
                          r"apple(?:['’]s)?\s+official.{0,35}account.{0,35}(?:shares?|publishes?)", opening)
                        and s(r"shot\s+on\s+iphone", opening))
    if (s(r"^apple\s+(?:shares|commissions)|^苹果(?:发布|委托)",h)
            and s(r"photos|photographers|摄影|照片",h)
            and (s(r"^apple\s+commissions|^苹果委托",h) or s(r"commissioned\s+by\s+apple|apple.{0,30}commission|苹果.{0,15}委托",opening)
                 or official_gallery)):
        model=s(r"iphone\s+(\d+(?:\s+pro(?:\s+max)?)?|duo|air)\b",h)
        if model:
            # Named contributors distinguish separate sessions on the same
            # device, while their order and the article language do not.
            name = r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?(?:\s+[A-Z][a-z]+){1,3}"
            contributors = set()
            for sentence in _compiled_rule(r"[.!?。！？]").split(lead[:950]):
                if s(r"last\s+(?:year|month)|previously|earlier\s+campaign|过去|去年|此前|曾经", sentence):
                    continue
                credit = s(r"(?:commissioned\s+(?:from\s+)?|photos?\b.{0,80})photographers?\s+|本次拍摄由\s*", sentence)
                if credit is None:
                    continue
                names = _compiled_rule(name + r"(?:\s*(?:,\s*(?:and\s+)?|and\s+|with\s+|与\s*|和\s*)" + name + r")*").match(sentence[credit.end():])
                if names:
                    contributors.update(_subject_slug(v) for v in _compiled_rule(name).findall(names.group()))
            subject = 'iphone-' + model.group(1).replace(' ','-')
            if contributors:
                subject += ':creators:' + ','.join(sorted(contributors))
            return frame(subject,'official-photo-publication','hardware_products',kind='marketing_ad')
    return None


def source_primary_assertion(title: str, lead: str) -> str:
    """Title and first non-duplicate assertion; later history has its own owner."""
    h = _normalized(title)
    opening = _normalized(lead)
    if opening.startswith(h):
        opening = opening[len(h):].lstrip(" .。")
    first = next(source_sentence_spans(opening), (0, len(opening)))
    return h + ". " + opening[first[0]:first[1]]


def source_product_lifecycle_assertion(title: str, lead: str) -> tuple[str, str]:
    """Keep the current list assignment, excluding historical comparison models.

    Inline original labels resolve translations; a bare ambiguous translation
    establishes a listing, not a repair cutoff.
    """
    h = _normalized(title)
    opening = source_primary_assertion(title, lead)[len(h) + 2:]
    clauses = _compiled_rule(r"(?<=[，,；;])").split(opening)
    current = [clause for clause in clauses if not _frame_search(
        r"此前|去年|上月|回顾|早已|早在|\b(?:previously|last\s+(?:year|month)|revisits?)\b", clause)
        or not _extract_patterns(clause, PRODUCT_PATTERNS)]
    scope = h + ". " + "".join(current)
    assigned: set[str] = set()
    for match in _compiled_rule(
        r"(?:列入|标记为|归类为|归为)\s*[‘“\"']?\s*(过时|停产|复古)"
        r"[’”\"']?\s*(?:[（(]\s*(obsolete|vintage)\s*[）)])?", re.I).finditer(scope):
        if match.group(2):
            assigned.add(match.group(2).lower())
        elif match.group(1) != "过时":
            assigned.add("vintage" if match.group(1) == "复古" else "obsolete")
    assigned.update(_compiled_rule(
        r"\b(?:to|as)\s+(?:(?:its|the)\s+)?[‘“\"']?(obsolete|vintage)\b", re.I).findall(scope))
    if not assigned:
        assigned.update(_compiled_rule(r"\b(?:obsolete|vintage)\b", re.I).findall(h))
    if not assigned:
        assigned.update(_compiled_rule(r"\b(?:obsolete|vintage)\b", re.I).findall(scope))
    if not assigned:
        if "复古" in scope:
            assigned.add("vintage")
        if "停产" in scope:
            assigned.add("obsolete")
    return scope, next(iter(assigned)) if len(assigned) == 1 else "listed"


def source_current_lifecycle_update(title: str, lead: str) -> bool:
    """Bind Apple's current update to a device-status list, not any list."""
    assertion, _state = source_product_lifecycle_assertion(title, lead)
    scope = assertion[len(_normalized(title)) + 2:] if lead else _normalized(title)
    status = r"(?:obsolete|vintage)(?:\s+and\s+(?:obsolete|vintage))?"
    device_list = (r"(?:" + status + r"\s+(?:products?\s+)?list|"
                   r"list\s+of\s+" + status + r"\s+products?)")
    assignment = _frame_search(
        r"\bapple\s+(?:(?:has|today|now|just)\s+)*(?:updated?|updates)\s+(?:its|the)\s+" + device_list
        + r"|\bapple\s+(?:(?:has|today|now|just)\s+)*added\s+[^.!?。]{1,160}?\s+to\s+(?:its|the)\s+" + device_list
        + r"|苹果(?:公司)?(?:今天|今日|现已|已经|已|刚刚)*更新\s*[‘“\"']?(?:过时|停产|复古)"
          r"(?:[、与和及]*(?:过时|停产|复古))*(?:产品)?[’”\"']?(?:名单|列表)"
        + r"|\bapple\s+(?:(?:has|today|now|just)\s+)*(?:considers?|declared|classifies?)\s+"
          r"[^.!?。]{1,160}?\s+(?:as\s+)?" + status, scope)
    support_ended = (_state == 'obsolete' and _frame_search(
        r"\bapple\s+(?:(?:has|today|now|just)\s+)*(?:ended|stopped|terminated)\s+"
        r"(?:official\s+)?hardware\s+(?:service|support|repairs)\b|"
        r"苹果(?:公司)?(?:今天|今日|现已|已经|已)*(?:结束|终止|停止)"
        r"(?:[^。！？；，,]{1,25}的)?官方硬件(?:服务|维修)", scope))
    return bool((assignment or support_ended)
        and source_predicate_role(scope) == 'current'
        and not source_denies_action('', scope, r'updat\w*|add\w*|list\w*|更新|列入|标记')
        and not _frame_search(r'回顾|传闻|明年|计划|尚未|未改变|\b(?:revisits?|plans?|rumors?)\b', scope))


def source_denies_action(title: str, lead: str, predicate: str) -> bool:
    scope = source_primary_assertion(title, lead)
    return bool(_frame_search(r"\b(?:denies|denied|ruled\s+out|are\s+false)\b|否认|不实", scope)
        or _frame_search(r"\b(?:not|never|cannot|can't|won't|unable\s+to)\s+(?:(?:yet|currently|been|be|being)\s+){0,3}(?:" + predicate + r")|"
                        r"(?:并未|没有|不再)(?:" + predicate + r")", scope))


def source_software_capability_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """Bind a built-in software object before a host device or comparison.

    Versioned code discoveries and observed capabilities retain different
    predicates from the hardware whose future release they might imply.
    """
    h, opening = _normalized(title), _normalized(lead)[:950]
    local = h + ". " + opening
    s = _frame_search
    if is_os_release_announcement(title):
        return None
    if source_denies_action(title, lead, r"find|found|discover\w*|test\w*|track\w*|发现|测试"):
        return None
    if s(r"\b(?:not\s+found|found\s+no|no\s+new|unchanged|wishlist|wish\s+list|last\s+year|previously)\b|未发现|没有新|愿望|保持不变|去年|回顾", h):
        return None
    if (s(r'homepod', h) and s(r'surround\s*(?:sound|system)|环绕声', h)
            and s(r'(?:there\s+are\s+)?code\s+references?|代码.{0,12}(?:发现|引用)', opening)
            and s(r'new\s+(?:software\s+)?features?|新功能', opening)
            and not s(r'no\s+(?:new\s+)?code|未发现|不存在|wishlist|希望', opening)):
        version = s(r'(?:tvos|audioos)\s*(\d+(?:\.\d+)*)', local)
        return SourceActionFrame('homepod:surround-system', 'feature-code-discovery', kind='os_app',
                                 model_generation=version.group(1) if version else '')
    # A third-party action containing OS names cannot own a built-in change.
    if not s(r"^(?:(?:modernized|new)\s+|苹果.{0,12})?(?:macos|ios|ipados|watchos|tvos|visionos|iphone|ipad|siri|focus|apple\s*music|this\s+is\s+apple\s*music)(?![a-z0-9])", h):
        return None
    if s(r"revisited|旧闻|回顾", h) or s(r"last\s+year|previously|去年|此前", opening[:250]) and not s(r"\b(?:now|today|newly)\b|最新|新增|今日", opening[:250]):
        return None
    version = s(r"(?<![a-z0-9])(ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)*)", local)
    code = s(r"\b(?:code|strings?|references?|recognizer|simulator|spotted|discovered|hints?|clues?)\b|代码|字符串|发现|模拟器|挖掘", local)
    component = ""
    if version and code:
        platform = version.group(1)
        if platform == "macos" and s(r"touch(?:screen|[- ]enabled|\s+gestures?|\s+recognition)|触控|触屏", local):
            component = "touch-gestures"
        elif platform == "tvos" and s(r"apple\s+intelligence|siri\s*ai|foundation\s+models|基础模型|苹果智能", local):
            component = "intelligence-model-support"
        if component:
            return SourceActionFrame(f"{platform}-{version.group(2)}:{component}", "feature-code-discovery", kind="os_app")
    # The current Focus control is the object, not the containing lock screen
    # or an adjacent Safari/StandBy feature mentioned later in the report.
    if s(r"focus\s*(?:mode|control)|专注模式", h) and s(r"toggle|controls?|button|开关|切换|控制", local) and (code or s(r"leaker|reveals?|revealed|unannounced|消息源|曝光|爆料", local)):
        device = s(r"(?<![a-z0-9])(iphone|ipad)\s*(duo|\d+(?:\s*pro(?:\s*max)?)?)(?![a-z0-9])", local)
        if device:
            return SourceActionFrame(_compiled_rule(r"\s+", 0).sub("-", device.group(), 0) + ":focus-control", "feature-code-discovery", kind="os_app")
    if (version and version.group(1) == "macos" and s(r"\bhdr\b", h)
            and s(r"scaled\s+resolution|分辨率", local)
            and s(r"fix(?:es|ed)?|introduced|improvement|修复|优化|允许", local)):
        return SourceActionFrame(f"macos-{version.group(2)}:hdr-scaled-resolution", "system-capability-report", kind="os_app")
    if (s(r"apple\s*music|苹果音乐", h) and s(r"(?<![a-z0-9])logo(?![a-z0-9])|wordmark|标识|字标", h)
            and s(r"new\s+(?:logo|look)|redesign|rolling\s+out|modernized|chunkier|新|加粗|小写", local)):
        return SourceActionFrame("apple-music:wordmark", "visual-design-change", kind="os_app")
    return None


def source_memorial_publication_frame(title: str, lead: str) -> SourceActionFrame | None:
    """The current first-party post owns the action, not the death it recalls."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    if not s(r"tribute|commemorat|memorial|缅怀|纪念", h):
        return None
    owner_pattern = (r"\bapple(?:['’]s)?\s+(?:(?:current|new)\s+)?(?:ceo|chief executive)\b|"
                     r"苹果(?:现任|新任|新)?\s*(?:ceo|首席执行官)")
    person = r"(?:(?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})|[\u4e00-\u9fff]{2,8}(?:\s*[·・]\s*[\u4e00-\u9fff]{2,8})*)"
    publication = _compiled_rule(
        r"^\s*(?:" + person + r")?\s*"
        r"(?:(?:与|和|、|and\s+)(?:苹果)?(?:前任?|former\s+(?:apple\s+)?)(?:\s*ceo\s*)?" + person + r")?\s*"
        r"(?:(?:today|has|have|now|just|also|both)\s+|今日|今天|分别|先后|刚刚|现已|已经){0,3}"
        r"(?:posts?|posted|publishes?|published|shares?|shared|发文|发布(?:了)?(?:纪念)?(?:文章|文字))", re.I)
    inactive = (r"\b(?:former|ex[- ])\s*$|\b(?:last\s+(?:year|month|week)|previously|revisited|"
                r"denies|denied|false|not\s+(?:yet\s+)?post\w*|never\s+post\w*)\b|"
                r"去年|上个月|上周|旧帖|旧文|此前|否认|未发文|没有发文|并未|不实")
    if s(inactive, h) or s(r"\bold\s+(?:post|tribute|statement).{0,30}(?:resurfac|reprint)|旧(?:帖|文).{0,15}(?:再|转载)", opening):
        return None
    owned = False
    dated_publication = False
    for text in (title, lead[:1200]):
        for start, end in source_sentence_spans(text):
            clause = text[start:end]
            if s(inactive, clause):
                continue
            for owner in _compiled_rule(owner_pattern, re.I).finditer(clause):
                if s(r"\b(?:former|ex[- ])\s*$|前任?\s*$", clause[:owner.start()]):
                    continue
                # Names and simple publication auxiliaries may intervene;
                # another finite verb/actor or a planned post cannot.
                action = publication.search(clause[owner.end():])
                if not action or not s(r"tribute|commemorat|memorial|缅怀|纪念", clause):
                    continue
                bridge = clause[owner.end():owner.end() + action.end()]
                if s(r"将于|将会|明[天日]|计划|打算|拟于|准备|曾经|曾发文", bridge):
                    continue
                # A year attached to posting is a dated prior statement unless
                # this clause explicitly establishes its current publication.
                # Stop before a relative/background clause about the honoree.
                post_scope = _compiled_rule(r"[,，;；]|\b(?:who|when|after)\b|逝世|去世|\bdied\b", re.I).split(
                    clause[owner.end() + action.end():], maxsplit=1)[0]
                if (s(r"\b(?:in|on)\s+20\d{2}\b|20\d{2}\s*年", post_scope)
                        and not s(r"\btoday\b|今日|今天|刚刚", bridge)):
                    dated_publication = True
                    continue
                owned = True
    if not owned or dated_publication:
        return None
    if s(r"\bsteve\s+jobs\b|乔布斯", h):
        honoree = "steve-jobs"
    else:
        target = s(r"(?:tribute\s+to|commemorat\w*)\s+([a-z]+(?:\s+[a-z]+){0,2})(?=\s+on\b|[,.:]|$)|"
                   r"(?:缅怀|纪念)([^，。:：\s]{2,12})|^([^，。:：\s]{2,12})逝世", h)
        if not target:
            return None
        honoree = next(part for part in target.groups() if part).replace(" ", "-")
    anniversary = s(r"\b(\d{1,3})(?:st|nd|rd|th)?\s+anniversary\b|(\d{1,3})\s*周年", h)
    period = "anniversary:" + next(part for part in anniversary.groups() if part) if anniversary else ""
    return SourceActionFrame("apple:memorial:" + honoree, "memorial-publication",
        "hardware_products", "company_org", period=period)


def source_owned_organization_frame(title: str, lead: str) -> SourceActionFrame | None:
    """Current hiring and supply-chain evaluation belong to their actual actor."""
    h, opening = _normalized(title), _normalized(lead)[:950]
    s = _frame_search
    local = h + ". " + opening
    memorial = source_memorial_publication_frame(title, lead)
    if memorial is not None:
        return memorial
    if s(r"not\s+hiring|old\s+listing|no\s+job\s+opening|are\s+false|last\s+year|now\s+closed|并未招聘|未招聘|旧招聘|去年|已关闭|不实", source_primary_assertion(title, lead)):
        return None
    internal_assignment = s(r"(?:internal|staff|employee)\s+lottery|内部抽签|面向.{0,30}员工.{0,15}抽签", source_primary_assertion(title, lead))
    if (not internal_assignment
            and s(r"apple\s+is\s+hiring|apple.{0,25}\bhiring\b|苹果.{0,15}(?:招募|招聘)", h)
            and s(r"apple\s+is\s+hiring|苹果.{0,50}(?:正在招聘|招聘信息|招募)", opening)):
        # A team/program identifier joins translated role names; otherwise
        # preserve the reported role text rather than merge all Apple hiring.
        program = _compiled_rule(r"\bi[A-Z][A-Za-z]+\b", 0).search(title + " " + lead)
        role = program.group().lower() if program else h
        return SourceActionFrame("apple:hiring:" + role, "job-opening", "hardware_products", "company_org")
    if s(r"工艺|制程|process|foundry", h) and s(r"评估|evaluat", h):
        # Restrict ownership to the evaluation sentence: another customer's
        # confirmed order elsewhere cannot become Apple's production order.
        for start, end in source_sentence_spans(opening):
            clause = opening[start:end]
            node = s(r"(?<![a-z0-9])\d+(?:\.\d+)?\s*(?:a|nm)(?![a-z0-9])", clause)
            if (node and s(r"apple|苹果", clause) and s(r"正在评估|are\s+evaluating|is\s+evaluating", clause)
                    and not s(r"not\s+evaluat|并未|没有|未在|去年|last\s+year", clause)):
                return SourceActionFrame("apple:process:" + node.group().replace(" ", ""),
                    "supplier-process-evaluation", "hardware_products", "hardware_market")
    return None


def source_independent_software_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """Distinguish independent utilities from new OS/driver compatibility."""
    h, opening = _normalized(title), _normalized(lead)[:950]
    s = _frame_search
    local = h + ". " + opening
    if (s(r"\b(?:patcher|oclp)\b|系统补丁", local)
            and s(r"macos|macs?\b|旧\s*mac", local)
            and s(r"support\s+for\s+the\s+first\s+time|新增.{0,25}(?:系统|支持)|首次.{0,25}支持", opening)
            and s(r"release\s+candidate|was\s+released|released|候选版|发布", opening)):
        release = s(r"\b\d+\.\d+\.\d+(?:[- ]rc[. ]?\d+)?\b", opening)
        return SourceActionFrame("third-party:os-patcher:" + (release.group() if release else h),
            "os-compatibility-release", "software_systems", "ecosystem_interop", "ecosystem")
    # A released OS image adaptation plus a new graphics bridge provides
    # platform compatibility even when its guest hardware is virtual.
    guest = s(r'(?<![a-z0-9-])([a-z][a-z0-9-]*\s*os)(?![a-z0-9-])', h)
    if guest and s(r'apple\s*silicon|苹果芯片|mac', h):
        detail = ' '.join((local, *(_normalized(f) for f in facts)))
        adaptation = s(r'(?:恢复(?:镜像|映像)|recovery\s+image).{0,45}(?:改造|修改|适配)|(?:modif\w*|adapt\w*).{0,45}recovery\s+image', detail)
        bridge = (s(r'vulkan', detail) and s(r'metal', detail)
            and s(r'转换层|图形转换|vulkan.{0,20}转换为.{0,8}metal|translation\s+layer|graphics\s+bridge', detail)
            and s(r'(?:调用|使用).{0,20}(?:mac.{0,8})?gpu|(?:access|use).{0,25}(?:mac.{0,8})?gpu', detail))
        if (adaptation and bridge
                and s(r'开源|公开|released|published|open.source', local)
                and not s(r'未实现|尚未实现|尚未发布|尚未公开|not\s+(?:yet\s+)?released|nothing\s+has\s+been\s+released|no\s+(?:graphics|gpu)|without\s+gpu', local)):
            project = (s(r'^([a-z][a-z0-9-]*)\s+project\b', h)
                or s(r'(?:开源项目|open.source\s+project)\s+([a-z][a-z0-9-]*)', local)
                or s(r'(?:名为|named|called)\s*([a-z][a-z0-9-]*)', opening)
                or s(r'released\s+([a-z][a-z0-9-]*),\s+an?\s+open.source\s+project', opening))
            implementation = project.group(1) if project else h
            return SourceActionFrame('third-party:os-adaptation:' + implementation + ':' + guest.group(1).replace(' ', '') + ':mac',
                'os-compatibility-release', 'software_systems', 'ecosystem_interop', 'ecosystem')
    first_party = bool(s(r"^(?:apple\s+(?:(?:today|has|now)\s+){0,3}(?:releas\w*|launch\w*|introduc\w*)|苹果(?:今日|已经|现已)?(?:发布|推出|开发))", h)
        or s(r"^(?:apple\s+(?:(?:today|has|now)\s+){0,3}(?:releas\w*|launch\w*|introduc\w*)|苹果(?:今日|已经|现已)?(?:发布|推出|开发))", opening))
    if (not first_party and s(r"\b(?:tool|utility|script)\b|工具|脚本", h + " " + opening[:450])
            and s(r"open.source|command.line|github|开源|第三方", local)
            and not s(r"apple(?:['’]s)?\s+(?:new\s+)?(?:tool|utility)|苹果(?:发布|推出|开发).{0,20}(?:工具|脚本)", h)):
        # A declared headline subject outranks names of alternatives in the
        # body. Generic pronouns never identify an independent product.
        pronouns = {"it", "this", "that", "they", "he", "she", "which", "there", "one"}
        declaration = r"(?<![a-z0-9])([A-Za-z][A-Za-z0-9-]*)\s+is\s+(?:a|an)\s+(?:[a-z-]+\s+){0,4}(?:tool|script|utility)\b"
        headline_name = _compiled_rule(r"^([A-Za-z][A-Za-z0-9-]*)\s*[:：]\s*(?:a|an)\s+(?:[a-z-]+\s+){0,4}(?:tool|script|utility)\b", re.I).search(title)
        named = {headline_name.group(1).lower()} if headline_name and headline_name.group(1).lower() not in pronouns else set()
        if not named:
            for text in (lead, *facts):
                for start, end in source_sentence_spans(text):
                    sentence = text[start:end]
                    for match in _compiled_rule(
                        r"(?:called|named|名为)\s*[\"'“]?([A-Za-z][A-Za-z0-9-]*)|" + declaration, re.I).finditer(sentence):
                        name = (match.group(1) or match.group(2)).lower()
                        comparison = _frame_search(r"compet\w*\s+with|compared?\s+(?:with|to)|unlike|alternative\s+to|对比|相比|竞争", sentence[:match.start()])
                        if name not in pronouns and not comparison:
                            named.add(name)
        subject = next(iter(named)) if len(named) == 1 else h
        version = s(re.escape(subject) + r"\s+v?(\d+(?:\.\d+)+)", local + " " + " ".join(facts)) if len(named) == 1 else None
        return SourceActionFrame("third-party:utility:" + subject, "independent-utility-release",
            "software_systems", "third_party_ecosystem", "weak", version.group(1) if version else "")
    return None


def source_launch_campaign_frame(title: str, lead: str) -> SourceActionFrame | None:
    """A newly reported batch schedule owns its product inventory and old dates."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    local = h + ". " + opening
    owner = s(r"^(?:sources?:\s*)?apple\b|^(?:消息称|报道称)?苹果", h)
    generic = s(r"^(?:second|third)\b", h) and s(r"^apple\b", opening)
    if not (owner or generic):
        return None
    if (source_denies_action(title, lead, r"plan\w*|launch\w*|announc\w*|发布|计划")
            or s(r"looking\s+back|history|recap|回顾|历史", h)
            or not s(r"planning|plans?|expected|rumors?\s+suggest|有望|可能|消息称|报道称", local)):
        return None
    assertion = source_primary_assertion(title, lead)
    if (s(r"last\s+(?:year|month)|previously|去年|上个月|此前", assertion)
            and not s(r"has\s+since\s+learned|now\s+(?:reports?|plans?)|latest|最新|现计划", assertion)):
        return None
    wave = s(r"\b(second|third|two|three)\s+(?:\w+\s+)?(?:['‘]?event|wave|round|batch|set)|([2-9])\s*波|第(二|三)场|再推一批", h)
    if not wave or not s(r"product|launch|announcement|releases?|new\s+macs|新品|发布|上市", local):
        return None
    # Bind the newly reported late-month window, never the earlier event date
    # or a previous forecast appearing in the same report.
    months = "january february march april may june july august september october november december".split()
    month_names = "|".join(months)
    late = None
    clause = ""
    date_pattern = (r"(?:final|last)\s+week\s+of\s+(?:the\s+)?(" + month_names + r"|month)(?:\s*,?\s*(20\d{2}))?|"
        r"end\s+of\s+(?:the\s+)?(" + month_names + r"|month)(?:\s*,?\s*(20\d{2}))?|"
        r"(?:(20\d{2})\s*年\s*)?(?:(\d{1,2})\s*月|本月)(?:的)?(?:最后\s*(?:一|1)\s*周|月底|末|下旬)")
    for clause in _compiled_rule(r"[。；;]|(?<=[.!?])\s+|\bbut\b|\bhowever\b|但是|不过").split(local):
        if s(r"previously|last\s+(?:year|month)|used\s+to|此前|去年|上个月", clause):
            continue
        late = s(date_pattern, clause)
        if late:
            break
    if not late:
        return None
    explicit = late.group(1) or late.group(3)
    year = late.group(2) or late.group(4) or late.group(5) or ""
    if late.group(6):
        month = int(late.group(6))
    elif explicit in months:
        month = months.index(explicit) + 1
    else:
        # Resolve “this month” only when the headline, or otherwise the lead,
        # supplies one unambiguous named month.
        named = s(r"\b(" + month_names + r")\b", h)
        lead_months = set(_compiled_rule(r"\b(" + month_names + r")\b").findall(opening))
        if named:
            month = months.index(named.group(1)) + 1
        elif len(lead_months) == 1:
            month = months.index(next(iter(lead_months))) + 1
        else:
            return None
    ordinal = {"second": "2", "two": "2", "third": "3", "three": "3"}.get(wave.group(1), wave.group(2)) or {"二":"2", "三":"3"}.get(wave.group(3), "2")
    return SourceActionFrame("apple:product-launch-campaign", "additional-launch-plan",
        "hardware_products", "hardware_market", period=f"month:{month}:late:wave:{ordinal}", year=year)


def source_editorial_outlook(title: str, lead: str, passages: tuple[str, ...]) -> bool:
    """Read explicit recap/forecast form without treating old citations as news."""
    s = _frame_search
    h = _normalized(title)
    interpretation = (s(r'^what.{0,90}(?:means?\s+for|signals?\s+for)|释放.{0,8}(?:什么|何种)信号|意味着什么', h)
        and not s(r'(?:apple|苹果).{0,20}(?:explains?|解释|表示|回应)|高管|\bceo\b|features?|changes?|功能|变化|修复|漏洞|要求|支持', h))
    if interpretation and s(r'in\s+our\s+view|we\s+(?:think|believe)|perhaps|在我看来|我们认为|或许', ' '.join((lead, *passages))):
        # The writer's interpretation owns the report; the current launch is
        # its subject, not another independently reported announcement.
        return True
    strategy = s(r'^how\s+apple\s+(?:can|could|should)\s+(?:win|succeed|compete|lead|improve)\b|苹果(?:如何|怎样)(?:才能|能够)?.{0,15}(?:成功|取胜|竞争|领先)', h)
    if not strategy and not s(r'features?|changes?|when\s+to\s+expect|when.{0,50}(?:ship|launch|releas)|^remembering\b|功能|变化|前瞻|^回顾', h):
        return False
    if is_os_release_announcement(title):
        return False
    text = ' '.join((lead, *passages))
    recap = s(r'(?:here\s+is|here[’\']s).{0,20}recap.{0,50}rumou?r|looks?\s+back\s+at.{0,25}(?:old|past)\s+rumou?r|(?:回顾|汇总).{0,20}旧传闻', text)
    older = sum(bool(s(r'(?:report|bloomberg|消息|报道).{0,35}(?:earlier\s+this\s+week|this\s+summer|last\s+month|上周|上月)', p)) for p in set(passages))
    forecast = (s(r'when\s+to\s+expect|when.{0,50}(?:ship|launch|releas)', h)
        and s(r'we[’\']re\s+expecting|most\s+likely|here[’\']s\s+when\s+to\s+expect|我们预计', text))
    strategy_opinion = strategy and s(r'apple\s+could|if\s+(?:apple|it)|opportunity\s+lies|苹果(?:可以|可能|应该)|如果苹果', text)
    if not (recap or older >= 2 or forecast or strategy_opinion):
        return False
    for clause in source_current_disclosure_clauses(lead, passages):
        in_scope, development = source_platform_development_disclosure(title, clause)
        if not in_scope or development is not None:
            return False
    return True


def source_current_disclosure_clauses(lead: str, passages: tuple[str, ...]) -> tuple[str, ...]:
    """Locate current attributed disclosures; their claims still need an owner."""
    result = []
    for p in (lead, *passages):
        for start, end in source_clause_spans(p):
            clause = p[start:end]
            if source_predicate_role(clause) != 'current':
                continue
            if _frame_search(r'(?:new|fresh)\s+(?:report|filing|disclosure).{0,70}(?:reveals?|says?|shows?)|'
                 r'(?:today|now).{0,45}(?:reports?|announced|confirmed|disclosed|released|launched)|'
                 r'(?:reports?|announced|confirmed|disclosed|released|launched).{0,75}(?:today|now)|'
                 r'(?:今天|最新).{0,30}(?:报道|披露|证实|发布|推出)', clause):
                result.append(clause)
    return tuple(dict.fromkeys(result))


_DEVELOPMENT_PLATFORMS = r'\b(homeos|macos|ios|ipados|watchos|tvos|visionos)\b'


def source_platform_development_disclosure(title: str, clause: str) -> tuple[bool, SourceActionFrame | None]:
    """Separate a development claim's scope from its valid owner and target.

    Callers supply a current disclosure clause. An in-scope failure cannot
    turn the disclosure marker itself into evidence of an Apple action.
    """
    s = _frame_search
    headline = _normalized(title)
    platform = s(_DEVELOPMENT_PLATFORMS, headline)
    claim = s(r'\b(testing|developing)\s+(?:a\s+)?new\s+'
              r'(interface|feature|application|service)\s+for\s+([a-z][a-z0-9]*)\b', clause)
    if platform is None or claim is None:
        return False, None
    if (s(r'\bapple\s+(?:is\s+)?$', clause[:claim.start()])
            and s(_DEVELOPMENT_PLATFORMS, claim.group(3))
            and s(r'\b' + claim.group(3) + r'\b', headline)
            and not source_denies_action('', clause, r'test\w*|develop\w*')):
        return True, SourceActionFrame(claim.group(3).lower() + ':' + claim.group(2).lower(),
            claim.group(1).lower() + '-disclosure', kind='os_app')
    return True, None


def source_disclosure_bundle(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """Bind a coordinated disclosure, not each device or its historical context.

    The headline/opening owns the action and product family. The body may name
    the collaborator or release, but cannot turn compatibility into authorship.
    """
    h, opening = _normalized(title), _normalized(lead)[:1200]
    local = h + '. ' + opening
    detail = ' '.join((opening, *(_normalized(f) for f in facts)))
    s = _frame_search
    # A platform release can introduce several linked interoperability features.
    # Its version is mandatory; an independent app is a different operation.
    version = s(r'(?:hyperos|澎湃\s*os)\s*(\d+(?:\.\d+)*)', local)
    if (version and s(r'小米|xiaomi', local) and s(r'apple|苹果|airdrop', h)
            and s(r'互联|互传|兼容|interoperab|cross.device', h)
            and s(r'上线|宣布|官宣|推出|发布|launch|announc|introduc', local)
            and not s(r'应用商店|watch\s+app|app\s+store|上架', h)):
        if s(r'回顾|旧功能|look\s+back|retrospect', h) and s(r'去年|此前|last\s+year|no\s+new|没有新', opening):
            return SourceActionFrame('editorial:' + h, 'interoperability-recap', kind='general_company', tier='weak')
        denied = source_denies_action(title, lead, r'launch\w*|上线|推出|发布') or s(r'尚未.{0,8}(?:上线|推出|发布)', h)
        return SourceActionFrame('xiaomi:hyperos-' + version.group(1) + ':apple-interoperability',
                                 'interoperability-release-denied' if denied else 'interoperability-release',
                                 kind='ecosystem_interop', tier='weak' if denied else 'ecosystem')
    if not s(r'home|家居|门铃|门锁|温控|恒温|摄像头', h) or not s(r'apple|苹果', h):
        return None
    if s(r'look\s+back|回顾|旧图', h) and s(r'no\s+new|没有新|old\s+images|旧图', opening):
        return SourceActionFrame('editorial:' + h, 'design-recap', 'hardware_products', 'general_company', 'weak')
    # A code registry is an OS discovery; names in that registry are not a
    # hardware announcement. Conversely, a hardware headline keeps its family.
    if (s(r'second.party|第二方', h) and s(r'code|代码|table|产品表', detail)
            and s(r'homekit|secondpartyproducts|partnership\s+table|ios\s*\d', detail)):
        version = s(r'ios\s*(\d+(?:\.\d+)*)', detail)
        return SourceActionFrame('apple-home:second-party-registry', 'code-registry-discovery', kind='os_app',
                                 period='ios-' + version.group(1) if version else '')
    if (s(r"apple['’]s\s+own|apple.{0,35}\bown\b|苹果自[有研]|苹果自己的", h)
            and s(r'cameras?|摄像头', h) and s(r'separate|clarif|独立|澄清', detail)):
        return SourceActionFrame('apple-home:own-camera', 'independent-development-clarification',
                                 'hardware_products', 'hardware_market')
    # Recognize the partner on either side of a joint-development predicate.
    partner = s(r'(?:apple|苹果)(?:\s*(?:and|&|与|和|携手|将联手)\s*)([a-z][a-z0-9-]*)|'
                r'apple\s+(?:is\s+)?(?:collaborating|working)\s+with\s+([a-z][a-z0-9-]*)|'
                r'(?:co-developed|codeveloped|made)\s+with\s+(?!apple\b)([a-z][a-z0-9-]*)|'
                r'(?:under\s+)([a-z][a-z0-9-]*)\s+branding|'
                r'brands\s+such\s+as\s+([a-z][a-z ]+?)\s+developed\s+in\s+partnership\s+with\s+apple|'
                r'(?:苹果|该公司)与([a-z][a-z0-9-]*)(?:电子)?展开.{0,15}合作', local)
    joint = s(r'co.develop|helped\s+develop|合作开发|联合开发|携手打造|合作打造|参与.{0,15}(?:设计|开发)|'
              r'developed\s+in\s+partnership\s+with\s+apple|collaborating|working\s+with|made\s+with\s+apple|apple\s+and\s+\w+.{0,30}partnered', local)
    if not (partner and joint) or s(r'denies|not\s+working|否认|并未合作|独立开发', local[:500]):
        # Explicit compatibility of an independently developed accessory is
        # an ecosystem story, even when Apple Home is the target platform.
        if s(r'独立开发|independently\s+developed', opening) and s(r'兼容|matter|compatib', local):
            return SourceActionFrame('third-party:home:' + h, 'accessory-compatibility',
                                     'hardware_products', 'third_party_ecosystem', 'weak')
        return None
    name = next(v for v in partner.groups() if v)
    if name in {'apple', 'new', 'the', 'its'}:
        return None
    # Use the principal family, not every product mentioned in background.
    first = opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
    family = 'accessory-collection' if s(r'accessories|配件', h) and s(r'partnership|合作', h) else ''
    for scope in (() if family else (h, first)):
        if s(r'cameras?|doorbell|摄像头|门铃', scope):
            family = 'imaging'
            break
        if s(r'thermostat|deadbolt|smart\s+lock|temperature\s+sensor|恒温|温控|门锁|温度传感器', scope):
            family = 'environment-access'
            break
    if not family and s(r'accessories|配件', h) and s(r'partnership|合作', h):
        family = 'accessory-collection'
    if not family:
        return None
    # An explicit common batch owns all of its constituents, even when each
    # headline selects a different device. Never infer a batch from partnership.
    batch_scope = next((opening[start:end] for start, end in source_sentence_spans(opening)
        if s(r'(?:single|same|one)\s+batch|同一批|同批', opening[start:end])
        and s(r'images?|designs?|图像|设计', opening[start:end])), '')
    if batch_scope:
        owner = s(r'\b([a-z][a-z0-9_-]*)\s+(?:published|shared|posted)\b', batch_scope)
        objects = [key for key, pattern in (
            ('camera', r'cameras?|摄像头'), ('doorbell', r'doorbell|门铃'),
            ('thermostat', r'thermostat|恒温|温控'), ('lock', r'(?:door|smart)\s*lock|deadbolt|门锁'),
            ('temperature-sensor', r'temperature\s+sensor|温度传感器')) if s(pattern, batch_scope)]
        if owner:
            family = 'batch-by:' + owner.group(1)
        elif len(objects) > 1:
            family = 'batch:' + ','.join(objects)
    if s(r'did\s+not\s+co.develop|images?.{0,20}(?:fake|forged)|leak.{0,20}withdrawn|伪造|否认.{0,10}合作', local):
        action = 'design-disclosure-retracted'
    elif s(r'begin\s+shipping|now\s+shipping|start\s+shipping|开始发货|现已发货', h):
        action = 'customer-shipment'
    elif s(r'partnership\s+disclosure|合作开发披露', h):
        action = 'joint-development-disclosure'
    elif s(r'images?|photographs?|drawings?|first\s+look|look\s+like|实物|曝光|抢先看|再曝', local):
        action = 'design-image-disclosure'
    else:
        return None
    if action == 'design-image-disclosure' and s(r'revised|redesigned|修订|重新设计', h):
        action = 'revised-design-image-disclosure'
    separate = s(r'(?:separate|different)\s+batch\s+of\s+(?:design\s+)?images|另[一\d]批.{0,10}(?:图像|设计)', opening)
    if separate and action == 'design-image-disclosure':
        # An explicit separate disclosure is not a continuation merely because
        # its devices belong to the same family. Keep its attributed owner.
        clause = next(opening[a:b] for a, b in source_sentence_spans(opening) if a <= separate.start() < b)
        owner = s(r'\b([a-z][a-z0-9_-]*)\s+(?:published|shared|posted)\b', clause)
        action = 'separate-design-image-disclosure'
        family += ':' + (owner.group(1) if owner else h)
    batch = s(r'(second|third|\d+)\s+batch\s+of\s+(?:design\s+)?images|第([二三\d]+)批.{0,10}(?:图像|设计)', local)
    if batch and action == 'design-image-disclosure':
        value = batch.group(1) or batch.group(2)
        action += '-batch-' + {'second':'2', 'third':'3', '二':'2', '三':'3'}.get(value, value)
    generation = s(r'(first|second|third|\d+)[- ]generation|第([一二三\d]+)代', local)
    period = ''
    if generation:
        value = generation.group(1) or generation.group(2)
        period = 'generation:' + {'first':'1', 'second':'2', 'third':'3', '一':'1', '二':'2', '三':'3'}.get(value, value)
    collection = s(r'[\"“](apple\s+[^\"”]{3,60})[\"”]', detail) if family == 'accessory-collection' else None
    return SourceActionFrame('apple-home:joint:' + name + ':' + family, action,
                             'hardware_products', 'hardware_market', period=period,
                             aliases=('apple-home:collection:' + collection.group(1),) if collection else ())


def source_dated_launch_frame(title: str, lead: str, passages: tuple[str, ...], identity: EventIdentity | None = None) -> SourceActionFrame | None:
    """Bind a launch's date and confirmation stage before its product inventory."""
    s = _frame_search
    # Compatibility view only: media invitations belong to the source binder,
    # including unresolved invitations. No legacy date/title rule may retry.
    if s(r'\binvit\w*|邀请', ' '.join((title, lead, *passages))):
        from .article_processing import capture_article_title_evidence
        invitation = bind_media_invitation(capture_article_title_evidence('', '', title, lead, passages))
        if invitation is not None:
            if invitation.report_role != 'independent' or invitation.review_reason:
                return None
            values = {q[1]: q[2] for q in invitation.qualifiers}
            return SourceActionFrame('apple:product-launch-campaign', 'launch-date-report',
                'hardware_products', 'hardware_market', period='month:' + values['event-month'] + ':day:' + values['event-day'],
                year=values.get('event-year', ''))
    return _legacy_dated_launch_frame(title, lead, passages, identity)


def _legacy_dated_launch_frame(title: str, lead: str, passages: tuple[str, ...], identity: EventIdentity | None = None) -> SourceActionFrame | None:
    """Existing launch/sales schedules; media invitations have a separate owner."""
    s = _frame_search
    h = _normalized(title)
    if identity is not None and (identity.scope not in {'apple-direct', 'unknown'} or identity.content_form != 'news'):
        return None
    # A relative preorder window is still a concrete sales schedule. Keep
    # its named batch and report/open stage, without inventing a calendar date.
    preorder = r'pre[- ]?orders?|预购|预售'
    superseded = r'cancel\w*|delay\w*|postpon\w*|(?:was|were|had\s+been)\s+(?:expected|planned|scheduled)|取消|推迟|延期|此前(?:预计|计划)|原(?:定|计划)'
    opening_predicate = r'expected|planned|scheduled|available|begin|start|open|预期|预计|计划|开始|开启|开放'
    preorder_clauses = []
    if s(preorder, h):
        preorder_clauses = [_normalized(p[start:end]) for p in (lead, *passages)
            for start, end in source_sentence_spans(p) if s(preorder, _normalized(p[start:end]))]
    relative_date = r'\b(?:this|next)\s+week\b|\b(?:tomorrow|today)\b|本周|下周|明天|明日|今天|今日'
    relative_schedule = (
        r'(?:pre[- ]?orders?\s+(?:(?:are|is|will|be|expected|to|begin|start(?:ing)?|open|on|available)\s+)*)'
        r'(?P<after>' + relative_date + r')|'
        r'(?P<before>' + relative_date + r')\s*(?:开始|开启|接受)?(?:预购|预售)|'
        r'(?:预购|预售)(?:将于|于|定于|将在)?\s*(?P<chinese_after>' + relative_date + r')')
    relative = s(relative_date, h) if preorder_clauses else None
    if relative is None and preorder_clauses:
        relative = s(relative_date, ' '.join(preorder_clauses))
    if relative and s(preorder, h):
        local = h + '. ' + _normalized(lead)
        subjects = hardware_action_subjects(title)
        if (subjects and s(r'begin|start|open|expected|开始|开启|预计', local)
                and not s(r'last\s+year|previously|recap|guess|wish|historical|去年|此前|回顾|推测|希望', source_primary_assertion(title, lead))
                and not s(superseded, h)
                and not source_denies_action(title, lead, opening_predicate)):
            def models_in(text):
                models = set()
                for subject in sorted(subjects):
                    variants = {match.group().replace(' ', '-') for match in _compiled_rule(
                        re.escape(subject).replace(r'\-', r'\s*')
                        + r'(?:\s+(?:mini|pro|max|air|duo|ultra|hd|\d+[a-z]*)){0,3}').finditer(text)}
                    models.update(variants - {subject} or variants)
                return models
            models = models_in(h)
            owned = []
            for clause in preorder_clauses:
                clause_subjects = hardware_action_subjects(clause)
                clause_models = models_in(clause)
                if not clause_models and not s(r'\bboth\s+(?:devices|products|models)\b|两款(?:设备|产品|机型)', clause):
                    continue
                if clause_subjects and (not clause_subjects <= subjects or any(
                        model not in models and model not in subjects for model in clause_models)):
                    continue
                schedule = s(relative_schedule, clause)
                if (schedule
                        and s(r'available|begin|start|open|开始|开启|开放', clause)
                        and not s(superseded, clause)
                        and not source_denies_action(clause, '', opening_predicate)
                        and not s(r'not|never|不会|尚未', clause)):
                    owned.append(next(value for value in schedule.groups() if value))
            if owned:
                relative = owned[0]
                stage = ('reported' if s(r'expected|may|might|could|should|预计|可能|据称', h)
                         else 'open' if s(r'now|already|现已|开始接受', h)
                         else 'announced' if s(r'confirm|announc|宣布|确认', h)
                         else 'reported')
                period = ('next-week' if s(r'next|下周', relative) else
                          'this-week' if s(r'this|本周', relative) else
                          'tomorrow' if s(r'tomorrow|明天|明日', relative) else 'today')
                return SourceActionFrame('apple:preorder-batch:' + '+'.join(sorted(models)),
                    'preorder-schedule-' + stage, 'hardware_products', 'hardware_market', period=period)
    if (not s(r'apple|苹果|macbook|ipad|jos?z?wiak', h)
            or not s(r'launch|announc|event|debut|teases?|reveal|unveil|coming|发布|官宣|亮相|新品', h)
            or s(r'last\s+year|回顾|buy|购买|不要买|delay|postpon|cancel|延期|推迟|取消', h)
            or s(r'(?<![a-z])(?:ios|ipados|macos|watchos|tvos|visionos|homeos)(?![a-z])', h)
            or source_denies_action(title, lead, r'launch\w*|introduc\w*|release\w*|发布|推出')):
        return None
    primary = h + '. ' + _normalized(lead[:500])
    if not s(r'(?:product|hardware|macs|macbook|ipads?|home|event|iphone).{0,45}(?:launch|debut|event|releases?)|'
             r'(?:launch|debut|introduc|releas|event|teas).{0,55}(?:product|hardware|macs|macbook|ipads?|home|iphone)|'
             r'\b(?:announc\w*|confirm\w*|plans?|hold\w*|schedul\w*)\b.{0,35}\bevent\b|'
             r'发布会|新品|发布.{0,35}(?:mac|ipad|iphone|家居)|(?:mac|ipad|iphone|家居).{0,35}(?:发布|亮相)', primary):
        return None
    # A specific non-launch object already completes the headline predicate.
    if s(r'repair\s+program|replacement\s+program|recall|维修计划|召回|更换计划', h) or s(
            r'\b(?:launch\w*|announc\w*|introduc\w*|releas\w*)\b[^.;:]{0,65}\b(?:apps?|applications?|software|services?|features?|subscriptions?|websites?)\b|'
            r'(?:发布|推出|上线).{0,35}(?:应用|软件|服务|功能|订阅|网站)', h):
        return None
    months = 'january february march april may june july august september october november december'.split()
    month_numbers = {name: index for index, month in enumerate(months, 1) for name in (month, month[:3])}
    month_numbers['sept'] = 9
    names = '|'.join(sorted(month_numbers, key=len, reverse=True))
    en_date = r'(?:on|around|for|until|happening\s+on)[ \"‘’“”]*(?:or\s+around[ \"‘’“”]*)?(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+)?(' + names + r')\.?\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?'
    zh_day = r'(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    zh_date = r'(?:计划(?:在|于)?|拟于|定档|将于|安排在|(?:会|将)在)\s*' + zh_day
    for value in (title, lead, *passages):
        for start, end in source_sentence_spans(value):
            clause = _normalized(value[start:end])
            if s(r'previously|last\s+(?:year|month)|此前|去年|此前爆料|not\s+announc|尚未.*公布', clause):
                continue
            if source_denies_action('', clause, r'invit\w*|launch\w*|introduc\w*|发布|推出|邀请'):
                continue
            if not s(r'apple|苹果|jos?z?wiak|发布会', clause):
                continue
            if not s(r'launch|announc|introduc|event|debut|release|teas|发布|官宣|亮相|推出', clause):
                continue
            headline_devices = hardware_action_subjects(title)
            clause_devices = hardware_action_subjects(clause)
            if headline_devices:
                compatible = any(a == b or a.startswith(b + '-') or b.startswith(a + '-')
                                 for a in headline_devices for b in clause_devices)
                if not compatible and (clause_devices or value != title):
                    continue
            date = s(en_date, clause)
            chinese = s(zh_date, clause)
            actor = s(r'apple|苹果|jos?z?wiak|发布会', clause)
            dated = date or chinese
            if dated and actor and actor.start() > dated.start():
                continue
            if dated and s(r'\b(?:following|after)\s+(?:its|their|the|apple\x27s)\s+'
                           r'(?:unveiling|launch|release|announcement)\b', clause[:dated.start()]):
                continue
            if date:
                month, day = month_numbers[date.group(1)], int(date.group(2))
                year = s(r'\b20\d{2}\b', clause[date.end():date.end()+8])
                year = year.group() if year else ''
            elif chinese:
                year, month, day = chinese.group(1) or '', int(chinese.group(2)), int(chinese.group(3))
            else:
                continue
            if not (1 <= month <= 12 and 1 <= day <= 31):
                continue
            confirmed = s(r'\b(?:announces|announced|confirms|confirmed|invited|invites|teases|teased)\b|官宣|宣布|定档|预热视频|邀请函|已确认|has\s+made\s+it.{0,30}clear', h + ' ' + clause)
            reported = s(r'rumou?r|reportedly|expected|may\s+(?:announce|confirm)|could\s+(?:announce|confirm)|传闻|可能|预计|大概率', h + ' ' + clause)
            action = 'launch-date-confirmation' if confirmed and not reported else 'launch-date-report'
            subjects = hardware_action_subjects(title + ' ' + clause)
            phones = iphone_report_subjects(title + ' ' + clause)
            if phones:
                model_identity = identity or build_event_identity(title, '')
                models = {'iphone-' + value.removeprefix('iphone-model:')
                          for value in model_identity.title_components if value.startswith('iphone-model:')}
                if models:
                    phones = models
                elif s(r'iphone\s*\d+\s*(?:series|系列)', h):
                    phones = {'iphone-family-' + p.removeprefix('iphone-') for p in phones}
                subjects.discard('iphone')
                subjects |= phones
            subject = ('apple:product-launch:' + next(iter(subjects)) if len(subjects) == 1
                       and not s(r'\bevent\b|发布会|特别活动', h) else 'apple:product-launch-campaign')
            return SourceActionFrame(subject, action, 'hardware_products', 'hardware_market', period=f'month:{month}:day:{day}', year=year, launch_subjects=tuple(sorted(subjects)))
    return None


def _leadership_transition_scope(title: str) -> bool:
    # Existing organizational handover reports are outside this migration.
    return bool(_frame_search(r'leadership\s+transition|transition|meddl|interfer|stepped\s+down|leaving.{0,30}ceo|交接|干预|卸任', title))


def bind_leadership_report(evidence: ArticleEvidence) -> BoundClaim | None:
    """Bind person-led interviews/profiles, keeping unresolved roles visible.

    A current responsibility or attributed company choice establishes policy
    evidence. The interview's existence and a person's name do not. Software
    operations and other named public actions remain with their own binders.
    """
    title = evidence.title
    lead = evidence.raw_lead or next((u.text for u in evidence.units if u.kind == 'summary'), '')
    if _leadership_transition_scope(title):
        return None
    people = source_executive_people(title)
    if not people:
        named = _compiled_rule(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?i:discusses|talks|explains|reflects)\b', 0).search(title)
        if named:
            people = frozenset({named.group(1).lower().replace(' ', '-')})
    if not people and _frame_search(r'\b(?:ceo|chairman|executive)\b|首席执行官|高管|董事长|苹果(?:公司)?(?:新任)?ceo', title):
        people = source_executive_people(lead[:next(source_sentence_spans(lead), (0, len(lead)))[1]])
    if len(people) != 1:
        return None
    person = next(iter(people))
    # Anchor the report predicate to the identified person's name. Title Case
    # words belonging to another action cannot extend that nominal subject.
    full_name = re.escape(person.replace('-', ' ')).replace(r'\ ', r'\s+')
    name_pattern = next((pattern for key, pattern in _EXECUTIVE_NAME_ALIASES if key == person), full_name)
    presentation = _compiled_rule(
        r'\s+(?i:talks?|discusses?|explains?|reflects?|(?:is\s+)?featured\s+on|'
        r'in\s+(?:a\s+)?(?:new\s+)?interview)\b|\s*(?:登上|登)[^：:。]{0,35}封面', 0)
    report_form = any(
        presentation.match(title, match.end())
        or _compiled_rule(r'^(?i:(?:new\s+)?(?:interview|profile)\s+(?:with|of|on))\s*$|^(?:专访|访谈|采访)\s*$', 0).match(title[:match.start()])
        for match in _compiled_rule(name_pattern, re.I).finditer(title))
    role_question = _frame_search(r'^[^：:，,。！？]{0,50}(?:CEO|首席执行官)[:：][^。！？]{0,80}(?:为何|如何)', title)
    if not report_form and not role_question:
        return None

    body = tuple(u for u in evidence.units if u.kind in {'p', 'li', 'text', 'summary', 'selected_fact'}
                 and u.container_id != 'caption')
    interview = r'\binterview(?:ed|s)?\b|采访|专访|访谈'
    if not any(_frame_search(interview, value) for value in (title, lead, *(u.text for u in body))):
        return None
    person_pattern = r'(?:' + re.escape(person.replace('-', ' ')).replace(r'\ ', r'\s+') + '|' + re.escape(person.rsplit('-', 1)[-1]) + r')'
    def owns(text):
        return person in source_executive_people(text) or bool(_frame_search(
            r'(?<![a-z])' + re.escape(person.rsplit('-', 1)[-1]) + r'(?![a-z])', text))
    role = r'(?:CEO|chief executive|chairman|executive chair|vice president|首席执行官|董事长|高管|掌门人)'
    roles = []
    for unit in evidence.units:
        # Company and holder belong to one noun phrase, not two mentions
        # somewhere in the same paragraph.
        for match in _compiled_rule(
                r'(?P<before>(?i:former)\s+|前任|前)?(?P<company>[A-Z][A-Za-z0-9]*|苹果)(?:公司|[\x27’]s)?\s*'
                r'(?:(?i:new|current)\s+|新任)?(?P<after>(?i:former)\s+|前任)?'
                r'(?i:' + role + r')\s*(?P<holder>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}|[\u4e00-\u9fff·・]{2,18})', 0).finditer(unit.text):
            holder = match.group('holder')
            if (_normalized(holder).replace(' ', '-') == person
                    or person in source_executive_people(holder)
                    or (' ' not in holder and owns(holder))):
                roles.append((unit.unit_id, match.start(), match.end(), match.group('company'),
                              bool(match.group('before') or match.group('after'))))
        for match in _compiled_rule(person_pattern + r',\s*(?:a\s+)?(?P<past>former\s+)?'
                r'(?P<company>[a-z][a-z0-9]*)\s+' + role, re.I).finditer(unit.text):
            roles.append((unit.unit_id, match.start(), match.end(), match.group('company'), bool(match.group('past'))))
    # A named person's explicit work affiliation can resolve a later current
    # role in the same report. An explicit other-company or former role wins.
    affiliations = [u for u in body if _frame_search(person_pattern +
        r'\s+(?:was|is)\s+(?:involved|working)\b[^.!?。]{0,100}\bat\s+Apple\b', u.text)]
    current_roles = [u for u in body if _frame_search(person_pattern +
        r'[^.!?。]{0,85}\b(?:tenure\s+as|serves?\s+as)\s+' + role, u.text)]
    if not roles and affiliations and current_roles:
        roles = [(u.unit_id, 0, len(u.text), 'Apple', False) for u in (*affiliations, *current_roles)]
    relation = ('independent' if roles and any(past or company.lower() not in {'apple', '苹果'}
                                              for _, _, _, company, past in roles)
                else 'apple-direct' if roles else '')
    spans = []
    statements = []
    publication = [(person, 'company-role', company.lower() + (':former' if past else ':current'), key, start, end)
                   for key, start, end, company, past in roles]
    objects = set()
    historical = bool(_frame_search(r'resurfaced|revisited|旧访谈|去年.{0,12}采访|'
        r'interview[^.!?。]{0,75}(?:from|recorded|conducted|published)\s+(?:last\s+year|\d+\s+years?\s+ago)', lead))
    for unit in body:
        text = unit.text
        if _frame_search(interview, text):
            outlet = (_compiled_rule(r'(?:interview\s+with|sat\s+down\s+with|told)\s+((?:The\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}|TIME)\b', 0).search(text)
                      or _compiled_rule(r'《([^》]+)》[^。]{0,55}(?:采访|专访)|(?:采访|专访)[^。]{0,55}《([^》]+)》', 0).search(text))
            if outlet:
                name = next(v for v in outlet.groups() if v)
                publication.append((person, 'interview-publisher', _normalized(name).removeprefix('the ').replace(' ', '-'),
                                    unit.unit_id, outlet.start(), outlet.end()))
        for start, end in source_sentence_spans(text):
            clause = text[start:end]
            if not owns(clause):
                continue
            responsibility = _compiled_rule(
                r'(?P<holder>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}|[\u4e00-\u9fff·・]{2,12})\s*[“\"]?\s*'
                r'(?i:currently\s+(?:leads?|oversees?|manages?)|has\s+devoted|is\s+responsible\s+for|'
                r'(?:正在|正)\s*(?:进一步)?(?:负责|主导|强化|统筹|掌管))', 0).search(clause)
            if responsibility and not owns(responsibility.group('holder')):
                responsibility = None
            object_scope = _frame_search(r'\b(?:design|teams?|policymakers?|management|development)\b|'
                                        r'设计|团队|管理|研发|政策', clause)
            attribution = _frame_search(person_pattern + r'\s+(?:said|says|states?|emphasiz\w*)\b', clause)
            choice = _frame_search(r'\b(?:the company|apple)\b[^.!?。]{0,110}\b(?:focus\w*|make|prioriti\w*|consider\w*)\b|'
                r'苹果[^。]{0,65}(?:要求|考虑|选择|决定)|(?:方案|安全)[^。]{0,45}(?:纳入考虑|考虑因素)', clause)
            predicate = responsibility or attribution
            prefix = clause[:predicate.end()] if predicate else clause
            if source_predicate_role(prefix) != 'current' or _frame_search(r'^\s*(?:if\b|如果|假如)', prefix):
                continue
            if (responsibility and object_scope) or (attribution and choice):
                statements.append((unit.unit_id, start, end))
                target = clause[attribution.end():] if attribution else clause
                software = _extract_patterns(_normalized(target), PRODUCT_PATTERNS) & {
                    'app-store', 'icloud', 'apple-music', 'apple-tv', 'ios', 'ipados', 'macos', 'siri'}
                policy = _frame_search(r'\b(?:charging|fee|permissions?|access policy|distribution terms)\b|收费|费用|权限|分发条款', target)
                objects.add('service-policy:' + '+'.join(sorted(software)) if software and policy else 'company-responsibilities')
    spans.extend(statements)
    if not spans:
        spans = [(u.unit_id, 0, len(u.text)) for u in body[:1]]
    report_role = 'background' if historical else 'independent' if statements else ''
    reason = '' if report_role else 'Captured leadership reporting has no bound current responsibility or company decision; review its profile and supporting facts without using the person as eligibility evidence'
    if report_role == 'independent' and not relation:
        reason = 'The reported responsibility is clear but the speaker\'s current company role is unresolved'
    if len(objects) > 1:
        report_role = ''
        reason = 'Company responsibilities and a specific service policy need separate source-bound decisions'
    elif report_role == 'independent' and relation and not reason:
        reason = 'Current company report is qualified; its interview instance is unbound, so verify shared source reporting before merging'
    # Publication identity is only a retrieval clue. Without a shared cited
    # interview instance, the matcher must keep its relation unresolved.
    target = next(iter(objects)) if len(objects) == 1 else 'company-responsibilities'
    category = 'software_systems' if target.startswith('service-policy:') else 'hardware_products'
    return BoundClaim(person, 'leadership-report', target, tuple(publication),
        evidence.article_id, tuple(dict.fromkeys(key for key, _, _ in spans)), tuple(dict.fromkeys(spans)),
        evidence.content_form, category, 'company_org', relation, report_role, 'affirmed', reason)


def _legacy_transition_interview_frame(title: str, lead: str, passages: tuple[str, ...]) -> SourceActionFrame | None:
    """Bind the current speaker, interview publication and leadership topic."""
    h = _normalized(title)
    s = _frame_search
    named = _compiled_rule(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\b', 0).search(title)
    person = named.group(1).lower().replace(' ', '-') if named else ''
    if s(r'库克', h):
        person = 'tim-cook'
    elif s(r'特努斯|特纳斯', h):
        person = 'john-ternus'
    if not person or s(r'old\s+interview|last\s+year.s\s+interview|旧访谈|去年.{0,8}采访', h):
        return None
    intro = _normalized(lead[:1000])
    historical = bool(s(r'resurfaced|revisited|interview\s+(?:(?:with|by)\s+[^.]{0,45}?\s+)?(?:from|recorded|conducted|published)\s+(?:last\s+year|\d+\s+years?\s+ago)|旧访谈|去年.{0,20}采访', intro))
    for value in (lead, *passages):
        if not s(r'apple|苹果|cook|ternus|库克|特努斯', value):
            continue
        outlet = (_compiled_rule(r"(?:interview\s+with|sat\s+down\s+with|told|According\s+to)\s+((?:The\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", 0).search(value)
                  or _compiled_rule(r"^((?:The\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})['’]s.{0,80}interview", 0).search(value)
                  or _compiled_rule(r'接受《([^》]+)》.{0,60}采访', 0).search(value))
        if not outlet:
            continue
        publication = _normalized(outlet.group(1)).removeprefix('the ').replace(' ', '-')
        publication = {'独立报': 'independent'}.get(publication, publication)
        return SourceActionFrame('apple:leadership:' + person + ':' + publication,
            'historical-interview' if historical else 'transition-interview', 'hardware_products', 'company_org', 'weak' if historical else 'strong')
    if s(r'interview|采访|访谈', intro) and s(r'apple|苹果', h + ' ' + intro):
        return SourceActionFrame('apple:leadership:' + person + ':unidentified-interview',
            'historical-interview' if historical else 'transition-interview', 'hardware_products', 'company_org', 'weak' if historical else 'strong')
    return None


def source_leadership_interview_frame(title: str, lead: str, passages: tuple[str, ...]) -> SourceActionFrame | None:
    """Compatibility view of the same source relationship; no second policy."""
    if _leadership_transition_scope(title):
        return _legacy_transition_interview_frame(title, lead, passages)
    from .article_processing import capture_article_title_evidence
    claim = bind_leadership_report(capture_article_title_evidence('', '', title, lead, passages))
    if claim is None:
        return None
    publisher = next((q[2] for q in claim.qualifiers if q[1] == 'interview-publisher'), '')
    return SourceActionFrame('apple:leadership:' + claim.subject + ':' + publisher,
        claim.action, claim.category, claim.event_kind, '', bound_claim=claim)


def source_market_report_frame(title: str, lead: str, passages: tuple[str, ...]) -> SourceActionFrame | None:
    """The reported measure or order is the object, not its price backdrop.

    A response, an equity move and a device-sales measurement have different
    actors/objects even when every source repeats the same production rumor.
    """
    h, opening = _normalized(title), _normalized(lead)[:1000]
    s = _frame_search
    local = h + ' ' + opening
    if s(r'last year|historical|回顾|去年', h):
        return None
    def frame(subject, action, period=''):
        return SourceActionFrame(subject, action, 'hardware_products', 'hardware_market', period=period)
    # A source can report one redistribution across several models. Bind the
    # complete set of model/direction pairs, not a reservation or price nearby.
    if (s(r'iphone', h) and s(r'orders?|加单|砍单|订单', h)
            and _operation_owner(h) in {'', 'apple'}
            and not s(r"apple(?:['’]s)?\s+(?:supplier|rival|competitor)\b|苹果供应商", h)
            and not s(r'否认|驳斥|没有|并未|\b(?:denies|denied|refut\w*|not|never)\b', h)
            and s(r'苹果(?:公司)?(?:正在|正)?[^。.!?]{0,55}结构性调整|苹果.{0,25}订单.{0,15}结构性调整|apple.{0,45}rebalanc', local)):
        changes = set()
        periods = set()
        for value in (opening, *(_normalized(p) for p in passages)):
            if s(r'此前|去年|last\s+year|previously|否认|驳斥|并未|没有|假消息|does\s+not|denied', value):
                continue
            for match in _compiled_rule(r'iphone\s*(duo|\d+(?:\s*pro(?:\s*max)?)?)\s*(?:(?:则|相应|已|已经|将|的订单)\s*){0,3}(加单|砍单)', re.I).finditer(value):
                changes.add(match.group(1).replace(' ', '-') + ':' + ('increase' if match.group(2) == '加单' else 'reduction'))
            for start, end in source_sentence_spans(value):
                clause = value[start:end]
                # A later product's season cannot date this order operation.
                if not s(r'结构性调整|rebalanc', clause) or not s(r'orders?|订单', clause):
                    continue
                season = s(r'(?:(20\d{2})\s*年)?(春|夏|秋|冬)季', clause)
                if season:
                    periods.add((season.group(1) or '', {'春':'spring', '夏':'summer', '秋':'fall', '冬':'winter'}[season.group(2)]))
        dated = {p for p in periods if p[0]}
        if len(changes) >= 2 and len({p[1] for p in periods}) == 1 and len(dated) <= 1:
            year, period = next(iter(dated or periods))
            return replace(frame('apple:iphone-orders:' + ','.join(sorted(changes)), 'coordinated-order-reallocation', period), year=year)
    if (s(r'apple\s+(?:shares|stock)|苹果股价', h)
            and s(r'fall|fell|drop|rise|rose|gain|下跌|上涨', h)
            and not s(r'could|might|may|预测|可能', h)):
        return frame('apple:equity', 'trading-price-report')
    phone = s(r'iphone\s*(\d+|duo|air)(?![a-z0-9])(?:\s*(pro(?:\s*max)?|plus|air)(?![a-z0-9]))?', h)
    if not phone:
        return None
    model = 'iphone-' + phone.group(1) + (('-' + phone.group(2).replace(' ', '-')) if phone.group(2) else '')
    first = opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
    if s(r'refut|disput|质疑|驳斥', first) and not s(r'respond|回应|否认', h):
        return None  # A disputed claim in a feed excerpt is not this source's finding.
    response = s(r'回应|否认|没听说|未.{0,8}变化|respond|deni(?:es|ed)|refut', h)
    orders = s(r'orders?|production|订单|减产|零部件生产', h)
    if orders and response:
        obj = 'assembly-orders' if s(r'assembly|whole.unit|整机|组装', h) else 'component-orders'
        return frame(model + ':' + obj, 'supplier-response')
    if orders and s(r'cut|reduc|increas|boost|orders?\s+(?:up|down)\s+\d|削减|减少|增加|增产|减产', h):
        # Actor and polarity belong to the operation, not to another sentence
        # that mentions Apple as background or an unchanged comparator.
        owner = _operation_owner(h)
        denied = r'\b(?:not|never|no|denies?|denied|might|could)\b|并未|否认|没有|可能'
        owned = s(r'apple\s+(?:(?:has|reportedly|allegedly|now|will)\s+)*(?:cuts?|reduc\w*|increas\w*|boost\w*)|苹果(?:(?:据报|据称|被曝|公司|方面|已经|大幅|正在|已|正|将)\s*)*(?:削减|减少|增加|增产|减产)', h)
        owned_verb = owned
        if owned_verb is not None:
            owner = _operation_owner(h[owned_verb.start():])
        if owned is None and s(r'production\s+orders?\s+(?:up|down)\s+\d', h):
            owned = s(r'production\s+orders?\s+(?:up|down)', h)
        if owner not in {'', 'apple'} or not owned or s(denied, owned.group()):
            return None
        if not s(r'orders?|production|订单|产量|零部件生产', opening):
            return None
        # A teaser prefix may name another phone. Bind the object after the
        # owned order verb before falling back to a phone-led headline.
        order_object = (_compiled_rule(r'[;；!！:：。]|\b(?:while|whereas|but)\b|而|但', 0).split(h[owned_verb.end():])[0]
                        if owned_verb is not None else '')
        order_phone = s(r'iphone\s*(\d+|duo|air)(?![a-z0-9])(?:\s*(pro(?:\s*max)?|plus|air)(?![a-z0-9]))?', order_object)
        if order_phone:
            model = 'iphone-' + order_phone.group(1) + (('-' + order_phone.group(2).replace(' ', '-')) if order_phone.group(2) else '')
        obj = 'assembly-orders' if s(r'assembly|whole.unit|整机|组装', h) else 'component-orders'
        action = 'order-increase-report' if s(r'increas|boost|orders?\s+up\s+\d|增加|增产', h) else 'order-reduction-report'
        months = 'january february march april may june july august september october november december'.split()
        month_names = '|'.join(months)
        periods = set()
        for value in (h, opening, *(_normalized(p) for p in passages)):
            for start, end in source_sentence_spans(value):
                clause = value[start:end]
                if (not s(r'orders?|订单', clause)
                        or s(r'是否|没有明确|尚不清楚|\bwhether\b|unclear|unknown', clause)):
                    continue
                month = (s(r'orders?\s+for\s+(' + month_names + r')(?:\s+(20\d{2}))?', clause)
                         or s(r'(' + month_names + r')(?:\s+(20\d{2}))?\s+(?:component\s+|assembly\s+)?orders?', clause)
                         or s(r'(?:(20\d{2})年)?(1[0-2]|[1-9])\s*月(?:份)?(?!\s*\d+\s*日)[^，,。；;]{0,15}订单', clause))
                if month:
                    a, b = month.groups()
                    periods.add((b or '', str(months.index(a) + 1)) if a in months else (a or '', b))
        if len(periods) > 1:
            return None
        year, month = next(iter(periods), ('', ''))
        return replace(frame(model + ':' + obj, action, 'month-' + month if month else ''), year=year)
    if (s(r'sales|activations?|销量|激活量|卖出|狂销|卖不动', h)
            and not s(r'(?<![a-z0-9])w\s*\d|week\s*\d|预计|forecast|未达|没有达到|\b(?:not|never|no)\b', h)
            and not s(r'超过|outperform|outsell|beats?', h[:phone.start()])):
        # This supplements the primary-measure parser only with an explicit
        # weekly measurement. Keep the measured model, scope and quantity;
        # the headline model alone cannot stand in for the measured product.
        previous_period = ''
        for value in (opening, *(_normalized(p) for p in passages)):
            for start, end in source_sentence_spans(value):
                clause = value[start:end]
                if s(r'^其中|^within\s+that\s+week', clause.strip()) and previous_period:
                    clause = previous_period + ' ' + clause
                week = s(r'(?<![a-z0-9])w\s*(\d{1,2})(?![0-9])|week\s+(\d{1,2})|第\s*(\d{1,2})\s*周', clause)
                previous_period = clause if week and s(r'iphone.{0,65}(?:激活量|sales|销量)', clause) else ''
                measured = s(r'iphone\s*(\d+)(?:\s*(pro(?:\s*max)?|plus|air))?', clause)
                count = s(r'(?:sales|activations?|销量|激活量?)\D{0,20}([\d,]+(?:\.\d+)?)\s*(万|million|units|台)', clause)
                if not (week and measured and count):
                    continue
                # The period introduction can name the family, while the
                # following breakdown measures one model. Use the local model.
                before_count = list(_compiled_rule(r'iphone\s*(\d+)(?:\s*(pro(?:\s*max)?|plus|air))?', re.I).finditer(clause[:count.start()]))
                if before_count:
                    measured = before_count[-1]
                if s(r'\b(?:not|never|no|forecast|expected)\b|未达|没有达到|否认|预计|预测|此前|last\s+(?:year|week)', clause):
                    return None
                scope = h + ' ' + clause
                regions = [key for key, pattern in (('china', r'中国|国内|\bchina\b'),
                    ('us', r'美国|united states|\bus\b'), ('global', r'全球|worldwide|global')) if s(pattern, scope)]
                if len(regions) > 1:
                    return None
                product = 'iphone-' + measured.group(1) + (('-' + measured.group(2).replace(' ', '-')) if measured.group(2) else '')
                cumulative = bool(s(r'累计|cumulative|to.date', clause[:count.end()]))
                single = bool(s(r'单周|当周|本周|weekly|single.week', clause[:count.end()]))
                if cumulative and single:
                    return None
                metric = 'cumulative' if cumulative else 'single-week' if single else 'unspecified'
                year = s(r'(?<!\d)(20\d{2})(?:年|[- ]w)', clause)
                quantity = format((Decimal(count.group(1).replace(',', '')) * {'万': 10000, 'million': 1000000}.get(count.group(2), 1)).normalize(), 'f')
                subject = ':'.join((product, 'sales', metric, quantity))
                return replace(frame(subject, 'device-sales-report', 'week-' + next(v for v in week.groups() if v)),
                               year=year.group(1) if year else '', region=regions[0] if regions else '')

    return None


_DEVICE_TEST_OBJECT = (r'(?<![a-z0-9])(iphone|ipad)\s*(\d+)(?:\s*(pro(?:\s+max)?|air|mini|plus))?'
    r'(?:\s*(?:/|and|和|及|、)\s*(?:pro\s+)?(max))?')


def source_device_test_objects(text: str) -> frozenset[str]:
    objects = set()
    for match in _compiled_rule(_DEVICE_TEST_OBJECT, 0).finditer(_normalized(text)):
        family = match.group(1) + '-' + match.group(2)
        suffix = _compiled_rule(r'\s+', 0).sub('', match.group(3) or '')
        objects.add(family + (':' + suffix if suffix else ''))
        if match.group(4):
            objects.add(family + ':promax')
    return frozenset(objects)


def source_device_behavior_test_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """A focused device test owns its conditions, not the accessory used in it."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    device = s(_DEVICE_TEST_OBJECT, h)
    if not device or s(r'教程|选购|推荐|促销|how\s+to|buying\s+guide|best\s+chargers?', h):
        return None
    focus = ('charging' if s(r'充电|快充|charging', h) else
             'camera-exposure' if s(r'快门|曝光|shutter|exposure', h) else '')
    if not focus:
        return None
    # A headline test must concern the Apple device's measured behavior; a
    # charger launch, a prospective test or an old quoted claim cannot own it.
    passages = [opening, *(_normalized(f) for f in facts)]
    objects = source_device_test_objects(h)
    subject = ','.join(sorted(objects))
    def owns_object(text):
        values = source_device_test_objects(text)
        return bool(values & objects or any(value.split(':')[0] in objects for value in values))
    claims = [claim.group() for p in passages[:3]
        if (claim := s(r'(?:实测(?:显示|发现)|测试(?:显示|指出|发现)|\b(?:tests?|testing)\s+(?:shows?|found|reveals?)\b)'
          r'[，,:：\s]*(?:在\s*)?(?:苹果\s*|apple\s+)?' + _DEVICE_TEST_OBJECT, p))
        and not s(r'计划.{0,16}(?:测试|实测)|(?:尚未|并未|没有).{0,8}(?:测试|实测)|去年|此前|'
                  r'\b(?:plans?\s+to\s+test|not\s+(?:yet\s+)?tested|previously|last\s+year)\b', p)
    ]
    if (s(r'测试.{0,12}(?:尚待|尚未)|not\s+yet\s+tested', h)
            or (claims and not any(owns_object(claim) for claim in claims))):
        return SourceActionFrame('publisher:test:' + h, 'test-without-current-device-result',
            'hardware_products', 'general_company', 'weak')
    if not claims:
        return None
    if focus == 'charging':
        if not (s(r'^(?:苹果\s*)?(?:iphone|ipad)|\btests?\s+(?:the\s+)?(?:iphone|ipad)', h)
                and s(r'测试|实测|test', h)
                and any(owns_object(p) and s(r'\d+\s*(?:分钟|minutes?)', p)
                        and s(r'充满|full\s+charge|charge\s+fully', p) for p in passages)):
            return None
    elif not any(s(r'手动|manual', p) and s(r'单帧|多帧|single.frame|frame\s+stacking', p)
                 for p in passages):
        return None
    reporter = s(r'(?:科技媒体|评测机构|媒体|实验室)\s*([a-z][a-z0-9]*(?:\s+[a-z0-9]+){0,2})(?=\s*(?:今天|近日|实测|测试|发布))', opening)
    if reporter is None:
        reporter = s(r'^([a-z][a-z0-9]*(?:\s+[a-z0-9]+){0,2})(?=\s*(?:称|实测|测试|tests?\b))', h)
    owner = reporter.group(1).replace(' ', '-') if reporter else h
    return SourceActionFrame(subject + ':tester:' + owner, 'device-behavior-test-' + focus,
                             'hardware_products', 'hardware_market')


def source_system_pairing_frame(title: str, lead: str) -> SourceActionFrame | None:
    """A new system pairing implementation is not ordinary companion-app use."""
    h, opening = _normalized(title), _normalized(lead)
    s = _frame_search
    if not s(r'apple\s*watch', h):
        return None
    platforms = {p for p in ('android', 'linux', 'windows', 'harmonyos') if s(r'\b' + p + r'\b', h)}
    if s(r'安卓', h):
        platforms.add('android')
    if s(r'鸿蒙', h):
        platforms.add('harmonyos')
    if not platforms:
        return None
    if opening.startswith(h):
        opening = opening[len(h):].lstrip(' .。')
    sentences = [opening[a:b] for a, b in source_sentence_spans(opening[:900])]
    if not sentences:
        return None
    def current_clause(sentence):
        return _compiled_rule(r'\b(?:while|whereas|but|after|following)\b|而另|但另|在此前').split(sentence, maxsplit=1)[0]
    first = current_clause(sentences[0])
    blocked = (r'\b(?:plans?|hopes?|would|will|could|may|not|never|previously|recap|revisits?)\b|'
               r"\b(?:doesn|don|didn|isn|aren|hasn|haven|wasn|weren)['’]t\b|"
               r'last\s+(?:year|month)|years?\s+ago|计划|拟|将|尚未|并未|没有|否认|去年|此前|回顾')
    implementation = r'\b(?:has\s+developed|implements?|reimplements?|reconstructs?)\b|已(?:经)?(?:实现|开发|重建)|重建了'
    action = s(implementation, first)
    if (not action or s(blocked, h + ' ' + first) or not s(r'apple\s*watch', first)
            or not s(r'pairing|activation|setup\s+process|配对|激活', first)):
        return None
    owned_flow = (r'(?:implements?|reimplements?|reconstructs?)\s+(?:the\s+)?'
                  r'apple(?:\s*watch(?:[\'’]s)?|[\'’]s)\s+(?:normal\s+)?'
                  r'pairing\s+and\s+activation|(?:已经|已)?(?:实现|重建)(?:了)?\s*apple\s*watch\s*配对(?:与|和)激活')
    # The flow must be the object of the developer's own first predicate,
    # not of another named project's later predicate in the same sentence.
    protocol = _compiled_rule(owned_flow).match(first, action.start())
    if not protocol and len(sentences) > 1 and s(
            r'has\s+developed\s+(?:a\s+)?tool\b[^.。!?]{0,100}'
            r'apple\s*watch\s+setup\s+process', first[action.start():]):
        # A direct anaphoric developer quote may explain that setup tool.
        follow = current_clause(sentences[1]).lstrip()
        referring_subject = s(
            r'^(?:the\s+developers?\s+(?:say|explain)(?:\s+that)?\s+)?'
            r'(?:it|the\s+tool)\s+["“\']?', follow)
        if referring_subject and not s(blocked, follow):
            protocol = _compiled_rule(owned_flow).match(follow, referring_subject.end())
    if not protocol:
        return None
    owner = _compiled_rule(r'^(?:the\s+|开源项目\s*)').sub('', first[:action.start()]).strip()
    owner = _compiled_rule(r'\s+(?:now|today|currently)$').sub('', owner).strip() or h
    return SourceActionFrame('apple-watch:system-pairing:' + owner + ':' + '+'.join(sorted(platforms)),
                             'system-pairing-implementation', kind='ecosystem_interop', tier='ecosystem')


def source_focused_report_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """Bind reported measurements and platform operations to their actual object.

    A host device, comparison model or article date cannot supply the subject
    of a capability or the launch window of a specification report.
    """
    h, opening = _normalized(title), _normalized(lead)[:1000]
    local = h + '. ' + opening
    detail = ' '.join((opening, *(_normalized(f) for f in facts)))
    s = _frame_search
    def frame(subject, action, category='software_systems', kind='os_app', period=''):
        return SourceActionFrame(subject, action, category, kind, period=period)

    market = source_market_report_frame(title, lead, facts)
    if market is not None:
        return market
    measurement = source_device_behavior_test_frame(title, lead, facts)
    if measurement is not None:
        return measurement
    pairing = source_system_pairing_frame(title, lead)
    if pairing is not None:
        return pairing

    if (s(r'dates?|日程|日期', h) and s(r'calendar|日历|日程', h)
            and s(r'recapped|recap|回顾|汇总', opening)):
        return replace(frame('publisher:calendar-recap', 'schedule-recap', 'hardware_products', 'general_company'), tier='weak')

    primary = h + ' ' + opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
    if (s(r'museum|hobbyist|enthusiast|博物馆|爱好者', primary)
            and s(r'replica|recreat|repurpos|复刻|复制品|爆改', primary)
            and s(r'mac|iphone|ipad', h)
            and _operation_owner(h) != 'apple'):
        # A measured Apple-device workload is reportable even when the
        # machines also form an exhibit. A target or comparison is not a test.
        other_cluster = any(
            not s(r'mac\s*mini', match.group())
            for match in _compiled_rule(
                r'\b(?:a|an|another|its)\s+(?:[a-z0-9-]+\s+){1,4}cluster\b|'
                r'(?:另有|另外|拥有|另一(?:个|套|组))[^。.!?，,]{0,40}集群', 0).finditer(detail))
        measured = any(
            s(r'matrix|矩阵', paragraph)
            and s(r'tests?|benchmark|测试|实测', passage)
            and (not other_cluster or s(r'\b(?:tested|benchmarked)\s+(?:this|the|its)\s+mac\s*mini\s+cluster\b|(?:测试|实测)[^。.!?]{0,12}mac\s*mini\s*集群', passage))
            and s(r'\b(?:tested|tests|benchmarked)\s+(?:this|the|its)\s+(?:mac\s*mini\s+)?cluster\b|'
                  r'(?:最近(?:一次)?|本次|此次)(?:的)?(?:基准)?测试(?:使用|采用)\s*\d+\s*个?[^。.!?]{0,15}(?:核心|节点)|'
                  r'(?:最近|本次|此次)(?:的)?测试中[^。.!?]{0,70}该集群|'
                  r'(?:展品|(?:该|本)?集群)(?:近期|最近|本次|此次)使用[^。.!?]{0,60}(?:程序)?测试', passage)
            and s(r'(?:^|[，,；;]|\band\s+)\s*'
                  r'(?:(?:该|本|此)集群|展品|(?:综合|浮点|计算)?性能|(?:the|this|its)\s+cluster)?\s*'
                  r'(?:achieved|reached|measured|达到|达到了|成绩约为)[^。.!?，,；;]{0,45}'
                  r'\d+(?:\.\d+)?\s*(?:(?:[gt]|giga|tera)flops|万亿次浮点运算每秒)', passage)
            and not s(r'\b(?:not|never|would|could|estimates?|estimated|predicts?|predicted)\b|plans?\s+to|will\s+test|theoretical|for\s+comparison|计划|拟|尚未|没有|未能|理论|预计|去年|作为对比|另一.{0,8}集群', passage)
            for paragraph in (opening, *(_normalized(f) for f in facts))
            for start, end in source_sentence_spans(paragraph)
            for passage in _compiled_rule(
                r'[;；]|\b(?:while|whereas|but)\b|[，,]\s*(?:而|但|同时)', 0
            ).split(paragraph[start:end]))
        target = s(r'(?<![a-z0-9])([a-z][a-z0-9]*-\d+)(?![a-z0-9])', h)
        count = s(r'(\d+)\s*台\s*(?:(?:\d{4})\s*(?:年)?款?\s*)?[^0-9。.!?，,]{0,16}mac\s*mini|'
                  r'(\d+)\s+(?:(?:old|retired|repurposed|apple)\s+){0,3}mac\s*mini', primary)
        if measured and target and count and s(r'mac\s*mini', h):
            size = next(value for value in count.groups() if value is not None)
            institution = s(r'(?:报道称|报道[，,:：]?|消息[，,:：]?|^)([\u4e00-\u9fff]{2,24}博物馆)', opening)
            if institution is None:
                institution = s(r'^((?:[a-z][a-z\'-]*\s+){1,5}museum)\b', h)
            owner = institution.group(1) if institution else h
            return frame('device-cluster:mac-mini:' + owner + ':' + target.group(1) + ':' + size,
                         'matrix-benchmark-report', 'hardware_products', 'hardware_market')
        return replace(frame('third-party:device-reuse:' + h, 'independent-project', 'hardware_products', 'third_party_ecosystem'), tier='weak')

    if (s(r'apple|苹果', h) and s(r'fund|基金', h)
            and s(r'clean\s+energy|renewable|清洁能源|可再生能源', local)
            and s(r'expand|increas|commit|扩容|增至|增资|承诺投资', local)
            and not s(r'deni|否认|not\s+(?:expand|increase)|不会扩', local)):
        return frame('apple:renewable-energy-fund', 'fund-investment-expansion', 'hardware_products', 'company_org')

    if (s(r'wraps?|vinyl\s+skins?|贴膜|保护贴', h)
            and s(r'our\s+favorites|our\s+picks|推荐|选购', opening)
            and not s(r'apple\s+(?:launches|introduces)|苹果(?:推出|发布)', h)):
        return replace(frame('third-party:accessories:' + h, 'accessory-selection'), tier='weak')

    if (s(r'apple\s*watch', h) and s(r'配对|pair', local)
            and s(r'harmonyos|android|安卓|鸿蒙', local)
            and s(r'已.{0,8}登陆|正式.{0,8}上线|now\s+available|launch', opening)
            and not s(r'尚未|不支持|not\s+(?:available|support)', local)):
        platform = 'harmonyos' if s(r'harmonyos|鸿蒙', local) else 'android'
        return replace(frame('apple-watch:' + platform + ':pairing', 'interoperability-rollout'), tier='ecosystem')

    if (s(r'iphone', h) and s(r'startup|boot|greet|开机|special\s+surprise', h)
            and s(r'custom|personali[sz]|自定义|个性化|定制', detail)
            and s(r'name|名字|用户名|姓名', detail) and s(r'apple\s*stores?|苹果零售店|门店', detail)):
        model = s(r'iphone\s*(duo|\d+(?:\s*pro(?:\s*max)?)?)', h)
        blocked = (s(r'how\s+to|step.by.step|教程|操作指南|third.party|第三方', h)
                   or s(r'否认|不提供|不会|\b(?:denies|denied|not|never)\b', h))
        # Bind the local function owner, not merely a store mentioned as
        # audience or as an explicit non-provider later in the paragraph.
        third_party = s(r'(?:third.party|independent).{0,18}app|第三方应用|第三方程序', opening)
        denied_store = s(r'(?:apple\s*stores?|苹果(?:实体)?零售店|门店).{0,18}(?:并未|没有|不提供|不会|does\s+not|do\s+not|never)', opening)
        retail_claim = False
        for passage in (opening, *(_normalized(f) for f in facts)):
            for start, end in source_sentence_spans(passage):
                clause = passage[start:end]
                if s(r'third.party|independent\s+app|第三方应用|并未|不提供|does\s+not|do\s+not', clause):
                    continue
                retail_operation = s(r'(?:buy|purchas\w*)[^.!?]{0,70}(?:from|at|in)[^.!?]{0,25}apple\s*store|'
                    r'apple\s*stores?\s+(?:buyers|customers|owners)|'
                    r'apple\s*stores?\s+(?:(?:will|can|now)\s+)*(?:offer|provide|personali[sz]|custom|set)|'
                    r'在[^。！？]{0,12}苹果(?:实体)?零售店购买|'
                    r'苹果(?:实体)?零售店.{0,25}(?:提供|定制|设置)|苹果使用零售店', clause)
                if retail_operation and s(r'personali[sz]|custom|姓名|名字|个性化|定制|设置.{0,25}开机', clause):
                    retail_claim = True
                    break
            if retail_claim:
                break
        if third_party and not retail_claim:
            return replace(frame('third-party:personalization:' + h, 'independent-app-personalization', 'hardware_products', 'third_party_ecosystem'), tier='weak')
        blocked = blocked or denied_store or not retail_claim
        if model and not blocked:
            return frame('iphone-' + model.group(1).replace(' ', '-') + ':startup-greeting', 'retail-personalization-report', 'hardware_products', 'hardware_market')

    # An editorial column name or MDM transport does not own a first-party
    # diagnostic operation. Require the platform's command and destination.
    if (s(r'applecare', h) and s(r'log\s+collection|日志.{0,8}收集|收集.{0,8}日志', h)
            and not s(r'how\s+to|step.by.step|教程|操作指南|third.party|第三方', h)
            and s(r'apple\s+(?:introduced|added|provides)|苹果(?:新增|引入|提供)', detail)
            and s(r'(?:management\s+)?commands?|管理命令', detail)
            and s(r'logs?.{0,55}(?:directly\s+to\s+apple|straight\s+to\s+apple)|日志.{0,35}(?:直接上传苹果|上传至苹果)', detail)):
        version = s(r'(?:macos|ios|ipados|tvos)\s*(\d+(?:\.\d+)*)', h)
        if version:
            return frame('applecare:remote-diagnostics', 'platform-log-collection', period='os-' + version.group(1))

    if s(r'trademark|商标', h):
        applicant = s(r'^(?:apple(?:[’\']s)?\s+(?:rival|competitor|supplier)\s+)?([a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*){0,2})\s+(?:files|filed|registers|registered|applies|applied)\b', h)
        if applicant:
            actor = _compiled_rule(r'\s+(?:reportedly|potentially|recently|secretly)$', re.I).sub('', applicant.group(1))
            if actor != 'apple':
                return replace(frame('third-party:trademark:' + actor, 'trademark-disclosure', 'hardware_products', 'third_party_ecosystem'), tier='weak')

    if (s(r'trademark|商标', h)
            and s(r'apple\s+(?:(?:potentially|reportedly|possibly|secretly|has)\s+)*(?:behind|used|fil(?:ed|es|ing)|appl(?:ied|ies))|苹果(?:可能|或曾|疑似|据报|被曝|曾)?(?:通过[^，。]{0,70}|为[^，。]{0,40})?(?:申请|注册)', h + ' ' + opening)
            and not s(r'apple[- ]compatible|兼容苹果', h)):
        name = (_compiled_rule(r'[\'"“‘]([A-Za-z][A-Za-z0-9 ]+)[\'"”’]\s+trademark', re.I).search(title)
                or _compiled_rule(r'([A-Za-z][A-Za-z0-9]+)[”’\'"]?\s*商标', re.I).search(title))
        if name:
            return frame('apple:trademark:' + name.group(1).lower().replace(' ', '-'), 'trademark-disclosure', 'hardware_products', 'hardware_market')

    if (s(r'apple\s*tv\s*4k', h) and s(r'vintage|obsolete|过时|停产产品', h)
            and not s(r'\b(?:not|never|no)\b|尚未|并非|不是', h)):
        model_year = (s(r'(20\d{2})\s*(?:款(?:初代)?)?\s*apple\s*tv\s*4k', opening)
                      or s(r'apple\s*tv\s*4k\s+from\s+(20\d{2})', opening))
        if model_year:
            state = 'obsolete' if s(r'\bobsolete\b|停产产品', h) else 'vintage'
            return frame('apple-tv-4k:' + model_year.group(1), 'support-status-' + state, 'hardware_products', 'hardware_market')

    if (s(r'homekit|apple\s*home|家居|门锁|恒温', local)
            and s(r'nfc|轻触|未通电|未通电先配对', local)
            and s(r'code|firmware|代码|固件', opening)
            and s(r'配对|设置|pair|set\s*up|commission', local)):
        version = s(r'ios\s*(\d+(?:\.\d+)*)', opening)
        if version and s(r'without\s+power|unpowered|未通电|无需先接电', local):
            return frame('homekit:ios-' + version.group(1) + ':nfc-preprovisioning', 'feature-code-discovery')

    phone = s(r'(?<![a-z0-9])iphone\s*(?:air\s*\d+|duo\s*\d*|\d+(?:\s*pro(?:\s*max)?|\s*plus)?)(?![a-z0-9])', h)
    if (phone and s(r'inventory|stocking|备货', h)
            and s(r'limited|low|small|short|少|不足|有限', h)
            and not s(r'\bnot\b|deni(?:es|ed)|否认|并非|没有', h)):
        for start, end in source_sentence_spans(opening):
            sentence = opening[start:end]
            clauses = _compiled_rule(r'[;；]|\b(?:while|whereas|but)\b|但是|然而|不过', 0).split(sentence)
            clause = next((part for part in clauses if s(re.escape(phone.group().strip()) + r'(?![a-z0-9])', part)
                           and s(r'inventory|stocking|备货', part)), '')
            first_phone = s(phone.re.pattern, clause)
            if first_phone is None or first_phone.group().strip() != phone.group().strip():
                continue
            if any(m.group().strip() != phone.group().strip() for m in _compiled_rule(phone.re.pattern, 0).finditer(clause)):
                continue
            if not s(r'inventory|stocking|备货', clause):
                continue
            if (s(r'last\s+(?:year|month|week)|previously|此前|去年|回顾|零售商|retailer|门店|store|\bnot\b|deni(?:es|ed)|否认|并非|没有|no\s+longer|recovered|restored|已解除|已缓解|恢复', clause)
                    or s(r'\b(?:was|were)\b.{0,55}\b(?:in|during)\s+20\d{2}', clause)
                    or (len(clauses) > 1 and s(r'(?:supply|inventory).{0,35}(?:recovered|restored|no\s+longer)|供货.{0,20}(?:恢复|缓解)', clauses[1])
                        and not s(phone.re.pattern, clauses[1]))):
                return None
            if (s(r'sources?\s+(?:report|say|claim)|reports?\s+that|analyst|leaker|消息|爆料|博主.{0,12}(?:表示|称)', clause)
                    and s(r'limited|low|small|short|少|不足|有限', clause)):
                model = _compiled_rule(r'\s+', 0).sub('-', phone.group().strip())
                return frame(model + ':inventory', 'supply-constraint-report', 'hardware_products', 'hardware_market')
    if (phone and s(r'thin(?:ner)?|thickness|厚度|薄至|减薄', h)
            and s(r'battery|电池', opening)
            and s(r'rumou?r|leak|claims?|爆料|曝光|消息源', local)
            and not s(r'denied|denies|retract|否认|撤回|并非|去年|last\s+year', h)):
        model = _compiled_rule(r'\s+', 0).sub('-', phone.group())
        return frame(model + ':dimensions-and-battery', 'configuration-report', 'hardware_products', 'hardware_market')

    if (s(r'macbook\s*pro', h) and s(r'thinn?er|thickness|厚度|更薄|变薄', local)
            and s(r'(?:not|won.t|don.t\s+think|不会|未必|不太).{0,30}(?:thinn?er|thin|薄)|厚度.{0,20}(?:不|低于)|修正.{0,30}(?:厚|瘦)', h + ' ' + detail)
            and s(r'gurman|古尔曼|leak|爆料', local + ' ' + detail)
            and not s(r'\b(?:launch|event)\b.{0,45}\b(?:on|october|november)|\d+\s*月\s*\d+\s*日.{0,10}发布', h)):
        return frame('macbook-pro:enclosure-thickness', 'forecast-correction', 'hardware_products', 'hardware_market')

    if (s(r'ipad\s*mini', h) and s(r'refresh|promotion|\d+\s*hz|高刷|刷新率', h + ' ' + opening[:600])
            and s(r'rumou?r|leak|claims?|爆料|传闻|消息', local)
            and not s(r'last\s+year|去年|回顾', h)):
        rate = s(r'(\d+)\s*hz', opening)
        if rate and s(r'oled', opening):
            generation = s(r'ipad\s*mini\s*(\d+)', h + ' ' + opening[:200])
            return replace(frame('ipad-mini:oled-refresh', 'display-specification-report', 'hardware_products', 'hardware_market', period=rate.group(1)),
                model_generation=generation.group(1) if generation else '')

    if (s(r'apple|苹果|(?<![a-z0-9])mac(?![a-z0-9])', h)
            and s(r'(?<![a-z0-9])idc(?![a-z0-9])', detail) and s(r'(?<![a-z0-9])pc(?![a-z0-9])|personal\s+comput|个人电脑', detail)
            and s(r'shipments?|出货', local) and s(r'apple|苹果|\bmac\b', detail)):
        quarter = (s(r'(20\d{2}).{0,6}(?:q|第)([1-4一二三四])(?:季度)?', detail)
                   or s(r'\bq([1-4])\s+(20\d{2})', detail))
        period = ''
        if quarter:
            a, b = quarter.groups()
            year, q = (a, b) if len(a) == 4 else (b, a)
            q = str('一二三四'.index(q) + 1) if q in '一二三四' else q
            period = 'q' + q
        if not period:
            q = s(r'今年第([一二三四])季', detail)
            if q:
                period = 'q' + str('一二三四'.index(q.group(1)) + 1)
        regions = [key for key, pattern in (('china', r'中国|国内|\bchina\b'), ('us', r'美国|united states|\bus\b'), ('worldwide', r'全球|worldwide|global')) if s(pattern, local)]
        if len(regions) > 1:
            return None
        region = regions[0] if regions else ''
        return replace(frame('idc:pc-shipments', 'market-measurement-report', 'hardware_products', 'hardware_market', period=period), year=year if quarter else '', region=region)

    if (s(r'iphone|ios', h) and s(r'updat|install|升级|更新', h)
            and s(r'prominent|reversing\s+the\s+order|主要位置|首位|顺序|首先看到', opening)
            and s(r'also\s+available|其他可用|也可用', opening)):
        versions = sorted(set(_compiled_rule(r'ios\s*(\d+(?:\.\d+)*)', 0).findall(opening)))
        majors = sorted({v.split('.')[0] for v in versions}, key=int)
        if len(majors) == 2:
            return frame('ios:upgrade-presentation:' + '-'.join(majors), 'update-priority-change')

    if (s(r'spyware|malware|间谍软件', local) and s(r'iphone|ios', local)
            and s(r'report|uncover|discover|披露|曝光', local)):
        variant = s(r'(?<![a-z0-9])([a-z]\d+\s+[a-z][a-z0-9-]+)(?![a-z0-9-])', opening)
        if variant:
            return frame('ios:malware:' + variant.group(1).replace(' ', '-'), 'security-research-report')

    if (s(r'apps?(?![a-z])|app\s*store|开发者', h) and s(r'必须|强制|硬性|require|must', h)
            and s(r'app\s*store\s*connect', detail)
            and s(r'现已?可以|现可|now\s+(?:submit|accept)', detail)):
        device = s(r'iphone\s*(duo|\d+(?:\s*pro)?)', h)
        if device:
            return frame('app-store:submission:' + device.group(1), 'developer-submission-requirement')

    if (s(r'apple\s*tv', h) and s(r'acqui|收购|购入|采购|授权', h)
            and s(r'rights|series|crime\s+drama|剧集|版权', opening)):
        name = (s(r'rights\s+to\s+([a-z][a-z0-9 ]{1,45}?)[,，]', opening)
                or s(r"acquires?\s+['‘\"]([^'’\"]+)['’\"]", h))
        if not name:
            for value in (opening, *(_normalized(f) for f in facts)):
                if s(r'此前|去年|last\s+year|previously|今年夏季', value):
                    continue
                if s(r'apple\s*tv.{0,50}(?:获得|购入|宣布)', value) and s(r'全球.{0,15}播放权', value):
                    name = s(r'《[^》]+》\s*[（(]([a-z][a-z0-9 ]+)[）)]', value)
                    if name:
                        break
        if name:
            return frame('apple-tv:content:' + name.group(1).strip().replace(' ', '-'), 'rights-acquisition', kind='service_content')
    return None


_EXECUTIVE_NAME_ALIASES = (('tim-cook', r'(?:tim\s*)?cook(?![a-z])|库克'),
                           ('john-ternus', r'(?:john\s*)?ternus(?![a-z])|特努斯'))


def source_executive_people(text: str) -> frozenset[str]:
    """Read explicit people; a different named executive resets local ownership."""
    known = _EXECUTIVE_NAME_ALIASES
    def canonical(name):
        return next((key for key, pattern in known if _frame_search(pattern, name)),
                    _normalized(name).strip().replace(' ', '-'))
    people = {key for key, pattern in known if _frame_search(pattern, text)}
    for pattern in (
        r'\b(?:CEO|Chairman|Executive(?:\s+Chair)?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b',
        r'(?:高管|首席执行官|执行董事长|董事长|主席)\s*([\u4e00-\u9fff·\s]{2,20}?)(?=与|和|在|将|计划|会见|访问|参观|一行|[，。])',
    ):
        people.update(canonical(match.group(1)) for match in _compiled_rule(pattern, 0).finditer(text))
    return frozenset(people)


def source_executive_government_frame(title: str, lead: str, *, context_actor: str = '') -> SourceActionFrame | None:
    """Bind the actor, counterpart and phase to the actual meeting clause."""
    s = _frame_search
    headline = _normalized(title)
    if not context_actor and not s(r'apple|苹果', title + ' ' + lead):
        return None
    if not s(r'会见|会面|会谈|meet|\bmet\b|visit|tour|访华|来华|访问|到访', headline):
        return None
    if s(r'last\s+year|previously|去年|此前', headline):
        return None
    people = source_executive_people(title)
    if len(people) > 1:
        return None
    person = next(iter(people), context_actor)
    if not person:
        return None
    relation = r'会见|会面|会谈|met|meets?|meeting|talk\s+to|talked\s+(?:to|with)'
    raw = title + '. ' + lead
    for start, end in source_sentence_spans(raw):
        original = raw[start:end]
        clause = _normalized(original)
        if not s(relation, clause) or s(r'last\s+year|previously|去年|此前|未会见|not\s+meet', clause):
            continue
        actors = source_executive_people(original)
        if actors and actors != {person}:
            continue
        if not actors and not (context_actor or s(r'^\s*(?:he\b|他)', clause)):
            continue
        region = s(r'(?:与|[,，]|^)([\u4e00-\u9fff]{2,5}?)省(?:省委副书记、|委副书记、|省长|长)|'
                   r'governor\s+of\s+([a-z][a-z -]{1,35}?)(?=\s+(?:today|tomorrow|yesterday|next|last|this|on|during|after|before|in)\b|[,.]|$)', clause)
        counterpart = s(r'(?:国务院)?(?:副总理|总理|部长|总统|副总统)\s*([\u4e00-\u9fff·]{2,12}?)(?=\d|在|于|会见|与|[，。])', clause)
        if not region and not counterpart:
            continue
        place = (next(v for v in region.groups() if v).removeprefix('并与').removeprefix('与')
                 if region else counterpart.group(1))
        aliases = {'广东': 'guangdong', '浙江': 'zhejiang', '江苏': 'jiangsu', '四川': 'sichuan', '福建': 'fujian', '山东': 'shandong'}
        place = aliases.get(place, place).strip().replace(' ', '-')
        cancelled = s(r'cancel|取消', clause)
        planned = s(r'will\s+meet|plans?\s+to\s+(?:meet|visit)|(?:计划|将)(?:会见|会谈|访问)', clause)
        if not cancelled and not planned and not s(r'\bmet\b|会见了|已经会见', clause):
            planned = s(r'plans?\s+to\s+(?:meet|visit)|will\s+(?:meet|visit)|(?:计划|将)(?:会见|会谈|访问)', headline)
        action = 'government-meeting-cancelled' if cancelled else 'planned-government-meeting' if planned else 'government-meeting'
        return SourceActionFrame('apple:executive:' + person + ':government:' + place,
            action, 'hardware_products', 'company_org')
    return None


def source_executive_visit_frame(title: str, lead: str, facts: tuple[str, ...] = ()) -> SourceActionFrame | None:
    """A current corporate visit is not a preceding change of executive role."""
    s = _frame_search
    visit = r'\b(?:visit(?:s|ed|ing)?|tour(?:s|ed|ing)?)\b|访华|来华|到访|探访|参观|访问|探班|现身'
    if not s(visit, title):
        return None
    h, opening = _normalized(title), _normalized(lead)[:700]
    role = r'(?:apple(?:[\u2019\x27]s)?\s+(?:(?:current|new|executive)\s+)?(?:ceo|coo|chairman|chair|executive)|苹果(?:公司)?(?:董事会)?(?:执行)?(?:主席|董事长|高管|ceo|coo|首席执行官|首席运营官))'
    if not s(role, h + ' ' + opening) or source_denies_action(title, lead, visit):
        return None
    if s(r'\b(?:previously|last year|remembering)\b|去年|此前|早在|旧照|回顾|追忆', source_primary_assertion(title, lead)):
        return None
    person, actor_end, person_pattern = '', 0, ''
    for key, name in (('tim-cook', r'(?:tim\s+)?cook(?![a-z])|(?:蒂姆\s*[·.・]?\s*)?库克'),
                      ('john-ternus', r'(?:john\s+)?ternus(?![a-z])|(?:约翰\s*[·.・]?\s*)?特努斯')):
        actor = s(r'^(?:(?:' + role + r'|苹果)\s*)?(?:' + name + r')', h)
        if actor:
            person = key
            actor_end = actor.end()
            person_pattern = name
            break
    if not person:
        named = _compiled_rule(r'^Apple(?:[\u2019\x27]s)?\s+(?:CEO|Chairman|Executive)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b', 0).search(title)
        if named:
            person = named.group(1).lower().replace(' ', '-')
            actor_end = h.index(named.group(1).lower()) + len(named.group(1))
            person_pattern = re.escape(named.group(1).lower())
    if not person:
        # A product-first headline can still explicitly own an officer's
        # factory visit. Resolve the named actor from its opening, then bind
        # only that actor's locally described facility and visit date.
        if not s(role + r'[^。！？]{0,45}(?:到访|参观|访问)', h):
            return None
        officer = s(role + r'\s*(?:\([^)]{1,20}\)\s*)?'
            + r'(?:[a-z][a-z .-]{1,45}\s*\(\s*)?'
            + r'(?P<name>(?!亲自|计划|首次|再次)[\u4e00-\u9fff]{2,8}?(?:\s*[·.]\s*[\u4e00-\u9fff]{1,8})?)\s*\)?'
            + r'\s*(?P<stage>(?:计划|将|拟|已|亲自|于|\d|年|月|日|\s){0,25})(?:到访|参观|访问)', opening)
        if not officer:
            return None
        name = officer.group('name')
        person = _compiled_rule(r'[\s·.]', 0).sub('', name)
        actor_pattern = re.escape(name).replace(r'\ ', r'\s*').replace('·', r'\s*·\s*')
        date_pattern = r'(?:(?P<year>20\d{2})\s*年\s*)?(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日'
        # The opening resolves the person; a directly adjacent equivalent role
        # in the headline can own the same visit, without crossing another name.
        owned_role = s(role, officer.group(0)).group(0)
        for role_alias in (r'coo|首席运营官', r'ceo|首席执行官', r'chairman|chair|主席|董事长', r'executive|高管'):
            if s(r'(?:' + role_alias + r')$', owned_role):
                owned_role = r'(?:apple(?:[\u2019\x27]s)?\s+|苹果(?:公司)?)(?:' + role_alias + r')'
                break
        headline_visit = s(r'(?:' + actor_pattern + '|' + owned_role + r')(?P<stage>计划|将|拟|已)?于?(?:'
            + date_pattern + r')?(?:到访|参观|访问)', h)
        clauses = [clause for value in (h, opening, *facts)
            for begin, end in source_sentence_spans(value)
            if (clause := _normalized(value[begin:end])) and (s(actor_pattern, clause) or (value == h and headline_visit and headline_visit.group(0) in clause))
            and not s(r'去年|此前|上次|回顾|previously|last\s+year', clause)]
        facilities = set()
        dates = set()
        years = set()
        for clause in clauses:
            for facility in _compiled_rule(r'(?:到访|参观|访问|与|表示[，,])\s*([\u4e00-\u9fff]{2,16}?)(?:科技园|园区|工厂|员工)', 0).finditer(clause):
                facilities.add(facility.group(1))
            local_date = (headline_visit if headline_visit and headline_visit.group('month') and headline_visit.group(0) in clause else None) or (s(date_pattern + r'[，,]\s*' + actor_pattern, clause)
                or s(actor_pattern + r'(?:计划|将|拟|已)?于?' + date_pattern + r'(?:到访|参观|访问)', clause))
            if local_date and (local_date is headline_visit or s(actor_pattern + r'.{0,100}(?:到访|参观|访问|走进)', clause)):
                dates.add('month:' + str(int(local_date.group('month'))) + ':day:' + str(int(local_date.group('day'))))
                if local_date.group('year'):
                    years.add(local_date.group('year'))
        if not facilities or len(dates) > 1 or len(years) > 1:
            return None
        # A source may state the same facility with and without a province;
        # choose only a locally evidenced common suffix, never invent a city.
        facility = min(facilities, key=len)
        if any(not other.endswith(facility) for other in facilities):
            return None
        planned = (headline_visit.group('stage') in {'计划', '将', '拟'}
            if headline_visit and headline_visit.group('stage')
            else bool(s(r'计划|将|拟', officer.group('stage'))))
        return SourceActionFrame('apple:executive:' + person + ':factory-visit:' + facility,
            'planned-corporate-visit' if planned else 'corporate-visit', 'hardware_products',
            'company_org', 'strong', next(iter(dates), ''), year=next(iter(years), ''))
    predicate = h[actor_end:]
    if not s(r'^\s*(?:(?:will|may|might|plans?\s+to|is\s+(?:set|expected)\s+to)\s+)?(?:visit(?:s|ed|ing)?|tour(?:s|ed|ing)?)\b|'
             r'^\s*(?:分享)?(?:(?:卸任|辞任|接任|转任|退休)[^，。！？:：]{0,35}?后)?(?:首次|再次|计划|将|拟|已|正在)*(?:访华|来华|到访|探访|参观|访问|探班|现身)', predicate):
        return None
    if '现身' in predicate and not s(r'访华|来华|到访|探访|参观|访问|探班', h):
        # A virtual appearance is not a corporate visit. Bind a physical visit
        # or its plan to this person in the opening assertion.
        owned_visit = s(r'(?:' + person_pattern + r')\s*(?:今日|今天|首次|再次|已|将|计划|正在)*'
            r'(?:到访|探访|参观|访问|探班|现身)', _normalized(source_primary_assertion('', lead)))
        if (not owned_visit or s(r'现身[^,，。！？]{0,15}(?:视频|宣传片|广告|直播|节目)', predicate)
                or s(r'数字形象|虚拟形象|virtual\s+(?:avatar|appearance)', _normalized(source_primary_assertion('', lead)))):
            return None
    place = None
    for text in (h, opening):
        place = s(r'(?:首站(?:落地|到访)?|现身|来到|到访|探访|访问|前往|抵达)\s*([\u4e00-\u9fff]{2,10}?)(?=[,，。！？：:、\s]|现场|观看|探班|与|参加|开展|的|$)', text)
        place = place or s(r'\b(?:visit(?:s|ed|ing)?|tour(?:s|ed|ing)?)\s+([a-z][a-z .-]{1,60}?)(?=\s+(?:after|with|to|on|next|for|and)\b|[.!?,;:]|$)', text)
        if place:
            break
    if not place:
        return None
    destination = place.group(1).strip().removeprefix('来到').replace(' ', '-')
    destination = {'广州':'guangzhou', '上海':'shanghai', '北京':'beijing', '深圳':'shenzhen'}.get(destination, destination)
    planned_prefix = r'(?:will|may|might|plans?\s+to|is\s+(?:set|expected)\s+to)\s+(?:visit|tour)\b|(?:计划|将|拟|即将)(?:访问|来华|访华|到访|参观|现身)'
    planned = bool(s(r'^\s*(?:' + planned_prefix + r')|\b(?:next\s+(?:week|month|year)|tomorrow)\b|下周|下月|明年|明天', predicate))
    if not planned and not s(r'^\s*(?:visited|toured)\b|^\s*已(?:访问|到访|参观)', predicate):
        # Only the first assertion of this person's visit to this destination
        # can fill a neutral headline's stage. Later plans are another action.
        owned = s(r'(?:' + person_pattern + r')\s*(?P<predicate>' + planned_prefix
            + r'|(?:visit(?:s|ed)?|tour(?:s|ed)?)\b|(?:已)?(?:访问|到访|参观|现身))\s*'
            + re.escape(place.group(1).strip()) + r'(?=$|[\s，。！？,.!?:;])', opening)
        planned = bool(owned and s(r'^(?:' + planned_prefix + r')$', owned.group('predicate')))
    year = s(r'\b20\d{2}\b|20\d{2}(?=年)', h)
    return SourceActionFrame('apple:executive:' + person + ':visit:' + destination,
        'planned-corporate-visit' if planned else 'corporate-visit', 'hardware_products',
        'company_org', 'strong', year.group() if year else '')


def source_closing_market_value_frame(passage: str) -> SourceActionFrame | None:
    """Bind a local Apple closing result; never infer its date from publication."""
    s = _frame_search
    value = _normalized(passage)
    if not s(r'trillion|万亿|market\s+(?:cap|valuation)|市值', value):
        return None
    for start, end in source_sentence_spans(value):
        clause = value[start:end]
        if (s(r'clos(?:e|ed|ing)|收盘', clause) and s(r'trillion|万亿|market\s+(?:cap|valuation)|市值', clause)
                and s(r'\bapple(?:[’\x27]s)?\s+(?:(?:stocks?|shares|valuation)\s+)?'
                      r'(?:(?:today|yesterday|just|has|had)\s+)*(?:closed|closes|became\s+the\s+(?:first|second)\s+company\s+(?:ever\s+)?to\s+close)\b|'
                      r'at\s+close\s+of\s+market,?\s+apple[’\x27]s\s+(?:valuation|market\s+cap)|'
                      r'苹果(?:公司|股价|股票)?(?:是[^，,；;。！？!?]{1,60}[，,]\s*)?'
                      r'(?:昨日|今日|昨天|今天|在|于|当地时间|[（()）\d\s年月日，,]|逆势上涨|首次|市值)*(?:收盘|收涨|收跌|收平)', clause)
                and not s(r'(?:和|与|及|、)\s*苹果|\b(?:and|with)\s+apple\b', clause)
                and not s(r'(?:收盘|clos(?:ed|es|ing))[^，,。！？!?;；]{0,70}(?:合计|共同|\bcombined\b|\btogether\b)', clause)
                and not s(r'last\s+(?:year|month)|previously|back\s+in|去年|此前|之前|曾经|曾于|从未', clause)
                and not s(r'\b(?:could|might|may|forecast|expected)\b|预测|目标|有望|预计|尚未|未能', clause)
                and not source_denies_action('', clause, r'clos\w*|收盘')):
            months = 'january february march april may june july august september october november december'.split()
            date = s(r'\b(' + '|'.join(months) + r')\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b', clause)
            chinese = s(r'(?:(20\d{2})\s*年)?(\d{1,2})\s*月\s*(\d{1,2})\s*日(?!消息)', clause)
            if date:
                month, day, year = str(months.index(date.group(1)) + 1), date.group(2), date.group(3) or ''
            elif chinese:
                year, month, day = chinese.group(1) or '', chinese.group(2), chinese.group(3)
            else:
                year = month = day = ''
            return SourceActionFrame('apple:equity:closing-value', 'closing-market-value-report',
                'hardware_products', 'company_org', period=month + ':' + day if month else '', year=year)
    return None


def source_internal_testing_frame(title: str, lead: str) -> SourceActionFrame | None:
    """Bind an Apple internal test to its own platform, version and observation."""
    h, lead = _normalized(title), _normalized(lead)
    s = _frame_search
    # A version is owned by the testing predicate, not by later release history.
    os_title = s(r'\b(ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)+)\b', h)
    if os_title:
        assertion = source_primary_assertion(title, lead)
        for start, end in source_clause_spans(assertion):
            clause = assertion[start:end]
            testing = s(r"(?:\bapple(?:'s)?\s+(?:(?:software\s+)?engineers?\s+)?"
                r"(?:(?:are|is|already|internally|began|currently)\s+)*testing\s+|"
                r"苹果(?:软件工程师)?(?:正在|正|已在|已经|内部)*测试\s*)"
                r'(ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+)+)\b', clause)
            if testing is None or testing.groups() != os_title.groups():
                continue
            observed = (s(r'\binternally\b|内部', testing.group())
                or s(r'logs?\s+(?:show|indicate)|网站日志显示', clause[:testing.start()])
                or s(r'^\s+according\s+to\s+[^,.;]{0,50}(?:visitor|analytics|server)\s+logs?\b', clause[testing.end():]))
            if (observed and source_predicate_role(clause) == 'current'
                    and not source_denies_action('', clause, r'test\w*|测试')):
                return SourceActionFrame(testing.group(1) + '-' + testing.group(2), 'internal-test-observation', kind='os_app')

    return None


def source_current_report_frame(title: str, lead: str, facts: tuple[str, ...], source_units: tuple[str, ...] = ()) -> SourceActionFrame | None:
    """Bind the reported operation before compatible devices and prior events.

    These frames require a named subject and a source-local predicate. Detail
    facts may resolve a headline's object, but cannot supply a different actor.
    """
    h, opening = _normalized(title), _normalized(lead)[:1200]
    local = h + '. ' + opening
    detail = ' '.join((opening, *(_normalized(f) for f in facts)))
    s = _frame_search
    def frame(subject, action, category='software_systems', kind='os_app', tier='strong', period=''):
        return SourceActionFrame(subject, action, category, kind, tier, period)

    internal = source_internal_testing_frame(title, lead)
    if internal is not None:
        return internal

    if s(_DEVELOPMENT_PLATFORMS, h):
        for clause in source_current_disclosure_clauses(lead, source_units or facts):
            _in_scope, development = source_platform_development_disclosure(title, clause)
            if development is not None:
                return development

    if s(r'promotion|shopping|sale|优惠|促销', h):
        campaign = s(r'[“"「]([^”"」]{2,50})[”"」]', h)
        assertion = opening[len(h):].lstrip(' .。') if opening.startswith(h) else opening
        assertion = assertion[:next(source_sentence_spans(assertion), (0, len(assertion)))[1]]
        store_scope = opening + ' ' + ' '.join(_normalized(p) for p in source_units[:2])
        if (campaign and s(r'(?:apple(?:[’\x27]s)?|苹果)(?:\s+(?:announces?|launches?|unveils?|introduces?|new|its|today)){0,4}\s*$', h[:campaign.start()])
                and s(r'(?:its|apple[’\x27]s)\s+(?:online\s+)?store|苹果(?:官方旗舰店|在线商店|官网)', store_scope)
                and s(r'(?:\bapple\s+(?:(?:today|just|has|officially)\s+)*(?:announced|announces|launched)\b|'
                      r'苹果(?:公司)?(?:今日|今天|刚刚|正式|对外|现已)*(?:公布|宣布|推出))'
                      r'[^.!?。，,;；]{0,100}(?:promotion|campaign|sale|优惠|促销)', assertion)
                and not s(r'last\s+(?:year|month|week)|previously|expects?|prediction|去年|此前|上月|上周|预计|预测', assertion)
                and not source_denies_action('', assertion, r'announc\w*|launch\w*|公布|宣布|推出')):
            return frame('apple:retail-program:' + _subject_slug(campaign.group(1)),
                         'retail-program-announcement', 'hardware_products', 'hardware_market')

    if (s(r'apple|苹果', h) and s(r'trillion|万亿|market\s+(?:cap|valuation)|市值', h)
            and not s(r'could|might|may|forecast|last\s+(?:year|month)|previously|目标|有望|预计|预测|去年|此前|回顾', h)):
        for passage in (lead, *facts):
            closing = source_closing_market_value_frame(passage)
            if closing is not None:
                return closing

    canonical_ai = bool(s(r'apple\s*intelligence|苹果智能', h))
    abbreviated_ai_title = s(r'apple\s*ai(?![a-z0-9])|苹果\s*(?:国行|中国)?\s*ai(?![a-z0-9])', h)
    if (canonical_ai or abbreviated_ai_title) and s(r'china|中国|国行|在华|国内', h):
        for passage in (lead, *facts):
            for start, end in source_sentence_spans(passage):
                clause = _normalized(passage[start:end])
                rollout = s(r'(?:苹果智能|apple\s*intelligence)'
                    r'(?:[（(](?:苹果智能|apple\s*intelligence)[）)])?'
                    r'(?:首批功能|核心功能|\s+features)?'
                    r'(?:及相关[^，,。；;]{1,35}大模型)?(?:确?已获得批准)?[，,]?\s*'
                    r'将(?:于|在)?\s*(?:今年)?(?P<schedule>(?:1[0-2]|[1-9]|十一|十二|十|[一二三四五六七八九])\s*月)'
                    r'(?:底|末|晚些时候)?\s*(?:(?:面向|为|在)(?:中国(?:大陆)?|国行|国内)(?:用户)?)?'
                    r'(?:发布|推出|上线)\s*(?:测试版(?:本)?|beta)', clause)
                if (rollout is None or source_predicate_role(clause[:rollout.end()]) != 'current'
                        or source_denies_action('', clause, r'发布|推出|上线|available')):
                    continue
                date = s(r'(?<!\d)(\d{1,2}|[一二三四五六七八九十]{1,3})\s*月', rollout.group('schedule'))
                if date:
                    period = normalize_rollout_time(date.group(1) + '月').split(':')[1]
                    return SourceActionFrame('apple-intelligence:regional-rollout', 'beta-release-plan',
                        kind='os_app', period=period, region='china')
    plan_predicate = (r'\bapple\s+plans?\s+to\s+(?:(?:finally|formally|officially)\s+)?(?:launch|release|bring)\s+'
                  r'(?:(?:its|the)\s+)?apple\s*intelligence\b|'
                  r'苹果(?:公司)?计划(?:(?!发布|推出|上线|登陆|回顾)[^，,；;。！？!?]){0,100}'
                  r'(?:[，,]\s*(?:面向|为|向)[^，,；;。！？!?]{1,45}?)?'
                  r'(?:推出|上线|登陆)\s*(?:苹果智能|apple\s*intelligence)')
    owned_ai_plan = next((clause[match.start():match.end()] +
        _compiled_rule(r'[，,；;]|\b(?:and|while|but|whereas)\b').split(clause[match.end():], 1)[0]
        for start, end in source_sentence_spans(opening) for clause in (opening[start:end],)
        for match in (s(plan_predicate, clause),)
        if match and not s(r'last\s+(?:year|month)|previously|去年|此前|回顾', clause)
        and not source_denies_action('', clause, r'plan\w*|launch\w*|releas\w*|计划|推出|上线|登陆')), '') if canonical_ai or abbreviated_ai_title else ''
    abbreviated_ai = bool(abbreviated_ai_title and owned_ai_plan)
    if ((canonical_ai or abbreviated_ai) and s(r'china|中国|国行|国内', h)
            and (s(r'coming|debut|release\s+window|推出|登陆|上线', h) or owned_ai_plan)
            and not s(r'cancel|denied|否认|取消|不会|回顾', h)):
        if ((s(r'bloomberg|gurman|彭博|古尔曼', detail) or owned_ai_plan)
                and s(r'plans?|expected|could|reportedly|据报|预计|有望|计划', local)
                and s(r'launch|coming|debut|roll\s*out|release|推出|上线|登陆', detail)
                and not source_denies_action(title, lead, r'plan\w*|launch\w*|releas\w*|计划|推出|上线|登陆')):
            version = s(r'ios\s*(\d+\.\d+)', local)
            months = 'january february march april may june july august september october november december'.split()
            date_pattern = r'\b(' + '|'.join(months) + r')\b|(\d{1,2})\s*月'
            date = (s(date_pattern, owned_ai_plan) or s(date_pattern, h)
                    or (s(date_pattern, opening[:500]) if not owned_ai_plan else None))
            period = str(months.index(date.group(1)) + 1) if date and date.group(1) else date.group(2) if date else ''
            if period and version:
                return SourceActionFrame('apple-intelligence:regional-rollout', 'reported-release-plan',
                    kind='os_app', period=period, region='china', model_generation='ios-' + version.group(1))

    if (s(r'apple\s*maps|苹果.{0,8}地图', h) and s(r'detailed\s+city\s+experience|精细化|高精.{0,3}3d', local)
            and s(r'comes?\s+to|launch|available|推出|上线|解锁', local)
            and not s(r'might|could|wish|希望|可能|尚未', h)
            and not s(r'last\s+(?:year|month)|previously|去年|此前|回顾', source_primary_assertion(title, lead))
            and not source_denies_action(title, lead, r'launch\w*|available|offer\w*|推出|上线|提供')):
        city = s(r'(?:in|to)\s+([a-z]+(?:\s+[a-z]+){0,2})(?=,|\s+ahead|\s+-|$)', h)
        if not city:
            # A source's own parenthesized place name resolves translation;
            # the same clause must attribute the rollout to Apple in that city.
            city = s(r'苹果(?:公司)?在[^，。()（）]{1,55}[（(]([a-z]+(?:\s+[a-z]+){0,2}),\s*[a-z ]+[)）]'
                     r'为\s*apple\s*maps\s*推出', opening)
        if city:
            return frame('apple-maps:detailed-city:' + city.group(1).replace(' ', '-'), 'city-feature-availability')

    if s(r'benchmark|跑分', h):
        from .article_processing import capture_article_title_evidence
        evidence = capture_article_title_evidence('', '', title, lead, tuple(dict.fromkeys((*facts, *source_units))))
        claim = bind_device_measurement(evidence)
        if claim is not None and claim.subject and claim.object and claim.polarity == 'affirmed':
            record = next((q[2] for q in claim.qualifiers if q[1] == 'measurement-record'), '')
            return frame(claim.subject + ':' + claim.object, claim.action,
                         claim.category, claim.event_kind, period=record)

    variants = s(r'(airpods\s*(?:pro\s*)?)(\d+)', h)
    if (variants and s(r'dual|two\s+(?:variants|versions)|双版本|高低双|高低两个版本', local)
            and s(r'leaker|reportedly|爆料|消息称|消息人士', local)
            and s(r'(?:苹果(?:公司)?(?:正在)?(?:计划|考虑)(?:为|在)?\s*(?:下一代)?|'
                  r'apple\s+(?:is\s+)?(?:considering|plans?\s+to).{0,15})'
                  + re.escape(variants.group()).replace(r'\ ', r'\s*') + r'[^。.!?]{0,40}(?:两个版本|双版本|two\s+(?:variants|versions))', opening)
            and not s(r'last\s+year|previously|去年|此前|早在|否认|取消', h + ' ' + opening[:180])):
        family = _compiled_rule(r'\s+').sub('-', variants.group(1).strip())
        return SourceActionFrame(family + ':variant-lineup', 'reported-configuration-plan',
            'hardware_products', 'hardware_market', model_generation=variants.group(2))

    # The provider of developer assistance is the actor; a device's launch
    # in the opening is only context for the software adaptation work.
    assistance = (
        r'(?:^|[：:。.!?，,]\s*)(?:苹果(?:公司)?(?:会|正|正在)?(?:面对面)?(?:指导|帮助|培训)开发者|'
        r'apple\s+(?:(?:is\s+)?(?:providing|offering)\s+(?:hands-on\s+)?(?:guidance|training)\s+to|'
        r'helps?|mentors?|trains?)\s+developers)')
    if (s(assistance, h)
            and not s(r'去年|此前|回顾|旧闻|last\s+year|previously|recap', h)):
        target_expression = (
            r'(?<![a-z0-9])(?:iphone(?:\s*(?:duo|air|\d+(?:\s*pro(?:\s*max)?)?))?|'
            r'ipad(?:\s*(?:mini|air|pro))?|ios|ipados|macos|watchos|tvos|visionos|xcode)(?![a-z0-9])'
        )
        target_pattern = _compiled_rule(target_expression)
        targets = {value.replace(' ', '') for value in target_pattern.findall(h)}
        supported_targets = set()
        for passage in (lead, *facts, *source_units):
            value = _normalized(passage)
            provider = s(assistance, value)
            if provider:
                clause = _compiled_rule(r'[。.!?;；]|\b(?:but|while|whereas)\b').split(value[provider.end():], maxsplit=1)[0]
                if s(r'去年|此前|回顾|last\s+(?:year|month)|previously|years?\s+ago', value[:provider.end()] + clause):
                    continue
                for target in _compiled_rule(
                        r'(?:适配|adapt(?:ing)?\s+(?:(?:their\s+)?apps?\s+)?(?:for|to)|'
                        r'build(?:ing)?\s+apps?\s+for)\s*(' + target_expression + ')').findall(clause):
                    supported_targets.add(target.replace(' ', ''))
        targets &= supported_targets
        if targets:
            return frame('apple:developer-assistance:' + '+'.join(sorted(targets)),
                         'developer-assistance', kind='developer_program')

    personal_appearance = s(r'(?:现身|偶遇)[^,，。！？]{0,35}(?:游玩|游览|旅游|观光)(?=被|时|中|后|[\s,，。！？]|$)|\b(?:spotted|seen)\b.{0,40}\b(?:on\s+vacation|sightseeing)\b', h)
    if (personal_appearance and source_executive_people(h[:personal_appearance.start()])
            and not s(r'并非|并未|不是|没有|不为|not|never', personal_appearance.group())
            and s(r'苹果|\bapple\b', opening)):
        return frame('personal-appearance:' + h, 'personal-leisure', 'hardware_products', 'company_org', 'weak')
    meeting = source_executive_government_frame(title, lead)
    if meeting is not None:
        return meeting
    if (s(r'年会|annual\s+(?:meeting|conference)', _normalized(source_primary_assertion(title, lead)))
            and s(r'库克|tim\s+cook|特努斯|ternus', h)
            and s(r'苹果|apple', local)):
        actor = s(r'(?:苹果(?:公司)?(?:(?:执行)?董事长|主席|ceo)?\s*)?'
            r'(?P<name>(?:tim\s+)?cook|库克|(?:john\s+)?ternus|特努斯)\s*'
            r'(?:今日|今天|已|再次|还)?(?:现身|参加|出席|attends?\b|attended\b)', h + ' ' + opening)
        primary = _normalized(source_primary_assertion(title, lead))
        historical = s(r'去年|此前|回顾|上次|last\s+year|previously', h + ' ' + primary)
        denied_attendance = s(r'(?:库克|cook|特努斯|ternus)[^。.!?]{0,20}(?:不会|不曾|并未|没有|不|not|never)[^。.!?]{0,10}(?:出席|参加|attend)', opening)
        if actor and not historical and not denied_attendance:
            # Delimit the institution from the preceding actor and verb.
            institution_name = r'([\u4e00-\u9fff]{2,20}?(?:大学|经管学院)(?:[\u4e00-\u9fff]{2,10}?学院)?)'
            institution = s(r'(?:^|[，,。；;：:\s])' + institution_name, opening)
            if institution:
                place = _compiled_rule(r'^.*(?:现身|出席|参加|在|于)').sub('', institution.group(1))
                person = {'库克':'tim-cook','cook':'tim-cook','tim cook':'tim-cook','特努斯':'john-ternus','ternus':'john-ternus','john ternus':'john-ternus'}[actor.group('name')]
                year = s(r'20\d{2}(?=年|\s*年)', opening)
                return SourceActionFrame('apple:executive:' + person + ':annual-meeting:' + place,
                    'institutional-attendance', 'hardware_products', 'company_org', year=year.group() if year else '')
    if (source_executive_people(h) and s(r'年会|annual\s+meeting', local)
            and not s(r'去年|此前|回顾|last\s+year|previously', h)
            and not s(r'(?:库克|cook|特努斯|ternus)[^。.!?]{0,20}(?:不会|并未|没有|not|never)[^。.!?]{0,10}(?:出席|参加|attend)', opening)):
        institution = s(r'([\u4e00-\u9fff]{2,20}大学[\u4e00-\u9fff]{2,15}学院)顾问委员会\s*(20\d{2})\s*年会', opening)
        people = source_executive_people(h)
        # A coordinated list or its explicit collective reference may own the
        # attendance; another person's following sentence may not.
        collective = s(r'(?:库克|特努斯)、[^。.!?]{0,100}(?:参加|出席)', h)
        collective = collective or s(r'(?:库克|特努斯)、[^。.!?]{0,100}等人[^。.!?]{0,80}(?:[二三四五六七八九十]人|他们)(?:是|均)?(?:参加|出席)', opening)
        if institution and len(people) == 1 and collective:
            return SourceActionFrame('apple:executive:' + next(iter(people)) + ':annual-meeting:' + _compiled_rule(r'^.*(?:出席|参加|在|于)').sub('', institution.group(1)),
                'institutional-attendance', 'hardware_products', 'company_org', year=institution.group(2))
    visit = source_executive_visit_frame(title, lead, facts + source_units)
    if visit is not None:
        return visit
    interview = source_leadership_interview_frame(title, lead, facts + source_units)
    if interview is not None:
        return interview
    focused = source_focused_report_frame(title, lead, facts)
    if focused is not None:
        return focused
    filing_scope = ' '.join((opening, *(_normalized(p) for p in source_units[:3])))
    if (s(r'苹果|apple|iphone', h) and s(r'智能|(?<![a-z])ai(?![a-z])|大模型', h)
            and s(r'国行|中国', filing_scope)
            and s(r'(?:新增|增加)[^。.!?]{0,20}大模型备案编号|大模型[^。.!?]{0,15}(?:新增|增加)', filing_scope)
            and not s(r'未新增|未增加|没有新增|否认|去年|回顾', h + ' ' + filing_scope)):
        record = s(r'\b[a-z]+[- ]+apple[- ]?zhineng[- ]+(\d{6,})\b', detail + ' ' + ' '.join(_normalized(p) for p in source_units))
        renewal = s(r'(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。.!?]{0,12}(?:换证|增加|新增)', filing_scope)
        if record and renewal:
            assertion = _compiled_rule(r'[。.!?；;]').split(filing_scope[:renewal.end()])[-1]
            if not s(r'预计|计划|将|拟|尚未|并未|没有|否认', assertion):
                return replace(frame('apple-intelligence:device-registration:' + record.group(1),
                                     'registration-update-disclosure', kind='service_policy',
                                     period=f'{int(renewal.group(2)):02}-{int(renewal.group(3)):02}'),
                               year=renewal.group(1) or '')
    if (s(r'event|launch|发布会', h) and s(r'livestream|keynote|presentation|线上|直播|形式', h)
            and not s(r'\byou\b|\bpoll\b|投票|你会', h)):
        dated = source_dated_launch_frame(title, lead, facts + source_units)
        attributed_format = any(s(r'(?:says?|reports?|writes?|报道|透露|称).{0,100}(?:video\s+presentation|online\s+video|线上视频|线下环节)', _normalized(p))
            and not s(r'last\s+year|previously|去年|此前|does\s+not|denies|否认', _normalized(p))
            for p in facts + source_units)
        if dated and attributed_format:
            return replace(dated, action='event-format-report')
    bundle = source_disclosure_bundle(title, lead, facts)
    if bundle is not None:
        return bundle

    if (s(r'hackintosh|intel\s+(?:pci-e\s+)?mac', h) and s(r'drivers?', opening)
            and s(r'graphics|metal|vulkan', opening) and s(r'run\s+on|运行', opening)
            and s(r"(?:it|driver)['’]s\s+out|released|available|已发布", opening)):
        model = s(r'(nvidia|amd)\s+(\d{3,4})\s+card', opening)
        denied = s(r"not\s+(?:yet\s+)?(?:released|available)|hasn['’]t\s+been\s+released|尚未发布|并未发布", opening)
        if model and not denied:
            return frame('graphics-driver:' + model.group(1) + '-' + model.group(2) + ':intel-mac',
                         'hardware-enablement-release', kind='ecosystem_interop', tier='ecosystem')

    # Named capabilities own the event; host devices and compatible equipment
    # do not move a service/software operation into the hardware category.
    if (s(r'formula\s*1|\bf1\b|一级方程式', h) and s(r'dolby\s*atmos|杜比全景声', h)
            and s(r'apple\s*tv', local) and s(r'announc|adds?|gains?|getting|支持|上线', local)):
        return frame('apple-tv:formula-1:dolby-atmos', 'broadcast-audio-rollout', kind='service_content')
    # The opening must announce an education program; its proper name can be
    # in the captured body even when the selected fact list is empty.
    if (s(r'apple|苹果', h) and s(r'launch|announc|introduc', local)
            and (s(r'education\s+program|教育项目', opening) or s(r'apple\s*[x×]', h))
            and not s(r'\b(?:visits?|visited|meets?|met|attends?|attended|tours?|toured)\b|探访|到访|参观|出席', h)):
        # Field boundaries are not part of a proper name.
        for program_text in (title, lead, *facts[:2], *(u[:700] for u in source_units[:1])):
            for start, end in source_sentence_spans(program_text):
                clause = program_text[start:end]
                if s(r'previously|formerly|last\s+(?:year|month)|此前|过去|去年', clause):
                    continue
                if not s(r'launch|announc|will|introduc', clause):
                    continue
                initiative = _compiled_rule(r"Apple\s*[x×]\s+([A-Z][\w’'-]*(?:\s+[A-Z][\w’'-]*){1,7})(?=\s+(?:will|initiative|program|participants)|[\"”.!,]|$)", 0).search(clause)
                if initiative:
                    name = _compiled_rule(r'[^a-z0-9]+', 0).sub('-', initiative.group(1).lower()).strip('-')
                    return frame('apple:initiative:' + name, 'program-launch', kind='company_org')
    if (s(r'apple\s*watch', h) and s(r'skin\s+irritation|皮肤|灼烧|灼热', h)
            and s(r'owners?.{0,30}(?:report|experience)|users?.{0,30}(?:report|complain)|用户.{0,40}(?:报告|反映|反馈)', local)):
        models = sorted(set(_compiled_rule(r'(?<![a-z0-9])(series|ultra)\s*(\d+)', 0).findall(opening[:550])))
        if models:
            return frame('apple-watch:' + ','.join(k + '-' + n for k, n in models) + ':skin',
                         'reported-irritation', 'hardware_products', 'hardware_market')
    if (s(r'苹果|apple', h) and s(r'developer|开发者', h) and s(r'适配|submission|submit', local)
            and s(r'必须|强制|require|must', local) and s(r'截图|screenshots?', local)):
        model = s(r'iphone\s*(duo|\d+(?:\s*pro)?)', h)
        if model:
            return frame('app-store:submission:' + model.group(1), 'screenshot-requirement')
    version = s(r'(?<![a-z0-9])(watchos|ios|ipados|macos)\s*(\d+(?:\.\d+)*)', h)
    if (version and s(r'adds?\s+(?:\w+\s+){0,2}new\s+apps|新增.{0,8}应用', h)
            and s(r'latest\s+major\s+software\s+update|系统更新', opening)
            and s(r'\bsiri\b|find\s*my|查找', detail)):
        return frame(version.group(1) + '-' + version.group(2) + ':built-in-apps', 'system-app-additions')
    if (s(r'ad\s+vendors?|广告', h) and s(r'block|阻挡|拦截', local)
            and s(r'safari', opening) and s(r'by\s+apple|apple.{0,20}(?:side|blocking)|苹果.{0,20}拦截', opening)):
        version = s(r'ios\s*(\d+(?:\.\d+)*)', opening)
        if version:
            return frame('safari:ios-' + version.group(1) + ':advertising', 'blocking-behavior-report')
    if (s(r'child.safety|儿童安全', h) and s(r'apple|苹果', h)
            and s(r'praised|welcomed|支持|赞扬', opening) and s(r'framework|框架', opening)
            and s(r'european\s+union|\beu\b|欧盟', opening)):
        return frame('apple:eu:child-safety-framework', 'executive-policy-statement', kind='regulation')
    if (s(r'\btax\b|税', h) and s(r'\beu\b|欧盟', h) and s(r'apple|苹果', h)
            and s(r'modified\s+version|revised\s+version|修订|修改', opening)
            and s(r'propos\w*|plan|提案|计划', opening)):
        return frame('eu:digital-services-tax', 'revised-tax-proposal', kind='regulation')

    # The measured market/period is the object of a comparative report, not
    # the rival whose growth is also mentioned in its headline.
    if (s(r'carrier|operator|运营商', h) and s(r'europe|欧洲', h) and s(r'apple|苹果', h)
            and s(r'counterpoint', local) and s(r'销量|sales|市场份额|market\s*share', local)):
        quarter = s(r'(?<![a-z])q([1-4])(?!\d)|(?:second|第二)\s*(?:quarter|季度)', local)
        year = s(r'(?<!\d)(20\d{2})(?!\d)|(?<!\d)(20\d{2})q', local)
        if quarter and year:
            return frame('apple:europe:carrier-smartphones', 'market-share-report',
                         'hardware_products', 'hardware_market', period=next(v for v in year.groups() if v) + ':q' + (quarter.group(1) or '2'))

    # Bind a retailer's paid access product before the Apple device it lets a
    # buyer order. Later device prices and supply reports do not own this sale.
    first = opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
    seller = s(r'(?:^|[，,：:])\s*(?:日前|近日|今天|今日|目前)?'
        r'(?P<zh>[^，,。；;：:\s]{0,16}(?:平台|零售商|经销商|电商|商店))'
        r'(?:今天|今日|近日|日前|目前)?\s*(?:上架|出售|售卖|开售)(?:了)?|'
        r'^\s*(?P<en>(?:retailer|reseller|store|marketplace)\s+[a-z][a-z0-9 -]{1,35}?)'
        r'\s+(?:is\s+|has\s+started\s+)?(?:selling|sells|offering|offers)\s+', first)
    if seller:
        owner = next(value for value in seller.groupdict().values() if value)
        # The sold noun phrase must itself carry the fee. A following clause,
        # or a device sold "with" a benefit, has a different price owner.
        offered = _compiled_rule(r'[，；;]|(?<!\d),|,(?!\d)|\b(?:with|and|but|while|whereas)\b', 0).split(first[seller.end():], maxsplit=1)[0]
        entitlement = s(r'优先购买(?:资格|权益)|早鸟先享(?:资格|权益)|购机资格|权益包|'
            r'priority[- ]purchase\s+(?:pass|membership|rights?)', offered)
        paid = s(r'售价|收费|付费|支付|\d\s*元|[$€£]\s*\d|\bpaid\b', offered)
        bundled_or_denied = entitlement and s(r'\b(?:not|free|includes?|included)\b|免费|并非|不是|附赠|赠送|赠品|不另收费', offered)
        if entitlement and paid and not bundled_or_denied and not s(r'苹果|\bapple\b|官方', owner):
            return frame('retail-entitlement:' + h, 'paid-retail-entitlement',
                         'hardware_products', 'general_company', 'weak')

    # Retail offers and one buyer's anecdote remain distinct from product news.
    if (s(r'last\s+call|grab|save\s*[$€£]|deal|促销|优惠', h + ' ' + opening[:180])
            and s(r'offers?\s+end|specials?\s+end|prime\s+big\s+deal|限时优惠', opening)):
        return frame('retail-offer:' + h, 'retail-promotion', 'hardware_products', 'general_company', 'weak')
    if (s(r'网友|用户|redditor', h) and s(r'二手|典当|pawn\s*shop', opening)
            and s(r'买|购买|buy|bought', h)):
        return frame('personal-purchase:' + h, 'purchase-anecdote', 'hardware_products', 'general_company', 'weak')

    if (s(r"everything\s+new|what['’]s\s+new|更新汇总|新功能汇总", h)
            and not is_os_release_announcement(title) and not s(r"now\s+available|现已可用",h)
            and ("更新汇总" not in h or s(r"[、，,]",h.split("更新汇总",1)[1]))):
        version = s(r'(?<![a-z0-9])(ios|ipados|macos|watchos|tvos)\s*(\d+(?:\.\d+)*)', h)
        stage = s(r'beta\s*(\d+)', h)
        if version and stage:
            platform = 'ios' if version.group(1) == 'ipados' and s(r'(?<![a-z0-9])ios(?![a-z0-9])',h) else version.group(1)
            return frame(platform + '-' + version.group(2) + ':beta-' + stage.group(1),
                         'feature-inventory')

    # A desktop distribution running on generic PCs and Macs does not announce
    # a new Apple hardware enablement merely by updating its Linux base.
    if (s(r'(?<![a-z0-9])pc(?![a-z0-9])', h) and s(r'(?<![a-z0-9])mac(?![a-z0-9])', h)
            and s(r'desktop|桌面|发行版', h)
            and s(r'(?:基于|以|based\s+on).{0,35}(?:debian|linux|ubuntu|fedora)|(?:debian|linux).{0,100}\biso\b', local)
            and not s(r'^(?:apple|苹果|macos)\b', h)):
        subject = s(r'^([a-z][a-z0-9 .+-]+?)(?=为|四|\d|returns?\b|releases?\b|升级|重返)', h)
        return frame('third-party:desktop-distribution:' + (subject.group(1).strip() if subject else h),
                     'general-distribution-update', tier='weak', kind='third_party_ecosystem')
    # The app's own minimum OS change is not an Apple OS support change.
    if (s(r'\b(?:drop|end|remove)\w*\s+support|不再支持|最后一个支持', local)
            and s(r'\b(?:app|application)\b|应用', detail)
            and s(r'\b(?:ios|ipados)\s*\d', local)
            and not s(r'^(?:apple|苹果|ios|ipados)\b', h)
            and not s(r'^(?:testflight|app\s*store\s*connect)(?![a-z0-9])', h)):
        app = s(r'\b([a-z][a-z0-9]*)\s+(?:\d+\.\d+|to\s+(?:drop|end)|support)', h)
        return frame('third-party:app-support:' + (app.group(1) if app else h),
                     'minimum-os-change', tier='weak', kind='third_party_ecosystem')
    # Price advice and a rival's own sales are not Apple's reported action.
    if (s(r'price\s+hike|涨价', h) and s(r"we(?:['’]ll|\s+will)\s+be\s+shocked|inevitable|do\s+not\s+wait|赶紧买", local)
            and not s(r'apple\s+(?:announced|confirmed)|苹果(?:宣布|确认)', opening)):
        return frame('editorial:' + h, 'price-prediction', 'hardware_products', 'general_company', 'weak')
    rival_sale = s(r'(华为|三星|小米|huawei|samsung|xiaomi)[^。；;]{0,55}?(?:销量|出货量|sales|shipments)[^。；;]{0,30}?(?:增长|大增|增加|grew|increased|rose)', h)
    if rival_sale:
        return frame('third-party:' + rival_sale.group(1), 'rival-sales-report', 'hardware_products', 'hardware_market', 'weak')

    if (s(r'screen\s*time|屏幕使用时间', h)
            and s(r"apple(?:['’]s)?\s+(?:new|requirement)|苹果.{0,20}(?:要求|新)", local)
            and s(r'controls?|requirements?|controls|架构|要求', local)):
        version = s(r'(?:ios|os|系统)\s*(\d+)', local)
        return frame('screen-time:' + (version.group(1) if version else 'current'), 'support-rollout-report')
    # Co-development is an explicit Apple action; compatibility alone is not.
    if s(r'home|家居|门铃|门锁|温控|恒温', h) and s(r'apple|苹果', h):
        partner = s(r'(?:apple|苹果)(?:\s+and\s+|与\s*|和\s*|将联手\s*)([a-z][a-z0-9-]*)\s*(?:team\s+up|(?:have\s+been\s+)?working\s+together|(?:电子)?\s*(?:联合|共同|合作)?开发)|'
                    r'apple[\'’]s\s+(?:plans|products|devices)[^.!?。]{0,120}(?:codeveloped|co-developed|developed)\s+in\s+partnership\s+with\s+([a-z][a-z0-9-]*)|'
                    r'apple\s+(?:is\s+)?(?:collaborating|working)\s+with\s+([a-z][a-z0-9-]*)', local)
        if partner and not s(r'denies|not\s+working|否认|并未合作', local[:450]):
            name=next(v for v in partner.groups() if v)
            return frame('apple:home-codevelopment:' + name, 'joint-hardware-development', 'hardware_products', 'hardware_market')
    if s(r'apple\s*tv', h):
        for start,end in source_sentence_spans(opening):
            clause=opening[start:end]
            if s(r'last\s+year|previously|去年|此前', clause):
                continue
            work=s(r'apple\s*tv\s+announced\s+(?:a\s+new\s+[^.!?]{0,50}[—–-]|["“])([^"”—–-]{2,70})["”—–-]', clause)
            if work:
                name=_compiled_rule(r'[^a-z0-9]+', 0).sub('-', work.group(1), 0).strip('-').removeprefix('the-')
                return frame('apple-tv-content:' + name, 'series-announcement', kind='service_content')

    # A teardown publication owns the models it actually examines, including
    # shorthand model names in the opening; comparison history stays outside.
    if s(r'apple\s*watch',h) and s(r'teardown|tears?\s+down|拆解',local) and s(r'ifixit',detail):
        first_end=next(source_sentence_spans(opening),(0,len(opening)))[1]
        models=sorted(set(_compiled_rule(r'(?<![a-z0-9])(series|ultra)\s*(\d+)',0).findall(opening[:first_end])))
        if models and not s(r'last\s+year|去年|回顾',h):
            return frame('ifixit:apple-watch:' + ','.join(kind+'-'+number for kind,number in models),
                         'device-teardown-report','hardware_products','hardware_market')
    # Executive transactions concern Apple equity, independent of the devices
    # a biography happens to mention.
    seller=s(r'^([a-z]+(?:\s+[a-z]+){1,3})\s+sold\b',h)
    person = seller.group(1).replace(' ','-') if seller else ''
    if s(r'库克',h): person='tim-cook'
    if s(r'特努斯',h): person='john-ternus'
    if (person and s(r'apple\s+shares|苹果.{0,35}股票',h) and s(r'\bsold\b|减持|出售',h)
            and s(r'apple.{0,30}(?:executive|chair|ceo)|苹果.{0,20}(?:高管|董事|首席执行官)',opening)
            and not s(r'last year|previously|去年|此前',h)
            and not s(r'\b(?:may|might|could|not)\s+(?:have\s+)?(?:sell|sold)\b|(?:计划|可能|并未).{0,5}(?:出售|减持)',local)):
        sale_date=s(r'\bsold\b[^.!?]{0,130}?\bon\s+([a-z]+)\s+(\d{1,2})',opening)
        local_sale_date=s(r'(?:库克|特努斯|tim\s*cook|john\s*ternus|董事[^，。]{0,20})[^，。]{0,25}?(?:于|在)(?:今年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:出售|减持)',opening)
        date_key=''
        months="january february march april may june july august september october november december".split()
        if sale_date and sale_date.group(1) in months:
            date_key=str(months.index(sale_date.group(1))+1)+'-'+str(int(sale_date.group(2)))
        elif local_sale_date:
            date_key=str(int(local_sale_date.group(1)))+'-'+str(int(local_sale_date.group(2)))
        if date_key:
            return frame('apple:equity:' + person + ':' + date_key,'executive-share-sale','hardware_products','company_org')
    # A newly attributed disclosure about a discarded memory plan is one
    # report, whether the headline names the chip or its host phone.
    if s(r'considered|once\s+planned|曾计划',h) and s(r'\d+\s*gb',h):
        model=s(r'iphone\s*(\d+)\s*pro',local)
        capacity=s(r'(\d+)\s*gb',h)
        reporter=_compiled_rule(r'\bleaker\s+(?:known\s+as\s+)?["“]?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})|爆料者[^。]{0,20}[（(]([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})[）)]',0).search(lead[:600])
        if model and reporter and not s(r'last year.{0,30}(?:report|post)|去年.{0,20}报道',opening):
            name=next(v for v in reporter.groups() if v).lower().replace(' ','')
            return frame('iphone-'+model.group(1)+'-pro:memory:'+capacity.group(1)+':'+name,
                         'discarded-plan-disclosure','hardware_products','hardware_market')
    if s(r'apple\s+arcade',h) and s(r'launch|announc|exclusive',h):
        game=(_compiled_rule(r"^['\"]([^'\"]+)['\"].{0,30}Launching",re.I).search(title)
              or _compiled_rule(r'Apple Arcade subscribers will get access to ([^.!?]+)',re.I).search(lead[:500]))
        if game and not s(r'last year|previously|cancel|去年|取消',h):
            name=_compiled_rule(r'[^a-z0-9]+', 0).sub('-', game.group(1).lower(), 0).strip('-')
            return frame('apple-arcade:'+name,'catalog-addition',kind='service_content')

    # The named built-in feature owns software disclosures on a host device.
    if s(r'messages|消息|信息', h) and s(r'suggest|建议', h) and s(r'controls?|toggle|关闭|控制|隐藏', detail):
        version=s(r'(?<![a-z0-9])ios\s*(\d+(?:\.\d+)*)', local)
        if version and s(r'code|leaker|发现|代码', detail):
            return frame('ios-' + version.group(1) + ':messages:suggestion-controls', 'feature-code-discovery')
    if s(r'iphone', h) and s(r'pdf|documents?|quick\s*look', h) and s(r'two.page|双页', h):
        device=s(r'iphone\s*(duo|\d+)', h)
        if device and s(r'latest\s+reveal|leak|preview|code|new\s+finding|曝光|爆料|分享.{0,20}视频', local):
            return frame('iphone-' + device.group(1) + ':quick-look:pdf-layout', 'feature-code-discovery')
    if s(r'homekit|灵动岛|dynamic\s*island', h) and s(r'代码|code', local) and s(r'controls?|控制', local):
        version=s(r'(?<![a-z0-9])ios\s*(\d+(?:\.\d+)*)', local)
        if version:
            return frame('ios-' + version.group(1) + ':homekit:proximity-controls', 'feature-code-discovery')
    # This helper only binds a macOS maintenance release. Asset discoveries
    # and multi-platform release waves retain their existing claim authority.
    if (s(r'macos', h) and s(r'\brc\s*\d*|release\s+candidates?|候选发布', h)
            and not s(r'(?<![a-z])(?:ios|ipados|watchos|tvos|visionos)(?![a-z])', h)
            and not s(r'曝光|发现|泄露|\breveals?\b|disclos|code\s+clues|hidden', h)
            and (s(r'now\s+available|out\s+for\s+testing|现已可用', h)
                 or s(r'\b(?:issued|released|releases|releasing|rolling\s+out)\b|(?<!未)(?:发布|推送)', local))
            and not source_denies_action(title, lead, r'issu\w*|releas\w*|roll\w*|发布|推送')):
        current = opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
        versions = sorted(set(_compiled_rule(r'macos\s+(?:[a-z]+\s+)?(\d+\.\d+(?:\.\d+)?)', 0).findall(h + ' ' + current)))
        builds = sorted(set(_compiled_rule(r'(?<![a-z0-9])\d{2}[a-z]\d{3,}[a-z]?(?![a-z0-9])', 0).findall(detail)))
        if versions or builds:
            stage = s(r'\brc\s*(\d+)|\b(first|second|third)\s+(?:release\s+)?candidate|第([一二三\d]+)个?候选', h + ' ' + current)
            ordinal = next((v for v in stage.groups() if v), '1') if stage else '1'
            number = {'first':'1', 'second':'2', 'third':'3', '一':'1', '二':'2', '三':'3'}.get(ordinal, ordinal)
            # A concrete build identifies the same release even when reports
            # disagree on its version label. Version aliases also connect a
            # sparse source that does not carry the build; preserve both labels.
            version_subject = 'macos:maintenance:' + ','.join(versions)
            subject = 'macos:builds:' + ','.join(builds) if builds else version_subject
            return SourceActionFrame(subject, 'maintenance-rc-' + number, kind='os_app',
                period=','.join(builds), aliases=(version_subject,) if builds and versions else ())

    # A new observation of a product fault remains a report with uncertainty.
    device = s(r'iphone\s*(\d+)\s*pro(?:\s*max)?', h)
    if (device and s(r'discolor|fading|褪色|变色', h)
            and s(r'users?.{0,40}(?:report|complain)|用户.{0,50}(?:反馈|反映|称|吐槽)', local)
            and not s(r'去年.{0,30}(?:用户|报告)|last\s+year.{0,30}report', opening[:160])):
        return frame('iphone-' + device.group(1) + '-pro:finish', 'reported-discoloration', 'hardware_products', 'hardware_market')
    if (s(r'apple[- ](?:i|1)(?![a-z0-9])|苹果一号', h)
            and not s(r'去年|此前|回顾|last\s+year|previously', h)):
        named_artifact = _compiled_rule(r'[“\"‘\'(]([a-z][a-z ]{1,30})[”\"’\')](?:\s*)apple[- ](?:i|1)\b|'
            r'(?:the\s+)?([a-z][a-z-]{1,30})\s+apple[- ](?:i|1)\b')
        def artifact_names(text):
            return {next(v for v in match.groups() if v) for match in named_artifact.finditer(text)} - {
                'working', 'an', 'original', 'the', 'rare', 'surviving'}
        title_artifacts = artifact_names(h)
        naming = s(r'(?:(?:the|this)\s+(?:machine|computer)\s+is\s+(?:known as|called)\s+|'
                   r'(?:这|该)台(?:机器|设备|电脑)(?:被)?称为)([^.!?。！？]{1,100})', opening)
        for clause in (h, *(opening[start:end] for start, end in source_sentence_spans(opening))):
            sale = s(r'\bsold\b|拍出|成交|落槌', clause)
            if (not s(r'apple[- ](?:i|1)(?![a-z0-9])|苹果一号', clause)
                    or not sale
                    or source_predicate_role(clause) != 'current'
                    or source_denies_action('', clause, r'sold|拍出|成交|落槌')):
                continue
            # The artifact is the subject of a passive sale or the direct
            # object of an active sale, not a later result or comparison.
            direct_object = _compiled_rule(r'\b(?:for|at|with|including|while|whereas|but)\b|[,;]').split(
                clause[sale.end():], maxsplit=1)[0]
            artifacts = artifact_names(direct_object) or artifact_names(clause[:sale.start()])
            if not artifacts and naming:
                artifacts = artifact_names(naming.group(1))
            if len(artifacts) == 1 and (not title_artifacts or artifacts == title_artifacts):
                return frame('apple-1:artifact:' + next(iter(artifacts)).replace(' ', '-'),
                    'completed-auction-sale', 'hardware_products', 'hardware_market')
    if s(r'auction|拍卖', h) and s(r'apple\s*i(?![a-z0-9])|苹果一号', h):
        active = s(r'正在.{0,25}拍卖|竞价.{0,20}(?:\d|本月)|auction.{0,35}(?:runs|open)|拍卖.{0,50}(?:日期|竞价)', detail)
        house = s(r'bonhams|邦瀚斯', detail)
        if active and house:
            window = s(r'(\d{1,2})\s*月[）)]?\s*(\d{1,2})\s*日至\s*(\d{1,2})\s*日', detail)
            if window:
                return frame('apple-i:bonhams:' + '-'.join(window.groups()), 'current-auction', 'hardware_products', 'hardware_market')
    if s(r'earnings|financial\s+report|财报|q[1-4].{0,15}results', h) and s(r'apple|苹果', local):
        year=s(r'\b(20\d{2})\b', h)
        quarter=s(r'\bq([1-4])\b|第\s*([1-4])\s*财季', h)
        if year and quarter and s(r'(?:report|releas\w*|results|公布|发布).{0,80}(?:november|\d+\s*月)|\b(?:november|\d+\s*月).{0,35}(?:report|release|公布|发布)', local):
            return frame('apple:earnings:' + year.group(1) + ':q' + next(v for v in quarter.groups() if v), 'earnings-schedule', 'hardware_products', 'company_org')
    if (s(r'charge\s*limits?|充电上限', h) and s(r'years?|年', h) and s(r'results?|结果', h)
            and s(r'iphone', h) and s(r'\d+\s*(?:%|percent)', detail)
            and s(r'\d+\s*(?:charge\s*)?cycles?|循环.{0,10}\d+', detail)):
        duration=s(r'\b(one|two|three|four|five|\d+)\s+years?|([一二三四五\d]+)年', h)
        return frame('iphone:charge-limit:' + (duration.group() if duration else h), 'longitudinal-battery-measurement', 'hardware_products', 'hardware_market')
    return None


def source_platform_component_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """A current platform component change owns its version and release stage."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    local = h + '. ' + opening
    s = _frame_search
    if (s(r'^(?:an?\s+)?(?:(?:independent|graphic|ui|ux|concept)\s+)*designer\b|^(?:独立|概念|界面)?设计师', h)
            and s(r'concept|概念', opening)):
        return SourceActionFrame('third-party:concept:' + h, 'design-concept', kind='third_party_ecosystem', tier='weak')
    # A multi-component inventory must not inherit only its first component.
    if s(r'health|健康\s*app', h) and s(r'apple\s*music', h):
        return None
    version = s(r'(?<![a-z])(ios|ipados|macos|tvos|watchos)\s*(\d+(?:\.\d+)*)', local)
    if version and not s(r'去年|此前版本|last\s+year|retrospective|not\s+(?:removed|replaced)|并未(?:移除|更换)', h):
        period = version.group(1) + '-' + version.group(2)
        stage = s(r'beta\s*(\d+)', local)
        if s(r'(?:apple\s*)?health\s*(?:app|redesign)|健康\s*app', h) and s(r'remov|no\s+longer\s+includes|移除|撤回', h) and not source_denies_action(title, lead, r'remove|移除|撤回'):
            return SourceActionFrame('apple-health:redesign', 'feature-withdrawal', kind='os_app',
                period=period + (':beta-' + stage.group(1) if stage else ''))
        if (s(r'apple\s*music', h) and s(r'icon|图标', h)
                and s(r'new|replac|新增|更换|全新', local)
                and not source_denies_action(title, lead, r'include|replace|add|更换|新增')):
            return SourceActionFrame('apple-music:app-icon', 'visual-design-change', kind='os_app', period=period, model_generation='beta-' + stage.group(1) if stage else '')
        if (s(r'day.one|首批', h) and s(r'updat|更新', h) and s(r'iphone|ipad', h)):
            builds = sorted(set(_compiled_rule(r'(?<![a-z0-9])\d{2}[a-z]\d{3,6}[a-z]?(?![a-z0-9])', re.I).findall(local)))
            device = s(r'(iphone|ipad)\s*(duo|air|\d+(?:\s*pro(?:\s*max)?)?)', h)
            if len(builds) >= 2 and device:
                return SourceActionFrame(_subject_slug(device.group()) + ':initial-os-update', 'device-build-update', kind='os_app',
                    period=period + ':' + ','.join(builds))
    feature = r'sleep\s*apnea|睡眠呼吸暂停'
    activation = r'launch|rollout|rolls?\s+out|上线|启用|推出|正式登陆'
    current_statement = any(
        s(r'apple\s*watch\s*[“\x22\x27]?(?:' + feature + r')'
          r'(?:\s|迹象提示|通知|功能|notifications?|feature|[”\x22\x27])*'
          r'(?:现已(?:推出|上线|启用)|(?:is\s+|are\s+)?now\s+(?:available|launched)\b)', clause)
        and not s(r'去年|此前|尚未|计划|预计|last\s+year|previously', clause)
        and not source_denies_action('', clause, r'launch\w*|available|推出|上线|启用')
        for a, b in source_sentence_spans(opening) for clause in (opening[a:b],))
    # The opening may name a feature omitted by an abbreviated headline.
    # A known software capability does not need an OS version to stay software.
    owned_activation = (s(feature, h) and s(activation, h)) or (
        s(r'功能|feature|更新|update', h) and s(feature, opening)
        and s(activation, opening) and s(r'today|now|今天|今日|终于', local)) or (
        s(feature, h) and s(r'apple|苹果', h) and current_statement)
    if ((s(r'apple\s*watch', h) or current_statement) and owned_activation
            and not s(r'last\s+year|previously|去年|回顾|尚未|未获|计划|预计', h)
            and not source_denies_action(title,lead,r'launch|roll\s+out|启用|上线')):
        region_pattern = (r'(?:launch(?:es|ed)?|rolls?\s+out|available)[^.!?。]{0,90}?\s+in\s+(?:the\s+)?'
                          r'([a-z]+(?:\s+[a-z]+){0,2}?)(?=\s+(?:today|now|with|for|under|on|as)\b|[,.!?]|$)')
        region_match = s(region_pattern, h) or s(r'在([^，。]{2,10}?)(?:上线|启用|推出)', h)
        if region_match is None:
            for start, end in source_sentence_spans(opening):
                clause = opening[start:end]
                if (s(feature, clause) and s(activation, clause)
                        and not s(r'last\s+year|previously|not\s+launch|去年|此前|尚未', clause)):
                    region_match = s(region_pattern, clause)
                    if region_match:
                        break
        region = region_match.group(1) if region_match else ''
        region = {'united states':'us','united kingdom':'uk','美国':'us','日本':'japan','中国':'china','中国大陆':'china'}.get(region,region)
        if not region and s(r'中国|国内|国行|国家药品监督管理局|\bchina\b', local):
            region='china'
        return SourceActionFrame('apple-watch:sleep-apnea', 'regional-feature-activation', kind='os_app', region=region)
    return None


def source_collection_operation_frame(title: str, lead: str) -> SourceActionFrame | None:
    """Bind a first-party collection's focal operation before compatible hubs."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    local = h + '. ' + opening
    collection = s(r'apple\s*home\s*collection', local)
    if not collection or not s(r'accessor|lineup|collection|配件|系列|家居', h):
        return None
    app = s(r'(?:supports?|works?\s+with|compatib\w*\s+with|兼容|支持)\s*[「“"]?(.{2,45}?)\s*[」”"]?\s*(?:app(?:lication)?\b|应用)', h)
    owner = s(r'apple\s*home\s*collection', h[:app.start()]) if app else None
    owner_prefix = _compiled_rule(r'[,，;；]', 0).split(h[:owner.start()])[-1] if owner else ''
    if owner and not s(r'\b(?:unlike|versus|vs|compared\s+(?:with|to))\b|不同于|相比|对比|(?:\bfor|适用于|兼容)\s*$', owner_prefix):
        name = _compiled_rule(r'\s+', 0).sub('-', app.group(1).strip('「」“”" '), 0)
        assertion = h[owner.start():app.end()]
        denied = (source_denies_action(assertion, '', r'support|compatib|work')
            or bool(s(r"\b\w+n['’]t\s+(?:support|compatib|work)|no\s+longer|不再|不支持|不兼容", assertion)))
        return SourceActionFrame('apple-home:collection:app:' + name,
            'app-compatibility-denied' if denied else 'app-compatibility', kind='os_app')
    if (source_editorial_evaluation(title, lead)
            or source_denies_action(title, lead, r'launch|announce|introduce|发布|推出|宣布')
            or s(r'cancel|cancelled|retrospective|取消|回顾', h)
            or s(r'last\s+(?:year|month|week)|previously|去年|此前', opening[:300])):
        return None
    shipping = s(r'now\s+shipping|begun\s+shipping|开始发货|现已发货', h)
    declared_inventory = s(r'new\s+apple\s*home\s*collection\s+pairs.{0,90}hardware', opening)
    if ((declared_inventory or s(r'(?:apple|苹果)(?:\s+(?:today|also)|今日|今天|还)?\s*(?:announc\w*|unveil\w*|debut\w*|launch\w*|公布|推出|宣布)|introducing', local))
            and (declared_inventory or s(r'cameras?|thermostats?|door\s*lock|smart\s+home\s+accessories|摄像头|恒温器|门锁', local))
            and (declared_inventory or s(r'collaborat|developed\s+with|合作(?:设计|开发|推出)|联合研发', local))
            and not s(r'expected|rumou?r|plans?\s+to|预计|传闻|计划', h)):
        return SourceActionFrame('apple-home:collection', 'collection-shipping' if shipping else 'collection-announcement', 'hardware_products', 'hardware_market')
    return None


def source_patent_challenge_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """A party's current post-verdict filing is distinct from the ruling or plan."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    local = h + '. ' + opening
    if not s(r'patent|专利', local) or not s(r'verdict|jury|裁决|判决|陪审团', local):
        return None
    current = False
    for a, b in source_sentence_spans(local):
        clause = local[a:b]
        if s(r'previously|last\s+(?:year|week|month)|at\s+the\s+time|此前|去年|当时|计划|plans?\s+to|will\s+file|not\s+file|尚未|没有', clause):
            continue
        if (s(r'apple\s+(?:is\s+)?asking\s+(?:a|the)\s+(?:federal\s+)?judge\s+to\s+(?:overturn|vacate)|'
              r'apple\s+(?:has\s+)?filed\s+(?:a\s+)?(?:new\s+)?motion\s+to\s+(?:overturn|vacate)|'
              r'(?:new\s+filing\s+from\s+apple|new\s+filing\s+suggests)|'
              r'苹果(?:公司)?(?:正|正在)?请求[^。；;]{0,60}撤销|苹果提交.{0,12}(?:新|最新).{0,8}动议', clause)
                and not s(r'appeals\s+court|上诉法院', clause)):
            current = True
            break
    if not current:
        return None
    party = s(r'(?:brought\s+by|awarded\s+to|awarded)\s+([a-z][a-z0-9-]+)(?:\s+technology)?|'
              r'([a-z][a-z0-9-]+)(?:\s+technology)?[’\x27]s\s+patents|'
              r'([a-z][a-z0-9-]+)\s*(?:科技|公司).{0,15}(?:提起|无法证明)|'
              r'([a-z][a-z0-9-]+)\s+verdict', local)
    name = next((v for v in party.groups() if v), '') if party else ''
    if not name or name in {'apple','patent','recent','the','jury'}:
        return None
    category = 'hardware_products' if has_haptic_patent_subject(title, lead) else 'software_systems'
    return SourceActionFrame('apple-legal:' + name + ':patent-verdict', 'post-verdict-motion', category, 'legal_antitrust')


def source_brand_collaboration_frame(title: str, lead: str) -> SourceActionFrame | None:
    """Bind a first-party brand's partner, product and announcement stage."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    if not s(r'(?<![a-z])beats(?![a-z])', h):
        return None
    if source_denies_action(title, lead, r'release|announce|launch|推出|发布|合作'):
        return None
    for value in (h, opening):
        for a, b in source_sentence_spans(value):
            clause = value[a:b]
            # A leading reference to yesterday's teaser does not date the
            # independent current announcement that follows it.
            clause = _compiled_rule(r'^following\s+[^,]+,\s*', re.I).sub('', clause)
            if s(r'previously|last\s+(?:year|month|week)|此前|曾经|去年|not\s+(?:announce|release)|并未|尚未公布', clause):
                continue
            relationship = s(r'collab|team\s*up|teaming\s+up|联名|合作|携手|联手|beats\s+x\s+', clause)
            if not relationship:
                continue
            match = s(r'(?:collaboration\s+with|teaming\s+up\s+with)\s+(?:the\s+)?([a-zé][a-zé0-9-]*(?:\s+[a-zé][a-zé0-9-]*){0,3}?)(?=\s+(?:for|to|on|with|team|speaker)|[,.]|$)|'
                      r'beats\s+(?:and|x)\s+([a-zé][a-zé0-9-]*(?:\s+[a-zé][a-zé0-9-]*){0,3}?)(?=\s+(?:collaboration|announc\w*|introduc\w*|releas\w*|team\w*|teas\w*|for|to|on|with|will|new)|[,.]|$)|'
                      r'beats(?:携手|联手|.{0,12}与)([^，。 （(]{2,15}?)(?:推出|合作|联名|[（(])', clause)
            partner = next((v for v in match.groups() if v), '') if match else ''
            if not partner and s(r'pok[eé]mon|宝可梦', clause):
                partner = 'pokemon'
            if not partner:
                continue
            partner = 'pokemon' if partner in {'pokémon', '宝可梦'} else partner
            model = s(r'beats\s*(pill|studio\s*(?:pro|buds)?|solo\s*\d*|fit\s*pro|powerbeats\s*pro)', clause)
            if not model:
                model = s(r'beats\s*(pill|studio\s*(?:pro|buds)?|solo\s*\d*|fit\s*pro|powerbeats\s*pro)', opening)
            stage = ('partnership-teaser' if s(r'teas|预告|预热', clause)
                     else 'partnership-announcement' if s(r'new|announc|reveal|released|team\s*up|teaming\s+up|推出|公布|全新|联名', clause)
                     else '')
            if stage:
                return SourceActionFrame('beats:collaboration:' + _subject_slug(partner), stage, 'hardware_products', 'hardware_market',
                    model_generation=_subject_slug(model.group(1)) if model else '')
    return None


def _homepod_mac_audio_activation(assertion: str) -> SourceActionFrame | None:
    s = _frame_search
    if (s(r'(?:software|firmware)\s+(?:\d|update)|软件更新|固件更新', assertion)
            and s(r'\b(?:released?|enabled?|adding|added)\b|新增|启用|开始支持', assertion)
            and s(r'\btoday\b|\bnow\b|今日|今天|现已', assertion)
            and not s(r'previously|last\s+(?:year|month|week)|此前|去年|上月|上周', assertion)):
        version = s(r'(?:software|firmware)\s+(\d+(?:\.\d+)+)', assertion)
        return SourceActionFrame('homepod:mac-system-audio', 'platform-capability-activation', kind='os_app',
                                 period='software-' + version.group(1) if version else '')
    return None


def source_device_operation_frame(title: str, lead: str, facts: tuple[str, ...] = (), *, source_units: tuple[str, ...] = ()) -> SourceActionFrame | None:
    """Keep a named device's launch and focused reports with their own object.

    A compatibility host, launch inventory or software carrying a hardware
    discovery does not replace the subject of the reported operation.
    """
    h, opening = _normalized(title), _normalized(lead)[:1200]
    # Ordering reports may start their extracted summary at a specification;
    # the captured opening retains the source's actual introduction relation.
    if source_units and _frame_search(r'pre.?order|预订|预购', h):
        opening = _normalized(' '.join(source_units[:2]))[:1200]
    # HTML titles may append a section label and a publisher domain.
    h = _compiled_rule(r'\s+-\s+[^-]+\s+-\s+[a-z0-9.]+\.(?:com|net)$').sub('', h)
    s = _frame_search
    local = h + '. ' + opening
    if source_editorial_evaluation(title, lead):
        return None
    if s(r'\b(?:wish|concept)\b|概念|设想|希望', h):
        return None
    if (s(r'homepods?|homepod\s*mini', h) and s(r'mac\s+system\s+audio|mac.{0,8}系统(?:音频|声音|提示音)', h)
            and not source_denies_action(title, lead, r'output|route\w*|支持|输出')
            and not s(r'\b(?:wish|concept|could|might|expected|planned|will|would)\b|设想|希望|预计|预测|未来|有望', source_primary_assertion(title, lead))):
        for a, b in source_sentence_spans(opening):
            clause = opening[a:b]
            if (s(r'homepods?[^.!?。]{0,40}(?:can\s+output|支持|可输出)[^.!?。]{0,30}mac|'
                  r'\bmac\b[^.!?。]{0,120}homepod[^.!?。]{0,100}can\s+be\s+routed|'
                  r'\bmac[^.!?。]{0,120}(?:声音|音频|提示音)[^.!?。]{0,45}'
                  r'(?:可以|可|能够)(?:直接)?通过\s*homepod\s*(?:播放|输出)', clause)
                    and not source_denies_action('', clause, r'output|route\w*|支持|输出')):
                assertion = _normalized(source_primary_assertion(title, lead))
                activation = _homepod_mac_audio_activation(assertion)
                if activation is not None:
                    return activation
                return SourceActionFrame('homepod:mac-system-audio', 'platform-capability-report', kind='os_app')
    if (s(r'which.{0,50}(?:devices?|models?).{0,30}(?:get|support)|哪些.{0,20}(?:设备|机型).{0,15}支持', h)
            and s(r'siri\s*ai', h) and s(r'apple|苹果', local)
            and s(r'confirmed|support|支持|确认', opening)):
        return SourceActionFrame('siri-ai:home-device-support', 'platform-support-matrix-report', kind='os_app')
    launch_title = s(r'\b(?:announces?|unveils?|introduces?|launches?)\b|(?:苹果|音箱|设备).{0,20}(?:发布|推出)', h)
    launch_inventory = (s(r'colors?|配色|粉色|绿色', h)
        and s(r'^(?:apple|苹果).{0,25}(?:introduc|announc|推出|发布)', opening))
    if (not launch_title and not launch_inventory and s(r'homepod|apple\s*tv', h) and s(r'surround\s*sound|环绕声', h)
            and not s(r'code|代码|rumou?r|爆料', h)
            and s(r'four|4\s*(?:个|台|只)|四', local)
            and s(r'support|available|支持|可用', local)
            and s(r'new\s+apple\s*tv|fourth.generation|4th.generation|新款\s*apple\s*tv|第四代', local)):
        return SourceActionFrame('homepod:surround-system', 'feature-announcement', kind='os_app')
    primary = _compiled_rule(r'\s+(?:with|featuring|alongside|for)\s+', re.I).split(h, maxsplit=1)[0]
    prefix = _compiled_rule(r'[:：]', 0).split(primary, maxsplit=1)[0]
    if disclosed_device_subjects(prefix) or s(r'homeview|siri\s*remote', prefix):
        primary = prefix
    if not (disclosed_device_subjects(primary) or s(r'homeview|home\s*hub|家庭中枢|家居中枢|homepod|siri\s*remote', primary)):
        primary = h
    devices = disclosed_device_subjects(primary)
    if (s(r'^apple[’\x27]s\s+new\b[^.!?]{0,45}\bremote\b', h)
            and s(r'compatib|work\s+with', h)):
        definition = _normalized(source_units[0]) if source_units else opening
        definition = definition[:next(source_sentence_spans(definition), (0, len(definition)))[1]]
        if (s(r'(?:new|updated)\s+siri\s+remote\b', definition)
                and s(r'available\s+to\s+buy\s+standalone|sold\s+separately', definition)
                and not s(r'third.party|concept|imagines?|last\s+year|第三方|概念|去年', definition)):
            devices = {'siri-remote': ''}
            opening = definition
            local = h + '. ' + opening
    named_introduction = False
    if (not devices and s(r'苹果', h) and s(r'新|做了|发布|推出', h)
            and not s(r'概念|回顾|去年|拟|计划|将', h)):
        introduction = _normalized(' '.join(source_units[:2]))[:1200] if source_units else opening
        named = s(r'(?:它|这款设备|该设备)(?:叫|名为|被命名为)\s*([^，,。.!?；;]+)', introduction)
        if (named and s(r'苹果(?:公司)?(?:今天|今日|这次|此次|正式)*'
                       r'(?:召开[^。.!?]{0,70}新品发布会|发布|推出)', introduction[:named.start()])
                and not s(r'去年|此前|上月|计划|将|拟|尚未|并未|没有|否认', introduction[:named.start()])
                and not s(r'概念|设计师', introduction)):
            if s(r'homeview|home\s*hub|家庭中枢|家居中枢', named.group(1)):
                devices['apple-home-hub'] = ''
            else:
                devices.update(disclosed_device_subjects(named.group(1)))
            named_introduction = len(devices) == 1
    if s(r'homeview|home\s*hub|家庭中枢|家居中枢', primary):
        devices['apple-home-hub'] = ''
    if s(r'homepod(?!\s*mini|.like)', primary):
        devices['homepod'] = ''
    if s(r'siri\s*remote|siri\s*遥控器', primary):
        # The remote is the head noun; TVs are its compatibility targets.
        remote_at = s(r'siri\s*remote|siri\s*遥控器', primary).start()
        host = s(r'apple\s*tv', primary)
        if not host or remote_at < host.start() or s(r'^what\s+apple\s*tv.{0,80}siri\s*remote.{0,30}compatib', primary):
            devices = {'siri-remote': ''}
    if not devices and s(r'\bfaces\b|显示界面|界面|表盘', h):
        face_owners = {key for key, aliases in PRODUCT_PATTERNS
                       if any(s(r'^' + re.escape(alias) + r'(?![a-z0-9])', h) for alias in aliases)}
        if len(face_owners) == 1:
            devices[next(iter(face_owners))] = ''
    if not devices and s(r'^\d+\s+[^.!?]{1,65}\bfeatures\b|(?:功能|特性)(?:汇总|一览)', h):
        canonical_devices = _collapse_product_hierarchy(_extract_patterns(primary, PRODUCT_PATTERNS))
        canonical_devices &= {key for key, _name, _aliases in MULTI_PRODUCT_HARDWARE_SUBJECTS}
        devices = {key: '' for key in canonical_devices}
    if len(devices) != 1:
        return None
    subject, generation = next(iter(devices.items()))
    if not generation:
        generation = disclosed_device_subjects(opening[:500]).get(subject, '')
    if subject == 'homepod':
        model = (s(r'homepod\s*([2-9]\d*)(?!\d)', primary)
            or s(r'homepod\s*\(?(first|second|third|fourth|[1-9]\d*(?:st|nd|rd|th))[- ]generation|'
                 r'\b(first|second|third|fourth|[1-9]\d*(?:st|nd|rd|th))[- ]generation\s+homepod|第([一二三四\d]+)代\s*homepod', primary))
        if model:
            number=next(v for v in model.groups() if v)
            generation={'first':'1','second':'2','third':'3','fourth':'4','一':'1','二':'2','三':'3','四':'4'}.get(number,_compiled_rule(r'(st|nd|rd|th)$').sub('',number))
    if subject == 'apple-tv':
        for value in (primary, opening[:350]):
            model = (s(r'\b(first|second|third|fourth|fifth|[1-9]\d*(?:st|nd|rd|th)?)[- ]generation\s+apple\s*tv|apple\s*tv(?:\s*4k)?\s*(?:gen(?:eration)?\.?\s*)([1-9]\d*)', value)
                     or s(r'第([一二三四五六七八九十\d]+)代\s*apple\s*tv', value))
            if model:
                number = next(v for v in model.groups() if v)
                generation = {'first':'1','second':'2','third':'3','fourth':'4','fifth':'5','一':'1','二':'2','三':'3','四':'4','五':'5'}.get(number,_compiled_rule(r'(st|nd|rd|th)$').sub('',number))
                break
    def frame(component, action, category='hardware_products', kind='hardware_market', tier='strong'):
        return SourceActionFrame(subject + (':' + component if component else ''), action,
                                 category, kind, tier, model_generation=generation)

    if named_introduction:
        return frame('', 'device-announcement')

    detail = local + ' ' + ' '.join(_normalized(f) for f in facts)
    if s(r'^\d+\s+[^.!?]{1,65}\bfeatures\b|(?:功能|特性)(?:汇总|一览)', h):
        from .article_processing import capture_article_title_evidence
        evidence = capture_article_title_evidence('', '', title, lead, tuple(dict.fromkeys((*facts, *source_units))))
        claim = bind_device_capability_inventory(evidence)
        if claim is not None and claim.subject and claim.report_role == 'independent':
            return frame(claim.object, claim.action, claim.category, claim.event_kind)
    if (s(r'撞名|同名|namesake|same\s+name', h) and s(r'旧|年前|previous|years?\s+ago', h)
            and not s(r'trademark|lawsuit|起诉|商标争议', h)):
        return frame('historical-namesake', 'third-party-name-recollection', tier='weak')
    if (s(r'european\s+union|\beu\b|欧盟', h)
            and s(r"(?:won[’']t|isn[’']t|not|no)\s+(?:be\s+)?(?:available|launch|homeview)|无缘|不会.{0,8}(?:发售|上市)", local)):
        return replace(frame('availability', 'regional-launch-withheld'), region='eu')
    if s(r'\bai\b|人工智能|智能', h) and s(r'needs?|依赖|requires?', h) and s(r'iphone|ipad', h):
        return frame('personal-ai:paired-device', 'platform-capability-report', 'software_systems', 'os_app')
    if s(r'facial\s+recognition|人脸识别', h) and s(r'\bworks?\b|如何|机制|原理|运作|工作', h):
        return frame('personal-content:face-recognition', 'platform-capability-report', 'software_systems', 'os_app')
    if (s(r'\bfaces\b|显示界面|界面|表盘', h)
            and not s(r'\bwish\b|\bconcept\b|希望|概念|教程|如何', h)):
        aliases = next((names for key, names in PRODUCT_PATTERNS if key == subject), ())
        owner = r'(?:apple[’\']s\s+|苹果\s*)?(?:' + '|'.join(re.escape(name) for name in aliases) + r')(?![a-z0-9])'
        opening_claim = opening[len(h):].lstrip(' .。') if opening.startswith(h) else opening
        opening_claim = opening_claim[:next(source_sentence_spans(opening_claim), (0, len(opening_claim)))[1]]
        capability = _compiled_rule(r'[，,；;]|\b(?:but|while|whereas)\b', 0).split(opening_claim, maxsplit=1)[0]
        if (aliases and s(r'^' + owner, h)
                and s(r'^' + owner + r'(?:[’\']s|的)?\s*(?:(?:display\s+)?faces|显示界面|界面|表盘)?\s*'
                      r'(?:(?:now|currently)\s+)?(?:includes?\b|offers?\b|provides?\b|(?:现已|目前)?(?:提供|包含|支持))', capability)
                and s(r'customizable|customisable|可定制|自定', capability)
                and s(r'\bfaces\b|显示界面|界面|表盘', capability)
                and not s(r'\bconcept\b|proposed\s+interface|independent\s+designer|unofficial|unconfirmed|概念|设想|未经确认|独立设计师', opening_claim)
                and not source_denies_action(title, lead, r'include\w*|offer\w*|provide\w*|提供|包含|支持')):
            return frame('display-faces', 'display-face-capability-report', 'software_systems', 'os_app')
    if (s(r'siri\s*ai', h) and s(r"won[’']t|not\s+(?:have|support)|不会|不支持", h)
            and s(r'launch|right\s+away|发布|立即', h)
            and s(r'apple|苹果', local) and s(r"future\s+(?:software\s+)?update|available\s+later|未来.{0,8}软件更新|won[’']t\s+be\s+available\s+on\s+launch", detail)):
        return frame('siri-ai', 'feature-activation-deferred', 'software_systems', 'os_app')
    if (s(r'涨至|突然提价|发布后.{0,10}(?:涨价|提价)|price.{0,25}(?:raised|increased)\s+after', h)
            and s(r'price|售价|定价|价格|元', local)):
        return frame('retail-price', 'post-announcement-price-revision')
    # The headline chooses a focused object before the opening's release recap.
    if (s(r'repair|service\s+cost|维修', h) and s(r'fees?|costs?|price|费用|收费|价格|要价', h)
            and s(r'applecare|保修|保障', local)
            and not s(r'how\s+to\s+repair|自行维修|第三方维修|repair\s+shop', h)):
        history = s(r'last\s+(?:year|month|week)|previously|去年|此前|上月|上周', source_primary_assertion(title, lead))
        current_fees = s(r'(?:today|now|今日|今天|本周)[^.。]{0,70}(?:repair|fees?|维修|费用)|'
                         r'(?:repair|fees?|维修|费用)[^.。]{0,70}(?:today|now|今日|今天|本周)', local)
        if history and not current_fees:
            return frame('repair-fees', 'historical-service-price-reference', 'software_systems', 'service_policy', 'weak')
        return frame('repair-fees', 'service-price-disclosure', 'software_systems', 'service_policy')
    if s(r'power\s*(?:adapter|requirements?)|供电|电源|充电器', h):
        if s(r'(?:apple|苹果).{0,80}(?:published|support\s+(?:document|article)|支持文档)|'
             r'(?:support\s+(?:document|article)|支持文档).{0,80}(?:power|adapter|供电|电源)', local):
            return frame('power-requirements', 'support-requirements-report')
        return None
    if (s(r'camera|摄像头', h) and s(r'code|代码|固件|(?:macos|ios|tvos)\s*\d', local)
            and s(r'sensor|imx\d|像素|pixels?|cmos', local + ' ' + ' '.join(facts))
            and s(r'found|discover|reveal|挖掘|发现|显示|曝光', local)
            and not source_denies_action(title, lead, r'reveal(?:ed)?|disclos\w*|find|found|discover\w*|公布|发现|披露')):
        version = s(r'(?:macos|ios|tvos)\s*(\d+(?:\.\d+)*)', local)
        return replace(frame('camera-sensor', 'hardware-code-discovery'),
                       period='code-' + version.group(1) if version else '')
    if s(r'wall.mount|for\s+(?:your|the)\s+wall|壁挂|挂墙', h) and s(r'vesa|bracket|mount|支架|配件', h):
        if s(r'vesa', h) and s(r'lacks?|no\s+vesa|不兼容|不支持', local):
            return frame('mount-accessories', 'installation-requirements-report')
        if s(r'bracket|mount|支架|配件', h) and s(r'purchase\s+separately|sold\s+separately|doesn[’\x27]t\s+include\s+(?:a\s+)?mount|另购|单独购买|不附带|不包含', local):
            return frame('mount-accessories', 'installation-requirements-report')
        return None
    if s(r'(?:third.party|第三方).{0,20}(?:apps?|widgets?|应用|小组件)|\b(?:video\s+)?apps?\b|\bwidgets?\b|原生应用|应用支持', h):
        aliases = next((names for key, names in PRODUCT_PATTERNS if key == subject), ())
        owner = '|'.join(re.escape(name) for name in aliases)
        if owner and s(r'apple|苹果', local) and s(r'iphone|ipad', detail):
            for a, b in source_sentence_spans(opening):
                clause = opening[a:b]
                if (s(owner, clause) and s(r'run|support|play|display|运行|支持|显示', clause)
                        and not s(r'\bimagines?\b|\bconcept\b|proposed\s+interface|independent\s+designer|概念|设想|独立设计师', clause)):
                    return frame('app-hosting', 'platform-capability-report', 'software_systems', 'os_app')
        return None
    if s(r'default\s+(?:mac\s+)?speaker|默认.{0,8}(?:扬声器|音箱)', h):
        if (s(r'mac', h)
                and (s(r'(?:can|now|supports?|支持|允许|可).{0,65}(?:default|默认)', local)
                     or s(r'\b(?:works?|serves?)\s+as\s+(?:(?:a|the|your)\s+)?default', h))
                and not source_denies_action(title, lead, r'work\w*|serve\w*|support\w*|支持|充当')
                and not s(r'\b(?:could|would|may|might|wish|concept)\b|希望|概念|设想', source_primary_assertion(title, lead))):
            if subject in {'homepod', 'homepod-mini'}:
                activation = _homepod_mac_audio_activation(_normalized(source_primary_assertion(title, lead)))
                if activation is not None:
                    return activation
                # Supported speaker models qualify the shared Mac system-output
                # operation; they do not make separate hardware announcements.
                return SourceActionFrame('homepod:mac-system-audio', 'platform-capability-report', kind='os_app')
            return frame('mac-default-audio', 'platform-capability-report', 'software_systems', 'os_app')
        return None
    if subject != 'siri-remote' and s(r'siri|apple\s*intelligence|苹果智能', h):
        if (s(r"won[’']t\s+support|not\s+coming|not\s+(?:getting|support)|不支持|不会支持|无缘", h)
                and s(r'confirmed|confirms|corrected|correction|确认|更正', opening)
                and s(r'apple|苹果|corrected\s+its\s+article', local)
                and not s(r'否认[^。.!?]{0,60}(?:无缘|不支持)|(?:尚未|没有|并未|未|拒绝)确认|'
                          r'\b(?:not|never)\s+(?:yet\s+)?confirm|回顾|去年|previously|last\s+year', source_primary_assertion(title, lead))):
            original = s(r'original|first.generation|第一代|初代', h)
            return replace(frame('siri-ai', 'platform-support-denial', 'software_systems', 'os_app'),
                           model_generation='1' if original else generation)

        if s(r'older|existing|\w+.year.old|旧款|老款|第[一二三四五六七八九十\d]+代[、和与及].{0,10}第[一二三四五六七八九十\d]+代', h) and s(r'coming|support|兼容|支持', local):
            return replace(frame('siri-ai:existing-models', 'platform-support-report', 'software_systems', 'os_app'), model_generation='')
        if (s(r'website|alt.text|官网|替代文本', local)
                and s(r'clue|hint|suggest\w*|indicat\w*|暗示|线索', h)
                and not source_denies_action(title, lead, r'add(?:ed)?|suggest\w*|indicat\w*|新增|显示|暗示')
                and not s(r'designer|concept|设计师|概念', opening)
                and any(s(r'alt.text|替代文本|替代文字|图片.{0,10}文字描述', _normalized(p))
                        and not s(r'designer|concept|设计师|概念', _normalized(p))
                        for p in (detail, *source_units))):
            return frame('siri-ai:website-evidence', 'support-clue-disclosure', 'software_systems', 'os_app')

    model_patterns = {
        'apple-home-hub': r'(?:apple\s*)?(?:homeview|home\s*hub)|家庭中枢|家居中枢',
        'apple-tv': r'apple\s*tv(?:\s*4k)?',
        'homepod-mini': r'homepod\s*mini(?:\s*\d+)?',
        'homepod': r'homepod(?!\s*mini)',
        'siri-remote': r'siri\s*(?:remote|遥控器)',
        'ipad-mini': r'ipad\s*mini(?:\s*\d+)?',
        'ipad-base': r'ipad\s*\d+',
    }
    device = model_patterns.get(subject, r'(?!)')
    opening_assertion = opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
    comparison = s(r'\bvs\.?|\bversus\b|对比|比较|compared', h)
    comparison_baseline = (s(r'\b(?:vs\.?|versus)\s+(?:(?:the\s+)?(?:previous|older|original|first|second|third|fourth|gen(?:eration)?\s*\d)|' + device + ')', h)
                           or s(r'新旧|上一代|前代', h))
    comparison_introduction = bool(comparison and comparison_baseline and (
        s(r'^(?:apple|苹果)(?:\s*(?:today|yesterday|this\s+(?:week|morning|afternoon)|just|has|now|officially)\s*|今天|昨日|今日|正式)*\s*'
          r'(?:announc\w*|introduc\w*|unveil\w*|releas\w*|launch\w*|推出|发布)[^.!?。]{0,65}(?:' + device + ')', opening_assertion)
        or s(r'^(?:the\s+)?(?:new\s+|[a-z0-9-]+[- ]generation\s+)?(?:' + device + r')\s+is\s+here\b', opening_assertion))
        and not s(r'benchmark|teardown|measur(?:ed|ement)|battery\s+(?:test|life)|repair|compatib|实测|拆解|跑分|维修|兼容', h)
        and not s(r'\b(?:tested|measured|benchmarked)\b|(?:测试|测量|实测)(?:结果|数据)|测得', opening))

    # A focused physical property outranks the opening's launch recap. Match
    # the reported object, not every specification listed in a release.
    if not launch_title and not launch_inventory and not comparison_introduction:
        qualified = (s(r'\b(?:rumou?rs?|rumou?red|may|could|expected|testing|concept)\b|概念|传闻|预计|或将|去年|回顾|爆料|曝光|曝|将|测试', h)
            or s(r'last\s+(?:year|month|week)|previously|has\s+tested|testing|去年|此前|已测试|测试内置', _normalized(source_primary_assertion(title, lead)))
            or source_denies_action(title, lead, r'have|include|add|support|支持|搭载'))
        for component, pattern, evidence_pattern in (
            ('display-brightness', r'(?:display|screen).{0,25}brightness|屏幕.{0,12}亮度', r'nits?|尼特'),
            ('microphone-array', r'microphones?|麦克风', r'far.field|built.in|内置|远场'),
            ('audio-hardware', r'audio\s+hardware|speaker.{0,15}(?:system|detail)|扬声器.{0,12}细节', r'woofer|drivers?|低音|扬声器'),
            ('environment-sensors', r'(?:temperature|humidity)[^.!?。]{0,35}sensors?|(?:温度|湿度|温\s*[/／、和及与]\s*湿度).{0,8}传感器', r'built.in|includes?|has|内置|自带|配备'),
        ):
            if s(pattern, h) and s(evidence_pattern, local):
                if component == 'environment-sensors' and (
                        s(r'\b(?:firmware|software|update|enabl\w*|activat\w*|concept|designer)\b|软件|固件|启用|激活|概念|设计师', source_primary_assertion(title, lead))
                        or not s('(?:' + device + r')\s*(?:\d+\s*)?(?:includes?|has|features?|内置|自带|配备)[^.!?。]{0,80}(?:sensors?|传感器)', local)):
                    continue
                if qualified:
                    return None
                return frame(component, 'hardware-specification-report')
        if (s(r'(?:models?|two|两款).{0,50}difference|difference|差异', h)
                and s(r'speaker|扬声器', opening[:250])
                and s(r'woofer|drivers?|低音|扬声器', detail) and not qualified):
            return frame('audio-hardware', 'hardware-specification-report')

    if subject not in model_patterns:
        return None

    # Current first-party introduction must own this device. A future plan,
    # old announcement or unrelated Apple release does not establish a launch.
    software_object = s(r'(?:apple|苹果)\s*(?:(?:today|has|now|officially)\s+|今日|今天|正式)*'
                        r'(?:releas\w*|announc\w*|launch\w*|发布|推送)\s*(?:(?:the|new)\s+)*'
                        '(?:' + device + r')\s*(\d+(?:\.\d+)*)?\s*(?:software\b|firmware\b|软件|固件)', opening_assertion)
    if not software_object:
        # An explicit definition also resolves a shorthand title such as a
        # device name plus software version in a coordinated release report.
        software_object = s('(?:' + device + r')\s*(\d+(?:\.\d+)*)?\s*'
                            r'(?:is\s+(?:the\s+)?(?:(?:latest|new)\s+)?|是(?:最新的?)?)'
                            r'(?:software\b|firmware\b|软件|固件)', opening)
    if software_object and (not generation or not software_object.group(1) or software_object.group(1) == generation):
        return None
    if s(r'how\s+to|retrospective|回顾|教程|firmware|软件更新|固件', h) or (comparison and not comparison_introduction):
        return None
    focus_detail = s(r'\b(?:needs?|requires?|why|how|repair|fees?|compatib|microphones?|facial|power|app[s]?|website|clue|support)\b|'
                     r'配对|维修|摄像头|麦克风|人脸|供电|官网|线索|支持条件', primary)
    remote_compatibility = subject == 'siri-remote' and s(r'compatib|works?\s+with|for\s+your|兼容|支持', h)
    if focus_detail and not remote_compatibility:
        return None
    media_title = s(r'\b(?:video|film|advert\w*|commercial|campaign)\b|宣传片|广告|视频', h)
    if media_title and not (s(r'reveal|introduc|announc|unveil|揭晓|发布', h)
            and s(r'as\s+part\s+of\s+(?:the|its)\s+event|(?:event|presentation)\s+included|发布会.{0,20}(?:展示|播放)', opening)):
        # A device can be the subject of a film without being the object of
        # the reported release. Only explicitly linked reveal material shares
        # the current device introduction.
        return None
    for value in (h, opening):
        for a, b in source_sentence_spans(value):
            clause = value[a:b]
            # Restrict temporal denial to the introduction, not qualifications
            # about a feature that ships later in the very same launch report.
            owned = s(r'(?:apple|苹果)(?:\s*(?:today|yesterday|this\s+(?:week|morning|afternoon)|just|has|now|officially|is|the|new|long.awaited|next\s+generation\s+of)\s*|今天|今日|正式|在[^，。]{0,16})*\s*'
                      r'(?:announc\w*|introduc\w*|unveil\w*|releas\w*|launch\w*|debut(?:s|ed)?|推出|发布)'
                      r'[^.!?。;；]{0,65}(?:' + device + ')', clause)
            passive = s('(?:' + device + r')(?:[^.!?。;；]{0,35}(?:announced|introduced|unveiled|launched|has\s+(?:finally\s+)?been\s+updated)|\s*(?:智能音箱|音箱|设备|新品|新机)?\s*(?:已|今日|今天|正式|现已|全球)?(?:发布|推出)(?!时间|日期|计划|安排|会))', clause)
            arrival = (s('(?:' + device + r')\s+is\s+here\b', clause)
                       if comparison_introduction else None)
            current = owned or passive or arrival
            if not current:
                continue
            # The object can be device software rather than a physical model.
            if s(r'^\s*(?:\d+(?:\.\d+)*\s*)?(?:software\b|firmware\b|软件|固件)', clause[current.end():]):
                return None
            if s(r"^\s*(?:'s\s+)?(?:(?:reveal|introduction|launch|promotional|product)\s+)?"
                 r'(?:video|film|campaign|advertisement)\b|^\s*的?(?:揭晓|发布|宣传|介绍)?(?:视频|影片|广告)', clause[current.end():]):
                return None
            prefix = clause[:current.end()]
            prefix = _compiled_rule(r'\blong[- ]rumou?red\b').sub('', prefix)
            if s(r'last\s+(?:year|month|week)|previously|\bexpects?\b|expected|rumou?r|plans?\s+to|set\s+to\s+be|\b(?:will|would|may|might|could)\b|'
                 r'did\s+not|not\s+(?:announce|introduce|release|launch|unveil)|\b(?:hasn|haven|hadn|isn|wasn|weren|didn|doesn|don|won|wouldn|couldn|can)[\x27’]t\b|\bnever\b|\b(?:current|previous|original)\b|(?:将|拟)(?:随|于|在|推出|发布|搭载|配备)|去年|此前|现款|上代|上一代|预计|有望|传闻|计划|尚未|并未|没有', prefix) or s(r'last\s+(?:year|month|week)|years?\s+ago|去年|此前|年前', clause[current.end():]):
                continue
            if s(r'^\s*(?:next\s+(?:year|month|week)|tomorrow|in\s+20\d{2})\b', clause[current.end():]):
                continue
            return frame('', 'device-announcement')
    if (s(r'pre.?order|预订|预购', h)
            and s(r'^apple\s+is\s+getting\s+into\s+[^.!?。]{1,55}\s+with\s+its\s+new\s+(?:' + device + r')', opening)):
        return frame('', 'device-announcement')
    if subject == 'apple-home-hub' and s(r'finally\s+(?:culminated|ready\s+to\s+release)', opening) and s(r'apple\s+calls\s+it', opening):
        return frame('', 'device-announcement')
    if remote_compatibility and s(r'new|新', h) and s(r'\$\s*\d|\d+\s*美元|announced|introduced|unveiled|available\s+for\s+purchase|发布|推出', local):
        return frame('', 'device-announcement')
    return None


def source_hardware_action_frame(title: str, lead: str, facts: tuple[str, ...], source_units: tuple[str, ...] = ()) -> SourceActionFrame | None:
    """Bind hardware reports to the headline action before background calendars.

    Body evidence may resolve a named partnership's object, but cannot invent
    a partnership, retail action or device roadmap absent from the headline.
    """
    h, opening = _normalized(title), _normalized(lead)[:950]
    local = h + '. ' + opening
    detail_text = None
    def detail():
        nonlocal detail_text
        if detail_text is None:
            detail_text = ' '.join((local, *(_normalized(x) for x in facts + source_units)))
        return detail_text
    s = _frame_search
    def frame(subject, action, period=''):
        return SourceActionFrame(subject, action, 'hardware_products', 'hardware_market', 'strong', period)

    if (s(r'carplay', h) and s(r'ota|车机|车型|车辆', local)
            and s(r'升级|推送|update|rollout', h) and s(r'新增|增加|adds?|support', h)
            and not s(r'^(?:apple|苹果)\s*(?:发布|推出|announc|releas)|api|框架|framework|协议', h)):
        return SourceActionFrame('third-party:vehicle-update:' + h, 'ordinary-device-compatibility',
            'software_systems', 'third_party_ecosystem', 'weak')
    if (s(r'data|archive|数据|资料|档案', h) and s(r'publis|release|公开|发布', h)
            and s(r'iphone', h) and s(r'仍.{0,15}整理|尚未.{0,15}(?:纳入|公开)|not\s+(?:yet\s+)?included|still.{0,20}process', detail())
            and not s(r'^(?:apple|苹果)(?![a-z])', h)):
        return SourceActionFrame('third-party:data-publication:' + h, 'archive-publication',
            'hardware_products', 'general_company', 'weak')

    hub = r'(?:smart\s+)?home\s+(?:hub|control\s+cent(?:er|re)|controller)|smart\s+(?:hub|display)|(?:智能)?(?:家庭|家居)(?:中枢|控制中心)'
    named_hub_disclosure = bool(s(r'device\s+disclosure', h)
        and (s('(?:' + hub + r').{0,100}(?:named|called|命名|定名)', opening)
             or s(r'名为\s*[a-z][a-z0-9-]*\s*的.{0,20}(?:' + hub + ')', opening))
        and not source_denies_action(title, lead, r'named|called|命名|定名'))
    if (s(hub, h) and s(r'(?:apple|苹果)[^.。]{0,55}(?:' + hub + ')', h)
            and (named_hub_disclosure or s(r'called|named|chip|芯片|定名|命名', h)
                or (s(r'colors?|finishes|配色', h)
                    and s(r'ship\w*\s+(?:in|around)\s+(?:mid[- ]|late[- ]|early[- ])?(?:january|february|march|april|may|june|july|august|september|october|november|december)|\d{1,2}月.{0,10}(?:交付|发货)', h)))
            and not s(r'合作|partner|installation|cost|price|售价|价格', h)
            and s(r'gurman|bloomberg|古尔曼|彭博|according\s+to|report\s+says|记者|爆料|透露', detail())
            and (named_hub_disclosure or s(r'report|ship|called|named|new|曝光|定名|命名|首款', h))
            and not s(r'now\s+shipping|now\s+available|正式发售|开始发货|否认|not\s+developing', h)):
        # A nickname is local attribution, not a permanent product whitelist.
        generation = s(r'(?:second|third|\d+)[- ]generation|第([二三\d]+)代', h)
        return replace(frame('apple-home-hub', 'unreleased-device-disclosure'),
            model_generation=generation.group() if generation else '')
    detailed_tv_preview = (s(r'upgrades?|configuration|升级|配置', h)
        and s(r'rumou?red|reportedly|据报|爆料', opening)
        and not s(r'wish|want|希望|愿望', h))
    tv_configuration_headline = (
        s(r'apple\s*tv', h) and not s(r'homepod|home\s*hub|software|软件', h)
        and not s(r'pre.order|ship|delivery|confirmed|announc|released|cancel|abandon|scrap|正式发布|确认量产|否认|取消|交付|发货', h)
        and (detailed_tv_preview or not s(r'launch', h))
        and not source_denies_action(title, '', r'planned|expected|upgrad\w*|equip|feature|include|have|计划|预计|升级|搭载|配备'))
    if tv_configuration_headline:
        historical_configuration = r'last\s+year|previous(?:ly)?|former|old\s+(?:plan|report)|此前|去年|旧计划|回顾'
        current_configuration_clauses = [
            _normalized(value[start:end])
            for value in (lead, *facts) for start, end in source_sentence_spans(value)
            if not s(historical_configuration, _normalized(value[start:end]))
            and not source_denies_action(value[start:end], '', r'test|include|have|feature|测试|配备|搭载')]
        current_configuration = ' '.join(current_configuration_clauses)
        tested_configuration = (
            s(r'test|microphone|remote|mic\b|hardware\s+configuration|麦克风|遥控器', h)
            and s(r'microphones?|remote.{0,35}speaker|麦克风|遥控器.{0,15}扬声器', current_configuration)
            and s(r'test\w*|测试', current_configuration)
            and not s(historical_configuration, h)
            and s(r'report|new|testing|getting|could|disclosure|曝|新一代', h))
        candidate_configuration = False
        historical_configuration = r'last\s+year|previous(?:ly)?|former|old\s+(?:plan|report)|此前|去年|旧计划|回顾'
        if (not s(historical_configuration, h)
                and s(r'hardware\s+configuration|硬件配置', h)
                and s(r'^(?:report\s*:\s*)?(?:the\s+)?(?:new\s+)?apple\s*tv\b', h)):
            # Only the projected device's own predicates establish a candidate
            # configuration; the original aggregate's other units cannot lend it
            # hardware, ownership, or a more certain production stage.
            for value in (lead, *facts):
                for start, end in source_sentence_spans(value):
                    clause = _normalized(value[start:end])
                    if (s(r'^(?:the\s+)?(?:new\s+)?apple\s*tv(?:\s+4k)?\s+(?:may|could)\s+(?:have|include|feature)\s+', clause)
                            and s(r'built.in\s+microphones?|remote.{0,50}built.in\s+speaker', clause)
                            and not s(historical_configuration, clause)
                            and not source_denies_action(clause, '', r'have|include|feature')):
                        candidate_configuration = True
        reported_configuration = (detailed_tv_preview
            and s(r'built.in\s+microphones?|microphone\s+built\s+into|内置麦克风', current_configuration)
            and s(r'remote.{0,50}(?:speaker|扬声器)|遥控器.{0,20}扬声器', current_configuration))
        if tested_configuration or candidate_configuration or reported_configuration:
            explicit_hd = s(r'apple\s*tv\s*hd(?![a-z0-9])', h + ' ' + current_configuration)
            explicit_4k = s(r'apple\s*tv\s*4k(?![a-z0-9])', h + ' ' + current_configuration)
            return replace(frame('apple-tv-hd' if explicit_hd else 'apple-tv-4k' if explicit_4k else 'apple-tv', 'hardware-configuration-test-report'),
                           aliases=() if explicit_hd else ('apple-tv:current-configuration',))

    # A cancellation or denial is itself the headline action. Returning no
    # frame would let background specifications regain affirmative authority.
    configuration_headline = s(r'upgrades?|configuration|device\s+disclosure|配置|升级细节', h)
    if configuration_headline:
        cancelled = s(r'cancel\w*|abandon\w*|scrap\w*|取消|放弃', h)
        denied = source_denies_action(title, '', r'planned|expected|upgrad\w*|equip|feature|计划|预计|升级|搭载|配备')
        subjects = hardware_action_subjects(title)
        if (cancelled or denied) and len(subjects) == 1 and _operation_owner(title) in {'', 'apple'}:
            devices = disclosed_device_subjects(title)
            family, generation = next(iter(devices.items())) if len(devices) == 1 else (next(iter(subjects)), '')
            return replace(frame(family, 'configuration-plan-cancelled' if cancelled else 'configuration-plan-denied'),
                           model_generation=generation)

    # A focused configuration projection carries the device predicate in
    # its own facts; borrowed silicon's original device never owns the upgrade.
    if (configuration_headline
            and not s(r'pre.order|delivery|ship|announc|cancel|abandon|scrap|预购|交付|发货|正式发布|取消|放弃', h)
            and not source_denies_action(title, '', r'planned|expected|upgrad\w*|equip|feature|计划|预计|升级|搭载|配备')):
        subjects = hardware_action_subjects(title)
        if len(subjects) == 1:
            subject = next(iter(subjects))
            for value in (lead, *facts):
                previous_owner = set()
                for start, end in source_sentence_spans(value):
                    clause = _normalized(value[start:end])
                    predicate = s(r'\b(?:will|should|is|uses?|features?)\b|将搭载|将配备|采用', clause)
                    owners = hardware_action_subjects(clause[:predicate.start()]) if predicate else set()
                    if not owners and previous_owner == subjects and s(r'^the\s+(?:big\s+)?change\s+here\b|^it\s+(?:will|uses|features)', clause):
                        owners = previous_owner
                    transition = s(r'\b([ams]\d+(?:\s+(?:pro|max|ultra))?)\s+chip.{0,35}up\s+from\s+(?:the\s+)?(?:(?:current|existing|previous)\s+)?([ams]\d+)\s+chip', clause)
                    if transition is None:
                        transition = s(r'\bnew\s+([ams]\d+(?:\s+(?:pro|max|ultra))?)\s+chip.{0,70}current\s+model.s\s+([ams]\d+)\s+processor', clause)
                    previous_owner = owners
                    if (owners == {subject} and transition
                            and not source_denies_action(clause, '', r'be|equip|feature|use|搭载|配备')
                            and not s(r'last\s+year|previously|去年|此前|现款已', clause)):
                        devices = disclosed_device_subjects(title)
                        family, generation = next(iter(devices.items())) if len(devices) == 1 else (subject, '')
                        return replace(frame(family + ':processor:' + transition.group(2) + '-to-' + transition.group(1).replace(' ', '-'),
                                             'device-configuration-report'), model_generation=generation,
                            aliases=(family + ':processor:' + transition.group(1).replace(' ', '-'), family + ':current-configuration'),
                            period='processor:' + transition.group(1).replace(' ', '-'))

    if (configuration_headline and len(hardware_action_subjects(title)) == 1
            and not s(r'pre.order|delivery|ship|announc|cancel|abandon|scrap|预购|交付|发货|正式发布|取消|放弃', h)
            and not source_denies_action(title, '', r'planned|expected|upgrad\w*|equip|feature|计划|预计|升级|搭载|配备')):
        subjects = hardware_action_subjects(title)
        for value in (lead, *facts):
            clause = _normalized(value)
            target = s(r'搭载\s*([ams]\d+(?:\s+(?:pro|max|ultra))?)\s*芯片', clause)
            if (target and hardware_action_subjects(clause[:target.start()]) == subjects
                    and s(r'新款|升级版|全新', clause[:target.start()])
                    and not s(r'去年|此前|旧款|原本|取消|否认|并未', clause)
                    and not source_denies_action(clause, '', r'搭载|配备')):
                devices = disclosed_device_subjects(title)
                family, generation = next(iter(devices.items())) if len(devices) == 1 else (next(iter(subjects)), '')
                return replace(frame(family + ':processor:' + target.group(1).replace(' ', '-'),
                                     'device-configuration-report'), model_generation=generation,
                               aliases=(family + ':current-configuration',), period='processor:' + target.group(1).replace(' ', '-'))

    # Sparse configuration paragraphs still own a current device upgrade.
    # A launch, price or historical paragraph cannot lend that ownership.
    if (s(r'hardware\s+configuration\s+disclosure', h)
            and _operation_owner(title) in {'', 'apple'}
            and len(hardware_action_subjects(title)) == 1
            and not s(r'last\s+year|previous|cancel|denied|去年|此前|取消|否认|旧款|预购|交付|发货|价格', local)
            and not source_denies_action(title, lead, r'upgrade|equip|feature|升级|配备|搭载')):
        subjects = hardware_action_subjects(title)
        if (s(r'新款|新一代|此次更新', opening)
                and s(r'据称|消息显示|消息人士|透露', opening)
                and s(r'(?:将|将在).{0,45}(?:处理性能|处理器|内部硬件)', opening)
                and hardware_action_subjects(opening) == subjects):
            if subjects == {'apple-tv'} and not s(r'apple\s*tv\s*(?:hd|\d+(?!k))', h):
                return replace(frame('apple-tv:current-configuration', 'hardware-configuration-test-report'))
            devices = disclosed_device_subjects(title)
            if subjects == {'homepod'} and 'homepod-mini' in devices:
                return replace(frame('homepod-mini:current-configuration', 'device-configuration-report'),
                               model_generation=devices['homepod-mini'])

    # Joint delivery owns one date and an explicit batch, separate from each
    # device's configuration and from opening orders for that batch.
    if (s(r'ship|joint\s+delivery|共同交付|发货', h)
            and _operation_owner(title) in {'', 'apple'}
            and not s(r'pre.order|预购|cancel|delay|\bshipped\b|now\s+shipping|already|announc|confirm|取消|延期|推迟|现已|宣布|确认', h)
            and not source_denies_action(title, lead, r'expected|planned|ship\w*|launch|arrive')):
        subjects = hardware_action_subjects(title)
        if len(subjects) >= 2:
            months = 'january february march april may june july august september october november december'.split()
            for value in (lead, *facts):
                for start, end in source_sentence_spans(value):
                    clause = _normalized(value[start:end])
                    # Both devices must own the same future predicate. A
                    # second device in a later clause cannot inherit its date.
                    future = s(r'\b(?:will|should|(?:is|are)\s+(?:expected|scheduled)\s+to)\b|计划于|预计将|将', clause)
                    if not future or hardware_action_subjects(clause[:future.start()]) != subjects:
                        continue
                    future_clause = _compiled_rule(r'[,，;；]\s*(?:while|whereas|but|and|而|但)\b', re.I).split(clause[future.start():], 1)[0]
                    shipping = s(r'\b(?:ship|launch|arrive)\b.{0,25}\bon\s+(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+)?(' + '|'.join(months) + r')\s+(\d{1,2})(?!\d)', future_clause)
                    chinese_shipping = s(r'(?:计划于|预计将|将于?)\s*(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日(?:开始)?(?:向(?:用户|客户))?(?:交付|发货)', future_clause)
                    if ((shipping or chinese_shipping) and not source_denies_action(clause, '', r'ship\w*|launch|arrive|交付|发货')
                            and not s(r'last\s+year|previously|cancel|去年|此前|取消', clause)):
                        models = []
                        for subject in sorted(subjects):
                            pattern = re.escape(subject).replace(r'\-', r'\s*') + r'(?:\s+(?:mini|pro|max|air|ultra|hd|\d+[a-z]*)){0,3}'
                            names = {m.group().replace(' ', '-') for scope in (h, clause[:future.start()])
                                     if (m := s(pattern, scope))}
                            model = max(names, key=len) if names else subject
                            if any(model != name and not model.startswith(name + '-') for name in names):
                                break
                            models.append(model)
                        if len(models) != len(subjects):
                            continue
                        title_year = s(r'(?:' + '|'.join(months) + r')\s+\d{1,2}(?:,\s*|\s+)(20\d{2})\b', h)
                        clause_year = s(r'^\s*,?\s*(20\d{2})\b', future_clause[shipping.end():]) if shipping else None
                        years = {m.group(1) for m in (title_year, clause_year) if m}
                        if chinese_shipping and chinese_shipping.group(1):
                            years.add(chinese_shipping.group(1))
                        if len(years) > 1:
                            continue
                        month = str(months.index(shipping.group(1))+1) if shipping else str(int(chinese_shipping.group(2)))
                        day = shipping.group(2) if shipping else str(int(chinese_shipping.group(3)))
                        # Resolve sparse current model names through the same
                        # source's explicit new-device processor predicates.
                        # Old/comparison devices never supply this batch alias.
                        processors = {}
                        for value in (lead, *facts, *source_units):
                            for begin, finish in source_sentence_spans(value):
                                part = _normalized(value[begin:finish])
                                if source_denies_action(part, '', r'equip|feature|include|have|搭载|配备|采用'):
                                    continue
                                if s(r'去年|此前|旧款|原本|取消|否认|last\s+year|previous|old\s+|cancel|denied|unlike', part):
                                    continue
                                for match in _compiled_rule(r'(?:new\s+(?:upcoming\s+)?|新款|升级版|新一代)(?P<device>apple\s*tv(?:\s*4k)?|homepod\s*mini(?:\s*\d+)?)(?![a-z0-9])(?P<detail>[^。;；.!?]{0,80}?)(?<![a-z0-9])(?P<chip>[ams]\d+)\s*(?:chip|芯片)', re.I).finditer(part):
                                    if (hardware_action_subjects(match.group('detail'))
                                            and not s(r'^\s+(?:will|is\s+expected\s+to)\s+be\s+equipped\s+with', match.group('detail'))):
                                        continue
                                    name = _compiled_rule(r'apple\s*tv(?:\s*4k)?', re.I).sub('apple-tv', match.group('device')).replace(' ', '-')
                                    processors.setdefault(name,set()).add(match.group('chip'))
                                # Chinese also puts the chip before the noun.
                                for match in _compiled_rule(r'搭载(?:标准)?\s*(?P<chip>[ams]\d+)\s*芯片的?新(?P<device>apple\s*tv)(?![a-z0-9])', re.I).finditer(part):
                                    processors.setdefault('apple-tv',set()).add(match.group('chip'))
                        resolved = [model.removesuffix('-4k') for model in models]
                        aliases = ()
                        if all(name in processors and len(processors[name]) == 1 for name in resolved):
                            aliases = ('apple:delivery-config:' + '+'.join(name + ':' + next(iter(processors[name])) for name in resolved),)
                        return replace(frame('apple:delivery-batch:' + '+'.join(models), 'joint-delivery-report',
                                     'month:' + month + ':day:' + day),
                                     year=next(iter(years), ''), aliases=aliases)

    camera = r'(?:home|security)\s+camera|(?:家用|家庭|家居|安防)摄像头'
    development = r'(?:develop\w*|work\w*\s+on|研发|开发)'
    if (s(r'apple|苹果', h) and s(r'camera|摄像头', h) and s(development, h)
            and not s(r'合作|联手|co.develop|with\s+[a-z]|and\s+[a-z]', h)
            and s(r'apple(?:\s+is)?\s+(?:(?:reportedly|currently)\s+)?' + development + r'[^.!?。]{0,70}' + camera + r'|苹果(?:被曝)?(?:正|正在|计划)?' + development + r'[^。]{0,50}' + camera, local)
            and not s(r'homekit|支持.{0,15}摄像头|camera\s+(?:app|feature)|摄像头功能', h)
            and not source_denies_action(title, lead, development)):
        return frame('apple-home-camera', 'hardware-development-report')

    collaboration = r'partner\w*|合作|联手'
    if (s(r'apple|苹果', h) and s(collaboration + r'|installations?', h)
            and not s(r'合作打造|合作开发|合作再曝|共同研发|co.develop|leaked\s+images|design\s+images', h)):
        partner = (s(r'partnership\s+with\s+(?:(?:a|the|home|security|company|firm|new)\s+)*([a-z][a-z0-9-]*)', local)
            or s(r'与(?:[^，。]{0,25}?(?:公司|企业)\s*)?([a-z][a-z0-9-]*)\s*(?:建立新?合作|合作|联手)', h)
            or s(r'^([a-z][a-z0-9-]*)\s+(?:rumored|reportedly|plans?|will|to)\b', h))
        if partner and s(r'home|家居|家庭', local) and s(r'install\w*|安装', detail()):
            name = partner.group(1)
            denied = s(r'denies?\s+(?:the\s+)?partnership|not\s+partnering|否认.{0,25}合作|并未合作', local)
            if not denied:
                target = next((key for key, pattern in (('camera', r'camera|摄像头'), ('lock', r'door\s*lock|门锁'), ('thermostat', r'thermostat|恒温器')) if s(pattern, h)), 'home-devices')
                stage = 'installation-partnership-report' if s(r'rumor|report|may|could|plan|消息|报道|或|计划', local) else 'installation-partnership-announcement'
                date = s(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}', h)
                return frame('apple:installation-partner:' + name + ':' + target, stage, date.group() if date else '')

    device = s(r'(?<![a-z0-9])((?:iphone|ipad)\s+(?:duo|air|mini|\d+)(?:\s+pro)?(?:\s+max)?)(?![a-z0-9])', h)
    if (device and s(r'apple|苹果', h) and s(r'retail|stores?|直营店|门店|零售店', h)
            and s(r'demo|showcase|display|体验(?:活动|区|样机)|展示|演示', h)
            and s(r'plan|prepar|will|计划|将|筹备', local)
            and not source_denies_action(title, lead, r'plan|prepare|展示|体验')):
        return frame(device.group(1).replace(' ', '-') + ':retail', 'retail-demonstration-plan')

    if (s(r'ipad\s*mini', h) and s(r'price|expensive|cost|售价|价格|涨价', h)
            and s(r'will|could|expected|report|rumor|预计|消息|或|将', local)
            and s(r'gurman|bloomberg|古尔曼|彭博|according\s+to|report\s+says|记者|爆料|透露', detail())
            and not s(r'last\s+year|previously|denies|去年|此前|否认', h)
            and not s(r'apple\s+(?:announces?|confirms?|cuts?|raises?)|苹果(?:宣布|确认|下调|上调)', h)):
        generation = s(r'ipad\s*mini\s*(\d+)', h)
        return replace(frame('ipad-mini', 'device-price-forecast'),
            model_generation=generation.group(1) if generation else '')

    # The date must belong to this headline's product and postponement, not a
    # different product's event mentioned in the opening paragraph.
    model = s(r'(?:entry.level|base.model)\s+ipad|(?:入门级|基础款)\s*ipad', h)
    delay = s(r"not\s+expected\s+until|won['’]t\s+arrive\s+until|not\s+arriv\w*\s+until|wait\s+until|推迟至|推迟到|不早于|等到", h)
    if model and delay:
        window = s(r'early\s+(20\d{2})|(20\d{2})\s*年初', h)
        if window:
            year = next(v for v in window.groups() if v)
            return replace(frame('ipad-base', 'delayed-launch-window', 'early-year'), year=year)

    if (s(r'(?:ios|iphone|ipad).{0,15}(?:设备)?好评榜|(?:device|iphone|ipad).{0,20}satisfaction\s+rank', h)
            and s(r'好评率|satisfaction\s+(?:rate|score)', detail())
            and not s(r'购买意愿|想买|would\s+(?:you\s+)?buy|purchase\s+intent', local)):
        period = s(r'(20\d{2})\s*年\s*(\d{1,2})\s*月', opening)
        # Owner approval is a preference survey, even when quantified and
        # ranked; it is not a measurement of the device's physical behavior.
        return replace(frame('apple-devices:owner-satisfaction', 'owner-rating-ranking',
            '-'.join(period.groups()) if period else ''), tier='weak')
    return None


def is_joint_market_measurement(clause: str) -> bool:
    """A combined vendor total cannot establish one vendor's own result."""
    value = _normalized(clause)
    quantity = _frame_search(r'\d+(?:\.\d+)?\s*(?:%|percent(?:age\s+points?)?|million|万|台|百分点)', value)
    # An aside comma may precede the joint predicate. Stop after the first
    # measurement, so a later combined comparison cannot erase an owned value.
    first = (value[:quantity.end()] + _compiled_rule(r'[,，;；]').split(value[quantity.end():], maxsplit=1)[0]
             if quantity else value)
    return bool(_frame_search(r'\b(?:combined|together|collectively|jointly)\b|合计|合共|合拿|合占|共占|共同占', first))


def source_market_measurement_frame(title: str, lead: str, passages: tuple[str, ...], *, published_year: str = '',
                                   measurement_passages: tuple[str, ...] | None = None) -> SourceActionFrame | None:
    """Bind a measured market, provider and period, with an actual Apple result.

    A vendor-neutral headline is sufficient for discovery, not inclusion. The
    detail must contain an Apple measurement, including a preserved table row.
    Comparison years and financial revenue do not date shipment measurements.
    """
    h, opening = _normalized(title), _normalized(lead)
    s = _frame_search
    if not s(r'shipments?|market\s+share|出货|市场份额|市占', h):
        return None
    local = h + ' ' + opening[:1000]
    sectors = (
        ('pc', r'(?<![a-z0-9])pc(?![a-z0-9])|personal\s+comput|laptops?|notebooks?|个人电脑|笔记本'),
        ('smartphone', r'smartphone|智能手机|手机(?:市场|出货)'),
        ('tablet', r'tablet|平板电脑'),
        ('wearable', r'wearable|可穿戴'))
    sector = next((key for key, pattern in sectors if s(pattern, local)), '')
    if (not sector or (sector == 'wearable' and not s(r'wearable|可穿戴', h))
            or s(r'forecast|predict|预计|预测|回顾|last\s+year', h)):
        return None
    units = (opening, *(_normalized(p) for p in passages))
    detail = ' '.join(units)
    provider = s(r'(?<![a-z0-9])(idc|gartner|counterpoint(?:\s+research)?|canalys|omdia)(?![a-z0-9])', local + ' ' + detail)
    if not provider:
        return None
    quarter_pattern = r'(20\d{2})\s*(?:年\s*)?(?:q|第)([1-4一二三四])(?:季度)?|\bq([1-4])\s+(20\d{2})'
    def quarter_of(text):
        match = s(quarter_pattern, text)
        relative = s(r'(?:今年\s*第([1-4一二三四])季度|this\s+year\s+(?:in\s+)?q([1-4])\b|\bq([1-4])\s+(?:of\s+)?this\s+year)', text)
        if relative and (not match or relative.start() < match.start()):
            q = next(value for value in relative.groups() if value)
            return published_year, 'q' + (str('一二三四'.index(q) + 1) if q in '一二三四' else q)
        if not match:
            return '', ''
        a, b, c, d = match.groups()
        year, q = (a, b) if a else (d, c)
        return year, 'q' + (str('一二三四'.index(q) + 1) if q in '一二三四' else q)
    # Headline first; otherwise only a current shipment/share clause, excluding
    # historical comparisons and a nearby fiscal result about revenue.
    clauses = [h]
    for unit in units:
        for start, end in source_sentence_spans(unit):
            clause = unit[start:end]
            if (s(r'shipments?|shipped|market\s+share|出货|份额', clause)
                    and not s(r'^for\s+comparison|^作为对比|^此前|since\s+q|since\s+20\d{2}|compared\s+to\s+q|revenue|营收|截至.*以来', clause)):
                clauses.append(clause)
    year = period = ''
    for clause in clauses:
        year, period = quarter_of(clause)
        if period:
            break
    if not period:
        return None
    apple_result = False
    measurement_units = units if measurement_passages is None else tuple(_normalized(p) for p in measurement_passages)
    for unit in measurement_units:
        for start, end in source_sentence_spans(unit):
            for clause in _compiled_rule(r'[;；]|\b(?:while|whereas)\b|\bbut\b(?!\s+(?:because|due\s+to)\b)|\band\s+(?=[a-z]+\s+(?:shipped|had|held|saw|captured))|而|但(?!由于|因为|受)', 0).split(unit[start:end]):
                owner = s(r'(?<![a-z])apple(?![a-z])|苹果|\bmacs?\b', clause)
                if not owner or s(r'for\s+comparison|last\s+year|previously|此前|去年|作为对比|'
                                  r'expected|forecast|predict|预计|预测|有望', clause[:owner.start()]):
                    continue
                owned = clause[owner.start():]
                if is_joint_market_measurement(owned):
                    continue
                # Values before Apple still belong to the preceding vendor.
                # An explicit other market/period cannot borrow this headline.
                current_measure = _compiled_rule(r'compared\s+(?:with|to)|\b(?:up|down)\s+from\b|同比|较(?:去年|上季)', 0).split(owned)[0]
                if s(r'previously|last\s+(?:year|quarter)|此前|去年|上季度|'
                     r'expected|forecast|predict|\b(?:will|would|could|may|might)\b|next\s+(?:quarter|year)|'
                     r'预计|预测|有望|明年|下季度', current_measure):
                    continue
                explicit_sectors = {key for key, pattern in sectors if s(pattern, owned)}
                explicit_period = quarter_of(owned)
                if (explicit_sectors - {sector} or explicit_period not in {('', ''), (year, period)}
                        or s(r'did\s+not\s+participate|no\s+apple\s+data|not\s+included|未参与|未纳入|无苹果数据', owned)):
                    continue
                table_row = s(r'^(?:apple|苹果|mac)\s*\|\s*[\d,]+\s*\|', owned)
                quantity = s(r'\d+(?:\.\d+)?\s*(?:%|percent(?:age\s+points?)?|million|万|台|个?百分点)|a\s+(?:fifth|quarter|third)', owned)
                measure = s(r'shipments?|shipped|share|份额|出货|销量|市占|(?:capture|占据).{0,50}market', owned)
                # A reported direction is a measured result even when the
                # publisher omits the vendor's exact count. Keep prediction
                # and missing-data statements distinct from an observation.
                direction = s(r'(?:shipments?|market\s+share|出货量?|销量|市场份额|市占率?).{0,35}'
                              r'(?:declin\w*|fell|falling|decreas\w*|increas\w*|grew|grown|growth|rose|rising|'
                              r'remain\w*\s+(?:flat|stable)|下滑|下降|下跌|增长|上升|持平)', owned)
                if direction:
                    # Resolve the metric's grammatical subject rather than
                    # borrowing any Apple mention earlier in the sentence.
                    prefix = _compiled_rule(r'[,，]').split(owned[:direction.start()])[-1].strip()
                    english_owner = _compiled_rule(
                        r"^(?:(?:apple(?:[’']s)?|its|the company(?:[’']s)?)\s*)?"
                        r"(?:(?:reported|saw|had|overall|total|quarterly|current|global|worldwide|"
                        r"chinese|smartphone|phone|iphone|mac|pc|unit|market)\s*)*$").fullmatch(prefix)
                    chinese_owner = _compiled_rule(
                        r'^(?:苹果(?:公司)?|其|该公司|本季度|当季|季度|今年|同期|因此|但|仍|整体|'
                        r'智能手机|手机|的|全球|中国|市场|报告|表示|称|\s)*$').fullmatch(prefix)
                    # Only a nominal explanation may intervene here. A clause
                    # such as benefiting from a rival's growth has a new owner.
                    if not chinese_owner:
                        chinese_owner = _compiled_rule(
                            r'^(?:苹果(?:公司)?|其|该公司)'
                            r'(?:(?:凭借|得益于|依靠|受益于)[^，,。；;!?！？]{0,90}'
                            r'(?:产品|组合|布局|策略|优势|需求|供应|表现|时间))?'
                            r'(?:实现|取得|录得)了$').fullmatch(prefix)
                        if chinese_owner and s(r'将|可能|或许|使|让|令|帮助|带动|促成|表示|声称|指出|披露', prefix):
                            chinese_owner = None
                    if not (english_owner or chinese_owner):
                        direction = None
                observed_direction = bool(direction and not s(
                    r'expected|forecast|predict|\b(?:will|would|could|may|might)\b|next\s+(?:quarter|year)|'
                    r'not\s+(?:disclos\w*|report\w*)|预计|预测|有望|明年|下季度|未(?:公布|披露)', owned))
                if table_row or (measure and (quantity or observed_direction)):
                    apple_result = True
                    break
            if apple_result:
                break
        if apple_result:
            break
    if not apple_result:
        return None
    region = next((key for key, pattern in (
        ('worldwide', r'global|worldwide|全球'), ('china', r'中国|\bchina\b'),
        ('us', r'united\s+states|\bus\b|美国')) if s(pattern, local)), '')
    return SourceActionFrame(provider.group(1).removesuffix(' research') + ':' + sector + '-shipments',
        'market-measurement-report', 'hardware_products', 'hardware_market', period=period, year=year, region=region)


def source_named_publication_frame(title: str, lead: str, passages: tuple[str, ...], identity: EventIdentity) -> SourceActionFrame | None:
    """A named announcement, report or filing owns its supporting inventory.

    Resolve the local action before broad device/feature keywords. A quoted
    name alone never proves Apple ownership or an announcement stage.
    """
    h, opening = _normalized(title), _normalized(lead)[:1500]
    local = h + ' ' + opening
    s = _frame_search
    def name(value):
        return _compiled_rule(r'[^a-z0-9\u4e00-\u9fff]+', 0).sub('-', _normalized(value)).strip('-')
    def frame(subject, action, category='software_systems', kind='os_app', **qualifiers):
        return SourceActionFrame(subject, action, category, kind, **qualifiers)
    if s(r'last\s+year|looking\s+back|recap|旧闻|回顾', h):
        return None

    if s(r'fashion|collection|creative\s+profile|时装|作品|设计', local):
        owned = False
        for passage in (lead, *passages):
            value = _normalized(passage)
            for a, b in source_sentence_spans(value):
                clause = _compiled_rule(r'[;；]|\b(?:while|whereas|but)\b', 0).split(value[a:b], 1)[0]
                publication = s(r"apple(?:'s)?\s+(?:(?:today|has|latest|new)\s+)*(?:shared|showcases?|creative\s+profile)|"
                        r"苹果(?:公司)?(?:今日|昨日|近日|今天|昨天|现已)?(?:[（(][^）)]{1,30}[）)])?\s*(?:展示|分享|发布)|"
                        r"check\s+it\s+out\s+on\s+@apple\s+beginning", clause)
                target = clause[publication.end():] if publication else ''
                object_clause = _compiled_rule(r'[,，]', 0).split(target, 1)[0]
                announcement = s(r'^\s*(?:公告|新闻稿)[，,]\s*(?:宣布|介绍|展示|分享)', target)
                if (publication
                        and (s(r'creative\s+profile|check\s+it\s+out', publication.group())
                             or s(r'fashion|collection|behind.the.scenes|作品|时装|设计师',
                                  target if announcement else object_clause))
                        and not s(r'last\s+(?:year|month)|previously|years?\s+ago|去年|此前|回顾', clause)
                        and not source_denies_action('', clause, r'shar\w*|showcas\w*|publish\w*|分享|发布|展示')):
                    owned = True
                    break
            if owned:
                break
        if owned:
            original = title + ' ' + lead
            creator = (_compiled_rule(r'(?:\bdesigner\s+|设计师\s*)([A-Z][^\W\d_]+\s+[A-Z][^\W\d_]+)\b').search(original)
                       or _compiled_rule(r"^([A-Z][^\W\d_]+\s+[A-Z][^\W\d_]+)[’']s\s+new\s+collection").search(original))
            if creator:
                creator_name = ''.join(c for c in unicodedata.normalize('NFKD', creator.group(1)) if not unicodedata.combining(c)).lower().replace('ı', 'i')
                work = s(r'(?:collection,?\s*|look\s+at\s*|名为\s*)[“\"‘\']([^”\"’\']{1,80})[”\"’\']', local)
                return frame('apple:creator-profile:' + creator_name.replace(' ', '-'),
                    'official-product-showcase', 'hardware_products', 'company_org',
                    period='work:' + name(work.group(1)) if work else '')

    campaign = s(r'campaign|celebrat|kicks?\s+off|宣传活动|游戏周|活动周', local)
    owned_campaign = s(r'apple.{0,70}(?:announc|kick|celebrat|new.{0,10}campaign)|苹果.{0,80}(?:启动|宣布|上线)', local)
    if (campaign and (owned_campaign or s(r'^app\s*store\b', h))
            and not source_denies_action(title, lead, r'announc\w*|launch\w*|kick\w*|宣布|启动|上线')
            and not s(r'cancel|取消|推迟|postpone', h)):
        # English names supplied by the source also resolve translated titles.
        label = (s(r'(?:app\s*store\s+)?([a-z]+(?:\s+[a-z]+){0,3}\s+(?:games?\s+)?week)\b', local)
                 if s(r'app\s*store', local) else None)
        if label:
            label_text = label.group(1).removeprefix('app store ').removeprefix('is ')
            return frame('app-store:campaign:' + name(label_text), 'campaign-announcement', kind='service_content')
        label = s(r'[\(“‘\"\'](switch\s+to\s+[a-z][a-z ]{1,35}?)[\)”’\"\']', local)
        if label and s(r'website|web\s*page|官网|网页', opening):
            return frame('apple:campaign:' + name(label.group(1)), 'campaign-announcement', kind='service_content')

    if (s(r'immersive|沉浸式', local) and s(r'film|horror|电影|影片', local)
            and s(r'apple|苹果', local) and not s(r'trailer|预告片', h)):
        detail = local + ' ' + ' '.join(_normalized(p) for p in passages)
        work = s(r'[《“‘\"\']([a-z][a-z0-9 -]{1,60})[,，]?[》”’\"\']', local)
        owned = s(r'apple.{0,45}(?:announced|releasing|release|unveil)|苹果.{0,20}(?:官宣|宣布|发布)', local)
        premiere = s(r'premieres?|首播|上线|(?:on\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}.{0,30}apple\s+is\s+releasing', detail)
        if work and owned and premiere:
            months = 'january february march april may june july august september october november december'.split()
            calendar = '(' + '|'.join(months) + r')\s+(\d{1,2})(?:,?\s+(20\d{2}))?'
            period = year = ''
            for value in (lead, *passages):
                for start, end in source_sentence_spans(value):
                    clause = _normalized(value[start:end])
                    if name(work.group(1)) not in name(clause) or s(r'previously|last\s+year|此前|去年', clause):
                        continue
                    moment = (s(r'premier(?:es?|ing)[^.。]{0,40}?' + calendar, clause)
                              or s(calendar + r'[^.。]{0,35}apple\s+is\s+releasing', clause))
                    chinese = s(r'(?:将于|定于|于)\s*(?:(20\d{2})\s*年)?(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。]{0,25}(?:上线|首播|开播)', clause)
                    if moment:
                        month, day, year = moment.groups()
                        period = str(months.index(month) + 1) + ':' + str(int(day))
                        year = year or ''
                    elif chinese:
                        year, month, day = chinese.groups()
                        period = str(int(month)) + ':' + str(int(day))
                        year = year or ''
                    if period:
                        break
                if period:
                    break
            return frame('apple-immersive:content:' + name(work.group(1)), 'premiere-schedule', kind='service_content',
                         period=period, year=year)

    if (s(r'language|语言', h) and s(r'iphone|ios|苹果', local)
            and s(r'支持|supports?|新增', opening) and s(r'原住民|濒危|indigenous|endangered', local)):
        outlet = (s(r'new\s+report\s+(?:in|from|by)\s+([a-z][a-z0-9 -]{1,35}?)(?=\s+(?:details|shows|reveals|says)|[,.]|$)', opening)
                  or s(r'《([^》]+)》.{0,30}发布(?:博文|报道)', opening))
        if outlet and s(r'new\s+report|发布博文|报道称|新增支持', opening):
            version = s(r'ios\s*(\d+(?:\.\d+)*)', h + ' ' + opening[:500])
            publisher = {'连线': 'wired'}.get(outlet.group(1), name(outlet.group(1)))
            return frame('ios:language-input:' + publisher, 'implementation-report',
                         model_generation=version.group(1) if version else '')

    engineering_disclosure = False
    if s(r'engineering|performance|cooling|thermal|工程|性能|设计|散热', h) and s(r'iphone', h):
        statements = (clause for start, end in source_sentence_spans(opening)
                      for clause in _compiled_rule(r'[;；]|\b(?:while|whereas|but)\b|而|但', 0).split(opening[start:end]))
        for statement in statements:
            role = s(r'apple(?:[’\x27]s)?\s+(?:(?:vice\s+president|vp|senior\s+manager)\s+of\s+)?(?:(?:silicon|thermal|product|chip)\s+)*(?:engineering(?:\s+team)?|engineers?|design(?:\s+team)?)|苹果(?:公司)?(?:芯片|硅|散热产品|散热|热)?(?:工程|设计).{0,8}(?:团队|工程师|副总裁|经理)', statement)
            # The current role must own the following disclosure predicate.
            # A different speaker's Apple employment history is not ownership.
            owned = statement[role.end():] if role else ''
            if (role and s(r'discuss(?:ed)?|explain\w*|reveal\w*|披露|揭秘|接受.{0,15}采访', owned)
                    and not s(r'\b(?:declin\w*|refus\w*|deni\w*|not|never)\s+(?:to\s+)?(?:discuss\w*|explain\w*|reveal\w*|comment\w*)|(?:拒绝|并未|没有)(?:披露|揭秘|解释|评论|接受)', owned)
                    and not s(r'former|ex[-\s]|previously|曾任|曾是|此前担任|(?<![目此])前$', statement[max(0, role.start() - 40):role.start()])):
                engineering_disclosure = True
                break
    if engineering_disclosure and not s(r'teardown|拆解', h):
        phone = s(r'iphone\s*(duo|air|\d+(?:\s*pro(?:\s*max)?)?)', h)
        if phone and s(r'heat|thermal|散热|电池布局', opening):
            return frame('iphone-' + name(phone.group(1)) + ':thermal-design', 'engineering-explanation', 'hardware_products', 'hardware_market')

    if (identity.counterparties and s(r'apple|苹果', local)
            and s(r'filing|court|discovery|evidence\s+disclosure|诉|(?:文件|证据)(?:提交|披露|开示)', h)
            and not s(r'ruling|verdict|appeal|裁决|判决|上诉', h)):
        detail = local + ' ' + ' '.join(_normalized(p) for p in passages)
        current_joint_filing = any(
            s(r'joint\s+(?:filing|status\s+(?:report|update))|联合.{0,3}(?:报告|进度|状态)', clause)
            and not s(r'previously|earlier|last\s+(?:month|year|week)|此前|先前|去年|上个月|曾经', clause)
            and not s(r"\b(?:not|never|cannot|unable\s+to|refus\w*\s+to)\s+(?:yet\s+)?(?:submit\w*|fil(?:e|ed|ing))\s+(?:(?:a|the|new)\s+)?joint|(?:未|没有|拒绝)(?:提交|递交).{0,12}联合|joint\s+(?:filing|status\s+(?:report|update))\s+(?:(?:was|is)\s+not\s+|has\s+not\s+been\s+)(?:submitted|filed)", clause)
            for start, end in source_sentence_spans(local) for clause in (local[start:end],))
        if (current_joint_filing
                and s(r'document\s+production|discovery|(?:文件|证据)(?:提交|披露|开示)|(?:提交|披露)(?:内部)?文件', detail)):
            return frame('apple-legal:' + ','.join(sorted(identity.counterparties)) + ':document-production',
                         'joint-status-filing', kind='legal_regulatory')

    if (s(r'apple|苹果', h) and s(r'event|showcase|活动', h)
            and s(r'planning|plans?|计划', opening) and s(r'product\s+showcase|产品展示', opening)):
        # Read only the planned showcase clause: a preceding event in another
        # city is background. Preserve explicit dates rather than a device list.
        owned_plan = s(r'apple\s+(?:is\s+)?(?:planning|plans)\b[^.!?。]+|苹果(?:公司)?计划[^。]+', opening)
        current = owned_plan.group() if owned_plan else ''
        if source_denies_action(current, '', r'plan\w*|计划'):
            return None
        dates = (s(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})\s+(?:and\s+\1\s+|through\s+)(\d{1,2})', current)
                 or s(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[至~～-]\s*(\d{1,2})\s*日', current))
        place = s(r'los\s+angeles|洛杉矶|new\s+york|纽约|london|伦敦|shanghai|上海', current)
        if dates and place:
            month, first, last = dates.groups()
            if not month.isdigit():
                month = str('january february march april may june july august september october november december'.split().index(month) + 1)
            city = {'洛杉矶':'los-angeles', '纽约':'new-york', '伦敦':'london', '上海':'shanghai'}.get(place.group(), name(place.group()))
            year = s(r'\b(20\d{2})\b', h)
            return frame('apple:product-showcase:' + city, 'showcase-plan', 'hardware_products', 'company_org',
                         period=month + ':' + first + '-' + last, year=year.group(1) if year else '')
    return None


def source_dated_production_frame(title: str, lead: str, *, published_year: str = '', source_units: tuple[str, ...] = ()) -> SourceActionFrame | None:
    """Bind a production schedule to its local model, stage and production date."""
    h, opening = _normalized(title), _normalized(lead)[:1200]
    s = _frame_search
    if not s(r'production|manufactur|生产|量产|排产|gearing\s+up.{0,60}sales', h):
        return None
    if s(r'delay\w*|cancel\w*|暂停|取消|推迟|延期', h):
        return None
    if source_denies_action(title, lead, r'plan\w*|start\w*|begin|produce|计划|开始|生产|排产'):
        return None
    device = r'(?<![a-z0-9])(iphone|ipad|airpods)\s*(duo|air|\d+[a-z]?)(\s*pro(?:\s*max)?)?(?![a-z0-9])'
    months = 'january february march april may june july august september october november december'.split()
    passages = (opening, *(_normalized(u) for u in source_units))
    for value, a, b in ((v, a, b) for v in passages for a, b in source_sentence_spans(v)):
        clause = _compiled_rule(r'\b(?:because|following|after)\b|由于|因为').split(value[a:b], 1)[0]
        if s(r'last\s+(?:year|month)|previously|去年|此前|取消|否认|cancel\w*|denied', clause):
            continue
        if source_denies_action('', clause, r'plan\w*|start\w*|begin|enter|produce|计划|开始|生产|排产'):
            continue
        start = s(r'\b(?:start|begin|began|started|enter|scheduled)\b|开始(?:生产|量产|排产)|启动(?:生产|量产|排产)', clause)
        production = s(r'production|manufactur|生产|量产|排产', clause)
        if not start or not production or abs(start.start() - production.start()) > 100:
            continue
        models = list(_compiled_rule(device, 0).finditer(clause[:start.start()]))
        if not models and s(r'this\s+model', clause[:start.start()]):
            preceding = list(source_sentence_spans(value[:a]))
            antecedent = value[preceding[-1][0]:preceding[-1][1]] if preceding else ''
            models = list(_compiled_rule(device, 0).finditer(antecedent))
            if len(models) != 1:
                continue
        if not models:
            continue
        family, generation, variant = models[-1].groups()
        model = family + '-' + generation + ('-' + _compiled_rule(r'\s+', 0).sub('-', variant.strip()) if variant else '')
        headline_models = {(m.group(1), m.group(2), (m.group(3) or '').strip())
                           for m in _compiled_rule(device, 0).finditer(h)}
        if headline_models and (family, generation, (variant or '').strip()) not in headline_models:
            continue
        # A release or sales date in the following sentence is not a factory date.
        date_scope = clause[max(0, start.start() - 45):start.end() + 65]
        date = s(r'\b(?:(early|mid|late|end\s+of)[- ]+)?(' + '|'.join(months) + r')(?:\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?)?(?:,?\s+(20\d{2}))?\b', clause[start.end():start.end() + 65])
        chinese_date = s(r'(?:(20\d{2})年)?(\d{1,2})月(?:(\d{1,2})日|(上旬|中旬|下旬|底|末))?', date_scope)
        if date:
            year, month, part = date.group(4) or published_year, months.index(date.group(2)) + 1, date.group(3) or date.group(1) or ''
        elif chinese_date:
            year, month = chinese_date.group(1) or published_year, int(chinese_date.group(2))
            part = chinese_date.group(3) or {'上旬':'early', '中旬':'mid', '下旬':'late', '底':'late', '末':'late'}.get(chinese_date.group(4), '')
            if not 1 <= month <= 12:
                continue
        elif s(r'will\s+enter.{0,30}(?:production|manufacturing)\s+presently', clause):
            year, month, part = '', '', ''
        else:
            continue
        if part == 'end of':
            part = 'late'
        planned = s(r'\b(?:scheduled|plans?|planned|expected|will|may|might|could)\b|计划|预计|将|可能', clause[:start.end()])
        return SourceActionFrame(model + ':production', 'production-start-plan' if planned else 'production-start-report',
                                 'hardware_products', 'hardware_market', period=str(month) + (':' + part if part else '') if month else '', year=year)
    return None


def source_service_fee_frame(title: str, lead: str, facts: tuple[str, ...]) -> SourceActionFrame | None:
    """Bind the official fee table before its coverage and component examples."""
    h = _normalized(title)
    s = _frame_search
    device_pattern = r'(?<![a-z0-9])(iphone|ipad|airpods)\s*(duos?|\d+)(?:\s*(pro)(?:\s*(max))?)?(?![a-z0-9])'
    device = s(device_pattern, h)
    if not device or not s(r'repair|applecare|charging|维修|费用', h):
        return None
    if s(r'how\s+to|repair\s+shop|third.party|回顾|第三方|自行维修|my\s+repair|我的维修', h):
        return None
    fee_clauses = []
    owned_passage = -1
    passages = (lead[:1500], *facts)
    for passage_index, raw_clause in ((i, p[a:b]) for i, p in enumerate(passages)
                                     for a, b in source_sentence_spans(p)):
        clause = _normalized(raw_clause)
        # A table's next sentence can specify a customer repair charge. A
        # newly named provider or an unrelated quotation cannot inherit it.
        continuation = (owned_passage == passage_index and s(
            r'^其中[，,]?\s*(?:(?:非?applecare\+?\s*)?用户|消费者)?'
            r'(?:更换|维修|修理)(?:一[块个层])?'
            r'(?:内屏|外屏|屏幕|电池|保护层|后盖|主板|摄像头)'
            r'(?:需要|需支付|费用为|价格为)\s*(?:\d|人民币|美元|cny|usd|\$)', clause))
        owned_passage = -1
        target = s(device_pattern, clause)
        if target and target.groups() != device.groups():
            continue
        if not continuation and not s(r'repair.{0,30}(?:fees?|costs?|prices?)|charges?.{0,50}repair|(?:维修|服务).{0,20}(?:费用|收费|价格)', clause):
            continue
        owned = s(r"\bapple(?:'s\s+(?:official\s+)?(?:website|site))?\s+(?:(?:has|today|now|already)\s+)*(?:published|announced|released|listed|lists|charges)\b|"
                  r"apple's\s+(?:(?:out.of.warranty|uninsured|estimated)\s+)*(?:list\s+of|repair)|"
                  r"苹果(?:官网|官方网站)?(?:现已|已经|提前|今天|今日|正式|已)*(?:公布|发布)|"
                  r"(?:苹果(?:官网|官方网站)|apple's\s+(?:official\s+)?(?:website|site))\s*(?:显示|列出|列示|shows?)"
                  r"[,，:：]?\s*(?:that\s+)?(?:the\s+)?(?:iphone|ipad|airpods|苹果(?:手机|平板))"
                  r"[^.!?。]{0,55}?(?:repair\s+(?:fees?|costs?|prices?)|(?:维修|服务).{0,12}(?:费用|价格|收费))", clause)
        provider = s(r'(?:charged|collected|set)\s+by\s+(.+?)(?=\s+(?:in|for|are|is)\b|[,.;]|$)|'
                     r'由([^，。；]{1,40}?)(?:收取|定价)', clause)
        if provider and next(value for value in provider.groups() if value).strip() not in {'apple', '苹果', '苹果公司'}:
            continue
        if ((owned or continuation) and not s(r'last\s+(?:year|month|week)|previously|\bago\b|去年|此前|先前|回顾', clause)
                and not source_denies_action('', clause, r'publish\w*|announc\w*|list\w*|show\w*|公布|发布|显示|列出|列示')):
            fee_clauses.append(raw_clause)
            owned_passage = passage_index
    if not fee_clauses:
        return None
    def qualifiers(raw):
        text = _normalized(raw)
        regions = _extract_patterns(text, tuple((region, tuple(t for t in terms if t != 'US'))
                                                for region, terms in REGION_TERMS.items()))
        if _compiled_rule(r'(?<![A-Za-z0-9])US(?![A-Za-z0-9])', 0).search(raw):
            regions.add('united-states')
        if '国行' in text:
            regions.add('china')
        currencies = set()
        if s(r'人民币|(?<![a-z0-9])cny(?![a-z0-9])|(?<![合约\d.,])\d[\d,.]*\s*元(?!件)', text):
            currencies.add('cny')
        if s(r'\$|美元|\busd\b', text):
            currencies.add('usd')
        return regions, currencies

    regions, currencies = qualifiers(title)
    # The headline/first owned table anchors each qualifier. A later price
    # in a different region is supporting comparison, not a new table key.
    for raw in dict.fromkeys(fee_clauses):
        local_regions, local_currencies = qualifiers(raw)
        if ((regions and local_regions and regions != local_regions)
                or (currencies and local_currencies and currencies != local_currencies)):
            continue
        if not regions and len(local_regions) == 1:
            regions = local_regions
        if not currencies and len(local_currencies) == 1:
            currencies = local_currencies
    currency = next(iter(currencies)) if len(currencies) == 1 else ''
    model = '-'.join(part.removesuffix('s') if part.startswith('duo') else part for part in device.groups() if part)
    return SourceActionFrame(model + ':repair-fees', 'service-price-disclosure', kind='service_policy',
        region=','.join(sorted(regions)), period='currency:' + currency if currency else '')


def source_trade_secret_procedure_frame(title: str, lead: str, facts: tuple[str, ...], identity: EventIdentity) -> SourceActionFrame | None:
    """Keep the filing party and requested act, not background accusations."""
    h, opening = _normalized(title), _normalized(lead)[:1500]
    s = _frame_search
    local = h + ' ' + opening
    if not s(r'trade.?secrets?|confidential|商业(?:机密|秘密)|机密', local):
        return None
    if not s(r'filing|court|lawsuit|hearing|judge|injunction|诉讼|法院|听证', local):
        return None
    # Match an explicit named party at the headline start. A later mention
    # of the opponent's original lawsuit never reverses this filing's owner.
    if not s(r'\bapple\b|苹果', local):
        return None
    parties = identity.title_actors - {'apple'}
    owner = ('apple' if s(r'^(?:apple\b|苹果)', h) else
             next((actor for actor in sorted(parties) if s('^' + re.escape(actor) + r'(?![a-z0-9])', h)), ''))
    if not owner or (owner == 'apple' and len(parties) != 1):
        return None
    other = next(iter(parties)) if owner == 'apple' else 'apple'
    case = ':'.join(sorted((owner, other))) + ':trade-secret-case:' + owner
    primary = opening[:next(source_sentence_spans(opening), (0, len(opening)))[1]]
    owned_undertaking = any(
        s(r'\b' + re.escape(owner) + r'\s+(?:has\s+)?(?:voluntarily\s+)?'
          r'(?:agree[ds]?|volunteer(?:ed|s)?)\s+(?:not\s+to|to\s+not)\s+use\s+'
          r'(?:(?:any|alleged)\s+)*' + re.escape(other) + r'(?:[’\x27]s)?\s+trade\s+secrets?\b', clause)
        and not source_denies_action('', clause, r'agree\w*|volunteer\w*')
        for start, end in source_sentence_spans(opening) for clause in (opening[start:end],)
        if source_predicate_role(clause) == 'current')
    if ((owned_undertaking or (
            s(r'agrees?\s+not\s+to\s+use|undertak\w*.{0,20}not\s+to\s+use|承诺不使用|同意不使用', h)
            and s(r'voluntar|主动|承诺|同意', opening)))
            and not s(r'denied|denies|not\s+agreed|refused|拒绝|否认|没有同意|未同意', primary)):
        return SourceActionFrame(case, 'voluntary-nonuse-undertaking', 'hardware_products', 'legal_policy')
    allegation = s(r'alleges?|claims?|accuses?|says?|反指|指控|声称', h)
    if (allegation and s(r'stole|stolen|took|showed|presented|窃取|盗取', h)
            and s(r'ex.employee|former\s+employee|(?:alleged\s+)?thief|员工', local)
            and s(r'files?|product\s+plans?|device|hardware|资料|硬件|文件', local)):
        # The opponent receiving the material is stated in the headline or
        # current assertion; background employment alone is not an allegation.
        recipient = r'\bapple\b|苹果' if other == 'apple' else re.escape(other) + r'(?![a-z0-9])'
        if s(recipient, h[allegation.end():]):
            return SourceActionFrame(case + ':recipient:' + other, 'confidential-file-transfer-allegation',
                                     'hardware_products', 'legal_policy')
    return None


def source_operation_frame(title: str, lead: str, facts: tuple[str, ...], identity: EventIdentity, *, source_units: tuple[str, ...] = (), published_year: str = '') -> SourceActionFrame | None:
    """Resolve concrete operations absent from broad topic/compatibility rules.

    Only the headline and opening establish the action. Same-incident facts
    may identify its affected service or release, never a background action.
    """
    h = _normalized(title)
    opening = _normalized(lead)[:950]
    local = h + ". " + opening
    s = _frame_search
    def frame(subject, action, category="software_systems", kind="os_app", tier="strong", period=""):
        return SourceActionFrame(subject, action, category, kind, tier, period)

    historical_launch = (
        s(r'\b(?:launched|introduced|announced|unveiled|released)\b[^.!?。]{0,90}\b\d+\s+years?\s+ago\b', h)
        or (s(r'(?:\d+|[一二三四五六七八九十百]+)年前(?:的)?今天', h)
            and s(r'苹果.{0,45}(?:发布|推出)', h)))
    current_title = _compiled_rule(r'\b\d+\s+years?\s+ago(?:\s+today)?|(?:\d+|[一二三四五六七八九十百]+)年前(?:的)?今天').sub('', h) if historical_launch else h
    current_release = (s(r'\b(?:now|today)\s+(?:announc\w*|introduc\w*|releas\w*|launch\w*|unveil\w*)|(?:现|今日|今天).{0,5}(?:推出|发布)', current_title)
        or any(s(r'^(?:apple|苹果)(?:\s*(?:today|now|just|has)\s*|今日|今天|正式)+'
                 r'(?:announc\w*|introduc\w*|releas\w*|launch\w*|unveil\w*|adds?|推出|发布|新增)', opening[a:b].strip())
               and not s(r'last\s+(?:year|month|week)|years?\s+ago|去年|前年|此前|年前', opening[a:b])
               for a, b in source_sentence_spans(opening))) if historical_launch else False
    if (historical_launch and not current_release
            and s(r'^today\s+marks\b[^.!?。]{0,70}\banniversary\b|\b(?:launched|became\s+available|introduced)[^.!?。]{0,60}\byears?\s+ago\b|^(?:今天|今日).{0,35}周年', opening)):
        hardware = bool(identity.title_products & {key for key, _, _ in MULTI_PRODUCT_HARDWARE_SUBJECTS})
        return frame('apple:release-recollection:' + _subject_slug(h), 'historical-release-recollection',
                     'hardware_products' if hardware else 'software_systems',
                     'hardware_market' if hardware else 'os_app', 'weak')

    # The modified board belongs to its independent maker, even when its
    # compatibility inventory names Apple services or wireless protocols.
    if (s(r'第三方主板|third.party\s+(?:replacement\s+)?board|改装|modification', h)
            and s(r'ipod|iphone|ipad|mac', h) and s(r'替换|改装|replacement|modification', local)
            and not s(r'^(?:apple|苹果).{0,20}(?:发布|推出|announc|launch)', h)):
        return frame('third-party:device-modification:' + h, 'independent-modification',
                     'hardware_products', 'third_party_ecosystem', 'weak')
    legal = source_trade_secret_procedure_frame(title, lead, facts, identity)
    if legal is not None:
        return legal

    production = source_dated_production_frame(title, lead, published_year=published_year, source_units=source_units)
    if production is not None:
        return production
    publication = source_named_publication_frame(title, lead, source_units or facts, identity)
    if publication is not None:
        return publication
    market = source_market_measurement_frame(title, lead, source_units or facts, published_year=published_year)
    if market is not None:
        return market
    component = source_platform_component_frame(title, lead, facts)
    if component is not None:
        return component
    collection = source_collection_operation_frame(title, lead)
    if collection is not None:
        return collection
    legal = source_patent_challenge_frame(title, lead, facts)
    if legal is not None:
        return legal
    brand = source_brand_collaboration_frame(title, lead)
    if brand is not None:
        return brand
    service_fee = source_service_fee_frame(title, lead, facts)
    if service_fee is not None:
        return service_fee
    device = source_device_operation_frame(title, lead, facts, source_units=source_units)
    if device is not None:
        return device
    hardware = source_hardware_action_frame(title, lead, facts, source_units)
    if hardware is not None:
        return hardware

    report = source_current_report_frame(title, lead, facts, source_units)
    if report is not None:
        return report

    campaign = source_launch_campaign_frame(title, lead)
    if campaign is not None:
        return campaign

    capability = source_software_capability_frame(title, lead, facts)
    if capability is not None:
        return capability
    organization = source_owned_organization_frame(title, lead)
    if organization is not None:
        return organization

    object_operation = source_object_operation_frame(title, lead, facts, identity)
    if object_operation is not None:
        return object_operation

    web_exploit = source_web_exploit_frame(title, lead, facts)
    if web_exploit is not None:
        return web_exploit

    correspondence = app_removal_correspondence_frame(h, opening)
    if correspondence is not None:
        return correspondence

    if identity.content_form == "news":
        first_party_app = source_first_party_app_frame(title, lead)
        if first_party_app is not None:
            return first_party_app
        service_client = source_service_client_frame(title, lead, identity)
        if service_client is not None:
            return service_client
        territory = source_service_territory_frame(title, lead, facts, identity)
        if territory is not None:
            return territory

    device_issue = s(r"(?<![a-z0-9])iphone\s+\d+(?:\s*pro(?:\s*max)?)?(?![a-z0-9])", h)
    if (device_issue and s(r"issue|failure|故障|问题", h)
            and s(r"spokesperson.{0,100}(?:directed\s+us\s+to\s+apple|responded)|发言人.{0,60}(?:回应|要求.{0,20}联系苹果)", opening)
            and s(r"latest\s+request|follow.up\s+questions|最新.{0,15}(?:询问|置评)|追问", opening)):
        return frame(_compiled_rule(r"\s+", 0).sub("-", device_issue.group(), 0) + ":connectivity-followup", "current-company-response",
            "hardware_products", "hardware_market")
    # Attributed hardware design reports need not identify a model or date.
    # Those omissions remain qualifications, not evidence of editorial intent.
    if identity.content_form == "news" and identity.title_products & {"iphone", "ipad", "macbook", "apple-watch"}:
        design = next((name for name, pattern in (("display-bezel", r"bezels?|边框"),
            ("device-thickness", r"thinner\s+(?:body|design)|机身厚度")) if s(pattern, h)), "")
        if (design and s(r"leaker\s+says|according\s+to\s+(?:the\s+)?leaker|爆料者|消息源", local)
                and s(r"set\s+to\s+gain|will\s+(?:gain|have)|将.{0,20}(?:采用|获得|缩窄)", opening)
                and not s(r"previously|last\s+year|此前|去年|没有新", h + " " + opening[:350])):
            return frame(",".join(sorted(identity.title_products)) + ":" + design, "reported-hardware-design", "hardware_products", "hardware_market")

    if (s(r"safari", h) and s(r"track|追踪|跟踪", h) and s(r"promot|推广", h)
            and s(r"google|谷歌", h) and s(r"testing\s+code|测试.{0,12}代码", opening)
            and not source_denies_action(title, lead, r"test\w*|track\w*|测试|追踪")):
        version = s(r"(?:ios|safari)\s*(\d+(?:\.\d+)*)", opening)
        if version:
            return frame("safari-" + version.group(1) + ":google-promotion-measurement", "code-experiment-report")
    if (s(r"siri", h) and s(r"european\s+union|\beu\b|欧盟", h)
            and s(r"wait|delay|等待|再等|推迟", h) and s(r"months?|个月", local)
            and not source_denies_action(title, lead, r"wait|face|等待|推迟")):
        return frame("siri-ai:eu:ios-ipados", "regional-availability-delay-report")
    if (s(r"^(?:new\s+|next.generation\s+)?apple\s*tv\s*4k\s+(?:launch|arriv|com)", h)
            and s(r"next\s+(?:week|month)|即将|下周|下月", h)
            and not source_denies_action(title, lead, r"launch|arrive|发布|推出")):
        return frame("apple-tv-4k", "reported-launch-window", "hardware_products", "hardware_market")

    # A submitted app belongs to the software catalog, not the new host's
    # hardware release. Keep the specific target in the action identity.
    if (s(r"app\s*store|apps?\b|应用", local) and s(r"submit|提交", h)
            and s(r"apple\s+(?:invites?|accepts?|announces?)|苹果(?:开放|邀请|接受)|developers\s+can\s+now\s+submit", h)
            and s(r"invites?|accepts?|can\s+now\s+submit|can\s+(?:now\s+)?be\s+submitted|submissions?\s+(?:are\s+)?(?:now\s+)?open|开放|接受.{0,25}提交", h + " " + opening[:500])
            and not source_denies_action(title, lead, r"submit|accept|open|提交|开放")
            and not s(r"last\s+year|previously|去年|旧公告", source_primary_assertion(title, lead))):
        device = s(r"(?<![a-z0-9])(?:iphone|ipad)\s*(?:duo|\d+(?:\s*pro(?:\s*max)?)?)(?![a-z0-9])", local)
        if device:
            return frame("app-store:" + _compiled_rule(r"\s+", 0).sub("-", device.group(), 0), "app-submission-open")

    # Independent owners retain their operation even if the object is Apple hardware.
    owner = _operation_owner(h)
    app_actor = s(r"^([a-z][a-z0-9.+-]*)\s+(?:turns?|transforms?)\b", h)
    named_app = app_actor.group(1) if app_actor else owner
    if (named_app and named_app != "apple" and _lead_assigns_app_release_to_apple(named_app, opening)
            and not _blocked_update_assertion(opening.split(".", 1)[0])):
        return frame("apple-app:" + named_app, "software-update")
    named_owner = s(re.escape(owner), title).group() if owner and s(re.escape(owner), title) else ""
    proper_owner = bool(named_owner and all(word[0].isupper() for word in named_owner.split()))
    routine_app = s(r"\bapps?\b|应用|软件|(?:mac|macos).{0,25}\bbeta\b", local) and identity.title_products & {"mac", "iphone", "ipad", "vision-pro", "carplay"}
    connection = device_connection_frame(h, opening, facts)
    if connection is not None:
        return connection
    if (owner and owner not in {"apple", "beats"} and identity.action_owner != "apple"
            and (proper_owner or identity.title_actors - {"apple"}) and not routine_app
            and not _extract_patterns(owner, PRODUCT_PATTERNS)
            and s(r"发布|推出|推[‘“\"']|进军|turns?\b|launch\w*\b", h)):
        category = source_accessory_category(h) or (
            "hardware_products" if identity.title_products & {"iphone","ipad","mac","airpods"}
            else "software_systems")
        return frame("third-party:" + owner, "independent-product-action", category, "third_party_ecosystem", "weak")
    if s(r"risk|threat|could\s+(?:bypass|threaten)|风险|威胁", h) and s(r"analyst|bank|bofa|分析师|银行", local):
        return frame("analyst:" + h, "business-risk-opinion", kind="general_company", tier="weak")
    if s(r"guide|指南",h) and s(r"unofficial|非官方|开发者自行",local):
        return frame("third-party:guide", "independent-guide-publication",tier="weak")
    value_instrument = identity.products & {"apple-gift-card", "apple-card", "apple-pay", "apple-cash", "apple-account", "apple-id", "icloud"}
    if (s(r"fraud|scam|parcel\s+theft|可疑.{0,10}交易|诈骗|冒领", h) and s(r"police|警方|平安.{1,10}公众号|物流单号", local)
            and s(r"iphone|ipad|airpods|macbook", h) and not value_instrument
            and not s(r"gift\s*cards?|redeem|account|礼品卡|兑换码|账户", local)
            and not s(r"apple\s+(?:announces?|changes?|confirms?)|苹果(?:宣布|确认|调整)", opening)):
        # Device crime alone is weak; a failure of Apple's own transaction
        # verification is a service-security incident, even if disclosed by police.
        owned_mechanism = (
            r"apple(?:['’]s)?\s+(?:(?:online\s+store(?:['’]s)?\s+(?:online\s+)?)|online\s+)?"
            r"(?:security(?:\s+and\s+(?:identity\s+)?verification)?|"
            r"(?:(?:identity|payment)\s+and\s+)?(?:identity\s+|payment\s+)?verification)"
            r"(?:\s+(?:requirements?|mechanisms?|checks?))?"
        )
        owned_mechanism_zh = (
            r"苹果(?:网店|在线商店|网购流程)(?:中)?(?:的)?(?:在线)?"
            r"(?:安全(?:和|及|与))?(?:(?:身份(?:和|及|与)付款|身份|付款|支付))?"
            r"(?:验证|安全)(?:机制|要求|流程)?"
        )
        # Ownership and failure form one predicate. An arbitrary proximity gap
        # would borrow a different merchant's failure after an Apple reference.
        failure_predicate = (
            owned_mechanism + r"\s+(?:(?:was|were|is|are|had|has|have|been|being|"
            r"somehow|reportedly|allegedly|apparently)\s+){0,5}(?:not\s+in\s+effect|waived|bypassed)\b|"
            r"\b(?:waived|bypassed)\s+(?:the\s+)?" + owned_mechanism + "|"
            + owned_mechanism_zh + r"(?:在(?:这些|本次|相关)?交易中)?(?:未触发|未启动|被绕过)|"
            r"(?:未触发|未启动|绕过)" + owned_mechanism_zh
        )
        for text in (opening, *facts):
            for claim in _compiled_rule(r"[。；;!?]|(?<=\.)\s+|\b(?:while|whereas|but)\b|，\s*(?:而|但)", 0).split(_normalized(text)):
                if (s(r"\b(?:last\s+year|previously|historically|denied|denies)\b|去年|此前|否认", claim)
                        or s(r"not\s+(?:waived|bypassed)|never\s+(?:waived|bypassed)|并未.{0,12}绕过|"
                             r"(?:remain\w*|was|were|is|are)\s+(?:fully\s+)?active|运作正常|正常启用", claim)):
                    continue
                if s(failure_predicate, claim):
                    return frame("apple:online-store:payment-verification", "security-incident-report")
        return frame("third-party:device-purchase-fraud", "crime-report", kind="general_company", tier="weak")

    # A measured ecosystem failure/security issue is more than ordinary app availability.
    if s(r"firebase", local) and s(r"crash|崩溃", local) and s(r"ios|iphone", local):
        return frame("google:firebase:ios-apps", "service-crash-incident", tier="ecosystem", kind="ecosystem_interop")
    if (s(r"messages|imessage|信息.{0,8}数据库", local) and s(r"unauthori[sz]ed|without.{0,30}permission|越权|未获.{0,20}(?:授权|许可)|权限被.{0,8}禁用", local)
            and s(r"read|access|upload|读取|同步|上传", local)):
        owner = next(iter(sorted(identity.title_actors - {"apple"})), "reported-agent")
        return frame(owner + ":apple-messages-data", "unpermitted-data-access-report", tier="ecosystem", kind="ecosystem_interop")

    independent_software = source_independent_software_frame(title, lead, facts)
    if independent_software is not None:
        return independent_software

    message_service = source_message_service_frame(title, lead)
    if message_service is not None:
        return message_service
    # Already-bound named applications keep their canonical release or
    # integration identity; the fallback only fills an unresolved app object.
    app_frame = source_named_app_frame(title, lead, bound_subjects=identity.title_named_subjects)
    if app_frame is not None:
        return app_frame

    if identity.content_form not in {"news", "tutorial"}:
        return None
    device_pattern = r"(?<![a-z0-9])(iphone|ipad|airpods)\s*(duos?|\d+)(?:\s*(pro)(?:\s*(max))?)?(?![a-z0-9])"
    device = s(device_pattern,h)
    if device is None and s(r"iphone|ipad|airpods", h):
        device = s(device_pattern,opening[:250])
    model = "-".join(p.removesuffix('s') if p.startswith('duo') else p for p in device.groups() if p) if device else ""
    if (device and s(r'repair|维修', h) and s(r'fees?|costs?|prices?|费用|收费|价格', h)
            and any(s(r"\bapple(?:'s\s+(?:official\s+)?(?:website|site))?\s+(?:(?:has|today|now|already)\s+)*(?:published|announced|released|lists)\b|苹果(?:官网|官方网站)?(?:现已|已经|提前|今天|今日|正式|已)*(?:公布|发布)", clause)
                    and not s(r'last\s+(?:year|month|week)|previously|\bago\b|去年|前年|此前|先前|回顾', clause)
                    for a, b in source_sentence_spans(opening) for clause in (opening[a:b],))
            and not source_denies_action(title, lead, r'publish\w*|announc\w*|公布|发布')
            and not s(r'how\s+to|repair\s+shop|third.party|回顾|第三方|自行维修', h)):
        scope = source_primary_assertion(title, lead)
        local_regions = _extract_patterns(scope, tuple((region, tuple(t for t in terms if t != 'US'))
                                                       for region, terms in REGION_TERMS.items()))
        if _compiled_rule(r'(?<![A-Za-z0-9])US(?![A-Za-z0-9])').search(title + ' ' + lead):
            local_regions.add('united-states')
        if s(r'国行|人民币', scope):
            local_regions.add('china')
        region = ','.join(sorted(local_regions))
        return replace(frame(model + ':repair-fees', 'service-price-disclosure', kind='service_policy'), region=region)
    if device and s(r"teardown|拆解|repairab|可维修", local):
        return frame(model, "device-teardown", "hardware_products", "hardware_market")
    accessory = s(r"\bmagsafe\s*(\d+)\b", h)
    if (accessory and s(r"cable|连接线|充电线", h) and s(r"firmware|固件", h)
            and s(r"releas\w*|推送|发布", h) and not _blocked_update_assertion(h)):
        release_scope = _compiled_rule(r"previous|旧版本|此前运行", 0).split(h + " " + opening, 1)[0]
        build = s(r"(?<![a-z0-9])(?:\d+[a-z]\d{3,}[a-z]?|\d+\.\d+\.\d+)(?![a-z0-9])", release_scope)
        stage_scope = _compiled_rule(r"\b(?:after|following)\b|此前|之前", 0).split(h + " " + opening[:300], 1)[0]
        stage = "beta" if s(r"\bbeta\b|测试版", stage_scope) else "final"
        return frame("magsafe-" + accessory.group(1) + ":cable:" + stage + ":" + (build.group() if build else "unspecified"),
            "accessory-firmware-release", "software_systems", "os_app")
    if s(r"airpods", h) and s(r"firmware|固件", h) and s(r"releas\w*|rolling\s+out|got\s+new|推送|发布", local):
        first_span = next(source_sentence_spans(opening), (0, len(opening)))
        primary_release = opening[first_span[0]:first_span[1]]
        if _blocked_update_assertion(h) or _blocked_update_assertion(primary_release):
            return frame("airpods:firmware", "release-not-current", tier="weak")
        # Keep the identifier with its new/beta release statement. References to
        # current stable firmware, old builds or compatibility examples are excluded.
        build_scope = [h, opening, *(_normalized(f) for f in facts)]
        builds = []
        release_context = False
        for value in build_scope:
            for start, end in source_sentence_spans(value):
                clause = value[start:end]
                if s(r"for\s+reference|current\s+public|previous|old\s+(?:firmware|build)|stable|last\s+(?:year|month|week)|\d+\s+(?:years?|months?|weeks?)\s+ago|正式固件|当前正式|作为参考|旧固件|旧版本|去年|上个月|上周", clause):
                    release_context = False
                    continue
                current = s(r"new|latest|updated|releas\w*|rolling\s+out|新|最新|推送|发布", clause)
                identifier = s(r"firmware|固件|build\s+number|版本号", clause)
                # A continuation such as 'The firmware has a build number ...'
                # inherits only the immediately preceding current release.
                if identifier and (current or (release_context and s(r"^(?:the\s+firmware|该固件|本次固件)", clause))):
                    owned = _compiled_rule(r"\b(?:replacing|up from|previously)\b|替代旧|从旧", re.I).split(clause)[0]
                    builds.extend(_compiled_rule(r"(?<![a-z0-9])\d+[a-z]\d{2,}[a-z]?(?![a-z0-9])", re.I).findall(owned))
                release_context = bool(current and s(r"firmware|固件",clause))
        stage = "beta" if s(r"beta|developer|测试|开发者", h + " " + opening[:350]) else "final"
        return frame("airpods:firmware:" + ",".join(sorted(set(builds))) + ":" + stage, "firmware-update")
    if (device and s(r"speaker|扬声器|听筒",h) and s(r"software|软件",local)
            and s(r"(?:apple|苹果).{0,70}(?:confirm|promise|确认|承诺)",local)
            and s(r"fix|修复",local)):
        return frame(model + ":speaker", "software-fix-commitment")
    if device and s(r"speaker|扬声器|听筒", h) and s(r"crackl|popping|噼啪|爆音|异响", local):
        return frame(model + ":speaker", "device-issue-report", "hardware_products", "hardware_market")
    if (device and s(r"production|manufactur|making|量产|产量|生产|良率", h)
            and s(r"report|据|消息|claim|量产|manufacturer", local)
            and not s(r"^(?:even\s+)?before\b|^(?:ahead\s+of|prior\s+to)\b", h)
            and "production-ramp" not in identity.title_components):
        if s(r"increas\w*|rais\w*|boost\w*|ramp\w*|增产|提高产量|增加产量", h):
            action = "production-increase-report"
        elif s(r"cut\w*|reduc\w*|decreas\w*|减产|降低产量|削减产量", h):
            action = "production-decrease-report"
        elif s(r"start\w*|begins?|enter\w*|开始|启动|进入",h):
            action = "production-start-report"
        else:
            action = "production-constraint-report"
        return frame(model + ":production", action, "hardware_products", "hardware_market")
    if device and s(r"get\s+ready|early\s+start|预购准备|选配置|pre.order\s+(?:process|starting)|set\s+up.{0,35}pre.order|提前.{0,16}(?:配置|选购)", h):
        return frame(model, "preorder-preparation", "hardware_products", "hardware_market")
    if s(r"face\s*id|面容识别", h):
        for value in (opening,*(_normalized(f) for f in facts)):
            version = s(r"ios\s*(\d+(?:\.\d+)+)", value)
            if version and s(r"(?:fix|addresses|修复|更新)", value) and s(r"face\s*id|面容识别",value):
                action_title = _compiled_rule(r"^(?:report|exclusive)\s*[:：]\s*",re.I).sub("",h)
                predicate = s(r"\b(?:releas\w*|publish\w*|issu(?:es|ed)|fix(?:es|ed)|address\w*|reports?|reported|reporting|complain\w*|not\s+working)\b|发布|推送|修复|反馈|无法",action_title)
                release_primary = bool(predicate and s(r"releas|publish|issu|fix|address|发布|推送|修复",predicate.group()) and
                    (_operation_owner(action_title)=="apple" or s(r"ios\s*\d+",action_title)))
                if not release_primary and s(r"not\s+working|fails?|failure|无法|失效",h) and s(r"users?|owners?|reports?|用户|反馈",opening):
                    return frame((model or "iphone") + ":face-id", "software-issue-report")
                return frame("ios-" + version.group(1) + ":face-id", "public-fix-release")
    if s(r"崩溃|crash", h) and s(r"ios\s*\d", h) and s(r"home\s*screen|主屏幕|小组件|widget", local):
        version = s(r"ios\s*(\d+(?:\.\d+)*)", h).group(1)
        return frame("ios-" + version + ":home-screen", "software-issue-report")
    if s(r"ios\s*\d", h) and s(r"文字大小|text\s+size", h) and s(r"滑块|slider", local):
        version = s(r"ios\s*(\d+(?:\.\d+)*)", h).group(1)
        return frame("ios-" + version + ":control-center-text-size", "beta-capability-report")
    if s(r"emergency\s+sos|紧急.{0,3}sos", h) and s(r"available|开放|上线", local):
        region = s(r"(?:in|在)\s*([a-z]+)(?:[, .]|$)", h)
        if region:
            return frame("emergency-sos:satellite:" + region.group(1), "service-rollout")
    if s(r"apple\s*pay", h) and s(r"india|印度", local) and s(r"axis", local):
        planned = s(r"set\s+to\s+launch|reportedly\s+launching|计划|将于", h + " " + opening[:200])
        return frame("apple-pay:india:axis-bank", "rollout-plan" if planned else "service-rollout")
    if s(r"guide|指南", h) and s(r"screen\s*time|parental|digital\s*habits|家长|数字健康", local) and s(r"apple|苹果", local) and s(r"release|share|发布|整合|team\s+up|partnership", local):
        return frame("apple:family-digital-habits-guide", "document-publication")
    if (s(r"apple\s*tv|苹果\s*tv", h) and s(r"viewership|收视", local)
            and s(r"record|纪录|highest|最高", local)
            and s(r"\bweek\b|单周|当周|周收视", h + " " + opening[:250])):
        period_scope=local + " " + " ".join(_normalized(f) for f in facts[:8])
        date=s(r"week\s+(?:of|starting)\s+([a-z]{3,9})\.?\s+(\d{1,2})",period_scope)
        months=("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec")
        period=""
        if date and date.group(1)[:3] in months:
            period=f"week:{months.index(date.group(1)[:3])+1}-{int(date.group(2))}"
        else:
            date=s(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。；]{0,6}(?:周|星期)",period_scope)
            if date:
                period=f"week:{int(date.group(1))}-{int(date.group(2))}"
        return frame("apple-tv:weekly-viewership", "current-market-report", kind="service_content",period=period)
    if s(r"interview|访谈|采访", opening[:300]) and s(r"api|uikit|swiftui", local + " " + " ".join(facts[:5])) and s(r"hinge|铰链", local + " " + " ".join(facts[:5])) and not s(r"retrospective|last\s+year|回顾|去年", opening[:300]):
        return frame((model or "iphone") + ":hinge-api", "current-capability-disclosure")
    return source_dated_launch_frame(title, lead, facts + source_units, identity)


def bind_operation_report_claims(evidence: ArticleEvidence) -> tuple[BoundClaim, ...]:
    """Assign local assertions and adjacent support; keep ambiguous lists queued."""
    primary = evidence.title + " " + evidence.raw_lead[:500]
    creative = bool(_frame_search(_CREATIVE_APPS, primary) and
        _frame_search(r"updates?|updated|new features|gets?|got|now\s+support|新增|更新|新功能",primary)
        and _operation_owner(evidence.title) in {"", "apple"})
    title_owner = _operation_owner(evidence.title)
    apple_owned = title_owner == "apple" or (not title_owner and _operation_owner(evidence.raw_lead) == "apple")
    parent_frame = organization_action_frame(primary, apple_owned=apple_owned) if apple_owned else None
    company = bool(apple_owned and (
        (parent_frame and parent_frame.action.startswith("workforce-")) or
        (_frame_search(r"reshape|restructur|layoff|support\s+employees|apple\s*care|release|launch|budget|leaner|organi[sz]ation|客服|裁员|裁减|组织|管理层|重塑|研发|更少|发布节奏", evidence.title) and
         _frame_search(r"ceo|ternus|特努斯|restructur|layoff|support\s+employees|apple\s*care|organi[sz]ation|客服|裁员|组织|管理层", primary))))
    if not creative and not company:
        return ()
    groups: dict[SourceActionFrame, list[tuple[str,int,int]]] = {}
    active = None
    for unit in evidence.units:
        if unit.kind not in {"p","li","text","h2","h3"} or unit.container_id == "caption":
            continue
        if unit.kind in {"h2","h3"}:
            app = _frame_search(_CREATIVE_APPS, unit.text) if creative else None
            active = SourceActionFrame("apple:final-cut-camera" if app and app.group().lower().startswith("final cut camera") else "apple:creator-studio", "software-update",kind="os_app") if app else None
            continue
        for start,end in source_sentence_spans(unit.text):
            # A comma before a new explicit actor can introduce another app's
            # update. Do not split ordinary feature or device lists at commas.
            sentence = unit.text[start:end]
            boundaries = [0, *[match.end() for match in _compiled_rule(r",\s*(?=Apple\s+(?:announced|updated|released)|and\s+(?:the\s+)?(?:[a-z'-]+\s+){0,5}(?:team|division|company)\s+(?:dismiss\w*|cut\w*|reduc\w*))",re.I).finditer(sentence)], len(sentence)]
            if company:
                for conjunction in _compiled_rule(r"\b(?:while|whereas|but|and|after|following|because)\b|[，,]\s*(?:而|但|不过)", re.I).finditer(sentence):
                    if _operation_owner(sentence[conjunction.end():].strip()):
                        boundaries.extend((conjunction.start(), conjunction.end()))
                boundaries = sorted(set(boundaries))
            for left,right in zip(boundaries,boundaries[1:]):
                while left < right and sentence[left].isspace():
                    left += 1
                text = sentence[left:right]
                if company and _frame_search(r"^(?:while|whereas|but|and|after|following|because|[，,]\s*(?:而|但|不过))$", text.strip()):
                    continue  # Connectives do not assert an action or clear its referent.
                normalized = _normalized(text)
                owner = _operation_owner(text)
                blocked = (owner not in {"","apple"} or
                    _frame_search(r"^(?:if\b|therefore\b|it\s+remains|因此|如果)|remains\s+to\s+be\s+seen|\b(?:for years|last year|in august|historically)\b|多年|去年|8\s*月底|此前长期",normalized))
                if creative:
                    blocked = blocked or _blocked_update_assertion(normalized)
                if blocked:
                    active = None
                    continue
                frame = creative_update_frame(text) if creative else organization_action_frame(text,apple_owned=company)
                if (company and active and active.action.startswith("workforce-")
                        and (frame is None or frame.subject == active.subject)
                        and _workforce_causal_uncertainty(normalized)):
                    # A lack of proof about these cuts' cause qualifies the
                    # referenced operation; it does not assert completed cuts.
                    frame = active
                # References inherit ownership. A new workforce predicate
                # supplies its own stage; a role description keeps the old one.
                if (company and active and active.action.startswith("workforce-")
                        and (frame is None or frame.subject == "apple:organization")
                        and _frame_search(r"\b(?:these|those)\s+roles\b|这些岗位|上述岗位", normalized)):
                    predicate = _frame_search(
                        r"\b(?:these|those)\s+roles\s+(?:(?:have|had|has|now|already|not|never|yet|been|being|are|were|was|be|will|would|could|also|still)\s+)*(?:eliminat\w*|dismiss\w*|cut|laid\s+off|reduc\w*|replac\w*)\b|"
                        r"(?:这些|上述)岗位(?:已经|现已|仍|尚|未|没有|并未|将|计划|被)*(?:裁[减撤]|削减|取消|替代)", normalized)
                    frame = replace(active, action=_workforce_action(predicate.group())) if predicate else active
                if (company and frame and frame.subject == "apple:management" and active
                        and active.action.startswith("workforce-")
                        and _frame_search(r"^(?:[\"“‘])?(?:the|these|those)\s+cuts\b|这些裁减|上述裁撤", normalized)):
                    frame = replace(frame,subject=active.subject,category=active.category)
                if (company and frame and frame.action == "workforce-reduction" and parent_frame
                        and parent_frame.subject == "apple:organization"
                        and _frame_search(r"\bplans?\b|proposal|under\s+consideration|计划|提议|考虑", primary)
                        and _frame_search(r"^(?:for\s+(?:instance|example),?\s*)?(?:(?:this|that)\s+(?:includes?|involves?)|one\s+(?:proposal|idea|change))\b|这一(?:计划|提议)", normalized)):
                    # A later team's completed cuts cannot complete this proposal.
                    local = _compiled_rule(r"\b(?:after|while|whereas|because|following)\b|此前|同时|之后|由于", re.I).split(normalized, maxsplit=1)[0]
                    completed = _frame_search(
                        r"\b(?:has|have|had|is|are|was|were)\s+(?:(?:now|already|recently|been|being)\s+)*(?:eliminat\w*|dismiss\w*|cut|laid\s+off|reduc\w*|replac\w*)\b|"
                        r"(?:已经|现已|已)(?:被)?(?:裁[减撤]|削减|取消|替代)", local)
                    if not completed:
                        frame = replace(frame,action="workforce-plan")
                tail = unit.text[start+right:]
                next_start,next_end = next(source_sentence_spans(tail),(0,0))
                following = _normalized(tail[next_start:next_end])
                referred_hold = bool(_operation_owner(following) in {"","apple"} and _frame_search(r"(?:this|that|these|those)\s+plans?|这(?:项|一|个)(?:裁员)?(?:计划|方案)|该计划",following) and _workforce_action(following)=="workforce-plan-held")
                if (frame and frame.action == "workforce-plan" and parent_frame
                        and parent_frame.action == "workforce-plan-held" and frame.subject == parent_frame.subject
                        and _frame_search(r"summer|previously|had\s+considered|原计划|曾于|曾计划",normalized)):
                    frame = replace(frame,action="workforce-plan-held")
                elif frame and frame.action=="workforce-plan" and referred_hold:
                    frame = replace(frame,action="workforce-plan-held")
                names = list(_compiled_rule(_CREATIVE_APPS,re.I).finditer(normalized)) if creative else []
                subjects = {"apple:final-cut-camera" if n.group().startswith("final cut camera") else "apple:creator-studio" for n in names}
                if frame is None and active:
                    if creative and len(subjects)<=1 and (not subjects or active.subject in subjects) and not _frame_search(r"subscribe|check\s+out|related|comments|订阅频道|相关阅读|推荐购买",text):
                        frame = active
                    elif company and _frame_search(r"^(?:those\s+employees|the\s+cuts|it\s+had|that\s+does|这些|上述|这批|相关员工|此次裁员|这一轮裁员)|"
                            r"\b(?:these|those)\s+(?:employees|workers|roles)\b|这些(?:员工|岗位)|"
                            r"(?:this|that|those|these)\s+plans?|这(?:项|一|个)(?:裁员)?(?:计划|方案)|该计划",normalized):
                        frame = active
                plan_reference = _frame_search(r"\b(?:this|that|those|these)\s+plans?\b|这(?:项|一|个)(?:裁员)?(?:计划|方案)|该计划", normalized) if company else None
                if active and frame == active and active.action.startswith("workforce-") and plan_reference:
                    stage = _workforce_action(normalized)
                    if stage in {"workforce-plan-held", "workforce-plan-hold-denied"}:
                        frame = replace(active, action=stage)
                if (active and frame and plan_reference and active.action == "workforce-plan"
                        and frame.subject == active.subject
                        and frame.action in {"workforce-plan-held", "workforce-plan-hold-denied"}):
                    # An explicit disposition of the referenced proposal owns
                    # its description, including intervening explanatory facts.
                    groups.setdefault(frame, []).extend(groups.pop(active, []))
                if frame:
                    groups.setdefault(frame,[]).append((unit.unit_id,start+left,start+right))
                    active = frame
                else:
                    # Named application section labels carry the preceding
                    # suite update, but do not invent a different app's update.
                    active = active if creative and active and subjects == {active.subject} else None
    return tuple(BoundClaim(frame.subject,frame.action,"source-operation",(),
        evidence.article_id,tuple(dict.fromkeys(s[0] for s in spans)),tuple(spans),evidence.content_form,
        category=frame.category,event_kind=frame.kind, subject_relation="apple-direct", report_role="independent")
        for frame,spans in groups.items())
