"""A carrier's current activation service must not inherit a recap's status."""
from pathlib import Path
import json
import unittest

from test_relevance_rules import load_module


class CarrierServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.evidence = json.loads((Path(__file__).parent /
            'fixtures/20261024_carrier_service.json').read_text())

    def test_current_operator_service_owns_its_column_despite_later_recap(self):
        e = self.evidence
        facts = [u['text'] for u in e['units']]
        tier, _, category = self.m.source_text_outcome(e['title'], e['raw_lead'], facts, e['source'])
        self.assertEqual((tier, category), ('strong', 'software_systems'))

    def test_current_deployment_preserves_operator_and_venue(self):
        from apple_news_core.event_identity import source_retail_program_frame as frame
        title = '北方通信：已在苹果直营店安排工作人员，协助 iPhone Duo 购机用户现场开通 eSIM'
        body = '北方通信已在苹果直营店安排工作人员，协助用户现场开通 eSIM。'
        current = frame(title, body)
        self.assertIsNotNone(current)
        self.assertEqual(current.action, 'retail-customer-activation-service')
        self.assertEqual(current.category, 'software_systems')
        self.assertIsNotNone(frame(title, body.replace('用户现场', 'iPhone Duo 购机用户现场')))
        for other in ('南方通信',):
            changed = frame(title.replace('北方通信', other), body.replace('北方通信', other))
            self.assertIsNotNone(changed)
            self.assertNotEqual(current.subject, changed.subject)
        for wrong in (
            body.replace('北方通信', '南方通信'),
            body.replace('已在', '计划在'),
            body.replace('已在', '去年在'),
            body.replace('安排', '未安排'),
            body.replace('苹果直营店', '苹果直营店附近的咖啡店'),
            body.replace('苹果直营店', '华为门店'),
            body.replace('用户现场开通', 'iPad 用户现场开通'),
            body.replace('用户现场开通', 'iPhone 18 用户现场开通'),
            body.replace('用户现场开通', '用户了解无法开通'),
            '北方通信已在苹果直营店安排工作人员。南方通信协助用户现场开通 eSIM。',
        ):
            with self.subTest(body=wrong):
                self.assertIsNone(frame(title, wrong))


if __name__ == '__main__':
    unittest.main()
