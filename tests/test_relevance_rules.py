import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


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

    def test_ithome_ad_tips_do_not_make_article_marketing_ad(self):
        module = load_module()
        source = source_named(module, "IT之家")
        page = """
        <html>
          <head>
            <meta name="description" content="苹果为 WWDC26 参会者准备了包含托特包、水杯、贴纸套装和珐琅徽章的礼品礼包。苹果开发者 App 也上线了同款主题虚拟贴纸。" />
          </head>
          <body>
            <h1>苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章</h1>
            <span id="pubtime_baidu">2026/6/8 6:56:55</span>
            <div id="paragraph">
              <p>IT之家 6 月 8 日消息，苹果推出了“小小访达精灵（Lil Finder Guy）”实体徽章。这个可爱的吉祥物以 Mac 系统的访达功能为原型，最初亮相于 MacBook Neo 的宣传活动中。</p>
              <p>IT之家注意到，今年的礼包内含托特包、水杯、贴纸套装以及珐琅徽章。苹果也在本年度的苹果开发者 App 内上线了同款主题虚拟贴纸，以此呼应这些趣味形象。</p>
              <p class="ad-tips">广告声明：文内含有的对外跳转链接（包括不限于超链接、二维码、口令等形式），用于传递更多信息，节省甄选时间，结果仅供参考，IT之家所有文章均包含本声明。</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/961/195.htm",
            title="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        tier, reason = module.classify_relevance_tier(title, summary, facts, "IT之家")

        self.assertNotIn("广告声明", summary)
        self.assertNotEqual(module.detect_event_kind(title, summary, facts), "marketing_ad")
        self.assertEqual(tier, "strong", reason)

    def test_9to5_related_and_subscription_copy_do_not_enter_summary_or_facts(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-06-08T01:00:00+00:00" />
            <meta property="og:description" content="Apple is preparing a new Wallet feature for iOS 27 that will let users manage more identity and travel documents." />
          </head>
          <body>
            <article>
              <h1>iOS 27 will reportedly add two major new features to Apple Wallet</h1>
              <p>Apple is preparing a new Wallet feature for iOS 27 that will let users manage more identity and travel documents.</p>
              <div class="related-guide">
                <p class="related-guide__desc">iOS is Apple's mobile operating system that runs on the iPhone and iPod touch.</p>
              </div>
              <div class="newsletter-signup">
                <p>Subscribe to 9to5Mac on YouTube for more Apple news and reviews.</p>
              </div>
            </article>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/03/ios-27-wallet-features/",
            title="iOS 27 will reportedly add two major new features to Apple Wallet",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})

        combined = " ".join([summary, *facts])
        self.assertNotIn("related-guide", combined)
        self.assertNotIn("mobile operating system", combined)
        self.assertNotIn("Subscribe to 9to5Mac", combined)

    def test_9to5_post_content_is_preferred_over_sidebar_article_cards(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-06-08T20:34:43+00:00" />
            <meta property="og:description" content="Apple unveiled iOS 27 today during its WWDC keynote, here's what's new for the Wallet app." />
          </head>
          <body>
            <article class="article feature sidebar flex is-clickable-card">
              <h3>Apple officially announces iOS 27, the next major iPhone update</h3>
            </article>
            <div id="content" class="container flex-lg">
              <div class="container med post-content">
                <p>Apple Wallet is continually improving, and iOS 27 will bring more new features to Wallet users.</p>
                <p><strong>Create a Pass</strong> is a new feature inside iOS 27's Wallet app that lets users turn physical cards and tickets into Wallet passes.</p>
                <ol>
                  <li>Scan a physical pass to import it using the iPhone camera and Visual Intelligence.</li>
                  <li>Create a pass manually with Standard, Membership, and Event options.</li>
                </ol>
              </div>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/08/heres-everything-new-for-apple-wallet-in-ios-27/",
            title="Here's everything new for Apple Wallet in iOS 27",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("Create a Pass", combined)
        self.assertIn("Standard, Membership, and Event", combined)
        self.assertNotIn("Apple officially announces iOS 27", combined)

    def test_selected_candidate_with_feed_time_survives_detail_fetch_failure(self):
        module = load_module()
        source = module.Source(
            name="IT之家",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ithome.com/rss/"],
            pages=[],
            domains=("ithome.com", "www.ithome.com"),
        )
        feed = """
        <rss><channel><item>
          <title>苹果 iOS 27 悄悄更新中文输入法：标点建议和联想词更准确，找生僻字更方便</title>
          <link>https://www.ithome.com/0/961/716.htm</link>
          <description><![CDATA[
            IT之家 6 月 9 日消息，苹果今日正式公布了 iOS 27 系统更新。iOS 27 悄悄更新优化了中文输入法，带来中文标点建议，根据上下文联想词语的准确度也得到了提升。此外，iOS 27 的输入法优化了汉字拆字逻辑，用户可以通过输入两个部分的拼音，来查找一个生僻字。
          ]]></description>
          <pubDate>Mon, 08 Jun 2026 22:16:48 GMT</pubDate>
        </item></channel></rss>
        """
        original_build_sources = module.build_sources
        original_fetch_url = module.fetch_url
        module.build_sources = lambda _now_local: [source]

        def fake_fetch_url(url, _cache_dir, diagnostics, *_args, **_kwargs):
            if url == "https://www.ithome.com/rss/":
                return feed
            diagnostics.setdefault("failed_fetches", []).append(
                {"url": url, "error": "TimeoutError: simulated detail fetch failure"}
            )
            return None

        module.fetch_url = fake_fetch_url
        args = type(
            "Args",
            (),
            {
                "timeout": 1.0,
                "retries": 0,
                "timezone": "UTC",
                "hours": 24 * 3650,
                "cache_dir": "",
                "max_detail_pages": 300,
                "include_diagnostics": True,
            },
        )()

        try:
            with TemporaryDirectory() as cache_dir:
                args.cache_dir = cache_dir
                data = module.run(args)
        finally:
            module.build_sources = original_build_sources
            module.fetch_url = original_fetch_url

        titles = [event["title"] for event in data["events"]]
        self.assertTrue(any("中文输入法" in title for title in titles))
        self.assertEqual(data["diagnostics"]["selected_detail_fetch_failures"][0]["source"], "IT之家")

    def test_ithome_listing_summary_is_attached_to_html_candidate(self):
        module = load_module()
        source = source_named(module, "IT之家")
        page = """
        <ul class="bl">
          <li>
            <a href="https://www.ithome.com/0/961/195.htm" target="_blank" class="img">
              <img alt="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章" />
            </a>
            <div class="c" data-ot="2026-06-08T06:56:55.3100000+08:00">
              <h2>
                <a title="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章" target="_blank" href="https://www.ithome.com/0/961/195.htm" class="title">苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章</a>
              </h2>
              <div class="m">苹果为 WWDC26 参会者准备了包含托特包、水杯、贴纸套装和珐琅徽章的礼品礼包。苹果开发者 App 也上线了同款主题虚拟贴纸。</div>
            </div>
          </li>
        </ul>
        """

        candidates = module.parse_html_links(page, "https://www.ithome.com/apple/", source)
        target = next(item for item in candidates if item.url == "https://www.ithome.com/0/961/195.htm")

        self.assertIn("苹果开发者 App", target.summary)
        self.assertEqual(target.feed_time_raw, "2026-06-08T06:56:55.3100000+08:00")
        self.assertTrue(module.is_relevant_candidate(target, source))

    def test_wwdc_apple_gift_reveal_title_is_relevant_without_listing_summary(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/961/195.htm",
            title="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))

    def test_wwdc_candidate_gets_detail_priority_bonus(self):
        module = load_module()
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/961/195.htm",
            title="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章",
            summary="苹果为 WWDC26 参会者准备了包含托特包、水杯、贴纸套装和珐琅徽章的礼品礼包。",
        )

        self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 70)

    def test_collect_candidates_prefers_richer_ithome_duplicate_listing(self):
        module = load_module()
        source = module.Source(
            name="IT之家",
            default_tz="Asia/Shanghai",
            feeds=[],
            pages=["https://www.ithome.com/", "https://www.ithome.com/apple/"],
            domains=("ithome.com", "www.ithome.com"),
        )
        compact_page = """
        <ul class="nl">
          <li class="n"><a href="https://www.ithome.com/0/961/195.htm" target="_blank">苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章</a><b>06:56</b></li>
        </ul>
        """
        rich_page = """
        <ul class="bl">
          <li>
            <a href="https://www.ithome.com/0/961/195.htm" target="_blank" class="img"><img alt="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章" /></a>
            <div class="c" data-ot="2026-06-08T06:56:55.3100000+08:00">
              <h2><a title="苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章" target="_blank" href="https://www.ithome.com/0/961/195.htm" class="title">苹果 WWDC26 参会礼品曝光：内含“小小访达精灵”实体徽章</a></h2>
              <div class="m">苹果为 WWDC26 参会者准备了包含托特包、水杯、贴纸套装和珐琅徽章的礼品礼包。苹果开发者 App 也上线了同款主题虚拟贴纸。</div>
            </div>
          </li>
        </ul>
        """
        original_fetch_url = module.fetch_url
        module.fetch_url = lambda url, *_args, **_kwargs: {
            "https://www.ithome.com/": compact_page,
            "https://www.ithome.com/apple/": rich_page,
        }.get(url)

        try:
            with TemporaryDirectory() as cache_dir:
                candidates = module.collect_candidates(
                    source,
                    Path(cache_dir),
                    {"failed_sources": [], "source_candidate_counts": {}},
                )
        finally:
            module.fetch_url = original_fetch_url

        self.assertEqual(len(candidates), 1)
        self.assertIn("苹果开发者 App", candidates[0].summary)
        self.assertEqual(candidates[0].feed_time_raw, "2026-06-08T06:56:55.3100000+08:00")

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

    def test_9to5_feed_category_context_makes_apple_tv_casting_relevant(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        feed = """
        <rss><channel><item>
          <title>Your Friends &amp; Neighbors adds yet another star for season 3</title>
          <link>https://9to5mac.com/2026/06/04/your-friends-neighbors-adds-yet-another-star-for-season-3/</link>
          <description><![CDATA[
            <p>Apple TV's acclaimed drama continues building out its season 3 cast.</p>
            <span data-layer-postcategory="apple-tv"></span>
          ]]></description>
          <pubDate>Thu, 04 Jun 2026 18:30:00 +0000</pubDate>
        </item></channel></rss>
        """

        candidates = module.parse_xml_feed(feed, source, "https://9to5mac.com/feed/")

        self.assertEqual(len(candidates), 1)
        self.assertIn("apple tv", candidates[0].context)
        self.assertTrue(module.is_relevant_candidate(candidates[0], source))
        self.assertEqual(
            module.detect_event_kind(candidates[0].title, f"{candidates[0].summary} {candidates[0].context}"),
            "service_content",
        )
        self.assertEqual(
            module.choose_category(candidates[0].title, f"{candidates[0].summary} {candidates[0].context}"),
            "software_systems",
        )

    def test_messages_platform_ai_agent_is_relevant_strong_software_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/04/apples-messages-app-on-iphone-now-has-a-third-party-ai-agent/",
            title="Apple’s Messages app on iPhone now has a third-party AI agent",
            summary=(
                "Poke says Apple approved its proactive AI assistant for Messages for Business, "
                "letting iPhone users ask it to manage messages and reminders."
            ),
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "messages_platform")
        self.assertEqual(tier, "strong")
        self.assertIn("Messages", reason)
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_ithome_messages_platform_title_is_relevant_without_summary(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/960/194.htm",
            title="苹果批准首个 iMessage AI 智能体，Poke 可回邮件也能设提醒",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "messages_platform")
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_messages_platform_rule_requires_message_agent_and_action_context(self):
        module = load_module()

        self.assertNotEqual(
            module.detect_event_kind(
                "苹果批准第三方 AI 应用登陆 iPhone",
                "这款应用可在 iOS 上运行，但没有接入 iMessage 或 Apple Messages for Business。",
            ),
            "messages_platform",
        )
        self.assertNotEqual(
            module.detect_event_kind(
                "Poke AI assistant updates its iPhone app",
                "The app mentions Apple Messages but has no approval or integration change.",
            ),
            "messages_platform",
        )

    def test_messages_platform_story_does_not_merge_with_local_ai_app_story(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple’s Messages app on iPhone now has a third-party AI agent",
                "Third-party AI service Poke was approved for use in Apple’s Messages app on iPhone.",
            ),
            article_for(
                module,
                "LM Studio now lets you use your iPhone to talk to local models on your Mac",
                "LM Studio’s Locally app lets users talk to LLMs running on their Macs from iPhones.",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertIn("messages_platform", {event.event_kind for event in events})

    def test_messages_platform_same_poke_event_merges_across_languages(self):
        module = load_module()
        long_background = (
            "The article also explains enterprise messaging workflows, customer service use cases, "
            "startup history, reminder management, calendar coordination, email triage, proactive suggestions, "
            "privacy boundaries, notification behavior, and account setup details."
        )
        articles = [
            article_for(
                module,
                "Apple’s Messages app on iPhone now has a third-party AI agent",
                "Third-party AI service Poke was approved for use in Apple’s Messages app on iPhone, bringing an AI agent directly into iMessage for the first time. "
                + long_background,
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果批准首个 iMessage AI 智能体，Poke 可回邮件也能设提醒",
                "苹果批准 Poke 成为首个接入 Apple Messages for Business 平台的第三方 AI 智能体。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "messages_platform")

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

    def test_local_ai_app_for_iphone_and_mac_is_deferred_as_weak(self):
        module = load_module()

        tier, reason = module.classify_relevance_tier(
            "LM Studio now lets you use your iPhone to talk to local models on your Mac",
            "LM Studio’s Locally app lets users talk to LLMs running on their Macs right from their iPhones.",
            [],
            "9to5Mac",
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

    def test_ithome_related_posts_and_site_footer_do_not_become_key_facts(self):
        module = load_module()
        html = """
        <div class="post_content">
          <p>IT之家 6 月 5 日消息，苹果批准 Poke 成为首个接入 Apple Messages for Business 平台的第三方 AI 智能体。</p>
          <p>IT之家援引博文介绍，Poke 由加州初创公司打造，已在 2026 年 3 月公开发布。</p>
        </div>
        <!-- 相关文章 -->
        <div class="related_post">
          <div class="title"><h2>相关文章</h2></div>
          <ul class="list_3">
            <li><a href="https://www.ithome.com/0/945/784.htm">苹果 FY2026Q2 研发支出 114 亿美元创新高，同比增长 34% 加码 AI</a></li>
            <li><a href="https://www.ithome.com/0/932/734.htm">苹果联合打造 RubiCap 框架：让 AI 描述图像每个细节，性能击败 10 倍体量对手</a></li>
          </ul>
        </div>
        <div id="fls" class="bb">
          <p><strong>软媒旗下网站：</strong> IT之家 最会买 iPhone之家 Win7之家 Win10之家 Win11之家</p>
        </div>
        """

        facts = module.extract_key_facts(html, "苹果批准首个 iMessage AI 智能体", "IT之家")

        self.assertTrue(any("Apple Messages for Business" in fact for fact in facts))
        self.assertFalse(any("FY2026Q2" in fact for fact in facts))
        self.assertFalse(any("RubiCap" in fact for fact in facts))
        self.assertFalse(any("软媒旗下网站" in fact for fact in facts))

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
