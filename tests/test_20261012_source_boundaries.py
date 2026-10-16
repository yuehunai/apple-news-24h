"""October 12 source-owned hardware actions and compatibility boundaries."""
from datetime import datetime, timezone
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

class SourceBoundariesTests(unittest.TestCase):
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261012_source_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,10,12,tzinfo=timezone.utc))}

    def test_external_storage_compatibility_is_not_platform_support_change(self):
        events, _ = self.cluster_sources('27a55fbfe26b0e55c2b73779')
        self.assertEqual(len(events), 1)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        for title, body in (
            ('Atlas portable SSD goes on sale', 'The SSD is compatible with macOS and supports iPhone external video recording.'),
            ('星海移动固态硬盘今日开售', '兼容性覆盖macOS和Windows系统，可为iPhone进行视频外录。')):
            self.assertEqual(self.profile(title, body).relevance_tier, 'weak')
        for title, body in (
            ('Apple announces iOS 27 compatible iPhones', 'iOS 27 is compatible with iPhone 17 and newer models.'),
            ('苹果公布iOS 27兼容列表', 'iOS 27兼容列表包括iPhone 17和更新机型。'),
            ('Apple ends support for older Macs', 'macOS 27 drops software support for older Intel Macs.')):
            self.assertNotEqual(self.profile(title, body).relevance_tier, 'weak')

    def test_os_compatibility_list_belongs_to_platform_not_peripheral(self):
        for title, body in (
            ('星海移动固态硬盘今日开售', '这款硬盘的兼容列表包含iPhone与macOS设备。'),
            ('星海移动固态硬盘今日开售', 'macOS支持这款硬盘，iPhone也可外录。'),
            ('Atlas drive goes on sale', 'macOS supports this drive, while iPhone can record video externally.'),
            ('Atlas drive goes on sale', 'The drive compatibility list includes iPhone and macOS devices.')):
            a = article_for(self.m, title, body)
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier, 'weak')
            e = self.m.event_to_dict(self.m.cluster_articles([a])[0], timezone.utc)
            self.assertEqual(e['relevance_tier'], 'weak')
        for title, body in (
            ('新版支持列表公布', '苹果更新iOS 27兼容列表，新增支持iPhone 17。'),
            ('A new support list is available', 'Apple updates the macOS compatibility list to include newer Macs.')):
            self.assertNotEqual(self.profile(title, body).relevance_tier, 'weak')

    def test_roundup_current_attributed_device_plan_survives_old_product_label(self):
        sid = '3808f494f497c08b968022b7'
        articles = self.source_articles(sid)
        children = [a for a in articles if 'macbook' in a.title.lower()]
        self.assertEqual(len(children), 1)
        child = children[0]
        unit = self.rows[sid]['evidence']['units'][1]
        begin = unit['text'].index('touchscreen MacBook')
        exact = unit['text'][begin:]
        self.assertIn(exact, child.key_facts)
        self.assertNotIn(unit['text'], child.key_facts)
        profile = self.m.article_reconciliation_profile(child)
        self.assertEqual(profile.relevance_tier, 'strong')
        self.assertEqual(profile.category_hint, 'hardware_products')
        public = self.m.event_to_dict(self.m.cluster_articles(articles)[0], timezone.utc)
        self.assertEqual(public['relevance_tier'], 'strong')
        self.assertEqual(public['category'], 'hardware_products')
        self.assertIn(exact, public['key_facts'])
        self.assertIn(exact, public['must_include_facts'])
        self.assertFalse(any('What we probably' in fact for fact in public['must_include_facts']))
        projections, remainder, excluded = self.m.project_article_evidence(child.evidence)
        self.assertIn((unit['unit_id'], begin, len(unit['text'])), projections[0].claim.evidence_spans)
        self.assertFalse(any(key == unit['unit_id'] and start < begin for key, start, end in remainder))
        self.assertTrue(any(key == unit['unit_id'] and start == 0 and end == begin and 'editorial inference' in reason.lower() for key, start, end, reason in excluded))
        self.assertTrue(all(any(span[0] == unit['unit_id'] for span in remainder)
            for unit in self.rows[sid]['evidence']['units'] if unit['ordinal'] in (4, 11, 12, 16)))
        evidence = child.evidence
        for text, count in (
            ('The long-rumored OLED iPad, which reporter Alex Smith says will launch next month.', 1),
            ('The long-rumored OLED iPad, which reporter Alex Smith previously said will launch next month.', 0),
            ('The long-rumored OLED iPad, which we expect will launch next month.', 0),
            ('The long-rumored OLED iPad, which reporter Alex Smith says will not launch next month.', 0)):
            e = replace(evidence, units=(replace(evidence.units[1],text=text),))
            variants, _, _ = self.m.project_article_evidence(e)
            self.assertEqual(len(variants), count, text)

    def test_only_adjacent_author_prediction_is_excluded(self):
        from apple_news_core.article_projector import source_evidence_remainder
        evidence = self.source_articles('3808f494f497c08b968022b7')[0].evidence
        claim = 'OLED iPad, which reporter Alex Smith says will launch next month.'
        for prefix, excluded_prediction in (
            ('We expect to see the ', True),
            ('What I probably will not see is the ', True),
            ('“We expect to launch this product,” Apple says. ', False),
            ('We will release the developer tools. ', False),
            ('The report says the plan may change. ', False)):
            unit = replace(evidence.units[1], text=prefix + claim)
            e = replace(evidence, units=(unit,))
            remaining, excluded = source_evidence_remainder(e, [(unit.unit_id, len(prefix), len(unit.text))])
            predictions = [span for span in excluded if 'editorial inference' in span[3].lower()]
            self.assertEqual(bool(predictions), excluded_prediction, prefix)
            if excluded_prediction:
                self.assertEqual(predictions[0][:3], (unit.unit_id, 0, len(prefix)))
            else:
                self.assertTrue(remaining, prefix)

    def test_adjacent_attributed_first_person_commitment_stays_in_review(self):
        evidence = self.source_articles('3808f494f497c08b968022b7')[0].evidence
        text = ('We expect to release the developer tools this fall, Apple said in its statement, alongside the '
            'OLED iPad, which reporter Alex Smith says will launch next month.')
        unit = replace(evidence.units[1], text=text)
        e = replace(evidence, units=(unit,))
        projections, remaining, excluded = self.m.project_article_evidence(e)
        self.assertEqual(len(projections), 1)
        begin = text.index('OLED iPad')
        self.assertEqual(projections[0].claim.evidence_spans, ((unit.unit_id, begin, len(text)),))
        self.assertTrue(any(text[start:end] == text[:begin].rstrip() for key, start, end in remaining if key == unit.unit_id))
        self.assertFalse(any('editorial inference' in reason.lower() for _, _, _, reason in excluded))
        self.m.validate_evidence_dispositions(e, projections, remaining, excluded)

    def test_attributed_launch_does_not_absorb_shipping_stage(self):
        base = self.source_articles('3808f494f497c08b968022b7')[0]
        articles = []
        for verb in ('launch', 'ship'):
            text = 'The OLED iPad, which reporter Alex Smith says will ' + verb + ' next month.'
            e = replace(base.evidence, article_id=verb, url='https://example.com/' + verb,
                units=(replace(base.evidence.units[1], text=text),))
            projections, _, _ = self.m.project_article_evidence(e)
            if projections:
                p = projections[0]
                a = replace(base, title=p.title, summary=p.summary, key_facts=list(p.key_facts),
                    url=e.url, evidence=e, bound_claim=p.claim)
            else:
                a = replace(base, title='OLED iPad ' + verb + ' report', summary=text,
                    key_facts=[text], url=e.url, evidence=e, bound_claim=None)
            articles.append(a)
        for order in (articles, articles[::-1]):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 2)
            self.assertEqual(sum(len(self.m.event_to_dict(e, timezone.utc)['sources']) for e in events), 2)

    def test_captured_hardware_categories(self):
        for sid in ('2026c53522ad68308c77c076', '72527b59f290315caef14f7e'):
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual({e.category for e in events}, {'hardware_products'})

    def test_captured_shared_actions_in_both_orders(self):
        for ids in (
            ('418be765853078ed13cd97c6','95cceddbc01fe81dfcd40a08','4445c8c0a43dd7d7b08ac7ef','39272e340b14e2a41b10ec61'),
            ('9439d7e3bf3835ffb1114d37','4b8a0c4098372825f9b8120a','588db6ce47d8e597ba26b8f4'),
            ('0dbbd4b39da91bf95cf9aebf','9617cf5610aad7e9475a0134','551566ab566bf5a43adda482')):
            for order in (ids, ids[::-1]):
                with self.subTest(ids=order):
                    events, _ = self.cluster_sources(*order)
                    self.assertEqual(len(events), 1)
                    self.assertEqual(self.source_ids(events[0]), set(ids))
                    self.assertEqual(events[0].category, 'hardware_products')

    def test_captured_os_virtual_hardware_adaptation(self):
        ids = ('35e103e77589249df87b60b2','71ff4e0f1782f9c3f2cbe856')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')
        for a in events[0].articles:
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier, 'ecosystem')

    def test_captured_mini_price_forecast_keeps_launch_separate(self):
        ids = ('756cef0a3349f8a02a9dba7b','53e24fd7da1443462201e95a','b2981b49bdfa942fa1f23c0e')
        launch = '1dbe2299d7710a5589023c86'
        for order in (ids + (launch,), (launch,) + ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            price = next(e for e in events if ids[0] in self.source_ids(e))
            self.assertEqual(self.source_ids(price), set(ids))
            self.assertEqual(price.category, 'hardware_products')
            self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier == 'strong' for a in price.articles))

    def test_captured_executive_actions_keep_fact_ownership(self):
        ids = ('39d31a16b9c29c1273dfa041','1f7dab402563933c375df601',
               '0b1aa47937f0baeab22d3fa8','a2bd6a7145f1c29940e97223',
               'eedefe66ca83d1d9484ba8dc','98e27fc936fab13088e029f7')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            meeting = next(e for e in events if ids[1] in self.source_ids(e))
            visit = next(e for e in events if ids[-1] in self.source_ids(e))
            self.assertIsNot(meeting, visit)
            self.assertEqual(self.source_ids(meeting), set(ids[:5]))
            self.assertEqual(self.source_ids(visit), {ids[0],ids[1],ids[3],ids[5]})
            expected = Counter(self.rows[i]['evidence']['url'] for i in ids)
            expected.update(self.rows[i]['evidence']['url'] for i in (ids[0],ids[1],ids[3]))
            self.assertEqual(Counter(a.url for e in events for a in e.articles), expected)
            self.assertIn(ids[0], self.source_ids(meeting))
            self.assertIn(ids[0], self.source_ids(visit))
            self.assertTrue(set(ids[1:5]) <= self.source_ids(meeting))
            self.assertIn(ids[1], self.source_ids(visit))
            self.assertNotIn(ids[4], self.source_ids(visit))
            self.assertEqual({e.category for e in events}, {'hardware_products'})
            self.assertFalse(any(x in ' '.join(meeting.key_facts) for x in ('早茶','Xmind','咏春')))
            self.assertFalse(any(x in ' '.join(visit.key_facts) for x in ('省长','扩大在粤','扩大在广东')))
            self.assertTrue(all('ceo-transition' not in ' '.join(self.m.article_reconciliation_profile(a).event_keys) for e in events for a in e.articles))

    def test_captured_home_device_disclosures(self):
        for ids in (
            ('d71ffdb28ebe7121a30fdbb4','0e0f76ac974c1ba9258945e5','5db57c5d89d4a7e148d7574a','51529299b8a8b7960c1a4853','2e9d180bb7e336f686ef06bc','89dc6c321a3577aafbf7ad16'),
            ('22343ed7729b0c9cbf98bee8','c1e8b0f3ec3c19c13f55acdc','9cb6cb7e6184ea7baa51b76e','4021fb64d7ea440731d859ac')):
            for order in (ids, ids[::-1]):
                with self.subTest(ids=order):
                    events, _ = self.cluster_sources(*order)
                    self.assertEqual(len(events), 1)
                    self.assertEqual(self.source_ids(events[0]), set(ids))
                    self.assertEqual(events[0].category, 'hardware_products')
                    self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier == 'strong' for a in events[0].articles))

    def test_captured_catalog_projects_devices_and_partnership(self):
        articles = self.source_articles('ad36090e826cb98e42617cda')
        self.assertEqual(len(articles), 5)
        events, _ = self.cluster_sources('ad36090e826cb98e42617cda')
        self.assertEqual({e.category for e in events}, {'hardware_products'})
        self.assertEqual(len(events), 5)
        for fragment in ('A18', 'S10', 'A19', 'Schneider'):
            self.assertTrue(any(fragment in ' '.join(a.key_facts) for a in articles), fragment)
        self.assertFalse(any('A18' in ' '.join(a.key_facts) and 'A19' in ' '.join(a.key_facts) for a in articles))
        self.assertFalse(any('Schneider' in ' '.join(a.key_facts) and 'A19' in ' '.join(a.key_facts) for a in articles))

    def test_captured_third_party_action_is_not_apple_hardware_result(self):
        for sid in ('ce7d0120e8a6afeefdd6e4b5','8662bf6be59ce394e57465de'):
            with self.subTest(sid=sid):
                self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier == 'weak' for a in self.source_articles(sid)))

    def profile(self, title, lead):
        return self.m.article_reconciliation_profile(article_for(self.m, title, lead))

    def assert_separate(self, left, right):
        events = self.m.cluster_articles([article_for(self.m, *left), article_for(self.m, *right)])
        self.assertEqual(len(events), 2)

    def test_natural_partnership_actor_object_stage_and_date_boundaries(self):
        base = ('Apple plans partnership with Atlas for smart home installations', 'Apple may partner with security company Atlas to install home devices.')
        other = ('Apple plans partnership with Beacon for smart home installations', 'Apple may partner with security company Beacon to install home devices.')
        for right in (other,
            ('Apple plans partnership with Atlas for smart door lock installations','Apple may partner with Atlas to install smart home door locks.'),
            ('Apple announces partnership with Atlas for smart home installations','Apple announced a partnership with Atlas to install home devices.'),
            ('Atlas hires installation technicians','Atlas is hiring installers. Apple smart home devices are a possible customer use case.'),
            ('Apple developing a security camera','Apple is developing a new home camera with on-device processing.')):
            with self.subTest(right=right): self.assert_separate(base, right)
        self.assert_separate((base[0] + ' on 2027-03-01', base[1]), (base[0] + ' on 2027-04-01', base[1]))
        denied = self.profile('Apple denies partnership with Atlas for smart home installations','Apple denies the partnership and is not partnering with Atlas.')
        self.assertNotIn('installation-partnership-report', ' '.join(denied.event_keys))

    def test_natural_hardware_camera_is_not_camera_software_or_compatibility(self):
        owned = self.profile('Apple developing a security camera','Apple is developing a new home camera with on-device processing.')
        self.assertEqual(owned.category_hint, 'hardware_products')
        for title, lead in (
            ('Apple adds a camera feature to iOS','Apple adds a camera app feature to iOS.'),
            ('HomeKit adds camera support','Apple adds HomeKit support for a third-party home camera.'),
            ('Atlas developing a HomeKit camera','Atlas is developing a security camera compatible with Apple HomeKit.'),
            ('Apple denies developing a security camera','Apple is not developing a home camera.')):
            p = self.profile(title, lead)
            self.assertNotIn('hardware-development-report', ' '.join(p.event_keys))

    def test_natural_retail_and_roadmap_keep_independent_stages(self):
        base = ('Apple plans iPhone Duo retail showcase','Apple plans retail demo displays for iPhone Duo.')
        for other in (
            ('Apple opens iPhone Duo preorders','Apple opens preorders for iPhone Duo.'),
            ('Apple releases iPhone Duo firmware update','Apple releases a firmware update for iPhone Duo.'),
            ('Apple introduces iPhone Duo name setup','Apple introduces an on-device name setup screen for iPhone Duo.'),
            ('Apple plans iPhone 19 retail showcase','Apple plans retail demo displays for iPhone 19.')):
            self.assert_separate(base, other)
        self.assert_separate(('Entry-level iPad not expected until early 2027','Apple will not release its entry-level iPad until early 2027.'), ('Entry-level iPad not expected until early 2028','Apple will not release its entry-level iPad until early 2028.'))
        self.assert_separate(('Entry-level iPad not expected until early 2027','Apple will not release its entry-level iPad until early 2027.'), ('iPad Air not expected until early 2027','Apple will not release its iPad Air until early 2027.'))

    def test_natural_os_adaptation_requires_new_compatibility_work(self):
        positive = self.profile('Developer brings Aurora OS to Apple Silicon Mac', 'A developer released an open-source project adapting the recovery image for virtual hardware. A new Vulkan to Metal translation layer lets the guest use the Mac GPU.')
        self.assertEqual(positive.relevance_tier, 'ecosystem')
        for lead in (
            'A developer runs Aurora OS on Mac with an existing QEMU configuration, using only CPU emulation.',
            'An open-source utility runs on Mac and uses Metal to render its ordinary app interface.',
            'A developer plans to adapt the recovery image and build a Vulkan to Metal translation layer letting the guest use the Mac GPU; nothing has been released.'):
            p = self.profile('Developer runs Aurora OS on Mac', lead)
            self.assertNotEqual(p.relevance_tier, 'ecosystem')

    def test_owner_satisfaction_is_subjective_despite_percentages(self):
        events, _ = self.cluster_sources('72527b59f290315caef14f7e')
        self.assertEqual(len(events), 1)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        for title, body in (
            ('iOS设备好评榜公布', '本月用户调查中iPhone 17 Pro好评率达到98%，排名第一。'),
            ('iPhone device satisfaction ranking released', 'An owner survey gives iPhone 17 a satisfaction score of 98 percent, ahead of older models.')):
            self.assertEqual(self.profile(title, body).relevance_tier, 'weak')
        p = self.profile('iPhone charge limit results after two years',
            'A test measures battery capacity at 94% after 600 charge cycles, compared with 89% for the unrestricted device.')
        self.assertEqual(p.relevance_tier, 'strong')
        self.assertIn('longitudinal-battery-measurement', ' '.join(p.event_keys))

    def test_natural_ratings_are_not_purchase_intention_or_os_features(self):
        for title, lead in (
            ('Poll: which iOS device would you buy?', 'Readers report their purchase intent, not device satisfaction rates.'),
            ('Apple improves iOS performance', 'Apple releases an iOS update improving camera performance.')):
            self.assertNotIn('owner-rating-ranking',' '.join(self.profile(title, lead).event_keys))

    def test_hardware_conditions_do_not_create_historical_siri_rollouts(self):
        sid = '497793ab3afdb67e9465296b'
        evidence = self.source_articles(sid)[0].evidence
        projections, remaining, excluded = self.m.project_article_evidence(evidence)
        self.assertFalse(projections)
        self.assertTrue({evidence.units[i].unit_id for i in (12,39)} <= {span[0] for span in remaining})
        current = replace(evidence, title='Apple expands Siri AI to new languages today',
            raw_lead='Apple today announced Siri AI now supports French and Japanese.',
            units=(replace(evidence.units[0], text='Apple today announced Siri AI now supports French and Japanese.'),))
        projections, _, _ = self.m.project_article_evidence(current)
        self.assertTrue(projections)
        self.assertEqual({p.subject for p in projections}, {'siri'})

    def test_review_source_actor_action_and_stage_boundaries(self):
        cases = (
            (("Report: Apple's new smart home hub will cost $499", "According to Mark Gurman, Apple's smart home hub is expected to cost $499."), ("Report: Apple's new smart home hub will ship in November", "According to Mark Gurman, Apple's smart home hub will ship in November.")),
            (("Report: new Apple TV will ship in November", "Apple TV will ship in November. Apple previously tested microphones and a remote with a speaker."), ("Apple testing microphones for new Apple TV", "Apple is testing microphones and a remote with a speaker for the new Apple TV.")),
            (("Apple executive Tim Cook will meet governor of Guangdong", "Tim Cook will meet the governor of Guangdong next month."), ("Apple executive Tim Cook met governor of Guangdong", "Tim Cook met the governor of Guangdong today.")),
            (("Apple executive Tim Cook cancels meeting with governor of Guangdong", "Tim Cook canceled his meeting with the governor of Guangdong."), ("Apple executive Tim Cook met governor of Guangdong", "Tim Cook met the governor of Guangdong today.")),
            (("Cedar project brings Aurora OS to Apple Silicon Mac", "A developer released Cedar, an open-source project adapting the recovery image for virtual hardware. A new Vulkan to Metal translation layer lets the guest use the Mac GPU."), ("Birch project brings Aurora OS to Apple Silicon Mac", "Another developer released Birch, an open-source project adapting the recovery image for virtual hardware. A new Vulkan to Metal translation layer lets the guest use the Mac GPU.")),
        )
        for pair in cases:
            with self.subTest(pair=pair): self.assert_separate(*pair)
        third = self.profile('Atlas reveals new smart home hub with Apple Home support', 'According to Atlas, its new smart home hub supports Apple Home and ships next month.')
        self.assertEqual(third.relevance_tier, 'weak')
        background = self.profile('Apple executive Tim Cook announces new iPhone factory', 'Apple executive Tim Cook announced a new iPhone factory today. Tim Cook met the governor of Guangdong during his tour.')
        self.assertNotIn('government-meeting', ' '.join(background.event_keys))

    def test_review_catalog_polarity_subject_and_executive_projection(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        from apple_news_core.article_projector import project_smart_home_roadmap, project_executive_visit_actions
        def evidence(title, texts, kind='li'):
            return ArticleEvidence('review', 'MacRumors', 'https://example.com/review', title, texts[0], 'news',
                tuple(EvidenceUnit(str(i),kind,text,'html',i) for i,text in enumerate(texts)))
        title = 'New Apple TV 4K and HomePod mini: details just leaked'
        base = ["Apple's home hub will be named HomeView.", 'HomeView will feature an A18 chip.',
            'The new HomePod mini will feature an S10 chip.', 'The new Apple TV 4K will feature an A19 chip.']
        for extra in ('HomePod mini will support independently developed third-party accessories.',
                      'HomeView will not include third-party accessories.',
                      'Apple and Atlas did not co-develop the accessories.'):
            rows = project_smart_home_roadmap(title, base[0], base+[extra], fact_limit=50, evidence=evidence(title,base+[extra]))
            self.assertFalse(any('partnership disclosure' in row[0] for row in rows))
        extra = 'HomePod mini will feature the S10 chip, unlike HomeView with A18.'
        rows = project_smart_home_roadmap(title,base[0],base+[extra],fact_limit=50,evidence=evidence(title,base+[extra]))
        self.assertTrue(all('HomePod mini' in row[0] for row in rows if extra in row[2]))
        from apple_news_core.event_identity import source_executive_government_frame
        for stage, action in (('will meet','planned-government-meeting'),('met','government-meeting'),('cancels meeting with','government-meeting-cancelled')):
            title = 'Apple executive Tim Cook ' + stage + ' governor of Guangdong'
            rows = project_executive_visit_actions(title,title,evidence(title,[title+' next month.'],'p'),fact_limit=50)
            self.assertTrue(rows)
            self.assertEqual(source_executive_government_frame(rows[0][0], rows[0][1]).action, action)
        title = 'Apple executive Tim Cook met governor of Guangdong'
        for other in ('Microsoft CEO Nadella met developers in Guangzhou.', '微软首席执行官纳德拉与开发者交流，参观广州零售店。'):
            rows = project_executive_visit_actions(title,title,evidence(title,[title+' today.',other],'p'),fact_limit=50)
            self.assertEqual(len(rows),1)
            self.assertNotIn(other,rows[0][2])

    def test_rereview_predicate_actor_counterparty_and_current_clause_ownership(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        from apple_news_core.article_projector import project_smart_home_roadmap, project_executive_visit_actions
        def evidence(title, texts, kind='li'):
            return ArticleEvidence('review', 'MacRumors', 'https://example.com/review', title, texts[0], 'news',
                tuple(EvidenceUnit(str(i),kind,text,'html',i) for i,text in enumerate(texts)), published_utc='2026-10-12T00:00:00+00:00')
        title = 'New Apple TV 4K and HomePod mini: details just leaked'
        base = ["Apple's home hub will be named HomeView.", 'HomeView will feature an A18 chip.',
            'The new HomePod mini will feature an S10 chip.', 'The new Apple TV 4K will feature an A19 chip.']
        for extra, expected in (('These accessories were not developed in partnership with Apple.', None),
                                ('Unlike HomeView, HomePod mini will feature an S10 chip.', 'HomePod mini')):
            rows=project_smart_home_roadmap(title,base[0],base+[extra],fact_limit=50,evidence=evidence(title,base+[extra]))
            if expected is None:
                self.assertFalse(any('partnership disclosure' in row[0] for row in rows))
            else:
                self.assertTrue(any(extra in row[2] for row in rows))
                self.assertTrue(all(expected in row[0] for row in rows if extra in row[2]))
        title='Apple executive Tim Cook met governor of Guangdong'
        for extra in ('苹果高管特努斯与开发者交流，参观广州零售店。','Tim Cook met governor of Zhejiang today.'):
            rows=project_executive_visit_actions(title,title,evidence(title,[title+' today.',extra],'p'),fact_limit=50)
            self.assertEqual(len(rows),1)
            self.assertNotIn(extra,rows[0][2])
        title='Apple executive Tim Cook plans to visit Guangdong'
        text='Apple executive Tim Cook will meet governor of Guangdong next month.'
        rows=project_executive_visit_actions(title,text,evidence(title,[text],'p'),fact_limit=50)
        self.assertEqual(rows[0][0], title)
        self.assertIn(text, rows[0][2])
        title='Apple executive Tim Cook met governor of Guangdong last year'
        self.assertFalse(project_executive_visit_actions(title,title,evidence(title,[title+'.'],'p'),fact_limit=50))
        title='苹果 Siri AI 今天新增语言支持'
        text='Siri AI 今年9月仅支持英语，今天新增法语和日语支持。'
        projections, remaining, _=self.m.project_article_evidence(evidence(title,[text],'p'))
        self.assertTrue(projections)
        self.assertTrue(all('英语' not in ' '.join(p.key_facts) for p in projections))
        self.assertTrue(any('法语' in ' '.join(p.key_facts) and '日语' in ' '.join(p.key_facts) for p in projections))
        self.assertTrue(remaining)

    def test_focused_finishes_and_employee_deployment_keep_existing_objects(self):
        from apple_news_core.event_identity import source_hardware_action_frame
        for title, lead in (
            ("Apple's All-New Home Hub Rumored to Launch in These Four Colors", "According to a leaker, Apple's home hub will launch in four finishes."),
            ('苹果开始向更多直营店员工配发 iPhone 16，优化 Tap to Pay 体验', '苹果将向更多 Apple Store 员工配发 iPhone 16，并逐步淘汰旧读卡器。'),
            ('Report: Atlas smart hub named Nestling with new chip', 'According to Atlas, its new smart hub works with Apple Home.'),
            ('消息称 Atlas 智能家居中枢定名 Nestling，搭载新芯片', '记者透露，Atlas 的新品兼容 Apple Home。'),
        ):
            with self.subTest(title=title):
                self.assertIsNone(source_hardware_action_frame(title, lead, ()))
        self.assert_separate(
            ("Apple's All-New Home Hub Rumored to Launch in These Four Colors", "According to a leaker, Apple's home hub will launch in four finishes."),
            ("Report: Apple smart home hub named Nestling with A18 chip", "According to Mark Gurman, Apple's new hub will be named Nestling and feature an A18 chip."))

    def test_second_live_preorders_are_a_reported_sales_stage(self):
        sid='45480dffd95cbcbad8708e4f'
        events, _=self.cluster_sources(sid)
        self.assertEqual(len(events),1)
        self.assertEqual(self.m.article_reconciliation_profile(events[0].articles[0]).relevance_tier,'strong')
        self.assertTrue(any('preorder-schedule' in k for k in self.m.article_reconciliation_profile(events[0].articles[0]).event_keys))
        events, _=self.cluster_sources(sid,'bd67fc4b61a9d1a526b63667')
        self.assertTrue(all(len(self.source_ids(e))==1 for e in events))
        reported=('New Apple TV 4K and HomePod Mini 2 Pre-Orders Expected to Begin This Week',
                  'A new report says both devices should be available to pre-order starting this week.')
        for other in (
            ('New Apple TV 4K and HomePod Mini 2 will ship this week','A new report says both devices will be delivered this week.'),
            ('New Apple TV 4K and HomePod Mini 2 pre-orders expected next week','A new report says both devices should be available to pre-order starting next week.'),
            ('Apple confirms Apple TV 4K and HomePod Mini 2 pre-orders begin this week','Apple officially confirmed both devices will be available to pre-order starting this week.'),
            ('Apple TV 4K and HomePod Mini 3 pre-orders expected this week','A new report says both devices should be available to pre-order starting this week.'),
            ('Apple TV 4K and HomePod Mini 2 pre-orders now open this week','Apple announced both devices are available to pre-order starting this week.')):
            with self.subTest(other=other): self.assert_separate(reported,other)
        unrelated=self.profile('Apple TV and HomePod pre-orders expected this week',
            'A new report says iPhone 18 pre-orders will begin this week.')
        self.assertFalse(any('preorder-batch' in key for key in unrelated.event_keys))
        for title,lead in (
            ('Apple TV and HomePod news this week: recap','A recap of previously reported announcements, without new reporting.'),
            ('Apple TV and HomePod pre-orders this week?','An educated guess based on historical patterns, with no new report.')):
            self.assertEqual(self.profile(title,lead).relevance_tier,'weak')

    def test_second_live_os_adaptation_uses_an_existing_graphics_library(self):
        ids=('35e103e77589249df87b60b2','71ff4e0f1782f9c3f2cbe856','8862265b7a97a61af5a92e4d')
        for order in (ids,ids[::-1]):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),1)
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier=='ecosystem' for a in events[0].articles))
        title='Cedar项目让Aurora OS在Mac运行'
        lead='开发者发布名为Cedar的开源项目，修改恢复镜像来适配虚拟硬件。项目将Vulkan调用转换为Metal，让客体调用Mac的GPU。'
        self.assertEqual(self.profile(title,lead).relevance_tier,'ecosystem')
        for text in ('开发者发布名为Cedar的工具，启动已有虚拟机，只使用CPU软件渲染。',
                     '开发者发布名为Cedar的工具，启动现成系统映像，以现有图形库将Vulkan调用转换为Metal，调用Mac的GPU。'):
            self.assertEqual(self.profile(title,text).relevance_tier,'weak')

    def test_relative_preorders_require_a_current_affirmative_schedule(self):
        from apple_news_core.event_identity import source_dated_launch_frame
        positive=('Apple TV and HomePod pre-orders expected to begin this week',
                  'A report says both devices will be available to pre-order starting this week.')
        for title,lead in (
            ('Apple TV and HomePod pre-orders not expected to begin this week',
             'A report says both devices will be available to pre-order starting next week.'),
            ('Apple cancels plans to open Apple TV and HomePod pre-orders this week',
             'A report says both devices were expected to be available to pre-order starting this week.'),
            ('Apple TV and HomePod pre-orders expected to begin this week',
             'A report says both devices were expected to be available to pre-order starting this week.'),
            ('苹果取消本周开启 Apple TV 和 HomePod 预购的计划',
             '报道称，两款设备此前计划本周开启预购。')):
            with self.subTest(title=title,lead=lead):
                self.assertIsNone(source_dated_launch_frame(title,lead,()))
                self.assertFalse(any('preorder-schedule-reported' in key for key in self.profile(title,lead).event_keys))
                self.assert_separate(positive,(title,lead))
        self.assertIsNotNone(source_dated_launch_frame(*positive,()))

    def test_catalog_configuration_children_rejoin_their_focused_reports(self):
        aggregate='ad36090e826cb98e42617cda'
        focused=('89dc6c321a3577aafbf7ad16','c959f15b04815dba4797bec3','95014c2a571939d323ec00aa')
        for order in ((aggregate,*focused),(*focused[::-1],aggregate)):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),5)
            for sid in focused:
                event=next(e for e in events if sid in self.source_ids(e))
                self.assertEqual(self.source_ids(event),{aggregate,sid})
                self.assertEqual(Counter(a.url for a in event.articles),Counter(self.rows[x]['evidence']['url'] for x in (aggregate,sid)))
        configuration=('Report: HomePod mini 2 configuration upgrades',
            'According to a new report, the new HomePod mini will be equipped with an S10 chip, up from the S5 chip in the current model.')
        for other in (
            ('HomePod mini pre-orders begin this week','A new report says HomePod mini pre-orders will begin this week.'),
            ('HomePod mini will ship on October 30','A report says HomePod mini with an S10 chip, up from S5, will ship on October 30.'),
            ('Report: Apple Watch configuration upgrades','A report says the new Apple Watch will be equipped with an S10 chip, up from the S5 chip in the current model.'),
            ('Report: HomePod mini 2 configuration upgrades','A report says the new HomePod mini will be equipped with an S11 chip, up from the S5 chip in the current model.'),
            ('Report: HomePod mini 3 configuration upgrades','A report says the new HomePod mini will be equipped with an S10 chip, up from the S5 chip in the current model.'),
            ('Atlas speaker configuration upgrades','Atlas is upgrading its speaker. HomePod mini uses an S10 chip, up from the S5 chip in the old model.')):
            with self.subTest(other=other): self.assert_separate(configuration,other)
        delivery=('Apple TV and HomePod mini to ship on October 30',
            'The new Apple TV and HomePod mini will launch on October 30, according to a report.')
        for other in (
            ('Apple TV and HomePod mini to ship on November 6','A report says the new Apple TV and HomePod mini will launch on November 6.'),
            ('Apple TV and HomePod mini not expected to ship on October 30','A report says the new Apple TV and HomePod mini will launch on November 6.'),
            ('Apple cancels Apple TV and HomePod mini shipment plans','The Apple TV and HomePod mini were previously expected to launch on October 30.'),
            ('Apple TV and HomePod mini now shipping','Apple announced the new Apple TV and HomePod mini launch on October 30.'),
            ('Apple TV and HomePod mini pre-orders begin this week','A report says Apple TV and HomePod mini pre-orders will begin this week.')):
            with self.subTest(other=other): self.assert_separate(delivery,other)

    def test_configuration_and_joint_delivery_require_owned_current_actions(self):
        from apple_news_core.event_identity import source_hardware_action_frame
        delivery=('Apple TV and HomePod mini to ship on October 30',
            'According to a report, Apple TV and HomePod mini will launch on October 30.')
        configuration=('Report: HomePod mini 2 configuration upgrades',
            'According to a report, the new HomePod mini will be equipped with an S10 chip, up from the S5 chip in the current model.')
        for title,lead,positive in (
            ('Apple TV and HomePod mini shipping dates reported',
             'According to a report, Apple TV will launch on October 30, while HomePod mini will launch on November 6.',delivery),
            ('Apple TV and HomePod mini shipped on October 30',
             'Apple TV and HomePod mini shipped on October 30, according to a report.',delivery),
            ('Apple cancels HomePod mini 2 configuration upgrades',configuration[1],configuration),
            ('HomePod mini 2 configuration upgrades are not planned',configuration[1],configuration)):
            with self.subTest(title=title):
                frame=source_hardware_action_frame(title,lead,())
                if positive == configuration:
                    self.assertIn(frame.action, {'configuration-plan-cancelled','configuration-plan-denied'})
                else:
                    self.assertIsNone(frame)
                self.assert_separate(positive,(title,lead))
        self.assertIsNotNone(source_hardware_action_frame(*delivery,()))
        self.assertIsNotNone(source_hardware_action_frame(*configuration,()))
        for left,right in (
            (delivery,('Apple TV and HomePod to ship on October 30','According to a report, Apple TV and HomePod will launch on October 30.')),
            (('Apple TV and HomePod mini 2 to ship on October 30','A report says Apple TV and HomePod mini 2 will launch on October 30.'),
             ('Apple TV and HomePod mini 3 to ship on October 30','A report says Apple TV and HomePod mini 3 will launch on October 30.')),
            (('Apple TV and HomePod mini to ship on October 30, 2026','A report says Apple TV and HomePod mini will launch on October 30, 2026.'),
             ('Apple TV and HomePod mini to ship on October 30, 2027','A report says Apple TV and HomePod mini will launch on October 30, 2027.'))):
            with self.subTest(left=left,right=right): self.assert_separate(left,right)

    def test_configuration_plan_polarity_survives_all_profile_adapters(self):
        from apple_news_core.event_identity import source_hardware_action_frame, build_event_identity
        from apple_news_core.event_reconciler import build_reconciliation_profile
        lead='According to a report, the new HomePod mini will be equipped with an S10 chip, up from the S5 chip in the current model.'
        positive=('Apple HomePod mini technical details',lead)
        self.assertTrue(any('technical-details-disclosure' in key for key in self.profile(*positive).event_keys))
        for title,action in (
            ('Apple cancels HomePod mini 2 configuration upgrades','configuration-plan-cancelled'),
            ('HomePod mini 2 configuration upgrades are not planned','configuration-plan-denied')):
            with self.subTest(title=title):
                p=self.profile(title,lead)
                self.assertTrue(any(action in key for key in p.event_keys))
                self.assertFalse(any('technical-details-disclosure' in key or 'device-configuration-report' in key for key in p.event_keys))
                frame=source_hardware_action_frame(title,lead,())
                self.assertEqual((frame.subject,frame.action,frame.model_generation),('homepod-mini',action,'2'))
                core=build_reconciliation_profile(title=title,lead=lead,identity=build_event_identity(title,lead),exact_facets=(),regions=())
                self.assertEqual(core.event_keys,p.event_keys)
                self.assertEqual(self.m.classify_relevance_tier(title,lead,[],'MacRumors')[0],p.relevance_tier)
                self.assertEqual(self.m.source_text_outcome(title,lead,[],'MacRumors')[2],'hardware_products')
                self.assertEqual(self.m.source_text_profile(title,lead,[],'MacRumors').event_kind_hint,'hardware_market')
                final_events=self.m.cluster_articles([article_for(self.m,title,lead)])
                self.assertEqual((final_events[0].event_kind,final_events[0].category),('hardware_market','hardware_products'))
                serialized=self.m.event_to_dict(final_events[0],timezone.utc)
                self.assertEqual((serialized['event_kind'],serialized['category']),('hardware_market','hardware_products'))
                self.assertEqual(serialized['sources'][0]['title'],title)
                self.assertEqual(self.m.classify_projected_article_relevance(title,title,lead,[],'MacRumors')[0],p.relevance_tier)
                self.assert_separate(positive,(title,lead))


    def test_catalog_tv_candidate_configuration_rejoins_focused_report(self):
        aggregate='ad36090e826cb98e42617cda'
        tv='c1e8b0f3ec3c19c13f55acdc'
        others=('89dc6c321a3577aafbf7ad16','c959f15b04815dba4797bec3','95014c2a571939d323ec00aa')
        for ids in ((aggregate,tv),(aggregate,tv,*others)):
            for order in (ids,ids[::-1]):
                events,_=self.cluster_sources(*order)
                self.assertEqual(len(events),5)
                event=next(e for e in events if tv in self.source_ids(e))
                self.assertEqual(self.source_ids(event),{aggregate,tv})
                expected=Counter({self.rows[aggregate]['evidence']['url']:5})
                expected.update(self.rows[x]['evidence']['url'] for x in ids[1:])
                self.assertEqual(Counter(a.url for e in events for a in e.articles),expected)
                by_id={a.evidence.article_id:a for a in event.articles}
                self.assertIn('may have',' '.join(by_id[aggregate].key_facts))
                self.assertIn('tested',' '.join(by_id[tv].key_facts))
                self.assertRegex(' '.join(by_id[tv].key_facts),r'unclear|unknown|whether|not confirmed')

    def test_tv_candidate_configuration_preserves_action_boundaries(self):
        positive=('Apple TV 4K hardware configuration disclosure',
            'The new Apple TV 4K may have built-in microphones. The new Apple TV 4K may have an updated remote with a built-in speaker.')
        self.assertTrue(any('hardware-configuration-test-report' in k for k in self.profile(*positive).event_keys))
        for other in (
            ('New Apple TV will ship on October 30','Apple previously tested microphones and a remote with a speaker.'),
            ('Apple TV hardware configuration confirmed for production','Apple confirmed production of Apple TV with built-in microphones and a remote speaker.'),
            ('Apple announces Apple TV hardware configuration','Apple announced Apple TV with built-in microphones and a remote speaker.'),
            ('Atlas remote for Apple TV hardware configuration disclosure','The Atlas remote may have built-in microphones and a speaker for Apple TV.'),
            ('Apple TV software configuration disclosure','Apple TV may have new Siri software features using microphones in existing remotes.'),
            ('Apple cancels Apple TV hardware configuration upgrades',positive[1]),
            ('Apple TV hardware configuration upgrades are not planned',positive[1])):
            with self.subTest(other=other):
                self.assertFalse(any('hardware-configuration-test-report' in k for k in self.profile(*other).event_keys))
                self.assert_separate(positive,other)

    def test_tv_candidate_configuration_history_is_not_current_identity(self):
        positive=('Apple TV hardware configuration disclosure',
            'The new Apple TV 4K may have built-in microphones. The new Apple TV 4K may have an updated remote with a built-in speaker.')
        for other in (
            ('Apple TV hardware configuration disclosure from last year',positive[1]),
            (positive[0],'Last year, the new Apple TV 4K may have been planned with built-in microphones and a remote with a built-in speaker.'),
            (positive[0],'The new Apple TV 4K may have built-in microphones, according to last year’s plan. The new Apple TV 4K may have an updated remote with a built-in speaker, as reported last year.')):
            with self.subTest(other=other):
                self.assertFalse(any('hardware-configuration-test-report' in k for k in self.profile(*other).event_keys))
                self.assert_separate(positive,other)
        current=('New Apple TV hardware configuration disclosure',
            'The new Apple TV 4K may have built-in microphones, according to a new report by Mark Gurman. Last year’s model did not have these microphones.')
        self.assertTrue(any('hardware-configuration-test-report' in k for k in self.profile(*current).event_keys))
        articles=[article_for(self.m,*x) for x in (positive,current)]
        self.assertEqual(len(self.m.cluster_articles(articles)),1)

    def test_hardware_development_source_details_reach_fact_view(self):
        article=self.source_articles('2026c53522ad68308c77c076')[0]
        view=self.m.prepare_source_fact_view(article)
        for n in (2,14):
            unit=article.evidence.units[n]
            facts=[f for f in (*view.normal,*view.unprocessed) if f.text==unit.text]
            self.assertTrue(facts,unit.text)
            self.assertIn((article.source,article.url,article.evidence.article_id,unit.unit_id,0,len(unit.text)),facts[0].origins)
        events,_=self.cluster_sources('2026c53522ad68308c77c076')
        output=self.m.event_to_dict(events[0],self.m.ZoneInfo('Asia/Singapore'))
        serialized=json.dumps(output,ensure_ascii=False)
        for n in (2,14):self.assertIn(article.evidence.units[n].text,serialized)

    def test_hardware_development_details_require_local_owner_and_attribution(self):
        title='苹果正在研发家用摄像头'
        lead='科技记者李明透露，苹果正在研发一款代号为K720的家用摄像头。'
        details=('外形上，K720是一个小巧的金属圆柱体。',
                 'K720采用陶瓷外壳。',
                 'K720是一个球形设备。',
                 '李明指出了这种设计的限制：发生盗窃时，用户需要录像作为证据，仅凭文字描述难以发挥作用。')
        negatives=('外形上，K730是一个小巧的金属圆柱体。',
                   '竞品的摄像头是一个小巧的金属圆柱体。',
                   '我认为这种设计很糟糕，发生盗窃时没有录像作为证据。',
                   '王华指出了这种设计的限制：发生盗窃时，用户需要录像作为证据，仅凭文字描述难以发挥作用。',
                   '李明指出了竞品这种设计的限制：发生盗窃时，用户需要录像作为证据，仅凭文字描述难以发挥作用。',
                   '这项设计没有证据证明会成功，作者觉得它让人失望。')
        for detail in (*details,*negatives):
            with self.subTest(detail=detail):
                article=article_for(self.m,title,lead,facts=[lead])
                article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
                view=self.m.prepare_source_fact_view(article)
                texts=[f.text for f in (*view.normal,*view.unprocessed)]
                self.assertEqual(detail in texts,detail in details)

    def test_development_details_follow_local_subject_switches(self):
        title='苹果正在研发家用摄像头'
        lead='科技记者李明透露，苹果正在研发一款代号为K720的家用摄像头。'
        other='科技记者王华透露，苹果正在研发另一款代号为K730的家用摄像头。'
        limit='李明表示，这种设计在断网时无法保存记录，仅可本地处理数据。'
        shape='外形上，K730是一个小巧的金属圆柱体。'
        back='K720采用金属圆柱体外壳。'
        for paragraphs,expected in (([other,shape,limit],False),([other,shape,back,limit],True)):
            article=article_for(self.m,title,lead,facts=[lead])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article>'+''.join('<p>'+x+'</p>' for x in [lead,*paragraphs])+'</article>',title)
            view=self.m.prepare_source_fact_view(article)
            texts=[f.text for f in (*view.normal,*view.unprocessed)]
            self.assertNotIn(shape,texts)
            self.assertEqual(limit in texts,expected)
        for peer in ('K720A','AK720'):
            paragraphs=[lead,'科技记者王华透露，苹果正在研发另一款代号为'+peer+'的家用摄像头。',peer+'采用金属圆柱体外壳。',limit]
            article=article_for(self.m,title,lead,facts=[lead])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article>'+''.join('<p>'+x+'</p>' for x in paragraphs)+'</article>',title)
            self.assertNotIn(limit,[f.text for f in self.m.prepare_source_fact_view(article).normal])
        opinion='外形上，K720是一个小巧的金属圆柱体，我觉得这种设计很优秀。'
        article=article_for(self.m,title,lead,facts=[lead])
        article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article><p>'+lead+'</p><p>'+opinion+'</p></article>',title)
        self.assertNotIn(opinion,[f.text for f in self.m.prepare_source_fact_view(article).normal])

    def test_captured_visit_result_and_adaptation_delivery_have_exact_facts(self):
        for sid,n in (('034d8140970179b342c7dde7',1),('8862265b7a97a61af5a92e4d',3)):
            article=self.source_articles(sid)[0]
            unit=article.evidence.units[n]
            view=self.m.prepare_source_fact_view(article)
            facts=[f for f in (*view.normal,*view.unprocessed) if f.text==unit.text]
            self.assertTrue(facts,unit.text)
            self.assertIn((article.source,article.url,article.evidence.article_id,unit.unit_id,0,len(unit.text)),facts[0].origins)
            events,_=self.cluster_sources(sid)
            output=json.dumps(self.m.event_to_dict(events[0],self.m.ZoneInfo('Asia/Singapore')),ensure_ascii=False)
            self.assertIn(unit.text,output)

    def test_support_operations_keep_actor_and_editorial_boundaries(self):
        for title,lead,detail in (
            ('苹果高管李明到访工厂参观 iPhone 生产线','苹果高管李明到访制造商，与生产线员工交流。',
             '其他公司的王华还到访了另一家工厂。据介绍，双方通过共同努力，实现了从所有产品包装中移除塑料的目标。'),
            ('Mac 系统适配项目发布','开发者发布了一个 Mac 系统适配项目，支持新的虚拟设备。',
             '另一个项目的工具被封装成一个可点击的macOS应用，直接拖入Dock即可使用。'),
            ('Mac 应用新增记录保存功能','这个 Mac 应用可以保存操作记录。',
             '这个 Mac 应用可以保存记录，证据显示它令人失望而且没有实用价值，作者建议读者避开这个工具。'),
            ('Mac 系统适配项目发布','开发者发布了一个 Mac 系统适配项目，支持新的虚拟设备。',
             '我觉得将整个过程封装成一个macOS应用很优秀，直接拖入Dock即可使用。')):
            article=article_for(self.m,title,lead,facts=[lead])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
            self.assertNotIn(detail,[f.text for f in self.m.prepare_source_fact_view(article).normal])

    def test_fact_support_discourse_subject_switches(self):
        title='苹果正在研发家用摄像头'
        lead='科技记者李明透露，苹果正在研发一款代号为K720的家用摄像头。'
        peer='另一款摄像头由三星研发，主要用于室外安防。'
        limit='李明表示，这种设计在断网时无法保存记录，仅可本地处理数据。'
        for paragraphs,expected in (([peer,limit],False),([peer,'K720采用陶瓷外壳。',limit],True)):
            article=article_for(self.m,title,lead,facts=[lead])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article>'+''.join('<p>'+x+'</p>' for x in [lead,*paragraphs])+'</article>',title)
            self.assertEqual(limit in [f.text for f in self.m.prepare_source_fact_view(article).normal],expected)
        title='苹果高管李明到访工厂参观 iPhone 生产线'
        lead='苹果高管李明到访制造商，与生产线员工进行交流。'
        for actor,expected in (('其他公司的王华',False),('苹果高管李明',True)):
            detail='此外，'+actor+'还到访了另一家工厂。据介绍，双方通过共同努力，实现了从所有苹果产品包装中移除塑料的目标。'
            article=article_for(self.m,title,lead,facts=[lead])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
            self.assertEqual(detail in [f.text for f in self.m.prepare_source_fact_view(article).normal],expected)

    def test_source_owned_officer_factory_visit_rejoins_without_losing_support(self):
        ids=('034d8140970179b342c7dde7','be8cc7c9a20fd777855d5adc')
        for order in (ids,ids[::-1]):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),1)
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertEqual(Counter(a.url for a in events[0].articles),Counter(self.rows[sid]['evidence']['url'] for sid in ids))
            plan=events[0].fact_plan
            all_facts=[*plan.facts,*plan.required,*plan.unprocessed]
            combined=' '.join(f.text for f in all_facts)
            for fragment in ('独家组装','关键制程','摄像头模组产线','阳极氧化','表面溅镀','全球最大的','裕同科技','移除塑料','20','1000'):
                self.assertIn(fragment,combined)
            for sid,ordinal in ((ids[1],1),(ids[1],2),(ids[1],3),(ids[0],1)):
                unit=self.rows[sid]['evidence']['units'][ordinal]
                self.assertTrue(any(sid==origin[2] and unit['unit_id']==origin[3] for f in all_facts for origin in f.origins))
    def test_officer_factory_visit_keeps_actor_date_place_and_stage(self):
        visit=('苹果首席运营官李明到访苏州星海工厂',
               '苹果首席运营官李明于10月11日到访苏州星海工厂，实地考察生产线。李明称，苏州星海工厂正在生产新款iPhone。')
        for other in (
            ('星海工厂独家组装新款iPhone','星海工厂独家组装新款iPhone，正在为新机发售加紧备货。'),
            (visit[0].replace('李明','王华'),visit[1].replace('李明','王华')),
            (visit[0].replace('苏州','杭州'),visit[1].replace('苏州','杭州')),
            (visit[0],visit[1].replace('10月11日','10月12日')),
            ('苹果首席运营官李明计划到访苏州星海工厂',visit[1].replace('于10月11日到访','计划于10月11日到访'))):
            with self.subTest(other=other):self.assert_separate(visit,other)

    def test_factory_visit_headline_date_belongs_to_named_visit(self):
        lead='据报道，苹果首席运营官李明到访苏州星海工厂，实地考察新机生产线。'
        self.assert_separate(('苹果首席运营官李明10月11日到访苏州星海工厂',lead),
                             ('苹果首席运营官李明10月12日到访苏州星海工厂',lead))

    def test_factory_visit_explicit_year_belongs_to_named_visit(self):
        lead='据报道，苹果首席运营官李明到访苏州星海工厂，实地考察新机生产线。'
        left=('苹果首席运营官李明2025年10月11日到访苏州星海工厂',lead)
        right=('苹果首席运营官李明2026年10月11日到访苏州星海工厂',lead)
        for entry,year in ((left,'2025'),(right,'2026')):
            p=self.profile(*entry)
            self.assertIn('source-report-year:'+year,p.separation_keys)
            self.assertIn('source-report-period:month:10:day:11',p.separation_keys)
        self.assert_separate(left,right)
        for stage,action in (('计划于','planned-corporate-visit'),('已于','corporate-visit')):
            p=self.profile('苹果首席运营官李明'+stage+'2026年10月11日到访苏州星海工厂',lead)
            self.assertIn('source-report-year:2026',p.separation_keys)
            self.assertIn('primary-claim-predicate:'+action,p.separation_keys)
        events=self.m.cluster_articles([article_for(self.m,*left),article_for(self.m,*right)])
        output=[self.m.event_to_dict(e,self.m.ZoneInfo('Asia/Singapore')) for e in events]
        self.assertEqual(len(output),2)
        self.assertTrue(all(len(e['sources'])==1 for e in output))

    def test_factory_visit_role_headline_owns_stage_and_date(self):
        lead='苹果首席运营官李明到访苏州星海工厂，实地考察生产线。'
        def entry(tail):return ('iPhone生产线考察：苹果COO'+tail+'到访苏州星海工厂',lead)
        self.assert_separate(entry('计划'),entry('已'))
        for tail,year,day,stage in (
            ('计划于2026年10月11日','2026','11','planned-corporate-visit'),
            ('已于2026年10月11日','2026','11','corporate-visit'),
            ('2025年10月11日','2025','11','corporate-visit'),
            ('2026年10月12日','2026','12','corporate-visit')):
            p=self.profile(*entry(tail))
            self.assertIn('source-report-year:'+year,p.separation_keys)
            self.assertIn('source-report-period:month:10:day:'+day,p.separation_keys)
            self.assertIn('primary-claim-predicate:'+stage,p.separation_keys)
        self.assert_separate(entry('2025年10月11日'),entry('2026年10月11日'))
        self.assert_separate(entry('2026年10月11日'),entry('2026年10月12日'))
        unrelated=self.profile(*entry('王华计划'))
        self.assertNotIn('primary-claim-predicate:planned-corporate-visit',unrelated.separation_keys)

    def test_visit_support_keeps_reporting_intro_and_named_attribution(self):
        title='iPhone生产线考察：苹果首席运营官李明到访苏州星海工厂'
        lead='苹果首席运营官李明到访苏州星海工厂，参观新款iPhone的生产线。'
        for detail,expected in (
            ('值得注意的是，新款iPhone由星海工厂负责组装生产，目前工厂正在备货，为即将到来的新机发售做准备。',True),
            ('李明在接受采访时表示，苏州星海工厂可以说是这一地区最大的智能手机制造工厂，也是当地规模最大的智能手机制造园区。',True),
            ('王华在接受采访时表示，苏州星海工厂可以说是这一地区最大的智能手机制造工厂，也是当地规模最大的智能手机制造园区。',False),
            ('李明在接受采访时表示，杭州晨光工厂可以说是这一地区最大的智能手机制造工厂，也是当地规模最大的智能手机制造园区。',False),
            ('新款iPhone由星海工厂负责组装生产，目前工厂正在备货，我觉得它特别好用，非常值得购买和推荐给所有用户。',False)):
            a=article_for(self.m,title,lead,facts=[lead])
            a.evidence=self.m.capture_article_evidence(a.source,a.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
            self.assertEqual(detail in [f.text for f in self.m.prepare_source_fact_view(a).normal],expected,detail)

    def test_prepared_reported_state_changes_keep_priority_and_exact_origin(self):
        sid='1dbe2299d7710a5589023c86'
        article=self.source_articles(sid)[0]
        unit=article.evidence.units[22];start=unit.text.index('现款');claim=unit.text[start:]
        events,_=self.cluster_sources(sid)
        output=self.m.event_to_dict(events[0],self.m.ZoneInfo('Asia/Singapore'))
        self.assertIn(claim,output['key_facts'])
        self.assertIn(claim,output['must_include_facts'])
        exact=next(x for x in output['fact_sources'] if x['text']==claim)
        self.assertTrue(any(o['unit_id']==unit.unit_id and o['start']==start and o['end']==len(unit.text) for o in exact['origins']))
        self.assertLessEqual(len(output['key_facts']),20)
        ordinary=article.evidence.units[19].text
        self.assertIn(ordinary,[f.text for f in events[0].fact_plan.unprocessed])
        self.assertNotIn(unit.text[:start],output['key_facts'])
        from apple_news_core.models import PreparedFact
        from apple_news_core.event_reconciler import reconcile_fact_views
        for title,lead,detail in (
            ('macOS adds automatic activity records','macOS now supports automatic activity recording.',
             '目前macOS并没有直接导出全部活动记录的功能，而新版本据称可能首次提供将记录保存为本地文件的选项。'),
            ('Apple Music adds offline program access','Apple Music adds new program access options.',
             '开发者表示，Apple Music目前不支持离线播放这类节目的功能，已经保存的内容需要网络连接才能访问。')):
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,facts=[lead])
                a.evidence=self.m.capture_article_evidence(a.source,a.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
                view=self.m.prepare_source_fact_view(a)
                fact=next(f for f in view.normal if f.text==detail)
                filler=tuple(PreparedFact('Ordinary explanatory observation '+str(i),'ordinary-'+str(i),roles=frozenset({'source-support-fact'})) for i in range(4))
                kept=reconcile_fact_views([replace(view,normal=(*filler,fact),structured=(),owned=())],base_limit=3,official_limit=3)
                self.assertIn(detail,[f.text for f in kept])
                self.assertLessEqual(len(kept),3)
                self.assertTrue(all(o[3] and o[4]==0 and o[5]==len(detail) for o in fact.origins))
        title='macOS adds automatic activity records';lead='macOS now supports automatic activity recording.'
        for detail in (
            '如果苹果能够为 macOS 增加记录导出的功能，就有机会改善当前无法保存记录的情况，并让用户更轻松地管理数据。',
            'Android目前并没有直接导出全部活动记录的功能，而新版本据称可能首次提供将记录保存为本地文件的选项。'):
            a=article_for(self.m,title,lead,facts=[lead])
            a.evidence=self.m.capture_article_evidence(a.source,a.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
            self.assertNotIn(detail,[f.text for f in self.m.prepare_source_fact_view(a).normal if 'source-condition' in f.roles])

    def test_attributed_source_clauses_survive_without_author_inference(self):
        mini=self.source_articles('1dbe2299d7710a5589023c86')[0]
        unit=mini.evidence.units[22];start=unit.text.index('现款')
        facts=(*self.m.prepare_source_fact_view(mini).normal,*self.m.prepare_source_fact_view(mini).unprocessed)
        kept=next((f for f in facts if f.text==unit.text[start:]),None)
        self.assertIsNotNone(kept)
        self.assertIn((mini.source,mini.url,mini.evidence.article_id,unit.unit_id,start,len(unit.text)),kept.origins)
        self.assertFalse(any(unit.text[:start] in f.text for f in facts))
        self.assertFalse(any(mini.evidence.units[16].text in f.text for f in facts))
        nasa=self.source_articles('8662bf6be59ce394e57465de')[0]
        unit=nasa.evidence.units[4]
        facts=self.m.prepare_source_fact_view(nasa).normal
        kept=next((f for f in facts if f.text==unit.text),None)
        self.assertIsNotNone(kept)
        self.assertIn((nasa.source,nasa.url,nasa.evidence.article_id,unit.unit_id,0,len(unit.text)),kept.origins)
        self.assertEqual(self.m.article_reconciliation_profile(nasa).relevance_tier,'weak')
        title='macOS adds automatic activity records';lead='macOS now supports automatic activity recording.'
        condition='如果用户开启 macOS 的自动记录功能，系统就会自动保存每次操作的时间和详细内容，用户可以在设置中查看这些记录。'
        article=article_for(self.m,title,lead,facts=[lead])
        article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article><p>'+lead+'</p><p>'+condition+'</p></article>',title)
        self.assertIn(condition,[f.text for f in self.m.prepare_source_fact_view(article).normal])

    def test_same_device_other_features_are_local_continuations(self):
        title='macOS adds automatic activity records';lead='macOS now supports automatic activity recording.'
        for detail in ('其他功能包括在 macOS 设置中查看自动保存的操作记录，用户可以按时间筛选记录，并将这些记录保存到本地文件。',
                       '另一种输入方式可以在 macOS 设置中开启，用户可以用键盘输入操作记录，并将这些记录保存到本地文件。'):
            article=article_for(self.m,title,lead,facts=[lead])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article><p>'+lead+'</p><p>'+detail+'</p></article>',title)
            self.assertIn(detail,[f.text for f in self.m.prepare_source_fact_view(article).normal])
            events=self.m.cluster_articles([article])
            self.assertIn(detail,self.m.event_to_dict(events[0],self.m.ZoneInfo('Asia/Singapore'))['key_facts'])

        title='苹果正在研发家用摄像头'
        lead='科技记者李明透露，苹果正在研发一款代号为K720的家用摄像头。'
        feature='其他功能包括识别家庭成员和宠物，并向用户发送文字通知。'
        limit='李明表示，这种设计在断网时无法保存记录，仅可本地处理数据。'
        article=article_for(self.m,title,lead,facts=[lead])
        article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article>'+''.join('<p>'+x+'</p>' for x in (lead,feature,limit))+'</article>',title)
        self.assertIn(limit,[f.text for f in self.m.prepare_source_fact_view(article).normal])
        events=self.m.cluster_articles([article])
        self.assertIn(limit,self.m.event_to_dict(events[0],self.m.ZoneInfo('Asia/Singapore'))['key_facts'])

    def test_current_smart_home_paragraph_report_projects_local_actions(self):
        sid='e0701414084a3f8381a73905'
        articles=self.source_articles(sid)
        self.assertEqual(len(articles),5)
        self.assertEqual(len(self.m.cluster_articles(articles)),5)
        self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier=='strong' for a in articles))
        self.assertEqual(len(self.m.cluster_articles(articles[::-1])),5)
        facts={a.title:' '.join(a.key_facts) for a in articles}
        tv=next(v for k,v in facts.items() if 'TV' in k and 'delivery' not in k)
        mini=next(v for k,v in facts.items() if 'HomePod' in k and 'delivery' not in k)
        hub=next(v for k,v in facts.items() if 'hub' in k)
        partnership=next(v for k,v in facts.items() if 'partnership' in k)
        delivery=next(v for k,v in facts.items() if 'delivery' in k)
        self.assertIn('测试了两项功能',tv);self.assertIn('A19',tv)
        self.assertIn('S10',mini);self.assertIn('粉色、白色、绿色、蓝色和午夜色',mini)
        self.assertIn('A18',hub);self.assertIn('11月中旬',hub);self.assertIn('App Store',hub)
        self.assertIn('欧洲市场',partnership);self.assertIn('财务负担',partnership)
        self.assertIn('10月30日',delivery)
        self.assertFalse('S10' in tv or 'A19' in mini or '40%至50%' in partnership)
        for a in articles:
            self.assertTrue(a.projected_fact_spans or a.bound_claim)
            self.assertEqual(a.url,self.rows[sid]['evidence']['url'])

    def test_paragraph_home_roadmap_requires_current_first_party_actions(self):
        from apple_news_core.article_projector import project_smart_home_roadmap
        title='苹果为何再次拓展智能家居市场？'
        current='苹果公司将于下周发布一系列智能家居新品。'
        details=['新款Apple TV配备新的芯片，苹果正在测试内置麦克风。',
                 '新款HomePod mini搭载新的芯片，并提供绿色和蓝色配色。']
        for lead,body,expected in (
            (current,details,2),
            ('苹果公司去年发布了一系列智能家居新品。',details,1),
            ('苹果公司否认下周发布一系列智能家居新品。',details,1),
            (current,['Apple TV、HomePod mini和家居中枢。'],1),
            (current,['去年Apple TV配备了新的芯片。','竞品HomePod mini配件提供新的颜色。'],1)):
            article=article_for(self.m,title,lead,facts=[lead,*body])
            article.evidence=self.m.capture_article_evidence(article.source,article.url,'<article>'+''.join('<p>'+x+'</p>' for x in [lead,*body])+'</article>',title)
            result=project_smart_home_roadmap(title,lead,[lead,*body],fact_limit=12,evidence=article.evidence)
            self.assertEqual(len(result),expected,(lead,body))

    def test_sparse_current_catalog_configuration_and_batch_rejoin(self):
        catalog='ad36090e826cb98e42617cda'
        paragraph='e0701414084a3f8381a73905'
        sparse='bd67fc4b61a9d1a526b63667'
        focused=('c959f15b04815dba4797bec3','c1e8b0f3ec3c19c13f55acdc','95014c2a571939d323ec00aa')
        for ids in ((sparse,*focused[:2]),(paragraph,catalog,*focused)):
            for order in (ids,ids[::-1]):
                events,_=self.cluster_sources(*order)
                self.assertEqual(len(events),2 if sparse in ids else 5)
                for sid in focused[:2] if sparse in ids else focused:
                    event=next(e for e in events if sid in self.source_ids(e))
                    self.assertIn(sparse if sparse in ids else paragraph,self.source_ids(event))
                expected=Counter({self.rows[x]['evidence']['url']: (2 if x==sparse else 5 if x in (paragraph,catalog) else 1) for x in ids})
                self.assertEqual(Counter(a.url for e in events for a in e.articles),expected)

    def test_sparse_configuration_and_local_batch_do_not_borrow_background(self):
        config=('Apple HomePod mini 2 hardware configuration disclosure',
                '新款HomePod mini据称将在处理性能和无线连接能力方面获得升级。')
        focused=('Report: HomePod mini 2 configuration upgrades',
                 'According to a report, the new HomePod mini will be equipped with an S10 chip, up from the S5 chip in the current model.')
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,*config),article_for(self.m,*focused)])),1)
        for title,lead in (
            (config[0].replace('mini 2','mini 3'),config[1]),
            (config[0],'去年新款HomePod mini据称将在处理性能和无线连接能力方面获得升级。'),
            ('Apple HomePod mini 2 pre-orders expected next week',config[1]),
            ('Apple cancels HomePod mini 2 configuration upgrades',config[1]),
            ('Atlas speaker hardware configuration disclosure',config[1])):
            with self.subTest(title=title,lead=lead): self.assert_separate(focused,(title,lead))
        reference=article_for(self.m,'Apple TV 4K and HomePod mini to ship on October 30',
            'The new Apple TV 4K with A19 chip and new HomePod mini with S10 chip will launch on October 30.')
        title='Apple TV and HomePod mini joint delivery schedule'
        lead='新款HomePod mini和Apple TV计划于10月30日开始向用户交付。'
        local=['升级版HomePod mini搭载S10芯片。','一款搭载标准A19芯片的新Apple TV机顶盒。']
        positive=article_for(self.m,title,lead,facts=[lead,*local])
        self.assertEqual(len(self.m.cluster_articles([reference,positive])),1)
        for other_title,other_lead,other_facts in (
            (title,lead,['去年新款Apple TV 4K搭载A19芯片。',local[0]]),
            (title.replace('Apple TV','Apple TV HD'),lead.replace('Apple TV','Apple TV HD'),local),
            (title,lead.replace('10月30日','11月6日'),local),
            (title,'新款HomePod mini计划于10月30日预购，而Apple TV计划于10月30日交付。',local),
            (title,lead.replace('计划于','已于'),local),
            ('Apple cancels Apple TV and HomePod mini delivery',lead,local),
            ('Atlas plans Apple TV and HomePod mini delivery',lead,local),
            (title.replace('mini','mini 3'),lead.replace('mini','mini 3'),local)):
            with self.subTest(title=other_title,lead=other_lead):
                article=article_for(self.m,other_title,other_lead,facts=[other_lead,*other_facts])
                self.assertEqual(len(self.m.cluster_articles([reference,article])),2)

    def test_delivery_dates_and_configuration_polarity_are_clause_local(self):
        from apple_news_core.event_identity import source_hardware_action_frame
        title='Apple TV and HomePod mini joint delivery schedule'
        delivery='新款HomePod mini和Apple TV计划于10月30日开始向用户交付。'
        configs=['升级版HomePod mini搭载S10芯片。','一款搭载标准A19芯片的新Apple TV机顶盒。']
        positive=article_for(self.m,title,delivery,facts=[delivery,*configs])
        mixed='新款HomePod mini和Apple TV计划于10月30日开始预购，并在11月6日交付。'
        mixed_article=article_for(self.m,title,mixed,facts=[mixed,*configs])
        mixed_profile=self.m.article_reconciliation_profile(mixed_article)
        self.assertNotIn('source-report-period:month:10:day:30',mixed_profile.separation_keys)
        self.assertEqual(len(self.m.cluster_articles([positive,mixed_article])),2)
        from apple_news_core.article_projector import project_smart_home_roadmap
        paragraph_title='苹果将扩展智能家居市场'
        paragraph_lead='苹果公司将于下周发布一系列智能家居新品。'
        paragraphs=[paragraph_lead,'新款Apple TV HD正在测试内置麦克风。','新款HomePod mini搭载新的芯片并提供绿色配色。']
        evidence=self.m.capture_article_evidence(positive.source,positive.url,'<article>'+''.join('<p>'+x+'</p>' for x in paragraphs)+'</article>',paragraph_title)
        projected=project_smart_home_roadmap(paragraph_title,paragraph_lead,paragraphs,fact_limit=12,evidence=evidence)
        self.assertTrue(any('Apple TV HD' in x[0] for x in projected))
        self.assertFalse(any('4K' in x[0] for x in projected))
        negative=['新款HomePod mini搭载S10芯片。','新款Apple TV并未搭载A19芯片。']
        frame=source_hardware_action_frame(title,delivery,tuple(negative))
        self.assertFalse(frame.aliases)
        for headline,detail in (
            ('Apple TV hardware configuration disclosure','去年苹果为新款Apple TV测试了内置麦克风和遥控器扬声器。'),
            ('Apple TV HD hardware configuration disclosure','新款Apple TV HD正在测试内置麦克风和遥控器扬声器。')):
            profile=self.profile(headline,detail)
            self.assertFalse(any('apple-tv-4k' in key or 'apple-tv:current-configuration' in key for key in profile.event_keys))
            self.assert_separate(('Apple TV 4K hardware configuration disclosure','The new Apple TV 4K may have built-in microphones and an updated remote with a built-in speaker.'),(headline,detail))

    def test_chinese_projected_configuration_and_delivery_keep_stage(self):
        from apple_news_core.event_identity import source_hardware_action_frame
        config=('Apple HomePod mini device disclosure','升级版HomePod mini搭载S12芯片，并新增绿色配色。')
        delivery=('Apple TV and HomePod mini joint delivery schedule','新款HomePod mini和Apple TV计划于11月6日开始向用户交付。')
        for title,lead in (config,delivery):
            self.assertEqual(self.profile(title,lead).relevance_tier,'strong')
            self.assertIsNotNone(source_hardware_action_frame(title,lead,()))
        for title,lead in (
            (config[0],'去年升级版HomePod mini搭载S12芯片，并新增绿色配色。'),
            ('Apple cancels HomePod mini configuration upgrades',config[1]),
            (delivery[0],'新款HomePod mini和Apple TV此前计划于11月6日开始向用户交付。'),
            (delivery[0],'新款HomePod mini计划于11月6日交付，而Apple TV计划于11月13日交付。'),
            (delivery[0],'新款HomePod mini和Apple TV已于11月6日向用户交付。')):
            frame=source_hardware_action_frame(title,lead,())
            self.assertTrue(frame is None or frame.action in {'configuration-plan-cancelled','configuration-plan-denied'},(title,lead,frame))

if __name__ == '__main__':
    unittest.main()
