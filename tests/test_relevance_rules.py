import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_24h_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_named(module, name):
    return next(source for source in module.build_sources(datetime.now().astimezone()) if source.name == name)


class RelevanceRuleTests(unittest.TestCase):
    def test_apple_watch_health_data_research_is_relevant_and_software_category(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/05/28/apple-watch-sleep-data-helps-harvard-researchers-study-menopause-transition/",
            title="Apple Watch sleep data helps Harvard researchers study menopause transition",
            summary=(
                "Researchers at Harvard have published the results of a study that analyzed "
                "more than 94,000 nights of Apple Watch sleep data to better understand how "
                "sleep patterns change during perimenopause."
            ),
            feed_time_raw="Thu, 28 May 2026 22:43:28 +0000",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_generic_apple_watch_sleep_advice_remains_filtered(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/example/apple-watch-sleep-tips/",
            title="Apple Watch sleep tips for better bedtime routines",
            summary="A guide to using Apple Watch sleep features more comfortably every night.",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))

    def test_related_article_title_is_not_key_fact(self):
        module = load_module()

        self.assertFalse(
            module.is_key_fact("h2", "iOS 27 leak reveals new Siri design, Camera app, more")
        )


if __name__ == "__main__":
    unittest.main()
