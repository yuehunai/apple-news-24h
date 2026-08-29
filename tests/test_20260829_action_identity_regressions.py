import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260829_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((title, summary)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc),
        published_raw="2026-08-29T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


class ActionIdentityRegressions20260829(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_third_party_product_sale_with_apple_home_compatibility_stays_weak(self):
        article = article_for(
            self.module,
            "Aqara 智能窗帘电机 C100 开售：原生支持 Apple Home，售 399 元",
            "该产品售价 399 元，支持多种窗型适配，可接入苹果 Home 生态。",
            "IT之家",
            [
                "Aqara 智能窗帘电机 C100 今日开售，原生支持 Apple Home。",
                "支持 iPhone、Apple Watch、HomePod 控制窗帘并与其他 Apple Home 设备联动。",
            ],
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_first_person_experience_and_upgrade_editorials_stay_weak(self):
        articles = [
            article_for(
                self.module,
                "This video experiment perfectly illustrates my frustration with iPhone Cinematic mode",
                "I tested an existing iPhone feature and explain why I believe Apple should improve it.",
                facts=[
                    "The author filmed a friend with an iPhone 16 Pro Max and observed focus errors.",
                    "The article asks Apple to take greater advantage of current chip performance.",
                ],
            ),
            article_for(
                self.module,
                "iPhone 18 Pro: Two new features I’m excited to upgrade for",
                "Previously reported camera and A20 Pro rumors are presented as the author's upgrade motivation.",
                facts=[
                    "Mark Gurman previously described a camera hardware leap.",
                    "The author says cameras and A20 Pro are the top two reasons to upgrade.",
                ],
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertTrue(all(event.relevance_tier == "weak" for event in events), events)

    def test_multi_year_rumor_catalog_stays_weak_without_new_report(self):
        article = article_for(
            self.module,
            "iPhone Ultra rumors: design, release date, cost",
            "Rumors of a folding iPhone go back more than a decade and the article catalogs conflicting predictions.",
            "AppleInsider",
            [
                "The article recounts release predictions from 2017 through 2026.",
                "Past predictions for 2020, 2022, 2023, 2024, and 2025 did not materialize.",
            ],
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_disaster_relief_reports_merge_by_beneficiary_and_action(self):
        articles = [
            article_for(
                self.module,
                "Apple Pledges Donation for Nepal and Tibet Flood Relief",
                "Apple CEO Tim Cook pledged a company donation for relief and rebuilding after floods in Nepal and Tibet.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Tim Cook宣布援助尼泊尔洪灾受灾民众 或将继续负责苹果救灾声明",
                "苹果首席执行官 Tim Cook 宣布苹果将向尼泊尔与西藏洪灾救援和重建工作提供捐款。",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "cnBeta"})

    def test_content_rights_reports_merge_by_named_work_and_rights_action(self):
        articles = [
            article_for(
                self.module,
                "Apple TV acquires breakout British hit comedy for global streaming",
                "Apple TV has picked up a new comedy series, Small Prophets, for its streaming service in an atypical fashion.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple TV Buys an Existing Hit for the First Time Ever",
                "Apple TV bought worldwide rights to Small Prophets after its BBC run and will stream it globally on October 7.",
                "MacRumors",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "MacRumors"})

    def test_preorder_schedule_reports_merge_despite_secondary_product_context(self):
        articles = [
            article_for(
                self.module,
                "iPhone 18 Pro pre-orders could kick off slightly later than usual",
                "iPhone 18 Pro will be unveiled on September 9, and a new report says pre-orders will kick off slightly later than usual.",
                "9to5Mac",
                ["iPhone 18 Pro pre-orders likely starting Saturday, September 12."],
            ),
            article_for(
                self.module,
                "iPhone 18 Pro Pre-Orders May Start at an Unusual Time",
                "Apple may open iPhone 18 Pro pre-orders on Saturday, September 12 at midnight Pacific, a day later than usual.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "It's not clear when iPhone 18 Pro and folding iPhone preorders will start",
                "Apple will reportedly sidestep a September 11 preorder date by moving sales to Saturday.",
                "AppleInsider",
                ["The company is expected to open preorders at 12:01 a.m. Pacific."],
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(
            {article.source for article in events[0].articles},
            {"9to5Mac", "MacRumors", "AppleInsider"},
        )

    def test_named_apple_history_auction_has_one_consistent_strong_tier(self):
        facts = [
            "RR Auction sold Steve Jobs' 1968 science project for $34,375.",
            "The same Apple anniversary auction sold a working Apple-1 for $499,363.",
        ]
        articles = [
            article_for(
                self.module,
                "Steve Jobs' 8th-grade science project sells for $34,375",
                "RR Auction sold the named Steve Jobs science project in an Apple anniversary auction.",
                "AppleInsider",
                facts,
            ),
            article_for(
                self.module,
                "苹果前 CEO 乔布斯“1968 年亲手制作的中学科学展览项目”拍卖落槌，成交价 34,375 美元",
                "RR Auction 完成苹果 50 周年主题拍卖，乔布斯中学科学项目以 34,375 美元成交。",
                "IT之家",
                facts,
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertNotIn("mixed relevance tiers", events[0].merge_warnings)

    def test_editorial_framing_does_not_demote_concrete_versioned_os_feature(self):
        article = article_for(
            self.module,
            "Apple Photos in iOS 27 upgrades one of my favorite features in a big way",
            (
                "Apple Photos is full of updates in iOS 27. Shared Albums now support "
                "full-resolution photos and videos, and users can react with any emoji."
            ),
            "9to5Mac",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "software_systems")

    def test_official_apple_store_checkout_financing_option_is_strong(self):
        article = article_for(
            self.module,
            "支付服务登陆苹果 Apple Store 在线商店，支持最长 24 期免息买 iPhone",
            (
                "用户在 Apple Store 在线商店购买 iPhone、Mac 和 iPad 时，"
                "现在可在结账时选择最长 24 期免息付款，且不收额外利息或手续费。"
            ),
            "IT之家",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_disaster_relief_facts_drop_unrelated_leadership_background(self):
        title = "Apple Pledges Donation for Nepal and Tibet Flood Relief"
        summary = (
            "Apple CEO Tim Cook pledged a company donation for relief and rebuilding "
            "after floods in Nepal and Tibet."
        )
        facts = [
            "Apple will make a donation toward relief and rebuilding work in Nepal and Tibet.",
            "Apple did not disclose the amount or form of the aid.",
            (
                "Cook again promised disaster relief. "
                "It is one of his final acts before a successor becomes CEO on September 1."
            ),
            "John Ternus replaces Cook as CEO on September 1 while Cook becomes executive chairman.",
        ]

        filtered = self.module.filter_key_facts_for_primary_topic(title, summary, facts)

        self.assertEqual(filtered, [facts[0], facts[1], "Cook again promised disaster relief."])


if __name__ == "__main__":
    unittest.main()
