"""Source-owned operations in mixed high-volume news coverage."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module
import test_p4_pure_json_batch as prior


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261021_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 21, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def ids(self, *prefixes):
        return [next(k for k in self.rows if k.startswith(p)) for p in prefixes]

    def test_current_platform_operation_owns_eligibility_and_category(self):
        for prefix, tier in (('8102', 'ecosystem'), ('aa649', 'ecosystem'),
                             ('0f6ea', 'strong'), ('c55c5', 'strong'), ('6e7d3', 'strong')):
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertEqual([(e.relevance_tier, e.category) for e in events],
                                 [(tier, 'software_systems')])

    def test_native_workload_observation_survives_project_framing(self):
        events, _ = self.cluster_sources(*self.ids('d2a269'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('strong', 'hardware_products')])
        text = ' '.join(events[0].articles[0].key_facts)
        for part in ('90', 'M4 MacBook Air', 'Metal 4', '32 至 59'):
            self.assertIn(part, text)

    def test_non_numeric_qualifications_remain_visible_for_review(self):
        events, _ = self.cluster_sources(*self.ids('d5a550'))
        pending = events[0].fact_plan.unprocessed
        requirements = [f for f in pending if 'minimum qualification' in f.text]
        self.assertEqual(len(requirements), 1)
        self.assertIn('preferred qualifications', requirements[0].text)
        self.assertIn('generative AI', requirements[0].text)
        self.assertTrue(all(origin[2].startswith('d5a550') for origin in requirements[0].origins))

    def test_qualification_review_keeps_local_context_without_assigning_it(self):
        from dataclasses import replace
        article = self.source_articles(self.ids('d5a550')[0])[0]
        unit = next(u for u in article.evidence.units if 'minimum qualification' in u.text)
        for text in ('Another employer lists a certification as a minimum qualification.',
                     '此前另一家公司把无线研究经验列为最低任职资格，相关论文属于优先条件。'):
            evidence = replace(article.evidence, units=(replace(unit, text=text),))
            facts, pending = self.m.prepare_source_condition_evidence(replace(article, evidence=evidence))
            self.assertFalse(facts)
            self.assertTrue(any(f.text == text for f in pending))
            for kind, container in (('h2', ''), ('p', 'caption')):
                other = replace(evidence, units=(replace(unit, text=text, kind=kind, container_id=container),))
                _, excluded = self.m.prepare_source_condition_evidence(replace(article, evidence=other))
                self.assertFalse(any(f.text == text for f in excluded))
        for text in ('Read more about the minimum qualifications for this position.',
                     'Image credit: minimum qualifications listed on Apple Jobs.',
                     'Learn more about the preferred qualifications for this position.'):
            evidence = replace(article.evidence, units=(replace(unit, text=text),))
            _, pending = self.m.prepare_source_condition_evidence(replace(article, evidence=evidence))
            self.assertFalse(any(f.text == text for f in pending))

    def test_natural_frame_rate_requires_current_apple_configuration_and_execution(self):
        from apple_news_core.event_identity import source_device_workload_measure, build_event_identity
        title = '开源项目运行《山谷》，M7 MacBook Air 稳定74帧'
        lead = '新项目将《山谷》静态重编译为原生程序。在基础款M7 MacBook Air上，这款游戏稳定跑到74帧。'
        def measure(t, text):
            return source_device_workload_measure(t, text, (), build_event_identity(t, text))
        self.assertIsNotNone(measure(title, lead))
        self.assertNotEqual(measure(title, lead), measure(title.replace('M7', 'M8'), lead.replace('M7', 'M8')))
        self.assertNotEqual(measure(title, '甲实验室报告：' + lead),
                            measure(title, '乙实验室报告：' + lead))
        for bad in (lead.replace('稳定跑到', '预计跑到'), '去年，' + lead,
                    lead.replace('稳定跑到', '尚未跑到'), lead.replace('稳定跑到', '计划稳定跑到'),
                    lead.replace('稳定跑到74帧', '仅支持4K输出'),
                    lead.replace('M7 MacBook Air', 'RTX 6090 PC'),
                    lead.replace('上，这款游戏', '与桌面平台对比，RTX 6090'),
                    lead.replace('在基础款', '作为对比，在基础款')):
            with self.subTest(bad=bad):
                self.assertIsNone(measure(title, bad))

    def test_one_version_feature_report_keeps_same_action_across_languages(self):
        ids = self.ids('32db9', '4197a')
        for order in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual((events[0].relevance_tier, events[0].category),
                             ('strong', 'software_systems'))

    def test_current_hardware_actions_survive_report_wording(self):
        for prefix in ('a5d2c', '9e8de', '68ae73', '19e07'):
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'strong' and e.category == 'hardware_products'
                                    for e in events))

    def test_embedded_current_os_support_is_not_lost_at_admission(self):
        events, _ = self.cluster_sources(*self.ids('04380'))
        self.assertTrue(any(e.relevance_tier == 'ecosystem' and e.category == 'software_systems'
                            for e in events))

    def test_other_companies_transaction_cannot_borrow_apple_patent_ownership(self):
        events, _ = self.cluster_sources(*self.ids('70a923'))
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_acquisition_strategy_recap_does_not_supply_current_transaction(self):
        from test_relevance_rules import article_for
        events, _ = self.cluster_sources(*self.ids('85e2'))
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        for title, lead in (
            ('Why Apple keeps acquiring startups',
             'Apple acquires companies every year. The author argues that these deals may improve its services.'),
            ('苹果持续收购公司的战略目的',
             '本文分析苹果近年来的多笔交易，作者认为它们可能增强服务生态。'),
        ):
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertEqual(events[0].relevance_tier, 'weak')

    def test_concrete_transaction_disclosures_survive_editorial_context(self):
        from test_relevance_rules import article_for
        for title, lead in (
            ('Apple acquired Acme last year, newly published filing reveals',
             'A filing published today reveals Apple acquired Acme last year. The deal may improve its services.'),
            ('Apple in talks to acquire Acme',
             'Apple and Acme are negotiating an acquisition, according to a new report.'),
            ('Apple acquires Acme assets',
             'Apple acquired assets from Acme today. The deal follows earlier acquisitions.'),
            ('Why Apple keeps acquiring startups',
             'Apple acquired Acme today, a newly published filing confirms. The author discusses its strategy.'),
            ('Why Apple keeps acquiring startups',
             'Apple is in talks to acquire Acme, according to a new report.'),
            ('Why Apple keeps acquiring startups',
             'Apple and Acme are negotiating an acquisition, according to a new report.'),
            ('Why Apple keeps acquiring startups',
             'Apple is in talks to acquire Acme, while the claim about a separate deal is false.'),
            ('Why Apple keeps acquiring startups',
             'Apple and Acme are negotiating an acquisition, while the claim about a separate deal is false.'),
            ('Why Apple keeps acquiring startups',
             'Last year, Apple considered another deal, but Apple is in talks to acquire Acme now.'),
        ):
            with self.subTest(title=title):
                events = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertEqual(events[0].relevance_tier, 'strong')
        from apple_news_core.event_identity import source_acquisition_frame
        title = 'Why Apple keeps acquiring startups'
        lead = 'Apple is in talks to acquire Acme, according to a new report.'
        self.assertEqual(source_acquisition_frame(title, lead).action, 'acquisition-negotiation')
        for bad in ('Last year, ' + lead, lead.replace('is in talks', 'is not in talks'),
                    lead.replace('Apple is', 'Meta is'),
                    'The claim that Apple and Acme are negotiating an acquisition is false.',
                    'It is not true that Apple is in talks to acquire Acme.',
                    'Apple denies it is in talks to acquire Acme.'):
            with self.subTest(lead=bad):
                events = self.m.cluster_articles([article_for(self.m, title, bad)])
                self.assertEqual(events[0].relevance_tier, 'weak')

    def test_component_purchases_do_not_become_company_negotiations(self):
        from apple_news_core.event_identity import source_acquisition_frame
        for component in ('Memory Chips', 'Display Panels', 'Camera Sensors',
                          'DRAM Chips', 'OLED Display Panels', 'Advanced Camera Sensors'):
            for verb in ('buy', 'acquire'):
                with self.subTest(component=component, verb=verb):
                    self.assertIsNone(source_acquisition_frame(
                        f'Apple in Talks to {verb.title()} {component} From Acme',
                        f'Apple is in talks to {verb} {component.lower()} from Acme for its devices.'))
        for company in ('Acme', 'Memory Labs', 'Acme Semiconductor'):
            with self.subTest(company=company):
                frame = source_acquisition_frame(
                    f'Apple in talks to buy {company} from ParentCo',
                    f'Apple is in talks to buy {company} from ParentCo.')
                self.assertEqual(frame.action, 'acquisition-negotiation')
                self.assertEqual(frame.subject, 'apple-acquisition:' + company.lower().replace(' ', '-'))
        for company, deal in (('Acme Sensors', 'an acquisition'), ('Acme Chips', 'a merger')):
            with self.subTest(company=company):
                frame = source_acquisition_frame('Why Apple keeps acquiring startups',
                    f'Apple and {company} are negotiating {deal}, according to a new report.')
                self.assertEqual(frame.action, 'acquisition-negotiation')
                self.assertEqual(frame.subject, 'apple-acquisition:' + company.lower().replace(' ', '-'))

    def test_self_service_parts_are_one_store_extension_not_device_roadmaps(self):
        ids = self.ids('a5dd3', 'e2d1d5', '3072a', '5a9b0', '8bbf40')
        for order in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_open_consultation_and_company_response_match_existing_actions(self):
        ids = self.ids('04499a', '1551d', 'e413a')
        for order in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(self.source_ids(e) == set(ids) for e in events))
            self.assertTrue(all(e.category == 'software_systems' for e in events))

    def test_chinese_consultation_keeps_owner_stage_and_deadline(self):
        from apple_news_core.event_identity import bind_regulatory_access_consultation
        title = '英国竞争与市场管理局讨论 Apple Pay 竞争者接入费用'
        proposal = '英国竞争与市场管理局（CMA）提出新方案，计划降低 iPhone NFC 接入费用。'
        stage = '这仍是公开征询意见的提案，并非已生效的新规。'
        end = '公众咨询将于2027年12月18日结束。'
        claims = bind_regulatory_access_consultation(self.evidence(title, proposal + stage, end))
        self.assertTrue(claims)
        self.assertTrue(any(q[1:3] == ('consultation-day', '18') for c in claims for q in c.qualifiers))
        for other in (proposal.replace('提出', '去年提出') + stage,
                      proposal.replace('英国竞争与市场管理局（CMA）', '美国联邦通信委员会（FCC）') + stage,
                      proposal + '另一份FCC方案涉及不同服务。' + stage,
                      proposal + '文件回顾早期阶段：去年，' + stage + '如今已经结束。',
                      proposal + stage.replace('仍是公开征询', '尚未公开征询')):
            with self.subTest(text=other):
                self.assert_consultation_unresolved(self.evidence(title, other, end))

    def assert_consultation_unresolved(self, evidence):
        from apple_news_core.event_identity import bind_regulatory_access_consultation
        from apple_news_core.event_reconciler import claim_eligibility
        claims = bind_regulatory_access_consultation(evidence)
        self.assertTrue(claims)
        for claim in claims:
            self.assertEqual(claim.report_role, 'unresolved')
            self.assertFalse(claim.subject)
            self.assertEqual((claim_eligibility(claim).tier, claim.category), ('', 'software_systems'))

    def test_unresolved_access_report_cannot_fall_back_to_hardware_specs(self):
        title = '英国提议要求苹果开放 iPhone 非接触支付技术'
        lead = ('英国竞争与市场管理局讨论 iPhone NFC 安全芯片。'
                '公众咨询的主体及阶段尚未明确，报道显示该芯片保存支付凭证。')
        evidence = self.evidence(title, lead)
        article = self.m.Article('Test', evidence.url, title, lead, [lead], '',
            datetime(2026, 10, 21, tzinfo=timezone.utc), '', '', 'detail', set(), evidence=evidence)
        profile = self.m.article_reconciliation_profile(article)
        self.assertIsNotNone(profile.bound_claim)
        self.assertEqual(profile.relevance_tier, '')
        self.assertEqual(profile.category_hint, 'software_systems')
        self.assertTrue(profile.review_reasons)
        from apple_news_core.event_identity import bind_regulatory_access_consultation
        title = 'iPhone 22 NFC安全芯片规格曝光'
        lead = '报告显示，iPhone 22采用全新的NFC安全芯片，存储容量提高一倍。'
        history = '此前英国竞争与市场管理局（CMA）就Apple Pay接入方案进行公众咨询。'
        evidence = self.evidence(title, lead, history)
        self.assertFalse(bind_regulatory_access_consultation(evidence))
        article = self.m.Article('Test', evidence.url, title, lead, [lead, history], '',
            datetime(2026, 10, 21, tzinfo=timezone.utc), '', '', 'detail', set(), evidence=evidence)
        profile = self.m.article_reconciliation_profile(article)
        self.assertEqual((profile.relevance_tier, profile.category_hint), ('strong', 'hardware_products'))

    def test_open_consultation_continuation_keeps_local_actor_and_tense(self):
        from apple_news_core.event_identity import bind_regulatory_access_consultation
        title = 'CMA discusses Apple Pay NFC access'
        text = ('The CMA said its evidence did not suggest either approach was insecure. '
                'The proposals are open for consultation until November 17, 2026.')
        proposal = 'The CMA has proposed changes to Apple Pay NFC access.'
        self.assertTrue(any(c.action == 'consultation' for c in
                            bind_regulatory_access_consultation(self.evidence(title, proposal, text))))
        self.assert_consultation_unresolved(self.evidence(title, text))
        self.assert_consultation_unresolved(self.evidence(title,
            'The CMA proposed changes to Apple Pay NFC access last year.', text))
        for other in (text.replace('The CMA', 'The FCC'),
                      'The CMA discussed the FCC proposals on Apple Pay NFC access. '
                      'The proposals are open for consultation until November 17, 2026.',
                      'The CMA said its evidence showed that the FCC proposals on Apple Pay NFC access were secure. '
                      'The proposals are open for consultation until November 17, 2026.',
                      text.replace('are open', 'were previously open'),
                      text.replace('are open', 'may be open')):
            with self.subTest(text=other):
                evidence = self.evidence(title, proposal, other)
                self.assert_consultation_unresolved(evidence)

    def test_current_patent_request_keeps_physical_object(self):
        events, _ = self.cluster_sources(*self.ids('8993a', 'fbba4'))
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_same_first_party_exhibition_has_one_owner(self):
        ids = self.ids('a31a5', '8a5e4')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_current_job_listing_and_interview_survive_candidate_admission(self):
        for prefix in ('d5a55', 'e9ffc', '223826'):
            with self.subTest(source=prefix):
                events, _ = self.cluster_sources(*self.ids(prefix))
                self.assertTrue(any(e.relevance_tier == 'strong' and e.category == 'hardware_products'
                                    for e in events))

    def test_explicit_partnership_batch_keeps_same_program_update_together(self):
        ids = self.ids('1cde7', '4c5c7', '669e4', '753d2', '8bf50', '8c3ac', 'a2a81')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_regulator_consultation_and_current_response_keep_distinct_actors(self):
        ids = self.ids('1551d', 'feaff', '7847c')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertEqual(self.source_ids(event), set(ids))
            self.assertEqual((event.relevance_tier, event.category), ('strong', 'software_systems'))

    def evidence(self, title, *paragraphs):
        return self.m.capture_article_title_evidence('Test', 'https://example.test/report', title,
                                                    paragraphs[0], tuple(paragraphs))

    def test_delivery_tracking_keeps_its_observed_channel_waits(self):
        events, payload = self.cluster_sources(*self.ids('35b653'))
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('strong', 'hardware_products')])
        article = events[0].articles[0]
        self.assertEqual(article.bound_claim.action, 'delivery-wait-report')
        text = ' '.join(article.key_facts)
        for value in ('BofA', '82天', '102天', '50天'):
            self.assertIn(value, text)
        self.assertNotIn('起拍价', text)
        ids = self.ids('35b653', '9e8de')
        for order in (ids, list(reversed(ids))):
            grouped, _ = self.cluster_sources(*order)
            self.assertEqual(len(grouped), 2)
            self.assertEqual({frozenset(self.source_ids(e)) for e in grouped},
                             {frozenset({sid}) for sid in ids})

    def test_wait_report_needs_current_owned_observation_and_not_just_matching_numbers(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_delivery_wait_report
        from apple_news_core.event_matcher import identity_pair_decision
        title = 'iPhone 22 delivery wait times average 64 days'
        observed = ('Acme Bank tracked Apple store and carrier orders and found that iPhone 22 '
                    'delivery wait times average 64 days, with 80 days at Apple and 40 at carriers.')
        claim = bind_delivery_wait_report(self.evidence(title, observed))
        self.assertIsNotNone(claim)
        self.assertEqual(identity_pair_decision(claim, replace(claim, article_id='copy')), 'match')
        body_only = self.m.capture_article_title_evidence('Test', 'https://example.test/copied-report',
            title, 'New tracking results were published today.', (observed,))
        copied = bind_delivery_wait_report(body_only)
        self.assertEqual(identity_pair_decision(claim, copied), 'match')
        self.assertEqual(len(claim.evidence_spans), 2)
        self.assertEqual(len(copied.evidence_spans), 1)
        other = replace(bind_delivery_wait_report(self.evidence(title, observed.replace('Acme', 'Birch'))),
                        article_id='another-report')
        self.assertNotEqual(identity_pair_decision(claim, other), 'match')
        for text in ('Last year, ' + observed, 'Forecast: ' + observed,
                     observed.replace('found that', 'did not find that'),
                     observed.replace('iPhone 22', 'iPhone 21'),
                     'Analysts predict iPhone 22 delivery wait times will average 64 days.',
                     '美国银行追踪苹果官网及运营商订单后预计，iPhone 22的平均交付等待时间为64天。'):
            with self.subTest(text=text):
                self.assertIsNone(bind_delivery_wait_report(self.evidence(title, text)))
        self.assertIsNone(bind_delivery_wait_report(self.evidence(
            '苹果对iPhone 22限购两台：交付等待时间拉长',
            '苹果今日宣布对iPhone 22限购两台。', observed)))

    def test_platform_owner_cannot_be_borrowed_by_an_ordinary_app(self):
        from apple_news_core.event_identity import bind_interoperability_report
        evidence = self.evidence('Android 17 上第三方 App 今日更新',
            'Android 17 上的第三方 App 今日发布更新。',
            '该 App now supports iPhone interconnection，提供消息相互流转。')
        self.assertIsNone(bind_interoperability_report(evidence))
        self.assertIsNone(bind_interoperability_report(self.evidence('Linux 7.4 released',
            'Linux 7.4 kernel was released today.',
            'The Syncthing app now supports iPhone interconnection through its own server.')))
        for text in ('此前 Linux 7.4 首次实现了对苹果 M4 的启动支持。',
                     'Linux 7.4 未新增苹果 M4 的启动支持。'):
            self.assertIsNone(bind_interoperability_report(self.evidence('Linux 7.4 发布',
                'Linux 7.4 稳定内核今天发布。', text)))

    def test_historical_models_and_partners_do_not_change_current_batch(self):
        from apple_news_core.event_identity import bind_current_program_operation, bind_manufacturing_partnership_batch
        current = self.evidence('Apple now sells repair parts for iPhone 19 Pro',
            'Apple now sells parts for iPhone 19 Pro through its Self Service Repair Store.',
            'Mac mini was added last year.')
        self.assertEqual(bind_current_program_operation(current).object, 'iphone-19-pro')
        paragraph = ('Apple today announced new and expanded partnerships through its American Manufacturing Program '
                     'with Aster Company and Birch Electronics for iPhone 19 Pro materials.')
        base = self.evidence('Apple announces new American Manufacturing Program partners', paragraph)
        historical = self.evidence(base.title, paragraph,
            'Last year, Apple partnered with Other Technologies for iPhone 17 Pro components.')
        self.assertEqual(bind_manufacturing_partnership_batch(base).object,
                         bind_manufacturing_partnership_batch(historical).object)
        existing = self.evidence(base.title, paragraph,
            'Existing partner Other Technologies continues to supply iPhone 17 Pro parts.')
        self.assertEqual(bind_manufacturing_partnership_batch(base).object,
                         bind_manufacturing_partnership_batch(existing).object)

    def test_withdrawn_consultation_and_historical_response_keep_their_stage(self):
        from apple_news_core.event_identity import bind_regulatory_access_consultation
        withdrawn = self.evidence('CMA withdraws Apple Pay NFC consultation',
            'The CMA has withdrawn its consultation on Apple Pay NFC access.')
        self.assertFalse(any(c.action == 'consultation' for c in bind_regulatory_access_consultation(withdrawn)))
        current = self.evidence('CMA opens Apple Pay NFC consultation',
            'The CMA has opened a public consultation on Apple Pay NFC access.',
            'Apple has told reporters last year that it rejected the old proposal.')
        self.assertFalse(any(c.action == 'company-response' for c in bind_regulatory_access_consultation(current)))

    def test_mac_repair_generations_are_not_interchangeable(self):
        from apple_news_core.event_identity import bind_current_program_operation
        from apple_news_core.event_matcher import identity_pair_decision
        claims = [bind_current_program_operation(self.evidence(
            f'Apple now sells repair parts for M{generation} Mac mini',
            f'Apple now sells parts for M{generation} Mac mini through its Self Service Repair Store.'))
            for generation in (6, 7)]
        self.assertEqual(identity_pair_decision(*claims), 'conflict')

    def test_current_kernel_cannot_borrow_another_versions_support(self):
        from apple_news_core.event_identity import bind_interoperability_report
        e = self.evidence('Linux 7.4 发布', 'Linux 7.4 稳定内核今天发布。',
                          'Linux 7.2 首次实现了对苹果 M4 的启动支持。')
        self.assertIsNone(bind_interoperability_report(e))

    def test_historical_interview_quote_does_not_establish_current_policy(self):
        from apple_news_core.event_identity import bind_leadership_report
        e = self.evidence('John Ternus discusses design teams',
            'Apple CEO John Ternus gave a new interview with TIME.',
            'John Ternus says that at Apple “design teams were much smaller years ago”.',
            'Design teams were much smaller years ago.')
        claim = bind_leadership_report(e)
        self.assertIsNotNone(claim)
        self.assertNotEqual(claim.report_role, 'independent')

    def test_unrelated_physical_patent_cannot_change_software_case(self):
        from apple_news_core.event_identity import source_patent_challenge_frame
        frame = source_patent_challenge_frame('Northstar asks for more after Apple patent verdict',
            'Northstar has asked a judge for additional damages from Apple in its App Store billing software patent case.',
            ('An unrelated case against Apple concerns haptic mechanisms and patents.',))
        self.assertNotEqual(frame.category, 'hardware_products')

    def test_missing_patent_object_preserves_eligibility_with_category_review(self):
        events, _ = self.cluster_sources(*self.ids('8993a'))
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertTrue(any('category' in reason.lower() for reason in events[0].merge_warnings))

    def test_current_announcement_inside_roundup_has_local_facts(self):
        events, _ = self.cluster_sources(*self.ids('738260'))
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        self.assertTrue(any('10 月 28' in fact for a in events[0].articles for fact in a.key_facts))
        self.assertFalse(any('A20 Pro' in fact for a in events[0].articles for fact in a.key_facts))

    def test_joint_top_two_ranking_does_not_assign_joint_share_to_apple(self):
        ids = self.ids('0c979', '5c325')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_physical_observation_does_not_borrow_historical_symptom(self):
        ids = self.ids('68ae73', 'bfc236', 'f6d913')
        for order in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
            self.assertEqual(sorted(len(self.source_ids(e)) for e in events), [1, 2])

    def test_distinct_consultation_deadlines_do_not_merge(self):
        from apple_news_core.event_identity import bind_regulatory_access_consultation
        from apple_news_core.event_matcher import identity_pair_decision
        claims = [bind_regulatory_access_consultation(self.evidence('CMA opens Apple Pay NFC consultation',
            'The CMA has opened a public consultation on Apple Pay NFC access.',
            f'The deadline for public comments is November {day}, 2026.'))[0] for day in (5, 20)]
        self.assertEqual(identity_pair_decision(*claims), 'conflict')

    def test_local_event_cannot_borrow_history_or_other_inviter(self):
        from apple_news_core.event_identity import bind_media_invitation
        old = self.evidence('Product roundup',
            'Apple announced a new product event for October 28 last year.')
        self.assertIsNone(bind_media_invitation(old))
        current = self.evidence('Product roundup',
            'Apple announced a new product event for October 28.',
            'Samsung invited selected media to its October 29 launch event.')
        claim = bind_media_invitation(current)
        self.assertIsNotNone(claim)
        units = {u.unit_id: u for u in current.units}
        self.assertFalse(any('Samsung' in units[k].text[a:b] for k, a, b in claim.evidence_spans))

    def test_software_wrapper_leaves_unmigrated_versioned_operation_with_its_owner(self):
        from apple_news_core.event_identity import bind_device_capability_inventory, source_software_capability_frame
        frames = []
        for version in ('27.2', '27.3'):
            title = f'audioOS {version} code reveals HomePod surround sound system'
            lead = f'There are code references in audioOS {version} for new features of the HomePod surround sound system.'
            frames.append(source_software_capability_frame(title, lead, (lead,)))
            self.assertIsNone(bind_device_capability_inventory(self.evidence(title, lead)))
        self.assertNotEqual(frames[0].model_generation, frames[1].model_generation)

    def test_translated_job_reports_keep_role_and_generation(self):
        ids = self.ids('07474', '68225', 'd5a55')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_newly_entered_translations_keep_the_existing_source_action(self):
        for prefixes, category in ((('6e7d3', '0db201'), 'software_systems'),
                                   (('a31a5', '8a5e4', '81f02', 'f97ce'), 'hardware_products')):
            ids = self.ids(*prefixes)
            for order in (ids, list(reversed(ids))):
                events, _ = self.cluster_sources(*order)
                self.assertEqual(len(events), 1)
                self.assertEqual(self.source_ids(events[0]), set(ids))
                self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', category))

    def test_newly_entered_retail_commentary_and_app_do_not_borrow_apple_owner(self):
        for sid in self.ids('ead8f6', 'a2552', '4f146'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
                for article in events[0].articles:
                    profile = self.m.article_reconciliation_profile(article)
                    self.assertFalse(profile.trusted_direct_action)
                    if sid.startswith(('ead8f6', '4f146')):
                        self.assertEqual(profile.hard_boundary, 'source-local-third-party-action')

    def test_hardware_specification_needs_the_reported_generation(self):
        title = 'iPhone 19 design leaked'
        self.assertFalse(self.m.is_direct_iphone_hardware_spec_rumor_story(title,
            'Readers discussed its appearance. For comparison, iPhone 17 Pro has a different camera.'))
        self.assertFalse(self.m.is_direct_iphone_hardware_spec_rumor_story(title,
            'Readers discussed its appearance. For comparison, iPhone 17 Pro was released last year. Its camera uses a fixed aperture.'))
        self.assertTrue(self.m.is_direct_iphone_hardware_spec_rumor_story(title,
            'A report reveals that iPhone 19 uses a variable aperture camera. For comparison, iPhone 17 Pro used a fixed aperture.'))

    def test_installer_form_does_not_exclude_new_system_support(self):
        from apple_news_core.event_identity import is_third_party_app_action_on_apple_platform
        self.assertFalse(is_third_party_app_action_on_apple_platform(
            'Linux comes to Apple Silicon Macs with a new unofficial installer',
            'An independent project called BridgeLinux provides first-time Linux support for Apple silicon M4, including new GPU drivers and hardware acceleration.',
            named_only=True))
        title = 'Linux comes to Apple Silicon Macs with a new unofficial installer'
        lead = ('An independent project called BridgeLinux provides first-time Linux support for '
                'Apple silicon M4, including new GPU drivers and hardware acceleration.')
        for background in (
            'Previously, a different installer installed existing runtime software on older Macs.',
            'OtherProject installer installs existing runtime software on older Macs.',
            'BridgeLinux previously used an installer. Its automated setup installs existing runtime software.',
        ):
            with self.subTest(background=background):
                self.assertFalse(is_third_party_app_action_on_apple_platform(
                    title, lead, named_only=True, passages=(background,)))

    def test_internal_vacancy_keeps_job_ownership_without_staff_dispatch(self):
        from apple_news_core.event_identity import source_owned_organization_frame
        frame = source_owned_organization_frame('苹果内部招聘新的工程师职位',
            '苹果内部招聘一名 7G 蜂窝调制解调器系统工程师，该职位面向内部员工开放申请。')
        self.assertIsNotNone(frame)
        self.assertEqual(frame.action, 'job-opening')
        self.assertIsNone(source_owned_organization_frame('苹果招募发布会支援人员',
            '苹果面向零售员工开启内部抽签，入选员工参与发布会现场支援。'))
        title = 'Apple is hiring a firmware engineer'
        lead = 'Apple is hiring a firmware engineer who will develop cellular software.'
        base = source_owned_organization_frame(title, lead)
        for tail in ('Previously Apple hired a 6G cellular modem systems engineer.',
                     'Apple is hiring a 6G cellular modem systems engineer for another role.'):
            self.assertEqual(source_owned_organization_frame(title, lead + ' ' + tail).subject, base.subject)

    def test_cooperative_measurement_needs_current_tested_device_and_result(self):
        from apple_news_core.event_identity import source_current_report_frame
        title = 'iPhone 19 Pro Max 外接 MacBook Pro 运行 AI 模型'
        lead = ('开发者通过自制软件将 iPhone 19 Pro Max 与 M6 Pro MacBook Pro 连接，运行 Qwen5.0-32B 模型。'
                '实验显示，预填充性能提升 42%。')
        frame = source_current_report_frame(title, lead, ())
        self.assertEqual(frame.action, 'cooperative-device-workload-test')
        for text in (lead.replace('19 Pro Max', '18 Pro Max'),
                     lead.replace('实验显示', '预计'),
                     lead.replace('实验显示', '此前的实验显示'),
                     lead.replace('实验显示', '另一台 iPhone 18 Pro Max 实验显示')):
            with self.subTest(text=text):
                frame = source_current_report_frame(title, text, ())
                self.assertTrue(frame is None or frame.action != 'cooperative-device-workload-test')

    def test_joint_market_claim_needs_an_observed_result(self):
        from apple_news_core.event_identity import source_market_measurement_frame
        title = '苹果与华为位居前二：2026 年 Q3 中国智能手机市场份额报告'
        for claim in ('预计苹果与华为合计占40.8%。', '苹果与华为合计并未达到40.8%。',
                      '去年苹果与华为合计占40.8%。'):
            frame = source_market_measurement_frame(title,
                'Counterpoint 发布2026年第三季度中国智能手机市场报告。', (claim,))
            self.assertIsNone(frame)


if __name__ == '__main__':
    unittest.main()
