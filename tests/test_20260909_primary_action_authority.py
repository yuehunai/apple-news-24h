import unittest

from test_20260905_claim_ownership_boundaries import article_for, load_module


class PrimaryActionAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def groups(self, pairs):
        articles = [article_for(self.m, title, lead, source=str(i))
                    for i, (title, lead) in enumerate(pairs)]
        events = self.m.cluster_articles(articles)
        self.assertCountEqual([a.url for a in articles],
                              [a.url for e in events for a in e.articles])
        return events

    def test_named_first_party_apps_do_not_inherit_device_inventory(self):
        for name in ('Readiness', 'Motion', 'Canvas'):
            with self.subTest(name=name):
                events = self.groups([
                    (f"Apple to introduce all-new '{name}' app tomorrow",
                     f"Apple plans to announce its new {name} app for Apple Watch. Apple Watch SE 3 is unavailable."),
                    (f"苹果拟为 Apple Watch 推出全新{name}应用", f"苹果将推出{name}应用。发布会将公布新手表。"),
                    ('Apple Watch SE 3 is unavailable', 'Apple online store shows the watch is out of stock.'),
                ])
                self.assertEqual(sorted(len(e.articles) for e in events), [1, 2])
                app = next(e for e in events if len(e.articles) == 2)
                self.assertEqual(app.category, 'software_systems')
                self.assertEqual(app.relevance_tier, 'strong')

    def test_firmware_owns_device_and_target_version_not_unreleased_status(self):
        for device in ('Beats 360', 'Beats Orbit', 'AirPods Pro 4'):
            with self.subTest(device=device):
                events = self.groups([
                    (f'Apple may launch {device} this month',
                     f'Apple today released firmware 4A203 for the upcoming {device}. AirPods Max previously received beta firmware.'),
                    (f'产品尚未发布，苹果已为 {device} 推送新固件',
                     f'苹果为 {device} 推送固件更新，版本号 4A203。iOS 27 发布在即。'),
                    (f'Apple releases firmware 4A204 for {device}', f'Apple released firmware 4A204 for {device}.'),
                    ('Apple releases firmware 4A203 for Beats Flex', 'Beats Flex received firmware 4A203.'),
                ])
                self.assertEqual(sorted(len(e.articles) for e in events), [1, 1, 2])
                self.assertTrue(all(e.category == 'software_systems' for e in events))
                self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_official_adapter_firmware_beats_event_and_accessory_background(self):
        for watt in (140, 96):
            events = self.groups([
                (f'Apple releases firmware update for {watt}W USB-C Power Adapter', 'Apple released firmware version 1.4.90.'),
                (f'iPhone 18 Pro 发布会前夕，苹果推送 {watt}W USB-C 适配器固件更新',
                 '苹果向适配器推送更新，从 v1.4.84 升级到 v1.4.90 版本。'),
            ])
            self.assertEqual(len(events), 1)
            self.assertEqual((events[0].category, events[0].relevance_tier), ('software_systems', 'strong'))

    def test_acquisition_object_not_future_device_use(self):
        for name in ('Sonera', 'Neurospan'):
            events = self.groups([
                ('Apple acquires brain imaging firm', f'Apple has bought {name}, a California company. Vision Pro may use its technology.'),
                (f'苹果收购传感技术初创公司{name} 或用于Apple Watch', f'苹果今年早些时候收购了{name}。'),
                ("Apple's latest acquisition concerns new technology", f'EU filings revealed today that Apple has acquired a company called {name}.'),
                ('Apple acquires another sensor company', 'Apple acquired Signalworks, a sensor startup.'),
            ])
            self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])

    def test_hardware_identifier_disclosure_is_not_patent_or_launch(self):
        events = self.groups([
            ("Apple adds 41 hardware identifiers ahead of its event", 'Apple added new identifiers for iPhones, iPads, Macs and watches to its backend.'),
            ("New product identifiers show up in Apple's backend, not release timing", 'Apple added 41 identifiers for multiple unreleased products.'),
            ('苹果 iPhone 新品名单再添悬念，第8个标识符现身', '苹果向后台新增41个硬件标识符，覆盖 iPhone、Mac、iPad 和 Apple Watch。'),
            ('苹果探索可拉伸显示屏，未来用于Apple Watch', '最新专利描述可拉伸显示屏，适用于iPhone和iPad。'),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_chip_disclosure_uses_device_not_os_release_or_old_chip(self):
        events = self.groups([
            ("Next Apple TV's chip revealed in code", 'New code points to A20 or A20 Pro instead of the previously expected A18 Pro.'),
            ('苹果 Apple TV 4K 曝光：升级 A20/Pro 芯片', '代码发现 AppleTV19,1，配备A20系列芯片。'),
            ('Apple TV may get Siri AI thanks to A20 or A20 Pro chip', 'A leaked identifier shows the new chip.'),
            ('Apple releases tvOS 28', 'Apple released its new software.'),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])

    def test_biometric_code_skepticism_is_same_disclosure(self):
        events = self.groups([
            ("iPhone Ultra Touch ID confirmed in iOS 28? Not so fast", 'References in iOS 28 beta may be legacy code, not proof.'),
            ('Code in iOS 28 seems to prove iPhone Ultra uses Touch ID', 'The code refers to Touch ID.'),
            ('苹果 iOS 28 代码实锤折叠iPhone采用触控ID？先别急', '这可能只是遗留代码，不足为证。'),
            ('Apple releases iOS 28 beta', 'Apple has released a new beta.'),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_actual_production_report_not_target_and_preserves_period(self):
        events = self.groups([
            ('TrendForce: Apple produced 53 million iPhones in Q3', 'Apple smartphone production reached 53 million in Q3 2027, a 20% share.'),
            ('集邦报告2027Q3全球手机产量：三星23%、苹果20%', '集邦咨询报告2027年第三季度生产数据。苹果产量5300万台，同比增长。'),
            ('TrendForce predicts iPhone production', 'TrendForce expects Apple to produce 53 million iPhones in Q3 2027.'),
            ('TrendForce: Apple produced 53 million iPhones in Q4', 'Production reached 53 million in Q4 2027.'),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 1, 2])

    def test_device_safety_regulation_not_existing_os_feature(self):
        events = self.groups([
            ("Apple faces new UK rules over nude images on children's iPhones", 'The UK intends legislation requiring Apple and Google to prevent children viewing nude images on devices.'),
            ('UK repeats demands for child safety features Apple already made', 'The UK government plans legislation for device-level child protection.'),
            ('英国拟推动 iOS 安卓系统层面增强未成年人安全保护', '英国要求苹果谷歌阻止儿童拍摄分享裸露图片。'),
            ('Apple adds child safety features to iOS 28', 'Apple announced an updated parental control feature.'),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))

    def test_third_party_app_version_cannot_join_os_release(self):
        for name in ('微信', '星河'):
            events = self.groups([
                (f'{name} iOS版8.0.78正式版发布', f'{name}更新修复已知问题。苹果iOS 26.6.2也已发布。'),
                ('Apple releases iOS 26.6.2', 'Apple released an update fixing cellular downloads.'),
            ])
            self.assertEqual(len(events), 2)
            self.assertEqual(next(e for e in events if name in e.title).relevance_tier, 'weak')

    def test_editorial_titles_do_not_borrow_new_action_from_body(self):
        for title in ('Seven Apple TV settings can limit tracking without breaking streaming',
                      'Apple Event Tomorrow: iPhone 18 Pro Cheat Sheet'):
            event = self.groups([(title, 'Apple announced new software and hardware today.')])[0]
            self.assertEqual(event.relevance_tier, 'weak', title)

    def test_authority_requires_bound_owner_current_action_and_value(self):
        from apple_news_core.primary_action import owned_primary_action
        for title, lead in (
            ('apple rival microsoft acquired sensorworks', 'Microsoft acquired Sensorworks, while Apple watches.'),
            ('apple mentions that microsoft acquired sensorworks', 'Apple discusses the deal.'),
            ('apple considers buying sensorworks', 'Apple has not acquired Sensorworks.'),
            ('apple may launch beats orbit', 'Apple releases iOS 28.1.2. Sony headphones received firmware 4A203.'),
            ('apple releases firmware update for beats orbit', 'Apple released iOS 28.1.2. Beats Flex received firmware 4A203.'),
            ('uk child safety rules for apple: a retrospective', 'The UK proposed legislation in 2021.'),
            ('critics reject uk child safety demands for apple devices', 'A campaign group criticizes the existing legislation.'),
        ):
            with self.subTest(title=title):
                self.assertIsNone(owned_primary_action(title.lower(), lead.lower(), ''))

    def test_distinct_catalog_batches_do_not_merge(self):
        events = self.groups([
            ('Apple adds 37 hardware identifiers to backend', 'Apple added new identifiers today.'),
            ('Apple adds 42 hardware identifiers to backend', 'Apple added new identifiers today.'),
        ])
        self.assertEqual(len(events), 2)

    def test_initial_content_reviews_keep_existing_admission(self):
        event = self.groups([("Silo season 3 hailed as best season yet in first reviews",
                              'Silo returns this week on Apple TV, and the first reviews of season 3 are now available.')])[0]
        self.assertNotEqual(event.relevance_tier, 'weak')

    def test_review_return_to_service_owns_same_work_only(self):
        for name, season in (('Slow Horses', 6), ('Silo', 3)):
            with self.subTest(name=name):
                event = self.groups([
                    (f'{name} season {season} hailed as best yet in first reviews',
                     f'{name} returns next week to Apple TV, and early reviews say season {season} is the best yet.'),
                ])[0]
                self.assertNotEqual(event.relevance_tier, 'weak')
        for lead in (
            'Dark returns next week to Netflix. Silo returns to Apple TV.',
            'Dark returns to Netflix, compared to Silo returning to Apple TV.',
        ):
            with self.subTest(lead=lead):
                event = self.groups([('Dark season 3 first reviews arrive', lead)])[0]
                self.assertEqual(event.relevance_tier, 'weak')

    def test_current_chip_evidence_not_prior_chip_in_lead(self):
        events = self.groups([
            ('New Apple TV will be more powerful, per code leak',
             'The code points to a more powerful chip. Originally it was rumored to use A18 Pro. We discovered its identifier implies A20 or A20 Pro.'),
            ('Next Apple TV chip leaked', 'The Apple TV will use A20 or A20 Pro according to new code.'),
        ])
        self.assertEqual(len(events), 1)

    def test_background_seed_requires_compatible_action_domain(self):
        from apple_news_core.event_reconciler import reconcile_articles
        pairs = [
            ('苹果探索可拉伸显示屏，用于 Apple Watch', '苹果最新专利显示可拉伸屏用于多款设备。'),
            ('Apple Watch SE 3 suddenly unavailable', 'The Apple online store is out of stock ahead of the event.'),
            ("Apple introduces a new 'Motion' app", 'Apple Watch will support the new app.'),
        ]
        articles = [article_for(self.m, t, s, source=str(i)) for i, (t, s) in enumerate(pairs)]
        groups = reconcile_articles(articles, profile_for=self.m.article_reconciliation_profile,
                                    initial_groups=[articles])
        self.assertEqual(len(groups), 3)

    def test_cadillac_current_factory_support_not_old_policy(self):
        events = self.groups([
            ("The Cadillac Lyriq EV is the first crack in GM's CarPlay ban",
             'GM first announced the ban in 2023. The configurator for 2027 models shows Lyriq still supports CarPlay.'),
            ('2027 款凯迪拉克 Lyriq 支持 CarPlay，禁令首个例外', '凯迪拉克2027款配置器显示标配CarPlay。'),
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, 'ecosystem')

    def test_firmware_primary_fact_survives_os_background_filter(self):
        for name in ('Beats 360', 'Beats Orbit'):
            title = f'产品尚未发布，苹果已为 {name} 耳机推送新固件'
            summary = f'苹果提前为未发布的 {name} 头戴耳机推送固件，爆料显示这款耳机支持主动降噪，是苹果首款 IPX4 防汗防水头戴耳机，新品发布临近。'
            fact = f'除了 iOS / iPadOS 28.1.2 正式版更新之外，苹果同时还为其即将推出的 {name} 耳机推送固件更新（版本号 5B204）。'
            result = self.m.filter_key_facts_for_primary_topic(title, summary, [fact])
            self.assertIn(fact, result)

    def test_official_adapter_firmware_with_inline_store_link(self):
        pairs = [
            ('Apple releases firmware for 96W USB-C Power Adapter', 'Apple released firmware version 1.5.91 for the adapter.'),
            ('发布会前夕，苹果推送 96W USB-C 适配器固件更新',
             '苹果向96W USB-C 电源适配器（点此前往苹果官网选购，售价729元）推送固件更新，从 v1.5.84 升级到 v1.5.91。'),
        ]
        events = self.groups(pairs)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, 'software_systems')

    def test_app_release_does_not_carry_os_release_key(self):
        events = self.groups([
            ('星河 iOS 版 8.0.78 最新官方正式版下载发布，解决了一些已知问题',
             '星河 iOS 版 8.0.78 最新官方正式版下载发布'),
            ('Apple releases iOS 28.1.2', 'Apple released iOS 28.1.2.'),
        ])
        self.assertEqual(len(events), 2)
        self.assertEqual(next(e for e in events if '星河' in e.title).relevance_tier, 'weak')

    def test_independent_owner_cannot_borrow_apple_app_predicate(self):
        events = self.groups([
            ('Acme launches Canvas app while Apple launches Motion app', 'Acme released Canvas. Apple separately released Motion.'),
            ('Apple launches Canvas app', 'Apple released its Canvas app.'),
        ])
        self.assertEqual(len(events), 2)
        article = article_for(self.m, 'Acme launches Canvas app while Apple launches Motion app', 'Acme released Canvas. Apple released Motion.')
        self.assertFalse(self.m.article_reconciliation_profile(article).primary_action_owned)

    def test_adapter_manufacturer_owns_firmware_not_compatible_laptop(self):
        events = self.groups([
            ('Anker releases firmware for 96W USB-C adapter for Apple laptops', 'Anker released firmware version 1.5.91 for its own adapter, which supports Apple laptops.'),
            ('Apple releases firmware for 96W USB-C adapter', 'Apple released firmware version 1.5.91 for its own adapter.'),
        ])
        self.assertEqual(len(events), 2)
        self.assertEqual(next(e for e in events if 'Anker' in e.title).relevance_tier, 'weak')

    def test_unknown_firmware_version_never_borrows_other_assertion(self):
        for lead in (
            'The Beats update has no disclosed version. Sony released firmware 4A203 for its headphones.',
            'Apple releases firmware for Beats Orbit, while iOS is updated to 28.1.2.',
        ):
            article = article_for(self.m, 'Apple releases firmware update for Beats Orbit', lead)
            self.assertFalse(self.m.article_reconciliation_profile(article).primary_action_owned)
        events = self.groups([
            ('Apple releases firmware update for Beats Orbit', 'The update has no disclosed version. Sony released firmware 4A203.'),
            ('Apple releases firmware 4A203 for Beats Orbit', 'Apple released firmware 4A203 for Beats Orbit.'),
        ])
        self.assertEqual(len(events), 2)

    def test_production_product_and_period_are_owned_by_measured_subject(self):
        events = self.groups([
            ('TrendForce: Apple produced 53 million iPhones in Q3', 'Samsung produced 60 million phones in Q2 2027. Apple produced 53 million iPhones in Q3 2027.'),
            ('TrendForce: Apple produced 53 million iPhones in Q2 2027', 'Apple produced 53 million iPhones in Q2 2027.'),
            ('TrendForce: Apple produced 53 million iPads in Q3 2027', 'Apple produced 53 million iPads in Q3 2027.'),
        ])
        self.assertEqual(len(events), 3)

    def test_acquisition_proposal_does_not_use_old_completed_buyer_action(self):
        events = self.groups([
            ('Apple considers acquisition of Neurospan', 'Apple acquired Sonera in 2024. No deal with Neurospan has been completed.'),
            ('Apple acquired Sonera', 'Apple acquired Sonera in 2024.'),
        ])
        self.assertEqual(len(events), 2)

    def test_named_app_versions_are_distinct_release_actions(self):
        events = self.groups([
            ('Apple releases Canvas app version 1.0', 'Apple released Canvas version 1.0 today.'),
            ('Apple releases Canvas app version 2.0', 'Apple released Canvas version 2.0 today.'),
        ])
        self.assertEqual(len(events), 2)

    def test_review_service_owns_named_work_not_competitor_background(self):
        event = self.groups([('Dark season 3 hailed as best season yet in first reviews',
                              'Netflix released Dark season 3 for early reviews. It competes with Silo on Apple TV.')])[0]
        self.assertEqual(event.relevance_tier, 'weak')
        events = self.groups([
            ('Silo season 3 hailed as best season yet in first reviews', 'Silo returns this week on Apple TV, and first reviews are available.'),
            ('Apple TV 剧集 Silo 第三季首批影评出炉', 'Apple TV 剧集 Silo 第三季首批影评现已公布。'),
        ])
        self.assertEqual(len(events), 1)

    def test_commissioned_apple_hardware_keeps_existing_admission(self):
        for title, lead in (
            ('Apple commissions Foxconn to manufacture new 96W USB-C adapter', 'Apple designed the adapter and commissioned Foxconn to manufacture it for Apple.'),
            ('Foxconn begins production of Apple-designed smart glasses', 'Apple commissioned Foxconn to manufacture its new glasses. Foxconn began mass production under the Apple contract.'),
        ):
            self.assertNotEqual(self.groups([(title, lead)])[0].relevance_tier, 'weak')

    def assert_report_preserved(self, title, lead, facts):
        article = article_for(self.m, title, lead, facts=facts)
        events = self.m.cluster_articles([article])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 1)
        retained = events[0].articles[0]
        self.assertIs(retained, article)
        self.assertEqual((retained.title, retained.summary, retained.key_facts), (title, lead, facts))
        self.assertEqual(retained.projection_child_key, '')
        return events[0]

    def test_current_report_preserves_unassigned_facts(self):
        event = self.assert_report_preserved(
            'How Apple shaped the foldable iPhone, and what it may cost',
            'Bloomberg is out with a new report detailing Apple engineers developing the foldable iPhone in 2016.',
            ['Apple developed the hinge in 2016.', 'The prototype weighs 250 grams.', 'A supplier rejected the first display sample.'],
        )
        self.assertEqual(event.relevance_tier, 'strong')

    def test_history_with_multiple_prices_preserves_all_prices(self):
        self.assert_report_preserved(
            'Foldable iPhone development history revealed in new report',
            'Reuters shares a new report on Apple engineers developing the foldable iPhone in 2016.',
            ['Apple developed the hinge in 2016.', 'Apple recently discussed pricing at $2,199.',
             'Apple recently discussed pricing the larger configuration at $2,999.'],
        )

    def test_old_and_current_prices_in_same_sentence_are_not_rewritten(self):
        self.assert_report_preserved(
            'Apple planned for $1,999 iPhone Ultra, but component shortages intervened',
            'Bloomberg shares new details on Apple pricing the iPhone Ultra.',
            ['Apple originally targeted $1,999 but recently discussed pricing at $2,199.'],
        )

    def test_old_attributed_report_without_new_facts_stays_weak(self):
        event = self.assert_report_preserved(
            '苹果折叠屏iPhone研发历程回顾',
            '据2019年路透社报道，苹果工程师在2016年开始研发折叠屏iPhone。今天没有任何新增细节。',
            ['苹果工程师在2016年开始研发折叠屏iPhone。'],
        )
        self.assertEqual(event.relevance_tier, 'weak')

    def test_distinct_current_reports_do_not_share_product_history_identity(self):
        pairs = [
            ('Foldable iPhone hinge development history revealed in new report',
             'Bloomberg shares a new report detailing Apple engineers developing the hinge in 2016.'),
            ('Foldable iPhone battery development history revealed in new report',
             'Reuters shares a new report detailing Apple engineers developing the battery in 2024.'),
        ]
        events = self.groups(pairs)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.relevance_tier == 'strong' for e in events))
        self.assertEqual({a.title for e in events for a in e.articles}, {p[0] for p in pairs})

    def test_report_name_alone_does_not_promote_evergreen_history(self):
        event = self.groups([
            ('Why the foldable iPhone is a bad idea',
             'Bloomberg has covered Apple for decades. Apple engineers developed prototypes in 2017.'),
        ])[0]
        self.assertEqual(event.relevance_tier, 'weak')

    def test_facility_and_patent_category_follows_physical_object(self):
        for title, lead, kind in (
            ('Apple Riverside reopens after major redesign', 'The retail store has a redesigned Genius Bar, pickup area and step-free building entrance.', None),
            ('Apple sued for alleged authentication patent infringement', 'The complaint alleges iPhones infringe patents covering optical skin detection sensors, projected light and material properties.', 'legal_antitrust'),
        ):
            event = self.groups([(title, lead)])[0]
            self.assertEqual(event.category, 'hardware_products')
            if kind:
                self.assertEqual(event.event_kind, kind)
        event = self.groups([('Apple faces biometric privacy lawsuit', 'The complaint challenges biometric data retention and user consent policies.')])[0]
        self.assertEqual(event.category, 'software_systems')


if __name__ == '__main__':
    unittest.main()
