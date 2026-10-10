"""Source-owned actions and lossless projection on complete public articles."""

import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class LiveSourceSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        fixture = json.loads((Path(__file__).parent / "fixtures/p3_live_source_semantics.json").read_text())
        cls.rows = {row["id"]: row for row in fixture["cases"]}
        cls.pairs = fixture["pairs"]

    def article(self, row):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit

        m = self.m
        published = datetime(2027, 9, 18, tzinfo=timezone.utc)
        article = m.Article(
            source=row["source"], url=row["url"], title=row["title"],
            summary=row["summary"], key_facts=list(row["key_facts"]),
            category="", published_utc=published,
            published_raw="2027-09-18T00:00:00Z", published_source="synthetic",
            confidence="detail", tokens=m.article_tokens(row["title"], row["summary"]),
            regions=m.extract_regions(" ".join([row["title"], row["summary"], *row["key_facts"]])),
        )
        article.evidence = ArticleEvidence(
            article_id=row["id"], source=row["source"], url=row["url"],
            title=row["title"], raw_lead=row["summary"], content_form="news",
            units=tuple(EvidenceUnit(f"{row['id']}-u{i}", unit["kind"], unit["text"], "html", i)
                        for i, unit in enumerate(row["units"])),
            published_utc=published.isoformat(), published_raw=article.published_raw,
            published_source="synthetic", confidence="detail", extraction_path="detail",
            discovery_title=row["title"], discovery_lead=row["summary"],
        )
        return article

    def test_source_action_and_category_come_from_the_current_owner(self):
        m = self.m
        for row in self.rows.values():
            if row["review_role"] != "same-first-path-red":
                continue
            expected = row["expected"]
            if "tier" not in expected:
                continue
            with self.subTest(source=row["id"]):
                profile = m.article_reconciliation_profile(self.article(row))
                tier, _reason, category = m.resolve_reconciliation_outcome(
                    profile, observed_tier="", observed_reason="", observed_category="")
                self.assertEqual(tier, expected["tier"])
                if "category" in expected:
                    self.assertEqual(category, expected["category"])
                forbidden = expected.get("forbidden_event_key")
                if forbidden:
                    self.assertFalse(any(forbidden in key for key in profile.event_keys))

    def test_complete_sources_join_only_the_same_named_action(self):
        m = self.m
        originals = [self.article(row) for row in self.rows.values()
                     if row["id"] not in {"recap-parent-grammar", "mixed-claim-grammar"}]
        by_id = {article.evidence.article_id: article for article in originals}
        profiles = {name: m.article_reconciliation_profile(article) for name, article in by_id.items()}
        for left, right, expected in self.pairs:
            with self.subTest(pair=(left, right)):
                decision = m.profile_pair_decision(profiles[left], profiles[right])
                self.assertEqual(decision == "match", expected == "match")
        events = m.cluster_articles(originals)
        groups = [{article.evidence.article_id for article in event.articles} for event in events]
        self.assertEqual(set().union(*groups), set(by_id))
        self.assertEqual(sum(map(len, groups)), len(originals))
        for left, right, expected in self.pairs:
            with self.subTest(full_group=(left, right)):
                same = any({left, right} <= group for group in groups)
                self.assertEqual(same, expected == "match")

    def test_historical_parent_retains_original_facts_without_current_children(self):
        from apple_news_core.article_projector import historical_roadmap_recap_without_current_report

        m = self.m
        for name in ("recap-parent", "recap-parent-grammar"):
            row = self.rows[name]
            with self.subTest(source=name):
                self.assertEqual(len(row["units"]), 6)
                self.assertTrue(historical_roadmap_recap_without_current_report(
                    row["title"], row["summary"], row["key_facts"]))
                article = self.article(row)
                profile = m.article_reconciliation_profile(article)
                self.assertEqual(m.resolve_reconciliation_outcome(
                    profile, observed_tier="", observed_reason="", observed_category="")[0], "weak")
                variants = m.compound_article_variants(row["title"], row["summary"], row["key_facts"])
                self.assertEqual(len(variants), 1)
                self.assertEqual(variants[0][2], row["key_facts"])
                self.assertTrue(any("2025 — Press Release" in fact for fact in variants[0][2]))
        new_report = self.rows["recap-parent-grammar"]
        self.assertFalse(historical_roadmap_recap_without_current_report(
            new_report["title"], new_report["summary"],
            [*new_report["key_facts"], "Apple today announced a new Home hub with an updated display."]))

    def test_mixed_sentence_keeps_tv_clause_and_siri_rollout_in_distinct_spans(self):
        from apple_news_core.article_projector import project_article_evidence

        for name in ("mixed-claim", "mixed-claim-grammar"):
            row = self.rows[name]
            with self.subTest(source=name):
                self.assertEqual(len(row["units"]), 4)
                evidence = self.article(row).evidence
                source_unit = evidence.units[1].text
                boundary = source_unit.index("Siri AI")
                projections, remaining, excluded = project_article_evidence(evidence)
                siri = [projection for projection in projections
                        if projection.subject == "siri" and projection.action == "rollout"]
                self.assertEqual(len(siri), 1)
                self.assertEqual({item[0] for item in siri[0].claim.qualifiers},
                                 {"french", "japanese", "spanish"})
                self.assertEqual(siri[0].claim.evidence_spans,
                                 ((evidence.units[1].unit_id, boundary, len(source_unit)),))
                self.assertNotIn("Apple TV app", siri[0].summary)
                self.assertIn((evidence.units[1].unit_id, 0, boundary - 1), remaining)
                self.assertIn((evidence.units[1].unit_id, boundary - 1, boundary,
                               "Whitespace separator"), excluded)

    def test_title_sparse_owned_action_and_external_owner_stay_distinct(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        cases = (
            ("Screen-Free Fitness Band Prototypes Under Test",
             "Apple has tested prototypes of a screen-free fitness band for continuous health tracking.",
             "band-zh", True),
            ("Whoop Tests Screen-Free Fitness Band, With Apple Watch as Context",
             "Whoop tested a screen-free fitness band. Apple Watch is only a comparison product.",
             "band-zh", False),
            ("AI Pendant Project Put on Hold",
             "Apple has put its AI pendant project on hold. The device has no release date.",
             "pin-zh", True),
            ("Startup Puts AI Pendant Project on Hold, Citing Apple Plans",
             "A startup put its AI pendant on hold. Apple Siri plans are background context.",
             "pin-zh", False),
            ("Texture and Grain Controls Support List Clarified",
             "Apple revised its support page to clarify that Texture and Grain controls require selected models. These are software editing options in the camera app.",
             "texture-zh", True),
            ("Third-Party Editor Revises Texture and Grain Controls for iPhone",
             "A third-party editor revised Texture and Grain controls for its app. Apple devices merely run the app's software.",
             "texture-zh", False),
        )
        for index, (title, lead, partner, should_match) in enumerate(cases):
            with self.subTest(title=title):
                relation = _source_owned_named_action(title, lead)
                self.assertEqual(relation is not None, should_match)
                sparse = self.article({"id": f"sparse-{index}", "source": "MacRumors",
                                       "url": f"https://example.invalid/sparse-{index}",
                                       "title": title, "summary": lead, "key_facts": [lead],
                                       "units": [{"kind": "p", "text": lead}]})
                reported = self.article(self.rows[partner])
                decision = self.m.profile_pair_decision(
                    self.m.article_reconciliation_profile(sparse),
                    self.m.article_reconciliation_profile(reported))
                self.assertEqual(decision == "match", should_match)


if __name__ == "__main__":
    unittest.main()
