"""Admission preserves Apple-owned reports; editorial context cannot invent actions."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load_module()
        cls.rows=json.loads((Path(__file__).parent/'fixtures/20261004_source_boundaries.json').read_text())
        cls.discovery=json.loads((Path(__file__).parent/'fixtures/20261004_discovery.json').read_text())
        cls.sources={s.name:s for s in cls.m.build_sources(datetime(2026,10,4,tzinfo=timezone.utc))}
    source_articles=prior.PureJsonBatchTests.source_articles
    cluster_sources=prior.PureJsonBatchTests.cluster_sources
    source_ids=staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_captured_apple_reports_survive_lexical_discovery_vetoes(self):
        for row in self.discovery:
            c=self.m.Candidate(**{k:v for k,v in row.items() if k!='admitted'})
            with self.subTest(title=c.title):
                self.assertTrue(self.m.is_relevant_candidate(c,self.sources[c.source]))

    def test_all_nine_sources_admit_direct_report_with_compatible_vendor_context(self):
        for source in self.sources.values():
            c=self.m.Candidate(source.name,'https://'+source.domains[0]+'/newsroom/2026/10/apple-podcasts-update/',
                'Apple Podcasts adds live transcripts in iOS 28.2',
                'Apple today introduced live transcripts to Apple Podcasts. Supported playback devices include Amazon Fire TV.')
            with self.subTest(source=source.name):
                self.assertTrue(self.m.is_relevant_candidate(c,source))

    def test_retail_discount_and_podcast_episode_are_not_report_admission(self):
        cases=[
            ('Save $100 on iPad at Amazon','Amazon offers a discount on iPad today.','https://9to5mac.com/deals/ipad/'),
            ('9to5Mac Daily: iOS 28 and Apple Podcasts','Listen to a recap in our daily podcast episode.','https://9to5mac.com/podcast/ios-28/'),
        ]
        for title,lead,url in cases:
            c=self.m.Candidate('9to5Mac',url,title,lead)
            self.assertFalse(self.m.is_relevant_candidate(c,self.sources[c.source]),title)

    def test_competitor_compatibility_keeps_weak_tier(self):
        a=article_for(self.m,'Amazon Fire TV adds Apple TV shortcut','Amazon launched a new Fire TV stick with an Apple TV shortcut.')
        self.assertTrue(all(e.relevance_tier=='weak' for e in self.m.cluster_articles([a])))

    def test_broadcast_retains_us_free_access_and_device_conditions(self):
        events,data=self.cluster_sources('2453554c282406eacca66d43')
        self.assertEqual(len(events),1)
        self.assertEqual((events[0].category,events[0].relevance_tier),('software_systems','strong'))
        text=json.dumps(data,ensure_ascii=False)
        for term in ['美国','无需订阅','Fire TV','排位','正赛']:
            self.assertIn(term,text)

    def test_measurement_is_one_strong_event_with_both_sources_and_limits(self):
        ids=['48923b211c3bc40943f39bc2','496711bc1bd1f0d2bf64b98e']
        for order in [ids,ids[::-1]]:
            events,data=self.cluster_sources(*order)
            self.assertEqual(len(events),1)
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertEqual((events[0].category,events[0].relevance_tier),('hardware_products','strong'))
            text=json.dumps(data,ensure_ascii=False)
            for term in ['44%','35%','29%','64K','256','140K']:
                self.assertIn(term,text)

    def test_chinese_replacement_synonyms_merge_without_carrier_notice(self):
        ids=['3cadfcbb4022c3f7fef845c7','9c0202e67931629ca71f3634','f5858694132390a62501cc40']
        for order in [ids,ids[::-1]]:
            events,_=self.cluster_sources(*order,'c0f6b9ba61a571d727ad5cc8')
            self.assertEqual(len(events),2,[(e.title,self.source_ids(e)) for e in events])
            replacement=next(e for e in events if ids[0] in self.source_ids(e))
            self.assertEqual(self.source_ids(replacement),set(ids))
            self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def test_named_store_reopening_is_strong(self):
        events,_=self.cluster_sources('f123a4fc832533fd4a4260de')
        self.assertEqual((events[0].category,events[0].relevance_tier),('hardware_products','strong'))
        self.assertEqual(events[0].regions,{'united-kingdom'})

    def test_region_abbreviations_do_not_match_word_suffixes_or_pronouns(self):
        for text in ['Genius Bar offers a dedicated pickup counter.',
                     'The bonus offer tells us about the store.',
                     'The campus store reopened in England.']:
            self.assertNotIn('united-states',self.m.extract_regions(text),text)
        for text in ['Apple expands its US stores.', 'Available in the US.',
                     'Available in the U.S.', 'Apple United States stores', 'Apple USA stores']:
            self.assertIn('united-states',self.m.extract_regions(text),text)
        self.assertEqual(self.m.extract_regions('Apple Ridgeway in England reopens its Genius Bar.'),{'united-kingdom'})
        for region in ['US','U.S.','USA']:
            title=f'AppleCare+ now offers a monthly payment option for {region} customers.'
            self.assertTrue(self.m.is_first_party_applecare_plan_change_story(title,title),region)
        title='AppleCare+ tells us about monthly payment options.'
        self.assertFalse(self.m.is_first_party_applecare_plan_change_story(title,title))

    def test_personal_upgrade_and_prior_rumor_roundup_are_weak(self):
        for sid in ['178f25f45a1947fb5a3d77b4','3b60cae6c0982b1d46465ca7']:
            events,_=self.cluster_sources(sid)
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),[(e.title,e.relevance_reason) for e in events])

    def test_new_disclosure_and_new_measurement_not_blocked_by_review_words(self):
        from apple_news_core.event_identity import source_device_disclosure
        self.assertIsNotNone(source_device_disclosure('New entry-level iPad leak reveals A20 chip','New code discovered today reveals the next entry-level iPad will use the A20 chip.'))
        title='I tested the M6 MacBook Pro: new benchmark results'
        a=article_for(self.m,title,'Our newly published test measured 125 tokens per second on the M6 MacBook Pro, compared with 90 on M5.')
        self.assertEqual(self.m.title_led_identity(title,a.summary).content_form,'news')

    def test_reopening_requires_a_store_and_distinct_locations_do_not_merge(self):
        cases=[('Apple Ridgeway reopening on November 8','Apple Ridgeway in Boston closed for renovations in July. The store will reopen to customers on November 8.'),
               ('Apple Lakeside reopening on November 8','Apple Lakeside in Austin closed for renovations in July. The store will reopen to customers on November 8.')]
        events=self.m.cluster_articles([article_for(self.m,t,l) for t,l in cases])
        self.assertEqual(len(events),2)
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))
        from apple_news_core.event_identity import source_object_operation_frame,build_event_identity
        for title,lead in [('Apple Ridgeway will not reopen','Apple says the store will not reopen after renovations.'),('Apple TV documentary about a reopening','The film tells the story of a store reopening after renovations.')]:
            f=source_object_operation_frame(title,lead,(),build_event_identity(title,lead))
            self.assertTrue(f is None or f.action!='store-reopening')

    def test_navigation_and_evergreen_catalog_do_not_use_report_admission(self):
        for url in ['https://www.ithome.com/tags/Apple%20TV/', 'https://example.com/category/apple-tv/']:
            c=self.m.Candidate('IT之家',url,'Apple TV','Apple TV is free on Amazon Fire TV this weekend.')
            self.assertFalse(self.m.is_relevant_candidate(c,self.sources[c.source]))
        title='All Apple TV shows and movies: what to watch with your subscription'
        self.assertEqual(self.m.title_led_identity(title,'Apple TV includes many shows.').content_form,'roundup')

    def test_same_free_race_merges_across_languages(self):
        ids=['2453554c282406eacca66d43','6bf3cf457cd9fcb92cf7ce10']
        for order in [ids,ids[::-1]]:
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),1,[(e.title,self.source_ids(e)) for e in events])
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertEqual((events[0].category,events[0].relevance_tier),('software_systems','strong'))
        from apple_news_core.event_identity import source_free_race_stream
        a=source_free_race_stream('Apple TV offers free F1 Bahrain Grand Prix','The Bahrain Grand Prix is streaming for free.')
        b=source_free_race_stream('Apple TV offers free F1 Japanese Grand Prix','The Japanese Grand Prix is streaming for free.')
        self.assertNotEqual(a,b)
        self.assertIsNone(source_free_race_stream('Apple TV will no longer offer free F1 Bahrain Grand Prix','The Bahrain Grand Prix requires a subscription.'))

    def test_free_broadcast_denial_does_not_merge_with_affirmative_report(self):
        positive=article_for(self.m,'苹果 Apple TV 免费直播 F1 巴林大奖赛','苹果宣布将免费直播本周末的 F1 巴林大奖赛，美国用户无需订阅即可观看。')
        for title,lead in [
            ('苹果 Apple TV 不会免费直播 F1 巴林大奖赛','苹果确认不会免费直播本周末的 F1 巴林大奖赛，用户需要订阅。'),
            ('传闻称苹果 Apple TV 免费直播 F1 巴林大奖赛','苹果否认本周末的 F1 巴林大奖赛将免费直播，用户需要订阅。')]:
            self.assertEqual(len(self.m.cluster_articles([positive,article_for(self.m,title,lead)])),2)

    def test_subscription_requirement_negation_preserves_free_stream(self):
        from apple_news_core.event_identity import source_free_race_stream
        title='Apple TV offers free F1 Bahrain Grand Prix'
        self.assertIsNotNone(source_free_race_stream(title,'Apple TV will stream the F1 Bahrain Grand Prix for free. You won’t need a subscription to watch for free.'))
        self.assertIsNone(source_free_race_stream(title,'Apple TV denied that the F1 Bahrain Grand Prix would be streamed for free.'))
        self.assertIsNone(source_free_race_stream('Apple TV won’t stream the F1 Bahrain Grand Prix for free','Apple TV says the race requires a subscription.'))

    def test_store_predicate_owns_history_negation_and_month(self):
        from apple_news_core.event_identity import source_object_operation_frame,build_event_identity
        for month in ['May','November']:
            title='Apple Ridgeway reopening on '+month+' 8'
            lead='Apple Ridgeway previously closed for renovations in January. The store will reopen to customers on '+month+' 8.'
            f=source_object_operation_frame(title,lead,(),build_event_identity(title,lead))
            self.assertIsNotNone(f);self.assertEqual(f.action,'store-reopening')
        cases=[('Apple Ridgeway reopening: a look back','Apple Ridgeway reopened to customers in 2015 after renovations. We look back at the event.'),
               ('Apple Ridgeway reopening on November 8','Apple Ridgeway won’t reopen on November 8. The store will remain closed for renovations.'),
               ('Apple Ridgeway reopening on November 8?','Apple Ridgeway remains closed for renovations. A reader speculates that the store could reopen.'),
               ('Apple Ridgeway reopening cancelled','Apple Ridgeway reopening has been cancelled. The store will remain closed.'),
               ('Apple Ridgeway reopening on November 8','Apple Ridgeway won’t reopen on November 8. Apple Lakeside will reopen to customers after renovations.'),
               ('Apple Ridgeway reopening on November 8','Apple Ridgeway remains closed for renovations. Apple Lakeside has announced a new date. The store will reopen on November 8.')]
        for title,lead in cases:
            f=source_object_operation_frame(title,lead,(),build_event_identity(title,lead))
            self.assertTrue(f is None or f.action!='store-reopening',(title,f))

    def test_carrier_and_replacement_negation_are_local_and_order_independent(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        from apple_news_core.event_identity import bind_connectivity_remedy_claims
        def claims(paragraphs):
            e=ArticleEvidence('test','快科技','https://example.com/incident','苹果确认：iPhone 19 Pro 断网问题只能通过换机解决',paragraphs[0],'news',tuple(EvidenceUnit(str(i),'p',t,'body',i) for i,t in enumerate(paragraphs)))
            return bind_connectivity_remedy_claims(e)
        a='苹果确认，iPhone 19 Pro 的 Meridian公司的用户遇到断网问题，必须换机。'
        b='苹果表示，iPhone 19 Pro 的 Orion公司的用户同样遇到断网问题，必须换机。'
        for ps in [[a,b],[b,a]]:
            cs=claims(ps)
            for c in cs:
                for uid in c.unit_ids:
                    text=ps[int(uid)]
                    self.assertIn(c.subject.split(':network:')[1],text.lower())
        cs=claims(['去年，iPhone 19 Pro 的 Meridian公司的用户曾遇到断网问题。',b])
        self.assertEqual(len(cs),1);self.assertIn(':network:orion',cs[0].subject)
        cs=claims(['iPhone 19 Pro 的 Meridian公司的用户出现断网问题。','苹果确认，受影响用户并非只能通过换机解决问题。'])
        self.assertFalse(cs)

    def test_offered_replacement_joins_required_remedy_without_carrier_notice(self):
        ids=['9c0202e67931629ca71f3634','68a64255ee5087d8ec8fe99c']
        for order in [ids,ids[::-1]]:
            events,_=self.cluster_sources(*order,'c0f6b9ba61a571d727ad5cc8')
            self.assertEqual(len(events),2)
            remedy=next(e for e in events if ids[1] in self.source_ids(e))
            self.assertEqual(self.source_ids(remedy),set(ids))
            self.assertEqual((remedy.category,remedy.relevance_tier),('hardware_products','strong'))

    def test_replacement_offer_requires_current_apple_commitment(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        from apple_news_core.event_identity import bind_connectivity_remedy_claims
        title='苹果宣布为 Meridian 网络 iPhone 19 Pro 用户免费换新'
        context='iPhone 19 Pro 的 Meridian网络用户出现网络故障。'
        def actions(sentence):
            e=ArticleEvidence('test','快科技','https://example.com/remedy',title,context,'news',
                (EvidenceUnit('0','p',context,'body',0),EvidenceUnit('1','p',sentence,'body',1)))
            return [c.action for c in bind_connectivity_remedy_claims(e)]
        for sentence in ['苹果宣布，将为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         '苹果宣布，将为受影响的 iPhone 19 Pro 提供免费换新服务，打消此前用户的使用顾虑。',
                         'Apple announced it will provide free replacements for affected iPhone 19 Pro devices.']:
            self.assertEqual(actions(sentence),['device-replacement-remedy'])
        sentence='Apple will offer free replacements for iPhone 19 Pro devices, but iPhone 20 Pro devices are not eligible.'
        e=ArticleEvidence('test','快科技','https://example.com/remedy',title,context,'news',
            (EvidenceUnit('1','p',sentence,'body',1),))
        cs=bind_connectivity_remedy_claims(e)
        self.assertEqual([c.action for c in cs],['device-replacement-remedy'])
        self.assertTrue(all('20 Pro' not in sentence[start:end] for c in cs for _,start,end in c.evidence_spans))
        for sentence in ['苹果宣布，不会为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         '苹果否认将为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         '苹果表示，正在考虑为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         '去年苹果宣布，将为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         '苹果已了解问题，Meridian宣布将为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         '苹果称Meridian宣布将为受影响的 iPhone 19 Pro 提供免费换新服务。',
                         'Apple says Meridian will provide free replacements for affected iPhone 19 Pro devices.',
                         'Apple announced it will not provide free replacements for affected iPhone 19 Pro devices.',
                         'Reports that Apple will offer free replacements for affected iPhone 19 Pro devices were denied by Apple.',
                         'Reports that Apple will offer free replacements for affected iPhone 19 Pro devices, a claim denied by Apple, are circulating online.',
                         'Apple will offer free replacements for affected iPhone 19 Pro devices, according to a statement issued last year.',
                         '苹果宣布将为受影响的 iPhone 19 Pro 提供免费换新服务，该计划已取消。',
                         '苹果宣布将为受影响的 iPhone 19 Pro 提供免费换新服务的计划已取消。',
                         'Apple announced it will provide free replacements for affected iPhone 19 Pro devices last year.',
                         'Apple will offer free replacements for iPhone 20 Pro devices, but iPhone 19 Pro devices are not eligible.',
                         '苹果宣布，将为受影响的 iPhone 19 Pro Max 提供免费换新服务。',
                         '苹果宣布，将为 Orion网络用户的 iPhone 19 Pro 提供免费换新服务。']:
            self.assertNotIn('device-replacement-remedy',actions(sentence),sentence)

if __name__=='__main__':unittest.main()
