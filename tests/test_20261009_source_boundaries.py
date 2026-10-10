"""Source-local operations own their subject, release batch and reporting stage."""
from datetime import datetime, timezone
from pathlib import Path
import json
import unittest
from dataclasses import replace
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

GROUPS = {
    'phone_dimensions': ['006c29c0c61c9f4678ac59ed', '5e19c16fbee793f1034399c7', '4a2246be57c7929aec840aa6', 'b608203f614ae8d428da358c'],
    'carrier_bundle': ['041206ae838f022312cf7efc'],
    'home_setup': ['964a1f89652243d1807c8178'],
    'notebook_correction': ['127448fbfe8fd4ea89b7c88a', 'c10bfcf1b16f0d37fdfb45ba', 'b7d5fbf67db12be82dfa74d7', '1ddb8359fc788c8504aea97e', '7c41830527bf544a1ef5b151'],
    'tablet_refresh': ['de30642abefe37d796e87298', '313ecf64ceb95809ba2bb303', '73b1f2eb3dccd53be7ae5df3', 'a552534c89ad9ddbf24be7fc', 'dcff63deec4dcec94e04149e'],
    'market_report': ['8bd2acd6017c61c1a69041c3', 'c47d09ee2dd189a466291724', '3faa75e2c6a6eaa1080d1dba'],
    'update_prompt': ['3de8fc1025f1ba172d5551d7', '3ba8576e1bf04ad5a6ec13ef', '0b4bca039922e8988402288c'],
    'security_report': ['7ff16cc1e560b937ed4daf03', 'b7da6d8c8592cdc533339d23', '8bd7877218b75d9b217f9b71'],
    'submission': ['9b28948145e61306a8266639', 'b47220fa028a0155a96217bb'],
    'content_acquisition': ['b357168c348d964b4b906a2f', '167661afd591090a76c0c6a4', '111b1ce25b2bcb9d06770aff'],
}
GROUPS.update({
    'launch_plan': ['99d872595783a551d8f6fafd', 'fd6dfba4b7d6b823466aff13', 'b3ca03e5c734db0bee7c1467', '106cbcd0087a62b7084a40a4', 'aed4c35659561ccdc10ce5e1', '8061c307e4bc48fbeb337200', '95d74c3181664170fc293761'],
    'launch_confirmation': ['f99ecfa0850e2407744b3a23', 'abf73f0e34de687758e86140', '8f1c3fa4b95f8c0ce5727ead', 'de50e4ed2fa5d2076f90eb33', 'c077353a622e1c02e742d6b2', 'e439e960f0f8ede6f3f29b5e', '452778561b2870137f4a4b46'],
    'leadership_interview': ['44637b5f7c3edec94a45f0b2', '7722dcfe18312fb6339ea239', '08ee59d8878ef49f6d059fc5', 'f5bc71e4570388a9dc402a3a', '0f77d7ef39262d83c11e4411', 'dac9950d20bf5a77eac30c94', '5adac218ad7bffa39c95b062'],
})
ORG = ['2ff8cb36404627cb9c4d017b', '8c2858cd76db8bff04316488', 'dff63f34b77b63cdeb1d0a35', 'd62c5ad8c1b5e7907b51a8af', '90cc75ff51835ca8ca06a280']
LEGAL = ['72d0e3b04f9721ddd202b7aa', '096850b4c765267579ee3149', '3fd696b96d10edce9f0acb8f', '546f916265f073f059597da1']
SOFTWARE = {'carrier_bundle', 'home_setup', 'update_prompt', 'security_report', 'submission', 'content_acquisition'}


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261009_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 9, tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_local_reports_merge_only_their_operation(self):
        for name, ids in GROUPS.items():
            for order in (ids, ids[::-1]):
                with self.subTest(group=name, reverse=order != ids):
                    events, _ = self.cluster_sources(*order)
                    self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
                    self.assertEqual(self.source_ids(events[0]), set(ids))
                    self.assertEqual(events[0].category, 'software_systems' if name in SOFTWARE else 'hardware_products')
                    self.assertIn(events[0].relevance_tier, {'strong', 'ecosystem'})

    def test_host_phone_cannot_merge_home_setup_with_dimensions(self):
        ids = GROUPS['phone_dimensions'] + GROUPS['home_setup']
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                {frozenset(GROUPS['phone_dimensions']), frozenset(GROUPS['home_setup'])})

    def test_schedule_is_separate_from_specs_and_other_date(self):
        ids = GROUPS['launch_plan'] + GROUPS['launch_confirmation'] + GROUPS['notebook_correction'] + GROUPS['tablet_refresh']
        events, _ = self.cluster_sources(*ids)
        self.assertEqual({frozenset(self.source_ids(e)) for e in events}, {frozenset(GROUPS[k]) for k in ('launch_plan', 'launch_confirmation', 'notebook_correction', 'tablet_refresh')})

    def test_company_appointment_and_service_appointment_are_owned(self):
        events, _ = self.cluster_sources(*ORG)
        self.assertEqual(len(events), 2, [(e.title, self.source_ids(e)) for e in events])
        company = next(e for e in events if e.category == 'hardware_products')
        self.assertEqual(self.source_ids(company), set(ORG))
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        service = next(e for e in events if e.category == 'software_systems')
        self.assertTrue(any('Carson' in f or '卡森' in f for f in service.key_facts))
        self.assertFalse(any('Carson' in f or '卡森' in f for f in company.key_facts))

    def test_litigation_parties_keep_separate_claims(self):
        events, data = self.cluster_sources(*LEGAL)
        self.assertEqual(len(events), 3, [(e.title, e.category) for e in events])
        self.assertTrue(all(e.category == 'software_systems' and e.relevance_tier == 'strong' for e in events))
        self.assertEqual(set().union(*(self.source_ids(e) for e in events)), set(LEGAL))
        self.assertTrue(any('December 2' in f for d in data for f in d['key_facts'] + d.get('must_include_facts', [])))

    assert_consumed = prior.PureJsonBatchTests.assert_consumed

    def test_configuration_disclosure_keeps_material_source_details(self):
        _, data = self.cluster_sources(*GROUPS['phone_dimensions'])
        self.assert_consumed(data, '5e19c16fbee793f1034399c7', 2, 'VC')
        self.assert_consumed(data, '5e19c16fbee793f1034399c7', 4, 'C2', 'C1X')
        self.assert_consumed(data, '4a2246be57c7929aec840aa6', 1, '5.6mm', '5.2mm', '7%')
        self.assert_consumed(data, '4a2246be57c7929aec840aa6', 2, '3,149mAh', '11%')
        self.assert_consumed(data, '006c29c0c61c9f4678ac59ed', 1, '3149mAh')
        self.assert_consumed(data, '006c29c0c61c9f4678ac59ed', 1, '钛金属', '更小灵动岛')

    def test_functional_examples_and_limits_reach_consumption(self):
        sid = 'd7fdf39f714c1223ef63ae4d'
        events, data = self.cluster_sources(sid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assert_consumed(data, sid, 5, 'address', 'email', 'text messages', 'routing', 'voice')
        self.assert_consumed(data, sid, 11, "Apple doesn’t let you use your own photos")
        facts = [f['text'] for e in data for f in e['fact_sources']]
        self.assertFalse(any('for some reason' in f or 'isn’t known for' in f for f in facts))

    def test_unassigned_enumeration_context_has_review_span(self):
        sid = 'e439e960f0f8ede6f3f29b5e'
        events, _ = self.cluster_sources(*GROUPS['launch_confirmation'])
        review = prior.PureJsonBatchTests.replay_source_review(self, events[0], sid)
        unit = self.rows[sid]['evidence']['units'][9]
        self.assertIn('语音认证', unit['text'])
        self.assertTrue(any(item['unit_id'] == unit['unit_id']
            and item['text'] == unit['text'][item['start']:item['end']]
            and all(word in item['text'] for word in ('语音认证', '二次认证', '访客模式'))
            for item in review['unprocessed_evidence']))

        title = 'Apple Home adds guest access'
        lines = ['Apple Home adds guest access in its latest update.',
                 'A separate guest profile hides private account information.',
                 'Modes include Local, Shared, and Guest.',
                 'Additional modes include Solo, Family, and Away.']
        article = replace(article_for(self.m, title, lines[0]),
            evidence=self.evidence_for(title, lines))
        view = self.m.prepare_source_fact_view(article)
        context = [fact for fact in view.unprocessed if fact.text == lines[1]]
        self.assertEqual(len(context), 1)
        self.assertEqual(context[0].origins[0][3:], ('1', 0, len(lines[1])))
        self.assertNotIn(lines[1], [fact.text for fact in view.structured])

    def test_retrieval_facts_keep_scope_and_reject_hypothetical_commentary(self):
        title = 'Apple Maps adds saved destination search'
        paragraphs = [
            'Apple Maps now offers voice search for saved destinations.',
            'You can retrieve a saved destination from your account using only your voice.',
            'Apple Maps isn’t known for its themes, but Apple Maps doesn’t let you import a custom image for some reason.',
            'Perhaps Apple Maps could retrieve private requests to improve its business.',
            'Alexa retrieves household contacts from an independent account.',
            'It retrieves all contact addresses from that separate account.',
            'Apple Maps retrieves saved destinations from its own location history.',
            'Alexa is useful, and it retrieves household contacts from an independent account.',
            'Perhaps Apple Maps could be useful, and it could retrieve private messages from your email.',
        ]
        article = replace(article_for(self.m, title, paragraphs[0]),
            evidence=self.evidence_for(title, paragraphs))
        facts = self.m.source_supporting_facts(article, ())
        text = '\n'.join(fact.text for fact in facts)
        self.assertIn('using only your voice', text)
        self.assertIn('doesn’t let you import a custom image', text)
        self.assertIn('its own location history', text)
        for omitted in ('Perhaps', 'for some reason', 'isn’t known for',
                        'Alexa', 'all contact addresses', 'household contacts', 'private messages'):
            self.assertNotIn(omitted, text)

    def evidence_for(self, title, paragraphs):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit, PublicationEvidence, EmbeddedReference
        data = dict(self.rows[LEGAL[0]]['evidence'])
        data['title'] = data['discovery_title'] = title
        data['raw_lead'] = data['discovery_lead'] = paragraphs[0]
        data['content_form'] = 'news'
        prototype = EvidenceUnit(**data['units'][0])
        data['units'] = tuple(replace(prototype, unit_id=str(i), text=text, kind='p') for i, text in enumerate(paragraphs))
        data['publication_candidates'] = tuple(PublicationEvidence(**x) for x in data['publication_candidates'])
        data['embedded_references'] = tuple(EmbeddedReference(**x) for x in data['embedded_references'])
        return ArticleEvidence(**data)

    def test_launch_actor_negation_stage_and_date_boundaries(self):
        from apple_news_core.event_identity import source_dated_launch_frame
        cases = [
            ('Apple announces iOS 28 release for October 13', 'Apple announced iOS 28 will be released on October 13.'),
            ('Apple announces iPhone 19 repair program', 'Apple announced a free battery replacement program for iPhone 19.'),
            ('Apple launches new iPhone app', 'Apple launched a new app for creating invitations.'),
            ('Apple delays the iPad mini launch', 'Apple delayed the iPad mini launch until next year.'),
            ('Apple will not launch new iPads on October 27', 'Apple denied plans to launch new iPads on October 27.'),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                self.assertIsNone(source_dated_launch_frame(title, lead, ('Apple announced an event for October 13 to introduce its home products.',)))
        for day in (13, 27):
            confirmed = source_dated_launch_frame(f'Apple confirms event for October {day}, reports Bloomberg', f'Bloomberg reports Apple has confirmed its event for October {day}.', ())
            reported = source_dated_launch_frame(f'Apple reportedly plans event for October {day}', f'Apple is expected to hold a new product launch on October {day}.', ())
            self.assertEqual(confirmed.action, 'launch-date-confirmation')
            self.assertNotEqual(confirmed.action, reported.action)
            self.assertEqual(confirmed.period, reported.period)
        article = article_for(self.m, *cases[0])
        self.assertEqual(self.m.cluster_articles([article])[0].category, 'software_systems')
        phones = [article_for(self.m, f'Apple to launch iPhone {model} on October 13',
            f'Apple plans to launch iPhone {model} on October 13.') for model in (19, 20)]
        self.assertEqual(len(self.m.cluster_articles(phones)), 2)
        variants = [article_for(self.m, f'Apple to launch iPhone 19{suffix} on October 13',
            f'Apple plans to launch iPhone 19{suffix} on October 13.') for suffix in ('', ' Pro', ' Pro Max')]
        self.assertEqual(len(self.m.cluster_articles(variants)), 3)
        family = article_for(self.m, 'Apple to launch iPhone 19 series on October 13',
            'Apple plans to launch the iPhone 19 series on October 13.')
        self.assertEqual(len(self.m.cluster_articles([family, variants[1]])), 1)

    def test_appointments_require_affirmative_local_owner(self):
        from apple_news_core.event_identity import bind_role_appointment_claims
        from apple_news_core.event_matcher import identity_pair_decision
        title = 'Apple names new mergers and acquisitions chief'
        evidence = self.evidence_for(title, [
            'Apple appointed Alex Morgan as its new mergers and acquisitions chief.',
            'Apple denied reports that Carson Oliver was promoted to App Store vice president.',
            'Apple confirmed Carson Oliver will not be promoted to App Store vice president.',
            "Apple confirmed Carson Oliver won't be promoted to App Store vice president.",
            'Adrian Perica led mergers and acquisitions in 2020.',
        ])
        claims = bind_role_appointment_claims(evidence)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].unit_ids, ('0',))
        other = self.evidence_for(title, ['Apple appointed Jane Lee as its new mergers and acquisitions chief.'])
        self.assertEqual(identity_pair_decision(claims[0], bind_role_appointment_claims(other)[0]), 'conflict')

    def test_filing_speaker_history_and_bilingual_aliases(self):
        from apple_news_core.event_identity import bind_joint_litigation_claims
        title = 'Apple and Jon Prosser file new joint status report in iOS 26 trade secret lawsuit'
        evidence = self.evidence_for(title, [
            'Apple and defendant Jon Prosser filed a new joint status report in the iOS 26 trade secret case.',
            'Prosser says Apple wants to delay the trial, a claim Apple denies.',
            'Last year, Prosser said Apple had already received all documents.',
        ])
        claims = bind_joint_litigation_claims(evidence)
        self.assertEqual(len(claims), 1)
        self.assertTrue(claims[0].subject.endswith(':jon-prosser'))
        self.assertEqual(claims[0].evidence_spans, (('1', 0, len(evidence.units[1].text)),))
        nested = self.evidence_for(title, [evidence.units[0].text,
            'Prosser says that, while Apple wants more documents, he has fulfilled his obligations.'])
        claims = bind_joint_litigation_claims(nested)
        self.assertEqual(len(claims), 1)
        self.assertTrue(claims[0].subject.endswith(':jon-prosser'))
        self.assertEqual(claims[0].evidence_spans, (('1', 0, len(nested.units[1].text)),))
        coordinated = self.evidence_for(title, [evidence.units[0].text,
            'Prosser says Apple wants more documents and Apple seeks a delay.'])
        claims = bind_joint_litigation_claims(coordinated)
        self.assertEqual(len(claims), 1)
        self.assertTrue(claims[0].subject.endswith(':jon-prosser'))
        self.assertEqual(claims[0].evidence_spans, (('1', 0, len(coordinated.units[1].text)),))
        independent = self.evidence_for(title, [evidence.units[0].text,
            'Apple says discovery should continue, while Prosser says Apple wants to delay the trial.'])
        claims = bind_joint_litigation_claims(independent)
        self.assertEqual(len(claims), 2)
        self.assertTrue(claims[0].subject.endswith(':apple'))
        self.assertTrue(claims[1].subject.endswith(':jon-prosser'))
        self.assertEqual(independent.units[1].text[claims[1].evidence_spans[0][1]:],
            'Prosser says Apple wants to delay the trial.')
        chinese = self.evidence_for('iOS 26 商业秘密诉讼新进展', [
            '苹果与乔恩·普罗瑟（Jon Prosser）提交了新的联合状态报告，涉及 iOS 26 商业秘密案。',
            '苹果表示仍在等待取证材料。', '普罗瑟表示已经履行取证义务。'])
        claims = bind_joint_litigation_claims(chinese)
        self.assertEqual({c.subject.rsplit(':', 1)[-1] for c in claims}, {'apple', 'jon-prosser'})

    def test_interview_identity_and_report_freshness(self):
        from apple_news_core.event_identity import source_leadership_interview_frame
        old = source_leadership_interview_frame('Tim Cook discusses the CEO transition', 'A newly resurfaced interview with The Independent from last year discussed John Ternus at Apple.', ())
        self.assertEqual(old.tier, 'weak')
        current = source_leadership_interview_frame('Jane Miller discusses Apple leadership transition', 'Apple chairman Jane Miller gave an interview with The Observer on the leadership transition.', ())
        other = source_leadership_interview_frame('Jane Miller discusses Apple leadership transition', 'Apple chairman Jane Miller gave an interview with The Times on the leadership transition.', ())
        self.assertEqual(current.tier, 'strong')
        self.assertNotEqual(current.subject, other.subject)

    def test_source_continuations_require_the_same_owned_object(self):
        from apple_news_core.event_identity import bind_configuration_disclosure_claim, bind_connectivity_remedy_claims
        evidence = self.evidence_for('iPhone Air 3 rumored to be thinner with a larger battery', [
            'A leaker reports iPhone Air 3 will be 5.1mm thick with a higher-capacity battery.',
            'The iPhone 19 Pro will gain a new telephoto camera.',
            'Meanwhile, Apple is preparing a new iPad mini display.',
            'The display will use a different driver chip.',
        ])
        claim = bind_configuration_disclosure_claim(evidence)
        self.assertEqual(claim.unit_ids, ('0',))
        for comparison, expected in [
            ('Compared with this phone, iPhone 19 Pro will have a new telephoto camera.', ('0',)),
            ('This phone will have the same telephoto camera as iPhone 19 Pro.', ('0', '1', '2')),
        ]:
            with self.subTest(comparison=comparison):
                compared = self.evidence_for(evidence.title, [
                    evidence.raw_lead, comparison, 'The camera will use a larger sensor.',
                ])
                self.assertEqual(bind_configuration_disclosure_claim(compared).unit_ids, expected)
        carrier = self.evidence_for('Apple releases Verizon carrier settings update for iPhone 19', [
            'Apple released Verizon carrier settings update 90.1 for iPhone 19 to address cellular connectivity issues.',
            'Today’s release includes an Acme carrier bundle version 99.0 for iPhone 20.',
        ])
        claims = bind_connectivity_remedy_claims(carrier)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].unit_ids, ('0',))

    def test_os_compatibility_does_not_own_another_package_release(self):
        from apple_news_core.event_identity import is_os_release_announcement
        for title in ['Apple rolls out carrier update for iPhone 19 on iOS 28.2 beta',
                      'Developer releases camera plugin for macOS 29',
                      'Apple releases firmware for AirPods on iOS 28']:
            self.assertFalse(is_os_release_announcement(title))
        for title in ['Apple releases iOS 28.2 beta 3 with new Siri features', 'Apple seeds third public beta of macOS 29']:
            self.assertTrue(is_os_release_announcement(title))

    def test_personal_preference_does_not_own_the_favored_brand_action(self):
        from apple_news_core.event_identity import build_event_identity
        events, _ = self.cluster_sources('5092b9a712cc61a3e711b73f')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        cases = [
            ('苹果 CEO 最爱的汽车品牌，要推出新超跑了', '一家汽车制造商宣布将推出新跑车，苹果高管是该品牌的个人客户。'),
            ('苹果高管喜欢的餐厅开设新店', '这家餐厅宣布开设第二家门店。'),
            ("Apple CEO's favorite automaker unveils a new sports car", 'The automaker announced a new sports car. An Apple executive owns one of its older models.'),
            ("Apple executive Jane Miller's favourite cafe opens another location", 'The cafe opened a second location.'),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                identity = build_event_identity(title, lead)
                self.assertEqual(identity.scope, 'third-party-context')
                self.assertEqual(identity.action_owner, 'third-party')
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertEqual(events[0].relevance_tier, 'weak')
        for title, lead in [
            ('苹果 CEO 宣布新研发中心启用', '苹果今天宣布新的研发中心正式启用。'),
            ("Apple CEO's favorite iOS 28 Photos feature gains new privacy controls", 'Apple added new privacy controls to Photos in iOS 28.'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(build_event_identity(title, lead).scope, 'apple-direct')
                self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'strong')
        for title, lead in [
            ("Apple CEO's favorite feature gains new privacy controls", 'Apple added new privacy controls to Photos in iOS 28.'),
            ('苹果 CEO 最喜欢的功能新增隐私控制', '苹果为 iOS 28 照片功能新增隐私控制。'),
        ]:
            self.assertEqual(build_event_identity(title, lead).scope, 'apple-direct')
        self.assertEqual(build_event_identity(cases[0][0], 'Apple added new privacy controls to Photos in iOS 28.').scope, 'third-party-context')

    def test_reported_supply_is_not_retailer_buying_advice(self):
        events, _ = self.cluster_sources('076b5dc83bff51043c13e77b')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'hardware_products')
        from apple_news_core.event_identity import source_focused_report_frame
        title = 'iPhone 19 launch inventory will be limited'
        current = 'Sources report that iPhone 19 launch inventory will be limited by production constraints.'
        self.assertIsNotNone(source_focused_report_frame(title, current, ()))
        for lead in [
            'Last year sources reported that iPhone 19 inventory was limited.',
            'A retailer urges shoppers to buy iPhone 19 while its store inventory is limited.',
            'Sources report that iPhone 20 launch inventory will be limited by production constraints.',
            'Sources report that iPhone 20 inventory is low compared with iPhone 19.',
            'Sources report that iPhone 19 inventory will not be limited.',
            'Sources report that iPhone 19 will launch in September, while iPhone 20 inventory will be limited.',
            'Sources report that iPhone 19 inventory is no longer limited after production recovered.',
            'Sources report that iPhone 19 inventory was limited in 2025, but supply has since recovered.',
            'Sources report that iPhone 19 had limited inventory, but supply has now recovered.',
        ]:
            self.assertIsNone(source_focused_report_frame(title, lead, ()))

    def test_report_period_version_and_owner_boundaries(self):
        cases = [
            [('IDC reports Apple Mac shipments in Q3 2030', 'IDC reports worldwide PC shipments in Q3 2030 declined, including Apple Mac shipments.'),
             ('IDC reports Apple Mac shipments in Q4 2030', 'IDC reports worldwide PC shipments in Q4 2030 declined, including Apple Mac shipments.')],
            [('iPad mini 8 rumored to have a 60Hz OLED display', 'A leaker claims iPad mini 8 will have a 60Hz OLED display.'),
             ('iPad mini 9 rumored to have a 60Hz OLED display', 'A leaker claims iPad mini 9 will have a 60Hz OLED display.')],
            [('Apple TV acquires new crime series', 'Apple TV acquired global rights to Nightfall, a new crime drama.'),
             ('Apple TV acquires new crime series', 'Apple TV acquired global rights to Daybreak, a new crime drama.')],
        ]
        for pair in cases:
            for order in (pair, pair[::-1]):
                with self.subTest(rows=order):
                    self.assertEqual(len(self.m.cluster_articles([article_for(self.m, h, b) for h, b in order])), 2)

    def test_adjacent_model_and_operation_boundaries(self):
        rows = [
            ('iPhone Air 3 rumored to be thinner with a larger battery', 'A leaker reports iPhone Air 3 will be 5.1mm thick with a higher-capacity battery.'),
            ('iPhone Air 4 rumored to be thinner with a larger battery', 'A leaker reports iPhone Air 4 will be 5.1mm thick with a higher-capacity battery.'),
            ('iPhone Air 3 starts shipping', 'Apple announced iPhone Air 3 starts shipping today. Its body is 5.1mm thick.'),
            ('iPhone Air 3 thickness rumor denied', 'Apple denied the claim that iPhone Air 3 would have a thinner body.'),
        ]
        for order in (rows, rows[::-1]):
            self.assertEqual(len(self.m.cluster_articles([article_for(self.m, h, b) for h, b in order])), 4)


if __name__ == '__main__':
    unittest.main()
