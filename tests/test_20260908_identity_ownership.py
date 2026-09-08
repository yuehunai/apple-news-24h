import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apple_news_core.event_identity import (
    build_event_identity,
    is_apple_led_developer_submission_story,
)


class IdentityOwnership20260908Tests(unittest.TestCase):
    def test_first_party_app_ownership_survives_unprefixed_title(self):
        import apple_news_24h as crawler

        for name in ("Journal", "Canvas"):
            title = f"{name} app arrives on the App Store"
            lead = f"Apple today released its new first-party {name} application for iPad."
            with self.subTest(name=name):
                self.assertEqual(build_event_identity(title, lead).scope, "apple-direct")
                self.assertEqual(crawler.classify_relevance_tier(title, lead, [], "9to5Mac")[0], "strong")

    def test_other_apple_app_release_cannot_supply_named_app_ownership(self):
        title = "Example Relay app arrives on the App Store"
        lead = "Apple today released its new first-party Journal application for iPad."
        self.assertEqual(build_event_identity(title, lead).scope, "third-party-context")

    def test_app_release_object_allows_apposition_and_chinese_ownership(self):
        import apple_news_24h as crawler

        for title, lead in (
            ("Journal app arrives on the App Store", "Apple has released Journal, its new first-party app, for iPad."),
            ("日记应用正式上架App Store", "苹果今天发布了自研的日记应用，首次支持iPad。"),
            ("Canvas app arrives on the App Store", "Apple has released Canvas, its new first-party app, for iPad."),
        ):
            with self.subTest(title=title):
                self.assertEqual(build_event_identity(title, lead).scope, "apple-direct")
                self.assertEqual(crawler.classify_relevance_tier(title, lead, [], "9to5Mac")[0], "strong")

    def test_app_ownership_requires_same_release_object_and_positive_predicate(self):
        for title, lead in (
            ("Journal app arrives on the App Store", "Apple has released Notes, its new first-party app. Journal is a third-party app."),
            ("Journal app arrives on the App Store", "Apple has not released Journal, a third-party app."),
            ("日记应用正式上架App Store", "苹果今天发布了自研的备忘录应用。日记由另一家公司开发。"),
            ("日记应用正式上架App Store", "苹果今天尚未发布日记应用。"),
        ):
            with self.subTest(lead=lead):
                self.assertEqual(build_event_identity(title, lead).scope, "third-party-context")

    def test_announcement_with_attributed_judgment_remains_news(self):
        import apple_news_24h as crawler

        title = "Apple announces new privacy feature, says tracking users is a bad idea"
        for lead in (
            "Apple today announced a new privacy feature that blocks tracking.",
            "The company today announced a new privacy feature that blocks tracking.",
        ):
            with self.subTest(lead=lead):
                self.assertEqual(build_event_identity(title, lead).content_form, "news")
                self.assertEqual(crawler.classify_relevance_tier(title, lead, [], "9to5Mac")[0], "strong")

    def test_editorial_judgment_of_announced_feature_stays_analysis(self):
        title = "Apple announces new privacy feature, but blocking tracking is a bad idea"
        lead = "Apple today announced a new privacy feature that blocks tracking."
        self.assertEqual(build_event_identity(title, lead).content_form, "analysis")

    def test_chinese_web_submission_terminology_matches_current_call(self):
        title = "苹果公开征集 Interop 2027 提案：遏制网页“变脸”，减少换个浏览器就变样问题"
        for lead in (
            "科技媒体9to5Mac报道称苹果WebKit团队启动Interop2027议题征集，"
            "目标是在不同浏览器中让同一现代Web技术获得更一致的支持，"
            "覆盖15个影响Web开发的关键兼容性领域，并收集社区建议。",
            "WebKit团队收集社区建议，改善Web开发中的跨浏览器兼容性。",
            "WebKit邀请网页开发社区提交议题，提升不同浏览器之间的兼容性。",
        ):
            with self.subTest(lead=lead):
                self.assertTrue(is_apple_led_developer_submission_story(title, lead))

    def test_web_community_terms_do_not_relax_submission_ownership(self):
        lead = "WebKit团队收集社区建议，改善Web开发中的跨浏览器兼容性。"
        for title in (
            "第三方组织公开征集 Interop 2027 提案",
            "回顾苹果公开征集 Interop 2022 提案",
            "苹果曾公开征集 Interop 2022 提案",
            "苹果未公开征集 Interop 2027 提案",
            "苹果介绍 Interop 2027 浏览器兼容性",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_apple_led_developer_submission_story(title, lead))
        self.assertFalse(is_apple_led_developer_submission_story(
            "苹果公开征集社区建议", "社区建议关注WebKit宣传材料和浏览器图标的配色。",
        ))

    def test_named_app_store_arrival_is_third_party_not_lead_device_action(self):
        for title in (
            "星河互联 App 登陆 App Store",
            "示例互联应用正式上架苹果 App Store",
            "Example Relay app arrives on the App Store",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, "HarmonyOS 7 尚未支持 Apple Watch 消息转发。")
                self.assertEqual(identity.scope, "third-party-context")
                self.assertEqual(identity.action_owner, "third-party")

    def test_apple_owned_app_release_is_not_third_party_arrival(self):
        for title in (
            "苹果发布全新日记应用，正式上架 App Store",
            "Apple releases a new Journal app on the App Store",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, "Apple today released its new app.")
                self.assertEqual(identity.scope, "apple-direct")
                self.assertEqual(identity.content_form, "news")

    def test_buyer_guidance_is_not_news(self):
        for title in (
            "iPhone 18 Pro: Nine Reasons Not to Upgrade This Year",
            "Desktop Mac buyer's gude: Which Mac to buy in fall 2026",
            "iPad buyer's guide: Which tablet to buy this spring",
            "AirPods: Five reasons to upgrade this year",
        ):
            with self.subTest(title=title):
                self.assertEqual(build_event_identity(title, "").content_form, "buying_advice")

    def test_editorial_judgments_are_analysis(self):
        for title in (
            "Reports describe two ways for Apple to make more money; only one is good",
            "Trying to squeeze more profit out of the App Store is a bad idea",
            "Before iPhone 18 Pro event, carriers don't know any more than you do",
            "'Cupertino' legal drama doesn't represent region demographics, landmarks, or reality",
            "Apple's pricing strategy is a terrible idea",
            "'Harbor Lights' comedy fails to capture the reality of family life",
        ):
            with self.subTest(title=title):
                self.assertEqual(build_event_identity(title, "").content_form, "analysis")

    def test_evidence_noun_is_not_a_competitor(self):
        for subject in ("Leak", "Leaked code", "Firmware", "Patent filing", "Support document"):
            with self.subTest(subject=subject):
                identity = build_event_identity(
                    f"{subject} Hints at Four New Features for Apple Watch Series 12 and Ultra 4",
                    "New code reveals Apple is developing satellite connectivity for Apple Watch.",
                )
                self.assertEqual(identity.scope, "apple-direct")
                # Disclosure alone supplies no headline action predicate.
                self.assertEqual(identity.action_owner, "unknown")
                self.assertEqual(identity.content_form, "news")

    def test_competitor_evidence_is_not_first_party(self):
        for subject in ("Pixel leak", "Leaked Pixel code", "Samsung patent filing", "Huawei firmware"):
            with self.subTest(subject=subject):
                identity = build_event_identity(
                    f"{subject} hints at what Apple's iPhone could offer",
                    "Apple is developing its next phone, but this report describes a competitor's product.",
                )
                self.assertEqual(identity.scope, "third-party-context")

    def test_competitor_purchase_and_leadership_claims_are_context(self):
        for title in (
            "余承东：建议苹果用户买华为阔直板当备用机 备用几天就可能成为主力机",
            "苹果iPhone 18 Pro Max也要跟进了！余承东称华为引领可变光圈技术创新",
            "建议iPhone用户购买三星手机当备用机",
            "苹果也要跟进了！雷军称小米引领相机技术创新",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, "")
                self.assertEqual(identity.scope, "third-party-context")
                self.assertEqual(identity.action_owner, "third-party")

    def test_actual_apple_disclosures_remain_news(self):
        for title, lead in (
            ("苹果iPhone 18 Pro将采用可变光圈，华为此前已使用", "供应链新报告披露苹果相机组件规格。"),
            ("苹果采用三星OLED面板", "苹果与三星签订显示面板供应协议。"),
            ("Apple announces new App Store fees", "Apple today announced a new pricing policy."),
            ("Apple releases trailer for 'Cupertino' legal drama", "Apple TV today shared a new trailer."),
            ("Apple updates Mac buyer's guide with new specifications", "Apple published revised specifications today."),
            ("Leaked iPhone code reveals four new camera features", "New code reveals a revised sensor."),
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, lead)
                self.assertEqual(identity.scope, "apple-direct")
                self.assertEqual(identity.content_form, "news")

    def test_component_supply_contract_is_sourcing(self):
        for title, component in (
            ("打破惯例！苹果或签铠侠NAND长期协议：3到5年合约无价格上限", "memory"),
            ("苹果或签铠侠NAND长期协议 3到5年合约无价格上限", "memory"),
            ("苹果签订显示面板供应协议", "display"),
            ("苹果与供应商达成闪存采购合约", "memory"),
            ("Apple signs a NAND supply agreement with Kioxia", "memory"),
            ("Apple enters into a long-term supply contract for OLED panels", "display"),
            ("Kioxia signs a NAND supply agreement with Apple", "memory"),
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, "")
                self.assertIn(f"component-supplier-sourcing:{component}", identity.title_components)

    def test_unrelated_contracts_are_not_component_sourcing(self):
        for title, lead in (
            ("苹果签订NAND专利诉讼和解协议", ""),
            ("Apple signs a legal settlement over NAND patents", ""),
            ("Apple signs a software subscription contract", "The software tracks NAND inventory."),
            ("苹果签订软件订阅合同", "该服务管理显示面板库存。"),
            ("Apple signs a new agreement", "NAND supply prices rose today."),
            ("Samsung signs a NAND supply agreement as Apple watches", ""),
            ("三星签订NAND供应协议，苹果尚未参与", ""),
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, lead)
                self.assertNotIn("component-supplier-sourcing", identity.components)


if __name__ == "__main__":
    unittest.main()
