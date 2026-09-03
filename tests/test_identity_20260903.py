import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apple_news_core.event_identity import build_event_identity


class Identity20260903Tests(unittest.TestCase):
    def test_historical_product_comparison_is_not_a_current_leadership_action(self):
        for title in (
            "网友发现：某位苹果 CEO 任期的第一台和最后一台 iPhone 都是相同刷新率",
            "The first and last iPads during Apple's CEO tenure still have the same port",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(
                    title,
                    "Apple has appointed a new CEO. Readers compare specifications of products released years apart.",
                )
                self.assertEqual(identity.content_form, "analysis")

    def test_current_apple_announcement_with_historical_comparison_remains_news(self):
        identity = build_event_identity(
            "Apple announces a new iPad port, unlike the first and last models of the previous CEO tenure",
            "Apple today announced a new connector. Previous generations used the same port.",
        )
        self.assertEqual(identity.content_form, "news")

    def test_temporal_background_preserves_first_party_maps_scope(self):
        identity = build_event_identity(
            "继谷歌地图后，苹果地图面向美国用户将安大略湖更名为“美国湖”",
            "继特朗普签署行政命令后，苹果已面向美国用户在地图应用中更改安大略湖的名称为“美国湖”（Lake America），加拿大用户仍可看到原名。",
        )
        self.assertEqual(identity.scope, "apple-direct")
        self.assertEqual(identity.content_form, "news")
        self.assertIn("feature-change", identity.title_actions)

    def test_temporal_background_does_not_assign_competitor_action_to_apple(self):
        identity = build_event_identity(
            "继苹果地图后，谷歌地图推出新功能",
            "谷歌今天更新其地图服务，苹果地图的旧功能只是背景。",
        )
        self.assertNotEqual(identity.action_owner, "apple")

    def test_leaked_first_party_parts_are_not_a_competitor_action(self):
        for product in ("iPhone 18 Pro", "iPad Pro", "MacBook Pro"):
            for attribution in ("SonnyDickson", "ExampleReporter"):
                for suffix in ("", " - Apple iPhone - cnBeta.COM"):
                    with self.subTest(product=product, attribution=attribution, suffix=suffix):
                        identity = build_event_identity(
                            f"泄露的{product}零部件暗示将推出三种机身配色" + suffix,
                            f"爆料者{attribution}分享了不同颜色SIM零部件照片，称这些部件属于苹果即将推出的{product}。",
                        )
                        self.assertEqual(identity.scope, "apple-direct")
                        self.assertEqual(identity.action_owner, "apple")

    def test_competitor_leak_stays_third_party(self):
        identity = build_event_identity(
            "Leaked Pixel parts hint at what Apple's iPhone could offer",
            "Google is developing a new phone. Apple is mentioned only as a comparison.",
        )
        self.assertEqual(identity.scope, "third-party-context")
        self.assertEqual(identity.action_owner, "third-party")

    def test_single_subject_report_is_not_a_roundup_due_to_punctuation(self):
        identity = build_event_identity(
            "A20 Pro 芯片爆料：升级 7 核 GPU，苹果 iPhone 18 Pro / Max 首发",
            "数码博主于 8 月 30 日发布微博，通过焊点图反推苹果 A20 Pro 的内部结构。"
            "根据成品图，小核 L2 从 6MB 增加至 8MB，7 核 GPU 最符合布局。"
            "海外博主据此预估图形性能可能提升 28%。",
        )
        self.assertEqual(identity.content_form, "news")
        self.assertEqual(identity.scope, "apple-direct")

    def test_single_report_rule_is_not_specific_to_chip_or_model(self):
        for title in (
            "苹果相机爆料：新传感器增加读出速度，专业版首发",
            "New sensor leak: Faster readout, coming to Apple's camera",
            "Apple sensor rumor: Faster readout, coming to the next camera",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(title, "A new component photo supports a specific hardware report.")
                self.assertEqual(identity.content_form, "news")

    def test_source_date_does_not_decide_report_structure(self):
        for date in ("8 月 30 日", "9 月 3 日"):
            with self.subTest(date=date):
                identity = build_event_identity(
                    "A20 Pro 芯片爆料：升级 7 核 GPU，苹果手机首发",
                    f"博主于 {date} 发布芯片布局研究。本文转述该单一来源的推论，未提供新的测量。",
                )
                self.assertEqual(identity.content_form, "news")

    def test_explicit_old_rumor_collections_stay_roundups(self):
        for title in (
            "苹果新品爆料汇总：相机升级，平板换屏",
            "iPhone rumors: Smaller Dynamic Island, more RAM",
            "苹果芯片爆料：核心变化，缓存变化",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(
                    title,
                    "文章汇总此前的传闻与报道，没有新增消息。",
                )
                self.assertEqual(identity.content_form, "roundup")

    def test_current_official_video_is_not_the_historical_incident(self):
        identity = build_event_identity(
            "'I Wouldn't Be Talking to You': Apple Shares Apple Watch Survival Story",
            "Apple today shared a short video featuring an Apple Watch user named Amanda "
            "who says her device saved her life. In 2024, Amanda began receiving alerts "
            "about an abnormal heart rate.",
        )
        self.assertEqual(identity.content_form, "news")
        self.assertEqual(identity.action_owner, "apple")
        self.assertIn("official-communication", identity.title_actions)
        self.assertNotIn("i-wouldn", identity.title_named_subjects)

    def test_actual_single_user_workaround_stays_anecdotal(self):
        identity = build_event_identity(
            "One user fixes broken MacBook with a home-made workaround",
            "One user repairs a damaged screen with an old device, without any Apple announcement.",
        )
        self.assertEqual(identity.content_form, "user_anecdote")

    def test_quoted_mixed_case_feature_name_is_title_identity(self):
        for name, slug in (("iPhone Handoff", "iphone-handoff"), ("eDevice Relay", "edevice-relay")):
            with self.subTest(name=name):
                identity = build_event_identity(
                    f"iOS 27 Introduces New '{name}' Feature",
                    f'Apple has added a new "{name}" feature. The WWDC PPT listed hundreds of features.',
                )
                self.assertIn(slug, identity.title_named_subjects)
                self.assertIn(slug, identity.named_subjects)
                self.assertNotIn("ppt", identity.title_named_subjects)

    def test_explicit_lead_names_and_title_acronyms_are_preserved(self):
        identity = build_event_identity(
            "Apple adds XYZ support to iOS",
            'Apple calls the new feature "XYZ Relay".',
        )
        self.assertIn("xyz", identity.title_named_subjects)
        self.assertIn("xyz-relay", identity.named_subjects)

    def test_quotes_adjacent_to_chinese_text_still_extract_names(self):
        identity = build_event_identity(
            "苹果发布“Harbor Lights”预告片",
            "苹果上线新影片的预告片。",
        )
        self.assertIn("harbor-lights", identity.title_named_subjects)

    def test_chip_prefixed_feature_preview_is_a_roundup(self):
        identity = build_event_identity(
            "M6 MacBook Pro: Three new upgrades launching this fall",
            "Now that the M6 chip has officially been unveiled, here are three upgrades "
            "to expect from the new MacBook Pro. The author extrapolates from the existing chip.",
        )
        self.assertEqual(identity.content_form, "roundup")

    def test_explanatory_opinion_is_not_new_product_reporting(self):
        identity = build_event_identity(
            "Siri AI won't be your friend, and here's why that really matters",
            "A university survey vindicates Apple's careful decision about AI relationships.",
        )
        self.assertEqual(identity.content_form, "analysis")

    def test_speculative_launch_preview_with_old_rumors_is_a_roundup(self):
        identity = build_event_identity(
            "Apple's smart home display could be coming soon, sounds amazing",
            "Apple's new smart home display could be launching soon. Here's what the rumors "
            "say will be coming, and when. A lot of what we've been hearing isn't exactly new.",
        )
        self.assertEqual(identity.content_form, "roundup")

    def test_release_question_without_new_reporting_is_a_preview(self):
        identity = build_event_identity(
            "When is Apple releasing new AirPods?",
            "Apple is planning updates. Here's what to expect from the lineup and when to buy.",
        )
        self.assertNotEqual(identity.content_form, "news")
        self.assertNotEqual(identity.action_owner, "apple")

    def test_current_original_supply_chain_report_survives_preview_language(self):
        for title in (
            "M6 MacBook Pro: Three new upgrades launching this fall",
            "Apple's smart home display could be coming soon",
            "When is Apple releasing new AirPods?",
        ):
            with self.subTest(title=title):
                identity = build_event_identity(
                    title,
                    "A new report today from a supplier says Apple will launch the device "
                    "in October. Production has begun with a revised shipment target.",
                )
                self.assertEqual(identity.content_form, "news")

    def test_current_supply_chain_attribution_does_not_require_exact_new_report_phrase(self):
        identity = build_event_identity(
            "MacBook Pro: Three new upgrades launching this fall",
            "A new supply-chain report says Apple will launch the device in October. "
            "The supplier has started production with a revised shipment target.",
        )
        self.assertEqual(identity.content_form, "news")

    def test_future_commitment_judgment_is_analysis(self):
        identity = build_event_identity(
            "AI will be the defining test of Apple's environmental commitments",
            "Greenpeace says the adoption of AI poses the biggest threat to Apple's environmental "
            "track record, and argues that data center demands could change that record.",
        )
        self.assertEqual(identity.content_form, "analysis")

    def test_multi_product_sneak_preview_is_a_roundup(self):
        for title in ("苹果新品发布会剧透：五大旗舰抢先看", "苹果新机前瞻：三款产品提前看"):
            with self.subTest(title=title):
                identity = build_event_identity(
                    title,
                    "苹果发布会越来越近了，按照目前曝光的消息，手机、手表和耳机可能轮番登场。",
                )
                self.assertEqual(identity.content_form, "roundup")

    def test_customer_demo_device_usage_is_not_a_corporate_policy_announcement(self):
        identity = build_event_identity(
            "苹果多家体验店成中小学生免费网吧！门店称无权劝阻或赶走",
            "苹果、华为等数码门店里，中小学生长时间占用展示样机玩游戏。"
            "门店工作人员表示没有权利驱赶，只能等待孩子自行离开。",
        )
        self.assertEqual(identity.content_form, "user_anecdote")
        self.assertNotEqual(identity.action_owner, "apple")

    def test_formal_retail_policy_change_is_still_news(self):
        identity = build_event_identity(
            "苹果宣布调整门店样机使用政策",
            "此前中小学生长时间占用展示样机，门店工作人员表示没有权利驱赶。"
            "苹果今天发布了新的门店政策。",
        )
        self.assertEqual(identity.content_form, "news")
        self.assertEqual(identity.action_owner, "apple")

    def test_current_independent_supplier_report_is_not_generic_commentary(self):
        identity = build_event_identity(
            "Trust fall: TSMC's relationship with Apple is something Intel struggles to match",
            "Intel's loss of Apple's chip custom was due to Apple trusting TSMC more. "
            "Apple transitioned to its own chips in 2020. According to a report by Culpium "
            "released on Wednesday, Intel told equipment vendors Apple was already its client "
            "to secure manufacturing capacity before Apple committed to orders.",
        )
        self.assertEqual(identity.content_form, "news")

    def test_bare_product_navigation_has_no_authoritative_action(self):
        for title in ("iPhone", "Apple Maps", "泄露的iPhone"):
            with self.subTest(title=title):
                identity = build_event_identity(title, "")
                self.assertFalse(identity.title_actions)
                self.assertEqual(identity.action_owner, "unknown")


if __name__ == "__main__":
    unittest.main()
