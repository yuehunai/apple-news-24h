import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260831_test", SCRIPT_PATH)
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
        published_utc=datetime(2026, 8, 31, tzinfo=timezone.utc),
        published_raw="2026-08-31T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


def partitions(events):
    return {
        frozenset(article.title for article in event.articles)
        for event in events
    }


class StructuredEventRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_seed_split_is_symmetric_for_product_roadmap_and_leadership_action(self):
        roadmap = article_for(
            self.module,
            "Beyond iPhone 18 Pro: AirPods 5 in September, iPad Mini With OLED Display in October",
            "AirPods 5 will arrive in September. Apple expects an OLED iPad mini by the end of October.",
            "MacRumors",
        )
        leadership = article_for(
            self.module,
            "库克卸任倒计时，新任 CEO 特努斯签名苹果员工 5 周年纪念牌",
            "苹果员工纪念牌已改用新任 CEO 特努斯签名，既定交接即将执行。",
            "IT之家",
        )
        for order in permutations([roadmap, leadership]):
            groups = self.module.reconcile_articles(
                list(order),
                profile_for=self.module.article_reconciliation_profile,
                initial_groups=[list(order)],
            )
            self.assertEqual(len(groups), 2)

    def test_partner_facility_action_does_not_merge_with_product_feature_report(self):
        watch = article_for(
            self.module,
            "New Apple Watch Series 12 and Apple Watch Ultra 4 Features Revealed",
            "Apple is testing continuous heart-rate monitoring and new ceramic finishes.",
            "MacRumors",
        )
        facility = article_for(
            self.module,
            "苹果与康宁在美国肯塔基州开设创新中心：探索全新玻璃材料，新增数百个岗位",
            "苹果与康宁将建设创新中心和玻璃产线，为未来 iPhone 和 Apple Watch 供货。",
            "IT之家",
        )
        groups = self.module.reconcile_articles(
            [watch, facility],
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[watch, facility]],
        )
        self.assertEqual(len(groups), 2)
        facility_profile = self.module.article_reconciliation_profile(facility)
        self.assertEqual(facility_profile.category_hint, "hardware_products")

    def test_accessory_compatibility_evaluation_merges_cross_language_reports(self):
        reports = [
            article_for(
                self.module,
                "Apple Pencil for iPhone Ultra Was Tested",
                "Apple built and tested a shorter magnetic Pencil for its foldable iPhone prototype, but it is not expected to ship.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "消息称苹果曾为折叠屏 iPhone 测试触控笔：可磁吸在手机侧面，但量产机可能无缘",
                "苹果曾测试折叠 iPhone 专用手写笔，但量产版本预计不会支持。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果折叠屏iPhone正在测试手写笔：乔布斯当年最嫌弃的配件回归",
                "苹果正在测试折叠屏 iPhone 专用触控笔，量产计划尚未确定。",
                "快科技",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_component_adoption_merges_and_multi_product_report_projects_actions(self):
        title = "Beyond iPhone 18 Pro: AirPods 5 in September, iPad Mini With OLED Display in October"
        summary = (
            "AirPods 5 will be released in September alongside Apple's fall lineup. "
            "Apple also expects an iPad mini with an OLED display to launch by the end of October."
        )
        variants = self.module.compound_article_variants(title, summary, [])
        variant_titles = {variant_title for variant_title, _summary, _facts in variants}
        self.assertTrue(any("AirPods" in value for value in variant_titles), variant_titles)
        self.assertTrue(any("iPad mini" in value for value in variant_titles), variant_titles)

        english = article_for(
            self.module,
            "New OLED iPad mini expected by the end of October",
            "Apple is expected to launch its first OLED iPad mini by the end of October.",
            "9to5Mac",
        )
        chinese = article_for(
            self.module,
            "iPad mini屏幕史诗级升级：首次搭载OLED 苹果最强小平板",
            "新款 iPad mini 将首次搭载 OLED 屏幕，并预计于十月底前推出。",
            "快科技",
        )
        events = self.module.cluster_articles([english, chinese])
        self.assertEqual(len(events), 1, partitions(events))

    def test_case_revival_merges_independent_repair_lawsuit_translations(self):
        reports = [
            article_for(
                self.module,
                "Court revives 2022 lawsuit accusing Apple of blocking independent repairs",
                "A California appeals court restored the case alleging Apple discouraged third-party repairs.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "加州法院恢复审理指控苹果阻碍独立维修的诉讼",
                "加州上诉法院推翻驳回裁定，让这宗独立维修诉讼继续推进。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_platform_named_headline_still_defers_third_party_app_update(self):
        title = "Apple CarPlay just added a major weather app"
        summary = (
            "The Weather Channel released a Storm Radar update that adds its own CarPlay app. "
            "Apple did not announce a new API, policy, or platform capability."
        )
        tier, reason = self.module.classify_relevance_tier(
            title,
            summary,
            ["Storm Radar version 4.0.19 now works with CarPlay."],
            "9to5Mac",
        )
        self.assertEqual(tier, "weak", reason)

    def test_ceo_assumption_reports_merge_without_departing_executive_in_title(self):
        reports = [
            article_for(
                self.module,
                "苹果新 CEO 特努斯 9 月 1 日上任，人工智能将成为其任期内的首要任务",
                "苹果新任 CEO 将于 9 月 1 日正式上任，并把人工智能列为首要任务。",
                "IT之家",
            ),
            article_for(
                self.module,
                "库克时期落幕！苹果新任CEO特努斯明天正式上任：AI成首要任务",
                "苹果新任 CEO 特努斯将在 9 月 1 日上任，人工智能成为首要任务。",
                "快科技",
            ),
        ]
        transition_key = "primary-claim:apple-leadership:ceo-transition"
        for report in reports:
            profile = self.module.article_reconciliation_profile(report)
            self.assertIn(transition_key, profile.event_keys)
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))

    def test_multi_product_title_clauses_project_without_body_sentence_split(self):
        title = "古尔曼：苹果 AirPods 5 耳机最早 9 月发布，OLED 版 iPad mini 平板预计 10 月推出"
        summary = "苹果计划在秋季更新 AirPods 5 和 OLED iPad mini，两款产品发布时间不同。"
        variants = self.module.compound_article_variants(title, summary, [])
        variant_titles = {variant_title for variant_title, _summary, _facts in variants}
        self.assertEqual(
            variant_titles,
            {"Apple AirPods roadmap update", "Apple iPad mini roadmap update"},
        )


if __name__ == "__main__":
    unittest.main()
