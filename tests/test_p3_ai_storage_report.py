"""Current AI model storage observations stay scoped to one OS report action."""

import unittest

from test_relevance_rules import article_for, load_module


class AIStorageReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_same_observed_report_joins_but_other_action_and_version_do_not(self):
        m = self.m
        english = article_for(
            m, "Apple Intelligence Taking up 23GB+ on Some Macs Running macOS 30",
            "After installing macOS 30, Apple downloads an AI model. Apple lists a smaller "
            "storage allowance, but observed use is higher. On an M5 Pro Mac mini running "
            "macOS 30, a reporter measured 23.4GB for Apple Intelligence in System Settings.",
            "MacRumors", ["A reporter measured 23.4GB on an M5 Pro Mac mini running macOS 30."],
        )
        chinese = article_for(
            m, "部分苹果 Mac 升级 macOS 30 后，Apple Intelligence 占用空间超 23GB",
            "安装 macOS 30 后，苹果自动下载 AI 模型。实测占用远高于苹果公布的额度。"
            "一台 M5 Pro Mac mini 运行 macOS 30，一名记者在系统设置中记录到 "
            "Apple Intelligence 占用 23.4GB。",
            "IT之家", ["记者记录到 M5 Pro Mac mini 的 Apple Intelligence 占用 23.4GB。"],
        )
        dot_zero_chinese = article_for(
            m, "部分苹果 Mac 升级 macOS 30.0 后，Apple Intelligence 占用空间超 23GB",
            "安装 macOS 30.0 后，苹果自动下载 AI 模型。实测占用远高于苹果公布的额度。"
            "一台 M5 Pro Mac mini 运行 macOS 30.0，一名记者在系统设置中记录到 "
            "Apple Intelligence 占用 23.4GB空间。",
            "IT之家", ["记者记录到 M5 Pro Mac mini 的 Apple Intelligence 占用 23.4GB空间。"],
        )
        different_action = article_for(
            m, "Apple Intelligence Adds Storage Controls in macOS 30",
            "Apple added a storage control in macOS 30 that lets Mac owners remove a downloaded "
            "model. Earlier storage observations included 23.4GB on an M5 Pro Mac mini.",
            "9to5Mac", ["The current change is the removal control, not a measured storage anomaly."],
        )
        different_version = article_for(
            m, "部分苹果 Mac 升级 macOS 31 后，Apple Intelligence 占用空间超 23GB",
            "安装 macOS 31 后，苹果自动下载 AI 模型。实测占用远高于苹果公布的额度。"
            "一台 M5 Pro Mac mini 运行 macOS 31，一名记者在系统设置中记录到 "
            "Apple Intelligence 占用 23.4GB。",
            "IT之家", ["记者记录到 M5 Pro Mac mini 的 Apple Intelligence 占用 23.4GB。"],
        )
        different_minor_version = article_for(
            m, "部分苹果 Mac 升级 macOS 30.10 后，Apple Intelligence 占用空间超 23GB",
            "安装 macOS 30.10 后，苹果自动下载 AI 模型。实测占用远高于苹果公布的额度。"
            "一台 M5 Pro Mac mini 运行 macOS 30.10，一名记者在系统设置中记录到 "
            "Apple Intelligence 占用 23.4GB。",
            "IT之家", ["记者记录到 M5 Pro Mac mini 的 Apple Intelligence 占用 23.4GB。"],
        )
        articles = [english, chinese, dot_zero_chinese, different_action,
                    different_version, different_minor_version]
        profiles = [m.article_reconciliation_profile(article) for article in articles]
        for index in (0, 1, 2):
            self.assertEqual(m.resolve_reconciliation_outcome(
                profiles[index], observed_tier="", observed_reason="", observed_category="")[::2],
                ("strong", "software_systems"))
        groups = [{article.title for article in event.articles}
                  for event in m.cluster_articles(articles)]
        self.assertEqual(sum(map(len, groups)), len(articles))
        self.assertTrue(any({english.title, chinese.title, dot_zero_chinese.title} <= group
                            for group in groups), groups)
        for distinct in (different_action, different_version, different_minor_version):
            self.assertFalse(any({english.title, distinct.title} <= group for group in groups), groups)
            self.assertFalse(any({chinese.title, distinct.title} <= group for group in groups), groups)


if __name__ == "__main__":
    unittest.main()
