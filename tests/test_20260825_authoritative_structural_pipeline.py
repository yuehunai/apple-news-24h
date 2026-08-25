import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "apple_news_20260825_authoritative_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(
    module,
    title,
    summary,
    source,
    *,
    facts=None,
    tier=None,
    reason=None,
    category=None,
):
    facts = list(facts or [summary])
    observed_tier, observed_reason = module.classify_relevance_tier(
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
        category=category or module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 25, tzinfo=timezone.utc),
        published_raw="2026-08-25T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier or observed_tier,
        relevance_reason=reason if reason is not None else observed_reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class AuthoritativeStructuralPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_non_apple_metric_comparison_overrides_legacy_strong_tier(self):
        article = article_for(
            self.module,
            "突破500万分：小米玄戒 O3 性能领先苹果 A19 Pro",
            "小米发布玄戒 O3 并公布跑分，Apple A19 Pro 只作为性能比较对象。",
            "快科技",
            tier="strong",
            reason="legacy Apple silicon performance match",
            category="hardware_products",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_first_person_multi_product_preview_does_not_project_background_mentions(self):
        title = "Apple is about to launch five new products that I’m very excited for"
        facts = [
            "The first foldable iPhone is almost here, and I am excited to see how iOS adapts.",
            "It has been four years since the current Apple TV 4K launched.",
            "I have used an iPad Pro as my main computer for over a decade.",
            "MacBook Ultra, I suspect, could bring touch support and OLED.",
            "I am undecided whether to choose Apple Watch Series 12 or Ultra 4.",
        ]

        variants = self.module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(len(variants), 1, variants)
        projected = article_for(
            self.module,
            variants[0][0],
            variants[0][1],
            "9to5Mac",
            facts=variants[0][2],
        )
        event = self.module.cluster_articles([projected])[0]
        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_versioned_first_party_os_release_without_apple_prefix_is_promoted(self):
        article = article_for(
            self.module,
            "Second Release Candidates for macOS Tahoe 26.7 and macOS Sequoia 15.8 now available",
            "Apple is rolling out the second release candidates with builds 25G224 and 24H20.",
            "9to5Mac",
            tier="weak",
            reason="legacy third-party platform classification",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
        self.assertEqual(event.category, "software_systems")

    def test_explanatory_retrospective_does_not_become_a_current_os_event(self):
        article = article_for(
            self.module,
            "How Apple Leaked Itself",
            "The release candidate last week contained references already reported in previous builds, and this article explains how branches may have been merged.",
            "MacRumors",
            tier="strong",
            reason="legacy OS release classification",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_structured_reconciler_splits_legacy_recall_bridges(self):
        reports = [
            article_for(
                self.module,
                "Handy disk image tool is to be removed from macOS",
                "Apple deprecated hdiutil in macOS 27 and recommends diskutil image instead.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "macOS 27 已标记弃用磁盘镜像工具 hdiutil，苹果推荐改用 diskutil",
                "苹果已将 hdiutil 标记为弃用，未来会移除，并推荐 diskutil image。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Ted Lasso season 5 begins filming in London",
                "Apple TV production on Ted Lasso season 5 is scheduled to begin in London in January.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "曝《足球教练》第五季明年 1 月在伦敦开拍",
                "Apple TV 剧集《足球教练》（Ted Lasso）第五季计划于明年 1 月启动制作。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Smart TV analytics report lower Apple TV F1 viewership",
                "Samba TV measured a four percent decline in its connected-TV sample for Apple F1 races.",
                "AppleInsider",
            ),
        ]
        events = self.module.cluster_articles(reports)

        owners = [
            {article.title for article in event.articles}
            for event in events
        ]
        self.assertEqual(sorted(len(owner) for owner in owners), [1, 2, 2], owners)
        self.assertTrue(
            any(
                "Handy disk image tool is to be removed from macOS" in owner
                and any("hdiutil" in title.lower() for title in owner)
                for owner in owners
            ),
            owners,
        )
        self.assertTrue(
            any(any("Ted Lasso" in title for title in owner) and any("足球教练" in title for title in owner) for owner in owners),
            owners,
        )
        self.assertTrue(
            any(len(owner) == 1 and "F1" in next(iter(owner)) for owner in owners),
            owners,
        )

    def test_store_app_assistant_merges_across_languages_as_software(self):
        reports = [
            article_for(
                self.module,
                "Apple Store app is testing an AI shopping assistant",
                "Apple is rolling out an early preview of a virtual shopping assistant in the Apple Store app.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果 Apple Store 应用 AI 助手进入早期预览",
                "苹果开始向部分用户测试 Apple Store 应用内的虚拟购物助手。",
                "IT之家",
                category="hardware_products",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].category, "software_systems")

    def test_apple_tv_key_fact_action_can_promote_and_merge_a_sparse_headline(self):
        reports = [
            article_for(
                self.module,
                "Ted Lasso season 5 gets a new status update",
                "A new report says the next season may arrive sooner than expected.",
                "9to5Mac",
                facts=[
                    "Multiple sources say Ted Lasso season 5 production is set to kick off in January for the Apple TV comedy."
                ],
                tier="weak",
                reason="Apple term appears only outside a title-led direct Apple event",
            ),
            article_for(
                self.module,
                "'Ted Lasso' season 5 begins filming in London",
                "Apple TV production on Ted Lasso season 5 will begin in London in January.",
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")

    def test_home_hub_profile_feature_merges_as_software(self):
        reports = [
            article_for(
                self.module,
                "Home Hub code hints at face-based profile switching",
                "macOS code shows Apple's Home Hub can identify a face and switch personal profiles.",
                "MacRumors",
                tier="weak",
                reason="legacy weak roadmap classifier",
            ),
            article_for(
                self.module,
                "Ambient sensing and cameras to power Apple Home Hub personalization",
                "Apple Home Hub code describes cameras, ambient sensing and automatic profile switching.",
                "AppleInsider",
                tier="weak",
                reason="legacy weak roadmap classifier",
            ),
            article_for(
                self.module,
                "代码显示苹果 HomeHub 支持识别人脸并自动切换不同账号",
                "macOS 代码显示 HomeHub 会识别用户面容并切换个人配置文件。",
                "IT之家",
                category="hardware_products",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")

    def test_apple_ai_server_internal_photos_merge_as_hardware(self):
        reports = [
            article_for(
                self.module,
                "This is the first look at the inside of Apple's AI servers",
                "Photos show the internal layout of Apple's Private Cloud Compute server hardware in a custom 2U chassis.",
                "AppleInsider",
                category="software_systems",
            ),
            article_for(
                self.module,
                "苹果 AI 服务器内部结构首曝：采用定制 2U 机架",
                "图片展示苹果自研 AI 服务器内部布局、计算单元和散热结构。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].category, "hardware_products")

    def test_iphone_anniversary_design_comparison_target_is_not_a_new_subject(self):
        reports = [
            article_for(
                self.module,
                "iPhone 20's curved glass design to be made like iPhone Air",
                "The anniversary iPhone will use a curved glass assembly derived from iPhone Air manufacturing.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "iPhone 20 will look like a rounder and thinner iPhone Air",
                "The anniversary model will use more rounded glass and improve thinness and heat dissipation.",
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_public_beta_wave_uses_primary_release_not_background_developer_beta(self):
        reports = [
            article_for(
                self.module,
                "New public betas now available for iOS 27, iPadOS 27, macOS 27, more",
                (
                    "Following the seventh developer betas, Apple is rolling out the "
                    "corresponding public builds, marking the fifth public beta rollout."
                ),
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Releases Fifth Public Betas of iOS 27, iPadOS 27, macOS 27, and tvOS 27",
                "The fifth public betas arrive a few hours after the seventh developer betas.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果发布 iOS / iPadOS 27 第 5 个公测版，整合 Beta 7 相关改进",
                "本次第五个公开测试版整合第七个开发者测试版的改进。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_current_event_schedule_reports_merge_across_headline_forms(self):
        reports = [
            article_for(
                self.module,
                "iPhone 18 Pro and iPhone Ultra: When Will Apple Event Be Announced?",
                (
                    "Bloomberg reports the Apple event will take place on or around "
                    "September 9, with the iPhone 18 Pro and iPhone Ultra expected."
                ),
                "MacRumors",
                tier="weak",
                reason="analysis or opinion without a new standalone Apple action",
            ),
            article_for(
                self.module,
                "苹果秋季发布会大概率定档 9 月 10 日，邀请函即将发布",
                "多方消息称 iPhone 18 Pro 发布会可能在美国时间 9 月 9 日举行。",
                "快科技",
            ),
            article_for(
                self.module,
                "iPhone 18 Pro 与折叠屏 iPhone 即将登场，苹果秋季发布会何时举办？",
                "报道分析 Apple 将在 9 月 9 日前后举行 iPhone 18 Pro 发布会。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "hardware_products")

    def test_retrospective_beta_explainer_does_not_claim_current_disclosure_from_old_assets(self):
        article = article_for(
            self.module,
            "How Apple Leaked Itself",
            "A release candidate last week contained product references.",
            "MacRumors",
            facts=[
                "The article explains how internal development branches were merged.",
                "All product references except one had appeared in previous software.",
            ],
            tier="strong",
            reason="legacy OS release classification",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_hardware_roadmap_background_does_not_claim_ceo_transition(self):
        reports = [
            article_for(
                self.module,
                "Apple Holds Farewell Party for Tim Cook as Ternus Prepares to Take Over",
                "Apple held a farewell party for Tim Cook before John Ternus takes over as CEO.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "New Mac mini days away, OLED iPad mini in October, AirPods 5 in 2026",
                "A new hardware roadmap says the Mac mini is days away and the OLED iPad mini is planned for October.",
                "AppleInsider",
                facts=[
                    "AirPods 5 are expected in 2026 as part of the same product roadmap.",
                    "The report also notes that Tim Cook is preparing to step down and John Ternus is expected to become CEO.",
                ],
                category="hardware_products",
            ),
            article_for(
                self.module,
                "古尔曼：苹果可能在“未来几天内”发布新款 Mac mini",
                "新款 Mac mini 可能在 iPhone 18 Pro 发布会前亮相，并测试过 M5 和 M6 芯片。",
                "IT之家",
                facts=[
                    "古尔曼称新款 Mac mini 可能成为库克卸任前最后一款新品。",
                ],
                category="hardware_products",
            ),
        ]

        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in reports
        }
        groups = self.module.reconcile_articles(
            reports,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[[article] for article in reports],
        )

        self.assertEqual(
            sorted(len(group) for group in groups),
            [1, 2],
            [[article.title for article in group] for group in groups],
        )
        self.assertTrue(
            any(
                len(group) == 2 and all("Mac mini" in article.title for article in group)
                for group in groups
            ),
            [[article.title for article in group] for group in groups],
        )

    def test_same_wallet_transit_card_availability_merges_across_title_angles(self):
        reports = [
            article_for(
                self.module,
                "苹果钱包上线郑州绿城通交通卡：乘当地公交车 8 折、地铁 9.5 折",
                "苹果钱包现已支持郑州绿城通交通卡，可用于当地公交和地铁。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苦等五年！苹果iPhone终于上线绿城通交通卡：全国互联",
                "iPhone 用户现可在苹果钱包添加绿城通交通卡，并使用全国互联服务。",
                "快科技",
                facts=[
                    "绿城通交通卡现已加入苹果钱包。",
                    "该卡可在全国支持互联互通的交通一卡通线路使用。",
                ],
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual(len(events[0].articles), 2)

    def test_current_multi_product_launch_report_projects_product_scoped_facts(self):
        title = "New Mac mini days away, OLED iPad mini in October, AirPods 5 in 2026"
        facts = [
            "According to Bloomberg, a new Mac mini could be announced within the next few days.",
            "AirPods 5 are expected to launch in September in standard and ANC versions.",
            "The OLED iPad mini remains scheduled to launch in October.",
        ]

        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            "Bloomberg reported separate current launch windows for three Apple products.",
            facts,
        )

        self.assertEqual(len(variants), 3, variants)
        by_title = {variant_title: variant_facts for variant_title, _summary, variant_facts in variants}
        self.assertTrue(any("Mac mini" in value for value in by_title), by_title)
        self.assertTrue(any("iPad mini" in value for value in by_title), by_title)
        self.assertTrue(any("AirPods" in value for value in by_title), by_title)
        for variant_title, variant_facts in by_title.items():
            if "Mac mini" in variant_title:
                self.assertFalse(any("AirPods" in fact or "iPad mini" in fact for fact in variant_facts))

    def test_multi_product_projection_splits_sentences_and_ignores_excluded_background_subject(self):
        title = "传新款Mac mini将于数日内发布 OLED iPad mini或定档10月"
        facts = [
            "苹果或将在未来几天内推出新一代 Mac mini。若消息属实，新机很快亮相。",
            "除 Mac mini 外，第五代 AirPods 有望提供主动降噪和标准版，并最快在9月亮相。届时 iPhone 18 Pro 也将发布。",
            "配备 OLED 屏幕的新款 iPad mini 仍有望在10月推出。同期还有 iMac 和 MacBook Pro 更新。",
        ]

        variants = self.module.multi_product_hardware_roadmap_variants(
            title,
            "报道称苹果的多款硬件进入不同发布窗口。",
            facts,
        )

        projected_titles = {variant_title for variant_title, _summary, _facts in variants}
        self.assertEqual(len(variants), 3, variants)
        self.assertTrue(any("Mac mini" in value for value in projected_titles), projected_titles)
        self.assertTrue(any("iPad mini" in value for value in projected_titles), projected_titles)
        self.assertTrue(any("AirPods" in value for value in projected_titles), projected_titles)
        self.assertFalse(any("iPhone" in value for value in projected_titles), projected_titles)

    def test_same_hardware_launch_window_reconciles_with_action_before_or_after_product(self):
        reports = [
            article_for(
                self.module,
                "Apple could debut two AirPods 5 models next month, per report",
                "Bloomberg reports that Apple could announce AirPods 5 at its September event.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "AirPods 5 to Launch as Early as Next Month",
                "Apple plans to launch AirPods 5 in standard and ANC versions in September.",
                "MacRumors",
            ),
        ]
        profiles = {
            id(article): self.module.article_reconciliation_profile(article)
            for article in reports
        }

        groups = self.module.reconcile_articles(
            reports,
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[[article] for article in reports],
        )

        self.assertEqual(len(groups), 1, [[article.title for article in group] for group in groups])

    def test_projected_product_launch_does_not_merge_with_different_feature_analysis(self):
        reports = [
            article_for(
                self.module,
                "Apple iPhone Ultra roadmap update",
                "The foldable iPhone Ultra is expected to launch at Apple's September event.",
                "cnBeta",
                category="hardware_products",
            ),
            article_for(
                self.module,
                "Five features the iPhone Ultra reportedly won't have",
                "The article analyzes five capabilities that may be absent from the foldable iPhone.",
                "9to5Mac",
                category="hardware_products",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_third_party_customized_apple_device_is_not_promoted_as_apple_price_action(self):
        article = article_for(
            self.module,
            "全球限量17台！纯银定制折叠iPhone Ultra亮相：售价约12.7万元",
            (
                "奢华定制品牌 Caviar 推出纯银改装版折叠 iPhone Ultra 模型；"
                "硬件参数和最终外观都没有获得苹果确认。"
            ),
            "快科技",
            category="hardware_products",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)


if __name__ == "__main__":
    unittest.main()
