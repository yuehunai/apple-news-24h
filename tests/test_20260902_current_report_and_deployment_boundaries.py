import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260902_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source, facts=None):
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
    module.reconcile_article_relevance(article, module.article_reconciliation_profile(article))
    return article


class CurrentReportAndDeploymentBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_one_multi_product_mockup_disclosure_remains_one_source_event(self):
        title = "苹果 iPhone 18 Pro Max 和首款折叠 iPhone Ultra 机模曝光"
        summary = (
            "Unbox Therapy 发布同一段视频，展示 iPhone 18 Pro Max 与首款折叠 "
            "iPhone Ultra 的未发布机模，并比较两款设备的外形。"
        )
        facts = [
            "iPhone 18 Pro Max 机模的外观变化相对有限。",
            "折叠 iPhone Ultra 机模采用两颗后置摄像头。",
        ]

        self.assertEqual(
            self.module.compound_article_variants(title, summary, facts),
            [(title, summary, facts)],
        )
        tier, reason = self.module.classify_relevance_tier(title, summary, facts, "IT之家")
        self.assertEqual(tier, "strong", reason)

    def test_released_product_personal_hands_on_stays_weak(self):
        article = article_for(
            self.module,
            "iPhone 17 Pro 上手三个月：这是我最喜欢的五个功能",
            "作者分享个人使用体验，没有新的苹果产品、政策或平台动作。",
            "IT之家",
        )
        self.assertEqual(article.relevance_tier, "weak")

    def test_first_regulated_clinical_deployment_is_not_a_routine_third_party_app_update(self):
        reports = [
            article_for(
                self.module,
                "全球首例苹果 Vision Pro 辅助髋关节镜手术完成，医生无需频繁扭头看屏幕",
                (
                    "Duke Health 完成全球首例使用 Stryker SportSuite Vision 和 Apple Vision Pro "
                    "辅助的髋关节镜手术；该应用已获得 FDA De Novo 授权，可在术中使用。"
                ),
                "IT之家",
                ["医生可在视野内查看关节镜画面，不必反复转头看外部显示器。"],
            ),
            article_for(
                self.module,
                "Apple Vision Pro assists hip surgery with Stryker app",
                (
                    "The first surgery using Stryker's SportSuite Vision app on Apple Vision Pro "
                    "has been completed at Duke Health. The FDA-authorized app places arthroscopic "
                    "and CT imaging in the surgeon's field of view."
                ),
                "AppleInsider",
            ),
        ]

        self.assertTrue(all(article.relevance_tier in {"strong", "ecosystem"} for article in reports))
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertIn(events[0].relevance_tier, {"strong", "ecosystem"})

    def test_routine_vision_pro_app_update_stays_weak(self):
        tier, _reason = self.module.classify_relevance_tier(
            "Third-party Vision Pro app adds three new toolbar controls",
            "The independent developer updated its app. Apple announced no platform API or policy change.",
            [],
            "9to5Mac",
        )
        self.assertEqual(tier, "weak")

    def test_current_quantified_apple_tenure_result_is_news_and_merges_cross_language(self):
        reports = [
            article_for(
                self.module,
                "AAPL gained 2,736% under Cook, but Ternus doesn't have to emulate him",
                (
                    "Bloomberg reports that Apple shares gained 2,275% during Tim Cook's tenure and "
                    "delivered a 2,736% total return including dividends; market value rose from under "
                    "$350 billion to $4.6 trillion. The article then discusses Ternus's options."
                ),
                "9to5Mac",
            ),
            article_for(
                self.module,
                "库克执掌 15 年间，苹果股价累计涨了 2275%",
                (
                    "据彭博社最新统计，库克任内苹果股价累计上涨 2275%，计入股息的总回报为 "
                    "2736%，公司市值从不足 3500 亿美元增至 4.6 万亿美元。"
                ),
                "IT之家",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in reports))
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家"})

    def test_quantified_current_report_gets_detail_priority_over_opinion_retrospective(self):
        current = self.module.Candidate(
            source="IT之家",
            url="https://example.com/current-market-report",
            title="库克执掌 15 年间，苹果股价累计涨了 2275%",
            summary=(
                "据彭博社报道，库克任内不仅进一步确立了苹果作为全球标志性品牌的地位，"
                "也让苹果股票成为过去十多年最稳定、最成功的大型科技股投资之一。"
            ),
        )
        opinion = self.module.Candidate(
            source="IT之家",
            url="https://example.com/opinion-retrospective",
            title="库克十五年功过：下一任苹果 CEO 应该学什么",
            summary="作者回顾库克的管理风格，没有新的数据、公司动作或当前报告。",
        )

        current_tier, current_reason = self.module.classify_relevance_tier(
            current.title, current.summary, [], current.source
        )
        opinion_tier, _opinion_reason = self.module.classify_relevance_tier(
            opinion.title, opinion.summary, [], opinion.source
        )
        self.assertEqual(current_tier, "strong", current_reason)
        self.assertEqual(opinion_tier, "weak")
        self.assertGreaterEqual(self.module.candidate_detail_priority(current)[0], 60)
        self.assertGreater(
            self.module.candidate_detail_priority(current)[0],
            self.module.candidate_detail_priority(opinion)[0],
        )

    def test_display_feature_report_does_not_absorb_product_lifecycle_change(self):
        reports = [
            article_for(
                self.module,
                "为 OLED MacBook Pro 铺路：苹果 macOS 27 增强液态玻璃高光 HDR 效果",
                (
                    "macOS 27 Golden Gate 在高端 OLED 显示器上呈现更强的 Liquid Glass "
                    "HDR 高光效果，报道认为这可能为未来 OLED MacBook Pro 做准备。"
                ),
                "IT之家",
            ),
            article_for(
                self.module,
                "macOS Golden Gate Seems to Hint at MacBook Pro With OLED Display",
                (
                    "Liquid Glass interface elements have stronger HDR highlights on OLED displays, "
                    "possibly in preparation for future OLED MacBook Pro models."
                ),
                "MacRumors",
            ),
            article_for(
                self.module,
                "服役 7 年终成绝唱！苹果将三款 Intel MacBook 打入冷宫：官方不再提供维修",
                (
                    "快科技消息，苹果近日更新了过时产品名单，将三款搭载英特尔芯片的 "
                    "MacBook 正式列入其中。这意味着官方硬件维修服务与零部件供应将正式终止。"
                    "文章背景还说明 macOS 26 Tahoe 是最后一个支持 Intel Mac 的大版本，"
                    "macOS 27 Golden Gate 将只支持 Apple 芯片 Mac。"
                ),
                "快科技",
                [
                    "苹果近日更新了过时产品名单，将三款搭载英特尔芯片的 MacBook 正式列入其中。",
                    "官方硬件维修服务与零部件供应将正式终止。",
                ],
            ),
        ]
        reports[0].published_utc = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)
        reports[1].published_utc = datetime(2026, 9, 1, 19, 34, tzinfo=timezone.utc)
        reports[2].published_utc = datetime(2026, 9, 1, 10, 41, tzinfo=timezone.utc)
        lifecycle_profile = self.module.article_reconciliation_profile(reports[2])
        self.assertIn(
            "assertion-action:product-lifecycle-obsolete",
            lifecycle_profile.separation_keys,
        )

        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 2])
        lifecycle_event = next(
            event
            for event in events
            if any("打入冷宫" in article.title for article in event.articles)
        )
        self.assertEqual(len(lifecycle_event.articles), 1)

    def test_ceo_transition_merges_without_absorbing_role_or_product_policy_actions(self):
        reports = [
            article_for(
                self.module,
                "John Ternus is now the CEO of Apple",
                "Ternus formally took over as CEO on September 1 while Tim Cook became executive chair.",
                "The Verge",
            ),
            article_for(
                self.module,
                "John Ternus is Now Apple's CEO",
                "Apple's leadership page now lists Ternus as CEO and Cook as executive chair.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果官网更新：约翰・特努斯正式出任首席执行官，蒂姆・库克转任董事会执行主席",
                "苹果领导层页面确认特努斯正式出任 CEO。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Luca Maestri isn't running Apple's Corporate Services anymore",
                "Maestri stepped down from the separate Corporate Services role.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple customer service denies iPhone charger and EarPods policy change",
                "Apple said it issued no notice restoring in-box accessories.",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1, 3])

    def test_ceo_social_account_and_compensation_each_merge_but_stay_separate(self):
        reports = [
            article_for(
                self.module,
                "Apple's New CEO John Ternus is Now on X",
                "Ternus opened an X account and posted his first message.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果新任 CEO 特努斯入驻微博、X 平台，首条博文向网友问好",
                "特努斯开通两个社交账号并发布首条消息。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果新任 CEO 约翰·特努斯在 X 平台发布首条动态",
                "特努斯正式加入 X 并发布个人账号首条动态。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "Here's What Apple is Paying John Ternus to Run the Company",
                "An SEC filing discloses the new CEO's salary and equity compensation.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果新 CEO 特努斯薪酬方案曝光：基本年薪 300 万美元",
                "苹果提交的监管文件披露其薪酬和股权奖励。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [2, 3])

    def test_first_ceo_employee_memo_and_its_launch_tease_form_one_document_event(self):
        reports = [
            article_for(
                self.module,
                "Read John Ternus's full memo to Apple employees on his first day as CEO",
                "Ternus sent his first company-wide employee memo and teased a huge launch next week.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Teases 'Huge Launch' Next Week",
                "The teaser appeared in John Ternus's first memo to Apple employees as CEO.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果新 CEO 特努斯首封内部信：下周新品发布必将惊艳四座",
                "特努斯在上任首封全员内部信中预告下周新品发布。",
                "IT之家",
            ),
            article_for(
                self.module,
                "直指 iPhone Ultra！苹果新 CEO 放话：下周发布新品必将惊艳四座",
                "新任 CEO 在发给全体内部员工的公开信中预告下周发布活动，折叠 iPhone 只是媒体解读。",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 4)

    def test_pure_ceo_transition_is_not_reclassified_by_memo_background(self):
        transition = article_for(
            self.module,
            "John Ternus is now the CEO of Apple",
            "Apple confirmed the leadership transition. A later paragraph mentions his employee memo.",
            "The Verge",
        )
        memo = article_for(
            self.module,
            "John Ternus sends first memo as Apple CEO",
            "The new CEO sent his first company-wide memo to staff.",
            "9to5Mac",
        )
        events = self.module.cluster_articles([transition, memo])
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1])

    def test_openai_response_merges_without_absorbing_apple_evidence_filing(self):
        reports = [
            article_for(
                self.module,
                "OpenAI calls trade secret dispute 'a mess of Apple's own making'",
                "OpenAI denied stealing Apple trade secrets and responded to Apple's evidence claims.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Dispute With OpenAI Said to Be a 'Mess of Apple's Own Making'",
                "OpenAI filed a response denying Apple's trade-secret allegations.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "OpenAI 否认窃取苹果商业机密：自己一手造成的还想赖别人",
                "OpenAI 提交回应文件，否认苹果关于商业秘密的指控。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Apple accuses OpenAI of destroying evidence",
                "Apple filed allegations that OpenAI destroyed evidence in the trade-secret case.",
                "The Verge",
            ),
        ]

        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 3])

    def test_vision_group_layoff_reports_use_one_canonical_workforce_subject(self):
        reports = [
            article_for(
                self.module,
                "Apple's Vision Pro Layoffs Were Broader Than First Reported",
                "Apple cut more jobs across the Vision Pro and visionOS organization.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "古尔曼：苹果 Vision Pro 团队裁员规模超出此前报道，visionOS 等部门受波及",
                "同一轮裁员覆盖 Vision Pro、visionOS 与相关团队。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_foldable_iphone_magsafe_support_merges_across_languages(self):
        reports = [
            article_for(
                self.module,
                "Foldable iPhone Ultra Likely Has MagSafe Charging",
                "Gurman reports that Apple's foldable iPhone will support MagSafe charging.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "古尔曼：苹果首款折叠手机 iPhone Ultra 有望支持 MagSafe 磁吸充电",
                "报道称首款折叠 iPhone 将支持 MagSafe。",
                "IT之家",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_mac_app_store_intel_support_removal_policy_merges_across_languages(self):
        reports = [
            article_for(
                self.module,
                "Apple tells Mac App Store developers they can now drop Intel support",
                "Apple notified developers that apps requiring macOS 13 or later may become arm64-only.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果通知 Mac 开发者可移除英特尔 CPU 支持，需 macOS 13 及以上",
                "开发者可把构建设置改为仅支持 arm64 并重新提交 Mac App Store。",
                "IT之家",
            ),
            article_for(
                self.module,
                "彻底说再见！苹果允许开发者直接移除英特尔CPU支持",
                "苹果向开发者发送通知，Mac App Store 通用应用现可移除 Intel Mac 支持。",
                "快科技",
            ),
        ]
        self.assertEqual(len(self.module.cluster_articles(reports)), 1)

    def test_openai_response_title_outranks_evidence_background_in_lead(self):
        reports = [
            article_for(
                self.module,
                "OpenAI calls trade secret dispute 'a mess of Apple's own making'",
                "Apple first presented shocking evidence, but OpenAI's filing denies theft and calls the dispute Apple's own making.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Dispute With OpenAI Said to Be a 'Mess of Apple's Own Making'",
                "OpenAI denied Apple's trade-secret allegations in its court response.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple accuses OpenAI of destroying evidence",
                "Apple filed a request for expedited discovery over alleged evidence destruction.",
                "The Verge",
            ),
            article_for(
                self.module,
                "OpenAI称苹果自身应为商业秘密诉讼混乱负责",
                "OpenAI 否认苹果的窃密指控，并提交法庭回应。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 3])

    def test_specific_ceo_document_policy_and_profile_actions_outrank_transition_background(self):
        reports = [
            article_for(
                self.module,
                "John Ternus is Now Apple's CEO",
                "Apple's leadership page confirms the CEO transition.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "John Ternus addresses staff as he takes over as Apple CEO",
                "New Apple CEO John Ternus emailed all staff with his first company-wide memo.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "约翰·特努斯正式出任苹果CEO，内部备忘录预告下周重大新品发布",
                "苹果完成 CEO 交接，特努斯在内部备忘录中预告新品。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "苹果新CEO上任首日！新iPhone被曝恢复赠送充电头、有线耳机 官方回应",
                "苹果客服否认恢复随盒配件，称没有发布任何政策变更通知。",
                "快科技",
            ),
            article_for(
                self.module,
                "苹果新任 CEO 特努斯微博头像太糊，运营团队更换高清素材",
                "特努斯上任后开通微博账号，团队随后替换了个人资料头像。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果宣布约翰·特努斯出任 CEO，库克担任执行董事长",
                "苹果官网确认特努斯已正式出任首席执行官。",
                "cnBeta",
            ),
        ]
        events = self.module.cluster_articles(reports)
        self.assertEqual(sorted(len(event.articles) for event in events), [1, 1, 2, 2])

    def test_executive_retrospective_question_is_not_promoted_as_current_company_report(self):
        title = "被骂了15年的库克，为什么能让苹果市值翻了10倍？"
        summary = "文章回顾库克任期的功过与管理风格，没有新的公司披露或当前研究报告。"
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_external_praise_of_new_ceo_is_opinion_not_apple_action(self):
        tier, reason = self.module.classify_relevance_tier(
            "苹果换帅！知名投资人夸赞新负责人：他应该会是一个很好的 CEO",
            "一位外部投资人发表个人看法，苹果没有宣布新的产品、政策或组织动作。",
            [],
            "快科技",
        )
        self.assertEqual(tier, "weak", reason)

    def test_named_third_party_ios_app_spotlight_stays_weak_after_reconciliation(self):
        article = article_for(
            self.module,
            "Cibby is a beautifully designed iOS app for physical video game collectors",
            (
                "Cibby is a new independent iOS app made by Michael Flarup for cataloging "
                "physical games. Apple announced no platform, API, policy, or first-party change."
            ),
            "9to5Mac",
            [
                "Earlier this year, Apple announced a partnership with Ford for native Apple Maps integration.",
                "Ford wanted a close working relationship with the Apple Maps team for EV mapping.",
                "CarPlay users can still choose Apple Maps, Google Maps, Waze, and other apps.",
            ],
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_leadership_scorecard_and_resurfaced_old_interview_stay_weak(self):
        scorecard = article_for(
            self.module,
            "Tim Cook's Apple: his 10 biggest wins and misses",
            "An editorial retrospective evaluates Cook's 15-year tenure without a new Apple action.",
            "The Verge",
        )
        old_interview = article_for(
            self.module,
            "Steve Jobs in 1996: 'I still think Apple has a future'",
            "A vintage 1996 interview has resurfaced and provides historical perspective.",
            "9to5Mac",
        )
        self.assertEqual(scorecard.relevance_tier, "weak", scorecard.relevance_reason)
        self.assertEqual(old_interview.relevance_tier, "weak", old_interview.relevance_reason)

    def test_official_product_obsolescence_is_a_strong_hardware_lifecycle_action(self):
        article = article_for(
            self.module,
            "服役7年终成绝唱！苹果将三款Intel MacBook打入冷宫：官方不再提供维修",
            (
                "苹果更新过时产品名单，将三款 Intel MacBook 正式列入其中，"
                "官方硬件维修与零部件供应随之终止。"
            ),
            "快科技",
        )
        self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)
        self.assertEqual(article.category, "hardware_products")

    def test_executive_role_exit_can_use_the_opening_lead_and_merge_cross_source(self):
        reports = [
            article_for(
                self.module,
                "Ex-Apple CFO Luca Maestri Winding Down His Time at the Company",
                (
                    "Former Apple CFO Luca Maestri stayed to run Corporate Services, but stepped "
                    "down from that position in recent weeks."
                ),
                "MacRumors",
            ),
            article_for(
                self.module,
                "Luca Maestri isn't running Apple's Corporate Services anymore",
                "Maestri stepped down from Apple's Corporate Services role in recent weeks.",
                "AppleInsider",
            ),
        ]
        self.assertTrue(all(article.relevance_tier == "strong" for article in reports))
        events = self.module.cluster_articles(reports)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_first_party_maps_rename_is_strong_and_merges_across_headline_angles(self):
        reports = [
            article_for(
                self.module,
                "Apple Maps Renames Lake Ontario 'Lake America'",
                "Apple Maps now displays Lake America for users in the United States.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple Maps follows Google in renaming Lake Ontario",
                "Apple Maps has officially changed Lake Ontario to Lake America for U.S. users.",
                "The Verge",
            ),
            article_for(
                self.module,
                "Apple Maps now uses 'Lake America' instead of 'Lake Ontario' after Trump order",
                "Apple Maps has started renaming Lake Ontario to Lake America for U.S. users.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple Maps bring up Lake Ontario if you search for 'Lake America'",
                "Apple Maps search now resolves Lake America to Lake Ontario.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple Maps面向美国用户将“安大略湖”改名为“美国湖”",
                "Apple Maps 已面向美国用户把安大略湖标注为美国湖。",
                "cnBeta",
            ),
        ]
        third_party_preference = article_for(
            self.module,
            "Ford explains why it chose Apple Maps over Google for its new EVs",
            (
                "Ford vice president Alan Clarke explains the automaker's decision to use "
                "Apple Maps instead of Google Maps for its upcoming Universal Electric "
                "Vehicle Platform and what it means for CarPlay Ultra."
            ),
            "9to5Mac",
        )
        self.assertTrue(all(article.relevance_tier == "strong" for article in reports))
        self.assertEqual(third_party_preference.relevance_tier, "weak")
        profiles = [self.module.article_reconciliation_profile(article) for article in reports]
        shared_claims = set.intersection(*(set(profile.event_keys) for profile in profiles))
        self.assertTrue(
            any("named-object-rename-class:lake:united-states" in key for key in shared_claims),
            shared_claims,
        )
        events = self.module.cluster_articles([*reports, third_party_preference])
        self.assertEqual(len(events), 2)
        rename_event = next(event for event in events if event.relevance_tier == "strong")
        self.assertEqual(len(rename_event.articles), 5)
        self.assertEqual(rename_event.category, "software_systems")
        self.assertNotIn(third_party_preference, rename_event.articles)

    def test_versioned_os_feature_change_keeps_software_category(self):
        article = article_for(
            self.module,
            "iOS 27 breaks 15 years of muscle memory on iPhone and iPad",
            (
                "Starting with iOS 27, Apple changes how users open Notification Center on "
                "iPhone and iPad when Siri AI is enabled."
            ),
            "9to5Mac",
        )
        self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)
        self.assertEqual(article.category, "software_systems")


if __name__ == "__main__":
    unittest.main()
