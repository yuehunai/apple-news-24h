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
    def test_current_single_subject_report_is_not_downgraded_by_what_to_expect_title(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Watch redesign is coming, but not for years",
                "Bloomberg reports Apple is late-stage testing Series 12 and Ultra 4 for September, with no major design change this year.",
                "AppleInsider",
            ),
            article_for(
                module,
                "What to Expect From Apple Watch Series 12 and Apple Watch Ultra 4",
                "Bloomberg's Mark Gurman today outlined that three Apple Watch models are in late-stage testing for September and no new SE is planned.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple Watch Series 12 and Ultra 4: What to expect",
                "According to Gurman, three next-generation Apple Watch models are in late-stage testing for September, while Apple Watch SE will not be updated.",
                "9to5Mac",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "MacRumors", "9to5Mac"})

    def test_direct_apple_smart_glasses_reports_share_one_hardware_event(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple's AI glasses to be unveiled at WWDC27",
                "Bloomberg reports Apple plans to reveal its first smart glasses at WWDC 2027 and ship them by year-end, with privacy-focused hardware and software.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Planning to Unveil Privacy-Focused Smart Glasses at WWDC 2027",
                "Apple is prototyping privacy features for its smart glasses and plans to reveal them at WWDC 2027 before a late-2027 launch.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple is banking on privacy to set its smart glasses apart",
                "Mark Gurman reports Apple is planning to reveal its first smart glasses at WWDC next June and launch them by the end of 2027.",
                "The Verge",
            ),
            article_for(
                module,
                "Public distrust in smart glasses will be a challenge for Apple Glass",
                "Apple will introduce its first smart glasses at WWDC in 2027 and is testing camera-free prototypes and privacy protections.",
                "AppleInsider",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "MacRumors", "The Verge", "AppleInsider"})

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

    def test_subject_first_third_party_titles_stay_weak(self):
        module = load_module()
        samples = [
            (
                "As Garmin Cirqa launches, should Apple make a fitness band or ring?",
                "A reader poll compares Garmin's new wearable with possible future Apple products.",
                "9to5Mac",
            ),
            (
                "漫步者 S1000MKIII 音箱发布：支持苹果 AirPlay 2",
                "漫步者发布第三方桌面音箱，并把 AirPlay 2 兼容性列为连接功能之一。",
                "IT之家",
            ),
            (
                "Samsung's new foldable is wider than Apple's anniversary iPhone",
                "Samsung announced a Galaxy foldable and compares its dimensions with a rumored iPhone.",
                "The Verge",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                identity = module.title_led_identity(title, summary)
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(identity.scope, "third-party-context")
                self.assertEqual(tier, "weak", reason)

    def test_bridge_article_joins_best_matching_first_party_program_event(self):
        module = load_module()
        restricted = article_for(
            module,
            "iOS 27 adds restricted mode for financed iPhones with unpaid balances",
            "Apple limits an overdue financed device to ten system apps and blocks erasure for resale.",
            "9to5Mac",
        )
        upgrades = [
            article_for(
                module,
                "'Apple Upgrade' Program Reportedly Launching Next Week",
                "Apple will launch Apple Upgrade as a device-leasing program for iPhone, iPad, Mac, and Apple Watch.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple debuting new Apple Upgrade leasing program next week, per report",
                "The Apple Upgrade program lets customers lease several first-party devices and upgrade later.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Upgrades will let users lease iPhones and Macs with Klarna",
                "Apple's own Upgrade program uses Klarna financing for monthly device leases.",
                "AppleInsider",
            ),
        ]
        bridge = article_for(
            module,
            "苹果有望下周美国推出月租 iPhone 17 等，iOS 27 显示欠款后可用 10 款白名单 App",
            (
                "苹果将推出 Apple Upgrade 设备租赁计划，覆盖 iPhone、iPad、Mac 和 Apple Watch。"
                "同一报道还披露 iOS 27 的欠款设备受限模式。"
            ),
            "IT之家",
        )
        localized_restricted = article_for(
            module,
            "苹果月租设备欠费后将停用，并防止抹除转卖",
            "iOS 27 代码显示，Apple 会限制欠费租赁设备，仅保留系统白名单应用。",
            "快科技",
        )

        self.assertEqual(upgrades[-1].relevance_tier, "strong", upgrades[-1].relevance_reason)
        bridge_identity = module.article_title_led_event_identity(bridge)
        self.assertIn("apple-device-leasing-program", bridge_identity.title_components)
        self.assertIn("financed-device-restriction", bridge_identity.title_components)
        events = module.cluster_articles([restricted, *upgrades, bridge, localized_restricted])
        upgrade_event = next(event for event in events if upgrades[0] in event.articles)
        restricted_event = next(event for event in events if restricted in event.articles)

        self.assertEqual(
            {article.title for article in [*upgrades, bridge]},
            {article.title for article in upgrade_event.articles},
            event_partitions(events),
        )
        self.assertNotIn(restricted, upgrade_event.articles)
        self.assertEqual(
            {restricted.title, localized_restricted.title},
            {article.title for article in restricted_event.articles},
            event_partitions(events),
        )

    def test_compound_leasing_and_restriction_article_contributes_to_both_events(self):
        module = load_module()
        title = "苹果有望下周美国推出月租 iPhone 17 等，iOS 27 显示欠款后可用 10 款白名单 App"
        summary = (
            "Apple Upgrade 计划覆盖 iPhone、iPad、Mac 和 Apple Watch，租期为 24 或 36 个月。"
            "iOS 27 代码还显示，欠款租赁设备会进入受限模式，只保留 10 款白名单 App 并防止抹除转卖。"
        )
        facts = [
            "Apple Upgrade 由 Klarna 提供融资，支持提前升级或买断。",
            "欠款设备只保留 10 款系统 App，并启用 Partner Finance Lock。",
        ]

        variants = module.compound_article_variants(title, summary, facts)

        self.assertEqual(len(variants), 2, variants)
        identities = [module.title_led_identity(item_title, item_summary) for item_title, item_summary, _ in variants]
        self.assertEqual(
            {"apple-device-leasing-program", "financed-device-restriction"},
            {
                component
                for identity in identities
                for component in identity.title_components
                if component in {"apple-device-leasing-program", "financed-device-restriction"}
            },
        )
        self.assertTrue(all(item_facts for _, _, item_facts in variants))

        localized_variants = module.compound_article_variants(
            "苹果将在美国推月租 iPhone 17 等业务：欠费停用，防止拆零件等行为",
            summary,
            facts,
        )
        self.assertEqual(len(localized_variants), 2, localized_variants)
        self.assertTrue(
            all(
                module.classify_relevance_tier(item_title, item_summary, item_facts, "快科技")[0]
                == "strong"
                for item_title, item_summary, item_facts in localized_variants
            )
        )

    def test_first_party_app_updates_merge_by_named_product_and_stay_software(self):
        module = load_module()
        testflight = [
            article_for(
                module,
                "Apple just improved TestFlight for users with a lot of beta apps",
                "Apple updated TestFlight with search and filtering for beta apps.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Updates TestFlight With Search and Filtering",
                "The same TestFlight release adds search and filtering for testers.",
                "MacRumors",
            ),
        ]
        invites = [
            article_for(
                module,
                "Apple Invites app updated with two new invitation features",
                "Apple Invites now supports emoji replies and celebration effects.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Invites App Updated With Two New Features",
                "The Apple Invites update adds the same host and guest features.",
                "MacRumors",
            ),
        ]

        events = module.cluster_articles([*testflight, *invites])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in testflight), event_partitions(events))
        self.assertIn(frozenset(article.title for article in invites), event_partitions(events))
        self.assertTrue(all(article.category == "software_systems" for article in [*testflight, *invites]))
        self.assertTrue(all(event.event_kind == "os_app" for event in events))

    def test_unrelated_weak_third_party_events_cannot_merge_from_body_background(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "三星时隔多年杀入金融科技领域 推出全新信用卡产品 - Samsung 三星 - cnBeta.COM",
                "The Samsung fintech product supports common wallets and mentions Apple Pay as market background.",
                "AppleInsider",
            ),
            article_for(
                module,
                "台积电芯片代工基准价格拟上调最高达10% - TSMC 台积电 - cnBeta.COM",
                "The report lists Apple, Qualcomm, and MediaTek among many customers affected by broad chip costs.",
                "cnBeta",
            ),
            article_for(
                module,
                "Intel wins Fortinet as its first public external foundry customer",
                "The manufacturing report compares Intel capacity with TSMC and mentions Apple chip orders as history.",
                "快科技",
            ),
        ]

        for article in articles:
            article.relevance_tier = "weak"
            article.relevance_reason = "non-Apple primary subject with incidental Apple context"
            self.assertNotIn("com", module.article_title_led_event_identity(article).named_subjects)
        self.assertEqual(len(module.cluster_articles(articles)), 3)

    def test_supplier_input_cost_event_does_not_merge_with_device_price_forecast(self):
        module = load_module()
        supplier_cost = [
            article_for(
                module,
                "Apple Chipmaker TSMC Plans Price Hikes of Up to 10% in 2027",
                "TSMC plans to increase advanced-node chip prices, directly raising Apple's processor costs.",
                "MacRumors",
            ),
            article_for(
                module,
                "More bad news for Apple pricing as TSMC increases chip costs",
                "TSMC is raising fabrication prices for Apple chips in 2027.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Expect 2027 iPhones to cost more as TSMC increases chip prices",
                "The supplier price increase affects Apple processors and could pressure future device pricing.",
                "AppleInsider",
            ),
        ]
        device_price = article_for(
            module,
            "iPhone 18 Pro Max price could rise by $200 at launch",
            "A separate forecast estimates the future retail price of one iPhone model.",
            "IT之家",
        )

        self.assertTrue(all(article.relevance_tier == "strong" for article in supplier_cost))
        events = module.cluster_articles([device_price, *supplier_cost])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in supplier_cost), event_partitions(events))

    def test_title_primary_supplier_price_report_beats_downstream_device_price_forecast(self):
        module = load_module()
        device_price = article_for(
            module,
            "涨价 1000 元：iPhone 18 Pro Max 起售价或达 1.1 万元",
            (
                "博主预测下一代 iPhone 的中国零售价将上涨，背景原因包括内存和台积电 2nm 成本。"
                "文章没有报告供应商已完成新的价格谈判。"
            ),
            "快科技",
        )
        chinese_supplier = article_for(
            module,
            "苹果 iPhone 18 Pro 系列涨价成定局：台积电敲定 2027 年涨价最高达 10%",
            "台积电已与客户完成晶圆代工价格谈判，2027 年基础报价将上调 5% 至 10%。",
            "快科技",
        )
        english_supplier = article_for(
            module,
            "Apple Chipmaker TSMC Plans Price Hikes of Up to 10% in 2027",
            "TSMC completed talks with clients covering the same foundry base-price increase.",
            "MacRumors",
        )

        events = module.cluster_articles([device_price, chinese_supplier, english_supplier])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(
            frozenset([chinese_supplier.title, english_supplier.title]),
            event_partitions(events),
        )

    def test_shared_chip_name_cannot_bridge_distinct_iphone_price_and_product_roadmaps(self):
        module = load_module()
        device_price = article_for(
            module,
            "涨价 1000 元：iPhone 18 Pro Max 起售价或达 1.1 万元",
            "博主暗示并预计 A20 Pro 和内存成本会推高下一代 Pro Max 的零售价。",
            "快科技",
        )
        air_successor = article_for(
            module,
            "2027 年发布 iPhone Air 2：双摄、A20 Pro、VC 散热",
            "第二代 iPhone Air 预计补齐相机、电池和散热短板，并使用 A20 Pro。",
            "快科技",
        )
        air_followup = article_for(
            module,
            "iPhone Air 2 有望补齐短板：双摄、A20 Pro、VC 散热",
            "同一产品路线图还包括 3,500mAh 电池与超广角镜头。",
            "cnBeta",
        )

        events = module.cluster_articles([device_price, air_successor, air_followup])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(
            frozenset([air_successor.title, air_followup.title]),
            event_partitions(events),
        )

    def test_distinct_display_changes_do_not_merge_on_shared_iphone_roadmap_words(self):
        module = load_module()
        anniversary_display = [
            article_for(
                module,
                "Apple Testing 7-Inch Display for Largest 20th Anniversary iPhone Model",
                "Apple is testing a 7-inch display for the largest anniversary iPhone.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果测试 7 英寸二十周年 iPhone 显示屏",
                "供应链称苹果正在测试同一款 7 英寸周年机型屏幕。",
                "IT之家",
            ),
            article_for(
                module,
                "Largest ever iPhone screen arriving next year, suggests leaker",
                "Supply chain sources say Apple is trialing its largest ever iPhone display for next year's anniversary model.",
                "9to5Mac",
            ),
        ]
        ltpo = article_for(
            module,
            "iPhone 18 Pro display upgrades include LTPO+ and wider ProMotion support",
            "A separate panel report describes LTPO+ technology and refresh-rate changes.",
            "9to5Mac",
        )

        events = module.cluster_articles([*anniversary_display, ltpo])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in anniversary_display), event_partitions(events))
        self.assertFalse(
            module.is_apple_display_panel_supply_chain_story(
                "Supply chain sources say Apple is trialing its largest ever iPhone screen for next year."
            )
        )
        self.assertTrue(
            module.is_apple_display_panel_supply_chain_story(
                "Samsung Display will supply Apple with 10 million OLED iPhone panels under a new panel order."
            )
        )

    def test_direct_apple_patent_and_official_product_story_stay_strong(self):
        module = load_module()
        samples = [
            (
                "Future iMac could come with a removable dock and carrying handle",
                "A newly published Apple patent describes an iMac chassis with a removable dock and handle.",
                "AppleInsider",
            ),
            (
                "Apple shares video showing Apple Watch helping rescue a swimmer",
                "Apple published an official video demonstrating the Watch emergency feature in a real rescue.",
                "9to5Mac",
            ),
        ]

        for title, summary, source in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "strong", reason)

    def test_product_patent_disclosure_does_not_merge_with_patent_litigation(self):
        module = load_module()
        imac_patents = [
            article_for(
                module,
                "Future iMac could come with a removable dock or carrying handle",
                "A newly granted Apple design patent describes a detachable iMac dock and folding handle.",
                "AppleInsider",
            ),
            article_for(
                module,
                "行走的 iMac：苹果专利探索可拆卸扩展坞与折叠提手",
                "苹果获批的设计专利勾勒了同一款便携 iMac 方案。",
                "IT之家",
            ),
        ]
        litigation = article_for(
            module,
            "Apple loses bid to overturn $634 million Masimo patent verdict",
            "A court rejected Apple's challenge to a patent-infringement verdict involving Apple Watch.",
            "9to5Mac",
        )

        events = module.cluster_articles([*imac_patents, litigation])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in imac_patents), event_partitions(events))

    def test_product_patent_identity_can_use_clean_detail_lead_beyond_first_paragraph(self):
        module = load_module()
        english = article_for(
            module,
            "Future iMac could come with a removable dock or handle to make it easier to carry",
            (
                "Moving an all-in-one desktop is awkward, and transporting many units also requires bulky packaging. "
                "Existing carrying cases solve only part of that problem for customers and do not simplify shipping. "
                "Apple has therefore explored a thinner transport design. A newly-granted patent called Low profile "
                "computer support describes a removable dock and a folding handle for the iMac."
            ),
            "AppleInsider",
        )
        chinese = article_for(
            module,
            "“行走的 iMac”：苹果专利探索便携方案，可拆卸扩展坞 / 折叠式提手",
            "苹果最新获批专利描述同一款可拆卸扩展坞与折叠式提手方案。",
            "IT之家",
        )

        self.assertIn(
            "product-patent-disclosure",
            module.article_title_led_event_identity(english).components,
        )
        self.assertIn(
            "product-patent-disclosure",
            module.article_title_led_event_identity(chinese).components,
        )
        self.assertEqual(
            module.identity_pair_decision(
                module.article_title_led_event_identity(english),
                module.article_title_led_event_identity(chinese),
            ),
            "match",
        )
        self.assertEqual(english.relevance_tier, chinese.relevance_tier)
        self.assertTrue(module.regions_compatible(english, module.singleton_merge_event(chinese)))
        self.assertTrue(module.should_merge(english, module.singleton_merge_event(chinese)))
        self.assertTrue(module.should_merge(chinese, module.singleton_merge_event(english)))
        self.assertTrue(module.articles_share_cohesive_title_identity([english, chinese]))
        clusters = module.cluster_articles([english, chinese])
        self.assertEqual(
            len(clusters),
            1,
            [
                {
                    "titles": [article.title for article in event.articles],
                    "warnings": event.merge_warnings,
                    "kind": event.event_kind,
                }
                for event in clusters
            ],
        )

    def test_official_product_story_merges_across_languages_when_action_words_are_separated(self):
        module = load_module()
        english = article_for(
            module,
            "Apple shares video on how Apple Watch helped rescue an injured cyclist",
            "Apple published an official video about Fall Detection and Emergency SOS helping Phil after a crash.",
            "9to5Mac",
        )
        chinese = article_for(
            module,
            "苹果发布 Apple Watch 真实案例视频，山地骑行事故中帮助挽救男子生命",
            "苹果官方视频讲述同一名男子 Phil 的山地骑行救援经历。",
            "IT之家",
        )

        self.assertEqual(len(module.cluster_articles([english, chinese])), 1)

    def test_rumor_roundups_and_multi_vendor_predictions_stay_deferred(self):
        module = load_module()
        samples = [
            (
                "苹果 iPhone 18 Pro / Max 爆料汇总：A20 芯片、可变光圈等",
                "文章汇总此前传闻，没有新增消息。",
            ),
            (
                "iPhone 18 Rumor Reality Check: 20 Claims Ranked by Likelihood",
                "The article ranks previously reported rumors without new reporting.",
            ),
            (
                "9月份新机预测：iPhone 18、小米18、华为Mate 90谁更有料",
                "文章比较苹果、小米和华为三家新机的配置与价格预测。",
            ),
        ]

        for title, summary in samples:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "快科技")
                self.assertEqual(tier, "weak", reason)

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

    def test_same_product_generation_production_ramp_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "苹果 iPhone 18 Pro 系列已量产：目前处于产能爬坡阶段，富士康迎来招工高峰",
                (
                    "苹果 iPhone 18 系列已于本月进入量产阶段，目前正处于产能提升阶段。"
                    "背景数据显示 iPhone 在中国市场份额增长。"
                ),
                "IT之家",
            ),
            article_for(
                module,
                "苹果iPhone 18系列进入量产爬坡期，富士康迎来招工高峰",
                (
                    "产业链人士称 iPhone 18 系列已进入量产阶段，目前正处于产能爬坡期。"
                    "背景还提到 Pro 系列灵动岛开孔缩小。"
                ),
                "快科技",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]
        self.assertTrue(
            all("production-ramp" in identity.title_components for identity in identities)
        )
        self.assertTrue(
            all("product-generation:iphone-18" in identity.title_components for identity in identities)
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_anniversary_iphone_generation_report_merges_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Here's What the 'iPhone 20' is Expected to Look Like",
                (
                    "Apple's 20th anniversary iPhone is expected to arrive in the fall of 2027 "
                    "with the most significant design overhaul since the iPhone X. The device "
                    "may use optical refraction, light-guiding structures, and a visual illusion "
                    "to make the frame recede from view, unlike curved screens on Android phones. "
                    "An unverified mock-up depicted a 1.1mm "
                    "bezel compared with approximately 1.44mm on the iPhone 17 Pro. Apple wants "
                    "to move Face ID and the selfie camera beneath the display. "
                    + " ".join(f"background-detail-{index}" for index in range(120))
                    + " DSCC's Ross Young says the technology is unlikely to be fully ready for 2027. "
                    "Apple is reportedly planning two anniversary models at roughly 6.3 and 6.9 inches."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 20 周年纪念版 iPhone 前瞻：微曲面显示屏、无实体按键，真全面屏仍存悬念",
                (
                    "据科技媒体 MacRumors 报道，苹果预计将在 2027 年秋季推出 20 周年纪念版 "
                    "iPhone，并带来 iPhone X 同等规模的创新。苹果希望这款手机完全没有屏幕 "
                    "开孔，将面容 ID 和前置摄像头隐藏在屏幕下方，但 DSCC 研究员 Ross Young "
                    "认为这种技术很难在 2027 年成熟。产品预计有 6.3 英寸和 6.9 英寸两种版本。"
                    "这两个尺寸类似 iPhone 18 Pro 和 iPhone 18 Pro Max。"
                ),
                "IT之家",
                ["产品预计有 6.3 英寸和 6.9 英寸两种版本，类似 iPhone 18 Pro 和 iPhone 18 Pro Max。"],
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]
        self.assertTrue(
            all("product-generation:iphone-20" in identity.title_components for identity in identities)
        )
        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})

    def test_cohesive_product_generation_event_is_not_downgraded_by_comparison_background(self):
        module = load_module()
        english = article_for(
            module,
            "Here's What the 'iPhone 20' is Expected to Look Like",
            "Apple's anniversary iPhone uses a display unlike curved screens on Android phones.",
            "MacRumors",
        )
        chinese = article_for(
            module,
            "苹果 20 周年纪念版 iPhone 前瞻",
            "苹果预计推出 6.3 英寸和 6.9 英寸两种版本，尺寸类似 iPhone 18 Pro 系列。",
            "IT之家",
        )
        self.assertEqual([english.relevance_tier, chinese.relevance_tier], ["strong", "strong"])
        event = module.cluster_articles([english, chinese])[0]

        self.assertEqual(event.relevance_tier, "strong")

    def test_production_ramps_for_different_product_generations_do_not_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 enters mass production ramp at Foxconn",
                "Apple suppliers started ramping production for the iPhone 18 generation.",
                "9to5Mac",
            ),
            article_for(
                module,
                "iPhone 19 enters mass production ramp at Foxconn",
                "Apple suppliers started ramping production for the iPhone 19 generation.",
                "MacRumors",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 2, event_partitions(module.cluster_articles(articles)))

    def test_applecare_coverage_and_payment_changes_are_service_content(self):
        module = load_module()
        title = "AppleCare+ Changes Announced in Japan"
        summary = (
            "Apple expanded theft and loss coverage to iPad and Apple Watch, and added monthly "
            "or annual AppleCare+ payment options for more products in Japan."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "service_content")
        self.assertEqual(module.choose_category(title, summary), "software_systems")

    def test_apple_store_shopping_assistant_merges_without_competitor_or_financing_bridge(self):
        module = load_module()
        assistant_articles = [
            article_for(
                module,
                "Apple Store App Getting AI Shopping Assistant",
                "Apple updated the Apple Store app privacy policy for a virtual shopping assistant.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple Store app may soon get an AI-powered shopping assistant",
                "The unreleased Apple Store app assistant will answer product and compatibility questions.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果 Apple Store 应用即将迎来 AI 购物助手",
                "苹果官方应用隐私条款披露虚拟购物助手，可通过聊天帮助用户选购产品。",
                "cnBeta",
            ),
        ]
        restriction = article_for(
            module,
            "苹果 iOS 27 代码曝光：租赁设备逾期未还款或将进入受限模式",
            "iOS 27 代码显示 Apple Upgrade 租赁设备欠款后会启用 Partner Finance Lock。",
            "cnBeta",
        )
        competitor = article_for(
            module,
            "Hands-On With Samsung's Galaxy Z Fold8, the Closest Thing Yet to a Foldable iPhone",
            "Samsung launched its foldable phone; the article compares it with a future foldable iPhone.",
            "MacRumors",
        )

        events = module.cluster_articles([competitor, *assistant_articles, restriction])

        self.assertEqual(len(events), 3, event_partitions(events))
        self.assertIn(
            frozenset(article.title for article in assistant_articles),
            event_partitions(events),
        )
        assistant_event = next(
            event for event in events if assistant_articles[0].title in {a.title for a in event.articles}
        )
        self.assertEqual(assistant_event.relevance_tier, "strong")
        self.assertEqual(competitor.relevance_tier, "weak")

    def test_product_generation_does_not_hide_production_ramp_from_lead(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Foxconn Ramps Up Hiring as iPhone 18 Pro Enters Mass Production",
                "Apple's iPhone 18 Pro entered mass production and Foxconn raised hiring for the ramp.",
                "MacRumors",
            ),
            article_for(
                module,
                "It has begun: Foxconn amassing army of workers for iPhone 18 Pro assembly",
                "The report says the iPhone 18 Pro has entered the mass production stage and Foxconn is recruiting workers.",
                "AppleInsider",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]

        self.assertTrue(all("production-ramp" in identity.components for identity in identities))
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_same_camera_and_facility_actions_merge_across_title_wording(self):
        module = load_module()
        camera = [
            article_for(
                module,
                "The iPhone 18 Pro's Rumored Camera Upgrade, Explained",
                "Apple is expected to introduce a variable-aperture main camera on iPhone 18 Pro.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果 iPhone 18 Pro 系列将首次引入可变光圈相机系统",
                "机械式可变光圈将调整进光量并改善景深控制。",
                "cnBeta",
            ),
        ]
        facility = [
            article_for(
                module,
                "Apple Park Visitor Center Has 'Update in Progress'",
                "The Exhibition Space closed temporarily while Apple renovates the visitor center.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple Park Visitor Center partially closed for store improvements",
                "Apple partially closed the Visitor Center for improvements while the store remains open.",
                "9to5Mac",
            ),
        ]

        events = module.cluster_articles([*camera, *facility])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in camera), event_partitions(events))
        self.assertIn(frozenset(article.title for article in facility), event_partitions(events))

    def test_broad_mac_roadmap_article_splits_into_product_scoped_variants(self):
        module = load_module()
        title = "Apple's huge Mac roadmap revealed in new report"
        facts = [
            "The entry 14-inch MacBook Pro J804 is expected to use M6 this fall.",
            "The 13-inch and 15-inch MacBook Air models J913 and J915 are planned for early 2027.",
            "Apple is testing a Mac mini with M6 and M5 Pro chips.",
            "A new Mac Studio is expected to use M5 Max and M5 Ultra.",
            "The next iMac is ready for this year, while an OLED iMac remains in development.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)
        variant_products = {
            frozenset(module.title_led_identity(variant_title, variant_summary).products)
            for variant_title, variant_summary, _ in variants
        }

        self.assertGreaterEqual(len(variants), 5)
        self.assertTrue(
            {
                frozenset({"macbook"}),
                frozenset({"mac-mini"}),
                frozenset({"mac-studio"}),
                frozenset({"imac"}),
            }.issubset(variant_products),
            variant_products,
        )

    def test_mac_roadmap_variants_split_same_product_distinct_chip_generations(self):
        module = load_module()
        title = "Apple's huge Mac roadmap revealed in new report"
        facts = [
            "The redesigned MacBook Pro models K114 and K116 will use M5 Pro and M5 Max with OLED touchscreens in early 2027.",
            "The touch sensors are integrated into the OLED panel and macOS will enlarge controls for touch input.",
            "A separate redesigned MacBook Pro K104 with the standard M7 chip is planned for late 2027.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)
        macbook_pro_variants = [
            (variant_title, variant_summary, variant_facts)
            for variant_title, variant_summary, variant_facts in variants
            if "MacBook Pro" in variant_title
        ]

        self.assertEqual(len(macbook_pro_variants), 2, macbook_pro_variants)
        m5_variant = next(item for item in macbook_pro_variants if "M5" in item[0])
        m7_variant = next(item for item in macbook_pro_variants if "M7" in item[0])
        self.assertNotIn("M6", m5_variant[0])
        self.assertNotIn("M7", " ".join(m5_variant[2]))
        self.assertNotIn("M5", " ".join(m7_variant[2]))

        negated_identity = module.title_led_identity(
            "Apple's touchscreen MacBook Pro will use M5 Pro and M5 Max, not M6",
            "The OLED model is a direct Apple hardware roadmap report.",
        )
        self.assertIn("apple-silicon-generation:m5", negated_identity.title_components)
        self.assertNotIn("apple-silicon-generation:m6", negated_identity.title_components)

    def test_current_market_performance_does_not_merge_with_future_product_roadmap(self):
        module = load_module()
        market = article_for(
            module,
            "Apple defied a global PC sales slump in Q2 2026 thanks to MacBook Neo",
            "Global PC shipments declined 4%, while MacBook Neo shipments grew 13% in the quarter.",
            "AppleInsider",
        )
        roadmap = article_for(
            module,
            "苹果 MacBook Neo 2 笔记本前瞻：A19 Pro 芯片 + 12GB 内存",
            "苹果计划 2027 年发布第二代 MacBook Neo，并测试 A19 Pro 和 12GB 内存。",
            "IT之家",
        )

        events = module.cluster_articles([market, roadmap])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_focused_touchscreen_macbook_merges_with_matching_roadmap_variant(self):
        module = load_module()
        focused = article_for(
            module,
            "苹果首款触控屏 MacBook 笔记本前瞻：M5 Pro / Max 芯片，最快年底登场",
            "苹果正在开发 14 英寸和 16 英寸 OLED 触控 MacBook Pro，搭载 M5 Pro 和 M5 Max。",
            "IT之家",
        )
        roadmap_variant = article_for(
            module,
            "Apple MacBook Pro M5 roadmap update",
            "Apple is developing redesigned 14-inch and 16-inch OLED touchscreen MacBook Pro models K114 and K116 with M5 Pro and M5 Max.",
            "快科技",
        )

        events = module.cluster_articles([focused, roadmap_variant])

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_direct_mac_roadmap_sources_are_strong_and_same_product_sources_merge(self):
        module = load_module()
        imac = [
            article_for(
                module,
                "iMac Update Expected This Year, Model With OLED Display Also in Works",
                "Apple completed a new 24-inch iMac for this year and is developing a later OLED iMac.",
                "MacRumors",
            ),
            article_for(
                module,
                "新一代 iMac 有望于今年问世，未来还将推出 OLED 屏幕版本",
                "苹果今年更新 24 英寸 iMac，并继续开发后续 OLED 机型。",
                "cnBeta",
            ),
        ]
        macbook_ultra = article_for(
            module,
            "'MacBook Ultra' Reportedly on Track for Release by Early Next Year",
            "Apple's high-end MacBook roadmap includes an OLED display, touch support, and M5 Pro or M5 Max.",
            "MacRumors",
        )

        events = module.cluster_articles([*imac, macbook_ultra])

        self.assertTrue(all(article.relevance_tier == "strong" for article in [*imac, macbook_ultra]))
        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in imac), event_partitions(events))

    def test_iphone_to_android_migration_is_one_ecosystem_event_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Switching From iPhone to Android Just Got Easier With Android 17",
                "Android 17 can directly transfer iPhone passwords, Wi-Fi credentials, and eSIM data.",
                "MacRumors",
            ),
            article_for(
                module,
                "谷歌上线全新数据迁移功能：从苹果 iPhone 换到安卓更方便，密码也能同步",
                "Android 17 原生迁移流程可从 iPhone 传输密码、Wi-Fi 凭据和 eSIM。",
                "IT之家",
            ),
            article_for(
                module,
                "Google 升级 Android 数据迁移工具，支持从 iPhone 直接转移密码与 eSIM",
                "新流程直接影响 iPhone 与 Android 之间的数据互操作。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertTrue(all(article.relevance_tier == "ecosystem" for article in articles))
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_mac_roadmap_variants_do_not_reintroduce_other_product_names(self):
        module = load_module()
        title = "Upgraded Mac Mini, Mac Studio, and OLED iMac are all in the pipeline"
        facts = [
            "Apple is preparing a Mac mini with M6 and M5 Pro chips.",
            "A new Mac Studio is expected to use M5 Max and M5 Ultra.",
            "The next iMac is ready for this year, while an OLED iMac remains in development.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)
        variant_titles = {variant_title for variant_title, _summary, _facts in variants}

        self.assertEqual(len(variants), 3, variants)
        for variant_title in variant_titles:
            subjects = module.multi_product_hardware_subjects(variant_title)
            self.assertEqual(len(subjects), 1, (variant_title, subjects))

        articles = [
            article_for(module, variant_title, variant_summary, "AppleInsider")
            for variant_title, variant_summary, _facts in variants
        ]
        self.assertEqual(len(module.cluster_articles(articles)), 3, event_partitions(module.cluster_articles(articles)))

    def test_distinct_macbook_models_do_not_merge_through_generic_roadmap_terms(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple MacBook Pro roadmap update",
                "Apple plans an OLED MacBook Pro with an M7 chip.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple MacBook Air roadmap update",
                "Apple plans a MacBook Air refresh with an M6 chip.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple MacBook Neo roadmap update",
                "Apple plans a MacBook Neo refresh with more memory.",
                "AppleInsider",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 3, event_partitions(module.cluster_articles(articles)))

    def test_numbered_first_party_content_announcements_split_into_events(self):
        module = load_module()
        title = "Apple TV announces two high-profile new shows"
        facts = [
            "#1: Protective Custody is a new comedy with Benicio Del Toro and Ben Stiller",
            "Apple unveiled Protective Custody, a comedy about a disgraced financier.",
            "#2: Peculiar Stars is a new romance adaptation from Rebecca Yarros",
            "Apple secured the rights to adapt Peculiar Stars into an Apple TV series.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(len(variants), 2, variants)
        self.assertIn("Protective Custody", variants[0][0])
        self.assertIn("Peculiar Stars", variants[1][0])

    def test_direct_mac_product_roadmap_is_hardware_even_with_ai_background(self):
        module = load_module()
        title = "Apple Working on New MacBook Neo With Two Upgrades"
        summary = (
            "Apple is testing a MacBook Neo with an A19 Pro and 12GB of memory. "
            "The extra memory also supports larger on-device AI models."
        )

        self.assertEqual(module.detect_event_kind(title, summary), "hardware_market")
        self.assertEqual(module.choose_category(title, summary), "hardware_products")

    def test_product_scoped_roadmap_projection_merges_with_focused_source(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple iMac roadmap update",
                "Apple plans a refreshed iMac this fall and is developing a later OLED model.",
                "MacRumors",
            ),
            article_for(
                module,
                "iMac Update Expected This Year, Model With OLED Display Also in Works",
                "Apple completed a new 24-inch iMac and is developing a future OLED iMac.",
                "AppleInsider",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_compound_product_report_projects_facts_by_concrete_action(self):
        module = load_module()
        title = "iPhone 18 enters mass production as Apple plans a price increase"
        facts = [
            "The iPhone 18 Pro entered mass production and suppliers are ramping capacity.",
            "Apple delayed the standard iPhone 18 until spring 2027.",
            "The iPhone 18 Pro adds a variable-aperture main camera.",
            "Apple may raise the iPhone 18 Pro starting price to $1,199.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)
        identities = [
            module.title_led_identity(variant_title, variant_summary)
            for variant_title, variant_summary, _variant_facts in variants
        ]

        self.assertEqual(len(variants), 4, variants)
        self.assertTrue(any("production-ramp" in identity.components for identity in identities))
        self.assertTrue(any("product-release-delay" in identity.components for identity in identities))
        self.assertTrue(any("camera-system" in identity.components for identity in identities))
        self.assertTrue(any("price-change" in identity.actions for identity in identities))

    def test_single_action_product_title_does_not_project_body_background(self):
        module = load_module()
        title = "iPhone 18 Pro enters mass production"
        facts = [
            "The iPhone 18 Pro entered mass production this month.",
            "Earlier rumors said the model could use a variable-aperture camera.",
            "Analysts previously expected component costs to increase.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(variants, [(title, " ".join(facts), facts)])

    def test_shared_os_version_does_not_merge_distinct_first_party_components(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iOS 27 adds convenient new iPhone feature",
                "The keyboard now shows a paste suggestion for copied text and images.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Card adds a new feature in iOS 27",
                "Wallet now groups recurring transactions and subscription charges.",
                "MacRumors",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]

        self.assertIn("clipboard-paste-suggestion", identities[0].components)
        self.assertIn("recurring-transactions", identities[1].components)
        self.assertEqual(len(module.cluster_articles(articles)), 2, event_partitions(module.cluster_articles(articles)))

    def test_financed_device_restriction_sources_do_not_bridge_into_leasing_program(self):
        module = load_module()
        program = article_for(
            module,
            "Apple Upgrade leasing program launches next week",
            "Apple will offer 24-month and 36-month device leases.",
            "9to5Mac",
        )
        restrictions = [
            article_for(
                module,
                "iOS code could let Apple cut off apps when users miss iPhone payments",
                "The financed iPhone enters a restricted mode after a missed payment.",
                "The Verge",
            ),
            article_for(
                module,
                "苹果 iOS 27 代码曝光：租赁设备逾期未还款将进入受限模式",
                "欠款设备只保留系统白名单应用，并启用 Partner Finance Lock。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles([program, *restrictions])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in restrictions), event_partitions(events))
        self.assertTrue(all(article.category == "hardware_products" for article in restrictions))

        compound = module.compound_article_variants(
            "Don't miss a payment with Apple Upgrade or your iPhone will be locked",
            (
                "Apple Upgrade is a new device leasing program. If a payment is missed, "
                "the financed iPhone enters Restricted Mode."
            ),
            [
                "Apple Upgrade uses monthly device leases.",
                "A missed payment activates Restricted Mode and Partner Finance Lock.",
            ],
        )
        self.assertEqual(len(compound), 2, compound)

    def test_body_platform_mentions_do_not_promote_unrelated_third_party_app(self):
        module = load_module()
        app = article_for(
            module,
            "This iPhone app patches a hidden Bluetooth alarm flaw in millions of cars",
            (
                "KARR Security updated its dealer-installed car alarm app. The article background "
                "mentions Android support and CarPlay, but Apple did not change iOS or its platform."
            ),
            "AppleInsider",
        )
        ios_feature = article_for(
            module,
            "iOS 27 adds convenient new iPhone paste feature",
            "Apple changed the native paste menu in iOS 27 for copied text.",
            "9to5Mac",
        )

        self.assertEqual(app.relevance_tier, "weak")
        self.assertEqual(len(module.cluster_articles([app, ios_feature])), 2)

    def test_ordinal_public_beta_title_matches_numbered_beta_wave(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Second macOS Golden Gate Public Beta Now Available",
                "Apple released the second public beta of macOS 27 Golden Gate.",
                "MacRumors",
            ),
            article_for(
                module,
                "macOS 27 public beta 2 now available",
                "Apple released macOS 27 public beta 2 to public testers.",
                "9to5Mac",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]

        self.assertTrue(all("os-wave:27:beta-2" in identity.components for identity in identities))
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_same_standard_iphone_delay_merges_despite_background_topics(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 exits fall launch lineup as Apple prioritizes Pro models",
                "Apple delayed the standard iPhone 18 until spring while keeping Pro models in fall.",
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 今年缺席：苹果基础款手机改到明年春季发布",
                "苹果将标准版 iPhone 18 延期到明年春季，Pro 系列仍在秋季发布。",
                "快科技",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]

        self.assertTrue(all("product-release-delay" in identity.components for identity in identities))
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_same_apple_park_renovation_merges_across_action_wording(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Park Visitor Center Has 'Update in Progress'",
                "Apple temporarily closed its Exhibition Space while renovating the visitor center.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple Park Visitor Center partially closed for store improvements",
                "The Visitor Center is partially closed while Apple completes store improvements.",
                "9to5Mac",
            ),
        ]

        identities = [module.article_title_led_event_identity(article) for article in articles]

        self.assertTrue(all("facility-renovation" in identity.components for identity in identities))
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_distinct_ios_components_do_not_merge_through_shared_os_version(self):
        module = load_module()
        lock_screen = article_for(
            module,
            "iOS 27 Adds Five New Features to the iPhone Lock Screen",
            "Apple added clock, wallpaper, notification, and Lock Screen controls in iOS 27.",
            "MacRumors",
        )
        photos = article_for(
            module,
            "iOS 27 gives Apple Photos a very useful feature I've wanted for years",
            "Apple Photos in iOS 27 adds a new sorting control for the photo library.",
            "9to5Mac",
        )

        events = module.cluster_articles([lock_screen, photos])

        self.assertEqual(len(events), 2, event_partitions(events))

    def test_distinct_apple_tv_programs_stay_separate_but_same_program_merges(self):
        module = load_module()
        morning_show = article_for(
            module,
            "Apple TV confirms 'The Morning Show' will end with season six",
            "Apple TV confirmed The Morning Show will conclude with its sixth season in 2027.",
            "9to5Mac",
        )
        morning_show_followup = article_for(
            module,
            "'The Morning Show' will bring Apple TV's first prestige drama to an end in 2027",
            "Apple TV will end The Morning Show with season six in 2027.",
            "AppleInsider",
        )
        dating_series = article_for(
            module,
            "Apple TV orders dating docuseries 'The Last Person on Earth'",
            "The Last Person on Earth is a new Apple TV dating docuseries.",
            "The Verge",
        )
        the_dink = article_for(
            module,
            "Apple TV sets premiere date for new comedy 'The Dink'",
            "The Dink will premiere on Apple TV later this year.",
            "MacRumors",
        )

        events = module.cluster_articles(
            [morning_show, morning_show_followup, dating_series, the_dink]
        )

        self.assertEqual(len(events), 3, event_partitions(events))
        morning_event = next(event for event in events if morning_show in event.articles)
        self.assertEqual(
            {article.source for article in morning_event.articles},
            {"9to5Mac", "AppleInsider"},
        )

    def test_apple_maps_platform_integration_merges_official_and_media_reports(self):
        module = load_module()
        official = article_for(
            module,
            "Apple Maps to power navigation experience for Ford UEV platform",
            "Apple announced that Apple Maps will power navigation in Ford's UEV platform.",
            "Apple Newsroom",
        )
        media = article_for(
            module,
            "Ford integrates Apple Maps into its new UEV navigation platform",
            "Ford is using Apple Maps and MapKit in the same UEV navigation experience.",
            "9to5Mac",
        )

        self.assertEqual(len(module.cluster_articles([official, media])), 1)

    def test_foldable_iphone_production_hurdle_does_not_merge_generic_iphone_production(self):
        module = load_module()
        foldable_reports = [
            article_for(
                module,
                "Apple's foldable iPhone faces production hurdles before launch",
                "Apple and suppliers are resolving manufacturing obstacles for the foldable iPhone.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果折叠屏 iPhone 量产仍面临制造难题",
                "供应链正在解决折叠 iPhone 的生产障碍和良率瓶颈。",
                "IT之家",
            ),
        ]
        generic_iphone = article_for(
            module,
            "iPhone 18 Pro enters mass production",
            "Apple suppliers started mass production of the iPhone 18 Pro.",
            "快科技",
        )

        events = module.cluster_articles([*foldable_reports, generic_iphone])

        self.assertEqual(len(events), 2, event_partitions(events))
        foldable_event = next(event for event in events if foldable_reports[0] in event.articles)
        self.assertEqual(
            {article.title for article in foldable_event.articles},
            {article.title for article in foldable_reports},
        )

    def test_apple_tv_lifecycle_actions_split_unquoted_program_titles(self):
        module = load_module()
        morning_reports = [
            article_for(
                module,
                "Apple announces The Morning Show is ending after season 5",
                "Apple TV announced the final season of The Morning Show for 2027.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple TV 质量标杆：苹果官宣《早间新闻》最终季 2027 年播出",
                "苹果宣布《早间新闻》第五季也是最终季，将于 2027 年完结。",
                "IT之家",
            ),
        ]
        dating_reports = [
            article_for(
                module,
                "Apple TV announces new dating series: The Last Person on Earth",
                "Apple TV announced the new eight-part dating documentary series.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple TV is branching out with a self-help eight-part dating docuseries",
                "Apple TV announced The Last Person on Earth as a new dating docuseries.",
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles([*morning_reports, *dating_reports])

        self.assertEqual(len(events), 2, event_partitions(events))
        morning_event = next(event for event in events if morning_reports[0] in event.articles)
        self.assertEqual({article.source for article in morning_event.articles}, {"9to5Mac", "IT之家"})

    def test_real_apple_maps_integration_wording_merges_official_and_media(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Maps to power navigation experience for Ford UEV Platform",
                "Apple and Ford announced Apple Maps will be integrated directly into Ford's UEV Platform.",
                "Apple Newsroom",
            ),
            article_for(
                module,
                "Apple Maps to Help Power Autonomous Driving in Ford's 2027 EV",
                "Ford will embed Apple Maps through the MapKit for Automotive SDK.",
                "MacRumors",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_real_foldable_production_hurdle_wording_merges_but_generic_iphone_stays_separate(self):
        module = load_module()
        foldable = [
            article_for(
                module,
                "Foldable iPhone Still Faces Production Hurdles, Report Says",
                "Foxconn is making final mass-production adjustments while launch timing remains undecided.",
                "MacRumors",
            ),
            article_for(
                module,
                "苹果首款折叠手机 iPhone Ultra 发布日期尚不明朗，消息称富士康正调整产线",
                "组装复杂和良率较低可能造成延期，富士康正调整制造流程。",
                "IT之家",
            ),
        ]
        generic = article_for(
            module,
            "iPhone 18 Pro 开始量产",
            "苹果供应商开始量产 iPhone 18 Pro。",
            "快科技",
        )
        foldable[0].regions = {"united-states"}
        foldable[1].regions = {"china"}

        events = module.cluster_articles([*foldable, generic])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertTrue(
            any(
                {article.title for article in foldable}
                == {article.title for article in event.articles}
                for event in events
            )
        )

    def test_chatgpt_health_rollout_merges_across_integration_wording(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "ChatGPT's Apple Health Integration Now Rolling Out to U.S. Users",
                "OpenAI is rolling out ChatGPT Health with connected Apple Health data.",
                "MacRumors",
            ),
            article_for(
                module,
                "OpenAI relaunches Apple Health-connected ChatGPT feature with expanded access",
                "OpenAI is rolling out the connected Apple Health feature to more users.",
                "9to5Mac",
            ),
            article_for(
                module,
                "OpenAI全面开放ChatGPT Health功能：整合Apple Health与电子病历",
                "OpenAI 全面开放该功能，接入 Apple Health 数据。",
                "cnBeta",
            ),
            article_for(
                module,
                "OpenAI 上线 ChatGPT Health：接入苹果 Health 等数据",
                "该服务向用户开放，并直接接入苹果 Health 数据。",
                "IT之家",
            ),
        ]
        unrelated = article_for(
            module,
            "iPhone Driver's Licenses May Soon Expand to New State",
            "A related link mentions that ChatGPT Health integrates Apple Health data.",
            "MacRumors",
        )
        privacy_commentary = article_for(
            module,
            "Connecting Apple Health to ChatGPT creates privacy risks Siri AI can avoid",
            "The analysis discusses the privacy tradeoffs after the feature rollout.",
            "AppleInsider",
        )

        identities = [module.article_title_led_event_identity(article) for article in articles]
        self.assertTrue(all("apple-data-integration" in identity.components for identity in identities))
        self.assertNotIn(
            "apple-data-integration",
            module.article_title_led_event_identity(unrelated).components,
        )
        events = module.cluster_articles([*articles, unrelated, privacy_commentary])
        self.assertEqual(len(events), 3, event_partitions(events))
        health_event = next(event for event in events if articles[0] in event.articles)
        self.assertEqual(
            {article.source for article in health_event.articles},
            {"MacRumors", "9to5Mac", "cnBeta", "IT之家"},
        )
        self.assertNotIn(privacy_commentary, health_event.articles)

    def test_legal_counterparty_extraction_ignores_generic_words_and_chip_models(self):
        module = load_module()

        facets = module.legal_case_counterparty_facets(
            "New lawsuit alleges unpatchable Apple A12 and A13 chip exploit used stolen trade secrets"
        )

        self.assertNotIn("legal-counterparty-new", facets)
        self.assertNotIn("legal-counterparty-a12", facets)
        self.assertNotIn("legal-counterparty-a13", facets)

    def test_exact_first_party_program_identity_overrides_event_kind_variation(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Upgrade launches in the United States",
                "Apple launched its Upgrade device-leasing program for iPhone, iPad, Mac, and Apple Watch.",
                "Apple Newsroom",
            ),
            article_for(
                module,
                "Apple Upgrade leasing program launches for iPhone, Mac, iPad, and Apple Watch",
                "Apple's new Klarna-backed leasing plan is now live in the United States.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果推出硬件租赁服务 Apple Upgrade，覆盖 Mac、iPad 等全线产品",
                "Apple Upgrade 已在美国上线，用户可按月租用苹果设备。",
                "cnBeta",
            ),
        ]
        articles[0].event_kind = "hardware_market"
        articles[1].event_kind = "retail_store"
        articles[2].event_kind = "hardware_market"

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_named_service_trailer_merges_without_absorbing_executive_interview(self):
        module = load_module()
        trailer_sources = [
            article_for(
                module,
                "Apple unveils Ted Lasso season 4 trailer, series returns next week",
                "Apple TV released the Ted Lasso season 4 trailer ahead of its August premiere, which Tim Cook and John Ternus attended.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple Shares Ted Lasso Season 4 Trailer",
                "Apple shared the first trailer for Ted Lasso season 4.",
                "MacRumors",
            ),
            article_for(
                module,
                "Back to Richmond in season 4, Ted Lasso changes the playbook",
                "Apple TV released a new Ted Lasso season 4 trailer.",
                "AppleInsider",
            ),
        ]
        interview = article_for(
            module,
            "Tim Cook, John Ternus talk Apple CEO transition and more in new interview",
            "The Apple executives discussed leadership succession and the future of Apple TV at the Ted Lasso season 4 premiere.",
            "9to5Mac",
        )

        events = module.cluster_articles([*trailer_sources, interview])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset(article.title for article in trailer_sources), event_partitions(events))
        self.assertIn(frozenset({interview.title}), event_partitions(events))

    def test_smart_home_roadmap_article_projects_distinct_product_actions(self):
        module = load_module()
        title = "Apple has three new smart home products nearly ready to launch"
        facts = [
            "Apple TV and HomePod mini refreshes are nearly ready for launch this fall.",
            "A separate seven-inch Apple home hub with Siri AI is planned for late 2026 or early 2027.",
            "Apple is also developing a later smart-home security camera.",
        ]

        variants = module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(len(variants), 2, variants)
        identities = [module.title_led_identity(item_title, item_summary) for item_title, item_summary, _ in variants]
        self.assertTrue(any(identity.title_products & {"apple-tv", "homepod"} for identity in identities))
        self.assertTrue(any("apple-home-hub" in identity.title_products for identity in identities))

    def test_projected_and_localized_home_hub_reports_stay_strong_and_merge(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple home hub and smart-home accessories roadmap",
                "Apple's home hub is nearly ready to launch between October and early next year, followed by a robotic version and an in-home security camera.",
                "9to5Mac",
            ),
            article_for(
                module,
                "消息称苹果智能家居中枢将搭载全新 Siri AI，将于今秋至明年初发布",
                "苹果计划推出 7 英寸家庭中枢，运行基于 tvOS 的系统，并支持 FaceTime、HomeKit 和安防监控。",
                "IT之家",
            ),
            article_for(
                module,
                "全新 Siri AI 加持！苹果首款 7 英寸家庭中枢曝光，支持人脸识别",
                "苹果家庭中枢最快 10 月推出，提供桌面和磁吸壁挂形态，并运行基于 tvOS 定制的系统。",
                "快科技",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))
        self.assertTrue(all(article.category == "hardware_products" for article in articles))
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_cohesive_first_party_program_and_global_valuation_do_not_warn_as_mixed(self):
        module = load_module()
        program_articles = [
            article_for(
                module,
                "Apple Upgrade launches in the United States",
                "Apple launched its first-party leasing program for iPhone, iPad, Mac, and Apple Watch with Klarna.",
                "Apple Newsroom",
            ),
            article_for(
                module,
                "Apple Upgrade pricing starts at $18 per month for iPhone",
                "The same Apple leasing program lists monthly terms and replaces the iPhone Upgrade Program.",
                "MacRumors",
            ),
        ]
        program_articles[1].event_kind = "hardware_market"
        valuation_articles = [
            article_for(
                module,
                "Apple just hit $5 trillion market cap for first time",
                "Apple became the second company to cross the global valuation milestone.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果市值首次触及 5 万亿美元",
                "苹果股价上涨并达到这一全球估值里程碑。",
                "IT之家",
            ),
        ]
        valuation_articles[0].regions = {"united-states"}
        valuation_articles[1].regions = {"china"}

        self.assertNotIn("mixed event kinds", module.event_merge_warnings(program_articles))
        self.assertNotIn("mixed primary topic facets", module.event_merge_warnings(program_articles))
        self.assertNotIn("multiple region-specific markers", module.event_merge_warnings(valuation_articles))

    def test_current_direct_apple_actions_are_not_demoted_by_background_terms(self):
        module = load_module()
        cases = [
            (
                "AppleCare+ Changes Introduced in Canada",
                "Monthly and annual AppleCare+ subscriptions are now available for iPhone, iPad, Mac, Apple Watch, Apple TV, AirPods, HomePod, Studio Display, and Vision Pro in Canada; coverage starts at $0.99 per month for some accessories.",
                "MacRumors",
                "strong",
                "service_content",
                "software_systems",
            ),
            (
                "苹果操作系统更新首次致谢 AI 安全研究",
                "Apple 在 iOS、iPadOS 和 macOS 安全公告中首次致谢 Anthropic、OpenAI、NVIDIA 与 Z.ai 使用 AI 发现漏洞的研究团队，并发布了对应修复。",
                "cnBeta",
                "strong",
                "security_privacy",
                "software_systems",
            ),
            (
                "苹果 AI 眼镜明年 WWDC 见，但这次隐私不好做",
                "彭博社称 Apple 计划在 WWDC 2027 发布智能眼镜，年底上市，并正处理硬件隐私设计问题。",
                "爱范儿",
                "strong",
                "hardware_market",
                "hardware_products",
            ),
            (
                "Apple says iOS 27 Restricted Mode isn't for new Upgrade program leases",
                "Apple clarified that the native iOS 27 Restricted Mode is not used for missed Apple Upgrade lease payments.",
                "9to5Mac",
                "strong",
                "os_app",
                "software_systems",
            ),
        ]
        for title, summary, source, tier, kind, category in cases:
            with self.subTest(title=title):
                actual_tier, reason = module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(actual_tier, tier, reason)
                self.assertEqual(module.detect_event_kind(title, summary), kind)
                self.assertEqual(module.choose_category(title, summary), category)

    def test_third_party_app_and_editorial_upgrade_framing_stay_weak(self):
        module = load_module()
        cases = [
            (
                "Apple Watch just gained a brand-new app for AI meeting notes",
                "Granola, the AI-powered meeting notepad best known for its Mac app, is expanding to Apple Watch today. The launch comes as watchOS 27 introduces Siri AI, but Granola for Apple Watch is the newly available app.",
            ),
            (
                "iOS 27's Siri gets one thing very right that other AI assistants get wrong",
                "The author shares a personal assessment of an already released Siri behavior and reports no new Apple action.",
            ),
            (
                "iPhone 18 Pro could be a no-brainer upgrade for lots of users",
                "The article recaps previously reported iPhone 18 Pro rumors as purchase advice and contains no new reporting.",
            ),
        ]
        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = module.classify_relevance_tier(title, summary, [], "9to5Mac")
                self.assertEqual(tier, "weak", reason)

    def test_direct_executive_strategy_statements_merge_across_headline_angles(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Ternus says he plans to build on the success of Apple TV",
                "Incoming Apple CEO John Ternus directly said he plans to continue growing Apple's entertainment business.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Apple TV may be losing $1B a year but its future is safe under Ternus",
                "In a Reuters interview, incoming Apple CEO John Ternus said Apple will build on Apple TV's success.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果候任 CEO 特努斯：上任后将继续推动娱乐业务增长",
                "特努斯在采访中直接表示，接任苹果 CEO 后会继续发展 Apple TV 与娱乐业务。",
                "IT之家",
            ),
        ]
        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_market_cap_wording_variants_merge_as_one_company_value_event(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Just Became a $5 Trillion Company",
                "Apple's market capitalization crossed $5 trillion for the first time.",
                "MacRumors",
            ),
            article_for(
                module,
                "Strong iPhone demand turns Apple's rebound into a $5 trillion run",
                "Apple shares reached a record and the company passed a $5 trillion market valuation.",
                "AppleInsider",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))

    def test_first_party_service_and_home_hardware_titles_resist_body_product_bridges(self):
        module = load_module()
        applecare = article_for(
            module,
            "AppleCare+ Changes Introduced in Canada",
            "Monthly and annual AppleCare+ plans now cover Apple TV, HomePod, AirPods, Mac, and other devices.",
            "MacRumors",
        )
        apple_tv = article_for(
            module,
            "New Apple TV and HomePod mini are nearly ready to launch",
            "Apple plans faster Apple TV and HomePod mini hardware this fall.",
            "9to5Mac",
        )
        home_hub = article_for(
            module,
            "消息称苹果智能家居中枢将搭载全新 Siri AI，将于今秋至明年初发布",
            "苹果家庭中枢配备 7 英寸屏幕并支持人脸识别。",
            "IT之家",
        )
        macbook = article_for(
            module,
            "Apple's redesigned MacBook Pro gains a 14-inch OLED touch display",
            "Samsung will supply the MacBook Pro OLED panel.",
            "AppleInsider",
        )

        events = module.cluster_articles([applecare, apple_tv, home_hub, macbook])

        self.assertEqual(len(events), 4, event_partitions(events))

    def test_negated_restricted_mode_clarification_keeps_all_direct_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple says iOS 27 Restricted Mode isn't for new Upgrade program leases",
                "Apple clarified that Restricted Mode will not be used after missed lease payments.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple won't turn on any Restricted Mode for missed lease payments",
                "Apple says its device-leasing plan will not activate the iOS restriction feature.",
                "The Verge",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        self.assertTrue(all(article.category == "software_systems" for article in articles))
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_market_cap_reach_wording_merges_with_company_milestone(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple just hit $5 trillion market cap for first time",
                "Apple became the second company to cross the valuation milestone.",
                "9to5Mac",
            ),
            article_for(
                module,
                "苹果市值首次触及 5 万亿美元",
                "苹果股价上涨并达到这一历史估值里程碑。",
                "cnBeta",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_same_macbook_oled_supplier_report_merges_without_absorbing_spec_roundup(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "MacBook Ultra OLED Touch Panel to Be Exclusively Supplied by Samsung",
                "Samsung Display will be the sole supplier of OLED touch panels for Apple's redesigned MacBook Pro.",
                "MacRumors",
            ),
            article_for(
                module,
                "6 Display Upgrades Coming With Apple's Redesigned MacBook Pro",
                "The same Samsung OLED touch-panel report lists tandem OLED, oxide TFT, integrated touch, and 1Hz to 120Hz refresh.",
                "MacRumors",
            ),
            article_for(
                module,
                "OLED MacBook Pro will get displays exclusively from Samsung",
                "Samsung Display will exclusively supply about 2.5 million OLED touch panels for the redesigned MacBook Pro.",
                "AppleInsider",
            ),
            article_for(
                module,
                "放弃 Mini-LED，苹果 MacBook 拥抱 OLED：三星拿到独家供货资格",
                "三星显示将独家供应苹果新款 MacBook Pro OLED 触控面板。",
                "快科技",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 2, event_partitions(events))
        supplier_titles = {
            articles[0].title,
            articles[2].title,
            articles[3].title,
        }
        self.assertIn(frozenset(supplier_titles), event_partitions(events))
        self.assertIn(frozenset({articles[1].title}), event_partitions(events))

    def test_negated_restricted_mode_clarification_merges_with_localized_projection(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple says iOS 27 Restricted Mode isn't for new Upgrade program leases",
                "Apple clarified that missed Apple Upgrade lease payments will not activate Restricted Mode.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple financed-device restricted mode",
                "苹果证实 Apple Upgrade 逾期不会启用 iOS 27 受限模式。",
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        variants = module.compound_article_variants(
            "苹果确认 Apple Upgrade 逾期不会启用 iOS 27 受限模式",
            "苹果表示，Apple Upgrade 用户即使逾期也不会触发 Restricted Mode。",
            ["苹果未说明 iOS 27 中这套受限模式的最终用途。"],
        )
        self.assertEqual(len(variants), 1, variants)

    def test_new_analyst_target_action_is_not_treated_as_unchanged_opinion(self):
        module = load_module()
        title = "Goldman Sachs raises AAPL target to $370 ahead of Q3 results"
        summary = "Goldman Sachs increased its Apple price target from $340 to $370 in a new investor note."

        article = article_for(module, title, summary, "AppleInsider")

        self.assertEqual(article.relevance_tier, "strong", article.relevance_reason)
        self.assertEqual(module.primary_topic_facets(title, summary), {"apple-analyst-rating-target"})


    def test_multi_feature_os_summary_does_not_absorb_specific_app_story(self):
        module = load_module()
        summary = article_for(
            module,
            "iOS 27 adds three new iPhone features you'll use all the time",
            "The report covers Siri AI, automatic proofreading, and search changes in Spotlight, Photos, and Mail.",
            "9to5Mac",
        )
        maps = article_for(
            module,
            "Apple Maps in iOS 27 expands Suggested Places",
            "Apple Maps now lets users scroll through more Suggested Places recommendations.",
            "MacRumors",
        )

        self.assertEqual(module.title_led_identity(summary.title, summary.summary).content_form, "roundup")
        self.assertEqual(len(module.cluster_articles([summary, maps])), 2)

    def test_os_performance_does_not_merge_with_modem_revenue_story(self):
        module = load_module()
        performance = article_for(
            module,
            "iOS 27 Speeds Up the iPhone You Already Own: Here's How",
            "Apple says iOS 27 makes app launches up to 30 percent faster and AirDrop transfers up to 80 percent quicker.",
            "MacRumors",
        )
        modem = article_for(
            module,
            "Qualcomm Expects Apple Modem Revenue to Drop Faster Than Expected",
            "Qualcomm expects Apple revenue to decline as its next-iPhone component share falls below 20 percent.",
            "MacRumors",
        )

        self.assertEqual(len(module.cluster_articles([performance, modem])), 2)

    def test_generic_executive_word_does_not_bridge_distinct_supplier_actions(self):
        module = load_module()
        modem = article_for(
            module,
            "Qualcomm says supply constraints are shrinking its Apple business",
            "Qualcomm CEO said supply constraints will cause its Apple revenue to decline faster and reduce its share below 20 percent.",
            "9to5Mac",
        )
        memory = article_for(
            module,
            "Apple faces pushback over plans to buy Chinese memory chips",
            "Apple CEO Tim Cook is navigating a memory shortage while senators demand that Apple avoid supply from CXMT and YMTC.",
            "9to5Mac",
        )

        self.assertEqual(len(module.cluster_articles([modem, memory])), 2)

    def test_exact_same_action_facets_merge_across_headline_specificity(self):
        module = load_module()
        cases = [
            [
                article_for(
                    module,
                    "Apple Says UK App Store Steering Rules Would Be Highly Intrusive",
                    "Apple objected to the UK CMA proposal on external App Store payment links and commissions.",
                    "MacRumors",
                ),
                article_for(
                    module,
                    "英国 CMA 要求苹果 App Store 开放外链支付，苹果强烈反对",
                    "英国竞争与市场管理局拟限制佣金并开放第三方支付链接。",
                    "IT之家",
                ),
                article_for(
                    module,
                    "Apple pushes back against UK proposal to loosen App Store rules",
                    "Apple formally opposed the same CMA proposal on App Store fees and payment links.",
                    "9to5Mac",
                ),
            ],
            [
                article_for(
                    module,
                    "Apple One Premier gains two new iOS 27 perks",
                    "Paid iCloud+ plans gain higher Apple Intelligence limits and HomeKit Secure Video benefits.",
                    "9to5Mac",
                ),
                article_for(
                    module,
                    "iPhone Users Who Pay for iCloud Storage Get Two New iOS 27 Perks",
                    "Apple says paid iCloud+ plans gain higher AI limits and new HomeKit Secure Video benefits.",
                    "MacRumors",
                ),
            ],
            [
                article_for(
                    module,
                    "Apple Begins Selling Refurbished Studio Display XDR",
                    "Apple added Studio Display XDR to its Certified Refurbished store.",
                    "MacRumors",
                ),
                article_for(
                    module,
                    "苹果首次上架翻新 Studio Display XDR，八五折起",
                    "苹果认证翻新商店现已销售 Studio Display XDR。",
                    "IT之家",
                ),
                article_for(
                    module,
                    "Studio Display XDR hits Apple's refurb store, saving you up to $540",
                    "Apple started selling the display through its Certified Refurbished store.",
                    "9to5Mac",
                ),
            ],
        ]

        for articles in cases:
            with self.subTest(titles=[article.title for article in articles]):
                self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
                events = module.cluster_articles(articles)
                self.assertEqual(len(events), 1, event_partitions(events))

    def test_apple_upgrade_headline_variants_share_program_identity(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Upgrade is a really great deal for one reason",
                "Apple's new device leasing program covers iPhone, iPad, Mac, and Apple Watch.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Apple's New Upgrade Program: Is It Worth It?",
                "Apple launched the same Upgrade leasing program with Klarna in the United States.",
                "MacRumors",
            ),
        ]

        events = module.cluster_articles(articles)
        self.assertEqual(len(events), 1, event_partitions(events))

    def test_same_named_supplier_commercial_outlook_merges_across_sources(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Qualcomm says supply constraints are shrinking its Apple business",
                "Qualcomm CEO said Apple revenue will decline faster as its next-iPhone component share falls below 20 percent.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Qualcomm Expects Apple Modem Revenue to Drop Faster Than Expected",
                "Qualcomm expects the Apple revenue decline to start in the fourth quarter because of supply constraints.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple's reliance on Qualcomm could decline faster than expected",
                "Qualcomm says its component share in the next iPhone will fall below the earlier 20 percent estimate.",
                "AppleInsider",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_supplier_commercial_outlook_does_not_absorb_market_share_or_procurement(self):
        module = load_module()
        outlook = [
            article_for(
                module,
                "Qualcomm expects Apple modem revenue to drop faster than expected",
                "Its component share in the next iPhone will fall well below the earlier 20 percent estimate.",
                "MacRumors",
            ),
            article_for(
                module,
                "高通预估苹果调制解调器业务收入下滑速度超出预期",
                "高通称供应约束将令其下一代 iPhone 组件份额低于此前预计的 20%。",
                "cnBeta",
            ),
            article_for(
                module,
                "高通财报预警：苹果业务加速流失",
                "高通表示苹果相关收入将在第四季度更快下降。",
                "IT之家",
            ),
        ]
        market_share = article_for(
            module,
            "iPhone sales keep rising in China even as market declines",
            "CAICT says Apple's June iPhone shipments rose in China while the total market fell.",
            "AppleInsider",
        )
        procurement = article_for(
            module,
            "Apple faces pushback over plans to buy Chinese memory chips",
            "Senators urged Apple not to source memory from CXMT or YMTC.",
            "9to5Mac",
        )

        self.assertTrue(
            all(
                module.primary_topic_facets(article.title, article.summary)
                == {"apple-supplier-commercial-outlook"}
                for article in outlook
            )
        )
        events = module.cluster_articles([*outlook, market_share, procurement])
        self.assertEqual(len(events), 3, event_partitions(events))
        self.assertIn(frozenset(article.title for article in outlook), event_partitions(events))

    def test_region_scoped_exact_action_ignores_incidental_background_regions(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple Says UK App Store Steering Rules Would Be Highly Intrusive",
                "Apple opposed the UK CMA proposal and compared it with EU and US rules.",
                "MacRumors",
            ),
            article_for(
                module,
                "Apple pushes back against UK proposal to loosen App Store rules",
                "Apple filed its response to the same UK CMA consultation.",
                "9to5Mac",
            ),
        ]
        articles[0].regions = {"united-kingdom", "europe", "united-states", "multi-region"}
        articles[1].regions = {"united-kingdom", "multi-region"}

        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_restricted_memory_supplier_pushback_is_one_cross_region_action(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple faces pushback over plans to buy Chinese memory chips",
                "US senators urged Apple to commit by August 21 not to use CXMT or YMTC memory chips from China.",
                "9to5Mac",
            ),
            article_for(
                module,
                "多名美国参议员联名施压苹果，要求放弃采用中国制造存储芯片计划",
                "美国参议员反对苹果采购中国长鑫存储和长江存储芯片，并要求苹果在 8 月 21 日前承诺。",
                "cnBeta",
            ),
        ]
        articles[0].regions = {"china", "united-states", "multi-region"}
        articles[1].regions = {"china", "united-states", "multi-region"}

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual(events[0].merge_warnings, [])

    def test_memory_chip_procurement_is_not_an_ai_company_acquisition(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple faces pushback over plans to buy Chinese memory chips",
                "US senators urged Apple not to use memory chips from CXMT or YMTC during the AI-driven shortage.",
                "9to5Mac",
            ),
            article_for(
                module,
                "US senators urge Apple to abandon plans for Chinese-made chips",
                "During the global memory shortage, Apple requested to buy chips from CXMT and previously purchased YMTC chips for possible use in China products. The senators asked Apple to reconsider chips from either company.",
                "AppleInsider",
            ),
        ]

        self.assertTrue(
            all("apple-memory-supplier-sourcing" in module.article_primary_facets(article) for article in articles)
        )
        self.assertTrue(
            all("apple-ai-chip-acquisition" not in module.article_primary_facets(article) for article in articles)
        )
        self.assertEqual(len(module.cluster_articles(articles)), 1, event_partitions(module.cluster_articles(articles)))

    def test_analyst_target_actions_require_the_same_named_institution(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "JP Morgan lowers Apple price target to $340 on supply constraints",
                "The investment bank kept its Overweight rating after Apple's earnings call.",
                "AppleInsider",
            ),
            article_for(
                module,
                "担忧供应链短缺，摩根大通将苹果目标价下调至 340 美元",
                "摩根大通维持增持评级，并将目标价从 345 美元降至 340 美元。",
                "IT之家",
            ),
            article_for(
                module,
                "Services slowdown pushes Morgan Stanley's Apple target down to $360",
                "Morgan Stanley kept its Overweight rating while lowering the target from $364.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Rosenblatt hikes AAPL target to $300 after earnings",
                "Rosenblatt retained its Neutral rating and raised the target by $24.",
                "9to5Mac",
            ),
            article_for(
                module,
                "Goldman Sachs lowers AAPL target to $360 after earnings call",
                "Goldman Sachs cut its target from $370 while remaining positive on Apple.",
                "MacRumors",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 4, event_partitions(events))
        self.assertIn(
            frozenset({articles[0].title, articles[1].title}),
            event_partitions(events),
        )

    def test_iphone_roadmap_models_do_not_bridge_through_shared_generation(self):
        module = load_module()
        air_en = article_for(
            module,
            "iPhone Air 2 Expected to Launch Early Next Year With Five New Features",
            "Jeff Pu expects a second 48MP camera, A20 Pro, N2, C2 and 12GB RAM in early 2027.",
            "MacRumors",
        )
        air_zh = article_for(
            module,
            "蒲得宇预估苹果 2027Q1 发布 iPhone Air 2：新增 4800 万超广角、A20 Pro 芯片",
            "研报称 iPhone Air 2 将升级双摄、A20 Pro、N2 和 C2 芯片。",
            "IT之家",
        )
        budget = article_for(
            module,
            "iPhone 18e Rumored to Feature Increased RAM",
            "The lower-end iPhone 18e is expected to use 9GB of RAM in March 2027.",
            "MacRumors",
        )
        base = article_for(
            module,
            "iPhone 18 rumors: Smaller Dynamic Island, 12GB or 9GB RAM",
            "Apple's base iPhone 18 may use 12GB or 9GB RAM and launch in spring 2027.",
            "AppleInsider",
        )

        events = module.cluster_articles([air_en, budget, base, air_zh])

        self.assertEqual(len(events), 3, event_partitions(events))
        self.assertIn(frozenset({air_en.title, air_zh.title}), event_partitions(events))

    def test_specific_iphone_variants_do_not_merge_through_generation_or_price(self):
        module = load_module()
        pro = article_for(
            module,
            "iPhone 18 Pro Models Could Be Up to $300 More Expensive, Says Analyst",
            "The iPhone 18 Pro and Pro Max may start at $1,399 after memory prices rise.",
            "MacRumors",
        )
        budget = article_for(
            module,
            "iPhone 18e Rumored to Feature Increased RAM",
            "The lower-end iPhone 18e is expected to use 9GB of RAM.",
            "MacRumors",
        )
        pro_zh = article_for(
            module,
            "苹果 iPhone 18 Pro系列售价或上调 300 美元",
            "同一份研报预计 iPhone 18 Pro 和 Pro Max 将因内存成本涨价。",
            "IT之家",
        )

        events = module.cluster_articles([pro, budget, pro_zh])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(frozenset({pro.title, pro_zh.title}), event_partitions(events))

    def test_same_future_iphone_price_report_consolidates_partial_source_clusters(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro Models Could Be Up to $300 More Expensive, Says Analyst",
                "Jeff Pu expects iPhone 18 Pro pricing to rise by $250 to $300.",
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro may launch at $1,399 starting price",
                "The same Jeff Pu report attributes the increase to memory and chip costs.",
                "9to5Mac",
            ),
            article_for(
                module,
                "蒲得宇：苹果 iPhone 18 Pro / Max 恐涨价 250~300 美元",
                "蒲得宇预计芯片和内存成本将推高 Pro 系列售价。",
                "IT之家",
            ),
            article_for(
                module,
                "消息称 iPhone 18 Pro系列售价最高或上涨 300 美元",
                "同一份研报预计起售价可能达到 1399 美元。",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_analyst_target_action_does_not_merge_with_earnings_or_stock_recap(self):
        module = load_module()
        target = article_for(
            module,
            "担忧供应链短缺问题，摩根大通将苹果目标股价下调至 340 美元",
            "摩根大通维持增持评级，并将苹果目标股价从 345 美元下调至 340 美元。",
            "IT之家",
        )
        earnings = article_for(
            module,
            "库克最后一次苹果财报会太意外！业绩全线飘红，盘后股价大跌 8%",
            "苹果公布季度营收并讨论供应限制，盘后股价下跌。",
            "快科技",
        )

        self.assertEqual(len(module.cluster_articles([target, earnings])), 2)

    def test_analyst_target_without_literal_target_word_stays_out_of_product_rumor(self):
        module = load_module()
        rating = article_for(
            module,
            "Rosenblatt hikes AAPL to $300 on expected iPhone 18 demand, still underwater",
            "Rosenblatt raised its Apple price target but retained a Neutral rating.",
            "AppleInsider",
        )
        roadmap = article_for(
            module,
            "iPhone 18 rumors: Smaller Dynamic Island, 12GB or 9GB RAM",
            "Apple's base iPhone 18 may change the Dynamic Island and memory configuration.",
            "MacRumors",
        )

        self.assertEqual(len(module.cluster_articles([rating, roadmap])), 2)

    def test_title_primary_intent_separates_market_retrospective_and_capital_strategy(self):
        module = load_module()
        market_move = article_for(
            module,
            "苹果市值一夜蒸发超 3000 亿美元，盘后股价大跌 8%",
            "苹果发布季度业绩后股价下跌。",
            "快科技",
        )
        retrospective = article_for(
            module,
            "库克 15 年 CEO 任期收官：苹果市值增长超 10 倍",
            "报道回顾库克任内苹果产品和市值变化。",
            "快科技",
        )
        capital_strategy = article_for(
            module,
            "大型科技企业加码 AI，苹果坚持较低资本开支策略",
            "苹果没有跟随同行大幅增加 AI 基础设施投资。",
            "cnBeta",
        )

        self.assertEqual(
            len(module.cluster_articles([market_move, retrospective, capital_strategy])),
            3,
        )

    def test_same_executive_tenure_retrospective_merges_across_languages(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "How Apple Changed Under Tim Cook: 15 Years in Numbers",
                (
                    "Tim Cook joined his final Apple earnings call before John Ternus takes over on "
                    "September 1. The report compares Apple's 2011 and 2026 revenue, devices, services, "
                    "subscriptions, and shareholder returns across Cook's 15-year tenure."
                ),
                "MacRumors",
            ),
            article_for(
                module,
                "用数字回顾蒂姆・库克掌舵苹果的十五年历程",
                (
                    "库克参加任内最后一次苹果财报电话会议，约翰・特努斯将在 9 月 1 日接任。"
                    "报道对比库克掌舵十五年来苹果的营收、设备、服务、订阅及股东回报。"
                ),
                "IT之家",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))
        self.assertEqual({article.source for article in events[0].articles}, {"MacRumors", "IT之家"})
        self.assertTrue(all(article.event_kind == "company_org" for article in articles))
        self.assertEqual(events[0].event_kind, "company_org")
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual(events[0].merge_warnings, [])

    def test_executive_retrospectives_with_different_subject_or_tenure_stay_separate(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "How Apple Changed Under Tim Cook: 15 Years in Numbers",
                "A data retrospective covers Tim Cook's 15-year tenure as Apple CEO.",
                "MacRumors",
            ),
            article_for(
                module,
                "John Ternus: Five Years Leading Apple's Hardware Organization",
                "A separate retrospective covers John Ternus and five years of hardware leadership.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Tim Cook at Apple: A 10-Year Retrospective",
                "An older retrospective covers the first 10 years of Tim Cook's tenure.",
                "9to5Mac",
            ),
        ]

        self.assertEqual(len(module.cluster_articles(articles)), 3)

    def test_title_primary_intent_separates_policy_price_and_constraint_domains(self):
        module = load_module()
        memory_policy = article_for(
            module,
            "美国议员要求苹果承诺不采用中国存储芯片",
            "议员要求苹果只从获准供应商采购 iPhone 存储芯片。",
            "IT之家",
        )
        price = article_for(
            module,
            "iPhone 18 Pro 或因芯片和内存成本上涨 300 美元",
            "研报预测下一代 Pro 机型售价上调。",
            "MacRumors",
        )
        product_supply = article_for(
            module,
            "苹果预计本季度将遭遇严重产品供货紧张",
            "苹果称多条硬件产品线将受供应约束。",
            "cnBeta",
        )
        compute_risk = article_for(
            module,
            "苹果警告 AI 算力资源短缺或导致服务延迟",
            "公司在风险披露中提到数据中心算力容量不足。",
            "cnBeta",
        )

        self.assertEqual(
            len(module.cluster_articles([memory_policy, price, product_supply, compute_risk])),
            4,
        )

    def test_market_share_product_sales_and_supply_constraint_are_distinct_actions(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Apple hit a record 49% share of global smartphone revenue for Q2",
                "Counterpoint measured Apple's record revenue share and 21% shipment share.",
                "9to5Mac",
            ),
            article_for(
                module,
                "MacBook Neo becomes Apple's best-selling notebook",
                "Apple said the affordable MacBook Neo became its best-selling notebook this quarter.",
                "快科技",
            ),
            article_for(
                module,
                "Apple expects severe product supply constraints this quarter",
                "Apple warned that advanced chip shortages will constrain Mac, iPhone and iPad output.",
                "cnBeta",
            ),
        ]

        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 3, event_partitions(events))

    def test_title_supply_constraint_resists_market_share_background_bridge(self):
        module = load_module()
        market = article_for(
            module,
            "Apple hit a record 49% share of global smartphone revenue for Q2",
            "Counterpoint measured Apple's record revenue share and 23% shipment share.",
            "9to5Mac",
        )
        supply = article_for(
            module,
            "苹果预计本季度将遭遇严重供货紧张",
            "苹果警告先进芯片短缺将限制 Mac、iPhone 和 iPad 供货。财报背景还提到 iPhone 营收增长与全球手机份额。",
            "cnBeta",
            facts=[
                "Counterpoint 的另一份市场报告称苹果占全球智能手机营收近一半。",
            ],
        )

        self.assertIn("primary-intent:product-supply-constraint", module.article_title_led_event_identity(supply).title_components)
        self.assertNotIn("apple-market-share-report", module.article_primary_facets(supply))
        self.assertEqual(len(module.cluster_articles([market, supply])), 2)

    def test_named_product_sales_performance_resists_broad_market_background(self):
        module = load_module()
        market = article_for(
            module,
            "Apple hit a record 49% share of global smartphone revenue for Q2",
            "Counterpoint measured Apple's global smartphone revenue and shipment share.",
            "9to5Mac",
        )
        product_sales = article_for(
            module,
            "苹果新任 CEO 操刀打造，MacBook Neo 成为苹果最畅销笔记本",
            "MacBook Neo 本季度成为苹果销量最高的笔记本。同期行业报告还讨论了苹果的全球手机份额。",
            "快科技",
            facts=["Counterpoint 另称苹果占全球智能手机营收近一半。"],
        )

        identity = module.article_title_led_event_identity(product_sales)
        self.assertIn("hardware-market-performance", identity.title_components)
        self.assertIn("apple-product-sales-performance", module.article_primary_facets(product_sales))
        self.assertNotIn("apple-market-share-report", module.article_primary_facets(product_sales))
        self.assertEqual(len(module.cluster_articles([market, product_sales])), 2)

    def test_apple_financial_results_resist_market_share_background_bridge(self):
        module = load_module()
        market = article_for(
            module,
            "Apple hit a record 49% share of global smartphone revenue for Q2",
            "Counterpoint measured Apple's global smartphone revenue and shipment share.",
            "9to5Mac",
        )
        earnings = article_for(
            module,
            "库克最后一舞：苹果连续四个季度营收突破 1000 亿美元",
            "苹果公布季度业绩和经营指引。背景还引用 Counterpoint 的全球手机营收份额数据。",
            "快科技",
            facts=["苹果本财季总营收、净利润和毛利率均同比增长。"],
        )
        stock_reaction = article_for(
            module,
            "苹果股价因下一财季业绩指引不及预期而重挫 9%",
            "苹果公布季度业绩后，投资者担忧下一季度指引，盘后市值大幅下跌。",
            "cnBeta",
        )

        self.assertIn("apple-financial-results", module.article_primary_facets(earnings))
        self.assertNotIn("apple-market-share-report", module.article_primary_facets(earnings))
        self.assertNotIn("apple-financial-results", module.article_primary_facets(stock_reaction))
        self.assertEqual(earnings.event_kind, "general_company")
        self.assertEqual(len(module.cluster_articles([market, earnings, stock_reaction])), 3)

    def test_non_apple_comparison_cannot_join_direct_product_roadmap(self):
        module = load_module()
        apple = article_for(
            module,
            "iPhone Air 2 to feature smaller Dynamic Island and dual cameras",
            "Apple is expected to release iPhone Air 2 with a smaller Dynamic Island in 2027.",
            "9to5Mac",
        )
        competitor = article_for(
            module,
            "REDMI K100 Pro Max debuts with 6.9-inch display and red finish",
            "The Android phone uses a red color that resembles a rumored iPhone 18 Pro finish.",
            "快科技",
        )

        events = module.cluster_articles([apple, competitor])

        self.assertEqual(competitor.relevance_tier, "weak")
        self.assertEqual(len(events), 2, event_partitions(events))

    def test_current_service_perk_does_not_merge_with_service_history(self):
        module = load_module()
        perk = article_for(
            module,
            "2TB iCloud+ Plan to Feature Another Key Benefit With iOS 27",
            "Apple will give the 2TB iCloud+ tier higher Siri AI usage limits in iOS 27.",
            "MacRumors",
        )
        history = article_for(
            module,
            "How iTools became iCloud",
            "Before iCloud became the backbone of the Apple ecosystem, it spent more than a decade evolving through iTools, .Mac, and MobileMe.",
            "AppleInsider",
        )

        events = module.cluster_articles([perk, history])

        self.assertEqual(history.relevance_tier, "weak", history.relevance_reason)
        self.assertEqual(len(events), 2, event_partitions(events))

    def test_first_party_platform_and_owned_brand_actions_override_body_comparisons(self):
        module = load_module()
        cases = [
            (
                "Shazam launches its first ever sticker pack for a new album",
                "The Apple-owned Shazam app announced an Artist Sticker Pack in its latest app update.",
                "9to5Mac",
            ),
            (
                "iOS 27 Features CarPlay Video Mode",
                "Apple is allowing developers to create CarPlay video apps for parked vehicles; automakers must support the platform.",
                "MacRumors",
            ),
            (
                "Inside Beats lab: Outside Apple because AirPods can't do everything well",
                "Apple has spent 12 years strengthening Beats as a separate brand. Executives say it combines its culture with Apple's engineering resources and was developed to complement AirPods as a dual-ecosystem product line.",
                "AppleInsider",
            ),
            (
                "Another major car brand is preparing to support Apple Car Keys",
                "Apple Wallet code shows Haval preparing support for Car Key on iPhone and Apple Watch.",
                "9to5Mac",
            ),
        ]

        articles = [article_for(module, *case) for case in cases]

        self.assertTrue(
            all(article.relevance_tier in {"strong", "ecosystem"} for article in articles),
            [(article.title, article.relevance_tier, article.relevance_reason) for article in articles],
        )
        self.assertEqual(articles[1].event_kind, "os_app")
        self.assertEqual(articles[2].category, "hardware_products")

    def test_same_attributed_specific_iphone_report_merges_across_language_and_detail_focus(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone Air 2 Expected to Launch Early Next Year With Five New Features",
                "In a new investor note, analyst Jeff Pu says iPhone Air 2 will launch in early 2027 with a 48-megapixel Ultra Wide camera, A20 Pro, N2, and C2 chips.",
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone Air 2 to feature smaller Dynamic Island, more: report",
                "In the same investor note seen today, analyst Jeff Pu gives the iPhone Air 2 feature rundown and says it will keep a 6.55-inch display.",
                "9to5Mac",
            ),
            article_for(
                module,
                "蒲得宇预估苹果 2027Q1 发布 iPhone Air 2：新增 4800 万超广角、A20 Pro 芯片",
                "广发证券分析师蒲得宇（Jeff Pu）在最新研报中列出 iPhone Air 2 的五项变化，包括 N2 和 C2 芯片。",
                "IT之家",
            ),
        ]

        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))
        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_compact_chinese_iphone_pro_price_report_merges_with_same_analyst_report(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "iPhone 18 Pro Models Could Be Up to $300 More Expensive, Says Analyst",
                "Analyst Jeff Pu expects the iPhone 18 Pro and Pro Max to cost $250 to $300 more because of chip and memory costs.",
                "MacRumors",
            ),
            article_for(
                module,
                "消息称iPhone 18 Pro系列售价最高或上涨300美元",
                "分析师 Jeff Pu 的同一份研报预计 iPhone 18 Pro 和 Pro Max 将涨价 250 至 300 美元。",
                "cnBeta",
            ),
            article_for(
                module,
                "蒲得宇：苹果 iPhone 18 Pro / Max 恐涨价 250~300 美元",
                "广发证券分析师蒲得宇（Jeff Pu）的研报把涨价归因于 2nm 芯片、DRAM 和 NAND 成本。",
                "IT之家",
            ),
        ]

        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))
        events = module.cluster_articles(articles)

        self.assertEqual(len(events), 1, event_partitions(events))

    def test_unsourced_editorial_hardware_inference_and_user_durability_anecdote_are_weak(self):
        module = load_module()
        inferred = article_for(
            module,
            "iPad Air Could Finally Be Redesigned Next Year",
            "There is a reasonable case for a redesign, but there are no specific rumors about its design and it is only the obvious candidate if iPad mini changes first.",
            "MacRumors",
        )
        anecdote = article_for(
            module,
            "iPhone 17 Pro found pristine after surviving fall from airplane",
            "One owner accidentally dropped her phone from a plane and later found it undamaged in a field; Apple announced no product or durability change.",
            "9to5Mac",
        )
        derivative = article_for(
            module,
            "消息称苹果明年更新 iPad Air 模具，换装 OLED 屏幕",
            "据 MacRumors 报道，iPad Air 外观可能在 2027 年变化；文章没有提供独立消息源，只复述原文的编辑推演。",
            "IT之家",
        )

        self.assertEqual(inferred.relevance_tier, "weak", inferred.relevance_reason)
        self.assertEqual(anecdote.relevance_tier, "weak", anecdote.relevance_reason)
        inferred_event = module.cluster_articles([inferred, derivative])
        self.assertEqual(len(inferred_event), 1, event_partitions(inferred_event))
        self.assertEqual(inferred_event[0].relevance_tier, "weak", inferred_event[0].relevance_reason)

    def test_owned_brand_strategy_stays_strong_after_event_metadata_refresh(self):
        module = load_module()
        beats = article_for(
            module,
            "Inside Beats lab: Outside Apple because AirPods can't do everything well",
            "Apple has spent 12 years strengthening Beats as a separate brand. Apple's vice president of hardware engineering says Beats complements AirPods and uses Apple's engineering resources and reliability testing.",
            "AppleInsider",
        )

        events = module.cluster_articles([beats])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong", events[0].relevance_reason)
        self.assertEqual(events[0].event_kind, "hardware_market")

    def test_report_attribution_in_key_facts_merges_same_model_and_action(self):
        module = load_module()
        source = article_for(
            module,
            "iPhone 18 Pro Models Could Be Up to $300 More Expensive, Says Analyst",
            "The next iPhone 18 Pro models could cost $250 to $300 more because component costs increased.",
            "MacRumors",
            facts=["According to an earnings note by analyst Jeff Pu, both Pro models could rise by $250 to $300."],
        )
        followup = article_for(
            module,
            "iPhone 18 Pro may launch at $1,399 starting price, per report",
            "The iPhone 18 Pro might cost much more than its predecessor, starting around $1,399.",
            "9to5Mac",
            facts=["Analyst Jeff Pu corroborates a roughly $300 price increase for iPhone 18 Pro."],
        )
        contextual_followup = article_for(
            module,
            "Huge $300 iPhone 18 Pro price hike rumored as chip shortage bites",
            "The same iPhone 18 Pro price forecast says silicon and memory costs could add $300.",
            "AppleInsider",
        )

        identities = [module.article_title_led_event_identity(article) for article in (source, followup)]
        self.assertTrue(
            all("report-attribution:jeff-pu" in identity.components for identity in identities)
        )
        self.assertEqual(
            len(module.cluster_articles([source, contextual_followup, followup])),
            1,
        )

    def test_specific_attributed_price_report_stays_cohesive_without_supply_bridge(self):
        module = load_module()
        report_articles = [
            article_for(
                module,
                "iPhone 18 Pro Models Could Be Up to $300 More Expensive, Says Analyst",
                "Analyst Jeff Pu expects both Pro models to rise by $250 to $300.",
                "MacRumors",
            ),
            article_for(
                module,
                "iPhone 18 Pro may launch at $1,399 starting price, per report",
                "The price may start near $1,399.",
                "9to5Mac",
                facts=["Analyst Jeff Pu corroborates a roughly $300 price increase for iPhone 18 Pro."],
            ),
            article_for(
                module,
                "蒲得宇：芯片和内存成本飙升，苹果 iPhone 18 Pro / Max 恐涨价 250~300 美元",
                "分析师蒲得宇（Jeff Pu）的研报称芯片和存储成本将推高售价。",
                "IT之家",
            ),
        ]
        industry_context = article_for(
            module,
            "苹果18涨价2000元只是开始！三星：明年内存短缺加剧 至少持续到2028年",
            "报告称即将发布的 iPhone 18 Pro 可能涨价；三星另行预测全行业内存短缺将持续到 2028 年。",
            "快科技",
        )

        events = module.cluster_articles([*report_articles, industry_context])

        self.assertEqual(len(events), 2, event_partitions(events))
        self.assertIn(
            frozenset(article.title for article in report_articles),
            event_partitions(events),
        )
        mixed = module.event_from_article_group(events[0], [*report_articles, industry_context])
        split = module.split_mixed_topic_event(mixed)
        self.assertIn(
            frozenset(article.title for article in report_articles),
            event_partitions(split),
        )

    def test_compact_chinese_iphone_air_model_preserves_generation(self):
        module = load_module()
        article = article_for(
            module,
            "苹果iPhone Air 2配置确认：2nm A20 Pro、后置双摄等5大升级",
            "分析师 Jeff Pu 在研报中称苹果计划于 2027 年第一季度发布第二代机型。",
            "快科技",
        )

        identity = module.article_title_led_event_identity(article)

        self.assertIn("iphone-model:air-2", identity.title_components)
        self.assertNotIn("iphone-line:air", identity.title_components)

    def test_colloquial_chinese_future_iphone_price_is_not_current_price_action(self):
        module = load_module()
        title = "苹果18涨价2000元只是开始！三星：明年内存短缺加剧"
        summary = "报告称即将发布的 iPhone 18 Pro 售价可能上调至少 2000 元。"

        facets = module.apple_product_price_topic_facets(f"{title} {summary}")

        self.assertIn("apple-future-product-price-forecast", facets)
        self.assertNotIn("apple-current-product-price-increase", facets)

    def test_chinese_beats_lab_followup_stays_first_party_and_merges(self):
        module = load_module()
        articles = [
            article_for(
                module,
                "Inside Beats lab: Outside Apple because AirPods can't do everything well",
                "Apple's vice president of hardware engineering says Beats complements AirPods and uses Apple's reliability and wireless testing resources.",
                "AppleInsider",
            ),
            article_for(
                module,
                "Beats 成立 20 周年 / 加入苹果 12 周年之际，其美国实验室首次向媒体开放",
                "苹果硬件工程副总裁表示 Beats 与 AirPods 互补；工程楼设有人耳实验室、五间消声室以及可靠性、无线和质量测试设备。",
                "IT之家",
            ),
        ]

        self.assertTrue(all(article.relevance_tier == "strong" for article in articles))
        self.assertTrue(all(article.event_kind == "hardware_market" for article in articles))
        self.assertEqual(len(module.cluster_articles(articles)), 1)


if __name__ == "__main__":
    unittest.main()
