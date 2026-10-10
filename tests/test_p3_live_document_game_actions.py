"""Source-owned document action and third-party game platform boundaries."""

import unittest

from test_relevance_rules import article_for, load_module


class LiveDocumentGameActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def outcome(self, article):
        profile = self.m.article_reconciliation_profile(article)
        return self.m.resolve_reconciliation_outcome(
            profile, observed_tier="", observed_reason="", observed_category=""
        )

    def test_document_revision_survives_independent_repair_background(self):
        m = self.m
        angled_title = (
            "苹果支持文档不再将 M5 Pro/M6 Mac mini SSD 列为可更换部件，"
            "民间维修仍可扩容"
        )
        angled_lead = (
            "苹果在9月21日更新Mac mini零件支持文档，M5 Pro和M6芯片机型不再将"
            "SSD列为可更换部件。第三方维修工程师表示，仍可焊接NAND芯片扩容。"
        )
        direct_title = "苹果更新 M5 Pro/M6 Mac mini 支持文档，SSD 模块不再列为可更换部件"
        direct_lead = (
            "苹果公司于9月21日更新支持文档，在官方维修体系中，M5 Pro和M6芯片"
            "Mac mini的SSD模块不再列为可更换部件。"
        )
        angled = article_for(m, angled_title, angled_lead, source="cnBeta", facts=[angled_lead])
        direct = article_for(m, direct_title, direct_lead, source="IT之家", facts=[direct_lead])
        physical_title = "New Mac mini NAND report for M6 and M5 Pro"
        physical_lead = (
            'As confirmed by the website "Expand Mac mini," NAND storage in the new M6 and '
            'M5 Pro Mac mini is soldered to the logic board. The old removable modules remain separate.'
        )
        physical = article_for(m, physical_title, physical_lead, source="MacRumors")

        for article in (angled, direct):
            with self.subTest(title=article.title):
                self.assertEqual(self.outcome(article)[::2], ("strong", "hardware_products"))
        groups = [set(a.url for a in event.articles)
                  for event in m.cluster_articles([angled, direct, physical])]
        self.assertIn({angled.url, direct.url}, groups)
        self.assertIn({physical.url}, groups)
        # A publisher's brief dateline before the same Apple subject does not
        # turn the source's first sentence into an unattributed document mention.
        bylined = article_for(
            m, angled_title, "科技媒体9月23日消息，" + angled_lead,
            source="cnBeta", facts=[angled_lead],
        )
        self.assertEqual(self.outcome(bylined)[::2], ("strong", "hardware_products"))
        bylined_groups = [set(a.url for a in event.articles)
                          for event in m.cluster_articles([bylined, direct])]
        self.assertIn({bylined.url, direct.url}, bylined_groups)

    def test_document_relation_requires_apple_completed_update(self):
        from apple_news_core.event_reconciler import _source_owned_named_action

        current_title = "苹果更新 M5 Pro/M6 Mac mini 支持文档，SSD 模块不再列为可更换部件"
        current_lead = (
            "苹果公司于9月21日更新支持文档，在官方维修体系中，M5 Pro和M6芯片"
            "Mac mini的SSD模块不再列为可更换部件。"
        )
        current = article_for(self.m, current_title, current_lead, source="IT之家")
        title = "苹果支持文档提到 M5 Pro/M6 Mac mini SSD，维修商尝试扩容"
        for lead in (
            "苹果计划更新Mac mini零件支持文档，第三方工程师已焊接NAND芯片扩容。",
            "苹果没有更新Mac mini零件支持文档，第三方工程师已焊接NAND芯片扩容。",
            "苹果表示第三方工程师更新了Mac mini零件说明，苹果支持文档并无变化。",
        ):
            with self.subTest(lead=lead):
                self.assertIsNone(_source_owned_named_action(title, lead))
                other = article_for(self.m, title, lead, source="cnBeta")
                groups = [set(a.url for a in event.articles)
                          for event in self.m.cluster_articles([current, other])]
                self.assertIn({current.url}, groups)
                self.assertIn({other.url}, groups)

    def test_cross_platform_game_release_is_not_an_os_release(self):
        m = self.m
        title = "国产冒险 RPG 游戏《星域》移动端开服：iOS / Android / 鸿蒙同步上线"
        lead = (
            "多人在线冒险 RPG《星域》今日正式开服，iOS、Android和鸿蒙平台同步上线，"
            "与PC数据互通。游戏由独立工作室研发、发行公司发行。"
            "游戏功能包括多人协作以及随昼夜天气变化的角色生态。"
        )
        game = article_for(m, title, lead, source="IT之家", facts=[lead])
        self.assertEqual(m.detect_event_kind(title, lead, [lead]), "third_party_ecosystem")
        self.assertEqual(self.outcome(game)[::2], ("weak", "software_systems"))
        events = m.cluster_articles([game])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "weak")
        apple_title = "Apple releases watchOS 28 with a new Siri feature for Apple Watch"
        apple_lead = (
            "Apple today released watchOS 28 with an updated Siri feature. "
            "The report mentions game invitations shared with iOS and Android apps."
        )
        apple = article_for(m, apple_title, apple_lead, source="9to5Mac")
        self.assertEqual(self.outcome(apple)[0], "strong")


if __name__ == "__main__":
    unittest.main()
