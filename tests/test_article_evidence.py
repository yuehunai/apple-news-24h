import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/scripts/apple_news_24h.py'


def load_module():
    spec = importlib.util.spec_from_file_location('article_evidence_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ArticleEvidenceTests(unittest.TestCase):
    def test_run_keeps_short_independent_actions_as_separate_evidence_view(self):
        module = load_module()
        now = module.utc_now().isoformat()
        candidate = module.Candidate('MacRumors', 'https://www.macrumors.com/sample/', 'Apple updates Siri')
        page = f'''<html><meta property="article:published_time" content="{now}">
        <article><h1>Apple updates Siri</h1><p>Siri launches today.</p>
        <ul><li>English</li><li>French</li></ul><p>AppleCare expands.</p>
        <table><tr><th>Plan</th><th>Devices</th></tr><tr><td>Family</td><td>6</td></tr></table></article></html>'''
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), patch.object(module, 'fetch_url', return_value=page):
                result = module.run(args)
        units = [unit for record in result.get('source_evidence', {}).values() for unit in record['units']]
        self.assertTrue(units, 'Original source evidence must survive before topic/length filtering')
        texts = [unit['text'] for unit in units]
        for expected in ['English', 'French', 'AppleCare expands.', 'Family | 6']:
            self.assertIn(expected, texts)


    def test_no_paragraph_and_short_list_units_keep_structure_and_stable_ids(self):
        module = load_module()
        body = '<article>Direct text<div>One</div><ul><li>Two</li><li>Three</li></ul><table><tr><td>A</td><td>B</td></tr></table></article>'
        first = module.capture_article_evidence('Source', 'https://example.com/a', body, 'Title')
        second = module.capture_article_evidence('Source', 'https://example.com/a', body, 'Title')
        other = module.capture_article_evidence('Source', 'https://example.com/b', body, 'Title')
        self.assertEqual(first, second)
        self.assertEqual([u.text for u in first.units], ['Direct text', 'One', 'Two', 'Three', 'A | B'])
        self.assertEqual(first.units[-1].kind, 'tr')
        self.assertEqual(first.units[-1].container_id, 'table:1')
        self.assertEqual(len({u.unit_id for u in first.units}), len(first.units))
        self.assertTrue({u.unit_id for u in first.units}.isdisjoint(u.unit_id for u in other.units))
        with self.assertRaises((AttributeError, TypeError)):
            first.units[0].text = 'changed'

    def test_jsonld_keeps_whole_body_even_when_dom_only_contains_final_paragraph(self):
        module = load_module()
        body = {'@type': 'NewsArticle', 'articleBody': 'The watch runs for 50 hours.\nSiri adds five languages.\nA final paragraph.'}
        page = '<script type="application/ld+json">' + json.dumps(body) + '</script><article><p>A final paragraph.</p></article>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/a', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['The watch runs for 50 hours.', 'Siri adds five languages.', 'A final paragraph.'])
        self.assertEqual(evidence.units[0].origin, 'jsonld:articleBody')

    def test_advertising_scripts_and_related_blocks_are_not_source_units(self):
        module = load_module()
        page = '<article><p>Original action.</p><script>tracking()</script><aside>More stories</aside><div class="related"><p>Another article</p></div><p>Second action.</p></article>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/a', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['Original action.', 'Second action.'])

    def test_discovery_failure_preserves_original_lead_and_publication_origin(self):
        module = load_module()
        evidence = module.capture_article_evidence('Source', 'https://example.com/a', None, 'Original title',
            'Short original lead.', (module.PublicationEvidence('2026-09-10', 'discovery feed'),))
        self.assertEqual(evidence.extraction_path, 'discovery_fallback')
        self.assertEqual(evidence.title, 'Original title')
        self.assertEqual(evidence.raw_lead, 'Short original lead.')
        self.assertEqual(evidence.discovery_lead, 'Short original lead.')
        self.assertEqual(evidence.discovery_title, 'Original title')
        self.assertEqual(evidence.units[0].origin, 'discovery')
        self.assertIsNone(evidence.published_utc)
        self.assertEqual(evidence.publication_candidates[0].raw, '2026-09-10')

    def test_multi_action_cross_source_evidence_is_kept_before_legacy_selection(self):
        module = load_module()
        english = '<article><h1>Siri rollout</h1><p>Siri adds French and Japanese in October.</p><p>Watch audio arrives in December.</p></article>'
        chinese = '<article><h1>苹果功能分批上线</h1><p>Siri 十月新增法语、日语。</p><p>手表音频功能年底提供。</p><p>密码应用将自动修复泄露密码。</p></article>'
        records = [module.capture_article_evidence('English', 'https://example.com/en', english, ''),
                   module.capture_article_evidence('Chinese', 'https://example.com/zh', chinese, '')]
        self.assertIn('Watch audio arrives in December.', [u.text for u in records[0].units])
        self.assertIn('密码应用将自动修复泄露密码。', [u.text for u in records[1].units])
        self.assertNotEqual(records[0].article_id, records[1].article_id)
        self.assertTrue(all(u.unit_id for record in records for u in record.units))

    def test_main_body_beats_earlier_article_card_and_keeps_sibling_body_blocks(self):
        module = load_module()
        page = '<article><p>Recommended story</p></article><div class="article-body"><p>First action.</p></div><div class="article-body"><p>Second action.</p></div>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/a', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['First action.', 'Second action.'])

    def test_explicit_related_reading_heading_ends_body_without_losing_prior_short_facts(self):
        module = load_module()
        page = '<div class="post_content"><p>甲功能上线。</p><p>乙功能延期。</p><p><strong>相关阅读：</strong></p><ul><li>推荐文章</li></ul></div>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/a', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['甲功能上线。', '乙功能延期。'])

    def test_related_ancestor_is_removed_before_collecting_body_fragments(self):
        module = load_module()
        page = '<main><section class="related"><div class="article-body"><p>Apple cancels MacBook Pro.</p></div></section><div class="article-body"><p>Apple updates Siri.</p></div><div class="article-body">Short follow-up.</div></main>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/main', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['Apple updates Siri.', 'Short follow-up.'])

    def test_explicit_promo_containers_are_removed_but_nosnippet_alone_is_kept(self):
        module = load_module()
        page = '<div class="post-content"><p>First action.</p><div class="ad-disclaimer-container"><p class="disclaimer-affiliate">FTC: Affiliate disclosure.</p></div><div class="visitor-promo" data-nosnippet="true">Visit our homepage.</div><p data-nosnippet="true">Important regional limit.</p><p>Second action.</p></div>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/main', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['First action.', 'Important regional limit.', 'Second action.'])

    def test_jsonld_foreign_article_is_not_bound_to_current_page(self):
        module = load_module()
        graph = {'@graph': [
            {'@type': 'NewsArticle', 'url': 'https://example.com/main', 'articleBody': 'Apple updates Siri.'},
            {'@type': 'NewsArticle', 'url': 'https://example.com/other', 'articleBody': 'Apple cancels MacBook Pro.'}]}
        page = '<script type="application/ld+json">' + json.dumps(graph) + '</script><article><p>Apple updates Siri.</p></article>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/main', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['Apple updates Siri.'])

    def test_jsonld_ownership_respects_canonical_mainentity_and_tracking_aliases(self):
        module = load_module()
        for identity in [
            {'url': 'https://example.com/canonical?utm_source=feed'},
            {'mainEntityOfPage': 'https://example.com/canonical/'},
            {'mainEntityOfPage': {'@id': 'https://example.com/canonical#webpage'}},
            {'@id': 'https://example.com/canonical#article'},
            {}]:
            with self.subTest(identity=identity):
                node = dict(identity, **{'@type': 'NewsArticle', 'articleBody': 'Complete source body.'})
                page = '<link href="https://example.com/canonical" rel="canonical"><script type="application/ld+json">' + json.dumps(node) + '</script><article><p>Last DOM paragraph.</p></article>'
                evidence = module.capture_article_evidence('Source', 'https://example.com/amp?utm_campaign=test', page, 'Title')
                self.assertIn('Complete source body.', [u.text for u in evidence.units])

    def test_jsonld_conflicting_or_ambiguous_ownership_does_not_invent_source_binding(self):
        module = load_module()
        for nodes in [
            [{'@type': 'NewsArticle', 'url': 'https://example.com/other', 'mainEntityOfPage': 'https://example.com/main', 'articleBody': 'Conflicting body.'}],
            [{'@type': 'NewsArticle', 'articleBody': 'Unknown first body.'}, {'@type': 'NewsArticle', 'articleBody': 'Unknown second body.'}]]:
            with self.subTest(nodes=nodes):
                page = '<script type="application/ld+json">' + json.dumps({'@graph': nodes}) + '</script><article><p>Current DOM body.</p></article>'
                evidence = module.capture_article_evidence('Source', 'https://example.com/main', page, 'Title')
                self.assertEqual([u.text for u in evidence.units], ['Current DOM body.'])

    def test_jsonld_body_is_not_rescoped_to_one_nested_html_fragment(self):
        module = load_module()
        node = {'@type': 'Article', 'articleBody': '<p>First fact.</p><div class="article-body"><p>Second fact.</p></div><p>Third fact.</p>'}
        page = '<script type="application/ld+json">' + json.dumps(node) + '</script>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/main', page, 'Title')
        self.assertEqual([u.text for u in evidence.units], ['First fact.', 'Second fact.', 'Third fact.'])


if __name__ == '__main__':
    unittest.main()
