import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260817_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ActionOwnerCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_future_os_feature_proposal_is_editorial_analysis(self):
        title = "It’s time for iOS to have its own Material You - 9to5Mac"
        summary = (
            "Apple has added lock screen personalization, icon tinting, and Liquid Glass over time. "
            "iOS 27 has not even released yet, so I may be getting ahead of myself. "
            "I feel like thematic app color schemes would be a logical next step."
        )

        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(identity.content_form, "analysis")
        self.assertEqual(tier, "weak", reason)

    def test_non_apple_vendor_owns_chinese_platform_app_update(self):
        title = "Mozilla 宣布正为苹果 iOS 版 Firefox 火狐浏览器引入原生广告拦截功能"
        summary = (
            "Mozilla 发文，计划为 iOS 版 Firefox 加入基于 EasyList 的原生广告拦截功能，"
            "并正分批向部分用户推送实验版。"
        )

        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "IT之家")

        self.assertEqual(identity.scope, "third-party-context")
        self.assertFalse(
            self.module.is_direct_apple_os_component_change_story(title, summary)
        )
        self.assertEqual(tier, "weak", reason)

    def test_first_party_safari_platform_change_remains_strong(self):
        title = "iOS 27 adds native content blocking controls to Safari"
        summary = (
            "Apple added new system-level content blocking controls to Safari in iOS 27 beta 5."
        )

        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "9to5Mac")

        self.assertEqual(identity.scope, "apple-direct")
        self.assertEqual(identity.content_form, "news")
        self.assertEqual(tier, "strong", reason)


if __name__ == "__main__":
    unittest.main()
