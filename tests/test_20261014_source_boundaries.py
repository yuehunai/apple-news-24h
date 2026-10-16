"""High-volume source reports retain their primary action and local evidence."""
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior


class SourceBoundariesTests(unittest.TestCase):
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())['sources']
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 14, tzinfo=timezone.utc))}

    def test_directional_market_result_survives_fact_selection_and_admission(self):
        row = self.rows['600566159023022a444e3631']
        title, lead, _ = row['recorded_extraction']
        body = '<article>' + ''.join('<p>' + escape(u['text']) + '</p>' for u in row['evidence']['units']) + '</article>'
        facts = self.m.extract_key_facts(body, title, 'IT之家')
        self.assertTrue(any('苹果新品' in fact and '出货量同比小幅下滑' in fact for fact in facts))
        for source in self.sources.values():
            candidate = self.m.Candidate(source.name, 'https://' + source.domains[0] + '/report/', title, lead)
            self.assertTrue(self.m.is_relevant_candidate(candidate, source, facts), source.name)
        frame = self.m.source_market_measurement_frame(title, lead, tuple(facts))
        self.assertIsNotNone(frame)
        self.assertEqual((frame.subject, frame.region, frame.year, frame.period),
                         ('idc:smartphone-shipments', 'china', '2026', 'q3'))

    def test_paid_retail_entitlement_does_not_own_the_device_price_or_supply_report(self):
        events, rows = self.cluster_sources('b1844ff318d27aa2c52789f4')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        self.assertIn('retail-entitlement', events[0].relevance_reason)
        # A weak primary transaction does not erase local reported evidence.
        facts = ' '.join(rows[0]['key_facts'])
        self.assertIn('据产业链消息', facts)
        self.assertIn('良率仅为60%出头', facts)
        self.assertIn('良率爬坡至少还需要半年', facts)
        self.assertEqual(rows[0]['sources'][0]['url'], self.rows['b1844ff318d27aa2c52789f4']['evidence']['url'])

    def test_retail_entitlement_boundary_follows_seller_and_paid_object(self):
        cases = (
            ('花500元获得iPhone优先购买资格',
             '某零售商今天上架了一款收费的iPhone优先购买权益包。手机费用需另行支付。'),
            ('A paid priority purchase pass for iPhone sells out',
             'Retailer Northstar is selling a $250 priority purchase pass for iPhone. The phone must be purchased separately.'),
            ('A paid priority purchase pass for iPhone sells out',
             'Retailer Northstar is selling a $1,250 priority purchase pass for iPhone. The phone must be purchased separately.'),
        )
        for title, lead in cases:
            with self.subTest(title=title):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual(event.relevance_tier, 'weak')
                self.assertIn('retail-entitlement', event.relevance_reason)
        controls = (
            ('Apple opens iPhone Duo pre-orders for $1,599',
             'Apple is accepting pre-orders for iPhone Duo. The $1,599 payment covers the phone.'),
            ('Apple announces priority purchase eligibility for iPhone Duo',
             'Apple announced priority purchase eligibility for its customers. A retailer previously sold paid purchase passes.'),
            ('苹果公布AppleCare维修费用',
             '苹果官网公布了iPhone Duo的AppleCare维修费用。'),
            ('iPhone Duo pre-orders are available at Amazon',
             'Amazon is selling iPhone Duo for $1,599. Customers receive the phone, not a priority purchase pass.'),
            ('Retailer Northstar starts iPhone pre-orders',
             'Retailer Northstar is selling the iPhone for $1,599, not a priority purchase pass.'),
            ('某平台开启iPhone预购',
             '某平台上架售价9999元的iPhone，附赠免费的优先购买资格。'),
            ('Retailer Northstar starts iPhone pre-orders',
             'Retailer Northstar is selling the iPhone for $1599 with priority purchase rights included for free.'),
            ('iPhone Duo预购开启',
             '某平台上架售价15999元的iPhone Duo，优先购买资格免费赠送。'),
            ('iPhone Duo预购开启',
             '某平台上架售价15999元的iPhone Duo，优先购买资格不另收费。'),
            ('iPhone Duo预购开启',
             '某平台上架售价15999元的iPhone Duo，苹果官方另为用户提供优先购买资格。'),
        )
        for title, lead in controls:
            with self.subTest(title=title):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertNotIn('retail-entitlement', event.relevance_reason)
                if 'included for free' in lead:
                    self.assertEqual(event.relevance_tier, 'strong')

    def test_named_platform_report_gets_detail_without_release_keywords(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/20261014_source_boundaries.json').read_text())
        row=fixture['naming_discovery']
        for source in self.sources.values():
            candidate=self.m.Candidate(**{**row,'source':source.name})
            with self.subTest(source=source.name):
                self.assertTrue(self.m.is_relevant_candidate(candidate,source))
        event=self.m.cluster_articles([article_for(self.m,row['title'],row['summary'])])[0]
        self.assertEqual(event.category,'software_systems')
        for title,lead in (
            ('Microsoft demonstrates HomeOS research project',
             'Microsoft researchers demonstrated their HomeOS project for managing home devices; Apple HomePod is a competing product.'),
            ('Independent designer imagines homeOS for Apple HomeView',
             'An independent designer created a concept for homeOS. Apple has not announced this interface.')):
            with self.subTest(title=title):
                e=self.m.cluster_articles([article_for(self.m,title,lead)])[0]
                self.assertEqual(e.relevance_tier,'weak')

    def test_first_party_developer_assistance_does_not_join_device_production(self):
        support = self.source_articles('cdb7f71dee196225402aff40')
        production = self.source_articles('00d847f97d483446680cfd67')
        event = self.m.cluster_articles(support)[0]
        self.assertEqual((event.category, event.relevance_tier), ('software_systems', 'strong'))
        for articles in (support + production, production + support):
            events = self.m.cluster_articles(articles)
            self.assertEqual(len(events), 2)
            self.assertEqual(sorted(len(e.articles) for e in events), [1, 1])

    def test_same_introduction_ordering_details_share_device_announcement(self):
        self.assert_group(('c15f35ba72c09daa00affe87', '368d58bcf026767a8df92ebf'), 'hardware_products')
        self.assert_group(('0118d29fc3f8200aca518c07', '23f9d8a016246e24aef4c76e',
                           'a788b5093d16540430753e38'), 'hardware_products')
        launch = article_for(self.m, 'Apple announces HomePod mini 3',
            'Apple today introduced HomePod mini 3. Preorders will open next month.')
        for title, lead in (
            ('HomePod mini 3 preorders open today', 'Apple introduced HomePod mini 3 last month. Preorders open today.'),
            ('HomePod mini 3 now shipping', 'Apple introduced HomePod mini 3 last month. Deliveries begin today.'),
            ('HomePod mini 3 preorders reopen', 'Apple introduced HomePod mini 3 last month. Orders reopen today after a delay.'),
        ):
            other = article_for(self.m, title, lead)
            for articles in ([launch, other], [other, launch]):
                self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_current_introduction_configuration_comparison_keeps_launch_action(self):
        self.assert_group(('590591dc9f116f110e316116', 'b58858e0c678d440066832ee',
                           'ce3e390cc5eca9fe971d7e60'), 'hardware_products')
        self.assert_group(('e2968acad5955e5960573431', 'df029e247000c2a2cf1077f5'), 'hardware_products')

    def test_canonical_product_discovery_does_not_require_a_feed_excerpt(self):
        for source in self.sources.values():
            for title in ('AirTag firmware update released', 'Magic Keyboard firmware update released'):
                with self.subTest(source=source.name, title=title):
                    candidate = self.m.Candidate(source.name, 'https://' + source.domains[0] + '/report/', title, '')
                    self.assertTrue(self.m.is_relevant_candidate(candidate, source))
        source = self.sources['MacRumors']
        for title in ('Safari tour bookings open today', 'Swift bird population declines',
                      'A new game controller released today', 'New polishing cloth launched for kitchen cleaning',
                      '安卓应用商店新增游戏评测功能', '数字车钥匙现支持更多品牌汽车'):
            self.assertFalse(self.m.is_relevant_candidate(self.m.Candidate(source.name,
                'https://www.macrumors.com/report/', title, ''), source))
        accessory = article_for(self.m, 'Elevation Lab Pulls AirTag Silencer After Criticism',
            'Elevation Lab stopped selling its AirTag silencing enclosure after criticism.')
        self.assertEqual(self.m.cluster_articles([accessory])[0].relevance_tier, 'weak')

    def test_unmodified_launch_verb_keeps_current_comparison_with_introduction(self):
        self.assert_group(('767391679aa1a77e7ec6d8b3', 'df029e247000c2a2cf1077f5'), 'hardware_products')

    def test_affirmative_default_speaker_support_preserves_its_device(self):
        events, _ = self.cluster_sources('7d19cec9f4b2021195223997')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        for lead in ('Apple says HomePod 2 does not work as a default Mac speaker.',
                     'A designer hopes HomePod 2 could work as a default Mac speaker.'):
            from apple_news_core.event_identity import source_device_operation_frame
            self.assertIsNone(source_device_operation_frame('HomePod 2 default Mac speaker support', lead))

    def test_same_regional_repair_fee_table_keeps_coverage_tiers_together(self):
        self.assert_group(('5baf3408e68dcabec8141e69', 'e0db7a94a1667af074f0dd5c'), 'software_systems')

    def test_production_plan_owns_target_device_instead_of_prior_sales(self):
        self.assert_group(('2c79ef55fba0f78c159c2f3e', 'a03d26da850cc89e2f853e8d',
                           '00d847f97d483446680cfd67'), 'hardware_products')

    def test_dated_production_preserves_model_stage_and_schedule(self):
        from apple_news_core.event_identity import source_dated_production_frame as frame
        for model, canonical in (('iPhone 19', 'iphone-19'), ('iPhone19 Pro', 'iphone-19-pro')):
            with self.subTest(model=model):
                result = frame(model + ' production plans reported',
                    model + ' production is scheduled to start in late November 2027.', published_year='2026')
                self.assertEqual((result.subject, result.action, result.year, result.period),
                    (canonical + ':production', 'production-start-plan', '2027', '11:late'))
        planned = article_for(self.m, 'iPhone 19 production schedule reported',
            'iPhone 19 production is scheduled to start in late November 2027.')
        for title, lead in (
            ('iPhone 19 Pro production schedule reported', 'iPhone 19 Pro production is scheduled to start in late November 2027.'),
            ('iPhone 19 production schedule reported', 'iPhone 19 production is scheduled to start in early December 2027.'),
            ('iPhone 19 production begins', 'iPhone 19 production started in late November 2027.'),
        ):
            other = article_for(self.m, title, lead)
            for order in ([planned, other], [other, planned]):
                self.assertEqual(len(self.m.cluster_articles(order)), 2, lead)
        for lead in (
            'Apple denied plans to start iPhone 19 production in late November.',
            'Apple cancelled iPhone 19 production scheduled to start in late November.',
            'Last year iPhone 19 production started in late November.',
        ):
            self.assertIsNone(frame('iPhone 19 production report', lead, published_year='2026'))
        for date, expected in (('November 12, 2027', '11:12'), ('November 25, 2027', '11:25')):
            result = frame('iPhone 19 production schedule reported',
                'iPhone 19 production is scheduled to start on ' + date + '.', published_year='2026')
            self.assertEqual((result.year, result.period), ('2027', expected))
        possible = frame('iPhone 19 production schedule reported',
            'iPhone 19 production may start in November 2027.', published_year='2026')
        self.assertEqual((possible.action, possible.year, possible.period), ('production-start-plan', '2027', '11'))
        self.assertIsNone(frame('iPhone 19 production delayed',
            'iPhone 19 production is delayed because iPhone 18 production is scheduled to start in November 2027.'))

    def test_repair_fee_disclosures_keep_region_model_and_provider(self):
        baseline = article_for(self.m, '苹果公布国行iPhone Duo维修费用', '苹果官网公布国行iPhone Duo维修费用。')
        for title, lead in (
            ('苹果公布美国iPhone Duo维修费用', '苹果官网公布美国iPhone Duo维修费用。'),
            ('苹果公布国行iPhone 18维修费用', '苹果官网公布国行iPhone 18维修费用。'),
            ('Apple suppliers publish iPhone Duo repair fees', 'Apple suppliers published iPhone Duo repair fees.'),
            ('Apple to publish iPhone Duo repair fees', 'Apple will publish iPhone Duo repair fees next week.'),
        ):
            other = article_for(self.m, title, lead)
            for order in ([baseline, other], [other, baseline]):
                self.assertEqual(len(self.m.cluster_articles(order)), 2)
        japan = article_for(self.m, 'Apple publishes iPhone Duo repair fees in Japan',
            'Apple published iPhone Duo repair fees in Japan.')
        canada = article_for(self.m, 'Apple publishes iPhone Duo repair fees in Canada',
            'Apple published iPhone Duo repair fees in Canada.')
        for order in ([japan, canada], [canada, japan]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)
        from apple_news_core.event_identity import source_operation_frame
        title, lead = 'Third-party iPhone Duo repair prices announced', 'Independent repair shops published their iPhone Duo repair fees.'
        result = source_operation_frame(title, lead, (), self.m.title_led_identity(title, lead))
        self.assertTrue(result is None or result.action != 'service-price-disclosure')

    def test_repair_fee_history_does_not_own_a_current_disclosure(self):
        current = article_for(self.m, 'iPhone 19 repair fees published',
            'Apple published iPhone 19 repair fees today.')
        old = article_for(self.m, 'iPhone 19 repair fees explained',
            'Last year Apple published iPhone 19 repair fees. This article revisits that old fee table.')
        for order in ([current, old], [old, current]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)
        fresh = article_for(self.m, 'iPhone 19 repair fees published',
            'Last year Apple published an older fee table. Today Apple published new iPhone 19 repair fees.')
        for order in ([current, fresh], [fresh, current]):
            self.assertEqual(len(self.m.cluster_articles(order)), 1)

    def test_captured_lifecycle_service_refusal_is_a_current_apple_action(self):
        events, rows = self.cluster_sources('642f3b25e137627d376780d3')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category),
                         ('strong', 'hardware_products'))
        self.assertEqual(rows[0]['sources'][0]['evidence_id'], '642f3b25e137627d376780d3')
        self.assertEqual(events[0].articles[0].evidence.confidence, 'discovery')
        self.assertIn('sixth generation iPad', ' '.join(rows[0]['key_facts']))
        captured = self.source_articles('642f3b25e137627d376780d3')
        other = article_for(self.m, 'Apple stops repairs for obsolete MacBook and iPad models',
            'Apple added the last 12-inch MacBook, sixth generation iPad and Beats X colors to its obsolete list. Apple will not repair them.')
        for articles in (captured + [other], [other] + captured):
            combined = self.m.cluster_articles(articles)
            self.assertEqual(len(combined), 1)
            self.assertEqual(Counter(a.url for a in combined[0].articles), Counter(a.url for a in articles))

    def test_lifecycle_refusal_requires_apple_to_own_the_service_consequence(self):
        title = 'Apple updates its obsolete product list'
        base = 'Apple added the 2017 MacBook to its obsolete product list today. '
        for consequence in ("Apple won't repair this MacBook.",
                            'Apple will not service this MacBook.',
                            'Apple no longer repairs this MacBook.'):
            with self.subTest(consequence=consequence):
                self.assertTrue(self.m.is_direct_apple_product_lifecycle_action(title, base + consequence))
        for product in ('Beats X', 'Apple TV', 'HomePod', 'AirPods'):
            with self.subTest(product=product):
                self.assertTrue(self.m.is_direct_apple_product_lifecycle_action(title,
                    'Apple added ' + product + " to its obsolete list today. Apple won't repair these devices."))
        for lead in (
            base + "Independent repair shops won't repair this MacBook.",
            base + "Apple won't stop repairing this MacBook.",
            "Apple's obsolete product list includes old Macs. Apple denies claims that it won't repair the 2017 MacBook.",
            'Apple added the 2017 MacBook to its obsolete product list today. It can still receive service while parts last.',
        ):
            with self.subTest(lead=lead):
                self.assertFalse(self.m.is_direct_apple_product_lifecycle_action(title, lead))

    def test_lifecycle_refusal_is_asserted_and_belongs_to_the_current_report(self):
        for title, lead in (
            ('A false rumor about an old laptop',
             "Apple's obsolete product list has not changed. The rumor that Apple won't repair the 2017 MacBook is false; service remains available."),
            ('Remembering an old laptop',
             "Last year Apple added the 2017 MacBook to its obsolete list. Apple won't repair this MacBook. This article revisits that old announcement."),
            ('Remembering an old laptop',
             "A decade ago Apple added this MacBook to its obsolete list. Apple won't repair this MacBook. This article revisits that old announcement."),
            ('Remembering an old laptop',
             "Apple added this MacBook to its obsolete list during its former CEO's tenure. Apple won't repair this MacBook. This article revisits that old announcement."),
        ):
            with self.subTest(title=title):
                self.assertFalse(self.m.is_direct_apple_product_lifecycle_action(title, lead))
                self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'weak')
        for title, lead in (
            ('Apple updates repair eligibility for older Macs',
             "Last year Apple added an older iMac to its obsolete list. Today Apple added the 2017 MacBook to that list. Apple won't repair this MacBook."),
            ('Apple confirms repair support has ended for an old MacBook',
             "Apple added the 2017 MacBook to its obsolete list last year. A new support notice confirms Apple will not repair this MacBook."),
        ):
            with self.subTest(title=title):
                self.assertTrue(self.m.is_direct_apple_product_lifecycle_action(title, lead))
                self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'strong')

    def test_current_week_feature_inventory_shares_its_device_introduction(self):
        self.assert_group(('3c423e428ccdaf0d1ce95c59', 'df029e247000c2a2cf1077f5'), 'hardware_products')
        launch = article_for(self.m, 'Apple announces HomePod mini 3',
            'Apple today introduced HomePod mini 3 with a new chip and wireless connectivity.')
        for period in ('this week', 'this morning'):
            inventory = article_for(self.m, 'HomePod mini 3: All the new features',
                'Apple ' + period + ' introduced HomePod mini 3. It has a faster chip and wireless networking.')
            for articles in ([launch, inventory], [inventory, launch]):
                self.assertEqual(len(self.m.cluster_articles(articles)), 1)
        for title, lead in (
            ('HomePod mini 3: All the new features', 'Apple introduced HomePod mini 3 last week. This article revisits the old announcement.'),
            ('HomePod mini 3: All the new features', 'Apple may introduce HomePod mini 3 this week. These are expected features.'),
            ('HomePod mini 3 vs HomePod mini 2: all differences', 'Apple this week introduced HomePod mini 3. AudioLab measured audio latency on both models using the same network, obtaining 40ms and 70ms.'),
            ('HomePod mini 3 repair costs', 'Apple this week introduced HomePod mini 3. Apple published repair fees and AppleCare coverage.'),
        ):
            other = article_for(self.m, title, lead)
            with self.subTest(title=title, lead=lead):
                for articles in ([launch, other], [other, launch]):
                    self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_comparison_baseline_cannot_erase_a_separate_reported_action(self):
        launch = article_for(self.m, 'Apple announces HomePod mini 3',
            'Apple today introduced HomePod mini 3 with a new chip and wireless connectivity.')
        for title, lead in (
            ('HomePod mini 3 vs the previous model: all changes',
             'Apple just introduced HomePod mini 3. The new model adds a faster chip and wireless networking.'),
            ('HomePod mini 3 vs HomePod mini 2: all differences',
             'Apple yesterday announced HomePod mini 3. It retains the prior design with a new chip and wireless connectivity.'),
        ):
            other = article_for(self.m, title, lead)
            for rows in ([launch, other], [other, launch]):
                self.assertEqual(len(self.m.cluster_articles(rows)), 1)
        for title, lead in (
            ('HomePod mini 3 vs HomePod mini 2: measured audio latency',
             'Apple just introduced HomePod mini 3. We measured audio latency on both models using the same network, obtaining 40ms and 70ms.'),
            ('HomePod mini 3 vs HomePod mini 2: repair costs',
             'Apple just introduced HomePod mini 3. Apple published repair fees and AppleCare coverage for the two models.'),
            ('HomePod mini 3 vs HomePod mini 2: all differences',
             'Apple introduced HomePod mini 3 last year. Today we revisit the old specifications.'),
            ('HomePod mini 3 vs HomePod mini 2: rumored changes',
             'Apple may introduce HomePod mini 3 next month. These are expected specifications.'),
            ('HomePod mini 3 vs Orion Speaker: all differences',
             'Apple just introduced HomePod mini 3. We compare it with Orion Speaker.'),
        ):
            with self.subTest(title=title, lead=lead):
                other = article_for(self.m, title, lead)
                for rows in ([launch, other], [other, launch]):
                    self.assertEqual(len(self.m.cluster_articles(rows)), 2)

        for report in ('I measured', 'AudioLab measured', 'Reviewers tested'):
            for title in ('HomePod mini 3 vs HomePod mini 2: measured audio latency',
                          'HomePod mini 3 vs HomePod mini 2: all differences'):
                measured = article_for(self.m, title, 'Apple just introduced HomePod mini 3. '
                    + report + ' audio latency on both models using the same network, obtaining 40ms and 70ms.')
                for rows in ([launch, measured], [measured, launch]):
                    self.assertEqual(len(self.m.cluster_articles(rows)), 2)

    def test_historical_release_anniversary_is_not_a_new_launch(self):
        events, _ = self.cluster_sources('b257c5dbe05f7e3fa6114e3c')
        self.assertEqual([e.relevance_tier for e in events], ['weak'])
        for title, lead in (
            ('Apple Launched iPhone 4S With Siri 15 Years Ago Today',
             'Today marks the 15th anniversary of the iPhone 4S launch, introducing Siri as a built-in feature. The iPhone 4S went on sale on October 14, 2011.'),
            ('Apple introduced HomePod 10 years ago today',
             'Today marks the 10th anniversary of the HomePod introduction. Apple released the speaker a decade ago.'),
            ('十年前的今天，苹果推出HomePod音箱',
             '今天是HomePod发布十周年，当时苹果推出了这款智能音箱。'),
        ):
            with self.subTest(title=title):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual((event.relevance_tier, event.category), ('weak', 'hardware_products'))
        for title, lead in (
            ('Apple announces an anniversary HomePod edition', 'Apple today introduced a special HomePod model to mark its 10th anniversary.'),
            ('Apple releases new HomePod software on its anniversary', 'Apple released HomePod software today with security fixes.'),
            ('New filing discloses Apple product plan from ten years ago', 'A newly released court filing reveals an unreported Apple product plan from ten years ago.'),
            ('Apple launched HomePod 10 years ago today and now introduces a new anniversary edition',
             'Today marks the 10th anniversary of HomePod. Apple today introduced a new HomePod anniversary edition with a redesigned speaker and a $349 price.'),
            ('Apple launched HomePod 10 years ago today',
             'Today marks the 10th anniversary of HomePod. Apple today introduced a new HomePod anniversary edition with a redesigned speaker and a $349 price.'),
        ):
            with self.subTest(title=title):
                self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'strong')

    def test_serialized_product_card_is_removed_before_fact_sentence_splitting(self):
        body = ('Apple introduced HomePod mini 3 today with updated audio features and new colors. '
                '[Product: New device | https://shop.example.test/c/123?ref=publisher&u=https%3A%2F%2Fapple.com] '
                'HomePod mini 3 supports four speakers and costs $149. Customers can order it through Apple starting today.')
        page = '<script type="application/ld+json">' + json.dumps({
            '@type': 'NewsArticle', 'articleBody': body}) + '</script>'
        scope = self.m.structured_article_body_html(page, 'The Verge')
        facts = self.m.extract_key_facts(scope, 'Apple introduces HomePod mini 3', 'The Verge')
        joined = ' '.join(facts)
        self.assertNotIn('[Product:', joined)
        self.assertNotIn('ref=publisher', joined)
        self.assertIn('supports four speakers', joined)
        self.assertIn('$149', joined)

    def test_editorial_outlook_does_not_borrow_background_launch(self):
        title = "Apple's Home revamp is only half done, but the future is bright"
        lead = ("We didn't get a redesigned Home app, and the Apple TV 4K is overpriced, but the HomeView is interesting. "
                "Apple's series of press releases showed it still cares about the smart home, but I think a crucial bit was missing. "
                "I'm excited about HomeView, but the more important announcement was Apple's direct acknowledgement of a problem with third-party accessories.")
        self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'weak')
        from apple_news_core.event_identity import source_editorial_evaluation
        for title, lead in (
            ('Apple announces new Home device', 'Apple announced its new device. I think the future is bright.'),
            ('Apple CEO says the future of its Home strategy is bright', 'Apple CEO said, "I think the future is bright" after announcing a new support program.'),
            ('Apple Home software adds missing device controls', 'Apple added device controls. I think the Home strategy is promising.'),
            ('Apple launches a bright new Home interface in its Home revamp', 'Apple launched a redesigned Home interface today with new device controls. I think the future is bright.'),
            ('Apple CEO: The future of Home is bright', 'Apple CEO Tim Cook told reporters: I think the future of Home is bright. Apple announced a new support program today.'),
        ):
            self.assertFalse(source_editorial_evaluation(title, lead))

    def test_device_hosting_report_does_not_require_feed_excerpt(self):
        title = 'HomeView Runs Third-Party Apps From Your iPhone or iPad'
        for source in self.sources.values():
            with self.subTest(source=source.name):
                c = self.m.Candidate(source.name, 'https://' + source.domains[0] + '/device-app-support/', title, '')
                self.assertTrue(self.m.is_relevant_candidate(c, source))
        from apple_news_core.collection import sparse_apple_subject_needs_detail
        for title in ('New third-party app runs on HomeView and iPhone',
                      'Orion supports third-party apps like Apple HomeView',
                      'How to run third-party apps on iPad'):
            identity = self.m.title_led_identity(title, '')
            self.assertFalse(sparse_apple_subject_needs_detail(identity, has_lead=False,
                event_kind='third_party_ecosystem', title=title))

    def test_new_window_reports_bind_registration_and_website_evidence(self):
        self.assert_group(('6837b27a805c70caa588f70d', '34ce2b7f5d77b044d4304341'), 'software_systems')
        self.assert_group(('bf36fd2452f6c23f683d0f1b', 'd3b746b1e5b4f6789fc0e3b7'), 'software_systems')

    def test_reveal_material_belongs_to_the_current_device_introduction(self):
        self.assert_group(('25d23dd3ec5329fa5af13c8a', '16fe21226c990289c866b389'), 'hardware_products')
        release = article_for(self.m, 'Apple announces HomeView', 'Apple today introduced HomeView.')
        for device, title, lead in (
            ('HomeView', 'Watch Apple’s reveal video for HomeView', 'Apple just announced HomeView during its event today. As part of the event, it showed a video featuring the new device.'),
            ('HomePod mini 3', 'Watch the HomePod mini 3 introduction video', 'Apple just introduced HomePod mini 3 at its event today. The presentation included this video.'),
        ):
            announcement = article_for(self.m, 'Apple announces ' + device, 'Apple today introduced ' + device + '.')
            for rows in ([announcement, article_for(self.m, title, lead)], [article_for(self.m, title, lead), announcement]):
                self.assertEqual(len(self.m.cluster_articles(rows)), 1)
        for title, lead in (
            ('Watch Apple’s original HomeView reveal video', 'Apple introduced HomeView last year. The publisher revisits that original video today.'),
            ('Apple releases new HomeView film “Quiet House”', 'Apple introduced HomeView last month. Today Apple launched a separate advertising campaign called Quiet House.'),
            ('Apple releases HomeView reveal video', 'Apple just released a HomeView reveal video as part of the event. The device was introduced last month.'),
            ('Designer imagines a HomeView reveal video', 'An independent designer created this concept. Apple has not announced HomeView.'),
        ):
            other = article_for(self.m, title, lead)
            for rows in ([release, other], [other, release]):
                self.assertEqual(len(self.m.cluster_articles(rows)), 2)

    def test_registration_disclosure_keeps_document_and_renewal_boundaries(self):
        from apple_news_core.event_identity import source_current_report_frame
        title = '苹果国行AI备案出现新进展'
        lead = '国行iPhone于8月18日完成换证，新增大模型备案编号。'
        record = 'Shanghai-AppleZhiNeng-202506160057'
        current = source_current_report_frame(title, lead, (record,))
        self.assertEqual(current.category, 'software_systems')
        for other_lead, other_record in (
            (lead.replace('8月18日', '8月19日'), record),
            (lead, record.replace('202506160057', '202607160081')),
        ):
            other = source_current_report_frame(title, other_lead, (other_record,))
            self.assertNotEqual((current.subject, current.period), (other.subject, other.period))
        for other_title, other_lead in (
            (title, '国行iPhone尚未新增大模型备案编号。此前8月18日完成换证。'),
            ('苹果国行AI预计下月上线', '作者预计国行iPhone将增加大模型备案编号，尚无换证文件。'),
            (title, '预计国行iPhone将于8月18日完成换证，新增大模型备案编号。'),
            ('回顾苹果国行AI备案', lead),
        ):
            result = source_current_report_frame(other_title, other_lead, (record,))
            self.assertTrue(result is None or result.action != 'registration-update-disclosure')
        years = [source_current_report_frame(title, lead.replace('8月18日', f'{year}年8月18日'), (record,))
                 for year in (2025, 2026)]
        self.assertEqual([frame.year for frame in years], ['2025', '2026'])
        for pair in ((2025, 2026), (2026, 2025)):
            articles = [article_for(self.m, title, lead.replace('8月18日', f'{year}年8月18日'), facts=[record]) for year in pair]
            self.assertEqual(len(self.m.cluster_articles(articles)), 2)

    def test_video_application_capability_is_not_a_media_release(self):
        rows = (
            ('HomeView does not play video apps natively, you still need an iPhone or iPad',
             'Apple says HomeView runs compatible video apps from your iPhone or iPad.'),
            ('苹果 HomeView 支持第三方音频和视频应用',
             '苹果确认 HomeView 可运行来自 iPhone 或 iPad 的兼容第三方应用。'),
        )
        for ordered in (rows, rows[::-1]):
            events = self.m.cluster_articles([article_for(self.m, *row) for row in ordered])
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].category, events[0].relevance_tier), ('software_systems', 'strong'))

    def test_website_clue_requires_reported_evidence_not_denied_or_concept_text(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = 'Apple website suggests Siri AI is coming to HomePod'
        for lead in (
            'Apple has not added any such clue to its website. The old alt text remains unchanged.',
            'A designer created the alt text as a concept for an imagined Apple website.',
        ):
            self.assertIsNone(source_device_operation_frame(title, lead, (lead,)))

    def test_developer_assistance_binds_provider_platform_and_current_operation(self):
        from apple_news_core.event_identity import source_current_report_frame
        cases = (
            ('苹果面对面指导开发者适配iPhone Duo', '苹果会面对面指导开发者，帮助他们适配iPhone Duo。'),
            ('Apple helps developers adapt apps for visionOS', 'Apple is providing hands-on guidance to developers adapting their apps for visionOS.'),
            ('Apple mentors developers building apps for iPad', 'Apple mentors developers building apps for iPad through its developer center.'),
        )
        for title, lead in cases:
            with self.subTest(title=title):
                frame = source_current_report_frame(title, lead, (lead,))
                self.assertIsNotNone(frame)
                self.assertEqual((frame.action, frame.category, frame.tier), ('developer-assistance', 'software_systems', 'strong'))
        for title, lead in (
            ('第三方指导开发者适配iPhone Duo', '软件公司指导开发者适配iPhone Duo，苹果仅提供硬件。'),
            ('Apple does not provide developer guidance for iPad', 'Apple does not provide this training; an independent firm helps developers.'),
            ('苹果并未指导开发者适配iPhone Duo', '苹果没有提供这项指导，第三方负责培训。'),
            ('回顾苹果去年指导开发者适配iPad', '苹果去年提供了指导，今年没有新增活动。'),
            ('Apple should help developers adapt apps for visionOS', 'The author hopes Apple will provide guidance.'),
            ('Apple helps developers adapt apps for Android', 'Apple hardware is used by a third-party instructor training Android developers.'),
            ('iPhone Duo arrives: Apple helps developers adapt apps', 'Apple helps developers adapt apps for Android. iPhone Duo is mentioned as a comparison.'),
            ('Apple helps developers adapt apps for iPhone Duo', 'Apple helps developers adapt apps for Android using iPhone Duo only as a comparison.'),
            ('Apple helps developers adapt apps for iPad', 'Apple helps developers adapt apps for iPad in a course offered last year. There is no new program.'),
        ):
            with self.subTest(title=title):
                frame = source_current_report_frame(title, lead, (lead,))
                self.assertTrue(frame is None or frame.action != 'developer-assistance')
        first = source_current_report_frame('苹果指导开发者适配iPhoneDuo', '苹果指导开发者适配iPhoneDuo。', ())
        second = source_current_report_frame('Apple helps developers adapt apps for iPhone Duo', 'Apple helps developers adapt apps for iPhone Duo.', ())
        self.assertEqual(first.subject, second.subject)

    def test_named_device_definition_cannot_override_negation_or_concept(self):
        launch = article_for(self.m, 'Apple announces HomeView', 'Apple today announced HomeView.')
        for lead in ('苹果没有发布这款新设备。它叫HomeView，只是设计师展示的概念。',
                     '苹果将在明年发布一款新设备。它叫HomeView，目前仍是计划。',
                     '苹果去年发布了一款新设备。它叫HomeView，这次只是回顾。',
                     '苹果前员工发布了一个新设备。它叫HomeView。',
                     '苹果供应商发布了一个新设备。它叫HomeView。'):
            other = article_for(self.m, '苹果给Siri做了一块新屏幕', lead)
            for articles in ([launch, other], [other, launch]):
                self.assertEqual(len(self.m.cluster_articles(articles)), 2)
        for lead in ('苹果今天发布了一个新设备。它叫HomeView。',
                     '苹果今天发布了一个新设备。它叫HomeView，将于11月13日上市。'):
            other = article_for(self.m, '苹果给Siri做了一块新屏幕', lead)
            for articles in ([launch, other], [other, launch]):
                self.assertEqual(len(self.m.cluster_articles(articles)), 1)

    def test_duplicate_page_anchors_keep_the_complete_title_in_both_orders(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())
        for row in fixture['duplicate_page_links']:
            source = self.sources[row['source']]
            for anchors in (row['anchors'], list(reversed(row['anchors']))):
                with self.subTest(source=source.name, first=anchors[0][:80]):
                    rows = self.m.parse_html_links(''.join(anchors), row['page_url'], source)
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].url, row['target_url'])
                    self.assertTrue(self.m.is_relevant_candidate(rows[0], source))
                    self.assertGreater(len(rows[0].title), 40)
        for source in self.sources.values():
            url = 'https://' + source.domains[0] + '/newsroom/2026/10/device-support/'
            page = '<a href="' + url + '#summary">Current report</a><a href="' + url + '">Apple announces new device support requirements</a>'
            with self.subTest(source=source.name):
                rows = self.m.parse_html_links(page, source.pages[0], source)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].title, 'Apple announces new device support requirements')

    def test_paragraph_excerpt_does_not_replace_page_or_feed_headline(self):
        capture = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())['retail_listing_links']
        source = self.sources['快科技']
        title = self.rows['b1844ff318d27aa2c52789f4']['evidence']['discovery_title']
        for blocks in (capture['blocks'], capture['blocks'][::-1]):
            rows = self.m.parse_html_links(''.join(blocks), capture['page_url'], source)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].title, title)
            self.assertIn('999元复购补贴', rows[0].summary)
            self.assertTrue(self.m.is_relevant_candidate(rows[0], source))
        paragraph = next(block for block in capture['blocks'] if block.startswith('<p>'))
        excerpt = self.m.parse_html_links(paragraph, capture['page_url'], source)[0]
        feed = self.m.Candidate(source.name, capture['target_url'], title, feed_time_raw='2026-10-14T10:41:55Z')
        for order in ([excerpt, feed], [feed, excerpt]):
            merged = self.m.merge_duplicate_candidates(order)[0]
            self.assertEqual(merged.title, title)
            self.assertIn('999元复购补贴', merged.summary)
            self.assertEqual(merged.feed_time_raw, feed.feed_time_raw)
            self.assertTrue(self.m.is_relevant_candidate(merged, source))
        url = capture['target_url']
        for title_markup in (
            '<p class="headline"><a href="'+url+'">'+title+'</a></p>',
            '<p><a itemprop="headline" href="'+url+'">'+title+'</a></p>',
        ):
            comment = '<a href="'+url+'#comments">Join the discussion</a>'
            for html in (title_markup+comment, comment+title_markup):
                row = self.m.parse_html_links(html, capture['page_url'], source)[0]
                self.assertEqual(row.title, title)
                self.assertTrue(self.m.is_relevant_candidate(row, source))

    def test_writer_inferred_use_case_is_not_a_device_roadmap(self):
        events, _ = self.cluster_sources('ac59bc3b0ecc0fd7c03b1c13')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        from apple_news_core.event_identity import source_editorial_evaluation
        for title, lead in (
            ('Apple TV video reveals the one use-case for this device',
             'While watching the video, I suspect this is the one use-case for Apple TV.'),
            ('视频揭示了 HomePod 的唯一使用场景', '看完视频后，我认为这是设备唯一的使用场景。'),
        ):
            self.assertEqual(source_editorial_evaluation(title, lead), 'analysis')
        for title, lead in (
            ('Apple explains the use-case for HomeView', 'Apple explained its use-case today. I think it is interesting.'),
            ('HomeView video reveals the one use-case for this device', 'Apple’s CEO said, “I think this is the main use-case for HomeView.”'),
            ('HomeView adds new smart home controls', 'HomeView adds smart home controls. I suspect people will enjoy them.'),
            ('HomeView display test results', 'I measured the display and found it reached 0.3 nits.'),
            ('HomeView customizable faces support one use-case: smart home control',
             'HomeView includes customizable faces for smart home control. I think this is useful.'),
        ):
            self.assertEqual(source_editorial_evaluation(title, lead), '')
        capability = article_for(self.m, 'HomeView customizable faces support one use-case: smart home control',
            'HomeView includes customizable faces for smart home control. I think this is useful.')
        event = self.m.cluster_articles([capability])[0]
        self.assertEqual((event.relevance_tier, event.category), ('strong', 'software_systems'))

    def test_script_markup_never_becomes_article_summary_or_facts(self):
        body = 'Apple today announced a new accessibility feature with support for 12 languages and 4 device models.'
        script = '<script>function cleanResponse(text) { return text.replace(/<p>.*?<\/p>/g, ""); } const example="<p>Apple added 999 imaginary devices to the software support list today.</p>";</script>'
        metadata = '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-10-14T10:00:00Z"}</script>'
        page = metadata+'<article>'+script+'<p>'+body+'</p></article>'
        source = self.sources['MacRumors']
        candidate = self.m.Candidate(source.name, 'https://www.macrumors.com/2026/10/14/feature/', 'Apple announces new accessibility feature')
        extracted = self.m.extract_article(candidate, source, page, {})
        self.assertEqual(extracted[1], body)
        self.assertIn(body, extracted[2])
        self.assertNotIn('999', ' '.join(extracted[2]))
        self.assertEqual(extracted[3].isoformat(), '2026-10-14T10:00:00+00:00')

    def test_current_device_faces_report_owns_software_capability(self):
        from apple_news_core.event_identity import source_device_operation_frame
        events, _ = self.cluster_sources('431b7f233678b06d7482cebe')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))
        for title, lead in (
            ('HomeView界面包含照片、动画与智能家居控件', '苹果HomeView提供可定制的显示界面，可展示照片、动画和智能家居控件。'),
            ("Apple Watch faces include photos and animations", "Apple Watch includes customizable faces for photos and animations.")):
            with self.subTest(title=title):
                e = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual((e.relevance_tier, e.category), ('strong', 'software_systems'))
        for title, lead in (
            ('How to customize HomeView faces', 'This guide explains how to customize HomeView faces using existing options.'),
            ('HomeView faces we wish Apple would add', 'We wish Apple would provide customizable faces for HomeView.'),
            ('Orion app adds HomeView faces', 'Orion is a third-party app that provides new faces compatible with HomeView.'),
            ('HomeView faces do not include custom artwork', 'Apple confirms HomeView does not include custom artwork.'),
            ('HomeView faces and artwork', 'HomeView includes a clock. Orion offers customizable faces for its Android app.'),
            ('HomeView faces and artwork', 'HomeView includes a clock, while Orion offers customizable faces for its Android app.'),
            ('HomeView faces and artwork', 'HomeView includes customizable faces in an independent designer’s proposed interface.')):
            with self.subTest(title=title):
                frame = source_device_operation_frame(title, lead)
                self.assertFalse(frame and frame.action == 'display-face-capability-report')

    def test_platform_retrospective_requires_current_disclosure_to_be_strong(self):
        for platform in ('homeOS', 'macOS'):
            title = 'Remembering ' + platform
            lead = ('Last year Apple was rumored to be developing ' + platform +
                    '. This article looks back at the old rumor.')
            with self.subTest(platform=platform):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual(event.relevance_tier, 'weak')
        title = 'Remembering homeOS'
        lead = 'Last year Apple was rumored to be developing homeOS. This article looks back at the old rumor.'
        current = 'A fresh filing reveals that Apple is testing a new interface for homeOS.'
        for summary, facts in ((lead + ' ' + current, []), (lead, [current])):
            with self.subTest(current_in_facts=bool(facts)):
                event = self.m.cluster_articles([article_for(self.m, title, summary, facts=facts)])[0]
                self.assertEqual(event.relevance_tier, 'strong')
        for current in (
            'A fresh filing reveals that Orion is testing a new interface for homeOS.',
            'A fresh filing reveals that Apple is not testing a new interface for homeOS.',
            'A fresh filing reveals that Apple is testing a new interface for Android.',
        ):
            with self.subTest(current=current):
                event = self.m.cluster_articles([article_for(self.m, title, lead, facts=[current])])[0]
                self.assertEqual(event.relevance_tier, 'weak')
        release = 'Apple released homeOS today.'
        unrelated = 'A fresh filing reveals that Orion is testing a new interface for homeOS.'
        for facts in ([release], [unrelated, release], [release, unrelated],
                      [unrelated.rstrip('.') + ', while ' + release],
                      [release.rstrip('.') + ', while ' + unrelated]):
            with self.subTest(independent_release=facts):
                event = self.m.cluster_articles([article_for(self.m, title, lead, facts=facts)])[0]
                self.assertEqual(event.relevance_tier, 'strong')

    def test_collection_app_support_does_not_borrow_hub_hardware_action(self):
        articles = self.source_articles('c441037811a8c5fac267abff')
        other = article_for(self.m, 'Apple Home Collection accessories support LG ThinQ app',
                            'LG confirms its Apple Home Collection accessories work with LG ThinQ app and Apple Home. A HomePod or Apple TV is required as a home hub.')
        for order in (articles + [other], [other] + articles):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].category, 'software_systems')
            self.assertEqual(events[0].relevance_tier, 'strong')
        changed = article_for(self.m, 'Apple Home Collection accessories support Orion app',
                              'The Apple Home Collection now works with Orion app.')
        self.assertEqual(len(self.m.cluster_articles(articles + [changed])), 2)
        independent = article_for(self.m, 'LG independently developed cameras work with Apple Home',
                                   'LG independently developed the cameras, which are compatible with Apple Home and require an Apple TV as a hub.')
        self.assertEqual(self.m.cluster_articles([independent])[0].relevance_tier, 'weak')
        background = article_for(self.m, 'Orion collection accessories support LG ThinQ app',
                                  'Orion independently developed these cameras. Apple Home Collection is a competing lineup.')
        self.assertEqual(self.m.cluster_articles([background])[0].relevance_tier, 'weak')
        self.assertEqual(len(self.m.cluster_articles(articles + [background])), 2)
        contrasted = article_for(self.m, 'Orion collection accessories support LG ThinQ app, unlike Apple Home Collection',
                                  'Orion independently developed the accessories. Its products support LG ThinQ app.')
        self.assertEqual(self.m.cluster_articles([contrasted])[0].relevance_tier, 'weak')
        self.assertEqual(len(self.m.cluster_articles(articles + [contrasted])), 2)
        denial = article_for(self.m, 'Apple Home Collection accessories do not work with LG ThinQ app',
                              'Apple confirms its collection accessories do not work with LG ThinQ app.')
        self.assertEqual(len(self.m.cluster_articles(articles + [denial])), 2)

    def test_editorial_interpretation_does_not_borrow_current_launch(self):
        events, _ = self.cluster_sources('28797974f1eac469ea3c7f94')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        editorial = article_for(self.m, 'What Apple’s new home launch means for the industry',
                                 'Today Apple announced new home devices. In our view, the competition could accelerate household automation.')
        self.assertEqual(self.m.cluster_articles([editorial])[0].relevance_tier, 'weak')
        for title, lead in (
            ('苹果 iOS 27.2 新功能意味着什么？',
             '苹果今天发布 iOS 27.2，新增屏幕朗读功能。我们认为这或许更方便。'),
            ('What Apple’s new iOS 27.2 changes mean for users',
             'Apple released iOS 27.2 today with new accessibility features and language support. In our view, these changes make the device easier to use.')):
            with self.subTest(title=title):
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual(event.relevance_tier, 'strong')
                self.assertEqual(event.category, 'software_systems')

    def test_category_entry_finds_report_after_homepage_rolls_past_it(self):
        capture = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())['rolling_discovery']
        source = self.sources['快科技']
        for homepage in ('', capture['html']):
            with self.subTest(homepage_has_report=bool(homepage)):
                pages = {capture['captured_from']: capture['html'], source.pages[0]: homepage}
                with mock.patch.object(self.m, 'fetch_url', side_effect=lambda url, *_args, **_kwargs: pages.get(url, '')):
                    candidates = self.m.collect_candidates(source, Path('/unused-cache'), {})
                self.assertEqual([c.url for c in candidates], [capture['url']])
                chosen = self.m.select_detail_candidates(candidates, {source.name: source}, 20,
                    datetime(2026, 10, 13, 7, 39, tzinfo=timezone.utc),
                    datetime(2026, 10, 14, 7, 39, tzinfo=timezone.utc))
                self.assertEqual([c.url for c in chosen], [capture['url']])

    def test_tag_pagination_recovers_current_report_and_stops_at_window(self):
        capture = json.loads((Path(__file__).parent / 'fixtures/20261014_source_boundaries.json').read_text())['ithome_pagination']
        source = self.sources['IT之家']
        calls = []
        def fetch(url, *_args, **kwargs):
            if '/category/tagpage?' in url:
                calls.append((url, kwargs.get('method')))
                return json.dumps(capture['response'])
            return capture['first_html'] if url == capture['page_url'] else ''
        start = datetime(2026, 10, 13, 7, 53, tzinfo=timezone.utc)
        with mock.patch.object(self.m, 'fetch_url', side_effect=fetch):
            candidates = self.m.collect_candidates(source, Path('/unused-cache'), {}, window_start_utc=start)
        self.assertIn(capture['target_url'], [c.url for c in candidates])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 'POST')
        chosen = self.m.select_detail_candidates(candidates, {source.name: source}, 380,
            start, datetime(2026, 10, 14, 7, 53, tzinfo=timezone.utc))
        self.assertIn(capture['target_url'], [c.url for c in chosen])

    def test_read_only_post_transport_keeps_get_cache_separate(self):
        url = 'https://www.ithome.com/category/tagpage?keyword=apple&page=1'
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"success":true}'
        response.headers = {'content-type': 'application/json'}
        response.status = 200
        with TemporaryDirectory() as temp, mock.patch('urllib.request.urlopen', return_value=response) as opened:
            self.m.fetch_url(url, Path(temp), {}, retries=0)
            self.m.fetch_url(url, Path(temp), {}, retries=0, method='POST')
            self.assertEqual([c.args[0].get_method() for c in opened.call_args_list], ['GET', 'POST'])
            self.assertEqual(opened.call_args_list[-1].args[0].data, b'')
            self.assertEqual(len(list(Path(temp).glob('*.json'))), 2)

    def test_tag_pagination_bounds_failures_duplicates_and_unordered_dates(self):
        m = self.m
        page_url = 'https://www.ithome.com/tags/apple/'
        start = datetime(2026, 10, 13, tzinfo=timezone.utc)
        def candidate(number, date='2026-10-14T01:00:00+00:00'):
            return m.Candidate('IT之家', f'https://www.ithome.com/1/012/{number}.htm',
                               'Apple announces a new feature', feed_time_raw=date)
        first = [candidate(1)]
        cases = (
            (first, [candidate(1)], 'valid', 240, 'no-progress', 0),
            (first, [], 'valid', 240, 'empty-page', 0),
            (first, [], 'invalid', 240, 'invalid-response', 0),
            (first, [candidate(2), candidate(3)], 'valid', 2, 'candidate-budget', 1),
            ([candidate(1, '2026-10-12T00:00:00+00:00'), candidate(2)],
             [candidate(3, '2026-10-12T00:00:00+00:00')], 'valid', 240, 'window-covered', 1),
            ([candidate(1, '2026-10-12T00:00:00+00:00'), candidate(2, '')],
             [candidate(3), candidate(4, '2026-10-12T00:00:00+00:00')], 'valid', 240, 'window-covered', 2),
        )
        for initial, rows, response_type, limit, reason, expected in cases:
            with self.subTest(reason=reason):
                fetch = mock.Mock(return_value=json.dumps({'success': True, 'content': {'html': 'rows'}})
                                  if response_type == 'valid' else '{invalid')
                diagnostics = {}
                extra = m.collection.supplement_ithome_tag_candidates(page_url,
                    '/category/tagpage?', initial, start, limit, fetch, lambda *_: rows,
                    lambda raw: m.parse_datetime_value(raw, 'Asia/Shanghai'), diagnostics)
                self.assertEqual(len(extra), expected)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(diagnostics['source_listing_pagination'][page_url]['stop_reason'], reason)

    def test_vendor_neutral_chinese_phone_market_headline_fetches_detail(self):
        row=self.rows['06fe7661bb338a9db87357a8']
        title,lead,_=row['recorded_extraction']
        body='<article>'+''.join('<p>'+escape(u['text'])+'</p>' for u in row['evidence']['units'])+'</article>'
        candidate=self.m.Candidate('快科技',row['evidence']['url'],title,lead)
        source=self.sources['快科技']
        self.assertTrue(self.m.is_relevant_candidate(candidate,source))
        facts=self.m.extract_key_facts(body,title,source.name)
        self.assertTrue(any('苹果方面' in fact and '出货量仍同比小幅下滑' in fact for fact in facts))
        self.assertTrue(self.m.is_relevant_candidate(candidate,source,facts))
        result=self.m.source_market_measurement_frame(title,lead,tuple(facts))
        self.assertIsNotNone(result)
        self.assertEqual((result.subject,result.year,result.period,result.region),
                         ('idc:smartphone-shipments','2026','q3','china'))

    def test_market_direction_requires_a_current_apple_measurement(self):
        title = 'IDC: Q3 2026 smartphone shipments declined in China'
        for fact in ("Apple's shipments declined slightly year over year.",
                     '苹果出货量同比小幅下滑。',
                     "Apple's market share increased this quarter."):
            with self.subTest(fact=fact):
                self.assertIsNotNone(self.m.source_market_measurement_frame(title, '', (fact,)))
        for fact in ('Apple is a major customer of the chip supplier.',
                     "Apple's shipments are expected to decline next quarter.",
                     '苹果出货量预计明年下滑。',
                     '去年苹果出货量同比小幅下滑。',
                     '华为出货量增长，苹果新品受到欢迎。',
                     'Apple did not disclose its shipment trend.',
                     'Apple laptop shipments declined this quarter.'):
            with self.subTest(fact=fact):
                self.assertIsNone(self.m.source_market_measurement_frame(title, '', (fact,)))

    def test_language_conditions_do_not_replace_hardware_launch(self):
        for sid in ('5e3de9acb7b355b50db74bf6', 'df029e247000c2a2cf1077f5',
                    '16fe21226c990289c866b389', 'bf7e5dccb492bf4e7482e8a5'):
            with self.subTest(source=sid):
                articles = self.source_articles(sid)
                self.assertEqual(len(articles), 1)
                self.assertEqual(articles[0].title, self.rows[sid]['evidence']['title'])
                events = self.m.cluster_articles(articles)
                self.assertEqual(events[0].category, 'hardware_products')
                self.assertEqual(events[0].relevance_tier, 'strong')

    def test_language_prerequisite_does_not_merge_distinct_device_capabilities(self):
        ids = ('c282a8322f8fcee28420d003', '60961cd1f5e4f443fc4509a4')
        articles = [a for sid in ids for a in self.source_articles(sid)]
        for order in (articles, articles[::-1]):
            with self.subTest(order=[a.url for a in order]):
                events = self.m.cluster_articles(order)
                self.assertEqual(len(events), 2)
                self.assertEqual(Counter(a.url for e in events for a in e.articles),
                                 Counter(self.rows[sid]['evidence']['url'] for sid in ids))

    def assert_group(self, ids, category=None, tier='strong'):
        articles = [a for sid in ids for a in self.source_articles(sid)]
        for order in (articles, articles[::-1]):
            with self.subTest(order=[a.url for a in order]):
                events = self.m.cluster_articles(order)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].relevance_tier, tier)
                if category:
                    self.assertEqual(events[0].category, category)
                self.assertEqual(Counter(a.url for e in events for a in e.articles),
                                 Counter(self.rows[sid]['evidence']['url'] for sid in ids))

    def test_same_device_launch_sources_keep_one_primary_action(self):
        for ids in (
            ('861e9239c0e8c07f8dee7cb6','16fe21226c990289c866b389','bf7e5dccb492bf4e7482e8a5','ea9ef804932f1e147ac2d578','2cd3c46e3279984d47a05374'),
            ('0774f7be13d22e553f0c2aa5','270b3ac324c10cf0a6e23b5c','969c4508a42e645935fae19f','368d58bcf026767a8df92ebf','df029e247000c2a2cf1077f5'),
            ('5e3de9acb7b355b50db74bf6','8b034208e2e7356fc1c8be54','8eb03e07a3b763702f1c00b8','536f42752bf2a187006622bb','ce3e390cc5eca9fe971d7e60')):
            self.assert_group(ids, 'hardware_products')

    def test_current_launch_verb_keeps_device_announcement_identity(self):
        from apple_news_core.event_identity import source_device_operation_frame as frame
        self.assert_group(('7927763b5a586d8d07bbdac5', '861e9239c0e8c07f8dee7cb6'), 'hardware_products')
        for title, lead in (
            ('Apple launches HomePod mini 3', 'Apple today launches HomePod mini 3.'),
            ('HomePod mini 3 launched today', 'HomePod mini 3 was launched today by Apple.'),
        ):
            with self.subTest(title=title):
                self.assertEqual(frame(title, lead).action, 'device-announcement')
        for title, lead in (
            ('Apple will launch HomePod mini 3', 'Apple will launch HomePod mini 3 next year.'),
            ('HomePod mini 3 may be launched', 'HomePod mini 3 may be launched next year.'),
            ('HomePod mini 3 launched last year', 'HomePod mini 3 was launched last year.'),
            ('HomePod mini 3 was not launched', 'HomePod mini 3 was not launched by Apple.'),
            ("HomePod mini 3 hasn't launched", "HomePod mini 3 hasn't launched yet."),
            ('Apple is launching HomePod mini 3 next year', 'Apple is launching HomePod mini 3 next year.'),
            ('Apple launches HomePod mini software 28', 'Apple today launches HomePod mini software 28.'),
            ('Apple launches HomePod mini 28', 'Apple today launches HomePod mini software 28.'),
        ):
            with self.subTest(title=title):
                result = frame(title, lead)
                self.assertFalse(result and result.action == 'device-announcement')

    def test_support_reports_keep_their_owned_feature_and_device(self):
        self.assert_group(('eb3e4418546fc74d2274e866','514e74da021a56a617031ed9','8d3aa54178f5c7e89d4beb57'), 'software_systems')
        self.assert_group(('3f18a8a3e0fc9d1a7c7fe781','87d112d9347ac727abb4499f','09aaf52d3543e44632972953'), 'software_systems')
        self.assert_group(('d3b746b1e5b4f6789fc0e3b7','bb4507df0068e01b15e08f57'), 'software_systems')
        for sid in ('1c7d511e5d7226cb9f773753','2147a0064a757504c57fa6de'):
            events,_=self.cluster_sources(sid)
            self.assertEqual(events[0].relevance_tier,'strong')

    def test_remote_compatibility_does_not_project_host_devices_as_roadmaps(self):
        ids=('21b0767d403457664de1023d','a0861353fc6f55ae9cb9f954','9a64d7f4b7d4c7b019970ab6','f23b4cdca1ecb84d431b189a')
        self.assert_group(ids,'hardware_products')
        for sid in ids:
            self.assertEqual(len(self.source_articles(sid)),1)

    def test_repair_camera_mount_and_historical_namesake_are_not_one_event(self):
        repairs=('ca2c0cc19972bccbfc690318','e593f0408b916bf82f0c4c81','fe0e0043d904255effba2276','c629b17efe1a81dc403a9676')
        self.assert_group(repairs)
        self.assert_group(('37fd38e9197524089fe1922b','ead2097d917310b3a8a66b3f'),'hardware_products')
        ids=(repairs[0],'37fd38e9197524089fe1922b','8cae6eb32666346ae2828ad4','0b6604cf7909740d10ad2f39')
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),4)
        collision=next(e for e in events if any(a.evidence.article_id==ids[-1] for a in e.articles))
        self.assertEqual(collision.relevance_tier,'weak')

    def test_first_party_brand_collaboration_launch_is_not_partner_news(self):
        self.assert_group(('3f3022c53d5269c9fd8d1d3f','26a4d4fd922f594913aa1dba','1b51603acecdb3335a89eb57','b2855b67ac0b94afb7b40fa3'), 'hardware_products')

    def test_current_patent_challenge_is_not_editorial_guesswork(self):
        self.assert_group(('acae485dbbb930c925771f21','0bfc4b7b556bb7bf1a28d0cf','2aaf4af917e36ba1361b1b44'), 'hardware_products')
        base = self.source_articles('0bfc4b7b556bb7bf1a28d0cf')[0]
        for title, lead in (
            ('Jury orders Apple to pay Taction damages', 'A jury ruled that Apple infringed Taction Technology patents for haptic feedback.'),
            ('Apple plans appeal against Taction verdict', 'Apple said it would appeal the verdict. No motion has been filed.'),
            ('Apple asks judge to vacate Orion patent verdict', 'Apple filed a new motion to vacate the verdict awarded to Orion Technology over haptic patents.'),
        ):
            with self.subTest(title=title):
                self.assertEqual(len(self.m.cluster_articles([base, article_for(self.m,title,lead)])), 2)

    def test_currency_saving_headline_stays_a_deal(self):
        title, lead, facts = self.rows['6578f5aa2fcb2d60166d5794']['recorded_extraction']
        events = self.m.cluster_articles([article_for(self.m,title,lead,facts=facts)])
        self.assertEqual(events[0].relevance_tier, 'weak')
        source = self.sources['AppleInsider']
        self.assertFalse(self.m.is_relevant_candidate(self.m.Candidate(source.name,'https://appleinsider.com/deal',title,lead),source,facts))

    def test_numbered_beta_available_now_keeps_release_inventory(self):
        articles = self.source_articles('a73db546ff9a8c1c3a3b4051')
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, self.rows['a73db546ff9a8c1c3a3b4051']['evidence']['title'])

    def test_device_operations_keep_history_negation_and_neighbor_actions(self):
        from apple_news_core.event_identity import source_device_operation_frame as frame
        for title, lead in (
            ('Apple may announce HomePod mini 3', 'Apple is expected to announce HomePod mini 3 next year.'),
            ('Apple did not announce HomePod mini 3', 'Apple did not introduce HomePod mini 3 today.'),
            ('HomePod mini 2 retrospective', 'Apple announced HomePod mini 2 last year.'),
            ('How to use HomePod mini 2', 'Apple today announced HomePod mini 2. Here are the setup steps.'),
            ('Apple TV 4K firmware update released', 'Apple released an Apple TV 4K firmware update today.'),
        ):
            with self.subTest(title=title):
                result = frame(title,lead)
                self.assertFalse(result and result.action == 'device-announcement')
        launch = article_for(self.m,'Apple announces HomePod mini 2','Apple today announced HomePod mini 2.')
        for title,lead in (
            ('Apple announces HomePod mini 3','Apple today announced HomePod mini 3.'),
            ('HomePod mini 2 works as default Mac speaker','The new HomePod mini 2 can be a default speaker for supported Macs.'),
        ):
            self.assertEqual(len(self.m.cluster_articles([launch, article_for(self.m,title,lead)])),2)

    def test_announced_collection_is_one_first_party_hardware_inventory(self):
        self.assert_group(('1ff9027cace745a11b9f6ab3','203786f3fa73d815393520b4','28c96958f048ddbd268d4aa4',
            '4b99f0751da348af39e10f3c','80d3e24e786da39769c0e482','90adf4aed68111a89356c1ba','c83ff869afe326ce84ac59ab'),'hardware_products')

    def test_price_revision_after_announcement_remains_separate(self):
        events,_=self.cluster_sources('04a89cb108cf414d0929d910','270b3ac324c10cf0a6e23b5c')
        self.assertEqual(len(events),2)
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def test_evaluation_cannot_borrow_a_background_product_launch(self):
        for sid in ('0666099558bfa8d0830996d7','1fbc926ae2e237a4f13c4433','48134007d524caa4e7f18fe1',
                    '5ec047e50cb7c2630d4ad83f','e1e91e3e2fc81950315a735a'):
            with self.subTest(source=sid):
                events,_=self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier=='weak' for e in events))
                self.assertEqual(len(events),1)

    def test_focused_device_conditions_reconcile_without_changing_their_action(self):
        for ids,category in (
            (('a3c6dd3aa1d960b86f88f721','531932dc659991a0fd7c7ad2','3f9e53df9ed991144c26157c'),'hardware_products'),
            (('c282a8322f8fcee28420d003','3bdd6bac050df85d5e15bd13'),'software_systems'),
            (('6995a639cbf44e3d3cee2a58','c6a98bdea90b2a45581755d2'),'software_systems'),
            (('0a4567e53f0281c392ca7700','f66ff865a3405ced0f954624','fb3b2c4166f666463b1ab89a'),'software_systems'),
            (('eb3e4418546fc74d2274e866','3d1a7423844a4c917da17e31'),'software_systems'),
        ):
            self.assert_group(ids,category)
        events,_=self.cluster_sources('a3c6dd3aa1d960b86f88f721','c282a8322f8fcee28420d003','8cdc3abd3a3af2e8a37c94c6','16fe21226c990289c866b389')
        self.assertEqual(len(events),4)

    def test_platform_component_changes_keep_software_identity(self):
        for ids in (('76979035750b104d583aa274','0ae45ec73d26223eb87a894a'),
                    ('0303da6aa757a3c773923516','1944739b6e0ecf4a5304bade'),
                    ('6c963291149610f445e1c815','09c4c93070d1e4bd02ee20e4')):
            self.assert_group(ids,'software_systems')
        events,_=self.cluster_sources('f11ed688414444da29df39ae')
        self.assertEqual(events[0].category,'software_systems')

    def test_companion_remote_does_not_replace_tv_release_inventory(self):
        self.assert_group(('c69fa1183ef32757445d6daa','5e3de9acb7b355b50db74bf6'),'hardware_products')

    def test_multi_feature_launch_is_not_only_one_support_condition(self):
        self.assert_group(('d68ff27601cce218da12139f','270b3ac324c10cf0a6e23b5c'),'hardware_products')

    def test_historical_preview_keeps_invitation_visible_without_new_roadmaps(self):
        sid='9481bf06f331a281b5018ff9'
        events,_=self.cluster_sources(sid)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].relevance_tier,'weak')
        row=self.rows[sid]
        body='<article>'+''.join('<p>'+escape(u['text'])+'</p>' for u in row['evidence']['units'])+'</article>'
        facts=self.m.extract_key_facts(body,row['evidence']['title'],row['evidence']['source'])
        self.assertTrue(any('苹果已邀请' in fact for fact in facts))
        for text in ('苹果可能邀请媒体参加活动。','苹果去年邀请媒体参加活动。',
                     'Apple has not invited creators to the event.','Orion invited media to discuss Apple.'):
            self.assertFalse(self.m.source_apple_invitation_fact(text))

    def test_publisher_outlook_is_not_another_current_device_action(self):
        events,_=self.cluster_sources('883b535fa71e0383e1efd1c3')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].relevance_tier,'weak')

    def test_market_measurement_does_not_transfer_between_grammatical_owners(self):
        for fact in ("Despite Apple's launch, Huawei's shipments grew this quarter.",
                     "Apple said Huawei's shipments declined this quarter.",
                     '苹果新品推出后，华为出货量仍保持增长。',
                     "Despite Apple's launch, Huawei's smartphone shipments grew this quarter.",
                     'Apple faced competition as Huawei shipments grew this quarter.'):
            self.assertIsNone(self.m.source_market_measurement_frame(
                'IDC: Q3 2026 smartphone shipments in China','',(fact,)))

    def test_directional_market_result_keeps_local_explanatory_modifier(self):
        row = self.rows['9bc131c0de1398024b5348e7']
        title, lead, _ = row['recorded_extraction']
        body = '<article>' + ''.join('<p>' + escape(u['text']) + '</p>'
                                    for u in row['evidence']['units']) + '</article>'
        facts = self.m.extract_key_facts(body, title, 'IT之家')
        self.assertTrue(any('苹果凭借' in fact and '销量和市占上的增长' in fact for fact in facts))
        article = article_for(self.m, title, lead, facts=facts)
        other = next(v['recorded_extraction'] for v in self.rows.values()
                     if v['evidence']['url'].endswith('1157388.htm'))
        peer = article_for(self.m, other[0], other[1], facts=other[2])
        for order in ([article, peer], [peer, article]):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')
            self.assertEqual(events[0].category, 'hardware_products')
        for fact in ('苹果凭借高端产品组合实现了销量增长。',
                     '苹果得益于提前发布的策略取得了市占上的增长。'):
            self.assertIsNotNone(self.m.source_market_measurement_frame(title, '', (fact,)))
        for fact in ('苹果表示华为凭借高端产品组合实现了销量和市占上的增长。',
                     '苹果凭借高端产品组合预计将实现销量和市占上的增长。',
                     '苹果凭借高端产品组合实现了营收增长。',
                     '苹果凭借高端产品组合去年实现了销量和市占上的增长。',
                     '苹果凭借高端产品组合，华为实现了销量和市占上的增长。',
                     '苹果凭借高端产品组合将在本季度实现销量增长。',
                     '苹果受益于华为实现了销量增长。',
                     '苹果凭借渠道支持帮助华为实现了销量增长。'):
            self.assertIsNone(self.m.source_market_measurement_frame(title, '', (fact,)))

    def test_regions_partners_generations_and_release_stages_do_not_collapse(self):
        pairs=(
            (('Apple Watch sleep apnea detection launches in Japan with watchOS 27.2','Apple enabled the feature with a watchOS update in Japan.'),
             ('Apple Watch sleep apnea detection launches in the US with watchOS 27.2','Apple enabled the feature with a watchOS update in the United States.')),
            (('Apple introduces HomePod (2nd generation)','Apple introduced HomePod (2nd generation) today.'),
             ('Apple introduces HomePod (3rd generation)','Apple introduced HomePod (3rd generation) today.')),
            (('Apple Watch sleep apnea detection launches in Japan','Apple enabled the feature with a watchOS update in Japan.'),
             ('Apple Watch sleep apnea detection launches in the US','Apple enabled the feature with a watchOS update in the United States.')),
            (('Beats announces new collaboration with New Balance for Beats Pill','Beats announced a new collaboration with New Balance for Beats Pill.'),
             ('Beats announces new collaboration with New Era for Beats Pill','Beats announced a new collaboration with New Era for Beats Pill.')),
            (('Apple introduces third-generation Apple TV 4K','Apple introduced third-generation Apple TV 4K today.'),
             ('Apple introduces fourth-generation Apple TV 4K','Apple introduced fourth-generation Apple TV 4K today.')),
            (('Apple introduces HomePod 2','Apple introduced HomePod 2 today.'),
             ('Apple introduces HomePod 3','Apple introduced HomePod 3 today.')),
            (('Apple announces Apple Home Collection smart home accessories','Apple today announced Apple Home Collection cameras developed with LG; preorders will open next month.'),
             ('Apple Home Collection smart home accessories now shipping','Apple today announced that Apple Home Collection cameras developed with LG have begun shipping.')),
            (('iOS 27.2 Adds New Apple Music Icon in Beta 3','Apple replaced the Apple Music icon in iOS 27.2 beta 3.'),
             ('iOS 27.2 Adds New Apple Music Icon in Beta 4','Apple replaced the Apple Music icon in iOS 27.2 beta 4.')),
        )
        for pair in pairs:
            with self.subTest(pair=pair):
                articles=[article_for(self.m,*row) for row in pair]
                self.assertEqual(len(self.m.cluster_articles(articles)),2)
                self.assertEqual(len(self.m.cluster_articles(articles[::-1])),2)

    def test_history_concepts_and_denials_cannot_borrow_current_action(self):
        pairs=(
            (('HomeView repair fees explained','Apple published the HomeView repair fees last year. The fees remain unchanged.'),
             ('Apple HomeView repair fees revealed','Apple revealed new HomeView repair fees for AppleCare customers.')),
            (('A look back at HomeView repair fees','Apple published the HomeView repair fees last year. The fees remain unchanged.'),
             ('Apple HomeView repair fees revealed','Apple revealed new HomeView repair fees for AppleCare customers.')),
            (('HomeView repair fees: what owners paid last year','AppleCare customers paid these repair fees last year.'),
             ('Apple HomeView repair fees revealed','Apple revealed new HomeView repair fees for AppleCare customers.')),
            (('Apple Home Collection smart home accessories retrospective','Apple announced Apple Home Collection cameras developed with LG last year.'),
             ('Apple announces Apple Home Collection smart home accessories','Apple today announced Apple Home Collection cameras developed with LG.')),
            (('HomeView camera sensor not revealed by iOS 27.2 code','The code does not reveal the camera sensor; a Sony IMX614 is merely speculation.'),
             ('HomeView camera sensor revealed by iOS 27.2 code','The code revealed a Sony IMX614 sensor for HomeView.')),
            (('iOS 27.2 will not include a new Apple Music icon','Apple confirmed the existing icon remains unchanged.'),
             ('iOS 27.2 Adds New Apple Music Icon','Apple replaced the Apple Music icon in iOS 27.2 beta 4.')),
        )
        for pair in pairs:
            with self.subTest(pair=pair):
                self.assertEqual(len(self.m.cluster_articles([article_for(self.m,*r) for r in pair])),2)
        e=self.m.cluster_articles([article_for(self.m,'Designer unveils new Apple Music icon for iOS 27.2',
            'A designer created a concept for a new Apple Music icon; Apple has not announced any change.')])[0]
        self.assertEqual(e.relevance_tier,'weak')

    def test_hardware_launch_is_not_replaced_by_companion_software(self):
        rows=(('Apple announces HomePod mini 3',
               'Apple today announced HomePod mini 3 with HomePod mini software 28.'),
              ('Apple unveils HomePod mini 3', 'Apple today unveiled HomePod mini 3.'))
        articles=[article_for(self.m,*r) for r in rows]
        for order in (articles,articles[::-1]):
            events=self.m.cluster_articles(order)
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].category,'hardware_products')
            self.assertEqual(events[0].relevance_tier,'strong')

    def test_designer_concept_cannot_merge_with_first_party_icon_change(self):
        release=article_for(self.m,'iOS 27.2 Adds New Apple Music Icon',
                            'Apple replaced the Apple Music icon in iOS 27.2 beta 4.')
        for role in ('Independent designer','A graphic designer','独立设计师'):
            with self.subTest(role=role):
                concept=article_for(self.m,role+' unveils new Apple Music icon for iOS 27.2',
                    'An independent designer created a concept for a new Apple Music icon; Apple has not announced any change.')
                self.assertEqual(self.m.cluster_articles([concept])[0].relevance_tier,'weak')
                for order in ([concept,release],[release,concept]):
                    self.assertEqual(len(self.m.cluster_articles(order)),2)

    def test_sparse_installation_and_announced_collection_are_not_generic_accessories(self):
        self.assert_group(('8e18ab103daf954711cdcfab','8cae6eb32666346ae2828ad4'),'hardware_products')
        self.assert_group(('3444bbeaad99769e4a5e0c9b','1ff9027cace745a11b9f6ab3'),'hardware_products')

    def test_multiword_partner_name_ends_before_the_announcement_verb(self):
        rows=(('Beats and New Balance announce new Beats Pill collaboration','Beats announced a new collaboration with New Balance for Beats Pill.'),
              ('Beats announces new collaboration with New Balance for Beats Pill','Beats announced a new collaboration with New Balance for Beats Pill.'))
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,*r) for r in rows])),1)

    def test_live_focused_specs_do_not_inherit_release_or_preorder(self):
        groups=(
            ('65de70d863df8ef4e2efe508','f68ea5f115e397983a87a63f'),
            ('b84808868a4d3988c6538cb0','f7c9ce3a748b09b3fa3781c5','6a3e651a233d7fcf87d9fbb3'),
            ('60961cd1f5e4f443fc4509a4','30254d07fb8f99c803817149'),
            ('031bd4444f42cb381c6743d5','8cae6eb32666346ae2828ad4'),
            ('0118d29fc3f8200aca518c07','16fe21226c990289c866b389'),
        )
        for ids in groups:
            self.assert_group(ids,'hardware_products')
        ids=tuple(g[0] for g in groups)
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),len(ids))

    def test_live_regional_feature_activation_is_software_across_headline_angles(self):
        self.assert_group(('f11ed688414444da29df39ae','cb6515a98b589ad26f304961','973bec3ee9968957677ee718'),'software_systems')

    def test_numeric_and_direction_only_sources_share_current_market_report(self):
        rows=[self.rows[sid]['recorded_extraction'] for sid in ('600566159023022a444e3631','3237783d95f585f0f483add0')]
        title,lead,facts=rows[0]
        units=self.rows['600566159023022a444e3631']['evidence']['units']
        facts=self.m.extract_key_facts('<article>'+''.join('<p>'+escape(u['text'])+'</p>' for u in units)+'</article>',title,'IT之家')
        articles=[article_for(self.m,title,lead,facts=facts),article_for(self.m,*rows[1][:2],facts=rows[1][2])]
        for order in (articles,articles[::-1]):
            self.assertEqual(len(self.m.cluster_articles(order)),1)
        for title,lead in (
            ('Counterpoint: Q3 2026 China smartphone shipments fall','Counterpoint says Apple shipments declined slightly in China.'),
            ('IDC: Q2 2026 China smartphone shipments fall','IDC says Apple shipments declined slightly in China.'),
            ('IDC: Q3 2026 global smartphone shipments fall','IDC says Apple shipments declined slightly worldwide.'),
        ):
            self.assertEqual(len(self.m.cluster_articles([articles[0],article_for(self.m,title,lead)])),2)

    def test_multi_component_inventory_does_not_take_one_component_identity(self):
        from apple_news_core.event_identity import source_platform_component_frame
        for sid in ('4964851174ba23d29b927130','8a43a95654d8221dd2fe94f0'):
            title,lead,facts=self.rows[sid]['recorded_extraction']
            self.assertIsNone(source_platform_component_frame(title,lead,tuple(facts)))

    def test_executive_current_institutional_attendance_is_company_news(self):
        self.assert_group(('4ad1219c421d1f029485ed9e','75c5c69797e9b2ec290e1b3c'),'hardware_products')

    def test_company_visit_owns_category_before_background_app_compatibility(self):
        events, _ = self.cluster_sources('a2b6f13bb8998ac645bbbd92')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].category, events[0].relevance_tier), ('hardware_products', 'strong'))
        from apple_news_core.event_identity import source_executive_visit_frame
        title, lead, facts = self.rows['a2b6f13bb8998ac645bbbd92']['recorded_extraction']
        frame = source_executive_visit_frame(title, lead, tuple(facts))
        self.assertEqual(frame.action, 'corporate-visit')
        for changed in (title.replace('爱奇艺总部', '腾讯总部'), title.replace('现身', '将访问')):
            self.assertNotEqual(source_executive_visit_frame(changed, lead, tuple(facts)), frame)
        for title, lead in (
            ('库克去年现身企业总部的旧照', '苹果执行主席库克去年到访企业总部。'),
            ('苹果库克现身爱奇艺总部的旧照', '苹果执行主席库克去年到访爱奇艺总部，这是一张当时的旧照。'),
            ('苹果库克现身宣传视频', '苹果执行主席库克的数字形象今日出现在宣传视频中。'),
            ('苹果库克未现身企业总部', '苹果执行主席库克没有到访企业总部。'),
            ('雷军现身企业总部，库克未到场', '小米董事长雷军今日到访企业总部，苹果执行主席库克没有到访。'),
        ):
            self.assertIsNone(source_executive_visit_frame(title, lead))
        planned = article_for(self.m, '苹果库克将现身爱奇艺总部', '苹果执行主席库克将现身爱奇艺总部。')
        current = self.source_articles('a2b6f13bb8998ac645bbbd92')
        self.assertEqual(source_executive_visit_frame(planned.title, planned.summary).action, 'planned-corporate-visit')
        for order in (current+[planned], [planned]+current):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_current_variant_report_is_not_lost_when_headline_says_rumored(self):
        articles = self.source_articles('894dac849570f5d8c3371dce')
        events = self.m.cluster_articles(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        for headline in ('AirPods Pro 4传出高低双版本', 'iPad mini 9传出高低双版本'):
            device = headline.split('传出')[0]
            current = article_for(self.m, headline, '据爆料账号透露，苹果正在考虑为'+device+'推出高低两个版本。')
            self.assertEqual(self.m.cluster_articles([current])[0].relevance_tier, 'strong')
            for prefix, lead in (
                ('回顾：', '去年曾有传闻称苹果考虑推出两个版本，本文回顾旧消息，没有新披露。'),
                ('设计师想象：', '独立设计师制作了两个版本的概念图，并非苹果的计划。'),
                ('我的愿望：', '我希望苹果能做出两个版本，没有任何具体爆料。'),
            ):
                self.assertEqual(self.m.cluster_articles([article_for(self.m, prefix+headline, lead)])[0].relevance_tier, 'weak')
        other = article_for(self.m, 'AirPods Pro 4充电盒规格曝光', '据另一名消息人士透露，AirPods Pro 4的充电盒将采用新接口。')
        for order in (articles+[other], [other]+articles):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)
        unrelated = article_for(self.m, 'AirPods Pro 4传出高低双版本', '据消息人士透露，苹果正在考虑为下一代HomePod推出高低两个版本。AirPods仅为比较对象。')
        self.assertEqual(self.m.cluster_articles([unrelated])[0].relevance_tier, 'weak')
        for lead in (
            '早在2024年，据消息人士透露，苹果计划为AirPods Pro 4推出两个版本。',
            '据消息人士透露，苹果正在考虑为AirPods Pro 3推出高低两个版本。',
        ):
            event = self.m.cluster_articles([article_for(self.m, 'AirPods Pro 4传出高低双版本', lead)])[0]
            self.assertEqual(event.relevance_tier, 'weak')

    def test_personal_sighting_does_not_borrow_background_business_attendance(self):
        title, lead, facts = self.rows['2167dd78707e6a61f4b10bb2']['recorded_extraction']
        events = self.m.cluster_articles([article_for(self.m, title, lead, facts=facts)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        current = article_for(self.m, '苹果库克现身爱奇艺总部，结束假期后恢复商务活动', '苹果执行主席库克今日到访爱奇艺总部。')
        self.assertEqual(self.m.cluster_articles([current])[0].relevance_tier, 'strong')
        for title, lead in (
            ('苹果库克现身旅游科技展，展示苹果设备', '苹果执行主席库克今日到访旅游科技展，与企业代表交流苹果设备在旅游行业的应用。'),
            ('苹果库克现身北京并非游玩，而是到访合作企业', '苹果执行主席库克今日到访企业总部，与代表讨论业务。'),
        ):
            self.assertEqual(self.m.cluster_articles([article_for(self.m, title, lead)])[0].relevance_tier, 'strong')

    def test_focused_spec_and_feature_neighbors_keep_distinct_action(self):
        pairs=(
            (('HomeView screen brightness specifications revealed','HomeView can dim its display to 0.4 nits.'),
             ('HomeView screen brightness may change next year','Apple may add a dimmer display next year.')),
            (('Apple Watch sleep apnea notifications launch in China','Apple launched the feature in China today.'),
             ('Apple Watch sleep apnea notifications gain regulatory approval in China','The regulator approved the feature; Apple has not launched it.')),
            (('Apple Watch sleep apnea notifications launch in China','Apple launched the feature in China today.'),
             ('Apple Watch sleep apnea notifications launched last year','A guide explains the existing feature Apple launched last year.')),
        )
        for pair in pairs:
            with self.subTest(pair=pair):
                self.assertEqual(len(self.m.cluster_articles([article_for(self.m,*row) for row in pair])),2)

    def test_live_review_qualifiers_stay_owned_by_the_current_action(self):
        from apple_news_core.event_identity import source_current_report_frame
        for title,lead in (
            ('雷军出席清华大学年会，库克未到场','雷军今天参加清华大学2026年年会。苹果董事长库克没有到场。'),
            ('库克不会出席清华大学年会','苹果董事长库克明确表示，他不会参加清华大学2026年年会。'),
            ('库克出席清华大学年会的照片公布','苹果董事长库克去年参加清华大学2025年年会，照片今天公开。'),
            ('库克将出席清华大学年会','苹果董事长库克将出席清华大学2026年年会。'),
        ):
            frame=source_current_report_frame(title,lead,())
            self.assertFalse(frame and frame.action=='institutional-attendance')
        frames=[source_current_report_frame('苹果董事长库克出席清华大学年会',lead,()) for lead in (
            '苹果董事长库克今日出席清华大学2026年年会。',
            '在清华大学，苹果董事长库克今日出席2026年年会。',
            '库克出席清华大学2026年年会。',
            '清华大学2026年年会今天举行，苹果董事长库克出席。')]
        self.assertTrue(all(frame == frames[0] for frame in frames))
        self.assertTrue(frames[0].subject.endswith(':清华大学'))
        for title,lead in (
            ('HomeView screen brightness specifications explained','Apple reported the HomeView display brightness of 0.4 nits last year. The specifications remain unchanged.'),
            ('HomeView model differences rumored','The two HomeView models could have different speakers with a woofer.'),
        ):
            self.assertEqual(self.m.cluster_articles([article_for(self.m,title,lead)])[0].relevance_tier,'weak')
        articles=[article_for(self.m,'Apple Watch update brings a new feature to '+region,
            'Apple launches sleep apnea notifications in '+region+' today.') for region in ('Japan','the US')]
        self.assertEqual(len(self.m.cluster_articles(articles)),2)


if __name__ == '__main__':
    unittest.main()
