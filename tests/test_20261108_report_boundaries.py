import json
from datetime import datetime, timezone
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as batch

class ReportBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent/'fixtures/20261108_report_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,11,8,tzinfo=timezone.utc))}
    source_articles = batch.PureJsonBatchTests.source_articles
    cluster_sources = batch.PureJsonBatchTests.cluster_sources
    def check_sources(self, prefixes, category, tier, count=1):
        ids=[k for k in self.rows if any(k.startswith(p) for p in prefixes)]
        self.assertEqual(len(ids),len(prefixes))
        for order in ((ids,ids[::-1]) if len(ids)>1 else (ids,)):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),count,[(e.title,e.relevance_tier) for e in events])
            self.assertTrue(all((e.category,e.relevance_tier)==(category,tier) for e in events),[(e.category,e.relevance_tier) for e in events])
    def test_research_owner_is_not_the_experimental_hardware_vendor(self):
        self.check_sources(['db0e','85ce'],'software_systems','strong')
    def test_launch_dataset_uses_reporter_and_period_across_headline_angles(self):
        self.check_sources(['2567','5f8e'],'hardware_products','strong')
    def test_host_side_sensor_protocol_is_platform_interoperability(self):
        self.check_sources(['b616'],'software_systems','ecosystem')
    def test_actual_os_adaptation_on_mac_is_not_a_hardware_mod(self):
        self.check_sources(['223a'],'software_systems','ecosystem')
    def test_emulator_execution_keeps_apple_platform_object(self):
        self.check_sources(['c0a1'],'software_systems','ecosystem')
    def test_actual_display_operation_test_is_not_generic_buying_advice(self):
        self.check_sources(['e48c'],'software_systems','strong')
    def test_software_deployment_survey_is_not_hardware_sales(self):
        self.check_sources(['0361'],'software_systems','strong')
    def test_individual_physical_failure_is_not_official_price_publication(self):
        self.check_sources(['64cc'],'hardware_products','strong')
    def test_editorial_framing_does_not_establish_a_new_product_report(self):
        events,_=self.cluster_sources(next(k for k in self.rows if k.startswith('a53f')))
        self.assertTrue(all(e.relevance_tier=='weak' for e in events))
    def test_independent_app_cannot_borrow_hardware_control_background(self):
        for p in ['38db','eac5','393b']:
            events,_=self.cluster_sources(next(k for k in self.rows if k.startswith(p)))
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),p)
    def test_primary_ifanr_discovery_is_retained_without_dead_feed(self):
        s=self.sources['爱范儿']
        self.assertEqual(s.feeds,['https://www.ifanr.com/feed'])
        self.assertIn('https://www.ifanr.com/',s.pages)
    def test_research_requires_apple_authorship_and_current_publication(self):
        from apple_news_core.event_identity import source_named_publication_frame, build_event_identity
        title = '苹果研究团队披露机器人控制研究'
        body = '苹果研究团队在预印本平台提交论文《Adaptive Motion from Vision》，披露了新的控制系统。'
        def bind(text):
            return source_named_publication_frame(title,text,(text,),build_event_identity(title,text))
        self.assertIsNotNone(bind(body))
        for text in (body.replace('苹果研究团队','大学研究团队'),
                     body.replace('提交论文','计划提交论文'),
                     body.replace('提交论文','没有提交论文'),
                     '去年，'+body,
                     '苹果研究团队介绍工作，大学研究团队提交论文《Adaptive Motion from Vision》。'):
            with self.subTest(text=text):
                self.assertIsNone(bind(text))
        self.assertNotEqual(bind(body).subject,bind(body.replace('Motion','Navigation')).subject)

    def test_dated_dataset_preserves_reporter_period_model_and_stage(self):
        from apple_news_core.event_identity import source_weekly_device_measurement as bind
        title = 'iPhone Duo首周销量曝光'
        body = '数码博主 @海岸观测 今日曝光了iPhone Duo销量数据，2026年10月19日-10月25日期间合计约12万台。'
        frame = bind(title,body)
        self.assertIsNotNone(frame)
        self.assertNotEqual(frame.subject,bind(title,body.replace('海岸','高原')).subject)
        self.assertNotEqual(frame.period,bind(title,body.replace('25日','26日')).period)
        self.assertNotEqual(frame.year,bind(title,body.replace('2026','2027')).year)
        for text in (body.replace('今日曝光','计划公布'), body.replace('今日曝光','并未公布'),
                     body.replace('合计','预计'), body.replace('iPhone Duo','iPhone Air'),
                     body.replace('10月19日-10月25日','上周'), '去年，'+body):
            with self.subTest(text=text):
                self.assertIsNone(bind(title,text))

    def test_os_demonstration_requires_actual_apple_host_and_implementation(self):
        from apple_news_core.event_identity import source_independent_software_frame as bind
        title = '网友成功将MacBook Pro刷入NovaOS 6系统'
        body = '网友为一台苹果MacBook Pro成功刷入了NovaOS 6系统。'
        implementation = '视频显示应用小窗正常，开发者表示嫁接Linux内核后仍有问题。'
        self.assertEqual(bind(title,body,(body,implementation)).tier,'ecosystem')
        for text,detail in ((body.replace('成功刷入了','计划刷入'),implementation),
                           (body.replace('成功刷入了','未能刷入'),implementation),
                           (body.replace('MacBook Pro','华为电脑'),implementation),
                           ('去年，'+body,implementation), (body,'')):
            with self.subTest(text=text,detail=detail):
                self.assertIsNone(bind(title,text,(text,detail)))

    def test_host_protocol_requires_implemented_operation(self):
        from apple_news_core.event_identity import source_independent_software_frame as bind
        title = 'AirPods head tracking works on Linux'
        body = 'The Orbit project, which reads the motion sensor data of AirPods Pro in Linux, implements a new protocol.'
        self.assertEqual(bind(title,body,(body,)).tier,'ecosystem')
        for text in (body.replace('which reads','which will read'),body.replace('which reads','which cannot read'),
                     body.replace('AirPods Pro','Galaxy Buds'), 'Last year, '+body):
            with self.subTest(text=text):
                self.assertIsNone(bind(title,text,(text,)))

    def test_emulation_does_not_borrow_other_platform_or_future_target(self):
        from apple_news_core.event_identity import source_independent_software_frame as bind
        title = 'Switch游戏可在iPhone上运行'
        body = '开发者林晨展示了Switch游戏在iPhone 18上运行的画面。'
        detail = '林晨表示，移植过程中针对iOS内存限制进行了优化。'
        self.assertEqual(bind(title,body,(body,detail)).tier,'ecosystem')
        for text,extra in ((body.replace('展示了','计划展示'),detail),
                           (body.replace('展示了','尚未展示'),detail),
                           (body.replace('iPhone 18','PS5'),detail),
                           ('去年，'+body,detail),
                           (body,'另一名开发者移植了PS5模拟器。')):
            with self.subTest(text=text,extra=extra):
                self.assertIsNone(bind(title,text,(text,extra)))

    def test_display_test_does_not_promote_plans_or_generic_app_availability(self):
        from apple_news_core.event_identity import source_device_behavior_test_frame as bind
        title = 'iPhone Duo游戏适配表现测试'
        body = '实际体验iPhone Duo时，折叠展开时视野没有拉伸，操作按键布局跟随屏幕重排。'
        self.assertIsNotNone(bind(title,'',(body,)))
        for text in (body.replace('实际体验','计划进行实际体验'),
                     body.replace('实际体验','没有进行实际体验'),
                     '去年，'+body,
                     '这款第三方游戏发布新版本，支持折叠展开和布局调整。'):
            with self.subTest(text=text):
                self.assertIsNone(bind(title,'',(text,)))

    def test_physical_incident_and_official_fee_table_remain_different(self):
        from apple_news_core.event_identity import source_device_operation_frame, source_service_fee_frame
        title = '男子称iPhone Duo用了四天黑屏：维修报价过万元'
        body = '张先生称自己买的iPhone Duo用了四天就黑屏了，机器已送检。'
        self.assertEqual(source_device_operation_frame(title,body).category,'hardware_products')
        for text in (body.replace('就黑屏了','没有黑屏'),body.replace('就黑屏了','不再黑屏'),
                     body.replace('就黑屏了','没有发生黑屏'),body.replace('就黑屏了','尚未出现黑屏'),
                     body.replace('iPhone Duo','三星手机'),'去年，'+body):
            with self.subTest(text=text):
                self.assertIsNone(source_device_operation_frame(title,text))
        table = '苹果官网公布了iPhone Duo维修费用，内屏保外维修收费7998元。'
        self.assertIsNone(source_service_fee_frame(title,body,(table,)))
        self.assertIsNotNone(source_service_fee_frame('苹果公布iPhone Duo维修费用',table,(table,)))

    def test_named_app_ownership_does_not_capture_apple_or_unrelated_developer(self):
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform as check
        title = "'Glowpad' Lets You Customize MacBook Pro's Logo"
        body = 'A new "Glowpad" app created by designer Jane Stone lets you customize the MacBook logo.'
        self.assertTrue(check(title,body,named_only=True))
        self.assertFalse(check(title,body.replace('designer Jane Stone','Apple'),named_only=True))
        self.assertFalse(check(title,body.replace('Glowpad','Otherpad'),named_only=True))

    def test_editorial_forecast_preserves_separately_reported_disclosure(self):
        from apple_news_core.event_identity import source_editorial_outlook as check
        title = 'iPhone Air has something to prove'
        opinion = 'It seems obvious to me that it needs to appeal to a wider audience.'
        self.assertTrue(check(title,opinion,(opinion,)))
        news = 'A new report from Bloomberg today reveals a redesigned antenna for iPhone Air.'
        self.assertFalse(check(title,news,(news,opinion)))
    def test_same_dataset_dates_do_not_merge_different_markets(self):
        articles=[]
        for region,value in [('中国',12),('美国',20)]:
            title=f'iPhone Duo{region}首周销量曝光'
            body=f'数码博主 @海岸观测 今日曝光了iPhone Duo在{region}的销量数据，2026年10月19日-10月25日期间合计约{value}万台。'
            articles.append(article_for(self.m,title,body,source='IT之家'))
        for order in (articles,articles[::-1]):
            events=self.m.cluster_articles(order)
            self.assertEqual(len(events),2)
            self.assertTrue(all(len(e.articles)==1 for e in events))

    def test_publication_cannot_borrow_another_research_team(self):
        from apple_news_core.event_identity import source_named_publication_frame,build_event_identity
        title='苹果研究团队介绍机器人研究'
        body='苹果研究团队在交流会上介绍，大学研究团队提交论文《Adaptive Motion from Vision》，披露了控制系统。'
        self.assertIsNone(source_named_publication_frame(title,body,(),build_event_identity(title,body)))
        joined=body.replace('介绍，','听到')
        self.assertIsNone(source_named_publication_frame(title,joined,(),build_event_identity(title,joined)))
        self.assertEqual(self.m.classify_relevance_tier(title,body,(),'IT之家')[0],'weak')

    def test_display_result_cannot_borrow_another_device(self):
        from apple_news_core.event_identity import source_device_behavior_test_frame
        title='iPhone Duo游戏适配表现如何：先看另一款折叠屏'
        lead='本文先介绍三星Galaxy Fold的表现。'
        facts=('实际体验三星Galaxy Fold，折叠展开时视野没有拉伸，操作按键布局跟随屏幕重排。',)
        self.assertIsNone(source_device_behavior_test_frame(title,lead,facts))
        self.assertEqual(self.m.classify_relevance_tier(title,lead,facts,'IT之家')[0],'weak')

    def test_deployment_survey_requires_apple_in_the_surveyed_population(self):
        from apple_news_core.event_identity import source_named_publication_frame,build_event_identity
        title='Mac admins discuss AI scripts'
        body='Fleet surveyed more than 250 enterprise IT workers who manage Windows. The report covered scripts and configurations.'
        self.assertIsNone(source_named_publication_frame(title,body,(),build_event_identity(title,body)))
        self.assertEqual(self.m.classify_relevance_tier(title,body,(),'IT之家')[0],'weak')

    def test_screen_negation_stays_with_its_surface(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title='用户反馈iPhone Duo内屏开裂'
        body='用户反馈iPhone Duo外屏没有开裂但内屏开裂。'
        self.assertIsNotNone(source_device_operation_frame(title,body))
        self.assertEqual(self.m.classify_relevance_tier(title,body,(),'IT之家')[0],'strong')
