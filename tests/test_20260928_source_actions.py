"""Current source actions, with complete captured evidence and nearby controls."""
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
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20260928_source_actions.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 9, 28, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_wishlist_cannot_borrow_prior_leak_authority(self):
        for aid in ['7e061f72ca962a9b62575ada', '7a6e4704673562435238e13a']:
            with self.subTest(aid=aid):
                events, _ = self.cluster_sources(aid)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].relevance_tier, 'weak')

    def test_current_holiday_notice_joins_across_languages(self):
        ids = ['071ba5e82d79848a615a8c90', '638e1e8d5dd3ba3238d97679']
        for ordered in [ids, ids[::-1]]:
            events, _ = self.cluster_sources(*ordered)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_current_store_sales_agree_across_sources(self):
        ids = ['20da00d1f3a9a4e0d4346469', 'aa5bed932f2a91e0b1c15411']
        for ordered in [ids, ids[::-1]]:
            events, _ = self.cluster_sources(*ordered)
            sales = [e for e in events if len(self.source_ids(e)) == 2]
            self.assertEqual(len(sales), 1, [e.title for e in events])
            self.assertEqual(sales[0].relevance_tier, 'strong')
            self.assertEqual(sales[0].category, 'hardware_products')

    def test_measured_device_performance_is_not_accessory_compatibility(self):
        events, _ = self.cluster_sources('834d8d4c27bed5d1609b6584')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        visible = ' '.join(f.text for f in (*events[0].fact_plan.facts,
            *events[0].fact_plan.required, *events[0].fact_plan.unprocessed))
        for fragment in ['447.9', '400.4', '25.1', '冰镇']:
            self.assertIn(fragment, visible)

    def test_different_benchmark_workloads_do_not_merge_on_shared_chip(self):
        ids = ['834d8d4c27bed5d1609b6584','27dff77322a2b39575ae7268','c25d1d3325fb1d0c5d0980bb']
        for ordered in [ids, ids[::-1]]:
            events, _ = self.cluster_sources(*ordered)
            self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                {frozenset(ids[:1]), frozenset(ids[1:])})

    def test_headline_owned_apple_market_share_is_not_background(self):
        events, _ = self.cluster_sources('4b1d1c40bcebb05fcd8e7e0f')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))

    def test_glasses_and_headset_roadmaps_project_separate_products(self):
        for aid in ['3cdcf77fce490b451ab35cec', 'c35aa3962e15866f1144266d']:
            with self.subTest(aid=aid):
                articles = self.source_articles(aid)
                self.assertEqual(len(articles), 2, [a.title for a in articles])
                events = self.m.cluster_articles(articles)
                self.assertEqual(len(events), 2)
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
                self.assertTrue(all(a.projected_fact_spans or a.bound_claim for a in articles))

    def test_apple_pay_display_condition_reaches_fact_plan(self):
        events, _ = self.cluster_sources('4815cbd9bbb9fa30b4c4b002')
        visible = ' '.join(f.text for f in (*events[0].fact_plan.facts,
            *events[0].fact_plan.required, *events[0].fact_plan.unprocessed))
        self.assertIn('Merchants and developers have control', visible)

    def test_independent_body_actions_remain_reviewable(self):
        for aid, fragments in [
            ('09ea0c2e8748a1ab6ca7f39f', ['appeal', 'testing']),
            ('aa5bed932f2a91e0b1c15411', ['裁员', '200', '100']),
        ]:
            events, _ = self.cluster_sources(aid)
            visible = ' '.join(f.text for e in events for f in (
                *e.fact_plan.facts, *e.fact_plan.required, *e.fact_plan.unprocessed))
            for fragment in fragments:
                self.assertIn(fragment, visible)

    def test_editorial_and_ordinary_third_party_sources_stay_weak(self):
        for aid in ['2a86853cd73f1d4fe6e9b93a', '39505f0794f6f028b2d458a4',
                    'f95c26e1f3756c3930662b7c', '4508887c6425a19dfb260ef0',
                    '7c19361e3fa0ea4245755f2d', '631b07c5614240e35c47e218',
                    '806447864f53c7fcd5521e94', 'fa2333a7328c1f457fb4250f']:
            with self.subTest(aid=aid):
                events, _ = self.cluster_sources(aid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_wishlist_words_do_not_suppress_a_reported_release(self):
        for title, lead, tier in [
            ('My biggest feature request for iPad mini', 'Last week a report leaked new iPad mini details. I would like Apple to add a larger display.', 'weak'),
            ("What we'd like to see Apple improve in AirPods", 'Bloomberg reported last month that Apple is developing AirPods. Here are our wishes.', 'weak'),
            ('Apple announces iPad mini display update', 'Apple today announced an iPad mini display update, addressing a popular feature request.', 'strong'),
            ('New iPad mini code leak reveals updated display', 'Newly leaked internal Apple code reveals a new iPad mini display.', 'strong'),
        ]:
            with self.subTest(title=title):
                article = article_for(self.m, title, lead, source='9to5Mac')
                self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, tier)

    def test_employee_notice_requires_current_owner_and_keeps_holiday_year(self):
        positives = [article_for(self.m, f'Apple announces {year} {holiday} employee leave',
            f'Apple announced extra {holiday} leave for its employees this year.', source='9to5Mac')
            for year, holiday in [(2026, 'Thanksgiving'), (2027, 'Thanksgiving'), (2026, 'Christmas')]]
        for ordered in [positives, positives[::-1]]:
            events = self.m.cluster_articles(ordered)
            self.assertEqual(len(events), 3)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        for title, lead in [
            ('History of Apple Thanksgiving staff leave', 'Last year Apple announced extra Thanksgiving leave for employees.'),
            ('Apple Thanksgiving staff leave discussed', 'Apple has not announced Thanksgiving leave for staff.'),
            ('Apple Thanksgiving staff leave plans', 'Apple plans to announce Thanksgiving leave for employees.'),
            ('Apple Thanksgiving staff leave compared', 'Samsung announced Thanksgiving leave for employees, unlike Apple.'),
        ]:
            p = self.m.article_reconciliation_profile(article_for(self.m, title, lead, source='MacRumors'))
            self.assertFalse(any('current-employee-notice' in key for key in p.event_keys), title)

    def test_store_monthly_observation_does_not_merge_other_scales_or_actions(self):
        original = self.source_articles('20da00d1f3a9a4e0d4346469')[0]
        controls = [article_for(self.m, title, lead, source='MacRumors') for title, lead in [
            ('Apple Vision Pro global sales reach 100000 units', 'A research firm reports global Vision Pro sales of 100000 units. Apple stores sell the headset.'),
            ('Apple Vision Pro sales history revisited', 'Last year a reporter said stores sold only 1 headset per month. There is no new sales report.'),
            ('Apple cuts Vision Pro jobs', 'Apple announced layoffs in its Vision Pro team today.'),
            ('Apple iPad monthly store sales', 'According to store employees, some Apple stores sell only 1 device per month.'),
        ]]
        for ordered in [[original, *controls], [*controls[::-1], original]]:
            events = self.m.cluster_articles(ordered)
            sales = next(e for e in events if original in e.articles)
            self.assertEqual(sales.articles, [original])

    def test_workload_measurement_keeps_model_and_cannot_borrow_promotional_numbers(self):
        originals = [article_for(self.m, f'iPhone {generation} Pro transcription performance tested',
            f'A developer tested iPhone {generation} Pro speech-to-text throughput. It processed 510 words per second without cooling and 630 words per second with cooling.', source='MacRumors')
            for generation in [19, 20]]
        self.assertEqual(len(self.m.cluster_articles(originals)), 2)
        for a in originals:
            self.assertEqual(self.m.cluster_articles([a])[0].relevance_tier, 'strong')
        for title, lead in [
            ('iPhone 19 Pro cooling accessory guide', 'A company sells a cooler for iPhone 19 Pro and advertises speech-to-text throughput of 630 words per second. No test was performed.'),
            ('iPhone 19 Pro performance plans', 'A developer has not tested iPhone 19 Pro speech-to-text throughput; 630 words per second is a target.'),
            ('iPhone 19 Pro old performance revisited', 'Last year a developer tested iPhone 19 Pro speech-to-text throughput at 630 words per second.'),
        ]:
            p = self.m.article_reconciliation_profile(article_for(self.m, title, lead, source='9to5Mac'))
            self.assertFalse(any('speech-transcription:current-benchmark-report' in k for k in p.event_keys), title)

    def test_apple_measurement_must_be_owned_not_an_incidental_market_row(self):
        from apple_news_core.event_reconciler import _measured_apple_market_result_keys
        lead = '洛图科技数据显示，2026年8月中国笔记本销量下滑。'
        facts = '苹果表现突出，线上销量份额增至8.2%。小米份额升至5.1%。'
        keys = _measured_apple_market_result_keys('笔记本市场下滑，苹果逆势增长', lead, facts)
        self.assertTrue(keys)
        self.assertTrue(all('2026-08' in k and k.endswith(':8.2') for k in keys), keys)
        for title, body in [
            ('中国笔记本市场销量下滑', facts),
            ('苹果参与的笔记本市场下滑', '联想份额达到34.3%，小米份额增至5.1%。'),
        ]:
            self.assertFalse(_measured_apple_market_result_keys(title, lead, body))

    def test_roadmap_product_facts_do_not_cross_between_projections(self):
        for aid in ['3cdcf77fce490b451ab35cec', 'c35aa3962e15866f1144266d']:
            articles = self.source_articles(aid)
            glasses = next(a for a in articles if 'glasses' in a.title)
            headset = next(a for a in articles if 'Vision Pro' in a.title)
            self.assertNotIn('N224', ' '.join(glasses.key_facts))
            self.assertNotIn('2027', ' '.join(headset.key_facts))
        articles = [a for aid in ['3cdcf77fce490b451ab35cec','c35aa3962e15866f1144266d','66dd165dd1c49e6f8d4326ec']
                    for a in self.source_articles(aid)]
        for ordered in [articles, articles[::-1]]:
            events = self.m.cluster_articles(ordered)
            for e in events:
                self.assertFalse(any('glasses' in a.title for a in e.articles)
                    and any('Vision Pro' in a.title for a in e.articles))
            named = next(e for e in events if any(a.evidence.article_id == '66dd165dd1c49e6f8d4326ec' for a in e.articles))
            self.assertEqual(self.source_ids(named), {'66dd165dd1c49e6f8d4326ec','3cdcf77fce490b451ab35cec'})

    def test_hardware_program_keeps_active_code_not_cancelled_context(self):
        originals = [article_for(self.m, 'Apple working on new Vision Pro',
            f'Apple had been considering a Vision Air, codenamed N300. That project was shelved last year. Apple is now working on a new project, {code}, with a lighter design.', source=source)
            for code, source in [('N400','MacRumors'),('N500','9to5Mac')]]
        events = self.m.cluster_articles(originals)
        self.assertEqual(len(events), 2)
        for a, code in zip(originals, ['n400','n500']):
            p = self.m.article_reconciliation_profile(a)
            self.assertTrue(any(f':project:{code}:' in key for key in p.event_keys), p.event_keys)
            self.assertFalse(any(':project:n300:' in key for key in p.event_keys))

    def test_roadmap_heading_stops_at_a_different_product_paragraph(self):
        from apple_news_core.article_projector import project_hardware_roadmap
        aid = '3cdcf77fce490b451ab35cec'
        article = self.source_articles(aid)[0]
        evidence = article.evidence
        units = list(evidence.units)
        index = next(i for i, u in enumerate(units) if u.kind == 'h2' and 'Visions' in u.text)
        peer_text = 'Apple MacBook Pro will launch with a redesigned display in 2029.'
        units.insert(index + 1, replace(units[index + 1], unit_id='separate-mac-report', text=peer_text))
        title, summary, facts = self.rows[aid]['recorded_extraction']
        variants = project_hardware_roadmap(title, summary, facts,
            identity=self.m.build_event_identity(title, summary),
            single_source_disclosure=False, fact_limit=100,
            evidence=replace(evidence, units=tuple(units)))
        self.assertFalse(any(peer_text in fact for _, _, items in variants for fact in items))

    def test_unclosed_legal_quote_cannot_borrow_the_next_speaker(self):
        article = self.source_articles('09ea0c2e8748a1ab6ca7f39f')[0]
        units = article.evidence.units
        article.evidence = replace(article.evidence, units=(units[7],
            replace(units[8], text='“We disagree with the verdict.'),
            replace(units[10], text="Taction's spokesperson said:"),
            replace(units[12], text='“We welcome the verdict.”')))
        _, unprocessed = self.m.prepare_source_condition_evidence(article)
        for fact in unprocessed:
            if 'Apple spokesperson' in fact.text:
                self.assertNotIn('We welcome the verdict', fact.text)

    def test_possessive_glasses_description_keeps_generations_and_capabilities(self):
        articles = self.source_articles('3cdcf77fce490b451ab35cec')
        glasses = next(a for a in articles if 'glasses' in a.title)
        headset = next(a for a in articles if 'Vision Pro' in a.title)
        facts = ' '.join(glasses.key_facts)
        for text in ['audio, camera, and smart capabilities',
                     'without a display for video feedback',
                     'A later release would introduce the display element']:
            self.assertIn(text, facts)
            self.assertNotIn(text, ' '.join(headset.key_facts))

    def test_glasses_possessive_alias_requires_apple_owner(self):
        from apple_news_core.event_identity import multi_product_hardware_subjects
        for name in ["Apple's glasses", 'Apple’s glasses']:
            self.assertEqual(multi_product_hardware_subjects(name), {'apple-glasses'})
        for name in ["Meta's glasses", 'the glasses', 'camera and audio glasses']:
            self.assertNotIn('apple-glasses', multi_product_hardware_subjects(name))

    def test_employee_notice_keeps_extra_days_and_team_exceptions(self):
        events, _ = self.cluster_sources('071ba5e82d79848a615a8c90', '638e1e8d5dd3ba3238d97679')
        visible = ' '.join(f.text for e in events for f in (
            *e.fact_plan.facts, *e.fact_plan.required, *e.fact_plan.unprocessed))
        for text in ['Monday through Wednesday', 'three extra days off',
                     'Retail and AppleCare', 'international teams', 'at a later date']:
            self.assertIn(text, visible)

    def test_employee_schedule_does_not_borrow_history_or_another_employer(self):
        article = self.source_articles('071ba5e82d79848a615a8c90')[0]
        unit = article.evidence.units[6]
        for text in [
            'Last year, our US teams got Monday through Wednesday off and three extra days off later.',
            "Samsung's employees get four days off, while our Apple teams are discussed for comparison.",
        ]:
            article.evidence = replace(article.evidence, units=(replace(unit, text=text),))
            facts, pending = self.m.prepare_source_condition_evidence(article)
            self.assertFalse(any('employee-leave-condition' in f.roles for f in (*facts, *pending)))

    def test_chip_headline_with_workload_in_lead_joins_same_measurement(self):
        ids = ['6d9176b9ce6ac37d3738aefc', '27dff77322a2b39575ae7268', 'c25d1d3325fb1d0c5d0980bb']
        for ordered in [ids, ids[::-1]]:
            events, _ = self.cluster_sources(*ordered)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_workload_in_competitor_comparison_cannot_own_apple_measurement(self):
        for title, lead in [
            ('Snapdragon gaming performance beats A20 Pro', 'A developer tested Snapdragon gaming performance, compared with iPhone 18 Pro Max running 《GTA 5》 at 66FPS.'),
            ('手机芯片对比：A20 Pro与新竞品', '厂商公布新芯片性能。作为对比，iPhone 18 Pro Max在《GTA 5》实测达到66FPS。'),
        ]:
            p = self.m.article_reconciliation_profile(article_for(self.m, title, lead, source='MacRumors'))
            self.assertFalse(any('current-benchmark-report' in key for key in p.event_keys))


if __name__ == '__main__':
    unittest.main()
