import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260824_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source, *, url=None, facts=None, tier=None, reason=None):
    facts = list(facts or [])
    observed_tier, observed_reason = module.classify_relevance_tier(
        title,
        summary,
        facts,
        source,
    )
    return module.Article(
        source=source,
        url=url or f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 24, tzinfo=timezone.utc),
        published_raw="2026-08-24T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier or observed_tier,
        relevance_reason=reason if reason is not None else observed_reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class StructuralEventOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_external_evaluation_of_one_unreleased_product_merges_across_wording(self):
        reports = [
            article_for(
                self.module,
                "Some people outside of Apple have already used the folding iPhone",
                "Bloomberg reports that early testers praised the hinge and large inner display but missed a telephoto camera.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "iPhone Ultra: what people who've used it like most",
                "People outside Apple who handled the unreleased foldable liked its hinge and display but criticized the camera tradeoff.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "消息称苹果外部已有人体验过折叠屏 iPhone：屏幕铰链评价积极，但缺少长焦镜头",
                "据彭博社报道，早期体验者对同一未发布折叠屏 iPhone 的铰链和内屏评价积极。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Gurman: iPhone Ultra Wows Early Testers, Except for Its Camera",
                "The same Bloomberg report says external testers liked the foldable iPhone except for its lack of a telephoto camera.",
                "MacRumors",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(len(events[0].articles), 4)

    def test_retail_layout_preparation_for_home_launches_is_one_action(self):
        reports = [
            article_for(
                self.module,
                "Apple Stores preparing 'significant' changes for new Home product launches",
                "Apple is rearranging retail display areas before upcoming Home product launches.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Retail Stores Preparing for New Home Product Launches",
                "Apple retail stores are changing their internal display layout for new Home products.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果零售店布局即将调整，为一系列新的家庭设备做准备",
                "门店大道区将重新排列并增加展示位，以迎接新的家庭设备。",
                "IT之家",
            ),
            article_for(
                self.module,
                "备战新品：苹果零售店大改版，新增智能家居展区",
                "苹果零售团队正在调整产品陈列，为智能家居设备上市做准备。",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].category, "hardware_products")

    def test_retail_operation_page_does_not_project_background_product_roadmaps(self):
        facts = [
            "Apple is rearranging retail display areas for upcoming Home products.",
            "An Apple TV and HomePod mini refresh are expected later this year.",
            "A separate seven-inch home hub is rumored for a later launch.",
        ]

        variants = self.module.compound_article_variants(
            "苹果零售店重组内部布局，全面迎接全新智能家居产品上市",
            " ".join(facts),
            facts,
        )

        self.assertEqual(len(variants), 1, variants)

    def test_price_forecast_and_event_preview_split_even_when_seeded_together(self):
        price = article_for(
            self.module,
            "It's anyone's guess how high iPhone prices might go, but $100 might be enough",
            "A report estimates that iPhone 18 Pro prices could rise by $100.",
            "AppleInsider",
        )
        event_preview = article_for(
            self.module,
            "苹果发布会举办时间本周官宣，三款 iPhone 集中亮相",
            "多位博主预计苹果将在本周公布发布会时间，活动可能在 9 月 9 日举行。",
            "cnBeta",
        )

        groups = self.module.reconcile_articles(
            [price, event_preview],
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[price, event_preview]],
        )

        self.assertEqual(len(groups), 2, [[article.title for article in group] for group in groups])

    def test_policy_constrained_component_procurement_is_hardware(self):
        article = article_for(
            self.module,
            "美国考虑放行苹果采购中国存储产品，仅限中国市场设备使用",
            "美国政府正考虑批准苹果采购中国厂商的存储产品，以缓解设备存储器供应压力。",
            "快科技",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong")
        self.assertEqual(event.category, "hardware_products")

    def test_non_apple_product_with_comparison_context_stays_weak(self):
        articles = [
            article_for(
                self.module,
                "三星 Galaxy S27 Ultra 渲染图出炉：横向镜组撞脸 iPhone",
                "三星调整 Galaxy S27 Ultra 的相机设计，iPhone 仅用于外观比较。",
                "快科技",
            ),
            article_for(
                self.module,
                "黄仁勋亲签 RTX Pro 6000 Blackwell 拍出 5.7 万美元",
                "英伟达显卡在一场同时包含 Apple-1 的拍卖会上成交。",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertTrue(events)
        self.assertTrue(
            all(event.relevance_tier == "weak" for event in events),
            [(event.title, event.relevance_tier, event.relevance_reason) for event in events],
        )

    def test_structured_profile_demotes_legacy_background_false_positive(self):
        article = article_for(
            self.module,
            "黄仁勋亲签 RTX Pro 6000 Blackwell 拍出 5.7 万美元",
            "英伟达显卡在一场同时包含 Apple-1 的拍卖会上成交。",
            "快科技",
            tier="strong",
            reason="legacy Apple auction background match",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_attributed_strategy_commentary_without_new_action_stays_weak(self):
        article = article_for(
            self.module,
            "古尔曼：中国折叠机占全球半壁江山，苹果得打好硬件和身份两张牌",
            "文章分析中国折叠屏市场份额，并建议苹果应如何竞争，没有披露新的产品动作。",
            "cnBeta",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_direct_beta_asset_disclosure_recovers_from_legacy_weak_tier(self):
        article = article_for(
            self.module,
            "How Apple leaked product plans and even a video in a beta",
            "A macOS release candidate accidentally included future product identifiers and a product video when test branches were combined.",
            "AppleInsider",
            tier="weak",
            reason="legacy editorial classifier",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)

    def test_beta_asset_disclosure_merges_product_first_and_cause_first_reports(self):
        reports = [
            article_for(
                self.module,
                "How Apple leaked product plans and even a video in a beta",
                "A macOS release candidate accidentally included future product identifiers and a product video when test branches were combined.",
                "AppleInsider",
                tier="weak",
                reason="legacy editorial classifier",
            ),
            article_for(
                self.module,
                "揭秘苹果摄像头版 AirPods 为何泄露：可能是测试新功能时合并错误",
                "苹果发布 macOS RC 时意外泄露了 AirPods 演示视频和 Home Hub 等未公布产品信息，原因是内部测试分支被错误合并。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")

    def test_current_attributed_product_roadmap_recovers_from_legacy_weak_tier(self):
        article = article_for(
            self.module,
            "古尔曼：苹果新款 iMac 今年推出，搭载 M6 芯片并增加新配色",
            "据彭博社报道，新款 M6 iMac 预计年底前推出，并增加新的配色选项。",
            "IT之家",
            tier="weak",
            reason="legacy editorial classifier",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_exact_generation_refresh_identity_survives_one_legacy_weak_member(self):
        reports = [
            article_for(
                self.module,
                "M6 iMac Coming This Year in New Colors",
                "Apple is expected to release an M6 iMac in new colors later this year.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Report: Apple launching updated iMac with M6 chip and new colors later this year",
                "A current report says the M6 iMac refresh will arrive before year end.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果 M6 iMac 预计将于年底前发布，或迎超短生命周期",
                "报道称苹果将在年底前推出 M6 iMac，机身设计不变。",
                "cnBeta",
                tier="weak",
                reason="legacy editorial classifier",
            ),
        ]

        event = self.module.cluster_articles(reports)

        self.assertEqual(len(event), 1, [(item.title, len(item.articles)) for item in event])
        self.assertEqual({article.source for article in event[0].articles}, {"MacRumors", "9to5Mac", "cnBeta"})

    def test_speculative_price_commentary_stays_weak_even_with_concrete_numbers(self):
        article = article_for(
            self.module,
            "It's anyone's guess how high iPhone prices might go, but $100 might be enough",
            "The commentary reviews existing price increases and speculates that a future iPhone could rise by $100.",
            "AppleInsider",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)


if __name__ == "__main__":
    unittest.main()
