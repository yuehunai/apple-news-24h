"""Public natural source relationships and collection boundaries."""
import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from dataclasses import replace
from test_relevance_rules import load_module

class PublicSourceRelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.fixture = json.loads((Path(__file__).parent/'fixtures/p3_public_source_relations.json').read_text())

    def test_source_action_background_does_not_change_release_or_editorial_form(self):
        import hashlib
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        m = self.m
        fixture = self.fixture['source_action_background']
        articles = {}
        for row in fixture['sources']:
            aid = hashlib.sha256(row['url'].encode()).hexdigest()[:24]
            units = tuple(EvidenceUnit(f"{aid}-{n}", u['kind'], u['text'], 'synthetic', u['ordinal'])
                          for n, u in enumerate(row['units']))
            evidence = ArticleEvidence(aid, row['source'], row['url'], row['title'], row['summary'], 'news', units, confidence='detail')
            articles[row['id']] = m.Article(source=row['source'], url=row['url'], title=row['title'],
                summary=row['summary'], key_facts=row['key_facts'], category='',
                published_utc=datetime(2032,10,24,tzinfo=timezone.utc), published_raw='2032-10-24',
                published_source='synthetic', confidence='detail',
                tokens=m.article_tokens(row['title'], ' '.join([row['summary'][:1200], *row['key_facts'][:5]])),
                event_kind=m.detect_event_kind(row['title'], row['summary'], row['key_facts']),
                regions=m.extract_regions(' '.join([row['title'], row['summary'], *row['key_facts'][:5]])),
                evidence=evidence, projection_source_title=row['title'])
        profiles = {k:m.article_reconciliation_profile(a) for k,a in articles.items()}
        for key, expected in fixture['expected'].items():
            with self.subTest(source=key):
                actual = m.resolve_reconciliation_outcome(profiles[key], observed_tier='', observed_reason='', observed_category='')
                self.assertEqual(actual[0], expected['tier'])
                if 'category' in expected:self.assertEqual(actual[2], expected['category'])
        self.assertNotEqual(m.profile_pair_decision(profiles['software_release'], profiles['hardware_forecast']), 'match')
        events = m.cluster_articles(list(articles.values()))
        self.assertEqual(len(events), 3)
        self.assertEqual({s.url for e in events for s in e.articles}, {a.url for a in articles.values()})
        row = fixture['candidates'][0]
        c = m.Candidate(**row['candidate'])
        self.assertNotEqual(m.detect_event_kind(c.title,c.summary,[c.context]), 'os_app')
        self.assertEqual(m.source_text_outcome(c.title,c.summary,[c.context],c.source)[0], 'weak')

    def test_source_action_background_controls_keep_current_software_and_comparison_roles(self):
        m = self.m
        def outcome(title, lead):
            p = m.source_text_profile(title, lead, [lead], 'Fixture News')
            return p, m.resolve_reconciliation_outcome(p, observed_tier='', observed_reason='', observed_category='')
        title = 'Apple releases HomePod 28 with two new improvements'
        lead = 'Today Apple released HomePod 28 software with AutoMix and security fixes.'
        a, ao = outcome(title, lead)
        b, bo = outcome('Apple ships HomePod 28 software update', lead)
        self.assertEqual(ao[::2], ('strong', 'software_systems'))
        self.assertEqual(bo[::2], ('strong', 'software_systems'))
        self.assertEqual(m.profile_pair_decision(a,b), 'match')
        other, _ = outcome(title.replace('28','29'), lead.replace('28','29'))
        self.assertNotEqual(m.profile_pair_decision(a,other), 'match')
        for title, lead in [
            ('Apple releases iOS 28 for download today', 'Apple today released iOS 28, available for public download with new Siri features.'),
            ('Apple adds new wallpapers in iOS 28', 'Apple today added new dynamic wallpapers to iOS 28. Users can download the update now.'),
            ('Apple updates Siri voice recognition', 'Apple updated Siri voice recognition with a new local feature, similar to Google voice controls.'),
            ('苹果更新Siri语音功能', '苹果今日更新Siri语音功能，与别家公司类似，新的处理过程在本地完成。'),
            ('A new way to handle requests', 'Apple today updated Siri in iOS 28 with new voice features.')]:
            with self.subTest(title=title):
                self.assertEqual(m.detect_event_kind(title,lead,[]), 'os_app')
                if title != 'A new way to handle requests':
                    self.assertEqual(outcome(title,lead)[1][0], 'strong')
        row = self.fixture['source_action_background']['candidates'][0]
        c = m.Candidate(**row['candidate'])
        self.assertEqual(m.detect_event_kind(c.title,c.summary,[c.context]), 'third_party_ecosystem')
        self.assertEqual(m.candidate_detail_priority(c)[0], 15)
        self.assertFalse(m.is_apple_os_feature_or_summary_story(c.title+' '+c.summary))
        self.assertFalse(m.is_apple_os_feature_or_summary_story(
            'QN describes local television voice controls. Its new voice feature works similar to Apple Siri.'))

    def profiles(self):
        m=self.m; profiles={}
        for key,(title,summary) in self.fixture['rows'].items():
            url='https://fixture.example/'+key
            evidence=m.capture_article_title_evidence('Fixture News',url,title,summary,(summary,))
            article=m.Article(source='Fixture News',url=url,title=title,summary=summary,key_facts=[summary],category='',published_utc=datetime(2031,10,8,tzinfo=timezone.utc),published_raw='2031-10-08',published_source='synthetic',confidence='detail',tokens=set(),evidence=evidence)
            profiles[key]=m.article_reconciliation_profile(article)
        return profiles

    def test_natural_specific_source_relations(self):
        p=self.profiles()
        for row in self.fixture['pairs']:
            with self.subTest(left=row['left'],right=row['right']):
                decision=self.m.profile_pair_decision(p[row['left']],p[row['right']])
                if row['expected']=='match':self.assertEqual(decision,'match')
                else:self.assertNotEqual(decision,'match')

    def test_current_action_not_historical_or_other_subject_background(self):
        p=self.profiles()
        def outcome(key):return self.m.resolve_reconciliation_outcome(p[key],observed_tier='',observed_reason='',observed_category='')
        self.assertEqual(outcome('actors')[0],'weak')
        self.assertEqual(outcome('gpu-background')[2],'hardware_products')
        self.assertFalse(any('apple-os-utility-opencl' in k for k in p['gpu-background'].separation_keys))
        self.assertEqual(outcome('hardware-positive')[0],'strong')
        self.assertEqual(outcome('opencl-current-positive')[::2],('strong','software_systems'))

    def test_trailing_commerce_and_related_lists_use_same_clean_boundary(self):
        for key in ('html','related_html'):
            with self.subTest(html=key):
                text=self.fixture[key]
                evidence=self.m.capture_article_evidence('9to5Mac','https://9to5mac.com/2031/10/08/public-radio/',text,'Teardown identifies iPhone 22 Pro radio hardware','Lab Delta published a regional radio teardown.')
                units='\n'.join(u.text for u in evidence.units)
                facts='\n'.join(self.m.extract_key_facts(text,'Teardown identifies iPhone 22 Pro radio hardware','9to5Mac'))
                for item in self.fixture['required']:self.assertIn(item,units)
                for item in self.fixture['forbidden']:
                    self.assertNotIn(item,units)
                    self.assertNotIn(item,facts)

    def test_captured_shortlist_keeps_important_apple_testing_remainder(self):
        from dataclasses import replace
        m=self.m; f=self.fixture['increment']['memory'];url='https://fixture.example/memory-source'
        title='从无人看好到全球第三：山河存储份额升至16%，苹果也在测试另一家内存'
        ev=m.capture_article_evidence('Fixture News',url,f['html'],title,f['captured_summary'])
        a=m.Article(source='Fixture News',url=url,title=title,summary=f['captured_summary'],key_facts=f['captured_key_facts'],category='',published_utc=datetime(2031,10,8,tzinfo=timezone.utc),published_raw='2031-10-08',published_source='synthetic',confidence='detail',tokens=set(),evidence=ev)
        def plan(article):return m.resolve_event_fact_plan([m.prepare_source_fact_view(article)],relevance_tier='weak',base_limit=6,official_limit=6)
        def owned(p,u):return [x for x in (*p.facts,*p.unprocessed) if '苹果已在测试' in x.text and any(o[1]==u for o in x.origins)]
        for article in (a,replace(a,key_facts=[*a.key_facts,f['target']])):
            facts=owned(plan(article),url);self.assertTrue(facts)
            self.assertTrue(any('加拿大' in x.text and 'iPhone和Mac' in x.text for x in facts))
        other=replace(a,url='https://other.example/source',key_facts=[*a.key_facts,f['target']])
        self.assertFalse(owned(plan(other),url))

    def test_apple_measurement_subject_and_external_analyst_attribution(self):
        m=self.m; profiles={}
        for key,(title,summary) in self.fixture['increment']['rows'].items():
            profiles[key]=m.source_text_profile(title,summary,[summary],'Fixture News')
        self.assertEqual(m.profile_pair_decision(profiles['score-explicit'],profiles['score-comparison']),'match')
        self.assertNotEqual(m.profile_pair_decision(profiles['score-explicit'],profiles['score-nonapple']),'match')
        self.assertEqual(m.resolve_reconciliation_outcome(profiles['score-nonapple'],observed_tier='',observed_reason='',observed_category='')[0],'weak')
        analyst=self.fixture['increment']['rows']['analyst']
        self.assertFalse(m.is_apple_company_org_change_story(' '.join(analyst)))
        self.assertTrue(m.is_apple_company_org_change_story(' '.join(self.fixture['increment']['rows']['apple-appointment'])))

    def test_sparse_collection_keeps_reports_not_explicit_navigation_or_instructions(self):
        m=self.m
        source=next(s for s in m.build_sources(datetime(2031,10,8,tzinfo=timezone.utc)) if s.name=='MacRumors')
        negatives=['iPhone之家','Apple Intelligence Guide','21 Time-Saving iPhone Tips',
                   'Hard Reset or Force Restart Your iPhone 18',
                   'iPhone 18 Pro: Record Time-Lapse Videos in 4K',
                   'iPhone 18 Pro: Apply Cinematic Effects to Photos',
                   'iPhone 17 vs iPhone 17 Pro vs iPhone Air','iPhone Cases','iPhone 17e','the iPhone Duo']
        positives=['Apple raises iPhone 18 Pro price to $1,199',
                   'iPhone 18 Pro Max Test Shows Much Faster Charging',
                   'iOS 29: 13 Ways the Messages App is Smarter and Less Annoying',
                   '10 iOS 29 Performance Improvements You Will Notice']
        for title in negatives+positives:
            with self.subTest(title=title):
                identity=m.title_led_identity(title,'')
                sparse=m.collection.sparse_apple_subject_needs_detail(identity,has_lead=False,event_kind=m.detect_event_kind(title,'',[]),title=title)
                if title in negatives:self.assertFalse(sparse)
                else:self.assertTrue(m.is_relevant_candidate(m.Candidate(source.name,'https://www.macrumors.com/2031/10/08/report/',title),source))

    def test_specific_reports_keep_model_metric_owner_and_disclosure_boundaries(self):
        m=self.m
        def profile(row):return m.source_text_profile(row[0],row[1],[row[1]],'Fixture News')
        controls=[
            ('score-title', [('174','175')]),
            ('score-title', [('22 Pro','22 Pro Max')]),
            ('teardown-uses', [('Japan','Canada'),('Japanese','Canadian')]),
            ('teardown-uses', [('TechInsights','LabDelta')]),
            ('teardown-uses', [('SDX90M','SDX91M')]),
            ('watch-en', [('Series 16','Series 17')]),
            ('watch-en', [('handwashing timer','blood oxygen monitor')]),
            ('fake-en', [('M9 Pro','M9 Max')]),
            ('interview-b', [('Casey Lane','Taylor Reed')]),
            ('interview-b', [('six years','eight years')]),
            ('shipping', [('24 watt-hours','28 watt-hours'),('24 Wh','28 Wh')]),
        ]
        for key,replacements in controls:
            original=self.fixture['rows'][key];changed=list(original)
            for old,new in replacements:changed=[x.replace(old,new) for x in changed]
            with self.subTest(case=key,replacements=replacements):
                self.assertNotEqual(m.profile_pair_decision(profile(original),profile(changed)),'match')

    def test_template_words_inside_real_prose_and_lists_are_retained(self):
        m=self.m
        html='<article><h1>Apple documents accessory compatibility</h1><p>Apple explains how accessories connect to iPhone 22 Pro. A linked manual documents the supported USB protocol and external power limits.</p><ul><li>Japan: Q90 radio</li><li>Canada: C7 radio</li></ul><p>The Image tool adds Tags and Comments to exported photographs.</p></article>'
        ev=m.capture_article_evidence('9to5Mac','https://fixture.example/real-accessories',html,'Apple documents accessory compatibility','Apple published a manual.')
        text=' '.join(u.text for u in ev.units)
        for target in ['accessories connect','linked manual','Japan: Q90','Canada: C7','Image tool adds Tags and Comments']:self.assertIn(target,text)

    def test_complete_natural_relation_groups(self):
        m=self.m; articles={}; profiles={}
        for key,row in self.fixture['natural_increment']['rows'].items():
            url='https://fixture.example/'+key
            evidence=m.capture_article_title_evidence('Fixture News',url,row['title'],row['summary'],tuple(row['key_facts']))
            a=m.Article(source='Fixture News',url=url,title=row['title'],summary=row['summary'],key_facts=row['key_facts'],category='',published_utc=datetime(2031,10,8,tzinfo=timezone.utc),published_raw='2031-10-08',published_source='synthetic',confidence='detail',tokens=set(),evidence=evidence)
            articles[key]=a;profiles[key]=m.article_reconciliation_profile(a)
        for row in self.fixture['natural_increment']['pairs']:
            with self.subTest(left=row['left'],right=row['right']):
                decision=m.profile_pair_decision(profiles[row['left']],profiles[row['right']])
                if row['expected']=='match':self.assertEqual(decision,'match')
                else:self.assertNotEqual(decision,'match')
        for country in ('Canada','Japan'):
            expected='primary-claim:iphone-22-pro-max:regional-modem-teardown:chipscope:'+country.lower()+':qualcomm'
            for side in ('a','b'):
                self.assertIn(expected,profiles['modem-'+country+'-'+side].event_keys)
        self.assertFalse(any(k.startswith('interview-test-duration:') for k in profiles['interview-a'].separation_keys))
        self.assertIn('interview-test-duration:6-years',profiles['interview-b'].separation_keys)
        for key in ('alarm-a','alarm-b','alarm-c'):
            self.assertIn('primary-claim:ios-29-clock:local-workday-alarm-option',profiles[key].event_keys)
        self.assertIn('benchmark-report-action:authenticity-assessment',profiles['verify-a'].separation_keys)
        self.assertIn('benchmark-report-action:result-disclosure',profiles['exposure-a'].separation_keys)
        self.assertEqual(m.resolve_reconciliation_outcome(profiles['actors'],observed_tier='',observed_reason='',observed_category='')[0],'weak')
        groups=[(('verify-a','exposure-a','exposure-b','verify-b'),[{'verify-a','verify-b'},{'exposure-a','exposure-b'}]),(('alarm-a','alarm-b','alarm-c'),[{'alarm-a','alarm-b','alarm-c'}]),(('interview-a','interview-b'),[{'interview-a','interview-b'}]),(('modem-Canada-a','modem-Canada-b','modem-Japan-a','modem-Japan-b'),[{'modem-Canada-a','modem-Canada-b'},{'modem-Japan-a','modem-Japan-b'}])]
        for keys,expected in groups:
            with self.subTest(group=keys):
                events=m.cluster_articles([articles[k] for k in keys]);actual={frozenset(a.url.rsplit('/',1)[-1] for a in e.articles) for e in events}
                self.assertEqual(actual,{frozenset(x) for x in expected})

    def test_source_objects_are_not_missing_detail_or_media_names(self):
        m=self.m;articles={};profiles={};fixture=self.fixture['source_structure_increment']
        for key,row in fixture['rows'].items():
            url='https://fixture.example/'+key
            e=m.capture_article_title_evidence('Fixture News',url,row['title'],row['summary'],tuple(row['key_facts']))
            a=m.Article(source='Fixture News',url=url,title=row['title'],summary=row['summary'],key_facts=row['key_facts'],category='',published_utc=datetime(2031,10,8,tzinfo=timezone.utc),published_raw='2031-10-08',published_source='synthetic',confidence='detail',tokens=set(),evidence=e)
            articles[key]=a;profiles[key]=m.article_reconciliation_profile(a)
        for left,right,expected in fixture['pairs']:
            with self.subTest(left=left,right=right):
                decision=m.profile_pair_decision(profiles[left],profiles[right])
                if expected=='match':self.assertEqual(decision,'match')
                else:self.assertNotEqual(decision,'match')
        for check in fixture['field_checks']:
            with self.subTest(field=check['case']):
                self.assertFalse(any(check['forbidden_predicate'] in key for key in profiles[check['case']].event_keys))
        self.assertIn('teardown-part-code:x:x90',profiles['modem-Canada-a'].separation_keys)
        self.assertFalse(any(key.startswith('teardown-part-code:sdx:') for key in profiles['modem-Canada-a'].separation_keys))
        self.assertIn('teardown-part-code:sdx:sdx90m',profiles['modem-Canada-b'].separation_keys)
        self.assertFalse(any(key.startswith('teardown-part-code:x:') for key in profiles['modem-Canada-b'].separation_keys))
        def variant(key,old,new):
            article=articles[key]
            title=article.title.replace(old,new);summary=article.summary.replace(old,new)
            facts=[fact.replace(old,new) for fact in article.key_facts]
            evidence=m.capture_article_title_evidence('Fixture News',article.url,title,summary,tuple(facts))
            return m.article_reconciliation_profile(replace(article,title=title,summary=summary,key_facts=facts,evidence=evidence))
        with self.subTest(control='same-code-family-different-suffix'):
            self.assertNotEqual(m.profile_pair_decision(profiles['modem-Canada-b'],variant('modem-Canada-b','SDX90M','SDX90N')),'match')
        with self.subTest(control='standalone-media-name-is-not-object'):
            self.assertFalse(any('cover-glass-durability-test' in key for key in variant('media-name-only','ScreenJournal','Screen').event_keys))
        with self.subTest(control='clock-different-explicit-market'):
            self.assertNotEqual(m.profile_pair_decision(profiles['alarm-a'],variant('alarm-a','中国大陆','加拿大')),'match')
        with self.subTest(control='clock-different-minor-version'):
            self.assertNotEqual(m.profile_pair_decision(profiles['alarm-a'],variant('alarm-a','iOS 29','iOS 29.1')),'match')
        for group,keys in fixture['groups'].items():
            with self.subTest(group=group):
                events=m.cluster_articles([articles[k] for k in keys])
                expected=[set(keys)] if group=='alarm' else [{'verify-a','verify-b'},{'exposure-unbranded'}]
                self.assertEqual({frozenset(a.url.rsplit('/',1)[-1] for a in e.articles) for e in events},{frozenset(x) for x in expected})

    def test_measurement_owner_controls_source_tier_not_title_prefix(self):
        m=self.m
        for key,(title,summary,expected) in self.fixture['source_tier_increment'].items():
            with self.subTest(source=key):
                profile=m.source_text_profile(title,summary,[summary],'Fixture News')
                result=m.resolve_reconciliation_outcome(profile,observed_tier='',observed_reason='',observed_category='')
                self.assertEqual(result[0],expected)
                if expected=='strong':
                    self.assertIn('benchmark-report-action:result-disclosure',profile.separation_keys)
        title,summary,_=self.fixture['source_tier_increment']['english-apple-chip']
        for old,new in [('an Apple M9 Pro processor','an Orion M9 Pro processor'),('an Apple M9 Pro processor','an Apple M10 Pro processor')]:
            with self.subTest(owner_or_object=new):
                changed=summary.replace(old,new)
                p=m.source_text_profile(title,changed,[changed],'Fixture News')
                self.assertFalse(p.trusted_direct_action)

    def test_attributed_measurement_relationship_preserves_owner_and_time(self):
        for key,(title,summary,expected) in self.fixture['attributed_score_increment'].items():
            with self.subTest(source=key):
                p=self.m.source_text_profile(title,summary,[summary],'Fixture News')
                outcome=self.m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')
                self.assertEqual(outcome[0],expected)
        title,summary,_=self.fixture['attributed_score_increment']['attributed-score-apple']
        changed=summary.replace('is claimed to run on an "Apple M9 Pro"','runs on an Orion processor; a sidebar mentions an "Apple M9 Pro"')
        p=self.m.source_text_profile(title,changed,[changed],'Fixture News')
        self.assertEqual(self.m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'weak')
        unknown=self.m.source_text_profile('A benchmark entry surfaces in a database','The newly posted measurement does not identify its manufacturer.',[],'Fixture News')
        self.assertEqual(unknown.identity.scope,'unknown')
        self.assertNotIn('non-Apple primary subject',unknown.defer_reason)
        self.assertNotEqual(self.m.resolve_reconciliation_outcome(unknown,observed_tier='',observed_reason='',observed_category='')[0],'strong')

    def test_security_release_requires_current_same_version_and_keeps_hardware_details(self):
        m=self.m
        title='iOS 26.5.2 Patches More Than 25 Security Vulnerabilities'
        lead='Apple released iOS 26.5.2 and iPadOS 26.5.2 with fixes for more than 25 security vulnerabilities.'
        current=m.source_text_profile(title,lead,[lead],'Fixture News')
        self.assertTrue(any(k.startswith('apple-os-release-wave:') for k in current.event_keys))
        for bad_lead in [lead.replace('26.5.2','26.5.3'),lead.replace('released','will release'),lead.replace('released','previously released')]:
            with self.subTest(lead=bad_lead):
                p=m.source_text_profile(title,bad_lead,[bad_lead],'Fixture News')
                self.assertFalse(any(k.startswith('apple-os-release-wave:') for k in p.event_keys))
        other=m.source_text_profile(title.replace('26.5.2','26.5.3'),lead.replace('26.5.2','26.5.3'),[lead.replace('26.5.2','26.5.3')],'Fixture News')
        self.assertNotEqual(m.profile_pair_decision(current,other),'match')
        hardware=m.source_text_profile('iPhone 22 Pro technical details revealed','The new iPhone 22 Pro includes a variable-aperture main camera and a new battery design.',[],'Fixture News')
        self.assertTrue(any('technical-details-disclosure' in key for key in hardware.event_keys))
        self.assertEqual(m.resolve_reconciliation_outcome(hardware,observed_tier='',observed_reason='',observed_category='')[2],'hardware_products')

    def test_editorial_guide_parent_does_not_borrow_tutorial_link_actions(self):
        m=self.m
        for key,row in self.fixture['editorial_guide'].items():
            with self.subTest(key=key):
                url='https://fixture.example/'+key
                ev=m.capture_article_evidence('Fixture News',url,row['html'],row['title'],row['summary'])
                facts=[u.text for u in ev.units if u.kind in {'p','li'}]
                a=m.Article(source='Fixture News',url=url,title=row['title'],summary=row['summary'],key_facts=facts,category='',published_utc=datetime(2030,9,21,tzinfo=timezone.utc),published_raw='2030-09-21',published_source='fixture',confidence='detail',tokens=set(),evidence=ev)
                p=m.article_reconciliation_profile(a)
                self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],row['expected'])
                result=[m.event_to_dict(e,timezone.utc) for e in m.cluster_articles([a])]
                self.assertEqual(len(result),1)
                self.assertEqual(result[0]['relevance_tier'],row['expected'])
                self.assertEqual(result[0]['sources'][0]['relevance_tier'],row['expected'])
                self.assertEqual(result[0]['sources'][0]['url'],url)
                if key=='natural-recap-guide':
                    self.assertEqual(len(ev.units),73)
                    self.assertIn(row['summary'].split('. ',1)[0]+'.',[u.text for u in ev.units])
                else:self.assertIn(row['summary'],[u.text for u in ev.units])
                if row['expected']=='weak':
                    self.assertEqual(p.identity.content_form,'tutorial')
                    self.assertEqual(len(m.project_article_evidence(ev)[0]),0)
                    for heading,items in row['sections']:
                        for item in items:self.assertIn(item,[u.text for u in ev.units])

    def test_existing_tutorial_collection_is_not_just_a_guide_keyword(self):
        m=self.m
        for title,summary in [
            ('iOS 29 feature reference', 'We compiled our previous coverage into tutorials. These guides help readers find earlier instructions.'),
            ('iOS 29 功能索引', '本文整理此前教程，按功能分类，便于读者查找指南。'),
        ]:
            with self.subTest(title=title):
                p=m.source_text_profile(title,summary,[summary],'Fixture News')
                self.assertEqual(p.identity.content_form,'tutorial')
                self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'weak')
        title='iOS 29 adds a new Maps route option: a guide to the change'
        summary='Apple today added a new route option to Maps in iOS 29. Our guide collects existing coverage and tutorials in a separate archive.'
        p=m.source_text_profile(title,summary,[summary],'Fixture News')
        self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'strong')

    def test_guide_archive_cannot_borrow_a_different_or_historical_body_action(self):
        m=self.m;title='iOS 29 adds a new Maps route option: a guide to the change'
        archive=' Our guide collects our iOS 29 coverage and tutorials so readers can find a recap.'
        for opening in (
            'Maps offers route planning on iPhone. Apple today added new editing controls to Photos in iOS 29.',
            'Maps offers route planning on iPhone. Separately, Apple today added a new route option to Maps in iOS 29.',
            'Maps offers route planning on iPhone. Microsoft today added a new route option to Maps in iOS 29.',
            'Maps offers route planning on iPhone. Apple previously added a new route option to Maps in iOS 29.',
            'Maps offers route planning on iPhone. Apple will add a new route option to Maps in iOS 29.',
        ):
            with self.subTest(opening=opening):
                p=m.source_text_profile(title,opening+archive,[opening+archive],'Fixture News')
                self.assertEqual(p.identity.content_form,'tutorial')
                self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'weak')

    def test_priority_reuses_only_exact_local_kind_input(self):
        from unittest import mock
        m=self.m
        c=m.Candidate(source='Fixture News',url='https://fixture.example/current-feature',title='iOS 29 adds a new Maps route option',summary='Apple today added a new route option to Maps in iOS 29.',context='Cyclists can avoid steep hills.')
        with mock.patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
            m.candidate_detail_priority(c)
        calls=[call for call in detect.call_args_list if call.args==(c.title,c.summary,[c.context])]
        self.assertEqual(len(calls),1)

    def test_kind_snapshot_is_exact_and_never_inherited_by_parent(self):
        from unittest import mock
        from dataclasses import asdict
        m=self.m
        title='iOS 29 adds a new Maps route option'
        summary='Apple today added a new route option to Maps in iOS 29.'
        facts=['Cyclists can avoid steep hills.','The setting is optional.']
        kind=m.detect_event_kind(title,summary,facts)
        snapshot=(title,summary,tuple(facts),kind)
        def article(t,s,f):
            return m.Article(source='Fixture News',url='https://fixture.example/snapshot',title=t,summary=s,key_facts=list(f),category='',published_utc=datetime(2030,9,21,tzinfo=timezone.utc),published_raw='',published_source='fixture',confidence='detail',tokens=set(),event_kind=kind)
        for t,s,f in [(title+' for cyclists',summary,facts),(title,summary+' A new control is available.',facts),(title,summary,[facts[0]]),(title,summary,list(reversed(facts)))]:
            with self.subTest(title=t,summary=s,facts=f):
                reference=m.article_reconciliation_profile(article(t,s,f))
                with mock.patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
                    actual=m.article_reconciliation_profile(article(t,s,f),_source_kind_snapshot=snapshot)
                self.assertEqual(asdict(actual),asdict(reference))
                self.assertTrue(any(c.args==(t,s,f) for c in detect.call_args_list))
                self.assertEqual(asdict(m.source_text_profile(t,s,f,'Fixture News',_source_kind_snapshot=snapshot)),asdict(m.source_text_profile(t,s,f,'Fixture News')))
        parent='iOS 29 is now available for public download'
        reference=m.source_text_profile(title,summary,facts,'Fixture News',source_title=parent)
        with mock.patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
            actual=m.source_text_profile(title,summary,facts,'Fixture News',source_title=parent,_source_kind_snapshot=snapshot)
        self.assertEqual(asdict(actual),asdict(reference))
        self.assertTrue(any(c.args==(parent,summary,[]) for c in detect.call_args_list))
        self.assertFalse(any(c.args==(title,summary,facts) for c in detect.call_args_list))

    def test_kind_snapshot_keeps_sparse_bound_completion(self):
        from dataclasses import asdict
        m=self.m
        title='Siri 十月新增法语支持。'
        for summary,facts in [('',[]),('Siri 十月新增法语支持。',[])]:
            with self.subTest(summary=summary):
                kind=m.detect_event_kind(title,summary,facts)
                reference=m.source_text_profile(title,summary,facts,'Fixture News')
                actual=m.source_text_profile(title,summary,facts,'Fixture News',_source_kind_snapshot=(title,summary,tuple(facts),kind))
                self.assertIsNotNone(actual.bound_claim)
                self.assertEqual(asdict(actual),asdict(reference))

    def natural_claim_articles(self):
        import hashlib
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        articles = {}
        for row in self.fixture['natural_source_claims']['sources']:
            ident = hashlib.sha256(row['url'].encode()).hexdigest()[:24]
            units = tuple(EvidenceUnit(hashlib.sha256((ident + str(n)).encode()).hexdigest()[:24],
                u['kind'], u['text'], 'synthetic-captured', u['ordinal']) for n,u in enumerate(row['units']))
            ev = ArticleEvidence(ident,row['source'],row['url'],row['title'],row['summary'],'news',units,confidence='detail')
            articles[row['id']] = self.m.Article(source=row['source'],url=row['url'],title=row['title'],
                summary=row['summary'],key_facts=row['key_facts'],category='',
                published_utc=datetime(2030,9,21,tzinfo=timezone.utc),published_raw='2030-09-21',
                published_source='synthetic',confidence='detail',tokens=set(),evidence=ev)
        return articles

    def test_natural_current_source_claims_keep_concrete_actions(self):
        a=self.natural_claim_articles();p={k:self.m.article_reconciliation_profile(v) for k,v in a.items()}
        for row in self.fixture['natural_source_claims']['pairs']:
            with self.subTest(left=row['left'],right=row['right']):
                self.assertEqual(self.m.profile_pair_decision(p[row['left']],p[row['right']]),row['expected'])
        for key,index,want in [('s13',0,'strong'),('s37',0,'strong'),('s16',0,'strong'),
                               ('s9',0,'weak'),('s8',2,'software_systems'),('s21',2,'hardware_products')]:
            with self.subTest(source=key,field=index):
                self.assertEqual(self.m.resolve_reconciliation_outcome(p[key],observed_tier='',observed_reason='',observed_category='')[index],want)
        self.assertNotIn('primary-claim:apple-iphone-group:workforce-reduction',p['s17'].event_keys)
        self.assertNotIn('health data research',self.m.resolve_reconciliation_outcome(p['s26'],observed_tier='',observed_reason='',observed_category='')[1])

    def test_current_hardware_release_uses_own_lead_not_research_background(self):
        import hashlib
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        m=self.m
        for row in self.fixture['current_hardware_release']['sources']:
            aid=hashlib.sha256(row['url'].encode()).hexdigest()[:24]
            units=tuple(EvidenceUnit(hashlib.sha256((aid+str(n)).encode()).hexdigest()[:24],u['kind'],u['text'],'synthetic-captured',u['ordinal']) for n,u in enumerate(row['units']))
            ev=ArticleEvidence(aid,row['source'],row['url'],row['title'],row['summary'],'news',units,confidence='detail')
            a=m.Article(source=row['source'],url=row['url'],title=row['title'],summary=row['summary'],key_facts=list(row['key_facts']),category='',published_utc=datetime(2030,8,20,tzinfo=timezone.utc),published_raw='2030-08-20',published_source='synthetic',confidence='detail',tokens=set(),evidence=ev)
            with self.subTest(source=row['id']):
                p=m.article_reconciliation_profile(a)
                outcome=m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')
                self.assertEqual((outcome[0],outcome[2]),('strong','hardware_products'))
                self.assertNotIn('health data research',outcome[1])
                events=m.cluster_articles([a])
                self.assertEqual(len(events),1)
                self.assertEqual((events[0].relevance_tier,events[0].category),('strong','hardware_products'))

    def test_release_support_requires_current_publisher_and_direct_hardware_object(self):
        from apple_news_core.event_reconciler import _source_current_hardware_release
        m=self.m; title="Apple Watch hardware specifications explained"
        identity=m.title_led_identity(title,"")
        for lead,want in [
            ("Apple today released the new Apple Watch with updated sensors.",True),
            ("Apple previously released the new Apple Watch with updated sensors.",False),
            ("Apple will release the new Apple Watch with updated sensors.",False),
            ("Apple has not released the new Apple Watch with updated sensors.",False),
            ("Samsung today released the new Apple Watch demonstration guide.",False),
            ("Apple today released a guide to the Apple Watch.",False),
            ("Apple today released an update for the Apple Watch.",False),
            ("Apple today released the new iPad with updated sensors.",False),
        ]:
            with self.subTest(lead=lead):
                self.assertEqual(_source_current_hardware_release(lead,identity),want)

    def test_complete_selected_source_faq_consumes_only_its_complete_condition(self):
        import hashlib
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        m=self.m;r=self.fixture['selected_faq_consumption'];aid=hashlib.sha256(r['url'].encode()).hexdigest()[:24]
        units=tuple(EvidenceUnit(hashlib.sha256((aid+str(n)).encode()).hexdigest()[:24],u['kind'],u['text'],'synthetic-captured',u['ordinal']) for n,u in enumerate(r['units']))
        ev=ArticleEvidence(aid,r['source'],r['url'],r['title'],r['summary'],'news',units,confidence='detail')
        a=m.Article(source=r['source'],url=r['url'],title=r['title'],summary=r['summary'],key_facts=list(r['key_facts']),category='',published_utc=datetime(2030,8,20,tzinfo=timezone.utc),published_raw='2030-08-20',published_source='synthetic',confidence='detail',tokens=set(),evidence=ev)
        v=m.prepare_source_fact_view(a);target=r['target']
        def plan(views):return m.resolve_event_fact_plan(views,relevance_tier='weak',base_limit=10,official_limit=16)
        p=plan([v]);kept=[f for f in p.facts if target in f.text]
        self.assertTrue(kept)
        self.assertFalse(any(f.text==target for f in p.unprocessed))
        final=[m.event_to_dict(e,timezone.utc) for e in m.cluster_articles([a])]
        self.assertTrue(any(target in f['text'] and any(o['url']==r['url'] for o in f['origins']) for e in final for f in e['fact_sources']))
        local=replace(v,normal=tuple(f for f in v.normal if target not in f.text),responses=tuple(f for f in v.responses if target not in f.text),summary_units=())
        self.assertTrue(any(f.text==target for f in plan([local]).unprocessed))
        other_url=r['url']+'-independent';other_id=hashlib.sha256(other_url.encode()).hexdigest()[:24]
        foreign=tuple(replace(f,origins=tuple(('Independent',other_url,other_id,'',0,0) for _ in f.origins)) for f in kept)
        other=replace(v,source='Independent',url=other_url,normal=foreign,responses=(),structured=(),owned=(),required_actions=(),unprocessed=(),summary_units=())
        foreign_plan=plan([local,other])
        self.assertTrue(any(target in f.text and any(o[1]==other_url for o in f.origins) for f in foreign_plan.facts))
        self.assertTrue(any(f.text==target for f in foreign_plan.unprocessed))
        pending=next(f for f in v.unprocessed if f.text==target)
        # A matching suffix inside a condition is not the complete assertion.
        carrier=replace(kept[0],text="仅在满足额外条件时，"+target,key="condition-carrier")
        scoped=replace(local,normal=(carrier,),responses=(),structured=(),owned=(),required_actions=(),unprocessed=(pending,))
        self.assertIn(pending,plan([scoped]).unprocessed)
        extra=replace(pending,text=target+"仅限已完成注册的玩家。")
        self.assertIn(extra,plan([replace(v,unprocessed=(extra,))]).unprocessed)
        attribution=replace(pending,roles=pending.roles|frozenset({'unverified-attribution'}))
        self.assertIn(attribution,plan([replace(v,unprocessed=(attribution,))]).unprocessed)

    def test_workforce_reduction_keeps_local_department_and_personnel_object(self):
        m=self.m
        cases=[
            ("Apple trims Vision Pro gaming staff", "Apple trims Vision Pro gaming staff in its current restructuring.", True),
            ("Apple adjusts its Vision Pro organization", "Apple cut Vision Pro gaming and immersive video roles in its current restructuring.", True),
            ("Apple adjusts its Vision Pro organization", "Samsung cut Vision Pro demonstration staff while Apple retained its team.", False),
            ("Apple adjusts its Vision Pro organization", "Years earlier, Apple cut Vision Pro demonstration roles; the current plan retains staff.", False),
            ("Apple cuts prices for Vision Pro staff", "Apple cuts prices for Vision Pro staff purchases without eliminating jobs.", False),
        ]
        for title,summary,want in cases:
            with self.subTest(title=title,summary=summary):
                p=m.source_text_profile(title,summary,[],"Fixture News")
                self.assertEqual('primary-claim:apple-vision-group:workforce-reduction' in p.event_keys,want)

    def test_natural_source_conditions_have_local_exact_dispositions(self):
        import re
        a=self.natural_claim_articles();norm=lambda x:re.sub(r'\s+','',x).casefold()
        for key,targets in self.fixture['natural_source_claims']['fact_targets'].items():
            article=a[key];view=self.m.prepare_source_fact_view(article)
            plan=self.m.resolve_event_fact_plan([view],relevance_tier='strong',base_limit=10,official_limit=16)
            units={u.unit_id:u.text for u in article.evidence.units}
            for target in targets:
                with self.subTest(source=key,target=target):
                    facts=[f for f in (*plan.facts,*plan.unprocessed) if norm(target) in norm(f.text) and any(o[1]==article.url for o in f.origins)]
                    self.assertTrue(facts)
                    for fact in facts:
                        self.assertTrue(any(o[3] and units[o[3]][o[4]:o[5]]==fact.text for o in fact.origins))

    def test_natural_claims_keep_other_investigator_fault_and_source_boundaries(self):
        m=self.m;a=self.natural_claim_articles()
        import json
        def changed(article,old,new):
            return replace(article,title=article.title.replace(old,new),summary=article.summary.replace(old,new),
                key_facts=[v.replace(old,new) for v in article.key_facts],url=article.url+'/changed',evidence=None)
        for key,old,new in [('s7','iProbe','iMeasure'),('s7','iPhone 17','iPhone 16')]:
            with self.subTest(key=key,change=new):
                self.assertNotEqual(m.profile_pair_decision(m.article_reconciliation_profile(a[key]),m.article_reconciliation_profile(changed(a[key],old,new))),'match')
        first=a['s12'];other=a['s19']
        for old,new in [('Reset Fault','Camera Fault'),('ResetFault','CameraFault'),('Face ID','camera preview'),('死机','相机花屏'),('重启','花屏'),('关机','花屏')]:other=changed(other,old,new)
        self.assertNotEqual(m.profile_pair_decision(m.article_reconciliation_profile(first),m.article_reconciliation_profile(other)),'match')
        # A second participant in the same source does not replace the stated
        # hardware speaker or the shared interview's concrete disclosure.
        joint=replace(a['s37'],summary=a['s37'].summary+' 另一位设计负责人也参加了同场集体采访。')
        self.assertEqual(m.profile_pair_decision(m.article_reconciliation_profile(a['s13']),m.article_reconciliation_profile(joint)),'match')
        p=m.resolve_event_fact_plan([m.prepare_source_fact_view(a['s15'])],relevance_tier='strong',base_limit=30,official_limit=30)
        self.assertFalse(any('make sure you catch' in f.text.lower() for f in (*p.facts,*p.required,*p.unprocessed)))

    def test_natural_source_conditions_final_queue_and_serialized_spans(self):
        from unittest.mock import patch
        import tempfile,re
        m=self.m;articles=self.natural_claim_articles();by_url={a.url:a for a in articles.values()}
        candidates=[m.Candidate(a.source,a.url,a.title,a.summary) for a in articles.values()]
        now=m.utc_now()
        def captured(source,url,*args):return by_url[url].evidence
        def extracted(candidate,*args):
            a=by_url[candidate.url]
            return a.title,a.summary,a.key_facts,now,now.isoformat(),'detail','detail'
        with tempfile.TemporaryDirectory() as directory:
            args=m.parse_args(['--timezone','Asia/Singapore','--cache-dir',directory])
            with patch.object(m,'build_sources',return_value=[m.Source(a.source,'UTC') for a in articles.values()]), \
                 patch.object(m,'collect_candidates_from_sources',return_value=candidates), \
                 patch.object(m,'select_detail_candidates',return_value=candidates), \
                 patch.object(m,'fetch_detail_page_texts',return_value=['<article></article>']*len(candidates)), \
                 patch.object(m,'capture_article_evidence',side_effect=captured), \
                 patch.object(m,'extract_article',side_effect=extracted):
                result=m.run(args)
        scaffold=m.render_brief_scaffold(result)
        norm=lambda t:re.sub(r'\s+','',t).casefold()
        for key,targets in self.fixture['natural_source_claims']['fact_targets'].items():
            a=articles[key]
            for target in targets:
                with self.subTest(source=key,target=target):
                    reviews=[(q,u) for q in result['final_brief_queue'] if a.url in q.get('source_urls',[]) for u in q.get('unprocessed_evidence',[]) if norm(target) in norm(u['text'])]
                    facts=[f for e in result['events']+result['deferred_events'] for f in e.get('fact_sources',[]) if norm(target) in norm(f['text']) and any(o['url']==a.url for o in f['origins'])]
                    self.assertTrue(reviews or facts)
                    if reviews:
                        self.assertIn(norm(target),norm(scaffold))
                        for q,u in reviews:
                            self.assertTrue(q['reason'])
                            original=next(v for v in result['source_evidence'][q['evidence_id']]['units'] if v['unit_id']==u['unit_id'])
                            self.assertEqual(original['text'][u['start']:u['end']],u['text'])

    def test_natural_source_qualification_scope_and_selected_coverage(self):
        m=self.m
        a=self.natural_claim_articles()['s25']
        from apple_news_core.models import EvidenceUnit
        target='视频录制时，白平衡稳定性还有提升空间，在不同光线环境下偶尔会出现较明显的变化。'
        variants=[
            ('current',target,True),
            ('historical','去年'+target,False),
            ('foreign','Samsung says its camera may still need better white balance.',False),
        ]
        for label,text,wanted in variants:
            with self.subTest(label=label):
                unit=EvidenceUnit('scope-'+label,'p',text,'synthetic-captured',0)
                source=replace(a,evidence=replace(a.evidence,units=(unit,)),key_facts=[])
                view=m.prepare_source_fact_view(source)
                pending=[f for f in view.unprocessed if 'unprocessed-source-qualification' in f.roles]
                self.assertEqual(bool(pending),wanted)
                if wanted:
                    selected=replace(source,key_facts=[text])
                    plan=m.resolve_event_fact_plan([m.prepare_source_fact_view(selected)],relevance_tier='strong',base_limit=30,official_limit=30)
                    self.assertTrue(any(f.text==text for f in plan.facts))
                    self.assertFalse(any(f.text==text for f in plan.unprocessed))
        original=self.natural_claim_articles()['s7']
        same=self.natural_claim_articles()['s15']
        chinese=[self.natural_claim_articles()[k] for k in ('s30','s31')]
        other=replace(original,title=original.title.replace('iProbe','iMeasure'),summary=original.summary.replace('iProbe','iMeasure'),
            key_facts=[v.replace('iProbe','iMeasure') for v in original.key_facts],url=original.url+'/other',evidence=None)
        for members in ([original,same,*chinese,other],[other,*reversed(chinese),same,original]):
            groups=m.cluster_articles(members)
            self.assertEqual(sorted(len(e.articles) for e in groups),[1,4])

    def test_qualification_remainder_is_not_duplicated_by_prepared_parent_span(self):
        import re
        m=self.m;articles=self.natural_claim_articles();norm=lambda t:re.sub(r'\s+','',t).casefold()
        for key,targets in self.fixture['natural_source_claims']['fact_targets'].items():
            a=articles[key]
            for target in targets:
                with self.subTest(source=key,target=target):
                    units=[u.text for u in a.evidence.units if norm(target) in norm(u.text)]
                    selected=replace(a,key_facts=[*a.key_facts,*units])
                    plan=m.resolve_event_fact_plan([m.prepare_source_fact_view(selected)],relevance_tier='strong',base_limit=10,official_limit=16)
                    retained=[f for f in (*plan.facts,*plan.unprocessed) if norm(target) in norm(f.text) and any(o[1]==a.url for o in f.origins)]
                    self.assertEqual(len(retained),1)

    def test_qualification_remainder_consumes_only_emitted_local_summary(self):
        m=self.m;a=self.natural_claim_articles()['s14']
        text=a.evidence.units[1].text
        a=replace(a,summary=text+' '+text+' '+a.evidence.units[2].text,key_facts=[])
        view=m.prepare_source_fact_view(a)
        target=next(f for f in view.unprocessed if f.text==text)
        def plan(views):
            return m.resolve_event_fact_plan(views,relevance_tier='strong',base_limit=10,official_limit=16)
        result=plan([view])
        self.assertIn(text,result.summary)
        self.assertNotIn(target,result.unprocessed)
        extra=replace(target,text=text+' The battery safety condition remains unresolved.')
        self.assertIn(extra,plan([replace(view,unprocessed=(extra,))]).unprocessed)
        independent=replace(target,roles=target.roles|frozenset({'unverified-attribution'}))
        self.assertIn(independent,plan([replace(view,unprocessed=(independent,))]).unprocessed)
        other=replace(view,url=a.url+'-other',source='Independent',summary_units=())
        local=replace(target,origins=tuple(('Independent',other.url,*o[2:]) for o in target.origins))
        self.assertIn(local,plan([view,replace(other,unprocessed=(local,))]).unprocessed)
        # Input summary is not consumption if the three display slots filled
        # before this source. No cross-source display or raw-summary shortcut.
        first=replace(view,source_priority=-1,source='First',url=a.url+'-first',
                      summary_units=('First separate detail.','Second separate detail.','Third separate detail.'),unprocessed=())
        self.assertIn(target,plan([first,view]).unprocessed)

    def test_fact_view_reuses_only_local_invariant_source_preparation(self):
        import sys
        import re
        from unittest.mock import patch
        from apple_news_core.models import BoundClaim
        m=self.m
        original=m.article_title_led_event_identity
        build=m.build_event_identity
        for article in self.natural_claim_articles().values():
            unit=article.evidence.units[1]
            bound=BoundClaim('fixture-subject','fixture-action','fixture-object',(),
                article.evidence.article_id,(unit.unit_id,),((unit.unit_id,0,len(unit.text)),),'news')
            variants=(article,replace(article,evidence=None),replace(article,projected_fact_spans=()),
                      replace(article,bound_claim=bound))
            for variant in variants:
                counts=[];unneeded=[]
                def observed(*args,**kwargs):
                    if sys._getframe(1).f_code.co_name in {'prepare_source_fact_view','local_source_identity'}:
                        counts.append(args)
                    return original(*args,**kwargs)
                def observed_build(title,summary,*args,**kwargs):
                    if sys._getframe(1).f_code.co_name=='prepare_source_fact_view' and not re.search(r'苹果|\bApple\b',title,re.I):
                        unneeded.append(title)
                    return build(title,summary,*args,**kwargs)
                with self.subTest(url=article.url,projected=variant.projected_fact_spans,
                                  evidence=bool(variant.evidence),bound=bool(variant.bound_claim)):
                    with patch.object(m,'article_title_led_event_identity',new=observed),patch.object(m,'build_event_identity',new=observed_build):
                        m.prepare_source_fact_view(variant)
                    self.assertLessEqual(len(counts),1)
                    self.assertFalse(unneeded)
                    if variant.evidence is None or variant.bound_claim or variant.projected_fact_spans is not None:
                        self.assertEqual(counts,[])

    def test_run_kind_snapshot_is_exact_private_and_copy_safe(self):
        import copy
        from dataclasses import asdict
        from unittest.mock import patch
        m=self.m;a=self.natural_claim_articles()['s0']
        kind=m.detect_event_kind(a.title,a.summary,a.key_facts)
        base=asdict(a)
        a._source_kind_snapshot=(a.title,a.summary,tuple(a.key_facts),kind)
        reference=m.article_reconciliation_profile(replace(a))
        with patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
            self.assertEqual(m.article_reconciliation_profile(a),reference)
        self.assertFalse(any(c.args==(a.title,a.summary,a.key_facts) for c in detect.call_args_list))
        self.assertEqual(asdict(a),base)
        self.assertEqual(asdict(copy.deepcopy(a)),base)
        for variant,wants_recompute in (
                (copy.deepcopy(a),False),(replace(a),True),
                (replace(a,event_kind='intentionally-wrong'),True)):
            with self.subTest(recompute=wants_recompute):
                with patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
                    actual=m.article_reconciliation_profile(variant)
                self.assertEqual(actual,reference)
                self.assertEqual(any(c.args==(variant.title,variant.summary,variant.key_facts) for c in detect.call_args_list),wants_recompute)
        explicit_mismatch=(a.title+' different',a.summary,tuple(a.key_facts),kind)
        with patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
            m.article_reconciliation_profile(a,_source_kind_snapshot=explicit_mismatch)
        self.assertTrue(any(c.args==(a.title,a.summary,a.key_facts) for c in detect.call_args_list))
        parent=replace(a,title='Apple publishes a separate source report',summary='A separate source introduction.',key_facts=[])
        self.assertIsNone(parent._source_kind_snapshot)
        sparse=replace(a,title='Siri 十月新增法语支持。',summary='',key_facts=[],evidence=None,bound_claim=None)
        sparse._source_kind_snapshot=(sparse.title,sparse.summary,(), 'not-a-bound-decision')
        with patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
            bound_profile=m.article_reconciliation_profile(sparse)
        self.assertIsNotNone(bound_profile.bound_claim)
        self.assertFalse(detect.called)
        for change in ('title','summary','fact','order'):
            variant=copy.deepcopy(a)
            if change=='title':variant.title+=' report'
            elif change=='summary':variant.summary+=' A separately attributed observation.'
            elif change=='fact':variant.key_facts=[*variant.key_facts,'Additional local detail.']
            else:variant.key_facts=list(reversed(variant.key_facts))
            self.assertNotEqual(variant._source_kind_snapshot[:3],(variant.title,variant.summary,tuple(variant.key_facts)))
            with patch.object(m,'detect_event_kind',wraps=m.detect_event_kind) as detect:
                actual=m.article_reconciliation_profile(variant)
            self.assertTrue(any(c.args==(variant.title,variant.summary,variant.key_facts) for c in detect.call_args_list))
            self.assertEqual(actual,m.article_reconciliation_profile(replace(variant)))

    def test_priority_identity_preparation_reuses_only_exact_local_inputs(self):
        from contextlib import nullcontext
        from unittest.mock import patch
        from apple_news_core import event_identity as identity
        scope=getattr(identity,'_identity_preparation_scope',nullcontext)
        args=('Apple releases iOS 31','Apple released iOS 31 today.',('one','two'),('first','second'))
        with patch.object(identity,'_content_form',wraps=identity._content_form) as work:
            with scope():
                first=identity.build_event_identity(*args)
                second=identity.build_event_identity(*args)
                self.assertEqual(first,second)
            self.assertEqual(work.call_count,1)
            identity.build_event_identity(*args)
            self.assertEqual(work.call_count,2)
        for position in range(4):
            changed=list(args)
            changed[position]=changed[position]+' changed' if position<2 else tuple(reversed(changed[position]))
            with scope(),patch.object(identity,'_content_form',wraps=identity._content_form) as work:
                identity.build_event_identity(*args)
                identity.build_event_identity(*changed)
                self.assertEqual(work.call_count,2)

    def test_priority_identity_preparation_scope_exits_and_iterables_remain_uncached(self):
        from unittest.mock import patch
        from concurrent.futures import ThreadPoolExecutor
        from apple_news_core import event_identity as identity
        scope=identity._identity_preparation_scope
        args=('Apple releases iOS 31','Apple released iOS 31 today.')
        with patch.object(identity,'_content_form',wraps=identity._content_form) as work:
            with scope():
                identity.build_event_identity(*args)
                with scope():identity.build_event_identity(*args)
                identity.build_event_identity(*args)
                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(identity.build_event_identity,*args).result()
            self.assertEqual(work.call_count,3)
        with self.assertRaisesRegex(RuntimeError,'scope exit'):
            with scope():
                identity.build_event_identity(*args)
                raise RuntimeError('scope exit')
        with patch.object(identity,'_content_form',return_value='tutorial'):
            with scope():self.assertEqual(identity.build_event_identity(*args).content_form,'tutorial')
        with patch.object(identity,'_content_form',wraps=identity._content_form) as work:
            with scope():
                for _ in range(2):identity.build_event_identity(*args,identity_evidence=(v for v in ('detail',)))
            self.assertEqual(work.call_count,2)
        original=identity.build_event_identity(*args)
        with scope(),patch.object(identity,'_build_event_identity',side_effect=[ValueError('construction failed'),original]) as work:
            with self.assertRaisesRegex(ValueError,'construction failed'):
                identity.build_event_identity(*args)
            self.assertEqual(identity.build_event_identity(*args),original)
            self.assertEqual(work.call_count,2)
        class CustomList(list):pass
        class CustomString(str):pass
        for value in (CustomList(['one']),[CustomString('one')]):
            with scope(),patch.object(identity,'_content_form',wraps=identity._content_form) as work:
                for _ in range(2):identity.build_event_identity(*args,facets=value)
                self.assertEqual(work.call_count,2)

    def test_priority_identity_preparation_preserves_entry_point_and_patch_calls(self):
        from unittest.mock import patch
        from apple_news_core import event_identity as identity
        m=self.m
        c=m.Candidate(source='Fixture News',url='https://fixture.example/current-feature',title='iOS 29 adds a new Maps route option',summary='Apple today added a new route option to Maps in iOS 29.',context='Cyclists can avoid steep hills.')
        m._candidate_detail_priority(c)
        with patch.object(identity,'_build_event_identity',wraps=identity._build_event_identity) as work:
            expected=m._candidate_detail_priority(c)
            uncached=work.call_count
        with patch.object(identity,'_build_event_identity',wraps=identity._build_event_identity) as work:
            actual=m.candidate_detail_priority(c)
            self.assertEqual(actual,expected)
            self.assertLess(work.call_count,uncached)
        with patch.object(m,'build_event_identity',wraps=m.build_event_identity) as calls:
            self.assertEqual(m.candidate_detail_priority(c),expected)
            self.assertTrue(calls.called)
        self.assertIsNone(identity._identity_preparation.get())

    def kind_live_articles(self):
        import hashlib
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        m=self.m;articles={}
        for row in self.fixture['kind_live_relations']['sources']:
            ident=hashlib.sha256(row['url'].encode()).hexdigest()[:24]
            units=tuple(EvidenceUnit(hashlib.sha256((ident+str(n)).encode()).hexdigest()[:24],u['kind'],u['text'],'synthetic-captured',u['ordinal']) for n,u in enumerate(row['units']))
            evidence=ArticleEvidence(ident,row['source'],row['url'],row['title'],row['summary'],'news',units,confidence='detail')
            articles[row['id']]=m.Article(source=row['source'],url=row['url'],title=row['title'],summary=row['summary'],key_facts=row['key_facts'],category='',published_utc=datetime(2030,9,21,tzinfo=timezone.utc),published_raw='2030-09-21',published_source='synthetic',confidence='detail',tokens=m.article_tokens(row['title'],' '.join([row['summary'][:1200],*row['key_facts'][:5]])),evidence=evidence,event_kind=m.detect_event_kind(row['title'],row['summary'],row['key_facts']),regions=m.extract_regions(' '.join([row['title'],row['summary'],*row['key_facts'][:5]])),projection_source_title=row['title'])
        return articles

    def test_kind_live_local_report_relationships_and_full_groups(self):
        m=self.m;a=self.kind_live_articles();p={k:m.article_reconciliation_profile(v) for k,v in a.items()}
        for row in self.fixture['kind_live_relations']['pairs']:
            with self.subTest(pair=row):self.assertEqual(m.profile_pair_decision(p[row['left']],p[row['right']]),row['expected'])
        for keys in (['teardown_report','teardown_news','teardown_followup','teardown_camera','teardown_score'],['yield_news','yield_response','yield_supply'],['sales_data','sales_followup','sales_social']):
            for ordered in (keys,list(reversed(keys))):
                with self.subTest(group=ordered):self.assertEqual(len(m.cluster_articles([replace(a[k]) for k in ordered])),1)
        for key,tier in [('photo_tutorial','weak'),('camera_news','strong')]:
            self.assertEqual(m.resolve_reconciliation_outcome(p[key],observed_tier='',observed_reason='',observed_category='')[0],tier)
        other=replace(a['teardown_news'],title=a['teardown_news'].title.replace('iPhone 18','iPhone 16'),summary=a['teardown_news'].summary.replace('iPhone 18','iPhone 16'),key_facts=[v.replace('iPhone 18','iPhone 16') for v in a['teardown_news'].key_facts],evidence=None)
        self.assertNotEqual(m.profile_pair_decision(p['teardown_news'],m.article_reconciliation_profile(other)),'match')
        self.assertFalse(any('percent:70' in key and ('oled' in key or 'display-panel' in key) for key in p['yield_supply'].event_keys))
        self.assertFalse(any('structured-attributed-measure:john-ternus' in key for key in p['sales_social'].event_keys))

    def test_kind_live_remainders_are_local_to_exact_original_units(self):
        import re
        m=self.m;a=self.kind_live_articles();norm=lambda t:re.sub(r'\s+','',t).casefold()
        for key,targets in self.fixture['kind_live_relations']['fact_targets'].items():
            source=a[key]
            for selected in (False,True):
                article=replace(source,key_facts=[*(u.text for u in source.evidence.units),*source.key_facts]) if selected else source
                plan=m.resolve_event_fact_plan([m.prepare_source_fact_view(article)],relevance_tier='strong',base_limit=10,official_limit=16)
                for target in targets:
                    with self.subTest(source=key,target=target,selected=selected):
                        units={u.unit_id:u for u in source.evidence.units if (norm(target)==norm(u.text) if len(target)<35 else norm(target) in norm(u.text))}
                        found=[f for f in (*plan.facts,*plan.unprocessed) if norm(target) in norm(f.text) and any(o[1]==source.url and o[3] in units for o in f.origins)]
                        self.assertTrue(found)
                        for fact in found:
                            for origin in fact.origins:
                                if origin[3] in units:self.assertEqual(units[origin[3]].text[origin[4]:origin[5]],fact.text)

    def test_kind_live_report_objects_and_attributions_are_source_local(self):
        m=self.m;a=self.kind_live_articles()
        def swapped(article,old,new):
            return replace(article,title=article.title.replace(old,new),summary=article.summary.replace(old,new),key_facts=[f.replace(old,new) for f in article.key_facts],evidence=None,url=article.url+'/changed')
        for left,right,old,new in [('teardown_report','teardown_news','iProbe','RepairLab'),('sales_social','sales_data','数码观测站','移动数据观察')]:
            one=swapped(a[left],old,new);two=swapped(a[right],old,new)
            self.assertEqual(m.profile_pair_decision(m.article_reconciliation_profile(one),m.article_reconciliation_profile(two)),'match')
            self.assertNotEqual(m.profile_pair_decision(m.article_reconciliation_profile(one),m.article_reconciliation_profile(a[right])),'match')
        panel=swapped(a['yield_supply'],'整机良率','面板良率')
        p=m.article_reconciliation_profile(panel)
        self.assertFalse(any('device-assembly-yield-report' in k for k in p.event_keys))
        orphan=replace(a['settlement'],key_facts=[],evidence=replace(a['settlement'].evidence,units=tuple(u for u in a['settlement'].evidence.units if u.text=='iPhone 16')))
        plan=m.resolve_event_fact_plan([m.prepare_source_fact_view(orphan)],relevance_tier='strong',base_limit=10,official_limit=16)
        self.assertFalse(any(f.text=='iPhone 16' for f in plan.unprocessed))

    def test_kind_live_required_facts_survive_real_run_with_original_unit_spans(self):
        import re,tempfile
        from unittest.mock import patch
        m=self.m;all_articles=self.kind_live_articles();articles={k:all_articles[k] for k in self.fixture['kind_live_relations']['fact_targets']}
        by_url={a.url:a for a in articles.values()};candidates=[m.Candidate(a.source,a.url,a.title,a.summary) for a in articles.values()];now=m.utc_now()
        def extracted(c,*args):
            a=by_url[c.url];return a.title,a.summary,a.key_facts,now,now.isoformat(),'detail','detail'
        with tempfile.TemporaryDirectory() as directory:
            args=m.parse_args(['--timezone','Asia/Singapore','--cache-dir',directory])
            with patch.object(m,'build_sources',return_value=[m.Source(a.source,'UTC') for a in articles.values()]),patch.object(m,'collect_candidates_from_sources',return_value=candidates),patch.object(m,'select_detail_candidates',return_value=candidates),patch.object(m,'fetch_detail_page_texts',return_value=['<article></article>']*len(candidates)),patch.object(m,'capture_article_evidence',side_effect=lambda source,url,*args:by_url[url].evidence),patch.object(m,'extract_article',side_effect=extracted):
                result=m.run(args)
        scaffold=m.render_brief_scaffold(result);norm=lambda t:re.sub(r'\s+','',t).casefold()
        for key,targets in self.fixture['kind_live_relations']['fact_targets'].items():
            a=articles[key]
            for target in targets:
                with self.subTest(source=key,target=target):
                    ids={u.unit_id for u in a.evidence.units if (norm(target)==norm(u.text) if len(target)<35 else norm(target) in norm(u.text))}
                    reviews=[(q,u) for q in result['final_brief_queue'] if a.url in q.get('source_urls',[]) for u in q.get('unprocessed_evidence',[]) if u['unit_id'] in ids and norm(target) in norm(u['text'])]
                    facts=[f for e in result['events']+result['deferred_events'] for f in e.get('fact_sources',[]) if norm(target) in norm(f['text']) and any(o['url']==a.url and o.get('unit_id') in ids for o in f['origins'])]
                    self.assertTrue(reviews or facts)
                    self.assertIn(norm(target),norm(scaffold))
                    for q,u in reviews:
                        original=next(v for v in result['source_evidence'][q['evidence_id']]['units'] if v['unit_id']==u['unit_id'])
                        self.assertEqual(original['text'][u['start']:u['end']],u['text'])
                        self.assertTrue(u.get('reason') or q.get('reason'))

    def test_paragraph_list_replacement_requires_same_unit_exact_coverage(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        m = self.m
        for row in self.fixture['paragraph_list_units']:
            with self.subTest(case=row['id']):
                units = tuple(EvidenceUnit(f"{row['id']}-{i}", u['kind'], u['text'], 'synthetic-captured', i)
                              for i, u in enumerate(row['units']))
                evidence = ArticleEvidence(row['id'], row['source'], row['url'], row['title'], row['summary'], 'news', units, confidence='detail')
                article = m.Article(source=row['source'], url=row['url'], title=row['title'], summary=row['summary'],
                    key_facts=row['key_facts'], category='', published_utc=datetime(2030,9,21,tzinfo=timezone.utc),
                    published_raw='2030-09-21', published_source='synthetic', confidence='detail',
                    tokens=m.article_tokens(row['title'], ' '.join([row['summary'][:1200], *row['key_facts'][:5]])),
                    evidence=evidence, event_kind=m.detect_event_kind(row['title'], row['summary'], row['key_facts']),
                    regions=m.extract_regions(' '.join([row['title'], row['summary'], *row['key_facts'][:5]])),
                    projection_source_title=row['title'])
                plan = m.resolve_event_fact_plan([m.prepare_source_fact_view(article)], relevance_tier='strong', base_limit=10, official_limit=16)
                for target in row['targets']:
                    unit = units[target['unit']]
                    self.assertTrue(any(target['text'] in f.text and any(o[1] == article.url and o[3] == unit.unit_id
                        and unit.text[o[4]:o[5]] == f.text for o in f.origins) for f in (*plan.facts, *plan.unprocessed)), target['text'])
                if row.get('replaceable_whole'):
                    self.assertNotIn(row['replaceable_whole'], [f.text for f in (*plan.facts, *plan.unprocessed)])

    def test_podcast_credit_lists_do_not_become_required_news_facts(self):
        import socket, tempfile
        from unittest.mock import patch
        from apple_news_core.article_projector import source_evidence_remainder
        m = self.m
        rows = self.fixture['podcast_editorial_lists']
        numeric_publisher = json.loads(json.dumps(rows[0], ensure_ascii=False).replace('Orchard','7to3Orchard'))
        for row in [*rows, numeric_publisher]:
            with self.subTest(case=row['id']), tempfile.TemporaryDirectory() as directory:
                c = m.Candidate(row['source'], row['url'], row['title'])
                now = m.utc_now()
                args = m.parse_args(['--timezone','Asia/Singapore','--cache-dir',directory])
                extracted = (row['title'],row['summary'],row['key_facts'],now,now.isoformat(),'synthetic','detail')
                with patch.object(m,'collect_candidates_from_sources',return_value=[c]), patch.object(m,'select_detail_candidates',return_value=[c]), patch.object(m,'fetch_detail_page_texts',return_value=[row['html']]), patch.object(m,'extract_article',return_value=extracted), patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
                    result = m.run(args)
                facts = [f['text'] for e in result['events']+result['deferred_events'] for f in e['fact_sources'] if any(o['url']==row['url'] for o in f['origins'])]
                reviews = [(q,u['text']) for q in result['final_brief_queue'] if row['url'] in q['source_urls'] for u in q.get('unprocessed_evidence',[])]
                for text in row['exclude_standalone']:
                    self.assertNotIn(text, facts)
                    self.assertFalse(any(q['required'] and t==text for q,t in reviews))
                for text in row['retain']:
                    self.assertTrue(any(text in t for t in facts) or any(text in t for _,t in reviews), text)
                evidence = m.capture_article_evidence(row['source'],row['url'],row['html'],row['title'],row['summary'])
                remaining, excluded = source_evidence_remainder(evidence, [])
                for text in row['exclude_standalone']:
                    unit = next(u for u in evidence.units if u.text==text)
                    self.assertIn((unit.unit_id,0,len(text),'Publisher programme credits or subscription navigation'), excluded)
                    self.assertFalse(any(span[0]==unit.unit_id for span in remaining))
        people = self.fixture['podcast_editorial_lists'][1]
        ev = m.capture_article_evidence(people['source'],people['url'],people['html'].replace('Newly appointed members','Hosts'),people['title'],people['summary'])
        self.assertFalse(m.editorial_list_unit_ids(ev))

    def podcast_live_articles(self, fixture_key="podcast_live_relations"):
        import hashlib
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        m = self.m
        articles = {}
        for row in self.fixture[fixture_key]['sources']:
            aid = hashlib.sha256(row['url'].encode()).hexdigest()[:24]
            units = tuple(EvidenceUnit(hashlib.sha256((aid+str(n)).encode()).hexdigest()[:24], u['kind'], u['text'], 'synthetic', u['ordinal']) for n,u in enumerate(row['units']))
            ev = ArticleEvidence(aid,row['source'],row['url'],row['title'],row['summary'],'news',units,confidence='detail')
            articles[row['id']] = m.Article(source=row['source'],url=row['url'],title=row['title'],summary=row['summary'],key_facts=row['key_facts'],category='',published_utc=datetime(2032,10,24,tzinfo=timezone.utc),published_raw='2032-10-24',published_source='synthetic',confidence='detail',tokens=m.article_tokens(row['title'],' '.join([row['summary'][:1200],*row['key_facts'][:5]])),event_kind=m.detect_event_kind(row['title'],row['summary'],row['key_facts']),regions=m.extract_regions(' '.join([row['title'],row['summary'],*row['key_facts'][:5]])),evidence=ev,projection_source_title=row['title'])
        return articles

    def test_current_executive_interview_detail_admission_without_name_list(self):
        m = self.m
        raw = self.fixture['podcast_live_relations']['admission']
        # A role belongs to the person in this interview, rather than a known-name dictionary.
        source = m.Source(name='FixtureWire',default_tz='UTC',feeds=[],pages=[],domains=('example.invalid',))
        for name in ('Alex Mercer', 'Jordan Vale'):
            row = {k:v.replace('Alex Mercer',name).replace('alex mercer',name.lower()) if isinstance(v,str) else v for k,v in raw.items()}
            self.assertTrue(m.is_relevant_candidate(m.Candidate(**row),source))
        other = dict(raw)
        other['title'] = 'Alex Mercer just gave the best comparison of Lumen goggles with Vision Pro'
        other['summary'] = raw['summary'].replace('Apple’s new CEO','Lumen’s new CEO').replace('best defense yet for Apple Vision Pro','comparison between Lumen goggles and Apple Vision Pro')
        self.assertFalse(m.is_relevant_candidate(m.Candidate(**other),source))

    def test_current_report_action_not_background_product_or_configuration(self):
        m = self.m
        articles = self.podcast_live_articles()
        keys = ('cancel_report','cancel_reprint','charger_report','watch_storage','watch_setting','mac_reviews','mac_availability','teardown_camera','teardown_full')
        profiles = {k:m.article_reconciliation_profile(articles[k]) for k in keys}
        for left,right,wanted in (('cancel_report','cancel_reprint','match'),('cancel_report','charger_report','not-match'),('watch_storage','watch_setting','not-match'),('mac_reviews','mac_availability','not-match'),('teardown_camera','teardown_full','match')):
            with self.subTest(left=left,right=right):
                actual = m.profile_pair_decision(profiles[left],profiles[right])
                if wanted=='match': self.assertEqual(actual,'match')
                else: self.assertNotEqual(actual,'match')
        different = replace(articles['teardown_full'],title=articles['teardown_full'].title.replace('iPhone 22','iPhone 20'),summary=articles['teardown_full'].summary.replace('iPhone 22','iPhone 20'),key_facts=[x.replace('iPhone 22','iPhone 20') for x in articles['teardown_full'].key_facts],evidence=None,bound_claim=None)
        self.assertNotEqual(m.profile_pair_decision(profiles['teardown_camera'],m.article_reconciliation_profile(different)),'match')

    def test_platform_version_and_compatibility_do_not_transfer_action_ownership(self):
        articles = self.podcast_live_articles()
        for key,wanted in (('charger_news','weak'),('developer_en','weak'),('developer_zh','weak'),('builtin_switcher','strong')):
            with self.subTest(source=key):
                profile=self.m.article_reconciliation_profile(articles[key])
                self.assertEqual(self.m.resolve_reconciliation_outcome(profile,observed_tier='',observed_reason='',observed_category='')[0],wanted)

    def test_inline_editorial_markup_keeps_body_not_ad_or_related_directory(self):
        m=self.m
        for row in self.fixture['podcast_live_relations']['html_controls']:
            with self.subTest(row=row['id']):
                ev=m.capture_article_evidence('FixtureWire','https://example.invalid/'+row['id'],row['html'],row['title'])
                text=' '.join(u.text for u in ev.units)
                self.assertNotIn(row['excluded_token'],text)
                self.assertIn(row['kept_token'],text)
                self.assertNotIn(row['excluded_token'],' '.join(m.extract_key_facts(row['html'],row['title'],'FixtureWire')))
        html='<article><p>Apple explains how the app requests an extended trial from its server.</p><p><strong>Related Stories</strong> is the name of a new reading feature.</p><ul><li>iPhone 22 supports it in Canada.</li></ul></article>'
        ev=m.capture_article_evidence('FixtureWire','https://example.invalid/body',html,'Apple adds a reading feature')
        for value in ('extended trial','Related Stories','iPhone 22'):
            self.assertIn(value,' '.join(u.text for u in ev.units))

    def test_earlier_rollout_language_cannot_bind_current_release(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        from apple_news_core.event_identity import bind_article_claims
        from apple_news_core.article_projector import project_article_evidence
        for row in self.fixture['podcast_rollout_language']['cases']:
            units=tuple(EvidenceUnit(str(n),u['kind'],u['text'],'synthetic',u['ordinal']) for n,u in enumerate(row['units']))
            ev=ArticleEvidence(row['id'],row['source'],row['url'],row['title'],row['summary'],'news',units,confidence='detail')
            claims=bind_article_claims(ev)
            with self.subTest(row=row['id']):
                self.assertFalse(any(q[0]=='english' for claim in claims for q in claim.qualifiers))
                if row['id']=='beta2_report':
                    self.assertFalse(any(c.object=='languages' for c in claims))
        a=self.podcast_live_articles()['apps_removed']
        self.assertFalse(any(p.claim.object=='watch-audio' for p in project_article_evidence(a.evidence)[0]))

    def test_editorial_purpose_and_service_compatibility_do_not_promote_background(self):
        from apple_news_core.event_identity import build_event_identity
        articles=self.podcast_live_articles()
        for key in ('car_audio','music_tutorial','accessory_guide'):
            with self.subTest(source=key):
                p=self.m.article_reconciliation_profile(articles[key])
                self.assertEqual(self.m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'weak')
        a=articles['battery_zh']
        self.assertNotEqual(build_event_identity(a.title,a.summary).content_form,'user_anecdote')

    def test_current_beta_wave_availability_and_shipping_control_relations(self):
        m=self.m; articles=self.podcast_live_articles()
        for left,right in (('beta_wearable','beta_desktop'),('battery_en','battery_zh')):
            with self.subTest(left=left):
                lp=m.article_reconciliation_profile(articles[left]);rp=m.article_reconciliation_profile(articles[right])
                self.assertEqual(m.profile_pair_decision(lp,rp),'match')
                self.assertEqual(m.resolve_reconciliation_outcome(rp,observed_tier='',observed_reason='',observed_category='')[0],'strong')
        a=articles['beta_desktop']
        other=replace(a,title=a.title.replace('28.3','28.4'),summary=a.summary.replace('28.3','28.4'),key_facts=[x.replace('28.3','28.4') for x in a.key_facts])
        self.assertNotEqual(m.profile_pair_decision(m.article_reconciliation_profile(a),m.article_reconciliation_profile(other)),'match')

    def test_measurement_comparison_uses_device_names_not_surface_verb(self):
        a=self.podcast_live_articles()['mac_measurement'];m=self.m
        self.assertFalse(m.is_non_apple_device_comparison_story(a.title,a.title+' '+a.summary))
        p=m.article_reconciliation_profile(a)
        self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'strong')
        for title in ('Surface Pro is thinner than an iPad','Microsoft Surface challenges the iPad'):
            self.assertTrue(m.is_non_apple_device_comparison_story(title,title+' The device is compared with Apple hardware.'))

    def test_current_builtin_feature_legal_request_and_signing_have_source_support(self):
        articles=self.podcast_live_articles();m=self.m
        for key in ('builtin_steps','legal_request','signing'):
            with self.subTest(source=key):
                p=m.article_reconciliation_profile(articles[key])
                self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'strong')

    def test_code_disclosure_and_reproduced_failure_keep_concrete_objects(self):
        a=self.podcast_live_articles();m=self.m
        for left,right in (('code_feature_en','code_feature_zh'),('reboot_report','reboot_reprint'),('face_report','face_reprint')):
            with self.subTest(left=left):
                lp=m.article_reconciliation_profile(a[left]);rp=m.article_reconciliation_profile(a[right])
                self.assertEqual(m.profile_pair_decision(lp,rp),'match')
                self.assertEqual(m.resolve_reconciliation_outcome(lp,observed_tier='',observed_reason='',observed_category='')[0],'strong')
        p=m.article_reconciliation_profile(a['code_feature_en'])
        renamed=replace(a['code_feature_en'],summary=a['code_feature_en'].summary.replace('SecureHold','WakeAssist'),key_facts=[s.replace('SecureHold','WakeAssist') for s in a['code_feature_en'].key_facts])
        self.assertNotEqual(m.profile_pair_decision(p,m.article_reconciliation_profile(renamed)),'match')

    def test_unselected_source_disclosures_settings_and_responsibility_have_exact_origins(self):
        articles=self.podcast_live_articles();m=self.m
        for key,targets in self.fixture['podcast_live_relations']['fact_targets'].items():
            a=articles[key];p=m.article_reconciliation_profile(a)
            plan=m.resolve_event_fact_plan([m.prepare_source_fact_view(a)],relevance_tier=p.relevance_tier,base_limit=10,official_limit=16)
            for target in targets:
                with self.subTest(source=key,target=target[:35]):
                    def located(plan):
                        return [f for f in (*plan.facts,*plan.unprocessed) if target in f.text and any(o[1]==a.url and any(u.unit_id==o[3] and u.text[o[4]:o[5]]==f.text for u in a.evidence.units) for o in f.origins)]
                    # In this single-source plan, an exact displayed summary
                    # sentence is already consumed; do not demand duplicate review.
                    self.assertTrue(located(plan) or (target in plan.summary and target in m.prepare_source_fact_view(a).summary_units))
                    selected=replace(a,key_facts=[target,*a.key_facts])
                    positive=m.resolve_event_fact_plan([m.prepare_source_fact_view(selected)],relevance_tier=p.relevance_tier,base_limit=10,official_limit=16)
                    self.assertTrue(located(positive))
                    if any(target in f.text for f in positive.facts):
                        self.assertFalse(any(f.text==target for f in positive.unprocessed))

    def test_current_home_device_name_and_description_preserve_report_window(self):
        a=self.podcast_live_articles();m=self.m
        left=m.article_reconciliation_profile(a['home_report']);right=m.article_reconciliation_profile(a['home_news'])
        self.assertEqual(m.profile_pair_decision(left,right),'match')
        self.assertEqual(m.resolve_reconciliation_outcome(right,observed_tier='',observed_reason='',observed_category='')[0],'strong')
        changed=replace(a['home_news'],summary=a['home_news'].summary.replace('October','September'),key_facts=[x.replace('October','September') for x in a['home_news'].key_facts])
        self.assertNotEqual(m.profile_pair_decision(left,m.article_reconciliation_profile(changed)),'match')

    def test_source_measurements_bind_storage_role_and_wait_time_report(self):
        a=self.podcast_live_articles();m=self.m
        for left,right in (('storage_en','storage_zh'),('demand_report','demand_reprint')):
            with self.subTest(left=left):
                lp=m.article_reconciliation_profile(a[left]);rp=m.article_reconciliation_profile(a[right])
                self.assertEqual(m.profile_pair_decision(lp,rp),'match')
                self.assertEqual(m.resolve_reconciliation_outcome(lp,observed_tier='',observed_reason='',observed_category='')[0],'strong')
        x=a['storage_en'];changed=replace(x,title=x.title.replace('22','20'),summary=x.summary.replace('iPhone 22','iPhone 20'),key_facts=[f.replace('iPhone 22','iPhone 20') for f in x.key_facts])
        self.assertNotEqual(m.profile_pair_decision(m.article_reconciliation_profile(x),m.article_reconciliation_profile(changed)),'match')

    def test_third_party_policy_clarification_needs_company_and_vehicle_scope(self):
        a=self.podcast_live_articles();m=self.m
        lp=m.article_reconciliation_profile(a['car_clarification']);rp=m.article_reconciliation_profile(a['car_clarification_zh'])
        self.assertEqual(m.profile_pair_decision(lp,rp),'match')
        for p in (lp,rp):self.assertEqual(m.resolve_reconciliation_outcome(p,observed_tier='',observed_reason='',observed_category='')[0],'weak')
        original=a['car_clarification'];other=replace(original,title=original.title.replace('Roadway Motors','Other Motors'),summary=original.summary.replace('Roadway Motors','Other Motors'),key_facts=[s.replace('Roadway Motors','Other Motors') for s in original.key_facts])
        self.assertNotEqual(m.profile_pair_decision(lp,m.article_reconciliation_profile(other)),'match')

    def test_podcast_live_relations_keep_final_source_outcomes_and_local_facts(self):
        import re, socket, tempfile
        from unittest.mock import patch
        m=self.m; articles=self.podcast_live_articles(); fixture=self.fixture['podcast_live_relations']
        by_url={a.url:a for a in articles.values()}
        candidates=[m.Candidate(a.source,a.url,a.title,a.summary) for a in articles.values()]
        now=m.utc_now()
        def extracted(c,*args):
            a=by_url[c.url];return a.title,a.summary,a.key_facts,now,now.isoformat(),'detail','detail'
        with tempfile.TemporaryDirectory() as directory:
            args=m.parse_args(['--timezone','Asia/Singapore','--cache-dir',directory])
            with patch.object(m,'build_sources',return_value=[m.Source(a.source,'UTC') for a in articles.values()]),patch.object(m,'collect_candidates_from_sources',return_value=candidates),patch.object(m,'select_detail_candidates',return_value=candidates),patch.object(m,'fetch_detail_page_texts',return_value=['<article></article>']*len(candidates)),patch.object(m,'capture_article_evidence',side_effect=lambda source,url,*args:by_url[url].evidence),patch.object(m,'extract_article',side_effect=extracted),patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
                result=m.run(args)
        events=result['events']+result['deferred_events'];scaffold=m.render_brief_scaffold(result)
        norm=lambda t:re.sub(r'\s+','',t).casefold()
        for key,tier in fixture['fields'].items():
            with self.subTest(source=key,tier=tier):
                sources=[s for e in events for s in e['sources'] if s['url']==articles[key].url]
                self.assertTrue(sources)
                self.assertTrue(all(s['relevance_tier']==tier for s in sources),sources)
        for check in fixture['pairs']:
            left=articles[check['left']].url;right=articles[check['right']].url
            together=any({left,right}<={s['url'] for s in e['sources']} for e in events)
            with self.subTest(pair=(check['left'],check['right'])):
                self.assertEqual(together,check['expected']=='match')
        for key,targets in fixture['fact_targets'].items():
            a=articles[key]
            for target in targets:
                with self.subTest(fact_source=key,target=target[:30]):
                    ids={u.unit_id for u in a.evidence.units if norm(target) in norm(u.text)}
                    reviews=[(q,u) for q in result['final_brief_queue'] if a.url in q.get('source_urls',[]) for u in q.get('unprocessed_evidence',[]) if u.get('unit_id') in ids and norm(target) in norm(u['text'])]
                    facts=[f for e in events for f in e.get('fact_sources',[]) if norm(target) in norm(f['text']) and any(o['url']==a.url and o.get('unit_id') in ids for o in f['origins'])]
                    summaries=[e for e in events if norm(target) in norm(e['summary']) and any(s['url']==a.url for s in e['sources']) and target in m.prepare_source_fact_view(a).summary_units]
                    self.assertTrue(reviews or facts or summaries)
                    if not summaries:
                        self.assertIn(norm(target),norm(scaffold))
                    else:
                        # Final source-local summary is an accepted disposition;
                        # the scaffold does not promise to repeat summaries.
                        self.assertTrue(ids)
                        self.assertTrue(all(any(s['url']==a.url and s.get('evidence_id')==a.evidence.article_id for s in e['sources']) for e in summaries))
                    for q,u in reviews:
                        unit=next(v for v in result['source_evidence'][q['evidence_id']]['units'] if v['unit_id']==u['unit_id'])
                        self.assertEqual(unit['text'][u['start']:u['end']],u['text'])
                    for fact in facts:
                        for origin in fact['origins']:
                            if origin['url']==a.url and origin.get('unit_id') in ids:
                                unit=next(v for v in result['source_evidence'][origin['article_id']]['units'] if v['unit_id']==origin['unit_id'])
                                self.assertEqual(unit['text'][origin['start']:origin['end']],fact['text'])

    def test_storage_measurement_roles_and_transport_limit_are_not_interchangeable(self):
        m=self.m; a=self.podcast_live_articles()
        def changed(source, swaps):
            def transform(text):
                for old,new in swaps:text=text.replace(old,new)
                return text
            return replace(source,title=transform(source.title),summary=transform(source.summary),key_facts=[transform(f) for f in source.key_facts],evidence=None,url=source.url+'-changed')
        storage=a['storage_en'];base=m.article_reconciliation_profile(storage)
        for swaps in ((('79.4','TEMP'),('25.6','79.4'),('TEMP','25.6')), (('1TB','2TB'),), (('Under sustained testing, it reached a speed of','During a brief peak test, it reached a speed of'),)):
            with self.subTest(storage=swaps):
                other=m.article_reconciliation_profile(changed(storage,swaps))
                self.assertNotEqual(m.profile_pair_decision(base,other),'match')
        battery=a['battery_en'];bp=m.article_reconciliation_profile(battery)
        other=m.article_reconciliation_profile(changed(battery,(('22Wh','24Wh'),)))
        self.assertNotEqual(m.profile_pair_decision(bp,other),'match')
        rated=replace(battery,title='iPhone 22 Pro Max battery capacity measured',summary='Apple lists the iPhone 22 Pro Max battery at 22Wh. The phone is now shipping.',key_facts=['The rated battery capacity is 22Wh.'],evidence=None)
        self.assertFalse(any('battery-transport-control' in k for k in m.article_reconciliation_profile(rated).event_keys))

    def test_sponsor_meta_prefix_uses_retained_body_boundary_without_losing_news(self):
        m=self.m;row=self.fixture['podcast_live_repair']['html_control']
        c=m.Candidate('FixtureWire','https://example.invalid/meta',row['title'])
        title,summary,facts,*_=m.extract_article(c,m.Source('FixtureWire','UTC'),row['html'],{})
        self.assertNotIn('FleetShield',summary)
        self.assertIn(row['kept_token'],summary)
        evidence=m.capture_article_evidence(c.source,c.url,row['html'],row['title'])
        self.assertIn('FleetShield',evidence.raw_lead)
        news='<meta property="og:description" content="Apple explains why FleetShield now supports a new iPhone feature."><article><p>Apple explains why FleetShield now supports a new iPhone feature.</p></article>'
        self.assertIn('FleetShield',m.extract_summary(news,''))

    def test_natural_multisource_relations_keep_all_edges_and_source_outcomes(self):
        m=self.m
        for fixture_key in ('podcast_live_repair','podcast_live_lexical'):
            fixture=self.fixture[fixture_key];articles=self.podcast_live_articles(fixture_key)
            profiles={k:m.article_reconciliation_profile(a) for k,a in articles.items()}
            for row in fixture['pairs']:
                with self.subTest(scope=fixture_key,pair=(row['left'],row['right'])):
                    self.assertEqual(m.profile_pair_decision(profiles[row['left']],profiles[row['right']]),row['expected'])
            for key,wanted in fixture.get('fields',{}).items():
                with self.subTest(source=key):
                    self.assertEqual(m.resolve_reconciliation_outcome(profiles[key],observed_tier='',observed_reason='',observed_category='')[0],wanted)
            for ids in fixture['groups']:
                with self.subTest(group=ids):
                    events=m.cluster_articles([articles[k] for k in ids])
                    self.assertEqual(len(events),1)
                    self.assertEqual({a.url for e in events for a in e.articles},{articles[k].url for k in ids})

    def test_accessory_and_developer_targets_do_not_borrow_compatible_device_identity(self):
        m=self.m;a=self.podcast_live_articles('podcast_live_repair')
        def changed(article, old, new):
            return replace(article,title=article.title.replace(old,new),summary=article.summary.replace(old,new),key_facts=[f.replace(old,new) for f in article.key_facts],evidence=None,url=article.url+'-different')
        base=a['charger_zh'];p=m.article_reconciliation_profile(base)
        self.assertTrue(any('co-branded-accessory-retail-offer' in k for k in p.event_keys))
        for old,new in (('澜电','清电'),('星港','月谷')):
            with self.subTest(accessory=old):
                other=m.article_reconciliation_profile(changed(base,old,new))
                self.assertNotEqual(m.profile_pair_decision(p,other),'match')
        b=self.podcast_live_articles('podcast_live_lexical')['builder_en'];p=m.article_reconciliation_profile(b)
        for old,new in (('Codary','Modary'),('iPhone Duo','iPhone Mini')):
            with self.subTest(developer=old):
                self.assertNotEqual(m.profile_pair_decision(p,m.article_reconciliation_profile(changed(b,old,new))),'match')
        transport=a['transport_natural'];p=m.article_reconciliation_profile(transport)
        other=changed(transport,'22','24')
        self.assertNotEqual(m.profile_pair_decision(p,m.article_reconciliation_profile(other)),'match')

    def test_historical_beta_list_and_os_causal_clause_do_not_bind_current_siri_rollout(self):
        m=self.m;a=self.podcast_live_articles('podcast_live_repair')
        for key in self.fixture['podcast_live_repair']['language']:
            with self.subTest(source=key):
                children,remaining,excluded=m.project_article_evidence(a[key].evidence)
                self.assertFalse(any('language' in str(c.claim.object) for c in children))
                self.assertTrue(remaining)
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform
        self.assertFalse(is_third_party_app_action_on_apple_platform(a['builtin_removed'].title,a['builtin_removed'].summary))
        self.assertFalse(m.is_third_party_app_or_service_status_story(a['diagnostics_mixed'].title,' '.join([a['diagnostics_mixed'].title,a['diagnostics_mixed'].summary,*a['diagnostics_mixed'].key_facts])))
        self.assertTrue(m.is_third_party_app_or_service_status_story('Example app for iPhone updated','The Example app for iPhone was updated today with a new sharing tool.'))

    def test_natural_repair_production_run_keeps_final_source_strength_and_groups(self):
        import socket,tempfile
        from unittest.mock import patch
        m=self.m;articles=self.podcast_live_articles('podcast_live_repair')
        articles.update(self.podcast_live_articles('podcast_live_lexical'))
        by_url={a.url:a for a in articles.values()};candidates=[m.Candidate(a.source,a.url,a.title,a.summary) for a in by_url.values()];now=m.utc_now()
        def extracted(c,*args):
            a=by_url[c.url];return a.title,a.summary,a.key_facts,now,now.isoformat(),'detail','detail'
        with tempfile.TemporaryDirectory() as directory:
            args=m.parse_args(['--timezone','Asia/Singapore','--cache-dir',directory])
            with patch.object(m,'build_sources',return_value=[m.Source(a.source,'UTC') for a in by_url.values()]),patch.object(m,'collect_candidates_from_sources',return_value=candidates),patch.object(m,'select_detail_candidates',return_value=candidates),patch.object(m,'fetch_detail_page_texts',return_value=['<article></article>']*len(candidates)),patch.object(m,'capture_article_evidence',side_effect=lambda source,url,*args:by_url[url].evidence),patch.object(m,'extract_article',side_effect=extracted),patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
                result=m.run(args)
        events=result['events']+result['deferred_events']
        for key,tier in self.fixture['podcast_live_repair']['fields'].items():
            with self.subTest(source=key):
                sources=[s for e in events for s in e['sources'] if s['url']==articles[key].url]
                self.assertTrue(sources)
                self.assertTrue(all(s['relevance_tier']==tier for s in sources),sources)
        # IDs shared by both fixtures use the lexical-preserving complete rows.
        for fixture_key in ('podcast_live_repair','podcast_live_lexical'):
            for ids in self.fixture[fixture_key]['groups']:
                with self.subTest(group=ids):
                    urls={articles[k].url for k in ids}
                    self.assertTrue(any(urls<={s['url'] for s in e['sources']} for e in events))

    def test_sponsor_only_truncated_meta_falls_back_to_news_without_changing_raw_evidence(self):
        m=self.m
        for row in self.fixture['sponsor_meta_excerpt']['cases']:
            with self.subTest(case=row['id']):
                c=m.Candidate('FixtureWire','https://example.invalid/'+row['id'],row['title'])
                title,summary,facts,*_=m.extract_article(c,m.Source('FixtureWire','UTC'),row['html'],{})
                self.assertEqual(row['noise'] in summary,row['expect_primary_noise'])
                self.assertIn(row['keep'],summary)
                evidence=m.capture_article_evidence(c.source,c.url,row['html'],row['title'])
                self.assertIn(row['noise'],evidence.raw_lead)
                self.assertTrue(any(row['keep'] in u.text for u in evidence.units))
        ordinary='<meta property="og:description" content="A guide sponsored by an industry group explains new iPhone support."><article><p>A guide sponsored by an industry group explains new iPhone support.</p></article>'
        self.assertIn('sponsored by an industry group',m.extract_summary(ordinary,''))
