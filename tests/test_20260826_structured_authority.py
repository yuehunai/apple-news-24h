import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "apple_news_20260826_structured_authority_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(
    module,
    title,
    summary,
    source,
    *,
    facts=None,
    tier=None,
    reason=None,
    category=None,
    event_kind=None,
):
    facts = list(facts or [summary])
    observed_tier, observed_reason = module.classify_relevance_tier(
        title,
        summary,
        facts,
        source,
    )
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=category or module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 25, tzinfo=timezone.utc),
        published_raw="2026-08-25T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=event_kind or module.detect_event_kind(title, summary, facts),
        relevance_tier=tier or observed_tier,
        relevance_reason=reason if reason is not None else observed_reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class StructuredAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_title_led_first_party_actions_override_legacy_weak_labels(self):
        samples = [
            (
                "Apple Reveals M6 as First-Ever 2nm Chip",
                "Apple announced M6 as its first 2nm chip with a Dual 16-core Neural Engine.",
                "hardware_products",
            ),
            (
                "69 元，苹果官网上线新款抛光布",
                "苹果官网上架新款抛光布，售价 69 元。",
                "hardware_products",
            ),
            (
                "苹果全新 Mac mini 首次支持 Genlock，通过 USB-C 实现显示器、摄像头精准同步",
                "苹果发布的新款 Mac mini 首次增加 Genlock 能力。",
                "hardware_products",
            ),
            (
                "Apple's 40W Dynamic Power Adapter Expands to More Countries",
                "Apple expanded its 40W Dynamic Power Adapter to Vietnam and European countries.",
                "hardware_products",
            ),
            (
                "Apple Maps Ads Are Here, and There's No Way to Turn Them Off",
                "Apple Maps ads are now live in the United States and Canada.",
                "software_systems",
            ),
            (
                "古尔曼：苹果智能家居显示屏仍有望于今年推出",
                "苹果仍计划今年推出首款带屏智能家居中枢。",
                "hardware_products",
            ),
        ]

        for title, summary, expected_category in samples:
            with self.subTest(title=title):
                article = article_for(
                    self.module,
                    title,
                    summary,
                    "MacRumors",
                    tier="weak",
                    reason="legacy body-derived weak classification",
                    category="software_systems",
                    event_kind="third_party_ecosystem",
                )

                event = self.module.cluster_articles([article])[0]

                self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
                self.assertEqual(event.category, expected_category)

    def test_editorial_forms_override_legacy_strong_labels(self):
        samples = [
            (
                "iPhone 扫一扫冷知识汇总：这几个隐藏玩法赶快用起来",
                "文章介绍如何使用 iPhone 扫码、识别文字和查询植物。",
            ),
            (
                "Apple just revealed two ways iPhone 18 Pro could get big upgrades",
                "The article infers possible A20 Pro gains from the newly announced M6 chip.",
            ),
        ]

        for title, summary in samples:
            with self.subTest(title=title):
                article = article_for(
                    self.module,
                    title,
                    summary,
                    "9to5Mac",
                    tier="strong",
                    reason="legacy title Apple match",
                    category="hardware_products",
                    event_kind="hardware_market",
                )

                event = self.module.cluster_articles([article])[0]

                self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_roundup_and_legacy_seed_cannot_bridge_distinct_accessory_actions(self):
        articles = [
            article_for(
                self.module,
                "Apple Quietly Refreshes Magic Keyboards",
                "Apple refreshed four Magic Keyboard models with symbol-only labels on several keys.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果悄然更新妙控键盘，多个按键改用符号标识",
                "苹果更新四款妙控键盘，将多个文字按键改为图形符号。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Apple launches a lower-priced Polishing Cloth",
                "Apple launched a new Polishing Cloth for $9, down from $19.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "69 元，苹果官网上线新款抛光布",
                "苹果官网上架新款抛光布，价格从 145 元降至 69 元。",
                "IT之家",
            ),
            article_for(
                self.module,
                "New Macs and More: Here's Everything Apple Announced Today",
                "Apple announced new chips, Macs, keyboards, and a Polishing Cloth.",
                "MacRumors",
                tier="strong",
                reason="legacy roundup promoted by Apple terms",
            ),
        ]

        events = self.module.cluster_articles(articles)
        title_sets = [{item.title for item in event.articles} for event in events]

        self.assertFalse(
            any(
                any("Keyboard" in title or "键盘" in title for title in titles)
                and any("Cloth" in title or "抛光布" in title for title in titles)
                for titles in title_sets
            ),
            title_sets,
        )
        self.assertTrue(
            any(sum("Keyboard" in title or "键盘" in title for title in titles) == 2 for titles in title_sets),
            title_sets,
        )
        self.assertTrue(
            any(sum("Cloth" in title or "抛光布" in title for title in titles) == 2 for titles in title_sets),
            title_sets,
        )
        roundup_event = next(
            event
            for event in events
            if any("Everything Apple Announced" in item.title for item in event.articles)
        )
        self.assertEqual(roundup_event.relevance_tier, "weak")

    def test_generic_multi_product_summary_cannot_pollute_a_precise_product_event(self):
        articles = [
            article_for(
                self.module,
                "Apple Debuts M5 Ultra as Most Powerful Chip Ever",
                "Apple announced the M5 Ultra for the new Mac Studio.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple Unveiled Four New Products Today",
                (
                    "Apple unveiled a new Mac mini, a new Mac Studio, a lower-priced "
                    "Polishing Cloth, and updated Magic Keyboards."
                ),
                "MacRumors",
                tier="strong",
                reason="legacy Apple title match",
            ),
        ]

        events = self.module.cluster_articles(articles)
        summary_event = next(
            event
            for event in events
            if any("Four New Products" in item.title for item in event.articles)
        )
        product_event = next(
            event
            for event in events
            if any("M5 Ultra" in item.title for item in event.articles)
        )

        self.assertIsNot(summary_event, product_event)
        self.assertEqual(summary_event.relevance_tier, "weak")

    def test_specific_official_multi_product_release_remains_direct_news(self):
        article = article_for(
            self.module,
            "Apple introduces M6 and M5 Ultra for a big leap in performance and AI compute",
            "Apple announced the M6 and M5 Ultra chips for its new Mac lineup.",
            "Apple Newsroom",
            tier="weak",
            reason="legacy multi-product uncertainty",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)

    def test_current_os_device_feature_matrix_is_not_downgraded_as_editorial_poll(self):
        article = article_for(
            self.module,
            "Which iPhones Support Every iOS 27 Feature?",
            (
                "Apple's iOS 27 compatibility matrix shows that iPhone 11 and later "
                "can install the update, while only three current models support every "
                "new on-device Siri feature."
            ),
            "MacRumors",
            tier="weak",
            reason="legacy editorial poll classification",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "software_systems")

    def test_current_home_hub_report_is_not_downgraded_by_background_products(self):
        article = article_for(
            self.module,
            "Apple Smart Home Display Still Coming This Year",
            (
                "Apple remains on track to launch its first smart home device with a "
                "screen before the end of the year, according to Bloomberg's Mark Gurman."
            ),
            "MacRumors",
            facts=[
                "Apple's smart home hub remains on track to launch before year end.",
                "Background reporting also discussed possible Apple TV and HomePod refreshes.",
            ],
            tier="weak",
            reason="legacy multi-product roundup classification",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_first_lead_subject_is_not_overridden_by_later_product_background(self):
        article = article_for(
            self.module,
            "Apple's first smart-home product remains on track for this year",
            "Apple's home hub remains on track to launch before the end of the year.",
            "MacRumors",
            facts=[
                "Apple's home hub remains on track to launch before year end.",
                "Later background mentions possible Apple TV, HomePod, and iPad integrations.",
            ],
            tier="weak",
            reason="legacy multi-product roundup classification",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_dual_chip_announcement_projects_facts_to_each_named_chip(self):
        facts = [
            "Apple announced the M6 and M5 Ultra as its next-generation chips.",
            "The M6 uses a 2nm process and a 12-core CPU.",
            "CPU: Up to 1.2x faster multithreaded performance than M5.",
            "GPU AI compute: Nearly 30% higher than M5.",
            "At the high end, Apple announced the M5 Ultra for Mac Studio.",
            "The M5 Ultra supports up to a 36-core CPU and 80-core GPU.",
            "Memory bandwidth: Up to 1.2TB/s.",
        ]

        variants = self.module.compound_article_variants(
            "Apple introduces M6 and M5 Ultra for a big leap in performance and AI compute",
            "Apple announced two distinct Apple silicon chips for different Mac products.",
            facts,
        )

        self.assertEqual(len(variants), 2, variants)
        by_title = {
            title: (summary, variant_facts)
            for title, summary, variant_facts in variants
        }
        m6_title = next(title for title in by_title if "M6" in title)
        ultra_title = next(title for title in by_title if "M5 Ultra" in title)
        m6_facts = " ".join(by_title[m6_title][1])
        ultra_facts = " ".join(by_title[ultra_title][1])

        self.assertIn("M6 uses a 2nm process", by_title[m6_title][0])
        self.assertNotIn("M5 Ultra", by_title[m6_title][0])
        self.assertIn("M5 Ultra for Mac Studio", by_title[ultra_title][0])
        self.assertNotIn("M6 and M5 Ultra", by_title[ultra_title][0])
        self.assertIn("CPU: Up to 1.2x", m6_facts)
        self.assertNotIn("1.2TB/s", m6_facts)
        self.assertIn("1.2TB/s", ultra_facts)
        self.assertNotIn("GPU AI compute: Nearly 30%", ultra_facts)

    def test_projected_chip_release_does_not_join_product_price_story_from_body_mention(self):
        projected_release = article_for(
            self.module,
            "Apple M6 chip release",
            "快科技8月26日消息，苹果推出新款 Mac mini 与 Mac Studio，最高分别搭载 2nm 芯片 M6 及 M5 Ultra 芯片，在性能和 AI 能力上实现跃升。",
            "快科技",
            facts=[
                "快科技8月26日消息，苹果推出新款 Mac mini 与 Mac Studio，最高分别搭载 2nm 芯片 M6 及 M5 Ultra 芯片。",
                "M6 是苹果首款采用 2nm 制程的芯片，所有计算模块均获得全面升级。",
            ],
        )
        price_story = article_for(
            self.module,
            "Mac mini性价比神机没了：苹果疯狂涨价 起步就是6999元",
            "苹果官网发布了搭载 M6 与 M5 Pro 芯片的 Mac mini，以及搭载 M5 Max 与 M5 Ultra 芯片的 Mac Studio 等新品。",
            "快科技",
            facts=[
                "售价方面，M6 款 Mac mini 起售价为 899 美元，国内定价 6999 元起。",
                "2nm 先进制程叠加内存芯片持续走高，上游元器件正在重塑消费电子产业链的成本结构。",
            ],
        )

        events = self.module.cluster_articles([projected_release, price_story])
        title_sets = [{item.title for item in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)

    def test_projected_chip_release_joins_chip_event_not_host_product_launch(self):
        projected_release = article_for(
            self.module,
            "Apple M6 chip release",
            "苹果推出新款 Mac mini 与 Mac Studio，分别搭载 M6 与 M5 Ultra。",
            "快科技",
            facts=[
                "苹果推出新款 Mac mini 与 Mac Studio，分别搭载 M6 与 M5 Ultra。",
                "M6 是苹果首款 2nm 芯片，采用 12 核 CPU。",
            ],
        )
        direct_chip_release = article_for(
            self.module,
            "Apple Reveals M6 as First-Ever 2nm Chip",
            "Apple announced M6 as its first 2nm chip with a 12-core CPU.",
            "MacRumors",
        )
        product_launch = article_for(
            self.module,
            "Apple Announces New Mac Mini With M6 and M5 Pro Chips and More",
            "Apple launched the new Mac mini with M6 and M5 Pro chips.",
            "MacRumors",
        )
        performance_bridge = article_for(
            self.module,
            "苹果M6版Mac mini性能与AI能力大幅跃升 最高可比M4快40% - Apple 苹果 - cnBeta.COM",
            "苹果 M6 版 Mac mini 在性能和 AI 能力上提升，最高可比 M4 快 40%。",
            "cnBeta",
            facts=[
                "M6 是苹果首款 2nm 芯片，搭载 12 核 CPU。",
                "新款 Mac mini 提供 M6 和 M5 Pro 两种处理器配置。",
            ],
        )

        events = self.module.cluster_articles(
            [projected_release, direct_chip_release, product_launch, performance_bridge]
        )
        title_sets = [{item.title for item in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)
        self.assertTrue(
            any(
                projected_release.title in titles
                and direct_chip_release.title in titles
                and product_launch.title not in titles
                and performance_bridge.title not in titles
                for titles in title_sets
            ),
            title_sets,
        )

    def test_product_release_with_two_chip_options_is_not_projected_as_chip_events(self):
        title = "Apple unveils a more powerful Mac mini featuring M6 and M5 Pro"
        facts = [
            "Apple announced the new Mac mini with M6 and M5 Pro configurations.",
            "The M6 model starts at $899.",
            "The M5 Pro model starts at $1,699.",
        ]

        variants = self.module.compound_article_variants(
            title,
            "Apple refreshed the Mac mini product line with two chip options.",
            facts,
        )

        self.assertEqual(variants, [(title, "Apple refreshed the Mac mini product line with two chip options.", facts)])

    def test_cross_language_external_display_capability_reports_merge(self):
        articles = [
            article_for(
                self.module,
                "New M6 Mac mini keeps the three-display limit but raises refresh rates",
                "Apple kept the new M6 and M5 Pro Mac mini at three external displays, but increased the maximum refresh rate, and gave M5 Pro support for connecting all three through one Thunderbolt port.",
                "AppleInsider",
                facts=[
                    "Apple kept the new M6 and M5 Pro Mac mini at three external displays, but increased the maximum refresh rate, and gave M5 Pro support for connecting all three through one Thunderbolt port.",
                    "The Mac mini models were introduced August 25 and will be available September 22. M6 replaces M4 in the standard model, while M5 Pro succeeds M4 Pro in the higher-performance configuration.",
                    "Both chips support one display at up to 8K at 60Hz, 5K at 120Hz, or 4K at 240Hz.",
                ],
            ),
            article_for(
                self.module,
                "苹果新款 Mac mini 可连接三台显示器，但不同处理器的多显示器最高分辨率有区别",
                "苹果已推出新款 Mac mini，升级 M6/M5 Pro 芯片，售价 6999 元起，将于 9 月 22 日正式上市，不同芯片版本均支持连接三台显示器，但最高分辨率和刷新率有区别。",
                "IT之家",
                facts=[
                    "IT之家 8 月 25 日消息，苹果现已推出新款 Mac mini，新品升级 M6/M5 Pro 芯片，售价 6999 元起，9 月 22 日上市。",
                    "据苹果官网所述，M6 Mac mini 可通过雷雳和 HDMI 端口连接三台显示器。",
                    "M5 Pro Mac mini 可通过雷雳和 HDMI 端口的任意组合最多连接三台显示器。",
                ],
            ),
            article_for(
                self.module,
                "苹果全新 Mac mini 首次支持 Genlock 专业同步",
                "新款 Mac mini 可通过 USB-C 同步显示器和摄像头。",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(articles)
        title_sets = [{item.title for item in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)
        self.assertTrue(
            any(
                len(titles) == 2
                and any("three-display" in title for title in titles)
                and any("三台显示器" in title for title in titles)
                for titles in title_sets
            ),
            title_sets,
        )

    def test_exact_capability_identity_survives_noisy_recall_seed_groups(self):
        launch = article_for(
            self.module,
            "Apple announces new Mac mini with M6 and M5 Pro chips - 9to5Mac",
            "Apple launched the new Mac mini with M6 and M5 Pro chips.",
            "9to5Mac",
        )
        supply = article_for(
            self.module,
            "Updated M5 Mac mini arrives in RAM and SSD constrained environment",
            "Apple launched the updated Mac mini while memory and storage supply remain constrained.",
            "AppleInsider",
        )
        price = article_for(
            self.module,
            "Mac mini性价比神机没了：苹果疯狂涨价 起步就是6999元",
            "苹果提高新款 Mac mini 的起售价。",
            "快科技",
        )
        chinese_launch = article_for(
            self.module,
            "苹果全新Mac mini发布：搭载M6、M5 Pro芯片，6999元起售 - Apple 苹果 - cnBeta.COM",
            "苹果发布搭载 M6 与 M5 Pro 的新款 Mac mini。",
            "cnBeta",
        )
        chinese_display = article_for(
            self.module,
            "苹果新款 Mac mini 可连接三台显示器，但不同处理器的多显示器最高分辨率有区别",
            "苹果已推出新款 Mac mini，升级 M6/M5 Pro 芯片，售价 6999 元起，将于 9 月 22 日正式上市，不同芯片版本均支持连接三台显示器，但最高分辨率和刷新率有区别。",
            "IT之家",
        )
        verge_launch = article_for(
            self.module,
            "Apple’s new Mac Mini has fresh M6 and M5 Pro chip offerings — and higher prices",
            "Apple launched the Mac mini with M6 and M5 Pro chips at higher prices.",
            "The Verge",
        )
        english_display = article_for(
            self.module,
            "New M6 Mac mini keeps the three-display limit but raises refresh rates",
            "Apple kept the new M6 and M5 Pro Mac mini at three external displays, but increased the maximum refresh rate, and gave M5 Pro support for connecting all three through one Thunderbolt port.",
            "AppleInsider",
        )
        silicon_launch = article_for(
            self.module,
            "首发2nm M6芯片！苹果全新Mac mini发布：6999元起",
            "苹果发布搭载 M6 的全新 Mac mini。",
            "快科技",
        )
        chip_specs = article_for(
            self.module,
            "苹果正式推出 M5 Ultra 芯片，最高 36 核 CPU/80 核 GPU，1.2 TB/s 统一内存带宽",
            "苹果发布 M5 Ultra，统一内存带宽达到 1.2 TB/s。",
            "IT之家",
        )
        articles = [
            launch,
            supply,
            price,
            chinese_launch,
            chinese_display,
            verge_launch,
            english_display,
            silicon_launch,
            chip_specs,
        ]
        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in articles
        }

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[
                [launch, supply, price, chinese_launch, chinese_display, verge_launch],
                [english_display, silicon_launch, chip_specs],
            ],
        )
        title_sets = [{item.title for item in group} for group in groups]

        self.assertTrue(
            any(
                english_display.title in titles
                and chinese_display.title in titles
                for titles in title_sets
            ),
            title_sets,
        )

    def test_exact_capability_reunites_after_price_and_launch_seed_cleanup(self):
        english_display = article_for(
            self.module,
            "New M6 Mac mini keeps the three-display limit but raises refresh rates",
            "Apple kept the new M6 and M5 Pro Mac mini at three external displays, but increased the maximum refresh rate.",
            "AppleInsider",
        )
        launch = article_for(
            self.module,
            "首发2nm M6芯片！苹果全新Mac mini发布：6999元起",
            "苹果发布搭载 M6 的全新 Mac mini。",
            "快科技",
        )
        price = article_for(
            self.module,
            "Mac mini性价比神机没了：苹果疯狂涨价 起步就是6999元",
            "苹果提高新款 Mac mini 的起售价。",
            "快科技",
        )
        price_followup = article_for(
            self.module,
            "苹果Mac mini M6发布：两年涨2500块 AI税反噬龙虾神机",
            "苹果新款 Mac mini 相比上一代涨价 2500 元。",
            "快科技",
        )
        chinese_display = article_for(
            self.module,
            "苹果新款 Mac mini 可连接三台显示器，但不同处理器的多显示器最高分辨率有区别",
            "苹果新款 Mac mini 的两种芯片配置均支持三台显示器。",
            "IT之家",
        )
        roundup = article_for(
            self.module,
            "Apple Unveiled Four New Products Today",
            "Apple unveiled a Mac mini, Mac Studio, and two new chips.",
            "MacRumors",
        )
        articles = [
            english_display,
            launch,
            price,
            price_followup,
            chinese_display,
            roundup,
        ]
        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in articles
        }

        from apple_news_core.event_reconciler import (
            _reunite_exact_relation_groups,
        )

        groups = _reunite_exact_relation_groups(
            [
                [english_display],
                [launch],
                [price, price_followup],
                [chinese_display],
                [roundup],
            ],
            profiles,
        )
        title_sets = [{item.title for item in group} for group in groups]

        self.assertTrue(
            any(
                english_display.title in titles
                and chinese_display.title in titles
                for titles in title_sets
            ),
            title_sets,
        )

    def test_inferred_os_release_date_stays_weak_but_official_date_stays_strong(self):
        inferred = [
            article_for(
                self.module,
                "macOS Golden Gate Release Date Potentially Revealed by Apple",
                (
                    "New Macs are slated to ship with macOS Golden Gate, which could "
                    "indirectly reveal the software release window."
                ),
                "MacRumors",
            ),
            article_for(
                self.module,
                "iOS 27 release date: Here's when the new iPhone update will launch",
                "Here is when to expect iOS 27 based on Apple's familiar release cadence.",
                "9to5Mac",
            ),
        ]
        official = article_for(
            self.module,
            "Apple Announces iOS 27 Will Be Released September 15",
            "Apple announced that iOS 27 will be available as a free update on September 15.",
            "Apple Newsroom",
        )

        inferred_events = self.module.cluster_articles(inferred)
        official_event = self.module.cluster_articles([official])[0]

        self.assertTrue(
            all(event.relevance_tier == "weak" for event in inferred_events),
            [(event.title, event.relevance_tier, event.relevance_reason) for event in inferred_events],
        )
        self.assertEqual(official_event.relevance_tier, "strong", official_event.relevance_reason)

    def test_third_party_app_comparing_itself_with_ios_is_not_an_os_compatibility_matrix(self):
        article = article_for(
            self.module,
            "微信鸿蒙版 App 灰度全新相机页面：看齐 iOS 端，支持按住滑动选择精确焦段",
            "微信鸿蒙版正在灰度新的相机页面，交互方式与该应用的 iOS 版本相似。",
            "IT之家",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak")
        self.assertNotEqual(
            event.relevance_reason,
            "current Apple OS device and feature compatibility matrix",
        )

    def test_global_market_report_does_not_warn_on_background_regions(self):
        articles = [
            article_for(
                self.module,
                "Counterpoint: iPhone 17 was the world's best-selling smartphone in Q2 2026",
                "The global report also discusses Apple's results in India and Japan.",
                "IT之家",
            ),
            article_for(
                self.module,
                "2026 Q2 global smartphone bestseller ranking puts iPhone 17 first",
                "Counterpoint's worldwide ranking includes regional context from Japan and India.",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_legacy_seed_cannot_join_distinct_first_party_title_subjects(self):
        articles = [
            article_for(
                self.module,
                "Apple Reveals M6 as First-Ever 2nm Chip",
                "Apple announced M6 as its first 2nm chip.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple releases new Magic Keyboards with one notable change",
                "Apple released new Magic Keyboards with revised key symbols.",
                "9to5Mac",
            ),
        ]

        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}
        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )

        self.assertEqual(len(groups), 2, [[item.title for item in group] for group in groups])

    def test_real_chinese_accessory_titles_merge_only_with_same_product(self):
        articles = [
            article_for(
                self.module,
                "Apple Quietly Refreshes Magic Keyboards",
                "Apple refreshed four Magic Keyboard models with symbol-only labels.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple releases new Magic Keyboards with one notable change",
                "Apple launched minor updates to its Magic Keyboard accessories.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "MacBook-style key symbols come to all four Magic Keyboards",
                "Apple quietly updated its Magic Keyboard with symbol-only keycaps.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果妙控键盘美式英语版悄悄更新：Tab、CapsLock、Return 等按键取消文字，改为符号",
                "苹果更新四款妙控键盘的按键标识。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果悄然更新妙控键盘 多个按键改用符号标识",
                "苹果更新妙控键盘，将文字标签换为符号。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "69 元，苹果官网上线新款抛光布",
                "苹果官网上架新款抛光布。",
                "IT之家",
            ),
            article_for(
                self.module,
                "价格腰斩！苹果新款抛光布发布：只要69元",
                "苹果发布售价 69 元的新款抛光布。",
                "快科技",
            ),
        ]

        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}
        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )
        title_sets = [{item.title for item in group} for group in groups]

        self.assertEqual(len(groups), 2, title_sets)
        self.assertTrue(
            any(
                len(titles) == 5
                and all("Keyboard" in title or "键盘" in title for title in titles)
                for titles in title_sets
            )
        )
        self.assertTrue(any(len(titles) == 2 and all("抛光布" in title for title in titles) for titles in title_sets))
        for article in articles:
            self.module.reconcile_article_relevance(article, profiles[id(article)])
        self.assertTrue(all(article.category == "hardware_products" for article in articles))

    def test_editorial_shopping_and_product_preview_forms_override_legacy_strong(self):
        samples = [
            "Where to preorder the updated Mac Mini and Mac Studio",
            "New Mac mini and more now available from Amazon for launch day pre-order",
            "Three new Macs are launching this fall, here's what's coming",
        ]

        for title in samples:
            with self.subTest(title=title):
                article = article_for(
                    self.module,
                    title,
                    "An editorial overview links to products and recaps announced specifications.",
                    "9to5Mac",
                    tier="strong",
                    reason="legacy Apple product match",
                )
                event = self.module.cluster_articles([article])[0]
                self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_direct_product_subjects_split_roadmap_from_unrelated_feature_detail(self):
        articles = [
            article_for(
                self.module,
                "M6 MacBook Pro and M6 iMacs Likely Coming in October",
                "Apple is expected to launch refreshed MacBook Pro and iMac models in October.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果全新 Mac mini 搭载 Apple N1 无线网络芯片，支持 Wi-Fi 7、蓝牙 6、Thread 网络技术",
                "苹果新款 Mac mini 增加 N1 无线芯片。",
                "IT之家",
            ),
        ]
        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )

        self.assertEqual(len(groups), 2, [[item.title for item in group] for group in groups])

    def test_structured_editorial_tier_prevents_roundup_from_bridging_news(self):
        articles = [
            article_for(
                self.module,
                "Apple Reveals M6 as First-Ever 2nm Chip",
                "Apple announced M6 as its first 2nm chip.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Three new Macs are launching this fall, here's what's coming",
                "The article recaps announced and rumored Mac models.",
                "9to5Mac",
                tier="strong",
                reason="legacy Apple product match",
            ),
        ]
        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )

        self.assertEqual(len(groups), 2, [[item.title for item in group] for group in groups])

    def test_comparison_style_product_is_not_the_title_action_subject(self):
        title = "MacBook-style key symbols come to all four Magic Keyboards"
        identity = self.module.cached_article_title_led_event_identity(
            title,
            "Apple quietly updated its Magic Keyboard with symbol-only keycaps.",
            (),
            (),
        )

        self.assertIn("magic-keyboard", identity.title_products)
        self.assertNotIn("macbook", identity.title_products)

    def test_news_flash_prefix_does_not_hide_first_party_product_owner(self):
        articles = [
            article_for(
                self.module,
                "Apple Reveals M6 as First-Ever 2nm Chip",
                "Apple announced M6 as its first 2nm chip.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "刚刚，新款 Mac mini 发布！价格大涨 2500 元",
                "新机采用 M6 与 M5 Pro，并调整起售价。",
                "爱范儿",
            ),
        ]
        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )

        self.assertEqual(len(groups), 2, [[item.title for item in group] for group in groups])

    def test_platform_release_context_does_not_absorb_specific_service_action(self):
        articles = [
            article_for(
                self.module,
                "iOS 27 release date: Here's when the new iPhone update will launch",
                "Apple is expected to release iOS 27 in September.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果 iOS 27 正式版发布在即，Siri AI 预计将采用候补名单机制",
                "Siri AI 首发时预计采用候补名单控制访问。",
                "IT之家",
            ),
        ]
        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )

        self.assertEqual(len(groups), 2, [[item.title for item in group] for group in groups])

    def test_product_launch_does_not_absorb_separate_capability_report(self):
        articles = [
            article_for(
                self.module,
                "时隔近两年！苹果全新 Mac mini 即将发布",
                "苹果准备发布新款 Mac mini。",
                "快科技",
            ),
            article_for(
                self.module,
                "苹果新款 Mac mini 可连接三台显示器，但不同处理器的最高分辨率有区别",
                "新款 Mac mini 的显示器支持规格因处理器而异。",
                "IT之家",
            ),
        ]
        profiles = {id(article): self.module.article_reconciliation_profile(article) for article in articles}

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[articles],
        )

        self.assertEqual(len(groups), 2, [[item.title for item in group] for group in groups])

    def test_service_access_mechanism_does_not_join_os_release_date(self):
        articles = [
            article_for(
                self.module,
                "iOS 27 release date: Here's when the new iPhone update will launch",
                "Apple is expected to release iOS 27 in September.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Prepare to wait for Siri AI access when iOS 27 launches next month",
                "Apple will use a waitlist to control initial access to Siri AI.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "You'll have to wait in line for Siri AI in iOS 27",
                "Apple will initially place Siri AI users in an access queue.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果或将为 Siri AI 设置排队机制，iOS 27 正式版发布初期访问可能受限",
                "苹果将通过候补名单限制 Siri AI 首发阶段的访问量。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "苹果 iOS 27 正式版发布在即，Siri AI 预计将采用候补名单机制",
                "Siri AI 首发时预计采用候补名单控制访问。",
                "IT之家",
            ),
        ]

        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in articles
        }
        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[[article] for article in articles],
        )
        title_sets = [{item.title for item in group} for group in groups]

        self.assertEqual(len(groups), 2, title_sets)
        self.assertTrue(any(len(titles) == 4 and all("Siri AI" in title for title in titles) for titles in title_sets))

    def test_same_first_party_product_action_merges_across_source_wording(self):
        samples = [
            (
                [
                    ("Apple Maps launches ads on iPhone, here's what's new", "Apple Maps ads began rolling out in the US and Canada."),
                    ("Apple Maps ads begin rolling out in US, Canada", "Sponsored listings are now appearing in Apple Maps."),
                    ("苹果地图广告正式在美国、加拿大上线，且无法关闭", "苹果地图广告正式在美国和加拿大上线。"),
                ],
                "software_systems",
            ),
            (
                [
                    ("Apple Releases New Polishing Cloth", "Apple released a new Polishing Cloth for $9."),
                    ("Apple's Polishing Cloth is back for $9", "Apple restored its Polishing Cloth to the store at $9."),
                    ("苹果新款擦布悄然降价 10 美元，产品本身与旧款并无差异", "苹果官网上架新版擦拭布并将售价从 19 美元降至 9 美元。"),
                ],
                "hardware_products",
            ),
            (
                [
                    ("Apple's 40W Dynamic Power Adapter Expands to More Countries", "Apple expanded the adapter to additional European markets."),
                    ("苹果 40W 动态电源适配器登陆欧洲更多市场，支持最高 60W 短时充电功率", "苹果把动态电源适配器扩展到更多市场。"),
                    ("苹果 40W 动态充电头开始普及，最高能输出 60W 功率", "苹果进一步扩大了 40W 动态电源适配器的销售覆盖范围。"),
                ],
                "hardware_products",
            ),
            (
                [
                    ("Apple Unveils New Mac Studio With M5 Max and M5 Ultra Chips", "Apple launched the new Mac Studio with M5 Max and M5 Ultra."),
                    ("Apple introduces new Mac Studio with M5 Max and M5 Ultra", "Apple introduced the same Mac Studio generation."),
                    ("苹果新一代 Mac Studio 正式登场：可选 M5 Max 或 M5 Ultra 芯片", "苹果发布新一代 Mac Studio。"),
                ],
                "hardware_products",
            ),
            (
                [
                    ("Apple Home hub roadmap update", "Apple's Home Hub remains planned for this year."),
                    ("Apple Smart Home Display Still Coming This Year", "Apple still plans to release its smart home hub this year."),
                    ("苹果 Home Hub 或将支持人脸识别自动切换个人资料", "苹果智能家居中枢将支持个人资料切换。"),
                ],
                "hardware_products",
            ),
        ]

        for rows, expected_category in samples:
            with self.subTest(title=rows[0][0]):
                articles = [
                    article_for(self.module, title, summary, f"Source-{index}")
                    for index, (title, summary) in enumerate(rows)
                ]
                events = self.module.cluster_articles(articles)
                self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])
                self.assertEqual(events[0].category, expected_category)

    def test_same_named_apple_tv_project_merges_across_descriptive_titles(self):
        articles = [
            article_for(
                self.module,
                "Apple TV unveils Matthew McConaughey comedy series from The Office alum",
                "Apple TV has a new original comedy series - Brothers - premiering September 23.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果 Apple TV+ 原创喜剧《兄弟》定档 9 月 23 日",
                "Apple TV+ 下个月将推出原创喜剧《兄弟》（Brothers），由马修 · 麦康纳和伍迪 · 哈里森联袂主演。"
                "苹果日前公布了该剧预告片。两人将在剧中出演经过虚构化处理的自己。"
                "这部剧将于 9 月 23 日首播。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])
        self.assertEqual(events[0].category, "software_systems")

    def test_precise_product_release_reconciles_globally_without_absorbing_capability_news(self):
        articles = [
            article_for(
                self.module,
                "Apple Unveils New Mac Studio With M5 Max and M5 Ultra Chips",
                "Apple launched the new Mac Studio generation with M5 Max and M5 Ultra.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple introduces new Mac Studio with M5 Max and M5 Ultra",
                "Apple introduced the same Mac Studio generation.",
                "Apple Newsroom",
            ),
            article_for(
                self.module,
                "苹果最强 Mac 杀到！全新 Mac Studio 发布：19999 元起",
                "苹果发布新一代 Mac Studio，搭载 M5 Max 和 M5 Ultra。",
                "快科技",
            ),
            article_for(
                self.module,
                "Apple's new Mac Studio has fresh M5 Max and M5 Ultra offerings",
                "Apple is announcing a new generation of the Mac Studio.",
                "The Verge",
            ),
            article_for(
                self.module,
                "Mac Studio gets update to M5 Max and M5 Ultra",
                "Apple has launched new versions of the Mac Studio with M5 Max and M5 Ultra.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果全新 Mac Studio 首次支持 Genlock 专业同步",
                "新款 Mac Studio 可通过 USB-C 同步显示器和摄像头。",
                "IT之家",
            ),
        ]

        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in articles
        }
        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[[article] for article in articles],
        )
        title_sets = [{item.title for item in group} for group in groups]

        self.assertEqual(len(groups), 2, title_sets)
        self.assertTrue(any(len(titles) == 5 for titles in title_sets), title_sets)
        self.assertTrue(any(any("Genlock" in title for title in titles) for titles in title_sets), title_sets)

    def test_global_product_release_does_not_carry_seeded_display_capability(self):
        articles = [
            article_for(
                self.module,
                "Apple Announces New Mac Mini With M6 and M5 Pro Chips and More",
                "Apple announced the new Mac mini with M6 and M5 Pro chips.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "New M6 Mac mini keeps the three-display limit but raises refresh rates",
                "Apple kept the new M6 and M5 Pro Mac mini at three external displays, but increased the maximum refresh rate, and gave M5 Pro support for connecting all three through one Thunderbolt port.",
                "AppleInsider",
                facts=[
                    "The Mac mini models were introduced August 25 and will be available September 22.",
                    "Both chips support one display at up to 8K at 60Hz, 5K at 120Hz, or 4K at 240Hz.",
                ],
            ),
            article_for(
                self.module,
                "苹果新款 Mac mini 可连接三台显示器，但不同处理器的多显示器最高分辨率有区别",
                "苹果已推出新款 Mac mini，升级 M6/M5 Pro 芯片，售价 6999 元起，将于 9 月 22 日正式上市，不同芯片版本均支持连接三台显示器，但最高分辨率和刷新率有区别。",
                "IT之家",
                facts=[
                    "据苹果官网所述，M6 Mac mini 可通过雷雳和 HDMI 端口连接三台显示器。",
                    "M5 Pro Mac mini 可通过雷雳和 HDMI 端口的任意组合最多连接三台显示器。",
                ],
            ),
            article_for(
                self.module,
                "苹果全新 Mac mini 发布：搭载 M6、M5 Pro 芯片",
                "苹果发布全新 Mac mini，提供 M6 和 M5 Pro 两种芯片版本。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "Apple Mac mini roadmap update",
                "Apple could launch a new Mac mini later this year.",
                "RoadmapSource",
            ),
        ]
        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in articles
        }

        groups = self.module.reconcile_articles(
            articles,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[[articles[0], articles[2], articles[4]], [articles[1]], [articles[3]]],
        )
        title_sets = [{item.title for item in group} for group in groups]

        self.assertEqual(len(groups), 3, title_sets)
        self.assertTrue(any(len(titles) == 2 for titles in title_sets), title_sets)
        self.assertTrue(
            any(
                len(titles) == 2
                and any("three-display" in title for title in titles)
                and any("三台显示器" in title for title in titles)
                for titles in title_sets
            ),
            title_sets,
        )

    def test_generation_refresh_key_does_not_absorb_display_capability(self):
        articles = [
            article_for(
                self.module,
                "Apple Announces New Mac Mini With M6 and M5 Pro Chips and More",
                "Apple announced the new Mac mini with M6 and M5 Pro chips.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "New M6 Mac mini keeps the three-display limit but raises refresh rates",
                "The new M6 Mac mini supports three displays with higher refresh rates.",
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 2, [[item.title for item in event.articles] for event in events])

    def test_third_party_tool_cannot_become_a_product_release_anchor(self):
        articles = [
            article_for(
                self.module,
                "Apple Announces New Mac Mini With M6 and M5 Pro Chips and More",
                "Apple announced the new Mac mini with M6 and M5 Pro chips.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "JetBrains local model won't cost any tokens, but needs a $2,700 Mac mini to run it",
                "Apple just announced the Mac mini with M5 Pro, while JetBrains released a local coding model that requires 64GB of RAM.",
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 2, [[item.title for item in event.articles] for event in events])
        third_party_event = next(
            event for event in events if any("JetBrains" in item.title for item in event.articles)
        )
        self.assertEqual(third_party_event.relevance_tier, "weak")

    def test_release_does_not_absorb_later_high_memory_configuration(self):
        articles = [
            article_for(
                self.module,
                "Apple Unveils New Mac Studio With M5 Max and M5 Ultra Chips",
                "Apple announced the new Mac Studio with M5 Max and M5 Ultra.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Mac Studio With M5 Ultra Chip and 512GB of RAM Launching in October",
                "The 512GB configuration arrives later than the standard September launch.",
                "9to5Mac",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 2, [[item.title for item in event.articles] for event in events])

    def test_attributed_direct_product_roadmap_is_not_demoted_by_reporter_name(self):
        article = article_for(
            self.module,
            "古尔曼：新一代苹果 iPad mini 最晚 10 月下旬发布，带来 OLED 屏幕、防水等升级",
            "据彭博社记者马克·古尔曼报道，苹果计划于 10 月底前推出新款 iPad mini。",
            "IT之家",
            tier="weak",
            reason="non-Apple primary subject using Apple only as comparison context",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_reported_launch_window_keeps_sources_with_same_changed_component(self):
        articles = [
            article_for(
                self.module,
                "New iPad Mini With Four Upgrades Expected to Launch by Late October",
                "The next iPad mini is expected by late October with an OLED display.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "古尔曼：新一代苹果 iPad mini 最晚 10 月下旬发布，带来 OLED 屏幕、防水等升级",
                "苹果计划于 10 月底前推出新款 iPad mini，升级 OLED 屏幕并支持防水。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])
        self.assertEqual(len(events[0].articles), 2)

    def test_accessibility_feature_catalog_is_software(self):
        title = "Apple outlines 50 ways to make devices easier to use as we age"
        summary = "Apple published an accessibility feature catalog covering iOS, macOS, and watchOS capabilities."

        article = article_for(self.module, title, summary, "9to5Mac")
        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.category, "software_systems")

    def test_isolated_affiliate_cta_does_not_become_a_key_fact(self):
        source = next(
            source
            for source in self.module.build_sources(datetime.now(timezone.utc).astimezone())
            if source.name == "9to5Mac"
        )
        page = """
        <html><head>
          <meta property="article:published_time" content="2026-08-25T18:33:10+00:00" />
          <meta property="og:description" content="Apple Maps ads are rolling out in the US and Canada." />
        </head><body><div class="post-content">
          <p>Apple confirmed that sponsored listings are now rolling out in Apple Maps.</p>
          <p>Ads appear in Suggested Places before a search and in relevant search results.</p>
          <p>*Buy iPhone with 15% discount from Apple refurbished</p>
        </div></body></html>
        """
        candidate = self.module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/example/maps-ads/",
            title="Apple Maps launches ads on iPhone",
        )

        _, summary, facts, *_ = self.module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertNotIn("15% discount", combined)


if __name__ == "__main__":
    unittest.main()
