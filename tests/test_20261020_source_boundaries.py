"""Current source actions, functional categories and same-report boundaries."""
from datetime import datetime, timezone
from dataclasses import replace
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261020_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 20, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def ids(self, *prefixes):
        return [next(k for k in self.rows if k.startswith(p)) for p in prefixes]

    def test_recalled_order_case_cannot_create_a_current_named_order(self):
        from apple_news_core.event_identity import bind_resale_report
        evidence = self.source_articles(self.ids('eed022')[0])[0].evidence
        recalled = next(u for u in evidence.units if '此前有媒体报道称' in u.text)
        for text in (recalled.text, recalled.text.replace('经销商提前', '经销商许山提前'),
                     recalled.text.replace('此前有媒体报道称，', ''),
                     '经销商正在订下50台首批货源。', '商家刚刚锁定50台首批货源。'):
            revised = replace(evidence, units=tuple(
                replace(u, text=text) if u.unit_id == recalled.unit_id else u for u in evidence.units))
            claims = bind_resale_report(revised) or ()
            with self.subTest(text=text):
                self.assertFalse(any(c.action == 'resale-order-report' for c in claims))
        current = replace(evidence, units=(replace(recalled,
            text=recalled.text.replace('此前有媒体报道称，', '').replace('经销商提前', '经销商许山提前')),))
        claims = bind_resale_report(current) or ()
        self.assertTrue(any(c.action == 'resale-order-report' for c in claims))
        updated = replace(evidence, units=(
            replace(recalled, text=recalled.text.replace('经销商提前', '经销商许山提前')),
            replace(recalled, unit_id='current-order-update', ordinal=recalled.ordinal + 1,
                    text='这批订单今天已经全部交付，商家确认收到剩余货款。')))
        claims = bind_resale_report(updated) or ()
        order = next(c for c in claims if c.action == 'resale-order-report')
        self.assertIn('current-order-update', order.unit_ids)
        self.assertIn(recalled.unit_id, order.unit_ids)
        historical = replace(recalled, text='手机经销商许山已于去年锁定50台首批货源。')
        other = replace(recalled, unit_id='other-buyer', ordinal=recalled.ordinal + 1,
                        text='另一名消费者李明今天收到新机。')
        pronoun = replace(recalled, unit_id='other-buyer-update', ordinal=recalled.ordinal + 2,
                          text='他今天已经全部转卖。')
        for units in ((historical,), (updated.units[0], other, pronoun)):
            claims = bind_resale_report(replace(evidence, units=units)) or ()
            self.assertFalse(any(c.action == 'resale-order-report' for c in claims))
        projections, remaining, _ = self.m.project_article_evidence(evidence)
        self.assertFalse(any(p.claim.action == 'resale-order-report' for p in projections))
        self.assertTrue(any(span[0] == recalled.unit_id for span in remaining))

    def test_current_operation_owns_category_and_tier(self):
        for prefix, tier, category in (
                ('5681', 'strong', 'hardware_products'),
                ('04ce', 'strong', 'software_systems'),
                ('f7f13', 'strong', 'hardware_products'),
                ('1cc6', 'ecosystem', 'software_systems'),
                ('c08a', 'strong', 'hardware_products'),
                ('d500', 'strong', 'software_systems'),
                ('70f5', 'strong', 'hardware_products')):
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [(tier, category)])

    def test_independent_ports_and_existing_personal_health_case_stay_weak(self):
        for prefix in ('97ed', 'c256', '8a367', '303225', 'fc4bc', '2075', '23897'):
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_named_home_features_split_and_share_only_their_own_sources(self):
        ids = self.ids('b340', '1eb26', 'a564', 'b57e', 'c9d0')
        events, data = self.cluster_sources(*ids)
        self.assertTrue(all(e.category == 'software_systems' and e.relevance_tier == 'strong' for e in events))
        claims = {a.bound_claim.subject for e in events for a in e.articles if a.bound_claim}
        self.assertIn('homepod:lock-controls', claims)
        self.assertIn('homepod:sound-glow', claims)
        glow = next(e for e in events if any(a.bound_claim and a.bound_claim.subject == 'homepod:sound-glow' for a in e.articles))
        lock = next(e for e in events if any(a.bound_claim and a.bound_claim.subject == 'homepod:lock-controls' for a in e.articles))
        self.assertIsNot(glow, lock)
        self.assertNotIn(ids[0], self.source_ids(glow))
        self.assertIn(ids[2], self.source_ids(glow))
        # Source-specific support limits must survive projection, not spread
        # from one feature to every capability on the same host device.
        facts = ' '.join([*glow.key_facts, *(f.text for f in glow.fact_plan.required)])
        self.assertIn('not available on the original', facts)
        facts = ' '.join([*lock.key_facts, *(f.text for f in lock.fact_plan.required)])
        self.assertIn('All HomePod models', facts)
        self.assertIn('FaceTime', facts)
        surround = next(e for e in events if any(a.bound_claim and a.bound_claim.subject == 'homepod:surround-system' for a in e.articles))
        self.assertEqual(self.source_ids(surround), set(ids[2:]))

    def test_release_candidate_sources_share_wave_and_keep_older_versions_separate(self):
        ids = self.ids('023b', '732c', '7b90', 'c788', '1421', '8ae8', '93d0')
        for sequence in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*sequence, *self.ids('4589'))
            self.assertEqual(len(events), 2)
            current = next(e for e in events if ids[0] in self.source_ids(e))
            self.assertEqual(self.source_ids(current), set(ids))
            self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'software_systems' for e in events))

    def test_same_transactions_documents_and_hardware_readiness_merge(self):
        for prefixes in (('e1d05', 'b591', '29f9', '9756'), ('ecb3', '6eb94'),
                         ('1fda', 'cb39'), ('d7fd', '95f4'), ('a145', '70f5'),
                         ('a156', 'c82a')):
            with self.subTest(sources=prefixes):
                ids = self.ids(*prefixes)
                events, _ = self.cluster_sources(*ids)
                self.assertEqual(len(events), 1)
                self.assertEqual(self.source_ids(events[0]), set(ids))
                self.assertEqual(events[0].relevance_tier, 'strong')

    def test_local_apple_market_results_do_not_require_apple_headline(self):
        for prefixes in (('3d496', 'ce3d'), ('3b74', '722c')):
            with self.subTest(sources=prefixes):
                events, _ = self.cluster_sources(*self.ids(*prefixes))
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].relevance_tier, 'strong')
        events, _ = self.cluster_sources(*self.ids('6e601'))
        self.assertEqual(events[0].relevance_tier, 'strong')
        events, _ = self.cluster_sources(*self.ids('8fe6'))
        self.assertEqual(events[0].relevance_tier, 'weak')

    def test_event_announcement_does_not_inherit_inventory_forecasts(self):
        current = self.ids('22f82', '80a560', '062fe5', 'e4c892', '49b0a8', '34ef99')
        forecast = self.ids('cf7d40')[0]
        for sequence in (current, list(reversed(current))):
            events, _ = self.cluster_sources(*sequence, forecast)
            self.assertEqual(len(events), 2)
            announcement = next(e for e in events if current[0] in self.source_ids(e))
            self.assertEqual(self.source_ids(announcement), set(current))
            self.assertNotIn(forecast, self.source_ids(announcement))

    def test_service_policy_qualifies_without_inventing_interview_identity(self):
        events, _ = self.cluster_sources(*self.ids('f863', 'd500'))
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'software_systems' for e in events))
        self.assertTrue(all(a.bound_claim.review_reason for e in events for a in e.articles))

    def test_hardware_response_and_camera_scope_require_own_actions(self):
        from apple_news_core.event_identity import source_device_operation_frame, source_hardware_action_frame
        title = 'iPhone 17 camera-control coating: Apple support responds'
        response = 'Apple support says a warranty repair requires inspection of the device.'
        self.assertEqual(source_device_operation_frame(title, response).category, 'hardware_products')
        self.assertIsNone(source_device_operation_frame(title.replace('Apple support', 'A retailer'), response.replace('Apple support', 'A retailer')))
        for title, lead in (
            ('Apple is developing an indoor camera', 'Apple is developing an indoor camera with an infrared sensor.'),
            ('苹果正在研发家用摄像头', '苹果正在研发配备红外传感器的家用摄像头。')):
            self.assertEqual(source_hardware_action_frame(title, lead, (), ()).category, 'hardware_products')
        self.assertIsNone(source_hardware_action_frame('Apple is developing a camera app', 'Apple is developing a camera app for iPhone.', (), ()))

    def test_named_feature_support_does_not_create_an_absent_release(self):
        from apple_news_core.event_identity import bind_home_feature_release
        evidence = self.source_articles(self.ids('b340')[0])[0].evidence
        unit = replace(evidence.units[0], text='HomePod Software 27.2 RC does not add Lock Controls. The setting is not available on any HomePod.')
        self.assertEqual(bind_home_feature_release(replace(evidence, units=(unit,))), ())

        for text in (
            'HomePod Software 27.2 RC does not add Sound Glow. Existing HomePod models support music playback.',
            'HomePod Software 27.2 RC does not add Sound Glow. Sound Glow supports animated lights on HomePod mini.',
            'Sound Glow supports animated lights on HomePod mini. HomePod Software 27.2 RC has not been released.',
            'HomePod Software 27.2 RC is available. Sound Glow could be added next year. All HomePod models support music playback.'):
            with self.subTest(text=text):
                self.assertEqual(bind_home_feature_release(replace(evidence, units=(replace(unit, text=text),))), ())

    def test_rc_numbers_and_incident_dates_remain_distinct(self):
        for articles in (
            [article_for(self.m, f'{n} release candidate for macOS 27.2 now available',
                         f'Apple released the {n.lower()} RC for macOS 27.2 today.') for n in ('First', 'Second')],
            [article_for(self.m, f'Apple store looted on October {day}',
                         f'The Apple Sainte-Catherine was looted on October {day}, 2026 during protests.') for day in (17, 19)]):
            with self.subTest(titles=[a.title for a in articles]):
                self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_interview_identity_does_not_supply_company_decision(self):
        from apple_news_core.event_identity import bind_service_leadership_report
        evidence = self.source_articles(self.ids('d500')[0])[0].evidence
        unit = replace(evidence.units[0], text="Apple’s new head of App Store, Carson Oliver, gave an interview with Polygon. He discussed his childhood and favorite games, without announcing any Apple decision.")
        self.assertIsNone(bind_service_leadership_report(replace(evidence,
            title='App Store chief discusses his favorite childhood games', units=(unit,))))
        intro = replace(unit, text="Apple’s new head of App Store, Carson Oliver, gave an interview with Polygon.")
        for speaker, keep in (('The interviewer', False), ('Carson Oliver', True)):
            statement = replace(evidence.units[1], text=speaker + ' said: We continue investing in App Store game discovery.')
            claim = bind_service_leadership_report(replace(evidence, units=(intro, statement)))
            self.assertEqual(claim is not None, keep)
            if claim:
                self.assertIn(statement.unit_id, claim.unit_ids)
            same_paragraph = replace(intro, text=intro.text + ' ' + statement.text)
            claim = bind_service_leadership_report(replace(evidence, units=(same_paragraph,)))
            self.assertEqual(claim is not None, keep)

    def test_acquisition_description_does_not_replace_target_or_stage(self):
        from apple_news_core.event_identity import source_acquisition_frame
        direct = source_acquisition_frame('Apple buys Samplab', 'Apple acquired Samplab today.')
        descriptive = source_acquisition_frame('Apple Buys Music Startup Samplab', 'Apple acquired Samplab today.')
        self.assertEqual(direct, descriptive)
        self.assertIsNone(source_acquisition_frame('Apple acquisition of Samplab: a look back',
            'Apple acquired Samplab in 2020. The company has not announced a new deal.'))
        uncertain = source_acquisition_frame('Apple acquisition of Samplab still unconfirmed',
            'Reports claimed Apple acquired Samplab. Apple has not confirmed any acquisition.')
        self.assertEqual(uncertain.action, 'acquisition-unconfirmed')
        for purpose in ("app 'Logic Pro'", 'a tool called Logic Pro'):
            articles = [article_for(self.m,
                f"Apple acquires audio app {name} to improve {purpose}",
                f"Apple acquired {name} today to improve {purpose}.")
                for name in ('Samplab', 'Acme')]
            with self.subTest(purpose=purpose):
                self.assertEqual(len(self.m.cluster_articles(articles)), 2)
                for article, name in zip(articles, ('samplab', 'acme')):
                    self.assertEqual(source_acquisition_frame(article.title, article.summary).subject,
                                     'apple-acquisition:' + name)

    def test_incidental_event_does_not_replace_another_action(self):
        from apple_news_core.event_identity import source_dated_launch_frame
        a = article_for(self.m, 'Apple reveals OLED MacBook Pro price increase',
            'Apple today announced an event on October 28. The OLED MacBook Pro will cost $200 more, according to a new supplier report.')
        profile = self.m.article_reconciliation_profile(a)
        self.assertFalse(any('launch-date-confirmation' in key for key in profile.event_keys))
        frame = source_dated_launch_frame('Apple plans Mac launch on November 6',
            'Apple announced an event on October 28, according to an unconfirmed rumor.', ())
        self.assertTrue(frame is None or frame.action != 'launch-date-confirmation')
        self.assertIsNone(source_dated_launch_frame('苹果新发布会官宣：Mac 与 iPad 新品',
            '北京时间 10 月 29 日凌晨 1 点，苹果不会举行新品发布活动。', ()))

    def test_comparison_and_cast_wishes_cannot_borrow_background_actions(self):
        for prefix in ('ee001', '24e383', 'beb3', '2b029'):
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        events, _ = self.cluster_sources(*self.ids('6d1146'))
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'hardware_products')

    def test_editorial_aside_does_not_replace_a_reported_fix(self):
        article = article_for(self.m,
            "Apple fixes bug where Siri doesn't understand requests",
            "Apple released iOS 27.2 to fix a bug where Siri fails to understand requests. "
            "It's hard to believe this bug lasted so long.")
        events = self.m.cluster_articles([article])
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('strong', 'software_systems')])

    def test_product_event_frame_keeps_category_after_legacy_context(self):
        events, _ = self.cluster_sources(*self.ids('15e306', '7158', '647ae'))
        self.assertTrue(all(e.category == 'hardware_products' for e in events))


if __name__ == '__main__':
    unittest.main()
