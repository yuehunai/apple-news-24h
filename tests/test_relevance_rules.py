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

    def test_roundup_article_focuses_on_apple_item_instead_of_whole_brief(self):
        module = load_module()
        source = source_named(module, "IT之家")
        page = """
        <html>
          <head>
            <meta name="description" content="IT早报：DeepSeek 完成融资；库克称苹果将因内存芯片短缺涨价；微信支付推 AI 专属卡。" />
            <span id="pubtime_baidu">2026/6/18 07:01:00</span>
          </head>
          <body>
            <h1>IT早报 0618：DeepSeek 以 4000 亿元估值完成首轮融资；库克称苹果将因内存芯片短缺涨价；微信支付推 AI 专属卡...</h1>
            <div id="paragraph">
              <p>“IT早报”时间，大家好，现在是 2026 年 6 月 18 日星期四，今天的重要科技资讯有：</p>
              <p>1、DeepSeek 以 4000 亿元估值完成首轮外部融资：510 亿元到账，投资方含腾讯、宁德时代、京东、网易等。</p>
              <p>3、库克：AI 浪潮引发存储芯片价格暴涨，iPhone 等苹果产品涨价已“不可避免”。华尔街日报报道称，苹果 CEO Tim Cook 确认苹果公司为应对 AI 需求导致的存储芯片成本飙升，计划上调产品售价。</p>
              <p>4、给 Agent 留的指定“办事钱包”：微信支付 AI 专属卡发布，实现从智能推荐到下单支付的自动化消费。</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/965/709.htm",
            title="IT早报 0618：DeepSeek 以 4000 亿元估值完成首轮融资；库克称苹果将因内存芯片短缺涨价；微信支付推 AI 专属卡...",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([title, summary, *facts])

        self.assertIn("库克", title)
        self.assertIn("苹果", combined)
        self.assertIn("涨价", combined)
        self.assertNotIn("DeepSeek", combined)
        self.assertNotIn("微信支付", combined)

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

    def test_9to5_trailing_affiliate_recommendations_do_not_enter_article_facts(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-06-09T20:00:00+00:00" />
            <meta property="og:description" content="Apple is adding Call Context in iOS 27 to reduce the friction of customer service calls." />
          </head>
          <body>
            <div class="container med post-content">
              <p>Apple is adding Call Context in iOS 27, using Siri AI to summarize why a user is calling and keep relevant account details available during customer service calls.</p>
              <p>The feature is limited to devices that support Siri AI, including iPhone 15 Pro or later, and is designed to reduce repeated explanations during support calls.</p>
              <p>My favorite Apple accessory recommendations:</p>
              <ul>
                <li>Anker MagSafe/Qi2 Ultra-Slim Battery Pack</li>
                <li>AirPods Pro 3 (2x ANC vs AirPods Pro 2!)</li>
                <li>Anker Nano 45W Fast Charger with Smart Display</li>
              </ul>
              <p>FTC: We use income earning auto affiliate links.</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/09/ios-27-call-context-makes-phone-calls-much-easier-siri-ai/",
            title="iOS 27 Call Context makes phone calls much easier with Siri AI",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("Call Context", combined)
        self.assertIn("iPhone 15 Pro", combined)
        self.assertNotIn("AirPods Pro 3", combined)
        self.assertNotIn("45W Fast Charger", combined)

    def test_9to5_worth_checking_out_on_amazon_section_is_removed(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-06-09T18:00:00+00:00" />
            <meta property="og:description" content="Apple is bringing pull-to-refresh to macOS 27 across several built-in apps." />
          </head>
          <body>
            <div class="container med post-content">
              <p>macOS 27 Golden Gate adds pull-to-refresh support to the Mac in Safari, Mail, News, Podcasts, and Calendar.</p>
              <p>The gesture brings a familiar iPhone and iPad interaction to Apple’s desktop platform.</p>
              <p>Worth checking out on Amazon</p>
              <ul>
                <li>MacBook Neo</li>
                <li>Logitech MX Master 4</li>
                <li>AirTag (2nd Generation) – 4 Pack</li>
              </ul>
              <p>FTC: We use income earning auto affiliate links.</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/09/macos-27-golden-gate-pull-to-refresh-support/",
            title="macOS 27 Golden Gate adopts iPhone-like pull-to-refresh support",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("Safari, Mail, News, Podcasts, and Calendar", combined)
        self.assertNotIn("MacBook Neo", combined)
        self.assertNotIn("Logitech MX Master", combined)

    def test_9to5_best_apple_watch_accessories_section_is_removed(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-06-12T18:00:00+00:00" />
            <meta property="og:description" content="Apple is adding two first-party apps to watchOS 27." />
          </head>
          <body>
            <div class="container med post-content">
              <p>watchOS 27 will add a dedicated Siri app that keeps conversations available across Apple Watch, iPhone, Mac, and other devices.</p>
              <p>Apple is also streamlining Find Devices, Find Items, and Find People into a unified Find My app on Apple Watch.</p>
              <p>Best Apple Watch and iPhone accessories</p>
              <ul>
                <li>AirPods Pro 3 (now only $179, down from $249)</li>
                <li>Portable USB-C charger for Apple Watch</li>
                <li>Retro Mac stand for Apple Watch Nightstand Mode</li>
              </ul>
              <p>FTC: We use income earning auto affiliate links.</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/12/watchos-27-will-add-two-new-apps-to-your-apple-watch/",
            title="watchOS 27 will add two new apps to your Apple Watch",
        )

        title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("dedicated Siri app", combined)
        self.assertIn("unified Find My app", combined)
        self.assertNotIn("AirPods Pro 3", combined)
        self.assertNotIn("Retro Mac stand", combined)

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

    def test_app_store_guideline_update_does_not_merge_with_wwdc_os_features(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Updates App Store Guidelines With Stricter Rules for Low-Quality Apps",
                "Apple updated the App Store Review Guidelines at WWDC for low-quality apps, spam submissions, and possible Developer Program removal.",
                facts=[
                    "Certain app categories such as dating, flashlight, sound effects, wallpaper, simple timers, and fortune telling require a meaningfully different or improved experience.",
                    "Repeated low-effort App Store submissions could lead to removal from the Apple Developer Program.",
                ],
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果 macOS 27 引入“下拉刷新”手势",
                "苹果在 WWDC 期间为 macOS 27 Golden Gate 增加下拉刷新手势，Safari、邮件、新闻、播客和日历等内置 App 支持该功能。",
                source="IT之家",
            ),
            article_for(
                module,
                "iOS 27 and iPadOS 27 adoption rate appears in App Store developer data",
                "Apple shared iOS and iPadOS adoption numbers for developers during WWDC, but the story is about operating system install rates.",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)
        self.assertIn("app_store_trust", {event.event_kind for event in events})

    def test_app_store_listing_with_generic_guide_text_is_not_policy_update(self):
        module = load_module()

        event_kind = module.detect_event_kind(
            "小米智能存储App上架！首款NAS有望登场：外观提前揭晓",
            "小米智能存储 App 提前上架了苹果应用商店，目前已经隐藏。操作指南显示该机背部有电源、网线、USB、HDMI 接口。",
            [],
        )

        self.assertNotEqual(event_kind, "app_store_trust")

    def test_third_party_app_store_listing_is_deferred_weak_ecosystem_candidate(self):
        module = load_module()
        source = source_named(module, "快科技")
        candidate = module.Candidate(
            source="快科技",
            url="https://news.mydrivers.com/1/1128/1128311.htm",
            title="小米智能存储App上架！首款NAS有望登场：外观提前揭晓",
            summary="小米智能存储 App 提前上架了苹果应用商店，不过目前已经隐藏。",
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak")
        self.assertIn("third-party app", reason)

    def test_chinese_third_party_watchos_app_availability_is_deferred_weak(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/962/150.htm",
            title="Telegram App 重返苹果 watchOS 平台，上线全新原生 Apple Watch 应用",
            summary=(
                "Telegram CEO 宣布，App 已正式重返 watchOS 平台，上线全新原生 Apple Watch 客户端。"
                "用户可在 Apple Watch 上访问联系人和聊天记录，同时支持 GIF 动图与视频播放、语音和文字消息收发、位置共享、贴纸等功能。"
            ),
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak")
        self.assertIn("third-party app", reason)

    def test_official_app_store_personalization_feature_is_not_third_party_listing(self):
        module = load_module()
        source = source_named(module, "cnBeta")
        candidate = module.Candidate(
            source="cnBeta",
            url="https://www.cnbeta.com.tw/articles/tech/1565186.htm",
            title="苹果在App Store推出个性化推荐功能 提升应用发现效率",
            summary="苹果公司近日宣布，将在 App Store 引入一系列全新的应用发现功能，通过个性化推荐帮助用户更高效地找到适合自己的应用和游戏。这一更新首先在美国地区以英文形式上线，未来还将扩展至更多国家和语言。",
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertFalse(module.is_third_party_platform_availability_candidate(f"{candidate.title} {candidate.summary}"))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_ipad_cellular_data_plan_is_relevant_hardware_strategy(self):
        module = load_module()
        source = source_named(module, "AppleInsider")
        candidate = module.Candidate(
            source="AppleInsider",
            url="https://appleinsider.com/articles/26/06/09/you-can-buy-unlimited-att-data-for-your-ipad-for-3-a-day?utm_source=rss",
            title="You can buy unlimited AT&T data for your iPad for $3 a day",
            summary="AT&T will let iPad owners buy a day of unlimited cellular data without a monthly plan, contract, subscription, or credit check.",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "hardware_market")
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "hardware_products")

    def test_app_store_subscription_bundles_do_not_merge_with_apple_music_or_tv_features(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple introduces new subscription bundles coming to App Store",
                "At WWDC, Apple introduced App Store subscription Bundles and Suites so developers can sell access to multiple subscriptions through In-App Purchase.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果 iOS 27 为 Apple Music 增加横屏播放界面",
                "iOS 27 中 Apple Music 获得新的横屏播放界面，用户可以在 iPhone 横向使用音乐应用。",
                source="IT之家",
            ),
            article_for(
                module,
                "iOS 27 lets Apple TV remote stay pinned on the Home Screen",
                "Apple TV remote controls can be pinned to the iPhone Home Screen in iOS 27.",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)
        self.assertTrue(all(event.category == "software_systems" for event in events))

    def test_app_store_subscription_bundle_sources_merge_despite_policy_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple introduces new subscription bundles coming to App Store",
                "At WWDC, Apple introduced App Store subscription Bundles and Suites so developers can sell access to multiple subscriptions through In-App Purchase.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "The App Store is going to add subscription bundles soon",
                "Streaming-style bundles for iPhone app subscriptions were announced during WWDC, along with other App Store changes like new guidelines about removing opportunistic apps.",
                source="The Verge",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertIn("app-store-subscriptions", module.event_primary_facets(events[0]))

    def test_wwdc_os_app_micro_updates_do_not_merge_when_primary_topics_differ(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Reveals How Many iPhones Were Running iOS 26 Before WWDC",
                "Apple shared iOS 26 and iPadOS 26 adoption rates ahead of WWDC.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果为三款 AirPods 推出测试版固件 9A5292e",
                "Apple released new AirPods beta firmware with iOS 27 features.",
                source="IT之家",
            ),
            article_for(
                module,
                "iOS 27 lets Apple TV remote stay pinned on the Home Screen",
                "Apple TV remote controls can be pinned to the iPhone Home Screen in iOS 27.",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果在App Store推出个性化推荐功能 提升应用发现效率",
                "苹果公司近日宣布，将在 App Store 引入全新的应用发现功能，通过个性化推荐帮助用户找到应用和游戏。",
                source="cnBeta",
            ),
            article_for(
                module,
                "苹果 iPhone 国行机型升级 iOS 27 后可使用 AI 壁纸扩图功能",
                "iOS 27 开发者预览版让部分国行 iPhone 用户通过锁屏壁纸启用 AI 扩图功能。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果统一 iOS 27、macOS 27 及 CarPlay 壁纸设计 “Celosia”",
                "Apple unified the default wallpaper design across iOS 27, macOS 27, and CarPlay with the Celosia theme.",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 6)
        self.assertEqual(
            {
                tuple(sorted(module.event_primary_facets(event)))
                for event in events
            },
            {
                ("os-adoption",),
                ("airpods-firmware",),
                ("apple-tv-remote",),
                ("app-store-discovery",),
                ("ai-wallpaper",),
                ("system-wallpaper",),
            },
        )

    def test_broad_os_compatibility_facet_does_not_merge_distinct_feature_topics(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "七年之痒终得解，苹果 macOS 27 系统“随航”功能终于支持手指触控",
                "At WWDC, Apple's iOS 27, iPadOS 27, and macOS 27 developer beta update Sidecar with direct touch support for iPad.",
                source="IT之家",
            ),
            article_for(
                module,
                "操控 Apple TV 更方便，iOS 27 支持将“遥控器”功能固定到主屏幕",
                "At WWDC, Apple's iOS 27 and iPadOS 27 developer beta support pinning the Apple TV remote shortcut to the iPhone Home Screen.",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_macos_performance_feedback_does_not_merge_with_touch_macbook_roadmap(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "有望为触控 MacBook 铺路：苹果 macOS 27 引入“下拉刷新”手势",
                (
                    "苹果在 macOS 27 Golden Gate 中引入 Swipe down to refresh 下拉刷新手势，"
                    "Safari、邮件、新闻、播客和日历等应用已确认支持；报道认为这项设计变化"
                    "可能为后续触控 MacBook Ultra 铺路。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "用户反馈苹果 macOS 27 大幅提升流畅度，像是换了台 Mac",
                (
                    "macOS 27 Golden Gate Beta 1 赢得社区用户积极反馈，多名用户称其大幅改善"
                    "老设备运行流畅度；M1 Pro MacBook Pro 用户称升级后未遇到卡顿、掉帧和反应迟缓。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual(
            {tuple(sorted(module.effective_topic_facets(module.event_primary_facets(event)))) for event in events},
            {("macbook-touch-roadmap", "macos-pull-refresh"), ("macos-performance-feedback",)},
        )

    def test_macos_performance_feedback_is_software_not_security_or_hardware(self):
        module = load_module()
        title = "用户反馈苹果 macOS 27 大幅提升流畅度，像是换了台 Mac"
        summary = (
            "macOS 27 Golden Gate Beta 1 赢得社区用户积极反馈，多名用户称其大幅改善老设备运行流畅度。"
            "M1 Pro MacBook Pro 用户称升级后没有遇到 macOS 26 Tahoe 稳定版存在的卡顿、掉帧和整体反应迟缓问题。"
        )
        facts = [
            "按照以往经验，macOS 开发者测试版通常会伴随大量漏洞和性能问题，上一代正式版 macOS Tahoe 也因卡顿和性能退步饱受诟病。"
        ]

        self.assertEqual(module.detect_event_kind(title, summary, facts), "os_app")
        self.assertEqual(module.choose_category(title, " ".join([summary, *facts])), "software_systems")
        self.assertEqual(module.classify_relevance_tier(title, summary, facts, "IT之家")[0], "strong")

    def test_macbook_memory_ai_specs_do_not_merge_with_macos_touch_gesture(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "有望为触控 MacBook 铺路：苹果 macOS 27 引入“下拉刷新”手势",
                (
                    "苹果在 macOS 27 Golden Gate 中引入下拉刷新手势，报道认为这项设计变化"
                    "可能为后续触控 MacBook Ultra 铺路，相关机型或配备触控 OLED 屏幕和 M6 芯片。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "容量增幅 50%：消息称 MacBook Neo 2 配 12GB 内存，支持苹果最强本地 AI 模型",
                (
                    "MacBook Neo 2 据称配备 12GB 内存，容量较前代增加 50%，并将支持 AFM 3 Core Advanced"
                    " 本地 AI 模型；消息称该设备使用 A19 Pro 芯片。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual(
            {tuple(sorted(module.effective_topic_facets(module.event_primary_facets(event)))) for event in events},
            {("macbook-touch-roadmap", "macos-pull-refresh"), ("macbook-memory-ai",)},
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

    def test_non_apple_m3_model_name_does_not_create_apple_relevance(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/example/minimax-m3.htm",
            title="Day-0 支持，摩尔线程完成 MiniMax M3 大模型适配",
            summary="摩尔线程宣布其 GPU 已完成 MiniMax M3 大模型适配，支持本地部署和推理。",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))
        self.assertEqual(
            module.classify_relevance_tier(candidate.title, candidate.summary, [], candidate.source)[0],
            "weak",
        )

    def test_appleinsider_vs_comparison_is_deferred_as_weak(self):
        module = load_module()
        title = "MacBook Neo vs Dell XPS 13: $599 budget battle, compared"
        summary = "A comparison of a rumored MacBook Neo against Dell's XPS 13, with buying advice and benchmark discussion."

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_intel_pc_macbook_marketing_comparison_stays_weak(self):
        module = load_module()
        title = "Intel compares Core Ultra laptops against Apple's MacBook Pro"
        summary = "Intel's marketing material positions new Windows PCs as rivals to Apple's MacBook Pro in performance and gaming compatibility."

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_top_stories_recap_is_deferred_as_weak(self):
        module = load_module()
        title = "Top Stories: WWDC 2026 Recap, iOS 27 Features, Apple Wallet, and More"
        summary = "A weekly recap links to Apple's WWDC announcements, iOS 27 features, Apple Wallet changes, and other previously reported stories."

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "weak", reason)

    def test_apple_os_support_drop_not_deferred_by_intel_comparison_context(self):
        module = load_module()
        title = "Have One of These 16 Apple Devices? Software Support Ends This Fall"
        summary = (
            "Apple will end software support for 16 devices this fall across four product lines. "
            "The full extent of this year's software drops became clear with macOS 27 Golden Gate, "
            "iPadOS 27, tvOS 27, and watchOS 27. By comparison, iPadOS 26 cut only a single device. "
            "macOS Golden Gate brings the era of Intel Macs to a close, and Apple TV sees two models "
            "dropped with tvOS 27."
        )
        key_facts = [
            "watchOS 27 drops Series 6, Series 7, Series 8, Apple Watch Ultra (first generation), and Apple Watch SE (second generation).",
            "iPadOS 27 raises the floor to the A14 Bionic chip or the M1 chip, dropping five iPad models.",
            "The remaining Intel Macs supported by macOS Tahoe do not make the cut for macOS 27.",
        ]

        self.assertEqual(module.detect_event_kind(title, summary, key_facts), "os_compatibility")
        tier, reason = module.classify_relevance_tier(title, summary, key_facts, "MacRumors")

        self.assertEqual(tier, "strong", reason)

    def test_chinese_buying_advice_is_not_promoted_to_security_news(self):
        module = load_module()
        title = "避开购机亏空 解析苹果几年换最划算"
        summary = "文章分析 iPhone、MacBook 和 Apple Watch 的换机周期、保值率和购买建议，帮助用户避免购机亏空。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_amd_hardware_chart_with_macos_context_stays_weak(self):
        module = load_module()
        title = "历史新高！AMD显卡占比破19%：RX 9070 XT/9060 XT首次登上Steam硬件榜"
        summary = "Steam 硬件榜显示 AMD 显卡占比继续提升，文章背景提到 macOS 和 Linux 用户占比变化。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_generic_consumer_electronics_fda_magnet_story_stays_weak_despite_airpods_context(self):
        module = load_module()
        title = "消费电子产品磁场可干扰心脏起搏器，FDA 建议保持 15 厘米安全距离"
        summary = (
            "FDA 建议佩戴心脏起搏器或除颤器的患者，将智能手机、耳机和智能手表等电子设备与植入器械保持至少 15 厘米距离。"
            "文章提到 2022 年研究曾测试 AirPods、iPhone 12 Pro Max、Apple Pencil 和微软 Surface Pen。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)

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

    def test_magsafe_accessory_wallet_word_does_not_become_apple_wallet_feature(self):
        module = load_module()
        title = "Hands-on: Belkin's new 25W MagSafe battery pack and wallet are great travel accessories"
        summary = "The third-party Belkin accessories include a MagSafe battery and a magnetic wallet attachment, with Amazon pricing and hands-on impressions."

        self.assertNotEqual(module.detect_event_kind(title, summary), "wallet_feature")
        self.assertEqual(module.classify_relevance_tier(title, summary, [], "9to5Mac")[0], "weak")

    def test_belkin_hands_on_stays_weak_even_with_apple_service_affiliate_tail(self):
        module = load_module()
        title = "Hands-on: Belkin's new 25W MagSafe battery packs 10,000mAh for your iPhone"
        summary = "Belkin's third-party MagSafe battery is now available on Amazon for $84.99 after a 15% discount."
        facts = [
            "The Belkin UltraCharge Pro comes in two colors: Black and Sand. It’s available on Amazon for $84.99, a 15% discount from its typical pricing.",
            "Apple Music – $10.99/mo after free trial",
            "Apple TV+ – $12.99/mo after free trial",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_apple_service_affiliate_tail_is_fact_noise(self):
        module = load_module()

        self.assertTrue(module.fact_noise("Apple Music – $10.99/mo after free trial"))
        self.assertTrue(module.fact_noise("Apple One bundle – $19.95/mo after free trial"))

    def test_rosetta_retirement_warning_is_software_not_hardware(self):
        module = load_module()
        title = "Apple says Rosetta 2 support for Intel Mac apps will end after macOS 28"
        summary = "Apple's developer documentation warns that Rosetta 2 remains available in macOS 27 and macOS 28 but will be removed in a later macOS release."

        self.assertEqual(module.detect_event_kind(title, summary), "os_compatibility")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_chinese_rosetta_retirement_warning_is_software_not_hardware(self):
        module = load_module()
        title = "苹果 macOS 27 系统强化 Rosetta 2 淘汰提醒，Intel 架构应用未来将无法在新系统运行"
        summary = "苹果在 macOS 27 中继续提供 Rosetta 2，但开发者文档提示 Intel 架构应用未来会失去支持，用户需要迁移到 Apple Silicon 原生版本。"

        self.assertEqual(module.detect_event_kind(title, summary), "os_compatibility")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_apple_car_test_site_asset_sale_is_strong_hardware_company_news(self):
        module = load_module()
        title = "Waymo bought Apple's former car testing site in Arizona"
        summary = "Waymo acquired the Arizona proving ground Apple used for its canceled Apple Car project, marking a disposition of Apple vehicle testing assets."

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

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

    def test_competitor_background_does_not_hard_exclude_direct_apple_thread_story(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/962/726.htm",
            title="苹果谷歌智能家居设备升级 Thread 1.4 协议，统一网络凭证共享迈出关键一步",
            summary=(
                "Apple TV 在 tvOS 27 开发者测试版中已接入 Thread 1.4，Google TV Streamer 也升级。"
                "报道还提到三星 SmartThings、宜家 Dirigera 和亚马逊等智能家居生态。"
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "os_app")

    def test_specific_os_app_removal_does_not_merge_with_general_ios_summary(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Removes Walkie-Talkie From Apple Watch in watchOS 27 Beta",
                "Apple removed the Walkie-Talkie app from watchOS 27 beta. The article mentions a previous security vulnerability only as historical background.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果 iOS 27 Beta 1 发布，主要更新点一文汇总",
                "苹果 iOS 27 Beta 1 带来 Apple Intelligence、Safari、Messages、Phone、Wallet、App Store 和通信安全等多项系统更新。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual(
            module.detect_event_kind(articles[0].title, articles[0].summary, articles[0].key_facts),
            "os_app",
        )

    def test_broad_multi_platform_os_summary_does_not_bridge_specific_platform_events(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 iOS 27 五千人投票结果出炉，近六成升级用户对首个预览版很满意",
                "iOS 27 首个预览版用户投票结果出炉，开发者预览版 Beta 1 已面向全球用户推出。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果找到了软件更新的完美节奏：一年堆功能 一年做优化",
                "文章回顾 iOS 27、iPadOS 27、macOS 27、watchOS 27、tvOS 27 和 visionOS 27 的整体更新节奏。",
                source="cnBeta",
            ),
            article_for(
                module,
                "苹果 watchOS 27 测试版悄然移除 Apple Watch 对讲机应用",
                "watchOS 27 首个开发者测试版悄然移除了 Apple Watch 上的对讲机应用，该应用已从应用列表和控制中心内彻底消失。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)

    def test_ios_performance_optimization_merges_across_sources_not_with_future_hardware_testing(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Is Already Testing Four New Products With iOS 28",
                (
                    "Apple is testing a HomePod with a screen, a foldable iPhone, and camera-equipped "
                    "AirPods with iOS 28. The report says the AirPods could become Apple's first wearable "
                    "AI product and feed surroundings to Siri."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "iOS 27 makes your iPhone faster in 40+ ways, here’s the full list",
                (
                    "While Apple Intelligence and Siri AI are the biggest additions to iOS 27, "
                    "the update will also make your iPhone noticeably faster in more than 40 ways. "
                    "Apple says apps launch up to 30 percent faster, Photos content can load up to "
                    "70 percent faster, and AirDrop transfers can be up to 80 percent faster."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果 iOS 27 引入 40+ 底层优化：App 启动提速 30%、隔空投送最高提速 80%",
                (
                    "苹果 iOS 27 带来 40 多项底层性能优化，覆盖 App 启动、照片加载、键盘响应、"
                    "表情键盘、锁屏、语音控制和隔空投送等系统体验。App 启动最高提速 30%，"
                    "照片内容加载最高提速 70%，隔空投送最高提速 80%。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "iPhone更快了！iOS 27带来超40+底层优化：APP提速超30%",
                (
                    "苹果在最新的 iOS 27 系统中带来超过 40 项底层优化，包括相机启动速度、"
                    "浏览器页面加载速度、窗口切换速度等。APP 启动速度最高提升 30%，"
                    "隔空投送传输速度最高提升 80%，相册加载新拍摄内容速度最高提升 70%。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        hardware_events = [event for event in events if "iOS 28" in event.title]
        performance_events = [event for event in events if "40" in event.title or any("40" in fact for fact in event.key_facts)]
        self.assertEqual(len(hardware_events), 1)
        self.assertEqual(len(hardware_events[0].articles), 1)
        self.assertEqual({article.source for article in performance_events[0].articles}, {"9to5Mac", "IT之家", "快科技"})

    def test_event_summary_level_consolidates_same_performance_event(self):
        module = load_module()
        english_article = article_for(
            module,
            "iOS 27 makes your iPhone faster",
            "Apple says iOS 27 improves iPhone performance.",
            facts=[
                "Apple outlined more than 40 ways iOS 27 makes iPhone faster.",
                "Apps launch up to 30% faster, Photos content loads up to 70% faster, and AirDrop transfers can be up to 80% faster.",
            ],
            source="9to5Mac",
        )
        chinese_article = article_for(
            module,
            "iPhone 更快了，iOS 27 带来底层优化",
            "苹果在 iOS 27 中改善 iPhone 性能。",
            facts=[
                "iOS 27 带来超过 40 项底层性能优化。",
                "App 启动最高提速 30%，相册加载最高提升 70%，隔空投送最高提升 80%。",
            ],
            source="快科技",
        )
        english_article.tokens = module.article_tokens(english_article.title, english_article.summary)
        chinese_article.tokens = module.article_tokens(chinese_article.title, chinese_article.summary)
        english_event = module.Event(
            event_id="english-performance",
            category=english_article.category,
            title=english_article.title,
            summary=" ".join([english_article.summary, *english_article.key_facts]),
            key_facts=english_article.key_facts,
            published_utc=english_article.published_utc,
            published_raw=english_article.published_raw,
            published_source=english_article.published_source,
            confidence=english_article.confidence,
            articles=[english_article],
            tokens=set(english_article.tokens),
            event_kind=english_article.event_kind,
            relevance_tier=english_article.relevance_tier,
            relevance_reason=english_article.relevance_reason,
            regions=set(english_article.regions),
        )
        chinese_event = module.Event(
            event_id="chinese-performance",
            category=chinese_article.category,
            title=chinese_article.title,
            summary=" ".join([chinese_article.summary, *chinese_article.key_facts]),
            key_facts=chinese_article.key_facts,
            published_utc=chinese_article.published_utc,
            published_raw=chinese_article.published_raw,
            published_source=chinese_article.published_source,
            confidence=chinese_article.confidence,
            articles=[chinese_article],
            tokens=set(chinese_article.tokens),
            event_kind=chinese_article.event_kind,
            relevance_tier=chinese_article.relevance_tier,
            relevance_reason=chinese_article.relevance_reason,
            regions=set(chinese_article.regions),
        )

        self.assertFalse(module.should_merge(english_article, chinese_event))
        self.assertTrue(module.events_should_merge(english_event, chinese_event))

    def test_apple_product_price_increase_reports_merge_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Tim Cook Says Apple Price Increases Are 'Unavoidable' Due to Memory Costs",
                (
                    "Tim Cook said Apple price increases are unavoidable because AI demand is "
                    "driving memory and storage chip shortages. The iPhone 18 Pro, iPad, and Mac "
                    "could get more expensive, and Apple already raised the Mac mini from $599 to $799."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "AI-driven chip shortages to cause Apple product price increase, says Cook",
                (
                    "Cook said Apple product price increases are unavoidable as memory and storage "
                    "costs rise. The Wall Street Journal estimated a price-inflated iPhone 18 Pro "
                    "could start around $1,299."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "内存、存储成本持续飙升！库克确认：苹果产品涨价不可避免",
                (
                    "苹果 CEO 蒂姆・库克表示，受内存和存储成本持续上涨影响，苹果产品涨价已不可避免。"
                    "iPhone 18 Pro、iPad、Mac 等产品未来存在涨价可能，TechInsights 认为 iPhone 18 Pro "
                    "售价可能需要上调约 270 美元。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "苹果计划上调多款硬件售价 Tim Cook称内存成本“已不可持续”",
                (
                    "受全球存储芯片持续短缺及成本飙升影响，苹果计划上调多款硬件产品价格，包括 iPhone、iPad 和 Mac。"
                    "Tim Cook 直言当前内存相关支出已不可持续，价格上调在所难免。"
                ),
                source="cnBeta",
            ),
            article_for(
                module,
                "库克：AI 浪潮引发存储芯片价格暴涨，iPhone 等苹果产品涨价已“不可避免”",
                (
                    "华尔街日报报道称，苹果 CEO Tim Cook 确认苹果公司为应对 AI 需求导致的存储芯片成本飙升，"
                    "计划上调产品售价。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "AppleInsider", "快科技", "cnBeta", "IT之家"})
        self.assertEqual(events[0].category, "hardware_products")
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_iphone_air_successor_does_not_merge_with_foldable_iphone_render_leak(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "消息称苹果 iPhone Air 2 明年春季发售：升级双摄、换用 A20 芯片",
                (
                    "彭博社报道称，iPhone Air 2 已进入高级测试阶段，将于 2027 年春季发售。"
                    "新机主要升级后置双摄，新增超广角镜头，并将采用 2nm 工艺 A20 芯片提升能效和续航。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "被起诉的爆料人 Jon Prosser 再现身，发布苹果首款折叠屏 iPhone Ultra 手机渲染图",
                (
                    "Jon Prosser 根据最新传闻制作了苹果首款折叠屏手机 iPhone Ultra 的全新渲染图。"
                    "新图调整了 USB-C 接口和扬声器格栅位置，展示相机控制按钮，并重申 7.8 英寸内屏、"
                    "5.5 英寸外屏、9mm 厚度和四枚摄像头等参数。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual(
            {
                tuple(sorted(module.effective_topic_facets(module.event_primary_facets(event))))
                for event in events
            },
            {("iphone-air-successor",), ("foldable-iphone-render-leak",)},
        )

    def test_mixed_hardware_roadmap_event_splits_by_specific_topic(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "消息称苹果 iPhone Air 2 明年春季发售：升级双摄、换用 A20 芯片",
                (
                    "彭博社报道称，iPhone Air 2 已进入高级测试阶段，将于 2027 年春季发售。"
                    "新机主要升级后置双摄，新增超广角镜头，并将采用 2nm 工艺 A20 芯片提升能效和续航。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "被起诉的爆料人 Jon Prosser 再现身，发布苹果首款折叠屏 iPhone Ultra 手机渲染图",
                (
                    "Jon Prosser 根据最新传闻制作了苹果首款折叠屏手机 iPhone Ultra 的全新渲染图。"
                    "新图调整了 USB-C 接口和扬声器格栅位置，展示相机控制按钮，并重申 7.8 英寸内屏、"
                    "5.5 英寸外屏、9mm 厚度和四枚摄像头等参数。"
                ),
                source="IT之家",
            ),
        ]
        mixed = module.Event(
            event_id="mixed-hardware-roadmap",
            category="hardware_products",
            title=articles[0].title,
            summary=" ".join(article.summary for article in articles),
            key_facts=[],
            published_utc=articles[0].published_utc,
            published_raw=articles[0].published_raw,
            published_source=articles[0].published_source,
            confidence=articles[0].confidence,
            articles=articles,
            tokens=set().union(*(article.tokens for article in articles)),
            event_kind="hardware_market",
            relevance_tier="strong",
            regions=set(),
            merge_warnings=["mixed primary topic facets"],
        )

        split_events = module.split_mixed_topic_events([mixed])

        self.assertEqual(len(split_events), 2)
        self.assertEqual(
            {
                tuple(sorted(module.effective_topic_facets(module.event_primary_facets(event))))
                for event in split_events
            },
            {("iphone-air-successor",), ("foldable-iphone-render-leak",)},
        )

    def test_price_increase_region_warning_is_exempt_for_global_product_pricing(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Tim Cook Says Apple Price Increases Are 'Unavoidable' Due to Memory Costs",
                (
                    "In the United States, Cook said Apple price increases are unavoidable because AI demand "
                    "is driving memory and storage chip shortages. The iPhone 18 Pro, iPad, Mac, and Mac mini "
                    "could get more expensive as Apple absorbs higher component costs."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "库克：苹果产品涨价已不可避免",
                (
                    "中国媒体报道称，苹果 CEO Tim Cook 确认内存和存储成本上涨将推动 iPhone、iPad 和 Mac "
                    "等产品价格上调，iPhone 18 Pro 和 Mac mini 也可能受到成本压力影响。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_ios_recovery_carplay_route_and_ipados_restore_image_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "似曾相识的感觉：苹果 iOS 27 系统新增 Recovery 修复模式，支持诊断、抹除等功能",
                "IT之家实测发现，iOS 27 新增 Recovery 修复模式，支持恢复助理、软件更新、诊断模式、抹掉所有内容和设置、恢复模式等功能。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 iOS 27 版 CarPlay 新增路线共享功能，将解决特斯拉 FSD 导航同步难题",
                "苹果公司推出路线共享 Route Sharing 功能，支持导航应用以路段坐标数组的形式，把路线数据传递给车辆。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果手滑：为非兼容 iPad Pro 机型提供 iPadOS 27 镜像下载链接",
                "苹果开发者网站短暂上架了针对不在 iPadOS 27 官方兼容列表内的旧款 iPad Pro 的恢复镜像，随后删除。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)

    def test_communication_framework_and_facetime_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 iOS 27 升级 LiveCommunicationKit：锁屏时支持全屏来电显示等",
                "LiveCommunicationKit 现已支持全屏显示在锁定屏幕上，包含联系人姓名、照片以及一套标准操作控件，与来电时的界面完全一致。该框架为开发者提供 VoIP 通话交互接口，并支持将应用程序设置为系统默认通话应用。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果升级 iOS 27 版 FaceTime 视频通话：iPhone 17 系列可同时调用前后摄像头",
                "在 iOS 27 系统中，苹果计划为 FaceTime 引入双摄像头功能，在视频通话中让 iPhone 17 系列用户同时调用前后摄像头。用户在 FaceTime 通话界面点击“翻转”按钮，系统自动切换为双摄像头模式。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_macos_afp_and_boot_partition_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "macOS 27 终止支持 AFP 协议：苹果 Time Capsule 失去官方备份支持",
                "在 macOS 27 系统中，苹果公司终止支持 AFP 协议，导致已停产的 Time Capsule 无法继续用于 Time Machine 备份。从 macOS 27 开始，Time Machine 将强制要求使用 SMBv2 或 SMBv3 协议的存储设备。",
                source="IT之家",
            ),
            article_for(
                module,
                "Asahi Linux 反馈称苹果 macOS 27 调整启动盘检测机制，影响多系统用户",
                "macOS 27 开发者测试版调整启动选择器检测有效操作系统引导卷的方式，导致部分用户无法选择备用分区或磁盘启动，Asahi Linux 用户受影响尤为严重。团队已向苹果提交编号为 FB22994760 的错误报告。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_wallet_feature_roundup_and_tap_to_share_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 Adds Six New Features to Apple Wallet on Your iPhone",
                "Apple Wallet gets enhanced passes, digital hotel keys, four new barcode types, bill splitting powered by Apple Cash and Apple Intelligence, and order tracking in Australia and Canada.",
                source="MacRumors",
            ),
            article_for(
                module,
                "iOS 27 Introduces New 'Tap to Share' Feature, But Not Available in EU",
                "Tap to Share lets merchants use an iPhone NFC tap to exchange membership information, shipping addresses, contact details, and order information while completing payment.",
                source="MacRumors",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_weather_and_keyboard_input_updates_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果升级 iOS 27 版天气应用：可简要显示未来几天重要天气事件",
                "iOS 27 版天气应用新增亮点版块，并引入每小时和 10 天降水、风力概览。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 iOS 27 键盘输入法扩展支持 10 种语言，优化简体中文输入",
                "iOS 27 Beta 1 升级键盘输入法，新增 10 种语言，并改进拼音转换、上下文候选词和中文标点建议。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_iphone_color_dummy_and_beats_headphones_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 iPhone 18 Pro Max 机模曝光：深樱桃色、浅蓝、深灰颜色亮相",
                "消息源分享 iPhone 18 Pro Max 机模照片，展示深樱桃色、浅蓝色和深灰版本。",
                source="IT之家",
            ),
            article_for(
                module,
                "韩国球员李刚仁佩戴苹果新款 Beats 耳机现身",
                "继西班牙球员拉明·亚马尔之后，韩国球员李刚仁在世界杯期间佩戴新款 Beats 耳机现身。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_macbook_heat_defect_does_not_merge_with_amd_game_comparison(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 M5 Max MacBook Pro 被曝过热后屏幕变色，疑似硬件缺陷",
                "用户反馈 M5 Max MacBook Pro 在高负载时过热，并出现屏幕边缘变色问题，苹果支持建议送修检测。",
                source="IT之家",
            ),
            article_for(
                module,
                "AMD 新掌机运行游戏表现反超 MacBook Neo，Windows 兼容性优势明显",
                "测试对比 AMD Windows 设备和传闻中的 MacBook Neo，讨论游戏兼容性和性能差异。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_chinese_amd_windows_macbook_marketing_comparison_stays_weak(self):
        module = load_module()
        title = "Windows与macOS之争再起！AMD公开放话：苹果笔记本给不了你的 我们都能给"
        summary = (
            "AMD官网发布全新营销物料，直接将矛头对准苹果最新推出的高性价比MacBook Neo，"
            "突出自己的游戏兼容性优势，称20款热门PC游戏中MacBook Neo仅能原生运行5款。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_chinese_amd_windows_macbook_marketing_comparison_with_fact_details_stays_weak(self):
        module = load_module()
        title = "Windows与macOS之争再起！AMD公开放话：苹果笔记本给不了你的 我们都能给"
        summary = "AMD官网发布全新营销物料，直接将矛头对准苹果最新推出的高性价比MacBook Neo。"
        facts = [
            "AMD官网发布全新营销物料，直接将矛头对准苹果最新推出的高性价比MacBook Neo，突出自己的游戏兼容性优势，打出“MacBook Neo舍弃的一切，AMD锐龙AI处理器都为你内置”的宣传口号。",
            "在官方宣传中，AMD强调，在20款全球最热门的PC游戏中，MacBook Neo仅能原生运行其中5款，其余15款均不支持原生运行。",
            "除了游戏兼容性，AMD还拿出搭载锐龙5 220处理器的惠普Omnibook X翻转本与MacBook Neo进行逐项对比。",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_macbook_ultra_touch_rumor_does_not_merge_with_m5_heat_defect(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "消息称苹果 MacBook Ultra 屏幕“百分百确认要上触控”，有望今年底至明年初登场",
                (
                    "博主透露苹果 MacBook 屏幕确认要上触控，预计相应机型为 MacBook Ultra，"
                    "并可能搭载 M6 Pro 与 M6 Max 处理器，同时升级为主动均热板散热设计。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "网友反馈其苹果 M5 Max MacBook Pro 高负载运行过热导致屏幕变色",
                (
                    "用户反馈 M5 Max MacBook Pro 在执行本地大语言模型高负载任务时过热，"
                    "屏幕出现区域性颜色失真，芯片温度可突破 100 摄氏度。"
                ),
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_iphone_material_rumor_does_not_merge_with_foldable_shipments_or_pc_memory_comparison(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 iPhone 18 Pro 或改用铝合金工艺，新增深樱桃配色",
                "供应链称 iPhone 18 Pro 机身将调整为铝合金工艺，并测试深樱桃、浅蓝等配色。",
                source="快科技",
            ),
            article_for(
                module,
                "苹果折叠 iPhone Ultra 备货量曝光，国行版本同步推进",
                "供应链消息称折叠 iPhone Ultra 初期备货量有限，苹果正在推进国行认证和生产节奏。",
                source="快科技",
            ),
            article_for(
                module,
                "WinPC 厂商学习 MacBook 内存策略，8GB 机型仍用于入门市场",
                "行业观察称部分 Windows PC 厂商借鉴 MacBook 入门内存定位，但用户仍建议选择 16GB。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)

    def test_fasttech_iphone_material_foldable_and_winpc_titles_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果听劝！17 Pro掉漆被吐槽：iPhone 18 Pro全面改进铝合金工艺",
                (
                    "最新的供应链爆料显示，iPhone 18 Pro没有换回钛金属机身，将继续沿用铝合金材质，"
                    "苹果针对掉漆痛点研发全新的铝合金精炼工艺，并提供浅蓝色、黑色、银色以及樱桃红版本。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "苹果为折叠屏iPhone Ultra铺路：iOS 27新增多款原生应用横屏模式",
                (
                    "苹果首款折叠屏iPhone Ultra将在今年秋季亮相，配备5.49英寸外屏和7.76英寸内屏，"
                    "iOS 27新增多款原生应用横屏模式，为折叠屏体验铺路。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "反转来得太快 刚嘲笑MacBook 8GB内存不够用：WinPC这就学上了",
                "Windows PC 厂商开始在入门机型采用 8GB 内存策略，文章把它与 MacBook 入门配置作行业对比。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)

    def test_iphone_material_finish_and_iphone_ultra_biometric_change_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果听劝！17 Pro掉漆被吐槽：iPhone 18 Pro全面改进铝合金工艺",
                "iPhone 18 Pro 将继续沿用铝合金材质，并针对掉漆痛点研发新的铝合金精炼工艺和樱桃红配色。",
                source="快科技",
            ),
            article_for(
                module,
                "iPhone Ultra取消Face ID：改用侧边指纹 博主感叹像是在做梦",
                "爆料称 iPhone Ultra 砍掉 Face ID 人脸识别方案，回归 Touch ID，并将指纹识别集成到电源键。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_fasttech_related_headline_fragments_are_fact_noise(self):
        module = load_module()

        self.assertTrue(module.fact_noise("苹果显示技术大转向！MacBook Ultra首发三星8.6代OLED：Mini-LED退场"))
        self.assertTrue(module.fact_noise("《苹果 M6 MacBook Pro（MacBook Ultra）前瞻：首搭 OLED 触摸屏、配 2nm 工艺芯片，最快 2026 年底发布》"))
        self.assertTrue(module.fact_noise("比华为三折叠还稀缺！iPhone Ultra国行备货量不足：博主直言抢到赚到"))
        self.assertTrue(module.fact_noise("iPhone Ultra取消Face ID：改用侧边指纹 博主感叹像是在做梦"))
        self.assertTrue(module.fact_noise("反转来得太快 刚嘲笑MacBook 8GB内存不够用：WinPC这就学上了"))

    def test_messages_drawing_and_safari_ai_features_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果升级 iOS 27 版信息应用，上线绘图工具",
                "iOS 27 和 macOS 27 Golden Gate 的信息应用新增绘图选项，集成 Markup 标注工具。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 iOS 27 版 Safari 浏览器新增 AI 自动整理标签页、自定义扩展等功能",
                "iOS 27 版 Safari 可按主题自动分类标签页，并支持用自然语言创建扩展和 Notify Me 网页监控。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_xcode_gemini_integration_is_strong_developer_tool_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/10/xcode-27-expands-agentic-coding-toolset-with-gemini-integration/",
            title="Xcode 27 expands agentic coding toolset with Gemini integration",
            summary=(
                "Starting with Xcode 27, developers can natively use Google Gemini, "
                "in addition to Claude Code and OpenAI Codex, to plan, write, and review code."
            ),
            feed_time_raw="Wed, 10 Jun 2026 21:00:00 +0000",
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")
        self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 80)

    def test_apple_leak_lawsuit_candidate_gets_high_detail_priority(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/10/jon-prosser-seeks-another-shot-to-respond-to-apples-liquid-glass-leak-lawsuit/",
            title="Jon Prosser seeks another shot to respond to Apple’s Liquid Glass leak lawsuit",
            summary=(
                "Apple's lawsuit over Liquid Glass leaks may see a default ruling reversed "
                "after Jon Prosser asked the court for another chance to respond."
            ),
            feed_time_raw="Wed, 10 Jun 2026 20:30:00 +0000",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "legal_antitrust")
        self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 80)

    def test_official_vision_pro_accessory_discontinuation_is_strong_hardware_news(self):
        module = load_module()
        title = "Apple Seemingly Discontinuing Vision Pro Travel Case Around the World"
        summary = (
            "Apple's official Vision Pro Travel Case appears to be unavailable from Apple Store "
            "online in multiple countries. The article mentions Meta and Ray-Ban smart glasses only as market background."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_detail_selection_prefers_in_window_candidate_over_old_high_score_candidate(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        old_high_score = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/08/ios-27-announcement/",
            title="Apple officially announces iOS 27, the next major iPhone update",
            summary="Apple announced iOS 27 at WWDC with new features, Siri AI, and Liquid Glass.",
            feed_time_raw="Mon, 08 Jun 2026 18:00:00 +0000",
        )
        current_legal_story = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/10/jon-prosser-seeks-another-shot-to-respond-to-apples-liquid-glass-leak-lawsuit/",
            title="Jon Prosser seeks another shot to respond to Apple’s Liquid Glass leak lawsuit",
            summary="Apple's lawsuit over Liquid Glass leaks may see a default ruling reversed.",
            feed_time_raw="Wed, 10 Jun 2026 20:30:00 +0000",
        )

        selected = module.select_detail_candidates(
            [old_high_score, current_legal_story],
            {"9to5Mac": source},
            1,
            datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(selected, [current_legal_story])

    def test_deal_roundup_remains_filtered_even_when_current_and_apple_product_heavy(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/10/deals-airpods-pro-240w-beats-cable-macbook-pro/",
            title="Deals: AirPods Max 2, 240W Beats cable, MacBook Pro, more",
            summary=(
                "Today’s 9to5Toys Lunch Break is headlined by AirPods Pro 3 dropping "
                "to the best price ever at $179, with MacBook Pro, Apple Watch, and Beats accessories available on Amazon."
            ),
            feed_time_raw="Wed, 10 Jun 2026 18:30:00 +0000",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))

    def test_routine_third_party_apple_platform_tool_update_stays_weak(self):
        module = load_module()
        title = "OmniOutliner 6.2 is now available in 11 languages"
        summary = (
            "OmniGroup's outlining tool expanded localization support across Mac, iPad, "
            "iPhone, and Apple Vision Pro, and mentions Apple Intelligence support."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_watchos_app_removal_with_official_release_word_is_not_accessory_market_news(self):
        module = load_module()
        title = "A dedicated Apple Watch communication app is missing in watchOS 27"
        summary = (
            "watchOS 27 beta no longer includes the Walkie-Talkie app or Control Center tile. "
            "Walkie-Talkie app appears to be discontinued, and a public beta follows in July ahead of the official release this fall."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(module.classify_relevance_tier(title, summary, [], "9to5Mac")[0], "strong")

    def test_vision_pro_disney_story_does_not_merge_with_beats_headphones(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 Beats 新耳机再度曝光：撞色设计，预估支持定制耳罩等",
                (
                    "科技媒体 9to5Mac 昨日（6 月 11 日）发布博文，报道称继西班牙球员拉明 · 亚马尔"
                    "之后，韩国球员李刚仁在世界杯开赛期间佩戴新款 Beats 耳机现身。亚马尔此前展示的两款 "
                    "Beats 耳机中，耳罩、头带与机身颜色一致，而本次李刚仁佩戴的耳机耳罩与头带为霓虹黄。"
                    "该媒体认为 Beats 近期通过球员街拍持续制造悬念，预热新品发布。"
                ),
                source="IT之家",
                facts=[
                    "IT之家 6 月 13 日消息，科技媒体 9to5Mac 昨日（6 月 11 日）发布博文，报道称继西班牙球员拉明 · 亚马尔之后，韩国球员李刚仁在世界杯开赛期间佩戴新款 Beats 耳机现身。"
                ],
            ),
            article_for(
                module,
                "苹果 Vision Pro 头显成最大功臣：助力迪士尼改造乐园项目，献礼美国 250 周年",
                (
                    "科技媒体 Appleinsider 昨日（6 月 12 日）发布博文，报道称迪士尼为迎接美国建国 250 周年，"
                    "借助苹果 Vision Pro 头显，改造 EPCOT 经典飞行项目 Soarin，并将其更名为 Soarin' Across "
                    "America，带领游客飞跃美国标志性景观。迪士尼 Disney Unscripted 昨日放出幕后花絮视频，"
                    "展示了团队如何通过苹果 Vision Pro 头显改造该项目。"
                ),
                source="IT之家",
                facts=[
                    "IT之家 6 月 13 日消息，科技媒体 Appleinsider 昨日（6 月 12 日）发布博文，报道称迪士尼为迎接美国建国 250 周年，借助苹果 Vision Pro 头显，改造 EPCOT 经典飞行项目 Soarin，并将其更名为 Soarin' Across America，带领游客飞跃美国标志性景观。",
                    "IT之家注：EPCOT 位于佛罗里达 Walt Disney World，于 1982 年开放，设有众多未来科技主题项目与文化展馆，是迪士尼四大主题乐园之一。",
                ],
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        event_titles = " ".join(event.title for event in events)
        self.assertIn("Vision Pro", event_titles)
        self.assertIn("Beats", event_titles)

    def test_vision_pro_disney_chinese_followup_merges_with_english_original(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Vision Pro helped Disney re-engineer a classic EPCOT ride",
                (
                    "Just in time for America's 250th anniversary, Disney Imagineers tapped Apple Vision Pro "
                    "to help give one of their most iconic flight rides a patriotic makeover. The attraction "
                    "in question is Soarin, at EPCOT, which has been rebranded to Soarin' Across America. "
                    "Rather than focusing on wonders around the world or California, the ride takes guests "
                    "on an airborne adventure across the United States with new aerial footage, sound design, "
                    "projection checks, engineering work, and on-site previews at Walt Disney World in Florida."
                ),
                source="AppleInsider",
                facts=[
                    "Just in time for America's 250th anniversary, Disney Imagineers tapped Apple Vision Pro to help give one of their most iconic flight rides a patriotic makeover.",
                    "The attraction in question is Soarin, at EPCOT, which has been rebranded to Soarin' Across America for the 250th anniversary of the United States of America.",
                ],
            ),
            article_for(
                module,
                "苹果 Vision Pro 头显成最大功臣：助力迪士尼改造乐园项目，献礼美国 250 周年",
                (
                    "科技媒体 Appleinsider 昨日（6 月 12 日）发布博文，报道称迪士尼为迎接美国建国 250 周年，"
                    "借助苹果 Vision Pro 头显，改造 EPCOT 经典飞行项目 Soarin，并将其更名为 Soarin' Across "
                    "America，带领游客飞跃美国标志性景观。"
                ),
                source="IT之家",
                facts=[
                    "IT之家 6 月 13 日消息，科技媒体 Appleinsider 昨日（6 月 12 日）发布博文，报道称迪士尼为迎接美国建国 250 周年，借助苹果 Vision Pro 头显，改造 EPCOT 经典飞行项目 Soarin，并将其更名为 Soarin' Across America，带领游客飞跃美国标志性景观。",
                    "IT之家注：EPCOT 位于佛罗里达 Walt Disney World，于 1982 年开放，设有众多未来科技主题项目与文化展馆，是迪士尼四大主题乐园之一。",
                ],
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "IT之家"})

    def test_unreleased_beats_headphones_with_product_details_is_strong_hardware_news(self):
        module = load_module()
        title = "Antonee Robinson Shows Off Unreleased Two-Tone Beats Over-Ear Headphones at the World Cup"
        summary = (
            "Apple-owned Beats appears to be running an influencer seeding campaign for unreleased over-ear headphones through athletes, "
            "including Antonee Robinson. The pair has a white headband and housings with royal blue ear cups, "
            "new Beats headphones appeared in the FCC database last month, and it is unclear whether this is "
            "a new Beats Studio Pro version or a new product."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_pure_beats_marketing_without_product_details_stays_weak(self):
        module = load_module()
        title = "Beats launches World Cup campaign with Antonee Robinson"
        summary = (
            "Beats published a new commercial and social campaign starring football players, "
            "with Apple mentioned only as the parent company and no new model, certification, "
            "design, availability, or product-line details."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "marketing_ad")
        self.assertEqual(tier, "weak", reason)

    def test_same_unreleased_beats_headphones_story_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Antonee Robinson Shows Off Unreleased Two-Tone Beats Over-Ear Headphones at the World Cup",
                (
                    "Apple-owned Beats appears to be running an influencer seeding campaign for unreleased over-ear headphones through athletes, "
                    "including Antonee Robinson. The pair has a white headband and housings with royal blue ear cups, "
                    "new Beats headphones appeared in the FCC database last month, and it is unclear whether this is "
                    "a new Beats Studio Pro version or a new product."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "多名球星发图展示新款 Beats 头戴式耳机：提供撞色设计，有望为 Studio Pro 新一代产品",
                (
                    "美国男足球员 Antonee Robinson 展示了一款尚未发布的 Beats 头戴式耳机，采用白色头梁和皇家蓝耳罩的撞色设计。"
                    "近期多名世界杯球员佩戴新款 Beats 耳机，相关设备已经现身 FCC 数据库，外界猜测可能是新一代 Beats Studio Pro。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_chinese_site_boilerplate_is_not_extracted_as_key_facts(self):
        module = load_module()
        html = """
        <article>
          <p>IT之家 6 月 14 日消息，苹果今日宣布停止支持 16 款旧设备，涉及 iPhone、iPad、Mac 和 Apple Watch，多数设备将停留在当前系统版本。</p>
          <p>官方清单包括 iPhone X、iPhone 8、iPhone 8 Plus、第一代 iPad Pro、Apple Watch Series 3 等 16 款设备。</p>
          <p>当前位置：首页 &gt; Apple &gt; 文章详情</p>
          <p>相关阅读：苹果 iPhone 18 Pro 新配色曝光</p>
          <p>豫ICP备2023000000号-1，本站所有文章均包含本声明。</p>
        </article>
        """

        facts = module.extract_key_facts(html, "苹果停止支持 16 款旧设备", "IT之家")

        self.assertTrue(any("16 款" in fact for fact in facts))
        self.assertFalse(any("当前位置" in fact for fact in facts))
        self.assertFalse(any("相关阅读" in fact for fact in facts))
        self.assertFalse(any("ICP备" in fact for fact in facts))

    def test_iphone_mirroring_feature_update_is_os_app_not_compatibility(self):
        module = load_module()
        title = "macOS 27 brings three key upgrades to iPhone Mirroring"
        summary = (
            "iOS 27 and macOS 27 Golden Gate bring three updates to iPhone Mirroring: "
            "a resizable iPhone Mirroring window, Control Center access with CMD+4, "
            "and a refreshed app icon. The article notes that the feature currently works "
            "with iOS 27-compatible apps."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(module.classify_relevance_tier(title, summary, [], "9to5Mac")[0], "strong")

    def test_third_party_dock_macos_compatibility_stays_weak_and_does_not_merge_with_terminal_security(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "倍思推出 Spacemate RD1 Pro 扩展坞：15 合 1 设计，支持 Qi2.2 25W 磁吸无线充电",
                (
                    "这款第三方扩展坞集成 15 个接口，支持单屏 4K 120Hz 输出和双屏 4K 60Hz 输出，"
                    "Windows 系统下支持镜像、双屏扩展模式；macOS 平台则支持镜像、单屏扩展模式。"
                    "顶部带有 Qi2.2 磁吸无线充电模块，最高输出功率 25W。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "苹果解释 macOS 为何会拦截终端命令粘贴",
                (
                    "苹果更新支持文档，解释称在 macOS 26.4 中，若用户不常用终端，"
                    "且命令来自网站、聊天智能体、信息或邮件应用，系统可能阻止粘贴，"
                    "以防范依托 Terminal 传播的恶意软件。"
                ),
                source="IT之家",
            ),
        ]

        self.assertEqual(articles[0].relevance_tier, "weak")
        self.assertEqual(module.detect_event_kind(articles[1].title, articles[1].summary), "security_privacy")
        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertTrue(any("扩展坞" in event.title for event in events))
        self.assertTrue(any("终端" in event.title for event in events))


    def test_service_content_events_do_not_merge_on_generic_service_boilerplate(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "New 'Apple One' Perk Extends to Chase's Sapphire Reserve Credit Card",
                (
                    "Chase's Sapphire Reserve credit card now includes a complimentary Apple TV subscription "
                    "or an Apple One discount. Apple TV is available for $12.99 per month and Apple Music "
                    "requires a subscription."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple TV releases massive Widow's Bay themed playlist on Apple Music",
                (
                    "Apple TV has published Patricia's Sunset Cocktails, a 300-track Apple Music playlist "
                    "tied to episode 4 of the Apple TV series Widow's Bay. Apple Music requires a subscription."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "Eugene Levy's Apple TV travel series is coming back for season 4",
                (
                    "Apple TV renewed The Reluctant Traveler With Eugene Levy for season 4. "
                    "The travel series follows Levy visiting new destinations and will return on Apple TV."
                ),
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3)
        self.assertTrue(any("Chase" in event.title for event in events))
        self.assertTrue(any("Widow" in event.title for event in events))
        self.assertTrue(any("Eugene" in event.title for event in events))

    def test_ithome_listing_noise_does_not_merge_watchos_design_with_macos_naming(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果逐渐弱化 macOS 27 独立代号“Golden Gate”，转向强调数字版本号",
                (
                    "苹果在 WWDC 后逐渐弱化 macOS 27 的 Golden Gate 代号，更多强调数字版本号。"
                    "列表页附近还出现 iOS、watchOS、Liquid Glass 等系统更新相关新闻。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 watchOS 27 微调 Apple Watch 液态玻璃设计，暂未引入透明度滑块",
                (
                    "9to5Mac 发现 watchOS 27 没有提供类似 iOS 27、iPadOS 27 和 macOS 27 的 Liquid Glass 透明度滑块，"
                    "但 Apple Watch 的通知、控制中心和系统控件外观已有细微变化。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertTrue(any("Golden Gate" in event.title for event in events))
        self.assertTrue(any("液态玻璃" in event.title for event in events))

    def test_9to5_service_subscription_boilerplate_is_not_key_fact(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-06-16T15:00:00+00:00" />
            <meta property="og:description" content="Apple TV renewed Eugene Levy's travel series for season 4." />
          </head>
          <body>
            <div class="container med post-content">
              <p>Apple TV renewed The Reluctant Traveler With Eugene Levy for season 4, continuing the unscripted travel series with new destinations.</p>
              <p>The show follows Levy as he visits hotels, local communities, and travel destinations outside his comfort zone.</p>
              <p>Apple TV is available for $12.99 per month after a seven-day free trial. Apple Music is available for $10.99 per month after free trial.</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/16/eugene-levys-apple-tv-travel-series-is-coming-back-for-season-4/",
            title="Eugene Levy's Apple TV travel series is coming back for season 4",
        )

        _title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("season 4", combined)
        self.assertNotIn("$12.99", combined)
        self.assertNotIn("$10.99", combined)

    def test_apple_service_offer_discount_fact_is_not_treated_as_subscription_boilerplate(self):
        module = load_module()
        fact = (
            "For example, a Reddit user showed that their Apple One Premier plan has been discounted "
            "to $21.95 per month, down from the regular price of $37.95 per month. "
            "This is actually a $16/month discount, which is slightly higher than advertised."
        )

        self.assertFalse(module.fact_noise(fact))

    def test_ithome_post_content_scope_ignores_sidebar_or_related_paragraphs(self):
        module = load_module()
        source = source_named(module, "IT之家")
        page = """
        <html>
          <head>
            <meta name="description" content="苹果正在弱化 macOS 27 Golden Gate 代号，转向更强调数字版本号。" />
          </head>
          <body>
            <div class="post_content" id="paragraph">
              <p>IT之家 6 月 17 日消息，苹果在官网文档中逐渐弱化 macOS 27 Golden Gate 代号，转向更强调数字版本号。</p>
              <p>苹果把部分支持文档中的 macOS Sequoia、macOS Ventura 等名称替换为 macOS 15、macOS 13 等数字版本。</p>
            </div>
            <div class="fr fx">
              <p>苹果 watchOS 27 微调 Apple Watch 液态玻璃设计，暂未引入透明度滑块。</p>
            </div>
          </body>
        </html>
        """
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/965/150.htm",
            title="苹果逐渐弱化 macOS 27 独立代号“Golden Gate”，转向强调数字版本号",
        )

        _title, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("Golden Gate", combined)
        self.assertNotIn("液态玻璃", combined)

    def test_official_apple_store_third_party_accessory_is_hardware_market(self):
        module = load_module()
        title = "398 元：苹果上架 PopSockets 新手柄兼支架，兼容 iPhone 17 等"
        summary = (
            "苹果中国在线官网上线 PopSockets Low-Pro Grip & Stand 手柄兼支架，"
            "兼容 MagSafe，适用于 iPhone 17、iPhone Air 等机型，售价为 398 元，厚度仅 2.5 毫米。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "hardware_products")


if __name__ == "__main__":
    unittest.main()
