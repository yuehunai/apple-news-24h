"""Incident remedies and platform objects retain their local action boundaries."""
import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load_module()
        cls.rows=json.loads((Path(__file__).parent/'fixtures/20261003_source_boundaries.json').read_text())
        cls.sources={s.name:s for s in cls.m.build_sources(datetime(2026,10,3,tzinfo=timezone.utc))}
    source_articles=prior.PureJsonBatchTests.source_articles
    cluster_sources=prior.PureJsonBatchTests.cluster_sources
    source_ids=staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_incident_has_four_evidence_backed_actions_with_software_remedies(self):
        ids=['6c33b0ede52e634f52b8ebe5','3e2c595aaf1ee11590bca72b','8a03bd6da7bb00a13fdeff76','ac0313f05098353656f4650a','efe935eb4fb236011f5f86b1','6cdafd864c979de2ebb223c5','a9f500e04cd21c3e68d60f95','7e171854b222d9386f2d7553','0b294b1bdc73258aa815ca44']
        for order in [ids,list(reversed(ids))]:
            events,_=self.cluster_sources(*order)
            self.assertEqual(len(events),4,[(e.title,self.source_ids(e)) for e in events])
            self.assertTrue(all(a.bound_claim is not None for e in events for a in e.articles))
            groups={e.articles[0].bound_claim.action:e for e in events}
            self.assertEqual(set(groups),{'carrier-incident-notice','carrier-settings-release','setup-update-requirement','device-replacement-remedy'})
            self.assertEqual(self.source_ids(groups['setup-update-requirement']),{ids[2]})
            self.assertEqual(self.source_ids(groups['carrier-settings-release']),{ids[2]})
            self.assertEqual(self.source_ids(groups['device-replacement-remedy']),{ids[3],ids[7],ids[8]})
            for name,e in groups.items():
                self.assertEqual(e.category,'software_systems' if name in {'carrier-settings-release','setup-update-requirement'} else 'hardware_products')
                self.assertEqual(e.relevance_tier,'strong')
            self.assertEqual(set().union(*(self.source_ids(e) for e in events)),set(ids))

    def test_same_permission_plan_merges_across_six_sources(self):
        ids=['b14db74d15a8d37a16ab5a0b','eead8de5ef9370e0fc3607dc','25cc6253ebad621499d49d1d','9ad18e6d9fadb8354ab48490','3cfdff4717e615b1f6a5ccc3','5a7d71145a3f7a0f681d9741']
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(self.source_ids(events[0]),set(ids))
        self.assertEqual((events[0].category,events[0].relevance_tier),('software_systems','strong'))

    def test_different_current_os_surfaces_do_not_merge(self):
        events,_=self.cluster_sources('9be19d4b9537cad40141dd7d','e3a62293365d94aff28e46b7')
        self.assertEqual(len(events),2)
        self.assertTrue(all(e.category=='software_systems' and e.relevance_tier=='strong' for e in events))

    def test_attributed_homeos_roadmap_is_one_system_action(self):
        ids=['53265d928ea06f0ef5a2350d','397f1489d6967887846ef3cf']
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),1)
        self.assertEqual(self.source_ids(events[0]),set(ids))
        self.assertEqual(events[0].category,'software_systems')

    def test_protocol_migration_commitment_is_software(self):
        events,_=self.cluster_sources('fdbb6182e52d30d9ee84424c')
        self.assertEqual((events[0].category,events[0].relevance_tier),('software_systems','strong'))

    def test_newly_disclosed_protection_bypass_is_security_even_with_old_video(self):
        events,_=self.cluster_sources('a2a290c1495ef98607d00530')
        self.assertEqual((events[0].category,events[0].relevance_tier),('software_systems','strong'))

    def test_evergreen_choice_guide_and_historical_date_guess_stay_weak(self):
        for sid in ['d09789d939a107e76b41ee93','d2a11bce4673d4f32c1c85c0']:
            with self.subTest(sid=sid):
                events,_=self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier=='weak' for e in events))

    def test_removable_layer_and_service_price_both_survive_same_sentence(self):
        events,data=self.cluster_sources('d555ba83d3628e369029503b')
        self.assertEqual(len(events),2)
        self.assertEqual({e.category for e in events},{'software_systems','hardware_products'})
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))
        for e in events:
            self.assertEqual(self.source_ids(e),{'d555ba83d3628e369029503b'})

    def test_unrelated_weak_sources_are_not_promoted(self):
        for sid in ['395829e1b8630e96c4ad22ed','dbc2fc004b0f9b7b6d013abc','46f69335df2f5290280ec640','07362e0f0b42eb36d76755e5','435a084a57866d73f8dccb02']:
            events,_=self.cluster_sources(sid)
            self.assertTrue(all(e.relevance_tier=='weak' for e in events),sid)

    def remedy_evidence(self,title,paragraphs):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        return ArticleEvidence('incident-test','MacRumors','https://example.com/incident',title,paragraphs[0],'news',
            tuple(EvidenceUnit(str(i),'p',t,'body',i) for i,t in enumerate(paragraphs)))

    def test_remedies_require_affirmative_current_own_device_action(self):
        from apple_news_core.event_identity import bind_connectivity_remedy_claims
        title='Meridian and Apple take steps to fix iPhone 19 Pro cellular issues'
        for statement in [
            'Apple has not released a Meridian carrier settings update for iPhone 19 Pro.',
            'Apple might release a Meridian carrier settings update for iPhone 19 Pro.',
            'Apple today released an Orion carrier settings update for iPhone 19 Pro.',
            'Apple today released an Orion carrier settings update for iPhone 19 Pro, while the Meridian network remains affected.',
            'Apple released a Meridian carrier settings update for iPhone 19 Pro last week.',
            'Last year, Apple released a Meridian carrier settings update for iPhone 19 Pro.',
            'Apple today released a Meridian carrier settings update for iPhone 18 Pro.',
            'Apple today started requiring iPhone 18 Pro users to install iOS 28.0.1 to set up the device.',
        ]:
            e=self.remedy_evidence(title,['The iPhone 19 Pro has cellular issues on the Meridian network.',statement])
            self.assertFalse(bind_connectivity_remedy_claims(e),statement)

    def test_distinct_networks_and_device_models_keep_remedies_separate(self):
        from apple_news_core.event_identity import bind_connectivity_remedy_claims
        from apple_news_core.event_matcher import identity_pair_decision
        def claims(network,model):
            return bind_connectivity_remedy_claims(self.remedy_evidence(
                network+' and Apple take steps to fix iPhone '+model+' cellular issues',[
                    'The iPhone '+model+' has cellular issues on the '+network+' network.',
                    'Apple today released a '+network+' carrier settings update for iPhones.',
                    'Apple today started requiring iPhone '+model+' users to install iOS 28.0.1 to set up the device.']))
        a=claims('Meridian','19 Pro');self.assertEqual(len(a),2)
        for b in [claims('Orion','19 Pro'),claims('Meridian','20 Pro')]:
            self.assertEqual(len(b),2)
            for first,second in zip(a,b):self.assertEqual(identity_pair_decision(first,second),'conflict')

    def test_permission_owner_and_rollout_stage_do_not_borrow_background(self):
        from apple_news_core.event_identity import source_operation_frame,build_event_identity
        cases=[
            ('Meta adds Full Disk Access to its macOS app','Meta released its new macOS app today. Apple previously announced plans to tighten Full Disk Access controls.'),
            ('Apple has no plans to tighten Full Disk Access on macOS','Apple says it has no plans to introduce additional controls.'),
            ('Apple will not tighten macOS Full Disk Access','Apple denies plans to add new controls.'),
        ]
        for title,lead in cases:
            f=source_operation_frame(title,lead,(),build_event_identity(title,lead))
            self.assertTrue(f is None or f.action!='permission-control-plan')
        articles=[article_for(self.m,t,l) for t,l in [
            ('Apple announces plans to tighten Full Disk Access on macOS','Apple will introduce additional controls in a future update.'),
            ('Apple announces new Full Disk Access controls for macOS','Apple today released the new controls in macOS 28.1; they are now available.')]]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)

    def test_current_surface_versions_do_not_merge(self):
        titles=['iOS 28 adds new ways to customize the Lock Screen','iOS 29 adds new ways to customize the Lock Screen']
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,t,t+'. Apple introduced these new features.') for t in titles])),2)

    def test_replacement_denial_does_not_match_affirmative_remedy(self):
        from apple_news_core.event_identity import bind_connectivity_remedy_claims
        from apple_news_core.event_matcher import identity_pair_decision
        claims=[]
        for phrase in ['need','do not need']:
            e=self.remedy_evidence('Apple confirms iPhone 19 Pro Meridian cellular issues, replacement statement',[
                'iPhone 19 Pro users on the Meridian network have cellular issues.',
                'Apple says iPhone 19 Pro users on the Meridian network '+phrase+' a hardware replacement.'])
            c=bind_connectivity_remedy_claims(e);self.assertEqual(len(c),1);claims.append(c[0])
        self.assertEqual(identity_pair_decision(*claims),'conflict')
        e=self.remedy_evidence('Apple confirms iPhone 19 Pro Meridian cellular issues, replacement statement',[
            'iPhone 19 Pro users on the Meridian network have cellular issues.',
            'Apple says iPhone 19 Pro users do not need a software update but need a hardware replacement.'])
        positive=bind_connectivity_remedy_claims(e)
        self.assertEqual(len(positive),1)
        self.assertEqual(identity_pair_decision(claims[0],positive[0]),'match')

    def test_cover_price_order_does_not_drop_second_action(self):
        from apple_news_core.event_identity import bind_replaceable_component_claims
        for sentence in [
            'The iPhone Duo cover layer is replaceable for a $19 fee under AppleCare+.',
            'The iPhone Duo cover layer can be replaced, with each replacement costing $19 under AppleCare+.',
        ]:
            e=self.remedy_evidence('Apple confirms iPhone Duo cover layer is replaceable',[sentence])
            claims=bind_replaceable_component_claims(e)
            self.assertEqual({c.action for c in claims},{'replaceable-cover-design','repair-fee-schedule'})
            projections,remainder,excluded=self.m.project_article_evidence(e)
            self.m.validate_evidence_dispositions(e,projections,remainder,excluded)

    def test_settings_and_mandatory_os_versions_cannot_bridge(self):
        articles=[]
        for i,statement in enumerate([
            'Apple today released a Meridian carrier settings update (version 72.1) for iPhone 19 Pro.',
            'Apple today released a Meridian carrier settings update (version 72.2) for iPhone 19 Pro.',
            'Apple today released a Meridian carrier settings update (version 72.1) for iPhone 19 Pro, while an upgrade to version 72.2 is only being considered.',
            'Apple today released a Meridian carrier settings update, upgrading from version 72.0.2 to version 72.1 for iPhone 19 Pro.',
            'Apple today started requiring iPhone 19 Pro users to install iOS 28.0.1 to set up the device.',
            'Apple today started requiring iPhone 19 Pro users to install iOS 28.0.2 to set up the device.',
            'For users running iOS 28.0, Apple today started requiring iPhone 19 Pro users to install iOS 28.0.1 to set up the device.',
        ]):
            e=self.remedy_evidence('Meridian and Apple take steps to fix iPhone 19 Pro cellular issues',[
                'iPhone 19 Pro users on the Meridian network have cellular issues.',statement])
            projections,remaining,excluded=self.m.project_article_evidence(e)
            self.m.validate_evidence_dispositions(e,projections,remaining,excluded)
            self.assertEqual(len(projections),1)
            p=projections[0]
            a=article_for(self.m,p.title,p.summary);a.evidence=e;a.bound_claim=p.claim
            articles.append(a)
        self.assertEqual(len(self.m.cluster_articles(articles)),4)
        duplicate=article_for(self.m,articles[0].title,articles[0].summary)
        duplicate.evidence=articles[0].evidence;duplicate.bound_claim=articles[0].bound_claim
        self.assertEqual(len(self.m.cluster_articles([*articles,duplicate])),4)

if __name__=='__main__':unittest.main()
