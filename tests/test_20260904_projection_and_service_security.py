from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apple_news_24h.py"


def load_module():
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("apple_news_24h_20260904", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="MacRumors", facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    article = module.Article(
        source=source,
        url=f"https://example.com/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 9, 4, tzinfo=timezone.utc),
        published_raw="2026-09-04T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, f"{summary} {' '.join(facts)}"),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=set(),
    )
    module.reconcile_article_relevance(
        article,
        module.article_reconciliation_profile(article),
    )
    return article


class ProjectionAndServiceSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_focused_mac_report_does_not_project_historical_background(self):
        title = "New chip rumor could make the MacBook Ultra a portable Mac Studio"
        facts = [
            "Apple has been working on a MacBook Pro with a new OLED display for years, and the current report says it may launch before the end of 2026.",
            "Omdia believes the OLED MacBook Pro is highly likely to feature an M5 Ultra chip.",
            "Apple announced the M5 Ultra last month in the upgraded Mac Studio, where it offers up to a 36-core CPU and 80-core GPU.",
            "Bringing the chip to a portable machine would make the OLED MacBook worthy of the MacBook Ultra name.",
            "The report remains skeptical that the chip can meet laptop power and cooling limits.",
        ]

        variants = self.module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(variants, [(title, " ".join(facts), facts)])

    def test_focused_chip_report_does_not_project_secondary_device_context(self):
        title = "iPhone 18 Pro Chip Leak Indicates Major GPU and Memory Bandwidth Improvements"
        summary = (
            "An alleged A20 Pro diagram suggests a seven-core GPU and wider memory bus. "
            "The chip is expected in iPhone 18 Pro and could also be used in Apple's "
            "first foldable iPhone."
        )
        facts = [summary]

        variants = self.module.compound_article_variants(title, summary, facts)

        self.assertEqual(variants, [(title, summary, facts)])

    def test_explicit_multi_product_mac_report_still_projects_owned_actions(self):
        title = "Upgraded Mac mini, Mac Studio, and OLED iMac are all in the pipeline"
        facts = [
            "Apple is preparing a Mac mini with M6 and M5 Pro chips.",
            "Apple is preparing a Mac Studio with M5 Max and M5 Ultra chips.",
            "Apple is developing an OLED iMac for 2030.",
        ]

        variants = self.module.compound_article_variants(title, " ".join(facts), facts)

        self.assertEqual(len(variants), 3, variants)
        self.assertTrue(any("Mac mini" in item[0] for item in variants), variants)
        self.assertTrue(any("Mac Studio" in item[0] for item in variants), variants)
        self.assertTrue(any("iMac" in item[0] for item in variants), variants)

    def test_editorial_future_catalog_cannot_create_strong_child_events(self):
        source_title = "Apple will launch six major new products next week, here's what's coming"
        child_title = "Apple HomePod roadmap update"
        summary = "HomePod mini 2 may get a new chip and Siri AI at next week's event."

        tier, _reason = self.module.classify_projected_article_relevance(
            source_title,
            child_title,
            summary,
            [summary],
            "9to5Mac",
        )

        self.assertEqual(tier, "weak")

    def test_apple_owned_value_instrument_fraud_is_brief_eligible(self):
        article = article_for(
            self.module,
            "苹果礼品卡全球诈骗案告破：犯罪团伙窃取兑换码后重新封装",
            "澳大利亚警方破获针对苹果礼品卡兑换体系的跨国诈骗案，全美前 20 大零售商均受波及。",
            "IT之家",
            [
                "犯罪集团从零售货架盗取苹果礼品卡，窃取兑换码后重新封装并放回货架。",
                "警方查获 65 张苹果礼品卡，总面值超过 1 万澳元。",
            ],
        )

        self.assertNotEqual(article.relevance_tier, "weak", article.relevance_reason)
        self.assertEqual(article.event_kind, "security_privacy")
        self.assertEqual(article.category, "software_systems")

    def test_device_used_only_as_criminal_evidence_remains_weak(self):
        article = article_for(
            self.module,
            "Apple Watch data reveals final movements in murder trial",
            "Police used Apple Watch health records and iPhone call logs only as evidence in a criminal trial.",
            "AppleInsider",
        )

        self.assertEqual(article.relevance_tier, "weak")

    def test_third_party_homekit_compatibility_is_not_apple_data_integration(self):
        cases = [
            (
                "某智能家居品牌发布接入 HomeKit 的桌面妙控旋钮",
                "该品牌推出自有智能家居控制器，并接入 Apple HomeKit 供用户使用。",
            ),
            (
                "某智能家居品牌发布原生支持 Apple Home 的墙壁开关",
                "该品牌推出自有墙壁开关，支持在苹果 Apple Home 生态中控制。",
            ),
        ]

        for title, summary in cases:
            with self.subTest(title=title):
                tier, reason = self.module.classify_relevance_tier(
                    title,
                    summary,
                    [],
                    "IT之家",
                )

                self.assertFalse(
                    self.module.is_direct_third_party_apple_data_integration_story(title, summary)
                )
                self.assertNotIn(
                    "apple-data-integration",
                    self.module.title_led_identity(title, summary).title_components,
                )
                self.assertEqual(tier, "weak", reason)
                self.assertEqual(
                    self.module.detect_event_kind(title, summary),
                    "third_party_ecosystem",
                )

    def test_att_lawsuit_merges_across_language_and_currency_rendering(self):
        articles = [
            article_for(
                self.module,
                "Apple Hit With $2.7 Billion Lawsuit Over App Tracking Rules",
                "A UK class action alleges App Tracking Transparency harmed third-party developers.",
            ),
            article_for(
                self.module,
                "Apple faces yet another lawsuit over App Tracking Transparency, with a twist",
                "Apple's ATT privacy policy is challenged in the same UK class action.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Apple sued over App Tracking Transparency in $2.7 billion class action",
                "A former UK antitrust director says ATT disadvantaged developers.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "前英国反垄断官员发起诉讼，指控苹果利用应用追踪透明度政策打压开发者",
                "安·波普向英国竞争上诉法庭提起集体诉讼，要求苹果赔偿 27 亿美元。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "苹果在英国遭 20 亿英镑集体诉讼，被指‘要求 App 不跟踪’弹窗损害开发者利益",
                "苹果在英国面临 20 亿英镑集体诉讼，前 CMA 高管指控其 ATT 弹窗对第三方开发者不公。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_face_id_patent_case_is_not_parsed_as_analyst_target(self):
        articles = [
            article_for(
                self.module,
                "Apple's Face ID technology target of latest lawsuit from German company BASF",
                "BASF subsidiary trinamiX alleges Face ID infringes seven material-detection patents.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "巴斯夫起诉苹果公司，称 Face ID 侵犯其 7 项专利",
                "德国巴斯夫旗下 trinamiX 在美国起诉苹果，案件涉及 Face ID 材料检测技术。",
                "IT之家",
            ),
        ]
        identity = self.module.title_led_identity(articles[0].title, articles[0].summary)

        self.assertNotIn("analyst-target-action", identity.title_components)
        self.assertEqual(len(self.module.cluster_articles(articles)), 1)

    def test_named_content_rights_acquisition_merges_across_quote_styles(self):
        articles = [
            article_for(
                self.module,
                "Apple lands disaster film 'Waffle House Index'",
                "Apple TV is betting on the Waffle House Index for a sci-fi disaster flick; the deal was seven figures.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "《华夫饼屋指数》电影版权被苹果以 7 位数美元拿下",
                "苹果 Apple TV 以七位数美元购得《华夫饼屋指数》（Waffle House Index）的电影版权。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_distinct_hardware_roadmap_actions_do_not_share_a_product_family_cluster(self):
        articles = [
            article_for(
                self.module,
                "Apple may find OLED middle-ground between MacBook Pro and Air in 2029",
                "Apple is planning to introduce a new OLED MacBook model in 2029 to bridge the gap between MacBook Air and MacBook Pro.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "消息称苹果计划推出全新 MacBook 机型：13.8 寸 OLED 面板，定位介于 Air 和 Pro 之间",
                "苹果可能在 2029 年推出全新 MacBook，定位介于 Air 和 Pro 之间。",
                "IT之家",
            ),
            article_for(
                self.module,
                "Long-rumored all-screen folding MacBook Pro project may be dead",
                "Apple has scrapped plans for an all-screen folding MacBook Pro.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Omdia 报告苹果已搁置开发 16.1~18 英寸大型可折叠 MacBook",
                "苹果已搁置可折叠 MacBook 项目。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果 LCD 版 MacBook Pro 至少将销售到 2027 年底",
                "Omdia 表示苹果预计继续销售现有 LCD 版 MacBook Pro。",
                "快科技",
            ),
            article_for(
                self.module,
                "Mini-LED MacBook Pro Models Could Stick Around Until 2028",
                "Omdia expects existing mini-LED MacBook Pro models to remain available through 2028.",
                "MacRumors",
            ),
        ]

        events = self.module.cluster_articles(articles)
        groups = [set(article.title for article in event.articles) for event in events]

        self.assertEqual(len(events), 3, groups)
        self.assertTrue(any(len(group) == 2 and all("between" in title.lower() or "介于" in title for title in group) for group in groups), groups)
        self.assertTrue(any(len(group) == 2 and all("fold" in title.lower() or "折叠" in title for title in group) for group in groups), groups)
        self.assertTrue(
            any(
                len(group) == 2
                and any("lcd" in title.lower() for title in group)
                and any("mini-led" in title.lower() for title in group)
                for group in groups
            ),
            groups,
        )

    def test_aggregate_same_family_cancellations_project_by_concrete_program(self):
        source_title = "Apple Apparently Cancels Plans for Two New MacBooks"
        source_facts = [
            "Apple has scrapped development of a large foldable MacBook that would have measured between 16.1 and 18 inches when unfolded.",
            "Apple has also called off a separate planned MacBook with an OLED display between 14.4 and 16.1 inches, which would have sat between the standard MacBook Pro and the canceled foldable.",
        ]

        variants = self.module.compound_article_variants(
            source_title,
            " ".join(source_facts),
            source_facts,
        )

        self.assertEqual(len(variants), 2, variants)
        self.assertTrue(any("foldable" in title.lower() for title, _summary, _facts in variants), variants)
        self.assertTrue(any("oled" in title.lower() for title, _summary, _facts in variants), variants)
        self.assertTrue(any("16.1" in summary for _title, summary, _facts in variants), variants)
        self.assertTrue(any("14.4" in summary for _title, summary, _facts in variants), variants)
        foldable_variant = next(
            item for item in variants if "foldable" in item[0].lower()
        )
        oled_variant = next(item for item in variants if "oled" in item[0].lower())
        self.assertFalse(
            any("14.4" in fact for fact in foldable_variant[2]),
            foldable_variant,
        )
        self.assertTrue(any("14.4" in fact for fact in oled_variant[2]), oled_variant)
        self.assertFalse(
            any("18 inches" in fact for fact in oled_variant[2]),
            oled_variant,
        )

        projected = [
            article_for(self.module, title, summary, "MacRumors", facts)
            for title, summary, facts in variants
        ]
        focused = [
            article_for(
                self.module,
                "Apple has reportedly canceled innovative product that was Ternus priority",
                "A new Omdia report says plans for a 16.1-inch to 18-inch foldable MacBook have been canceled.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "Omdia 报告苹果已搁置开发 16.1~18 英寸大型可折叠 MacBook",
                "苹果已搁置可折叠 MacBook 项目。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles([*projected, *focused])
        groups = [set(article.source for article in event.articles) for event in events]

        self.assertEqual(len(events), 2, [(event.title, groups[index]) for index, event in enumerate(events)])
        self.assertTrue(any(group == {"MacRumors", "9to5Mac", "IT之家"} for group in groups), groups)
        self.assertTrue(any(group == {"MacRumors"} for group in groups), groups)

    def test_competitor_comparison_cannot_override_title_owned_cancellation(self):
        article = article_for(
            self.module,
            "苹果折叠 iPad/Mac 项目被砍掉：竞品成为这一赛道的唯一玩家",
            "苹果叫停折叠 iPad/Mac 混合设备；后文介绍竞品的折叠电脑和专利。",
            "快科技",
        )

        self.assertEqual(article.event_kind, "hardware_market")
        self.assertEqual(article.relevance_tier, "strong")
        self.assertEqual(article.category, "hardware_products")

    def test_opening_lead_can_project_multiple_same_family_cancellations(self):
        title = "Omdia 报告苹果已搁置开发 16.1~18 英寸大型可折叠 MacBook"
        facts = [
            "苹果公司已搁置开发尺寸在 16.1~18 英寸的大型可折叠 MacBook，此前消息将其描述为大屏可折叠 iPad。",
            "苹果同时取消了一款采用 14.4 至 16.1 英寸 OLED 显示屏的 MacBook。",
        ]
        summary = (
            "Omdia 指出苹果可能已搁置可折叠 MacBook 和更大尺寸 OLED MacBook 机型的计划。 "
            + " ".join(facts)
        )

        variants = self.module.compound_article_variants(title, summary, facts)

        self.assertEqual(len(variants), 2, variants)
        foldable_variant = next(item for item in variants if "foldable" in item[0].lower())
        oled_variant = next(item for item in variants if "oled" in item[0].lower())
        self.assertTrue(any("16.1~18" in fact for fact in foldable_variant[2]))
        self.assertFalse(any("14.4" in fact for fact in foldable_variant[2]))
        self.assertTrue(any("14.4" in fact for fact in oled_variant[2]))

    def test_same_named_research_report_price_forecast_merges_across_languages(self):
        articles = [
            article_for(
                self.module,
                "iPhone 18 Pro Prices Estimated Ahead of Apple Event Next Week",
                "Research firm TrendForce estimates iPhone 18 Pro and Pro Max prices will rise around 10% to 20% based on the latest hardware cost environment.",
                "MacRumors",
                facts=[
                    "For the 256GB Pro model, memory costs in 3Q26 are expected to be nearly 400% higher than a year earlier.",
                    "TrendForce expects iPhone 18 Pro prices to rise by $150 to $200.",
                ],
            ),
            article_for(
                self.module,
                "Apple paying 400% more for iPhone 18 Pro memory, says TrendForce",
                "A new market intelligence report suggests that Apple will be paying four times more for iPhone 18 Pro memory.",
                "9to5Mac",
                facts=["TrendForce forecasts a 10% to 20% iPhone 18 Pro price increase."],
            ),
            article_for(
                self.module,
                "TrendForce：苹果 iPhone 18 Pro 内存采购成本暴涨 400%，预估新机涨价 10%-20%",
                "TrendForce 集邦咨询预计 iPhone 18 Pro 系列涨价 10% 至 20%，256GB 机型内存成本同比上涨近 400%。",
                "IT之家",
            ),
            article_for(
                self.module,
                "存储成本暴涨近400%！iPhone 18 Pro系列预计涨价10%-20%",
                "根据 TrendForce 集邦咨询最新手机产业研究，苹果将推出 iPhone 18 Pro 系列。",
                "快科技",
                facts=[
                    "以 iPhone 18 Pro 256GB 版本为例，其存储器成本同比上涨近 400%。",
                    "预计 iPhone 18 系列整体涨幅将在 10%-20% 之间。",
                ],
            ),
            article_for(
                self.module,
                "机构预计iPhone 18 Pro系列起售价或上涨至1249美元",
                "距离发布不到一周，研究机构 TrendForce 根据当前硬件成本环境对新机价格进行了预估。",
                "cnBeta",
                facts=[
                    "按照 TrendForce 的预测，iPhone 18 Pro 起售价或为 1249 至 1299 美元。",
                    "256GB 内存芯片价格同比上涨近 400%。",
                ],
            ),
            article_for(
                self.module,
                "苹果大涨价！iPhone 18 Pro、18 Pro Max和首款折叠屏售价曝光：万元起步 最贵超2万",
                "受到上游原材料涨价影响，新一代 iPhone 系列大概率全面提价。",
                "快科技",
                facts=[
                    "iPhone 18 Pro 起售价可能上调至 1249 到 1299 美元。",
                    "iPhone 18 Pro Max 起售价可能达到 1349 到 1399 美元。",
                ],
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_product_price_forecast_does_not_merge_with_production_constraint(self):
        articles = [
            article_for(
                self.module,
                "消息称苹果折叠屏手机 iPhone Ultra 售价约为同期 Pro 机型的 1.8 倍",
                "运营商渠道曝光 iPhone Ultra 在多个地区的预计售价。",
                "IT之家",
            ),
            article_for(
                self.module,
                "iPhone Ultra production is only a few hundred units per day",
                "Supply-chain sources say strict quality-control standards are limiting daily output of Apple's foldable iPhone.",
                "MacRumors",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_same_product_production_constraint_merges_across_languages(self):
        articles = [
            article_for(
                self.module,
                "iPhone Ultra production is only a few hundred units per day",
                "Supply-chain sources say strict quality-control standards are limiting daily output of Apple's foldable iPhone.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "苹果 iPhone Ultra 量产遇瓶颈，日产量仅数百台",
                "供应链消息称严格的质量控制限制了这款折叠屏 iPhone 的当前产能。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "Apple's suppliers only made a few hundred of the iPhone Ultra in August",
                "Mass production is underway, but Nikkei Asia reports that quality inspections limited output to a few hundred units per day.",
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_same_named_report_reconciles_equivalent_product_production_status(self):
        articles = [
            article_for(
                self.module,
                "iPhone Ultra production is only a few hundred units per day, says Nikkei",
                "Nikkei Asia says strict quality controls are limiting daily output.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple's suppliers only made a few hundred of the iPhone Ultra in August",
                (
                    "Mass production has been underway for weeks. Reports have differed over the bottleneck. "
                    "The device is still expected at Apple's event. According to Nikkei Asia, manufacturing "
                    "slowed in late August to only a few hundred units per day."
                ),
                "AppleInsider",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_existing_multilingual_production_group_accepts_sparse_same_report_source(self):
        macrumors = article_for(
            self.module,
            "iPhone Ultra Production Hitting Just 'a Few Hundred' a Day, Says Nikkei",
            "Nikkei Asia reports that strict quality controls limit output to a few hundred units per day.",
            "MacRumors",
        )
        cnbeta = article_for(
            self.module,
            "苹果折叠屏 iPhone Ultra 日产量仅数百台，量产爬坡缓慢",
            "据日经亚洲报道，苹果在 8 月底的日产量仍只有数百台。",
            "cnBeta",
        )
        appleinsider = article_for(
            self.module,
            "Apple's suppliers only made a few hundred of the iPhone Ultra in August",
            (
                "Mass production has been underway for weeks. "
                "Reports have differed over whether the bottleneck was resolved. "
                "According to Nikkei Asia, production has been very slow. "
                "Manufacturing slowed in late August to only a few hundred units per day."
            ),
            "AppleInsider",
            [
                "Reportedly, manufacturing slowed in late August to no more than a few hundred units per day."
            ],
        )

        groups = self.module.reconcile_articles(
            [macrumors, cnbeta, appleinsider],
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[macrumors, cnbeta], [appleinsider]],
        )

        self.assertEqual(
            len(groups),
            1,
            [[article.source for article in group] for group in groups],
        )

    def test_report_attribution_extracts_named_entity_without_grammar_noise(self):
        cases = [
            (
                "iPhone 18 Pro Prices Estimated Ahead of Apple Event Next Week",
                "Research firm TrendForce has estimated the prices based on the latest hardware cost environment.",
                "report-attribution:trendforce",
            ),
            (
                "苹果 LCD 版 MacBook Pro 至少将销售到 2027 年底",
                "据报道，Omdia 总监在韩国显示大会上表示现有机型将延长销售。",
                "report-attribution:omdia",
            ),
            (
                "机构预计 iPhone 18 Pro 系列起售价上涨",
                "按照 TrendForce 的预测，新机起售价将上涨。",
                "report-attribution:trendforce",
            ),
            (
                "Foldable iPhone production remains slow, says Nikkei",
                "Nikkei Asia reports that quality controls are limiting output.",
                "report-attribution:nikkei-asia",
            ),
        ]

        for title, lead, expected in cases:
            with self.subTest(title=title):
                identity = self.module.title_led_identity(title, lead)
                attributions = {
                    component
                    for component in identity.components
                    if component.startswith("report-attribution:")
                }
                self.assertIn(expected, attributions)
                self.assertFalse(
                    any(
                        fragment in attribution
                        for attribution in attributions
                        for fragment in ("taking-", "按照", "远低于", "订单规模")
                    ),
                    attributions,
                )

    def test_same_chip_disclosure_merges_from_model_and_changed_objects(self):
        articles = [
            article_for(
                self.module,
                "A20 Pro 芯片焊点图曝光，GPU 与内存总线升级",
                "焊点图显示 A20 Pro 采用 7 核 GPU 和 96 位内存总线。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "iPhone 18 Pro chip leak hints at performance upgrades in two key areas",
                "The leaked A20 Pro solder map points to a seven-core GPU and wider memory bus.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Leaker claims iPhone 18 Pro chip will have 7 GPU cores and faster RAM",
                "The same A20 Pro solder diagram indicates a 96-bit memory interface.",
                "9to5Mac",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_competitor_device_with_apple_comparison_stays_deferred(self):
        title = "Lenovo's new MacBook Neo competitor comes in two sizes and seven colors"
        summary = "Lenovo announced its IdeaPad Vibe with OLED options and used MacBook Neo only as a price comparison."
        article = article_for(
            self.module,
            title,
            summary,
            "The Verge",
        )
        source = next(
            source
            for source in self.module.build_sources(datetime.now().astimezone())
            if source.name == "The Verge"
        )
        candidate = self.module.Candidate(
            source="The Verge",
            url="https://example.com/lenovo-macbook-competitor",
            title=title,
            summary=summary,
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)
        self.assertTrue(self.module.is_relevant_candidate(candidate, source))

    def test_non_apple_device_using_apple_equivalent_component_stays_deferred(self):
        article = article_for(
            self.module,
            "消息称某品牌旗舰手机确认搭载新一代发光材料，苹果折叠屏同款方案",
            "该安卓手机将首发新的显示材料，苹果产品只用于说明方案相同。",
            "IT之家",
        )

        self.assertTrue(
            self.module.is_non_apple_title_action_using_apple_as_reference_story(
                article.title,
                article.summary,
            )
        )
        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_apple_device_adopting_named_component_remains_direct(self):
        article = article_for(
            self.module,
            "消息称苹果折叠屏 iPhone Ultra 确认采用新一代 M16 发光材料",
            "供应链称苹果将为首款折叠屏 iPhone 采用新的显示材料。",
            "IT之家",
        )

        self.assertFalse(
            self.module.is_non_apple_title_action_using_apple_as_reference_story(
                article.title,
                article.summary,
            )
        )
        self.assertNotEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_ranked_rumor_digest_stays_deferred(self):
        article = article_for(
            self.module,
            "iPhone 18 Pro Rumor Reality Check: 20 Claims Ranked by Likelihood",
            "The article ranks previously reported claims and introduces no new report or Apple action.",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_first_party_app_getting_started_guide_stays_deferred(self):
        article = article_for(
            self.module,
            "Inside iMovie: Getting started with video editing on iPhone and iPad",
            "This guide walks new users through importing clips, arranging a timeline, and exporting a movie.",
            "AppleInsider",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_third_party_owner_launching_on_apple_hardware_stays_deferred(self):
        cases = [
            (
                "倍思提前预热苹果 iPhone 18 Pro 系列外设配件",
                "倍思推出适配 iPhone 的手机壳、充电宝和桌充。",
                "IT之家",
            ),
            (
                "辉瑞推出苹果 Vision Pro 沉浸式体验",
                "辉瑞与创意工作室开发了运行在 Vision Pro 上的药物科普体验。",
                "IT之家",
            ),
        ]

        for title, summary, source in cases:
            with self.subTest(title=title):
                article = article_for(self.module, title, summary, source)
                self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_competitor_benchmark_tied_with_iphone_stays_deferred(self):
        article = article_for(
            self.module,
            "谷歌 Pixel 11 影像获 154 分，与 iPhone 15 Pro 打平",
            "DXOMARK 测试的是 Pixel 11，iPhone 只用于分数比较。",
            "快科技",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_existing_builtin_feature_tip_is_not_a_new_apple_action(self):
        article = article_for(
            self.module,
            "苹果没告诉你：iPhone 自带照片清理器，不用额外装 App",
            "文章教用户在相册中打开既有的重复项目功能。",
            "快科技",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_countdown_what_we_know_article_is_a_roundup(self):
        article = article_for(
            self.module,
            "Six Sleeps Until iPhone 18 Pro: Here's What We Know",
            "Apple will hold its event next week. The article lists previously reported design, battery, chip, and camera rumors.",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_broad_roadmap_does_not_absorb_a_specific_cancellation(self):
        articles = [
            article_for(
                self.module,
                "Apple's big roadmap for new Mac and iPad models revealed: report - 9to5Mac",
                "Omdia published a wide-ranging display-panel roadmap for future MacBook Pro, MacBook Air, iPad mini, iPad Air, and iPad Pro models through 2029.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果折叠iPad/Mac项目被砍掉：华为成了这一赛道的唯一玩家",
                "苹果内部曾立项折叠屏 iPhone 和折叠屏 iPad 两条产品线；Omdia 表示苹果已经叫停 18 至 20 英寸大型可折叠 iPad / MacBook 显示屏项目。",
                "快科技",
                facts=[
                    "这款新品原计划在 2026 年问世，随后被推迟至 2028 年，最终被正式叫停。",
                    "调研机构 Omdia 的最新显示面板报告称折叠屏 MacBook 项目已被取消。",
                ],
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])

    def test_competitor_score_tie_with_detailed_results_stays_deferred(self):
        article = article_for(
            self.module,
            "谷歌 Pixel 11 影像获 154 分，与 iPhone 15 Pro 打平",
            "DXOMARK 公布 Pixel 11 的完整测试结果，并称其与 iPhone 15 Pro 并列。",
            "快科技",
        )

        self.assertEqual(article.relevance_tier, "weak", article.relevance_reason)

    def test_same_multi_device_capability_merges_across_languages(self):
        articles = [
            article_for(
                self.module,
                "HomePods may get surround sound through four connected speakers",
                "Code in audioOS 27 shows a four-speaker setup with new calibration and Party Mode.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果测试 4 台 HomePod 联动的家庭影院环绕声",
                "audioOS 27 Beta 8 的调音文件显示四台设备可组成家庭影院。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, len(event.articles)) for event in events])

    def test_different_multi_device_capability_counts_do_not_merge(self):
        articles = [
            article_for(
                self.module,
                "HomePods may get surround sound through four connected speakers",
                "Code in audioOS 27 shows a four-speaker setup with Party Mode.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "苹果测试 2 台 HomePod 组成家庭影院环绕声",
                "新代码显示两台设备可以组成家庭影院。",
                "IT之家",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 2, [(event.title, len(event.articles)) for event in events])


if __name__ == "__main__":
    unittest.main()
