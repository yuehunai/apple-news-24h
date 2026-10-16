"""Source-local actions cannot borrow a stage from adjacent context."""

import unittest
from dataclasses import replace

from test_relevance_rules import article_for, load_module


class SourceLocalStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_denied_release_does_not_take_the_public_fix_key(self):
        m = self.m
        announced = article_for(
            m, "Apple releases watchOS 28.0.1 with restart fix",
            "Apple today released watchOS 28.0.1 to fix unexpected Apple Watch restarts.",
            "Example News",
        )
        denied = article_for(
            m, "watchOS 28.0.1 has not been released to fix restart bug",
            "Apple has not released watchOS 28.0.1. Users still report unexpected "
            "Apple Watch restarts, and the fix is only planned.",
            "Another News",
        )
        positive = m.article_reconciliation_profile(announced)
        negative = m.article_reconciliation_profile(denied)
        self.assertTrue(any("public-fix-release" in key for key in positive.event_keys))
        self.assertFalse(any("public-fix-release" in key for key in negative.event_keys))
        self.assertNotEqual(m.reconciliation_seed_compatible(positive, negative), True)

    def test_active_denial_and_planned_watch_fix_do_not_join_a_release(self):
        m = self.m
        released = article_for(
            m, "Apple releases watchOS 28.0.1 restart fix",
            "Apple today released watchOS 28.0.1 to fix unexpected Apple Watch restarts.",
            "Release News",
        )
        denied = article_for(
            m, "Apple has not released watchOS 28.0.1 restart fix",
            "Apple has not released watchOS 28.0.1. A restart fix is still planned.",
            "Denied News",
        )
        planned = article_for(
            m, "Apple plans watchOS 28.0.1 restart fix",
            "Apple plans to release watchOS 28.0.1 later to fix unexpected restarts.",
            "Planned News",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (released, denied, planned)]
        self.assertTrue(any("public-fix-release" in key for key in profiles[0].event_keys))
        for profile in profiles[1:]:
            self.assertFalse(any("public-fix-release" in key for key in profile.event_keys))
        groups = [{article.source for article in event.articles}
                  for event in m.cluster_articles([released, denied, planned])]
        for other in (denied, planned):
            self.assertFalse(any({released.source, other.source} <= group
                                 for group in groups), groups)

    def test_historical_filing_context_cannot_become_a_new_disclosure(self):
        m = self.m
        historical = article_for(
            m, "OpenAI's old ChatGPT Apple court filing revisited",
            "In a filing last year, OpenAI said its Apple ChatGPT integration "
            "underperformed. There is no new court filing today.",
            "Example News",
        )
        profile = m.article_reconciliation_profile(historical)
        self.assertFalse(any("current-court-filing-disclosure" in key
                             for key in profile.event_keys))

    def test_background_display_roadmap_cannot_own_a_camera_report(self):
        m = self.m
        camera = article_for(
            m, "Next iPhone Pro camera report details sensor changes",
            "The current report concerns a camera sensor change. In the background, "
            "last year's 20th anniversary iPhone design report said a curved "
            "display would postpone COE and LTPO+ adoption.",
            "Example News",
        )
        profile = m.article_reconciliation_profile(camera)
        self.assertFalse(any("anniversary-iphone:display-design" in key
                             for key in profile.event_keys))

    def test_ceo_interview_background_cannot_own_launch_store_or_event_display(self):
        m = self.m
        interview_title = "苹果CEO：iPhone Duo设计为何如此"
        interview_lead = "苹果CEO特努斯近日接受媒体专访，首次解读 iPhone Duo 的设计理念。"
        # A topic-only excerpt requires source evidence, not an eligible event
        # fabricated through the old interview retrieval key.
        interview_profile = m.source_text_profile(interview_title, interview_lead, [], "Interview News")
        launch = article_for(
            m, "Apple unveils iPhone Duo in two configurations",
            "Apple unveiled iPhone Duo today in two configurations. CEO Ternus "
            "discussed the design in an earlier interview.", "Launch News",
        )
        store = article_for(
            m, "Apple Store maintenance begins ahead of iPhone Duo preorders",
            "Apple Store is temporarily unavailable ahead of iPhone Duo preorders. "
            "CEO Ternus discussed the phone in an earlier interview.", "Store News",
        )
        display = article_for(
            m, "Apple shows iPhone Duo at an awards event",
            "Apple displayed iPhone Duo at the event, where CEO Ternus appeared. "
            "In an earlier interview, Ternus discussed its design.", "Event News",
        )
        profiles = [interview_profile, *(m.article_reconciliation_profile(article)
                    for article in (launch, store, display))]
        self.assertEqual(interview_profile.bound_claim.action, 'leadership-report')
        self.assertFalse(interview_profile.eligibility.resolved)
        from apple_news_core.event_reconciler import profile_pair_decision
        for profile in profiles[1:]:
            self.assertNotEqual(profile_pair_decision(interview_profile, profile), 'match')
            self.assertNotEqual(profile_pair_decision(profile, interview_profile), 'match')
        self.assertEqual(len(m.cluster_articles([launch, store, display])), 3)

    def test_cross_language_event_display_is_not_design_interview(self):
        m = self.m
        english = article_for(
            m, "CEO Ternus attending Emmy Awards with iPhone Duo",
            "At the Emmy Awards, John Ternus showed an unreleased iPhone Duo "
            "to attendees and press.", "English News",
        )
        chinese = article_for(
            m, "特努斯出席艾美奖，展示 iPhone Duo",
            "苹果高管特努斯出席艾美奖颁奖典礼，并展示尚未发售的 "
            "iPhone Duo。", "Chinese News",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (english, chinese)]
        self.assertTrue(profiles[0].event_keys & profiles[1].event_keys)
        self.assertFalse(any("interview-remarks" in key for profile in profiles
                             for key in profile.event_keys))
        groups = [{article.source for article in event.articles}
                  for event in m.cluster_articles([english, chinese])]
        self.assertTrue(any({english.source, chinese.source} <= group
                            for group in groups), groups)

    def test_current_apple_action_does_not_borrow_muse_or_beats_background(self):
        m = self.m
        muse = article_for(
            m, "Meta unveils Muse Charm handheld AI device",
            "Meta announced its Muse Charm handheld device with a screen today.",
            "Muse News",
        )
        beats = article_for(
            m, "Apple launches Beats 360 over-ear headphones",
            "Apple launched Beats 360 headphones today.", "Beats News",
        )
        apple_muse = article_for(
            m, "Apple updates Apple TV interface",
            "Apple updated the Apple TV interface today. Earlier, Meta introduced "
            "the Muse Charm handheld device.", "Apple TV News",
        )
        apple_beats = article_for(
            m, "Apple updates Apple TV app",
            "Apple updated the Apple TV app today. Beats 360 headphones were "
            "launched last year.", "Apple App News",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (muse, beats, apple_muse, apple_beats)]
        self.assertTrue(any("meta:muse-charm" in key for key in profiles[0].event_keys))
        launch_key = "primary-claim:beats-model-360:product-launch"
        self.assertIn(launch_key, profiles[1].event_keys)
        self.assertFalse(any("meta:muse-charm" in key for key in profiles[2].event_keys))
        self.assertNotIn(launch_key, profiles[3].event_keys)

    def test_future_home_devices_do_not_join_released_camera_service_fees(self):
        m = self.m
        devices = article_for(
            m, "New Apple TV and HomePod mini on track to launch this year",
            "A source today reiterated a rumor that new Apple TV and HomePod mini "
            "devices remain on track to launch this year.", "Hardware News",
        )
        fees = article_for(
            m, "Apple Home security camera features cost a monthly fee",
            "With the public release of iOS 28 and tvOS 28, Apple Intelligence "
            "camera summaries cost $29.99 a month.", "Software News",
        )
        profiles = [m.article_reconciliation_profile(article)
                    for article in (devices, fees)]
        self.assertTrue(any("future-device-lineup-report" in key
                            for key in profiles[0].event_keys))
        self.assertTrue(any("current-software-subscription-pricing" in key
                            for key in profiles[1].event_keys))
        self.assertFalse(profiles[0].event_keys & profiles[1].event_keys)
        groups = [{article.source for article in event.articles}
                  for event in m.cluster_articles([devices, fees])]
        self.assertFalse(any({devices.source, fees.source} <= group
                             for group in groups), groups)

    def test_chinese_card_rate_denial_keeps_its_predicate_scope(self):
        m = self.m
        title = "苹果上调 Apple Card 储蓄账户利率"
        affirmative = article_for(
            m, title,
            "苹果今日将 Apple Card 储蓄账户利率从 4.1% 上调至 4.2%。",
            "Affirmative News",
        )
        denied = replace(article_for(
            m, title,
            "苹果尚未将 Apple Card 储蓄账户利率从 4.1% 上调至 4.2%。",
            "Denied News",
        ), url="https://example.com/denied-card-rate")
        neighbor = replace(article_for(
            m, title,
            "另一家银行尚未上调自身利率，但苹果今日将 Apple Card 储蓄账户"
            "利率从 4.1% 上调至 4.2%。",
            "Neighbor News",
        ), url="https://example.com/neighbor-card-rate")
        profiles = [m.article_reconciliation_profile(article)
                    for article in (affirmative, denied, neighbor)]
        self.assertTrue(profiles[0].event_keys & profiles[2].event_keys)
        self.assertFalse(profiles[0].event_keys & profiles[1].event_keys)
        groups = [{article.source for article in event.articles}
                  for event in m.cluster_articles([affirmative, denied, neighbor])]
        self.assertTrue(any({affirmative.source, neighbor.source} <= group
                            for group in groups), groups)
        self.assertFalse(any({affirmative.source, denied.source} <= group
                             for group in groups), groups)


if __name__ == "__main__":
    unittest.main()
