"""Current operating actions own eligibility and category before host devices."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

class SourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads((Path(__file__).parent/'fixtures/20261024_source_boundaries.json').read_text())
        cls.sources = {s.name:s for s in cls.m.build_sources(datetime(2026,10,24,tzinfo=timezone.utc))}
    source_articles = prior.PureJsonBatchTests.source_articles
    cluster_sources = prior.PureJsonBatchTests.cluster_sources

    def test_owned_current_operations_keep_their_category(self):
        software=['5c68a0775915c69294e8241d','f881c2f11dcf9a4bda4d1d0b','a34ceb9e3fe72aa1757291ea','59b12092f52e49b7067dee18','42f1cf18e89e9f82378bd33b','cafb5a0d9d762399fc2d0900','11dff28766dda8f755085310','68de0620336efc03216b4484']
        hardware=['47b352918fe28d4293e8a082','2113095e16eeb783cbbf961a','67ffcc48853825e02a9d8f26']
        for id in software+hardware:
            with self.subTest(id=id):
                events,_ = self.cluster_sources(id)
                self.assertTrue(any(e.relevance_tier in {'strong','ecosystem'} for e in events))
                self.assertEqual({e.category for e in events},{'software_systems' if id in software else 'hardware_products'})

    def test_same_capability_reports_merge_without_other_features(self):
        a,b,c='a34ceb9e3fe72aa1757291ea','59b12092f52e49b7067dee18','5c68a0775915c69294e8241d'
        events,_=self.cluster_sources(a,b,c)
        groups=[{a.evidence.article_id for a in e.articles} for e in events]
        self.assertIn({a,b},groups)
        self.assertIn({c},groups)

    def test_app_accessory_and_episode_are_not_first_party_actions(self):
        for id in ['9adf85926c5676e4abe2f4c7','8ec2c5b47cf1f7955aec490c','47d287542e650911c1d3682f']:
            with self.subTest(id=id):
                title,lead,facts=self.rows[id]['recorded_extraction']
                self.assertEqual(self.m.source_text_outcome(title,lead,facts,self.rows[id]['evidence']['source'])[0],'weak')

    def test_current_document_publication_is_not_a_tutorial(self):
        events,_=self.cluster_sources('4e7bffb48531c58bb5957ab5')
        self.assertTrue(events)
        self.assertTrue(all(e.relevance_tier=='strong' for e in events))

    def test_application_release_channel_does_not_change_its_host_system(self):
        events, _ = self.cluster_sources('d48d2a927ed8be6f5f195484')
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('weak', 'software_systems')])
        for title, lead in (
            ('Northstar browser adds a slower release channel on macOS',
             'Northstar will offer its browser enterprise customers a slower feature update schedule on macOS. The browser will continue receiving security fixes.'),
            ('第三方浏览器为 macOS 企业用户提供延长更新周期',
             '软件厂商宣布其浏览器的功能版本改为每季度发布，安全更新仍正常提供。')):
            with self.subTest(title=title):
                self.assertEqual(self.m.source_text_outcome(title, lead, [lead], 'cnBeta')[0], 'weak')

    def test_first_party_release_evidence_survives_legacy_promotion_removal(self):
        for evidence_id in ('594a7a360bf243daa98fd263', 'a11f84142f7ed2e29cd3705a',
                            'b22edbf07f312a2180834adf'):
            with self.subTest(evidence_id=evidence_id):
                events, _ = self.cluster_sources(evidence_id)
                self.assertTrue(events)
                self.assertTrue(all((e.relevance_tier, e.category) == ('strong', 'software_systems')
                                    for e in events))

    def test_first_party_capability_requires_its_own_current_assertion(self):
        for title, lead in (
            ('Siri AI can pull battery data from third-party apps',
             'Apple denies Siri AI can pull battery data from third-party apps.'),
            ('Siri AI can pull battery data from third-party apps',
             'Siri AI cannot pull battery data from third-party apps in the current beta.'),
            ('Siri AI can access app data',
             "Siri AI can't access app data in the current beta."),
            ('用户反馈苹果 macOS 27 大幅提升流畅度',
             '这是去年用户的旧反馈，本次没有新增进展。'),
            ('Siri AI could pull data from apps',
             'Users hope Siri AI could pull data from apps in a future update.'),
            ('macOS 27 gets a new browser channel',
             'Northstar introduces a new browser update channel for macOS 27.'),
            ('Microsoft introduces a browser channel on macOS',
             'macOS 27 brings Apple Intelligence to Apple apps. Microsoft changes only its browser update schedule.')):
            with self.subTest(title=title):
                self.assertEqual(self.m.source_text_outcome(title, lead, [lead], 'IT之家')[0], 'weak')
        title = 'Siri AI can pull battery data if developers opt in'
        lead = 'Siri AI can pull battery data if developers opt in to the current API.'
        self.assertEqual(self.m.source_text_outcome(title, lead, [lead], 'IT之家')[0], 'strong')
        title = 'macOS 27 improves window responsiveness'
        lead = 'Last year users reported slow windows. macOS 27 improves window responsiveness in current testing.'
        self.assertEqual(self.m.source_text_outcome(title, lead, [lead], 'IT之家')[0], 'strong')
        title = 'Siri AI can pull battery data from third-party apps'
        lead = ('Last year Apple denied that Siri AI could pull app data. '
                'Siri AI can pull battery data from approved apps in the current developer beta.')
        self.assertEqual(self.m.source_text_outcome(title, lead, [lead], 'IT之家')[0], 'strong')
        for lead in (
            'Siri AI can pull battery data from approved apps, but Northstar cannot access these app records.',
            'Siri AI can pull battery data from approved apps, but cannot read health data.',
            'Siri AI can pull battery data from approved apps and Northstar cannot access these app records.',
            'Siri AI can pull battery data from approved apps, Northstar cannot access these app records.',
            'Siri AI can pull battery data from approved apps and cannot read health data.'):
            with self.subTest(lead=lead):
                self.assertEqual(self.m.source_text_outcome(title, lead, [lead], 'IT之家')[0], 'strong')

    def test_first_party_operator_owns_the_repair_or_builtin_trial(self):
        from apple_news_core.event_identity import is_direct_first_party_feature_change as owned
        for title, lead in (
            ("Apple fixes bug where Siri doesn't understand requests",
             'Apple released iOS 27.2 to fix a bug where Siri fails to understand requests.'),
            ('苹果修复 Siri 无法理解请求的问题',
             '苹果已经修复 Siri 无法理解请求的问题。用户此前对此表达不满。'),
            ("Apple fixes bug where Siri doesn't understand requests",
             'Apple has fixed a bug where Siri could not understand requests.'),
            ('Apple fixes Siri request handling',
             'Apple has fixed Siri request handling, which users first reported last year.'),
            ('Siri AI is hiding a new way to access Writing Tools',
             'Apple is testing a new way to access its built-in Writing Tools after users complained about access last year.'),
            ('Siri AI is hiding a new way to access Writing Tools',
             'Apple is testing a new way to access its built-in Writing Tools on macOS 27.')):
            with self.subTest(title=title):
                self.assertTrue(owned(title, lead))
                self.assertEqual(self.m.source_text_outcome(title, lead, (lead,), '9to5Mac')[0], 'strong')
        for title, lead in (
            ('Apple fixes Siri request handling', 'Apple has not fixed Siri request handling.'),
            ('Apple fixes Siri request handling', 'Last year Apple fixed Siri request handling.'),
            ('Apple fixes Siri request handling', 'Apple fixed Siri request handling last year.'),
            ('Users hope Apple fixes Siri request handling', 'Users hope Apple will fix Siri request handling.'),
            ('Apple fixes Siri request handling', 'Apple denies it has fixed Siri request handling.'),
            ('Apple fixes Siri request handling', 'Apple fixed Chrome request handling on macOS.'),
            ('Northstar fixes requests on macOS', 'Apple is testing its built-in Writing Tools. Northstar fixed its own browser.'),
            ('Siri AI is hiding a new way to access Writing Tools',
             'Apple is testing a new way to access a third-party writing app on macOS.'),
            ('Siri AI is hiding a new way to access Writing Tools',
             'Apple is testing its built-in camera while Writing Tools remain unchanged.'),
            ('Siri AI is hiding a new way to access Writing Tools',
             'Users are testing a new way to access the built-in Writing Tools on macOS.'),
            ('How to fix Siri request handling yourself',
             'This tutorial explains how users can restart Siri. Apple released iOS 27.2 last week.')):
            with self.subTest(title=title, lead=lead):
                self.assertFalse(owned(title, lead))

    def test_independent_storage_modification_is_not_an_apple_release(self):
        events, _ = self.cluster_sources('cbedd0c7ca5e12309e4c8178')
        self.assertTrue(events)
        self.assertTrue(all((e.relevance_tier, e.category) == ('weak', 'hardware_products')
                            for e in events))

    def test_physical_tools_do_not_establish_a_software_utility(self):
        events, _ = self.cluster_sources('2f5605f3bc08738f6ecc1cd8')
        self.assertEqual([(e.relevance_tier, e.category) for e in events],
                         [('weak', 'hardware_products')])
        from apple_news_core.event_identity import source_independent_software_frame as frame
        for title, lead in (
            ('第三方维修人员为 iPhone 更换闪存',
             '维修人员使用第三方工具打磨旧芯片，再安装新存储芯片。'),
            ('Independent technician changes iPhone storage',
             'The technician used a third-party tool to remove and replace the flash chip.')):
            with self.subTest(title=title):
                self.assertIsNone(frame(title, lead, (lead,)))
        title = 'Cedar: a command-line tool for macOS'
        lead = 'Cedar is a new open-source utility that removes unused local files on macOS.'
        self.assertEqual(frame(title, lead, (lead,)).category, 'software_systems')

    def test_customization_binds_the_modifier_to_its_physical_target(self):
        from apple_news_core.event_identity import source_device_customization_frame as frame
        for title in ('第三方维修师傅已成功将 iPad 12 的存储扩容至 1TB',
                      'Repair technician upgrades an iPhone 23 to 1TB storage'):
            with self.subTest(title=title):
                result = frame(title, title + '.')
                self.assertIsNotNone(result)
                self.assertEqual((result.tier, result.category), ('weak', 'hardware_products'))
        for title, lead in (
            ('苹果发布 iPhone 23 后，第三方维修师傅已将该机的存储扩容至 2TB',
             '苹果上周发布 iPhone 23，维修师傅今日自行完成改装。'),
            ('iPhone 23 开售，维修师傅已将存储扩容至 2TB',
             '苹果此前发布的 iPhone 23 今日开售，维修师傅今日完成存储改装。')):
            with self.subTest(title=title):
                self.assertEqual(frame(title, lead).tier, 'weak')
                self.assertEqual(self.m.source_text_outcome(title, lead, (lead,), 'IT之家')[0], 'weak')
        title = '苹果 iPhone 23 刚开售，第三方维修师傅已将该机的存储扩容至 2TB'
        for lead in (
            '苹果官方维修团队表示，第三方维修师傅已自行扩容存储，这不是官方维修项目。',
            '苹果官方维修团队为 iPad 提供电池更换，第三方维修师傅则自行将 iPhone 23 存储扩容至 2TB。',
            '这名师傅并非苹果授权维修人员，他自行将 iPhone 23 的存储扩容至 2TB。'):
            with self.subTest(lead=lead):
                self.assertEqual(frame(title, lead).tier, 'weak')
                self.assertEqual(self.m.source_text_outcome(title, lead, (lead,), 'IT之家')[0], 'weak')
        for title in ('苹果为 iPhone 23 新增存储配置，第三方维修师傅进行测试',
                      '第三方维修师傅未能将 iPhone 23 的存储扩容',
                      '第三方维修师傅计划将 iPhone 23 的存储扩容',
                      '第三方维修师傅去年将 iPhone 23 的存储扩容',
                      '第三方维修师傅称苹果为 iPhone 23 新增存储配置',
                      '第三方维修师傅将安卓手机的存储扩容，旁边摆着 iPhone 23',
                      '第三方维修师傅拆解 iPhone 23，发现苹果升级存储',
                      '第三方维修师傅已将 iPhone 23 的存储管理软件更换',
                      '传闻维修师傅已将 iPhone 23 的存储扩容，苹果否认',
                      '苹果维修人员已将 iPhone 23 的闪存更换为新模块',
                      '下周维修师傅将 iPhone 23 的存储扩容',
                      '如果维修师傅将 iPhone 23 的存储扩容，维修成本就会上升',
                      '维修师傅已将 iPhone 23 旁边的安卓手机存储扩容',
                      'Independent reviewer measures iPhone 23 storage performance'):
            with self.subTest(title=title):
                self.assertIsNone(frame(title, title + '.'))

    def test_modification_cannot_override_an_official_action_or_its_date(self):
        from apple_news_core.event_identity import source_device_customization_frame as frame
        title = '苹果发布 iPhone 23 官方存储升级方案：维修师傅将 iPhone 23 的闪存更换为新模块'
        lead = '苹果今日发布 iPhone 23 官方存储升级方案，由维修人员按官方流程更换闪存模块。'
        self.assertIsNone(frame(title, lead))
        self.assertEqual(self.m.source_text_outcome(title, lead, (lead,), 'IT之家')[0], 'strong')
        for title, lead in (
            ('苹果发布 iPhone 23 官方存储升级方案，维修师傅已将 iPhone 23 的闪存更换为新模块',
             '苹果今日发布 iPhone 23 官方存储升级方案，苹果授权维修师傅已按照该方案完成闪存更换。'),
            ('苹果发布 iPhone 23 官方存储升级方案，维修人员已将该机的存储扩容',
             '苹果官方团队已为 iPhone 23 提供存储升级方案并完成验证。')):
            with self.subTest(title=title):
                self.assertIsNone(frame(title, lead))
                self.assertEqual(self.m.source_text_outcome(title, lead, (lead,), 'IT之家')[0], 'strong')
        self.assertIsNone(frame('维修师傅已将 iPhone 23 的存储扩容',
                                '苹果否认该维修师傅已成功扩容的说法。'))
        self.assertIsNone(frame('维修师傅已将 iPhone 23 的存储扩容',
                                '这段视频拍摄于去年，本次仅重新上传，没有新增进展。'))

    def test_capability_ownership_and_stage_do_not_follow_a_shared_host(self):
        from apple_news_core.event_identity import source_software_capability_frame as frame
        negatives = [
            ('iPhone 19 Control Center wishlist', 'Users hope Apple will add a new tap shortcut to open Control Center.'),
            ('iPhone 19 Control Center trick revisited', 'Last year Apple introduced a new tap shortcut to open Control Center.'),
            ('Widget app adds a Control Center button on iPhone 19', 'A developer added a new button to its own app.'),
            ('iPhone 19 new Control Center trick is not supported', 'Apple says it does not support tapping the icon to open Control Center.'),
        ]
        for title,lead in negatives:
            with self.subTest(title=title):self.assertIsNone(frame(title,lead,()))
        owned=frame('iPhone 19 has a hidden Control Center shortcut',
            'iPhone 19 introduces a new shortcut: users can tap the icon to open Control Center.',())
        self.assertEqual(owned.subject,'iphone-19:control-center:opening-input')
        self.assertEqual(owned.category,'software_systems')

    def test_independent_app_actions_do_not_borrow_first_party_surfaces(self):
        from apple_news_core.event_identity import source_software_capability_frame as frame
        cases=[('Widget app adds a new Control Center button on iPhone 19',
                'The independent Widget app has a new button: tap it to open Control Center. Apple has not changed iOS.'),
            ('New iPhone 19 app says Hello personally',
                'The third-party app greets you with a personalized message after setup.'),
            ('iPhone 19 has a new Control Center layout',
                'The new Control Center layout changes the volume slider. In the Notes app, tap the icon to open a saved note.')]
        for title,lead in cases:
            with self.subTest(title=title):self.assertIsNone(frame(title,lead,()))

    def test_different_issue_host_and_stage_remain_separate(self):
        pairs=[
            [('Apple acknowledges Safari crashes on launch','Apple is working on an issue in Safari that causes crashes when launching the app.'),
             ('Apple acknowledges Safari printing issues','Apple is working on an issue in Safari that prevents printing PDF files.')],
            [('iPhone 19微信已适配平板登录','微信客户端已经支持同时登录，可以显示左右分栏。'),
             ('iPad 12微信已适配平板登录','微信客户端已经支持同时登录，可以显示左右分栏。')],
            [('iPhone 19 has a hidden Control Center shortcut','iPhone 19 introduces a new shortcut: users can tap the icon to open Control Center.'),
             ('iPhone 19 hidden Control Center shortcut revealed','Apple will add a new shortcut: tap the icon to open Control Center.')]]
        for pair in pairs:
            with self.subTest(pair=pair):
                events=self.m.cluster_articles([article_for(self.m,title,lead) for title,lead in pair])
                self.assertEqual(len(events),2)

    def test_opening_operation_does_not_cross_a_new_subject_or_negation(self):
        from apple_news_core.event_identity import source_software_capability_frame as frame
        for bridge in (', while ', ', ', ' and '):
            self.assertIsNone(frame('Widget app adds a new Control Center button on iPhone 19',
                'Apple provides iPhone 19 devices to developers' + bridge + 'Widget adds a button to open Control Center.',()))
        self.assertIsNone(frame('iPhone 19 introduces a new Control Center button',
            'iPhone 19 introduces a new button that does not open Control Center.',()))
        current=frame('iPhone 19 has a hidden Control Center shortcut',
            'iPhone 19 introduces a new way to open Control Center.',())
        planned=frame('iPhone 19 hidden Control Center shortcut revealed',
            'Apple will add a new way to open Control Center on iPhone 19.',())
        self.assertNotEqual(current.action,planned.action)

    def test_reservation_eligibility_requires_its_own_model_and_change(self):
        from apple_news_core.event_identity import source_retail_operation_frame as frame
        title='中国联通开放 iPhone 19 现货预约购买，无需验证老用户身份'
        for body in ('中国联通已全面开放 Galaxy S30 现货预约购买，非老用户也可预约登记。',
                     '中国联通已全面开放 iPhone 19 现货预约购买，但仍然仅限老用户参加。',
                     '中国联通尚未开放 iPhone 19 现货预约购买，非老用户也不可预约登记。'):
            value=frame(title,body)
            self.assertTrue(value is None or value.action!='reservation-eligibility-expansion',body)
        value=frame(title,'中国联通已全面开放 iPhone 19 现货预约购买，非老用户也可预约登记。')
        self.assertEqual(value.action,'reservation-eligibility-expansion')

    def test_live_sources_share_the_same_concrete_software_action(self):
        groups = [
            ['65c23096250106de03f411be','0fbcd32f9e559eaaa4b59b98','2767020d3c5b14f096d6f9a6','a34ceb9e3fe72aa1757291ea','59b12092f52e49b7067dee18'],
            ['23130d1e8d89321692367bff','42f1cf18e89e9f82378bd33b'],
            ['b22edbf07f312a2180834adf','43adf1c57f432a3fe47b7ed2','948f7d595995a12ff7b8435f'],
        ]
        for ids in groups:
            with self.subTest(ids=ids):
                events,_=self.cluster_sources(*ids)
                self.assertEqual(len(events),1)
                self.assertEqual(events[0].category,'software_systems')
                self.assertEqual(len(events[0].articles),len(ids))

    def test_live_security_reports_are_software_and_keep_different_operations(self):
        ids=['711fb70d1386e301d90d8aa4','214d8249375fa280cd705493','450327134db26ea3bbfb2b87']
        events,_=self.cluster_sources(*ids)
        self.assertEqual(len(events),2)
        self.assertEqual({e.category for e in events},{'software_systems'})

    def test_live_app_login_is_not_a_device_release(self):
        events,_=self.cluster_sources('d639daedeca6279ffedb7475','8ec2c5b47cf1f7955aec490c','1c4ebd9a677fdf825eb9dd77')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].relevance_tier,'weak')
        self.assertEqual(events[0].category,'software_systems')

    def test_live_physical_store_closures_are_hardware(self):
        for id in ['4623c6a3f350d692ffa86827','3c0483628c8ca1a8492ede89','ac0645d4ccf322930bb81831']:
            with self.subTest(id=id):
                events,_=self.cluster_sources(id)
                self.assertEqual({e.category for e in events},{'hardware_products'})

    def test_separate_future_generations_keep_owned_facts(self):
        events,rows=self.cluster_sources('f53f6fb2cf6970967edb6356')
        self.assertEqual(len(events),1)
        self.assertNotIn('Duo 2',' '.join(rows[0]['must_include_facts']))
        self.assertTrue(any('Duo 2' in fact.text for fact in events[0].fact_plan.unprocessed))

    def test_revised_rc_needs_unique_current_ordinal(self):
        rows=[article_for(self.m,'Apple seeds updated watchOS 28.1 release candidate',
                'Apple released an updated version of the watchOS 28.1 release candidate, four days after the first RC became available.'),
              article_for(self.m,'Apple seeds watchOS 28.1 RC 2','Apple released watchOS 28.1 RC 2 today.'),
              article_for(self.m,'Apple seeds watchOS 28.1 RC 3','Apple released watchOS 28.1 RC 3 today.')]
        self.assertEqual(len(self.m.cluster_articles(rows)),3)
        self.assertEqual(len(self.m.cluster_articles(rows[:2])),1)

    def test_security_disclosures_keep_local_host_stage_and_path(self):
        from apple_news_core.event_identity import source_software_capability_frame as frame
        title='iPhone 19 Jailbreak Demonstration'
        for lead in ('An iPhone 18 Pro running iOS 30.1 was jailbroken by hacker team Acme. The iPhone 19 work is still in progress.',
                     'An iPhone 19 running iOS 31 may be jailbroken by hacker team Acme next year.',
                     'An iPhone 19 running iOS 31 was examined by security researcher Acme. No jailbreak was attempted.'):
            self.assertIsNone(frame(title,lead,()))
        lead='An iPhone 19 running iOS 31 has been jailbroken by hacker team Acme'
        self.assertEqual(frame(title,lead+'.',()),frame(title,lead+', as demonstrated today.',()))
        rows=[article_for(self.m,'iPhone 19 lock screen bypass reported',
            'An iPhone 19 running iOS 31 can unlock through '+path+'.') for path in ('Touch ID fingerprint input','Siri voice commands')]
        self.assertEqual(len(self.m.cluster_articles(rows)),2)

    def test_revised_rc_does_not_override_current_build_conflicts(self):
        title='Apple seeds updated watchOS 28.1 RC'
        lead='Apple released an updated watchOS 28.1 RC, build 25S100.'
        second=article_for(self.m,'Apple seeds watchOS 28.1 RC 2','Apple released watchOS 28.1 RC 2, build 25S200.')
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,title,lead),second])),2)
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,title,lead.replace('25S100','25S200')),second])),1)
        lead=lead[:-1]+', four days after the first RC.'
        self.assertEqual(len(self.m.cluster_articles([article_for(self.m,title,lead),second])),2)

    def test_received_device_fault_is_not_a_retail_discount(self):
        row=self.rows['695a08f775759a9dac56c0cf'];title,lead,facts=row['recorded_extraction']
        candidate=self.m.Candidate('快科技',row['evidence']['url'],title,lead)
        self.assertTrue(self.m.is_relevant_candidate(candidate,self.sources['快科技']))
        self.assertFalse(self.m.is_routine_retail_discount_story(title,title+' '+lead))
        events,_=self.cluster_sources('695a08f775759a9dac56c0cf')
        self.assertEqual(events[0].relevance_tier,'strong')
        self.assertEqual(events[0].category,'hardware_products')
        self.assertTrue(self.m.is_routine_retail_discount_story('iPhone 19 券后到手 5999 元',
            '商家限时发放优惠券，领券到手5999元。'))
        from apple_news_core.event_identity import source_current_report_frame
        dropped=source_current_report_frame('iPhone 19 screens cracked',
            'Users report iPhone 19 screens cracked at the hinge after dropping phones on concrete.',())
        self.assertTrue(dropped is None or dropped.action!='reported-screen-fracture')

    def test_current_fault_observation_and_download_instruction_keep_their_forms(self):
        events,_=self.cluster_sources('ef1ac4336525701b908e5460')
        self.assertEqual(events[0].relevance_tier,'strong')
        title,lead,facts=self.rows['404bbe91a32fbc42d63d4123']['recorded_extraction']
        self.assertEqual(self.m.source_text_outcome(title,lead,facts,'9to5Mac')[0],'weak')
