"""Local report ownership and stable event anchors from captured sources."""
from datetime import datetime, timezone
import json
from dataclasses import replace
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261019_source_boundaries.json').read_text())
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 19, tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    source_ids = staticmethod(prior.PureJsonBatchTests.source_ids)
    def ids(self, *prefixes):
        return [next(k for k in self.rows if k.startswith(p)) for p in prefixes]

    def test_resale_reports_use_order_and_observation_boundaries(self):
        ids = self.ids('1195', '6d3b', '631e', 'd59a', '9706')
        for sequence in (ids, list(reversed(ids))):
            events, data = self.cluster_sources(*sequence)
            self.assertEqual(len(events), 4)
            self.assertIn(set(ids[:3]), [self.source_ids(e) for e in events])
            self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier == 'strong'
                                for e in events for a in e.articles))

    def test_quote_continuation_keeps_observation_and_leaves_other_actions_unassigned(self):
        from apple_news_core.event_identity import bind_resale_report
        evidence = self.source_articles(self.ids('2531')[0])[0].evidence
        claims = bind_resale_report(evidence)
        self.assertIsNotNone(claims)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].action, 'resale-quote-report')
        self.assertEqual(set(claims[0].unit_ids), {u.unit_id for u in evidence.units[:2]})
        units = {u.unit_id: u.text for u in evidence.units}
        selected = ' '.join(units[key][a:b] for key, a, b in claims[0].evidence_spans)
        for fact in ('到货日期', '存储空间', '2000元至3000元', '发售日当天'):
            self.assertIn(fact, selected)
        for unrelated in ('由此可见', '崩盘', '古尔曼', '第二天'):
            self.assertNotIn(unrelated, selected)

    def test_quote_continuation_cannot_borrow_other_model_or_historical_context(self):
        from apple_news_core.event_identity import bind_resale_report
        evidence = self.source_articles(self.ids('2531')[0])[0].evidence
        for text in ('此前，iPhone Duo在二手交易平台上的价格明显上涨。',
                     'iPhone 18在二手交易平台上的价格明显上涨。',
                     '如果iPhone Duo在二手交易平台上的价格继续上涨，商家认为首日现货还会更贵。',
                     '博主建议，消费者不要为iPhone Duo在二手交易平台上的高价格买单。'):
            with self.subTest(text=text):
                units = (replace(evidence.units[0], text=text), *evidence.units[1:])
                self.assertIsNone(bind_resale_report(replace(evidence, units=units)))
        units = (evidence.units[0], replace(evidence.units[1],
            text='届时，全新未拆封的iPhone Duo会被加价2000元至3000元。'), *evidence.units[2:])
        self.assertIsNone(bind_resale_report(replace(evidence, units=units)))

    def test_complete_quote_observation_merges_across_paragraph_layouts(self):
        ids = self.ids('253104', 'fb949')
        for sequence in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*sequence)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_quote_republication_requires_all_ordered_observation_conditions(self):
        from apple_news_core.event_identity import bind_resale_report
        from apple_news_core.event_matcher import identity_pair_decision
        evidence = self.source_articles(self.ids('fb949')[0])[0].evidence
        original = bind_resale_report(evidence)[0]
        for old, new in [('2000元至3000元', '2000元至4000元'), ('存储空间', '销售地区'),
                         ('未拆封', '已拆封'), ('发售日当天', '发售一周后'), ('被加价', '回收报价'),
                         ('根据到货日期和存储空间的不同，', ''), ('普遍被加价', '预计将被加价')]:
            with self.subTest(change=new):
                unit = replace(evidence.units[0], text=evidence.units[0].text.replace(old, new))
                claims = bind_resale_report(replace(evidence, article_id='other', units=(unit, *evidence.units[1:])))
                if new == '预计将被加价':
                    self.assertIsNone(claims)
                else:
                    self.assertNotEqual(identity_pair_decision(original, claims[0]), 'match')
        generic = replace(evidence, units=(replace(evidence.units[0], text='iPhone Duo黄牛加价3000元。'),))
        left = bind_resale_report(generic)[0]
        right = bind_resale_report(replace(generic, article_id='other'))[0]
        self.assertNotEqual(identity_pair_decision(left, right), 'match')
        other = replace(original, article_id='other', qualifiers=tuple(reversed(original.qualifiers)))
        self.assertNotEqual(identity_pair_decision(original, other), 'match')

    def test_same_esim_conditions_merge_across_republication(self):
        ids = self.ids('63f218', 'eb2b88')
        for sequence in (ids, list(reversed(ids))):
            events, _ = self.cluster_sources(*sequence)
            self.assertEqual(len(events), 1)
            self.assertEqual(self.source_ids(events[0]), set(ids))

    def test_esim_conditions_keep_model_region_limit_and_activation_owner(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'iPhone Duo eSIM使用限制公布'
        passage = 'iPhone Duo国行版最多可以存储2张eSIM号码，而且开卡需要前往线下营业厅办理。'
        frame = source_device_operation_frame(title, passage, source_units=(passage,))
        self.assertIsNotNone(frame)
        for changed in (passage.replace('2张', '8张'),):
            other = source_device_operation_frame(title, changed, source_units=(changed,))
            self.assertNotEqual(frame.subject, other.subject)
        for changed in (passage.replace('国行版', '美国版'), passage.replace('iPhone Duo', 'iPhone Air'),
                        passage.replace('需要前往', '不需要前往'), '计划让' + passage,
                        passage.replace('，而且', '。苹果否认'),
                        passage.replace('，而且', '，未来'),
                        passage.replace('，而且', '。三星手机'),
                        passage.replace('，而且', '，三星手机'),
                        'iPhone Duo支持eSIM。三星手机' + passage[len('iPhone Duo'):],
                        'iPhone Duo支持eSIM。三星发布了新手机。' + passage[len('iPhone Duo'):]):
            with self.subTest(changed=changed):
                self.assertIsNone(source_device_operation_frame(title, changed, source_units=(changed,)))

    def test_esim_configuration_background_cannot_own_another_action(self):
        from apple_news_core.event_identity import source_device_operation_frame
        actual = self.source_articles(self.ids('63f218')[0])[0]
        conditions = 'iPhone Duo国行版最多可以存储2张eSIM号码，而且开卡需要前往线下营业厅办理。'
        for title, lead in [
            ('苹果修复iPhone Duo的eSIM激活漏洞', '苹果发布系统更新，修复iPhone Duo的eSIM激活失败漏洞。'),
            ('中国移动为iPhone Duo推出eSIM号码保护新服务', '中国移动推出新服务，用户可在手机丢失后冻结eSIM号码。'),
            ('苹果修复iPhone Duo的eSIM配置漏洞', '苹果发布系统更新，修复iPhone Duo的eSIM配置漏洞。'),
            ('中国移动为iPhone Duo推出eSIM配置新服务', '中国移动推出新服务，用户可在手机丢失后冻结eSIM号码。'),
        ]:
            with self.subTest(title=title):
                frame = source_device_operation_frame(title, lead, source_units=(lead, conditions))
                self.assertTrue(frame is None or frame.action != 'device-provisioning-conditions-report')
                other = article_for(self.m, title, lead, facts=[lead, conditions])
                self.assertEqual(len(self.m.cluster_articles([actual, other])), 2)

    def test_supply_decision_reports_merge_without_phishing_lure(self):
        ids = self.ids('3d3f', '0f43', 'd131', '46cd', '05fc')
        events, _ = self.cluster_sources(*ids)
        self.assertEqual({frozenset(self.source_ids(e)) for e in events},
                         {frozenset(ids[:4]), frozenset(ids[4:])})
        a = self.source_articles(ids[-1])[0]
        self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier, 'weak')

    def test_owned_hardware_reports_merge_by_document_and_design(self):
        for prefixes in [('57b4', '97ec', 'cfb1', '752e'), ('9a22', 'e73e', 'debc')]:
            with self.subTest(prefixes=prefixes):
                events, _ = self.cluster_sources(*self.ids(*prefixes))
                self.assertEqual(len(events), 1)

    def test_launch_calendar_does_not_absorb_chip_roadmap(self):
        ids = self.ids('d8fd', '99e1', '115c')
        events, _ = self.cluster_sources(*ids)
        self.assertFalse(any(ids[1] in self.source_ids(e) and
                             (ids[0] in self.source_ids(e) or ids[2] in self.source_ids(e)) for e in events))
        self.assertIn({ids[0], ids[2]}, [self.source_ids(e) for e in events])
    def test_chip_background_cannot_override_denial_or_capability(self):
        current = self.source_articles(self.ids('99e1')[0])[0]
        denied = article_for(self.m, 'Apple denies skipping M6 Pro chips to accelerate M7',
            'Apple says it is not skipping M6 Pro or M6 Max for M7.')
        memory = article_for(self.m, 'Apple M7 Ultra chip supports 1.5TB memory',
            'Apple designed M7 Ultra with 1.5TB memory. Earlier reports said no M6 Pro would ship before M7.')
        self.assertEqual(len(self.m.cluster_articles([current, denied, memory])), 3)
        equivalent = article_for(self.m, 'Apple is skipping M6 chips for M7',
            'Apple will release only the base M6 before moving to M7 six months later. '
            'M6 Pro, M6 Max, and M6 Ultra are cancelled to accelerate M7.')
        canonical = article_for(self.m, "Here's Why Apple is Reportedly Skipping M6 Pro and M6 Max Chips",
            equivalent.summary)
        self.assertEqual(len(self.m.cluster_articles([canonical, current, equivalent])), 1)
        for statement in ('No M6 chip supports the new memory mode available on M7.',
                          'There is no M6 chip that supports the new memory mode available on M7.'):
            capacity = article_for(self.m, 'Apple compares memory support in M6 and M7 chips', statement)
            with self.subTest(statement=statement):
                self.assertEqual(len(self.m.cluster_articles([canonical, capacity])), 2)

    def test_denial_polarity_uses_the_local_predicate(self):
        for title in ("Apple has not denied skipping M6 Pro chips to accelerate M7",
                      "Apple hasn't denied skipping M6 Pro chips to accelerate M7",
                      "苹果未否认跳过M6 Pro芯片以加速M7",
                      "苹果没有否认跳过M6 Pro芯片以加速M7"):
            with self.subTest(title=title):
                self.assertNotIn('claim-denial', self.m.title_led_identity(title, '').title_actions)
        for title in ("Apple denies skipping M6 Pro chips to accelerate M7",
                      "苹果否认跳过M6 Pro芯片以加速M7"):
            with self.subTest(title=title):
                self.assertIn('claim-denial', self.m.title_led_identity(title, '').title_actions)

    def test_competitor_measurements_and_accessory_deals_stay_weak(self):
        for sid in self.ids('8ca1', '1b76'):
            with self.subTest(sid=sid):
                self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier == 'weak'
                                    for a in self.source_articles(sid)))

    def test_platform_interoperability_reports_are_software(self):
        for sid in self.ids('0bcd', '783c', '1403'):
            with self.subTest(sid=sid):
                profiles = [self.m.article_reconciliation_profile(a) for a in self.source_articles(sid)]
                self.assertTrue(any(p.relevance_tier in {'strong', 'ecosystem'} and
                                    p.category_hint == 'software_systems' for p in profiles))

    def test_commentary_retains_only_independent_first_party_facts(self):
        for prefix, category, fragment in [('7c0b', 'software_systems', 'removed'),
                                           ('d66b', 'hardware_products', '胶')]:
            articles = self.source_articles(self.ids(prefix)[0])
            selected = [a for a in articles if self.m.article_reconciliation_profile(a).relevance_tier == 'strong']
            self.assertTrue(selected, prefix)
            self.assertTrue(all(a.bound_claim for a in selected), prefix)
            self.assertTrue(all(self.m.article_reconciliation_profile(a).category_hint == category for a in selected))
            self.assertIn(fragment, ' '.join(f for a in selected for f in a.key_facts))

    def test_dedicated_phone_feature_inventory_keeps_version_conditions(self):
        articles = self.source_articles(self.ids('7bd2')[0])
        self.assertTrue(any(self.m.article_reconciliation_profile(a).relevance_tier == 'strong' and
                            self.m.article_reconciliation_profile(a).category_hint == 'software_systems' for a in articles))

    def test_order_records_survive_quote_changes_but_not_other_batches(self):
        from apple_news_core.event_matcher import identity_pair_decision
        claims = [self.source_articles(sid)[0].bound_claim for sid in self.ids('1195', '6d3b')]
        self.assertEqual(identity_pair_decision(*claims), 'match')
        other = replace(claims[1], qualifiers=tuple(
            (*q[:2], '1234567', *q[3:]) if q[1] == 'order-total' else q for q in claims[1].qualifiers))
        self.assertEqual(identity_pair_decision(claims[0], other), 'conflict')
        unknown = replace(claims[1], qualifiers=tuple(q for q in claims[1].qualifiers if q[1] == 'report-party'))
        self.assertEqual(identity_pair_decision(claims[0], unknown), 'unknown')
        # A missing record cannot bridge two explicitly different orders.
        self.assertEqual(identity_pair_decision(other, unknown), 'unknown')

    def test_price_report_facts_keep_buy_and_sell_samples_separate(self):
        articles = [a for sid in self.ids('1195', '6d3b', '631e', 'd59a', '9706') for a in self.source_articles(sid)]
        orders = [a for a in articles if a.bound_claim.action == 'resale-order-report']
        self.assertTrue(all('3000' in ' '.join(a.key_facts) for a in orders))
        quotes = [a for a in articles if a.bound_claim.action == 'resale-quote-report']
        self.assertEqual(len(quotes), 3)
        self.assertTrue(any('79999' in ' '.join(a.key_facts) and '3000' in ' '.join(a.key_facts) for a in quotes))
        self.assertTrue(any('25500' in ' '.join(a.key_facts) and '5000' in ' '.join(a.key_facts) for a in quotes))
        self.assertFalse(any('建议' in f or '省一月工资' in f for a in articles for f in a.key_facts))

    def test_partial_reports_do_not_import_other_actions_or_editorial_predictions(self):
        for prefix, forbidden in [('1403', 'CEC'), ('0bcd', '9 月 7 日'),
                                  ('7c0b', '27.3'), ('d66b', '垃圾'), ('7bd2', 'Tello')]:
            facts = ' '.join(f for a in self.source_articles(self.ids(prefix)[0]) for f in a.key_facts)
            self.assertNotIn(forbidden, facts)
        facts = ' '.join(f for a in self.source_articles(self.ids('0bcd')[0]) for f in a.key_facts)
        for required in ['7.0', '单耳', '耳机盒', '平板', '手动连接']:
            self.assertIn(required, facts)

    def test_causal_launch_cannot_own_another_vendors_sales(self):
        other = article_for(self.m, 'iPhone Duo发布后友商手机销量大涨', '友商手机销量增长76%。')
        own = article_for(self.m, 'iPhone Duo发布后苹果手机销量大涨', '苹果手机销量增长76%。')
        self.assertEqual(self.m.article_reconciliation_profile(other).relevance_tier, 'weak')
        from apple_news_core.event_identity import source_current_report_frame
        self.assertIsNone(source_current_report_frame(own.title, own.summary, ()))

    def changed_evidence(self, prefix, changes):
        evidence = self.source_articles(self.ids(prefix)[0])[0].evidence
        def changed(text):
            for old, new in changes:
                text = text.replace(old, new)
            return text
        return replace(evidence, title=changed(evidence.title), raw_lead=changed(evidence.raw_lead),
                       units=tuple(replace(u, text=changed(u.text)) for u in evidence.units),
                       article_id=evidence.article_id + '-other')

    def test_actual_batch_count_and_ordinal_block_equal_money(self):
        from apple_news_core.event_identity import bind_resale_report
        from apple_news_core.event_matcher import identity_pair_decision
        original = self.source_articles(self.ids('1195')[0])[0].bound_claim
        for changes in [[('50台', '60台')], [('首批货源', '第二批货源')]]:
            revised = bind_resale_report(self.changed_evidence('1195', changes))[0]
            self.assertEqual(identity_pair_decision(original, revised), 'conflict')
        changed_quote = bind_resale_report(self.changed_evidence('1195', [('3500价格', '3800价格')]))[0]
        self.assertEqual(identity_pair_decision(original, changed_quote), 'match')

    def test_generic_app_names_do_not_bind_competitor_apps(self):
        from apple_news_core.event_identity import bind_device_capability_inventory, bind_embedded_app_state
        other = self.changed_evidence('7bd2', [('Apple', 'Google'), ('iPhone', 'Android phone'), ('iOS', 'Android')])
        self.assertIsNone(bind_device_capability_inventory(other))
        self.assertIsNone(bind_embedded_app_state(self.changed_evidence('7c0b', [('This Health app', 'This Samsung Health app')])))

    def test_platform_matrix_versions_remain_distinct(self):
        from apple_news_core.event_identity import bind_interoperability_report
        from apple_news_core.event_matcher import identity_pair_decision
        original = self.source_articles(self.ids('0bcd')[0])[0].bound_claim
        revised = bind_interoperability_report(self.changed_evidence('0bcd', [('7.0', '8.0'), ('HarmonyOS 7', 'HarmonyOS 8')]))
        self.assertEqual(identity_pair_decision(original, revised), 'conflict')

    def test_publication_owner_and_cancelled_roadmap_are_not_affirmative_plans(self):
        unofficial = article_for(self.m, 'Researcher reveals unofficial iPhone Duo battery label',
            'A researcher published an unofficial EU energy label for the Apple iPhone Duo; Apple has not released this document.')
        self.assertEqual(self.m.article_reconciliation_profile(unofficial).relevance_tier, 'weak')
        denied = article_for(self.m, 'Apple denies publishing iPhone Duo battery capacity',
            'Apple denies publishing an EU energy label for iPhone Duo.')
        real = self.source_articles(self.ids('57b4')[0])[0]
        self.assertEqual(len(self.m.cluster_articles([denied, real])), 2)
        planned = article_for(self.m, 'Apple Planning HomeView With Robotic Arm',
            'Bloomberg reports Apple plans to release the J595 robotic display in 2027.')
        cancelled = article_for(self.m, 'Gurman: Apple cancels plans for HomeView robotic arm',
            'Bloomberg reports Apple has cancelled plans to release the J595 robotic display.')
        self.assertEqual(len(self.m.cluster_articles([planned, cancelled])), 2)

    def test_later_order_payment_and_partial_sale_do_not_replace_batch_identity(self):
        from apple_news_core.event_identity import bind_resale_report
        from apple_news_core.event_matcher import identity_pair_decision
        original = self.source_articles(self.ids('1195')[0])[0].bound_claim
        revised = self.changed_evidence('1195', [('每台能赚取2000元利润',
            '每台能赚取2000元利润。他已经支付了974950元尾款，并转售20台，完成这批订单的付款')])
        self.assertEqual(identity_pair_decision(original, bind_resale_report(revised)[0]), 'match')
        restated = self.changed_evidence('1195', [('他已经向上游支付了25000元订金', '他已支付的订金合计25000元')])
        claim = bind_resale_report(restated)[0]
        self.assertEqual({q[2] for q in claim.qualifiers if q[1] == 'order-total'}, {'999950'})
        self.assertEqual(identity_pair_decision(original, claim), 'match')

    def test_recovered_robot_report_and_new_battery_comparison_keep_owned_actions(self):
        for prefixes in [('57b4', 'ecb3'), ('e73e', 'ed925')]:
            with self.subTest(prefixes=prefixes):
                events, _ = self.cluster_sources(*self.ids(*prefixes))
                self.assertEqual(len(events), 1)
                self.assertTrue(all(self.m.article_reconciliation_profile(a).relevance_tier == 'strong'
                                    for e in events for a in e.articles))
        denied = article_for(self.m, 'HomeView follow-up with robot arm rumor denied by Gurman',
            'Gurman says Apple is not planning a HomeView follow-up with a robot arm.')
        real = self.source_articles(self.ids('ed925')[0])[0]
        self.assertEqual(len(self.m.cluster_articles([denied, real])), 2)

    def test_source_navigation_does_not_consume_article_budget_after_recovery(self):
        source = self.sources['AppleInsider']
        navigation = [
            'https://prices.appleinsider.com/current-gen',
            'https://appleinsider.com/inside',
            'https://appleinsider.com/inside/iphone',
            'https://appleinsider.com/inside/iphone/videos',
            'https://appleinsider.com/inside/iphone/reviews',
            'https://appleinsider.com/inside/iphone/best',
            'https://appleinsider.com/inside/iphone/vs',
        ]
        articles = [
            'https://appleinsider.com/articles/26/10/18/homeview-follow-up-with-robot-arm-rumored-to-ship-in-2027',
            'https://appleinsider.com/inside/apple-tv-plus/tips/how-to-watch-its-the-great-pumpkin-charlie-brown-for-free-in-2026',
            'https://appleinsider.com/inside/macbook-pro/review/macbook-pro-review',
        ]
        for url in navigation:
            self.assertFalse(self.m.collection.source_article_url_allowed(url, source), url)
        for url in articles:
            self.assertTrue(self.m.collection.source_article_url_allowed(url, source), url)
        markup = ''.join('<a href="' + url + '">Apple unveils its new iPhone</a>' for url in navigation + articles)
        self.assertEqual({c.url for c in self.m.parse_html_links(markup, 'https://appleinsider.com/news', source)}, set(articles))
