"""Owned operations and equivalent reports in the October 11 capture."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

STARTUP = ['911633911af07701f1e75411', '0df787e7d111c2b0adf68600',
           '3d5bab99f044a1e1fef6e84c', 'ef15ad762f1748c0414ee756']
ORDERS = ['9b3dcb8491530365a92f0601', 'b5aea388df4ca964fd0a3841', 'ddaae9bbaa81f97f46a555ec']
TV = ['d5fda65430fec2ff22aedde0', '23cbd651210d5ad44b64779e']


class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261011_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 11, tzinfo=timezone.utc))}

    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)

    def test_corporate_visit_is_not_its_background_leadership_transition(self):
        ids = ['a4fa6c3557110d0369488986', 'a44278bc9274acf84d99e72b']
        for order in (ids, ids[::-1]):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].category, 'hardware_products')
            self.assertEqual(self.source_ids(events[0]), set(ids))
            for article in events[0].articles:
                profile = self.m.article_reconciliation_profile(article)
                self.assertFalse(any('ceo-transition' in key for key in profile.event_keys))

    def test_corporate_visit_owns_person_place_and_stage(self):
        rows = [
            ('Apple CEO Jane Doe visits Paris after taking over the role', 'Apple CEO Jane Doe visited Paris and watched an iPhone film shoot.'),
            ('Apple CEO Jane Doe visits London', 'Apple CEO Jane Doe visited London to meet filmmakers.'),
            ('Apple CEO John Roe visits Paris', 'Apple CEO John Roe visited Paris to meet filmmakers.'),
            ('Apple CEO Jane Doe plans to visit Paris', 'Apple CEO Jane Doe plans to visit Paris next month.'),
            ('Apple CEO Jane Doe visits Paris next month', 'Apple CEO Jane Doe plans to visit Paris next month.'),
            ('Apple CEO Jane Doe visits Paris', 'Apple CEO Jane Doe plans to visit Paris next month.'),
        ]
        events = self.m.cluster_articles([article_for(self.m, *r) for r in rows])
        self.assertEqual(len(events), 4)
        self.assertTrue(all(e.category == 'hardware_products' for e in events))
        future = next(e for e in events if any(a.title == rows[4][0] for a in e.articles))
        self.assertEqual({a.title for a in future.articles}, {rows[3][0], rows[4][0], rows[5][0]})
        from apple_news_core.event_identity import source_executive_visit_frame
        for next_place in ('London', 'Paris'):
            current = source_executive_visit_frame('Apple CEO Jane Doe visits Paris',
                'Apple CEO Jane Doe visited Paris today. Jane Doe plans to visit ' + next_place + ' next month.')
            planned = source_executive_visit_frame(*rows[3])
            self.assertEqual(current.action, 'corporate-visit')
            self.assertNotEqual(current.action, planned.action)
        for title, lead in [
            ('Acme CEO Jane Doe visits Paris', 'Acme CEO Jane Doe visited Paris. Apple CEO Tim Cook visited last year.'),
            ('Apple CEO Jane Doe says Acme executives will visit Paris', 'Apple CEO Jane Doe discussed another company’s visit.'),
            ('Apple CEO Jane Doe watches Acme CEO John Roe visit Paris', 'Apple CEO Jane Doe watches the other executive visiting Paris.'),
            ('库克称另一家公司高管将访问巴黎', '苹果董事会执行主席库克介绍了其他公司高管的行程。'),
            ('Apple CEO Jane Doe denies plans to visit Paris', 'Apple CEO Jane Doe will not visit Paris.'),
            ('苹果新应用支持虚拟参观巴黎', '苹果 CEO Jane Doe 介绍了应用，不曾到访巴黎。'),
        ]:
            self.assertIsNone(source_executive_visit_frame(title, lead))

    def test_equivalent_owned_reports_merge(self):
        for ids in (STARTUP, ORDERS, TV, ['39959f07c35432bce89e6679', 'd24ead9751cc08650522322d']):
            for order in (ids, ids[::-1]):
                with self.subTest(ids=order):
                    events, _ = self.cluster_sources(*order)
                    self.assertEqual(len(events), 1, [(e.title, e.relevance_tier) for e in events])
                    self.assertEqual(self.source_ids(events[0]), set(ids))
                    self.assertEqual(events[0].relevance_tier, 'strong')
                    self.assertEqual(events[0].category, 'hardware_products')

    def test_first_party_capability_and_launch_are_not_third_party_actions(self):
        for sid, category in [('feef9c943c782c88c5186be2', 'software_systems'),
                              ('4b36848bc25a7b54eea1c2d2', 'hardware_products'),
                              ('d24ead9751cc08650522322d', 'hardware_products')]:
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertEqual(events[0].relevance_tier, 'strong')
                self.assertEqual(events[0].category, category)

    def test_consumer_intent_does_not_borrow_product_specifications(self):
        events, _ = self.cluster_sources('5b8ad820f617d815e970e704')
        self.assertEqual(events[0].relevance_tier, 'weak')
        for title, lead in [
            ('iPhone 19 能吸引安卓用户吗：调查报告出炉', '一项读者调查显示，45% 受访者愿意换用 iPhone。苹果已发布 A21 芯片。'),
            ('苹果新款 iPhone 消费者调查公布', '受访者表示手机偏贵，购买意愿不高。'),
        ]:
            self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'weak')

    def test_personalization_requires_retail_operation_not_usage_advice(self):
        for title, lead in [
            ('How to customize the iPhone startup greeting', 'Follow these steps to personalize the boot screen with your name. Apple Store buyers can also get a greeting.'),
            ('Third-party app adds iPhone startup greetings', 'The independent app personalizes the boot screen with a name. Apple Store customers use iPhones.'),
            ('苹果零售店不提供 iPhone 19 开机个性化服务', '苹果否认会为顾客定制开机姓名欢迎画面。'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'weak')

    def test_remote_logs_require_first_party_operation(self):
        for title, lead in [
            ('A third-party app simplifies AppleCare log collection on macOS 28', 'Acme released an app that uploads logs to Acme; AppleCare still requires manual export.'),
            ('How to collect AppleCare logs on your Mac', 'Open the terminal and follow this step-by-step guide to collect and upload logs to Apple.'),
        ]:
            self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'weak')

    def test_launch_object_and_stage_remain_separate(self):
        rows = [
            ('A New Apple TV 4K is Finally Coming on Tuesday', 'Apple is expected to announce a new Apple TV on Tuesday, October 13.'),
            ('Apple Home Hub will be revealed October 13', 'Apple reportedly plans to unveil its new home hub on Tuesday, October 13.'),
            ('Apple TV 4K will be revealed October 20', 'Apple plans to unveil its new Apple TV on Tuesday, October 20.'),
            ('Apple announces Apple TV 4K for October 13', 'Apple confirmed a new Apple TV release on Tuesday, October 13.'),
        ]
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m, *r) for r in rows])), len(rows))

    def test_captured_company_progress_remains_one_event(self):
        events, output = self.cluster_sources('062a51d9b2b3196841f45e6a')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'hardware_products')
        text = json.dumps(output, ensure_ascii=False)
        for fact in ('95%', '2.12', '14.22', '6.71'):
            self.assertIn(fact, text)

    def test_order_batch_keeps_direction_period_and_source_actor(self):
        from apple_news_core.event_identity import source_market_report_frame
        title = '苹果调整 iPhone 19 订单'
        lead = '苹果公司结构性调整 2027 年秋季新品订单，iPhone 19 Pro 加单 8%，iPhone 19 Pro Max 砍单 8%。'
        base = source_market_report_frame(title, lead, ())
        self.assertIsNotNone(base)
        self.assertEqual(base, source_market_report_frame(title, lead, ('另据报道，2028 年春季苹果将推出新款 iPad。',)))
        self.assertNotEqual(base, source_market_report_frame(title, lead.replace('2027', '2028'), ()))
        self.assertNotEqual(base, source_market_report_frame(title, lead.replace('加单', '砍单'), ()))
        for heading, body in [
            ('苹果否认调整 iPhone 19 订单', lead),
            ('Apple supplier Foxconn adjusts iPhone 19 orders', lead),
            (title, '去年，' + lead),
            ('iPhone 19 销量增长', lead),
        ]:
            result = source_market_report_frame(heading, body, ())
            self.assertTrue(result is None or result.action != 'coordinated-order-reallocation')

        denial = ('苹果 iPhone 19 订单调整传闻遭驳斥',
                  '苹果公司没有进行结构性调整 2027 年秋季新品订单，iPhone 19 Pro 加单与 iPhone 19 Pro Max 砍单均为假消息。')
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m, title, lead), article_for(self.m, *denial)])), 2)

    def test_third_party_personalization_does_not_join_retail_service(self):
        rows = [
            ('iPhone 19 开机欢迎画面加入姓名定制', 'Acme 开发的第三方应用可自定义 iPhone 开机欢迎画面，显示用户姓名。苹果零售店并未提供这项服务。'),
            ('苹果零售店为 iPhone 19 提供开机姓名定制', '苹果零售店为顾客定制 iPhone 19 开机欢迎画面，显示用户姓名。'),
        ]
        for ordered in (rows, rows[::-1]):
            events = self.m.cluster_articles([article_for(self.m, *row) for row in ordered])
            self.assertEqual(len(events), 2)
            self.assertEqual({e.relevance_tier for e in events}, {'weak', 'strong'})
        unrelated_store = rows[0][1].replace('苹果零售店并未提供这项服务。', '顾客可以从苹果零售店购买手机。')
        self.assertEqual(self.m.cluster_articles([article_for(self.m, rows[0][0], unrelated_store)])[0].relevance_tier, 'weak')
        for prefix in ('', 'iPhone 19 新增开机欢迎画面选择。'):
            for ordered in ([rows[1], (rows[0][0], prefix + unrelated_store)],
                            [(rows[0][0], prefix + unrelated_store), rows[1]]):
                events = self.m.cluster_articles([article_for(self.m, *row) for row in ordered])
                self.assertEqual(len(events), 2)
                self.assertEqual({e.relevance_tier for e in events}, {'weak', 'strong'})

    def test_sales_quantity_before_model_is_valid_natural_order(self):
        from apple_news_core.event_identity import source_market_report_frame
        title = 'iPhone 19 sales report'
        lead = 'During week 41, sales reached 50 million units for iPhone 19 Pro Max.'
        result = source_market_report_frame(title, lead, ())
        self.assertIn('iphone-19-pro-max', result.subject)
        self.assertEqual(result.period, 'week-41')
        self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'strong')

    def test_activation_period_does_not_transfer_across_unrelated_paragraph(self):
        from apple_news_core.event_identity import source_market_report_frame
        title = 'iPhone 19 Pro 激活量增长'
        period = '2027年第41周，iPhone 19 Pro 系列在中国市场的单周激活量增长。'
        detail = '其中 iPhone 19 Pro Max 单周激活量超过 50 万台。'
        result = source_market_report_frame(title, period + detail, ())
        self.assertEqual(result.period, 'week-41')
        self.assertIn('19-pro-max', result.subject)
        self.assertEqual(result.region, 'china')
        for lead in [period + '另一项研究统计的是安卓市场。' + detail,
                     period + '其中 iPhone 19 Pro Max 预计激活量超过 50 万台。',
                     period + '其中 iPhone 19 Pro Max 激活量没有达到 50 万台。']:
            self.assertIsNone(source_market_report_frame(title, lead, ()))
