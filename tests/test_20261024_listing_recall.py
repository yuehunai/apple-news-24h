"""Dated article cards survive loss of a richer RSS excerpt without promotion."""
from copy import deepcopy
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import unittest
from unittest import mock

from test_relevance_rules import load_module, source_named


class ListingRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.source = source_named(cls.m, 'The Verge')
        cls.capture = json.loads((Path(__file__).parent /
            'fixtures/20261024_verge_listing.json').read_text())

    def page(self, row, *, related=None):
        node = {'categoryLayoutPosts': {'nodes': [row]},
                'relatedPosts': {'nodes': [related] if related else []}}
        data = {'props': {'pageProps': {'hydration': {'responses': [{'data': {'node': node}}]}}}}
        links = [row] + ([related] if related else [])
        return ('<script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) +
                '</script>' + ''.join('<a href="' + html.escape(r['permalink']) + '">' +
                html.escape(r['title']) + '</a>' for r in links))

    def test_real_article_card_reaches_detail_without_rss_lead(self):
        row = self.capture['article']
        body = self.page(row)
        with mock.patch.object(self.m, 'fetch_url', side_effect=lambda url, *_a, **_k:
                body if url in self.source.pages else None):
            candidates = self.m.collect_candidates(self.source, Path('/unused-cache'), {})
        self.assertEqual([c.url for c in candidates], [row['permalink']])
        self.assertEqual(candidates[0].feed_time_raw, row['publishedAt'])
        self.assertEqual(candidates[0].publication_time_raw, row['publishedAt'])
        self.assertEqual(candidates[0].summary, row['dek']['html'])
        chosen = self.m.select_detail_candidates(candidates, {self.source.name: self.source}, 1,
            datetime(2026, 10, 23, 6, 46, tzinfo=timezone.utc),
            datetime(2026, 10, 24, 6, 46, tzinfo=timezone.utc))
        self.assertEqual([c.url for c in chosen], [row['permalink']])
        self.assertEqual(self.m.classify_relevance_tier(row['title'],
            'A guide to using the device, with setup advice and no newly announced change.',
            [], self.source.name)[0], 'weak')

    def test_card_metadata_cannot_come_from_related_or_modified_fields(self):
        row = deepcopy(self.capture['article'])
        related = deepcopy(row)
        related['permalink'] = 'https://www.theverge.com/tech/other/iphone-tips'
        related['dek']['html'] = 'A neighboring description must stay with its own link.'
        row['modifiedAt'] = row.pop('publishedAt')
        candidates = self.m.parse_html_links(self.page(row, related=related),
                                             self.capture['captured_from'], self.source)
        by_url = {c.url: c for c in candidates}
        self.assertEqual(by_url[row['permalink']].feed_time_raw, '')
        self.assertEqual(by_url[related['permalink']].feed_time_raw, '')
        self.assertEqual(by_url[related['permalink']].summary, '')
        self.assertFalse(self.m.is_relevant_candidate(by_url[row['permalink']], self.source))

    def test_dated_usage_recall_is_source_neutral_and_not_a_navigation_escape(self):
        for name in ('The Verge', '9to5Mac', 'MacRumors'):
            source = source_named(self.m, name)
            with self.subTest(source=name):
                c = self.m.Candidate(name, 'https://' + source.domains[0] + '/2026/10/24/report/',
                    'Our tips for using the iPad mini', 'New ways to use the device.',
                    '2026-10-24T06:00:00+00:00',
                    publication_time_raw='2026-10-24T06:00:00+00:00')
                self.assertTrue(self.m.is_relevant_candidate(c, source))
                c.publication_time_raw = 'not a publication date'
                self.assertFalse(self.m.is_relevant_candidate(c, source))
        for title in ('Hard Reset or Force Restart Your iPhone 18',
                      'iPhone 18 Pro: Record Time-Lapse Videos in 4K',
                      'iPhone 17 vs iPhone 17 Pro', 'iPhone Cases', 'iPhone 17e'):
            with self.subTest(title=title):
                identity = self.m.title_led_identity(title, '')
                self.assertFalse(self.m.collection.sparse_apple_subject_needs_detail(
                    identity, has_lead=False, event_kind=self.m.detect_event_kind(title, '', []),
                    title=title, has_publication_time=True))

    def test_atom_updated_does_not_enable_publication_recall(self):
        stamp = '2026-10-24T06:00:00+00:00'
        published = '2026-10-23T14:00:00+00:00'
        entry = ('<title>Our tips for using the iPad mini</title>'
                 '<link href="https://www.theverge.com/tech/42/ipad-tips"/>'
                 '<summary>New ways to use the device.</summary>'
                 '<updated>' + stamp + '</updated>')
        for suffix in ('', '<published>' + published + '</published>'):
            c = self.m.parse_xml_feed('<feed><entry>' + entry + suffix + '</entry></feed>',
                                      self.source, self.source.feeds[0])[0]
            self.assertEqual(c.feed_time_raw, stamp)
            self.assertEqual(c.publication_time_raw, published if suffix else '')
            self.assertEqual(self.m.is_relevant_candidate(c, self.source), bool(suffix))
        row = self.capture['article']
        listed = self.m.parse_html_links(self.page(row), self.capture['captured_from'], self.source)[0]
        updated = self.m.Candidate(self.source.name, listed.url, listed.title,
                                   feed_time_raw=stamp)
        for order in ([listed, updated], [updated, listed]):
            merged = self.m.merge_duplicate_candidates(order)[0]
            self.assertEqual(merged.publication_time_raw, row['publishedAt'])
            self.assertTrue(self.m.is_relevant_candidate(merged, self.source))


if __name__ == '__main__':
    unittest.main()
