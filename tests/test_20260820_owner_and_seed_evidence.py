import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260820_test", SCRIPT_PATH)
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
        published_utc=datetime(2026, 8, 20, tzinfo=timezone.utc),
        published_raw="2026-08-20T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class OwnerAndSeedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def reconcile(self, articles, initial_groups=None):
        return self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=initial_groups or [[article] for article in articles],
        )

    def test_seed_group_requires_positive_same_event_evidence(self):
        airpods_5 = article_for(
            self.module,
            "Apple system code reveals unreleased AirPods 5 identifiers",
            "macOS code contains identifiers for Apple's next AirPods models.",
            "MacRumors",
        )
        camera_delay = article_for(
            self.module,
            "Camera-equipped AirPods reportedly delayed until 2027",
            "The B790 project was canceled and the B798 camera-equipped AirPods remain in development.",
            "AppleInsider",
        )
        camera_translation = article_for(
            self.module,
            "消息称苹果摄像头 AirPods 延至 2027 年推出",
            "苹果仍在开发 B798 摄像头 AirPods，原 B790 项目已经取消。",
            "IT之家",
        )
        ios_feature = article_for(
            self.module,
            "iOS 27 adds a new reason to wear AirPods all day",
            "Apple added an iOS 27 AirPods listening feature; no new AirPods hardware is announced.",
            "9to5Mac",
        )
        groups = self.reconcile(
            [airpods_5, camera_delay, camera_translation, ios_feature],
            [[airpods_5, camera_delay, camera_translation, ios_feature]],
        )
        self.assertEqual(sorted(len(group) for group in groups), [1, 1, 2])
        self.assertTrue(
            any({article.title for article in group} == {camera_delay.title, camera_translation.title}
                for group in groups)
        )

    def test_epic_eu_fee_reaction_merges_across_source_wording(self):
        reports = [
            article_for(
                self.module,
                "Epic Games disagrees with Apple's 'junk' EU fee changes",
                "Epic criticized Apple's revised App Store fees and commercial terms in the European Union.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "EU Welcomes Apple's App Store Changes, Epic Slams 'Junk Fees'",
                "The Commission welcomed Apple's revised EU App Store fee structure while Epic objected.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Epic Games 强烈抨击苹果欧盟区应用商店新规，称其为新垃圾费用",
                "Epic 反对苹果调整后的欧盟 App Store 收费条款。",
                "cnBeta",
            ),
        ]
        groups = self.reconcile(reports)
        self.assertEqual(len(groups), 1)

    def test_third_party_desktop_app_owner_controls_relevance_and_merging(self):
        reports = [
            article_for(
                self.module,
                "Meta AI is getting a Mac app",
                "Meta is launching its own desktop app for Mac with screen sharing and dictation.",
                "The Verge",
            ),
            article_for(
                self.module,
                "Meta AI comes to Mac in a new desktop app",
                "Meta released a beta Mac app for its AI assistant.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Meta 推出 Meta AI 原生 Mac 应用：支持窗口共享、跨应用听写",
                "Meta 发布其自有 AI 助手的 macOS 桌面客户端。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")
        self.assertEqual(len(events[0].articles), 3)

    def test_third_party_desktop_app_owner_survives_headline_variants(self):
        reports = [
            article_for(
                self.module,
                "Meta AI Launches Mac App With Screen Sharing and Dictation",
                "Meta today launched a new Meta AI app for the Mac in beta.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Meta AI桌面端测试版登陆macOS 主打商务助手功能",
                "Facebook 母公司 Meta 旗下的 Meta AI 已推出 Mac 平台测试版。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")

    def test_home_hub_code_reports_merge_despite_title_perspective(self):
        reports = [
            article_for(
                self.module,
                "HomePad code suggests it'll act like a giant Apple Watch",
                "macOS code shows Widget Gallery and Smart Stack interfaces for HomePad.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple's home automation hardware will work more like an Apple Watch than a HomePod",
                "New macOS code says HomeHub uses Faces, widgets and Smart Stacks.",
                "AppleInsider",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "software_systems")

    def test_beats_owned_brand_spec_leaks_merge_across_chinese_titles(self):
        reports = [
            article_for(
                self.module,
                "苹果 Beats 360 头戴式耳机偷跑：主动降噪最高达 Beats Studio Pro 的 1.75 倍",
                "零售商页面曝光 Beats 360 的 ANC、IPX4 与可更换耳垫规格。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Beats 360头戴式耳机零售信息遭泄露 规格细节曝光",
                "苹果旗下 Beats 新品的零售页面曝光完整规格与 299 美元售价。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "hardware_products")

    def test_airpods_software_commentary_does_not_join_camera_hardware_claim(self):
        feature = article_for(
            self.module,
            "Apple is about to launch best reason yet to wear AirPods all day long",
            "With iOS 27, Siri AI and new software features make AirPods more useful all day.",
            "9to5Mac",
        )
        camera = article_for(
            self.module,
            "Apple's Camera AirPods Not Launching Until 2027 Despite Leaked Video",
            "Apple's camera-equipped AirPods hardware project has reportedly been delayed until 2027.",
            "MacRumors",
        )
        events = self.module.reconcile_articles(
            [feature, camera],
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[feature, camera]],
        )
        self.assertEqual(len(events), 2)

    def test_first_person_product_commentary_without_new_reporting_stays_weak(self):
        article = article_for(
            self.module,
            "Apple is about to launch best reason yet to wear AirPods all day long",
            (
                "AirPods are one of my favorite Apple products and I often wear them all day. "
                "The article recaps existing iOS 27 Siri features and a previously leaked "
                "camera-equipped AirPods video; I imagine the combination will be useful."
            ),
            "9to5Mac",
        )
        event = self.module.cluster_articles([article])[0]
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_versioned_camera_app_reports_merge_across_languages(self):
        reports = [
            article_for(
                self.module,
                "What's new with the Camera app in iOS 27",
                (
                    "Apple changed the stock Camera app in iOS 27 with Siri mode, "
                    "RAW 9 processing and Reference Images."
                ),
                "AppleInsider",
            ),
            article_for(
                self.module,
                "初探苹果 iOS 27 版相机应用：新 Siri 模式可估算食物卡路里等",
                "iOS 27 相机应用新增 Siri 模式、RAW 9，并整合 AI 参考图像模式。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual(len(events[0].articles), 2)

    def test_structured_code_report_does_not_project_generic_calendar_background(self):
        title = "Apple accidentally leaked more than 10 new products in macOS update"
        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            "The macOS resource list contains identifiers for several unreleased devices.",
            [
                "The code contains unreleased AirPods 5 identifiers for two new models.",
                "An unknown MacBook Pro model identifier also appears in the resource list.",
                "Apple's annual iPhone event takes place in September, so some products may appear next month.",
            ],
        )
        projected_titles = [variant_title for variant_title, _summary, _facts in variants]
        self.assertTrue(any("AirPods" in value for value in projected_titles))
        self.assertTrue(any("MacBook" in value for value in projected_titles))
        self.assertFalse(any("iPhone" in value for value in projected_titles))

    def test_unresolved_identifier_set_stays_one_aggregate_disclosure(self):
        title = "线索仍有限：苹果 macOS 26.7 RC 曝光多款未识别设备标识"
        facts = [
            "A3465 前后关联 A3464 和 A3466，其中 A3464 是 13 英寸 iPad Air。",
            "A3441 关联的 A3442 预估是面向中国市场的 15 英寸 MacBook Air。",
            "A3456、A3457 周围字符串涉及世界旅行适配器套装的不同版本。",
        ]
        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            "系统代码出现一批暂时无法对应公开产品的标识符。",
            facts,
        )
        self.assertEqual(variants, [(title, "系统代码出现一批暂时无法对应公开产品的标识符。", facts)])

    def test_historical_causal_retrospective_without_current_action_stays_weak(self):
        article = article_for(
            self.module,
            "苹果成功的隐秘金主：美中情局如何助推了 iPhone 诞生？",
            (
                "文章回顾 1986 年中情局如何资助 NeXT，并追溯这段历史如何间接影响 "
                "乔布斯回归苹果和后来 iPhone 的底层系统。"
            ),
            "cnBeta",
        )
        event = self.module.cluster_articles([article])[0]
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_first_party_code_and_owned_brand_actions_are_not_deferred(self):
        cases = [
            (
                "HomePad code suggests it'll act like a giant Apple Watch",
                "Apple's macOS code shows Widget Gallery and Smart Stack interfaces for the rumored HomePad.",
                "software_systems",
            ),
            (
                "苹果 Beats 360 头戴式耳机零售信息泄露",
                "电商页面曝光苹果旗下 Beats 360 的 ANC、IPX4 和可更换耳垫规格。",
                "hardware_products",
            ),
            (
                "苹果 macOS 26.7 RC 曝光多款未识别设备标识",
                "苹果系统代码包含多组尚未对应公开产品的设备型号，可能关联未发布 Mac 和 iPad。",
                "hardware_products",
            ),
        ]
        for title, summary, category in cases:
            with self.subTest(title=title):
                event = self.module.cluster_articles(
                    [article_for(self.module, title, summary, "IT之家")]
                )[0]
                self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
                self.assertEqual(event.category, category)

    def test_retailer_discount_and_third_party_archive_stay_deferred(self):
        cases = [
            (
                "Grab an iPad Air M4 for its lowest price since the June increase",
                "Amazon and Best Buy have the iPad Air on sale for $649, $100 below retail price.",
                "The Verge",
            ),
            (
                "The best look into Apple's past comes from this 'MacWeek' archive",
                "A third-party publication archive makes historical MacWeek issues available to browse.",
                "AppleInsider",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                event = self.module.cluster_articles(
                    [article_for(self.module, title, summary, source)]
                )[0]
                self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_weak_roundup_projection_cannot_be_repromoted_during_clustering(self):
        source_title = "Apple will launch 10 new products soon, with September event coming"
        projected_title = "Apple iPad roadmap update"
        summary = (
            "The 10 products above are the most likely to get September launches. "
            "Other possibilities include an iPad mini with OLED, a home security camera, "
            "and new Macs that are more likely for October."
        )
        article = article_for(self.module, projected_title, summary, "9to5Mac")
        article.relevance_tier, article.relevance_reason = (
            self.module.classify_projected_article_relevance(
                source_title,
                projected_title,
                summary,
                [summary],
                "9to5Mac",
            )
        )
        self.assertEqual(article.relevance_tier, "weak")
        event = self.module.cluster_articles([article])[0]
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)


if __name__ == "__main__":
    unittest.main()
