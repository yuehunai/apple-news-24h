"""Source-owned reporting and anaphoric comparison facts at production entry points."""

import unittest

from test_relevance_rules import article_for, load_module


class RecapComparisonOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_expected_feature_list_without_new_disclosure_stays_weak(self):
        m = self.m
        title = "'MacBook Nova' Coming Soon With Touchscreen and 5 Other Changes"
        summary = (
            "Reports and rumors suggest the next MacBook Nova could have a touchscreen. "
            "In his latest report, a reporter does not specify a release date for the first "
            "MacBook Nova models, but the wording implies it could arrive later this year. "
            "Below, we've listed the features and changes we are expecting for the MacBook Nova."
        )
        article = article_for(m, title, summary, "MacRumors",
                              ["The laptop is expected to use OLED and a touchscreen."])
        profile = m.article_reconciliation_profile(article)
        self.assertEqual(m.resolve_reconciliation_outcome(
            profile, observed_tier="", observed_reason="", observed_category="")[:1], ("weak",))
        self.assertEqual(m.cluster_articles([article])[0].relevance_tier, "weak")

        # A list format must not conceal a newly attributed hardware disclosure.
        new_report = article_for(m, title,
            "In a new report today, an analyst disclosed that Apple's next MacBook Nova "
            "will use a newly developed OLED panel. Below, we've listed the features "
            "and changes we are expecting for the MacBook Nova.", "MacRumors",
            ["The newly reported panel supports variable refresh rates."])
        new_profile = m.article_reconciliation_profile(new_report)
        self.assertEqual(m.resolve_reconciliation_outcome(
            new_profile, observed_tier="", observed_reason="", observed_category="")[:1], ("strong",))

        reported_with_background = article_for(m, title,
            "In a new report today, an analyst disclosed that Apple's next MacBook Nova "
            "will use a newly developed OLED panel. Previously reported rumors covered "
            "the laptop's touch input. Below, we've listed the expected changes.", "MacRumors",
            ["The newly reported panel supports variable refresh rates."])
        background_profile = m.article_reconciliation_profile(reported_with_background)
        self.assertEqual(m.resolve_reconciliation_outcome(
            background_profile, observed_tier="", observed_reason="", observed_category="")[:1], ("strong",))

        unrelated_report = article_for(m, title,
            summary + " Separately, a new report today revealed that an Android maker "
            "will introduce a camera tablet.", "MacRumors",
            ["The laptop is expected to use OLED and a touchscreen."])
        unrelated_profile = m.article_reconciliation_profile(unrelated_report)
        self.assertEqual(m.resolve_reconciliation_outcome(
            unrelated_profile, observed_tier="", observed_reason="", observed_category="")[:1], ("weak",))

        adjacent_report = article_for(m, title,
            "A new report today revealed that an Android maker's camera tablet "
            "will support Apple's MacBook Nova. Previously reported rumors covered "
            "the laptop's touch input. Below, we've listed the expected changes.",
            "MacRumors", ["The laptop is expected to use OLED and a touchscreen."])
        adjacent_profile = m.article_reconciliation_profile(adjacent_report)
        self.assertEqual(m.resolve_reconciliation_outcome(
            adjacent_profile, observed_tier="", observed_reason="", observed_category="")[:1], ("weak",))

        for negative_chain in ("has not", "hasn't", "hasn’t", "has never", "has not yet",
                               "cannot have", "couldn't have"):
            with self.subTest(negative_chain=negative_chain):
                unconfirmed = article_for(m, title,
                    "A new report today " + negative_chain + " confirmed that Apple's next "
                    "MacBook Nova will use a newly developed OLED panel. Previously reported "
                    "rumors covered the laptop's touch input. Below, we've listed the expected changes.",
                    "MacRumors", ["The laptop is expected to use OLED and a touchscreen."])
                unconfirmed_profile = m.article_reconciliation_profile(unconfirmed)
                self.assertEqual(m.resolve_reconciliation_outcome(
                    unconfirmed_profile, observed_tier="", observed_reason="", observed_category="")[:1], ("weak",))
                self.assertEqual(m.cluster_articles([unconfirmed])[0].relevance_tier, "weak")

    def test_external_comparison_pronoun_retains_antecedent_and_origins(self):
        from apple_news_core.models import ArticleEvidence, EvidenceUnit

        m = self.m
        title = "iPhone 18 camera gains a capture verification mode"
        owner = "苹果不是可信拍摄技术的发明者。佳能推出的照片内容凭证就是一个例子。"
        caption = "图｜佳能"
        claim = "开启功能后，相机会利用机内安全硬件为照片附上签名凭证。它采用开放标准，记录来源和后续修改。"
        own_claim = "苹果表示 iPhone 18 的传感器会签署原始像素数据。"
        article = article_for(m, title, own_claim, "少数派", [own_claim, claim])
        article.evidence = ArticleEvidence(
            article_id="comparison-owner", source=article.source, url=article.url,
            title=title, raw_lead=own_claim, content_form="news",
            units=tuple(EvidenceUnit(f"u{i}", kind, text, "html", i)
                        for i, (kind, text) in enumerate((
                            ("p", own_claim), ("p", owner), ("div", caption), ("p", claim)))),
        )
        view = m.prepare_source_fact_view(article)
        selected = [fact for fact in view.normal if claim in fact.text]
        self.assertEqual(len(selected), 1)
        fact = selected[0]
        self.assertIn("佳能", fact.text)
        self.assertEqual({origin[3] for origin in fact.origins}, {"u1", "u3"})
        self.assertEqual({(origin[3], origin[4], origin[5]) for origin in fact.origins},
                         {("u1", 0, len(owner)), ("u3", 0, len(claim))})
        event = m.cluster_articles([article])[0]
        final_text = " ".join([event.summary, *event.key_facts])
        if claim in final_text:
            self.assertIn("佳能", final_text)

        # An explicit first-party subject after the comparison resets ownership.
        apple_claim = "苹果在 iPhone 18 上开启功能后，相机会利用机内安全硬件为照片附上签名凭证。它记录来源和后续修改。"
        direct = article_for(m, title, own_claim, "少数派", [own_claim, apple_claim])
        direct.evidence = ArticleEvidence(
            article_id="comparison-owner-reset", source=direct.source, url=direct.url,
            title=title, raw_lead=own_claim, content_form="news",
            units=tuple(EvidenceUnit(f"d{i}", kind, text, "html", i)
                        for i, (kind, text) in enumerate((
                            ("p", own_claim), ("p", owner), ("div", caption), ("p", apple_claim)))),
        )
        direct_facts = [fact for fact in m.prepare_source_fact_view(direct).normal
                        if apple_claim in fact.text]
        self.assertEqual(len(direct_facts), 1)
        self.assertEqual(direct_facts[0].text, apple_claim)
        self.assertEqual({origin[3] for origin in direct_facts[0].origins}, {"d3"})


if __name__ == "__main__":
    unittest.main()
