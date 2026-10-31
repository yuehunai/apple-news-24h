"""Concrete report boundaries from captured source evidence."""
import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

class ReportBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent/'fixtures/20261030_report_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,10,30,tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    def sid(self,prefix):
        return next(k for k in self.rows if k.startswith(prefix))
    def test_device_model_does_not_identify_a_shared_action(self):
        for prefixes in [('25d7','c584'),('25d7','e957'),('e4e0','a629')]:
            with self.subTest(prefixes=prefixes):
                events,_=self.cluster_sources(*(self.sid(p) for p in prefixes))
                self.assertEqual(len(events),2)
    def test_direct_company_report_survives_incidental_exclusion_words(self):
        from unittest import mock
        row=self.rows[self.sid('4a9c')];m=self.m;source=self.sources['MacRumors']
        with mock.patch.object(m,'fetch_url',side_effect=lambda url,*args,**kwargs:
                row['feed_xml'] if url==row['captured_from'] else None):
            candidates=m.collect_candidates(source,Path('/unused-cache'),{})
        chosen=m.select_detail_candidates(candidates,{source.name:source},20,
            datetime(2026,10,30,8,38,tzinfo=timezone.utc),datetime(2026,10,31,8,38,tzinfo=timezone.utc))
        self.assertEqual([c.url for c in chosen],[row['evidence']['url']])
        for title,body in (
                ('Regulator places Apple on a data registry','Apple and Microsoft must retain user data under the regulator’s designation.'),
                ('Regulator lists Apple and Microsoft as data custodians','The regulator added Apple and Microsoft to its data registry.')):
            candidate=m.Candidate(source.name,'https://www.macrumors.com/2026/10/31/report/',title,body)
            self.assertTrue(m.is_relevant_candidate(candidate,source))
        candidate=m.Candidate(source.name,'https://www.macrumors.com/2026/10/31/report/',
            'Regulator places Microsoft on a data registry','Microsoft faces new data retention duties. Apple remains outside the new designation.')
        self.assertFalse(m.is_relevant_candidate(candidate,source))
    def test_registry_report_keeps_its_regulatory_action(self):
        events,_=self.cluster_sources(self.sid('4a9c'))
        self.assertEqual([(e.relevance_tier,e.category,e.event_kind) for e in events],
                         [('strong','software_systems','legal_policy')])
        evidence=events[0].articles[0].evidence
        reviews=[];dispositions={}
        self.m.add_source_remainder_reviews(events,{evidence.article_id:evidence},reviews,dispositions)
        self.assertTrue(any('three years' in part['text'] for review in reviews
                            for part in review['unprocessed_evidence']))
        from apple_news_core.event_identity import source_operation_frame, build_event_identity
        title='Russia places Apple on its communications registry'
        for body in (
                'The regulator added Apple and Microsoft to its communications registry.',
                'Apple and Microsoft have been added to Russia’s communications registry.',
                'Apple was placed on Russia’s communications registry.',
                'Apple and Microsoft were listed on Russia’s communications registry.',
                'Apple faces data retention duties after being added to Russia’s state surveillance registry.'):
            frame=source_operation_frame(title,body,(),build_event_identity(title,body))
            self.assertIsNotNone(frame)
            self.assertEqual(frame.action,'regulatory-registration')
        for body in (
                'The regulator has not added Apple to its communications registry.',
                'The regulator plans to add Apple to its communications registry.',
                'Last year, the regulator added Apple to its communications registry.',
                'The regulator added Microsoft to its communications registry. Apple remains outside it.',
                'The regulator placed Apple on a sanctions list and Microsoft on its communications registry.',
                'The regulator placed Apple on a sanctions list with Microsoft on its communications registry.',
                'The regulator added Apple to its communications registry, but this claim is false.'):
            frame=source_operation_frame(title,body,(),build_event_identity(title,body))
            self.assertTrue(frame is None or frame.action!='regulatory-registration',body)
    def test_publisher_offer_roundup_does_not_require_a_numeric_price(self):
        from apple_news_core.event_identity import source_retail_invitation, build_event_identity
        row=self.rows[self.sid('fbf31')];evidence=row['evidence']
        self.assertEqual(build_event_identity(evidence['title'],evidence['raw_lead']).content_form,'deal')
        candidate=self.m.Candidate(evidence['source'],evidence['url'],evidence['title'],evidence['discovery_lead'])
        self.assertFalse(self.m.is_relevant_candidate(candidate,self.sources['MacRumors']))
        for title,body in (
                ('Weekend discounts on Apple accessories','We are tracking accessory discounts from several retailers.'),
                ('New Apple pre-order offers','It is launch week, and we’re rounding up the best pre-order offers.'),
                ('Apple weekend discounts','This weekend, we are tracking the best deals.'),
                ('Apple weekend discounts','This weekend, we are tracking the best Apple accessory deals.'),
                ('Acme accessory discounts','We are tracking the best Acme accessory deals.')):
            self.assertTrue(source_retail_invitation(title,body))
        for title,body in (
                ('Apple announces education discounts','Apple announced new education prices today. We are tracking further details.'),
                ('Regulator investigates Apple retail discounts','The regulator is investigating how retailers set discounts.'),
                ('Regulator investigates Apple retail discounts','We are tracking a regulatory investigation into Apple retail discounts.'),
                ('Apple announces education discounts','Apple announced new education prices, and we are tracking the official offers.'),
                ('Apple pre-orders open today','Apple opened pre-orders today. A retailer says we are tracking accessory discounts.'),
                ('Apple expands its service','We are tracking its rollout. Retailers have discounts.')):
            self.assertFalse(source_retail_invitation(title,body))
    def test_internal_repair_instruction_is_one_reported_operation(self):
        for prefixes in [('6534','7fdf','0929'),('0929','7fdf','6534')]:
            events,_=self.cluster_sources(*(self.sid(p) for p in prefixes))
            self.assertEqual(len(events),1)
            self.assertEqual((events[0].relevance_tier,events[0].category),('strong','hardware_products'))
    def test_software_inventory_does_not_inherit_host_hardware_category(self):
        for prefixes in [('ad20','c139'),('c139','ad20'),('29af','0f49'),('0f49','29af')]:
            with self.subTest(sources=prefixes):
                events,_=self.cluster_sources(*(self.sid(p) for p in prefixes))
                self.assertEqual(len(events),1)
                self.assertEqual((events[0].relevance_tier,events[0].category),('strong','software_systems'))
    def test_regional_announcement_keeps_its_feature_and_partner_reports(self):
        sources=('0c9b','4895','ee83','6692','68a9','e287','ac48','cd79','46a5','a41a','c0f3','50b8','86c6','e042','6939')
        for prefixes in (sources,sources[::-1]):
            events,_=self.cluster_sources(*(self.sid(p) for p in prefixes))
            self.assertEqual(len(events),1,[(e.title,e.relevance_tier) for e in events])
            self.assertEqual((events[0].relevance_tier,events[0].category),('strong','software_systems'))
    def test_announcements_keep_local_owner_stage_and_version(self):
        from apple_news_core.event_identity import source_current_report_frame, source_device_operation_frame, source_software_capability_frame
        title='Apple Intelligence comes to China with iOS 28.1'
        text='Apple today announced that Apple Intelligence will launch in China with iOS 28.1. A developer beta will be available in November.'
        frame=source_current_report_frame(title,text,(),(text,))
        self.assertEqual((frame.action,frame.model_generation),('announced-release-plan','ios-28.1'))
        opinion_text='My personal opinion is that these features are unnecessary. '+text
        opinion=source_current_report_frame('Why I hate Apple Intelligence in China',opinion_text,(),(opinion_text,))
        self.assertFalse(opinion and opinion.action=='announced-release-plan')
        for other in (text.replace('today announced','has not announced'),
                      text.replace('today announced','last year announced'),
                      text.replace('today announced','is expected to announce'),
                      'Apple Intelligence was approved in China in July. Bloomberg expects an iOS 28.1 beta later.',
                      'Apple announced the launch of Apple Intelligence in China last year. Bloomberg now expects an iOS 28.1 beta.',
                      text.replace('in China','in Japan'),
                      'Acme makes software. The company announced its alternative to Apple Intelligence in China with an iOS 28.1 beta.'):
            frame=source_current_report_frame(title,other,(),(other,))
            self.assertFalse(frame and frame.action=='announced-release-plan')
        title='Apple alerts stores to iPhone Air inner display cracking'
        text='Apple provided technicians with guidance to diagnose iPhone Air inner display cracking this week.'
        self.assertEqual(source_device_operation_frame(title,text,source_units=(text,)).action,'internal-service-guidance')
        for other in (text.replace('this week','last year'),
                      text.replace('Apple provided','Apple has not provided'),
                      text.replace('Apple provided','A repair shop provided'),
                      text.replace('iPhone Air','iPhone 20'),
                      'Apple provided stores with general safety guidance, while an independent repair shop issued instructions to technicians for iPhone Air inner display cracking.'):
            frame=source_device_operation_frame(title,other,source_units=(other,))
            self.assertFalse(frame and frame.action=='internal-service-guidance')
        title='HomeView Software 28.1 features'
        for text in ('Apple plans to release HomeView Software 28.1.',
                     'Apple has not released HomeView Software 28.1.',
                     'Apple released HomePod Software 28.1.',
                     'Last year, Apple released HomeView Software 28.1.',
                     'Apple released HomeView Software 28.1 last year.',
                     'Apple released HomeView Software 28.1, but this claim is false.'):
            frame=source_software_capability_frame(title,text,(text,))
            self.assertFalse(frame and frame.action=='software-release')
        beta=source_software_capability_frame(title,'Apple released HomeView Software 28.1 beta today.',())
        self.assertEqual(beta.action,'software-beta-release')
        title='MacBook Pro touch display: details'
        for text in ('There are settings in a third-party Windows app to turn off touch on the external monitor.',
                     'There are settings in a third-party macOS app to turn off touch on the external monitor.',
                     'The MacBook Pro has no settings to turn off touch.'):
            frame=source_software_capability_frame(title,text,(text,))
            self.assertFalse(frame and frame.subject=='macos:touch-input-control')
    def test_coordinated_actions_do_not_supply_another_owners_objects(self):
        from apple_news_core.event_identity import source_current_report_frame, source_device_operation_frame, source_software_capability_frame
        title='Apple Intelligence in China: latest rollout news'
        body='Apple today announced new developer tools for iOS 28.1, while Acme will launch its alternative to Apple Intelligence in China.'
        frame=source_current_report_frame(title,body,(),(body,))
        self.assertFalse(frame and frame.action=='announced-release-plan')
        for body in ('Apple today announced new developer tools for iOS 28.1 and Acme will launch Apple Intelligence integrations in China.',
                     'Apple today announced that Apple Intelligence will not launch in China with iOS 28.1.',
                     '苹果今日宣布，Apple 智能将不会在中国上线，iOS 28.1 不提供这一功能。'):
            frame=source_current_report_frame(title,body,(),(body,))
            self.assertFalse(frame and frame.action=='announced-release-plan')
        body='Apple today announced that Apple Intelligence will launch in China. Acme then announced its own assistant. These features will launch with iOS 28.1.'
        frame=source_current_report_frame(title,body,(),(body,))
        self.assertTrue(frame is None or not frame.model_generation)
        body='Apple released HomeView Software 28.1, while HomePod Software 28.2 remains in beta.'
        frame=source_software_capability_frame('HomeView Software 28.1 features',body,(body,))
        self.assertEqual(frame.action,'software-release')
        body='Apple provided stores with general safety guidance, and an independent repair shop issued instructions to technicians for iPhone Air inner display cracking.'
        for text in (body,body.replace(', and',' and')):
            frame=source_device_operation_frame('Apple alerts stores to iPhone Air inner display cracking',text,source_units=(text,))
            self.assertFalse(frame and frame.action=='internal-service-guidance')
    def test_coordinated_subjects_keep_their_shared_predicate(self):
        from apple_news_core.event_identity import source_clause_spans, source_current_report_frame
        for body in ('Apple Intelligence and related features will launch in China with iOS 28.1.',
                     'Apple and Alibaba will launch their service in China.'):
            self.assertEqual([body[a:b] for a,b in source_clause_spans(body)],[body])
        body='Apple announced that Apple Intelligence and related features will launch in China with iOS 28.1.'
        frame=source_current_report_frame('Apple Intelligence in China: latest rollout news',body,(),(body,))
        self.assertIsNotNone(frame)
        self.assertEqual((frame.action,frame.model_generation),('announced-release-plan','ios-28.1'))
        body='We expect 8K video next year, and the camera currently supports 4K recording at 60fps.'
        article=article_for(self.m,'Apple reports iPhone camera support',body,facts=[body])
        article.evidence=self.m.capture_article_title_evidence(article.source,article.url,article.title,body,(body,))
        plan=self.m.resolve_event_fact_plan([self.m.prepare_source_fact_view(article)],relevance_tier='strong',base_limit=2,official_limit=2)
        self.assertTrue(any('currently supports 4K recording at 60fps' in fact.text for fact in plan.required))
        self.assertFalse(any('We expect' in fact.text for fact in plan.required))
    def test_platform_key_layout_does_not_own_a_keyboard_release(self):
        events,_=self.cluster_sources(self.sid('531122'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events],
                         [('weak','hardware_products')])
        from apple_news_core.event_identity import is_platform_compatible_accessory_title
        for title in (
                'Acme keyboard launches with a native macOS layout',
                '新款机械键盘上市：原生 Mac 键位',
                'Nova keyboard for iPad debuts with a macOS key layout'):
            self.assertTrue(is_platform_compatible_accessory_title(title),title)
        for title in (
                'Apple launches a new keyboard with a native macOS layout',
                'Magic Keyboard launches with a new macOS key layout',
                '新款妙控键盘发售：原生 macOS 键位',
                'macOS adds a new keyboard layout',
                'New macOS keyboard layout supports more languages'):
            self.assertFalse(is_platform_compatible_accessory_title(title),title)
    def test_current_shop_markdown_is_a_retail_offer(self):
        from apple_news_core.event_identity import source_retail_price_offer
        events,_=self.cluster_sources(self.sid('9d9c'))
        self.assertEqual([e.relevance_tier for e in events],['weak'])
        title='5999 元：iPhone 20 渠道再次降价'
        body='iPhone 20 今日在“某电商自营店”直降至 5999 元。'
        self.assertTrue(source_retail_price_offer(title,(body,)))
        for other in (body.replace('某电商自营店','苹果官方商城'),
                      body.replace('某电商自营店','Apple Store 官方旗舰店'),
                      body.replace('今日','去年'),
                      body.replace('直降至','没有降至'),
                      body.replace('直降至','预计将降至'),
                      body.replace('直降至','将于下月降至'),
                      'iPhone 20 今日在“某电商自营店”销售，Galaxy S30 直降至 5999 元。',
                      body.replace('iPhone 20','Galaxy S30')):
            self.assertFalse(source_retail_price_offer(title,(other,)),other)
        title='6999 元：MacBook Air 官方教育价调整'
        body='苹果今天宣布，MacBook Air 在苹果教育商店降至 6999 元。'
        self.assertFalse(source_retail_price_offer(title,(body,)))
        events=self.m.cluster_articles([article_for(self.m,title,body)])
        self.assertEqual([e.relevance_tier for e in events],['strong'])
    def test_launch_time_prefix_does_not_become_a_product_owner(self):
        from apple_news_core.event_identity import _operation_owner, build_event_identity
        for prefix in ('At launch, ', 'On launch day, ', 'During the release, '):
            title=prefix+'there were more iPhone Duo in stores than online'
            self.assertEqual(_operation_owner(title),'')
            self.assertEqual(build_event_identity(title,'Apple reserved most iPhone Duo units for its stores.').scope,'apple-direct')
        self.assertEqual(_operation_owner('At launch, Acme launches a keyboard for Mac'),'acme')
        for order in [('a13ea','96577'),('96577','a13ea')]:
            events,_=self.cluster_sources(*(self.sid(p) for p in order))
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].relevance_tier,'strong')
    def test_initial_inventory_allocation_requires_the_reported_operation(self):
        from apple_news_core.event_identity import source_retail_operation_frame, named_iphone_models
        title='Where did the iPhone Airs go? Mostly to stores'
        body='Apple allocated 70% of its initial iPhone Air inventory to its retail stores.'
        self.assertEqual(named_iphone_models(title),{'iphone-air'})
        self.assertNotIn('iphone-6',named_iphone_models('iPhone 6s'))
        self.assertEqual(source_retail_operation_frame(title,body).action,'launch-inventory-channel-allocation')
        for other in (
                body.replace('Apple allocated','Last year, Apple allocated'),
                body.replace('Apple allocated','If Apple allocated'),
                body.replace('Apple allocated','Apple did not allocate'),
                body.replace('Apple allocated','A reseller allocated'),
                body.replace('iPhone Air inventory','iPhone 20 inventory'),
                body.replace('initial','replacement'),
                'Apple announced iPhone Air launch day. Its stores reported long queues.'):
            with self.subTest(body=other):
                frame=source_retail_operation_frame(title,other)
                self.assertFalse(frame and frame.action=='launch-inventory-channel-allocation')
        for other in (body.replace('initial','replacement'),
                      'Apple allocated iPhone Air inventory to its retail stores for next year’s launch.',
                      body.rstrip('.')+' last year.',
                      body.rstrip('.')+', according to a hypothetical model.'):
            frame=source_retail_operation_frame('At launch, more iPhone Air units went to stores than online',other)
            self.assertFalse(frame and frame.action=='launch-inventory-channel-allocation')
    def test_published_device_parameters_are_not_an_unreleased_disclosure(self):
        from apple_news_core.event_identity import source_device_disclosure
        title='新款 iPad mini 电池容量揭晓'
        self.assertIsNone(source_device_disclosure(title,'苹果日前发布全新一代 iPad mini。监管文件曝光了电池容量。'))
        for lead in ('Apple has introduced the new iPad mini. Regulatory records reveal its battery capacity.',
                     '苹果本周正式发布新一代 iPad mini，但电池容量今天才曝光。'):
            self.assertIsNone(source_device_disclosure(title,lead))
        for lead in ('苹果发布了新款 MacBook Pro，下一代 iPad mini 配置曝光。',
                     '苹果预计将发布新款 iPad mini，内部代码曝光其配置。'):
            self.assertIsNotNone(source_device_disclosure(title,lead))
        self.assertIsNotNone(source_device_disclosure('下一代 iPad mini 配置曝光',
            '去年，苹果发布了新款 iPad mini。下一代 iPad mini 配置曝光。'))
    def test_cpu_record_and_battery_document_keep_distinct_actions(self):
        from apple_news_core.event_identity import bind_device_measurement
        for prefix,expected in [('0d19',{'3879-9870','3993-11365'}),('3ddd',{'3879-9870'})]:
            claim=bind_device_measurement(self.source_articles(self.sid(prefix))[0].evidence)
            self.assertEqual(claim.subject,'ipad-mini')
            self.assertEqual(claim.object,'geekbench-7')
            self.assertEqual({q[2] for q in claim.qualifiers if q[1]=='measurement-record'},expected)
        for prefixes in [('e224','0d19','3ddd'),('3ddd','0d19','e224')]:
            events,_=self.cluster_sources(*(self.sid(p) for p in prefixes))
            groups={frozenset(a.evidence.article_id for a in e.articles) for e in events}
            self.assertEqual(groups,{frozenset({self.sid('e224')}),frozenset({self.sid('0d19'),self.sid('3ddd')})})
    def test_anonymous_benchmark_keeps_owner_and_polarity(self):
        from apple_news_core.event_identity import bind_device_measurement
        def claim(title,body):
            evidence=self.m.capture_article_evidence('Test','https://example.com/test',
                '<article>'+body+'</article>',title)
            return bind_device_measurement(evidence)
        for name in ('iPhone20','iPhone 20'):
            result=claim(name+'跑分曝光',f'<p>{name} 在 Geekbench 7 单核成绩为3879分，多核成绩为9870分。</p>')
            self.assertEqual(result.subject,'iphone-20')
        result=claim('iPad mini 跑分曝光','<p>iPad mini 现身 Geekbench 7。</p>'
            '<p>其并未取得单核成绩为3879分，多核成绩为9870分。</p>')
        self.assertEqual(result.polarity,'denied')
        for introduction in ('iPad mini 现身 Geekbench 7。三星的新平板也接受了测试。',
                             'iPad mini 现身 Geekbench 7。</p><p>此次测试设备是三星 Galaxy Tab。',
                             '上一代 iPad mini 现身 Geekbench 7。'):
            result=claim('iPad mini 跑分曝光',f'<p>{introduction}</p><p>其单核成绩为3879分，多核成绩为9870分。</p>')
            self.assertFalse(any(q[1]=='measurement-record' for q in result.qualifiers))
    def test_laptop_market_report_reaches_detail_without_apple_headline(self):
        from apple_news_core.collection import market_summary_needs_detail
        for title in ('TrendForce 预测：全球 OLED 笔电出货量有望在中期维持超 30% 年增幅', 'Notebook shipments forecast to rise next year'):
            self.assertTrue(market_summary_needs_detail(title))
        self.assertFalse(market_summary_needs_detail('OLED 笔电优惠选购指南'))
    def test_reader_is_not_a_third_party_manufacturer(self):
        from apple_news_core.event_identity import _operation_owner
        self.assertEqual(_operation_owner('You Can Turn Off the New MacBook Pro Touchscreen'), '')
    def test_builtin_touch_input_is_software(self):
        for prefix in ('471b','5c00','25d7'):
            with self.subTest(source=prefix):
                events,_=self.cluster_sources(self.sid(prefix))
                self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong','software_systems')])
    def test_current_input_support_limit_is_software(self):
        events,_=self.cluster_sources(self.sid('589d'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong','software_systems')])
        self.assertIn('用不了苹果手写笔',events[0].title)
        from apple_news_core.event_identity import source_software_capability_frame
        title='MacBook Pro does not support Apple Pencil input'
        body='Apple confirms that MacBook Pro currently does not support Apple Pencil as a touch input method.'
        self.assertIsNotNone(source_software_capability_frame(title,body,(body,)))
        for introduction in ('苹果发布了新款 MacBook Pro。', '苹果推出了新款 MacBook Pro。',
                             'Apple has introduced a new MacBook Pro.'):
            body=introduction+' 苹果客服称，这款笔记本目前不支持 Apple Pencil。'
            self.assertIsNotNone(source_software_capability_frame(title,body,(body,)))
        for other in (
                'Last year, Apple confirmed that MacBook Pro did not support Apple Pencil as a touch input method.',
                'Apple plans to remove Apple Pencil input support from MacBook Pro next year.',
                'An independent app on MacBook Pro does not support Apple Pencil input.',
                'Apple confirms that iPad mini does not support Apple Pencil input.',
                'Apple denies claims that MacBook Pro does not support Apple Pencil input.',
                'Apple has not confirmed that MacBook Pro does not support Apple Pencil.',
                'Apple refutes reports that MacBook Pro does not support Apple Pencil.',
                '苹果客服澄清，并非 MacBook Pro 不支持 Apple Pencil。',
                '谈到 Surface Pro，苹果线上专家称，这款笔记本目前不支持 Apple Pencil。',
                'MacBook Pro 不支持 Apple Pencil 的说法并不属实。',
                '用户询问 Surface Pro 的触控笔兼容性。苹果客服称，这款笔记本目前不支持 Apple Pencil。',
                '苹果客服展示了一台 Surface Pro，并将它与 MacBook Pro 作比较。苹果客服称，这款笔记本目前不支持 Apple Pencil。',
                'MacBook Pro 不支持 Apple Pencil，这一说法不属实。'):
            self.assertIsNone(source_software_capability_frame(title,other,(other,)))
        self.assertIsNone(source_software_capability_frame(
            'MacBook Pro teardown reveals missing Apple Pencil digitizer',
            'A teardown found that MacBook Pro lacks an Apple Pencil digitizer. MacBook Pro does not support Apple Pencil.', ()))
    def test_current_official_price_and_fault_response_are_news(self):
        for prefix in ('591e','a498'):
            with self.subTest(source=prefix):
                events,_=self.cluster_sources(self.sid(prefix))
                self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong','hardware_products')])

    def test_current_reports_and_editorial_negatives(self):
        for prefix, tier in [('b862','strong'),('dd206','strong'),('fee7','strong'),('deca','weak'),('ce0f','weak')]:
            with self.subTest(source=prefix):
                events,_=self.cluster_sources(self.sid(prefix))
                self.assertEqual([e.relevance_tier for e in events],[tier])
    def test_touch_setting_cannot_borrow_third_party_or_historical_ownership(self):
        from test_relevance_rules import article_for
        for title,body in [
            ('Why I dislike the new MacBook Pro touchscreen', 'The new MacBook Pro has an accessibility setting that allows you to turn off touch input entirely. I would never buy one because I prefer a trackpad.'),
            ('Third-party utility turns off MacBook Pro touchscreen', 'A third-party utility provides an accessibility setting to turn off touch input on the MacBook Pro.'),
            ('Looking back at the MacBook touchscreen', 'Last year, Apple demonstrations showed how macOS reshapes its controls for touch input.')]:
            with self.subTest(title=title):
                e=self.m.cluster_articles([article_for(self.m,title,body)])
                self.assertEqual([x.relevance_tier for x in e],['weak'])
    def test_market_detail_retains_the_apple_forecast(self):
        sid=next(k for k,v in self.rows.items() if '019/776' in v['evidence']['url'])
        events,_=self.cluster_sources(sid)
        self.assertTrue(any(e.relevance_tier=='strong' for e in events))

    def test_new_window_rewrites_keep_the_reported_price_and_forecast(self):
        for prefixes in [('591e','ad2b'),('e957','479e','0185')]:
            for prefix in prefixes:
                events,_=self.cluster_sources(self.sid(prefix))
                self.assertEqual([e.relevance_tier for e in events],['strong'])
            for order in (prefixes,prefixes[::-1]):
                events,_=self.cluster_sources(*(self.sid(p) for p in order))
                self.assertEqual(len(events),1)

    def test_organization_change_requires_local_apple_ownership(self):
        events,_=self.cluster_sources(self.sid('1488'))
        self.assertEqual([e.relevance_tier for e in events],['weak'])
        for text in (
            'iPhone 新品推出。银行称调整卡组织的消费限额。',
            'Apple announced a new iPhone. A bank says its organization changed.',
            'Samsung executives leave as Apple releases iPhone.',
            '苹果发布 iPhone。三星高管称管理层将调整。',
            'Apple supplies devices to a bank. The bank reports changes in its management team.',
            "Apple's design team remained unchanged, while Samsung reports a management change.",
            '苹果设计团队没有调整，银行称其组织架构发生变化。',
            '苹果高管参会，三星高管宣布离职。',
            "Samsung's management changes affect Apple's design team, according to a new report.",
            '苹果设计团队参观三星管理层重组后的办公室，报道介绍了三星的新组织架构。',
            "Samsung executives leave after meeting Apple's executives.",
            '三星高管离职后与苹果高管会面。',
            "Apple executive watches Samsung executives leave.",
            "Apple Executive Watches Samsung Executives Leave",
        ):
            self.assertFalse(self.m.is_apple_company_org_change_story(text),text)
        for text in (
            "Apple's design team has lost influence, according to a new report.",
            '报道指出苹果管理层架构出现变化。',
            'Apple executive John Smith leaves for another company.',
            '苹果高管离职并加入新公司。',
        ):
            self.assertTrue(self.m.is_apple_company_org_change_story(text),text)

    def test_author_analysis_does_not_borrow_interview_eligibility(self):
        events,_=self.cluster_sources(self.sid('7486'))
        self.assertEqual([e.relevance_tier for e in events],['weak'])
        from apple_news_core.event_identity import source_editorial_evaluation
        title='为什么新款 iPad mini 仍是 60Hz？'
        self.assertEqual(source_editorial_evaluation(title,
            '文章辨析响应速度与刷新率，并从产品线区隔角度分析这一取舍。'),'analysis')
        self.assertEqual(source_editorial_evaluation('Why is the new iPad mini still limited?',
            'This article analyses the trade-offs behind the product strategy.'),'analysis')
        self.assertFalse(source_editorial_evaluation('苹果高管解释为什么 iPad mini 没有高刷新率',
            '苹果高管在采访中介绍 OLED 像素响应速度和屏幕发声技术。'))

    def test_forecast_quantity_after_target_year_keeps_local_ownership(self):
        from apple_news_core.event_identity import source_market_report_frame
        title='预计苹果OLED版MacBook Pro 2027年出货最高达150万台'
        fact='市场研究机构TrendForce近日发布报告称，苹果新一代OLED版MacBook Pro预计将在2027年实现120万至150万台出货量。'
        frame=source_market_report_frame(title,fact,(fact,))
        self.assertIsNotNone(frame)
        self.assertEqual((frame.subject,frame.action,frame.period),('trendforce:macbook-pro','shipment-forecast','2027'))
        for other in (
            fact.replace('市场研究机构TrendForce近日发布报告称','博主引用TrendForce旧报告后声称'),
            fact.replace('苹果新一代OLED版MacBook Pro','联想OLED笔电'),
            fact.replace('MacBook Pro预计将在','MacBook Pro价格不变，整个OLED市场预计将在'),
            fact.replace('近日发布','去年发布'),
        ):
            self.assertIsNone(source_market_report_frame(title,other,(other,)),other)

    def test_tail_forecast_attribution_keeps_the_actual_speaker(self):
        from apple_news_core.event_identity import source_market_report_frame
        title='MacBook Pro could ship 2 million units in 2027'
        fact='MacBook Pro could ship between 1.2 million and 1.5 million units in 2027, according to a new forecast from market intelligence firm TrendForce.'
        self.assertIsNotNone(source_market_report_frame(title,fact,(fact,)))
        possessive=fact.replace('a new forecast from market intelligence firm TrendForce',"TrendForce’s latest forecast")
        self.assertIsNotNone(source_market_report_frame(title,possessive,(possessive,)))
        for actor in ('an independent analyst commenting on the TrendForce report',
                      'an anonymous blogger discussing TrendForce'):
            other=fact.replace('a new forecast from market intelligence firm TrendForce',actor)
            self.assertIsNone(source_market_report_frame(title,other,(other,)))

    def test_same_touch_observation_reunites_in_both_orders(self):
        ids=[self.sid(p) for p in ('471b','5c00')]
        for order in (ids,ids[::-1]):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),1)
    def test_shared_forecast_does_not_merge_a_launch(self):
        ids=[self.sid(p) for p in ('e957','0ad3','479e')]
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        events,_=self.cluster_sources(*ids,self.sid('a629'))
        self.assertEqual(len(events),2)
    def test_same_preorder_reports_reunite(self):
        events,_=self.cluster_sources(self.sid('1208'),self.sid('a629'))
        self.assertEqual(len(events),1)

    def test_reported_operations_keep_their_own_categories(self):
        for prefix,tier,category in [('9916','strong','software_systems'),('fea9','strong','software_systems'),('8db6','strong','software_systems'),('7816','strong','software_systems'),('accf','strong','software_systems'),('3996','strong','hardware_products'),('c602','strong','hardware_products'),('9cfc','strong','hardware_products'),('9e09','weak','hardware_products'),('fd7e','weak','software_systems')]:
            with self.subTest(source=prefix):
                events,_=self.cluster_sources(self.sid(prefix))
                self.assertEqual([(e.relevance_tier,e.category) for e in events],[(tier,category)])
    def test_market_forecast_keeps_numeric_object_and_speaker(self):
        from apple_news_core.event_identity import source_market_report_frame
        title='TrendForce OLED notebook shipment forecast'
        for body in [
            'Following the introduction of the MacBook Pro, TrendForce expects global OLED notebook shipments to reach 46 million units in 2030.',
            'TrendForce 预计，随着 MacBook Pro 加入市场，2027 年全球 OLED 笔记本出货量将达 1800 万台。',
            'TrendForce expects Lenovo notebook shipments to reach 20 million units in 2027, while the MacBook Pro has an OLED display.',
            'TrendForce previously forecast MacBook Pro shipments of 2 million units in 2027. There is no new forecast in this report.',
            'TrendForce published a report on display pricing. An anonymous blogger expects MacBook Pro shipments to reach 2 million units in 2027.']:
            with self.subTest(body=body):
                self.assertIsNone(source_market_report_frame(title,body,(body,)))
        body='TrendForce expects MacBook Pro shipments to reach 2 million units in 2027.'
        self.assertIsNotNone(source_market_report_frame(title,body,(body,)))
    def test_personal_commentary_does_not_become_a_native_feature_report(self):
        from test_relevance_rules import article_for
        title='MacBook Pro touchscreen: my personal take'
        body='The new MacBook Pro has an accessibility setting that allows you to turn off touch input entirely. I would never buy one because I prefer a trackpad.'
        events=self.m.cluster_articles([article_for(self.m,title,body)])
        self.assertEqual([e.relevance_tier for e in events],['weak'])

    def test_forecast_rejects_a_locally_reassigned_speaker(self):
        from apple_news_core.event_identity import source_market_report_frame
        for body in [
            'TrendForce published a report about the OLED notebook market. According to independent analyst Jane Doe, MacBook Pro is expected to ship 2 million units in 2027.',
            'TrendForce 发布了全球 OLED 笔记本市场预测。另一位博主表示，MacBook Pro 2027 年预计出货 200 万台。',
            'TrendForce published an OLED market report. MacBook Pro is expected to ship 3 million units in 2027, according to independent analyst Jane Doe.',
            'TrendForce published an OLED market report. Analyst Jane Doe offered a separate estimate. MacBook Pro is expected to ship 3 million units in 2027.',
            'TrendForce published an OLED market report. Analyst Jane Doe disputed the TrendForce estimate. MacBook Pro is expected to ship 3 million units in 2027.',
            'TrendForce 发布了全球 OLED 市场预测。MacBook Pro 2027 年预计出货 300 万台，另一位博主称。']:
            self.assertIsNone(source_market_report_frame('TrendForce OLED notebook forecast',body,(body,)))
    def test_native_controls_do_not_change_an_opinion_reporting_subject(self):
        from test_relevance_rules import article_for
        for title, body in [
            ('Why the MacBook Pro touchscreen controls are a mistake', 'The new MacBook Pro has an accessibility setting that allows you to turn off touch input entirely. I think it is a pointless gimmick and would never buy it.'),
            ('MacBook Pro touch controls make no sense', 'The new MacBook Pro has an accessibility setting that allows you to turn off touch input entirely. I think it is a pointless gimmick and would never buy it.'),
            ('MacBook color calibration is overrated', 'The MacBook Pro supports Apple Pro Display Calibrator. I think the feature is pointless for most users and would not pay more for it.'),
            ('Why MacBook color calibration is overrated', 'The MacBook Pro supports Apple Pro Display Calibrator. I think it is a pointless gimmick and would never buy it.')]:
            events=self.m.cluster_articles([article_for(self.m,title,body)])
            self.assertEqual([e.relevance_tier for e in events],['weak'])
    def test_interview_pronoun_cannot_cross_a_new_speaker(self):
        from apple_news_core.event_identity import bind_leadership_report
        for previous in ('随后记者王明接受了专访。','记者王明在节目中评价了特努斯。'):
            text='苹果CEO约翰·特努斯接受采访。'+previous+'他在专访中表示，苹果决定放弃触屏Mac。'
            evidence=self.m.capture_article_title_evidence('IT之家','https://example.com/interview','苹果CEO特努斯回应触控决定',text,(text,))
            claim=bind_leadership_report(evidence)
            self.assertTrue(claim is None or claim.report_role!='independent')

    def test_author_aside_does_not_replace_the_reported_capability(self):
        from test_relevance_rules import article_for
        for title,body in [
            ('You Can Turn Off the New MacBook Pro Touchscreen', 'The new MacBook Pro models with OLED displays have an accessibility setting that allows you to turn off touch input entirely, according to MacStories editor-in-chief Federico Viticci. I think this is a welcome option.'),
            ('MacBook Pro supports display calibration', 'The MacBook Pro supports Apple Pro Display Calibrator. I think this will be useful for professionals.')]:
            events=self.m.cluster_articles([article_for(self.m,title,body)])
            self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong','software_systems')])

    def test_forecast_continuation_and_regional_asset_observation(self):
        for prefixes in [('e957','d23b'),('e4e0','3637')]:
            with self.subTest(sources=prefixes):
                for prefix in prefixes:
                    events,_=self.cluster_sources(self.sid(prefix))
                    self.assertEqual([e.relevance_tier for e in events],['strong'])
                events,_=self.cluster_sources(*(self.sid(p) for p in prefixes))
                self.assertEqual(len(events),1)

    def test_website_asset_requires_a_current_observation(self):
        from apple_news_core.event_identity import build_event_identity, source_named_publication_frame
        title='苹果 MacBook Pro 韩国官网宣传图变化'
        for body in ('去年苹果在韩国官网移除了宣传图。', '假想设计：韩国官网画面换成了另一张图片。',
                     '苹果发布了新款MacBook Pro。另一个产品iPad mini的韩国官网宣传图换成了新画面。',
                     '苹果发布了新款MacBook Pro。随后三星韩国官网宣传图换成了新画面。'):
            self.assertIsNone(source_named_publication_frame(title,body,(body,),build_event_identity(title,body)))
        from apple_news_core.event_identity import source_market_report_frame
        for body in (
                'TrendForce 预计 MacBook Pro 出货增长。联想新机本月发布。TrendForce预计，该款新机2027年的出货量将达到120万至150万台。',
                '苹果新款MacBook Pro采用OLED屏幕。这一变化促使联想推出了新款OLED笔记本。TrendForce预计，该款新机2027年的出货量将达到120万至150万台。'):
            self.assertIsNone(source_market_report_frame('TrendForce 笔记本出货预测',body,(body,)))

    def test_port_target_is_not_the_device_named_in_the_os_edition(self):
        events,_=self.cluster_sources(self.sid('5adb'))
        self.assertEqual([e.relevance_tier for e in events],['weak'])

    def test_third_party_specification_identity_keeps_model_and_action(self):
        from test_relevance_rules import article_for
        first=article_for(self.m,'联想 IdeaPad Vibe 完整规格曝光，正面对决 MacBook Neo',
                          "Lenovo disclosed the IdeaPad Vibe specifications, compared with Apple's MacBook Neo.")
        for title,body in [
            ('联想 IdeaPad Slim 完整规格曝光，正面对决 MacBook Neo', "Lenovo disclosed IdeaPad Slim specifications, compared with Apple's MacBook Neo."),
            ('联想 IdeaPad Vibe 开启预购，完整规格对标 MacBook Neo', "Lenovo opened preorders for IdeaPad Vibe, compared with Apple's MacBook Neo.")]:
            second=article_for(self.m,title,body)
            for pair in ([first,second],[second,first]):
                self.assertEqual(len(self.m.cluster_articles(pair)),2)
        second=article_for(self.m,'联想 IdeaPad Vibe 开启预购，正面对决 MacBook Neo', 'Lenovo opened preorders for IdeaPad Vibe, compared with MacBook Neo.')
        self.assertEqual(len(self.m.cluster_articles([first,second])),2)
        denial=article_for(self.m,'联想否认 IdeaPad Vibe 完整规格曝光，对比 MacBook Neo', 'Lenovo denied that IdeaPad Vibe specifications were disclosed.')
        self.assertEqual(len(self.m.cluster_articles([first,denial])),2)
        disclosed=article_for(self.m,'IdeaPad Vibe specifications revealed, compared with MacBook Neo', 'Lenovo has revealed IdeaPad Vibe specifications, compared with MacBook Neo.')
        denied=article_for(self.m,'IdeaPad Vibe specifications revealed? Compared with MacBook Neo', 'Lenovo says IdeaPad Vibe specifications were not revealed.')
        for pair in ([disclosed,denied],[denied,disclosed]):
            self.assertEqual(len(self.m.cluster_articles(pair)),2)
        models=[article_for(self.m,f'联想 ThinkPad X1 Carbon Gen {g} 完整规格曝光，对比 MacBook Neo',
                            f'Lenovo disclosed ThinkPad X1 Carbon Gen {g} specifications compared with MacBook Neo.')
                for g in (13,14)]
        for pair in (models,models[::-1]):
            self.assertEqual(len(self.m.cluster_articles(pair)),2)

    def test_localized_product_page_reports_the_website_asset(self):
        events,_=self.cluster_sources(self.sid('03b5'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events],[('strong','software_systems')])

    def test_hypothetical_website_layout_is_not_a_current_observation(self):
        from test_relevance_rules import article_for
        title='Apple Avoids Showing Pinched Fingers on iPad Mini Page in South Korea'
        body='In a hypothetical redesign, on its South Korean website, Apple simply shows an image of the iPad mini on its own.'
        events=self.m.cluster_articles([article_for(self.m,title,body)])
        self.assertEqual([e.relevance_tier for e in events],['weak'])

    def test_app_store_review_delay_keeps_affected_application_scope(self):
        events,_=self.cluster_sources(self.sid('6788'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events], [('strong','software_systems')])
        from apple_news_core.event_identity import build_event_identity, source_object_operation_frame
        title='《星图》中国版：App Store 审核超时导致更新延迟'
        body='开发者表示，受 App Store 审核流程超时影响，《星图》中国版 iOS 客户端本次更新延期。'
        frame=source_object_operation_frame(title,body,(),build_event_identity(title,body))
        self.assertIsNotNone(frame)
        self.assertIn('星图',frame.subject)
        self.assertNotEqual(frame.action,'service-outage')
        from test_relevance_rules import article_for
        other=article_for(self.m,title.replace('星图','蓝图'),body.replace('星图','蓝图'))
        first=article_for(self.m,title,body)
        for pair in ([first,other],[other,first]):
            self.assertEqual(len(self.m.cluster_articles(pair)),2)
        restored=article_for(self.m,'《星图》中国版审核完成，更新恢复上线',
            '《星图》中国版 App Store 审核超时问题已解决，更新已经正常上线。')
        for pair in ([first,restored],[restored,first]):
            self.assertEqual(len(self.m.cluster_articles(pair)),2)

    def test_app_store_context_does_not_create_a_review_delay(self):
        from apple_news_core.event_identity import build_event_identity, source_object_operation_frame
        title='《星图》中国版：App Store 审核超时导致更新延迟'
        for body in (
            '开发者称《星图》已提交 App Store 审核，正在等待正常处理，预计下周更新。',
            '开发者为改进内容主动推迟《星图》更新，App Store 审核没有超时。',
            'Google Play 审核流程超时导致《星图》更新延迟，App Store 版本已正常发布。',
            '去年受 App Store 审核流程超时影响，《星图》中国版更新延期。',
            '开发者否认《星图》因 App Store 审核超时而延期的说法。',
            '《蓝图》受 App Store 审核流程超时影响延后更新。《星图》按计划上线。',
            '《星图》中国版按计划上线，其他应用出现 App Store 审核超时。',
            '受 App Store 审核超时影响，《星图》国际版更新延期，中国版按计划上线。',
            '《星图》中国版 App Store 审核超时问题已解决，更新已经正常上线。'):
            with self.subTest(body=body):
                frame=source_object_operation_frame(title,body,(),build_event_identity(title,body))
                self.assertFalse(frame and frame.action=='review-processing-delay')

    def test_failed_feed_does_not_hide_title_only_discovery_gap(self):
        from unittest import mock
        m=self.m
        source=self.sources['cnBeta']
        sparse=m.Candidate(source.name,'https://www.cnbeta.com.tw/articles/tech/1584414.htm',
            '百度网盘为什么禁用传感器还能跳转摇一摇广告？因为还读取磁力计数据')
        rich=m.Candidate(source.name,sparse.url,sparse.title,'苹果 iOS 27.2 调整运动与健身权限。')
        for feed_ok, other_warning in ((False,False),(False,True),(True,False)):
            with self.subTest(feed_ok=feed_ok,other_warning=other_warning):
                diagnostics={'source_listing_pagination': {'https://elsewhere.example/': {'stop_reason':'window-covered'}}}
                if other_warning:
                    diagnostics['collection_warnings']=[{'source':source.name,'url':source.pages[0],
                        'reason':'empty-page','coverage':'unconfirmed'}]
                def fetch(url,*args,**kwargs):
                    return 'listing' if url not in source.feeds or feed_ok else None
                with mock.patch.object(m,'fetch_url',side_effect=fetch), \
                     mock.patch.object(m,'parse_html_links',return_value=[sparse]), \
                     mock.patch.object(m,'parse_xml_feed',return_value=[rich]):
                    m.collect_candidates(source,Path('/unused-cache'),diagnostics)
                warnings=[w for w in diagnostics.get('collection_warnings',[]) if w['reason']=='feed-discovery-failed']
                self.assertEqual([w['url'] for w in warnings],[] if feed_ok else source.feeds)
                if other_warning:
                    self.assertEqual(diagnostics['collection_warnings'][0]['reason'],'empty-page')

    def test_submitted_os_driver_adaptation_is_software_ecosystem(self):
        events,_=self.cluster_sources(self.sid('17e6'))
        self.assertEqual([(e.relevance_tier,e.category) for e in events],[('ecosystem','software_systems')])
        from apple_news_core.event_identity import source_independent_software_frame
        title='Intel Mac 的 Orbit 驱动适配补丁提交'
        body='Intel Mac 用户在 Linux 下获得驱动适配。开发者向内核邮件列表提交了 RFC 补丁，采用 orbit 驱动新增 Intel Mac 后端。'
        frame=source_independent_software_frame(title,body,())
        self.assertIsNotNone(frame)
        self.assertEqual(frame.action,'os-driver-patch-submission')
        self.assertIn('orbit',frame.subject)
        comparison=body.replace('采用 orbit 驱动', '相比旧 legacy 驱动，orbit 驱动')
        self.assertIn('linux-driver:orbit:',source_independent_software_frame(title,comparison,()).subject)
        unrelated=body+'另一项目的 nova 驱动今天已正式合入内核。'
        self.assertEqual(source_independent_software_frame(title,unrelated,()).action,'os-driver-patch-submission')
        unrelated=body+'另一项目的 nova 驱动也有一组补丁。这些补丁今天已正式合入内核。'
        self.assertEqual(source_independent_software_frame(title,unrelated,()).action,'os-driver-patch-submission')
        merged=body+'今天这些补丁已正式合入内核。'
        self.assertEqual(source_independent_software_frame(title,merged,()).action,'os-driver-patch-merge')
        for other in (
            'Intel Mac 用户在 Linux 下等待适配。开发者计划向内核邮件列表提交 RFC 补丁，采用 orbit 驱动。',
            'Intel Mac 用户在 Linux 下等待适配。开发者否认已向内核邮件列表提交 RFC 补丁，采用 orbit 驱动。',
            'Intel Mac 用户在 Linux 下运行 orbit 驱动。去年开发者向内核邮件列表提交了 RFC 补丁。',
            '开发者向内核邮件列表提交了 RFC 补丁，orbit 驱动只支持 ThinkPad，Intel Mac 是对照背景。',
            '开发者向内核邮件列表提交了 RFC 补丁，在 ThinkPad 上移植 Apple 软件，采用 orbit 驱动。',
            'Intel Mac 用户在 Linux 下运行 orbit 应用。开发者发布普通应用更新，没有提交内核补丁。',
            'Intel Mac 用户在 Linux 下运行 orbit 驱动。此前提交的 RFC 补丁现已合入内核。',
            'Intel Mac 用户在 Linux 下已运行 orbit 驱动。开发者向内核邮件列表提交了 RFC 补丁，新增仅支持 ThinkPad 的 nova 驱动。',
            'Intel Mac 用户在 Linux 下已运行 orbit 驱动，去年新增 Intel Mac 后端。开发者今天向内核邮件列表提交了 RFC 补丁，新增仅支持 ThinkPad 的 nova 驱动。',
            'Intel Mac 用户在 Linux 下等待适配。开发者向内核邮件列表提交了 RFC 补丁，但 orbit 驱动没有新增 Intel Mac 后端，仅支持 ThinkPad。',
            body + '今天这些补丁已正式合入内核。'):
            with self.subTest(body=other):
                frame=source_independent_software_frame(title,other,())
                self.assertFalse(frame and frame.action=='os-driver-patch-submission')

    def test_acquisition_stage_ignores_comparison_background(self):
        from apple_news_core.event_identity import source_acquisition_frame
        for order in (('7ecc','659e'),('659e','7ecc')):
            events,_=self.cluster_sources(*(self.sid(p) for p in order))
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].relevance_tier,'strong')
        title='苹果收购企业软件公司 Orion'
        for body in ('苹果近日完成对 Orion 的收购，不过与此前收购消费应用不同，Orion 从事企业业务。',
                     'Apple has acquired Orion, whereas previously it bought consumer apps.'):
            self.assertEqual(source_acquisition_frame(title,body).action,'acquisition-announcement')
        self.assertEqual(source_acquisition_frame('Apple acquired Orion last year', 'Apple acquired Orion last year.').action,'acquisition-historical')
        self.assertEqual(source_acquisition_frame('Apple acquired Orion', 'Reports said Apple acquired Orion, but Apple denies acquiring Orion.').action,'acquisition-denial')

    def test_acquisition_name_compatibility_characters_and_function(self):
        from apple_news_core.event_identity import source_acquisition_frame
        for order in (('7ecc','659e','972b'),('972b','659e','7ecc')):
            events,_=self.cluster_sources(*(self.sid(p) for p in order))
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].category,'software_systems')
        for name in ('Orion.io','Orion․io','Ｏｒｉｏｎ．ｉｏ'):
            frame=source_acquisition_frame('Apple acquires '+name, 'Apple acquired '+name+', a data engineering company.')
            self.assertEqual(frame.subject,'apple-acquisition:orion.io')
            self.assertEqual(frame.category,'software_systems')
        frame=source_acquisition_frame('Apple acquires Orion sensor manufacturer','Apple acquired Orion, a supplier of physical sensors.')
        self.assertEqual(frame.category,'hardware_products')
        for body in ('Apple has acquired Orion, a maker of storage controllers. Apple will use its chips for data management.',
                     'Apple has acquired Orion, a sensor company that Apple will use for data management.'):
            self.assertEqual(source_acquisition_frame('Apple acquires Orion',body).category,'hardware_products')
        for body in ('Apple acquired Orion, a company focused on sensors rather than data engineering.',
                     'Apple acquired Orion, a company focused on not data engineering.'):
            self.assertEqual(source_acquisition_frame('Apple acquires Orion',body).category,'hardware_products')
        alias=source_acquisition_frame('Apple acquires Orion.io',
            'The filing reveals a deal between Apple and Nimbus Labs, Inc., better known as Orion.io.')
        self.assertEqual(alias.subject,'apple-acquisition:orion.io')
        other=source_acquisition_frame('Apple acquires Orion.io',
            'The filing reveals a deal between Apple and Nimbus Labs, while another company Vega is better known as Orion.io.')
        self.assertEqual(other.subject,'apple-acquisition:nimbus-labs')

    def test_writer_prediction_roles_do_not_gain_required_status_from_numbers(self):
        for text in ("I'd expect macOS 31 to add new controls next year.",
                     "I’d expect macOS 31 to add new controls next year.",
                     "We would expect macOS 31 to add new controls next year."):
            self.assertEqual(self.m.source_fact_statement_role(text), 'editorial')
        self.assertEqual(self.m.source_fact_statement_role(
            '记者 Jordan Lee 认为苹果仍在调整界面，并预计 macOS 31 将增加新控件。'), 'unverified-attribution')
        self.assertEqual(self.m.source_fact_statement_role('Reporter Jordan Lee expects new controls in macOS 31.'), 'unverified-attribution')
        for text in ('据科技媒体报道记者 Jordan Lee 预计 macOS 31 将增加新控件。',
                     '据科技媒体报道，记者 Jordan Lee 预计 macOS 31 将增加新控件。'):
            self.assertEqual(self.m.source_fact_statement_role(text), 'unverified-attribution')
        for text in ("Reporter Jordan Lee expects new controls in macOS 31, according to people familiar with Apple's plans.",
                     "Reporter Jordan Lee expects new controls in macOS 31, citing employees she interviewed.",
                     "According to people familiar with Apple's plans, reporter Jordan Lee expects new controls in macOS 31."):
            self.assertEqual(self.m.source_fact_statement_role(text), 'report')

        for text in ('I tested the controls on macOS 31 and observed a 20ms response.',
                     'The controls responded faster than I had expected in the test.',
                     '分析师 Jordan Lee 预计苹果明年出货150万台。',
                     '记者 Jordan Lee 据知情人士透露的计划报道，苹果将在 macOS 31 增加新控件。',
                     'Apple says it expects macOS 31 to add new controls next year.'):
            self.assertNotIn(self.m.source_fact_statement_role(text), {'editorial', 'unverified-attribution'}, text)
        for order in (('d6f6','fee7'),('fee7','d6f6')):
            events, output = self.cluster_sources(*(self.sid(p) for p in order))
            public = '\n'.join(e['summary']+'\n'+'\n'.join(e['key_facts']+e.get('must_include_facts', [])) for e in output)
            self.assertNotIn('并预计明年发布的 macOS 28', public)
            self.assertNotIn('I’d expect', public)
            self.assertIn('才刚刚开始', public)
            pending = [f for e in events for f in e.fact_plan.unprocessed]
            self.assertTrue(any('unverified-attribution' in f.roles and 'Chris Welch' in f.text for f in pending))
            for f in pending:
                if 'Chris Welch' not in f.text:
                    continue
                self.assertNotIn('source-numeric-detail', f.roles)
                for _, _, sid, unit_id, start, end in f.origins:
                    if unit_id:
                        unit = next(u for u in self.rows[sid]['evidence']['units'] if u['unit_id']==unit_id)
                        self.assertEqual(f.text, unit['text'][start:end])

    def test_writer_review_keeps_reporting_context_without_orphan_required_prefix(self):
        from apple_news_core.article_processing import capture_article_title_evidence
        title = 'Apple reports current Mac touch controls'
        observed = 'Apple says the Mac currently supports touch controls in macOS 31.'
        for text, review in (
            ('据科技媒体报道，记者 Jordan Lee 预计 macOS 31 将增加新控件。', True),
            ('据科技媒体报道记者 Jordan Lee 预计 macOS 31 将增加新控件。', True),
            ('报道称，作者李明认为 macOS 31 会增加新控件。', True),
            ("Reporter Jordan Lee expects macOS 31 to add new controls, citing Apple employees who declined to discuss future plans.", True),
            ("According to people who have not confirmed future plans, reporter Jordan Lee expects macOS 31 to add new controls.", True),
            ("Reporter Jordan Lee expects new controls in macOS 31, according to people familiar with Apple's plans.", False),
            ("Reporter Jordan Lee expects new controls in macOS 31, citing Apple employees she interviewed.", False),
        ):
            with self.subTest(text=text):
                article = article_for(self.m, title, observed+' '+text, facts=[observed,text])
                article.evidence = capture_article_title_evidence(article.source,article.url,title,observed,(observed,text))
                plan = self.m.resolve_event_fact_plan([self.m.prepare_source_fact_view(article)], relevance_tier='strong',base_limit=2,official_limit=2)
                required = [f.text for f in plan.required]
                self.assertIn(observed,required)
                if review:
                    self.assertEqual(required,[observed])
                    self.assertTrue(any(text == f.text and 'unverified-attribution' in f.roles for f in plan.unprocessed))
                else:
                    self.assertIn(text,required)
