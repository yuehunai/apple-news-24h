import importlib.util
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "apple_news_24h.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "20260822_event_boundaries.json"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260822_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_from_fixture(module, item, *, title=None, summary=None, key_facts=None):
    article_title = title or item["title"]
    article_summary = summary if summary is not None else item["summary"]
    article_facts = list(item["key_facts"] if key_facts is None else key_facts)
    tier, reason = module.classify_relevance_tier(
        article_title,
        article_summary,
        article_facts,
        item["source"],
    )
    return module.Article(
        source=item["source"],
        url=item["url"],
        title=article_title,
        summary=article_summary,
        key_facts=article_facts,
        category=module.choose_category(article_title, article_summary),
        published_utc=datetime.fromisoformat(item["published_at"]),
        published_raw=item["published_at"],
        published_source="fixture",
        confidence="detail",
        tokens=module.article_tokens(
            article_title,
            " ".join([article_summary, *article_facts[:5]]),
        ),
        event_kind=module.detect_event_kind(
            article_title,
            article_summary,
            article_facts,
        ),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(
            " ".join([article_title, article_summary, *article_facts[:5]])
        ),
    )


class AuthoritativeEventPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["groups"]

    def articles(self, group_name):
        return [
            article_from_fixture(self.module, item)
            for item in self.fixture[group_name]
        ]

    def test_same_action_cross_source_reports_form_one_event(self):
        expected = {
            "vision-layoffs": 8,
            "camera-airpods": 4,
            "m6-macbook-pro": 3,
        }
        for group_name, source_count in expected.items():
            with self.subTest(group=group_name):
                events = self.module.cluster_articles(self.articles(group_name))
                self.assertEqual(len(events), 1)
                self.assertEqual(len(events[0].articles), source_count)

    def test_distinct_watch_subject_changes_remain_separate(self):
        events = self.module.cluster_articles(self.articles("apple-watch-actions"))

        self.assertEqual(len(events), 2)
        self.assertEqual(
            {event.category for event in events},
            {"hardware_products"},
        )

    def test_multi_title_service_page_projects_independent_claims(self):
        source = self.fixture["apple-tv-pages"][0]
        variants = self.module.compound_article_variants(
            source["title"],
            source["summary"],
            source["key_facts"],
        )
        normalized_titles = [title.lower() for title, _summary, _facts in variants]

        self.assertEqual(len(variants), 3)
        self.assertTrue(any("dark matter" in title for title in normalized_titles))
        self.assertTrue(any("mayday" in title for title in normalized_titles))
        self.assertTrue(any("slow horses" in title for title in normalized_titles))

    def test_projected_service_claims_do_not_absorb_another_title(self):
        roundup = self.fixture["apple-tv-pages"][0]
        articles = [
            article_from_fixture(
                self.module,
                roundup,
                title=title,
                summary=summary,
                key_facts=facts,
            )
            for title, summary, facts in self.module.compound_article_variants(
                roundup["title"],
                roundup["summary"],
                roundup["key_facts"],
            )
        ]
        articles.append(article_from_fixture(self.module, self.fixture["apple-tv-pages"][1]))

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 4)

    def test_single_work_page_does_not_project_historical_content_actions(self):
        variants = self.module.compound_article_variants(
            "Emmy-winning Stillwater returns to Apple TV with five new episodes",
            "Apple TV subscribers can now watch five new Stillwater episodes.",
            [
                "After releasing the trailer for Stillwater's new season a few days ago, Apple TV made all five episodes available to stream.",
                "Based on Jon J Muth's book series, Stillwater originally premiered in 2020.",
                "Stillwater's fourth season premiered last August.",
            ],
        )

        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0][0], "Emmy-winning Stillwater returns to Apple TV with five new episodes")

    def test_multi_work_projection_ignores_historical_related_content(self):
        variants = self.module.compound_article_variants(
            "Apple TV has three big new releases coming very soon",
            "Dark Matter season 2 premieres August 28. Mayday premieres September 4. Slow Horses season 6 premieres September 16.",
            [
                "After releasing the trailer for Stillwater's new season a few days ago, Apple TV made five episodes available.",
                "Dark Matter season 2 premieres Friday, August 28.",
                "Based on Jon J Muth's book series, Stillwater originally premiered in 2020.",
                "Stillwater's fourth season premiered last August.",
                "In the streaming era, viewers often wait several years for new seasons.",
                "Wonder quickly turns to nightmare when he tries to return to his reality.",
                "Apple TV has Ted Lasso airing now, and there are three more big new releases coming soon.",
                "Mayday premieres Friday, September 4 exclusively on Apple TV.",
                "Slow Horses season 6 premieres Wednesday, September 16.",
            ],
        )

        titles = [title.casefold() for title, _summary, _facts in variants]
        self.assertEqual(len(variants), 3)
        self.assertTrue(any("dark matter" in title for title in titles))
        self.assertTrue(any("mayday" in title for title in titles))
        self.assertTrue(any("slow horses" in title for title in titles))
        self.assertFalse(any("stillwater" in title for title in titles))

    def test_direct_platform_rollout_is_not_left_in_deferred(self):
        events = self.module.cluster_articles(self.articles("walmart-apple-pay"))

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 6)
        self.assertNotEqual(events[0].relevance_tier, "weak")

    def test_different_hardware_models_objects_and_content_forms_stay_separate(self):
        events = self.module.cluster_articles(self.articles("hardware-action-boundaries"))

        self.assertEqual(len(events), 4)
        self.assertEqual(
            sorted(len(event.articles) for event in events),
            [1, 1, 1, 1],
        )

    def test_non_apple_product_action_cannot_bridge_apple_hardware(self):
        events = self.module.cluster_articles(self.articles("competitor-apple-boundary"))

        self.assertEqual(len(events), 2)
        tiers_by_title = {event.title: event.relevance_tier for event in events}
        self.assertEqual(tiers_by_title["小米自研玄戒芯片即将发布：给苹果上点压力"], "weak")
        self.assertNotEqual(
            tiers_by_title["iPhone 18 Pro Max包装盒流出：清新配色撞脸远峰蓝"],
            "weak",
        )

    def test_non_apple_actions_do_not_enter_main_queue(self):
        events = self.module.cluster_articles(self.articles("main-queue-noise"))
        article_count = sum(len(event.articles) for event in events)

        self.assertEqual(article_count, len(self.fixture["main-queue-noise"]))
        self.assertTrue(events)
        self.assertTrue(
            all(event.relevance_tier == "weak" for event in events),
            [(event.title, event.relevance_tier, event.relevance_reason) for event in events],
        )


if __name__ == "__main__":
    unittest.main()
