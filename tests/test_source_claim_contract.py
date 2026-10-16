"""Source relationships survive preparation, qualification and pairing."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_relevance_rules import article_for, load_module


class SourceClaimContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_captured_distinct_cases_do_not_share_a_trade_secret_topic_identity(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference
        rows = json.loads((Path(__file__).parent / 'fixtures/20261016_legal_case_sources.json').read_text())
        articles = []
        for row in rows.values():
            data = dict(row)
            for field, record in (('units', EvidenceUnit), ('publication_candidates', PublicationEvidence),
                                  ('embedded_references', EmbeddedReference)):
                data[field] = tuple(record(**value) for value in data[field])
            evidence = ArticleEvidence(**data)
            articles.append(self.m.Article(evidence.source, evidence.url, evidence.title, evidence.raw_lead,
                [u.text for u in evidence.units if u.kind in {'p', 'text', 'summary'}], '',
                datetime.fromisoformat(evidence.published_utc), evidence.published_raw,
                evidence.published_source, evidence.confidence, set(), evidence=evidence))
        for order in (articles, articles[::-1]):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 2)
            self.assertEqual({a.evidence.article_id for event in events for a in event.articles}, set(rows))
            self.assertTrue(all(event.relevance_tier == 'strong' for event in events))

    def test_legal_topic_alone_cannot_identify_a_case(self):
        from apple_news_core.event_identity import build_event_identity
        from apple_news_core.event_matcher import identity_pair_decision
        left = build_event_identity('Apple files a response in the OpenAI trade secret lawsuit',
                                    'Apple disputes the allegations in the OpenAI case.')
        right = build_event_identity('Trade secret lawsuit against Apple is appealed',
                                     'Northstar is appealing its separate lawsuit against Apple.')
        self.assertEqual(identity_pair_decision(left, right), 'unknown')
        same = build_event_identity('OpenAI trade secret case receives Apple court response',
                                    'Apple filed a response to the allegations in the OpenAI lawsuit.')
        self.assertEqual(identity_pair_decision(left, same), 'match')

    def test_app_chart_publishers_keep_distinct_source_owned_results(self):
        rows = (
            ('星河应用占据App Store免费榜前六名',
             'App Store免费榜前六名里，有五款应用都来自星河科技。'),
            ('远山应用占据App Store付费榜前三名',
             'App Store付费榜前三名里，有两款应用都来自远山科技。'),
        )
        for order in (rows, rows[::-1]):
            with self.subTest(order=[title for title, _ in order]):
                articles = [article_for(self.m, title, lead) for title, lead in order]
                events = self.m.cluster_articles(articles)
                self.assertEqual(len(events), 2)
                self.assertTrue(all(event.relevance_tier == 'weak' for event in events))
                self.assertEqual(sorted(len(event.articles) for event in events), [1, 1])

    def test_same_publisher_chart_report_matches_across_languages(self):
        rows = (
            ('Northstar应用占据App Store免费榜前六名',
             'App Store免费榜前六名里，有五款应用都来自Northstar。'),
            ('Northstar apps dominate the App Store free chart',
             'Five of the top six apps in the App Store free chart are from Northstar.'),
        )
        for order in (rows, rows[::-1]):
            with self.subTest(order=[title for title, _ in order]):
                events = self.m.cluster_articles([article_for(self.m, *row) for row in order])
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].relevance_tier, 'weak')
                self.assertEqual(len(events[0].articles), 2)

    def test_chart_binding_keeps_owner_and_exact_source_evidence(self):
        article = article_for(self.m, '星河应用占据App Store免费榜前六名',
            'App Store免费榜前六名里，有五款应用都来自星河科技。')
        profile = self.m.article_reconciliation_profile(article)
        claim = profile.bound_claim
        self.assertIsNotNone(claim)
        self.assertEqual(claim.subject, '星河科技')
        self.assertEqual(profile.eligibility.tier, 'weak')
        units = {unit.unit_id: unit.text for unit in article.evidence.units}
        names = [units[key][start:end] for _, kind, _, key, start, end in claim.qualifiers
                 if kind == 'subject-name']
        self.assertEqual(names, ['星河科技'])

    def test_chart_background_does_not_supply_current_ownership(self):
        article = article_for(self.m, '星河应用占据App Store免费榜前六名',
            '去年，App Store免费榜的应用都来自苹果。')
        profile = self.m.article_reconciliation_profile(article)
        self.assertEqual(profile.bound_claim.report_role, 'background')
        self.assertEqual(profile.eligibility.tier, 'weak')

    def test_denied_and_affirmed_chart_ownership_are_not_the_same_assertion(self):
        title = 'Northstar apps dominate the App Store free chart'
        articles = [article_for(self.m, title,
            f'The apps in the App Store free chart are {negative}from Northstar.')
            for negative in ('', 'not ')]
        profiles = [self.m.article_reconciliation_profile(article) for article in articles]
        self.assertEqual([profile.bound_claim.polarity for profile in profiles], ['affirmed', 'denied'])
        self.assertEqual(self.m.profile_pair_decision(*profiles), 'conflict')

    def test_explicit_chart_observation_dates_define_the_dataset_not_its_counts(self):
        rows = [('Northstar apps dominate the App Store free chart',
                 f'On October {day}, {count} apps in the App Store free chart were from Northstar.')
                for day, count in ((14, 'five'), (15, 'three'), (14, 'six'))]
        for order in (rows, rows[::-1]):
            events = self.m.cluster_articles([article_for(self.m, *row) for row in order])
            self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])

    def test_chart_date_belongs_to_its_predicate_not_the_neighboring_action(self):
        title = 'Northstar apps dominate the App Store free chart'
        original = 'On October 14, five apps in the App Store free chart were from Northstar.'
        neighbor = original[:-1] + ', while Rival launched a new app on October 15.'
        comma_neighbor = original[:-1] + ', Rival launched a new app on October 15.'
        different = original.replace('October 14', 'October 15')
        rows = [article_for(self.m, title, text, source=str(index))
                for index, text in enumerate((original, neighbor, different, comma_neighbor))]
        for order in (rows, rows[::-1]):
            groups = {frozenset(article.source for article in event.articles)
                      for event in self.m.cluster_articles(order)}
            self.assertEqual(groups, {frozenset({'0', '1', '3'}), frozenset({'2'})})

    def test_measurement_tool_follows_a_local_device_reference(self):
        from apple_news_core.event_identity import bind_device_measurement
        title = 'iPhone Duo 跑分曝光'
        current = 'iPhone Duo 即将开售。'
        reference = '在产品预购启动前，这款新机已经出现在 Geekbench 7 性能测试数据库中。'
        scores = '初步跑分显示，iPhone Duo 的单核得分为3986分，多核得分为11067分。'
        for tool_subject, expected in ((reference, 'geekbench-7'),
                (reference.replace('这款新机', '另一款手机'), ''),
                ('Last year, iPhone 18 Pro appeared on Geekbench 7.', '')):
            evidence = self.m.capture_article_evidence('cnBeta', 'https://example.com/measurement',
                '<article><p>' + current + tool_subject + scores + '</p></article>', title)
            self.assertEqual(bind_device_measurement(evidence).object, expected)
        comparison = ('<p>The Rival phone has the same display size as iPhone Duo.</p>'
                      '<p>This phone appeared on Geekbench 7.</p><p>' + scores + '</p>')
        evidence = self.m.capture_article_evidence('cnBeta', 'https://example.com/comparison',
            '<article>' + comparison + '</article>', title)
        self.assertEqual(bind_device_measurement(evidence).object, '')

    def test_measured_dataset_uses_one_source_binding_for_projection_and_facts(self):
        import test_20261015_source_boundaries as captured
        captured.SourceBoundariesTests.setUpClass()
        case = captured.SourceBoundariesTests()
        articles = case.source_articles('656b1869e0381f71919a0970')
        self.assertEqual(len(articles), 1)
        claim = articles[0].bound_claim
        self.assertIsNotNone(claim)
        self.assertEqual((claim.subject, claim.action, claim.object),
                         ('iphone-duo', 'cpu-benchmark-report', 'geekbench-7'))
        self.assertIn('eceed09ad70781b96d98250b', claim.unit_ids)
        event = self.m.cluster_articles(articles)[0]
        text = ' '.join(fact.text for fact in event.fact_plan.facts)
        for value in ('3,985', '11,271', '4.93GHz', '11.30GB', '61,531', '6,845', '12,109', '9,076'):
            self.assertIn(value, text)

    def test_measurement_observations_do_not_replace_explicit_dataset_dates(self):
        title = 'iPhone Duo benchmark report'
        rows = [article_for(self.m, title,
            f'On October {day}, iPhone Duo achieved a single-core score of {single} and a multi-core score of 12000 on Geekbench 8.', source=str(index))
            for index, (day, single) in enumerate(((14, 4100), (14, 4200), (15, 4100)))]
        for order in (rows, rows[::-1]):
            events = self.m.cluster_articles(order)
            self.assertEqual({frozenset(a.source for a in e.articles) for e in events},
                             {frozenset({'0', '1'}), frozenset({'2'})})

    def test_measurement_tool_and_time_are_local_to_the_observed_record(self):
        title = 'iPhone Duo benchmark report'
        lead = 'iPhone Duo achieved a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8.'
        current = article_for(self.m, title, lead, source='current')
        background = article_for(self.m, title, lead + ' Last year, iPhone 18 Pro was tested on Geekbench 7.', source='background')
        historical = article_for(self.m, title, 'Last year, ' + lead.replace('achieved', 'did not achieve'), source='historical')
        mixed = article_for(self.m, title, lead + ' Last year, iPhone Duo did not achieve a single-core score of 3000 and a multi-core score of 9000 on Geekbench 7.', source='mixed')
        self.assertEqual(self.m.article_reconciliation_profile(background).bound_claim.object, 'geekbench-8')
        self.assertEqual(self.m.article_reconciliation_profile(mixed).bound_claim.object, 'geekbench-8')
        self.assertEqual(self.m.article_reconciliation_profile(historical).eligibility.tier, 'weak')
        for order in ([current, background, mixed, historical], [historical, mixed, background, current]):
            events = self.m.cluster_articles(order)
            self.assertEqual({frozenset(a.source for a in e.articles) for e in events},
                             {frozenset({'current', 'background', 'mixed'}), frozenset({'historical'})})

    def test_a_comparison_device_cannot_own_the_following_measurement(self):
        title = 'iPhone Duo benchmark report'
        lead = 'iPhone Duo achieved a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8.'
        article = article_for(self.m, title, lead)
        peer = "The Rival phone's configuration matches the iPhone Duo CPU configuration."
        score = 'For the GPU benchmark, the score was 99000.'
        article.evidence = self.m.capture_article_evidence(article.source, article.url,
            '<article><p>' + lead + '</p><p>' + peer + '</p><p>' + score + '</p></article>', title)
        claim = self.m.article_reconciliation_profile(article).bound_claim
        units = {unit.unit_id: unit.text for unit in article.evidence.units}
        claimed = ' '.join(units[key][start:end] for key, start, end in claim.evidence_spans)
        self.assertNotIn('99000', claimed)
        self.assertNotIn(peer, claimed)

    def test_operating_feature_inventory_is_bound_once_with_its_conditions(self):
        import test_20261015_source_boundaries as captured
        captured.SourceBoundariesTests.setUpClass()
        case = captured.SourceBoundariesTests()
        articles = case.source_articles('52cc918c31b2ba1a9e60a8aa')
        self.assertEqual(len(articles), 1)
        claim = articles[0].bound_claim
        self.assertIsNotNone(claim)
        self.assertEqual((claim.subject, claim.action),
                         ('apple-home-hub', 'platform-capability-inventory-report'))
        event = self.m.cluster_articles(articles)[0]
        self.assertEqual((event.relevance_tier, event.category), ('strong', 'software_systems'))
        text = ' '.join(f.text for f in (*event.fact_plan.facts, *event.fact_plan.unprocessed))
        for phrase in ('English only', 'personal context', 'peer-to-peer discovery', 'no App Store'):
            self.assertIn(phrase, text)

    def test_report_projection_reuses_its_source_binding(self):
        from apple_news_core import event_identity
        evidence = self.m.capture_article_evidence('MacRumors', 'https://example.com/features',
            '<article><p>HomeView supports timers.</p></article>', '10 HomeView features you missed')
        with patch.object(event_identity, 'bind_device_capability_inventory',
                wraps=event_identity.bind_device_capability_inventory) as bind:
            projections, _, _ = self.m.project_article_evidence(evidence)
        self.assertEqual(len(projections), 1)
        self.assertEqual(projections[0].claim.subject, 'apple-home-hub')
        self.assertEqual(bind.call_count, 1)

    def test_hands_on_authentication_condition_is_support_without_promotion(self):
        import test_20261015_source_boundaries as captured
        captured.SourceBoundariesTests.setUpClass()
        case = captured.SourceBoundariesTests()
        articles = case.source_articles('95cd72fbca675105f689825b')
        article = articles[0]
        claim = next(claim for claim in self.m.article_source_conditions(article)
                     if '1f326f1a78934b246d1e5269' in claim.unit_ids)
        self.assertEqual((claim.subject, claim.report_role), ('apple-home-hub', 'supporting'))
        event = self.m.cluster_articles(articles)[0]
        self.assertEqual(event.relevance_tier, 'weak')
        self.assertTrue(any('身份验证' in fact.text for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed)))

    def test_inventory_items_cannot_borrow_another_items_owner_or_status(self):
        title = '10 HomeView features you missed'
        body = ('<p>HomeView supports timers.</p><ul>'
                '<li>HomeView could support reminders next year.</li>'
                '<li>On RivalPad, you can run widgets.</li>'
                '<li>竞品平板支持小组件。</li></ul>')
        evidence = self.m.capture_article_evidence('MacRumors', 'https://example.com/inventory',
            '<article>' + body + '</article>', title)
        projections, remainder, _ = self.m.project_article_evidence(evidence)
        self.assertEqual(len(projections), 1)
        text = ' '.join(projections[0].key_facts)
        self.assertIn('HomeView supports timers', text)
        self.assertNotIn('could support', text)
        self.assertNotIn('竞品平板', text)
        self.assertNotIn('run widgets', text)
        self.assertTrue(remainder)

    def test_authentication_belongs_to_the_requirement_object_not_its_peer(self):
        sentences = (
            ('Apple requires identity verification on RivalPad when it connects to HomeView.', False),
            ('Apple requires identity verification on HomeView when it connects to RivalPad.', True),
            ('HomeView requires identity verification, which users should complete on iPhone.', True),
            ('I wish HomeView would require identity verification.', False),
            ('HomeView may require identity verification.', False),
        )
        for text, supported in sentences:
            with self.subTest(text=text):
                article = article_for(self.m, 'HomeView hands-on', 'A hands-on review of HomeView.')
                article.key_facts = []
                article.evidence = self.m.capture_article_evidence(article.source, article.url,
                    '<article><p>' + text + '</p></article>', article.title)
                event = self.m.cluster_articles([article])[0]
                facts = [fact.text for fact in event.fact_plan.facts if 'source-condition' in fact.roles]
                self.assertEqual(text in facts, supported)
                self.assertEqual(event.relevance_tier, 'weak')

    def test_unresolved_owner_survives_real_output_without_invented_tier(self):
        m = self.m
        title = 'Several apps dominate the App Store free chart'
        body = 'Six apps lead the list. Their publisher was not identified.'
        url = 'https://www.macrumors.com/2026/10/15/chart-report/'
        payload = {'@type': 'NewsArticle', 'headline': title,
                   'datePublished': '2026-10-15T08:00:00+00:00', 'articleBody': body}
        page = ('<html><head><script type="application/ld+json">' + json.dumps(payload)
                + '</script></head><body><article><p>' + body
                + '</p></article></body></html>')

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 10, 15, 12, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)

        with tempfile.TemporaryDirectory() as directory:
            args = m.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(m, 'datetime', Clock), patch.object(m, 'collect_candidates_from_sources',
                    return_value=[m.Candidate('MacRumors', url, title)]), \
                    patch.object(m, 'fetch_url', return_value=page), \
                    patch.object(m, 'extract_time_candidates', wraps=m.extract_time_candidates) as scan:
                result = m.run(args)
                self.assertEqual(scan.call_count, 1)
        self.assertEqual(result['events'], [])
        self.assertEqual(result['deferred_events'], [])
        self.assertEqual([source['url'] for source in result['source_evidence'].values()], [url])
        reviews = [item for item in result['final_brief_queue'] if item.get('evidence_id')]
        self.assertEqual(len(reviews), 1)
        self.assertIn('unresolved', reviews[0]['reason'])
        evidence = result['source_evidence'][reviews[0]['evidence_id']]
        units = {unit['unit_id']: unit['text'] for unit in evidence['units']}
        self.assertTrue(reviews[0]['unprocessed_evidence'])
        for fragment in reviews[0]['unprocessed_evidence']:
            self.assertEqual(fragment['text'], units[fragment['unit_id']][fragment['start']:fragment['end']])


if __name__ == '__main__':
    unittest.main()
