import importlib.util
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260804_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = facts or []
    kind = module.detect_event_kind(title, summary, facts)
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((title, summary)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 4, tzinfo=timezone.utc),
        published_raw="2026-08-04T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=kind,
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


def partitions(events):
    return {frozenset(article.title for article in event.articles) for event in events}


class AugustFourthBoundaryTests(unittest.TestCase):
    def test_hot_text_normalizers_are_bounded_memoized_functions(self):
        module = load_module()
        self.assertTrue(hasattr(module.title_and_lead_scope, "cache_info"))
        self.assertTrue(hasattr(module.clean_sentence, "cache_info"))

    def test_non_apple_discovery_candidate_exits_before_semantic_classification(self):
        module = load_module()
        source = next(
            source
            for source in module.build_sources(datetime.now().astimezone())
            if source.name == "The Verge"
        )
        candidate = module.Candidate(
            source="The Verge",
            url="https://www.theverge.com/example",
            title="A third-party game studio announces a new console release",
            summary="The company detailed its launch schedule and pricing.",
            feed_time_raw="2026-08-04T00:00:00Z",
            context="",
        )
        module.is_non_apple_primary_legal_story_with_incidental_apple_context = (
            lambda *args: (_ for _ in ()).throw(AssertionError("semantic path should not run"))
        )

        self.assertFalse(module.is_relevant_candidate(candidate, source))

    def test_key_fact_topic_analysis_is_reserved_for_possible_boundary_changes(self):
        module = load_module()
        title = "关键零部件免税：苹果印度制造 iPhone 成本下降"
        summary = "印度延长苹果合同制造设备和零部件的税收优惠。"
        same_topic = "相关税收优惠有效期将延长至 2041 年，并继续覆盖 iPhone 制造设备。"
        different_topic = "另一份泄露披露 iPhone 18 Pro 的 A20 Pro 芯片和主板设计。"

        self.assertFalse(
            module.key_fact_requires_topic_boundary_analysis(title, summary, same_topic)
        )
        self.assertTrue(
            module.key_fact_requires_topic_boundary_analysis(title, summary, different_topic)
        )

    def test_source_discovery_runs_independent_sources_concurrently(self):
        module = load_module()
        sources = module.build_sources(datetime.now().astimezone())[:2]
        barrier = threading.Barrier(2, timeout=1.0)
        thread_ids = set()

        def fake_collect(source, cache_dir, diagnostics):
            thread_ids.add(threading.get_ident())
            barrier.wait()
            return [
                module.Candidate(
                    source=source.name,
                    url=f"https://example.com/{source.name}",
                    title=f"Apple action from {source.name}",
                    summary="Apple announced a concrete update.",
                    feed_time_raw="2026-08-04T00:00:00Z",
                    context="",
                )
            ]

        module.collect_candidates = fake_collect
        candidates = module.collect_candidates_from_sources(
            sources,
            Path("/tmp/apple-news-source-concurrency-test"),
            {},
        )

        self.assertEqual([candidate.source for candidate in candidates], [source.name for source in sources])
        self.assertEqual(len(thread_ids), 2)

    def test_multi_family_iphone_report_splits_only_on_exclusive_subject_facts(self):
        module = load_module()
        title = "折叠屏与二十周年纪念款一同到来，苹果 iPhone 新机多重细节曝光"
        summary = (
            "苹果首款折叠 iPhone 的量产瓶颈已经解决，仍按原计划推进。"
            "另一方面，二十周年纪念版 iPhone 将使用更大的 VC 均热板和玻璃机身。"
            "iPhone 18 Pro 则有望采用 A20 芯片和可变光圈镜头。"
        )
        variants = module.compound_article_variants(title, summary, [])

        self.assertEqual(len(variants), 3, variants)
        variant_texts = [f"{variant_title} {variant_summary}" for variant_title, variant_summary, _ in variants]
        self.assertTrue(any("foldable" in value.lower() and "量产瓶颈" in value for value in variant_texts))
        self.assertTrue(any("anniversary" in value.lower() and "均热板" in value for value in variant_texts))
        self.assertTrue(any("iphone 18" in value.lower() and "可变光圈" in value for value in variant_texts))

    def test_manufacturing_tax_incentive_is_not_a_retail_discount(self):
        module = load_module()
        title = "苹果迎来利好：印度计划延长电子代工设备税收优惠至 2041 年"
        summary = (
            "印度政府拟将外国企业向合同制造商提供设备的所得税豁免延长至 2041 年，"
            "覆盖手机、平板和可穿戴设备，预计 2026 年生产全球 26% 的 iPhone。"
        )
        source = next(
            source
            for source in module.build_sources(datetime.now().astimezone())
            if source.name == "IT之家"
        )
        candidate = module.Candidate(
            source="IT之家",
            url="https://www.ithome.com/0/985/264.htm",
            title=title,
            summary=summary,
            feed_time_raw="2026-08-04T06:53:24+08:00",
            discovered_from="https://www.ithome.com/tags/apple/",
            context="",
        )

        self.assertFalse(module.is_routine_retail_discount_story(title, f"{title} {summary}"))
        self.assertTrue(module.is_relevant_candidate(candidate, source))
        self.assertEqual(
            module.classify_relevance_tier(title, summary, [], "IT之家")[0],
            "strong",
        )

    def test_direct_apple_siri_cost_policy_is_not_a_competitor_comparison(self):
        module = load_module()
        title = "库克称苹果正评估算力成本，iOS 27 的 Siri AI 额度方案尚未敲定"
        summary = (
            "苹果 CEO 蒂姆·库克在财报电话会上称，公司仍在评估 Siri AI 的算力成本与收费方式。"
            "苹果尽可能在设备端本地处理任务，部分任务会使用私有云计算，另有任务会调用 Google Gemini；"
            "iCloud+ 是否提供额外额度尚未决定。"
        )
        self.assertFalse(module.is_non_apple_device_comparison_story(title, summary))
        tier, _ = module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "strong")

    def test_attributed_apple_ai_cost_decision_survives_a_long_explanatory_lead(self):
        module = load_module()
        title = "Heavy Siri AI usage could cost more than expected after Cook's comment"
        summary = (
            "Outgoing Apple CEO Tim Cook discussed Siri AI usage costs during the earnings call. "
            "Apple will use on-device processing, Private Cloud Compute, and Google Gemini servers. "
            + ("The article explains server processing and iCloud subscription tiers. " * 28)
            + "Cook said the company has not yet decided the allowance model and is considering paid add-on usage limits."
        )

        self.assertTrue(module.is_direct_apple_ai_service_cost_policy_story(title, summary))
        self.assertFalse(module.is_non_apple_device_comparison_story(title, summary))
        self.assertEqual(
            module.classify_relevance_tier(title, summary, [], "9to5Mac")[0],
            "strong",
        )

    def test_apple_ai_cost_policy_uses_key_fact_for_cross_source_identity(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Heavy Siri AI usage could cost more than expected after Cook's comment",
                "Apple CEO Tim Cook discussed Siri AI server costs, iCloud+ tiers, and paid usage limits.",
                "9to5Mac",
                ["Cook said Apple has not yet decided the allowance model and is considering paid add-ons."],
            ),
            article_for(
                module,
                "库克称苹果正评估算力成本，iOS 27 的 Siri AI 额度方案尚未敲定",
                "苹果 CEO 蒂姆·库克称公司仍在评估 Siri AI 的算力成本、收费方式和 iCloud+ 额度。",
                "IT之家",
                ["相关计划尚未形成完整方案，苹果会观察高级功能的市场反响。"],
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(
            module.article_primary_facets(articles[0]),
            {"apple-ai-service-cost-policy"},
        )

    def test_price_forecast_does_not_merge_with_another_generation_market_report(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18系列预计最高涨价1350元 折叠屏至少13500元起售",
                "Mark Gurman 称 iPhone 18 系列预计涨价 100 至 200 美元。",
                "快科技",
            ),
            article_for(
                module,
                "苹果第二季度手机营收创历史新高！iPhone 17系列立大功 竞品涨价送助攻",
                "Counterpoint 报告称苹果在 2026 年第二季度占全球智能手机营收的 49%。",
                "cnBeta",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 2, partitions(events))

    def test_icloud_post_employment_access_and_bug_submission_quota_stay_separate(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Confidential Apple files followed former employees to OpenAI through iCloud",
                "Former Apple employees retained access to confidential work files through personal iCloud storage after leaving. "
                "The disclosure follows Apple's lawsuit against OpenAI and former employees over trade secrets.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果为遏制 AI 生成垃圾漏洞报告采取配额限制措施",
                "苹果限制安全漏洞提交数量，并在达到配额后设置 30 天冷静期。研究公司使用 OpenAI ChatGPT "
                "生成报告，并发现一个 macOS 提权漏洞；苹果漏洞奖金最高可达 500 万美元。",
                "cnBeta",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 2, partitions(events))

    def test_hardware_leadership_rehire_merges_and_stays_hardware(self):
        module = load_module()
        common = (
            "Incoming Apple CEO John Ternus rehired Laura Legros, a retired vice president of hardware engineering, "
            "to coordinate product delivery and engineering teams in the United States."
        )
        articles = [
            article_for(
                module,
                "John Ternus recruits key Apple hardware VP out of retirement ahead of CEO transition",
                common,
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple's Next CEO Adds Retired Hardware Executive to His Team",
                common,
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 9 月换帅前，候任 CEO 特努斯返聘 2022 年退休副总裁勒格罗斯",
                "苹果候任 CEO 约翰·特努斯重新聘用硬件工程与产品管理副总裁劳拉·勒格罗斯。",
                "IT之家",
            ),
            article_for(
                module,
                "苹果罕见召回退休副总裁：准 CEO 特努斯开始组建自己班底",
                "特努斯重新启用负责硬件工程、产品交付和开发时间表的勒格罗斯。",
                "快科技",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].category, "hardware_products")

        chinese_identity = module.article_title_led_event_identity(articles[2])
        self.assertNotIn(
            "primary-intent:executive-retrospective",
            chinese_identity.title_components,
        )
        self.assertFalse(
            module.is_direct_apple_leadership_strategy_story(
                articles[2].title,
                " ".join([articles[2].summary, *articles[2].key_facts]),
            )
        )

    def test_hardware_leadership_rehire_does_not_absorb_tenure_commentary(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 9 月换帅前，候任 CEO 特努斯返聘 2022 年退休副总裁勒格罗斯",
                "特努斯重新聘用负责硬件工程和产品交付的勒格罗斯。",
                "IT之家",
            ),
            article_for(
                module,
                "库克最会赚的钱 继任未必收得到",
                "库克称交接正在顺利推进，约翰·特努斯将接任 CEO。文章回顾库克十五年任期，并分析"
                "苹果服务收入从 13.88 亿美元增至 307 亿美元、占总营收 28%。",
                "快科技",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 2, partitions(events))

    def test_hardware_leadership_background_product_does_not_merge_with_product_shortage(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果罕见召回退休副总裁：准 CEO 特努斯开始组建自己班底",
                "勒格罗斯将负责硬件工程和产品交付；她曾在发布会上介绍 MacBook Air。",
                "快科技",
            ),
            article_for(
                module,
                "MacBook Air Experiencing Major Shortage Despite Price Increase",
                "MacBook Air shipments face a major memory supply shortage and delivery delays.",
                "MacRumors",
            ),
        ]
        self.assertEqual(len(module.cluster_articles(articles)), 2)

    def test_india_manufacturing_tax_reports_merge_as_hardware(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "India Moves to Extend Tax Break Apple Lobbied For",
                "India proposed extending until 2041 tax breaks for foreign companies supplying machinery and equipment to Apple's contract manufacturers; US and China production are background comparisons.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple’s contract manufacturing tax breaks in India could be extended to 2041",
                "The amendment would extend tax relief for equipment used by Apple contract manufacturers in India.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果迎来利好：印度计划延长电子代工设备税收优惠至 2041 年",
                "印度拟延长苹果合同制造设备税收豁免，覆盖 iPhone、iPad 和可穿戴设备。",
                "IT之家",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertIn(
            "india-tariff-iphone-manufacturing",
            module.article_primary_facets(articles[0]),
        )
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(events[0].merge_warnings, [])

    def test_same_icloud_backdoor_legal_challenge_merges_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Launches New Legal Challenge Against UK Backdoor Demand",
                "US-based Apple filed a second legal challenge against a UK order demanding access to encrypted iCloud data.",
                "MacRumors",
            ),
            article_for(
                module,
                "UK faces new legal challenge from Apple over backdoor access to iCloud data",
                "Apple challenged the UK's renewed demand for a backdoor to encrypted iCloud backups.",
                "AppleInsider",
            ),
            article_for(
                module,
                "英国再次要求设立“后门”获取加密数据，苹果提起法律诉讼进行反击",
                "苹果针对英国要求访问 iCloud 加密数据的命令提起第二项法律挑战。",
                "IT之家",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].merge_warnings, [])

    def test_same_first_party_content_promotion_merges_without_absorbing_other_content(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple announces Ted Lasso look-alike contest happening in NYC",
                "Apple TV announced a Ted Lasso look-alike contest in New York City.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Got 'Ted Energy?' Apple is holding a 'Ted Lasso' look-alike contest",
                "Apple is holding a Ted Lasso look-alike contest tied to the Apple TV series.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple Will Judge Your Mustache Authenticity at Its Ted Lasso Look-Alike Contest",
                "Ted Lasso season four premieres this week, and Apple is hosting the same look-alike contest in New York.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple TV shares trailer for a different upcoming series",
                "Apple TV released a trailer for an unrelated drama.",
                "MacRumors",
            ),
        ]
        events = module.cluster_articles(articles)
        self.assertTrue(all(article.event_kind == "service_content" for article in articles[:3]))
        self.assertEqual(
            partitions(events),
            {
                frozenset(
                    {
                        "Apple announces Ted Lasso look-alike contest happening in NYC",
                        "Got 'Ted Energy?' Apple is holding a 'Ted Lasso' look-alike contest",
                        "Apple Will Judge Your Mustache Authenticity at Its Ted Lasso Look-Alike Contest",
                    }
                ),
                frozenset({"Apple TV shares trailer for a different upcoming series"}),
            },
        )

    def test_cross_source_apple_health_sync_reports_form_one_ecosystem_event(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Google Health adds two-way Apple Health syncing on iPhone for Fitbit",
                "Google Health now provides two-way syncing between Fitbit data and Apple Health on iPhone.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Fitbit Data Can Finally Sync to Apple Health",
                "Fitbit workouts and health data can now sync directly into Apple Health.",
                "MacRumors",
            ),
            article_for(
                module,
                "Your Fitbit data can now connect directly to Apple Health",
                "Google Health added direct Fitbit data integration with Apple Health.",
                "The Verge",
            ),
            article_for(
                module,
                "时隔 12 年，iOS 版谷歌健康补齐和苹果健康双向数据同步兼容性缺口",
                "谷歌健康现可在 iPhone 上与苹果健康双向同步 Fitbit 健康和运动数据。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "ecosystem")

    def test_apple_health_sharing_wording_keeps_the_same_integration_identity(self):
        module = load_module()
        article = article_for(
            module,
            "Google Health now shares Fitbit workouts with Apple Health",
            "Google Health shares Fitbit workout and health data directly with Apple Health on iPhone.",
            "AppleInsider",
        )

        self.assertEqual(
            module.article_primary_facets(article),
            frozenset({"apple-health-data-sync"}),
        )
        self.assertEqual(article.relevance_tier, "ecosystem")

    def test_direct_apple_accessories_page_reports_merge_as_first_party_change(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple launches revamped Apple Accessories shopping experience",
                "Apple redesigned its official Apple Accessories shopping page with themed collections, search, and filters.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果官网升级配件页面：扩展主题种草清单，完善筛选和搜索体验",
                "苹果官网重做官方配件购物页面，增加主题清单、筛选和搜索功能。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_direct_cross_device_clipboard_reports_merge_across_tiers(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Plans iPhone-to-Windows Copy and Paste in EU After Microsoft Request",
                "Apple plans cross-device clipboard sharing between iPhone and Windows PCs in the EU.",
                "MacRumors",
            ),
            article_for(
                module,
                "微软提出请求后，苹果计划在欧盟推出 iPhone 与 Windows 跨设备复制粘贴功能",
                "苹果将按欧盟互操作要求支持 iPhone 与 Windows 跨设备剪贴板。",
                "IT之家",
            ),
            article_for(
                module,
                "iPhone to Windows clipboard sharing coming to iOS 28 in the EU",
                "Apple will add iPhone-to-Windows copy and paste interoperability in the EU.",
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "ecosystem")

    def test_exact_clipboard_action_does_not_absorb_unrelated_iphone_roadmap(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 Windows 终于打通：iPhone 将与 PC 跨设备互通剪贴板",
                "苹果计划支持 iPhone 与 Windows 跨设备复制粘贴。",
                "快科技",
            ),
            article_for(
                module,
                "Apple iPhone 18 hardware roadmap update",
                "苹果折叠 iPhone 的量产问题已经解决，二十周年纪念款还将升级散热和影像。",
                "cnBeta",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 2)

    def test_exact_clipboard_action_is_not_bridged_by_a_shared_iphone_token(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Iphone 18 hardware roadmap update",
                "iPhone 18 may use an A20 chip and a variable-aperture camera after a delayed roadmap.",
                "cnBeta",
            ),
            article_for(
                module,
                "苹果 Windows 终于打通：iPhone 将与 PC 跨设备互通剪贴板",
                "苹果计划在 iOS 28 支持 iPhone 与 Windows 双向复制粘贴。",
                "快科技",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 2, partitions(module.cluster_articles(articles)))

    def test_russia_app_preinstall_case_merges_without_weak_source_split(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple faces new antitrust case in Russia over state-backed apps",
                "Russia opened an antitrust case against Apple over mandatory local app preinstallation.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Russia escalates dispute with Apple over mandatory app preinstallation",
                "Russia's FAS escalated its proceeding against Apple for not preinstalling state-backed apps.",
                "9to5Mac",
            ),
            article_for(
                module,
                "俄罗斯联邦反垄断局起诉苹果公司，指控其未按要求预装本土 App",
                "俄罗斯监管机构针对苹果未预装本土应用提起反垄断案件。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_russia_app_preinstall_identity_outweighs_generic_regulatory_facet(self):
        module = load_module()
        article = article_for(
            module,
            "未预装俄制官方应用 俄罗斯对苹果公司发起反垄断诉讼 - Apple 苹果 - cnBeta.COM",
            (
                "俄罗斯联邦反垄断局因苹果拒绝在 iPhone 和 iPad 上预装 Max 与 RuStore "
                "而正式立案，苹果可能面临 40 亿卢布罚款。历史背景还提到苹果曾在俄区 "
                "App Store 移除 VPN 应用，并因应用内支付系统受到反垄断处罚。"
            ),
            "cnBeta",
        )

        self.assertEqual(
            module.article_primary_facets(article),
            frozenset({"russia-fas-app-preinstall-regulation"}),
        )

    def test_app_store_delisting_and_restoration_reports_form_one_ecosystem_event(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Telegram briefly pulled from the App Store over child sexual abuse material availability",
                "Telegram disappeared from Apple's App Store worldwide and was restored after a brief delisting.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Telegram 在多个国家和地区苹果 App Store 下架，现已恢复上架",
                "Telegram 曾从苹果 App Store 下架，随后恢复上架。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "ecosystem")

    def test_direct_apple_hardware_rumors_outweigh_comparison_background(self):
        module = load_module()
        airpods = article_for(
            module,
            "AirPods With Cameras Could Arrive Sooner Than Expected",
            "Apple is developing camera-equipped AirPods and the product roadmap may move forward sooner than expected.",
            "MacRumors",
        )
        iphone = article_for(
            module,
            "iPhone 18 Pro 首次搭载可变光圈镜头：光圈参数与华为 Pura 80 Pro 保持一致",
            "苹果 iPhone 18 Pro 被曝采用可变光圈主摄，华为机型仅用于参数比较。",
            "快科技",
        )
        competitor = article_for(
            module,
            "华为 Mate 90 Pro Max 首发麒麟 9050 Pro 与双层 OLED",
            "该机将对标 iPhone 18 Pro Max，并采用华为自有芯片、屏幕和相机方案。",
            "快科技",
        )

        self.assertEqual(airpods.relevance_tier, "strong")
        self.assertEqual(iphone.relevance_tier, "strong")
        self.assertEqual(competitor.relevance_tier, "weak")
        self.assertEqual(len(module.cluster_articles([iphone, competitor])), 2)

    def test_skeptical_price_commentary_is_not_upgraded_as_a_hardware_rumor(self):
        module = load_module()
        tier, reason = module.classify_relevance_tier(
            "A $1,399 starting price for the iPhone 18 Pro doesn't seem credible",
            (
                "Two sources suggest a $1,399 starting price, but the author says it is hard to "
                "believe and asks readers whether the increase sounds realistic."
            ),
            [],
            "9to5Mac",
        )

        self.assertEqual(tier, "weak", reason)

    def test_unsourced_multi_product_calendar_is_deferred_as_a_roundup(self):
        module = load_module()
        tier, reason = module.classify_relevance_tier(
            "Apple will launch five new products next month, here’s what’s coming",
            (
                "The list recaps rumors about iPhone 18 Pro, iPhone Ultra, Apple Watch Series 12, "
                "HomePod mini 2, and HomePod 3 without a new report or Apple announcement."
            ),
            [],
            "9to5Mac",
        )

        self.assertEqual(tier, "weak", reason)

    def test_retrospective_siri_evaluation_without_new_action_is_deferred(self):
        module = load_module()
        tier, reason = module.classify_relevance_tier(
            "苹果终于补齐 Siri 短板，但重磅升级依然显得平淡",
            "升级后的 Siri AI 已在 7 月发布的 iOS 27 测试版中亮相，本文评价其市场影响。",
            [],
            "cnBeta",
        )

        self.assertEqual(tier, "weak", reason)


if __name__ == "__main__":
    unittest.main()
