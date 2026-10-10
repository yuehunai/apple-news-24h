"""Captured September 26 source actions, including nearby non-news controls."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20260926_source_actions.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 9, 26, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def assert_group(self, ids, tier='strong', category='hardware_products'):
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual((events[0].relevance_tier, events[0].category), (tier, category))

    def test_testflight_is_first_party_versioned_update(self):
        self.assert_group(['c6bf0270ae417f5b8937a13b','3244fa6de1d1e1cbf846fa34'],category='software_systems')

    def test_document_catalog_is_separate_from_firmware(self):
        docs=['9079c5e3c1ba4f8bafdecb7d','8d1feb340c9fc60ce247132c']
        self.assert_group(docs)
        self.assert_group(['0f38d87d2dfc0b0516d7b9a0'],category='software_systems')
        events,_=self.cluster_sources(*docs,'0f38d87d2dfc0b0516d7b9a0')
        self.assertEqual({frozenset(self.source_ids(e)) for e in events},
            {frozenset(docs),frozenset(['0f38d87d2dfc0b0516d7b9a0'])})

    def test_release_notes_are_current_document_action(self):
        self.assert_group(['a4143934fb458ce8697f95c5','a1d04fc303ee4cd45bd4050f'],category='software_systems')

    def test_release_note_plain_text_bullet_reaches_facts_or_review(self):
        events, _ = self.cluster_sources('a4143934fb458ce8697f95c5')
        plan = events[0].fact_plan
        facts = (*plan.facts, *plan.required, *plan.unprocessed)
        match = [f for f in facts if 'Hi-Res Lossless' in f.text]
        self.assertTrue(match, 'Source bullet must not disappear before final review')
        self.assertTrue(any(origin[3] == 'c81bad07c00455e42a5ac942' for f in match for origin in f.origins))

    def test_hardware_images_agree_across_source_angles(self):
        for ids in [
            ['1c7ac6ec3972e2fe86a2fd9a','b38d5f54af8ac273bdd6de3a','f5883b5f1ba1c4ec6f3342f0'],
            ['e0db2d2602d17ef40a5e4efd','8c5ef776ea9af5894e338e7d','7685b6df50fde3535924a7e5','21220442fbfc676a9b390c59','4119f911da8c837c4cea62a4'],
            ['38611c40ea1865e1f0c83b6f','d1e52ed7b6da6ff9ce9f272c','09c1138e6a55395ec530d172','835e7a2007da89c4ee49927c'],
            ['86ebc224338af8a3d2ba09c5','45865dda3c77931507651d2e','139ee6c15b1807b422086750','20d3cb3f4f86a54a7d37c4ae','60257f33f6d3bb98f51785d0'],
        ]:
            with self.subTest(ids=ids): self.assert_group(ids)

    def test_screensaver_code_is_software_not_device_leak(self):
        software='18339ee6713cdbf16a726a8c';hardware='38611c40ea1865e1f0c83b6f'
        self.assert_group([software],category='software_systems')
        events,_=self.cluster_sources(software,hardware)
        self.assertEqual(len(events),2)

    def test_multi_device_leaks_project_each_owned_action(self):
        ids=['f97aa755f9fcf650ad8c7af9','2fc4c0b8c22d8a2242d18398','8edd317df593e5b51eb014d7']
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),3,[(e.title,self.source_ids(e)) for e in events])
        for e in events:
            self.assertEqual(e.relevance_tier,'strong')
            self.assertEqual(e.category,'hardware_products')
        # The two-device source must not become an iPad source through its peers.
        self.assertEqual(sorted(len(self.source_ids(e)) for e in events),[2,3,3])
        source_units={u['unit_id']:u['text'] for row in self.rows.values() for u in row['evidence']['units']}
        for event in events:
            for fact in (*event.fact_plan.facts,*event.fact_plan.required,*event.fact_plan.unprocessed):
                for origin in fact.origins:
                    if origin[3]: self.assertEqual(fact.text,source_units[origin[3]][origin[4]:origin[5]])

    def test_cellular_issue_is_not_background_chip_report(self):
        self.assert_group(['57de1b6497bd32adb5867f8f','3ce0dddd62682e18777787ae'])

    def test_current_hardware_variants_and_system_capability(self):
        self.assert_group(['b0de383bc3f9de1463e8183a'])
        self.assert_group(['cb90f5033327996e2c3be827'],category='software_systems')
        self.assert_group(['784530fbf3a3ce57c1bc0e83'],category='software_systems')

    def test_cross_platform_watch_connection_is_ecosystem(self):
        self.assert_group(['1dc14b583dacf324827a50bb'],tier='ecosystem',category='software_systems')

    def test_same_current_service_actions_merge_across_angles(self):
        self.assert_group(['483357ea840a6c26f4207d9d','bc8c60bad53d86bbcf781926'],category='software_systems')
        self.assert_group(['79cb850e5bbbae061de38be8','b59766a3bb0e0d3dd6f99a29'],category='software_systems')

    def test_market_measure_year_belongs_to_its_sentence(self):
        self.assert_group(['7e835e38e9e90a9d4787968d','17b0117ebb236023cee98650'])
        for aid in ['7e835e38e9e90a9d4787968d','17b0117ebb236023cee98650']:
            profile=self.m.article_reconciliation_profile(self.source_articles(aid)[0])
            keys=[key for key in profile.event_keys if 'apple-share-current:10' in key]
            self.assertTrue(keys)
            self.assertTrue(all(':2026:' in key for key in keys),keys)

    def test_device_generation_and_release_stage_remain_separate(self):
        cases=[('HomePod mini 2 images leaked', "Apple's code reveals images of the unannounced HomePod mini 2 in new colors."),
               ('HomePod mini 3 images leaked', "Apple's code reveals images of the unannounced HomePod mini 3 in new colors."),
               ('Apple releases HomePod mini 2', 'Apple today released HomePod mini 2. Its images were previously leaked from code.')]
        articles=[article_for(self.m,title,lead,source='MacRumors') for title,lead in cases]
        for ordered in [articles,list(reversed(articles))]:
            self.assertEqual(len(self.m.cluster_articles(ordered)),3)

    def test_app_background_os_version_cannot_supply_app_build(self):
        article=article_for(self.m,'TestFlight landscape support is still unavailable',
            'Apple has not updated TestFlight. macOS version 29.2.0 supports resized mirroring windows.',source='9to5Mac')
        profile=self.m.article_reconciliation_profile(article)
        self.assertFalse(any('testflight:29.2.0' in key for key in profile.event_keys))

    def test_unofficial_notes_do_not_become_apple_publication(self):
        articles=[article_for(self.m,'Apple shares tvOS 28 release notes',
            'Apple today published release notes for tvOS 28.',source='MacRumors'),
            article_for(self.m,'Developer shares tvOS 28 release notes',
            'A developer published unofficial release notes for tvOS 28. Apple has not shared its notes.',source='9to5Mac')]
        events=self.m.cluster_articles(articles)
        self.assertEqual(len(events),2)
        self.assertEqual(next(e for e in events if articles[1] in e.articles).relevance_tier,'weak')

    def test_distinct_screensaver_capabilities_do_not_merge(self):
        articles=[article_for(self.m,'tvOS 28 code reveals screensaver sound effects',
            'A developer found hidden audio controls in tvOS 28 code for Apple TV screensavers.',source='MacRumors'),
            article_for(self.m,'tvOS 28 code reveals new screensaver animation',
            'A developer found a hidden new aerial animation in tvOS 28 code.',source='9to5Mac')]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_planned_app_update_does_not_join_released_build(self):
        articles=[article_for(self.m,'Apple releases TestFlight version 5.1.0',
            'Apple has updated TestFlight version 5.1.0 with landscape support.',source='MacRumors'),
            article_for(self.m,'Apple plans to update TestFlight version 5.1.0',
            'Apple plans to update TestFlight version 5.1.0 with landscape support.',source='9to5Mac')]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_current_patent_verdict_targets_apple_not_third_party_background(self):
        self.assert_group(['ac2662763efe525ef9d1fb7f'])

    def test_patent_verdict_keeps_party_and_current_action_boundaries(self):
        cases = [
            ('Jury orders Apple to pay patent damages', "A federal jury today found Apple infringed Solana's patents and ordered damages."),
            ('Jury orders Apple to pay patent damages in Vega case', "A federal jury today found Apple infringed Vega's patents and ordered damages."),
            ('Taction patent verdict against Apple is recalled', 'An interview recalls how a jury previously found Apple infringed Taction patents. There is no new ruling.'),
            ('No patent verdict against Apple', 'The jury has not found Apple infringed Taction patents and has not ordered damages.'),
        ]
        articles = [article_for(self.m, title, lead, source='MacRumors') for title, lead in cases]
        for ordered in [articles, list(reversed(articles))]:
            events = self.m.cluster_articles(ordered)
            self.assertEqual(len(events), 4)
            for article in articles[:2]:
                self.assertEqual(next(e for e in events if article in e.articles).relevance_tier, 'strong')
            for article in articles[2:]:
                profile = self.m.article_reconciliation_profile(article)
                self.assertFalse(any('jury-damages-verdict' in key for key in profile.event_keys))

    def test_third_party_ota_and_editorial_items_stay_weak(self):
        for aid in ['eb265c2df1c8291a83c9adc7','366e199729e66afaaa00b511',
                    'c41f3e0605d13e78682544df','92d0620743a6fe0b91f8b64d',
                    'df03be6a96822853fa378681','6e395b0b9be430474fdce80c',
                    'af480081784b8e94b6d93d1d','6c73ea13fd27b4b77fef2362']:
            with self.subTest(aid=aid):
                events,_=self.cluster_sources(aid)
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier=='weak' for e in events))


if __name__=='__main__': unittest.main()
