import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260821_test", SCRIPT_PATH)
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
        published_utc=datetime(2026, 8, 20, tzinfo=timezone.utc),
        published_raw="2026-08-20T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class ReconcilerAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_supplier_market_result_and_factory_hiring_are_separate_actions(self):
        display_result = article_for(
            self.module,
            "Strong iPhone Sales Are Giving Samsung Display a Big OLED Boost",
            (
                "Samsung Display shipped about 120 million flexible OLED panels in the "
                "first half, up 35 percent, as strong iPhone sales lifted shipments. "
                "Demand may remain strong with iPhone 18 Pro and foldable iPhone models "
                "expected to launch in September."
            ),
            "MacRumors",
        )
        factory_hiring = article_for(
            self.module,
            "富士康为生产 iPhone 18 Pro 和苹果折叠机紧急扩招",
            (
                "富士康为 iPhone 18 Pro 和苹果折叠机量产补充工人，新员工可获 "
                "8800 元返岗奖金，提前到岗另奖 500 元，以备战 9 月新品生产。"
            ),
            "快科技",
        )

        events = self.module.cluster_articles([display_result, factory_hiring])

        self.assertEqual(len(events), 2)

    def test_different_apple_tv_titles_and_actions_stay_separate(self):
        returning_series = article_for(
            self.module,
            "Apple TV comedy Stick returns for season 2 with a new cast member",
            "Apple announced that Stick season 2 premieres November 4 and adds Rhea Seehorn.",
            "9to5Mac",
        )
        new_documentary = article_for(
            self.module,
            "The Dynasty: UConn Huskies is now available on Apple TV",
            "Apple released a three-part UConn women's basketball documentary for streaming.",
            "9to5Mac",
        )

        events = self.module.cluster_articles([returning_series, new_documentary])

        self.assertEqual(len(events), 2)

    def test_same_source_generic_apple_tv_headlines_need_shared_action_identity(self):
        returning_series = article_for(
            self.module,
            "Apple TV has beloved comedy returning soon, with Pluribus star added",
            "Stick season 2 is returning with a new cast member from Pluribus.",
            "9to5Mac",
        )
        new_documentary = article_for(
            self.module,
            "The Dynasty: UConn Huskies now available on Apple TV",
            "Apple released a three-part UConn documentary today.",
            "9to5Mac",
        )

        events = self.module.cluster_articles([returning_series, new_documentary])

        self.assertEqual(len(events), 2)

    def test_third_party_accessory_compatibility_does_not_become_apple_action(self):
        charger = article_for(
            self.module,
            "酷态科 CP6 电能充 Mini 充电器首发 79 元起：兼容安卓、iOS 设备",
            (
                "酷态科发布双 C 口 67W 充电器，针对 iPhone 17 优化，并兼容 "
                "iPhone、iPad、MacBook、AirPods 和安卓设备。"
            ),
            "快科技",
        )

        event = self.module.cluster_articles([charger])[0]

        self.assertEqual(event.relevance_tier, "weak")

    def test_third_party_app_integration_merges_but_stays_deferred(self):
        reports = [
            article_for(
                self.module,
                "ChatGPT update adds Apple Messages integration on Mac",
                "OpenAI updated ChatGPT for macOS so its app can read and send Messages with permission.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Mac 版 ChatGPT 可控制苹果信息应用",
                "OpenAI 升级其 macOS 应用，可在用户授权后读取、撰写和发送信息。",
                "IT之家",
            ),
            article_for(
                self.module,
                "ChatGPT gains iMessage support on Mac",
                "OpenAI's desktop app now integrates with Apple's Messages database.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "ChatGPT Can Now Read and Send iMessages on Mac",
                "OpenAI updated ChatGPT for Mac with Messages access.",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")
        self.assertEqual(len(events[0].articles), 4)

    def test_third_party_game_release_on_mac_stays_deferred(self):
        game = article_for(
            self.module,
            "网易《燕云十六声》Mac 原生版开放先行体验，苹果 M3 Max 稳定 120 帧",
            (
                "网易为其游戏开放 Mac 原生版先行体验，玩家可下载 1.0.0 版本；"
                "文章测试了 M3 Max 帧率，但苹果没有改变平台或产品。"
            ),
            "IT之家",
        )

        event = self.module.cluster_articles([game])[0]

        self.assertEqual(event.relevance_tier, "weak")

    def test_third_party_ios_app_version_is_not_an_ios_release_wave(self):
        app_update = article_for(
            self.module,
            "微信 iOS 版 8.0.76 最新官方正式版下载发布",
            "微信 iOS 平台迎来了 8.0.76 正式版更新。",
            "IT之家",
        )

        event = self.module.cluster_articles([app_update])[0]

        self.assertEqual(event.relevance_tier, "weak")
        self.assertIn("third-party", event.relevance_reason)

    def test_competitor_led_market_outlook_without_apple_metric_stays_deferred(self):
        market_outlook = article_for(
            self.module,
            "三星将重夺手机市场领先地位 华为、苹果都将保持增长：其余厂商销量承压",
            (
                "Counterpoint 预测 2026 年全球智能手机总出货量下降 14.3%，"
                "三星增长 0.8%；苹果仅被概括为依靠长期锁单避免大幅下滑，"
                "没有给出独立的苹果份额、销量或出货量数据。"
            ),
            "快科技",
        )

        event = self.module.cluster_articles([market_outlook])[0]

        self.assertEqual(event.relevance_tier, "weak")

    def test_anniversary_recap_without_new_action_stays_deferred(self):
        recap = article_for(
            self.module,
            "Apple Card turns seven with big change ahead",
            (
                "The article marks the card's seventh anniversary and recaps Apple's "
                "January announcement that Chase will become issuer in 2028; it reports "
                "no new current action or detail."
            ),
            "MacRumors",
        )

        event = self.module.cluster_articles([recap])[0]

        self.assertEqual(event.relevance_tier, "weak")

    def test_measured_apple_market_results_merge_across_headline_perspectives(self):
        reports = [
            article_for(
                self.module,
                "Apple bucks global slump in smartphone shipments and sales",
                (
                    "Counterpoint reports Apple gained nine points to 34 percent in Europe "
                    "and grew 5 percent in Latin America during Q2 2026."
                ),
                "9to5Mac",
            ),
            article_for(
                self.module,
                "三星苹果欧洲手机份额并列第一，苹果份额升至 34%",
                (
                    "Counterpoint 数据显示 2026 年第二季度欧洲出货量下降 10%，"
                    "苹果份额同比增加 9 个百分点至 34%。"
                ),
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(len(events[0].articles), 2)

    def test_same_apple_music_label_policy_merges_across_wording(self):
        reports = [
            article_for(
                self.module,
                "Apple Music will soon get visible labels for AI-generated content",
                "Apple says distributors must apply AI Transparency Tags to materially AI-generated music later in 2026.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "AI content in Apple Music will soon have to be labeled",
                "Apple is making AI disclosure labels mandatory for tracks, artwork and music videos.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果收紧 Apple Music 服务，AI 生成音乐年底将强制标注",
                "苹果要求内容提供商为大量使用 AI 生成的音乐应用透明度标签。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 3)

    def test_measured_market_reports_for_different_regions_stay_separate(self):
        europe = article_for(
            self.module,
            "Counterpoint says Apple gained share in Europe's Q2 2026 phone market",
            "Counterpoint reported Apple reached 25 percent share in Europe in Q2 2026.",
            "AppleInsider",
        )
        latin_america = article_for(
            self.module,
            "Counterpoint 报告 2026Q2 拉美智能手机出货量：苹果增 5%",
            "Counterpoint 称苹果在拉丁美洲 2026 年第二季度出货量同比增长 5%。",
            "IT之家",
        )
        events = self.module.cluster_articles([europe, latin_america])

        self.assertEqual(len(events), 2)

    def test_same_business_unit_layoff_merges_across_wording(self):
        reports = [
            article_for(
                self.module,
                "Layoffs in Apple's Vision Products Group affect at least 60 employees",
                "Apple laid off an entire VR development team in the Apple Vision Group.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple reportedly lays off Vision employees amid shifting priorities",
                "At least 60 employees tied to Apple's VR team and Vision group were affected.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "消息称苹果裁掉整个 VR 研发团队，影响至少 60 人",
                "苹果裁减 Apple Vision 业务组及相关岗位的至少 60 名员工。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果 VR 团队大瘦身：至少 60 名开发员工被裁，头显项目优先级下调",
                (
                    "据 AppleInsider 报道，苹果近期裁减了至少 60 名与 VR 团队、"
                    "Vision 部门及相关岗位的员工。"
                ),
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 4)

    def test_same_product_launch_schedule_merges_across_languages(self):
        reports = [
            article_for(
                self.module,
                "iPhone 18 won't launch next month, here's when it's coming instead",
                "The base iPhone 18 will miss September and is pushed to early 2027, likely by March.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "iPhone 18 缺席 9 月发布会，最晚明年 3 月推出",
                "苹果将标准版 iPhone 18 延后至 2027 年第一季度发布。",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_same_regional_store_terms_action_merges_across_perspectives(self):
        reports = [
            article_for(
                self.module,
                "European Commission approves Apple's new App Store terms",
                "The Commission welcomed Apple's revised EU business terms with rates from 5 to 26 percent.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Apple's long-running App Store battle with the EU appears to be over",
                "The EU welcomed Apple's new App commission rates and revised terms ranging from 5 to 26 percent.",
                "9to5Mac",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_same_legal_motion_response_merges_without_legacy_seed(self):
        reports = [
            article_for(
                self.module,
                "Apple hits back at OpenAI's bid to dismiss trade secret theft lawsuit",
                "Apple asked the court to deny OpenAI's motion to dismiss its trade secrets case.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple fires back at OpenAI's bid to toss trade secrets suit",
                "Apple filed an opposition to OpenAI's dismissal request in the same trade secrets lawsuit.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Distortion and speculation warrant denying OpenAI request for lawsuit dismissal, says Apple",
                "Apple says OpenAI's motion to dismiss should be denied in the trade secrets case.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果反驳 OpenAI 驳回诉讼动议，重申商业秘密窃取指控",
                "苹果提交文件，要求法院拒绝 OpenAI 驳回商业秘密诉讼的动议。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果要求法院驳回 OpenAI 撤诉请求，指控其歪曲事实",
                "苹果反对 OpenAI 要求撤销商业秘密诉讼的申请。",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(reports)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 5)

    def test_direct_launch_timing_does_not_merge_with_accessory_case(self):
        accessory = article_for(
            self.module,
            "iPhone 18 Pro Max 保护壳开箱：与 17 Pro Max 完美适配",
            (
                "第三方保护壳显示 6.9 英寸机身和相机开孔，并复述 A20 Pro、"
                "摄像头和 9 月新品发布传闻。"
            ),
            "快科技",
        )
        launch_timing = article_for(
            self.module,
            "苹果下周官宣 iPhone 18 Pro 发布时间：三大旗舰同步登场",
            (
                "报道预计苹果将公布 9 月发布会，iPhone 18 Pro、Pro Max 和折叠机"
                "同步登场，并提及 A20 Pro 与摄像头变化。"
            ),
            "快科技",
        )

        events = self.module.cluster_articles([accessory, launch_timing])

        self.assertEqual(len(events), 2)

    def test_accessory_background_facts_cannot_override_third_party_boundary(self):
        accessory = article_for(
            self.module,
            "iPhone 18 Pro Max保护壳开箱上手：实测跟17 Pro Max完美适配",
            "第三方保护壳展示了 6.9 英寸机身、K100 相机布局和 A20 Pro 背景传闻。",
            "快科技",
        )
        launch_timing = article_for(
            self.module,
            "年度大戏将至！苹果下周官宣iPhone 18 Pro发布时间：三大旗舰同步登场",
            "报道预计苹果下周宣布发布时间，并回顾 A20 Pro 和相机规格。",
            "快科技",
        )

        events = self.module.cluster_articles([accessory, launch_timing])

        self.assertEqual(len(events), 2)
        tiers = {event.title: event.relevance_tier for event in events}
        self.assertEqual(tiers[accessory.title], "weak")
        self.assertEqual(tiers[launch_timing.title], "strong")


if __name__ == "__main__":
    unittest.main()
