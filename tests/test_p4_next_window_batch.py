"""Full captured source boundaries from the September 25 pure window."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

import test_p4_pure_json_batch as prior
from test_relevance_rules import load_module


FIXTURE = Path(__file__).parent / "fixtures/p4_next_window_sources.json"


class NextWindowBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.sources = {source.name: source for source in cls.m.build_sources(
            datetime(2026, 9, 25, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def assert_source_span(self, event, article_id, index, *, start=0, end=None):
        unit = self.rows[article_id]["evidence"]["units"][index]
        end = len(unit["text"]) if end is None else end
        expected = unit["text"][start:end]
        self.assertTrue(any(
            fact.text == expected and any(
                origin[2:] == (article_id, unit["unit_id"], start, end)
                for origin in fact.origins)
            for fact in (*event.fact_plan.facts, *event.fact_plan.required,
                         *event.fact_plan.unprocessed)),
            f"missing exact source span {article_id} unit {index} [{start},{end})")

    def changed_primary_assertion(self, article_id, variant_id, title, lead, unit_index):
        """Keep the complete natural source, changing only its current claim."""
        row = deepcopy(self.rows[article_id])
        old_title = row["evidence"]["title"]
        old_lead = row["evidence"]["units"][unit_index]["text"]
        def replace_claim(value):
            if isinstance(value, str):
                return value.replace(old_lead, lead).replace(old_title, title)
            if isinstance(value, list):
                return [replace_claim(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_claim(item) for key, item in value.items()}
            return value
        row = replace_claim(row)
        # Extraction summaries can abbreviate the first HTML paragraph, so
        # replace their first assertion independently of the complete unit.
        summary = row["recorded_extraction"][1]
        if not summary.startswith(lead):
            first = next(self.m.source_sentence_spans(summary), (0, len(summary)))
            row["recorded_extraction"][1] = lead + summary[first[1]:]
        row["evidence"]["article_id"] = variant_id
        row["evidence"]["url"] = f"https://fixture.example/current-claim/{variant_id}"
        self.rows = {**self.rows, variant_id: row}
        return self.source_articles(variant_id)

    def test_n1_recap_and_rumor_source_forms_do_not_project_current_actions(self):
        for article_id in ("64f6c27cb86bf374c42122de",
                           "602d05ed00dcb51064786cf6",
                           "1d809c26d570f866dae79a66"):
            with self.subTest(article_id=article_id):
                events, _data = self.cluster_sources(article_id)
                self.assertTrue(events)
                self.assertTrue(all(event.relevance_tier == "weak" for event in events))
                self.assertFalse(any("roadmap update" in event.title.casefold()
                    for event in events))
                if article_id == "64f6c27cb86bf374c42122de":
                    selected = " ".join(fact.text for event in events
                        for fact in (*event.fact_plan.facts, *event.fact_plan.required))
                    self.assertNotIn("Sponsored by Stuff", selected)
                    self.assertNotIn("Subscribe to our podcast", selected)

    def test_n1_reader_poll_stays_separate_from_current_beta_report(self):
        report = "c1a610770f434bed77944a92"
        poll = "d32211a2440d5be951e0019f"
        events, _data = self.cluster_sources(report, poll)
        report_event = next(event for event in events if report in self.source_ids(event))
        self.assertEqual(report_event.relevance_tier, "strong")
        self.assertNotIn(poll, self.source_ids(report_event))
        self.assertNotIn("互动", report_event.title)
        poll_event = next(event for event in events if poll in self.source_ids(event))
        self.assertEqual(poll_event.relevance_tier, "weak")
        self.assert_source_span(poll_event, poll, 2)
        self.assertFalse(any("评论区中提供 App 名称" in fact.text
            for fact in poll_event.fact_plan.required))

    def test_n2_screenshot_code_discovery_is_one_unreleased_action(self):
        ids = ("9aef2f5f43481c0aeb28c453", "591329ad30c10b8e4dac2f0c",
               "d384b1573faf1266d844dbe3")
        events, _data = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), set(ids))
        self.assertEqual((event.relevance_tier, event.category), ("strong", "software_systems"))
        self.assert_source_span(event, ids[0], 2)
        # The first sentence states the uncertain beta stage; the next is
        # the author's separate prediction and has no release authority.
        self.assert_source_span(event, ids[2], 8, end=130)
        for article_id in ids:
            for article in self.source_articles(article_id):
                self.assertIn("primary-claim-predicate:feature-flag-code-discovery",
                    self.m.article_reconciliation_profile(article).separation_keys)

    def test_n2_hidden_screenshot_code_does_not_join_available_watch_face(self):
        code = ("9aef2f5f43481c0aeb28c453", "591329ad30c10b8e4dac2f0c",
                "d384b1573faf1266d844dbe3")
        face = ("c6fc956dfb1af4f411593c4c", "e627e27d94afb8738e2862ca")
        events, _data = self.cluster_sources(*code, *face)
        self.assertEqual({frozenset(self.source_ids(event)) for event in events},
            {frozenset(code), frozenset(face)})

    def test_n2_head_trip_free_livestream_joins_across_languages(self):
        ids = ("f42f1a25f72a5e9f1554f4ac", "351831c853785c565e11677c")
        events, _data = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), set(ids))
        self.assertEqual((event.relevance_tier, event.category), ("strong", "software_systems"))
        self.assert_source_span(event, ids[0], 4)
        self.assert_source_span(event, ids[1], 4)

    def test_n2_parental_control_video_joins_without_relaunching_features(self):
        ids = ("57915fbdf9ace90fe7d5379d", "72b2edb13547f8dbd59f1203",
               "f49eb4b8d19a29ba690eae6a")
        events, _data = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), set(ids))
        self.assertEqual((event.relevance_tier, event.category), ("strong", "software_systems"))
        self.assert_source_span(event, ids[1], 6, start=0, end=129)
        self.assert_source_span(event, ids[1], 6, start=130, end=244)
        for article_id in ids:
            for article in self.source_articles(article_id):
                self.assertIn("primary-claim-predicate:current-explainer-video",
                    self.m.article_reconciliation_profile(article).separation_keys)
        self.assertFalse(any("WWDC 2013" in fact.text
            for fact in event.fact_plan.facts))

    def test_n3_readiness_bezel_is_software_with_exact_display_mechanism(self):
        ids = ("c6fc956dfb1af4f411593c4c", "e627e27d94afb8738e2862ca")
        events, _data = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), set(ids))
        self.assertEqual((event.relevance_tier, event.category), ("strong", "software_systems"))
        self.assert_source_span(event, ids[0], 11)
        self.assert_source_span(event, ids[0], 12)

    def test_n3_macos_support_removal_joins_with_version_limits(self):
        ids = ("ad8facf06ae36e3e680e18d9", "4a7586f82090d938510a5093")
        events, _data = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), set(ids))
        self.assertEqual((event.relevance_tier, event.category), ("strong", "software_systems"))
        self.assert_source_span(event, ids[0], 5)
        self.assert_source_span(event, ids[0], 9)
        self.assertFalse(any("macOS 27" in fact.text and "drop support for Rosetta 2" in fact.text
            for fact in event.fact_plan.facts))

    def test_n4_knife_edge_host_and_production_credit_reach_the_work(self):
        article_id = "f1fa46511cdbfe802763a87f"
        events, _data = self.cluster_sources(article_id)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), {article_id})
        self.assert_source_span(event, article_id, 3)

    def test_new_source_local_actions_require_current_affirmative_stage(self):
        cases = (
            ("f42f1a25f72a5e9f1554f4ac", 1,
             "Apple Music Cancels Head Trip Festival Livestream",
             "Apple Music has cancelled its planned livestream of the Head Trip music festival with Goldenvoice in Indio, California, on October 10 and 11.",
             "livestream-announcement"),
            ("9aef2f5f43481c0aeb28c453", 1,
             "watchOS 27.2 Has No Screenshot Preview Code",
             "Code explorer pdfu found no screenshot preview, share, or delete feature flag in watchOS 27.2.",
             "feature-flag-code-discovery"),
            ("9aef2f5f43481c0aeb28c453", 1,
             "watchOS 27.2 Releases Screenshot Previews for Apple Watch",
             "Apple has released screenshot previews in watchOS 27.2, with options to share or delete after taking a screenshot.",
             "feature-flag-code-discovery"),
            ("57915fbdf9ace90fe7d5379d", 0,
             "Apple's Earlier Child Accounts Video Resurfaces",
             "Earlier this year, Apple shared a video about iOS 27 Child Accounts and parental controls.",
             "current-explainer-video"),
            ("57915fbdf9ace90fe7d5379d", 0,
             "Apple Has Not Shared a New iOS 27 Parental Controls Video",
             "Apple has not shared a new video about iOS 27 Child Accounts and parental controls.",
             "current-explainer-video"),
            ("c6fc956dfb1af4f411593c4c", 0,
             "Apple Watch Ultra 4 Does Not Include a New Readiness Watch Face Bezel Option",
             "Apple Watch Ultra 4 does not include a new Readiness bezel option for its watch face.",
             "configuration-added"),
            ("ad8facf06ae36e3e680e18d9", 1,
             "macOS Golden Gate Has Not Removed Legacy Support",
             "Apple has not removed Intel Mac or Boot Camp support in macOS Golden Gate.",
             "current-removal"),
        )
        for index, (source_id, unit_index, title, lead, action) in enumerate(cases, 1):
            with self.subTest(title=title):
                variant_id = f"{index:024x}"
                original = self.source_articles(source_id)
                changed = self.changed_primary_assertion(
                    source_id, variant_id, title, lead, unit_index)
                self.assertEqual(len(changed), 1)
                profile = self.m.article_reconciliation_profile(changed[0])
                self.assertNotIn(f"primary-claim-predicate:{action}", profile.separation_keys)
                if action in {"livestream-announcement", "configuration-added"}:
                    alternate = ("livestream-cancellation" if action == "livestream-announcement"
                        else "configuration-denied")
                    self.assertIn(f"primary-claim-predicate:{alternate}", profile.separation_keys)
                events = self.m.cluster_articles([*original, *changed])
                self.assertEqual({frozenset(self.source_ids(event)) for event in events},
                    {frozenset({source_id}), frozenset({variant_id})})


if __name__ == "__main__":
    unittest.main()
