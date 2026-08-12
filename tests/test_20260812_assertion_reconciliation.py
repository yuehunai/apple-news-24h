import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260812_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 12, tzinfo=timezone.utc),
        published_raw="2026-08-12T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(f"{title} {summary}"),
    )


def partitions(events):
    return {frozenset(article.title for article in event.articles) for event in events}


class AssertionReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_non_apple_product_action_with_apple_platform_recipient_is_deferred(self):
        samples = (
            (
                "Zoom flaw let an attacker take over your device, including iPhone and Mac",
                "The vulnerability is in Zoom Workplace; iPhone and Mac are among the affected clients.",
            ),
            (
                "Grok Bot Brings Always-On AI Agents to macOS and iOS",
                "The third-party Grok Bot app added an always-on agent mode for Apple platforms.",
            ),
        )
        for title, summary in samples:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary, "9to5Mac")
                profile = self.module.article_reconciliation_profile(article)
                self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
                self.assertTrue(profile.defer_reason or profile.hard_boundary)

    def test_concrete_subject_action_conflicts_split_even_with_shared_broad_facet(self):
        glass = article_for(
            self.module,
            "Apple's 20th-anniversary all-glass iPhone redesign remains on track",
            "The 2027 anniversary iPhone retains its all-glass redesign after a cancellation report.",
        )
        naming = article_for(
            self.module,
            "Everyone at Apple calls the foldable phone iPhone Ultra",
            "The foldable iPhone is internally named iPhone Ultra.",
            "AppleInsider",
        )
        events = self.module.cluster_articles([glass, naming])
        self.assertEqual(len(events), 2, partitions(events))

    def test_distinct_apple_tv_titles_and_actions_do_not_share_an_event(self):
        trailer = article_for(
            self.module,
            "Apple TV unveils new crime thriller that kicks off big fall lineup",
            "Apple TV released the trailer for Last Seen, which premieres October 2.",
        )
        premiere = article_for(
            self.module,
            "Women in Blue's second season premieres on Apple TV",
            "Apple TV premiered season two of Women in Blue today.",
        )
        events = self.module.cluster_articles([trailer, premiere])
        self.assertEqual(len(events), 2, partitions(events))

    def test_real_apple_tv_possessive_season_title_does_not_bridge_to_another_work(self):
        trailer = article_for(
            self.module,
            "Apple TV unveils new crime thriller that kicks off big fall lineup - 9to5Mac",
            (
                "Today Apple TV released the trailer for Last Seen, a new thriller series "
                "that will kick off the streamer's fall lineup next month."
            ),
        )
        premiere = article_for(
            self.module,
            "Women in Blue’s second season premieres on Apple TV - 9to5Mac",
            (
                "Apple TV subscribers can now stream the first episode of the new season "
                "of Women in Blue (Las Azules)."
            ),
        )
        events = self.module.cluster_articles([trailer, premiere])
        self.assertEqual(len(events), 2, partitions(events))
        profiles = [self.module.article_reconciliation_profile(article) for article in (trailer, premiere)]
        content_titles = [
            {key for key in profile.separation_keys if key.startswith("content-title:")}
            for profile in profiles
        ]
        self.assertEqual(content_titles, [{"content-title:last-seen"}, {"content-title:women-in-blue"}])

    def test_airpods_firmware_never_bridges_into_os_public_beta_train(self):
        os_beta = article_for(
            self.module,
            "Third iOS 27 and iPadOS 27 Public Betas Now Available",
            "Apple released public beta 3 of iOS 27 and iPadOS 27.",
            "MacRumors",
        )
        firmware = article_for(
            self.module,
            "Apple Releases New iOS 27 AirPods Firmware for Public Beta Testers",
            "Apple released public beta firmware 9A5336b for supported AirPods models.",
            "MacRumors",
        )
        events = self.module.cluster_articles([os_beta, firmware])
        self.assertEqual(len(events), 2, partitions(events))

    def test_private_relay_class_action_merges_across_language(self):
        reports = [
            article_for(
                self.module,
                "Apple faces class action lawsuit for fraud over iCloud Private Relay flaw",
                "The complaint alleges iCloud Private Relay exposed users' real IP addresses.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "因 iCloud 专用代理存在漏洞，苹果面临欺诈集体诉讼",
                "诉讼称 iCloud Private Relay 会泄露用户真实 IP 地址。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_boe_ipad_air_oled_supplier_reports_merge_across_language(self):
        reports = [
            article_for(
                self.module,
                "BOE seeks to supply OLED panels for Apple's 2027 iPad Air",
                "BOE will submit OLED samples as it seeks qualification as an iPad Air display supplier.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "京东方或将参与 2027 年新款 iPad Air OLED 面板供应",
                "京东方正争取成为苹果 iPad Air OLED 面板供应商并提交样品。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_regional_feature_code_evidence_merges_but_not_with_beta_roundup(self):
        clue_reports = [
            article_for(
                self.module,
                "iOS 27 Beta 5 reveals China Apple Intelligence code references",
                "New code references indicate Apple Intelligence readiness for iPhones sold in China.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "iOS 27 Beta 5 发现国行 Apple Intelligence 代码踪迹",
                "系统代码出现国行 Apple Intelligence 备案与设备支持线索。",
                "IT之家",
            ),
        ]
        roundup = article_for(
            self.module,
            "iOS 27 Beta 5: 20 changes, new icons, China AI clues and more",
            "This roundup lists 20 unrelated changes found across iOS 27 beta 5.",
            "AppleInsider",
        )
        events = self.module.cluster_articles([*clue_reports, roundup])
        self.assertIn(frozenset(article.title for article in clue_reports), partitions(events))
        self.assertIn(frozenset({roundup.title}), partitions(events))

    def test_specific_ios_feature_background_does_not_bridge_into_code_events(self):
        regional_code = article_for(
            self.module,
            "iOS 27 Beta 5 reveals China Apple Intelligence code references",
            "New code references indicate Apple Intelligence readiness for China.",
            "IT之家",
        )
        model_codes = article_for(
            self.module,
            "Latest iOS 27 Beta References Six Unreleased iPhone Models",
            "Hidden code in iOS 27 beta 5 reveals six unreleased iPhone models.",
            "MacRumors",
        )
        liquid_glass = article_for(
            self.module,
            "iOS 27 beta 5 lets you make Liquid Glass more transparent than ever",
            (
                "Apple changed the Liquid Glass transparency slider in iOS 27 beta 5. "
                "Other reports found China Apple Intelligence code and six unreleased iPhone identifiers."
            ),
            "9to5Mac",
        )
        events = self.module.cluster_articles([regional_code, model_codes, liquid_glass])
        self.assertEqual(len(events), 3, partitions(events))

    def test_unreleased_iphone_code_list_merges_across_product_aliases_and_languages(self):
        reports = [
            article_for(
                self.module,
                "Latest iOS 27 Beta References Six Unreleased iPhone Models",
                "Hidden code in iOS 27 beta 5 reveals six unreleased iPhone models.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "含 iPhone Ultra、iPhone 18 Pro 等，六款未发布的苹果 iPhone 新机首度现身 iOS 27 系统代码",
                "苹果在 iOS 27 Beta 5 系统代码中首次曝光六款新 iPhone 的代号。",
                "IT之家",
            ),
            article_for(
                self.module,
                "iOS 27代码泄露苹果6款未发新机：iPhone Ultra、iPhone 18 Pro/e等",
                "系统文件写入 6 款未发布 iPhone 的内部代号。",
                "快科技",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_numbered_os_feature_compilation_is_deferred_without_standalone_action(self):
        article = article_for(
            self.module,
            "30 New Things Your iPhone Can Do in iOS 27",
            "This guide compiles features coming in iOS 27 without a new standalone Apple action.",
            "MacRumors",
        )
        profile = self.module.article_reconciliation_profile(article)
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        self.assertEqual(profile.identity.content_form, "roundup")
        self.assertTrue(profile.defer_reason)

    def test_causative_named_os_feature_merges_with_translated_report(self):
        reports = [
            article_for(
                self.module,
                "iOS 27 beta 5 lets you make Liquid Glass more transparent than ever",
                "Apple changed the Liquid Glass transparency slider in iOS 27 beta 5.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "iOS 27 Beta 5 调整液态玻璃滑块，苹果提升最高透明度档位效果",
                "报道称苹果调整液态玻璃（Liquid Glass）滑块的最高透明度。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_cross_platform_public_beta_train_merges_while_firmware_stays_separate(self):
        releases = [
            article_for(
                self.module,
                "Third iOS 27 and iPadOS 27 Public Betas Now Available",
                "Apple released public beta 3 for iOS 27 and iPadOS 27.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple rolls out macOS 27 Golden Gate public beta 3",
                "Apple released public beta 3 for macOS 27.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果发布 watchOS 27、tvOS 27 第三个公测版",
                "苹果发布同一轮 watchOS 27 与 tvOS 27 public beta 3。",
                "IT之家",
            ),
        ]
        firmware = article_for(
            self.module,
            "Apple Releases New iOS 27 AirPods Firmware for Public Beta Testers",
            "Apple released public beta firmware 9A5336b for AirPods.",
            "MacRumors",
        )
        events = self.module.cluster_articles([*releases, firmware])
        self.assertIn(frozenset(article.title for article in releases), partitions(events))
        self.assertIn(frozenset({firmware.title}), partitions(events))

    def test_service_regional_launch_and_executive_departure_stay_separate(self):
        launch = article_for(
            self.module,
            "Apple Pay to Launch in India by October",
            "Apple Pay will launch in the Indian market by October.",
            "MacRumors",
        )
        departures = [
            article_for(
                self.module,
                "Apple Pay Chief Jennifer Bailey Retiring in October",
                "Jennifer Bailey will retire from Apple in October.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple Pay chief Jennifer Bailey retiring in October",
                "Apple's Apple Pay and Wallet vice president Jennifer Bailey is retiring.",
                "9to5Mac",
            ),
        ]
        events = self.module.cluster_articles([launch, *departures])
        self.assertIn(frozenset({launch.title}), partitions(events))
        self.assertIn(frozenset(article.title for article in departures), partitions(events))

    def test_supplier_capacity_negotiation_and_device_cost_are_distinct_assertions(self):
        reports = [
            article_for(
                self.module,
                "China is less likely to solve Apple's memory crunch",
                "Political restrictions and limited supplier capacity constrain Apple's memory sourcing.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple's low-price memory negotiation is rejected",
                "A memory supplier rejected Apple's proposed price during procurement talks.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "iPhone 18 Pro component cost rises 38%",
                "A bill-of-materials forecast says iPhone 18 Pro component costs rise 38%.",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 3, partitions(events))

    def test_supplier_primary_action_ignores_cross_action_background(self):
        reports = [
            article_for(
                self.module,
                "China is even less likely to solve Apple's memory crunch",
                (
                    "Chinese suppliers have no spare capacity for Apple's proposed RAM sourcing. "
                    "Apple has separately negotiated lower prices, while analysts forecast higher "
                    "iPhone component costs."
                ),
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple's low-price memory offer is rejected by its supplier",
                (
                    "A supplier rejected Apple's proposed price during procurement talks. "
                    "The wider shortage has constrained capacity and raised projected iPhone BOM costs."
                ),
                "AppleInsider",
            ),
            article_for(
                self.module,
                "iPhone 18 Pro component cost rises 38%",
                (
                    "A bill-of-materials forecast says iPhone 18 Pro component costs rise 38%. "
                    "The report also discusses constrained capacity and Apple's supplier negotiations."
                ),
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 3, partitions(events))

    def test_program_extension_and_ios_feature_merge_across_language(self):
        promotion = [
            article_for(
                self.module,
                "Apple Extends 2026 Back to School Promotion Until September 24",
                "Apple extended its Back to School offer to September 24.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 2026 返校季活动延长至 9 月 24 日",
                "苹果将返校季教育优惠延长至 9 月 24 日。",
                "IT之家",
            ),
        ]
        birthdays = [
            article_for(
                self.module,
                "iOS 27 celebrates your friends' birthdays with fireworks",
                "The Phone app adds a birthday reminder during calls and shows fireworks.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "iOS 27 或引入通话生日提醒功能，屏幕播放烟花动画",
                "电话应用新增生日提醒，会在通话时播放烟花动画。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles([*promotion, *birthdays])
        self.assertIn(frozenset(article.title for article in promotion), partitions(events))
        self.assertIn(frozenset(article.title for article in birthdays), partitions(events))


if __name__ == "__main__":
    unittest.main()
