"""Current disclosures own their release bundle, stage and source-local action."""
from datetime import datetime, timezone
from pathlib import Path
import json
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior
GROUPS = {'interoperability': ['29e1e506d96c9d259d0af901', '5176a7cd0f5d94abfdb0321a', 'd323e8896fc4a6f380a6a2c5'], 'home_controls': ['27db073baf4720a45e95cc15', '247ac2418b20f4dabcbb7bea', '9eb6e3add3c3efdda0fb0a88', 'f183bf0922d68ecba470da12', '75741b44e6851456d149152a', 'e4a02334a84d60057c8f9607'], 'home_cameras': ['95b1909d5d62d0b0ca05f89f', 'fb0481736bbc8e18ef855d77', 'ffadac7adef07f54c480fd05'], 'home_registry': ['76ef8dd741127ae87b1ef4da', 'db269b285ea27824c4613cdd', '36b32370bd856e1ced568d0c'], 'own_camera': ['eec8cb353c940454771f4097', '638222ce381e69d8e3f41c65'], 'f1_audio': ['16707a4d9419576310beca1c', '9f2a5caee9b60ec4d398993e', 'ad8eb5d540cced2b7d6ad2e0'], 'creative_labs': ['281364c070e0587baf6fdbd3', '7742e34a148e07fb8c0344f3', '0d873cf67c671281e9157bd1', '79397503563d58aded361266'], 'skin_reports': ['8f79917cdfdfa409e2aef3cb', '49924af8fcea1c86b15cde25', 'e90e985ad471c4d9859d1df8'], 'maintenance_rc': ['6382c6654c9da76f71cd764b', '67b3ba3dd72b4ee7a0741955'], 'document_layout': ['4481aa6c512f9006d8a0895b', '0027a8448cf671d808531933'], 'executive_sale': ['2d26c1cf123bf95639f997a1', '56044768a6d9b4a8a02bc0b6'], 'carrier_market': ['a6202b772dbcc474563e9ba3', '5572d3b30ab081b465dec0f8', 'b57602db137425c9b5e7f7ab'], 'app_submission': ['30a1ad3f69bc280ecdac48f7'], 'earnings_notice': ['aefac7b95cbe4dbcd64e0ab2'], 'browser_blocking': ['4fad0dd26cc76edeeefa4151'], 'executive_statement': ['8da1c1f89224ccf8ff29eb17'], 'system_apps': ['abb7ee47ec0c594091d3cfd7'], 'tax_proposal': ['c2522d3bc678931b5d0c14f8'], 'graphics_driver': ['eedee43fd2be56c659191031']}
WEAK = ['04d37edf081f9c8f8bb2c6b8', '59881cae04e182db0ad6de5c', '4b7e7a6468b1f259eaa0c45f', 'ea303a6801f6302e976f5fda', '43280ad123913a375ddb63b4', '042973d809b917f6cc55ded3', '300c57893e78c735079bfd1d', 'd5abe2fe0572b2b4b7ea391a']
SOFTWARE = {'interoperability', 'home_registry', 'f1_audio', 'creative_labs', 'maintenance_rc', 'document_layout', 'app_submission', 'browser_blocking', 'system_apps', 'executive_statement', 'tax_proposal', 'graphics_driver'}

class SourceBoundaryTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261008_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 8, tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_current_actions_reconcile_with_owned_category(self):
        for (name, ids) in GROUPS.items():
            for order in (ids, ids[::-1]):
                with self.subTest(group=name, reverse=order != ids):
                    (events, _) = self.cluster_sources(*order)
                    self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
                    self.assertEqual(self.source_ids(events[0]), set(ids))
                    self.assertEqual((events[0].relevance_tier, events[0].category), ('ecosystem' if name in {'interoperability', 'graphics_driver'} else 'strong', 'software_systems' if name in SOFTWARE else 'hardware_products'))

    def test_distinct_home_disclosures_do_not_bridge(self):
        names = ['home_controls', 'home_cameras', 'home_registry', 'own_camera']
        for order in (names, names[::-1]):
            (events, _) = self.cluster_sources(*(sid for name in order for sid in GROUPS[name]))
            self.assertEqual({frozenset(self.source_ids(e)) for e in events}, {frozenset(GROUPS[name]) for name in names})

    def test_promotions_accessories_and_recap_stay_weak(self):
        for sid in WEAK:
            with self.subTest(source=sid):
                (events, _) = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all((e.relevance_tier == 'weak' for e in events)), [(e.title, e.relevance_tier) for e in events])

    def test_update_outlook_cannot_invent_content_releases(self):
        (events, _) = self.cluster_sources('9cd3071e50aa8539eb32989e')
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].title.startswith('Apple service'))
        self.assertEqual(events[0].relevance_tier, 'weak')

    def test_interoperability_versions_and_separate_apps_stay_distinct(self):
        articles = [article_for(self.m, '小米澎湃 OS ' + v + ' 推出苹果设备互联功能', '小米官方宣布澎湃 OS ' + v + ' 上线苹果设备互联，支持照片传输和双向消息同步。') for v in ['5', '6']]
        articles.append(article_for(self.m, '小米互联应用上线 Apple Watch', '小米发布独立的 Apple Watch 应用，支持健康数据同步。'))
        self.assertEqual(len(self.m.cluster_articles(articles)), 3)

    def test_compatibility_does_not_imply_apple_codevelopment(self):
        a = article_for(self.m, 'LG 智能恒温器新增 Apple Home 兼容', 'LG 宣布其独立开发的温控器通过 Matter 接入 Apple Home，支持温度设置。')
        events = self.m.cluster_articles([a])
        self.assertEqual(events[0].relevance_tier, 'weak')

    def test_camera_shipments_are_not_design_disclosures(self):
        articles = [article_for(self.m, 'Apple and LG home cameras revealed in leaked images', 'Apple and LG co-developed four cameras. Ringo shared images of a doorbell, floodlight, indoor and outdoor cameras.'), article_for(self.m, 'Apple and LG home cameras begin shipping', 'Apple and LG announced their co-developed cameras are shipping today to customers in Canada.')]
        self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_negative_and_disclosure_qualifiers_separate_events(self):
        cases = [[('小米澎湃 OS 5 推出苹果设备互联功能', '小米官方宣布澎湃 OS 5 上线苹果设备互联，支持照片传输。'), ('小米澎湃 OS 5 尚未推出苹果设备互联功能', '小米官方澄清，澎湃 OS 5 并未上线苹果设备互联，相关功能仍在测试。')], [('Apple second-party home products found in code', 'The iOS 27 code includes a SecondPartyProducts table naming a smart lock.'), ('Apple second-party home products discovered in new code', 'The iOS 28 code includes a SecondPartyProducts table naming a new thermostat.')], [('macOS 26.1 RC now available', 'Apple released the first release candidate of macOS 26.1 today.'), ('macOS 26.1 second release candidate now available', 'Apple released the second release candidate of macOS 26.1 today.')], [('Apple and LG home cameras revealed in first leaked images', 'Apple and LG co-developed home cameras. Alice shared design images today showing the indoor camera.'), ('New Apple and LG home camera design images reveal a revised enclosure', 'Apple and LG co-developed home cameras. Bob published a separate second batch of design images today showing a revised outdoor camera.')], [('Apple and LG home cameras revealed in leaked images', 'Apple and LG co-developed first-generation home cameras. Images show the original indoor camera design.'), ('Apple and LG second-generation home cameras revealed in leaked images', 'Apple and LG co-developed second-generation home cameras. New images show a different design for the successor.')], [('Apple and LG home cameras revealed in leaked images', 'Apple and LG co-developed home cameras. Images show four cameras.'), ('Apple and LG home cameras: leaked images were fake', 'Apple and LG did not co-develop the cameras shown in images. The leak has been withdrawn.')]]
        for rows in cases:
            for order in (rows, rows[::-1]):
                with self.subTest(rows=order):
                    events = self.m.cluster_articles([article_for(self.m, h, l) for (h, l) in order])
                    self.assertEqual(len(events), 2)

    def test_current_release_is_not_demoted_by_retrospective_context(self):
        for lead in ['Apple released iOS 27.1 beta 2 today, adding encrypted backups.', 'Apple today released iOS 27.1 beta 2 with encrypted backups.']:
            a = article_for(self.m, 'iOS 27.1 beta 2 released with new features', lead + ' Here is a recap of rumors that preceded this release.')
            events = self.m.cluster_articles([a])
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual(events[0].category, 'software_systems')

    def test_same_explicit_disclosure_batch_spans_device_families(self):
        lead = 'Apple and LG co-developed home devices. Alice published a single batch of FCC design images today showing the camera, thermostat and door lock.'
        rows = [article_for(self.m, title, lead) for title in ['First look at Apple and LG home cameras', 'First look at Apple and LG home thermostat and smart lock']]
        self.assertEqual(len(self.m.cluster_articles(rows)), 1)

    def test_rc_stage_in_lead_matches_explicit_headline(self):
        lead = 'Apple released macOS 26.1 RC 2 today, build 25B500.'
        rows = [article_for(self.m, title, lead) for title in ['macOS 26.1 RC now available', 'macOS 26.1 RC 2 released for testing']]
        self.assertEqual(len(self.m.cluster_articles(rows)), 1)

    def test_historical_bundle_is_not_current_rollout(self):
        cases = [
            [('小米澎湃 OS 5 推出苹果设备互联功能', '小米官方宣布澎湃 OS 5 上线苹果设备互联，支持照片传输。'), ('回顾小米澎湃 OS 5 推出的苹果设备互联功能', '小米去年宣布澎湃 OS 5 上线苹果设备互联。本文回顾旧功能，没有新的发布。')],
            [('Apple and LG home cameras revealed in leaked images', 'Apple and LG co-developed home cameras. New images were published today.'), ('Apple and LG home cameras: a look back at the leaked images', 'Apple and LG co-developed home cameras last year. This article reviews those old images; no new designs have been disclosed.')]
        ]
        for rows in cases:
            events = self.m.cluster_articles([article_for(self.m, h, lead) for h, lead in rows])
            self.assertEqual(len(events), 2)
            self.assertEqual(sorted(e.relevance_tier for e in events), ['ecosystem', 'weak'] if rows[0][0].startswith('小米') else ['strong', 'weak'])

    def test_unreleased_driver_cannot_join_released_enablement(self):
        rows = [article_for(self.m, 'Hackintosh and Intel Mac graphics driver released', 'The Nvidia 5060 card now has a released Metal graphics driver. Apps run on Intel PCI-E Macs.'), article_for(self.m, 'Hackintosh and Intel Mac graphics driver still delayed', 'The Nvidia 5060 card driver is not yet released. Metal apps cannot run on Intel PCI-E Macs with it yet.')]
        events = self.m.cluster_articles(rows)
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(e.relevance_tier for e in events), ['ecosystem', 'weak'])

    def test_disclosure_batch_ownership_does_not_depend_on_complete_inventory(self):
        same = [article_for(self.m, 'First look at Apple and LG home cameras', 'Apple and LG co-developed home devices. Alice published a single batch of FCC design images today showing the camera, thermostat and door lock.'), article_for(self.m, 'First look at Apple and LG home thermostat', 'Apple and LG co-developed home devices. Alice published the same batch of FCC design images today. The thermostat has a round screen.')]
        different = [article_for(self.m, 'Apple and LG home cameras revealed in first leaked images', 'Apple and LG co-developed home cameras. Alice shared design images today showing the indoor camera.'), article_for(self.m, 'More Apple and LG home camera images surface', 'Apple and LG co-developed home cameras. Bob published a separate batch of design images today showing the outdoor camera.')]
        for rows, count in [(same, 1), (different, 2)]:
            for order in [rows, rows[::-1]]:
                self.assertEqual(len(self.m.cluster_articles(order)), count)

    def test_program_name_cannot_cross_title_and_body_boundaries(self):
        h = "Ada Smith launches Apple x River Creative Labs"
        for lead in [
            "Ada Smith, a guest, attended the newly launched Apple x River Creative Labs.",
            "Ada Smith , a guest, attended the newly launched Apple x River Creative Labs.",
        ]:
            with self.subTest(lead=lead):
                a = article_for(self.m, h, lead)
                b = article_for(self.m, 'Apple announces a new education program',
                    'Apple announced a new education program. Apple x River Creative Labs will offer creative workshops to students.')
                self.assertEqual(len(self.m.cluster_articles([a, b])), 1)

    def test_software_port_demo_does_not_own_a_system_release(self):
        for title, lead in [
            ('Developer demonstrates iOS 9 on Orion handheld', 'An independent developer demonstrated a retro hardware porting project running iOS 9 on an Orion handheld.'),
            ('开发者展示旧掌机运行 macOS 系统', '开发者展示了复古硬件移植项目的成果，将 macOS 移植到旧掌机。'),
        ]:
            with self.subTest(title=title):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual(event.relevance_tier, 'weak')
        official = article_for(self.m, 'Apple releases new open-source XNU kernel for macOS 28',
            'Apple released the new XNU kernel today for macOS 28. Developers can use it for their porting projects and demonstrations.')
        self.assertEqual(self.m.cluster_articles([official])[0].relevance_tier, 'strong')

    def test_port_background_cannot_demote_release_or_apple_hardware(self):
        cases = [
            ('macOS 28 XNU kernel source released', "Apple released new XNU source code for macOS 28 today. An independent developer demonstrated a retro porting project using last year's source code."),
            ('New macOS 28 patcher adds support for older hardware', 'An independent developer released a new porting project and demonstrated macOS 28 support on older Mac Pro computers. The new patcher adds support for these Apple computers.'),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertIn(event.relevance_tier, {'strong', 'ecosystem'})

    def test_mixed_report_keeps_unassigned_current_assertions(self):
        events, _ = self.cluster_sources('d60c517615be353c5314ed02')
        review = '\n'.join(f.text for e in events for f in e.fact_plan.unprocessed)
        for fact in ['macOS 27.2', 'Dock', '图标会稍稍放大', '每周', 'Molly Anderson', 'Steve Lemay', 'Kevan Parekh', 'Sabih Khan', '管理层级']:
            with self.subTest(fact=fact):
                self.assertIn(fact, review)

    def test_local_report_review_does_not_inherit_foreign_or_historical_owner(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        from apple_news_core.event_identity import source_local_report_passages
        lines = [
            'Apple CEO Dana Lee oversees the design team today.',
            'Microsoft recruited a new design team.',
            'The team is responsible for product design.',
            'Last year Apple recruited its design team.',
            'In the latest macOS 29 beta, pressing a toolbar button displays a compact panel.',
            'If a future macOS 29 beta enlarged icons when clicked, it could suggest new hardware.',
        ]
        evidence = ArticleEvidence(article_id='mixed', source='Test', url='https://example.com/mixed', title='Company news', raw_lead=lines[0], content_form='news', units=tuple(EvidenceUnit(str(i), 'p', line, 'html', i) for i, line in enumerate(lines)))
        ids = {key for key, *_ in source_local_report_passages(evidence)}
        self.assertEqual(ids, {'0', '4'})

    def test_discovery_fallback_keeps_program_identity(self):
        articles = []
        for sid in GROUPS['creative_labs']:
            original = self.rows[sid]
            evidence = original['evidence']
            try:
                if evidence['confidence'] == 'discovery':
                    candidate = self.m.Candidate(evidence['source'], evidence['url'],
                        evidence['discovery_title'], evidence['discovery_lead'], evidence['published_raw'])
                    extracted = self.m.fallback_article_from_discovery(candidate, self.sources[evidence['source']], {})
                    self.rows[sid] = dict(original, recorded_extraction=extracted[:3])
                articles.extend(self.source_articles(sid))
            finally:
                self.rows[sid] = original
        self.assertEqual(len(self.m.cluster_articles(articles)), 1)

    def test_program_visit_is_not_its_background_launch(self):
        launch = article_for(self.m, 'Apple announces a new education program',
            'Apple announced a new education program. Apple x River Creative Labs will offer creative workshops.')
        for verb, past in [('visits', 'visited'), ('attends', 'attended')]:
            visit = article_for(self.m, 'Tim Cook ' + verb + ' Apple x River Creative Labs',
                'Tim Cook ' + past + ' a student session at the Apple x River Creative Labs program today, which launched earlier this week.')
            for order in ([launch, visit], [visit, launch]):
                with self.subTest(verb=verb, reverse=order[0] is visit):
                    self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_prior_program_cannot_name_current_education_launch(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        h = 'Apple launches a new education program'
        lead = 'Apple announced a new education program offering coding scholarships for students.'
        old = 'Previously, the Apple x River Creative Labs program taught music production. The new coding program has a separate curriculum and funding.'
        a = article_for(self.m, h, lead)
        a.evidence = ArticleEvidence(article_id='new-coding', source=a.source, url=a.url, title=h, raw_lead=lead, content_form='news', units=(EvidenceUnit('u1', 'p', old, 'html', 0),))
        b = article_for(self.m, 'Apple x River Creative Labs program launches', 'Apple announced a new education program. Apple x River Creative Labs will offer music workshops.')
        self.assertEqual(len(self.m.cluster_articles([a, b])), 2)
