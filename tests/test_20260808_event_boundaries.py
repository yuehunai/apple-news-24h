import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260808_test", SCRIPT_PATH)
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
        published_utc=datetime(2026, 8, 8, tzinfo=timezone.utc),
        published_raw="2026-08-08T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class AugustEighthEventBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_refurbished_configuration_numbers_are_not_numbered_announcements(self):
        title = "Apple expands refurb store with rare M5 MacBook Pro configs, Apple TV 4K, more"
        summary = "Apple added new M5 MacBook Pro configurations and Apple TV 4K units to its Certified Refurbished Store."
        facts = [
            "14-inch M5 MacBook Pro with 512GB storage and 16GB memory: $1,439",
            "15-inch M5 MacBook Air with 4TB storage and 24GB memory: $2,969",
            "The Apple TV 4K is available again from Apple's Certified Refurbished Store.",
        ]

        variants = self.module.compound_article_variants(title, summary, facts)

        self.assertEqual(variants, [(title, summary, facts)])

    def test_refurbished_roadmap_and_third_party_asset_disposal_stay_separate(self):
        refurbished = article_for(
            self.module,
            "Apple expands refurb store with rare M5 MacBook Pro configs, Apple TV 4K, more",
            "Apple added M5 MacBook Pro configurations and Apple TV 4K units to its Certified Refurbished Store.",
        )
        roadmap = article_for(
            self.module,
            "MacBook Pro users will soon have two compelling new upgrade options",
            "A report says Apple plans an M6 MacBook Pro and a distinct MacBook Ultra with OLED and touch support this fall.",
        )
        disposal = article_for(
            self.module,
            "Tech company to destroy more than 100 M4 MacBook Pro units after layoffs",
            "An unnamed employer plans to destroy company-owned M4 MacBook Pro computers after laying off staff; Apple announced no product action.",
            "cnBeta",
        )

        events = self.module.cluster_articles([refurbished, roadmap, disposal])

        self.assertEqual(len(events), 3)
        self.assertEqual(disposal.relevance_tier, "weak")
        self.assertEqual({event.articles[0].url for event in events}, {article.url for article in [refurbished, roadmap, disposal]})

    def test_product_anniversary_reports_merge_across_languages(self):
        english = article_for(
            self.module,
            "Mac Pro Turns 20 Today, Five Months After Apple Killed It",
            "Apple introduced the first Mac Pro on August 7, 2006, and discontinued the product line in March 2026.",
            "MacRumors",
        )
        chinese = article_for(
            self.module,
            "苹果旗舰台式机 Mac Pro 迎来 20 周年纪念，停产已有五个月",
            "苹果于 2006 年 8 月 7 日发布初代 Mac Pro，并于 2026 年 3 月停售该产品线。",
            "IT之家",
        )

        events = self.module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_editorial_framing_cannot_demote_a_current_first_party_action(self):
        cases = [
            (
                "Apple Wallet in iOS 27 adds feature that's been on my wishlist for years",
                "iOS 27 adds Create a Pass, letting users scan physical membership cards or tickets and save their barcodes to Apple Wallet.",
                "9to5Mac",
                "strong",
            ),
            (
                "Why does Apple keep banning Telegram, but never X?",
                "For roughly an hour this week, Telegram vanished from Apple's App Store. Apple said it removed the app over CSAM and restored it after the content was removed.",
                "The Verge",
                "strong",
            ),
        ]
        for title, summary, source, expected in cases:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary, source)
                events = self.module.cluster_articles([article])
                self.assertEqual(events[0].relevance_tier, expected, events[0].relevance_reason)

    def test_poll_and_third_party_tool_update_are_weak(self):
        cases = [
            (
                "iPhone 18 Pro vs foldable iPhone Ultra: Which will you buy?",
                "Vote in our reader poll after reviewing previously reported features for both phones.",
                "9to5Mac",
            ),
            (
                "Claude Code now lets sessions talk to each other on macOS",
                "Anthropic released Claude Code 2.1.224 for macOS and Linux so its own sessions can exchange summaries; Apple made no platform change.",
                "9to5Mac",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_third_party_platform_update_stays_discoverable_for_deferred_review(self):
        candidate = self.module.Candidate(
            source="9to5Mac",
            url="https://example.com/claude-code-macos-update",
            title="Claude Code now lets sessions talk to each other on macOS",
            summary="Users running the latest version of Claude Code on macOS and Linux can now have their sessions message each other.",
        )
        source = self.module.Source(
            name="9to5Mac",
            default_tz="America/Los_Angeles",
            domains=("9to5mac.com",),
        )

        self.assertTrue(self.module.is_relevant_candidate(candidate, source))

    def test_explicit_multi_product_roadmap_projects_product_scoped_variants(self):
        title = "Apple rumored to launch three new Ultra products by early next year"
        facts = [
            "The foldable iPhone Ultra is expected in September with a 7.7-inch inner display.",
            "AirPods Ultra may add infrared cameras for hands-free Visual Intelligence.",
            "MacBook Ultra is expected in early 2027 with an OLED touchscreen.",
        ]
        variants = self.module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(len(variants), 3)
        variant_titles = {variant[0] for variant in variants}
        self.assertTrue(any("iPhone" in value for value in variant_titles))
        self.assertTrue(any("AirPods" in value for value in variant_titles))
        self.assertTrue(any("MacBook" in value for value in variant_titles))

    def test_explicit_mac_upgrade_options_project_to_specific_models(self):
        title = "MacBook Pro users will soon have two compelling new upgrade options"
        facts = [
            "The M6 MacBook Pro keeps the current design and moves to Apple's first 2nm Mac chip.",
            "MacBook Ultra adds an OLED touchscreen, a thinner design, and M5 Pro or M5 Max options.",
        ]

        variants = self.module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(len(variants), 2)
        self.assertEqual(
            {variant[0] for variant in variants},
            {"Apple MacBook Pro roadmap update", "Apple MacBook Ultra roadmap update"},
        )

    def test_software_release_wording_does_not_create_hardware_roadmap_variants(self):
        title = "发布 326 天，苹果 iOS 26 在 iPhone 11/iPad 9 等机型上迎来首次越狱"
        summary = "Dopamine 团队发布 iOS 26 越狱工具，正文同时列出 iPhone、iPad 和 Apple TV 的支持历史。"
        facts = [
            "该越狱支持部分 iPhone 和 iPad 机型。",
            "Apple TV 只在正文的旧版支持列表中被提及。",
        ]

        variants = self.module.compound_article_variants(title, summary, facts)

        self.assertEqual(variants, [(title, summary, facts)])

    def test_different_wallet_objects_and_actions_do_not_merge(self):
        account_card = article_for(
            self.module,
            "Apple Account Card Expands Again: What It Is and What It Isn't",
            "Apple this week expanded support for its Apple Account Card in Wallet to Estonia, Latvia, Lithuania, and Malta.",
            "MacRumors",
            ["The card displays the balance associated with a user's Apple Account and can be used at Apple Store locations."],
        )
        physical_pass = article_for(
            self.module,
            "Apple Wallet in iOS 27 adds feature that's been on my wishlist for years",
            "iOS 27 lets users scan physical membership cards and event tickets into Apple Wallet as barcode passes.",
            "9to5Mac",
            [
                "Users can point the Camera app at a physical card or screenshot and save a barcode or QR code pass.",
                "The imported pass is available on iPhone and Apple Watch.",
            ],
        )

        events = self.module.cluster_articles([account_card, physical_pass])

        self.assertEqual(len(events), 2)

    def test_shop_at_apple_refurbished_promo_is_removed_from_article_tail(self):
        html = (
            "<article><p>iOS 27 lets users scan physical membership cards into Apple Wallet, "
            "save their barcodes, and present the resulting pass from an iPhone or Apple Watch "
            "without carrying the original card.</p>"
            "<h3>*Shop at Apple with 15% discount on certified refurbished</h3>"
            "<p>Recommended accessories and store links follow.</p></article>"
        )

        cleaned = self.module.remove_trailing_promo_sections(html)

        self.assertIn("physical membership cards", cleaned)
        self.assertNotIn("certified refurbished", cleaned)

    def test_shared_product_name_cannot_merge_incompatible_event_actions(self):
        health_feature = article_for(
            self.module,
            "watchOS 27 could make Apple Watch's important new health feature even better",
            "Apple Watch added hypertension notifications last year, and watchOS 27 may improve the feature after FDA review.",
            "9to5Mac",
            [
                "The change is a watchOS software feature and may extend to older Apple Watch models.",
            ],
        )
        refurbished_store = article_for(
            self.module,
            "降幅 10~15%：苹果美国扩充官翻 Mac、Apple Watch、Apple TV 4K 等产品",
            "苹果美国官网扩充认证翻新产品阵容，新增 Mac、Apple Watch、Apple TV 4K 和 iPhone 配置。",
            "IT之家",
            [
                "翻新商品享有一年有限保修和 14 天退货政策。",
            ],
        )

        events = self.module.cluster_articles([health_feature, refurbished_store])

        self.assertEqual(len(events), 2)

    def test_official_refurbished_store_action_merges_across_languages(self):
        english = article_for(
            self.module,
            "Apple expands refurb store with rare M5 MacBook Pro configs, Apple TV 4K, more",
            "Apple added M5 MacBook Pro, Apple Watch, and Apple TV 4K products to its Certified Refurbished Store.",
            "9to5Mac",
        )
        chinese = article_for(
            self.module,
            "降幅 10~15%：苹果美国扩充官翻 Mac、Apple Watch、Apple TV 4K 等产品",
            "苹果美国官网扩充翻新产品阵容并上架多款 Mac、Apple Watch、Apple TV 4K 和 iPhone 配置。",
            "IT之家",
        )

        events = self.module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_apple_operated_mfi_compatibility_list_update_is_strong(self):
        tier, reason = self.module.classify_relevance_tier(
            "Apple adds nearly 45 hearing devices to its Made for iPhone compatibility list",
            "Apple updated its official MFi hearing-device list to 623 models across 104 brands.",
            ["The current update adds 43 models across 22 brands."],
            "9to5Mac",
        )

        self.assertEqual(tier, "strong", reason)

    def test_apple_compatibility_list_update_does_not_merge_with_service_content(self):
        compatibility = article_for(
            self.module,
            "Apple adds nearly 45 hearing devices to its Made for iPhone compatibility list",
            "Apple updated its official MFi list to 623 supported hearing devices across 104 brands.",
            "9to5Mac",
        )
        arcade = article_for(
            self.module,
            "Madden NFL 27 launches on Apple Arcade",
            "EA released Madden NFL 27 through Apple Arcade for iPhone, iPad, Mac, and Apple TV.",
            "IT之家",
        )

        events = self.module.cluster_articles([compatibility, arcade])

        self.assertEqual(len(events), 2)
        self.assertEqual(compatibility.event_kind, "os_compatibility")
        self.assertIn(
            "apple-operated-compatibility-list-update",
            self.module.topic_facets_from_text(
                " ".join([compatibility.title, compatibility.summary, *compatibility.key_facts])
            ),
        )

    def test_apple_operated_activity_challenge_is_strong_software_event(self):
        title = "苹果庆祝“全国健身日”邀请 Apple Watch 用户今日挑战：健身 20+ 分钟解锁限量奖章"
        summary = (
            "苹果公司邀请 Apple Watch 用户在 8 月 8 日记录至少 20 分钟锻炼，即可获得限量版奖章。"
            "用户可以使用 Apple Watch 自带的体能训练 App，或任何能够将运动数据记录至健康 App 的第三方应用。"
        )

        article = article_for(self.module, title, summary, "IT之家")
        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "software_systems")
        self.assertIn(
            "apple-operated-activity-challenge",
            self.module.topic_facets_from_text(f"{title} {summary}"),
        )

    def test_third_party_activity_challenge_remains_weak(self):
        tier, reason = self.module.classify_relevance_tier(
            "Fitness app launches an Apple Watch activity challenge",
            "The third-party app invites users to complete a workout and unlock a badge on Apple Watch.",
            [],
            "9to5Mac",
        )

        self.assertEqual(tier, "weak", reason)

    def test_event_summary_drops_background_from_other_os_actions(self):
        article = article_for(
            self.module,
            "Apple Testing iOS 26.6.1 Update for iPhones",
            (
                "Apple's software engineers are internally testing iOS 26.6.1. "
                "Apple already released macOS 26.6.1 with a Screen Sharing security fix. "
                "iOS 26.6.1 would likely include bug fixes or security fixes. "
                "iOS 27 beta 5 is still awaiting release to developers."
            ),
            "MacRumors",
            [
                "Apple already released macOS 26.6.1 with a Screen Sharing security fix.",
                "iOS 26.6.1 would likely include bug fixes or security fixes.",
                "iOS 27 beta 5 is still awaiting release to developers.",
            ],
        )

        _title, summary, facts = self.module.build_event_summary([article])

        self.assertIn("iOS 26.6.1", summary)
        self.assertNotIn("macOS", summary)
        self.assertNotIn("iOS 27", summary)
        self.assertFalse(any("macOS" in fact or "iOS 27" in fact for fact in facts))

        background_only = self.module.filter_key_facts_for_primary_topic(
            article.title,
            "Apple's software engineers are internally testing iOS 26.6.1.",
            ["Apple released macOS 26.6.1 to fix a Screen Sharing authentication vulnerability."],
        )
        self.assertEqual(background_only, [])

        sparse_title_background = self.module.filter_key_facts_for_primary_topic(
            "iOS 26.6.1 likely coming soon as Apple speeds up iPhone updates",
            "Apple appears to be testing a forthcoming iOS 26.6.1 update for iPhone users.",
            ["Apple released macOS Sonoma 14.8.9, Sequoia 15.7.9, and Tahoe 26.6.1."],
        )
        self.assertEqual(sparse_title_background, [])

        chinese_compact_background = self.module.filter_key_facts_for_primary_topic(
            "消息称苹果正测试 iOS 26.6.1 系统，或修复安全漏洞",
            "苹果内部正测试 iOS 26.6.1。参考同日发布的 macOS 26.6.1 屏幕共享修复。",
            ["苹果今日推出 macOS 26.6.1 Tahoe，修复屏幕共享认证漏洞。"],
        )
        self.assertEqual(chinese_compact_background, [])

    def test_app_store_removal_restoration_action_is_must_include(self):
        article = article_for(
            self.module,
            "Why does Apple keep banning Telegram, but never X?",
            (
                "For roughly an hour, Telegram vanished from Apple's App Store. "
                "Apple said it removed the app because of CSAM and restored it once that content was removed. "
                "Apple previously removed Telegram for a similar violation in 2018."
            ),
            "The Verge",
        )
        event = self.module.cluster_articles([article])[0]

        facts = self.module.event_must_include_facts(event)

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertTrue(any("restored" in fact and "CSAM" in fact for fact in facts), facts)
        self.assertFalse(any("previously" in fact or "2018" in fact for fact in facts), facts)


if __name__ == "__main__":
    unittest.main()
