"""Collection must not lose a title-owned report to incidental exclusion words."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest import mock

from test_relevance_rules import load_module, source_named


class CandidateAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.source = source_named(cls.m, 'MacRumors')
        cls.capture = json.loads((Path(__file__).parent /
            'fixtures/20261011_adt_discovery.json').read_text())

    def candidate(self, title, lead):
        return self.m.Candidate(self.source.name,
            'https://www.macrumors.com/2026/10/11/report/', title, lead)

    def test_real_rss_report_survives_collection_and_detail_selection(self):
        m, capture = self.m, self.capture
        with mock.patch.object(m, 'fetch_url', side_effect=lambda url, *_args, **_kwargs:
                capture['feed_xml'] if url == capture['captured_from'] else None):
            candidates = m.collect_candidates(self.source, Path('/unused-cache'), {})
        self.assertEqual([c.url for c in candidates], [capture['url']])
        chosen = m.select_detail_candidates(candidates, {self.source.name: self.source}, 20,
            datetime(2026, 10, 10, 3, 6, 5, tzinfo=timezone.utc),
            datetime(2026, 10, 11, 3, 6, 5, tzinfo=timezone.utc))
        self.assertEqual([c.url for c in chosen], [capture['url']])
        self.assertEqual(chosen[0].feed_time_raw, 'Sun, 11 Oct 2026 02:17:37 +0000')
        self.assertIn('Another potential giveaway', chosen[0].summary)

    def test_company_action_without_a_product_survives_body_keywords(self):
        for tail in ('Another potential giveaway is the staff preparation.',
                     'The report also compares Amazon and Microsoft.',
                     'A background chart shows a record low in competitor spending.',
                     'The publisher also runs a weekly giveaway.'):
            with self.subTest(tail=tail):
                c = self.candidate('Rumor: Apple to Announce New Partnership With Orion',
                    'Apple may announce a partnership with Orion. ' + tail)
                self.assertTrue(self.m.is_relevant_candidate(c, self.source))

    def test_named_counterparty_is_not_a_retailer_advertisement(self):
        for partner in ('Amazon', 'Microsoft'):
            c = self.candidate('Rumor: Apple to Announce New Partnership With ' + partner,
                'Apple may announce a partnership with ' + partner + ' for logistics.')
            self.assertTrue(self.m.is_relevant_candidate(c, self.source))

    def test_actual_reader_giveaways_are_not_saved_by_an_apple_prize(self):
        for title, lead in [
            ('Orion Giveaway: Win an iPhone', 'Enter our giveaway to win an iPhone. Apple announced the device yesterday.'),
            ('Apple iPhone giveaway: enter to win', 'A retailer is giving away an iPhone. Enter the contest for a chance to win.'),
            ('Win an iPhone in our latest giveaway', 'Enter our giveaway for a chance to win the new iPhone.'),
            ('This week’s iPhone giveaway', 'Enter our giveaway for a chance to win an iPhone. Apple announced the phone yesterday.'),
        ]:
            with self.subTest(title=title):
                c = self.candidate(title, lead)
                self.assertFalse(self.m.is_relevant_candidate(c, self.source))
                self.assertEqual(self.m.classify_relevance_tier(title, lead, [], self.source.name)[0], 'weak')

    def test_incidental_apple_action_does_not_rescue_promotions_or_competitors(self):
        for title, lead in [
            ('Deals: Apple iPhone hits record low', 'Amazon offers a discounted iPhone. Apple announced it last month.'),
            ('Amazon introduces a new home security service', 'Amazon announced a new service. Apple could announce its own partnership later.'),
            ('AppleInsider Podcast discusses an Apple partnership', 'Listen to the AppleInsider Podcast for this week\'s Apple rumors.'),
        ]:
            with self.subTest(title=title):
                self.assertFalse(self.m.is_relevant_candidate(self.candidate(title, lead), self.source))

    def test_navigation_and_weekly_recap_still_excluded(self):
        for url, title in [
            ('https://www.macrumors.com/tag/apple/', 'Apple announces a partnership'),
            ('https://www.macrumors.com/2026/10/11/top-stories/', 'Top Stories: Apple announces a partnership'),
        ]:
            c = self.m.Candidate(self.source.name, url, title,
                'Apple announced a partnership. Amazon is mentioned as background.')
            self.assertFalse(self.m.is_relevant_candidate(c, self.source))

    def test_market_entry_and_lawsuit_victory_are_not_reader_invitations(self):
        for title, lead in [
            ('Apple to Enter Home Security Market: iPhone Deployment Is a Giveaway',
             'Apple may announce a new partnership with Orion. Orion employees received iPhones, offering a clue to the agreement.'),
            ('Apple scores a win in iPhone giveaway lawsuit',
             'Apple won a lawsuit over an unauthorized iPhone giveaway. The court ruled in favor of Apple.'),
            ('Apple wins lawsuit over iPhone giveaway',
             'Apple won a lawsuit over an unauthorized iPhone giveaway. The disputed advertisement said enter our giveaway for a chance to win.'),
            ('Apple sues company over "iPhone Giveaway: Win an iPhone"',
             'Apple filed a lawsuit against Orion for unauthorized use of its trademarks in an iPhone giveaway.'),
            ('Apple sues company over iPhone Giveaway: Win an iPhone',
             'Apple filed a lawsuit against Orion for unauthorized use of its trademarks in an iPhone giveaway.'),
            ('Apple wins lawsuit over iPhone giveaway',
             'Apple won a lawsuit over an unauthorized iPhone giveaway. The disputed advertisement read: "Free iPhones for everyone. Enter our giveaway for a chance to win."'),
            ('Apple wins lawsuit over iPhone giveaway',
             'Apple won a lawsuit over an unauthorized iPhone giveaway. Enter our giveaway for a chance to win an iPhone.'),
        ]:
            with self.subTest(title=title):
                c = self.candidate(title, lead)
                self.assertTrue(self.m.is_relevant_candidate(c, self.source))
                self.assertEqual(self.m.classify_relevance_tier(title, lead, [], self.source.name)[0], 'strong')


if __name__ == '__main__':
    unittest.main()
