import importlib.util
import sys
import unittest
from unittest import mock
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


def event_for(module, article):
    return module.Event(
        event_id="test-event",
        category=article.category,
        title=article.title,
        summary=article.summary,
        key_facts=list(article.key_facts),
        published_utc=article.published_utc,
        published_raw=article.published_raw,
        published_source=article.published_source,
        confidence=article.confidence,
        articles=[article],
        tokens=set(article.tokens),
        event_kind=article.event_kind,
        relevance_tier=article.relevance_tier,
        relevance_reason=article.relevance_reason,
        regions=set(article.regions),
    )


class RelevanceRuleTests(unittest.TestCase):
    def test_cached_score_terms_matches_list_tuple_and_set_inputs(self):
        module = load_module()
        text = "Apple released iOS 27 beta 3 for iPhone and iPad."

        self.assertEqual(module.score_terms(text, ["apple", "ios", "macos"]), 2)
        self.assertEqual(module.score_terms(text, ("apple", "ios", "macos")), 2)
        self.assertEqual(module.score_terms(text, {"apple", "ios", "macos"}), 2)

    def test_primary_topic_facet_cache_returns_independent_sets(self):
        module = load_module()
        title = "Apple and Broadcom Extend Chip Supply Deal to 2031"
        summary = "Apple and Broadcom extended their chip supply deal for wireless components."

        first = module.primary_topic_facets(title, summary)
        self.assertIn("apple-broadcom-chip-supply-deal", first)
        first.add("mutated-test-facet")

        second = module.primary_topic_facets(title, summary)
        self.assertIn("apple-broadcom-chip-supply-deal", second)
        self.assertNotIn("mutated-test-facet", second)

    def test_os_beta_release_is_not_downgraded_as_personal_settings_guide(self):
        module = load_module()
        title = "Apple Seeds Fourth iOS 26.6 and iPadOS 26.6 Betas to Developers"
        summary = (
            "Apple today seeded the fourth betas of upcoming iOS 26.6 and iPadOS 26.6 "
            "updates to developers for testing purposes. Registered developers can "
            "download the betas from the Settings app by going to General and selecting "
            "Software Update. The update primarily focuses on bug fixes and performance improvements."
        )

        self.assertFalse(
            module.is_personal_usage_or_settings_guide_without_new_apple_action(title, summary)
        )
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "strong", reason)

    def test_os_wallpaper_release_is_not_downgraded_as_personal_settings_guide(self):
        module = load_module()
        title = "macOS Golden Gate Gets New Wallpaper"
        summary = (
            "With the third beta of macOS 27, Apple added new Golden Gate-themed wallpaper "
            "options to the Mac. Golden Gate Sunset and Golden Gate Night animate when "
            "unlocking the Mac and can be set as a screen saver. In the Photos section "
            "of the Settings app, Apple also added a new Show Rating Controls toggle."
        )

        self.assertFalse(
            module.is_personal_usage_or_settings_guide_without_new_apple_action(title, summary)
        )
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "strong", reason)

    def test_watchos_siri_ai_release_is_not_downgraded_as_device_mod_project(self):
        module = load_module()
        title = "watchOS 27第三个测试版将Siri AI带入Apple Watch"
        summary = (
            "苹果在最新发布的 watchOS 27 第三个开发者测试版中，为 Apple Watch 用户正式开放"
            "全新升级的 Siri AI，并引入独立的 Siri 应用。该应用可在 Dynamic App Grid "
            "界面中启动，并在同一 Apple ID 下同步对话记录。随着测试版推送，改造后的 Siri AI "
            "以独立应用的形式登陆 Apple Watch 平台。"
        )

        self.assertFalse(
            module.is_third_party_hardware_mod_or_repair_story_without_apple_action(title, summary)
        )
        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")
        self.assertEqual(tier, "strong", reason)

    def test_foldable_iphone_mass_production_story_stays_strong_despite_market_context(self):
        module = load_module()
        title = "史上最贵iPhone蓄势待发 苹果首款折叠屏手机开始量产"
        summary = (
            "据多方爆料，苹果首款折叠屏 iPhone 预计定名为 iPhone Ultra，并有望在今年 9 月发布。"
            "赣州富士康发布招聘文章，招聘 18 至 50 岁员工，主要从事苹果手机精密组件的生产与加工，"
            "供应链信息显示苹果首款折叠屏手机已进入量产准备阶段。三星、华为、荣耀、OPPO、vivo、"
            "小米等厂商均已推出折叠屏产品，苹果入局后有望进一步拉高折叠屏手机市场热度，"
            "并推动这一品类进入新的竞争阶段。"
        )

        self.assertTrue(module.is_foldable_iphone_supply_chain_story(summary))
        self.assertFalse(module.is_broad_multi_vendor_market_report(summary, title))
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "strong", reason)

    def test_integer_major_os_beta_release_facets_include_platform_and_round(self):
        module = load_module()
        text = "Apple Seeds Third iOS 27 and iPadOS 27 Betas to Developers"

        facets = module.os_release_facets_from_text(text)

        self.assertIn("os-release-version-27", facets)
        self.assertIn("os-release-beta", facets)
        self.assertIn("os-release-beta-3", facets)
        self.assertIn("platform-ios", facets)
        self.assertIn("platform-ipados", facets)

    def test_same_integer_major_os_beta_release_merges_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Apple Seeds Third iOS 27 and iPadOS 27 Betas to Developers",
            "Apple today seeded the third betas of iOS 27 and iPadOS 27 to developers for testing purposes.",
            source="MacRumors",
        )
        nine_to_five = article_for(
            module,
            "iOS 27 beta 3 now available for developers",
            "Apple has released the third iOS 27 beta for developer testing. iOS 27 beta 3 replaces the second iOS 27 beta.",
            source="9to5Mac",
        )

        self.assertTrue(module.should_merge(macrumors, event_for(module, nine_to_five)))

    def test_system_wallpaper_merges_only_when_platform_matches(self):
        module = load_module()
        macrumors_wallpaper = article_for(
            module,
            "macOS Golden Gate Gets New Wallpaper",
            "With the third beta of macOS 27, Apple added new Golden Gate-themed wallpaper options to the Mac.",
            source="MacRumors",
        )
        nine_to_five_wallpaper = article_for(
            module,
            "macOS 27 Golden Gate adds these new wallpapers and screen savers to your Mac",
            "Today’s macOS 27 Golden Gate beta 3 release includes two new wallpaper and screen saver options for your Mac.",
            source="9to5Mac",
        )
        ios_feature_roundup = article_for(
            module,
            "Here's what's new with iOS 27 beta 3",
            "Apple released iOS 27 beta 3 today. The third beta adds a new wallpaper animation, Siri voice customization, and Photos improvements.",
            source="9to5Mac",
        )

        self.assertTrue(module.should_merge(macrumors_wallpaper, event_for(module, nine_to_five_wallpaper)))
        self.assertFalse(module.should_merge(ios_feature_roundup, event_for(module, macrumors_wallpaper)))

    def test_beta_feature_title_is_not_release_availability_story(self):
        module = load_module()
        feature = article_for(
            module,
            "iOS 27 beta 3 makes it easier to adjust AirPods Adaptive mode intensity",
            "After Apple released iOS 27 beta 3, the update adds a new way to adjust AirPods Adaptive Audio intensity from the mode picker.",
            source="9to5Mac",
        )
        generic_beta = article_for(
            module,
            "macOS 27 Golden Gate beta 3 now available for developers",
            "Apple is rolling out macOS 27 Golden Gate beta 3 for developers ahead of the public beta.",
            source="9to5Mac",
        )

        self.assertFalse(module.is_os_release_availability_article(feature))
        self.assertFalse(module.should_merge(feature, event_for(module, generic_beta)))

    def test_major_beta_does_not_merge_with_point_release_background_mention(self):
        module = load_module()
        ios_27_beta = article_for(
            module,
            "Apple Seeds Third iOS 27 and iPadOS 27 Betas to Developers",
            "Apple seeded the third betas of iOS 27 and iPadOS 27 to developers.",
            source="MacRumors",
        )
        ios_26_beta = article_for(
            module,
            "Apple releases iOS 26.6 beta 4 for iPhone, here’s what to expect",
            "Apple released the fourth iOS 26.6 developer beta, with the update preparing minor iPhone changes before iOS 27.",
            source="9to5Mac",
        )

        self.assertFalse(module.should_merge(ios_27_beta, event_for(module, ios_26_beta)))

    def test_broad_apple_ai_facet_alone_does_not_merge_distinct_features(self):
        module = load_module()
        home_icloud = article_for(
            module,
            "Apple Intelligence Home Features Require 2TB iCloud+ Plan in iOS 27",
            "Apple Intelligence camera features in the Home app will require an iCloud+ plan starting at 2TB.",
            source="MacRumors",
        )
        watch_siri = article_for(
            module,
            "Siri AI Comes to Apple Watch in watchOS 27 Beta 3",
            "With watchOS 27 beta 3, Apple added support for Siri AI and the Siri app, so Apple Watch users can now use the features from their wrist.",
            source="MacRumors",
        )

        self.assertFalse(module.should_merge(home_icloud, event_for(module, watch_siri)))

    def test_os_release_title_primary_facet_wins_over_service_terms(self):
        module = load_module()
        title = "Apple Seeds tvOS 27 Beta 3 to Developers"
        summary = "Apple seeded the third tvOS 27 beta to developers for testing on Apple TV."

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("os-release-beta", facets)
        self.assertIn("os-release-version-27", facets)
        self.assertNotIn("apple-tv-content", facets)

    def test_siri_voice_customization_has_specific_facet(self):
        module = load_module()
        title = "New in iOS 27 beta 3: Siri AI voice customization options"
        summary = "Apple added Siri AI voice customization controls for speaking pace and expressivity."

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("siri-voice-customization", facets)

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

    def test_apple_showcased_research_paper_is_apple_research(self):
        module = load_module()
        title = "Apple to showcase computer vision studies at annual conference in June"
        summary = (
            "Apple will present several computer vision research papers at CVPR, "
            "including studies from Apple's machine learning researchers."
        )

        self.assertTrue(module.is_apple_research_candidate(f"{title} {summary}"))
        self.assertEqual(module.detect_event_kind(title, summary), "apple_research")

    def test_non_apple_societal_iphone_research_stays_weak(self):
        module = load_module()
        title = "最新研究：iPhone是一种高级避孕工具"
        summary = (
            "NBER 最新发表的论文称，2007 年 iPhone 发布后美国生育率开始下降，"
            "研究人员对比 AT&T 覆盖率和生育率变化，认为 iPhone 普及可以解释部分下降。"
            "另一项大学研究覆盖 128 个国家，讨论智能手机普及和青少年生育率。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertFalse(module.is_apple_research_candidate(f"{title} {summary}"))
        self.assertEqual(tier, "weak", reason)

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

    def test_ithome_daily_brief_candidate_is_filtered_before_detail_fetch(self):
        module = load_module()
        source = source_named(module, "IT之家")
        daily_brief = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/969/735.htm",
            title="IT早报 0629：央视揭秘欧洲“缺”空调原因；曝苹果寻求从长鑫采购内存芯片",
            summary="苹果正寻求从长鑫采购内存芯片，Mac Studio 路线图也有新消息。",
        )
        spaced_daily_brief = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/969/736.htm",
            title="IT 早报 0629：曝苹果寻求从长鑫采购内存芯片",
            summary="苹果正寻求从长鑫采购内存芯片。",
        )
        ordinary_article = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/969/739.htm",
            title="（更新：已恢复）苹果地图搜索、导航等服务出现服务中断",
            summary="苹果地图搜索、导航服务和查找服务一度异常，随后恢复可用。",
        )
        non_ithome_daily_brief = module.Candidate(
            source="快科技",
            url="https://news.mydrivers.com/1/1132/1132999.htm",
            title="IT早报：苹果发布 iOS 27 beta 3",
            summary="苹果发布 iOS 27 beta 3，新增系统功能并修复多个问题。",
        )

        self.assertFalse(module.is_relevant_candidate(daily_brief, source))
        self.assertFalse(module.is_relevant_candidate(spaced_daily_brief, source))
        self.assertTrue(module.is_relevant_candidate(ordinary_article, source))
        self.assertTrue(module.is_relevant_candidate(non_ithome_daily_brief, source_named(module, "快科技")))

    def test_ifanr_daily_brief_candidate_is_filtered_before_detail_fetch(self):
        module = load_module()
        source = source_named(module, "爱范儿")
        daily_brief = module.Candidate(
            source="爱范儿",
            url="https://www.ifanr.com/1670360",
            title="早报｜曝 iPhone 18 标准版内存升至 9GB / 自变量机器人 2 个月完成 4 轮融资",
            summary="曝 iPhone 18 标准版内存升至 9GB，另有多条非 Apple 科技新闻。",
        )
        spaced_daily_brief = module.Candidate(
            source="爱范儿",
            url="https://www.ifanr.com/1670361",
            title="早 报｜苹果发布 iOS 26.5.2 安全更新",
            summary="苹果发布系统更新。",
        )
        ordinary_article = module.Candidate(
            source="爱范儿",
            url="https://www.ifanr.com/1670300",
            title="苹果发布 iOS 26.5.2 安全更新，修复多项系统漏洞",
            summary="苹果向 iPhone 用户推送 iOS 26.5.2，提前发布安全修复。",
        )

        self.assertFalse(module.is_relevant_candidate(daily_brief, source))
        self.assertFalse(module.is_relevant_candidate(spaced_daily_brief, source))
        self.assertTrue(module.is_relevant_candidate(ordinary_article, source))

    def test_duplicate_candidates_merge_context_before_relevance_filtering(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        api_candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/29/silo-season-3-hailed-as-best-season-yet-here-are-the-first-reviews/",
            title="Silo season 3 hailed as ‘best season yet,’ here are the first reviews",
            summary=(
                "Silo returns later this week for season 3, and the first reviews indicate "
                "the new season could be the show’s best yet thanks in part to a new split-timeline story."
            ),
            feed_time_raw="2026-06-29T18:21:00+00:00",
        )
        category_context_candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/29/silo-season-3-hailed-as-best-season-yet-here-are-the-first-reviews/#more-1058808",
            title="Expand Expanding Close",
            context="apple tv",
        )

        merged = module.merge_duplicate_candidates([api_candidate, category_context_candidate])

        self.assertEqual(len(merged), 1)
        self.assertIn("Silo season 3", merged[0].title)
        self.assertIn("split-timeline", merged[0].summary)
        self.assertIn("apple tv", merged[0].context)
        self.assertTrue(module.is_relevant_candidate(merged[0], source))

    def test_roundup_variant_does_not_inherit_global_context_for_non_apple_item(self):
        module = load_module()
        source = source_named(module, "爱范儿")
        inherited_context = "apple iphone apple tv apple intelligence"
        variant_context = module.context_for_article_variant(is_roundup=True, candidate_context=inherited_context)
        non_apple_item = module.Candidate(
            source="爱范儿",
            url="https://www.ifanr.com/1670360",
            title="Jeep 未来四年连发三款新车，将与东风联合开发大型 SUV",
            summary="Jeep 将在未来四年推出三款新车，并与东风联合开发大型 SUV。",
            context=variant_context,
        )

        self.assertEqual(variant_context, "")
        self.assertFalse(module.is_relevant_candidate(non_apple_item, source))

    def test_roundup_variants_keep_only_apple_subject_items(self):
        module = load_module()
        variants = module.roundup_article_variants(
            "早报｜曝 iPhone 18 标准版内存升至 9GB / 理想汽车进入澳门市场",
            "曝 iPhone 18 标准版内存升至 9GB",
            "苹果 iPhone 18 标准版内存升至 9GB，理想汽车进入澳门市场。",
            [
                "曝 iPhone 18 标准版内存升至 9GB，分析师称苹果将提高内存容量。",
                "理想汽车进入澳门市场，首家零售中心开业，海外版智能系统支持 Apple CarPlay、Spotify 等本地化应用。",
                "Jeep 未来四年连发三款新车，将与东风联合开发大型 SUV。",
            ],
        )
        titles = " ".join(title for title, _, _ in variants)

        self.assertIn("iPhone 18", titles)
        self.assertNotIn("理想汽车", titles)
        self.assertNotIn("Jeep", titles)

    def test_roundup_apple_items_expand_to_separate_article_variants(self):
        module = load_module()
        original_title = "Daily briefing: Apple foldable iPhone suppliers; Apple closes three U.S. stores"
        title = "供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布"
        summary = (
            "4、供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布。"
            "19、苹果美国关闭三家 Apple Store，部分门店员工遭区别对待引争议。"
        )
        facts = [
            "4、供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布。",
            "19、苹果美国关闭三家 Apple Store，部分门店员工遭区别对待引争议。",
        ]

        variants = module.roundup_article_variants(original_title, title, summary, facts)

        self.assertEqual(len(variants), 2)
        self.assertIn("折叠屏 iPhone", variants[0][0])
        self.assertFalse(variants[0][0].startswith("4、"))
        self.assertFalse(variants[0][1].startswith("4、"))
        self.assertNotIn("Apple Store", variants[0][1])
        self.assertIn("Apple Store", variants[1][0])
        self.assertFalse(variants[1][0].startswith("19、"))
        self.assertFalse(variants[1][1].startswith("19、"))
        self.assertNotIn("折叠屏 iPhone", variants[1][1])

    def test_foldable_iphone_supply_chain_roundup_item_merges_with_standalone_story(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布",
                "供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布。",
                source="IT之家",
            ),
            article_for(
                module,
                "供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布",
                "一位苹果供应链公司人士表示，截至目前，其得到的目标指引是，首款折叠屏 iPhone 将于 2026 年秋季发布。",
                source="IT之家",
                facts=[
                    "一位苹果供应链公司人士表示，截至目前，其得到的目标指引是，首款折叠屏 iPhone 将于 2026 年秋季发布。"
                ],
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertIn("foldable-iphone-supply-chain", module.event_primary_facets(events[0]))

    def test_foldable_iphone_supply_chain_merges_when_wording_differs(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布",
                "相关厂商已向苹果首款折叠屏 iPhone 小批量供货，目标指引是 2026 年秋季发布。",
                source="IT之家",
            ),
            article_for(
                module,
                "Apple foldable phone suppliers enter early production stage",
                "Multiple suppliers have started small-batch production work for Apple's first folding iPhone ahead of a planned fall launch.",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)

    def test_non_apple_title_with_apple_pricing_background_stays_weak(self):
        module = load_module()
        title = "消息称今年 Q3-Q4 的安卓旗舰 SoC 机型起步价可能接近 6 开头"
        summary = (
            "供应链消息称，安卓旗舰 SoC 机型起步价可能上调。文章后文顺带提到，"
            "苹果 CEO Tim Cook 计划因存储芯片成本上升而上调 iPhone 等产品售价。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)

    def test_apple_product_price_increase_story_stays_hardware_before_os_feature_rules(self):
        module = load_module()
        title = "等不到今年的秋季发布会 古尔曼预判苹果很快涨价"
        summary = (
            "苹果 CEO Tim Cook 表示，受 AI 热潮驱动，DRAM 与 NAND 存储器芯片短缺及价格暴涨，"
            "苹果产品涨价不可避免。TechInsights 估算，若全部转嫁成本，下一代 iPhone 18 Pro "
            "起售价或升至 1299 美元，Mac 与 iPad 产品线同样面临调价压力。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_english_apple_price_increase_story_is_hardware_even_without_product_in_title(self):
        module = load_module()
        title = "Three reasons to suspect the Apple price increases could be imminent"
        summary = (
            "Tim Cook said price increases are unavoidable. The price hikes could affect iPhone, "
            "iPad, and Mac products sooner than the fall launch."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_ithome_apple_price_candidate_reaches_detail_review(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/968/675.htm",
            title="苹果提高 Mac、iPad、Vision Pro、HomePod 等产品价格，以应对内存短缺",
            summary="苹果公司称，人工智能数据中心的快速扩张导致内存需求激增。提高 Mac、iPad 等系列产品价格以应对内存短缺。",
            feed_time_raw="2026-06-25T20:43:30.1630000+08:00",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))

    def test_ithome_official_back_to_school_candidate_reaches_detail_review(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/968/725.htm",
            title="Mac 和 iPad 涨价后，古尔曼预测苹果下周开启返校季促销活动",
            summary=(
                "彭博社记者古尔曼透露，苹果一年一度的返校季促销活动预计将在下周启动。"
                "此举或为缓冲近期 Mac、iPad 产品线大幅涨价带来的影响，符合资格的学生和教育工作者购买指定产品可获赠配件或礼品卡。"
            ),
            feed_time_raw="2026-06-26T00:42:39.9270000+08:00",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))

    def test_ithome_hardware_market_title_without_summary_reaches_detail_review(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/968/747.htm",
            title="CounterPoint：苹果 iPhone Ultra 助推下，2026 全球折叠手机加权平均批发价预估上涨 18%",
        )

        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "hardware_market")
        self.assertTrue(module.is_relevant_candidate(candidate, source))

    def test_third_party_retail_discount_candidate_stays_filtered(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/968/999.htm",
            title="京东苹果 iPad 今日促销立减 300 元，限时优惠",
            summary="电商平台推出普通零售促销活动，用户可领取优惠券购买 iPad。",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))

    def test_back_to_school_promo_does_not_merge_with_current_price_increase(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                (
                    "Apple dramatically increased device prices across multiple product lines after memory "
                    "and storage costs rose quickly. Apple said it had shielded customers but now needs to "
                    "raise prices on products including iPad and Mac."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "Mac 和 iPad 涨价后，古尔曼预测苹果下周开启返校季促销活动",
                (
                    "彭博社记者古尔曼透露，苹果一年一度的返校季促销活动预计将在下周启动。"
                    "此举或为缓冲近期 Mac、iPad 产品线大幅涨价带来的影响，符合资格的学生和教育工作者购买指定产品可获赠配件或礼品卡。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_future_iphone_price_forecast_does_not_merge_with_current_price_increase(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                (
                    "Apple dramatically increased device prices across multiple product lines after memory "
                    "and storage costs rose quickly. Apple said it had shielded customers but now needs to "
                    "raise prices on products including iPad and Mac."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "消息称苹果 iPhone 18 Pro / Max 及 Ultra 阔折叠均为“万元机”",
                (
                    "苹果已上调 Mac、iPad 等产品售价，称涨价因存储元件成本上涨，后续或仍有调价空间。"
                    "业内透露 iPhone 18 Pro 系列及首款折叠屏 Ultra 都将万元起售。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_regional_reseller_retroactive_price_action_does_not_merge_with_current_price_increase(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Explains Why It Raised Prices on 14 Products Today",
                (
                    "Apple said memory and storage component costs have risen unprecedentedly. "
                    "The company said it has shielded customers so far but now needs to raise "
                    "prices across Mac, iPad, Vision Pro, Apple TV, and HomePod products."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果英国经销商被指擅自涨价：买家调价前下单 128G 内存版 MacBook Pro，仍被要求补差价",
                (
                    "英国授权经销商 KRCS 在用户 6 月 5 日全额下单 M5 Max 处理器 +128GB 内存 "
                    "MacBook Pro 后，因苹果官方涨价要求补足差价，否则取消订单并全额退款。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "苹果涨价经销商趁火打劫！已全款下单MacBook：还要补2万元差价",
                (
                    "苹果因存储短缺上调 MacBook Pro 售价后，部分经销商开始对涨价前已全款下单的订单追要差价，"
                    "其中包括英国苹果高级经销商 KRCS。Reddit 用户 sw1000 称，他 6 月 5 日全款下单购买一台 "
                    "128GB 统一内存的 M5 Max MacBook Pro，KRCS 后来要求补齐涨价后的差价或者全额退款。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 2, titles_by_event)
        reseller_events = [
            event for event in events if "KRCS" in " ".join(article.summary for article in event.articles)
        ]
        self.assertEqual(len(reseller_events), 1, titles_by_event)
        self.assertEqual({article.source for article in reseller_events[0].articles}, {"IT之家", "快科技"})

    def test_generic_chip_image_leak_does_not_merge_with_supplier_data_breach(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Leaked A20 Pro Image Hints at iPhone 18 Pro Performance Gains",
                "An alleged image of the iPhone 18 Pro motherboard shows the A20 Pro chip will use WMCM packaging for performance gains.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple Tata Leak Reveals iPhone 18 Pro Drop Test Files",
                "Reuters says Tata files posted on the dark web include confidential Apple iPhone 18 Pro drop test photos, circuit-board chips, battery and camera components.",
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro dark web breach includes drop-test documents",
                "The files allegedly stolen from Apple supplier Tata include iPhone 18 Pro drop-test images and internal hardware documents.",
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 2, titles_by_event)
        chip_events = [event for event in events if "A20 Pro Image" in " ".join(article.title for article in event.articles)]
        breach_events = [event for event in events if "Tata" in " ".join(article.title for article in event.articles)]
        self.assertEqual(len(chip_events), 1, titles_by_event)
        self.assertEqual(len(breach_events), 1, titles_by_event)
        self.assertEqual(len(breach_events[0].articles), 2, titles_by_event)

    def test_iphone_hardware_rumor_subtopics_do_not_form_one_large_cluster(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Leaked A20 Pro Image Hints at iPhone 18 Pro Performance Gains",
                "An alleged image of the iPhone 18 Pro motherboard shows the A20 Pro chip will use WMCM packaging and side-mounted DRAM for better cooling.",
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro is Just a Few Months Away With These 10 New Features",
                (
                    "A broad roundup says the iPhone 18 Pro may debut in September, use an A20 Pro chip, "
                    "feature a smaller Dynamic Island, and be affected by Tata files leaked on the dark web."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro launch date likely September 8, says Gurman",
                "Bloomberg says Apple's iPhone 18 Pro models and foldable iPhone are most likely to debut on September 8, 2026.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple Tata Leak Reveals iPhone 18 Pro Drop Test Files",
                "Reuters says Tata files posted on the dark web include confidential Apple iPhone 18 Pro drop test photos, circuit-board chips, battery and camera components.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果 iPhone 18 Pro 被曝配备更大均热板",
                "爆料称 iPhone 18 Pro 的 VC 均热板散热面积非常大，一直延伸到手机顶部。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertGreaterEqual(len(events), 3, titles_by_event)
        self.assertTrue(any("A20 Pro Image" in title for title in titles_by_event), titles_by_event)
        self.assertTrue(any("launch date" in title for title in titles_by_event), titles_by_event)
        self.assertTrue(any("Tata" in title for title in titles_by_event), titles_by_event)
        self.assertFalse(
            any(
                "10 New Features" in title and "A20 Pro Image" in title and "launch date" in title and "Tata" in title
                for title in titles_by_event
            ),
            titles_by_event,
        )

    def test_iphone_launch_timing_does_not_absorb_memory_supply_or_chip_process_topics(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro and Ultra Launch Date: Here's When They'll Likely Debut",
                "Bloomberg's Mark Gurman says Apple's iPhone 18 Pro models and foldable iPhone are most likely to debut on September 8, 2026.",
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 With 9GB of RAM Still Won't Support Two New iOS 27 Features",
                "The lower-end iPhone 18 and iPhone 18e will have 9GB of RAM but still miss two Apple Intelligence features that need 12GB.",
                source="MacRumors",
            ),
            article_for(
                module,
                "郭明錤：苹果寻求采购长鑫存储内存原因，是内存供需缺口持续扩大至明年",
                "郭明錤称苹果寻求采购长鑫存储内存芯片，是因为 LPDDR 内存供需缺口将持续扩大至 2027 年，A20 芯片拉货量可能低于目标。",
                source="IT之家",
            ),
            article_for(
                module,
                "每片晶圆30万元也照买！苹果抢占1.4纳米制程深层布局曝光",
                "苹果预计 2026 年和 2027 年采用台积电 2 纳米 N2 与 N2P 制程，并在 2028 年为 A22 Pro 芯片换装 1.4 纳米工艺。",
                source="快科技",
            ),
            article_for(
                module,
                "苹果 iPad mini 8 主板首曝，配 A20 Pro 芯片",
                "消息源分享苹果 iPad mini 8 主板图片，显示该机配备 A20 Pro 芯片。",
                source="IT之家",
            ),
            article_for(
                module,
                "iPhone 18 Pro Max真机首次泄露：横向大矩阵镜组+全新深空灰配色",
                "塔塔电子遭遇网络安全事件，暗网泄露 iPhone 18 Pro Max 跌落测试视频和供应商清单。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]
        launch_event_titles = [title for title in titles_by_event if "Launch Date" in title or "debute" in title]

        self.assertGreaterEqual(len(events), 5, titles_by_event)
        self.assertTrue(launch_event_titles, titles_by_event)
        launch_event_title = launch_event_titles[0]
        self.assertNotIn("9GB of RAM", launch_event_title)
        self.assertNotIn("长鑫存储", launch_event_title)
        self.assertNotIn("1.4纳米", launch_event_title)
        self.assertNotIn("iPad mini 8", launch_event_title)
        self.assertNotIn("真机首次泄露", launch_event_title)

    def test_os_beta_release_sources_merge_separately_from_security_release(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Releases Third watchOS 26.6, tvOS 26.6 and visionOS 26.6 Betas",
                "Apple today provided developers with the third betas of upcoming watchOS 26.6, tvOS 26.6, and visionOS 26.6 updates for testing purposes.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple Seeds Third iOS 26.6 and iPadOS 26.6 Betas to Developers",
                "Apple seeded the third betas of iOS 26.6 and iPadOS 26.6 to developers, two weeks after beta 2.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple releases iOS 26.6 beta 3 for iPhone, here’s what to expect",
                "Apple released the third iOS 26.6 developer beta, with the update preparing minor iPhone changes before iOS 27.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果 iOS / iPadOS 26.6 开发者预览版 Beta 3 发布",
                "苹果向 iPhone 和 iPad 用户推送 iOS / iPadOS 26.6 开发者预览版 Beta 3，内部版本号 23G5052d。",
                source="IT之家",
            ),
            article_for(
                module,
                "iOS 26.5.2 Patches More Than 25 Security Vulnerabilities",
                "Apple released iOS 26.5.2 and iPadOS 26.5.2 with fixes for more than 25 security vulnerabilities.",
                source="MacRumors",
            ),
            article_for(
                module,
                "iOS 26.5.2 has fixes for 25 security issues on iPhone, details here",
                "Apple released iOS 26.5.2 for iPhone with patches for nearly 30 security issues.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Leaker outlines iPhone lineup for next year, with six new models coming",
                "A leaker says Apple plans six new iPhone models next year after the iOS 27 cycle, including an iPhone 18e and iPhone Ultra.",
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 3, titles_by_event)
        beta_events = [event for event in events if "26.6" in " ".join(article.title for article in event.articles)]
        security_events = [event for event in events if "26.5.2" in " ".join(article.title for article in event.articles)]
        lineup_events = [event for event in events if "iPhone lineup" in " ".join(article.title for article in event.articles)]
        self.assertEqual(len(beta_events), 1, titles_by_event)
        self.assertEqual(len(security_events), 1, titles_by_event)
        self.assertEqual(len(lineup_events), 1, titles_by_event)
        self.assertEqual({article.source for article in beta_events[0].articles}, {"MacRumors", "9to5Mac", "IT之家"})
        self.assertEqual({article.source for article in security_events[0].articles}, {"MacRumors", "9to5Mac"})
        self.assertEqual({article.source for article in lineup_events[0].articles}, {"9to5Mac"})

    def test_security_update_title_facets_resist_related_beta_noise(self):
        module = load_module()
        title = "iOS 26.5.2 has fixes for 25+ security issues on iPhone, details here"
        noisy_summary = (
            "Apple released iOS 26.5.2 for iPhone with patches for nearly 30 security issues. "
            "Related coverage also mentions iOS 26.6 beta 3 rolling out to developers."
        )

        facets = module.primary_topic_facets(title, noisy_summary)

        self.assertIn("os-release-version-26-5-2", facets)
        self.assertIn("os-release-security", facets)
        self.assertNotIn("os-release-version-26-6", facets)
        self.assertNotIn("os-release-beta", facets)

    def test_multi_version_os_update_context_does_not_bridge_release_events(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple releases iOS 26.6 beta 3 for iPhone, here’s what to expect",
                "Apple released iOS 26.6 beta 3 to developers with minor iPhone changes.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "iOS 26.5.2 has fixes for 25+ security issues on iPhone, details here",
                "Apple released iOS 26.5.2 for iPhone with patches for nearly 30 security issues.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple accelerates security updates in response to AI-powered hacking risks",
                (
                    "Apple's iOS 26.5.2 security release arrived the same day as iOS 26.6 beta 3, "
                    "showing a broader push to ship urgent security fixes faster."
                ),
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 3, titles_by_event)
        self.assertFalse(
            any("26.6 beta" in title and "26.5.2" in title for title in titles_by_event),
            titles_by_event,
        )

    def test_apple_acquisition_does_not_merge_with_antitrust_case(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Acquires Award-Winning App 'Play'",
                "Apple notified the European Commission that it would acquire certain assets and hire employees from Rabbit 3 Times, the company behind the app design tool Play.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple Design award winner acquired by Apple for new Swift tools",
                "Apple has now bought Rabbit 3 Times, which made a visual Swift development tool called Play, after previously giving it an Apple Design Award.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "Apple says India built its App Store antitrust case on copy-pasted claims from rivals",
                "Apple asked India to scrap a CCI App Store antitrust investigation, arguing the report copied rival claims and threatens its integrated business model.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "India's antitrust case is plagiarized and should be scrapped, says Apple",
                "Apple told regulators that India's App Store antitrust case should be withdrawn because it borrowed from a European ruling.",
                source="AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 2, titles_by_event)
        acquisition_events = [
            event
            for event in events
            if "Play" in " ".join(article.title for article in event.articles)
            or "Swift tools" in " ".join(article.title for article in event.articles)
        ]
        antitrust_events = [event for event in events if "antitrust" in " ".join(article.title for article in event.articles).lower()]
        self.assertEqual(len(acquisition_events), 1, titles_by_event)
        self.assertEqual(len(antitrust_events), 1, titles_by_event)
        self.assertEqual({article.source for article in acquisition_events[0].articles}, {"MacRumors", "AppleInsider"})
        self.assertEqual(acquisition_events[0].relevance_tier, "strong", titles_by_event)
        self.assertFalse(any("antitrust" in article.title.lower() for article in acquisition_events[0].articles))

    def test_direct_apple_acquisition_is_strong_even_when_target_is_an_app(self):
        module = load_module()

        self.assertTrue(module.is_apple_strategic_transaction_story("Apple Acquires Award-Winning App 'Play'"))
        self.assertIn(
            "apple-strategic-transaction",
            module.primary_topic_facets("Apple Acquires Award-Winning App 'Play'"),
        )

        tier, reason = module.classify_relevance_tier(
            "Apple Acquires Award-Winning App 'Play'",
            (
                "In February, Apple notified the European Commission that it would be acquiring certain assets "
                "from and have the right to hire certain employees from Rabbit 3 Times, the company behind the "
                "award-winning app design tool Play."
            ),
            [
                "In 2025, the app won an Apple Design Award for innovation.",
                "The listing describes Play as offering iOS and macOS tools for designing SwiftUI code in real time.",
            ],
            "MacRumors",
        )

        self.assertEqual(tier, "strong", reason)

    def test_apple_acquisition_title_stays_strong_when_summary_contains_app_store_noise(self):
        module = load_module()
        noisy_summary = (
            "Apple Acquires Award-Winning App 'Play'. In February, Apple notified the European Commission that "
            "it would be acquiring certain assets from and have the right to hire certain employees from Rabbit "
            "3 Times, the company behind the award-winning app design tool Play. The notification was published "
            "on the European Commission's website this week, following a four-month waiting period. Play was a "
            "Mac and iPhone app that allowed designers to prototype iPhone app interfaces using Apple's SwiftUI "
            "frameworks, and then send them to Xcode. Apple has acquired a variety of apps recently, and the "
            "latest—Play—won the 2025 Apple Design Award in the Innovation category. IT之家称苹果向欧盟委员会提交申报，"
            "计划收购 Rabbit 3 Times 公司的部分资产，并有权吸纳该公司部分员工。日前，腾讯旗下一款名为 TenPayGo 的支付应用已上架苹果应用商店 App Store，"
            "引起了外界对腾讯有无计划推出独立支付应用的讨论。"
        )

        tier, reason = module.classify_relevance_tier(
            "Apple Acquires Award-Winning App 'Play'",
            noisy_summary,
            [
                "In 2025, the app won an Apple Design Award for innovation.",
                "And the latest addition, as spotted by MacRumors, is for Rabbit 3 Times along with its Play app.",
                "苹果官方表示：Play 是一款功能专业、上手门槛低的工具，用户可依托 SwiftUI 框架制作可交互原型。",
                "从已公开的信息来看，TenPayGo界面设计较为简洁。用户绑定银行卡后，可生成付款二维码供商户扫码，或主动扫描商户二维码完成支付。",
                "在应用场景上，该App覆盖购物、餐饮、交通、酒店、景区、医疗健康等多个日常消费领域。",
                "Perhaps the company will integrate its feature set into Xcode, or re-launch Play as a new standalone app.",
                "值得注意的是，这并非腾讯首次在跨境支付领域进行布局。",
            ],
            "MacRumors",
        )

        self.assertEqual(tier, "strong", reason)

    def test_third_party_app_store_title_is_not_strengthened_by_related_acquisition_noise(self):
        module = load_module()
        noisy_summary = (
            "Tencent's TenPayGo payment app has been listed on Apple's App Store for internal testing. "
            "Related links mention Apple acquiring the award-winning Play app from Rabbit 3 Times."
        )

        tier, reason = module.classify_relevance_tier(
            "腾讯 TenPayGo 支付应用上架苹果 App Store，目前处于内部测试",
            noisy_summary,
            [],
            "cnBeta",
        )

        self.assertEqual(tier, "weak", reason)

    def test_merged_apple_app_acquisition_event_is_not_downgraded_by_app_status_language(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Acquires Award-Winning App 'Play'",
                (
                    "In February, Apple notified the European Commission that it would be acquiring certain assets "
                    "from Rabbit 3 Times, the company behind the award-winning app design tool Play. Play was a Mac "
                    "and iPhone app that allowed designers to prototype iPhone app interfaces using Apple's SwiftUI "
                    "frameworks, and then send them to Xcode."
                ),
                source="MacRumors",
                facts=["In 2025, the app won an Apple Design Award for innovation."],
            ),
            article_for(
                module,
                "Apple just acquired the app that won last year’s Innovation Apple Design Award",
                (
                    "Apple has acquired a variety of apps recently, and the latest—Play—won the 2025 Apple Design "
                    "Award in the Innovation category. Here’s what it does."
                ),
                source="9to5Mac",
                facts=["Perhaps the company will integrate its feature set into Xcode or Apple developer resources."],
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(events[0].relevance_tier, "strong", events[0].relevance_reason)

    def test_third_party_payment_app_listing_does_not_merge_with_apple_acquisition(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Acquires Award-Winning App 'Play'",
                (
                    "Apple notified the European Commission that it would acquire certain assets and hire employees "
                    "from Rabbit 3 Times, the company behind the app design tool Play."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "腾讯 TenPayGo 支付应用上架苹果 App Store，目前处于内部测试",
                (
                    "腾讯旗下 TenPayGo 支付应用已上架苹果应用商店，用户绑定银行卡后可生成付款二维码，"
                    "未来还将逐步接入更多本地交通及生活服务功能。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 2, titles_by_event)
        self.assertFalse(any("Play" in titles and "TenPayGo" in titles for titles in titles_by_event), titles_by_event)

    def test_mixed_relevance_event_splits_weak_app_noise_from_strong_transaction(self):
        module = load_module()
        strong_article = article_for(
            module,
            "Apple Acquires Award-Winning App 'Play'",
            (
                "Apple notified the European Commission that it would acquire certain assets and hire employees "
                "from Rabbit 3 Times, the company behind the app design tool Play."
            ),
            source="MacRumors",
        )
        weak_article = article_for(
            module,
            "腾讯 TenPayGo 支付应用上架苹果 App Store，目前处于内部测试",
            (
                "腾讯旗下 TenPayGo 支付应用已上架苹果应用商店，用户绑定银行卡后可生成付款二维码，"
                "未来还将逐步接入更多本地交通及生活服务功能。"
            ),
            source="IT之家",
        )
        event = module.cluster_articles([strong_article])[0]
        module.rebuild_event_from_articles(event, [strong_article, weak_article])

        split_events = module.split_mixed_topic_event(event)
        titles_by_event = [" | ".join(article.title for article in item.articles) for item in split_events]

        self.assertEqual(len(split_events), 2, titles_by_event)
        self.assertTrue(any("Play" in titles and "TenPayGo" not in titles for titles in titles_by_event), titles_by_event)
        self.assertTrue(any("TenPayGo" in titles and "Play" not in titles for titles in titles_by_event), titles_by_event)

    def test_same_apple_acquisition_merges_across_secondary_developer_tool_guard(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Acquires Award-Winning App 'Play'",
                (
                    "Apple notified the European Commission that it would acquire certain assets and hire employees "
                    "from Rabbit 3 Times, the company behind the app design tool Play."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果收购获奖应用 Play 开发商部分资产，App Store 已下架该应用",
                (
                    "苹果向欧盟委员会提交申报，计划收购 Rabbit 3 Times 公司的部分资产，并有权吸纳该公司部分员工。"
                    "Play 是一款适用于 Mac 与 iPhone 的应用，设计师可借助苹果 SwiftUI 框架制作原型并导入 Xcode。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [" | ".join(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 1, titles_by_event)

    def test_future_iphone_price_forecasts_still_merge_with_each_other(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "消息称苹果 iPhone 18 Pro / Max 及 Ultra 阔折叠均为“万元机”",
                (
                    "苹果已上调 Mac、iPad 等产品售价，称涨价因存储元件成本上涨，后续或仍有调价空间。"
                    "业内透露 iPhone 18 Pro 系列及首款折叠屏 Ultra 都将万元起售。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 iPhone 18 Pro 系列或全面涨价：Ultra 折叠屏起售价超万元",
                (
                    "供应链人士称 iPhone 18 Pro、iPhone 18 Pro Max 和折叠屏 iPhone Ultra "
                    "会采用更贵的零部件，预计新机起售价将进入万元区间。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)

    def test_market_share_report_does_not_merge_with_current_price_increase(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                (
                    "Apple dramatically increased device prices across multiple product lines after memory "
                    "and storage costs rose quickly."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "Report: Apple set to reach record market share despite higher prices",
                (
                    "Counterpoint Research says Apple is on track for record market share this year, "
                    "with iPhone demand remaining resilient even as premium phones become more expensive."
                ),
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_apple_market_share_report_has_specific_topic_facet(self):
        module = load_module()
        title = "Apple set to reach record market share across major product categories in 2026"
        summary = (
            "Counterpoint Research predicts Apple will hit record market share in smartphones, "
            "laptops, and tablets, with iPad share rising from 35% to 39%, iPhone reaching 25%, "
            "Apple Watch reaching 23%, and Mac reaching 12%."
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("apple-market-share-report", facets)

    def test_non_apple_followup_price_story_is_weak_and_separate(self):
        module = load_module()
        title = "微软 Xbox 主机跟进苹果涨价，海外售价上调 80 美元"
        summary = (
            "微软宣布 Xbox 主机海外售价上调，文章提到苹果 Mac 和 iPad 近期涨价，"
            "但主要内容是 Xbox 硬件和游戏订阅价格变化。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_followup_price_story_with_indirect_title_is_weak(self):
        module = load_module()
        title = "微软紧随苹果上调Xbox主机售价 存储和内存成本已暴涨2.5倍"
        summary = (
            "在苹果宣布提高 MacBook 和 iPad 售价仅数小时后，微软也宣布 Xbox 主机价格上调。"
            "文章重点列出 Xbox Series S 和 Series X 的新价格，苹果仅作为涨价背景。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_drone_price_rumor_after_apple_is_weak(self):
        module = load_module()
        title = "继苹果后大疆被传全系涨价3%-8% 官方回应：消息不实 纯属谣言"
        summary = (
            "传言称 DJI 大疆全系产品将因供应链成本上升调价，新的价格适用于官方商城、京东、"
            "天猫、抖音及线下授权体验店等渠道。文章后文提到苹果已上调多个市场 Mac、iPad "
            "等硬件产品售价，作为成本压力背景。"
        )

        self.assertTrue(module.is_non_apple_price_followup_story(title, summary))
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_native_ios_app_launch_stays_weak(self):
        module = load_module()
        title = "Open Source AI Agent OpenClaw Gets Native iOS App"
        summary = (
            "OpenClaw is expanding to the iPhone and iPad with a new native iOS app "
            "for chat, voice approvals, sharing, and device-aware automation."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "weak", reason)

    def test_classic_mac_os_third_party_client_stays_weak(self):
        module = load_module()
        title = "开发者为经典MacOS 9打造完整的OpenStreetMap客户端 - Apple macOS - cnBeta.COM"
        summary = (
            "开发者发布 OS9Map 地图应用，为已经停产多年的经典 Mac OS 9 操作系统带来现代地图体验，"
            "需要 PowerPC Macintosh 电脑和 Open Transport 网络栈。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_iphone_accessory_compatibility_stays_weak(self):
        module = load_module()
        title = "iPhone也能有背屏了！OPPO Bubble潮玩自拍屏官宣适配：499元"
        summary = (
            "OPPO Bubble 潮玩自拍屏正式官宣适配 iPhone，新版本已经开启预约，"
            "可在 App 查看电量、连接情况，并支持设置个性壁纸。"
        )
        facts = [
            "快科技6月30日消息，OPPO Bubble潮玩自拍屏正式官宣适配iPhone，新版本已经开启预约，将于7月6日开售，依然定价499元。",
            "从官方海报来看，OPPO应该做了单独的软件适配，可以在App查看电量、连接情况，并且支持设置个性壁纸等等。",
            "OPPO Bubble机身厚度约7mm，重量约27.5g，内置550mAh电池，正面配备一块圆形AMOLED触屏，支持显示静态图片、实况照片和视频内容。",
        ]

        self.assertEqual(module.detect_event_kind(title, summary, facts), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, facts, "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_legacy_apple_hardware_replica_stays_weak(self):
        module = load_module()
        title = "SB Mini II 登场：硬件复刻苹果 Apple II Plus 电脑，6502 CPU+48K 内存"
        summary = (
            "Simon Boak 发布 SB Mini II 项目，通过现代元件硬件复刻 Apple II Plus。"
            "Apple II Plus 于 1979 年推出，是苹果早期 8 位个人计算机型号。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "weak", reason)

    def test_former_apple_staff_third_party_vehicle_story_stays_weak(self):
        module = load_module()
        title = "苹果、奥迪前员工联合创业，推出 2.5 万美元月球车风格轻型电动车"
        summary = (
            "电动车初创公司 Amble 推出首款产品 Amble One。"
            "设计总监 Julian Hoenig 曾在奥迪参与 R8、Q3 等车型设计，后加入苹果负责 Apple Watch、Vision Pro 及已取消的 Project Titan 汽车项目。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "爱范儿")
        self.assertEqual(tier, "weak", reason)

    def test_non_apple_component_market_background_story_is_weak(self):
        module = load_module()
        title = "日本痛失国运：银行不给钱支持尔必达 内存巨头就此倒闭"
        summary = (
            "文章主要回顾日本内存产业和尔必达倒闭过程，只在背景段落提到苹果曾采购尔必达内存，"
            "并用当前内存涨价说明行业利润变化。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_domestic_phone_price_wave_story_is_weak(self):
        module = load_module()
        title = "内存价格持续狂飙！国产手机即将掀起第二轮涨价潮"
        summary = (
            "文章先提到苹果 Mac 和 iPad 涨价作为行业背景，主体讨论国产安卓手机厂商很快迎来第二轮涨价，"
            "涨幅预计在 200 元至 800 元之间。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_current_price_response_articles_still_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                (
                    "Apple dramatically increased device prices across multiple product lines after memory "
                    "and storage costs rose quickly."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果回应 Mac / iPad 等 14 款产品涨价：消费电子行业正面临前所未有的挑战",
                (
                    "苹果公司回应昨日上调 14 款产品价格，指出 AI 数据中心扩张推高内存与存储芯片需求，"
                    "导致 RAM 和 SSD 成本快速上涨。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)

    def test_apple_tv_price_increase_is_not_apple_tv_content_facet(self):
        module = load_module()
        title = "Apple TV and HomePod Just Went Up in Price Amid Wait for New Models"
        summary = "Apple raised prices on Apple TV and HomePod hardware as part of a broader product price increase."

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("apple-current-product-price-increase", facets)
        self.assertNotIn("apple-tv-content", facets)

    def test_macbook_price_increase_due_to_memory_cost_is_not_memory_ai_facet(self):
        module = load_module()
        title = "Apple Hikes M4 Pro Mac Mini Starting Price Amid Rising Memory Costs"
        summary = "Apple raised the starting price because RAM and SSD storage costs have increased sharply."

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("apple-current-product-price-increase", facets)
        self.assertNotIn("macbook-memory-ai", facets)

    def test_official_apple_refurbished_product_story_is_strong(self):
        module = load_module()
        title = "Refurbished MacBook Neo Models Now Available, a Day After Price Hike"
        summary = (
            "Apple today began selling refurbished MacBook Neo units through its Certified Refurbished store, "
            "a day after raising prices on the laptop and several other products."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "retail_store")
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "strong", reason)

    def test_back_to_school_promo_does_not_merge_with_refurbished_price_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Refurbished MacBook Neo Models Now Available, a Day After Price Hike",
                (
                    "Apple today began selling refurbished MacBook Neo units through its Certified Refurbished store, "
                    "a day after raising prices on the laptop and several other products."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "Back to School promotion could ease the sting of Apple's higher Mac & iPad prices",
                (
                    "Apple's annual Back to School promotion is expected to return around July 1, "
                    "giving eligible students a timely way to offset Apple's newly announced Mac and iPad price increases."
                ),
                source="AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)

    def test_refresh_event_metadata_does_not_downgrade_strong_article_group(self):
        module = load_module()
        article = article_for(
            module,
            "Back to School promotion could ease the sting of Apple's higher Mac & iPad prices",
            (
                "Apple's annual Back to School promotion is expected to return around July 1, "
                "giving eligible students a timely way to offset Apple's newly announced Mac and iPad price increases."
            ),
            source="AppleInsider",
        )
        event = module.Event(
            event_id="promo",
            category=article.category,
            title="Third-party Vision Pro accessory now available",
            summary="A third-party accessory story uses Apple products mainly as platform context.",
            key_facts=[],
            published_utc=article.published_utc,
            published_raw=article.published_raw,
            published_source=article.published_source,
            confidence=article.confidence,
            articles=[article],
            tokens=set(article.tokens),
            event_kind=article.event_kind,
            relevance_tier=article.relevance_tier,
            relevance_reason=article.relevance_reason,
            regions=set(article.regions),
        )

        module.refresh_event_metadata(event)

        self.assertEqual(event.relevance_tier, "strong")

    def test_retail_promo_event_does_not_emit_price_response_must_include(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Back to School promotion could ease the sting of Apple's higher Mac & iPad prices",
                (
                    "Apple's annual Back to School promotion is expected to return around July 1, "
                    "giving eligible students a timely way to offset Apple's newly announced Mac and iPad price increases."
                ),
                facts=[
                    "Apple raised prices on several Mac and iPad models on Thursday, June 25.",
                    "Apple said AI data centers drove extraordinary memory and storage demand and that this is not welcome news.",
                ],
                source="AppleInsider",
            )
        ]
        event = module.cluster_articles(articles)[0]
        event_dict = module.event_to_dict(event, timezone.utc)

        self.assertNotIn("must_include_facts", event_dict)

    def test_future_price_forecast_event_does_not_emit_current_price_response_must_include(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "消息称苹果 iPhone 18 Pro / Max 及 Ultra 阔折叠均为“万元机”",
                (
                    "业内透露 iPhone 18 Pro 系列及首款折叠屏 Ultra 都将万元起售，"
                    "报道背景提到苹果已上调 Mac 和 iPad 等产品售价。"
                ),
                facts=[
                    "苹果回应称 AI 数据中心推高内存与存储需求，这并非好消息，苹果正竭力寻找解决方案。"
                ],
                source="IT之家",
            )
        ]
        event = module.cluster_articles(articles)[0]
        event_dict = module.event_to_dict(event, timezone.utc)

        self.assertNotIn("must_include_facts", event_dict)

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

    def test_9to5_apple_work_sponsor_copy_is_removed_and_column_stays_weak(self):
        module = load_module()
        html = """
        <html>
          <head><meta name="description" content="Apple continues to become an enterprise vendor of choice, but breaking core functions like printing in minor security updates is a trend that needs to stop." /></head>
          <body>
            <article class="post-content">
              <p>Apple @ Work is exclusively brought to you by Mosyle, the only Apple Unified Platform. Request your EXTENDED TRIAL today.</p>
              <p>About Apple @ Work: Bradley Chambers has been an Apple IT admin since 2009 and shares ways Apple could improve its products for IT departments.</p>
              <p>A perfect example happened with the March 2026 security updates. Apple released patches for macOS 26.4, macOS 15.7.5, and macOS 14.8.5, after which some enterprise users saw printing problems with PaperCut Mobility Print.</p>
            </article>
          </body>
        </html>
        """
        title = "Apple @ Work: As Apple grows in the enterprise, these are the kind of update bugs it has to squash immediately"

        summary = module.extract_summary(html, title)
        facts = module.extract_key_facts(html, title, "9to5Mac")
        combined = " ".join([summary, *facts])
        tier, reason = module.classify_relevance_tier(title, summary, facts, "9to5Mac")

        self.assertNotIn("Mosyle", combined)
        self.assertNotIn("About Apple @ Work", combined)
        self.assertEqual(tier, "weak", reason)

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

    def test_9to5_unlocked_renewed_iphone_amazon_list_is_removed(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        page = """
        <html><head>
          <meta property="article:published_time" content="2026-07-15T16:00:00+00:00" />
          <meta property="og:description" content="Apple now locks carrier-financed iPhones until they are paid in full." />
        </head><body><div class="post-content">
          <p>Apple updated its purchase FAQ: iPhones financed through AT&amp;T, T-Mobile, or Verizon remain locked until paid in full.</p>
          <p>The policy closes a workaround that previously combined carrier financing with an unlocked device.</p>
          <p>One of the easiest ways to buy an unlocked iPhone and save some cash in the process is via Amazon:</p>
          <ul>
            <li>iPhone 17 Pro (Unlocked, Renewed): $1,069</li>
            <li>iPhone 17 Pro Max (Unlocked, Renewed): $1,179</li>
            <li>iPhone 17 (Unlocked, Renewed): $745</li>
            <li>iPhone Air (Unlocked, Renewed): $768.10</li>
          </ul>
        </div></body></html>
        """
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/15/unlocked-iphone-carrier-financing/",
            title="Apple just closed a popular workaround for buying an unlocked iPhone",
        )

        _, summary, facts, *_ = module.extract_article(candidate, source, page, {})
        combined = " ".join([summary, *facts])

        self.assertIn("locked until paid in full", combined)
        self.assertNotIn("Renewed", combined)
        self.assertNotIn("$1,069", combined)

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

    def test_apple_disney_strategic_merger_talk_is_relevant_company_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/23/apple-and-disney-had-conversations-about-merging-says-bob-iger/",
            title="Apple and Disney had conversations about merging, says Bob Iger",
            summary=(
                "Disney's former CEO Bob Iger shared new quotes about the long-discussed "
                "idea of Apple and Disney merging, saying the companies had conversations "
                "but Apple's interest was limited."
            ),
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

    def test_apple_strategic_merger_talk_merges_across_languages_by_counterparty(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple and Disney had conversations about merging, says Bob Iger",
                (
                    "Disney's former CEO Bob Iger shared new quotes about Apple and Disney "
                    "having merger conversations, but said Apple's interest was limited."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "前迪士尼 CEO 艾格：曾规划“最具变革公司合并”，但苹果兴趣不高",
                "迪士尼前 CEO 鲍勃·艾格透露，迪士尼曾与苹果讨论过合并事宜，但苹果并未表现出太大兴趣。",
                source="IT之家",
            ),
            article_for(
                module,
                "Apple reportedly discussed acquiring a different AI startup",
                "Apple executives reportedly discussed a possible acquisition of an AI startup, but no deal progressed.",
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        merged = next(event for event in events if any("Disney" in item.title for item in event.articles))
        self.assertEqual({item.source for item in merged.articles}, {"9to5Mac", "IT之家"})

    def test_swift_package_index_joining_apple_is_relevant_developer_ecosystem_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/23/swift-package-index-joins-apple-pledges-to-remain-open-source/",
            title="Swift Package Index joins Apple, pledges to remain open source",
            summary=(
                "Community-run Swift package search engine and metadata index Swift Package "
                "Index is joining Apple, but says little is changing for developers in the near term."
            ),
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "developer_tool")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "software_systems")

    def test_macbook_oled_panel_planning_is_relevant_hardware_roadmap_news(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/967/644.htm",
            title='消息称苹果规划新款 13.8" OLED 面板，用于 MacBook 笔记本电脑',
            summary="由于苹果产品开发周期通常为 2~3 年，这一新尺寸面板目前仍处于商业化的早期阶段，仍可能被搁置或放弃。",
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "hardware_market")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(candidate.title, candidate.summary), "hardware_products")

    def test_apple_oled_supply_chain_title_with_boe_is_not_treated_as_jd_discount(self):
        module = load_module()
        title = "三星和LG包揽iPhone 18 Pro/iPad所有OLED面板订单：京东方出局"
        summary = (
            "据供应链消息，三星显示与LG Display已开始为苹果2026年产品线量产OLED面板。"
            "iPhone 18 Pro、iPhone 18 Pro Max、折叠屏iPhone、新款iPad mini和MacBook Pro所需OLED面板均进入量产阶段。"
        )
        facts = [
            "三星显示成为iPad mini、折叠屏iPhone以及MacBook Pro的独家OLED供应商，其中iPad mini面板供应量约为200万块，折叠屏iPhone约为1000万块。",
            "LG Display独家供应Apple Watch Series 12所需OLED面板，预计出货量约为3400万块；iPhone 18 Pro和iPhone 18 Pro Max面板由两家公司共同供货，合计约9000万块。",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "快科技")

        self.assertFalse(module.is_routine_retail_discount_story(title, f"{title} {summary}"))
        self.assertEqual(module.detect_event_kind(title, summary, facts), "hardware_market")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_competitor_display_panel_story_using_apple_as_background_stays_weak(self):
        module = load_module()
        title = "继苹果之后再失三星订单 传京东方Galaxy S27 OLED合作告吹"
        summary = (
            "报道称京东方继失去苹果 iPhone OLED 面板订单后，又被传失去三星 Galaxy S27 OLED 合作；"
            "文章主体是三星 Galaxy 供应链变化。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_swift_package_index_joining_apple_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "软件包聚合平台 Swift Package Index 官宣加入苹果，承诺保持开源",
                (
                    "Swift Package Index 平台宣布正式加入苹果，官方承诺将保持开源，平台功能与社区参与模式不变。"
                    "未来，苹果工程师将参与其开发，并计划推出软件包签名、身份认证等新功能。"
                    "IT之家注：Swift Package Index 是一个开源的 Swift 软件包搜索引擎和元数据索引平台，"
                    "支持 macOS、iOS、Linux、Android 等系统，过去一年完成超 350 万次跨平台兼容性构建测试。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "Developer resource Swift Package Index to stay open source after Apple acquisition",
                (
                    "The Swift Package Index is no longer independent as Apple has taken control, "
                    "but it will remain an open source search engine for third-party code. "
                    "The Swift Package Index gave developers one trusted location to look for third-party code "
                    "for use in their own apps. Developers can find code that works with Xcode's Swift Package Manager, "
                    "and earlier in 2026 it had tested and indexed over 10,000 Swift packages."
                ),
                source="AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"IT之家", "AppleInsider"})

    def test_apple_tv_4k_device_story_is_hardware_news(self):
        module = load_module()
        title = "New Apple TV 4K is coming this fall with three new features: report"
        summary = (
            "A report says Apple is preparing a new Apple TV 4K set-top box for the fall, "
            "with Siri AI, Apple Intelligence features, a revised remote, possible tvOS updates, "
            "a faster chip, Wi-Fi improvements, and Thread smart-home support."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")
        self.assertIn("apple-tv-hardware", module.topic_facets_from_text(f"{title} {summary}"))
        self.assertNotIn("apple-tv-content", module.topic_facets_from_text(f"{title} {summary}"))

    def test_apple_tv_4k_device_story_does_not_merge_with_apple_tv_plus_content(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "New Apple TV 4K is coming this fall with three new features: report",
                "A report says Apple is preparing a new Apple TV 4K set-top box for the fall, with a faster chip, Wi-Fi improvements, and Thread smart-home support.",
            ),
            article_for(
                module,
                "Apple TV+ new thriller Cape Fear adds another star",
                "Apple TV+ is preparing a new thriller series for its streaming service, with casting updates for the upcoming season.",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual({event.event_kind for event in events}, {"hardware_market", "service_content"})

    def test_apple_watch_hardware_launch_rumor_stays_hardware_despite_health_terms(self):
        module = load_module()
        title = "传 Apple Watch Ultra 4 将于今年晚些时候登场"
        summary = (
            "预计苹果将于今年晚些时候推出 Apple Watch Ultra 4，这将是 Ultra 系列一次幅度较大的更新，"
            "重点围绕外观设计、健康传感器、身份验证和续航表现展开。新表可能加入 Touch ID，"
            "并通过新一代芯片和重新分配内部空间改善电池表现。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")
        self.assertEqual(tier, "strong", reason)

    def test_ios_home_screen_widget_story_remains_software_after_hardware_launch_rule(self):
        module = load_module()
        title = "iOS 27 adds brand new widgets for your iPhone's Home Screen"
        summary = "Apple is adding new extra-large Home Screen widgets in iOS 27 for iPhone users."

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

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

    def test_chinese_third_party_ios_app_launch_is_deferred_weak(self):
        module = load_module()
        examples = [
            (
                "迅雷光鸭云盘 iOS 版上线，适配 iOS / iPadOS 17.6 以上系统",
                "迅雷光鸭云盘 iOS 版上线，适配 iOS / iPadOS 17.6 以上系统。",
            ),
            (
                "腾讯Marvis马维斯iOS版上线 躺着掏出手机 就能远程指挥电脑桌面",
                "腾讯 Marvis iOS 版上线，可以远程控制电脑桌面。",
            ),
        ]

        for title, summary in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
                self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
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

    def test_apple_wallet_digital_id_third_party_use_case_is_strong_and_merges(self):
        module = load_module()
        title = "Apple Wallet's Digital ID feature could potentially have a major new use case soon"
        summary = (
            "Anthropic could use Apple's Digital ID feature for nationality verification. "
            "Digital ID lets US passport holders store an identity credential in Apple Wallet, "
            "and Anthropic already uses Apple's age verification API."
        )
        chinese_title = "消息称 Anthropic 或采用苹果 Digital ID 完成用户身份核验"
        chinese_summary = (
            "苹果数字身份证功能或迎来首个大规模应用场景，集成到 Claude AI 中用于核验用户国籍。"
            "该方案基于双方已有合作，但会排除无 iPhone 或非美国护照持有者。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
        events = module.cluster_articles(
            [
                article_for(module, title, summary, source="9to5Mac"),
                article_for(module, chinese_title, chinese_summary, source="IT之家"),
            ]
        )

        self.assertEqual(module.detect_event_kind(title, summary), "wallet_feature")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家"})

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

    def test_top_stories_with_hardware_leak_terms_stays_weak_and_separate(self):
        module = load_module()
        top_stories = article_for(
            module,
            "Top Stories: 'MacBook Ultra' and iPhone 18 Rumors, iOS 26.5.2 Security Fixes, and More",
            (
                "This week's top stories include a MacBook Ultra rumor, iPhone 18 Pro references, "
                "iOS 26.5.2 security fixes, and supplier leak follow-ups."
            ),
            "MacRumors",
            facts=[
                "A20 Pro reports mention LPDDR6 memory, a wider memory bus, NAND storage tradeoffs, and iPhone 18 Pro cost pressure.",
                "Earlier reports said Apple is trying to buy DRAM from ChangXin Memory Technologies and CXMT, and has asked the Trump administration for access to restricted memory suppliers.",
                "Other linked stories discuss Tata Electronics data leaks and MacBook chip roadmap rumors.",
            ],
        )
        memory_bus = article_for(
            module,
            "消息称苹果 A20 Pro 内存总线升级到 96-bit，LPDDR6 与高容量闪存存在取舍",
            (
                "爆料称 iPhone 18 Pro 的 A20 Pro 可能采用 96-bit LPDDR6 内存总线，"
                "但 1TB/2TB 版本或因成本使用 QLC NAND 闪存。"
            ),
            "cnBeta",
            facts=[
                "A20 Pro 可能采用 96-bit LPDDR6 内存总线，带宽相较 64-bit LPDDR5X 明显提升。",
                "1TB/2TB 版本可能使用 QLC NAND，256GB/512GB 版本仍使用 TLC NAND。",
            ],
        )

        events = module.cluster_articles([top_stories, memory_bus])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(top_stories.relevance_tier, "weak", top_stories.relevance_reason)
        self.assertEqual(len(events), 2, clusters)
        self.assertFalse(any({top_stories.title, memory_bus.title} == cluster for cluster in clusters), clusters)

    def test_column_commentary_about_apple_management_stays_weak(self):
        module = load_module()
        title = "Sunday Reboot: The right marketing, the wrong changes"
        summary = (
            "A columnist argues about Apple's marketing, management changes, and product decisions "
            "without reporting a new Apple announcement, filing, executive move, or product fact."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

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

    def test_lost_iphone_find_my_how_to_stays_weak_and_out_of_data_leak_cluster(self):
        module = load_module()
        how_to = article_for(
            module,
            "苹果没告诉你 iPhone 丢了怎么办：这功能一定提前打开",
            (
                "如果哪天出门不小心把 iPhone 丢了，用户可以通过查找 App 标记为丢失、暂停 Apple Pay、"
                "远程抹掉数据并避免个人隐私泄露。文章提醒用户不要提前删除设备，避免解除激活锁。"
            ),
            "快科技",
            facts=[
                "花 30 秒打开查找我的 iPhone、查找网络和发送最后的位置，可提高找回概率。",
            ],
        )
        leak = article_for(
            module,
            "海量未公开机密数据流入暗网 印度政府调查苹果手机信息泄露事件",
            (
                "印度政府正调查苹果供应商塔塔电子数据泄露事件，超过 630GB 文件流入暗网，"
                "涉及 iPhone 18 Pro 主板图纸、A20 Pro 数据表和供应商清单。"
            ),
            "快科技",
        )

        events = module.cluster_articles([leak, how_to])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(how_to.relevance_tier, "weak", how_to.relevance_reason)
        self.assertEqual(len(events), 2, clusters)

    def test_former_apple_engineer_background_ai_model_story_stays_weak(self):
        module = load_module()
        title = "硅仙人 Jim Keller 大赞中国大模型：成本降低 5 倍 美国 AI 没法微调"
        summary = (
            "Jim Keller 是硅谷著名芯片设计师，之前被称为 Zen 架构之父，领导了苹果公司初代处理器开发，"
            "也在 Intel 参与多款处理器开发，现在成为 Tenstorrent 公司的 CEO。"
            "他表示公司已经把开发任务切换到 Kimi K2 与 GLM-5.2，成本降低 5 倍并实现隐私保护。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_broad_ai_phone_market_commentary_with_apple_example_stays_weak(self):
        module = load_module()
        title = "AI手机、AIPC都不太给力：消费者无意买单 苹果也带不动"
        summary = (
            "文章讨论 AI 手机和 AIPC 市场接受度偏低，并以 UBS 调查中的 Apple Intelligence 换机意愿为例，"
            "称会因为该功能提前升级设备的消费者占比为 24%，比半年前少 5 个百分点。"
        )

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

    def test_apple_design_leadership_org_change_is_strong_company_news(self):
        module = load_module()
        title = "古尔曼：过去十年苹果设计部门地位持续下滑，新 CEO 特纳斯将做出改变"
        summary = (
            "Mark Gurman reports that Apple's design team has lost influence since Jony Ive left, "
            "and that John Ternus may rebalance Apple's product design organization after taking over. "
            "The article discusses a former Apple designer's startup company only as background."
        )
        facts = [
            "报道认为苹果内部设计部门的地位过去十年持续下滑，产品路线更多由工程和运营团队主导。",
            "John Ternus 可能在接任 CEO 后重新提高 Apple 设计团队在产品决策中的权重。",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary, facts), "company_org")
        self.assertEqual(tier, "strong", reason)

    def test_apple_design_org_change_does_not_merge_with_product_price_increase(self):
        module = load_module()
        design_article = article_for(
            module,
            "古尔曼：过去十年苹果设计部门地位持续下滑，新 CEO 特努斯将做出改变",
            "彭博社梳理了苹果过去十年管理层架构变化，指出在库克时代，设计团队话语权持续减弱，财务与运营部门决策权扩张。新任 CEO 约翰 · 特努斯或将重新确立设计团队的核心价值，并已着手与工业设计团队深入沟通。",
            source="IT之家",
        )
        price_article = article_for(
            module,
            "别等iPhone秋季发布会！古尔曼预判苹果很快涨价",
            "快科技6月22日消息，据媒体报道，苹果公司CEO蒂姆·库克上周公开表示，受AI热潮驱动，DRAM与NAND存储器芯片正经历严重短缺及价格暴涨，这一供应链冲击已使得苹果产品涨价不可避免。TechInsights估算下一代iPhone 18 Pro起售价或攀升至1299美元，Mac及iPad产品线同样面临调价压力。",
            source="快科技",
        )

        events = module.cluster_articles([design_article, price_article])

        self.assertEqual(len(events), 2)

    def test_apple_design_org_change_merges_across_sources(self):
        module = load_module()
        chinese_article = article_for(
            module,
            "古尔曼：过去十年苹果设计部门地位持续下滑，新 CEO 特努斯将做出改变",
            "彭博社梳理苹果过去十年管理层架构变化，称库克时代设计团队话语权减弱，新 CEO John Ternus 或将恢复设计团队决策权。",
            source="IT之家",
        )
        english_article = article_for(
            module,
            "Incoming CEO John Ternus may be looking to fix Apple's design organization",
            "John Ternus has taken over Apple's design team and may rebalance product decision authority after years of weaker industrial design influence.",
            source="AppleInsider",
        )

        events = module.cluster_articles([chinese_article, english_article])

        self.assertEqual(len(events), 1)

    def test_apple_design_leadership_org_change_candidate_is_relevant_from_listing(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/966/745.htm",
            title="古尔曼：过去十年苹果设计部门地位持续下滑，新 CEO 特努斯将做出改变",
            summary=(
                "彭博社梳理了苹果过去十年管理层架构变化，指出在库克时代，设计团队话语权持续减弱，"
                "财务与运营部门决策权扩张。新任 CEO 约翰 · 特努斯或将重新确立设计团队的核心价值。"
            ),
        )

        self.assertTrue(module.is_apple_company_org_change_story(f"{candidate.title} {candidate.summary}"))
        self.assertTrue(module.is_relevant_candidate(candidate, source))

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

    def test_final_brief_queue_lists_every_event_for_coverage_check(self):
        module = load_module()
        article_one = article_for(
            module,
            "Apple Wallet Digital ID may be used for verification",
            "Apple Wallet Digital ID could be used by a partner for identity verification.",
            source="9to5Mac",
        )
        article_two = article_for(
            module,
            "苹果美国关闭三家 Apple Store",
            "苹果关闭美国三家 Apple Store，员工安置安排引发争议。",
            source="IT之家",
        )
        events = module.cluster_articles([article_one, article_two])
        event_dicts = [module.event_to_dict(event, timezone.utc) for event in events]

        queue = module.build_final_brief_queue(event_dicts)

        self.assertEqual(len(queue), len(event_dicts))
        self.assertEqual({item["id"] for item in queue}, {event["id"] for event in event_dicts})
        self.assertTrue(all(item["required"] for item in queue))
        self.assertTrue(all(item["source_names"] for item in queue))

    def test_final_brief_markdown_scaffold_covers_every_event(self):
        module = load_module()
        data = {
            "events": [
                {
                    "category": "software_systems",
                    "title": "Apple Wallet Digital ID may be used for verification",
                    "summary": "Apple Wallet Digital ID could be used for identity verification.",
                    "key_facts": [],
                    "sources": [{"name": "9to5Mac", "url": "https://example.com/wallet"}],
                },
                {
                    "category": "hardware_products",
                    "title": "苹果美国关闭三家 Apple Store",
                    "summary": "苹果关闭美国三家 Apple Store，员工安排引发争议。",
                    "key_facts": [],
                    "sources": [{"name": "IT之家", "url": "https://example.com/store"}],
                },
            ]
        }

        markdown = module.render_markdown(data)

        self.assertIn("Apple Wallet Digital ID", markdown)
        self.assertIn("苹果关闭美国三家 Apple Store", markdown)
        self.assertIn("**软件与系统**", markdown)
        self.assertIn("**硬件与产品**", markdown)

    def test_compact_brief_scaffold_lists_titles_without_long_summaries(self):
        module = load_module()
        data = {
            "events": [
                {
                    "category": "software_systems",
                    "title": "Apple Wallet Digital ID may be used for verification",
                    "summary": "This long source summary should not be copied into the coverage scaffold.",
                    "key_facts": ["A long key fact should be reserved for final writing, not the checklist."],
                    "sources": [{"name": "9to5Mac", "url": "https://example.com/wallet"}],
                },
                {
                    "category": "hardware_products",
                    "title": "苹果美国关闭三家 Apple Store",
                    "summary": "苹果关闭美国三家 Apple Store，员工安排引发争议。",
                    "key_facts": [],
                    "sources": [{"name": "IT之家", "url": "https://example.com/store"}],
                },
            ]
        }

        scaffold = module.render_brief_scaffold(data)

        self.assertIn("Apple Wallet Digital ID", scaffold)
        self.assertIn("苹果美国关闭三家 Apple Store", scaffold)
        self.assertNotIn("This long source summary", scaffold)
        self.assertNotIn("A long key fact", scaffold)

    def test_json_output_writes_adjacent_brief_scaffold(self):
        module = load_module()
        data = {
            "events": [
                {
                    "category": "software_systems",
                    "title": "Apple Wallet Digital ID may be used for verification",
                    "summary": "Apple Wallet Digital ID could be used for identity verification.",
                    "key_facts": [],
                    "sources": [{"name": "9to5Mac", "url": "https://example.com/wallet"}],
                },
            ]
        }
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "latest.json"
            brief_path = module.write_brief_scaffold_file(output_path, data)

            self.assertEqual(brief_path, Path(temp_dir) / "latest.brief.md")
            self.assertIn("Apple Wallet Digital ID", brief_path.read_text(encoding="utf-8"))

    def test_status_title_list_can_be_derived_from_final_brief_queue(self):
        module = load_module()
        event_dicts = [
            {
                "id": "event-one",
                "category": "software_systems",
                "event_kind": "wallet_feature",
                "relevance_tier": "strong",
                "relevance_reason": "Apple-specific wallet feature event",
                "title": "Apple Wallet Digital ID may be used for verification",
                "sources": [{"name": "9to5Mac", "url": "https://example.com/wallet"}],
            }
        ]
        queue = module.build_final_brief_queue(event_dicts)

        self.assertEqual(
            module.required_final_brief_titles(queue),
            [
                {
                    "index": 1,
                    "event_id": "event-one",
                    "required": True,
                    "separate_bullet_by_default": True,
                    "coverage_rule": module.FINAL_BRIEF_ITEM_COVERAGE_RULE,
                    "omission_not_allowed_for": module.FINAL_BRIEF_OMISSION_NOT_ALLOWED_FOR,
                    "category": "software_systems",
                    "title": "Apple Wallet Digital ID may be used for verification",
                    "sources": ["9to5Mac"],
                }
            ],
        )

        status_titles = [
            {
                "index": item.get("index"),
                "event_id": item.get("id"),
                "required": item.get("required"),
                "separate_bullet_by_default": True,
                "coverage_rule": item.get("coverage_rule"),
                "omission_not_allowed_for": item.get("omission_not_allowed_for"),
                "category": item.get("category"),
                "title": item.get("title"),
                "sources": item.get("source_names", []),
            }
            for item in queue
        ]

        self.assertEqual(
            status_titles,
            [
                {
                    "index": 1,
                    "event_id": "event-one",
                    "required": True,
                    "separate_bullet_by_default": True,
                    "coverage_rule": module.FINAL_BRIEF_ITEM_COVERAGE_RULE,
                    "omission_not_allowed_for": module.FINAL_BRIEF_OMISSION_NOT_ALLOWED_FOR,
                    "category": "software_systems",
                    "title": "Apple Wallet Digital ID may be used for verification",
                    "sources": ["9to5Mac"],
                }
            ],
        )

    def test_required_titles_warn_against_omitting_single_source_speculative_events(self):
        module = load_module()
        event_dicts = [
            {
                "id": "iring-event",
                "category": "hardware_products",
                "event_kind": "hardware_market",
                "relevance_tier": "strong",
                "relevance_reason": "Apple hardware roadmap or product-development event",
                "title": "Apple 'iRing' Rumor Re-Emerges Amid Oura Ring Popularity",
                "sources": [
                    {
                        "name": "MacRumors",
                        "url": "https://www.macrumors.com/2026/06/26/apple-iring-rumor-returns-oura-ring-rival/",
                    }
                ],
            }
        ]

        queue = module.build_final_brief_queue(event_dicts)
        required = module.required_final_brief_titles(queue)
        scaffold = module.render_brief_scaffold({"events": event_dicts})

        self.assertEqual(required[0]["coverage_rule"], module.FINAL_BRIEF_ITEM_COVERAGE_RULE)
        self.assertIn("single_source", required[0]["omission_not_allowed_for"])
        self.assertIn("speculative_or_rumor", required[0]["omission_not_allowed_for"])
        self.assertIn("competitor_or_third_party_context", required[0]["omission_not_allowed_for"])
        self.assertIn("single-source", scaffold)
        self.assertIn("speculative", scaffold)
        self.assertIn("Apple 'iRing'", scaffold)

    def test_broad_multi_vendor_market_report_without_apple_metrics_is_weak(self):
        module = load_module()
        title = "Omdia 报告：2026 年第一季度中国大陆 PC 出货量下滑 2%，联想华为苹果前三"
        summary = (
            "Omdia 报告显示，中国大陆 PC 和平板电脑市场分别同比下降。"
            "联想、华为、苹果占据 PC 市场前三，市场疲软主要受到零部件成本上涨和补贴力度减弱影响。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_primary_subjects_with_incidental_apple_terms_stay_weak(self):
        module = load_module()
        examples = [
            (
                "安卓最强Soc！高通骁龙8E6系列双剑齐发：小米拿到首发权",
                (
                    "高通下一代旗舰芯片敲定双版本规划，小米18系列拿到全球独家首发权。"
                    "文章后文提到此前苹果 Mac、iPad 已因存储成本上调售价，安卓旗舰也可能涨价。"
                ),
            ),
            (
                "塔塔汽车公布 2031 战略：产品线扩至 25 款，电动汽车目标年销 40 万辆",
                (
                    "印度塔塔汽车乘用车业务公布面向 2031 财年的发展规划，"
                    "其中一款车型可能是 Safari EV，并将扩充电动车产品线。"
                ),
            ),
            (
                "英国斥资 7.5 亿英镑新建国家级超算，能模拟量子、地震、宇宙膨胀",
                (
                    "该超算将部署在爱丁堡大学位于中洛锡安佩尼库克和罗斯林的校舍内，"
                    "用于科研模拟并获得英国政府资助。"
                ),
            ),
            (
                "PSA: Lifetime Plex Plan goes from $249.99 to a painful $749.99 on July 1",
                "Plex says its lifetime pass price will rise, and the article says users can stream a movie collection to an iPhone.",
            ),
            (
                "联想拯救者神秘新平板真机曝光：50MP 单摄 + 环形 RGB",
                (
                    "联想拯救者新平板在展会上亮相。作为参考，在售 Y700 支持查看接收 iPhone 端短信，"
                    "并可与联想电脑、moto 手机、iPhone 跨生态文件互传。"
                ),
            ),
            (
                "苹果 Mac 用户集体力挺微软 Edge 浏览器：比 Chrome 更快、更省内存",
                (
                    "一名苹果用户在社交平台吐槽 Mac 上使用微软 Edge 浏览器，评论区 Mac 用户为 Edge 辩护，"
                    "称其内存占用低、性能出色、兼容政企网站，并可参与必应积分活动。"
                ),
            ),
        ]

        for title, summary in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
                self.assertEqual(tier, "weak", reason)

    def test_ambiguous_apple_terms_do_not_create_relevance_by_themselves(self):
        module = load_module()

        self.assertEqual(module.effective_apple_term_score("Safari EV 将作为塔塔汽车的电动车推出"), 0)
        self.assertEqual(module.effective_apple_term_score("佩尼库克和罗斯林的校舍内建设超算"), 0)

    def test_direct_apple_supplier_and_memory_policy_stories_remain_strong(self):
        module = load_module()
        memory_title = "Apple asks Trump to let it buy memory from a blacklisted supplier"
        memory_summary = (
            "Apple asked the Trump administration to approve buying RAM from Chinese supplier CXMT "
            "after product price increases caused by memory and storage shortages."
        )
        leak_title = "苹果供应商发生泄密事件：630G文件被窃取 官方已展开调查"
        leak_summary = (
            "苹果在印度的主要供应商 Tata Electronics 遭受网络攻击，超过 20 万份文件被窃取，"
            "其中包括 iPhone 电路板零件制造规格，并且苹果已派安全团队合作调查。"
        )

        self.assertEqual(module.classify_relevance_tier(memory_title, memory_summary, [], "AppleInsider")[0], "strong")
        self.assertEqual(module.classify_relevance_tier(leak_title, leak_summary, [], "快科技")[0], "strong")

    def test_apple_specific_market_report_stays_strong(self):
        module = load_module()
        title = "Counterpoint: iPhone shipments grew 8% in Latin America during Q1"
        summary = (
            "Counterpoint says Apple's iPhone shipments grew 8% year over year in Latin America, "
            "with Apple gaining share in premium phones."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "strong", reason)

    def test_routine_retail_discount_story_stays_weak(self):
        module = load_module()
        title = "iPhone 17 全系国补再来：17 Pro Max 京东 8499 元，换新折后再降价"
        summary = "京东国补和以旧换新活动让 iPhone 17 Pro Max 到手价降至 8499 元。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)

    def test_official_apple_service_promo_is_not_treated_as_routine_retail_discount(self):
        module = load_module()
        title = "Apple Card Promo to Offer Free AirPods Pro 3"
        summary = "Apple will run an Apple Card promotion offering free AirPods Pro 3 for eligible purchases."

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "strong", reason)

    def test_broad_market_report_does_not_merge_with_foldable_iphone_supply_chain(self):
        module = load_module()
        foldable = article_for(
            module,
            "供应链公司称已向苹果首款折叠屏 iPhone 小批量供货，新机预计 9 月发布",
            "苹果供应链公司人士称已开始向首款折叠屏 iPhone 小批量供货，目标指引为 2026 年秋季发布。",
            source="IT之家",
        )
        broad_market = article_for(
            module,
            "Omdia 报告：2026 年第一季度中国大陆 PC 出货量下滑 2%，联想华为苹果前三",
            (
                "Omdia 报告显示中国大陆 PC 和平板电脑市场分别同比下降。"
                "联想、华为、苹果占据 PC 市场前三，市场疲软主要受到零部件成本上涨和补贴力度减弱影响。"
            ),
            source="IT之家",
        )

        events = module.cluster_articles([foldable, broad_market])

        self.assertEqual(len(events), 2)

    def test_broad_apple_product_roadmap_merges_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple to Release These 20 New Products Across Rest of 2026 and 2027",
                (
                    "Mark Gurman says Apple has around 20 new products planned across the rest of 2026 and 2027, "
                    "including iPhone 18 Pro, foldable iPhone Ultra, MacBook Ultra, OLED iPad mini, Apple Watch, "
                    "AirPods Ultra, HomePod, Apple TV, and Apple Glasses."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果未来两年新品大爆发！20款产品蓄势待发 首款折叠屏iPhone领衔",
                (
                    "古尔曼透露，苹果计划从今年下半年到 2027 年推出约 20 款新品，覆盖 iPhone、Mac、iPad、"
                    "Apple Watch、智能家居、AirPods Ultra 和 Apple Glasses 等多个产品线。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "快科技"})
        self.assertEqual(events[0].category, "hardware_products")

    def test_broad_apple_product_roadmap_does_not_merge_with_single_iphone_air_story(self):
        module = load_module()
        roadmap = article_for(
            module,
            "Apple to Release These 20 New Products Across Rest of 2026 and 2027",
            (
                "Mark Gurman says Apple has around 20 new products planned across iPhone, Mac, iPad, Apple Watch, "
                "AirPods Ultra, HomePod, Apple TV, and Apple Glasses."
            ),
            source="MacRumors",
        )
        iphone_air = article_for(
            module,
            "机型定位“降档”：消息称苹果 iPhone Air 2 手机仅采用 A20 标准版芯片",
            "消息称 iPhone Air 2 将采用标准版 A20 芯片，而非 iPhone 18 Pro 系列和折叠屏 iPhone 使用的 A20 Pro。",
            source="IT之家",
        )

        events = module.cluster_articles([roadmap, iphone_air])

        self.assertEqual(len(events), 2)

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

    def test_blacklisted_memory_supplier_approval_reports_merge_with_price_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple asks Trump admin to approve Chinese RAM after product price increases",
                (
                    "Apple is lobbying the Trump administration for clearance to buy memory chips "
                    "from CXMT, a Chinese supplier on a Pentagon blacklist. The request is intended "
                    "to ease pressure from recent Apple product price increases caused by memory costs."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple asks Trump to let it buy memory from a blacklisted supplier",
                (
                    "Apple has petitioned the Trump administration to allow it to buy Mac RAM chips "
                    "from CXMT, a Chinese memory supplier on the Chinese Military Company Blacklist, "
                    "because the global memory crisis is increasing component costs."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "iPhone 18 Pro memory rumor points to 96-bit LPDDR6 support",
                (
                    "A separate board leak claims Apple's A20 Pro chip may use a WMCM package and "
                    "support 96-bit LPDDR6 memory for the iPhone 18 Pro."
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        supplier_event = next(
            event for event in events if {article.source for article in event.articles} == {"9to5Mac", "AppleInsider"}
        )
        self.assertEqual({article.source for article in supplier_event.articles}, {"9to5Mac", "AppleInsider"})

    def test_short_list_items_after_context_lead_are_preserved_as_key_facts(self):
        module = load_module()
        html = """
        <article class="post-content">
          <p>iPadOS 27 drops support for all devices with an A12 or A12X chipset, including:</p>
          <ul>
            <li><a href="https://example.com/ipad">iPad (8th generation)</a> - 2020</li>
            <li><a href="https://example.com/air">iPad Air (3rd generation)</a> - 2019</li>
            <li><a href="https://example.com/mini">iPad mini (5th generation)</a> - 2019</li>
            <li><a href="https://example.com/pro11">iPad Pro (11-inch, 1st generation)</a> - 2018</li>
            <li><a href="https://example.com/pro129">iPad Pro (12.9-inch, 3rd generation)</a> - 2018</li>
          </ul>
          <p>iOS 27 continues to support every iPhone model that ran iOS 26.</p>
        </article>
        """

        units = module.extract_text_units(html)
        facts = module.extract_key_facts(
            html,
            "iPadOS 27: Apple is leaving these five iPad models behind",
            "9to5Mac",
        )
        article = article_for(
            module,
            "iPadOS 27: Apple is leaving these five iPad models behind",
            "iPadOS 27 drops support for five older iPad models while iOS 27 keeps supporting all iOS 26 iPhones.",
            source="9to5Mac",
            facts=facts,
        )
        event = module.cluster_articles([article])[0]
        combined = " ".join(event.key_facts)

        self.assertIn(("li", "iPad (8th generation) - 2020"), units)
        for item in [
            "iPad (8th generation) - 2020",
            "iPad Air (3rd generation) - 2019",
            "iPad mini (5th generation) - 2019",
            "iPad Pro (11-inch, 1st generation) - 2018",
            "iPad Pro (12.9-inch, 3rd generation) - 2018",
        ]:
            with self.subTest(item=item):
                self.assertIn(item, combined)

    def test_mydrivers_related_news_block_does_not_enter_key_facts(self):
        module = load_module()
        html = """
        <html><body>
          <div class="news_info">
            <p>苹果自研芯片在之前在内存带宽方面的重视程度不够，但随着 M7 芯片的推出，将会有明显改善。</p>
            <p>据称 M7 的统一内存带宽将提高到 240GB/s，仍低于目前 M5 Pro 的 307GB/s，但比 M5 的 153GB/s 提升明显。</p>
            <div style="overflow: hidden;font-size:14px;padding-top:30px;border-bottom:1px solid #eee;">
              <p class="zhuanzai">【本文结束】如需转载请务必注明出处：快科技</p>
            </div>
          </div>
          <div class="navs_newsinfo xg_newsinfo">
            <h6>相关资讯</h6>
            <ul>
              <li><a href="https://news.mydrivers.com/1/1132/1132478.htm">全系万元起步！苹果iPhone 18 Pro将迎来近十年最大涨幅</a></li>
            </ul>
          </div>
        </body></html>
        """

        facts = module.extract_key_facts(
            html,
            "苹果M6芯片可能没有Pro/MAX M7将大幅提高AI性能",
            "快科技",
        )
        combined = " ".join(facts)

        self.assertIn("240GB/s", combined)
        self.assertNotIn("全系万元起步", combined)

    def test_mydrivers_end_marker_cuts_plain_related_news_tail(self):
        module = load_module()
        title = "捡到 iPhone 别急着刷机：30 秒打开查找功能能提高找回概率"
        html = """
        <html><body>
          <div class="news_info">
            <p>如果哪天出门不小心把 iPhone 丢了，用户可以通过查找 App 标记为丢失并显示联系电话。</p>
            <p>苹果提醒用户提前打开查找网络、发送最后的位置和丢失模式，这些设置能帮助找回设备。</p>
            <p class="zhuanzai">【本文结束】如需转载请务必注明出处：快科技</p>
            <h3>相关资讯</h3>
            <p>海量未公开机密数据流入暗网，印度政府调查苹果供应商塔塔电子数据泄露事件，超过 630GB 文件包含 iPhone 18 Pro 主板图纸。</p>
          </div>
        </body></html>
        """

        summary = module.extract_summary(html, title)
        facts = module.extract_key_facts(html, title, "快科技")
        combined = " ".join([summary, *facts])

        self.assertIn("查找", summary)
        self.assertNotIn("塔塔", combined)
        self.assertNotIn("630GB", combined)
        self.assertFalse(module.is_apple_product_data_leak_story(combined, title))

    def test_memory_supplier_approval_does_not_absorb_distinct_price_followups(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple asks Trump admin to approve Chinese RAM after product price increases",
                (
                    "Apple is lobbying the Trump administration for clearance to buy memory chips "
                    "from CXMT, a Chinese supplier on a Pentagon blacklist. The request is intended "
                    "to ease pressure from recent Apple product price increases caused by memory costs."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple asks Trump to let it buy memory from a blacklisted supplier",
                (
                    "Apple has petitioned the Trump administration to allow it to buy Mac RAM chips "
                    "from CXMT, a Chinese memory supplier on the Chinese Military Company Blacklist."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "苹果被迫游说特朗普政府放行长鑫存储芯片",
                (
                    "苹果正在华盛顿寻求特批通道，希望允许其从被五角大楼列入黑名单的长鑫存储 CXMT "
                    "采购内存芯片，以缓解 iPhone 18 Pro 的成本压力。"
                ),
                source="cnBeta",
            ),
            article_for(
                module,
                "苹果上调产品售价 马斯克公开声援库克：这辈子没见过这么大涨幅",
                (
                    "马斯克转发库克采访并表示内存涨价幅度罕见。苹果已上调 Mac、iPad、Vision Pro、"
                    "HomePod 等 14 款产品价格，MacBook Air 起售价从 8499 元升至 9999 元。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "美光高管怒怼苹果：芯片涨45美元 你终端加价250美元",
                (
                    "美光高管和财经博主围绕苹果成本转嫁发生争议，称苹果曾长期压低内存采购价格，"
                    "如今芯片涨 45 美元却向消费者加价 250 美元。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "新机涨价官翻补位！MacBook Neo官翻版上架：679美元 苹果最便宜笔记本",
                (
                    "苹果官方翻新版 MacBook Neo 512GB 版本上架，价格为 679 美元，比全新机型便宜 "
                    "120 美元，并享受苹果标准保修服务。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "8999元成历史！iPhone 18 Pro涨价不可逆：内存问题解决也不降回原价",
                (
                    "TrendForce 数据显示 DRAM 价格在 2026 年第一季度暴涨 98%，第二季度预计继续上涨 "
                    "58% 至 63%。Mark Gurman 认为 iPhone 18 Pro 涨价后不会降回原价。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)
        titles_by_event = [[article.title for article in event.articles] for event in events]

        supplier_events = [
            event for event in events if any("CXMT" in article.summary or "长鑫" in article.summary for article in event.articles)
        ]
        self.assertEqual(len(supplier_events), 1)
        self.assertEqual({article.source for article in supplier_events[0].articles}, {"9to5Mac", "AppleInsider", "cnBeta"})
        self.assertGreaterEqual(len(events), 5, titles_by_event)
        self.assertTrue(any("官翻版" in " ".join(titles) for titles in titles_by_event))
        self.assertTrue(any("iPhone 18 Pro涨价不可逆" in " ".join(titles) for titles in titles_by_event))

    def test_direct_apple_product_price_increase_stays_strong_despite_supplier_background(self):
        module = load_module()
        title = "Report: iPhone 18 Pro Could Start at $1,399 Amid Price Hikes"
        summary = (
            "Apple price increases are coming across its lineup due to rising memory chip costs. "
            "The Wall Street Journal estimates the iPhone 18 Pro could start as high as $1,399. "
            "The price hikes stem from a global shortage of DRAM and NAND flash storage, with "
            "Samsung Electronics and Micron shifting production toward enterprise-scale memory chips."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "strong", reason)

    def test_routine_price_buying_advice_does_not_merge_with_direct_price_report(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Report: iPhone 18 Pro Could Start at $1,399 Amid Price Hikes",
                (
                    "Apple price increases are coming due to rising memory chip costs, and "
                    "The Wall Street Journal estimates the iPhone 18 Pro could start as high as $1,399. "
                    "DRAM and NAND flash storage costs are projected to rise sharply."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果全面涨价：分析一下现在上车还是等iPhone 18",
                (
                    "库克表示受内存和存储成本上涨影响，苹果产品未来可能涨价。"
                    "文章主要分析用户应该现在买 iPhone 17 还是等 iPhone 18，并给出换机建议。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual({event.relevance_tier for event in events}, {"strong", "weak"})

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

    def test_service_content_cluster_requires_specific_content_anchor(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "You Can Watch All of F1's 2026 Austrian Grand Prix For Free on Apple TV",
                "Apple announced every part of Formula 1's 2026 Austrian Grand Prix will stream live on Apple TV for free.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Formula 1 Austrian Grand Prix will be free on Apple TV in the US",
                "Apple TV will stream an entire Formula 1 race weekend free to U.S. viewers for the first time.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "Apple Music Reveals Top 20 Most-Streamed Artists of All Time",
                "Apple teamed with Chart Data to share the top 20 most-streamed artists of all time, led by Drake, Taylor Swift, and Future.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Top 20 most streamed artists on Apple Music revealed",
                "The new Apple Music chart lists the top 20 artists of all time, including Taylor Swift, Bad Bunny, Ariana Grande, and Kendrick Lamar.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "Drake, Taylor Swift, and Future are the 3 most streamed artists in Apple Music history",
                "ChartData published Apple Music's Top 20 most streamed artists of all time.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple TV reveals new comedy series with Matthew McConaughey coming soon",
                "Apple TV announced the release date for Brothers, a new comedy series starring Matthew McConaughey and Woody Harrelson.",
                source="9to5Mac",
            ),
            article_for(
                module,
                'Apple TV comedy "Brothers" gets fall 2026 debut',
                'The Apple TV comedy "Brothers" starring Woody Harrelson and Matthew McConaughey premieres in fall 2026. The plot mentions a Texas governor as story background.',
                source="AppleInsider",
            ),
            article_for(
                module,
                "Vince Gilligan reveals the current status of ‘Pluribus’ season 2",
                "Vince Gilligan offered an update on the progress of season 2, which is still being written and produced.",
                facts=["Pluribus is an Apple TV series, but this article is a distinct production-status update."],
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 4)
        event_sources = [{article.source for article in event.articles} for event in events]
        event_texts = [" ".join([event.title, event.summary, *event.key_facts]) for event in events]
        self.assertIn({"MacRumors", "AppleInsider"}, event_sources)
        self.assertIn({"MacRumors", "AppleInsider", "9to5Mac"}, event_sources)
        self.assertTrue(
            any(sources == {"9to5Mac", "AppleInsider"} and "Brothers" in text for sources, text in zip(event_sources, event_texts))
        )
        self.assertTrue(
            any(sources == {"9to5Mac"} and "Pluribus" in text for sources, text in zip(event_sources, event_texts))
        )
        self.assertNotIn("mixed primary topic facets", {warning for event in events for warning in event.merge_warnings})

    def test_apple_tv_series_plot_region_does_not_become_regional_regulation(self):
        module = load_module()
        title = 'Apple TV comedy "Brothers" gets fall 2026 debut'
        summary = (
            'The Apple TV comedy "Brothers" stars Woody Harrelson and Matthew McConaughey. '
            "Its fictional plot mentions a Texas governor, but the story is about an Apple TV premiere."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "service_content")
        self.assertEqual(module.classify_relevance_tier(title, summary, [], "AppleInsider")[0], "strong")

    def test_a12_a13_bootrom_exploit_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple's A12 and A13 Chips Facing New Unpatchable Exploit",
                "Paradigm Shift published details of usbliter8, a BootROM vulnerability affecting Apple's A12 and A13 chips.",
                source="MacRumors",
            ),
            article_for(
                module,
                "A12 & A13 Apple devices face an unpatchable SecureROM vulnerability",
                "Security researchers published a new unpatchable SecureROM exploit for Apple's A12 and A13 chips.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "New unpatchable exploit targets Apple devices with A12 and A13 chips",
                "Researchers at Paradigm Shift published technical details of usbliter8, a new iPhone BootROM vulnerability.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "无法软件修复：苹果 A12/A13 芯片曝新漏洞，影响 iPhone 11 系列等",
                "安全公司 Paradigm Shift 发布影响苹果 A12 和 A13 芯片的 BootROM 漏洞 usbliter8，因固化在芯片中无法通过软件修复。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "AppleInsider", "9to5Mac", "IT之家"})

    def test_find_my_hide_location_features_merge_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 Adds These New Features to Find My, Including 'Hide Location'",
                "iOS 27 adds Find My improvements including Hide Location, custom sharing durations, and landscape support.",
                source="MacRumors",
            ),
            article_for(
                module,
                "初探苹果 iOS 27 系统“查找”App：支持隐藏共享位置、自定义共享时长",
                "iOS 27 的查找应用新增隐藏位置功能，可暂停共享位置，并支持自定义共享时长和横屏模式。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 iOS 27 的查找应用支持隐藏位置和自定义共享时长",
                "报道称 iOS 27 Find My 支持 Hide Location、15 分钟到 30 天的共享时长以及横屏界面。",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家", "cnBeta"})

    def test_brazil_app_store_policy_is_strong_and_merges_direct_policy_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Announces Major App Store Changes on iOS in Brazil",
                "Apple announced that developers in Brazil can distribute iPhone apps through alternative app marketplaces and accept payments through third-party platforms.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple announces changes to iOS in Brazil",
                "Apple said Brazil developers may use alternative app marketplaces, external links, and new payment options under a CADE agreement.",
                source="Apple Newsroom",
            ),
            article_for(
                module,
                "Apple announces major App Store changes for Brazil, including alternative app marketplaces",
                "Apple is making iOS App Store changes in Brazil, adding alternative marketplaces, web distribution, and third-party payment options.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果巴西 App Store 重大调整落地：开放第三方应用商店与内购，全新佣金体系公布",
                "苹果在巴西落地 App Store 政策调整，允许第三方应用商店分发应用，并开放多种内购方式和全新佣金体系。",
                source="IT之家",
            ),
        ]

        tiers = [module.classify_relevance_tier(article.title, article.summary, article.key_facts, article.source)[0] for article in articles]
        events = module.cluster_articles(articles)

        self.assertEqual(tiers, ["strong", "strong", "strong", "strong"])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "Apple Newsroom", "9to5Mac", "IT之家"})

    def test_third_party_or_legacy_context_stories_are_deferred_weak(self):
        module = load_module()
        cases = [
            (
                "How to update an iPad with your Mac when Software Update fails",
                "A Mac can update an iPad using the same iPadOS software Apple delivers through Software Update. Here's how Finder can help recover failed installs.",
                "AppleInsider",
            ),
            (
                "小米发布并开源 Xiaomi Miloco 2.0：接入 OpenClaw，让 AI 掌控全屋智能",
                "小米发布全屋智能 AI 开源方案 Xiaomi Miloco 2.0，底层由小米自研 MiMo 大模型驱动，页面模板提到苹果客户端。",
                "快科技",
            ),
            (
                "AI 公司 Midjourney 跨界发布首款硬件“全身超声波扫描仪”：前苹果 Vision Pro 工程师带队",
                "Midjourney 成立医疗部门并推出全身超声波扫描仪，项目由前苹果 Vision Pro 工程师带队，但不是 Apple 产品或服务。",
                "IT之家",
            ),
            (
                "诞生至今已有 41 年，Linux 7.2 内核将移除苹果 AppleTalk 协议",
                "Linux 上游开发者将移除苹果 1985 年推出的 AppleTalk 网络协议，苹果官方早已停止支持该历史协议。",
                "IT之家",
            ),
        ]

        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_non_apple_swift_observatory_link_story_is_not_developer_tool(self):
        module = load_module()
        title = "Link 卫星 6 月 27 日发射：10 个月打造，拯救 5 亿美元价值雨燕天文卫星"
        summary = (
            "NASA 的 Neil Gehrels Swift Observatory 轨道高度持续衰减，Katalyst 将发射 Link 卫星执行救援任务。"
            "文章主题是航天器轨道救援、合同金额和发射窗口。"
        )

        self.assertFalse(module.is_apple_developer_tool_story(f"{title} {summary}"))
        self.assertNotEqual(module.detect_event_kind(title, summary), "developer_tool")
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_xr_smart_glasses_iphone_moment_is_deferred_weak(self):
        module = load_module()
        title = "2026 最强智能眼镜发布，但「iPhone 时刻」还没到来"
        summary = (
            "Xreal Aura 搭载 Android XR、Gemini 和高通 XR 芯片，Snap SPECS 也公布了更长续航。"
            "文章用 iPhone 时刻作为行业拐点类比，但没有 Apple 新产品、Vision Pro 策略或苹果官方动作。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "爱范儿")
        self.assertEqual(tier, "weak", reason)

    def test_apple_music_top_artists_chart_merges_cnbeta_followup(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Music Reveals Top 20 Most-Streamed Artists of All Time",
                "Apple teamed with Chart Data to share the top 20 most-streamed artists of all time, led by Drake, Taylor Swift, and Future.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Top 20 most streamed artists on Apple Music revealed",
                "The new Apple Music chart lists the top 20 artists of all time, including Taylor Swift, Bad Bunny, Ariana Grande, and Kendrick Lamar.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "Apple Music公布最常被收听艺术家前二十名 Drake居首 Taylor Swift紧随其后",
                "苹果与 Chart Data 合作首次公布 Apple Music 平台史上最常被串流收听艺术家前二十名，Drake 第一，Taylor Swift 第二，Future 第三。",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "AppleInsider", "cnBeta"})

    def test_third_party_cpu_benchmark_using_apple_chip_as_comparison_stays_weak(self):
        module = load_module()
        title = "最弱 Wildcat Lake：英特尔酷睿 3 304 单核跑分追平苹果 A18 Pro，核心数还少一个"
        summary = (
            "英特尔 Wildcat Lake 入门级处理器酷睿 3 304 最新 PassMark 跑分曝光，"
            "单核成绩跃升至 3982 分，与苹果 A18 Pro 平均分持平。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)
        self.assertIn("third-party", reason)

    def test_third_party_cpu_benchmark_does_not_merge_with_apple_product_price_increase(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Report: iPhone 18 Pro Could Start at $1,399 Amid Price Hikes",
                (
                    "Apple price increases are coming due to rising memory chip costs, and "
                    "The Wall Street Journal estimates the iPhone 18 Pro could start as high as $1,399. "
                    "DRAM and NAND flash storage costs are projected to rise sharply."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "最弱 Wildcat Lake：英特尔酷睿 3 304 单核跑分追平苹果 A18 Pro，核心数还少一个",
                (
                    "英特尔 Wildcat Lake 入门级处理器酷睿 3 304 最新 PassMark 跑分曝光，"
                    "单核成绩跃升至 3982 分，与苹果 A18 Pro 平均分持平。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertEqual({event.relevance_tier for event in events}, {"strong", "weak"})

    def test_carplay_ios_platform_feature_update_is_strong_software_news(self):
        module = load_module()
        title = "What Siri AI, Apple TV, & more are like with CarPlay in iOS 27"
        summary = (
            "CarPlay is seeing one of its biggest updates in years thanks to iOS 27, "
            "including the new Siri AI orb, a chat-style app interface, first-party and "
            "third-party media app upgrades, and a mini player for Apple Music and Podcasts."
        )
        facts = [
            "CarPlay, Apple's in-car UI, is powered by iOS, so iOS 27 brings enhancements to the car.",
            "Apple is allowing any app to offer a conversation mode in CarPlay.",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "AppleInsider")

        self.assertEqual(module.detect_event_kind(title, summary, facts), "os_app")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_routine_third_party_carplay_app_availability_stays_weak(self):
        module = load_module()
        title = "Spotify launches redesigned app for CarPlay users"
        summary = (
            "Spotify's third-party app is now available with a redesigned CarPlay interface "
            "for iPhone users, adding larger album art and queue controls."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)
        self.assertIn("third-party", reason)

    def test_third_party_app_update_with_ios_carplay_terms_stays_weak(self):
        module = load_module()
        title = "Pocket Casts update brings three new features, including CarPlay chapter artwork"
        summary = (
            "Pocket Casts version 8.15 adds CarPlay chapter artwork, a Siri shortcut, and a "
            "Lock Screen or Control Center control. The third-party podcast app also drops "
            "support for iOS 16 and watchOS 9. That means Pocket Casts app updates now require "
            "iOS 17 and watchOS 10 or later. The release also fixes an Apple Watch episode heading."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_travel_app_update_stays_weak_even_with_apple_platform_context(self):
        module = load_module()
        title = "Flighty Update Adds Step-by-Step Guide for Connecting Flights"
        summary = (
            "Flighty, a third-party travel app for iPhone and Apple Watch, added a Connection "
            "Assistant feature that helps travelers make connecting flights."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_harmonyos_wechat_update_stays_weak_when_apple_is_not_primary_subject(self):
        module = load_module()
        title = "微信鸿蒙版灰度测试聊天实况照片发送功能，补齐私聊场景短板"
        summary = "微信鸿蒙版正在灰度测试聊天实况照片发送功能，功能面向鸿蒙系统用户，与苹果 iPhone 仅作为实况照片格式背景相关。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_competitor_product_event_before_apple_launch_stays_weak(self):
        module = load_module()
        title = "Google's Pixel 11 Event Set for August 12, a Month Before Apple Debuts Foldable iPhone"
        summary = (
            "Google will introduce Pixel 11 smartphones and a Pixel 11 Pro Fold at an August 12 event, "
            "about a month before Apple is expected to introduce new iPhone models. The body also mentions "
            "related iPhone 18 Pro thickness rumors and foldable iPhone timing as market context."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_competitor_product_event_does_not_merge_into_foldable_iphone_timing(self):
        module = load_module()
        competitor = article_for(
            module,
            "Google's Pixel 11 Event Set for August 12, a Month Before Apple Debuts Foldable iPhone",
            (
                "Google will introduce Pixel 11 smartphones and a Pixel 11 Pro Fold at an August 12 event, "
                "about a month before Apple is expected to introduce new iPhone models. The body also mentions "
                "foldable iPhone release timing as market context."
            ),
            "MacRumors",
        )
        foldable = article_for(
            module,
            "Foldable iPhone Ultra May Launch After iPhone 18 Pro Models",
            "Apple's first foldable iPhone may launch after the iPhone 18 Pro models, with preorders possibly delayed until the fourth quarter.",
            "MacRumors",
        )

        events = module.cluster_articles([competitor, foldable])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertFalse(module.events_should_merge(event_for(module, competitor), event_for(module, foldable)))
        self.assertEqual(len(events), 2, clusters)
        self.assertFalse(any(competitor.title in cluster and foldable.title in cluster for cluster in clusters), clusters)

    def test_competitor_foldable_phone_event_does_not_merge_into_apple_foldable_timing(self):
        module = load_module()
        competitor = article_for(
            module,
            "三星官宣7月22日发布会：Z Fold 8设计大改 对标苹果折叠机",
            (
                "三星将推出 Galaxy Z Fold 8，文章把新机设计与苹果计划推出的折叠款 iPhone 作比较，"
                "但主语和动作都是三星发布会。"
            ),
            "cnBeta",
        )
        foldable = article_for(
            module,
            "Foldable iPhone Ultra May Launch After iPhone 18 Pro Models",
            "Apple's first foldable iPhone may launch after the iPhone 18 Pro models, with preorders possibly delayed until the fourth quarter.",
            "MacRumors",
        )

        self.assertEqual(competitor.relevance_tier, "weak", competitor.relevance_reason)
        self.assertFalse(module.events_should_merge(event_for(module, competitor), event_for(module, foldable)))

    def test_third_party_ai_service_expanding_to_iphone_stays_weak(self):
        module = load_module()
        title = "Claude Cowork Expands to iPhone and the Web"
        summary = (
            "Anthropic is bringing Claude Cowork to mobile and the web, letting the third-party AI service "
            "continue cloud tasks across devices including iPhone."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_broad_android_user_apple_ai_survey_stays_weak(self):
        module = load_module()
        title = "安卓用户也不给苹果AI面子：不会因此而转向iPhone手机"
        summary = (
            "一项消费者调查称，Android 用户不会因为 Apple Intelligence 大规模上线就转向 iPhone；"
            "文章讨论消费者换机意愿，没有新的苹果系统、服务或硬件动作。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_broad_windows_desktop_share_report_stays_weak(self):
        module = load_module()
        title = "StatCounter 称 6 月全球桌面系统中 Windows 占比首次跌破 60%"
        summary = (
            "StatCounter 数据显示 Windows 全球桌面系统份额首次跌破 60%，macOS 和 Linux 作为对比数据出现，"
            "但文章主体是 Windows 桌面份额变化。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_apple_executive_government_meeting_is_relevant_and_high_priority(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/07/tim-cook-and-john-ternus-hold-virtual-meeting-with-minister-president-of-bavaria/",
            title="Tim Cook and John Ternus hold virtual meeting with Minister-President of Bavaria",
            summary=(
                "Apple CEO Tim Cook and hardware chief John Ternus held a virtual meeting with "
                "Bavarian Minister-President Markus Söder about Apple's more than 2,000 jobs in "
                "Munich, investment in Bavaria, data protection, and overregulation."
            ),
            feed_time_raw="2026-07-07T20:45:00+00:00",
            context="apple executive government meeting bavaria munich investment jobs regulation",
        )
        pocket = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/07/pocket-casts-update-brings-three-new-features-including-carplay-chapter-artwork/",
            title="Pocket Casts update brings three new features, including CarPlay chapter artwork",
            summary="Pocket Casts version 8.15 adds CarPlay chapter artwork, a Siri shortcut, and drops iOS 16 support.",
            feed_time_raw="2026-07-07T15:42:00+00:00",
            context="carplay ios podcast app",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary, [candidate.context]), "company_org")
        tier, reason = module.classify_relevance_tier(candidate.title, candidate.summary, [candidate.context], "9to5Mac")
        self.assertEqual(tier, "strong", reason)
        self.assertGreater(module.candidate_detail_priority(candidate), module.candidate_detail_priority(pocket))

    def test_texas_app_store_age_verification_regulation_stays_strong(self):
        module = load_module()
        title = "Apple must continue to age-verify users in Texas, says one-sentence ruling"
        summary = (
            "A court ruling says Apple must continue age verification for App Store and Apple ID "
            "users in Texas while litigation over the state law continues."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(module.detect_event_kind(title, summary), "regional_regulation")
        self.assertEqual(tier, "strong", reason)

    def test_apple_pushed_airpods_firmware_is_not_third_party_accessory_story(self):
        module = load_module()
        title = "苹果向 AirPods Pro 3 等耳机推送 9A5314b 开发固件，支持 GymKit 健身器材同步心率"
        summary = (
            "苹果向 AirPods Pro 3、AirPods 4 和 AirPods Max 推送 9A5314b 开发者测试固件，"
            "新增 iOS 27 相关功能，并支持 GymKit 健身器材同步心率数据。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertFalse(module.is_third_party_accessory_platform_compatibility_story(title, summary))
        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_airpods_beta_firmware_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Releases New AirPods Beta Firmware With iOS 27 Features",
                "Apple released 9A5314b beta firmware for AirPods Pro 3, AirPods 4, and AirPods Max with iOS 27 features.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple releases new beta firmware for AirPods Pro 3 and more",
                "Apple's new AirPods beta firmware enables developer testing of upcoming iOS 27 AirPods features.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果向 AirPods Pro 3 等耳机推送 9A5314b 开发固件，支持 GymKit 健身器材同步心率",
                "苹果向 AirPods Pro 3、AirPods 4 和 AirPods Max 推送 9A5314b 开发者测试固件，并支持 GymKit 健身器材同步心率数据。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "os_app")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "9to5Mac", "IT之家"})

    def test_airpods_max_condensation_lawsuit_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "AirPods Max Condensation Lawsuit Largely Dismissed by NY Judge",
                (
                    "A New York judge largely dismissed an AirPods Max condensation class-action "
                    "lawsuit, while allowing some warranty-related claims to proceed."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "AirPods Max condensation lawsuit significantly narrowed by judge",
                (
                    "A judge significantly narrowed a lawsuit accusing Apple of selling AirPods Max "
                    "with condensation issues, dismissing most claims but leaving a narrow path forward."
                ),
                "9to5Mac",
            ),
            article_for(
                module,
                "No sweat: Most claims stricken in AirPods Max condensation lawsuit",
                (
                    "Most claims in the AirPods Max condensation lawsuit were struck, with Apple "
                    "facing only a narrowed set of allegations."
                ),
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "legal_antitrust")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "9to5Mac", "AppleInsider"})

    def test_beats_power_pink_cables_merge_as_official_accessory_event(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Beats Charging Cables Now Available in 'Power Pink'",
                (
                    "Apple's Beats charging cables are now available in a new Power Pink color "
                    "from Apple's online store."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 Beats 充电线新配色 Power Pink 上架：USB-C、USB-C to Lightning 可选",
                (
                    "苹果官网上架 Beats 充电线 Power Pink 新配色，提供 USB-C to USB-C、"
                    "USB-C to Lightning 和 USB-C to Apple Watch 磁力充电线。"
                ),
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_ios_signing_closure_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple stops signing iOS 26.5.1 after critical security fix release",
                "Apple has stopped signing iOS 26.5.1, preventing iPhone users from downgrading after installing iOS 26.5.2.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果停止签署 iOS26.5/iOS 26.5.1 系统，已升级 26.5.2 的 iPhone 用户无法再降级",
                "苹果关闭 iOS 26.5 和 iOS 26.5.1 签名验证，已升级到 iOS 26.5.2 的 iPhone 用户无法再降级。",
                "IT之家",
            ),
            article_for(
                module,
                "升了就回不去了！苹果关闭iOS 26.5/26.5.1签名验证",
                "苹果关闭 iOS 26.5 和 iOS 26.5.1 签名通道，iPhone 用户升级后无法回退到旧系统。",
                "快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "os_app")
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家", "快科技"})

    def test_siri_ai_third_party_app_data_feature_stays_strong(self):
        module = load_module()
        title = "Siri AI can pull info from third-party apps in the latest developer beta"
        summary = (
            "We've been looking out for new features in iOS 27 beta 3, and the latest developer "
            "beta allows Siri AI to access information from third-party apps. The only examples "
            "seen so far are pulling in the remaining battery from electric car apps, and it works "
            "with Tesla via the Tessie app."
        )
        facts = [
            "Siri AI can use third-party apps in iOS 27 beta 3.",
            "Siri 会先向用户申请应用访问权限，之后调取第三方应用内的数据。",
            "该功能目前暂不支持特斯拉官方 App。",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "9to5Mac")

        self.assertEqual(module.detect_event_kind(title, summary, facts), "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_ios_public_beta_timing_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 Public Beta is Coming Soon",
                "Apple is expected to release the first iOS 27 public beta soon, likely after the third or fourth developer beta.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果iOS 27公测版最快下周发布！升级教程收好：iPhone 11及以上都能体验",
                "苹果 iOS 27 公测版最快下周发布，iPhone 11 及以上机型可通过测试版更新入口体验。",
                "快科技",
            ),
            article_for(
                module,
                "iOS 27 公测版即将发布 苹果提醒用户提前做好准备",
                "苹果提醒用户在 iOS 27 公测版即将发布前做好备份和测试版设置准备。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "os_app")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "快科技", "cnBeta"})

    def test_os_public_beta_four_reports_merge_across_platform_scope(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Seeds Fourth Public Betas of iOS 26.6, macOS Tahoe 26.6 and More",
                "Apple seeded the fourth public betas of iOS 26.6, iPadOS 26.6, macOS Tahoe 26.6, watchOS 26.6, and tvOS 26.6.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果推送 iOS / iPadOS 26.6 第四个公测版，修复 Bug / 改进安全",
                "苹果推送 iOS 26.6 和 iPadOS 26.6 第四个公测版，主要修复 Bug 并改进安全。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "os_app")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_public_beta_setup_background_does_not_trigger_age_verification_regulation(self):
        module = load_module()
        title = "iOS 27 Public Beta is Coming Soon"
        summary = (
            "Apple announced the first iOS 27 public beta will be released in July. "
            "Users can prepare through beta.apple.com, Apple ID settings, and device setup; "
            "the support page also mentions family and child safety settings as background, "
            "and says users can continue after confirming those setup options."
        )

        self.assertFalse(module.is_direct_apple_regional_platform_regulation_story(title, summary))
        self.assertEqual(module.detect_event_kind(title, summary), "os_app")

    def test_jp_morgan_apple_stock_target_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Bullish JP Morgan bumps AAPL price target to $345",
                "J.P. Morgan raised its Apple stock target to $345 while staying bullish despite memory-driven hardware price hikes.",
                "AppleInsider",
            ),
            article_for(
                module,
                "J.P. Morgan raises Apple stock target despite hardware price hikes",
                "J.P. Morgan raised AAPL's price target to $345 and said Apple's hardware price hikes should not derail long-term revenue.",
                "9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "9to5Mac"})

    def test_foldable_iphone_launch_timing_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Foldable iPhone Ultra May Launch After iPhone 18 Pro Models",
                "Apple's first foldable iPhone may launch after the iPhone 18 Pro models, with preorders possibly delayed until the fourth quarter.",
                "MacRumors",
            ),
            article_for(
                module,
                "不会延期发售！果链确认：苹果首款折叠机iPhone Ultra可正常交付",
                "供应链人士称苹果首款折叠 iPhone Ultra 没有延期，预计 9 月发布后可以正常交付。",
                "快科技",
            ),
            article_for(
                module,
                "多位果链企业人士称“没听说”苹果首款折叠屏 iPhone 延期发售，预计 9 月可正常交付",
                "多位果链企业人士表示没有听说苹果首款折叠屏 iPhone 延期发售，预计 9 月发布并可正常交付。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "快科技", "IT之家"})

    def test_iphone_physical_dimension_rumors_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Weibo leaker says iPhone 18 Pro thickness will be ‘surprising’",
                (
                    "Days after materials from Apple supplier Tata surfaced online, Fixed Focus Digital said "
                    "both the iPhone 18 Pro body and rear camera plateau are thicker by about 2mm, with leaked "
                    "drop tests and A20 Pro documents."
                ),
                "9to5Mac",
            ),
            article_for(
                module,
                "iPhone 18 Pro Could Be Noticeably Thicker Than iPhone 17 Pro",
                (
                    "Fixed Focus Digital says the iPhone 18 Pro aluminum frame and camera housing are set to "
                    "grow thicker, with overall thickness around 9.9 to 10.9mm and a variable aperture main camera."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro's camera bump could be a little bit thicker",
                (
                    "The iPhone 18 Pro will probably be thicker thanks to a more generous camera plateau. "
                    "The design could be about 2 millimeters thicker than the 2025 release."
                ),
                "AppleInsider",
            ),
            article_for(
                module,
                "iPhone 18 Pro机身或明显增厚 继续采用铝合金中框",
                "爆料称 iPhone 18 Pro 铝合金中框和后置摄像头平台都将变厚，整体厚度预计增加约 2 毫米，并继续采用铝合金材质。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "MacRumors", "AppleInsider", "cnBeta"})

    def test_iphone_physical_dimension_events_remerge_after_topic_split(self):
        module = load_module()
        leak_article = article_for(
            module,
            "Weibo leaker says iPhone 18 Pro thickness will be ‘surprising’",
            (
                "Days after materials from Apple supplier Tata surfaced online, Fixed Focus Digital "
                "doubled down that the iPhone 18 Pro body and rear camera plateau are thicker. "
                "The stolen Tata files include logic board diagrams, A20 Pro documents, supplier lists, "
                "and drop-test videos."
            ),
            "9to5Mac",
        )
        dimension_article = article_for(
            module,
            "iPhone 18 Pro Could Be Noticeably Thicker Than iPhone 17 Pro",
            (
                "Fixed Focus Digital says the iPhone 18 Pro aluminum frame and camera housing are set "
                "to grow thicker, with overall thickness around 9.9 to 10.9mm and a variable aperture main camera."
            ),
            "MacRumors",
        )

        self.assertTrue(module.events_should_merge(event_for(module, leak_article), event_for(module, dimension_article)))

    def test_iphone_physical_dimension_title_gets_dedicated_primary_facet(self):
        module = load_module()
        facets = module.primary_topic_facets(
            "Weibo leaker says iPhone 18 Pro thickness will be ‘surprising’",
            (
                "Days after Tata supplier files surfaced online, the article says the iPhone 18 Pro "
                "body and rear camera plateau are thicker by about 2mm."
            ),
        )

        self.assertIn("iphone-physical-dimension-rumor", facets)
        self.assertNotIn("apple-product-data-leak", facets)
        self.assertNotIn("iphone-logic-board-leak", facets)

    def test_foldable_launch_timing_does_not_merge_with_iphone_thickness_context(self):
        module = load_module()
        thickness = article_for(
            module,
            "iPhone 18 Pro Could Be Noticeably Thicker Than iPhone 17 Pro",
            (
                "The iPhone 18 Pro's aluminum frame and camera housing are both set to grow thicker. "
                "The article mentions Apple's foldable iPhone launch timing as broader roadmap context."
            ),
            "MacRumors",
        )
        foldable = article_for(
            module,
            "Foldable iPhone Ultra May Launch After iPhone 18 Pro Models",
            "Apple's first foldable iPhone may launch after the iPhone 18 Pro models, with preorders possibly delayed until the fourth quarter.",
            "MacRumors",
        )

        self.assertFalse(module.events_should_merge(event_for(module, thickness), event_for(module, foldable)))

    def test_iphone_logic_board_leak_does_not_merge_with_physical_dimension_rumor(self):
        module = load_module()
        logic_board = article_for(
            module,
            "iPhone 18 Pro logic board leak reveals A20 Pro and LPDDR6 details",
            (
                "Leaked Tata files show the iPhone 18 Pro logic board, A20 Pro package, LPDDR6 memory, "
                "supplier lists, and component documents. The article mentions separate iPhone 18 Pro "
                "thickness rumors as background."
            ),
            "IT之家",
        )
        dimension = article_for(
            module,
            "Weibo leaker says iPhone 18 Pro thickness will be ‘surprising’",
            (
                "Fixed Focus Digital says the iPhone 18 Pro body and rear camera plateau are thicker by "
                "about 2mm, with overall thickness around 9.9 to 10.9mm."
            ),
            "9to5Mac",
        )

        events = module.cluster_articles([logic_board, dimension])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)
        self.assertFalse(any(logic_board.title in cluster and dimension.title in cluster for cluster in clusters), clusters)

    def test_iphone_data_leak_specs_do_not_bridge_into_physical_dimension_cluster(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro board schematics leak from supplier breach",
                (
                    "Leaked Tata files include iPhone 18 Pro logic board diagrams, A20 Pro data sheets, "
                    "LPDDR6 details, supplier lists, and component documents."
                ),
                "快科技",
            ),
            article_for(
                module,
                "iPhone 18 Pro logic board leak reveals A20 Pro and LPDDR6 details",
                "The iPhone 18 Pro logic board leak shows A20 Pro chip packaging, LPDDR6 memory, and component layout.",
                "IT之家",
            ),
            article_for(
                module,
                "Weibo leaker says iPhone 18 Pro thickness will be ‘surprising’",
                (
                    "Fixed Focus Digital says the iPhone 18 Pro body and rear camera plateau are thicker by "
                    "about 2mm, while mentioning the Tata breach as background."
                ),
                "9to5Mac",
            ),
            article_for(
                module,
                "iPhone 18 Pro Could Be Noticeably Thicker Than iPhone 17 Pro",
                "The iPhone 18 Pro aluminum frame and camera housing are set to grow thicker, with overall thickness around 9.9 to 10.9mm.",
                "MacRumors",
            ),
        ]

        events = module.cluster_articles(articles)
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)
        self.assertTrue(any(articles[0].title in cluster and articles[1].title in cluster for cluster in clusters), clusters)
        self.assertTrue(any(articles[2].title in cluster and articles[3].title in cluster for cluster in clusters), clusters)

    def test_third_party_charger_with_iphone_compatibility_stays_weak(self):
        module = load_module()
        title = "绿联 25W 磁吸无线充电器发售：适配苹果 iPhone 12-17 系列，139 元"
        summary = "绿联新推出一款 25W 磁吸无线充电器，配 1.5m 编织线，适配 iPhone 12 至 iPhone 17 系列。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_storage_enclosure_with_macos_compatibility_stays_weak(self):
        module = load_module()
        title = "华硕推出 ProArt 创梦 40Gbps 移动高速硬盘盒：内嵌智能风扇，569 元"
        summary = (
            "华硕推出 ProArt 创梦系列 40Gbps 移动高速硬盘盒，支持 USB4、NVMe/SATA、"
            "Windows、MacOS 和 Linux，京东售价 569 元。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_game_cross_platform_launches_stay_weak(self):
        module = load_module()
        cases = [
            (
                "腾讯重磅新游！《失控进化》今日上线：PC、iOS、安卓、鸿蒙多端互通",
                "腾讯开放世界沙盒生存新作《失控进化》全平台公测，支持 PC、iOS、安卓、鸿蒙和平板之间账号数据互通，游戏进度和社交关系可延续。",
                "快科技",
            ),
            (
                "网易海洋冒险 RPG《遗忘之海》今日公测，PC、安卓、苹果 iOS 数据互通",
                "网易 Joker 工作室海洋冒险 RPG《遗忘之海》PC 版公测，移动端计划随后上线，相同账号在 PC、iOS、安卓之间数据互通。",
                "IT之家",
            ),
            (
                "努比亚官宣：全球首款AI智能体手机下周首次亮相",
                "努比亚将发布 AI 智能体手机，文章提到苹果和 iPhone 只是行业对比，没有 Apple 产品、系统、服务或供应链动作。",
                "快科技",
            ),
        ]

        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
                self.assertEqual(tier, "weak", reason)

    def test_apple_buyer_guides_without_new_action_stay_weak(self):
        module = load_module()
        cases = [
            (
                "Apple Watch has a useful hidden feature for tracking a great healthy habit",
                "The article explains how to find Time in Daylight data in the Health app, a feature that has existed since iOS 17 and watchOS 10.",
                "9to5Mac",
            ),
            (
                "When is Apple's 2026 Back to School Offer?",
                "The article speculates on when Apple's Back to School promotion might return and explains previous offers, without Apple announcing a new promotion.",
                "MacRumors",
            ),
            (
                "When is Apple releasing new AirPods?",
                "The article is a buying guide that discusses when customers might see new AirPods hardware and whether they should wait.",
                "9to5Mac",
            ),
        ]

        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_sun_valley_apple_leadership_reports_are_relevant_and_merge(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/07/08/cook-and-ternus-attend-sun-valley-conference/",
            title="Cook and Ternus Attend Sun Valley Conference Together",
            summary=(
                "Apple CEO Tim Cook and hardware engineering chief John Ternus attended the "
                "Allen & Co. Sun Valley Conference together, alongside other technology and media executives "
                "including Amazon's Jeff Bezos, OpenAI CEO Sam Altman, Meta CEO Mark Zuckerberg, and "
                "Alphabet CEO Sundar Pichai."
            ),
            feed_time_raw="2026-07-08T09:00:00-07:00",
            context="Apple leadership Sun Valley conference Tim Cook John Ternus hardware strategy",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        articles = [
            article_for(
                module,
                candidate.title,
                candidate.summary,
                "MacRumors",
            ),
            article_for(
                module,
                "John Ternus takes his place at the Sun Valley billionaire camp",
                "Apple hardware chief John Ternus appeared at the 2026 Allen & Co. Sun Valley retreat with Tim Cook and other technology executives.",
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "AppleInsider"})

    def test_foldable_iphone_supply_shortage_is_hardware_not_os_app(self):
        module = load_module()
        title = "iPhone X一机难求再度重演！苹果折叠屏供货严重不足"
        summary = (
            "苹果首款折叠屏iPhone的上市节奏，可能正在重演2017年iPhone X的历史。"
            "分析师郭明錤在最新产业调查中指出，由于初期产能极为有限，该机型大概率无法与 iPhone 18 Pro 系列同步开售。"
            "2026年下半年的组装出货量预计仅约700万至800万部，其中第三季度出货量低至50万至100万部。"
            "郭明錤将这一状况与2017年的iPhone X类比，当年 iPhone X 因 OLED 全面屏与 Face ID 等新技术导致制造难度极高。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_same_mac_market_share_report_merges_despite_memory_price_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple the only bright spot in a declining PC market, savaged by RAM price hikes",
                (
                    "Apple gained ground in the PC market even as global shipments fell. "
                    "An estimated 6.7 million Macs shipped during the quarter, increasing Apple's shipments "
                    "10.1% year over year and lifting its PC market share from 8.5% to 9.9%."
                ),
                "AppleInsider",
                [
                    "Apple's response: AI data centers drove extraordinary memory and storage demand and unusually fast component-cost increases."
                ],
            ),
            article_for(
                module,
                "内存价格飙升冲击全球PC市场 苹果Mac成为唯一亮点",
                (
                    "全球 PC 市场在连续九个季度增长之后首次出现下滑，但苹果 Mac 逆势扩张。"
                    "2026 年第二季度全球 PC 出货量同比下降 4.9%，总计约 6820 万台；"
                    "苹果 Mac 出货量同比增长 10.1%，市场份额从 8.5% 升至 9.9%。"
                ),
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "cnBeta"})

    def test_memory_supplier_sourcing_merges_despite_price_pressure_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Begins Testing Controversial Chinese Memory Chips",
                (
                    "Apple is testing DRAM memory chips from China's state-backed ChangXin Memory Technologies. "
                    "The report says Apple previously discussed sourcing memory from CXMT and YMTC, with approval still uncertain."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "苹果传测试长鑫内存 纾困涨价危机却难治本",
                (
                    "为应对全球内存价格飙升带来的成本压力，苹果公司开始测试来自长鑫存储（CXMT）的 DRAM 内存芯片。"
                    "如果测试达标并获得美国政府放行，相关芯片未来可能进入部分 iPhone。"
                ),
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "cnBeta"})

    def test_direct_apple_wallet_car_key_partner_reports_are_strong_and_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 Code Points to Car Key Support for Lucid and Xiaomi",
                "Code in iOS 27 beta 3 suggests Apple is preparing to add Apple Wallet car key support for Lucid and Xiaomi vehicles.",
                "MacRumors",
            ),
            article_for(
                module,
                "iOS 27 hints at Apple Wallet car key support for two new automakers",
                "Apple Wallet car key references in iOS 27 beta 3 point to new Lucid and Xiaomi support for iPhone and Apple Watch.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果 iOS 27 现踪迹：iPhone 17 等用户未来可用 Apple 车钥匙解锁小米 SU7/YU7 汽车",
                "iOS 27 测试版代码出现小米和 Lucid 车企识别代码，意味着 Apple Wallet 数字车钥匙将适配这些车型。",
                "IT之家",
            ),
        ]

        for article in articles:
            self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)
            self.assertEqual(article.event_kind, "wallet_feature")
        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "9to5Mac", "IT之家"})

    def test_cross_language_platform_feature_reports_merge_for_same_action(self):
        module = load_module()
        cases = [
            [
                article_for(
                    module,
                    "Apple Loses EU Fight Over App Store Gatekeeper Label",
                    "The EU General Court rejected Apple's appeal and upheld the European Commission decision designating iOS and App Store as gatekeeper core platform services under the DMA.",
                    "MacRumors",
                ),
                article_for(
                    module,
                    "欧盟法院驳回苹果上诉，维持 App Store 和 iOS“看门人”认定",
                    "欧盟普通法院驳回苹果对 DMA 相关认定的上诉，维持将 iOS 和 App Store 认定为看门人核心平台服务。",
                    "IT之家",
                ),
                article_for(
                    module,
                    "欧盟驳回苹果上诉 确认其App Store和iOS为“守门人”平台",
                    "卢森堡普通法院驳回苹果关于 App Store 和 iOS 被认定为守门人的诉讼请求。",
                    "cnBeta",
                ),
            ],
            [
                article_for(
                    module,
                    "Apple to Drop Support for Encrypted Mac OS Extended Drives Next Year",
                    "Apple says macOS 28 will no longer support encrypted Mac OS Extended or HFS+ volumes and users should migrate to APFS.",
                    "MacRumors",
                ),
                article_for(
                    module,
                    "Encrypted Mac OS Extended drive format support dies in macOS 28",
                    "Apple confirmed encrypted HFS+ drive support ends in macOS 28, while macOS 26 will warn affected users.",
                    "AppleInsider",
                ),
                article_for(
                    module,
                    "苹果宣布 macOS 28 将不再支持“Mac OS 扩展（日志式，加密）”文件系统格式",
                    "苹果宣布 macOS 28 起不再支持 Mac OS 扩展（日志式，加密）格式，建议用户迁移到 APFS。",
                    "IT之家",
                ),
            ],
            [
                article_for(
                    module,
                    "iOS 27 adds nine new languages and accents to Apple Translate",
                    "Apple Translate in iOS 27 adds nine languages and accents, bringing total support to 30 languages.",
                    "9to5Mac",
                ),
                article_for(
                    module,
                    "新增支持粤语：苹果 iOS 27 版翻译应用总支持语言数量达 30 种",
                    "苹果 iOS 27 版翻译应用新增支持 9 种语言和方言，总支持语言数量达到 30 种。",
                    "IT之家",
                ),
            ],
        ]

        for articles in cases:
            with self.subTest(title=articles[0].title):
                events = module.cluster_articles(articles)
                self.assertEqual(len(events), 1)
                self.assertEqual({article.source for article in events[0].articles}, {article.source for article in articles})

    def test_apple_tv_emmy_and_purchased_4k_upgrade_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple TV Earns Record 87 Emmy Nominations for 2026",
                "Apple TV received a record 87 Emmy nominations for the 78th Primetime Emmy Awards, led by Widow's Bay and Pluribus.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple TV just landed a record 87 Emmy nominations",
                "Apple TV earned a record number of Emmy nominations across its original shows.",
                "9to5Mac",
            ),
            article_for(
                module,
                "TV show purchases on Apple TV are finally getting free 4K upgrades",
                "Apple is extending its free 4K upgrade policy to select purchased TV shows in the Apple TV app for the first time.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果 Apple TV 已购剧集开始免费升级 4K",
                "Apple TV Store 开始把已购内容免费升级到 4K 的政策从电影扩展到部分电视剧和节目。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        clusters = [{article.source for article in event.articles} for event in events]

        self.assertEqual(len(events), 2)
        self.assertIn({"MacRumors", "9to5Mac"}, clusters)
        self.assertIn({"AppleInsider", "IT之家"}, clusters)

    def test_home_app_ai_icloud_subscription_reports_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Says These iOS 27 Features Require $9.99/Month Subscription",
                "iOS 27 includes new Apple Intelligence features for compatible cameras in Apple's Home app, but only with an iCloud+ plan with at least 2TB of storage.",
                "MacRumors",
            ),
            article_for(
                module,
                "I'm disappointed Apple will charge for AI camera features in the Home app",
                "Apple revealed that the new AI camera features in the Home app require a 2TB iCloud+ subscription for iOS, iPadOS, and macOS 27 users.",
                "9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "9to5Mac"})

    def test_third_party_mac_touch_monitor_launch_stays_weak(self):
        module = load_module()
        title = "制造商 Alogic 推出一系列苹果 Mac 专用触控显示器产品：协作大屏、双屏便携屏"
        summary = (
            "Alogic 发布面向苹果 Mac 用户的触控显示器产品，包括 FOKUS Interactive Touchscreen、"
            "Aspekt Touch 27、Folio 和 Folio Duo，并通过自家软件为 Mac 提供触控操作。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_third_party_homepod_alternative_hands_on_stays_weak(self):
        module = load_module()
        title = "Hands-on: Denon Home 200 feels like a modern HomePod"
        summary = (
            "Denon released the Home 200 speaker with Siri and Apple ecosystem integrations, "
            "and the review describes it as a strong HomePod alternative."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_third_party_messaging_app_beta_update_is_not_developer_tool_news(self):
        module = load_module()
        title = "WhatsApp tests new animated message bubbles on iPhone"
        summary = (
            "WhatsApp is rolling out a new animation for messages to some beta testers in "
            "the latest iOS TestFlight build, with a dedicated setting in Chats > Animations."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_ithome_tag_page_is_not_relevant_news_candidate(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/tags/watchOS%2027/",
            title="watchOS 27",
            summary="苹果回应 watchOS 27 收窄兼容性，确保所有 Apple Watch 都具备最佳体验。",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))

    def test_visionos_m5_device_specific_ai_features_merge_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "visionOS 27 gives the M5 Vision Pro two unique new advantages",
                (
                    "visionOS 27 brings Siri AI voice customization and the AFM 3 Core Advanced "
                    "on-device model to the M5 Vision Pro, while M2 Vision Pro misses those two features."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "visionOS 27 今秋推送：M5 Vision Pro 头显独占 Siri 语音定制和苹果最强本地 AI 模型",
                (
                    "在 visionOS 27 系统中，苹果为 M5 Vision Pro 独占推出 Siri 语音定制和 "
                    "AFM 3 Core Advanced 本地 AI 模型。M2 款 Vision Pro 仍可获得 Siri AI、"
                    "全景照片转空间场景和重新设计的控制中心等功能。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家"})

    def test_iphone_parts_factory_contamination_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone factory right back in the spotlight as India opens new contamination probe",
                "India opened a new investigation into alleged wastewater contamination from Tata's iPhone parts plant in Tamil Nadu.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "iPhone parts factory in India faces new water contamination probe",
                "Health officials are investigating alleged water contamination from Tata Electronics' iPhone parts factory in Hosur, India.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果印度 iPhone 零件工厂被控废水污染农田：井水 TDS 超标 1 倍，作物枯萎",
                "路透社报道称印度卫生部门正调查苹果供应商 Tata 位于 Hosur 的 iPhone 零部件工厂废水排放问题。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "9to5Mac", "IT之家"})

    def test_parse_wordpress_posts_api_discovers_9to5mac_time_window_posts(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        payload = """
        [
          {
            "date_gmt": "2026-06-22T12:05:59",
            "link": "https://9to5mac.com/2026/06/22/apples-productivity-apps-have-a-small-but-useful-ai-enhancement-in-macos-27/",
            "title": {"rendered": "Apple’s productivity apps have a small but useful AI enhancement in macOS 27"},
            "excerpt": {"rendered": "<p>macOS 27 brings a small Apple Intelligence enhancement to Pages, Keynote, Numbers, and TextEdit.</p>"}
          },
          {
            "date_gmt": "2026-06-22T14:35:00",
            "link": "https://9to5mac.com/2026/06/22/ios-27-adds-brand-new-widgets-for-your-iphones-home-screen/",
            "title": {"rendered": "iOS 27 adds brand new widgets for your iPhone’s Home Screen"},
            "excerpt": {"rendered": "<p>iOS 27 beta 2 adds new Apple widgets for the iPhone Home Screen.</p>"}
          },
          {
            "date_gmt": "2026-06-29T15:01:27",
            "link": "https://9to5mac.com/2026/06/29/silo-season-3-hailed-as-best-season-yet-here-are-the-first-reviews/",
            "title": {"rendered": "Silo season 3 hailed as ‘best season yet,’ here are the first reviews"},
            "excerpt": {"rendered": "<p>Silo returns later this week for season 3, and the first reviews indicate the new season could be the show’s best yet.</p>"},
            "_embedded": {
              "wp:term": [
                [
                  {"name": "Apple TV+", "slug": "apple-tv-plus"},
                  {"name": "TV", "slug": "tv"}
                ]
              ]
            }
          }
        ]
        """

        candidates = module.parse_wordpress_posts_api(payload, source, "https://9to5mac.com/wp-json/wp/v2/posts")

        self.assertEqual([candidate.title for candidate in candidates], [
            "Apple’s productivity apps have a small but useful AI enhancement in macOS 27",
            "iOS 27 adds brand new widgets for your iPhone’s Home Screen",
            "Silo season 3 hailed as ‘best season yet,’ here are the first reviews",
        ])
        self.assertEqual(candidates[0].feed_time_raw, "2026-06-22T12:05:59+00:00")
        self.assertIn("Pages", candidates[0].summary)
        self.assertIn("apple tv", candidates[2].context.lower())
        self.assertTrue(module.is_relevant_candidate(candidates[2], source))

    def test_9to5mac_wordpress_api_preserves_links_needed_for_embedded_terms(self):
        module = load_module()
        source = source_named(module, "9to5Mac")

        self.assertTrue(source.wordpress_posts_apis)
        self.assertIn("_embed=wp:term", source.wordpress_posts_apis[0])
        self.assertIn("_links.wp:term", source.wordpress_posts_apis[0])

    def test_macos_productivity_apps_enhancement_is_direct_os_news(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/22/apples-productivity-apps-have-a-small-but-useful-ai-enhancement-in-macos-27/",
            title="Apple’s productivity apps have a small but useful AI enhancement in macOS 27",
            summary="macOS 27 brings an Apple Intelligence enhancement to Pages, Keynote, Numbers, and TextEdit.",
            feed_time_raw="2026-06-22T12:05:59+00:00",
            context="keynote macos 27 numbers pages textedit",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "os_app")
        tier, reason = module.classify_relevance_tier(candidate.title, candidate.summary, [], "9to5Mac")
        self.assertEqual(tier, "strong", reason)

    def test_ios_widgets_are_not_demoted_as_third_party_platform_story(self):
        module = load_module()
        title = "iOS 27 adds brand new widgets for your iPhone’s Home Screen"
        summary = "iOS 27 beta 2 adds new first-party widgets to the iPhone Home Screen."

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_macrumors_system_beta_feature_guide_is_relevant_when_detail_time_is_current(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/guide/ios-27-features/",
            title="Everything New in iOS 27 Beta 2",
            summary="Apple's iOS 27 beta 2 includes new Wallet, Messages, RCS, widgets, and other feature changes.",
            feed_time_raw="2026-06-22T16:02:49-07:00",
            context="featured ios 27",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(candidate.title, candidate.summary), "os_app")

    def test_os_beta_roundup_with_concrete_feature_changes_is_strong(self):
        module = load_module()
        title = "苹果 iOS 27 Beta 2 更新汇总：洞察支出、升级 AI 写作、增强 RCS 聊天"
        summary = "iOS 27 Beta 2 带来 Apple Wallet 支出洞察、Write with Siri、RCS 内联回复和新的系统功能变化。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_airport_utility_app_retirement_is_direct_os_app_news(self):
        module = load_module()
        title = "苹果收尾旧网络产品支持，iOS / iPadOS 27 预告 AirPort Utility 应用退场"
        summary = "苹果确认 AirPort Utility 将从 App Store 下架，iOS 27 和 iPadOS 27 继续移除旧 AirPort 路由器支持。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_foldable_iphone_ultra_roadmap_not_demoted_by_display_context(self):
        module = load_module()
        title = "Foldable iPhone 'Ultra' Still on Track for September Debut"
        summary = (
            "A supply-chain report says Apple's first foldable iPhone remains on track for September, "
            "with a 7.8-inch inner display, a 5.5-inch cover display, A20 chip, C2 modem, and pricing around $2,000."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(tier, "strong", reason)

    def test_broad_oled_panel_allocation_does_not_merge_with_foldable_iphone_launch(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Foldable iPhone 'Ultra' Set for Production in July Despite Hinge Issues",
                (
                    "Apple's rumored foldable iPhone Ultra is expected to begin mass production at the end of July. "
                    "The report says hinge-related issues have been worked out and Apple is still targeting a September launch."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "三星和LG包揽iPhone 18 Pro/iPad所有OLED面板订单：京东方出局",
                (
                    "据供应链消息，三星显示与LG Display已开始为苹果2026年产品线量产OLED面板。"
                    "iPhone 18 Pro、iPhone 18 Pro Max、折叠屏iPhone、新款iPad mini和MacBook Pro所需OLED面板均进入量产阶段。"
                    "LG Display独家供应Apple Watch Series 12所需OLED面板，预计出货量约为3400万块。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertTrue(any("OLED面板订单" in event.title for event in events))
        self.assertTrue(any("Foldable iPhone" in event.title for event in events))

    def test_broad_oled_panel_allocation_does_not_merge_with_foldable_panel_only_story(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果今年最重磅的新品！折叠屏iPhone面板开始量产",
                (
                    "三星显示已正式通过苹果量产认证，获准启动折叠屏iPhone专用OLED模组生产，"
                    "双方签订三年独家供货协议，今年首批交付订单约300万片。"
                ),
                source="快科技",
            ),
            article_for(
                module,
                "三星和LG包揽iPhone 18 Pro/iPad所有OLED面板订单：京东方出局",
                (
                    "三星显示与LG Display已开始为苹果2026年产品线量产OLED面板，"
                    "iPhone 18 Pro、iPhone 18 Pro Max、折叠屏iPhone、新款iPad mini、MacBook Pro和Apple Watch Series 12所需面板均进入量产或生产计划。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        self.assertTrue(any("专用OLED模组" in event.summary for event in events))
        self.assertTrue(any("2026年产品线" in event.summary for event in events))

    def test_support_document_security_guidance_stays_software_not_hardware(self):
        module = load_module()
        title = "What to do if your iPhone is stolen – more detailed advice from Apple"
        summary = (
            "Apple updated its support page with a new section warning of potential scams, "
            "advising users not to enter contact details to display on the stolen device, "
            "and covering Lost Mode, remote erase, trusted devices, and AppleCare+ with Theft and Loss."
        )

        event_kind = module.detect_event_kind(title, summary, [])

        self.assertIn(event_kind, {"security_privacy", "os_app"})
        self.assertEqual(
            module.event_category_from_metadata(title, summary, [], event_kind),
            "software_systems",
        )

    def test_title_primary_siri_ai_change_is_not_hardware_due_to_incidental_apple_tv_mention(self):
        module = load_module()
        title = "Apple tells Siri AI to clearly refuse requests to summarize URLs - 9to5Mac"
        summary = (
            "A new rule added to Siri AI's system prompt in iOS 27 beta 2 changes how it handles requests "
            "involving URLs. The article also mentions the same beta cycle included Wallet Insights, "
            "Write with Siri, and the possibility to update an Apple TV 4K remotely from the Home app."
        )

        event_kind = module.detect_event_kind(title, summary, [])

        self.assertEqual(event_kind, "os_app")
        self.assertEqual(
            module.event_category_from_metadata(title, summary, [], event_kind),
            "software_systems",
        )

    def test_first_party_calendar_update_is_not_demoted_by_wallet_or_third_party_calendar_background(self):
        module = load_module()
        title = "Here’s everything new for Apple Calendar in iOS 27"
        summary = (
            "iOS 27 is packed with new features for Apple Wallet, Messages, Notes, and other system apps, "
            "including Apple Calendar. Calendar gains natural language event creation, a redesigned event editor, "
            "free/busy status for iCloud calendars similar to Google calendars, larger widgets, and Siri improvements."
        )

        event_kind = module.detect_event_kind(title, summary, [])
        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(event_kind, "os_app")
        self.assertEqual(tier, "strong", reason)

    def test_routine_third_party_promotions_and_accessory_deals_stay_weak(self):
        module = load_module()
        examples = [
            (
                "Your Mac isn't immune to viruses, Intego One is here to help (and it's 50% off)",
                "Intego One bundles antivirus, firewall, VPN, Mac Cleaner, and identity-protection tools for Mac users. The subscription promo offers a limited-time 50% off reader discount.",
                "AppleInsider",
            ),
            (
                "The Apple Watch SE 3 is just $199 for Prime Day",
                "A retailer Prime Day deal discounts Apple Watch SE 3 to $199 for shoppers.",
                "The Verge",
            ),
            (
                "MagSafe Monday: Upgrade your MagSafe travel gear with the new ESR summer collection",
                "ESR launched a third-party MagSafe travel accessory collection for iPhone users.",
                "9to5Mac",
            ),
        ]

        for title, summary, source in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)
        self.assertEqual(
            module.detect_event_kind(examples[0][0], examples[0][1]),
            "third_party_ecosystem",
        )

    def test_event_summary_reclassifies_sparse_strong_buying_advice_as_weak(self):
        module = load_module()
        article = module.Article(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/24/apple-watch-series-11-vs-apple-watch-se/",
            title="Apple Watch Series 11 vs Apple Watch SE: Buying guide - 9to5Mac",
            summary=(
                "Compare Apple Watch SE 3 and Series 11 to see which model offers the best features, "
                "health tracking, and value. Both models are available at big discounts for Prime Day."
            ),
            key_facts=[
                "The guide compares Apple Watch SE 3 and Series 11 features, health tracking, battery life, and value.",
                "Both Apple Watch Series 11 and Apple Watch SE 3 are available at big discounts for Prime Day this week.",
            ],
            category="hardware_products",
            published_utc=datetime(2026, 6, 24, 0, 0, tzinfo=timezone.utc),
            published_raw="2026-06-24T00:00:00Z",
            published_source="test",
            confidence="detail",
            tokens=module.article_tokens("Apple Watch Series 11 vs Apple Watch SE", "buying guide value discounts"),
            event_kind="hardware_market",
            relevance_tier="strong",
            relevance_reason="stale sparse article metadata",
            regions=set(),
        )

        events = module.cluster_articles([article])

        self.assertEqual(events[0].relevance_tier, "weak")
        self.assertIn("buying advice", events[0].relevance_reason)

    def test_opinion_surveillance_and_third_party_management_stay_weak(self):
        module = load_module()
        examples = [
            (
                "Apple should release the Apple Ring",
                (
                    "The Apple Watch is king among fitness trackers, but there is a gap in the market "
                    "for Apple to release a ring-style tracker even though it probably will not."
                ),
                "AppleInsider",
            ),
            (
                "Cops will soon upgrade to license plate readers that can track your iPhone and AirPods in public",
                (
                    "A surveillance firm with deep ties to law enforcement has developed SignalTrace, "
                    "a technology to wirelessly identify Bluetooth devices like iPhones and AirPods."
                ),
                "AppleInsider",
            ),
            (
                "Mosyle launches new service to help parents manage Mac and iPad screen time for K-12 devices at home",
                (
                    "Mosyle announced Mosyle@Home, a third-party platform replacing ScreenGuide that gives parents "
                    "controls over school-issued Apple devices including Macs and iPads."
                ),
                "9to5Mac",
            ),
        ]

        for title, summary, source in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_competitor_product_with_apple_style_context_stays_weak_before_os_feature_rules(self):
        module = load_module()
        title = "告别防窥膜！小米18 Pro搭载硬件级防窥屏：全方位保护隐私"
        summary = (
            "小米18 Pro 正在测试新一代 2K 防窥显示技术，系统方面预计搭载小米澎湃OS 4，"
            "并引入类似苹果风格的光感 UI。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_apple_services_executive_award_story_is_kept_and_merged(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/22/eddy-cue-accepts-entertainment-person-of-the-year-award-at-cannes-lions/",
            title="Eddy Cue accepts Entertainment Person of the Year Award at Cannes Lions",
            summary=(
                "Today, Apple’s SVP of Services and Health, Eddy Cue, received the 2026 "
                "Entertainment Person of the Year award at the Cannes Lions International "
                "Festival of Creativity."
            ),
            feed_time_raw="2026-06-23T01:48:52+00:00",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        detailed_summary = (
            "Eddy Cue, received the 2026 Entertainment Person of the Year award at the "
            "Cannes Lions International Festival of Creativity. Eddy Cue has consistently "
            "pushed the boundaries of entertainment and storytelling, building platforms "
            "and experiences that have redefined how audiences engage with culture. Under "
            "his leadership, Apple has not only produced world-class content but has also "
            "shaped the future of entertainment through innovation, creativity and quality. "
            "Apple added that under Cue, Apple TV, which launched just over six years ago as "
            "a wholly original streaming platform, has become one of the industry’s most "
            "award-winning and culture-defining services."
        )
        self.assertEqual(module.detect_event_kind(candidate.title, detailed_summary), "service_content")

        articles = [
            article_for(
                module,
                "Steve Jobs would approve of Apple TV, says Cue",
                (
                    "Alongside dropping yet more hints about a sequel to F1: The Movie, "
                    "Eddy Cue has revealed why Apple TV did not just buy an existing library. "
                    "Cue has been named the Cannes Lions Entertainment Person of the Year "
                    "for his leadership of Apple TV and Apple Music."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "Cannes Lions 2026 Entertainment Person of the Year is Apple TV chief",
                (
                    "The Apple TV streaming service is run by Apple SVP of Services and Health, "
                    "Eddy Cue, and Cannes Lions has recognized him as the 2026 Entertainment "
                    "Person of the Year thanks to his work on the platform."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                candidate.title,
                detailed_summary,
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "AppleInsider"})

    def test_mixed_hardware_topics_split_instead_of_absorbing_competitor_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "消息称苹果 iPhone 18 Pro / Pro Max、iPad Mini 所需 OLED 面板已量产",
                "Samsung Display 与 LG Display 已启动苹果 iPhone 18 Pro / Pro Max 和新款 iPad Mini 所需 OLED 面板量产，后续还包括折叠屏 iPhone 和 OLED MacBook Pro 面板。",
                source="IT之家",
            ),
            article_for(
                module,
                "库克时代渐远？古尔曼：苹果新CEO将重申设计团队重要性",
                "苹果新 CEO 预计会重组工业设计团队，并把设计重新放回公司核心决策位置。",
                source="cnBeta",
            ),
            article_for(
                module,
                "苹果iPhone 17价格可能本月就要涨价 库克称无法避免",
                "存储芯片成本上涨使苹果 iPhone 17 系列价格可能上调，库克称涨价无法避免。",
                source="快科技",
            ),
            article_for(
                module,
                "告别防窥膜！小米18 Pro搭载硬件级防窥屏：全方位保护隐私",
                "小米18 Pro 测试防窥显示技术，并引入类似苹果风格的光感 UI。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertGreaterEqual(len(events), 3)
        oled_events = [event for event in events if "OLED 面板" in event.summary]
        self.assertEqual(len(oled_events), 1)
        self.assertNotIn("小米18", oled_events[0].summary)
        self.assertTrue(any(event.relevance_tier == "weak" and "小米18" in event.summary for event in events))

    def test_product_price_hike_cluster_splits_chip_roadmap_and_keeps_response_facts(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                (
                    "Apple dramatically increased device prices across multiple product lines after taking "
                    "the online store offline. MacBook Neo is now $699, iPad starts at $449, Apple TV is "
                    "$199, and HomePod mini is $129."
                ),
                source="MacRumors",
                facts=[
                    "HomePod mini: $129, up from $99 (+$30)",
                    "Apple TV: $199, up from $129 (+$70)",
                    "iPad: $449, up from $349 (+$100)",
                    "MacBook Neo: $699, up from $599 (+$100)",
                    "MacBook Air: $1,299, up from $1,099 (+$200)",
                    "MacBook Pro: $1,999, up from $1,699 (+$300)",
                    "iMac: $1,499, up from $1,299 (+$200)",
                    "Mac mini M4 Pro: $1,599, up from $1,399 (+$200)",
                    "Vision Pro: $3,699, up from $3,499 (+$200)",
                    "Mac Studio M4 Max: $2,499, up from $1,999 (+$500)",
                ],
            ),
            article_for(
                module,
                "Apple Explains Why It Raised Prices on 14 Products Today",
                (
                    "Apple said memory and storage component costs have risen unprecedentedly. "
                    "The company said it has shielded customers so far, has reached a point where "
                    "it needs to begin raising prices on products including today's iPad and Mac "
                    "increases, knows this is not welcome news, and is working tirelessly to find solutions."
                ),
                source="MacRumors",
                facts=[
                    "Apple said memory and storage component costs have increased at unprecedented levels.",
                    "Apple said it has shielded customers from those increases so far.",
                    "Apple said it has reached a point where it needs to begin raising prices on a number of products, including today's increases for iPad and Mac.",
                    "Apple said it knows this is not welcome news and is working tirelessly to find solutions.",
                ],
            ),
            article_for(
                module,
                "2027 Macs to Get AI-Focused M7 Chips as Apple Skips High-End M6",
                (
                    "Apple's updated chip launch timeline points to M7 Pro and M7 Max chips in late 2027, "
                    "with the high-end MacBook Pro skipping M6 Pro and M6 Max. The article notes this news "
                    "arrived just after Apple raised prices across Macs and iPads."
                ),
                source="MacRumors",
                facts=[
                    "Apple is expected to skip M6 Pro and M6 Max chips for high-end Macs.",
                    "M7 Pro and M7 Max chips are slated for late 2027.",
                ],
            ),
            article_for(
                module,
                "M5 Ultra Mac Studio Could Launch in 2026 With Up to 768GB of RAM",
                (
                    "Apple may still update the Mac Studio with an M5 Ultra chip in 2026 and up to "
                    "768GB of RAM. A footer link points readers to Apple's stock reaction after price increases."
                ),
                source="MacRumors",
                facts=[
                    "The M5 Ultra Mac Studio could launch in 2026.",
                    "The high-end configuration could support up to 768GB of RAM.",
                ],
            ),
        ]

        events = module.split_mixed_topic_events(module.cluster_articles(articles))

        price_events = [event for event in events if "Increased Prices" in event.title or "Raised Prices" in event.title]
        self.assertEqual(len(price_events), 1)
        price_event = price_events[0]
        self.assertEqual(price_event.category, "hardware_products")
        self.assertEqual(price_event.event_kind, "hardware_market")
        self.assertIn("not welcome news", " ".join([price_event.summary, *price_event.key_facts]))
        self.assertNotIn("M7 Pro", price_event.summary)
        self.assertNotIn("M5 Ultra Mac Studio", price_event.summary)
        self.assertTrue(any("M7" in event.summary for event in events if event is not price_event))
        self.assertTrue(any("M5 Ultra" in event.summary for event in events if event is not price_event))

    def test_current_weak_apple_adjacent_noise_stays_deferred(self):
        module = load_module()
        examples = [
            (
                "国产Pro Max扎堆亮相 这次能叫板苹果吗",
                "多家国产手机厂商推出 Pro Max 机型，文章讨论这些安卓旗舰能否叫板苹果 iPhone。",
                "快科技",
            ),
            (
                "曾称追觅要赶超苹果等！俞浩以后不能随便发狂言了：社交账户被公司接管",
                "追觅公司接管高管社交账号，背景提到此前曾称要赶超苹果、特斯拉和戴森。",
                "快科技",
            ),
            (
                "Notion shutting down its AI-powered email client, including Mac and iOS apps",
                "Notion is shutting down Notion Mail across web, Mac, and iOS apps after 17 months.",
                "9to5Mac",
            ),
            (
                "Soulver 4 brings 50+ improvements, new workflows, and an agent-friendly CLI",
                "Soulver 4 adds more than 50 improvements to the third-party calculator app on Mac.",
                "9to5Mac",
            ),
        ]

        for title, summary, source in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_apple_chip_roadmap_and_wearable_rumors_stay_strong(self):
        module = load_module()
        examples = [
            (
                "2027 Macs to Get AI-Focused M7 Chips as Apple Skips High-End M6",
                (
                    "Apple is changing its Apple silicon launch timeline to speed up the debut of "
                    "M7 Pro and M7 Max chips for AI workloads, while skipping M6 Pro and M6 Max."
                ),
                "hardware_market",
            ),
            (
                "消息称苹果正开发 iRing 智能戒指，上市后将和三星 Galaxy Ring 等竞争",
                (
                    "消息源称苹果公司正在开发 Ring 智能戒指，上市后预估会和 Oura、三星 Galaxy Ring "
                    "等产品竞争，但开发并不等于最终量产。"
                ),
                "hardware_market",
            ),
        ]

        for title, summary, expected_kind in examples:
            with self.subTest(title=title):
                self.assertEqual(module.detect_event_kind(title, summary), expected_kind)
                tier, reason = module.classify_relevance_tier(title, summary, [], "")
                self.assertEqual(tier, "strong", reason)

    def test_non_apple_pc_vendor_responses_to_macbook_stay_weak(self):
        module = load_module()
        title = "换名不换芯！PC厂商集体套娃卖旧货"
        summary = (
            "面对苹果推出 MacBook Neo 抢占入门市场，各供应商将旧芯片重新包装后推出以降低 OEM "
            "成本压力。AMD 重新上市锐龙 100 系列处理器，并直接对比 MacBook Neo。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_apple_price_explanation_is_not_downgraded_by_component_context(self):
        module = load_module()
        title = "Apple Explains Why It Raised Prices on 14 Products Today"
        summary = (
            "Apple said the consumer electronics industry faces an unprecedented memory and storage "
            "component cost challenge, that it has shielded customers so far, and that it now needs "
            "to begin raising prices on iPad and Mac products. Other companies including Microsoft "
            "and Samsung have raised prices in response to the same shortage."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "strong", reason)

    def test_product_data_leak_does_not_merge_with_mac_chip_roadmap(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "2027 Macs to Get AI-Focused M7 Chips as Apple Skips High-End M6",
                (
                    "Apple is changing its Apple silicon launch timeline to speed up the debut of M7 Pro "
                    "and M7 Max chips while skipping M6 Pro and M6 Max chips."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro board schematics, A20 Pro data, C2 modem files stolen from Tata",
                (
                    "Hackers stole iPhone 18 Pro logic board schematics, A20 Pro data sheets, and C2 "
                    "modem files from Apple supplier Tata and listed the files on the dark web. A related "
                    "article link mentions that Apple will skip M6 Pro and M6 Max in favor of M7 chips."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "苹果代工厂塔塔电子被黑，部分 iPhone 18 Pro 与 A20 Pro 资料确认泄露",
                "苹果代工厂塔塔电子遭黑客入侵，部分 iPhone 18 Pro、A20 Pro 和 C2 调制解调器机密文件流入暗网。",
                source="IT之家",
            ),
        ]

        events = module.split_mixed_topic_events(module.cluster_articles(articles))

        self.assertEqual(len(events), 2)
        leak_events = [event for event in events if "Tata" in event.summary or "塔塔" in event.summary]
        self.assertEqual(len(leak_events), 1)
        self.assertEqual(leak_events[0].category, "hardware_products")
        self.assertNotIn("M7 Pro", leak_events[0].summary)

    def test_product_data_leak_does_not_merge_with_iphone_product_roadmap_leak(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Leak claims iPhone Ultra 2 is already greenlit, but maybe not Air 3",
                (
                    "A leaker claims Apple has already greenlit iPhone Ultra 2 and that tooling for "
                    "iPhone Air 3 has not yet begun."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "iPhone 18 Pro board schematics, A20 Pro data, C2 modem files stolen from Tata",
                (
                    "AppleInsider can exclusively confirm that logic board designs for iPhone 18 Pro, "
                    "A20 Pro data sheets, and C2 modem files were stolen from Tata's India facility."
                ),
                source="AppleInsider",
            ),
        ]
        self.assertNotIn(
            "apple-product-data-leak",
            module.primary_topic_facets(
                "Leak claims iPhone Ultra 2 is already greenlit, but maybe not Air 3",
                (
                    "A leaker claims Apple has already greenlit iPhone Ultra 2 and that tooling for "
                    "iPhone Air 3 has not yet begun."
                ),
            ),
        )

        events = module.split_mixed_topic_events(module.cluster_articles(articles))

        self.assertEqual(len(events), 2)
        roadmap_events = [event for event in events if "greenlit" in event.summary]
        self.assertEqual(len(roadmap_events), 1)
        self.assertNotIn("A20 Pro data", roadmap_events[0].summary)

    def test_foldable_iphone_successor_roadmap_does_not_merge_with_first_gen_production(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone Ultra 2 Gets Green Light for Development, Says Leaker",
                (
                    "Apple's second-generation foldable iPhone has officially been given the go-ahead "
                    "for development. The first foldable iPhone will use a foldable 7.8-inch OLED panel "
                    "supplied by Samsung, based on reports. Digital Chat Station also said that the "
                    "iPhone Air 3 has not entered the prototype stage yet."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone Ultra 2 already given go-ahead, iPhone Air 3 not, says leaker",
                (
                    "The iPhone Ultra2 second generation wide folding project has been confirmed, "
                    "with a high probability of reusing this year's screen. The same post says Apple "
                    "has not yet decided whether to proceed with an iPhone Air 3."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "曝苹果折叠屏 iPhone 七月底量产，铰链问题已大部分解决",
                (
                    "苹果首款折叠屏 iPhone 计划于 7 月底前后开始量产，并仍按原计划推进 9 月发布。"
                    "首批产品将由富士康负责生产，铰链由新日兴和安费诺供应。"
                ),
                source="爱范儿",
            ),
        ]

        self.assertNotIn(
            "foldable-iphone-supply-chain",
            module.primary_topic_facets(
                "iPhone Ultra 2 Gets Green Light for Development, Says Leaker",
                (
                    "Apple's second-generation foldable iPhone has officially been given the go-ahead "
                    "for development. The first foldable iPhone will use a foldable 7.8-inch OLED panel "
                    "supplied by Samsung, based on reports."
                ),
            ),
        )
        self.assertNotIn(
            "apple-display-panel-spec-rumor",
            module.primary_topic_facets(
                "iPhone Ultra 2 Gets Green Light for Development, Says Leaker",
                (
                    "Apple's second-generation foldable iPhone has officially been given the go-ahead "
                    "for development. The first foldable iPhone will use a foldable 7.8-inch OLED panel "
                    "supplied by Samsung, based on reports."
                ),
            ),
        )

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2)
        successor_events = [event for event in events if "Ultra 2" in event.title or "Ultra2" in event.summary]
        self.assertEqual(len(successor_events), 1)
        self.assertEqual({article.source for article in successor_events[0].articles}, {"MacRumors", "9to5Mac"})
        self.assertNotIn("七月底前后开始量产", successor_events[0].summary)

    def test_product_data_leak_merges_cross_language_compact_chinese_title(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro logic board schematics, A20 Pro data sheets, C2 modem files stolen from Tata",
                (
                    "Hackers stole iPhone 18 Pro logic board schematics, A20 Pro data sheets, and C2 "
                    "modem files from Apple supplier Tata and listed the files on the dark web."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "塔塔遭黑客攻击 iPhone 18 Pro主板图纸与A20 Pro芯片资料遭泄露",
                "塔塔电子遭黑客攻击，iPhone 18 Pro 主板图纸、A20 Pro 芯片资料以及 C2 调制解调器文件遭泄露。",
                source="cnBeta",
            ),
        ]

        events = module.split_mixed_topic_events(module.cluster_articles(articles))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")

    def test_product_data_leak_with_apple_response_remains_hardware_event(self):
        module = load_module()
        title = "Photos of iPhone 18 Pro drop tests and other sensitive info hits the dark web"
        summary = (
            "Reuters says Apple is particularly concerned after supplier Tata Electronics suffered "
            "a data breach. World Leaks posted more than 200,000 files on the dark web, including "
            "iPhone 18 Pro drop test photos, component supplier lists, logic-board chip details, "
            "camera parts, and battery information."
        )
        chinese_title = "苹果供应商塔塔泄露 iPhone 18 Pro 跌落测试照片和零部件清单"
        chinese_summary = (
            "塔塔电子遭黑客攻击后，暗网上出现 iPhone 18 Pro 跌落测试照片、零部件供应商清单、"
            "主板芯片、电池和摄像头资料，苹果对此表示担忧。"
        )
        facts = [
            "报道指出，这些泄露的敏感信息涵盖 iPhone 18 Pro 零部件供应商名单，"
            "由于供应商协议受到苹果严密保护，此次事件可能激怒苹果并对塔塔电子与苹果之间的合作伙伴关系造成实质性冲击。",
            "泄露文件包含主板芯片配置、电池组件、摄像头部件和跌落测试照片。",
            "The ransomware organization World Leaks posted the files, and a related video appears to show a new back design change with the Apple logo.",
        ]

        self.assertEqual(module.detect_event_kind(title, summary, facts), "hardware_market")
        articles = [
            article_for(module, title, summary, facts=facts, source="9to5Mac"),
            article_for(module, chinese_title, chinese_summary, facts=facts, source="IT之家"),
        ]
        events = module.split_mixed_topic_events(module.cluster_articles(articles))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual(events[0].category, "hardware_products")

    def test_product_data_leak_summary_events_can_remerge_after_intermediate_split(self):
        module = load_module()
        left = module.cluster_articles(
            [
                article_for(
                    module,
                    "iPhone 18 Pro logic board schematics, A20 Pro data sheets, C2 modem files stolen from Tata",
                    (
                        "Hackers stole iPhone 18 Pro logic board schematics, A20 Pro data sheets, and C2 "
                        "modem files from Apple supplier Tata and listed the files on the dark web."
                    ),
                    source="AppleInsider",
                )
            ]
        )[0]
        right = module.cluster_articles(
            [
                article_for(
                    module,
                    "塔塔遭黑客攻击 iPhone 18 Pro主板图纸与A20 Pro芯片资料遭泄露",
                    (
                        "塔塔电子遭黑客攻击，iPhone 18 Pro 主板图纸、A20 Pro 芯片资料以及 C2 调制解调器文件遭泄露。"
                        "相关新闻还提到 M6 MacBook Pro、折叠 iPhone 和苹果设计团队调整。"
                    ),
                    source="cnBeta",
                )
            ]
        )[0]

        self.assertTrue(module.events_should_merge(left, right))

    def test_product_data_leak_summary_merge_keys_use_specific_file_leak_anchors(self):
        module = load_module()
        event = module.cluster_articles(
            [
                article_for(
                    module,
                    "塔塔遭黑客攻击 iPhone 18 Pro主板图纸与A20 Pro芯片资料遭泄露",
                    (
                        "塔塔电子遭黑客攻击，iPhone 18 Pro 主板图纸、A20 Pro 芯片资料以及 "
                        "C2 调制解调器文件遭泄露。相关新闻还提到 M6 MacBook Pro 和折叠 iPhone。"
                    ),
                    source="cnBeta",
                )
            ]
        )[0]

        keys = module.event_summary_merge_keys(event)

        self.assertIn(("apple-product-data-leak-specs", ()), keys)
        self.assertIn(("iphone-chip-packaging", ()), keys)
        self.assertNotIn(("apple-product-data-leak", ()), keys)

    def test_product_data_leak_event_not_split_by_extra_related_hardware_facets(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro logic board schematics, A20 Pro data sheets, C2 modem files stolen from Tata",
                (
                    "Hackers stole iPhone 18 Pro logic board schematics, A20 Pro data sheets, and C2 "
                    "modem files from Apple supplier Tata and listed the files on the dark web."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "塔塔遭黑客攻击 iPhone 18 Pro主板图纸与A20 Pro芯片资料遭泄露",
                (
                    "塔塔电子遭黑客攻击，iPhone 18 Pro 主板图纸、A20 Pro 芯片资料以及 C2 调制解调器文件遭泄露。"
                    "页面尾部还列出 M6 MacBook Pro 和折叠 iPhone 等相关文章。"
                ),
                source="cnBeta",
            ),
        ]
        event = module.cluster_articles(articles)[0]
        event.merge_warnings = ["mixed primary topic facets"]

        split_events = module.split_mixed_topic_event(event)

        self.assertEqual(len(split_events), 1)

    def test_price_event_key_facts_keep_response_from_summary_before_price_list(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                "Apple dramatically increased device prices across multiple product lines.",
                source="MacRumors",
                facts=[
                    "HomePod mini: $129, up from $99 (+$30)",
                    "Apple TV: $199, up from $129 (+$70)",
                    "iPad mini: $599, up from $499 (+$100)",
                    "iPad Air: $749, up from $599 (+$150)",
                    "iPad Pro: $1,199, up from $999 (+$200)",
                    "MacBook Neo: $699, up from $599 (+$100)",
                    "MacBook Air: $1,299, up from $1,099 (+$200)",
                    "MacBook Pro: $1,999, up from $1,699 (+$300)",
                    "iMac: $1,499, up from $1,299 (+$200)",
                    "Mac Studio M4 Max: $2,499, up from $1,999 (+$500)",
                ],
            ),
            article_for(
                module,
                "Apple Explains Why It Raised Prices on 14 Products Today",
                (
                    "Apple said the consumer electronics industry is facing an unprecedented challenge "
                    "because AI data centers have created extraordinary demand for memory and storage. "
                    "Apple said it has shielded customers so far, but now needs to begin raising prices "
                    "on iPad and Mac, knows this is not welcome news, and is working tirelessly to find solutions."
                ),
                source="MacRumors",
                facts=[],
            ),
        ]

        facts = module.collect_event_key_facts(articles)

        combined = " ".join(facts[:4])
        self.assertIn("not welcome news", combined)
        self.assertIn("working tirelessly", combined)

    def test_price_event_key_facts_keep_customer_response_when_many_cost_reasons_compete(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                (
                    "Apple dramatically increased device prices across multiple product lines. "
                    "Last week, Apple announced that price increases were inevitable, with CEO Tim Cook "
                    "saying the move was unavoidable. The price increases "
                    "are due to the ongoing memory chip shortage. Companies such as OpenAI and Meta have "
                    "been purchasing large amounts of memory chips for AI servers. Apple said component "
                    "costs have increased unusually quickly."
                ),
                source="MacRumors",
                facts=[
                    "HomePod mini: $129, up from $99 (+$30)",
                    "Apple TV: $199, up from $129 (+$70)",
                    "iPad mini: $599, up from $499 (+$100)",
                    "MacBook Neo: $699, up from $599 (+$100)",
                ],
            ),
            article_for(
                module,
                "Apple Explains Why It Raised Prices on 14 Products Today",
                (
                    "Last week, Apple announced that it was preparing to raise prices across its product lineup, "
                    "with CEO Tim Cook confirming that the move was inevitable. The price increases are due to "
                    "the ongoing memory chip shortage, which has led to skyrocketing prices for RAM and SSD storage. "
                    "Companies such as OpenAI and Meta have been purchasing large amounts of memory chips for AI servers. "
                    "\"We have never seen a component price increase this much, this quickly,\" said Apple. "
                    "Apple said it knows this is not welcome news and is working tirelessly to find solutions."
                ),
                source="MacRumors",
                facts=[],
            ),
        ]

        facts = module.collect_event_key_facts(articles)

        combined = " ".join(facts[:6])
        self.assertIn("not welcome news", combined)
        self.assertIn("working tirelessly", combined)

    def test_price_event_key_facts_keep_distinct_substory_details(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                "Apple dramatically increased device prices across multiple product lines.",
                source="MacRumors",
                facts=[
                    "HomePod mini: $129, up from $99 (+$30)",
                    "Apple TV: $199, up from $129 (+$70)",
                    "iPad mini: $599, up from $499 (+$100)",
                    "iPad Air: $749, up from $599 (+$150)",
                    "iPad Pro: $1,199, up from $999 (+$200)",
                    "MacBook Neo: $699, up from $599 (+$100)",
                    "MacBook Air: $1,299, up from $1,099 (+$200)",
                    "MacBook Pro: $1,999, up from $1,699 (+$300)",
                    "iMac: $1,499, up from $1,299 (+$200)",
                    "Mac Studio M4 Max: $2,499, up from $1,999 (+$500)",
                ],
            ),
            article_for(
                module,
                "Apple Explains Why It Raised Prices on 14 Products Today",
                (
                    "Apple said the consumer electronics industry is facing an unprecedented challenge "
                    "because AI data centers have created extraordinary demand for memory and storage. "
                    "Apple said it has shielded customers so far, but now needs to begin raising prices "
                    "on iPad and Mac, knows this is not welcome news, and is working tirelessly to find solutions."
                ),
                source="MacRumors",
                facts=[],
            ),
            article_for(
                module,
                "苹果提高 Mac、iPad、Vision Pro、HomePod 等产品价格，以应对内存短缺",
                "苹果公司宣布上调 Mac、iPad、Vision Pro、HomePod 等产品价格。",
                source="IT之家",
                facts=[
                    "MacBook Neo 的起售价从 4599 元上调至 5499 元，涨价 900 元",
                    "MacBook Air 的起售价从 8499 元上调至 9999 元，涨价 1500 元",
                    "MacBook Pro 的起售价从 13499 元上调至 15999 元，涨价 2500 元",
                    "Mac Studio 的起售价从 16499 元上调至 19999 元，涨价 3500 元",
                    "Vision Pro 的起售价从 29999 元上调至 31999 元，涨价 2000 元",
                    "HomePod mini 的起售价从 749 元上调至 999 元，涨价 250 元",
                ],
            ),
            article_for(
                module,
                "苹果 iPad 等硬件涨价落地：股价单日下跌 6.15%，分析师整体仍偏乐观",
                "苹果宣布上调 Mac、iPad、Vision Pro、HomePod 硬件产品价格后，股价在周四收盘下跌约 6.15%。",
                source="IT之家",
                facts=[
                    "苹果宣布上调 Mac、iPad、Vision Pro、HomePod 硬件产品价格后，股价在周四收盘下跌约 6.15%。",
                    "Evercore ISI 分析师 Amit Daryanani 重申“跑赢大盘”评级，并维持 365 美元目标价。",
                    "Wedbush 分析师 Dan Ives 同样维持“跑赢大盘”评级，目标价保持 400 美元不变。",
                ],
            ),
            article_for(
                module,
                "Apple hints at more price increases coming later",
                "Apple said it has reached a point where it needs to begin raising prices on a number of products.",
                source="9to5Mac",
                facts=[
                    "Apple's wording suggests the Mac and iPad changes may be the start of a broader set of price increases.",
                    "iPhone, Apple Watch, and AirPods were not included in this round of price increases.",
                ],
            ),
        ]

        facts = module.collect_event_key_facts(articles)
        combined = " ".join(facts)

        self.assertGreater(len(facts), module.MAX_KEY_FACTS)
        self.assertIn("not welcome news", combined)
        self.assertIn("HomePod mini: $129", combined)
        self.assertIn("MacBook Pro 的起售价从 13499 元上调至 15999 元", combined)
        self.assertIn("股价在周四收盘下跌约 6.15%", combined)
        self.assertIn("365 美元目标价", combined)
        self.assertIn("broader set of price increases", combined)
        self.assertIn("iPhone, Apple Watch, and AirPods were not included", combined)

    def test_price_event_brief_queue_marks_official_response_as_must_include(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Increased Prices on MacBooks, iPads, and More",
                "Apple dramatically increased device prices across multiple product lines.",
                source="MacRumors",
                facts=[
                    "HomePod mini: $129, up from $99 (+$30)",
                    "Apple TV: $199, up from $129 (+$70)",
                    "iPad mini: $599, up from $499 (+$100)",
                    "MacBook Neo: $699, up from $599 (+$100)",
                ],
            ),
            article_for(
                module,
                "Apple Explains Why It Raised Prices on 14 Products Today",
                (
                    "Apple said the consumer electronics industry is facing an unprecedented challenge "
                    "because AI data centers have created extraordinary demand for memory and storage. "
                    "Apple said it has shielded customers so far, but now needs to begin raising prices "
                    "on iPad and Mac, knows this is not welcome news, and is working tirelessly to find solutions."
                ),
                source="MacRumors",
                facts=[],
            ),
        ]
        event = module.cluster_articles(articles)[0]
        event_dict = module.event_to_dict(event, timezone.utc)

        self.assertEqual(len(event_dict["must_include_facts"]), 1)
        self.assertLess(len(event_dict["must_include_facts"][0]), 450)
        combined = " ".join(event_dict["must_include_facts"])
        self.assertIn("AI data centers", combined)
        self.assertIn("memory and storage", combined)
        self.assertIn("shielded customers", combined)
        self.assertIn("iPad and Mac", combined)
        self.assertIn("not welcome news", combined)
        self.assertIn("working tirelessly", combined)

        queue_item = module.build_final_brief_queue([event_dict])[0]
        queue_combined = " ".join(queue_item["must_include_facts"])
        self.assertIn("not welcome news", queue_combined)
        self.assertIn("working tirelessly", queue_combined)

    def test_price_article_extracts_statement_blockquote_as_key_fact(self):
        module = load_module()
        html = """
        <article>
          <h1>Apple Explains Why It Raised Prices on 14 Products Today</h1>
          <p>Apple today raised prices on many of its products, including all Macs and iPads.</p>
          <p>Apple's full statement:</p>
          <blockquote><p>The consumer electronics industry is facing an unprecedented challenge.
          The rapid expansion of AI data centers has created an extraordinary surge in demand for
          memory and storage. We have never seen a component price increase this much, this quickly.
          We have shielded our customers from these increases so far, but we have now reached a
          point where we need to begin raising prices on a number of products, including today's
          increases for iPad and Mac. We know this is not welcome news, and we are working
          tirelessly to find solutions.</p></blockquote>
        </article>
        """

        facts = module.extract_key_facts(html, "Apple Explains Why It Raised Prices on 14 Products Today", "MacRumors")

        combined = " ".join(facts)
        self.assertIn("not welcome news", combined)
        self.assertIn("working tirelessly", combined)

    def test_structured_price_list_keeps_later_product_rows(self):
        module = load_module()
        html = """
        <article>
          <h1>苹果提高 Mac、iPad、Vision Pro、HomePod 等产品价格</h1>
          <p>苹果公司宣布上调 Mac、iPad 等产品价格，以应对内存芯片及存储器成本压力。</p>
          <p>苹果在声明中表示，人工智能数据中心导致内存和存储需求激增，公司不得不提高部分产品价格。</p>
          <ul>
            <li>MacBook Neo 的起售价从 4599 元上调至 5499 元，涨价 900 元</li>
            <li>MacBook Air 的起售价从 8499 元上调至 9999 元，涨价 1500 元</li>
            <li>MacBook Pro 的起售价从 13499 元上调至 15999 元，涨价 2500 元</li>
            <li>iMac 的起售价从 10999 元上调至 12499 元，涨价 1500 元</li>
            <li>Mac mini 的起售价从 4499 元上调至 5999 元，涨价 1500 元</li>
            <li>Mac Studio 的起售价从 16499 元上调至 19999 元，涨价 3500 元</li>
            <li>iPad Pro 的起售价从 8999 元上调至 10799 元，涨价 1800 元</li>
            <li>iPad Air 的起售价从 4799 元上调至 5999 元，涨价 1200 元</li>
            <li>iPad mini 的起售价从 3999 元上调至 4799 元，涨价 800 元</li>
            <li>iPad（A16）的起售价从 2999 元上调至 3799 元，涨价 800 元</li>
            <li>Vision Pro 的起售价从 29999 元上调至 31999 元，涨价 2000 元</li>
            <li>HomePod 的起售价从 2299 元上调至 2699 元，涨价 400 元</li>
            <li>HomePod mini 的起售价从 749 元上调至 999 元，涨价 250 元</li>
            <li>Apple TV 的起售价从 129 美元上调至 199 美元，涨价 70 美元</li>
          </ul>
        </article>
        """

        facts = module.extract_key_facts(html, "苹果提高 Mac、iPad、Vision Pro、HomePod 等产品价格", "IT之家")
        combined = " ".join(facts)

        self.assertIn("MacBook Pro 的起售价从 13499 元上调至 15999 元", combined)
        self.assertIn("Vision Pro 的起售价从 29999 元上调至 31999 元", combined)
        self.assertIn("Apple TV 的起售价从 129 美元上调至 199 美元", combined)

    def test_third_party_platform_update_directly_improving_airpods_beats_is_ecosystem_relevant(self):
        module = load_module()
        title = "微软修复Windows 11蓝牙故障：AirPods和Beats连接更稳定"
        summary = (
            "微软近日对Windows 11的蓝牙功能进行系统级优化，修复长期存在的蓝牙兼容性与稳定性问题，"
            "其中AirPods和Beats系列耳机的连接体验得到显著提升，包括减少断连、配对失败、音频不同步和麦克风失效。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "ecosystem_interop")
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "ecosystem", reason)

    def test_apple_online_store_status_is_retail_not_software(self):
        module = load_module()
        title = "Apple's Online Store Is Down"
        summary = (
            "Apple's online store has gone down with a We'll be right back message. "
            "The change could be due to the Back to School program, price increases, or new product pages."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "retail_store")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_multiple_apple_retail_store_moves_are_hardware_news(self):
        module = load_module()
        title = "Two Apple Stores in U.S. Are Moving Soon"
        summary = (
            "Apple Queens Center and Apple Renaissance at Colony Park will move to new "
            "physical retail locations later this month."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "retail_store")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_single_article_multi_region_context_does_not_create_merge_warning(self):
        module = load_module()
        article = article_for(
            module,
            "Apple's Online Store Is Down",
            (
                "Apple's online store is down while the annual Back to School promotion for the "
                "United States and Canada is expected to launch soon."
            ),
            source="MacRumors",
        )
        article.event_kind = "retail_store"
        article.regions = {"united-states", "canada"}

        warnings = module.event_merge_warnings([article])

        self.assertNotIn("multiple region-specific markers", warnings)

    def test_apple_relief_donation_candidate_is_relevant(self):
        module = load_module()
        source = next(item for item in module.build_sources(datetime.now(timezone.utc)) if item.name == "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/06/26/apple-donating-to-venezuela-earthquake-relief/",
            title="Apple Donating to Relief Efforts in Venezuela Following Devastating Earthquakes",
            summary=(
                "In a social media post today, Apple CEO Tim Cook said Apple will be donating to "
                "relief efforts on the ground in Venezuela after the country was hit by two catastrophic earthquakes."
            ),
            feed_time_raw="Fri, 26 Jun 2026 07:10:00 PDT",
            context="apple rumors mac ios iphone ipad",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))

    def test_apple_books_platform_trust_story_is_not_blocked_by_amazon_background(self):
        module = load_module()
        title = "AI-generated knockoffs of Joanna Stern's book keep appearing on Apple Books - 9to5Mac"
        summary = (
            "Joanna Stern called out Apple over AI-generated knockoffs of her book that continue "
            "to appear on Apple Books. A background paragraph says Kara Swisher previously raised "
            "a similar Amazon issue, but the current story is about Apple Books platform enforcement."
        )
        source = next(item for item in module.build_sources(datetime.now(timezone.utc)) if item.name == "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/06/26/ai-generated-knockoffs-of-joanna-sterns-book-keep-appearing-on-apple-books/",
            title=title,
            summary=summary,
        )

        self.assertFalse(module.should_hard_exclude_candidate(f"{title} {summary}"))
        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(module.detect_event_kind(title, summary), "app_store_trust")
        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
        self.assertEqual(tier, "strong", reason)

    def test_apple_hardware_roadmap_is_not_third_party_accessory_compatibility(self):
        module = load_module()
        title = "MacBook Ultra and new MacBook Pro both launching this fall, per rumors - 9to5Mac"
        summary = (
            "Apple's high-end MacBook plans are coming into focus after recent Bloomberg reports, "
            "including MacBook Ultra and a new M6 MacBook Pro expected to launch this fall. "
            "The touchscreen MacBook with OLED display will use M5 Pro and M5 Max chips."
        )

        self.assertFalse(module.is_third_party_accessory_platform_compatibility_story(title, summary))
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
        self.assertEqual(tier, "strong", reason)

    def test_macbook_ultra_commentary_analysis_stays_weak_without_new_reporting(self):
        module = load_module()
        title = "MacBook Ultra could be very good news for MacBook Pro users - 9to5Mac"
        summary = (
            "Here’s why the rumored new MacBook Ultra model could be good news for MacBook Pro users "
            "in light of a previous redesign misstep. The author argues Apple could avoid upsetting "
            "Pro users by splitting the lineup, while referencing earlier Bloomberg rumors."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_apple_smart_ring_rumor_is_hardware_roadmap_not_weak_health_context(self):
        module = load_module()
        title = "Apple 'iRing' Rumor Re-Emerges Amid Oura Ring Popularity"
        summary = (
            "Apple is developing a smart ring that could potentially rival products like the Oura Ring "
            "and Samsung Galaxy Ring, according to a leaker. The wearable could track biometrics and "
            "expand Apple's hardware lineup beyond Apple Watch."
        )

        self.assertTrue(module.is_direct_apple_hardware_roadmap_story(summary, title))
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "strong", reason)

    def test_9to5_prime_day_apple_gear_block_is_removed_before_fact_extraction(self):
        module = load_module()
        html = """
        <div class="post-content">
          <p>Apple's upcoming touchscreen MacBook lineup will be powered by existing M5 Pro and M5 Max chips.</p>
          <p>These new MacBooks will also have OLED screens and come in 14-inch and 16-inch sizes.</p>
          <h2>Prime Day savings on Apple gear</h2>
          <ul>
            <li>13-inch MacBook Air: $996 on Amazon (now $1,299 from Apple)</li>
            <li>M5 MacBook Pro: $1,549 on Amazon (now $1,999 from Apple)</li>
          </ul>
        </div>
        """

        scoped = module.article_scope(html)
        facts = module.extract_key_facts(scoped, "Apple's touchscreen MacBook to use M5 Pro and M5 Max chips", "9to5Mac")
        combined = " ".join(facts)

        self.assertIn("M5 Pro and M5 Max", combined)
        self.assertNotIn("Amazon", combined)
        self.assertNotIn("$1,299", combined)

    def test_mixed_hardware_cluster_splits_price_macbook_and_company_org_events(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro and Pro Max May See $200 Price Increase",
                "Apple's iPhone 18 Pro and Pro Max may increase by $200 because memory and storage costs are rising.",
                source="MacRumors",
                facts=["iPhone 18 Pro could rise from $1,099 to $1,299, while Pro Max could rise from $1,199 to $1,399."],
            ),
            article_for(
                module,
                "Apple's touchscreen MacBook to use M5 Pro and M5 Max chips, not M6",
                "Apple's upcoming touchscreen MacBook will use M5 Pro and M5 Max chips, add OLED, and arrive in 14-inch and 16-inch sizes.",
                source="9to5Mac",
                facts=["The model may be branded MacBook Ultra and be positioned at the top of Apple's lineup."],
            ),
            article_for(
                module,
                "Apple Loses Another Top Executive to OpenAI",
                "Paul Meade, who oversees Vision Pro and upcoming smart glasses work, is leaving Apple for OpenAI's hardware unit.",
                source="MacRumors",
                facts=["Meade has been at Apple since 2010 and in the Vision Products Group since 2017."],
            ),
        ]

        events = module.cluster_articles(articles)
        titles = [event.title for event in events]
        joined = " || ".join(titles)

        self.assertEqual(len(events), 3, joined)
        self.assertTrue(any("Price Increase" in title for title in titles), joined)
        self.assertTrue(any("touchscreen MacBook" in title for title in titles), joined)
        self.assertTrue(any("OpenAI" in title for title in titles), joined)

    def test_iphone_ram_report_does_not_merge_with_touchscreen_macbook_roadmap(self):
        module = load_module()
        macbook_article = article_for(
            module,
            "Apple's touchscreen MacBook to use M5 Pro and M5 Max chips, not M6",
            "Apple's upcoming touchscreen MacBook will use M5 Pro and M5 Max chips, add OLED and Dynamic Island, and arrive in 14-inch and 16-inch sizes.",
            source="9to5Mac",
            facts=["Bloomberg also reports that Apple is in advanced testing of follow-up MacBook models powered by M7 Pro and M7 Max chips."],
        )
        iphone_article = article_for(
            module,
            "New iPhone 18 specs report raises big question of iOS 27 limitations",
            "Ming-Chi Kuo says Apple's lower-end iPhone 18 will use the A20 chip with 9GB of RAM, raising questions about Apple Intelligence features in iOS 27.",
            source="9to5Mac",
            facts=["The base iPhone 18 was previously rumored to get 12GB of RAM, but the new report says 9GB is planned instead."],
        )

        events = module.cluster_articles([macbook_article, iphone_article])

        self.assertEqual(len(events), 2)

    def test_multi_vendor_chip_background_story_is_deferred_weak(self):
        module = load_module()
        title = "联发科最强芯！天玑9600 Pro首发主机级超分插帧"
        summary = (
            "今年9月，高通、苹果和联发科将陆续推出各自的旗舰芯片，分别为骁龙8E6系列、"
            "A20系列以及天玑9600系列。文章主体介绍联发科天玑9600 Pro 的 NGP 神经加速器。"
        )

        self.assertTrue(module.is_multi_vendor_chip_or_phone_roadmap_background_story(title, summary))
        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_refurbished_store_availability_does_not_merge_with_memory_price_crisis(self):
        module = load_module()
        refurbished_article = article_for(
            module,
            "Refurbished MacBook Neo Models Now Available, a Day After Price Hike",
            "Apple today began selling refurbished MacBook Neo units through its Certified Refurbished store. The base model starts at $599 after Apple raised prices on new MacBook models.",
            source="MacRumors",
            facts=["The refurbished MacBook Neo is available in all four colors in Apple's Certified Refurbished store."],
        )
        crisis_article = article_for(
            module,
            "Micron Suggests Apple Helped Cause Memory Price Crisis",
            "Micron said tough supplier negotiations contributed to the memory shortage, while Apple raised Mac and iPad prices because DRAM and NAND costs increased.",
            source="MacRumors",
            facts=["Apple's response says AI data centers drove memory and storage demand and unusually fast component-cost increases."],
        )

        self.assertEqual(refurbished_article.event_kind, "retail_store")
        events = module.cluster_articles([refurbished_article, crisis_article])

        self.assertEqual(len(events), 2)

    def test_mixed_retail_and_price_event_is_split_before_output(self):
        module = load_module()
        refurbished_article = article_for(
            module,
            "Refurbished MacBook Neo Models Now Available, a Day After Price Hike",
            "Apple today began selling refurbished MacBook Neo units through its Certified Refurbished store. The base model starts at $599 after Apple raised prices on new MacBook models.",
            source="MacRumors",
            facts=["The refurbished MacBook Neo is available in all four colors in Apple's Certified Refurbished store."],
        )
        crisis_article = article_for(
            module,
            "Micron Suggests Apple Helped Cause Memory Price Crisis",
            "Micron said tough supplier negotiations contributed to the memory shortage, while Apple raised Mac and iPad prices because DRAM and NAND costs increased.",
            source="MacRumors",
            facts=["Apple's response says AI data centers drove memory and storage demand and unusually fast component-cost increases."],
        )
        mixed_event = module.event_from_article_group(
            module.cluster_articles([refurbished_article])[0],
            [refurbished_article, crisis_article],
        )

        split_events = module.split_mixed_topic_event(mixed_event)

        self.assertEqual(len(split_events), 2)
        self.assertTrue(any(event.event_kind == "retail_store" for event in split_events))
        self.assertTrue(any(event.event_kind == "hardware_market" for event in split_events))

    def test_uk_cma_app_store_payment_and_nfc_rules_are_strong_regulation(self):
        module = load_module()
        title = "UK Pushes Apple to Loosen App Store Payment and NFC Rules"
        summary = (
            "The UK's Competition and Markets Authority proposed letting app developers direct users "
            "to payment options outside Apple's App Store and requiring Apple to open iOS NFC access "
            "for contactless payments, digital wallets, digital identity, and car keys."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "regional_regulation")
        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "strong", reason)

    def test_siri_ai_eu_dma_meeting_merges_across_policy_and_leadership_angles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Tim Cook and EU tech chief hold virtual meeting over Siri AI - 9to5Mac",
                "Tim Cook held constructive talks with EU tech chief Henna Virkkunen over launching Siri AI in Europe while complying with the Digital Markets Act.",
                "9to5Mac",
                facts=[
                    "Apple proposed a Trusted System Agent and an 18-month transition period for virtual assistant interoperability.",
                ],
            ),
            article_for(
                module,
                "苹果 CEO 库克与欧盟科技主管就 Siri AI 展开“建设性”会谈",
                "库克与欧盟科技事务负责人亨娜・维尔库宁举行建设性会谈，讨论苹果如何在欧洲推出新版 Siri，同时避免违反 DMA。",
                "IT之家",
            ),
            article_for(
                module,
                "Tim Cook's government liaison position comes into focus before stepping down as Apple CEO",
                "Apple CEO Tim Cook had a virtual meeting with Henna Virkkunen about launching revamped AI tools in the EU without violating the Digital Markets Act.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Tim Cook即将卸任苹果CEO 提前上阵担任“政府联络官”",
                "报道称 Tim Cook 与欧盟委员会执行副主席 Henna Virkkunen 举行建设性虚拟会晤，讨论苹果如何在不违反 DMA 的前提下在欧盟推出 AI 工具。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual({article.event_kind for article in articles}, {"regional_regulation"})
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家", "AppleInsider", "cnBeta"})

    def test_epic_supreme_court_appeal_with_payment_facts_stays_strong_legal_event(self):
        module = load_module()
        title = "Supreme Court Will Hear Apple's Appeal in Epic Games App Store Fight"
        summary = (
            "The United States Supreme Court agreed to hear Apple's appeal against a contempt ruling "
            "over App Store anti-steering rules, external purchase links, and 12% or 27% commissions."
        )
        facts = [
            "The previous denial involved the original Epic Games vs. Apple commission battle, but the case has since piqued the Supreme Court's interest.",
            "Apple says the injunction did not prevent it from instituting new fees on external purchases.",
            "Epic says it will fight against junk fees Apple charges on third-party payments.",
            "A noisy translated paragraph says developers still needed to pay Apple Pay 12% or 27% commissions.",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary, facts), "legal_antitrust")
        self.assertEqual(tier, "strong", reason)

    def test_payment_regulation_epic_appeal_and_amex_rewards_do_not_merge(self):
        module = load_module()
        amex = article_for(
            module,
            "American Express Announces New Apple Pay Feature",
            "American Express cardholders can redeem Membership Rewards points when checking out with Apple Pay on iPhone and iPad.",
            "MacRumors",
        )
        uk_cma = article_for(
            module,
            "UK Pushes Apple to Loosen App Store Payment and NFC Rules",
            "The CMA proposed allowing app developers to direct users outside the App Store and requiring Apple to open iOS NFC access.",
            "MacRumors",
        )
        epic = article_for(
            module,
            "US Supreme Court agrees to hear Apple's Epic Games appeal",
            "The Supreme Court will review Apple's appeal over an Epic Games ruling about App Store anti-steering and external-link commissions.",
            "AppleInsider",
        )

        events = module.cluster_articles([amex, uk_cma, epic])

        self.assertEqual(len(events), 3)

    def test_airdrop_vulnerability_multisource_cluster_includes_chinese_coverage(self):
        module = load_module()
        english = article_for(
            module,
            "Three AirDrop vulnerabilities discovered, with Apple working on a full fix",
            "Researchers found three AirDrop vulnerabilities affecting iPhone and Mac; Apple fixed one and is working on full fixes.",
            "9to5Mac",
        )
        chinese = article_for(
            module,
            "影响全球超 50 亿台手机：苹果隔空投送 / 谷歌快速分享曝安全漏洞",
            "CISPA 研究指出苹果隔空投送 AirDrop 和谷歌 Quick Share 存在安全漏洞，攻击者可在 10-30 米范围内让相关服务崩溃。",
            "IT之家",
        )

        tier, reason = module.classify_relevance_tier(chinese.title, chinese.summary, [], "IT之家")
        events = module.cluster_articles([english, chinese])

        self.assertIn(tier, {"strong", "ecosystem"}, reason)
        self.assertEqual(len(events), 1)
        self.assertNotEqual(events[0].relevance_tier, "weak")

    def test_apple_watch_redesign_multisource_reports_merge(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Report: Apple Watch Redesign Coming Next Year With New Band System",
            "A leaker says the Apple Watch will get a major overhaul in 2027 with a new band attachment system and possible compatibility break.",
            "MacRumors",
        )
        nine = article_for(
            module,
            "Apple Watch to get 'major overhaul' next year, says leaker",
            "The Apple Watch Series line could get a 2027 redesign, with Weibo leaker Instant Digital tying it to Apple Watch X band-system rumors.",
            "9to5Mac",
        )
        insider = article_for(
            module,
            "Apple Watch redesign will have new band attachment points",
            "Apple Watch Series 13 may bring a major redesign with new band attachment points, making older watch bands incompatible.",
            "AppleInsider",
        )

        events = module.cluster_articles([macrumors, nine, insider])

        self.assertEqual(len(events), 1)

    def test_creator_studio_multisource_reports_merge_and_stay_software(self):
        module = load_module()
        newsroom = article_for(
            module,
            "Apple Creator Studio gets smarter, faster, and more connected",
            "Apple introduced updates to Creator Studio, including Final Cut Pro AI captions, Pixelmator Pro image generation, Logic Pro tools, Motion, Compressor, and Final Cut Camera features.",
            "Apple Newsroom",
        )
        macrumors = article_for(
            module,
            "Apple Creator Studio Gets New AI Features",
            "Apple Creator Studio adds AI-powered updates for Final Cut Pro, Pixelmator Pro, Logic Pro, Motion, Compressor, and other Apple creative apps.",
            "MacRumors",
        )
        ithome = article_for(
            module,
            "苹果升级 Apple 创作坊：扩展 AI 工具，订阅年费 380 元",
            "Apple 创作坊更新 Final Cut Pro、Pixelmator Pro、Logic Pro、Motion 和 Compressor，国内订阅年费 380 元。",
            "IT之家",
        )

        events = module.cluster_articles([newsroom, macrumors, ithome])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "software_systems")
        self.assertNotEqual(events[0].event_kind, "hardware_market")

    def test_creator_studio_and_iwork_updates_remain_separate(self):
        module = load_module()
        creator = article_for(
            module,
            "Apple Creator Studio Gets New AI Features",
            "Apple Creator Studio adds AI-powered updates for Final Cut Pro, Pixelmator Pro, Logic Pro, Motion, and Compressor.",
            "MacRumors",
        )
        iwork = article_for(
            module,
            "Pages, Keynote, and Numbers updates arrive with these new features",
            "Apple updated Pages, Keynote, and Numbers to version 15.3 with new transitions, custom shapes, image replacement, and sheet tab colors.",
            "9to5Mac",
        )

        events = module.cluster_articles([creator, iwork])

        self.assertEqual(len(events), 2)

    def test_huawei_launch_competitor_story_stays_weak(self):
        module = load_module()
        title = "9月巅峰对决！华为Mate 90系列迎战iPhone 18 Pro"
        summary = "华为 Mate 90 系列计划 9 月发布，报道将其与苹果 iPhone 18 Pro 发布窗口和市场竞争作比较。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)
        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")

    def test_chinese_uk_cma_payment_nfc_rules_are_strong_and_merge_with_english(self):
        module = load_module()
        chinese = article_for(
            module,
            "英国监管机构拟针对苹果谷歌出台新规：开放平台外支付与 iOS NFC 功能",
            "英国竞争与市场管理局 CMA 计划允许英国应用开发者把用户引导至应用商店之外付款，并研究要求苹果开放 iOS NFC，让第三方钱包、数字身份和汽车钥匙服务接入。",
            "IT之家",
        )
        english = article_for(
            module,
            "UK Pushes Apple to Loosen App Store Payment and NFC Rules",
            "The CMA proposed letting developers direct users outside the App Store and requiring Apple to open iOS NFC access for contactless payments, digital wallets, digital identity, and car keys.",
            "MacRumors",
        )
        amex = article_for(
            module,
            "American Express Announces New Apple Pay Feature",
            "American Express cardholders can redeem Membership Rewards points when checking out with Apple Pay on iPhone and iPad.",
            "MacRumors",
        )

        self.assertEqual(chinese.relevance_tier, "strong", chinese.relevance_reason)
        self.assertEqual(english.relevance_tier, "strong", english.relevance_reason)
        events = module.cluster_articles([chinese, english, amex])

        self.assertEqual(len(events), 2)
        cma_events = [event for event in events if "CMA" in event.summary or "NFC" in event.summary or "nfc" in event.summary.lower()]
        self.assertEqual(len(cma_events), 1)
        self.assertEqual(len(cma_events[0].articles), 2)

    def test_airdrop_vulnerability_chinese_quick_share_story_stays_strong_and_merges(self):
        module = load_module()
        english = article_for(
            module,
            "Three AirDrop vulnerabilities discovered, with Apple working on a full fix",
            "Researchers found three AirDrop vulnerabilities affecting iPhone and Mac; Apple fixed one and is working on full fixes.",
            "9to5Mac",
        )
        chinese = article_for(
            module,
            "影响全球超 50 亿台手机：苹果隔空投送 / 谷歌快速分享曝安全漏洞",
            "CISPA 研究指出苹果 AirDrop 隔空投送和谷歌 Quick Share 存在安全漏洞，攻击者可在 10-30 米范围内让 AirDrop、接力和通用剪贴板等连续互通功能崩溃，苹果已修复其中一个漏洞并继续制作补丁。",
            "IT之家",
        )

        self.assertNotEqual(chinese.relevance_tier, "weak", chinese.relevance_reason)
        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_third_party_financial_service_only_supporting_apple_pay_is_weak(self):
        module = load_module()
        title = "马斯克的“银行”：X Money 上线，年化收益 6%、消费返现 3%"
        summary = (
            "X Money 面向美国 Premium 用户内测上线，提供活期利息、Visa 金属卡和返现；"
            "实体卡支持 Apple Pay，但报道主体是 X 的金融服务。"
        )

        self.assertNotEqual(module.detect_event_kind(title, summary), "wallet_feature")
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)

    def test_iphone_16e_refurbished_reports_merge_across_languages(self):
        module = load_module()
        english = article_for(
            module,
            "Apple Now Sells Refurbished iPhone 16e Starting at $419",
            "Apple updated its online refurbished store in the United States, adding the iPhone 16e with 128GB, 256GB, and 512GB models in black and white.",
            "MacRumors",
        )
        chinese = article_for(
            module,
            "苹果首次上架 iPhone 16e 官翻机：约 2853 元起售",
            "苹果美国官方翻新商店首次上架 iPhone 16e，提供 128GB、256GB、512GB 三种存储版本，售价分别为 419、509、679 美元。",
            "快科技",
        )

        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")

    def test_iphone_air_successor_reports_merge_across_languages(self):
        module = load_module()
        kuaikeji = article_for(
            module,
            "iPhone Air 2外观首秀：告别单摄 补齐影像短板",
            "曝光图显示 iPhone Air 2 采用横置相机 DECO，升级为双摄，预计配备 4800 万像素主摄和超广角。",
            "快科技",
        )
        ithome = article_for(
            module,
            "苹果 iPhone Air 2 渲染图首秀：升级双摄、A20 芯片、6.55 英寸、缩小灵动岛",
            "消息源分享 iPhone Air 2 渲染图，显示背面升级双摄，并称其配备 A20 芯片、6.55 英寸屏幕和更小灵动岛。",
            "IT之家",
        )

        events = module.cluster_articles([kuaikeji, ithome])

        self.assertEqual(len(events), 1)

    def test_apple_arcade_game_catalog_updates_are_strong_service_content(self):
        module = load_module()
        nine = article_for(
            module,
            "Family Feud Pocket lands on Apple Arcade with 4 more games coming later this week",
            "Apple Arcade added Family Feud Pocket to iPhone, iPad, Mac, Apple Vision Pro, Apple TV, and iPod touch, with four more App Store games coming July 2.",
            "9to5Mac",
        )
        macrumors = article_for(
            module,
            "Apple Arcade Adding 5 Games This Week, Including 'Family Feud Pocket'",
            "Apple Arcade is adding Family Feud Pocket and four additional games this week across iPhone, iPad, Mac, Apple TV, Apple Vision Pro, and iPod touch.",
            "MacRumors",
        )

        self.assertEqual(macrumors.relevance_tier, "strong", macrumors.relevance_reason)
        self.assertEqual(module.detect_event_kind(macrumors.title, macrumors.summary), "service_content")
        events = module.cluster_articles([nine, macrumors])

        self.assertEqual(len(events), 1)

    def test_product_data_leak_enforcement_specs_and_price_followups_stay_separate(self):
        module = load_module()
        enforcement = article_for(
            module,
            "Apple Crackdown Suspected After iPhone 18 Pro Leak Videos Disappear",
            "Apple appears to be filing DMCA takedowns against social media posts sharing stolen iPhone 18 Pro supplier videos and internal data from a Tata breach.",
            "MacRumors",
        )
        spec_leak = article_for(
            module,
            "iPhone 18 Pro leaks: Qualcomm or Apple C2 model, A20 details, camera upgrades",
            "Leaked iPhone 18 Pro files reveal A20 Pro packaging, C2 modem details, camera upgrades, and 12GB RAM.",
            "AppleInsider",
        )
        price_followup = article_for(
            module,
            "iPhone 18 Pro price may rise as memory and storage costs surge",
            "Analysts expect iPhone 18 Pro pricing to rise after Apple increased Mac and iPad prices due to DRAM and NAND shortages.",
            "快科技",
        )

        events = module.cluster_articles([enforcement, spec_leak, price_followup])

        self.assertEqual(len(events), 3)

    def test_apple_pay_rewards_reports_merge_across_amex_title_variants(self):
        module = load_module()
        macrumors = article_for(
            module,
            "American Express Announces New Apple Pay Feature",
            "American Express cardholders can redeem Membership Rewards points when checking out with Apple Pay on iPhone and iPad.",
            "MacRumors",
        )
        insider = article_for(
            module,
            "Amex cardholders can now use Membership Rewards during Apple Pay checkout",
            "Amex cardholders can now use Membership Rewards points during Apple Pay checkout with participating merchants.",
            "AppleInsider",
        )

        events = module.cluster_articles([macrumors, insider])

        self.assertEqual(len(events), 1)

    def test_online_refurbished_store_copy_detects_official_refurbished_iphone(self):
        module = load_module()
        title = "Apple Now Sells Refurbished iPhone 16e Starting at $419"
        summary = (
            "Apple today updated its online refurbished store in the United States, adding the iPhone 16e. "
            "Refurbished iPhone 16e models are available at discounted prices for the first time since launch."
        )

        self.assertTrue(module.is_official_apple_refurbished_product_story(f"{title} {summary}"))
        self.assertIn("apple-refurbished-iphone", module.primary_topic_facets(title, summary))

    def test_data_leak_title_action_wins_over_related_detail_background(self):
        module = load_module()
        enforcement = article_for(
            module,
            "Apple Crackdown Suspected After iPhone 18 Pro Leak Videos Disappear",
            "Apple appears to be filing DMCA takedowns against social media posts; background paragraphs mention A20 Pro packaging, C2 modem details, and camera upgrades from the same Tata leak.",
            "MacRumors",
        )
        specs = article_for(
            module,
            "iPhone 18 Pro leaks: Qualcomm or Apple C2 model, A20 details, camera upgrades",
            "Leaked files describe C2 modem choices, A20 Pro packaging, camera upgrades, and 12GB RAM; background paragraphs mention Apple is removing some leaked videos.",
            "AppleInsider",
        )

        self.assertIn("apple-product-data-leak-enforcement", module.article_primary_facets(enforcement))
        self.assertNotIn("apple-product-data-leak-specs", module.article_primary_facets(enforcement))
        self.assertIn("apple-product-data-leak-specs", module.article_primary_facets(specs))
        events = module.cluster_articles([enforcement, specs])

        self.assertEqual(len(events), 2)

    def test_data_leak_specs_merge_when_title_is_hardware_specs_and_body_names_leaked_files(self):
        module = load_module()
        english = article_for(
            module,
            "iPhone 18 Pro leaks: Qualcomm or Apple C2 model, A20 details, camera upgrades",
            "Leaked iPhone 18 Pro files reveal C2 modem choices, A20 Pro packaging, camera upgrades, and 12GB RAM.",
            "AppleInsider",
        )
        chinese = article_for(
            module,
            "iPhone 18 Pro曝光：或采用双调制解调器方案A20 Pro芯片与相机迎重大升级",
            "相关信息来自塔塔集团工厂遭遇网络攻击后泄露的机密文件，其中包括主板设计图、物料清单以及 A20 Pro 芯片与相机配置等技术文档。",
            "cnBeta",
        )

        self.assertIn("apple-product-data-leak-specs", module.article_primary_facets(chinese))
        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)

    def test_iphone_color_mockup_rumor_stays_strong_despite_third_party_source_context(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Alleged iPhone 18 Pro Sim Tray Again Shows Dark Cherry Color",
            "Apple's upcoming iPhone 18 Pro models are expected to introduce a dark cherry color, and a leaked SIM tray image gives another look at the finish.",
            "MacRumors",
        )
        ithome = article_for(
            module,
            "2026 苹果最抢手颜色：樱桃红 iPhone 18 Pro 测试照片流出",
            "消息源在 X 平台发布视频，展示正在测试的樱桃红 iPhone 18 Pro；另有卡托图片显示银灰、浅蓝等配色。",
            "IT之家",
        )

        self.assertEqual(ithome.relevance_tier, "strong", ithome.relevance_reason)
        events = module.cluster_articles([macrumors, ithome])

        self.assertEqual(len(events), 1)

    def test_refurbished_store_availability_is_not_color_mockup_context(self):
        module = load_module()
        title = "Apple Now Sells Refurbished iPhone 16e Starting at $419"
        summary = (
            "Apple today updated its online refurbished store in the United States, adding the iPhone 16e. "
            "The iPhone 16e comes in black or white, and Apple has both colors available."
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("apple-refurbished-iphone", facets)
        self.assertNotIn("iphone-color-mockup", facets)

    def test_iphone_color_mockup_and_refurbished_availability_do_not_merge(self):
        module = load_module()
        color = article_for(
            module,
            "Alleged iPhone 18 Pro Sim Tray Again Shows Dark Cherry Color",
            "A leaked SIM tray image allegedly shows Apple's iPhone 18 Pro in a dark cherry finish, with light blue and silver also rumored.",
            "MacRumors",
        )
        refurbished = article_for(
            module,
            "Apple Now Sells Refurbished iPhone 16e Starting at $419",
            "Apple updated its online refurbished store, adding iPhone 16e models at discounted prices. The iPhone 16e comes in black or white, and Apple has both colors available.",
            "MacRumors",
        )

        events = module.cluster_articles([color, refurbished])

        self.assertEqual(len(events), 2)

    def test_iphone_color_mockup_and_data_leak_enforcement_do_not_merge(self):
        module = load_module()
        color = article_for(
            module,
            "Alleged iPhone 18 Pro Sim Tray Again Shows Dark Cherry Color",
            "A leaked SIM tray image allegedly shows Apple's iPhone 18 Pro in a dark cherry finish, with light blue and silver also rumored.",
            "MacRumors",
        )
        enforcement = article_for(
            module,
            "Apple Crackdown Suspected After iPhone 18 Pro Leak Videos Disappear",
            "Apple appears to be filing DMCA takedowns against social media posts sharing stolen iPhone 18 Pro supplier videos and internal data from a Tata breach.",
            "MacRumors",
        )

        events = module.cluster_articles([color, enforcement])

        self.assertEqual(len(events), 2)

    def test_color_article_with_dmca_background_keeps_color_primary_topic(self):
        module = load_module()
        title = "苹果 iPhone 18 Pro“樱桃红”配色卡托曝光，消息称系列手机还可选“银灰”“浅蓝”配色"
        summary = (
            "博主曝光 iPhone 18 Pro 樱桃红配色卡托，并确认该系列还将提供银灰和浅蓝选项。"
            "背景信息提到近期塔塔电子泄露的测试视频，以及苹果正通过 DMCA 清理相关泄露内容。"
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("iphone-color-mockup", facets)
        self.assertNotIn("apple-product-data-leak-enforcement", facets)

    def test_red_finish_leak_title_keeps_color_primary_topic(self):
        module = load_module()
        title = "爱马仕橙退场！iPhone 18 Pro 红色款偷跑：年度爆款色预定"
        summary = (
            "最新泄露的文件还曝光了 iPhone 18 Pro 红色款；背景段落提到塔塔电子文件泄露、"
            "A20 Pro 数据表和供应商清单。"
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("iphone-color-mockup", facets)
        self.assertNotIn("apple-product-data-leak-specs", facets)

    def test_drop_test_title_keeps_drop_test_primary_topic(self):
        module = load_module()
        title = "iPhone 18 Pro 在泄露的坠落测试中亮相"
        summary = (
            "视频显示 iPhone 18 Pro 进行跌落测试；背景信息提到塔塔电子泄露文件包含 A20 Pro 数据表、"
            "供应商清单和组件文档。"
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("iphone-drop-test-leak", facets)
        self.assertNotIn("apple-product-data-leak-specs", facets)

    def test_data_leak_enforcement_title_does_not_bridge_visual_leak_events(self):
        module = load_module()
        title = "苹果疑似加大打击力度，iPhone 18 Pro 泄露测试视频在社交平台迅速消失"
        summary = (
            "文章称苹果通过 DMCA 或平台投诉推动泄露视频下架；正文背景描述这些视频展示了 iPhone 18 Pro "
            "跌落测试和深色外观。"
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("apple-product-data-leak-enforcement", facets)
        self.assertNotIn("iphone-drop-test-leak", facets)
        self.assertNotIn("iphone-color-mockup", facets)

    def test_foldable_iphone_ultra_mockup_does_not_merge_with_iphone_18_pro_specs_leak(self):
        module = load_module()
        ultra = article_for(
            module,
            "窥见苹果 iPhone Ultra 机密样机，该说些实话还是瞎话",
            "iPhone Ultra 机模与核心规格爆料趋于一致，苹果或采用宽比例折叠屏、无痕铰链、侧边指纹、A20 Pro 芯片和 5800mAh 电池。",
            "IT之家",
        )
        specs = article_for(
            module,
            "iPhone 18 Pro leaks: Qualcomm & C2 modem options, camera upgrades",
            "Leaked Tata files reveal iPhone 18 Pro C2 modem choices, A20 Pro packaging, camera upgrades, supplier lists, and component documents.",
            "AppleInsider",
        )

        self.assertIn("foldable-iphone-render-leak", module.article_primary_facets(ultra))
        events = module.cluster_articles([ultra, specs])

        self.assertEqual(len(events), 2)

    def test_9to5mac_posts_api_has_enough_depth_for_late_day_posts(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        api_text = " ".join(source.wordpress_posts_apis)

        self.assertRegex(api_text, r"per_page=(?:[1-9]\d{2,}|[6-9]\d)")

    def test_russia_fas_fine_reports_merge_across_sources(self):
        module = load_module()
        nine = article_for(
            module,
            "Russia threatens Apple with $52 million fine over alleged app discrimination",
            "Russia's Federal Antimonopoly Service is accusing Apple of discriminatory practices against Russian search engines and software and threatening a 4 billion roubles fine unless Apple remedies the violations by July 15.",
            "9to5Mac",
            facts=["The dispute follows Russia's rule requiring phones and tablets sold in the country to ship with MAX and other local apps preinstalled."],
        )
        insider = article_for(
            module,
            "Apple in Russia's crosshairs, facing $52M fine for bias against local apps",
            "Russia's antimonopoly regulator warned Apple it may face a $52 million fine unless it stops discriminating against local apps and search engines on iPhone and iPad.",
            "AppleInsider",
        )
        kuaikeji = article_for(
            module,
            "俄罗斯勒令苹果整改iOS应用预装规则：否则将面临最高40亿卢布罚款",
            "俄罗斯联邦反垄断局要求苹果在 7 月 15 日前整改 iOS 设备本土应用和搜索引擎预装规则，否则最高罚款 40 亿卢布。",
            "快科技",
        )

        self.assertEqual(nine.relevance_tier, "strong", nine.relevance_reason)
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/01/russia-threatens-apple-with-52-million-fine-over-alleged-app-discrimination/",
            title=nine.title,
            summary=nine.summary,
            feed_time_raw="2026-07-01T22:30:02",
        )
        self.assertTrue(module.is_relevant_candidate(candidate, source))
        events = module.cluster_articles([nine, insider, kuaikeji])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "regional_regulation")

    def test_safari_technology_preview_mcp_reports_merge_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Apple Releases Safari Technology Preview 247 With MCP Server for AI Agent Integration",
            "Apple released Safari Technology Preview 247, adding the Safari Model Context Protocol server for AI agents to inspect webpages, console logs, network requests, screenshots, and page elements.",
            "MacRumors",
            facts=["The update also includes fixes for Accessibility, CSS, HTML, JavaScript, WebDriver, WebGL, and more."],
        )
        nine = article_for(
            module,
            "Safari's new MCP server lets coding agents inspect and debug websites",
            "Apple says Safari Technology Preview 247 includes the Safari MCP server, letting compatible coding agents connect to Safari and debug websites directly in the browser.",
            "9to5Mac",
            facts=["The post lists tools such as browser_console_messages, screenshot, list_network_requests, and page_interactions."],
        )
        ithome = article_for(
            module,
            "苹果 Safari 技术预览版 247 引入 MCP 服务，AI 智能体加速网页开发和调试",
            "苹果 WebKit 博客宣布在 Safari Technology Preview 247 中引入 Safari MCP Server，可让编程智能体检查网页、控制台日志、网络请求、截图和页面元素。",
            "IT之家",
        )

        self.assertEqual(macrumors.relevance_tier, "strong", macrumors.relevance_reason)
        self.assertEqual(nine.relevance_tier, "strong", nine.relevance_reason)
        macrumors_source = source_named(module, "MacRumors")
        macrumors_candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/07/01/apple-releases-safari-technology-preview-247/",
            title=macrumors.title,
            summary="",
            feed_time_raw="Wednesday July 1, 2026 3:21 PM PDT",
        )
        self.assertTrue(module.is_relevant_candidate(macrumors_candidate, macrumors_source))
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/01/safaris-new-mcp-server-lets-coding-agents-inspect-and-debug-websites/",
            title=nine.title,
            summary=nine.summary,
            feed_time_raw="2026-07-01T21:59:20",
        )
        self.assertTrue(module.is_relevant_candidate(candidate, source))
        events = module.cluster_articles([macrumors, nine, ithome])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "software_systems")

    def test_macrumors_current_os_feature_guide_candidate_is_relevant(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/guide/ios-27-maps/",
            title="iOS 27: All the New Apple Maps Features",
            summary=(
                "The Maps app has several new iOS 27 features, including Flyover improvements, "
                "Local Lists, natural language search expansion, Apple Watch Parked Car widget, "
                "offline map improvements, and expanded Visited Places."
            ),
            feed_time_raw="Wednesday July 1, 2026 4:46 PM PDT",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 70)

        evergreen = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/guide/safari-technology-preview/",
            title="Safari Technology Preview",
            summary="Safari Technology Preview articles on MacRumors.com",
            feed_time_raw="",
        )

        self.assertFalse(module.is_relevant_candidate(evergreen, source))

    def test_non_apple_platform_apps_and_device_comparisons_stay_weak(self):
        module = load_module()
        examples = [
            (
                "Google's Gemini Spark for macOS will work on your local Mac files",
                "Google launched Gemini Spark for its macOS desktop app, letting Google's AI agent automate local files and connect to Google Tasks, Keep, Canva, Dropbox, Instacart, OpenTable, and Zillow.",
                "AppleInsider",
            ),
            (
                "Elon Musk's SpaceX prototypes an AI device thinner than an iPhone",
                "SpaceX showed investors an xAI-powered handheld prototype that is thinner than an iPhone and uses a Qualcomm chip, while Musk continues to say he does not want to build a phone.",
                "AppleInsider",
            ),
            (
                "The iPhone contributed to 'a collapse in US fertility,' claims scientific study",
                "A scientific study argues iPhone adoption changed social behavior and may correlate with declining US birthrates, but the article does not describe a new Apple product, policy, or research action.",
                "9to5Mac",
            ),
            (
                "MLB app gives baseball fans a new iPhone and iPad real-time scores widget",
                "The MLB app added real-time scores widgets for iPhone and iPad users as a third-party sports app update.",
                "9to5Mac",
            ),
            (
                "New Jamf Beacon gives businesses active Mac threat hunting",
                "Jamf launched Beacon, a third-party threat hunting tool for enterprise Macs.",
                "AppleInsider",
            ),
        ]

        for title, summary, source in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)
                event = module.cluster_articles([article_for(module, title, summary, source)])[0]
                self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_third_party_netflix_game_catalog_detail_path_stays_weak(self):
        module = load_module()
        title = "You're paying for 80+ iPhone and iPad games through Netflix, here's the full catalog - 9to5Mac"
        summary = (
            "Looking for new iPhone and iPad games to play? The App Store has plenty of games without ads and "
            "in-app purchases. Every Netflix subscription currently includes a huge collection of mobile and TV games."
        )
        facts = [
            "This includes the most affordable “Standard with ads” Netflix subscription for $8.99/month.",
            "Beyond these titles, Netflix supports a catalog of over 80 iPhone and iPad games. You can download any of these games from the App Store, then sign in with your Netflix email and password to play.",
        ]
        tier, reason = module.classify_relevance_tier(title, summary, facts, "9to5Mac")
        event = module.cluster_articles([article_for(module, title, summary, "9to5Mac", facts=facts)])[0]

        self.assertEqual(tier, "weak", reason)
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_apple_first_party_pro_app_update_stays_strong_and_separate_from_device_comparison_noise(self):
        module = load_module()
        final_cut = article_for(
            module,
            "iPhone 17 Pro just got an exclusive new pro-focused camera feature",
            (
                "Apple updated Final Cut Camera with Clean HDMI Out, an Apple first-party camera app feature "
                "exclusive to iPhone 17 Pro and iPhone 17 Pro Max."
            ),
            "9to5Mac",
            facts=[
                "Apple Creator Studio also received updates across Final Cut Pro, Pixelmator Pro, and other Apple creative apps."
            ],
        )
        spacex = article_for(
            module,
            "Elon Musk's SpaceX prototypes an AI device thinner than an iPhone",
            "SpaceX showed investors an xAI-powered handheld prototype that is thinner than an iPhone and uses a Qualcomm chip.",
            "AppleInsider",
        )

        self.assertEqual(final_cut.relevance_tier, "strong", final_cut.relevance_reason)
        self.assertEqual(spacex.relevance_tier, "weak", spacex.relevance_reason)

        events = module.cluster_articles([final_cut, spacex])

        self.assertEqual(len(events), 2)
        self.assertTrue(any(event.relevance_tier == "strong" and final_cut.title in {article.title for article in event.articles} for event in events))
        self.assertTrue(any(event.relevance_tier == "weak" and spacex.title in {article.title for article in event.articles} for event in events))

    def test_final_cut_camera_update_merges_without_camera_hardware_leakage(self):
        module = load_module()
        final_cut_9to5 = article_for(
            module,
            "iPhone 17 Pro just got an exclusive new pro-focused camera feature",
            "Apple updated Final Cut Camera with Clean HDMI Out, a new feature exclusive to iPhone 17 Pro and iPhone 17 Pro Max.",
            "9to5Mac",
            facts=["Apple Creator Studio also received updates across Final Cut Pro, Pixelmator Pro, and Motion."],
        )
        final_cut_insider = article_for(
            module,
            "New Final Cut Camera tries to be more useful for Mac users",
            "Apple released Final Cut Camera 2.3 for iPhone with easier media transfer to Final Cut Pro on Mac, Clean HDMI Out, and more ProRes options.",
            "AppleInsider",
        )
        final_cut_ithome = article_for(
            module,
            "苹果更新 Final Cut Camera 至 2.3 版：iPhone 17 Pro / Max 新增“纯净 HDMI 输出”",
            "苹果更新 Final Cut Camera 应用，在 2.3 版本中为 iPhone 17 Pro 和 iPhone 17 Pro Max 新增纯净 HDMI 输出，并提供更多 ProRes 选项。",
            "IT之家",
        )
        camera_leak = article_for(
            module,
            "苹果史上最大规模影像升级：iPhone 18 Pro 摄像头细节流出",
            "iPhone 18 Pro 和 iPhone 18 Pro Max 摄像头细节曝光，包含三摄布局、闪光灯、麦克风和激光雷达传感器位置。",
            "IT之家",
        )
        camera_patent = article_for(
            module,
            "苹果新 iPhone 相机防抖专利公示：机械校正保持画面水平",
            "苹果获批相机防抖专利，未来 iPhone 相机模块可能通过物理旋转图像传感器校正画面倾斜。",
            "IT之家",
        )

        events = module.cluster_articles([final_cut_9to5, final_cut_insider, final_cut_ithome, camera_leak, camera_patent])
        final_cut_events = [
            event
            for event in events
            if any("Final Cut Camera" in article.title for article in event.articles)
        ]

        self.assertEqual(len(final_cut_events), 1)
        self.assertEqual(len(final_cut_events[0].articles), 3)
        self.assertEqual(final_cut_events[0].event_kind, "os_app")
        self.assertFalse(
            any(camera_leak.title in {article.title for article in event.articles} and final_cut_9to5.title in {article.title for article in event.articles} for event in events),
            [{article.title for article in event.articles} for event in events],
        )
        self.assertFalse(
            any(camera_patent.title in {article.title for article in event.articles} and final_cut_9to5.title in {article.title for article in event.articles} for event in events),
            [{article.title for article in event.articles} for event in events],
        )
        self.assertFalse(
            any(camera_patent.title in {article.title for article in event.articles} and camera_leak.title in {article.title for article in event.articles} for event in events),
            [{article.title for article in event.articles} for event in events],
        )

    def test_hide_my_email_vulnerability_reports_merge_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Hide My Email bug allows 100% of real email addresses to be discovered",
                "A privacy flaw in Apple's Hide My Email feature means real email addresses can be discovered; EasyOptOuts reported the issue to Apple more than a year ago.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Hide My Email Vulnerability Exposes Real Email Addresses",
                "A flaw in Apple's Hide My Email service can allow almost anyone to uncover the real email address behind a generated alias, and Apple has failed to address it for more than a year.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果“Hide My Email”被曝安全漏洞：测试中 100% 可溯源真实邮箱",
                "研究人员称苹果 iCloud+ 的 Hide My Email 功能存在漏洞，测试中 100% 可反查真实邮箱，该问题已向苹果报告超过一年。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "security_privacy")

    def test_memory_supplier_talks_do_not_merge_with_unrelated_iphone_or_foldable_events(self):
        module = load_module()
        memory = article_for(
            module,
            "Apple in Talks to Buy Memory Chips From Chinese Makers CXMT and YMTC",
            "Apple is in talks to buy memory from ChangXin Memory Technologies and Yangtze Memory Technologies for devices sold in China, while Tim Cook has spoken with Trump administration officials including Treasury Secretary Scott Bessent.",
            "MacRumors",
        )
        chinese = article_for(
            module,
            "苹果被曝正洽谈采购长鑫 + 长江存储芯片，供应中国市场设备",
            "苹果正寻求从长鑫存储、长江存储采购存储芯片用于中国市场设备，以释放其他供应商产能给美国等市场。",
            "IT之家",
        )
        iphone_cut = article_for(
            module,
            "Apple Has Reportedly Cut iPhone 17 Lineup Production",
            "Apple reportedly cut iPhone 17 lineup production by 15% after a long sales cycle.",
            "MacRumors",
        )
        paste = article_for(
            module,
            "iOS 27 Adds New Copy and Paste Feature",
            "Apple added a new keyboard paste shortcut in iOS 27 for text, photos, links, and other copied content.",
            "MacRumors",
        )
        fold_panel = article_for(
            module,
            "iPhone Fold expected to fuel rebound in foldable phone panel shipments",
            "Counterpoint expects Apple's first foldable iPhone to account for 29% of foldable smartphone panel orders in 2026.",
            "9to5Mac",
        )

        events = module.cluster_articles([memory, chinese, iphone_cut, paste, fold_panel])
        memory_events = [event for event in events if any("CXMT" in article.title or "长鑫" in article.title for article in event.articles)]

        self.assertEqual(len(memory_events), 1)
        self.assertEqual(len(memory_events[0].articles), 2)
        self.assertEqual(len(events), 4)

    def test_iphone_roadmap_background_does_not_create_large_mixed_cluster(self):
        module = load_module()
        iphone_cut = article_for(
            module,
            "Apple Has Reportedly Cut iPhone 17 Lineup Production",
            (
                "Apple reportedly lowered iPhone 17 production plans by 15% after a long demand cycle. "
                "The article adds background that some buyers may be waiting for iPhone 18 Pro models and Apple's first foldable iPhone."
            ),
            "MacRumors",
        )
        paste = article_for(
            module,
            "iOS 27 Adds a Useful New Copy-and-Paste Feature to Your iPhone",
            "iOS 27 adds a keyboard copy-and-paste shortcut that can paste text, photos, and links from Safari, Reddit, Messages, and Notes.",
            "MacRumors",
        )
        roadmap = article_for(
            module,
            "Apple to Release These 16 New Products Later This Year",
            "Apple is expected to release a broad list of products, including iPhone, Apple Watch, Apple TV, HomePod, and MacBook updates.",
            "MacRumors",
        )
        foldable_en = article_for(
            module,
            "Apple reportedly orders 10M foldable iPhone Ultra models, which could sell for around $2500",
            "Apple has reportedly raised the foldable iPhone production target to 10 million units, up from earlier 7 million to 8 million estimates.",
            "9to5Mac",
        )
        foldable_cn = article_for(
            module,
            "近年来最密集发布节奏：消息称苹果今明两年拟推出至少 5 款 iPhone 新机",
            "日经亚洲称苹果要求供应商为今年生产约 1000 万部折叠屏 iPhone 做好准备，高于此前约 700 万至 800 万部的预期。",
            "IT之家",
        )
        camera = article_for(
            module,
            "苹果史上最大规模影像升级：iPhone 18 Pro 摄像头细节流出",
            "iPhone 18 Pro 和 iPhone 18 Pro Max 摄像头细节曝光，包含三摄布局、闪光灯、麦克风和激光雷达传感器位置。",
            "IT之家",
        )
        ipad = article_for(
            module,
            "苹果预计于 2027 年春季推出新款 11 英寸和 13 英寸 iPad Pro",
            "苹果计划在 2027 年春季发布新款 iPad Pro，升级重点是 M6 或 M7 芯片和散热系统。",
            "cnBeta",
        )

        events = module.cluster_articles([iphone_cut, paste, roadmap, foldable_en, foldable_cn, camera, ipad])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertFalse(
            any(iphone_cut.title in cluster and paste.title in cluster for cluster in clusters),
            clusters,
        )
        self.assertFalse(
            any(iphone_cut.title in cluster and foldable_en.title in cluster for cluster in clusters),
            clusters,
        )
        foldable_clusters = [cluster for cluster in clusters if foldable_en.title in cluster or foldable_cn.title in cluster]
        self.assertEqual(len(foldable_clusters), 1, clusters)
        self.assertEqual(foldable_clusters[0], {foldable_en.title, foldable_cn.title})
        self.assertGreaterEqual(len(events), 6, clusters)

    def test_ipad_product_roadmap_does_not_merge_with_foldable_iphone_production(self):
        module = load_module()
        ipad = article_for(
            module,
            "Apple to Launch New iPad Pro in Spring 2027",
            (
                "Apple is planning to release new 11-inch and 13-inch iPad Pro models in spring 2027. "
                "The iPad Pro models could use either M6 chips or M7 chips. "
                "The article notes in background that iPhone 18e, iPhone 18, and iPhone Air 2 are also slated for spring 2027."
            ),
            "MacRumors",
        )
        ipad_chips = article_for(
            module,
            "古尔曼：苹果 2027 春季更新 iPad Pro 机型，升级 M6/M7 芯片",
            (
                "苹果 2027 春季更新 iPad Pro 机型，仍包括 11 英寸和 13 英寸版本，升级重点是 M6 或 M7 芯片和散热系统。"
                "背景还提到苹果同期准备折叠屏 iPhone 和多款 iPhone 新机。"
            ),
            "IT之家",
        )
        ipad_cn = article_for(
            module,
            "苹果预计于2027年春季推出新款11英寸和13英寸iPad Pro",
            "苹果计划在 2027 年春季发布新款 iPad Pro，升级重点是 M6 或 M7 芯片和散热系统。",
            "cnBeta",
        )
        macbook = article_for(
            module,
            "M6 MacBook Pro Coming in Late 2026, Redesigned M7 Model Launching in 1H 2027",
            (
                "Apple plans to release an updated 14-inch MacBook Pro with an M6 chip in late 2026, "
                "then follow it with a revamped M7 MacBook Pro in the first half of 2027. "
                "The report also mentions future iPad Pro models in broader product-roadmap context."
            ),
            "MacRumors",
        )
        foldable = article_for(
            module,
            "Apple reportedly orders 10M foldable iPhone Ultra models, which could sell for around $2500",
            (
                "Apple plans to manufacture and sell around 10 million foldable iPhone Ultra models. "
                "Nikkei Asia reports that Apple raised the foldable iPhone production target from 7 million to 8 million units."
            ),
            "9to5Mac",
        )

        events = module.cluster_articles([ipad, ipad_chips, ipad_cn, macbook, foldable])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertFalse(any(ipad.title in cluster and foldable.title in cluster for cluster in clusters), clusters)
        self.assertFalse(any(ipad.title in cluster and macbook.title in cluster for cluster in clusters), clusters)
        ipad_clusters = [
            cluster for cluster in clusters if ipad.title in cluster or ipad_chips.title in cluster or ipad_cn.title in cluster
        ]
        self.assertEqual(len(ipad_clusters), 1, clusters)
        self.assertEqual(ipad_clusters[0], {ipad.title, ipad_chips.title, ipad_cn.title})
        self.assertEqual(len(events), 3, clusters)

    def test_macbook_price_hike_report_does_not_merge_with_macbook_chip_roadmap(self):
        module = load_module()
        price = article_for(
            module,
            "MacBook price hikes expected to contribute to drop in global laptop shipments",
            (
                "TrendForce says Apple's recent MacBook price hikes will contribute to a 13.6% drop "
                "in global laptop shipments, with AI data centers driving memory and storage component costs higher."
            ),
            "9to5Mac",
            facts=["Apple said AI data centers drove extraordinary memory and storage demand and unusually fast component-cost increases."],
        )
        roadmap = article_for(
            module,
            "M6 MacBook Pro Coming in Late 2026, Redesigned M7 Model Launching in 1H 2027",
            (
                "Bloomberg reports Apple plans an updated 14-inch MacBook Pro with an M6 chip in late 2026, "
                "then a redesigned M7 model in the first half of 2027."
            ),
            "MacRumors",
        )

        events = module.cluster_articles([price, roadmap])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)

    def test_macbook_price_shipments_report_does_not_get_product_roadmap_facet(self):
        module = load_module()
        price = article_for(
            module,
            "苹果MacBook全面涨价！2026年全球笔记本出货恐下跌13.6%",
            (
                "根据 TrendForce 最新笔记本产业研究，受零部件成本上升、终端售价上涨以及消费需求转弱影响，"
                "2026 年全球笔记本市场或将明显承压。苹果 MacBook 涨价后仍有望维持双位数增长。"
            ),
            "快科技",
        )

        self.assertIn("apple-product-price-increase", module.article_primary_facets(price))
        self.assertNotIn("macbook-product-roadmap", module.article_primary_facets(price))

    def test_non_apple_processor_review_using_macbook_as_benchmark_is_weak(self):
        module = load_module()
        title = "英特尔酷睿5 315实测：为硬刚MacBook Neo而生"
        summary = (
            "MacBook Neo 的成功让 Windows 阵营看到新的市场突破点。"
            "文章测试 Wildcat Lake 处理器中的酷睿 5 315，包含 CPU-Z、Cinebench、单核和多核成绩。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], source_name="快科技")

        self.assertEqual(tier, "weak")
        self.assertIn("benchmark", reason)

    def test_iphone_18_data_leak_detail_is_strong_and_merges_with_main_leak_event(self):
        module = load_module()
        main_leak = article_for(
            module,
            "苹果史上最大规模泄密！iPhone 18 Pro / Max 被彻底扒干净",
            (
                "苹果印度供应商塔塔电子遭黑客入侵，超过 630GB 内部文件泄露，"
                "涉及 iPhone 18 Pro 和 iPhone 18 Pro Max 的组件设计、规格文件、质量控制和测试资料。"
            ),
            "IT之家",
            facts=["文件显示 iPhone 18 Pro 内部代号 V63，iPhone 18 Pro Max 内部代号 V64。"],
        )
        color_and_sim = article_for(
            module,
            "iPhone 18 Pro秘密都被泄露完了：只剩价格还没公布",
            (
                "苹果印度供应商塔塔电子近期遭黑客组织攻击并泄露超过 630GB 内部文件，"
                "更多 iPhone 18 Pro 系列工程细节浮出水面，涉及测试配色、深樱桃红、更窄灵动岛、"
                "中国大陆单实体 SIM + eSIM 配置。"
            ),
            "快科技",
        )

        self.assertEqual(color_and_sim.relevance_tier, "strong", color_and_sim.relevance_reason)
        events = module.cluster_articles([main_leak, color_and_sim])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "hardware_market")

    def test_foldable_iphone_panel_market_reports_stay_strong_and_merge(self):
        module = load_module()
        appleinsider = article_for(
            module,
            "iPhone Fold expected to take 29% of 2026 foldable phone screen orders",
            (
                "Counterpoint Research says Apple's first iPhone Fold is expected to take 29% of "
                "2026 foldable smartphone display orders, trailing Samsung at 31% and ahead of Huawei at 24%."
            ),
            "AppleInsider",
        )
        nine = article_for(
            module,
            "iPhone Fold expected to fuel rebound in foldable phone panel shipments",
            (
                "Counterpoint Research says Apple's entry into the foldable phone market will help drive "
                "a 24% increase in foldable smartphone panel shipments and about 48% revenue growth."
            ),
            "9to5Mac",
            facts=["Samsung Display is expected to be the sole supplier of panels for Apple's first foldable iPhone."],
        )
        ithome = article_for(
            module,
            "CounterPoint 称 iPhone Ultra 改写 2026 全球折叠面板供应格局，苹果首年贡献 29% 采购份额",
            (
                "CounterPoint Research 预估苹果首款折叠 iPhone 上市后，在 2026 年全球折叠手机屏幕出货量中"
                "斩获约 29% 的订单，全年折叠屏面板出货量预计约 2750 万片，同比增长约 24%。"
            ),
            "IT之家",
        )

        self.assertEqual(nine.relevance_tier, "strong", nine.relevance_reason)
        self.assertEqual(ithome.relevance_tier, "strong", ithome.relevance_reason)
        events = module.cluster_articles([appleinsider, nine, ithome])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertNotIn("mixed primary topic facets", events[0].merge_warnings)

    def test_foldable_panel_market_report_does_not_merge_with_production_target(self):
        module = load_module()
        panel = article_for(
            module,
            "iPhone Fold expected to fuel rebound in foldable phone panel shipments",
            (
                "Counterpoint Research says Apple's entry into the foldable phone market will help drive "
                "a 24% increase in foldable smartphone panel shipments and about 48% revenue growth. "
                "Apple is expected to account for 29% of foldable smartphone panel orders."
            ),
            "9to5Mac",
        )
        production = article_for(
            module,
            "Apple reportedly orders 10M foldable iPhone Ultra models, which could sell for around $2500",
            (
                "Nikkei Asia reports Apple has raised the foldable iPhone production target to 10 million units, "
                "up from earlier 7 million to 8 million estimates, with the first model expected to sell for around $2500."
            ),
            "9to5Mac",
        )

        events = module.cluster_articles([panel, production])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)

    def test_direct_iphone_battery_capacity_rumor_is_not_third_party_platform_status(self):
        module = load_module()
        title = "iPhone 18 Pro Max电池容量新鲜出炉：5425mAh刷新苹果纪录"
        summary = (
            "快科技7月2日消息，有博主在社交平台上公布了iPhone 18 Pro Max的电池容量信息。"
            "其中国行版本的电池容量为5235mAh，而eSIM版本则达到了5425mAh，创苹果历史新高，两者容量相差190mAh。"
            "作为对比，iPhone 17 Pro Max eSIM版的电池容量为5088mAh，与iPhone 18 Pro Max eSIM版相比，容量差距为337mAh；"
            "而iPhone 17 Pro Max国行版的电池容量为4823mAh，与iPhone 18 Pro Max国行版之间的差距则达到了412mAh。"
        )
        facts = [
            "iPhone 18 Pro Max 国行版预计采用实体 SIM 加 eSIM 并存的组合方式。",
            "目前国内三大运营商中国联通、中国移动和中国电信均已正式启动面向 eSIM 手机的相关运营服务，用户可前往线下营业厅办理。",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "快科技")
        event = module.cluster_articles([article_for(module, title, summary, "快科技", facts=facts)])[0]

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_third_party_mfi_adapter_and_magsafe_case_stay_weak(self):
        module = load_module()
        cases = [
            (
                "酷态科推出 CP 苹果转接头 C to L：配硅胶绳套、获 MFi 认证，69 元",
                "酷态科现已在京东上架一款 CP 苹果转接头 C to L，可以将 USB-C 接口充电线转成苹果 Lightning 接口，定价为 69 元。",
            ),
            (
                "XTREM 为苹果 iPhone 17 系列推出 MagSafe 彩色墨水屏手机壳：利用 NFC 供电、不影响无线充电，399 元",
                "制造商 XTREM 极稚宣布为苹果 iPhone 17 系列手机推出一款 MagSafe 墨水屏手机壳，产品利用 NFC 供电，支持苹果 MagSafe 磁吸生态。",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
                self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
                self.assertEqual(tier, "weak", reason)

    def test_third_party_browser_security_feature_does_not_merge_with_macos_malware_report(self):
        module = load_module()
        pamstealer = article_for(
            module,
            "PamStealer 恶意软件披露：针对苹果 Mac 用户，加载 Rust 载荷收集隐私数据",
            (
                "Jamf Threat Labs 披露名为 PamStealer 的恶意软件，主要针对苹果 macOS 用户，"
                "通过伪装成 Maccy 剪贴板管理器分发恶意 AppleScript 应用，并窃取浏览器 Cookie、"
                "剪贴板内容和加密货币钱包数据。"
            ),
            "IT之家",
        )
        opera = article_for(
            module,
            "Opera 推出 Paste Protect：防御剪贴板攻击，支持 Windows、macOS、Linux",
            (
                "Opera 宣布推出浏览器原生防御功能 Paste Protect，内置于 Opera 桌面浏览器中，"
                "可监控剪贴板活动并阻止潜在恶意命令，支持 Windows、macOS 和 Linux。"
            ),
            "IT之家",
        )

        self.assertEqual(pamstealer.relevance_tier, "strong")
        self.assertEqual(opera.relevance_tier, "weak")
        events = module.cluster_articles([pamstealer, opera])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)
        self.assertTrue(any(pamstealer.title in cluster for cluster in clusters), clusters)
        self.assertTrue(any(opera.title in cluster for cluster in clusters), clusters)

    def test_iphone_photography_awards_reports_merge_as_hardware_event(self):
        module = load_module()
        macrumors = article_for(
            module,
            "iPhone Photography Awards Highlight Best Images of 2026",
            (
                "The iPhone Photography Awards announced the 2026 winners, with the grand prize image "
                "shot on an iPhone 15 Pro and winning entries also captured on older iPhone models."
            ),
            "MacRumors",
        )
        nine = article_for(
            module,
            "Check out all the winning shots in the 2026 iPhone Photography Awards",
            "The 2026 iPhone Photography Awards winners include images shot on iPhone and iPad devices by photographers around the world.",
            "9to5Mac",
        )
        appleinsider = article_for(
            module,
            "Gorgeous shots winning 2026 iPhone Photography Awards show old models still cut it",
            "The winners of the 2026 iPhone Photography Awards have been announced after entries from more than 140 countries were submitted.",
            "AppleInsider",
        )

        events = module.cluster_articles([macrumors, nine, appleinsider])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual(events[0].category, "hardware_products")

    def test_price_stock_reaction_does_not_merge_with_icloud_perks_or_production_cut(self):
        module = load_module()
        icloud = article_for(
            module,
            "iPhone Users Who Pay for iCloud Storage Get Two New Perks on iOS 27",
            "iOS 27 adds two iCloud+ perks including higher Apple Intelligence limits and HomeKit Secure Video summaries.",
            "MacRumors",
        )
        stock = article_for(
            module,
            "Apple stock recovers after hit from unprecedented price hikes on products",
            (
                "Last week, Apple announced dramatic price increases on Macs, iPads, and other products "
                "due to rising component costs. Apple stock rebounded with a 5% gain today."
            ),
            "9to5Mac",
        )
        production = article_for(
            module,
            "消息称苹果下调 iPhone 生产计划以应对涨价影响",
            (
                "产业链称苹果下调整体市场预期，iPhone 生产计划削减 15%，以应对涨价带来的潜在销量波动，"
                "传闻称 iPhone 17 Pro 系列涨价 800-1000 元。"
            ),
            "快科技",
        )

        events = module.cluster_articles([icloud, stock, production])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 3, clusters)

    def test_modem_and_nand_data_leak_details_stay_separate(self):
        module = load_module()
        modem = article_for(
            module,
            "iPhone 18 Pro Could Use Qualcomm Modem in the US and C2 Elsewhere",
            (
                "Stolen Tata files show iPhone 18 Pro could use Qualcomm modem in the US and Apple C2 modem elsewhere. "
                "The breach involved 630GB of data, schematics, and supplier documents."
            ),
            "MacRumors",
        )
        nand = article_for(
            module,
            "iPhone 18 Pro high-capacity storage reportedly downgraded to QLC NAND",
            (
                "Stolen Tata files and Reptalica details say iPhone 18 Pro 1TB and 2TB models may use QLC NAND flash, "
                "while 256GB and 512GB versions use TLC NAND storage."
            ),
            "AppleInsider",
        )

        events = module.cluster_articles([modem, nand])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)

    def test_third_party_reference_and_explainer_projects_stay_weak(self):
        module = load_module()
        cases = [
            (
                "Explore every iPad ever released in this interactive timeline",
                "The sheets.works project catalogs all 45 iPad models released since 2010 across 131 colorways and turns the dataset into an interactive visualization.",
            ),
            (
                "New iFixit video shows how an iPhone battery is made",
                "iFixit published a video showing the production steps for an iPhone battery, including BMS connection, adhesive strips, and quality-control checks.",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
                self.assertEqual(tier, "weak", reason)

    def test_ifixit_battery_explainer_does_not_merge_with_iphone_battery_capacity_leak(self):
        module = load_module()
        leak = article_for(
            module,
            "iPhone 18 Pro Max’s huge battery size reportedly leaked",
            "A social media leak says iPhone 18 Pro Max may have 5,425 mAh in eSIM models and 5,235 mAh in physical SIM models.",
            "9to5Mac",
        )
        explainer = article_for(
            module,
            "New iFixit video shows how an iPhone battery is made",
            "iFixit published a video showing how an iPhone battery is made, including BMS connection and adhesive-strip production steps.",
            "9to5Mac",
        )

        events = module.cluster_articles([leak, explainer])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)

    def test_third_party_accessory_with_apple_compatibility_stays_weak_even_with_specs(self):
        module = load_module()
        cases = [
            (
                "XTREM 为苹果 iPhone 17 系列推出 MagSafe 彩色墨水屏手机壳：利用 NFC 供电、不影响无线充电，399 元",
                "制造商 XTREM 极稚宣布为苹果 iPhone 17 系列推出一款 MagSafe 墨水屏手机壳，厚度 2.2mm、重量 44g，支持 NFC 供电和无线充电。",
            ),
            (
                "酷态科推出 CP 苹果转接头 C to L：配硅胶绳套、获 MFi 认证，69 元",
                "酷态科推出第三方 C to L 转接头，支持苹果 Lightning 设备并通过 MFi 认证。",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                self.assertEqual(module.detect_event_kind(title, summary, []), "third_party_ecosystem")
                tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
                self.assertEqual(tier, "weak", reason)

    def test_tutorial_ad_malware_and_public_response_noise_stay_weak(self):
        module = load_module()
        cases = [
            (
                "iOS 27 Public Beta Available This Month, Here's How to Get Your iPhone Ready Now",
                "Apple previously announced the iOS 27 public beta would be released in July. The article outlines how to get ready and how to install the beta.",
            ),
            (
                "Malware found spreading through sponsored ad on X",
                "Jamf Threat Labs found a sponsored ad posing as a third-party Mac utility and redirecting users to a malicious lookalike domain.",
            ),
            (
                "韩红基金会回应采购万元苹果电脑：诚恳致歉",
                "韩红基金会回应采购单价上万的苹果电脑争议，称设备采购用于公益影像留存、素材制作和项目归档。",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(tier, "weak", reason)

    def test_foldable_iphone_ten_million_order_reports_merge_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Apple Ramps Foldable iPhone 'Ultra' Production to 10 Million Units",
            "Nikkei Asia says Apple told suppliers to prepare to make around 10 million foldable iPhones this year, up from 7-8 million units.",
            "MacRumors",
        )
        appleinsider = article_for(
            module,
            "Confident Apple increases its iPhone Fold orders to 10 million",
            (
                "Apple expects to sell 10 million of the iPhone Fold in 2026 and into early 2027, "
                "considerably up from previous estimates. A related paragraph mentions Samsung's estimated "
                "31% foldable display panel share and Huawei's 24% share."
            ),
            "AppleInsider",
        )
        kuaikeji = article_for(
            module,
            "苹果折叠屏信心满满！iPhone Ultra年产目标上调至1000万台",
            "供应链消息称苹果将首款折叠 iPhone 的生产目标由 700-800 万台上调至 1000 万台。",
            "快科技",
        )

        events = module.cluster_articles([macrumors, appleinsider, kuaikeji])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 1, clusters)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "AppleInsider", "快科技"})

    def test_official_apple_privacy_ad_is_direct_security_privacy_event(self):
        module = load_module()
        title = "岳云鹏出演苹果新广告：App 访问权限 iPhone 管，隐私由你说了算"
        summary = (
            "苹果今年持续推出 iPhone 隐私保护宣传活动，聚焦 App 隐私保护，发布由岳云鹏主演的影片。"
            "影片展示 App 在日常使用中索取超出实际所需权限，并介绍 App 审核准则、App 隐私标签、"
            "App 权限许可和 App 跟踪透明度等 iPhone 隐私保护功能。"
        )
        facts = [
            "App 审核准则：每款 App 在上架 App Store 之前，都需要经过专家审核流程，以检查是否存在恶意软件，以及可能影响用户安全与隐私的软件问题。",
            "App 隐私标签：顾客可以直接在 App Store 的 App 产品页面上查看清晰的隐私摘要，了解该 App 会收集哪些数据。",
            "App 权限许可：当第三方 App 首次请求使用用户数据时，用户会收到提示。",
            "App 跟踪透明度：App 在出于广告目的跨其他公司拥有的 App 和网站跟踪用户活动之前，必须先征得用户同意。",
        ]

        self.assertEqual(module.detect_event_kind(title, summary, facts), "security_privacy")
        tier, reason = module.classify_relevance_tier(title, summary, facts, "IT之家")
        self.assertEqual(tier, "strong", reason)

    def test_buying_advice_opinion_and_non_apple_memory_price_stay_weak(self):
        module = load_module()
        cases = [
            (
                "Which iPad is right for you? Here’s what Apple has to say - 9to5Mac",
                (
                    "Over the years, buying an iPad has become an increasingly confusing task. "
                    "The article summarizes how Apple markets each model and gives buying advice across the iPad lineup. "
                    "Tech specs include A16, M4, M5, Apple Intelligence support, Apple Pencil compatibility, "
                    "Magic Keyboard support, cameras, displays, storage choices, and price comparisons."
                ),
                "9to5Mac",
            ),
            (
                "We really need a way to hand over ownership of an Apple Home - 9to5Mac",
                (
                    "The author argues Apple should add an Owner role to Apple Home so a smart home can be handed over "
                    "to a new resident, but the piece is a wishlist based on personal moving experience."
                ),
                "9to5Mac",
            ),
            (
                "内存价格越来越贵：千元机受伤最严重",
                (
                    "卢伟冰指出不少千元机因为存储芯片价格上涨而取消 OLED 屏、满级防水和高强度玻璃等配置，"
                    "文章讨论安卓预算机和内存行业涨价，苹果只是成本背景。"
                ),
                "快科技",
            ),
        ]

        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_non_apple_memory_price_background_stays_deferred_after_event_refresh(self):
        module = load_module()
        article = article_for(
            module,
            "内存价格越来越贵：千元机受伤最严重",
            (
                "卢伟冰指出，不少原先的千元机“飘档”，OLED 屏、满级防水、高强度玻璃等曾经的标配在千元机上越来越少见。"
                "成本失控的根源在于存储芯片价格暴涨，文章称随着苹果等主流品牌先后启动涨价，手机行业被迫适应新的价格体系。"
            ),
            "快科技",
        )
        events = module.cluster_articles([article])

        self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_third_party_custom_unreleased_iphone_concept_stays_weak(self):
        module = load_module()
        title = "奢侈定制品牌Caviar替苹果率先发布iPhone Ultra折叠机：售价10万起"
        summary = (
            "苹果官方至今还没有发布传闻中的 iPhone Ultra 折叠机型，主打超高端定制的第三方厂商 Caviar "
            "结合供应链公开信息和泄露渲染图，提前推出 Flagship 限定系列，每款全球限量 19 台。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_camera_airpods_code_and_suspension_merge_without_iphone_sensor_leak(self):
        module = load_module()
        macrumors_code = article_for(
            module,
            "iOS 27 Beta Hints at New Apple Product Such as 'AirPods Ultra'",
            (
                "The second iOS 27 developer beta hints at a new Apple product codenamed B790 that can relay "
                "two images from cameras on either side of a user's head. The code may point to camera-equipped "
                "AirPods or smart glasses, both tied to Visual Intelligence."
            ),
            "MacRumors",
        )
        appleinsider_code = article_for(
            module,
            "AirPods with cameras show up in iOS 27 beta code",
            (
                "Code in the latest iOS 27 developer beta describes handling two images from cameras on either side "
                "of a user's head, pointing to expected AirPods with cameras rather than ordinary smart glasses."
            ),
            "AppleInsider",
        )
        ithome_code = article_for(
            module,
            "苹果 iOS 27 代码曝光 B790 耳机，指向带摄像头的 AirPods",
            (
                "IT之家称 iOS 27 开发者测试版出现代号 B790，代码字符串描述来自用户头部两侧摄像头的 2 张图像，"
                "后续判断更高概率指向带摄像头的 AirPods。"
            ),
            "IT之家",
        )
        samsung_sensor = article_for(
            module,
            "iPhone 18 系列将搭载三星图像传感器，打破索尼独家供应局面",
            (
                "产业链消息称 iPhone 18 系列将搭载三星图像传感器，三星将在美国得克萨斯州奥斯汀工厂为苹果生产高端图像传感器，"
                "打破索尼多年来对 iPhone 图像传感器的独家供应。"
            ),
            "快科技",
        )
        tata_leak = article_for(
            module,
            "iPhone 18 Pro 系列手机遭泄密后，印度政府宣布调查苹果供应商塔塔电子数据泄露事件",
            (
                "塔塔电子位于印度的工厂遭遇网络攻击，超过 630GB 机密数据被窃取，"
                "包括尚未发布的 iPhone 18 Pro 系列主板设计图纸以及多款苹果自研芯片数据手册。"
            ),
            "IT之家",
        )

        self.assertEqual(macrumors_code.relevance_tier, "strong", macrumors_code.relevance_reason)
        self.assertEqual(samsung_sensor.relevance_tier, "strong", samsung_sensor.relevance_reason)
        events = module.cluster_articles([macrumors_code, appleinsider_code, ithome_code, samsung_sensor, tata_leak])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 3, clusters)
        self.assertTrue(
            any(
                {macrumors_code.title, appleinsider_code.title, ithome_code.title} <= cluster
                for cluster in clusters
            ),
            clusters,
        )
        self.assertTrue(any({samsung_sensor.title} == cluster for cluster in clusters), clusters)
        self.assertTrue(any({tata_leak.title} == cluster for cluster in clusters), clusters)

    def test_camera_airpods_suspension_does_not_merge_with_iphone_battery_capacity(self):
        module = load_module()
        airpods = article_for(
            module,
            "Camera-Equipped AirPods Pro Development 'Suspended,' Leaker Claims",
            (
                "Development of Apple's rumored camera-equipped AirPods Pro has been halted. "
                "The built-in cameras would feed visual information about the wearer's surroundings to Siri "
                "and connect to Apple Intelligence."
            ),
            "MacRumors",
        )
        battery = article_for(
            module,
            "苹果 iPhone 18 Pro Max 电池首曝：5187mAh 容量，欣旺达生产",
            (
                "消息源分享了适用于苹果 iPhone 18 Pro Max 的电池电芯细节，型号 A3166 配备 3.903V 5187mAh 电池，"
                "此前 eSIM 版容量为 5425mAh，实体 SIM 卡版为 5235mAh。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([airpods, battery])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)

    def test_camera_airpods_suspension_merges_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Camera-Equipped AirPods Pro Development 'Suspended,' Leaker Claims",
            (
                "Development of Apple's rumored camera-equipped AirPods Pro has been halted. "
                "Kosutami says the project was suspended after earlier reports said it was in advanced testing."
            ),
            "MacRumors",
        )
        ithome = article_for(
            module,
            "消息称苹果带摄像头 AirPods Pro 项目“暂停”，距量产仅一步之遥",
            (
                "爆料者 Kosutami 透露，苹果内部代号 H90 的带红外摄像头 AirPods Pro 开发项目已被暂停，"
                "此前彭博社报道称这款带摄像头的 AirPods Pro 已接近量产。"
            ),
            "IT之家",
        )
        kuaikeji = article_for(
            module,
            "胎死腹中！苹果带摄像头AirPods Pro项目被曝暂停",
            "知情人士透露，苹果内部代号为 H90 的 AirPods Pro 开发项目已遭暂停。",
            "快科技",
        )

        events = module.cluster_articles([macrumors, ithome, kuaikeji])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 1, clusters)

    def test_platform_only_overlap_does_not_merge_ios_features_with_foldable_hardware(self):
        module = load_module()
        ios_features = article_for(
            module,
            "12 New Things Your iPhone Can Do in iOS 27",
            (
                "Apple will release iOS 27 in September with context-aware Siri, Safari tab organization, "
                "natural language shortcuts, Liquid Glass transparency controls, and Image Playground updates."
            ),
            "MacRumors",
        )
        foldable = article_for(
            module,
            "苹果首款折叠屏 iPhone Ultra 或搭载 2nm A20 Pro 芯片",
            (
                "供应链消息称苹果首款折叠屏 iPhone Ultra 预计将与 iPhone 18 Pro 系列同步发布，"
                "搭载台积电 2nm 工艺的 A20 Pro 芯片。"
            ),
            "快科技",
        )

        events = module.cluster_articles([ios_features, foldable])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)
        self.assertEqual(ios_features.event_kind, "os_app")
        self.assertEqual(foldable.event_kind, "hardware_market")

    def test_data_leak_sensor_supplier_chip_rumor_and_competitor_phone_stay_separate(self):
        module = load_module()
        tata = article_for(
            module,
            "iPhone 18 Pro 系列手机遭泄密后，印度政府宣布调查苹果供应商塔塔电子数据泄露事件",
            (
                "塔塔电子工厂遭遇网络攻击，超过 630GB 机密数据被窃取，包含 iPhone 18 Pro 主板设计图纸、"
                "跌落测试素材、摄像头模组和苹果自研芯片数据手册，印度政府已移交 CERT-In 调查。"
            ),
            "IT之家",
        )
        samsung_sensor = article_for(
            module,
            "iPhone 18 系列将搭载三星图像传感器，打破索尼独家供应局面",
            (
                "产业链消息称 iPhone 18 系列将首次采用三星图像传感器，三星将在得克萨斯州奥斯汀工厂"
                "为苹果生产高端图像传感器。"
            ),
            "快科技",
        )
        intel_denial = article_for(
            module,
            "iPhone 18 标准版采用英特尔 18A 工艺传闻被否认",
            (
                "爆料者称已经审阅塔塔工厂泄露的苹果内部文件，但没有找到标准版 iPhone 18 采用英特尔 18A "
                "制程生产 A20 芯片的证据。"
            ),
            "cnBeta",
        )
        redmi = article_for(
            module,
            "REDMI K100 系列今年将史诗级提档，工程机配色参考 iPhone 18 Pro",
            (
                "报道主体介绍 REDMI K100 系列配置，称工程机配色参考 iPhone 18 Pro 系列，"
                "并将采用骁龙芯片和 2 亿像素主摄。"
            ),
            "快科技",
        )

        self.assertEqual(redmi.relevance_tier, "weak", redmi.relevance_reason)
        events = module.cluster_articles([tata, samsung_sensor, intel_denial, redmi])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 4, clusters)

    def test_tata_government_investigation_and_dark_web_data_leak_merge_across_chinese_sources(self):
        module = load_module()
        ithome = article_for(
            module,
            "iPhone 18 Pro 系列手机遭泄密后，印度政府宣布调查苹果供应商塔塔电子数据泄露事件",
            (
                "塔塔电子位于印度的工厂上月遭遇大规模网络攻击，超过 630GB 机密数据被窃取，"
                "其中包括尚未发布的 iPhone 18 Pro 系列主板设计图纸，以及多款苹果自研芯片数据手册。"
                "印度政府已将事件移交 CERT-In 调查。"
            ),
            "IT之家",
        )
        kuaikeji = article_for(
            module,
            "海量未公开机密数据流入暗网 印度政府调查苹果手机信息泄露事件",
            (
                "印度政府正就塔塔电子大规模数据泄露事件展开正式调查。黑客组织 World Leaks "
                "窃取并上传超过 20 万份、总量约 630GB 的未公开机密数据，涵盖 iPhone 18 Pro "
                "跌落测试、主板芯片、摄像头模组和供应商清单。"
            ),
            "快科技",
        )
        cnbeta = article_for(
            module,
            "iPhone 18 Pro泄密影响恶劣 印度政府机构调查塔塔",
            (
                "印度政府已开始调查塔塔电子数据泄露事件，事件已上报给印度计算机应急响应小组。"
                "泄露文件包括 iPhone 18 Pro 的组件清单、供应商清单、机型照片和跌落测试视频，"
                "规模超过 630GB、涉及逾 20 万份文件。"
            ),
            "cnBeta",
        )

        events = module.cluster_articles([ithome, kuaikeji, cnbeta])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual({article.source for article in events[0].articles}, {"IT之家", "快科技", "cnBeta"})

    def test_mixed_data_leak_cluster_splits_weak_competitor_and_distinct_hardware_followups(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro 系列手机遭泄密后，印度政府宣布调查苹果供应商塔塔电子数据泄露事件",
                (
                    "塔塔电子工厂遭遇网络攻击，超过 630GB 机密数据被窃取，包含 iPhone 18 Pro 主板设计图纸、"
                    "跌落测试素材、摄像头模组和苹果自研芯片数据手册，印度政府已移交 CERT-In 调查。"
                ),
                "IT之家",
            ),
            article_for(
                module,
                "海量未公开机密数据流入暗网 印度政府调查苹果手机信息泄露事件",
                (
                    "印度政府正就塔塔电子大规模数据泄露事件展开正式调查。World Leaks 上传超过 630GB "
                    "苹果未公开机密数据，文件包含 iPhone 18 Pro 跌落测试、主板芯片和供应商清单。"
                ),
                "快科技",
            ),
            article_for(
                module,
                "iPhone 18 系列将搭载三星图像传感器，打破索尼独家供应局面",
                "产业链消息称 iPhone 18 系列将首次采用三星图像传感器，三星将在得克萨斯州奥斯汀工厂为苹果生产高端图像传感器。",
                "快科技",
            ),
            article_for(
                module,
                "iPhone 18 标准版采用英特尔 18A 工艺传闻被否认",
                (
                    "爆料者称已经审阅塔塔工厂泄露的苹果内部文件，但没有找到标准版 iPhone 18 采用英特尔 18A "
                    "制程生产 A20 芯片的证据，认为相关代工传闻不实。"
                ),
                "cnBeta",
            ),
            article_for(
                module,
                "8月见！REDMI K100系列外观全方位对标iPhone 18 Pro：中框背板同色",
                "REDMI K100 系列外观对标 iPhone 18 Pro，报道主体介绍 REDMI 手机规格和设计。",
                "快科技",
            ),
        ]
        events = module.cluster_articles(articles)
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 4, clusters)
        self.assertTrue(any({articles[0].title, articles[1].title} == cluster for cluster in clusters), clusters)
        self.assertTrue(any({articles[2].title} == cluster for cluster in clusters), clusters)
        self.assertTrue(any({articles[3].title} == cluster for cluster in clusters), clusters)
        self.assertTrue(any({articles[4].title} == cluster for cluster in clusters), clusters)

    def test_live_style_competitor_foldable_and_redmi_items_do_not_pollute_apple_events(self):
        module = load_module()
        ios_features = article_for(
            module,
            "12 New Things Your iPhone Can Do in iOS 27",
            "Apple will release iOS 27 in September with context-aware Siri, Safari tab organization, and Liquid Glass controls.",
            "MacRumors",
        )
        foldable_market = article_for(
            module,
            "华为首创阔折叠形态！苹果安卓集体跟进 大战一触即发",
            (
                "据数码闲聊站爆料，TOP6 手机厂商中，华为已率先发布阔折叠产品，vivo 暂时不做大阔折，"
                "其余几家厂商的大阔折机型预计将在 2026 年下半年至 2027 年上半年全部亮相，"
                "其中苹果将成为首个搭载 2nm 芯片的大阔折厂商。"
            ),
            "快科技",
        )
        redmi = article_for(
            module,
            "8月见！REDMI K100系列外观全方位对标iPhone 18 Pro：中框背板同色",
            "REDMI K100 系列外观对标 iPhone 18 Pro，报道主体介绍 REDMI 手机规格和设计。",
            "快科技",
        )

        self.assertEqual(foldable_market.relevance_tier, "weak", foldable_market.relevance_reason)
        self.assertEqual(redmi.relevance_tier, "weak", redmi.relevance_reason)
        events = module.cluster_articles([ios_features, foldable_market, redmi])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 3, clusters)
        self.assertTrue(any({ios_features.title} == cluster for cluster in clusters), clusters)

    def test_live_style_os_summary_and_non_apple_phone_stories_keep_correct_priority(self):
        module = load_module()
        ios_features = article_for(
            module,
            "12 New Things Your iPhone Can Do in iOS 27",
            (
                "Apple will release iOS 27 in September with context-aware Siri, Safari tab organization, "
                "Liquid Glass controls, AI wallpaper generation, and a Camera-related visual lookup workflow."
            ),
            "MacRumors",
        )
        foldable_market = article_for(
            module,
            "华为首创阔折叠形态！苹果安卓集体跟进 大战一触即发",
            (
                "据数码闲聊站爆料，TOP6手机厂商中，华为已率先发布阔折叠产品，vivo明确暂时不做大阔折，"
                "其余几家厂商的大阔折机型预计将在2026年下半年至2027年上半年全部亮相，"
                "其中苹果将成为首个搭载2nm芯片的大阔折厂商。"
            ),
            "快科技",
        )
        redmi = article_for(
            module,
            "8月见！REDMI K100系列外观全方位对标iPhone 18 Pro：中框背板同色",
            (
                "REDMI K100 系列今年将在 8 月发布，工程机配色参考 iPhone 18 Pro 系列，"
                "文章主体介绍 REDMI 手机的骁龙芯片、主摄和价格策略。"
            ),
            "快科技",
        )

        self.assertEqual(ios_features.event_kind, "os_app")
        self.assertEqual(ios_features.category, "software_systems")
        self.assertNotIn("iphone-camera-design-leak", module.article_primary_facets(ios_features))
        self.assertEqual(foldable_market.relevance_tier, "weak", foldable_market.relevance_reason)
        self.assertEqual(redmi.relevance_tier, "weak", redmi.relevance_reason)
        events = module.cluster_articles([ios_features, foldable_market, redmi])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 3, clusters)
        self.assertTrue(any({ios_features.title} == cluster for cluster in clusters), clusters)

    def test_chip_foundry_denial_keeps_chip_process_topic_despite_tata_leak_background(self):
        module = load_module()
        intel_denial = article_for(
            module,
            "英特尔代工苹果A20处理器传闻被否定 可信爆料者痛批原始消息源为“吹牛”",
            (
                "一则关于英特尔将为苹果基础版 iPhone 18 代工 A20 芯片的传闻仅维持数小时便被推翻。"
                "爆料者称已审阅近期从印度塔塔工厂泄露的苹果内部文件，但没有找到标准版 iPhone 18 "
                "采用英特尔 18A 制程工艺的证据。"
            ),
            "cnBeta",
        )

        facets = module.article_primary_facets(intel_denial)

        self.assertEqual(intel_denial.relevance_tier, "strong")
        self.assertIn("chip process", intel_denial.relevance_reason)
        self.assertIn("apple-chip-process-roadmap", facets)
        self.assertNotIn("apple-product-data-leak", facets)

    def test_cnbeta_iphone_18_ai_feature_limit_merges_with_ram_feature_story(self):
        module = load_module()
        macrumors = article_for(
            module,
            "iPhone 18 With 9GB RAM Still Won't Support Two New iOS 27 Features",
            (
                "The lower-end iPhone 18 and iPhone 18e will have 9GB of RAM, but two new Apple Intelligence "
                "features in iOS 27 will require 12GB of RAM."
            ),
            "MacRumors",
        )
        cnbeta = article_for(
            module,
            "iPhone 18系列或涨价 两项iOS 27新AI功能仍缺席 - Apple iPhone - cnBeta.COM",
            (
                "郭明錤预测苹果下一代入门机型 iPhone18 和 iPhone18e 将把运行内存从 8GB 提升至 9GB，"
                "不过即便升级至 9GB，这两款机型仍将缺席 iOS27 中两项最新的 Siri 和语音相关智能功能。"
            ),
            "cnBeta",
        )

        self.assertIn("iphone-memory-feature-support", module.article_primary_facets(cnbeta))
        events = module.cluster_articles([macrumors, cnbeta])

        self.assertEqual(len(events), 1)

    def test_prosser_apple_lawsuit_reports_merge_across_sources(self):
        module = load_module()
        insider = article_for(
            module,
            "Leaker Jon Prosser denies Apple's charges and blames everything on his co-defendant",
            (
                "Prosser's lawyers filed a rebuttal to Apple's lawsuit alleging he and Michael Ramacciotti "
                "conspired to steal trade secrets from an Apple employee's iPhone."
            ),
            "AppleInsider",
        )
        verge = article_for(
            module,
            "Jon Prosser responds to Apple lawsuit by blaming the other guy",
            (
                "Prosser admitted participating in a FaceTime call where unreleased iOS features were shown, "
                "but denied jointly planning to access Apple's alleged trade secrets and requested a jury trial."
            ),
            "The Verge",
        )

        self.assertEqual(verge.event_kind, "legal_antitrust")
        events = module.cluster_articles([insider, verge])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "legal_antitrust")

    def test_ios_point_release_internal_testing_reports_merge_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Apple Already Testing iOS 27.4",
            "Apple software engineers are already internally testing iOS 27.4 according to MacRumors visitor logs.",
            "MacRumors",
        )
        ithome = article_for(
            module,
            "苹果内部正测试 iOS 27.4，预计明年春季发布",
            (
                "MacRumors 网站日志显示，苹果软件工程师正在内部测试 iOS 27.4 版本。"
                "文章同时提到 iOS 27.0 在 WWDC 发布，将带来全新 Siri、相机智能、AI 壁纸、"
                "Safari 标签页整理、自然语言提醒事项和液态玻璃设计等功能。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([macrumors, ithome])

        self.assertEqual(len(events), 1)

    def test_internal_testing_point_release_requires_same_platform(self):
        module = load_module()
        ios = article_for(
            module,
            "Apple Already Testing iOS 27.4",
            "Apple software engineers began testing iOS 27.4 according to MacRumors visitor logs.",
            "MacRumors",
        )
        macos = article_for(
            module,
            "Apple Already Testing macOS 27.4",
            "Apple software engineers began testing macOS 27.4 according to MacRumors visitor logs.",
            "MacRumors",
        )

        events = module.cluster_articles([ios, macos])

        self.assertEqual(len(events), 2)

    def test_apple_watch_band_sensor_reports_merge_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Sketchy Rumor Claims Apple Watch Series 12 Could Introduce Sensor in Band",
            "A leaker claims Apple Watch Series 12 will feature a new health sensor injection molded into a fluoroelastomer band.",
            "MacRumors",
        )
        ithome = article_for(
            module,
            "消息称苹果 Apple Watch Series 12 新表带内嵌传感器，支持血糖监测等",
            (
                "IT之家 7 月 4 日消息，科技媒体 MacRumors 昨日发布博文，报道称在 Apple Watch Series 12 "
                "智能手表表带上，苹果公司可能会嵌入新的健康传感器。报道称 Apple Watch Series 12 "
                "这款表带将采用注塑方式，将传感器集成到硅胶表带中。该媒体指出苹果公司早在 2017 年"
                "获得相关专利，构想表带的每个链节可以容纳不同的功能，包括血压监测器和汗液传感器。"
                "随后消息源补充表示一款表带可能具备血糖监测功能。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([macrumors, ithome])

        self.assertEqual(len(events), 1)

    def test_india_app_store_icloud_card_payment_restore_merges_across_sources(self):
        module = load_module()
        english = article_for(
            module,
            "Four years on, Apple bends to India's banks over card payments",
            (
                "App Store and iCloud users in India should soon be able to subscribe using credit or debit cards again, "
                "as Apple tests the restored payment options with a limited number of users after complying with RBI card tokenisation rules."
            ),
            "AppleInsider",
        )
        chinese = article_for(
            module,
            "时隔约 5 年，苹果印度 App Store 测试恢复银行卡支付选项",
            (
                "印度财经媒体 Moneycontrol 报道称，苹果在印度小规模测试恢复 App Store 和 iCloud 交易的信用卡和借记卡支付选项。"
                "苹果此前因印度循环付款监管要求停止卡支付，如今完成 card tokenisation 合规后重新启用相关功能。"
            ),
            "IT之家",
        )

        self.assertIn(english.event_kind, {"wallet_feature", "app_store_trust", "os_app"})
        self.assertIn(chinese.event_kind, {"wallet_feature", "app_store_trust", "os_app"})
        self.assertEqual(english.relevance_tier, "strong", english.relevance_reason)
        self.assertEqual(chinese.relevance_tier, "strong", chinese.relevance_reason)
        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "IT之家"})

    def test_apple_watch_edge_ai_market_report_does_not_merge_with_dumb_phone_guide(self):
        module = load_module()
        watch_report = article_for(
            module,
            "Report: Apple Watch accounted for nearly all Edge AI smartwatch shipments in Q1 2026",
            (
                "Counterpoint Research says global shipments of Edge AI-capable smartwatches grew 70% year over year in Q1 2026, "
                "reaching 25% penetration, and Apple accounted for roughly 90% of those shipments. "
                "The report defines Edge AI smartwatches as devices with a dedicated neural engine or NPU running at least one health, safety, or interaction feature locally."
            ),
            "9to5Mac",
            facts=[
                "Blood pressure monitoring rose from 11% to 23% of smartwatch shipments, sleep apnea detection from 5% to 18%, and ECG from 31% to 34%.",
            ],
        )
        dumb_phone_guide = article_for(
            module,
            "Here's how to turn any iPhone into a dumb phone",
            (
                "The guide explains how parents can use Screen Time, allowed apps, and Safari restrictions to make an iPhone behave like a basic phone for children. "
                "A related link mentions a Counterpoint Apple Watch report, but the article itself is a how-to guide without a new Apple action."
            ),
            "9to5Mac",
        )
        ithome_watch = article_for(
            module,
            "Counterpoint：2026 年 Q1 全球端侧 AI 智能手表出货量同比增长 70%，苹果占约 90%",
            (
                "Counterpoint Research 报告称 2026 年第一季度全球支持端侧 AI 的智能手表出货量同比增长 70%，市场渗透率达到 25%，"
                "苹果在端侧 AI 智能手表出货量中占约 90%，全年渗透率有望接近 32%。"
            ),
            "IT之家",
        )

        self.assertEqual(watch_report.relevance_tier, "strong", watch_report.relevance_reason)
        self.assertEqual(ithome_watch.relevance_tier, "strong", ithome_watch.relevance_reason)
        self.assertEqual(dumb_phone_guide.relevance_tier, "weak", dumb_phone_guide.relevance_reason)
        events = module.cluster_articles([watch_report, dumb_phone_guide, ithome_watch])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, clusters)
        self.assertTrue(
            any({watch_report.title, ithome_watch.title} == cluster for cluster in clusters),
            clusters,
        )

    def test_apple_market_share_report_does_not_merge_with_os_beta_or_service_events(self):
        module = load_module()
        watch_report = article_for(
            module,
            "Report: Apple Watch accounted for nearly all Edge AI smartwatch shipments in Q1 2026",
            (
                "Counterpoint Research says global shipments of Edge AI-capable smartwatches grew 70% year over year in Q1 2026, "
                "reaching 25% penetration, and Apple accounted for roughly 90% of those shipments."
            ),
            "9to5Mac",
        )
        watchos_siri_beta = article_for(
            module,
            "watchOS 27 beta 3 includes upgraded Siri AI experience and dedicated Siri app",
            (
                "Apple Watch owners can now use the new Siri AI in watchOS 27 beta 3, "
                "including a dedicated Siri app and a more capable on-device assistant."
            ),
            "9to5Mac",
        )
        icloud_home_features = article_for(
            module,
            "Apple Home AI features locked behind 2TB iCloud+ plan",
            (
                "Apple says Apple Intelligence camera features in the Home app will require an iCloud+ plan starting at 2TB."
            ),
            "AppleInsider",
        )

        events = module.cluster_articles([watchos_siri_beta, icloud_home_features, watch_report])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertTrue(any(cluster == {watch_report.title} for cluster in clusters), clusters)
        self.assertFalse(
            any(watch_report.title in cluster and len(cluster) > 1 for cluster in clusters),
            clusters,
        )

    def test_mixed_beta_service_payment_and_market_events_split_after_clustering(self):
        module = load_module()
        visionos_beta = article_for(
            module,
            "Apple Seeds Third visionOS 27 Beta to Developers",
            "Apple provided developers with the third beta of visionOS 27, adding Siri AI and spatial environment updates for Vision Pro.",
            "MacRumors",
        )
        icloud_home = article_for(
            module,
            "Apple Intelligence Home Features Require 2TB iCloud+ Plan in iOS 27",
            "Apple says Apple Intelligence camera features in the Home app require an iCloud+ plan starting at 2TB.",
            "MacRumors",
        )
        payment = article_for(
            module,
            "Four years on, Apple bends to India's banks over card payments",
            "App Store and iCloud users in India can subscribe using credit or debit cards again as Apple tests restored payment options after complying with RBI card tokenisation rules.",
            "AppleInsider",
        )
        watch_report = article_for(
            module,
            "Report: Apple Watch accounted for nearly all Edge AI smartwatch shipments in Q1 2026",
            "Counterpoint says Edge AI-capable smartwatch shipments grew 70% year over year, and Apple accounted for roughly 90% of shipments.",
            "9to5Mac",
        )

        events = module.cluster_articles([visionos_beta, icloud_home, payment, watch_report])
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertTrue(any(cluster == {payment.title} for cluster in clusters), clusters)
        self.assertTrue(any(cluster == {watch_report.title} for cluster in clusters), clusters)
        self.assertFalse(
            any(
                payment.title in cluster
                and (visionos_beta.title in cluster or icloud_home.title in cluster or watch_report.title in cluster)
                for cluster in clusters
            ),
            clusters,
        )
        self.assertFalse(
            any(watch_report.title in cluster and len(cluster) > 1 for cluster in clusters),
            clusters,
        )


    def test_mac_ai_demand_does_not_merge_with_foldable_iphone_supply_chain(self):
        module = load_module()
        macrumors_mac_ai = article_for(
            module,
            "Apple Silicon Exec Explains Mac Mini AI Demand and On-Device Future",
            (
                "Apple's Mac mini and Mac Studio have become the machines of choice for running AI agents, "
                "according to Doug Brooks, Apple's senior product manager of Apple silicon. "
                "Brooks made the claim while discussing Apple's chip strategy and on-device AI future."
            ),
            "MacRumors",
            facts=[
                "Brooks says that the company has seen \"incredible demand\" for the two desktop Macs.",
                "Many AI tools are also Mac-first or Mac-only, which Brooks says has helped cement the Mac's standing among developers.",
                "Apple more recently added neural accelerators to the GPU, extending AI performance from iPhone-class parts up to the Mac's largest silicon.",
            ],
        )
        cnbeta_mac_ai = article_for(
            module,
            "苹果高管详解 Mac mini 在本地 AI 时代走红的原因",
            (
                "苹果公司负责 Apple 芯片产品的高级产品经理 Doug Brooks 表示，Mac mini 与 Mac Studio "
                "已经成为众多开发者和团队运行 AI 智能体的首选设备。"
            ),
            "cnBeta",
            facts=[
                "Brooks 称，公司看到来自这两款桌面 Mac 的“惊人需求”。",
                "很多用户希望有一台由自己掌控、与主力电脑隔离、并且可以 7×24 小时不间断运行的系统。",
            ],
        )
        iphone_ultra_availability = article_for(
            module,
            "Limited availability of the iPhone Ultra may be a feature, not a bug",
            (
                "After conflicting reports about when the iPhone Ultra would launch, there is now a clear consensus "
                "that it will be announced in September alongside the iPhone 18 Pro."
            ),
            "9to5Mac",
            facts=[
                "Apple analyst Ming-Chi Kuo warned that only one million units may be manufactured within the third quarter.",
                "Delivery times could stretch four to six weeks or more for the folding iPhone.",
            ],
        )
        foldable_supply = article_for(
            module,
            "iPhone Ultra 本月开始大规模量产，供应链急招工人",
            (
                "蓝思科技大规模急招操作工、质检员和技术员，业内认为这是为苹果折叠屏 iPhone Ultra "
                "量产做人力储备。"
            ),
            "cnBeta",
            facts=[
                "蓝思科技将为苹果折叠屏 iPhone Ultra 供应 UTG 玻璃，良率已突破 90%。",
                "扩招岗位月薪 5500 至 7500 元，并覆盖操作工人、质检员、包装员、技术员等岗位。",
            ],
        )
        apple_foldable_phone_forecast = article_for(
            module,
            "郭明錤爆料最新苹果折叠手机：出货量明显不足",
            (
                "知名分析师郭明錤预测，苹果的可折叠手机可能沿用 iPhone X 的发布节奏，"
                "会先随秋季新品发布，但数月后才开放预购和销售。"
            ),
            "快科技",
            facts=[
                "2026 年下半年可折叠 iPhone 的组装出货量约为 700 万至 800 万部。",
                "第三季度出货量约为 50 万至 100 万部，约占苹果总出货量的 10%。",
            ],
        )

        events = module.cluster_articles(
            [
                macrumors_mac_ai,
                cnbeta_mac_ai,
                iphone_ultra_availability,
                foldable_supply,
                apple_foldable_phone_forecast,
            ]
        )
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertTrue(
            any({macrumors_mac_ai.title, cnbeta_mac_ai.title} == cluster for cluster in clusters),
            clusters,
        )
        self.assertFalse(
            any(
                macrumors_mac_ai.title in cluster
                and (
                    iphone_ultra_availability.title in cluster
                    or foldable_supply.title in cluster
                    or apple_foldable_phone_forecast.title in cluster
                )
                for cluster in clusters
            ),
            clusters,
        )


    def test_personal_usage_podcast_and_third_party_projects_stay_weak(self):
        module = load_module()
        samples = [
            (
                "Apple Watch sleep score became more useful for me with these settings",
                (
                    "Apple Watch includes a built-in sleep tracking feature. "
                    "On iPhone, go to the Watch app, swipe down to the Sleep section, then tap Sleep Score Notifications to toggle alerts."
                ),
                "9to5Mac",
            ),
            (
                "9to5Mac Overtime 071: A weird time for Apple",
                (
                    "9to5Mac Overtime is a weekly video-first podcast exploring observations in the Apple ecosystem. "
                    "Subscribe to Overtime via Apple Podcasts and YouTube."
                ),
                "9to5Mac",
            ),
            (
                "iPhone 17 Pro Max Sealed in Time Capsule Until 2276",
                (
                    "America250 sealed an iPhone 17 Pro Max inside a 250 year time capsule as part of America's Semiquincentennial celebrations. "
                    "The capsule will be reopened in 2276."
                ),
                "MacRumors",
            ),
            (
                "一位工程师自行为 MacBook Pro 升级 8TB 存储，但代价高昂过程坎坷",
                (
                    "一位 Reddit 工程师分享了为 MacBook Pro 自行更换 NAND 闪存并升级到 8TB SSD 的全过程。"
                    "他强调这需要焊接经验和专业工具，并不适合普通用户。"
                ),
                "cnBeta",
            ),
            (
                "《连线》编辑善用 iOS 17 辅助访问将 iPhone 13 变儿童手机：仅保留 6 款 App",
                (
                    "Wired 编辑利用 iOS 17 辅助访问功能把 iPhone 13 配置成儿童手机，"
                    "仅保留通话、信息、地图、相机、照片和音乐六款应用。"
                ),
                "IT之家",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                article = article_for(module, title, summary, source)
                self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_apple_broadcom_chip_supply_deal_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple and Broadcom Extend Chip Supply Deal to 2031",
                (
                    "Broadcom has agreed to extend its chip partnership with Apple through 2031, "
                    "expanding a deal that covers custom radio frequency components, Wi-Fi and Bluetooth connectivity, "
                    "and other networking semiconductors found throughout Apple's lineup."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "Apple-Broadcom renew partnership through 2031",
                (
                    "Apple has extended its long-time supplier agreement with Broadcom, ensuring Apple gets a steady flow "
                    "of custom chips until 2031. The deal includes custom ASIC products and wireless components."
                ),
                "AppleInsider",
            ),
            article_for(
                module,
                "博通、苹果续签多年期协议，双方技术合作延长至 2031 年",
                (
                    "Broadcom 向 SEC 递交 Form 8-K 报告，表示该企业已与 Apple 达成新的多年期协议，"
                    "将双方长久以来的技术合作进一步延长至 2031 年，涉及射频前端元件、无线组件和模块。"
                ),
                "IT之家",
            ),
            article_for(
                module,
                "苹果与博通将芯片供应合作延长至2031年",
                (
                    "据路透社报道，博通已同意将其与苹果的芯片合作伙伴关系延长至 2031 年，"
                    "扩展原有涵盖多种定制芯片开发与供应的长期协议。"
                ),
                "cnBeta",
            ),
            article_for(
                module,
                "Apple radio chips switch likely to take five more years, suggests Broadcom deal",
                (
                    "Reuters reports that Apple has agreed to retain and expand its partnership with Broadcom through 2031. "
                    "The deal suggests Apple's move to fully in-house radio chips may take five more years."
                ),
                "9to5Mac",
            ),
            article_for(
                module,
                "印度代工厂被黑 苹果最怕泄露的不是真机照片",
                (
                    "黑客组织声称泄露苹果印度供应商塔塔电子超过 20 万份文件，"
                    "其中包含 iPhone 18 Pro 主板设计、测试数据和工厂文件。"
                    "背景段落提到苹果也与博通、高通等供应商合作，但本文主事件不是 Broadcom 续约。"
                ),
                "快科技",
            ),
        ]

        events = module.cluster_articles(articles)
        broadcom_events = [
            event for event in events if any("Broadcom" in article.title or "博通" in article.title for article in event.articles)
        ]

        self.assertEqual(len(events), 2)
        self.assertEqual(len(broadcom_events), 1)
        self.assertEqual(
            {article.source for article in broadcom_events[0].articles},
            {"MacRumors", "AppleInsider", "IT之家", "cnBeta", "9to5Mac"},
        )

    def test_apple_tv_purchase_4k_upgrade_is_service_news(self):
        module = load_module()
        title = "Apple starts offering free 4K upgrades for purchased TV shows"
        summary = (
            "Apple is extending free 4K upgrades to select purchased TV shows in the Apple TV app "
            "and iTunes Store, after previously upgrading purchased movies at no additional charge."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "service_content")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_ios_beta_siri_ai_release_is_software_news(self):
        module = load_module()
        title = "iOS 27 beta 3 now available as Apple tests major Siri AI upgrade"
        summary = (
            "Apple has released the third iOS 27 beta for developer testing. "
            "The update continues testing Siri AI, Apple Intelligence, and new Apple Foundation Models. "
            "Other iPhone changes include smoother Camera behavior, continuous sending in Messages, "
            "custom EQ for AirPods, new recovery options, and easier Apple Pay card switching."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_third_party_app_launch_on_apple_platform_stays_weak(self):
        module = load_module()
        title = "腾讯 AI 生成应用 App“吐司”苹果 iOS 版上线，主打探索型 Vibe Coding"
        summary = (
            "腾讯 AI 生成应用 App“吐司”苹果 iOS 版上线，主打探索型 Vibe Coding。"
            "腾讯旗下 AI 应用生成平台“吐司”iOS 版已正式登陆 App Store。这款定位为探索型氛围编程的产品，"
            "让用户通过自然语言描述想法，AI 即可自动拆解功能、生成原型并打包成 App。"
            "安卓版本已在上个月推出。IT之家查询 App Store 页面获悉，这款应用大小 20.5MB，"
            "兼容 iOS 17.6、macOS 14.6 和 visionOS 1.3 或更高版本。"
        )
        article = article_for(module, title, summary, "IT之家")

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        events = module.cluster_articles([article])
        self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_non_apple_charity_donation_with_apple_purchase_context_stays_weak(self):
        module = load_module()
        title = "曾因买万元苹果电脑惹争议！韩红慈善基金会驰援广西 捐赠200万元救灾资金"
        summary = (
            "韩红爱心慈善基金会宣布驰援广西受灾地区，统筹调配 200 万元应急物资并捐赠专项善款。"
            "此前该基金会曾因购买万元苹果电脑引发争议，但本文主事件是慈善捐赠和救灾响应。"
        )
        article = article_for(module, title, summary, "快科技")

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        events = module.cluster_articles([article])
        self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_former_apple_commentary_without_new_apple_action_stays_weak(self):
        module = load_module()
        title = "Our choice of AI assistant really matters, says Tony Fadell"
        summary = (
            "Father of the iPod Tony Fadell wrote a lengthy column arguing that our choice of AI assistant matters. "
            "He points to the Mac, iPod, iPhone, and Nest as examples of behavior shifts, but the article does not report "
            "a new Apple product, service, policy, release, filing, or executive action."
        )
        article = article_for(module, title, summary, "9to5Mac")

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        events = module.cluster_articles([article])
        self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_current_apple_store_phrase_does_not_trigger_former_apple_commentary(self):
        module = load_module()
        title = "苹果定价创新高！iPhone Ultra起步价突破1.5万元：贵过MacBook Pro"
        summary = (
            "快科技7月10日消息，有博主发文爆料，苹果首款折叠屏手机将于9月份推出，"
            "起售价定为2300美元，折合人民币约为15600元。该博主表示，iPhone Ultra的定价已与"
            "MacBook Pro相当，但它并非市面上最好的折叠屏手机。按照2300美元的起售价计算，"
            "iPhone Ultra的价格已刷新苹果手机的定价纪录，几乎是iPhone 17 Pro Max（1199美元）的两倍。"
            "即便与苹果自家笔记本产品线相比，这一价格也超过了多款MacBook Pro；"
            "目前苹果官网在售的14英寸M5 MacBook Pro定价为1999美元，仍低于iPhone Ultra的起售价。"
        )

        self.assertFalse(module.is_former_apple_figure_commentary_without_new_apple_action(title, summary))
        self.assertTrue(module.is_future_apple_product_price_forecast_story(summary, title))
        article = article_for(module, title, summary, "快科技")
        self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)

    def test_future_iphone_price_forecast_has_price_boundary_facet(self):
        module = load_module()
        title = "苹果定价创新高！iPhone Ultra起步价突破1.5万元：贵过MacBook Pro"
        summary = (
            "快科技7月10日消息，有博主发文爆料，苹果首款折叠屏手机将于9月份推出，"
            "起售价定为2300美元，折合人民币约为15600元。按照2300美元的起售价计算，"
            "iPhone Ultra的价格已刷新苹果手机的定价纪录，几乎是iPhone 17 Pro Max（1199美元）的两倍。"
        )
        flatness = article_for(
            module,
            "iPhone Ultra平整度看齐OPPO Find N6：折痕近乎无感",
            (
                "博主定焦数码爆料，苹果首款折叠屏iPhone Ultra的屏幕平整度将达到与OPPO Find N6相当的水准。"
                "iPhone Ultra折叠屏的产业链与OPPO Find N6存在高度重合，目前已正式启动量产，新品将于9月正式发布。"
            ),
            "快科技",
        )
        price = article_for(module, title, summary, "快科技")

        facets = module.topic_facets_from_text(f"{title} {summary}")
        self.assertIn("apple-product-price-increase", facets)
        self.assertIn("apple-future-product-price-forecast", facets)
        self.assertFalse(module.should_merge(price, event_for(module, flatness)))
        self.assertFalse(module.should_merge(flatness, event_for(module, price)))

    def test_chinese_former_apple_commentary_without_new_action_stays_weak(self):
        module = load_module()
        title = "前苹果员工称 AI 助手选择会影响用户习惯"
        summary = (
            "前苹果员工在一篇专栏中表示，用户选择 AI 助手会影响长期使用习惯。文章提到 iPhone、"
            "Mac 和 Apple Watch 等产品作为历史案例，但没有报道新的 Apple 产品、服务、政策、发布、"
            "监管文件或高管动作。"
        )

        self.assertTrue(module.is_former_apple_figure_commentary_without_new_apple_action(title, summary))
        article = article_for(module, title, summary, "9to5Mac")
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_m6_chip_roadmap_merges_across_language_sources(self):
        module = load_module()
        english = article_for(
            module,
            "Apple’s M6 chip could skip many new products, here’s what’s rumored",
            (
                "Apple is expected to launch its next-generation M6 chip this fall, but rumors indicate the new chip could skip "
                "a number of products. Mark Gurman says Apple plans to ship only a base M6 chip, with no M6 Pro or M6 Max, "
                "as the company accelerates M7 for on-device AI."
            ),
            "9to5Mac",
        )
        chinese = article_for(
            module,
            "最“单薄”Mac 芯片系列：消息称苹果 M6 仅规划基础版，跳过 Mac mini 等多数产品线",
            (
                "9to5Mac 报道称苹果 M6 系列可能仅有 M6 标准版一款，后续预估不会推出 M6 Pro 和 M6 Max。"
                "M6 标准版可能采用 12 核 GPU，内存带宽提高到 200GB/s，Mac mini、iMac、Mac Studio "
                "和高端 MacBook Pro 大概率跳过 M6 升级到 M7。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([english, chinese])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家"})

    def test_iphone_logic_board_leak_merges_across_language_sources(self):
        module = load_module()
        cnbeta = article_for(
            module,
            "iPhone 18 Pro主板高清实物曝光：A20 Pro占用更大裸芯面积 高通5G基带",
            (
                "iPhone 18 Pro 与 iPhone 18 Pro Max 的主板实物图再次曝光，显示 A20 Pro 采用 WMCM 封装，"
                "DRAM 从堆叠式改为与 SoC 并排放置，并可能配合 96-bit LPDDR6 内存。图中 PMX75 标签被认为"
                "对应高通 Snapdragon X80 5G 基带。"
            ),
            "cnBeta",
        )
        ithome = article_for(
            module,
            "苹果 iPhone 18 Pro 逻辑板曝光：A20 Pro 芯片、LPDDR6 内存等",
            (
                "消息源分享 3 张图片，展示苹果 iPhone 18 Pro 系列高分辨率主板图片，进一步呈现 A20 Pro 芯片细节。"
                "A20 Pro 是苹果首款 2nm SoC，采用晶圆级多芯片模块封装，DRAM 移至芯片侧边，并再次提及 LPDDR6 内存。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([cnbeta, ithome])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"cnBeta", "IT之家"})

    def test_iphone_logic_board_leak_merges_despite_background_region_and_leak_facets(self):
        module = load_module()
        cnbeta = article_for(
            module,
            "iPhone 18 Pro主板高清实物曝光：A20 Pro占用更大裸芯面积 高通5G基带",
            (
                "iPhone 18 Pro 与 iPhone 18 Pro Max 的主板实物图再次曝光，显示 A20 Pro 采用 WMCM 封装，"
                "DRAM 与 SoC 并排放置，配合 LPDDR6 内存和高通 X80 5G 基带。文章还提到美国市场机型、"
                "Tata 数据泄露、折叠屏 iPhone 背景和散热调整。"
            ),
            "cnBeta",
        )
        ithome = article_for(
            module,
            "苹果 iPhone 18 Pro 逻辑板曝光：A20 Pro 芯片、LPDDR6 内存等",
            (
                "消息源分享 3 张图片，展示苹果 iPhone 18 Pro 系列高分辨率主板图片，A20 Pro 采用晶圆级多芯片模块封装，"
                "DRAM 移至芯片侧边，并再次提及 LPDDR6 内存。"
            ),
            "IT之家",
        )
        mydrivers = article_for(
            module,
            "iPhone 18 Pro主板图纸流传 华强北卖家称绝无可能复刻真机",
            (
                "大量标注机密标识的 iPhone 18 Pro 主板设计图纸、芯片参数与供应链清单流入市场，"
                "泄密源头指向苹果印度核心代工厂塔塔电子。图纸显示 A20 Pro、LPDDR6 内存和双层板结构，"
                "华强北卖家称难以复刻真机。"
            ),
            "快科技",
        )

        events = module.cluster_articles([cnbeta, ithome, mydrivers])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"cnBeta", "IT之家", "快科技"})
        self.assertEqual(events[0].merge_warnings, [])

    def test_iphone_battery_interpretation_merges_with_capacity_leak(self):
        module = load_module()
        filing = article_for(
            module,
            "iPhone 18 Pro Battery Capacities Revealed by Regulatory Filings",
            (
                "Chinese regulatory filings appear to confirm iPhone 18 Pro battery capacities: 4,056mAh in China and "
                "4,288mAh in the U.S., while iPhone 18 Pro Max is listed at 5,391mAh in China and 5,567mAh in the U.S."
            ),
            "MacRumors",
        )
        interpretation = article_for(
            module,
            "iPhone 18 Pro vs. iPhone 18 Pro Max: Here's What the Latest Leak Says",
            (
                "The latest leak says iPhone 18 Pro Max could take a bigger step forward in battery life. "
                "If the leaked capacities are accurate, the Pro Max battery would be nearly 10% larger than iPhone 17 Pro Max, "
                "while iPhone 18 Pro would increase by less than 1%."
            ),
            "MacRumors",
        )

        events = module.cluster_articles([filing, interpretation])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.title for article in events[0].articles}, {filing.title, interpretation.title})

    def test_wallet_car_key_story_is_not_airdrop_vulnerability(self):
        module = load_module()
        text = (
            "iOS 27 code points to Apple Wallet car key support for Lucid and Xiaomi. "
            "Apple car key lets drivers use iPhone or Apple Watch to lock, unlock, and start a car, "
            "and keys can be shared with Messages, Mail, and AirDrop. The implementation uses NFC and UWB secure communication."
        )

        self.assertTrue(module.is_apple_wallet_car_key_partner_support_story("iOS 27 car key support", text))
        self.assertFalse(module.is_airdrop_vulnerability_story(text))
        self.assertEqual(module.detect_event_kind("iOS 27 car key support", text), "wallet_feature")
        tier, reason = module.classify_relevance_tier("iOS 27 car key support", text)
        self.assertEqual(tier, "strong")
        self.assertIn("car key", reason.lower())

    def test_carplay_accessory_recommendations_are_cut_after_article_body(self):
        module = load_module()
        html = (
            "<article><p>Apple is preparing Apple Wallet car key support for Lucid and Xiaomi in iOS 27.</p>"
            "<p>Specific compatible car models and launch timing are not yet confirmed.</p>"
            "<h2>My favorite CarPlay accessories&nbsp;</h2>"
            "<ul><li>iOttie Easy One Touch iPhone Car Mount</li>"
            "<li>Belkin MagSafe-compatible Car Charger for iPhone</li></ul></article>"
        )

        cleaned = module.strip_tags(module.remove_noise_blocks(html))
        self.assertIn("Apple Wallet car key support", cleaned)
        self.assertNotIn("iOttie Easy One Touch", cleaned)
        self.assertNotIn("Belkin MagSafe-compatible", cleaned)

    def test_apple_tv_4k_hardware_refresh_is_hardware_category(self):
        module = load_module()
        title = "Everything Coming in the 2026 Apple TV 4K"
        summary = (
            "Apple's next Apple TV 4K set-top box is expected to launch in 2026 with an updated chip, "
            "a newer wireless chip, and support for Siri AI features after iOS 27."
        )

        self.assertTrue(module.is_apple_tv_hardware_story(f"{title} {summary}"))
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_apple_tv_lineup_and_trailer_are_separate_service_events(self):
        module = load_module()
        comic_macrumors = article_for(
            module,
            "Apple TV Taking Over Comic-Con's Hall H for the First Time With Widow's Bay, Silo and More",
            (
                "Apple TV+ announced a major San Diego Comic-Con Hall H lineup with panels for Silo, "
                "Dark Matter, For All Mankind, Monarch, and the new series Widow's Bay."
            ),
            "MacRumors",
        )
        comic_9to5 = article_for(
            module,
            "Apple TV+ sets major Comic-Con lineup with Silo, Dark Matter, Widow's Bay, more",
            (
                "Apple TV+ will bring Silo, Dark Matter, For All Mankind, Monarch, and Widow's Bay "
                "to San Diego Comic-Con as part of a Hall H panel lineup."
            ),
            "9to5Mac",
        )
        snoopy = article_for(
            module,
            "Apple TV+ shares first trailer for There's No Place Like Home, Snoopy",
            "Apple TV+ shared the first trailer for the new Peanuts special There's No Place Like Home, Snoopy.",
            "9to5Mac",
        )

        self.assertEqual(module.detect_event_kind(comic_9to5.title, comic_9to5.summary), "service_content")
        self.assertEqual(module.detect_event_kind(snoopy.title, snoopy.summary), "service_content")
        events = module.cluster_articles([comic_macrumors, comic_9to5, snoopy])
        self.assertEqual(len(events), 2)
        comic_events = [event for event in events if any("Comic-Con" in article.title for article in event.articles)]
        self.assertEqual(len(comic_events), 1)
        self.assertEqual({article.source for article in comic_events[0].articles}, {"MacRumors", "9to5Mac"})
        snoopy_events = [event for event in events if any("Snoopy" in article.title for article in event.articles)]
        self.assertEqual(len(snoopy_events), 1)
        self.assertEqual({article.source for article in snoopy_events[0].articles}, {"9to5Mac"})

    def test_apple_tv_4k_chip_and_networking_roadmap_is_hardware(self):
        module = load_module()
        title = "苹果 2026 款 Apple TV 4K 前瞻：A17 Pro 芯片、支持 Siri AI 和 Wi-Fi 7"
        summary = (
            "苹果有望发布 2026 款 Apple TV 4K，升级 A17 Pro 芯片，支持 Apple Intelligence "
            "和 Siri AI，并可能搭载 N1 网络芯片，引入 Wi-Fi 7、蓝牙 6.0、Thread 和新 Siri Remote。"
        )

        self.assertTrue(module.is_apple_tv_hardware_story(f"{title} {summary}"))
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "strong", reason)

    def test_apple_tv_mlb_schedule_merges_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Apple TV and MLB Release August Schedule for Friday Night Baseball",
            "Apple and Major League Baseball released the August schedule for Friday Night Baseball on Apple TV+.",
            "MacRumors",
        )
        nine = article_for(
            module,
            "Apple TV unveils August Friday Night Baseball schedule",
            "Apple TV+ announced August games for Friday Night Baseball, with MLB matchups streaming on Apple TV+.",
            "9to5Mac",
        )
        newsroom = article_for(
            module,
            "Apple and Major League Baseball announce August Friday Night Baseball schedule",
            "Apple and Major League Baseball announced the August Friday Night Baseball schedule for Apple TV+ subscribers.",
            "Apple Newsroom",
        )

        events = module.cluster_articles([macrumors, nine, newsroom])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "9to5Mac", "Apple Newsroom"})

    def test_siri_ai_settlement_merges_across_sources(self):
        module = load_module()
        macrumors = article_for(
            module,
            "'Siri AI' Lawsuit Update: Apple to Pay Owners of These iPhone Models",
            (
                "Apple agreed to pay $250 million to settle a U.S. class action lawsuit over Siri AI's delayed launch. "
                "Eligible iPhone 15 Pro and iPhone 16 owners can receive $25 per device, or up to $95 if fewer claims are filed."
            ),
            "MacRumors",
        )
        mydrivers = article_for(
            module,
            "Siri AI功能虚假宣传！苹果要支付17亿天价赔偿：iPhone 16/15 Pro每人645元",
            (
                "苹果已达成2.5亿美元集体诉讼和解协议，以解决 iPhone 16 系列宣传的 Siri AI 功能延迟上线纠纷。"
                "本次补偿面向美国境内购入 iPhone 15 Pro、iPhone 15 Pro Max 以及 iPhone 16 全系机型的消费者。"
            ),
            "快科技",
        )

        events = module.cluster_articles([macrumors, mydrivers])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "快科技"})

    def test_india_tariff_exemption_merges_without_absorbing_iphone_costs(self):
        module = load_module()
        tariff_articles = [
            article_for(
                module,
                "Apple's Manufacturing in India Gets Boost From New Tariff Exemptions",
                "India removed import duties of 7.5% and 5% on smartphone and electronics parts, helping Apple lower iPhone manufacturing costs through March 31, 2029.",
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone manufacturing in India gets a tariff boost",
                "India removed tariffs on select parts used in smartphones and other devices, including wireless charging modules and lithium-ion battery cells, helping Apple suppliers.",
                "9to5Mac",
            ),
            article_for(
                module,
                "印度取消部分手机及电子设备零部件进口关税，利好苹果、小米等厂商",
                "印度已取消部分手机及其他电子设备零部件的进口关税，免除了此前 7.5% 和 5% 的税率，有望帮助苹果进一步降低制造成本。",
                "IT之家",
            ),
            article_for(
                module,
                "印度取消部分电子产品及智能手机零部件进口关税",
                "印度政府取消部分用于制造手机及其他电子设备的进口关税，预计将使苹果、小米等在印布局的电子厂商获益，有效期至 2029 年 3 月 31 日。",
                "cnBeta",
            ),
        ]
        cost_article = article_for(
            module,
            "iPhone 18 Pro Max component costs could jump by nearly $300",
            "Counterpoint estimates that NAND, DRAM, a 2nm SoC, and new packaging will push the iPhone 18 Pro Max bill of materials much higher.",
            "9to5Mac",
        )

        self.assertEqual(tariff_articles[-1].relevance_tier, "strong", tariff_articles[-1].relevance_reason)
        events = module.cluster_articles([*tariff_articles, cost_article])
        tariff_events = [event for event in events if any("tariff" in article.title.lower() or "关税" in article.title for article in event.articles)]
        self.assertEqual(len(tariff_events), 1)
        self.assertEqual({article.source for article in tariff_events[0].articles}, {"MacRumors", "9to5Mac", "IT之家", "cnBeta"})
        cost_events = [event for event in events if any("component costs" in article.title for article in event.articles)]
        self.assertEqual(len(cost_events), 1)
        self.assertEqual({article.source for article in cost_events[0].articles}, {"9to5Mac"})

    def test_prismml_on_device_ai_story_is_strong_software_and_merges(self):
        module = load_module()
        macrumors = article_for(
            module,
            "Apple Exploring Ways to Run Much Larger AI Models Directly on iPhones",
            "Apple is exploring PrismML compression technology to run much larger Apple Intelligence models directly on iPhones.",
            "MacRumors",
        )
        ithome = article_for(
            module,
            "已在 iPhone 17 Pro 上完整运行 Qwen 3.6，消息称 PrismML 模型 AI 压缩技术被苹果看中",
            (
                "The Information 报道称苹果公司正接洽 PrismML 初创公司，评估在 iPhone 上直接运行更大规模 AI 模型的可行性。"
                "PrismML 的 1-bit 模型压缩技术可将模型体积压缩至全精度版本的 1/14，内存占用降低超 90%。"
            ),
            "IT之家",
        )

        self.assertEqual(ithome.relevance_tier, "strong", ithome.relevance_reason)
        self.assertEqual(ithome.category, "software_systems")
        events = module.cluster_articles([macrumors, ithome])
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_on_device_ai_model_story_does_not_merge_with_wallet_id_event(self):
        module = load_module()
        wallet = article_for(
            module,
            "Apple Says iPhone Driver's Licenses Will Expand to These 6 U.S. States",
            (
                "In select U.S. states, residents can add a driver's license or state ID "
                "to the Apple Wallet app on the iPhone and Apple Watch. Apple Wallet IDs "
                "are accepted at TSA checkpoints in more than 250 airports."
            ),
            "MacRumors",
        )
        prism_9to5 = article_for(
            module,
            "Apple interested in startup that runs giant AI models on iPhone without servers",
            (
                "The startup PrismML said it has shrunk down Qwen 3.6, an open-source model "
                "with 27 billion parameters, so it can run directly on iPhone without servers."
            ),
            "9to5Mac",
        )
        prism_macrumors = article_for(
            module,
            "Apple Exploring Ways to Run Much Larger AI Models Directly on iPhones",
            "Apple is exploring PrismML compression technology to run much larger Apple Intelligence models directly on iPhones.",
            "MacRumors",
        )

        self.assertEqual(prism_9to5.relevance_tier, "strong", prism_9to5.relevance_reason)
        self.assertIn("apple-on-device-ai-model-compression", module.primary_topic_facets(prism_9to5.title, prism_9to5.summary))
        self.assertFalse(module.should_merge(prism_9to5, event_for(module, wallet)))
        events = module.cluster_articles([wallet, prism_9to5, prism_macrumors])
        wallet_events = [event for event in events if any("Driver's Licenses" in article.title for article in event.articles)]
        prism_events = [event for event in events if any("PrismML" in article.summary or "giant AI models" in article.title for article in event.articles)]
        self.assertEqual(len(wallet_events), 1)
        self.assertEqual({article.source for article in wallet_events[0].articles}, {"MacRumors"})
        self.assertEqual(len(prism_events), 1)
        self.assertEqual({article.source for article in prism_events[0].articles}, {"9to5Mac", "MacRumors"})

    def test_iphone_18_pro_max_weight_and_component_costs_merge_separately(self):
        module = load_module()
        weight_sources = [
            article_for(
                module,
                "iPhone 18 Pro Max Said to Be Thicker and Heavier Than Predecessor",
                "Ice Universe claims the iPhone 18 Pro Max will be around 9mm thick and weigh about 240 grams because of a larger battery.",
                "MacRumors",
            ),
            article_for(
                module,
                "Rumored iPhone 18 Pro Max specs point to Apple's heaviest iPhone in years",
                "A new leak says the iPhone 18 Pro Max could be heavier and larger, with a 5,500 mAh battery and weight around 240 grams.",
                "9to5Mac",
            ),
        ]
        cost_sources = [
            article_for(
                module,
                "iPhone 18 Pro Max component costs could jump by nearly $300",
                "Counterpoint estimates that NAND, DRAM, a 2nm SoC, and new packaging will push the iPhone 18 Pro Max bill of materials much higher.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Price rises certain as iPhone 18 Pro Max component costs soar",
                "Memory and storage prices are driving up iPhone 18 Pro Max component costs, with NAND above $250 and combined DRAM and NAND about $400.",
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles([*weight_sources, *cost_sources])
        weight_events = [event for event in events if any("heavier" in article.title.lower() or "heaviest" in article.title.lower() for article in event.articles)]
        cost_events = [event for event in events if any("component costs" in article.title.lower() or "costs soar" in article.title.lower() for article in event.articles)]
        self.assertEqual(len(weight_events), 1)
        self.assertEqual({article.source for article in weight_events[0].articles}, {"MacRumors", "9to5Mac"})
        self.assertEqual(len(cost_events), 1)
        self.assertEqual({article.source for article in cost_events[0].articles}, {"9to5Mac", "AppleInsider"})
        self.assertEqual(len(events), 2)

    def test_android_memory_market_commentary_stays_weak_after_event_refresh(self):
        module = load_module()
        article = article_for(
            module,
            "Memory prices are bad news for Android brands but may help Apple",
            (
                "Omdia says memory costs have become a serious burden for Android smartphones below $400, "
                "with that market segment declining more than 22% year over year. The article argues that "
                "higher Android prices could make entry-level iPhones look more appealing, but it does not "
                "report a new Apple shipment, production, price, or supplier action."
            ),
            "9to5Mac",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        events = module.cluster_articles([article])
        self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_third_party_ipad_stylus_is_weak_without_apple_action(self):
        module = load_module()
        title = "纸张、iPad 皆可书写：ELECOM 联手 Zebra 推出 STYLUS 2WAY 双功能笔"
        summary = (
            "日本硬件制造商 ELECOM 联手文具制造商 Zebra 推出 STYLUS 2WAY 笔。"
            "这一第三方设备采用独特结构设计，在纸张和苹果 iPad 平板电脑上均可书写，"
            "并支持磁吸固定和 7 小时续航。"
        )

        self.assertTrue(module.is_third_party_accessory_platform_compatibility_story(title, summary))
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "weak", reason)

    def test_apple_pencil_patent_is_not_downgraded_as_third_party_stylus(self):
        module = load_module()
        title = "苹果 Apple Pencil 新专利获批：“预见”手写笔姿态，支持旋转交互"
        summary = (
            "苹果一项 Apple Pencil 新专利获批，可在触控笔接近屏幕前预判姿态，"
            "并支持旋转交互和更细粒度的输入控制。"
        )

        self.assertFalse(module.is_third_party_accessory_platform_compatibility_story(title, summary))
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "strong", reason)

    def test_conflicting_discovery_summary_does_not_override_detail_topic(self):
        module = load_module()
        cost_title = "A20 Pro、存储是主因！iPhone 18 Pro Max硬件成本暴涨2000元：苹果还要混用TLC、QLC"
        cost_summary = (
            "Counterpoint 预计 iPhone 18 Pro Max 的 12GB+1TB 顶配版本综合硬件成本"
            "相比上一代上涨近 300 美元，主要来自 NAND、DRAM 和 A20 Pro 芯片成本。"
        )
        signing_discovery_summary = (
            "Apple has stopped signing several older versions of iOS for legacy iPhone and iPad models, "
            "cutting off paths to reinstall or downgrade affected software."
        )
        wallet_title = "Apple Says iPhone Driver's Licenses Will Expand to These 6 U.S. States"
        wallet_summary = (
            "In select U.S. states, residents can add their driver's license or state ID to the Apple Wallet app "
            "on the iPhone and Apple Watch, then use it to display proof of identity or age."
        )
        foldable_discovery_summary = (
            "苹果首款折叠屏手机 iPhone Ultra 白色版机模亮相，传闻搭载 A20 Pro 芯片、12GB 内存，"
            "首批产能可能紧张。"
        )

        self.assertTrue(
            module.discovery_text_conflicts_with_detail_topic(
                cost_title,
                cost_summary,
                signing_discovery_summary,
            )
        )
        self.assertEqual(
            module.safe_combine_detail_and_discovery_summary(
                cost_title,
                cost_summary,
                signing_discovery_summary,
            ),
            cost_summary,
        )
        self.assertTrue(
            module.discovery_text_conflicts_with_detail_topic(
                wallet_title,
                wallet_summary,
                foldable_discovery_summary,
            )
        )
        self.assertEqual(
            module.safe_context_for_detail_article(False, wallet_title, wallet_summary, foldable_discovery_summary),
            "",
        )

    def test_wallet_drivers_license_has_digital_id_topic_boundary(self):
        module = load_module()
        title = "Apple Says iPhone Driver's Licenses Will Expand to These 6 U.S. States"
        summary = (
            "In select U.S. states, residents can add their driver's license or state ID to the Apple Wallet app "
            "on the iPhone and Apple Watch, then use it to display proof of identity or age."
        )

        facets = module.topic_boundary_facets_for_text(title, summary)

        self.assertIn("apple-wallet-digital-id", facets)

    def test_incompatible_background_facts_are_filtered_from_primary_event(self):
        module = load_module()
        title = "关键零部件免税：苹果印度制造 iPhone 成本直线下降"
        summary = (
            "印度取消用于制造智能手机及其他电子产品的多种零部件进口关税，"
            "此前 7.5% 和 5% 的税率将被免除，政策预计持续至 2029 年 3 月 31 日。"
        )
        facts = [
            "报道称这些关税豁免政策有效期将持续至2029年3月31日，预计将使包括苹果在内的多家手机制造商受益。",
            "泄露内容涵盖iPhone 18 Pro系列的数百种零部件明细及供应商清单、主板设计图纸、A20 Pro芯片数据手册，以及工厂内拍摄的新机跌落测试视频。",
        ]

        filtered = module.filter_key_facts_for_primary_topic(title, summary, facts)

        self.assertEqual(filtered, [facts[0]])

    def test_hardware_rumor_supporting_facts_are_not_filtered(self):
        module = load_module()
        title = "A20 Pro、存储是主因！iPhone 18 Pro Max硬件成本暴涨2000元：苹果还要混用TLC、QLC"
        summary = (
            "Counterpoint 预计 iPhone 18 Pro Max 的 12GB+1TB 顶配版本综合硬件成本"
            "相比上一代上涨近 300 美元。"
        )
        facts = [
            "同规格256GB NAND闪存的采购成本涨幅达到了80%至90%，占这次整机成本增量的最大比例。",
            "iPhone 18 Pro全系列预计都会搭载台积电独家2nm工艺制程打造的A20 Pro芯片，单片晶圆报价接近3万美元。",
        ]

        self.assertEqual(module.filter_key_facts_for_primary_topic(title, summary, facts), facts)

    def test_macrumors_political_forum_notice_is_not_key_fact(self):
        module = load_module()
        notice = (
            "Note: Due to the political or social nature of the discussion regarding this topic, "
            "the discussion thread is located in our Political News forum."
        )

        self.assertTrue(module.fact_noise(notice))

    def test_direct_apple_regulated_technology_access_story_is_selected(self):
        module = load_module()
        source = source_named(module, "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url=(
                "https://9to5mac.com/2026/07/10/us-eases-restrictions-on-apples-access-to-ai-chips-"
                "and-data-center-equipment-in-the-uae/"
            ),
            title="US eases restrictions on Apple's access to AI chips and data center equipment in the UAE",
            summary=(
                "Apple is among eight U.S. companies now able to bring advanced-computing chips, servers, "
                "and controlled technology into the UAE without individual export licenses."
            ),
            feed_time_raw="Fri, 10 Jul 2026 18:10:28 +0000",
            context="aapl",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(
            module.detect_event_kind(candidate.title, candidate.summary, [candidate.context]),
            "regional_regulation",
        )
        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [candidate.context],
            candidate.source,
        )
        self.assertEqual(tier, "strong", reason)
        self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 90)

    def test_current_macrumors_os_component_guide_ignores_body_third_party_context(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/guide/ios-27-mail/",
            title="iOS 27: What's New With the Mail App",
            summary=(
                "Apple's Mail app gets relevance-ranked search, Ask Siri, Writing Tools, Call Context, "
                "and contextual suggestions in iOS 27. Contextual suggestions are also available to "
                "third-party apps. Related Roundups: iOS 27, iPadOS 27."
            ),
            feed_time_raw="Fri, 10 Jul 2026 15:26:16 PDT",
            context="featured ios 27",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(
            module.detect_event_kind(candidate.title, candidate.summary, [candidate.context]),
            "os_app",
        )
        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [candidate.context],
            candidate.source,
        )
        self.assertEqual(tier, "strong", reason)
        self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 70)

    def test_watchos_builtin_app_removal_is_strong_despite_opinion_framing(self):
        module = load_module()
        title = "Will you miss the Walkie-Talkie Apple Watch app when watchOS 27 drops push-to-talk?"
        summary = (
            "Apple Watch is losing its built-in Walkie-Talkie app in watchOS 27. The system-level "
            "push-to-talk feature will disappear, and a third-party app might eventually fill the gap. "
            "Related iOS stories discuss third-party iPhone apps, app updates, and Apple Watch features."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
        self.assertEqual(tier, "strong", reason)
        self.assertIn("built-in-app-change", module.primary_topic_facets(title, summary))

    def test_builtin_app_changes_on_different_os_platforms_do_not_merge(self):
        module = load_module()
        messages = article_for(
            module,
            "These are my favorite new Messages features in iOS 27 [Video]",
            "iOS 27 makes the built-in Messages app faster and adds new Siri and drawing features.",
            source="9to5Mac",
        )
        walkie_talkie = article_for(
            module,
            "Will you miss the Walkie-Talkie Apple Watch app when watchOS 27 drops push-to-talk?",
            "Apple Watch is losing its built-in Walkie-Talkie app in watchOS 27.",
            source="9to5Mac",
        )

        messages_event = module.cluster_articles([messages])[0]
        self.assertFalse(
            module.topic_facets_compatible(
                walkie_talkie,
                messages_event,
                walkie_talkie.tokens & messages_event.tokens,
                module.jaccard(walkie_talkie.tokens, messages_event.tokens),
            )
        )

        events = module.cluster_articles([messages, walkie_talkie])

        self.assertEqual(len(events), 2)

    def test_foldable_iphone_battery_aliases_merge_but_eu_battery_rule_stays_separate(self):
        module = load_module()
        battery_articles = [
            article_for(
                module,
                "苹果 iPhone Ultra 阔折叠？消息称苹果供应商入网备案 4883mAh 电池",
                "两块电芯额定容量为 1921mAh 和 2962mAh，合计 4883mAh，可能用于苹果首款折叠屏 iPhone。",
                source="IT之家",
            ),
            article_for(
                module,
                "Foldable iPhone Ultra Battery Capacity Allegedly Registered by Supplier",
                "Apple's supplier registered 1,921mAh and 2,962mAh cells for a combined 4,883mAh foldable iPhone battery.",
                source="MacRumors",
            ),
            article_for(
                module,
                "iPhone Fold将采用双电池设计 但容量恐怕要让你失望了",
                "消息透露苹果首款折叠屏手机采用 1921mAh 和 2962mAh 双电池，合计 4883mAh。",
                source="快科技",
            ),
        ]
        regulation_articles = [
            article_for(
                module,
                "报道称欧版苹果 iPhone 18 Pro 豁免欧盟新规，不会改为可拆卸电池",
                (
                    "欧盟 Commission Regulation (EU) 2023/1670 将于 2027 年执行；满足 500 次循环保留 "
                    "83% 容量、1000 次保留 80% 容量的设备可豁免普通用户可拆卸电池要求。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "No, EU iPhones won't have a removable battery door in 2027",
                (
                    "European Union battery legislation takes effect in 2027, but qualifying iPhones are exempt "
                    "from the user-replaceable battery requirement."
                ),
                source="AppleInsider",
            ),
        ]

        events = module.cluster_articles([*battery_articles, *regulation_articles])

        self.assertEqual(len(events), 2)
        capacity_event = next(event for event in events if len(event.articles) == 3)
        regulation_event = next(event for event in events if len(event.articles) == 2)
        self.assertEqual(capacity_event.relevance_tier, "strong")
        self.assertEqual(regulation_event.event_kind, "hardware_market")
        self.assertIn("apple-device-battery-regulation", module.event_primary_facets(regulation_event))
        self.assertNotIn("iphone-battery-capacity-leak", module.event_primary_facets(regulation_event))

        cnbeta_candidate = module.Candidate(
            source="cnBeta",
            url="https://www.cnbeta.com.tw/articles/tech/example.htm",
            title="iPhone 依然不会改变其目前的不可拆卸电池设计",
            summary=(
                "欧盟 2027 年电池法规允许满足循环寿命标准的 iPhone 豁免可拆卸电池要求；"
                "文章末尾以任天堂 Switch 2 作为不符合豁免条件的对照。"
            ),
        )
        self.assertTrue(module.is_relevant_candidate(cnbeta_candidate, source_named(module, "cnBeta")))

    def test_same_foldable_iphone_mockup_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果首款折叠手机：白色版 iPhone Ultra 机模曝光",
                "TheAppleHub 分享白色 iPhone Ultra 折叠机机模视频，中间有明显折痕。",
                source="IT之家",
            ),
            article_for(
                module,
                "9月发布！苹果首款折叠手机 iPhone Ultra 白色版机模亮相：折痕明显",
                "海外博主展示同一白色折叠 iPhone 机模，零售版据称会改善折痕。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_openai_trade_secret_lawsuit_merges_sues_wording_and_data_theft_details(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple sues OpenAI & previous VP of product design over mass IP theft",
                "Apple filed suit alleging former employees stole trade secrets and supplied them to OpenAI.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "苹果起诉 OpenAI，指控其挖角前员工窃取未发布产品、供应链资料等商业机密",
                "苹果向法院起诉 OpenAI，称前员工窃取商业秘密、未发布产品和供应链资料。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "legal_antitrust")

    def test_same_iphone_production_forecast_merges_despite_cost_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Reportedly Slashes iPhone 17 Demand Forecast Amid Rising Costs",
                (
                    "A Chinese leaker says some standard iPhone 17 lines moved from a 15% reduction to "
                    "suspending roughly one-third of capacity."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "成本上涨太恐怖！苹果部分产线砍掉iPhone 17三分之一产能",
                (
                    "消息称标准版iPhone 17部分产线从减产 15% 调整为暂停三分之一产能；"
                    "DRAM、NAND 与 A19 成本上涨构成背景，苹果在美国的回应解释了成本压力。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_direct_apple_market_share_report_is_not_downgraded_by_comparisons(self):
        module = load_module()
        title = "Apple Watch Accounts for 90% of AI Smartwatch Shipments"
        summary = (
            "Counterpoint says Apple accounted for roughly 90% of Edge AI smartwatch shipments in Q1 2026, "
            "where artificial intelligence runs directly on the wearable, "
            "while Huawei followed with comparable silicon, Qualcomm is entering the race, and Google is "
            "preparing a Tensor wearable chip. This remains niche compared to Apple's dedicated-chip strategy."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "strong", reason)

        english = article_for(module, title, summary, source="MacRumors")
        chinese = article_for(
            module,
            "苹果 Apple Watch 在边缘 AI 智能手表市场首季出货量独占九成",
            (
                "Counterpoint 报告显示，Apple Watch 占 2026 年第一季度 Edge AI 智能手表出货量约 90%，"
                "该市场同比增长 70%、渗透率达到 25%；研究报告还介绍了本地心率、健康与安全推理场景。"
            ),
            source="cnBeta",
        )

        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)

    def test_third_party_desktop_client_update_does_not_become_apple_hardware_news(self):
        module = load_module()
        title = "微信 Win / Mac PC 测试版 4.1.12 发布：通话中可接听新来电，支持 Markdown 排版"
        summary = (
            "微信团队面向 PC 版内测用户推送 4.1.12 更新，支持通话中接听新来电，"
            "并为桌面版笔记新增 Markdown 标题、加粗、列表和待办事项排版。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)

    def test_rumor_feature_recap_without_new_reporting_is_weak(self):
        module = load_module()
        examples = [
            (
                "Apple to Launch 'MacBook Ultra' With Up to Six New Features",
                "This roundup recaps six previously reported rumored features and contains no new reporting.",
            ),
            (
                "iPhone 18 Pro Coming Soon With These 10 New Features",
                "Below, we have recapped 10 features rumored for the iPhone 18 Pro models as of July.",
            ),
            (
                "苹果秋季发布会锁定9月份：史上最大规模新品潮有何看点",
                "文章汇总此前传闻，盘点秋季发布会可能出现的 16 款产品，没有新增消息。",
            ),
        ]

        for title, summary in examples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
                self.assertEqual(tier, "weak", reason)

    def test_personal_os_feature_walkthrough_is_weak_without_a_new_standalone_action(self):
        module = load_module()
        title = "These are my favorite new Messages features in iOS 27 [Video]"
        summary = (
            "A hands-on walkthrough highlights four favorite quality-of-life features already included "
            "in the iOS 27 Messages app."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_chip_tariff_exemption_merges_hardware_and_regulatory_angles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "WSJ: Apple avoided semiconductor tariffs thanks to Intel chip deal",
                (
                    "Apple reportedly committed to use Intel's U.S. foundries for some future chips, "
                    "helping the company secure an exemption from 100% semiconductor tariffs."
                ),
                source="9to5Mac",
            ),
            article_for(
                module,
                "美国政府施压：苹果同意让英特尔代工部分芯片，换取半导体关税豁免",
                (
                    "报道称苹果承诺采用英特尔美国晶圆厂生产部分 iPhone 和 Mac 芯片，"
                    "并因此获得美国政府的半导体关税豁免。"
                ),
                source="IT之家",
            ),
            article_for(
                module,
                "Apple's 100% tariff exemption may have been helped by Intel supply deal",
                (
                    "Apple's Intel chip-production agreement reportedly helped persuade the U.S. government "
                    "to exempt the company from 100% semiconductor tariffs."
                ),
                source="AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家", "AppleInsider"})

    def test_lawsuit_response_merges_with_same_case_background_before_topic_guards(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "OpenAI Responds After Being Sued by Apple",
                (
                    "OpenAI responded to Apple's lawsuit alleging that former employees stole trade secrets "
                    "for its AI hardware work. The company denied seeking Apple's confidential information."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果与 OpenAI 反目始末：人才挖角如何演变为法律大战？",
                (
                    "报道回顾苹果起诉 OpenAI 的同一商业秘密案件，称前员工利用漏洞访问内部文件，"
                    "复制 iPhone 资料，并补充 io Products 收购、AI 设备、原型电池、逻辑板和"
                    "硬件团队的案件背景。"
                ),
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "legal_antitrust")

    def test_multi_product_preview_and_buying_roundup_is_weak(self):
        module = load_module()
        title = "九月苹果新品前瞻！iPhone 万元起步，史上最贵"
        summary = (
            "文章汇总 iPhone、折叠 iPhone、Mac、Apple Watch 等此前传闻，并按预算、"
            "价格和使用场景给出购买建议，没有苹果发布或新的独立信源。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_apple_work_first_person_usage_column_is_weak_without_new_action(self):
        module = load_module()
        title = "Apple @ Work: The M1 MacBook Air has the longest usable lifespan of any Apple laptop"
        summary = (
            "The author explains why I still keep 30 to 40 five-year-old M1 MacBook Air units as daily "
            "loaners and recommends that IT teams retain them instead of recycling them."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_ai_generated_apple_product_photo_debunk_is_weak(self):
        module = load_module()
        title = "演员手持折叠 iPhone 照片刷屏，多处破绽显示系 AI 生成"
        summary = (
            "网友指出照片中的屏幕宽度和机身细节不一致，判断这是一张 AI 生成的伪造照片；"
            "正文随后复述此前流传的 iPhone Ultra 规格传闻，没有苹果行动或新的独立爆料。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_chip_roadmap_memory_capacity_research_transfer_and_process_node_stay_separate(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Here's Why Apple is Reportedly Skipping M6 Pro and M6 Max Chips",
                (
                    "Apple will release only the base M6 before moving to M7 six months later. "
                    "M6 Pro, M6 Max, and M6 Ultra are reportedly cancelled so Apple can accelerate "
                    "the AI-focused M7 generation."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "M6 era will last just six months as Apple pushes for AI-focused M7",
                (
                    "Apple's base M6 is expected in late 2026, followed by M7 in early 2027. "
                    "The report says there will be no M6 Pro, M6 Max, or M6 Ultra."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "Apple's M7 Ultra Chip Designed to Match a 2019 Mac Pro Feat",
                (
                    "The M7 Ultra chip is designed to support up to 1.5TB of unified memory, "
                    "although the final configuration depends on memory supply."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "M7 Ultra to potentially feature up to 1.5TB of RAM",
                "Apple is preparing an M7 Ultra configuration with up to 1.5TB of unified memory.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Power of Apple's M7 & M8 chips was born from Apple Car research",
                (
                    "Research from Apple's cancelled car project is reportedly being reused in the "
                    "AI design of future M7 and M8 chips for Macs and Apple Intelligence servers."
                ),
                source="AppleInsider",
            ),
            article_for(
                module,
                "苹果 M7 与 M8 芯片的性能被指源自此前造车项目研究",
                "苹果把自动驾驶项目积累的研究成果转化到 M7 和 M8 芯片的 AI 架构设计中。",
                source="cnBeta",
            ),
            article_for(
                module,
                "Apple M8 Chips Expected to Use TSMC's 1.4nm Process",
                "Apple is developing M8 chips expected to use TSMC's 1.4nm process in 2028.",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)
        clusters = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 4, clusters)
        self.assertTrue(any({articles[0].title, articles[1].title} <= cluster for cluster in clusters), clusters)
        self.assertTrue(any({articles[2].title, articles[3].title} <= cluster for cluster in clusters), clusters)
        self.assertTrue(any({articles[4].title, articles[5].title} <= cluster for cluster in clusters), clusters)
        self.assertFalse(any(articles[0].title in cluster and articles[2].title in cluster for cluster in clusters), clusters)

    def test_direct_m6_lineup_report_is_strong_hardware_news(self):
        module = load_module()
        title = "Here's Why Apple is Reportedly Skipping M6 Pro and M6 Max Chips"
        summary = (
            "Apple will release a base M6 chip but no M6 Pro, M6 Max, or M6 Ultra, then move "
            "to the AI-focused M7 generation six months later."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(tier, "strong", reason)

    def test_apple_store_employee_iphone_deployment_is_hardware_and_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Stores to Expand Use of 'Tap to Pay on iPhone'",
                (
                    "Apple will give more retail employees iPhone 16 units to replace iPhone 14 "
                    "and dedicated Bluetooth card readers for in-store Tap to Pay. iOS 27 also "
                    "adds Tap to Share."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果开始向更多直营店员工配发 iPhone 16，优化 Tap to Pay 体验",
                "苹果将向更多 Apple Store 员工配发 iPhone 16，并逐步淘汰旧读卡器。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "retail_store")
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_same_new_apple_pencil_report_merges_despite_battery_regulation_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Two New Apple Pencils Reportedly Launching Next Year",
                (
                    "Apple is developing new USB-C Apple Pencil and Apple Pencil Pro models for "
                    "the next iPad Pro, with a new battery system linked to EU requirements."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "古尔曼：苹果明年春季推出新款 Apple Pencil，与下一代 iPad Pro 同步发布",
                (
                    "两款新 Apple Pencil 代号 B582 和 B632，预计采用新的可维修电池系统；"
                    "现款此前已在美国上市。"
                ),
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_crime_blotter_is_weak_when_apple_devices_are_only_evidence_or_stolen_goods(self):
        module = load_module()
        title = "Crime blotter: Stolen iPad leads to arrest of accused bank robber"
        summary = (
            "A weekly crime roundup covers a stolen iPad tracked by police, school iPads taken "
            "during a burglary, and counterfeit AirPods offered to officers."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_advice_led_back_to_school_article_is_weak_without_independent_offer_terms(self):
        module = load_module()
        title = "Assess Apple's imminent Back to School sales, before you pull the trigger on a bad deal"
        summary = (
            "Apple is preparing its annual promotion, but readers are advised to assess the terms "
            "before buying because other vendors may offer better deals. No 2026 terms are announced."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_multi_brand_activation_comparison_is_weak_despite_apple_background_metrics(self):
        module = load_module()
        title = "iPhone 17 Pro Max激活量超1438万台：一款顶四款国产Ultra旗舰总和"
        summary = (
            "博主把 iPhone 17 Pro Max 的 1438 万台激活量与 iQOO、小米、vivo、OPPO "
            "四款 Ultra 旗舰合计 83.4 万台进行对比，称前者达到后者总和的 17.2 倍；"
            "正文另以 Counterpoint 第一季度数据作为背景。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_competitor_chip_process_first_claim_stays_weak_and_separate_from_apple_m8_process(self):
        module = load_module()
        competitor = article_for(
            module,
            "谷歌抢苹果首发？曝 Tensor G6 芯片将率先用上台积电 2nm 工艺",
            (
                "谷歌 Pixel 11 预计搭载 Tensor G6，成为台积电 2nm 首发客户，"
                "比苹果 A20 芯片早一个月；苹果只是历代先进制程首发惯例的比较背景。"
            ),
            source="IT之家",
        )
        apple = article_for(
            module,
            "苹果 M8 系列已在研发，预计采用台积电 1.4nm 制程",
            "苹果 M8 芯片预计于 2028 年采用台积电 1.4nm 工艺，并获得首批产能。",
            source="cnBeta",
        )

        events = module.cluster_articles([competitor, apple])

        self.assertEqual(competitor.event_kind, "third_party_ecosystem")
        self.assertEqual(competitor.relevance_tier, "weak", competitor.relevance_reason)
        self.assertEqual(apple.event_kind, "hardware_market")
        self.assertEqual(apple.relevance_tier, "strong", apple.relevance_reason)
        self.assertEqual(len(events), 2)

    def test_direct_apple_acquisition_survives_competitor_names_in_body_background(self):
        module = load_module()
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/13/apple-acquires-observability-startup-sigscalr/",
            title="Apple acquires observability startup SigScalr",
            summary=(
                "Apple acquired part of SigScalr's assets and hired members of its team. "
                "The observability market also includes Microsoft, Amazon, and Alphabet."
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source_named(module, "9to5Mac")))

    def test_material_apple_stock_move_survives_market_comparison_background(self):
        module = load_module()
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/07/13/apple-stock-record-territory/",
            title="Apple Stock Returns to Record Territory After 15% Rally",
            summary=(
                "AAPL added roughly $600 billion as investors welcomed Apple's AI spending caution "
                "and product price increases. Amazon and Microsoft were discussed as market peers."
            ),
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source_named(module, "MacRumors")))
        tier, reason = module.classify_relevance_tier(
            candidate.title, candidate.summary, [], candidate.source
        )
        self.assertEqual(tier, "strong", reason)

    def test_app_store_purchase_language_does_not_create_acquisition_identity(self):
        module = load_module()
        acquisition = article_for(
            module,
            "Apple Acquiring SigScalr",
            "Apple acquired SigScalr assets and hired employees from the observability startup.",
            source="MacRumors",
        )
        acquisition_followup = article_for(
            module,
            "SigLens acquired by Apple for debugging massive apps and services",
            "Apple bought assets from SigScalr and brought members of the SigLens team into Apple.",
            source="AppleInsider",
        )
        epic = article_for(
            module,
            "Epic Games fights Apple's request to pause App Store commission proceedings",
            (
                "Epic opposed Apple's request in the App Store case. The filing discusses app purchases, "
                "commissions, alternative payments, and an earlier company acquisition cited as background."
            ),
            source="9to5Mac",
        )

        self.assertNotIn("apple-strategic-transaction", module.primary_topic_facets(epic.title, epic.summary))
        events = module.cluster_articles([acquisition, epic, acquisition_followup])
        self.assertEqual(len(events), 2)
        acquisition_event = next(event for event in events if any("Sig" in item.title for item in event.articles))
        self.assertEqual({item.source for item in acquisition_event.articles}, {"MacRumors", "AppleInsider"})

    def test_generic_component_capacity_story_is_weak_and_does_not_bridge_apple_chip_roadmap(self):
        module = load_module()
        generic_cowos = article_for(
            module,
            "台积电 CoWoS 供不应求，订单外溢至封测厂和英特尔",
            (
                "AI 芯片带动先进封装需求，英伟达囊括大多数 CoWoS 产能，其他客户还包括苹果、"
                "博通、AMD、亚马逊和联发科；订单外溢至日月光、英特尔等封测厂。"
                "报道没有披露苹果与博通之间的新协议，也没有苹果订单、产品或制程动作。"
            ),
            source="快科技",
        )
        apple_m8 = article_for(
            module,
            "苹果 M8 芯片路线图曝光：计划采用台积电 1.4nm 制程",
            "苹果计划让 M8 系列 Mac 芯片采用台积电 1.4nm 工艺，并争取首批产能。",
            source="快科技",
        )

        self.assertEqual(generic_cowos.relevance_tier, "weak", generic_cowos.relevance_reason)
        self.assertEqual(apple_m8.relevance_tier, "strong", apple_m8.relevance_reason)
        self.assertEqual(len(module.cluster_articles([generic_cowos, apple_m8])), 2)

    def test_first_public_beta_release_wave_merges_cross_platform_sources_without_feature_bridging(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 and iPadOS 27 Now Available to Public Beta Testers",
                (
                    "Apple released the first public betas of iOS 27 and iPadOS 27. "
                    "Subscribe to the MacRumors YouTube channel for more videos."
                ),
                source="MacRumors",
            ),
            article_for(
                module,
                "iOS 27 public beta is here with Siri AI, iPhone speed upgrades, and more",
                "Apple released the first iOS 27 public beta with Siri AI and performance changes.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "First macOS Golden Gate Public Beta Now Available",
                "Apple released the first macOS 27 Golden Gate public beta to testers.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple's public betas for iOS 27 and more are out now",
                "Apple released the first public betas of iOS 27, iPadOS 27, macOS 27, and watchOS 27.",
                source="The Verge",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "9to5Mac", "The Verge"})

    def test_routine_third_party_apple_tv_app_launch_is_weak(self):
        module = load_module()
        title = "WordPress just released a brand-new Apple TV app with thousands of free videos"
        summary = "WordPress launched its own third-party tvOS app for watching WordPress.tv videos on Apple TV."

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_same_apple_cross_device_pairing_api_merges_platform_and_meta_angles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Plans AirPods-Like Pairing for Meta's Glasses and Quest",
                "Apple is developing an iOS API that gives approved third-party devices automatic proximity pairing like AirPods.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果披露正为欧盟地区 iOS 开发全新 API，允许第三方产品跨设备自动同步配对",
                "苹果的新配对 API 将先支持 Meta Quest 头显，并受欧盟互操作要求推动。",
                source="IT之家",
            ),
            article_for(
                module,
                "Facebook demands AirPods-like pairing for its glasses and headsets",
                "Meta requested the same Apple iOS automatic pairing API for its glasses and Quest headsets.",
                source="AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家", "AppleInsider"})
        self.assertEqual(events[0].category, "software_systems")

    def test_material_apple_stock_move_merges_cross_source_reporting(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "AAPL stock rallies 15% as investors favor AI caution and welcome price increases",
                "Apple shares gained 15% from their post-WWDC low as investors reassessed AI spending and product prices.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple Stock Returns to Record Territory After 15% Rally",
                "Apple added about $600 billion in value and closed at $315.32, near its $317.40 record.",
                source="MacRumors",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "MacRumors"})
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual(events[0].category, "hardware_products")

    def test_revised_developer_builds_stay_separate_from_first_public_beta_wave(self):
        module = load_module()
        public_ios = article_for(
            module,
            "iOS 27 public beta is here with Siri AI and iPhone speed upgrades",
            "Apple released the first iOS 27 public beta to public beta testers.",
            source="9to5Mac",
        )
        public_tvos = article_for(
            module,
            "tvOS 27 and watchOS 27 now available to public beta testers",
            "Apple released the first public betas of tvOS 27 and watchOS 27.",
            source="MacRumors",
        )
        revised_9to5 = article_for(
            module,
            "Apple rolls out revised beta 3 builds for iPadOS 27 and macOS 27 Golden Gate",
            "Apple replaced the third developer beta builds of iPadOS 27 and macOS 27 with revised builds.",
            source="9to5Mac",
        )
        revised_ai = article_for(
            module,
            "iPadOS 27 and macOS 27 beta 3 get a version 2 update as public betas drop",
            "Apple issued second builds of the third developer betas for iPadOS 27 and macOS 27.",
            source="AppleInsider",
        )

        events = module.cluster_articles([public_ios, public_tvos, revised_9to5, revised_ai])

        self.assertEqual(len(events), 2)
        revised_event = next(event for event in events if any("revised" in item.title.lower() or "version 2" in item.title.lower() for item in event.articles))
        self.assertEqual({item.source for item in revised_event.articles}, {"9to5Mac", "AppleInsider"})
        self.assertTrue(all("public beta" not in item.title.lower() or "version 2" in item.title.lower() for item in revised_event.articles))

    def test_direct_apple_vision_pro_design_guidance_is_strong_software(self):
        module = load_module()
        title = "苹果更新 Vision Pro 空间配件设计指南，详解 visionOS 27 第三方手柄支持"
        summary = "苹果面向开发者更新官方设计指南，列出空间配件与 visionOS 27 控制器的接口和交互要求。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_apple_car_research_reused_for_named_m_series_roadmap_is_strong_hardware(self):
        module = load_module()
        title = "消息称苹果转化 100 亿美元造车成果，用于 M7/M8 系列 Mac AI 芯片"
        summary = "苹果把已终止造车项目积累的芯片与 AI 研究成果转入 M7 和 M8 系列 Mac 芯片研发。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "strong", reason)
        self.assertIn("apple-chip-research-transfer", module.primary_topic_facets(title, summary))
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_dated_apple_tv_sports_lineup_is_service_content(self):
        module = load_module()
        title = "Apple TV has a packed lineup of sports premieres coming soon"
        summary = "Apple announced dated July premieres and schedules for Formula 1, MLS, and Friday Night Baseball on Apple TV."

        self.assertEqual(module.detect_event_kind(title, summary, []), "service_content")
        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
        self.assertEqual(tier, "strong", reason)

    def test_hardware_trade_secret_lawsuit_is_classified_as_hardware(self):
        module = load_module()
        article = article_for(
            module,
            "Apple's OpenAI lawsuit threatens plans for an iPhone rival",
            (
                "Apple alleges former hardware engineers took unreleased device designs and product-roadmap secrets "
                "to OpenAI, affecting Jony Ive's physical AI hardware timeline."
            ),
            source="MacRumors",
        )

        event = module.cluster_articles([article])[0]

        self.assertEqual(event.event_kind, "legal_antitrust")
        self.assertEqual(event.category, "hardware_products")

    def test_combined_release_roundup_cannot_bridge_public_beta_and_revised_build_events(self):
        module = load_module()
        public = article_for(
            module,
            "iOS 27 and iPadOS 27 Now Available to Public Beta Testers",
            "Apple released the first public betas of iOS 27 and iPadOS 27.",
            source="MacRumors",
        )
        combined = article_for(
            module,
            "苹果发布 iOS 27 等首个公测版，同步推送 macOS 27 Beta 3 修订版",
            "苹果发布首个 iOS 27 公测版，同时向开发者推送 macOS 27 Beta 3 修订编译版本。",
            source="IT之家",
        )
        revised = article_for(
            module,
            "Apple rolls out revised beta 3 builds for iPadOS 27 and macOS 27 Golden Gate",
            "Apple replaced the third developer beta builds of iPadOS 27 and macOS 27.",
            source="9to5Mac",
        )

        events = module.cluster_articles([public, combined, revised])

        self.assertEqual(len(events), 2)
        self.assertFalse(any(public in event.articles and revised in event.articles for event in events))

    def test_epic_app_store_case_cannot_absorb_openai_hardware_trade_secret_case(self):
        module = load_module()
        epic = article_for(
            module,
            "Epic fights Apple's request to pause App Store commission proceedings",
            "Epic opposed Apple's request in the App Store commission lawsuit.",
            source="9to5Mac",
        )
        generic_epic = article_for(
            module,
            "苹果请求法院暂停 App Store 佣金诉讼，遭 Epic 反对",
            "法院文件涉及 Apple、Epic、App Store 佣金和替代支付争议。",
            source="IT之家",
        )
        openai = article_for(
            module,
            "OpenAI hardware timeline unchanged after Apple trade-secret lawsuit",
            "Apple alleges former hardware engineers took unreleased device designs for OpenAI's physical AI product.",
            source="cnBeta",
        )

        events = module.cluster_articles([epic, generic_epic, openai])

        self.assertEqual(len(events), 2)
        self.assertFalse(any(epic in event.articles and openai in event.articles for event in events))
        self.assertEqual(next(event for event in events if openai in event.articles).category, "hardware_products")

    def test_same_q2_iphone_market_share_reports_merge_despite_pricing_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple hits record 20% global smartphone shipment share as market plunges",
                "Counterpoint says Apple reached a record Q2 share of 20% in 2026.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Omdia 报告 2026Q2 全球手机出货量同比降 4%：三星占 22%、苹果占 20%",
                "Omdia 称苹果 2026 年第二季度全球智能手机份额达到同期纪录 20%。",
                source="IT之家",
            ),
            article_for(
                module,
                "苹果 2026 年 Q2 全球智能手机份额冲至 20%：创同期新高，全靠 iPhone 17 不涨价",
                "报告称苹果份额达到 20%，iPhone 17 维持定价被视为增长因素。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual({item.source for item in events[0].articles}, {"9to5Mac", "IT之家", "快科技"})

    def test_same_beta_number_release_wave_merges_across_platforms_and_update_labels(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Seeds Fifth iOS 26.6 and iPadOS 26.6 Betas to Developers [Update: Public Beta Available]",
                "Apple released beta 5 of iOS 26.6 and iPadOS 26.6.",
                source="MacRumors",
            ),
            article_for(
                module,
                "macOS 26.6 beta 5 now available, here's what's coming",
                "Apple released macOS 26.6 beta 5 to developers.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果 watchOS 26.6 开发者预览版 Beta 5 发布",
                "苹果发布 watchOS 26.6 Beta 5。",
                source="IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)

    def test_public_beta_advice_and_feature_list_without_new_action_are_weak(self):
        module = load_module()
        titles = [
            "iOS 27 Public Beta Is Here: 10 New Features Worth Testing",
            "iOS 27 public beta: Should you install it on your iPhone?",
            "The macOS 27 public beta is worth it just for the Liquid Glass tweaks",
        ]

        for title in titles:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, title, [], "9to5Mac")
                self.assertEqual(tier, "weak", reason)

    def test_current_macrumors_public_beta_feature_guide_remains_reviewable(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/guide/ios-27-public-beta-features/",
            title="iOS 27 Public Beta Is Here: 10 New Features Worth Testing",
            summary=(
                "Apple released the iOS 27 public beta today and lists performance improvements, "
                "Siri AI, Visual Intelligence, Safari, Home, AirPods EQ, and Shortcuts changes. "
                "The guide also mentions third-party apps, alternative Siri activation methods, "
                "installation advice, and forum links."
            ),
            feed_time_raw="Mon, 13 Jul 2026 16:07:18 PDT",
            context="featured ios 27",
        )

        tier, reason = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [candidate.context],
            candidate.source,
        )

        self.assertEqual(tier, "weak", reason)
        self.assertTrue(module.is_relevant_candidate(candidate, source))

    def test_direct_macos_malware_reports_merge_by_family(self):
        module = load_module()
        english = article_for(
            module,
            "CrashStealer malware poses as an Apple tool to steal passwords and Mac data",
            "CrashStealer targets macOS users and steals credentials from 14 password managers.",
            source="AppleInsider",
        )
        chinese = article_for(
            module,
            "CrashStealer 攻击披露：针对苹果 Mac 用户，瞄准 14 款密码管理器",
            "该恶意软件伪装成苹果工具，窃取 macOS 密码和浏览器数据。",
            source="IT之家",
        )

        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "security_privacy")
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_malicious_imessage_warning_reports_merge_as_direct_os_security_change(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 26.6 Will Warn You About Malicious iMessages",
                "Apple added an iOS warning for malicious messages and suspicious links.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果 iOS 26.6 Beta 5 新增检测到恶意信息提醒",
                "信息 App 会警告用户收到的恶意 iMessage。",
                source="IT之家",
            ),
            article_for(
                module,
                "iOS 26.6 将针对恶意 iMessage 发出警告",
                "苹果新增恶意信息警告功能。",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_kind, "security_privacy")
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_apple_i_auction_is_hardware_news(self):
        module = load_module()
        self.assertEqual(
            module.choose_category(
                "又一台能开机的苹果 Apple I 电脑被拍卖，估价 30 万-50 万美元",
                "一台可运行的 Apple I 实体电脑进入拍卖。",
            ),
            "hardware_products",
        )

    def test_openai_product_trade_secret_case_merges_across_headline_styles_as_hardware(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "为了 AI iPhone 苹果正式起诉 OpenAI",
                "苹果指控前员工窃取未发布产品、设备设计和供应链资料，协助 OpenAI 开发实体 AI 硬件。",
                source="快科技",
            ),
            article_for(
                module,
                "Report: Apple's OpenAI Lawsuit Threatens iPhone Rival Plans",
                "Apple alleges former hardware engineers took unreleased device designs for OpenAI's physical AI product.",
                source="MacRumors",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(events[0].event_kind, "legal_antitrust")

    def test_plural_beta_release_titles_merge_by_version_and_beta_number(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Releases Fifth watchOS 26.6, tvOS 26.6 and visionOS 26.6 Betas",
                "Apple released beta 5 across watchOS, tvOS, and visionOS.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple Seeds Fifth iOS 26.6 and iPadOS 26.6 Betas to Developers [Update: Public Beta Available]",
                "Apple released beta 5 of iOS 26.6 and iPadOS 26.6.",
                source="MacRumors",
            ),
            article_for(
                module,
                "macOS 26.6 beta 5 now available, here's what's coming",
                "Apple released macOS 26.6 beta 5 to developers.",
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)

    def test_apple_intel_foundry_commitment_is_hardware_and_merges_with_named_chip_order(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Report: Apple Agreed to Intel Chips Amid White House Tariff Talks",
                "Apple agreed to have Intel fabricate chips for future Mac and iPhone products.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Intel 18A-P 工艺拿下苹果 M7 处理器订单",
                "苹果将由 Intel 代工 M7 芯片，采用 18A-P 制程。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(events[0].event_kind, "hardware_market")

    def test_competitor_chip_launch_cannot_join_apple_foundry_sourcing_event(self):
        module = load_module()
        competitor = article_for(
            module,
            "台积电 2nm 已量产，谷歌新机将抢先苹果首发搭载",
            "报道主体是谷歌手机和台积电 2nm 量产，仅在比较中提到苹果后续产品。",
            source="快科技",
        )
        apple = article_for(
            module,
            "Report: Apple Agreed to Intel Chips Amid White House Tariff Talks",
            "Apple agreed to have Intel fabricate chips for future Mac and iPhone products.",
            source="MacRumors",
        )

        events = module.cluster_articles([competitor, apple])

        self.assertEqual(len(events), 2)
        self.assertEqual(competitor.relevance_tier, "weak")
        self.assertNotIn("apple-chip-foundry-sourcing", module.article_primary_facets(competitor))

    def test_high_overlap_hardware_leak_followups_merge_on_multiple_specific_facets(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro 散热史诗级提升，A20 Pro 采用台积电 WMCM 封装",
                "泄露资料显示 A20 Pro 采用 WMCM 多芯片封装、2nm 芯片和新散热结构。",
                source="快科技",
            ),
            article_for(
                module,
                "iPhone 18 Pro 散热大翻身，A20 Pro 性能释放更彻底",
                "同一批泄露资料显示 A20 Pro 使用 WMCM 多芯片封装、2nm 芯片和新散热结构。",
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)

    def test_third_party_product_name_containing_vision_pro_is_not_apple_news(self):
        module = load_module()
        source = source_named(module, "IT之家")
        candidate = module.Candidate(
            source="IT之家",
            url="https://example.com/dynamic-vision-pro-cooler",
            title="利民推出 Dynamic Vision PRO 360 ARGB BLACK 液冷散热器",
            summary="产品配备 6400 RPM 水泵、VRM 风扇和可旋转 LCD 冷头屏幕。",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))
        tier, _ = module.classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [],
            candidate.source,
        )
        self.assertEqual(tier, "weak")

    def test_apple_service_how_to_without_new_action_is_weak(self):
        module = load_module()
        title = "How to use Playlist Playground to build Apple Music playlists in seconds"
        summary = (
            "Apple added Playlist Playground in iOS 26.4. This walkthrough explains how "
            "to enter prompts and refine an existing playlist."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_market_comparison_cannot_join_direct_apple_share_report(self):
        module = load_module()
        apple_report = article_for(
            module,
            "Apple hits record 20% global smartphone shipment share as market plunges",
            "Counterpoint says Apple reached a record Q2 share of 20% in 2026.",
            source="9to5Mac",
        )
        competitor_report = article_for(
            module,
            "三星 Galaxy 手机在韩独占逾 80% 份额，亦成为 78% 用户未来购机选择",
            (
                "韩国盖洛普调查显示 Galaxy 用户占 81%，苹果手机占 19%；只有 20 至 29 岁人群中，"
                "苹果手机用户占比 53%，高于 Galaxy 的 47%。"
            ),
            source="IT之家",
        )

        events = module.cluster_articles([apple_report, competitor_report])

        self.assertEqual(len(events), 2)
        self.assertFalse(any(apple_report in event.articles and competitor_report in event.articles for event in events))

    def test_direct_apple_metrics_in_multi_vendor_market_report_are_strong(self):
        module = load_module()
        title = (
            "IDC 报告 2026 年 Q2 全球智能手机出货量同比下滑 6.7%："
            "小米跌幅最大但有意为之，三星、苹果、华为逆势上涨"
        )
        summary = (
            "苹果第二季度出货量创历史同期新高，市场份额扩大 3.8 个百分点，"
            "全年市场份额有望达到 22%，主要受 iPhone 17 需求推动。"
            "IDC 全球客户端设备副总裁发布了相关分析。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "strong", reason)
        self.assertIn("apple-market-share-report", module.primary_topic_facets(title, summary))

    def test_government_pressure_for_apple_to_use_intel_foundry_is_hardware_sourcing(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Report: Apple Agreed to Intel Chips Amid White House Tariff Talks",
                "Apple agreed to have Intel fabricate chips for future Mac and iPhone products.",
                source="MacRumors",
            ),
            article_for(
                module,
                "英特尔翻身有靠山！特朗普施压苹果、英伟达：英特尔这单你们必须接",
                (
                    "美国政府将英特尔复兴列为战略优先项，向苹果、英伟达及 SpaceX 等潜在合作伙伴施压，"
                    "鼓励采用英特尔的芯片与晶圆制造服务；苹果与英特尔的谈判正在推进。"
                    "背景还提到日本软银此前对英特尔投资。"
                ),
                source="快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(events[0].event_kind, "hardware_market")
        self.assertEqual(events[0].merge_warnings, [])

    def test_independent_ios_developer_project_is_weak_without_apple_action(self):
        module = load_module()
        title = "代码 100% 由 AI 编写：9 年 iOS 开发者 15 天打造外卖游戏，斩获 2.5 万美元奖金"
        summary = (
            "一名独立 iOS 开发者在 Cursor Vibe Jam 中使用 Claude Code 开发第三方游戏并获奖，"
            "科技媒体发布博文称项目生成了约 2.7 万行代码；报道主体是参赛项目、开发过程和奖金，"
            "并未涉及平台政策或系统功能变更。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)
        facets = module.primary_topic_facets(title, summary)
        self.assertFalse(any(facet.startswith("os-release-version-") for facet in facets))

    def test_numbered_os_feature_roundup_without_new_action_is_weak(self):
        module = load_module()
        title = "Time for change: 50 Apple Watch updates coming in watchOS 27"
        summary = (
            "A roundup collects 50 previously announced watchOS 27 interface and app changes. "
            "It does not report a new release, build, or standalone Apple action."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_led_corporate_ranking_with_apple_as_comparison_is_weak(self):
        module = load_module()
        title = "普华永道发布 2026 全球市值 100 强上市公司排行榜，英伟达超越苹果登顶"
        summary = (
            "PwC 按 2026 年 3 月 31 日市值列出全球 100 强公司，英伟达位居第一。"
            "报告讨论全球企业总市值、美国公司占比，以及半导体、硬件和芯片行业增长，"
            "苹果只是排名比较对象。"
        )

        kind = module.detect_event_kind(title, summary)
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(kind, "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

    def test_non_apple_legal_dispute_with_later_apple_comparison_is_rejected(self):
        module = load_module()
        source = source_named(module, "IT之家")
        title = "OpenAI 反击马斯克窃密官司：xAI 诉讼浪费公司资源，需承担百万法律费"
        summary = (
            "OpenAI 向法院申请裁定 xAI 的商业机密窃取诉讼本不该立案，并要求对方承担超百万美元法律费用。"
            "这标志着两家公司法律纠纷进一步升级。OpenAI 指责 xAI 先起诉后找证据。"
            "作为后文背景，报道提到苹果公司上周也对 OpenAI 提起了另一宗商业秘密诉讼。"
        )
        candidate = module.Candidate(
            source="IT之家",
            url="https://example.com/openai-xai-lawsuit",
            title=title,
            summary=summary,
            context="苹果起诉 OpenAI 涉嫌窃取未发布硬件机密。",
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))
        tier, reason = module.classify_relevance_tier(
            title,
            summary,
            [candidate.context],
            candidate.source,
        )
        self.assertEqual(tier, "weak", reason)

    def test_apple_legal_story_with_direct_lead_remains_strong(self):
        module = load_module()
        title = "OpenAI hardware timeline unchanged after Apple trade-secret theft lawsuit"
        summary = (
            "Apple sued OpenAI over alleged theft of unreleased hardware information. "
            "OpenAI still plans to unveil its first device this year."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "strong", reason)

    def test_macos_point_beta_and_legacy_release_candidates_remain_separate(self):
        module = load_module()
        current_beta = article_for(
            module,
            "Fifth macOS Tahoe 26.6 Beta Now Available for Developers [Update: Public Beta Available]",
            (
                "Apple released macOS Tahoe 26.6 beta 5 to developers for testing purposes. "
                "An update notes that "
                "public release candidates for macOS Sonoma 14.8.8 and macOS Sequoia 15.7.8 "
                "also became available."
            ),
            source="MacRumors",
        )
        legacy_rc = article_for(
            module,
            "macOS Sonoma 14.8.8 and macOS Sequoia 15.7.8 get a rare fifth RC",
            (
                "Developers testing macOS Sonoma 14.8.8 and macOS Sequoia 15.7.8 can install "
                "the fifth release candidate builds for macOS Sonoma 14.8.8 "
                "and macOS Sequoia 15.7.8 alongside macOS 26.6 beta 5."
            ),
            source="9to5Mac",
        )

        events = module.cluster_articles([current_beta, legacy_rc])

        self.assertEqual(len(events), 2)
        self.assertIn("os-release-version-26-6", module.primary_topic_facets(current_beta.title, current_beta.summary))
        self.assertIn("os-release-beta-5", module.primary_topic_facets(current_beta.title, current_beta.summary))
        self.assertIn("os-release-version-14-8-8", module.primary_topic_facets(legacy_rc.title, legacy_rc.summary))
        self.assertIn("os-release-rc", module.primary_topic_facets(legacy_rc.title, legacy_rc.summary))

    def test_distinct_apple_tv_titles_do_not_merge_on_cast_and_trailer_boilerplate(self):
        module = load_module()
        mayday = article_for(
            module,
            "Apple TV's next action-comedy starring Ryan Reynolds gets first trailer - 9to5Mac",
            "Apple TV today released the first trailer for Mayday, an action comedy movie starring Ryan Reynolds and Kenneth Branagh. Watch it below.",
            source="9to5Mac",
        )
        lucky = article_for(
            module,
            "Limited series Lucky, starring Anya Taylor-Joy, premieres on Apple TV - 9to5Mac",
            "The first episodes of Lucky, Apple TV's new limited series starring Anya Taylor-Joy, are now streaming. Watch the trailer below.",
            source="9to5Mac",
        )

        self.assertEqual(len(module.cluster_articles([mayday, lucky])), 2)

    def test_apple_arcade_title_identity_overrides_device_compatibility_background(self):
        module = load_module()
        newsroom = article_for(
            module,
            "Madden NFL 27 Arcade Edition brings gridiron action to Apple Arcade on August 6",
            "Apple announced Madden NFL 27 Arcade Edition for Apple Arcade on iPhone, iPad, Mac, Apple TV, and Apple Vision Pro.",
            source="Apple Newsroom",
        )
        appleinsider = article_for(
            module,
            "Madden football returns to Mac for the first time in 19 years",
            "Madden NFL 27 Arcade Edition arrives through Apple Arcade and also supports Apple TV and Vision Pro as compatible devices.",
            source="AppleInsider",
        )

        self.assertEqual(
            module.primary_topic_facets(appleinsider.title, appleinsider.summary),
            {"apple-arcade"},
        )
        events = module.cluster_articles([newsroom, appleinsider])
        self.assertEqual(len(events), 1)

    def test_distinct_apple_legal_cases_do_not_merge_through_generic_legal_terms(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple says Epic's arguments against pausing the case are wrong",
                "Apple responded to Epic Games in the App Store commission and anti-steering case.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果请求暂停 App Store 佣金案程序，称 Epic 的反对理由错误",
                "苹果在 Epic Games 的 App Store 反引导和佣金诉讼中提交了新的法院文件。",
                source="IT之家",
            ),
            article_for(
                module,
                "Judge dismisses lawsuit accusing Apple of failing to stop CSAM on iCloud",
                "A federal judge dismissed the iCloud CSAM class action under Section 230.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果成功驳回 iCloud 儿童性虐待材料集体诉讼",
                "法院依据 Section 230 驳回指控苹果未阻止 iCloud 传播儿童性虐待材料的案件。",
                source="cnBeta",
            ),
            article_for(
                module,
                "OpenAI says it has seen no evidence supporting Apple's trade-secret theft claims",
                "OpenAI responded to Apple's lawsuit alleging theft of unreleased hardware trade secrets.",
                source="9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 3)
        source_sets = [{article.source for article in event.articles} for event in events]
        self.assertIn({"9to5Mac", "IT之家"}, source_sets)
        self.assertIn({"9to5Mac", "cnBeta"}, source_sets)

    def test_direct_prismml_talks_are_strong_but_model_only_release_stays_weak(self):
        module = load_module()
        direct = [
            article_for(
                module,
                "PrismML confirms it is in talks with Apple about AI model-shrinking tech",
                "PrismML CEO Babak Hassibi confirmed early talks with Apple about evaluating its model-compression technology.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "PrismML确认正与苹果洽谈 AI 模型压缩技术合作",
                "PrismML 表示苹果正在评估其 1-bit 模型压缩技术，双方处于早期沟通阶段。",
                source="cnBeta",
            ),
        ]
        model_only = article_for(
            module,
            "PrismML releases Bonsai 27B, claiming first major AI model of its size fit for iPhone",
            "The startup released a compressed third-party AI model that can run on iPhone; Apple did not announce a partnership or platform change.",
            source="9to5Mac",
        )

        self.assertTrue(all(article.relevance_tier == "strong" for article in direct))
        self.assertTrue(
            all(
                "apple-on-device-ai-model-compression" in module.primary_topic_facets(article.title, article.summary)
                for article in direct
            )
        )
        self.assertEqual(model_only.relevance_tier, "weak")
        events = module.cluster_articles([*direct, model_only])
        self.assertEqual(len(events), 2)
        self.assertEqual(len(next(event for event in events if direct[0] in event.articles).articles), 2)

    def test_chinese_apple_initiated_ai_compression_talks_are_direct_apple_news(self):
        module = load_module()
        title = "苹果研发 AI 模型压缩技术：把 270 亿参数大模型装进 iPhone"
        summary = (
            "苹果正与硅谷初创公司 PrismML 进行早期洽谈，后者宣称能将大型 AI 模型压缩至可在 "
            "iPhone 上本地运行。双方仍在评估技术，尚未公布交易。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(
            module.primary_topic_facets(title, summary),
            {"apple-on-device-ai-model-compression"},
        )

    def test_siri_beta_availability_does_not_inherit_listed_product_topics(self):
        module = load_module()
        title = "苹果通过 iOS 27 公测版向更多用户开放 Siri AI"
        summary = (
            "苹果向公众开放重构后的 Siri AI。此次公测覆盖 iPhone、iPad、Mac、Apple Watch、"
            "CarPlay、AirPods、Apple TV 和 Vision Pro；正文还说明模型基于苹果芯片优化。"
        )

        facets = module.primary_topic_facets(title, summary)

        self.assertIn("apple-ai-platform", facets)
        self.assertNotIn("apple-tv-content", facets)
        self.assertNotIn("carplay-platform-feature", facets)
        self.assertNotIn("ipad-chip-roadmap", facets)

    def test_product_outlook_roundup_is_not_promoted_by_recycled_specs(self):
        module = load_module()
        title = "OLED iPad Mini: Release Date, Pricing, and What to Expect"
        summary = (
            "A roundup asks what to expect and recaps prior reports about an A19 Pro chip, an 8.4-inch "
            "OLED panel, water resistance, and a possible late-2026 launch. It contains no newly sourced report."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_industry_story_is_not_promoted_by_later_apple_legal_example(self):
        module = load_module()
        title = "SK海力士扩产画饼被戳破！2028年产能仅六分之一：DRAM高价还要3年"
        summary = (
            "美国银行发布全球存储周报，估算 SK 海力士到 2028 年实际新增产能仅为原规划的"
            "六分之一。正文后段才讨论存储厂商在美国遭遇的集体诉讼，并将苹果对 iPad 和 Mac"
            "的全面提价援引为直接损害案例。"
        )
        facts = [
            "三星、SK 海力士与美光在加州联邦法院遭遇集体诉讼。",
            "原告方将苹果对 iPad 和 Mac 的提价援引为损害案例。",
        ]

        tier, reason = module.classify_relevance_tier(title, summary, facts, "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_apple_carrier_financing_lock_policy_is_direct_hardware_news(self):
        module = load_module()
        title = (
            "分期买 iPhone 17 Pro 不再自动解锁：苹果确认 T-Mobile 和 Verizon "
            "分期用户不再享受无锁待遇"
        )
        summary = (
            "苹果更新购买 FAQ：通过运营商设备分期计划购买的 iPhone 在还清全款前保持有锁状态，"
            "用户不能直接换网；新条款涉及 T-Mobile、Verizon 和 AT&T。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(
            module.primary_topic_facets(title, summary),
            {"iphone-carrier-lock-policy"},
        )

    def test_apple_analyst_rating_action_is_separate_from_market_share_background(self):
        module = load_module()
        title = "KeyBanc downgrades Apple to Underweight with a $250 price target"
        summary = (
            "The investment bank cut its Apple rating and set a $250 target, citing slower iPhone production, "
            "weaker carrier subsidies, and service growth risk. The report later notes Apple's 20% market share."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(
            module.primary_topic_facets(title, summary),
            {"apple-analyst-rating-target"},
        )

    def test_speculative_witness_analysis_is_not_a_new_legal_action(self):
        module = load_module()
        response = article_for(
            module,
            "OpenAI says Apple's trade-secret complaint has no merit",
            "OpenAI formally responded to Apple's lawsuit and denied that the complaint has evidentiary merit.",
            source="9to5Mac",
        )
        analysis = article_for(
            module,
            "Jony Ive may be unable to stay out of the Apple and OpenAI dispute",
            (
                "A commentary says Ive could possibly be subpoenaed as a witness during discovery, but notes that "
                "it is too early to know and reports no subpoena, filing, ruling, testimony, or confirmed action."
            ),
            source="IT之家",
        )

        self.assertEqual(analysis.relevance_tier, "weak", analysis.relevance_reason)
        self.assertEqual(len(module.cluster_articles([response, analysis])), 2)

    def test_airpods_public_beta_firmware_sources_merge_as_firmware_event(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "AirPods public betas arrive one day after iOS 27 public beta",
                "Apple released AirPods firmware 9.0.314 build 9A5314b to public beta testers for AirPods Pro, AirPods 4, and AirPods Max.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple Releases New iOS 27 AirPods Firmware For Public Beta Testers",
                "Apple released AirPods firmware 9A5314b for public beta testers with iOS 27 features.",
                source="MacRumors",
            ),
        ]

        self.assertTrue(
            all(
                "airpods-firmware" in module.primary_topic_facets(article.title, article.summary)
                for article in articles
            )
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_same_ipad_mini_display_spec_rumor_merges_across_source_wording(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Upcoming OLED iPad Mini Allegedly Uses 60Hz 8.4-Inch Display Panel",
                "A supply-chain report says the next iPad mini uses an 8.4-inch LTPS hybrid OLED panel fixed at 60Hz.",
                source="MacRumors",
            ),
            article_for(
                module,
                "消息称苹果 iPad mini 8 搭载 8.4 寸 60Hz OLED 面板",
                "新款 iPad mini 据称采用 8.4 英寸 LTPS Hybrid OLED 屏幕，刷新率仍为 60Hz。",
                source="IT之家",
            ),
            article_for(
                module,
                "传闻称新款 OLED iPad mini 将采用 60Hz 显示屏",
                "供应链消息称苹果下一代 iPad mini 配备 8.4 英寸 OLED 面板并保持 60Hz。",
                source="cnBeta",
            ),
            article_for(
                module,
                "OLED iPad mini may still launch before the end of 2026",
                (
                    "According to a Naver post by Yeux1122, the iPad mini with an AMOLED display will launch "
                    "in the second half of 2026. Mass production is underway on Samsung Display's A2 G5.5 "
                    "line for an 8.4-inch LTPS rear panel with hybrid OLED."
                ),
                source="AppleInsider",
            ),
        ]

        self.assertTrue(
            all(
                "apple-display-panel-spec-rumor" in module.primary_topic_facets(article.title, article.summary)
                for article in articles
            )
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_multi_product_oled_supply_roadmap_stays_separate_from_one_product_spec_rumor(self):
        module = load_module()
        roadmap = article_for(
            module,
            "Omdia: BOE may supply Apple OLED panels for 2027 iPad Air and 2028 MacBook Pro",
            (
                "Omdia says BOE may supply OLED panels for Apple's 2027 iPad Air and 2028 MacBook Pro. "
                "The wider roadmap also expects a 2026 iPad mini with an 8.4-inch LTPS hybrid OLED panel."
            ),
            source="IT之家",
        )
        ipad_mini_spec = article_for(
            module,
            "OLED iPad mini may still launch before the end of 2026",
            (
                "According to a Naver post, mass production is underway for an 8.4-inch LTPS hybrid OLED "
                "panel and the iPad mini is expected in the second half of 2026."
            ),
            source="AppleInsider",
        )

        self.assertNotIn(
            "apple-display-panel-spec-rumor",
            module.primary_topic_facets(roadmap.title, roadmap.summary),
        )
        self.assertEqual(len(module.cluster_articles([roadmap, ipad_mini_spec])), 2)

    def test_eu_apple_device_battery_exemption_is_not_regulated_access_story(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Watch among wearables exempted from EU user-replaceable battery rules",
                "The European Commission exempted Apple Watch and AirPods from user-replaceable battery requirements when opening a sealed device would harm safety or durability.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple Watch、Meta 眼镜和 AirPods 获欧盟可更换电池法规豁免",
                "欧盟委员会修订电池法规，为 Apple Watch 和 AirPods 等紧凑密封设备提供用户可更换电池豁免；欧委会否认此举源于美国施压。",
                source="cnBeta",
            ),
        ]

        self.assertTrue(
            all(
                module.primary_topic_facets(article.title, article.summary) == {"apple-device-battery-regulation"}
                for article in articles
            )
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_apple_market_share_action_overrides_competitor_and_price_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone grows China market share as price hikes harm Android rivals",
                "IDC says iPhone shipments in China grew 24.4% and market share rose from 13.9% to 18.1%; Android price pressure is background context.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "iPhone在华市场份额增长，涨价冲击 Android 竞争对手",
                "IDC 数据显示苹果 iPhone 第二季度在华出货量增长 24.4%，份额从 13.9% 升至 18.1%。",
                source="cnBeta",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        self.assertTrue(
            all(module.primary_topic_facets(article.title, article.summary) == {"apple-market-share-report"} for article in articles)
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_iphone_production_retooling_does_not_absorb_ai_company_talks(self):
        module = load_module()
        hardware = [
            article_for(
                module,
                "Factories Now Ready for iPhone 20's Glass Redesign, Leaker Claims",
                "Apple suppliers completed factory-line renovations for a new glass enclosure and are waiting for iPhone production equipment.",
                source="MacRumors",
            ),
            article_for(
                module,
                "传苹果 iPhone 20 将迎来全玻璃机身设计，供应链已做好准备",
                "苹果供应链工厂完成新玻璃工艺产线改造，等待设备进场生产下一代 iPhone。",
                source="cnBeta",
            ),
        ]
        prism = article_for(
            module,
            "PrismML confirms it is in talks with Apple about AI model-shrinking tech",
            "PrismML confirmed early discussions with Apple about model compression for on-device AI.",
            source="AppleInsider",
        )

        events = module.cluster_articles([*hardware, prism])
        self.assertEqual(len(events), 2)
        self.assertEqual(len(next(event for event in events if hardware[0] in event.articles).articles), 2)
        self.assertFalse(any(prism in event.articles and hardware[0] in event.articles for event in events))

    def test_third_party_usage_opinion_tutorial_and_comparison_stories_stay_weak(self):
        module = load_module()
        samples = [
            (
                "Opera gains ground among iPhone users in the US and UK",
                "Opera says its iOS monthly active users grew after Apple's browser choice screen; the update also adds Opera account sync and browser AI.",
                "9to5Mac",
            ),
            (
                "Owning an Apple Home: The broken promise of Matter",
                "An opinion column argues that third-party Matter accessories still provide an inconsistent Apple Home experience, without a new Apple action.",
                "AppleInsider",
            ),
            (
                "These are the things you should do first after updating to iOS 27",
                "A tutorial recommends settings and setup steps after installing iOS 27; Apple announced no new change in the article.",
                "AppleInsider",
            ),
            (
                "OpenAI's first hardware device will be a HomePod, but don't tell them that",
                "A commentary compares OpenAI's rumored smart speaker with Apple's HomePod; Apple made no product announcement.",
                "AppleInsider",
            ),
            (
                "多名用户示警：OpenAI 最新模型 GPT-5.6 Sol 会擅自删除用户文件",
                "用户报告第三方 OpenAI 模型删除 Windows 和 Mac 文件；苹果没有发布或调整任何产品、平台或安全机制。",
                "IT之家",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_non_apple_hardware_report_does_not_join_apple_legal_response_from_background_case(self):
        module = load_module()
        legal = article_for(
            module,
            "OpenAI says it has seen no evidence supporting Apple's trade-secret theft claims",
            "OpenAI directly responded to Apple's lawsuit over unreleased hardware trade secrets.",
            source="9to5Mac",
        )
        hardware = article_for(
            module,
            "OpenAI's First AI Device Will Be a Portable Smart Speaker",
            (
                "Bloomberg reports that OpenAI is developing a portable smart speaker for 2027. "
                "The device is also mentioned in Apple's separate lawsuit over unreleased hardware trade secrets."
            ),
            source="MacRumors",
        )

        self.assertEqual(legal.relevance_tier, "strong")
        self.assertEqual(hardware.relevance_tier, "weak")
        self.assertEqual(hardware.event_kind, "third_party_ecosystem")
        self.assertNotIn("apple-legal-proceeding", module.article_primary_facets(hardware))
        self.assertEqual(len(module.cluster_articles([legal, hardware])), 2)

    def test_third_party_model_release_without_direct_apple_action_stays_weak(self):
        module = load_module()
        title = "手机 AI 的 DeepSeek 时刻：Bonsai 27B 模型登场，苹果 iPhone 17 Pro 可运行"
        summary = (
            "PrismML 发布 Bonsai 27B 模型，压缩后可在 12GB 内存的 iPhone 上本地运行。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "weak", reason)
        self.assertNotIn("apple-on-device-ai-model-compression", module.primary_topic_facets(title, summary))

    def test_single_weak_roundup_event_is_not_promoted_by_aggregated_summary(self):
        module = load_module()
        roundup = article_for(
            module,
            "OLED iPad Mini: Release Date, Pricing, and What to Expect",
            "A buying-oriented roundup recaps old OLED, pricing, and release-date rumors without new reporting.",
            source="MacRumors",
        )

        roundup.relevance_tier = "weak"
        roundup.relevance_reason = "routine product outlook roundup"
        event = module.cluster_articles([roundup])[0]
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_direct_display_spec_rumor_stays_strong_with_comparison_background(self):
        module = load_module()
        title = "传闻称新款 OLED iPad mini 将采用 60Hz 显示屏"
        summary = (
            "供应链称新款 iPad mini 配备 8.4 英寸 LTPS OLED 面板，刷新率为 60Hz。"
            "正文随后比较 iPad Pro、iPhone 17 和三星显示生产线。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "cnBeta")

        self.assertEqual(tier, "strong", reason)

    def test_apple_market_growth_title_uses_market_report_identity_despite_price_background(self):
        module = load_module()
        title = "苹果 iPhone 17 定价策略助力其在二季度中国智能手机市场逆势增长"
        summary = "IDC 数据显示苹果第二季度在华出货量增长 24.9%，市场份额由 13.9% 升至 18.1%。"

        self.assertTrue(module.is_title_primary_apple_market_share_story(title, summary))
        self.assertEqual(module.primary_topic_facets(title, summary), {"apple-market-share-report"})
        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")

    def test_same_device_battery_regulation_ignores_background_region_markers(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Watch among wearables exempted from EU user-replaceable battery rules",
                "The European Commission granted an exemption; the report also discusses U.S. pressure claims.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple Watch, Meta Glasses, AirPods get reprieve from EU replaceable battery law",
                "The EU exemption covers sealed wearables and includes technical examples from Germany.",
                source="AppleInsider",
            ),
            article_for(
                module,
                "Apple Watch、Meta 眼镜和 AirPods 获欧盟可更换电池法规豁免",
                "欧盟委员会调整同一法规；正文还提到美国和日本市场的维修安排。",
                source="cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_feature_and_hardware_outlook_roundups_stay_weak(self):
        module = load_module()
        samples = [
            (
                "Top watchOS 27 features that will enhance your Apple Watch",
                "Here is everything new in watchOS 27 so far, including Siri, widgets, gestures, and health changes.",
            ),
            (
                "Your iPhone might miss out on these iOS 27 features",
                "Here is everything you need to know about compatibility and previously announced feature availability.",
            ),
            (
                "Apple has a new MacBook Pro coming soon, here's what we know",
                "This roundup recaps previously reported OLED, touchscreen, design, and launch timing rumors.",
            ),
        ]

        for title, summary in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(tier, "weak", reason)
        os_roundups = [article_for(module, title, summary, source="9to5Mac") for title, summary in samples[:2]]
        self.assertEqual(len(module.cluster_articles(os_roundups)), 2)

    def test_subjective_legal_commentary_without_new_case_action_stays_weak(self):
        module = load_module()
        title = "Sam Altman didn't need another lawsuit"
        summary = (
            "A commentary discusses Apple's existing trade-secret accusations and the former employees named in them."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "The Verge")

        self.assertEqual(tier, "weak", reason)

    def test_epic_pause_response_merges_when_legal_action_is_in_first_sentence(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple says Epic's arguments against pausing the case are wrong",
                "Apple responded to Epic's opposition to pausing lower-court proceedings over App Store commissions.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "苹果回应 Epic 反对暂停 App Store 佣金诉讼：对方论点存在谬误",
                "苹果正式回应 Epic 反对暂停下级法院 App Store 佣金诉讼的请求。",
                source="IT之家",
            ),
        ]

        self.assertTrue(
            all("epic-app-store-appeal" in module.article_primary_facets(article) for article in articles)
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_live_official_education_promotion_is_relevant_and_merges_across_languages(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/07/15/apple-2026-back-to-school-offer-rolling-out/",
            title="Apple's 2026 Back to School Offer Just Went Live in Select Countries",
            summary=(
                "Apple's annual Back to School promotion is now live in China, India, Malaysia, "
                "Singapore, and other Asian markets through August 27. Eligible Mac and iPad buyers "
                "can receive AirTags, AirPods, Apple Pencil Pro, or an Apple gift card."
            ),
            feed_time_raw="Wed, 15 Jul 2026 11:48:45 PDT",
            context="featured back to school promotion",
        )
        english = article_for(module, candidate.title, candidate.summary, source="MacRumors")
        chinese = article_for(
            module,
            "苹果 2026 返校季活动开启：中国大陆用户买 Mac / iPad 送 AirTags",
            "苹果返校季教育优惠在八个亚洲市场正式启动，活动持续至 8 月 27 日。",
            source="IT之家",
        )
        airpods_angle = article_for(
            module,
            "苹果 2026 返校季教育优惠开启：免费 AirPods 取消、选耳机需补差价",
            (
                "苹果中国同一返校季活动持续至 8 月 27 日，购买指定 Mac 或 iPad 可享 849 元促销优惠；"
                "选择 AirPods 4、AirPods Pro 3 或 Apple Pencil Pro 时需补不同差价。"
            ),
            source="快科技",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        event = module.cluster_articles([english, chinese, airpods_angle])
        self.assertEqual(len(event), 1)
        self.assertEqual({article.source for article in event[0].articles}, {"MacRumors", "IT之家", "快科技"})

    def test_applecare_price_change_is_distinct_from_ipad_financing_and_keeps_regional_prices(self):
        module = load_module()
        source = source_named(module, "MacRumors")
        applecare_candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/07/15/applecare-plus-price-increase/",
            title="AppleCare+ for Macs and iPads Just Got More Expensive",
            summary=(
                "Apple is increasing AppleCare+ subscription prices for new Mac and iPad plans by "
                "$0.50 per month or $5 per year. Existing subscriptions are unchanged."
            ),
            feed_time_raw="Wed, 15 Jul 2026 14:32:09 PDT",
            context="applecare",
        )
        financing = article_for(
            module,
            "Apple Adds 36-Month Carrier Financing for Cellular iPads",
            (
                "Apple added AT&T and Verizon 36-month financing for cellular iPads. The 11-inch "
                "iPad Pro now starts at $1,399 after an earlier hardware price increase."
            ),
            source="MacRumors",
        )
        applecare = article_for(
            module,
            "苹果提高 Mac、iPad 等产品 AppleCare+ 价格",
            "苹果提高 AppleCare+ 服务计划价格，硬件此前也因内存成本上涨而调价。",
            facts=[
                "Mac mini：原价 649 元，现价 799 元",
                "Mac Studio / iMac：原价 1399 元，现价 1549 元",
                "MacBook Neo：原价 1099 元，现价 1249 元",
                "MacBook Air 13 英寸：原价 1599 元，现价 1749 元",
                "MacBook Air 15 英寸：原价 1899 元，现价 2049 元",
                "MacBook Pro 14 英寸：原价 2299 元，现价 2449 元",
                "MacBook Pro 16 英寸：原价 3299 元，现价 3449 元",
                "Mac Pro：原价 3999 元，无变化",
                "iPad / iPad mini：原价 549 元，现价 649 元",
                "11 英寸 iPad Air（M4）：原价 649 元，现价 749 元",
                "13 英寸 iPad Air（M4）：原价 799 元，现价 899 元",
            ],
            source="IT之家",
        )
        applecare_english = article_for(
            module,
            "AppleCare+ for Macs and iPads Just Got More Expensive",
            "Apple raised new AppleCare+ plans by $0.50 per month or $5 per year; existing subscriptions are unchanged.",
            source="MacRumors",
        )
        applecare_followup = article_for(
            module,
            "Apple bumps monthly AppleCare+ for iPad, Mac by 50 cents",
            "The same AppleCare+ price change raises the monthly plan by 50 cents and annual plan by $5.",
            source="AppleInsider",
        )

        self.assertTrue(module.is_relevant_candidate(applecare_candidate, source))
        events = module.cluster_articles([financing, applecare, applecare_english, applecare_followup])
        self.assertEqual(len(events), 2)
        applecare_event = next(event for event in events if "AppleCare" in event.title)
        self.assertEqual(len(applecare_event.articles), 3)
        for expected in applecare.key_facts:
            self.assertIn(expected, applecare_event.key_facts)
        event_dict = module.event_to_dict(applecare_event, timezone.utc)
        must_include = " ".join(event_dict.get("must_include_facts", []))
        for expected in applecare.key_facts:
            self.assertIn(expected, must_include)

    def test_crashstealer_detail_facts_do_not_downgrade_direct_macos_malware(self):
        module = load_module()
        macrumors = article_for(
            module,
            "CrashStealer Malware Impersonates Apple Tool to Steal Mac Passwords and Crypto",
            (
                "CrashStealer targets macOS, impersonates Apple's crash reporter, and was found in "
                "an Apple-notarized app before Apple revoked its signing credentials."
            ),
            facts=[
                "It targets more than 80 cryptocurrency wallet extensions and 14 password managers including 1Password, LastPass, and Dashlane.",
                "It requests full disk access and uses a native macOS password prompt to access the login keychain.",
            ],
            source="MacRumors",
        )
        nine_to_five = article_for(
            module,
            "Beware of fake Mac crash reports out to steal your passwords",
            "Jamf identified the same malware as CrashStealer after seeing active macOS infections in July.",
            source="9to5Mac",
        )

        self.assertEqual(macrumors.relevance_tier, "strong", macrumors.relevance_reason)
        self.assertEqual(len(module.cluster_articles([macrumors, nine_to_five])), 1)

    def test_china_apple_intelligence_approval_merges_but_suno_imessage_update_stays_weak(self):
        module = load_module()
        direct_articles = [
            article_for(
                module,
                "Apple reaches agreement with Chinese government on Apple Intelligence rollout",
                "Apple Intelligence received regulatory clearance for rollout in China with local partners.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple Intelligence Finally Cleared to Launch in China",
                "Chinese regulators cleared Apple Intelligence for launch in the country.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果 Apple 智能在列，网信部门发布手机端侧生成式人工智能服务备案信息",
                "网信部门公告 Apple 智能完成手机端侧生成式人工智能服务备案。",
                source="IT之家",
            ),
            article_for(
                module,
                "Apple Intelligence finally on the road to release in China",
                "Apple's Chinese partner Alibaba says Qwen will be integrated when Apple Intelligence becomes available in China.",
                source="AppleInsider",
            ),
        ]
        suno = article_for(
            module,
            "Suno 接入 iMessage：苹果 iPhone 用户可在聊天内 AI 生成歌曲",
            "第三方 Suno 应用更新后可从 iMessage 应用抽屉生成歌曲。",
            source="IT之家",
        )

        self.assertTrue(all(article.relevance_tier == "strong" for article in direct_articles))
        self.assertTrue(
            all(
                "apple-intelligence-china-regulatory-rollout" in module.article_primary_facets(article)
                for article in direct_articles
            )
        )
        self.assertEqual(suno.relevance_tier, "weak", suno.relevance_reason)
        events = module.cluster_articles([*direct_articles, suno])
        strong_events = [event for event in events if event.relevance_tier == "strong"]
        self.assertEqual(len(strong_events), 1)
        self.assertEqual(len(strong_events[0].articles), 4)

    def test_ai_chip_acquisition_sources_merge_without_absorbing_china_ai_partner_update(self):
        module = load_module()
        acquisition_articles = [
            article_for(
                module,
                "Apple looks into buying AI chip startups to bolster infrastructure",
                "Apple is contacting semiconductor startups about possible acquisitions for AI server chips.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "消息称苹果正寻求收购人工智能芯片企业",
                "苹果与银行家和半导体初创企业接触，评估用于 AI 服务器芯片的收购。此前曾收购 Q.ai。",
                source="IT之家",
            ),
            article_for(
                module,
                "Apple Reportedly Looking to Acquire AI Chip Companies",
                "Apple may acquire AI chip companies and the report cites its earlier Q.ai and PA Semi deals as background.",
                source="MacRumors",
            ),
        ]
        partner_update = article_for(
            module,
            "阿里回应千问将与苹果 AI 合作：无需切换应用即可调用",
            "阿里千问将作为 AI 能力集成至中国版 Apple 智能。",
            source="快科技",
        )

        events = module.cluster_articles([*acquisition_articles, partner_update])
        acquisition_event = next(
            event for event in events if any("acquire" in article.title.lower() or "收购" in article.title for article in event.articles)
        )
        self.assertEqual(len(acquisition_event.articles), 3)
        self.assertNotIn(partner_update, acquisition_event.articles)

    def test_carrier_financing_lock_policy_merges_across_confirmation_headline_styles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "分期买 iPhone 17 Pro 不再自动解锁：苹果确认新政策",
                "通过 T-Mobile 或 Verizon 分期购买的 iPhone 在付清前保持锁定。",
                source="IT之家",
            ),
            article_for(
                module,
                "Apple Closes Unlocked iPhone Loophole for T-Mobile and Verizon Financing",
                "Apple's purchase FAQ says carrier-financed iPhones will be locked until paid in full.",
                source="MacRumors",
            ),
            article_for(
                module,
                "Apple just closed a popular workaround for buying an unlocked iPhone",
                "AT&T, T-Mobile, and Verizon installment-plan iPhones are now locked until paid off.",
                source="9to5Mac",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_direct_apple_maps_ad_policy_sources_are_strong_and_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Maps won't allow ads from these categories at launch",
                "Apple updated Maps advertising rules to prohibit political ads, bail bonds, crypto ATMs, and home services.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "Apple Won't Allow These Ad Categories in the Maps App",
                "The revised Apple Maps ad policy prohibits the same categories.",
                source="MacRumors",
            ),
            article_for(
                module,
                "苹果更新地图 Apple Maps 广告投放条款：明确禁投家政服务等内容",
                "苹果修订 Apple Maps 广告政策，禁止政治广告、保释担保和加密货币 ATM。",
                source="IT之家",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_direct_apple_battery_regulation_sources_stay_strong_and_merge_despite_competitor_context(self):
        module = load_module()
        english = article_for(
            module,
            "EU Drops Battery Removal Requirement for Apple Watch and AirPods",
            (
                "The EU added a sealed-wearable exemption directly covering Apple Watch and AirPods. "
                "The report also compares Meta glasses and Nintendo hardware."
            ),
            facts=["Apple continues battery service through Apple Stores and authorized providers."],
            source="MacRumors",
        )
        chinese = article_for(
            module,
            "欧盟修改新规为苹果让步：iPhone 等旗下产品不用拆卸电池设计",
            "欧盟修订便携式电池规则；报道将 iPhone 作为苹果设备示例，并说明可穿戴设备新增豁免。",
            source="快科技",
        )
        self.assertEqual(
            module.detect_event_kind(english.title, english.summary, english.key_facts),
            "hardware_market",
        )
        english.event_kind = "retail_store"

        self.assertEqual(english.relevance_tier, "strong", english.relevance_reason)
        self.assertEqual(len(module.cluster_articles([english, chinese])), 1)

    def test_brazil_minor_gambling_app_inquiry_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple faces new questions from Brazil over betting apps accessible to minors",
                "Brazil gave Apple five business days to explain App Store controls for 18+ gambling apps.",
                source="9to5Mac",
            ),
            article_for(
                module,
                "巴西施压苹果，限期说明如何拦截未成年人下载 18+ 博彩应用",
                "巴西监管部门要求苹果说明 App Store 年龄核验、授权检查和下架流程。",
                source="IT之家",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_ui_screen_order_language_is_not_display_panel_supply_chain_evidence(self):
        module = load_module()
        title = "iOS 27 breaks 15 years of muscle memory on iPhone and iPad"
        summary = (
            "Apple changed the top-edge swipe gesture for Notification Center. The screen shows alerts "
            "in chronological order, and Apple says the change will ship this fall."
        )

        self.assertFalse(module.is_apple_display_panel_supply_chain_story(f"{title} {summary}"))
        self.assertEqual(module.detect_event_kind(title, summary), "os_app")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_apple_specific_metrics_in_multi_vendor_report_remain_strong(self):
        module = load_module()
        title = "Omdia：中国大陆智能手机出货量下降 2%，华为苹果逆势大涨"
        summary = (
            "苹果排名第二，出货量 1240 万台、份额 19%，出货量和份额均创历年第二季度新高；"
            "华为、OPPO 等厂商数据也列在报告中。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(tier, "strong", reason)

        market_report = article_for(module, title, summary, source="IT之家")
        product_forecast = article_for(
            module,
            "苹果一芯难求！A18 Pro 产能不足：MacBook Neo 出货量暴降 40%",
            "分析师因 A18 Pro 供应瓶颈将单一 MacBook Neo 年度出货预期从 1000 万台下调至 600 万到 700 万台。",
            source="快科技",
        )
        self.assertNotIn("apple-market-share-report", module.article_primary_facets(product_forecast))
        self.assertIn("apple-product-production-forecast", module.article_primary_facets(product_forecast))
        self.assertFalse(
            module.article_primary_facets(product_forecast)
            & {
                "apple-product-price-increase",
                "apple-current-product-price-increase",
                "apple-future-product-price-forecast",
            }
        )
        self.assertEqual(len(module.cluster_articles([market_report, product_forecast])), 2)

    def test_supplier_wealth_profile_and_rumor_feature_roundup_stay_weak(self):
        module = load_module()
        samples = [
            (
                "靠着 iPhone 等苹果产品，立讯精密创始人成为中国女首富",
                "文章回顾创始人的创业经历和 855 亿元身家，并以历年苹果供应链合作作为背景。",
                "快科技",
            ),
            (
                "Apple Watch Series 12: Four rumored new features coming soon",
                "The roundup recaps four features previously rumored by multiple reports and adds no new reporting.",
                "9to5Mac",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_unrelated_weak_third_party_titles_do_not_merge_from_incidental_apple_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "华为全新轻薄本入网：整机仅重 700g",
                "报道以 MacBook Air 重量作为对比，并介绍鸿蒙跨设备能力。",
                source="快科技",
            ),
            article_for(
                module,
                "华为 Mate 90 定于 9 月中下旬登场",
                "报道将发布时间与 iPhone 18 Pro 对比，并讨论鸿蒙与 iOS 阵营。",
                facts=["华为新机将在 iPhone 18 Pro 发布后登场，并采用新一代麒麟芯片。"],
                source="快科技",
            ),
            article_for(
                module,
                "Nomad Kicks Off Anniversary Sale With Up to 30% Off Sitewide",
                "The third-party sale covers iPhone cases, Apple Watch bands, and charging accessories.",
                facts=[
                    "A related-page fragment says the iPhone 18 Pro will launch in September with a new chip.",
                    "Nomad's iPhone cases are discounted during the anniversary sale.",
                ],
                source="MacRumors",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "weak" for article in articles))
        self.assertEqual(len(module.cluster_articles(articles)), 3)

    def test_non_apple_security_statistics_with_apple_as_comparison_stays_weak(self):
        module = load_module()
        title = "Linux 2308 个漏洞成全球第一！内核大佬喊话微软苹果：你们上报太少了"
        summary = (
            "报告主体是 Linux 内核 CVE 数量和披露机制，并把微软与苹果的漏洞上报数量作为对比，"
            "没有新的 Apple 漏洞、补丁、政策或平台动作。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_subjects_do_not_become_strong_from_incidental_apple_context(self):
        module = load_module()
        samples = [
            (
                "地震预警 App 被质疑会员优先推送消息，研究所发布整改公告",
                (
                    "使用苹果手机打开该第三方 App 时会看到广告；公告称核心地震预警推送和灾害提醒对所有用户"
                    "无差别开放，整改针对会员加速通道文案、预警信息推送和开屏广告。"
                ),
            ),
            (
                "纽约州试点引入机器人老师：课程内容可控、保护隐私",
                "机器人由 Realbotix 提供，课程参考苹果联合创始人沃兹尼亚克开发的教学体系。",
            ),
            (
                "Omdia：2030 年全球录制音乐市场规模将突破 560 亿美元",
                "Spotify、Apple Music 和 YouTube Music 等订阅平台是全球行业增长背景，但没有 Apple Music 专属数据或动作。",
            ),
            (
                "泡泡玛特创始人访问苹果总部，送 LABUBU 给库克和特努斯",
                "第三方公司高管礼节性探访 Apple Park 并赠送玩偶，没有宣布合作、投资、产品或平台动作。",
            ),
        ]

        for title, summary in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
                self.assertEqual(tier, "weak", reason)

    def test_third_party_app_status_with_apple_phone_usage_context_stays_weak(self):
        module = load_module()
        title = "地震预警 App 被质疑会员优先推送消息，研究所发布整改公告"
        summary = (
            "消息称使用苹果手机打开由研究所研发的地震预警 App 时会看到开屏广告，"
            "会员页面还标注预警信息加速通道。"
        )
        facts = [
            "公告称核心地震预警推送和灾害提醒对所有用户免费开放、无差别推送。",
            "研究所已删除会员加速通道的歧义文案，并全面下线开屏广告。",
        ]

        self.assertTrue(
            module.is_third_party_app_or_service_status_story(
                title,
                " ".join([summary, *facts]),
            )
        )
        tier, reason = module.classify_relevance_tier(title, summary, facts, "IT之家")
        self.assertEqual(tier, "weak", reason)

    def test_weak_background_display_facet_does_not_merge_unrelated_product_stories(self):
        module = load_module()
        smart_home = article_for(
            module,
            "Apple's 2026 Smart Home Lineup: New Apple TV, HomePod, and Home Hub",
            (
                "Apple is rumored to be planning several smart-home products, including a home hub with a "
                "7-inch display, a new Apple TV 4K, and new HomePod models. The article is a broad roundup of "
                "previously reported specifications and launch expectations."
            ),
            source="MacRumors",
        )
        huawei_laptop = article_for(
            module,
            "代号玛丽莲·梦露 华为全新轻薄本入网：仅重700g 刷新行业纪录",
            (
                "华为新笔记本通过 3C 认证，爆料称整机约 700g，并搭载鸿蒙系统。"
                "目前华为在售的 MateBook Pro 为 14.2 英寸、重 970g；报道只把 1.23kg 的苹果 "
                "MacBook Air 作为重量对比，还提到屏幕和显示规格。"
            ),
            source="快科技",
        )
        smart_home.relevance_tier = "weak"
        smart_home.relevance_reason = "broad product rumor roundup"
        huawei_laptop.relevance_tier = "weak"
        huawei_laptop.relevance_reason = "non-Apple comparison story"

        self.assertEqual(len(module.cluster_articles([smart_home, huawei_laptop])), 2)

        huawei_event = event_for(module, huawei_laptop)
        with mock.patch.object(
            module,
            "article_primary_facets",
            return_value={"apple-display-panel-spec-rumor"},
        ), mock.patch.object(
            module,
            "event_primary_facets",
            return_value={"apple-display-panel-spec-rumor"},
        ):
            self.assertFalse(module.weak_event_has_title_level_identity(smart_home, huawei_event))

    def test_direct_apple_legal_action_is_not_typed_as_third_party_ecosystem(self):
        module = load_module()
        title = "Apple wins discovery fight over federal agency documents in DOJ case"
        summary = "A federal judge granted Apple's request for agency records in the DOJ antitrust lawsuit."

        self.assertEqual(module.detect_event_kind(title, summary), "legal_antitrust")

    def test_legal_case_person_profile_does_not_merge_with_new_email_development(self):
        module = load_module()
        email = article_for(
            module,
            "An email mistake derailed pre-lawsuit talks between Apple and OpenAI",
            "Newly disclosed emails show a 13-minute mixup that ended pre-lawsuit talks in Apple's hardware trade-secret case.",
            source="9to5Mac",
        )
        profile = article_for(
            module,
            "Tang Tan: The ex-Apple VP at the heart of OpenAI's IP trouble",
            "A profile retraces Tang Tan's career from iPod and iPhone design to his later departure, without a new filing or ruling.",
            source="AppleInsider",
        )

        self.assertEqual(email.relevance_tier, "strong", email.relevance_reason)
        self.assertEqual(profile.relevance_tier, "weak", profile.relevance_reason)
        self.assertEqual(len(module.cluster_articles([email, profile])), 2)

    def test_single_product_shipment_forecast_does_not_merge_with_market_share_report(self):
        module = load_module()
        market_report = article_for(
            module,
            "Omdia：第二季度中国大陆智能手机出货量同比下降 2%，华为苹果逆势大涨",
            "苹果出货量 1240 万台、市场份额 19%，两项数据均创历年第二季度新高。",
            source="IT之家",
        )
        ithome_forecast = article_for(
            module,
            "约 40% 降幅，DigiTimes 下调 2026 苹果 MacBook Neo 笔记本出货量预期至 600~700 万台",
            (
                "DigiTimes 因 A18 Pro 芯片供应限制，将单一 MacBook Neo 年度出货量预期"
                "从 1000 万台下调至 600~700 万台。"
            ),
            source="IT之家",
        )
        fasttech_forecast = article_for(
            module,
            "苹果一芯难求！A18 Pro 产能不足：MacBook Neo 出货量暴降 40%",
            "A18 Pro 供应瓶颈令 MacBook Neo 年度出货目标从 1000 万台下调至 600~700 万台。",
            source="快科技",
        )

        self.assertIn("apple-product-production-forecast", module.article_primary_facets(ithome_forecast))
        events = module.cluster_articles([market_report, ithome_forecast, fasttech_forecast])
        self.assertEqual(len(events), 2)
        forecast_event = next(event for event in events if "MacBook Neo" in event.title)
        self.assertEqual({article.source for article in forecast_event.articles}, {"IT之家", "快科技"})

    def test_detail_page_identity_rejects_non_apple_discovery_context(self):
        module = load_module()
        title = "三星 Galaxy AI 通过大模型服务备案，合作方为百度智能云"
        summary = "中国三星与百度智能云合作，为 Galaxy AI 提供搜索、笔记和语音助手能力。"
        discovery_context = (
            "相关阅读称 Apple Intelligence 已获中国监管批准，将由阿里巴巴和百度提供本地模型。"
        )

        safe_context = module.safe_context_for_detail_article(False, title, summary, discovery_context)

        self.assertEqual(safe_context, "")
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "weak", reason)

    def test_narrative_colon_paragraphs_are_not_mandatory_structured_rows(self):
        module = load_module()
        article = article_for(
            module,
            "Apple Intelligence 获得中国监管批准",
            "中国监管部门完成 Apple Intelligence 手机端侧生成式 AI 服务备案。",
            facts=[
                "7 月 15 日下午，监管部门发布公告：新增 Apple 智能等 7 款服务完成备案。",
                "小米是最直观的例子：去年 9 月送审的服务名称随后发生变化。",
                "把苹果的备案编号单独拎出来看：登记日期为 2025 年 6 月 16 日。",
                "过去两年的上线传闻反复变化：版本从 iOS 18.6 一路传到 iOS 26.4。",
            ],
            source="IT之家",
        )

        self.assertEqual(module.structured_enumerated_data_facts(article), [])

    def test_bullish_analyst_commentary_without_new_rating_action_stays_weak(self):
        module = load_module()
        title = "大摩坚定看涨苹果：iPhone 涨价料成拉升引擎"
        summary = (
            "摩根士丹利分析师认为未来 iPhone 提价可改善盈利，并维持原有增持评级和 360 美元目标价；"
            "报告没有上调或下调评级、目标价，也没有披露新的 Apple 定价行动。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_apple_silicon_driver_certification_is_software_ecosystem_news(self):
        module = load_module()
        title = "苹果 M1/M2 在 Asahi Linux 上拿下 OpenCL 3.1 完整一致性认证"
        summary = (
            "Mesa Rusticl 驱动让运行 Asahi Linux 的 Apple Silicon 成为首个通过 OpenCL 3.1 "
            "完整一致性测试的实现；该成果来自第三方开源社区，并非 Apple 官方发布。"
        )

        self.assertEqual(module.detect_event_kind(title, summary), "os_compatibility")
        self.assertEqual(module.choose_category(title, summary), "software_systems")
        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "ecosystem", reason)

    def test_model_generation_rows_remain_in_price_table_facts(self):
        module = load_module()
        title = "苹果提高 Mac、iPad 等产品 AppleCare+ 价格"
        summary = "苹果上调中国大陆 Mac 三年期与 iPad 两年期 AppleCare+ 方案价格。"
        facts = [
            "11 英寸 iPad Air（M4）：原价 649 元，现价 749 元",
            "11 英寸 iPad Pro（M5）：原价 1299 元，现价 1399 元",
            "13 英寸 iPad Pro（M5）：原价 1449 元，现价 1549 元",
        ]

        self.assertEqual(module.filter_key_facts_for_primary_topic(title, summary, facts), facts)
        article = article_for(module, title, summary, facts=facts, source="IT之家")
        self.assertEqual(module.structured_enumerated_data_facts(article), facts)


if __name__ == "__main__":
    unittest.main()
