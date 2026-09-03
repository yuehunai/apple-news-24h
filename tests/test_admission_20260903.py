import importlib.util
from pathlib import Path
import sys
import unittest
from datetime import datetime
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


class SemanticAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("admission_0903", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.sources = {s.name: s for s in cls.module.build_sources(datetime.now())}

    def candidate(self, title, summary="", source="IT之家"):
        return self.module.Candidate(source, "https://example.com/current-report", title, summary)

    def test_direct_subjects_survive_discovery_without_legacy_action_words(self):
        cases = [
            self.candidate(
                "继谷歌地图后，苹果地图面向美国用户将安大略湖更名为美国湖",
                "苹果地图在美国显示新地名，加拿大用户仍看到原名称。",
            ),
            self.candidate(
                "沃兹尼亚克、乔布斯签名的苹果 Apple I 电脑，有望拍出高价",
                "拍卖行展示可正常工作的早期电脑，并随附原始用户的签名信件。",
            ),
            self.candidate(
                "Apple Shares Apple Watch Survival Story",
                "Apple today shared a short video about a user's diagnosis after Watch alerts.",
                "MacRumors",
            ),
        ]
        for candidate in cases:
            with self.subTest(title=candidate.title):
                self.assertTrue(self.module.is_relevant_candidate(candidate, self.sources[candidate.source]))

    def test_clean_detail_does_not_need_feed_promo_keywords_for_admission(self):
        candidate = self.candidate(
            "Apple Shares Apple Watch Survival Story",
            "Apple today shared a user's story. The medical incident took place two years ago.",
            "MacRumors",
        )
        self.assertTrue(self.module.is_relevant_candidate(candidate, self.sources[candidate.source], []))

    def test_semantic_strong_decision_does_not_depend_on_event_kind_allowlist(self):
        candidate = self.candidate("Apple historical artifact", "An authenticated Apple computer is on display.")
        with patch.object(self.module, "detect_event_kind", return_value="general_company"), patch.object(
            self.module, "classify_relevance_tier", return_value=("strong", "owned subject")
        ):
            self.assertTrue(self.module.is_relevant_candidate(candidate, self.sources[candidate.source]))

    def test_admission_does_not_promote_a_third_party_apple_platform_app(self):
        candidate = self.candidate(
            "Independent iPhone app adds a new timer",
            "A third-party developer updated its app, without any Apple platform change.",
            "9to5Mac",
        )
        self.assertTrue(self.module.is_relevant_candidate(candidate, self.sources[candidate.source]))
        tier, _ = self.module.classify_relevance_tier(candidate.title, candidate.summary, [], candidate.source)
        self.assertEqual(tier, "weak")

    def test_source_roundup_and_non_apple_candidate_stay_excluded(self):
        for candidate in [
            self.candidate("IT 早报：苹果今日动态"),
            self.candidate("A console studio schedules its annual tournament", source="The Verge"),
        ]:
            with self.subTest(title=candidate.title):
                self.assertFalse(self.module.is_relevant_candidate(candidate, self.sources[candidate.source]))

    def test_bare_product_navigation_does_not_consume_detail_budget(self):
        for title in ("Mac mini", "iPhone 18 Pro", "Apple Watch SE 3"):
            candidate = self.module.Candidate("MacRumors", "https://example.com/product", title)
            with self.subTest(title=title):
                self.assertFalse(self.module.is_relevant_candidate(candidate, self.sources[candidate.source]))

    def test_official_communication_preserves_nonnumeric_substantive_facts(self):
        html = (
            "<p>Apple today shared a new video about a customer's use of Apple Watch.</p>"
            "<p>The device prompted a medical visit, where doctors identified a serious condition.</p>"
            "<p>After completing treatment, the person returned to their ordinary daily activities.</p>"
            "<p>Subscribe to our newsletter for more stories and daily deals.</p>"
        )
        facts = self.module.extract_key_facts(html, "Apple Shares Apple Watch Customer Story", "MacRumors")
        self.assertTrue(any("serious condition" in fact for fact in facts))
        self.assertTrue(any("After completing treatment" in fact for fact in facts))
        self.assertFalse(any("Subscribe" in fact for fact in facts))

    def test_personal_story_does_not_gain_official_communication_fact_fallback(self):
        facts = self.module.extract_key_facts(
            "<p>I wanted to share my personal experience with a watch and my daily fitness routine.</p>",
            "My Apple Watch after a year", "MacRumors",
        )
        self.assertEqual(facts, [])


if __name__ == "__main__":
    unittest.main()
