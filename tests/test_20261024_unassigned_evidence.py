"""Captured material remains accountable when no parent event was admitted."""
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class UnassignedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference
        rows = json.loads((Path(__file__).parent /
            'fixtures/20261024_unassigned_evidence.json').read_text())
        cls.evidence = {}
        for key, row in rows.items():
            row['units'] = tuple(EvidenceUnit(**u) for u in row['units'])
            row['publication_candidates'] = tuple(PublicationEvidence(**u) for u in row['publication_candidates'])
            row['embedded_references'] = tuple(EmbeddedReference(**u) for u in row['embedded_references'])
            cls.evidence[key] = ArticleEvidence(**row)

    def test_real_unassigned_sources_keep_local_actions_and_context(self):
        events, reviews, dispositions = [], [], {}
        self.m.add_source_remainder_reviews(events, self.evidence, reviews, dispositions)
        by_id = {item['evidence_id']: item for item in reviews}
        self.assertEqual(set(by_id), set(self.evidence))
        for key, text in (
            ('45d2d353978010e4c697fac2', '从macOS发起串流'),
            ('45d2d353978010e4c697fac2', '目前这些改动仅面向测试版用户'),
            ('98b7b0a250d66c5d6aac479b', '正在逐步推出'),
            ('98b7b0a250d66c5d6aac479b', 'iPhone 则先提供较有限'),
            ('b8e1687ac1d119842c690cb4', 'Apple is also planning to add its reachability feature'),
        ):
            with self.subTest(source=key, text=text):
                self.assertIn(text, ' '.join(part['text'] for part in by_id[key]['unprocessed_evidence']))
        for key, evidence in self.evidence.items():
            disposition = dispositions[key]
            self.assertEqual(disposition['coverage'], 'captured-source-spans')
            self.m.validate_source_span_dispositions(evidence, disposition['assigned'],
                disposition['unprocessed'], [(x['unit_id'], x['start'], x['end'], x['reason'])
                    for x in disposition['excluded']])
        # A review obligation is not an Apple event or an eligibility decision.
        self.assertEqual(events, [])
        self.assertTrue(all(item['required'] and 'relevance_tier' not in item for item in reviews))

    def test_unassigned_review_is_idempotent_and_preserves_prior_exclusion(self):
        key = '45d2d353978010e4c697fac2'
        evidence = self.evidence[key]
        unit = evidence.units[2]
        exclusion = {'unit_id': unit.unit_id, 'start': 0, 'end': len(unit.text), 'reason': 'Resolved historical background'}
        dispositions = {key: {'assigned': [], 'unprocessed': [], 'excluded': [exclusion]}}
        reviews = []
        self.m.add_source_remainder_reviews([], {key: evidence}, reviews, dispositions)
        self.assertEqual(len(reviews), 1)
        first = json.dumps((reviews, dispositions), sort_keys=True)
        self.m.add_source_remainder_reviews([], {key: evidence}, reviews, dispositions)
        self.assertEqual(json.dumps((reviews, dispositions), sort_keys=True), first)
        self.assertIn(exclusion, dispositions[key]['excluded'])
        self.assertFalse(any(p['unit_id'] == unit.unit_id for p in reviews[0]['unprocessed_evidence']))

    def test_fully_disposed_source_does_not_create_an_empty_review(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        evidence = ArticleEvidence('closed', 'Local', 'https://example.com/closed',
            'Closed source', '', 'news', (EvidenceUnit('body', 'p', 'Resolved text.', 'html', 0),))
        dispositions = {'closed': {'assigned': [], 'unprocessed': [], 'excluded': [
            {'unit_id': 'body', 'start': 0, 'end': 14, 'reason': 'Explicit prior exclusion'}]}}
        reviews = []
        self.m.add_source_remainder_reviews([], {'closed': evidence}, reviews, dispositions)
        self.assertEqual(reviews, [])
        self.assertEqual(dispositions['closed'].get('coverage'), 'captured-source-spans')


if __name__ == '__main__':
    unittest.main()
