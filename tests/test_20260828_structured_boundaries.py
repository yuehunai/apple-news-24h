import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "apple_news_20260828_structured_boundaries_test",
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
        published_utc=datetime(2026, 8, 28, tzinfo=timezone.utc),
        published_raw="2026-08-28T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(f"{title} {summary}"),
    )


class StructuredBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_training_words_do_not_invent_apple_intelligence_product(self):
        identity = self.module.build_event_identity(
            "Apple Announces New Education Center in Vietnam",
            "Apple expanded training and skill development for supply-chain employees.",
        )

        self.assertNotIn("apple-intelligence", identity.products)
        self.assertNotIn("apple-intelligence", identity.title_products)

    def test_first_party_education_center_reports_merge_across_languages(self):
        reports = [
            article_for(
                self.module,
                "Apple Announces New Education Center in Vietnam",
                "Apple announced a new Apple Education Center in Hanoi to expand manufacturing training for supplier employees.",
                "MacRumors",
            ),
            article_for(
                self.module,
                "Apple expands educational program for its supply-chain workers in Vietnam",
                "Vietnam is becoming an important manufacturing center as Apple diversifies beyond China; Apple expanded its fund through a new Apple Education Center in Vietnam.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果宣布在越南设立全新教育中心，进一步加大区域人才培养力度",
                "苹果公司正式宣布将在越南设立全新教育中心，通过科技资源与教育项目支持当地学生、教育工作者和社区的技能发展。",
                "cnBeta",
            ),
            article_for(
                self.module,
                "Mac, iPhone, and Apple Vision Pro suppliers in Vietnam get new Apple Education Center",
                "Apple announced a Hanoi education center serving employees at Vietnamese suppliers.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "全球供应链培训已超 10.8 万人，苹果在越南落地首个教育中心",
                "苹果在越南河内建立首个教育中心，为供应链员工提供专业技能培训。",
                "IT之家",
            ),
        ]

        donation = article_for(
            self.module,
            "库克宣布苹果公司将捐款支持西藏吉隆的救援与灾后重建工作",
            "灾害发生后，国家防灾减灾救灾委员会、应急管理部启动国家二级救灾应急响应。",
            "IT之家",
        )
        donation_followup = article_for(
            self.module,
            "西藏吉隆县泥石流灾害令人心痛，库克宣布苹果将捐款支持当地救援与灾后重建",
            "8月28日消息，今天上午，苹果CEO库克发文表示，西藏吉隆县突发的洪水山洪和泥石流灾害令人心痛，我们心系每一位受影响的人，Apple将捐款支持当地的救援与灾后重建工作。",
            "快科技",
        )
        events = self.module.cluster_articles([*reports, donation, donation_followup])
        title_sets = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)
        self.assertIn({article.title for article in reports}, title_sets)
        self.assertIn({donation.title, donation_followup.title}, title_sets)
        education_event = next(
            event for event in events if len(event.articles) == len(reports)
        )
        self.assertEqual(education_event.category, "software_systems")

    def test_event_invitation_interpretations_merge_without_absorbing_schedule(self):
        logo_interpretation = article_for(
            self.module,
            "Apple Event Logo Hints at Two iPhone 18 Pro Features",
            "Apple's logo for its September 9 Surprise and shine event may hint at a variable-aperture camera and a sky-blue finish.",
            "MacRumors",
        )
        chinese_interpretation = article_for(
            self.module,
            "古尔曼解读苹果 iPhone 18 Pro / Max 邀请函：可变光圈、新天蓝色",
            "古尔曼认为邀请函图案暗示可变光圈相机和天蓝色外观。",
            "IT之家",
        )
        schedule = article_for(
            self.module,
            "Apple announces September 9 iPhone event",
            "Apple officially scheduled its fall product event at Apple Park.",
            "9to5Mac",
        )

        events = self.module.cluster_articles(
            [logo_interpretation, chinese_interpretation, schedule]
        )
        title_sets = [{article.title for article in event.articles} for event in events]

        self.assertEqual(len(events), 2, title_sets)
        self.assertIn(
            {logo_interpretation.title, chinese_interpretation.title},
            title_sets,
        )
        self.assertIn({schedule.title}, title_sets)

    def test_mac_mini_generation_does_not_merge_distinct_primary_actions(self):
        roadmap = article_for(
            self.module,
            "Mac Mini's New M6 Chip Coming to These Two Macs Next",
            "A current roadmap report says M6 will move next to the iMac and MacBook Pro.",
            "MacRumors",
        )
        order_adjustment = article_for(
            self.module,
            "苹果为 M4 版 Mac mini 用户未发货订单免费升级 M6 版本",
            "Apple is replacing pending M4 Mac mini orders with M6 models at no charge.",
            "IT之家",
        )
        specifications = article_for(
            self.module,
            "苹果 M6 Mac mini 三项隐藏细节：内存带宽、Thread 与预装系统",
            "The released Mac mini has new memory-bandwidth tiers, Thread support and macOS 27.",
            "IT之家",
        )
        specifications_followup = article_for(
            self.module,
            "苹果 M6 Mac mini 细节曝光：自研 N1 芯片支持 Thread 智能家居协议",
            "The released Mac mini has new memory bandwidth tiers, an N1 chip, Thread support and macOS 27.",
            "快科技",
        )

        events = self.module.cluster_articles(
            [roadmap, order_adjustment, specifications, specifications_followup]
        )

        self.assertEqual(
            len(events),
            3,
            [[article.title for article in event.articles] for event in events],
        )
        self.assertTrue(all(event.category == "hardware_products" for event in events))
        self.assertIn(
            {specifications.title, specifications_followup.title},
            [{article.title for article in event.articles} for event in events],
        )

    def test_third_party_resale_analysis_and_storage_alternative_stay_weak(self):
        resale = article_for(
            self.module,
            "换机苹果 iPhone 18 Pro 参考：SellCell 称旧机回收价 10 天内最高跌幅 20.2%",
            "美国头部二手服务商 SellCell 于 8 月 25 日发布博文，基于以往数据，在苹果新款 iPhone 发布到发售的约 10 天间隔内，其用户手中的旧款 iPhone 二手回收价格损失最高可达 20.2%。",
            "IT之家",
        )
        storage = article_for(
            self.module,
            "Skip Apple's $3,800 storage upgrade with these 8TB SSD",
            "A shopping guide recommends external SSD alternatives to Apple's internal upgrade.",
            "AppleInsider",
        )

        self.assertEqual(resale.relevance_tier, "weak")
        self.assertEqual(storage.relevance_tier, "weak")

    def test_hands_on_story_with_independent_first_party_launch_is_strong(self):
        launch = article_for(
            self.module,
            "Apple's new and cheaper Apple Polishing Cloth is now available",
            "Apple officially launched its second-generation polishing cloth for $9.",
            "AppleInsider",
        )
        hands_on = article_for(
            self.module,
            "69元！唯一降价的苹果单品，博主上手第二代抛光布",
            "快科技 8 月 28 日消息，苹果官方近日上架全新一代抛光布，国行价格由 145 元降至 69 元。",
            "快科技",
        )

        events = self.module.cluster_articles([launch, hands_on])

        self.assertEqual(hands_on.relevance_tier, "strong")
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_mixed_iphone_lineup_does_not_relabel_all_facts_as_ultra(self):
        title = (
            "苹果秋季发布会 6 款新品蓄势待发："
            "iPhone 18 Pro 领衔、iPhone Ultra 首秀"
        )
        facts = [
            "iPhone 18 Pro 将采用 A20 Pro 芯片，并新增深樱桃配色。",
            "iPhone Ultra 配备约 7.7 英寸内屏和两颗后置摄像头。",
            "iPhone 18、iPhone 18e 和 iPhone Air 2 预计延后到 2027 年春季。",
            "Apple Watch Series 12 将升级芯片和健康监测能力。",
        ]

        variants = self.module.compound_article_variants(
            title,
            " ".join(facts),
            facts,
        )
        variant_titles = {variant[0] for variant in variants}

        self.assertNotIn("Apple iPhone Ultra roadmap update", variant_titles)
        self.assertIn("Apple iPhone roadmap update", variant_titles)


if __name__ == "__main__":
    unittest.main()
