import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


class DeveloperSubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("developer_submission_test", SCRIPT_PATH)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def detail(self):
        m = self.module
        source = m.Source("9to5Mac", "UTC")
        candidate = m.Candidate(
            source.name,
            "https://example.com/developer-proposals",
            "Apple invites developers to submit browser interoperability ideas",
        )
        page = """<html><head>
        <title>Apple invites developers to submit ideas for Interop 2027</title>
        <meta property="article:published_time" content="2026-09-07T20:31:22Z">
        </head><body><article>
        <p>Apple's WebKit team is inviting developers to submit their ideas for
        Interop 2027, the next edition of the cross-browser initiative aimed at
        improving web interoperability.</p>
        <p>Apple has collaborated with Google, Microsoft, Mozilla, Bocoup, and
        Igalia on Interop, an annual effort to improve browser interoperability.</p>
        <p>The call is open through September 23. Proposals must use mature web
        standards and include Web Platform Tests to measure interoperability.</p>
        </article></body></html>"""
        title, summary, facts, published, *_ = m.extract_article(candidate, source, page, {})
        self.assertEqual(published, datetime(2026, 9, 7, 20, 31, 22, tzinfo=timezone.utc))
        self.assertIn("Microsoft", summary)
        return source, m.Candidate(source.name, candidate.url, title, summary), facts

    def test_extracted_detail_survives_partner_background(self):
        source, candidate, facts = self.detail()
        self.assertTrue(self.module.is_relevant_candidate(candidate, source, facts))

    def test_extracted_detail_is_strong(self):
        source, candidate, facts = self.detail()
        tier, reason = self.module.classify_relevance_tier(
            candidate.title, candidate.summary, facts, source.name
        )
        self.assertEqual(tier, "strong", reason)

    def test_extracted_detail_stays_strong_after_reconciliation(self):
        m = self.module
        source, candidate, facts = self.detail()
        tier, reason = m.classify_relevance_tier(candidate.title, candidate.summary, facts, source.name)
        article = m.Article(
            source.name, candidate.url, candidate.title, candidate.summary, facts,
            m.choose_category(candidate.title, candidate.summary),
            datetime(2026, 9, 7, 20, 31, 22, tzinfo=timezone.utc),
            "2026-09-07T20:31:22Z", "detail", "detail",
            m.article_tokens(candidate.title, candidate.summary),
            m.detect_event_kind(candidate.title, candidate.summary, facts), tier, reason,
        )
        events = m.cluster_articles([article])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual([a.url for a in events[0].articles], [candidate.url])

    def test_partner_name_does_not_change_admission_or_tier(self):
        source, candidate, facts = self.detail()
        for summary in [candidate.summary, candidate.summary.replace("Microsoft, ", "")]:
            with self.subTest(summary=summary):
                candidate.summary = summary
                self.assertTrue(self.module.is_relevant_candidate(candidate, source, facts))
                self.assertEqual(self.module.classify_relevance_tier(
                    candidate.title, summary, facts, source.name
                )[0], "strong")

    def test_submission_action_is_not_project_or_year_specific(self):
        for title, lead in [
            ("Apple invites developers to submit ideas for Browser Focus 2029",
             "Apple's WebKit team is inviting developers to submit proposals for browser interoperability."),
            ("WebKit invites developers to submit proposals for Browser Focus 2030",
             "WebKit invites developers to submit proposals based on web standards and browser interoperability tests."),
            ("苹果公开征集浏览器互操作性提案", "苹果 WebKit 团队邀请开发者提交网页标准互操作性提案。"),
        ]:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, lead, [], "9to5Mac")
                self.assertEqual(tier, "strong", reason)

    def test_third_party_submission_is_not_apple_action(self):
        title = "Independent browser group invites developers to submit ideas"
        lead = "An independent group invites developers to submit browser interoperability proposals for Apple WebKit."
        tier, reason = self.module.classify_relevance_tier(title, lead, [], "9to5Mac")
        self.assertNotEqual(tier, "strong", reason)

    def test_historical_call_is_not_current_action(self):
        title = "Looking back at the browser interoperability proposal process"
        lead = "In 2022, Apple invited developers to submit browser interoperability proposals. The old call is closed."
        tier, reason = self.module.classify_relevance_tier(title, lead, [], "9to5Mac")
        self.assertNotEqual(tier, "strong", reason)

    def test_background_call_cannot_supply_headline_action(self):
        title = "Independent group invites developers to submit browser proposals"
        lead = "Apple invites developers to submit browser interoperability ideas in a separate WebKit program."
        self.assertFalse(self.module.is_apple_led_developer_submission_story(title, lead))

    def test_non_browser_submission_is_not_this_exception(self):
        title = "Apple invites developers to submit app ideas"
        lead = "Apple invites developers to submit app ideas for its design contest."
        self.assertFalse(self.module.is_apple_led_developer_submission_story(title, lead))

    def test_historical_and_negated_headline_calls_are_not_this_exception(self):
        lead = "Apple's WebKit team invited developers to submit browser interoperability proposals."
        for title in [
            "Apple invited developers to submit ideas for Interop 2022",
            "Apple invites developers to submit ideas: historical recap",
            "Apple is not inviting developers to submit browser proposals",
        ]:
            with self.subTest(title=title):
                self.assertFalse(self.module.is_apple_led_developer_submission_story(title, lead))


if __name__ == "__main__":
    unittest.main()
