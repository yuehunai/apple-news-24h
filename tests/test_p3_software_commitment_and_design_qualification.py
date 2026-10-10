"""Current software repair owns its category; unsettled hardware options retain source scope."""
import unittest

from apple_news_core.models import ArticleEvidence, EvidenceUnit
from test_relevance_rules import article_for, load_module


class CommitmentAndDesignQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_confirmed_future_software_fix_owns_device_spec_background(self):
        m = self.m
        article = article_for(
            m, "Apple says software update to fix iPhone 21 Pro rebooting bug is coming next week",
            "Apple has confirmed that a software update to address the reboot problem "
            "is in the works and should be available early next week. The phone's "
            "Face ID sensor moved beneath the display, reducing the Dynamic Island.",
            "Repair News",
        )
        profile = m.article_reconciliation_profile(article)
        self.assertEqual(profile.category_hint, "software_systems")
        event = m.cluster_articles([article])[0]
        self.assertEqual((event.relevance_tier, event.category), ("strong", "software_systems"))

    def test_unsettled_watch_direction_and_options_reach_source_review(self):
        m = self.m
        article = article_for(
            m, "Apple Is Working on a Screenless Fitness Band",
            "Apple is exploring an Apple Watch-style screenless fitness band and has built prototypes.",
            "Wearable News",
        )
        qualification = ("Apple has not yet settled on the direction of its Apple Watch lineup, "
                         "and is also considering smart rings and a circular-display Watch.")
        article.evidence = ArticleEvidence(
            "synthetic-wearable", article.source, article.url, article.title,
            article.summary, "news", (
                EvidenceUnit("u1", "p", article.summary, "body", 0),
                EvidenceUnit("u2", "p", qualification, "body", 1),
            ), confidence="detail")
        event = m.cluster_articles([article])[0]
        self.assertEqual((event.relevance_tier, event.category), ("strong", "hardware_products"))
        self.assertTrue(any(origin[3] == "u2" for fact in (
            *event.fact_plan.facts, *event.fact_plan.unprocessed) for origin in fact.origins))

    def test_bilingual_repair_commitment_groups_by_model_and_action_not_guide(self):
        m = self.m
        chinese = article_for(
            m, "苹果确认下周推送 iOS 28 更新，修复 iPhone 21 Pro 自动重启问题",
            "苹果向记者确认，正在开发软件更新以解决 iPhone 21 Pro 在 Face ID 认证失败后重启的问题，预计下周初推送。",
            "Chinese News",
        )
        english = article_for(
            m, "Apple says software update to fix iPhone 21 Pro rebooting bug is coming next week",
            "Apple has confirmed that a software update to address the reboot after failed Face ID is in the works "
            "and should be available early next week.",
            "English News",
        )
        guide = article_for(
            m, "iPhone Handoff in iOS 28: How It Works and Carrier Support",
            "Apple in iOS 28 introduced iPhone Handoff so one number can move between two iPhones; "
            "the line remains active on one phone at a time.",
            "Guide News",
        )
        other_model = article_for(
            m, "Apple says software update to fix iPhone 22 Pro rebooting bug is coming next week",
            "Apple has confirmed a software update for iPhone 22 Pro rebooting after a failed Face ID attempt "
            "is in the works and should be available early next week.",
            "Other Model News",
        )
        denied = article_for(
            m, "Apple says software update to fix iPhone 21 Pro rebooting bug is coming next week",
            "Apple has not confirmed a software update to fix the iPhone 21 Pro reboot after failed Face ID; "
            "a next-week repair remains unannounced.",
            "Denial News",
        )
        released = article_for(
            m, "Apple says software update to fix iPhone 21 Pro rebooting bug is coming next week",
            "Apple confirmed the software update fixing the iPhone 21 Pro reboot after failed Face ID "
            "was already released today.",
            "Release News",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (chinese, english, guide, other_model, denied, released)]
        repair_keys = [next((key for key in profile.event_keys if key.startswith("primary-claim:")), "")
                       for profile in profiles]
        self.assertTrue(repair_keys[0])
        self.assertEqual(repair_keys[0], repair_keys[1])
        self.assertNotEqual(repair_keys[0], repair_keys[2])
        self.assertNotEqual(repair_keys[0], repair_keys[3])
        self.assertNotEqual(repair_keys[0], repair_keys[4])
        self.assertNotEqual(repair_keys[0], repair_keys[5])
        events = m.cluster_articles([chinese, english, guide, other_model, denied, released])
        groups = {frozenset(article.source for article in event.articles)
                  for event in events}
        self.assertIn(frozenset({"Chinese News", "English News"}), groups)
        self.assertIn(frozenset({"Guide News"}), groups)
        self.assertIn(frozenset({"Other Model News"}), groups)
        self.assertIn(frozenset({"Denial News"}), groups)
        self.assertIn(frozenset({"Release News"}), groups)


if __name__ == "__main__":
    unittest.main()
