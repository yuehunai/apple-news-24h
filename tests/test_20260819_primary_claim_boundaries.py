import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260819_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    kind = module.detect_event_kind(title, summary, facts)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.event_category_from_metadata(title, summary, facts, kind),
        published_utc=datetime(2026, 8, 18, tzinfo=timezone.utc),
        published_raw="2026-08-18T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=kind,
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


class PrimaryClaimBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def cluster(self, articles):
        return self.module.cluster_articles(articles)

    def test_seed_without_shared_primary_claim_is_split(self):
        articles = [
            article_for(
                self.module,
                "Apple overhauls App Store fees in the EU with new unified terms",
                "Apple changed its EU fee structure and external-payment terms.",
            ),
            article_for(
                self.module,
                "Apple pulls AI nudify app promoted in Meta ads",
                "Apple removed the named app from the App Store after the advertising campaign was reported.",
            ),
            article_for(
                self.module,
                "Apple's US App Store commission revenue is down 18% this year",
                "A market report estimates a decline in US commission revenue.",
                "MacRumors",
            ),
        ]
        groups = self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[articles],
        )
        self.assertEqual(len(groups), 3)

    def test_siri_remote_refresh_merges_cross_language_and_stays_hardware(self):
        articles = [
            article_for(
                self.module,
                "New Apple TV 4K to have upgraded Siri Remote, per leak",
                "macOS code references a new physical Siri Remote for the next Apple TV.",
            ),
            article_for(
                self.module,
                "New Apple TV to Come With Upgraded Siri Remote",
                "Apple's next set-top box is expected to ship with an upgraded remote.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果新一代 Apple TV 4K 曝光，有望配备升级款 Siri Remote 遥控器",
                "系统代码指向一款将随新 Apple TV 推出的新实体遥控器。",
                "IT之家",
            ),
            article_for(
                self.module,
                "macOS Tahoe code hints at upcoming Siri Remote",
                "The ATVRemote identifier points to a new Siri Remote accessory.",
                "AppleInsider",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(len(events[0].articles), 4)

    def test_home_hub_widget_capability_merges_promotes_and_is_software(self):
        articles = [
            article_for(
                self.module,
                "Apple's Home Hub Will Have a Widget Gallery With iPhone Widget Support",
                "The first-party device UI will include Widget Gallery and Smart Stack.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "泄露代码暗示：苹果家庭中枢产品 Home Hub 将搭载小组件库",
                "macOS 文件显示苹果家庭中枢将支持小组件图库、智能叠放和 iPhone 小组件镜像。",
                "IT之家",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual(len(events[0].articles), 2)

    def test_apple_card_cashback_offer_merges_without_deferred_source(self):
        articles = [
            article_for(
                self.module,
                "Apple Card Offering 5% Cash Back on Select Purchases for Limited Time",
                "Apple is offering 5% Daily Cash through September 15.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 Apple Card 限时活动：指定消费可获 5% 返现",
                "苹果推出限时返现活动，指定商户消费可获 5% Daily Cash。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Apple Card adds 5% Daily Cash on travel, gas, and more",
                "Apple Card is making road trips more rewarding with a 5% Daily Cash offer.",
                "AppleInsider",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual(len(events[0].articles), 3)

    def test_app_store_terms_and_revenue_are_distinct_cohesive_events(self):
        articles = [
            article_for(
                self.module,
                "Apple overhauls App Store fees in the EU with new unified terms",
                "Apple changed EU app distribution fees and external-payment terms.",
            ),
            article_for(
                self.module,
                "New EU App Store terms lower both costs and bar to entry for external payments",
                "Apple published lower unified EU terms for external payments.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple's US App Store Commission Revenue Down 18% This Year",
                "A report estimates Apple's US commission revenue fell 18%.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "报告称 2026 苹果 App Store 在美国佣金收入同比下降 18%",
                "报告估算苹果美国 App Store 佣金收入同比下降 18%。",
                "IT之家",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(len(event.articles) for event in events), [2, 2])
        self.assertTrue(all(event.category == "software_systems" for event in events))

    def test_regulatory_services_impact_joins_same_commission_report(self):
        articles = [
            article_for(
                self.module,
                "苹果首次承认：各地监管机构的反垄断攻势已开始冲击公司服务业务",
                "苹果服务收入和利润率低于预期。",
                "IT之家",
                facts=[
                    "英国《金融时报》报道监管变化已冲击苹果服务业务。",
                    "Appfigures 估计美国 App Store 佣金收入下降 18%。",
                    "巴西和日本实施监管变化后也出现收入下滑。",
                ],
            ),
            article_for(
                self.module,
                "Apple's US App Store Commission Revenue Down 18% This Year",
                "Appfigures says US App Store commission revenue fell 18%.",
                "MacRumors",
                facts=[
                    "The figures follow Apple's admission that regulatory changes weighed on Services growth.",
                ],
            ),
            article_for(
                self.module,
                "Apple overhauls App Store fees in the EU with new unified terms",
                "Apple announced a separate new EU fee structure and external-payment terms.",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])
        merged = next(event for event in events if len(event.articles) == 2)
        self.assertNotIn("multiple region-specific markers", merged.merge_warnings)

    def test_non_apple_criminal_case_using_device_records_is_deferred(self):
        article = article_for(
            self.module,
            "Apple Watch data reveals final movements in murder trial",
            "Prosecutors used Apple Watch health records, iPhone call logs, and search history as evidence in a criminal trial.",
            "AppleInsider",
        )
        event = self.cluster([article])[0]
        self.assertEqual(event.relevance_tier, "weak")

    def test_exact_reconciled_claim_does_not_emit_background_region_warning(self):
        articles = [
            article_for(
                self.module,
                "Apple's US App Store Commission Revenue Down 18% This Year",
                "A report says regulation cut U.S. commission revenue and also affected Japan and Brazil.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple admits it may not make any commission from alternative app stores",
                "Apple's filing says regulatory changes can reduce App Store commission revenue worldwide.",
            ),
            article_for(
                self.module,
                "报告称 2026 苹果 App Store 在美国佣金收入同比下降 18%",
                "报告称美国收入下降，并以日本和巴西作为监管影响背景。",
                "IT之家",
            ),
        ]
        event = self.cluster(articles)[0]
        self.assertNotIn("multiple region-specific markers", event.merge_warnings)

    def test_sparse_official_source_joins_matching_primary_claim_group(self):
        articles = [
            article_for(
                self.module,
                "Apple overhauls App Store fees in the EU with new unified terms",
                "Apple changed EU app distribution fees and external-payment terms.",
            ),
            article_for(
                self.module,
                "New EU App Store terms lower costs for external payments",
                "The unified commercial terms replace the previous fee structure.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple announces changes for apps in the European Union",
                "Apple announced changes to its business terms for apps in the European Union.",
                "Apple Newsroom",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 3)

    def test_airpods_generation_identifiers_do_not_merge_with_camera_model(self):
        articles = [
            article_for(
                self.module,
                "Unreleased AirPods 5 Models Referenced in macOS 26.7",
                "Two identifiers point to standard and noise-cancelling AirPods 5 models.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 AirPods 5 耳机曝光，预估升级 H3 芯片",
                "系统代码出现两款 AirPods 5 型号标识。",
                "IT之家",
            ),
            article_for(
                self.module,
                "AirPods with cameras get their clearest leak yet",
                "A leaked demo shows camera-equipped AirPods using visual intelligence.",
            ),
            article_for(
                self.module,
                "苹果带摄像头的 AirPods 实机演示曝光，可实现环境视觉感知",
                "演示视频显示摄像头 AirPods 可识别环境并调用 Siri。",
                "IT之家",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(len(event.articles) for event in events), [2, 2])
        self.assertTrue(all(event.category == "hardware_products" for event in events))

    def test_camera_airpods_opinion_does_not_join_hardware_leak(self):
        leak = article_for(
            self.module,
            "AirPods with cameras get their clearest leak yet",
            "A macOS demo video shows camera-equipped AirPods using Visual Intelligence.",
        )
        opinion = article_for(
            self.module,
            "Security Bite: Apple's camera AirPods will make rival glasses look reckless",
            "A commentary argues that Apple's rumored product would compare favorably with a competitor.",
        )
        events = self.cluster([leak, opinion])
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(event.relevance_tier for event in events), ["strong", "weak"])

    def test_variable_aperture_reports_merge_by_model_and_component_action(self):
        articles = [
            article_for(
                self.module,
                "iPhone 18 Pro Max Rumored to Get Exclusive Camera Upgrade",
                "The larger model is expected to receive an exclusive camera upgrade.",
                "MacRumors",
                facts=["The exclusive upgrade is a variable-aperture main camera."],
            ),
            article_for(
                self.module,
                "Only the iPhone 18 Pro Max will get variable aperture",
                "The variable-aperture camera will be exclusive to the Pro Max.",
            ),
            article_for(
                self.module,
                "消息称苹果 iPhone 18 Pro Max 独占可变光圈升级",
                "可变光圈主摄将由 Pro Max 独享。",
                "IT之家",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 3)

    def test_legal_response_does_not_merge_with_regulatory_revenue_impact(self):
        articles = [
            article_for(
                self.module,
                "苹果反驳美国司法部反垄断案最新主张",
                "苹果向法院回应美国司法部在反垄断案件中的主张。",
                "IT之家",
            ),
            article_for(
                self.module,
                "反垄断打压开始侵蚀苹果服务业务",
                "各地监管行动正在冲击苹果服务收入。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "苹果首次承认监管攻势开始冲击公司服务业务",
                "苹果称反垄断监管已影响服务业务。",
                "IT之家",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])

    def test_editorial_opinion_and_its_third_party_utility_stay_deferred(self):
        articles = [
            article_for(
                self.module,
                "macOS 27 makes one design decision that I would change for MacBooks",
                "The author dislikes the new battery percentage layout and would change it.",
            ),
            article_for(
                self.module,
                "外媒用 AI 开发 macOS 27 工具，提高菜单栏电量可读性",
                "媒体编辑制作了一款可下载的第三方菜单栏工具，用于替代系统电池显示。",
                "IT之家",
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.relevance_tier == "weak" for event in events))

    def test_future_support_recap_stays_deferred_without_a_new_action(self):
        article = article_for(
            self.module,
            "Apple Wallet driver's license: which states are next?",
            "The article recaps states announced since 2021 and lists partners with unknown launch dates.",
        )
        event = self.cluster([article])[0]
        self.assertEqual(event.relevance_tier, "weak")

    def test_known_identifier_context_is_not_projected_as_new_product_roadmap(self):
        title = "Apple product identifier leak is a hard mystery to solve"
        summary = (
            "A3466 belongs to the already sold MagSafe Battery for iPhone Air. "
            "A3464 is a confirmed mainland-China M4 iPad Air model. "
            "Separate identifiers reference unreleased AirPods 5 models."
        )
        facts = [
            "A3466 belongs to the already sold MagSafe Battery for iPhone Air.",
            "A3464 is a confirmed mainland-China M4 iPad Air model.",
            "Two identifiers reference unreleased AirPods 5 models.",
        ]
        variants = self.module.compound_article_variants(title, summary, facts)
        projected_titles = {item[0] for item in variants}
        self.assertNotIn("Apple iPhone roadmap update", projected_titles)
        self.assertNotIn("Apple iPad roadmap update", projected_titles)
        self.assertTrue(any("AirPods" in item for item in projected_titles))

    def test_first_party_activity_challenge_is_software(self):
        article = article_for(
            self.module,
            "National Parks Apple Watch Activity Challenge Launching August 23",
            "Apple invites Apple Watch users to earn a limited-edition Fitness badge by completing a workout.",
            "MacRumors",
        )
        event = self.cluster([article])[0]
        self.assertEqual(event.relevance_tier, "strong")
        self.assertEqual(event.category, "software_systems")

    def test_non_apple_browser_progress_using_safari_as_benchmark_is_weak(self):
        article = article_for(
            self.module,
            "1 个月性能提升约 12 倍：浏览器引擎新血液 Ladybird 加速追赶 Chrome 和 Safari",
            "Ladybird 团队通过 Rust 重构提升自有浏览器引擎性能，Safari 只作为性能比较对象。",
            "IT之家",
        )
        event = self.cluster([article])[0]
        self.assertEqual(event.relevance_tier, "weak")

    def test_same_app_store_removal_keeps_structured_cross_source_evidence(self):
        articles = [
            article_for(
                self.module,
                "Apple pulls AI 'nudify' app promoted in Meta ads",
                "Meta ran ads for an App Store app that Apple later pulled.",
                "9to5Mac",
                facts=[
                    "After WIRED contacted both companies, Apple removed the app and Meta ended the 32-ad campaign."
                ],
            ),
            article_for(
                self.module,
                "AI 换脸色情 App 营销引争议：Meta 下架广告、苹果移除应用",
                "Kromix 投放争议广告后，Meta 已删广告，苹果已将该 App 下架。",
                "IT之家",
                facts=[
                    "外媒 WIRED 联系双方后，苹果移除应用，Meta 结束共 32 则广告的投放。"
                ],
            ),
        ]
        events = self.cluster(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_current_versioned_builtin_app_changes_override_roundup_form(self):
        article = article_for(
            self.module,
            "What's new with the Camera app in iOS 27",
            "In iOS 27, Apple is bringing a new set of changes to the stock Camera app.",
            "AppleInsider",
            facts=[
                "Apple moved Visual Intelligence into a first-party Siri mode and redesigned Camera controls."
            ],
        )
        event = self.cluster([article])[0]
        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "software_systems")


if __name__ == "__main__":
    unittest.main()
