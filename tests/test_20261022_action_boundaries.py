"""Current operations, attributed tests and neighboring context in mixed reports."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class ActionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261022_action_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 22, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_app_hands_on_keeps_completed_adaptation_software_owner(self):
        events, _ = self.cluster_sources(*self.ids('8d2aab'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'software_systems')])
        from apple_news_core.event_identity import source_app_adaptation_frame
        title = '实测 iPhone 23 山川应用适配版：体验如何？'
        frame = source_app_adaptation_frame(title, '山川应用终于适配iPhone 23！',
            ('山川应用正式推送了8.0.80版本的iPhone客户端更新。',))
        self.assertIsNotNone(frame)
        self.assertEqual(frame.subject, 'third-party-app:山川应用:iphone-23')
        for lead in ('山川应用计划终于适配iPhone 23。',
                     '山川应用终于决定将适配iPhone 23。',
                     '山川应用终于计划适配iPhone 23。',
                     '山川应用去年终于适配iPhone 23。',
                     '山川应用并未终于适配iPhone 23。',
                     '另一应用终于适配iPhone 23。',
                     '山川应用终于适配iPhone 24。'):
            self.assertIsNone(source_app_adaptation_frame(title, lead,
                ('山川应用发布客户端更新。',)), lead)

    def test_publisher_deductions_are_not_required_version_facts(self):
        events, output = self.cluster_sources(*self.ids('8d2aab'))
        public = '\n'.join(e['summary'] + '\n' + '\n'.join(
            e['key_facts'] + e.get('must_include_facts', [])) for e in output)
        article = self.source_articles(*self.ids('8d2aab'))[0]
        reviews = []
        self.m.add_source_remainder_reviews(events,
            {article.evidence.article_id: article.evidence}, reviews, {})
        for phrase in ('从我们实际体验到的界面表现来看', '爱范儿推测', '爱范儿也推测'):
            self.assertNotIn(phrase, public)
            self.assertIn(phrase, str(reviews))
        self.assertIn('8.0.80', public)
        self.assertIn('左右分栏显示', public)
        for phrase in ('示例媒体推测，这一版本采用了新的 SDK。',
                       '因此示例媒体也推测，下一版很快会上线。',
                       '从我们实际体验到的界面来看，这一版本显然基于新 SDK。',
                       '不过既然分栏已经出现，合理推断，下一版很快会上线。'):
            self.assertEqual(self.m.source_fact_statement_role(phrase, publisher='示例媒体'), 'editorial')
        for phrase in ('据分析师林川推测，新版本将在下月发布。',
                       '示例媒体称，分析师林川预计新版本将在下月发布。',
                       '据另一媒体报道，应用计划下月发布更新。',
                       '示例媒体实测发现，当前客户端支持左右分栏。'):
            self.assertNotEqual(self.m.source_fact_statement_role(phrase, publisher='示例媒体'), 'editorial')

    def test_publisher_turn_keeps_independent_fact_in_both_orders(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        fact = '苹果确认当前iPhone 23摄像头支持4K'
        for inference in ('示例媒体推测下一版会支持8K', '示例媒体推测，下一版会支持8K'):
            for text in (fact + '，但' + inference + '。', fact + '，' + inference + '。',
                         inference + '，但' + fact + '。'):
                article = article_for(self.m, 'iPhone 23摄像头当前录制支持', text, facts=[text])
                article.source = '示例媒体'
                article.evidence = capture_article_title_evidence(article.source, article.url,
                    article.title, text, (text,))
                view = self.m.prepare_source_fact_view(article)
                public = '\n'.join(f.text for f in (*view.normal, *view.structured))
                self.assertIn(fact, public, text)
                self.assertNotIn('8K', public, text)
                self.assertTrue(any(inference in f.text for f in view.unprocessed), text)

    def test_versioned_partial_app_adaptation_keeps_app_action(self):
        ids = self.ids('e8d8d', 'e23cbc', 'f76e1')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('weak', 'software_systems'))
            self.assertEqual(self.source_ids(events[0]), set(ids))
        from apple_news_core.event_identity import source_app_adaptation_frame
        title = '员工回应山川应用初步适配iPhone 23：后续将优化'
        text = '最新的山川应用8.0.80版本，已经初步适配了iPhone 23，后续体验还会优化。'
        frame = source_app_adaptation_frame(title, text)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.subject, 'third-party-app:山川应用:iphone-23')
        for other in (text.replace('已经初步', '计划初步'), text.replace('已经初步', '尚未'),
                      text.replace('iPhone 23', 'iPhone 24'), text.replace('山川应用', '另一应用')):
            self.assertIsNone(source_app_adaptation_frame(title, other), other)

    def test_observed_interface_alignment_owns_only_its_software_fact(self):
        article = self.source_articles(*self.ids('8d580'))[0]
        self.m.prepare_article_source(article)
        claim = article.bound_claim
        self.assertIsNotNone(claim)
        self.assertEqual(claim.action, 'software-behavior-report')
        units = {u.unit_id: u.text for u in article.evidence.units}
        text = '\n'.join(units[k][a:b] for k, a, b in claim.evidence_spans)
        self.assertIn('并没有对齐', text)
        for unrelated in ('TrueDepth', 'Duo 2', '强迫症'):
            self.assertNotIn(unrelated, text)
        events, _ = self.cluster_sources(*self.ids('8d580'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        from apple_news_core.event_identity import source_software_capability_frame, bind_device_capability_inventory
        title = 'iPhone 23指纹UI提示条与实体按键未对齐'
        body = '博主林川晒出的图片显示，iPhone 23指纹UI提示条与实体按键没有对齐。'
        for bad in (body.replace('iPhone 23', 'iPhone 24'), body.replace('图片显示', '概念图显示'),
                    body.replace('晒出的', '计划发布的'), body.replace('晒出的', '去年晒出的'),
                    body.replace('没有对齐', '已经对齐'),
                    body[:-1] + '的说法不实。',
                    '网友认为iPhone 23指纹UI提示条与实体按键没有对齐。',
                    '博主林川晒出的图片显示，iPhone 23旁边的Orion手机指纹UI提示条与实体按键没有对齐。',
                    '博主林川晒出的图片显示，iPhone 23已经对齐，但Orion手机指纹UI提示条与实体按键没有对齐。'):
            frame = source_software_capability_frame(title, bad, (bad,))
            self.assertTrue(frame is None or frame.action != 'software-behavior-report', bad)
        bound = bind_device_capability_inventory(self.evidence(title, body))
        self.assertIsNotNone(bound)

    def test_app_type_suffix_resolves_a_headline_shorthand(self):
        from apple_news_core.event_identity import source_app_adaptation_frame
        title = '山川宣布适配iPhone 23'
        for suffix in ('地图', '导航', '浏览器', '应用', '客户端', '软件'):
            text = '山川' + suffix + '全面适配iPhone 23，并支持横竖屏自动布局。'
            frame = source_app_adaptation_frame(title, text)
            self.assertIsNotNone(frame, suffix)
            self.assertEqual(frame.subject, 'third-party-app:山川' + suffix + ':iphone-23')
        for name in ('山川计划', '山川预计', '山川地图计划', '另一山川地图', '山川保护壳', '山川Pro', '另一应用'):
            self.assertIsNone(source_app_adaptation_frame(title,
                name + '适配iPhone 23，并更新软件界面。'), name)

    def test_named_reseller_activation_service_keeps_operator_and_software(self):
        events, _ = self.cluster_sources(*self.ids('8d6b9'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','software_systems')])
        from apple_news_core.event_identity import source_retail_program_frame
        title = '山川：旗下门店为iPhone 23受理eSIM现场办理'
        text = '苹果授权经销商山川宣布，旗下部分门店已支持受理eSIM现场办理。'
        frame = source_retail_program_frame(title, text)
        self.assertIsNotNone(frame)
        self.assertIn('山川', frame.subject)
        self.assertNotEqual(frame.subject, 'apple-store:esim-activation')
        for bad in (text.replace('山川', '山川科技'), text.replace('山川', '另一商家'),
                    text.replace('已支持', '计划支持'), text.replace('已支持', '去年已支持'),
                    text.replace('已支持', '尚未支持'), text.replace('旗下部分门店', '附近运营商门店'),
                    text[:-1] + '的消息不实。'):
            self.assertIsNone(source_retail_program_frame(title, bad), bad)

    def test_operator_activation_channel_is_not_an_app_update(self):
        ids = self.ids('e44c', '8d6b9')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertEqual({(e.relevance_tier, e.category) for e in events},
                             {('strong', 'software_systems')})
        from apple_news_core.event_identity import source_retail_program_frame
        title = '山川通信：现可通过App提前预约eSIM办理'
        body = '山川通信宣布，旗下自有营业厅现已全面支持iPhone 23的eSIM办理。'
        frame = source_retail_program_frame(title, body)
        self.assertIsNotNone(frame)
        self.assertIn('山川通信', frame.subject)
        for bad in (body.replace('山川通信', '另一运营商'),
                    body.replace('现已全面支持', '计划支持'),
                    body.replace('现已全面支持', '去年已支持'),
                    body.replace('现已全面支持', '尚未支持'),
                    body.replace('iPhone 23', 'Orion手机'),
                    body.replace('旗下自有营业厅', '附近其他营业厅'),
                    body[:-1] + '的消息不实。',
                    '山川通信宣布，旗下App新增地图功能。iPhone 23支持eSIM。'):
            self.assertIsNone(source_retail_program_frame(title, bad), bad)

    def test_preposed_app_type_owns_current_adaptation_release(self):
        events, _ = self.cluster_sources(*self.ids('92e2'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('weak', 'software_systems')])
        from apple_news_core.event_identity import source_app_adaptation_frame
        title = '山川 - iPhone 23体验'
        body = '作为首批适配iPhone 23的App，山川已经上架了第一个初步适配版本。'
        frame = source_app_adaptation_frame(title, body)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.subject, 'third-party-app:山川:iphone-23')
        for bad in (body.replace('山川', '山川科技'), body.replace('山川', '另一应用'),
                    body.replace('iPhone 23', 'iPhone 24'), body.replace('App', '保护壳'),
                    body.replace('已经上架', '计划上架'), body.replace('已经上架', '去年已经上架'),
                    body.replace('已经上架', '尚未上架'), body[:-1] + '的消息不实。',
                    body.replace('作为首批', '另一应用作为首批')):
            self.assertIsNone(source_app_adaptation_frame(title, bad), bad)
        self.assertIsNotNone(source_app_adaptation_frame('山川 - iOS 27',
            '作为适配iOS 27的App，山川已经上架了初步适配版本。'))
        self.assertIsNone(source_app_adaptation_frame('山川 - iOS 27',
            '作为适配iOS 28的App，山川已经上架了初步适配版本。'))

    def test_device_review_cannot_become_a_named_app_from_title_echo(self):
        events, _ = self.cluster_sources(*self.ids('c676'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'hardware_products')])
        from apple_news_core.event_identity import source_app_adaptation_frame
        for title in ('博主谈iPhone 23：1TB也有QLC 软件适配一般',
                      '观察者谈iPhone 23软件适配一般'):
            body = title + '。今日，博主分享手机使用感受，认为软件适配一般。'
            self.assertIsNone(source_app_adaptation_frame(title, body))
        title = '山川应用率先适配iPhone 23'
        self.assertIsNotNone(source_app_adaptation_frame(title,
            title + '。山川应用已完成iPhone 23适配，并更新软件界面。'))
        for body in ('山川应用计划适配iPhone 23，并更新软件界面。',
                     '山川应用预计适配iPhone 23，并更新软件界面。',
                     '山川应用尚未适配iPhone 23，正在修改软件界面。'):
            self.assertIsNone(source_app_adaptation_frame(title, title + '。' + body))

    def test_current_opening_keeps_executive_restatement_with_same_sale(self):
        ids = self.ids('cd8d', 'ecb209')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_broadcast_audio_wording_does_not_absorb_whole_race_program(self):
        ids = self.ids('f7fb', '3c506', '6d9e')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order, *self.ids('582e'))
            self.assertEqual(len(events), 2)
            self.assertIn(set(ids), [self.source_ids(e) for e in events])

    def test_sales_opening_keeps_current_date_model_and_region(self):
        from apple_news_core.event_identity import source_retail_operation_frame
        title = 'iPhone Duo 今日开售'
        first = source_retail_operation_frame(title, 'iPhone Duo 于 10 月 23 日正式开售。')
        self.assertIsNotNone(first)
        self.assertEqual((first.action, first.period), ('retail-sales-opening', '10-23'))
        for lead in ('iPhone Duo 去年于 10 月 23 日开售。',
                     'iPhone Duo 将于 10 月 23 日开售。',
                     'iPhone Duo 并未于 10 月 23 日开售。',
                     'iPhone Air 于 10 月 23 日开售。',
                     '10月16日开启预购后，iPhone Duo 今天正式开售。',
                     'iPhone Duo 于10月23日开售的说法不实。',
                     '10月23日消息，iPhone Duo 去年开售。'):
            frame = source_retail_operation_frame(title, lead)
            self.assertTrue(frame is None or frame.action != 'retail-sales-opening', lead)
        later = source_retail_operation_frame(title, 'iPhone Duo 于 10 月 30 日正式开售。')
        self.assertNotEqual(first.period, later.period)
        regional = source_retail_operation_frame(title, '在日本，iPhone Duo 于 10 月 23 日正式开售。')
        self.assertEqual(regional.region, 'japan')

    def test_broadcast_audio_keeps_its_own_rollout_predicate(self):
        from apple_news_core.event_identity import source_current_report_frame
        title = 'F1 on Apple TV with Dolby Atmos'
        for lead in (
            'Dolby Atmos may come to F1 on Apple TV.',
            'Dolby Atmos will not come to F1 on Apple TV.',
            'Last year Dolby Atmos came to F1 on Apple TV.',
            'Apple TV announces Dolby Vision for F1; Dolby Atmos is not available.',
            'Netflix adds Dolby Atmos for F1, while Apple TV supports standard stereo.',
            'F1 on Apple TV uses stereo compared with Netflix getting Dolby Atmos.',
            'Apple TV adds Dolby Atmos for F1, but the company denies this announcement.',
        ):
            frame = source_current_report_frame(title, lead, ())
            self.assertTrue(frame is None or frame.action != 'broadcast-audio-rollout', lead)

    def test_supply_constraint_keeps_current_product_and_channel_owner(self):
        events, _ = self.cluster_sources(*self.ids('efecc'))
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        title = 'MacBook Air faces a major shortage'
        for lead in (
            'Galaxy phones are out of stock; Orion Store says delivery will take four weeks.',
            'Apple Store sells MacBook Air. Orion Store has a shortage and delivery delays.',
            'Apple Store shows iPad delivery delays of six weeks.',
            'Apple Store says MacBook Air does not face a shortage or shipping delays.',
            'Last year, Apple Store reported MacBook Air shipping delays of six weeks.',
            'Orion Store reports MacBook Air cases are out of stock with shipping delays of four weeks.',
            'Apple Store reports Galaxy S27 shipping delays of six weeks.',
        ):
            self.assertFalse(self.m.is_title_led_apple_product_supply_constraint_story(title, lead), lead)
        self.assertFalse(self.m.is_title_led_apple_product_supply_constraint_story(
            'iPhone 23 faces a shortage', 'Apple Store reports iPhone 24 shipping delays of six weeks.'))
        self.assertTrue(self.m.is_title_led_apple_product_supply_constraint_story(
            'iPhone 23 faces a shortage', 'Apple Store reports iPhone 23 shipping delays of six weeks.'))
        for lead in ('苹果官网部分机型预计要到 8 月下旬发货。',
                     '苹果官网部分机型预计要到8月下旬发货。',
                     '苹果官网部分配置需等待三至四周。'):
            self.assertTrue(self.m.is_title_led_apple_product_supply_constraint_story(
                '苹果 MacBook Air 出现供应紧张', lead), lead)

    def test_current_pc_report_keeps_local_apple_results_and_period(self):
        ids = self.ids('1053', '9756')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_market_value_roles_follow_relation_not_number_order(self):
        title = 'Apple PC market share rises in Q3 2026'
        leads = (
            'Counterpoint reports Apple worldwide PC market share rose from 8.7% to 9.8% in Q3 2026.',
            'Counterpoint reports Apple worldwide PC market share reached 9.8% up from 8.7% in Q3 2026.',
            'Counterpoint报告2026年第三季度全球PC市场苹果份额升至9.8%，此前为8.7%。',
        )
        for lead in leads[1:]:
            with self.subTest(lead=lead):
                a = article_for(self.m, title, leads[0])
                b = article_for(self.m, title, lead, source='MacRumors')
                for pair in ([a, b], [b, a]):
                    self.assertEqual(len(self.m.cluster_articles(pair)), 1)

    def test_market_percentage_points_keep_target_share_not_change_as_previous(self):
        for unit in ('percentage points', 'points', '个百分点'):
            with self.subTest(unit=unit):
                title = 'Apple PC market share rises in Q3 2026'
                lead = ('Counterpoint报告2026年第三季度全球PC市场苹果份额上升1.1个百分点至9.8%。'
                    if unit == '个百分点' else
                    'Counterpoint reports Apple worldwide PC market share rose 1.1 ' + unit + ' to 9.8% in Q3 2026.')
                a = article_for(self.m, title, lead)
                profile = self.m.article_reconciliation_profile(a)
                self.assertIn('market-result-measure:share-current:9.8', profile.separation_keys)
                self.assertFalse(any('share-previous:' in k for k in profile.separation_keys))
                b = article_for(self.m, title, lead.replace('9.8%', '8.7%'), source='MacRumors')
                for pair in ([a, b], [b, a]):
                    self.assertEqual(len(self.m.cluster_articles(pair)), 2)

    def test_market_threshold_continues_to_its_actual_result(self):
        title = 'Apple global smartphone market share in Q2 2026'
        for lead in (
            'Counterpoint reports Apple global smartphone market share crossed 20%, reaching 22% in Q2 2026.',
            'Counterpoint报告2026年第二季度苹果全球智能手机市场份额突破20%，达到22%。',
        ):
            with self.subTest(lead=lead):
                a = article_for(self.m, title, lead)
                profile = self.m.article_reconciliation_profile(a)
                self.assertIn('market-result-measure:share-current:22', profile.separation_keys)
                self.assertNotIn('market-result-measure:share-current:20', profile.separation_keys)
                b = article_for(self.m, title,
                    'Counterpoint reports Apple global smartphone market share reached 23% in Q2 2026.', source='MacRumors')
                for pair in ([a, b], [b, a]):
                    self.assertEqual(len(self.m.cluster_articles(pair)), 2)

    def test_market_result_period_is_not_its_comparison_period(self):
        title = 'Counterpoint worldwide PC shipment report'
        for lead in (
            'Compared with Q3 2025, Apple worldwide PC shipments fell 11% in Q3 2026, according to Counterpoint.',
            'Compared with the third quarter of 2025, Apple worldwide PC shipments fell 11% in the third quarter of 2026, according to Counterpoint.',
        ):
            with self.subTest(lead=lead):
                profile = self.m.article_reconciliation_profile(article_for(self.m, title, lead))
                self.assertIn('source-report-year:2026', profile.separation_keys)
                self.assertFalse(any(':2025-q3:' in k for k in profile.event_keys))
                self.assertTrue(any(':2026-q3:' in k for k in profile.event_keys))

    def test_apple_request_does_not_borrow_vendor_or_contrast_words(self):
        events, _ = self.cluster_sources(*self.ids('dcad'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        title = '苹果向显示厂商发出信息请求'
        lead = '苹果向显示厂商发出面板信息请求。OLED对比度更高，苹果将评估后续型号。'
        self.assertFalse(self.m.is_multi_vendor_chip_or_phone_roadmap_background_story(title, lead))

    def test_named_app_aliases_do_not_borrow_store_accessory_context(self):
        ids = self.ids('73edef', '06500')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual((events[0].relevance_tier, events[0].category),
                             ('weak', 'software_systems'))

    def test_store_accessory_action_requires_its_own_physical_object(self):
        for text in (
            'Orbit app adds a calendar. Fold iPhone into a stand. Download at https://apps.apple.com/app/orbit.',
            '应用新增桌面日历；把手机折成支架。下载地址 https://apps.apple.com/app/orbit。',
            'Apple Store sells cases. Orbit app is now available with a stand mode.',
            'Apple Store has not launched a new charging stand.',
            'Apple Store now sells iPhone, while Orion launched a charging stand.',
            'The claim that Apple Store has launched a charging stand is false.',
        ):
            self.assertFalse(self.m.is_official_apple_accessory_market_story(text), text)
        for text in (
            "Apple's online store now sells a new charging stand for iPhone.",
            '苹果官网上架新的充电支架，适用于 iPhone。',
            "Apple's charging cable is no longer available from Apple Store online.",
        ):
            self.assertTrue(self.m.is_official_apple_accessory_market_story(text), text)

    def test_mixed_app_release_preserves_name_version_owner_and_stage(self):
        from apple_news_core.event_identity import source_named_app_frame
        title = '星轨·Orbit Notes推出iPhone版本'
        lead = '效率应用“星轨·Orbit Notes”刚刚正式推出支持iPhone的5.4版。'
        frame = source_named_app_frame(title, lead)
        self.assertIsNotNone(frame)
        self.assertEqual((frame.tier, frame.category), ('weak', 'software_systems'))
        self.assertEqual(source_named_app_frame(title,
            '苹果旗下应用星轨·Orbit Notes正式更新5.4版本。').tier, 'strong')
        for other in ('去年' + lead, lead.replace('刚刚正式推出', '计划推出'),
                      lead.replace('刚刚正式推出', '没有推出'),
                      lead.replace('Orbit Notes', 'Orbit Maps'),
                      lead.replace('星轨', '新星轨')):
            self.assertIsNone(source_named_app_frame(title, other), other)

    def test_channel_discount_and_personal_regret_are_source_forms(self):
        for sid in self.ids('c87d2', '8c634', '381a'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_channel_price_header_cannot_borrow_other_actions(self):
        from apple_news_core.event_identity import source_retail_price_offer
        title = 'iPhone 23 免税价公布，比官网便宜200元'
        for body in ('免税店公布的价格如下：', '与官网同步公布的还有免税渠道的价格：',
                     'iPhone 23的免税渠道价格如下：'):
            self.assertTrue(source_retail_price_offer(title, (body,)))
        for headline, body in (
            ('苹果调整iPhone 23官方售价，比官网便宜200元',
             '苹果公布了iPhone 23新价格。零售商公布了Galaxy S27售价。'),
            (title, '零售商公布了Galaxy S27售价。'),
            (title, 'Galaxy S27的免税渠道价格如下：'),
            (title, '以下为Galaxy S27在免税店的价格：'),
            (title, 'iPhone 23 Pro的免税渠道价格如下：'),
            (title, 'iPhone 23保护壳的免税渠道价格如下：'),
            (title, '零售商没有公布iPhone 23售价。'),
            (title, '零售商预计将公布iPhone 23售价。'),
            (title, '预计免税店将公布的价格如下：'),
            (title, '去年免税店公布的价格如下：'),
            (title + '的消息不实', '免税店公布的价格如下：'),
        ):
            self.assertFalse(source_retail_price_offer(headline, (body,)), (headline, body))

    def test_discount_and_regret_do_not_downgrade_distinct_actions(self):
        from apple_news_core.event_identity import build_event_identity, is_personal_product_complaint
        for title, lead in (
            ('苹果印度制造 iPhone 成本下降', '印度对关键零部件免税，苹果制造成本比此前便宜。'),
            ('苹果公布 iPhone 新定价', '苹果官网公布 iPhone 售价，比上代便宜 200 元。'),
            ('苹果公布300元维修服务', '苹果公布了300元维修服务。零售商另有优惠券。'),
            ('苹果公布300元维修服务', '苹果公布了300元维修服务。零售商另有优惠券，充电器到手20元。'),
        ):
            self.assertNotEqual(build_event_identity(title, lead).content_form, 'deal')
        for title, lead in (
            ('博主实测 iPhone 续航', '博主在统一亮度下实测 iPhone，续航达到 20 小时。'),
            ('iPhone 屏幕出现闪烁', '博主表示 iPhone 在低亮度下每次解锁都会闪烁。'),
            ('苹果退货政策更新', '苹果修改退货政策；一位博主表示后悔买了手机。'),
        ):
            self.assertFalse(is_personal_product_complaint(title, lead))

    def test_official_case_pairing_uses_same_object_despite_title_shorthand(self):
        ids = self.ids('6d3cb', '2dab')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
        from apple_news_core.event_identity import source_official_accessory_conditions
        title = 'iPhone 23官方壳贴膜后盖不上'
        for owner in ('Orion', 'Orion ', '山川'):
            self.assertIsNone(source_official_accessory_conditions(title,
                owner + '官方保护壳，无法搭配贝尔金钢化膜一起使用。'))

    def test_case_compatibility_cannot_bind_phone_construction(self):
        from apple_news_core.event_identity import bind_accessory_construction
        sid = self.ids('6d3cb')[0]
        articles = self.source_articles(sid)
        self.assertTrue(articles)
        self.assertTrue(all(a.bound_claim is None or a.bound_claim.action != 'accessory-construction-report'
                            for a in articles))
        events, _ = self.cluster_sources(sid)
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        self.assertIn('前盖', ' '.join(f for a in articles for f in a.key_facts))
        title = "Apple's official iPhone 23 case update"
        for paragraph in (
            'The iPhone 23 uses a polished titanium frame. Apple sells an official case.',
            'Apple sells an official case. The phone uses adhesive for its battery.',
            'Orion case uses adhesive to hold its cover.',
            'Orion released a case. The case uses adhesive to hold its cover.',
        ):
            self.assertIsNone(bind_accessory_construction(self.evidence(title, paragraph)))
        self.assertIsNone(bind_accessory_construction(self.evidence(title,
            'Orion released a case.', 'The case uses adhesive to hold its cover.')))
        self.assertIsNone(bind_accessory_construction(self.evidence(title,
            'Apple designed two cases for iPhone 23: a silicone case, and a folio case. '
            'This concern is about the former. Orion released a case.',
            'The case uses adhesive to hold its cover.')))

    def test_case_pairing_keeps_counterpart_and_assertion_status(self):
        from apple_news_core.event_identity import source_official_accessory_conditions as frame
        title = '苹果 iPhone 23 官方保护壳适配问题'
        lead = '苹果官方保护壳无法和Acme钢化膜匹配，前盖盖不上。'
        first = frame(title, lead)
        self.assertIsNotNone(first)
        self.assertNotEqual(first.subject, frame(title, lead.replace('Acme', 'Bravo')).subject)
        self.assertNotEqual(frame(title, lead.replace('Acme', '贝尔金')).subject,
                            frame(title, lead.replace('Acme', '倍思')).subject)
        for text in ('去年' + lead, '苹果否认' + lead, lead + '此消息不实。',
                     lead.replace('苹果官方保护壳', '第三方保护壳')):
            self.assertIsNone(frame(title, text), text)
        self.assertIsNone(frame("Apple's official iPhone 23 case update",
            "Apple's official iPhone 24 case cannot fit with a glass screen protector."))

    def test_same_report_roadmap_keeps_component_and_generation(self):
        prototypes = set(self.ids('1baec', '3f644', '8cab', 'f157', 'f13c', '2dc21'))
        displays = set(self.ids('4b459', '1653', 'f53f'))
        ids = sorted(prototypes | displays)
        for order in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*order)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                             {frozenset(prototypes), frozenset(displays)})

    def test_project_approval_keeps_its_model_stage_and_denial(self):
        from apple_news_core.event_reconciler import hardware_roadmap_primary_claim
        title = 'iPhone Duo 2 gets green light'
        def claim(h, lead):
            return hardware_roadmap_primary_claim(h, lead)
        current = 'Apple gave iPhone Duo 2 the green light.'
        positive = claim(title, current)
        self.assertIsNotNone(positive)
        self.assertEqual(positive, claim(title, current.rstrip('.') + ' but has not approved the iPhone Air 3.'))
        self.assertNotEqual(positive, claim(title, 'Last year, ' + current))
        self.assertNotEqual(positive, claim(title + '? Apple denies approval', current))
        self.assertIsNone(claim('iPhone Ultra 2 gets green light for development',
            "Last year, Apple's second-generation foldable iPhone was given the go-ahead."))

    def test_largest_iphone_display_requires_a_display_object(self):
        from apple_news_core.event_identity import build_event_identity
        for title in ('弥补最大遗憾！iPhone Duo 2原型机曝光：测试屏下Face ID',
                      '最大的变化：iPhone Duo 2原型机开始测试'):
            self.assertNotIn('largest-iphone-display', build_event_identity(title, '').components)
        for title in ('苹果正在测试最大屏幕的 iPhone', 'iPhone 将采用史上最大屏幕'):
            self.assertIn('largest-iphone-display', build_event_identity(title, '').components)

    def test_roadmap_generation_is_an_owned_bound_not_a_join_key(self):
        from apple_news_core.event_identity import foldable_iphone_generation_subject as generation
        from apple_news_core.event_matcher import profile_pair_decision
        for title, expected in (
            ('The first foldable iPhone will use an advanced hinge', 'g1'),
            ('第二代 iPhone Duo 原型机配备面容 ID', 'g2'),
            ('iPhone Duo 3 prototypes include Face ID', 'g3'),
            ('Third-generation AirPods tested alongside iPhone Duo', ''),
        ):
            self.assertEqual(generation(title), 'foldable-iphone' + ('-' + expected if expected else ''))
        def profile(title):
            return self.m.article_reconciliation_profile(article_for(self.m, title, title))
        second = profile('iPhone Duo 2 prototypes include Face ID')
        third = profile('iPhone Duo 3 prototypes include Face ID')
        generic = profile('iPhone Duo prototypes include Face ID')
        self.assertEqual(profile_pair_decision(second, third), 'conflict')
        self.assertEqual(profile_pair_decision(second, generic), 'match')
        for title in ('iPhone Duo 2 prototypes include OLED displays',
                      'Apple launches iPhone Duo 2 with Face ID',
                      'Apple cancelled iPhone Duo 2 prototypes with Face ID'):
            self.assertNotEqual(profile_pair_decision(second, profile(title)), 'match', title)
        self.assertFalse(any('generation' in key for key in second.event_keys))

    def test_roadmap_opening_uses_complete_repeated_deck_only(self):
        from apple_news_core.event_reconciler import _short_lead_scope, hardware_roadmap_primary_claim
        opening = 'A report from Example Research says Apple plans a larger inner display for iPhone Duo.'
        teaser = 'A report from Example Research says... '
        self.assertEqual(_short_lead_scope(teaser + opening, sentences=1), opening.lower())
        unrelated = 'Another report describes a larger iPhone Duo display.'
        self.assertNotIn('larger', _short_lead_scope(teaser + unrelated, sentences=1))
        different_claims = ('Mark Gurman says Apple is not testing Face ID... '
                            'Mark Gurman says Apple is planning a larger display.')
        self.assertIn('not testing', _short_lead_scope(different_claims, sentences=1))
        for title in ('Apple launches iPhone Duo with a larger display',
                      'Apple cancelled its plans for a larger iPhone Duo display'):
            result = hardware_roadmap_primary_claim(title, opening)
            self.assertTrue(result is None or result[1] != 'display-enlargement-planning')

    def test_roadmap_predicate_cannot_borrow_a_different_owner_or_denial(self):
        from apple_news_core.event_reconciler import hardware_roadmap_primary_claim as claim
        title = 'iPhone Duo 2 prototypes include Face ID'
        for lead in ('Mark Gurman denies that iPhone Duo 2 prototypes include Face ID.',
                     'Last year Apple tested iPhone Duo 2 prototypes with Face ID.'):
            result = claim(title, lead)
            self.assertTrue(result is None or not result[1].startswith('component-development'), lead)
        self.assertIsNone(claim('iPhone Duo 2 comparison: Orion prototypes include Face ID',
                                'Orion prototypes include Face ID.'))
        self.assertIsNone(claim('Apple considers a future iPhone Duo',
                                'Orion plans a larger screen for its next phone.'))
        self.assertIsNone(claim('Apple considers a larger iPhone Duo',
                                'Apple does not plan a larger iPhone Duo display.'))
        self.assertIsNone(claim('iPhone Duo comparison: Orion plans a larger display',
                                'Orion plans a larger display.'))
        self.assertIsNone(claim('Apple considers a future iPhone Duo',
                                'Apple says Orion plans a larger iPhone Duo display.'))

    def test_named_app_feature_reports_keep_software_ownership(self):
        for prefix in ('007edf', 'f76e1'):
            events, _ = self.cluster_sources(*self.ids(prefix))
            self.assertEqual([(e.relevance_tier, e.category) for e in events],
                             [('weak', 'software_systems')], prefix)
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform as owns
        title = 'Orion starts testing scheduled messages on iPhone'
        lead = 'Orion is finally making its messaging features available to select iPhone beta testers.'
        self.assertTrue(owns(title, lead, named_only=True))
        for other in ('If ' + lead, 'Last year, ' + lead,
                      lead.replace('Orion', 'NewOrion'), lead.replace('iPhone', 'Android'),
                      lead.replace('is finally making', 'is not making')):
            self.assertFalse(owns(title, other, named_only=True), other)
        self.assertFalse(owns(title.replace('Orion', 'Apple'), lead.replace('Orion', 'Apple'), named_only=True))
        self.assertFalse(owns(title, 'Orion is making announcements, while Atlas makes its app features available to select iPhone beta testers.', named_only=True))

    def test_current_preorder_result_keeps_its_subject_and_stage(self):
        from apple_news_core.event_identity import source_retail_operation_frame as resolve
        title = 'iPhone 23预订量超过预期'
        lead = 'iPhone 23在多个主要市场获得的预订量超过了公司原先预期。'
        frame = resolve(title, lead)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.action, 'reported-preorder-demand')
        for other in ('去年' + lead, '预计' + lead, '如果' + lead,
                      lead.replace('iPhone 23', 'iPhone 24'),
                      lead.replace('超过了', '没有超过'),
                      'iPhone 23已经开售，Orion手机预订量超过预期。'):
            result = resolve(title, other)
            self.assertTrue(result is None or result.action != frame.action, other)
        events, _ = self.cluster_sources(*self.ids('1e03', '78b381'))
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_charging_stand_owns_hardware_not_compatibility_software(self):
        from apple_news_core.event_identity import source_accessory_category
        self.assertEqual(source_accessory_category('Orion充电支架支持苹果认证'), 'hardware_products')
        self.assertEqual(source_accessory_category('Orion charging stand with configuration software'), 'hardware_products')
        self.assertEqual(source_accessory_category('Orion charging stand firmware update'), 'software_systems')
        events, _ = self.cluster_sources(*self.ids('6540'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'hardware_products')])

    def test_explanation_and_screen_modification_are_not_one_teardown(self):
        events, _ = self.cluster_sources(*self.ids('4e161', 'a6f07'))
        self.assertEqual(len(events), 2)
        for event in events:
            source_ids = self.source_ids(event)
            self.assertEqual(event.relevance_tier,
                             'weak' if self.ids('a6f07')[0] in source_ids else 'strong')
            for article in event.articles:
                self.assertNotIn('device-teardown', str(self.m.article_reconciliation_profile(article).event_keys))
        title = 'iPhone 23 cooling system exposed in teardown'
        lead = 'Repair firm Orion took apart the iPhone 23 and measured its thermal design.'
        profile = self.m.article_reconciliation_profile(article_for(self.m, title, lead))
        self.assertIn('device-teardown', str(profile.event_keys))
        for other in ('Last year, ' + lead, lead.replace('iPhone 23', 'iPhone 24'),
                      lead.replace('iPhone 23', 'iPhone 23 Pro'), lead.replace('iPhone 23', 'iPhone 23 case'),
                      lead.replace('took apart', 'did not take apart')):
            profile = self.m.article_reconciliation_profile(article_for(self.m, title, other))
            self.assertNotIn('device-teardown', str(profile.event_keys), other)
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPhone 23保护层可以徒手撕下'
        lead = '视频中，博主徒手撕下了iPhone 23的保护层。'
        self.assertEqual(source_device_operation_frame(title, lead).tier, 'weak')
        for other in ('去年' + lead, lead.replace('撕下了', '没有撕下'),
                      lead.replace('iPhone 23', 'iPhone 24')):
            self.assertIsNone(source_device_operation_frame(title, other), other)
        for other in ('iPhone 23', 'Galaxy S27'):
            profile = self.m.article_reconciliation_profile(article_for(self.m,
                'AirPods 5 teardown shows a replaceable battery',
                "AirPods 5 have replaceable batteries. Here's how " + other + " fared in its latest teardown."))
            self.assertNotIn('device-teardown', str(profile.event_keys))

    def test_typed_app_release_does_not_borrow_its_host_device(self):
        from apple_news_core.event_identity import source_named_app_frame
        title = '复古游戏模拟器 Orion 3.0 上线：iPhone 23变身游戏机'
        lead = '报道称复古游戏模拟器 Orion 更新至 3.0 版本，支持iPhone 23。'
        self.assertEqual(source_named_app_frame(title, lead).tier, 'weak')
        first_party = source_named_app_frame('苹果软件 Orion 3.0 上线：支持iPhone 23',
                                            '苹果旗下软件 Orion 更新至 3.0 版本。')
        self.assertEqual((first_party.tier, first_party.kind), ('strong', 'os_app'))
        self.assertTrue(first_party.subject.startswith('apple-app:'))
        for other in ('去年' + lead, lead.replace('更新至', '没有更新至'),
                      lead.replace('Orion', 'NewOrion'), lead.replace('3.0', '4.0')):
            self.assertIsNone(source_named_app_frame(title, other), other)
        events, _ = self.cluster_sources(*self.ids('d5c521'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'software_systems')])

    def test_reported_technical_explanation_keeps_its_speaker(self):
        title = 'Orion分析iPhone 23发烫原因：散热结构受限'
        lead = 'Orion官方发布技术分析文章，解释了iPhone 23发烫的原因。'
        def profile(text):
            return self.m.article_reconciliation_profile(article_for(self.m, title, text))
        self.assertIn('attributed-engineering-explanation', str(profile(lead).event_keys))
        for other in ('去年' + lead, lead.replace('Orion', 'NewOrion'),
                      lead.replace('iPhone 23', 'iPhone 24'), lead.replace('发布', '没有发布'),
                      lead.replace('，解释', '，Atlas解释'),
                      'Orion官方发布技术分析文章，解释了Galaxy的散热结构，文中同时提到iPhone 23。'):
            self.assertNotIn('attributed-engineering-explanation', str(profile(other).event_keys), other)

    def test_market_comparison_keeps_the_measured_owner_and_metric(self):
        from apple_news_core.event_identity import source_market_statements
        text = '苹果的iPhone 23 Pro系列开局强劲，首发销量比iPhone 22 Pro系列同比增长近20%。'
        statements = list(source_market_statements(text))
        self.assertTrue(any('首发销量比' in owned and role == 'observed'
                            for _, owned, role in statements))
        self.assertFalse(list(source_market_statements(
            '三星首发销量比iPhone 22 Pro系列同比增长近20%。')))
        self.assertFalse(any(role == 'observed' and '20%' in owned for _, owned, role
            in source_market_statements('去年苹果开局强劲，首发销量同比增长20%。')))
        self.assertFalse(any('20%' in owned for _, owned, _ in source_market_statements(
            '苹果开局强劲，首发销量由三星领跑并同比增长20%。')))
        events, output = self.cluster_sources(*self.ids('80b560'))
        self.assertTrue(any(e.relevance_tier == 'strong' for e in events))
        public = str(output)
        self.assertIn('首发销量', public)
        self.assertIn('iPhone 17 Pro', public)
        self.assertIn('近 20%', public)

    def test_store_demo_configuration_does_not_become_an_app_update(self):
        sid = self.ids('3b03e1')[0]
        title, lead, facts = self.rows[sid]['recorded_extraction']
        self.assertFalse(self.m.is_third_party_consumer_app_update_on_apple_platform(
            title, ' '.join((lead, *facts))))
        events, _ = self.cluster_sources(sid)
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('strong', 'hardware_products')])

    def test_demo_configuration_requires_its_device_and_operator(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPhone 23 demo units cannot install third-party apps'
        lead = 'Apple Store iPhone 23 demo units currently cannot install third-party apps.'
        frame = source_device_operation_frame(title, lead)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.action, 'retail-demonstration-configuration')
        for other in (lead.replace('iPhone 23', 'iPhone 24'),
                      lead.replace('Apple Store', 'Orion Store'),
                      'Last year, ' + lead, 'If ' + lead,
                      '苹果官方门店的iPhone 23展示机支持第三方应用，三星门店展示机无法安装第三方应用。',
                      '苹果官方门店的iPhone 23展示机运行正常，顾客的手机无法安装第三方应用。',
                      lead.replace('currently cannot', 'will not be able to'),
                      'Apple Store iPhone 23 demo units support third-party apps, while Orion Store demo units cannot install third-party apps.',
                      "Apple Store iPhone 23 demo units are available, but visitors' phones cannot install third-party apps"):
            result = source_device_operation_frame(title, other)
            self.assertTrue(result is None or result.action != frame.action, other)

    def test_named_app_actions_keep_stage_and_platform(self):
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform as owned
        for title, lead in (
            ('Orion 接入 iMessage：iPhone 用户可生成音乐', '第三方 Orion 应用更新后可从 iMessage 生成音乐。'),
            ('山川鸿蒙版灰度测试新功能', '山川鸿蒙版正在灰度测试新功能，iPhone 仅是背景。'),
        ):
            self.assertTrue(owned(title, lead, named_only=True))
            for other in ('如果' + lead, lead.replace('Orion', 'NewOrion').replace('山川', '新山川'), lead.replace('更新后', '更新已被拒绝，尚未接入iMessage，')
                          if '更新后' in lead else lead.replace('新功能', '的申请已被拒绝'),
                          lead.replace('Orion', 'Aurora').replace('山川', '河流')):
                self.assertFalse(owned(title, other, named_only=True), other)
        self.assertFalse(owned('山川鸿蒙版灰度测试新功能',
                              '山川Android版正在灰度测试新功能，iPhone 仅是背景。', named_only=True))

    def test_named_app_edition_keeps_its_own_testing_action(self):
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform as owned
        title = '可调用不同镜头：山川 iOS 版灰度测试相机功能'
        lead = '山川团队灰度测试自己的 iOS 应用相机功能，可调用 iPhone 镜头。'
        self.assertTrue(owned(title, lead, named_only=True))
        self.assertTrue(owned(title, '山川 iOS 版正在灰度测试相机功能。', named_only=True))
        for other in ('去年' + lead, '如果' + lead,
                      lead.replace('山川', '新山川'), lead.replace('山川', '河流'),
                      lead.replace('iOS', 'Android'),
                      lead.replace('灰度测试', '没有灰度测试'),
                      '山川团队发布新闻，河流团队灰度测试自己的 iOS 应用相机功能。'):
            self.assertFalse(owned(title, other, named_only=True), other)

    def test_owned_action_skips_unused_legacy_support(self):
        from unittest.mock import patch
        title = 'Apple describes developer apps for iPhone 23'
        lead = ('Apple has named apps and games it will highlight on the App Store '
                'when the new device goes on sale.')
        article = article_for(self.m, title, lead)
        with patch.object(self.m, 'is_apple_intelligence_china_regulatory_rollout_story',
                          side_effect=AssertionError('unused legacy support was evaluated')):
            profile = self.m.legacy_article_reconciliation_profile(article,
                _source_kind_snapshot=(article.title, article.summary, tuple(article.key_facts), article.event_kind))
        self.assertIn('source-local-action-authority', profile.separation_keys)
        self.assertEqual((profile.relevance_tier, profile.category_hint),
                         ('strong', 'software_systems'))

    def test_channel_plan_does_not_borrow_chip_or_official_launch_actions(self):
        events, _ = self.cluster_sources(*self.ids('5d011'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        article = events[0].articles[0]
        self.assertEqual(article.bound_claim.action, 'channel-stock-schedule')
        self.assertIn('京东', article.bound_claim.object)
        self.assertIn('今晚', ' '.join(article.key_facts))
        self.assertNotIn('technical-disclosure', str(self.m.article_reconciliation_profile(article).event_keys))
        for title, lead in (
            ('iPhone 23 渠道开售：搭载 A25 Pro', 'iPhone 23搭载A25 Pro芯片。苹果官网显示每人限购2部。'),
            ('A25 Pro iPhone 23供货报道', '苹果官网显示iPhone 23库存变化。它使用A25 Pro芯片。'),
            ('iPhone 23 渠道开售：搭载A25 Pro', '报道称Orion的X9芯片采用3nm工艺，iPhone 23使用A25 Pro。'),
            ('iPhone 23 渠道开售：搭载A25 Pro', '苹果官网显示搭载A25 Pro芯片的iPhone 23每人限购2部。'),
            ('iPhone 23 渠道开售：搭载A25 Pro', '去年报道称A25 Pro采用2nm工艺。'),
            ('iPhone 23 渠道开售：搭载A25 Pro', '消息称A25 Pro采用2nm工艺，但这一消息不实。'),
        ):
            profile = self.m.article_reconciliation_profile(article_for(self.m, title, lead, 'IT之家'))
            self.assertFalse(any('technical-disclosure' in key for key in profile.event_keys))

    def test_channel_plan_unresolved_scope_does_not_fall_back(self):
        from apple_news_core.event_identity import bind_channel_stock_operation
        title = 'iPhone 23 山川商店率先开售'
        for text in (
            'iPhone 23 明天上市，山川商店下一批将于今晚20:00开抢保护壳。',
            'iPhone 23 明天上市，山川商店下一批将于今晚20:00开抢其他配件。',
            'iPhone 23山川商店下一批将于今晚20:00开抢，但这一消息不实。',
        ):
            claim = bind_channel_stock_operation(self.evidence(title, text))
            self.assertIsNotNone(claim)
            self.assertTrue(claim.review_reason)
            self.assertFalse(self.m.claim_eligibility(claim).resolved)

    def test_owned_promotion_form_governs_admission_and_relevance(self):
        row = self.rows[self.ids('55f458')[0]]
        title, summary, facts = row['recorded_extraction']
        candidate = self.m.Candidate('IT之家', row['evidence']['url'], title, summary)
        self.assertFalse(self.m.is_relevant_candidate(candidate, self.sources['IT之家'], facts))
        article = article_for(self.m, title, summary, 'IT之家')
        self.assertEqual(self.m.article_title_led_event_identity(article).content_form, 'deal')
        self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'weak')
        from apple_news_core.event_identity import build_event_identity
        self.assertEqual(build_event_identity('iPhone 23 套装上线，红包不限量',
            '全场狂促，数码家电皆为年度好价，点击领取购物红包。').content_form, 'deal')
        self.assertNotEqual(build_event_identity('iPhone 23 安全调查发现红包骗局',
            '研究人员发现新型攻击。文末购物广告提供红包不限量。').content_form, 'deal')
        for title, lead in (
            ('苹果警告：红包不限量是诈骗，切勿领取', '苹果发布安全警告，提醒用户不要相信所谓购物促销或点击领取红包链接。'),
            ('苹果关闭“领取红包”诈骗应用', '苹果确认删除了以购物优惠为幌子的诈骗应用，用户被诱导点此领取红包。'),
        ):
            self.assertNotEqual(build_event_identity(title, lead).content_form, 'deal')

    def test_new_window_app_and_competitor_measurement_owners(self):
        for prefix in ('ad2fff', '9616f2'):
            events, _ = self.cluster_sources(*self.ids(prefix))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'weak')
        events, _ = self.cluster_sources(*self.ids('ad2fff', '9257b8'))
        self.assertEqual(len(events), 2)

    def test_mixed_script_app_names_and_platform_targets_keep_owner(self):
        from apple_news_core.event_identity import source_app_adaptation_frame
        for name in ('AB音乐', '山川Music'):
            title = name + '率先适配iOS 28'
            body = name + '已完成iOS 28适配并更新软件界面。'
            frame = source_app_adaptation_frame(title, body)
            self.assertIsNotNone(frame)
            self.assertEqual(frame.tier, 'weak')
            self.assertIn(name.lower(), frame.subject)
            for text in (body.replace('已完成','尚未完成'), body.replace(name,'其他应用'),
                         body.replace('已完成','去年已完成'), body.replace('iOS 28', 'iOS 29'),
                         name + ' 9.0版本已完成全面适配Android 16，并更新软件界面。'):
                self.assertIsNone(source_app_adaptation_frame(title, text))

    def test_causal_market_headline_keeps_the_measured_product(self):
        from apple_news_core.event_identity import source_hardware_sales_owner
        title = 'iPhone 23带动星海折叠手机出货：Orion Max销量环比增长38%'
        body = 'iPhone 23开售后，星海Orion Max的单周销量环比增长38%。'
        self.assertEqual(source_hardware_sales_owner(title, body), '星海orion max')
        self.assertFalse(self.m.is_apple_specific_market_share_report_story(body, title))
        self.assertEqual(self.m.classify_relevance_tier(title, body, [], '快科技')[0], 'weak')
        for other in ('去年' + body, '如果' + body,
                      body.replace('Orion Max', 'Orion Mini'), body.replace('增长38%', '没有增长')):
            self.assertEqual(source_hardware_sales_owner(title, other), '', other)
        self.assertEqual(source_hardware_sales_owner('iPhone 23销量增长：Orion Max同期下滑',
            'iPhone 23的单周销量增长20%。Orion Max销量下滑。'), 'apple')
        events, _ = self.cluster_sources(*self.ids('b509'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'hardware_products')])

    def test_cumulative_measurement_uses_the_same_owner(self):
        from apple_news_core.event_identity import source_hardware_sales_owner
        title = '山川阔折叠手机出货量突破300万：iPhone 23预售六天'
        self.assertEqual(source_hardware_sales_owner(title, '山川阔折叠累计出货量突破300万台。'), '山川阔折叠手机')
        for text in ('去年山川阔折叠累计出货量突破300万台。', '另一手机累计出货量突破300万台。'):
            self.assertEqual(source_hardware_sales_owner(title, text), '')
        from apple_news_core.event_identity import source_market_report_frame
        frames = [source_market_report_frame(name + '手机出货量增长：对比iPhone 23',
            name + '累计出货量突破300万台。', ()) for name in ('山川', '星海')]
        self.assertNotEqual(frames[0].subject, frames[1].subject)

    def test_retailer_name_does_not_make_a_stock_report_a_discount(self):
        row = self.rows[self.ids('3f3d8d')[0]]
        title, summary, facts = row['recorded_extraction']
        self.assertFalse(self.m.is_routine_retail_discount_story(title, title + ' ' + summary))
        evidence = row['evidence']
        candidate = self.m.Candidate(evidence['source'], evidence['url'], title, summary)
        self.assertTrue(self.m.is_relevant_candidate(candidate, self.sources[evidence['source']], facts))
        events, _ = self.cluster_sources(self.ids('3f3d8d')[0])
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        from apple_news_core.event_identity import bind_channel_stock_operation
        headline = '山川商店补货iPhone 23现货'
        for opening in ('山川商店今天补货iPhone 23现货。', '星海商店今天补货iPhone 23现货。',
                        '去年山川商店补货iPhone 23现货。', '山川商店计划补货iPhone 23现货。',
                        '山川商店没有补货iPhone 23现货。', '山川商店今天补货iPhone 23 Pro现货。',
                        '山川商店今天补货iPhone 23 cases。'):
            frame = bind_channel_stock_operation(self.evidence(headline, opening))
            self.assertEqual(frame is not None and bool(frame.subject) and frame.action == 'channel-stock-availability', opening == '山川商店今天补货iPhone 23现货。')

    def test_vendor_platform_announcement_keeps_unresolved_apple_transfer(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference
        data = dict(self.rows[self.ids('3044d8')[0]]['evidence'])
        data['units'] = tuple(EvidenceUnit(**u) for u in data['units'])
        data['publication_candidates'] = tuple(PublicationEvidence(**u) for u in data['publication_candidates'])
        data['embedded_references'] = tuple(EmbeddedReference(**u) for u in data['embedded_references'])
        evidence = ArticleEvidence(**data)
        projections, remainder, excluded = self.m.project_article_evidence(evidence)
        self.assertEqual(len(projections), 1)
        self.assertFalse(self.m.claim_eligibility(projections[0].claim).resolved)
        self.assertTrue(projections[0].claim.review_reason)
        self.assertTrue(remainder)
        self.m.validate_evidence_dispositions(evidence, projections, remainder, excluded)

    def test_new_window_local_operation_and_company_category(self):
        for prefix, expected in [('ce80dd', ('ecosystem', 'software_systems')),
                                 ('8fdd46', ('strong', 'hardware_products')),
                                 ('bde2be', ('weak', 'software_systems'))]:
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [expected])
                if prefix == 'ce80dd':
                    text = ' '.join(events[0].key_facts)
                    self.assertIn('全日空', text)
                    self.assertIn('预防措施', text)
                    self.assertIn('Apple Wallet登机牌服务', text)
                    self.assertNotIn('维基百科', text)
                if prefix == 'bde2be':
                    p = self.m.article_reconciliation_profile(self.source_articles(self.ids(prefix)[0])[0])
                    self.assertFalse(any('keyboard-compatibility' in k for k in p.event_keys))

    def test_service_inclusion_preserves_local_suspension_scope(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_embedded_app_state
        article = self.source_articles(self.ids('7f20')[0])[0]
        unit = next(u for u in article.evidence.units if '全日空航空关闭' in u.text)
        for text, included in [
            ('山川周三表示，已作为预防措施暂停其网站和应用程序服务，包括Apple Wallet登机牌服务。', True),
            ('Example Airways said it suspended its website and app services, including Apple Wallet boarding passes.', True),
            ('山川表示，将暂停其网站服务，包括Apple Wallet登机牌服务。', False),
            ('山川表示，尚未暂停其网站服务，包括Apple Wallet登机牌服务。', False),
            ('山川暂停网站服务，但Apple Wallet登机牌服务不受影响。', False),
            ('用户暂停Apple Wallet登机牌通知。', False),
            ('山川表示去年暂停其网站服务，包括Apple Wallet登机牌服务。', False),
        ]:
            with self.subTest(text=text):
                evidence = replace(article.evidence, units=(replace(unit, text=text),))
                claim = bind_embedded_app_state(evidence)
                self.assertEqual(claim is not None, included)
                if claim is not None:
                    self.assertEqual(claim.action, 'integration-suspension')
                    self.assertEqual(claim.category, 'software_systems')
        for text, actor in [
            ('山川表示，海港航空已暂停其网站和应用程序服务，包括Apple Wallet登机牌服务。', '海港航空'),
            ('Example Airways said Harbor Bank suspended its website services, including Apple Wallet cards.', 'harbor-bank'),
        ]:
            claim = bind_embedded_app_state(replace(article.evidence, units=(replace(unit, text=text),)))
            self.assertTrue(claim.subject.startswith(actor + ':'), claim)
        unresolved = bind_embedded_app_state(replace(article.evidence, units=(replace(unit,
            text='某机构暂停Apple Wallet登机牌服务。'),)))
        self.assertTrue(unresolved.review_reason)
        self.assertFalse(unresolved.subject)

    def test_accessory_evaluation_requires_local_product_operation(self):
        from apple_news_core.event_reconciler import _hardware_accessory_evaluation_claim
        for title, lead in [
            ('macOS runs on an ARM laptop', 'The keyboard works. Support is limited to one laptop.'),
            ('Mac prototype disclosed', 'Its keyboard has black keys. Software supports a new media format.'),
            ('Mac prototype disclosed', 'Apple revealed the Mac display, while Orion tested its keyboard.'),
        ]:
            self.assertIsNone(_hardware_accessory_evaluation_claim(title, lead, self.m.title_led_identity(title, lead)))

    def ids(self, *prefixes):
        return [next(k for k in self.rows if k.startswith(p)) for p in prefixes]

    def test_shared_source_form_keeps_negation_and_subject_normalization(self):
        from apple_news_core.event_identity import _content_form, source_hardware_sales_owner
        title = 'Apple TV pre-orders this week?'
        for denial in ('no new report', 'without any new report', 'not a new report',
                       'no new report from an analyst', 'no new report according to a leaker'):
            lead = 'An educated guess based on historical patterns, with ' + denial + '.'
            with self.subTest(denial=denial):
                self.assertEqual(_content_form(title, lead), 'analysis')
                self.assertNotEqual(_content_form(title, lead + ' Sources say orders open Friday.'), 'analysis')
                self.assertNotEqual(_content_form(title, lead[:-1] + ', but sources say orders open Friday.'), 'analysis')
        for verb in ('recap', 'recapped', 'are recapping', 'compile', 'compiled', 'are compiling'):
            self.assertEqual(_content_form('AirPods news this week',
                'We ' + verb + ' previously reported AirPods rumors, without new reporting.'), 'roundup')
        for subject in ('苹果', '苹果手机', '苹果设备', '苹果公司手机'):
            self.assertEqual(source_hardware_sales_owner(subject + '销量增长', subject + '销量增长15%。'), 'apple')
        for subject in ('苹果手机壳', '苹果供应商', '友商手机'):
            self.assertNotEqual(source_hardware_sales_owner(subject + '销量增长', subject + '销量增长15%。'), 'apple')

    def test_comparison_ownership_is_shared_by_legacy_and_identity_entrypoints(self):
        from apple_news_core.event_identity import is_non_apple_title_context
        for title, expected in [
            ('Leaker reveals larger iPhone 23 details, possible Telephoto camera', False),
            ('Researcher describes a faster iPhone 23 processor', False),
            ('Leaker says iPhone 23 is larger than iPhone 22', False),
            ('A new report reveals iPhone 23 uses the same camera as iPhone 22', False),
            ('报告称iPhone 23采用与iPhone 22同款相机', False),
            ('Leaker says Orion phone is larger than iPhone 23', True),
            ('Orion’s Android phone has a wider screen like the iPhone 23', True),
            ('Orion phone is larger than the iPhone 23', True),
            ('Orion phone uses the same camera technology as iPhone 23', True),
            ('iPhone 23 has a wider screen than an Orion phone', False),
            ('Orion园区面积超苹果园区', True),
            ('Orion手机跑分与iPhone 23持平', True),
            ('秋季新品对决！Orion新手机迎战iPhone 23', True),
            ('iPhone 23迎战Orion手机', False),
            ('挑战业内对手，供应商将为苹果提供屏幕', False),
            ('Inside Beats lab: Outside Apple, a new acoustic process', False),
        ]:
            with self.subTest(title=title):
                self.assertEqual(is_non_apple_title_context(title, ''), expected)
                self.assertEqual(self.m.is_non_apple_title_action_using_apple_as_reference_story(title, ''), expected)
        for prefix, tier in [('4b459', 'strong'), ('ef69', 'weak')]:
            events, _ = self.cluster_sources(*self.ids(prefix))
            self.assertTrue(events)
            self.assertEqual({e.relevance_tier for e in events}, {tier})

    def test_fresh_source_operations_keep_owner_and_category(self):
        for prefix, tier, category in [
            ('26c8','strong','software_systems'), ('3065','strong','software_systems'),
            ('31b5','weak','software_systems'), ('3550','strong','software_systems'),
            ('582e','strong','software_systems'), ('8d3d','strong','software_systems'),
            ('cdd8','weak','hardware_products'), ('ed134','strong','software_systems'),
            ('594149','weak','hardware_products'), ('c1f50','weak','software_systems'),
            ('511197','strong','hardware_products'), ('6d9a','strong','hardware_products'),
            ('1653','strong','hardware_products'), ('1e587','strong','hardware_products'),
        ]:
            with self.subTest(source=prefix):
                events,_ = self.cluster_sources(*self.ids(prefix))
                self.assertTrue(events)
                self.assertTrue(all((e.relevance_tier,e.category)==(tier,category) for e in events),
                    [(e.relevance_tier,e.category,e.relevance_reason) for e in events])

    def test_retail_discount_is_excluded_at_candidate_admission(self):
        row = self.rows[self.ids('1e1a')[0]]
        evidence = row['evidence']
        title, summary, facts = row['recorded_extraction']
        candidate = self.m.Candidate(evidence['source'], evidence['url'], title, summary,
                                     evidence['published_utc'])
        self.assertFalse(self.m.is_relevant_candidate(candidate, self.sources[evidence['source']], facts))

    def test_current_store_activation_and_editorial_comparison_have_owned_roles(self):
        for prefix, expected in [('d4c3', ('strong', 'software_systems')), ('69d76', ('weak', 'software_systems'))]:
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [expected])

    def test_badge_announcement_is_not_completed_deployment(self):
        ids = self.ids('a9e5', '901f', '26c8', '04bd')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_same_named_work_appeal_does_not_borrow_initial_trial_stage(self):
        ids = self.ids('62ec', 'c03f')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_store_activation_service_requires_current_operator_action(self):
        from apple_news_core.event_identity import source_retail_program_frame
        title = '苹果门店可以办理eSIM激活'
        text = '苹果已在全国所有Apple Store零售店安排运营商工作人员，为顾客现场办理eSIM激活业务。'
        frame = source_retail_program_frame(title, text, (text,))
        self.assertEqual((frame.category, frame.tier), ('software_systems', 'strong'))
        for bad in ('去年' + text, text.replace('苹果已在', 'Orion已在'),
                    text.replace('安排', '没有安排'), '苹果门店附近，Orion安排人员为顾客办理eSIM激活。',
                    'A rival of Apple provides carrier staff at its stores to help customers activate eSIM.',
                    '苹果在Apple Store零售店安排活动，Orion提供工作人员为用户办理eSIM激活。'):
            self.assertIsNone(source_retail_program_frame(title, bad, (bad,)), bad)

    def test_editorial_comparison_preserves_reported_current_actions(self):
        from apple_news_core.event_identity import source_editorial_outlook
        title = 'Apple is catching up with its assistant'
        opinion = 'I suspect the next advance will depend on personal context.'
        self.assertTrue(source_editorial_outlook(title, opinion, (opinion,)))
        current = 'Apple announced a new assistant feature today.'
        self.assertFalse(source_editorial_outlook(title, current, (current, opinion)))
        quoted = 'A researcher said, "I suspect the next advance will depend on personal context."'
        self.assertFalse(source_editorial_outlook(title, quoted, (quoted,)))

    def test_copyright_appeal_identity_preserves_case_and_procedural_boundaries(self):
        from apple_news_core.event_identity import source_copyright_appeal_frame
        title = 'Apple wins copyright appeal'
        current = 'The Ninth Circuit Court of Appeals today upheld the verdict for Apple.'
        case = 'Filmmaker Alice Carter sued over the series Harbor.'
        frame = source_copyright_appeal_frame(title, current, (current, case))
        self.assertIsNotNone(frame)
        for other in (case.replace('Harbor', 'Beacon'), case.replace('Alice Carter', 'Jane Baker')):
            self.assertNotEqual(frame.subject, source_copyright_appeal_frame(title, current, (current, other)).subject)
        other_court = current.replace('Ninth', 'Third')
        self.assertNotEqual(frame.region, source_copyright_appeal_frame(title, other_court, (other_court, case)).region)
        for bad in (current.replace('today', 'last year'), current.replace('upheld', 'has not upheld'),
                    'Apple plans to appeal the verdict.', 'A jury found for Apple in the copyright trial.'):
            self.assertIsNone(source_copyright_appeal_frame(title, bad, (bad, case)), bad)
        unrelated = current.replace('for Apple', 'in an unrelated case against Orion')
        self.assertIsNone(source_copyright_appeal_frame(title, unrelated, (unrelated, case)))
        commentary = 'Director Jane Baker commented on copyright law.'
        self.assertEqual(frame.subject, source_copyright_appeal_frame(title, current, (current, commentary, case)).subject)

    def test_production_and_order_targets_share_reported_operation(self):
        ids = self.ids('00c128', '9f3d25bd62086fe04dc53937')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)

    def test_same_store_display_preparation_keeps_all_sources(self):
        ids = self.ids('511197', '1fc248', 'a3fabd')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_retail_display_requires_actor_and_physical_object(self):
        from apple_news_core.event_identity import source_retail_operation_frame
        for title, lead, expected in [
            ('Giant iPhone 23 installations', 'Apple is preparing a report about the display at its Fifth Avenue store.', False),
            ('iPhone 23巨型模型布置', '苹果第五大道零售店外，Orion正在搭建巨型模型。', False),
            ('iPhone 23巨型模型布置', '苹果否认正在纽约第五大道旗舰店外布置大型展示装置。', False),
            ('iPhone 23巨型模型布置', '苹果正在纽约第五大道旗舰店外布置大型展示装置。具体展示形式尚未公开。', True),
            ('Giant iPhone 23 installations', 'Apple is preparing what appear to be giant iPhone 23 displays outside its Fifth Avenue store.', True),
        ]:
            with self.subTest(lead=lead):
                frame = source_retail_operation_frame(title, lead, (lead,))
                self.assertEqual(bool(frame and frame.action == 'retail-display-preparation'), expected)

    def test_visual_queue_report_preserves_current_observation_boundary(self):
        from apple_news_core.event_identity import bind_retail_queue_observation, source_accessory_category
        title = '多家苹果店门前排起长龙，只为iPhone 23'
        for text, current in [
            ('博主视频显示，多家苹果零售店门前排起了长队，消费者等候领取iPhone 23。', True),
            ('博主视频显示，多家苹果零售店门前并未排起长队，消费者已领取iPhone 23。', False),
            ('博主预计，多家苹果零售店门前将会排起长队，消费者等待iPhone 23。', False),
            ('去年博主视频显示，多家苹果零售店门前排起了长队，消费者等候iPhone 23。', False),
        ]:
            claim = bind_retail_queue_observation(self.evidence(title, text))
            self.assertEqual(bool(claim and claim.subject), current)
        self.assertEqual(source_accessory_category('A Windows ARM laptop can be made into a Hackintosh'), 'software_systems')
        self.assertEqual(source_accessory_category('Orion laptop runs Windows with a new display'), 'hardware_products')

    def test_first_deliveries_share_the_actual_regional_launch(self):
        ids = self.ids('e1c389', 'dbb371')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_current_support_cannot_borrow_contextual_legacy_keywords(self):
        from apple_news_core.event_identity import source_hardware_sales_owner
        self.assertEqual(source_hardware_sales_owner('iPhone 23上市后Orion手机销量增长',
            '截至周三，Orion手机销量达到400万台。'), 'orion手机')
        self.assertEqual(source_hardware_sales_owner('Orion手机上市后iPhone 23销量增长',
            'iPhone 23销量达到400万台。'), 'apple')
        self.assertEqual(source_hardware_sales_owner('iPhone 23销量增长',
            '去年iPhone 23销量达到400万台。'), '')
        self.assertFalse(self.m.is_apple_retail_device_deployment_story('Apple Store buyers line up for iPhone 23',
            'Store employees watched customers queue for the iPhone 23, which is equipped with a new display.'))
        self.assertTrue(self.m.is_apple_retail_device_deployment_story('Apple expands staff equipment',
            'Apple will give retail employees iPhone 23 units to replace their card readers.'))
        self.assertFalse(self.m.is_direct_apple_product_patent_story('iPhone 23 goes on sale today',
            'Apple patented a folding device in 2011. Customers can now collect their new phones.'))
        self.assertTrue(self.m.is_direct_apple_product_patent_story('A future iMac could have a removable dock',
            'A newly granted Apple patent describes an iMac with a removable dock.'))

    def test_local_authority_uses_actors_recipients_and_polarity(self):
        from apple_news_core.event_identity import (source_product_patent_disclosure,
            source_retail_employee_equipment, source_hardware_sales_owner,
            source_operation_frame, build_event_identity)
        self.assertFalse(source_product_patent_disclosure('Apple denies new design patent for iPhone 23',
            'Apple denied that it had received a new design patent for iPhone 23.'))
        self.assertFalse(source_product_patent_disclosure('Orion granted patent for iPhone case',
            'Orion was granted a new patent for an iPhone case.'))
        self.assertFalse(source_retail_employee_equipment('Apple Store employees greet customers',
            'Apple Store employees greet customers while Orion equips buyers with iPhones.'))
        self.assertNotEqual(source_hardware_sales_owner('Apple supplier sales rose',
            'Apple supplier sales rose to 4 million units.'), 'apple')
        for subject in ('iPhone case', 'Apple Watch rival'):
            self.assertNotEqual(source_hardware_sales_owner(subject + ' sales rose',
                subject + ' sales reached 4 million units.'), 'apple')
        self.assertEqual(source_hardware_sales_owner('iPhone 23 sales rose',
            'iPhone 23 sales rose to 4 million units.'), 'apple')
        self.assertEqual(source_hardware_sales_owner('iPhone 23 sales rose',
            'iPhone 24 sales rose to 4 million units.'), '')
        for title, lead in [
            ('Apple Music adds Apple Watch support',
             'Apple Music now allows members to connect their Apple Watch to its own service.'),
            ('Orion adds Apple Watch support',
             'Orion denied that it will allow members to connect their Apple Watch to its proprietary platform.'),
        ]:
            frame = source_operation_frame(title, lead, (), build_event_identity(title, lead))
            self.assertTrue(frame is None or not frame.subject.startswith('third-party-service:'))
        title = 'Orion previews iPhone 23 apps'
        lead = 'Editorial collections for iPhone 23 will go live on the App Store.'
        frame = source_operation_frame(title, lead, (), build_event_identity(title, lead), source_units=(lead,))
        self.assertTrue(frame is None or not frame.subject.startswith('apple:app-store:curated-apps:'))

    def test_multi_seat_announcement_keeps_each_channels_stage(self):
        from apple_news_core.event_identity import source_named_publication_frame, build_event_identity
        row = self.rows[self.ids('8d3d')[0]]
        evidence = row['evidence']
        passages = tuple(u['text'] for u in evidence['units'])
        frame = source_named_publication_frame(evidence['title'], evidence['raw_lead'], passages,
            build_event_identity(evidence['title'], evidence['raw_lead']))
        self.assertEqual(frame.subject, 'app-store:subscription-seat-purchasing')
        self.assertEqual(frame.action, 'store-feature-announcement')

    def test_app_removal_does_not_inherit_the_preceding_update(self):
        ids=self.ids('b16e','105f')
        for order in (ids,ids[::-1]):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),2)

    def test_comparison_compatibility_does_not_reject_a_service_recipient(self):
        title = 'Transit operator responds to free Apple Pay cards and Android fees'
        self.assertFalse(self.m.is_non_apple_title_action_using_apple_as_reference_story(title, ''))
        events, _ = self.cluster_sources(*self.ids('e132'))
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'software_systems' for e in events))

    def test_current_cover_report_binds_local_role_and_company_choice(self):
        events, _ = self.cluster_sources(*self.ids('c118'))
        self.assertTrue(any(e.relevance_tier == 'strong' and e.category == 'hardware_products' for e in events))
        from apple_news_core.article_processing import capture_article_title_evidence
        from apple_news_core.event_identity import bind_leadership_report
        title = 'Apple CEO explains the product development decision'
        lead = 'Apple released the device earlier this year.'
        report = 'In a new cover story, Apple CEO Jane Miller explains the development decision.'
        choice = 'Miller says Apple prioritizes mature technology in product development.'
        for intro, statement, expected in [
            (report, choice, 'strong'),
            (report.replace('Apple CEO', 'Orion CEO'), choice, 'weak'),
            (report.replace('Apple CEO', 'former Apple CEO'), choice, 'weak'),
            (report.replace('new cover story', 'cover story from last year'), choice, None),
            (report, 'Miller discusses her favorite books and weekend walks.', ''),
        ]:
            with self.subTest(intro=intro, statement=statement):
                evidence = capture_article_title_evidence('Source', '', title, lead, (lead, intro, statement))
                claim = bind_leadership_report(evidence)
                if expected is None:
                    self.assertTrue(claim is None or self.m.claim_eligibility(claim).tier != 'strong')
                else:
                    self.assertIsNotNone(claim)
                    self.assertEqual(self.m.claim_eligibility(claim).tier, expected)
        for other_title, intro in [
            (title, 'Apple CEO Jane Miller did not give a new interview.'),
            ('John Ternus buys a new car', 'In a new cover story, Apple CEO John Ternus explains the development decision.'),
        ]:
            statement = choice if 'Miller' in intro else 'Ternus says Apple prioritizes mature technology in product development.'
            claim = bind_leadership_report(capture_article_title_evidence('Source', '', other_title, lead, (intro, statement)))
            self.assertTrue(claim is None or self.m.claim_eligibility(claim).tier != 'strong')
        events, _ = self.cluster_sources(*self.ids('9a7d'))
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_chinese_store_marker_uses_the_same_planned_service_action(self):
        events, output = self.cluster_sources(*self.ids('04bd'))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'software_systems')
        for ids in [self.ids('04bd', '901f'), self.ids('901f', '04bd')]:
            grouped, _ = self.cluster_sources(*ids)
            self.assertEqual(len(grouped), 1)
            self.assertEqual(self.source_ids(grouped[0]), set(ids))
        from apple_news_core.event_identity import source_named_publication_frame, build_event_identity
        for verb in ['引入', '推出', '新增']:
            title = '苹果为iPhone 23推出专属应用标识'
            text = '苹果宣布将在App Store中' + verb + '“Designed for iPhone 23”标识。'
            frame = source_named_publication_frame(title, text, (text,), build_event_identity(title, text))
            self.assertIsNotNone(frame)
            self.assertEqual(frame.action, 'store-feature-plan')

    def test_numeric_shortlist_does_not_turn_author_inferences_into_required_facts(self):
        cases = [
            ('8f5f3d34', 'While it sounds like', 'exclude muted'),
            ('77fe', '按照理论推算', '4K 120fps'),
            ('77fe', '其像素数量可能低于 800 万', '4K 120fps'),
            ('1baec0', 'we may see another evolution', 'Mark Gurman reports'),
            ('1baec0', 'With iPhone Duo 2 and the twentieth anniversary iPhone Pro', 'Mark Gurman reports'),
            ('1baec0', 'customers can probably expect', 'Mark Gurman reports'),
            ('8233db', '或许是更稳妥的选择', '溢价2000至3000元'),
        ]
        for prefix, interpretation, reported in cases:
            with self.subTest(source=prefix):
                events, output = self.cluster_sources(*self.ids(prefix))
                public = '\n'.join(e['summary'] + '\n' + '\n'.join(
                    e['key_facts'] + e.get('must_include_facts', [])) for e in output)
                self.assertNotIn(interpretation, public)
                self.assertIn(reported, public)
                pending = [fact for e in events for fact in e.fact_plan.unprocessed]
                self.assertTrue(any(interpretation in fact.text for fact in pending))
                for fact in pending:
                    if interpretation not in fact.text:
                        continue
                    self.assertNotIn('source-measurement', fact.roles)
                    for _, _, sid, unit_id, start, end in fact.origins:
                        if unit_id:
                            unit = next(u for u in self.rows[sid]['evidence']['units']
                                        if u['unit_id'] == unit_id)
                            self.assertEqual(fact.text, unit['text'][start:end])

    def test_attributed_forecast_and_real_numeric_conditions_keep_preservation(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        title = 'Apple reports current iPhone 23 camera support'
        facts = [
            'Apple says iPhone 23 currently supports 1080p recording at 60fps.',
            'According to analyst Morgan Lee, the next iPhone may offer a 12-megapixel camera.',
            'Morgan Lee says we may see a 12-megapixel camera next year.',
            'Apple says the camera records 1080p video at 60fps, but Morgan Lee says we may see a 12-megapixel camera next year.',
            'Apple says the camera will not support 4K recording in iOS 31.2.',
            'The iPhone 23 camera requires iOS 31.1 and supports only 30fps in low light.',
        ]
        article = article_for(self.m, title, ' '.join(facts), facts=facts)
        article.evidence = capture_article_title_evidence(article.source, article.url,
            title, facts[0], tuple(facts))
        view = self.m.prepare_source_fact_view(article)
        required = self.m.resolve_event_fact_plan([view], relevance_tier='strong',
            base_limit=2, official_limit=2).required
        for text in facts:
            self.assertTrue(any(text in fact.text for fact in required), text)

    def test_evaluative_words_do_not_override_reported_conditions(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        cases = [
            ('微信开发者官方给出了配置要求。',
             'iPhone 23上的应用不建议自行删减必需配置。请将必配及实际使用的能力配置放在前25项，完成后应验证实际使用的功能。'),
            ('报道披露了当前市场价格。',
             '值得一提的是，iPhone 23在其他渠道溢价2000至3000元不等，当前不同容量版本的报价存在差异。'),
            ('设计师陈明评价了iPhone 23的界面。',
             '设计师陈明点评iPhone 23的侧边导航，直言很多图标让人看不懂。'),
        ]
        for context, text in cases:
            with self.subTest(text=text):
                article = article_for(self.m, 'Apple reports iPhone 23 operating conditions', text, facts=[text])
                article.evidence = capture_article_title_evidence(article.source, article.url,
                    article.title, context, (context, text))
                view = self.m.prepare_source_fact_view(article)
                self.assertTrue(any(text in fact.text for fact in view.normal))
                self.assertFalse(any(text in fact.text for fact in view.unprocessed
                    if 'unprocessed-editorial-condition' in fact.roles))
        for prefix, text in [('9257b8', '不建议为节省名额自行删减'),
                             ('c69bc0', 'ColorOS设计总监陈希点评')]:
            _, output = self.cluster_sources(*self.ids(prefix))
            self.assertTrue(any(text in event['summary'] or any(text in fact
                for fact in event['key_facts']) for event in output), prefix)

    def test_report_argument_does_not_inherit_background_market_qualification(self):
        from apple_news_core.event_identity import source_editorial_evaluation
        events, _ = self.cluster_sources(*self.ids('d9e1b618'))
        self.assertTrue(all(event.relevance_tier == 'weak' for event in events))
        for title, lead in [
            ('More iPhone parts ordered does not mean more shipments',
             'A new report is conflating two different figures to conclude that production increased.'),
            ('增加零件订单不等于整机出货增长',
             '这篇报道混淆了零件订单与整机出货两种口径，进而得出产量上升的结论。'),
        ]:
            self.assertEqual(source_editorial_evaluation(title, lead), 'analysis')
        for title, lead in [
            ('Apple says increased parts orders do not mean increased shipments',
             'Apple says a new report is conflating component orders with shipments, and confirms its production target is unchanged.'),
            ('An analyst revises the iPhone shipment forecast',
             'Morgan Lee says a previous report confused two figures and has cut the forecast from 15 to 12 million.'),
            ('苹果回应：零件订单增加不等于出货增长',
             '苹果回应称报道混淆了零件与整机口径，并确认今年出货目标不变。'),
        ]:
            self.assertNotEqual(source_editorial_evaluation(title, lead), 'analysis')

    def test_app_commentary_does_not_pool_background_specs_with_other_announcements(self):
        events, _ = self.cluster_sources(*self.ids('3d3760'))
        self.assertTrue(all(event.relevance_tier == 'weak' for event in events))
        for title, text in [
            ('Apps on iPhone 23 face a difficult transition',
             'Apple announced updated apps. Developers discuss the inner screen and camera. Other apps are coming later.'),
            ('iPhone 23应用适配仍需时间',
             '苹果公布了一批适配应用。开发者讨论内屏与相机的使用。其他应用预计稍后推出。'),
            ('iPhone 23 apps will take time', 'Apple published an app update that uses the iPhone 23 screen.'),
            ('iPhone 23 apps will take time', 'A new report says developers are adapting apps to the iPhone 23 display.'),
            ('iPhone 23应用适配仍需时间', 'Apple公布了一款使用iPhone 23屏幕和相机的应用。'),
            ('iPhone 23 apps will take time', 'A new app for iPhone 23 was released. It reportedly uses the camera to scan documents.'),
        ]:
            self.assertFalse(self.m.is_direct_iphone_hardware_spec_rumor_story(title, text))
        self.assertTrue(self.m.is_direct_iphone_hardware_spec_rumor_story('iPhone 23 details leaked',
            'A new report reveals that iPhone 23 will use a variable aperture camera.'))
        self.assertTrue(self.m.is_direct_iphone_hardware_spec_rumor_story('iPhone 23 camera report',
            'iPhone 23 has a new camera. It reportedly uses a larger sensor.'))

    def test_hardware_disclosure_keeps_its_physical_object(self):
        cases = [
            ('iPhone 23规格报告', '博主公布了iPhone 23的电池容量信息。', True),
            ('iPhone 23包装盒曝光', '疑似iPhone 23包装盒流出，真实性仍存疑。', True),
            ('iPhone 23规格报告', 'Apple is using a revised display stack in its upcoming phone.', True),
            ('iPhone 23规格爆料', '苹果将发布iPhone 23，爆料展示了芯片和调制解调器规格。', True),
            ('iPhone 23规格报告', '博主没有公布iPhone 23的电池容量信息。', False),
            ('iPhone 23包装盒曝光', 'iPhone 23包装盒没有流出。', False),
            ('iPhone 23规格报告', '去年博主公布了iPhone 23的电池容量信息。', False),
            ('iPhone 23规格报告', '博主公布了iPhone 22的电池容量信息。', False),
            ('iPhone 23应用报告', 'Apple is using a camera app in its upcoming phone.', False),
            ('iPhone 23规格报告', 'Orion is using a revised display stack in its upcoming phone.', False),
            ('iPhone 23规格爆料', '苹果将发布iPhone 23，开发者爆料展示了相机应用。', False),
            ('iPhone 23规格爆料', '苹果将发布iPhone 23，爆料展示了相机应用。', False),
            ('iPhone 23配置曝光', '针对iPhone 23，报道披露了Galaxy S30的电池容量。', False),
            ('iPhone 23配置曝光', '开发者展示适配iPhone 23，报道披露了另一款手机的电池容量。', False),
            ('iPhone 23配置曝光', '苹果将发布iPhone 23，报道披露了另一款手机的电池容量。', False),
            ('iPhone 23 display report', 'A competitor of Apple is using a 120Hz display in its new phone.', False),
            ('iPhone 23 display report', 'A supplier of Apple is using a 120Hz display in its new phone.', False),
            ('iPhone 23 display report', 'Apple is using a 120Hz display in its new phone, but the phone is not iPhone 23.', False),
        ]
        for title, text, expected in cases:
            with self.subTest(title=title, text=text):
                self.assertEqual(self.m.is_direct_iphone_hardware_spec_rumor_story(title, text), expected)

    def test_reader_scenarios_do_not_create_required_numeric_predictions(self):
        article = self.source_articles(*self.ids('3d3760'))[0]
        view = self.m.prepare_source_fact_view(article)
        public = '\n'.join(f.text for f in (*view.normal, *view.structured))
        pending = '\n'.join(f.text for f in view.unprocessed)
        for text in ('seems like an eternity', 'Consequently, there will be developers', 'There will be others',
                     'you may well never see', "they'd be in great shape"):
            self.assertNotIn(text, public)
            self.assertIn(text, pending)
        for text in ('until October 8', 'Xcode was updated'):
            self.assertIn(text, public)
        events, serialized = self.cluster_sources(*self.ids('3d3760'))
        reviews = []
        self.m.add_source_remainder_reviews(events,
            {article.evidence.article_id: article.evidence}, reviews, {})
        self.assertIn('coming weeks', str(serialized) + str(reviews))
        for text in (
            'Apple says users may not see the feature until January 2028.',
            'According to Morgan Lee, developers may never release their planned camera app.',
            'If the display is locked, users will not see the private notification text.',
            'If you hold the button, recording will continue at 60fps.',
            'If you enable the privacy option, you may see fewer notifications on iOS 31.2.',
            'If you hold the button, you may record 4K at 60fps.',
        ):
            self.assertNotEqual(self.m.source_fact_statement_role(text), 'editorial')

    def test_official_launch_app_showcase_keeps_the_software_action(self):
        events, output = self.cluster_sources(*self.ids('5a5a1c'))
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))
        article = events[0].articles[0]
        self.assertFalse(self.m.is_third_party_accessory_platform_compatibility_story(
            article.title, article.summary))
        profile = self.m.article_reconciliation_profile(article)
        self.assertIn('source-local-action-authority', profile.separation_keys)
        self.assertIn('next few weeks', '\n'.join(unit.text for unit in article.evidence.units))

    def test_app_showcase_requires_apple_curation_for_the_device_launch(self):
        from apple_news_core.event_identity import source_named_publication_frame, build_event_identity
        title = 'Apple describes developer apps for iPhone 23'
        positive = 'Apple has named apps and games it will highlight on the App Store when the new device goes on sale.'
        frame = source_named_publication_frame(title, positive, (positive,), build_event_identity(title, positive))
        self.assertIsNotNone(frame)
        self.assertEqual(frame.category, 'software_systems')
        for text in [
            'If Apple selected apps to highlight on the App Store when the new device goes on sale, developers would benefit.',
            'Apple has named apps to highlight on the App Store when iPhone 24 goes on sale.',
            'Apple has named apps for iPhone 24. The company will highlight them on the App Store when the new device goes on sale.',
            'Apple has named apps for iPhone 23. Orion announced its own app collection. The company will highlight its apps on the App Store when the new device goes on sale.',
            'Apple has named apps for iPhone 23, but Orion announced its own app collection. The company will highlight its apps on the App Store when the new device goes on sale.',
            'Apple has named apps for iPhone 23. The company will not highlight them on the App Store when the new device goes on sale.',
            'Apple has named apps for iPhone 23. A developer hopes they will be highlighted on the App Store when the new device goes on sale.',
            'Developers say Apple should highlight their apps on the App Store when the new device goes on sale.',
            'Apple has not named apps to highlight on the App Store when the new device goes on sale.',
            'Last year Apple named apps it highlighted on the App Store when the new device went on sale.',
            'Apple says developers are doing incredible work for the larger display.',
        ]:
            self.assertIsNone(source_named_publication_frame(title, text, (text,), build_event_identity(title, text)), text)
        app_title = 'Harbor app adds a new layout for Apple iPhone 23'
        app_lead = 'Harbor has updated its layout. ' + positive
        self.assertIsNone(source_named_publication_frame(app_title, app_lead,
            (app_lead,), build_event_identity(app_title, app_lead)))
        app_event = self.m.cluster_articles([article_for(self.m, app_title, app_lead)])[0]
        self.assertEqual(app_event.relevance_tier, 'weak')
        self.assertTrue(self.m.is_third_party_accessory_platform_compatibility_story(
            'Acme portable monitor supports iPhone 23',
            'Acme launched a portable monitor with USB-C support for iPhone 23 and Mac.'))

    def test_official_app_inventory_and_store_badge_keep_distinct_objects(self):
        ids = self.ids('5a5a1c', '1746467', 'a9e5bdf')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertIn(set(ids[:2]), [self.source_ids(e) for e in events])
            self.assertTrue(all((e.relevance_tier, e.category) == ('strong', 'software_systems') for e in events))
        from apple_news_core.event_identity import source_named_publication_frame, build_event_identity
        title = 'Apple highlights apps for iPhone 23'
        current = 'Apple today highlighted third-party App Store apps optimized for iPhone 23.'
        self.assertIsNotNone(source_named_publication_frame(title, current, (current,), build_event_identity(title, current)))
        for text in (current.replace('today', 'last year'), current.replace('today highlighted', 'has not highlighted'),
                     current.replace('iPhone 23.', 'iPhone 24.'),
                     'Developers hope Apple will highlight their App Store apps for iPhone 23.'):
            self.assertIsNone(source_named_publication_frame(title, text, (text,), build_event_identity(title, text)), text)

    def test_named_store_badge_requires_current_first_party_rollout(self):
        from apple_news_core.event_identity import source_named_publication_frame, build_event_identity
        title = 'Apple labels apps for iPhone 23'
        text = 'Apple is rolling out a new badge in the App Store. The new “Designed for iPhone 23” badge indicates optimized apps.'
        frame = source_named_publication_frame(title, text, (text,), build_event_identity(title, text))
        self.assertIsNotNone(frame)
        self.assertEqual((frame.category, frame.tier), ('software_systems', 'strong'))
        planned = text.replace('is rolling out', 'will roll out')
        future = source_named_publication_frame(title, planned, (planned,), build_event_identity(title, planned))
        self.assertIsNotNone(future)
        self.assertNotEqual(future.action, frame.action)
        expanded = text.replace('indicates optimized apps', 'will appear on more apps tomorrow, and is already visible on launch apps today')
        actual = source_named_publication_frame(title, expanded, (expanded,), build_event_identity(title, expanded))
        self.assertEqual(actual.action, frame.action)
        for bad in (text.replace('is rolling out', 'has not rolled out'), text.replace('is rolling out', 'last year rolled out'),
                    text.replace('Apple is rolling out', 'Developers hope Apple will roll out'),
                    text.replace('Apple is rolling out', 'Orion is rolling out'),
                    text.replace('The new', 'Orion introduced its new'),
                    'Apple discussed app labels, but Orion is rolling out a new “Designed for iPhone 23” badge in the App Store.',
                    'Apple is rolling out a new badge in the App Store, while Orion introduces its “Designed for iPhone 23” badge.',
                    text.replace('indicates optimized apps', 'belongs to Orion, not Apple'),
                    text.replace('indicates optimized apps', 'is only a proposed name, not the official name'),
                    text.replace('indicates optimized apps', 'indicates optimized apps but belongs to Orion, not Apple'),
                    '苹果正在App Store推出新标识。新的“适用于iPhone 23”标识属于Orion，并非苹果。',
                    '苹果正在App Store推出新标识。新的“适用于iPhone 23”标识仅为拟议名称，并非正式名称。'):
            self.assertIsNone(source_named_publication_frame(title, bad, (bad,), build_event_identity(title, bad)), bad)
        self.assertIsNone(source_named_publication_frame('Harbor app introduces a new badge', text,
            (text,), build_event_identity('Harbor app introduces a new badge', text)))

    def test_author_turn_keeps_the_neighboring_reported_operation(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        cases = [
            ('Apple says the camera records 1080p video at 60fps, but we may see 4K support next year.',
             'records 1080p video at 60fps', 'we may see 4K support'),
            ('Apple says the camera records 1080p video at 60fps, we may see 4K support next year.',
             'records 1080p video at 60fps', 'we may see 4K support'),
            ('测试发现摄像头可录制1080p视频，我认为这意味着明年一定会支持4K。',
             '摄像头可录制1080p视频', '我认为'),
            ('The next version is scheduled for release next week. I’m guessing this means the feature will ship in iOS 31.2.',
             'scheduled for release next week', 'I’m guessing'),
            ('It is a great choice, but the camera cannot record 4K video.',
             'the camera cannot record 4K video', 'great choice'),
            ('We may see 8K video next year, and the camera currently supports 4K recording at 60fps.',
             'currently supports 4K recording at 60fps', 'We may see'),
        ]
        for text, reported, interpretation in cases:
            with self.subTest(text=text):
                article = article_for(self.m, 'Apple reports iPhone 23 camera support', text, facts=[text])
                article.evidence = capture_article_title_evidence(article.source, article.url,
                    article.title, text, (text,))
                view = self.m.prepare_source_fact_view(article)
                plan = self.m.resolve_event_fact_plan([view], relevance_tier='strong', base_limit=2, official_limit=2)
                self.assertTrue(any(reported in f.text for f in plan.required))
                self.assertFalse(any(interpretation in f.text for f in plan.required))
                self.assertTrue(any(interpretation in f.text for f in plan.unprocessed))

    def test_unbound_app_qualification_keeps_its_software_object(self):
        for title, summary in (
            ('iDaily：率先支持iPhone Duo折叠屏的新闻杂志应用',
             '著名中文媒体应用“iDaily·每日环球视野”刚刚正式发布为苹果首款折叠机 iPhone Duo 优化的7.0版本，不仅提供 iPhone Duo 内屏横屏的全新沉浸模式，还融合 Liquid Glass 液态界面设计。'),
            ('山川：率先支持iPhone 23的新闻杂志应用',
             '新闻应用“山川·每日阅读”正式发布为iPhone 23优化的8.0版本，支持新的阅读布局。'),
        ):
            event = self.m.cluster_articles([article_for(self.m, title, summary)])[0]
            self.assertEqual((event.relevance_tier, event.category), ('weak', 'software_systems'))

    def test_unprojected_source_remainder_keeps_material_without_retrieval_terms(self):
        for sid in self.ids('4e4f43', '954df7'):
            events, _ = self.cluster_sources(sid)
            evidence = events[0].articles[0].evidence
            reviews, dispositions = [], {}
            self.m.add_source_remainder_reviews(events, {sid: evidence}, reviews, dispositions)
            texts = [part['text'] for review in reviews for part in review['unprocessed_evidence']]
            expected = next(unit.text for unit in evidence.units
                if 'Lower-carbon alternatives' in unit.text or '材料替代' in unit.text)
            self.assertTrue(all(expected[left:right] in texts for left, right
                in self.m.source_sentence_spans(expected)), sid)
            self.assertEqual(len(reviews), 1)
            self.m.add_source_remainder_reviews(events, {sid: evidence}, reviews, dispositions)
            self.assertEqual(texts, [part['text'] for review in reviews
                                    for part in review['unprocessed_evidence']])

    def test_summary_coverage_is_local_and_does_not_consume_a_whole_paragraph(self):
        from types import SimpleNamespace
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, EventFactPlan
        lead = 'The facility now uses renewable electricity.'
        tail = ' The alternative materials still require reliability testing.'
        def evidence(sid):
            return ArticleEvidence(sid, sid, 'https://example.com/' + sid,
                'Facility report', lead, 'news',
                (EvidenceUnit(sid + '-p', 'p', lead + tail, 'html', 0),))
        first, second = evidence('first'), evidence('second')
        plan = EventFactPlan('Facility report', lead, (),
            summary_sources=((first.source, first.url, lead),))
        event = SimpleNamespace(fact_plan=plan, articles=[
            SimpleNamespace(evidence=first), SimpleNamespace(evidence=second)])
        reviews, dispositions = [], {}
        self.m.add_source_remainder_reviews([event],
            {first.article_id: first, second.article_id: second}, reviews, dispositions)
        parts = {row['evidence_id']: [x['text'] for x in row['unprocessed_evidence']]
                 for row in reviews}
        self.assertEqual(parts['first'], [tail.strip()])
        self.assertEqual(parts['second'], [lead, tail.strip()])
        self.assertEqual(dispositions['first']['assigned'], [(first.units[0].unit_id, 0, len(lead))])

    def test_remainder_retains_existing_exclusion_and_review_destinations(self):
        from types import SimpleNamespace
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, EventFactPlan
        evidence = ArticleEvidence('local', 'Local', 'https://example.com/local',
            'Device report', '', 'news', (
                EvidenceUnit('heading', 'h1', 'Device report', 'html', 0),
                EvidenceUnit('body', 'p', 'The observed limit still applies.', 'html', 1),
                EvidenceUnit('ad', 'p', 'A previously excluded promotion.', 'html', 2)))
        reviews = [self.m.evidence_review_item(evidence, [('body', 0, 33)], 'Existing review')]
        dispositions = {'local': {'assigned': [], 'unprocessed': [('body', 0, 33)],
            'excluded': [{'unit_id': 'ad', 'start': 0, 'end': 32, 'reason': 'Promotion'}]}}
        event = SimpleNamespace(fact_plan=EventFactPlan('', '', ()),
            articles=[SimpleNamespace(evidence=evidence)])
        self.m.add_source_remainder_reviews([event], {'local': evidence}, reviews, dispositions)
        self.assertEqual(len(reviews), 1)
        self.assertEqual([p['text'] for p in reviews[0]['unprocessed_evidence']],
                         ['The observed limit still applies.'])
        self.assertTrue(any(p['unit_id'] == 'heading' for p in dispositions['local']['excluded']))

    def test_named_app_object_owns_category_without_a_headline_version(self):
        for sid in self.ids('c335c8', 'aaa9d9', '937ea4'):
            events, _ = self.cluster_sources(sid)
            self.assertEqual([(e.relevance_tier, e.category) for e in events],
                             [('weak', 'software_systems')], sid)
        from apple_news_core.event_identity import source_named_app_frame
        for title, lead in [
            ('Harbor Updated for iPhone 23 With Adaptive Layout',
             'Northstar has updated its task management app Harbor with support for iPhone 23.'),
            ('山川 App 适配苹果首款折叠 iPhone 23，引入双栏体验',
             '山川面向 iPad 和 iPhone 23 推送 4.8.0 版本更新，重新设计应用界面。'),
        ]:
            frame = source_named_app_frame(title, lead)
            self.assertIsNotNone(frame)
            self.assertEqual((frame.tier, frame.category), ('weak', 'software_systems'))
        title = 'Harbor Updated for iPhone 23 With Adaptive Layout'
        for lead in (
            'Northstar updated its Harbor keyboard. Its companion app offers settings.',
            'Northstar updated its task management app Beacon. Harbor supports iPhone 23.',
            'Last year Northstar updated its task management app Harbor for iPhone 23.',
            'Northstar did not update its task management app Harbor for iPhone 23.',
            'Northstar plans to update its task management app Harbor for iPhone 23.',
            'The claim that Northstar has updated its task management app Harbor is false.',
        ):
            self.assertIsNone(source_named_app_frame(title, lead), lead)
        frame = source_named_app_frame(title,
            'Apple has updated its task management app Harbor with support for iPhone 23.')
        self.assertEqual((frame.subject, frame.tier), ('apple-app:harbor', 'strong'))
        for title, lead in (
            ('手机要卖了微信等应用还没适配 iPhone Duo被批 博主：几周内就会解决',
             '评测发现很多应用尚未适配，博主认为后续会解决。'),
            ('山川 App 尚未适配iPhone 23', '山川表示其应用尚未完成iPhone 23适配，计划下月更新界面。'),
            ('山川 App 适配iPhone 23回顾', '去年山川 App 已完成iPhone 23适配，今天没有发布新版本。'),
            ('山川 App 适配iPhone 23', '山川面向iPhone 23计划推送4.8.0版本更新。'),
            ('山川 App 适配iPhone 23', '山川面向iPhone 23，另一应用发布4.8.0版本更新。'),
            ('山川 App 适配iPhone 23', '山川面向iPhone 23推送4.8.0版本更新的消息不实。'),
        ):
            self.assertIsNone(source_named_app_frame(title, lead), lead)

    def test_publisher_category_is_not_a_comparison_target(self):
        from copy import deepcopy
        from apple_news_core.article_processing import extract_title
        sid = self.ids('954df7')[0]
        row = self.rows[sid]
        title = extract_title(row['title_markup'], row['evidence']['discovery_title'])
        self.assertEqual(title, row['evidence']['discovery_title'])
        original = self.rows
        self.rows = deepcopy(original)
        try:
            self.rows[sid]['evidence']['title'] = title
            self.rows[sid]['recorded_extraction'][0] = title
            events, _ = self.cluster_sources(sid)
            self.assertEqual([(e.relevance_tier, e.category) for e in events],
                             [('strong', 'hardware_products')])
        finally:
            self.rows = original

    def test_visible_headline_must_confirm_metadata_prefix(self):
        from apple_news_core.article_processing import extract_title
        for headline in ('供应商减排遭遇挑战', '厂商推出新机挑战苹果',
                         'Apple opens a store - new services included'):
            metadata = headline + ' - Apple - Example News'
            page = ('<meta property="og:title" content="' + metadata + '">'
                    '<meta property="og:site_name" content="Example News">'
                    '<meta property="article:section" content="Apple">'
                    '<h1>' + headline + '</h1>')
            self.assertEqual(extract_title(page, ''), headline)
            self.assertEqual(extract_title(page.replace('<h1>' + headline + '</h1>',
                '<h1>Unrelated heading</h1>'), ''), metadata)
        page = ('<meta property="og:title" content="Apple opens a store - new services included">'
                '<meta property="og:site_name" content="Example News"><h1>Apple opens a store</h1>')
        self.assertEqual(extract_title(page, ''), 'Apple opens a store - new services included')
        page = ('<meta property="og:title" content="Apple changes App Store rules - rollout begins next year - Example News">'
                '<meta property="og:site_name" content="Example News"><h1>Apple changes App Store rules</h1>')
        self.assertIn('rollout begins next year', extract_title(page, ''))

    def test_current_specification_does_not_depend_on_publisher_product_suffix(self):
        sid = self.ids('77fe2a')[0]
        events, values = self.cluster_sources(sid)
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('strong', 'hardware_products')])
        self.assertIn('苹果并未给出明确说明', ' '.join(values[0]['must_include_facts']))
        for title in ('iPhone Duo屏下前摄参数，苹果公布功能',
                      'iPhone Air相机参数，苹果公布功能',
                      'iPhone 23相机参数，苹果公布功能'):
            self.assertTrue(self.m.has_direct_iphone_product_title_subject(title))
        for title in ('An iPhone moment for Android', 'Galaxy competes with iPhone',
                      '手机配件支持iPhone'):
            self.assertFalse(self.m.has_direct_iphone_product_title_subject(title))
        from apple_news_core.event_identity import current_iphone_report_passages
        for model in ('Fold', 'Ultra', 'Pro', 'Max', 'e'):
            current = 'iPhone ' + model + ' has a new camera.'
            other = 'iPhone 23 has a larger battery.'
            self.assertTrue(self.m.has_direct_iphone_product_title_subject('iPhone ' + model))
            self.assertEqual(current_iphone_report_passages('iPhone ' + model + ' camera',
                current + ' ' + other), (current,))

    def test_vendor_neutral_market_report_keeps_late_compact_apple_result(self):
        sid = self.ids('bfe426')[0]
        row = self.rows[sid]
        title, summary, facts = row['recorded_extraction']
        source = self.sources[row['evidence']['source']]
        candidate = self.m.Candidate(source.name, row['evidence']['url'], title, '')
        self.assertTrue(self.m.is_relevant_candidate(candidate, source))
        candidate.summary = summary
        self.assertTrue(self.m.is_relevant_candidate(candidate, source, facts))
        events, values = self.cluster_sources(sid)
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        result = row['evidence']['units'][7]['text']
        self.assertTrue(any(result in f for f in values[0]['must_include_facts']))
        self.assertEqual(self.source_ids(events[0]), {sid})

    def test_market_result_keeps_its_local_research_provider(self):
        from apple_news_core.event_identity import source_market_measurement_frame
        title = '全球PC出货量下滑'
        lead = 'Counterpoint报告显示，2028年第三季度全球PC出货量下降。'
        for passages, provider in [
            (('Omdia数据显示，苹果出货680万台，排名第四。',), 'omdia'),
            (('Gartner公布最新统计。', '苹果出货680万台。'), 'gartner'),
            (('Omdia公布当前报告。', 'Gartner去年未发布报告。', '苹果出货680万台。'), 'omdia'),
            (('Omdia published its report.', 'Gartner did not publish a report.', 'Apple shipped 6.8 million PCs.'), 'omdia'),
            (('苹果出货680万台。',), 'counterpoint'),
            (('Apple shipped 6.8 million PCs, according to Omdia.',), 'omdia'),
            (('Counterpoint reports a decline, while Omdia says Apple shipped 6.8 million PCs.',), 'omdia'),
        ]:
            with self.subTest(passages=passages):
                frame = source_market_measurement_frame(title, lead, passages)
                self.assertIsNotNone(frame)
                self.assertEqual(frame.subject, provider + ':pc-shipments')
                selected = source_market_measurement_frame(title, lead, passages, measurement_passages=(passages[-1],))
                self.assertEqual(selected.subject, frame.subject)
        mixed = ('Omdia reports Apple shipped 6.8 million PCs.', 'Gartner reports Apple shipped 6 million PCs.')
        unresolved = source_market_measurement_frame(title, lead, mixed)
        self.assertIsNotNone(unresolved.bound_claim)
        self.assertTrue(unresolved.bound_claim.review_reason)
        profile = self.m.source_text_profile(title, lead, list(mixed), 'IT之家')
        self.assertIsNotNone(profile.bound_claim)
        self.assertTrue(profile.review_reasons)
        self.assertEqual(profile.eligibility.tier, '')
        self.assertEqual(profile.category_hint, 'hardware_products')
        evidence = self.m.capture_article_title_evidence('IT之家', 'https://example.com/report', title, lead, mixed)
        projections, remainder, excluded = self.m.project_article_evidence(evidence)
        self.assertEqual(len(projections), 1)
        self.assertFalse(self.m.claim_eligibility(projections[0].claim).resolved)
        self.assertTrue(remainder)
        self.m.validate_evidence_dispositions(evidence, projections, remainder, excluded)

    def test_different_market_research_reports_do_not_share_headline_provider(self):
        ids = (self.ids('029987')[0], self.ids('3389ec')[0])
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products' for e in events))
            self.assertEqual({frozenset(self.source_ids(e)) for e in events}, {frozenset([sid]) for sid in ids})

    def test_market_vendor_count_requires_local_owner_and_report_scope(self):
        from apple_news_core.event_identity import source_market_measurement_frame
        title = '全球PC出货量下降：零部件成本上涨'
        lead = 'Omdia最新研究显示，2028年第三季度全球PC出货量下降。'
        for result in ('苹果690万台', 'Apple 6.9 million units'):
            frame = source_market_measurement_frame(title, lead, (result,))
            self.assertIsNotNone(frame, result)
            self.assertEqual((frame.subject, frame.period, frame.year), ('omdia:pc-shipments', 'q3', '2028'))
        for result in ('联想690万台，苹果未公布数据', '此前苹果690万台',
                       '预计苹果690万台', '苹果采购690万台', '苹果690万台服务器',
                       '苹果营收690万美元', '苹果手机出货690万台',
                       '2027年第三季度苹果690万台', '2028年第二季度苹果690万台',
                       '智能手机市场苹果690万台'):
            self.assertIsNone(source_market_measurement_frame(title, lead, (result,)), result)
        for incomplete in ('最新研究显示，2028年第三季度全球PC出货量下降。',
                           'Omdia最新研究显示，全球PC出货量下降。'):
            self.assertIsNone(source_market_measurement_frame(title, incomplete, ('苹果690万台',)))

    def test_custom_vendor_owns_edition_when_headline_omits_customization(self):
        ids = [sid for sid, row in self.rows.items() if '景泰蓝' in row['evidence']['title']]
        self.assertEqual(len(ids), 2)
        for sid in ids:
            events, _ = self.cluster_sources(sid)
            self.assertTrue(all(e.relevance_tier == 'weak' and e.category == 'hardware_products' for e in events))
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
        for title, lead in (
            ('Orion launches a gold iPhone 23 edition', 'Independent custom brand Orion launched a customized iPhone 23 edition with a gold case.'),
            ('金艺社发布金色iPhone 23', '独立定制品牌金艺社推出定制版iPhone 23，替换机身外壳。'),
        ):
            article = article_for(self.m, title, lead, 'IT之家')
            self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'weak')
        for title, lead in (
            ('Apple launches iPhone 23 with a custom chip', 'Apple today launched iPhone 23 with a custom chip.'),
            ('苹果发布iPhone 23', '苹果正式发布iPhone 23，采用定制芯片。'),
            ('iPhone 23 adds a new camera', 'Apple added a new camera to iPhone 23. Last year independent custom brand Orion launched a customized iPhone 23 edition.'),
        ):
            article = article_for(self.m, title, lead, 'IT之家')
            self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'strong')

    def test_unnamed_customizer_plan_keeps_ownership_without_a_launch(self):
        from apple_news_core.event_identity import source_device_customization_frame
        for title, lead in (
            ('A custom iPhone 23 costs a premium', 'An independent designer plans production of a custom case.'),
            ('定制iPhone 23外壳方案曝光', '独立设计师计划制作定制外壳。'),
        ):
            frame = source_device_customization_frame(title, lead)
            self.assertIsNotNone(frame)
            self.assertEqual((frame.tier, frame.action), ('weak', 'independent-modification-plan'))
        for lead in ('独立设计师计划制作定制外壳的消息不实。',
                     'An independent designer plans production of a custom case, but that report is false.'):
            frame = source_device_customization_frame('A custom iPhone 23 case', lead)
            self.assertEqual((frame.tier, frame.action), ('weak', 'independent-modification-denial'))
        self.assertIsNone(source_device_customization_frame('Apple launches iPhone 23',
            'Apple today launched iPhone 23. An independent designer plans production of a custom case.'))

    def test_embedded_platform_function_suspension_owns_only_affected_operation(self):
        sid = self.ids('7f20')[0]
        articles = self.source_articles(sid)
        self.assertEqual(len(articles), 1)
        event = self.m.cluster_articles(articles)[0]
        self.assertEqual((event.category, event.relevance_tier), ('software_systems', 'ecosystem'))
        facts = ' '.join(articles[0].key_facts)
        for phrase in ('全日空航空关闭 Apple Wallet 电子登机牌', '暂未发现被入侵', '预防性措施'):
            self.assertIn(phrase, facts)
        self.assertNotIn('日本航空以系统维护', facts)
        from dataclasses import replace
        from apple_news_core.event_identity import bind_embedded_app_state
        evidence = articles[0].evidence
        unit = next(u for u in evidence.units if '全日空航空关闭' in u.text)
        for text in ('示例航空尚未关闭Apple Wallet电子登机牌功能。',
                     '示例航空关闭普通网站，Apple Wallet电子登机牌功能照常。',
                     '示例航空将关闭Apple Wallet电子登机牌功能。',
                     '示例航空关闭普通网站，使用iPhone的乘客受到影响。',
                     '示例航空关闭Apple Wallet电子登机牌功能的传闻不实。',
                     '用户关闭Apple Wallet通知以免被打扰。'):
            self.assertIsNone(bind_embedded_app_state(replace(evidence, units=(replace(unit, text=text),))), text)
        subjects = []
        for provider, feature in (('示例航空', '电子登机牌'), ('山川航空', '电子登机牌'), ('示例银行', '银行卡')):
            claim = bind_embedded_app_state(replace(evidence, units=(replace(unit,
                text=provider + '关闭Apple Wallet' + feature + '功能。'),)))
            self.assertIsNotNone(claim)
            self.assertIn(provider, claim.subject)
            self.assertIn(feature, claim.subject)
            subjects.append(claim.subject)
        self.assertEqual(len(set(subjects)), 3)

    def test_localized_software_feature_uses_same_operation_identity(self):
        ids = self.ids('223ffc1', '21f6ad')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].category, events[0].relevance_tier), ('software_systems', 'strong'))

    def test_named_review_opening_owns_distinct_measurement_methods(self):
        sid = self.ids('c81ebe')[0]
        articles = self.source_articles(sid)
        self.assertEqual(len(articles), 3)
        by_method = {a.bound_claim.object.split(':')[-1]:a for a in articles}
        self.assertEqual(set(by_method), {'fold-endurance', 'hinge-structure', 'surface-scratch'})
        for method, facts in (('fold-endurance', ('48微米', '167微米', '1.245度', '3000次')),
                              ('hinge-structure', ('CT扫描', '100个零件', '15–165度')),
                              ('surface-scratch', ('指甲', '房卡', '15牛'))):
            text = ' '.join(by_method[method].key_facts)
            for fact in facts: self.assertIn(fact, text)
        for other in ('hinge-structure', 'surface-scratch'):
            self.assertNotIn('3000次', ' '.join(by_method[other].key_facts))
        old = next(a for a in self.source_articles(self.ids('d7f0')[0])
                   if a.bound_claim and a.bound_claim.object == '何同学:fold-endurance')
        for order in ([old, by_method['fold-endurance']], [by_method['fold-endurance'], old]):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 1)
            self.assertEqual(len(events[0].articles), 2)

    def test_official_walkin_statement_groups_its_regional_conditions(self):
        ids = self.ids('2c5940c', 'd536533', 'de14f27', '610c8b2', '0baac0', 'c7f8fc')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertTrue(all(a.bound_claim is not None for a in events[0].articles))

        facts = ' '.join(f for a in self.source_articles(self.ids('c7f8')[0]) for f in a.key_facts)
        for condition in ('法国、中国、中国香港、印度、日本、马来西亚、韩国、台湾、泰国以及阿联酋', '预约到店取货时间'):
            self.assertIn(condition, facts)

    def test_visual_identity_reveal_keeps_website_activation_separate(self):
        ids = self.ids('bc57122', '810881d', '6fc255c', '58f2666', 'aa9ee75', 'da2002a')
        site = self.ids('e9c530e')[0]
        for order in (ids + [site], [site] + ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertIn(set(ids), [self.source_ids(e) for e in events])
            self.assertIn({site}, [self.source_ids(e) for e in events])
            self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_certificate_revocation_is_current_platform_protection(self):
        ids = self.ids('ec8d5b0', '69e2b41')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))

    def test_named_device_software_plan_and_existing_feature_keep_software_category(self):
        ids = self.ids('f1be329', 'bc03f99', '0010d93')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))
        events, _ = self.cluster_sources(*self.ids('223ffc1'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','software_systems')])

    def test_supplier_property_purchase_cannot_borrow_apple_background(self):
        events, _ = self.cluster_sources(*self.ids('5c0e154'))
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_ordinary_app_feature_on_carplay_keeps_third_party_owner(self):
        events, _ = self.cluster_sources(*self.ids('b31fec', '9395a3'))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')

    def test_chinese_named_app_adaptation_keeps_its_software_owner(self):
        for id in self.ids('d8a226', '19151b'):
            events, _ = self.cluster_sources(id)
            self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'software_systems')])
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform
        for name in ('示例导航', '山川地图'):
            self.assertTrue(is_third_party_app_action_on_apple_platform(
                name + '宣布全面适配iPhone 23', name + '已对界面布局进行适配优化。', named_only=True))
        self.assertTrue(is_third_party_app_action_on_apple_platform(
            '示例导航官宣全面适配苹果iPhone 23', '示例导航全面适配iPhone 23，支持横竖屏自动布局。', named_only=True))
        for name, layout in (('山川键盘', '按键布局'), ('示例保护壳', '开孔布局')):
            self.assertFalse(is_third_party_app_action_on_apple_platform(
                name + '官宣适配iPad 23', name + '已更新' + layout + '，适配iPad 23。', named_only=True))
        for name in ('苹果', '苹果地图', 'iOS'):
            self.assertFalse(is_third_party_app_action_on_apple_platform(
                name + '宣布全面适配iPhone 23', name + '已对界面布局进行适配优化。', named_only=True))
        self.assertFalse(is_third_party_app_action_on_apple_platform('示例导航宣布全面适配iPhone 23',
            '示例导航并未对界面布局进行适配优化。', named_only=True))

    def test_app_adaptation_identity_keeps_owner_and_completion_stage(self):
        ids = self.ids('746512', '1db020')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('weak', 'software_systems'))
        pending = self.ids('2a056f')[0]
        events, _ = self.cluster_sources(*ids, pending)
        self.assertEqual(len(events), 2)
        self.assertTrue(all((e.relevance_tier, e.category) == ('weak', 'software_systems') for e in events))
        from apple_news_core.event_identity import source_app_adaptation_frame
        for body in ('Sample用户正在讨论另一款应用的新界面，Other已完成iPhone 23适配。',
                     'Sample去年已完成iPhone 23适配并更新界面。',
                     'Sample已更新界面，计划下月适配iPhone 23。',
                     'Sample已经完成iPhone 24适配并优化软件界面。'):
            with self.subTest(body=body):
                self.assertIsNone(source_app_adaptation_frame('Sample官宣适配iPhone 23', body))

    def test_reported_app_compatibility_keeps_app_owner_and_software_category(self):
        events, _ = self.cluster_sources(*self.ids('7ecac2'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'software_systems')])
        from apple_news_core.event_identity import source_app_adaptation_frame
        title = '厂商称山川应用已适配iPhone 23：后续还会优化'
        body = '当前版本的山川应用已经能够在iPhone 23上正常安装与运行。'
        frame = source_app_adaptation_frame(title, body)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.subject, 'third-party-app:山川应用:iphone-23')
        for body in ('当前版本的另一应用已经能够在iPhone 23上正常安装与运行。',
                     '去年版本的山川应用已经能够在iPhone 23上正常安装与运行。',
                     '当前版本的山川应用尚不能在iPhone 23上正常安装与运行。',
                     '山川应用计划下月能够在iPhone 23上正常安装与运行。',
                     '山川应用可以在iPhone 23上正常安装，但无法运行。',
                     '山川应用可以在iPhone 23上正常安装，另一应用才可以运行。',
                     '山川应用已经能够在iPhone 24上正常安装与运行。'):
            self.assertIsNone(source_app_adaptation_frame(title, body), body)

    def test_product_action_before_colon_owns_the_later_description(self):
        events, _ = self.cluster_sources(*self.ids('cac430'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'hardware_products')])
        for maker in ('星川', 'ExampleCo'):
            title = maker + '新款智能手表外观曝光：采用Apple Watch Ultra式轮廓'
            lead = maker + '产品经理公布新款智能手表外观，具体名称尚未公布。'
            event = self.m.cluster_articles([article_for(self.m, title, lead, 'IT之家')])[0]
            self.assertEqual(event.relevance_tier, 'weak')
        for title in ('记者透露：苹果发布Apple Watch Ultra 9',
                      '新发现：Apple Watch Ultra 9已经上市',
                      '苹果新款手表发布：Apple Watch Ultra 9售价799美元'):
            event = self.m.cluster_articles([article_for(self.m, title,
                '苹果今日正式发布Apple Watch Ultra 9，售价799美元。', 'IT之家')])[0]
            self.assertEqual(event.relevance_tier, 'strong')
        from apple_news_core.event_identity import _headline_subject_clause
        for action in ('苹果正式发布iPhone 23', 'Apple has launched iPhone 23',
                       'Apple Watch Ultra 9正式上市'):
            title = '星川新款手机发布：' + action
            self.assertIn(action.lower(), _headline_subject_clause(title))

    def test_display_rate_conflicts_remain_facts_of_the_same_device_report(self):
        ids = self.ids('f1c61', '16100')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            facts = ' '.join(f for a in events[0].articles for f in a.key_facts)
            for value in ('60Hz', '120Hz', 'A20 Pro', 'A19 Pro', '8.7英寸', '8.5英寸'):
                self.assertIn(value, facts)

    def test_order_target_revision_binds_whole_device_quantity_and_period(self):
        ids = self.ids('9f3d25', '3a44ee', '859cf3')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
        from apple_news_core.event_identity import source_market_report_frame
        title = 'Apple boosts iPhone 23 orders'
        lead = 'Apple raised its iPhone 23 shipment target from 9.7 million to 14 million devices for the next 12 months.'
        base = source_market_report_frame(title, lead, ())
        for old, new in (('14 million', '15 million'), ('12 months', '24 months'),
                         ('devices', 'display panels'), ('iPhone 23', 'iPhone 24')):
            with self.subTest(change=(old, new)):
                self.assertNotEqual(base, source_market_report_frame(title.replace(old,new), lead.replace(old,new), ()))
        for prefix in ('Last year, ', 'Apple denied that '):
            self.assertNotEqual(base, source_market_report_frame(title, prefix + lead, ()))
        self.assertNotEqual(base, source_market_report_frame(title, 'Apple increased iPhone 23 orders.',
            ('Samsung raised its shipment target from 9.7 million to 14 million devices for the next 12 months.',)))
        self.assertNotEqual(base, source_market_report_frame(title, 'Apple increased iPhone 23 orders.',
            ('Samsung received instructions to increase Galaxy S26 orders from 9.7 million to 14 million devices for the next 12 months.',)))
        for verb in ('提升', '提高', '上调', '增加', '调整', '降低', '降', '减少'):
            statement = f'苹果将iPhone 23未来12个月出货目标从最开始原定的970万部直接{verb}至1400万部。'
            if verb in ('降低', '降', '减少'):
                statement = statement.replace('970万部', '1800万部')
            positive = source_market_report_frame(title, statement, ())
            self.assertIsNotNone(positive)
            self.assertIn(':assembly-orders:from-', positive.subject)
            self.assertNotEqual(positive, source_market_report_frame(title, statement.replace('苹果将', '苹果并未将'), ()))
        current = '苹果将iPhone 23未来12个月出货目标从970万部提升至1400万部。'
        self.assertEqual(base, source_market_report_frame(title, '苹果否认了有关Mac库存的报道。' + current, ()))
        from apple_news_core.event_identity import source_denies_action
        for transition in ('但', '而', '，但', '，而'):
            self.assertFalse(source_denies_action('', '苹果并未将iPhone 23加入旧计划' + transition + '提升了新计划。', '提升'))
            self.assertEqual(base, source_market_report_frame(title,
                '苹果并未将iPhone 23订单上调' + transition + current, ()))
        component = source_market_report_frame('Apple cuts iPhone 23 component orders',
            'Apple reduced component orders for iPhone 23, which sold 14 million devices.', ())
        self.assertEqual(component.subject, 'iphone-23:component-orders')

    def test_reported_order_revision_keeps_its_coordinated_apple_subject(self):
        ids = self.ids('9f3d25', '3a44ee', '859cf3', 'd61ba8', '2dcdb7')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_order_revision_inherits_only_the_same_sentence_actor(self):
        from apple_news_core.event_identity import source_market_report_frame
        title = 'Apple boosts iPhone 23 orders'
        lead = 'Apple increased iPhone 23 orders.'
        revision = 'has boosted its shipment targets from 8 million to 11 million units over the first 12 months.'
        base = source_market_report_frame(title,
            'Apple raised its iPhone 23 shipment target from 8 million to 11 million devices for the next 12 months.', ())
        for prior, connector in (
            ('The report indicates that Apple expects strong demand for iPhone 23', ', and '),
            ('Apple expects strong demand for iPhone 23', ', and '),
            ('Apple did not raise its iPhone 23 orders this morning', ', but now '),
        ):
            # A denial belongs to its own predicate, not the following current revision.
            self.assertEqual(base, source_market_report_frame(title, lead, (lead, prior + connector + revision)))
        for text in (
            'Apple expects strong demand for iPhone 23, and Samsung ' + revision,
            "Apple's supplier expects strong demand for iPhone 23, and " + revision,
            'Apple supplier Orion expects strong demand for iPhone 23, and ' + revision,
            "Apple's rival expects strong demand for iPhone 23, and " + revision,
            'Apple expects strong demand for iPhone 23. The company ' + revision,
            'Last year Apple expected strong demand for iPhone 23, and ' + revision,
            'If Apple expected strong demand for iPhone 23, it could boost its shipment targets from 8 million to 11 million units over the first 12 months.',
            'Apple expects strong demand for iPhone 23, and has not boosted its shipment targets from 8 million to 11 million units over the first 12 months.',
        ):
            with self.subTest(text=text):
                self.assertNotEqual(base, source_market_report_frame(title, lead, (lead, text)))

    def test_device_tradein_estimate_is_not_an_official_price_change(self):
        events, _ = self.cluster_sources(*self.ids('1471a0'))
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_version_feature_inventory_survives_hands_on_framing(self):
        events, _ = self.cluster_sources(*self.ids('2fc4102'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','software_systems')])

    def test_attributed_thermal_measurements_do_not_bridge_reviewers(self):
        ids = self.ids('d197a3', '0ff1cb')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 3)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
            self.assertEqual({a.bound_claim.object for e in events for a in e.articles},
                {'mrwhosetheboss:stress', 'htx-studio:gaming', 'tom-s-guide:benchmark-heat'})
            groups = [self.source_ids(e) for e in events]
            self.assertEqual(groups.count(set(ids)), 2)
            self.assertEqual(groups.count({ids[0]}), 1)

    def test_comparison_model_and_test_result_do_not_redefine_test_method(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        for comparison in ('Galaxy Z Fold', 'Galaxy Z Fold8', 'an unfolded device'):
            claims = bind_attributed_device_tests(self.evidence('iPhone Duo heat tests',
                f"Review Lab did a benchmark heat test of iPhone Duo against {comparison}.",
                'The iPhone Duo scored 75.9 percent stability on the stress test.'))
            self.assertEqual([c.object for c in claims], ['review-lab:benchmark-heat'])

    def test_same_fingerprint_unlock_operation_merges_across_reprints(self):
        ids = self.ids('c600f1', 'adf2ca', '7f424b')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong','hardware_products'))

    def test_unlock_identity_requires_current_owned_operation(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPhone 23 Touch ID unlocking report'
        operation = ('iPhone 23 Touch ID pauses on the Lock Screen. '
                     'If you keep your finger there, it continues to the Home Screen.')
        frame = source_device_operation_frame(title, operation)
        self.assertEqual(frame.subject, 'iphone-23:fingerprint-hold-to-unlock')
        for heading in ('How to use Touch ID to unlock iPhone 23', 'Should you buy iPhone 23 for Touch ID?'):
            frame = source_device_operation_frame(heading, operation)
            self.assertFalse(frame and frame.subject.endswith(':fingerprint-hold-to-unlock'))
        for text in (operation.replace('iPhone 23', 'iPhone 22'),
                     'Last year, ' + operation,
                     operation.replace('pauses', 'will pause'),
                     operation.replace('pauses', 'does not pause'),
                     operation.replace('Home Screen', 'camera'),
                     operation.replace('continues', 'does not continue'),
                     operation.replace('If you', 'On iPad mini, if you'),
                     operation.replace('If you keep your finger there, it continues', 'You must continue swiping upward to reach'),
                     operation.replace('iPhone 23 ', '')):
            with self.subTest(text=text):
                frame = source_device_operation_frame(title, text)
                self.assertFalse(frame and frame.subject.endswith(':fingerprint-hold-to-unlock'))
        frame = source_device_operation_frame(title, 'iPhone 23 uses Touch ID.',
            source_units=('iPhone 23 uses Touch ID.', operation.replace('iPhone 23', 'iPad mini')))
        self.assertFalse(frame and frame.subject.endswith(':fingerprint-hold-to-unlock'))

    def test_hinge_endurance_and_reverse_bending_keep_test_methods(self):
        ids = self.ids('b371a2', '94b3e8', '944aa5', '855340')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 3)
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        self.assertIn({ids[0],ids[1],ids[3]}, [self.source_ids(e) for e in events])
        self.assertIn({ids[0],ids[2]}, [self.source_ids(e) for e in events])

    def test_new_review_roundup_keeps_observer_across_the_result_sentence(self):
        ids = self.ids('d7f0', '944aa5', 'b371a2')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            new = [e for e in events if ids[0] in self.source_ids(e)]
            self.assertEqual(len(new), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in new))
            self.assertIn(set(ids), [self.source_ids(e) for e in new])
            self.assertIn({ids[0]}, [self.source_ids(e) for e in new])

    def test_pending_observer_requires_an_adjacent_observed_result(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        for paragraphs in (
            ('博主何同学发布了iPhone Duo测试预告。', '他将完成3000次折叠测试。'),
            ('博主何同学发布了iPhone Duo视频。', '另一家实验室接手了评测工作。', '测试完成了3000次折叠。'),
        ):
            self.assertIsNone(bind_attributed_device_tests(self.evidence('iPhone Duo折叠测试', *paragraphs)))

    def test_review_attribution_ends_when_the_experimenter_changes(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        title = '博主何同学：iPhone Duo深度评测'
        opening = '博主何同学发布了iPhone Duo深度评测。'
        for intervening in (
            ('另一家实验室接手了评测工作。',),
            ('博主王同学发布了iPhone Duo评测。', '另一家实验室接手了评测工作。'),
            ('博主王同学发布了iPhone Duo评测。', '视频介绍了设备外观。'),
        ):
            with self.subTest(intervening=intervening):
                self.assertIsNone(bind_attributed_device_tests(self.evidence(
                    title, opening, *intervening, '测试完成了3000次折叠。')))
        local = bind_attributed_device_tests(self.evidence(title, opening,
            '博主王同学发布了iPhone Duo评测。', '测试完成了3000次折叠。'))
        self.assertEqual([c.object for c in local], ['王同学:fold-endurance'])

    def test_simultaneous_store_incidents_keep_distinct_facilities(self):
        ids = self.ids('b22c85', '86579f', '3dbceb')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
            self.assertTrue(all(self.source_ids(e) == set(ids) for e in events))

    def test_arcade_sports_updates_keep_each_named_work(self):
        events, _ = self.cluster_sources(*self.ids('bc4eb7'))
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        texts = [' '.join(f for a in e.articles for f in a.key_facts) for e in events]
        self.assertEqual(sum('November 5' in t for t in texts), 1)

    def test_finale_release_and_next_season_trailer_are_distinct(self):
        events, _ = self.cluster_sources(*self.ids('ad9bef'))
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def evidence(self, title, *paragraphs):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        return ArticleEvidence('boundary', 'MacRumors', 'https://example.com/boundary',
            title, paragraphs[0], 'news', tuple(EvidenceUnit(str(i),'p',text,'body',i)
            for i,text in enumerate(paragraphs)))

    def test_planned_historical_and_other_device_tests_do_not_become_measurements(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        for paragraph in (
            'Review Lab will test iPhone Duo in a 30-minute gaming test.',
            'Review Lab did a 30-minute gaming test of iPhone Duo last year.',
            'Review Lab did a 30-minute gaming test of Galaxy Z Fold8. It reached 46°C.',
            'Review Lab did not test iPhone Duo in a 30-minute gaming test.',
        ):
            with self.subTest(paragraph=paragraph):
                self.assertIsNone(bind_attributed_device_tests(self.evidence('iPhone Duo heat tests',paragraph)))

    def test_distinct_test_durations_cannot_match_on_a_shared_temperature(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        from apple_news_core.event_matcher import identity_pair_decision
        claims=[bind_attributed_device_tests(self.evidence('iPhone Duo gaming tests',
            f'Review Lab did a {minutes}-minute gaming test with iPhone Duo. It reached 46°C.'))[0]
            for minutes in (20,30)]
        self.assertNotEqual(identity_pair_decision(*claims),'match')

    def test_store_city_and_incident_date_boundaries_use_local_assertions(self):
        from apple_news_core.event_identity import bind_store_incidents
        from apple_news_core.event_matcher import identity_pair_decision
        claims=bind_store_incidents(self.evidence('Apple stores looted in two cities',
            'Apple stores in Boston and York were looted on October 18, 2026.',
            'The Apple store in Boston was previously looted in 2018.'))
        self.assertEqual(len(claims),2)
        self.assertEqual(identity_pair_decision(*claims),'conflict')
        later=bind_store_incidents(self.evidence('Apple store looted in Boston',
            'Apple stores in Boston were looted on October 19, 2026.'))[0]
        boston=next(c for c in claims if c.subject.endswith('boston'))
        self.assertEqual(identity_pair_decision(boston,later),'conflict')

    def test_certificate_authorities_and_software_plan_negation_remain_distinct(self):
        from apple_news_core.event_identity import source_software_capability_frame
        for title,lead in (
            ('Apple will not add Reachability to iPhone 19', 'Apple will not add the accessibility software feature to iPhone 19.'),
            ('Last year Apple blocked certificates', 'Apple blocked certificates issued by certificate authority Example last year.'),
        ):
            self.assertIsNone(source_software_capability_frame(title,lead,()))
        articles=[article_for(self.m,'Apple blocks certificates from '+authority,
            'Apple revoked certificates issued by certificate authority '+authority+' on iOS today.')
            for authority in ('AlphaTrust','BetaTrust')]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_actual_carplay_platform_api_does_not_become_ordinary_app_update(self):
        article=article_for(self.m,'Apple adds a new CarPlay API for navigation apps',
            'Apple released a new CarPlay API that allows navigation apps to draw turn guidance in the instrument cluster.')
        self.assertEqual(self.m.article_reconciliation_profile(article).relevance_tier,'strong')

    def test_compound_feed_summary_is_retained_for_detail_projection(self):
        title='Apple stores looted in two cities'
        lead='Apple stores in Boston and York were looted.'
        profile=self.m.source_text_profile(title,lead,[],'AppleInsider')
        self.assertFalse(profile.eligibility.resolved)
        source=self.sources['AppleInsider']
        self.assertTrue(self.m.is_relevant_candidate(self.m.Candidate('AppleInsider','https://example.com/two',title,lead,''),source))

    def test_competing_content_and_denied_trailers_do_not_borrow_apple(self):
        from apple_news_core.event_identity import bind_content_updates
        e=self.evidence('River Town season 6 finale and new trailer',
            'The River Town season 6 finale is available now on Netflix. Plus, Netflix has debuted the first trailer for season 7.')
        self.assertIsNone(bind_content_updates(e))
        e=self.evidence('River Town season 6 finale and new trailer',
            'The River Town season 6 finale is available now on Apple TV. Apple has not debuted the first trailer for season 7.')
        self.assertEqual([c.action for c in bind_content_updates(e)],['content-release'])

    def test_other_store_cannot_borrow_apples_incident_or_date(self):
        from apple_news_core.event_identity import bind_store_incidents
        e=self.evidence('Apple stores and local looting',
            'Samsung stores in Boston were looted, while Apple stores remained open.')
        self.assertTrue(all(not c.subject_relation for c in bind_store_incidents(e)))
        e=self.evidence('Apple stores looted in Boston',
            'Apple stores in Boston were looted.',
            'A jewelry store was looted on October 18, 2026.')
        self.assertFalse(bind_store_incidents(e)[0].qualifiers)

    def test_observer_reuse_does_not_merge_separate_experiments(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        from apple_news_core.event_matcher import identity_pair_decision
        first='Review Lab did a 20-minute gaming test with iPhone Duo. It reached 46°C.'
        second='Review Lab did a 30-minute gaming test with iPhone Duo. It reached 48°C.'
        claims=bind_attributed_device_tests(self.evidence('iPhone Duo gaming tests',first,second))
        self.assertEqual(len(claims),2)
        other=bind_attributed_device_tests(self.evidence('iPhone Duo gaming tests',second.replace('30-minute','20-minute')))[0]
        self.assertNotEqual(identity_pair_decision(claims[0],other),'match')
        historical=bind_attributed_device_tests(self.evidence('iPhone Duo gaming tests',first,
            'The iPhone Duo reached 50°C last year.'))[0]
        self.assertNotIn('50:c',[q[2] for q in historical.qualifiers])

    def test_trailer_work_and_history_remain_local(self):
        from apple_news_core.event_identity import bind_content_updates
        for extra, expected in (
            ('Apple has debuted the first trailer for Harbor Road season 7.', 'harbor-road'),
            ('Last year, Apple debuted the first trailer for season 7.', None),
        ):
            claims=bind_content_updates(self.evidence('River Town finale and trailers',
                'The River Town season 6 finale is available now on Apple TV.', extra))
            trailers=[c for c in claims if c.action=='trailer-release']
            self.assertEqual([c.subject for c in trailers],[expected] if expected else [])

    def test_threatened_store_incident_is_not_an_observed_attack(self):
        from apple_news_core.event_identity import bind_store_incidents
        claims=bind_store_incidents(self.evidence('Apple stores may be looted',
            'Police warned that Apple stores in Boston could be looted on October 18, 2026.'))
        self.assertTrue(all(not c.subject_relation for c in claims))

    def test_shared_instrument_cannot_identify_independent_test_results(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        from apple_news_core.event_matcher import identity_pair_decision
        claims=[bind_attributed_device_tests(self.evidence('iPhone Duo reverse-bend test',
            'Review Lab did a reverse-bend test of iPhone Duo with a calibrated push-pull gauge.',
            f'The test reached {force}kgf.'))[0] for force in (12,18)]
        self.assertNotEqual(identity_pair_decision(*claims),'match')

    def test_local_observations_and_retail_preparation_keep_qualified_actions(self):
        for prefix,category in [('d9472','hardware_products'),('92b88','hardware_products'),
                                ('74370','software_systems'),('e23bc','hardware_products')]:
            with self.subTest(source=prefix):
                events,_=self.cluster_sources(*self.ids(prefix))
                self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong',category)])
        articles=self.source_articles(self.ids('d9472')[0])
        self.assertTrue(any('34 token/s' in fact for a in articles for fact in a.key_facts))
        articles=self.source_articles(self.ids('74370')[0])
        self.assertTrue(any('陀螺仪' in fact for a in articles for fact in a.key_facts))
        self.assertTrue(any('不能安装iPad' in fact for a in articles for fact in a.key_facts))

    def test_workload_subject_and_observation_continuations_do_not_borrow_context(self):
        from apple_news_core.event_identity import bind_device_measurement, bind_device_capability_inventory, bind_attributed_device_tests
        e=self.evidence('Mac Studio local model performance',
            'Mac Studio并未运行模型，推理和任务执行都留在了另一台Linux电脑上。',
            '我们使用 DeepSeek V4 Flash 跑了一个图形，平均输出速度在 34 token/s。')
        self.assertIsNone(bind_device_measurement(e))
        e=self.evidence('iPhone Duo App适配实测',
            '记者实测了iPhone Duo的日常使用体验。',
            '去年Galaxy的拍摄软件连陀螺仪都会错乱，画面方向完全颠倒。')
        self.assertIsNone(bind_device_capability_inventory(e))
        e=self.evidence('iPhone Duo指纹测试',
            '记者正在测试iPhone Duo内屏。',
            '去年团队对Galaxy屏幕用原子力显微镜做纳米形貌检测，检测了指纹污渍。')
        self.assertIsNone(bind_attributed_device_tests(e))

    def test_retail_preparation_uses_operation_location(self):
        from apple_news_core.event_identity import source_retail_operation_frame
        lead='Apple has begun setting up several large structures at its Sanlitun store in Beijing.'
        frame=source_retail_operation_frame('New installations at Apple Fifth Avenue',lead,(lead,))
        self.assertEqual(frame.subject,'apple-store:sanlitun')

    def test_list_observation_uses_the_same_evidence_domain(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_attributed_device_tests
        e = self.evidence('iPhone Duo指纹测试', '记者正在测试iPhone Duo内屏。',
                          '原子力显微镜显示纹理凹凸起伏很大。')
        e = replace(e, units=(e.units[0], replace(e.units[1], kind='li')))
        claim = bind_attributed_device_tests(e)[0]
        self.assertIn(e.units[1].unit_id, claim.unit_ids)

    def test_local_model_measurements_need_the_same_observation(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_device_measurement
        from apple_news_core.event_matcher import identity_pair_decision
        def claim(rate=34, memory=256, task='一个图形', source='MacRumors'):
            e = self.evidence('Mac Studio local model performance',
                f'Mac Studio配备{memory}GB内存。', '模型推理和任务执行留在了这台Mac Studio。',
                f'我们使用 DeepSeek V4 Flash 跑了{task}，平均输出速度在 {rate} token/s。')
            return bind_device_measurement(replace(e, source=source))
        original = claim()
        self.assertEqual(identity_pair_decision(original, claim()), 'match')
        for other in (claim(rate=50), claim(memory=128), claim(task='一段代码'), claim(source='IT之家')):
            with self.subTest(other=other):
                self.assertNotEqual(identity_pair_decision(original, other), 'match')

    def test_distinct_claims_sharing_titles_have_unique_stable_event_ids(self):
        for prefixes in (('b22c85', '86579f', '3dbceb'), ('bc4eb7',)):
            ids = self.ids(*prefixes)
            forward, _ = self.cluster_sources(*ids)
            reverse, _ = self.cluster_sources(*ids[::-1])
            self.assertEqual(len({e.event_id for e in forward}), len(forward))
            self.assertEqual({e.event_id for e in forward}, {e.event_id for e in reverse})

    def test_new_court_remedy_does_not_merge_with_other_case_discovery(self):
        ids = self.ids('879be5', '77eb', '337cd8', 'fcab4', '53e82b')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
            self.assertIn(set(ids[:4]), [self.source_ids(e) for e in events])
        articles = self.source_articles(ids[0])
        text = ' '.join(f for a in articles for f in a.key_facts)
        self.assertIn('March 1, 2027', text)
        self.assertNotIn("EU's DMA", text)
        text = ' '.join(f for a in self.source_articles(ids[1]) for f in a.key_facts)
        for fact in ('Provide access to developer tools', 'Restrict fees and other barriers',
                     'receiving a written application', 'subsequent hearings', 'request a stay and appeal'):
            self.assertIn(fact, text)
        text = ' '.join(f for a in self.source_articles(ids[2]) for f in a.key_facts)
        for fact in ('开放开发者工具', '限制费用与壁垒', '书面申请', '后续救济程序', '暂停执行判决'):
            self.assertIn(fact, text)

    def test_purchase_suitability_cannot_borrow_repair_price_background(self):
        events, _ = self.cluster_sources(*self.ids('fa23'))
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_retail_display_preparation_groups_translated_reports(self):
        ids = self.ids('e23bc', 'cd8cd6')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_annual_category_forecast_gets_details_then_preserves_forecast_role(self):
        from apple_news_core.collection import market_summary_needs_detail
        ids = self.ids('32bc', 'fe1a')
        self.assertTrue(market_summary_needs_detail(self.rows[ids[0]]['evidence']['title']))
        self.assertFalse(market_summary_needs_detail('2026年智能手机选购指南：预计出货增长'))
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertTrue(all(a.bound_claim.action == 'market-forecast-report' for a in events[0].articles))
        facts = ' '.join(f for e in events for a in e.articles for f in a.key_facts)
        for fact in ('14:10', '66%', 'Galaxy Fold8'):
            self.assertIn(fact, facts)

    def test_mixed_review_retains_local_operations_and_measured_tests(self):
        events, _ = self.cluster_sources(*self.ids('bef8'))
        self.assertEqual(len(events), 4)
        self.assertEqual(sum(e.category == 'software_systems' for e in events), 1)
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        facts = ' '.join(f for e in events for a in e.articles for f in a.key_facts)
        for fact in ('SDK', '45W', '60 帧', '缝隙', '智能拍摄', '自动按快门', '无需联网', '左边缘内移'):
            self.assertIn(fact, facts)
        self.assertNotIn('早在 2011 年', facts)

    def test_review_predicates_require_current_owned_observations(self):
        from apple_news_core.event_identity import bind_device_review_observations
        for text in (
            '去年我们在实测中发现：iPhone Duo 采用快充协议，输入功率 45W。',
            '我们计划实测 iPhone Duo 的快充，预计输入功率 45W。',
            '我们并未实测 iPhone Duo 的快充，理论功率 45W。',
            '我们实测了 Galaxy 的快充，输入功率 45W。',
        ):
            self.assertIsNone(bind_device_review_observations(self.evidence('我们用了一周的 iPhone Duo', text)))

    def test_legal_obligations_and_forecasts_keep_their_actual_parties(self):
        from apple_news_core.event_identity import bind_court_remedy, bind_market_forecast
        from apple_news_core.event_matcher import identity_pair_decision
        e = self.evidence('Apple App Store court order',
            'Apple has been ordered by the Federal Court of Australia to allow alternative App Stores.',
            'Google must pay a fine of $25 million.',
            'Apple must allow alternative payment methods.')
        claim = bind_court_remedy(e)
        self.assertEqual(claim.unit_ids, ('0', '2'))
        claims = [bind_market_forecast(self.evidence('Foldable display shipments forecast',
            f'{provider}预计，随着苹果推出折叠手机，2026年全球折叠手机显示屏出货量有望达到2900万片。'))
            for provider in ('Omdia', 'DSCC')]
        self.assertNotEqual(identity_pair_decision(*claims), 'match')

    def test_court_command_binds_the_named_recipient(self):
        from apple_news_core.event_identity import bind_court_remedy
        title = 'App Store 第三方应用商店整改要求'
        opening = '澳大利亚联邦法院对苹果作出一系列反垄断整改要求，责令其允许第三方应用商店进入iOS生态。'
        self.assertEqual(bind_court_remedy(self.evidence(title, opening)).subject, 'apple-app-store:australia')
        for text in (opening.replace('苹果', '谷歌'), '去年，'+opening,
                     opening.replace('作出', '没有作出'), opening.replace('作出', '计划作出')):
            with self.subTest(text=text):
                claim = bind_court_remedy(self.evidence(title, text))
                self.assertTrue(claim is None or claim.review_reason)

    def test_native_transfer_expansion_retains_current_models_and_conditions(self):
        events, _ = self.cluster_sources(*self.ids('f492'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('ecosystem','software_systems')])
        facts = ' '.join(f for e in events for a in e.articles for f in a.key_facts)
        for fact in ('One UI 9', 'Galaxy A56', 'Galaxy A57', 'AirDrop', '可被发现', 'Galaxy S26'):
            self.assertIn(fact, facts)

    def test_native_transfer_rollout_requires_owned_current_support(self):
        from apple_news_core.event_identity import bind_interoperability_report
        from apple_news_core.event_matcher import identity_pair_decision
        title = 'Galaxy A61 的原生跨平台传输扩展'
        opening = '三星下放 Quick Share 跨平台分享功能，Galaxy A61 升级 One UI 12 后可以直接向 iPhone 发送文件。'
        protocol = 'Quick Share 兼容苹果 AirDrop 协议。'
        claim = bind_interoperability_report(self.evidence(title, opening, protocol))
        self.assertIsNotNone(claim)
        for text in (opening.replace('A61', 'A62'), opening.replace('12', '13')):
            other = bind_interoperability_report(self.evidence(title, text, protocol))
            self.assertNotEqual(identity_pair_decision(claim, other), 'match')
        for text in ('去年，'+opening, opening.replace('下放', '计划下放'), opening.replace('下放', '没有下放'),
                     opening.replace('三星下放 Quick Share', '第三方应用新增 Quick Share'),
                     opening.replace('向 iPhone', '向 Windows')):
            with self.subTest(text=text):
                claim = bind_interoperability_report(self.evidence(title, text, protocol))
                self.assertTrue(claim is None or claim.review_reason)
        self.assertTrue(bind_interoperability_report(self.evidence('如何使用 Quick Share 向 iPhone 传输文件', opening, protocol)).review_reason)

    def test_unresolved_migrated_reports_do_not_reenter_legacy_profiles(self):
        from unittest.mock import patch
        evidence = [self.evidence('法院要求苹果 App Store 开放第三方应用商店',
            '澳大利亚联邦法院的整改要求涉及苹果和其他平台，具体受命方仍不明确。'),
            self.evidence('Quick Share 的平台传输支持',
                '三星计划下放 Quick Share 功能，Galaxy A61 升级 One UI 12 后可以向 iPhone 传文件。',
                'Quick Share 使用 AirDrop 协议。'),
            self.evidence('iPhone 23 门店现货安排',
                '苹果表示现场库存十分有限，但并未说明这是哪一款机型。')]
        with patch.object(self.m, 'legacy_article_reconciliation_profile', side_effect=AssertionError('legacy reentry')):
            for e in evidence:
                with self.subTest(title=e.title):
                    a = self.m.Article('MacRumors', 'https://example.test/report', e.title, e.raw_lead, [], '',
                        datetime(2026, 10, 22, tzinfo=timezone.utc), '', '', 'high', set(), evidence=e)
                    p = self.m.article_reconciliation_profile(a)
                    self.assertTrue(p.bound_claim.review_reason)
                    self.assertFalse(p.trusted_direct_action)

    def test_official_inventory_requires_local_current_attribution(self):
        from apple_news_core.event_identity import bind_official_walkin_statement
        title = 'iPhone 23 in-store inventory'
        for paragraphs in (
            ('Last year, Apple said that iPhone 22 had limited stock.',
             'A reporter expects limited iPhone 23 in-store inventory.'),
            ('Apple said iPhone 23 in-store stock is not limited.',),
            ('Apple said employees were instructed to warn customers about limited iPhone 23 in-store stock.',),
        ):
            with self.subTest(paragraphs=paragraphs):
                claim = bind_official_walkin_statement(self.evidence(title,*paragraphs))
                self.assertTrue(claim is None or claim.review_reason)

    def test_inventory_scope_does_not_own_other_retail_operations(self):
        from apple_news_core.event_identity import bind_official_walkin_statement
        for title, paragraphs in (
            ('Apple raises iPhone 23 retail prices', ('Apple said it raised iPhone 23 retail prices.',)),
            ('Apple changes store opening hours', ('Apple said its retail stores now open at 9am.',)),
            ('Apple raises iPhone 23 retail prices', ('Apple said it raised iPhone 23 retail prices.',
                'Last year, Apple said iPhone 23 in-store inventory was limited.')),
        ):
            with self.subTest(title=title, paragraphs=paragraphs):
                self.assertIsNone(bind_official_walkin_statement(self.evidence(title, *paragraphs)))
        for title, paragraph in (
            ('Apple store update', 'Apple said in-store inventory is limited but did not identify the model.'),
            ('Apple store update', 'Apple said iPhone 23 and iPhone 24 in-store inventory is limited.'),
        ):
            with self.subTest(paragraph=paragraph):
                claim = bind_official_walkin_statement(self.evidence(title, paragraph))
                self.assertIsNotNone(claim)
                self.assertTrue(claim.review_reason)

    def test_possessive_court_and_competing_stores_keep_the_existing_order(self):
        ids = self.ids('fcab4', '476211')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
        a = self.source_articles(ids[1])[0]
        remaining, _ = self.m.source_evidence_remainder(a.evidence, a.bound_claim.evidence_spans)
        units = {u.unit_id:u.text for u in a.evidence.units}
        covered = ' '.join(a.key_facts) + ' ' + ' '.join(units[k][start:end] for k,start,end in remaining)
        for fact in ('Apple Account', 'worldwide', 'noon Melbourne', 'February 1', 'May 3', 'appeal'):
            self.assertIn(fact, covered)

    def test_multi_observer_review_reuses_current_device_ownership(self):
        ids = self.ids('b7b011', '944aa5')
        articles = self.source_articles(ids[0])
        self.assertTrue(all(a.bound_claim for a in articles))
        folded = [a for a in articles if a.bound_claim.object.endswith(':fold-endurance')]
        self.assertEqual(len(folded), 1)
        self.assertNotIn('头发', ' '.join(folded[0].key_facts))
        self.assertIn('1000', ' '.join(folded[0].key_facts))
        events, _ = self.cluster_sources(*ids)
        self.assertTrue(any(self.source_ids(e) == set(ids) for e in events))
        from apple_news_core.event_identity import current_device_observation_spans
        e = self.evidence('iPhone Horizon review', 'The iPhone Horizon is being reviewed.',
            'This is compared with iPhone 23.', 'Example Lab used a fold test on Horizon and completed 1000 folds.')
        spans = list(current_device_observation_spans(e, 'iphone-horizon'))
        self.assertIn(e.units[-1].unit_id, {k for k,_,_ in spans})
        e = self.evidence('iPhone Air review', 'The iPhone Air is being reviewed.',
            'The Windows PC was tested.', 'Cooling air reached 20 degrees.')
        self.assertNotIn(e.units[-1].unit_id, {k for k,_,_ in current_device_observation_spans(e, 'iphone-air')})

    def test_retail_queue_copies_share_the_observation_not_official_inventory(self):
        ids = self.ids('363d85', '7235ce')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertTrue(all(a.bound_claim.action == 'retail-queue-observation' for a in events[0].articles))
        from dataclasses import replace
        from apple_news_core.event_identity import bind_retail_queue_observation
        from apple_news_core.event_reconciler import bound_reconciliation_profile
        for article_id in ids:
            evidence = self.source_articles(article_id)[0].evidence
            claim = bind_retail_queue_observation(evidence)
            self.assertEqual({q[2] for q in claim.qualifiers if q[1] == 'queue-launch-day'}, {'23'})
            changed = replace(evidence, article_id='other-launch',
                units=tuple(replace(u, text=u.text.replace('23日', '24日')) for u in evidence.units))
            self.assertNotEqual(self.m.profile_pair_decision(bound_reconciliation_profile(claim),
                bound_reconciliation_profile(bind_retail_queue_observation(changed))), 'match')
            selected = ' '.join(u.text[a:b] for k,a,b in claim.evidence_spans
                for u in evidence.units if u.unit_id == k)
            self.assertNotIn('16日开启线上预售', selected)
        original = self.source_articles(ids[0])[0].evidence
        left = bound_reconciliation_profile(bind_retail_queue_observation(original))
        for changes in ((('168', '268'),), (('四十', '五十'),), (('开市客', '示例商店'),),
                        (('23日', '24日'),), (('21日下午', '22日下午'),),
                        (('南京', '成都'), ('上海', '北京'), ('杭州', '广州'))):
            def altered(text):
                for old,new in changes:
                    text = text.replace(old,new)
                return text
            evidence = replace(original, article_id='other-observation',
                units=tuple(replace(u, text=altered(u.text)) for u in original.units))
            with self.subTest(changes=changes):
                right = bound_reconciliation_profile(bind_retail_queue_observation(evidence))
                self.assertNotEqual(self.m.profile_pair_decision(left, right), 'match')
        for paragraph in ('Customers queued overnight at Costco stores for Galaxy Z Fold8.',
                          'No customers queued overnight at Costco stores for iPhone 23.'):
            claim = bind_retail_queue_observation(self.evidence('iPhone 23 queue report', paragraph))
            self.assertTrue(claim.review_reason)
        for paragraph in ('A reporter expects limited iPhone 23 stock at stores.',
                          'Customers will queue overnight at Costco stores for iPhone 23.',
                          '预计消费者会为 iPhone 23 在门店排队。',
                          'Last year, customers queued overnight at Costco stores for iPhone 23.',
                          'Employees told customers not to queue overnight for iPhone 23.',
                          '工作人员要求顾客不要为 iPhone 23 提前排队。'):
            self.assertIsNone(bind_retail_queue_observation(self.evidence('iPhone 23 queue report', paragraph)))

    def test_named_store_queue_owns_its_facility_and_stock_conditions(self):
        from apple_news_core.event_identity import bind_retail_queue_observation
        sid = self.ids('9259')[0]
        articles = self.source_articles(sid)
        self.assertTrue(articles)
        self.assertTrue(all(a.bound_claim and not a.bound_claim.review_reason for a in articles))
        events, _ = self.cluster_sources(sid, *self.ids('363d85', '7235ce'))
        self.assertEqual(len(events), 2)
        event = next(e for e in events if sid in self.source_ids(e))
        self.assertEqual((event.relevance_tier, event.category), ('strong', 'hardware_products'))
        title = 'iPhone 23门店排队观察'
        text = '有网友发布视频，10月24日晚8点，江苏南京山川生活广场店已有不少人排队等待iPhone 23发售。'
        claim = bind_retail_queue_observation(self.evidence(title, text))
        self.assertFalse(claim.review_reason)
        self.assertIn('江苏南京山川生活广场店', claim.object)
        self.assertNotIn('queue-count', {q[1] for q in claim.qualifiers})
        for bad in (text.replace('已有不少人', '预计将有不少人'),
                    text.replace('已有不少人排队', '没有人排队'),
                    text.replace('iPhone 23发售', 'Galaxy A61发售'),
                    '江苏南京山川生活广场店提醒顾客不要提前排队等待iPhone 23发售。'):
            bound = bind_retail_queue_observation(self.evidence(title, bad))
            self.assertTrue(bound is None or bound.review_reason)

    def test_migrated_actions_cannot_borrow_other_procedures_or_historical_models(self):
        from apple_news_core.event_identity import bind_court_remedy, bind_interoperability_report
        e = self.evidence('Apple appeals App Store third-party app stores order',
            'Apple has appealed an order by the Federal Court of Australia requiring third-party app stores.')
        self.assertIsNone(bind_court_remedy(e))
        opening = 'Samsung now supports Quick Share on Galaxy A61 with One UI 12 to iPhone.'
        protocol = 'Quick Share uses the AirDrop protocol.'
        claim = bind_interoperability_report(self.evidence('Galaxy A61 transfer support',
            opening + ' Last year Galaxy S26 used One UI 11.', protocol))
        self.assertNotIn('s26', claim.subject)
        self.assertIn('a61', claim.subject)
        denied = bind_interoperability_report(self.evidence('Galaxy A61 transfer support',
            opening.replace('to iPhone.', ', but cannot send files to iPhone.'), protocol))
        self.assertTrue(denied.review_reason)

    def test_same_attributed_imaging_observation_excludes_specs_and_viewer_opinion(self):
        ids = self.ids('394584','457e','b546','77fe')
        for order in (ids,ids[::-1]):
            events,_ = self.cluster_sources(*order)
            self.assertEqual(len(events), 3)
            self.assertIn(set(ids[:2]), [self.source_ids(e) for e in events])
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        for id in ids[:2]:
            a = self.source_articles(id)[0]
            remaining, _ = self.m.source_evidence_remainder(a.evidence, a.bound_claim.evidence_spans)
            units = {u.unit_id:u.text for u in a.evidence.units}
            text = ' '.join(units[k][start:end] for k,start,end in remaining)
            self.assertIn('PetaPixel', text)

    def test_imaging_identity_requires_a_current_attributed_output_observation(self):
        from apple_news_core.event_identity import bind_attributed_device_tests
        from apple_news_core.event_matcher import identity_pair_decision
        title = 'iPhone 23 under-display camera photos'
        opening = 'The iPhone 23 has an under-display camera.'
        observation = 'Camera Lab said its photos were low-res and washed out.'
        claims = bind_attributed_device_tests(self.evidence(title, opening, observation))
        self.assertEqual(len(claims), 1)
        other = bind_attributed_device_tests(self.evidence(title, opening, observation.replace('Camera Lab','Lens Lab')))
        self.assertNotEqual(identity_pair_decision(claims[0], other[0]), 'match')
        for text in ('Last year, '+observation, observation.replace('said','will test whether'),
                     observation.replace('were low-res and washed out','were not low-res or washed out'),
                     'Viewers said the photos were trash.', 'Camera Lab said it has a 4-megapixel camera.',
                     observation.replace('its photos', 'the rear camera photos'),
                     observation.replace('were low-res', 'will be low-res')):
            with self.subTest(text=text):
                self.assertFalse(bind_attributed_device_tests(self.evidence(title,opening,text)))
