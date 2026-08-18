import importlib.util
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260818_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 18, tzinfo=timezone.utc),
        published_raw="2026-08-18T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class AuthoritativeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def reconcile(self, articles, initial_groups=None):
        return self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=initial_groups or [[article] for article in articles],
        )

    def test_legacy_seed_requires_positive_identity_evidence(self):
        pairs = [
            [
                article_for(
                    self.module,
                    "A serious Mac screen sharing vulnerability is being actively exploited",
                    "Apple says attackers are exploiting CVE-2026-65400 in macOS Screen Sharing.",
                ),
                article_for(
                    self.module,
                    "Apple rolls out macOS Tahoe 26.7 and macOS Sequoia 15.8 RCs",
                    "Apple released two separate macOS release candidates to developers.",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Apple says DOJ discovery challenge fails at every level",
                    "Apple opposed the DOJ bid to overturn a discovery ruling in its antitrust case.",
                ),
                article_for(
                    self.module,
                    "Michigan women sue Apple over AirTag anti-stalking failures",
                    "Two women filed a separate product-liability lawsuit over AirTag alerts.",
                    "AppleInsider",
                ),
            ],
        ]
        for pair in pairs:
            with self.subTest(titles=[article.title for article in pair]):
                groups = self.reconcile(pair, [pair])
                self.assertEqual(len(groups), 2)

    def test_positive_seed_identity_is_preserved(self):
        reports = [
            article_for(
                self.module,
                "Apple agrees to change App Tracking Transparency in Germany",
                "German regulators reached an agreement with Apple over the ATT consent prompt.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "德国监管机构要求苹果调整 App 广告数据授权规则",
                "苹果同意在德国修改同一 App Tracking Transparency 授权弹窗。",
                "IT之家",
            ),
        ]
        groups = self.reconcile(reports, [reports])
        self.assertEqual(len(groups), 1)

    def test_unique_canonical_titles_are_not_group_level_identity_evidence(self):
        reports = [
            article_for(
                self.module,
                "Apple fixes an actively exploited macOS Screen Sharing vulnerability",
                "Apple says attackers exploited CVE-2026-65400.",
            ),
            article_for(
                self.module,
                "Apple releases macOS 26.7 RC to developers",
                "The release candidate is available for developer testing.",
            ),
        ]
        profiles = [self.module.article_reconciliation_profile(article) for article in reports]
        supported = self.module.supported_reconciliation_event_keys(profiles)
        self.assertFalse(
            any(key.startswith("structured-canonical-title:") for key in supported)
        )

    def test_public_beta_title_overrides_developer_beta_background(self):
        article = article_for(
            self.module,
            "苹果发布 iOS / iPadOS 27 第 4 个公测版：更新通知动画等",
            (
                "苹果在发布 iOS / iPadOS 27 Beta 6 数小时后，向 Apple Beta 用户发布"
                "第 4 个公开测试版，内部版本号为 24A5418b。"
            ),
            "IT之家",
        )
        profile = self.module.article_reconciliation_profile(article)
        release_keys = {
            key for key in profile.event_keys if key.startswith("apple-os-release-wave:")
        }
        self.assertEqual(release_keys, {"apple-os-release-wave:27:beta-4"})

    def test_developer_and_public_beta_waves_split_without_platform_key_suffix(self):
        developer = article_for(
            self.module,
            "Apple Seeds iOS 27 Beta 6 to Developers",
            "Apple released the sixth developer beta of iOS 27.",
        )
        public = article_for(
            self.module,
            "苹果发布 iOS 27 第 4 个公测版",
            "苹果面向公测用户发布 iOS 27 第四个公开测试版。",
            "IT之家",
        )
        groups = self.reconcile([developer, public], [[developer, public]])
        self.assertEqual(len(groups), 2)

    def test_unnumbered_public_beta_title_does_not_join_developer_beta(self):
        developer = article_for(
            self.module,
            "Apple Seeds iOS 27 Beta 6 to Developers",
            "Apple released developer beta 6 for iOS 27 through the Settings app.",
        )
        public = article_for(
            self.module,
            "Apple Releases New iOS 27, iPadOS 27, macOS 27, and tvOS 27 Public Betas",
            "These are the fourth public betas, available through Settings after developer beta 6.",
            "MacRumors",
        )
        events = self.module.cluster_articles([developer, public])
        self.assertEqual(len(events), 2)

    def test_generic_feature_assertion_cannot_bridge_different_release_waves(self):
        developer = article_for(
            self.module,
            "Apple Seeds iOS 27 Beta 6 to Developers",
            "Apple released developer beta 6 for iOS 27.",
        )
        public = article_for(
            self.module,
            "Apple Releases iOS 27 Public Beta 4",
            "Apple released the fourth public beta of iOS 27.",
        )
        shared = "structured-assertion:os-feature:ios:settings:feature-change"
        profiles = {}
        for article in (developer, public):
            profile = self.module.article_reconciliation_profile(article)
            profiles[id(article)] = replace(
                profile,
                event_keys=frozenset({*profile.event_keys, shared}),
            )
        groups = self.module.reconcile_articles(
            [developer, public],
            profile_for=lambda article: profiles[id(article)],
            initial_groups=[[developer], [public]],
        )
        self.assertEqual(len(groups), 2)

    def test_incidental_lead_product_cannot_bridge_fitness_and_wallet_actions(self):
        fitness = article_for(
            self.module,
            "Apple Fitness+ hiring points to live production work",
            "Apple is hiring a producer for Fitness+; the service can use Apple Watch workout data.",
        )
        wallet = article_for(
            self.module,
            "Apple Wallet IDs expand to four more states",
            "Apple is expanding Wallet IDs; Apple Watch support is mentioned as background.",
            "MacRumors",
        )
        groups = self.reconcile([fitness, wallet], [[fitness, wallet]])
        self.assertEqual(len(groups), 2)

    def test_att_policy_action_does_not_merge_with_app_store_review_commentary(self):
        att = article_for(
            self.module,
            "German regulators reach agreement with Apple on App Tracking Transparency",
            "Apple agreed to change the ATT consent prompt after a regulatory investigation.",
            "AppleInsider",
        )
        review_commentary = article_for(
            self.module,
            "苹果 App Store 审查机制漏洞遭质疑",
            "开发者举报虚假评分和评论未被及时发现，媒体质疑应用审核承诺。",
            "cnBeta",
        )
        groups = self.reconcile(
            [att, review_commentary],
            [[att, review_commentary]],
        )
        self.assertEqual(len(groups), 2)

    def test_compound_report_product_projections_remain_separate_events(self):
        variants = [
            article_for(
                self.module,
                "Apple Beats roadmap update",
                "System code contains identifiers for two unreleased Beats products.",
            ),
            article_for(
                self.module,
                "Apple iMac roadmap update",
                "System code contains J833 and J834 identifiers for future iMac models.",
            ),
            article_for(
                self.module,
                "Apple iPhone Ultra roadmap update",
                "System code contains a V68 identifier for the foldable iPhone Ultra.",
            ),
        ]
        for article in variants:
            article.url = "https://example.com/compound-product-code-report"
        events = self.module.cluster_articles(variants)
        self.assertEqual(len(events), 3)
        self.assertEqual(len({event.event_id for event in events}), 3)

    def test_weak_third_party_app_cannot_be_promoted_by_hardware_seed(self):
        hardware = article_for(
            self.module,
            "Apple camera-equipped AirPods roadmap update",
            "Apple system code contains image-stream references for unreleased camera-equipped AirPods.",
            "MacRumors",
        )
        app = article_for(
            self.module,
            "AirBuddy 3 now available with new widgets and automation",
            "The third-party Mac app adds controls for managing AirPods.",
            "9to5Mac",
        )
        events = self.module.cluster_articles([hardware, app])
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(event.relevance_tier for event in events), ["strong", "weak"])

    def test_platform_edition_third_party_app_remains_weak(self):
        title = "Mac 版 AirBuddy 3 发布：增强苹果 AirPods 管理，带来 150+ 项改动"
        summary = (
            "独立开发者发布 AirBuddy 3，为 Mac 用户提供 AirPods 管理、小组件和自动化功能。"
        )
        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(
            title,
            summary,
            [],
            "IT之家",
        )
        self.assertEqual(identity.scope, "third-party-context")
        self.assertEqual(tier, "weak", reason)

    def test_source_editorial_form_survives_roundup_item_projection(self):
        source_title = "This iPad keyboard case is the perfect addition to our back-to-school tech roundup"
        variants = [
            (
                "Anker Nano Power Strip",
                "Anker's power strip charges a MacBook, iPhone, iPad, and AirPods from one desk clamp.",
                ["The third-party power strip is part of a back-to-school shopping roundup."],
            ),
            (
                "Apple AirPods Max 2",
                "The shopping roundup describes the existing AirPods Max 2 and links to a retailer.",
                ["No new Apple product action is reported."],
            ),
        ]
        for title, summary, facts in variants:
            tier, reason = self.module.classify_projected_article_relevance(
                source_title,
                title,
                summary,
                facts,
                "9to5Mac",
            )
            self.assertEqual(tier, "weak", reason)

    def test_action_owner_not_apple_product_reference_controls_relevance(self):
        cases = [
            (
                "待机功耗直降80%！老款MacBook Pro独显高热难题被根治：降低显存频率就行",
                "一位 Reddit 用户发布自研 Windows 工具，将旧款 MacBook Pro 的 GPU 待机功耗从 14W 降至 3W。",
                "快科技",
            ),
            (
                "剑指苹果 MacBook Neo：联想 IdeaPad Vibe 笔记本规格曝光",
                "Windows Latest 曝光联想 IdeaPad Vibe 14 和 15 的规格，MacBook Neo 只是竞争参照。",
                "IT之家",
            ),
            (
                "比MacBook Neo更轻！宏碁非凡Go Air上新Wildcat Lake版：售5099元",
                "宏碁推出自己的 Windows 笔记本，标题仅用 MacBook Neo 比较重量。",
                "快科技",
            ),
            (
                "联想IdeaPad Vibe完整规格曝光 正面对决MacBook Neo",
                "联想即将推出 IdeaPad Vibe，MacBook Neo 只是竞品参照。",
                "cnBeta",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                identity = self.module.title_led_identity(title, summary)
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(identity.scope, "third-party-context")
                self.assertEqual(tier, "weak", reason)

    def test_direct_apple_product_report_survives_competitor_background(self):
        title = "史上最贵！iPhone Ultra 顶配版售价有望突破 2 万元：与竞品价格相当"
        summary = "消息人士预计苹果首款折叠屏 iPhone Ultra 起售价约 1.5 万元，竞品只用于价格比较。"
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "strong", reason)

    def test_multi_product_code_report_projects_concrete_product_actions(self):
        title = "深挖 macOS 26.7 RC 代码：大量苹果未发布产品代号浮出水面"
        facts = [
            "家庭中枢 J490 和 J491 出现新的 Siri 设置代码。",
            "HomePod mini B525 安装了名为 Argentium 的新组件。",
            "摄像头 AirPods B790 出现左右耳图像流代码。",
            "AirPods Pro 4 对应的 AirPodsPro1,4 出现在代码中。",
            "iPhone Ultra V68 被列为苹果折叠屏产品标识。",
            "iMac J833 和 J834 出现在图形资源清单中。",
        ]
        variants = self.module.compound_article_variants(title, " ".join(facts), facts)
        variant_text = " ".join(item[0] for item in variants).lower()
        self.assertGreaterEqual(len(variants), 5)
        for marker in ("home", "airpods", "iphone", "imac"):
            self.assertIn(marker, variant_text)

    def test_comparison_baseline_does_not_block_multi_family_report_projection(self):
        title = "iPhone 18 Pro and iPhone Ultra: New Details Leak as Apple Event Nears"
        summary = (
            "iPhone Ultra supply will be very limited at launch. "
            "The iPhone 18 Pro A20 Pro chip is claimed to be 18% faster and 30% more efficient "
            "than the iPhone 17 Pro A19 Pro chip."
        )
        variants = self.module.multi_family_iphone_report_variants(title, summary, [])
        self.assertEqual(len(variants), 2)

    def test_title_led_first_party_actions_are_not_deferred_by_background(self):
        cases = [
            (
                "招聘信息暗示：苹果 Fitness+ 健康服务可能推出直播内容",
                "苹果招聘高级直播制作人负责 Fitness+ 的第一方直播内容制作。",
                "IT之家",
            ),
            (
                "Leaker details A20 Pro chip's new speed gains",
                "The report says Apple's A20 Pro chip will improve CPU and GPU performance while lowering power use.",
                "9to5Mac",
            ),
            (
                "Apple ordered to stop scaring iPhone users away from third-party apps",
                "German regulators ordered Apple to change its first-party ATT consent screen and remove discouraging language.",
                "The Verge",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "strong", reason)
        self.assertEqual(
            self.module.choose_category(cases[0][0], cases[0][1]),
            "software_systems",
        )

    def test_actual_wallet_and_fitness_background_watch_reference_do_not_merge(self):
        wallet = article_for(
            self.module,
            "Apple Wallet Driver's License Feature to Launch in Four More U.S. States",
            "Residents can add an ID to Apple Wallet on iPhone and Apple Watch.",
            "MacRumors",
        )
        fitness = article_for(
            self.module,
            "招聘信息暗示：苹果 Fitness+ 健康服务可能推出直播内容",
            "Fitness+ 可在 iPhone 和 Apple TV 观看，并使用 Apple Watch 记录运动数据。",
            "IT之家",
        )
        events = self.module.cluster_articles([wallet, fitness])
        self.assertEqual(len(events), 2)

    def test_platform_release_stage_conflict_splits_unnumbered_os_release(self):
        developer = article_for(
            self.module,
            "Apple Releases macOS Golden Gate Beta 6",
            "Apple provided developers with the sixth macOS beta.",
            "MacRumors",
        )
        public = article_for(
            self.module,
            "Apple releases public beta 4 for iOS 27, macOS 27, iPadOS 27, tvOS 27",
            "Apple released the fourth public beta across its operating systems.",
            "9to5Mac",
        )
        groups = self.reconcile([developer, public], [[developer, public]])
        self.assertEqual(len(groups), 2)

    def test_os_feature_roundup_does_not_absorb_specific_component_change(self):
        roundup = article_for(
            self.module,
            "Here’s what’s new with iOS and macOS 27 beta 6",
            "The roundup lists changes across iOS and macOS beta 6.",
            "9to5Mac",
        )
        wallpaper = article_for(
            self.module,
            "macOS Golden Gate gets unique dynamic wallpapers with beta 6",
            "Apple added two Golden Gate Bridge dynamic wallpapers.",
            "AppleInsider",
        )
        groups = self.reconcile([roundup, wallpaper], [[roundup, wallpaper]])
        self.assertEqual(len(groups), 2)

    def test_price_forecast_does_not_absorb_chip_performance_report(self):
        price = article_for(
            self.module,
            "iPhone 18 Pro Pricing: Worse Than Expected?",
            "Jeff Pu says iPhone 18 Pro could cost $300 more because of component costs.",
            "MacRumors",
        )
        performance = article_for(
            self.module,
            "Leaker details A20 Pro chip's new speed gains",
            "Apple's A20 Pro is reported to be 18% faster and 30% more efficient.",
            "9to5Mac",
        )
        groups = self.reconcile([price, performance], [[price, performance]])
        self.assertEqual(len(groups), 2)

    def test_number_word_hardware_feature_list_is_editorial_roundup(self):
        cases = [
            "iPhone 18 Pro: Twelve Changes Coming to Apple's Next Flagship",
            "iPhone 18 Pro: Six New Features Are Coming Next Month",
        ]
        for title in cases:
            with self.subTest(title=title):
                identity = self.module.title_led_identity(title, "The article recaps prior rumors.")
                tier, reason = self.module.classify_relevance_tier(
                    title, "The article recaps prior rumors.", [], "MacRumors"
                )
                self.assertEqual(identity.content_form, "roundup")
                self.assertEqual(tier, "weak", reason)

    def test_same_cve_security_reports_merge_across_headline_wording(self):
        reports = [
            article_for(
                self.module,
                "A serious Mac screen sharing vulnerability is being actively exploited",
                "Apple says CVE-2026-65400 affects macOS Screen Sharing.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple's macOS Screen Sharing Flaw Is Being Exploited in the Wild",
                "The NCSC confirmed exploitation of CVE-2026-65400.",
                "MacRumors",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_same_airtag_product_liability_case_merges_across_languages(self):
        reports = [
            article_for(
                self.module,
                "Michigan women sue Apple over AirTag anti-stalking protection failures",
                "Two women sued Apple over AirTag anti-stalking alerts.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "美国 2 名女子起诉苹果公司，称 AirTag 反跟踪警报未能提供有效保护",
                "两名女子就 AirTag 反跟踪保护失效起诉苹果。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_same_cross_platform_messages_reply_feature_merges(self):
        reports = [
            article_for(
                self.module,
                "iOS 27 Finally Fixes Replying to Android Texts",
                "Apple changed Messages so iPhone users can reply to Android texts.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 iOS 27 改善跨平台互联，iPhone 可直接回复安卓绿色气泡信息",
                "iOS 27 的信息应用支持直接回复安卓消息。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_three_component_os_version_is_preserved_in_release_identity(self):
        article = article_for(
            self.module,
            "Apple has shipped iOS 26.6.1, and you should install it soon",
            "The final public update follows last week's release candidate.",
            "AppleInsider",
        )
        profile = self.module.article_reconciliation_profile(article)
        release_keys = {
            key for key in profile.event_keys if key.startswith("apple-os-release-wave:")
        }
        self.assertIn("apple-os-release-wave:26.6.1:final:mobile", release_keys)
        self.assertFalse(any(":rc" in key for key in release_keys), release_keys)

    def test_mixed_stable_and_beta_title_does_not_invent_cross_action_release_wave(self):
        article = article_for(
            self.module,
            "苹果推送 iOS 26.6.1 安全更新，同时发布 iOS 27 第六开发者测试版",
            "苹果面向公众发布 iOS 26.6.1，并向开发者发布 iOS 27 Beta 6。",
            "cnBeta",
        )
        profile = self.module.article_reconciliation_profile(article)
        self.assertNotIn("apple-os-release-wave:26.6.1:beta-6", profile.event_keys)

    def test_same_developer_beta_wave_ignores_incidental_feature_detail_conflicts(self):
        reports = [
            article_for(
                self.module,
                "Apple Seeds tvOS 27 Beta 6 to Developers",
                "Apple released tvOS 27 beta 6 and also recapped Control Center changes.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "macOS 27 Golden Gate developer beta 6 now available to developers",
                "Apple released the same developer beta wave and mentioned Siri changes.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果 iOS / iPadOS 27.0 开发者预览版 Beta 6 发布",
                "苹果发布同一轮开发者测试版，并说明通知动画变化。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_versioned_os_compatibility_matrix_is_not_a_reader_poll(self):
        title = "Which iPhones Support Every iOS 27 Feature?"
        summary = (
            "Apple's iOS 27 supports iPhone 11 and later, but device memory divides "
            "Siri AI and Apple Intelligence support into three compatibility tiers."
        )
        article = article_for(self.module, title, summary, "MacRumors")
        self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)
        self.assertEqual(article.event_kind, "os_compatibility")

    def test_same_first_party_service_action_merges_without_product_only_bridging(self):
        cases = [
            [
                article_for(
                    self.module,
                    "Apple Fitness+ could be getting live sessions, but probably not",
                    "An Apple job listing seeks a producer with live multi-camera experience for Fitness+.",
                    "9to5Mac",
                ),
                article_for(
                    self.module,
                    "招聘信息暗示：苹果 Fitness+ 健康服务可能推出直播内容",
                    "苹果为 Fitness+ 招聘具备直播或多机位录播经验的制片人。",
                    "IT之家",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Apple Wallet driver's license is coming to new US state soon",
                    "North Carolina joins Utah, Virginia, and Oklahoma in preparing Wallet ID support.",
                    "9to5Mac",
                ),
                article_for(
                    self.module,
                    "Apple Wallet Driver's License Feature to Launch in Four More U.S. States",
                    "Apple Wallet digital IDs are expanding to North Carolina, Utah, Virginia, and Oklahoma.",
                    "MacRumors",
                ),
            ],
        ]
        for reports in cases:
            with self.subTest(title=reports[0].title):
                groups = self.reconcile(reports)
                self.assertEqual(len(groups), 1)
                events = self.module.cluster_articles(reports)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].relevance_tier, "strong")

    def test_named_macos_and_numbered_cross_platform_pages_join_same_beta_wave(self):
        reports = [
            article_for(
                self.module,
                "Apple Releases macOS Golden Gate Beta 6",
                "Apple provided developers with the sixth beta of macOS Golden Gate and recapped Siri AI changes.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "macOS 27 Golden Gate developer beta 6 now available to developers",
                "Apple rolled out macOS 27 beta 6 and mentioned new app icons for Siri and Safari.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple releases beta 6 for iPadOS 27, tvOS 27, and more",
                "The same developer beta wave covers iPadOS, tvOS, watchOS, HomePod, and macOS.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Seeds tvOS 27 Beta 6 to Developers",
                "The sixth beta also recaps the redesigned Podcasts app and Control Center.",
                "MacRumors",
            ),
        ]
        groups = self.reconcile(reports)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_same_release_wave_ignores_different_incidental_feature_assertions(self):
        reports = [
            article_for(
                self.module,
                "Apple Releases macOS Golden Gate Beta 6",
                "Apple released the beta and recapped a Settings change.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "macOS 27 Golden Gate developer beta 6 now available to developers",
                "Apple released the same developer beta and mentioned a Siri change.",
                "9to5Mac",
            ),
        ]
        groups = self.reconcile(reports)
        self.assertEqual(len(groups), 1)

    def test_codename_release_attaches_after_numbered_wave_seed_is_already_grouped(self):
        codename = article_for(
            self.module,
            "Apple Releases macOS Golden Gate Beta 6",
            "Apple released the beta and recapped a Settings change.",
            "MacRumors",
        )
        numbered_mac = article_for(
            self.module,
            "macOS 27 Golden Gate developer beta 6 now available to developers",
            "Apple released the beta and mentioned a Siri change.",
            "9to5Mac",
        )
        numbered_ios = article_for(
            self.module,
            "Apple Seeds Sixth iOS 27 and iPadOS 27 Betas to Developers",
            "Apple released the sixth developer beta across iPhone and iPad.",
            "MacRumors",
        )
        groups = self.reconcile(
            [codename, numbered_mac, numbered_ios],
            [[codename], [numbered_mac, numbered_ios]],
        )
        self.assertEqual(len(groups), 1)

    def test_different_third_party_comparisons_cannot_share_an_apple_product_bridge(self):
        lenovo = article_for(
            self.module,
            "剑指苹果 MacBook Neo：联想 IdeaPad Vibe 笔记本规格曝光",
            "联想公布 IdeaPad Vibe 规格，并将其与 MacBook Neo 对比。",
            "IT之家",
        )
        lenovo_translation = article_for(
            self.module,
            "联想 IdeaPad Vibe 完整规格曝光，正面对决 MacBook Neo",
            "Lenovo IdeaPad Vibe is compared with Apple's MacBook Neo.",
            "cnBeta",
        )
        acer = article_for(
            self.module,
            "比 MacBook Neo 更轻：宏碁非凡 Go Air 上新",
            "Acer launched a different PC and used MacBook Neo as a comparison.",
            "快科技",
        )
        groups = self.reconcile(
            [lenovo, lenovo_translation, acer],
            [[lenovo, lenovo_translation, acer]],
        )
        self.assertEqual(len(groups), 2)
        self.assertEqual(sorted(len(group) for group in groups), [1, 2])

    def test_os_security_release_is_not_projected_as_hardware_roadmaps(self):
        title = "苹果发布 iOS / iPadOS 26.6.1：聚焦安全漏洞修复"
        facts = [
            "苹果发布了 iOS 26.6.1、iPadOS 26.6.1 和 macOS 26.6.2。",
            "iOS / iPadOS 26.6.1 修复的漏洞此前已在 iOS / macOS 27 Beta 中修复。",
            "iOS 26.6.1 在 iPhone 上修复了 20 多个安全漏洞。",
            "iOS 26.6.1、iPadOS 26.6.1 的正式版 Build 编号与 RC 不同。",
        ]
        variants = self.module.compound_article_variants(title, " ".join(facts), facts)
        self.assertEqual(variants, [(title, " ".join(facts), facts)])

    def test_unanimous_article_kind_survives_aggregate_background_fact(self):
        reports = [
            article_for(
                self.module,
                "Apple iPhone 18 hardware roadmap update",
                "The A20 Pro chip is expected to improve performance.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple iPhone 18 hardware roadmap update",
                "The launch is expected in the fall; a background paragraph mentions a security update.",
                "IT之家",
                ["iOS 26.6.1 separately fixed WebKit security vulnerabilities."],
            ),
        ]
        reports = [replace(report, event_kind="hardware_market", category="hardware_products") for report in reports]
        self.assertTrue(all(report.event_kind == "hardware_market" for report in reports))
        event = self.module.event_from_article_group(
            self.module.singleton_merge_event(reports[0]), reports
        )
        self.assertEqual(event.event_kind, "hardware_market")
        self.assertEqual(event.category, "hardware_products")

    def test_repeated_incident_commentary_without_one_new_action_is_weak(self):
        title = "苹果 App Store 审查机制屡现漏洞，官方安全性承诺遭质疑"
        summary = "文章回顾多起此前发生的违规应用、虚假评分和订阅价格案例。"
        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(
            title, summary, [], "cnBeta"
        )
        self.assertEqual(identity.content_form, "analysis")
        self.assertEqual(tier, "weak", reason)

    def test_projected_hardware_roadmap_variants_keep_hardware_classification(self):
        for product in ("HomePod", "Home hub", "iPhone Ultra"):
            with self.subTest(product=product):
                title = f"Apple {product} roadmap update"
                summary = (
                    "A current macOS build contains identifiers for unreleased hardware. "
                    "A background clause also mentions Apple Intelligence in China."
                )
                self.assertEqual(
                    self.module.detect_event_kind(title, summary, []),
                    "hardware_market",
                )
                self.assertEqual(
                    self.module.choose_category(title, summary),
                    "hardware_products",
                )
                article = article_for(self.module, title, summary, "MacRumors")
                profile = self.module.article_reconciliation_profile(article)
                self.assertEqual(profile.category_hint, "hardware_products")
                self.assertFalse(
                    any(
                        key.startswith("structured-assertion:apple-intelligence:")
                        for key in profile.event_keys
                    )
                )
                event = self.module.cluster_articles([article])[0]
                self.assertEqual(event.event_kind, "hardware_market")
                self.assertEqual(event.category, "hardware_products")

    def test_title_led_apple_hardware_production_outweighs_org_background(self):
        title = "Apple expands Mac mini assembly at Foxconn's Houston factory"
        summary = (
            "The new production line will occupy 170,000 square feet. "
            "Apple CEO Tim Cook toured the facility with the US Commerce Secretary, "
            "visited Apple's manufacturing school, and discussed the company's wider "
            "US investment strategy and executive commitments."
        )
        self.assertEqual(
            self.module.detect_event_kind(title, summary, []),
            "hardware_market",
        )
        self.assertEqual(
            self.module.choose_category(title, summary),
            "hardware_products",
        )
        chinese_title = "苹果扩大今年晚些时候将在富士康休斯顿工厂组装 Mac mini"
        chinese_summary = (
            "新生产线位于富士康工厂，面积 17 万平方英尺。苹果首席执行官 Tim Cook "
            "与美国商务部长参观工厂和制造学校，并介绍公司 6000 亿美元投资承诺、"
            "员工薪酬、零售运营与管理层战略。"
        )
        self.assertEqual(
            self.module.detect_event_kind(chinese_title, chinese_summary, []),
            "hardware_market",
        )

    def test_refurbished_apple_products_affiliate_tail_is_removed(self):
        body = (
            "<article><p>" + ("Apple changed its ATT consent flow in Germany. " * 4) + "</p>"
            "<p>Certified refurbished Apple products 15% off at apple.com</p>"
            "<p>MacBook and iPhone deals</p></article>"
        )
        cleaned = self.module.remove_trailing_promo_sections(body)
        self.assertIn("ATT consent flow", cleaned)
        self.assertNotIn("Certified refurbished Apple products", cleaned)
        self.assertNotIn("MacBook and iPhone deals", cleaned)

    def test_one_title_with_two_os_release_trains_projects_each_action(self):
        title = "苹果推送 iOS 26.6.1 安全更新，同时发布 iOS 27 第六开发者测试版"
        facts = [
            "苹果面向所有用户推送 iOS 26.6.1，包含关键安全修复。",
            "苹果同时发布 iOS 27 第六个开发者测试版，内部版本号为 24A5418b。",
        ]
        variants = self.module.compound_article_variants(
            title,
            " ".join(facts),
            facts,
        )
        self.assertEqual(len(variants), 2)
        profiles = [
            self.module.build_reconciliation_profile(
                title=variant_title,
                lead=variant_summary,
                identity=self.module.title_led_identity(variant_title, variant_summary),
                exact_facets=self.module.primary_topic_facets(variant_title, variant_summary),
                regions=(),
            )
            for variant_title, variant_summary, _variant_facts in variants
        ]
        release_keys = [
            {
                key
                for key in profile.event_keys
                if key.startswith("apple-os-release-wave:")
            }
            for profile in profiles
        ]
        self.assertTrue(any(any(":26.6.1:final" in key for key in keys) for keys in release_keys))
        self.assertTrue(any(any(":27:beta-6" in key for key in keys) for keys in release_keys))

    def test_concrete_third_party_os_support_for_apple_silicon_is_ecosystem(self):
        title = "Linux 7.2 released with initial support for Apple's M3 chips"
        summary = (
            "The Linux kernel adds initial Apple M3 support, new drivers, and scheduling changes."
        )
        tier, reason = self.module.classify_relevance_tier(
            title,
            summary,
            [],
            "cnBeta",
        )
        self.assertEqual(tier, "ecosystem", reason)
        self.assertEqual(
            self.module.detect_event_kind(title, summary, []),
            "os_compatibility",
        )
        event = self.module.cluster_articles(
            [article_for(self.module, title, summary, "cnBeta")]
        )[0]
        self.assertEqual(event.relevance_tier, "ecosystem", event.relevance_reason)
        self.assertEqual(event.event_kind, "os_compatibility")

if __name__ == "__main__":
    unittest.main()
