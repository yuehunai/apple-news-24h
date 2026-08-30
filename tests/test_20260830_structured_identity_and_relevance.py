import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260830_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source, facts=None):
    facts = list(facts or [])
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((title, summary)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc),
        published_raw="2026-08-30T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts])),
    )


class StructuredIdentityAndRelevance20260830(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_platform_compatibility_milestone_merges_cross_language_reports(self):
        articles = [
            article_for(
                self.module,
                "Asahi Linux nears M3 support release, with M4 and M5 work continuing",
                "The Asahi Linux project says M3 support is almost ready for release, while M4 and M5 enablement remains in development.",
                "AppleInsider",
            ),
            article_for(
                self.module,
                "Asahi Linux 即将发布苹果 M3 芯片支持，M4、M5 适配仍在推进",
                "Asahi Linux 团队表示 M3 支持已接近正式发布，M4 和 M5 支持尚在开发中。",
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual({article.source for article in events[0].articles}, {"AppleInsider", "cnBeta"})

    def test_hardware_repair_cost_estimate_merges_translated_reports(self):
        articles = [
            article_for(
                self.module,
                "苹果 iPhone Ultra 折叠屏手机维修费用曝光：更换内屏费用或超 1 千美元",
                "业内预测这款折叠屏手机的内屏维修费用约 1155 美元，远高于三星 Galaxy Z Fold 8。",
                "IT之家",
                [
                    "维修公司 Correct 创始人认为，这台手机换内屏的价格大约是 1,155 美元。",
                    "三星 Galaxy Z Fold 8 的屏幕维修费用大约是 772 美元。",
                ],
            ),
            article_for(
                self.module,
                "苹果iPhone Ultra折叠屏手机维修费用曝光：换个内屏不便宜！",
                "第三方维修机构结合苹果过往定价与屏幕成本，测算内屏更换费用将突破旗舰机型上限。",
                "快科技",
                [
                    "内屏更换价格大约会达到1155美元，折合人民币差不多7800元。",
                    "三星 Galaxy Z Fold 8 的内屏维修费用约 772 美元，苹果估价高出一半以上。",
                ],
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(events[0].category, "hardware_products")

    def test_unreleased_apple_hardware_launch_roadmap_merges_cross_language_reports(self):
        articles = [
            article_for(
                self.module,
                "Apple will be launching its first AI smart glasses next year",
                "A new supply-chain report says Apple's first smart glasses are set to debut in 2027.",
                "9to5Mac",
            ),
            article_for(
                self.module,
                "苹果首款 AI 智能眼镜被曝 2027 年发布",
                "供应链消息称苹果计划在 2027 年推出首款 AI 智能眼镜。",
                "IT之家",
            ),
            article_for(
                self.module,
                "苹果 AI 眼镜明年登场：首款产品 2027 年发布",
                "最新报告称苹果智能眼镜将在 2027 年亮相。",
                "快科技",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [event.title for event in events])
        self.assertEqual(events[0].category, "hardware_products")
        self.assertEqual({article.source for article in events[0].articles}, {"9to5Mac", "IT之家", "快科技"})

    def test_event_highlights_roundup_stays_weak(self):
        article = article_for(
            self.module,
            "机圈春晚！苹果秋季发布会看点都在这了",
            "文章依据供应链与媒体既有信息，汇总 iPhone 18 Pro、折叠屏 iPhone、Apple Watch、AirPods 和 HomePod 等发布会候选产品。",
            "快科技",
            [
                "从目前汇总的供应链与媒体信息来看，发布会候选名单包括多条既有产品传闻。",
                "文章汇总 A20 Pro、可变光圈、折叠屏尺寸、AirPods 摄像头和 HomePod 等不同产品线信息。",
                "以上信息目前仍停留在爆料阶段，最终答案需等待发布会揭晓。",
            ],
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_first_person_product_usage_story_stays_weak(self):
        article = article_for(
            self.module,
            "As a relatively new Vision Pro user, this is my favorite way to use it",
            "The author describes a personal workflow using existing Vision Pro features and does not report a new Apple action.",
            "9to5Mac",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_single_user_support_eligibility_experiment_stays_weak(self):
        article = article_for(
            self.module,
            "MacBook user deliberately cycles battery hoping for a free replacement, but health barely moves",
            "One M1 Max MacBook owner repeatedly discharged the battery to qualify for AppleCare service, reporting only a personal result.",
            "快科技",
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)

    def test_versioned_os_background_does_not_promote_third_party_app_availability(self):
        article = article_for(
            self.module,
            "iOS 27 版 Siri AI 上线前，苹果 CarPlay 已接入 4 个第三方 AI 应用",
            "科技媒体报道，在 Siri AI 上线之前，CarPlay 目前已接入支持 4 款第三方 AI 聊天机器人。",
            "IT之家",
            [
                "苹果自 iOS 26.4 起支持对话类应用接入 CarPlay，并计划在 iOS 27 后把 Siri AI 纳入平台。",
                "继 ChatGPT、Perplexity、Grok 之后，CarPlay 界面出现 Meta AI。",
                "部分用户能看到 Meta AI 图标，但启动时提示当前账号暂不支持。",
            ],
        )

        event = self.module.cluster_articles([article])[0]

        self.assertEqual(event.relevance_tier, "weak", event.relevance_reason)


if __name__ == "__main__":
    unittest.main()
