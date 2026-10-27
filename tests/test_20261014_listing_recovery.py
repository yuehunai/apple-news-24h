"""Recover business-empty listing responses without claiming full coverage."""
from datetime import datetime, timezone
import json
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from test_relevance_rules import load_module


class ListingRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.capture = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())['ithome_pagination']
        cls.source = next(s for s in cls.m.build_sources(datetime(2026, 10, 14, tzinfo=timezone.utc)) if s.name == 'IT之家')

    def run_pages(self, responses):
        m, c = self.m, self.capture
        first = m.parse_html_links(c['first_html'], c['page_url'], self.source)
        fetch, diagnostics = mock.Mock(side_effect=responses), {}
        with mock.patch.object(m.collection.time, 'sleep') as sleep:
            result = m.collection.supplement_ithome_tag_candidates(
                c['page_url'], c['first_html'], first,
                datetime(2026, 10, 13, 7, 53, tzinfo=timezone.utc), 240,
                fetch, lambda body, url: m.parse_html_links(body, url, self.source),
                lambda raw: m.parse_datetime_value(raw, 'Asia/Shanghai'), diagnostics)
        return result, fetch, diagnostics, sleep

    @staticmethod
    def empty():
        return json.dumps({'success': True, 'content': {'html': '', 'count': 0}})

    def test_empty_then_current_page_recovers_same_endpoint(self):
        result, fetch, diagnostics, sleep = self.run_pages([self.empty(), json.dumps(self.capture['response'])])
        self.assertIn(self.capture['target_url'], [c.url for c in result])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[0], fetch.call_args_list[1])
        sleep.assert_called_once_with(0.5)
        detail = diagnostics['source_listing_pagination'][self.capture['page_url']]
        self.assertEqual(detail['stop_reason'], 'window-covered')
        self.assertEqual(detail['empty_page_retries'], 1)
        self.assertEqual(detail['request_attempts'], 2)
        self.assertFalse(diagnostics.get('collection_warnings'))

    def test_persistent_empty_is_bounded_and_not_window_coverage(self):
        result, fetch, diagnostics, _ = self.run_pages([self.empty(), self.empty()])
        self.assertEqual(result, [])
        self.assertEqual(fetch.call_count, 2)
        detail = diagnostics['source_listing_pagination'][self.capture['page_url']]
        self.assertEqual(detail['stop_reason'], 'empty-page')
        self.assertEqual(detail['last_page_count'], 0)
        self.assertEqual(diagnostics['collection_warnings'][0]['coverage'], 'unconfirmed')

    def test_normal_page_has_no_extra_request_or_delay(self):
        result, fetch, diagnostics, sleep = self.run_pages([json.dumps(self.capture['response'])])
        self.assertIn(self.capture['target_url'], [c.url for c in result])
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()
        self.assertFalse(diagnostics.get('collection_warnings'))

    def test_initial_listing_failure_is_visible_even_when_other_entries_work(self):
        m, c = self.m, self.capture
        for failed_body, reason in ((None, 'request-failed'), ('<html>Temporarily unavailable</html>', 'pagination-unavailable')):
            diagnostics = {}
            def fetch(url, *_args, **_kwargs):
                return failed_body if url == c['page_url'] else c['first_html']
            with mock.patch.object(m, 'fetch_url', side_effect=fetch) as transport:
                candidates = m.collect_candidates(self.source, Path('/unused-cache'), diagnostics,
                    window_start_utc=datetime(2026, 10, 13, 7, 53, tzinfo=timezone.utc))
            self.assertTrue(candidates)
            self.assertFalse(diagnostics.get('failed_sources'))
            self.assertEqual(diagnostics['collection_warnings'][0]['reason'], reason)
            self.assertEqual(diagnostics['collection_warnings'][0]['coverage'], 'unconfirmed')
            self.assertFalse(any('/category/tagpage?' in call.args[0] for call in transport.call_args_list))

    def test_static_first_page_can_establish_coverage_without_pagination(self):
        diagnostics, fetch = {}, mock.Mock()
        start = datetime(2026, 10, 13, tzinfo=timezone.utc)
        row = self.m.Candidate('IT之家', 'https://www.ithome.com/1/012/001.htm', 'Apple current report', feed_time_raw=start.isoformat())
        self.m.collection.supplement_ithome_tag_candidates(self.capture['page_url'], '<p>Static listing</p>', [row], start, 240,
            fetch, mock.Mock(), lambda raw: datetime.fromisoformat(raw), diagnostics)
        fetch.assert_not_called()
        self.assertFalse(diagnostics.get('collection_warnings'))

    def test_failed_retry_stops_without_page_advance(self):
        for second, reason in [(None, 'request-failed'), ('{invalid', 'invalid-response')]:
            with self.subTest(reason=reason):
                result, fetch, diagnostics, _ = self.run_pages([self.empty(), second])
                self.assertEqual(result, [])
                self.assertEqual(fetch.call_count, 2)
                self.assertEqual(fetch.call_args_list[0], fetch.call_args_list[1])
                self.assertEqual(diagnostics['source_listing_pagination'][self.capture['page_url']]['stop_reason'], reason)
                self.assertEqual(diagnostics['collection_warnings'][0]['coverage'], 'unconfirmed')

    def test_coverage_warning_is_visible_without_verbose_diagnostics(self):
        warning = {'source': 'IT之家', 'url': self.capture['page_url'],
                   'reason': 'empty-page', 'coverage': 'unconfirmed'}
        def collect(_sources, _cache, diagnostics, **_kwargs):
            diagnostics['collection_warnings'] = [warning]
            return []
        with TemporaryDirectory() as directory:
            args = self.m.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with mock.patch.object(self.m, 'collect_candidates_from_sources', side_effect=collect):
                result = self.m.run(args)
        self.assertEqual(result['collection_warnings'], [warning])
        self.assertNotIn('diagnostics', result)
        with TemporaryDirectory() as directory, mock.patch.object(self.m, 'run', return_value=result), mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            code = self.m.main(['--cache-dir', str(Path(directory) / 'cache'), '--format', 'json', '--output', str(Path(directory) / 'latest.json')])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())['collection_warnings'], [warning])

    def test_output_status_does_not_repeat_saved_review_material(self):
        queue = [{'id': 'evidence-review:source', 'title': 'Review material',
                  'required': True, 'source_urls': [], 'evidence_id': 'source', 'reason': 'unassigned',
                  'unprocessed_evidence': [{'unit_id': 'body', 'text': 'Source evidence. ' * 10000}]}]
        result = {'events': [], 'final_brief_queue': queue,
                  'required_final_brief_titles': self.m.required_final_brief_titles(queue)}
        with TemporaryDirectory() as directory, mock.patch.object(self.m, 'run', return_value=result), mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            target = Path(directory) / 'latest.json'
            code = self.m.main(['--cache-dir', str(Path(directory) / 'cache'),
                                '--format', 'json', '--output', str(target)])
            self.assertEqual(code, 0)
            saved = json.loads(target.read_text())
            self.assertEqual(saved['final_brief_queue'], queue)
            self.assertEqual(saved['required_final_brief_titles'], result['required_final_brief_titles'])
            status = json.loads(output.getvalue())
            self.assertEqual(status['required_final_brief_events'], 1)
            self.assertFalse('required_final_brief_titles' in status)
            self.assertNotIn('Source evidence.', output.getvalue())
            self.assertEqual(status['output'], str(target))
            self.assertTrue(Path(status['brief_output']).is_file())

    def test_entire_source_discovery_failure_is_visible_by_default(self):
        source = next(s for s in self.m.build_sources(datetime(2026, 10, 27, tzinfo=timezone.utc)) if s.name == 'AppleInsider')
        diagnostics = {}
        with mock.patch.object(self.m, 'fetch_url', return_value=None):
            self.assertEqual(self.m.collect_candidates(source, Path('/unused-cache'), diagnostics), [])
        self.assertEqual(diagnostics['failed_sources'], [source.name])
        warning, = diagnostics['collection_warnings']
        self.assertEqual((warning['source'], warning['reason'], warning['coverage']),
                         (source.name, 'source-discovery-failed', 'unconfirmed'))

    def test_archive_success_does_not_hide_primary_discovery_failure(self):
        source = next(s for s in self.m.build_sources(datetime(2026, 10, 27, tzinfo=timezone.utc)) if s.name == '9to5Mac')
        candidate = self.m.Candidate(source.name, 'https://9to5mac.com/2026/10/26/apple-update/', 'Apple releases iOS 27.2')
        primary = [*source.feeds, *source.wordpress_posts_apis, source.pages[0]]
        for recovered in [None, *primary]:
            with self.subTest(recovered=recovered):
                diagnostics = {}
                def fetch(url, *_args, **_kwargs):
                    return 'listing' if url in (source.pages[-1], recovered) else None
                with mock.patch.object(self.m, 'fetch_url', side_effect=fetch), \
                     mock.patch.object(self.m, 'parse_html_links', return_value=[candidate]), \
                     mock.patch.object(self.m, 'parse_xml_feed', return_value=[]), \
                     mock.patch.object(self.m, 'parse_wordpress_posts_api', return_value=[]):
                    self.assertTrue(self.m.collect_candidates(source, Path('/unused-cache'), diagnostics))
                self.assertFalse(diagnostics.get('failed_sources'))
                self.assertEqual(bool(diagnostics.get('collection_warnings')), recovered is None)
                if recovered is None:
                    self.assertEqual(diagnostics['collection_warnings'][0]['reason'], 'primary-discovery-failed')

    def test_budget_boundary_confirms_only_a_fully_consumed_page(self):
        m = self.m
        start = datetime(2026, 10, 13, tzinfo=timezone.utc)
        def candidate(number, date):
            return m.Candidate('IT之家', f'https://www.ithome.com/1/012/{number}.htm',
                               'Apple updates a feature', feed_time_raw=date)
        first = [candidate(1, '2026-10-14T01:00:00+00:00')]
        boundary = candidate(3, start.isoformat())
        for rows, reason in [([boundary], 'window-covered'),
                             ([candidate(2, '2026-10-14T00:00:00+00:00'), boundary], 'candidate-budget')]:
            with self.subTest(reason=reason):
                diagnostics = {}
                fetch = mock.Mock(return_value=json.dumps({'success': True, 'content': {'html': 'rows', 'count': len(rows)}}))
                result = m.collection.supplement_ithome_tag_candidates(
                    self.capture['page_url'], '/category/tagpage?', first, start, 2,
                    fetch, lambda *_: rows, lambda raw: datetime.fromisoformat(raw), diagnostics)
                self.assertEqual(len(result), 1)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(diagnostics['source_listing_pagination'][self.capture['page_url']]['stop_reason'], reason)
                self.assertEqual(bool(diagnostics.get('collection_warnings')), reason == 'candidate-budget')

    def test_mydrivers_category_discovers_report_after_shared_sidebar_rolls_off(self):
        capture = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())['mydrivers_category_discovery']
        source = next(s for s in self.m.build_sources(datetime(2026, 10, 14, tzinfo=timezone.utc)) if s.name == '快科技')
        def fetch(url, *_args, **_kwargs):
            return capture['html'] if url == capture['page_url'] else '<html></html>'
        with mock.patch.object(self.m, 'fetch_url', side_effect=fetch):
            rows = self.m.collect_candidates(source, Path('/unused-cache'), {})
        retained = [row for row in rows if row.url == capture['target_url']]
        self.assertEqual(len(retained), 1)
        self.assertIn('Apple Watch', retained[0].title)
        self.assertFalse(any('1157440.htm' in row.url for row in rows))
