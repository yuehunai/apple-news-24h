import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260813_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
        published_utc=datetime(2026, 8, 13, tzinfo=timezone.utc),
        published_raw="2026-08-13T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, []),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(f"{title} {summary}"),
    )


def partitions(events):
    return {frozenset(article.title for article in event.articles) for event in events}


class PrimaryActionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_third_party_action_owner_is_deferred_when_apple_is_only_platform_or_comparison(self):
        samples = (
            (
                "奥造科技推出冷奥 L100 手机液冷散热器：支持为 iPhone 15W 无线充电，568 元",
                "制造商发布第三方散热器，仅兼容 iPhone 14-17 系列。",
                "IT之家",
            ),
            (
                "Dave the Diver is coming to Apple devices on September 17",
                "The third-party game launches on iPhone, iPad, Mac and Vision Pro.",
                "AppleInsider",
            ),
            (
                "Google为Quick Share引入“碰一碰”分享功能 类似苹果AirDrop",
                "Google updates Quick Share for Android; AirDrop is only a comparison.",
                "cnBeta",
            ),
            (
                "Google's $100 Pixel Price Hike and Trade-In Push Hint at Apple's iPhone 18 Pro Plans",
                "Google raised Pixel prices; the article speculates what Apple might do.",
                "MacRumors",
            ),
            (
                "苹果 Mac 平台最强效率工具：Raycast 0.71 发布，让 AI 直接“看懂”你的屏幕",
                "Raycast released a third-party screen-awareness feature for Mac.",
                "IT之家",
            ),
        )
        for title, summary, source in samples:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary, source)
                profile = self.module.article_reconciliation_profile(article)
                self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
                self.assertEqual(profile.identity.scope, "third-party-context")

    def test_broad_market_report_does_not_absorb_direct_iphone_launch_schedule(self):
        market = article_for(
            self.module,
            "Counterpoint：2026 年二季度美国智能手机销量同比降 5%，低端市场承压",
            (
                "Counterpoint 报告显示美国智能手机销量同比下降 5%，苹果、三星、摩托罗拉和谷歌"
                "总销量下降 4%，低端厂商受内存价格上涨冲击。"
            ),
            "IT之家",
        )
        schedule = article_for(
            self.module,
            "苹果拆分 iPhone 18 系列登场时间，标准版或延至明年春季",
            "供应链消息称苹果调整发布节奏，iPhone 18 Pro 今秋发布，标准版延至 2027 年春季。",
            "cnBeta",
        )
        events = self.module.cluster_articles([market, schedule])
        self.assertEqual(market.relevance_tier, "weak", market.relevance_reason)
        self.assertEqual(len(events), 2, partitions(events))

    def test_distinct_watchos_feature_subjects_split_inside_one_version(self):
        apps = article_for(
            self.module,
            "watchOS 27 will add two new apps to your Apple Watch",
            "watchOS 27 adds a Siri app and a unified Find My app.",
        )
        face = article_for(
            self.module,
            "watchOS 27 将为苹果 Apple Watch 的 Modular 表盘新增 9 种颜色",
            "watchOS 27 Beta 5 code reveals nine new colors for the Modular watch face.",
            "IT之家",
        )
        self.assertEqual(len(self.module.cluster_articles([apps, face])), 2)

    def test_distinct_apple_tv_work_and_action_split_inside_one_service(self):
        continuation = article_for(
            self.module,
            "Eddy Cue said the thing we wanted to hear on future Ted Lasso seasons",
            (
                "Apple TV services chief Eddy Cue hinted that Ted Lasso could continue after season 4. "
                "Two episodes are available and new episodes air Wednesdays through October 7."
            ),
        )
        trailer = article_for(
            self.module,
            "Australian thriller 'Last Seen' gets a September launch date",
            (
                "Apple TV has released the first trailer for \"Last Seen,\" its upcoming thriller. "
                "The first two episodes premiere "
                "September 9 and new episodes release Wednesdays through October 7."
            ),
            "AppleInsider",
        )
        self.assertEqual(len(self.module.cluster_articles([continuation, trailer])), 2)

    def test_same_iphone_launch_schedule_merges_across_wording_and_language(self):
        reports = [
            article_for(
                self.module,
                "Apple Skipping iPhone 18 Launch This Year",
                "Apple supplier Pegatron indirectly confirmed the standard iPhone 18 will not be released until next year.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple supplier Pegatron confirms 2027 iPhone 18 launch",
                "An Apple supplier says Apple will release the iPhone 18 base model separately in early 2027.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "和硕间接确认：苹果 iPhone 18 Pro 今秋发布，标准版推迟至明年发布",
                "iPhone 18 Pro remains in fall 2026 and the base iPhone 18 moves to spring 2027.",
                "IT之家",
            ),
        ]
        expected_key = "structured-assertion:iphone-18-base:split-release-schedule"
        self.assertTrue(
            all(expected_key in self.module.article_reconciliation_profile(article).event_keys for article in reports)
        )
        self.assertEqual(len(self.module.cluster_articles(reports)), 1, partitions(self.module.cluster_articles(reports)))

    def test_iphone_feature_report_does_not_join_release_delay_from_body_background(self):
        delay = article_for(
            self.module,
            "Apple Skipping iPhone 18 Launch This Year",
            "Apple supplier Pegatron says the base iPhone 18 will not be released until next year.",
            "MacRumors",
        )
        feature = article_for(
            self.module,
            "iPhone 18 could get two new Pro-level upgrades, per report",
            (
                "Apple's base iPhone 18 won't launch until early 2027, but analyst Jeff Pu says "
                "it will gain 12GB RAM and a smaller Dynamic Island."
            ),
        )
        self.assertEqual(len(self.module.cluster_articles([delay, feature])), 2)

    def test_same_first_party_action_merges_without_inventing_verb_phrase_subjects(self):
        groups = (
            (
                article_for(
                    self.module,
                    "Apple Hires Airline Exec as Vice President of Government Affairs",
                    "Apple hired Nate Gatten to lead government affairs.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "苹果任命 Nate Gatten 为政府事务新主管",
                    "Apple appointed Nate Gatten as its government affairs leader.",
                    "cnBeta",
                ),
            ),
            (
                article_for(
                    self.module,
                    "Apple Wallet Could Soon Save Trade-In Quotes for 90 Days",
                    "Apple Wallet may store Apple trade-in quotes for 90 days.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "Apple Wallet may soon store trade-in offers for 90 days",
                    "Code suggests Apple Wallet can retain a trade-in offer for 90 days instead of 14.",
                    "9to5Mac",
                ),
                article_for(
                    self.module,
                    "代码显示苹果 Wallet 将重构线下换购流程：估价 90 天有效",
                    "Apple Trade In 换购方案要求用户在收到新设备后的 14 天内寄回旧设备。",
                    "IT之家",
                ),
            ),
            (
                article_for(
                    self.module,
                    "Apple in Talks to Pay Publishers for News Content to Power Siri AI",
                    "Apple is negotiating publisher licenses for live news content used by Siri AI.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "Siri AI could get a boost from news content with new publisher deal",
                    "Hallucinations are a problem, so Apple could let Siri AI provide news directly from an outlet via paid partnerships.",
                    "AppleInsider",
                ),
                article_for(
                    self.module,
                    "消息称苹果拟向出版商支付数亿美元，获取新闻内容以改进 AI 版 Siri",
                    "据报道，苹果正与多家出版商洽谈多年期许可协议，拟支付数亿美元费用。",
                    "IT之家",
                ),
            ),
        )
        for group in groups:
            with self.subTest(title=group[0].title):
                events = self.module.cluster_articles(list(group))
                self.assertEqual(len(events), 1, partitions(events))
                for article in group:
                    subjects = self.module.article_reconciliation_profile(article).identity.title_named_subjects
                    self.assertFalse(any(subject.startswith(("apple-hires", "apple-wallet-could")) for subject in subjects))

    def test_same_patent_and_court_stay_merge_across_language(self):
        patent = [
            article_for(
                self.module,
                "Apple Patenting Way to Improve Notification Summaries and Reduce Interruptions Focus",
                "An Apple patent describes interruption-aware notification summaries.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果新专利：iPhone 将能判断何时该打扰用户",
                "苹果一项新专利揭示，系统可分析用户当前操作来决定是否要发出通知。",
                "IT之家",
            ),
        ]
        court = [
            article_for(
                self.module,
                "Supreme Court Lets Apple Delay App Store Fee Fight for 24 Hours",
                "U.S.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple wins temporary Supreme Court pause in Epic proceedings",
                "The Supreme Court granted Apple a 24-hour extension in the App Store commission case.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果获最高法院批准，可晚一天提交 App Store 外部支付佣金方案",
                "在加州法官驳回苹果的暂停请求后，苹果紧急上诉至最高法院。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(patent)), 1, partitions(self.module.cluster_articles(patent)))
        self.assertEqual(len(self.module.cluster_articles(court)), 1, partitions(self.module.cluster_articles(court)))

    def test_same_anniversary_iphone_glass_display_report_merges_across_angles(self):
        reports = [
            article_for(
                self.module,
                "iPhone 20 Pro will be bigger with familiar aspect ratios, be bezel free",
                "The iPhone 20 Pro display keeps the aspect ratio, grows slightly, and uses a glass cover for a bezel-free result.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "消息称苹果 iPhone 20 Pro 系列手机有望采用 2D 直屏 + 玻璃盖板工艺，实现无边四曲面效果",
                "数码闲聊站称 V73/V74 新屏尺寸增大、比例不变，并以玻璃折射形成无边视觉。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Leaker: All-Glass 2027 iPhone Still on Track Despite Cancellation Rumors",
                "The 20th-anniversary all-glass iPhone remains on track despite a cancellation claim.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "iPhone 20 Pro's all-glass design spotted in supply chain, says leaker",
                "A supply-chain report says the anniversary iPhone glass display design remains on track.",
            ),
        ]
        expected_key = "structured-assertion:iphone-anniversary-redesign:glass-display"
        self.assertTrue(
            all(expected_key in self.module.article_reconciliation_profile(article).event_keys for article in reports)
        )
        self.assertEqual(len(self.module.cluster_articles(reports)), 1, partitions(self.module.cluster_articles(reports)))

    def test_app_store_impersonation_incident_keeps_removal_followup_in_one_event(self):
        reports = [
            article_for(
                self.module,
                "苹果应用商店出现山寨版政务 App，闽政通官方回应称相关部门正在协调处理",
                "假冒 App 名为闽证通，闽政通官方已上报并协调处理。",
                "IT之家",
            ),
            article_for(
                self.module,
                "盗版“闽政通”政务 App 已被苹果应用商店下架",
                "福建政务服务平台闽政通遭假冒，相关盗版应用现已从 App Store 下架。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果商店现山寨版政务 APP！官方回应：相关部门正处理",
                "福建政务服务 App 统一平台（简称“闽政通 App”）在苹果应用商店被假冒。",
                "快科技",
            ),
        ]
        expected_key = "structured-assertion:app-store:闽政通:impersonation-incident"
        self.assertTrue(
            all(expected_key in self.module.article_reconciliation_profile(article).event_keys for article in reports)
        )
        self.assertEqual(len(self.module.cluster_articles(reports)), 1, partitions(self.module.cluster_articles(reports)))

    def test_impersonation_subject_uses_the_legitimate_platform_name_not_the_copycat_name(self):
        report = article_for(
            self.module,
            "苹果客服回应现山寨版政务 APP：软件上架与下架由相应团队负责",
            (
                "福建政务服务 App 统一平台（闽政通 App）在苹果应用商店出现疑似山寨版本。"
                "假冒 App 名为‘闽证通’，苹果客服已反馈相应团队处理。"
            ),
            "快科技",
        )
        profile = self.module.article_reconciliation_profile(report)
        self.assertIn(
            "structured-assertion:app-store:闽政通:impersonation-incident",
            profile.event_keys,
        )

    def test_same_apple_reference_image_feature_reconciles_a_sparse_followup(self):
        reports = [
            article_for(
                self.module,
                "Apple authenticating iPhone photos is just the start",
                "iOS 27 Beta 5 references Apple Reference Image for authenticating photos and preserving provenance.",
            ),
            article_for(
                self.module,
                "Faked photos could be shown up by new iPhone feature",
                "Apple aims to prove a photo was taken on iPhone and not altered by using Reference mode metadata.",
                "AppleInsider",
            ),
        ]
        expected_key = "structured-assertion:iphone-camera:reference-image-authentication"
        self.assertTrue(
            all(expected_key in self.module.article_reconciliation_profile(article).event_keys for article in reports)
        )
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_reference_image_identity_can_use_clean_key_facts_without_expanding_generic_similarity(self):
        report = article_for(
            self.module,
            "Apple authenticating iPhone photos is just the start",
            "iOS 27 Beta 5 includes references to an upcoming iPhone photo feature.",
            facts=[
                "Apple Reference Image lets an Apple server authenticate genuine iPhone photos.",
                "The feature preserves provenance metadata when the image is transferred.",
            ],
        )
        self.assertIn(
            "structured-assertion:iphone-camera:reference-image-authentication",
            self.module.article_reconciliation_profile(report).event_keys,
        )

    def test_same_display_inventory_buffer_action_merges_and_stays_hardware(self):
        reports = [
            article_for(
                self.module,
                "苹果罕见延长 OLED 面板储备周期，提前稳住零部件成本",
                "苹果把显示屏面板库存持有周期从 4 周延长至 6 周，并作为长期采购策略。",
                "快科技",
            ),
            article_for(
                self.module,
                "苹果为何要加大力度采购 OLED 面板，背后原因揭晓",
                (
                    "苹果预计秋季新机发布后可能面临供货短缺。"
                    "苹果已把显示屏供应缓冲期由 4 周延长至 6 周，并将长期维持。"
                ),
                "快科技",
            ),
        ]
        expected_key = "structured-assertion:apple-display-inventory:buffer-extension"
        self.assertTrue(
            all(expected_key in self.module.article_reconciliation_profile(article).event_keys for article in reports)
        )
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1, partitions(events))
        self.assertEqual(events[0].category, "hardware_products")

    def test_distinct_apple_tv_works_and_actions_do_not_merge(self):
        reports = [
            article_for(
                self.module,
                "Vince Gilligan reveals Pluribus season 2 just hit major milestone",
                "The hit series is about to start filming its second season.",
                facts=["Pluribus became an instant hit when it premiered on Apple TV."],
            ),
            article_for(
                self.module,
                "Apple TV publishes the trailer for Stillwater's fifth season",
                "Apple TV published the trailer before the fifth season premieres in August.",
            ),
        ]
        profiles = [self.module.article_reconciliation_profile(article) for article in reports]
        self.assertIn(
            "structured-assertion:apple-tv:pluribus:production-update",
            profiles[0].event_keys,
        )
        self.assertIn(
            "structured-assertion:apple-tv:stillwater:trailer",
            profiles[1].event_keys,
        )
        self.assertEqual(len(self.module.cluster_articles(reports)), 2)

    def test_calendar_inference_cannot_be_repromoted_by_hardware_identity(self):
        report = article_for(
            self.module,
            "iPhone 18 Pro and iPhone Ultra: Pre-Orders and Release Date",
            (
                "Apple has yet to reveal the dates, but they usually follow a familiar pattern. "
                "The most likely event date is September 9 until proven otherwise; another possibility "
                "is September 15, with pre-orders and release inferred from historical schedules."
            ),
            "MacRumors",
        )
        self.assertEqual(report.relevance_tier, "weak")
        profile = self.module.article_reconciliation_profile(report)
        self.module.reconcile_article_relevance(report, profile)
        self.assertEqual(report.relevance_tier, "weak")
        self.assertEqual(profile.hard_boundary, "editorial-inference-without-new-reporting")

    def test_same_foldable_cover_display_protector_leak_merges_across_languages(self):
        reports = [
            article_for(
                self.module,
                "苹果首款折叠手机：iPhone Ultra 外屏曝光",
                "同一爆料者分享了外屏贴膜图片，显示靠近铰链一侧方角、另一侧圆角。",
                "IT之家",
            ),
            article_for(
                self.module,
                "'iPhone Ultra' Screen Protectors Reveal Asymmetric Corners",
                "A leaker shared images and video of screen protectors for Apple's foldable iPhone.",
                "MacRumors",
            ),
        ]
        expected = "structured-assertion:foldable-iphone:cover-display-protector-leak"
        self.assertTrue(
            all(expected in self.module.article_reconciliation_profile(article).event_keys for article in reports)
        )
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_supply_constraint_uses_direct_fact_instead_of_buying_wrapper_as_event_title(self):
        report = article_for(
            self.module,
            "MacBook Air shortages: where to buy one right now",
            "MacBook Air shipping estimates at Apple have slipped to September amid memory supply constraints.",
            "9to5Mac",
            facts=[
                "Most standard configurations now quote delivery in two to three weeks, with custom models later.",
            ],
        )
        report.relevance_tier = "strong"
        report.relevance_reason = "Apple product delivery constraint"
        title, _summary, _facts = self.module.build_event_summary([report])
        self.assertEqual(
            title,
            "MacBook Air shipping estimates at Apple have slipped to September amid memory supply constraints.",
        )

    def test_display_buffer_identity_accepts_chinese_numerals_in_clean_key_facts(self):
        report = article_for(
            self.module,
            "苹果为何要加大力度采购 OLED 面板，背后原因揭晓",
            "苹果正在增加 OLED 显示屏库存，以应对零部件供应和成本压力。",
            "快科技",
            facts=[
                "苹果把显示屏供应缓冲期从通常的四周延长至六周，并计划长期维持。",
            ],
        )
        self.assertIn(
            "structured-assertion:apple-display-inventory:buffer-extension",
            self.module.article_reconciliation_profile(report).event_keys,
        )

    def test_personnel_appointment_does_not_absorb_an_unrelated_patent_from_same_publisher(self):
        appointment = [
            article_for(
                self.module,
                "Apple picks up Nate Gatten as new head of government affairs",
                "Apple appointed Nate Gatten as its new vice president of government affairs.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple hires American Airlines exec to lead government affairs",
                "Apple has hired a new vice president of government affairs.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Hires Airline Exec as Vice President of Government Affairs",
                "Apple hired a former airline executive as its new vice president of government affairs.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果任命Nate Gatten为政府事务新主管 助力跨党派沟通与政府合作 - Apple 苹果 - cnBeta.COM",
                "苹果任命 Nate Gatten 为政府事务负责人，负责跨党派沟通和政府合作。",
                "cnBeta",
            ),
        ]
        patent = article_for(
            self.module,
            "苹果操作系统新专利曝光：聚焦减少中断 强化通知摘要与专注模式 - Apple 苹果 - cnBeta.COM",
            "苹果专利描述可判断何时打扰用户的通知摘要和专注模式。",
            "cnBeta",
        )

        events = self.module.cluster_articles([appointment[0], patent, *appointment[1:]])

        self.assertEqual(len(events), 2, partitions(events))
        self.assertIn(frozenset(article.title for article in appointment), partitions(events))


if __name__ == "__main__":
    unittest.main()
