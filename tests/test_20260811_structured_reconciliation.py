import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "apple_news_20260811_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(
        title,
        summary,
        facts,
        source,
    )
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 11, tzinfo=timezone.utc),
        published_raw="2026-08-11T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(f"{title} {summary}"),
    )


def title_sets(groups):
    return [{article.title for article in group} for group in groups]


class StructuredReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def reconcile(self, articles, initial_groups):
        return self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=initial_groups,
        )

    def test_pattern_extraction_preserves_ascii_boundaries_and_inflections(self):
        from apple_news_core import event_identity

        patterns = (("ship-action", ("ship",)), ("ring-product", ("ring",)))

        self.assertEqual(
            event_identity._extract_patterns(
                "apple ships and shipped the product before shipping ended",
                patterns,
            ),
            {"ship-action"},
        )
        self.assertEqual(
            event_identity._extract_patterns(
                "the service offering is unrelated",
                patterns,
            ),
            set(),
        )

    def test_term_scoring_preserves_ascii_boundaries_cjk_and_wwdc_suffixes(self):
        text = "Pineapple iosish macOS WWDC2026，苹果发布"

        self.assertEqual(
            self.module.score_terms(
                text,
                ["apple", "ios", "macos", "wwdc", "苹果"],
            ),
            3,
        )
        self.assertEqual(self.module.score_terms("xwwdc2026 wwdc20261", ["wwdc"]), 0)

    def test_named_supplier_qualification_for_apple_product_is_direct_hardware_news(self):
        title = "挑战三星显示，消息称面板厂争取为苹果 iPad Air 供应 OLED 面板"
        summary = (
            "The supplier is developing an OLED panel for Apple's iPad Air, will submit samples, "
            "and is seeking qualification as a second supplier before mass production."
        )

        tier, reason = self.module.classify_relevance_tier(
            title,
            summary,
            [],
            "IT之家",
        )

        self.assertEqual(tier, "strong", reason)
        self.assertIn("supplier", reason)
        article = article_for(self.module, title, summary, "IT之家")
        event = self.module.cluster_articles([article])[0]
        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "hardware_products")

    def test_broad_supplier_story_with_incidental_apple_comparison_stays_weak(self):
        title = "Samsung Display expands OLED output for multiple device brands"
        summary = (
            "The broad industry expansion covers Android vendors and mentions Apple's iPad Air "
            "only as a comparison with premium tablets."
        )

        tier, reason = self.module.classify_relevance_tier(
            title,
            summary,
            [],
            "IT之家",
        )

        self.assertEqual(tier, "weak", reason)

    def test_same_attributed_component_cost_report_reconciles_without_manual_event_key(self):
        reports = [
            article_for(
                self.module,
                "TrendForce: iPhone 18 Pro component cost rises 38%",
                "TrendForce estimates the 256GB iPhone 18 Pro bill of materials will rise 38% as DRAM costs increase.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "集邦咨询：预估 iPhone 18 Pro 成本大增近 40%",
                "根据 TrendForce 最新研究，iPhone 18 Pro 256GB 零部件成本预计增加约 38%。",
                "IT之家",
            ),
            article_for(
                self.module,
                "iPhone 18 Pro memory could reach 42% of its bill of materials",
                "A TrendForce report says DRAM may account for 42% of the iPhone 18 Pro bill of materials in 2027.",
                "cnBeta",
            ),
        ]

        groups = self.reconcile(reports, [[article] for article in reports])

        self.assertEqual([len(group) for group in groups], [3], title_sets(groups))

    def test_component_cost_assertion_normalizes_cross_language_headline_variants(self):
        reports = [
            article_for(
                self.module,
                "The iPhone 18 Pro will cost Apple 38% more in parts",
                "A new TrendForce analysis estimates Apple will pay 38% more for iPhone 18 Pro components; the bill of materials is led by memory.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Memory crisis will make iPhone 18 Pro 40% more expensive to manufacture",
                "Analysis from TrendForce says the iPhone 18 Pro bill of materials will rise 38% year over year.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "集邦咨询：预估 iPhone 18 Pro 成本大增近 40%",
                "TrendForce 估算 iPhone 18 Pro 的零部件成本将增加 38%，DRAM 是主要原因。",
                "IT之家",
            ),
        ]

        groups = self.reconcile(reports, [[article] for article in reports])

        self.assertEqual([len(group) for group in groups], [3], title_sets(groups))

    def test_component_cost_buyer_and_rounded_headline_share_report_identity(self):
        precise = article_for(
            self.module,
            "The iPhone 18 Pro will cost Apple 38% more in parts",
            "A new TrendForce analysis estimates that Apple will pay 38% more for "
            "iPhone 18 Pro components than it did for its predecessor.",
            "9to5Mac",
            [
                "TrendForce estimates the 256GB iPhone 18 Pro bill of materials "
                "will rise 38% year over year."
            ],
        )
        rounded = article_for(
            self.module,
            "Memory crisis will make iPhone 18 Pro 40% more expensive to manufacture",
            "The memory crisis is expected to make the iPhone 18 Pro cost Apple "
            "almost 40% more to manufacture than its predecessor.",
            "AppleInsider",
            [
                "TrendForce estimates the iPhone 18 Pro bill of materials will "
                "rise 38% year over year."
            ],
        )

        groups = self.reconcile([precise, rounded], [[precise], [rounded]])

        self.assertEqual([len(group) for group in groups], [2], title_sets(groups))

    def test_attributed_shipment_plan_report_merges_but_denial_stays_separate(self):
        shipment_reports = [
            article_for(
                self.module,
                "Apple Cutting Back 2026 Hardware Shipments Due to Memory Shortage",
                "Apple is scaling back its hardware shipment plans due to DRAM shortages, analyst Ming-Chi Kuo said.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "郭明錤：苹果缩减 iPhone 18 等硬件出货量，因存储短缺",
                "分析师郭明錤发布行业调查，称苹果正在缩减 2026 年硬件出货规划。",
                "快科技",
            ),
            article_for(
                self.module,
                "涨价不可避免：郭明錤称苹果正缩减 2026 年 iPhone 18 Pro 等硬件出货计划",
                "天风国际证券分析师郭明錤指出，由于 DRAM 内存短缺，苹果正在缩减硬件出货计划。",
                "IT之家",
            ),
        ]
        denial = article_for(
            self.module,
            "Kuo denies rumor of $1B Apple chip stockpile at TSMC",
            "Ming-Chi Kuo disputes a report that TSMC is holding unpackaged Apple processors.",
            "AppleInsider",
        )

        groups = self.reconcile(
            [*shipment_reports, denial],
            [[article] for article in [*shipment_reports, denial]],
        )

        self.assertIn({article.title for article in shipment_reports}, title_sets(groups))
        self.assertIn({denial.title}, title_sets(groups))

    def test_project_cancellation_report_merges_without_absorbing_rating_action(self):
        cancellation_reports = [
            article_for(
                self.module,
                "Next year's iPhone redesign with all-glass look might be canceled: report",
                "Jefferies analyst Edison Lee says Apple may have canceled the all-glass 20th anniversary iPhone because of yield problems.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple's All-Glass 20th Anniversary iPhone Reportedly Canceled",
                "A report from Jefferies analyst Edison Lee says Apple canceled the planned all-glass iPhone.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "杰富瑞分析师：因良率不佳，苹果已砍掉 20 周年全玻璃 iPhone 机型",
                "分析师 Edison Lee 称苹果取消了原定的全玻璃周年 iPhone 项目。",
                "IT之家",
            ),
        ]
        rating = article_for(
            self.module,
            "Jefferies downgrades Apple stock, cites all-glass iPhone cancellation rumor",
            "Jefferies lowered its Apple stock rating and cited the cancellation rumor as one reason.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [*cancellation_reports, rating],
            [[article] for article in [*cancellation_reports, rating]],
        )

        self.assertIn({article.title for article in cancellation_reports}, title_sets(groups))
        self.assertIn({rating.title}, title_sets(groups))

    def test_component_development_reconciles_without_merging_product_roadmap(self):
        panel_reports = [
            article_for(
                self.module,
                "苹果 iMac 要换 OLED 屏？消息称 LG Display 正研发 5 层堆叠 OLED 面板",
                "LG Display is developing a five-layer OLED panel for a future Apple iMac.",
                "IT之家",
            ),
            article_for(
                self.module,
                "LG Display develops five-stack OLED panel for Apple's iMac",
                "The supplier is developing a five-layer OLED panel with three blue-emitting layers for a future iMac.",
                "cnBeta",
            ),
        ]
        roadmap = article_for(
            self.module,
            "Apple plans M6 iMac and MacBook Pro updates",
            "A current roadmap says Apple plans M6 updates across several Mac product lines.",
            "AppleInsider",
        )

        groups = self.reconcile(
            [*panel_reports, roadmap],
            [[article] for article in [*panel_reports, roadmap]],
        )

        self.assertIn({article.title for article in panel_reports}, title_sets(groups))
        self.assertIn({roadmap.title}, title_sets(groups))

    def test_seeded_component_development_splits_from_sparse_product_roadmap(self):
        panel = article_for(
            self.module,
            "苹果 iMac 要换 OLED 屏？消息称 LG Display 正研发 5 层堆叠 OLED 面板",
            "LG Display is developing a five-layer OLED panel for a future Apple iMac.",
            "IT之家",
        )
        sparse_roadmap = article_for(
            self.module,
            "Apple iMac roadmap update",
            "The next iMac will use a 24-inch panel and M5 or M6 chip as a routine performance update.",
            "AppleInsider",
        )

        groups = self.reconcile(
            [panel, sparse_roadmap],
            [[panel, sparse_roadmap]],
        )

        self.assertEqual(len(groups), 2, title_sets(groups))
        self.assertIn({panel.title}, title_sets(groups))
        self.assertIn({sparse_roadmap.title}, title_sets(groups))

    def test_seeded_os_feature_splits_from_unrelated_hardware_roadmap(self):
        os_feature = article_for(
            self.module,
            "苹果 iOS 27 Beta 5 隐藏变化：优化 Siri 动画、移除 CarPlay 壁纸",
            "The current iOS beta changes Siri animation and removes CarPlay wallpapers.",
            "IT之家",
        )
        hardware_roadmap = article_for(
            self.module,
            "Apple's All-Glass 20th Anniversary iPhone Reportedly Canceled",
            "A report says Apple canceled the planned all-glass anniversary iPhone.",
            "MacRumors",
        )

        groups = self.reconcile(
            [os_feature, hardware_roadmap],
            [[os_feature, hardware_roadmap]],
        )

        self.assertEqual(len(groups), 2, title_sets(groups))
        self.assertIn({hardware_roadmap.title}, title_sets(groups))
        self.assertIn({os_feature.title}, title_sets(groups))

    def test_related_story_facet_cannot_bridge_os_feature_and_hardware_roadmap(self):
        related_story_noise = (
            " Related story: Apple stopped signing iOS 26.5, preventing users "
            "from downgrading after an update."
        )
        os_feature = article_for(
            self.module,
            "苹果 iOS 27 Beta 5 隐藏变化：优化 Siri 动画、移除 CarPlay 壁纸",
            "The current iOS beta changes Siri animation and removes CarPlay wallpapers."
            + related_story_noise,
            "IT之家",
        )
        hardware_roadmap = article_for(
            self.module,
            "Apple's All-Glass 20th Anniversary iPhone Reportedly Canceled",
            "A report says Apple canceled the planned all-glass anniversary iPhone."
            + related_story_noise,
            "MacRumors",
        )

        groups = self.reconcile(
            [os_feature, hardware_roadmap],
            [[os_feature, hardware_roadmap]],
        )

        self.assertEqual(len(groups), 2, title_sets(groups))
        self.assertIn({hardware_roadmap.title}, title_sets(groups))
        self.assertIn({os_feature.title}, title_sets(groups))

    def test_legal_settlement_evidence_reconciles_sparse_cross_language_titles(self):
        reports = [
            article_for(
                self.module,
                "Apple settles lawsuit over alleged discrimination against Jewish employee",
                "Apple agreed to pay $150,000 to settle a religious discrimination lawsuit filed by the EEOC.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "员工申请安息日休息被解雇，苹果同意支付 15 万美元和解宗教歧视诉讼",
                "苹果将支付 15 万美元，并提供宗教歧视培训。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Discrimination lawsuit involving converted Jewish employee settled by Apple",
                "Apple settled the religious discrimination case for $150,000 after an EEOC lawsuit.",
                "AppleInsider",
            ),
        ]

        groups = self.reconcile(reports, [[article] for article in reports])

        self.assertEqual([len(group) for group in groups], [3], title_sets(groups))

    def test_distinct_attributed_hardware_actions_split_even_when_legacy_seed_mixed_them(self):
        shipment = article_for(
            self.module,
            "郭明錤称苹果因内存短缺缩减 iPhone 18 Pro 等硬件出货计划",
            "分析师郭明錤表示，苹果正在缩减 iPhone、折叠机与 Mac 的 2026 年出货计划。",
            "IT之家",
        )
        component_cost = article_for(
            self.module,
            "TrendForce says iPhone 18 Pro costs nearly 40% more to build",
            "TrendForce estimates a 38% bill-of-materials increase caused by DRAM prices.",
            "9to5Mac",
        )
        oled_panel = article_for(
            self.module,
            "LG Display develops five-stack OLED panel for Apple's iMac",
            "LG Display is developing a five-layer OLED panel for a future iMac.",
            "MacRumors",
        )
        product_roadmap = article_for(
            self.module,
            "Apple plans M6 iMac and MacBook Pro updates for October",
            "A current report says Apple plans an M6 iMac and a 14-inch M6 MacBook Pro for October.",
            "AppleInsider",
        )

        groups = self.reconcile(
            [shipment, component_cost, oled_panel, product_roadmap],
            [[shipment, component_cost], [oled_panel, product_roadmap]],
        )

        self.assertEqual(len(groups), 4, title_sets(groups))
        for article in (shipment, component_cost, oled_panel, product_roadmap):
            self.assertIn({article.title}, title_sets(groups))

    def test_chinese_cost_increase_report_does_not_merge_with_shipment_cut(self):
        cost_report = article_for(
            self.module,
            "集邦咨询：预估 iPhone 18 Pro 成本大增近 40%，内存占比明年或达 42%",
            "TrendForce 估算 iPhone 18 Pro 的零部件成本明显上涨，DRAM 是主要原因。",
            "IT之家",
        )
        shipment_report = article_for(
            self.module,
            "郭明錤称内存短缺迫使苹果缩减 iPhone 18 Pro 出货计划",
            "郭明錤预计苹果将下调多条产品线的出货量。",
            "MacRumors",
        )

        groups = self.reconcile(
            [cost_report, shipment_report],
            [[cost_report, shipment_report]],
        )

        self.assertEqual(
            title_sets(groups),
            [{cost_report.title}, {shipment_report.title}],
        )

    def test_component_cost_report_splits_from_consumer_price_action_in_seed(self):
        component_cost = article_for(
            self.module,
            "Memory crisis will make iPhone 18 Pro 40% more expensive to manufacture",
            "TrendForce estimates the iPhone 18 Pro bill of materials will rise 38% year over year.",
            "AppleInsider",
        )
        retail_price = article_for(
            self.module,
            "Apple Could Raise iPhone 17 Prices When iPhone 18 Pro Debuts",
            "TrendForce says Apple may increase retail prices for the older iPhone 17 lineup.",
            "MacRumors",
        )

        groups = self.reconcile(
            [component_cost, retail_price],
            [[component_cost, retail_price]],
        )

        self.assertEqual(len(groups), 2, title_sets(groups))
        self.assertIn({component_cost.title}, title_sets(groups))
        self.assertIn({retail_price.title}, title_sets(groups))

    def test_measurement_normalization_preserves_integer_trailing_zero(self):
        report = article_for(
            self.module,
            "iPhone 18 Pro costs 40% more to manufacture",
            "TrendForce estimates a 40% increase in component costs.",
            "AppleInsider",
        )

        profile = self.module.article_reconciliation_profile(report)

        self.assertTrue(
            any("percent:40" in key for key in profile.event_keys),
            profile.event_keys,
        )
        self.assertFalse(
            any(key.endswith("percent:4") for key in profile.event_keys),
            profile.event_keys,
        )

    def test_claim_denial_sources_merge_without_absorbing_cost_report(self):
        denials = [
            article_for(
                self.module,
                "Kuo pours water on rumor of $1B Apple chip stockpile at TSMC",
                "Ming-Chi Kuo denies that TSMC holds a $1 billion Apple chip stockpile.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "分析师郭明錤否认台积电为苹果积压十亿美元芯片传闻",
                "郭明錤否认台积电积压价值十亿美元的苹果芯片。",
                "cnBeta",
            ),
        ]
        component_cost = article_for(
            self.module,
            "iPhone 18 Pro memory cost share may reach 42%",
            "TrendForce says memory may account for 42% of the bill of materials.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [*denials, component_cost],
            [[denials[0], component_cost], [denials[1]]],
        )

        self.assertIn({article.title for article in denials}, title_sets(groups))
        self.assertIn({component_cost.title}, title_sets(groups))

    def test_claim_and_direct_followup_share_subject_action_and_measure(self):
        cancellation = article_for(
            self.module,
            "Apple's All-Glass 20th Anniversary iPhone Reportedly Canceled",
            "A new report says the all-glass anniversary iPhone project was canceled.",
            "MacRumors",
        )
        followup = article_for(
            self.module,
            "Apple's 20th-anniversary iPhone redesign reportedly remains on track",
            "A new follow-up counters the cancellation claim and says the anniversary iPhone is still planned.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [cancellation, followup],
            [[cancellation], [followup]],
        )

        self.assertEqual([len(group) for group in groups], [2], title_sets(groups))

    def test_same_numbered_beta_wave_merges_across_platforms_without_absorbing_features(self):
        releases = [
            article_for(
                self.module,
                "Apple Seeds Fifth visionOS 27 Beta to Developers",
                "Apple released visionOS 27 beta 5 to developers.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple Seeds watchOS 27 Beta 5 to Developers",
                "Apple released watchOS 27 beta 5 to developers.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 macOS 27.0 开发者预览版 Beta 5 发布",
                "苹果向开发者发布 macOS 27 beta 5。",
                "IT之家",
            ),
        ]
        feature = article_for(
            self.module,
            "iOS 27 Beta 5 Expands Siri Voice Customization",
            "The current beta adds new voice customization controls to Siri.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [*releases, feature],
            [[releases[0]], [releases[1]], [releases[2]], [feature]],
        )

        self.assertIn({article.title for article in releases}, title_sets(groups))
        self.assertIn({feature.title}, title_sets(groups))

    def test_release_title_can_take_version_from_lead_without_absorbing_feature_report(self):
        macos_release = article_for(
            self.module,
            "Apple Releases macOS Golden Gate Beta 5 to Developers",
            "The fifth beta of macOS Golden Gate is now available to developers.",
            "MacRumors",
        )
        numbered_macos_release = article_for(
            self.module,
            "macOS 27 Golden Gate beta 5 now available to developers",
            "Apple released macOS 27 beta 5 to developers.",
            "9to5Mac",
        )
        feature = article_for(
            self.module,
            "Here’s what’s new with iOS 27 beta 5",
            "The beta changes Siri search behavior and the Settings app.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [macos_release, numbered_macos_release, feature],
            [[macos_release], [numbered_macos_release], [feature]],
        )

        self.assertIn(
            {macos_release.title, numbered_macos_release.title},
            title_sets(groups),
        )
        self.assertIn({feature.title}, title_sets(groups))

    def test_codename_release_uses_same_platform_anchor_when_other_platform_matches_stage(self):
        codename_release = article_for(
            self.module,
            "Apple Releases macOS Golden Gate Beta 5",
            "The fifth beta of macOS Golden Gate is now available to developers.",
            "MacRumors",
        )
        numbered_macos_release = article_for(
            self.module,
            "macOS 27 Golden Gate beta 5 now available to developers",
            "Apple released macOS 27 beta 5 to developers.",
            "9to5Mac",
        )
        ios_release = article_for(
            self.module,
            "Apple Seeds iOS 26 Beta 5 to Developers",
            "Apple released iOS 26 beta 5 to developers.",
            "AppleInsider",
        )

        groups = self.reconcile(
            [codename_release, numbered_macos_release, ios_release],
            [[codename_release], [numbered_macos_release], [ios_release]],
        )

        self.assertIn(
            {codename_release.title, numbered_macos_release.title},
            title_sets(groups),
        )
        self.assertNotIn(
            {codename_release.title, ios_release.title},
            title_sets(groups),
        )

    def test_multiword_first_party_feature_name_reconciles_cross_language_sources(self):
        english = article_for(
            self.module,
            "Apple launches Apple Reference Image for developers",
            "Apple Reference Image is a new first-party image resource for app developers.",
            "MacRumors",
        )
        chinese = article_for(
            self.module,
            "苹果推出 Reference Image 开发者图像资源",
            "Apple Reference Image 面向开发者提供统一的参考图像。",
            "IT之家",
        )

        groups = self.reconcile(
            [english, chinese],
            [[english], [chinese]],
        )

        self.assertEqual([len(group) for group in groups], [2], title_sets(groups))

    def test_explicit_first_party_name_in_key_fact_reconciles_sparse_headline(self):
        sparse = article_for(
            self.module,
            "Apple is working on a way to authenticate that a photo came from an iPhone camera",
            "References in the current iOS 27 beta describe a new photo provenance feature.",
            "9to5Mac",
            [
                "New code shows Apple is working on something called Apple Reference Image, which authenticates the source using iPhone camera hardware.",
            ],
        )
        explicit = article_for(
            self.module,
            "iOS 27 Hints at 'Apple Reference Image' Photo Authentication",
            "Apple Reference Image is a new first-party provenance feature for iPhone photos.",
            "MacRumors",
        )

        events = self.module.cluster_articles([sparse, explicit])

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_direct_first_party_market_entry_and_current_beta_report_are_promoted(self):
        apple_pay = article_for(
            self.module,
            "消息称苹果 Apple Pay 下月进入印度市场，初期支持 Visa、万事达卡",
            "苹果正与印度银行谈判，计划在当地推出 Apple Pay，并按交易收取服务费。",
            "IT之家",
        )
        beta_changes = article_for(
            self.module,
            "Here’s what’s new with iOS 27 beta 5",
            "The newly released beta changes Siri, Safari, Settings, and search behavior.",
            "9to5Mac",
        )
        bank_app = article_for(
            self.module,
            "Example Bank adds Apple Pay support",
            "Example Bank updated its own cards so customers can add them to Apple Pay; Apple made no platform change.",
            "The Verge",
        )

        events = self.module.cluster_articles([apple_pay, beta_changes, bank_app])
        by_title = {
            article.title: event
            for event in events
            for article in event.articles
        }

        self.assertEqual(by_title[apple_pay.title].relevance_tier, "strong")
        self.assertEqual(by_title[beta_changes.title].relevance_tier, "strong")
        self.assertEqual(by_title[bank_app.title].relevance_tier, "weak")

    def test_generic_non_apple_app_store_action_is_not_promoted(self):
        android_store = article_for(
            self.module,
            "The first rival Android app store just arrived in the US Play Store",
            "Following Google's legal dispute with Epic, Android users can download Aptoide from Google Play. Android remains more open than iOS.",
            "The Verge",
        )
        android_store.relevance_tier = "weak"
        android_store.relevance_reason = "non-Apple primary subject"

        event = self.module.cluster_articles([android_store])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_comprehensive_multi_product_rumor_recap_remains_weak(self):
        recap = article_for(
            self.module,
            "iPhone 18 Pro and six more Apple products fully leaked before the event",
            "The article compiles seven products from prior rumors and past release patterns without new reporting.",
            "快科技",
        )

        variants = self.module.compound_article_variants(
            recap.title,
            recap.summary,
            recap.key_facts,
        )
        event = self.module.cluster_articles([recap])[0]

        self.assertEqual(len(variants), 1, variants)
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_chinese_multi_product_leak_recap_does_not_spawn_product_events(self):
        recap = article_for(
            self.module,
            "iPhone 18 Pro 等 7 款苹果新品彻底泄密：发布会再无悬念",
            "文章汇总此前关于多条产品线的爆料，没有提供新的独立调查或消息来源。",
            "快科技",
        )

        variants = self.module.compound_article_variants(
            recap.title,
            recap.summary,
            recap.key_facts,
        )
        event = self.module.cluster_articles([recap])[0]

        self.assertEqual(len(variants), 1, variants)
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_event_countdown_multi_product_preview_does_not_spawn_product_events(self):
        preview = article_for(
            self.module,
            "一个月倒计时！苹果 9 月发布会将推 8 款新品：折叠 iPhone 最受期待",
            "文章综合既有爆料与往年惯例，预览 iPhone、Apple Watch 和 HomePod 等多条产品线，没有新的独立消息源。",
            "快科技",
        )

        variants = self.module.compound_article_variants(
            preview.title,
            preview.summary,
            preview.key_facts,
        )
        event = self.module.cluster_articles([preview])[0]

        self.assertEqual(len(variants), 1, variants)
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_editorial_feature_request_and_personal_complaint_remain_weak(self):
        request = article_for(
            self.module,
            "Apple, please do this to end the guessing game with iPhone app settings",
            "The author argues Apple should redesign settings but reports no new Apple action.",
            "9to5Mac",
        )
        complaint = article_for(
            self.module,
            "罗永浩吐槽：iPhone 第三方输入法不好用，苹果自己的更差",
            "罗永浩在社交媒体分享个人使用感受，苹果没有发布相关更新。",
            "快科技",
        )

        events = self.module.cluster_articles([request, complaint])
        request_identity = self.module.title_led_identity(
            request.title,
            request.summary,
        )

        self.assertTrue(
            all(event.relevance_tier == "weak" for event in events),
            [(event.title, event.relevance_tier, event.relevance_reason) for event in events],
        )
        self.assertNotIn("transaction", request_identity.title_actions)
        self.assertNotIn("content-release", request_identity.title_actions)

    def test_question_led_price_commentary_remains_weak(self):
        commentary = article_for(
            self.module,
            "iPhone 18 系列迎来史上最大涨幅，还值得买吗",
            "文章根据既有传闻讨论购买价值，没有新的报告或 Apple 动作。",
            "快科技",
        )

        event = self.module.cluster_articles([commentary])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_weak_editorial_recap_cannot_attach_to_strong_report(self):
        commentary = article_for(
            self.module,
            "iPhone 18 系列迎来史上最大涨幅，还值得买吗",
            "文章根据既有成本传闻讨论购买价值，没有新的报告。",
            "快科技",
        )
        report = article_for(
            self.module,
            "TrendForce: iPhone 18 Pro component cost rises 38%",
            "TrendForce estimates that the bill of materials will rise 38%.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [commentary, report],
            [[commentary, report]],
        )

        self.assertEqual(len(groups), 2, title_sets(groups))
        self.assertIn({commentary.title}, title_sets(groups))
        self.assertIn({report.title}, title_sets(groups))

    def test_third_party_luxury_custom_product_remains_weak(self):
        custom = article_for(
            self.module,
            "iPhone 18 Pro 高奢定制版上架：可选鳄鱼皮，售价 6.8 万元起",
            "Caviar 网站上架了自行改装的奢侈定制版，Apple 没有发布或销售该产品。",
            "快科技",
        )

        event = self.module.cluster_articles([custom])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_generic_beta_release_titles_reconcile_without_absorbing_feature_story(self):
        releases = [
            article_for(
                self.module,
                "Fifth developer betas of iOS 27 and macOS 27 land",
                "Apple released the fifth developer beta wave across its operating systems.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple Releases macOS Golden Gate Beta 5",
                "Apple released the fifth macOS Golden Gate beta to developers.",
                "MacRumors",
            ),
        ]
        feature = article_for(
            self.module,
            "iOS 27 Beta 5 Brings New Icons for Siri, Safari, and Settings",
            "The fifth beta changes several first-party app icons.",
            "MacRumors",
        )

        groups = self.reconcile(
            [*releases, feature],
            [[article] for article in [*releases, feature]],
        )

        self.assertIn({article.title for article in releases}, title_sets(groups))
        self.assertIn({feature.title}, title_sets(groups))

    def test_same_beta_change_roundup_reconciles_without_absorbing_specific_feature(self):
        roundups = [
            article_for(
                self.module,
                "Here’s what’s new with iOS 27 beta 5",
                "A current roundup covers the app icons, Liquid Glass, search, and Siri changes in beta 5.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Everything New in iOS 27 Beta 5",
                "This roundup lists all currently discovered changes in the fifth beta.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 iOS / iPadOS 27 Beta 5 更新汇总：图标、搜索和 Siri 迎来变化",
                "文章汇总第五个测试版中已经发现的多项系统变化。",
                "IT之家",
            ),
        ]
        specific = article_for(
            self.module,
            "iOS 27 beta 5 expands Siri voice customization",
            "The beta adds British English controls for Siri pace and expressivity.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [*roundups, specific],
            [[article] for article in [*roundups, specific]],
        )

        self.assertIn({article.title for article in roundups}, title_sets(groups))
        self.assertIn({specific.title}, title_sets(groups))

    def test_same_versioned_app_icon_redesign_reconciles_as_concrete_change(self):
        icon_reports = [
            article_for(
                self.module,
                "iOS 27 beta 5 adds new app icons for Siri, Safari, and more",
                "The fifth beta redesigns icons for several built-in apps.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "iOS 27 Beta 5 Brings New Icons for Siri, Safari, Settings and More",
                "Apple redesigned the built-in app icons in the same fifth beta.",
                "MacRumors",
            ),
        ]
        release = article_for(
            self.module,
            "Apple Seeds Fifth iOS 27 Beta to Developers",
            "Apple released iOS 27 beta 5 to developers.",
            "AppleInsider",
        )
        roundup = article_for(
            self.module,
            "Here’s what’s new with iOS 27 beta 5",
            "A roundup covers icons, search, Liquid Glass, and Siri changes in beta 5.",
            "9to5Mac",
        )

        groups = self.reconcile(
            [*icon_reports, release, roundup],
            [[icon_reports[0], roundup], [icon_reports[1]], [release]],
        )

        self.assertIn({article.title for article in icon_reports}, title_sets(groups))
        self.assertIn({release.title}, title_sets(groups))
        self.assertIn({roundup.title}, title_sets(groups))

    def test_background_app_removal_cannot_override_primary_os_release_identity(self):
        release = article_for(
            self.module,
            "苹果推送 iOS 27 等多个系统的第五开发者预览版 - Apple 苹果 - cnBeta.COM",
            "苹果发布 iOS 27、macOS 27 与 watchOS 27 Beta 5。后文回顾另一事件中 App Store 曾下架第三方应用。",
            "cnBeta",
        )
        companion = article_for(
            self.module,
            "Apple Seeds Fifth iOS 27 Beta to Developers",
            "Apple released iOS 27 beta 5 to developers.",
            "MacRumors",
        )

        profile = self.module.article_reconciliation_profile(release)
        events = self.module.cluster_articles([release, companion])

        self.assertFalse(
            any(key.startswith("app-store-removal:") for key in profile.event_keys),
            profile.event_keys,
        )
        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(events[0].merge_warnings, [])

    def test_third_party_custom_modification_does_not_become_an_apple_hardware_event(self):
        custom = article_for(
            self.module,
            "iPhone 18 Pro 高奢定制版上架：售价 6.8 万元起",
            "Caviar 网站上架了自己改装的鳄鱼皮和黄金定制版，苹果尚未发布这款手机。",
            "IT之家",
        )

        event = self.module.cluster_articles([custom])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_third_party_brand_ios_app_update_remains_weak(self):
        update = article_for(
            self.module,
            "Meta 扩充 iOS 应用矩阵：Creator Studio 强化社交与 AI 能力",
            "Meta 为自己的 Creator Studio 应用增加发布和 AI 工具，Apple 没有改变 iOS 或 App Store 政策。",
            "IT之家",
        )

        identity = self.module.article_title_led_event_identity(update)
        event = self.module.cluster_articles([update])[0]

        self.assertEqual(identity.scope, "third-party-context")
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_independent_open_source_interop_tool_remains_weak(self):
        tool = article_for(
            self.module,
            "BlueFerry 上线：通过蓝牙让 Linux 直接收发 iPhone 消息",
            "这是托管在 GitHub 的独立开源项目，使用现有蓝牙协议显示和回复消息；Apple、Linux 发行版和平台所有者均未发布系统更新。",
            "IT之家",
        )

        event = self.module.cluster_articles([tool])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_same_evidenced_supply_claim_denial_reconciles_across_languages(self):
        denials = [
            article_for(
                self.module,
                "Kuo pours water on rumor of $1B Apple chip stockpile at TSMC",
                "Ming-Chi Kuo denies that TSMC is holding $1 billion of unpackaged Apple processors.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "分析师郭明錤否认台积电为苹果积压十亿美元芯片传闻",
                "郭明錤反驳台积电为苹果积压十亿美元芯片的报道。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "郭明錤否认台积电积压苹果芯片：不存在 10 亿美元 A20 Pro 等待封装",
                "郭明錤称台积电没有价值 10 亿美元的 A20 Pro 库存等待封装。",
                "快科技",
            ),
        ]

        groups = self.reconcile(
            denials,
            [[article] for article in denials],
        )

        self.assertEqual([len(group) for group in groups], [3], title_sets(groups))

    def test_supplier_sourcing_reconciles_without_absorbing_shipment_plan_change(self):
        sourcing_feasibility = article_for(
            self.module,
            "China now even less likely to solve Apple's memory crunch",
            (
                "Apple considered buying RAM from CXMT and YMTC, but government scrutiny, "
                "supplier capacity, pricing, and qualification constraints make that sourcing "
                "plan less likely."
            ),
            "9to5Mac",
        )
        shipment_reduction = article_for(
            self.module,
            "Apple cutting 2026 hardware shipments due to memory shortage",
            (
                "Apple is reducing its 2026 hardware shipment plan to match the DRAM capacity "
                "available across its product lines."
            ),
            "MacRumors",
        )
        supplier_testing = article_for(
            self.module,
            "Apple tested Chinese memory chips for Mac",
            (
                "Apple is testing CXMT DRAM as a possible component supplier for Macs sold in "
                "China, subject to qualification and regulatory approval."
            ),
            "AppleInsider",
        )

        groups = self.reconcile(
            [sourcing_feasibility, shipment_reduction, supplier_testing],
            [[sourcing_feasibility, shipment_reduction], [supplier_testing]],
        )

        self.assertIn(
            {sourcing_feasibility.title, supplier_testing.title},
            title_sets(groups),
        )
        self.assertIn({shipment_reduction.title}, title_sets(groups))

    def test_component_shortage_context_is_not_a_supplier_sourcing_action(self):
        shortage = article_for(
            self.module,
            "Apple cuts device shipments as memory supply tightens",
            "The company reduced its shipment plan because DRAM availability remains limited.",
            "MacRumors",
        )

        identity = self.module.article_title_led_event_identity(shortage)

        self.assertNotIn("component-supplier-sourcing", identity.components)
        self.assertIn("hardware-shipment-plan-change", identity.components)

    def test_immersive_sports_sources_merge_without_regular_tv_schedule(self):
        immersive = [
            article_for(
                self.module,
                "Apple Vision Pro to stream live MLB games in Immersive Video",
                "Apple is making another foray into live Apple Immersive content and will stream four MLB games live in Apple Immersive Video for Vision Pro.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Announces 3D MLB Games Coming to Vision Pro",
                "Apple and MLB today released the September schedule for Apple TV's weekly Friday Night Baseball doubleheader. The games are included with an Apple TV subscription at no additional cost, and there is a new perk for Vision Pro users. For the first time, Friday Night Baseball will be streamed live in the Apple Immersive format.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Some more Vision Pro content for Baseball fans",
                "Starting on Friday, August 28th, Apple will begin streaming Friday Night Baseball in immersive video on Apple Vision Pro. The stream will feature commentary from various analysts and reporters, and live graphics will be anchored around the viewers space during the game.",
                "The Verge",
            ),
            article_for(
                self.module,
                "Friday Night Baseball season will stream key games live in Apple Immersive",
                "Apple and Major League Baseball have announced the first games of their new season, and in the US and certain other countries, many will be streamed in Immersive Video to Apple Vision Pro users.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果将为 Vision Pro 用户沉浸式直播四场周五夜棒球赛",
                "苹果正在再次探索 Apple Immersive 沉浸式内容体验，并将通过 Apple Immersive Video 为 Vision Pro 直播同样四场 MLB 比赛。",
                "IT之家",
            ),
        ]
        schedule = article_for(
            self.module,
            "Apple, MLB announce September Friday Night Baseball schedule",
            "Apple published the regular September Apple TV game schedule.",
            "Apple Newsroom",
        )

        groups = self.reconcile(
            [*immersive, schedule],
            [
                [immersive[0], immersive[4]],
                [immersive[2], immersive[1], immersive[3]],
                [schedule],
            ],
        )

        self.assertIn({article.title for article in immersive}, title_sets(groups))
        self.assertIn({schedule.title}, title_sets(groups))


if __name__ == "__main__":
    unittest.main()
