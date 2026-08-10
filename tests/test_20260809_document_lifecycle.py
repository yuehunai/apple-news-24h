import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260809_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source="IT之家", facts=None):
    facts = facts or []
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 9, tzinfo=timezone.utc),
        published_raw="2026-08-09T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class AugustNinthDocumentLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_same_first_party_document_appearance_and_removal_form_one_event(self):
        articles = [
            article_for(
                self.module,
                "苹果 Mac 简体中文支持文档更新，Apple 智能阿里千问扩展现身",
                (
                    "苹果官网的 Mac 简体中文使用手册新增‘在 Mac 上配合 Apple 智能使用千问’页面，"
                    "说明 macOS 26.6 用户可在写作工具和 Siri 中调用千问。"
                ),
                "IT之家",
                ["页面列出中国大陆设备、账户和位置条件。"],
            ),
            article_for(
                self.module,
                "苹果终于把千问接进 Siri，中国版 Apple Intelligence 来了",
                (
                    "苹果中国官网 Mac 使用手册出现‘在 Mac 上配合 Apple 智能使用千问’页面，"
                    "写作工具可生成文本或图像，Siri 可调用千问回答请求。"
                ),
                "cnBeta",
            ),
            article_for(
                self.module,
                "刚上线就删了！苹果中国官网删除 Apple 智能接入阿里千问手册",
                (
                    "苹果中国官网随后删除同一份‘在 Mac 上配合 Apple 智能使用千问’使用手册，"
                    "原链接恢复显示 ChatGPT 页面。"
                ),
                "快科技",
            ),
            article_for(
                self.module,
                "苹果中国官网删除 Apple 智能接入阿里千问使用手册",
                (
                    "此前苹果公司官方网站更新的 Mac 简体中文使用手册曾说明 Apple 智能将配合"
                    "阿里巴巴的千问大模型工作，不过目前这份中文操作手册已被删除。"
                ),
                "cnBeta",
            ),
        ]

        events = self.module.cluster_articles(articles)

        self.assertEqual(len(events), 1, [(event.title, [a.title for a in event.articles]) for event in events])
        self.assertEqual({article.url for article in events[0].articles}, {article.url for article in articles})
        self.assertEqual(events[0].category, "software_systems")
        self.assertEqual(events[0].event_kind, "os_app")
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assertEqual(events[0].relevance_reason, "first-party Apple document lifecycle update")

    def test_document_lifecycle_does_not_absorb_a_launch_or_another_document(self):
        qwen_document = article_for(
            self.module,
            "苹果官网使用手册出现 Apple 智能千问扩展说明",
            "苹果 Mac 使用手册新增‘在 Mac 上配合 Apple 智能使用千问’页面。",
            "IT之家",
        )
        qwen_launch = article_for(
            self.module,
            "苹果正式发布中国版 Apple Intelligence 千问扩展",
            "苹果宣布面向中国大陆用户正式上线千问扩展，并开始向 iPhone 和 Mac 推送。",
            "Apple Newsroom",
        )
        private_relay_document = article_for(
            self.module,
            "苹果支持文档撤下 iCloud Private Relay 网络要求说明",
            "苹果官网删除一份介绍 iCloud Private Relay 网络要求的支持文档。",
            "MacRumors",
        )

        events = self.module.cluster_articles([qwen_document, qwen_launch, private_relay_document])

        self.assertEqual(len(events), 3, [(event.title, [a.title for a in event.articles]) for event in events])

    def test_attributed_concrete_roadmap_survives_commentary_framing(self):
        title = "Here's why Apple is skipping its M6 Pro and M6 Max chips to accelerate M7 launch"
        summary = (
            "According to reports from Bloomberg, Apple will skip the M6 Pro, M6 Max and M6 Ultra, "
            "release only the base M6, and move the M7 launch forward to spring 2027. The redesigned "
            "MacBook Pro will use M5 Pro and M5 Max chips, while a base-model MacBook Pro gets M6."
        )

        tier, reason = self.module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "strong", reason)
        self.assertEqual(self.module.choose_category(title, summary), "hardware_products")

    def test_unsourced_commentary_framing_remains_weak(self):
        title = "Here's why the M6 MacBook Pro could be Apple's best value yet"
        summary = (
            "The author argues that Apple should preserve the current design and imagines how a cheaper "
            "configuration could appeal to more buyers; the article contains no new reporting."
        )

        tier, reason = self.module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(tier, "weak", reason)


if __name__ == "__main__":
    unittest.main()
