"""New-window reports keep their source-owned action, stage and eligibility."""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior
import test_20261014_source_boundaries as previous


class SourceBoundariesTests(unittest.TestCase):
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources
    assert_group = previous.SourceBoundariesTests.assert_group

    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/20261015_source_boundaries.json').read_text())['sources']
        cls.sources = {s.name: s for s in cls.m.build_sources(datetime(2026, 10, 15, tzinfo=timezone.utc))}

    def test_host_platform_app_capabilities_keep_the_software_operation(self):
        self.assert_group(('7f65649411a2b4ff6aea37e7', 'e51db6bb0bb1423294e1c27b',
                           '0f2d53467d7fc4709a497161', 'f18524c4d3cc8247782e7349'), 'software_systems')

    def test_government_meeting_projection_preserves_the_actual_counterpart(self):
        sid = '04e61b3dc6b46993607f3901'
        articles = self.source_articles(sid)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, self.rows[sid]['evidence']['title'])
        self.assertTrue(any('部长王文涛会见' in fact for fact in articles[0].key_facts))
        event, = self.m.cluster_articles(articles)
        self.assertEqual((event.relevance_tier, event.category), ('strong', 'hardware_products'))

    def test_a_playback_device_does_not_own_an_independent_content_release(self):
        events, _ = self.cluster_sources('040d194fe5019617fadf0738')
        self.assertTrue(events)
        self.assertTrue(all((event.relevance_tier, event.category) == ('weak', 'software_systems')
                            for event in events))
        for owner, tier in (('Apple', 'strong'), ('Studio North', 'weak')):
            with self.subTest(publisher=owner):
                article = article_for(self.m, owner + ' releases immersive film "Sky Journey" for Vision Pro',
                    owner + ' released its new immersive film today. "Sky Journey" is now available on Vision Pro.')
                event, = self.m.cluster_articles([article])
                self.assertEqual((event.relevance_tier, event.category), (tier, 'software_systems'))
        article = article_for(self.m, 'Apple releases immersive film "Sky Journey" for Vision Pro',
            'Apple released "Sky Journey" today. Studio North\'s "Ocean Path" is now available on Vision Pro.')
        profile = self.m.article_reconciliation_profile(article)
        self.assertIn('primary-claim:apple-tv-content:sky-journey:release', profile.event_keys)
        self.assertFalse(any(key.startswith('primary-claim:') and 'ocean-path' in key
                             for key in profile.event_keys))
        other = article_for(self.m, 'Studio North releases immersive film "Ocean Path" for Vision Pro',
            'Studio North released "Ocean Path" today. "Ocean Path" is now available on Vision Pro.')
        for order in ([article, other], [other, article]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_source_actions_keep_eligibility_without_component_key_authority(self):
        from dataclasses import replace
        for suffix in ('1157521.htm', '013/271.htm', 'apple-says-beloved-macbook-is-now-obsolete-more-products-too/'):
            sid = next(sid for sid, row in self.rows.items() if row['evidence']['url'].endswith(suffix))
            with self.subTest(source=sid):
                articles = self.source_articles(sid)
                self.assertTrue(all(event.relevance_tier == 'strong' for event in self.m.cluster_articles(articles)))
        article, = self.source_articles('040d194fe5019617fadf0738')
        profile = self.m.article_reconciliation_profile(article)
        for keys in (frozenset(), frozenset({'structured-component:new-topic:vision-pro'})):
            result = self.m.resolve_reconciliation_outcome(replace(profile, event_keys=keys),
                observed_tier='strong', observed_reason='old classifier', observed_category='hardware_products')
            self.assertEqual((result[0], result[2]), ('weak', 'software_systems'))

    def test_official_fee_statements_join_the_same_regional_table(self):
        sid = next(sid for sid, row in self.rows.items()
                   if row['evidence']['url'].endswith('1582282.htm'))
        self.assert_group((sid, 'e0db7a94a1667af074f0dd5c', '5baf3408e68dcabec8141e69'), 'software_systems')
        regional = tuple(key for key, row in self.rows.items()
                         if row['evidence']['url'].endswith(('1582282.htm', '013/117.htm', '1157508.htm', '1157692.htm')))
        self.assertEqual(len(regional), 4)
        self.assert_group(regional, 'software_systems')
        for order in ((sid, 'c73b10fdc5dde77d56f198e6'), ('c73b10fdc5dde77d56f198e6', sid)):
            events, _ = self.cluster_sources(*order)
            self.assertEqual(len(events), 2)
        title = 'iPhone 18 repair fees in the US'
        lead = "Apple's website shows iPhone 18 repair fees in the US."
        own = 'Apple charges $99 for iPhone 18 repairs in the US.'
        comparison = 'For comparison, Apple charges CNY 799 for iPhone 18 repairs in China.'
        articles = [article_for(self.m, title, lead, facts=facts, source=str(i))
                    for i, facts in enumerate(([own], [own, comparison]))]
        for ordered in (articles, articles[::-1]):
            self.assertEqual(len(self.m.cluster_articles(ordered)), 1)
        from apple_news_core.event_identity import source_service_fee_frame
        for continuation, currency in (
            ('非AppleCare+用户更换内屏需要7998元。', 'currency:cny'),
            ('第三方维修店的报价为999元。', ''),
            ('用户在第三方维修店更换内屏需要999元。', ''),
            ('用户更换屏幕选择第三方门店需支付999元。', ''),
            ('用户更换RivalPhone需要999元。', ''),
            ('用户更换屏幕需支付999元。', 'currency:cny'),
        ):
            frame = source_service_fee_frame('iPhone 18维修费用',
                '苹果官网公布iPhone 18维修费用。其中，' + continuation, ())
            self.assertEqual(frame.period, currency)

    def test_source_relations_do_not_borrow_a_different_object_or_owner(self):
        from apple_news_core.event_identity import (
            source_current_lifecycle_update, source_dated_launch_frame, source_service_fee_frame)
        rows = (
            (source_dated_launch_frame, 'iPhone 18 preorders open tomorrow',
             'Apple announced that iPhone 17 preorders open tomorrow.',
             'Apple announced that iPhone 18 preorders open tomorrow.'),
            (source_current_lifecycle_update, 'Apple updates information about obsolete MacBooks',
             'Apple updated its mailing list for news about obsolete MacBooks.',
             'Apple updated its obsolete products list, adding the final MacBook model.'),
            (source_service_fee_frame, 'iPhone 18 repair fees in the US',
             "Apple's website shows that RepairCo charges $99 for iPhone 18 repair fees in the US.",
             "Apple's website shows iPhone 18 repair fees in the US are $99."),
        )
        rows += (
            (source_dated_launch_frame, 'iPhone 18 preorders open tomorrow',
             'Preorders for the RivalPhone start tomorrow.',
             'Apple announced that iPhone 18 preorders open tomorrow.'),
            (source_current_lifecycle_update, 'Apple updates its obsolete MacBook list',
             'Last year, Apple updated its obsolete products list, adding the final MacBook model.',
             'Today, Apple updated its obsolete products list, adding the final MacBook model.'),
            (source_service_fee_frame, 'iPhone 18 repair fees in the US',
             "Apple's website shows iPhone 18 repair fees charged by RepairCo in the US are $99.",
             "Apple's website shows iPhone 18 repair fees charged by Apple in the US are $99."),
        )
        for relation, title, bad, good in rows:
            args = () if relation is source_current_lifecycle_update else ((),)
            with self.subTest(relation=relation.__name__):
                self.assertFalse(relation(title, bad, *args))
                self.assertTrue(relation(title, good, *args))
                articles = [article_for(self.m, title, text, source=source)
                            for source, text in (('bad', bad), ('good', good))]
                for ordered in (articles, articles[::-1]):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 2)

    def test_sparse_direct_reports_and_market_results_reach_detail_verification(self):
        rows = (
            ('cnBeta', 'https://www.cnbeta.com.tw/articles/tech/1582200.htm',
             '获乔布斯与沃兹尼亚克双重加持的Apple I拍出115万美元 创历史最高成交价'),
            ('IT之家', 'https://www.ithome.com/1/013/197.htm',
             '美股三大指数齐跌、AI 科技股几乎“全军覆没”，韩国首尔综合指数一度触发熔断'),
        )
        for source, url, title in rows:
            with self.subTest(title=title):
                self.assertTrue(self.m.is_relevant_candidate(self.m.Candidate(source, url, title, ''), self.sources[source]))
        for title in ('美股投资指南：如何选股', '铁威马 D4-321 四盘位硬盘柜上市：USB-C 10Gbps，999 元'):
            with self.subTest(title=title):
                self.assertFalse(self.m.is_relevant_candidate(self.m.Candidate('IT之家',
                    'https://www.ithome.com/1/011/111.htm', title, ''), self.sources['IT之家']))
        for title in ('Apple', '苹果', 'iPhone', '苹果电脑使用教程'):
            identity = self.m.title_led_identity(title, '')
            self.assertFalse(self.m.collection.sparse_apple_subject_needs_detail(identity,
                has_lead=False, event_kind=self.m.detect_event_kind(title, ''), title=title))

    def test_rolling_list_cards_preserve_their_own_assertion_for_admission(self):
        capture = json.loads((Path(__file__).parent / 'fixtures/20261015_listing_admission.json').read_text())
        m, source = self.m, self.sources['MacRumors']
        for url, card in capture['cards'].items():
            with self.subTest(url=url):
                rows = m.collection.supplement_macrumors_index_candidates('https://www.macrumors.com/',
                    '<main>' + card + '</main>', [], datetime(2026, 10, 13, tzinfo=timezone.utc), 240,
                    lambda _url: None, lambda body, page: m.parse_html_links(body, page, source),
                    lambda raw: m.parse_datetime_value(raw, source.default_tz), {})
                own = next(r for r in rows if r.url == url)
                self.assertTrue(own.summary)
                self.assertTrue(m.is_relevant_candidate(own, source))
        row = capture['ithome']
        candidate = m.Candidate('IT之家', row['url'], row['title'], '')
        self.assertTrue(m.is_relevant_candidate(candidate, self.sources['IT之家']))
        for title, summary in (
            ('HomePod mini buyer guide: which should you buy?', 'Apple introduced the HomePod mini years ago. Here is our buying advice.'),
            ('HomePod mini vs competitor speaker buyer guide', 'These are our favorite speakers to buy.'),
        ):
            candidate = m.Candidate('MacRumors', 'https://www.macrumors.com/guide/speakers/', title, summary)
            self.assertFalse(m.allowed_url_excluded_candidate(candidate, source, title + ' ' + summary))

    def test_subjective_device_evaluations_do_not_borrow_a_launch(self):
        for sid in ('cfddbf594a481cbf43555555', '97d7eccb58fb0f6f5027112a',
                    '2baf26b1cc19c1db949b58a2', 'a8c618e8486bdbde13e3c497', '95cd72fbca675105f689825b'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(events)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_explicit_support_denial_is_a_software_report(self):
        self.assert_group(('5c509cc5d8563b898d940d41', '5e9e5768deedb7e1f535449a',
                           'a516bc4391f6b117c551a13d'), 'software_systems')
        events, _ = self.cluster_sources('13080d9d817493f8eecafc1d')
        self.assertTrue(all(e.category == 'software_systems' and e.relevance_tier == 'strong' for e in events))

    def test_official_retail_program_is_not_an_independent_retailer_deal(self):
        from apple_news_core.event_identity import source_current_report_frame
        self.assert_group(('e278bd99be5a9cd4c699e276',), 'hardware_products')
        title = 'Apple announces “Autumn Shopping” promotion with iPhone discounts'
        current = article_for(self.m, title,
            'Apple today announced its Autumn Shopping promotion for its online store. The new campaign starts next week.')
        self.assertEqual(self.m.cluster_articles([current])[0].relevance_tier, 'strong')
        for other_title, lead in (
            ('Retailer Northstar launches “Autumn Shopping” sale on Apple products',
             'Apple today announced a new iPhone for its online store. Northstar is offering its own Autumn Shopping discounts on Apple devices.'),
            ('Retailer Northstar announces “Autumn Shopping” iPhone discounts',
             'Retailer Northstar announced an Autumn Shopping sale on Apple products. Apple announced its own program last year.'),
            ('Apple “Autumn Shopping” discounts have not been announced',
             'Apple did not announce an Autumn Shopping promotion. Its online store prices are unchanged.'),
            ('A look back at Apple “Autumn Shopping” discounts',
             'Apple announced its Autumn Shopping promotion last year. Here are the discounts that were offered in its online store.'),
            ('When will Apple “Autumn Shopping” discounts return?',
             'A blogger expects Apple to announce an Autumn Shopping promotion for its online store next week.'),
        ):
            other = article_for(self.m, other_title, lead)
            with self.subTest(lead=lead):
                self.assertIsNone(source_current_report_frame(other_title, lead, ()))
                if 'did not announce' not in lead:
                    self.assertEqual(self.m.cluster_articles([other])[0].relevance_tier, 'weak')
                for order in ([current, other], [other, current]):
                    self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_default_mac_speaker_and_system_audio_keep_one_operation(self):
        ids = ('c20efa44b358c6315a063b92', '7d19cec9f4b2021195223997',
               '8cec308aa5b16d3a6915ade7')
        self.assert_group(ids, 'software_systems')
        current = self.source_articles(ids[1])[0]
        controls = (
            ('HomePod mini works with Mac through AirPlay',
             'The original HomePod mini plays music from a Mac over AirPlay. It cannot serve as the default system speaker.'),
            ('Apple TV adds HomePod surround sound',
             'The new Apple TV supports four HomePod speakers for surround sound.'),
            ('HomePod mini could become a default Mac speaker',
             'A designer imagines a future HomePod mini that could serve as the default Mac speaker.'),
            ('HomePod mini 3 can output Mac system audio after software 28.1 rollout',
             'HomePod mini 3 can output Mac system audio now: Apple enabled it today through a new software update.'),
            ('HomePod mini 3 now works as default Mac speaker after software 28.1 rollout',
             'Apple released HomePod software 28.1 today, adding default Mac speaker support to HomePod mini 3 for the first time.'),
            ('First-generation HomePod now works as default Mac speaker',
             'Apple enabled default Mac speaker support for the first-generation HomePod today through a new software update. This model did not support the feature before.'),
        )
        for title, lead in controls:
            other = article_for(self.m, title, lead)
            for order in ([current, other], [other, current]):
                with self.subTest(title=title, order=[a.title for a in order]):
                    self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_platform_system_audio_report_is_not_hardware(self):
        events, _ = self.cluster_sources('8cec308aa5b16d3a6915ade7')
        self.assertEqual([(e.category, e.relevance_tier) for e in events], [('software_systems', 'strong')])

    def test_explicit_launch_anniversary_does_not_claim_a_current_action(self):
        events, _ = self.cluster_sources('fbc329d5c7423d2e07b673ff')
        self.assertTrue(all(e.relevance_tier == 'weak' for e in events))
        fresh = article_for(self.m, 'AppleCare launched 20 years ago; Apple adds theft coverage today',
            'Apple today announced theft coverage for AppleCare. The service originally launched 20 years ago.')
        self.assertEqual(self.m.cluster_articles([fresh])[0].relevance_tier, 'strong')

    def test_third_party_modification_and_personal_delivery_crime_stay_weak(self):
        for sid in ('44bdfc5fc0ff931b341fd7b5', 'a22cf27435e6c4c9a6f8ac23'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_adverse_claim_and_nonuse_commitment_keep_distinct_actions(self):
        claims = ('dbd99fc9884db098d21a0a8a', '402af9a22e10156a4ee36bb7',
                  '3e5b9d97a09cc051a2fdd691', 'a6556fed858341dcde66d7ee', '5e777361a0a73e4b2cd60bfb')
        commitments = ('e7b13a78789581ea8fed22ca', 'f539aec8e399ee6f6da5834d', 'fb35d9193885b89a3fe876b2')
        self.assert_group(claims, 'hardware_products')
        self.assert_group(commitments, 'hardware_products')
        a = [x for sid in claims + commitments for x in self.source_articles(sid)]
        for order in (a, a[::-1]):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 2)
            self.assertEqual(sorted(len(e.articles) for e in events), [3, 5])

    def test_listing_lead_does_not_borrow_the_next_container_or_source(self):
        parser = self.m.collection._ListingLeadParser()
        parser.feed('<div class="js-contentInner"><p><img src="image"></p></div>'
                    '<aside><p>Apple announced unrelated hardware today.</p></aside>')
        self.assertEqual(parser.summary, '')
        parser = self.m.collection._ListingLeadParser()
        parser.feed('<div class="js-contentInner"><div><p><img></p></div>'
                    '<p>Apple <b>announced</b> a new device.</p></div><p>Other item.</p>')
        self.assertEqual(parser.summary, 'Apple announced a new device.')

    def test_current_reports_keep_capabilities_separate_from_wishes_and_tutorials(self):
        from apple_news_core.event_identity import source_device_operation_frame, source_editorial_evaluation
        for title, lead in (
            ('I wish HomeView supported video apps', 'I wish Apple would let HomeView run video apps from my iPhone.'),
            ('HomeView video app concept', 'An independent designer imagines Apple HomeView running iPhone video apps.'),
        ):
            with self.subTest(title=title):
                self.assertIsNone(source_device_operation_frame(title, lead))
        self.assertFalse(source_editorial_evaluation('Apple adds a simpler interface for HomeView',
            'Apple today announced a simpler interface and detailed its accessibility controls.'))

    def test_current_regional_launch_plan_keeps_one_action_and_its_conditions(self):
        self.assert_group(('ee92100ad1812fca913bb9ae','70b6eb9654a6c61310ca48ee',
            '6026a84b31e0d55a29d982e6','1c5244eb6a094ae47b96efd6','4e98f548c82b335b8afcd8ed',
            'c2bd9f06b26ff25e799d5445'), 'software_systems')

    def test_public_beta_plan_keeps_one_action_without_borrowing_os_background(self):
        ids = ('27312dca3875d2a170b442c5', 'cd39a8e8286058a0ca8fb6fc', 'c607dc3cab4411ca71658d19', '892f559afc6027fdac4e2dae')
        self.assert_group(ids, 'software_systems')
        from apple_news_core.event_identity import source_current_report_frame
        for sid in ids:
            article, = self.source_articles(sid)
            frame = source_current_report_frame(article.title, article.summary, tuple(article.key_facts))
            self.assertEqual((frame.action, frame.period, frame.region, frame.model_generation),
                             ('beta-release-plan', '10', 'china', ''))
        articles = [a for sid in (*ids, 'ee92100ad1812fca913bb9ae') for a in self.source_articles(sid)]
        for ordered in (articles, articles[::-1]):
            self.assertEqual(sorted(len(e.articles) for e in self.m.cluster_articles(ordered)), [1, 4])

    def test_beta_plan_and_internal_test_need_their_own_subject_and_stage(self):
        from apple_news_core.event_identity import source_current_report_frame
        title = '苹果智能将在中国推出测试版'
        current = '苹果智能首批功能将于11月推出测试版本。'
        frame = source_current_report_frame(title, current, ())
        self.assertEqual((frame.action, frame.period), ('beta-release-plan', '11'))
        for text in ('去年' + current, '苹果否认' + current,
                     '苹果智能首批功能仍在准备，微软将于11月推出测试版本。',
                     '苹果智能将于10月继续接受审核，微软将于11月推出测试版本。',
                     '苹果智能尚未获批，将于11月推出测试版本。'):
            with self.subTest(text=text):
                self.assertIsNone(source_current_report_frame(title, text, ()))
        article = article_for(self.m, title, current, facts=[
            '此前媒体称，苹果会在12月随iOS 28.3发布正式版本。'])
        keys = self.m.article_reconciliation_profile(article).event_keys
        self.assertFalse(any('internal-test' in key or 'ios-28.3' in key for key in keys))
        no_plan = article_for(self.m, 'Apple previews a new accessibility feature',
            'Apple discussed testing the upcoming feature with users.', facts=[
                'The service shipped with iOS 28.3 last year.'])
        self.assertFalse(any('internal-test' in key for key in self.m.article_reconciliation_profile(no_plan).event_keys))
        self.assertIsNone(source_current_report_frame('Apple testing iOS 28.3 with users',
            'Apple is testing iOS 28.3 with users in the public beta program.', ()))
        self.assertIsNone(source_current_report_frame('Apple testing iOS 28.3 with users',
            'Apple is testing iOS 28.3 with users in the public beta program, while Microsoft is internally testing Windows.', ()))
        public_test = article_for(self.m, 'Apple testing iOS 28.3 with users',
            'Apple is testing iOS 28.3 with users in the public beta program, while Microsoft is internally testing Windows.')
        profile = self.m.article_reconciliation_profile(public_test)
        self.assertFalse(any('internal-test' in key for key in profile.event_keys | profile.separation_keys))
        self.assertFalse(self.m.is_os_point_release_internal_testing_story(public_test.title, public_test.summary))

    def test_actual_closing_market_value_reports_share_one_measurement(self):
        self.assert_group(('7f92c18e52788a5929e4ed4e','3d0b32c9297e733796b43af1',
            'ac104508e78dde6dbea96e91','5f81b94a8bd27053ac4ca703','75d84a5a85d7adb687d11102'), 'hardware_products')

    def test_local_closing_result_survives_without_a_parent_article(self):
        m = self.m
        captured = self.rows['7fb774fb2223b28db915ce38']['evidence']
        body = ''.join('<p>' + unit['text'] + '</p>' for unit in captured['units'])
        page = ('<meta property="article:published_time" content="' + captured['published_utc']
                + '"><h1>' + captured['title'] + '</h1><article>' + body + '</article>')
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 10, 15, 12, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        with TemporaryDirectory() as directory:
            args = m.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(m, 'datetime', Clock), patch.object(m, 'collect_candidates_from_sources',
                    return_value=[m.Candidate(captured['source'], captured['url'], captured['title'])]), \
                    patch.object(m, 'fetch_url', return_value=page):
                result = m.run(args)
        self.assertEqual(result['events'], [])
        self.assertEqual(result['deferred_events'], [])
        review, = [item for item in result['final_brief_queue'] if item.get('evidence_id')]
        self.assertTrue(review['required'])
        self.assertEqual(review['source_urls'], [captured['url']])
        expected = next(unit['text'] for unit in captured['units'] if '收盘市值首次站上' in unit['text'])
        self.assertEqual([unit['text'] for unit in review['unprocessed_evidence']], [expected])
        self.assertTrue(result['evidence_dispositions'][review['evidence_id']]['unprocessed'])

    def test_closing_value_relation_keeps_its_local_owner_and_observation(self):
        from apple_news_core.event_identity import source_closing_market_value_frame
        current = '苹果公司是为数不多上涨的科技股，收盘市值首次站上 5 万亿美元。'
        frame = source_closing_market_value_frame(current)
        self.assertIsNotNone(frame)
        self.assertEqual((frame.year, frame.period), ('', ''))
        for text in (
            current.replace('苹果公司', '微软公司'), '去年' + current, '分析师预计' + current,
            '苹果公司上涨，英伟达收盘市值首次站上 5 万亿美元。',
            '微软和苹果公司合计收盘市值首次站上 5 万亿美元。',
            '苹果公司和微软收盘市值首次站上 5 万亿美元。',
            '苹果公司是为数不多上涨的科技股，收盘市值与微软合计达到 5 万亿美元。',
            '苹果公司收盘市值尚未站上 5 万亿美元。',
        ):
            with self.subTest(text=text):
                self.assertIsNone(source_closing_market_value_frame(text))

    def test_same_benchmark_configuration_is_not_the_comparison_device(self):
        self.assert_group(('34706450af225330ed8da151','21af1bf5b8bb3be3c5de5c99'), 'hardware_products')

    def test_same_disclosed_variants_keep_one_report(self):
        self.assert_group(('894dac849570f5d8c3371dce','35fd7e10a3d5f16fa0168420'), 'hardware_products')

    def test_apple_created_profile_is_not_ordinary_third_party_use(self):
        self.assert_group(('ab10809d911dbd2f6407b9a4','7c18df70975289819274b1a6',
                           '06efa7c34f233aa48da9db71'), 'hardware_products')

    def test_completed_named_historical_device_auction_is_direct_hardware(self):
        self.assert_group(('7b8a7743066e569a2b9d3578','53e5932795e3364698f854a7',
            '9a930c43b9d8f2fbc71ff3f9', '0ae2885ebc042495f0ba0db4',
            '0963227fa1f1e051b054c0b5'), 'hardware_products')
        from apple_news_core.event_identity import source_current_report_frame
        self.assertIsNone(source_current_report_frame('Hatfield Apple-1 auction update',
            'The Miller Apple-1 sold at auction today. The Hatfield Apple-1 remains unsold.', ()))
        self.assertIsNone(source_current_report_frame('Hatfield Apple-1 auction update',
            'The Hatfield Apple-1 owner sold the Miller Apple-1 for $1 million today.', ()))
        frame = source_current_report_frame('Hatfield Apple-1 auction update',
            'Bonhams sold the Hatfield Apple-1 for $1,148,200 today.', ())
        self.assertIsNotNone(frame)
        self.assertEqual(frame.subject, 'apple-1:artifact:hatfield')

    def test_media_invitation_owns_its_date_before_the_product_inventory(self):
        self.assert_group(('18323485800faf6ad8d3fc8d','d87293a7c5b2e36119709a61',
                           'bd491c7a974cafdfcd6d4113', '8472c0ca3be5ce08b2387d74',
                           '3eb22bd833def1515a76984f'), 'hardware_products')
        from apple_news_core.event_identity import source_dated_launch_frame, source_sentence_spans
        source = self.rows['18323485800faf6ad8d3fc8d']['evidence']
        for title in (source['title'], 'Apple inviting media to a launch experience'):
            frame = source_dated_launch_frame(title, source['raw_lead'], ())
            self.assertIsNotNone(frame)
            self.assertEqual((frame.subject, frame.action, frame.period),
                             ('apple:product-launch-campaign', 'launch-date-report', 'month:10:day:28'))
        for date in ('Oct. 28', 'Oct 28', 'October 28'):
            sentence = 'Apple is now inviting media to a product launch experience on ' + date + ' in Los Angeles.'
            self.assertEqual([sentence[a:b] for a, b in source_sentence_spans(sentence)], [sentence])
            frame = source_dated_launch_frame(source['title'], sentence, ())
            self.assertEqual(frame.period, 'month:10:day:28')
        for text in ('Apple is not inviting media to a product launch experience on October 28.',
                     'Apple invited media to a product launch experience last year on October 28.',
                     'Apple is now inviting media to a launch experience in Los Angeles, while Samsung is holding a launch event on October 28.'):
            self.assertIsNone(source_dated_launch_frame('Apple inviting media to a launch experience', text, ()))

        for text in ('苹果已经开始邀请部分媒体参加10月28日在洛杉矶举行的全天新品体验活动。',
                     '苹果已邀请媒体参加将在10月28日举行的新品体验活动。',
                     '苹果已邀请部分媒体于10月28日参加在洛杉矶举行的新品体验活动。',
                     '去年苹果举行了发布会，而今年苹果已经开始邀请媒体参加10月28日举行的新品体验活动。'):
            frame = source_dated_launch_frame('苹果邀请媒体参加新品体验活动', text, ())
            self.assertEqual((frame.subject, frame.period),
                             ('apple:product-launch-campaign', 'month:10:day:28'))
        for text in ('苹果没有邀请媒体参加10月28日举行的新品体验活动。',
                     '去年苹果邀请媒体参加10月28日举行的新品体验活动。',
                     '苹果邀请媒体参加新品体验活动，而另一家公司将在10月28日举行发布会。'):
            self.assertIsNone(source_dated_launch_frame('苹果邀请媒体参加新品体验活动', text, ()))

    def test_media_invitation_scope_does_not_fall_back_to_a_device_disclosure(self):
        from apple_news_core.event_identity import bind_source_report
        from apple_news_core.event_matcher import identity_pair_decision
        capture = self.m.capture_article_title_evidence
        title = '苹果向媒体发出邀请函，多款 Mac 与新 iPad mini 或将登场'
        dated = '苹果已经开始邀请部分媒体参加10月28日在洛杉矶举行的新品体验活动。'
        claim, = bind_source_report(capture('cnBeta', 'https://example.com/invite', title, dated, ()))
        self.assertEqual((claim.subject, claim.action, claim.report_role),
                         ('apple', 'media-invitation', 'independent'))
        self.assertEqual(self.m.claim_eligibility(claim).tier, 'strong')
        for text in ('苹果已经开始邀请部分媒体参加新品体验活动。',
                     '苹果邀请媒体参加新品体验活动，而另一家公司将在10月28日举行发布会。'):
            with self.subTest(text=text):
                pending, = bind_source_report(capture('cnBeta', 'https://example.com/sparse', title, text, ()))
                self.assertEqual(self.m.claim_eligibility(pending).tier, 'strong')
                self.assertEqual(identity_pair_decision(claim, pending), 'unknown')
                self.assertTrue(pending.review_reason)
                article = article_for(self.m, title, text)
                result, = self.m.cluster_articles([article])
                self.assertEqual((result.relevance_tier, result.category), ('strong', 'hardware_products'))
                self.assertIn(pending.review_reason, result.merge_warnings)
        for text in (dated.replace('28日', '29日'), dated.replace('10月28日', '2025年10月28日')):
            other, = bind_source_report(capture('cnBeta', 'https://example.com/date', title, text, ()))
            if '2025' in text:
                this_year, = bind_source_report(capture('cnBeta', 'https://example.com/date2', title,
                                                        dated.replace('10月28日', '2026年10月28日'), ()))
                self.assertEqual(identity_pair_decision(this_year, other), 'conflict')
            else:
                self.assertEqual(identity_pair_decision(claim, other), 'conflict')
        contradictory, = bind_source_report(capture('cnBeta', 'https://example.com/dates', title,
                                                    dated + dated.replace('28日', '29日'), ()))
        self.assertEqual(identity_pair_decision(claim, contradictory), 'unknown')
        self.assertTrue(contradictory.review_reason)
        for text, tier in (
            ('去年苹果邀请媒体参加10月28日举行的新品体验活动。', 'weak'),
            ('苹果没有邀请媒体参加10月28日举行的新品体验活动。', ''),
            ('另一家公司邀请媒体参加10月28日举行的新品体验活动。', ''),
        ):
            with self.subTest(text=text):
                pending, = bind_source_report(capture('cnBeta', 'https://example.com/role', title, text, ()))
                self.assertEqual(self.m.claim_eligibility(pending).tier, tier)
                self.assertNotEqual(identity_pair_decision(claim, pending), 'match')
                evidence = capture('cnBeta', 'https://example.com/role', title, text, ())
                projections, remaining, excluded = self.m.project_article_evidence(evidence)
                self.m.validate_evidence_dispositions(evidence, projections, remaining, excluded)
                self.assertTrue(projections)
                self.assertEqual(self.m.claim_eligibility(projections[0].claim).tier, tier)
        for heading, text in (
            ('Apple announces new Macs', 'Apple will launch new Macs on October 28.'),
            ('Apple may hold an event', 'Apple may hold a product event on October 28.'),
            ('Apple launches new Macs', 'Apple today launched new Macs. Last year Apple invited media to an event on October 28.'),
            ('Apple Invites adds media guest lists', 'Apple Invites lets users invite reporters to an event on October 28.'),
            ('Apple invites developers to a product event', 'Apple invited developers to an event on October 28, according to media reports.'),
        ):
            self.assertIsNone(bind_source_report(capture('MacRumors', 'https://example.com/launch', heading, text, ())))
        sent, = bind_source_report(capture('MacRumors', 'https://example.com/sent', 'Apple invites media to an event',
            'Apple invited media on October 15 to a product event next month.', ()))
        scheduled, = bind_source_report(capture('MacRumors', 'https://example.com/scheduled', 'Apple invites media to an event',
            'Apple invited media to a product event on October 15.', ()))
        self.assertEqual(identity_pair_decision(sent, scheduled), 'unknown')
        self.assertFalse(sent.qualifiers)
        after, = bind_source_report(capture('MacRumors', 'https://example.com/sent2', 'Apple invites media to an event',
            'Apple invited media to a product event next month after sending invitations on October 15.', ()))
        self.assertEqual(identity_pair_decision(after, scheduled), 'unknown')
        self.assertFalse(after.qualifiers)
        for text, day in (
            ('苹果已邀请部分媒体于10月20日前回复后参加新品体验活动。', None),
            ('苹果已邀请部分媒体于10月20日前回复并参加10月28日举行的新品体验活动。', '28'),
        ):
            reply, = bind_source_report(capture('Source', 'https://example.com/reply', title, text, ()))
            days = {q[2] for q in reply.qualifiers if q[1] == 'event-day'}
            self.assertEqual(days, {day} if day else set())
            self.assertEqual(bool(reply.review_reason), day is None)
        from dataclasses import replace
        opinion_text = 'Apple invited media to an event on October 28. I think the event will be disappointing.'
        opinion, = bind_source_report(replace(capture('MacRumors', 'https://example.com/comment',
            'Why Apple’s media invitation disappoints me', opinion_text, ()),
            raw_lead=opinion_text, content_form='opinion'))
        self.assertEqual(self.m.claim_eligibility(opinion).tier, 'weak')
        self.assertNotEqual(identity_pair_decision(claim, opinion), 'match')

    def test_secondary_invitation_needs_a_local_report_relation(self):
        from apple_news_core.event_identity import bind_media_invitation
        capture = self.m.capture_article_title_evidence
        title = 'Apple may unveil new hardware this month'
        lead = 'Apple may unveil new hardware at a product event this month.'
        invitation = 'Apple has invited media to a product event on October 28.'
        for fact, expected in (
            ('Alex Smith reports that ' + invitation, True),
            ('陈明透露，苹果已经邀请媒体参加10月28日举行的新品体验活动。', True),
            (invitation + ' This is for the new Macs. — Alex Smith (@alexsmith)', True),
            ('A new report says Apple will hold a product event on October 28. It says that ' + invitation, True),
            (invitation, False),
            ('It says that ' + invitation, False),
            ("Last year's report says Apple will hold a product event on October 28. It says that " + invitation, False),
            (invitation + ' This claim is false. — Alex Smith (@alexsmith)', False),
            (invitation + ' Samsung is launching a new phone. — Alex Smith (@alexsmith)', False),
            ('Alex Smith reports a new installation partnership. ' + invitation, False),
            ('Alex Smith previously reported that ' + invitation, False),
            ('陈明没有透露苹果已经邀请媒体参加10月28日举行的新品体验活动。', False),
        ):
            with self.subTest(fact=fact):
                claim = bind_media_invitation(capture('Source', '', title, lead, (fact,)))
                self.assertEqual(claim is not None, expected)
                if expected:
                    self.assertEqual(self.m.claim_eligibility(claim).tier, 'strong')
                    self.assertTrue(any(q[1] == 'report-attribution' for q in claim.qualifiers))

    def test_external_device_update_keeps_its_compatibility_target(self):
        events, rows = self.cluster_sources('1f82d4bf6d92c0a9881e03ff')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('ecosystem', 'software_systems'))
        self.assertTrue(any('iOS' in fact and '投屏' in fact for fact in rows[0]['key_facts']))
        for title, lead, tier in (
            ('星海电视迎秋季升级，新增 iOS 快捷投屏功能',
             '星海发布电视固件更新，新增 iOS 投屏功能。', 'ecosystem'),
            ('Aurora TV adds iOS screen mirroring support',
             'Aurora released a television firmware update enabling iOS screen mirroring.', 'ecosystem'),
            ('星海电视支持 iOS 快捷投屏功能',
             '星海发布新款电视，支持 iOS 投屏功能。', 'weak'),
            ('Aurora TV adds iOS screen mirroring support',
             'Aurora released a new television with iOS screen mirroring support.', 'weak'),
            ('星海电视迎秋季升级，新增 iOS 快捷投屏功能',
             '星海去年发布电视固件更新，新增 iOS 投屏功能。', 'weak'),
            ('星海电视迎秋季升级，新增 iOS 快捷投屏功能',
             '星海发布电视固件更新，但没有新增 iOS 投屏功能。', 'weak'),
            ('星海电视迎秋季升级，新增 iOS 快捷投屏功能',
             '星海发布电视固件更新，而另一品牌新增 iOS 投屏功能。', 'weak'),
            ('Aurora TV adds iOS screen mirroring support',
             'Aurora released a television firmware update and Boreal added iOS screen mirroring.', 'weak'),
            ('Aurora TV adds iOS screen mirroring support',
             'Aurora released a television firmware update enabling macOS screen mirroring.', 'weak'),
            ('iOS 28 新增电视投屏功能',
             '苹果为 iOS 28 新增电视投屏功能。', 'strong'),
        ):
            with self.subTest(title=title, lead=lead):
                event, = self.m.cluster_articles([article_for(self.m, title, lead)])
                self.assertEqual(event.relevance_tier, tier)

    def test_reviewer_opinion_does_not_borrow_a_background_launch(self):
        events, rows = self.cluster_sources('52c7aa324799e6d3beedbbe9')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        self.assertTrue(any('CarPlay' in fact for fact in rows[0]['key_facts'])
                        or 'CarPlay' in rows[0]['summary'])
        from apple_news_core.event_identity import source_editorial_evaluation
        self.assertEqual(source_editorial_evaluation('A reviewer is unconvinced about the new iPad',
            'Apple introduced a new iPad this week. In a hands-on impressions video, a tech reviewer questions its value.'), 'review')
        self.assertFalse(source_editorial_evaluation('Apple explains the new iPad design',
            'Apple explained the new iPad design in response to a tech reviewer.'))
        for extra in ('', ' A reviewer also demonstrated these sensors in a review video.'):
            article = article_for(self.m, 'HomeView temperature and humidity sensors',
                'HomeView has temperature and humidity sensors.' + extra)
            event, = self.m.cluster_articles([article])
            self.assertEqual(event.relevance_tier, 'strong')
        current, _ = self.cluster_sources('e06c10fcf15d387d47931e03')
        self.assertEqual(len(current), 1)
        self.assertEqual((current[0].relevance_tier, current[0].category), ('strong', 'software_systems'))

    def test_institutional_attendance_does_not_become_a_broadcast_service(self):
        self.assert_group(('b51c10676c222837f2a3a2f8','a96ee24af589c5dfae103528'), 'hardware_products')

    def test_device_gaming_commentary_does_not_borrow_announced_specs(self):
        for sid in ('3992aad702aa96b30756ecaf','bdaa12c5700b2eae018cd6e7'):
            with self.subTest(source=sid):
                events, _ = self.cluster_sources(sid)
                self.assertTrue(all(e.relevance_tier == 'weak' for e in events))

    def test_same_map_city_capability_joins_across_headline_angles(self):
        self.assert_group(('a04be5aa80ccf4de41be8c90','54c5ad7833a47e071b1f2872'), 'software_systems')

    def test_attributed_production_plan_uses_its_own_schedule_not_launch_background(self):
        self.assert_group(('2c79ef55fba0f78c159c2f3e','00d847f97d483446680cfd67',
            'a03d26da850cc89e2f853e8d','60a856cf649cd2bf3afbedb7','c1c0f3714fb99c1f4e6559a3'), 'hardware_products')

    def test_service_fee_tables_preserve_price_region_across_coverage_tiers(self):
        usa = ('ee7b6ace7f6640f3127d82e9','e0f8000e5cef0fa387529bee',
               '5185b706f276abd5b80f5adc','3a52d8d6150e962f993f2a82','c73b10fdc5dde77d56f198e6')
        china = ('e0db7a94a1667af074f0dd5c','5baf3408e68dcabec8141e69')
        self.assert_group(usa, 'software_systems')
        self.assert_group(china, 'software_systems')
        articles = [a for sid in usa + china for a in self.source_articles(sid)]
        for order in (articles, articles[::-1]):
            events = self.m.cluster_articles(order)
            self.assertEqual(sorted(len(e.articles) for e in events), [2, 5])

    def test_purchase_justification_retains_fees_as_supporting_evidence(self):
        events, rows = self.cluster_sources('b262e6c37853373cf3e6a7a1')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'weak')
        self.assertEqual(rows[0]['sources'][0]['url'], self.rows['b262e6c37853373cf3e6a7a1']['evidence']['url'])
        self.assertTrue(any('$19' in fact and '$49' in fact for fact in rows[0]['key_facts']))
        from apple_news_core.event_identity import source_editorial_evaluation
        self.assertEqual(source_editorial_evaluation('This iPad feature could help customers justify the cost',
            'The feature could help customers justify spending more on the tablet.'), 'buying_advice')
        self.assertEqual(source_editorial_evaluation('Apple says this iPad feature could help customers justify the cost',
            'Apple said, "This feature could help customers justify the cost."'), '')

    def test_trading_day_and_intraday_stage_are_not_one_close(self):
        a = article_for(self.m, 'Apple closes above $6 trillion',
            'Apple closed with a $6 trillion market capitalization on November 4, 2027.')
        for title, lead in (
            ('Apple closes above $6 trillion', 'Apple closed with a $6 trillion market capitalization on November 5, 2027.'),
            ('Apple reaches $6 trillion intraday', 'Apple reached a $6 trillion market capitalization during intraday trading on November 4, 2027.'),
        ):
            other = article_for(self.m, title, lead)
            for order in ([a, other], [other, a]):
                self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_current_report_signatures_protect_version_results_and_plan_stage(self):
        pairs = (
            (('Apple Intelligence coming to China in December with iOS 28.3',
              'Bloomberg reports Apple plans to launch Apple Intelligence in China in December with iOS 28.3.'),
             ('Apple Intelligence coming to China in January with iOS 28.4',
              'Bloomberg reports Apple plans to launch Apple Intelligence in China in January with iOS 28.4.')),
            (('iPhone Duo benchmark report', 'The iPhone Duo scored a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8.'),
             ('iPhone Duo benchmark report', 'The iPhone Duo scored a single-core score of 4200 and a multi-core score of 12500 on Geekbench 8.')),
        )
        for pair in pairs:
            a = [article_for(self.m, *row) for row in pair]
            for order in (a, a[::-1]):
                self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_new_current_frames_reject_denial_and_background_ownership(self):
        from apple_news_core.event_identity import (source_trade_secret_procedure_frame,
            source_named_publication_frame, source_current_report_frame)
        for title, lead in (
            ('OpenAI agrees not to use Apple trade secrets', 'OpenAI denied that it had voluntarily agreed not to use Apple trade secrets at the court hearing.'),
            ('Apple agrees not to use OpenAI trade secrets', 'Apple has not agreed to the requested voluntary undertaking in the court case.'),
            ("OpenAI responds to Apple's trade secret lawsuit", "OpenAI has volunteered not to use Microsoft trade secrets. Apple's court case continues."),
            ("OpenAI responds to Apple's trade secret lawsuit", 'The court case continues. OpenAI denied that OpenAI has agreed not to use Apple trade secrets.'),
        ):
            self.assertIsNone(source_trade_secret_procedure_frame(title, lead, (), self.m.title_led_identity(title, lead)))
        title = 'Designer Alice Reed creates a collection with iPad'
        lead = 'Designer Alice Reed made the collection independently. Apple has not shared this project or published a creative profile.'
        self.assertIsNone(source_named_publication_frame(title, lead, (lead,), self.m.title_led_identity(title, lead)))
        self.assertIsNone(source_current_report_frame('Apple closed above $2 trillion last year',
            'Apple closed at a $2 trillion market capitalization in 2025. This is a historical review.', ()))

    def test_focused_reports_cannot_borrow_another_subject_or_a_denied_action(self):
        pairs = (
            (('iPhone Duo benchmark report', 'The iPhone Duo scored a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8.'),
             ('iPhone Duo benchmark report', 'The iPhone 18 Pro scored a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8. The iPhone Duo has not been tested.')),
            (('Apple Intelligence coming to China in December with iOS 28.3', 'Bloomberg reports Apple plans to launch Apple Intelligence in China in December with iOS 28.3.'),
             ('Apple Intelligence coming to China in December with iOS 28.3', 'Bloomberg denied reports that Apple plans to launch Apple Intelligence in China in December with iOS 28.3.')),
            (('Apple Maps launches Detailed City Experience in Austin, Texas', 'Apple Maps now offers Detailed City Experience in Austin, Texas.'),
             ('Apple Maps launches Detailed City Experience in Austin, Texas', 'Apple denied that Detailed City Experience is available in Austin, Texas.')),
            (('Apple showcases a new fashion collection', 'Apple today shared a creative profile of designer Alice Reed and her collection.'),
             ('Apple showcases a new fashion collection', 'Last year Apple shared a creative profile of designer Alice Reed and her collection. This is a retrospective.')),
            (('Apple publishes iPhone Duo repair fees', 'Apple published iPhone Duo repair fees in the US.'),
             ('Apple publishes iPhone Duo repair fees', 'Apple published iPhone Duo repair fees in Canada.')),
        )
        for pair in pairs:
            with self.subTest(lead=pair[1][1]):
                articles = [article_for(self.m, *row) for row in pair]
                for order in (articles, articles[::-1]):
                    self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_closing_result_requires_actual_apple_measurement(self):
        from apple_news_core.event_identity import source_current_report_frame
        for lead in ('Apple rival Nvidia closed above a $6 trillion market capitalization on November 4, 2027.',
                     'Nvidia closed above $6 trillion today. Apple remains below the threshold.',
                     'Apple may close above $6 trillion tomorrow, analysts forecast.'):
            frame = source_current_report_frame('Apple reaches $6 trillion', lead, ())
            self.assertTrue(frame is None or frame.action != 'closing-market-value-report')

    def test_production_units_keep_negation_and_anaphoric_subject(self):
        from apple_news_core.event_identity import source_dated_production_frame
        for units in (
            ('iPhone 19 production did not start in November 2027.',),
            ('Apple also discussed iPhone 18. This model is scheduled to start production in November 2027.',),
        ):
            self.assertIsNone(source_dated_production_frame('iPhone 19 production report',
                'The report discusses a future device.', source_units=units))

    def test_named_card_owner_must_enclose_its_discovery_lead(self):
        from apple_news_core.collection import _ListingLeadParser
        parser = _ListingLeadParser()
        parser.feed('<div data-io-article-url="https://www.macrumors.com/own/"></div>'
            '<aside><div class="js-contentInner"><p>Apple released an unrelated device.</p></div></aside>')
        self.assertEqual(parser.summary, '')

    def test_collective_attendance_keeps_the_named_person(self):
        current = article_for(self.m, '苹果库克参加大学年会',
            '苹果董事长库克出席清华大学经济管理学院顾问委员会2027年会。')
        unrelated = article_for(self.m, '苹果库克参加大学年会',
            '苹果董事长库克不会出席。张先生参加清华大学经济管理学院顾问委员会2027年会。')
        for order in ([current, unrelated], [unrelated, current]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_capability_assertions_keep_their_host_and_real_status(self):
        from apple_news_core.event_identity import source_device_operation_frame
        for title, lead in (
            ('HomePod Mac system audio support', 'Apple confirms HomePod cannot output Mac system audio. Older Macs can output audio to wired speakers.'),
            ('HomeView widgets support', 'A designer imagines Apple HomeView running widgets from iPhone.'),
        ):
            with self.subTest(title=title):
                self.assertIsNone(source_device_operation_frame(title, lead))

    def test_descriptive_remote_name_resolves_from_its_own_captured_definition(self):
        events, _ = self.cluster_sources('a037e00269305e4455bf4803')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'strong')
        from apple_news_core.event_identity import source_device_operation_frame
        self.assertIsNone(source_device_operation_frame('New Find My-compatible remote works with Apple TV',
            'A third-party company launched its own remote with Find My support.'))


    def test_current_assertions_keep_negation_and_background_separate(self):
        true_score = article_for(self.m, 'iPhone Duo benchmark report',
            'The iPhone Duo achieved a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8.')
        denied_score = article_for(self.m, 'iPhone Duo benchmark report',
            'The iPhone Duo did not achieve a single-core score of 4100 and a multi-core score of 12000 on Geekbench 8.')
        for order in ([true_score, denied_score], [denied_score, true_score]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)
        current = article_for(self.m, 'HomeView widgets support', 'Apple HomeView now runs widgets from iPhone.')
        historical_context = article_for(self.m, 'HomeView widgets support',
            'Apple HomeView now runs widgets from iPhone. An independent designer previously proposed a concept interface.')
        for order in ([current, historical_context], [historical_context, current]):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].relevance_tier, 'strong')


    def test_current_feature_statement_supports_the_reported_regional_activation(self):
        reported = self.source_articles('d54b747638cfb257e22235ce')
        direct = article_for(self.m, 'Apple Watch sleep apnea notifications launch in China',
            'Apple launched sleep apnea notifications in China today.')
        for order in (reported + [direct], [direct] + reported):
            events = self.m.cluster_articles(order)
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'software_systems'))
        from apple_news_core.event_identity import source_platform_component_frame
        for lead in (
            '苹果高管提到全球很多人受睡眠呼吸暂停影响。Apple Watch去年在中国推出睡眠呼吸暂停通知。',
            '苹果高管表示，Apple Watch睡眠呼吸暂停通知尚未在中国推出。',
            '苹果高管讨论睡眠呼吸暂停。第三方手环的睡眠呼吸暂停通知现已在中国推出。',
            'Apple Watch中国用户关注睡眠呼吸暂停，第三方手环现已推出相关通知。',
        ):
            self.assertIsNone(source_platform_component_frame('苹果高管谈睡眠呼吸暂停', lead, ()))


    def test_visit_and_institutional_attendance_keep_their_primary_action(self):
        visits=('a2b6f13bb8998ac645bbbd92','5f4d980b3f65b7b6b4b895c1')
        attendance=('b51c10676c222837f2a3a2f8','a96ee24af589c5dfae103528')
        self.assert_group(visits, 'hardware_products')
        all_articles=[a for sid in visits+attendance for a in self.source_articles(sid)]
        for order in (all_articles, all_articles[::-1]):
            events=self.m.cluster_articles(order)
            self.assertEqual(sorted(len(e.articles) for e in events), [2,2])

    def test_source_owned_city_translation_keeps_the_same_availability(self):
        self.assert_group(('fb251e65648db42efd73f16a','a04be5aa80ccf4de41be8c90','54c5ad7833a47e071b1f2872'), 'software_systems')

    def test_deictic_lifecycle_headline_resolves_its_own_device_list(self):
        events,_=self.cluster_sources('791c3fbd409df100674e6f46')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].relevance_tier,'strong')
        self.assert_group(('791c3fbd409df100674e6f46', '642f3b25e137627d376780d3', '26504e5d7524a07f2ad46402'), 'hardware_products')


    def test_translated_city_rollout_does_not_borrow_a_plan_or_another_owner(self):
        from apple_news_core.event_identity import source_current_report_frame
        title='美国城市解锁苹果精细化地图，高精3D建模'
        for lead in (
            '苹果公司将在美国某市（Boston, Massachusetts）为Apple Maps推出详细城市体验（Detailed City Experience）功能。',
            '苹果公司否认在美国某市（Boston, Massachusetts）为Apple Maps推出详细城市体验（Detailed City Experience）功能。',
            '第三方公司在美国某市（Boston, Massachusetts）为Apple Maps推出详细城市体验（Detailed City Experience）概念图。',
            '去年，苹果公司在美国某市（Boston, Massachusetts）为Apple Maps推出详细城市体验（Detailed City Experience）功能。本文回顾当时的发布。',
        ):
            self.assertIsNone(source_current_report_frame(title,lead,()))


    def test_nested_list_prices_reach_event_facts_or_required_review(self):
        row = json.loads((Path(__file__).parent / 'fixtures/20261015_nested_lists.json').read_text())
        candidate = self.m.Candidate(row['source'], row['url'], row['title'],
            '苹果官网现已公布了 iPhone Duo 手机的维修预估费用。', '2026-10-14T14:21:15+00:00')
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 10, 15, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        with TemporaryDirectory() as directory:
            args = self.m.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(self.m, 'datetime', Clock), \
                    patch.object(self.m, 'collect_candidates_from_sources', return_value=[candidate]), \
                    patch.object(self.m, 'fetch_url', return_value=row['html']):
                result = self.m.run(args)
        self.assertEqual(len(result['events']), 1)
        exposed = json.dumps([result['events'], result['final_brief_queue']], ensure_ascii=False)
        for price in row['expected_rows']:
            with self.subTest(price=price):
                self.assertIn(price, exposed)
        self.assertIn('购买了 AppleCare+', exposed)

    def test_nested_list_wrappers_preserve_members_without_duplicating_text(self):
        page = ('<article><p>Apple lists service conditions.</p><ul>'
                '<li><p>Battery: 80%</p><div>Coverage: 2 years</div></li>'
                '<li><div><p>Screen: $99</p></div></li>'
                '<li>Outer<ul><li><p>Inner</p></li></ul>Tail</li>'
                '</ul><p>Following paragraph.</p><aside><li><p>Unrelated</p></li></aside>'
                '<table><tr><td><p>Cell</p></td><td>Value</td></tr></table></article>')
        evidence = self.m.capture_article_evidence('Source', 'https://example.test/list', page, 'Title')
        self.assertEqual([(u.kind, u.text) for u in evidence.units], [
            ('p', 'Apple lists service conditions.'), ('li', 'Battery: 80%'),
            ('li', 'Coverage: 2 years'), ('li', 'Screen: $99'), ('li', 'Outer'),
            ('li', 'Inner'), ('li', 'Tail'), ('p', 'Following paragraph.'), ('tr', 'Cell | Value')])

    def test_paragraph_requirement_lists_and_purpose_limits_survive_shortlists(self):
        row = json.loads((Path(__file__).parent / 'fixtures/20261015_nested_lists.json').read_text())['paragraph_requirements']
        article = article_for(self.m, row['title'], row['summary'])
        article.source, article.url = row['source'], row['url']
        article.evidence = self.m.capture_article_evidence(row['source'], row['url'], row['html'], row['title'])
        article.key_facts = self.m.extract_key_facts(row['html'], row['title'], row['source'])
        event = self.m.cluster_articles([article])[0]
        exposed = [fact.text for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed)]
        for required in row['required']:
            with self.subTest(required=required):
                self.assertTrue(any(required in fact for fact in exposed), required)

    def test_requirement_lists_stop_after_final_row_and_keep_foreign_ownership(self):
        title = 'Apple adds a new iPhone monitoring feature'
        lead = 'Apple announced a new iPhone monitoring feature today.'
        condition = 'This feature is not intended for professional diagnosis or treatment.'
        page = ('<article><p>' + lead + '</p><p>' + condition + '</p>'
                '<p>Microsoft announced a separate monitoring service.</p>'
                '<p>Its requirements are:</p><p>Enable cloud tracking;</p>'
                '<p>Record at least 12 nights.</p><p>Unrelated advice.</p></article>')
        article = article_for(self.m, title, lead)
        article.evidence = self.m.capture_article_evidence(article.source, article.url, page, title)
        event = self.m.cluster_articles([article])[0]
        retained = [fact.text for fact in event.fact_plan.facts]
        pending = [fact.text for fact in event.fact_plan.unprocessed]
        self.assertIn(condition, retained + pending)
        for required in ('Enable cloud tracking;', 'Record at least 12 nights.'):
            self.assertIn(required, pending)
            self.assertNotIn(required, retained)
        self.assertNotIn('Unrelated advice.', retained + pending)

    def test_requirement_heading_owner_precedes_shared_platform_words(self):
        title = 'Apple adds a new iPhone monitoring feature'
        lead = 'Apple announced a new iPhone monitoring feature today.'
        for owner in ('Microsoft', 'Apple'):
            page = ('<article><p>' + lead + '</p><p>Requirements for ' + owner
                    + "'s iPhone monitoring service:</p><p>Enable cloud tracking;</p>"
                    '<p>Record at least 12 nights.</p></article>')
            article = article_for(self.m, title, lead)
            article.evidence = self.m.capture_article_evidence(article.source, article.url, page, title)
            event = self.m.cluster_articles([article])[0]
            retained = [fact.text for fact in event.fact_plan.facts]
            pending = [fact.text for fact in event.fact_plan.unprocessed]
            for requirement in ('Enable cloud tracking;', 'Record at least 12 nights.'):
                with self.subTest(owner=owner, requirement=requirement):
                    self.assertIn(requirement, retained if owner == 'Apple' else pending)
                    if owner == 'Microsoft':
                        self.assertNotIn(requirement, retained)

    def test_translated_sensor_specifications_share_the_reported_component(self):
        self.assert_group(('1599ed9d10717af2db598dcc', '466c482348338161c52125ef'), 'hardware_products')
        actual = article_for(self.m, 'HomePod 2 includes temperature and humidity sensors',
            'HomePod 2 includes built-in temperature and humidity sensors for indoor readings.')
        same = article_for(self.m, 'HomePod 2 自带温 / 湿度传感器',
            '苹果官方规格显示，HomePod 2 内置温度和湿度传感器，可监测室内环境。')
        self.assertEqual(len(self.m.cluster_articles([actual, same])), 1)
        for title, lead in (
            ('HomePod 3 includes temperature and humidity sensors', 'HomePod 3 includes built-in temperature and humidity sensors.'),
            ('HomePod 2 software update enables temperature and humidity sensors', 'Apple released a HomePod 2 software update to activate its temperature and humidity sensors.'),
            ('HomePod 2 does not include humidity sensors', 'Apple confirmed that HomePod 2 does not include humidity sensors.'),
            ('A HomePod 2 concept includes temperature and humidity sensors', 'An independent designer imagined a HomePod 2 concept with extra sensors.'),
            ('Third-party temperature sensors for HomePod 2', 'Northstar launched its temperature sensors, which work with HomePod 2.'),
            ('HomePod 2 temperature and humidity sensors', "A designer's concept of HomePod 2 includes built-in temperature and humidity sensors."),
            ('HomePod 2 temperature and humidity sensors', 'HomePod 2 has temperature and humidity sensors enabled today by a new software update.'),
        ):
            other = article_for(self.m, title, lead)
            for ordered in ([actual, other], [other, actual]):
                with self.subTest(title=title):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 2)

    def test_current_lifecycle_label_can_omit_the_list_noun(self):
        self.assert_group(('791c3fbd409df100674e6f46', '642f3b25e137627d376780d3',
                           '26504e5d7524a07f2ad46402', 'f4b31a16512daf580d96fed0'), 'hardware_products')

    def test_short_lifecycle_label_requires_current_apple_owned_listing(self):
        base = article_for(self.m, 'Apple adds the 2017 MacBook to its obsolete list',
            'Apple today added the 2017 MacBook to its obsolete product list.')
        title = '苹果 MacBook 2017 款被列入“停产”'
        for other_title, lead in (
            (title, '苹果今天更新停产产品名单，将 MacBook 2017 款列入停产（Obsolete）产品。'),
            (title.replace('“停产”', '停产'), '苹果今天更新停产产品名单，将 MacBook 2017 款列入停产（Obsolete）产品。'),
        ):
            other = article_for(self.m, other_title, lead)
            for ordered in ([base, other], [other, base]):
                with self.subTest(lead=lead, title=other_title):
                    events = self.m.cluster_articles(ordered)
                    self.assertEqual(len(events), 1)
                    self.assertEqual(events[0].relevance_tier, 'strong')
        for other_title, lead in (
            (title, '独立维修商 Northstar 今天更新自己的停产设备名单，将 MacBook 2017 款列入名单；苹果未调整其官方产品状态。'),
            (title, '苹果否认将 MacBook 2017 款列入停产名单，官方产品状态未改变。'),
            ('回顾：' + title, '去年苹果更新停产产品名单，将 MacBook 2017 款列入停产（Obsolete）产品。本文回顾当时的调整。'),
            ('传闻：' + title, '传闻称苹果明年计划将 MacBook 2017 款列入停产名单，目前尚未调整。'),
        ):
            other = article_for(self.m, other_title, lead)
            for ordered in ([base, other], [other, base]):
                with self.subTest(lead=lead):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 2)

    def test_abbreviated_platform_name_uses_its_own_reported_rollout(self):
        self.assert_group(('70b6eb9654a6c61310ca48ee', 'ee92100ad1812fca913bb9ae',
                           '8eea7ada27d4d7f476f98900'), 'software_systems')
        from apple_news_core.event_identity import source_current_report_frame
        title = 'Apple AI coming to China in December with iOS 27.3'
        lead = 'Bloomberg reports Apple plans to launch Apple Intelligence in China in December with iOS 27.3.'
        base = article_for(self.m, title, lead)
        self.assertIsNotNone(source_current_report_frame(title, lead, ()))
        for other_title, other_lead in (
            (title, 'Microsoft plans to launch its AI service in December. Apple Intelligence is a competing service.'),
            (title, 'Bloomberg says Apple denied plans to launch Apple Intelligence in China.'),
            (title, 'Bloomberg reports Apple plans to launch a new iPhone with iOS 27.3 in China in December, while Apple Intelligence remains under development.'),
            ('苹果 AI 将于12月随 iOS 27.3 在中国上线', '彭博称，苹果计划于12月在中国发布搭载iOS 27.3的新iPhone，同时回顾去年推出Apple Intelligence的情况。'),
            ('苹果 AI 将于12月随 iOS 27.3 在中国上线', '彭博称，苹果计划于12月在中国发布搭载iOS 27.3的新iPhone并回顾去年推出Apple Intelligence的情况。'),
            (title.replace('December', 'January').replace('27.3', '27.4'), lead.replace('December', 'January').replace('27.3', '27.4')),
        ):
            other = article_for(self.m, other_title, other_lead)
            for ordered in ([base, other], [other, base]):
                with self.subTest(lead=other_lead):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 2)

    def test_lifecycle_listing_keeps_explicit_status_and_model_year(self):
        obsolete = article_for(self.m, 'Apple adds the 2017 MacBook to its obsolete list',
            'Apple today added the 2017 MacBook to its obsolete product list.')
        vintage = article_for(self.m, '苹果 MacBook 2017 款被列入“过时”',
            '苹果今天更新过时产品名单，将 MacBook 2017 款列入过时（Vintage）产品。')
        earlier = article_for(self.m, '苹果 MacBook 2016 款被列入“停产”',
            '苹果今天更新停产产品名单，将 MacBook 2016 款列入停产（Obsolete）产品。')
        for other in (vintage, earlier):
            for ordered in ([obsolete, other], [other, obsolete]):
                with self.subTest(title=other.title):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 2)
        same = article_for(self.m, 'Apple adds the 2017 MacBook to its vintage list',
            'Apple today added the 2017 MacBook to its vintage product list.')
        for ordered in ([vintage, same], [same, vintage]):
            self.assertEqual(len(self.m.cluster_articles(ordered)), 1)

        chinese_vintage = article_for(self.m, '苹果 MacBook 2017 款被列入“复古”',
            '苹果今天更新复古产品名单，将 MacBook 2017 款列入复古产品，仍可在零件可用时维修。')
        for ordered in ([obsolete, chinese_vintage], [chinese_vintage, obsolete]):
            self.assertEqual(len(self.m.cluster_articles(ordered)), 2)
        for ordered in ([same, chinese_vintage], [chinese_vintage, same]):
            self.assertEqual(len(self.m.cluster_articles(ordered)), 1)
        for label in ('2016年款MacBook', '2016款MacBook'):
            earlier = article_for(self.m, '苹果' + label + '被列入“停产”',
                '苹果今天更新停产产品名单，将' + label + '列入停产（Obsolete）产品。')
            for ordered in ([obsolete, earlier], [earlier, obsolete]):
                with self.subTest(model=label):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 2)
        for background in ('而 MacBook Air 2015 款此前已被列入', 'MacBook Air 2015 款此前已被列入'):
            current = article_for(self.m, '苹果 MacBook 2017 款被列入“停产”',
                '苹果今天更新停产产品名单，将 MacBook 2017 款列入停产（Obsolete）产品，' + background + '。')
            for ordered in ([obsolete, current], [current, obsolete]):
                with self.subTest(background=background):
                    self.assertEqual(len(self.m.cluster_articles(ordered)), 1)

    def test_later_translations_keep_the_existing_reported_operation(self):
        for ids, category in (
            (('7d19cec9f4b2021195223997', '8cec308aa5b16d3a6915ade7', '4050cc4c2dd380083310ba37'), 'software_systems'),
            (('5c509cc5d8563b898d940d41', '5e9e5768deedb7e1f535449a', 'a516bc4391f6b117c551a13d', '72babaaccc4e5c4200f84099'), 'software_systems'),
            (('7f92c18e52788a5929e4ed4e', '3d0b32c9297e733796b43af1', 'ac104508e78dde6dbea96e91', '5f81b94a8bd27053ac4ca703', '75d84a5a85d7adb687d11102', '5d03ce08a69bb377a886db02'), 'hardware_products'),
            (('34706450af225330ed8da151', '21af1bf5b8bb3be3c5de5c99', '341c024b898136cd075ee543'), 'hardware_products'),
        ):
            with self.subTest(source=ids[-1]):
                self.assert_group(ids, category)

    def test_market_measurement_keeps_apple_results_despite_price_background(self):
        self.assert_group(('5dad1ac82ca98c81a25909d8',), 'hardware_products')

    def test_body_vendor_measurement_reaches_required_fact_review(self):
        sid = '5dad1ac82ca98c81a25909d8'
        events, _ = self.cluster_sources(sid)
        facts = events[0].fact_plan.unprocessed
        self.assertTrue(any('苹果以22%的市场份额位列第二' in fact.text for fact in facts))
        from apple_news_core.event_identity import source_local_report_passages
        from dataclasses import replace
        evidence = self.source_articles(sid)[0].evidence
        target = next(unit for unit in evidence.units if '苹果以22%' in unit.text)
        for detail in ('三星以22%的市场份额位列第二。', '去年苹果以22%的市场份额位列第二。',
                       'Omdia预计苹果下季度将获得22%的市场份额。', '三星和苹果合计占据22%的市场份额。'):
            units = tuple(replace(unit, text=detail) if unit.unit_id == target.unit_id else unit for unit in evidence.units)
            with self.subTest(detail=detail):
                self.assertFalse(any(row[0] == target.unit_id for row in source_local_report_passages(replace(evidence, units=units))))

    def test_market_measurement_uses_individual_current_vendor_results(self):
        from apple_news_core.event_identity import source_market_measurement_frame
        title = '内存涨价影响全球手机出货，三星苹果合计份额领先'
        lead = 'Omdia报告显示，2027年第三季度全球智能手机出货量下降。'
        for detail in ('苹果以21%的市场份额位列第二。', '苹果市场份额同比上升。'):
            frame = source_market_measurement_frame(title, lead, (detail,))
            self.assertIsNotNone(frame)
            self.assertEqual((frame.year, frame.period, frame.region), ('2027', 'q3', 'worldwide'))
        for detail in (
            '三星和苹果合计占据全球44%的智能手机市场份额。',
            '苹果和三星共同占全球44%的智能手机市场份额。',
            'Apple and Samsung together held 44 percent of smartphone shipments.',
            'Apple and Samsung, together held 44 percent of smartphone shipments.',
            '三星以23%的市场份额位列第一，苹果未公布本季度数据。',
            '去年苹果以21%的市场份额位列第二。',
            '苹果预计下季度将获得21%的市场份额。',
            'Omdia预计苹果本季度占据全球22%的智能手机市场份额。',
        ):
            with self.subTest(detail=detail):
                self.assertIsNone(source_market_measurement_frame(title, lead, (detail,)))
        for detail in ('苹果以21%的市场份额位列第二。',
                       '三星和苹果合计占据全球44%的智能手机市场份额。',
                       'Apple and Samsung, together held 44 percent of smartphone shipments.',
                       'Omdia预计苹果本季度占据全球22%的智能手机市场份额。'):
            article = article_for(self.m, title, lead + detail)
            expected = 'strong' if detail.startswith('苹果以') else 'weak'
            self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, expected)

    def test_comparative_benchmark_keeps_the_measured_subject(self):
        from apple_news_core.event_identity import source_current_report_frame
        title = 'iPhone Duo 跑分曝光'
        detail = 'Geekbench 8跑分显示，iPhone Duo的CPU性能与iPhone 19 Pro基本处于同一水平，单核得分为4100分，多核得分为12000分。'
        frame = source_current_report_frame(title, detail, ())
        self.assertIsNotNone(frame)
        self.assertEqual(frame.subject, 'iphone-duo:geekbench-8')
        for other in (detail.replace('iPhone Duo的CPU性能与iPhone 19 Pro', 'iPhone 19 Pro的CPU性能与iPhone Duo'),
                      detail.replace('跑分显示', '预测显示'),
                      detail.replace('单核得分为', '并未取得单核得分为')):
            with self.subTest(detail=other):
                self.assertIsNone(source_current_report_frame(title, other, ()))

    def test_local_platform_conditions_do_not_borrow_an_affirmative_operation(self):
        from apple_news_core.event_identity import source_device_operation_frame, source_current_report_frame
        title = '苹果为HomePod扩展音频支持 Mac系统提示音也可无线播放'
        lead = '苹果确认，Mac上的系统提示音可以直接通过HomePod播放。'
        frame = source_device_operation_frame(title, lead)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.category, 'software_systems')
        for other in (lead.replace('可以', '不能'), '设计师设想Mac上的系统提示音可以直接通过HomePod播放。',
                      '苹果预计，Mac上的系统提示音未来可以通过HomePod播放。'):
            self.assertIsNone(source_device_operation_frame(title, other))
        denied = '苹果确认初代 HomePod mini 无缘 Siri AI'
        self.assertIsNone(source_device_operation_frame(denied, '苹果否认初代HomePod mini无缘Siri AI，确认它可以支持。'))
        self.assertIsNone(source_device_operation_frame('初代 HomePod mini 无缘 Siri AI',
            '苹果尚未确认初代HomePod mini无缘Siri AI，目前仍在测试兼容性。'))
        for current, other in (
            ((title, lead), (title, '苹果预计，Mac上的系统提示音未来可以通过HomePod播放。')),
            ((denied, '苹果确认初代HomePod mini无缘Siri AI，算力不足。'),
             ('初代 HomePod mini 无缘 Siri AI', '苹果尚未确认初代HomePod mini无缘Siri AI，目前仍在测试兼容性。')),
        ):
            pair = [article_for(self.m, *current), article_for(self.m, *other)]
            for order in (pair, pair[::-1]):
                self.assertEqual(len(self.m.cluster_articles(order)), 2)
        close_title = '苹果首次收盘站上市值门槛'
        for lead in ('三星股价于11月4日收涨，市值在收盘突破新高，苹果没有变化。',
                     '去年苹果股价于11月4日收涨，市值在收盘突破新高。'):
            self.assertIsNone(source_current_report_frame(close_title, lead, ()))

    def test_visible_publication_field_precedes_future_sale_dates(self):
        row = json.loads((Path(__file__).parent / 'fixtures/20261015_publication_time.json').read_text())['visible_publication']
        source = self.sources[row['source']]
        page = ('<title>Apple sale starts October 15, 2026 at 8:00 AM PDT</title>'
                + row['publication_element'] + '<article>' + row['body_event_paragraph'] + '</article>')
        candidate = self.m.Candidate(source.name, row['url'], 'Apple sales report', '',
                                     '2026-10-13T21:35:09.473+08:00')
        result = self.m.extract_article(candidate, source, page, {})
        self.assertEqual(result[3], datetime(2026, 10, 13, 13, 35, 9, tzinfo=timezone.utc))
        self.assertEqual(result[4:6], (row['published_raw'], 'source publication field'))
        self.assertLess(result[3], datetime(2026, 10, 14, 2, 52, tzinfo=timezone.utc))
        decoy = '<span id="pubtime_baidu">2020/1/1 08:00:00</span>'
        for inactive in ('<!--' + decoy + '-->', '<script>' + decoy + '</script>', '<template>' + decoy + '</template>'):
            with self.subTest(inactive=inactive):
                self.assertEqual(self.m.extract_time_candidates(inactive + page, source.name)[0],
                                 (row['published_raw'], 'source publication field'))
        self.assertFalse(any(label == 'source publication field'
                             for _, label in self.m.extract_time_candidates(page, 'MacRumors')))

    def test_visible_publication_line_excludes_body_event_dates(self):
        page = '<div>Published 2026/10/14 09:30:00</div><p>Apple sales start 10 月 15 日 20:00.</p>'
        body_dates = [raw for raw, label in self.m.extract_time_candidates(page) if label == 'body date pattern']
        self.assertEqual(body_dates, ['2026/10/14 09:30:00'])

    def test_provider_publication_metadata_precedes_body_event_dates(self):
        rows=json.loads((Path(__file__).parent/'fixtures/20261015_publication_time.json').read_text())['sources']
        source=self.sources['快科技']
        for row in rows:
            page=row['publication_script']+'<article>'+row['body_event_paragraph']+'</article>'
            candidate=self.m.Candidate('快科技',row['url'],'Apple product report','')
            result=self.m.extract_article(candidate,source,page,{})
            self.assertEqual(result[4:6],(row['published_raw'],'source publication metadata'))
            expected=self.m.parse_datetime_value(row['published_raw'],source.default_tz).astimezone(timezone.utc)
            self.assertEqual(result[3],expected)
        old_assignment="var g_PostDateStr = new Date('2020-01-01 08:00:00');"
        for comment in ('/*\n'+old_assignment+'\n*/', '// '+old_assignment):
            page='<script>'+comment+"\nvar quoted = 'https://example.test/*text*/';\n"+"var g_PostDateStr = new Date('2026-10-15 09:30:00');</script>"
            values=self.m.extract_time_candidates(page,'快科技')
            self.assertEqual(values[0],('2026-10-15 09:30:00','source publication metadata'))
        raw=rows[0]['publication_script']
        for page, source_name in ((raw,'MacRumors'),(raw.replace('<script language="javascript">','<pre>').replace('</script>','</pre>'),'快科技'),(raw.replace('g_PostDateStr','g_ModifiedDateStr'),'快科技')):
            self.assertFalse(any(label=='source publication metadata' for _,label in self.m.extract_time_candidates(page,source_name)))


    def test_system_pairing_implementation_is_software_interoperability(self):
        events, _ = self.cluster_sources('cc64e4cef573c9a70236d518')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category),
                         ('ecosystem', 'software_systems'))
        self.assertEqual(len(events[0].articles), 1)

    def test_system_pairing_requires_an_implemented_device_protocol(self):
        from apple_news_core.event_identity import source_system_pairing_frame
        for title, lead in (
            ('BridgeKit connects Apple Watch to Linux and Windows',
             "BridgeKit now reimplements Apple Watch pairing and activation, allowing setup on Linux and Windows without an iPhone."),
            ('BridgeKit connects Apple Watch to Android',
             "BridgeKit now reimplements Apple Watch pairing and activation after last year's failed attempt."),
            ('开源项目实现 Apple Watch 与安卓电脑配对',
             'WatchBridge 已重建 Apple Watch 配对与激活流程，让手表无需 iPhone 即可在 Android 和 Windows 上完成设置并持续连接。'),
        ):
            with self.subTest(lead=lead):
                frame = source_system_pairing_frame(title, lead)
                self.assertIsNotNone(frame)
                self.assertEqual((frame.tier, frame.category), ('ecosystem', 'software_systems'))
                event = self.m.cluster_articles([article_for(self.m, title, lead)])[0]
                self.assertEqual((event.relevance_tier, event.category), ('ecosystem', 'software_systems'))
        title = 'BridgeKit connects Apple Watch to Android'
        for lead in (
            'BridgeKit forwards notifications from Android through an already paired iPhone app.',
            'BridgeKit plans to reimplement Apple Watch pairing and activation for Android next year.',
            'BridgeKit has not reimplemented Apple Watch pairing and activation for Android.',
            "BridgeKit doesn't reimplement Apple Watch pairing and activation for Android.",
            'Last year BridgeKit reimplemented Apple Watch pairing and activation for Android. This article revisits that project.',
            'BridgeKit reimplements a Samsung watch pairing and activation flow. Apple Watch is a comparison device.',
            'BridgeKit reimplements Samsung watch pairing and activation, using Apple Watch as a comparison device.',
            'Apple Watch inspired BridgeKit, which reimplements Samsung watch pairing and activation.',
            'BridgeKit has developed an Android app. Another project reimplements Apple Watch pairing and activation.',
            'BridgeKit has developed an Apple Watch setup guide, while RivalKit reimplements Apple Watch pairing and activation for Android.',
            'BridgeKit has developed an Apple Watch setup guide, and RivalKit reimplements Apple Watch pairing and activation for Android.',
            'BridgeKit has developed a tool to handle the full Apple Watch setup process. The developers say that it is a guide, and RivalKit reimplements Apple Watch pairing and activation.',
            'WatchBridge 计划重建 Apple Watch 配对与激活流程，以后可通过安卓手机完成设置。',
            'WatchBridge 尚未重建 Apple Watch 配对与激活流程，安卓手机仍无法完成设置。',
            '去年 WatchBridge 已重建 Apple Watch 配对与激活流程，本文回顾安卓适配项目。',
        ):
            with self.subTest(lead=lead):
                self.assertIsNone(source_system_pairing_frame(title, lead))


    def test_first_party_feature_inventory_is_not_an_accessory_compatibility_story(self):
        article = self.source_articles('52cc918c31b2ba1a9e60a8aa')[0]
        # The migrated inventory consumes its source binding, not the legacy
        # accessory predicate's view of the generated display text.
        self.assertEqual(article.bound_claim.subject_relation, 'apple-direct')
        events = self.m.cluster_articles([article])
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('strong', 'software_systems')])
        for title, text in (
            ('Rival display supports HomeView',
             'Rival offers a display accessory that supports HomeView and iPhone.'),
            ('HomeView-compatible charging dock launches',
             'Rival launched a charging dock compatible with HomeView and iPhone.'),
            ('Third-party screen supports Apple TV',
             'The display accessory supports Apple TV and iPhone.'),
            ('Northstar display gets HomeView features',
             'Northstar offers a display accessory supporting HomeView and iPhone.'),
        ):
            with self.subTest(title=title):
                self.assertTrue(self.m.is_third_party_accessory_platform_compatibility_story(title, text))

    def test_device_feature_inventory_preserves_recaps_and_other_owners(self):
        from apple_news_core.event_identity import source_device_operation_frame
        title = '6 iPad features you might have missed'
        lead = 'Apple plans to launch the iPad next month. This report describes its operating features.'
        unit = 'iPad supports Safari recipe walkthroughs and multiple timers.'
        frame = source_device_operation_frame(title, lead, source_units=(unit,))
        self.assertIsNotNone(frame)
        self.assertEqual((frame.category, frame.tier), ('software_systems', 'strong'))
        for detail in ('iPad supports Bluetooth and multiple timers.',
                       'iPad supports Bluetooth, multiple timers and widgets.'):
            with self.subTest(unit=detail):
                result = source_device_operation_frame(title, lead, source_units=(detail,))
                self.assertIsNotNone(result)
                self.assertEqual(result.action, 'platform-capability-inventory-report')
        for other_title, other_lead, other_unit in (
            (title, 'We recap previously announced iPad features from last year.', unit),
            (title, lead, 'Rival supports Safari recipe walkthroughs using iPad as a screen.'),
            (title, lead, 'Designers imagine that iPad could support Safari recipe walkthroughs.'),
            ('6 Rival display features for iPad', lead, unit),
            (title, lead, 'iPad supports a brighter panel and a metal housing.'),
            (title, lead, 'Apple denies that iPad supports Safari recipe walkthroughs.'),
            (title, lead, 'iPad supports a brighter panel, while Rival provides Safari recipe walkthroughs.'),
            (title, lead, 'iPad supports a brighter panel and Rival provides Safari recipe walkthroughs.'),
            (title, lead, 'iPad supports a brighter panel, Rival provides Safari recipe walkthroughs.'),
        ):
            with self.subTest(title=other_title, unit=other_unit):
                result = source_device_operation_frame(other_title, other_lead, source_units=(other_unit,))
                self.assertTrue(result is None or result.action != 'platform-capability-inventory-report')

    def test_source_authentication_requirement_survives_fact_selection(self):
        events, _ = self.cluster_sources('95cd72fbca675105f689825b')
        self.assertEqual(events[0].relevance_tier, 'weak')
        facts = [fact for event in events
                 for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed)]
        target = '涉及解锁房门这类比较敏感的操作时，HomeView 则会要求用户通过人脸或 iPhone 完成身份验证。'
        retained = next((fact for fact in facts if target in fact.text), None)
        self.assertIsNotNone(retained)
        self.assertTrue(any(origin[3] == '1f326f1a78934b246d1e5269' for origin in retained.origins))

    def test_authentication_conditions_keep_local_ownership_and_statement_scope(self):
        title = 'HomeView 的家庭控制功能'
        lead = 'HomeView 支持家庭配件控制。'
        for detail, keep in (
            ('HomeView 要求用户通过 iPhone 完成身份验证后才能解锁房门。', True),
            ('HomeView requires identity verification on an iPhone before unlocking a door.', True),
            ('HomeView requires authentication before showing private account information.', True),
            ('Apple requires identity verification before HomeView unlocks a door.', True),
            ('Apple requires identity verification before Apple Cash transfers.', False),
            ('竞品设备要求用户通过 iPhone 完成身份验证后才能解锁房门。', False),
            ('Rival requires authentication on an iPhone before unlocking a door.', False),
            ('我建议 HomeView 要求用户通过 iPhone 完成身份验证后才能解锁房门。', False),
            ('如果 HomeView 能够要求用户完成身份验证，就有机会提升使用体验。', False),
        ):
            with self.subTest(detail=detail):
                article = article_for(self.m, title, lead)
                page = '<article><p>' + lead + '</p><p>' + detail + '</p></article>'
                article.evidence = self.m.capture_article_evidence(article.source, article.url, page, title)
                facts = self.m.source_supporting_facts(article, ())
                self.assertEqual(any(fact.text == detail for fact in facts), keep)

    def test_translated_versioned_app_report_joins_its_release(self):
        self.assert_group(('35bbaf85944ebb22bbf99d22', '1d515d60e134a606d1efbf02',
                           '86b24456d8dced8f27323318'), 'software_systems')

    def test_translated_creator_showcase_joins_the_named_publication(self):
        self.assert_group(('ab10809d911dbd2f6407b9a4', '7c18df70975289819274b1a6',
                           '06efa7c34f233aa48da9db71', '2ff5aa2744192d9ecc9321e4'),
                          'hardware_products')

    def test_translated_app_name_keeps_version_and_update_ownership(self):
        from apple_news_core.event_identity import source_first_party_app_frame
        title = '苹果 Meridian 2.4.0 更新：新增日历小组件'
        lead = '苹果更新日程（Apple Meridian）应用至 2.4.0 版本，新增日历小组件。'
        result = source_first_party_app_frame(title, lead)
        self.assertIsNotNone(result)
        self.assertEqual((result.subject, result.period), ('apple-app:apple-meridian', 'app-version:2.4.0'))
        current = article_for(self.m, title, lead)
        same = article_for(self.m, 'Apple Meridian App updated today',
                           'Apple released version 2.4.0 of its Meridian app for iPhone.')
        self.assertEqual(len(self.m.cluster_articles([current, same])), 1)
        versioned = [article_for(self.m, f'Apple Meridian {version} App Updated Today',
            'The Apple Meridian app was updated today with a new calendar widget.')
            for version in ('2.4.0', '2.5.0')]
        for order in (versioned, versioned[::-1]):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)
        for other_title, other_lead in (
            (title.replace('2.4.0', '2.5.0'), lead.replace('2.4.0', '2.5.0')),
            ('苹果 Meridian 2.4.0 更新计划', '苹果计划未来更新 Meridian 应用至 2.4.0，尚未发布。'),
            ('苹果 Meridian 2.4.0 并未更新', '苹果否认 Meridian 应用更新至 2.4.0 的消息。'),
            ('苹果 Meridian 2.4.0 更新回顾', '去年苹果更新了 Meridian 应用至 2.4.0 版本。'),
        ):
            other = article_for(self.m, other_title, other_lead)
            for order in ([current, other], [other, current]):
                with self.subTest(title=other_title):
                    self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_translated_showcase_keeps_creator_work_and_current_action(self):
        from apple_news_core.event_identity import source_named_publication_frame
        title = '苹果分享设计师新作品：iPad 参与时装秀'
        lead = '苹果公司昨日（11 月 4 日）发布公告，分享设计师 Alice Reed 名为“North Sky”的时装作品。'
        current = article_for(self.m, title, lead)
        same = article_for(self.m, 'Apple showcases a new fashion collection',
            'Apple today shared a creative profile of designer Alice Reed and her collection, “North Sky,” made with iPad.')
        self.assertEqual(len(self.m.cluster_articles([current, same])), 1)
        independent_title = '设计师 Alice Reed 的新时装作品：iPad 参与设计'
        independent = '苹果公司昨日（11 月 4 日）发布新 iPad。设计师 Alice Reed 独立展示名为“North Sky”的时装作品。'
        for background in (independent, independent.replace('iPad。', 'iPad，')):
            self.assertIsNone(source_named_publication_frame(independent_title, background, (),
                self.m.title_led_identity(independent_title, background)))
        for other in (
            lead.replace('Alice Reed', 'Maya Stone'),
            lead.replace('North Sky', 'Southern Light'),
            '去年苹果分享设计师 Alice Reed 名为“North Sky”的时装作品，本文进行回顾。',
            '设计师 Alice Reed 独立展示名为“North Sky”的时装作品，苹果没有发布或分享此项目。',
        ):
            article = article_for(self.m, title, other)
            for order in ([current, article], [article, current]):
                with self.subTest(lead=other):
                    self.assertEqual(len(self.m.cluster_articles(order)), 2)


    def test_current_benchmark_dataset_does_not_project_identifiers_or_comparators(self):
        sid = '656b1869e0381f71919a0970'
        articles = self.source_articles(sid)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, self.rows[sid]['evidence']['title'])
        events, rows = self.cluster_sources(sid)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].relevance_tier, events[0].category), ('strong', 'hardware_products'))
        text = ' '.join(rows[0]['key_facts']) + ' ' + rows[0]['summary']
        for value in ('3,985', '11,271', '4.93GHz', '11.30GB', '61,531', '6,845', '12,109', '9,076'):
            self.assertIn(value, text)
        gpu = next(f for f in events[0].fact_plan.facts if '61,531' in f.text)
        self.assertTrue(any(o[3] == 'eceed09ad70781b96d98250b' for o in gpu.origins))
        previous = self.source_articles('34706450af225330ed8da151')
        for order in (articles + previous, previous + articles):
            self.assertEqual(len(self.m.cluster_articles(order)), 2)

    def test_hardware_identifiers_are_not_numbered_product_families(self):
        from apple_news_core.event_identity import iphone_report_subjects
        for text in ('iPhone19,4', 'iPhone 19, 4', 'iPhone19，4'):
            with self.subTest(text=text):
                self.assertEqual(iphone_report_subjects(text), set())
        self.assertEqual(iphone_report_subjects('iPhone 19 Pro'), {'iphone-19'})

    def test_benchmark_continuation_requires_adjacent_current_owned_measurement(self):
        title = 'iPhone 20 跑分曝光'
        lead = '在 Geekbench 8 中，iPhone 20 的单核成绩为 4,100 分，多核成绩为 12,200 分。'
        configuration = 'iPhone 20 的 8 核 CPU 基础频率为 5.2GHz，单核成绩为 4,100 分，多核成绩为 12,200 分。'
        result = '在 GPU 方面，共有 4 条记录，目前最高分为 65,700 分。'
        for preceding, detail, keep in (
            (configuration, result, True),
            (configuration, 'For GPU results, the highest score is 65,700.', True),
            (configuration.replace('iPhone 20', 'iPhone 19'), result, False),
            ('去年' + configuration, result, False),
            (configuration + '下面转向 Rival 手机的测试。', result, False),
            (configuration.rstrip('。') + '，下面转向 Rival 手机的测试。', result, False),
            (configuration + '</p><h2>其他设备</h2><p>', result, False),
            (configuration, result.replace('目前最高分', '预计最高分'), False),
            (configuration, result.replace('目前最高分', '三星设备最高分'), False),
            (configuration, '在 GPU 方面，Rival 的最高分为 65,700 分。', False),
            (configuration, '在 GPU 方面，去年最高分为 65,700 分。', False),
        ):
            with self.subTest(preceding=preceding, detail=detail):
                article = article_for(self.m, title, lead)
                page = '<article><p>' + lead + '</p><p>' + preceding + '</p><p>' + detail + '</p></article>'
                article.evidence = self.m.capture_article_evidence(article.source, article.url, page, title)
                facts = self.m.source_supporting_facts(article, ())
                self.assertEqual(any(f.text == detail for f in facts), keep)

    def test_cpu_record_scores_preserve_the_measured_device(self):
        from apple_news_core.event_identity import source_current_report_frame
        title = 'iPhone 20 跑分曝光'
        lead = '在 Geekbench 8 跑分平台上，iPhone 20 出现多条 CPU 记录。'
        record = '在 CPU 跑分方面，这里附上多核跑分最高的一条记录，显示单核成绩为 4,100 分，多核成绩为 12,200 分。Geekbench 信息显示，iPhone 20 的 8 核 CPU 基础频率为 5.2GHz。'
        result = source_current_report_frame(title, lead, (record,))
        self.assertEqual((result.subject, result.period), ('iphone-20:geekbench-8', '4100-12200'))
        for other in (record.replace('iPhone 20 的', 'iPhone 19 的'),
                      record.replace('显示单核', '预计单核'),
                      record.replace('显示单核', 'Rival 手机单核'),
                      record.replace('多核跑分最高的一条记录', 'Rival 手机的一条记录')):
            with self.subTest(record=other):
                self.assertIsNone(source_current_report_frame(title, lead, (other,)))

    def test_third_party_app_chart_results_do_not_become_platform_actions(self):
        events, _ = self.cluster_sources('fd0e918ed0aba2859c745a8c')
        self.assertEqual([(e.relevance_tier, e.category) for e in events], [('weak', 'software_systems')])
        for title, lead in (
            ('App Store 免费榜前十被同一发行商占据', 'App Store 免费榜前十名里，有七款应用都来自星河科技。'),
            ('Northstar dominates the App Store top ten chart', 'Seven apps in the App Store top ten are from Northstar.'),
        ):
            with self.subTest(title=title):
                article = article_for(self.m, title, lead)
                self.assertEqual(self.m.cluster_articles([article])[0].relevance_tier, 'weak')
        from apple_news_core.event_identity import source_operation_frame
        for title, lead in (
            ('Apple publishes its App Store annual charts', 'Apple today published its annual App Store charts. Seven apps in the top ten are from Northstar.'),
            ('苹果调整 App Store 免费榜排序规则', '苹果今日调整 App Store 排行榜规则。此前榜单有七款应用来自星河科技。'),
            ('Apple Invites tops App Store chart', 'The Apple Invites app topped the App Store chart. The app is from Apple.'),
            ('Apple Invites tops App Store chart', 'Apple Invites topped the App Store chart today. Seven other apps in the top ten are from Northstar.'),
            ('App Store chart ranks apps under new rules announced by Apple', 'Apple changed its App Store ranking policy today. Seven apps in the old chart are from Northstar.'),
            ('Apple apps dominate App Store charts', 'Apple apps topped the App Store charts today. Seven other apps in the top ten are from Northstar.'),
        ):
            with self.subTest(title=title):
                result = source_operation_frame(title, lead, (), self.m.title_led_identity(title, lead))
                self.assertTrue(result is None or result.action != 'independent-app-chart-result')

    def test_locally_owned_regional_plan_joins_without_a_named_publisher(self):
        self.assert_group(('ee92100ad1812fca913bb9ae', '70b6eb9654a6c61310ca48ee',
                           '4fa58f0e7b5a02e015d25868'), 'software_systems')
        from apple_news_core.event_identity import source_current_report_frame
        title = '明年1月iOS 28.3更新后到来：苹果国行AI就绪'
        lead = '苹果计划在明年1月通过iOS 28.3系统更新，面向中国区用户正式推出苹果智能功能。'
        result = source_current_report_frame(title, lead, ())
        self.assertIsNotNone(result)
        self.assertEqual((result.action, result.period, result.model_generation),
                         ('reported-release-plan', '1', 'ios-28.3'))
        for other in (
            '苹果计划发布新iPhone，Rival计划在1月通过iOS 28.3推出自己的AI应用。',
            '苹果计划通过iOS 28.3系统更新，面向中国区用户正式推出苹果智能功能，Rival计划在1月推出自己的AI应用。',
            'Apple plans to launch Apple Intelligence in China through iOS 28.3, while Rival plans its own app in January.',
            '苹果否认计划在1月通过iOS 28.3系统更新，面向中国区用户正式推出苹果智能功能。',
            '去年苹果计划在1月通过iOS 28.3系统更新，面向中国区用户推出苹果智能功能，本文回顾旧计划。',
        ):
            with self.subTest(lead=other):
                neutral_title = 'iOS 28.3更新后到来：苹果国行AI就绪'
                self.assertIsNone(source_current_report_frame(neutral_title, other, ()))


if __name__ == '__main__':
    unittest.main()
