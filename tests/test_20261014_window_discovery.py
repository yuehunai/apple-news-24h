"""Rolling feeds must not hide current articles on published index pages."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest import mock

from test_relevance_rules import load_module


class WindowDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.capture = json.loads((Path(__file__).parent / 'fixtures/20261014_macrumors_pagination.json').read_text())
        cls.source = next(s for s in cls.m.build_sources(datetime(2026, 10, 14, tzinfo=timezone.utc)) if s.name == 'MacRumors')

    def test_real_next_pages_recover_article_after_it_rolls_out_of_feed(self):
        m, capture = self.m, self.capture
        pages = capture['pages']
        diagnostics = {}
        with mock.patch.object(m, 'fetch_url', side_effect=lambda url, *_a, **_k: pages.get(url)) as fetch:
            rows = m.collect_candidates(self.source, Path('/unused'), diagnostics,
                window_start_utc=datetime.fromisoformat(capture['window_start']))
        found = [r for r in rows if r.url == capture['target_url']]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].feed_time_raw, '2026-10-13T18:20:00+00:00')
        self.assertEqual(found[0].discovered_from, 'https://www.macrumors.com/2/')
        self.assertEqual(sum(c.args[0] == 'https://www.macrumors.com/2/' for c in fetch.call_args_list), 1)
        self.assertEqual(sum(c.args[0] == 'https://www.macrumors.com/3/' for c in fetch.call_args_list), 1)
        self.assertFalse(any(c.args[0] == 'https://www.macrumors.com/4/' for c in fetch.call_args_list))
        self.assertEqual(diagnostics['source_listing_pagination']['https://www.macrumors.com/']['stop_reason'], 'window-covered')
        self.assertFalse(diagnostics.get('collection_warnings'))

    @staticmethod
    def page(rows, next_link='/2/', tail=''):
        cards = ''.join('<article><h2><a href="/2026/10/14/report-' + str(n) + '/">Apple updates device ' + str(n) + '</a></h2>'
            + ('<time datetime="' + stamp + '"></time>' if stamp else '') + '</article>' for n, stamp in rows)
        return '<main>' + cards + '<nav><a rel="next" href="' + next_link + '">Older Posts</a></nav></main>' + tail

    def supplement(self, first, response, limit=240):
        m = self.m
        url = 'https://www.macrumors.com/'
        parse = lambda body, page: m.parse_html_links(body, page, self.source)
        initial = parse(first, url) if first is not None else []
        fetch, diagnostics = mock.Mock(return_value=response), {}
        rows = m.collection.supplement_macrumors_index_candidates(url, first, initial,
            datetime(2026, 10, 13, 13, 26, tzinfo=timezone.utc), limit, fetch, parse,
            lambda raw: m.parse_datetime_value(raw, self.source.default_tz), diagnostics)
        return rows, fetch, diagnostics

    def test_complete_first_page_does_not_fetch_next(self):
        _, fetch, diag = self.supplement(self.page([(1, '2026-10-13T12:00:00Z')]), None)
        fetch.assert_not_called()
        self.assertFalse(diag.get('collection_warnings'))

    def test_missing_or_unordered_dates_and_old_sidebar_do_not_end_window(self):
        second = self.page([(3, '2026-10-13T18:00:00Z'), (4, '2026-10-13T12:00:00Z')])
        for first_rows in ([(1, ''), (2, '2026-10-13T12:00:00Z')],
                           [(1, '2026-10-12T12:00:00Z'), (2, '2026-10-14T12:00:00Z')]):
            first = self.page(first_rows, tail='<aside><time datetime="2020-01-01T00:00:00Z">Old</time></aside>')
            rows, fetch, diag = self.supplement(first, second)
            fetch.assert_called_once()
            self.assertTrue(any('report-3' in c.url for c in rows))
            self.assertFalse(diag.get('collection_warnings'))

    def test_untrusted_or_missing_next_link_is_a_visible_coverage_gap(self):
        for link in ['https://other.example/2/', '/?page=2', '/', '/2/#section']:
            with self.subTest(link=link):
                _, fetch, diag = self.supplement(self.page([(1, '2026-10-14T12:00:00Z')], link), None)
                fetch.assert_not_called()
                self.assertEqual(diag['collection_warnings'][0]['coverage'], 'unconfirmed')

    def test_truncated_page_cannot_claim_its_dropped_boundary(self):
        first = self.page([(1, '2026-10-14T12:00:00Z')])
        second = self.page([(2, '2026-10-13T18:00:00Z'), (3, '2026-10-13T12:00:00Z')])
        # The generic first-page scan also spends a slot on its navigation link.
        rows, fetch, diag = self.supplement(first, second, limit=3)
        fetch.assert_called_once()
        self.assertEqual(len({c.url for c in rows}), 2)
        self.assertEqual(diag['collection_warnings'][0]['reason'], 'candidate-budget')
        self.assertFalse(any('report-3' in c.url for c in rows))

    def test_failed_or_repeated_page_stops_and_reports_gap(self):
        first = self.page([(1, '2026-10-14T12:00:00Z')])
        for response, reason in [(None, 'request-failed'), ('<main></main>', 'empty-page'), (first, 'no-progress')]:
            _, fetch, diag = self.supplement(first, response)
            fetch.assert_called_once()
            self.assertEqual(diag['collection_warnings'][0]['reason'], reason)

    def test_article_next_link_cannot_skip_index_pages(self):
        first = self.page([(1, '2026-10-14T12:00:00Z')]).replace('</article>',
            '<nav><a rel="next" href="/300/">Next historical story</a></nav></article>')
        second = self.page([(2, '2026-10-13T12:00:00Z')])
        _, fetch, diag = self.supplement(first, second)
        fetch.assert_called_once_with('https://www.macrumors.com/2/')
        self.assertFalse(diag.get('collection_warnings'))


if __name__ == '__main__':
    unittest.main()
