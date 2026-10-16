"""Source-local reports must survive sparse discovery and keep their action."""
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceBoundariesTests(unittest.TestCase):
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.fixture = json.loads((Path(__file__).parent / 'fixtures/20261013_source_boundaries.json').read_text())
        cls.rows = cls.fixture['sources']
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 13, tzinfo=timezone.utc))}

    def assert_group(self, ids, category, tier='strong'):
        articles = [a for sid in ids for a in self.source_articles(sid)]
        for order in (articles, articles[::-1]):
            with self.subTest(order=[a.evidence.article_id for a in order]):
                events = self.m.cluster_articles(order)
                self.assertEqual(len(events), 1)
                value = self.m.event_to_dict(events[0], timezone.utc)
                self.assertEqual(value['category'], category)
                self.assertEqual(value['relevance_tier'], tier)
                self.assertEqual(Counter(s['url'] for s in value['sources']),
                    Counter(self.rows[sid]['evidence']['url'] for sid in ids))

    def test_market_headline_without_apple_gets_detail_verification(self):
        title = 'Gartner 数据：2026Q3 全球 PC 出货量降至 2023 年初以来最低水平'
        url = self.rows[self.fixture['gartner_id']]['evidence']['url']
        src = self.sources['IT之家']
        c = self.m.parse_html_links('<li><a href="' + url + '">' + title + '</a></li>', 'https://www.ithome.com/', src)[0]
        self.assertTrue(self.m.is_relevant_candidate(c, src))
        self.assertIn(c, self.m.select_detail_candidates([c], self.sources, 20))
        for source in self.sources.values():
            c = self.m.Candidate(source.name, 'https://' + source.domains[0] + '/report/',
                'Research report: global smartphone shipments fell in Q3 2026', '')
            self.assertTrue(self.m.is_relevant_candidate(c, source), source.name)
        for title in ('PC buying guide: ten best deals', 'Global DRAM prices increase in Q3 2026',
                      'New laptop ships tomorrow', '个人电脑促销：最低价仅1999元'):
            c = self.m.Candidate(src.name, url, title, '')
            self.assertFalse(self.m.is_relevant_candidate(c, src), title)

    def test_market_headline_keeps_its_own_measurement(self):
        sid = 'c1292d4ada409146b21b1876'
        _, values = self.cluster_sources(sid)
        title = self.rows[sid]['evidence']['title']
        self.assertIn(title, values[0]['must_include_facts'])
        fact = next(f for f in values[0]['fact_sources'] if f['text'] == title)
        self.assertEqual({o['url'] for o in fact['origins']},
                         {self.rows[sid]['evidence']['url']})
        self.assertTrue(all(o['location_status'] == 'source-text-only' for o in fact['origins']))
        article = self.source_articles(sid)[0]
        self.assertFalse(self.m.source_market_headline_has_uncovered_measurement(
            replace(article, projected_fact_spans=())))
        self.assertFalse(self.m.source_market_headline_has_uncovered_measurement(
            replace(article, title='A different projected subject')))

    def test_page_budget_applies_after_discovery_eligibility(self):
        source = self.sources['IT之家']
        budget = self.m.MAX_PAGE_LINKS
        noise = ''.join(f'<a href="/news/car-{i}.htm">汽车厂商发布新款柴油卡车{i}</a>'
                        for i in range(budget + 5))
        titles = ('Gartner 数据：2026Q3 全球 PC 出货量降至最低水平',
                  '苹果发布新的系统安全更新')
        relevant = ''.join(f'<a href="/news/report-{i}.htm">{title}</a>'
                           for i, title in enumerate(titles))
        for page in (noise + relevant, relevant + noise):
            with self.subTest(order=page[:60]):
                rows = self.m.parse_html_links(page, source.pages[0], source)
                self.assertEqual(len(rows), budget)
                self.assertEqual([c.title for c in rows if self.m.is_relevant_candidate(c, source)],
                                 list(titles))
        # A dense relevant page still obeys the unchanged budget and page order.
        page = ''.join(f'<a href="/news/system-{i}.htm">苹果发布系统安全更新{i}</a>'
                       for i in range(budget + 5))
        rows = self.m.parse_html_links(page, source.pages[0], source)
        self.assertEqual(len(rows), budget)
        self.assertTrue(rows[-1].url.endswith(f'system-{budget - 1}.htm'))

    def test_purchase_inspection_walkthrough_is_not_hardware_news(self):
        events, _ = self.cluster_sources('676c15e64292ed87e22cac5b')
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        for title, lead in (
            ('二手平台买 iPad 靠谱吗：到手验机全记录',
             '我在二手平台买了一台 iPad，今天分享从下单到验机的全过程。'),
            ('Buying a used iPhone: my purchase and inspection experience',
             'I bought a used iPhone from a reseller. Here is my purchase experience and inspection checklist.'),
        ):
            with self.subTest(title=title):
                a = article_for(self.m, title, lead, facts=['The inspection took 35 minutes.'])
                self.assertEqual(a.relevance_tier, 'weak')
        for title, lead in (
            ('苹果发布 iPad 验机诊断工具', '苹果发布新的 iPad 诊断工具，可检测屏幕和触控硬件故障。'),
            ('Apple releases a new iPad inspection tool', 'Apple released a new diagnostic tool for iPad hardware repairs.'),
        ):
            with self.subTest(title=title):
                self.assertEqual(article_for(self.m, title, lead).relevance_tier, 'strong')
        identity = self.m.build_event_identity(
            'Apple publishes a new iPhone inspection checklist',
            'Apple published a new checklist for iPhone hardware diagnostics. A customer said, I bought an iPhone last month.')
        self.assertNotEqual(identity.content_form, 'review')

    def test_headline_measurement_coverage_does_not_borrow_another_metric(self):
        title = 'Q3 2026 global smartphone shipments fall: average selling price rises 18% this year'
        lead = 'Counterpoint reports global smartphone shipments fell 18% in Q3 2026. Apple held a 23% market share.'
        def make(headline, detail):
            article = article_for(self.m, headline, lead, facts=[detail])
            return replace(article, evidence=self.m.capture_article_title_evidence(
                article.source, article.url, headline, lead, (detail,)))
        for detail in ('Global smartphone shipments fell 18% this year.',
                       'Average selling price rose 16% this year.',
                       'Average selling price rises 18% last year.',
                       'Average selling price falls 18% this year.',
                       'Samsung average selling price rises 18% this year.'):
            with self.subTest(detail=detail):
                event = self.m.cluster_articles([make(title, detail)])[0]
                self.assertIn(title, self.m.event_must_include_facts(event))
        article = make(title, 'Average selling price rises 18% this year.')
        event = self.m.cluster_articles([article])[0]
        self.assertNotIn(title, self.m.event_must_include_facts(event))
        event = self.m.cluster_articles([replace(article, key_facts=[])])[0]
        self.assertIn(title, self.m.event_must_include_facts(event))
        for headline in ('Could average selling price rise 18%? Q3 2026 global smartphone shipments fall',
                         'Forecast: Q3 2026 global smartphone shipments fall, average selling price may rise 18%',
                         'Q3 2026 global smartphone shipments fall: average selling price is expected to rise 18% this year',
                         '2026年第三季度全球手机出货量下降：今年平均售价有望上涨18%'):
            event = self.m.cluster_articles([make(headline, lead)])[0]
            self.assertNotIn(headline, self.m.event_must_include_facts(event))

    def test_local_cluster_measurement_accepts_chinese_rate_units(self):
        events, values = self.cluster_sources('d4a6a2972191dfa935fc3c47')
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertTrue(any('1.3万亿次浮点运算每秒' in f for f in values[0]['must_include_facts']))
        title = '博物馆用20台旧Mac mini打造Nova-7外形复刻品'
        lead = '博物馆将20台Mac mini组成计算集群。'
        measured = '展品近期使用团队编写的Python矩阵乘法程序测试，当时有48个核心投入运行，成绩约为1.2万亿次浮点运算每秒。'
        comparison = '作为参照，原版机器的理论峰值为每秒1亿次浮点运算。'
        article = article_for(self.m, title, lead, facts=[measured + comparison])
        self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'strong')
        with_comparison = measured.rstrip('。') + '，而原版机器的理论峰值仅为每秒1亿次浮点运算。'
        self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead,
            facts=[with_comparison])])[0].relevance_tier, 'strong')
        for detail in (
            measured.replace('近期使用', '计划近期使用'),
            measured.replace('成绩约为', '预计成绩约为'),
            measured.replace('近期使用', '去年使用'),
            measured.replace('程序测试', '程序测试但尚未得到有效结果'),
            '另有一套Ryzen集群。' + measured.replace('展品近期', '该集群近期'),
            '展品近期使用团队编写的Python矩阵乘法程序测试，但未达到1.2万亿次浮点运算每秒。',
            '展品近期使用团队编写的Python矩阵乘法程序测试，成绩尚待公布，而Ryzen工作站成绩约为1.2万亿次浮点运算每秒。',
            '展品近期使用团队编写的Python矩阵乘法程序测试，而Ryzen工作站接受相同测试，成绩约为1.2万亿次浮点运算每秒。',
        ):
            with self.subTest(detail=detail):
                other = article_for(self.m, title, lead, facts=[detail, comparison])
                self.assertEqual(self.m.cluster_articles([other])[0].relevance_tier, 'weak')

    def test_current_device_test_is_not_accessory_advice(self):
        events, values = self.cluster_sources('f97ea0d6eac4926f3a1a05fa')
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(events[0].category, 'hardware_products')
        self.assertTrue(any('82' in f and '84' in f for f in values[0]['must_include_facts']))

    def test_independent_camera_test_does_not_merge_with_general_review(self):
        ids = ['fd6a0aaae3abae552341405d', 'dd1e501e6df4eb3eb3c35d9b']
        for order in (ids, ids[::-1]):
            events, values = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_device_test_keeps_non_numeric_method_and_conditions(self):
        events, values = self.cluster_sources('fd6a0aaae3abae552341405d')
        text = next(u['text'] for u in self.rows['fd6a0aaae3abae552341405d']['evidence']['units']
                    if '三脚架' in u['text'])
        self.assertIn(text, values[0]['must_include_facts'])
        item = next(f for f in values[0]['fact_sources'] if f['text'] == text)
        self.assertTrue(all(o['location_status'] == 'located' for o in item['origins']))
        article = self.source_articles('fd6a0aaae3abae552341405d')[0]
        for other in (text.replace('DPReview', 'OtherLab'), text.replace('在三脚架', '去年在三脚架'),
                      text.replace('在三脚架', '建议在三脚架'), text.replace('主摄像头', '另一部手机的主摄像头'),
                      text.replace('主摄像头', '三星 Galaxy S26 的主摄像头'),
                      text.replace('在三脚架上', '将三星 Galaxy S26安装在三脚架上，')):
            with self.subTest(other=other):
                evidence = replace(article.evidence, units=tuple(replace(u, text=other)
                    if u.text == text else u for u in article.evidence.units))
                changed = replace(article, evidence=evidence)
                self.assertFalse(any(f.text == other for f in self.m.source_supporting_facts(changed, ())))

    def test_focused_device_test_owns_reporter_object_and_current_stage(self):
        from apple_news_core.event_identity import source_device_behavior_test_frame
        title = 'iPhone 19充电测试：不同协议下的充满时间'
        lead = '科技媒体 Example Lab 实测显示，在苹果 iPhone 19 上，两种充电器速度接近。'
        facts = ['iPhone 19在相同环境中使用两款电源，分别耗时81分钟和83分钟充满。']
        first = article_for(self.m, title, lead, facts=facts)
        same = article_for(self.m, 'iPhone 19快充实测结果公布', lead, facts=facts)
        translated = article_for(self.m, 'Example Lab tests iPhone 19 charging behavior',
            'Example Lab tests show iPhone 19 has similar charging speeds with both adapters.',
            facts=['The iPhone 19 takes 81 minutes to charge fully with the first adapter.'])
        separate = article_for(self.m, title.replace('不同协议', '两款电源'),
            lead.replace('Example Lab', 'Other Lab'), facts=facts)
        next_model = article_for(self.m, title.replace('19', '20'), lead.replace('19', '20'),
            facts=[f.replace('19', '20') for f in facts])
        for order in ([first, same, translated, separate, next_model], [next_model, separate, translated, same, first]):
            self.assertEqual(len(self.m.cluster_articles(order)), 3)
        pro = article_for(self.m, title.replace('19', '19 Pro'), lead.replace('19', '19 Pro'),
            facts=[f.replace('19', '19 Pro') for f in facts])
        self.assertEqual(len(self.m.cluster_articles([first, pro])), 2)
        for other_title, other_lead in (
            (title, lead.replace('实测显示', '计划测试')),
            (title, lead.replace('实测显示', '去年实测显示')),
            ('充电器上市：兼容iPhone 19', lead),
            ('iPhone 19充电器选购教程', lead),
            (title, lead.replace('在苹果 iPhone 19 上', '在某款竞品手机上，iPhone 19仅作为参照')),
        ):
            self.assertIsNone(source_device_behavior_test_frame(other_title, other_lead, tuple(facts)))
        for other_title in (title, 'iPhone 19充电测试：新机测试尚待进行'):
            prior = article_for(self.m, other_title, lead.replace('iPhone 19', 'iPhone 18'),
                facts=[f.replace('19', '18') for f in facts])
            self.assertEqual(self.m.cluster_articles([prior])[0].relevance_tier, 'weak')
        camera = self.source_articles('fd6a0aaae3abae552341405d')[0]
        translated_camera = article_for(self.m,
            'DPReview tests iPhone 18 Pro and Pro Max manual shutter behavior',
            'DPReview tests show iPhone 18 Pro and Pro Max use a single frame in manual shutter mode.',
            facts=['The test compared automatic exposure with manual shutter modes.'])
        self.assertEqual(len(self.m.cluster_articles([camera, translated_camera])), 1)
        for model in ('Pro', 'Pro Max'):
            one = article_for(self.m, 'Example Lab tests iPhone 19 ' + model + ' charging behavior',
                'Tests show iPhone 19 ' + model + ' has fast charging.',
                facts=['iPhone 19 ' + model + ' takes 83 minutes to charge fully.'])
            self.assertEqual(len(self.m.cluster_articles([first, one])), 2)

    def test_market_table_preserves_columns_and_apple_metrics(self):
        sid = self.fixture['gartner_id']; row = self.rows[sid]; e = row['evidence']
        c = self.m.Candidate(e['source'], e['url'], e['title'], '')
        title, lead, facts, *_ = self.m.extract_article(c, self.sources[e['source']], self.fixture['gartner_html'], {})
        self.assertTrue(any('苹果 | 5,835 | 10.5% | 6,279 | 8.8% | -7.1%' in f for f in facts), facts)
        p = self.m.article_reconciliation_profile(article_for(self.m, title, lead, facts=facts))
        self.assertEqual((p.relevance_tier, p.category_hint), ('strong', 'hardware_products'))

    def test_market_detail_uses_owned_result_beyond_the_lead(self):
        src = self.sources['cnBeta']
        c = self.m.Candidate(src.name, 'https://www.cnbeta.com.tw/articles/tech/report.htm',
            'Global smartphone shipments fall in Q3 2026',
            'Counterpoint reports a worldwide market decline during the quarter.')
        self.assertTrue(self.m.is_relevant_candidate(c, src,
            ['Apple held 22% market share in Q3 2026.']))
        for facts in (['Samsung held 23% market share. Apple did not participate.'],
                      ['Apple held 22% market share in Q3 2025.'],
                      ['Apple previously held 22% market share.'],
                      ['Apple held 22% market share last year.'],
                      ['Apple increased its quarterly revenue by 10%.']):
            self.assertFalse(self.m.is_relevant_candidate(c, src, facts), facts)

    def test_retained_table_values_keep_the_adjacent_unit_caption(self):
        article = self.source_articles(self.fixture['gartner_id'])[0]
        c = self.m.Candidate(article.source, article.url, article.title, '')
        title, lead, facts, *_ = self.m.extract_article(c, self.sources[article.source],
            self.fixture['gartner_html'], {})
        article = replace(article, title=title, summary=lead, key_facts=facts)
        event = self.m.cluster_articles([article])[0]
        value = self.m.event_to_dict(event, timezone.utc)
        self.assertIn('上述出货量均以千台计算', value['must_include_facts'])
        fact = next(f for f in value['fact_sources'] if f['text'] == '上述出货量均以千台计算')
        self.assertTrue(all(o['location_status'] == 'located' for o in fact['origins']))
        # A nearby unrelated caption must not be reclassified as a unit note.
        for caption in ('苹果以设计创新吸引消费者，图为最新款电脑。',
                        '苹果以云计算提升设备体验，图为最新款电脑。'):
            changed = tuple(replace(u, text=caption)
                if u.container_id == 'caption' else u for u in article.evidence.units)
            other = replace(article, evidence=replace(article.evidence, units=changed))
            value = self.m.event_to_dict(self.m.cluster_articles([other])[0], timezone.utc)
            self.assertNotIn(caption, value.get('must_include_facts', []))

    def test_thermal_interview_coverage_keeps_the_same_owned_action(self):
        sid = next(v for k, v in self.fixture['live_followup_sources'].items() if 'cooling system' in k)
        self.assert_group(['d9aa8fe5ce0c8f0a8bcb250e', 'd3a79a8c5cc1a89ee6ff5a6c', sid], 'hardware_products')
        articles = self.source_articles(sid)
        teardown = article_for(self.m, 'iPhone Duo cooling system exposed in teardown',
            'Repair firm Orion took apart the iPhone Duo and measured its thermal design. '
            'Apple engineers discussed the chip in an earlier interview.')
        self.assertEqual(len(self.m.cluster_articles([*articles, teardown])), 2)

    def test_strategy_opinion_does_not_promote_cited_old_rumors(self):
        sid = next(v for k, v in self.fixture['live_followup_sources'].items() if 'How Apple can win' in k)
        events, _ = self.cluster_sources(sid)
        self.assertEqual(events[0].relevance_tier, 'weak')
        p = self.m.article_reconciliation_profile(article_for(self.m,
            'How Apple could succeed in personal computing',
            'Apple could leapfrog its rivals if it fixes its software. The opportunity lies in execution.'))
        self.assertEqual(p.relevance_tier, 'weak')
        from apple_news_core.event_identity import source_editorial_outlook
        # A new attributed disclosure is not declared an old-rumor recap;
        # final eligibility still requires its own bound subject and action.
        self.assertFalse(source_editorial_outlook('How Apple can win the smart home',
            'A new report today reveals Apple has launched a home control service.', ()))

    def test_engineering_role_titles_bind_the_same_interview(self):
        self.assert_group(['d9aa8fe5ce0c8f0a8bcb250e', 'd3a79a8c5cc1a89ee6ff5a6c',
                           'd11ffe8ea4d3c26f178defec', '1a23f82a3983e976abbf8199'], 'hardware_products')
        current = self.source_articles('1a23f82a3983e976abbf8199')
        limited_scope = article_for(self.m, 'Apple engineers explain iPhone Duo thermal design',
            'Apple engineers discussed why the iPhone Duo thermal design is not limited to its processor.')
        self.assertEqual(len(self.m.cluster_articles([*current, limited_scope])), 1)
        for lead in (
            '三星散热设计经理在采访中披露其对 iPhone Duo 散热结构的分析，他曾任苹果芯片工程副总裁。',
            '三星散热设计经理在采访中披露其对 iPhone Duo 散热结构的分析。苹果芯片工程副总裁是他过去担任的职务。',
            '三星散热设计经理在采访中披露其对 iPhone Duo 散热结构的分析，而苹果芯片工程副总裁拒绝评论。',
            '苹果芯片工程副总裁拒绝披露 iPhone Duo 的散热设计。三星经理在采访中披露自己的散热分析。',
            'Samsung thermal manager discussed iPhone Duo cooling in an interview. He was formerly an Apple thermal engineer.'):
            other = article_for(self.m, '三星工程师披露 iPhone Duo 散热分析', lead)
            self.assertEqual(len(self.m.cluster_articles([*current, other])), 2)

    def test_current_year_market_report_keeps_its_publication_year(self):
        self.assert_group([self.fixture['gartner_id'], '6c610b97c17eed372b475417'], 'hardware_products')
        lead = 'Gartner reports global PC shipments fell this year in Q3. Apple market share increased 1.7 percentage points. For comparison, global PC shipments fell in Q1 2023.'
        a = article_for(self.m, 'Gartner: global PC shipments in Q3', lead)
        a = replace(a, published_utc=datetime(2028, 10, 13, tzinfo=timezone.utc), published_raw='2028-10-13')
        p = self.m.article_reconciliation_profile(a)
        self.assertIn('source-report-year:2028', p.separation_keys)
        b = replace(a, published_utc=datetime(2027, 10, 13, tzinfo=timezone.utc), published_raw='2027-10-13')
        self.assertEqual(len(self.m.cluster_articles([a, b])), 2)
        local_new_year = replace(a, published_utc=datetime(2027, 12, 31, 16, 30, tzinfo=timezone.utc),
                                 published_raw='2028-01-01T00:30:00+08:00')
        self.assertIn('source-report-year:2028', self.m.article_reconciliation_profile(local_new_year).separation_keys)

    def test_subjective_purchase_comment_stays_weak(self):
        events, _ = self.cluster_sources('5ff955732b029de09c643da1')
        self.assertEqual(events[0].relevance_tier, 'weak')
        for title, lead in (
            ('Orion CEO calls iPhone Duo a waste of money', 'Orion CEO Alex Smith says the iPhone Duo is not worth buying because it has no telephoto camera.'),
            ('某公司高管评价iPhone Duo：不值得买', '该公司高管称iPhone Duo价格太高，缺少长焦镜头，不值得购买。')):
            p = self.m.article_reconciliation_profile(article_for(self.m, title, lead))
            self.assertEqual(p.relevance_tier, 'weak')
        events, _ = self.cluster_sources('dd1e501e6df4eb3eb3c35d9b')
        self.assertEqual(events[0].relevance_tier, 'strong')  # Actual measured device results.

    def test_same_os_adaptation_uses_project_and_guest_not_title_text(self):
        self.assert_group(['81b59144e3d7c4bb02df4411', '8862265b7a97a61af5a92e4d'], 'software_systems', 'ecosystem')

    def test_named_app_store_campaign_groups_its_reported_inventory(self):
        self.assert_group(['dac3c920bcc60138f5bdc87e', 'aaac43e64af4c23f65e36dc5',
                           '5916da8cc5ad4bcdf6647515', 'dd78ff360de590c8bd5b889b'], 'software_systems')

    def test_named_browser_campaign_is_not_hardware_or_wallet_support(self):
        self.assert_group(['bd1ab7b1e774d20acef34518', 'b84802a6c081747c5fca4f9c'], 'software_systems')

    def test_owned_partner_teaser_has_same_stage_across_languages(self):
        self.assert_group(['c57681d1eb23c3269083b12b', 'e5fb4308bb789d9ee96c3f04',
                           'bf0cda1eda1c763dfa5ced1d', 'b12c7fdf0bf2dcd87d787420',
                           '7e9c604c829688e9776a6bc5'], 'hardware_products')

    def test_immersive_film_premiere_is_content_not_device_launch(self):
        self.assert_group(['1600d069535986517a04a2c3', '93b23e450366f7c97d13e3d3',
                           '5699c25e8bbd36ec86958e25'], 'software_systems')

    def test_platform_language_support_is_software(self):
        self.assert_group(['f59d4c24aa3c0644daef9c0e', '4e5f9a09fec73422fdcd90b8'], 'software_systems')

    def test_executive_meeting_is_current_company_action(self):
        events, values = self.cluster_sources('4050ed0615762e84366a0433')
        self.assertEqual((values[0]['relevance_tier'], values[0]['category']), ('strong', 'hardware_products'))

    def test_reported_order_increase_does_not_join_preorder_preparation(self):
        a, b, prep = 'a3fbd043c4f7b9cc1ee527e5', 'e7ec2776461132bde12051c6', '2ae143a5ad8af82ef90fcb5b'
        self.assert_group([a, b], 'hardware_products')
        events, values = self.cluster_sources(a, b, prep)
        self.assertEqual(len(events), 2)
        self.assertIn({self.rows[a]['evidence']['url'], self.rows[b]['evidence']['url']},
                      [{s['url'] for s in v['sources']} for v in values])
        self.assert_group([prep, 'f62ebf305c3a25dcdad6507b'], 'hardware_products')

    def test_product_showcase_binds_its_own_dates_not_listed_ipad(self):
        self.assert_group(['aeed5c3ac22ed577a4a82f61', 'bc479b87ceb91829a0c6f00b'], 'hardware_products')

    def test_same_quantitative_market_report_keeps_apple_result(self):
        self.assert_group(['24fbfb7f6648423c85185d6e', '19197ad74d7d73918e546bc5',
                           'c1292d4ada409146b21b1876'], 'hardware_products')

    def test_named_engineering_explanation_is_hardware_report(self):
        self.assert_group(['d9aa8fe5ce0c8f0a8bcb250e', 'd3a79a8c5cc1a89ee6ff5a6c'], 'hardware_products')

    def test_current_joint_filing_keeps_both_parties_attribution(self):
        self.assert_group(['04e7cf494105e48942acbf17', 'f0b09a5cca929482671098ee',
                           '045213f9bc60e043b256aa35'], 'software_systems')

    def test_joint_filing_discovery_headline_keeps_sparse_source_in_group(self):
        self.assert_group(['04e7cf494105e48942acbf17', 'f0b09a5cca929482671098ee',
                           '045213f9bc60e043b256aa35', '180b6d90844b3e9ed63c0d91'],
                          'software_systems')

    def test_discovery_report_does_not_join_a_ruling_or_different_party(self):
        current = self.source_articles('180b6d90844b3e9ed63c0d91')
        for title, lead in (
            ('法院裁决苹果与Epic证据披露争议', '法院裁决苹果必须提交文件，双方此前提交过联合状态报告。'),
            ('Apple appeals court discovery ruling in Epic case', 'Apple appeals the document production ruling. A joint status report preceded the decision.'),
            ('Apple and Google dispute evidence disclosure scope', 'Apple and Google submitted a joint status report about document production and discovery.'),
            ('Apple completes discovery in Epic dispute', 'Apple has completed document production in its dispute with Epic. The companies submitted a joint status report last month.'),
            ('Apple and Epic postpone evidence disclosure', 'Apple and Epic have agreed to postpone document production until December. The parties previously filed a joint status report in October.'),
            ('Apple and Epic dispute evidence disclosure after talks fail', 'Apple and Epic did not submit a joint status report on document production. They remain unable to agree on the disclosure deadline.'),
            ('苹果与Epic未就证据披露范围达成一致', '苹果与Epic没有提交联合状态报告，双方对文件提交期限仍有争议。')):
            other = article_for(self.m, title, lead)
            self.assertEqual(len(self.m.cluster_articles([*current, other])), 2)
        natural = article_for(self.m, 'Apple and Epic dispute evidence disclosure scope',
            'Apple and Epic submitted a joint status report about document production and discovery.')
        self.assertEqual(len(self.m.cluster_articles([*current, natural])), 1)

    def test_same_price_forecast_accepts_cost_wording(self):
        self.assert_group(['838db9192ac28e980ec91d35', '69018f4e3f2c2094337e04df'], 'hardware_products')

    def test_podcast_recap_is_not_promoted_by_hardware_context(self):
        events, _ = self.cluster_sources('70795170665fb560dd0a46a6')
        self.assertEqual(events[0].relevance_tier, 'weak')

    def test_shipping_outlook_without_new_disclosure_is_not_a_release(self):
        events, _ = self.cluster_sources('2e334031392154b4d4836c68')
        self.assertEqual(events[0].relevance_tier, 'weak')

    def test_sectioned_preview_keeps_borrowed_devices_and_colors_with_owner(self):
        articles = self.source_articles('fc7d635781c81a48447d1d00')
        self.assertEqual(len(articles), 5)
        profiles = [self.m.article_reconciliation_profile(a) for a in articles]
        self.assertEqual([p.category_hint for p in profiles].count('software_systems'), 1)
        self.assertTrue(all(p.relevance_tier == 'strong' for p in profiles))
        hub = next(a for a in articles if 'hub device' in a.title)
        self.assertTrue(any('borrow from the iPhone' in f for f in hub.key_facts))
        mini = next(a for a in articles if 'HomePod mini' in a.title)
        self.assertTrue({'Pink','White','Green','Blue','Black'} <= set(mini.key_facts))
        self.assertFalse(any('iPhone' in a.title for a in articles))
        self.assertFalse(any('Leaked images reveal' in f for a in articles for f in a.key_facts))

    def test_detailed_tv_preview_matches_configuration_without_borrowing_launch(self):
        projected = next(a for a in self.source_articles('fc7d635781c81a48447d1d00')
                         if 'hardware configuration' in a.title)
        focused = self.source_articles('415a85a2448bf81ac5c7ebc5')[0]
        self.assertEqual(len(self.m.cluster_articles([projected, focused])), 1)
        launch = article_for(self.m, 'Apple TV 4K pre-orders open Friday',
                            'Apple announced that Apple TV 4K pre-orders open this Friday.')
        self.assertEqual(len(self.m.cluster_articles([focused, launch])), 2)

    def test_sentence_boundaries_include_closing_quotes(self):
        from apple_news_core.event_identity import source_sentence_spans
        for text, expected in (
            ('Orion says it needs “a few months.” It could still appear earlier.',
             ['Orion says it needs “a few months.”', 'It could still appear earlier.']),
            ('Dr. Lee measured 3.5 watts. “It works!” They reported the result.',
             ['Dr. Lee measured 3.5 watts.', '“It works!”', 'They reported the result.']),
            ('报告称：“还需几个月。”它们仍可能提前展示。',
             ['报告称：“还需几个月。”', '它们仍可能提前展示。']),
        ):
            self.assertEqual([text[a:b] for a, b in source_sentence_spans(text)], expected)

    def test_adjacent_prediction_keeps_evidence_without_borrowing_attribution(self):
        from apple_news_core.article_projector import project_sectioned_home_preview, projected_source_dispositions
        article = next(a for a in self.source_articles('fc7d635781c81a48447d1d00')
                       if 'accessories partnership' in a.title)
        prediction = 'They could still be shown off as part of Apple’s broader home strategy tomorrow, though.'
        value = self.m.event_to_dict(self.m.cluster_articles([article])[0], timezone.utc)
        self.assertFalse(any(prediction in f for f in value['must_include_facts']))
        self.assertTrue(any('at least a few more months' in f for f in value['must_include_facts']))
        variants = project_sectioned_home_preview(article.evidence, 50)
        extraction = self.rows['fc7d635781c81a48447d1d00']['recorded_extraction']
        _, remaining, excluded = projected_source_dispositions(article.evidence,
            [v[2] for v in variants], [extraction[1], *extraction[2]])
        units = {u.unit_id: u for u in article.evidence.units}
        self.assertIn(prediction, [units[k].text[a:b] for k, a, b in remaining])
        self.assertFalse(any(prediction in units[k].text[a:b] for k, a, b, _ in excluded))
        review = self.m.evidence_review_item(article.evidence, remaining, 'Unprocessed source evidence')
        entry = next(v for v in review['unprocessed_evidence'] if v['text'] == prediction)
        self.assertIn('speaker', entry['review_reason'])
        self.assertEqual(units[entry['unit_id']].text[entry['start']:entry['end']], prediction)

    def test_prediction_review_preserves_quoted_and_independently_attributed_claims(self):
        from apple_news_core.article_projector import adjacent_unattributed_prediction_spans
        for text in (
            'Orion says the devices need several months. They could still be shown tomorrow, though.',
            '据报道设备还需数月。它们仍可能提前展示。',
        ):
            self.assertTrue(adjacent_unattributed_prediction_spans(text), text)
        for text in (
            'Orion says the devices could be shown tomorrow.',
            'Orion says the devices need several months. They could be shown tomorrow, the company says.',
            'Orion says “The devices need several months. They could still be shown tomorrow, though.”',
            'Orion says "The devices need several months. They could still be shown tomorrow, though."',
            "Orion says 'The devices need several months. They could still be shown tomorrow, though.'",
            'Orion says the devices need several months. The report adds they could be shown tomorrow.',
            'Orion says the device uses wireless control. It could connect to compatible speakers.',
            'Orion says the device uses wireless control. If the battery fails, it could shut down.',
            'Apple says the device supports two displays. Alerts may appear on either screen.',
            'Apple says the system supports multitasking. Users could launch apps from the Dock.',
            'Apple says the device supports two displays. It may appear on either screen.',
            'Apple says the system supports multitasking. It could launch apps from the Dock.',
            'Apple says the device supports two displays. It may be shown on screen.',
            'The devices need several months. They could still be shown tomorrow, though.',
        ):
            self.assertFalse(adjacent_unattributed_prediction_spans(text), text)

    def test_teaser_partner_model_and_stage_remain_boundaries(self):
        base = article_for(self.m, 'Beats teases collaboration with Orion',
            'Beats shared a short video teasing a new collaboration with Orion, featuring a Beats Pill speaker.')
        for title, lead in (
            ('Beats teases collaboration with Vega', 'Beats shared a short video teasing a new collaboration with Vega, featuring a Beats Pill speaker.'),
            ('Beats teases Orion Studio Pro headphones', 'Beats shared a video teasing a new collaboration with Orion, featuring Beats Studio Pro headphones.'),
            ('Beats launches Orion Pill speaker', 'Beats released the Orion Pill speaker today. A teaser video last week preceded the release.')):
            with self.subTest(title=title):
                other = article_for(self.m, title, lead)
                self.assertEqual(len(self.m.cluster_articles([base, other])), 2)

    def test_named_campaign_inventory_does_not_merge_separate_campaign(self):
        a = article_for(self.m, 'Apple announces Indie Games Week on App Store',
                        'Apple today announced Indie Games Week, celebrating seven new games on the App Store.')
        b = article_for(self.m, 'Apple announces Puzzle Games Week on App Store',
                        'Apple today announced Puzzle Games Week, celebrating seven new games on the App Store.')
        self.assertEqual(len(self.m.cluster_articles([a, b])), 2)

    def test_market_measurement_keeps_provider_period_scope_and_forecast(self):
        title = 'IDC: Apple grows in global PC shipments in Q3 2026'
        lead = 'IDC reports global PC shipments in Q3 2026. Apple shipped 6 million PCs, with a 10% market share.'
        base = article_for(self.m, title, lead)
        for old, new in [('IDC','Gartner'), ('Q3','Q4'), ('2026','2027'), ('global','China')]:
            with self.subTest(replacement=(old, new)):
                other = article_for(self.m, title.replace(old,new), lead.replace(old,new))
                self.assertEqual(len(self.m.cluster_articles([base, other])), 2)
        unrelated = article_for(self.m, 'Gartner: global PC shipments fell in Q3 2026',
            'Gartner reports that PC shipments fell 10% in Q3 2026. Lenovo and HP led. Apple did not participate in this study.')
        self.assertNotEqual(self.m.article_reconciliation_profile(unrelated).relevance_tier, 'strong')
        forecast = article_for(self.m, 'IDC forecasts Apple PC shipments for Q3 2026',
            'IDC forecasts that Apple will ship 6 million PCs in Q3 2026 with a 10% market share.')
        self.assertEqual(len(self.m.cluster_articles([base, forecast])), 2)

    def test_orders_up_is_not_pro_model_and_reverse_directions_do_not_merge(self):
        up = article_for(self.m, 'iPhone Air production orders up 25% says report',
            'Apple increased iPhone Air component production orders by 25%, according to a supply chain report.')
        down = article_for(self.m, 'Apple reduces iPhone Air orders by 25%',
            'Apple reduced iPhone Air component orders by 25%, according to a supply chain report.')
        self.assertEqual(len(self.m.cluster_articles([up, down])), 2)
        profile = self.m.article_reconciliation_profile(up)
        self.assertTrue(any('iphone-air:component-orders' in k for k in profile.event_keys))
        self.assertFalse(any('iphone-air-pro' in k for k in profile.event_keys))
        contextual = article_for(self.m, 'iPhone Air production orders up 25% while iPhone 20 Pro demand slows',
            'Apple increased iPhone Air component production orders by 25%. Demand for iPhone 20 Pro weakened.')
        self.assertEqual(len(self.m.cluster_articles([up, contextual])), 1)
        pro = article_for(self.m, 'iPhone Air launch nears; Apple boosts iPhone 20 Pro orders',
            'Apple increased iPhone 20 Pro component orders. iPhone Air launch timing is unchanged.')
        self.assertEqual(len(self.m.cluster_articles([up, pro])), 2)
        self.assertTrue(any('iphone-20-pro:component-orders' in k
            for k in self.m.article_reconciliation_profile(pro).event_keys))

    def test_showcase_dates_and_government_counterpart_remain_distinct(self):
        a = article_for(self.m, 'Apple plans two-day product showcase',
            'Apple is planning a product showcase in Los Angeles on October 27 and October 28, according to a new report.')
        b = article_for(self.m, 'Apple plans two-day product showcase in November',
            'Apple is planning a product showcase in Los Angeles on November 3 and November 4, according to a new report.')
        self.assertEqual(len(self.m.cluster_articles([a,b])), 2)

        a = article_for(self.m, '何立峰会见苹果公司执行董事长蒂姆·库克',
            '国务院副总理何立峰12日下午在人民大会堂会见苹果公司执行董事长蒂姆·库克。')
        b = article_for(self.m, '苹果公司执行董事长库克会见广东省长',
            '苹果公司执行董事长库克在广州会见广东省省长。')
        self.assertEqual(len(self.m.cluster_articles([a,b])), 2)

    def test_market_values_cannot_borrow_another_owner_sector_or_period(self):
        header = 'Gartner reports that global PC shipments fell 10% in Q3 2026. '
        for body in (
            'HP shipped 8 million PCs and Apple declined to comment.',
            'Apple declined to comment while HP shipped 8 million PCs.',
            'For comparison, Apple shipped 40 million smartphones in Q3 2026.',
            'Apple had a 10% PC market share in Q3 2025; no Apple data is available for Q3 2026.'):
            with self.subTest(body=body):
                p = self.m.article_reconciliation_profile(article_for(self.m,
                    'Gartner: global PC shipments fell in Q3 2026', header + body))
                self.assertNotEqual(p.relevance_tier, 'strong')

    def test_immersive_premiere_retains_own_date(self):
        articles = [article_for(self.m, 'Apple announces immersive film "Echoes" premiere in ' + month,
            'Apple announced that the immersive horror film "Echoes" premieres on ' + month + ' 16 on Apple Vision Pro.')
            for month in ('October','November')]
        for order in (articles, articles[::-1]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_campaign_denial_does_not_become_affirmative_announcement(self):
        a = article_for(self.m, 'Apple announces "Puzzle Games Week" on App Store',
            'Apple today announced Puzzle Games Week, celebrating seven new games on the App Store.')
        b = article_for(self.m, 'Apple denies announcing "Puzzle Games Week" on App Store',
            'Apple denied that it announced Puzzle Games Week, a campaign celebrating seven games on the App Store.')
        self.assertEqual(len(self.m.cluster_articles([a,b])), 2)

    def test_showcase_uses_current_plan_not_preceding_background(self):
        current = 'Apple is planning a product showcase in Los Angeles on November 3 and November 4, according to a new report.'
        a = article_for(self.m, 'Apple plans two-day product showcase',
            'After an event in New York on October 13 and October 14, ' + current)
        b = article_for(self.m, 'Apple plans November product showcase', current)
        self.assertEqual(len(self.m.cluster_articles([a,b])), 1)
        p = self.m.article_reconciliation_profile(a)
        self.assertIn('source-report-period:11:3-4', p.separation_keys)
        self.assertTrue(any('los-angeles' in k for k in p.event_keys))

    def test_teaser_current_partner_cannot_be_replaced_by_historical_brand(self):
        articles = [article_for(self.m, 'Beats teases collaboration with ' + partner,
            'Beats shared a short video teasing a new collaboration with ' + partner + ', featuring a Beats Pill speaker. The company previously worked with Pokemon.')
            for partner in ('Orion','Vega')]
        self.assertEqual(len(self.m.cluster_articles(articles)), 2)
        for a, name in zip(articles, ('orion','vega')):
            p = self.m.article_reconciliation_profile(a)
            self.assertIn('primary-claim:beats:collaboration:' + name + ':partnership-teaser', p.event_keys)

    def test_current_release_reported_in_podcast_keeps_release_identity(self):
        a = article_for(self.m, 'Apple releases iOS 27.2 to all users today',
            "On this week's episode of the Apple podcast, Apple announced that iOS 27.2 is now available to all iPhone users. Apple released iOS 27.2 today with a new security fix.")
        event = self.m.cluster_articles([a])[0]
        self.assertEqual((event.relevance_tier, event.category), ('strong','software_systems'))


if __name__ == '__main__':
    unittest.main()
