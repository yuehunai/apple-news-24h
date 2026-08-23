import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "apple_news_20260823_editorial_owner_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, *, source="Test Source"):
    tier, reason = module.classify_relevance_tier(title, summary, [], source)
    return module.Article(
        source=source,
        url=f"https://example.com/{abs(hash((title, summary)))}",
        title=title,
        summary=summary,
        key_facts=[],
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 23, tzinfo=timezone.utc),
        published_raw="2026-08-23T00:00:00Z",
        published_source="fixture",
        confidence="detail",
        tokens=module.article_tokens(title, summary),
        event_kind=module.detect_event_kind(title, summary, []),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=set(),
    )


class EditorialActionOwnerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def final_tier(self, title, summary, *, source="Test Source"):
        article = article_for(self.module, title, summary, source=source)
        return self.module.cluster_articles([article])[0].relevance_tier

    def test_settings_advice_without_a_new_apple_action_is_weak(self):
        cases = (
            (
                "iPhone拍照总是模糊：这项默认设置建议关掉",
                "本文建议用户关闭一个默认相机选项，以改善连续拍摄时的成片效果。",
            ),
            (
                "iPhone photos keep looking blurry? Turn off this default setting",
                "A settings walkthrough tells owners how to change an existing Camera option.",
            ),
        )
        for title, summary in cases:
            with self.subTest(title=title):
                self.assertEqual(self.final_tier(title, summary), "weak")

    def test_single_user_repair_workaround_without_apple_action_is_weak(self):
        cases = (
            (
                "MacBook Pro屏幕摔坏官方维修要4700元！老哥反手用一根橡皮筋解决：成本几乎为零",
                "一位 Reddit 用户分享了个人解决方案，用旧 MacBook 和 Moonlight 开源工具充当损坏设备的显示器。",
            ),
            (
                "Reddit user fixes a broken MacBook display with an old Mac and an open-source tool",
                "One owner shared a personal workaround after deciding not to pay for an official repair.",
            ),
        )
        for title, summary in cases:
            with self.subTest(title=title):
                self.assertEqual(self.final_tier(title, summary), "weak")

    def test_competitor_launch_using_apple_as_positioning_is_weak(self):
        cases = (
            (
                "惠普推出MacBook Neo竞品OmniBook 3：搭载骁龙X芯片",
                "惠普正式推出 OmniBook 3，并把它定位为 MacBook Neo 的竞争产品。",
            ),
            (
                "HP launches OmniBook 3 as a MacBook Neo rival",
                "HP introduced its own laptop and used Apple's MacBook as the market comparison.",
            ),
        )
        for title, summary in cases:
            with self.subTest(title=title):
                self.assertEqual(self.final_tier(title, summary), "weak")

    def test_direct_first_party_actions_remain_strong(self):
        cases = (
            (
                "iOS 27 adds a new Camera setting for faster capture",
                "Apple added the option in the current iOS 27 beta.",
            ),
            (
                "Apple expands Self Service Repair to the M6 MacBook Pro",
                "Apple announced that customers can order parts and tools for the new model.",
            ),
            (
                "Apple launches MacBook Neo with the M6 chip",
                "Apple introduced the new first-party Mac at its product event.",
            ),
        )
        for title, summary in cases:
            with self.subTest(title=title):
                self.assertEqual(self.final_tier(title, summary), "strong")


if __name__ == "__main__":
    unittest.main()
