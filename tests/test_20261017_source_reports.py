"""Current source actions must not inherit an unrelated background predicate."""

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

import test_p4_pure_json_batch as captured
from test_relevance_rules import load_module, article_for


class SourceReportTests(unittest.TestCase):
    source_articles = captured.PureJsonBatchTests.source_articles
    cluster_sources = captured.PureJsonBatchTests.cluster_sources

    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261017_source_reports.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 17, tzinfo=timezone.utc))}

    def test_regional_price_report_is_not_demoted_by_industry_headline_context(self):
        source_id = 'da7051c00d5ebdbad654fdf2'
        original = self.source_articles(source_id)[0]
        for title in (original.title, 'iPhone Duo全球售价一览：折叠屏手机均价2年涨近3成'):
            article = self.source_articles(source_id)[0]
            article.title = title
            profile = self.m.article_reconciliation_profile(article)
            self.assertEqual(profile.relevance_tier, 'strong')
            events = self.m.cluster_articles([article])
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        self.assertFalse(self.m.is_non_apple_price_followup_story(original.title, original.summary))

    def test_non_apple_price_actor_does_not_require_a_following_keyword(self):
        for title, lead in (
            ('三星上调手机售价，苹果此前已涨价', '三星今天宣布Galaxy手机售价上调100美元。报道提到苹果此前提高iPhone售价，作为背景。'),
            ('微软Xbox售价上调80美元，苹果仅作对比', '微软今天宣布Xbox售价上调80美元，苹果价格仅为对比。'),
            ('Following Apple! Microsoft raises prices on Xbox consoles', 'Microsoft announced new Xbox console prices. Apple previously increased iPad prices.'),
        ):
            with self.subTest(title=title):
                article = article_for(self.m, title, lead, source='快科技')
                self.assertEqual(self.m.article_reconciliation_profile(article).relevance_tier, 'weak')
        self.assertFalse(self.m.is_non_apple_price_followup_story(
            '三星上调手机售价！iPhone Duo全球售价一览', '该报道分别列出两家公司的官方价格。'))

    def test_current_company_encounters_keep_their_own_counterpart(self):
        pairs = [('ceb6181dcbfe62bada0964b5', '5cead8be8c1c89662264e3b9', 'corporate-visit', '米哈游'),
                 ('dfbbc6a096675d66953588c4', 'd21794645ec81c48d0370246', 'government-meeting', '陈吉宁')]
        groups = []
        for left, right, action, target in pairs:
            with self.subTest(action=action):
                articles = [self.source_articles(key)[0] for key in (left, right)]
                for article in articles:
                    profile = self.m.article_reconciliation_profile(article)
                    self.assertTrue(any(action in key and target in key for key in profile.event_keys))
                    self.assertEqual((profile.relevance_tier, profile.category_hint), ('strong', 'hardware_products'))
                for order in (articles, articles[::-1]):
                    self.assertEqual(len(self.m.cluster_articles(order)), 1)
                groups.extend(articles)
        self.assertEqual(len(self.m.cluster_articles(groups)), 2)

    def test_an_unresolved_encounter_cannot_borrow_a_background_meeting(self):
        from apple_news_core.event_identity import source_executive_government_frame
        article = self.source_articles('d21794645ec81c48d0370246')[0]
        self.assertIsNone(source_executive_government_frame('苹果库克与来宾会面',
            '苹果公司执行董事长库克今天与来宾会面。' + article.evidence.units[-1].text))

    def test_visit_conclusion_does_not_inherit_a_prior_leadership_transition(self):
        ids = ('3acffaf3f85d584683c373dd', '9a01b4fbcc5b45c3804a5833')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        from apple_news_core.event_identity import source_executive_visit_frame
        for title, lead in (
            ('苹果库克计划结束中国之行', '苹果执行董事长库克将结束本次访问。'),
            ('苹果库克去年结束中国之行', '报道回顾苹果库克去年结束的访问。'),
            ('苹果库克并未结束中国之行', '苹果执行董事长库克否认本次访问已经结束。'),
            ('其他公司CEO结束中国之行', '其他公司CEO结束访问，苹果库克去年也曾来华。'),
            ('库克中国之行结束在即：明日启程回国', '苹果董事会执行主席库克仍在访问中国，计划明日结束行程。'),
        ):
            with self.subTest(title=title):
                result = source_executive_visit_frame(title, lead, ())
                self.assertTrue(result is None or result.action != 'completed-corporate-visit')
        private = article_for(self.m, '库克日本之行结束：与家人度假归来',
            '苹果董事会执行主席库克结束了与家人在日本的私人度假，此行没有公司活动。', source='IT之家')
        self.assertEqual(self.m.article_reconciliation_profile(private).relevance_tier, 'weak')

    def test_store_maintenance_and_actual_preorder_opening_are_separate_actions(self):
        maintenance = ('353d5ea7a7e30c81da6be36b', '359cffb0ac569b80042208b4',
                       '5868a09a43abbecb0d738775', 'e1a7721d7cda6b9e4870680c')
        opened = ('9e70cbe79f5dbe9448efe9d5', '6ad7a2480e3fc1a08c022796',
                  '4e5bd283cfc702fe54f9125a', '841bf2f493a1661f82a215b2')
        for ids in (maintenance, opened):
            for order in (ids, ids[::-1]):
                events, _ = self.cluster_sources(*order)
                self.assertEqual(len(events), 1)
                self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))
                self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        events, _ = self.cluster_sources(*maintenance, *opened, '582f06078fea998d7f62a2fd')
        self.assertEqual(len(events), 3)

    def test_preorder_specs_and_trade_in_values_do_not_create_other_actions(self):
        article, = self.source_articles('4e5bd283cfc702fe54f9125a')
        profile = self.m.article_reconciliation_profile(article)
        self.assertFalse(any('repair-cost' in key or 'stylus' in key for key in profile.event_keys))
        self.assertTrue(any('preorder' in key for key in profile.event_keys))

    def test_software_inventory_does_not_merge_a_price_evaluation(self):
        feature = '419126e6f8f2acf6ca24b4ed'
        opinion = '0463e9af9c9e9485b96281d3'
        for order in ((feature, opinion), (opinion, feature)):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            by_source = {a.evidence.article_id: e for e in events for a in e.articles}
            self.assertEqual((by_source[feature].relevance_tier, by_source[feature].category), ('strong', 'software_systems'))
            self.assertEqual(by_source[opinion].relevance_tier, 'weak')

    def test_official_accessory_conditions_share_the_same_owned_product(self):
        ids = ('b0a35ee8122a5bd209bd0f75', '2f9df5085b30c2eee829f37e', 'f1d7aabdc17e45c225939874')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_company_appointment_cannot_become_a_third_party_finance_product(self):
        ids = ('8a8c6892ce34abbd1aecb046', 'a93f5e7ffd07c85ef4a2435c')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_current_measurement_and_completed_auction_remain_hardware_reports(self):
        for sid in ('22ebecd69112d8c6f663c2e9', '841f019511fcffdb8c6fd45b'):
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_native_platform_service_price_keeps_software_category(self):
        events, _ = self.cluster_sources('86119ff3c7f672bafeb35a11', '79e2d5ab4515d156ae8e8f44')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')

    def test_vehicle_capability_inventory_does_not_claim_a_platform_change(self):
        events, _ = self.cluster_sources('1d8210c33dd79b2617a5b827')
        self.assertEqual([event.relevance_tier for event in events], ['weak'])
        for title, lead, tier in (
            ('星河汽车旧车型固件升级：支持无线 CarPlay',
             '星河汽车发布旧车型固件更新，新增无线CarPlay连接，手机通过蓝牙和Wi-Fi连接。', 'ecosystem'),
            ('星河汽车座舱升级：支持苹果 CarPlay',
             '星河汽车公布座舱升级清单，新增视频显示分区；手机仍可使用CarPlay。', 'weak'),
            ('苹果发布 CarPlay 平台升级：支持新的车机显示布局',
             '苹果发布CarPlay软件更新，新增车机显示布局。', 'strong'),
        ):
            with self.subTest(title=title):
                article = article_for(self.m, title, lead, source='IT之家')
                self.assertEqual(self.m.article_reconciliation_profile(article).relevance_tier, tier)

    def test_retail_preserves_role_and_stage(self):
        rows = (
            ('Apple Store was down ahead of iPhone Duo preorders last year', "Apple's online store was down last year before iPhone Duo preorders began."),
            ('iPhone Duo delivery dates revisited', 'Last year, Apple delivery dates for iPhone Duo slipped into January.'),
            ('Apple denies iPhone Duo delivery dates slipped to January', 'Apple denies that iPhone Duo delivery dates slipped to January.'),
            ('iPhone Duo Preorder Deals: Best Carrier Offers', 'Apple will open iPhone Duo preorders on November 2. Here are the best carrier discounts.'),
            ('How to preorder iPhone Duo on November 2', 'Apple will open iPhone Duo preorders on November 2. Follow these steps to place your order.'),
            ('Apple did not open iPhone Duo preorders on November 2', 'Apple did not open iPhone Duo preorders on November 2.'),
        )
        for title, lead in rows:
            with self.subTest(title=title):
                event, = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertEqual(event.relevance_tier, 'weak')
        current = article_for(self.m, 'Apple Store is down ahead of iPhone Duo preorders', "Apple's online store is down today before iPhone Duo preorders begin.")
        planned = article_for(self.m, 'Apple Store will go offline ahead of iPhone Duo preorders', "Apple's online store will go offline next Friday before iPhone Duo preorders begin.")
        self.assertEqual(len(self.m.cluster_articles([current, planned])), 2)
        future = article_for(self.m, 'iPhone Duo preorders begin tomorrow',
            "iPhone Duo preorders will begin tomorrow. Apple's online store is back online after routine maintenance.")
        opened = article_for(self.m, 'iPhone Duo preorders are now open', 'iPhone Duo preorders are now open.')
        self.assertEqual(len(self.m.cluster_articles([future, opened])), 2)


    def test_denied_appointment_does_not_join_affirmative_appointment(self):
        good = article_for(self.m, 'Apple appoints a new legal executive', 'Apple has hired Scott Tucker to lead global litigation.')
        bad = article_for(self.m, 'Apple denies appointing a new legal executive', 'Apple denied reports that Apple has hired Scott Tucker to lead global litigation.')
        self.assertEqual(len(self.m.cluster_articles([good, bad])), 2)
        self.assertFalse(any(key.endswith(':executive-appointment') for key in self.m.article_reconciliation_profile(bad).event_keys))

    def test_measurement_cannot_borrow_old_or_other_camera_numbers(self):
        from apple_news_core.event_identity import source_device_behavior_test_frame
        title = 'The difference the variable aperture of iPhone 18 Pro makes at night'
        lead = 'I tested the camera controls on iPhone 18 Pro today.'
        for text in ('Last year, a photograph shot at f/1.8 reduced the exposure from 2.1 seconds to 1.7 seconds.',
                     'For comparison, a Nikon camera at f/1.8 reduced the exposure from 2.1 seconds to 1.7 seconds.'):
            with self.subTest(text=text):
                self.assertIsNone(source_device_behavior_test_frame(title, lead, (text,)))

    def test_feature_spans_leave_unrelated_claims_for_review(self):
        import html
        from apple_news_core.event_identity import bind_device_capability_inventory
        title = 'HomePod is about to get free upgrade with new features'
        texts = ['Apple announced three HomePod features that will arrive via a free software update.',
                 'HomePod can use AirPlay to play music.', 'Separately, Apple cancelled the next iPhone model.',
                 'Last year Apple introduced HomePod mini with Siri.', 'The writer hopes the display will support video.']
        evidence = self.m.capture_article_evidence('9to5Mac', 'https://example.com/features',
            '<article>' + ''.join('<p>' + html.escape(text) + '</p>' for text in texts) + '</article>', title)
        claim = bind_device_capability_inventory(evidence)
        self.assertIsNotNone(claim)
        units = {u.unit_id:u.text for u in evidence.units}
        bound = ' '.join(units[key][a:b] for key,a,b in claim.evidence_spans)
        self.assertIn('AirPlay', bound)
        for excluded in texts[2:]:
            self.assertNotIn(excluded, bound)

    def test_retail_forecast_and_transactions_preserve_opening_stage(self):
        ids = ('96b4f42719f031ff640e5a5f', 'f878bacf46cd769f4c382ca8', 'a0a43d46b5b9cfef8654e82a')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 3)

    def test_official_demand_response_owns_its_current_statement(self):
        ids = ('b24dc0ad7432d3086d0a92d1', 'd857ab3fb93386d3b1d33edf',
               '2ce24eba5be931f1cd62957b', 'e343ef33a1fdfec048074a19')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
            self.assertTrue(all(any('demand-response' in k for k in self.m.article_reconciliation_profile(a).event_keys)
                                for a in events[0].articles))

    def test_reported_interface_modes_are_software(self):
        events, _ = self.cluster_sources('f740ee830f761302f9112e50')
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))

    def test_publisher_discussion_does_not_borrow_its_topic_launch(self):
        for sid in ('3915d753299d01266ea137fb', '9dacb4c34e854249820c260c'):
            with self.subTest(sid=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_delivery_observations_merge_copies_without_merging_later_estimates(self):
        early = ('e4c09c34a66d27e9fcf2f4c2', '805234155cb8cc3120474c14')
        later = ('f3ab3684723e6081c995e0a1', '2111d585eddb7c8ad8fb95e4')
        for pair in (early, later):
            for order in (pair, pair[::-1]):
                events, _ = self.cluster_sources(*order)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].relevance_tier, 'strong')
        events, _ = self.cluster_sources(*early, *later)
        self.assertEqual(len(events), 2)
        from apple_news_core.event_identity import source_retail_operation_frame
        for lead in ('Last year, iPhone Duo estimated shipping dates slipped to January 25.',
                     'Apple denied that iPhone Duo estimated shipping dates slipped to January 25.',
                     'Rival Fold estimated shipping dates slipped to January 25.'):
            with self.subTest(lead=lead):
                frame = source_retail_operation_frame('iPhone Duo shipping dates slip', lead)
                self.assertFalse(frame and frame.action == 'retail-delivery-estimate')

    def test_delivery_date_requires_its_own_subject_relation_and_region(self):
        from apple_news_core.event_identity import source_retail_operation_frame
        title = 'iPhone Duo shipping dates slip'
        for passages in (
            ('Apple opened iPhone Duo preorders.', 'The leather case has an estimated delivery date of January 25, 2027.'),
            ('Last year Apple opened iPhone Duo preorders.', 'The estimated delivery date was January 25, 2026.'),
            ('The shipping date for iPhone Duo was discussed in a report published on October 10, 2026.',),
        ):
            with self.subTest(passages=passages):
                self.assertIsNone(source_retail_operation_frame(title, passages[0], passages))
        frame = source_retail_operation_frame(title,
            'The estimated delivery date for iPhone Duo is January 25, 2027, not January 29, 2027.')
        self.assertEqual(frame.period, '2027:1:25')
        frame = source_retail_operation_frame(title, '苹果已开启国行iPhone Duo预售。',
            ('苹果已开启国行iPhone Duo预售。', '美国官网的iPhone Duo交货时间已经排到1月。'))
        self.assertEqual(frame.region, 'us')

    def test_local_actions_do_not_borrow_other_owners_history_or_denial(self):
        from apple_news_core.event_identity import source_retail_operation_frame, source_device_operation_frame
        for title, lead in (
            ('Apple says iPhone Duo demand report needs context', 'Apple said demand for iPhone 17 is extraordinary.'),
            ('Apple says iPhone Duo demand was extraordinary', 'Apple said last year that demand for iPhone Duo was extraordinary.'),
        ):
            with self.subTest(lead=lead):
                self.assertIsNone(source_retail_operation_frame(title, lead))
        frame = source_retail_operation_frame('iPhone Duo resale demand after preorders',
                                              'No completed sales of iPhone Duo have been recorded.')
        self.assertEqual(frame.tier, 'weak')
        for text in ('Rival Fold detects the hinge angle to adjust the display interface.',
                     'Last year iPhone Duo detected the hinge angle to adjust the display interface.',
                     'Apple denied that iPhone Duo can detect the hinge angle to adjust its display interface.'):
            with self.subTest(text=text):
                frame = source_device_operation_frame('iPhone Duo display modes compared', text, source_units=(text,))
                self.assertFalse(frame and frame.action == 'platform-capability-report')

    def test_policy_ownership_and_quoted_opinion_remain_local(self):
        for text in ('Apple revised the App Review Guidelines last year to ban nonconsensual intimate imagery.',
                     'Apple developers revised their own rules after reviewing the App Review Guidelines for nonconsensual intimate imagery.'):
            with self.subTest(text=text):
                article = article_for(self.m, 'Apple App Review Guidelines for intimate imagery', text)
                keys = self.m.article_reconciliation_profile(article).event_keys
                self.assertFalse(any('policy-revision' in key for key in keys))
        from apple_news_core.event_identity import source_editorial_outlook
        self.assertFalse(source_editorial_outlook('Apple says iPhone Duo demand is a success',
            'Apple said demand for iPhone Duo is extraordinary.',
            ('Apple said demand for iPhone Duo is extraordinary.', 'In my opinion this is a success, an analyst said.')))

    def test_same_app_review_policy_revision_reconciles_across_languages(self):
        ids = ('c6840577bf082394f7fc03bc', '012517d9f1175e5c20e60d83',
               '13377470e19c0b154608c1cb', 'd03b1ce141d0a5586f37832d')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))


if __name__ == '__main__':
    unittest.main()
