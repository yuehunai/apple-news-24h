"""Captured source actions and nearby ownership/stage controls."""
from datetime import datetime, timezone
from dataclasses import replace
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20260927_source_actions.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 9, 27, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_personal_week_review_cannot_project_old_launch(self):
        articles = self.source_articles('9e320893f894857dfb4d3601')
        self.assertEqual(len(articles), 1)
        self.assertIsNone(articles[0].bound_claim)
        events = self.m.cluster_articles(articles)
        self.assertEqual(events[0].relevance_tier, 'weak')
        self.assertIn('one week later', events[0].title)

    def test_current_source_actions_are_not_demoted_by_background(self):
        for aid, tier, category in [
            ('b622d9698038a685459d2a45', 'ecosystem', 'software_systems'),
            ('7df296003a68264461be68c5', 'strong', 'hardware_products'),
            ('8aad52c76a42a6f14056ca74', 'strong', 'hardware_products'),
        ]:
            with self.subTest(aid=aid):
                events, _ = self.cluster_sources(aid)
                self.assertEqual(len(events), 1)
                self.assertEqual((events[0].relevance_tier, events[0].category), (tier, category))

    def test_nvme_patch_scope_and_stage_do_not_borrow_downstream_release(self):
        original = self.source_articles('b622d9698038a685459d2a45')[0]
        translated = article_for(self.m, 'Linux NVMe patches submitted for Apple M3 Macs',
            'A developer submitted NVMe driver patches to the Linux kernel mailing list for Apple M3 chips. The patches are under review.', source='MacRumors')
        distinct = [article_for(self.m, title, lead, source='9to5Mac') for title, lead in [
            ('Asahi Linux now supports Apple M3', 'Asahi Linux has released support for Apple M3 chips.'),
            ('Linux GPU patches submitted for Apple M3 Macs', 'A developer submitted GPU driver patches to the Linux kernel mailing list for Apple M3 chips.'),
            ('Linux NVMe patches submitted for Apple M4 Macs', 'A developer submitted NVMe driver patches to the Linux kernel mailing list for Apple M4 chips.'),
            ('Linux NVMe driver merged for Apple M3 Macs', 'The Linux kernel has merged NVMe driver support for Apple M3 chips.'),
        ]]
        for ordered in [[original, translated, *distinct], [*reversed(distinct), translated, original]]:
            events = self.m.cluster_articles(ordered)
            self.assertEqual(len(events), 5, [e.title for e in events])
            same = next(e for e in events if original in e.articles)
            self.assertIn(translated, same.articles)
            self.assertEqual((same.relevance_tier, same.category), ('ecosystem', 'software_systems'))

    def test_drawing_publication_requires_current_apple_actor(self):
        originals = self.source_articles('8aad52c76a42a6f14056ca74')
        positive = article_for(self.m, 'Apple publishes product design drawings',
            'Apple has updated its official public repository with new dimensional drawings for iPhone and AirPods.', source='MacRumors')
        controls = [article_for(self.m, title, lead, source='9to5Mac') for title, lead in [
            ('Apple product design drawings: a historical look', 'Apple previously published dimensional drawings for iPhone. Today a blogger revisits the archive.'),
            ('Apple product design drawings remain unpublished', 'Apple has not published the dimensional drawings. An accessory maker uploaded unofficial mockups.'),
            ('Designer publishes Apple product design drawings', 'A designer publishes unofficial dimensional drawings for iPhone. Apple has not updated its repository.'),
            ('Apple product design drawings discussed', 'Apple updated macOS today. A designer published unofficial dimensional drawings for iPhone.'),
        ]]
        events = self.m.cluster_articles([*originals, positive, *controls])
        joined = next(e for e in events if originals[0] in e.articles)
        self.assertIn(positive, joined.articles)
        for article in controls:
            self.assertNotIn(article, joined.articles)
            p = self.m.article_reconciliation_profile(article)
            self.assertFalse(any('document-catalog-report' in key for key in p.event_keys))

    def test_local_ai_numbers_do_not_authorize_third_party_or_old_claims(self):
        for title, lead in [
            ('Mac local AI model capacity compared with PCs', 'A reviewer estimates local AI model capacity on Mac. Apple has not published these parameter limits.'),
            ('Mac local AI model capacity revisited', 'Last year Apple published local AI parameter limits for Mac. Today a blogger compares them with PCs.'),
            ('Local AI vendor publishes Mac model capacity', 'An app vendor published local AI model parameter limits for Mac. Apple only supplies the hardware.'),
            ('Mac local AI model capacity explained', 'Apple updated macOS today. A reviewer estimates local AI model parameter limits for Mac.'),
            ('苹果公布Mac本地AI能力？', '苹果在今年的开发者大会上没有公布本地AI参数数据，只讨论了设计理念。'),
        ]:
            p = self.m.article_reconciliation_profile(article_for(self.m, title, lead, source='9to5Mac'))
            self.assertFalse(any('official-capability-report' in key for key in p.event_keys))

    def test_official_capacity_report_joins_across_languages(self):
        original = self.source_articles('7df296003a68264461be68c5')[0]
        translated = article_for(self.m, 'Apple shares local AI model capacity for Macs',
            'At its enterprise conference, Apple published local AI model parameter limits for iPhone, iPad and Mac.', source='MacRumors')
        events = self.m.cluster_articles([translated, original])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')

    def test_editorial_review_and_current_followup_have_different_authority(self):
        review = article_for(self.m, 'iPhone 19 two months later',
            'When Apple unveiled iPhone 19, its camera stood out. I have found the battery more useful after buying it.', source='MacRumors')
        followup = article_for(self.m, 'iPhone 19 two months later: Apple announces repair program',
            'Apple today announced a repair program for iPhone 19 after reports of charging failures.', source='9to5Mac')
        events = self.m.cluster_articles([review, followup])
        self.assertEqual(len(events), 2)
        self.assertEqual(next(e for e in events if review in e.articles).relevance_tier, 'weak')
        self.assertEqual(next(e for e in events if followup in e.articles).relevance_tier, 'strong')

    def test_official_capacity_keeps_hardware_scope(self):
        articles = [article_for(self.m, f'Apple shares local AI capacity of {device}',
            f'Apple published local AI model parameter limits for {device}.', source='MacRumors')
            for device in ['M5 Mac mini', 'M6 Mac mini', 'M5 Mac Studio']]
        for ordered in [articles, list(reversed(articles))]:
            self.assertEqual(len(self.m.cluster_articles(ordered)), 3)

    def test_kernel_patch_negation_and_history_do_not_supply_milestone(self):
        for lead in [
            'The developer has not submitted NVMe driver patches to the Linux kernel for Apple M5 chips.',
            'Last year a developer submitted NVMe driver patches to the Linux kernel for Apple M5 chips.',
            'A developer plans to submit NVMe driver patches to the Linux kernel for Apple M5 chips.',
        ]:
            article = article_for(self.m, 'Linux NVMe patches for Apple M5 Macs discussed', lead, source='MacRumors')
            p = self.m.article_reconciliation_profile(article)
            self.assertFalse(any('nvme-patch-submission' in key for key in p.event_keys))

    def test_current_feature_report_and_launch_remain_eligible(self):
        events, _ = self.cluster_sources('bc3ecb1299beab2673c0aebb')
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))
        article = article_for(self.m, 'Apple introduces Apple Watch Series 13',
            'Apple today introduced Apple Watch Series 13 with a new sensor.', source='MacRumors')
        self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'strong')

    def test_remaining_editorial_and_comparison_sources_stay_weak(self):
        for aid in ['3ecbca15cbf1567c6ddd8fd3', '4ac33692f339e227f3e38640',
                    'b7aa781499fa069f5ab79a5d', 'ba2db18dc8ca71b6d03c7f90',
                    '663ba47537bef7d1c11674ae', '124c3b2a94722ebfb2ff328d']:
            with self.subTest(aid=aid):
                events, _ = self.cluster_sources(aid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_legal_verdict_and_response_keep_distinct_source_groups(self):
        verdict = {'c34fc43b518eaaae776e3b93','7bd358322e25ad7b741e516e',
                   'ac2662763efe525ef9d1fb7f','456ed7e8ee4a8aeb60dfba52'}
        response = '043b683155b458bffb7d2607'
        for ids in [sorted(verdict) + [response], [response] + sorted(verdict, reverse=True)]:
            events, _ = self.cluster_sources(*ids)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                             {frozenset(verdict), frozenset({response})})
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_patent_category_does_not_depend_on_expiring_peer(self):
        ids = ['c34fc43b518eaaae776e3b93', '7bd358322e25ad7b741e516e',
               '456ed7e8ee4a8aeb60dfba52']
        for subset in [[aid] for aid in ids] + [ids, list(reversed(ids))]:
            with self.subTest(subset=subset):
                events, _ = self.cluster_sources(*subset)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].category, 'hardware_products')
        software = article_for(self.m, 'Apple faces App Store billing patent case',
            'The court heard a patent dispute over App Store payment software. iPhones also contain a Taptic Engine for haptic feedback.', source='MacRumors')
        self.assertEqual(self.m.cluster_articles([software])[0].category, 'software_systems')

    def test_legal_source_responses_and_verdict_details_reach_fact_review(self):
        for aid, fragments in [
            ('c34fc43b518eaaae776e3b93', [
                'two claims in one patent, and one in the other',
                'Apple failed on all three parts',
                "Taction isn't entitled to any damages",
                "Taction's own testing of Apple's products confirmed during trial",
                'will appeal']),
            ('7bd358322e25ad7b741e516e', ['two claims in one patent',
                'two Kannon gaming headsets', 'intends to appeal']),
        ]:
            events, _ = self.cluster_sources(aid)
            plan = events[0].fact_plan
            visible = (*plan.facts, *plan.required, *plan.unprocessed)
            for fragment in fragments:
                with self.subTest(aid=aid, fragment=fragment):
                    matching = [f for f in visible if fragment in f.text]
                    self.assertTrue(matching, fragment)
                    self.assertTrue(all(o[2] == aid and o[3]
                        for f in matching for o in f.origins))

    def test_legal_quote_keeps_attribution_without_creating_a_new_event(self):
        article = self.source_articles('c34fc43b518eaaae776e3b93')[0]
        unit = article.evidence.units[0]
        introduction = "Last year, Apple's statement on a separate case said:"
        quotation = 'We disagree with that verdict and intend to appeal.'
        evidence = replace(article.evidence, units=(
            replace(unit, unit_id='intro', text=introduction),
            replace(unit, unit_id='quote', kind='blockquote', text=quotation)))
        article.evidence = evidence
        events = self.m.cluster_articles([article])
        self.assertEqual(len(events), 1)
        reviewed = events[0].fact_plan.unprocessed
        self.assertTrue(any(introduction in f.text and quotation in f.text for f in reviewed))
        self.assertFalse(any(quotation in f.text for f in events[0].fact_plan.required))
        # A quote without a locally attributed legal statement is not promoted
        # merely because it appears below an Apple lawsuit headline.
        article.evidence = replace(evidence, units=(
            replace(evidence.units[0], text='An unrelated product review follows:'),
            evidence.units[1]))
        view = self.m.prepare_source_fact_view(article)
        self.assertFalse(any(quotation in f.text for f in view.unprocessed))

    def test_short_parallel_data_rows_are_not_dropped_from_a_source_list(self):
        article = self.source_articles('4d1be6b54a4f5f40b9f863cc')[0]
        for short_row in ['在 Android 上称为 FileObserver（2008 年）',
                          'On Android: FileObserver (2008)']:
            units = list(article.evidence.units)
            units[5] = replace(units[5], text=short_row)
            article.evidence = replace(article.evidence, units=tuple(units))
            plan = self.m.cluster_articles([article])[0].fact_plan
            visible = (*plan.facts, *plan.required, *plan.unprocessed)
            with self.subTest(short_row=short_row):
                self.assertTrue(any(short_row in f.text for f in visible))
                for label in ['inotify', 'ReadDirectoryChangesW', 'FSEvents']:
                    self.assertTrue(any(label in f.text for f in visible))


if __name__ == '__main__': unittest.main()
