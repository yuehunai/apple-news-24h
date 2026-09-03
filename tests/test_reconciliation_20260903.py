import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


class Reconciliation20260903Tests(unittest.TestCase):
    def test_apple_technology_reference_does_not_own_competitor_adoption(self):
        for title, lead in [
            ("Apple's iPhone Ultra Crease Fix Set for Android Foldables Next Year",
             "The Elec reports that Google, Oppo, and Vivo plan to adopt ultra-thin glass in their foldable phones next year, following Apple's lead."),
            ("Apple's iPad display method is coming to Windows tablets",
             "A report says competing manufacturers will adopt a new display stack next year, following Apple's lead."),
            ("苹果 iPad 的显示方案明年将用于安卓平板",
             "报道称，其他厂商计划采用新的显示技术，跟随苹果此前的技术路线。"),
        ]:
            with self.subTest(title=title):
                article = self.article(
                    title, f"{title}. {lead} Apple's product is expected to be unveiled next week, using the existing method.",
                    "MacRumors", ["The layers will be mass produced for Apple's rivals for wide adoption in 2027."],
                )
                self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
                events = self.module.cluster_articles([article])
                self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_direct_hardware_disclosures_stay_strong(self):
        for title, lead in [
            ("Apple's iPhone Ultra gains new display technology",
             "A new report says Apple is using a revised display stack in its upcoming phone. Competitors may adopt similar methods later."),
        ]:
            with self.subTest(title=title):
                article = self.article(title, lead, "MacRumors")
                self.assertIn(article.relevance_tier, {"strong", "ecosystem"}, article.relevance_reason)
                self.assertIn(self.module.cluster_articles([article])[0].relevance_tier, {"strong", "ecosystem"})

    def test_launch_year_stays_with_its_primary_assertion(self):
        article = self.article(
            "Apple plans to unveil its first smart glasses next year",
            "Apple plans to unveil its first smart glasses next year. "
            "Apple will launch its smart glasses in 2028. Other manufacturers launched their models in 2027.",
            facts=["The industry report also discusses a rival's 2026 launch."],
        )
        keys = self.profile(article).event_keys
        self.assertIn("primary-claim:apple-glasses:launch-roadmap:2028", keys)
        self.assertNotIn("primary-claim:apple-glasses:launch-roadmap:2026", keys)
        self.assertNotIn("primary-claim:apple-glasses:launch-roadmap:2027", keys)

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("reconciliation_20260903", SCRIPT_PATH)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def article(self, title, summary, source="9to5Mac", facts=()):
        m = self.module
        tier, reason = m.classify_relevance_tier(title, summary, list(facts), source)
        return m.Article(
            source=source,
            url=f"https://example.test/{source}/{title}",
            title=title,
            summary=summary,
            key_facts=list(facts),
            category=m.choose_category(title, summary),
            published_utc=datetime(2026, 9, 3, tzinfo=timezone.utc),
            published_raw="2026-09-03T00:00:00Z",
            published_source="test",
            confidence="detail",
            tokens=m.article_tokens(title, " ".join([summary, *facts])),
            event_kind=m.detect_event_kind(title, summary, list(facts)),
            relevance_tier=tier,
            relevance_reason=reason,
            regions=m.extract_regions(" ".join([title, summary, *facts])),
        )

    def profile(self, article):
        return self.module.article_reconciliation_profile(article)

    def assert_groups(self, articles, expected):
        events = self.module.cluster_articles(articles)
        self.assertEqual(
            {frozenset(a.url for a in event.articles) for event in events},
            {frozenset(articles[i].url for i in group) for group in expected},
        )
        self.assertCountEqual(
            [a.url for event in events for a in event.articles],
            [a.url for a in articles],
        )
        return events

    def content_articles(self, work="Being Heumann", other="Mayday"):
        return [
            self.article(
                "Apple’s new film from ‘Best Picture’ Oscar winner gets first trailer - 9to5Mac",
                f"Award-winning CODA director Siân Heder is back with another Apple awards contender: {work}. "
                "Here’s the new trailer. Apple TV just added a lot of classic movies to its library.",
                facts=[f"{work} will stream November 13 on Apple TV.",
                       f"Other films coming soon include Ryan Reynolds’ {other}, which premieres this week."],
            ),
            self.article(
                "Ryan Reynolds’ new Apple TV spy movie is a winner, reviews here - 9to5Mac",
                f"Apple TV premieres {other} this week, a new Ryan Reynolds film. And reviews say it’s a winner.",
                facts=["Joining the 15 free classic movies just added for subscribers, Apple has original films premiering soon.",
                       f"{other} premieres this Friday, September 4 on Apple TV."],
            ),
            self.article(
                "Apple TV adds 15 classic movies to its catalog",
                "Apple TV added a collection of classic movies that subscribers can stream at no extra cost.",
                "MacRumors",
            ),
        ]

    def test_trailer_reviews_and_catalog_are_distinct_actions(self):
        for work, other in [("Being Heumann", "Mayday"), ("Open Horizons", "Silent Harbor")]:
            with self.subTest(work=work):
                self.assert_groups(self.content_articles(work, other), [{0}, {1}, {2}])

    def test_trailer_claim_uses_primary_work_not_award_or_possessive(self):
        p = self.profile(self.content_articles()[0])
        self.assertIn("content-title:being-heumann", p.separation_keys)
        self.assertIn("content-action:trailer", p.separation_keys)
        self.assertNotIn("content-title:best-picture", p.separation_keys)

    def test_review_claim_does_not_take_background_catalog_or_premiere_action(self):
        p = self.profile(self.content_articles()[1])
        self.assertIn("content-title:mayday", p.separation_keys)
        self.assertIn("content-action:reviews", p.separation_keys)
        self.assertNotIn("content-action:catalog-addition", p.separation_keys)
        self.assertNotIn("content-action:premiere-schedule", p.separation_keys)

    def test_catalog_addition_can_be_owned_by_sparse_title_and_primary_lead(self):
        articles = [self.article(
            "Apple TV expands its library",
            "Apple TV added a collection of classic films for subscribers to stream at no extra cost.",
        ), self.article(
            "苹果 Apple TV 新增经典影片",
            "苹果为订阅用户新增经典电影片库。",
            "IT之家",
        )]
        self.assert_groups(articles, [{0, 1}])
        for a in articles:
            self.assertIn("content-action:catalog-addition", self.profile(a).separation_keys)

    def test_possessive_apostrophes_are_not_opening_work_quotes(self):
        a = self.article(
            "Apple TV acquires a new movie for global streaming",
            "Apple's streaming service bought worldwide rights to 'Silent Harbor', a director's new film.",
        )
        p = self.profile(a)
        self.assertIn("content-title:silent-harbor", p.separation_keys)
        self.assertEqual(
            {k for k in p.separation_keys if k.startswith("content-title:")},
            {"content-title:silent-harbor"},
        )

    def test_same_work_trailer_and_reviews_still_stay_separate(self):
        self.assert_groups(self.content_articles("Silent Harbor", "Silent Harbor"), [{0}, {1}, {2}])

    def test_internal_possessive_is_part_of_quoted_work(self):
        for work, slug in [("‘Widow’s Bay’", "widow-s-bay"), ("'Mother's Day'", "mother-s-day")]:
            with self.subTest(work=work):
                for title, lead in [
                    ("Apple TV acquires a film for global streaming", f"Apple's streaming service bought worldwide rights to {work}."),
                    (f"Apple TV shares first trailer for movie {work}", f"Apple released a trailer for movie {work}."),
                ]:
                    self.assertIn(f"content-title:{slug}", self.profile(self.article(title, lead)).separation_keys)

    def handoff_articles(self, version=27):
        return [
            self.article(
                f"iOS {version} Introduces New 'iPhone Handoff' Feature",
                f'Apple has added a new "iPhone Handoff" feature to iOS {version} that will allow you '
                "to switch between two iPhones while using the same phone number on each device. "
                "It was mentioned on a slide listing hundreds of new features at WWDC.",
                "MacRumors",
            ),
            self.article(
                f"苹果 iOS {version} 新增“iPhone 接力”功能，两部手机可共用同一号码",
                f"该功能可让两台 iPhone 共用一个电话号码自由切换，需两部运行 iOS {version} 的设备和运营商支持。"
                "苹果之前在列有数百项新功能的 PPT 上简要提及此功能。",
                "IT之家",
            ),
            self.article(
                f"苹果iOS {version}新增iPhone接力功能：两台手机共用一个eSIM号码",
                f"苹果iOS {version}加入全新iPhone Handoff功能，允许两台iPhone来回切换、共用同一个手机号码。"
                "该功能曾在WWDC功能清单幻灯片短暂亮相。",
                "快科技",
            ),
        ]

    def test_named_os_feature_merges_by_concrete_operation_across_languages(self):
        self.assert_groups(self.handoff_articles(), [{0, 1, 2}])

    def test_named_os_feature_not_replaced_by_background_acronym(self):
        profiles = [self.profile(a) for a in self.handoff_articles()]
        for p in profiles:
            self.assertFalse(any(k.endswith(":ppt") or k.endswith(":multi-feature") for k in p.event_keys))
        self.assertTrue(set.intersection(*(set(p.event_keys) for p in profiles)))

    def test_os_feature_version_and_distinct_operation_do_not_merge(self):
        articles = [self.handoff_articles(27)[0], self.handoff_articles(28)[1], self.article(
            "iOS 27 introduces a new iPhone photo transfer feature",
            "Apple added a feature to copy pictures between two iPhones. "
            "The slide also listed the iPhone Handoff feature for sharing a phone number.",
            "IT之家",
        )]
        self.assert_groups(articles, [{0}, {1}, {2}])

    def test_versioned_cross_device_operations_generalize_to_accounts_and_sessions(self):
        for platform, device, resource, resource_cn in [
            ("macOS", "Mac", "account", "账户"),
            ("iPadOS", "iPad", "session", "会话"),
        ]:
            with self.subTest(platform=platform):
                articles = [self.article(
                    f"{platform} 27 adds a new cross-device feature",
                    f"Apple allows users to switch between two {device}s while using the same {resource}.",
                    "MacRumors",
                ), self.article(
                    f"苹果 {platform} 27 新增跨设备功能",
                    f"苹果允许两台 {device} 共用同一个{resource_cn}，并在设备之间切换。",
                    "IT之家",
                )]
                self.assert_groups(articles, [{0, 1}])
                shared = self.profile(articles[0]).event_keys & self.profile(articles[1]).event_keys
                self.assertTrue(any(k.startswith("primary-claim:") for k in shared))

    def test_feature_name_alone_does_not_prove_resource_switching(self):
        a = self.article(
            "苹果 iOS 27 新增 iPhone 接力功能",
            "两台 iPhone 使用同一个电话号码，但本文没有说明设备之间的操作。",
            "IT之家",
        )
        self.assertFalse(any(k.startswith("primary-claim:") for k in self.profile(a).event_keys))

    def color_articles(self, generation=18):
        return [
            self.article(
                f"Leakers battle over whether third iPhone {generation} Pro color will be silver or black",
                f"Leaks agree on two of the three colors expected for iPhone {generation} Pro. "
                "Two leakers disagree on whether the third colour will be silver or black.",
            ),
            self.article(
                f"Leaked iPhone {generation} Pro Parts Point to Three Color Options Excluding Black",
                f"A leaker shared an image of SIM card trays for iPhone {generation} Pro, suggesting silver, sky blue and dark cherry, without black.",
                "MacRumors",
            ),
            self.article(
                f"泄露的iPhone {generation} Pro卡托零部件暗示将推出三种机身配色 或再次取消黑色",
                f"爆料者分享不同颜色SIM卡托照片，称部件属于iPhone {generation} Pro。"
                "照片显示银色、天空蓝和深樱桃色三种配色，没有黑色。",
                "cnBeta",
            ),
            self.article(
                f"没有黑色：苹果 iPhone {generation} Pro / Max 三种颜色卡托曝光",
                f"消息源分享 iPhone {generation} Pro 和 Pro Max 的 SIM 卡托，显示银色、天空蓝和深樱桃色，没有黑色。",
                "IT之家",
            ),
        ]

    def test_indirect_color_dispute_bridges_same_model_finish_disclosure(self):
        for generation in [18, 19]:
            with self.subTest(generation=generation):
                events = self.assert_groups(self.color_articles(generation), [{0, 1, 2, 3}])
                self.assertEqual(events[0].relevance_tier, "strong")

    def test_color_disclosure_not_other_generation_launch_or_camera(self):
        articles = [self.color_articles(18)[0], self.color_articles(19)[1], self.article(
            "Apple launches iPhone 18 Pro in three colors",
            "Apple announced retail availability for the iPhone 18 Pro in silver, blue and red.",
            "AppleInsider",
        ), self.article(
            "iPhone 18 Pro camera sensor upgrade leaks",
            "A new camera sensor is in development. Background rumors suggest three colors.",
            "IT之家",
        )]
        self.assert_groups(articles, [{0}, {1}, {2}, {3}])

    def test_color_count_must_belong_to_current_model_not_background(self):
        a = self.article(
            "Leaker battle: will iPhone 18 Pro come in silver or not?",
            "Leakers disagree about a silver color for iPhone 18 Pro. "
            "Last year, iPhone 17 Pro came in three colors. The new lineup is not known.",
        )
        self.assertFalse(any(
            key.startswith("primary-claim:iphone-18-pro:finish-lineup-disclosure:")
            for key in self.profile(a).event_keys
        ))

    def test_same_model_and_color_count_do_not_prove_same_disclosure(self):
        articles = [self.color_articles()[1], self.article(
            "Leaked iPhone 18 Pro prototype reveals three colors",
            "A separate prototype batch has gold, green and pink finishes, excluding white.",
            "IT之家",
        )]
        self.assert_groups(articles, [{0}, {1}])

    def test_intel_policy_owns_rosetta_background_without_rewriting_facts(self):
        summary = (
            "Apple has notified developers they no longer need to make their apps compatible with Intel Macs. "
            "The article also quotes a support document about upcoming changes to Rosetta support."
        )
        facts = [
            "Universal macOS apps on the Mac App Store that require macOS 13 or later can now remove support for Intel-based Mac computers.",
            "A previously published support document says macOS 27 is the final release with Rosetta support.",
        ]
        articles = [self.article(
            "Developers can stop supporting Intel Macs, says Apple", summary, "AppleInsider", facts,
        ), self.article(
            "苹果允许 Mac App Store 应用移除英特尔 Mac 支持",
            "苹果邮件通知开发者，要求 macOS 13 或更新版本的通用应用可以移除英特尔 Mac 支持。",
            "cnBeta",
        )]
        self.assert_groups(articles, [{0, 1}])
        self.assertEqual(articles[0].summary, summary)
        self.assertEqual(articles[0].key_facts, facts)
        self.assertEqual(
            {key for key in self.profile(articles[0]).event_keys if key.startswith("primary-claim:")},
            {"primary-claim:mac-developer-distribution:intel-support-removal"},
        )

    def test_intel_supporting_inflection_merges_distribution_policy(self):
        articles = [self.article(
            "Developers can stop supporting Intel Macs, says Apple",
            "Apple now allows developers to submit arm64-only apps to the Mac App Store.",
            "AppleInsider",
        ), self.article(
            "苹果允许Mac App Store应用停止支持英特尔处理器的Mac",
            "苹果允许开发者移除英特尔支持，提交仅支持 arm64 的应用。",
            "cnBeta",
        ), self.article(
            "彻底说再见！苹果允许开发者直接移除英特尔CPU支持",
            "苹果允许 Mac App Store 开发者提交仅支持 arm64 的应用。",
            "快科技",
        )]
        self.assert_groups(articles, [{0, 1, 2}])
        for a in articles:
            self.assertNotIn("primary-claim-predicate:app-enforcement-removal", self.profile(a).separation_keys)

    def test_official_follow_change_separate_from_ceo_account_launch(self):
        articles = [self.article(
            "苹果新任 CEO 约翰·特努斯成 Apple 官方 X 账号唯一关注",
            "苹果官方 X 账号取消关注前任 CEO，只关注新任 CEO。",
            "IT之家",
        ), self.article(
            "苹果官方社媒账号已取关库克：新CEO特努斯成苹果唯一关注",
            "苹果官方 X 账号更改关注列表，目前只关注新 CEO。",
            "快科技",
        ), self.article(
            "开微博、喊“你好”、预告“惊艳发布” 苹果新CEO开启中国首秀",
            "苹果新任首席执行官开通微博账号，发布个人首条动态。",
            "cnBeta",
        )]
        self.assert_groups(articles, [{0, 1}, {2}])


if __name__ == "__main__":
    unittest.main()
