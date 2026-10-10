"""Complete public-source launch and storage disclosure relation controls."""

from datetime import datetime
from dataclasses import replace
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class LiveSsdLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.sources = {
            row["id"]: row for row in json.loads(
                (Path(__file__).parent / "fixtures/p3_live_ssd_launch.json").read_text()
            )["sources"]
        }

    @classmethod
    def article(cls, source_id):
        from apple_news_core.models import ArticleEvidence, EmbeddedReference, EvidenceUnit, PublicationEvidence

        row = cls.sources[source_id]["recorded_articles"][0]
        data = dict(row)
        evidence = dict(data["evidence"])
        evidence["units"] = tuple(EvidenceUnit(**unit) for unit in evidence["units"])
        evidence["publication_candidates"] = tuple(PublicationEvidence(**item) for item in evidence["publication_candidates"])
        evidence["embedded_references"] = tuple(EmbeddedReference(**item) for item in evidence["embedded_references"])
        data["evidence"] = ArticleEvidence(**evidence)
        data["published_utc"] = datetime.fromisoformat(data["published_utc"])
        data["tokens"] = set(data["tokens"])
        data["regions"] = set(data["regions"])
        data["projection_parent_keys"] = frozenset(data["projection_parent_keys"])
        return cls.m.Article(**data)

    def test_current_launch_keeps_hands_on_with_official_release_but_not_other_actions(self):
        articles = {id_: self.article(id_) for id_ in ("p01", "p02", "p03", "p04", "p05")}
        groups = [set(article.url for article in event.articles)
                  for event in self.m.cluster_articles(list(articles.values()))]
        launch = {articles[id_].url for id_ in ("p01", "p02", "p03")}
        self.assertIn(launch, groups)
        self.assertIn({articles["p04"].url}, groups)
        self.assertIn({articles["p05"].url}, groups)
        self.assertEqual(articles["p02"].relevance_tier, "weak")

    def test_current_storage_disclosure_joins_measurements_but_not_support_document(self):
        articles = {id_: self.article(id_) for id_ in ("p06", "p07", "p08", "p09", "p11")}
        groups = [set(article.url for article in event.articles)
                  for event in self.m.cluster_articles(list(articles.values()))]
        self.assertIn({articles[id_].url for id_ in ("p06", "p07", "p08", "p09")}, groups)
        self.assertIn({articles["p11"].url}, groups)

    def test_current_disclosure_parent_is_not_a_historical_roadmap(self):
        row = self.sources["p10"]
        extraction = row["extraction"]
        variants = self.m.compound_article_variants(
            extraction["title"], extraction["summary"], extraction["key_facts"]
        )
        self.assertEqual(variants, [(
            extraction["title"], extraction["summary"], extraction["key_facts"]
        )])
        self.assertTrue(any("必须成对更换" in unit["text"] for unit in row["evidence"]["units"]))

    def test_unsplit_parent_repairs_remain_in_final_review_with_exact_source_span(self):
        source = self.sources["p10"]
        extraction = source["extraction"]
        original = self.article("p10")
        parent = replace(original, title=extraction["title"], summary=extraction["summary"],
                         key_facts=extraction["key_facts"], projection_child_key="",
                         projected_fact_spans=None)
        others = [self.article(id_) for id_ in ("p06", "p07", "p08", "p09", "p11")]
        event = next(event for event in self.m.cluster_articles([*others, parent])
                     if parent in event.articles)
        unit = next(unit for unit in parent.evidence.units if "必须成对更换" in unit.text)
        start = unit.text.index("苹果维修指南显示")
        end = len(unit.text)
        self.assertTrue(any(origin[3] == unit.unit_id and origin[4] <= start and origin[5] >= end
                            for fact in event.fact_plan.unprocessed for origin in fact.origins))

    def test_supplier_denial_and_other_chip_pair_are_not_the_current_disclosure(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        current = self.article("p08")
        title = "New Mac mini NAND report for M6 and M5 Pro"
        denial = ("Expand Mac mini denied reports that NAND storage in the new M6 and M5 Pro "
                  "Mac mini is soldered to the logic board. The claim remains unconfirmed.")
        self.assertIsNone(_source_owned_named_action(title, denial))
        shifted_owner = ("Expand Mac mini表示另一厂商确认，新款 M6 和 M5 Pro Mac mini 的 NAND "
                         "已经焊接在逻辑板上。")
        self.assertIsNone(_source_owned_named_action(title, shifted_owner))
        current_key = _source_owned_named_action(current.title, current.summary)
        other = current.summary.replace("M6", "M7").replace("M5 Pro", "M6 Pro")
        other_key = _source_owned_named_action(current.title, other)
        self.assertIsNotNone(current_key)
        self.assertIsNotNone(other_key)
        self.assertNotEqual(current_key, other_key)

        denied = self.m.Article(
            source="Synthetic boundary control", url="https://public-boundary.invalid/ssd-denial",
            title=title, summary=denial, key_facts=[denial], category="",
            published_utc=current.published_utc, published_raw="", published_source="synthetic",
            confidence="detail", tokens=self.m.article_tokens(title, denial),
            event_kind=self.m.detect_event_kind(title, denial, [denial]),
            projection_source_title=title,
        )
        groups = [set(article.url for article in event.articles)
                  for event in self.m.cluster_articles([current, denied])]
        self.assertIn({current.url}, groups)
        self.assertIn({denied.url}, groups)
        later = replace(current, url="https://public-boundary.invalid/other-chip-pair",
                        summary=other, key_facts=[other], evidence=None,
                        tokens=self.m.article_tokens(current.title, other))
        separated = [set(article.url for article in event.articles)
                     for event in self.m.cluster_articles([current, later])]
        self.assertIn({current.url}, separated)
        self.assertIn({later.url}, separated)

    def test_future_beats_announcement_does_not_inherit_completed_launch(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        title = "Beats计划推出360头戴式耳机"
        lead = "Beats计划正式发布全新头戴式耳机Beats360，目前仍未上市。"
        self.assertIsNone(_source_owned_named_action(title, lead))
        future = self.m.Article(
            source="Synthetic boundary control", url="https://public-boundary.invalid/beats-future",
            title=title, summary=lead, key_facts=[lead], category="",
            published_utc=self.article("p01").published_utc,
            published_raw="", published_source="synthetic", confidence="detail",
            tokens=self.m.article_tokens(title, lead),
            event_kind=self.m.detect_event_kind(title, lead, [lead]),
            projection_source_title=title,
        )
        launched = self.article("p01")
        groups = [set(article.url for article in event.articles)
                  for event in self.m.cluster_articles([launched, future])]
        self.assertIn({launched.url}, groups)
        self.assertIn({future.url}, groups)

    def test_supplier_passive_confirmation_requires_a_completed_affirmative_clause(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        current = self.article("p08")
        title = "New Mac mini NAND report for M6 and M5 Pro"
        variants = {
            "future": ("The soldered NAND storage in the M6 and M5 Pro Mac mini will be "
                       "confirmed by Expand Mac mini tomorrow. No confirmation has been issued yet."),
            "denied": ("The soldered NAND storage in the M6 and M5 Pro Mac mini has not been "
                       "confirmed by Expand Mac mini. The claim remains unconfirmed."),
            "future-perfect": ("The soldered NAND storage in the M6 and M5 Pro Mac mini will have been "
                               "confirmed by Expand Mac mini by tomorrow."),
            "cannot-have-been": ("The soldered NAND storage in the M6 and M5 Pro Mac mini cannot have been "
                                 "confirmed by Expand Mac mini. The claim remains unconfirmed."),
            "cant-have-been": ("The soldered NAND storage in the M6 and M5 Pro Mac mini can't have been "
                               "confirmed by Expand Mac mini. The claim remains unconfirmed."),
            "couldnt-have-been": ("The soldered NAND storage in the M6 and M5 Pro Mac mini couldn't have been "
                                  "confirmed by Expand Mac mini. The claim remains unconfirmed."),
            "will-not-have-been": ("The soldered NAND storage in the M6 and M5 Pro Mac mini will not have been "
                                   "confirmed by Expand Mac mini by tomorrow."),
        }
        for label, lead in variants.items():
            with self.subTest(label=label):
                self.assertIsNone(_source_owned_named_action(title, lead))
                variant = self.m.Article(
                    source="Synthetic boundary control",
                    url=f"https://public-boundary.invalid/supplier-passive-{label}",
                    title=title, summary=lead, key_facts=[lead], category="",
                    published_utc=current.published_utc, published_raw="",
                    published_source="synthetic", confidence="detail",
                    tokens=self.m.article_tokens(title, lead),
                    event_kind=self.m.detect_event_kind(title, lead, [lead]),
                    projection_source_title=title,
                )
                groups = [set(article.url for article in event.articles)
                          for event in self.m.cluster_articles([current, variant])]
                self.assertIn({current.url}, groups)
                self.assertIn({variant.url}, groups)
        affirmative = ("The soldered NAND storage in the M6 and M5 Pro Mac mini has been "
                       "confirmed by Expand Mac mini today.")
        self.assertEqual(_source_owned_named_action(title, affirmative),
                         _source_owned_named_action(current.title, current.summary))
        confirmed = self.m.Article(
            source="Synthetic boundary control",
            url="https://public-boundary.invalid/supplier-passive-confirmed",
            title=title, summary=affirmative, key_facts=[affirmative], category="",
            published_utc=current.published_utc, published_raw="", published_source="synthetic",
            confidence="detail", tokens=self.m.article_tokens(title, affirmative),
            event_kind=self.m.detect_event_kind(title, affirmative, [affirmative]),
            projection_source_title=title,
        )
        self.assertEqual(len(self.m.cluster_articles([current, confirmed])), 1)
