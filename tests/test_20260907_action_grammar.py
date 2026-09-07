import unittest

from test_20260905_claim_ownership_boundaries import article_for, load_module


class ActionGrammar20260907(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def groups(self, pairs):
        return self.m.cluster_articles([article_for(self.m, title, lead, source=str(i)) for i, (title, lead) in enumerate(pairs)])

    def test_platform_project_name_and_release_grammar(self):
        titles = [
            'Asahi Linux rolls out support for M3 Apple Silicon',
            'Asahi Linux 系统正式适配苹果 M3/M3 Pro/M3 Max 芯片',
            '告别macOS！Asahi Linux官宣正式支持M3/M3 Pro/M3 Max芯片：但GPU还得等等',
            'Asahi Linux宣布正式支持苹果M3系列芯片',
        ]
        events = self.groups([(t, 'The Asahi Linux project now officially supports Macs with M3 chips. GPU acceleration is still in development.') for t in titles])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 4)
        self.assertEqual(events[0].category, 'software_systems')
        self.assertEqual(events[0].relevance_tier, 'ecosystem')

    def test_compatibility_generation_and_milestone_remain_separate(self):
        pairs = [
            ('Asahi Linux now supports M3 Apple Silicon', 'M3 support is now available.'),
            ('Asahi Linux now supports M4 Apple Silicon', 'M4 support is now available.'),
            ('Asahi Linux nears release for M3 Apple Silicon', 'M3 driver support is close to release.'),
            ('Asahi Linux adds GPU acceleration for M3 Apple Silicon', 'The GPU driver now supports hardware acceleration.'),
            ('Aurora Linux now supports M3 Apple Silicon', 'The Aurora Linux project now officially supports M3.'),
        ]
        self.assertEqual(len(self.groups(pairs)), len(pairs))

    def test_participation_negation_owns_schedule_background(self):
        pairs = [
            ('Tim Cook或十几年来首度缺席苹果秋季发布会', '库克可能不会在今年苹果发布会视频中出镜。'),
            ('古尔曼：库克不会在苹果秋季发布会视频中出现，现在是特努斯时代', '苹果将于9月9日举行新品发布会，特努斯接替库克任 CEO。'),
            ('古尔曼爆料：库克将不再出镜苹果秋季发布会 特努斯担任发布会主角', '苹果9月1日换帅，发布会将在9月9日举行。'),
        ]
        events = self.groups(pairs)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 3)
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'hardware_products')

    def test_participant_state_person_and_event_are_boundaries(self):
        pairs = [
            ('Tim Cook will skip Apple September keynote', 'Cook will not appear in the video.'),
            ('Tim Cook will appear at Apple September keynote', 'Cook will participate.'),
            ('John Ternus will skip Apple September keynote', 'Ternus will not attend.'),
            ('Tim Cook will skip Apple WWDC keynote', 'Cook will not participate.'),
            ('Apple September keynote scheduled for September 9', 'Apple has announced the event date.'),
        ]
        self.assertEqual(len(self.groups(pairs)), len(pairs))

    def test_service_monetization_review_cross_language(self):
        events = self.groups([
            ('Apple might soon make App Store changes to raise revenue, increase margins: report', 'Apple is reportedly considering changing its App Store business model, including developer membership fees.'),
            ('古尔曼：苹果考虑调整 App Store 以提高收入和利润率', '苹果正酝酿调整 App Store 以提升利润率，可能提高开发者会员费。'),
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')

    def test_service_monetization_not_general_feature_or_actual_price(self):
        pairs = [
            ('Apple considers App Store changes to increase margins', 'Apple is considering developer fees.'),
            ('Apple raises App Store developer membership fee', 'Apple announces new membership pricing.'),
            ('Apple changes App Store search features', 'Apple adds a search interface.'),
            ('Apple considers Apple Music changes to increase margins', 'Apple considers subscription changes.'),
        ]
        self.assertEqual(len(self.groups(pairs)), len(pairs))

    def test_generic_app_use_headlines_stay_deferred(self):
        for title, lead in [
            ('Play iPhone 18 Pro Apple Keynote Bingo with this app', "Use this Bingo Card Generator to play along with Apple's September event."),
            ('Track Apple keynote predictions with this app', 'Use this independent app to track your predictions.'),
            ('用这款应用记录苹果发布会预测', '这款应用可以帮助用户记录发布会预测。'),
        ]:
            with self.subTest(title=title):
                event = self.groups([(title, lead)])[0]
                self.assertEqual(event.relevance_tier, 'weak')

    def test_first_party_apps_and_ecosystem_remain_eligible(self):
        pairs = [
            ('Apple releases a new Developer app for its keynote', 'Apple released its official app with a new schedule feature.'),
            ('Apple updates Keynote with new presentation features', 'Apple introduces new tools to its Keynote app.'),
            ('Apple opens a new CarPlay API for third-party apps', 'Apple changes CarPlay platform access for third-party applications.'),
            ('Apple launches a new Developer experience with this app', 'Apple released its official Developer app with new first-party conference features.'),
        ]
        for event in self.groups(pairs):
            self.assertNotEqual(event.relevance_tier, 'weak', event.title)

    def test_chip_compatible_app_is_not_an_operating_system_milestone(self):
        event = self.groups([('Acme Player now supports M3 Apple Silicon', 'The third-party media app now supports M3 Macs running macOS.')])[0]
        self.assertEqual(event.relevance_tier, 'weak')

    def test_monetization_opinion_and_vendor_do_not_promote_or_bridge(self):
        pairs = [
            ('Apple considers App Store business model changes', 'Apple is reviewing its App Store business model and developer fees.'),
            ('Opinion: Apple could change the App Store business model', 'This opinion proposes what Apple should do, not a reported plan.'),
            ('Opinion: Spotify could change its App Store business model', 'Spotify is considering its own subscription pricing, not an Apple platform change.'),
        ]
        events = self.groups(pairs)
        retained = [e for e in events if e.relevance_tier != 'weak']
        self.assertEqual(len(retained), 1)
        self.assertEqual([a.title for a in retained[0].articles], [pairs[0][0]])
        self.assertEqual(sum(len(e.articles) for e in events if e.relevance_tier == 'weak'), 2)

    def test_unrecognized_headline_wording_can_use_same_owned_lead(self):
        for titles, lead in [
            (['Apple considers App Store changes to increase margins', 'Apple weighs App Store changes to increase margins'], 'Apple is reviewing its App Store business model and developer fees.'),
            (['Tim Cook will skip Apple September keynote', 'Tim Cook will be absent from Apple September keynote'], 'Tim Cook will not appear at the September Apple event.'),
        ]:
            with self.subTest(titles=titles):
                self.assertEqual(len(self.groups([(t, lead) for t in titles])), 1)

    def test_released_platform_not_changed_by_pending_component_background(self):
        events = self.groups([
            ('Asahi Linux now supports M3 Apple Silicon', 'GPU support is close to release. M3 platform support is now available.'),
            ('Asahi Linux rolls out support for M3 Apple Silicon', 'M3 systems can now boot Linux.'),
        ])
        self.assertEqual(len(events), 1)

    def test_participation_opinion_and_podcast_cannot_join_report(self):
        title = 'Tim Cook will skip Apple September keynote'
        events = self.groups([
            (title, 'A new report confirms Cook will not appear in the keynote.'),
            ('Opinion: ' + title, 'This is commentary predicting what Cook should do.'),
            ('Podcast: ' + title, 'A podcast speculates about whether Cook will participate.'),
        ])
        retained = [e for e in events if e.relevance_tier != 'weak']
        self.assertEqual(len(retained), 1)
        self.assertEqual([a.title for a in retained[0].articles], [title])

    def test_owned_first_lead_supplies_missing_platform_stage(self):
        lead = 'Asahi Linux has released support for M3 Macs.'
        events = self.groups([
            ('Asahi Linux adds support for M3 Apple Silicon', lead),
            ('Asahi Linux adds support for M3 Apple Silicon, now available', lead),
        ])
        self.assertEqual(len(events), 1)

    def test_platform_release_with_component_limitation_is_same_stage(self):
        lead = 'Asahi Linux has released support for M3 Macs without GPU acceleration.'
        self.assertEqual(len(self.groups([
            ('Asahi Linux adds support for M3 Apple Silicon', lead),
            ('Asahi Linux adds support for M3 Apple Silicon, now available', lead),
        ])), 1)

    def test_platform_lead_stage_must_belong_to_target_generation(self):
        self.assertEqual(len(self.groups([
            ('Asahi Linux adds support for M3 Apple Silicon', 'Asahi Linux has released support for M2 Macs. M3 work is ongoing.'),
            ('Asahi Linux now supports M3 Apple Silicon', 'Asahi Linux has released support for M3 Macs.'),
        ])), 2)


if __name__ == '__main__':
    unittest.main()
