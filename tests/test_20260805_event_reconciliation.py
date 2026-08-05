import importlib.util
import itertools
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260805_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = facts or []
    kind = module.detect_event_kind(title, summary, facts)
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 5, tzinfo=timezone.utc),
        published_raw="2026-08-05T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=kind,
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


def partitions(events):
    return {
        frozenset(article.title for article in event.articles)
        for event in events
    }


class AugustFifthEventReconciliationTests(unittest.TestCase):
    def test_apple_india_annual_sales_reports_merge_across_wording_and_kind(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple's Annual India Sales Surpass $10 Billion for First Time",
                "Apple recorded more than $10 billion in annual India sales, led by iPhone demand.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple hits a record $10B in annual retail revenue in India",
                "Apple annual revenue in India passed $10 billion for the first time.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果印度年销售额首次突破 100 亿美元，每四部 iPhone 就有一部印度造",
                "苹果在印度的年度销售额首次超过 100 亿美元，iPhone 贡献大部分收入。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "AppleInsider", "IT之家"})

    def test_title_region_controls_annual_sales_identity_over_background_markets(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple's Annual India Sales Surpass $10 Billion for First Time",
                "Apple annual sales in India passed $10 billion for the first time.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple hits a record $10B in annual retail revenue in India",
                "Apple crossed $10 billion in India while the report also compared China, Japan, and United States demand.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果印度年销售额首次突破 100 亿美元，每四部 iPhone 就有一部印度造",
                "报道也回顾了苹果在中国、日本和美国市场的销售背景。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(len(events[0].articles), 3)

    def test_multi_product_roundup_stays_weak_but_same_price_forecast_sources_merge(self):
        module = load_module()
        price_reports = [
            article_for(
                module,
                "These Apple products are likely getting more expensive next month",
                "Prices for iPhone, Apple Watch, and AirPods are expected to rise at Apple's September event.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果 9 月新品全线涨价：手机、手表、耳机都将上调",
                "分析称 iPhone、Apple Watch 和 AirPods 的新品价格预计会在 9 月发布会提高。",
                "快科技",
            ),
        ]
        roundup = article_for(
            module,
            "苹果 9 月科技春晚新品汇总：5 大新品齐发",
            "文章盘点 iPhone、Apple Watch、AirPods 和其他此前传闻，没有一项新的独立报道。",
            "快科技",
        )

        events = module.cluster_articles([*price_reports, roundup])

        price_event = next(event for event in events if price_reports[0] in event.articles)
        roundup_event = next(event for event in events if roundup in event.articles)
        self.assertEqual(
            {article.title for article in price_event.articles},
            {article.title for article in price_reports},
        )
        self.assertEqual(price_event.relevance_tier, "strong")
        self.assertEqual(roundup_event.relevance_tier, "weak")
        self.assertNotIn(roundup, price_event.articles)

    def test_same_apple_security_actions_merge_without_exact_facets(self):
        module = load_module()
        bug_bounty = [
            article_for(
                module,
                "AI slop security reports are clogging up Apple's bug bounty program",
                "AI is flooding Apple's bug bounty system with flawed iOS and macOS security reports.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple Limits Bug Bounty Submissions After Flood of AI Slop",
                "Apple limited the number of vulnerabilities security researchers can submit to its bug bounty program because of an uptick in reports about fake bugs hallucinated by AI, according to The Financial Times.",
                "MacRumors",
            ),
        ]
        webkit = [
            article_for(
                module,
                "WebKit leaks in iOS and macOS expose user data despite proxy use",
                "Apple requires all browsers to use WebKit on iPhone, and three request paths can hand information around a proxy or iCloud Private Relay.",
                "AppleInsider",
            ),
            article_for(
                module,
                "基于苹果 WebKit 的浏览器被披露安全风险，恐泄露 iOS 和 macOS 用户网络信息",
                "网络安全博客披露 iOS 和 macOS 的 WebKit 存在 DNS 预取、通行密钥验证与 WebTransport 三个漏洞，可泄露用户网络信息。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles([*bug_bounty, *webkit])

        self.assertEqual(
            partitions(events),
            {frozenset(article.title for article in bug_bounty), frozenset(article.title for article in webkit)},
        )
        self.assertTrue(all(event.merge_warnings == [] for event in events))

    def test_same_airpods_firmware_wave_merges_despite_localized_beta_wording(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Releases New AirPods Beta Firmware With iOS 27 Features",
                "Apple released AirPods beta firmware 9A5336b for supported models.",
                "MacRumors",
            ),
            article_for(
                module,
                "AirPods Pro 3 just got new firmware release in beta, more models too",
                "The same AirPods beta firmware is available for AirPods Pro, AirPods 4, and AirPods Max.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果推送 AirPods 新测试版固件 9A5336b，支持 iOS 27 新功能",
                "苹果今日推送 AirPods Pro 2、Pro 3、AirPods 4 及 Max 2 的第四个测试版固件，版本号 9A5336b，并支持 iOS 27 新功能。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, partitions(events))

    def test_same_event_staff_support_action_merges_without_absorbing_product_roundups(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Starts Preparing for September iPhone Event",
                "Apple opened an internal lottery for retail staff to support guest check-in and security at its September event.",
                "MacRumors",
            ),
            article_for(
                module,
                "Staff lottery reveals Apple's first-half September event plans",
                "Apple is opening a lottery for U.S. retail employees to work at the September event.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果启动 9 月发布会筹备，面向零售员工开启现场支援岗位抽签",
                "苹果面向美国线下门店员工开启活动支援岗位抽签，入选人员负责媒体签到、现场引导和秩序维护。",
                "快科技",
            ),
            article_for(
                module,
                "消息称苹果在美国向零售店员工开放抽签，招募 9 月发布会现场秩序维护人员",
                "苹果近日面向美国零售店员工开放内部抽签，招募员工参与 9 月发布会现场支持工作。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, partitions(events))

    def test_event_countdown_preview_does_not_join_concrete_event_preparation(self):
        module = load_module()
        preparation = article_for(
            module,
            "Apple Starts Preparing for September iPhone Event",
            "Apple opened a staff lottery for retail employees to support its September media event.",
            "MacRumors",
        )
        preview = article_for(
            module,
            "苹果 9 月发布会倒计时：iPhone 18 Pro 等新品前瞻",
            "文章汇总此前关于 iPhone、Apple Watch 和 AirPods 的产品传闻，并以零售员工现场支援抽签作为发布会日期背景。",
            "快科技",
        )

        events = module.cluster_articles([preparation, preview])

        self.assertEqual(len(events), 2, partitions(events))
        preview_event = next(event for event in events if preview in event.articles)
        self.assertEqual(preview_event.relevance_tier, "weak")

    def test_same_attributed_iphone_display_report_merges_across_model_wording(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Next year's iPhone Pro models will have larger screen sizes, per leak",
                "A Chinese leaker says Apple is testing 6.4-inch and 7-inch displays for next year's anniversary iPhone Pro models.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Bigger Displays Rumored for Next Year's iPhone Models",
                "Apple is prototyping 6.4-inch and 7-inch displays for the 20th anniversary iPhone, according to the same Chinese leaker.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple plans massive 6.4-inch, 7-inch screens for the iPhone 20",
                "The iPhone 20 Pro line will use the same newly leaked 6.4-inch and 7-inch display sizes.",
                "AppleInsider",
            ),
            article_for(
                module,
                "消息称苹果 iPhone 20 周年或迎设计革新：四曲面屏与更大尺寸",
                "同一爆料称苹果正测试 6.4 英寸和 7.0 英寸屏幕，用于二十周年 iPhone Pro 系列。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, partitions(events))

    def test_followup_allegation_does_not_cross_assign_initial_delisting_sources(self):
        module = load_module()
        initial = [
            article_for(
                module,
                "Telegram Briefly Removed From App Store",
                "Apple briefly removed Telegram over prohibited content and restored it after cleanup.",
                "MacRumors",
            ),
            article_for(
                module,
                "Telegram 在苹果 App Store 短暂下架后恢复",
                "Telegram 因违规内容短暂下架，完成清理后恢复。",
                "cnBeta",
            ),
        ]
        allegation = [
            article_for(
                module,
                "Telegram CEO says extortionist planted illegal content to trigger App Store removal",
                "Pavel Durov alleged an extortionist planted content to weaponize Apple's removal process.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Telegram CEO 杜罗夫称勒索分子设局操纵苹果下架应用",
                "杜罗夫随后指控勒索者利用恶意举报诱使苹果下架 Telegram。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles([*initial, *allegation])

        self.assertEqual(partitions(events), {frozenset(a.title for a in initial), frozenset(a.title for a in allegation)})

    def test_unrelated_platform_feature_and_third_party_update_never_bridge(self):
        module = load_module()
        facetime = article_for(
            module,
            "iOS 27 gives FaceTime a new Dual Capture feature",
            "Apple added simultaneous front and rear camera video to FaceTime in iOS 27.",
            "9to5Mac",
        )
        signal = article_for(
            module,
            "Signal's latest iOS update expands multi-device support for iPhone users",
            "Signal updated its own iPhone app with support for linked devices.",
            "9to5Mac",
        )

        events = module.cluster_articles([facetime, signal])

        self.assertEqual(len(events), 2, partitions(events))
        self.assertEqual(signal.relevance_tier, "weak")

    def test_competitor_benchmark_and_apple_price_forecast_never_share_an_event(self):
        module = load_module()
        comparison = article_for(
            module,
            "Framework laptop with LPCAMM2 memory benchmarks slower than M5 MacBook Pro",
            "The third-party Framework notebook is compared with an Apple MacBook Pro benchmark.",
            "cnBeta",
        )
        forecast = article_for(
            module,
            "Apple products may face broad price increases at the September launch",
            "A new report forecasts higher prices for iPhone, Apple Watch, and AirPods next month.",
            "快科技",
        )

        events = module.cluster_articles([comparison, forecast])

        self.assertEqual(len(events), 2, partitions(events))
        self.assertEqual(comparison.relevance_tier, "weak")

    def test_third_party_accessory_and_platform_integration_are_deferred(self):
        module = load_module()
        cases = [
            (
                "GAMEBABY's translucent case turns your iPhone into a handheld console",
                "A third-party accessory adds physical game buttons to an iPhone case.",
            ),
            (
                "Savvy Navvy brings its CarPlay app to MasterCraft boats",
                "A third-party navigation app is adding its existing CarPlay interface to boats.",
            ),
            (
                "A jailbreak tool runs macOS virtual machines on iPad",
                "An independent developer released an unsupported virtualization tool for jailbroken iPads.",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(tier, "weak", reason)

    def test_reconciliation_is_independent_of_article_input_order(self):
        module = load_module()
        articles = [
            article_for(module, "Apple annual India sales pass $10 billion", "Apple annual sales in India passed $10 billion.", "MacRumors"),
            article_for(module, "苹果印度年销售额突破 100 亿美元", "苹果在印度年度销售额首次突破 100 亿美元。", "IT之家"),
            article_for(module, "Apple limits bug bounty submissions after AI report flood", "Apple added quotas to its bug bounty submission program.", "MacRumors"),
            article_for(module, "苹果限制漏洞赏金计划同时提交的报告数量", "苹果为漏洞赏金提交设置配额和冷却期。", "IT之家"),
            article_for(module, "iOS 27 adds Dual Capture to FaceTime", "Apple added Dual Capture to FaceTime.", "9to5Mac"),
            article_for(module, "Signal's iOS update expands linked devices", "Signal updated its third-party iPhone app.", "9to5Mac"),
        ]
        orders = [
            articles,
            list(reversed(articles)),
            articles[2:] + articles[:2],
            articles[::2] + articles[1::2],
        ]

        expected = partitions(module.cluster_articles(orders[0]))
        for order in orders[1:]:
            self.assertEqual(partitions(module.cluster_articles(order)), expected)

    def test_editorial_roundups_do_not_bridge_event_operations_or_product_reports(self):
        module = load_module()
        direct = [
            article_for(
                module,
                "Apple Starts Preparing for September iPhone Event",
                "Apple is getting ready for its September iPhone event and has begun internal preparations.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果面向零售员工开放 9 月发布会现场支援岗位抽签",
                "苹果招募零售员工参与媒体签到、引导和现场秩序维护。",
                "IT之家",
            ),
        ]
        roundups = [
            article_for(
                module,
                "Everything Apple Is Expected to Announce in September",
                "The article recaps previously reported iPhone, Watch, and AirPods rumors.",
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro will have three upgrades that have been rumored for years",
                "The article compiles three longstanding rumors without a new report.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果 2027 开年新机：iPhone 18 又是等等党的胜利",
                "本文结合供应链、分析师和行业爆料人的多方信息，总结 iPhone 18 的核心亮点。",
                "快科技",
            ),
        ]

        events = module.cluster_articles([*direct, *roundups])

        self.assertIn(frozenset(article.title for article in direct), partitions(events))
        for roundup in roundups:
            event = next(event for event in events if roundup in event.articles)
            self.assertEqual(event.relevance_tier, "weak")
            self.assertNotIn(direct[0], event.articles)

    def test_legal_case_actions_merge_within_stage_but_not_across_stages(self):
        module = load_module()
        rebuttal = [
            article_for(
                module,
                "OpenAI Posts Public Rebuttal to Apple's Trade Secrets Lawsuit",
                "OpenAI published a response disputing Apple's trade-secret allegations.",
                "MacRumors",
            ),
            article_for(
                module,
                "OpenAI 回应苹果商业秘密诉讼：公司否认相关指控",
                "OpenAI 发布公开回应，反驳苹果在商业秘密案件中的说法。",
                "IT之家",
            ),
        ]
        injunction = [
            article_for(
                module,
                "Apple moves for preliminary injunction in OpenAI trade secrets lawsuit",
                "Apple asked the court for a preliminary injunction against OpenAI.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果申请临时禁令，阻止 OpenAI 使用其商业秘密",
                "苹果向法院申请临时禁令并要求加速取证。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles([*rebuttal, *injunction])

        self.assertEqual(
            partitions(events),
            {frozenset(a.title for a in rebuttal), frozenset(a.title for a in injunction)},
        )

    def test_app_store_removal_subject_survives_localized_title_and_site_suffix(self):
        module = load_module()
        initial = [
            article_for(
                module,
                "Telegram Briefly Removed From App Store",
                "Apple briefly removed Telegram and restored it after prohibited content was removed.",
                "MacRumors",
            ),
            article_for(
                module,
                "因涉及 CSAM 内容 Telegram 遭苹果 App Store 短暂下架后恢复 - cnBeta.COM",
                "苹果临时下架 Telegram，清理违规内容后恢复。",
                "cnBeta",
            ),
        ]
        followup = [
            article_for(
                module,
                "Telegram CEO says extortionist planted content to trigger App Store removal",
                "Telegram alleged an extortionist planted content to manipulate Apple's review process.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Telegram 因恶意植入内容遭短暂下架，CEO 称规则被武器化 - Apple - cnBeta.COM",
                "Telegram CEO 指控勒索者植入内容，诱使苹果下架应用。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles([*initial, *followup])

        self.assertEqual(
            partitions(events),
            {frozenset(a.title for a in initial), frozenset(a.title for a in followup)},
        )

    def test_subject_owned_third_party_accessory_is_deferred(self):
        module = load_module()
        article = article_for(
            module,
            "GAMEBABY's translucent case turns your iPhone into a GameBoy",
            "The case adds physical game controls but Apple made no platform or hardware change.",
            "9to5Mac",
        )

        event = module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak")

    def test_appleish_facet_does_not_protect_an_explicit_competitor_benchmark(self):
        module = load_module()
        article = article_for(
            module,
            "Framework 笔记本引入 LPCAMM2 内存，性能表现暂不敌 MacBook Pro",
            "Framework 的模块化内存跑分低于 M5 MacBook Pro，苹果没有发布或改变任何产品。",
            "cnBeta",
        )

        event = module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak")

    def test_direct_legal_response_rejoins_case_even_if_preclassified_weak(self):
        module = load_module()
        strong = article_for(
            module,
            "OpenAI Posts Public Rebuttal to Apple's Trade Secrets Lawsuit",
            "OpenAI published a response disputing Apple's trade-secret allegations.",
            "MacRumors",
        )
        localized = article_for(
            module,
            "OpenAI 回应商业纠纷案：苹果对此案处理有误",
            "OpenAI 发布公开回应，反驳苹果在商业秘密案件中的说法。",
            "IT之家",
        )
        localized.relevance_tier = "weak"
        localized.relevance_reason = "preclassified weak"

        events = module.cluster_articles([strong, localized])

        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_sparse_and_detailed_display_reports_merge_by_generation_and_action(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Next year's iPhone Pro models will have larger screen sizes, per leak",
                "The 20th anniversary iPhone Pro models could bring larger screen sizes.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Bigger Displays Rumored for Next Year's iPhone Models",
                "Apple is prototyping 6.4-inch and 7-inch displays for the 20th anniversary iPhone.",
                "MacRumors",
            ),
            article_for(
                module,
                "消息称苹果二十周年 iPhone Pro 将采用更大尺寸屏幕",
                "同一爆料称苹果测试 6.4 英寸和 7.0 英寸屏幕。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, partitions(events))


if __name__ == "__main__":
    unittest.main()
