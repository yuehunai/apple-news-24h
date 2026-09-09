import unittest

from test_20260905_claim_ownership_boundaries import article_for, load_module


class LiveActionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def cluster(self, pairs):
        articles = [article_for(self.m, title, lead, source=str(i), facts=facts)
                    for i, (title, lead, facts) in enumerate(pairs)]
        originals = [(a.title, a.summary, list(a.key_facts)) for a in articles]
        events = self.m.cluster_articles(articles)
        self.assertCountEqual([a.url for a in articles], [a.url for e in events for a in e.articles])
        self.assertEqual(originals, [(a.title, a.summary, a.key_facts) for a in articles])
        return events

    def test_final_rumors_cannot_bridge_accessory_naming_reports(self):
        for name in ('Duo', 'Edge'):
            with self.subTest(name=name):
                events = self.cluster([
                    ("iPhone Ultra is coming, here's what the final rumors say",
                     'Apple is expected to announce its foldable iPhone tomorrow, which could be called iPhone Ultra.',
                     ['In a new report today, Bloomberg said Apple recently discussed a $2,199 starting price.']),
                    (f'Caseworks 公布苹果首款折叠屏手机保护壳，并称该机为 iPhone {name}',
                     f'Caseworks 官网曾上架折叠屏保护壳，将这款机型称为 iPhone {name}。', []),
                    (f'手机壳厂提前曝光苹果折叠屏命名：就叫 iPhone {name}',
                     f'配件厂商 Caseworks 建立了折叠屏保护壳页面，将机型称为 iPhone {name}。', []),
                ])
                self.assertEqual(sorted(len(e.articles) for e in events), [1, 2])

    def test_broad_launch_preview_cannot_join_named_product_claim(self):
        events = self.cluster([
            ('就在明天！苹果折叠掀起史上最强新机发布潮',
             '这场发布会很可能带来多个首次。折叠 iPhone 只是开端，未来一年苹果所有主力硬件都将更新。内部称为 iPhone Ultra，坊间传闻称为 iPhone Duo。', []),
            ('苹果首款折叠 iPhone 名称或定为 iPhone Duo',
             '配件厂商官网保护壳页面将首款折叠 iPhone 称为 iPhone Duo。', []),
        ])
        self.assertEqual(len(events), 2)

    def test_distinct_naming_targets_do_not_merge(self):
        events = self.cluster([
            ('苹果首款折叠 iPhone 名称或定为 iPhone Duo', '消息称该折叠手机名称为 iPhone Duo。', []),
            ('苹果首款折叠 iPhone 名称或定为 iPhone Edge', '消息称该折叠手机名称为 iPhone Edge。', []),
        ])
        self.assertEqual(len(events), 2)

    def test_naming_predicate_object_completes_sparse_title(self):
        for name in ('Duo', 'Edge'):
            with self.subTest(name=name):
                lead = f'Caseworks published a case listing for the foldable iPhone and named it iPhone {name}.'
                events = self.cluster([
                    (f'Foldable iPhone named iPhone {name} by Caseworks', lead, []),
                    (f'iPhone {name}?', lead, []),
                ])
                self.assertEqual(len(events), 1)

    def test_commission_and_official_api_after_developer_remain_first_party(self):
        for lead in (
            'Developers commissioned by Apple ported a third-party rendering model to Metal and Apple announced official support today.',
            '开发者受苹果委托将第三方渲染模型移植到 Metal，苹果今日正式发布这一平台功能。',
            'Developers can now port third-party rendering models to Metal using the new official API Apple released today.',
        ):
            with self.subTest(lead=lead):
                event = self.cluster([('Apple adds rendering support to Metal', lead, [])])[0]
                self.assertEqual(event.relevance_tier, 'strong')

    def test_official_title_and_adjacent_api_explanation_own_support(self):
        event = self.cluster([
            ('Apple adds official rendering support to Metal',
             'Developers can now port third-party rendering models to Metal. Apple released a new official API today to enable this support.', []),
        ])[0]
        self.assertEqual(event.relevance_tier, 'strong')

    def test_historical_api_background_does_not_authorize_independent_port(self):
        for lead in (
            'Developers ported a third-party rendering model to Metal in an unofficial experiment. Apple released an official API years ago.',
            'Developers ported a third-party rendering model to Metal in an unofficial experiment. The experiment runs at two frames per second. Apple released a new official API today to enable unrelated support.',
        ):
            with self.subTest(lead=lead):
                event = self.cluster([('Unofficial rendering port runs on Apple M5 Pro', lead, [])])[0]
                self.assertEqual(event.relevance_tier, 'weak')

    def test_unofficial_port_actor_overrides_target_hardware(self):
        for chip, technology in (('M5 Pro', 'DLSS 5'), ('M6 Max', 'RayBoost 2')):
            with self.subTest(chip=chip):
                events = self.cluster([
                    (f'苹果 {chip} 非官方移植第三方 {technology}：画质提升',
                     f'报道称开发者成功在苹果 {chip} 芯片上非官方移植第三方的 {technology}。', []),
                    (f'苹果 {chip} 跑 {technology}：延迟飙升',
                     f'开发者 @sample 将第三方 {technology} 渲染模型移植到苹果 Metal 框架下，在 {chip} 上运行。这是非官方实验。', []),
                ])
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_independent_port_does_not_join_official_platform_support(self):
        events = self.cluster([
            ('苹果 M5 Pro 非官方移植 DLSS 5',
             '开发者成功将第三方 DLSS 5 模型非官方移植到苹果 Metal 框架。', []),
            ('Apple adds DLSS 5 support to Metal',
             'Apple announced official DLSS 5 support in its Metal framework.', []),
        ])
        self.assertEqual(len(events), 2)
        official = next(e for e in events if e.articles[0].title.startswith('Apple adds'))
        self.assertNotEqual(official.relevance_tier, 'weak')

    def test_apple_employed_developers_are_not_independent_port_authors(self):
        event = self.cluster([
            ('Apple adds rendering support to Metal',
             'Apple developers ported a third-party rendering model to Metal as an official platform feature.', []),
        ])[0]
        self.assertNotEqual(event.relevance_tier, 'weak')

    def test_official_commission_and_hardware_reviews_are_not_unofficial_ports(self):
        for title, lead in (
            ('Apple adds new rendering support to Metal', 'Apple commissioned developers to port a rendering model to Metal and announced official support today.'),
            ('苹果 M5 Pro 性能测试：GPU 性能大幅提升', '测试显示苹果 M5 Pro GPU 性能提升。此前另有开发者非官方移植第三方软件。'),
        ):
            with self.subTest(title=title):
                event = self.cluster([(title, lead, [])])[0]
                self.assertNotEqual(event.relevance_tier, 'weak')


if __name__ == '__main__':
    unittest.main()
