"""A source's reporting focus owns the action; incidental facts do not."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module
import test_p4_pure_json_batch as prior


class ReportBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261025_report_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 25, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    def test_review_fragments_do_not_default_to_separate_bullets(self):
        queue = self.m.build_final_brief_queue([{'id': 'report', 'title': 'A focused report'}])
        queue.append({'id': 'evidence-review:source', 'evidence_id': 'source',
                      'required': True, 'title': 'A related background sentence',
                      'unprocessed_evidence': [{'unit_id': 'tail', 'text': 'Related background.'}],
                      'source_urls': [], 'reason': 'unassigned'})
        required = self.m.required_final_brief_titles(queue)
        self.assertTrue(required[0]['separate_bullet_by_default'])
        self.assertTrue(required[1]['required'])
        self.assertFalse(required[1]['separate_bullet_by_default'])
        scaffold = self.m.render_brief_scaffold({'events': [], 'final_brief_queue': queue})
        self.assertIn('<!-- unit_id: tail -->', scaffold)
        self.assertIn('required means review, not publication', scaffold)

    def test_teardown_report_is_not_an_independent_repair_project(self):
        events, data = self.cluster_sources('55f99cf9eb99d802f0d74e30')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        self.assertEqual(len(events), 1)
        self.assertIn('Teardown', events[0].title)

    def test_same_teardown_publications_match_across_languages(self):
        events, _ = self.cluster_sources('55f99cf9eb99d802f0d74e30', '5e7df390ec22179d1b6e50e7')
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 2)

    def test_teardown_publication_preserves_its_publisher_scope(self):
        from apple_news_core.event_identity import build_event_identity, source_operation_frame

        def frame(title, text):
            return source_operation_frame(title, text, (), build_event_identity(title, text), source_units=(text,))

        title = 'iPhone 29 teardown videos reveal internal components'
        english = 'The first iPhone 29 teardown videos have been shared by YouTube channels Orion Labs and Vega Repair.'
        chinese = 'YouTube频道 Vega Repair 与 Orion Labs 放出了首批 iPhone 29 的拆机视频。'
        left = frame(title, english)
        right = frame('苹果 iPhone 29 拆解：双电池设计', chinese)
        self.assertIsNotNone(left)
        self.assertEqual(left, right)
        self.assertNotEqual(left, frame(title, english.replace('Vega Repair', 'Atlas Workshop')))
        self.assertNotEqual(left, frame(title, english.replace(' and Vega Repair', '')))
        owned = 'YouTube频道乙发布了iPhone 29的拆机视频。'
        other = 'YouTube频道甲发布了iPad 9的拆机视频，而' + owned
        self.assertEqual(frame('iPhone 29拆机视频', owned), frame('iPhone 29拆机视频', other))
        for text in (chinese.replace('放出了', '没有发布'), '去年，' + chinese,
                     chinese.replace('iPhone 29', 'iPhone 30'),
                     chinese.replace('iPhone 29 的', 'iPhone 29 保护套的')):
            with self.subTest(text=text):
                self.assertIsNone(frame('苹果 iPhone 29 拆解：双电池设计', text))
        headline = 'iPhone 29 Teardowns Reveal Two Batteries'
        denied = 'YouTube channels Orion Labs and Vega Repair have not published an iPhone 29 teardown.'
        self.assertIsNone(source_operation_frame(headline, denied, (),
            build_event_identity(headline, denied), source_units=(headline, denied)))

    def test_teardown_profiles_keep_complete_publishers_and_precise_scopes(self):
        from test_relevance_rules import article_for
        title = '苹果 iPhone 29 拆解：双电池设计'
        lead = 'YouTube频道 Orion Labs 与 Vega Repair 发布了首批 iPhone 29 的拆解视频。'
        articles = [article_for(self.m, title, text) for text in (
            lead, lead.replace('Orion Labs', 'Atlas Labs'), lead.replace('Orion Labs 与 ', ''))]
        self.assertEqual(len(self.m.cluster_articles(articles)), 3)
        region_title = 'Japan iPhone 29 modem teardown identifies Qualcomm X80'
        region_lead = ('The first iPhone 29 teardown videos have been shared by YouTube channels Orion Labs and Vega Repair. '
                       'Orion has identified a Qualcomm X80 modem in the Japanese iPhone 29.')
        base = self.m.article_reconciliation_profile(article_for(self.m, region_title, region_lead))
        self.assertIn('teardown-part-code:x:x80', base.separation_keys)
        self.assertTrue(any('japan' in key for key in base.event_keys))
        for other_title, other_lead in (
            (region_title.replace('X80', 'X85'), region_lead.replace('X80', 'X85')),
            (region_title.replace('Japan', 'US'), region_lead.replace('Japanese', 'US')),
            (region_title, region_lead.replace('Vega Repair', 'Atlas Workshop')),
            (region_title.replace('29', '29 Pro Max'), region_lead.replace('29', '29 Pro Max')),
        ):
            with self.subTest(title=other_title, text=other_lead):
                other = self.m.article_reconciliation_profile(article_for(self.m, other_title, other_lead))
                self.assertNotEqual(self.m.profile_pair_decision(base, other), 'match')

    def test_current_test_and_negative_service_observation_remain_reports(self):
        for key in ['33be062962985651eeb385c0', 'b84ebffde786b65718670dde']:
            with self.subTest(source=key):
                events, _ = self.cluster_sources(key)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])

    def test_named_judge_can_own_a_court_remedy(self):
        events, _ = self.cluster_sources('eb3350ed984f76879c29a3a7')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        self.assertEqual(events[0].articles[0].bound_claim.subject, 'apple-app-store:australia')

    def test_same_copyright_appeal_reconciles_full_names_and_translated_aliases(self):
        ids = ('a5d791e653730902bb6a0add', 'a0b86a689929f326995b7fbd')
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(len(events[0].articles), 2)
            self.assertEqual(events[0].category, 'software_systems')

    def test_copyright_appeal_resolves_only_explicit_case_and_current_court(self):
        from apple_news_core.event_identity import source_copyright_appeal_frame
        from apple_news_core.models import EvidenceUnit
        from dataclasses import replace
        from test_relevance_rules import article_for
        title = 'Apple wins copyright appeal over Harbor'
        ruling = ('Apple and A. Hall have won an appeal over Apple TV series "Harbor," '
                  'with a federal appeals court upholding last year\'s jury verdict in their favor.')
        explanation = "In its October 22 decision, the Ninth Circuit rejected filmmaker Alice Carter's arguments."
        lawsuit = 'Carter sued in January 2020, alleging the series copied her film "Beacon."'
        paragraphs = (ruling, explanation, lawsuit)

        def frame(parts):
            return source_copyright_appeal_frame(title, parts[0], parts)

        current = frame(paragraphs)
        self.assertIsNotNone(current)
        chinese = ('苹果与 A·霍尔在 Apple TV 剧集《港湾》（Harbor）的版权诉讼上诉中胜诉，'
                   '美国联邦第九巡回上诉法院维持了去年陪审团作出的有利于他们的裁决。',
                   '法院驳回了导演爱丽丝 · 卡特（Alice Carter）的主张。',
                   '卡特在 2020 年 1 月提起诉讼，指控该剧抄袭电影《灯塔》（Beacon）。')
        self.assertEqual(current, frame(chinese))
        for parts in (
            (ruling, explanation.replace('decision', 'decision last year'), lawsuit),
            (ruling, 'In 2020, the Ninth Circuit allowed the suit to proceed.', lawsuit, explanation),
            (ruling, explanation, lawsuit.replace('sued', 'commented')),
            (ruling.replace('upholding', 'not upholding'), explanation, lawsuit),
            (ruling.replace('upholding', 'expected to uphold'), explanation, lawsuit),
            (ruling.replace('in their favor', 'against Orion. A separate verdict was for Apple'), explanation, lawsuit),
            (ruling, explanation + ' Director Jane Carter commented on the case.', lawsuit),
            (ruling, explanation.replace('the Ninth Circuit', 'the Ninth Circuit and Third Circuit'), lawsuit),
            ('The Ninth Circuit Court of Appeals did not issue a ruling. A district court upheld the verdict for Apple.', explanation, lawsuit),
            ('The Ninth Circuit Court of Appeals heard arguments, but a district judge upheld the verdict for Apple.', explanation, lawsuit),
            (ruling, 'In its October 22 decision, the court cited an unrelated Ninth Circuit precedent.', lawsuit),
            (ruling, explanation, 'Bob Carter sued over the series Harbor.'),
            (ruling, explanation, 'It is not true that Carter sued over the series Harbor.'),
            (ruling, explanation, 'It is not true that filmmaker Alice Carter sued over the series Harbor.'),
            (chinese[0].replace('维持了', '未维持'), *chinese[1:]),
            (chinese[0], chinese[1], chinese[2].replace('提起诉讼', '评论此案')),
            tuple(text.replace('Harbor', 'The Last Days of the Harbor Detectives') for text in chinese),
        ):
            with self.subTest(parts=parts):
                self.assertIsNone(frame(parts))
        template = self.source_articles('a5d791e653730902bb6a0add')[0].evidence
        def profile(headline, parts):
            article = article_for(self.m, headline, parts[0], facts=list(parts[1:]))
            article.evidence = replace(template, title=headline, raw_lead=parts[0], discovery_title=headline, discovery_lead=parts[0],
                units=tuple(EvidenceUnit(str(n), 'p', text, 'detail', n) for n, text in enumerate(parts)))
            return self.m.article_reconciliation_profile(article)
        base = profile(title, paragraphs)
        self.assertTrue(any('appeal-verdict-upheld' in key for key in base.event_keys))
        for change in (
            {'Alice Carter': 'Jane Baker', 'Carter sued': 'Baker sued'},
            {'Harbor': 'Estuary'}, {'Ninth Circuit': 'Third Circuit'},
            {'upholding': 'overturning'},
        ):
            parts = list(paragraphs)
            other_title = title
            for old, new in change.items():
                parts = [part.replace(old, new) for part in parts]
                other_title = other_title.replace(old, new)
            other = profile(other_title, parts)
            self.assertNotEqual(self.m.profile_pair_decision(base, other), 'match')

    def test_prototype_subject_accepts_a_described_device_without_renaming_it(self):
        events, _ = self.cluster_sources('ce6070b3ab6ba821f5cbc55e')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])
        self.assertEqual(events[0].articles[0].bound_claim.subject, 'ipad:foldable')
        from apple_news_core.event_identity import source_internal_testing_frame
        title = '苹果正在测试折叠 iPad'
        for phrase in ('一款大尺寸折叠平板设备', '一台小尺寸折叠平板电脑', '大尺寸折叠平板'):
            with self.subTest(phrase=phrase):
                frame = source_internal_testing_frame(title, f'苹果正在测试{phrase}。')
                self.assertIsNotNone(frame)
                self.assertEqual(frame.subject, 'ipad:foldable')
        for phrase in ('一款华为大尺寸折叠平板设备', '三星的一台折叠平板电脑',
                       '一款大尺寸折叠平板保护套', '一款大尺寸折叠平板应用'):
            with self.subTest(phrase=phrase):
                self.assertIsNone(source_internal_testing_frame(title, f'苹果正在测试{phrase}。'))

    def test_dedicated_operating_reports_are_software(self):
        for key in ['b5edcffacbcd0cc789ae9640', 'bb90f77a40553e3ebe82c416',
                    '710407c4c496581b7a965ade', '3823bf06cc7e6e161f597d20',
                    '332ad1614621851acfaff51e', '1de18b3e588ee0b5d557cfd4']:
            with self.subTest(source=key):
                events, _ = self.cluster_sources(key)
                self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])

    def test_attributed_causal_opinion_does_not_become_device_news(self):
        events, _ = self.cluster_sources('09322b2ff3e62223cf6fa781')
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_non_theme_resale_quote_does_not_promote_retail_offer(self):
        events, _ = self.cluster_sources('76c31e9862ff594a7834a644')
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_resale_report_keeps_its_theme_and_current_observation(self):
        events, data = self.cluster_sources('85cd2d77e31f5a38815ce590')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, self.rows['85cd2d77e31f5a38815ce590']['evidence']['title'])
        self.assertNotIn('或为', events[0].summary)
        self.assertTrue(any('1600' in fact for fact in events[0].key_facts))

    def test_current_quote_continues_its_observer_without_repeating_the_name(self):
        events, _ = self.cluster_sources('a2348cc9825ecf88fc57f654')
        self.assertEqual(len(events), 1)
        self.assertIn('3000', events[0].summary)
        self.assertTrue(any('79999' in fact for fact in events[0].key_facts))

    def test_quote_observer_does_not_cross_a_new_subject(self):
        from dataclasses import replace
        from apple_news_core.event_identity import bind_resale_report
        from apple_news_core.models import EvidenceUnit
        evidence = self.source_articles('a2348cc9825ecf88fc57f654')[0].evidence
        for continuation in ('华为新机目前溢价3000元。', '不过，华为新机目前溢价3000元。',
                             '华为新机正式开售。目前溢价回落到3000元。',
                             '目前溢价回落到4000元。华为新机正式开售。目前溢价回落到3000元。',
                             '目前溢价下降到4000元，而华为新机溢价3000元。'):
            revised = replace(evidence, title='iPhone Duo黄牛报价回落', units=(
                EvidenceUnit('price', 'p', '交易平台上，iPhone Duo目前溢价5000元。', 'html', 0),
                EvidenceUnit('next', 'p', continuation, 'html', 1)))
            claims = bind_resale_report(revised)
            units = {u.unit_id: u.text for u in revised.units}
            facts = [units[k][a:b] for c in claims for k, a, b in c.evidence_spans]
            self.assertTrue(facts)
            self.assertFalse(any('华为' in f or '3000' in f for f in facts))

    def test_reported_non_adoption_is_not_a_third_party_product_action(self):
        events, _ = self.cluster_sources('f6f08444781b82c7e79c08c6')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'hardware_products')])

    def test_architecture_decision_requires_apple_assertion_not_an_adjacent_actor(self):
        from apple_news_core.event_identity import source_hardware_action_frame
        title = '苹果手机芯片不采用3D堆叠技术'
        for text in (
            '谷歌已经明确没有计划采用3D堆叠技术，苹果尚未回应。',
            '消息人士明确表示，目前没有证据证实苹果不打算采用3D堆叠。',
            '去年消息人士表示没有手机厂商想要采用3D堆叠技术，苹果的朋友已经明确了这一点。',
            '分析师建议苹果不打算采用3D堆叠技术。'):
            with self.subTest(text=text):
                self.assertIsNone(source_hardware_action_frame(title, text, (text,)))
        text = '消息人士确认苹果目前不打算采用3D堆叠技术。'
        self.assertIsNotNone(source_hardware_action_frame(title, text, (text,)))

    def test_apple_responsible_officer_explanation_is_not_outside_commentary(self):
        title = '苹果工程负责人谈 iPhone Duo 屏幕开裂：原因是胶层缺陷'
        text = '苹果工程负责人发表了自己的看法，确认近期 iPhone Duo 屏幕开裂原因是胶层缺陷。苹果将免费更换受影响屏幕。'
        from apple_news_core.event_identity import source_editorial_evaluation
        self.assertEqual(source_editorial_evaluation(title, text), '')


if __name__ == '__main__':
    unittest.main()
