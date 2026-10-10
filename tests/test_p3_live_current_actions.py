"""Complete-source current actions, relation cohorts, and negative boundaries."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


class LiveCurrentActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.payload = json.loads(
            (Path(__file__).parent / "fixtures/p3_live_current_actions.json").read_text()
        )
        cls.articles = {row["id"]: cls.article(row) for row in cls.payload["source_profiles"]}

    @classmethod
    def article(cls, row):
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
        return cls.m.Article(**data)

    def test_complete_sources_keep_their_current_dispositions(self):
        stock = next(co for co in self.payload["cohorts"]
                     if co["id"] == "aapl-intraday-record")["members"]
        for row in self.payload["source_profiles"]:
            with self.subTest(source=row["id"]):
                profile = self.m.article_reconciliation_profile(self.articles[row["id"]])
                tier, _, category = self.m.resolve_reconciliation_outcome(
                    profile, observed_tier="", observed_reason="", observed_category=""
                )
                self.assertEqual(tier, row["expected"]["tier"])
                if row["id"] not in stock:
                    self.assertEqual(category, row["expected"]["category"])

    def test_named_actions_reject_other_builds_owners_and_old_or_negated_meetings(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        firmware = self.articles["p10"]
        current = _source_owned_named_action(firmware.title, firmware.summary)
        self.assertIsNotNone(current)
        other_build = _source_owned_named_action(
            firmware.title.replace("4A262", "4A263"),
            firmware.summary.replace("4A262", "4A263"),
        )
        other_model = _source_owned_named_action(
            firmware.title.replace("Beats 360", "Beats 361"),
            firmware.summary.replace("Beats 360", "Beats 361"),
        )
        self.assertNotEqual(current, other_build)
        self.assertNotEqual(current, other_model)
        self.assertIsNone(_source_owned_named_action(
            firmware.title.replace(" 4A262", ""),
            firmware.summary.replace(" 4A262", ""),
        ))

        meeting = self.articles["p21"]
        self.assertEqual(_source_owned_named_action(meeting.title, meeting.summary)[1],
                         "current-government-meeting")
        self.assertIsNone(_source_owned_named_action(
            "Tim Cook and the EU Commission President",
            "Tim Cook did not meet with Ursula von der Leyen this week.",
        ))
        self.assertIsNone(_source_owned_named_action(
            "Tim Cook and the EU Commission President",
            "Tim Cook previously met with Ursula von der Leyen at the UN General Assembly.",
        ))

        government = self.articles["p22"]
        self.assertEqual(_source_owned_named_action(government.title, government.summary)[1],
                         "current-amicus-filing")
        self.assertIsNone(_source_owned_named_action(
            "Apple brief in the Epic appeal before the Supreme Court",
            "Apple filed its own brief this week about the App Store external purchase commission. "
            "The Department of Justice has not filed a brief.",
        ))

    def test_public_counterparty_and_filing_subject_controls_stay_separate(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        controls = (
            ("henna", "Tim Cook meets EU chief Henna Virkkunen today over Siri AI",
             "Tim Cook meets EU chief Henna Virkkunen today to discuss Siri AI and the Digital Markets Act.",
             ("tim-cook:eu-commission-president", "current-government-meeting"), ("p14", "p21")),
            ("unnamed", "Tim Cook meets EU chief today",
             "Tim Cook meets EU chief today to discuss digital market rules.",
             ("tim-cook:eu-commission-president", "current-government-meeting"), ("p14", "p21")),
            ("apple-brief", "Apple files its opening brief in the Epic Supreme Court appeal",
             "The Department of Justice said Apple filed a brief this week with the Supreme Court "
             "about the App Store commission injunction.",
             ("us-government:apple-epic-external-purchase", "current-amicus-filing"),
             ("p16", "p22", "p23")),
        )
        for label, title, lead, forbidden, positives in controls:
            with self.subTest(control=label):
                self.assertNotEqual(_source_owned_named_action(title, lead), forbidden)
                article = self.m.Article(
                    source="Synthetic boundary control", url=f"https://public-boundary.invalid/{label}",
                    title=title, summary=lead, key_facts=[lead], category="",
                    published_utc=self.articles[positives[0]].published_utc,
                    published_raw="", published_source="synthetic", confidence="detail",
                    tokens=self.m.article_tokens(title, lead), evidence=None,
                    event_kind=self.m.detect_event_kind(title, lead, [lead]),
                    projection_source_title=title,
                )
                events = self.m.cluster_articles([*(self.articles[name] for name in positives), article])
                groups = [{item.url for item in event.articles} for event in events]
                control_group = next(group for group in groups if article.url in group)
                self.assertEqual(control_group, {article.url})
                if label == "apple-brief":
                    self.assertEqual(article.relevance_tier, "strong")

    def test_legal_filing_requires_an_affirmative_action_by_its_named_owner(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        apple_brief = (
            "Apple files its opening brief in the Epic Supreme Court appeal",
            "The Department of Justice said Apple filed a brief this week with the Supreme Court "
            "about the App Store commission injunction.",
        )
        controls = (
            ("apple-negated-future",
             "Apple will not file its opening brief in the Epic Supreme Court appeal",
             "Apple will not file its opening brief this week with the Supreme Court in the Epic "
             "App Store commission injunction appeal.",
             ("apple-epic-external-purchase", "opening-merits-brief"), apple_brief),
            ("apple-present-negation",
             "Apple does not file its opening brief in the Epic Supreme Court appeal",
             "Apple does not file its opening brief this week about the App Store commission injunction.",
             ("apple-epic-external-purchase", "opening-merits-brief"), apple_brief),
            ("chinese-government-reporting-epic",
             "Epic本周向最高法院提交法庭之友意见书",
             "美国司法部称，Epic本周就App Store外链抽佣禁令向最高法院提交法庭之友意见书。",
             ("us-government:apple-epic-external-purchase", "current-amicus-filing"),
             ("p16", "p22", "p23")),
            ("chinese-government-quotation",
             "Epic向最高法院提交法庭之友意见书",
             "美国司法部表示，Epic本周就App Store外链抽佣禁令向最高法院提交法庭之友意见书。",
             ("us-government:apple-epic-external-purchase", "current-amicus-filing"),
             ("p16", "p22", "p23")),
        )

        def synthetic(label, title, lead):
            return self.m.Article(
                source="Synthetic boundary control", url=f"https://public-boundary.invalid/{label}",
                title=title, summary=lead, key_facts=[lead], category="",
                published_utc=self.articles["p16"].published_utc,
                published_raw="", published_source="synthetic", confidence="detail",
                tokens=self.m.article_tokens(title, lead), evidence=None,
                event_kind=self.m.detect_event_kind(title, lead, [lead]),
                projection_source_title=title,
            )

        for label, title, lead, forbidden, positives in controls:
            with self.subTest(control=label):
                self.assertNotEqual(_source_owned_named_action(title, lead), forbidden)
                article = synthetic(label, title, lead)
                reference = ([synthetic("apple-brief-positive", *positives)]
                             if isinstance(positives[0], str) and positives[0].startswith("Apple files")
                             else [self.articles[name] for name in positives])
                events = self.m.cluster_articles([*reference, article])
                group = next({item.url for item in event.articles} for event in events
                             if any(item.url == article.url for item in event.articles))
                self.assertEqual(group, {article.url})
                self.assertTrue(all(item.relevance_tier == "strong" for item in reference))

    def test_legal_filing_current_key_excludes_explicit_past_and_future(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        apple_current = (
            "Apple files its opening brief in the Epic Supreme Court appeal",
            "The Department of Justice said Apple filed a brief this week with the Supreme Court "
            "about the App Store commission injunction.",
        )
        cases = (
            ("apple-past", "Last year, Apple filed its opening brief in the Epic Supreme Court appeal",
             "Last year, Apple filed its opening brief with the Supreme Court in the Epic App Store "
             "commission injunction appeal.",
             ("apple-epic-external-purchase", "opening-merits-brief"), apple_current),
            ("apple-future", "Tomorrow, Apple files its opening brief in the Epic Supreme Court appeal",
             "Tomorrow, Apple files its opening brief with the Supreme Court in the Epic App Store "
             "commission injunction appeal.",
             ("apple-epic-external-purchase", "opening-merits-brief"), apple_current),
            ("government-past", "去年，美国司法部向最高法院提交法庭之友意见书",
             "去年，美国司法部就 Epic 与 App Store 外链抽佣禁令向最高法院提交法庭之友意见书。",
             ("us-government:apple-epic-external-purchase", "current-amicus-filing"),
             ("p16", "p22", "p23")),
            ("government-future", "明日，美国司法部向最高法院提交法庭之友意见书",
             "明日，美国司法部就 Epic 与 App Store 外链抽佣禁令向最高法院提交法庭之友意见书。",
             ("us-government:apple-epic-external-purchase", "current-amicus-filing"),
             ("p16", "p22", "p23")),
        )

        def synthetic(label, title, lead):
            return self.m.Article(
                source="Synthetic time control", url=f"https://public-boundary.invalid/{label}",
                title=title, summary=lead, key_facts=[lead], category="",
                published_utc=self.articles["p16"].published_utc,
                published_raw="", published_source="synthetic", confidence="detail",
                tokens=self.m.article_tokens(title, lead), evidence=None,
                event_kind=self.m.detect_event_kind(title, lead, [lead]),
                projection_source_title=title,
            )

        for label, title, lead, forbidden, positives in cases:
            with self.subTest(control=label):
                self.assertNotEqual(_source_owned_named_action(title, lead), forbidden)
                article = synthetic(label, title, lead)
                reference = ([synthetic("apple-current", *positives)]
                             if positives == apple_current else [self.articles[name] for name in positives])
                groups = [{item.url for item in event.articles}
                          for event in self.m.cluster_articles([*reference, article])]
                self.assertEqual(next(group for group in groups if article.url in group), {article.url})

        contextual_lead = (
            "The Apple vs Epic case began seven years ago. "
            "The Solicitor General did file a brief this week with the Supreme Court "
            "about the App Store commission injunction."
        )
        self.assertEqual(
            _source_owned_named_action("DOJ amicus brief in the Epic Supreme Court appeal", contextual_lead),
            ("us-government:apple-epic-external-purchase", "current-amicus-filing"),
        )

    def test_filing_time_belongs_to_the_filing_not_the_cited_ruling(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        apple_current = (
            "Apple files its opening brief in the Epic Supreme Court appeal",
            "The Department of Justice said Apple filed a brief this week with the Supreme Court "
            "about the App Store commission injunction.",
        )
        apple_action = ("apple-epic-external-purchase", "opening-merits-brief")
        government_action = ("us-government:apple-epic-external-purchase", "current-amicus-filing")
        cases = (
            ("apple-yesterday", "Yesterday, Apple filed its opening brief in the Epic Supreme Court appeal",
             "Apple filed its opening brief yesterday evening, less than twelve hours before this report, "
             "with the Supreme Court about the Epic App Store commission injunction.", apple_action, True),
            ("apple-earlier-week", "Earlier, Apple filed its opening brief in the Epic Supreme Court appeal",
             "Apple filed its opening brief earlier this week with the Supreme Court about the Epic "
             "App Store commission injunction.", apple_action, True),
            ("apple-cited-ruling", "Apple files its opening brief citing a ruling issued last year "
             "in the Epic Supreme Court appeal",
             "Apple filed its opening brief this week with the Supreme Court about the Epic App Store "
             "commission injunction, citing a ruling issued last year.", apple_action, True),
            ("government-cited-ruling", "DOJ filed an amicus brief citing a ruling issued last year "
             "in the Epic Supreme Court appeal",
             "The Department of Justice filed an amicus brief citing a ruling issued last year "
             "in the Supreme Court about the Epic App Store commission injunction this week.",
             government_action, True),
            ("government-yesterday", "昨日，美国司法部向最高法院提交法庭之友意见书",
             "昨日，美国司法部就 Epic 与 App Store 外链抽佣禁令向最高法院提交法庭之友意见书。",
             government_action, True),
            ("apple-last-year-suffix", "Apple filed its opening brief last year in the Epic Supreme Court appeal",
             "Apple filed its opening brief last year with the Supreme Court in the Epic App Store "
             "commission injunction appeal.", apple_action, False),
            ("government-last-year-suffix", "DOJ filed an amicus brief last year in the Epic Supreme Court appeal",
             "The Department of Justice filed an amicus brief last year with the Supreme Court "
             "about the Epic App Store commission injunction.", government_action, False),
        )

        def synthetic(label, title, lead):
            return self.m.Article(
                source="Synthetic time control", url=f"https://public-boundary.invalid/{label}",
                title=title, summary=lead, key_facts=[lead], category="",
                published_utc=self.articles["p16"].published_utc,
                published_raw="", published_source="synthetic", confidence="detail",
                tokens=self.m.article_tokens(title, lead), evidence=None,
                event_kind=self.m.detect_event_kind(title, lead, [lead]),
                projection_source_title=title,
            )

        apple_reference = synthetic("apple-current", *apple_current)
        for label, title, lead, action, should_join in cases:
            with self.subTest(control=label):
                article = synthetic(label, title, lead)
                if should_join:
                    self.assertEqual(_source_owned_named_action(title, lead), action)
                else:
                    self.assertNotEqual(_source_owned_named_action(title, lead), action)
                reference = (self.articles[name] for name in ("p16", "p22", "p23")) if action == government_action else (apple_reference,)
                events = self.m.cluster_articles([*reference, article])
                group = next({item.url for item in event.articles} for event in events
                             if any(item.url == article.url for item in event.articles))
                self.assertEqual(len(group) > 1, should_join)

    def test_report_year_needs_same_filing_current_evidence(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        report_year = self.articles["p16"].published_utc.year
        previous_year = report_year - 3
        title = f"In {report_year}, Apple filed its opening brief in the Epic Supreme Court appeal"
        lead = (f"Apple filed its opening brief this week in {report_year} with the Supreme Court "
                "about the Epic App Store commission injunction.")
        current_title = "Apple files its opening brief in the Epic Supreme Court appeal"
        current_lead = ("The Department of Justice said Apple filed a brief this week with the "
                        "Supreme Court about the App Store commission injunction.")

        def synthetic(label, headline, summary):
            return self.m.Article(
                source="Synthetic year control", url=f"https://public-boundary.invalid/{label}",
                title=headline, summary=summary, key_facts=[summary], category="",
                published_utc=self.articles["p16"].published_utc,
                published_raw="", published_source="synthetic", confidence="detail",
                tokens=self.m.article_tokens(headline, summary), evidence=None,
                event_kind=self.m.detect_event_kind(headline, summary, [summary]),
                projection_source_title=headline,
            )

        current = synthetic("year-current", title, lead)
        reference = synthetic("apple-current", current_title, current_lead)
        action = ("apple-epic-external-purchase", "opening-merits-brief")
        self.assertEqual(_source_owned_named_action(title, lead), action)
        groups = [{item.url for item in event.articles}
                  for event in self.m.cluster_articles([reference, current])]
        self.assertIn({reference.url, current.url}, groups)

        undated_title = f"In {previous_year}, Apple filed its opening brief in the Epic Supreme Court appeal"
        undated_lead = ("This week the court discussed the Epic case. "
                        f"Apple filed its opening brief in {previous_year} with the Supreme Court "
                        "about the App Store commission injunction.")
        self.assertNotEqual(_source_owned_named_action(undated_title, undated_lead), action)
        previous = synthetic("year-previous", undated_title, undated_lead)
        reference = synthetic("apple-current", current_title, current_lead)
        groups = [{item.url for item in event.articles}
                  for event in self.m.cluster_articles([reference, previous])]
        self.assertIn({previous.url}, groups)

    def test_full_cluster_joins_actions_without_crossing_negative_boundaries(self):
        before = {name: (article.url, tuple(article.key_facts), asdict(article.evidence))
                  for name, article in self.articles.items()}
        events = self.m.cluster_articles(list(self.articles.values()))
        names_by_url = {article.url: name for name, article in self.articles.items()}
        groups = [{names_by_url[article.url] for article in event.articles}
                  for event in events]
        self.assertEqual(Counter(name for group in groups for name in group),
                         Counter(self.articles.keys()))
        membership = {name: index for index, group in enumerate(groups) for name in group}
        for cohort in self.payload["cohorts"]:
            with self.subTest(cohort=cohort["id"]):
                self.assertEqual(len({membership[name] for name in cohort["members"]}), 1)
        owner_by_name = {name: cohort["id"] for cohort in self.payload["cohorts"]
                         for name in cohort["members"]}
        for group in groups:
            self.assertLessEqual(len({owner_by_name[name] for name in group
                                      if name in owner_by_name}), 1)
        for pair in self.payload["negative_pairs"]:
            with self.subTest(negative=(pair["left"], pair["right"])):
                self.assertNotEqual(membership[pair["left"]], membership[pair["right"]])
        expected = {row["id"]: row["expected"] for row in self.payload["source_profiles"]}
        stock = next(co for co in self.payload["cohorts"]
                     if co["id"] == "aapl-intraday-record")["members"]
        for event in events:
            for article in event.articles:
                name = names_by_url[article.url]
                with self.subTest(member=name):
                    self.assertEqual(article.relevance_tier, expected[name]["tier"])
                    if name not in stock:
                        self.assertEqual(article.category, expected[name]["category"])
                    self.assertEqual((article.url, tuple(article.key_facts), asdict(article.evidence)),
                                     before[name])


if __name__ == "__main__":
    unittest.main()
