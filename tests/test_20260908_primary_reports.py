import unittest

from test_20260905_claim_ownership_boundaries import article_for, load_module


class PrimaryReports20260908(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def groups(self, pairs):
        return self.m.cluster_articles([
            article_for(self.m, title, lead, source=str(i))
            for i, (title, lead) in enumerate(pairs)
        ])

    def test_contracted_negation_does_not_take_positive_background(self):
        events = self.groups([
            ("Tim Cook Won't Appear in Apple's September Event Video", "Cook will remain chairman. Ternus will host the event."),
            ("库克不会在苹果秋季发布会视频中出现", "库克将继续担任董事会主席。"),
            ("Tim Cook will appear at Apple's September event", "Cook will participate."),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 2])

    def test_supplier_response_not_financial_or_negotiation_background(self):
        events = self.groups([
            ("长鑫科技回应与苹果合作：保持开放态度", "公司回应客户合作传闻，未确认具体客户。营收增长873.64%，苹果曾洽谈采购。"),
            ("CXMT responds to Apple partnership rumors", "The supplier says it is open to cooperation, without confirming a customer. Revenue surged last quarter."),
            ("长鑫总经理回应与苹果合作：已具备竞争能力", "公司保持开放态度，商业合作细节以公开披露为准。"),
            ("Apple negotiates memory procurement with CXMT", "Apple is negotiating new memory supply contracts."),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])
        self.assertTrue(all(e.category == "hardware_products" for e in events))

    def test_network_award_result_does_not_become_program_rights(self):
        events = self.groups([
            ("Apple TV leads Emmy wins with 20 awards", "At the 2026 Emmy Awards Apple earned 20 wins. Widows Bay earned eight awards and previously obtained global rights."),
            ("Apple TV wins 20 awards at the Emmys", "Widows Bay took eight prizes; Pluribus won four."),
            ("苹果 Apple TV 收获 20 项艾美奖", "苹果成为本轮获奖最多的平台。"),
            ("Apple TV acquires global rights to Widows Bay", "Apple announced a new licensing agreement."),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])

    def test_award_ceremonies_and_nominations_are_not_wins(self):
        pairs = [
            ("Apple TV wins 20 Emmy awards", "Apple won 20 awards."),
            ("Apple TV receives 20 Emmy nominations", "Apple received nominations."),
            ("Apple TV wins 20 Golden Globe awards", "Apple won 20 Golden Globes."),
        ]
        self.assertEqual(len(self.groups(pairs)), 3)

    def test_code_disclosure_owns_platform_component_not_release_background(self):
        camera = [
            ("Five New iPhone Camera Features Found in iOS 27 Code", "MacRumors forum member 'exampleuser' found new iOS 27 camera features in code."),
            ("苹果 iOS 27 暗藏五项相机功能", "网友 exampleuser 在论坛披露 iOS 27 代码中的相机功能，包括曝光与对焦辅助。"),
            ("Apple is packing more pro photography tools into iOS 27", "New iOS 27 beta code first spotted by exampleuser, a forum member, reveals advanced camera tools."),
        ]
        events = self.groups(camera)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "software_systems")
        independent = [
            ("Apple releases iOS 27 beta 8", "Apple released its latest developer beta."),
            ("iOS 27 Wallet code reveals new payment features", "Forum member 'exampleuser' found new Wallet code."),
            ("iOS 28 Camera code reveals new photography features", "Forum member 'exampleuser' found new Camera code."),
        ]
        self.assertEqual(len(self.groups(camera + independent)), 4)

    def test_proposal_is_not_a_completed_subscription_price_change(self):
        events = self.groups([
            ("Apple Plans to Squeeze More Revenue Out of App Store", "Apple is considering changes to developer membership fees, according to a new report."),
            ("苹果考虑提高 App Store 收入和利润率", "苹果正研究开发者会员收费方式。"),
            ("Apple raises App Store developer fees", "Apple announced a new membership fee."),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 2])

    def test_same_institution_quantified_production_report(self):
        events = self.groups([
            ("KeyBanc warns iPhone event could hit Apple shares", "KeyBanc expects Apple to build 80 million iPhones in fiscal 2026 Q4 and 2027 Q1."),
            ("Higher iPhone prices could hurt Apple", "According to KeyBanc, Apple will build 80 million iPhones across fiscal 2026 Q4 and 2027 Q1."),
            ("KeyBanc 预估苹果 iPhone 产量下降", "KeyBanc 预估苹果在 2026 财年第四季度至 2027 财年第一季度将生产 8000 万部 iPhone。"),
            ("Morgan Stanley predicts Apple iPhone production", "Morgan Stanley expects Apple to build 80 million iPhones in fiscal 2026 Q4 and 2027 Q1."),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 3])

    def test_current_cross_platform_device_interoperation(self):
        events = self.groups([
            ("华为鸿蒙星河互联升级，支持 Apple Watch 与 AirPods", "HarmonyOS 7 宣布互联升级，华为手机可接收 Apple Watch 消息提醒并查看 AirPods 电量。"),
            ("HarmonyOS 7 adds Apple Watch interoperability", "The platform now forwards notifications and calls between Huawei phones and Apple Watch."),
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].relevance_tier, "ecosystem")
        self.assertEqual(events[0].category, "software_systems")
        for title, lead in [
            ("星河互联 App 登陆 App Store", "HarmonyOS 7 尚未支持 Apple Watch 消息转发。"),
            ("HarmonyOS 7发布", "去年已支持 iPhone 文件互传，尚未支持 Apple Watch。"),
            ("华为新耳机兼容 iPhone", "第三方耳机可在 HarmonyOS 7 与 iPhone 之间切换蓝牙连接。"),
        ]:
            event = self.groups([(title, lead)])[0]
            self.assertEqual(event.relevance_tier, "weak", title)

    def test_supply_contract_is_not_price_negotiation(self):
        pairs = [
            ("苹果或签铠侠 NAND 长期协议", "苹果考虑三到五年的 NAND 供应合约。"),
            ("Apple may sign a long-term NAND supply agreement with Kioxia", "Apple is considering a multiyear NAND contract."),
            ("Apple negotiates lower NAND prices with Kioxia", "Apple is negotiating component prices."),
        ]
        events = self.groups(pairs)
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 2])
        self.assertTrue(all(e.relevance_tier != "weak" for e in events))

    def test_proposal_project_and_year_are_owned_boundaries(self):
        lead = "WebKit invites developers to submit proposals for browser interoperability. Microsoft is a project partner."
        events = self.groups([
            ("Apple invites developers to submit browser interoperability ideas for Interop 2027", lead),
            ("苹果公开征集 Interop 2027 提案", "WebKit 团队邀请开发者提交浏览器互操作性建议。微软参与合作。"),
            ("WebKit invites developers to submit browser interoperability ideas for Interop 2028", lead),
            ("Apple invites developers to submit browser interoperability ideas for WebReach 2027", lead),
        ])
        self.assertEqual(sorted(len(e.articles) for e in events), [1, 1, 2])
        self.assertTrue(all(e.relevance_tier == "strong" for e in events))

    def test_currency_quantity_cannot_become_a_product_year(self):
        from apple_news_core.event_reconciler import _evidence_measurements
        result = _evidence_measurements("苹果折叠 iPhone 售价2000美元", "The device costs $2027, with a launch planned in 2028.")
        self.assertNotIn("year:2000", result)
        self.assertNotIn("year:2027", result)
        self.assertIn("year:2028", result)
        formatted = _evidence_measurements("苹果设备售价20,000美元", "")
        self.assertIn("money:usd:20000", formatted)
        self.assertNotIn("money:usd:0", formatted)

    def test_same_forecast_amount_in_different_quarters_is_not_same_report(self):
        events = self.groups([
            ("KeyBanc predicts iPhone production", "KeyBanc expects Apple to build 80 million iPhones in 2027 Q1."),
            ("KeyBanc forecasts iPhone production", "KeyBanc expects Apple to build 80 million iPhones in 2027 Q4."),
        ])
        self.assertEqual(len(events), 2)

    def test_title_owned_hardware_category_does_not_need_launch_verb(self):
        event = self.groups([("约翰·特努斯在苹果面临的首项考验：如何卖出一部售价2000美元的折叠屏iPhone", "苹果将公布其首款折叠 iPhone，新设计已研发至少八年。")])[0]
        self.assertEqual(event.category, "hardware_products")

    def test_product_cost_category_is_not_management_background(self):
        title = "约翰·特努斯在苹果面临的首项考验：如何卖出一部售价2000美元的折叠屏iPhone"
        lead = "苹果公司负责硬件业务的约翰·特努斯将于周三公布其出任首席执行官后的首批新品，希望说服消费者接受折叠屏和超过2000美元的售价。这款全新设计已由苹果硬件部门研发至少八年。苹果需要让消费者接受涨价，以抵消供应链成本压力。"
        article = article_for(self.m, title, lead, facts=[
            lead,
            "工程师指出，十年前这种屏幕的制造成本将达到数千美元。如今耐用性和制造成本已有改善。",
        ])
        profile = self.m.article_reconciliation_profile(article)
        self.assertEqual(profile.category_hint, "hardware_products")


if __name__ == "__main__":
    unittest.main()
