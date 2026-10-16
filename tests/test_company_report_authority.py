"""Company reports use captured responsibilities, not a person's retrieval key."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class CompanyReportAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261016_company_reports.json').read_text())

    def article(self, key):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference
        data = dict(self.rows[key])
        for field, record in (('units', EvidenceUnit), ('publication_candidates', PublicationEvidence),
                              ('embedded_references', EmbeddedReference)):
            data[field] = tuple(record(**value) for value in data[field])
        evidence = ArticleEvidence(**data)
        return self.m.Article(evidence.source, evidence.url, evidence.title, evidence.raw_lead,
            [u.text for u in evidence.units if u.kind == 'p'], '',
            datetime.fromisoformat(evidence.published_utc), evidence.published_raw,
            evidence.published_source, evidence.confidence, set(), evidence=evidence)

    def test_current_company_responsibilities_own_qualification_and_category(self):
        for sid in ('54a2aa5303eda632a03546bf', '4661b7af3fcb8ac7532a0534', '75f2b8516e97b7e08cc908f8'):
            with self.subTest(source=sid):
                article = self.article('r4-' + sid)
                profile = self.m.article_reconciliation_profile(article)
                self.assertIsNotNone(profile.eligibility)
                self.assertEqual((profile.eligibility.tier, profile.eligibility.category),
                                 ('strong', 'hardware_products'))
                self.assertEqual(profile.bound_claim.action, 'leadership-report')
                self.assertTrue(profile.bound_claim.evidence_spans)
                # Neither retrieval words nor the old classifier may override it.
                result = self.m.resolve_reconciliation_outcome(replace(profile,
                    event_keys=frozenset({'structured-first-party-subject:other'})),
                    observed_tier='weak', observed_reason='legacy', observed_category='software_systems')
                self.assertEqual((result[0], result[2]), ('strong', 'hardware_products'))

    def test_profile_or_topic_listing_cannot_borrow_a_company_action(self):
        for key in ('r3-54a2aa5303eda632a03546bf', 'r4-606e01c61dce3ba01dfb796d'):
            with self.subTest(source=key):
                profile = self.m.article_reconciliation_profile(self.article(key))
                self.assertIsNotNone(profile.eligibility)
                self.assertNotEqual(profile.eligibility.tier, 'strong')
        from apple_news_core.event_identity import bind_leadership_report
        for title in ('Apple CEO Jane Miller confirms a beta release in an interview',
                      'Apple CEO John Ternus Confirms Beta Release in New Interview',
                      '库克确认苹果国行 AI，10 月底上线测试版！'):
            evidence = self.m.capture_article_title_evidence('Source', '', title,
                'Apple CEO Jane Miller confirmed the beta release in an interview with The Observer.', ())
            self.assertIsNone(bind_leadership_report(evidence))

    def test_current_role_is_source_bound_not_a_known_person_assumption(self):
        from apple_news_core.event_identity import bind_leadership_report
        from apple_news_core.article_processing import capture_article_title_evidence
        for owner, expected in (('Apple', 'apple-direct'), ('Acme', 'independent')):
            title = owner + ' CEO Jane Miller discusses company design work'
            lead = owner + ' CEO Jane Miller gave an interview with The Observer.'
            fact = 'Miller currently leads the industrial design team and spends two days each week in its studio.'
            evidence = capture_article_title_evidence('Source', 'https://example.test/report', title, lead, (fact,))
            claim = bind_leadership_report(evidence)
            self.assertIsNotNone(claim)
            self.assertEqual(claim.subject_relation, expected)
        title = 'Former Apple CEO Jane Miller discusses company design work'
        evidence = capture_article_title_evidence('Source', 'https://example.test/report', title,
            'Former Apple CEO Jane Miller gave an interview with The Observer about her career.',
            ('She led the industrial design team many years ago.',))
        self.assertNotEqual(self.m.claim_eligibility(bind_leadership_report(evidence)).tier, 'strong')

    def test_same_person_and_publisher_are_not_an_interview_instance(self):
        from apple_news_core.event_identity import bind_leadership_report
        from apple_news_core.article_processing import capture_article_title_evidence
        from apple_news_core.event_matcher import identity_pair_decision
        title = 'Apple CEO Jane Miller discusses company design work'
        lead = 'Apple CEO Jane Miller gave an interview with The Observer.'
        fact = 'Miller currently leads the industrial design team and spends two days each week in its studio.'
        claims = [bind_leadership_report(capture_article_title_evidence('Source', url, title, lead, (fact,)))
                  for url in ('https://example.test/a', 'https://example.test/b')]
        self.assertEqual(identity_pair_decision(*claims), 'unknown')

    def test_local_role_and_assertion_do_not_borrow_current_apple_authority(self):
        from apple_news_core.event_identity import bind_leadership_report
        from apple_news_core.article_processing import capture_article_title_evidence
        rows = (
            ('CEO Jane Miller discusses her work in an interview',
             'In the interview, Acme CEO Jane Miller compared her company with Apple.',
             'Miller currently leads the industrial design team at Acme.'),
            ('CEO Jane Miller discusses her work in an interview',
             'In the interview, Apple CEO John Ternus praises Jane Miller at Acme.',
             'Miller currently leads the industrial design team at Acme.'),
            ('John Ternus discusses his work in an interview',
             'John Ternus, a former Apple CEO, gave an interview with The Observer.',
             'Ternus currently leads the design team at Acme.'),
            ('Apple CEO Jane Miller discusses her career',
             'Apple CEO Jane Miller gave an interview with The Observer about her childhood.',
             'An archival interview published last year reports that Miller said Apple focuses on design.'),
            ('Apple CEO Jane Miller in a new interview',
             'Apple CEO Jane Miller gave an interview with The Observer.',
             'If Miller says Apple prioritizes design, that will be welcome news.'),
            ('Apple CEO Jane Miller discusses leadership',
             'Apple CEO Jane Miller gave an interview with The Observer.',
             'Miller interviewed Acme CEO Bob Jones, who is responsible for the industrial design team at Acme.'),
            ('Apple CEO Jane Miller discusses her career',
             'Apple CEO Jane Miller gave an interview with The Observer.',
             'Miller discussed leadership transition as a general topic during the interview.'),
        )
        for title, lead, fact in rows:
            with self.subTest(fact=fact):
                claim = bind_leadership_report(capture_article_title_evidence('Source', '', title, lead, (fact,)))
                self.assertIsNotNone(claim)
                self.assertNotEqual(self.m.claim_eligibility(claim).tier, 'strong')

    def test_decision_object_keeps_software_policy_and_company_scope_distinct(self):
        from apple_news_core.event_identity import bind_leadership_report
        from apple_news_core.article_processing import capture_article_title_evidence
        title = 'Apple CEO Jane Miller explains a business decision'
        lead = 'Apple CEO Jane Miller gave an interview with The Observer.'
        for fact, category in (
            ('Miller said Apple considers charging developers a new fee for App Store distribution.', 'software_systems'),
            ('Miller said Apple considers every viable option for its supply chain.', 'hardware_products'),
            ('Miller said Apple focuses on areas where it can differentiate, using Siri as an example.', 'hardware_products'),
        ):
            claim = bind_leadership_report(capture_article_title_evidence('Source', '', title, lead, (fact,)))
            decision = self.m.claim_eligibility(claim)
            self.assertEqual((decision.tier, decision.category), ('strong', category))

    def test_role_evidence_need_not_be_selected_as_a_news_fact(self):
        article = self.article('r4-54a2aa5303eda632a03546bf')
        projections, remaining, excluded = self.m.project_article_evidence(article.evidence)
        self.m.validate_evidence_dispositions(article.evidence, projections, remaining, excluded)
        projection, = projections
        claim = projection.claim
        self.assertTrue(any(key not in claim.unit_ids for _, _, _, key, _, _ in claim.qualifiers))
        first = claim.qualifiers[0]
        for invalid in ((*first[:3], 'foreign-source-unit', 0, 5), (*first[:4], 0, 1000000)):
            with self.assertRaises(ValueError):
                self.m.validate_evidence_dispositions(article.evidence,
                    (replace(projection, claim=replace(claim, qualifiers=(invalid,))),), remaining, excluded)


if __name__ == '__main__':
    unittest.main()
