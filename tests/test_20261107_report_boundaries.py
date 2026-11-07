import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class ReportBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261107_report_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,11,7,tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    def test_first_party_app_release_groups_localized_name_and_visual_changes(self):
        events, data = self.cluster_sources(*(k for k in self.rows if k.startswith(('485d','8e74','d4ac'))))
        self.assertEqual(len(events),1)
        self.assertEqual(data[0]['category'],'software_systems')
        self.assertEqual(len(data[0]['sources']),3)

    def test_vehicle_update_adds_platform_interoperability(self):
        sid=next(k for k in self.rows if k.startswith('018d'))
        events,data=self.cluster_sources(sid)
        self.assertEqual(len(events),1)
        self.assertEqual(data[0]['relevance_tier'],'ecosystem')
        self.assertEqual(data[0]['category'],'software_systems')

    def test_retail_gift_card_is_not_a_product_supply_report(self):
        sid=next(k for k in self.rows if k.startswith('7aa0'))
        events,data=self.cluster_sources(sid)
        self.assertEqual(data[0]['relevance_tier'],'weak')

    def test_return_policy_groups_regional_terms_in_software(self):
        events,data=self.cluster_sources(*(k for k in self.rows if k.startswith(('68e5','9495','fbc'))))
        self.assertEqual(len(events),1)
        self.assertEqual(data[0]['category'],'software_systems')
        self.assertEqual(len(data[0]['sources']),3)

    def test_legal_background_cannot_bridge_different_proceedings(self):
        events,data=self.cluster_sources(*(k for k in self.rows if k.startswith(('4431','8df6'))))
        self.assertEqual(len(events),2)
        self.assertEqual({e['category'] for e in data},{'software_systems'})
        self.assertEqual({e['relevance_tier'] for e in data},{'strong'})

    def test_platform_app_inventory_is_one_software_statement(self):
        ids=[k for k in self.rows if k.startswith(('e5e2','9e47','8d7b','cfba','a1fb','3c31','67e2'))]
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(data[0]['category'],'software_systems')
        self.assertEqual(data[0]['relevance_tier'],'strong')
        self.assertEqual(len(data[0]['sources']),len(ids))

    def test_official_preference_control_groups_software_behavior(self):
        ids=[k for k,v in self.rows.items() if any(x in v['evidence']['title'].lower() for x in ('glowing','发光'))]
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(data[0]['category'],'software_systems')
        self.assertEqual(data[0]['relevance_tier'],'strong')

    def test_purchase_recommendation_and_history_do_not_borrow_background_launch(self):
        for sid in (k for k in self.rows if k.startswith(('2c13','2c12'))):
            with self.subTest(source=sid):
                title,summary,facts=self.rows[sid]['recorded_extraction']
                article=article_for(self.m,title,summary,facts=facts)
                self.assertEqual(self.m.article_reconciliation_profile(article).relevance_tier,'weak')

    def test_accessory_firmware_does_not_become_an_iphone_update(self):
        sid=next(k for k in self.rows if k.startswith('d114'))
        title,summary,facts=self.rows[sid]['recorded_extraction']
        article=article_for(self.m,title,summary,facts=facts)
        self.assertEqual(self.m.article_reconciliation_profile(article).relevance_tier,'weak')

    def test_corporate_bond_prospectus_is_a_direct_company_action(self):
        events,data=self.cluster_sources(next(k for k in self.rows if k.startswith('80be')))
        self.assertEqual(data[0]['relevance_tier'],'strong')
        self.assertEqual(data[0]['category'],'hardware_products')

    def test_component_integration_is_not_device_cancellation(self):
        ids=[k for k in self.rows if k.startswith(('2598','a67e','225c','a3bf','f210','fc7e'))]
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(len(data[0]['sources']),6)
        self.assertEqual(data[0]['relevance_tier'],'strong')

    def test_keyboard_dictionary_research_is_one_software_report(self):
        ids=[k for k in self.rows if k.startswith(('f723','42ae'))]
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(data[0]['category'],'software_systems')
        self.assertEqual(data[0]['relevance_tier'],'strong')

    def test_joint_component_development_and_measured_device_workload_are_direct(self):
        for sid in (k for k in self.rows if k.startswith(('3104','0cbaa'))):
            with self.subTest(source=sid):
                events,data=self.cluster_sources(sid)
                self.assertEqual(data[0]['relevance_tier'],'strong')
                self.assertEqual(data[0]['category'],'hardware_products')

    def test_ad_assets_merge_without_bridging_two_different_ads(self):
        ids=[k for k in self.rows if k.startswith(('31b0','0c378','ef353'))]
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),2)
        self.assertEqual(sorted(len(e['sources']) for e in data),[1,3])
        self.assertEqual({e['relevance_tier'] for e in data},{'strong'})

    def test_first_delivery_batch_does_not_turn_into_old_launch_recap(self):
        ids=[k for k in self.rows if k.startswith(('35de','ef07','75c5'))]
        events,data=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(len(data[0]['sources']),3)
        self.assertEqual(data[0]['relevance_tier'],'strong')

    def test_preference_and_retired_name_commentary_remain_supporting(self):
        for sid in (k for k in self.rows if k.startswith(('f19e','4d429'))):
            title,summary,facts=self.rows[sid]['recorded_extraction']
            article=article_for(self.m,title,summary,facts=facts)
            self.assertEqual(self.m.article_reconciliation_profile(article).relevance_tier,'weak')

    def assert_distinct_reports(self, *cases):
        articles=[article_for(self.m,title,lead) for title,lead in cases]
        for ordered in (articles,list(reversed(articles))):
            self.assertEqual(len(self.m.cluster_articles(ordered)),len(cases))

    def test_app_release_keeps_client_platform_and_stage(self):
        self.assert_distinct_reports(
            ('Apple Music app updated to version 4.1 for Android', 'Apple released version 4.1 of its Apple Music app for Android.'),
            ('Apple Music app updated to version 4.1 for iPhone', 'Apple released version 4.1 of its Apple Music app for iPhone.'))
        self.assert_distinct_reports(
            ('Apple Music Classical app updated to version 4.2 beta', 'Apple released version 4.2 of its Apple Music Classical app for iPhone.'),
            ('Apple Music Classical app updated to version 4.2', 'Apple released version 4.2 of its Apple Music Classical app for iPhone.'),
            ('Apple Music Classical app updated to version 4.3', 'Apple released version 4.3 of its Apple Music Classical app for iPhone.'))

    def test_component_integration_plan_is_not_completed_integration(self):
        self.assert_distinct_reports(
            ('iPhone Action button and Camera Control integrated', 'Apple has merged the Action button and Camera Control in the iPhone released today.'),
            ('iPhone Action button and Camera Control integration planned', 'Apple plans to merge the Action button and Camera Control in a future iPhone.'))
        self.assert_distinct_reports(
            ('iPhone Action button and Camera Control integrated', 'Apple merged the Action button and Camera Control in the iPhone released today.'),
            ('iPhone Action button and Camera Control integration planned', 'Apple plans to merge the Action button and Camera Control in a future iPhone.'))

    def test_app_stage_can_be_stated_only_in_the_source_body(self):
        self.assert_distinct_reports(
            ('Apple Music Classical app updated to version 4.2', 'Apple released version 4.2 beta of its Apple Music Classical app for developers.'),
            ('Apple Music Classical app updated to version 4.2', 'Apple released version 4.2 of its Apple Music Classical app for iPhone.'))

    def test_official_gift_card_offer_is_not_a_reseller_sale(self):
        a=article_for(self.m,'Get a free $150 gift card with a MacBook Pro at Apple Store',
            'Apple Store is offering a free $150 gift card with every MacBook Pro purchased during its official holiday promotion.')
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')

    def test_inventory_confirmation_does_not_merge_with_denial(self):
        self.assert_distinct_reports(
            ('Apple says 100,000 apps are optimized for iPhone Duo', 'Apple says 100,000 apps are optimized for iPhone Duo.'),
            ('Apple denies 100,000 apps are optimized for iPhone Duo', 'Apple says reports that 100,000 apps are optimized for iPhone Duo are not accurate.'))

    def test_video_capture_preserves_ids_and_labels_without_network(self):
        from apple_news_core.article_processing import capture_article_evidence
        e=capture_article_evidence('Example','https://example.com/news',
            '<article><p>Apple shared two new ads.</p>'
            '<iframe data-src="https://www.youtube.com/embed/AbCdEf01234"></iframe>'
            '<p>The second is called <a href="https://youtu.be/XyZaBc56789">A <em>new</em> day</a>.</p>'
            '<a href="https://youtube.com.evil.invalid/watch?v=BadBad12345">Other</a></article>', 'Apple ads')
        self.assertEqual({(r.object_id,r.label) for r in e.embedded_references if r.platform=='youtube'},
            {('AbCdEf01234',''),('XyZaBc56789','A new day')})

    def test_background_or_denied_ad_cannot_claim_embedded_asset(self):
        from apple_news_core.models import ArticleEvidence,EmbeddedReference,EvidenceUnit
        from apple_news_core.event_identity import bind_advertisement_reports
        ref=EmbeddedReference('youtube','AbCdEf01234','https://youtu.be/AbCdEf01234','body',1,'<iframe>')
        for sentence in ('Apple shared a new ad last year.', 'Apple has not shared a new ad.',
                         'A fan shared a new Apple ad.', 'Apple plans to share a new ad.'):
            e=ArticleEvidence('id','Example','https://example.com/1','Apple ad discussion',sentence,'news',
                (EvidenceUnit('u','p',sentence,'body',0),),embedded_references=(ref,))
            self.assertIsNone(bind_advertisement_reports(e),sentence)

    def test_delivery_batch_keeps_observation_date(self):
        from apple_news_core.event_matcher import identity_pair_decision
        sid=next(k for k in self.rows if k.startswith('35de'))
        claim=self.source_articles(sid)[0].bound_claim
        later=replace(claim,qualifiers=tuple((a,b,'07' if b=='observation-day' else c,d,e,f)
            for a,b,c,d,e,f in claim.qualifiers))
        self.assertEqual(identity_pair_decision(claim,later),'conflict')

    def test_old_embedded_video_does_not_identify_a_new_ad(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_advertisement_reports
        e=capture_article_evidence('Example','https://example.com/ad',
            '<article><p>Apple shared a new Apple Card ad today.</p>'
            '<p>For comparison, here is last year\'s campaign:</p>'
            '<iframe src="https://www.youtube.com/embed/AbCdEf01234"></iframe></article>',
            'Apple shares a new Apple Card ad')
        self.assertIsNone(bind_advertisement_reports(e))

    def test_delivery_batch_keeps_generation_and_body_polarity(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_product_delivery_batch
        from apple_news_core.event_matcher import identity_pair_decision
        claims=[]
        for chip in ('M5','M6'):
            title=f'{chip} MacBook Pro and {chip} iMac Available From Today'
            e=capture_article_evidence('Example','https://example.com/'+chip,
                f'<article><p>From today, Apple\'s {chip} MacBook Pro and {chip} iMac are available to buy.</p></article>',title)
            e=replace(e,published_utc='2026-11-07T02:00:00+00:00')
            claims.append(bind_product_delivery_batch(e))
            denied=replace(e,units=(replace(e.units[0],text=f"From today, Apple's {chip} MacBook Pro and {chip} iMac are no longer available after a recall."),))
            self.assertIsNone(bind_product_delivery_batch(denied))
        self.assertTrue(all(claims))
        self.assertEqual(identity_pair_decision(*claims),'conflict')

    def test_research_samples_without_a_shared_artifact_remain_distinct(self):
        self.assert_distinct_reports(*[
            (f'{name} reports Apple keyboard blocked phrases list',
             f'Researcher {name} found words and phrases blocked from autocomplete in iOS 27. {name} independently collected a sample.')
            for name in ('Alice','Bob')])

    def test_buying_guide_measurement_remains_a_supporting_fact(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_device_measurement
        e=capture_article_evidence('Example','https://example.com/guide',
            '<article><p>This is a buying guide to useful iPhone apps.</p>'
            '<p>TinyModel 在 iPhone 18 Pro 上实测，平均解码速度为 350token/s。</p></article>',
            'Best iPhone 18 Pro apps to buy: TinyModel reaches 350 token/s')
        self.assertIsNone(bind_device_measurement(e))

    def test_background_video_does_not_remove_current_social_post_identity(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_reconciler import _embedded_current_preview_subject
        title='Apple CEO shares a new preview video'
        lead='Apple CEO Casey Stone shared a new preview video today.'
        markup='<article><p>'+lead+'</p><blockquote class="twitter-tweet"><a href="https://x.com/casey/status/123456789">Preview</a></blockquote>'
        for suffix in ('', '<p>For comparison, last year\'s product video:</p><iframe src="https://www.youtube.com/embed/AbCdEf01234"></iframe>'):
            e=capture_article_evidence('Example','https://example.com/news',markup+suffix+'</article>',title)
            self.assertEqual(_embedded_current_preview_subject(title,lead,e.embedded_references),
                             'embedded-video:x:123456789')

    def test_court_discovery_recipient_allows_spacing(self):
        from apple_news_core.event_identity import build_event_identity, source_trade_secret_procedure_frame
        for space in ('', ' '):
            title='苹果与 OpenAI 商业机密诉讼：法院批准扩大取证'
            lead=f'法官批准 OpenAI{space}扩大取证，提前获取苹果的商业机密诉讼证据。'
            frame=source_trade_secret_procedure_frame(title,lead,(),build_event_identity(title,lead))
            self.assertIsNone(frame)

    def test_new_client_update_without_version_joins_same_release(self):
        ids=[k for k in self.rows if k.startswith(('485d','8e74','d4ac','df54'))]
        for order in (ids, list(reversed(ids))):
            _, data=self.cluster_sources(*order)
            self.assertEqual(len(data),1)
            self.assertEqual(len(data[0]['sources']),4)

    def test_research_links_and_named_observer_preserve_same_report(self):
        ids=[k for k in self.rows if k.startswith(('42ae','f723','40a5'))]
        for order in (ids, list(reversed(ids))):
            _, data=self.cluster_sources(*order)
            self.assertEqual(len(data),1)
            self.assertEqual(data[0]['relevance_tier'],'strong')
            self.assertEqual(data[0]['category'],'software_systems')
            self.assertEqual(len(data[0]['sources']),3)

    def test_rival_client_visual_comparison_is_not_an_apple_update(self):
        _,data=self.cluster_sources(next(k for k in self.rows if k.startswith('0c56')))
        self.assertEqual(data[0]['relevance_tier'],'weak')

    def test_new_platform_watermark_reports_share_current_capability(self):
        _,data=self.cluster_sources(*(k for k in self.rows if k.startswith(('c6bc','895f'))))
        self.assertEqual(len(data),1)
        self.assertEqual(data[0]['relevance_tier'],'strong')
        self.assertEqual(data[0]['category'],'software_systems')

    def test_system_output_failure_is_not_an_ordinary_app_update(self):
        _,data=self.cluster_sources(next(k for k in self.rows if k.startswith('ae9d')))
        self.assertEqual(data[0]['relevance_tier'],'strong')
        self.assertEqual(data[0]['category'],'software_systems')

    def test_new_cross_build_host_support_is_platform_interoperability(self):
        _,data=self.cluster_sources(next(k for k in self.rows if k.startswith('27da')))
        self.assertEqual(data[0]['relevance_tier'],'ecosystem')
        self.assertEqual(data[0]['category'],'software_systems')

    def test_watermark_capability_rejects_rival_or_conflicting_version(self):
        from apple_news_core.event_identity import source_software_capability_frame
        title='iOS 27.2 adds an invisible watermark'
        for lead in (
            'A third-party app on iOS now uses OtherID watermarks. An Apple Intelligence support document is linked for comparison.',
            'Starting with iOS 28.2, Apple now uses SynthID watermarks. An Apple Intelligence support document confirms this.',
            'Apple plans to add SynthID watermarks in iOS 27.2. The Apple Intelligence support document has not announced this.',
            '苹果官方支持文档介绍 Apple Intelligence，而第三方 Acme 应用引入 SynthID 隐形水印用于导入的照片。',
        ):
            self.assertIsNone(source_software_capability_frame(title,lead,()))

    def test_cross_build_support_requires_current_named_release(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_interoperability_report
        title='ExampleOS 15.2 Beta 1发布：支持在macOS上交叉构建基础系统软件包'
        for lead in ('ExampleOS 15.2计划支持在macOS上交叉构建基础系统软件包。',
                     'ExampleOS 14.2支持在macOS上交叉构建基础系统软件包。',
                     'ExampleOS 15.2不支持在macOS上交叉构建基础系统软件包。',
                     'ExampleOS 15.2 Beta 2支持在macOS上交叉构建基础系统软件包。',
                     'ExampleOS 15.2正式版支持在macOS上交叉构建基础系统软件包。'):
            e=capture_article_evidence('Example','https://example.com/build','<article><p>'+lead+'</p></article>',title)
            self.assertIsNone(bind_interoperability_report(e))

    def test_research_anchors_do_not_join_different_observers(self):
        from apple_news_core.event_matcher import identity_pair_decision
        sid=next(k for k in self.rows if k.startswith('40a5'))
        claim=self.source_articles(sid)[0].bound_claim
        other=replace(claim,qualifiers=tuple((a,b,'someone else' if b=='research-observer' else c,d,e,f)
            for a,b,c,d,e,f in claim.qualifiers))
        self.assertEqual(identity_pair_decision(claim,other),'conflict')

    def test_same_researcher_different_samples_do_not_merge(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_keyboard_dictionary_report
        from apple_news_core.event_matcher import identity_pair_decision
        claims=[]
        for language in ('English','French'):
            title=f'Researcher Alice Smith reveals iOS 27 keyboard blocked phrases in {language} sample'
            lead=f'Researcher Alice Smith found words blocked from autocomplete in iOS 27 keyboard data using an independently collected {language} sample.'
            e=capture_article_evidence('Example','https://example.com/'+language,'<article><p>'+lead+'</p></article>',title)
            claims.append(bind_keyboard_dictionary_report(e))
        self.assertTrue(all(claims))
        self.assertEqual(identity_pair_decision(*claims),'conflict')

    def test_video_failure_keeps_polarity_and_exact_version(self):
        from apple_news_core.event_identity import source_software_capability_frame
        title='用户反馈 iOS 27 外接 HDMI 播放，锁屏即中断输出'
        for lead in ('用户反馈升级 iOS 27 后，通过 HDMI 外接显示设备播放视频时，锁屏后播放不再中断。',
                     '用户反馈升级 iOS 27.1 后，通过 HDMI 外接显示设备播放视频时，锁屏后播放中断。'):
            self.assertIsNone(source_software_capability_frame(title,lead,()))

    def test_unversioned_client_release_keeps_external_platform(self):
        self.assert_distinct_reports(*[
            (f'Apple Music Classical app gets a new icon in latest update for {host}',
             f'Apple today updated Apple Music Classical app for {host} with a new icon.')
            for host in ('Android','iPhone')])

    def test_patent_verdict_preserves_case_and_procedure_boundaries(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_patent_verdict
        from apple_news_core.event_matcher import identity_pair_decision
        def claim(owner='Orion', patents='10,123,456 and 10,234,567', city='San Diego'):
            title=f'Apple owes {owner} damages over haptic patents'
            body=f'A federal jury in {city} has awarded {owner} damages after finding Apple infringed patents. U.S. Patent Nos. {patents} cover haptic feedback.'
            return bind_patent_verdict(capture_article_evidence('Example','https://example.com/case',
                '<article><p>'+body+'</p></article>',title))
        base=claim()
        self.assertIsNotNone(base)
        self.assertEqual(identity_pair_decision(base,claim()),'match')
        for other in (claim(patents='10,345,678 and 10,456,789'), claim(city='New York'), claim(owner='Vega')):
            self.assertIsNotNone(other)
            self.assertEqual(identity_pair_decision(base,other),'conflict')

    def test_patent_verdict_rejects_historical_denied_or_response_reports(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_patent_verdict
        for title,body in (
            ('Apple responds to patent damages award', 'A jury has awarded Orion damages after finding Apple infringed patents.'),
            ('Apple appeals patent damages award', 'A jury has awarded Orion damages after finding Apple infringed patents.'),
            ('Apple owes Orion patent damages', 'Last year a jury awarded Orion damages after finding Apple infringed patents.'),
            ('Apple owes Orion patent damages', 'A jury has not awarded Orion damages against Apple.'),
        ):
            with self.subTest(title=title,body=body):
                evidence=capture_article_evidence('Example','https://example.com/case',
                    '<article><p>'+body+'</p></article>',title)
                self.assertIsNone(bind_patent_verdict(evidence))

    def test_patent_award_requires_apple_liability_and_local_case_evidence(self):
        from apple_news_core.article_processing import capture_article_evidence
        from apple_news_core.event_identity import bind_patent_verdict
        from apple_news_core.event_matcher import identity_pair_decision
        for title,body in (
            ('Apple avoids damages in Acme patent case', 'A jury found Apple did not infringe Acme patents and owes no damages.'),
            ('Acme owes Orion patent damages over technology used in Apple accessories', 'A jury ruled that Acme owes Orion damages for infringing patents.'),
        ):
            evidence=capture_article_evidence('Example','https://example.com/case',
                '<article><p>'+body+'</p></article>',title)
            self.assertIsNone(bind_patent_verdict(evidence))
        claims=[]
        for owner,patents in (('Orion','10,659,885 and 10,820,117'),('Zephyr','10,123,456 and 10,234,567')):
            body=f'A jury ruled that Apple owes Acme $5 million for infringing patents. In an unrelated case last year, a jury awarded {owner} damages over U.S. Patent Nos. {patents}.'
            evidence=capture_article_evidence('Example','https://example.com/'+owner,
                '<article><p>'+body+'</p></article>','Apple owes Acme patent damages')
            claims.append(bind_patent_verdict(evidence))
        self.assertTrue(all(claims))
        self.assertEqual(identity_pair_decision(*claims),'match')

    def test_financing_feed_reports_reach_details_and_preserve_filing_stage(self):
        rows=json.loads((Path(__file__).parent/'fixtures/20261107_financing_feeds.json').read_text())
        articles=[]
        for row in rows:
            candidate=self.m.Candidate(**row)
            with self.subTest(title=row['title']):
                self.assertTrue(self.m.is_relevant_candidate(candidate,self.sources[row['source']]))
                self.assertEqual(self.m.title_led_identity(row['title'],row['summary']).content_form,'news')
            articles.append(article_for(self.m,row['title'],row['summary'],source=row['source']))
        for order in (articles,list(reversed(articles))):
            events=self.m.cluster_articles(order)
            self.assertEqual(len(events),2)
            self.assertTrue(all(e.relevance_tier=='strong' and e.category=='hardware_products' for e in events))
            self.assertEqual(sorted(len(e.articles) for e in events),[2,2])

    def test_financing_context_does_not_promote_retail_or_another_issuer(self):
        for title,lead in (
            ('Save $100 on iPhone in a weekend sale', 'Amazon offers an iPhone discount. Apple also issued bonds to investors.'),
            ('iPhone on sale for $700 following Apple bond sale', 'Amazon has discounted the iPhone. Apple recently issued debt to investors.'),
            ('Bond headphones on sale for $100', 'The retailer has discounted wireless headphones that work with iPhone.'),
            ('Apple supplier Orion confirms $5 billion bond sale', 'Orion filed final debt terms with the SEC. Apple is a customer.'),
            ('Apple iPhone sale offers $100 off after bond offering', 'Amazon discounts the iPhone. Apple previously filed a bond prospectus with the SEC.'),
            ('Orion confirms $5 billion bond sale', 'Orion filed final debt terms with the SEC. Apple is a customer.'),
        ):
            with self.subTest(title=title):
                event=self.m.cluster_articles([article_for(self.m,title,lead)])[0]
                self.assertEqual(event.relevance_tier,'weak')

    def test_financing_confirmation_keeps_negation_and_historical_scope(self):
        from apple_news_core.event_identity import source_named_publication_frame,build_event_identity
        for title,lead in (
            ('Apple confirms bond sale', 'Apple has not confirmed any bond offering in SEC filings.'),
            ("Apple's $7 billion bond sale explained", 'Last year Apple issued bonds and filed a prospectus with the SEC.'),
            ("Looking back at Apple's bond sale last year", 'Apple filed its prospectus with the SEC last year.'),
        ):
            self.assertIsNone(source_named_publication_frame(title,lead,(lead,),build_event_identity(title,lead)))

    def test_future_financing_confirmation_remains_a_plan(self):
        from apple_news_core.event_identity import source_named_publication_frame,build_event_identity
        title='Apple plans to confirm $7 billion bond offering'
        lead='Apple plans to confirm the offering next month after filing a preliminary prospectus with the SEC.'
        frame=source_named_publication_frame(title,lead,(lead,),build_event_identity(title,lead))
        self.assertEqual(frame.action,'bond-offering-plan')
