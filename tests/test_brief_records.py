import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/scripts/brief_records.py"


class BriefRecordsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("brief_records_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.BriefRecords = module.BriefRecords
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name) / "clauses.json"
        self.evidence = {
            "one": {"source": "来源一", "url": "https://example.com/one", "units": [
                {"unit_id": "hinge", "text": "The hinge collected less dust than model A."},
                {"unit_id": "status", "text": "The feature is not available yet."},
            ]},
            "two": {"source": "来源二", "url": "https://example.com/two", "units": [
                {"unit_id": "inside", "text": "Much less dust entered the body than model A."},
                {"unit_id": "same", "text": "The hinge collected less dust than model A."},
            ]},
        }
        self.book = self.BriefRecords(self.record, self.evidence)
        self.book.add_report("test", "硬件与产品", ["event-one"])

    def test_saved_distinct_propositions_are_assembled_without_rewriting(self):
        first = "测试发现，铰链积尘少于 A 型号。"
        second = "来源二称，进入机身内部的粉尘明显少于 A 型号。"
        self.book.add("test", first, [("one", "hinge")])
        self.book.add("test", second, [("two", "inside")])
        self.book.check("test")
        result = self.book.render()
        self.assertIn(first + second, result)
        self.assertIn("[来源一](https://example.com/one)", result)
        self.assertIn("[来源二](https://example.com/two)", result)
        self.assertIn("在指定时间窗口内，该分类下没有发现符合条件的新闻。", result)

    def test_merge_uses_saved_entries_and_keeps_the_selected_complete_wording(self):
        first = self.book.add("test", "铰链积尘少于 A 型号。", [("one", "hinge")])
        second = self.book.add("test", "与 A 型号相比，铰链积尘更少。", [("two", "same")])
        self.book.merge(first, second, "同一观察、部位、比较对象及程度。")
        self.book.check("test")
        result = self.book.render()
        self.assertIn("铰链积尘少于 A 型号。", result)
        self.assertNotIn("与 A 型号相比", result)
        self.assertIn("https://example.com/two", result)
        saved = json.loads(self.record.read_text())
        self.assertEqual(saved["clauses"][second]["text"], "与 A 型号相比，铰链积尘更少。")
        self.assertEqual(saved["clauses"][second]["merged_into"], first)
        with self.assertRaises(TypeError):
            self.book.merge(first, second, "不能提供另写的综合句。", text="综合句。")

    def test_invalid_reference_and_cross_report_merge_leave_saved_records_unchanged(self):
        first = self.book.add("test", "铰链积尘更少。", [("one", "hinge")])
        self.book.add_report("other", "软件与系统", ["event-two"])
        second = self.book.add("other", "功能尚未开放。", [("one", "status")])
        before = self.record.read_bytes()
        with self.assertRaises(ValueError):
            self.book.merge(first, second, "不能跨报道合并。")
        with self.assertRaises(ValueError):
            self.book.add("test", "无依据。", [("one", "missing")])
        self.assertEqual(before, self.record.read_bytes())

    def test_omission_removes_only_its_links_and_keeps_the_reason(self):
        self.book.add("test", "铰链积尘更少。", [("one", "hinge")])
        omitted = self.book.add("test", "另一个未保留的观察。", [("two", "inside")])
        self.book.omit(omitted, "重新核对后不属于本报道的测量对象。")
        self.book.check("test")
        self.assertNotIn("https://example.com/two", self.book.render())
        saved = json.loads(self.record.read_text())
        self.assertIn("测量对象", saved["clauses"][omitted]["reason"])

    def test_wording_revision_invalidates_check_and_retains_prior_wording(self):
        clause = self.book.add("test", "灰尘更少。", [("one", "hinge")])
        self.book.check("test")
        self.book.revise(clause, "铰链积尘少于 A 型号。", "补明原文的部位与比较对象。")
        with self.assertRaises(ValueError):
            self.book.render()
        self.book.check("test")
        saved = json.loads(self.record.read_text())
        self.assertEqual(saved["clauses"][clause]["revisions"][0]["text"], "灰尘更少。")
        self.assertIn("铰链积尘少于 A 型号。", self.book.render())

    def test_reload_and_write_use_the_same_authoritative_clauses(self):
        self.book.add("test", "铰链积尘少于 A 型号。", [("one", "hinge")])
        self.book.check("test")
        loaded = self.BriefRecords(self.record, self.evidence)
        output = Path(self.temp.name) / "brief.md"
        loaded.write(output)
        self.assertEqual(output.read_text(), self.book.render())

    def test_repeated_publisher_urls_are_not_collapsed(self):
        self.evidence["two"]["source"] = "来源一"
        self.book.add("test", "铰链积尘更少。", [("one", "hinge")])
        self.book.add("test", "机身内部进灰明显更少。", [("two", "inside")])
        self.book.check("test")
        result = self.book.render()
        self.assertEqual(result.count("[来源一]"), 2)

    def test_boundary_correction_moves_wording_and_links_without_rewriting(self):
        clause = self.book.add("test", "功能尚未开放。", [("one", "status")])
        self.book.add_report("software", "软件与系统")
        self.book.check("test")
        self.book.move(clause, "software")
        with self.assertRaises(ValueError):
            self.book.render()
        self.book.check("test")
        self.book.check("software")
        software, hardware = self.book.render().split("**硬件与产品**")
        self.assertIn("功能尚未开放。", software)
        self.assertNotIn("https://example.com/one", hardware)

    def test_render_rejects_references_from_changed_source_evidence(self):
        self.book.add("test", "功能尚未开放。", [("one", "status")])
        self.book.check("test")
        self.evidence["one"]["units"][1]["text"] = "The feature is available now."
        with self.assertRaises(ValueError):
            self.BriefRecords(self.record, self.evidence).render()


if __name__ == "__main__":
    unittest.main()
