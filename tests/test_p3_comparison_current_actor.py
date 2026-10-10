"""An event name and editorial comparison cannot create an Apple action."""

import unittest

from test_relevance_rules import article_for, load_module


class ComparisonCurrentActorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_connect_event_name_is_not_integration_while_mail_change_is_current(self):
        m = self.m
        comparison = article_for(
            m, "Apple's headset strategy was on full display at Nova Connect",
            "Nova launched its new headset and compared its price and field of view "
            "with Apple Vision Pro. Apple announced no new headset feature.",
            "Comparison News",
        )
        mail = article_for(
            m, "iOS 28 gives Apple Mail my most wished-for search upgrade",
            "Apple says iOS 28 improves Mail search relevance and supports results "
            "based on meaning rather than only typed words.",
            "Software News",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (comparison, mail)]
        self.assertFalse(any("platform-integration" in key for key in profiles[0].event_keys))
        self.assertTrue(any("mail" in key and "feature-change" in key
                            for key in profiles[1].event_keys))
        events = m.cluster_articles([comparison, mail])
        outcomes = {article.source: (event.relevance_tier, event.category)
                    for event in events for article in event.articles}
        self.assertEqual(outcomes[comparison.source], ("weak", "hardware_products"))
        self.assertEqual(outcomes[mail.source], ("strong", "software_systems"))
        self.assertEqual(len(events), 2)

    def test_connect_directly_to_health_is_a_current_integration_action(self):
        m = self.m
        direct = article_for(
            m, "Your fitness data can now connect directly to Apple Health",
            "Fitbit workouts and health data now connect directly to Apple Health on iPhone.",
            "The Verge",
        )
        sync = article_for(
            m, "Fitness data now syncs with Apple Health",
            "Fitbit workouts and health data can now sync directly into Apple Health on iPhone.",
            "MacRumors",
        )
        direct_profile = m.article_reconciliation_profile(direct)
        self.assertIn("apple-health-data-sync", m.article_primary_facets(direct))
        self.assertTrue(any("platform-integration" in key for key in direct_profile.event_keys))
        events = m.cluster_articles([direct, sync])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "ecosystem")

    def test_connect_health_data_object_matches_sync_action(self):
        m = self.m
        lead = "OpenAI made ChatGPT Health available to users and lets them connect Apple Health data."
        connect = article_for(m, "ChatGPT users can now connect Apple Health data", lead,
                              "Connect News")
        sync = article_for(m, "ChatGPT users can now sync Apple Health data", lead,
                           "Sync News")
        for article in (connect, sync):
            self.assertIn("platform-integration",
                          m.article_title_led_event_identity(article).title_actions)
        events = m.cluster_articles([connect, sync])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)
        self.assertEqual(events[0].relevance_tier, "ecosystem")
        self.assertEqual(events[0].category, "software_systems")


if __name__ == "__main__":
    unittest.main()
