"""Current actions keep their owners despite release lists and body comparisons."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

GROUPS = {
    'current_memorial': ['804a199c2d967f0b35dc2743','7229aff17529a2bed8be5338'],
    'additional_launch': ['10ec639b1e07565f0cf46f41','b77bbae31d3d3da128fb5c89','b72297f6f468531789303444','7a34f5d772d601ca8473d98e'],
    'siri_delay': ['a503823062042ca8feb938c7','58a0f181f5a3a730196c285d'],
    'safari_telemetry': ['17268f684c676cc7d0273d50','8f4b1842a837d0c989551579'],
    'alias': ['b9c26b357fe8d17505cbb425','f5b8a2e0609b4763492942da'],
    'domain': ['a3552c1fb5ea9a2318b4b0dd','c13972e85410d3759d206e9f'],
    'mixed_quota': ['23047ce640adb7463096dcad'],
    'firmware': ['3da994d66a9b12c5c6b2072e','12dc08b0f991e2c5a3dc8ef2'],
    'mac_code': ['b5d705b07464ac0513aaffc0','b844559fdb813028ccfed276','13142456894c0aa24fe736ef','b643c251125fae9bdd6cc048'],
    'mac_roadmap': ['b4ac4c06064066d6fe3fdb7a'],
    'competitor': ['09afb17ab1cec324e726b887','9cbfd28a0f009c11e01e2095'],
    'beta': ['52dd7c7ecd3285ff87ead232','0907d04938ec0c53b74f521d','e9671a2004822598162aec58','afd27570edae9171ced9f2d6','e32e306cf7d5b5603d59b2c4','40c987e9323753ab06a10b13','1fa32c228c0f001a9cbcacfe','916ea081021c2c13cff03f2a','324a5855b565dfc686e580e8','45135648d3c09a4871f4e498','4da03d68e6c1d901d524b485'],
    'tv_roadmap': ['37bb5e74e876487a30a4aa4c'],
    'tv_code': ['6a7e3217cc4ee885f3773350','955700b8b3922923b0e8bbc9','4fc72dc59bc9265b2fe2f0a5'],
    'focus': ['e6dd75a13f696c4c18202cde','23e87a28f5baecbce9b85a0d','240e016bd125fea3ebf362d5','e8e75ded454933f1bf017c83','34d36e94ebed1789c526c507'],
    'cleanup_tool': ['4847ac49b8dd5635a2725199','51dbfe85110025296babc155','a45853a5fb92bfe78c0e51da','1ae7b1d1e764301c9d19c41d','e3f46736ffaf0f384a262576'],
    'jobs': ['033e09633342e544b9719584','4d4f506a46cfcd4e8628d71a'],
    'historical': ['0133d41cdfbfb794ee536335'],
    'process': ['8ca6b4482f4aca97ebc54a61'],
    'app_submission': ['952bdf071001ef2e26ef3cf1','00b2bdd2759c41769b0e866b','a5443ece3ab0eb14d3ae436e','9a9ccda85336fc8736c5b425'],
    'music_logo': ['be28c6d4cc239f7ec47c83d4','dd6757120d96f6f2c6df0fea'],
    'hdr': ['dff446f1f70ab57e7469b081','c815d799dd26a8c2bf041ba5'],
    'ipad': ['92d1edc455a2eea41d477f01'],
    'os_patcher': ['b47f56842e0b6e54f30e5c83'],
    'carrier_response': ['1d81150e0a5a8086d0cf96c5'],
}

class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent/'fixtures/20261006_source_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,10,6,tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def assert_group(self, name, category, tier='strong'):
        ids = GROUPS[name]
        for order in (ids, ids[::-1]):
            events, data = self.cluster_sources(*order)
            self.assertEqual(len(events),1,[(e.title,e.relevance_tier) for e in events])
            self.assertEqual(self.source_ids(events[0]),set(ids))
            self.assertEqual((events[0].category,events[0].relevance_tier),(category,tier))
        return events, data

    def test_release_inventory_cannot_replace_the_primary_release_with_one_feature(self):
        events,data = self.cluster_sources(GROUPS['beta'][0])
        self.assertEqual(len(events),1)
        self.assertIn('beta',events[0].title.lower())
        self.assertIn('ios',events[0].title.lower())
        for language in ['French','Japanese','Korean','Portuguese','Spanish']:
            self.assertIn(language,json.dumps(data))

    def test_current_numbered_beta_wave_reconciles_ordinal_and_numeric_titles(self):
        self.assert_group('beta','software_systems')

    def test_release_history_appendices_are_not_current_required_facts(self):
        from apple_news_core.article_processing import release_history_unit_ids
        events,data=self.cluster_sources(*GROUPS['beta'])
        for article in events[0].articles:
            history=release_history_unit_ids(article.evidence)
            if not history:
                continue
            self.assertTrue(any(unit.unit_id in history for unit in article.evidence.units))
            view=self.m.prepare_source_fact_view(article)
            for fact in (*view.normal,*view.structured,*view.unprocessed,*view.owned):
                self.assertTrue(all(origin[3] not in history for origin in fact.origins),fact.text)
        body=json.dumps(data,ensure_ascii=False)
        self.assertNotIn('2026-06-09',body)
        for build in ['24B5099f','24B5089g','26B5101f','24S5101f','24N5103f']:
            self.assertIn(build,body)

    def test_history_sections_do_not_hide_current_support_rows_or_prose(self):
        from dataclasses import replace
        from apple_news_core.article_processing import release_history_unit_ids
        from apple_news_core.models import EvidenceUnit
        e=self.evidence('Apple releases iOS 28.2 beta 3',['Apple releases a new beta today.'])
        e=replace(e,units=tuple(EvidenceUnit(str(i),kind,text,'html',i) for i,(kind,text) in enumerate([
            ('p','Apple released iOS 28.2 beta 3 today, replacing build 25B5089g.'),
            ('h3','Appendix: iOS release history'),
            ('p','2027-06-09: iOS 28 Beta (25A5355q)'),
            ('h3','Supported releases for the new upgrade'),
            ('p','2027-09-22: iOS 28.2 Beta 2 (25B5089g)'),
            ('p','2027-09-15: iOS 28.0 (25A437)'),
            ('p','Newly supported devices include iPhone 19.'),
        ])))
        self.assertEqual(release_history_unit_ids(e),frozenset({'1','2'}))
        from apple_news_core.article_projector import source_evidence_remainder
        remaining,excluded=source_evidence_remainder(e,())
        self.assertTrue({'1','2'}.isdisjoint({span[0] for span in remaining}))
        self.assertTrue({'0','3','4','5','6'} <= {span[0] for span in remaining})
        self.assertEqual({row[0] for row in excluded},{'1','2'})
        support=replace(e,units=(
            EvidenceUnit('s0','p','Apple released iOS 28.1 today. The following releases remain eligible for the new upgrade.','html',0),
            EvidenceUnit('s1','h3','Supported release history','html',1),
            EvidenceUnit('s2','p','2027-09-22: iOS 28.0 — eligible for the new upgrade.','html',2),
            EvidenceUnit('s3','p','2027-09-29: iOS 28.0.1 — eligible for the new upgrade.','html',3),
        ))
        self.assertFalse(release_history_unit_ids(support))
        self.assertFalse(release_history_unit_ids(replace(support,units=(
            replace(support.units[1],text='Appendix: iOS release history'), *support.units[2:]))))

    def test_body_component_cannot_merge_firmware_roadmap_and_competitor(self):
        ids=GROUPS['firmware'][:1]+GROUPS['mac_roadmap']+GROUPS['competitor'][:1]
        for order in (ids,ids[::-1]):
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),3)

    def test_accessory_firmware_binds_its_target_in_both_languages(self):
        self.assert_group('firmware','software_systems')

    def test_two_icloud_quota_objects_keep_both_owned_source_spans(self):
        ids=GROUPS['alias']+GROUPS['domain']+GROUPS['mixed_quota']
        for order in (ids,ids[::-1]):
            events,data=self.cluster_sources(*order)
            self.assertEqual(len(events),2)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                {frozenset(GROUPS['alias']+GROUPS['mixed_quota']),frozenset(GROUPS['domain']+GROUPS['mixed_quota'])})
            self.assertTrue(all(e.relevance_tier=='strong' and e.category=='software_systems' for e in events))
            self.assertIn('10',json.dumps(data));self.assertIn('9',json.dumps(data))

    def test_upgrade_count_is_not_a_count_of_products(self):
        events,_=self.cluster_sources(*GROUPS['tv_roadmap'])
        self.assertEqual(len(events),1)
        self.assertIn('Apple TV',events[0].title)
        self.assertNotIn('A15 roadmap',events[0].title)
        self.assertEqual(events[0].category,'hardware_products')

    def test_code_disclosures_keep_software_owner_and_distinct_hardware_roadmap(self):
        self.assert_group('mac_code','software_systems')
        events,_=self.cluster_sources(*(GROUPS['mac_code']+GROUPS['mac_roadmap']))
        self.assertEqual(len(events),2)

    def test_tv_intelligence_code_reports_are_one_software_disclosure(self):
        self.assert_group('tv_code','software_systems')

    def test_focus_disclosure_matches_without_borrowing_hardware_category(self):
        self.assert_group('focus','software_systems')

    def test_independent_cleanup_utility_does_not_borrow_apple_ai_authority(self):
        for sid in GROUPS['cleanup_tool']:
            events,_=self.cluster_sources(sid)
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),sid)

    def test_historical_memorial_and_competitor_remain_weak(self):
        for sid in GROUPS['historical']+GROUPS['competitor']:
            events,_=self.cluster_sources(sid)
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),sid)

    def test_apple_owned_hiring_is_a_current_company_action(self):
        self.assert_group('jobs','hardware_products')

    def test_current_executive_communication_is_not_the_historical_incident(self):
        self.assert_group('current_memorial','hardware_products')

    def test_memorial_post_keeps_current_apple_owner_and_publication_action(self):
        for title,lead in [
            ('Apple CEO posts tribute to Steve Jobs on the 16th anniversary of his death',
             'Apple CEO Jordan Ellis today posted a tribute to Steve Jobs. Jobs died in 2011.'),
            ('苹果 CEO 发文缅怀乔布斯，纪念其逝世 16 周年',
             '苹果现任 CEO 今日发布纪念文字，缅怀乔布斯。乔布斯于2011年逝世。'),
        ]:
            p=self.m.article_reconciliation_profile(article_for(self.m,title,lead))
            self.assertEqual((p.relevance_tier,p.category_hint),('strong','hardware_products'))
            self.assertTrue(any(k.endswith(':memorial-publication') for k in p.event_keys))

    def test_historical_denied_and_outsider_memorials_cannot_become_current_apple_posts(self):
        for title,lead in [
            ('Remembering Steve Jobs on the 16th anniversary of his death', 'Steve Jobs died in 2011; Apple CEO Jordan Ellis has not posted a tribute.'),
            ('Former Apple CEO posts a tribute to Steve Jobs', 'Former Apple CEO Morgan Lane posted a tribute today.'),
            ('Samsung CEO posts a tribute to Steve Jobs', 'Samsung CEO Jordan Ellis posted a tribute today. Apple CEO Morgan Lane did not comment.'),
            ('Apple CEO denies posting tribute to Steve Jobs', 'Apple CEO Jordan Ellis has not posted any tribute; the purported statement is false.'),
            ('Apple CEO tribute to Steve Jobs revisited', 'Apple CEO Jordan Ellis posted the tribute last year. This report reproduces that old post.'),
            ('苹果前任 CEO 发文缅怀乔布斯', '苹果前任 CEO 今日发文缅怀乔布斯。'),
            ('苹果 CEO 去年发文缅怀乔布斯', '苹果CEO去年发布的纪念文章今天被媒体再次转载。'),
            ('Apple CEO attends tribute to Steve Jobs', 'Apple CEO Jordan Ellis attended a ceremony, while a fan posted a tribute to Steve Jobs today.'),
            ('Apple CEO plans to post tribute to Steve Jobs tomorrow', 'Apple CEO Jordan Ellis plans to post a tribute to Steve Jobs tomorrow.'),
            ('Apple CEO tribute to Steve Jobs attracts attention', 'Apple CEO Jordan Ellis posted the tribute to Steve Jobs in 2025. The old post has resurfaced today.'),
            ('Apple CEO tribute to Steve Jobs attracts attention', 'Apple CEO Jordan Ellis posted the tribute to Steve Jobs in 2025. This article reproduces his original statement.'),
            ('苹果 CEO 将于明日发文缅怀乔布斯','苹果现任 CEO 将于明日发文缅怀乔布斯，纪念其逝世16周年。'),
            ('苹果CEO计划明天发文纪念乔布斯','苹果CEO计划明天发文纪念乔布斯。'),
        ]:
            with self.subTest(title=title):
                p=self.m.article_reconciliation_profile(article_for(self.m,title,lead))
                self.assertFalse(any(k.endswith(':memorial-publication') for k in p.event_keys))

    def test_memorial_posts_keep_the_honoree_and_anniversary_boundary(self):
        def report(person,anniversary):
            return article_for(self.m,f'Apple CEO posts tribute to {person} on the {anniversary}th anniversary of his death',
                f'Apple CEO Jordan Ellis posted a tribute to {person} today.')
        a=report('Steve Jobs',16)
        for b in [report('Steve Jobs',17),report('Alan Turing',16)]:
            for pair in ([a,b],[b,a]):
                self.assertEqual(len(self.m.cluster_articles(pair)),2)

    def test_apple_process_evaluation_is_hardware_not_executive_news(self):
        self.assert_group('process','hardware_products')

    def test_app_submission_is_a_software_operation(self):
        self.assert_group('app_submission','software_systems')

    def test_same_music_wordmark_change_matches_across_languages(self):
        self.assert_group('music_logo','software_systems')

    def test_current_os_hdr_change_survives_personal_monitor_test_context(self):
        self.assert_group('hdr','software_systems')

    def test_unspecified_model_does_not_hide_current_ipad_design_report(self):
        self.assert_group('ipad','hardware_products')

    def test_patcher_adds_os_support_instead_of_using_existing_protocols(self):
        self.assert_group('os_patcher','software_systems','ecosystem')

    def test_current_carrier_reply_is_not_lost_behind_last_week_background(self):
        self.assert_group('carrier_response','hardware_products')

    def evidence(self, title, paragraphs):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit
        return ArticleEvidence('boundary-test','MacRumors','https://example.com/boundary',
            title,paragraphs[0],'news',tuple(EvidenceUnit(str(i),'p',text,'body',i) for i,text in enumerate(paragraphs)))

    def test_quota_objects_numbers_history_and_denial_keep_local_ownership(self):
        from apple_news_core.event_identity import bind_mail_quota_claims
        from apple_news_core.event_matcher import identity_pair_decision
        title='Apple increases iCloud mail limits'
        current=self.evidence(title,[
            'Apple has increased iCloud Mail aliases from four to eight.',
            'Apple has increased personalized addresses per custom email domain from two to six.',
            'Now users can set up to five custom domains and create up to six personalized email addresses per domain.'])
        claims=bind_mail_quota_claims(current)
        self.assertEqual({c.object for c in claims},{'mail-alias','custom-domain-address'})
        domain=next(c for c in claims if c.object=='custom-domain-address')
        self.assertEqual({q[2] for q in domain.qualifiers if q[1]=='quota-to'},{'6'})
        other=bind_mail_quota_claims(self.evidence(title,['Apple has increased iCloud Mail aliases from four to seven.']))[0]
        alias=next(c for c in claims if c.object=='mail-alias')
        self.assertEqual(identity_pair_decision(alias,other),'conflict')
        for text in [
            'Apple has not raised the iCloud Mail alias limit from four to eight.',
            'Last year Apple raised the iCloud Mail alias limit from four to eight.',
            'Orion increases its iCloud Mail aliases from four to eight.',
        ]:
            with self.subTest(text=text):
                self.assertFalse(bind_mail_quota_claims(self.evidence(title,[text])))

    def test_standalone_language_rollout_survives_release_inventory_guard(self):
        e=self.evidence('Siri adds language support',[
            'Siri AI now supports French and Japanese.'])
        projections,_,_=self.m.project_article_evidence(e)
        self.assertEqual(len(projections),1)
        self.assertEqual(projections[0].claim.object,'languages')

    def test_version_and_object_boundaries_prevent_code_discovery_bridges(self):
        from apple_news_core.event_matcher import profile_pair_decision
        cases=[
            ('macOS 28.2 code reveals new touch gestures', 'macOS 28.2 code references new touch gesture recognizers for Notes.'),
            ('macOS 29.2 code reveals new touch gestures', 'macOS 29.2 code references new touch gesture recognizers for Notes.'),
            ('macOS 28.2 code reveals a new Settings pane', 'macOS 28.2 code references a new Settings pane for Safari.')]
        profiles=[self.m.article_reconciliation_profile(article_for(self.m,t,l)) for t,l in cases]
        for other in profiles[1:]:
            self.assertNotEqual(profile_pair_decision(profiles[0],other),'match')

    def test_old_reference_or_denial_cannot_establish_current_capability(self):
        from apple_news_core.event_identity import source_software_capability_frame
        for title,lead in [
            ('macOS 28.2 has no new touch gestures', 'The old code references touchscreen hardware, but no new touch gesture was found.'),
            ('Last year macOS 28.2 code revealed touch gestures', 'Previously discovered references are unchanged.'),
            ('Apple Music logo is unchanged', 'Apple denied introducing a new logo.'),
        ]:
            with self.subTest(title=title):
                self.assertIsNone(source_software_capability_frame(title,lead,()))

    def test_company_evaluation_and_hiring_do_not_borrow_other_actors(self):
        from apple_news_core.event_identity import source_owned_organization_frame
        for title,lead in [
            ('Intel 16A process evaluation expands', 'Orion is evaluating Intel 16A. Apple has not joined the evaluation.'),
            ('Apple recruitment remembered', 'Last year Apple was hiring for its iCup team.'),
        ]:
            with self.subTest(title=title):
                self.assertIsNone(source_owned_organization_frame(title,lead))

    def test_device_fault_recap_without_new_response_stays_weak(self):
        a=article_for(self.m,'Apple and AT&T have yet to explain the iPhone 19 Pro issue',
            'Last week Apple said affected iPhone 19 Pro devices need replacement. No new statement has been provided.')
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'weak')

    def test_siri_regional_delay_keeps_forecast_action(self):
        self.assert_group('siri_delay','software_systems')

    def test_safari_promotion_measurement_is_not_an_advertising_rollout(self):
        self.assert_group('safari_telemetry','software_systems')

    def test_two_quota_clauses_and_domain_count_have_separate_objects(self):
        from apple_news_core.event_identity import bind_mail_quota_claims
        e=self.evidence('Apple increases iCloud mail quotas',[
            'Apple has increased iCloud Mail aliases from three to nine and personalized addresses per custom email domain from three to ten.'])
        claims=bind_mail_quota_claims(e)
        self.assertEqual({c.object:{q[1]:q[2] for q in c.qualifiers} for c in claims},
            {'mail-alias':{'quota-from':'3','quota-to':'9'},'custom-domain-address':{'quota-from':'3','quota-to':'10'}})
        count=bind_mail_quota_claims(self.evidence('Apple increases iCloud domain quota',[
            'Apple has increased the number of custom domains in iCloud from five to ten.']))
        self.assertEqual([c.object for c in count],['custom-domain-count'])

    def test_external_or_historical_code_report_does_not_become_apple_discovery(self):
        for title,lead in [
            ('macOS 28.2 touchscreen code report revisited','Apple found references to touch gestures last year; the code has not changed.'),
            ('Orion adds macOS 28.2 touch gestures to its utility','Orion discovered a way to emulate touchscreen gestures in its own open-source app for macOS 28.2.'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(self.m.article_reconciliation_profile(article_for(self.m,title,lead)).relevance_tier,'weak')

    def test_hiring_denial_and_closed_listing_do_not_create_open_job(self):
        for title,lead in [
            ('Apple is not hiring for its iCup team','Reports that Apple is hiring for its iCup team are false; no job opening exists.'),
            ('Apple is hiring for its iCup team, according to an old listing','Apple is hiring for its iCup team, said a job listing from last year that is now closed.'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(self.m.article_reconciliation_profile(article_for(self.m,title,lead)).relevance_tier,'weak')

    def test_apple_published_open_source_tool_remains_first_party(self):
        a=article_for(self.m,'Apple releases a new open-source command-line tool for Swift developers',
            'Apple today released a new open-source tool that helps developers build Swift packages.')
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')

    def test_accessory_firmware_keeps_version_and_release_channel(self):
        a=article_for(self.m,'Apple Releases MagSafe 3 Cable Firmware 10M1543',
            'Apple today released firmware version 10M1543 for its MagSafe 3 charging cable.')
        for build,stage in [('10M1843',''),('10M1543','Beta')]:
            b=article_for(self.m,f'Apple Releases MagSafe 3 Cable Firmware {build} {stage}',
                f'Apple today released {stage} firmware version {build} for its MagSafe 3 charging cable.')
            for order in ([a,b],[b,a]):
                self.assertEqual(len(self.m.cluster_articles(order)),2)

    def test_quota_binding_is_independent_of_clause_order_and_adjectives(self):
        from apple_news_core.event_identity import bind_mail_quota_claims
        for text in [
            'Apple has increased personalized addresses per custom email domain from three to ten and mail aliases from three to nine.',
            'Apple has increased iCloud Mail aliases from three to nine and standard custom domain addresses from three to ten.',
        ]:
            claims=bind_mail_quota_claims(self.evidence('Apple increases iCloud limits',[text]))
            self.assertEqual({c.object:{q[1]:q[2] for q in c.qualifiers} for c in claims},
                {'mail-alias':{'quota-from':'3','quota-to':'9'},'custom-domain-address':{'quota-from':'3','quota-to':'10'}})

    def test_past_team_activity_does_not_negate_current_hiring(self):
        a=article_for(self.m,'Apple is hiring for its iCup team',
            'Apple is hiring for its iCup team today. The team expanded last year.')
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')

    def test_beta_history_does_not_split_final_firmware_release(self):
        title='Apple Releases MagSafe 3 Cable Firmware 10M1543'
        a=article_for(self.m,title,'Apple today released firmware version 10M1543 for its MagSafe 3 charging cable.')
        b=article_for(self.m,title,'Apple today released firmware version 10M1543 for its MagSafe 3 charging cable after beta testing.')
        self.assertEqual(len(self.m.cluster_articles([a,b])),1)

    def test_denials_do_not_acquire_positive_action_keys(self):
        for title,lead,predicate in [
            ('macOS 28.2 touch gesture discovery claim denied','Apple confirmed no new touch gesture code was discovered in macOS 28.2.','feature-code-discovery'),
            ('EU users will not wait months for Siri AI','Apple confirmed that EU users will not face a months-long delay for Siri AI; it launches today.','regional-availability-delay-report'),
            ('Apple denies Safari code will track Google promotions','Apple is not testing code to track Google promotions in Safari on iOS 28.2.','code-experiment-report'),
            ('Apple TV 4K launch next week ruled out','Apple has confirmed that the Apple TV 4K will not launch next week.','reported-launch-window'),
        ]:
            with self.subTest(title=title):
                p=self.m.article_reconciliation_profile(article_for(self.m,title,lead))
                self.assertFalse(any(k.endswith(':'+predicate) for k in p.event_keys))

    def test_causal_editorial_does_not_reannounce_a_quoted_prior_policy(self):
        events,_=self.cluster_sources('b30487da477f4d55c97a8592')
        self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_current_announcement_survives_causal_headline_rhetoric(self):
        a=article_for(self.m,'苹果收紧 macOS 完全磁盘访问权限，都是 AI 工具惹的祸',
            '苹果公司今日宣布，将为 macOS 完全磁盘访问权限增加额外控制，防止 AI 工具读取用户私人文件。')
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')

    def test_app_submission_announcement_must_actually_open_submission(self):
        for status in ['Cannot Be Submitted Yet', "Cannot Be Submitted", "Won't Be Accepted Yet"]:
            a=article_for(self.m,'Apple Announces iPhone Duo Apps '+status,
                'Apple announced that iPhone Duo apps cannot be submitted to the App Store yet; submission opens next month.')
            p=self.m.article_reconciliation_profile(a)
            self.assertFalse(any(k.endswith(':app-submission-open') for k in p.event_keys))

    def test_same_independent_utility_reconciles_as_one_weak_event(self):
        self.assert_group('cleanup_tool','software_systems','weak')

    def test_independent_utility_names_and_versions_are_not_interchangeable(self):
        a=article_for(self.m,'New open-source utility removes AI files on macOS',
            'An independent command-line tool called Alpha 2.1 removes downloaded models from a Mac.')
        for name in ['Beta 2.1','Alpha 2.2']:
            b=article_for(self.m,'Another open-source utility removes AI files on macOS',
                f'An independent command-line tool called {name} removes downloaded models from a Mac.')
            self.assertEqual(len(self.m.cluster_articles([a,b])),2)

    def test_utility_pronouns_and_competitor_mentions_cannot_supply_identity(self):
        cedar='Cedar: a new open-source utility for macOS'
        birch='Birch: a new open-source utility for macOS'
        for left,right in [
            ('It is a command-line tool that removes unused AI files on macOS.', 'It is a command-line tool that removes unused AI files on macOS.'),
            ('Cedar is a new open-source utility for macOS. It competes with a tool called Birch.', 'Birch is a tool for removing AI files on macOS.'),
        ]:
            a=article_for(self.m,cedar,left);b=article_for(self.m,birch,right)
            self.assertEqual(len(self.m.cluster_articles([a,b])),2)

    def test_additional_launch_reports_share_current_campaign_not_beta_background(self):
        self.assert_group('additional_launch','hardware_products')
        events,_=self.cluster_sources(*(GROUPS['additional_launch']+GROUPS['beta'][:2]))
        self.assertEqual(len(events),2)
        self.assertEqual({frozenset(self.source_ids(e)) for e in events},
            {frozenset(GROUPS['additional_launch']),frozenset(GROUPS['beta'][:2])})

    def test_launch_campaign_keeps_month_stage_owner_and_current_assertion(self):
        a=article_for(self.m,'Apple planning a second wave of product announcements',
            'Apple is planning to unveil another batch of products in the final week of October.')
        for title,lead in [
            ('Apple planning a second wave of product announcements', 'Apple is planning to unveil another batch of products in the final week of November.'),
            ('Apple event planned for October 13', 'Apple is planning to unveil its first wave of home products on October 13.'),
            ('Samsung planning a second wave of product announcements', 'Samsung is planning to unveil another batch of products in the final week of October. Apple held an event earlier.'),
            ('Apple denies second wave of product announcements', 'Apple denied reports it is planning another batch of products in the final week of October.'),
            ('Looking back at Apple’s two sets of product launches', 'Apple unveiled another batch of products in the final week of October last year.'),
            ('Apple planning a second wave of product announcements', 'Last year Apple was planning to unveil another batch of products in the final week of October.'),
            ('Apple planning a third wave of product announcements', 'Apple is planning to unveil another batch of products in the final week of October.'),
        ]:
            b=article_for(self.m,title,lead)
            self.assertEqual(len(self.m.cluster_articles([a,b])),2,(title,lead))

    def test_current_launch_clause_owns_month_and_explicit_year(self):
        title='Apple planning a second wave of product announcements'
        def report(text):
            return article_for(self.m,title,text)
        changed=report('Apple previously planned to unveil another batch of products in the final week of October, but now plans the second wave for the final week of November.')
        october=report('Apple is planning to unveil another batch of products in the final week of October.')
        november=report('Apple is planning to unveil another batch of products in the final week of November.')
        self.assertEqual(len(self.m.cluster_articles([changed,november])),1)
        self.assertEqual(len(self.m.cluster_articles([changed,october])),2)
        dated=[report(f'Apple is planning to unveil another batch of products in the final week of October {year}.') for year in [2026,2027]]
        self.assertEqual(len(self.m.cluster_articles(dated)),2)
        self.assertEqual(len(self.m.cluster_articles([october,dated[0]])),1)
