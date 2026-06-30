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

    def test_third_party_charger_with_iphone_compatibility_stays_weak(self):
        module = load_module()
        title = "绿联 25W 磁吸无线充电器发售：适配苹果 iPhone 12-17 系列，139 元"
        summary = "绿联新推出一款 25W 磁吸无线充电器，配 1.5m 编织线，适配 iPhone 12 至 iPhone 17 系列。"

        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(module.detect_event_kind(title, summary), "third_party_ecosystem")
        self.assertEqual(tier, "weak", reason)

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

        self.assertIn(("apple-product-data-leak", ()), module.event_summary_merge_keys(event))

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


if __name__ == "__main__":
    unittest.main()
