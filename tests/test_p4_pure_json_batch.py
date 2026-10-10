"""Full captured source evidence for the September 24 pure-input boundaries."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from test_relevance_rules import load_module


FIXTURE = Path(__file__).parent / "fixtures/p4_pure_sources.json"
REPLAY_FIXTURE = Path(__file__).parent / "fixtures/p4_replay_source_boundaries.json"


class PureJsonBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()
        cls.rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.replay_rows = json.loads(REPLAY_FIXTURE.read_text(encoding="utf-8"))
        cls.sources = {source.name: source for source in cls.m.build_sources(
            datetime(2026, 9, 24, tzinfo=timezone.utc))}

    def source_articles(self, article_id):
        from apple_news_core.models import (ArticleEvidence, EmbeddedReference, EvidenceUnit,
                                            PublicationEvidence)
        m = self.m
        row = self.rows[article_id]
        data = dict(row["evidence"])
        data["units"] = tuple(EvidenceUnit(**unit) for unit in data["units"])
        data["publication_candidates"] = tuple(PublicationEvidence(**item)
            for item in data["publication_candidates"])
        data["embedded_references"] = tuple(EmbeddedReference(**item)
            for item in data["embedded_references"])
        evidence = ArticleEvidence(**data)
        title, summary, facts = row["recorded_extraction"]
        published = datetime.fromisoformat(evidence.published_utc)
        candidate = m.Candidate(evidence.source, evidence.url, evidence.discovery_title,
                                evidence.discovery_lead, evidence.published_utc)
        projections, remainder, excluded = m.project_article_evidence(evidence)
        if projections:
            m.validate_evidence_dispositions(evidence, projections, remainder, excluded)
            return [m.Article(evidence.source, evidence.url, projection.title,
                projection.summary, list(projection.key_facts), "", published,
                evidence.published_raw, evidence.published_source, evidence.confidence,
                set(), event_kind="software_update", evidence=evidence,
                bound_claim=projection.claim) for projection in projections]
        is_roundup = m.is_roundup_article_title(candidate.title)
        if not is_roundup and m.detail_summary_needs_discovery_enrichment(summary, facts):
            summary = m.safe_combine_detail_and_discovery_summary(
                title, summary, candidate.summary)
        variants = [variant
            for base_title, base_summary, base_facts in m.roundup_article_variants(
                candidate.title, title, summary, facts)
            for variant in m.compound_article_variants(
                base_title, base_summary, base_facts, evidence=evidence)]
        articles = []
        for variant_title, variant_summary, variant_facts in variants:
            context = m.safe_context_for_detail_article(is_roundup, variant_title,
                variant_summary, candidate.context)
            if not m.is_relevant_candidate(m.Candidate(evidence.source, evidence.url,
                variant_title, variant_summary, candidate.feed_time_raw,
                context=context), self.sources[evidence.source], variant_facts):
                continue
            article = m.Article(evidence.source, evidence.url, variant_title,
                variant_summary, list(variant_facts), "", published,
                evidence.published_raw, evidence.published_source, evidence.confidence,
                m.article_tokens(variant_title, " ".join(
                    [variant_summary[:1200], *variant_facts[:5]])),
                event_kind=m.detect_event_kind(variant_title, variant_summary, variant_facts),
                regions=m.extract_regions(" ".join(
                    [variant_title, variant_summary, *variant_facts[:5]])),
                evidence=evidence, projection_source_title=candidate.title)
            article._source_kind_snapshot = (variant_title, variant_summary,
                                             tuple(variant_facts), article.event_kind)
            articles.append(article)
        if articles and (len(variants) > 1 or is_roundup):
            assigned, remaining, excluded = m.projected_source_dispositions(
                evidence, [article.key_facts for article in articles], [summary, *facts])
            m.validate_source_span_dispositions(evidence,
                [span for spans in assigned for span in spans], remaining, excluded)
            for article, spans in zip(articles, assigned):
                article.projected_fact_spans = spans
        self.assertTrue(articles, article_id)
        return articles

    def cluster_sources(self, *article_ids):
        articles = [article for article_id in article_ids
                    for article in self.source_articles(article_id)]
        events = self.m.cluster_articles(articles)
        return events, [self.m.event_to_dict(event, timezone.utc) for event in events]

    def replay_article(self, article_id, row=None):
        from apple_news_core.models import (ArticleEvidence, EmbeddedReference, EvidenceUnit,
                                            PublicationEvidence)
        data = dict(self.replay_rows[article_id] if row is None else row)
        evidence = dict(data["evidence"])
        evidence["units"] = tuple(EvidenceUnit(**unit) for unit in evidence["units"])
        evidence["publication_candidates"] = tuple(PublicationEvidence(**item)
            for item in evidence["publication_candidates"])
        evidence["embedded_references"] = tuple(EmbeddedReference(**item)
            for item in evidence["embedded_references"])
        data["evidence"] = ArticleEvidence(**evidence)
        data["published_utc"] = datetime.fromisoformat(data["published_utc"])
        data["tokens"] = set(data["tokens"])
        data["regions"] = set(data["regions"])
        data["projection_parent_keys"] = frozenset(data["projection_parent_keys"])
        return self.m.Article(**data)

    def replay_source_review(self, event, article_id):
        facts = [fact for fact in event.fact_plan.unprocessed
            if any(origin[2] == article_id for origin in fact.origins)]
        evidence = next(article.evidence for article in event.articles
            if article.evidence.article_id == article_id)
        spans = sorted({(origin[3], origin[4], origin[5]) for fact in facts
            for origin in fact.origins if origin[2] == article_id and origin[3]})
        reason = "; ".join(dict.fromkeys(fact.reason for fact in facts if fact.reason))
        return self.m.evidence_review_item(evidence, spans, reason)

    @staticmethod
    def source_ids(event):
        return {article.evidence.article_id for article in event.articles}

    def assert_consumed(self, events, article_id, unit_index, *fragments):
        unit = self.rows[article_id]["evidence"]["units"][unit_index]
        self.assertTrue(all(fragment in unit["text"] for fragment in fragments))
        located = [(event, fact, origin) for event in events
            for fact in event.get("fact_sources", []) for origin in fact["origins"]
            if origin["article_id"] == article_id and origin["unit_id"] == unit["unit_id"]
            and all(fragment in fact["text"] for fragment in fragments)
            and fact["text"] == unit["text"][origin["start"]:origin["end"]]
            and (fact["text"] in event["key_facts"]
                 or fact["text"] in event.get("must_include_facts", []))]
        self.assertTrue(located, f"unconsumed {article_id} unit {unit_index}: {fragments}")

    def test_j1_named_works_and_current_actions_partition_without_losing_story(self):
        ids = ("de01701cce6e1c9cc49c41a6", "4c3807ee198139ce58c1a24c",
               "1476ddb4908efebdfcce1d2f", "86edefef354c0679a76eba3b",
               "d2f6c6e7d29758850363e21d", "1ccb24f4ce79672ee58370d9")
        variants = self.source_articles(ids[2])
        self.assertTrue(any("Snoopy" in article.title for article in variants))
        self.assertTrue(any("Fraggle" in article.title for article in variants))
        self.assertTrue(any("Warrior Kid" in article.title for article in variants))
        events, data = self.cluster_sources(*ids)
        peanuts = next(event for event in events if ids[0] in self.source_ids(event))
        self.assertNotIn(ids[1], self.source_ids(peanuts))
        self.assertFalse(any(term in fact for term in ("Where’s Wanda", "Fraggle Rock",
            "Warrior Kid") for fact in (*peanuts.key_facts, peanuts.summary)))
        wanted = next(event for event in events if ids[4] in self.source_ids(event))
        self.assertIn(ids[5], self.source_ids(wanted))
        for work, article_id, unit, fragments in (
            ("Warrior Kid", ids[2], 7, ("Marc", "Uncle Jake", "real courage")),
            ("Fraggle", ids[3], 10, ("Spirit Captain", "snow globe")),
            ("Wanted Man", ids[4], 5, ("George Kay",)),
            ("Where’s Wanda", ids[1], 6, ("Wanda (Drinda)", "caught seemingly red-handed")),
        ):
            matching = [event_dict for event, event_dict in zip(events, data)
                if (event is wanted if work == "Wanted Man"
                    else work.casefold() in event.title.casefold())]
            self.assertEqual(len(matching), 1, work)
            self.assert_consumed(matching, article_id, unit, *fragments)
            unit_id = self.rows[article_id]["evidence"]["units"][unit]["unit_id"]
            self.assertFalse(any(
                origin["article_id"] == article_id and origin["unit_id"] == unit_id
                for other in data if other is not matching[0]
                for fact in other.get("fact_sources", [])
                if all(fragment in fact["text"] for fragment in fragments)
                for origin in fact["origins"]), work)

    def test_j2_future_software_fix_has_one_owner_without_confirming_version(self):
        ids = ("56971ac9b96331dd38ba5da6", "7b9c4401d1420e623f9d984e",
               "93de49fb1fa93648f90c75ef", "2ba69689843f12dcbda46c3e",
               "47c6e3d883216337e3600ad0")
        events, data = self.cluster_sources(*ids)
        fix = next(event for event in events if ids[0] in self.source_ids(event))
        self.assertEqual(self.source_ids(fix), set(ids))
        self.assertEqual((fix.relevance_tier, fix.category), ("strong", "software_systems"))
        self.assertNotIn("27.0.1", fix.title)
        self.assertRegex(fix.summary, r"27\.0\.1.{0,100}\blikely\b")
        self.assertNotIn("watchOS 27.0.1", " ".join(
            (fix.summary, *fix.key_facts,
             *(fact.text for fact in fix.fact_plan.required))))
        self.assert_consumed(data, ids[3], 2, "内存分配错误", "并非硬件级别", "数据安全性未受任何影响")
        self.assert_consumed(data, ids[3], 3, "最后测试阶段", "暂时关闭", "数字密码")

    def test_wanted_merge_retains_same_work_episode_count_and_producer_credit(self):
        news_id = "d2f6c6e7d29758850363e21d"
        insider_id = "1ccb24f4ce79672ee58370d9"
        events, data = self.cluster_sources(news_id, insider_id)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(self.source_ids(event), {news_id, insider_id})
        for index, fragments in ((0, ("executive-produced", "Hugh Laurie")),
                                 (1, ("eight-episode series", "Felix Carmichael"))):
            self.assert_consumed(data, insider_id, index, *fragments)

    def test_j3_bilateral_license_and_platform_integration_join(self):
        qualcomm = ("3883c63d955e8633e55e0959", "79d5fad6f9ae17fa0faf1c90",
                    "fa84c793f59c0ad95aa84047", "c6accf56ad8d8f4bf087337f")
        square = ("50f23a2f6e3c8f0cf5503b66", "0ea8be7287251c8ded51a576",
                  "c53968bb22d3eafc3e6cc746")
        for ids, expected_tier in ((qualcomm, "strong"), (square, "ecosystem")):
            with self.subTest(ids=ids):
                events, data = self.cluster_sources(*ids)
                self.assertEqual(len(events), 1)
                self.assertEqual(self.source_ids(events[0]), set(ids))
                self.assertEqual(events[0].relevance_tier, expected_tier)
                self.assertEqual(events[0].category, "software_systems")
                if ids == qualcomm:
                    for article_id in ids:
                        for article in self.source_articles(article_id):
                            self.assertIn(
                                "primary-claim:apple:qualcomm:patent-license:effective-2027-04-01:bilateral-renewal",
                                self.m.article_reconciliation_profile(article).event_keys)
                    self.assert_consumed(data, ids[3], 1, "授权费用", "具体期限")
                else:
                    self.assert_consumed(data, ids[1], 3, "United States and Canada", "without an Apple Business account")
                    self.assert_consumed(data, ids[1], 4, "physical locations", "Australia", "United States")

    def test_license_counterparty_and_effective_stage_are_source_local(self):
        from copy import deepcopy

        base_id = "3883c63d955e8633e55e0959"
        base = self.rows[base_id]
        other = deepcopy(base)
        other_id = "counterparty-variant"
        def substitute(value):
            if isinstance(value, str):
                return value.replace("Qualcomm", "Ericsson").replace("qualcomm", "ericsson")
            if isinstance(value, list):
                return [substitute(item) for item in value]
            if isinstance(value, dict):
                return {key: substitute(item) for key, item in value.items()}
            return value
        other = substitute(other)
        other["evidence"]["article_id"] = other_id
        self.rows[other_id] = other
        try:
            events, _data = self.cluster_sources(base_id, other_id)
            self.assertEqual(len(events), 2)
            self.assertEqual({frozenset(self.source_ids(event)) for event in events},
                             {frozenset({base_id}), frozenset({other_id})})
            for event in events:
                party = "qualcomm" if base_id in self.source_ids(event) else "ericsson"
                self.assertEqual(event.relevance_tier, "strong")
                self.assertIn(
                    f"primary-claim:apple:{party}:patent-license:effective-2027-04-01:bilateral-renewal",
                    self.m.article_reconciliation_profile(event.articles[0]).event_keys)
        finally:
            del self.rows[other_id]

        m = self.m
        def profile(title, lead):
            return m.build_reconciliation_profile(title=title, lead=lead,
                identity=m.build_event_identity(title, lead), exact_facets=(), regions=())
        title = base["evidence"]["title"]
        announcement = base["evidence"]["units"][1]["text"]
        current = profile(title, announcement)
        renewal = lambda value: {key for key in value.event_keys
            if "patent-license:" in key and "bilateral-renewal" in key}
        self.assertTrue(renewal(current))
        dated = profile(title, "September 24, 2026: " + announcement)
        self.assertEqual(renewal(dated), renewal(current))
        for title, lead in (
            ("Qualcomm denies renewed patent license agreement with Apple",
             "Qualcomm has not renewed its global patent licensing agreement with Apple, effective April 1, 2027."),
            ("Qualcomm previously renewed patent license agreement with Apple",
             "In 2019, Qualcomm renewed its patent licensing agreement with Apple, effective April 1, 2019."),
        ):
            with self.subTest(title=title):
                self.assertFalse(renewal(profile(title, lead)))

    def test_j4_commentary_recap_and_reappearing_archive_remain_weak(self):
        ids = ("9e4867e4f9ba281d04db8fa0", "a3b8d50692ef1b9c7281de48",
               "24bb53849d73e8b7c0eca489", "62e91cb3a0a667475786c453",
               "0c69181af37e52d02e180b6d", "952966002ff95902698017e4",
               "b2bca21681f3cb2dba1fc7a1")
        events, _data = self.cluster_sources(*ids)
        self.assertTrue(all(event.relevance_tier == "weak" for event in events))
        archive = next(event for event in events if ids[5] in self.source_ids(event))
        self.assertIn(ids[6], self.source_ids(archive))

    def test_j5_current_measured_storage_joins_despite_buyer_headline(self):
        ids = ("fd8f2c5b696ae406520fbdd9", "82872c4b091518b95f87c27a")
        events, data = self.cluster_sources(*ids)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.source_ids(events[0]), set(ids))
        self.assertEqual(events[0].relevance_tier, "strong")
        self.assert_consumed(data, ids[0], 1, "3000.2", "3216.8")

    def test_j6_source_local_support_and_negative_context(self):
        ids = ("1476ddb4908efebdfcce1d2f", "86edefef354c0679a76eba3b",
               "d2f6c6e7d29758850363e21d", "1ccb24f4ce79672ee58370d9",
               "c1a610770f434bed77944a92", "50f23a2f6e3c8f0cf5503b66")
        _events, data = self.cluster_sources(*ids)
        targets = ((ids[0], 7, ("Uncle Jake", "real courage")),
                   (ids[1], 10, ("Spirit Captain", "snow globe")),
                   (ids[2], 5, ("George Kay",)),
                   (ids[3], 3, ("George Kay",)),
                   (ids[4], 10, ("加速度计", "陀螺仪")),
                   (ids[4], 37, ("仅开屏禁止", "黑名单")))
        for article_id, unit, fragments in targets:
            with self.subTest(article_id=article_id, unit=unit):
                self.assert_consumed(data, article_id, unit, *fragments)
        excluded = ((ids[1], 12), (ids[4], 6), (ids[4], 17),
                    (ids[4], 24), (ids[4], 43), (ids[4], 46), (ids[5], 2))
        for article_id, index in excluded:
            unit = self.rows[article_id]["evidence"]["units"][index]
            with self.subTest(excluded=(article_id, index)):
                self.assertFalse(any(origin["article_id"] == article_id
                    and origin["unit_id"] == unit["unit_id"]
                    for event in data for fact in event.get("fact_sources", [])
                    for origin in fact["origins"]))
        selected_text = " ".join(text for event in data for text in
            (event["summary"], *event["key_facts"], *event.get("must_include_facts", [])))
        self.assertNotIn("摇出了尊严", selected_text)
        self.assertNotIn("正式版大概率", selected_text)

    def test_motion_prior_notice_denial_keeps_historical_antecedent_in_review(self):
        article_id = "c1a610770f434bed77944a92"
        events, _data = self.cluster_sources(article_id)
        self.assertEqual(len(events), 1)
        event = events[0]
        units = self.rows[article_id]["evidence"]["units"]
        rumor, response = units[24], units[26]
        self.assertFalse(any(
            any(origin[2] == article_id and origin[3] in
                {rumor["unit_id"], response["unit_id"]}
                for origin in fact.origins)
            for fact in event.fact_plan.facts))
        linked = [fact for fact in event.fact_plan.unprocessed
            if "2023 年 11 月" in fact.text
            and "苹果已经通知" in fact.text
            and "没有一家明确说收到过苹果的通知" in fact.text
            and "苹果也没给回复" in fact.text]
        self.assertEqual(len(linked), 1)
        self.assertEqual(
            {(origin[3], origin[4], origin[5]) for origin in linked[0].origins},
            {(rumor["unit_id"], 0, len(rumor["text"])),
             (response["unit_id"], 0, len(response["text"]))})
        review = self.replay_source_review(event, article_id)
        self.assertTrue(all(any(item["unit_id"] == unit["unit_id"]
            and item["text"] == unit["text"] for item in review["unprocessed_evidence"])
            for unit in (rumor, response)))
        self.assertFalse(any(item["unit_id"] == units[25]["unit_id"]
            for item in review["unprocessed_evidence"]))

    def test_replay_preserves_unknown_capability_and_scoped_forecasts(self):
        readiness_id = "a5900c2be5e67dd09b2eaea4"
        readiness = [self.replay_article(article_id) for article_id in (
            "1be80f48fdcbca065ff53af6", readiness_id, "6bdd55f12291fc55388da530")]
        events = self.m.cluster_articles(readiness)
        data = [self.m.event_to_dict(event, timezone.utc) for event in events]
        unit = self.replay_rows[readiness_id]["evidence"]["units"][10]
        expected = unit["text"][114:248]
        self.assertTrue(expected.startswith("Previously code-named Cobalt"))
        self.assertTrue(any(fact["text"] == expected
            and fact["text"] in (*event["key_facts"], *event.get("must_include_facts", []))
            and any(origin["article_id"] == readiness_id and origin["unit_id"] == unit["unit_id"]
                and (origin["start"], origin["end"]) == (114, 248) for origin in fact["origins"])
            for event in data for fact in event.get("fact_sources", [])))
        self.assertFalse(any(origin["article_id"] == readiness_id
            and origin["unit_id"] == unit["unit_id"] and origin["start"] < 114
            for event in data for fact in event.get("fact_sources", [])
            for origin in fact["origins"]))

        preview_id = "c8168246a73576689587847d"
        preview = self.replay_article(preview_id)
        preview_event = self.m.cluster_articles([preview])[0]
        review = self.replay_source_review(preview_event, preview_id)
        watch_unit_id = self.replay_rows[preview_id]["evidence"]["units"][23]["unit_id"]
        self.assertFalse(any(origin[3] == watch_unit_id
            for fact in preview_event.fact_plan.facts for origin in fact.origins))
        for index, end, fragments in (
            (23, 130, ("据外媒爆料", "Series 12 可能", "全天候心率监测")),
            (29, 62, ("预计将会改变", "几乎可以肯定", "售价将显著高于")),
        ):
            unit = self.replay_rows[preview_id]["evidence"]["units"][index]
            with self.subTest(index=index):
                self.assertTrue(all(fragment in unit["text"][:end] for fragment in fragments))
                self.assertTrue(any(item["unit_id"] == unit["unit_id"]
                    and (item["start"], item["end"]) == (0, end)
                    and item["text"] == unit["text"][:end]
                    for item in review["unprocessed_evidence"]))
        self.assertFalse(any("究竟会涨多少" in item["text"]
            for item in review["unprocessed_evidence"] if item["unit_id"] == unit["unit_id"]))

    def test_replay_named_app_qualification_keeps_its_local_owner(self):
        readiness_id = "a5900c2be5e67dd09b2eaea4"
        for platform_note in ("", " on Apple Watch"):
            with self.subTest(platform_note=platform_note):
                row = deepcopy(self.replay_rows[readiness_id])
                unit = row["evidence"]["units"][10]
                unit["text"] = (unit["text"]
                    .replace("this new Readiness app", "Google’s new Fitbit app")
                    .replace("code-named Cobalt", "code-named Orion")
                    .replace("it is health-related", f"it is health-related{platform_note}"))
                self.assertIn("Google’s new Fitbit app. Previously code-named Orion", unit["text"])
                article = self.replay_article(readiness_id, row)
                events = self.m.cluster_articles([article])
                data = [self.m.event_to_dict(event, timezone.utc) for event in events]
                qualifier = unit["text"][unit["text"].index("Previously code-named"):]
                selected = [text for event in data for text in
                    (event["summary"], *event["key_facts"], *event.get("must_include_facts", []))]
                self.assertFalse(any(qualifier in text for text in selected))
                self.assertFalse(any(origin["article_id"] == readiness_id
                    and origin["unit_id"] == unit["unit_id"]
                    for event in data for fact in event.get("fact_sources", [])
                    for origin in fact["origins"]))
                self.assertTrue(any(fact.text == unit["text"]
                    and fact.origins[0][3:] == (unit["unit_id"], 0, len(unit["text"]))
                    for event in events for fact in event.fact_plan.unprocessed))

    def test_replay_media_marker_is_not_a_sensor_fact(self):
        article_id = "66c4dbd9f008b748a57a2d95"
        article = self.replay_article(article_id)
        data = [self.m.event_to_dict(event, timezone.utc)
            for event in self.m.cluster_articles([article])]
        marker = self.replay_rows[article_id]["evidence"]["units"][7]
        body = self.replay_rows[article_id]["evidence"]["units"][8]
        self.assertTrue(marker["text"].startswith("[Image:"))
        self.assertFalse(any(origin["unit_id"] == marker["unit_id"]
            for event in data for fact in event.get("fact_sources", [])
            for origin in fact["origins"]))
        self.assertTrue(any("32-petal design" in fact["text"]
            and "two-petal design" in fact["text"]
            and any(origin["unit_id"] == body["unit_id"]
                and fact["text"] == body["text"][origin["start"]:origin["end"]]
                for origin in fact["origins"])
            for event in data for fact in event.get("fact_sources", [])))

    def test_replay_speaker_quote_has_one_attributed_required_span(self):
        article_id = "b3925fddbb5a5bb92a9cc32b"
        article = self.replay_article(article_id)
        event = self.m.cluster_articles([article])[0]
        review = self.replay_source_review(event, article_id)
        unit = self.replay_rows[article_id]["evidence"]["units"][5]
        spans = [(item["start"], item["end"], item["text"])
            for item in review["unprocessed_evidence"] if item["unit_id"] == unit["unit_id"]]
        self.assertEqual(spans, [(0, 155, unit["text"][:155]),
                                 (156, 366, unit["text"][156:366])])
        self.assertNotIn("editorial question or conjecture", review["reason"])
