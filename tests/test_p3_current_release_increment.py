"""Keep a current OS release distinct from a historical roadmap recap."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class CurrentReleaseIncrementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.payload = json.loads(
            (Path(__file__).parent / "fixtures/p3_current_release_increment.json").read_text()
        )

    def article(self, row):
        from apple_news_core.models import ArticleEvidence, EmbeddedReference, EvidenceUnit, PublicationEvidence

        data = dict(row["article"])
        evidence = dict(data["evidence"])
        evidence["units"] = tuple(EvidenceUnit(**item) for item in evidence["units"])
        evidence["publication_candidates"] = tuple(
            PublicationEvidence(**item) for item in evidence["publication_candidates"]
        )
        evidence["embedded_references"] = tuple(
            EmbeddedReference(**item) for item in evidence["embedded_references"]
        )
        data["evidence"] = ArticleEvidence(**evidence)
        data["published_utc"] = datetime.fromisoformat(data["published_utc"])
        data["tokens"] = set(data["tokens"])
        data["regions"] = set(data["regions"])
        data["projection_parent_keys"] = frozenset(data["projection_parent_keys"])
        return self.m.Article(**data)

    def test_current_release_retains_its_action_and_original_evidence(self):
        row = self.payload["source_profiles"][0]
        article = self.article(row)
        before = (article.url, tuple(article.key_facts),
                  tuple(asdict(unit) for unit in article.evidence.units))
        self.assertFalse(self.m.historical_roadmap_recap_without_current_report(
            article.title, article.summary, article.key_facts
        ))
        profile = self.m.article_reconciliation_profile(article)
        tier, _, category = self.m.resolve_reconciliation_outcome(
            profile, observed_tier="", observed_reason="", observed_category=""
        )
        self.assertEqual((tier, category), ("strong", "software_systems"))
        self.assertEqual((article.url, tuple(article.key_facts),
                          tuple(asdict(unit) for unit in article.evidence.units)), before)
        self.assertEqual(len(article.evidence.units), 37)
        self.assertEqual(len(article.key_facts), 14)

    def test_old_recap_still_has_no_new_strong_roadmap_action(self):
        parent = self.payload["parent_projection_inputs"][0]["extraction"]
        self.assertTrue(self.m.historical_roadmap_recap_without_current_report(
            parent["title"], parent["summary"], parent["key_facts"]
        ))
        variants = []
        for title, summary, facts in self.m.roundup_article_variants(
                parent["candidate"]["title"], parent["title"],
                parent["summary"], parent["key_facts"]):
            variants.extend(self.m.compound_article_variants(title, summary, facts))
        self.assertTrue(variants)
        original_facts = Counter(parent["key_facts"])
        self.assertTrue(any("2025" in fact for fact in original_facts))
        self.assertTrue(any("2025" in fact for _, _, facts in variants for fact in facts))
        self.assertTrue(all(self.m.source_text_outcome(
            title, summary, facts, parent["candidate"]["source"],
            source_title=parent["candidate"]["title"]
        )[0] != "strong" for title, summary, facts in variants))

    def test_market_fraction_belongs_to_apple_only_when_apple_is_measured(self):
        title = "Apple holds 65% of the premium smartphone market as segment reaches record high"
        summary = ("Counterpoint measured Apple at 65% of premium smartphone sales "
                   "in the first half of 2026, up from 63% a year earlier.")
        self.assertTrue(self.m.is_apple_specific_market_share_report_story(title))
        self.assertTrue(self.m.is_apple_specific_market_share_report_story(summary, title))

        previous = json.loads(
            (Path(__file__).parent / "fixtures/p3_structural_source_increment.json").read_text()
        )
        market_background = next(row["article"] for row in previous["source_profiles"]
                                 if row["id"] == "s06")
        self.assertFalse(self.m.is_apple_specific_market_share_report_story(
            market_background["summary"], market_background["title"]
        ))


if __name__ == "__main__":
    unittest.main()
