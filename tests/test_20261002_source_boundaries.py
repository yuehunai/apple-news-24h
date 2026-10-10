"""Source-owned objects and operations must survive translation and comparison."""
import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261002_source_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,10,2,tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def assert_group(self, ids, category, tier='strong'):
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1, [(e.title,e.relevance_tier) for e in events])
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual(events[0].category, category)
        self.assertEqual(events[0].relevance_tier, tier)
        return events[0]

    def test_catalog_additions_are_not_service_outages(self):
        outage = ['9e7c8bdd1b624b732def6419','a6c7920246f27e333308f03e']
        catalog = ['388322dd2ae35a030aba2b64','6b8deefa3cbdbb455b2b091e','29e197503f5c0e9b42798521']
        self.assert_group(outage,'software_systems')
        self.assert_group(catalog,'software_systems')
        events,_ = self.cluster_sources(*outage,*catalog)
        self.assertEqual({frozenset(self.source_ids(e)) for e in events}, {frozenset(outage),frozenset(catalog)})

    def test_competitor_and_editorial_cannot_borrow_background_actions(self):
        for sid in ['61124463435be021d71457ec','3c131ec12ae5d8094bb0cbe9','f1482ae9d70ba6857bee6d14','c0a7ddc53ed35e293e68e294','dd161bb36534cd4c16746671']:
            with self.subTest(sid=sid):
                events,_=self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier=='weak' for e in events))
        events,_=self.cluster_sources('61124463435be021d71457ec','8a1e6f26f783db7ab086e04a')
        self.assertEqual(len(events),2)

    def test_comparison_owner_is_not_a_vendor_name_allowlist(self):
        for title in ["Meridian’s answer to the MacBook Neo comes with OLED", "Orion's alternative to iPad is lighter"]:
            events=self.m.cluster_articles([article_for(self.m,title,'The company announced its own new device today. Apple hardware is the comparison.')])
            self.assertTrue(all(e.relevance_tier=='weak' for e in events))
        events=self.m.cluster_articles([article_for(self.m,'Apple’s answer to Meridian is an OLED MacBook Pro','Apple is developing a new MacBook Pro with an OLED display.')])
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def test_home_setup_is_one_software_discovery(self):
        self.assert_group(['1b7ade26d69c745717c3153b','d26dc6019863ff9a3fcffc7f','3421adfc10e29d47ffaa1064'],'software_systems')

    def test_device_colors_are_not_the_preview_software(self):
        ids=['da87f36d98cbd80cf4f5d07c','85d63b318da536c4a5362282','009c1cf4c1ba7e8f0c8c5140','a3a15dc4ee6c927f3d13b623']
        self.assert_group(ids,'hardware_products')
        events,_=self.cluster_sources(*ids,'1b7ade26d69c745717c3153b')
        self.assertEqual(len(events),2)

    def test_reported_camera_is_hardware_even_when_it_does_not_record(self):
        self.assert_group(['fe6fd473347c0a2683721ce2','bdcf287141574949627347b3','3222fdde4cc83440afccd8d3','656e3c848a3aef4ff310bad3'],'hardware_products')

    def test_recognized_user_content_switch_is_software(self):
        self.assert_group(['bc3ce52e9ce672a4c131edb5','32ee2902a06d82694f490fe1'],'software_systems')

    def test_protocol_shutdown_is_an_interoperability_change(self):
        self.assert_group(['9a168a76cc3c0111785d691d'],'software_systems','ecosystem')

    def test_security_bypass_keeps_same_mechanism_and_software_category(self):
        self.assert_group(['3e29691a86fc5197084c7a69','4b5f0fe83326a127d80b8359','cc8fdbd28d9e4e5edd7089db'],'software_systems')

    def test_retail_material_delivery_is_not_a_product_roadmap(self):
        self.assert_group(['a5575288109cd74d678f1c0a','5f4536ff786538ef9ca75795','3f013e9da576d4c4ba4741a9'],'hardware_products')

    def test_commissioned_photos_have_a_current_campaign(self):
        self.assert_group(['990258a9daab819f7b22d3c3','12e15939a8f36eda9a74095e','b207194c49a9066d5c8fd5e1'],'hardware_products')
        articles = [article_for(self.m, title, lead) for title,lead in [
            ('Apple shares new photos shot on iPhone 18',
             'Apple commissioned photographers Alex Moore and Robin Hill for this gallery.'),
            ('Apple shares another gallery shot on iPhone 18',
             'Apple commissioned photographers Casey Jones and Jamie Reed for another gallery.')]]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)
        def photo(title, lead):
            return article_for(self.m, 'Apple shares photos shot on iPhone 18: '+title, lead)
        for connector in ['with', 'and']:
            group = self.m.cluster_articles([
                photo('new gallery','Apple commissioned photographers Alex Moore and Robin Hill for this gallery.'),
                photo('latest gallery','Apple commissioned photographers Alex Moore '+connector+' Robin Hill for this gallery.')])
            self.assertEqual(len(group),1)
        self.assertEqual(len(self.m.cluster_articles([
            photo('new gallery','Apple commissioned photographer Alex Moore for this gallery.'),
            photo('another gallery','Apple commissioned photographer Casey Jones for another gallery.')])),2)
        group = self.m.cluster_articles([
            photo(label, 'Apple commissioned photographer Alex Moore for this gallery. Last year, photographers '+names+' worked on a different campaign.')
            for label,names in [('new gallery','Casey Jones and Jamie Reed'),('latest gallery','Robin Hill and Morgan Stone')]])
        self.assertEqual(len(group),1)
        group = self.m.cluster_articles([
            photo(label, "Apple's official Instagram account shares a new Shot on iPhone gallery today. Last year, photographers "+names+' worked on a different campaign.')
            for label,names in [('new gallery','Casey Jones and Jamie Reed'),('latest gallery','Robin Hill and Morgan Stone')]])
        self.assertEqual(len(group),1)

    def test_sparse_background_sources_cannot_bridge_owned_operations(self):
        catalog=['388322dd2ae35a030aba2b64','6b8deefa3cbdbb455b2b091e','29e197503f5c0e9b42798521']
        ids=[*catalog,'9e7c8bdd1b624b732def6419','a6c7920246f27e333308f03e','5f908dc6b8dc2db05fdc2ad2',
             'a5575288109cd74d678f1c0a','cfea29d69030072c9808c2b3']
        events,_=self.cluster_sources(*ids)
        groups={frozenset(self.source_ids(e)) for e in events}
        self.assertEqual(groups,{frozenset(catalog),frozenset(ids[3:5]),*(frozenset([i]) for i in ids[5:])})

    def test_attributed_podcast_disclosure_retains_its_reported_product(self):
        self.assert_group(['114057ba4fcf4391bc6951e2','8a1e6f26f783db7ab086e04a'],'hardware_products')

    def test_operations_preserve_owner_object_and_polarity(self):
        cases=[
            ("TraceBox can bypass the iPhone inactivity reboot", "ProbeKit can bypass the iPhone inactivity reboot"),
            ("TraceBox can bypass the iPhone inactivity reboot", "TraceBox cannot bypass the iPhone inactivity reboot"),
            ("Apple's Home Hub color options surface in a code leak", "Meridian's Home Hub color options surface in a code leak"),
            ("Apple TV adds classic movies today", "Apple TV removes classic movies today"),
        ]
        for first,second in cases:
            with self.subTest(second=second):
                events=self.m.cluster_articles([article_for(self.m,t,t+'. The report describes this current operation.') for t in [first,second]])
                self.assertEqual(len(events),2)
        from apple_news_core.event_identity import build_event_identity
        self.assertNotIn('apple-home-hub',build_event_identity("'DeskPad' gets new colors","Meridian's new home hub, commonly called 'DeskPad,' runs its own software.").title_products)

    def test_service_outage_binds_target_and_restoration_polarity(self):
        from apple_news_core.event_identity import build_event_identity, source_operation_frame
        def frame(title):
            return source_operation_frame(title,title,(),build_event_identity(title,title))
        down=frame('Apple TV is down after a streaming outage')
        self.assertEqual(frame('Apple TV outage still not resolved'),down)
        self.assertEqual(frame('Apple Music restored, but Apple TV is still down'),down)
        self.assertEqual(frame('Apple Music restored, Apple TV is still down'),down)
        self.assertEqual(frame('Apple Music is back online, Apple TV remains unavailable'),down)
        self.assertEqual(frame('Apple TV suffers a streaming disruption'),down)
        self.assertNotEqual(frame('Apple TV outage resolved').action,down.action)
        for title in ['Meridian 在苹果 App Store 短暂下架后恢复',
                      'Meridian is unavailable on the App Store',
                      'App Store listings are unavailable']:
            result = frame(title)
            self.assertTrue(result is None or not result.subject.startswith('services:'))
        self.assertEqual(frame('App Store 服务故障已恢复').action,'service-restoration')
        self.assertEqual(frame('Meridian is restored on App Store, Apple TV is still down'),down)
        events=self.m.cluster_articles([article_for(self.m,t,t) for t in ['Apple TV is down after a streaming outage','iCloud is down after a database outage']])
        self.assertEqual(len(events),2)
        events=self.m.cluster_articles([article_for(self.m,t,t) for t in ['Apple TV is down after a streaming outage','Apple TV suffers a streaming disruption']])
        self.assertEqual(len(events),1)

    def test_denied_finish_change_does_not_merge_with_disclosure(self):
        titles=["Apple's Home Hub color options surface in a code leak","Apple's Home Hub will not get new colors"]
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,t,t) for t in titles])),2)

    def test_repair_fees_require_own_device_and_affirmative_price(self):
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        from apple_news_core.event_identity import bind_replaceable_component_claims
        for fee in ['With AppleCare coverage, an iPad screen replacement costs $29.',
                    'Without AppleCare coverage, iPhone 18 screen replacement does not cost $29.',
                    'With AppleCare coverage, iPhone 19 screen replacement costs $29.',
                    'Samsung Galaxy screen replacement without insurance costs $29.',
                    "With AppleCare coverage, iPhone 18 screen replacement doesn't cost $29."]:
            title='Apple confirms iPhone 18 has a replaceable cover layer'
            evidence=ArticleEvidence('repair-test','MacRumors','https://example.com/repair',title,title,'news',
                (EvidenceUnit('design','p','The iPhone 18 cover layer is replaceable.','body',0),EvidenceUnit('fee','p',fee,'body',1)))
            claims=bind_replaceable_component_claims(evidence)
            self.assertEqual({c.action for c in claims},{'replaceable-cover-design'})
            self.assertTrue(all('fee' not in c.unit_ids for c in claims))

    def test_service_lists_and_restored_films_keep_their_actual_objects(self):
        titles=['Apple TV, Apple Music and App Store are down',
                'Apple Music, Apple TV and App Store are down']
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,t,t) for t in titles])),1)
        from apple_news_core.event_identity import build_event_identity,source_operation_frame,bind_replaceable_component_claims
        title='Apple TV adds a new selection of restored classic movies'
        lead='Apple TV has added a new selection of classic movies today.'
        self.assertEqual(source_operation_frame(title,lead,(),build_event_identity(title,lead)).action,'catalog-addition')
        from apple_news_core.models import ArticleEvidence,EvidenceUnit
        title='Apple confirms iPhone 18 cover layer is not replaceable'
        evidence=ArticleEvidence('negative','MacRumors','https://example.com/negative',title,title,'news',
            (EvidenceUnit('design','p',title,'body',0),))
        self.assertFalse(bind_replaceable_component_claims(evidence))

    def test_replaceable_part_is_not_an_employee_replacement(self):
        from apple_news_core.event_identity import organization_action_frame
        for text in [
            "Apple's vice president of hardware engineering revealed that the cover layer can be removed and replaced.",
            "AppleCare coverage allows the screen to be replaced for $29.",
            "苹果硬件工程负责人称内屏保护层可更换。",
        ]:
            self.assertIsNone(organization_action_frame(text,apple_owned=True))
        self.assertIsNotNone(organization_action_frame('Apple will replace AppleCare support employees with AI.',apple_owned=True))

    def test_cover_design_and_service_fee_are_distinct_source_actions(self):
        ids=['f398d63de155f81ae43e469a','fe2738dd42eda13fe641ea54','540800bd862ccf132af4a9ab','e49fd49fa66b2254ad6a2a39','c1d9cb9a5c8b0f7ee6d940a1']
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),2,[(e.title,e.category) for e in events])
        self.assertEqual({e.category for e in events},{'software_systems','hardware_products'})
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))
        self.assertEqual(set().union(*(self.source_ids(e) for e in events)),set(ids))
        self.assertTrue(all(a.bound_claim.action not in {'workforce-reduction','workforce-plan'} for e in events for a in e.articles if a.bound_claim))

if __name__ == '__main__':
    unittest.main()
