import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260815_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = facts or []
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 15, tzinfo=timezone.utc),
        published_raw="2026-08-15T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


def title_sets(groups):
    return [{article.title for article in group} for group in groups]


class AuthoritativeEventIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def reconcile(self, articles, initial_groups=None):
        return self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=initial_groups or [[article] for article in articles],
        )

    def test_editorial_form_and_action_owner_are_authoritative_for_relevance(self):
        cases = [
            (
                "Qualcomm Snapdragon C revealed: still hard to beat MacBook Neo",
                "Qualcomm unveiled its own processor and used Apple's notebook only as a performance comparison.",
                "快科技",
            ),
            (
                "Classic games get native Mac ports through decompilation",
                "An independent preservation project ported third-party games to macOS; Apple made no platform change.",
                "AppleInsider",
            ),
            (
                "New Apple Watch models launch next month, here's what's coming",
                "The article compiles previously reported rumors about several expected models without new reporting.",
                "9to5Mac",
            ),
            (
                "tvOS 27 could push you to upgrade to new Apple TV 4K",
                "An editorial argues existing tvOS features may make an upgrade worthwhile.",
                "9to5Mac",
            ),
            (
                "No new Apple Watch faces in watchOS 27, but here's one I've been loving",
                "The writer describes a personal favorite among existing watch faces and reports no new Apple action.",
                "9to5Mac",
            ),
            (
                "苹果 AirPods Pro 4 耳机最新消息汇总：摄像头与手势识别成焦点",
                "文章汇总此前关于多款未来耳机的传闻，没有本轮新增的独立报道。",
                "IT之家",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_title_led_first_party_actions_remain_strong_across_source_wording(self):
        cases = [
            (
                "Apple trained its own AI model for the China market with a local partner",
                "The first-party model is intended for Apple Intelligence services in China.",
                "MacRumors",
            ),
            (
                "苹果为中国市场训练自研 AI 模型，由本地合作伙伴提供支持",
                "苹果为国行 Apple Intelligence 训练第一方模型。",
                "快科技",
            ),
            (
                "Apple Maps opens ad booking for businesses in the US and Canada",
                "Apple opened reservations for a new first-party Maps advertising program.",
                "9to5Mac",
            ),
            (
                "Ads are now available to book in Apple Maps",
                "Apple opened merchant reservations for Maps ads in two countries.",
                "MacRumors",
            ),
            (
                "苹果在意大利撤下争议 iPhone 宣传海报",
                "苹果因监管争议主动撤下其第一方广告。",
                "IT之家",
            ),
            (
                "Tim Cook reflects on his legacy before leaving the Apple CEO role",
                "Cook discussed the leadership transition and how he hopes his Apple tenure is remembered.",
                "MacRumors",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "strong", reason)

    def test_same_first_party_action_reconciles_across_language_and_initial_tier(self):
        groups = [
            [
                article_for(
                    self.module,
                    "Apple trained its own AI model for China with help from a local partner",
                    "Apple developed a first-party model for Apple Intelligence in China.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "苹果联合本地伙伴训练中国市场自研 AI 模型",
                    "该模型将用于国行 Apple Intelligence。",
                    "快科技",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Apple Maps opens ad booking for businesses in the US and Canada",
                    "Apple opened reservations for its Maps advertising program.",
                    "9to5Mac",
                ),
                article_for(
                    self.module,
                    "苹果地图广告位开始接受美国和加拿大商家预订",
                    "苹果开放 Apple Maps 第一方广告项目预订。",
                    "IT之家",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Tim Cook reflects on his legacy before leaving the Apple CEO role",
                    "Cook discussed his Apple leadership transition in a new interview.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "库克卸任前接受采访，回顾担任苹果 CEO 的经历",
                    "库克在新的交接采访中谈到自己的管理遗产。",
                    "快科技",
                ),
            ],
        ]
        articles = [article for group in groups for article in group]
        reconciled = title_sets(self.reconcile(articles))
        for expected in groups:
            self.assertIn({article.title for article in expected}, reconciled)

    def test_catalog_update_uses_catalog_action_not_individual_listed_model_as_boundary(self):
        english = article_for(
            self.module,
            "Apple adds MacBook Air configs, iPhone 16 Plus, more to refurb store",
            "Apple expanded its official refurbished catalog with several Mac and iPhone models.",
            "9to5Mac",
        )
        chinese = article_for(
            self.module,
            "苹果美国扩充官翻阵容，新增 iPhone 16 Plus 和多款 MacBook Pro",
            "苹果扩充同一官方翻新商店目录，新增多款设备。",
            "IT之家",
        )
        groups = self.reconcile([english, chinese])
        self.assertEqual(len(groups), 1, title_sets(groups))

    def test_roundup_cannot_bridge_a_current_single_action_report(self):
        roundup = article_for(
            self.module,
            "September phone outlook: everything expected from Apple and rivals",
            "A broad roundup compiles existing expectations for several vendors and products.",
            "快科技",
        )
        current = article_for(
            self.module,
            "Supplier confirms iPhone 18 production starts in September",
            "A named supplier disclosed a current production schedule for Apple's iPhone 18.",
            "IT之家",
        )
        groups = self.reconcile([roundup, current], [[roundup, current]])
        self.assertEqual(len(groups), 2, title_sets(groups))

    def test_non_apple_consumption_research_is_not_promoted_as_hardware_market_news(self):
        title = "iPhone users spend 40% more on microdrama apps than Android users"
        summary = (
            "Omdia and Sensor Tower compared audience payment behavior across mobile platforms. "
            "iPhone users spent $14 per week and Android users spent $10, while paid-user rates "
            "were 69% and 68%."
        )

        tier, reason = self.module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_title_led_apple_shipment_result_remains_strong(self):
        title = "Counterpoint: iPhone shipments grew 8% in Latin America during Q1"
        summary = (
            "Counterpoint measured Apple's quarterly iPhone shipments and regional smartphone "
            "market share, including the year-over-year shipment change."
        )

        tier, reason = self.module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "strong", reason)

    def test_named_first_party_hardware_refresh_outranks_ai_feature_background(self):
        title = "苹果 HomePod mini 2 今秋有望亮相：升级 Siri AI 芯片"
        summary = (
            "第二代 HomePod mini 预计换用更快的处理器和新一代 UWB 硬件，"
            "并改善扬声器、麦克风和音频表现。"
        )

        self.assertTrue(self.module.is_apple_hardware_product_launch_story(f"{title} {summary}", title))
        self.assertEqual(self.module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(self.module.choose_category(title, summary), "hardware_products")

    def test_os_feature_on_named_hardware_remains_software(self):
        title = "iOS 27 adds a new Siri interface on iPhone"
        summary = "Apple changed the built-in Siri interface in the current iOS 27 beta."

        self.assertFalse(self.module.is_apple_hardware_product_launch_story(f"{title} {summary}", title))
        self.assertEqual(self.module.choose_category(title, summary), "software_systems")


if __name__ == "__main__":
    unittest.main()
