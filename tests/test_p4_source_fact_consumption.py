"""Complete source units must reach the event fact contract with local origins."""

from dataclasses import replace
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


FIXTURE = Path(__file__).parent / "fixtures/p4_fact_input_sources.json"
REPLAY_FIXTURE = Path(__file__).parent / "fixtures/p4_fact_input_replay_sources.json"
OVERDELETE_FIXTURE = Path(__file__).parent / "fixtures/p4_fact_input_overdelete_sources.json"
SEMANTIC_FIXTURE = Path(__file__).parent / "fixtures/p4_fact_input_semantic_sources.json"


class SourceFactConsumptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.replay_rows = json.loads(REPLAY_FIXTURE.read_text(encoding="utf-8"))
        cls.overdelete_rows = json.loads(OVERDELETE_FIXTURE.read_text(encoding="utf-8"))
        cls.semantic_rows = json.loads(SEMANTIC_FIXTURE.read_text(encoding="utf-8"))
        cls.sources = {source.name: source for source in cls.m.build_sources(
            datetime(2026, 9, 24, tzinfo=timezone.utc))}

    def run_source(self, row):
        m = self.m
        # The fixture contains every natural body unit. Render only inert HTML
        # wrappers so both extraction and evidence capture run as in production.
        # A source-local quote introduction supplies the distinct description
        # that precedes the Wanda story body on its original page.
        description = row["units"][5]["text"] if "watch-the-trailer" in row["url"] else ""
        meta = (f'<meta property="og:description" content="{escape(description, quote=True)}">'
                if description else "")
        markup = (f"<html><head><title>{escape(row['title'])}</title>{meta}</head>"
                  "<body><article>" + "".join(
                      unit.get("markup") or f"<{unit['kind']}>{escape(unit['text'])}</{unit['kind']}>"
                      for unit in row["units"]) + "</article></body></html>")
        candidate = m.Candidate(row["source"], row["url"], row["discovery_title"],
                                row["discovery_lead"], row["published_utc"])
        source = self.sources[row["source"]]
        evidence = m.capture_article_evidence(source.name, row["url"], markup,
                                              candidate.title, candidate.summary)
        self.assertEqual(evidence.article_id, row["article_id"])
        self.assertEqual([(unit.kind, unit.text) for unit in evidence.units],
                         [(unit["kind"], unit["text"]) for unit in row["units"]])
        evidence = replace(evidence, content_form=m.title_led_identity(
            evidence.title, evidence.raw_lead).content_form)
        title, summary, facts, published, raw, published_source, confidence = m.extract_article(
            candidate, source, markup, {})
        self.assertIsNotNone(published)
        if "recorded_extraction" in row:
            # Preserve the complete saved replay's extraction while exercising
            # the same captured natural units and downstream fact preparation.
            self.assertEqual(title, row["recorded_extraction"][0])
            title, summary, facts = row["recorded_extraction"]
        evidence = replace(evidence, published_utc=published.isoformat(),
                           published_raw=raw, published_source=published_source,
                           confidence=confidence)
        projections, remainder, excluded = m.project_article_evidence(evidence)
        articles = []
        if projections:
            m.validate_evidence_dispositions(evidence, projections, remainder, excluded)
            for projection in projections:
                articles.append(m.Article(source.name, row["url"], projection.title,
                    projection.summary, list(projection.key_facts), "", published, raw,
                    published_source, confidence, set(), event_kind="software_update",
                    evidence=evidence, bound_claim=projection.claim))
        else:
            is_roundup = m.is_roundup_article_title(candidate.title)
            if not is_roundup and m.detail_summary_needs_discovery_enrichment(summary, facts):
                summary = m.safe_combine_detail_and_discovery_summary(
                    title, summary, candidate.summary)
            variants = [variant
                for base_title, base_summary, base_facts in m.roundup_article_variants(
                    candidate.title, title, summary, facts)
                for variant in m.compound_article_variants(
                    base_title, base_summary, base_facts)]
            for variant_title, variant_summary, variant_facts in variants:
                context = m.safe_context_for_detail_article(is_roundup, variant_title,
                    variant_summary, candidate.context)
                if not m.is_relevant_candidate(m.Candidate(source.name, row["url"],
                    variant_title, variant_summary, candidate.feed_time_raw,
                    context=context), source, variant_facts):
                    continue
                article = m.Article(source.name, row["url"], variant_title,
                    variant_summary, list(variant_facts), "", published, raw,
                    published_source, confidence,
                    m.article_tokens(variant_title, " ".join(
                        [variant_summary[:1200], *variant_facts[:5]])),
                    event_kind=m.detect_event_kind(variant_title, variant_summary,
                                                   variant_facts),
                    regions=m.extract_regions(" ".join(
                        [variant_title, variant_summary, *variant_facts[:5]])),
                    evidence=evidence, projection_source_title=candidate.title)
                article._source_kind_snapshot = (variant_title, variant_summary,
                                                 tuple(variant_facts), article.event_kind)
                articles.append(article)
            if articles and (len(variants) > 1 or is_roundup):
                assigned, remaining, excluded = m.projected_source_dispositions(
                    evidence, [article.key_facts for article in articles],
                    [summary, *facts])
                m.validate_source_span_dispositions(evidence,
                    [span for spans in assigned for span in spans], remaining, excluded)
                for article, spans in zip(articles, assigned):
                    article.projected_fact_spans = spans
        self.assertTrue(articles)
        events = m.cluster_articles(articles)
        event_dicts = [m.event_to_dict(event, timezone.utc) for event in events]
        queue = m.build_final_brief_queue(event_dicts)
        return evidence, events, event_dicts, queue

    def test_local_details_are_consumable_and_located(self):
        # Multiple fragments in one item must survive together, so generic
        # topic words elsewhere cannot satisfy a missing condition.
        targets = {
            "e60d1321d9b6f10ed21d586f": [
                (6, ("A new ranking system", "most relevant results to the top")),
                (11, ("proper indexing", "Optimizing Search & Siri")),
            ],
            "f800cf2ad70e0e037926dc10": [
                (1, ("分析师Jeff Pu指出", "铰链生产遇到了瓶颈")),
            ],
            "e6449aec0188fa1a5929f38d": [
                (5, ("iPhone 17 or later", "iOS 27, iPadOS 27, or macOS 27")),
            ],
            "b1095240a9dd23076cb9866e": [
                (5, ("both events and reminders", "creating or editing an event")),
                (6, ("toggle this off in Settings",)),
                (19, ("’List’ and ‘Up Next’ widgets", "extra-large size")),
                (24, ("visual intelligence button", "scan an event flyer")),
            ],
            "975f836e815e3c3b2b3b23ed": [
                (5, ("third-party apps may require a separate sign-in", "banking apps")),
                (26, ("Carrier account management", "main iPhone")),
                (37, ("contact your carrier", "deleting an eSIM", "may not stop")),
            ],
            "4c3807ee198139ce58c1a24c": [
                (6, ("In season two", "Wanda (Drinda)", "caught seemingly red-handed")),
            ],
        }
        required_conditions = {
            ("e60d1321d9b6f10ed21d586f", 11),
            ("e6449aec0188fa1a5929f38d", 5),
            ("b1095240a9dd23076cb9866e", 6),
            ("975f836e815e3c3b2b3b23ed", 37),
        }
        for article_id, expected in targets.items():
            row = self.rows[article_id]
            evidence, events, event_dicts, queue = self.run_source(row)
            self.assertEqual({event.event_id for event in events},
                             {item["id"] for item in queue})
            for index, fragments in expected:
                with self.subTest(source=article_id, unit=index):
                    unit = evidence.units[index]
                    located = [(event_dict, fact) for event_dict in event_dicts
                        for fact in event_dict.get("fact_sources", [])
                        if all(fragment in fact["text"] for fragment in fragments)
                        and any(origin["article_id"] == article_id
                                and origin["url"] == row["url"]
                                and origin["unit_id"] == unit.unit_id
                                and unit.text[origin["start"]:origin["end"]]
                                    in fact["text"]
                                for origin in fact["origins"])]
                    self.assertTrue(located,
                        f"unit {index} missing from located event facts: {fragments}")
                    for event_dict, fact in located:
                        self.assertIn(fact["text"], event_dict["key_facts"])
                        self.assertTrue(any(item["id"] == event_dict["id"] for item in queue))
                    if (article_id, index) in required_conditions:
                        self.assertTrue(any(fact["text"] in event_dict.get("must_include_facts", [])
                                            for event_dict, fact in located))

    def test_neighboring_noise_and_cross_topic_camera_claim_stay_out(self):
        m = self.m
        mail = self.run_source(self.rows["e60d1321d9b6f10ed21d586f"])[2]
        self.assertFalse(any("I suspect that statement" in fact
            for event in mail for fact in event["key_facts"] + event.get("must_include_facts", [])))
        calendar = self.run_source(self.rows["b1095240a9dd23076cb9866e"])[2]
        self.assertFalse(any("I’ve been very happy" in fact
            for event in calendar for fact in event["key_facts"] + event.get("must_include_facts", [])))
        wanda = self.run_source(self.rows["4c3807ee198139ce58c1a24c"])[2]
        self.assertFalse(any("$14.99 per month" in fact
            for event in wanda for fact in event["key_facts"] + event.get("must_include_facts", [])))
        title = self.rows["e6449aec0188fa1a5929f38d"]["title"]
        summary = self.rows["e6449aec0188fa1a5929f38d"]["discovery_lead"]
        camera_design = "A leaked iPhone camera design adds a new rear camera module and changes the camera bump layout."
        self.assertEqual(m.filter_key_facts_for_primary_topic(title, summary,
                         [camera_design]), [])
        different_work = json.loads(json.dumps(self.rows["4c3807ee198139ce58c1a24c"]))
        for statement in (
            "Here’s Apple TV on what to expect from the second season of “The Other Show”:",
            "In season two, the other show's family searches for a missing coach. The case takes them to a different town.",
        ):
            different_work["units"].append({
                "unit_id": "", "kind": "p", "text": statement, "origin": "html",
                "ordinal": len(different_work["units"]), "container_id": "",
            })
        unrelated = self.run_source(different_work)[2]
        self.assertFalse(any("missing coach" in fact
            for event in unrelated for fact in event["key_facts"] + event.get("must_include_facts", [])))

    def test_neighboring_app_feature_does_not_become_current_fact(self):
        for text in (
            "Google Calendar allows users to create reminders with a separate account and provides search results across shared calendars.",
            "Apple Calendar allows users to create reminders with a separate account and provides search results across shared calendars.",
        ):
            with self.subTest(text=text):
                row = json.loads(json.dumps(self.rows["e60d1321d9b6f10ed21d586f"]))
                row["units"].append({"kind": "p", "text": text})
                _evidence, _events, event_dicts, _queue = self.run_source(row)
                self.assertFalse(any(text in fact["text"] for event in event_dicts
                    for fact in event.get("fact_sources", [])))

    def test_short_foreign_subject_changes_following_pronoun_scope(self):
        row = json.loads(json.dumps(self.rows["e60d1321d9b6f10ed21d586f"]))
        foreign = (
            "Google Calendar provides reminders.",
            "It allows users to create reminders with a separate account and provides search results across shared calendars.",
        )
        for text in foreign:
            row["units"].append({"kind": "p", "text": text})
        evidence, _events, event_dicts, _queue = self.run_source(row)
        self.assertEqual([unit.text for unit in evidence.units[-2:]], list(foreign))
        self.assertFalse(any(foreign[1] in fact["text"]
            for event in event_dicts for fact in event.get("fact_sources", [])))
        self.assertFalse(any(foreign[1] in text for event in event_dicts
            for text in event.get("must_include_facts", [])))

    def test_parent_release_features_keep_exact_source_fact_or_review_origin(self):
        targets = {
            "e5e9f162d87eb67980773eff": [
                ("11d4a91c3c9498f42ecbc03c", ("Shazam", "智能叠放", "歌曲标题和歌手名")),
            ],
            "86239c29eb6c0e1c88a104cb": [
                ("17f4049b457eeb149a706713", ("自然语言创建活动", "时间、地点、受邀人和活动标题")),
                ("726d63594b7e6adbc6c551d7", ("屏幕使用时间", "设备使用情况", "调整访问权限")),
                ("dc89a0ecc8d8606d85aafac8", ("Liquid Glass", "极致透明", "完全着色")),
            ],
            "3d5647fc0439ef1e8373e5f0": [
                ("116228f13ae95fa2571b4587", ("自动化任务", "生成快捷指令")),
                ("2be94553e630cf86123b666c", ("顶部工具栏", "侧边栏", "窗口形状和菜单栏图标", "减少了菜单栏")),
                ("c739b49d967357aa3560771f", ("自然语言生成图像", "生成逼真图像的能力")),
                ("82f269ba9c3c15cb66c076a7", ("折射效果和对比度", "透明度滑块", "完全着色")),
            ],
        }
        for article_id, expected in targets.items():
            evidence, events, event_dicts, _queue = self.run_source(self.overdelete_rows[article_id])
            for unit_id, fragments in expected:
                with self.subTest(article_id=article_id, unit_id=unit_id):
                    unit = next(unit for unit in evidence.units if unit.unit_id == unit_id)
                    self.assertTrue(all(fragment in unit.text for fragment in fragments))
                    selected = any(all(fragment in fact["text"] for fragment in fragments)
                        and any(origin["article_id"] == article_id
                            and origin["unit_id"] == unit_id
                            and unit.text[origin["start"]:origin["end"]] in fact["text"]
                            and all(fragment in unit.text[origin["start"]:origin["end"]]
                                    for fragment in fragments)
                            for origin in fact["origins"])
                        for event in event_dicts for fact in event.get("fact_sources", []))
                    review = any(all(fragment in fact.text for fragment in fragments)
                        and any(origin[2] == article_id and origin[3] == unit_id
                            and unit.text[origin[4]:origin[5]] == fact.text
                            for origin in fact.origins)
                        for event in events for fact in event.fact_plan.unprocessed)
                    self.assertTrue(selected or review,
                        f"source unit {unit_id} was neither selected nor kept for review")

    def test_same_work_synopsis_retains_declarative_positions_without_promotion(self):
        row = json.loads(json.dumps(self.rows["4c3807ee198139ce58c1a24c"]))
        statements = (
            "In season two, the Klatts return to their suburban home after months of searching for Wanda and begin rebuilding trust with the neighbors who witnessed her disappearance.",
            "Wanda finds a coded letter that links the murder to the town council.",
            "Her parents follow the lead through a shuttered train station.",
            "A witness later identifies the local doctor at the scene.",
        )
        row["units"][6]["text"] = " ".join((*statements, "Who can they trust?",
            "Subscribe now to watch more on Apple TV."))
        evidence, _events, event_dicts, _queue = self.run_source(row)
        unit = evidence.units[6]
        for statement in statements:
            with self.subTest(statement=statement):
                self.assertTrue(any(statement in fact["text"]
                    and any(origin["unit_id"] == unit.unit_id
                            and statement in unit.text[origin["start"]:origin["end"]]
                            for origin in fact["origins"])
                    for event in event_dicts for fact in event.get("fact_sources", [])))
        self.assertFalse(any("Who can they trust?" in fact["text"]
            or "Subscribe now to watch more" in fact["text"]
            for event in event_dicts for fact in event.get("fact_sources", [])))

    def test_replay_context_is_not_promoted_to_current_action_facts(self):
        rejected = {
            "80416cfdd640a69ddbfa051a": [
                (11, "worth the effort"),
                (16, "image credit: Apple"),
            ],
            "23b006e10aefe5daec40a03d": [
                (51, "2017年iPhone X发布"),
            ],
            "9ff16c1e9962f77409b33777": [
                (10, "Rumors suggest Apple will launch its own home security cameras"),
            ],
            "942845e03ef12ad9056b4018": [],
            "aa1a109377e5c8f1772f54d5": [
                (12, "make it seem more impressive"),
            ],
            "1ed292a7c9da70fddad2ac18": [
                (4, "彻底改变了日常移动生产力"),
                (4, "深度共生开辟了全新可能"),
            ],
        }
        retained = {
            "80416cfdd640a69ddbfa051a": (3, "When developers rebuild their apps using the new Xcode 27.1"),
            "23b006e10aefe5daec40a03d": (30, "从演示来看，通过不同折叠方式"),
            "9ff16c1e9962f77409b33777": (1, "Apple is requiring a $9.99 iCloud+ plan"),
            "942845e03ef12ad9056b4018": (1, "new EQ is specifically tied to your AirPods"),
            "aa1a109377e5c8f1772f54d5": (71, "preinstalled on their hardware"),
            "1ed292a7c9da70fddad2ac18": (4, "均可直接取代传统语音助手"),
        }
        for article_id, bad_units in rejected.items():
            evidence, _events, event_dicts, _queue = self.run_source(self.replay_rows[article_id])
            for index, fragment in bad_units:
                with self.subTest(article_id=article_id, rejected_unit=index):
                    unit = evidence.units[index]
                    self.assertIn(fragment, unit.text)
                    self.assertFalse(any(fragment in fact["text"]
                        and any(origin["unit_id"] == unit.unit_id for origin in fact["origins"])
                        for event in event_dicts for fact in event.get("fact_sources", [])))
                    self.assertFalse(any(fragment in fact for event in event_dicts
                        for fact in event.get("must_include_facts", [])))
            index, fragment = retained[article_id]
            unit = evidence.units[index]
            with self.subTest(article_id=article_id, retained_unit=index):
                self.assertTrue(any(fragment in fact["text"]
                    and any(origin["unit_id"] == unit.unit_id
                            and unit.text[origin["start"]:origin["end"]] in fact["text"]
                            for origin in fact["origins"])
                    for event in event_dicts for fact in event.get("fact_sources", [])))
            if article_id == "1ed292a7c9da70fddad2ac18":
                self.assertTrue(any("业内分析人士指出" in fact["text"]
                    for event in event_dicts for fact in event.get("fact_sources", [])))

    def test_current_action_mechanisms_and_limits_survive_narrow_noise_filter(self):
        # Complete saved source units pass through extraction, variants,
        # projection, preparation and event/queue serialization. One source
        # can protect several distinct relations without one test per story.
        targets = {
            "633aca132d18dc3205d49106": {4: (
                "nano-texture finish technology to reduce glare and reflections",
                "optically clear adhesives let the display layers glide",
            )},
            "80416cfdd640a69ddbfa051a": {2: (
                "existing builds will be displayed full screen on the front",
                "apps will be ranged left",
            )},
            "867743b2a11cd91c0795493f": {15: (
                "from ultra-clear to fully tinted", "Uniform toolbars, edge-to-edge sidebars",
            )},
            "e5e9f162d87eb67980773eff": {28: (
                "不会创建或存储录音", "安全隔区", "用户拥有控制权",
            )},
            "28967a535542e54650e6d308": {2: (
                "像素层面安全地标注照片数据", "转换为不可更改的图像",
            )},
            "203088f082d48396beb7161b": {4: (
                "opens a dynamic app grid", "full app launcher remains available",
            )},
            "e9b2227dd67dec29fe80e284": {
                5: ("dedicated Siri mode in Camera", "screenshots and captured images as context"),
                8: ("permission requests to websites", "detect and obscure graphic imagery"),
                9: ("readability improvements", "connect directly to compatible cardio equipment"),
            },
            "5517378cbc289889e7128216": {45: (
                "2TB iCloud+ plan for one camera", "4K streaming doesn't",
            )},
            "3deab7210ba8e5f3706cb7d9": {5: (
                "AVEVideoEncoder flaw", "UDF file system vulnerability", "Bluetooth, CUPS, and WebDAV",
            )},
            "1c4b2dec27a3a8025021fbbe": {20: (
                "switch between two iPhones", "same phone number on each device",
            )},
            "7f42b708e89b0e827286e581": {11: (
                "scan a receipt", "option to Split Bill with Apple Cash",
            )},
            "3e4ac554b4f7f9423a98297f": {
                15: ("Siri AI finally works with Apple Music", "only on the Mac"),
                44: ("removed the Open Tab Group action from the Mac",),
            },
            "b5d511740635c817ffb8740b": {
                6: ("dedicated Siri app allows you to revisit",),
                10: ("based on fitness history", "doesn't need your iPhone nearby"),
                11: ("no longer requires your iPhone to be nearby",),
            },
            "6aedcbff4029bfb5233dd9ba": {102: (
                "remote attacker may be able to cause unexpected app termination",
                "arbitrary code execution",
            )},
            "eced14d5d32e2d3f3bb88fe6": {
                52: ("focus tracking uses on-device AI models", "subject leaves the screen"),
                54: ("main camera signs photo data at a pixel level", "unalterable image"),
                92: ("ambient listening to take high-level notes", "You control if and when"),
                121: ("dock on the home screen is now oriented vertically", "status bar retains"),
            },
        }
        required_limits = {
            ("e5e9f162d87eb67980773eff", 28),
            ("5517378cbc289889e7128216", 45),
            ("3e4ac554b4f7f9423a98297f", 15),
            ("3e4ac554b4f7f9423a98297f", 44),
            ("b5d511740635c817ffb8740b", 11),
        }
        for article_id, units in targets.items():
            row = self.replay_rows.get(article_id) or self.overdelete_rows[article_id]
            evidence, events, event_dicts, queue = self.run_source(row)
            for index, fragments in units.items():
                unit = evidence.units[index]
                for fragment in fragments:
                    with self.subTest(article_id=article_id, unit=index, fragment=fragment):
                        located = [(event, fact) for event in event_dicts
                            for fact in event.get("fact_sources", [])
                            if fragment in fact["text"]
                            and any(origin["article_id"] == article_id
                                and origin["unit_id"] == unit.unit_id
                                and unit.text[origin["start"]:origin["end"]] in fact["text"]
                                for origin in fact["origins"])]
                        self.assertTrue(located, f"unconsumed {article_id} unit {index}: {fragment}")
                        self.assertTrue(any(fact["text"] in event["key_facts"]
                            or fact["text"] in event.get("must_include_facts", [])
                            for event, fact in located))
                        if (article_id, index) in required_limits:
                            self.assertTrue(any(fact["text"] in event.get("must_include_facts", [])
                                and "source-condition" in fact["roles"]
                                for event, fact in located))
                        self.assertTrue(any(item["id"] == event["id"]
                            for event, _fact in located for item in queue))
            if article_id == "6aedcbff4029bfb5233dd9ba":
                for indices, cve, impact in (
                    ((100, 102, 104), "CVE-2026-65414", "remote attacker"),
                    ((105, 107, 109), "CVE-2026-84560", "unauthorized access to Bluetooth"),
                ):
                    with self.subTest(component_impact=cve):
                        required_units = {evidence.units[i].unit_id for i in indices}
                        selected = [fact for event in event_dicts
                            for fact in event.get("fact_sources", [])
                            if "Bluetooth" in fact["text"] and cve in fact["text"]
                            and impact in fact["text"]
                            and required_units.issubset(
                                {origin["unit_id"] for origin in fact["origins"]})]
                        self.assertTrue(selected)
                        self.assertTrue(any(all(evidence.units[index].text[
                            origin["start"]:origin["end"]] in fact["text"]
                            for index in indices for origin in fact["origins"]
                            if origin["unit_id"] == evidence.units[index].unit_id)
                            for fact in selected))

    def test_semantic_support_keeps_observation_reporting_and_specifications(self):
        targets = {
            "0dd40f358db769f24956842e": (5,
                "This video does briefly show the front screen of one of the iPhones, but of course it's off."),
            "6d69c0d6c8563a2cd1a41922": (0, "A new report says that Phil Schiller left"),
            "e0ef44de52b202a3208421f6": (50, "four Thunderbolt ports"),
        }
        for article_id, (index, fragment) in targets.items():
            evidence, _events, event_dicts, _queue = self.run_source(self.semantic_rows[article_id])
            unit = evidence.units[index]
            with self.subTest(article_id=article_id, retained=fragment):
                self.assertTrue(any(fragment in fact["text"]
                    and any(origin["unit_id"] == unit.unit_id
                        and unit.text[origin["start"]:origin["end"]] in fact["text"]
                        for origin in fact["origins"])
                    for event in event_dicts for fact in event.get("fact_sources", [])))
                if article_id == "0dd40f358db769f24956842e":
                    start = unit.text.index(fragment)
                    self.assertTrue(any(fact["text"] == fragment
                        and any(origin["unit_id"] == unit.unit_id
                            and (origin["start"], origin["end"]) == (start, start + len(fragment))
                            for origin in fact["origins"])
                        for event in event_dicts for fact in event.get("fact_sources", [])))
        article_id = "6d69c0d6c8563a2cd1a41922"
        evidence, _events, event_dicts, _queue = self.run_source(self.semantic_rows[article_id])
        unit = evidence.units[11]
        appeal = [fact for event in event_dicts for fact in event.get("fact_sources", [])
            if "Apple is currently appealing to the Supreme Court" in fact["text"]
            and any(origin["unit_id"] == unit.unit_id for origin in fact["origins"])]
        self.assertTrue(appeal)
        self.assertFalse(any("source-condition" in fact["roles"] for fact in appeal))

    def test_semantic_support_rejects_editorial_hypothesis_and_false_conditions(self):
        rejected = {
            "0dd40f358db769f24956842e": ("Bigfoot question", "You also don't only film",
                "And of course a store mounts"),
            "6d69c0d6c8563a2cd1a41922": ("Read the room", "Conceivably Apple could",
                "might burst a blood vessel", "Perhaps Apple is just throwing up",
                "for some reason"),
            "e0ef44de52b202a3208421f6": ("Desktop Mac price ranges below",
                "is the only choice", "That insane price", "better shout", "option to take"),
            "2257caf4b54964f7296ae615": ("needs to analyze what works",),
        }
        for article_id, fragments in rejected.items():
            _evidence, _events, event_dicts, _queue = self.run_source(self.semantic_rows[article_id])
            for fragment in fragments:
                with self.subTest(article_id=article_id, rejected=fragment):
                    self.assertFalse(any(fragment in fact["text"]
                        for event in event_dicts for fact in event.get("fact_sources", [])))
                    self.assertFalse(any(fragment in fact
                        for event in event_dicts for fact in event.get("must_include_facts", [])))

    def test_live_support_separates_reported_facts_from_inference_and_captions(self):
        cases = {
            "40544989e9ecc18b0e35869f": (
                1, ("baseless accusations",), 1, "The lawsuit is ongoing"),
            "d019eb415ca4ca31a1bb6ec9": (
                11, ("likely a good sign",), 9, "cannot assign roles to the four speakers"),
            "0ba11ba04e201970be18016f": (
                5, ("likely down to the device's display geometry",), 3,
                "can't drag the divider"),
            "acdb7392465608a191da96e8": (
                11, ("A VPN is meant to mask your traffic, not track the user.",
                     "Image source: Proton"), 10,
                "85% of those downloaded in the US contain trackers"),
            "26ad5365e3a7b8d9c121b682": (
                7, ("would previously have hoped", "To assuage whatever loss"), 7,
                "carriers who support it will charge for the privilege"),
            "2e2a5fd90ba3d268445a8d06": (
                3, ("Many assumed",), 7,
                "HomePod 27 software includes the necessary code for Siri AI"),
            "f800cf2ad70e0e037926dc10": (
                1, ("想原价入手并不容易",), 1, "分析师Jeff Pu指出"),
        }
        for article_id, (bad_index, rejected, good_index, retained) in cases.items():
            row = (self.semantic_rows.get(article_id)
                or self.overdelete_rows.get(article_id) or self.rows[article_id])
            evidence, events, event_dicts, _queue = self.run_source(row)
            bad_unit, good_unit = evidence.units[bad_index], evidence.units[good_index]
            if article_id == "acdb7392465608a191da96e8":
                self.assertEqual(bad_unit.unit_id, "a848e94be51f1294a2e026c4")
                self.assertFalse(any(any(origin[3] == bad_unit.unit_id
                    for origin in fact.origins)
                    for event in events
                    for fact in (*event.fact_plan.facts, *event.fact_plan.required)))
                self.assertEqual(bad_unit.container_id, "caption")
            for fragment in rejected:
                with self.subTest(article_id=article_id, rejected=fragment):
                    self.assertIn(fragment, bad_unit.text)
                    self.assertFalse(any(fragment in fact["text"]
                        for event in event_dicts for fact in event.get("fact_sources", [])))
                    self.assertFalse(any(fragment in fact
                        for event in event_dicts for fact in event.get("must_include_facts", [])))
                    if article_id == "0ba11ba04e201970be18016f":
                        self.assertFalse(any(fragment in event["summary"]
                            for event in event_dicts))
            with self.subTest(article_id=article_id, retained=retained):
                self.assertIn(retained, good_unit.text)
                self.assertTrue(any(retained in fact.text
                    and any(origin[2] == article_id and origin[3] == good_unit.unit_id
                        and retained in good_unit.text[origin[4]:origin[5]]
                        for origin in fact.origins)
                    for event in events
                    for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed)))
            if article_id == "2e2a5fd90ba3d268445a8d06":
                june = evidence.units[3]
                self.assertTrue(any("gave zero mention of the assistant" in fact.text
                    and any(origin[3] == june.unit_id for origin in fact.origins)
                    for event in events
                    for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed)))
            for unit_index, fragment in ({
                "40544989e9ecc18b0e35869f": (
                    (4, "Sections D and F of the filing"),),
                "2e2a5fd90ba3d268445a8d06": (
                    (7, "isn’t active right now for users"),
                    (8, "unclear whether Siri AI will be tied to new hardware exclusively")),
            }.get(article_id, ())):
                unit = evidence.units[unit_index]
                self.assertTrue(any(fragment in fact.text
                    and any(origin[3] == unit.unit_id for origin in fact.origins)
                    for event in events
                    for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed)))

    def test_caption_role_does_not_swallow_mixed_body_prose(self):
        markup = ('<article><p>iPhone Duo supports a USB-C cable for pairing and charging. '
                  '<span class="image-caption">Image source: Publisher</span></p></article>')
        evidence = self.m.capture_article_evidence("Test", "https://example.test/mixed-caption",
            markup, "iPhone Duo pairing and charging")
        self.assertEqual(len(evidence.units), 1)
        self.assertEqual(evidence.units[0].kind, "p")
        self.assertEqual(evidence.units[0].container_id, "")

    def test_body_capabilities_replace_excluded_captions_at_exact_origins(self):
        cases = {
            "db45f02370b6f31e15047297": (10, 11, (
                "special animation that occurs when opening and closing",
                "blurred and pulled into the different form factors")),
            "d28eef9ef5cde18211077b39": (14, 13, (
                "new tab view that arranges the tabs in a Tab Group horizontally",
                "swipe between them")),
        }
        for article_id, (body_index, caption_index, fragments) in cases.items():
            evidence, events, event_dicts, _queue = self.run_source(
                self.semantic_rows[article_id])
            body, caption = evidence.units[body_index], evidence.units[caption_index]
            self.assertEqual(body.container_id, "")
            self.assertEqual(caption.container_id, "caption")
            prepared = [fact for event in events
                for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed,
                             *event.fact_plan.required)]
            self.assertFalse(any(origin[3] == caption.unit_id
                for fact in prepared for origin in fact.origins))
            with self.subTest(article_id=article_id):
                self.assertTrue(any(
                    all(fragment in fact.text and fragment in body.text[origin[4]:origin[5]]
                        for fragment in fragments)
                    for fact in prepared for origin in fact.origins
                    if origin[2] == article_id and origin[3] == body.unit_id))
                self.assertTrue(any(
                    all(fragment in fact["text"] for fragment in fragments)
                    and any(origin["article_id"] == article_id
                        and origin["unit_id"] == body.unit_id
                        and fact["text"] == body.text[origin["start"]:origin["end"]]
                        for origin in fact["origins"])
                    for event in event_dicts
                    for fact in event.get("fact_sources", [])))
                self.assertFalse(any("excellent view" in fact["text"]
                    for event in event_dicts for fact in event.get("fact_sources", [])))

    def test_included_modifier_and_prior_product_stage_do_not_become_current_facts(self):
        cases = {
            "4523e24dae5e6e0ddf346200": (
                self.semantic_rows, 6, "376e6cdee15c239fdedde936",
                ("included biometric authentication system", "secure and foolproof",
                 "perfect alternative to Face ID"),
                3, "Apple Watch is worn and unlocked, the iPhone Duo will authenticate"),
            "80416cfdd640a69ddbfa051a": (
                self.replay_rows, 13, "b14526d08fdca6cbf4c0c211",
                ("Back when the iPad first came out", "automatically scale up iPhone apps"),
                12, "huge black bars left and right"),
        }
        for article_id, (rows, bad_index, bad_id, rejected, good_index, retained) in cases.items():
            evidence, events, event_dicts, _queue = self.run_source(rows[article_id])
            bad, good = evidence.units[bad_index], evidence.units[good_index]
            self.assertEqual(bad.unit_id, bad_id)
            self.assertTrue(all(fragment in bad.text for fragment in rejected))
            with self.subTest(article_id=article_id):
                self.assertFalse(any(origin[3] == bad.unit_id
                    for event in events
                    for fact in (*event.fact_plan.facts, *event.fact_plan.unprocessed,
                                 *event.fact_plan.required)
                    for origin in fact.origins))
                self.assertFalse(any(fragment in text for fragment in rejected
                    for event in event_dicts
                    for text in (event["summary"], *event["key_facts"],
                                 *event.get("must_include_facts", []),
                                 *(fact["text"] for fact in event.get("fact_sources", [])))))
                self.assertTrue(any(retained in fact["text"]
                    and any(origin["article_id"] == article_id
                        and origin["unit_id"] == good.unit_id
                        and retained in good.text[origin["start"]:origin["end"]]
                        for origin in fact["origins"])
                    for event in event_dicts
                    for fact in event.get("fact_sources", [])))

    def test_passive_and_negative_inclusion_limits_keep_exact_source_origins(self):
        cases = {
            "a5900c2be5e67dd09b2eaea4": (11, "c9591ded8437cfc7076a9fe0", (
                "Readiness app itself has not been included in the beta",
                "related to the Workout app")),
            "943afe4b38dba799cdef15f6": (8, "1c4db199da880633cfcecd7c", (
                "AppleCare isn't included either",
                "need AppleCare+ or AppleCare One")),
            "7ddb3f72f67a0d0a763edc72": (5, "c0feb749d8ab814902d0556f", (
                "second argument involving the court's scope was not included in this filing",
                'only said that it would discuss the argument surrounding the "spirit of the law."')),
        }
        for article_id, (index, unit_id, fragments) in cases.items():
            evidence, events, event_dicts, _queue = self.run_source(
                self.semantic_rows[article_id])
            unit = evidence.units[index]
            self.assertEqual(unit.unit_id, unit_id)
            self.assertEqual(unit.container_id, "")
            self.assertTrue(all(fragment in unit.text for fragment in fragments))
            with self.subTest(article_id=article_id):
                self.assertTrue(any(all(fragment in fact["text"] for fragment in fragments)
                    and any(origin["article_id"] == article_id
                        and origin["unit_id"] == unit_id
                        and fact["text"] == unit.text[origin["start"]:origin["end"]]
                        for origin in fact["origins"])
                    and (fact["text"] in event["key_facts"]
                         or fact["text"] in event.get("must_include_facts", []))
                    for event in event_dicts
                    for fact in event.get("fact_sources", [])))

    def test_separate_stage_and_pairing_have_distinct_fact_roles(self):
        rejected = {
            "23b006e10aefe5daec40a03d": ("2014年，库克掏出",),
            "5a9a5ac0a63128f0e1487331": ("A rumor in late August suggested Apple tried and failed",),
        }
        for article_id, fragments in rejected.items():
            _evidence, _events, event_dicts, _queue = self.run_source(self.semantic_rows[article_id])
            for fragment in fragments:
                with self.subTest(article_id=article_id, rejected=fragment):
                    self.assertFalse(any(fragment in fact["text"]
                        for event in event_dicts for fact in event.get("fact_sources", [])))
                    self.assertFalse(any(fragment in fact
                        for event in event_dicts for fact in event.get("must_include_facts", [])))
        article_id = "38ede1a04c3171666180df9e"
        evidence, _events, event_dicts, _queue = self.run_source(self.semantic_rows[article_id])
        unit = evidence.units[4]
        pairing = [fact for event in event_dicts for fact in event.get("fact_sources", [])
            if "通过 USB-C 充电线配对和充电" in fact["text"]
            and any(origin["unit_id"] == unit.unit_id
                and "通过 USB-C 充电线配对和充电" in unit.text[origin["start"]:origin["end"]]
                for origin in fact["origins"])]
        self.assertTrue(pairing)
        self.assertFalse(any("磁力吸附在 iPad" in fact["text"] for fact in pairing))

    def test_continuing_stage_current_observation_and_download_terms(self):
        future_id = "9ff16c1e9962f77409b33777"
        evidence, _events, event_dicts, _queue = self.run_source(self.replay_rows[future_id])
        future = evidence.units[10]
        self.assertIn("as soon as next year", future.text)
        with self.subTest(issue="future-stage"):
            self.assertFalse(any("Apple's own home security cameras could require" in fact["text"]
                and any(origin["unit_id"] == future.unit_id for origin in fact["origins"])
                for event in event_dicts for fact in event.get("fact_sources", [])))
            self.assertFalse(any("Apple's own home security cameras could require" in fact
                for event in event_dicts for fact in event.get("must_include_facts", [])))

        observed_id = "3e4ac554b4f7f9423a98297f"
        evidence, _events, event_dicts, _queue = self.run_source(self.overdelete_rows[observed_id])
        observed = evidence.units[70]
        fragments = ("Clean Up removed her", "what looks to me like",
                     "Apple Watch poster and recreated that", "wooden cube seats")
        with self.subTest(issue="current-observation"):
            self.assertTrue(any("source-measurement" in fact["roles"]
                and all(fragment in fact["text"] for fragment in fragments)
                and any(origin["unit_id"] == observed.unit_id
                    and observed.text[origin["start"]:origin["end"]] == fact["text"]
                    for origin in fact["origins"])
                for event in event_dicts for fact in event.get("fact_sources", [])))
            self.assertFalse(any("if we ever divorce" in fact["text"]
                for event in event_dicts for fact in event.get("fact_sources", [])))

        access_id = "194f11ece70b91d6eeb18c44"
        evidence, _events, event_dicts, _queue = self.run_source(self.semantic_rows[access_id])
        access = evidence.units[25]
        with self.subTest(issue="download-and-subscription"):
            self.assertTrue(any("free to download" in fact["text"]
                and "subscription options" in fact["text"]
                and any(origin["unit_id"] == access.unit_id
                    and access.text[origin["start"]:origin["end"]] == fact["text"]
                    for origin in fact["origins"])
                for event in event_dicts for fact in event.get("fact_sources", [])))
            self.assertFalse(any("follow this link" in fact["text"]
                for event in event_dicts for fact in event.get("fact_sources", [])))


if __name__ == "__main__":
    unittest.main()
