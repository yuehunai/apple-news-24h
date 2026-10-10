"""Complete-source regression for the reported screenless band prototype."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class PublicBandIncrementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        fixtures = Path(__file__).parent / "fixtures"
        cls.band = json.loads((fixtures / "p3_public_band_increment.json").read_text())
        cls.previous = json.loads((fixtures / "p3_structural_source_increment.json").read_text())

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

    def test_full_sources_join_one_prototype_without_losing_evidence(self):
        rows = self.band["source_profiles"]
        articles = {row["id"]: self.article(row) for row in rows}
        before = {name: (article.url, tuple(article.key_facts), asdict(article.evidence))
                  for name, article in articles.items()}
        profiles = {name: self.m.article_reconciliation_profile(article)
                    for name, article in articles.items()}
        for name, profile in profiles.items():
            with self.subTest(source=name):
                tier, _, category = self.m.resolve_reconciliation_outcome(
                    profile, observed_tier="", observed_reason="", observed_category=""
                )
                self.assertEqual((tier, category), ("strong", "hardware_products"))
        for pair in self.band["pairs"]:
            with self.subTest(pair=(pair["left"], pair["right"])):
                self.assertEqual(self.m.profile_pair_decision(
                    profiles[pair["left"]], profiles[pair["right"]]), "match")

        pendant_row = next(row for row in self.previous["source_profiles"] if row["id"] == "s26")
        pendant = self.article(pendant_row)
        pendant_profile = self.m.article_reconciliation_profile(pendant)
        self.assertNotEqual(self.m.profile_pair_decision(profiles["b01"], pendant_profile), "match")

        events = self.m.cluster_articles([*articles.values(), pendant])
        ids = {id(article): name for name, article in articles.items()}
        ids[id(pendant)] = "pendant"
        groups = [{ids[id(article)] for article in event.articles} for event in events]
        self.assertEqual(Counter(name for group in groups for name in group),
                         Counter([*articles.keys(), "pendant"]))
        self.assertIn(set(articles), groups)
        self.assertIn({"pendant"}, groups)
        for name, article in articles.items():
            with self.subTest(evidence=name):
                self.assertEqual((article.url, tuple(article.key_facts), asdict(article.evidence)),
                                 before[name])


if __name__ == "__main__":
    unittest.main()
