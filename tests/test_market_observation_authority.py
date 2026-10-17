"""Market observations keep source ownership and assertion status."""
import unittest

from test_relevance_rules import article_for, event_for, load_module


class MarketObservationAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_forecast_history_and_denial_do_not_become_observed_results(self):
        title = '内存涨价影响全球手机出货，三星苹果合计份额领先'
        lead = 'Omdia报告显示，2027年第三季度全球智能手机出货量下降。'
        for detail in (
            'Omdia预计苹果本季度占据全球22%的智能手机市场份额。',
            'Omdia forecasts that Apple will hold 22 percent of global smartphone shipments this quarter.',
            '去年苹果以22%的市场份额位列第二。',
            '苹果未达到22%的市场份额。',
            'Omdia预计，苹果本季度占据全球22%的智能手机市场份额。',
            'Omdia预计2027年第三季度，苹果将占据全球22%的智能手机市场份额。',
            '去年，苹果以22%的市场份额位列第二。',
            'Omdia预计，苹果本季度全球智能手机销量第一。',
            'Apple shipments were not reported to have declined.',
            'Apple shipments were not reported as declining.',
            'Apple is expected to perform well, but because demand is weak, its shipments declined.',
        ):
            with self.subTest(detail=detail):
                article = article_for(self.m, title, lead + detail)
                self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'weak')

    def test_forecast_value_cannot_merge_with_an_observed_value(self):
        observed = article_for(self.m, 'Apple smartphone market share reaches 22%',
            'Omdia reports Apple held 22 percent of global smartphone shipments in Q3 2027.')
        mixed = article_for(self.m, 'Apple smartphone market share report',
            'Omdia reports Apple held 21 percent of global smartphone shipments in Q3 2027. '
            'Omdia forecasts Apple will reach 22 percent next quarter.')
        for left, right in ((observed, mixed), (mixed, observed)):
            self.assertFalse(self.m.should_merge(left, event_for(self.m, right)))
        self.assertEqual(len(self.m.cluster_articles([observed, mixed])), 2)

    def test_monthly_results_keep_metric_continuations_and_cross_source_grouping(self):
        left = article_for(self.m, '笔记本市场下滑，苹果逆势增长',
            '洛图科技数据显示，2026年8月中国笔记本销量下滑。'
            '苹果表现突出，线上销量份额增至8.2%。小米份额升至5.1%。')
        right = article_for(self.m, '苹果8月中国笔记本线上销量份额达8.2%',
            '洛图科技报告显示，2026年8月苹果在中国笔记本市场线上销量份额达到8.2%。', source='IT之家')
        events = self.m.cluster_articles([left, right])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')
        self.assertEqual(len(events[0].articles), 2)

    def test_qualifiers_stay_local_to_their_statement(self):
        from apple_news_core.event_identity import source_market_measurement_frame
        title = '内存涨价影响全球手机出货，三星苹果合计份额领先'
        lead = 'Omdia报告显示，2027年第三季度全球智能手机出货量下降。'
        for detail in (
            'Omdia预计苹果明年占据全球23%的份额，但苹果本季度智能手机市场份额达到22%。',
            'Omdia forecasts Apple will reach 23 percent next year; Apple held 22 percent of global smartphone shipments this quarter.',
            'Apple held 22 percent of global smartphone shipments, up from 21 percent last year.',
            'Apple held 22 percent of global smartphone shipments, while Samsung is expected to hold 24 percent.',
            'Apple products remain popular, but because demand is weak, its shipments declined.',
            'Apple products remain popular, because demand is weak, its shipments declined.',
            '三星预计占据全球24%的智能手机市场份额而苹果本季度实际达到22%的智能手机市场份额。',
        ):
            with self.subTest(detail=detail):
                article = article_for(self.m, title, lead + detail)
                self.assertIsNotNone(source_market_measurement_frame(title, lead, (detail,)))
                self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'strong')

    def test_same_period_forecast_is_not_an_observed_report(self):
        observed = article_for(self.m, 'Apple smartphone market share reaches 22%',
            'Omdia reports Apple held 22 percent of global smartphone shipments in Q3 2027.')
        forecast = article_for(self.m, 'Apple smartphone market share forecast for Q3 2027',
            'Omdia forecasts Apple will hold 22 percent of global smartphone shipments in Q3 2027.')
        for left, right in ((observed, forecast), (forecast, observed)):
            self.assertFalse(self.m.should_merge(left, event_for(self.m, right)))
        self.assertEqual(len(self.m.cluster_articles([observed, forecast])), 2)

    def test_forecast_introduction_keeps_its_role_with_a_metric_name(self):
        from apple_news_core.event_identity import source_market_measurement_frame
        title = '内存涨价影响全球手机出货，三星苹果合计份额领先'
        lead = ('Omdia报告显示，2027年第三季度全球智能手机出货量下降。'
                'Omdia的市场份额预测显示：苹果本季度占据全球22%的智能手机市场份额。')
        self.assertIsNone(source_market_measurement_frame(title, lead, ()))
        profile = self.m.article_reconciliation_profile(article_for(self.m, title, lead))
        self.assertTrue(any(k.startswith('structured-market-forecast:') for k in profile.event_keys))
        self.assertFalse(any(k.startswith('structured-market-result:') for k in profile.event_keys))
