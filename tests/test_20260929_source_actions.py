"""Source-owned actions and background boundaries from the September 29 batch."""
from datetime import datetime, timezone
from dataclasses import replace
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20260929_source_actions.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 9, 29, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_descriptive_apple_color_does_not_own_third_party_launch(self):
        events, _ = self.cluster_sources('d27555baa32d538a77f11457')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_editorial_selection_and_opinion_cannot_borrow_background_actions(self):
        for aid in ['dfce45ccc95615a83752c7f5', '8567a4d345243f7799cc8aea']:
            with self.subTest(aid=aid):
                events, _ = self.cluster_sources(aid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_software_action_owns_category_over_affected_hardware(self):
        for aid in ['27fff017815c3ddf6cb740d8', '447d6a9b5b4bfcee5b8b06ea', '26d08fa574869e0135ad08cf']:
            with self.subTest(aid=aid):
                events, _ = self.cluster_sources(aid)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong','software_systems')])

    def test_same_builtin_feature_discovery_joins_all_languages(self):
        ids = ['bacd790dbd3df6445af85070','0ef007a497e8c01d77fe8bbb','83b398dd12991adeb2bd1b0d','678094f38a16da7a71caa318','bdb38ea76d0c63849e7eab58']
        for order in [ids, ids[::-1]]:
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1, [e.title for e in events])
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong','software_systems'))
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertNotIn('mixed primary topic facets', events[0].merge_warnings)

    def test_current_project_owner_survives_competitor_and_cancelled_background(self):
        ids = ['710d5c909dde3b17dbc1243e','00cba6663e1c97b216c60838']
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong','hardware_products'))
        self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_primary_claim_warning_guard_preserves_conflicts_and_other_warnings(self):
        profiles = [self.m.article_reconciliation_profile(article_for(
            self.m, f'iPhone Duo StandBy code reveals new faces in iOS {version}',
            f'A developer discovered unannounced StandBy faces for iPhone Duo in iOS {version} code.',
            source='MacRumors')) for version in [28, 29]]
        self.assertFalse(self.m.profiles_share_primary_claim(profiles))
        self.assertFalse(self.m.profiles_share_primary_claim(profiles[:1]))
        articles = [self.source_articles(aid)[0] for aid in
                    ['bacd790dbd3df6445af85070', '678094f38a16da7a71caa318']]
        articles[1] = replace(articles[1], relevance_tier='weak')
        self.assertIn('mixed relevance tiers', self.m.event_merge_warnings(articles))

    def test_named_new_version_feature_is_not_evergreen_tutorial(self):
        events, _ = self.cluster_sources('330a77eaa1f9833e2a33f784')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong','software_systems')])

    def test_current_release_list_projects_version_and_platform_without_build_leakage(self):
        articles = self.source_articles('24c2505bb7b25fb50091cbb3')
        expected = [('iOS', '27.0.1','24A446'), ('iPadOS','27.0.1','24A446'),
                    ('macOS','27.0.1','26A434'), ('watchOS','27.0.1','24R365'),
                    ('visionOS','27.0.1','24M372'), ('iOS','26.7.1','23H30'),
                    ('iPadOS','26.7.1','23H30'), ('macOS','26.7.1','25G241'),
                    ('macOS','15.8.1','24H32')]
        self.assertEqual(len(articles), len(expected))
        for platform,version,build in expected:
            a = next(a for a in articles if a.title.lower().startswith(f'{platform} {version}'.lower()))
            self.assertIn(build, ' '.join(a.key_facts))
            self.assertTrue(a.projected_fact_spans or a.bound_claim)
            for other in {x[2] for x in expected} - {build}:
                self.assertNotIn(other, ' '.join(a.key_facts))
        events = self.m.cluster_articles(articles)
        self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'software_systems' for e in events))


    def test_financier_share_price_uses_apple_verdict_only_as_background(self):
        events, _ = self.cluster_sources('2631496c36db32777aae25dc')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        for title, lead in [
            ("Apple shares rise after patent verdict", "Apple shares rose 9% today following its patent court verdict."),
            ("Court orders Apple to pay patent damages", "A jury found Apple infringed Acme patents and ordered damages today."),
        ]:
            self.assertEqual(self.m.cluster_articles([article_for(self.m,title,lead,source='9to5Mac')])[0].relevance_tier,'strong')

    def test_multi_version_headline_is_projected_without_selecting_just_one_version(self):
        articles = self.source_articles('487f335029b57719e5f1091c')
        self.assertEqual(len(articles), 3)
        for version in ['27.0.1','26.7.1','15.8.1']:
            owned = [a for a in articles if version in a.title]
            self.assertEqual(len(owned), 1)
            p = self.m.article_reconciliation_profile(owned[0])
            self.assertIn(f'apple-os-release-wave:{version}:final:macos',p.event_keys)

    def test_color_reference_and_apple_owned_color_launch_have_different_owners(self):
        for title, lead, tier in [
            ('Acme buds 新增苹果绿配色', 'Acme 推出绿色蓝牙耳机，支持苹果手机。','weak'),
            ('Zen 耳机新增苹果红配色', 'Zen 发布红色耳机，苹果手机用户可使用。','weak'),
            ('苹果 AirPods 新增橙色款', '苹果今天发布橙色 AirPods 无线耳机。','strong'),
        ]:
            with self.subTest(title=title):
                e=self.m.cluster_articles([article_for(self.m,title,lead,source='IT之家')])[0]
                self.assertEqual(e.relevance_tier,tier)

    def test_discovery_preserves_capability_version_and_stage_boundaries(self):
        articles = [article_for(self.m,title,lead,source='MacRumors') for title, lead in [
            ('iOS 28 StandBy code reveals new faces', 'A developer discovered unannounced StandBy faces in iOS 28 code.'),
            ('iOS 29 StandBy code reveals new faces', 'A developer discovered unannounced StandBy faces in iOS 29 code.'),
            ('iOS 28 Lock Screen code reveals new layouts', 'A developer discovered unannounced Lock Screen layouts in iOS 28 code.'),
            ('iOS 28 StandBy new faces released', 'Apple released new StandBy faces in iOS 28 today.'),
        ]]
        for order in [articles,articles[::-1]]:
            self.assertEqual(len(self.m.cluster_articles(order)),4)
        for lead in [
            'A developer found no unannounced StandBy faces in iOS 28 code.',
            'A developer did not find any new StandBy faces in iOS 28 code.',
        ]:
            p=self.m.article_reconciliation_profile(article_for(self.m,'iOS 28 StandBy investigation',lead,source='MacRumors'))
            self.assertFalse(any('feature-code-discovery' in k for k in p.event_keys))

    def test_feature_tutorial_requires_current_version_and_first_party_capability(self):
        for title, lead in [
            ("macOS 28: How to use the new 'Notify Me' feature in Safari", "Safari's new 'Notify Me' feature lets users monitor websites, but it was introduced last year and is unchanged."),
            ("macOS 28: How to use the new 'Notify Me' feature in Acme", "Acme's new 'Notify Me' feature lets users monitor websites on a Mac."),
            ("How to use Safari notifications", "Safari lets users get website notifications. This is a settings guide."),
        ]:
            p=self.m.article_reconciliation_profile(article_for(self.m,title,lead,source='9to5Mac'))
            self.assertFalse(any('system-capability-report' in k for k in p.event_keys))
        first=article_for(self.m,"macOS 28: How to use the new 'Page Alert' feature in Safari", "Safari's new 'Page Alert' feature lets users monitor websites in macOS 28.",source='9to5Mac')
        second=replace(first,title=first.title.replace('28','29'),summary=first.summary.replace('28','29'),url=first.url+'other')
        self.assertEqual(len(self.m.cluster_articles([first,second])),2)

    def test_discovery_uses_its_own_sentence_and_mixed_language_model_boundary(self):
        english = article_for(self.m, 'iPhone Duo StandBy code reveals new faces',
            'A developer discovered unannounced StandBy faces for iPhone Duo.', source='MacRumors')
        for title in ['苹果iPhone Duo待机模式曝光新界面', '苹果iPhoneDuo待机模式曝光新界面']:
            chinese = article_for(self.m, title,
                '此前苹果已公布待机功能。开发者今天从测试代码发现尚未公布的新待机模式界面。', source='IT之家')
            events = self.m.cluster_articles([english, chinese])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].category, 'software_systems')
        for lead in ['开发者去年从代码发现了新待机界面，今天只是回顾旧发现。',
                     '开发者并未从代码发现新的待机界面。',
                     '开发者从代码发现这些待机界面是在去年，今天只是回顾。',
                     'A developer discovered unannounced StandBy faces last year in iOS 28 code.']:
            with self.subTest(lead=lead):
                old = article_for(self.m, 'iPhone Duo StandBy code investigation', lead, source='IT之家')
                p = self.m.article_reconciliation_profile(old)
                self.assertFalse(any('feature-code-discovery' in key for key in p.event_keys))
                self.assertEqual(len(self.m.cluster_articles([english, old])), 2)
        with_background = article_for(self.m, 'iPhone Duo StandBy code reveals new faces',
            'Apple announced StandBy last year, but a developer discovered unannounced faces today.', source='9to5Mac')
        self.assertEqual(len(self.m.cluster_articles([english, with_background])), 1)

    def test_release_inventory_does_not_promote_compatibility_or_old_lists(self):
        from apple_news_core.article_projector import project_current_release_inventory
        evidence=self.source_articles('24c2505bb7b25fb50091cbb3')[0].evidence
        for opening, heading in [
            ("Apple previously released these operating systems last year.","The new updates are:"),
            ("Apple's updates have arrived now.","Supported versions are:"),
            ("Apple has not released these updates.","The new updates are:"),
        ]:
            units=tuple(replace(u,text=heading) if u.kind!='li' else u for u in evidence.units)
            changed=replace(evidence,raw_lead=opening,units=units)
            self.assertEqual(project_current_release_inventory(evidence.title,opening,changed,30),[])

    def test_named_project_does_not_inherit_a_competitors_current_action(self):
        for title,lead in [
            ('Meta considering four headset concepts', 'Meta is working on a new project, N600, comparing its design to Apple Vision Pro.'),
            ('Apple considering four Vision Pro concepts', 'Apple had been considering a headset codenamed N600. That project was shelved last year.'),
        ]:
            p=self.m.article_reconciliation_profile(article_for(self.m,title,lead,source='MacRumors'))
            self.assertFalse(any(':project:n600:' in k for k in p.event_keys))

    def test_release_projection_does_not_promote_a_background_version(self):
        title='Apple releases iOS 28.0.1 for devices running iOS 28.0'
        summary='Apple released iOS 28.0.1 today to fix issues affecting iOS 28.0.'
        variants=self.m.compound_article_variants(title,summary,[summary])
        self.assertEqual(len(variants),1)
        self.assertEqual(variants[0][0],title)

    def test_multi_release_security_facts_keep_their_version_scope(self):
        articles=self.source_articles('487f335029b57719e5f1091c')
        by_version={v:next(a for a in articles if v in a.title) for v in ['27.0.1','26.7.1','15.8.1']}
        self.assertNotIn('CVE-2026-86950',' '.join(by_version['27.0.1'].key_facts))
        self.assertIn('no published CVE',' '.join(by_version['27.0.1'].key_facts))
        for version in ['26.7.1','15.8.1']:
            self.assertIn('CVE-2026-86950',' '.join(by_version[version].key_facts))
            self.assertNotIn('no published CVE',' '.join(by_version[version].key_facts))
            self.assertTrue(by_version[version].projected_fact_spans)

    def test_platform_version_does_not_erase_code_discovery_device_model(self):
        articles=[article_for(self.m,f'iOS 28 iPhone {model} StandBy code reveals new faces',
                  f'A developer discovered unannounced StandBy faces for iPhone {model} in iOS 28 code.',source='MacRumors') for model in ['18','19']]
        for order in [articles,articles[::-1]]:
            self.assertEqual(len(self.m.cluster_articles(order)),2)

    def test_runtime_first_party_app_cannot_own_a_third_party_feature(self):
        article=article_for(self.m,"macOS 28: How to use the new 'Notify Me' feature in Acme for Safari",
                "Acme's new 'Notify Me' feature lets users monitor websites in Safari.",source='9to5Mac')
        self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier,'weak')

    def test_project_code_belongs_to_its_sentence_actor(self):
        article=article_for(self.m,'Apple considering four Vision Pro concepts',
            'Apple is considering four designs for a new Vision Pro. Meta is working on a new project, N600, to rival it.',source='MacRumors')
        for lead in [article.summary,
            'Apple is considering four designs for a new Vision Pro, while Meta is working on a new project, N600, to rival it.',
            'To compete with Apple Vision Pro, Meta is working on a new project, N600.',
            "Meta's new headset, codenamed N600, competes with Apple Vision Pro.",
            '三星正在研发代号 N600 的新头显，与苹果 Vision Pro 竞争。',
            '苹果正在研发新头显，三星正在研发代号 N600 的竞争产品。',
            '苹果正在研发新头显, while Meta engineers are working on a new project, N600.',
            'Meta is developing a new headset. The company is working on a new project, N600, to rival Apple.',
            'Meta engineers are working on a new project, N600, to rival Apple Vision Pro.',
        ]:
            with self.subTest(lead=lead):
                article=replace(article,summary=lead,key_facts=[lead])
                profile=self.m.article_reconciliation_profile(article)
                self.assertFalse(any(':project:n600:' in k for k in profile.event_keys))
                self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier,'weak')

    def test_project_owner_survives_auxiliaries_and_team_subjects(self):
        for owner in ['Apple is currently', 'Apple engineers are actively', "Apple's Vision team is still"]:
            lead=f'{owner} working on a new project, N600, for Vision Pro.'
            profile=self.m.article_reconciliation_profile(article_for(self.m,'Apple considering four Vision Pro concepts',lead,source='MacRumors'))
            self.assertTrue(any(':project:n600:' in k for k in profile.event_keys),lead)


if __name__ == '__main__':
    unittest.main()
