"""Current source actions, distinct stages and functional categories."""
import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20260930_source_actions.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,9,30,tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_competitor_camera_style_does_not_borrow_apple_comparison(self):
        events, _ = self.cluster_sources('ab856fc1cba97fcd16a2d58c')
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        cases = [
            ('曝 Meridian 新手机重 218 克，照片风格向苹果 iPhone 靠拢',
             '消息源爆料 Meridian 新手机增加重量，拍照色彩向 iPhone 靠拢。'),
            ('Meridian camera colors move closer to iPhone',
             'A leaker revealed the new Meridian phone camera style today.'),
            ('Meridian phone mimics Apple iPhone camera colors',
             'The Meridian phone changes its photo rendering to match iPhone.'),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                groups = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(groups)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in groups))
        for title, lead in [
            ('Apple updates iPhone camera colors to move closer to Meridian',
             'Apple changed iPhone camera rendering in a new update today.'),
            ('苹果 iPhone 更新照片处理，色彩向 Meridian 靠拢',
             '苹果今天更新 iPhone 的照片处理算法。'),
        ]:
            with self.subTest(title=title):
                groups = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(groups)
                self.assertTrue(all(e.relevance_tier == 'strong' for e in groups))

    def test_captured_first_party_app_update_keeps_software_and_one_release(self):
        ids = ['298d6831de67860ce30802dd', '5f561a46470797eb17730b07',
               'f8c75b350dc3e479067651cb', 'e5375bc15b35f9d0ea03a709']
        events, articles = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_apple_named_app_does_not_borrow_its_host_device_category(self):
        cases = [
            ('Apple Meridian App Updated With New Features',
             'The free Apple Meridian app for iPhone was updated today.'),
            ('Apple Meridian for iPhone updated with new features',
             'Apple is rolling out a new version of its Apple Meridian app today.'),
            ('Apple Meridian update uses the latest iOS features',
             'An update to Apple Meridian improves its iPhone app.'),
            ('苹果 Meridian App 升至 2.4.0：新增共享功能',
             '苹果更新 Meridian App，为 iPhone 用户增加共享功能。'),
            ('Apple updates its Meridian app for iPhone',
             'Apple released an update to its Meridian app for iPhone today.'),
            ('Apple Meridian updated for iPhone',
             'Apple is rolling out its Apple Meridian app update today.'),
            ('苹果 Apple Meridian App 升至 2.4.0：新增共享功能',
             '苹果更新 Apple Meridian App，为 iPhone 用户增加共享功能。'),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(events)
                self.assertTrue(all(e.category == 'software_systems' for e in events))
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        self.assertEqual(len(self.m.cluster_articles([
            article_for(self.m, title, lead) for title, lead in cases])), 1)

    def test_app_frame_keeps_release_versions_and_invitation_verbs_distinct(self):
        from apple_news_core.event_identity import build_event_identity, source_operation_frame
        title = 'Apple invites developers to submit their latest apps'
        lead = 'Apple invites developers to submit apps for an upcoming event.'
        identity = build_event_identity(title, lead)
        frame = source_operation_frame(title, lead, (), identity)
        self.assertTrue(frame is None or frame.action != 'software-update')
        articles = [article_for(self.m, f'Apple Meridian App updated to version {version}',
                    f'Apple released version {version} of its Meridian app for iPhone.')
                    for version in ['2.4.0', '2.5.0']]
        self.assertEqual(len(self.m.cluster_articles(articles)), 2)
        for headline_version in [True, False]:
            articles = [article_for(self.m,
                f'Apple Meridian App updated to {version}' if headline_version
                else 'Apple Meridian App updated today',
                f'Apple released version {version} of its Meridian app for iPhone.')
                for version in ['2.4.0', '2.5.0']]
            self.assertEqual(len(self.m.cluster_articles(articles)), 2)
        planned = article_for(self.m, 'Apple Meridian App will be updated next month',
                              'Apple plans to release its Meridian app update next month.')
        current = article_for(self.m, 'Apple Meridian App updated today',
                              'Apple released its Meridian app update today.')
        self.assertEqual(len(self.m.cluster_articles([planned, current])), 2)

    def test_first_party_app_frame_requires_a_current_affirmative_update(self):
        from apple_news_core.event_identity import source_first_party_app_frame
        for title in ['Apple Meridian App was not updated today',
                      'Apple Meridian App updated last year']:
            with self.subTest(title=title):
                self.assertIsNone(source_first_party_app_frame(
                    title, 'The Apple Meridian app is available for iPhone.'))
        self.assertIsNone(source_first_party_app_frame(
            'Apple Meridian App updated today',
            'Apple denied that the Meridian app was updated today.'))

    def test_captured_service_country_expansion_joins_the_same_action(self):
        ids = ['94d5d8d8c63d30e0386dbe42', 'bc2083c201cf4aea28061913']
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')
        self.assertEqual(self.source_ids(events[0]), set(ids))
        facts = ' '.join(events[0].key_facts)
        for name in ['Albania', 'Brunei', 'Burkina Faso', 'Pakistan']:
            self.assertIn(name, facts)

    def test_captured_service_client_beta_is_not_its_country_rollout(self):
        beta = '6adbd2fea6d3e32ced2f03db'
        regions = ['94d5d8d8c63d30e0386dbe42', 'bc2083c201cf4aea28061913']
        events, _ = self.cluster_sources(beta, *regions)
        self.assertEqual(len(events), 2)
        self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                         {frozenset([beta]), frozenset(regions)})
        for event in events:
            self.assertEqual(event.category, 'software_systems')
            self.assertEqual(event.relevance_tier, 'strong')

    def test_captured_owned_code_report_is_software_not_accessory_compatibility(self):
        sid = 'd16eac467b36b7b6799ce5f3'
        events, _ = self.cluster_sources(sid)
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        self.assertTrue(all(e.category == 'software_systems' for e in events))
        self.assertEqual(set().union(*(self.source_ids(e) for e in events)), {sid})
        ids = [sid, 'aabfa3f8a1fd3f4acf143307', '2f79228189a4116d8d94ed9c']
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')
        self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_apple_owned_home_device_modifiers_do_not_transfer_ownership(self):
        from apple_news_core.event_identity import build_event_identity
        for modifier in ['upcoming', 'new', 'rumored', 'redesigned']:
            identity = build_event_identity(
                f"Code reveals features of Apple's {modifier} Home Hub",
                'A researcher discovered its unreleased StandBy capability in beta code.')
            self.assertIn('apple-home-hub', identity.title_products)
            self.assertEqual(identity.scope, 'apple-direct')
        identity = build_event_identity("Code reveals features of Meridian's upcoming Home Hub",
                                        'The accessory can connect to an iPhone.')
        self.assertNotIn('apple-home-hub', identity.title_products)

    def test_named_face_does_not_replace_other_current_code_discoveries(self):
        title = "Code reveals new StandBy controls for Apple's upcoming Home Hub"
        prefix = 'Researchers found new StandBy controls in Apple beta code today. '
        genuine = article_for(self.m,
            "Code reveals new Photo Face for Apple's upcoming Home Hub",
            'Researchers found new Photo Face controls in Apple beta code today.')
        for background in ['Photo Face was discovered last year and is unchanged.',
                           'Meridian uses Photo Face in its own smart display.']:
            article = article_for(self.m, title, prefix + background)
            profile = self.m.article_reconciliation_profile(article)
            self.assertFalse(any(':photo-face:' in key for key in profile.event_keys))
            self.assertEqual(len(self.m.cluster_articles([article, genuine])), 2)
        hardware = article_for(self.m,
            "Code reveals new camera hardware for Apple's upcoming Home Hub",
            'Researchers found a new camera sensor identifier in Apple beta code today. '
            'The report also mentions the existing Photo Face software.')
        events = self.m.cluster_articles([hardware])
        self.assertTrue(events)
        self.assertTrue(all(e.category == 'hardware_products' for e in events))

    def test_first_party_service_client_release_keeps_platform_version_and_stage(self):
        from apple_news_core.event_identity import build_event_identity, source_operation_frame
        def frame(title, lead):
            return source_operation_frame(title, lead, (), build_event_identity(title, lead))
        title = 'Apple Books 3.2 beta released for Windows'
        lead = 'Apple released version 3.2 beta of its Apple Books app for Windows today.'
        release = frame(title, lead)
        self.assertIsNotNone(release)
        self.assertEqual(release.category, 'software_systems')
        self.assertEqual(release.tier, 'strong')
        for other_title, other_lead in [
            (title.replace('3.2', '3.3'), lead.replace('3.2', '3.3')),
            (title.replace('Windows', 'Android'), lead.replace('Windows', 'Android')),
            (title.replace(' beta', ''), lead.replace(' beta', '')),
        ]:
            self.assertEqual(len(self.m.cluster_articles([
                article_for(self.m, title, lead),
                article_for(self.m, other_title, other_lead)])), 2)
        self.assertIsNone(frame(title, 'Apple denied releasing its Apple Books app for Windows.'))
        self.assertIsNone(frame(title, 'Last year Apple released its Apple Books app for Windows.'))

    def test_service_client_release_binds_version_stage_and_host_to_its_own_claim(self):
        from apple_news_core.event_identity import build_event_identity, source_operation_frame
        def frame(title, lead):
            return source_operation_frame(title, lead, (), build_event_identity(title, lead))
        lead = 'Apple released version 7.0 beta of its Apple Music app for Android today.'
        titles = ['Apple Music for Android updated to 7.0',
                  'Apple Music 7.0 beta released for Android',
                  'Apple Music for Android 16.0 updated to version 7.0']
        self.assertEqual(len(self.m.cluster_articles([
            article_for(self.m, title, lead) for title in titles])), 1)
        for title in titles:
            release = frame(title, lead)
            self.assertIsNotNone(release)
            self.assertEqual(release.action, 'client-beta-release')
            self.assertEqual(release.period, 'app-version:7.0')
        self.assertIsNone(frame('Apple Music 7.0 beta coming to Android',
            'Apple released version 7.0 of its Apple Music app for Windows today. '
            'The Android app will receive the beta next month.'))

    def test_service_expansion_uses_current_territories_not_background(self):
        articles = [
            article_for(self.m, 'Apple Arcade lands in two new countries',
                        'Apple Arcade is now available in Belgium and Denmark. Subscribers can play its games.'),
            article_for(self.m, 'Apple Arcade expands to two countries',
                        'Apple expanded Apple Arcade availability to Denmark and Belgium today.'),
            article_for(self.m, 'Apple Arcade expands to two other countries',
                        'Apple Arcade is now available in Austria and Finland. Subscribers can play its games.'),
        ]
        events = self.m.cluster_articles(articles)
        self.assertEqual(len(events), 2)
        self.assertTrue(any(len(e.articles) == 2 for e in events))
        from apple_news_core.event_identity import build_event_identity, source_operation_frame
        for title, lead in [
            ('Apple Arcade has not expanded to more countries',
             'Last year Apple Arcade was available in Belgium and Denmark.'),
            ('Apple Arcade expands its game catalog',
             'Apple added new games today. Previously the service became available in Belgium and Denmark.'),
            ('Apple Arcade expands to two new countries',
             'Apple denied expanding Apple Arcade availability to Belgium and Denmark.'),
            ('Apple Arcade expands to two new countries',
             'Apple Arcade competes with Meridian, which is now available in Belgium and Denmark.'),
        ]:
            with self.subTest(title=title):
                frame = source_operation_frame(title, lead, (), build_event_identity(title, lead))
                self.assertTrue(frame is None or frame.action != 'availability-expansion')
        planned = article_for(self.m, 'Apple Arcade expands to two new countries',
                              'Apple plans to expand Apple Arcade availability to Belgium and Denmark.')
        self.assertEqual(len(self.m.cluster_articles([articles[0], planned])), 2)

    def test_captured_camera_app_updates_do_not_borrow_host_hardware_action(self):
        ids = ['4f3bf6eb6d746d6960cfc2fb', '4fb85f6f188a93e9c699bea6']
        for sid in ids:
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_captured_message_ordering_is_the_vendors_service(self):
        for sid in ['41fc3f9fc34dc0aa11299613', 'bbb5b46814f23732f33e636f']:
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))
        events, _ = self.cluster_sources('9f682ee238760d7cf952dc1a')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        self.assertTrue(all(e.category == 'hardware_products' for e in events))

    def test_message_delivery_alone_does_not_establish_platform_interoperability(self):
        for title, lead in [
            ("Meridian unveils AI food ordering through Apple's Messages app",
             'Meridian is inviting iPhone users to try a new ordering assistant. A phone number connects text requests to the Meridian account.'),
            ('Meridian now lets you order by text in Apple Messages',
             'Meridian today launched text ordering through the existing Messages app. The service uses SMS and saved payment details.'),
        ]:
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))
        title = "Meridian launches food ordering through Apple's Messages app"
        lead = 'Apple introduced a new Messages API and approved the Meridian integration today. Meridian launched its ordering service using that new API.'
        events = self.m.cluster_articles([article_for(self.m, title, lead)])
        self.assertTrue(all(e.relevance_tier in {'strong', 'ecosystem'} for e in events))
        self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_named_app_capabilities_keep_the_app_owner_in_natural_headlines(self):
        for title, lead in [
            ('The Prism camera app now offers full control of the iPhone 18 Pro aperture',
             "A new update to Meridian's Prism camera app for iPhone adds manual aperture control."),
            ('Prism 4.2 pro camera arrives with iPhone 18 Pro support',
             'Meridian released the Prism pro camera app for iPhone. Today Prism adds aperture control.'),
            ('镜光相机应用现已支持 iPhone 18 Pro 光圈控制',
             '独立开发者发布镜光相机应用更新，新增 iPhone 光圈控制。'),
            ('镜光相机应用现已支持 iPhone 18 Pro 手动光圈',
             '独立开发者发布镜光相机应用更新，新增 iPhone 手动光圈功能。'),
            ('镜光相机应用更新，新增 iPhone 光圈调节',
             '独立开发者更新了镜光相机应用，为 iPhone 增加光圈调节功能。'),
        ]:
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_app_ownership_does_not_demote_apple_release_or_platform_change(self):
        for title, lead in [
            ('The Prism camera app now supports iPhone 18 Pro',
             'Apple released its new Prism camera app for iPhone today.'),
            ('Apple updates Final Cut Camera for iPhone 18 Pro',
             'Apple released an update to its Final Cut Camera app with aperture controls.'),
            ('iOS 27 adds an API for third-party camera apps',
             'Apple announced a new iOS 27 API for third-party camera applications.'),
        ]:
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_captured_tracking_accessories_remain_weak_hardware(self):
        for sid in ['11b755d180f0885632424562', '60538962b59ae9ad929523d6']:
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == 'hardware_products' for e in events))

    def test_named_app_variants_do_not_share_an_incomplete_owner_key(self):
        articles = [article_for(self.m, f'The Prism {edition} camera app now offers iPhone aperture control',
                    f'Meridian updated its Prism {edition} camera app for iPhone.')
                    for edition in ['Pro', 'Lite']]
        self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_short_application_headlines_keep_editions_and_release_ownership(self):
        articles = [article_for(self.m, f'Prism {edition} 4.2 arrives with iPhone 18 Pro support',
                    f'Meridian updated its Prism {edition} camera app for iPhone.')
                    for edition in ['Pro', 'Lite']]
        self.assertEqual(len(self.m.cluster_articles(articles)), 2)
        a = article_for(self.m, 'Prism Lite 4.2 arrives with iPhone 18 Pro support',
                        'Apple released its new Prism Pro camera app for iPhone. Meridian updated Prism Lite separately.')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in self.m.cluster_articles([a])))

    def test_app_platform_integration_requires_current_owned_api_evidence(self):
        title = "The Prism camera app adds support for Apple's new camera API"
        for lead, allowed in [
            ('Apple introduced a new iOS camera API today and approved the Prism integration. Meridian updated its Prism camera app to use that new API.', True),
            ('Last year Apple introduced an iOS camera API. Meridian updated its Prism camera app today.', False),
            ('Apple did not introduce a new iOS camera API or approve the Prism integration. Meridian updated its Prism camera app.', False),
        ]:
            with self.subTest(lead=lead):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(all((e.relevance_tier in {'strong', 'ecosystem'}) == allowed for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_message_service_cannot_borrow_an_unrelated_platform_api(self):
        title = "Meridian unveils AI food ordering through Apple's Messages app"
        lead = 'Apple introduced a new API for Safari extensions today. Meridian launched ordinary SMS ordering through a phone number.'
        events = self.m.cluster_articles([article_for(self.m, title, lead)])
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_current_api_claims_keep_each_relationship_polarity(self):
        messages = "Meridian unveils AI food ordering through Apple's Messages app"
        app = "The Prism camera app adds support for Apple's new camera API"
        for title, lead in [
            (messages, 'Apple introduced a new Messages API today. Meridian does not use that new API; its service only takes SMS orders through a phone number.'),
            (messages, 'Apple introduced a new Messages API today but has not approved the Meridian integration. Meridian launched ordinary SMS ordering through a phone number.'),
            (app, 'Researchers deny that Apple introduced a new iOS camera API today. Meridian updated its Prism camera app.'),
        ]:
            with self.subTest(lead=lead):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_api_use_participles_keep_local_negation(self):
        title = "Meridian unveils AI food ordering through Apple's Messages app"
        for use in ['without using', 'without actually using', 'not using',
                    'never using', 'without ever using', 'using']:
            with self.subTest(use=use):
                lead = 'Apple introduced a new Messages API today. Meridian launched its SMS ordering service ' + use + ' the new API.'
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(events)
                self.assertTrue(all((e.relevance_tier in {'strong', 'ecosystem'}) == (use == 'using') for e in events))
                self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_apple_release_of_another_app_does_not_supply_ownership(self):
        a = article_for(self.m, 'The Prism Lite camera app now supports iPhone 18 Pro',
                        'Apple released its new Prism Pro camera app for iPhone. Meridian updated Prism Lite separately.')
        events = self.m.cluster_articles([a])
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_physical_tracker_and_its_software_keep_distinct_types(self):
        for title, lead, category in [
            ('Orion launches a tracking tag compatible with iPhone',
             'Orion announced a new physical tracking tag.', 'hardware_products'),
            ('星原发布蓝牙追踪器', '星原推出新的蓝牙追踪器，支持 iOS。', 'hardware_products'),
            ('Orion updates tracker firmware for iPhone users',
             'Orion released new firmware for its tracking tag.', 'software_systems'),
            ('Orion launches a tracker app for iPhone',
             'Orion released a new tracking application for iPhone.', 'software_systems'),
        ]:
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                self.assertTrue(all(e.category == category for e in events))

    def test_captured_web_exploit_is_software_and_does_not_project_preorder_background(self):
        ids = ['8ae59a3bce206a13db9f124f', '963bd441007f0cffbe0a5a17']
        for sid in ids:
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all(e.category == 'software_systems' for e in events))
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        events, output = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        material = json.dumps(output, ensure_ascii=False)
        for word in ['Safari', 'DarkSword', 'MetaMask', 'Phantom', 'Trust Wallet',
                     'Coinbase Wallet', 'Exodus', 'Tonkeeper', 'April', 'March']:
            self.assertIn(word, material)
        required = ' '.join(output[0]['must_include_facts'])
        for word in ['MetaMask', 'Phantom', 'Trust Wallet', 'Coinbase Wallet',
                     'Exodus', 'Tonkeeper', 'April', 'March']:
            self.assertIn(word, required)

    def test_current_web_exploit_requires_its_own_platform_attack_path(self):
        for title, lead in [
            ('Fake iPhone preorder page uses a browser exploit',
             'Researchers report the page uses the NightBlade exploit chain on older unpatched iPhones. Just visiting the page is enough to launch the attack. Apple patched the flaw last year.'),
            ('假预购网页利用系统漏洞攻击 iPhone',
             '研究人员发现该网页利用 NightBlade 攻击链绕过 iOS 安全机制，用户仅打开网页就会安装恶意软件，窃取钥匙串密码。'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m, title, lead)
                self.assertEqual(a.relevance_tier, 'strong')
                self.assertEqual(a.category, 'software_systems')
        for lead in [
            'The fake page asks iPhone users to enter passwords into a form. It does not exploit iOS or install malware.',
            'The page uses the NightBlade exploit chain against a third-party game app on iOS. The iOS security mechanism is unaffected.',
            'Last year the page used the NightBlade exploit chain on older unpatched iPhones. Just visiting the page was enough to launch an attack. Today researchers review that past campaign.',
            'The page does not use the NightBlade exploit chain against older unpatched iPhones. Opening the page does not install malware.',
        ]:
            with self.subTest(lead=lead):
                a=article_for(self.m,'Fake iPhone preorder page reported',lead)
                self.assertEqual(a.relevance_tier,'weak')

    def test_distinct_web_exploit_chains_and_real_preorders_stay_separate(self):
        sources=[article_for(self.m, 'Fake iPhone preorder page uses a browser exploit',
                    f'Researchers report the page uses the {name} exploit chain on older unpatched iPhones. Just visiting the page is enough to launch the attack.')
                 for name in ['NightBlade', 'DayShield']]
        sources.append(article_for(self.m, 'Apple announces early iPhone Duo preorder preparation',
                        'Apple will let customers get ready for iPhone Duo pre-orders on October 12.'))
        self.assertEqual(len(self.m.cluster_articles(sources)),3)

    def test_web_attack_denial_and_app_owned_delivery_do_not_promote(self):
        for lead in [
            'Researchers deny that the page uses the NightBlade exploit chain on older unpatched iPhones. Just visiting the page is enough to launch the attack, according to the discredited claim.',
            'The page uses the NightBlade exploit chain against a game app on older unpatched iPhones, but it cannot bypass iOS security.',
            'The page uses the NightBlade exploit chain on older unpatched iPhones, but opening the page does not install malware or launch an attack.',
        ]:
            with self.subTest(lead=lead):
                a=article_for(self.m,'Fake iPhone preorder page reported',lead)
                self.assertEqual(a.relevance_tier,'weak')

    def test_web_attack_facts_leave_another_actor_and_platform_unassigned(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        lead='The page uses the NightBlade exploit chain on older unpatched iPhones. Just visiting the page is enough to launch the attack.'
        for other,support in [
            ('Separately, Orion malware targets Android phones and steals passwords from game accounts.',
             'The payload sends recovered keychain data to its server.'),
            ('Orion 攻击链针对 iPhone 窃取钱包密码。', '该恶意软件将密码发送到服务器。'),
        ]:
            with self.subTest(other=other):
                evidence=ArticleEvidence('web-mixed','9to5Mac','https://example.com/web',
                    'Fake iPhone preorder page uses a browser exploit',lead,'news',
                    tuple(EvidenceUnit(str(i),'p',text,'body',i) for i,text in enumerate([lead,other,support])))
                projections,remaining,excluded=self.m.project_article_evidence(evidence)
                self.assertEqual(len(projections),1)
                self.assertFalse(any('Orion' in fact for p in projections for fact in p.key_facts))
                self.assertFalse(any(support in fact for p in projections for fact in p.key_facts))
                self.assertIn(('1',0,len(other)),remaining)
                self.m.validate_evidence_dispositions(evidence,projections,remaining,excluded)

    def test_captured_physical_accessories_keep_hardware_category_and_weak_tier(self):
        for sid in ['3de72a79e20175a5a1c71ddb', 'ce9d30b3c2d3f7ef4873c8ca']:
            events, _ = self.cluster_sources(sid)
            self.assertTrue(events)
            self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
            self.assertTrue(all(e.category == 'hardware_products' for e in events))

    def test_unfamiliar_physical_accessories_do_not_borrow_runtime_category(self):
        for title, lead in [
            ('Nova launches a new Ethernet adapter', 'Nova launched a physical network adapter with an aluminum enclosure and one Ethernet port. It supports Mac, Windows and Linux computers.'),
            ('Nova launches an Ethernet adapter with a configuration app for Mac', 'Nova launched a physical network adapter with an Ethernet port. It includes an optional configuration application.'),
            ('星河推出万兆网卡', '星河发布了一款网卡，提供有线网络接口与铝制机身，兼容 Mac 和 Windows 电脑。'),
            ('600 元，北极游戏手柄限定版开售', '这款手柄有透明扳机键和电池盖，兼容游戏主机、Windows 和 iOS 设备。'),
        ]:
            with self.subTest(title=title):
                a = article_for(self.m, title, lead, source='IT之家')
                self.assertEqual(a.relevance_tier, 'weak')
                self.assertEqual(a.category, 'hardware_products')

    def test_accessory_software_remains_software_with_physical_device_context(self):
        for title, lead in [
            ('Nova launches an Ethernet adapter driver for macOS', 'Nova released software for its network adapter. The driver adds settings for Mac users.'),
            ('Nova launches new game controller firmware for iOS devices', 'Nova released firmware for its controller, with updated button mapping.'),
            ('Nova releases new firmware for its game controller', 'Nova released firmware for its controller, with updated button mapping.'),
            ('北极发布游戏手柄配套软件更新', '北极更新了手柄应用的按钮映射界面，支持 iOS 设备。'),
            ('Nova releases software to configure its game controller', 'Nova released a macOS configuration app for its game controller. The app adds button remapping.'),
            ('北极发布软件以配置游戏手柄', '北极推出一款 macOS 软件，用于配置游戏手柄的按钮映射。'),
        ]:
            with self.subTest(title=title):
                a = article_for(self.m, title, lead, source='IT之家')
                self.assertEqual(a.relevance_tier, 'weak')
                self.assertEqual(a.category, 'software_systems')

    def test_newsroom_html_navigation_does_not_consume_article_link_budget(self):
        source = self.sources['Apple Newsroom']
        links = ''.join(f'<a href="/us/shop/goto/account?item={i}">Apple Store Account</a>'
                        for i in range(self.m.MAX_PAGE_LINKS + 5))
        urls = ['https://www.apple.com/newsroom/2026/09/apple-unfamiliar-launch/',
                'https://www.apple.com/sg/newsroom/2026/09/apple-another-announcement/',
                'https://www.apple.com/befr/newsroom/2026/09/apple-new-announcement/',
                'https://www.apple.com/benl/newsroom/2026/09/apple-new-announcement/',
                'https://www.apple.com/chde/newsroom/2026/09/apple-new-announcement/',
                'https://www.apple.com/ca/fr/newsroom/2026/09/apple-new-announcement/']
        links += ''.join(f'<a href="{url}">Apple announces a new service</a>' for url in urls)
        actual = self.m.parse_html_links(links, source.pages[0], source)
        self.assertEqual([row.url for row in actual], urls)

    def test_newsroom_feed_and_listing_reject_non_article_destinations(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        source = self.sources['Apple Newsroom']
        keep = 'https://www.apple.com/newsroom/2026/09/apple-unfamiliar-launch/'
        urls = [keep, 'https://account.apple.com/',
                'https://www.apple.com/us/shop/goto/account',
                'https://apps.apple.com/us/app/apple-store/id375380948',
                'https://www.apple.com/newsroom/archive/',
                'https://www.apple.com/newsroom/2026/09/']
        feed = '<rss><channel>' + ''.join(
            f'<item><title>Apple announces a new service</title><link>{url}</link></item>'
            for url in urls) + '</channel></rss>'
        page = ''.join(f'<a href="{url}">Apple announces a new service</a>' for url in urls)
        with TemporaryDirectory() as cache, patch.object(
                self.m, 'fetch_url', side_effect=lambda url, *a, **kw: feed if url in source.feeds else page):
            actual = self.m.collect_candidates(source, Path(cache), {})
        self.assertEqual([row.url for row in actual], [keep])

    def test_other_publishers_keep_undated_article_discovery(self):
        source = self.sources['MacRumors']
        url = 'https://www.macrumors.com/how-to/a-new-system-capability/'
        rows = self.m.parse_html_links(
            f'<a href="{url}">Apple introduces a new system capability</a>', source.pages[0], source)
        self.assertEqual([row.url for row in rows], [url])

    def test_captured_cross_platform_app_vulnerabilities_are_not_apple_bulletins(self):
        articles=self.source_articles('52a2a1f1d1a2737b53464c3c')
        for article in articles:
            text=' '.join([article.summary,*article.key_facts])
            self.assertFalse(self.m.is_direct_apple_security_bulletin_research_story(article.title,text))
            self.assertFalse(self.m.is_direct_apple_platform_security_impact_story(article.title,text))
        events,_=self.cluster_sources('52a2a1f1d1a2737b53464c3c')
        self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_third_party_patch_ownership_is_not_changed_by_runtime_platforms(self):
        for title,lead in [
            ('RemoteBridge fixes critical vulnerabilities on macOS',
             'RemoteBridge released version 8.2 to fix vulnerabilities in its desktop application, which runs on Windows, Linux and macOS.'),
            ('macOS version of RemoteBridge receives security fixes',
             'RemoteBridge patched a vulnerability in its application that allowed arbitrary code execution on macOS. Apple has not issued a patch.'),
            ('RemoteBridge 修复高危漏洞，影响 macOS 用户',
             'RemoteBridge 软件存在访问控制漏洞，影响 Windows、Linux 和 macOS 用户。厂商已发布新版应用修复，攻击者此前可以执行任意代码。'),
            ('RemoteBridge releases security update for its Mac app',
             'RemoteBridge fixed vulnerabilities allowing arbitrary code execution in its own application. macOS Gatekeeper and security checks are unaffected.'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,source='IT之家')
                self.assertFalse(self.m.is_direct_apple_security_bulletin_research_story(title,lead))
                self.assertFalse(self.m.is_direct_apple_platform_security_impact_story(title,lead))
                self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'weak')

    def test_owned_apple_security_patches_and_platform_attacks_remain_strong(self):
        for title,lead in [
            ('Apple credits outside researcher for iOS security fixes',
             'Apple issued an iOS security bulletin and patched the vulnerabilities reported by an independent researcher.'),
            ('macOS 27.0.1 patches security vulnerabilities',
             'Apple released macOS 27.0.1 to fix vulnerabilities in the system kernel.'),
            ('研究人员发现 macOS 代码签名绕过漏洞',
             '研究人员发现漏洞可绕过 macOS 代码签名与安全检查，执行任意代码。'),
        ]:
            a=article_for(self.m,title,lead,source='IT之家')
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong',title)

    def test_security_background_cannot_promote_an_apps_own_vulnerability(self):
        title='macOS version of RemoteBridge receives security fixes'
        lead='RemoteBridge patched a vulnerability in its application that allowed arbitrary code execution on macOS. '
        for background in [
            'The flaw does not bypass Gatekeeper and Apple security mechanisms are unaffected.',
            'Apple patched a separate macOS kernel vulnerability last year.',
            'Last year Apple patched a separate macOS kernel vulnerability.',
            '该漏洞无法绕过 macOS 代码签名，苹果安全机制不受影响。',
        ]:
            a=article_for(self.m,title,lead+background,source='IT之家')
            self.assertFalse(self.m.is_direct_apple_security_bulletin_research_story(title,lead+background),background)
            self.assertFalse(self.m.is_direct_apple_platform_security_impact_story(title,lead+background),background)
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'weak',background)
            self.assertEqual(self.m.cluster_articles([a])[0].relevance_tier,'weak',background)

    def test_current_security_patch_survives_old_discovery_or_other_old_patches(self):
        title='Apple issues macOS security update to fix a kernel vulnerability'
        for lead in [
            'Apple issued a macOS security update and patched a kernel vulnerability discovered last year.',
            'Last year Apple patched a different macOS vulnerability. Today Apple issued a new security update and fixed the current kernel vulnerability.',
        ]:
            self.assertTrue(self.m.is_direct_apple_security_bulletin_research_story(title,lead))
            a=article_for(self.m,title,lead,source='IT之家')
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')

    def test_captured_current_ceo_report_projects_owned_actions_despite_old_role(self):
        articles=self.source_articles('98442f26a5a82e1878f312c6')
        claims={a.bound_claim.subject:a.bound_claim for a in articles if a.bound_claim}
        for subject,category in [('apple:organization','hardware_products'),
                                 ('apple:management','hardware_products'),
                                 ('apple:hardware-engineering','hardware_products'),
                                 ('apple:applecare','software_systems'),
                                 ('apple:services-business','software_systems')]:
            self.assertIn(subject,claims)
            self.assertEqual(claims[subject].category,category)
        self.assertEqual(claims['apple:applecare'].action,'workforce-plan-held')
        events,_=self.cluster_sources('98442f26a5a82e1878f312c6')
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def test_colon_keeps_an_owned_operation_but_not_a_former_figures_advice(self):
        for title,lead,tier in [
            ('苹果新CEO启动组织改革：加速产品开发',
             '苹果新任CEO正与同事讨论组织精简计划。报道回顾，他是苹果前硬件工程负责人。','strong'),
            ('Apple CEO starts an overhaul: faster product development',
             'Apple CEO has begun restructuring the organization. He was formerly Apple hardware engineering chief.','strong'),
            ('前苹果高管：公司应该精简管理层',
             '前苹果高管在专栏中建议公司精简管理层；没有报道新的苹果组织改革或公司行动。','weak'),
        ]:
            self.assertEqual(self.m.is_former_apple_figure_commentary_without_new_apple_action(title,lead),
                             tier=='weak',title)
            if tier=='strong':
                self.assertIsNotNone(self.m.organization_action_frame(title),title)

    def test_referred_causal_uncertainty_does_not_change_workforce_stage(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        for operation,stage in [('苹果计划裁减5000个AppleCare岗位。','workforce-plan'),
                                ('苹果已经裁减5000个AppleCare岗位。','workforce-reduction')]:
            qualification='不过，目前没有证据表明这5000个岗位全部是因为人工智能取代人工客服而被取消。'
            evidence=ArticleEvidence('cause-test','IT之家','https://example.com/cause',operation,operation,'news',
                (EvidenceUnit('operation','p',operation,'body',0),
                 EvidenceUnit('cause','p',qualification,'body',1)))
            projections,_,_=self.m.project_article_evidence(evidence)
            self.assertEqual({p.claim.action for p in projections},{stage})
            self.assertTrue(any(qualification in p.key_facts for p in projections))

    def joined(self, ids, category, tier='strong'):
        for order in [ids, ids[::-1]]:
            events,_ = self.cluster_sources(*order)
            self.assertEqual(len(events),1,[e.title for e in events])
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertEqual((events[0].category,events[0].relevance_tier),(category,tier))

    def test_viewership_is_not_a_trailer_or_its_adapted_book(self):
        metric=['25b115884e12211212394926','4a4255dd20d9ed4fb38629ed']
        trailer='4faed26b59e0f6cd221f25c7'
        self.joined(metric,'software_systems')
        events,_=self.cluster_sources(*metric,trailer)
        self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                         {frozenset(metric),frozenset([trailer])})
        p=self.m.article_reconciliation_profile(self.source_articles(trailer)[0])
        self.assertTrue(any('nocturne' in key and 'trailer' in key for key in p.event_keys))

    def test_app_removal_inquiry_does_not_absorb_company_explanations(self):
        inquiry='7bd2b9debaa1f1f95a1090b5'
        replies=['19937819c4a48547e66d0cd9','3f3667c62e5e31fdde9731b5','8c9c123e39b0984596af31da']
        self.joined(replies,'software_systems')
        for order in [[inquiry,*replies],[*replies[::-1],inquiry]]:
            events,_=self.cluster_sources(*order)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                             {frozenset([inquiry]),frozenset(replies)})

    def test_app_removal_explanation_inquiry_and_delisting_are_distinct_actions(self):
        rows=[
            ('Apple explains why it removed TrailMap from the App Store',
             'Apple published its letter explaining last year\'s removal of TrailMap from the App Store.'),
            ('Lawmaker questions Apple over removal of TrailMap from the App Store',
             'Senator Jordan Lane sent Apple a letter this week demanding a review of its decision to remove TrailMap.'),
            ('Apple removes TrailMap from the App Store',
             'Apple removed TrailMap from the App Store today for violating its review guidelines.'),
        ]
        articles=[article_for(self.m,t,l,source='MacRumors') for t,l in rows]
        self.assertEqual(len(self.m.cluster_articles(articles)),3)

    def test_app_removal_inquiries_bind_sender_and_application(self):
        rows=[
            ('Lawmaker questions Apple over removal of TrailMap from the App Store',
             'Senator Jordan Lane sent Apple a letter demanding a review of its removal of TrailMap.'),
            ('Senator Jordan Lane questions Apple over TrailMap removal from the App Store',
             'Senator Jordan Lane sent Apple a letter demanding a review of its removal of TrailMap.'),
            ('Lawmaker challenges Apple over removal of TrailMap from the App Store',
             'Senator Avery Park sent Apple a letter demanding a review of its removal of TrailMap.'),
            ('Lawmaker seeks review of Apple removal of RiverMap from the App Store',
             'Senator Jordan Lane sent Apple a letter demanding a review of its removal of RiverMap.'),
        ]
        articles=[article_for(self.m,t,l,source='MacRumors') for t,l in rows]
        events=self.m.cluster_articles(articles)
        self.assertEqual({frozenset(a.title for a in e.articles) for e in events},
                         {frozenset([articles[0].title,articles[1].title]),
                          frozenset([articles[2].title]),frozenset([articles[3].title])})

    def test_app_removal_explanation_keeps_polarity_and_planned_stage(self):
        rows=[
            ('Apple explains why it removed TrailMap from the App Store',
             'Apple published a letter explaining its removal of TrailMap from the App Store.'),
            ('Apple plans to explain why it removed TrailMap from the App Store',
             'Apple will publish a letter about its removal of TrailMap next week.'),
            ('Apple does not explain why it removed TrailMap from the App Store',
             'Apple has not published an explanation of its removal of TrailMap.'),
        ]
        events=self.m.cluster_articles([article_for(self.m,t,l,source='MacRumors') for t,l in rows])
        self.assertEqual(len(events),3)

    def test_app_removal_correspondence_keeps_explicit_letter_period(self):
        for titles,statement in [
            (['Apple explains why it removed TrailMap from the App Store',
              'Apple tells lawmaker why it removed TrailMap from the App Store'],
             'Apple explained its removal of TrailMap from the App Store.'),
            (['Senator Jordan Lane questions Apple over TrailMap removal from the App Store',
              'Senator Jordan Lane challenges Apple over TrailMap removal from the App Store'],
             'Senator Jordan Lane demanded Apple review its removal of TrailMap.'),
        ]:
            articles=[article_for(self.m,title,f'In a July {year} letter, {statement}',source='MacRumors')
                      for title,year in zip(titles,[2025,2026])]
            self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_app_removal_background_does_not_replace_another_explanation(self):
        reply=article_for(self.m,'Apple explains why it removed TrailMap from the App Store',
                          'Apple published its letter about the removal of TrailMap from the App Store.',source='MacRumors')
        settings=article_for(self.m,'Apple explains new privacy controls in Siri AI',
                             'Apple explains the new privacy controls in Siri AI. Last year Apple removed TrailMap from the App Store.',source='MacRumors')
        self.assertEqual(len(self.m.cluster_articles([reply,settings])),2)

    def test_requested_app_removal_explanation_is_the_lawmakers_inquiry(self):
        reply=article_for(self.m,'Apple explains why it removed TrailMap from the App Store',
                          'Apple published a letter explaining its removal of TrailMap from the App Store.',source='MacRumors')
        questions=[article_for(self.m,title,
                    'Senator Jordan Lane sent Apple a letter demanding an explanation for its removal of TrailMap from the App Store.',source='MacRumors')
                   for title in ['Senator Jordan Lane asks Apple to explain why it removed TrailMap from the App Store',
                                 'Senator Jordan Lane asks Apple to explain removal of TrailMap from the App Store',
                                 'Senator Jordan Lane questions Apple over TrailMap removal from the App Store']]
        for order in [[reply,*questions],[*questions[::-1],reply]]:
            events=self.m.cluster_articles(order)
            self.assertEqual({frozenset(a.title for a in e.articles) for e in events},
                             {frozenset([reply.title]),frozenset(a.title for a in questions)})

    def test_app_removal_inquiry_stage_is_not_part_of_the_sender_name(self):
        rows=[
            ('Senator Jordan Lane questions Apple over TrailMap removal from the App Store',
             'Senator Jordan Lane sent Apple a letter about its removal of TrailMap.', 'removal-inquiry','strong'),
            ('Senator Jordan Lane plans to question Apple over TrailMap removal from the App Store',
             'Senator Jordan Lane plans to send Apple a letter about its removal of TrailMap next week.', 'removal-inquiry-planned','strong'),
            ('Senator Jordan Lane has not asked Apple about TrailMap removal from the App Store',
             'Senator Jordan Lane has not sent Apple a letter about its removal of TrailMap.', 'removal-inquiry-unconfirmed','weak'),
        ]
        articles=[]
        for title,lead,action,tier in rows:
            article=article_for(self.m,title,lead,source='MacRumors')
            profile=self.m.article_reconciliation_profile(article)
            self.assertIn('primary-claim:apple:app-store-removal:trailmap:inquirer:jordan-lane:'+action,
                          profile.event_keys)
            self.assertEqual(profile.relevance_tier,tier)
            articles.append(article)
        self.assertEqual(len(self.m.cluster_articles(articles)),3)

    def test_app_removal_letter_period_binds_sentence_final_dates(self):
        for titles,statement in [
            (['Apple explains why it removed TrailMap from the App Store',
              'Apple tells lawmaker why it removed TrailMap from the App Store'],
             'Apple explained its removal of TrailMap from the App Store'),
            (['Senator Jordan Lane questions Apple over TrailMap removal from the App Store',
              'Senator Jordan Lane challenges Apple over TrailMap removal from the App Store'],
             'Senator Jordan Lane questioned Apple about its removal of TrailMap from the App Store'),
        ]:
            articles=[article_for(self.m,title,f'{statement} in a July {year} letter.',source='MacRumors')
                      for title,year in zip(titles,[2025,2026])]
            self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_app_removal_reply_does_not_borrow_the_requesters_letter_date(self):
        rows=[
            ('Apple explains why it removed TrailMap from the App Store',
             "In a July 2026 letter, Apple explained its removal of TrailMap from the App Store in response to Senator Jordan Lane's July 2025 letter."),
            ('Apple tells lawmaker why it removed TrailMap from the App Store',
             'Apple explained its removal of TrailMap from the App Store in a July 2026 letter.'),
        ]
        articles=[article_for(self.m,title,lead,source='MacRumors') for title,lead in rows]
        for article in articles:
            keys=self.m.article_reconciliation_profile(article).separation_keys
            self.assertIn('source-report-period:letter:2026:7',keys)
            self.assertNotIn('source-report-period:letter:2025:7',keys)
        self.assertEqual(len(self.m.cluster_articles(articles)),1)

    def test_distinct_os_component_actions_stay_separate(self):
        ids=['097602ef7db4acde60fc5b7b','97fb635da1b71590effad9d7']
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),2)
        self.assertTrue(all(e.category=='software_systems' for e in events))

    def test_firmware_build_is_current_not_background_and_teardown_is_distinct(self):
        firmware=['24c98f35de5f2d77e93fb70c','fee1ca0687f8315ad70b9673','1007aaf84b2cee1806cf0e31']
        teardown=['7dcc2ae55143c9733909eb36','3408c9c79a9b1fac73f5402b','07bd3acdc093190776738e38','c46dd6b3067dc1adb5f0c900']
        self.joined(firmware,'software_systems')
        self.joined(teardown,'hardware_products')
        events,_=self.cluster_sources(*firmware,*teardown)
        self.assertEqual(len(events),2)
        for aid in firmware:
            p=self.m.article_reconciliation_profile(self.source_articles(aid)[0])
            keys=' '.join(p.event_keys)
            self.assertIn('9b5042a',keys)
            self.assertNotIn('9a348',keys)
            self.assertNotIn('9a350',keys)

    def test_software_fix_and_satellite_service_do_not_inherit_device_category(self):
        for aid in ['71fb82da7e65d785506a892d','361b4cd70ae5f3095c061a83']:
            with self.subTest(aid=aid):
                events,_=self.cluster_sources(aid)
                self.assertEqual([(e.category,e.relevance_tier) for e in events],[('software_systems','strong')])
        p=self.m.article_reconciliation_profile(self.source_articles('71fb82da7e65d785506a892d')[0])
        self.assertTrue(any('software-issue-report' in key for key in p.event_keys))
        self.assertFalse(any('public-fix-release' in key for key in p.event_keys))
        for verb in ['releases','has released','reportedly releases','officially releases']:
            a=article_for(self.m,f'Apple {verb} iOS 27.0.1 to fix Face ID failure',
                'Apple released iOS 27.0.1 today to fix a Face ID failure reported by users.',source='MacRumors')
            keys=self.m.article_reconciliation_profile(a).event_keys
            self.assertTrue(any('public-fix-release' in key and 'ios-27.0.1' in key for key in keys))

    def test_creative_suite_and_camera_update_have_distinct_owned_projections(self):
        camera=['710953a29330c1ffec51b85f','c38b91586cb43521761a621d','1823da8cc212f6439eb4110b','c1f913eb59ba84ef397cf94e']
        mixed=['d2afa377686f5e977e85ad89','25bb585340f807ae19f935c5','e04bdeb4e2c8c2d87ca0acc8','61d791fd97df270d15214539','523aa37175f66b4f22d4a41b']
        events,_=self.cluster_sources(*camera,*mixed)
        self.assertEqual(len(events),2,[e.title for e in events])
        cam=next(e for e in events if set(camera)<=self.source_ids(e))
        self.assertTrue(all(e.category=='software_systems' and e.relevance_tier=='strong' for e in events))
        other=next(e for e in events if e is not cam)
        self.assertFalse(self.source_ids(other)&set(camera))
        self.assertTrue(all(a.projected_fact_spans or a.bound_claim for a in self.source_articles(mixed[0])))

    def test_company_report_projects_functional_units_and_preserves_plan_status(self):
        ids=['ecdcbefe003ac4b42817ba8d','03b7baa5fd5e140d0a28ceac','07bf91fe42fc559f10da6939']
        events,_=self.cluster_sources(*ids)
        hardware=[e for e in events if e.category=='hardware_products']
        software=[e for e in events if e.category=='software_systems']
        self.assertTrue(hardware)
        self.assertTrue(software)
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))
        self.assertTrue(any('engineering program managers' in ' '.join(a.key_facts) for e in hardware for a in e.articles))
        self.assertFalse(any('HomePod Mini' in e.title for e in events))
        for e in events:
            self.assertTrue(all(a.bound_claim or a.projected_fact_spans for a in e.articles))

    def test_companywide_reorganization_uses_company_category_without_moving_service_teams(self):
        events,_=self.cluster_sources('ecdcbefe003ac4b42817ba8d','03b7baa5fd5e140d0a28ceac','07bf91fe42fc559f10da6939')
        organization=[e for e in events if any(a.bound_claim and a.bound_claim.subject=='apple:organization' for a in e.articles)]
        services=[e for e in events if any(a.bound_claim and a.bound_claim.subject in {'apple:services-business','apple:applecare','apple:software-service-teams'} for a in e.articles)]
        self.assertTrue(organization)
        self.assertTrue(services)
        self.assertTrue(all(e.category=='hardware_products' for e in organization))
        self.assertTrue(all(e.category=='software_systems' for e in services))

    def test_management_reductions_keep_their_own_workforce_stage(self):
        from apple_news_core.event_identity import organization_action_frame
        for text,action in [
            ('Apple plans to eliminate middle-management positions next year.', 'workforce-plan'),
            ('Apple has eliminated middle-management positions this week.', 'workforce-reduction'),
            ('Apple has not eliminated middle-management positions.', 'workforce-reduction-denied'),
        ]:
            frame=organization_action_frame(text)
            self.assertIsNotNone(frame)
            self.assertEqual((frame.subject,frame.action,frame.category),
                             ('apple:management',action,'hardware_products'))

    def test_referred_management_proposals_do_not_become_completed_layoffs(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        proposal='ecdcbefe003ac4b42817ba8d'
        actual='304f16540d383e5f5024ec51'
        for aid,expected in [(proposal,{'workforce-plan'}),(actual,{'workforce-reduction'})]:
            articles=[a for a in self.source_articles(aid) if a.bound_claim and a.bound_claim.subject=='apple:management']
            self.assertTrue(articles)
            self.assertEqual({a.bound_claim.action for a in articles},expected)
        events,_=self.cluster_sources(proposal,actual)
        management=[e for e in events if any(a.bound_claim and a.bound_claim.subject=='apple:management' for a in e.articles)]
        self.assertEqual(len(management),2)
        planned=next(e for e in management if e.articles[0].bound_claim.action=='workforce-plan')
        done=next(e for e in management if e is not planned)
        self.assertEqual(self.source_ids(planned),{proposal})
        self.assertEqual(self.source_ids(done),{actual})
        engineering=[a for a in self.source_articles(proposal) if a.bound_claim and a.bound_claim.subject=='apple:hardware-engineering']
        self.assertTrue(any('half a dozen directors' in ' '.join(a.key_facts) for a in engineering))
        lead='Apple plans to restructure product development across the company.'
        completed='This includes six directors who have already been dismissed this week.'
        evidence=ArticleEvidence('management-test','MacRumors','https://example.com/management',lead,lead,'news',
                                 (EvidenceUnit('plan','p',lead,'body',0),EvidenceUnit('done','p',completed,'body',1)))
        projections,_,_=self.m.project_article_evidence(evidence)
        self.assertEqual({p.claim.action for p in projections if p.claim.subject=='apple:management'}, {'workforce-reduction'})

    def test_team_reorganization_binds_the_object_before_companywide_default(self):
        from apple_news_core.event_identity import organization_action_frame
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        for text,subject,category in [
            ('Apple plans to restructure its Siri software team.', 'apple:software-service-teams','software_systems'),
            ('Apple plans to restructure its AppleCare support organization.', 'apple:applecare','software_systems'),
            ('Apple plans to restructure its Vision Pro development team.', 'apple:vision-team','hardware_products'),
            ('Apple plans to restructure product development across the company while its Siri software team remains unchanged.', 'apple:organization','hardware_products'),
        ]:
            frame=organization_action_frame(text)
            self.assertIsNotNone(frame)
            self.assertEqual((frame.subject,frame.category),(subject,category))
            evidence=ArticleEvidence('reorg-test','MacRumors','https://example.com/reorg',text,text,'news',
                                     (EvidenceUnit('reorg-unit','p',text,'body',0),))
            projections,_,_=self.m.project_article_evidence(evidence)
            self.assertEqual({(p.claim.subject,p.claim.category) for p in projections}, {(subject,category)})
        self.assertIsNone(organization_action_frame('Apple plans to restructure its Siri software and Vision Pro teams.'))

    def test_workforce_references_parse_their_own_predicate_and_stage(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        company='Apple plans to restructure product development across the company.'
        team='Apple plans to cut hardware engineering program managers next year.'
        rows=[
            (company,'This includes eliminating middle-management positions that have overlapping responsibilities.','apple:management','workforce-plan'),
            (team,'These roles have now been eliminated.','apple:hardware-engineering','workforce-reduction'),
            (team,'These roles have not been eliminated.','apple:hardware-engineering','workforce-reduction-denied'),
            (team,'These roles will be eliminated next year.','apple:hardware-engineering','workforce-plan'),
            (team,'These roles have overlapping responsibilities.','apple:hardware-engineering','workforce-plan'),
            (company,'This includes eliminating middle-management positions after Apple has already eliminated other engineering jobs.','apple:management','workforce-plan'),
        ]
        for lead,reference,subject,action in rows:
            with self.subTest(reference=reference):
                evidence=ArticleEvidence('reference-test','MacRumors','https://example.com/reference',lead,lead,'news',
                                         (EvidenceUnit('lead','p',lead,'body',0),EvidenceUnit('reference','p',reference,'body',1)))
                projections,_,_=self.m.project_article_evidence(evidence)
                own_assertion=reference.split(' after Apple ')[0].rstrip('.')
                relevant=[p for p in projections if own_assertion in ' '.join(p.key_facts)]
                self.assertTrue(relevant)
                self.assertEqual({(p.claim.subject,p.claim.action) for p in relevant},{(subject,action)})
                if ' after Apple ' in reference:
                    self.assertFalse(any('other engineering jobs' in ' '.join(p.key_facts) for p in relevant))

    def test_applecare_hold_and_unconfirmed_cut_plan_are_separate_service_actions(self):
        held=['304f16540d383e5f5024ec51','75fd00e6183fbc9f1080578e']
        events,_=self.cluster_sources(*held,'b930f8030507bc198f973e15')
        care=[e for e in events if any(a.bound_claim and a.bound_claim.subject=='apple:applecare' for a in e.articles)]
        self.assertEqual(len(care),2)
        held_event=next(e for e in care if set(held)<=self.source_ids(e))
        self.assertNotIn('b930f8030507bc198f973e15',self.source_ids(held_event))
        self.assertTrue(all(e.category=='software_systems' for e in care))
        other=[e for e in events if e not in care]
        self.assertTrue(all(e.category==('hardware_products' if any(a.bound_claim and a.bound_claim.subject in {'apple:organization','apple:management'} for a in e.articles) else 'software_systems') for e in other))

    def test_reported_workforce_desires_and_referred_holds_keep_local_stage(self):
        from apple_news_core.event_identity import organization_action_frame
        for text in ['同时，他还希望削减部分中层管理职位，打破工程师与公司高层之间的间隔。',
                     'Apple hopes to eliminate middle-management positions.',
                     'Apple wants to cut engineering program manager roles.']:
            self.assertEqual(organization_action_frame(text,apple_owned=True).action,'workforce-plan')
        self.assertEqual(organization_action_frame('Apple has cut engineering program manager roles and wants to release more products.').action,'workforce-reduction')
        management=[a for a in self.source_articles('ad210030ef7f347e1347d356') if a.bound_claim and a.bound_claim.subject=='apple:management']
        care=[a for a in self.source_articles('5de2326b51095d9c77691af7') if a.bound_claim and a.bound_claim.subject=='apple:applecare']
        self.assertTrue(management)
        self.assertEqual({a.bound_claim.action for a in management},{'workforce-plan'})
        self.assertTrue(care)
        self.assertEqual({a.bound_claim.action for a in care},{'workforce-plan-held'})
        self.assertTrue(any('5000' in ' '.join(a.key_facts) and '居家办公' in ' '.join(a.key_facts) for a in care))

    def test_workforce_plan_references_resolve_stage_after_supporting_description(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        lead='Apple plans to cut AppleCare support employees.'
        explanation='These plans assume AI agents can perform some tasks.'
        for reference,action in [
            ('Apple has put those plans on hold indefinitely.','workforce-plan-held'),
            ('Apple denies putting those plans on hold.','workforce-plan-hold-denied'),
            ('Orion has put those plans on hold indefinitely.','workforce-plan'),
            ('Those plans remain under consideration while Orion has put its own plan on hold.','workforce-plan'),
            ('Those plans remain under consideration and Orion has put its own plan on hold.','workforce-plan'),
        ]:
            with self.subTest(reference=reference):
                evidence=ArticleEvidence('plan-reference','MacRumors','https://example.com/plan',lead,lead,'news',
                    tuple(EvidenceUnit(str(i),'p',t,'body',i) for i,t in enumerate([lead,explanation,reference])))
                projections,_,_=self.m.project_article_evidence(evidence)
                care=[p for p in projections if p.claim.subject=='apple:applecare']
                self.assertEqual({p.claim.action for p in care},{action})
                self.assertFalse(any('Orion' in ' '.join(p.key_facts) for p in care))
                if action=='workforce-plan-held':
                    self.assertTrue(all(t.rstrip('.') in ' '.join(care[0].key_facts) for t in [lead,explanation,reference]))

    def test_third_party_launch_customization_and_analyst_prediction_stay_weak(self):
        for aid in ['b0b1b8a4e2203999e3284575','d44a34e2e4762eb499da72a8','ea5347b79110b9471fc68349']:
            with self.subTest(aid=aid):
                events,_=self.cluster_sources(aid)
                self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_device_purchase_fraud_is_not_an_apple_transaction(self):
        for title,lead in [
            ('Police investigate credit card fraud involving iPhone purchases',
             'Police canceled suspicious purchases of iPhones at an independent retailer.'),
            ('警方调查购买iPhone的信用卡诈骗',
             '警方取消了第三方零售商的可疑购机交易，没有涉及苹果运营的交易流程。'),
        ]:
            a=article_for(self.m,title,lead,source='MacRumors')
            p=self.m.article_reconciliation_profile(a)
            self.assertEqual(p.relevance_tier,'weak')

    def test_named_apple_store_verification_abuse_is_a_direct_service_incident(self):
        ids=['6e3dc157837f0290b68ab5b7','e9ef319bcfd2fe18b52c75e9']
        self.joined(ids,'software_systems')
        for aid in ids:
            p=self.m.article_reconciliation_profile(self.source_articles(aid)[0])
            self.assertTrue(any('online-store' in k and 'verification' in k for k in p.event_keys))

    def test_store_security_does_not_borrow_unrelated_historical_or_denied_mechanisms(self):
        for body in [
            "Police found fake cards at an independent retailer. Apple's online store security and verification remained active.",
            "Police said Apple's online store verification remained active and a third-party retailer's security was bypassed.",
            "Police said Apple's online store was unaffected, and a third-party retailer's verification was bypassed.",
            "Police said Apple's online store verification was reviewed, and a third-party retailer's verification was bypassed.",
            "警方表示苹果网店未受影响，而另一商户的身份验证被绕过。",
            "Last year Apple's online store identity verification was bypassed. This week police found stolen iPhones at an unrelated retailer.",
            "Police denied that Apple's online store identity verification was bypassed. The suspicious orders were at a third-party retailer.",
        ]:
            a=article_for(self.m,'Police investigate iPhone purchase fraud',body,source='MacRumors')
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'weak')

    def test_spotlight_component_survives_chinese_word_adjacency(self):
        events,_=self.cluster_sources('db338f249d40c8f1f0196e1a')
        self.assertEqual([(e.category,e.relevance_tier) for e in events],[('software_systems','strong')])
        for title in ['苹果解释Spotlight在建索引','Spotlight indexing support report','聚焦索引支持说明']:
            a=article_for(self.m,title,'Apple explains Spotlight indexing in a support document.',source='MacRumors')
            self.assertIn('spotlight-index-preparation',self.m.article_reconciliation_profile(a).identity.components)
        for title in ['MySpotlight indexing app','Spotlighter indexing tool']:
            a=article_for(self.m,title,'A developer releases a third-party app.',source='MacRumors')
            self.assertNotIn('spotlight-index-preparation',self.m.article_reconciliation_profile(a).identity.title_components)

    def test_vehicle_update_owns_connection_changes_and_new_hardware_compatibility(self):
        events,_=self.cluster_sources('9f4d6da4cd94db681d6ba87d')
        self.assertEqual([(e.category,e.relevance_tier) for e in events],
                         [('hardware_products','weak')])
        for title,lead in [
            ('Orion retrofits older vehicles with wireless CarPlay',
             'Orion releases a firmware update for its older vehicles, adding wireless CarPlay connectivity in place of wired connections.'),
            ('星河汽车为旧车型新增无线CarPlay互通',
             '星河汽车发布旧车型固件更新，新增无线CarPlay连接，手机通过蓝牙和Wi-Fi连接。'),
        ]:
            with self.subTest(title=title):
                p=self.m.article_reconciliation_profile(article_for(self.m,title,lead,source='MacRumors'))
                self.assertEqual((p.category_hint,p.relevance_tier),('software_systems','ecosystem'))
        for title,lead,tier in [
            ('Orion releases a new head unit with CarPlay support',
             'Orion releases a new head unit compatible with existing CarPlay.', 'weak'),
            ('星河汽车发布兼容CarPlay的新车机',
             '星河汽车正式发布新款车机，兼容现有CarPlay。', 'weak'),
            ('Orion launches a stereo compatible with CarPlay',
             'Orion launches a third-party stereo. It supports existing CarPlay connections.', 'weak'),
            ('Orion vehicle OTA lists CarPlay among existing features',
             'Orion releases a vehicle OTA that retains existing CarPlay compatibility.', 'weak'),
            ('Orion denies adding wireless CarPlay to older vehicles',
             'Orion denies releasing firmware that adds wireless CarPlay to older vehicles.', 'weak'),
            ('Apple adds wireless CarPlay connectivity in a platform update',
             'Apple updates CarPlay to add a new wireless connection behavior.', 'strong'),
            ('Apple adds wireless CarPlay connectivity in a platform update',
             'The company releases a firmware update adding wireless CarPlay connectivity.', 'strong'),
        ]:
            with self.subTest(title=title):
                p=self.m.article_reconciliation_profile(article_for(self.m,title,lead,source='MacRumors'))
                self.assertEqual(p.relevance_tier,tier)

    def test_vehicle_firmware_binds_changed_connection_instead_of_background(self):
        for title,lead,tier in [
            ('Orion releases firmware for vehicles with wireless CarPlay',
             'Orion releases firmware for vehicles with wireless CarPlay, adding new radio presets while existing phone connections remain unchanged.', 'weak'),
            ('Orion adds wireless CarPlay to older vehicles',
             'Orion releases a firmware update adding wireless CarPlay to older vehicles, unlike its new head unit.', 'ecosystem'),
        ]:
            with self.subTest(title=title):
                p=self.m.article_reconciliation_profile(article_for(self.m,title,lead,source='MacRumors'))
                self.assertEqual((p.category_hint,p.relevance_tier),('software_systems',tier))

    def test_vehicle_support_facts_cannot_replace_explicit_apple_update(self):
        a=article_for(self.m,'Apple improves wireless CarPlay connectivity',
            'Apple releases a CarPlay update that improves wireless connectivity.',source='MacRumors',
            facts=['Orion releases a new head unit compatible with existing CarPlay.'])
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')

    def test_vehicle_firmware_publisher_is_independent_of_release_wording(self):
        articles=[article_for(self.m,f'Orion {verb} firmware enabling wireless CarPlay',
            f'Orion {verb} a firmware update adding wireless CarPlay to older vehicles.',source='MacRumors')
            for verb in ['releases','rolls out']]
        self.assertEqual(len(self.m.cluster_articles(articles)),1)

    def test_platform_incident_and_unpermitted_first_party_data_access_are_ecosystem(self):
        self.joined(['bb47f201ed4426aa4b02a46c','a3325fa30a732fe979e2c71e'],'software_systems','ecosystem')
        events,_=self.cluster_sources('b2d452426d2516391f0971b3')
        self.assertEqual([(e.category,e.relevance_tier) for e in events],[('software_systems','ecosystem')])

    def test_first_party_guide_publication_reconciles_without_tutorial_downgrade(self):
        self.joined(['51fbb0d017607b41b4dd74e4','18c1852430488a2b7bcf0774','9a4f0514d658734d4281574c',
                     '11b1ef69419b8f183f4a4aac','75b21f9fce8225c035e3bcda'],'software_systems')

    def test_production_reports_and_speaker_issue_reconcile_across_languages(self):
        self.joined(['12e89a8d0f5686ae5619d0fa','75062917e6c20333c18e5eb4',
                     'b45b15f2b489deb4e601a67b','b982559edc5934a64c28bc78'],'hardware_products')
        self.joined(['66916fbc4257b8e75681d1d3','98b976a4aa920cd4d19288b8',
                     'c938b1d15e775bdc5c2a5794','ca1b7f4e5aeceb3c4edf5fbf'],'hardware_products')

    def test_get_ready_is_not_actual_preorder_opening(self):
        ids=['904a623878aabb1adec59e53','964a3b3f3a7cb6ced83c42a9','36dd9df62b98b34931673eb1','98ba9efa97ddfa7bafe13e63']
        self.joined(ids,'hardware_products')
        prepared=self.source_articles(ids[0])[0]
        open_order=article_for(self.m,'Apple opens iPhone Duo pre-orders',
            'Apple opened iPhone Duo pre-orders today. Orders can now be submitted.',source='MacRumors')
        self.assertEqual(len(self.m.cluster_articles([prepared,open_order])),2)

    def test_current_public_api_description_is_software_but_old_interview_stays_weak(self):
        events,_=self.cluster_sources('ff0b1e7648fc45c7d8487905')
        self.assertEqual([(e.category,e.relevance_tier) for e in events],[('software_systems','strong')])
        a=article_for(self.m,'Federighi recalls the iPhone API from last year',
            'In a retrospective interview Federighi recalled last year\'s APIs without a new capability or disclosure.',source='9to5Mac')
        self.assertEqual(self.m.cluster_articles([a])[0].relevance_tier,'weak')

    def test_current_apple_pay_rollout_reconciles_but_preserves_planned_stage(self):
        actual=['eceb2e561c9d68272dfb68ef','a44f66125616368283729f1f']
        self.joined(actual,'software_systems')
        events,_=self.cluster_sources(*actual,'9f3db107c4642a89ca2cd1f4')
        self.assertEqual(len(events),2)
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def evidence_projections(self, title, paragraphs):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        e=ArticleEvidence('synthetic-action','9to5Mac','https://example.com/action',
            title,paragraphs[0],'news',tuple(EvidenceUnit(str(i),'p',text,'body',i)
                for i,text in enumerate(paragraphs)))
        projections,remaining,excluded=self.m.project_article_evidence(e)
        self.m.validate_evidence_dispositions(e,projections,remaining,excluded)
        return projections,remaining

    def test_body_projection_respects_explicit_non_apple_owner(self):
        for quote in ["'",'’']:
            with self.subTest(quote=quote):
                projections,_=self.evidence_projections('Acme CEO restructures support team after Apple contract',
                    [f"Acme{quote}s CEO plans to cut its support employees. Apple is only a customer of Acme."])
                self.assertFalse(projections)
                projections,_=self.evidence_projections('Apple restructures its support organization',
                    [f'Apple plans to cut support employees. Acme{quote}s CEO plans to cut its support employees too.'])
                self.assertTrue(projections)
                self.assertFalse(any('Acme' in f for p in projections for f in p.key_facts))

    def test_team_plans_and_denials_do_not_become_completed_reductions(self):
        for team in ['hardware engineering program managers','Vision Pro team','Siri software team']:
            for verb,action in [('plans to cut','workforce-plan'),('has not cut','workforce-reduction-denied'),('denies cutting','workforce-reduction-denied')]:
                with self.subTest(team=team,verb=verb):
                    ps,_=self.evidence_projections('Apple announces its organization changes',
                        [f'Apple {verb} its {team}.'])
                    self.assertTrue(ps)
                    self.assertEqual({p.action for p in ps},{action})

    def test_negated_app_update_cannot_reenter_through_supporting_text(self):
        for denial in ['Final Cut Camera was not updated and has no new features.',
                       'Apple did not update Final Cut Camera.']:
            ps,remaining=self.evidence_projections('Apple updates Creator Studio',
                ['Apple updated Creator Studio today.',denial])
            self.assertEqual({p.subject for p in ps},{'apple:creator-studio'})
            self.assertTrue(remaining)

    def test_local_transfer_condition_stays_with_hardware_team(self):
        articles=self.source_articles('03b7baa5fd5e140d0a28ceac')
        hw=next(a for a in articles if a.bound_claim.subject=='apple:hardware-engineering')
        self.assertTrue(any('weeks to find other positions' in f for f in hw.key_facts))
        self.assertFalse(any('Siri, Vision Pro' in f for a in articles for f in a.key_facts))
        self.assertFalse(any('Gurman cautioned' in f for f in hw.key_facts))
        suite=next(a for a in self.source_articles('25bb585340f807ae19f935c5')
            if a.bound_claim.subject=='apple:creator-studio')
        self.assertFalse(any('Final Cut Camera' in f for f in suite.key_facts))

    def test_unknown_firmware_build_does_not_borrow_an_old_identifier(self):
        for background in ['The old firmware build number was 9A350.',
                           'Apple released firmware 9A350 last year.']:
            a=article_for(self.m,'Apple releases AirPods beta firmware',
                'Apple released new AirPods beta firmware today.',facts=[background],source='MacRumors')
            self.assertFalse(any('9a350' in key for key in self.m.article_reconciliation_profile(a).event_keys))

    def test_company_target_and_ceo_headlines_keep_owned_team_projections(self):
        for aid in ['527b1978a7aab56a5f9d96df','88ff09fcda78264f343241a4']:
            arts=self.source_articles(aid)
            self.assertTrue(all(a.bound_claim for a in arts))
            self.assertTrue(any(a.bound_claim.subject=='apple:organization' for a in arts))

    def test_recalled_plan_follows_its_local_disposition(self):
        for text in ['Apple considered a plan to cut AppleCare employees. However, Apple put this plan on hold.',
                     '苹果今年夏季曾计划裁减 AppleCare 客服人员。不过，苹果最终暂缓了这一计划，目前并未推进该批裁员。']:
            ps,_=self.evidence_projections('Apple announces AppleCare organization changes',[text])
            self.assertEqual({p.action for p in ps},{'workforce-plan-held'})
        for aid in ['ad210030ef7f347e1347d356','62a88d943e4678f3e2ec7f40']:
            care=[a for a in self.source_articles(aid) if a.bound_claim and a.bound_claim.subject=='apple:applecare']
            self.assertTrue(care)
            self.assertEqual({a.bound_claim.action for a in care},{'workforce-plan-held'})

    def test_full_model_and_production_direction_remain_part_of_action(self):
        for cases in [[
            ('iPhone 19 Pro owners report speaker crackling','iPhone 19 Pro users report speaker crackling.'),
            ('iPhone 19 Pro Max owners report speaker crackling','iPhone 19 Pro Max users report speaker crackling.')], [
            ('Report: Apple increases iPhone 19 production','Apple is raising iPhone 19 production to meet demand.'),
            ('Report: Apple cuts iPhone 19 production','Apple is cutting iPhone 19 production because demand is weak.')]]:
            with self.subTest(cases=cases):
                arts=[article_for(self.m,h,lead,source='MacRumors') for h,lead in cases]
                self.assertEqual(len(self.m.cluster_articles(arts)),2)

    def test_apple_publisher_is_not_a_product_name_plus_adverb(self):
        for adverb in ['officially','reportedly','today']:
            a=article_for(self.m,f'Apple {adverb} launches iPhone 19',
                'Apple launches iPhone 19 today.',source='MacRumors')
            self.assertEqual(self.m.cluster_articles([a])[0].relevance_tier,'strong')

    def test_same_bound_claim_does_not_keep_generic_topic_warning(self):
        events,_=self.cluster_sources('ecdcbefe003ac4b42817ba8d','03b7baa5fd5e140d0a28ceac')
        for event in events:
            if len(event.articles)>1 and all(a.bound_claim for a in event.articles):
                self.assertNotIn('mixed primary topic facets',event.merge_warnings)

    def test_report_projection_cannot_borrow_apple_from_third_party_background(self):
        a=article_for(self.m,"Acme CEO restructures support team after Apple contract",
            "Acme's CEO plans to cut its support employees. Apple is only a customer of Acme.",source='9to5Mac')
        self.assertTrue(all(e.relevance_tier=='weak' for e in self.m.cluster_articles([a])))

    def test_negated_plan_disposition_cannot_become_an_affirmative_hold(self):
        from apple_news_core.event_identity import organization_action_frame
        for text in ['Apple has not put the AppleCare layoffs plan on hold.',
                     '苹果否认已经搁置 AppleCare 裁员计划。']:
            with self.subTest(text=text):
                f=organization_action_frame(text)
                self.assertTrue(f is None or f.action!='workforce-plan-held')

    def test_firmware_stage_and_model_issue_boundaries_remain_distinct(self):
        articles=[article_for(self.m,title,lead,source='MacRumors') for title,lead in [
            ('Apple releases AirPods beta firmware 10C123b','Apple released beta firmware with build number 10C123b for AirPods today.'),
            ('Apple releases AirPods final firmware 10C123b','Apple released final firmware with build number 10C123b for AirPods today.'),
            ('iPhone 19 Pro owners report speaker crackling','iPhone 19 Pro users report speaker crackling.'),
            ('iPhone 20 Pro owners report speaker crackling','iPhone 20 Pro users report speaker crackling.'),
        ]]
        self.assertEqual(len(self.m.cluster_articles(articles)),4)

    def test_viewership_reports_with_different_weeks_do_not_merge(self):
        articles=[article_for(self.m,'Apple TV reports record weekly viewership',
            f'Apple TV reports its highest weekly viewership for the week of September {day}, up 50%.',source='9to5Mac') for day in [7,14]]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_unofficial_guide_and_authorized_app_access_remain_weak(self):
        cases=[('Developer releases unofficial Apple parental guide',
                'A developer released an unofficial digital habits guide for iPhone parents.'),
               ('Zen app reads Messages export on iPhone',
                'Zen reads user-exported Messages data with explicit permission. This is an ordinary app feature.')]
        for title,lead in cases:
            with self.subTest(title=title):
                events=self.m.cluster_articles([article_for(self.m,title,lead,source='9to5Mac')])
                self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_speaker_fix_commitment_is_not_the_user_fault_report(self):
        fault=article_for(self.m,'iPhone 19 Pro owners report speaker crackling',
            'iPhone 19 Pro users report speaker crackling. Its cause is unknown.',source='MacRumors')
        reply=article_for(self.m,'Apple promises iPhone 19 Pro speaker software fix',
            'Apple confirmed the speaker issue is a software bug and will release an update.',source='9to5Mac')
        events=self.m.cluster_articles([fault,reply])
        self.assertEqual(len(events),2)
        self.assertEqual({e.category for e in events},{'hardware_products','software_systems'})


    def test_current_trailer_does_not_inherit_a_historical_or_secondary_publication(self):
        for lead in [
            'Apple TV previously unveiled the trailer for Nocturne last month.',
            'Nocturne will premiere on November 6. Apple TV unveiled the trailer for Nocturne last month.',
        ]:
            a=article_for(self.m,'Apple TV unveils a thriller based on a novel',lead,source='9to5Mac')
            self.assertFalse(any(key.endswith(':trailer') for key in self.m.article_reconciliation_profile(a).event_keys))

    def test_firmware_denial_and_historical_release_do_not_become_current_updates(self):
        for title,lead in [
            ('Apple did not release new AirPods firmware','Apple did not release new AirPods firmware today.'),
            ('Apple released AirPods firmware last year','Apple released AirPods firmware 11D456 last year.'),
        ]:
            a=article_for(self.m,title,lead,source='MacRumors')
            self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'weak')

    def test_named_third_party_app_cannot_inherit_hardware_or_music_service_action(self):
        events,_=self.cluster_sources('ce3dc2b415895c1246ec6125')
        self.assertEqual([(e.relevance_tier,e.category) for e in events],[('weak','software_systems')])

    def test_all_trailer_constructions_reject_historical_publication(self):
        for lead in [
            'Apple TV previously released Nocturne season 2 trailer last month.',
            'Apple TV previously released the trailer for "Nocturne" last month.',
            'Apple TV did not release the trailer for Nocturne today.',
        ]:
            a=article_for(self.m,'Apple TV unveils a thriller based on a novel',lead,source='9to5Mac')
            self.assertFalse(any(key.endswith(':trailer') for key in self.m.article_reconciliation_profile(a).event_keys))

    def test_named_app_headline_preserves_explicit_apple_update_ownership(self):
        for app in ['GarageBand','Freeform']:
            a=article_for(self.m,f'{app} turns your iPhone into a studio',
                f'Apple updated its {app} app today with new recording features.',source='MacRumors')
            p=self.m.article_reconciliation_profile(a)
            self.assertEqual((p.relevance_tier,p.category_hint),('strong','software_systems'))
            self.assertFalse(any('third-party-software' in key for key in p.event_keys))

    def test_publisher_apple_is_not_the_name_of_an_updated_application(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        for title,lead in [
            ('苹果今日发布 Apple Watch Series 16：新传感器',
             '苹果今日发布 Apple Watch Series 16 智能手表，配备新健康传感器，今日接受订购。'),
            ('Apple releases Apple Watch Series 16: updated sensors',
             'Apple today released Apple Watch Series 16 with updated sensors and opened orders.'),
        ]:
            a=article_for(self.m,title,lead,source='IT之家')
            a.evidence=ArticleEvidence('publisher-test','IT之家',a.url,title,lead,'news',
                                      (EvidenceUnit('lead','p',lead,'body',0),))
            p=self.m.article_reconciliation_profile(a)
            self.assertEqual((p.relevance_tier,p.category_hint),('strong','hardware_products'))
            self.assertNotIn('primary-claim:apple-app:apple:software-update',p.event_keys)

    def test_annual_sales_forecast_joins_without_borrowing_background_percentages(self):
        forecast=['c60499ea5410d1f1f2b8620d','099d37010ddfa5a85f94b1cb']
        china='d8a63017100cbf8e0f6ae346'
        self.joined(forecast,'hardware_products')
        for order in [forecast+[china],[china]+forecast[::-1]]:
            events,_=self.cluster_sources(*order)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                             {frozenset(forecast),frozenset([china])})
        for aid in forecast:
            p=self.m.article_reconciliation_profile(self.source_articles(aid)[0])
            self.assertTrue(any('sales' in k and '6000000' in k for k in p.event_keys))

    def test_sales_forecast_keeps_local_institution_model_period_and_current_assertion(self):
        def forecast(title,lead):
            a=article_for(self.m,title,lead,source='MacRumors')
            return a,self.m.article_reconciliation_profile(a)
        a,p=forecast('Counterpoint forecasts iPhone Duo annual sales',
            'Counterpoint expects Apple to sell 6 million iPhone Duo units in 2026. '
            'IDC expects total foldable shipments to reach 23 million units.')
        b,q=forecast('Counterpoint：预计 iPhone Duo 2026 年销量',
            'Counterpoint Research 预计，苹果2026年可售出约600万部iPhone Duo。'
            '去年全球市场份额为12%。')
        self.assertEqual(len(self.m.cluster_articles([a,b])),1)
        self.assertTrue(any('sales' in k and '2026' in k and '6000000' in k for k in p.event_keys))
        variants=[
            ('IDC forecasts iPhone Duo annual sales','IDC expects Apple to sell 6 million iPhone Duo units in 2026.'),
            ('Counterpoint forecasts iPhone Air annual sales','Counterpoint expects Apple to sell 6 million iPhone Air units in 2026.'),
            ('Counterpoint forecasts iPhone Duo annual sales','Counterpoint expects Apple to sell 6 million iPhone Duo units in 2027.'),
            ('Counterpoint forecasts iPhone Duo annual sales','Counterpoint expects Apple to sell 8 million iPhone Duo units in 2026.'),
            ('Counterpoint revisits iPhone Duo annual sales','Counterpoint previously expected Apple to sell 6 million iPhone Duo units in 2026.'),
            ('Counterpoint denies iPhone Duo sales forecast','Counterpoint does not expect Apple to sell 6 million iPhone Duo units in 2026.'),
            ('Counterpoint forecasts iPhone Duo annual sales','Counterpoint expects Apple to sell more iPhone Duo units in 2026. IDC expects Samsung to sell 6 million foldables in 2026.'),
        ]
        for title,lead in variants:
            with self.subTest(title=title,lead=lead):
                other,r=forecast(title,lead)
                self.assertFalse(p.event_keys&r.event_keys)
                self.assertEqual(len(self.m.cluster_articles([a,other])),2)

    def test_captured_personal_camera_trial_is_not_a_hardware_specification_report(self):
        articles=self.source_articles('bf214fcc7378a4fc7fcf20ce')
        for article in articles:
            p=self.m.article_reconciliation_profile(article)
            self.assertEqual(p.identity.content_form,'review')
            self.assertEqual(p.relevance_tier,'weak')
        events,_=self.cluster_sources('bf214fcc7378a4fc7fcf20ce')
        self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_personal_purchase_trials_do_not_suppress_reported_product_actions(self):
        for title,lead in [
            ('iPhone 19 Pro cameras are the best yet',
             'I wanted to test its camera before buying my next phone. Here is what I learned.'),
            ('MacBook Pro display is the best I have used',
             'I decided to try its display before upgrading my own laptop.'),
            ('iPhone 19 Pro 相机是我用过最好的',
             '我决定试用这款手机，为自己的升级和购买做准备。'),
            ('iPhone 19 Pro camera upgrade surprised me',
             'I wanted to test its camera before buying my next phone.'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,source='AppleInsider')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual((p.identity.content_form,p.relevance_tier),('review','weak'))
        for title,lead in [
            ('iPhone 19 Pro scores 180 points in DXOMARK camera test',
             'DXOMARK published its measured iPhone 19 Pro camera score of 180 today.'),
            ('Apple releases iPhone 19 Pro camera firmware',
             'Apple released new camera firmware today. I wanted to test it before buying my next phone.'),
            ('iPhone 19 Pro scores 180 points in DXOMARK camera test',
             'DXOMARK published its measured iPhone 19 Pro camera score of 180 today. '
             'A buyer said: "I wanted to test its camera before buying my next phone."'),
            ('iPhone 19 Pro scores 180 points in DXOMARK camera test',
             'DXOMARK 发布了 iPhone 19 Pro 相机的 180 分测试成绩。'
             '购买者表示：“我决定试用，为自己的升级和购买做准备。”'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,source='MacRumors')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual((p.identity.content_form,p.relevance_tier),('news','strong'))

    def test_hardware_design_and_function_comparisons_are_not_action_subjects(self):
        from apple_news_core.event_identity import hardware_action_subjects, owned_multi_product_hardware_subject
        for text in [
            'Apple home hub launching with iMac G4 design',
            'Apple home hub will launch with a design inspired by the iMac G4',
            'Apple home hub will act as a HomePod',
            'Apple home hub looks like an iMac G4 and will launch in October',
            'Apple home hub functions like a HomePod and will launch in October',
            'Apple home hub looks like a bedside clock and will launch in October',
            'Apple home hub to feature iMac G4-style design',
            '苹果家庭中枢将采用 iMac G4 风格设计',
            '苹果家庭中枢功能类似 HomePod',
        ]:
            with self.subTest(text=text):
                self.assertEqual(hardware_action_subjects(text), {'apple-home-hub'})
                self.assertEqual(owned_multi_product_hardware_subject(text), 'apple-home-hub')

    def test_hardware_comparison_preserves_separate_coordinated_launch(self):
        from apple_news_core.event_identity import hardware_action_subjects
        title='Apple home hub with iMac G4 design and HomePod mini will launch in October'
        self.assertEqual(hardware_action_subjects(title), {'apple-home-hub','homepod'})
        facts=['Apple home hub will launch in October with iMac G4-style design.',
               'HomePod mini will launch in October with a faster processor.']
        variants=self.m.compound_article_variants(title, ' '.join(facts), facts)
        self.assertEqual(len(variants),2,[v[0] for v in variants])
        self.assertFalse(any('iMac roadmap' in v[0] for v in variants))
        self.assertTrue(any('iMac G4-style' in fact for v in variants for fact in v[2]))
        for comparison in ['looks like an iMac G4','functions like a HomePod',
                           'looks like a bedside clock','with a clock-like design']:
            with self.subTest(comparison=comparison):
                facts=[f'Apple home hub {comparison} and will launch in October.',
                       'Apple TV will launch in October with a faster processor.']
                variants=self.m.compound_article_variants(
                    'Apple home hub and Apple TV will launch in October', ' '.join(facts), facts)
                self.assertEqual(len(variants),2,[v[0] for v in variants])

    def test_captured_home_hub_design_does_not_project_reference_products(self):
        for aid in ['5161f169a7bf58834b32eaec','2b0f7929b5450180cf8f89a7']:
            with self.subTest(aid=aid):
                articles=self.source_articles(aid)
                self.assertEqual(len(articles),1,[a.title for a in articles])
                self.assertNotIn('roadmap update',articles[0].title)
                events,rows=self.cluster_sources(aid)
                self.assertEqual((events[0].relevance_tier,events[0].category),('strong','hardware_products'))
                self.assertTrue(any('iMac G4' in f['text'] for row in rows for f in row['fact_sources']))

    def test_annual_forecast_binds_seller_full_model_and_comparison_period(self):
        def profile(model,lead):
            a=article_for(self.m,f'Counterpoint forecasts iPhone {model} annual sales',lead,source='MacRumors')
            return a,self.m.article_reconciliation_profile(a)
        duo,p=profile('Duo','Counterpoint expects Apple to sell 6 million iPhone Duo units in 2026.')
        foreign,q=profile('Duo','Counterpoint expects Samsung to sell 6 million foldables in 2026, while Apple launches the iPhone Duo.')
        self.assertFalse(p.event_keys&q.event_keys)
        self.assertEqual(len(self.m.cluster_articles([duo,foreign])),2)
        base,p=profile('19','Counterpoint expects Apple to sell 6 million iPhone 19 units in 2026.')
        pro,q=profile('19','Counterpoint expects Apple to sell 6 million iPhone 19 Pro units in 2026.')
        self.assertFalse(p.event_keys&q.event_keys)
        self.assertEqual(len(self.m.cluster_articles([base,pro])),2)
        relative,p=profile('Duo','Counterpoint expects Apple to sell 6 million iPhone Duo units this year.')
        comparison,q=profile('Duo','Counterpoint expects Apple to sell 6 million iPhone Duo units this year, up from 4 million in 2025.')
        self.assertEqual(p.event_keys,q.event_keys)
        self.assertTrue(any('this-year' in k for k in q.event_keys))
        self.assertFalse(any('2025' in k for k in q.event_keys))

    def test_captured_homekit_platform_report_stays_separate_from_device_roadmap(self):
        platform='cdeb73977e360d1e81dd9e11'
        hardware='b7538cc26fb3fd44d29197d1'
        for ids in [[platform,hardware],[hardware,platform]]:
            events,serialized=self.cluster_sources(*ids)
            retained=[e for e in events if platform in self.source_ids(e)]
            self.assertEqual(len(retained),1)
            self.assertEqual(self.source_ids(retained[0]),{platform})
            self.assertEqual((retained[0].category,retained[0].relevance_tier),
                             ('software_systems','strong'))
            item=next(e for e in serialized if any(s['evidence_id']==platform for s in e['sources']))
            facts=' '.join([item['summary'],*item['key_facts'],*item['must_include_facts']])
            self.assertIn('new categories of connected products',facts)
            self.assertIn('third-party manufacturers',facts)

    def test_homekit_platform_action_owns_software_category_despite_device_background(self):
        for title,lead in [
            ('Apple is working to expand HomeKit',
             'Apple is expanding HomeKit support for new connected product categories. A separate report discusses new Apple TV and HomePod hardware.'),
            ('HomeKit adds support for new device categories',
             'Apple is expanding its HomeKit platform. Apple TV and HomePod mini will also receive faster chips.'),
            ('苹果计划扩展 HomeKit 平台',
             '苹果计划扩展 HomeKit 平台，支持更多设备类别。另有报道提及新的 Apple TV 和 HomePod mini 硬件。'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,source='MacRumors')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual((p.category_hint,p.relevance_tier),('software_systems','strong'))
                self.assertEqual(p.identity.title_products,frozenset({'homekit'}))

    def test_homekit_compatibility_does_not_make_an_accessory_a_platform_update(self):
        platform=article_for(self.m,'Apple expands HomeKit platform support',
                            'Apple is expanding HomeKit support for new device categories.',source='MacRumors')
        for title,lead in [
            ('Acme launches new light bulb with HomeKit support',
             'Acme released its new light bulb that works with HomeKit. Apple has not changed its platform.'),
            ('第三方品牌推出支持 HomeKit 的灯泡',
             'Acme 推出支持 HomeKit 的新灯泡。苹果平台没有更新。'),
            ('HomeKit-compatible light bulb expands its color range',
             'Acme expanded its light bulb color range. Apple has not changed HomeKit.'),
            ('HomeKit light switch adds motion detection',
             'Acme added motion detection to its light switch. Apple has not changed HomeKit.'),
            ('Acme expands its HomeKit accessory range',
             'Acme launches additional light bulbs compatible with existing HomeKit.'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,source='MacRumors')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual(p.relevance_tier,'weak')
                self.assertNotEqual(p.category_hint,'software_systems')
                self.assertEqual(len(self.m.cluster_articles([platform,a])),2)

    def test_captured_apple_physical_implementation_is_not_third_party_context(self):
        sid='78e5fdf7a1dbbe2d2fdf0956'
        events,serialized=self.cluster_sources(sid)
        self.assertEqual(len(events),1)
        self.assertEqual((events[0].category,events[0].relevance_tier),('hardware_products','strong'))
        item=serialized[0]
        actual=' '.join([item['summary'],*item['key_facts'],*item['must_include_facts']])
        self.assertIn('Apple confirming',actual)
        self.assertIn('reduced by half',actual)
        self.assertIn('increases the brightness',actual)
        self.assertIn('three live activities',actual)

    def test_physical_implementation_binds_apple_publisher_not_device_compatibility(self):
        titles=[
            ('The clever way Apple embedded Face ID beneath the iPhone 19 screen','strong'),
            ('The way Apple placed a camera beneath the iPad Pro display','strong'),
            ('The way Acme embedded a camera into an iPhone case','weak'),
        ]
        for title,tier in titles:
            with self.subTest(title=title):
                lead='Apple embedded its module beneath the device display.' if tier=='strong' else 'Acme released its camera case for iPhone. Apple did not change the device.'
                a=article_for(self.m,title,lead,source='MacRumors')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual(p.relevance_tier,tier)
                if tier=='strong': self.assertEqual(p.category_hint,'hardware_products')
        from apple_news_core.event_identity import first_party_hardware_implementation
        for title in ['Apple could embed Face ID beneath the iPhone screen',
                      'Apple has not embedded Face ID beneath the iPhone screen',
                      'Acme embedded a camera into an iPhone case']:
            self.assertIsNone(first_party_hardware_implementation(title))

    def test_platform_action_is_not_its_compatible_accessory_object(self):
        for title,lead in [
            ('Siri adds new controls for HomeKit light bulbs',
             'Apple added new Siri controls for existing HomeKit light bulbs.'),
            ('HomeKit adds support for AirPlay speakers',
             'Apple expanded its HomeKit platform to support AirPlay speakers.'),
        ]:
            with self.subTest(title=title):
                a=article_for(self.m,title,lead,source='MacRumors')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual((p.relevance_tier,p.category_hint),('strong','software_systems'))

    def test_physical_implementation_keeps_host_model_and_denial(self):
        from apple_news_core.event_identity import first_party_hardware_implementation
        self.assertIsNone(first_party_hardware_implementation(
            'Report denies Apple embedded Face ID beneath the iPhone screen'))
        articles=[article_for(self.m,f'The way Apple embedded Face ID beneath the iPhone {model} screen',
                             f'Apple embedded its Face ID module beneath the iPhone {model} display.',source='MacRumors')
                  for model in [19,20]]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)
        denied=article_for(self.m,'Report denies Apple embedded Face ID beneath the iPhone 19 screen',
                           'The report denies that Apple embedded Face ID beneath the iPhone 19 display.',source='MacRumors')
        self.assertEqual(len(self.m.cluster_articles([articles[0],denied])),2)

    def test_long_mechanism_keeps_confirmation_without_another_actor(self):
        from copy import deepcopy
        sid='78e5fdf7a1dbbe2d2fdf0956';original=self.rows[sid];row=deepcopy(original)
        outside='Samsung increases the brightness of its own phone display by 90 percent.'
        row['evidence']['units'][5]['text']+=' '+outside
        self.rows[sid]=row
        try:
            _,serialized=self.cluster_sources(sid);item=serialized[0]
            actual=' '.join([item['summary'],*item['key_facts'],*item['must_include_facts']])
            self.assertIn('Apple confirming',actual)
            self.assertIn('reduced by half',actual)
            self.assertIn('increases the brightness',actual)
            self.assertNotIn(outside,actual)
        finally:
            self.rows[sid]=original

    def test_platform_control_accessories_keep_the_third_party_action(self):
        for title in [
            '某智能家居品牌发布接入 HomeKit 的桌面妙控旋钮',
            '第三方品牌推出支持 HomeKit 的家居控制器',
        ]:
            with self.subTest(title=title):
                lead='该品牌推出自有智能家居控制器，并接入 Apple HomeKit 供用户使用。'
                a=article_for(self.m,title,lead,source='IT之家')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual((p.relevance_tier,p.category_hint),('weak','hardware_products'))
                self.assertEqual(self.m.detect_event_kind(title,lead),'third_party_ecosystem')
        title='HomeKit 新增灯泡控制功能'
        lead='苹果扩展 HomeKit 平台，支持更多灯泡控制功能。'
        a=article_for(self.m,title,lead,source='IT之家')
        p=self.m.article_reconciliation_profile(a)
        self.assertEqual((p.relevance_tier,p.category_hint),('strong','software_systems'))

    def test_apple_tv_device_features_do_not_turn_the_device_into_its_service(self):
        for title in [
            'New Apple TV 4K is coming this fall with new Siri features',
            '苹果新款 Apple TV 4K 支持 Siri AI 和 Wi-Fi 7',
        ]:
            with self.subTest(title=title):
                lead='Apple is preparing a new Apple TV 4K set-top box, with Siri AI features, a faster chip and Wi-Fi 7.'
                a=article_for(self.m,title,lead,source='MacRumors')
                p=self.m.article_reconciliation_profile(a)
                self.assertEqual((p.relevance_tier,p.category_hint),('strong','hardware_products'))

if __name__=='__main__':
    unittest.main()
