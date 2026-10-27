"""Real report subjects retain their operator, action and evidence scope."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module
import test_p4_pure_json_batch as prior


class SourceReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261026_source_reports.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 26, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    def captured_case(self, key, title, body):
        from dataclasses import asdict, replace
        from apple_news_core.article_processing import capture_article_title_evidence
        evidence = capture_article_title_evidence('9to5Mac', 'https://example.org/' + key, title, body, ())
        evidence = replace(evidence, published_utc='2026-10-26T00:00:00+00:00',
                           published_raw='2026-10-26T00:00:00Z', published_source='test', confidence='detail')
        self.rows = {**self.rows, key: {'evidence': asdict(evidence), 'recorded_extraction': [title, body, []]}}
        return self.source_articles(key)

    def test_teardown_reports_share_investigator_but_not_another_test(self):
        ids = ('ae5e1bbca0e71bf70b2fc31f', '4126201b99c08997cbe5e2e1',
               'eff907e64403cba0446d4b1c', '1b636a17df66ea24b661604a',
               '7607c5dd9a9b6ff3bea53e74', 'a6ca0fc8651872fd1f51bb0d')
        jerry = '47e5b27391f6dbfd3d8f14a1'
        for order in ((*ids, jerry), (jerry, *reversed(ids))):
            with self.subTest(order=order):
                events, _ = self.cluster_sources(*order)
                groups = {frozenset(a.evidence.article_id for a in e.articles) for e in events}
                self.assertEqual(groups, {frozenset(ids), frozenset({jerry})})
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_commentary_cannot_join_named_physical_test(self):
        events, _ = self.cluster_sources('47e5b27391f6dbfd3d8f14a1', 'b7feb9149705d8ae559de6e3')
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(e.relevance_tier for e in events), ['strong', 'weak'])

    def test_current_supplier_response_owns_its_action_before_old_order_background(self):
        ids = ('7293b111f2d178216fc286d1', '45a890d1ca80aa5594e5e66b')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))

    def test_order_response_binds_speaker_device_and_current_speech(self):
        from apple_news_core.event_identity import source_market_report_frame
        title = '明川电子回应iPhone 23加单传闻：不评价比例'
        body = '明川电子是iPhone 23零件供应商。明川电子工作人员今日回应称，不对订单比例作评价，目前相关产线正在加班发货。'
        base = source_market_report_frame(title, body, (body,))
        self.assertIsNotNone(base)
        self.assertEqual(base.action, 'supplier-response')
        for word in ('加单', '砍单', '订单变化'):
            self.assertEqual(base, source_market_report_frame(title.replace('加单', word), body, (body,)))
        denial = body.replace('回应称，不对订单比例作评价', '否认追加订单的传闻')
        self.assertEqual(base, source_market_report_frame(title, denial, (denial,)))
        english_title = 'Supplier Meridian responds to iPhone 23 order rumors'
        english = 'Meridian is an iPhone 23 supplier. Meridian today denied the rumored order increase.'
        self.assertEqual(source_market_report_frame(english_title, english, (english,)).action, 'supplier-response')
        old = '此前苹果结构性调整订单，对iPhone 23加单，对iPhone 23 Pro砍单。'
        self.assertEqual(base, source_market_report_frame(title, body, (body, old)))
        for old, new in (('明川电子', '远河制造'), ('iPhone 23', 'iPhone 24')):
            self.assertNotEqual(base, source_market_report_frame(title.replace(old,new), body.replace(old,new), (body.replace(old,new),)))
        for changed in (body.replace('今日回应', '去年回应'), body.replace('今日回应', '计划明天回应'),
                        body.replace('今日回应', '尚未回应'), body.replace('今日回应', '没有回应'),
                        body.replace('iPhone 23', 'iPhone 24'), body.replace('明川电子工作人员', '远河制造工作人员')):
            with self.subTest(body=changed):
                self.assertNotEqual(base, source_market_report_frame(title, changed, (changed, old)))

    def test_attributed_commentary_does_not_inherit_background_customer_service_action(self):
        events, _ = self.cluster_sources('ac9a6122805b83cdf02d8467')
        self.assertEqual([e.relevance_tier for e in events], ['weak'])
        articles = self.captured_case('opinion-with-other-device-test',
            '林泉谈iPhone Duo订单取消：价格不便宜',
            '博主林泉表示，iPhone Duo价格不便宜。'
            '林泉发布了Galaxy Fold的防尘测试视频，并评论iPhone Duo不值得买。'
            '据媒体报道，苹果客服透露很多消费者取消了订单，官方渠道支持14天无理由退换货。')
        self.assertEqual([e.relevance_tier for e in self.m.cluster_articles(articles)], ['weak'])

    def test_quoted_evaluation_requires_same_external_speaker_and_judgment(self):
        from apple_news_core.event_identity import source_editorial_evaluation
        title = '林泉谈iPhone订单取消：价格不便宜'
        self.assertEqual(source_editorial_evaluation(title,
            '话题引发讨论。博主林泉发文表示，这个价格确实不便宜。苹果客服此前回应订单交付问题。'), 'analysis')
        for headline, body in (
                ('苹果谈iPhone订单取消：价格不便宜', '苹果发言人表示，新机定价不便宜，但订单交付正常。'),
                (title, '博主林泉发布实测结果，记录不同使用条件下的屏幕表现。'),
                (title, '博主张宁发文表示，这个价格确实不便宜。'),
                (title, '记者林泉获悉，苹果已经调整了订单交付安排。'),
                ('林泉谈iPhone订单取消：首批交付延期', '博主林泉表示，苹果通知他的订单推迟三天交付。')):
            with self.subTest(headline=headline, body=body):
                self.assertFalse(source_editorial_evaluation(headline, body))

    def test_focused_observation_keeps_eligibility_when_observer_adds_evaluation(self):
        body = ('博主林泉表示，这次防尘测试的结果令人失望。'
                '林泉发布了iPhone Duo的防尘测试视频，将荧光粉尘撒在铰链上并反复开合十次，'
                '随后设备无法闭合，拆开后观察到铰链内有粉尘。')
        for title in ('林泉谈iPhone Duo防尘测试：铰链进灰后无法闭合',
                      '林泉谈iPhone Duo防尘测试：结果令人失望',
                      '林泉谈iPhone Duo铰链进灰：开合十次后无法闭合，结果令人失望'):
            with self.subTest(title=title):
                articles = self.captured_case('measured-with-evaluation',
                    title, body)
                self.assertEqual([e.relevance_tier for e in self.m.cluster_articles(articles)], ['strong'])
        from apple_news_core.event_identity import source_editorial_evaluation
        for other in (body.replace('林泉发布', '张宁发布'),
                      body.replace('林泉发布', '林泉去年发布'),
                      body.replace('林泉发布', '林泉计划发布'),
                      body.replace('林泉发布', '林泉没有发布'),
                      body.replace('iPhone Duo的防尘', 'iPhone 28的防尘'),
                      '博主林泉表示，iPhone Duo不值得买。林泉发布了Galaxy Fold的防尘测试视频，并评论iPhone Duo不值得买。'):
            with self.subTest(other=other):
                self.assertEqual(source_editorial_evaluation(title, other), 'analysis')

    def test_current_product_reporting_survives_explanatory_headline_and_history(self):
        events, _ = self.cluster_sources('04640c5bc8eb1dff1364e1de')
        self.assertEqual([e.relevance_tier for e in events], ['strong'])

    def test_recent_teardown_publication_keeps_its_named_operator(self):
        ids = ('98e5f807dda26e3b83200118', 'ae5e1bbca0e71bf70b2fc31f')
        for order in (ids, tuple(reversed(ids))):
            events, _ = self.cluster_sources(*order)
            self.assertEqual([(e.relevance_tier, e.category) for e in events],
                             [('strong', 'hardware_products')])
            self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))

    def test_publication_modifiers_preserve_observer_and_action_scope(self):
        from apple_news_core.event_identity import source_operation_frame, build_event_identity
        title = 'iPhone 29 拆解报告：可能的故障原因'
        def frame(text):
            return source_operation_frame(title, text, (), build_event_identity(title, text),
                                          source_units=(text,))
        for text in ('Orion Labs发布了iPhone 29的最新拆解报告。',
                     'Orion Labs在上周末发布了iPhone 29的完整拆解报告。',
                     'Orion Labs于昨日发布了iPhone 29的最新拆解报告。'):
            with self.subTest(text=text):
                actual = frame(text)
                self.assertIsNotNone(actual)
                self.assertEqual(actual.subject, 'iphone-29:publishers:orion labs')
        base = frame('Orion Labs发布了iPhone 29的完整拆解报告。')
        for text in ('Orion Labs去年发布了iPhone 29的最新拆解报告。',
                     'Orion Labs计划在下周末发布iPhone 29的最新拆解报告。',
                     'Orion Labs在上周末没有发布iPhone 29的最新拆解报告。',
                     'Orion Labs在上周末发布了iPhone 29保护壳的最新拆解报告。',
                     'Vega Lab在上周末发布了iPhone 29的最新拆解报告。'):
            with self.subTest(text=text):
                self.assertNotEqual(frame(text), base)

    def test_broad_roadmap_identity_cannot_erase_processor_and_display_actions(self):
        for ids in (('493e02b77832bc36ef9dbf62', 'cbaaea7c99bdd65f084e5dda'),
                    ('cbaaea7c99bdd65f084e5dda', '493e02b77832bc36ef9dbf62')):
            events, _ = self.cluster_sources(*ids)
            self.assertEqual(len(events), 2)

    def test_rumor_preview_does_not_republish_old_material_as_a_current_disclosure(self):
        events, _ = self.cluster_sources('1a97ff7e924247dca7206be8')
        self.assertEqual([e.relevance_tier for e in events], ['weak'])
        from apple_news_core.event_identity import source_editorial_outlook
        title = "New iPad: here's what's coming"
        recap = "These are the rumors you have heard so far."
        self.assertTrue(source_editorial_outlook(title, recap, (recap,)))
        fresh = 'A new report today reveals Apple is developing a new iPad.'
        self.assertFalse(source_editorial_outlook(title, fresh, (fresh, recap)))

    def test_capability_inference_does_not_join_current_hardware_announcement(self):
        inference = 'e477e6f364f02015f720edd2'
        release = '493e02b77832bc36ef9dbf62'
        for order in ((inference, release), (release, inference)):
            events, _ = self.cluster_sources(*order)
            self.assertEqual({frozenset(a.evidence.article_id for a in e.articles): e.relevance_tier
                              for e in events},
                             {frozenset({inference}): 'weak', frozenset({release}): 'strong'})
        events, _ = self.cluster_sources('92cf6e0cccb5f09bf91c67ad')
        self.assertEqual([e.relevance_tier for e in events], ['weak'])

    def test_conditional_outlook_requires_authored_reasoning_not_uncertainty_alone(self):
        from apple_news_core.event_identity import source_editorial_outlook
        title = '消息称苹果新款iPad有望支持卫星通信'
        argument = '同时考虑到新处理器已经用于相关设备，因此这一情况便显得有些耐人寻味。'
        scenario = '如果苹果为iPad引入卫星通信，预计会采用新的天线方案。'
        premise = '此前报道提到苹果曾测试相关配置。'
        self.assertTrue(source_editorial_outlook(title, premise, (premise, argument, scenario)))
        for parts in ((premise, scenario),
                      (premise, '苹果表示，考虑到测试结果，因此预计会采用新方案。', scenario),
                      ('最新报道披露苹果正在为iPad测试卫星通信功能。', argument, scenario)):
            with self.subTest(parts=parts):
                self.assertFalse(source_editorial_outlook(title, parts[0], parts))
        title = '苹果确认新款iPad正在测试卫星通信，有望支持紧急联络'
        current = '苹果今日证实，新款iPad正在测试卫星通信功能。'
        for body in (current, current + argument + scenario):
            with self.subTest(body=body):
                articles = self.captured_case('current-disclosure-with-inference', title, body)
                self.assertEqual([e.relevance_tier for e in self.m.cluster_articles(articles)], ['strong'])
        from apple_news_core.event_identity import source_current_disclosure_clauses
        for absent in ('苹果今日没有确认测试iPad卫星通信。',
                       '苹果今日尚未公开确认测试iPad卫星通信。',
                       'Apple has not confirmed testing satellite connectivity today.'):
            with self.subTest(absent=absent):
                self.assertFalse(source_current_disclosure_clauses(absent, ()))
                articles = self.captured_case('missing-confirmation',
                    '消息称苹果新款iPad有望支持卫星通信', ' '.join((absent, argument, scenario)))
                self.assertEqual([e.relevance_tier for e in self.m.cluster_articles(articles)], ['weak'])
        for response in ('苹果今日否认测试iPad卫星通信。',
                         '苹果今日确认没有测试iPad卫星通信。',
                         'Apple denied testing satellite connectivity today.'):
            with self.subTest(response=response):
                self.assertEqual(source_current_disclosure_clauses(response, ()), (response,))

    def test_test_publication_requires_a_predicate_and_keeps_its_method(self):
        title = 'iPhone Duo 拆解报告征集'
        request = self.captured_case('request', title,
            '用户请求Orion Labs对iPhone Duo的完整拆解，实验室尚未开始测试。')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in self.m.cluster_articles(request)))
        for key, body in (
                ('plan', 'Orion Labs计划完成对iPhone Duo的完整拆解，以研究屏幕结构。'),
                ('old', 'Orion Labs发布了iPhone Duo的完整拆解报告，发布时间为去年。'),
                ('unfinished', 'Orion Labs没有完成对iPhone Duo的完整拆解。'),
                ('never', 'Orion Labs never tears down the iPhone Duo.')):
            with self.subTest(case=key):
                articles = self.captured_case(key, 'iPhone Duo 拆解报告', body)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in self.m.cluster_articles(articles)))
        dust = self.captured_case('dust', 'iPhone Duo 防尘测试',
            '博主Orion Labs发布了iPhone Duo的防尘测试视频，使用沙尘测试铰链。此次只测试防尘性能，未进行弯折测试。')
        bend = self.captured_case('bend', 'iPhone Duo 弯折测试',
            '博主Orion Labs发布了iPhone Duo的弯折测试视频，使用砝码测量断裂力度。这是另一次独立试验，没有使用沙尘。')
        for pair in (dust + bend, bend + dust):
            events = self.m.cluster_articles(pair)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_automation_capability_keeps_source_negation_history_and_stage(self):
        title = 'iPhone Duo 快捷指令：展开或折叠时触发'
        current = self.captured_case('current', title,
            'iPhone Duo 可以在展开或折叠时触发快捷指令，执行预设操作。')
        for key, body in (
                ('history', '去年，苹果展示了 iPhone Duo 展开或折叠时触发快捷指令、执行预设操作的演示。本文回顾这段旧演示，没有新增信息。'),
                ('denied', 'iPhone Duo 无法在展开或折叠时触发快捷指令，也不能执行预设操作。'),
                ('cannot-execute', 'iPhone Duo 无法在展开或折叠时执行预设操作。'),
                ('charging', 'iPhone Duo 目前可以在充电时触发快捷指令，执行预设操作。展开或折叠时触发快捷指令的能力尚未推出。'),
                ('future', '苹果计划让 iPhone Duo 在展开或折叠时触发快捷指令，执行预设操作。该功能目前尚未推出。')):
            with self.subTest(case=key):
                other = self.captured_case(key, title, body)
                self.assertEqual(len(self.m.cluster_articles(current + other)), 2)
                if key == 'history':
                    self.assertTrue(all(e.relevance_tier == 'weak' for e in self.m.cluster_articles(other)))
    def test_oled_prototype_report_does_not_project_background_macbook_pro(self):
        articles = self.source_articles('6dbdb38b20b96f151f83466a')
        self.assertEqual(len(articles), 1)
        self.assertIn('iMac', articles[0].title)
        self.assertIn('MacBook Air', articles[0].title)
        events, _ = self.cluster_sources('6dbdb38b20b96f151f83466a', 'cbaaea7c99bdd65f084e5dda')
        self.assertEqual(len(events), 2)

    def test_non_apple_hardware_port_is_not_first_party_release(self):
        events, _ = self.cluster_sources('717403910deb8b70a48017bb')
        self.assertEqual([e.relevance_tier for e in events], ['weak'])

    def test_reported_price_direction_reaches_detail_and_keeps_its_sample(self):
        row = self.rows['ce04eac2d330b8fa5dfb69a9']['evidence']
        candidate = self.m.Candidate(row['source'], row['url'], row['title'], '')
        self.assertTrue(self.m.is_relevant_candidate(candidate, self.sources[row['source']]))
        events, _ = self.cluster_sources(row['article_id'])
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        self.assertIn('部分区域', events[0].summary)

    def test_software_objects_keep_category_and_same_action_sources(self):
        for ids in (('b437790e4c728561e4146dd0',), ('f478727f825080de0a4e11aa',),
                    ('02b1054307b1a96fcc71d4b8', '8f586d2a94ab418b6cbe4e4c'),
                    ('10d3344b9b96f2c9811a2168', 'bdd859434fa147f06e65681c')):
            with self.subTest(ids=ids):
                events, _ = self.cluster_sources(*ids)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])

    def test_physical_support_document_keeps_same_action_sources(self):
        ids = ('7e0b6f1530a2bee8fd47af19', 'c3c01af3434bce35777fc167')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
            self.assertEqual({a.evidence.article_id for a in events[0].articles}, set(ids))

    def test_reported_device_failures_do_not_require_apple_confirmation(self):
        for aid in ('193c6b632c794d6e93707f0e', '0422e927f0e36b688d125632', 'f74ca44cf2b14b88e3c260dc'):
            with self.subTest(article=aid):
                events, _ = self.cluster_sources(aid)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])

    def test_named_experiment_continuation_keeps_operator_and_original_neighbors(self):
        ids = ('a6a8e3cc76f93ea6c4682a11', 'd6c3003df299762534e6d8b3')
        events, _ = self.cluster_sources(*ids, '47e5b27391f6dbfd3d8f14a1')
        self.assertEqual({frozenset(a.evidence.article_id for a in e.articles) for e in events},
                         {frozenset(ids), frozenset({'47e5b27391f6dbfd3d8f14a1'})})
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_observation_owns_operator_device_and_local_publication_stage(self):
        from apple_news_core.event_identity import source_operation_frame, build_event_identity
        def frame(title, text):
            return source_operation_frame(title, text, (), build_event_identity(title, text), source_units=(text,))
        title = 'iPhone Duo 拆解报告：屏幕故障可能与铰链有关'
        text = 'Orion Labs发布了iPhone Duo的完整拆解报告，故障原因可能与铰链有关。'
        base = frame(title, text)
        self.assertEqual(base.subject, 'iphone-duo:publishers:orion labs')
        for other in ('Vega Lab发布了iPhone Duo的完整拆解报告。',
                      'Orion Labs发布了iPhone 29的完整拆解报告。',
                      '去年，Orion Labs发布了iPhone Duo的完整拆解报告。',
                      'Orion Labs计划发布iPhone Duo的完整拆解报告。',
                      'Orion Labs没有发布iPhone Duo的完整拆解报告。',
                      'Orion Labs发布了iPhone Duo保护壳的拆解报告。'):
            with self.subTest(text=other):
                self.assertNotEqual(frame(title, other), base)
        tested = frame('iPhone Duo 防尘测试', '博主Orion Labs发布了iPhone Duo的耐用性测试视频。')
        self.assertEqual(tested.subject, 'iphone-duo:durability:orion-labs')
        self.assertNotEqual(tested.action, base.action)

    def test_discount_offer_or_old_feedback_cannot_supply_a_current_price_observation(self):
        from apple_news_core.event_identity import bind_resale_report
        from apple_news_core.article_processing import capture_article_title_evidence
        title = '苹果 iPhone 29 部分地区破发，电商平台提供补贴'
        positive = '根据消费者反馈，iPhone 29 在部分地区已经破发，市场价格低于上市价。'
        for text, qualifies in ((positive, True),
                ('去年，' + positive, False),
                (positive.replace('iPhone 29 在', 'iPhone 30 在'), False),
                ('某电商平台为iPhone 29提供百亿补贴，售价比官网便宜300元。', False)):
            with self.subTest(text=text):
                evidence = capture_article_title_evidence('Example', 'https://example.org/price', title, text, ())
                self.assertEqual(bool(bind_resale_report(evidence)), qualifies)

    def test_joint_prototype_object_does_not_borrow_another_product_test(self):
        from apple_news_core.event_identity import bind_hardware_prototype_testing
        from apple_news_core.article_processing import capture_article_title_evidence
        title = 'OLED upgrades for iMac and MacBook Air are planned'
        for text, resolved in (
                ('Apple is currently testing new versions of the MacBook Air and iMac.', True),
                ('Apple is currently testing new versions of the MacBook Pro.', False),
                ('Last year, Apple was testing new versions of the MacBook Air and iMac.', False),
                ('Apple plans to test new versions of the MacBook Air and iMac.', False)):
            with self.subTest(text=text):
                evidence = capture_article_title_evidence('Example', 'https://example.org/prototype', title, text, ())
                claims = bind_hardware_prototype_testing(evidence)
                self.assertEqual(bool(claims and all(c.subject for c in claims)), resolved)


if __name__ == '__main__':
    unittest.main()
