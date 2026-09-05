import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260905_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(
    module,
    title,
    summary,
    source="9to5Mac",
    facts=None,
    projection_parent_keys=(),
):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((title, summary)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc),
        published_raw="2026-09-05T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
        projection_child_key=(
            module.projection_child_key(title) if projection_parent_keys else ""
        ),
        projection_parent_keys=frozenset(projection_parent_keys),
    )


class ClaimOwnershipBoundaries20260905(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_single_controller_disclosure_does_not_project_background_products(self):
        title = "macOS 26.7 Code Hints at Two Unreleased Apple Game Controllers"
        summary = (
            "Apple's first macOS 26.7 release candidate was full of references "
            "to unreleased Apple devices, from iPhones and Macs to new home accessories."
        )
        facts = [
            "The current code contains two unreleased Apple game controller identifiers.",
            "Apple previously added Sony PlayStation VR2 Sense controller support to Vision Pro.",
        ]

        variants = self.module.multi_product_hardware_roadmap_variants(title, summary, facts)

        self.assertEqual(variants, [(title, summary, facts)])

    def test_hardware_roadmap_and_platform_feature_removal_do_not_merge(self):
        reports = [
            article_for(
                self.module,
                "Apple Apple Watch roadmap update",
                (
                    "Touch ID was initially rumored for the next Apple Watches but has been ruled out. "
                    "Apple Watch Series 12 may use a faster chip and ceramic case. "
                    "Apple Watch Ultra 4 may add continuous heart-rate sensing and satellite features, "
                    "including Apple Maps and Messages via satellite."
                ),
                "MacRumors",
            ),
            article_for(
                self.module,
                "watchOS 27 removes three features that Apple Watch users might miss after updating",
                (
                    "When watchOS 27 is released later this month, the software update removes "
                    "three features that users may miss after updating."
                ),
                "9to5Mac",
                [
                    "Walkie-Talkie is Apple's real-time voice app that only works between Apple Watches.",
                    "The Digital Crown double-click multitasking gesture is removed.",
                ],
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])
        self.assertEqual({event.category for event in events}, {"hardware_products", "software_systems"})

    def test_first_party_unreleased_controller_disclosures_merge_as_hardware(self):
        reports = [
            article_for(
                self.module,
                "Two unreleased Apple game controllers found in macOS code",
                "Apple's code contains identifiers for two unreleased Apple-made physical game controllers.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果 macOS 代码曝光两款未发布自研游戏手柄",
                "苹果系统代码显示两款第一方实体游戏手柄，支持 USB 和蓝牙连接。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].relevance_tier, "strong", events[0].relevance_reason)
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(len(events[0].articles), 2)

    def test_specific_hardware_disclosure_owns_system_code_context(self):
        article = article_for(
            self.module,
            "苹果加码游戏生态，macOS 26.7 RC 曝光 2 款自研游戏手柄",
            (
                "苹果系统代码包含两款未发布第一方实体游戏手柄的标识符，"
                "相关资源由候选版意外带出。"
            ),
            "IT之家",
        )

        profile = self.module.article_reconciliation_profile(article)

        self.assertEqual(profile.category_hint, "hardware_products")
        self.assertIn(
            "primary-claim:apple-game-controller:unreleased-code-disclosure",
            profile.event_keys,
        )
        self.assertNotIn(
            "primary-claim:apple-system-build:unintended-product-asset-disclosure",
            profile.event_keys,
        )

    def test_third_party_product_launch_with_apple_home_support_is_weak(self):
        article = article_for(
            self.module,
            "Aqara Debuts Five Matter Smart Lights With Apple Home Support",
            "Aqara launched five of its own Matter lights and lists Apple Home as a compatible platform.",
            "MacRumors",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_temporal_prefix_does_not_become_an_apple_tv_content_title(self):
        claims = self.module.project_first_party_content_claims(
            "Apple TV has two new Silo releases",
            (
                "Silo season 4 launches after production is complete. "
                "Today Silo debuted its season 3 finale on Apple TV. "
                "Silo’s season 3 finale is available now."
            ),
            [],
        )

        subjects = {claim.subject.casefold() for claim in claims}
        self.assertNotIn("today silo", subjects)
        self.assertIn("silo season 4", subjects)
        self.assertTrue(any("season 3 finale" in subject for subject in subjects), subjects)
        self.assertEqual(
            sum("season 3 finale" in subject for subject in subjects),
            1,
            subjects,
        )

    def test_progressive_production_wording_reconciles_with_production_report(self):
        reports = [
            article_for(
                self.module,
                "Apple making just a few hundred foldable iPhones per day, per report",
                "The trial line is making only a few hundred foldable iPhone units per day.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果首款折叠 iPhone 试产线日产仅数百台",
                "报道称苹果折叠 iPhone 目前每天只生产数百台，仍处于试产阶段。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(len(events[0].articles), 2)

    def test_first_party_home_camera_roadmap_merges_across_languages(self):
        reports = [
            article_for(
                self.module,
                "Apple Planning AI Home Security Camera and Service for 2027",
                "Apple is planning its own AI home security camera and related service for 2027.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果计划 2027 年推出自研家庭安防摄像头及配套服务",
                "苹果正在开发第一方智能家居摄像头和云端安防服务。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(len(events[0].articles), 2)

    def test_home_security_service_does_not_bridge_into_homepod_roadmap(self):
        reports = [
            article_for(
                self.module,
                "Apple HomePod roadmap update",
                "HomePod mini will use a newer chip, improved audio, Wi-Fi 7, and new colors.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple plans to launch home security and monitoring service: report",
                "Apple has a home security and monitoring service in the works for 2027.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Planning AI Home Security Camera and Service for 2027",
                "Apple is planning a privacy-forward camera and home security service for 2027.",
                "MacRumors",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])
        service_event = next(event for event in events if len(event.articles) == 2)
        self.assertEqual(service_event.category, "software_systems")

    def test_physical_title_subject_outranks_software_capability_qualifier(self):
        article = article_for(
            self.module,
            "Apple Testing New HomePod With Siri AI",
            "Apple is testing a new full-sized HomePod with Siri AI support.",
            "MacRumors",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.category, "hardware_products")

    def test_product_naming_rumor_merges_short_and_descriptive_titles(self):
        reports = [
            article_for(
                self.module,
                "iPhone Duo?",
                (
                    "iPhone Duo?. While the long-awaited foldable iPhone has often been referred "
                    "to as the iPhone Ultra or the iPhone Fold in rumors, another name making the "
                    "rounds is iPhone Duo."
                ),
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果首款折叠 iPhone 名称或定为 iPhone Duo",
                "消息称苹果正考虑为首款折叠屏 iPhone 使用 iPhone Duo 这一产品名称。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(len(events[0].articles), 2)

    def test_price_story_with_multiple_models_is_not_projected_as_roadmap(self):
        title = (
            "沃达丰意外曝光苹果新品售价：iPhone 18 Pro 系列温和上涨，"
            "折叠屏 iPhone Ultra 身价不菲"
        )
        summary = (
            "The carrier listed both unreleased phones with higher prices. "
            "Background reporting also describes their chips, cameras, colors, "
            "and expected launch schedule."
        )
        facts = [
            "iPhone 18 Pro was listed at $1,099.",
            "The foldable iPhone Ultra was listed at $1,999.",
            "Both models are expected to launch at Apple's September event.",
        ]

        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            summary,
            facts,
        )

        self.assertEqual(variants, [(title, summary, facts)])

    def test_broad_iphone_roadmap_projects_distinct_product_generations(self):
        title = "Leaked iPhone roadmap reveals plans for multiple future models"
        summary = (
            "The iPhone 18 Pro will use an A20 Pro chip and updated camera. "
            "The iPhone 20 will adopt a curved glass chassis and thinner bezels."
        )
        facts = [
            "iPhone 18 Pro will use an A20 Pro chip and updated camera.",
            "iPhone 20 will adopt a curved glass chassis and thinner bezels.",
        ]

        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            summary,
            facts,
        )

        titles = {variant_title for variant_title, _summary, _facts in variants}
        self.assertIn("Apple iPhone 18 roadmap update", titles)
        self.assertIn("Apple iPhone 20 roadmap update", titles)
        self.assertNotIn("Apple iPhone roadmap update", titles)

    def test_broad_foldable_roadmap_projects_explicit_generations(self):
        title = "Leaked iPhone roadmap reveals plans for multiple future models"
        summary = (
            "iPhone 18 Pro will use an A20 Pro chip. "
            "The first iPhone Ultra will use an advanced hinge. "
            "A second-generation foldable iPhone is already in testing with a new chip. "
            "A third-generation foldable iPhone will have larger inner and outer displays."
        )
        facts = [
            "iPhone 18 Pro will use an A20 Pro chip.",
            "The first iPhone Ultra will use an advanced hinge.",
            "A second-generation foldable iPhone is already in testing with a new chip.",
            "A third-generation foldable iPhone will have larger inner and outer displays.",
        ]

        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            summary,
            facts,
        )

        titles = {variant_title for variant_title, _summary, _facts in variants}
        self.assertIn("Apple iPhone Ultra roadmap update", titles)
        self.assertIn("Apple second-generation foldable iPhone roadmap update", titles)
        self.assertIn("Apple third-generation foldable iPhone roadmap update", titles)

    def test_foldable_roadmap_generations_remain_separate_after_clustering(self):
        reports = [
            article_for(
                self.module,
                "Apple iPhone Ultra roadmap update",
                "The first foldable iPhone will use an advanced hinge.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple second-generation foldable iPhone roadmap update",
                "The second-generation foldable is already in testing with a new chip.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple third-generation foldable iPhone roadmap update",
                "The third-generation foldable will have larger inner and outer displays.",
                "9to5Mac",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 3, [(event.title, len(event.articles)) for event in events])

    def test_physical_mockup_disclosure_does_not_merge_with_color_lineup(self):
        reports = [
            article_for(
                self.module,
                "This is the folding iPhone, if case manufacturers are right",
                (
                    "Case manufacturers created physical dummy units showing the "
                    "foldable iPhone's dimensions, buttons, hinge, and camera layout."
                ),
                "AppleInsider",
            ),
            article_for(
                self.module,
                "保护壳厂商提前曝光外形细节，折叠版 iPhone 真机或将长这样",
                "保护壳厂商的实体机模展示了折叠 iPhone 的尺寸、按键、铰链和摄像头布局。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "消息称苹果首款折叠 iPhone Ultra 仅推两款首发配色",
                "爆料称首发颜色只有深蓝色和银色。",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])

    def test_focused_finish_disclosure_does_not_merge_into_broad_roadmap(self):
        reports = [
            article_for(
                self.module,
                "Apple iPhone Ultra roadmap update",
                (
                    "iPhone Ultra will come in light and dark color options. "
                    "A second-generation foldable is already in testing with a new chip. "
                    "A third generation is planned with larger inner and outer displays."
                ),
                "9to5Mac",
            ),
            article_for(
                self.module,
                (
                    "打破常规配色预期：消息称苹果首款折叠屏 iPhone Ultra "
                    "仅推两款首发配色 - Apple iPhone - cnBeta.COM"
                ),
                (
                    "消息显示，这款开辟全新产品线的设备首发时预计仅提供两款配色方案。 "
                    "配件样品随后显示银色以及深蓝色两种机身色彩倾向。"
                ),
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_current_camera_roadmap_does_not_absorb_anniversary_redesign(self):
        reports = [
            article_for(
                self.module,
                "Apple iPhone 18 roadmap update",
                (
                    "iPhone 18 Pro will use an updated camera system, A20 Pro, "
                    "new colors, and an improved vapor chamber."
                ),
                "MacRumors",
            ),
            article_for(
                self.module,
                "iPhone 20 rumored to have biggest revamp since iPhone X",
                (
                    "Apple plans a 20th-anniversary iPhone with curved glass, "
                    "thinner bezels, and the largest redesign since iPhone X."
                ),
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_multi_year_product_launch_wave_merges_across_headline_variants(self):
        reports = [
            article_for(
                self.module,
                "Apple begins its largest product lineup in the new CEO era",
                (
                    "Apple is preparing its largest device launch wave across 2026, "
                    "2027, and later years, including new product categories."
                ),
                "cnBeta",
            ),
            article_for(
                self.module,
                "Gurman details Apple's biggest-ever product lineup through 2029",
                (
                    "Apple plans a multi-year hardware release cycle spanning 2026, "
                    "2027, and beyond."
                ),
                "IT之家",
            ),
            article_for(
                self.module,
                "Apple's five-year roadmap reveals its largest product wave",
                (
                    "Apple will launch new device forms and enter new product fields "
                    "through 2026, 2027, and later years."
                ),
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(len(events[0].articles), 3)

    def test_multi_year_product_wave_projects_product_owned_actions(self):
        variants = self.module.multi_product_hardware_roadmap_variants(
            "古尔曼称苹果将以史上最大新品阵容开启新时代，公布今年至 2029 年后产品规划",
            "彭博社称苹果将在 2026 年、2027 年及更远未来推出多个产品系列。",
            [
                "折叠 iPhone 将搭载 A20 Pro，并采用新铰链，预计今年发布。",
                "Apple Watch Series 12 将增加陶瓷表壳并升级健康功能。",
                "AirPods 5 将更新入门产品，并继续提供普通版和降噪版。",
                "M6 版 iMac 将换用新芯片，并可能增加机身配色。",
                "苹果正在筹备新一代 Apple Pencil，并计划在 2027 年推出。",
            ],
        )

        variant_titles = {title for title, _summary, _facts in variants}
        self.assertEqual(len(variants), 5, variants)
        for product in ("iPhone", "Apple Watch", "AirPods", "iMac", "Apple Pencil"):
            self.assertTrue(
                any(product in title for title in variant_titles),
                (product, sorted(variant_titles)),
            )

    def test_multi_year_product_wave_uses_fact_heading_as_subject_owner(self):
        variants = self.module.multi_product_hardware_roadmap_variants(
            "古尔曼称苹果将以史上最大新品阵容开启新时代，公布今年至 2029 年后产品规划",
            "彭博社称苹果将在 2026 年、2027 年及更远未来推出多个产品系列。",
            [
                "OLED 版 iPad Air：2027 款将改用 OLED，与 iPad mini 的显示技术一致。",
                (
                    "首批触摸屏 OLED MacBook Pro：苹果正在准备五年来幅度最大的改款。"
                    "新机将采用类似 iPhone 灵动岛的设计。"
                ),
                "全新 Apple Pencil：配合 2027 年 iPad 产品线，苹果正在筹备两款新手写笔。",
                "首款带屏智能家居中枢：苹果未来数月将推出约 7 英寸方形屏幕设备。",
            ],
        )

        variant_titles = {title for title, _summary, _facts in variants}
        self.assertEqual(len(variants), 4, variants)
        for product in ("iPad Air", "MacBook Pro", "Apple Pencil", "Home hub"):
            self.assertTrue(
                any(product in title for title in variant_titles),
                (product, sorted(variant_titles)),
            )
        self.assertFalse(
            any(title == "Apple iPhone roadmap update" for title in variant_titles),
            sorted(variant_titles),
        )
        macbook_facts = next(
            facts for title, _summary, facts in variants if "MacBook Pro" in title
        )
        self.assertTrue(any("灵动岛" in fact for fact in macbook_facts), macbook_facts)

    def test_projected_siblings_cannot_bridge_different_product_events(self):
        beats = article_for(
            self.module,
            "Apple Beats roadmap update",
            "Beats 360 will add a new over-ear design and replaceable cushions.",
            "MacRumors",
        )
        airpods = article_for(
            self.module,
            "Apple AirPods roadmap update",
            "AirPods 5 will update the entry-level earbuds in two versions.",
            "MacRumors",
        )
        translated_airpods = article_for(
            self.module,
            "Apple AirPods roadmap update",
            "苹果将更新入门级 AirPods 5，并继续提供普通版和降噪版。",
            "IT之家",
        )
        beats.url = airpods.url = "https://example.com/macrumors/apple-product-wave"

        self.assertIn(
            "beats",
            self.module.title_led_identity(beats.title, beats.summary).title_products,
        )

        events = self.module.cluster_articles([beats, airpods, translated_airpods])

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])
        event_title_sets = [{article.title for article in event.articles} for event in events]
        self.assertIn(
            {"Apple AirPods roadmap update"},
            event_title_sets,
        )

    def test_distinct_publisher_story_requires_specific_action_to_rejoin(self):
        generic_it = article_for(
            self.module,
            "Apple iPad roadmap update",
            "New entry-level iPad will use a faster chip and add Apple Intelligence.",
            "IT之家",
        )
        generic_fast = article_for(
            self.module,
            "Apple iPad roadmap update",
            "The entry-level iPad gets a faster chip and Apple Intelligence.",
            "快科技",
        )
        cancellation_fast = article_for(
            self.module,
            "Apple foldable iPad and Mac project officially cancelled",
            (
                "Apple had two foldable product lines, including a foldable iPad. "
                "The foldable iPad project used an 18- to 20-inch display. "
                "The device was delayed from 2026 to 2028 and then officially cancelled."
            ),
            "快科技",
            ["The device was delayed from 2026 to 2028 and then officially cancelled."],
        )
        generic_fast.url = "https://example.com/mydrivers/product-wave"
        cancellation_fast.url = "https://example.com/mydrivers/foldable-cancellation"

        events = self.module.cluster_articles(
            [generic_it, generic_fast, cancellation_fast]
        )

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_later_roadmap_details_do_not_create_title_fact_bridge(self):
        article = article_for(
            self.module,
            "Apple begins its largest multi-year product launch wave",
            (
                "Apple plans new product categories across 2026, 2027, and beyond. "
                "A later section says an Apple Watch redesign may eventually use a round screen."
            ),
            "cnBeta",
        )

        profile = self.module.article_reconciliation_profile(article)

        self.assertNotIn(
            "title-fact:form-factor-redesign:apple-watch",
            profile.event_keys,
        )

    def test_service_catalog_roundup_without_new_announcement_is_weak(self):
        article = article_for(
            self.module,
            "Apple TV's big fall lineup: Here's every new show and movie coming soon",
            (
                "Here is everything in Apple TV's fall lineup so far, including returning "
                "series, previously announced shows, and movies that are coming soon."
            ),
            "9to5Mac",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_executive_profile_without_current_apple_action_is_weak(self):
        article = article_for(
            self.module,
            "New profile of John Ternus offers insight into life and reputation of Apple CEO",
            (
                "The Financial Times published a profile about Ternus's education, early "
                "career, personality, and reputation among Apple employees and partners."
            ),
            "9to5Mac",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_third_party_app_update_cannot_be_promoted_as_os_compatibility(self):
        article = article_for(
            self.module,
            "iOS 版谷歌翻译升级实时翻译：iPhone 17 等支持贴耳私听",
            (
                "谷歌发布博文宣布升级 Google Translate 实时翻译功能，"
                "iPhone 17 等设备可通过听筒收听翻译内容。"
            ),
            "IT之家",
            [
                "iOS 版谷歌翻译新增听筒播放功能。",
                "安卓版还支持在后台和锁屏状态继续翻译。",
            ],
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)
        self.assertNotEqual(
            event.relevance_reason,
            "current Apple OS device and feature compatibility matrix",
        )

    def test_same_report_projection_rejoins_complementary_product_facts(self):
        shared_report = {"report-attribution:mark-gurman"}
        reports = [
            article_for(
                self.module,
                "Apple HomePod roadmap update",
                "HomePod mini will gain Wi-Fi 7, a newer chip, and new colors.",
                "MacRumors",
                projection_parent_keys=shared_report,
            ),
            article_for(
                self.module,
                "Apple HomePod roadmap update",
                "新款 HomePod mini 将升级处理器并支持 Siri AI，外观基本不变。",
                "IT之家",
                projection_parent_keys=shared_report,
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(len(events[0].articles), 2)

    def test_different_report_projections_keep_incompatible_actions_separate(self):
        reports = [
            article_for(
                self.module,
                "Apple HomePod roadmap update",
                "HomePod mini will gain new red and blue finishes.",
                "MacRumors",
                projection_parent_keys={"report-attribution:first-report"},
            ),
            article_for(
                self.module,
                "Apple HomePod roadmap update",
                "另一份报告称 HomePod 将改用更快的处理器。",
                "IT之家",
                projection_parent_keys={"report-attribution:second-report"},
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_overlapping_projection_cohorts_rejoin_each_child_only(self):
        reports = []
        for source, parent_url, entries in (
            (
                "MacRumors",
                "https://example.com/macrumors/product-wave",
                (
                    ("Apple HomePod roadmap update", "HomePod mini gains Wi-Fi 7 and new colors."),
                    ("Apple Apple TV roadmap update", "Apple TV gains more memory and a new remote."),
                ),
            ),
            (
                "IT之家",
                "https://example.com/ithome/product-wave",
                (
                    ("Apple HomePod roadmap update", "HomePod mini 将升级处理器并支持 Siri AI。"),
                    ("Apple Apple TV roadmap update", "Apple TV 将升级处理器并支持 Siri AI。"),
                ),
            ),
        ):
            for title, summary in entries:
                article = article_for(self.module, title, summary, source)
                article.url = parent_url
                article.projection_child_key = self.module.projection_child_key(title)
                reports.append(article)

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(sorted(len(event.articles) for event in events), [2, 2])
        self.assertTrue(
            all(len({article.title for article in event.articles}) == 1 for event in events)
        )

    def test_multi_year_iphone_sections_keep_model_owned_continuations(self):
        variants = self.module.multi_product_hardware_roadmap_variants(
            "苹果未来 5 年路线图曝光，史上最大新品阵容",
            (
                "折叠屏 iPhone：苹果计划推出 iPhone Ultra。"
                "该机将使用新铰链，并支持 Touch ID。"
                "iPhone 18 Pro 和 Pro Max：两款机型将使用 A20 Pro。"
                "相机将加入机械光圈，机身提供深红和浅蓝配色。"
            ),
            [
                "折叠屏 iPhone：苹果计划推出 iPhone Ultra。该机将使用新铰链，并支持 Touch ID。",
                "iPhone 18 Pro 和 Pro Max：两款机型将使用 A20 Pro。相机将加入机械光圈，机身提供深红和浅蓝配色。",
            ],
        )

        by_title = {title: (summary, facts) for title, summary, facts in variants}

        self.assertIn("Apple iPhone Ultra roadmap update", by_title)
        self.assertIn("Apple iPhone 18 roadmap update", by_title)
        ultra_summary, ultra_facts = by_title["Apple iPhone Ultra roadmap update"]
        iphone_18_summary, iphone_18_facts = by_title["Apple iPhone 18 roadmap update"]
        ultra_text = " ".join([ultra_summary, *ultra_facts])
        iphone_18_text = " ".join([iphone_18_summary, *iphone_18_facts])
        self.assertIn("新铰链", ultra_text)
        self.assertNotIn("机械光圈", ultra_text)
        self.assertIn("机械光圈", iphone_18_text)
        self.assertNotIn("新铰链", iphone_18_text)

    def test_projected_child_does_not_absorb_generic_focused_article(self):
        projected = article_for(
            self.module,
            "Apple iPhone Ultra roadmap update",
            (
                "The foldable iPhone will use an advanced hinge and Touch ID, "
                "but may launch after the iPhone 18 Pro models."
            ),
            "MacRumors",
            projection_parent_keys={"cohort:product-wave"},
        )
        projected.url = "https://example.com/macrumors/product-wave"
        projected.projection_child_key = self.module.projection_child_key(projected.title)
        focused = article_for(
            self.module,
            "iPhone Ultra pre-orders may be delayed until the fourth quarter",
            "Manufacturing constraints may push pre-orders beyond the iPhone 18 Pro launch.",
            "9to5Mac",
        )

        events = self.module.cluster_articles([projected, focused])

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_projected_cohort_does_not_bridge_a_focused_product_action(self):
        projections = [
            article_for(
                self.module,
                "Apple iPhone Ultra roadmap update",
                summary,
                source,
                projection_parent_keys={"cohort:product-wave"},
            )
            for source, summary in (
                (
                    "MacRumors",
                    "The foldable iPhone may launch after the iPhone 18 Pro models.",
                ),
                ("IT之家", "折叠屏 iPhone 将采用新铰链并支持 Touch ID。"),
            )
        ]
        focused = article_for(
            self.module,
            "iPhone Ultra pre-orders may be delayed until the fourth quarter",
            "Manufacturing constraints may push pre-orders beyond the iPhone 18 Pro launch.",
            "9to5Mac",
        )

        events = self.module.cluster_articles([*projections, focused])

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])

    def test_projected_cohort_does_not_bridge_on_one_overlapping_child_fact(self):
        projected = article_for(
            self.module,
            "Apple iPhone Ultra roadmap update",
            "A product-wave report lists the foldable model's hardware and launch window.",
            "快科技",
            projection_parent_keys={"cohort:product-wave"},
        )
        focused = article_for(
            self.module,
            "iPhone Ultra launch may be delayed by low production yield",
            "A focused supply-chain report describes a delayed regional launch.",
            "IT之家",
        )
        original_profile = self.module.article_reconciliation_profile

        def profile_with_shared_child_fact(article):
            profile = original_profile(article)
            return self.module.replace(
                profile,
                event_keys=frozenset(
                    {
                        *profile.event_keys,
                        "primary-claim:foldable-iphone:reported-launch-window",
                    }
                ),
            )

        self.module.article_reconciliation_profile = profile_with_shared_child_fact
        try:
            events = self.module.cluster_articles([projected, focused])
        finally:
            self.module.article_reconciliation_profile = original_profile

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])


if __name__ == "__main__":
    unittest.main()
