import importlib.util
import itertools
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_identity_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="9to5Mac", facts=None):
    facts = facts or []
    event_kind = module.detect_event_kind(title, summary, facts)
    relevance_tier, relevance_reason = module.classify_relevance_tier(
        title, summary, facts, source
    )
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((title, summary)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc),
        published_raw="2026-07-16T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=event_kind,
        relevance_tier=relevance_tier,
        relevance_reason=relevance_reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


def event_partitions(events):
    return {
        frozenset(article.title for article in event.articles)
        for event in events
    }


class EventIdentityArchitectureTests(unittest.TestCase):
    def test_legal_counterparty_and_case_action_define_separate_events(self):
        module = load_module()
        doj_articles = [
            article_for(
                module,
                "Apple and DOJ Hold Early Settlement Talks in iPhone Antitrust Case",
                "Apple proposed several offers to settle the 2024 Department of Justice antitrust lawsuit.",
                "MacRumors",
            ),
            article_for(
                module,
                "就反垄断诉讼事宜，消息称苹果和美国司法部展开早期和解谈判",
                "苹果与美国司法部正在讨论 2024 年 iPhone 反垄断案件的和解方案。",
                "IT之家",
            ),
            article_for(
                module,
                "Apple's long-running DOJ antitrust case may not make it to trial",
                "Apple and the Justice Department are discussing a settlement before the case reaches trial.",
                "AppleInsider",
            ),
        ]
        openai_articles = [
            article_for(
                module,
                "Apple sends legal letters to former employees now at OpenAI",
                "Apple sent preservation letters in its trade-secret lawsuit against OpenAI.",
                "9to5Mac",
            ),
            article_for(
                module,
                "OpenAI 与苹果法律纠纷升级，约 40 名前员工收到证据保全函",
                "苹果要求 OpenAI 的前苹果员工保存与硬件商业机密诉讼有关的数据。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles([*doj_articles, *openai_articles])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in doj_articles), event_partitions(events))
        self.assertIn(frozenset(article.title for article in openai_articles), event_partitions(events))
        self.assertTrue(all(article.event_kind == "legal_antitrust" for article in doj_articles))

    def test_service_price_identity_merges_same_service_without_crossing_icloud(self):
        module = load_module()
        music_articles = [
            article_for(
                module,
                "Apple raises prices for Apple Music and Apple One subscriptions",
                "Apple Music Individual, Student, and Family prices increased, while two Apple One tiers also rose.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Music Now Costs $11.99 as Apple Increases Subscription Prices",
                "Apple increased Apple Music subscription prices in the United States.",
                "MacRumors",
            ),
            article_for(
                module,
                "国区个人 11 元 / 月涨至 12 元 / 月，苹果 Apple Music 订阅全球多地涨价",
                "Apple Music 的个人、学生和家庭套餐同步调整价格。",
                "IT之家",
            ),
            article_for(
                module,
                "Is Apple One worth it after the latest price increases?",
                "The analysis follows the same Apple Music and Apple One price announcement and lists the new tiers.",
                "AppleInsider",
            ),
        ]
        icloud_articles = [
            article_for(
                module,
                "Apple Raises iCloud+ Prices in 8 Countries",
                "Apple increased iCloud+ prices by 11% to 55% in eight markets.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 iCloud+ 订阅在土耳其、尼日利亚等地涨价",
                "八个国家和地区的 iCloud+ 套餐价格上涨约 11% 至 55%。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles([*music_articles, *icloud_articles])

        self.assertEqual(len(events), 3, event_partitions(events))
        self.assertIn(frozenset(article.title for article in music_articles[:-1]), event_partitions(events))
        self.assertIn(frozenset(article.title for article in icloud_articles), event_partitions(events))
        self.assertIn(frozenset({music_articles[-1].title}), event_partitions(events))

    def test_specific_hardware_component_and_market_report_identity_merge_across_language(self):
        module = load_module()
        camera_articles = [
            article_for(
                module,
                "iPhone 18 Pro Max leak points to variable aperture and Sony IMX905 camera",
                "A leaked diagnostic file identifies the IMX905 main camera and variable aperture hardware.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 iPhone 18 Pro Max 影像规格再曝：可变光圈，主摄索尼 IMX905",
                "泄露诊断日志确认 IMX905 主摄和可变光圈机构。",
                "IT之家",
            ),
        ]
        loyalty_articles = [
            article_for(
                module,
                "iPhone Loyalty Rate Climbs to 87% as Switching to Android Slows",
                "CIRP reports that 87% of new iPhone buyers upgraded from another iPhone.",
                "MacRumors",
            ),
            article_for(
                module,
                "CIRP 报告美国新购苹果 iPhone 用户画像：87% 来自同平台升级",
                "CIRP 数据显示 Android 转入比例为 12%。",
                "IT之家",
            ),
            article_for(
                module,
                "苹果 iPhone 市场表现强劲，Android 阵营转换用户比例维持低位",
                "CIRP 报告显示 87% 的买家从旧 iPhone 升级，Android 转入比例为 12%。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles([*camera_articles, *loyalty_articles])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in camera_articles), event_partitions(events))
        self.assertIn(frozenset(article.title for article in loyalty_articles), event_partitions(events))
        loyalty_event = next(event for event in events if loyalty_articles[0] in event.articles)
        self.assertTrue(all(article.event_kind == "hardware_market" for article in loyalty_event.articles))
        self.assertNotIn("mixed event kinds", loyalty_event.merge_warnings)

    def test_same_product_price_action_and_region_merge_across_language(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Raises iPhone Prices in Japan",
                "Apple raised prices across the iPhone lineup in Japan by as much as 11.3%.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果多款 iPhone 在日本市场涨价，最高涨幅达 11.3%",
                "iPhone 17、iPhone Air 和 Pro 系列在日本同步提价。",
                "IT之家",
            ),
            article_for(
                module,
                "日元贬值压力增大：苹果公司上调日本市场 iPhone 售价",
                "苹果日本在线商店更新了 iPhone 价格。",
                "cnBeta",
            ),
        ]
        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))

    def test_direct_apple_actions_override_broad_third_party_context(self):
        module = load_module()
        cases = [
            (
                "Apple Car Keys reportedly coming to major Chinese automaker",
                "Apple Wallet backend code adds digital car key support for GWM Tank SUVs.",
                "wallet_feature",
            ),
            (
                'Apple ordered to remove 8 "nudify" apps from the App Store',
                "A prosecutor ordered Apple to remove policy-violating apps, and Apple removed three developers' apps.",
                "app_store_trust",
            ),
            (
                "苹果联想戴尔惠普优先拿货，曝长鑫存储 DRAM 订单已排至 2027 年底",
                "苹果完成长鑫 DRAM 测试并获得优先供货，属于 Apple 设备内存供应链安排。",
                "hardware_market",
            ),
            (
                "Apple Passed Nvidia to Become World's Most Valuable Company Again",
                "Apple shares rose 20% and its market capitalization reached nearly $5 trillion.",
                "hardware_market",
            ),
        ]

        for title, summary, expected_kind in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(tier, "strong", reason)
                self.assertEqual(module.detect_event_kind(title, summary), expected_kind)

    def test_poll_and_body_background_cannot_override_title_event_semantics(self):
        module = load_module()
        poll_title = "What will you do if Apple's higher pricing turns out to be permanent?"
        poll_summary = "Vote in our poll after Apple raised several product prices last month."
        tier, reason = module.classify_relevance_tier(poll_title, poll_summary, [], "9to5Mac")
        self.assertEqual(tier, "weak", reason)

        stock_title = "Apple overtakes Nvidia, becomes world's most valuable company"
        stock_summary = (
            "Apple closed at a $4.88 trillion market capitalization. Historical background mentions "
            "China, Apple Intelligence filings, Siri delays, tariffs, and the hardware roadmap."
        )
        self.assertEqual(module.detect_event_kind(stock_title, stock_summary), "hardware_market")
        self.assertEqual(module.choose_category(stock_title, stock_summary), "hardware_products")

        doj_title = "Apple's long-running DOJ antitrust case may not make it to trial"
        doj_summary = (
            "Apple and the Justice Department are discussing settlement. Background describes iPhone apps, "
            "smartwatches, Messages, wallets, and other product changes."
        )
        self.assertEqual(module.detect_event_kind(doj_title, doj_summary), "legal_antitrust")
        self.assertEqual(module.choose_category(doj_title, doj_summary), "software_systems")

    def test_shared_product_cannot_merge_distinct_component_and_system_actions(self):
        module = load_module()
        camera = article_for(
            module,
            "苹果 iPhone 18 Pro Max 影像规格再曝：可变光圈，主摄索尼 IMX905",
            "泄露诊断日志确认 IMX905 主摄和可变光圈机构。",
            "IT之家",
        )
        recovery = article_for(
            module,
            "iOS 27: Access the New iPhone Recovery Screen",
            "The new recovery screen offers Recovery Assistant, diagnostics, software update, and erase options.",
            "MacRumors",
        )

        events = module.cluster_articles([camera, recovery])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_future_price_forecast_does_not_merge_with_current_regional_price_change(self):
        module = load_module()
        forecast = article_for(
            module,
            "机构预判 iPhone 18 Pro 提价后依旧大卖",
            "An analyst forecasts that Apple may raise iPhone 18 Pro prices at the future launch.",
            "快科技",
        )
        current = article_for(
            module,
            "Apple Raises iPhone Prices in Japan",
            "Apple updated current iPhone prices in its Japanese online store.",
            "MacRumors",
        )

        events = module.cluster_articles([forecast, current])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_app_store_enforcement_merges_same_violation_without_absorbing_other_investigation(self):
        module = load_module()
        nudify = [
            article_for(
                module,
                'Apple ordered to remove 8 "nudify" apps from the App Store',
                "San Francisco demanded that Apple pull nonconsensual undressing apps.",
                "9to5Mac",
            ),
            article_for(
                module,
                "美国检方要求苹果 App Store 下架 8 款 AI 脱衣应用",
                "苹果已移除三款涉事应用，并要求其他开发者整改。",
                "IT之家",
            ),
        ]
        gambling = article_for(
            module,
            "Investigation reveals dozens of disguised gambling apps on the App Store in Brazil",
            "The report found more than 60 jacket apps that reveal gambling services only in Brazil.",
            "9to5Mac",
        )

        events = module.cluster_articles([*nudify, gambling])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in nudify), event_partitions(events))
        self.assertIn(frozenset({gambling.title}), event_partitions(events))

    def test_direct_supply_and_car_key_titles_survive_multi_vendor_context(self):
        module = load_module()
        supply_title = "长鑫存储内存订单已排至 2027 年底：苹果、联想等厂商优先拿货"
        supply_summary = (
            "The report lists Apple, Lenovo, Dell, and HP as priority DRAM customers, then compares "
            "Samsung, Micron, and other memory vendors."
        )
        tier, reason = module.classify_relevance_tier(supply_title, supply_summary, [], "快科技")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.detect_event_kind(supply_title, supply_summary), "hardware_market")

        car_key_title = "Apple Car Keys reportedly coming to major Chinese automaker"
        car_key_summary = "Code changes indicate GWM Tank vehicles will gain the first-party digital key feature."
        tier, reason = module.classify_relevance_tier(car_key_title, car_key_summary, [], "9to5Mac")
        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.detect_event_kind(car_key_title, car_key_summary), "wallet_feature")

    def test_memory_priority_order_headlines_share_specific_supply_identity(self):
        module = load_module()
        priority_order_english = article_for(
            module,
            "CXMT DRAM orders booked through 2027 as Apple gets priority supply",
            "Apple, Lenovo, Dell, and HP completed product testing and received priority allocation.",
            "快科技",
        )
        priority_order = article_for(
            module,
            "长鑫存储 DRAM 订单排至 2027 年底，苹果等厂商优先拿货",
            "苹果获得优先供货，报道还比较美国和中国内存市场。",
            "IT之家",
        )

        left = module.article_title_led_event_identity(priority_order_english)
        right = module.article_title_led_event_identity(priority_order)

        self.assertEqual(module.identity_pair_decision(left, right), "match")
        events = module.cluster_articles([priority_order_english, priority_order])
        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertNotIn("multiple region-specific markers", events[0].merge_warnings)

    def test_memory_supplier_policy_block_does_not_merge_with_order_allocation(self):
        module = load_module()
        policy_block = article_for(
            module,
            "内存短缺逼苹果找长鑫救急！美国议员紧急叫停：严重威胁国家安全",
            "苹果正洽谈采购长鑫 DRAM，但美国议员要求政府阻止这项供应安排。",
            "快科技",
        )
        priority_order = article_for(
            module,
            "长鑫存储 DRAM 订单排至 2027 年底，苹果等厂商优先拿货",
            "苹果、联想、戴尔和惠普完成产品测试并获得优先供货。",
            "IT之家",
        )

        left = module.article_title_led_event_identity(policy_block)
        right = module.article_title_led_event_identity(priority_order)

        self.assertEqual(module.identity_pair_decision(left, right), "conflict")
        self.assertEqual(len(module.cluster_articles([policy_block, priority_order])), 2)

    def test_background_legal_mentions_do_not_reclassify_podcast_or_roundup(self):
        module = load_module()
        podcast_title = "9to5Mac Overtime 073: iOS 27 Public Beta"
        podcast_summary = (
            "The podcast discusses iOS features and later mentions the DOJ lawsuit, settlement talks, "
            "OpenAI, and other unrelated weekly stories."
        )
        self.assertNotEqual(module.detect_event_kind(podcast_title, podcast_summary), "legal_antitrust")

        roundup_title = "iPhone 20 Rumors Point to These Seven Big Changes"
        roundup_summary = "A guide collects previously reported display, battery, chip, and camera rumors."
        tier, reason = module.classify_relevance_tier(roundup_title, roundup_summary, [], "MacRumors")
        self.assertEqual(tier, "weak", reason)

    def test_background_company_mentions_do_not_create_legal_identity_or_merge_weak_events(self):
        module = load_module()
        podcast = article_for(
            module,
            "9to5Mac Overtime 073: iOS 27 Public Beta",
            "The weekly podcast also mentions OpenAI, the DOJ case, and unrelated industry news.",
            "9to5Mac",
        )
        third_party_app = article_for(
            module,
            "OpenAI tweaks chat access in the ChatGPT app for Mac",
            "OpenAI changed its own Mac app; the article contains no new Apple platform action.",
            "9to5Mac",
        )
        packaging = article_for(
            module,
            "力成携手博通：斥资 27 亿元进军面板级封装",
            "文章主体是力成与博通的封装投资，背景段提到 OpenAI 和苹果等潜在客户。",
            "快科技",
        )

        identities = [
            module.article_title_led_event_identity(article)
            for article in (podcast, third_party_app, packaging)
        ]
        for left, right in itertools.combinations(identities, 2):
            self.assertNotEqual(module.identity_pair_decision(left, right), "match")

        events = module.cluster_articles([podcast, third_party_app, packaging])

        self.assertEqual(len(events), 3, event_partitions(events))

    def test_direct_apple_roundup_remains_discoverable_but_deferred(self):
        module = load_module()
        source = module.Source(
            name="MacRumors",
            default_tz="America/Los_Angeles",
            domains=("macrumors.com",),
        )
        candidate = module.Candidate(
            source="MacRumors",
            url="https://www.macrumors.com/2026/07/17/iphone-20-rumors-point-to-these-seven-big-changes/",
            title="iPhone 20 Rumors Point to These Seven Big Changes",
            discovered_from="https://www.macrumors.com/guide/",
        )

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        tier, reason = module.classify_relevance_tier(
            candidate.title,
            "A recap of previously reported display, battery, chip, and camera rumors.",
            [],
            candidate.source,
        )
        self.assertEqual(tier, "weak", reason)

    def test_non_apple_title_subject_cannot_be_promoted_by_apple_in_body_list(self):
        module = load_module()
        title = "三星盖乐世AI已备案：国行版三星手机AI服务合规落地"
        summary = (
            "网信部门公布七款完成备案的端侧生成式 AI 服务，包括 Apple 智能、华为小艺、"
            "小米澎湃 AI 和三星盖乐世 AI。报道重点是三星国行手机即将获得盖乐世 AI。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_regulatory_list_cannot_merge_with_direct_apple_clearance(self):
        module = load_module()
        apple_clearance = article_for(
            module,
            "苹果AI完成合规备案，国行 iPhone 将获得完整 Apple Intelligence",
            "网信部门公布 Apple 智能完成备案，国行 iPhone 将获得第一方 AI 服务。",
            "快科技",
        )
        samsung_clearance = article_for(
            module,
            "三星盖乐世AI已备案：国行版三星手机AI服务合规落地",
            (
                "网信部门公布七款端侧模型备案名单，其中顺带列出 Apple 智能；"
                "文章主体是三星盖乐世 AI 在国行 Galaxy 手机上的落地。"
            ),
            "快科技",
        )

        events = module.cluster_articles([apple_clearance, samsung_clearance])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertEqual(apple_clearance.relevance_tier, "strong")
        self.assertEqual(samsung_clearance.relevance_tier, "weak")

    def test_direct_builtin_service_feature_change_overrides_walkthrough_wording(self):
        module = load_module()
        title = "iOS 27 makes one of my favorite Apple Music features even better"
        summary = (
            "Apple changed the built-in Apple Music AutoMix feature in iOS 27. "
            "The update adds more varied, immersive transitions between songs than iOS 26."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "software_systems")

        carplay_title = "The best CarPlay upgrades to try in the iOS 27 public beta"
        carplay_summary = (
            "iOS 27 adds Siri AI, a Now Playing mini-player, new wallpapers, navigation accuracy, "
            "and dedicated video apps in CarPlay."
        )
        tier, reason = module.classify_relevance_tier(
            carplay_title, carplay_summary, [], "9to5Mac"
        )
        self.assertEqual(tier, "strong", reason)

    def test_service_value_analysis_is_reviewable_but_not_a_standalone_required_event(self):
        module = load_module()
        title = "Is Apple One worth it in summer 2026 after the latest price increases?"
        summary = (
            "The analysis calculates potential savings after Apple changed Apple Music and "
            "Apple One prices, but reports no separate Apple action."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_third_party_product_comparison_remains_weak(self):
        module = load_module()
        title = "Signal Ring gives blood pressure readings, better than an Apple Watch"
        summary = (
            "Signal Ring says its own smart ring measures systolic and diastolic blood pressure. "
            "Apple Watch is mentioned only as the competing product used for comparison."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_non_apple_policy_comparison_title_remains_weak(self):
        module = load_module()
        title = "Google is better than Apple at playing the AI regulations game"
        summary = (
            "The analysis compares Google's regulatory strategy with Apple's delayed Siri rollout. "
            "It reports no new Apple filing, product change, or platform action."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "The Verge")

        self.assertEqual(tier, "weak", reason)

    def test_third_party_mobile_creation_feature_remains_weak_across_sources(self):
        module = load_module()
        title = "AI-generated Roblox games are about to get much easier to make on iPhone"
        summary = (
            "Roblox is adding its own AI game creation tool to the Roblox mobile app. "
            "The feature runs on iPhone, iPad, and Android without a new Apple platform action."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "AppleInsider")

        self.assertEqual(tier, "weak", reason)

    def test_supplier_joint_venture_cannot_become_apple_broadcom_deal_from_background(self):
        module = load_module()
        title = "力成携手博通：斥资 27 亿元进军面板级封装"
        summary = (
            "力成与博通在新加坡设立合资公司，投入面板级封装。"
            "背景仅说明博通也与苹果、Google 和其他客户保持长期供货关系。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "weak", reason)

    def test_primary_apple_chip_supplier_capacity_action_remains_strong(self):
        module = load_module()
        title = "TSMC says it may build 12 Arizona chip plants in total"
        summary = (
            "Apple chipmaker TSMC announced another $100 billion investment in advanced chip and "
            "packaging plants; Apple is expected to use capacity from the facilities."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_distinct_apple_legal_actions_do_not_merge_through_generic_lawsuit_words(self):
        module = load_module()
        hide_email = article_for(
            module,
            "苹果隐藏电子邮件功能被曝漏洞未修复，用户提起集体诉讼",
            (
                "用户在加州联邦法院起诉苹果，指控 iCloud+ 的 Hide My Email 隐私保护"
                "存在未修复漏洞并涉嫌虚假广告、欺诈和违约。苹果曾称系统更新已经修复。"
            ),
            "IT之家",
        )
        openai = article_for(
            module,
            "邮件误发导致苹果与 OpenAI 谈判破裂，随后对簿公堂",
            (
                "苹果与 OpenAI 的分歧演变为公开法律诉讼。苹果指控 OpenAI 系统性挖角"
                "硬件人才并窃取未发布产品的商业秘密，随后向加州联邦法院正式起诉。"
            ),
            "cnBeta",
        )

        events = module.cluster_articles([hide_email, openai])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_distinct_apple_ai_actions_do_not_merge_through_generic_ai_context(self):
        module = load_module()
        baltra = article_for(
            module,
            "消息称苹果自研 AI 服务器 Baltra 芯片遇挑战，今年恐无缘亮相",
            (
                "苹果原计划在 2026 年推出 Baltra AI 服务器芯片，但芯片性能不足而延后。"
                "部分 Siri AI 负载因此转移到云端 GPU。"
            ),
            "IT之家",
        )
        prism = article_for(
            module,
            "古尔曼：苹果和 PrismML 在量化 AI 技术上合作可能性较低",
            (
                "PrismML 称苹果正在评估其 AI 模型量化技术，但古尔曼认为双方没有实质合作，"
                "收购或采用该技术的可能性较低。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([baltra, prism])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_hide_my_email_case_merges_across_event_kind_and_language(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Hide My Email class action lawsuit seeks payout without evidence of attacks",
                "A class action accuses Apple of selling privacy it could not provide because of an unresolved Hide My Email flaw.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple Sued Over Reported Hide My Email Flaw",
                "The proposed class action says Apple's Hide My Email feature could expose a user's real email address.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple accused of misleading users about Hide My Email privacy protections",
                "A California user filed a proposed class action over the same unresolved Hide My Email flaw.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果隐藏电子邮件功能被曝漏洞未修复，用户提起集体诉讼",
                "用户就 Hide My Email 隐私漏洞对苹果提起集体诉讼，称真实邮箱可能暴露。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual(len(events[0].articles), 4)

    def test_foldable_iphone_vapor_chamber_reports_merge_despite_extra_context(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Mass production of folding iPhone vapor cooling system has begun",
                "Apple increased vapor chamber orders for its foldable iPhone and a later anniversary model.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple Reportedly Ramps Up Vapor Chamber Orders for Foldable iPhone",
                "Apple asked suppliers for more vapor chamber cooling components for the foldable iPhone.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple increases vapor chamber orders ahead of foldable iPhone launch",
                "The larger component order is intended to improve thermal performance in Apple's foldable iPhone.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果折叠屏 iPhone 均热板散热系统传已开始量产",
                "苹果增加供应商均热板订单，首款折叠屏 iPhone 的散热模块开始量产。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual(len(events[0].articles), 4)

    def test_specific_base_iphone_delay_sources_merge_without_absorbing_broad_lineup(self):
        module = load_module()
        delay = article_for(
            module,
            "研究机构揭秘苹果推迟发布基础款 iPhone 18 原因：Pro 机型需求强劲",
            (
                "基础款 iPhone 18、iPhone Air 2 和 iPhone 18e 推迟到明年初；"
                "苹果把资源转向利润更高的 iPhone 18 Pro、Pro Max 和折叠机。"
            ),
            "cnBeta",
        )
        margin = article_for(
            module,
            "涨价也不愁卖！苹果打破多年发布惯例，重心全放在高利润机型",
            (
                "基础款 iPhone 18、Air 2 和 18e 放到明年初发布，苹果把资源倾斜给"
                "利润更高的 iPhone 18 Pro、Pro Max 和折叠机。"
            ),
            "快科技",
        )
        broad_lineup = article_for(
            module,
            "苹果明年要发 iPhone 20 等六款手机",
            (
                "苹果 2027 年将分两季推出六款 iPhone；基础款 iPhone 18 将推迟，"
                "高利润 Pro 系列先发。文章逐一汇总 iPhone Air 2、"
                "iPhone 18、iPhone 18e、周年版和折叠机的规格与时间表。"
            ),
            "IT之家",
        )

        events = module.cluster_articles([delay, margin, broad_lineup])

        self.assertEqual(len(events), 2, event_partitions(events))
        delay_event = next(event for event in events if delay in event.articles)
        self.assertEqual({article.source for article in delay_event.articles}, {"cnBeta", "快科技"})

    def test_content_form_is_an_authoritative_relevance_boundary(self):
        module = load_module()
        weak_cases = [
            (
                "Apple weekend deals: AirPods Pro 3, MacBook Pro up to $400 off, Series 11, chargers, bands, more",
                "A weekend shopping roundup lists retailer discounts on Apple hardware and accessories.",
                "deal",
            ),
            (
                "iPhone 18 Pro is just two months away, but you probably shouldn't wait for it",
                "The article recommends buying an iPhone 17 Pro now rather than waiting for the next model.",
                "buying_advice",
            ),
            (
                "Indie App Spotlight: 'Passable' makes it easy to share your contact through Apple Wallet",
                "A weekly showcase recommends a third-party app available from the App Store.",
                "third_party_spotlight",
            ),
            (
                "分析师：苹果 AI 策略‘保守’反而是优势，可降低资本压力并驱动硬件升级",
                "分析师评价苹果现有 AI 战略，但没有新的苹果决定、产品变化或评级动作。",
                "analysis",
            ),
            (
                "'AppleCare One' is Now Even More Valuable",
                "The article reassesses the plan after unrelated price changes but reports no new AppleCare action.",
                "analysis",
            ),
        ]

        for title, summary, expected_form in weak_cases:
            with self.subTest(title=title):
                identity = module.title_led_identity(title, summary)
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(identity.content_form, expected_form)
                self.assertEqual(tier, "weak", reason)

    def test_non_apple_benchmark_subject_is_not_promoted_by_apple_comparison(self):
        module = load_module()
        title = (
            "英伟达 N1X 首个 Cinebench 2026 跑分曝光：微软 Surface Ultra 工程样机现身，"
            "单核成绩接近苹果 M3 Max"
        )
        summary = "文章主体是英伟达和微软的工程样机，苹果 M3 Max 仅用于跑分比较。"

        identity = module.title_led_identity(title, summary)
        tier, reason = module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(identity.scope, "third-party-context")
        self.assertEqual(tier, "weak", reason)

    def test_event_summary_cannot_repromote_a_third_party_title_subject(self):
        module = load_module()
        article = article_for(
            module,
            (
                "英伟达 N1X 首个 Cinebench 2026 跑分曝光：微软 Surface Ultra 工程样机现身，"
                "单核成绩接近苹果 M3 Max"
            ),
            (
                "工程样机配备最高 128GB 统一内存。附带上下文提到 Apple 芯片、"
                "Mac 路线图和内存容量，但苹果产品仅用于比较。"
            ),
            "IT之家",
        )
        article.relevance_tier = "strong"
        article.relevance_reason = "simulated body-context promotion"

        event = module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)
        self.assertIn("third-party", event.relevance_reason)

    def test_third_party_driver_fix_with_direct_apple_hardware_interop_is_ecosystem(self):
        module = load_module()
        title = "70 个补丁修复一块屏：AMD 修好苹果 Studio Display 的 Linux 5K 显示异常"
        summary = (
            "AMDGPU 驱动补丁修正 Studio Display 双 DisplayPort 链路处理，"
            "合入 Linux 7.3 后可正常输出单一 5K 画面。"
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")

        self.assertEqual(tier, "ecosystem", reason)

    def test_icloud_price_language_normalizes_to_one_service_action(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple raises iCloud+ subscription prices in several countries",
                (
                    "Apple increased iCloud+ prices in eight markets. Those hikes came just days after Apple raised "
                    "prices for MacBooks, iPads, and other products in response to the memory shortage."
                ),
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple bumps up the cost of iCloud+ in 8 countries",
                (
                    "Apple has continued to put the prices up for its online services, with iCloud+ rising in cost "
                    "in a number of territories. Comparisons with previous pricing show it affects eight countries. "
                    "The price increases vary between territories, but fall in the range of 17% to 30%. "
                    "For example, the 50GB plan was 150 yen per month but is now 180 yen, up 20%."
                ),
                "AppleInsider",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]
        self.assertTrue(all("price-change" in identity.title_actions for identity in identities))
        self.assertTrue(all(article.event_kind == "service_content" for article in articles))
        self.assertEqual(module.identity_pair_decision(*identities), "match")
        self.assertEqual(len(module.cluster_articles(articles)), 1)

    def test_service_price_event_retains_regional_range_and_plan_examples(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple raises iCloud+ subscription prices in several countries",
                (
                    "Apple increased iCloud+ prices in eight markets. Those hikes came just days after Apple raised "
                    "prices for MacBooks, iPads, and other products in response to the memory shortage."
                ),
                "9to5Mac",
                facts=[
                    "Apple now lists Laos, Mauritius, and the Republic of Congo as regions billed in U.S. dollars with VAT.",
                ],
            ),
            article_for(
                module,
                "Apple bumps up the cost of iCloud+ in 8 countries",
                (
                    "Apple has continued to put the prices up for its online services, with iCloud+ rising in cost "
                    "in a number of territories. Comparisons with previous pricing show it affects eight countries. "
                    "The price increases vary between territories, but fall in the range of 17% to 30%. "
                    "For example, the 50GB plan was 150 yen per month but is now 180 yen, up 20%."
                ),
                "AppleInsider",
                facts=[
                    "The affected countries include Egypt, Indonesia, Japan, New Zealand, Nigeria, Philippines, Turkiye, and Vietnam; price increases range from 17% to 30%.",
                    "For example, the 50GB plan was 150 yen per month but is now 180 yen, up 20%.",
                    "Pricing in the United States and United Kingdom remains unchanged.",
                ],
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, event_partitions(events))
        event = events[0]

        self.assertTrue(
            any(fact.startswith("The affected countries include") and "17% to 30%" in fact for fact in event.key_facts),
            event.key_facts,
        )
        self.assertTrue(
            any(fact.startswith("For example, the 50GB plan") and "150 yen" in fact and "180 yen" in fact for fact in event.key_facts),
            event.key_facts,
        )

    def test_ios_public_beta_experience_does_not_merge_with_china_ai_filing(self):
        module = load_module()
        hands_on = article_for(
            module,
            "iOS 27 公测版上手：国行 AI 准备好了，但系统流畅更值得升级",
            (
                "实际体验 iOS 27 公测版的流畅度、液态玻璃和系统功能；"
                "文章同时提到 Apple Intelligence 已完成中国备案。"
            ),
            "爱范儿",
        )
        filing = article_for(
            module,
            "终于告别残血版 iPhone，国行版苹果 AI 降临",
            "Apple Intelligence 完成手机端侧生成式 AI 服务备案，国行 iPhone 等待正式上线。",
            "快科技",
        )

        hands_on_identity = module.article_title_led_event_identity(hands_on)
        filing_identity = module.article_title_led_event_identity(filing)
        events = module.cluster_articles([hands_on, filing])

        self.assertIn("ios", hands_on_identity.title_products)
        self.assertIn("apple-intelligence", filing_identity.title_products)
        self.assertEqual(module.identity_pair_decision(hands_on_identity, filing_identity), "conflict")
        self.assertEqual(hands_on.event_kind, "os_app")
        self.assertEqual(hands_on.relevance_tier, "strong")
        self.assertEqual(len(events), 2, event_partitions(events))

    def test_cluster_partition_is_stable_when_article_order_changes(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Sued Over Reported Hide My Email Flaw",
                "A lawsuit alleges that the Hide My Email privacy flaw can expose real addresses.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果隐藏电子邮件功能被曝漏洞未修复，用户提起集体诉讼",
                "用户针对同一 Hide My Email 隐私漏洞起诉苹果。",
                "IT之家",
            ),
            article_for(
                module,
                "邮件误发导致苹果与 OpenAI 谈判破裂，随后对簿公堂",
                "苹果与 OpenAI 因硬件合作和商业秘密争议进入诉讼。",
                "cnBeta",
            ),
        ]
        expected = None
        for permutation in itertools.permutations(articles):
            partitions = event_partitions(module.cluster_articles(list(permutation)))
            if expected is None:
                expected = partitions
            self.assertEqual(partitions, expected)

    def test_named_first_party_tool_pilot_merges_reporting_angles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Genius Bar AI tools spark concerns over employee monitoring & evaluation",
                (
                    "Apple is testing a new Genius Bar tool called Live Notes that transcribes and "
                    "summarizes customer conversations. Employees are concerned about evaluation use."
                ),
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple testing 'Live Notes' AI system to record Genius Bar sessions: report",
                "Apple is piloting Live Notes at retail locations to record and transcribe Genius Bar sessions.",
                "9to5Mac",
            ),
            article_for(
                module,
                "消息称苹果天才吧测试“Live Notes”系统，可记录直营店员工与顾客之间的对话",
                "苹果正在部分直营店测试名为 Live Notes 的 AI 系统，可转录并总结服务对话。",
                "IT之家",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]
        events = module.cluster_articles(articles)

        self.assertTrue(all("live-notes" in identity.named_subjects for identity in identities))
        self.assertTrue(all("pilot-testing" in identity.actions for identity in identities))
        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "9to5Mac", "IT之家"})

    def test_different_named_first_party_tool_pilots_remain_separate(self):
        module = load_module()
        live_notes = article_for(
            module,
            "Apple testing 'Live Notes' AI system at the Genius Bar",
            "Apple is piloting Live Notes to transcribe customer support sessions.",
            "9to5Mac",
        )
        queue_coach = article_for(
            module,
            "Apple testing 'Queue Coach' AI system at the Genius Bar",
            "Apple is piloting Queue Coach to predict appointment wait times.",
            "AppleInsider",
        )

        events = module.cluster_articles([live_notes, queue_coach])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_cancelled_hardware_program_merges_by_rare_project_anchors(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Mac Pro could have been far more powerful than the Mac Studio",
                "Apple developed M2 Extreme and M3 Extreme processors before cancelling the Mac Pro projects.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple Reportedly Worked on Two 'Extreme' Chips",
                "Apple developed M2 Extreme and M3 Extreme for the Mac Pro but decided not to release them.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple's scrapped Mac Pro plans reportedly included a new Intel model",
                "The cancelled J170 and J190 Mac Pro projects included Intel and M3 Ultra models plus M2 Extreme and M3 Extreme chips.",
                "9to5Mac",
            ),
            article_for(
                module,
                "消息称苹果砍掉 Mac Pro 前，曾秘密开发全新英特尔机型、M2 Extreme/M3 Extreme 芯片",
                "苹果取消了代号 J170 和 J190 的 Mac Pro 项目及 M2 Extreme、M3 Extreme 芯片。",
                "IT之家",
            ),
            article_for(
                module,
                "苹果曾计划为 Mac Pro 研发顶级性能芯片",
                "苹果曾为 Mac Pro 研发 M2 Extreme 和 M3 Extreme，但因成本和需求取消计划。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual(len(events[0].articles), 5)

    def test_rare_project_anchor_does_not_bridge_different_mac_roadmap_action(self):
        module = load_module()
        cancelled = article_for(
            module,
            "Apple cancelled M2 Extreme and M3 Extreme chips for Mac Pro",
            "The unreleased Mac Pro projects were abandoned because of cost and demand.",
            "MacRumors",
        )
        future = article_for(
            module,
            "M5 Ultra Mac Studio expected to launch this fall",
            "Apple is preparing a future Mac Studio update with an M5 Ultra chip.",
            "9to5Mac",
        )

        events = module.cluster_articles([cancelled, future])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_third_party_retailer_discount_stays_deferred_despite_chip_names(self):
        module = load_module()
        title = "B&H discounts M5 Pro & M5 Max MacBook Pro by up to $400"
        summary = (
            "B&H launched new markdowns on 14-inch and 16-inch MacBook Pro models, "
            "with savings of up to $400 off M5, M5 Pro, and M5 Max configurations."
        )
        article = article_for(module, title, summary, "AppleInsider")
        events = module.cluster_articles([article])

        identity = module.article_title_led_event_identity(article)
        self.assertEqual(identity.content_form, "deal")
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        self.assertEqual(events[0].relevance_tier, "weak", events[0].relevance_reason)

    def test_direct_apple_office_lease_candidate_is_discoverable_and_merges(self):
        module = load_module()
        source = next(item for item in module.build_sources(datetime.now(timezone.utc)) if item.name == "9to5Mac")
        candidate = module.Candidate(
            source="9to5Mac",
            url="https://9to5mac.com/2026/07/20/apple-leases-126000-square-foot-office-building-in-sunnyvale/",
            title="Apple leases 126,000-square-foot office building in Sunnyvale",
            summary="Apple is expanding its Sunnyvale footprint with a new office lease.",
            context="news aapl company",
        )
        articles = [
            article_for(
                module,
                candidate.title,
                "Apple leased a 125,800-square-foot Sunnyvale office and may later buy the property.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple adds another office to its Sunnyvale collection",
                "Apple leased the 125,800-square-foot building at 580 North Mary Avenue.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果在美国加州租赁约 11687 平方米办公楼",
                "苹果租下森尼韦尔 North Mary Avenue 580 号办公楼，未来可能买下。",
                "IT之家",
            ),
        ]

        self.assertTrue(module.is_relevant_candidate(candidate, source))
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "AppleInsider", "IT之家"})

    def test_summary_merge_key_cannot_merge_different_price_actions(self):
        module = load_module()
        plan_price = article_for(
            module,
            "'Apple One' Just Went Up in Price",
            "Apple raised the Family and Premier Apple One plans by $2 per month.",
            "MacRumors",
        )
        buyer_survey = article_for(
            module,
            "调查显示：苹果产品涨价致超九成用户调整购买行为",
            "A reader survey found that higher Apple hardware prices will slow upgrade cycles.",
            "IT之家",
        )

        events = module.cluster_articles([plan_price, buyer_survey])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_same_price_upgrade_behavior_survey_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Higher Apple prices look set to slow upgrade cycles",
                "A reader survey found only 9% would leave purchase behavior unchanged and more than one third would upgrade less often.",
                "9to5Mac",
            ),
            article_for(
                module,
                "调查显示：苹果产品涨价致超九成用户调整购买行为，超 1/3 将降低升级频率",
                "同一读者调查显示超过 90% 会改变购买方式，超过三分之一会延长换机周期。",
                "IT之家",
            ),
        ]
        for article in articles:
            article.relevance_tier = "strong"
            article.relevance_reason = "direct Apple buyer survey"

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_reader_upgrade_cycle_poll_stays_weak_even_with_analyst_background(self):
        module = load_module()
        title = "Higher Apple prices look set to slow upgrade cycles"
        summary = (
            "A 9to5Mac reader survey found only 9% would leave purchase behavior unchanged and "
            "more than one third would upgrade less often. A later paragraph cites an analyst "
            "report about supply-chain pricing through 2028."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)
        self.assertFalse(module.is_apple_analyst_rating_target_story(title, summary))

        chinese_title = "调查显示：苹果产品涨价致超九成用户调整购买行为，超 1/3 将降低升级频率"
        chinese_summary = (
            "一项针对数千名 9to5Mac 读者的调查显示，超过 90% 会调整购买方式，"
            "其中 38% 会降低升级频率；正文随后引用分析师对供应链价格的看法。"
        )
        chinese_tier, chinese_reason = module.classify_relevance_tier(
            chinese_title, chinese_summary, [], "IT之家"
        )
        self.assertEqual(chinese_tier, "weak", chinese_reason)

    def test_same_spotlight_index_preparation_action_merges_across_headline_angles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 26.6 includes key feature that prepares your iPhone for iOS 27",
                "Apple has debuted the RC for iOS 26.6 and confirmed one important preparation for the next major release. "
                + "Background about the beta cycle and release timing keeps the named component outside the short lead window. " * 4,
                "9to5Mac",
                facts=["Apple will start Spotlight indexing in iOS 26.6 so that the iPhone is ready for iOS 27."],
            ),
            article_for(
                module,
                "iOS 26.6: New features, release date, more",
                "iOS 26.6 is coming soon after several developer and public betas. "
                + "Background about availability and release timing keeps the named component outside the short lead window. " * 4,
                "9to5Mac",
                facts=["Apple says iOS 26.6 optimizes the Spotlight index to prepare for iOS 27."],
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual(events[0].merge_warnings, [])
        self.assertTrue(
            all(
                "spotlight-index-preparation" in module.article_title_led_event_identity(article).components
                for article in articles
            )
        )

    def test_third_party_power_bank_cannot_join_iphone_dual_battery_rumor(self):
        module = load_module()
        rumor = article_for(
            module,
            "iOS 27 Code References iPhone With Two Batteries",
            "Battery Health strings refer to multiple internal iPhone batteries and one failing cell.",
            "MacRumors",
        )
        accessory = article_for(
            module,
            "RORRY Flow power bank: essential travel gear for Apple fans",
            "The third-party 10,000mAh power bank charges an iPhone and Apple Watch while traveling.",
            "9to5Mac",
        )

        events = module.cluster_articles([rumor, accessory])

        self.assertEqual(accessory.relevance_tier, "weak", accessory.relevance_reason)
        self.assertEqual(len(events), 2, event_partitions(events))

    def test_dual_battery_code_report_merges_with_evidence_caveat_followup(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 Code References iPhone With Two Batteries",
                "Battery Health strings refer to multiple internal iPhone batteries and one failing cell.",
                "MacRumors",
            ),
            article_for(
                module,
                "Plurality in iOS 27 beta code may be red herring, not iPhone Fold hints",
                "The same battery health strings refer to multiple iPhone batteries, but the wording may not prove a foldable model.",
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_clicklock_family_merges_across_quoted_and_suffixed_names(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "'ClickLock' Malware Coerces Mac Users Into Giving Up Passwords",
                "Group-IB calls the macOS threat ClickLock Stealer.",
                "MacRumors",
            ),
            article_for(
                module,
                "ClickLock malware makes Macs unusable until victims surrender passwords",
                "The ClickLock Stealer campaign uses fake prompts on macOS.",
                "AppleInsider",
            ),
            article_for(
                module,
                "新型勒索木马 ClickLock 曝光，瞄准苹果 macOS 下手",
                "Group-IB 披露 ClickLock Stealer 窃取密码和浏览器数据。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_named_first_party_service_update_merges_across_event_kinds(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Sports App Updated With Additional Soccer Leagues Following 2026 FIFA World Cup",
                "Apple Sports 4.2 added soccer leagues and formations.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple's Sports app expands soccer features, here's what's new",
                "Apple Sports version 4.2 added the same leagues and formation views.",
                "9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertTrue(all(article.event_kind == "service_content" for article in articles))

    def test_body_source_handle_does_not_split_same_ipad_mini_report(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "New iPad Mini With OLED Display Will Also Have 'Major' Chip Upgrade",
                "Bloomberg reports an A19 Pro or A20 Pro processor and OLED display for the October model.",
                "MacRumors",
            ),
            article_for(
                module,
                "古尔曼：新款 OLED 屏 iPad mini 处理器将迎来重大升级",
                "新款 iPad mini 据称采用 A19 Pro 或 A20 Pro 和 OLED 屏幕。",
                "IT之家",
                facts=["消息人士 yeux1122 此前还讨论了 8.4 英寸 OLED 面板。"],
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]
        events = module.cluster_articles(articles)

        self.assertTrue(all("yeux1122" not in identity.named_subjects for identity in identities))
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_same_apple_tv_title_merges_despite_background_work_names(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple unveils new film from 'Best Picture' Oscar winner",
                "CODA director Sian Heder's follow-up Being Heumann will stream on Apple TV on November 13.",
                "9to5Mac",
            ),
            article_for(
                module,
                "'CODA' director returns to Apple TV with movie about disability activist Judy Heumann",
                "Sian Heder directs Being Heumann for Apple TV, starring Ruth Madeley.",
                "AppleInsider",
                facts=["The article also mentions Doctor Who and Years and Years as background credits."],
            ),
            article_for(
                module,
                "《健听女孩》导演海德执导，《成为休曼》传记片 11 月上架 Apple TV",
                "苹果 Apple TV 将推出《成为休曼》（Being Heuman），由 Sian Heder 执导，11 月 13 日上线。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_os_release_wave_normalizes_dot_zero_and_keeps_feature_story_separate(self):
        module = load_module()
        release_articles = [
            article_for(
                module,
                "Apple releases iOS 27 beta 4 to developers",
                "Apple released iOS 27 developer beta 4 today.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 iOS 27.0 开发者预览版 Beta 4 发布",
                "苹果向开发者推送 iOS 27.0 Beta 4。",
                "IT之家",
            ),
        ]
        feature = article_for(
            module,
            "iOS 27 beta 4 adds Automatic Downloads to the Apple TV app",
            "The built-in TV app now downloads the next two episodes.",
            "9to5Mac",
        )

        events = module.cluster_articles([*release_articles, feature])

        self.assertEqual(len(events), 2, event_partitions(events))
        release_event = next(event for event in events if release_articles[0] in event.articles)
        self.assertEqual(
            {article.title for article in release_event.articles},
            {article.title for article in release_articles},
        )

    def test_rc_release_wave_merges_same_version_across_platform_groups(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Seeds iOS 26.6 and iPadOS 26.6 Release Candidates",
                "Apple released the 26.6 RC builds to developers.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple releases iPadOS 26.6 RC plus watchOS 26.6 and more",
                "Apple released iPadOS, watchOS, tvOS, and visionOS 26.6 RC builds.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果发布 watchOS 26.6、visionOS 26.6、tvOS 26.6 RC 候选版本",
                "苹果向开发者推送同一轮 26.6 RC。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_direct_first_party_feature_and_store_metrics_stay_strong(self):
        module = load_module()
        samples = [
            (
                "Siri AI is hiding a more concise set of Writing Tools for Mac",
                "Apple is testing a new way to access its built-in Writing Tools on macOS 27.",
                "AppleInsider",
            ),
            (
                "App Store added nearly as many new apps in H1 2026 as in all of 2025",
                "Sensor Tower reports 560,000 new App Store apps, and Apple provided a review-time response.",
                "9to5Mac",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "strong", reason)

    def test_tutorial_podcast_old_rumor_and_former_executive_commentary_stay_weak(self):
        module = load_module()
        samples = [
            (
                "Mac beach balls and unresponsive trackpad? Here's the fix",
                "A troubleshooting guide suggests restarting WindowServer on macOS 26.",
                "9to5Mac",
            ),
            (
                "Plume CPO on fixing ISP-provided routers, public betas, & more",
                "A Smart Home Insider podcast episode discusses routers and Apple beta software.",
                "AppleInsider",
            ),
            (
                "Apple Watch Series 12 Coming in September With These New Features",
                "A roundup recaps previously reported rumors and adds no new reporting.",
                "MacRumors",
            ),
            (
                "'Apple Store father' Ron Johnson says Steve Jobs knew how to delegate",
                "The former Apple retail executive promotes a memoir and recalls historical conversations; Apple took no new action.",
                "IT之家",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_real_clicklock_pages_merge_despite_clickfix_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "'ClickLock' Malware Coerces Mac Users Into Giving Up Passwords",
                "Security firm Group-IB identified ClickLock Stealer, which uses a fake ClickFix Cloudflare page before pressuring macOS users for passwords.",
                "MacRumors",
            ),
            article_for(
                module,
                "ClickLock malware makes Macs unusable until victims surrender their passwords",
                "ClickLock Stealer builds on ClickFix and fake CAPTCHA prompts to steal macOS passwords and browser data.",
                "AppleInsider",
            ),
            article_for(
                module,
                "新型勒索木马 ClickLock 曝光，瞄准苹果 macOS 下手",
                "Group-IB 披露 ClickLock Stealer 伪装成验证页面，窃取系统密码和浏览器数据。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_real_apple_books_platform_trust_pages_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "AI fakes a growing problem on Apple Books and Amazon",
                "Joanna Stern found 10 AI-generated fake versions of I Am Not a Robot on Apple Books; removed copies were quickly replaced.",
                "9to5Mac",
            ),
            article_for(
                module,
                "AI 生成的盗版书泛滥，苹果图书和亚马逊上出现大量假冒作品",
                "记者在 Apple Books 发现 10 本 AI 生成的仿冒书，下架后又有新版本出现。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_real_being_heumann_pages_ignore_prior_work_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple unveils new film from 'Best Picture' Oscar winner",
                "Apple's CODA director follow-up Being Heumann is dated for Apple TV on November 13.",
                "9to5Mac",
            ),
            article_for(
                module,
                "'CODA' director returns to Apple TV with movie about disability activist Judy Heumann",
                "Apple TV is to screen Sian Heder's follow-up Being Heumann; Doctor Who is mentioned only as cast background.",
                "AppleInsider",
            ),
            article_for(
                module,
                "《健听女孩》导演海德执导，《成为休曼》传记片 11 月上架 Apple TV",
                "苹果 Apple TV 将推出《成为休曼》（Being Heuman），11 月 13 日上线。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_real_third_party_power_bank_podcast_and_former_executive_quote_stay_weak(self):
        module = load_module()
        samples = [
            (
                "RORRY Flow power bank: essential travel gear for Apple fans",
                "The third-party power bank has a wall plug, USB-C cable, and magnetic Apple Watch charger.",
                "9to5Mac",
            ),
            (
                "Plume CPO on fixing ISP-provided routers, public betas, & more",
                "On this week's episode of the Smart Home Insider podcast, Plume discusses OEM routers after a short Apple beta news recap.",
                "AppleInsider",
            ),
            (
                "“Apple Store 之父”罗恩 · 约翰逊：乔布斯之所以出色，是因为他懂得放权",
                "苹果前高管罗恩·约翰逊为即将出版的新书接受采访，回忆乔布斯重视细节但更善于授权，并介绍自己参与创建 Apple Store 的历史。",
                "IT之家",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)

    def test_release_wave_identity_uses_explicit_title_when_facets_are_sparse(self):
        module = load_module()
        release_titles = [
            "iOS 27 beta 4 now available as Apple tests major Siri AI upgrade",
            "苹果 iOS / iPadOS 27.0 开发者预览版 Beta 4 发布：增强 Siri AI",
            "Apple starts round four of its iOS 27, macOS 27 developer betas",
        ]
        releases = [
            article_for(module, title, "Apple released the fourth developer beta in the same OS 27 wave.", source)
            for title, source in zip(release_titles, ("9to5Mac", "IT之家", "AppleInsider"))
        ]
        feature = article_for(
            module,
            "iOS 27 beta 4 adds a useful Apple TV app feature",
            "The built-in Apple TV app can automatically download the next episodes.",
            "9to5Mac",
        )
        roundup = article_for(
            module,
            "Here’s what’s new with iOS 27 beta 4",
            "This feature review covers Siri AI changes, Apple TV downloads, and other discoveries after beta 4 shipped.",
            "9to5Mac",
        )
        writing_tools = article_for(
            module,
            "Siri AI is hiding a more concise set of Writing Tools for Mac",
            "Apple is testing a new way to access built-in Writing Tools on macOS 27; beta 4 is background release context.",
            "AppleInsider",
        )

        identities = [module.article_title_led_event_identity(article) for article in releases]
        events = module.cluster_articles([*releases, feature, roundup, writing_tools])

        self.assertTrue(all("os-wave:27:beta-4" in identity.components for identity in identities), identities)
        release_event = next(event for event in events if releases[0] in event.articles)
        self.assertEqual({article.title for article in release_event.articles}, set(release_titles))
        self.assertNotIn(feature, release_event.articles)
        self.assertNotIn(roundup, release_event.articles)
        self.assertNotIn(writing_tools, release_event.articles)

    def test_chinese_a20_pro_title_without_spacing_merges_with_english_report(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro's new A20 chip rumored to bring two major upgrades",
                "The A20 Pro is expected to use TSMC's 2nm process and WMCM packaging.",
                "9to5Mac",
            ),
            article_for(
                module,
                "iPhone 18 Pro首发！苹果A20 Pro两大升级：首次2nm制程、WMCM封装",
                "A20 Pro 将首次采用 2nm 制程和晶圆级多芯片模块封装。",
                "快科技",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]
        events = module.cluster_articles(articles)

        self.assertTrue(all("a20-pro" in identity.named_subjects for identity in identities), identities)
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_multi_vendor_report_with_concrete_apple_metrics_merges_as_source(self):
        module = load_module()
        facts = [
            "苹果在 2026 年第二季度中国市场出货量同比增长 23%，市场份额由 15% 升至 18%。"
        ]
        articles = [
            article_for(
                module,
                "Counterpoint：2026 年第二季度中国智能手机出货量同比下降 2%，华为、苹果逆势增长",
                "Counterpoint 报告中国智能手机市场整体下降，苹果出货量逆势增长。",
                "IT之家",
                facts=facts,
            ),
            article_for(
                module,
                "中国智能手机市场二季度出货量下降2% 华为逆势增长",
                "Counterpoint Research 的同一份 2026 年第二季度中国市场报告也显示苹果逆势增长。",
                "cnBeta",
                facts=facts,
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles), [(a.title, a.relevance_reason) for a in articles])
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_apple_music_system_features_do_not_merge_with_automaker_integration(self):
        module = load_module()
        system_features = article_for(
            module,
            "Apple Music in iOS 27: Five new features coming to your iPhone",
            "Apple Music gains landscape layouts, AutoMix improvements, and redesigned artist pages in iOS 27.",
            "9to5Mac",
        )
        automaker = article_for(
            module,
            "Volvo adds Apple Music to more than 2 million cars, with up to three months free",
            "Volvo is adding native Apple Music to 11 vehicle models and offers eligible customers up to three months free.",
            "9to5Mac",
        )

        events = module.cluster_articles([system_features, automaker])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_real_power_bank_copy_stays_weak_without_explicit_third_party_word(self):
        module = load_module()
        title = "RORRY Flow power bank: essential travel gear for Apple fans"
        summary = (
            "The RORRY Flow power bank has a built-in USB-C cable, wall plug, and magnetic Apple Watch charger. "
            "It charges an iPhone, iPad, Apple Watch, or MacBook Air while traveling."
        )

        tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)

    def test_real_sunnyvale_office_sources_merge_by_place_and_transaction(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple adds another office to its Sunnyvale collection",
                "Apple is leasing a 125,800-square-foot building in Sunnyvale at 580 North Mary Avenue.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果在美国加州租赁约 11687 平方米办公楼，未来不排除直接买下可能",
                "苹果租赁位于美国加州森尼韦尔（Sunnyvale）的办公地点，地址为 North Mary Avenue 580 号。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_platform_specific_os_beta_release_pages_merge_into_one_wave(self):
        module = load_module()
        releases = [
            article_for(
                module,
                "Apple Seeds tvOS 27 Beta 4 to Developers",
                "Apple released tvOS 27 beta 4 in the fourth developer beta wave.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple Seeds Fourth iOS 27 and iPadOS 27 Betas to Developers",
                "Apple released iOS 27 and iPadOS 27 beta 4 to developers.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple Releases macOS Golden Gate Beta 4",
                "Apple provided developers with the fourth beta of macOS Golden Gate.",
                "MacRumors",
            ),
            article_for(
                module,
                "macOS 27 Golden Gate beta 4 now available to developers",
                "Apple released macOS 27 Golden Gate beta 4 in the same developer wave.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Fourth iOS 27 and macOS 27 developer betas released",
                "Apple released the fourth developer beta wave across iOS 27 and macOS 27.",
                "cnBeta",
            ),
            article_for(
                module,
                "第四个 iOS 27 和 macOS 27 开发者测试版发布",
                "苹果面向开发者推出 iOS 27、macOS 27 和其他平台的第四轮测试版。",
                "cnBeta",
            ),
        ]
        feature_roundup = article_for(
            module,
            "苹果 iOS 27 Beta 4 更新汇总：国行 Siri AI 暂未上线",
            "文章汇总 Siri AI、相机和通知中心等具体变化。",
            "IT之家",
        )

        events = module.cluster_articles([*releases, feature_roundup])

        self.assertEqual(len(events), 2, event_partitions(events))
        release_partition = frozenset(article.title for article in releases)
        self.assertIn(release_partition, event_partitions(events))
        self.assertIn(frozenset({feature_roundup.title}), event_partitions(events))
        release_event = next(
            event for event in events if frozenset(article.title for article in event.articles) == release_partition
        )
        self.assertEqual(release_event.event_kind, "os_app")
        self.assertEqual(release_event.category, "software_systems")
        self.assertEqual(release_event.merge_warnings, [])

    def test_everything_new_roundup_does_not_absorb_specific_beta_feature(self):
        module = load_module()
        roundup = article_for(
            module,
            "Everything New in iOS 27 Beta 4",
            "A roundup of Siri, camera, Messages, and Apple TV changes discovered in beta 4.",
            "MacRumors",
        )
        specific_feature = article_for(
            module,
            "iOS 27 beta 4 adds a useful Apple TV app feature, here's how it works",
            "The Apple TV app can automatically download the next two episodes and remove watched downloads.",
            "9to5Mac",
        )

        events = module.cluster_articles([roundup, specific_feature])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertNotIn("apple-tv", module.article_title_led_event_identity(roundup).products)

    def test_os_roundup_does_not_absorb_specific_hardware_clue(self):
        module = load_module()
        roundup = article_for(
            module,
            "Here’s what’s new with iOS 27 beta 4",
            "The roundup includes Siri changes and a code reference to a future iPhone with two batteries.",
            "9to5Mac",
        )
        hardware_clue = article_for(
            module,
            "iOS 27 beta 4 mentions new iPhone model with multi-battery feature",
            "Code references a future iPhone with multiple internal batteries.",
            "9to5Mac",
        )

        events = module.cluster_articles([roundup, hardware_clue])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertNotIn("dual-battery", module.article_title_led_event_identity(roundup).components)

    def test_release_title_with_trailing_whats_new_is_not_a_weak_roundup(self):
        module = load_module()
        title = "macOS 27 Golden Gate beta 4 now available to developers, here’s what’s new"
        summary = "Apple released macOS 27 beta 4 to developers and detailed the latest fixes."

        article = article_for(module, title, summary, "9to5Mac")

        self.assertEqual(module.article_title_led_event_identity(article).content_form, "news")
        self.assertEqual(article.relevance_tier, "strong")

    def test_writing_tools_reports_merge_across_different_title_wording(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Siri AI is hiding a more concise set of Writing Tools for Mac",
                "macOS 27 is testing a compact Write with Siri menu for selected text.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果 macOS 27 隐藏新特性：调用 Siri AI 内容创作",
                "macOS 27 正在测试隐藏的轻量版 Siri AI 写作工具，可对选中文本进行重写。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_os_major_dot_zero_normalizes_to_same_release_train(self):
        module = load_module()
        left = module.os_release_facets_from_text("苹果 watchOS 27.0 开发者预览版 Beta 4 发布")
        right = module.os_release_facets_from_text("Apple releases watchOS 27 beta 4")

        self.assertEqual(
            module.os_release_version_facets(left),
            module.os_release_version_facets(right),
        )

    def test_same_platform_and_beta_number_do_not_bridge_different_os_versions(self):
        module = load_module()
        ios_26 = article_for(
            module,
            "Apple releases iOS 26 beta 4",
            "Apple released the fourth beta of iOS 26.",
            "MacRumors",
        )
        ios_27 = article_for(
            module,
            "Apple releases iOS 27 beta 4",
            "Apple released the fourth beta of iOS 27.",
            "9to5Mac",
        )

        events = module.cluster_articles([ios_26, ios_27])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_direct_apple_customer_loyalty_metric_stays_strong(self):
        module = load_module()
        article = article_for(
            module,
            "苹果用户忠诚度历史新高：87% iPhone 用户不愿换阵营",
            "CIRP 数据显示 iPhone 用户忠诚度由一年前的 84% 升至 87%，Android 转入用户占比降至 12%。",
            "快科技",
        )

        self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)
        self.assertEqual(article.event_kind, "hardware_market")
        self.assertIn("customer-loyalty", module.article_title_led_event_identity(article).components)

    def test_office_lease_event_remains_in_hardware_category_after_rebuild(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple adds another office to its Sunnyvale collection",
                "Apple is leasing a 125,800-square-foot office building in Sunnyvale.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple leases 126,000-square-foot office building in Sunnyvale",
                "Apple signed a lease for a new Sunnyvale office and may later buy it.",
                "9to5Mac",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual(
            module.choose_category(
                "Apple adds another office to its Sunnyvale collection",
                "Apple is expanding its presence in Sunnyvale once again by leasing a 125,800-square-foot building.",
            ),
            "hardware_products",
        )

    def test_speculative_omission_from_existing_lawsuit_is_not_new_legal_action(self):
        module = load_module()
        article = article_for(
            module,
            "Apple Likely Left Jony Ive Out of Its OpenAI Lawsuit on Purpose",
            "Bloomberg's Mark Gurman says Apple's decision not to name its former design chief in the existing trade-secret complaint was likely deliberate, and reports no new filing, ruling, response, subpoena, or other legal action.",
            "MacRumors",
        )
        chinese = article_for(
            module,
            "苹果 41 页指控 OpenAI 偷师：古尔曼剖析未点名前 Apple 设计师伊夫原因",
            "报道解释苹果为何没有在现有诉状中点名伊夫，没有披露新的提交、裁定、回应或传唤。",
            "IT之家",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        self.assertEqual(chinese.relevance_tier, "weak", chinese.relevance_reason)

    def test_china_siri_unavailability_roundup_merges_with_direct_regional_report(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 iOS 27 Beta 4 更新汇总：国行 Siri AI 暂未上线",
                "苹果 iOS 27 Beta 4 已发布，但中国大陆版 iPhone 仍未开放 Siri AI。",
                "IT之家",
            ),
            article_for(
                module,
                "苹果 iOS 27 Beta 4 发布：国行 iPhone 期待的 Siri AI 继续缺席",
                "Apple 智能已完成中国备案，但 Siri AI 在国行 iPhone 上仍未上线。",
                "快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertTrue(all(article.event_kind == "regional_regulation" for article in articles))
        self.assertTrue(
            all(
                "apple-intelligence-china-regulatory-rollout" in module.article_primary_facets(article)
                for article in articles
            )
        )
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_detail_declared_release_candidate_overrides_stale_numbered_beta_title(self):
        module = load_module()
        stale_title = article_for(
            module,
            "Sixth iOS 26.6, macOS 26.6 developer betas surface for testing",
            "The RC developer betas landed after the fifth builds released one week earlier.",
            "AppleInsider",
            facts=["The release candidates are the final builds unless additional bugs are found."],
        )
        current_title = article_for(
            module,
            "Apple releases iOS 26.6 and macOS 26.6 release candidates",
            "Apple released the iOS 26.6 and macOS 26.6 RC builds to developers.",
            "9to5Mac",
        )

        events = module.cluster_articles([stale_title, current_title])

        self.assertIn("os-release-rc", module.article_primary_facets(stale_title))
        self.assertNotIn("os-release-beta-6", module.article_primary_facets(stale_title))
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_writing_tools_sources_merge_without_watchos_feature_article(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Siri AI is hiding a more concise set of Writing Tools for Mac",
                "Apple is testing a compact Writing Tools menu for selected text in macOS 27.",
                "AppleInsider",
            ),
            article_for(
                module,
                "苹果 macOS 27 隐藏新特性：调用 Siri AI 内容创作",
                "macOS 27 正在测试隐藏的 Siri AI 写作工具和精简菜单。",
                "IT之家",
            ),
            article_for(
                module,
                "苹果 watchOS 27 Beta 4 发布：引入 Siri AI，新增一体化查找应用",
                "watchOS 27 Beta 4 新增 Siri AI、查找 App 和多项性能优化。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(
            {articles[0].title, articles[1].title},
            [{article.title for article in event.articles} for event in events],
        )


if __name__ == "__main__":
    unittest.main()
