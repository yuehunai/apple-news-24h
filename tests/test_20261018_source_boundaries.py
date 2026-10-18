"""Source-owned retail actions, fees and measured scopes across translations."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261018_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 18, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def ids(self, *prefixes):
        return [next(k for k in self.rows if k.startswith(p)) for p in prefixes]

    def test_stock_forecast_and_internal_store_guidance_merge_only_with_same_action(self):
        forecast = self.ids('a370', 'a304')
        guidance = self.ids('cb715', 'c70f', '1829', '2837')
        demand = self.ids('2396')
        local_store = self.ids('06e4')
        groups = [set(g) for g in (forecast, guidance, demand, local_store)]
        for ids in (forecast + guidance + demand + local_store,
                    local_store + demand + guidance[::-1] + forecast[::-1]):
            events, _ = self.cluster_sources(*ids)
            self.assertCountEqual([self.source_ids(e) for e in events], groups)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_translated_weekly_activation_measurement_is_one_event(self):
        ids = self.ids('5146', 'd10b', '2b0b')
        for ordered in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*ordered)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual(events[0].relevance_tier, 'strong')

    def test_first_party_case_construction_is_strong_hardware(self):
        ids = self.ids('008b', '4f19')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'hardware_products')

    def test_carrier_fee_uses_current_provider_not_background_dollar_price(self):
        article = self.source_articles(self.ids('edfc')[0])[0]
        p = self.m.article_reconciliation_profile(article)
        self.assertEqual(p.relevance_tier, 'ecosystem')
        self.assertEqual(p.category_hint, 'software_systems')
        from apple_news_core.event_identity import source_service_fee_frame
        e = article.evidence
        f = source_service_fee_frame(e.title, e.raw_lead, tuple(u.text for u in e.units))
        self.assertIsNotNone(f)
        self.assertIn('ee', f.subject)
        self.assertIn('gbp', f.period)
        self.assertNotIn('usd', f.period)

    def test_third_party_app_adaptations_and_device_tool_do_not_borrow_phone_specs(self):
        for sid in self.ids('cdad', 'c177', '6cb8', '6a7d'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_personal_deployment_tutorial_does_not_become_os_release(self):
        events, _ = self.cluster_sources(*self.ids('56ce'))
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_translated_legal_appointment_shares_actor_person_and_action(self):
        ids = self.ids('5dbc', '29a1')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'hardware_products')
        self.assertEqual(events[0].relevance_tier, 'strong')

    def test_retail_guidance_is_not_forecast_or_other_product_guidance(self):
        from apple_news_core.event_identity import source_retail_operation_frame
        samples = [
            ('Apple tells employees to discourage iPhone 20 walk-in purchases',
             'Apple retail employees were told to warn customers not to visit stores to buy iPhone 20 without a preorder.'),
            ('Reporter expects no iPhone 20 walk-in stock',
             'Reporter Jane Smith predicts that iPhone 20 will have little stock in stores on launch day.'),
            ('Apple tells employees to discourage iPhone 21 walk-in purchases',
             'Apple retail employees were told to warn customers not to visit stores to buy iPhone 21 without a preorder.'),
        ]
        frames = [source_retail_operation_frame(t, l, (l,)) for t, l in samples]
        self.assertTrue(all(frames))
        self.assertNotEqual(frames[0].action, frames[1].action)
        self.assertNotEqual(frames[0].subject, frames[2].subject)

    def test_operating_conditions_inside_commentary_keep_local_evidence(self):
        articles = self.source_articles(self.ids('34e9')[0])
        self.assertEqual(len(articles), 1)
        self.assertIsNotNone(articles[0].bound_claim)
        text = ' '.join(articles[0].key_facts)
        self.assertIn('first open', text)
        self.assertIn('Google', text)
        self.assertNotIn('social contract', text)
        p = self.m.article_reconciliation_profile(articles[0])
        self.assertEqual(p.category_hint, 'software_systems')
        self.assertEqual(p.relevance_tier, 'strong')

    def test_prior_job_title_does_not_make_general_ai_remarks_a_new_transition(self):
        events, _ = self.cluster_sources(*self.ids('a69b'))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'hardware_products')
        p = self.m.article_reconciliation_profile(events[0].articles[0])
        self.assertFalse(any('ceo-transition' in key for key in p.event_keys))
        self.assertTrue(any('institutional-attendance' in key for key in p.event_keys))

    def test_weekly_report_keeps_stage_model_week_and_denial(self):
        from apple_news_core.event_identity import source_weekly_device_measurement as frame
        title = 'iPhone 22 Pro Max W43国内单周激活量80万台'
        lead = '本周报告：2028年第43周，iPhone22ProMax国内单周激活量80万台。'
        positive = frame(title, lead)
        self.assertIsNotNone(positive)
        self.assertEqual(positive, frame(title, lead.replace('iPhone22ProMax', 'iPhone 22 Pro Max')))
        for other_title, other_lead in [(title.replace('W43', 'W44'), lead.replace('第43', '第44')),
                                        (title.replace('国内', '美国'), lead.replace('国内', '美国')),
                                        ('预计' + title, lead),
                                        (title.replace('22', '23'), lead.replace('22', '23'))]:
            self.assertNotEqual(positive, frame(other_title, other_lead))
        self.assertIsNone(frame(title, lead.replace('激活量80', '激活量未达80')))

    def test_nonapple_case_and_other_carrier_fee_do_not_borrow_ownership(self):
        from apple_news_core.event_identity import source_official_accessory_conditions, source_service_fee_frame
        self.assertIsNone(source_official_accessory_conditions(
            'Acme iPhone 22 case uses adhesive', 'Acme sells a third-party case for the iPhone 22.'))
        self.assertIsNone(source_service_fee_frame('Acme announces iPhone Handoff pricing',
            'Acme has not announced pricing. Another carrier charges $8/month.', ()))
        a = source_service_fee_frame('Acme announces iPhone Handoff pricing',
            'Acme will charge €8/month for iPhone Handoff.', ())
        b = source_service_fee_frame('Bravo announces iPhone Handoff pricing',
            'Bravo will charge €8/month for iPhone Handoff.', ())
        self.assertEqual(a.period, 'eur-month:8')
        self.assertNotEqual(a.subject, b.subject)

    def test_tutorial_label_does_not_suppress_new_measured_results(self):
        from apple_news_core.event_identity import source_editorial_evaluation
        self.assertEqual(source_editorial_evaluation(
            "How I'm preparing my computers for an OS update", "Here is the script I use to prepare each computer."), 'tutorial')
        self.assertEqual(source_editorial_evaluation(
            'Testing Rosetta on macOS 29 finds a new failure', 'Our tests found that the new release breaks an Intel app.'), '')

    def test_reviewed_retail_actions_require_local_actor_model_and_polarity(self):
        from apple_news_core.event_identity import source_retail_operation_frame
        for title, lead in [
            ('iPhone 20 walk-in availability remains unclear', 'Apple retail employees were told to warn customers not to visit stores to buy iPhone 19 without a preorder.'),
            ('Apple denies iPhone 20 walk-in restrictions', 'Apple says employees were not told to discourage iPhone 20 purchases without a preorder.'),
            ('iPhone 20 walk-in stock remains unclear', 'Reporter Jane Smith interviewed analyst John Brown, who predicts that iPhone 20 will have little stock in stores on launch day.'),
            ('iPhone 20 walk-in stock remains unclear', 'Last year, reporter Jane Smith predicted that iPhone 19 would have little stock in stores on launch day.'),
            ('iPhone Duo首销线下库存仍不明朗', '记者马克·古尔曼（Mark Gurman）采访了分析师张明，张明预计 iPhone Duo 首销线下库存不足。')]:
            self.assertIsNone(source_retail_operation_frame(title, lead))

    def test_weekly_breakdown_requires_continuing_report_context(self):
        from apple_news_core.event_identity import source_weekly_device_measurement as frame
        title = 'iPhone 22 Pro销量统计'
        total = 'iPhone 22 Pro系列累计激活300万台。'
        detail = '按照博主公布的统计数据，W40，iPhone 22 Pro Max单周激活76万台。'
        self.assertIsNotNone(frame(title, total + detail))
        for interruption in ('另外一位博主公布了报告。', '研究人员还测试了平板电脑。',
                             '根据另一份统计数据，iPhone 23销量增长。'):
            with self.subTest(interruption=interruption):
                self.assertIsNone(frame(title, total + interruption + detail))
        self.assertIsNone(frame(title, total + detail.replace('iPhone 22', 'iPhone 23')))

    def test_reviewed_fee_and_measurement_qualifiers_stay_with_their_subject(self):
        from apple_news_core.event_identity import source_service_fee_frame, source_weekly_device_measurement
        self.assertIsNone(source_service_fee_frame('EE announces iPhone Handoff pricing',
            'EE says Vodafone charges £7/month for iPhone Handoff.', ()))
        self.assertIsNone(source_service_fee_frame('EE announces iPhone Handoff pricing',
            'EE says Vodafone is charging £7/month for iPhone Handoff.', ()))
        self.assertIsNone(source_service_fee_frame('EE announces iPhone Handoff pricing',
            'EE announces that iPhone Handoff is free, while Vodafone charges £7/month.', ()))
        self.assertIsNone(source_weekly_device_measurement('iPhone 22国内单周销量80万台',
            'iPhone 22国内单周销量80万台，高于iPhone 21在第43周的销量60万台。'))
        articles = [article_for(self.m, 'iPhone 22 weekly sales report',
            'In week 43, iPhone 22 sales reached 800000 units in ' + region + '.') for region in ('China', 'the US')]
        self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_reviewed_operating_conditions_do_not_project_opinions_or_other_devices(self):
        from dataclasses import replace
        from apple_news_core.models import EvidenceUnit
        from apple_news_core.event_identity import bind_device_capability_inventory
        evidence = self.source_articles(self.ids('34e9')[0])[0].evidence
        for title, lead in [
            ('HomePod Siri needs a better setup', 'I think that on HomePod you must first fix Siri before adding more features.'),
            ('HomePod Siri is disappointing', "Apple's approach, which it says will work with Siri on iPhone, requires an unlocked screen."),
            ('HomePod Siri is disappointing', "Separately, Apple described a new Siri feature for iPhone. Apple's approach, which it says will work with any calendar, requires an unlocked screen.")]:
            e = replace(evidence, title=title, raw_lead=lead, units=(EvidenceUnit('p1', 'p', lead, 'body', 0),))
            self.assertIsNone(bind_device_capability_inventory(e))
            self.assertFalse(self.m.project_article_evidence(e)[0])
        texts = ['To use Siri on HomePod, you must first enable Siri in Settings.',
                 'Separately, iPhone now supports a new calendar feature.',
                 "Apple's approach, which it says will work with any calendar, requires an unlocked screen."]
        e = replace(evidence, title='HomePod Siri requires setup', raw_lead=texts[0],
                    units=tuple(EvidenceUnit(str(i), 'p', text, 'body', i) for i, text in enumerate(texts)))
        claim = bind_device_capability_inventory(e)
        self.assertIsNotNone(claim)
        self.assertEqual(claim.unit_ids, ('0',))


if __name__ == '__main__':
    unittest.main()
