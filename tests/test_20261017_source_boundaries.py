"""Keep publisher discovery surfaces separate from article evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest import mock

from test_relevance_rules import load_module


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.sources = cls.m.build_sources(datetime(2026, 10, 17, tzinfo=timezone.utc))
        cls.capture = json.loads((Path(__file__).parent /
            'fixtures/20261017_navigation_sources.json').read_text())

    def test_category_pagination_recovers_an_in_window_report_off_the_first_page(self):
        m = self.m
        row = json.loads((Path(__file__).parent / 'fixtures/20261017_listing_pages.json').read_text())
        source = next(s for s in self.sources if s.name == '快科技')
        responses = {row['page_url']: row['first_page'], row['second_url']: row['second_response']}
        diagnostics = {}
        with mock.patch.object(m, 'fetch_url', side_effect=lambda url, *_a, **_k: responses.get(url)) as fetch:
            found = m.collect_candidates(source, Path('/unused'), diagnostics,
                window_start_utc=datetime.fromisoformat(row['window_start']))
        target = [c for c in found if c.url == row['target_url']]
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0].feed_time_raw, '2026-10-16 14:36')
        self.assertIn(row['second_url'], [call.args[0] for call in fetch.call_args_list])
        self.assertEqual(diagnostics['source_listing_pagination'][row['page_url']]['stop_reason'], 'window-covered')

    def test_category_pagination_does_not_claim_coverage_on_failed_or_repeated_pages(self):
        m = self.m
        row = json.loads((Path(__file__).parent / 'fixtures/20261017_listing_pages.json').read_text())
        source = next(s for s in self.sources if s.name == '快科技')
        for response, reason in ((None, 'request-failed'), ('NewsList({});', 'invalid-response'),
                                 (row['second_response'], 'no-progress')):
            with self.subTest(reason=reason):
                diagnostics = {}
                fetch = mock.Mock(return_value=response)
                m.collection.supplement_mydrivers_category_candidates(
                    row['page_url'], row['first_page'], [],
                    datetime(2026, 10, 1, tzinfo=timezone.utc), 240, fetch,
                    lambda body, url: m.parse_html_links(body, url, source),
                    lambda raw: m.parse_datetime_value(raw, source.default_tz), diagnostics)
                self.assertEqual(diagnostics['source_listing_pagination'][row['page_url']]['stop_reason'], reason)
                self.assertTrue(diagnostics['collection_warnings'])
                self.assertLessEqual(fetch.call_count, 2)

    def test_category_pagination_keeps_its_budget_and_category_protocol(self):
        m = self.m
        row = json.loads((Path(__file__).parent / 'fixtures/20261017_listing_pages.json').read_text())
        source = next(s for s in self.sources if s.name == '快科技')
        for limit, reason in ((21, 'candidate-budget'), (240, 'window-covered')):
            diagnostics = {}
            fetch = mock.Mock(return_value=row['second_response'])
            found = m.collection.supplement_mydrivers_category_candidates(
                'https://news.mydrivers.com/jiadianshuma.html',
                row['first_page'].replace('1028', '804'), [],
                datetime.fromisoformat(row['window_start']), limit, fetch,
                lambda body, url: m.parse_html_links(body, url, source),
                lambda raw: m.parse_datetime_value(raw, source.default_tz), diagnostics)
            self.assertEqual(fetch.call_count, 1)
            self.assertIn('getdatelist_search.aspx?ac=804&', fetch.call_args.args[0])
            self.assertLessEqual(len({c.url for c in found}), limit)
            self.assertEqual(next(iter(diagnostics['source_listing_pagination'].values()))['stop_reason'], reason)

    def test_captured_channel_navigation_cannot_become_a_dated_article(self):
        m, row = self.m, self.capture
        source = next(s for s in self.sources if s.name == 'IT之家')
        markup = row['navigation_anchor'] + row['article_anchor']
        with mock.patch.object(m, 'fetch_url', side_effect=lambda url, *_a, **_k:
                               markup if url == row['captured_from'] else None):
            found = m.collect_candidates(source, Path('/unused'), {})
        self.assertEqual([c.url for c in found], [row['article_url']])
        selected = m.select_detail_candidates(found, {source.name: source}, 20)
        self.assertEqual([c.url for c in selected], [row['article_url']])

    def test_home_and_configured_discovery_pages_do_not_inherit_link_news(self):
        m = self.m
        for source in self.sources:
            urls = list(source.pages) + list(source.feeds) + list(source.wordpress_posts_apis)
            urls += ['https://' + source.domains[0] + '/',
                     'https://' + source.domains[0] + '/?utm_source=apple']
            for url in urls:
                with self.subTest(source=source.name, url=url):
                    candidate = m.Candidate(source.name, url,
                        'Apple announces a new iPhone', 'Apple announced a new iPhone today.')
                    self.assertFalse(m.collection.source_article_url_allowed(url, source))
                    self.assertFalse(m.is_relevant_candidate(candidate, source))

    def test_article_paths_remain_eligible_across_the_nine_sources(self):
        paths = {
            'MacRumors': '/2026/10/17/apple-announces-new-iphone/',
            '9to5Mac': '/2026/10/17/apple-announces-new-iphone/',
            'AppleInsider': '/articles/26/10/17/apple-announces-new-iphone',
            'The Verge': '/tech/1013314/apple-announces-new-iphone',
            'Apple Newsroom': '/newsroom/2026/10/apple-announces-new-iphone/',
            'IT之家': '/1/014/209.htm', '爱范儿': '/1684640',
            '快科技': '/1/1158/1158173.htm',
            'cnBeta': '/articles/tech/1582430.htm',
        }
        for source in self.sources:
            with self.subTest(source=source.name):
                self.assertTrue(self.m.collection.source_article_url_allowed(
                    'https://' + source.domains[0] + paths[source.name], source))

    def test_body_event_dates_cannot_override_publication_evidence(self):
        m = self.m
        source = next(s for s in self.sources if s.name == 'MacRumors')
        for body in (
            'Apple opens preorders on November 2, 2026 at 8:00 am PT.',
            'Apple first opened preorders on October 1, 2025 at 8:00 am PT.',
            'Apple opens preorders on <time datetime="2026-11-02T16:00:00Z">November 2</time>.',
        ):
            page = '<article><h1>Apple preorder report</h1><p>' + body + '</p></article>'
            for feed in ('2026-10-17T08:00:00Z', '2026-10-10T08:00:00Z', ''):
                with self.subTest(body=body, feed=feed):
                    candidate = m.Candidate(source.name, 'https://www.macrumors.com/2026/10/17/report/',
                                            'Apple preorder report', feed_time_raw=feed)
                    result = m.extract_article(candidate, source, page, {})
                    expected = m.parse_datetime_value(feed, source.default_tz).astimezone(timezone.utc) if feed else None
                    self.assertEqual(result[3], expected)
                    self.assertNotEqual(result[6], 'detail')

    def test_publication_roles_survive_inline_elements_and_article_prose(self):
        m = self.m
        stamp = '2026-10-17T08:00:00Z'
        body = '<article><p>Preorders open November 2, 2026 at 8:00 am PT.</p></article>'
        for header in ('<meta property="article:published_time" content="' + stamp + '">',
                       '<div class="byline">Published <time datetime="' + stamp + '">October 17</time> by Alex</div>',
                       '<div class="meta"><span>2026-10-17 08:00:00</span><span>Source: News</span></div>'):
            with self.subTest(header=header):
                candidates = m.extract_time_candidates(header + body)
                self.assertTrue(candidates)
                self.assertFalse(any('November' in raw for raw, _ in candidates))

    def test_nested_updates_and_event_nodes_do_not_supply_publication(self):
        m = self.m
        page = ('<div class="byline">Published October 17, 2026 at 1:00 am PT '
                '<span>Updated October 18, 2026 at 2:00 am PT</span></div>')
        self.assertEqual(m.extract_time_candidates(page),
                         [('October 17, 2026 at 1:00 am PT', 'body date pattern')])
        for markup in (
            '<div class="event-date">November 2, 2026 at 8:00 am PT preorders open.</div>',
            '<div class="event-date"><time datetime="2026-11-02T16:00:00Z">November 2, 2026 at 8:00 am PT</time></div>',
            '<div class="meta"><p>Apple opens preorders November 2, 2026 at 8:00 am PT.</p></div>',
            '<section itemscope itemtype="https://schema.org/Event"><time itemprop="startDate" datetime="2026-11-02T16:00:00Z">November 2, 2026 at 8:00 am PT</time></section>',
            '<time itemprop="endDate" datetime="2026-11-02T16:00:00Z">November 2, 2026 at 8:00 am PT</time>',
        ):
            with self.subTest(markup=markup):
                self.assertEqual(m.extract_time_candidates('<article>' + markup + '</article>'), [])
        page = '<p>Published <time datetime="2026-10-17T07:00:00Z">17 October</time> by Alex</p>'
        self.assertIn(('2026-10-17T07:00:00Z', 'time datetime'), m.extract_time_candidates(page))


if __name__ == '__main__':
    unittest.main()
