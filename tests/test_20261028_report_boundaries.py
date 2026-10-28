"""Source-owned release, measurement and capability reports across headline angles."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from test_relevance_rules import article_for, load_module
import test_p4_pure_json_batch as prior


class CurrentReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261028_report_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 28, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    def test_mac_release_sources_share_model_and_actual_introduction(self):
        groups = (
            ('3880ac9ad26534ecb613442f', 'cefffca1cd6ff13606b88e82', 'c652ca916e3fb6bbedfa820d',
             '6a492798f757841bc0c56537', 'fc3a571a13ad43c06725be4e', 'b7af8f7a7197ca34c7f3d3af',
             '4548caff010e226254975b1b', '430a97b11ec4be5a160e6127', '3d116968d06d1d84110fd25c',
             '4b9ecb2ae24947e84703068a', 'd9d4a227ec56dbfb94c047fe'),
            ('95b48b767099f4e5855d1d48', 'b42842ec16715e56e531b071', 'b1896fd2412cbd603f21bb80',
             '0a0a7693a8360df3ae56b511', '0a60f0de34147ef0076af817', '6efaf04b67b725a0fb68c8bb',
             '74b98309911f44c8407e3faf', 'e31d41c2b25ee82ab91d3715', 'e7f5ffaad02f7c0a409ad64e',
             'cd3a967428cfb0859a0fdaca'),
        )
        for ids in groups:
            with self.subTest(ids=ids):
                events, _ = self.cluster_sources(*ids)
                self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
                self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
                self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))

    def test_mac_announcement_does_not_absorb_prediction_or_another_product(self):
        ids = ('3880ac9ad26534ecb613442f', 'b42842ec16715e56e531b071', '51d52e97995255eea77ed11d')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 3)

    def test_launch_measurement_is_one_dataset_across_regional_angles(self):
        ids = ('148bb7d38939a06c37d785c0','2411053fbb6eed53362a69d9',
               '32d1d5f57751382b2fd44e0e','3bc792dada53de86634c17ec')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1, [(e.title,len(e.articles)) for e in events])
        self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))

    def test_builtin_capabilities_keep_software_without_a_new_release(self):
        ids = ('ed8dceaee08ea352e20041d2', '3d5528eb42fed68b26bdae70',
               '236c6a02f6e297d8d8d30c87', '1b8a7549e1154e17cd94e083',
               '3f9d843b3df41c1254781da6')
        for sid in ids:
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','software_systems')])

    def test_first_party_data_and_local_model_connections_are_ecosystem(self):
        for sid in ('c76cc26b635c8f48ef4c16be', '4fc5fbf98c523426dd037f0f', '4722d0d4ebe828663bb6b950', '8661c958fc010034a157db0e'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual([(e.relevance_tier,e.category) for e in events], [('ecosystem','software_systems')])

    def test_ordinary_app_release_cannot_borrow_its_host_platform(self):
        events, _ = self.cluster_sources('f132f7ce27a9d408d2986636')
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('weak','software_systems')])


    def test_mac_model_dimensions_and_sale_stage_are_not_inferred(self):
        from apple_news_core.event_matcher import profile_pair_decision
        def profile(title, body):
            return self.m.article_reconciliation_profile(article_for(self.m, title, body))
        left = profile('Apple unveils 14-inch M6 MacBook Pro',
                       'Apple today introduced the new 14-inch M6 MacBook Pro.')
        for title, body in (
            ('Apple unveils 16-inch M6 MacBook Pro', 'Apple today introduced the new 16-inch M6 MacBook Pro.'),
            ('Apple unveils M6 MacBook Pro', 'Apple today introduced the new M6 MacBook Pro.'),
            ('14-inch M6 MacBook Pro orders open today',
             'The new 14-inch M6 MacBook Pro features a faster processor. Orders opened today after last week’s announcement.'),
            ('14-inch M6 MacBook Pro begins shipping today',
             'The new 14-inch M6 MacBook Pro features a faster processor. It begins shipping today.'),
            ('14-inch M6 MacBook Pro now available in stores',
             'The new 14-inch M6 MacBook Pro features a faster processor. It is now available in stores.'),
        ):
            with self.subTest(title=title):
                self.assertNotEqual(profile_pair_decision(left, profile(title, body)), 'match')
        self.assertEqual(profile_pair_decision(
            profile('Apple unveils 14-inch MacBook Pro', 'Apple today introduced the new 14-inch MacBook Pro.'),
            profile('Apple unveils 16-inch MacBook Pro', 'Apple today introduced the new 16-inch MacBook Pro.')), 'conflict')
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'Apple unveils MacBook Pro'
        lead = 'Apple today introduced the new MacBook Pro.'
        for extra in ('Apple will introduce the new 14-inch M6 MacBook Pro next year.',
                      'Apple introduced the new 14-inch M5 MacBook Pro last year.',
                      'Apple has not introduced the new 14-inch M6 MacBook Pro.'):
            frame = source_device_operation_frame(title, lead, (), source_units=(lead, extra))
            self.assertFalse(frame and frame.model_generation, extra)

    def test_launch_dataset_does_not_borrow_forecasts_or_other_periods(self):
        from apple_news_core.event_identity import source_weekly_device_measurement
        intro = 'Counterpoint report examines iPhone 18 Pro sales. '
        for tail in (
            'iPhone 18 Pro sales were tracked in the first three weeks of availability. '
            'iPhone 18 Pro global sales grew 12% during the fourth quarter.',
            'iPhone 18 Pro global sales will be up 12% in the first three weeks of availability.',
            'iPhone 18 Pro global sales are forecast to be up 12% in the first three weeks of availability.',
            'iPhone 18 Pro sales were tracked in the first three weeks of availability. '
            'An unrelated consumer poll was released. iPhone 18 Pro global sales grew 12% yesterday.',
        ):
            with self.subTest(body=tail):
                self.assertIsNone(source_weekly_device_measurement('iPhone 18 Pro launch sales', intro + tail))

    def test_endpoint_access_belongs_to_client_and_keeps_scope_and_stage(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        from apple_news_core.event_identity import bind_interoperability_report
        def bind(title, body):
            return bind_interoperability_report(capture_article_title_evidence('', '', title, body, ()))
        self.assertIsNone(bind('ChatGPT launches new writing tools',
                               'ChatGPT now offers new writing tools. Apple Mail can access iCloud email.'))
        for body in ('Nimbus plans to access iCloud email.', 'Nimbus can access iCloud email next year.',
                     'Nimbus cannot access iCloud email.'):
            self.assertIsNone(bind('Nimbus iCloud connection', body), body)
        mail = bind('Nimbus iCloud Mail support', 'Nimbus can access iCloud email.')
        calendar = bind('Nimbus iCloud Calendar support', 'Nimbus can access iCloud calendar.')
        preview = bind('Nimbus previews iCloud support', 'Nimbus can access iCloud email in this preview.')
        self.assertEqual(mail.subject, 'nimbus:icloud')
        self.assertNotEqual(mail.object, calendar.object)
        self.assertNotEqual(mail.action, preview.action)
        for body in ('Nimbus can access iCloud email, while RivalApp can access iCloud calendar.',
                     'Nimbus can access iCloud email. RivalApp can access iCloud calendar.',
                     'Nimbus can access iCloud email. Nimbus cannot access iCloud calendar.'):
            self.assertEqual(bind('Nimbus iCloud support', body).object, 'mail', body)
        both = bind('Nimbus iCloud support', 'Nimbus can access iCloud email and calendar.')
        self.assertEqual(both.object, bind('Nimbus iCloud support',
            'Nimbus can access iCloud email. Nimbus can access iCloud calendar.').object)


    def test_current_release_and_permission_report_do_not_become_editorial(self):
        for sid in ('d9933239741ea24fdd1b5484', '42d98dcab7a0954805b56516'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong','software_systems')])
        events, _ = self.cluster_sources('35b725351ede1e9c6be97fd0')
        self.assertEqual([e.relevance_tier for e in events], ['weak'])

    def test_single_trailer_does_not_project_calendar_prose_as_film_names(self):
        articles = self.source_articles('bd87ff55c12282871b30282d')
        self.assertEqual(len(articles), 1, [a.title for a in articles])
        self.assertEqual(articles[0].title, self.rows['bd87ff55c12282871b30282d']['recorded_extraction'][0])


    def test_software_documents_proceedings_and_media_keep_their_operation(self):
        groups = (
            ('62ee86e620b8340038d17b78','0a1302ca3dc16a4eae3fdeb8'),
            ('d5d6a0474afa2320372625fd',), ('e2debd0afa0374406edac549',),
            ('dffe3a06219ce6b4f3a912e0','8e33b40431a99da8b577370c'),
            ('ccaec75370c2b2c06c2a4f43','45cfa8213498ae1890fdd179'),
            ('9262f7379038746a1c801fe8',),
        )
        for ids in groups:
            with self.subTest(sources=ids):
                events, _ = self.cluster_sources(*ids)
                self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','software_systems')])

    def test_supplier_statement_keeps_its_owner_across_translations(self):
        events, _ = self.cluster_sources('1937e97391e82bbaba14f3c5','6a36b138d379794f953d510d')
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','hardware_products')])

    def test_independent_inspections_keep_observers_and_local_measurements(self):
        own, _ = self.cluster_sources('48cfab893ca8b6f6f89901ba')
        self.assertEqual(len(own), 2)
        self.assertEqual({a.bound_claim.object for e in own for a in e.articles}, {'ifixit','wekihome'})
        events, _ = self.cluster_sources('48cfab893ca8b6f6f89901ba','c1524ada08e410122cfae6ec')
        self.assertEqual(len(events), 2, [e.title for e in events])
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products' for e in events))
        claims = [a.bound_claim for e in events for a in e.articles]
        self.assertEqual({c.object for c in claims}, {'ifixit','wekihome'})
        for claim in claims:
            if claim.article_id != '48cfab893ca8b6f6f89901ba':
                continue
            units = {u['unit_id']: u['text'] for u in self.rows[claim.article_id]['evidence']['units']}
            text = ' '.join(units[k][a:b] for k,a,b in claim.evidence_spans)
            if claim.object == 'wekihome':
                self.assertIn('1.91', text)
                self.assertIn('3.29', text)
                self.assertIn('681.5', text)
            else:
                self.assertNotIn('1.91', text)
                self.assertNotIn('681.5', text)
                self.assertIn('粉尘侵入测试', text)

    def test_publication_members_region_and_actions_keep_local_stage(self):
        from apple_news_core.event_identity import (build_event_identity, source_named_publication_frame,
            source_platform_component_frame, source_trade_secret_procedure_frame)
        title = 'Apple shares new Apple Watch stories'
        lead = 'Apple today shared a video from its "True Apple Watch Story" series.'
        for background in ('A video released last year features Morgan.', 'A future video will feature Morgan.'):
            result = source_named_publication_frame(title, lead, (lead, 'The video features Josh.', background),
                build_event_identity(title, lead))
            self.assertTrue(result.subject.endswith(':josh'), result)
        title = '苹果韩国官网 iPad mini A20 Pro 宣传图调整'
        text = '韩国官网仍保留 iPad mini A20 Pro 的手指宣传图。苹果在美国官网移除了对应手指。'
        result = source_named_publication_frame(title, text, (text,), build_event_identity(title, text))
        self.assertEqual(result.region, '美国')
        for action in ('will bring', 'bring'):
            result = source_platform_component_frame('Apple Fixes CoreGraphics Flaw on Older iPhones',
                f'iOS 18.7.11 and iPadOS 18.7.11 {action} the CoreGraphics fix next month.', ())
            self.assertFalse(result and result.action == 'component-security-fix')
        title = 'Apple wins expanded access to evidence in OpenAI trade secrets lawsuit'
        text = ('In the OpenAI trade secrets lawsuit, the judge granted discovery last year. '
                'The court has not granted the new request.')
        self.assertIsNone(source_trade_secret_procedure_frame(title, text, (), build_event_identity(title, text)))

    def test_caption_and_supplier_cannot_replace_explicit_local_owner(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_attributed_device_tests, bind_manufacturing_reports
        evidence = self.source_articles('48cfab893ca8b6f6f89901ba')[0].evidence
        text = ('iFixit 在拆解 iPhone Duo 中发现，屏幕采用可更换结构。', '图｜YouTube @WekiHome')
        units = tuple(replace(evidence.units[i], kind='p', text=t) for i, t in enumerate(text))
        claims = bind_attributed_device_tests(replace(evidence, raw_lead=text[0], units=units))
        self.assertEqual({c.object for c in claims}, {'ifixit'})
        evidence = self.source_articles('6a36b138d379794f953d510d')[0].evidence
        text = ('The iPhone Duo screen failure is under investigation.',
                'A statement from RivalCo released on October 26 discussed Galaxy hinge quality.',
                '"The quality issues were not caused by our components," RivalCo said.')
        units = tuple(replace(evidence.units[i], kind='p', text=t) for i, t in enumerate(text))
        claims = bind_manufacturing_reports(replace(evidence, raw_lead=text[0], units=units))
        self.assertFalse(claims)

    def test_live_window_translations_keep_the_same_current_report(self):
        from apple_news_core.event_identity import current_public_os_release
        for lead in ('苹果正式向用户推送iOS27.2系统更新（Beta 4）。',
                     '苹果计划明天正式向用户推送iOS27.2系统更新。',
                     '苹果去年正式向用户推送iOS27.2系统更新。',
                     '苹果否认正式向用户推送iOS27.2系统更新。'):
            self.assertIsNone(current_public_os_release('苹果发布iOS27.2系统更新',lead))
        groups = (
            ('d76bd776aa5d13eba48a58c8','d9933239741ea24fdd1b5484'),
            ('aa7b3f5a714ea21d37aa7760','3880ac9ad26534ecb613442f'),
            ('81faf951e0dbb34a7b13b097','95b48b767099f4e5855d1d48'),
            ('c475cac67820dd7819e8172b','148bb7d38939a06c37d785c0'),
            ('6378b126741869596a846b9b','ccaec75370c2b2c06c2a4f43'),
            ('4e8c59f8de302a505725a893','42d98dcab7a0954805b56516'),
            ('8467b57bfd9fe2d9f9d1c3de','dffe3a06219ce6b4f3a912e0'),
            ('1ff15a10326e70a3d466d314','0ba453be34861437cc898340','ff326ef10edd8a6725d57903'),
            ('b1710181e8fccace9ba5a814','03e20cf8cc03f806635cd9c6'),
            ('c4a9e2a038dc130dbb708917','d54108fa274df8c59508f922','7676786b2c8bf09925a108c5',
             'ab2acf32521bacca1d98de8d','b0990f66d1d9379f72faaa89'),
        )
        for ids in groups:
            with self.subTest(sources=ids):
                events, _ = self.cluster_sources(*ids)
                self.assertEqual(len(events), 1, [(e.title,e.relevance_tier) for e in events])
                self.assertEqual(events[0].relevance_tier,'strong')

    def test_live_advertising_and_platform_ports_keep_the_actual_operation(self):
        ad = '3b7de94c97fdf3b992e59665'
        events, _ = self.cluster_sources(ad,'ccb352cf135b776152cb8505','84280fd8c4966c5eb3a8a158')
        owned = [e for e in events if any(a.evidence.article_id == ad for a in e.articles)]
        self.assertEqual(len(owned),1)
        self.assertEqual(owned[0].category,'software_systems')
        self.assertEqual({a.evidence.article_id for a in owned[0].articles},{ad})
        events, _ = self.cluster_sources('f32bbb044966ad3b4b1f6e2d')
        self.assertEqual([e.relevance_tier for e in events],['weak'])
        events, _ = self.cluster_sources('85c1ccf1f03f29fe56505ceb')
        self.assertEqual([(e.relevance_tier,e.category) for e in events],[('ecosystem','software_systems')])

    def test_runtime_owner_asset_and_feature_stage_are_defining_scope(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_interoperability_report
        from apple_news_core.event_matcher import profile_pair_decision
        evidence = self.source_articles('85c1ccf1f03f29fe56505ceb')[0].evidence
        for tail in ('另一项目 ProjectB 把 HOS 系统调用转换为 iOS 系统调用。',
                     '该项目尚未把 HOS 系统调用转换为 iOS 系统调用。'):
            text = ('开发者展示了游戏在macOS上运行的画面。这个项目是 ProjectA 的一个分支版本。', tail)
            units = tuple(replace(evidence.units[i], kind='p', text=t) for i,t in enumerate(text))
            self.assertIsNone(bind_interoperability_report(replace(evidence,
                title='开发者成功在macOS上运行游戏', raw_lead=text[0], units=units)), tail)
        def profile(title, body):
            return self.m.article_reconciliation_profile(article_for(self.m,title,body))
        ads = [profile('Apple shares new 14-inch M6 MacBook Pro ad: ' + name,
            'Apple’s YouTube channel has published an ad for the new 14-inch M6 MacBook Pro titled "' + name + '".')
            for name in ('Boost Mode','Night Work')]
        self.assertEqual(profile_pair_decision(*ads),'conflict')
        self.assertNotEqual(profile_pair_decision(
            profile('iOS 27.2 beta adds selfie age verification',
                    'iOS 27.2 beta introduces age verification using a selfie.'),
            profile('iOS 27.2正式版新增自拍年龄验证', 'iOS 27.2正式版新增自拍年龄验证功能。')), 'match')

    def test_reported_service_and_official_appearance_differ_from_commentary(self):
        for sid, category in (('6834b5b340cef4a64c752082','hardware_products'),
                              ('148ec3ddab472c44e90c08f9','software_systems')):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong',category)])
        events, _ = self.cluster_sources('3b6961a498acdcafc13a9974')
        self.assertEqual([e.relevance_tier for e in events],['weak'])

    def test_current_configuration_provider_and_components_are_local(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_configuration_disclosure_claim
        evidence = self.source_articles('c4a9e2a038dc130dbb708917')[0].evidence
        def claim(texts):
            units = tuple(replace(evidence.units[i], kind='p', text=t) for i,t in enumerate(texts))
            return bind_configuration_disclosure_claim(replace(evidence,raw_lead=texts[0],units=units))
        value = claim(('Leaker Alpha News previously discussed the iPhone 18e.',
            'In a new post on Weibo, leaker Beta News said the iPhone 18e will have an OLED display, A20 chip and 48 megapixel camera.'))
        self.assertTrue(value.subject.endswith(':reporter:beta-news'))
        self.assertIsNone(claim(('Leaker Alpha News has details on the iPhone 18e.',
            'In a new post on Weibo, the leaker said the iPhone 18e will have an OLED display.',
            'The iPhone 17e has an A19 chip and a 48 megapixel camera.')))
        self.assertIsNone(claim(('爆料者“数码闲聊站”近日在微博称，iPhone 18e可能采用OLED屏幕。',
            '现款iPhone 17e采用A19芯片和4800万像素摄像头。')))

    def test_supporting_observation_does_not_create_another_investigation(self):
        events, _ = self.cluster_sources('c9aefb1f98dc724702f95b12','c1524ada08e410122cfae6ec')
        self.assertEqual(len(events),1)
        self.assertEqual({a.bound_claim.object for e in events for a in e.articles},{'ifixit'})
        from dataclasses import replace
        from apple_news_core.event_identity import bind_attributed_device_tests
        for event in events:
            for article in event.articles:
                evidence = article.evidence
                _, remaining, _ = self.m.project_article_evidence(evidence)
                units = {u.unit_id:u.text for u in evidence.units}
                text = ' '.join(units[k][a:b] for k,a,b in remaining)
                self.assertIn('CuriousHagi', text)
                self.assertTrue('snapped' in text or '断裂' in text)
                observation = next(u for u in evidence.units if 'CuriousHagi' in u.text)
                dedicated = replace(evidence, title='CuriousHagi tests the iPhone Duo hinge',
                    raw_lead=observation.text, units=(observation,))
                self.assertIn('curioushagi', {c.object for c in bind_attributed_device_tests(dedicated)})

    def test_platform_code_discovery_is_not_a_device_design_disclosure(self):
        software = 'e1c128c2b767e723fd36b43c'
        events, _ = self.cluster_sources(software,'23f31eaacc42fe622943136b')
        self.assertEqual(len(events),2)
        event = next(e for e in events if any(a.evidence.article_id==software for a in e.articles))
        self.assertEqual((event.category,event.relevance_tier),('software_systems','strong'))
        from apple_news_core.event_identity import source_software_capability_frame
        for lead in ('去年在macOS 27.2中发现了触控代码。',
                     'Nimbus发布一款macOS 27.2触控代码编辑器。',
                     '开发者没有发现macOS 27.2中的触控代码。',
                     '开发者计划下周挖掘macOS 27.2中的触控代码。',
                     '开发者希望在macOS 27.2中发现触控代码。'):
            self.assertIsNone(source_software_capability_frame('触控 Mac：macOS 27.2代码线索',lead,()))
        lead = 'Nimbus发布一款macOS 27.2触控代码编辑器。'
        for unrelated in ('Researchers discovered a Windows vulnerability.',
                          'The iOS 26 beta includes a new wallpaper.',
                          'The macOS 26 beta adds new touch gestures.',
                          'The macOS 27.2 beta includes a new wallpaper.'):
            self.assertIsNone(source_software_capability_frame('触控 Mac：macOS 27.2代码线索',
                lead, (lead, lead, lead, unrelated)))

    def test_pricing_and_configuration_angles_keep_the_attributed_report(self):
        ids = ('b6b0c420e7d187bf32a61972','f6ea8ed69505b456e464b3c9',
               'd8bb215e2fab19af6aec869a','86cb894c28a1e7340be3ebc4',
               'a85d8759c421e85d4c393499','2df34b3fddc9028425218ab2',
               'ccb352cf135b776152cb8505')
        events,_ = self.cluster_sources(*ids)
        self.assertEqual(len(events),1,[(e.title,len(e.articles)) for e in events])
        self.assertEqual(events[0].relevance_tier,'strong')
        events,_ = self.cluster_sources(*ids,'23f31eaacc42fe622943136b','d3ef598e6295a5d21f59254f')
        self.assertEqual(len(events),2)
        events,_ = self.cluster_sources(*ids,'84280fd8c4966c5eb3a8a158')
        self.assertEqual(len(events),2)
        extra = next(a for e in events for a in e.articles if a.evidence.article_id=='84280fd8c4966c5eb3a8a158')
        self.assertEqual(extra.bound_claim.action,'proposed-price-configuration-report')
        from dataclasses import replace
        from apple_news_core.event_identity import bind_configuration_disclosure_claim
        from apple_news_core.event_matcher import profile_pair_decision
        from apple_news_core.event_reconciler import bound_reconciliation_profile
        design = self.source_articles('23f31eaacc42fe622943136b')[0].evidence
        for text in ('Mark Gurman posted on X to deny the new MacBook Pro redesign claim.',
                     '记者马克·古尔曼今日在 X 平台发文，否认 MacBook Pro 将采用新转轴设计。'):
            denied = bind_configuration_disclosure_claim(replace(design,raw_lead=text,
                units=(replace(design.units[0],kind='p',text=text),)))
            self.assertEqual(denied.polarity,'denied')
            self.assertEqual(profile_pair_decision(bound_reconciliation_profile(denied),
                bound_reconciliation_profile(bind_configuration_disclosure_claim(design))),'conflict')
        evidence = self.source_articles(ids[1])[0].evidence
        for text in (
            'According to Bloomberg, Apple now charges $2899 for the MacBook Pro.',
            'According to Bloomberg, Apple has not discussed charging $2899 for the MacBook Pro.',
            'According to Bloomberg, last year Apple discussed charging $2899 for the MacBook Pro.',
            'According to Bloomberg, Apple discussed charging $2899 for the iPad Pro.',
            'According to Bloomberg, Dell discussed charging $2899 for its new laptop.',
        ):
            unit = replace(evidence.units[0],kind='p',text=text)
            self.assertIsNone(bind_configuration_disclosure_claim(replace(evidence,raw_lead=text,units=(unit,))),text)
        intro = 'Bloomberg’s Mark Gurman shared new details about MacBook Pro pricing.'
        for text, owner in (
            ('Last year, Apple discussed charging $2,899 for the MacBook Pro.',None),
            ('According to Reuters, Apple discussed charging $2,899 for the MacBook Pro.','reuters'),
        ):
            units = tuple(replace(evidence.units[i],kind='p',text=value) for i,value in enumerate((intro,text)))
            claim = bind_configuration_disclosure_claim(replace(evidence,raw_lead=intro,units=units))
            if owner:
                self.assertIn(':reporter:' + owner, claim.subject)
            else:
                self.assertIsNone(claim)

    def test_named_preorder_batch_is_a_schedule_not_an_editorial_inventory(self):
        events,_ = self.cluster_sources('c62d3fdeff301e9fd041fc09')
        self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong','hardware_products')])
        self.assertEqual(len(events[0].articles),1)
        from apple_news_core.event_identity import source_dated_launch_frame
        title = 'Apple to Open Pre-Orders for New Products Today'
        for text in ('Last year, pre-orders for iPad mini and iMac open at 10:10 a.m.',
                     'Pre-orders for iPad mini and iMac will not open at 10:10 a.m.',
                     'We guess pre-orders for iPad mini and iMac open at 10:10 a.m.'):
            self.assertIsNone(source_dated_launch_frame(title,text,(text,)))
        current = 'Pre-orders for iPad mini and iMac open at 10:10 a.m.'
        for other in ('Last year, pre-orders for MacBook Air opened at 10:10 a.m.',
                      'Pre-orders for MacBook Air open at 10:10 a.m. next week.',
                      'We guess pre-orders for MacBook Air open at 10:10 a.m.'):
            frame = source_dated_launch_frame(title,current,(current,other))
            self.assertEqual(frame.subject,'apple:preorder-batch:imac+ipad-mini')

    def test_authored_preview_and_buying_guide_cannot_borrow_release_background(self):
        release = 'cefffca1cd6ff13606b88e82'
        for sid in ('7d4c92f297f4f75b1a31de79', 'b6ab7f24ae39f61be39f990b'):
            title, summary, facts = self.rows[sid]['recorded_extraction']
            article = article_for(self.m, title, summary)
            article.key_facts = facts
            events = self.m.cluster_articles([article, *self.source_articles(release)])
            self.assertEqual(len(events), 2)
            self.assertEqual(next(e.relevance_tier for e in events if article in e.articles), 'weak')
            self.assertEqual(next(e.relevance_tier for e in events if article not in e.articles), 'strong')

    def test_sparse_release_uses_the_report_projection_before_fact_coverage(self):
        from apple_news_core.article_projector import single_article_input_projection
        for title in ('苹果发布iOS 27.2更新 Siri AI新增多语言支持并带来160余项安全修复',
                      'Apple releases iOS 27.2 with Siri language support',
                      '苹果发布tvOS 28.1更新，Siri新增法语支持'):
            with self.subTest(title=title):
                candidate = self.m.Candidate('cnBeta', 'https://example.com/release', title)
                self.m.candidate_detail_priority(candidate)
                evidence = self.m.capture_article_title_evidence('cnBeta', candidate.url, title, '', ())
                self.assertIsNone(single_article_input_projection(evidence))

    def test_court_order_uses_requesting_party_not_headline_speaker(self):
        ids = ('3e18ba4b2d84398a7c1ce224', 'd5d6a0474afa2320372625fd', 'b7603bafef3b0755fc0f22f0')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].category, 'software_systems')
        from apple_news_core.event_identity import source_trade_secret_procedure_frame, build_event_identity
        title = "Judge grants Apple's requests for OpenAI information"
        for clause in ('Last year the judge granted discovery in the trade secrets lawsuit.',
                       'The judge has not granted discovery in the trade secrets lawsuit.',
                       'The judge may grant discovery in the trade secrets lawsuit.',
                       "In the trade secrets lawsuit, Judge Davila granted OpenAI's request for discovery from Apple.",
                       'In the trade secrets lawsuit, Judge Davila ordered Apple to provide OpenAI with discovery records.'):
            with self.subTest(clause=clause):
                self.assertIsNone(source_trade_secret_procedure_frame(title, clause, (), build_event_identity(title, clause)))

    def test_code_assets_keep_actual_component_and_source_version(self):
        ids = ('ccdf98b1b31e8428ebfd2cbd', 'e837b48ac33bee622af1944b', 'd87e435d50a2e0b3836af4cb')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                             {frozenset(ids[:2]), frozenset(ids[2:])})
            self.assertTrue(all(e.category == 'software_systems' and e.relevance_tier == 'strong' for e in events))
        from apple_news_core.event_identity import source_software_capability_frame
        for body in ('A leaker inspected macOS 27 code. He found Dynamic Island assets in Windows 12.',
                     'A leaker inspected macOS 27 code. He hopes to find Dynamic Island assets.',
                     'A leaker inspected macOS 27 code. He did not find Dynamic Island assets.',
                     'A leaker did not inspect macOS 27 code. He found Dynamic Island assets.',
                     'A leaker hopes to inspect macOS 27 code. He found Dynamic Island assets.',
                     'A leaker inspected macOS 27 code. He found no Dynamic Island assets.',
                     'A leaker inspected macOS 27 code. Separately, in version 28, he found Dynamic Island assets.'):
            with self.subTest(body=body):
                self.assertIsNone(source_software_capability_frame('Dynamic Island assets in macOS 27', body, ()))

    def test_reported_display_fault_is_not_erased_by_reader_opinions(self):
        events, _ = self.cluster_sources('e7f8a44fa5694ac23191d24e')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        from apple_news_core.event_identity import source_software_capability_frame
        for body in ('对比测试中，博主晒出的截图显示，安卓手机的游戏画面被压缩在中央，四周有黑边。iPhone Duo运行同一游戏时显示正常。',
                     'iPhone Duo运行游戏正常。博主截图显示安卓手机的游戏画面被压缩，周围有黑边。'):
            self.assertIsNone(source_software_capability_frame('iPhone Duo游戏黑边讨论', body, ()))

    def test_native_camera_operation_is_not_downgraded_as_instructions(self):
        events, _ = self.cluster_sources('25a5f304a6eb1215d09a97c5')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        from apple_news_core.event_identity import source_software_capability_frame
        title = 'iPhone Duo: Take Selfies With Rear Cameras'
        opening = 'The iPhone Duo lets you use its rear cameras for selfies. '
        operation = "The Duo's outer display shows a live preview along with the camera controls."
        facts = ('Open the Camera app.',)
        frame = source_software_capability_frame(title, opening + operation, facts)
        self.assertIsNotNone(frame)
        for body in (operation.replace('shows', 'does not show'),
                     operation.replace('shows', 'will show'),
                     operation.replace('shows', 'used to show'),
                     operation.replace("Duo's", "Galaxy's"),
                     operation.replace('shows', 'uses a third-party app that shows')):
            self.assertIsNone(source_software_capability_frame(title, opening + body, facts), body)
        self.assertIsNone(source_software_capability_frame('iPhone Duo buying advice', opening + operation, facts))
        self.assertIsNone(source_software_capability_frame('iPhone Duo: Duo Preview for your subject', opening + operation, facts))

    def test_design_relation_does_not_borrow_background_launch_schedule(self):
        ids = ('7e52c965555151c0a19c10ab', '7c4ce3f08cfd8a9dc36ab2dc')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products' for e in events))
        from dataclasses import replace
        from apple_news_core.event_identity import bind_configuration_disclosure_claim
        evidence = self.source_articles(ids[0])[0].evidence
        for target, expected in (('the iPhone Duo 2 will have a new hinge design', None),
                                 ('the iPhone Duo 2 will have a new hinge design. The MacBook Pro is expected later today', None),
                                 ('the MacBook Pro will not feature hinge improvements', 'denied')):
            text = 'In a new Weibo post, the leaker known as "Fixed Focus Digital" said that ' + target + '.'
            unit = replace(next(u for u in evidence.units if 'new Weibo post' in u.text), text=text)
            claim = bind_configuration_disclosure_claim(replace(evidence, raw_lead=text, units=(unit,)))
            if expected is None:
                self.assertIsNone(claim)
            else:
                self.assertEqual(claim.polarity, expected)

    def test_current_video_posts_keep_publication_separate_from_product_rumors(self):
        resolved = ('85c87e24deb487833566d8ba', 'f545f3cb5f7bd9f926c95306')
        events, _ = self.cluster_sources(*resolved, '1204af76f01cee87b340576f', 'aded77643d94603858db3ca6', 'f13fcbd9d361925ad0e453fb', '7e52c965555151c0a19c10ab')
        self.assertEqual(len(events), 6)
        for sid in (*resolved, '1204af76f01cee87b340576f', 'aded77643d94603858db3ca6', 'f13fcbd9d361925ad0e453fb'):
            event = next(e for e in events if any(a.evidence.article_id == sid for a in e.articles))
            self.assertEqual((event.relevance_tier, event.category), ('strong', 'software_systems'), sid)
        from apple_news_core.event_identity import bind_content_updates
        self.assertIsNone(bind_content_updates(self.source_articles('9ab0117131c4c375083f6e83')[0].evidence))

    def test_design_post_translations_share_current_reporter(self):
        ids = ('7e52c965555151c0a19c10ab', '24e49df7249ee0fde30001c6', '74964a62c52e5dcb474f0591')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_translated_system_resources_keep_discovery_version(self):
        ids = ('ea6bdbe9b016fc8a68904985', 'e837b48ac33bee622af1944b', 'ccdf98b1b31e8428ebfd2cbd')
        events, _ = self.cluster_sources(*ids, 'd87e435d50a2e0b3836af4cb')
        self.assertIn(frozenset(ids), {frozenset(a.evidence.article_id for a in e.articles) for e in events})
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'software_systems' for e in events))

    def test_private_runtime_demo_keeps_current_target_platform(self):
        ids = ('cb5cab8d28289aa5601e0112', '85c1ccf1f03f29fe56505ceb')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'ecosystem' and e.category == 'software_systems' for e in events),
                        [(e.title, e.relevance_tier) for e in events])

    def test_publication_requires_current_publisher_and_resolved_shared_object(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_content_updates
        from apple_news_core.event_matcher import identity_pair_decision
        evidence = self.source_articles('85c87e24deb487833566d8ba')[0].evidence
        unit = next(u for u in evidence.units if u.kind == 'p')
        for text in ('Last year John Ternus posted a teaser video.',
                     'John Ternus plans to publish a teaser video.',
                     'John Ternus has not posted a teaser video.',
                     'Former Apple CEO Alex Blue posted a teaser video.',
                     'Samsung CEO Alex Blue posted a teaser video.',
                     'John Ternus shared a short video of his dog playing in his garden.',
                     'John Ternus said a fan posted a teaser video about a MacBook concept.'):
            changed = replace(evidence, raw_lead=text, units=(replace(unit, text=text),))
            self.assertIsNone(bind_content_updates(changed), text)
        foreign = replace(evidence, embedded_references=tuple(replace(ref,
            url='https://x.com/timcook/status/123456789', object_id='123456789') for ref in evidence.embedded_references))
        self.assertFalse(bind_content_updates(foreign)[0].qualifiers)
        historical = replace(evidence, units=tuple(replace(u, text=u.text.replace('October 28, 2026', 'October 28, 2025')) for u in evidence.units))
        self.assertFalse(bind_content_updates(historical)[0].qualifiers)
        claim = bind_content_updates(evidence)[0]
        other = replace(claim, qualifiers=tuple((a,b,'x:another',d,e,f) for a,b,c,d,e,f in claim.qualifiers))
        self.assertEqual(identity_pair_decision(claim, other), 'unknown')
        unknown = replace(claim, qualifiers=())
        self.assertEqual(identity_pair_decision(claim, unknown), 'unknown')
        self.assertEqual(identity_pair_decision(unknown, unknown), 'unknown')

    def test_private_runtime_does_not_borrow_historical_or_proposed_demonstration(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_interoperability_report
        evidence = self.source_articles('cb5cab8d28289aa5601e0112')[0].evidence
        base = next(u for u in evidence.units if 'Will Faust使用' in u.text)
        for change in ('计划完成', '未能完成', '去年完成了'):
            text = base.text.replace('完成了', change)
            candidate = replace(evidence, units=(replace(base, text=text),))
            self.assertIsNone(bind_interoperability_report(candidate), text)
        text = 'Will Faust使用私人修改版nxnative完成了安卓手机演示。nxnative会在苹果ARM硬件上直接执行原始Switch程序代码，同时将任天堂图形接口转换为Metal。'
        android = replace(evidence, title='nxnative完成安卓手机演示', raw_lead=text, units=(replace(base, text=text),))
        self.assertIsNone(bind_interoperability_report(android))
        claim = bind_interoperability_report(evidence)
        selected = ' '.join(u.text[a:b] for key,a,b in claim.evidence_spans for u in evidence.units if u.unit_id == key)
        self.assertNotIn('Eden', selected)
        self.assertIn('不会发布', selected)

    def test_component_name_alone_does_not_identify_a_feature_discovery(self):
        from apple_news_core.event_identity import source_software_capability_frame
        self.assertIsNone(source_software_capability_frame('macOS 27 MenuBarAgent memory leak discovered',
            'Researchers found a memory leak in macOS 27 MenuBarAgent code.', ()))

    def test_author_name_speculation_does_not_inherit_teaser_eligibility(self):
        events, _ = self.cluster_sources('9ab0117131c4c375083f6e83')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events), [(e.title, e.relevance_tier) for e in events])

    def test_education_price_change_does_not_merge_with_launch_price_comparison(self):
        events, _ = self.cluster_sources('51af8018fbd1569f2200d346', '3192145f0c1d22c25aacc659')
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products' for e in events))
        from apple_news_core.event_identity import source_device_operation_frame
        title = "Apple Raises MacBook Neo's Starting Price on Education Store"
        for lead in ("Apple has not raised the MacBook Neo's price on its education store.",
                     "Apple raised the MacBook Neo's price on its education store last year.",
                     "A retailer raised the MacBook Neo's price. Apple may follow."):
            frame = source_device_operation_frame(title, lead)
            self.assertFalse(frame and frame.action == 'price-increase', lead)

    def test_filming_completion_is_not_an_inferred_release_schedule(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_content_updates
        events, _ = self.cluster_sources('75e9d6d33243226dc389cc7b', '9939a5bb9fe321137a46f5f5')
        self.assertEqual(len(events), 1)
        evidence = self.source_articles('75e9d6d33243226dc389cc7b')[0].evidence
        claim = bind_content_updates(evidence)[0]
        self.assertEqual((claim.action, claim.object, claim.category), ('production-completed', 'season:4', 'software_systems'))
        selected = ' '.join(u.text[a:b] for key,a,b in claim.evidence_spans for u in evidence.units if u.unit_id == key)
        self.assertNotIn('2027', selected)
        self.assertIn('Jessica Williams', selected)
        unit = next(u for u in evidence.units if 'Jessica Williams' in u.text)
        for text in ('Jessica Williams hopes season 4 has officially wrapped production.',
                     'Jessica Williams denied that season 4 has officially wrapped production.',
                     'By comparison, Ted Lasso season 4 has officially wrapped production.',
                     'By comparison, Ted Lasso season four has officially wrapped production.',
                     "By comparison, Ted Lasso's filming has concluded for season four."):
            changed = replace(evidence, units=(replace(unit, text=text), replace(unit, unit_id='host', text='Shrinking airs on Apple TV.')))
            self.assertIsNone(bind_content_updates(changed), text)


if __name__ == '__main__':
    unittest.main()
