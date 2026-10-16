"""Full natural-source regression for owner, stage, and source dispositions."""

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class StructuralSourceIncrementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.payload = json.loads(
            (Path(__file__).parent / "fixtures/p3_structural_source_increment.json").read_text()
        )

    def article(self, row):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference

        data = dict(row["article"])
        evidence = dict(data["evidence"])
        evidence["units"] = tuple(EvidenceUnit(**unit) for unit in evidence["units"])
        evidence["publication_candidates"] = tuple(PublicationEvidence(**item)
                                                  for item in evidence["publication_candidates"])
        evidence["embedded_references"] = tuple(EmbeddedReference(**item)
                                                for item in evidence["embedded_references"])
        data["evidence"] = ArticleEvidence(**evidence)
        data["published_utc"] = datetime.fromisoformat(data["published_utc"])
        data["tokens"] = set(data["tokens"])
        data["regions"] = set(data["regions"])
        data["projection_parent_keys"] = frozenset(data["projection_parent_keys"])
        return self.m.Article(**data)

    def test_full_sources_retain_owner_and_join_only_matching_current_claims(self):
        m = self.m
        articles = {row["id"]: self.article(row) for row in self.payload["source_profiles"]}
        profiles = {name: m.article_reconciliation_profile(article) for name, article in articles.items()}
        for row in self.payload["source_profiles"]:
            with self.subTest(source=row["id"]):
                profile = profiles[row["id"]]
                tier, _reason, category = m.resolve_reconciliation_outcome(
                    profile, observed_tier="", observed_reason="", observed_category="")
                self.assertEqual(tier, row["expected"]["tier"])
                if row["expected"].get("category") in {"hardware_products", "software_systems"}:
                    self.assertEqual(category, row["expected"]["category"])
        all_pairs = self.payload["pairs"] + self.payload["negative_pairs"]
        for pair in all_pairs:
            with self.subTest(pair=(pair["left"], pair["right"])):
                same = m.profile_pair_decision(profiles[pair["left"]], profiles[pair["right"]]) == "match"
                self.assertEqual(same, pair["expected"] == "match")

        before = {name: (article.url, tuple(article.key_facts),
                         tuple(asdict(unit) for unit in article.evidence.units))
                  for name, article in articles.items()}
        events = m.cluster_articles(list(articles.values()))
        ids = {id(article): name for name, article in articles.items()}
        groups = [{ids[id(article)] for article in event.articles} for event in events]
        self.assertEqual(Counter(name for group in groups for name in group), Counter(articles.keys()))
        for pair in all_pairs:
            with self.subTest(full_group=(pair["left"], pair["right"])):
                same = any({pair["left"], pair["right"]} <= group for group in groups)
                self.assertEqual(same, pair["expected"] == "match")
        for name, article in articles.items():
            with self.subTest(disposition=name):
                self.assertEqual((article.url, tuple(article.key_facts),
                                  tuple(asdict(unit) for unit in article.evidence.units)), before[name])



if __name__ == "__main__":
    unittest.main()
