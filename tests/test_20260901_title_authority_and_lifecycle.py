import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260901_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    article = module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 9, 1, tzinfo=timezone.utc),
        published_raw="2026-09-01T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )
    profile = module.article_reconciliation_profile(article)
    module.reconcile_article_relevance(article, profile)
    return article


class TitleAuthorityAndLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_multi_product_catalog_withdrawal_is_not_projected_as_product_roadmaps(self):
        reports = [
            (
                "Apple could discontinue 10+ popular products next week",
                "Apple is expected to discontinue more than ten current devices after its September event, including iPhones, Watches, AirPods, Apple TV and HomePod models.",
                "9to5Mac",
                [
                    "Apple is expected to discontinue 10+ popular current devices.",
                    "September 9's products will lead to older iPhone, Apple Watch models, and more being discontinued.",
                    "Apple Watch Series 11",
                    "Apple TV 4K (3rd generation)",
                    "HomePod mini (1st generation)",
                ],
            ),
            (
                "苹果今秋发布会预估下架 11 款设备，iPhone 16 去留存悬念",
                "预计苹果会在发布会后下架 4 款 iPhone、2 款 Apple Watch、2 款 AirPods、Apple TV 和两款 HomePod。",
                "IT之家",
                [
                    "苹果公司可能会从官网下架 11 款设备。",
                    "覆盖 4 款 iPhone、2 款 Apple Watch、2 款 AirPods，以及 Apple TV 和两款 HomePod。",
                    "Apple Watch Series 11",
                    "iPhone 16 和 iPhone 16 Plus 的安排尚不明确。",
                ],
            ),
        ]
        articles = []
        for title, summary, source, facts in reports:
            variants = self.module.compound_article_variants(title, summary, facts)
            self.assertEqual(variants, [(title, summary, facts)])
            articles.append(article_for(self.module, title, summary, source, facts))

        specs = article_for(
            self.module,
            "iPhone 18 Pro is coming: Here's what's new with each model",
            "The new Pro models are expected to add camera and modem upgrades.",
            "MacRumors",
        )
        events = self.module.cluster_articles([*articles, specs])
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])
        lifecycle = next(event for event in events if len(event.articles) == 2)
        self.assertEqual(lifecycle.category, "hardware_products")
        self.assertEqual(lifecycle.relevance_tier, "strong")

    def test_catalog_withdrawal_does_not_absorb_foldable_release_timing(self):
        reports = [
            article_for(
                self.module,
                "Apple could discontinue 10+ popular products next week",
                "Apple may discontinue more than ten current devices after the event.",
                "9to5Mac",
                ["The list spans iPhone, Apple Watch, AirPods, Apple TV and HomePod."],
            ),
            article_for(
                self.module,
                "苹果今秋 iPhone 18 Pro / Max 发布会预估下架 11 款设备，iPhone 16 去留存悬念",
                "苹果可能从官网下架 11 款设备，覆盖 iPhone、Apple Watch、AirPods、Apple TV 和 HomePod。",
                "IT之家",
            ),
            article_for(
                self.module,
                "iPhone Ultra release timing: Here's what the latest reporting says",
                "Apple may unveil the foldable iPhone next week, but first shipments could be limited.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果首款折叠手机 iPhone Ultra 预估本月发售，首批供应极其有限",
                "报道聚焦折叠 iPhone 的发售时间与首批供应。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [2, 2])

    def test_third_party_app_update_roundup_stays_deferred_despite_platform_background(self):
        article = article_for(
            self.module,
            "CarPlay keeps getting better with three recent exciting app updates",
            "Three independent developers updated their apps for CarPlay. Earlier iOS releases made more app categories available, but Apple announced no new API, policy, or first-party feature in this report.",
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_real_carplay_app_update_roundup_wording_stays_deferred(self):
        article = article_for(
            self.module,
            "CarPlay keeps getting better with three recent exciting app updates",
            "MLB upgraded its iPhone app, while two other independent developers updated their CarPlay apps. Apple announced no new platform API or first-party feature.",
            "9to5Mac",
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_event_excitement_commentary_without_new_action_stays_deferred(self):
        article = article_for(
            self.module,
            "今年苹果秋季发布会可能是这几年最有看头的一次",
            "文章基于既有传闻评论发布会看点，没有披露新的日期、邀请函或产品动作。",
            "快科技",
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_non_apple_market_story_is_not_promoted_by_body_only_apple_metric(self):
        article = article_for(
            self.module,
            "Chinese display makers take global lead as BOE ranks first and TCL closes on Samsung",
            "The report concerns the global panel market. A later background paragraph says Apple represented 16.1 percent of one segment, but reports no Apple action or Apple-led result.",
            "快科技",
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_multi_brand_release_price_table_is_not_apple_owned(self):
        article = article_for(
            self.module,
            "iPhone 18, Xiaomi 18 and Huawei Mate 90 release dates and prices leak",
            "A multi-brand table lists speculative launch dates and prices for several phone makers without a distinct new Apple report.",
            "快科技",
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_ceo_transition_farewell_and_retrospective_have_separate_outcomes(self):
        transition = article_for(
            self.module,
            "John Ternus assumes role as Apple's new CEO on September 1",
            "Ternus formally succeeds Tim Cook and starts as chief executive.",
            "MacRumors",
        )
        farewell = article_for(
            self.module,
            "Tim Cook signs off as CEO with thanks to staff and a tribute to John Ternus",
            "Cook sent employees a final-day message thanking staff and welcoming Ternus.",
            "9to5Mac",
        )
        chinese_farewell = article_for(
            self.module,
            "库克卸任前发表告别内部信，感谢苹果员工并致意特努斯",
            "库克在最后一个工作日向员工发布告别信。",
            "IT之家",
        )
        retrospective = article_for(
            self.module,
            "Tim Cook as CEO: the man who grew Apple by trillions of dollars",
            "A retrospective assessment of Cook's tenure contains no new Apple action.",
            "AppleInsider",
        )

        events = self.module.cluster_articles([transition, farewell, chinese_farewell, retrospective])
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1, 2])
        self.assertEqual(retrospective.relevance_tier, "weak")
        farewell_event = next(event for event in events if len(event.articles) == 2)
        self.assertNotIn(transition, farewell_event.articles)

    def test_named_company_award_merges_cross_language_and_stays_strong(self):
        reports = [
            article_for(
                self.module,
                "Apple inducted into the Creative Hall of Fame",
                "The organization inducted Apple for its long-term brand and creative work.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果入选创意名人堂，表彰其长期品牌创新",
                "该奖项正式将苹果列入名人堂。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_role_reduction_reports_merge_without_exact_departure_wording(self):
        reports = [
            article_for(
                self.module,
                "Phil Schiller steps back from App Store and Apple events duties",
                "Apple adjusted Schiller's responsibilities for the App Store and product events.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "菲尔·席勒卸任苹果 App Store 及产品活动管理工作",
                "苹果调整席勒的管理职责。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)

    def test_same_beta_release_wave_merges_but_feature_only_report_stays_separate(self):
        reports = [
            article_for(
                self.module,
                "Apple releases developer beta 8 for iOS 27, iPadOS 27 and macOS 27",
                "Apple made beta 8 available to registered developers for the same release train.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "iOS 27 beta 8 now available as Apple tests major Siri AI upgrade",
                "Apple released developer beta 8 today; the build also contains Siri testing.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "iOS 27 beta 8 includes a redesigned Siri animation",
                "A feature report examines one Siri animation already present in the beta.",
                "AppleInsider",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])

    def test_actual_beta_release_headlines_join_the_same_release_wave(self):
        reports = [
            article_for(
                self.module,
                "Apple Seeds Eighth iOS 27 and iPadOS 27 Betas to Developers",
                "Apple released developer beta 8 for iOS 27 and iPadOS 27 today.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "iOS 27 beta 8 now available as Apple tests major Siri AI upgrade",
                "Apple made developer beta 8 available today and is also testing Siri.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Releases macOS Golden Gate Beta 8",
                "Apple released the eighth developer beta of macOS 27 Golden Gate today.",
                "MacRumors",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)

    def test_cross_platform_release_wave_is_not_resplit_by_hardware_release_cleanup(self):
        reports = [
            article_for(
                self.module,
                "Apple Seeds Eighth iOS 27 and iPadOS 27 Betas to Developers",
                "Apple released developer beta 8 for iOS 27 and iPadOS 27 today.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 visionOS 27.0 开发者预览版 Beta 8 发布",
                "苹果向 Vision Pro 用户推送 visionOS 27 beta 8。",
                "IT之家",
            ),
            article_for(
                self.module,
                "macOS 27 developer beta 8 now available",
                "Apple released developer beta 8 for macOS 27 today.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Releases macOS Golden Gate Beta 8",
                "Apple provided developers with the eighth beta of macOS Golden Gate today.",
                "MacRumors",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_lifecycle_list_does_not_become_accessory_compatibility_evaluation(self):
        reports = [
            article_for(
                self.module,
                "Apple adds three Macs to its obsolete products list",
                "Three Mac models moved to Apple's obsolete list and are no longer eligible for hardware service.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果将三款 Mac 列入过时产品名单，官方维修支持终止",
                "支持文档同时提到部分旧键盘配件，但本次动作是三款 Mac 的产品生命周期调整。",
                "IT之家",
            ),
        ]
        profiles = [self.module.article_reconciliation_profile(article) for article in reports]
        self.assertFalse(any("accessory-evaluation" in key for profile in profiles for key in profile.event_keys))
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_real_chinese_obsolete_list_wording_joins_lifecycle_event(self):
        reports = [
            article_for(
                self.module,
                "Apple Adds Three More Macs to Obsolete Products List",
                "Apple now considers 2017 and 2018 MacBook Pro and MacBook Air models obsolete, ending hardware service.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "2017/2018 款 MacBook Pro 与 2018 款 MacBook Air 正式进入苹果过时名单",
                "三款 Mac 进入苹果过时名单，官方维修和零件服务终止。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_same_new_evidence_legal_development_merges_across_wording(self):
        reports = [
            article_for(
                self.module,
                "Apple files new evidence in OpenAI trade-secret lawsuit",
                "Apple submitted evidence alleging stolen trade secrets and destruction of records.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果在诉 OpenAI 商业机密案中披露震撼新证据",
                "苹果向法院提交新证据，指控对方窃取商业秘密并销毁证据。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_actual_new_evidence_legal_headlines_form_one_event(self):
        reports = [
            article_for(
                self.module,
                "Apple reveals 'shocking evidence' from ex-employee's MacBook in OpenAI suit",
                "Apple submitted forensic evidence alleging stolen trade secrets and destroyed records.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Says Former Engineer Used Stolen Trade Secrets at OpenAI, Taught AI Agent to Run Them",
                "Apple says a former engineer used stolen trade secrets at OpenAI and trained an agent to run related software.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "New evidence shows OpenAI's trade secret theft and destruction of evidence, says Apple",
                "Apple disclosed new evidence in the same trade-secret lawsuit.",
                "AppleInsider",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_product_experience_phrase_does_not_turn_code_report_into_hands_on(self):
        article = article_for(
            self.module,
            "苹果摄像头版 AirPods 爆料：可拍摄 100 万像素彩照，改进空间音频体验",
            "Code strings reference camera-equipped AirPods intended to improve the user experience; this is a first-party hardware clue, not a hands-on review.",
            "IT之家",
        )
        identity = self.module.title_led_identity(article.title, article.summary)
        self.assertEqual(identity.content_form, "news")
        self.assertEqual(article.relevance_tier, "strong")

    def test_mac_mini_and_studio_ai_demand_reports_merge_as_hardware(self):
        reports = [
            article_for(
                self.module,
                "Unusual timing of Mac mini and Mac Studio updates all about AI, claims report",
                "Unexpected enterprise AI demand caused Apple to launch both desktop Macs early.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Mac 成 AI 硬件宠儿：苹果提前发布 2026 款 mini / Studio，全球需求激增促成 8 月上新",
                "企业 AI 硬件需求激增促使苹果提前更新 Mac mini 和 Mac Studio。",
                "IT之家",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")

    def test_real_mac_ai_demand_wording_joins_accelerated_refresh_event(self):
        reports = [
            article_for(
                self.module,
                "Unusual timing of Mac mini and Mac Studio updates all about AI, claims report",
                "The unusually timed announcement was driven by unexpectedly strong enterprise appetite for AI hardware.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Mac 成 AI 硬件宠儿：苹果提前发布 2026 款 mini / Studio，全球需求激增促成 8 月上新",
                "企业 AI 硬件需求激增促使苹果提前更新 Mac mini 和 Mac Studio。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_multi_brand_price_rise_with_unchanged_iphone_is_weak(self):
        article = article_for(
            self.module,
            "多款手机正式涨价，网友：就差 iPhone 17 没涨了",
            "多家安卓手机厂商上调售价；iPhone 17 系列尚未跟随调价，只被用作行业价格对照。",
            "快科技",
        )
        self.assertEqual(article.relevance_tier, "weak")
        self.assertIn("without a direct Apple action", article.relevance_reason)

    def test_direct_apple_multi_product_price_change_remains_strong(self):
        article = article_for(
            self.module,
            "Apple raises prices across iPhone, iPad, and Mac lineups",
            "Apple updated official store prices for several first-party product families.",
            "9to5Mac",
        )
        self.assertEqual(article.relevance_tier, "strong")

    def test_compact_chinese_catalog_withdrawal_joins_other_sources(self):
        reports = [
            article_for(
                self.module,
                "Apple could discontinue 10+ popular products next week",
                "The expected catalog change spans iPhone, Apple Watch, AirPods, Apple TV and HomePod.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果今秋发布会预估下架 11 款设备",
                "预计苹果会从官网下架 iPhone、Apple Watch、AirPods、Apple TV 和 HomePod。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果将停产10余款在售产品：iPhone 17系列、AirPods 4包括在内",
                "现有产品线将随发布会调整，预计停产停售的产品超过十款。",
                "快科技",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 3)

    def test_current_apple_repair_policy_appeal_is_strong(self):
        article = article_for(
            self.module,
            "碎屏背后的选择题：苹果 iPhone 独立维修案时隔 4 年重回法庭",
            "科技媒体 AppleInsider 报道，加州上诉法院推翻此前驳回决定，恢复消费者针对苹果第三方维修和保修政策的诉讼。",
            "IT之家",
            [
                "两名原告起诉苹果，指控其维修和保修政策限制第三方维修。",
                "原告被告知第三方门店维修会使设备保修失效，法院此前不允许修改起诉状。",
                "上诉法院恢复不正当竞争相关诉求，并将案件发回下级法院。",
            ],
        )
        self.assertEqual(article.relevance_tier, "strong")
        self.assertEqual(article.event_kind, "legal_antitrust")
        self.assertIn("lawsuit", article.relevance_reason)

    def test_executive_farewell_source_does_not_join_role_transition(self):
        reports = [
            article_for(
                self.module,
                "Tim Cook Steps Down as Apple CEO Tomorrow",
                "Cook steps down on September 1 and John Ternus takes over as CEO.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Today is Tim Cook's last day as Apple CEO, Ternus takes over",
                "Tim Cook steps down today after 15 years, with John Ternus taking over tomorrow.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Tim Cook Comments on His Final Day as Apple CEO",
                "Cook sent a farewell memo to Apple staff and thanked the team.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "蒂姆·库克卸任苹果 CEO 前发表告别信，期待约翰·特努斯接任",
                "库克在担任苹果 CEO 最后一天向全体员工发送内部告别信。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "库克回应苹果 CEO 最后一天：公司交给约翰·特努斯我无比安心",
                "库克在微博回应其担任 Apple CEO 的最后一天，并向 Apple 社区致意。",
                "快科技",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 2)
        farewell = next(
            event for event in events
            if any("Final Day" in article.title for article in event.articles)
        )
        self.assertEqual(
            {article.source for article in farewell.articles},
            {"AppleInsider", "cnBeta", "快科技"},
        )
        transition = next(
            event for event in events
            if any("Steps Down" in article.title for article in event.articles)
        )
        self.assertEqual(
            {article.source for article in transition.articles},
            {"MacRumors", "9to5Mac"},
        )

    def test_executive_tenure_market_retrospective_is_weak(self):
        article = article_for(
            self.module,
            "库克的中国十五年：种下苹果却养大对手",
            "文章回顾库克十五年任期内苹果在中国的市场、供应链和本地化投入变化。",
            "cnBeta",
            [
                "苹果大中华区营收从历史高点回落。",
                "报道复盘了库克任内约二十次访华和供应链演变。",
            ],
        )
        self.assertEqual(article.relevance_tier, "weak")
        self.assertIn("analysis", article.relevance_reason)


if __name__ == "__main__":
    unittest.main()
