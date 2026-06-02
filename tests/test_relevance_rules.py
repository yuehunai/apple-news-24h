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

    def test_market_share_shipment_story_is_relevant_hardware_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/01/counterpoint-iphone-shipments-grew-8-in-latin-america-during-q1/",
            title="Counterpoint: iPhone shipments grew 8% in Latin America during Q1",
            summary=(
                "A new Counterpoint Research report shows Apple saw iPhone shipments grow "
                "8% year over year in Latin America during Q1 2026."
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "hardware_products")

    def test_apple_tv_quality_ranking_is_relevant_service_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/01/apple-tv-ranks-higher-than-netflix-in-new-quality-ranking/",
            title="Apple TV ranks higher than Netflix in new quality ranking",
            summary=(
                "Research firm MoffetNathanson has developed a new quality index for "
                "streaming services, and Apple TV beat out Netflix in the first rankings."
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_apple_tv_original_film_casting_is_relevant_service_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/01/zoe-kravitz-to-star-in-upcoming-untitled-apple-tv-movie/",
            title="Zoë Kravitz to star in upcoming untitled Apple TV movie",
            summary=(
                "Apple TV confirmed that Zoë Kravitz will star in a new Apple Original "
                "Film from writer and director Megan Park and LuckyChap."
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_apple_retail_store_business_action_is_hardware_category(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/958/424.htm",
            title="疑似苹果 Apple Store 西安万象城零售店进行申报",
            summary=(
                "陕西政务服务网显示，名称为西安万象城购物中心苹果店室内装修及幕墙改造工程的项目"
                "于 2026 年 6 月 1 日进行申报。"
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "hardware_products")

    def test_source_configuration_includes_required_apple_channels(self):
        module = load_module()
        sources = {source.name: source for source in module.build_sources(datetime.now().astimezone())}

        self.assertIn("https://www.theverge.com/rss/apple/index.xml", sources["The Verge"].feeds)
        self.assertIn("https://www.ithome.com/apple/", sources["IT之家"].pages)

    def test_html_link_parser_keeps_late_apple_homepage_links(self):
        module = load_module()
        source = source_named(module, "IT之家")
        early_links = "".join(
            f'<a href="https://www.ithome.com/0/958/{index:03d}.htm">普通科技新闻 {index}</a>'
            for index in range(100)
        )
        html = (
            early_links
            + '<a href="https://www.ithome.com/0/958/424.htm">'
            + "疑似苹果 Apple Store 西安万象城零售店进行申报</a>"
        )

        candidates = module.parse_html_links(html, "https://www.ithome.com/", source)

        self.assertTrue(any(candidate.url.endswith("/0/958/424.htm") for candidate in candidates))

    def test_non_official_related_headings_do_not_become_key_facts(self):
        module = load_module()
        html = """
        <article>
          <h1>MacBook Neo rival launched at $599</h1>
          <p>Dell launched a new rival to Apple's MacBook Neo at the same price.</p>
          <h3>Report: New Apple TV, HomePod mini set to launch this fall; Siri Remote refresh possible</h3>
        </article>
        """

        self.assertEqual(module.extract_key_facts(html, "MacBook Neo rival launched at $599", "9to5Mac"), [])


if __name__ == "__main__":
    unittest.main()
