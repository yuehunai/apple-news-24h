import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260806_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_named(module, name):
    return next(
        source
        for source in module.build_sources(datetime.now().astimezone())
        if source.name == name
    )


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = facts or []
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 5, tzinfo=timezone.utc),
        published_raw="2026-08-05T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


class AugustSixthRelevanceBoundaryTests(unittest.TestCase):
    def test_product_centered_peer_reviewed_applied_research_is_retained(self):
        module = load_module()
        cases = [
            (
                "MacRumors",
                "Apple Vision Pro Speeds Up Surgery by Almost 20%",
                "A peer-reviewed study of 32 operations found surgeons using Vision Pro as the primary display finished 19% faster: 34.4 minutes instead of 42.7 minutes, with no complications.",
            ),
            (
                "IT之家",
                "研究显示：苹果 Vision Pro 可使泪道手术速度提升 19%",
                "同行评审研究分析 32 例手术，使用 Vision Pro 作为主要显示设备时平均耗时 34.4 分钟，传统显示器为 42.7 分钟，两组均无并发症。",
            ),
        ]

        for source_name, title, summary in cases:
            with self.subTest(source=source_name):
                source = source_named(module, source_name)
                candidate = module.Candidate(
                    source=source_name,
                    url=f"https://example.com/{source_name}/vision-pro-study",
                    title=title,
                    summary=summary,
                )
                tier, reason = module.classify_relevance_tier(title, summary, [], source_name)

                self.assertTrue(module.is_relevant_candidate(candidate, source))
                self.assertEqual(tier, "strong", reason)
                self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
                self.assertEqual(module.choose_category(title, summary), "hardware_products")
                self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 80)

    def test_product_centered_research_merges_across_sources(self):
        module = load_module()
        english = article_for(
            module,
            "Apple Vision Pro Speeds Up Surgery by Almost 20%",
            "Surgeons who wore an Apple Vision Pro as their primary display during a tear duct procedure finished operations 19% faster. A peer-reviewed study of 32 endoscopic surgeries found average operative time was 34.4 minutes with Vision Pro and 42.7 minutes with a traditional monitor.",
            "MacRumors",
        )
        chinese = article_for(
            module,
            "研究显示：苹果 Vision Pro 可使泪道手术速度提升 19%",
            "同行评审研究分析 32 例泪道内窥镜手术，使用 Vision Pro 作为主要显示设备时平均耗时 34.4 分钟，传统显示器为 42.7 分钟。",
            "IT之家",
        )

        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_private_relay_ip_leak_merges_without_requiring_webkit_in_every_source(self):
        module = load_module()
        reports = [
            article_for(
                module,
                "Apple's iCloud Private Relay is Leaking Users' Real IP Addresses",
                "Security researchers found that Apple's paid Safari privacy service can expose a user's real IP address in several cases.",
                "MacRumors",
            ),
            article_for(
                module,
                "研究发现：苹果 iCloud Private Relay 隐私功能会泄露用户真实 IP 地址",
                "研究显示 Passkey 等场景可绕过 iCloud Private Relay，苹果已注意到问题并调查。",
                "IT之家",
            ),
            article_for(
                module,
                "苹果iCloud+隐私功能存重大漏洞：泄露用户真实IP与DNS信息",
                "安全研究人员发现 iCloud Private Relay 的 WebKit 请求会绕过代理，暴露真实 IP 和 DNS 信息。",
                "快科技",
            ),
        ]

        events = module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家", "快科技"})

    def test_concrete_event_format_reporting_merges_with_event_operations(self):
        module = load_module()
        preparation = article_for(
            module,
            "Apple starts preparing for September iPhone event with employee lottery",
            "Apple opened an internal lottery for retail staff to support the September event.",
            "AppleInsider",
        )
        format_report = article_for(
            module,
            "A live iPhone launch seems unlikely, but the event could be live-lier this year",
            "A new report says Apple will likely retain prerecorded keynote segments while adding more live on-stage elements at its September iPhone event.",
            "9to5Mac",
        )

        events = module.cluster_articles([preparation, format_report])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "9to5Mac"})

    def test_event_date_history_remains_weak_and_separate(self):
        module = load_module()
        history = article_for(
            module,
            "iPhone 18 Pro event date: Six years of Apple announcements",
            "The article reviews announcement timing from the last six years to estimate a likely date.",
        )
        preparation = article_for(
            module,
            "Apple starts preparing for September iPhone event with employee lottery",
            "Apple opened an internal lottery for retail staff to support the September event.",
            "AppleInsider",
        )

        events = module.cluster_articles([history, preparation])

        self.assertEqual(len(events), 2)
        self.assertEqual(history.relevance_tier, "weak")

    def test_versioned_os_feature_report_is_not_redeferred_as_roundup(self):
        module = load_module()
        article = article_for(
            module,
            "iPadOS 27 adds two new iPad features I’ve been loving",
            "iPadOS 27 adds an always-visible menu bar option and expands Spotlight with Siri AI capabilities.",
        )

        event = module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)

    def test_versioned_os_feature_reports_keep_platform_and_component_boundaries(self):
        module = load_module()
        messages = article_for(
            module,
            "iOS 27’s best new Messages feature is all about saving you time",
            "iOS 27 gives Messages one-tap suggestions for recently shared codes and addresses.",
        )
        ipad_features = article_for(
            module,
            "iPadOS 27 adds two new iPad features I’ve been loving",
            "iPadOS 27 adds an always-visible menu bar option and expands Spotlight with Siri AI capabilities.",
        )

        groups = module.reconcile_articles(
            [messages, ipad_features],
            profile_for=module.article_reconciliation_profile,
            initial_groups=[[messages, ipad_features]],
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual({article.relevance_tier for article in [messages, ipad_features]}, {"strong"})

    def test_direct_supplier_negotiation_is_separate_from_broad_supplier_market_news(self):
        module = load_module()
        compact_tier, compact_reason = module.classify_relevance_tier(
            "苹果压价策略失灵 长鑫存储拒绝低价供货 - Apple 苹果 - cnBeta.COM",
            "据DigitalDaily，苹果近期与长鑫存储就LPDDR5X等移动DRAM供应价格展开谈判，希望借此降低下一代iPhone及智能设备的制造成本。",
            ["三星电子和SK海力士正积极部署AI内存产品线。"],
            "cnBeta",
        )
        self.assertEqual(compact_tier, "strong", compact_reason)
        direct = article_for(
            module,
            "消息称长鑫拒绝苹果压价，坚持要求内存采购价不低于三星电子和 SK 海力士",
            "苹果与长鑫存储就 LPDDR5X 采购价格谈判，希望降低下一代 iPhone 成本。",
            "IT之家",
        )
        translated_direct = article_for(
            module,
            "苹果压价策略失灵 长鑫存储拒绝低价供货 - Apple 苹果 - cnBeta.COM",
            "据DigitalDaily，苹果近期与长鑫存储就LPDDR5X等移动DRAM供应价格展开谈判，希望降低下一代iPhone成本，但长鑫拒绝进一步压价。",
            "cnBeta",
            facts=[
                "三星电子和 SK 海力士正加速将产能转向 HBM4、LPCAMM2 和企业级 SSD 等高附加值 AI 存储产品。"
            ],
        )
        unrelated = article_for(
            module,
            "华为小米长协锁产能！长鑫：产品不低于甚至高于三星和 SK 海力士",
            "长鑫存储表示不会低价倾销，报道讨论华为、小米等厂商的长期订单。相关阅读称苹果近期与长鑫存储就 LPDDR5X 供应价格谈判。",
            "快科技",
            facts=[
                "相关阅读：苹果近期与长鑫存储就 LPDDR5X 供应价格谈判，希望降低下一代 iPhone 成本。"
            ],
        )
        broad_ram = article_for(
            module,
            "RAM production worldwide is sold out through 2027",
            "Worldwide memory production capacity is sold out at high prices through 2027; Apple is one of many buyers affected.",
            "AppleInsider",
        )

        groups = module.reconcile_articles(
            [direct, translated_direct, unrelated, broad_ram],
            profile_for=module.article_reconciliation_profile,
            initial_groups=[[direct, translated_direct, unrelated, broad_ram]],
        )
        events = module.cluster_articles([direct, translated_direct, unrelated, broad_ram])

        self.assertEqual(
            module.article_source_primary_fact(unrelated),
            "长鑫存储表示不会低价倾销，报道讨论华为、小米等厂商的长期订单。",
        )
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(events), 3)
        self.assertEqual(direct.relevance_tier, "strong", direct.relevance_reason)
        self.assertEqual(translated_direct.relevance_tier, "strong", translated_direct.relevance_reason)
        self.assertEqual(unrelated.relevance_tier, "weak", unrelated.relevance_reason)
        self.assertEqual(broad_ram.relevance_tier, "weak", broad_ram.relevance_reason)
        direct_event = next(event for event in events if direct in event.articles)
        self.assertEqual({article.source for article in direct_event.articles}, {"IT之家", "cnBeta"})

    def test_apple_product_driven_market_forecast_remains_strong_without_industry_noise(self):
        module = load_module()
        english = article_for(
            module,
            "Foldable Smartphone Sales to Rise 20% This Year Due to 'iPhone Ultra'",
            "Global foldable smartphone shipments are expected to grow 20% in 2026, with Apple's first foldable iPhone cited as a main driver.",
            "MacRumors",
        )
        chinese = article_for(
            module,
            "消息称 2026 年全球折叠屏手机出货量预计同比增长 20%，苹果首款折叠 iPhone 成重要驱动力",
            "报告预测全球折叠屏手机出货量同比增长 20%，苹果首次进入该市场被视为主要驱动力。",
            "IT之家",
        )

        events = module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong", events[0].relevance_reason)

    def test_owned_third_party_offers_and_accessory_lists_stay_weak(self):
        module = load_module()
        cases = [
            (
                "These are my favorite Apple Watch accessories of 2026 (so far)",
                "A list of bands, chargers, power banks, stands, and accessories.",
            ),
            (
                "As iPhones get more expensive, T-Mobile launches new 3-year plan",
                "T-Mobile launched its own three-year carrier financing plan for customers buying phones.",
            ),
            (
                "MacPaw is building an on-device AI layer that will work across your Mac apps",
                "MacPaw announced its own AI software layer for third-party Mac applications.",
            ),
            (
                "iPhone Ultra sounds truly deserving of the ‘Ultra’ name",
                "Based on existing rumors, the author says it is fun to speculate about the name and explains personal arguments for and against it.",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(tier, "weak", reason)

    def test_direct_apple_emergency_component_procurement_survives_event_refresh(self):
        module = load_module()
        procurement = article_for(
            module,
            "消息称 iPhone 18 Pro / Ultra 量产遇挑战，苹果紧急抢购 DRAM 内存",
            "苹果正在紧急采购 DRAM，以解决 A20 Pro 封装阶段的内存短缺，并保障 iPhone 18 Pro 与折叠 iPhone 的量产。",
            "IT之家",
        )

        self.assertEqual(procurement.relevance_tier, "strong", procurement.relevance_reason)
        event = module.cluster_articles([procurement])[0]
        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.event_kind, "hardware_market")
        self.assertEqual(event.category, "hardware_products")

    def test_non_apple_supplier_financial_result_with_iphone_background_stays_weak(self):
        module = load_module()
        title = "Even before iPhone 18 Pro mass production, AI drives Foxconn to record profits"
        summary = (
            "Ahead of producing the iPhone 18 Pro and the folding iPhone, Apple's main manufacturer Foxconn "
            "has announced the greatest monthly earnings in its 52-year history, and says it is all down to "
            "AI demand. Reuters reported July revenue of $29.6 billion; future iPhone assembly is later "
            "production background."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)


if __name__ == "__main__":
    unittest.main()
