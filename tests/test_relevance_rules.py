import importlib.util
import sys
import unittest
from datetime import datetime, timezone
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


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = facts or []
    event_kind = module.detect_event_kind(title, summary, facts)
    relevance_tier, relevance_reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{abs(hash(title))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 6, 4, 0, 0, tzinfo=timezone.utc),
        published_raw="2026-06-04T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=event_kind,
        relevance_tier=relevance_tier,
        relevance_reason=relevance_reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


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

    def test_evergreen_guide_urls_are_filtered(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/guide/apple-store/",
            title="Apple Store",
            summary="Apple Store articles on MacRumors.com",
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

    def test_app_store_legal_developer_and_regional_stories_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Agrees to Hand Over Financial Data to India's Antitrust Regulator",
                "India's competition regulator is investigating App Store billing and asked Apple for financial data.",
            ),
            article_for(
                module,
                "Texas App Store age assurance law raises new compliance questions",
                "A Texas state law would require App Store age verification and new child safety compliance steps.",
            ),
            article_for(
                module,
                "Apple opens first European Developer Center in Berlin",
                "Apple announced a Berlin developer center for European app makers and developer education.",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)
        self.assertEqual(
            {event.event_kind for event in events},
            {"legal_antitrust", "regional_regulation", "developer_program"},
        )

    def test_quick_share_airdrop_story_is_ecosystem_relevant(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/example/google-quick-share-airdrop/",
            title="Google Quick Share could soon work with AirDrop on iPhone",
            summary="Code suggests cross-platform file sharing interoperability with Apple's AirDrop.",
        )

        tier, reason = module.classify_relevance_tier(candidate.title, candidate.summary, [], candidate.source)

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "ecosystem_interop")
        self.assertEqual(tier, "ecosystem")
        self.assertIn("interoperability", reason)
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_chinese_quick_share_airdrop_story_is_ecosystem_relevant(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/example/quick-share-airdrop.htm",
            title="谷歌 Pixel 机型现已支持苹果隔空投送",
            summary="谷歌 Quick Share 目前已支持与苹果隔空投送互通，让安卓手机能够和 iPhone、iPad、Mac 无缝传文件。",
        )

        tier, _ = module.classify_relevance_tier(candidate.title, candidate.summary, [], candidate.source)

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "ecosystem_interop")
        self.assertEqual(tier, "ecosystem")
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_ios_compatibility_wallet_features_and_hardware_rumors_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "These iPhones, iPads, Macs may not support Apple’s new software",
                "iOS 27, iPadOS 27, and macOS 27 compatibility may drop support for older devices.",
            ),
            article_for(
                module,
                "iOS 27 will reportedly add two major new features to Apple Wallet",
                "Apple Wallet may add digital passport support and expanded ID features in iOS 27.",
            ),
            article_for(
                module,
                "New iPads will launch later this year, here’s what rumors say is coming",
                "Apple is expected to launch new iPad models later this year.",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)
        self.assertEqual(
            {event.event_kind for event in events},
            {"os_compatibility", "wallet_feature", "hardware_market"},
        )

    def test_competitor_hardware_comparison_is_deferred_as_weak(self):
        module = load_module()

        tier, reason = module.classify_relevance_tier(
            "NVIDIA launches AI PC compared with Apple's Mac mini",
            "NVIDIA's new desktop is positioned as a compact AI PC rival to the Mac mini.",
            [],
            "cnBeta",
        )

        self.assertEqual(tier, "weak")
        self.assertIn("third-party", reason)

    def test_chinese_competitor_hardware_comparison_is_deferred_as_weak(self):
        module = load_module()

        tier, reason = module.classify_relevance_tier(
            "硬刚苹果！华为 Mate 新机首发麒麟芯片",
            "华为新旗舰将在 9 月发布，并与苹果 iPhone 形成竞品关系。",
            [],
            "快科技",
        )

        self.assertEqual(tier, "weak")
        self.assertIn("third-party", reason)

    def test_third_party_mac_app_availability_is_deferred_as_weak(self):
        module = load_module()

        tier, reason = module.classify_relevance_tier(
            "Google AI Edge Gallery launches to macOS for Mac users",
            "Google's experimental app lets Apple Mac users run Gemma models locally.",
            [],
            "IT之家",
        )

        self.assertEqual(tier, "weak")
        self.assertIn("third-party app", reason)

    def test_routine_product_ad_is_deferred_but_privacy_campaign_remains_strong(self):
        module = load_module()

        beats_tier, _ = module.classify_relevance_tier(
            "Apple's New Beats Pill Ad Leans Into Reality TV Show",
            "Apple shared a new Beats Pill advertisement referencing Love Island USA.",
            [],
            "MacRumors",
        )
        privacy_tier, _ = module.classify_relevance_tier(
            "Apple kicks off new Privacy on iPhone campaign promoting Safari",
            "Apple released a Safari privacy campaign about web tracking protection.",
            [],
            "9to5Mac",
        )

        self.assertEqual(beats_tier, "weak")
        self.assertEqual(privacy_tier, "strong")

    def test_third_party_vision_pro_app_is_deferred_as_weak(self):
        module = load_module()

        tier, reason = module.classify_relevance_tier(
            "Cirrus launches free native app for Apple Vision Pro",
            "The third-party Vision Pro app lets users watch a private flight demonstration.",
            [],
            "IT之家",
        )

        self.assertEqual(module.detect_event_kind("Cirrus launches free native app for Apple Vision Pro", "The third-party Vision Pro app lets users watch a private flight demonstration."), "third_party_ecosystem")
        self.assertEqual(tier, "weak")
        self.assertIn("third-party", reason)

    def test_related_blocks_are_removed_before_key_fact_extraction(self):
        module = load_module()
        html = """
        <article>
          <p>Apple said the iOS update fixes 12 vulnerabilities and supports 3 device models.</p>
          <div class="related-posts">
            <p>Counterpoint says iPhone shipments grew 8% in Latin America during Q1 2026.</p>
          </div>
        </article>
        """

        facts = module.extract_key_facts(html, "Apple releases iOS security update", "9to5Mac")

        self.assertTrue(any("12 vulnerabilities" in fact for fact in facts))
        self.assertFalse(any("Counterpoint" in fact for fact in facts))

    def test_service_privacy_and_retail_categories_follow_output_taxonomy(self):
        module = load_module()

        self.assertEqual(
            module.choose_category(
                "Apple privacy ad highlights Safari tracking protections",
                "Apple released a privacy campaign about Safari protections on iPhone.",
            ),
            "software_systems",
        )
        self.assertEqual(
            module.choose_category(
                "Apple Store in Yokohama reopens after renovation",
                "Apple's retail store in Yokohama will reopen with updated product areas.",
            ),
            "hardware_products",
        )
        self.assertEqual(
            module.choose_category(
                "John Ternus scaled back Apple’s Vision products roadmap",
                "Apple's product roadmap now focuses more on smart glasses than the Vision Pro series.",
            ),
            "hardware_products",
        )

    def test_render_markdown_keeps_source_links(self):
        module = load_module()
        data = {
            "events": [
                {
                    "category": "software_systems",
                    "title": "Apple Wallet adds new features",
                    "summary": "Apple Wallet adds new features in iOS 27.",
                    "key_facts": [],
                    "sources": [
                        {
                            "name": "9to5Mac",
                            "url": "https://9to5mac.com/2026/06/03/ios-27-will-reportedly-add-two-major-new-features-to-apple-wallet/",
                        }
                    ],
                }
            ],
            "deferred_events": [],
        }

        markdown = module.render_markdown(data)

        self.assertIn(
            "（来源：[9to5Mac](https://9to5mac.com/2026/06/03/ios-27-will-reportedly-add-two-major-new-features-to-apple-wallet/)）",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
