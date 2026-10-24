"""A dated alternate listing must prove coverage before retiring a warning."""
from datetime import datetime, timezone
from pathlib import Path
import unittest
from test_relevance_rules import load_module

class CalendarRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.source = next(s for s in cls.m.build_sources(datetime.now(timezone.utc)) if s.name == 'IT之家')

    def page(self, *dates):
        return '<ul class="datel">' + ''.join(f'<li><a class="c" data-ot="{d}">[iPhone之家]</a><a class="t" href="https://www.ithome.com/1/017/{n}.htm">Apple new functionality</a></li>' for n,d in enumerate(dates)) + '</ul>'

    def recover(self, body, limit=240, window_end=None):
        calls = []
        root = 'https://www.ithome.com/list/'
        def fetch(url):
            calls.append(url)
            return 'var date = "2026-10-24"; var _LISTPAGE_URL_REG_ = "$Y-$M-$D.html";' if url == root else body
        diagnostics = {'collection_warnings':[{'source':'IT之家','coverage':'unconfirmed'}, {'source':'MacRumors','coverage':'unconfirmed'}]}
        rows = self.m.collection.recover_ithome_calendar_candidates(datetime(2026,10,24,1,tzinfo=timezone.utc),limit,fetch,
            lambda text,url:self.m.parse_html_links(text,url,self.source),
            lambda raw:self.m.parse_datetime_value(raw,'Asia/Shanghai'),diagnostics,
            window_end=window_end or datetime(2026,10,24,5,tzinfo=timezone.utc))
        return rows,diagnostics,calls

    def test_offset_window_and_complete_calendar_recover(self):
        rows,d,calls = self.recover(self.page('2026-10-24T12:00:00+08:00','2026-10-24T08:59:59+08:00'))
        self.assertEqual(len(rows),1)
        self.assertEqual(d['ithome_calendar_recovery']['stop_reason'],'window-covered')
        self.assertEqual([w['source'] for w in d['collection_warnings']],['MacRumors'])
        self.assertEqual(len(d['recovered_listing_warnings']),1)
        self.assertEqual(calls[-1],'https://www.ithome.com/list/2026-10-24.html')

    def test_empty_unordered_wrong_day_and_budget_do_not_claim_coverage(self):
        cases = [('',240), (self.page('2026-10-24T08:00:00+08:00','2026-10-24T12:00:00+08:00'),240),
            (self.page('2026-10-23T12:00:00+08:00'),240),
            (self.page('2026-10-24T12:00:00+08:00','2026-10-24T11:00:00+08:00','2026-10-24T08:00:00+08:00'),1)]
        for body,limit in cases:
            with self.subTest(limit=limit,body=body):
                _,d,_ = self.recover(body,limit)
                self.assertNotEqual(d['ithome_calendar_recovery']['stop_reason'],'window-covered')
                self.assertEqual(len(d['collection_warnings']),2)

    def test_old_calendar_index_cannot_clear_a_new_window_warning(self):
        rows,d,calls=self.recover(self.page('2026-10-24T08:00:00+08:00'),
            window_end=datetime(2026,10,25,5,tzinfo=timezone.utc))
        self.assertEqual(rows,[])
        self.assertEqual(len(calls),1)
        self.assertEqual(d['ithome_calendar_recovery']['stop_reason'],'stale-calendar-index')
        self.assertEqual(len(d['collection_warnings']),2)
