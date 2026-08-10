import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260810_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac"):
    tier, reason = module.classify_relevance_tier(title, summary, [], source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=[],
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 10, tzinfo=timezone.utc),
        published_raw="2026-08-10T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, []),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(f"{title} {summary}"),
    )


def title_sets(groups):
    return [{article.title for article in group} for group in groups]


class AugustTenthTitleFactSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def reconcile(self, articles, initial_groups):
        return self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=initial_groups,
        )

    def test_same_concrete_actions_merge_across_language_and_seed_boundaries(self):
        fold_colors = [
            article_for(
                self.module,
                "Foldable 'iPhone Ultra' Rumored to Come in These Two Colors",
                "Third-party camera protectors indicate silver and dark blue finishes for Apple's foldable iPhone.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "iPhone Fold may ship in a choice of Silver or Dark Blue",
                "The first foldable iPhone may be sold in silver or dark blue.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果首款折叠屏手机 iPhone Ultra 新配色曝光：银色、深蓝色现身",
                "两款保护配件显示苹果折叠 iPhone 可能采用银色和深蓝色配色。"
                "该消息仍需等待苹果确认。此前另有报道讨论过黑色和白色方案，但不是本轮的新爆料。",
                "快科技",
            ),
        ]
        upgrade_preload = [
            article_for(
                self.module,
                "This scrapped Apple Upgrade feature would've made setup much more seamless",
                "Apple considered an Apple Upgrade white-glove feature that would preload a buyer's iCloud backup before delivery, but scrapped it over privacy optics.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Upgrade plan to preload your data nixed over privacy optics",
                "Apple evaluated shipping Apple Upgrade iPhones with the owner's previous iCloud data preloaded, but the feature did not make the final plan.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "古尔曼曝光苹果早前设想：生产 iPhone 时就装好 iCloud 数据",
                "苹果构思 Apple Upgrade 租赁计划时，曾考虑预载用户 iCloud 备份，让新机开箱即用，但最终取消该功能。",
                "IT之家",
            ),
        ]
        third_generation_fold = [
            article_for(
                self.module,
                "Foldable 'iPhone Ultra 3' Rumored to Feature Larger Displays",
                "Apple is reportedly planning a third-generation foldable iPhone for 2028 with larger inner and outer displays.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Of course, Apple's already planning a third-gen iPhone Fold",
                "Apple has already started planning its third-generation foldable iPhone as part of a three-year roadmap.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果第三代折叠屏首曝：iPhone Ultra 3 预计 2028 年发布",
                "苹果折叠 iPhone 三年路线图已经规划到第三代，内外屏将进一步增大。",
                "快科技",
            ),
        ]
        articles = [*fold_colors, *upgrade_preload, *third_generation_fold]

        groups = self.reconcile(
            articles,
            [fold_colors[:2], [fold_colors[2]], *[[item] for item in upgrade_preload], third_generation_fold[:2], [third_generation_fold[2]]],
        )

        self.assertEqual(
            sorted(len(group) for group in groups),
            [3, 3, 3],
            title_sets(groups),
        )

    def test_watch_redesign_and_ceramic_case_split_then_merge_by_concrete_fact(self):
        redesign = [
            article_for(
                self.module,
                "Apple considers round screens and more radical designs for future Apple Watch revamp",
                "Apple is considering a round display and a screenless fitness device while rethinking the Apple Watch form factor.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Watch Rethink Could See Debut of Round Model, Screenless Fitness Tracker, and More",
                "Apple is exploring a round Apple Watch and a screenless fitness tracker as part of a major form-factor rethink.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "古尔曼称苹果正研究圆屏 Apple Watch 或无屏手环",
                "苹果正在重新思考 Apple Watch 产品形态，包括圆形屏幕和完全无屏的健身设备。",
                "IT之家",
            ),
            article_for(
                self.module,
                "2026 Apple Watch upgrade will be dull, but a big redesign is in progress",
                "Apple is rethinking the wearable with round-screen and screenless concepts, although this year's model remains modest.",
                "AppleInsider",
            ),
        ]
        ceramic = [
            article_for(
                self.module,
                "Ceramic Case Could Return With Apple Watch Series 12",
                "Apple may reintroduce its ceramic Apple Watch casing with Series 12 this year or next year.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "A new ceramic Apple Watch could go on sale soon",
                "Apple is planning the return of the ceramic Apple Watch as a premium case material.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "古尔曼：苹果 AppleWatch Series 12 有望推出陶瓷版",
                "苹果计划重新推出陶瓷材质 Apple Watch，最快可能今年上市。",
                "IT之家",
            ),
        ]
        mixed_seed = [ceramic[0], redesign[1], redesign[2], redesign[3], ceramic[2]]
        articles = [*redesign, *ceramic]

        groups = self.reconcile(
            articles,
            [mixed_seed, [redesign[0]], [ceramic[1]]],
        )

        self.assertEqual(len(groups), 2, title_sets(groups))
        self.assertIn({article.title for article in redesign}, title_sets(groups))
        self.assertIn({article.title for article in ceramic}, title_sets(groups))

    def test_document_lifecycle_matches_linking_language_and_subject_before_manual(self):
        standard = article_for(
            self.module,
            "苹果客服回应删除接入千问手册：目前没有收到新项目通知",
            "苹果官网删除《在 Mac 上配合 Apple 智能使用千问》支持文档。",
            "IT之家",
        )
        variant = article_for(
            self.module,
            "上线不到一天！苹果客服回应官网删除千问使用手册",
            "苹果中国官网 Mac 板块的使用指南此前称国行 Apple 智能可联动阿里千问大模型，随后页面被删除。",
            "快科技",
        )

        groups = self.reconcile([standard, variant], [[standard], [variant]])

        self.assertEqual(len(groups), 1, title_sets(groups))

    def test_comparison_roundup_and_rumor_projection_do_not_enter_main_queue(self):
        cases = [
            (
                "Crimeblotter: Thieves try using stolen credit cards at a Miami Apple Store",
                "This week's Apple Crime Blotter collects unrelated crimes involving an Apple Watch, several iPhones, and stolen iPads.",
                "AppleInsider",
            ),
            (
                "iPhone 17 set to break a record no flagship has touched in 15 years",
                "Based on current rumors that iPhone 18 will arrive in spring 2027, the author projects an 18-month flagship run; the article has no new reporting.",
                "9to5Mac",
            ),
            (
                "马斯克超级芯片工厂 Terafab 面积超五角大楼、苹果园区等地标总和",
                "Terafab 已开始施工，Apple Park 仅作为面积比较对象；苹果没有参与该项目。",
                "IT之家",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

        direct_title = "Fire breaks out outside Apple Park office building leased by Apple"
        direct_summary = "Fire crews responded to a blaze at an Apple-leased facility; Apple employees use the building."
        tier, reason = self.module.classify_relevance_tier(direct_title, direct_summary, [], "AppleInsider")
        self.assertEqual(tier, "strong", reason)


if __name__ == "__main__":
    unittest.main()
