"""Current source assertions retain their owner, stage and editorial form."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

EVENT = '645ec274c79ee1453f6bc89a'
DEALS = ['8567d943c5c05de0582798eb', 'f4183dc555f34f7759fbbfe0']
COMPLAINT = '494b768576831e93dc7420ab'
WEEKLY = '760e2ed2f6e08ef5290eea9b'
DESIGN = ['3f1744badde165e8b93c1cfe', '8ea9232507d0baab531b97e7',
          'e804588eba9651c21bc34974', '10c1a64ac6c0bfe5f39f724a']
SALES = ['97a89c7f9b564a3794d8ec23', '733872b6c8555da2bc1d8995']
OTHER_MEASURE = '42d366661407fd08e06512c8'
MACBOOK = ['72ce293d4dfccfe3bba24e11', '592ba95115fa40fb6efa1897',
           'ef57ce8a87dfe67310c6bcca', 'bd58b6386fbc220c7d56ccc5',
           'ddf5c63dbac2d39a26ae1892']
LATE_MACBOOK = 'a72ff1a76e0c7edf8750e314'

class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent/'fixtures/20261005_source_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,10,5,tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_current_event_format_disclosure_survives_previous_week_background(self):
        import html
        row=self.rows[EVENT]
        e=row['evidence']
        page='<html><head><title>'+html.escape(e['title'])+'</title></head><body><article>'+''.join('<p>'+html.escape(u['text'])+'</p>' for u in e['units'])+'</article></body></html>'
        c=self.m.Candidate(e['source'],e['url'],e['discovery_title'],e['discovery_lead'],e['published_utc'])
        extracted=self.m.extract_article(c,self.sources[c.source],page,{})
        old=row['recorded_extraction']
        row['recorded_extraction']=list(extracted[:3])
        try:
            events, data = self.cluster_sources(EVENT)
        finally:
            row['recorded_extraction']=old
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].relevance_tier,'strong')
        self.assertIn('newsletter today', json.dumps(data))
        self.assertIn('hold an event', json.dumps(data))

    def test_captured_retail_sales_and_personal_complaint_stay_weak_and_separate(self):
        for ids in [DEALS+[COMPLAINT], [COMPLAINT]+DEALS[::-1]]:
            articles=[article_for(self.m,*self.rows[sid]['recorded_extraction'][:2],facts=self.rows[sid]['recorded_extraction'][2]) for sid in ids]
            events=self.m.cluster_articles(articles)
            self.assertEqual(len(events),3)
            self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_captured_weekly_column_does_not_refresh_prior_rollouts(self):
        events,_=self.cluster_sources(WEEKLY)
        self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_current_design_oversight_reports_merge_across_languages(self):
        for ids in [DESIGN,DESIGN[::-1]]:
            events,_=self.cluster_sources(*ids)
            self.assertEqual(len(events),1,[(e.title,e.relevance_tier) for e in events])
            self.assertEqual(self.source_ids(events[0]),set(DESIGN))
            self.assertEqual((events[0].category,events[0].relevance_tier),('hardware_products','strong'))

    def test_future_hardware_configuration_keeps_its_roadmap_action(self):
        for ids in [MACBOOK, MACBOOK[::-1]]:
            events,_ = self.cluster_sources(*ids)
            self.assertEqual(len(events),1)
            self.assertEqual(self.source_ids(events[0]),set(MACBOOK))
            self.assertEqual(events[0].event_kind,'hardware_market')
        single,_ = self.cluster_sources(MACBOOK[0])
        self.assertEqual(single[0].event_kind,'hardware_market')

    def test_software_compatibility_is_not_a_hardware_configuration(self):
        hardware = self.source_articles(MACBOOK[0])
        software = article_for(self.m,'macOS 27.2 to feature touch support on MacBook Pro',
            'Apple is testing macOS 27.2 with touch support for MacBook Pro. The operating system changes add touchscreen controls.')
        events = self.m.cluster_articles([*hardware, software])
        self.assertEqual(len(events),2)
        system = next(e for e in events if any(a is software for a in e.articles))
        self.assertEqual(system.category,'software_systems')

    def test_current_chinese_redesign_report_is_not_deferred_for_action_wording(self):
        for ids in [MACBOOK+[LATE_MACBOOK],[LATE_MACBOOK]+MACBOOK[::-1]]:
            events,_ = self.cluster_sources(*ids)
            self.assertEqual(len(events),1)
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertEqual(events[0].relevance_tier,'strong')
        single,_ = self.cluster_sources(LATE_MACBOOK)
        self.assertEqual((single[0].relevance_tier,single[0].event_kind),('strong','hardware_market'))

    def test_historical_chinese_redesign_is_not_a_current_roadmap(self):
        for prefix in ('回顾', '重温'):
            old = article_for(self.m, prefix+'苹果MacBook Pro 2021年大改款：机身与屏幕变化',
                '本文回顾苹果MacBook Pro在2021年的改款设计，此次没有新增消息。')
            event = self.m.cluster_articles([old])[0]
            self.assertEqual(event.relevance_tier, 'weak')

    def test_competitor_recap_and_denial_cannot_borrow_hardware_promotion(self):
        cases = [
            ('New Dell laptop to feature OLED screen, challenging MacBook Pro',
             'Dell will add an OLED touchscreen to its next laptop. Apple MacBook Pro is only a comparison.', 'weak'),
            ('New MacBook Pro to feature OLED: revisiting last year’s report',
             'Last year a report said Apple would add an OLED display to MacBook Pro. This is a retrospective without new reporting.', 'weak'),
            ('Redesigned MacBook Pro to feature lighter OLED enclosure?',
             'Apple denied that its redesigned MacBook Pro will feature a lighter OLED enclosure. The earlier report was incorrect.', 'strong'),
        ]
        for title, lead, tier in cases:
            for reverse in (False, True):
                with self.subTest(title=title, reverse=reverse):
                    other = article_for(self.m,title,lead)
                    articles = [*self.source_articles(MACBOOK[0]),other]
                    events = self.m.cluster_articles(articles[::-1] if reverse else articles)
                    self.assertEqual(len(events),2)
                    self.assertEqual(next(e for e in events if any(a is other for a in e.articles)).relevance_tier,tier)

    def test_unrelated_denial_in_background_does_not_change_hardware_action(self):
        title = 'Redesigned MacBook Pro to feature lighter OLED enclosure'
        report = 'A new report says Apple plans a lighter MacBook Pro with an OLED display.'
        cases = [report + ' Apple denied that iPhone will receive a price increase.',
                 'Apple denied that iPhone will receive a price increase. ' + report,
                 'Apple denied a price increase for MacBook Pro. ' + report,
                 'Apple denied a price increase for the OLED MacBook Pro. ' + report]
        for lead in cases:
            events = self.m.cluster_articles([*self.source_articles(MACBOOK[0]),article_for(self.m,title,lead)])
            self.assertEqual(len(events),1)

    def test_weekly_sales_duplicate_does_not_merge_different_measurement(self):
        for ids in [SALES+[OTHER_MEASURE],[OTHER_MEASURE]+SALES[::-1]]:
            events,_=self.cluster_sources(*ids)
            self.assertEqual(len(events),2)
            weekly=next(e for e in events if SALES[0] in self.source_ids(e))
            self.assertEqual(self.source_ids(weekly),set(SALES))
            self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def test_price_reduction_and_legal_complaint_keep_their_actual_actions(self):
        cases=[('Apple cuts the official price of MacBook Air by $200',
                'Apple today lowered the standard price of MacBook Air in its own online store by $200.'),
               ('Apple files a legal complaint against Acme',
                'Apple filed a lawsuit against Acme in federal court today alleging patent infringement.')]
        for title,lead in cases:
            events=self.m.cluster_articles([article_for(self.m,title,lead)])
            self.assertTrue(all(e.relevance_tier=='strong' for e in events),title)

    def test_design_opinion_history_and_other_company_do_not_promote(self):
        for title,lead in [
            ('Why Apple should put its CEO in charge of design','I think Apple should give its CEO responsibility for the design teams.'),
            ('Looking back at Apple CEO design oversight','Last year Apple put its CEO in charge of its design teams. This is a historical recap.'),
            ('Acme CEO takes a hands-on role in design','Acme CEO Alex Stone now leads its design teams. Apple is only a comparison.'),
        ]:
            events=self.m.cluster_articles([article_for(self.m,title,lead)])
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),title)

    def test_newsletter_attribution_and_subscription_prompts_are_distinct(self):
        for text in ["In his newsletter today, a reporter said Apple will hold an event.",
                     "The analyst reported in her latest newsletter that Apple has changed its plans.",
                     "The latest newsletter reports that Apple will hold an event later this month.",
                     "Apple News now offers a newsletter that explains how its new privacy controls work."]:
            self.assertIn(text,self.m.extract_summary('<article><p>'+text+'</p></article>',''))
        prompt='Subscribe to our newsletter for the latest Apple news, product updates and exclusive offers.'
        self.assertNotIn(prompt,self.m.extract_summary('<article><p>'+prompt+'</p></article>',''))
        signup='Get our free newsletter delivered to your inbox for the latest Apple updates every morning.'
        self.assertNotIn(signup,self.m.extract_summary('<article><p>'+signup+'</p></article>',''))

    def test_design_assignments_and_denials_keep_distinct_owners(self):
        cases=[('Apple CEO John Ternus takes a hands-on role in design',
                'Apple CEO John Ternus now oversees the industrial design teams, according to a new report.'),
               ('Apple CEO Tim Cook takes a hands-on role in design',
                'Apple CEO Tim Cook now oversees the industrial design teams, according to a new report.'),
               ('Apple CEO John Ternus will not take over design teams',
                'A new report says Apple CEO John Ternus has not taken over the design teams.')]
        events=self.m.cluster_articles([article_for(self.m,t,l) for t,l in cases])
        self.assertEqual(len(events),3)

    def test_newsletter_disclosure_survives_all_nine_source_extractors(self):
        text='In her newsletter today, the reporter specified that Apple is planning to hold an event that day.'
        page='<html><head><title>Apple reports an event plan</title></head><body><article><p>'+text+'</p></article></body></html>'
        self.assertEqual(len(self.sources),9)
        for source in self.sources.values():
            c=self.m.Candidate(source.name,'https://'+source.domains[0]+'/event-plan/','Apple reports an event plan','')
            with self.subTest(source=source.name):
                self.assertIn(text,self.m.extract_article(c,source,page,{})[1])

    def test_reviewed_design_subject_history_and_polarity_boundaries(self):
        cases = {'design-positive': ('Apple CEO John Ternus takes a hands-on role in design', 'Apple CEO John Ternus now oversees its industrial design teams.'), 'design-denial': ('Apple CEO John Ternus taking a hands-on role in design?', 'Apple denied that John Ternus oversees its industrial design teams. The report is false.'), 'design-history': ('Apple CEO John Ternus and his hands-on design approach', 'Last year Apple CEO John Ternus took charge of its industrial design teams. This article recalls that decision.'), 'design-other': ('Samsung CEO John Ternus takes a hands-on role in design', 'Samsung CEO John Ternus now oversees its industrial design teams, unlike Apple.'), 'design-other-long': ('Samsung Electronics CEO John Ternus takes a hands-on role in design', 'Samsung Electronics CEO John Ternus now oversees its industrial design teams, unlike Apple.'), 'design-other-cn': ('三星CEO库克亲掌设计', '三星CEO库克今日接管三星设计团队，苹果仅作为对照。')}
        positive=cases['design-positive']
        for key in ['design-denial','design-history','design-other-long','design-other-cn']:
            with self.subTest(case=key):
                events=self.m.cluster_articles([article_for(self.m,*positive),article_for(self.m,*cases[key])])
                self.assertEqual(len(events),2)
                if key!='design-denial':
                    other=next(e for e in events if e.title==cases[key][0])
                    self.assertEqual(other.relevance_tier,'weak')

    def test_reviewed_sales_metric_and_forecast_boundaries(self):
        cases = {'weekly-total': ('iPhone 19 Pro W40国内累计销量200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内累计销量200万台。'), 'weekly-week': ('iPhone 19 Pro W40国内单周销量200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内单周销量200万台。'), 'weekly-forecast-title': ('预计iPhone 19 Pro W40国内销量200万台', '分析师发布报告：iPhone 19 Pro系列W40国内销量200万台。'), 'weekly-observed': ('iPhone 19 Pro W40国内销量200万台', '分析师发布报告：iPhone 19 Pro系列W40国内销量200万台。')}
        for a,b in [('weekly-total','weekly-week'),('weekly-forecast-title','weekly-observed')]:
            with self.subTest(pair=(a,b)):
                events=self.m.cluster_articles([article_for(self.m,*cases[a]),article_for(self.m,*cases[b])])
                self.assertEqual(len(events),2)

    def test_weekly_metric_cannot_promote_history_or_competitor_headline(self):
        for title,lead in [
            ('回顾iPhone 19 Pro W40国内销量200万台','去年iPhone 19 Pro系列W40国内累计销量200万台，本文回顾此前的市场表现。'),
            ('华为销量超过iPhone 19 Pro，国内市场大获全胜','iPhone 19 Pro系列W40国内累计销量200万台，华为同期销量达300万台。')]:
            events=self.m.cluster_articles([article_for(self.m,title,lead)])
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),title)

    def test_local_qualifiers_cannot_cross_design_objects_or_sales_weeks(self):
        cases = {'design-current': ('Apple CEO John Ternus takes a hands-on role in design', 'Apple CEO John Ternus now oversees industrial design teams.'), 'design-unrelated-not': ('Apple CEO John Ternus takes a hands-on role in design', 'Apple CEO John Ternus now oversees industrial design teams, not software engineering.'), 'sales-current': ('iPhone 19 Pro W40国内销量200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内累计销量200万台。'), 'sales-negative': ('iPhone 19 Pro W40国内销量未达200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内累计销量没有达到200万台。'), 'sales-weeks-prediction': ('预计iPhone 19 Pro W41国内销量200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内累计销量200万台，W41预计保持这一水平。'), 'title-cumulative': ('iPhone 19 Pro W40国内累计销量200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内销量200万台。'), 'title-single': ('iPhone 19 Pro W40国内单周销量200万台', '博主今日发布统计，iPhone 19 Pro系列W40国内销量200万台。')}
        for a,b,count in [('design-current','design-unrelated-not',1),
                          ('sales-current','sales-negative',2),
                          ('sales-current','sales-weeks-prediction',2),
                          ('title-cumulative','title-single',2)]:
            with self.subTest(pair=(a,b)):
                events=self.m.cluster_articles([article_for(self.m,*cases[a]),article_for(self.m,*cases[b])])
                self.assertEqual(len(events),count)
        from apple_news_core.event_reconciler import _weekly_device_sales_subject
        self.assertEqual(_weekly_device_sales_subject(*cases['sales-weeks-prediction']),'')

    def test_different_weekly_sales_scopes_do_not_merge(self):
        cases=[('iPhone 19 Pro W40国内销量200万台','博主今日发布统计，iPhone 19 Pro系列W40国内累计销量200万台。'),
               ('iPhone 19 Pro W41国内销量200万台','博主今日发布统计，iPhone 19 Pro系列W41国内累计销量200万台。'),
               ('iPhone 20 Pro W40国内销量200万台','博主今日发布统计，iPhone 20 Pro系列W40国内累计销量200万台。'),
               ('iPhone 19 Pro W40美国销量200万台','博主今日发布统计，iPhone 19 Pro系列W40美国累计销量200万台。')]
        events=self.m.cluster_articles([article_for(self.m,t,l) for t,l in cases])
        self.assertEqual(len(events),4)

if __name__=='__main__':
    unittest.main()
