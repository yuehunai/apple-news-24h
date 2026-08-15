import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260814_test", SCRIPT_PATH)
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
        published_utc=datetime(2026, 8, 14, tzinfo=timezone.utc),
        published_raw="2026-08-14T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


def title_sets(groups):
    return [{article.title for article in group} for group in groups]


class PositiveEventCohesionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def reconcile(self, articles, initial_groups=None):
        return self.module.reconcile_articles(
            articles,
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=initial_groups or [[article] for article in articles],
        )

    def test_calendar_year_does_not_turn_lifecycle_story_into_product_roadmap_variants(self):
        title = "iPhone X & 2018 MacBook Pro join Apple's 'obsolete products' list"
        summary = (
            "Apple declared the iPhone X and 2018 15-inch MacBook Pro obsolete; "
            "Apple and authorized providers no longer offer repairs or parts."
        )
        facts = [
            "Apple's iPhone X launched in 2017 with Face ID and an OLED display.",
            "Also obsolete is the 2018 15-inch MacBook Pro with Apple's T2 chip.",
        ]
        variants = self.module.compound_article_variants(title, summary, facts)
        self.assertEqual(variants, [(title, summary, facts)])

    def test_provisional_seed_splits_different_content_product_and_lifecycle_actions(self):
        cases = [
            [
                article_for(
                    self.module,
                    "Ted Lasso Season 4 Premiere is Apple TV's Biggest Launch Ever",
                    "Ted Lasso season 4 drew 296.6 million U.S. viewing minutes in its first two days, an Apple TV premiere record.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "Apple TV publishes the trailer for Stillwater's fifth season",
                    "Apple TV released the Stillwater season 5 trailer and will stream five episodes on August 21.",
                    "9to5Mac",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Apple TV Gains Classic Movies Collection",
                    "Apple added Titanic, E.T. and other classic movies for subscribers to stream at no extra charge.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "Ted Lasso just had the biggest Apple TV premiere ever",
                    "Ted Lasso season 4 set Apple TV's premiere viewing record.",
                    "9to5Mac",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Apple adds iPhone X and 2018 MacBook Pro to obsolete products list",
                    "Apple moved both devices to its obsolete list and ended first-party hardware service.",
                    "9to5Mac",
                ),
                article_for(
                    self.module,
                    "MacBook Pro idle power drops from 24W to 12W after Linux AMD fix",
                    "A Linux kernel patch fixes discrete-GPU idle power on older MacBook Pro hardware.",
                    "快科技",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Apple Says iPhone X is Now Obsolete",
                    "Apple added iPhone X to its obsolete products list.",
                    "MacRumors",
                ),
                article_for(
                    self.module,
                    "iPhone 18 Pro OLED panel cost reportedly falls nearly 40%",
                    "A supply-chain report says Apple secured lower OLED pricing for iPhone 18 Pro.",
                    "IT之家",
                ),
                article_for(
                    self.module,
                    "Foldable iPhone Ultra may launch in the US first",
                    "Limited production could lead Apple to use a staggered regional rollout.",
                    "9to5Mac",
                ),
            ],
            [
                article_for(
                    self.module,
                    "Eddy Cue hints at more Ted Lasso seasons to come",
                    "Apple TV senior vice president Eddy Cue strongly suggests there will be a fifth season.",
                    "AppleInsider",
                ),
                article_for(
                    self.module,
                    "苹果在休斯顿开设 Mac Mini 新制造工厂",
                    "苹果在休斯顿为新制造工厂揭幕，提供制造培训课程并将生产 Mac Mini。",
                    "IT之家",
                ),
            ],
        ]
        for articles in cases:
            with self.subTest(titles=[article.title for article in articles]):
                groups = self.reconcile(articles, [articles])
                self.assertEqual(len(groups), len(articles), title_sets(groups))

    def test_cross_source_reports_reconcile_by_concrete_subject_and_action(self):
        sets = [
            [
                article_for(self.module, "Ted Lasso Season 4 Premiere is Apple TV's Biggest Launch Ever", "Ted Lasso season 4 set an Apple TV premiere viewing record.", "MacRumors"),
                article_for(self.module, "《足球教练》第四季首播创下 Apple TV 历史最高收视纪录", "第四季首播两天观看时长达到 2.966 亿分钟。", "IT之家"),
            ],
            [
                article_for(self.module, "Apple TV Gains Classic Movies Collection", "Apple added a classic movie collection for subscribers at no extra cost.", "MacRumors"),
                article_for(self.module, "苹果 Apple TV 新增《泰坦尼克号》等经典影片", "订阅用户可免费观看新增经典片库。", "IT之家"),
            ],
            [
                article_for(self.module, "Apple Says iPhone X is Now Obsolete", "Apple added iPhone X and the 2018 MacBook Pro to its obsolete list.", "MacRumors"),
                article_for(self.module, "iPhone X、2018 款 MacBook Pro 被苹果列入“停产”产品", "苹果结束两款产品的官方硬件服务与零件供应。", "IT之家"),
            ],
            [
                article_for(self.module, "Apple opens Advanced Manufacturing Center in Houston", "Apple opened a Houston training and manufacturing center ahead of Mac mini production.", "Apple Newsroom"),
                article_for(self.module, "苹果在休斯顿开设先进制造中心，今年将生产 Mac mini", "苹果启用休斯顿先进制造中心并提供制造培训。", "IT之家"),
                article_for(self.module, "库克陪同商务部长参观苹果 Mac mini 新工厂", "两人参加新制造培训学校揭幕，工厂今年晚些时候生产 Mac mini。", "cnBeta"),
            ],
            [
                article_for(self.module, "'Obvious' App Store ratings fraud going undetected by Apple", "A developer reported fake screenshots, reviews and AI-wrapped apps to Apple.", "9to5Mac"),
                article_for(self.module, "开发者反馈苹果 App Store 存在欺诈应用和虚假评论", "开发者向苹果反馈 App Store 评分和评论欺诈。", "IT之家"),
            ],
            [
                article_for(self.module, "Apple sends fresh wave of mercenary spyware warnings worldwide", "Apple sent threat notifications to users in more than 100 countries.", "9to5Mac"),
                article_for(self.module, "苹果向 110 个国家用户发布间谍软件威胁警报", "苹果再次向可能遭雇佣间谍软件攻击的用户发送警报。", "cnBeta"),
            ],
            [
                article_for(self.module, "Apple Glasses could chime when recording, patent shows", "An Apple patent describes an audible recording indicator for Apple Glasses.", "AppleInsider"),
                article_for(self.module, "苹果 Apple Glasses 专利获批：录制时发出音频提示", "苹果专利通过提示音降低智能眼镜录制被劫持的风险。", "IT之家"),
            ],
        ]
        articles = [article for group in sets for article in group]
        groups = self.reconcile(articles)
        actual = title_sets(groups)
        for expected in sets:
            self.assertIn({article.title for article in expected}, actual)

    def test_same_hardware_report_reconciles_without_broad_product_bridging(self):
        oled = [
            article_for(
                self.module,
                "Apple reportedly secures the lowest OLED price for iPhone 18 Pro",
                "The iPhone 18 Pro OLED panel cost falls nearly 40% to about $70.",
                "快科技",
            ),
            article_for(
                self.module,
                "苹果压价成功：iPhone 18 Pro 屏幕成本低至 70 美元",
                "OLED 面板成本同比下降近 40%，用于对冲内存涨价。",
                "IT之家",
            ),
        ]
        rollout = [
            article_for(
                self.module,
                "Foldable iPhone Ultra may launch in the US first",
                "Limited production and yield constraints could lead to a staggered market rollout.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果折叠屏 iPhone Ultra 产能有限，首批优先供应美国市场",
                "良率与零部件供应制约导致苹果采用分区域阶梯上市策略。",
                "快科技",
            ),
            article_for(
                self.module,
                "iPhone Ultra could initially launch only in the US",
                "The foldable iPhone may use a staggered international rollout.",
                "MacRumors",
            ),
        ]
        groups = self.reconcile([*oled, *rollout])
        actual = title_sets(groups)
        self.assertIn({article.title for article in oled}, actual)
        self.assertIn({article.title for article in rollout}, actual)

    def test_event_date_estimate_is_editorial_analysis(self):
        title = "iPhone 18 Pro and iPhone Ultra: When is the Next Apple Event?"
        summary = "The article estimates the event date from Apple's calendar and existing rumors."
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "MacRumors")
        self.assertEqual(tier, "weak", reason)

    def test_legal_proposal_and_court_stay_are_separate_actions(self):
        proposal = article_for(
            self.module,
            "Apple proposes commissions of up to 15% for off-App Store purchases",
            "Apple filed a new external-purchase commission proposal in the Epic case.",
            "9to5Mac",
        )
        stay = article_for(
            self.module,
            "Supreme Court denies another stay in Apple vs Epic proceedings",
            "The Supreme Court denied Apple's request to pause the filing deadline.",
            "AppleInsider",
        )
        chinese_proposal = article_for(
            self.module,
            "外链佣金最高 15%：苹果拟推行 App Store 新方案",
            "苹果提交外部支付新佣金方案，Epic 表示反对。",
            "IT之家",
        )
        groups = self.reconcile(
            [proposal, chinese_proposal, stay],
            [[proposal, chinese_proposal, stay]],
        )
        self.assertIn({proposal.title, chinese_proposal.title}, title_sets(groups))
        self.assertIn({stay.title}, title_sets(groups))

    def test_editorial_and_routine_compatibility_items_do_not_enter_main_events(self):
        cases = [
            (
                "Aqara H1 launches with Apple HomeKit support for 399 yuan",
                "Aqara launched its own lighting accessory with routine HomeKit compatibility; Apple made no platform or policy change.",
                "IT之家",
            ),
            (
                "PSA: Setting different default languages in different Mac apps",
                "This tutorial explains an existing macOS per-app language setting and reports no new Apple change.",
                "9to5Mac",
            ),
            (
                "iPhone 18 Pro and iPhone Ultra: When is the Next Apple Event?",
                "An editorial calendar estimate compiles existing launch rumors without new reporting.",
                "MacRumors",
            ),
            (
                "New Apple TV 4K: Release date, features, price, and rumors",
                "A buying guide compiles existing Apple TV rumors and purchase advice.",
                "9to5Mac",
            ),
            (
                "iPhone 17 Pro One Year Later: What Held Up and What Didn't",
                "A long-term experience review evaluates an existing phone without a new Apple action.",
                "MacRumors",
            ),
            (
                "What's Coming in September: New iPhones, Apple Watches and More",
                "A rumor roundup compiles previously reported product expectations.",
                "MacRumors",
            ),
            (
                "18还没发布 iPhone 20就都提前知道了：苹果供应链无秘密",
                "文章汇总既有路线图：标准版 iPhone 18 延至明年，随后讨论 20 周年 iPhone 20 的既有设计传闻。",
                "快科技",
            ),
            (
                "曾称要跟苹果三星三分天下！某品牌新手机完成首台交付",
                "该品牌交付自己的首款手机，并以 iPhone 作为定价和市场定位的比较对象；苹果没有采取新行动。",
                "快科技",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "weak", reason)
                article = article_for(self.module, title, summary, source)
                profile = self.module.article_reconciliation_profile(article)
                self.module.reconcile_article_relevance(article, profile)
                self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_direct_facility_patent_and_executive_service_followup_stay_strong(self):
        cases = [
            (
                "Apple opens Advanced Manufacturing Center in Houston",
                "Apple opened the first-party center for manufacturing training and future Mac mini production.",
                "Apple Newsroom",
            ),
            (
                "Apple Glasses could chime when recording, patent shows",
                "Apple's patent describes a first-party recording indicator for its glasses roadmap.",
                "AppleInsider",
            ),
            (
                "Eddy Cue hints at more Ted Lasso seasons to come",
                "Apple TV senior vice president Eddy Cue strongly suggests there will be a fifth season. The writer notes it was already a fair bet, but Cue said he hopes the show continues.",
                "AppleInsider",
            ),
        ]
        for title, summary, source in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(title, summary, [], source)
                self.assertEqual(tier, "strong", reason)

    def test_lifecycle_and_facility_events_are_hardware(self):
        cases = [
            ("Apple Says iPhone X is Now Obsolete", "Apple ended official hardware service for iPhone X."),
            ("Apple opens Advanced Manufacturing Center in Houston", "The facility will train manufacturers and produce Mac mini hardware."),
        ]
        for title, summary in cases:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary)
                profile = self.module.article_reconciliation_profile(article)
                self.assertEqual(profile.category_hint, "hardware_products")


if __name__ == "__main__":
    unittest.main()
