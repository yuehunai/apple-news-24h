import unittest

from test_20260905_claim_ownership_boundaries import article_for, load_module


class ReviewBoundaries20260908Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def articles_for(self, pairs):
        return [
            article_for(self.m, title, lead, source=str(index))
            for index, (title, lead) in enumerate(pairs)
        ]

    def cluster(self, articles):
        events = self.m.cluster_articles(articles)
        self.assertCountEqual(
            [article.url for event in events for article in event.articles],
            [article.url for article in articles],
            "Clustering must preserve every input article, including weak ones.",
        )
        return events

    def test_review_01_recall_is_not_its_background_production_forecast(self):
        articles = self.articles_for([
            (
                "Apple recalls iPhone batteries after overheating reports",
                "Apple announced a battery recall. KeyBanc expects Apple to "
                "build 80 million iPhones in 2027.",
            ),
            (
                "KeyBanc predicts iPhone production in 2027",
                "KeyBanc expects Apple to build 80 million iPhones in 2027.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1])
        self.assertTrue(all(event.relevance_tier == "strong" for event in events))

    def test_review_01_historical_volume_order_does_not_split_one_forecast(self):
        articles = self.articles_for([
            (
                "KeyBanc predicts iPhone production growth",
                "KeyBanc expects growth next quarter. Apple produced 80 million "
                "iPhones in 2026, and will build 90 million iPhones in 2027.",
            ),
            (
                "KeyBanc predicts iPhone production growth",
                "KeyBanc expects Apple to build 90 million iPhones in 2027. "
                "Apple produced 80 million iPhones in 2026.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_review_01_analyst_opening_does_not_replace_recall_action(self):
        articles = self.articles_for([
            (
                "Apple recalls iPhone batteries after overheating reports",
                "KeyBanc expects sales to fall after Apple's recall. Apple "
                "will build 80 million iPhones in 2027.",
            ),
            (
                "KeyBanc predicts iPhone production in 2027",
                "KeyBanc expects Apple to build 80 million iPhones in 2027.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1])
        self.assertTrue(all(event.relevance_tier == "strong" for event in events))

    def test_review_01_non_apple_forecast_cannot_promote_or_bridge(self):
        articles = self.articles_for([
            (
                "Samsung launches iPhone rival as KeyBanc predicts demand",
                "KeyBanc expects Samsung to build 80 million units in 2027. "
                "The Galaxy phone competes with Apple.",
            ),
            (
                "KeyBanc predicts iPhone production in 2027",
                "KeyBanc expects Apple to build 80 million iPhones in 2027.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        self.assertEqual(profile.relevance_tier, "weak")
        self.assertFalse(profile.trusted_direct_action)
        self.assertCountEqual(
            [
                (event.relevance_tier, frozenset(a.url for a in event.articles))
                for event in events
            ],
            [
                ("weak", frozenset({articles[0].url})),
                ("strong", frozenset({articles[1].url})),
            ],
        )

    def test_review_02_third_party_camera_code_cannot_promote_or_bridge(self):
        articles = self.articles_for([
            (
                "Photon Camera app adds manual focus on iOS 27",
                "Independent developers released their third-party Camera app "
                "for iPhone. Forum member 'exampleuser' found manual focus "
                "references in its iOS 27 code.",
            ),
            (
                "iOS 27 Camera code reveals new photography tools",
                "Forum member 'exampleuser' found manual focus tools in new "
                "iOS 27 camera code.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        self.assertEqual(profile.relevance_tier, "weak")
        self.assertFalse(profile.trusted_direct_action)
        self.assertCountEqual(
            [
                (event.relevance_tier, frozenset(a.url for a in event.articles))
                for event in events
            ],
            [
                ("weak", frozenset({articles[0].url})),
                ("strong", frozenset({articles[1].url})),
            ],
        )

    def test_review_02_code_disclosures_keep_beta_and_feature_boundaries(self):
        articles = self.articles_for([
            (
                "iOS 27 beta 7 camera code reveals new autofocus tools",
                "Forum member 'exampleuser' discovered a new autofocus "
                "algorithm in iOS 27 beta 7 camera code.",
            ),
            (
                "iOS 27 beta 8 camera code reveals new exposure tools",
                "Forum member 'exampleuser' discovered a new histogram in "
                "iOS 27 beta 8 camera code.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1])
        self.assertTrue(all(event.relevance_tier == "strong" for event in events))

    def test_review_02_historical_beta_cannot_cancel_current_build_boundary(self):
        articles = self.articles_for([
            (
                "iOS 27 beta 7 camera code reveals new autofocus tools",
                "Forum member 'exampleuser' discovered a new autofocus "
                "algorithm in iOS 27 beta 7 camera code.",
            ),
            (
                "iOS 27 beta 8 camera code reveals new exposure tools",
                "Forum member 'exampleuser' discovered a new histogram in "
                "iOS 27 beta 8 camera code. Previous iOS 27 beta 7 code had "
                "autofocus tools.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1])
        self.assertTrue(all(event.relevance_tier == "strong" for event in events))

    def test_review_03_interop_app_is_not_a_platform_milestone(self):
        articles = self.articles_for([
            (
                "Relay app adds Apple Watch interoperability on Android 17",
                "Relay now forwards notifications and calls. This is an "
                "independent third-party app, not an Android platform change.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        # App/platform pairwise merging was already broken in the baseline.
        self.assertEqual(profile.relevance_tier, "weak")
        self.assertFalse(profile.trusted_direct_action)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")

    def test_review_03_platform_prefix_does_not_make_companion_app_a_platform(self):
        articles = self.articles_for([
            (
                "Android 17 companion app adds Apple Watch interoperability",
                "Relay now forwards notifications and calls. This is an "
                "independent third-party app, not an Android platform change.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        self.assertEqual(profile.relevance_tier, "weak")
        self.assertFalse(profile.trusted_direct_action)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")

    def test_review_04_supplier_response_requires_apple_counterparty(self):
        articles = self.articles_for([
            (
                "CXMT responds to Samsung partnership rumors; Apple is not involved",
                "The supplier declined to confirm a new deal with Samsung. "
                "Apple is not involved.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        # Confirmation/denial and pairwise supplier merging are pre-existing.
        self.assertEqual(profile.relevance_tier, "weak")
        self.assertFalse(profile.trusted_direct_action)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")

    def test_review_04_apple_analyst_is_not_apple_counterparty(self):
        articles = self.articles_for([
            (
                "CXMT responds to Apple analyst's Samsung partnership rumors",
                "The supplier declined to confirm a new deal with Samsung. "
                "Apple is not involved.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        self.assertEqual(profile.relevance_tier, "weak")
        self.assertFalse(profile.trusted_direct_action)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")

    def test_review_05_platform_award_total_is_not_program_award_count(self):
        articles = self.articles_for([
            (
                "Apple TV leads Emmy wins with Severance",
                "Apple TV's Severance won 8 awards, while Apple earned 20 wins "
                "in total.",
            ),
            (
                "Apple TV wins 20 Emmy awards",
                "Apple earned 20 wins in total.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_review_05_program_awards_in_subclause_are_not_platform_total(self):
        articles = self.articles_for([
            (
                "Apple TV leads Emmy wins with Severance",
                "Apple TV won big at the Emmys, with Severance earning 8 "
                "awards. Apple earned 20 wins in total.",
            ),
            (
                "Apple TV wins 20 Emmy awards",
                "Apple earned 20 wins in total.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_review_06_submission_date_is_not_project_identity(self):
        articles = self.articles_for([
            (
                "Apple invites developers to submit browser interoperability ideas",
                "In September 2026, Apple opened its call for Interop 2027 "
                "proposals. WebKit invites developers to submit ideas for "
                "browser interoperability.",
            ),
            (
                "Apple invites developers to submit browser interoperability "
                "ideas for Interop 2027",
                "The WebKit team has opened its annual proposal call for "
                "Interop 2027.",
            ),
        ])

        events = self.cluster(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_review_07_first_party_app_arrival_keeps_apple_ownership(self):
        articles = self.articles_for([
            (
                "Journal app arrives on the App Store",
                "Apple today released its new first-party Journal application "
                "for iPad.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        self.assertEqual(profile.identity.scope, "apple-direct")
        self.assertEqual(profile.relevance_tier, "strong")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_review_08_quoted_opinion_does_not_demote_apple_launch(self):
        articles = self.articles_for([
            (
                "Apple announces new privacy feature, says tracking users is "
                "a bad idea",
                "Apple today announced a new iOS privacy feature that blocks "
                "cross-app tracking by default.",
            ),
        ])

        profile = self.m.article_reconciliation_profile(articles[0])
        events = self.cluster(articles)

        self.assertEqual(profile.identity.content_form, "news")
        self.assertEqual(profile.relevance_tier, "strong")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")


if __name__ == "__main__":
    unittest.main()
