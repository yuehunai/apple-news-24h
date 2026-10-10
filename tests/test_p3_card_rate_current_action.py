"""A current Apple Card rate change keeps its owner despite nearby offers."""

import unittest

from test_relevance_rules import article_for, load_module


class CardRateCurrentActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_current_rate_reports_join_without_promoting_other_offers_or_history(self):
        m = self.m
        direct = article_for(
            m, "Apple raises interest rate for Apple Card Savings Account",
            "Apple and its banking partner have increased the interest rate on the "
            "Apple Card Savings Account from 4.1% to 4.2% today. A different bank "
            "offers a 5.0% limited-time referral bonus for its own customers.",
            "9to5Mac", ["Apple and its banking partner have increased the account "
                         "interest rate from 4.1% to 4.2% today."],
        )
        passive = article_for(
            m, "Apple Card Savings Account's APY Went Up",
            "The annual percentage yield for the Apple Card's savings account "
            "increased from 4.1% to 4.2% today. A conditional example describes "
            "a one-year deposit without withdrawals.", "MacRumors",
        )
        different_change = article_for(
            m, "Apple raises APY for Apple Card Savings Account",
            "Apple and its banking partner increased the annual percentage "
            "yield on the Apple Card Savings Account from 4.2% to 4.3% today.",
            "AppleInsider",
        )
        outside_offer = article_for(
            m, "Bank launches a savings promotion with Apple Pay card support",
            "The bank increased its savings rate from 4.1% to 4.2% today and "
            "offers a limited-time bonus. Its cards support Apple Pay.", "Finance Daily",
        )
        guide = article_for(
            m, "How to open an Apple Card Savings Account",
            "This guide explains how to open the account. Apple increased its "
            "savings rate from 4.1% to 4.2% last year; another bank advertises "
            "a limited-time bonus today.", "Help Site",
        )
        historical = article_for(
            m, "Apple Card Savings Account rate rose last year",
            "Last year, Apple increased its savings account rate from 4.1% to "
            "4.2%. Today another bank advertises a limited-time bonus.", "Archive",
        )
        historical_context = article_for(
            m, "Apple Card Savings Account rate went up",
            "Last year, Apple increased its savings account rate from 4.1% to "
            "4.2%. Today another bank increased its own savings rate from "
            "5.0% to 5.1% and advertises a limited-time bonus.", "Archive",
        )
        articles = [direct, passive, different_change, outside_offer, guide,
                    historical, historical_context]
        outcomes = [m.resolve_reconciliation_outcome(
            m.article_reconciliation_profile(article), observed_tier="",
            observed_reason="", observed_category="") for article in articles]
        self.assertEqual([row[0] for row in outcomes[:3]], ["strong"] * 3)
        self.assertEqual([row[2] for row in outcomes[:3]],
                         ["software_systems"] * 3)
        self.assertEqual([row[0] for row in outcomes[3:]], ["weak"] * 4)
        groups = [{article.title for article in event.articles}
                  for event in m.cluster_articles(articles)]
        self.assertEqual(sum(map(len, groups)), len(articles))
        self.assertTrue(any({direct.title, passive.title} <= group for group in groups), groups)
        for unrelated in articles[2:]:
            self.assertFalse(any({direct.title, unrelated.title} <= group for group in groups), groups)

    def test_negated_rate_change_does_not_borrow_a_positive_title_or_neighbor_clause(self):
        m = self.m
        direct = article_for(
            m, "Apple raises interest rate for Apple Card Savings Account",
            "Apple and its banking partner have increased the interest rate on "
            "the Apple Card Savings Account from 4.1% to 4.2% today.", "9to5Mac",
        )
        denial = article_for(
            m, "Apple Card Savings Account's APY Went Up",
            "The annual percentage yield for the Apple Card's savings account "
            "has not increased from 4.1% to 4.2% today.", "MacRumors",
        )
        neighbor = article_for(
            m, "Apple Card Savings Account interest rate rises today",
            "Marcus has not increased its own savings rate, but Apple and its "
            "banking partner have increased the interest rate on the Apple "
            "Card Savings Account from 4.1% to 4.2% today.", "AppleInsider",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (direct, denial, neighbor)]
        self.assertTrue(profiles[0].event_keys & profiles[2].event_keys)
        self.assertFalse(profiles[0].event_keys & profiles[1].event_keys)
        groups = [{article.title for article in event.articles}
                  for event in m.cluster_articles([direct, denial, neighbor])]
        self.assertTrue(any({direct.title, neighbor.title} <= group for group in groups), groups)
        self.assertFalse(any({direct.title, denial.title} <= group for group in groups), groups)


if __name__ == "__main__":
    unittest.main()
