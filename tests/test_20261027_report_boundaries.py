"""Current source actors and predicates, rather than shared background, group reports."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import article_for, load_module
import test_p4_pure_json_batch as prior


class ReportBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261027_report_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 27, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    def test_launch_window_sales_and_outer_display_report_remain_independent(self):
        events, _ = self.cluster_sources('148bb7d38939a06c37d785c0', '66b07107e8b584959f1d2668')
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products'
                            for e in events), [(e.title, e.relevance_tier) for e in events])

    def test_launch_measurement_uses_current_model_period_and_institution(self):
        from apple_news_core.event_identity import source_weekly_device_measurement
        title = 'Counterpoint：iPhone 18 Pro上市三周全球销量增长'
        body = 'Counterpoint报告显示，iPhone 18 Pro系列上市三周，全球销量较去年同期的iPhone 17 Pro系列增长3.1%。'
        frame = source_weekly_device_measurement(title, body)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.period, 'launch-first-3-weeks')
        self.assertEqual(frame.region, 'global')
        self.assertIn('iphone-18-pro', frame.subject)
        self.assertIn('counterpoint', frame.subject)
        for changed in (body.replace('报告显示', '计划发布报告'),
                        body.replace('报告显示', '去年报告显示'),
                        body.replace('全球销量', '三星手机全球销量'),
                        body.replace('全球销量较去年同期的iPhone 17 Pro系列增长3.1%', 'iPhone 17 Pro全球销量增长3.1%'),
                        body.replace('全球销量较去年同期的iPhone 17 Pro系列增长3.1%', 'iPhone 17 Pro促销后需求回升，全球销量增长3.1%'),
                        body.replace('全球销量较', '而IDC报告显示iPhone 18 Pro全球销量较'),
                        body.replace('全球销量较', 'IDC报告显示iPhone 18 Pro全球销量较'),
                        body.replace('全球销量较', '预计全球销量较'),
                        body.replace('增长3.1%', '没有公布销量'),
                        body.replace('全球销量较去年同期的iPhone 17 Pro系列增长3.1%',
                                     '没有公布销量；iPhone 17 Pro全球销量增长3.1%'),
                        body.replace('iPhone 18 Pro', 'iPhone 19 Pro'),
                        body.replace('上市三周', '上市')):
            self.assertIsNone(source_weekly_device_measurement(title, changed), changed)
        other = source_weekly_device_measurement(title.replace('Counterpoint', 'IDC'), body.replace('Counterpoint', 'IDC'))
        self.assertNotEqual(frame.subject, other.subject)
        english = source_weekly_device_measurement('iPhone 18 Pro launch sales',
            'Counterpoint report shows iPhone 18 Pro in the first 3 weeks after launch, global sales grew 3.1% compared to iPhone 17 Pro.')
        self.assertIsNotNone(english)
        self.assertEqual(english.period, frame.period)

    def test_display_issue_cannot_borrow_another_surface_or_past_report(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPhone Duo外屏出现绿线'
        body = '有网友反映，他的iPhone Duo外屏出现绿线，没有摔过或磕碰。'
        self.assertIsNotNone(source_device_operation_frame(title, body))
        for changed in (body.replace('外屏', '内屏'), '去年，' + body,
                        body.replace('出现绿线', '没有出现绿线'),
                        body.replace('外屏出现绿线', '外屏正常，内屏出现绿线'),
                        body.replace('外屏出现绿线', '外屏正常而内屏出现绿线'),
                        body.replace('外屏出现绿线', '外屏正常，三星手机外屏出现绿线'),
                        body.replace('外屏出现绿线', '外屏将在明年出现绿线'),
                        body.replace('他的iPhone Duo外屏', '他的三星手机外屏')):
            self.assertIsNone(source_device_operation_frame(title, changed), changed)

    def test_physical_repair_document_keeps_hardware_category(self):
        events, _ = self.cluster_sources('41dc755c1ed064095999c36d')
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('strong', 'hardware_products')])

    def test_repair_document_owner_does_not_capture_software_or_background(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'Apple publishes iPhone 18 screen support documents'
        body = 'Apple has published support documents for iPhone 18 screen replacement.'
        frame = source_device_operation_frame(title, body)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.category, 'hardware_products')
        for changed in (body.replace('Apple has published', 'A repair shop has published'),
                        body.replace('has published', 'plans to publish'),
                        body.replace('has published', 'has not published'),
                        'Last year, ' + body,
                        body.replace('screen replacement', 'Screen Time settings'),
                        'Apple has published support documents for iPhone 18 Screen Time, '
                        'while a repair shop describes screen replacement.',
                        'Apple has published support documents for iPhone 18 Screen Time. '
                        'A repair shop describes screen replacement.',
                        'Today, Apple has published iPhone 18 screen replacement photos, '
                        'a repair shop has published support documents.',
                        'Apple has published iPhone 18 screen replacement photos while '
                        'a repair shop has published support documents.'):
            self.assertIsNone(source_device_operation_frame(title, changed), changed)
        self.assertEqual(source_device_operation_frame(title, 'Today, ' + body), frame)
        self.assertIsNone(source_device_operation_frame('苹果发布iPhone Duo铰链故障排查文档',
            '苹果为iPhone Duo计划发布支持文档，介绍铰链故障排查。'))
        self.assertIsNone(source_device_operation_frame('苹果发布iPhone Duo铰链故障排查文档',
            '快科技10月26日消息，苹果发布iPhone Duo铰链照片，维修店发布支持文档。'))

    def test_release_overview_joins_the_actual_platform_release(self):
        events, _ = self.cluster_sources('27fdb4a2f93959ed34210f67')
        a, = self.source_articles('27fdb4a2f93959ed34210f67')
        keys = self.m.article_reconciliation_profile(a).event_keys
        self.assertIn('apple-os-release-wave:27.2:final:ios', keys)
        from apple_news_core.event_identity import current_public_os_release
        for body in ('苹果公司计划面向 iPhone 推送 iOS 27.2 正式版更新。',
                     '苹果公司今天面向 iPhone 用户宣布，计划明年发布 iOS 27.2 正式版更新。',
                     '苹果公司今天面向 iPhone 用户表示，将于明年推送 iOS 27.2 正式版更新。',
                     '苹果公司今天面向 iPhone 推送 iOS 27.1 正式版更新。',
                     '苹果公司今天面向 iPhone 推送 iOS 27.2 测试版更新。'):
            self.assertIsNone(current_public_os_release(a.title, body))

    def test_functional_team_handoff_keeps_its_actual_hardware_role(self):
        events, _ = self.cluster_sources('a28cfef279b3999c97c6e8bb')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        from apple_news_core.event_identity import source_owned_organization_frame
        title = '苹果显示技术团队迎来交接'
        for body in ('苹果显示技术团队计划明年交出管理职责。',
                     '苹果否认显示技术团队交出管理职责。',
                     '苹果显示技术团队与三星合作，三星已经交出管理职责。',
                     '三星显示技术团队交出管理职责。'):
            self.assertIsNone(source_owned_organization_frame(title, body))

    def test_focused_native_capabilities_keep_software_identity_and_boundaries(self):
        ids = ('3b54ee28e490db490e275867', '29057c40456adb95b5b17b9f',
               '25154bc2ac833ad74b19bbf5', '5902ff4e6b00275d58d630ac')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 4)
            self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'software_systems'
                                for e in events), [(e.title, e.relevance_tier, e.category) for e in events])

    def test_vendor_neutral_market_report_binds_its_period_and_apple_percentage_rank(self):
        events, _ = self.cluster_sources('81c3359cc7722becc0f7bb7a')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        a, = self.source_articles('81c3359cc7722becc0f7bb7a')
        keys = self.m.article_reconciliation_profile(a).separation_keys
        self.assertIn('source-report-year:2026', keys)
        self.assertIn('source-report-period:q3', keys)

    def test_current_native_capabilities_and_market_ranks_require_their_owner(self):
        from apple_news_core.event_identity import source_software_capability_frame, source_market_measurement_frame
        title = 'iPhone Duo camera preview'
        body = 'Apple supports iPhone Duo with a feature called Camera Preview, which shows the main camera image.'
        self.assertIsNotNone(source_software_capability_frame(title, body, ()))
        for changed in (body.replace('Apple supports', 'A third-party app supports'),
                        'Last year, ' + body, body.replace('Apple supports', 'Apple plans to support'),
                        body.replace('Apple supports', 'Apple showcases CameraPro on')):
            self.assertIsNone(source_software_capability_frame(title, changed, ()), changed)
        self.assertIsNone(source_software_capability_frame('Quickly Silence iPhone Duo',
            'The iPhone Duo runs MutePro. MutePro adds a Control Center control. '
            'Its Silent Mode mutes calls and alerts.', ()))
        self.assertIsNone(source_software_capability_frame('iPhone Duo: Watch Video Above an App in Portrait Mode',
            "The iPhone Duo's two-app multitasking feature works side by side in landscape. "
            'Picture in Picture in portrait is planned for next year.', ()))
        title = 'Q3中国手机出货报告'
        report = 'IDC发布2026年第三季度中国智能手机市场跟踪报告。'
        for result in ('华为以17.8%位列第二；苹果未纳入统计。',
                       '预计苹果以17.8%位列第二。', '去年苹果以17.8%位列第二。'):
            self.assertIsNone(source_market_measurement_frame(title, report, (report, result)))
        planned = report.replace('发布', '计划发布')
        self.assertIsNone(source_market_measurement_frame(title, planned, (planned, '苹果以17.8%位列第二。')))

    def test_versioned_speaker_and_tv_software_releases_keep_the_release_owner(self):
        pairs = (('22fbdf7de29c32f9a76cbcc9', '1750529a961bb252c5b0d200'),
                 ('ee353252f99a8984bcf8a69e', 'c40abe6326f2efbc23da78a5'))
        events, _ = self.cluster_sources(*(sid for pair in pairs for sid in pair))
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(pair) for pair in pairs})
        self.assertTrue(all(e.category == 'software_systems' for e in events))
        from apple_news_core.event_identity import is_os_release_announcement
        for title in ('Apple releases HomePod 3', 'HomePod 28.1 will be released next week',
                      'New speaker firmware released for tvOS 28.1', 'tvOS 28.1 adds a new control'):
            self.assertFalse(is_os_release_announcement(title), title)

    def test_reported_forecast_is_not_the_secondary_writers_opinion(self):
        for sid in ('3126354156e5b48c3908c355', '7a7d6344d6ef44c3dc6df85e'):
            events, _ = self.cluster_sources(sid)
            self.assertEqual([(e.relevance_tier, e.category) for e in events],
                             [('strong', 'hardware_products')], sid)
        for sid in ('7f02a968c36cec4a229cc724', '5f9810b07679f04d603129cf'):
            events, _ = self.cluster_sources(sid)
            self.assertTrue(all(e.relevance_tier == 'weak' for e in events), sid)
        from apple_news_core.event_identity import source_editorial_outlook
        body = 'A new report today revealed that Apple has booked a venue for Tuesday. This arrangement would make sense.'
        self.assertFalse(source_editorial_outlook('Apple could announce new devices Tuesday', body, (body,)))

    def test_attributed_launch_inventory_owns_category_without_borrowing_a_host(self):
        from apple_news_core.event_identity import source_launch_campaign_frame
        title = 'Apple could announce new products next week'
        body = 'Reporter Alex Han said that Apple could announce an iPad mini and a MacBook Pro next week.'
        frame = source_launch_campaign_frame(title, body, (body,))
        self.assertIsNotNone(frame)
        self.assertEqual(frame.category, 'hardware_products')
        for changed in ('Last year, ' + body, body.replace('Apple could', 'Samsung could'),
                        body.replace('an iPad mini and a MacBook Pro', 'software for iPad mini and MacBook Pro'),
                        'Alex Han said that Apple could announce software next week. The writer uses an iPad mini and a MacBook Pro.',
                        'Reporter Alex Han said that Apple announced an iPad mini and a MacBook Pro last year.',
                        'Reporter Alex Han said that Apple could announce a subscription for iPad mini and MacBook Pro owners next week.',
                        'Reporter Alex Han said that Apple could announce plans next week, while Samsung could launch rivals to the iPad mini and MacBook Pro.',
                        body.replace('could announce', 'did not announce')):
            self.assertIsNone(source_launch_campaign_frame(title, changed, (changed,)), changed)

    def test_hearing_feature_activation_and_plan_keep_their_stages(self):
        events, _ = self.cluster_sources('f9b975f1b1ede394232ed7d3', '640b7a78e5dd50861e8a03ca')
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_current_catalog_specs_join_the_launch_but_operating_conditions_stay_focused(self):
        specs = ('cdf91dbdbfe1528a108e26f7', 'f236dcd6270dfa504b2348f1',
                 'a626f18a114dd7216d838bc9', '555f72ec3ecef94cb4dbca4a')
        conditions = ('17de3c19f2a70e30aacc17d6', '10ab728c7ce450b9ba1195be')
        events, _ = self.cluster_sources(*specs, *conditions)
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(specs), frozenset(conditions)})
        self.assertTrue(all(e.category == 'hardware_products' and e.relevance_tier == 'strong' for e in events))

    def test_independent_charging_test_does_not_borrow_quoted_official_conditions(self):
        title = 'iPad mini fast charging test with a 35W adapter'
        body = ("Apple's specifications say the iPad mini supports fast charging. "
                'We tested an iPad mini with a 35W adapter and measured 41% charge after 30 minutes.')
        profile = self.m.source_text_profile(title, body, [], 'MacRumors')
        self.assertFalse(any('official-operating-conditions' in k for k in profile.event_keys))

    def test_same_named_carrier_plan_is_one_service_selection(self):
        events, _ = self.cluster_sources('b1f5077c6b1ca7f44fe96a3f', 'b2693b2f3bd43c5971412464')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')

    def test_reported_release_and_specs_do_not_fall_back_to_background_facets(self):
        for ids in (('511d2cb096f43dcf0806a341', '461096ed307280b8b65ee58c'),
                    ('afd6cefa51f0ccc30e1d5df8', '555f72ec3ecef94cb4dbca4a'),
                    ('369e116d0dacfb1f00790897', '98e5f807dda26e3b83200118')):
            with self.subTest(ids=ids):
                events, _ = self.cluster_sources(*ids)
                self.assertEqual(len(events), 1)
        events, _ = self.cluster_sources('b0faa8ae5a96ae53989e91ec', '4e5ac4de9e340d72a46581aa',
                                        'e86c7f43eeca4eee7ba7aaa8', 'fbaaa4aaeb558512552ffd0b')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')

    def test_factory_source_and_developed_supplier_statement_own_their_passages(self):
        compound = '9d002f5bec512306d762520c'
        peers = ('188839dc8af64fdced380019', '7ffa4f54eb2fad0287d80f29')
        events, _ = self.cluster_sources(compound, *peers)
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset((compound, *peers)), frozenset((compound,))})
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products' for e in events))
        articles = self.source_articles(compound)
        self.assertEqual(len(articles), 2)
        spans = [set(a.bound_claim.unit_ids) for a in articles]
        self.assertFalse(spans[0] & spans[1])

    def test_report_roles_keep_adjacent_negative_boundaries(self):
        from apple_news_core.event_identity import (source_service_fee_frame, source_platform_component_frame,
                                                   current_public_os_release, bind_manufacturing_reports)
        title = "Carrier's new plans include subscription choices"
        body = 'Carrier today announced “Example”. Carrier plans do not include Apple TV subscriptions.'
        self.assertIsNone(source_service_fee_frame(title, body, ()))
        for title in ('iOS 28.1 will fix 200 security vulnerabilities', 'iOS 28.1 Beta fixes 200 security vulnerabilities',
                      'iOS 28.1 fixes a WebKit vulnerability CVE-2026-12345'):
            self.assertIsNone(source_platform_component_frame(title, title, ()))
        for prefix in ('Previously, ', 'Last year, '):
            self.assertIsNone(current_public_os_release('Get ready to update your Apple Watch to watchOS 28.1',
                prefix + 'Apple has released a watchOS update, suggesting watchOS 28.1 focuses on fixes.'))
        from dataclasses import replace
        a, b = self.source_articles('9d002f5bec512306d762520c')
        evidence = a.evidence
        changed = replace(evidence, units=tuple(replace(u, text=u.text.replace('发布了题为', '没有发布题为')) for u in evidence.units))
        self.assertEqual(len(bind_manufacturing_reports(changed)), 1)
        statement_unit = next(u for u in evidence.units if '官方网站' in u.text)
        changed = replace(evidence, units=tuple(u for u in evidence.units if 'finemtech' not in u.text.lower() and not u.text.startswith('该公司')) + (statement_unit,))
        self.assertTrue(all(c.action != 'supplier-quality-statement' for c in bind_manufacturing_reports(changed)))

    def test_new_report_bindings_require_the_same_local_object(self):
        from apple_news_core.event_identity import (source_service_fee_frame, current_public_os_release,
            source_platform_component_frame, bind_manufacturing_reports)
        title = "Carrier's new plans include subscriptions"
        for prefix in ('Last year ', ''):
            body = 'Carrier today announced “NewPlan”. ' + prefix + 'Carrier bundled Apple TV subscriptions with “OldPlan”.'
            self.assertIsNone(source_service_fee_frame(title, body, ()))
        self.assertIsNone(current_public_os_release('Get ready to update your Apple Watch to watchOS 28.1',
            'Apple has released a watchOS update, watchOS 28.0, ahead of watchOS 28.1 next week.'))
        self.assertIsNone(source_platform_component_frame('iOS 28.1 fixes 200 security vulnerabilities',
            'Apple released iOS 28.0 with security fixes. iOS 28.1 has not been released.', ()))
        self.assertIsNone(current_public_os_release('Get ready to update your Apple Watch to watchOS 28.1',
            'Apple has released a watchOS update ahead of watchOS 28.1 next week.'))
        self.assertIsNone(source_platform_component_frame('iOS 28.1 fixes 200 security vulnerabilities',
            'iOS 28.1 remains in beta, while iOS 28.0 fixes 200 security vulnerabilities.', ()))
        body = 'Carrier today announced “NewPlan”. Carrier “NewPlan” drops Netflix, while “OldPlan” includes Apple TV subscriptions.'
        self.assertIsNone(source_service_fee_frame(title, body, ()))
        from dataclasses import replace
        a, b = self.source_articles('9d002f5bec512306d762520c')
        e = a.evidence
        text = ' '.join(u.text for u in e.units if u.kind == 'p')
        merged = replace(e, units=(replace(e.units[0], kind='p', text=text),))
        self.assertEqual(len(bind_manufacturing_reports(merged)), 2)
        changed = replace(e, units=tuple(replace(u, text=u.text.replace('记者从一名', '记者从参与iPhone 17生产的一名')
            .replace('这名富士康内部员工', '这名参与iPhone 17生产的富士康内部员工')
            .replace('iPhone Duo产线', 'iPhone 17产线')) for u in e.units))
        self.assertFalse(any(c.action == 'factory-source-report' for c in bind_manufacturing_reports(changed)))
        self.assertIn('富士康', a.bound_claim.subject)

    def test_media_fault_commentary_cannot_borrow_a_company_response(self):
        events, _ = self.cluster_sources('bb91f23712a8f33cab3255d9')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_current_permission_setting_does_not_inherit_historical_beta(self):
        ids = ('04512ec727da9fb7c7cbc991', 'b9d5cf590d7280de9cfe2235')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        for sid in ids:
            a, = self.source_articles(sid)
            keys = self.m.article_reconciliation_profile(a).event_keys
            self.assertTrue(any('final:app-motion-data' in k for k in keys), keys)
        from apple_news_core.event_identity import source_software_capability_frame
        title = 'iOS 28.1 Beta 3 新增限制运动数据功能'
        body = 'iOS 28.1 Beta 3 系统设置新增限制运动数据开关。应用将无法读取传感器数据。'
        frame = source_software_capability_frame(title, body, ())
        self.assertEqual(frame.subject, 'ios-28.1-beta-3:app-motion-data')
        for changed in ('去年' + body, body.replace('系统设置', '第三方应用设置'),
                        body.replace('28.1 Beta 3', '27.2 Beta 2'),
                        body.replace('系统设置新增', '计划在系统设置新增'),
                        '第三方应用在自己的隐私与安全页面新增限制运动数据开关。iOS系统没有改变。'):
            self.assertIsNone(source_software_capability_frame(title, changed, ()))

    def test_new_window_software_observation_and_translation_keep_their_object(self):
        events, _ = self.cluster_sources('34b8d434aa18673d129bcc55', 'b9ec4aa74ccdc850215abaf5')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        events, _ = self.cluster_sources('b62c6b14831163cc691c7c21')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        e = self.rows['b62c6b14831163cc691c7c21']['evidence']
        self.assertFalse(self.m.is_apple_executive_government_meeting_story(e['title'], ' '.join(u['text'] for u in e['units'])))
        article, = self.source_articles(e['article_id'])
        self.assertEqual(self.m.article_reconciliation_profile(article).bound_claim.action, 'software-behavior-report')

    def test_official_teaser_does_not_absorb_reported_product_schedule(self):
        ids = ('6a24c45df71da0c64d14f410', '48e8dcb83ee13087d1681d7f',
               'a9ec7c439fe84480a571e615', '7a06580618bc861c1f6296f3', '51d52e97995255eea77ed11d')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(ids[:-1]), frozenset(ids[-1:])})

    def test_official_accessory_is_the_release_object_not_its_host(self):
        ids = ('27397640600c9aea9a75817d', '22bdcd6d29407e65d7d19ed2', '3ffcc22b6c5e51d95f2392eb', '555f72ec3ecef94cb4dbca4a')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(ids[:-1]), frozenset(ids[-1:])})

    def test_release_body_features_do_not_replace_the_release_subject(self):
        ids = ('acd3085647ef22a248bd5442', '0225d74d477120d486c4fa64', 'd1c0a62d9491286c6c9c2753')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(ids[:2]), frozenset(ids[2:])})

    def test_attributed_actions_keep_speaker_time_and_observer_identity(self):
        from apple_news_core.event_identity import source_launch_campaign_frame, _observation_operator
        from apple_news_core.event_reconciler import _first_party_content_claim
        title = 'Apple Music announces a headliner for the Sunset Garden Festival'
        body = 'Apple Music announced last year that a singer will headline the Apple Music Sunset Garden Festival.'
        identity = self.m.build_event_identity(title, body, ())
        self.assertIsNone(_first_party_content_claim(title, body, identity))
        title = '苹果预告下周新品'
        body = '苹果高级副总裁今天出席了活动。某科技媒体今天发布了分析，并透露苹果新品可能下周亮相。'
        self.assertIsNone(source_launch_campaign_frame(title, body, (body,)))
        self.assertFalse(self.m.is_apple_executive_government_meeting_story(
            'Apple CEO Tim Cook meets Microsoft president Brad Smith',
            'Tim Cook met Microsoft president Brad Smith today to discuss software collaboration.'))
        self.assertEqual(_observation_operator("JerryRigEverything's "), _observation_operator('JerryRigEverything '))
        self.assertEqual(_observation_operator("Tom's Guide 于 10 月 25 日"), "tom's guide")

    def test_new_source_relations_do_not_borrow_background_or_future_actions(self):
        from apple_news_core.event_identity import source_retail_price_offer, source_device_behavior_test_frame, source_software_capability_frame
        self.assertTrue(source_retail_price_offer("MacBook Air falls to $999", ("Example Store is discounting Apple's MacBook Air, marked down to $999.",)))
        self.assertFalse(source_retail_price_offer("MacBook Air falls to $999", ("Apple is discounting MacBook Air, marked down to $999.",)))
        sid = 'fc8b55d051b44c0f9ddce6d7'
        e = self.rows[sid]['evidence']; ps = tuple(u['text'] for u in e['units'])
        for prefix in ('去年', '计划', '并未'):
            texts = tuple(p.replace('发布实验室测试博文', prefix + '发布实验室测试博文') for p in ps)
            self.assertIsNone(source_device_behavior_test_frame(e['title'], texts[0], texts))
        title = 'iOS 27.2 已有 Apple 智能占用'
        for body in ('在 iOS 27.2 系统中，计划出现 Apple智能的存储占用数据。',
                     '去年在 iOS 27.2 系统中，已经出现 Apple智能的存储占用数据。'):
            self.assertIsNone(source_software_capability_frame(title, body, ()))

    def test_service_performance_announcement_uses_show_not_performer_spelling(self):
        ids = ('86d26dd2e4c5eaa76e06d382', '275aa816e2ce37b0147666db', 'c937870edd69c8aaa950f594')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])

    def test_retail_offer_and_editorial_background_do_not_become_news(self):
        for sid in ('897972d8445082fef3e93499', '5f9810b07679f04d603129cf', '48cfab893ca8b6f6f89901ba'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_named_lab_comparison_retains_the_measured_device_result(self):
        events, _ = self.cluster_sources('fc8b55d051b44c0f9ddce6d7')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])

    def test_attributed_company_quote_joins_its_existing_statement(self):
        events, _ = self.cluster_sources('c654ea05e5c32c5ff038a172', 'b6366b4f8984c3839cedb3a8')
        self.assertEqual(len(events), 1)

    def test_company_response_does_not_absorb_store_order_or_factory_reports(self):
        official = ('b6366b4f8984c3839cedb3a8', 'a28a629ba296a3ef16bcb941', '34a5525120396ac098a22258', 'e578058f94a05b6d0e93e9dd')
        store = '47fb7d4648de0b0ea1a3f748'
        quality = '188839dc8af64fdced380019'
        orders = ('2c316bca81f816ef00c3b8c8', 'b19c9911e5e23828748964f3')
        ids = (*official, store, quality, *orders)
        expected = {frozenset(official), frozenset({store}), frozenset({quality}), frozenset(orders)}
        for order in (ids, ids[::-1]):
            with self.subTest(order=order):
                events, _ = self.cluster_sources(*order)
                self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events}, expected)
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_generic_response_does_not_create_a_legal_case(self):
        for key in ('b6366b4f8984c3839cedb3a8', '2c316bca81f816ef00c3b8c8'):
            for article in self.source_articles(key):
                profile = self.m.article_reconciliation_profile(article)
                self.assertFalse(any(k.startswith('apple-legal:') for k in profile.event_keys))
        article = article_for(self.m, 'Apple adds a new case color to its online store',
            'Apple introduced a new silicone case for iPhone. In other news, Apple responded to '
            'Epic Games in the App Store commission and anti-steering case.', 'MacRumors')
        profile = self.m.article_reconciliation_profile(article)
        self.assertFalse(any(k.startswith('apple-legal:') for k in profile.event_keys))

    def test_source_ownership_cannot_cross_another_app_or_service_actor(self):
        from apple_news_core.event_identity import source_software_capability_frame, source_device_operation_frame
        self.assertIsNone(source_software_capability_frame('iPhone 摇一摇广告有了限制开关',
            'iOS 27.2 Beta 2 上，微信在设置中新增限制运动数据的开关。', ()))
        body = '京东客服表示，iPhone Duo 不支持换机。苹果表示正在调查屏幕问题。'
        for prefix in ('', '用户联系了苹果客服，但没有得到答复。'):
            self.assertIsNone(source_device_operation_frame('iPhone Duo 屏幕故障客服回应：不支持换机',
                prefix + body, source_units=(prefix + body,)))

    def test_launch_specifications_share_current_device_introduction(self):
        ids = ('555f72ec3ecef94cb4dbca4a', '4f86a5f7663688b1ad884363',
               '8364e29f35180ec75996be5c',
               'b58e28ad6fb0ca125386672f', '45864ea4a6573332d48591a2', '63b86830e9b586d8b486dac0',
               'c9d86427cb567b662ba83664', '26fc5681fe6b452306697c72')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_device_debut_requires_a_current_introduction(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPad mini 10：芯片按存储容量配置'
        body = '苹果全新 iPad mini 10 正式登场，拥有三种存储配置。'
        self.assertEqual(source_device_operation_frame(title, body).action, 'device-announcement')
        for changed in ('去年，' + body, body.replace('正式登场', '将正式登场'),
                        body.replace('正式登场', '尚未正式登场'), body.replace('mini 10', 'mini 9')):
            self.assertIsNone(source_device_operation_frame(title, changed), changed)

    def test_new_device_official_sales_schedule_is_not_an_opening_or_revision(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPad mini 10 pre-orders and release date'
        body = ("Apple's all-new OLED iPad mini 10 will be available to pre-order starting on "
                'Wednesday, November 12, at 10:15 a.m. Pacific Time on apple.com and in the Apple Store app.')
        self.assertEqual(source_device_operation_frame(title, body).action, 'device-announcement')
        for changed in (body.replace('will be', 'may be'), body.replace('will be', 'will not be'),
                        body.replace('will be', 'is now'), body.replace('will be', 'was expected to be'),
                        body.replace('mini 10', 'mini 9'),
                        body.replace('on apple.com and in the Apple Store app', 'at a third-party retailer'),
                        body.replace('on apple.com and in the Apple Store app',
                                     'at a third-party retailer. Apple.com sells accessories'),
                        body.replace('on apple.com and in the Apple Store app',
                                     'at RetailCo, while accessories are available on apple.com and in the Apple Store app'),
                        body.replace('on apple.com and in the Apple Store app',
                                     'at RetailCo, not on apple.com or in the Apple Store app'),
                        body.replace("Apple's all-new", "Apple's existing")):
            self.assertIsNone(source_device_operation_frame(title, changed), changed)
        for changed in ('iPad mini 10 pre-orders delayed', 'iPad mini 10 pre-orders expand to a new region'):
            self.assertIsNone(source_device_operation_frame(changed, body), changed)

    def test_current_software_observations_survive_explanatory_titles(self):
        for key in ('b9ec4aa74ccdc850215abaf5', 'de56c3dd703827cf91320955', '10d440cd2e5e2788a9ee4828'):
            with self.subTest(key=key):
                events, _ = self.cluster_sources(key)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])

    def test_named_current_experiment_survives_headline_reader_reactions(self):
        events, _ = self.cluster_sources('e66e711b1e666ecff8400c58')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        claim = events[0].articles[0].bound_claim
        self.assertEqual(claim.object, 'kuba-klawiter:fold-endurance')
        self.assertTrue(any(q[2] == '75000:cycles' for q in claim.qualifiers))

    def test_named_observer_in_chinese_keeps_device_and_actual_test(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_attributed_device_tests
        original = self.source_articles('e66e711b1e666ecff8400c58')[0].evidence
        body = '数码博主 Orion Labs 近日对 iPhone 29 做了耐用折叠测试。'
        def evidence(text):
            return replace(original, title='iPhone 29 耐用性引发讨论', raw_lead=text,
                units=(replace(original.units[0], text=text),
                       replace(original.units[1], text='根据视频展示，前 75000 次折叠都没有明显问题。')))
        claim, = bind_attributed_device_tests(evidence(body))
        self.assertEqual(claim.object, 'orion-labs:fold-endurance')
        for changed in ('去年，' + body, body.replace('做了', '没有做'),
                        body.replace('近日对', '计划对'), body.replace('iPhone 29', 'iPhone 28')):
            self.assertFalse(bind_attributed_device_tests(evidence(changed)), changed)
        other, = bind_attributed_device_tests(evidence(body.replace('Orion Labs', 'Atlas Labs')))
        self.assertNotEqual(other.object, claim.object)

    def test_ordinary_app_feature_does_not_inherit_host_ownership(self):
        events, _ = self.cluster_sources('9ae78d20688ad9aebe3a6029')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_translated_native_observation_reuses_the_same_bound_operation(self):
        ids = ('10d440cd2e5e2788a9ee4828', '931fe5098ea61b3e98edd73d')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))
            self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))

    def test_translated_observation_requires_current_first_party_operation(self):
        from apple_news_core.event_identity import source_software_capability_frame
        title = '苹果 iOS 29.3 图片加入 TraceMark 隐藏水印'
        lead = '据科技媒体 Orion 报道，苹果已在 iOS 29.3 加入 TraceMark 功能。Apple 智能编辑的图片会带有隐藏式水印。'
        observed = '据该媒体实测，在“照片”App 中编辑的图像带有 TraceMark 水印。'
        frame = source_software_capability_frame(title, lead, (observed,))
        self.assertIsNotNone(frame)
        for changed in (observed.replace('实测', '计划实测'), observed.replace('实测', '没有实测'),
                        '去年，' + observed, observed.replace('在“照片”App', '在第三方编辑器中参考“照片”App'),
                        observed.replace('据该媒体实测', '网友猜测'),
                        observed.replace('中编辑的图像带有 TraceMark 水印', '中仅打开了一张图片，未检查水印'),
                        observed.replace('带有', '没有带有'),
                        observed.replace('带有', '预计明年会带有'),
                        observed.replace('中编辑的图像带有 TraceMark 水印',
                            '中仅打开了一张图片。谷歌工具生成的图像带有 TraceMark 水印'),
                        observed.replace('中编辑的图像带有 TraceMark 水印',
                            '中仅打开了一张图片，谷歌工具生成的图像带有 TraceMark 水印'),
                        observed.replace('中编辑', '的 iOS 28.2 测试环境中编辑')):
            self.assertIsNone(source_software_capability_frame(title, lead, (changed,)), changed)
        self.assertIsNone(source_software_capability_frame(title,
            lead.replace('Apple 智能编辑', '第三方应用编辑'), (observed,)))
        self.assertIsNone(source_software_capability_frame(title,
            lead.replace('科技媒体 Orion', '多家媒体'), (observed,)))

    def test_platform_adaptation_and_current_teaser_are_reports(self):
        for key, tier, category in (('48e8dcb83ee13087d1681d7f', 'strong', 'hardware_products'),
                                   ('8f5460c77bd16de402f87ed4', 'ecosystem', 'software_systems')):
            with self.subTest(key=key):
                events, _ = self.cluster_sources(key)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [(tier, category)])

    def test_individual_stable_platform_releases_remain_separate(self):
        events, _ = self.cluster_sources('62571d2b48080fd1370ccf70', 'bc3edee40e6a7bd2954174de')
        self.assertEqual(len(events), 2)

    def test_corroborated_article_heading_overrides_unrelated_social_title(self):
        from apple_news_core.article_processing import extract_title
        page = ('<meta property="og:title" content="New tablet cases no longer fit">'
                '<h1>My experience buying a phone</h1>'
                '<script type="application/ld+json">'
                '{"@type":"NewsArticle","headline":"My experience buying a phone"}</script>')
        self.assertEqual(extract_title(page, ''), 'My experience buying a phone')
        self.assertEqual(extract_title(page.replace('NewsArticle', 'VideoObject'), ''), 'New tablet cases no longer fit')
        changed = page.replace('New tablet cases no longer fit', 'My experience buying a phone — battery test results')
        self.assertEqual(extract_title(changed, ''), 'My experience buying a phone — battery test results')

    def test_software_observation_requires_current_operation_and_matching_topic(self):
        from apple_news_core.event_identity import source_software_capability_frame
        title = 'Apple Watch users report calendar display glitch'
        body = 'Some users running watchOS 31 are reporting a calendar display glitch. The Always-On display keeps showing yesterday instead of today.'
        self.assertEqual(source_software_capability_frame(title, body, ()).action, 'software-behavior-report')
        for changed in ('Last year, ' + body, body.replace('are reporting', 'plan to report'),
                        body.replace('are reporting', 'are not reporting'),
                        body.replace('watchOS 31', 'another app')):
            with self.subTest(body=changed):
                self.assertIsNone(source_software_capability_frame(title, changed, ()))
        self.assertIsNone(source_software_capability_frame('Apple Watch buying advice', body, ()))
        third_party = ('Some users running watchOS 31 are reporting a calendar display glitch '
                       'in the third-party CalendarPro app. Their watch shows the CalendarPro error '
                       'while its built-in clock remains correct. watchOS itself is unaffected.')
        self.assertIsNone(source_software_capability_frame(title, third_party, ()))
        self.assertIsNone(source_software_capability_frame(title, third_party
            + ' The Always-On display keeps showing the correct date and time.', ()))

    def test_current_specification_requires_device_owner_and_present_feature(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'New iPad Mini offers another storage option'
        body = "Apple's new iPad mini offers another storage option."
        self.assertEqual(source_device_operation_frame(title, body).action, 'device-announcement')
        for changed in (body.replace('offers', 'may offer'), body.replace('new', 'previous'),
                        body.replace('new iPad mini', 'new iPhone'), 'Last year, ' + body):
            with self.subTest(body=changed):
                self.assertIsNone(source_device_operation_frame(title, changed))
        self.assertIsNone(source_device_operation_frame('New iPad Mini users report permanent display lines',
            "Apple's new iPad mini features an OLED display. Owners are reporting permanent lines after normal use."))
        for headline in ('Apple removes nano-texture option from new iPad mini',
                         'New iPad mini loses nano-texture option'):
            self.assertIsNone(source_device_operation_frame(headline,
                "Apple's new iPad mini offers a nano-texture display. Apple has removed this option from its online store today."))

    def test_product_teaser_does_not_borrow_an_old_or_future_post(self):
        from apple_news_core.event_identity import source_launch_campaign_frame
        title = 'Apple teases a week of new products'
        body = 'Apple today teased a week of new products. Last week Apple invited press to an event.'
        self.assertEqual(source_launch_campaign_frame(title, body).action, 'official-launch-teaser')
        for changed in ('Last year Apple today teased a week of new products.',
                        'Apple plans to tease new products next week.',
                        'Apple did not today tease new products.',
                        'A blogger today teased a week of new products. Apple has not announced anything.'):
            self.assertIsNone(source_launch_campaign_frame(title, changed))
        self.assertIsNone(source_launch_campaign_frame(title, 'Alex Blue today teased a week of new products.',
            ('In 2020, Alex Blue, Apple’s SVP of Marketing, led its launches. He now runs an independent accessory business.',)))

    def test_runtime_conversion_requires_affirmed_capability(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        from apple_news_core.event_identity import bind_interoperability_report
        title = 'Helios 让外部游戏成为 iPhone 与 Mac 原生应用'
        body = '一个名为Helios的新开源项目，不能把Switch游戏转换为iPhone和iPad上的原生应用。原始代码无法直接运行在苹果芯片上。'
        evidence = capture_article_title_evidence('9to5Mac', 'https://example.org/runtime', title, body, ())
        self.assertIsNone(bind_interoperability_report(evidence))

    def test_third_party_response_cannot_borrow_company_background(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'Repair shop responds to iPhone Duo screen failures'
        body = 'A repair shop responded to customer complaints. Apple says affected devices can be replaced.'
        self.assertIsNone(source_device_operation_frame(title, body, (body,)))

    def test_teardown_anaphora_preserves_observer_and_differs_from_durability_test(self):
        ids = ('75e3586a9131c390f0974915', '1f5e4a0e7c1c34c368df4cde', '23282834804b0662aa04598d')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(ids[:2]), frozenset({ids[2]})})
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_current_support_security_and_regional_rollout_reports(self):
        for key, category in (('e773aa14c34af2593efcd24b', 'hardware_products'),
                              ('ae734ce03fdedd71234e7f37', 'software_systems'),
                              ('640b7a78e5dd50861e8a03ca', 'software_systems')):
            with self.subTest(key=key):
                events, _ = self.cluster_sources(key)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', category)])

    def test_future_platform_reference_cannot_bridge_stable_releases(self):
        m = self.m
        articles = [article_for(m, 'Apple releases iOS 31.2', 'Apple released iOS 31.2 final today.', '9to5Mac'),
                    article_for(m, 'Apple releases macOS 31.2', 'Apple released macOS 31.2 final today.', 'MacRumors'),
                    article_for(m, 'Apple Releases iOS 31.2 Ahead of macOS 31.2',
                                'Apple released iOS 31.2 today. macOS 31.2 will arrive next week.', 'AppleInsider')]
        for order in (articles, list(reversed(articles))):
            self.assertEqual(len(m.cluster_articles(order)), 2)
        articles[-1] = article_for(m, 'Apple Releases iOS 31.2, macOS 31.2 Coming Next Week',
            'Apple released iOS 31.2 today, and macOS 31.2 will arrive next week.', 'AppleInsider')
        self.assertEqual(len(m.cluster_articles(articles)), 2)
        articles[-1] = article_for(m, 'Apple Releases iOS 31.2, macOS 31.2 Coming Next Week',
            'Apple released iOS 31.2, and macOS 31.2 will arrive next week.', 'AppleInsider')
        self.assertEqual(len(m.cluster_articles(articles)), 2)
        articles.append(article_for(m, 'Apple releases iPadOS 31.2', 'Apple released iPadOS 31.2 today.', 'IT之家'))
        articles[-2] = article_for(m, 'Apple Releases iOS 31.2, iPadOS 31.2 and macOS 31.2',
            'Apple released iOS 31.2, iPadOS 31.2 and macOS 31.2 today.', 'AppleInsider')
        for order in (articles, list(reversed(articles))):
            self.assertEqual(len(m.cluster_articles(order)), 1)
        articles[-2] = article_for(m, 'iOS 31.2 and iPadOS 31.2 are now available',
            'Apple released iOS 31.2 and iPadOS 31.2 final today.', 'AppleInsider')
        self.assertEqual(len(m.cluster_articles(articles)), 2)

    def test_teardown_reference_cannot_cross_a_new_device_owner(self):
        from apple_news_core.event_identity import source_operation_frame, build_event_identity
        title = 'iPhone Duo拆解结论'
        body = 'iPhone Duo上市后引发讨论。iFixit今天拿到一台MacBook Pro，发布了该设备的完整拆解报告。'
        result = source_operation_frame(title, body, (), build_event_identity(title, body), source_units=(body,))
        self.assertTrue(result is None or result.action != 'device-teardown')


if __name__ == '__main__':
    unittest.main()
