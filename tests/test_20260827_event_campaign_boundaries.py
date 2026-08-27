import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "apple_news_20260827_event_campaign_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source):
    facts = [summary]
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 26, tzinfo=timezone.utc),
        published_raw="2026-08-26T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(f"{title} {summary}"),
    )


class EventCampaignBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_event_announcement_assets_merge_but_purchase_survey_stays_separate(self):
        announcement = article_for(
            self.module,
            "Apple announces iPhone 18 Pro and foldable iPhone Ultra event: Surprise and shine",
            "Apple scheduled its fall product event for September 9 at Apple Park.",
            "9to5Mac",
        )
        localized_tagline = article_for(
            self.module,
            "Apple's iPhone Ultra event tagline in China includes a hidden foldable teaser",
            "Apple localized the Surprise and shine event tagline for China.",
            "9to5Mac",
        )
        social_asset = article_for(
            self.module,
            "Apple's Surprise and shine hashmoji is already live on X",
            "Apple activated a custom AppleEvent hashmoji for its announced fall event.",
            "9to5Mac",
        )
        survey = article_for(
            self.module,
            "75% of US adults are not interested in a foldable iPhone",
            "A YouGov purchase-intent survey measured interest and willingness to pay.",
            "MacRumors",
        )
        chinese_survey = article_for(
            self.module,
            "调查显示 75% 美国成年人对折叠屏 iPhone 不感兴趣，平均只愿支付 781 美元",
            "YouGov 调查衡量了消费者对折叠屏 iPhone 的购买意愿和可接受价格。",
            "IT之家",
        )
        survey_with_product_background_lead = article_for(
            self.module,
            "苹果首款折叠屏 iPhone 还没卖就被嫌贵，75% 美国成年人明确表示没兴趣",
            "苹果首款折叠屏手机预计今年 9 月发布。",
            "快科技",
        )
        expected_roundup = article_for(
            self.module,
            "iPhone Ultra 三大核心亮点汇总，几乎无折痕",
            "文章汇总此前关于首款折叠屏 iPhone 的三项传闻规格。",
            "快科技",
        )

        events = self.module.cluster_articles(
            [
                survey,
                chinese_survey,
                survey_with_product_background_lead,
                expected_roundup,
                announcement,
                localized_tagline,
                social_asset,
            ]
        )
        title_sets = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 3, title_sets)
        self.assertTrue(
            any(
                {announcement.title, localized_tagline.title, social_asset.title} <= titles
                and survey.title not in titles
                and chinese_survey.title not in titles
                and survey_with_product_background_lead.title not in titles
                and expected_roundup.title not in titles
                for titles in title_sets
            ),
            title_sets,
        )
        self.assertTrue(
            any(
                titles
                == {
                    survey.title,
                    chinese_survey.title,
                    survey_with_product_background_lead.title,
                }
                for titles in title_sets
            ),
            title_sets,
        )
        for survey_article in (
            survey,
            chinese_survey,
            survey_with_product_background_lead,
        ):
            self.assertEqual(survey_article.relevance_tier, "weak")
            profile = self.module.article_reconciliation_profile(survey_article)
            self.assertEqual(profile.relevance_tier, "weak")
            self.assertIn("market-report", profile.identity.title_actions)
            self.assertFalse(
                any(
                    key.startswith("structured-title-product-release:")
                    for key in profile.event_keys
                ),
                profile.event_keys,
            )
        survey_event = next(
            event
            for event in events
            if survey.title in {item.title for item in event.articles}
        )
        self.assertEqual(survey_event.relevance_tier, "weak")
        roundup_event = next(
            event
            for event in events
            if any(item.title == expected_roundup.title for item in event.articles)
        )
        self.assertEqual(roundup_event.relevance_tier, "weak")

    def test_campaign_identity_uses_title_led_action_not_background_event_context(self):
        announcement = article_for(
            self.module,
            "Apple announces iPhone 18 Pro and foldable iPhone event for September 9",
            "Apple scheduled the Surprise and shine event for September 9.",
            "9to5Mac",
        )
        localized_announcement = article_for(
            self.module,
            "苹果秋季新品发布会官宣定档 9 月 10 日",
            "苹果宣布举行秋季发布会，中文主题为亮新篇，来耀眼。",
            "IT之家",
        )
        production_hurdle = article_for(
            self.module,
            "苹果首款折叠屏出师不利：iPhone Ultra 产能爬坡遇阻",
            "文章先回顾发布会日程，随后独家报道称量产爬坡遇到问题，首发供货仍不确定。",
            "快科技",
        )

        events = self.module.cluster_articles(
            [announcement, localized_announcement, production_hurdle]
        )
        title_sets = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)
        self.assertTrue(
            any(
                titles == {announcement.title, localized_announcement.title}
                for titles in title_sets
            ),
            title_sets,
        )

    def test_hashmoji_candidate_is_a_direct_first_party_campaign_activation(self):
        source = next(
            source for source in self.module.build_sources(datetime.now(timezone.utc))
            if source.name == "9to5Mac"
        )
        candidate = self.module.Candidate(
            source="9to5Mac",
            url="https://example.com/apple-event-hashmoji",
            title="Apple's Surprise and shine hashmoji is already live on X",
            summary="People using the AppleEvent hashtag now receive Apple's custom campaign icon.",
            feed_time_raw="2026-08-26T19:36:54+00:00",
            context="Apple event",
        )

        self.assertTrue(self.module.is_relevant_candidate(candidate, source))

    def test_campaign_name_and_regional_date_are_transitive_event_aliases(self):
        social_asset = article_for(
            self.module,
            "Apple's Surprise and shine hashmoji is already live on X",
            "Apple activated a custom AppleEvent campaign icon.",
            "9to5Mac",
        )
        truncated_announcement = article_for(
            self.module,
            "Apple announces its next event: Surprise and shine",
            "Apple officially announced its next product event.",
            "9to5Mac",
        )
        dated_announcement = article_for(
            self.module,
            "Apple Event announced for September 9: 'Surprise and shine'",
            "The Apple event will take place on September 9 at Apple Park.",
            "MacRumors",
        )
        localized_announcement = article_for(
            self.module,
            "苹果秋季发布会官宣定档 9 月 10 日",
            "苹果发布会将于北京时间 9 月 10 日举行，主题为亮新篇，来耀眼。",
            "IT之家",
        )
        special_event_announcement = article_for(
            self.module,
            "苹果官宣 9 月 9 日特别活动，iPhone 18 Pro 与折叠机或亮相",
            "苹果正式宣布，将于当地时间 9 月 9 日举行下一场产品发布活动。",
            "cnBeta",
        )

        events = self.module.cluster_articles(
            [
                social_asset,
                truncated_announcement,
                dated_announcement,
                localized_announcement,
                special_event_announcement,
            ]
        )

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])

    def test_campaign_asset_can_take_the_announced_tagline_from_its_lead(self):
        official = article_for(
            self.module,
            "Apple Event announced for September 9: 'Surprise and shine'",
            "Apple will hold the event at Apple Park on September 9.",
            "MacRumors",
        )
        localized_teaser = article_for(
            self.module,
            "Google Translate thinks Apple's iPhone Ultra event tagline in China includes a hidden foldable teaser",
            "Apple announced the event with the tagline ‘Surprise and shine,’ then localized it for China.",
            "9to5Mac",
        )

        events = self.module.cluster_articles([official, localized_teaser])

        self.assertEqual(
            len(events),
            1,
            [[item.title for item in event.articles] for event in events],
        )

    def test_ordinal_event_date_merges_official_announcement_not_attendee_side_event(self):
        official = article_for(
            self.module,
            "Apple Event announced for September 9: 'Surprise and shine'",
            "Apple will hold the event at Apple Park on September 9.",
            "MacRumors",
        )
        ordinal_announcement = article_for(
            self.module,
            "Apple announces September iPhone launch event",
            "Apple's next launch event will take place on September 9th at 1PM ET.",
            "The Verge",
        )
        attendee_activity = article_for(
            self.module,
            "If you're going to the iPhone event, there's a Welcome Run",
            "Attendees are invited to a walk, run, or wheelchair lap the night before the keynote.",
            "AppleInsider",
        )

        events = self.module.cluster_articles([official, ordinal_announcement, attendee_activity])
        title_sets = [{item.title for item in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)
        self.assertIn({official.title, ordinal_announcement.title}, title_sets)
        self.assertIn({attendee_activity.title}, title_sets)

    def test_forced_strong_editorial_recap_does_not_join_direct_product_report(self):
        editorial = article_for(
            self.module,
            "iPhone Ultra is coming: Three new features will be worth the wait",
            "The article recaps three previously reported rumors without new reporting.",
            "9to5Mac",
        )
        editorial.relevance_tier = "strong"
        editorial.relevance_reason = "legacy product-term promotion"
        color_report = article_for(
            self.module,
            "Leaker says iPhone Ultra will come in red and blue colors",
            "A current attributed leak identifies two possible case colors.",
            "AppleInsider",
        )

        events = self.module.cluster_articles([editorial, color_report])

        self.assertEqual(len(events), 2, [[item.title for item in event.articles] for event in events])
        editorial_event = next(
            event for event in events if editorial.title in {item.title for item in event.articles}
        )
        self.assertEqual(editorial_event.relevance_tier, "weak")

    def test_cross_language_support_document_reports_merge_by_concrete_action(self):
        english = article_for(
            self.module,
            "Apple explains why Spotlight indexing may take days after major OS updates",
            "Apple published a support document explaining Spotlight index rebuilding.",
            "MacRumors",
        )
        chinese = article_for(
            self.module,
            "苹果发布支持文档：系统更新后 Spotlight 重建索引可能需要数天",
            "苹果支持文档解释了系统更新后 Spotlight 索引重建所需时间。",
            "IT之家",
        )

        events = self.module.cluster_articles([english, chinese])

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])

    def test_pending_order_free_upgrade_reports_merge_without_joining_product_launch(self):
        free_upgrade = [
            article_for(
                self.module,
                "Apple giving some Mac mini customers a free upgrade",
                "Apple is replacing pending M4 Mac mini orders with equivalent M6 or M5 Pro models at no charge.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple upgrading recent Mac mini orders to M6 and M5 Pro models for free",
                "Apple launched a new Mac mini, and reports show that recent M4 purchases are being upgraded for free.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果免费升级部分 Mac mini 订单至 M6 芯片新机",
                "苹果将尚未发货的旧款 Mac mini 订单免费升级为新款机型。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "网友未发货 Mac mini M4 免费升级 M6 新款，价格不变",
                "苹果已发布 M6 和 M5 Pro 两款 Mac mini，售价 6999 元起。",
                "快科技",
            ),
        ]
        product_launch = article_for(
            self.module,
            "Apple launches the new Mac mini with M6 and M5 Pro",
            "Apple released a refreshed Mac mini product line at higher starting prices.",
            "The Verge",
        )

        events = self.module.cluster_articles([*free_upgrade, product_launch])
        title_sets = [{article.title for article in event.articles} for event in events]

        for article in free_upgrade[:-1]:
            profile = self.module.article_reconciliation_profile(article)
            self.assertIn(
                "primary-claim:mac-mini:pending-order-free-upgrade",
                profile.event_keys,
                (article.title, profile.event_keys),
            )

        self.assertEqual(len(events), 2, title_sets)
        self.assertTrue(
            any(
                {article.title for article in free_upgrade} == titles
                for titles in title_sets
            ),
            title_sets,
        )

    def test_mac_mini_order_upgrade_display_price_and_launch_actions_stay_separate(self):
        free_upgrade = [
            article_for(
                self.module,
                "Apple giving some Mac mini customers a free upgrade",
                "Pending M4 Mac mini orders are being replaced by M6 models at no additional cost.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果免费升级部分 Mac mini 订单至 M6 芯片新机",
                "尚未发货的旧款订单将免费更换为新款，价格保持不变。",
                "cnBeta",
            ),
        ]
        display = article_for(
            self.module,
            "新款 Mac mini 外接显示能力升级：最高支持 4K 165Hz",
            "新机改变了外接显示器组合与最高刷新率。",
            "cnBeta",
        )
        preorder = article_for(
            self.module,
            "苹果全新 Mac mini 今日接受预购，6999 元起",
            "Apple opened preorders for the new Mac mini product line.",
            "IT之家",
        )
        price = article_for(
            self.module,
            "两千多的 Mac mini 没买，现在新款涨到 7000 元",
            "The article reports a current Mac mini starting-price increase.",
            "快科技",
        )

        events = self.module.cluster_articles([*free_upgrade, display, preorder, price])
        title_sets = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 4, title_sets)
        self.assertTrue(
            any(titles == {article.title for article in free_upgrade} for titles in title_sets),
            title_sets,
        )

    def test_foldable_iphone_component_leaks_merge_even_with_reporting_prefixes(self):
        reports = [
            article_for(
                self.module,
                "Leakers show off purported iPhone Ultra motherboards",
                "Photos disclose the logic-board layout for Apple's foldable iPhone.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果首款折叠手机 iPhone Ultra 主板曝光",
                "新的泄露图片显示折叠屏 iPhone 的主板与 A20 Pro 芯片位置。",
                "IT之家",
            ),
            article_for(
                self.module,
                "疑似苹果折叠屏 iPhone 主板曝光，或预示新品发布临近",
                "报道展示疑似折叠屏 iPhone 的主板照片。",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")

    def test_apple_tv_content_action_can_be_led_by_cast_names(self):
        reports = [
            article_for(
                self.module,
                "Anthony Mackie and Jamie Dornan lead new Apple TV heist drama",
                "According to Apple TV, '12 12 12' will debut globally on November 13.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple TV reveals new crime thriller coming soon with major stars",
                "Apple TV announced '12 12 12,' starring Anthony Mackie and Jamie Dornan, for November 13.",
                "9to5Mac",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].category, "software_systems")

    def test_same_measured_product_ranking_merges_when_one_title_omits_report_firm(self):
        report = article_for(
            self.module,
            "iPhone 17 remains world's best selling smartphone",
            "Counterpoint reports that iPhone 17 led global smartphone sales in Q2 2026.",
            "MacRumors",
        )
        followup = article_for(
            self.module,
            "World's best selling smartphone is the iPhone 17 again",
            "Figures for Q2 2026 show that iPhone 17 is once more the biggest-selling phone worldwide.",
            "AppleInsider",
        )

        events = self.module.cluster_articles([report, followup])

        report_keys = self.module.article_reconciliation_profile(report).event_keys
        followup_keys = self.module.article_reconciliation_profile(followup).event_keys
        self.assertTrue(
            any(
                key.startswith("structured-component-measure:")
                for key in report_keys & followup_keys
            ),
            (report_keys, followup_keys),
        )
        supported_keys = self.module.supported_reconciliation_event_keys(
            [
                self.module.article_reconciliation_profile(report),
                self.module.article_reconciliation_profile(followup),
            ]
        )
        self.assertTrue(
            any(key.startswith("structured-attributed-measure:counterpoint:") for key in supported_keys),
            supported_keys,
        )
        self.assertTrue(
            any(
                key.startswith("structured-market-result:counterpoint:global:")
                and key.endswith(":apple-rank:1")
                for key in supported_keys
            ),
            supported_keys,
        )

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])

    def test_wallet_document_change_does_not_merge_with_regional_license_rollout(self):
        passport_change = article_for(
            self.module,
            "iOS 27 tweaks Apple Wallet's U.S. passport Digital ID feature",
            "Apple changed the passport Digital ID card and some beta users must add it again.",
            "MacRumors",
        )
        license_rollout = article_for(
            self.module,
            "Apple Wallet driver's license support launches in Virginia",
            "Virginia became the fifteenth state to offer a driver's license in Apple Wallet.",
            "9to5Mac",
        )

        events = self.module.cluster_articles([passport_change, license_rollout])

        self.assertEqual(len(events), 2, [[item.title for item in event.articles] for event in events])

    def test_editorial_and_multi_vendor_forms_cannot_be_promoted_by_product_terms(self):
        samples = [
            (
                "Concept video imagines Apple's foldable iPhone reveal",
                "A designer created a fan-made concept video that is not an Apple advertisement.",
            ),
            (
                "This foldable iPhone teaser is almost as good as Apple launch videos",
                "A YouTuber produced a concept showing how Apple might present the device.",
            ),
            (
                "M5 Max Mac Studio vs. M4 Max Mac Studio: faster, more expensive",
                "Apple's Mac Studio just got updated with the M5 Max chip.",
            ),
            (
                "Foldable iPhone is coming: three new features will be worth the wait",
                "The article recaps three previously reported rumors and explains why they matter.",
            ),
            (
                "iPhone 18 Pro: pre-orders and release date",
                "Apple has not announced product availability; the article makes an educated guess from historical patterns.",
            ),
            (
                "Amazon, Apple, Microsoft, and Dell collectively raise prices",
                "A broad industry report attributes multi-vendor price increases to memory costs without a new Apple-specific action.",
            ),
            (
                "华为耳机在中国高端市场份额第一，把苹果甩在身后",
                "The report measures Huawei's market position and uses Apple only as the competitor comparison.",
            ),
        ]

        for title, summary in samples:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary, "MacRumors")
                article.relevance_tier = "strong"
                article.relevance_reason = "legacy product-term promotion"
                event = self.module.cluster_articles([article])[0]

                self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_direct_first_party_capability_actions_are_not_deferred(self):
        samples = [
            (
                "1-800-APL-CARE now connects you with AI assistant instead of human",
                "If you dial Apple Support's phone number from the U.S., calls are routed to the assistant.",
                "software_systems",
            ),
            (
                "New Mac mini and Mac Studio add Genlock support",
                "Apple added Genlock synchronization to the new Macs through USB-C.",
                "hardware_products",
            ),
        ]

        for title, summary, category in samples:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary, "MacRumors")
                article.relevance_tier = "weak"
                article.relevance_reason = "legacy missing action owner"
                event = self.module.cluster_articles([article])[0]

                self.assertEqual(event.relevance_tier, "strong", event.relevance_reason)
                self.assertEqual(event.category, category)

    def test_same_legal_case_schedule_response_merges_across_languages(self):
        english = article_for(
            self.module,
            "OpenAI's lawsuit delays cause more harm every day, says Apple",
            "Apple pushed back against OpenAI trying to delay the trade-secret lawsuit.",
            "AppleInsider",
        )
        chinese = article_for(
            self.module,
            "苹果指责 OpenAI 拖延诉讼程序：每延误一天损害都在扩大",
            "苹果与 OpenAI 围绕商业秘密纠纷的法律战仍在持续。",
            "cnBeta",
        )

        events = self.module.cluster_articles([english, chinese])

        shared_keys = (
            self.module.article_reconciliation_profile(english).event_keys
            & self.module.article_reconciliation_profile(chinese).event_keys
        )
        self.assertTrue(
            any(key.startswith("apple-legal:") for key in shared_keys),
            shared_keys,
        )

        self.assertEqual(len(events), 1, [[item.title for item in event.articles] for event in events])

    def test_selected_detail_failures_receive_one_bounded_second_pass(self):
        candidates = [
            self.module.Candidate(
                source="9to5Mac",
                url="https://example.com/apple-event-asset",
                title="Apple activates an event campaign asset",
            ),
            self.module.Candidate(
                source="MacRumors",
                url="https://example.com/other-apple-news",
                title="Apple releases another update",
            ),
        ]
        attempts = {candidate.url: 0 for candidate in candidates}

        def fake_fetch(url, cache_dir, diagnostics, timeout=None, retries=None):
            attempts[url] += 1
            if url.endswith("apple-event-asset") and attempts[url] == 1:
                diagnostics.setdefault("failed_fetches", []).append(
                    {"url": url, "error": "TimeoutError: transient"}
                )
                return None
            return f"detail:{url}"

        diagnostics = {"failed_fetches": []}
        with TemporaryDirectory() as cache_dir, mock.patch.object(
            self.module,
            "fetch_url",
            side_effect=fake_fetch,
        ):
            results = self.module.fetch_detail_page_texts(
                candidates,
                Path(cache_dir),
                diagnostics,
            )

        self.assertEqual(
            results,
            [
                "detail:https://example.com/apple-event-asset",
                "detail:https://example.com/other-apple-news",
            ],
        )
        self.assertEqual(attempts[candidates[0].url], 2)
        self.assertEqual(attempts[candidates[1].url], 1)
        self.assertEqual(diagnostics["detail_fetch_retry_count"], 1)
        self.assertEqual(diagnostics["detail_fetch_retry_recovered"], 1)


if __name__ == "__main__":
    unittest.main()
