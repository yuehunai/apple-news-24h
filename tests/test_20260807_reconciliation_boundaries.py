import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260807_test", SCRIPT_PATH)
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
        published_utc=datetime(2026, 8, 6, tzinfo=timezone.utc),
        published_raw="2026-08-06T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


def group_titles(groups):
    return [{article.title for article in group} for group in groups]


class AugustSeventhReconciliationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_platform_runtime_does_not_turn_third_party_model_or_app_into_apple_action(self):
        cases = [
            (
                "苹果 iPhone 上最快本地 AI 模型：Maple-Preview-20B-A1B 登场，可达 127 tokens/s",
                "美国独立 AI 研究实验室 DeepGrove 发布 Maple-Preview 模型，可在 iPhone（原文并未明确具体机型）上运行；苹果没有发布、批准或改变平台能力。",
                "IT之家",
                [
                    "Maple-Preview-20B-A1B 采用 ternary-weight 量化，拥有 200 亿参数。",
                    "测试称该模型在 iPhone 上可达到每秒 127 个 token。",
                ],
            ),
            (
                "可直接调用微距、长焦：微信 iOS 版灰度测试相机多焦段切换功能",
                "微信团队灰度测试自己的 iOS 应用相机功能，可调用 iPhone 的微距和长焦镜头；苹果没有改变 iOS 接口或系统能力。",
                "IT之家",
                [],
            ),
        ]
        for title, summary, source, facts in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, facts, source)
                self.assertEqual(tier, "weak", reason)

    def test_first_party_trade_in_market_metrics_and_os_features_stay_strong(self):
        cases = [
            (
                "Apple Raises Trade-In Values for iPhone, Mac, and More",
                "Apple updated its U.S. trade-in estimates, raising values for most iPhone, iPad, Mac, and Apple Watch models and adding Android phones.",
                "MacRumors",
            ),
            (
                "Apple increases trade-in offers and adds new Android devices",
                "Apple bumped up its own trade-in offers for iPhones, iPads, Macs, Apple Watches, and selected Android phones.",
                "The Verge",
            ),
            (
                "Apple holds 65% of the premium smartphone market as segment reaches record high",
                "Counterpoint measured Apple at 65% of premium smartphone sales in the first half of 2026, up from 63% a year earlier.",
                "9to5Mac",
            ),
            (
                "iOS 27 hints at all-new Home product launching soon",
                "iOS 27 upgrades HomeKit Secure Video with 4K video, AI descriptions, and search; the report says those direct platform changes may support a rumored Apple security camera.",
                "9to5Mac",
                [
                    "HomeKit Secure Video gains 4K video, AI descriptions, and natural-language search.",
                    "The direct iOS 27 platform change is available in Apple's Home app.",
                    "Accessory makers may later build cameras that use the expanded platform capability.",
                    "The article discusses third-party security camera accessories as market context.",
                    "A related accessory recommendation mentions compatible Home products.",
                    "Third-party accessories are not the subject of the Apple platform update.",
                ],
            ),
        ]
        for case in cases:
            title, summary, source, *case_facts = case
            facts = case_facts[0] if case_facts else []
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, facts, source)
                self.assertEqual(tier, "strong", reason)

    def test_reconciler_splits_different_products_actions_and_legal_cases(self):
        supply = article_for(
            self.module,
            "iPhone 18 Pro could have limited availability right after launch: report",
            "A DRAM shortage is holding up iPhone 18 Pro production and may constrain launch inventory.",
        )
        features = article_for(
            self.module,
            "传 iPhone 18 Pro 带来三大升级：可变光圈、缩小灵动岛、C2 基带",
            "报道列出相机、屏幕与通信三项硬件升级。",
            "cnBeta",
        )
        openai = article_for(
            self.module,
            "OpenAI asks for Apple's trade secrets lawsuit to be dismissed",
            "OpenAI filed a motion asking the judge to dismiss Apple's trade-secret lawsuit.",
        )
        prosser = article_for(
            self.module,
            "Apple flags delays in Jon Prosser's response to leak lawsuit",
            "Discovery in Apple's separate Jon Prosser leak case was extended after response delays.",
        )
        macbook = article_for(
            self.module,
            "MacBook Ultra is coming, here's the latest on release timing",
            "Apple is testing a MacBook Ultra roadmap with OLED and touch support.",
        )
        iphone_display = article_for(
            self.module,
            "传苹果 2027 年 iPhone Pro Max 屏幕将突破 7 英寸",
            "A supply-chain report describes larger displays for a future iPhone generation.",
            "cnBeta",
        )
        articles = [supply, features, openai, prosser, macbook, iphone_display]
        groups = self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[supply, features], [openai, prosser], [macbook, iphone_display]],
        )
        titles = group_titles(groups)
        for article in articles:
            self.assertIn({article.title}, titles)

    def test_reconciler_merges_cross_source_duplicates_by_concrete_action(self):
        variants = [
            article_for(
                self.module,
                "Apple Raises Trade-In Values for iPhone, Mac, and More",
                "Apple updated its U.S. trade-in estimates and raised values across its device lineup.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "存储涨价后：苹果上调多款 iPhone、iPad、Mac 以旧换新折抵价",
                "苹果调整官方以旧换新最高估值，多款设备的折抵价上涨。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Apple TV's surprise hit series is making the jump to theaters for one night only",
                "Apple TV will show Widow's Bay at AMC theaters in six cities on August 12 for one night.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple TV offers free 'Widow's Bay' AMC screenings",
                "Apple TV and AMC will hold free Widow's Bay screenings in six cities on August 12.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "MacBook Ultra is coming, here's the latest on release timing",
                "Apple is testing 14-inch and 16-inch MacBook Ultra models with OLED touch displays.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果 MacBook Ultra 10 月来袭：首发 OLED 触控屏",
                "新款 MacBook Ultra 据称采用 OLED 触控屏并在 10 月推出。",
                "快科技",
            ),
        ]
        groups = self.module.reconcile_articles(
            variants,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[article] for article in variants],
        )
        sizes = sorted(len(group) for group in groups)
        self.assertEqual(sizes, [2, 2, 2])

    def test_home_video_upgrade_and_apple_camera_roadmap_merge_across_languages(self):
        english = article_for(
            self.module,
            "iOS 27 hints at all-new Home product launching soon",
            "iOS 27 upgrades HomeKit Secure Video with 4K recording, AI video descriptions, and natural-language search ahead of a rumored Apple home security camera.",
            "9to5Mac",
        )
        chinese = article_for(
            self.module,
            "苹果首款家用安防摄像头有望今秋登场：支持 4K，可用 AI 描述画面",
            "报道基于 iOS 27 对 HomeKit 安全视频的 4K、AI 画面描述和自然语言搜索升级，称苹果有望推出自有家用安防摄像头。",
            "IT之家",
        )
        third_party = article_for(
            self.module,
            "Aqara launches a new HomeKit Secure Video camera",
            "Aqara launched its own compatible camera; Apple did not change HomeKit or announce a first-party camera roadmap.",
            "The Verge",
        )
        groups = self.module.reconcile_articles(
            [english, chinese, third_party],
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[english], [chinese], [third_party]],
        )
        self.assertIn({english.title, chinese.title}, group_titles(groups))
        self.assertIn({third_party.title}, group_titles(groups))

    def test_industry_roundup_and_repackaged_analysis_do_not_become_main_events(self):
        cases = [
            (
                "2026 年度旗舰集中在 9 月亮相：2nm 成为主角",
                "文章汇总苹果、高通、联发科、vivo 和多家安卓厂商的旗舰路线，苹果只是其中一个行业例子。",
                "快科技",
            ),
            (
                "DRAM 内存连涨 6 个月！国产大厂拒绝压价",
                "文章讨论全球 DRAM 行业价格和云服务商需求，并把苹果与长鑫谈判作为其中一个案例。",
                "快科技",
            ),
            (
                "Apple prepares for iPhone 18 Pro and Ultra launch by expanding its reach",
                "The analysis combines Apple's already launched leasing program, the current trade-in value update, and Android switcher support to argue that expensive phones may be easier to sell; it reports no additional Apple action.",
                "9to5Mac",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)


if __name__ == "__main__":
    unittest.main()
