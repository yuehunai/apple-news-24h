"""Source-owned actions from the October 10 capture, with adjacent boundaries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

GROUPS = {
    'component_orders': ['b4180f3caf887aae7379cef6', '144f000d07ae9875c558aa5a', 'f8b2300f149220abf71aae72', '3ef9295e756475897c114144', 'a75b6b9f74cf430e316172a3'],
    'sales_w40': ['7a03362a402ca56d48ee8e66', 'cc6cace6903f9b6a0bcf4adb'],
    'vintage': ['84f75ec7e0e32d8f4e4f0a79', '241dcac0b82ccea18647147f', 'd90ee8c1e49b8d7b8388e8af', '09c645565be200dae781827d'],
    'trademark': ['228428cc17ea44e481d18201', 'be6651a3af03598f6c62ef53', 'bd61de83aebe23b072d6a1c3'],
    'startup': ['01bc9cfe565ef78e3f8a595a', '9c0f9715e02c097a047c788a', '8ce0cadfffef8a348852ef2a'],
    'pc_shipments': ['dcaac0c3ca6a16394ce5e1bd', 'b06100d65cd6e2cc61f90841'],
}


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261010_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 10, tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_app_recommendations_do_not_borrow_device_specifications(self):
        cases = [
            ('这三个摄影 App，配得上你全新的 iPhone 18 Pro',
             '过去的 20 天里，我们用 iPhone 18 Pro 系列拍了 3000 多张照片，也试了十几款相机 App。我们最终推荐三种适合 iPhone 的摄影方式。苹果公布的可变光圈能够收至 f/4，Gloam 提供胶片滤镜。'),
            ('These camera apps deserve a place on your new iPhone',
             'We tested camera apps and recommend our favorite options. Apple revealed the iPhone camera with a variable aperture and a new sensor.'),
            ('最适合新 iPhone 的相机应用',
             '苹果今天发布配备新传感器的 iPhone。我们推荐三款第三方相机应用。'),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertEqual(events[0].relevance_tier, 'weak')
        current = article_for(self.m, 'Apple updates Final Cut Camera with new exposure controls',
            'Apple released Final Cut Camera 3.0 today with new manual exposure controls for iPhone. We recommend testing the new controls.')
        self.assertEqual(self.m.cluster_articles([current])[0].relevance_tier, 'strong')
        current = article_for(self.m, '苹果更新最值得尝试的相机应用',
            '苹果今天发布 Final Cut Camera 3.0，新增曝光控制。我们推荐试用新的功能。')
        self.assertEqual(self.m.cluster_articles([current])[0].relevance_tier, 'strong')

    def test_duplicate_reports_merge_by_owned_action(self):
        for name, ids in GROUPS.items():
            for order in (ids, ids[::-1]):
                with self.subTest(group=name, reversed=ids != order):
                    events, _ = self.cluster_sources(*order)
                    self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
                    self.assertEqual(self.source_ids(events[0]), set(ids))
                    self.assertIn(events[0].relevance_tier, {'strong', 'ecosystem'})

    def test_market_actions_and_periods_do_not_cross(self):
        ids = GROUPS['sales_w40'] + ['693d03d3b93a7ab4ccdb5bab', '2c913a2f1dd960a61059fd33', '5a6ce9e74c531e40dce67046']
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 4, [(e.title, self.source_ids(e)) for e in events])
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_partner_rollout_and_accessory_promotion_have_own_tiers(self):
        cases = [('d6c87ebf5d173ecfdb92306e', 'ecosystem'), ('3ebf326253b89b61ab9fd7a6', 'weak'),
                 ('a58b9b71318bb9606157bd1c', 'weak')]
        for sid, tier in cases:
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual(events[0].relevance_tier, tier)

    def test_incomplete_rebuttal_is_not_an_affirmative_order_report(self):
        events, _ = self.cluster_sources(*GROUPS['component_orders'], '86de522f591c410c795be64e')
        self.assertEqual(len(events), 2)
        company, _ = self.cluster_sources('abc99ae6aa26aeefe0189251')
        self.assertEqual(company[0].category, 'hardware_products')

    def test_market_subject_stage_and_actor_guards(self):
        rows = [
            ('Apple cuts iPhone 19 Pro component orders', 'Sources report Apple cut October component orders for iPhone 19 Pro by 12%.'),
            ('Apple increases iPhone 19 Pro component orders', 'Sources report Apple increased October component orders for iPhone 19 Pro by 12%.'),
            ('Apple cuts iPhone 20 Pro component orders', 'Sources report Apple cut October component orders for iPhone 20 Pro by 12%.'),
            ('Apple cuts iPhone 19 Pro assembly orders', 'Sources report Apple cut October whole-unit assembly orders for iPhone 19 Pro by 12%.'),
            ('Apple shares fall after iPhone 19 Pro order cuts', 'Apple shares fell 3% today after a report of lower component orders.'),
        ]
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m, *row) for row in rows])), len(rows))

    def test_incomplete_capture_has_required_review_without_promoting_it(self):
        article = self.source_articles('86de522f591c410c795be64e')[0]
        reviews = []
        evidence = article.evidence
        failures = [{'url': evidence.url, 'error': 'HTTPError: HTTP Error 403: Forbidden'}]
        self.m.add_source_capture_reviews({evidence.article_id: evidence}, reviews, failures)
        self.assertEqual(len(reviews), 1)

        self.assertEqual(reviews[0]['capture_status'], 'discovery-only')
        self.assertTrue(reviews[0]['required'])
        self.assertEqual(reviews[0]['fetch_error'], failures[0]['error'])
        self.assertEqual(reviews[0]['unprocessed_evidence'], [])
        scaffold = self.m.render_brief_scaffold({'events': [], 'final_brief_queue': reviews})
        self.assertIn(evidence.url, scaffold)
        self.assertIn(evidence.article_id, scaffold)
        self.assertIn(reviews[0]['reason'], scaffold)
        self.m.add_source_capture_reviews({evidence.article_id: evidence}, reviews, failures)
        self.assertEqual(len(reviews), 1)
        complete = self.source_articles(GROUPS['component_orders'][0])[0].evidence
        self.m.add_source_capture_reviews({complete.article_id: complete}, reviews, [])
        self.assertEqual(len(reviews), 1)

    def test_home_code_reports_keep_control_and_preprovisioning_distinct(self):
        ids = ['84fe82da237175b9d0759d38', '5ac64b7d2caf0123b2aace24', '80935a04018fd16defa99c1d',
               '76ce753bca9d6cd68ca0e360', 'cd637466fcd0af30bda63f88']
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 2, [(e.title, self.source_ids(e)) for e in events])
        self.assertTrue(all(e.category == 'software_systems' for e in events))
        controls = max(events, key=lambda e: len(e.articles))
        self.assertEqual(self.source_ids(controls), set(ids))
        pairing = next(e for e in events if e is not controls)
        self.assertEqual(self.source_ids(pairing), {'80935a04018fd16defa99c1d'})

    def test_market_measurements_keep_actor_period_and_polarity(self):
        pairs = {
'order_months': [('Apple cuts iPhone 19 Pro component orders for October','Sources report Apple cut October component orders for iPhone 19 Pro by 12%.'),('Apple cuts iPhone 19 Pro component orders for November','Sources report Apple cut November component orders for iPhone 19 Pro by 12%.')],
'order_owner': [('Apple cuts iPhone 19 Pro component orders','Sources report Apple cut October component orders for iPhone 19 Pro by 12%.'),('Foxconn cuts iPhone 19 Pro component orders','Foxconn cut component orders for iPhone 19 Pro by 12%. Apple has not changed its orders.')],
'order_negation': [('Apple cuts iPhone 19 Pro component orders','Sources report Apple cut October component orders for iPhone 19 Pro by 12%.'),('Apple has no plans to cut iPhone 19 Pro component orders','Sources say Apple has no plans to cut component orders for iPhone 19 Pro in October.')],
'order_supplier': [('Apple cuts iPhone 19 Pro component orders','Sources report Apple cut October component orders for iPhone 19 Pro by 12%.'),('Apple supplier Foxconn cuts iPhone 19 Pro component orders','Apple supplier Foxconn cut October component orders for iPhone 19 Pro by 12%. Apple has not changed its orders.')],
'pc_scope': [('Apple Mac shipments grow in China','IDC reports Apple Mac shipments rose 12% in China in Q3 2026. The PC market grew 5%.'),('Apple Mac shipments grow worldwide','IDC reports Apple Mac shipments rose 12% worldwide in Q3 2026. The PC market grew 5%.')],
'sales_scope': [('iPhone 19 Pro sales jump in China','iPhone 19 Pro sales reached 500,000 units in China in W40.'),('iPhone 19 Pro sales jump worldwide','iPhone 19 Pro sales reached 500,000 units worldwide in W40.')],
'sales_product': [('iPhone 19 Pro sales jump','iPhone 19 Pro Max sales reached 500,000 units in W40.'),('iPhone 19 Pro sales rise','iPhone 19 Pro sales reached 500,000 units in W40.')],
'sales_negation': [('iPhone 19 Pro sales rise','iPhone 19 Pro sales reached 500,000 units in W40.'),('iPhone 19 Pro sales did not reach 500,000','iPhone 19 Pro sales did not reach 500,000 units in W40.')],
}
        for name, rows in pairs.items():
            for ordered in (rows, rows[::-1]):
                with self.subTest(boundary=name, order=ordered):
                    events = self.m.cluster_articles([article_for(self.m, *row) for row in ordered])
                    self.assertEqual(len(events), 2, [(e.title, [a.title for a in e.articles]) for e in events])

    def test_unknown_region_does_not_bridge_conflicting_reports(self):
        rows = [
            ('Apple Mac shipments grow in China', 'IDC reports Apple Mac shipments rose 12% in China in Q3 2026. The PC market grew 5%.'),
            ('Apple Mac shipments grow worldwide', 'IDC reports Apple Mac shipments rose 12% worldwide in Q3 2026. The PC market grew 5%.'),
            ('Apple Mac shipments grow', 'IDC reports Apple Mac shipments rose 12% in Q3 2026. The PC market grew 5%.'),
        ]
        for ordered in (rows, rows[::-1]):
            events = self.m.cluster_articles([article_for(self.m, *row) for row in ordered])
            self.assertEqual(len(events), 2)
            self.assertFalse(any({rows[0][0], rows[1][0]} <= {a.title for a in e.articles} for e in events))

    def test_equivalent_sales_units_keep_one_measurement(self):
        rows = [
            ('iPhone 19 Pro sales surge in China', 'iPhone 19 Pro sales reached 500,000 units in China in W40.'),
            ('iPhone 19 Pro 中国销量增长', 'iPhone 19 Pro 销量达到 50 万台，中国 W40 统计结果公布。'),
        ]
        events = self.m.cluster_articles([article_for(self.m, *row) for row in rows])
        self.assertEqual(len(events), 1)

    def test_device_reuse_does_not_promote_a_third_party_project(self):
        for detail in ['The museum exhibited a visual replica using old Mac mini computers.',
                       'The museum plans to test the cluster at 2 teraflops using matrix multiplication.',
                       'For comparison, a separate Ryzen cluster achieved 2 teraflops in matrix tests.',
                       'The museum tested its Ryzen cluster with matrix multiplication and achieved 2 teraflops.',
                       'The museum also owns a Ryzen cluster. It tested this cluster with matrix multiplication and achieved 2 teraflops.',
                       'The museum has not achieved 2 teraflops in matrix tests of this cluster.',
                       'The museum estimates that the cluster would have reached 2 teraflops in matrix tests.']:
            article = article_for(self.m, 'Museum builds a Nova-7 replica with 20 Mac mini computers', detail)
            self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'weak')
        positive = article_for(self.m, 'Apple introduces Mac mini anniversary replica for museum exhibition',
            'Apple introduced a Mac mini replica for exhibition in a museum.')
        self.assertEqual(self.m.cluster_articles([positive])[0].relevance_tier, 'strong')

    def test_device_cluster_benchmark_is_not_only_a_replica_showcase(self):
        ids = ['22d9ed741eb42d18bd5cf621', '2d83b900225697e6477c799f']
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual(self.source_ids(events[0]), set(ids))
        measured = 'The museum tested this cluster with matrix multiplication and achieved 2 teraflops.'
        articles = [article_for(self.m, title, measured) for title in [
            'Museum builds a Nova-7 replica with 20 Mac mini computers',
            'Museum builds a Nova-7 replica with 22 Mac mini computers',
            'Museum builds a Nova-8 replica with 20 Mac mini computers',
            'Madrid museum builds a Nova-7 replica with 20 Mac mini computers',
            'London museum builds a Nova-7 replica with 20 Mac mini computers',
        ]]
        events = self.m.cluster_articles(articles)
        self.assertEqual(len(events), 5)
        self.assertTrue(all(event.relevance_tier == 'strong' for event in events))

    def test_compatibility_does_not_own_trademark(self):
        events = self.m.cluster_articles([article_for(self.m,
            'Samsung files an Apple-compatible “Vision” trademark',
            'Samsung filed the Vision trademark for accessories compatible with Apple devices.')])
        self.assertEqual(events[0].relevance_tier, 'weak')
        for actor in ('Apple rival Samsung', 'Apple supplier LG'):
            events = self.m.cluster_articles([article_for(self.m, actor + ' files “Vision” trademark',
                actor + ' filed the Vision trademark for its own headset.')])
            self.assertEqual(events[0].relevance_tier, 'weak')

    def test_home_pairing_requires_affirmative_owned_code(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        from apple_news_core.event_identity import bind_home_software_claims
        first = 'Researchers discovered HomeKit Dynamic Island controls in iOS 27.2 code.'
        for extra in [
            'Separately, Samsung SmartThings accessories allow NFC pairing while unpowered.',
            'The accessories do not support pairing while unpowered.',
            'A new laptop supports setup without power through a diagnostic service.',
            'Samsung firmware enables NFC pairing while unpowered, a feature unavailable in HomeKit.',
        ]:
            with self.subTest(extra=extra):
                evidence = ArticleEvidence('home', '9to5Mac', 'https://example.com/home',
                    'New HomeKit controls found in iOS code', first, 'news',
                    tuple(EvidenceUnit(str(i), 'p', value, 'html', i) for i, value in enumerate([first, extra])), confidence='detail')
                self.assertEqual({c.subject for c in bind_home_software_claims(evidence)}, {'homekit:proximity-controls'})

    def test_event_format_question_is_reporting_not_a_reader_poll(self):
        events, _ = self.cluster_sources('d3c9ccc49e98472f0652a8fc')
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'hardware_products')
        for title, lead in [
            ('Will you watch the Apple event?', 'Vote in our reader poll about the upcoming Apple launch.'),
            ('Will Apple livestream its next event?', 'We hope Apple will offer an online video presentation, but there is no report yet.'),
        ]:
            self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'weak')



if __name__ == '__main__':
    unittest.main()
