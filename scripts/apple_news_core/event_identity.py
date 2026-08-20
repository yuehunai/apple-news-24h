"""Title-led event identity and relevance guards.

The crawler's detail body is intentionally not authoritative here. Bodies are
useful for facts, but related links and background paragraphs can mention many
unrelated Apple products. Event identity therefore comes from the title first
and only falls back to a short lead when the title is sparse.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
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
    title_named_subjects: frozenset[str]
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
    "imac",
    "mac mini",
    "mac studio",
    "mac pro",
    "macos",
    "watchos",
    "tvos",
    "visionos",
    "airpods",
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
    ("foldable-iphone", ("foldable iphone", "folding iphone", "iphone fold", "iphone ultra", "折叠屏 iphone", "折叠 iphone", "折叠屏iphone", "折叠iphone")),
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
    ("airpods", ("airpods",)),
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
            "苹果智能眼镜",
            "苹果 ai 眼镜",
            "苹果ai眼镜",
            "苹果眼镜",
        ),
    ),
    ("vision-pro", ("vision pro", "visionos")),
    ("airtag", ("airtag", "air tag")),
    ("apple-tv", ("apple tv", "tvos", "苹果 tv", "苹果电视")),
    (
        "apple-home-hub",
        (
            "apple home hub",
            "apple's home hub",
            "apple’s home hub",
            "apple smart home hub",
            "苹果家庭中枢",
            "苹果智能家居中枢",
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
            "apple-owned beats",
            "apple's beats",
            "apple’s beats",
            "beats lab",
            "beats headphones",
            "beats earbuds",
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
    ("apple-maps", ("apple maps", "苹果地图")),
    ("apple-pay", ("apple pay", "苹果支付")),
    ("apple-fitness", ("apple fitness+", "fitness+", "苹果 fitness+", "苹果fitness+")),
    ("apple-card", ("apple card", "苹果卡")),
    ("xcode", ("xcode",)),
    ("carplay", ("carplay",)),
    ("homepod", ("homepod",)),
    ("apple-intelligence", ("apple intelligence", "apple 智能", "apple智能", "苹果智能", "苹果 ai", "苹果ai")),
)


COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
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
            "develops",
            "developing",
            "working on",
            "introduces",
            "introducing",
            "improves",
            "improved",
            "removes",
            "removed",
            "upgrade",
            "update",
            "new feature",
            "makes",
            "新增",
            "加入",
            "引入",
            "开发",
            "研发",
            "改进",
            "升级",
            "移除",
            "更新",
            "调整",
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
)


OS_COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
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
    match = re.search(r"([a-z]+)$", alias)
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
            if re.search(r"[\u3400-\u9fff]", alias):
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


def primary_assertion_components(value: str) -> frozenset[str]:
    """Expose typed components from the first assertion without mutating identity."""
    primary = re.split(
        r"(?:[。！？]|(?<=[.!?])\s+)",
        _normalized(value),
        maxsplit=1,
    )[0]
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
            "storage chip",
            "storage chips",
            "内存",
            "存储芯片",
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
        r"test|testing|tested|qualify|qualifying|qualification|approve|approval|"
        r"negotiate|negotiating|negotiation|talks?\s+with|consider(?:s|ed|ing)?\s+(?:buying|sourcing|using)|"
        r"采购|购买|寻求|寻找|测试|认证|送样|洽谈|谈判|议价|考虑采用|考虑使用|导入供应链)"
    )
    direct_buyer_relation = bool(
        re.search(rf"{apple_subject}[^。！？\n]{{0,110}}{sourcing_action}", text)
        or re.search(
            rf"{sourcing_action}[^。！？\n]{{0,110}}(?:for|to|by|供给|供应|面向)?\s*{apple_subject}",
            text,
        )
    )
    if not direct_buyer_relation:
        return set()
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


def _explicit_evidence_first_party_subjects(evidence: Iterable[str]) -> set[str]:
    subjects: set[str] = set()
    for evidence_item in tuple(evidence)[:6]:
        for match in re.finditer(
            r"(?i)(?:something\s+called|called|named|known\s+as|名为|称为)\s*"
            r"[\"'“‘]?\s*(Apple\s+[A-Z][A-Za-z0-9+-]{2,30}"
            r"(?:\s+[A-Z][A-Za-z0-9+-]{2,30}){0,2})\b",
            evidence_item,
        ):
            subject = _canonical_named_subject(match.group(1))
            if subject:
                subjects.add(subject)
    return subjects


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
    background_quoted_subjects: set[str] = set()

    for match in re.finditer(r"[\"'“‘]([^\"'“”‘’\n]{2,48})[\"'”’]", scoped):
        trailing_context = scoped[match.end() : match.end() + 36].lstrip(" \t\"'“”‘’")
        if re.match(
            r"(?:(?:oscar|emmy|bafta|grammy|golden globe)\s+(?:winner|nominee)|"
            r"director|winner|star|actor|actress|creator|author|filmmaker)\b",
            trailing_context,
            re.I,
        ):
            background = _valid_quoted_subject(match.group(1)) or _valid_content_title(match.group(1))
            if background:
                background_quoted_subjects.add(background)
            continue
        subject = _valid_quoted_subject(match.group(1)) or _valid_content_title(match.group(1))
        if subject:
            subjects.add(subject)

    named_pattern = re.compile(
        r"(?:called|named|codenamed|known as|story of|名为|代号(?:分别)?为?)\s*[\"'“‘]?"
        r"([A-Z][A-Za-z0-9+.-]*(?:\s+[A-Z][A-Za-z0-9+.-]*){0,3})"
    )
    for match in named_pattern.finditer(scoped):
        subject = _canonical_named_subject(match.group(1))
        if subject:
            subjects.add(subject)

    # Feature reports often establish a branded UI object through a
    # causative comparison rather than explicit naming language, for example
    # "make <Name> more ...". Preserve that syntactic subject so translations
    # and the original report share a concrete event identity.
    for match in re.finditer(
        r"\b(?:make|makes|making|set|sets|adjust|adjusts|change|changes)\s+"
        r"([A-Z][A-Za-z0-9+.-]*(?:\s+[A-Z][A-Za-z0-9+.-]*){1,3})\s+"
        r"(?:more|less|higher|lower|clearer|darker|lighter)\b",
        scoped,
    ):
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

    # Key facts may contain the explicit first-party name that a concise
    # headline omits. Accept only names introduced by naming language; this
    # keeps background product mentions from becoming event identity.
    subjects |= _explicit_evidence_first_party_subjects(evidence)

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
    for match in re.finditer(
        r"\bApple\s+([A-Z][A-Za-z0-9+-]{2,30}"
        r"(?:\s+(?!Apple\b)[A-Z][A-Za-z0-9+-]{2,30}){0,2})\b",
        scoped,
    ):
        branded_parts = match.group(1).split()
        stop_index = next(
            (
                index
                for index, part in enumerate(branded_parts)
                if part.lower() in apple_named_stopwords
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
    ):
        for match in re.finditer(pattern, scoped):
            subject = _valid_content_title(match.group(1))
            if subject:
                subjects.add(subject)

    # Unquoted entertainment headlines commonly put the work name directly
    # before a season/trailer action. Preserve that rare title anchor so a
    # premiere or executive interview mentioning the same show cannot bridge
    # into the trailer event merely through Apple TV background.
    for match in re.finditer(
        r"(?i)(?:apple\s+(?:unveils?|shares?|releases?)\s+|back\s+to\s+[^,]{2,40},\s*)?"
        r"(?P<name>[a-z][a-z0-9'’.-]*(?:\s+[a-z][a-z0-9'’.-]*){1,6})"
        r"\s+season\s+\d{1,2}(?:\s+(?:trailer|teaser))?",
        title,
    ):
        candidate = re.sub(
            r"(?i)^(?:apple\s+(?:unveils?|shares?|releases?)\s+)",
            "",
            match.group("name"),
        )
        subject = _valid_content_title(candidate.title())
        if subject:
            subjects.add(subject)
    return subjects - background_quoted_subjects


def _title_primary_named_subjects(title: str, lead: str) -> set[str]:
    """Return named subjects established by the headline, with narrow lead disambiguation."""
    subjects = _named_subjects(title, "")
    normalized_title = _normalized(title)
    for subject in _named_subjects(title, lead):
        chip_family = re.fullmatch(r"([am]\d{1,2})(?:-(?:pro|max|ultra|extreme))?", subject)
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
        for token in re.findall(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9.-]{2,})(?![A-Za-z0-9])", title)
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
    return bool(
        re.search(
            r"\b(?:price\s+target|target\s+price|aapl\s+target)\b|"
            r"\b(?:apple|aapl)(?:['’]s)?\b.{0,28}\b(?:price\s+)?target\b|"
            r"\b(?:analyst|bank|brokerage|investment\s+firm)\b.{0,32}\b(?:rating|upgrades?|downgrades?)\b|"
            r"\b(?:upgrades?|downgrades?)\b.{0,24}\b(?:apple|aapl)\b|"
            r"\b(?:raises?|cuts?|lowers?|lifts?|boosts?|hikes?|trims?)\b.{0,24}"
            r"\b(?:apple|aapl)\b.{0,18}(?:\bto\b|\bat\b)?\s*\$\s*\d|"
            r"(?:目标(?:股)?价|股票评级|股价评级|上调评级|下调评级)",
            lower,
        )
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
    value = re.sub(
        r"^(?:a\s+|the\s+|market\s+research\s+firm\s+|research\s+firm\s+|"
        r"市场研究机构|研究机构|分析机构|分析师|研究员)",
        "",
        value,
    )
    value = re.sub(
        r"(?:最新|手机|产业|市场|行业|研究)*(?:报告|研究|数据|预测|咨询)$",
        "",
        value,
    )
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff+.-]+", "-", value).strip("-")
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
    if re.fullmatch(
        r"(?:apple|iphone|ipad|mac|macbook|airpods|vision-pro|"
        r"[am]\d+(?:-(?:pro|max|ultra|extreme))?|j\d+(?:-mac-pro)?)",
        value,
    ):
        return ""
    return value


def _report_attribution_components(title: str, lead: str = "") -> set[str]:
    """Extract a report's named source independently of language and publisher."""
    scope = f"{title}. {lead[:900]}"
    values: set[str] = set()
    patterns = (
        r"\b(?:[Aa]nalyst|[Rr]esearcher)\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,2})\b",
        r"\b[Aa]ccording\s+to\s+([A-Z][A-Za-z0-9&+.'-]+(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,3})\b",
        r"\b(?:[Nn]ote|[Rr]eport)\s+(?:from|by)\s+([A-Z][A-Za-z0-9&+.'-]+(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,3})\b",
        r"\b([A-Z][A-Za-z0-9&+.'-]{2,30}(?:\s+[A-Z][A-Za-z0-9&+.'-]+){0,2})\s+"
        r"(?:reports?|says|estimates?|forecasts?|projects?|data\s+shows)\b",
        r"(?:根据|据)\s*([A-Za-z][A-Za-z0-9&+.'-]{2,30})(?:\s|的|，|,)",
        r"(?:根据|据)?(?:外媒|媒体|科技媒体)\s*"
        r"([A-Za-z][A-Za-z0-9&+.'-]{2,30})\s*(?:报道|披露|联系)",
        r"\b([A-Z][A-Z0-9&+.'-]{2,30})\s+"
        r"(?:reports?|reported|contacted|reached\s+out)\b",
        r"(?:分析师|研究员)[^。；,，\n]{0,24}?[（(]\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,2})\s*[）)]",
        r"(?:分析师|研究员)[^。；,，\n]{0,24}?([A-Z][A-Za-z'.-]+(?:\s*[A-Z][A-Za-z'.-]+)?)",
        r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9&+.'-]{1,23})"
        r"(?:报告称|数据显示|研究显示|预测)",
    )
    rejected = {
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
        for match in re.finditer(pattern, scope):
            raw_value = re.sub(r"([a-z])([A-Z])", r"\1-\2", match.group(1))
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


def _legal_case_topics(title: str, lead: str, facets: Iterable[str]) -> set[str]:
    text = f"{_normalized(title)} {_normalized(lead)[:520]}"
    topics: set[str] = set()
    aliases = (
        ("antitrust", ("antitrust", "anti-monopoly", "反垄断", "垄断诉讼")),
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
    if re.match(r"^psa:\s+", lower) and not re.search(
        r"\b(?:launches?|releases?|announces?|rolls? out|changes?|adds?|removes?)\b|"
        r"(?:发布|推出|宣布|上线|变更|新增|移除)",
        lower,
    ):
        return "tutorial"
    if re.match(
        r"^(?:add|enable|disable|turn on|turn off|show|hide|change|set up)\b"
        r".{0,90}\b(?:on|to|for)\s+(?:your\s+)?(?:iphone|ipad|mac|apple watch)\b",
        lower,
    ) or re.search(r"\b(?:here['’]s the fix|troubleshooting guide|fix seems to work)\b|故障排查|解决办法", lower):
        return "tutorial"
    if (
        "poll" in lower
        or re.match(r"^(?:what|which|would|will|should)\b.*\?", lower)
        or re.search(
            r"(?:^|:\s*)(?:what|which)\b[^?？]{0,90}"
            r"\b(?:will|would|do)\s+you\s+(?:buy|choose|pick|prefer)\b[^?？]*[?？]",
            lower,
        )
        or re.search(r"\bshould\s+apple\b[^?？]*[?？]", lower)
        or re.search(r"(?:vote|投票|你会怎么|你会如何|你是否).*[?？]?$", lower)
    ):
        return "poll"
    if re.match(
        r"^(?:[^:]{1,90}:\s*)?(?:when\s+is|when\s+will).{0,90}"
        r"\b(?:next\s+)?apple\s+(?:event|keynote)\b",
        lower,
    ):
        return "analysis"
    if re.match(
        r"^(?:it['’]s|it\s+is|now\s+is)\s+time\s+for\s+"
        r"(?:apple|iphone|ipad|ios|ipados|macos|watchos|tvos|visionos|safari|siri)\b"
        r".{0,80}\bto\s+(?:have|get|add|adopt|offer|support|bring)\b",
        lower,
    ):
        return "analysis"
    if re.match(r"^apple\s*,?\s+please\b", lower) or re.search(
        r"(?:还|是否)?值得(?:购买|买|升级)吗[?？]?$",
        lower,
    ):
        return "analysis"
    if re.search(
        r"\b(?:could|may|might|will)\s+(?:push|tempt|convince|persuade|make)\s+"
        r"(?:you|users?|owners?)\s+to\s+(?:buy|upgrade)\b|"
        r"(?:可能|或将|会).{0,18}(?:促使|吸引|说服|让).{0,12}(?:用户|你).{0,12}(?:购买|升级|换机)",
        lower,
    ):
        return "buying_advice"
    if re.search(
        r"\bhere['’]s\s+(?:the\s+)?one\s+i(?:'ve| have)\s+been\s+(?:loving|using)\b|"
        r"\b(?:one|feature)\s+i(?:'ve| have)\s+been\s+(?:loving|using)\b|"
        r"(?:我一直|我最近).{0,12}(?:喜欢|在用|使用).{0,18}(?:功能|表盘|应用)",
        lower,
    ):
        return "analysis"
    if (
        re.search(
            r"\b(?:best|biggest|main)\s+reason\s+(?:yet\s+)?to\b|"
            r"\b(?:one of )?my favorite\b|"
            r"(?:最值得|最大|最主要).{0,12}(?:理由|原因)",
            lower,
        )
        and re.search(
            r"\bi\s+(?:use|wear|rely|imagine|think|believe|often|already)\b|"
            r"\bi['’]ve\b|\bmy favorite\b|"
            r"(?:我(?:一直|经常|已经|认为|觉得|想象|依赖|使用|佩戴)|我最喜欢)",
            lead_lower,
        )
    ):
        return "analysis"
    if (
        (
            re.search(
                r"\bhow\b.{0,90}\b(?:helped|shaped|enabled|led to|made possible)\b|"
                r"如何.{0,60}(?:助推|塑造|催生|促成|成就)",
                lower,
            )
            or re.search(r"\b(?:origin story|historical retrospective)\b|历史回顾", lower)
        )
        and re.search(
            r"\b(?:19\d{2}|20\d{2})\b|\b(?:19)?(?:70|80|90)s\b|"
            r"(?:上世纪|历史上|当年|\d{2}年代|二十多年前|三十多年前|四十多年前)",
            f"{lower} {lead_lower}",
        )
        and not re.search(
            r"\b(?:today|now|new report|announces?|launches?|releases?|sues?|investigates?)\b|"
            r"(?:今日|最新|宣布|推出|发布|起诉|调查)",
            lower,
        )
    ):
        return "analysis"
    custom_vendor = re.search(
        r"(?<![a-z0-9])(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b)"
        r"([a-z][a-z0-9.+-]{2,30})(?![a-z0-9]).{0,36}"
        r"(?:lists?|listed|launch(?:es|ed)?|unveils?|上架|推出|发布)",
        lead_lower,
    )
    if (
        custom_vendor
        and re.search(
            r"\b(?:custom|customized|bespoke|luxury|modified)\b|"
            r"(?:定制版|定制款|高奢定制|奢华定制|改装版)",
            lower,
        )
        and not re.search(
            r"\bapple\s+(?:announces?|launches?|releases?|unveils?)\b|"
            r"苹果(?:宣布|推出|发布)",
            lead_lower,
        )
    ):
        return "third_party_spotlight"
    current_attributed_report = bool(
        re.search(
            r"\b(?:today (?:outlined|reported)|today['’]s report|latest edition|new report|"
            r"bloomberg reports|gurman reports|according to (?:bloomberg|mark gurman|gurman))\b|"
            r"(?:彭博社今日|古尔曼今日|据彭博社|古尔曼称|最新一期|最新报道|今日报告|今日透露)",
            lead_lower,
        )
        and re.search(
            r"\b(?:late-stage testing|will announce|will launch|will not be released|is not planned|"
            r"does not expect|do not expect|not expected|no major design changes|"
            r"unlikely to arrive|will not|codenamed|codenames|production|supplier|shipment)\b|"
            r"(?:后期测试|将发布|不会发布|预计不会|没有重大设计变化|没有重大改款|"
            r"没有计划|代号|量产|供应商|出货)",
            lead_lower,
        )
        and not re.search(
            r"\b(?:no new reporting|previously reported|recapped rumors|rumors so far)\b|"
            r"(?:汇总此前|此前传闻|无新增消息|没有新增消息)",
            lead_lower,
        )
    )
    if (not current_attributed_report) and re.search(
        r"\b(?:product|hardware|device)?\s*roadmap\b.{0,70}\bhere['’]s\s+what['’]s\s+coming\b|"
        r"\bhere['’]s\s+what['’]s\s+coming\b.{0,70}\b(?:product|hardware|device)?\s*roadmap\b|"
        r"(?:产品|硬件|设备)?路线图.{0,36}(?:即将推出|即将发布|有哪些|一览)",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"(?:发布会|活动).{0,28}(?:将|预计|有望|可能|大概率).{0,18}"
        r"(?:推|推出|发布|带来|亮相).{0,10}"
        r"(?:[一二三四五六七八九十百\d]+)\s*(?:款|项|个)?(?:新品|产品|设备|硬件)",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.match(
        r"^what['’]?s\s+coming\s+in\s+[a-z]+\b.{0,100}"
        r"\b(?:iphones?|ipads?|macs?|apple\s+watches?|airpods|products?)\b",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"\b(?:models?|products?|devices?)\s+(?:launch|arrive|debut)\s+"
        r"(?:next|this)\s+(?:week|month|season|fall|spring)\b.{0,40}"
        r"\bhere['’]s\s+what['’]s\s+coming\b|"
        r"(?:多款|系列).{0,16}(?:新品|产品|设备).{0,18}(?:即将|下月|下周).{0,18}(?:汇总|一览|有哪些)",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"\b(?:outlook|preview|roundup)\b.{0,24}\beverything\s+(?:expected|rumored|known)\b|"
        r"(?:前瞻|展望|汇总).{0,20}(?:全部|所有|已知|预期|传闻)",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"\b(?:besides|beyond|alongside)\b.{0,36}\b(?:iphone|ipad|macbook|apple watch)\b"
        r".{0,36}\b(?:other|rival|competing)\b.{0,24}\b(?:phones?|products?|flagships?)\b|"
        r"(?:iphone|ipad|macbook|apple watch).{0,24}之外.{0,12}(?:还有|另有|也有).{0,18}"
        r"(?:这些|多款|其他).{0,12}(?:手机|产品|旗舰|新品)",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"(?:等|共|多达)\s*[一二三四五六七八九十百\d]+\s*款"
        r"(?:苹果)?(?:新品|产品|设备).{0,28}"
        r"(?:彻底泄密|全部曝光|集中曝光|一次看完|汇总|再无悬念)",
        lower,
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"\b(?:rumors? point to|everything we know|"
        r"what to expect|these \d+ (?:new )?(?:features|changes)|"
        r"\d+ new things .+ (?:can do|to try|to know)|"
        r"(?:will|could|may|expected to)\s+(?:release|launch|unveil)\s+\d+\+?\s+"
        r"(?:new\s+)?(?:products?|devices?)|"
        r"\d+ rumored features|latest (?:apple )?rumors?|all (?:the )?(?:apple )?rumors?|"
        r"rumors? so far|best .+ to try)\b|传闻汇总|消息汇总|功能汇总|值得期待的\s*\d+",
        lower,
    ) or (
        not current_attributed_report
        and re.match(
            r"^(?:everything new|here['’]s what['’]s new|what['’]s new with)\b",
            lower,
        )
        and not re.match(
            r"^what['’]s new with (?:the )?[a-z][a-z -]{1,40} app in "
            r"(?:ios|ipados|macos|watchos|tvos|visionos)\s+\d+(?:\.\d+){0,2}\b",
            lower,
        )
    ) or (not current_attributed_report and "更新汇总" in lower) or (
        not current_attributed_report
        and
        re.search(r"\bcoming\b.{0,42}\bwith (?:these|\d+) (?:rumored )?new features\b", lower)
        and re.search(r"\b(?:recaps?|previously reported|rumored so far|no new reporting)\b|汇总此前|此前传闻|无新增", lead_lower)
    ):
        return "roundup"
    if (not current_attributed_report) and re.search(
        r"^(?:iphone|ipad|mac(?:book)?|apple watch|airpods|vision pro)\b"
        r".{0,48}\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\b"
        r"\s+(?:new\s+)?(?:features?|changes?|upgrades?)\b.{0,48}"
        r"\b(?:coming|expected|rumored|to expect)\b",
        lower,
    ):
        return "roundup"
    if re.search(
        r"\b(?:adds?|gets?|gains?|brings?)\s+(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?:new\s+)?(?:iphone\s+|ipad\s+|mac\s+)?(?:features?|changes?|upgrades?)\b|"
        r"(?:新增|带来|加入)\s*(?:两|三|四|五|六|七|八|九|十|\d+)\s*(?:项|个)?(?:新)?(?:功能|变化|升级)",
        lower,
    ):
        return "roundup"
    if re.search(
        r"(?:\d+|[一二三四五六七八九十]+)\s*项(?:功能|变化|升级|更新)"
        r".{0,20}(?:汇总|盘点|全(?:部)?(?:扒出|梳理|整理)|一览)",
        lower,
    ):
        return "roundup"
    if (
        re.match(r"^(?:is|are) .+ worth it\b", lower)
        or re.search(
            r"\b(?:doesn['’]t|does not|didn['’]t|did not)\s+seem\s+credible\b|"
            r"\b(?:hard|difficult)\s+to\s+believe\b|\bseems?\s+unlikely\b|"
            r"(?:显得|看起来|似乎).{0,10}(?:平淡|乏味|难以置信|不可信)|"
            r"(?:补齐|修复).{0,12}(?:短板|缺陷).{0,18}(?:但|不过|然而)",
            lower,
        )
        or re.match(r"^why\b.{0,100}\b(?:could|may|might)\b.{0,60}\b(?:risk|problem|concern)\b", lower)
        or re.search(r"(?:便利与隐患并存|(?:引发|存在|带来).{0,10}(?:隐私|安全).{0,8}(?:争议|风险|隐患))", lower)
        or re.search(r"值不值得|是否值得", lower)
    ):
        return "analysis"
    if re.match(
        r"^[^:：]{2,24}(?:吐槽|抱怨|炮轰|批评)[：:]",
        lower,
    ):
        return "analysis"
    if re.search(
        r"\bgets?\s+(?:one|something)\s+(?:thing\s+)?(?:very\s+)?right\b.{0,80}\bgets?\s+wrong\b",
        lower,
    ):
        return "analysis"
    if re.search(r"\bno[- ]brainer\s+upgrade\b", lower):
        return "buying_advice"
    if re.search(
        r"\brelease\s+date\s*,\s*features?\s*,\s*price\s*,\s*(?:and\s+)?rumors?\b",
        lower,
    ):
        return "buying_advice"
    if re.match(r"^(?:do|does|did|can|could)\s+we\s+need\s+to\s+worry\b", lower):
        return "analysis"
    policy_incentive = bool(
        re.search(
            r"\b(?:tax|tariff)\s+(?:break|breaks|incentive|incentives|relief|exemption|exemptions)\b|"
            r"(?:税收|关税|所得税).{0,10}(?:优惠|减免|豁免|激励)",
            lower,
        )
    )
    if not policy_incentive and re.search(
        r"\b(?:weekend deals?|daily deals?|best deals?|deal roundup|prime day|shopping guide)\b|"
        r"\b(?:up to\s+)?[$£€¥]\s*\d+(?:[.,]\d+)?\s+off\b|"
        r"(?:周末|每日|今日)?(?:优惠|好价|促销)(?:汇总|合集)?",
        lower,
    ):
        return "deal"
    if (
        re.search(r"\b(?:discounts?|markdowns?|savings?|sale|lowest price|record low)\b", lower)
        and re.search(
            r"[$£€¥]\s*\d|\b\d+(?:\.\d+)?\s*%|\bup to\b|\boff\b|"
            r"\bbelow\s+(?:the\s+)?(?:list|retail)\s+price\b",
            f"{lower} {lead_lower}",
        )
    ):
        return "deal"
    if re.search(
        r"\b(?:should(?:n['’]t| not)? (?:buy|wait|upgrade)|should you (?:buy|wait|upgrade)|"
        r"buy now or wait|upgrade now or wait|why you should(?:n['’]t| not)? wait|"
        r"reasons? to buy .+ instead of waiting|before you buy|buying advice|buying guide)\b|"
        r"(?:该不该|要不要|是否应该)(?:买|等|升级)|买还是等|购买建议|换机建议|"
        r"(?:升级|换到|换购).{0,18}(?:的|之)?(?:三|四|五|六|七|八|九|十|\d+)大理由",
        lower,
    ):
        return "buying_advice"
    if re.search(r"\b(?:indie app spotlight|app spotlight|app pick)\b|(?:应用|app)推荐", lower):
        return "third_party_spotlight"
    if re.search(
        r"\bmy\s+favorite\b.{0,45}\b(?:accessories|bands|chargers|cases|stands)\b|"
        r"\bfavorite\b.{0,36}\b(?:apple\s+watch|iphone|ipad|mac|airpods|vision\s+pro)\b"
        r".{0,36}\b(?:accessories|bands|chargers|cases|stands)\b|"
        r"(?:我最喜欢|最喜欢的|精选).{0,24}(?:苹果|iphone|ipad|mac|airpods|vision\s*pro).{0,20}(?:配件|表带|充电器|保护壳|支架)",
        lower,
    ):
        return "buying_advice"
    if re.search(
        r"\b(?:event|keynote)\s+date\b.{0,45}\b(?:years?|history|pattern|announcements?)\b|"
        r"\b(?:years?|history)\s+of\s+apple\s+announcements?\b|"
        r"(?:发布会|活动)(?:日期|时间).{0,28}(?:历年|历史|规律|回顾|推算)",
        lower,
    ):
        return "analysis"
    if re.search(
        r"\b(?:one|two|three|\d+)\s+years?\s+later\b.{0,90}"
        r"\b(?:what\s+held\s+up|what\s+didn['’]?t|long[- ]term|review)\b",
        lower,
    ):
        return "analysis"
    repeated_incident_retrospective = bool(
        re.search(
            r"\b(?:repeated|recurring|again and again)\b.{0,48}\b(?:failure|failures|issue|issues|flaw|flaws)\b|"
            r"(?:屡现|屡次|反复|一再).{0,32}(?:漏洞|失误|失守|问题|案例)",
            lower,
        )
        and re.search(
            r"\b(?:promise|promises|credibility|trust)\b.{0,30}\b(?:questioned|challenged|under scrutiny)\b|"
            r"(?:承诺|可信度|信任|机制).{0,24}(?:遭|受|被)?(?:到)?质疑",
            lower,
        )
    )
    if repeated_incident_retrospective:
        return "analysis"
    if re.search(
        r"^(?:analyst|analysis|opinion|commentary)\b|"
        r"^(?:分析师|机构观点|评论)[：:]|(?:分析师|评论人士).{0,24}(?:认为|称|表示)|"
        r"\b(?:now\s+)?(?:even\s+)?more valuable\b|\bbetter value\b|"
        r"\b(?:won['’]t|will not|wouldn['’]t|would not)\s+be\s+useful\s+without\b|"
        r"\b(?:great|good)\s+for\s+apple\b.{0,55}\b(?:not\s+good|bad)\s+for\b|"
        r"\bmight\s+not\s+be\s+good\s+for\s+(?:the\s+)?(?:buyer|customer|user)\b|"
        r"(?:更有价值|更划算)",
        lower,
    ):
        return "analysis"
    if re.search(r"\b(?:hands-on|hands on|first impressions?)\b|(?:公测版|测试版)?.{0,10}(?:上手|体验)", lower):
        return "hands_on"
    return "news"


def _title_scope(title: str, lead: str) -> str:
    title_lower = _normalized(title)
    lead_lower = _normalized(lead)[:600]
    if lead_lower.startswith(title_lower):
        lead_lower = lead_lower[len(title_lower) :].lstrip(" .:-：")
    apple_in_title = _contains_any(title_lower, APPLE_TITLE_TERMS)
    title_products = _collapse_product_hierarchy(
        _extract_patterns(title_lower, PRODUCT_PATTERNS)
    )
    beats_first_party_technical = bool(
        re.match(r"^beats\b", title_lower)
        and re.search(
            r"\b(?:lab|laboratory|engineering|r&d)\b|(?:实验室|工程实验室|研发)",
            title_lower,
        )
    )
    first_party_prefix = bool(
        re.match(
            r"^(?:(?:these|those|some|older|new)\s+)?(?:apple(?:'s)?|iphones?|ipads?|ios|ipados|macs?(?:book|os)?|watchos|tvos|visionos|airpods|icloud|safari|siri|shazam|beats\s+(?:lab|headphones|earbuds|pill|studio)|carplay|xcode|app store)\b|"
            r"^(?:苹果|传苹果|消息称苹果|报道称苹果)",
            title_lower,
        )
    ) or beats_first_party_technical
    direct_target = bool(
        re.search(
            r"(?:sues?|sued|fines?|threatens?|investigates?|orders?|blocks?|approves?|起诉|罚款|调查|要求|批准).{0,45}(?:apple|苹果)|"
            r"(?:apple|苹果).{0,30}(?:works? on|fix(?:es|ed|ing)?|patch(?:es|ed|ing)?|responds?|investigates?|修复|制作补丁|回应|调查)",
            title_lower,
        )
    )
    direct_relationship = bool(
        re.search(
            r"\b(?:in talks?|talking|partners?|partnering|signs? (?:a )?deal|working) with apple\b|"
            r"\b(?:joins? apple|acquired by apple|after apple(?:'s)? acquisition)\b|"
            r"(?:与苹果|和苹果).{0,20}(?:洽谈|合作|签署|达成|评估)|"
            r"(?:加入苹果|被苹果收购)",
            title_lower,
        )
    )
    comparison = bool(
        re.search(
            r"(?:better than|versus|\bvs\.?\b|rival(?:s|ing)?|compared (?:with|to)|beats?|"
            r"overtakes?|surpasses?|dethrones?|exceeds?|挑战|对标|剑指|对决|抗衡|交锋|媲美|优于|胜过|超越|超过|力压|"
            r"接近|相当于|追平|向.{0,20}看齐|酷似|类似(?:于)?)"
            r".{0,50}(?:apple|iphone|ipad|mac|airpods|苹果)",
            title_lower,
        )
        or re.search(r"(?:向|与).{0,24}(?:apple|iphone|ipad|mac|airpods|苹果).{0,12}(?:看齐|相似|类似)", title_lower)
        or re.search(
            r"(?:hard|difficult)\s+to\s+(?:beat|match|challenge).{0,30}(?:apple|iphone|ipad|macbook|airpods)\b|"
            r"(?:难|很难)(?:打|敌|撼动|胜过|匹敌).{0,24}(?:apple|iphone|ipad|macbook|airpods|苹果)",
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
        or re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果).{2,70}"
            r"\b(?:native\s+mac\s+ports?|mac\s+ports?)\b",
            title_lower,
        )
    )
    subject_first_platform_recipient = bool(
        re.search(
            r"^(?!apple\b|iphone\b|foldable\s+iphone\b|folding\s+iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果).{2,80}\b(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|"
            r"updat(?:es|ed|ing)|adds?|added|brings?|brought|tests?|tested|testing|"
            r"being tested|available|arrives?|coming|rolls? out)\b.{0,60}\b(?:on|for|to)\s+(?:select\s+)?"
            r"(?:iphone|ipad|mac|apple watch|apple devices?|apple platforms?|ios|ipados|macos|watchos|tvos|visionos)(?:\s+users?)?\b",
            title_lower,
        )
        or re.search(
            r"^(?!apple\b|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果).{2,80}\b(?:on|for|to)\s+(?:select\s+)?"
            r"(?:iphone|ipad|mac|apple watch|ios|ipados|macos|watchos|tvos|visionos)(?:\s+users?)?\b.{0,50}\b"
            r"(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|updat(?:es|ed|ing)|adds?|added|"
            r"brings?|brought|tests?|tested|testing|available|arrives?|coming|rolls? out)\b",
            title_lower,
        )
        or re.search(
            r"^(?!apple\b|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|苹果).{2,70}"
            r"\b(?:flaw|vulnerability|bug|exploit|malware|attack)\b.{0,90}"
            r"\b(?:including|affect(?:s|ed|ing)?|on|for)\b.{0,24}"
            r"\b(?:iphone|ipad|mac|ios|ipados|macos|watchos)\b",
            title_lower,
        )
    )
    subject_first_owned_platform_update = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果).{2,55}['’]s\s+(?:latest\s+)?"
            r"(?:ios|ipados|macos|watchos|carplay|iphone|ipad|mac)\s+"
            r"(?:app\s+)?(?:update|release|version|feature)\b",
            title_lower,
        )
    )
    subject_first_compatibility = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果)"
            r".{2,90}\b(?:supports?|compatible with|works with|with support for)\b"
            r".{0,30}\b(?:apple|airplay|homekit|iphone|ipad|mac)\b",
            title_lower,
        )
        or re.search(
            r"^(?!苹果|iphone|ipad|mac|airpods).{2,48}(?:音箱|耳机|充电器|配件|设备).{0,30}"
            r"(?:支持|兼容|适配).{0,18}(?:苹果|隔空播放|airplay|homekit|iphone|ipad|mac)",
            title_lower,
        )
    )
    subject_first_apple_hypothetical = bool(
        re.search(r"\bshould\s+apple\b[^?？]*[?？]", title_lower)
        and not first_party_prefix
    )
    subject_first_service_integration = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b)"
            r".{2,70}\b(?:adds?|integrates?|brings?|offers?|supports?)\b.{0,35}"
            r"\bapple\s+(?:music|tv|pay|wallet|carplay)\b",
            title_lower,
        )
    )
    direct_first_party_content = bool(
        re.search(r"\bapple\s+tv(?:\+|['’]s)?\b|苹果\s*tv", title_lower)
        and (
            any(
                (_valid_quoted_subject(match.group(1)) or _valid_content_title(match.group(1)))
                for match in re.finditer(r"[\"'“‘]([^\"'“”‘’\n]{2,48})[\"'”’]", title)
            )
            or re.search(
                r"\b(?:season|series|film|movie|documentary|docuseries|drama|comedy|premiere)\b|"
                r"(?:剧集|剧集|电影|影片|纪录片|首播|最终季)",
                title_lower,
            )
        )
    )
    subject_first_comparison = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b)"
            r".{2,70}(?:thinner|wider|faster|slower|better|worse|larger|smaller|"
            r"compares?|competes?|rivals?|benchmarks?).{0,30}(?:than|against|with).{0,35}apple(?:'s)?\b|"
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b).{2,80}with apple(?:'s)?\b.{0,35}\blooming\b|"
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b).{2,90}(?:closest thing|alternative|answer).{0,24}(?:to|for).{0,28}(?:apple|iphone|ipad|mac|airpods)\b",
            title_lower,
        )
    )
    subject_first_metric_comparison = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|macos\b|airpods\b|苹果)"
            r"[^:：]{2,70}[:：].{0,150}(?:apple|iphone|ipad|mac(?:book|os)?|airpods|苹果)"
            r".{0,45}(?:\d+(?:\.\d+)?\s*(?:x|times?|倍)|higher|lower|more|less|高于|低于|多于|少于)",
            title_lower,
        )
        or re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|macos\b|airpods\b|苹果)"
            r"[^:：]{2,70}[:：].{0,150}(?:\d+(?:\.\d+)?\s*(?:x|times?|倍)|higher|lower|more|less|高于|低于)"
            r".{0,45}(?:apple|iphone|ipad|mac(?:book|os)?|airpods|苹果)",
            title_lower,
        )
    )
    title_clauses = [
        clause.strip()
        for clause in re.split(r"[!！?？:：]", title_lower)
        if clause.strip()
    ]
    comparison_hook_then_non_apple_action = bool(
        len(title_clauses) >= 2
        and not first_party_prefix
        and re.search(r"(?:apple|iphone|ipad|macbook|airpods|苹果)", title_clauses[0])
        and re.search(
            r"(?:compete|rival|challenge|versus|\bvs\.?\b|compare|match|surpass|"
            r"对标|挑战|剑指|对决|抗衡|交锋|比肩|媲美|超越|赶超|三分天下|"
            r"比.{0,18}(?:苹果|iphone|ipad|macbook|airpods).{0,12}更|跟.{0,18}(?:苹果|iphone)|"
            r"与.{0,18}(?:苹果|iphone))",
            title_clauses[0],
        )
        and not re.match(
            r"^(?:apple(?:'s)?|iphone|ipad|macbook|apple watch|airpods|vision pro|苹果)",
            " ".join(title_clauses[1:]),
        )
        and re.search(
            r"(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|ship(?:s|ped|ping)?|"
            r"deliver(?:s|ed|ing)?|debut(?:s|ed|ing)?|announce(?:s|d|ing)?|"
            r"发布|推出|上新|上市|开售|交付|亮相|完成|宣布|曝光)",
            " ".join(title_clauses[1:]),
        )
    )
    independent_user_tool_action = bool(
        title_products
        and not first_party_prefix
        and re.search(
            r"\b(?:reddit\s+)?users?\b.{0,100}\b(?:self[- ](?:built|made|developed)|"
            r"open[- ]source|custom)\b.{0,30}\b(?:app|tool|utility|script)\b|"
            r"(?:reddit\s*)?用户.{0,100}(?:自研|自制|自行开发|开源|自定义).{0,24}(?:应用|工具|脚本|程序)",
            f"{title_lower} {lead_lower[:360]}",
        )
        and not re.search(
            r"(?:apple|苹果).{0,24}(?:发布|推出|更新|修复|开发|宣布|收购|招聘)",
            title_lower,
        )
    )
    platform_edition_third_party_action = bool(
        re.search(
            r"^(?:mac|ios|ipados|iphone|ipad|apple watch)\s*(?:版|version|app)\s*"
            r"(?!(?:apple|ios|ipados|macos|watchos|tvos|visionos|safari|xcode|airpods)\b)"
            r"[a-z][a-z0-9.+-]*(?:\s+[a-z0-9][a-z0-9.+-]*){0,3}\s+"
            r"(?:发布|推出|更新|上线|上架|launch(?:es|ed)?|releas(?:es|ed)?|updat(?:es|ed)?)",
            title_lower,
        )
    )
    subject_first_apple_followup = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b).{2,90}"
            r"\b(?:follows?|following|after|copies|imitates|emulates|takes? a page from)\b"
            r".{0,24}\bapple(?:'s)?\b",
            title_lower,
        )
        or re.search(
            r"^(?!苹果|iphone|ipad|mac|airpods).{2,60}(?:效仿|跟进|追随|照搬|学习)"
            r".{0,12}(?:苹果|apple)",
            title_lower,
        )
    )
    subject_first_apple_response = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果)"
            r".{1,70}\b(?:responds?|response|reacts?|reaction|answers?)\b.{0,70}"
            r"\b(?:apple|iphone|ipad|mac|airpods)\b|"
            r"^(?!苹果|iphone|ipad|mac|airpods).{1,50}(?:回应|答复|评价|表态).{0,40}"
            r"(?:苹果|iphone|ipad|mac|airpods)",
            title_lower,
        )
        and not re.search(
            r"\b(?:lawsuit|court|case|legal|filing|charges?)\b|(?:诉讼|法院|法庭|案件|指控|提交文件)",
            title_lower,
        )
    )
    framed_third_party_action = bool(
        re.search(
            r"^(?:apple|苹果).{0,48}[：:]\s*"
            r"(?!apple\b|苹果|iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|app store\b)"
            r"[a-z0-9][a-z0-9.+-]*(?:\s+[a-z0-9][a-z0-9.+-]*){0,4}.{0,36}"
            r"(?:launch(?:es|ed|ing)?|releas(?:es|ed|ing)|updat(?:es|ed|ing)|"
            r"发布|推出|更新|上线|上架)",
            title_lower,
        )
    )
    speculative_comparison = bool(
        re.search(
            r"^(?!apple\b|iphone\b|ipad\b|mac\b|airpods\b|苹果).{2,110}"
            r"\b(?:hints?|suggests?|signals?|shows?)\b.{0,36}"
            r"(?:what\s+)?apple(?:'s)?\b|"
            r"^(?!苹果|iphone|ipad|mac|airpods).{2,90}(?:暗示|预示|折射|可见)"
            r".{0,30}(?:苹果|iphone|ipad|mac|airpods)",
            title_lower,
        )
    )
    first_party_evidence_signal = bool(
        title_products
        and re.search(
            r"\b(?:job|hiring|recruiting)\s+(?:listing|post|posting)|"
            r"\b(?:code|filing|document|support document)\b|"
            r"(?:招聘(?:信息|启事)?|招募信息|代码|备案文件|支持文档)",
            title_lower,
        )
        and re.match(r"^(?:apple\b|苹果)", lead_lower)
        and re.search(
            r"\b(?:hires?|hiring|recruits?|plans?|tests?|develops?|builds?|adds?|"
            r"launches?|releases?|updates?)\b|"
            r"(?:招聘|招募|计划|测试|开发|构建|新增|推出|发布|更新)",
            lead_lower[:360],
        )
    )
    if (
        (subject_first_comparison or subject_first_metric_comparison)
        and not first_party_prefix
        and not direct_relationship
    ):
        return "third-party-context"
    if (
        comparison_hook_then_non_apple_action
        or independent_user_tool_action
        or platform_edition_third_party_action
    ):
        return "third-party-context"
    if direct_target or direct_relationship or first_party_evidence_signal:
        return "apple-direct"
    contextual_non_apple_action = bool(
        re.search(
            r"^as\s+(?:apple|iphones?|ipads?|macs?|apple\s+watch|airpods).{0,65},\s*"
            r"(?!apple\b|iphone\b|ipad\b|mac(?:book|os)?\b|苹果)"
            r".{2,55}\b(?:launch(?:es|ed)?|offer(?:s|ed)?|introduc(?:es|ed)?|"
            r"announce(?:s|d)?|start(?:s|ed)?|expand(?:s|ed)?)\b",
            title_lower,
        )
        or re.search(
            r"^(?!apple\b|iphone\b|foldable\s+iphone\b|folding\s+iphone\b|ipad\b|ios\b|ipados\b|mac(?:book|os)?\b|watchos\b|"
            r"tvos\b|visionos\b|airpods\b|icloud\b|safari\b|siri\b|carplay\b|xcode\b|"
            r"app store\b|苹果)[a-z0-9][a-z0-9.+-]*(?:\s+[a-z0-9][a-z0-9.+-]*){0,3}\s+"
            r"(?:is\s+|are\s+)?(?:building|launch(?:es|ed|ing)?|offer(?:s|ed|ing)?|"
            r"introduc(?:es|ed|ing)?|announce(?:s|d|ing)?|develop(?:s|ed|ing)?)\b"
            r".{0,100}\b(?:ios|ipados|macos|watchos|tvos|visionos|iphone|ipad|mac\s+apps?|apple\s+watch|airpods|vision\s+pro)\b",
            title_lower,
        )
        or re.search(
            r"^(?!苹果|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods)"
            r"[a-z][a-z0-9.+-]*(?:\s+[a-z][a-z0-9.+-]*){0,3}.{0,36}"
            r"(?:宣布|计划|发布|推出|引入|加入|更新|新增|扩充|强化|上线|上架|适配).{0,70}"
            r"(?:ios|ipados|macos|watchos|tvos|visionos|iphone|ipad|mac|苹果平台|苹果应用商店)",
            title_lower,
        )
        or re.search(
            r"^(?!苹果|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods)"
            r"[^:：]{2,55}(?:宣布|计划|开始|正在|正为|将为).{0,45}"
            r"(?:苹果\s*)?(?:ios|ipados|macos|watchos|tvos|visionos)(?:\s*版|平台)?"
            r".{0,60}(?:引入|加入|新增|推出|上线|更新|测试|推送)",
            title_lower,
        )
        or re.search(
            r"^(?!苹果|iphone|ipad|ios|ipados|mac(?:book|os)?|watchos|tvos|visionos|airpods)"
            r".{2,90}(?:发布|推出|上市|更新|新增|上线|上架).{0,70}"
            r"(?:支持(?:为)?|兼容|适配).{0,24}(?:苹果|iphone|ipad|mac|airpods|苹果平台)",
            title_lower,
        )
        or framed_third_party_action
    )
    if contextual_non_apple_action:
        return "third-party-context"
    embedded_first_party_subject_action = bool(
        title_products
        and re.search(r"(?:apple|苹果).{0,28}(?:fitness\+|[a-z][a-z0-9 +.-]{1,28})", title_lower)
        and re.search(
            r"\b(?:launch(?:es|ed|ing)?|release(?:s|d|ing)?|rolls? out|adds?|"
            r"hires?|hiring|recruits?|plans?|tests?|updates?)\b|"
            r"(?:发布|推出|上线|新增|招聘|招募|计划|测试|更新|调整|收购)",
            title_lower,
        )
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
        re.search(r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b", title_lower)
        and re.match(
            r"^(?:apple(?:'s)?|苹果|传苹果|消息称苹果|报道称苹果|"
            r"leaker\b|report\b|rumor\b|消息\b|报道称|传闻|爆料|"
            r"[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b)",
            title_lower,
        )
        and re.search(
            r"\b(?:report|reported|rumor|rumored|leak|leaker|details?|gains?|"
            r"faster|performance|speed|efficiency|cost|price)\b|"
            r"(?:消息|报道|传闻|爆料|性能|速度|能效|成本|价格)",
            title_lower,
        )
        and re.search(r"\bapple(?:'s)?\b|苹果", lead_lower[:360])
    )
    if (
        first_party_prefix
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
            r"(?:better than|versus|\bvs\.?\b|rival(?:s|ing)?|compared (?:with|to)|beats?|"
            r"closest thing.{0,18}(?:to|for)|alternative.{0,18}(?:to|for)|answer.{0,18}(?:to|for)|"
            r"挑战|对标|媲美|优于|胜过).{0,50}(?:apple|iphone|ipad|mac|airpods|苹果)",
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
    title_scope = _title_scope(title, lead)
    title_products = _collapse_product_hierarchy(_extract_patterns(title_lower, PRODUCT_PATTERNS))
    first_party_model_scope = f"{title_lower} {lead_lower[:260]}"
    if (
        title_scope == "apple-direct"
        and re.search(r"\b(?:ai|artificial intelligence)\b|(?:ai|人工智能|大模型)", first_party_model_scope)
        and re.search(
            r"\b(?:train(?:s|ed|ing)?|develop(?:s|ed|ing)?|custom model|own model)\b|"
            r"(?:训练|自研|自主研发|定制).{0,20}(?:模型|大模型)",
            first_party_model_scope,
        )
    ):
        title_products.add("apple-intelligence")
    if (
        re.match(r"^beats\b", title_lower)
        and re.search(
            r"\b(?:lab|laboratory|engineering|r&d)\b|(?:实验室|工程实验室|研发)",
            title_lower,
        )
    ):
        title_products.add("beats")
    if (
        re.search(r"^(?:apple\b|苹果)", title_lower)
        and re.search(r"\b(?:smart|ai)\s+glasses\b|智能眼镜|苹果眼镜", title_lower)
    ):
        title_products.add("apple-glasses")
    if re.search(r"苹果[^，。！？:：]{0,18}(?:家庭|智能家居)中枢", title_lower):
        title_products.add("apple-home-hub")
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
        "shazam",
    }
    if content_form != "roundup" and not (title_products & direct_service_products):
        products |= _extract_patterns(lead_lower[:260], PRODUCT_PATTERNS) & direct_service_products
    title_components = _extract_patterns(title_lower, COMPONENT_PATTERNS)
    leadership_scope = f"{title_lower} {lead_lower[:260]}"
    if (
        title_scope == "apple-direct"
        and re.search(r"\b(?:tim cook|apple ceo|chief executive)\b|(?:库克|苹果\s*ceo|首席执行官)", leadership_scope)
        and re.search(
            r"\b(?:legacy|transition|steps? down|leav(?:e|es|ing)|final weeks?|succession)\b|"
            r"(?:卸任|交接|接班|任期|管理遗产|领导层)",
            leadership_scope,
        )
    ):
        title_components.add("apple-leadership")
    if (
        title_scope == "apple-direct"
        and re.search(r"\b(?:refurbished|refurb)\b|(?:官翻|官方翻新)", title_lower)
        and re.search(r"\b(?:store|catalog)\b|(?:商店|阵容|目录)", title_lower)
    ):
        title_components.add("official-refurbished-catalog")
    if re.search(
        r"\b(?:cost|costs|costing)\b.{0,28}\b(?:build|built|make|manufacture|produce)\b|"
        r"\b(?:cost|costs|costing)\b.{0,36}\b(?:more|less)\b.{0,18}"
        r"\b(?:parts?|components?|materials?)\b|"
        r"(?:制造|生产|整机|零部件|物料).{0,12}成本|成本.{0,12}(?:制造|生产|整机|零部件|物料)|"
        r"成本(?:大增|上升|增加|上涨|提高)[^，。！？:：]{0,16}(?:\d+(?:\.\d+)?\s*%|近|约|达到|达)",
        title_lower,
    ):
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

        season_pattern = re.compile(r"\bseason\s*(\d{1,2})\b|第\s*(\d{1,2})\s*季")
        for match in season_pattern.finditer(f"{title_lower} {lead_lower[:420]}"):
            components.add(f"content-season:{match.group(1) or match.group(2)}")
        for match in re.finditer(r"\b(20\d{2})\b", f"{title_lower} {lead_lower[:320]}"):
            components.add(f"content-year:{match.group(1)}")
    product_generation_components = {
        f"product-generation:{match.group(1)}-{match.group(2)}"
        for match in re.finditer(
            r"(?<![a-z0-9])(iphone|ipad)\s*(\d{1,2})(?!\d)",
            title_lower,
        )
    }
    anniversary_iphone_generations = {
        next(group for group in match.groups() if group)
        for match in re.finditer(
            r"(?:\b(\d{1,2})(?:st|nd|rd|th)?\s+anniversary\s+iphone\b|"
            r"\biphone(?:'s)?\s+(\d{1,2})(?:st|nd|rd|th)?\s+anniversary\b|"
            r"(?<!\d)(\d{1,2})\s*周年(?:纪念版)?\s*iphone\b|"
            r"\biphone\s*(\d{1,2})\s*周年(?:纪念版)?)",
            title_lower,
        )
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
    for match in re.finditer(r"(?<![a-z0-9])iphone\s+air\s*(\d{1,2})?(?![a-z0-9])", title_lower):
        generation = match.group(1)
        iphone_model_components.add(
            f"iphone-model:air-{generation}" if generation else "iphone-line:air"
        )
    for match in re.finditer(
        r"(?<![a-z0-9])iphone\s*(\d{1,2})(?!\d)(?:\s*(pro\s+max|pro|max|plus|mini|ultra|e))?(?![a-z0-9])",
        title_lower,
    ):
        generation, variant = match.groups()
        trailing_scope = title_lower[match.end() : match.end() + 10]
        if not variant and re.match(r"\s*(?:series|系列)", trailing_scope):
            continue
        variant = re.sub(r"\s+", "-", variant or "base")
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
    for match in re.finditer(r"(?<![a-z0-9])([ma]\d{1,2})(?!\d)", title_lower):
        prefix = title_lower[max(0, match.start() - 28) : match.start()]
        if re.search(
            r"(?:\bnot|rather\s+than|instead\s+of)\b.{0,12}$|(?:而非|并非|不是|非).{0,8}$",
            prefix,
        ):
            continue
        apple_silicon_generation_components.add(
            f"apple-silicon-generation:{match.group(1)}"
        )
    title_components |= apple_silicon_generation_components
    components |= apple_silicon_generation_components
    if (products or title_scope == "apple-direct") and re.search(
        r"\b(?:shipments?|market\s+share|sales\s+(?:slump|decline|growth)|unit\s+sales|"
        r"best[- ]selling|top[- ]selling)\b|"
        r"(?:出货量|市场份额|销量|出货|同比(?:增长|下降)|最畅销|销量最高|销售冠军)",
        title_lower,
    ):
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
    if re.search(shipment_plan_change_pattern, title_lower):
        title_components.add("hardware-shipment-plan-change")
        components.add("hardware-shipment-plan-change")
    elif re.search(shipment_plan_change_pattern, lead_lower[:620]):
        components.add("hardware-shipment-plan-change")
    if products and re.search(
        r"\b(?:next[- ]generation|second[- ]generation|roadmap|in\s+development|"
        r"plans?\s+for|expected\s+(?:in|for)|coming\s+in|launch(?:es|ing)?\s+in)\b|"
        r"(?:第二代|下一代|路线图|产品前瞻|笔记本前瞻|计划.{0,20}(?:推出|发布)|"
        r"预计.{0,20}(?:推出|发布))",
        title_lower,
    ):
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
    display_size_pattern = re.compile(r"(?<!\d)(\d(?:\.\d+)?)\s*(?:-?inch|英寸)")
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
            re.search(r"\blargest(?:\s+ever)?\s+iphone\s+(?:screen|display)\b", title_lower)
            or re.search(r"\biphone\b.{0,32}\blargest(?:\s+ever)?\s+(?:screen|display)\b", title_lower)
            or re.search(r"(?:史上最大|最大(?:的)?|超大)(?:[^。！？\n]{0,24})iphone|iphone(?:[^。！？\n]{0,24})(?:史上最大|最大(?:的)?|超大)(?:屏|显示)", title_lower)
            or bool(title_display_sizes & {"display-size:6.96-inch", "display-size:7-inch"})
        )
    )
    if largest_iphone_display_title:
        title_components.add("largest-iphone-display")
        components.add("largest-iphone-display")
    financed_device_restriction_negated = bool(
        re.search(
            r"\b(?:isn['’]t|is\s+not|aren['’]t|are\s+not|won['’]t|will\s+not|not\s+for)\b"
            r".{0,90}\b(?:lease|leases|leased|financed|financing|apple\s+upgrade|upgrade\s+program)\b|"
            r"(?:并非|不是|不会|不用于|无关).{0,40}(?:租赁|月租|分期|apple\s*upgrade)",
            title_lower,
        )
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
    if (
        title_scope == "apple-direct"
        and "apple-intelligence" in title_products
        and re.search(
            r"\b(?:train(?:s|ed|ing)?|develop(?:s|ed|ing)?|custom model|own model)\b|"
            r"(?:训练|自研|自主研发|定制).{0,20}(?:模型|大模型)",
            title_lower,
        )
    ):
        title_actions.add("model-development")
    if "apple-leadership" in title_components:
        title_actions.add("leadership-transition")
    if (
        title_scope == "apple-direct"
        and "apple-maps" in title_products
        and re.search(
            r"\b(?:open(?:s|ed)?|accept(?:s|ed|ing)?|available)\b.{0,32}"
            r"\b(?:ad|ads|advertising)\b.{0,24}\b(?:book|booking|reservation)\b|"
            r"\b(?:ad|ads|advertising)\b.{0,24}\b(?:book|booking|reservation|available)\b|"
            r"(?:广告位|地图广告).{0,20}(?:招商|预订|接受|开放)",
            title_lower,
        )
    ):
        title_actions.add("commercial-launch")
    if (
        title_scope == "apple-direct"
        and re.search(r"\b(?:ad|advertising|campaign|poster)\b|(?:广告|宣传海报|宣传活动)", title_lower)
        and re.search(r"\b(?:withdraw(?:s|n)?|pull(?:s|ed)?|remove(?:s|d)?)\b|(?:撤下|撤回|移除)", title_lower)
    ):
        title_actions.add("withdrawal")
    if (
        "official-refurbished-catalog" in title_components
        and re.search(r"\b(?:add(?:s|ed|ing)?|expand(?:s|ed|ing)?)\b|(?:新增|扩充|扩展)", title_lower)
    ):
        title_actions.add("catalog-expansion")
    if re.search(
        r"\b(?:lets?|allows?|enables?)\s+(?:you|users?|people)\s+(?:to\s+)?"
        r"(?:make|set|adjust|change|choose|use|view|control)\b|"
        r"(?:让|允许|支持)用户.{0,18}(?:调整|设置|更改|选择|使用|查看|控制)",
        title_lower,
    ):
        title_actions.add("feature-change")
    if "price-change" in title_actions:
        price_mentions = list(
            re.finditer(
                r"\b(?:price increase|price hike)\b|(?:涨价|提价|上调价格|上调售价|降价)",
                title_lower,
            )
        )
        if price_mentions and all(
            re.search(
                r"(?:\b(?:no|not|without)\b\s*|(?:不|不会|未|没有|并未)\s*)$",
                title_lower[max(0, match.start() - 12) : match.start()],
            )
            for match in price_mentions
        ):
            title_actions.discard("price-change")
    if re.search(
        r"\b(?:denies?|disputes?|refutes?|counters?|pours?(?:\s+cold)?\s+water\s+on)\b"
        r".{0,90}\b(?:rumou?r|report|claim)\b|"
        r"(?:否认|反驳).{0,48}(?:传闻|报道|说法)|"
        r"(?:否认|反驳).{0,72}(?:不存在|没有|不实)|"
        r"(?:传闻|报道|说法).{0,48}(?:不实|被否认|遭否认)",
        title_lower,
    ):
        title_actions.add("claim-denial")
    if re.search(
        r"\benters?\s+(?:the\s+)?[a-z][a-z -]{0,24}\s+market\b|"
        r"(?:进入|登陆)[^，。！？:：]{0,16}市场",
        title_lower,
    ):
        title_actions.add("retail-availability")
    actions = set(title_actions)
    if re.search(
        r"\b(?:to|will|would|could|may|might|expected\s+to|reportedly\s+to)\s+feature\b",
        title_lower,
    ):
        title_actions.add("feature-change")
        actions.add("feature-change")
    if content_form != "roundup":
        actions |= _extract_patterns(lead_lower[:500], ACTION_PATTERNS)
    integration_pattern = (
        r"\b(?:integrates?|integrated|integration|connect(?:ed|s|ing)?|embeds?|embedded|"
        r"power(?:s|ed|ing)?\s+(?:the\s+)?navigation|at\s+the\s+core\s+of)\b|"
        r"(?:整合|集成|嵌入|接入|驱动导航|作为.{0,12}核心)"
    )
    if re.search(integration_pattern, title_lower):
        title_actions.add("platform-integration")
        actions.add("platform-integration")
    elif re.search(integration_pattern, lead_lower[:500]):
        actions.add("platform-integration")
    first_party_data_pattern = (
        r"(?<![a-z0-9])(?:apple\s+health|healthkit|apple\s+wallet|eventkit|homekit)(?![a-z0-9])|"
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
        or re.search(
            r"\b(?:series|film|movie|documentary|docuseries|show|season)\b|"
            r"(?:剧集|电影|影片|纪录片|节目|季度|最终季)",
            f"{title_lower} {lead_lower[:240]}",
        )
    )
    if content_lifecycle_subject and re.search(content_lifecycle_pattern, title_lower):
        title_actions.add("content-release")
        actions.add("content-release")
    elif content_lifecycle_subject and re.search(content_lifecycle_pattern, lead_lower[:500]):
        actions.add("content-release")
    official_product_communication = bool(
        re.search(
            r"\bapple\b.{0,40}\b(?:shares?|publishes|posts?|releases?)\b.{0,40}\b(?:video|story)\b",
            title_lower,
        )
        or re.search(
            r"苹果.{0,40}(?:发布|分享).{0,40}(?:视频|故事|案例)",
            title_lower,
        )
    )
    if official_product_communication:
        title_actions.add("official-communication")
        actions.add("official-communication")
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
        r"\b(?:could|may|might|will)\s+be\b.{0,24}\b(?:more\s+)?expensive\b|"
        r"\b(?:more\s+)?expensive\b.{0,24}\b(?:than|price|prices|pricing|cost|costs)\b|"
        r"\b(?:raise[sd]?|increase[sd]?|update[sd]?|bump(?:s|ed)?)\b.{0,36}\b(?:trade[ -]in\s+(?:value|values|offer|offers|estimate|estimates))\b|"
        r"(?:上调|提高|调高|调整).{0,24}(?:价格|售价|订阅价|以旧换新|折抵价|折抵估值)|(?:价格|售价|折抵价|折抵估值).{0,18}(?:上调|上涨|提高|调整)"
    )
    if re.search(price_change_pattern, title_lower):
        title_actions.add("price-change")
        actions.add("price-change")
    elif re.search(price_change_pattern, lead_lower[:220]):
        actions.add("price-change")
    primary_intent: str | None = None
    if _is_analyst_target_action_title(title_lower):
        primary_intent = "analyst-target"
    elif not re.search(
        r"\b(?:recruits?|hires?|rehire[sd]?|brings?\s+back|adds?)\b|"
        r"(?:返聘|召回|重新聘用|重新启用|组建)",
        title_lower,
    ) and re.search(
        r"(?:ceo|chief executive|tim cook|john ternus|steve jobs|库克|特努斯|乔布斯|首席执行官)"
        r".{0,40}(?:tenure|\d{1,2}\s*years?|in numbers|retrospective|任期|掌舵|历程|回顾|收官)",
        title_lower,
    ):
        primary_intent = "executive-retrospective"
    elif re.search(
        r"(?:apple|aapl|苹果).{0,35}(?:stock|shares|share\s+price|market\s+cap|valuation|股价|市值).{0,35}"
        r"(?:fall|falls|fell|drop|drops|plunge|plunges|lose|loses|lost|erase|erases|evaporate|蒸发|大跌|下跌|暴跌|重挫)|"
        r"(?:stock|shares|share\s+price|market\s+cap|valuation|股价|市值).{0,35}"
        r"(?:fall|falls|fell|drop|drops|plunge|plunges|lose|loses|lost|erase|erases|evaporate|蒸发|大跌|下跌|暴跌|重挫)",
        title_lower,
    ):
        primary_intent = "market-move"
    elif re.search(r"(?:lawmakers?|legislators?|senators?|congress|议员|国会)", title_lower) and re.search(
        r"(?:memory|storage\s+chips?|supplier|内存|存储芯片|供应商)", title_lower
    ) and re.search(r"(?:demand|require|commit|ban|not\s+use|要求|承诺|不用|禁止|施压)", title_lower):
        primary_intent = "memory-supplier-policy"
    elif (
        ("price-change" in title_actions or "apple-product-price-increase" in facets)
        and "component-cost-analysis" not in title_components
        and not re.search(r"\b(?:no|not|won['’]t|will\s+not)\b.{0,18}\b(?:price|prices|pricing)\b|(?:不|不会|未).{0,8}(?:涨价|提价|上调价格)", title_lower)
    ):
        primary_intent = "product-price-change"
    elif re.search(r"(?:\bai\b|artificial intelligence|人工智能|算力)", title_lower) and re.search(
        r"(?:shortage|constraint|risk|delay|insufficient|limited|短缺|不足|风险|延迟|受限)",
        title_lower,
    ):
        primary_intent = "compute-capacity-risk"
    elif re.search(r"(?:supply|availability|output|供货|供应|产量)", title_lower) and re.search(
        r"(?:shortage|constraint|tight|limited|紧张|短缺|受限|不足)", title_lower
    ):
        primary_intent = "product-supply-constraint"
    elif re.search(r"(?:\bai\b|artificial intelligence|人工智能)", title_lower) and re.search(
        r"(?:capex|capital expenditure|spending|investment|invest|资本开支|投入|投资|砸钱)", title_lower
    ):
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
                for match in re.finditer(
                    r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+){0,2})\b",
                    f"{title_lower} {lead_lower[:260]}",
                )
            }
        )
    main_title = re.split(r"[\[\(（【]", title_lower, maxsplit=1)[0]
    title_release_versions = sorted(
        {
            _normalized_os_version(match.group(1))
            for match in re.finditer(
                r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(\d+(?:\.\d+){0,2})\b",
                main_title,
            )
        }
    )
    title_is_public_beta = bool(
        re.search(r"\bpublic betas?\b|公测(?:版|测试版)?", main_title)
    )
    if title_is_public_beta:
        components.add("os-release-channel:public")
    elif re.search(
        r"\b(?:developer(?:s)?|developer beta)\b|"
        r"(?:开发者预览版|开发者测试版|开发者测试)",
        main_title,
    ):
        components.add("os-release-channel:developer")
    title_has_explicit_beta_number = bool(
        re.search(r"\bbeta\s*\d+\b|测试版\s*\d+|第\s*\d+\s*(?:个|版)?\s*测试版", main_title)
    )
    numbered_beta_stages = sorted(
        facet.removeprefix("os-release-")
        for facet in facets
        if re.fullmatch(r"os-release-beta-\d+", facet)
    )
    title_beta_match = re.search(r"\bbeta\s*(\d+)\b", main_title)
    title_public_beta_match = re.search(
        r"\bpublic\s+beta\s*(\d+)\b|"
        r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*公测(?:版|测试版)?",
        main_title,
    )
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
            public_lead_match = re.search(
                r"\bpublic\s+betas?\s*(\d+)\b|"
                r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth)\s+"
                r"(?:(?:ios|ipados|macos|watchos|tvos|visionos)(?:\s+\d+(?:\.\d+){0,2})?\s+)?"
                r"public\s+betas?\b|"
                r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*公测(?:版|测试版)?",
                lead_lower[:220],
            )
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
                    }.get(raw_number)
                )
                if number:
                    numbered_beta_stages = [f"beta-{number}"]
        beta_match = None if title_is_public_beta else re.search(
            r"\bbeta\s*(\d+)\b", release_scope
        )
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
            }
            ordinal_match = re.search(
                r"\b(?:round|developer beta)\s+(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth)\b",
                release_scope,
            ) or re.search(
                r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth)\s+"
                r"(?:round\s+of\s+)?developer\s+betas?\b",
                release_scope,
            ) or re.search(
                r"\b(one|first|two|second|three|third|four|fourth|five|fifth|six|sixth)\s+"
                r"(?:ios|ipados|macos|watchos|tvos|visionos)"
                r"(?:\s*(?:,|and|&|/)?\s*(?:ios|ipados|macos|watchos|tvos|visionos))*"
                r"(?:\s+[a-z][a-z0-9-]+){0,2}\s+"
                r"public betas?\b",
                main_title,
            )
            if ordinal_match:
                ordinal = ordinal_numbers[ordinal_match.group(1)]
                # "First macOS Public Beta" names the first public wave, not
                # developer beta 1. Later ordinals still distinguish public
                # beta 2/3 waves from the initial unnumbered public release.
                if not (title_is_public_beta and ordinal == "1"):
                    numbered_beta_stages = [f"beta-{ordinal}"]
        if not numbered_beta_stages:
            chinese_match = re.search(
                r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*(?:开发者)?(?:测试版|预览版)",
                release_scope,
            )
            if not chinese_match:
                chinese_match = re.search(
                    r"第\s*([一二三四五六七八九十\d]+)\s*(?:个|轮)?\s*公测(?:版|测试版)?",
                    release_scope,
                )
            if chinese_match:
                raw_number = chinese_match.group(1)
                number = raw_number if raw_number.isdigit() else chinese_number_map.get(raw_number)
                if number:
                    numbered_beta_stages = [f"beta-{number}"]
    title_is_signing_closure = bool(
        re.search(
            r"\b(?:stops?|stopped|ceases?|ceased)\s+signing\b|"
            r"\bno\s+longer\s+signs?\b|"
            r"(?:停止签署|停止签名|关闭.{0,12}签名(?:验证|通道)?)",
            main_title,
        )
    )
    title_is_release_wave = not title_is_signing_closure and bool(
        re.search(
            r"\b(?:releases?|released|ships?|shipped|seeds?|seeded|rolls? out|now available|available now|is here|are out now|arrives?|lands?|revised|surfaces?|is coming soon|are coming soon|coming next week)\b|"
            r"\bstarts?\s+round\b|\bversion\s*2\s+update\b|"
            r"(?:即将发布|最快.{0,8}发布|发布|推送|释出|修订版)|(?:正式版|候选版).{0,12}上线",
            main_title,
        )
    )
    title_has_beta_stage = bool(
        numbered_beta_stages
        and re.search(r"\bbetas?\b|(?:开发者|公测|测试版|预览版)", main_title)
    )
    title_has_rc_stage = bool(
        re.search(r"\brelease candidates?\b|\brc\b|候选版", main_title)
    )
    title_has_final_stage = bool(
        title_is_release_wave
        and not title_is_public_beta
        and not title_has_beta_stage
        and not title_has_rc_stage
        and re.search(
            r"\b(?:releases?|released|ships?|shipped|rolls? out|now available|available now|is here|are out now|arrives?|lands?)\b|"
            r"(?:正式发布|正式推送|正式版|面向全体用户|面向公众|"
            r"推送.{0,24}安全更新|发布.{0,24}安全更新|安全更新.{0,12}(?:发布|推送))",
            main_title,
        )
    )
    mixed_title_release_stages = bool(
        title_has_beta_stage
        and re.search(r"(?:安全更新|正式版|面向全体用户|面向公众)", main_title)
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
            for match in re.finditer(
                r"\b(ios|ipados|macos|watchos|tvos|visionos)\b",
                main_title,
            )
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
    )
