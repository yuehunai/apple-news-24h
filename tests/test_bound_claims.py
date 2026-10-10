"""End-to-end source-local action ownership, independent of legacy summaries."""
import tempfile
import unittest
from unittest.mock import patch
from test_article_evidence import load_module


class BoundClaimTests(unittest.TestCase):
    def test_run_defers_initial_outcome_until_full_source_profile(self):
        from datetime import datetime, timezone
        import json
        module = load_module()
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 9, 10, 12, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        rows = [
            ('price', 'Apple raises iPhone 18 Pro price to $1,199',
             'Apple today raised the iPhone 18 Pro starting price to $1,199, up from $1,099. The iPhone 18 Pro Max now starts at $1,299.'),
            ('security', 'Apple patches actively exploited WebKit vulnerability',
             'Apple released a security update to fix an actively exploited WebKit vulnerability. The flaw allowed attackers to execute code on iPhones when users opened malicious web content.'),
            ('opinion', 'Why I think Apple should make a round Apple Watch',
             'I think Apple should make a round Apple Watch. This is my design wish and there is no new reporting or announcement from Apple.'),
            ('roundup', 'Apple event roundup: iPhone and iPad announcements',
             'Apple announced the iPhone 18 Pro with a variable-aperture camera. Apple also announced iPad 12 with an upgraded display and longer battery life.'),
            ('family', 'Apple adds AppleCare One Family plan',
             'Apple today introduced the AppleCare One Family plan in the United States. The new plan costs $49.99 per month and covers up to six people.'),
        ]
        pages = {}
        candidates = []
        for slug, title, body in rows:
            url = 'https://www.macrumors.com/2026/09/10/public-' + slug + '/'
            payload = {'@type':'NewsArticle', 'headline':title, 'datePublished':'2026-09-10T08:00:00+00:00', 'articleBody':body}
            pages[url] = '<html><head><script type="application/ld+json">' + json.dumps(payload) + '</script></head><body><article><h1>' + title + '</h1><p>' + body + '</p></article></body></html>'
            candidates.append(module.Candidate('MacRumors', url, title))
        before = []
        original_cluster = module.cluster_articles
        def cluster(articles):
            before.extend((a.url, a.title, a.category, a.relevance_tier, a.relevance_reason, a.bound_claim is not None) for a in articles)
            return original_cluster(articles)
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone','Asia/Singapore','--cache-dir',directory])
            with patch.object(module,'datetime',Clock), patch.object(module,'collect_candidates_from_sources',return_value=candidates), \
                 patch.object(module,'fetch_url',side_effect=lambda url,*a,**k: pages[url]), \
                 patch.object(module,'choose_category',wraps=module.choose_category) as category, \
                 patch.object(module,'classify_projected_article_relevance',wraps=module.classify_projected_article_relevance) as classify, \
                 patch.object(module,'cluster_articles',side_effect=cluster):
                result = module.run(args)
        # The complete output is built before these assertions so a temporary
        # external harness can record the original same-input result for comparison.
        scaffold = module.render_brief_scaffold(result)
        self.assertTrue(result['events'])
        self.assertTrue(result['deferred_events'])
        self.assertTrue(any(not row[5] for row in before))
        self.assertEqual(category.call_count, 0)
        self.assertEqual(classify.call_count, 0)
        self.assertTrue(all(row[2:5] == ('', '', '') for row in before if not row[5]))
        sources = [source for event in result['events'] + result['deferred_events'] for source in event['sources']]
        self.assertTrue(all(source['category'] and source['relevance_tier'] and source['relevance_reason'] for source in sources))
        self.assertTrue(any(event['category'] == 'hardware_products' for event in result['events']))
        self.assertTrue(any(event['category'] == 'software_systems' for event in result['events']))
        self.assertIn('$49.99', scaffold)

    def test_os_release_fact_identities_are_lazy_and_reused_for_each_release(self):
        from unittest.mock import patch
        module = load_module()
        facts = ['Apple releases iOS 27 RC build 24A335 for developers.',
                 'Apple releases iPadOS 27 stable build 24A336 for all users.']
        for title in ['Apple announces iPhone 18', 'Apple releases iOS 27 RC']:
            with self.subTest(title=title), patch.object(module, 'title_led_identity', wraps=module.title_led_identity) as identify:
                clauses, prepared = module.source_release_projection_inputs(title, ' '.join(facts), facts)
                result = module.project_os_release_variants(title, ' '.join(facts), facts,
                    clauses=clauses, facts=prepared, fact_limit=module.MAX_KEY_FACTS)
                self.assertEqual(result, [(title, ' '.join(facts), facts)])
                self.assertEqual([call for call in identify.call_args_list if call.args[0] in facts], [])
        title = 'Apple releases iOS 27 RC; Apple releases iPadOS 27 stable'
        with patch.object(module, 'title_led_identity', wraps=module.title_led_identity) as identify:
            clauses, prepared = module.source_release_projection_inputs(title, ' '.join(facts), facts)
            result = module.project_os_release_variants(title, ' '.join(facts), facts,
                clauses=clauses, facts=prepared, fact_limit=module.MAX_KEY_FACTS)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][2], [facts[0]])
        self.assertEqual(result[1][2], [facts[1]])
        self.assertEqual(len([call for call in identify.call_args_list if call.args[0] in facts]), 2)

    def test_compound_projection_only_prepares_fact_identities_when_consumed(self):
        from unittest.mock import patch
        module = load_module()
        facts = ['Apple adds a brighter display to iPhone 18.',
                 'Apple adds a larger battery to iPhone 18.']
        cases = [
            ('Apple updates its privacy policy', 'Apple published revised privacy terms.'),
            ('Apple announces iPhone 18 and iPad 12', 'Apple announced two new products.'),
            ('Apple announces iPhone 18', 'Apple announced a new phone.'),
        ]
        for entry in (module.compound_product_action_variants, module.compound_article_variants):
            for title, summary in cases:
                with self.subTest(entry=entry.__name__, title=title), patch.object(module,
                        'title_led_identity', wraps=module.title_led_identity) as identify:
                    result = entry(title, summary, facts)
                    self.assertEqual(result, [(title, summary, facts)])
                    fact_calls = [call for call in identify.call_args_list
                                  if len(call.args) > 1 and call.args[1] in facts]
                    self.assertEqual(fact_calls, [])
        title = 'Apple cuts iPhone 18 Pro starting price and adds variable-aperture camera'
        facts = ['Apple cuts the iPhone 18 Pro starting price to $699.',
                 'Apple adds a variable-aperture camera to iPhone 18 Pro.']
        with patch.object(module, 'title_led_identity', wraps=module.title_led_identity) as identify:
            result = module.compound_product_action_variants(title, ' '.join(facts), facts)
        self.assertEqual(len(result), 2)
        self.assertEqual({fact for _, _, group in result for fact in group}, set(facts))
        self.assertTrue(all(len(group) == 1 for _, _, group in result))
        self.assertEqual(len([call for call in identify.call_args_list
                              if len(call.args) > 1 and call.args[1] in facts]), 2)

    def test_roundup_preparation_skips_discarded_items_but_keeps_real_projection(self):
        module = load_module()
        facts = ['Apple announced a new iPad Pro with an OLED screen.',
                 'Apple announced AirPods 7 with active noise cancellation.']
        for original_title, source_facts in [
            ('Apple announces iPad Pro', facts),
            ('Daily briefing: Apple announces iPad Pro', facts[:1]),
            ('Daily briefing: Apple announces iPad Pro', []),
        ]:
            with self.subTest(title=original_title, count=len(source_facts)):
                with patch.object(module, 'source_text_outcome', wraps=module.source_text_outcome) as outcome:
                    result = module.roundup_article_variants(original_title, 'iPad Pro', 'Source summary', source_facts)
                self.assertEqual(result, [('iPad Pro', 'Source summary', source_facts)])
                self.assertIs(result[0][2], source_facts)
                self.assertEqual(outcome.call_count, 0)
        with patch.object(module, 'source_text_outcome', wraps=module.source_text_outcome) as outcome:
            result = module.roundup_article_variants('Daily briefing: Apple iPad and AirPods announcements',
                                                     'Source roundup', 'Two announcements', facts)
        self.assertEqual(outcome.call_count, len(facts))
        self.assertEqual([row[1] for row in result], facts)
        self.assertEqual([row[2] for row in result], [[fact] for fact in facts])

    def test_natural_jsonld_media_caption_and_roundup_claims_have_source_dispositions(self):
        self._assert_natural_jsonld_media_caption_and_roundup_claims()

    def test_nominal_current_event_product_keeps_local_shape_and_capability(self):
        self._assert_natural_jsonld_media_caption_and_roundup_claims(
            'Apple’s “closing surprise” at this year’s product event was the iPhone Horizon — a book-shaped foldable that lies flat when opened.')

    def _assert_natural_jsonld_media_caption_and_roundup_claims(self, replacement_shape=None):
        import json
        from datetime import datetime, timezone
        module = load_module()
        from apple_news_core.article_projector import source_evidence_remainder
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 9, 10, 2, 26, 13, 593552, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        pages = {'https://verge.example/launch-summary': '<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Apple launch event: The three biggest announcements", "url": "https://verge.example/launch-summary", "datePublished": "2026-09-09T18:24:00+00:00", "articleBody": "Apple just finished its product event, presenting updates across several important device lines. We saw new phones, refreshed headphones, and changes to the company\\u2019s watch lineup.\\n\\nHere is a summary of the main announcements made during the event.\\n\\nApple\\u2019s first foldable: the iPhone Horizon\\n\\n[Image: https://images.example/event-2030-640.jpg?quality=83&strip=all]\\n\\nApple\\u2019s final reveal was the iPhone Horizon \\u2014 a book-shaped foldable that lies flat when opened. The device uses an 8.2-inch inner display and a 6.1-inch outer screen. It will support Apple Pencil later this year and has Touch ID on the side button.\\n\\nThe iPhone Horizon starts at $2199 and will go on sale November 23.\\n\\nNew AirPods add active noise cancellation\\n\\nApple announced AirPods 7 with active noise cancellation. They cost $149 and provide up to seven hours of listening.\\n\\nA new watch brings more health controls\\n\\nApple announced a new Watch with a 48-hour battery and a price of $429."}</script></head><body><article><h1>Apple launch event: The three biggest announcements</h1></article></body></html>', 'https://verge.example/mini-history': '<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "The incomplete history of Mini devices", "url": "https://verge.example/mini-history", "datePublished": "2026-09-09T18:24:00+00:00", "articleBody": "Apple announced a refreshed iPad mini today, but Mini is far from a new name for a portable device. Here are other compact devices that used the name.\\n\\nOrbit Mini\\n\\n[Image: The Orbit app store is full of tools, though most users need only a few. https://images.example/2031/248003_orbit_mini.jpg?quality=83&strip=all]\\n\\nAfter convincing its former owner to release the original software last year, Jordan Vale, the designer of a popular portable player, revived the device under a new company called Orbit Devices.\\n\\nThe Orbit Mini has a 1.8-inch screen and costs $89.\\n\\nThe Image control lets users retain captions when they export photographs."}</script></head><body><article><h1>The incomplete history of Mini devices</h1></article></body></html>'}
        if replacement_shape:
            old_shape = 'Apple’s final reveal was the iPhone Horizon — a book-shaped foldable that lies flat when opened.'
            pages = {url: page.replace(json.dumps(old_shape)[1:-1], json.dumps(replacement_shape)[1:-1])
                     for url, page in pages.items()}
        candidates = []
        for url, page in pages.items():
            ld = module.json_ld_objects(page)[0]
            candidates.append(module.Candidate('The Verge', url, ld['headline']))
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--hours', '24', '--cache-dir', directory])
            with patch.object(module, 'datetime', Clock), \
                 patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'select_detail_candidates', return_value=candidates), \
                 patch.object(module, 'fetch_detail_page_texts', side_effect=lambda selected, *args: [pages[c.url] for c in selected]):
                result = module.run(args)
        facts = [f for event in result['events'] + result['deferred_events'] for f in event['fact_sources']]
        reviews = [(item, span) for item in result['final_brief_queue'] for span in item.get('unprocessed_evidence', [])]
        self.assertTrue(facts)
        self.assertFalse(any('https://images.example/' in f['text'] for f in facts))
        self.assertFalse(any('https://images.example/' in span['text'] for _, span in reviews))
        targets = [('https://verge.example/launch-summary', 'Apple’s final reveal was the iPhone Horizon — a book-shaped foldable that lies flat when opened.'), ('https://verge.example/launch-summary', 'It will support Apple Pencil later this year and has Touch ID on the side button.'), ('https://verge.example/launch-summary', '$2199'), ('https://verge.example/launch-summary', '8.2-inch'), ('https://verge.example/mini-history', '1.8-inch')]
        if replacement_shape:
            targets[0] = (targets[0][0], replacement_shape)
        for url, target in targets:
            with self.subTest(target=target):
                matching_facts = [f for f in facts if target in f['text'] and any(o['url'] == url for o in f['origins'])]
                matching_reviews = [(q, span) for q, span in reviews if target in span['text'] and url in q.get('source_urls', [])]
                self.assertTrue(matching_facts or matching_reviews)
                if target in targets[0][1:]+targets[1][1:]:
                    self.assertIn(target, result['final_brief_markdown'])
                origins = [o for f in matching_facts for o in f['origins'] if o['url'] == url and o.get('unit_id')]
                for q, span in matching_reviews:
                    self.assertTrue(q.get('reason'))
                    origins.append(span)
                self.assertTrue(origins)
                for origin in origins:
                    evidence = next(e for e in result['source_evidence'].values() if e['url'] == url and any(u['unit_id'] == origin['unit_id'] for u in e['units']))
                    unit = next(u for u in evidence['units'] if u['unit_id'] == origin['unit_id'])
                    self.assertIn(target, unit['text'][origin['start']:origin['end']])
        history = candidates[1]
        evidence = module.capture_article_evidence(history.source, history.url, pages[history.url], history.title)
        remaining, excluded = source_evidence_remainder(evidence, ())
        units = {u.unit_id: u.text for u in evidence.units}
        caption = 'The Orbit app store is full of tools, though most users need only a few.'
        self.assertTrue(any(caption in units[key][start:end] for key, start, end in remaining))
        self.assertFalse(any('https://images.example/' in units[key][start:end] for key, start, end in remaining))
        self.assertTrue(any('https://images.example/' in units[key][start:end] for key, start, end, reason in excluded))
        self.assertTrue(any('The Image control lets users retain captions when they export photographs.' in u.text for u in evidence.units))

    def test_local_current_source_claims_keep_timing_without_crossing_topics(self):
        from test_relevance_rules import article_for
        module = load_module()
        from apple_news_core.article_processing import inline_media_marker_spans
        title = 'Apple launch event: The main product announcements'
        introduction = 'Apple today introduced a new iPad with a foldable design.'
        capability = 'It will support Apple Pencil later this year and has Touch ID on the side button.'
        for middle, keep in [('', True), ('The device uses a brighter display.', True),
                             ('Google announced a new tablet.', False),
                             ('The article then turns to a different product.', False)]:
            body = ' '.join(filter(None, (introduction, middle, capability)))
            article = article_for(module, title, body, facts=[], source='Public source')
            article.evidence = module.capture_article_evidence(article.source, article.url, '<article><p>' + body + '</p></article>', title)
            _, unresolved = module.prepare_source_condition_evidence(article)
            with self.subTest(middle=middle):
                self.assertEqual(any(f.text == capability for f in unresolved), keep)
                self.assertTrue(any(f.text == introduction for f in unresolved))
        for intro in [introduction.replace('today introduced', 'previously introduced'),
                      introduction.replace('today introduced', 'introduced in 2014'),
                      'Apple might introduce a new iPad with a foldable design.',
                      'Apple believes beautiful design can change the world.']:
            body = intro + ' ' + capability
            article = article_for(module, title, body, facts=[], source='Public source')
            article.evidence = module.capture_article_evidence(article.source, article.url, '<article><p>' + body + '</p></article>', title)
            _, unresolved = module.prepare_source_condition_evidence(article)
            with self.subTest(intro=intro):
                self.assertFalse(any(f.text in (intro, capability) for f in unresolved))
        for text in ['The Image control preserves captions at https://support.example/image.',
                     'Tags and Comments remain available for shared photographs.',
                     '[Image: not a resource address]']:
            self.assertEqual(module.clean_fact_text(text), text)
            self.assertFalse(inline_media_marker_spans(text))

    def test_nominal_current_source_scope_requires_current_event_and_product(self):
        from test_relevance_rules import article_for
        module = load_module()
        title = 'Apple launch event: The main product announcements'
        nominal = 'Apple’s “closing surprise” at this year’s product event was the iPhone Horizon — a book-shaped foldable that lies flat when opened.'
        capability = 'It will support Apple Pencil later this year and has Touch ID on the side button.'
        controls = [(nominal, True),
            (nominal.replace('“closing surprise”', 'newest device'), True),
            (nominal.replace('“closing surprise”', 'unexpected introduction').replace('this year’s product event', 'today’s launch event'), True),
            (nominal.replace('this year’s', 'last year’s'), False),
            (nominal.replace('was the', 'could be the'), False),
            (nominal.replace('was the', 'was not the'), False),
            (nominal.replace('Apple’s', 'Samsung’s'), False),
            (nominal.replace('the iPhone Horizon', 'a Samsung tablet compared with iPad'), False),
            (nominal.replace('at this year’s product event', 'in this year’s industry commentary'), False),
            (nominal.replace('a book-shaped foldable that lies flat when opened', 'an inspiring experience that changes everything'), False)]
        for introduction, expected in controls:
            for separator in ['', 'Google announced a different tablet.']:
                text = ' '.join(filter(None, [introduction, separator, capability]))
                article = article_for(module, title, text, source='Public source', facts=[])
                article.evidence = module.capture_article_evidence(article.source, article.url,
                    '<article><p>' + text + '</p></article>', title)
                _, unresolved = module.prepare_source_condition_evidence(article)
                with self.subTest(introduction=introduction, separator=separator):
                    self.assertEqual(any(f.text == introduction for f in unresolved), expected)
                    self.assertEqual(any(f.text == capability for f in unresolved), expected and not separator)

    def _current_remainder_public_pages(self):
        return {'https://news.example/current-launch': '<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Apple announces iPhone 18 Pro", "url": "https://news.example/current-launch", "datePublished": "2026-09-09T18:24:00+00:00", "articleBody": "Apple today unveiled the iPhone 18 Pro and iPhone 18 Pro Max, which have improved cameras and larger batteries.\\n\\nThe new screen supports a refresh rate of 120Hz. Pre-orders start Friday, with deliveries beginning September 25.\\n\\nBoth new devices have updated cooling systems for sustained performance."}</script></head><body><article><h1>Apple announces iPhone 18 Pro</h1></article></body></html>', 'https://news.example/current-support': '<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "New iPad Pro supports Apple Pencil with USB-C", "url": "https://news.example/current-support", "datePublished": "2026-09-09T18:24:00+00:00", "articleBody": "The new iPad Pro supports Apple Pencil with USB-C on its display. The stylus pairs over a cable and provides basic drawing controls.\\n\\nApple introduced the Apple Pencil with USB-C after announcing an iPad with a landscape front camera. The old camera arrangement prevented the magnets used by the previous stylus from fitting.\\n\\nApple introduced Camera Control with the iPhone 16, and all iPhones released since then have included the feature. On the new iPad, the reader can instead open the camera from the lock screen.\\n\\nThe iPad Pro starts at $1099 and ships September 25."}</script></head><body><article><h1>New iPad Pro supports Apple Pencil with USB-C</h1></article></body></html>', 'https://news.example/launch-roundup': '<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Apple launch event: The three biggest announcements", "url": "https://news.example/launch-roundup", "datePublished": "2026-09-09T18:24:00+00:00", "articleBody": "Apple just finished its product event, presenting new phones and watches.\\n\\nApple\\u2019s new foldable\\n\\nApple\\u2019s \\u201cclosing surprise\\u201d at this year\\u2019s product event was the iPhone Horizon \\u2014 a book-shaped foldable that lies flat when opened. The device uses an 8.2-inch inner display and a 6.1-inch outer screen. It will support Apple Pencil later this year and has Touch ID on the side button.\\n\\nThe iPhone Horizon starts at $2199 and will go on sale November 23."}</script></head><body><article><h1>Apple launch event: The three biggest announcements</h1></article></body></html>'}

    def test_historical_introductions_do_not_become_current_roundup_requirements(self):
        from datetime import datetime, timezone
        module = load_module()
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 9, 10, 2, 26, 13, 593552, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        pages = self._current_remainder_public_pages()
        candidates = [module.Candidate('The Verge', url, module.json_ld_objects(page)[0]['headline']) for url, page in pages.items()]
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--hours', '24', '--cache-dir', directory])
            with patch.object(module, 'datetime', Clock), \
                 patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'select_detail_candidates', return_value=candidates), \
                 patch.object(module, 'fetch_detail_page_texts', side_effect=lambda selected, *args: [pages[c.url] for c in selected]):
                result = module.run(args)
        reviews = [(q, span) for q in result['final_brief_queue'] for span in q.get('unprocessed_evidence', [])]
        historical = ['Apple introduced the Apple Pencil with USB-C after announcing an iPad with a landscape front camera.',
                      'Apple introduced Camera Control with the iPhone 16, and all iPhones released since then have included the feature.']
        source = next(e for e in result['source_evidence'].values() if e['url'] == 'https://news.example/current-support')
        for text in historical:
            with self.subTest(text=text):
                self.assertTrue(any(text in u['text'] for u in source['units']))
                self.assertFalse(any(text in span['text'] for q, span in reviews))
        for text in ['Apple’s “closing surprise” at this year’s product event was the iPhone Horizon — a book-shaped foldable that lies flat when opened.',
                     'It will support Apple Pencil later this year and has Touch ID on the side button.']:
            matches = [(q, span) for q, span in reviews if text in span['text'] and 'https://news.example/launch-roundup' in q['source_urls']]
            self.assertTrue(matches)
            self.assertIn(text, result['final_brief_markdown'])
            for q, span in matches:
                evidence = next(e for e in result['source_evidence'].values() if e['url'] == 'https://news.example/launch-roundup')
                unit = next(u for u in evidence['units'] if u['unit_id'] == span['unit_id'])
                self.assertEqual(unit['text'][span['start']:span['end']], span['text'])
        current = 'Apple today unveiled the iPhone 18 Pro and iPhone 18 Pro Max, which have improved cameras and larger batteries.'
        facts = [f for e in result['events'] + result['deferred_events'] for f in e['fact_sources']]
        self.assertTrue(any(current == f['text'] for f in facts))
        self.assertFalse(any(current == span['text'] for q, span in reviews))

    def test_prepared_unprocessed_fact_is_consumed_only_by_same_source_span(self):
        from test_relevance_rules import article_for
        from dataclasses import replace
        module = load_module()
        from apple_news_core.models import PreparedFact
        current = 'Apple today unveiled the iPhone 18 Pro and iPhone 18 Pro Max, which have improved cameras and larger batteries.'
        article = article_for(module, 'Apple announces iPhone 18 Pro', current, source='The Verge', facts=[current])
        article.url = 'https://news.example/current-launch'
        page = self._current_remainder_public_pages()[article.url]
        article.evidence = module.capture_article_evidence(article.source, article.url, page, article.title)
        view = module.prepare_source_fact_view(article)
        plan = module.resolve_event_fact_plan([view], relevance_tier='strong', base_limit=6, official_limit=6)
        self.assertTrue(any(f.text == current for f in plan.facts))
        self.assertTrue(any(f.text == current and any(o[3] for o in f.origins) for f in view.unprocessed))
        self.assertFalse(any(f.text == current for f in plan.unprocessed))
        original = next(f for f in view.unprocessed if f.text == current)
        text_only = tuple((o[0], o[1], o[2], '', 0, 0) for o in next(f for f in plan.facts if f.text == current).origins)
        text_only_view = replace(view, normal=tuple(replace(f, origins=text_only) if f.text == current else f for f in view.normal))
        text_only_plan = module.resolve_event_fact_plan([text_only_view], relevance_tier='strong', base_limit=6, official_limit=6)
        self.assertTrue(any(f.text == current and f.origins == text_only for f in text_only_plan.facts))
        self.assertFalse(any(f.text == current for f in text_only_plan.unprocessed))
        for text, origins in [
            (current, ()),
            (current.replace('larger batteries', 'smaller batteries'), original.origins),
            (current + ' Only selected markets qualify.', original.origins),
            (current, tuple((o[0], 'https://other.example/current-launch', 'other', *o[3:]) for o in original.origins)),
            (current, tuple((*o[:3], 'other-unit', *o[4:]) for o in original.origins)),
            (current, ((article.source, 'https://other.example/current-launch', 'other', '', 0, 0),)),
        ]:
            pending = PreparedFact(text, text.casefold(), origins=origins)
            control = replace(view, unprocessed=(pending,))
            cp = module.resolve_event_fact_plan([control], relevance_tier='strong', base_limit=6, official_limit=6)
            with self.subTest(text=text, origins=origins):
                self.assertTrue(any(f.text == text and f.origins == origins for f in cp.unprocessed))

    def test_relative_intro_chronology_keeps_current_title_and_local_time(self):
        from test_relevance_rules import article_for
        module = load_module()
        current = 'Apple introduced the new iPad Pro after announcing an updated display panel.'
        history = 'Apple introduced Camera Control with the iPhone 16, and all iPhones released since then have included the feature.'
        for title, text, expected in [
            ('Apple announces new iPad Pro', current, True),
            ('New iPad Pro supports Apple Pencil', current.replace('Apple introduced', 'Apple today introduced'), True),
            ('New iPad Pro supports Apple Pencil', current, False),
            ('Apple announces new iPad Pro', current.replace('new iPad Pro', 'Apple Pencil'), False),
            ('Apple announces iPhone 18 Pro', history, False),
            ('Apple announces new iPad Pro', current.replace('introduced', 'previously introduced'), False),
            ('Apple announces new iPad Pro', current.replace('introduced', 'might introduce'), False),
        ]:
            article = article_for(module, title, text, source='Public source', facts=[])
            article.evidence = module.capture_article_evidence(article.source, article.url, '<article><p>' + text + '</p></article>', title)
            _, unresolved = module.prepare_source_condition_evidence(article)
            with self.subTest(title=title, text=text):
                self.assertEqual(any(f.text == text for f in unresolved), expected)

    def test_editorial_byline_and_empty_intro_keep_publication_and_conditions(self):
        from datetime import datetime, timezone
        module = load_module()
        pages = {'https://tech.example/support-limits': '<html><head><meta property="article:published_time" content="2026-09-09T12:14:00-07:00"></head><body class="news layout-no-footer-desktop-970"><article><h1>Apple publishes new Apple Intelligence usage limits</h1><div class="byline--news"><time datetime="2026-09-09T12:14:00-07:00">Wednesday September 9, 2026 12:14 pm PDT</time> by <a rel="author" href="https://tech.example/author/jordan">Jordan Reed</a></div><div class="content--news js-content"><p class="wp-block-paragraph">Apple today published a new support article explaining Apple Intelligence usage limits. Here’s what the company says.</p><p>Apple says the limits apply only to selected accounts, beginning November 19.</p><p>On November 19, Apple will restore access for eligible accounts, as explained by its support team.</p><ul><li>Image Playground</li><li>Intelligent Photo Editing</li></ul></div></article></body></html>', 'https://rumors.example/family-plan': '<html><head><meta property="article:published_time" content="2026-09-09T12:14:00-07:00"></head><body class="news layout-no-footer-desktop-970"><article><h1>Apple announces AppleCare One Family for four people</h1><div class="byline--news"><time datetime="2026-09-09T12:14:00-07:00">Wednesday September 9, 2026 12:14 pm PDT</time> by <a rel="author" href="https://tech.example/author/jordan">Jordan Reed</a></div><div class="content--news js-content"><p class="wp-block-paragraph">Apple today announced AppleCare One Family for four people at $39.99 per month. </p><p>The plan covers four claims per year and launches November 19.</p><p>Apple says most devices less than four years old remain eligible.</p></div></article></body></html>'}
        expected_publication = {'https://tech.example/support-limits': [{'raw': '2026-09-09T12:14:00-07:00', 'source': 'meta published', 'allows_date_only': False}, {'raw': '2026-09-09T12:14:00-07:00', 'source': 'time datetime', 'allows_date_only': False}, {'raw': 'Wednesday September 9, 2026 12:14 pm PDT', 'source': 'time text', 'allows_date_only': False}, {'raw': 'September 9, 2026 12:14 pm PDT', 'source': 'body date pattern', 'allows_date_only': False}], 'https://rumors.example/family-plan': [{'raw': '2026-09-09T12:14:00-07:00', 'source': 'meta published', 'allows_date_only': False}, {'raw': '2026-09-09T12:14:00-07:00', 'source': 'time datetime', 'allows_date_only': False}, {'raw': 'Wednesday September 9, 2026 12:14 pm PDT', 'source': 'time text', 'allows_date_only': False}, {'raw': 'September 9, 2026 12:14 pm PDT', 'source': 'body date pattern', 'allows_date_only': False}]}
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 9, 10, 2, 26, 13, 593552, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        rows = [('9to5Mac', 'https://tech.example/support-limits', 'Apple publishes new Apple Intelligence usage limits'), ('MacRumors', 'https://rumors.example/family-plan', 'Apple announces AppleCare One Family for four people')]
        candidates = [module.Candidate(*row) for row in rows]
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'datetime', Clock), \
                 patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'select_detail_candidates', return_value=candidates), \
                 patch.object(module, 'fetch_detail_page_texts', side_effect=lambda rows, *args: [pages[row.url] for row in rows]):
                result = module.run(args)
        facts = [fact['text'] for event in result['events'] + result['deferred_events'] for fact in event['fact_sources']]
        reviews = [span['text'] for item in result['final_brief_queue'] for span in item.get('unprocessed_evidence', [])]
        for text in ['Wednesday September 9, 2026 12:14 pm PDT by Jordan Reed', 'Here’s what the company says.']:
            with self.subTest(metadata=text):
                self.assertFalse(any(text in value for value in facts + reviews))
        expected = ['Apple says the limits apply only to selected accounts, beginning November 19.', 'On November 19, Apple will restore access for eligible accounts, as explained by its support team.', 'Image Playground', 'Intelligent Photo Editing', 'The plan covers four claims per year and launches November 19.', 'Apple says most devices less than four years old remain eligible.']
        for text in expected:
            with self.subTest(required=text):
                self.assertTrue(any(text in value for value in facts + reviews))
                self.assertIn(text, module.render_brief_scaffold(result))
        evidence = list(result['source_evidence'].values())
        self.assertEqual({ev['url']: list(ev['publication_candidates']) for ev in evidence}, expected_publication)
        self.assertTrue(any('Here’s what the company says.' in unit['text'] for ev in evidence for unit in ev['units']))
        # A normal body sentence with an author attribution/date is not a
        # byline just because it mentions the same words or person.
        body = '<article><p>On November 19, Apple will restore access for eligible accounts, as explained by Jordan Reed.</p></article>'
        captured = module.capture_article_evidence('9to5Mac', 'https://tech.example/body-date', body, 'Apple restores access')
        self.assertTrue(any('as explained by Jordan Reed' in unit.text for unit in captured.units))

    def test_complete_template_context_excludes_local_metadata_not_body(self):
        from datetime import datetime, timezone
        module = load_module()
        from apple_news_core.article_projector import source_evidence_remainder
        pages = {'https://news.example/language': '<html><head><meta property="article:published_time" content="2026-09-09T20:00:00+00:00"></head><body><article><h1>Apple confirms Siri language expansion</h1><p class="wp-block-paragraph">Apple today confirmed Siri will add three languages in November. Here are the details.</p><ul><li>Finnish</li><li>Polish</li><li>Czech</li></ul><p class="wp-block-paragraph">For Tech Daily’s full coverage of Apple’s “Radiant Horizon” event,&nbsp;<a href="https://news.example/event-hub">follow this link</a>.</p><p>Apple says the Image control preserves original sensor data and Comments mode exports reader notes.</p></article></body></html>', 'https://watch.example/new-model': '<html><head><meta property="article:published_time" content="2026-09-09T20:00:00+00:00"></head><body><article><h1>Apple announces Watch Ultra 7</h1><p>Apple today announced Watch Ultra 7 with a new health control, available September 21 for $899.</p><div class="duet--media--caption"><cite class="duet--article--dangerously-set-cms-markup">Image: Apple</cite></div><p>The Image control preserves original sensor data and Tags mode exports all labels.</p></article></body></html>', 'https://tech.example/plan': '<html><head><meta property="article:published_time" content="2026-09-09T20:00:00+00:00"></head><body><article><h1>苹果发布 AppleCare Family 家庭保障计划</h1><div class="post_content" id="paragraph"><div class="tougao-user">感谢科技报网友 <a href="https://tech.example/profile">晨光</a> 的线索投递！</div><p>苹果今日宣布 AppleCare Family 覆盖四位家庭成员，月费39.99美元，每年四次理赔，9月14日开售。</p><p style="text-align:center;"><a class="topic-bar" href="https://tech.example/event">2026 苹果秋季新品发布会专题</a></p><p>正文中的 Tags、Comments 和 Image 都是新控制项的正式名称，用户可保留图片说明。</p></div></article></body></html>'}
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 9, 10, 2, 26, 13, 593552, tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        rows = [('9to5Mac', 'https://news.example/language', 'Apple confirms Siri language expansion'), ('The Verge', 'https://watch.example/new-model', 'Apple announces Watch Ultra 7'), ('IT之家', 'https://tech.example/plan', '苹果发布 AppleCare Family 家庭保障计划')]
        candidates = [module.Candidate(*row) for row in rows]
        markers = ['Here are the details.', 'follow this link', 'Image: Apple', '线索投递', '新品发布会专题']
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'datetime', Clock), \
                 patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'select_detail_candidates', return_value=candidates), \
                 patch.object(module, 'fetch_detail_page_texts', side_effect=lambda rows, *args: [pages[row.url] for row in rows]):
                result = module.run(args)
        facts = [fact['text'] for event in result['events'] + result['deferred_events'] for fact in event['fact_sources']]
        reviews = [span['text'] for item in result['final_brief_queue'] for span in item.get('unprocessed_evidence', [])]
        for marker in markers:
            with self.subTest(final_marker=marker):
                self.assertFalse(any(marker in text for text in facts + reviews))
        for candidate in candidates:
            ev = module.capture_article_evidence(candidate.source, candidate.url, pages[candidate.url], candidate.title)
            remaining, excluded = source_evidence_remainder(ev, ())
            units = {u.unit_id: u.text for u in ev.units}
            text = [units[key][start:end] for key, start, end in remaining]
            with self.subTest(remainder=candidate.url):
                self.assertFalse(any(marker in value for marker in markers for value in text))
                self.assertTrue(any('Image' in value for value in text))
            if candidate.url.endswith('language'):
                self.assertIn('Apple today confirmed Siri will add three languages in November.', text)
                for language in ['Finnish', 'Polish', 'Czech']:
                    self.assertIn(language, text)
                    self.assertIn(language, module.render_brief_scaffold(result))
                self.assertTrue(any(units[key][start:end] == 'Here are the details.' for key, start, end, reason in excluded))
            elif candidate.url.endswith('new-model'):
                self.assertTrue(any('September 21 for $899' in value for value in text))
            else:
                self.assertTrue(any('39.99' in value and '四次理赔' in value for value in text))
        caption = '<article><p>Apple introduces a camera control.</p><div class="duet--media--caption"><span>The Image control preserves all 48 MP data.</span><cite>Image: Apple</cite></div></article>'
        captured = module.capture_article_evidence('The Verge', 'https://watch.example/caption', caption, 'Apple introduces camera control')
        self.assertTrue(any('all 48 MP data' in unit.text for unit in captured.units))
        self.assertFalse(any('Image: Apple' in unit.text for unit in captured.units))

    def test_layout_no_footer_marker_keeps_body_and_real_template_exclusions(self):
        module = load_module()
        pages = {'ordinary': '<html><head><meta property="article:published_time" content="2026-09-09T20:00:00+00:00"></head><body><article><h1>Apple announces AppleCare One Family for four people</h1><p>Apple today announced AppleCare One Family for four people at $39.99 per month.</p><p>The plan includes four claims per year and launches September 21.</p><div class="linkback">Tags: <a href="https://rumors.example/guide">AppleCare One Guide</a></div><div class="footer--new"><p>37 comments</p></div></article></body></html>', 'layout-marker': '<html><head><meta property="article:published_time" content="2026-09-09T20:00:00+00:00"></head><body class="news layout-no-footer-desktop-970"><article><h1>Apple announces AppleCare One Family for four people</h1><p>Apple today announced AppleCare One Family for four people at $39.99 per month.</p><p>The plan includes four claims per year and launches September 21.</p><div class="linkback">Tags: <a href="https://rumors.example/guide">AppleCare One Guide</a></div><div class="footer--new"><p>37 comments</p></div></article></body></html>'}
        units = {label: [u.text for u in module.capture_article_evidence('MacRumors', 'https://rumors.example/layout', page, 'Apple announces AppleCare One Family for four people').units] for label, page in pages.items()}
        self.assertEqual(units['ordinary'], units['layout-marker'])
        self.assertEqual(len(units['ordinary']), 3)
        self.assertTrue(any('$39.99' in text for text in units['layout-marker']))
        self.assertFalse(any('Tags:' in text or '37 comments' in text for text in units['layout-marker']))
        # The restored body must remain attributable in the final output,
        # not merely recover a nonempty parser unit list.
        outcomes = []
        for label, page in pages.items():
            candidate = module.Candidate('MacRumors', 'https://rumors.example/layout', 'Apple announces AppleCare One Family for four people')
            page = page.replace('2026-09-09T20:00:00+00:00', module.utc_now().isoformat())
            with tempfile.TemporaryDirectory() as directory:
                args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
                with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), \
                     patch.object(module, 'select_detail_candidates', return_value=[candidate]), \
                     patch.object(module, 'fetch_detail_page_texts', return_value=[page]):
                    result = module.run(args)
            facts = [fact for event in result['events'] + result['deferred_events'] for fact in event['fact_sources']]
            self.assertTrue(facts, label)
            outcomes.append(sorted(fact['text'] for fact in facts))
            for token in ['$39.99', 'four claims per year', 'September 21']:
                matches = [fact for fact in facts if token in fact['text']]
                self.assertTrue(matches, (label, token))
                for fact in matches:
                    self.assertTrue(fact['origins'])
                    self.assertTrue(all(origin['url'] == candidate.url for origin in fact['origins']))
                self.assertIn(token, module.render_brief_scaffold(result))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_reported_formal_naming_remains_attributed_before_future_launch(self):
        from test_relevance_rules import article_for
        module = load_module()
        rows = [{'label': 'reported', 'title': 'Report: Apple foldable will be called iPhone Horizon', 'lead': 'Reporter Alex Lane claims Apple’s upcoming foldable will be called iPhone Horizon and arrive in November.'}, {'label': 'supply', 'title': 'iPhone Horizon还没开卖就引发关注：首批备货有限', 'lead': '据科技博主亚历克斯爆料，苹果首款折叠手机正式定名为iPhone Horizon，256GB入门版定价2300美元，预计11月上市，提供银色和绿色两款配色。博主周岚透露，iPhone Horizon将与其他新品一同亮相，但上市时间会有所延后。'}, {'label': 'formal', 'title': 'Apple announces foldable iPhone Horizon', 'lead': 'Apple today revealed its first foldable iPhone, called iPhone Horizon. Customers can buy it in November.'}, {'label': 'reading', 'title': 'iPhone Horizon怎么读：苹果折叠屏名称引起讨论', 'lead': '科技博主亚历克斯发文称，苹果公司即将推出的折叠屏手机名叫iPhone Horizon，新品将在11月上市。虽然新品尚未发布，但名字率先引起了讨论。'}]
        articles = [article_for(module, row['title'], row['lead'], source=row['label'], facts=[row['lead']]) for row in rows]
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        self.assertIn('product-disclosure-stage:reported', profiles[1].separation_keys)
        for i, j, decision in [(0, 1, 'match'), (1, 2, 'conflict'), (0, 2, 'conflict'), (0, 3, 'match'), (1, 3, 'match'), (2, 3, 'conflict')]:
            with self.subTest(pair=(i, j)):
                self.assertEqual(module.profile_pair_decision(profiles[i], profiles[j]), decision)
        self.assertEqual(sorted(sorted(a.source for a in e.articles) for e in module.cluster_articles(articles)), [['formal'], ['reading', 'reported', 'supply']])

    def test_same_source_chinese_paragraph_formatting_preserves_distinct_qualifications(self):
        module = load_module()
        from apple_news_core.models import PreparedFact, SourceFactView
        rows = [{'raw_response': '据科技报此前报道，7 月 13 日，星海首款 AI 旗舰 SoC 云峰 Z5 正式发布， 行业首发支持 DDR7 。7 月 18 日， 星海官宣 Starsea 23 Fold 全球首发远峰 DDR7 内存 。', 'located_fact': '据科技报此前报道，7 月 13 日，星海首款 AI 旗舰 SoC 云峰 Z5 正式发布，行业首发支持 DDR7。7 月 18 日，星海官宣 Starsea 23 Fold 全球首发远峰 DDR7 内存。'}, {'raw_response': '关于 DDR7 明年能否量产，周岚表示 DDR 系列产品是公司重要的产品线之一，公司在该领域持续投入研发，产品性能与可靠性不断提升， 已具备与国际主流厂商同台竞争的能力 。此次 DDR7 首发，是公司于区域科技产业链伙伴协同创新的代表性成果。公司将秉持开放合作的态度，与产业链伙伴携手，持续为客户和消费者创造价值。关于量产安排及盈利贡献等信息，请以公司公开披露的信息为准。', 'located_fact': '关于 DDR7 明年能否量产，周岚表示 DDR 系列产品是公司重要的产品线之一，公司在该领域持续投入研发，产品性能与可靠性不断提升，已具备与国际主流厂商同台竞争的能力。此次 DDR7 首发，是公司于区域科技产业链伙伴协同创新的代表性成果。公司将秉持开放合作的态度，与产业链伙伴携手，持续为客户和消费者创造价值。关于量产安排及盈利贡献等信息，请以公司公开披露的信息为准。'}]
        qualified = '公司产品在质量和供应稳定性方面已具备竞争能力，本合作的客户信息及商业合作细节请以公开披露的信息为准。'
        for i, row in enumerate(rows):
            raw, text = row['raw_response'], row['located_fact']
            source, url = 'Supplier source', 'https://supplier.example/reply-' + str(i)
            ev = module.capture_article_evidence(source, url, '<article><p>' + text + '</p><p>' + qualified + '</p></article>', '供应商回应客户合作询问')
            def located(value):
                unit = next(u for u in ev.units if u.text == value)
                return PreparedFact(value, value.casefold(), origins=((source, url, ev.article_id, unit.unit_id, 0, len(value)),))
            def pending(value, target_url=url):
                return PreparedFact(value, value.casefold(), origins=((source, target_url, ev.article_id if target_url == url else 'another-id', '', 0, 0),))
            def plan(value):
                view = SourceFactView(source, url, 1, module.utc_now(), False, 3, False, normal=(located(text),), responses=(value, located(qualified)))
                return module.resolve_event_fact_plan([view], relevance_tier='strong', base_limit=1, official_limit=1)
            with self.subTest(row=i):
                result = plan(pending(raw))
                self.assertFalse(any(f.text == raw for f in result.unprocessed))
                self.assertTrue(any(f.text == qualified for f in (*result.facts, *result.required, *result.unprocessed)))
            for value, target_url in [(raw.replace('DDR7', 'DDR8'), url), (raw.replace('正式发布', '尚未发布') if i == 0 else raw.replace('已具备', '尚未具备'), url), (raw + '仅适用于通过验证的客户。', url), (raw, 'https://other.example/reply')]:
                with self.subTest(row=i, value=value, url=target_url):
                    fact = pending(value, target_url)
                    self.assertTrue(any(f.text == fact.text and f.origins == fact.origins for f in plan(fact).unprocessed))

    def test_template_labels_comments_and_credit_do_not_replace_body_facts(self):
        module = load_module()
        title = 'Apple announces AppleCare One Family plan for four people'
        lead = 'Apple today announced AppleCare One Family, a new plan covering four people for $39.99 per month.'
        condition = 'The plan includes four claims per year and launches September 14.'
        meaningful = 'The Tags control supports 4 labels, and the Comments control supports 20 shared notes.'
        metadata = ['Tags: AppleCare One Guide', '37 comments', 'Image: Apple']
        body = '<p>' + lead + '</p><p>' + condition + '</p><p>' + meaningful + '</p>'
        page = '<html><head><meta property="article:published_time" content="' + module.utc_now().isoformat() + '"></head><article><h1>' + title + '</h1><div class="content--new js-content">' + body + '<div class="linkback">Tags: <a href="https://support.example/guide">AppleCare One Guide</a></div></div><div class="footer--new"><div>[ <a href="https://forum.example/comments">37 comments</a> ]</div><cite>Image: Apple</cite></div></article></html>'
        candidate = module.Candidate('MacRumors', 'https://rumors.example/metadata-controls', title)
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), \
                 patch.object(module, 'select_detail_candidates', return_value=[candidate]), \
                 patch.object(module, 'fetch_detail_page_texts', return_value=[page]):
                result = module.run(args)
        facts = [fact['text'] for event in result['events'] + result['deferred_events'] for fact in event['fact_sources']]
        reviews = [span['text'] for item in result['final_brief_queue'] for span in item.get('unprocessed_evidence', [])]
        self.assertTrue(facts)
        for noise in metadata:
            self.assertFalse(any(noise in text for text in facts + reviews), noise)
        for fact in [condition, meaningful]:
            self.assertTrue(any(fact in text for text in facts + reviews), fact)
            self.assertIn(fact, module.render_brief_scaffold(result))

    def test_source_disclosure_relationships_keep_model_period_and_action_boundaries(self):
        from test_relevance_rules import article_for
        module = load_module()
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, facts=[lead]))
        title = 'iPhone 22 Pro Max leak points to variable aperture and Sony IMX999 camera'
        lead = 'A leaked diagnostic file identifies the IMX999 main camera and variable aperture hardware.'
        source = profile(title, lead)
        key = 'primary-claim:iphone-22-pro-max:diagnostic-camera-disclosure:imx999'
        self.assertIn(key, source.event_keys)
        for other_title, other_lead in [
            (title.replace('Pro Max', 'Pro'), lead),
            (title.replace('IMX999', 'IMX998'), lead.replace('IMX999', 'IMX998')),
            ('Apple previews the iPhone 22 Pro Max camera before launch', 'Apple has not revealed camera specifications. ' + lead),
            (title, 'A leaked diagnostic file for the iPhone 21 Pro Max identifies the IMX999 main camera and variable aperture hardware.'),
        ]:
            with self.subTest(disclosure=(other_title, other_lead)):
                other = profile(other_title, other_lead)
                self.assertNotIn(key, other.event_keys)
                self.assertNotEqual(module.profile_pair_decision(source, other), 'match')
        anniversary_title = 'What the 25th anniversary iPhone is expected to look like'
        anniversary_lead = "Apple's 25th anniversary iPhone is expected to arrive in the fall of 2032 with a significant design overhaul."
        source = profile(anniversary_title, anniversary_lead)
        key = 'primary-claim:iphone-anniversary-25:design-launch-planning:2032'
        self.assertIn(key, source.event_keys)
        for other_title, other_lead in [
            (anniversary_title, anniversary_lead.replace('2032', '2033')),
            ('Apple announces the 25th anniversary iPhone', "Apple today unveiled the 25th anniversary iPhone with its new design. It will arrive in the fall of 2032."),
            (anniversary_title, 'Samsung announced a new foldable today. ' + anniversary_lead),
        ]:
            with self.subTest(anniversary=(other_title, other_lead)):
                other = profile(other_title, other_lead)
                self.assertNotIn(key, other.event_keys)
                self.assertNotEqual(module.profile_pair_decision(source, other), 'match')
        camera = profile('Apple event invitation hints at two iPhone 22 features',
                         'The invitation may hint at a variable-aperture camera and a blue finish.')
        screen = profile('Apple event invitation hints at two iPhone 22 features',
                         'The invitation may hint at an OLED display and faster charging.')
        self.assertNotEqual(module.profile_pair_decision(camera, screen), 'match')

    def test_inline_media_marker_preserves_real_launch_fact_and_raw_exclusion(self):
        import json
        import html as html_module
        module = load_module()
        from apple_news_core.article_projector import source_evidence_remainder
        title = 'Apple announces Watch Ultra 7 with new health controls'
        marker = '[Image: https://images.example/watch.jpg?quality=82&strip=all]'
        launch = 'The watch launches September 21 and starts at $899.'
        meaningful = 'The Image control shows four capture modes without changing the original sensor data.'
        lead = 'Apple today announced Watch Ultra 7 with a new health control.'
        body = '\n\n'.join([lead, marker, launch, meaningful])
        stamp = module.utc_now().isoformat()
        ld = {'@context': 'https://schema.org', '@type': 'NewsArticle', 'headline': title,
              'articleBody': body, 'datePublished': stamp}
        page = '<html><head><script type="application/ld+json">' + json.dumps(ld) + '</script></head><article><h1>' + title + '</h1><p>' + lead + '</p></article></html>'
        candidate = module.Candidate('The Verge', 'https://verge.example/watch-marker', title)
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), \
                 patch.object(module, 'select_detail_candidates', return_value=[candidate]), \
                 patch.object(module, 'fetch_detail_page_texts', return_value=[page]):
                result = module.run(args)
        facts = [fact for event in result['events'] + result['deferred_events'] for fact in event['fact_sources']]
        reviews = [span['text'] for item in result['final_brief_queue'] for span in item.get('unprocessed_evidence', [])]
        self.assertTrue(facts)
        self.assertFalse(any(marker in f['text'] or 'quality=82' in f['text'] for f in facts))
        self.assertFalse(any('[Image:' in text or 'quality=82' in text for text in reviews))
        self.assertTrue(any(launch in f['text'] for f in facts))
        self.assertIn(launch, module.render_brief_scaffold(result))
        self.assertTrue(any(meaningful in unit['text'] for evidence in result['source_evidence'].values() for unit in evidence['units']))
        for html in ['<article><p>' + html_module.escape(marker) + '</p><p>' + launch + '</p></article>',
                     '<article><p>' + html_module.escape(marker) + ' ' + launch + '</p></article>']:
            evidence = module.capture_article_evidence(candidate.source, candidate.url, html, title)
            remaining, excluded = source_evidence_remainder(evidence, ())
            units = {unit.unit_id: unit.text for unit in evidence.units}
            self.assertTrue(any(units[key][start:end] == marker for key, start, end, reason in excluded))
            self.assertTrue(any(launch == units[key][start:end] for key, start, end in remaining))
            self.assertFalse(any('[Image:' in units[key][start:end] or 'quality=82' in units[key][start:end]
                                 for key, start, end in remaining))
        prose = module.capture_article_evidence(candidate.source, candidate.url, '<article><p>' + meaningful + '</p></article>', title)
        retained, excluded = source_evidence_remainder(prose, ())
        self.assertTrue(any(next(u.text for u in prose.units if u.unit_id == key)[start:end] == meaningful for key, start, end in retained))
        self.assertFalse(excluded)
        self.assertEqual(module.clean_fact_text(meaningful), meaningful)

    def test_reported_naming_stage_retains_local_attribution_and_unreleased_scope(self):
        from test_relevance_rules import article_for
        module = load_module()
        rows = [('report', 'Report: Apple foldable will be called iPhone Horizon', 'Reporter Alex Lane claims Apple’s upcoming foldable will be called iPhone Horizon and arrive in November.'), ('reading', 'iPhone Horizon怎么读：苹果折叠屏命名让读者犯难', '科技博主亚历克斯发文称，苹果公司即将推出的折叠屏手机名叫iPhone Horizon，起售价2300美元，新品将在11月上市。虽然新品尚未发布，但名字率先登上了热搜。iPhone Horizon到底该怎么读，让一些读者犯了难。'), ('announced', 'Apple announces foldable iPhone Horizon', 'Apple today revealed its first foldable iPhone, called iPhone Horizon. Customers can buy it in November.')]
        articles = [article_for(module, title, lead, source=label, facts=[lead]) for label, title, lead in rows]
        profiles = [module.article_reconciliation_profile(a) for a in articles]
        self.assertIn('product-disclosure-stage:reported', profiles[1].separation_keys)
        self.assertEqual(module.profile_pair_decision(profiles[0], profiles[1]), 'match')
        self.assertNotEqual(module.profile_pair_decision(profiles[1], profiles[2]), 'match')
        self.assertNotEqual(module.profile_pair_decision(profiles[0], profiles[2]), 'match')
        self.assertEqual(sorted(sorted(a.source for a in e.articles) for e in module.cluster_articles(articles)),
                         [['announced'], ['reading', 'report']])

    def test_same_source_response_formatting_does_not_duplicate_consumed_fact(self):
        module = load_module()
        from apple_news_core.models import PreparedFact, SourceFactView
        source, url = 'Supplier source', 'https://supplier.example/cooperation'
        title = 'Supplier responds to Apple cooperation inquiry'
        kept = 'The company says its memory module offers 6400 MT/s and stable supply.'
        spaced = 'The company says its memory module offers 6400 MT/s and stable supply .'
        qualification = 'The company says product quality and supply stability are competitive; Apple customer details remain subject to public disclosure.'
        evidence = module.capture_article_evidence(source, url, '<article><p>' + kept + '</p><p>' + qualification + '</p></article>', title)
        def located(text):
            unit = next(u for u in evidence.units if u.text == text)
            return PreparedFact(text, text.casefold(), origins=((source, url, evidence.article_id, unit.unit_id, 0, len(text)),))
        response = PreparedFact(spaced, spaced.casefold(), origins=((source, url, evidence.article_id, '', 0, 0),))
        def plan(pending):
            view = SourceFactView(source, url, 1, module.utc_now(), False, 3, False,
                                 normal=(located(kept),), responses=(pending, located(qualification)), display_title=title)
            return module.resolve_event_fact_plan([view], relevance_tier='strong', base_limit=1, official_limit=1)
        result = plan(response)
        self.assertFalse(any(f.text == spaced for f in result.unprocessed))
        self.assertTrue(any(f.text == qualification for f in (*result.facts, *result.required, *result.unprocessed)))
        for text, other_url, other_id in [
            (kept.replace('6400', '7200'), url, evidence.article_id),
            (kept + ' Only selected customers qualify.', url, evidence.article_id),
            (kept, 'https://other.example/report', 'other-article'),
            (kept.replace('stable supply', 'no stable supply'), url, evidence.article_id),
        ]:
            with self.subTest(text=text, url=other_url):
                pending = PreparedFact(text, text.casefold(), origins=((source, other_url, other_id, '', 0, 0),))
                self.assertTrue(any(f.text == text and f.origins == pending.origins for f in plan(pending).unprocessed))

    def test_current_embedded_post_survives_same_owner_comparison_not_topic_switch(self):
        from test_relevance_rules import article_for
        module = load_module()
        rows = [('continued-owner', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. Just as Jordan Reed and other executives tease launches before special events, new CEO Casey Stone has done the same thing. His third post to X, ahead of today's special event, is a video that hints at something camera-related, without explicitly saying what it's about.", 'https://continued-owner.example/current/preview', '<article><h1>Casey Stone teases variable aperture in iPhone 22 Pro before event</h1><p>The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. Just as Jordan Reed and other executives tease launches before special events, new CEO Casey Stone has done the same thing. His third post to X, ahead of today&#x27;s special event, is a video that hints at something camera-related, without explicitly saying what it&#x27;s about.</p><blockquote class="twitter-tweet"><a href="https://x.com/caseystone/status/2110000000000000042">Preview post</a></blockquote></article>'), ('adjacent-control', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. His third post to X, ahead of today's special event, is a video that hints at something camera-related, without explicitly saying what it's about.", 'https://adjacent-control.example/current/preview', '<article><h1>Casey Stone teases variable aperture in iPhone 22 Pro before event</h1><p>The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. His third post to X, ahead of today&#x27;s special event, is a video that hints at something camera-related, without explicitly saying what it&#x27;s about.</p><blockquote class="twitter-tweet"><a href="https://x.com/caseystone/status/2110000000000000042">Preview post</a></blockquote></article>'), ('chinese-current', '苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温', '苹果将在今晚举办发布会，外界预计公司推出新品。发布会开始前，苹果新任 CEO Casey Stone 公开了一段神秘预告视频。这段短片中一束光照在手机边缘，光源的形状逐渐缩小，外界猜测与光圈有关。', 'https://chinese-current.example/current/preview', '<article><h1>苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温</h1><p>苹果将在今晚举办发布会，外界预计公司推出新品。发布会开始前，苹果新任 CEO Casey Stone 公开了一段神秘预告视频。这段短片中一束光照在手机边缘，光源的形状逐渐缩小，外界猜测与光圈有关。</p><blockquote class="twitter-tweet"><a href="https://x.com/caseystone/status/2110000000000000042">Preview post</a></blockquote></article>'), ('explicit-topic-switch', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. Samsung CEO Morgan Lake has now posted a different message about a display. His third post to X, ahead of today's special event, is a video that hints at something camera-related, without explicitly saying what it's about.", 'https://explicit-topic-switch.example/current/preview', '<article><h1>Casey Stone teases variable aperture in iPhone 22 Pro before event</h1><p>The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. Samsung CEO Morgan Lake has now posted a different message about a display. His third post to X, ahead of today&#x27;s special event, is a video that hints at something camera-related, without explicitly saying what it&#x27;s about.</p><blockquote class="twitter-tweet"><a href="https://x.com/caseystone/status/2110000000000000042">Preview post</a></blockquote></article>')]
        articles = []
        for label, title, lead, url, markup in rows:
            article = article_for(module, title, lead, source=label, facts=[lead])
            article.url = url
            article.evidence = module.capture_article_evidence(label, url, markup, title)
            articles.append(article)
        profiles = [module.article_reconciliation_profile(a) for a in articles]
        key = 'primary-claim:embedded-video:x:2110000000000000042:pre-event-preview-publication'
        for index in range(3):
            with self.subTest(source=rows[index][0]):
                self.assertIn(key, profiles[index].event_keys)
        self.assertNotIn(key, profiles[3].event_keys)
        for left, right, expected in [(0, 2, True), (0, 1, True), (1, 2, True), (3, 2, False)]:
            with self.subTest(pair=(left, right)):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == 'match', expected)
        groups = module.cluster_articles(articles)
        self.assertEqual(sorted(sorted(a.source for a in e.articles) for e in groups),
                         sorted([sorted(row[0] for row in rows[:3]), [rows[3][0]]]))
        base = articles[0]
        comparison = 'Just as Jordan Reed and other executives tease launches before special events, new CEO Casey Stone has done the same thing.'
        for replacement in [
            'Just as Casey Stone teases launches before special events, Samsung CEO Morgan Lake has done the same thing.',
            'New CEO Morgan Lake has done the same thing.',
            'New CEO Casey Stone has posted a different message about a display.',
            'New CEO Casey Stone did not do the same thing.',
        ]:
            with self.subTest(comparison=replacement):
                lead = base.summary.replace(comparison, replacement)
                other = article_for(module, base.title, lead, facts=[lead])
                other.evidence = base.evidence
                self.assertNotIn(key, module.article_reconciliation_profile(other).event_keys)
        renamed = article_for(module, base.title.replace('Casey Stone', 'Morgan Lake'),
                              base.summary.replace('Casey Stone', 'Morgan Lake'),
                              facts=[base.summary.replace('Casey Stone', 'Morgan Lake')])
        renamed.evidence = base.evidence
        self.assertIn(key, module.article_reconciliation_profile(renamed).event_keys)


    def test_embedded_video_current_post_continuity_keeps_hardware_prediction_separate(self):
        from test_relevance_rules import article_for
        module = load_module()
        rows = [('same-post-noun-publication', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The third X post from Apple CEO Casey Stone previews the upcoming iPhone 22 Pro camera. Before today's event, the executive shared a nine-second clip. The video shows a spotlight on dark glass. The light narrows into a small circle; the hardware itself has not been announced.", 'https://source-a.example/reports/teaser-video', '<html><article><h1>Casey Stone teases variable aperture in iPhone 22 Pro before event</h1><p>The third X post from Apple CEO Casey Stone previews the upcoming iPhone 22 Pro camera. Before today&#x27;s event, the executive shared a nine-second clip. The video shows a spotlight on dark glass. The light narrows into a small circle; the hardware itself has not been announced.</p><blockquote class="twitter-tweet"><p>Preview video</p><a href="https://x.com/caseystone/status/2110000000000000042">Posted today</a></blockquote></article></html>'), ('same-post-delayed-publication', '苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温', '苹果将在今晚举办发布会。开始前，苹果CEO凯西·斯通（Casey Stone）发布了一个九秒预告视频。一束光照在手机边缘，发光形状逐渐变小。外界猜测它暗示光圈变化，官方还没有公布规格。', 'https://source-b.example/news/preview-post', '<html><article><h1>苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温</h1><p>苹果将在今晚举办发布会。开始前，苹果CEO凯西·斯通（Casey Stone）发布了一个九秒预告视频。一束光照在手机边缘，发光形状逐渐变小。外界猜测它暗示光圈变化，官方还没有公布规格。</p><iframe title="X Post" src="https://platform.twitter.com/embed/Tweet.html?id=2110000000000000042&amp;lang=en"></iframe></article></html>'), ('embedded-noun-new-role', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. His third post to X, ahead of today's event, is a video hinting at a camera update. The clip shows a spotlight. The light narrows against curved glass; specifications remain unannounced.", 'https://source-d.example/current/preview', '<html><article><h1>Casey Stone teases variable aperture in iPhone 22 Pro before event</h1><p>The third X post from new Apple CEO Casey Stone is almost certainly teasing the iPhone 22 Pro Max camera, which should be revealed later today. His third post to X, ahead of today&#x27;s event, is a video hinting at a camera update. The clip shows a spotlight. The light narrows against curved glass; specifications remain unannounced.</p><blockquote class="twitter-tweet"><p>Preview video</p><a href="https://x.com/caseystone/status/2110000000000000042">Posted today</a></blockquote></article></html>'), ('embedded-later-role-publication', '苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温', '苹果将在今晚举办发布会，外界预计公司推出新品。发布会开始前，苹果新任 CEO Casey Stone 公开了一段神秘预告视频。这段短片中一束光照在手机边缘，光源的形状逐渐缩小，外界猜测与光圈有关。', 'https://source-e.example/current/preview', '<html><article><h1>苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温</h1><p>苹果将在今晚举办发布会，外界预计公司推出新品。发布会开始前，苹果新任 CEO Casey Stone 公开了一段神秘预告视频。这段短片中一束光照在手机边缘，光源的形状逐渐缩小，外界猜测与光圈有关。</p><iframe title="X Post" src="https://platform.twitter.com/embed/Tweet.html?id=2110000000000000042&amp;lang=en"></iframe></article></html>')]
        articles = []
        for label, title, lead, url, markup in rows:
            article = article_for(module, title, lead, source=label, facts=[lead])
            article.url = url
            article.evidence = module.capture_article_evidence(label, url, markup, title)
            articles.append(article)
        profiles = [module.article_reconciliation_profile(a) for a in articles]
        for index, profile in enumerate(profiles):
            with self.subTest(source=rows[index][0]):
                self.assertIn('primary-claim:embedded-video:x:2110000000000000042:pre-event-preview-publication', profile.event_keys)
                self.assertFalse(any(k.startswith('canonical-apple-action:') and k.endswith(':camera-system-adoption') for k in profile.event_keys))
        for left in range(4):
            for right in range(left + 1, 4):
                with self.subTest(pair=(left, right)):
                    self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]), 'match')
        self.assertEqual([len(e.articles) for e in module.cluster_articles(articles)], [4])
        from dataclasses import replace
        base = articles[2]
        for lead in [
            base.summary.replace("His third post to X, ahead of today\'s event, is a video", 'His third post to X is not a video'),
            base.summary.replace('The third X post from new Apple CEO', 'Last year, the third X post from new Apple CEO'),
            base.summary.replace('His third post to X,', 'Samsung CEO Morgan Lake posted another message. His third post to X,'),
            base.summary.replace('new Apple CEO Casey Stone', 'new Samsung CEO Casey Stone'),
            base.summary.replace('is almost certainly teasing', 'may be published tomorrow, teasing'),
        ]:
            with self.subTest(lead=lead):
                other = article_for(module, base.title, lead, facts=[lead])
                other.evidence = base.evidence
                profile = module.article_reconciliation_profile(other)
                self.assertFalse(any(k.startswith('primary-claim:embedded-video:') for k in profile.event_keys))
        chinese = articles[3]
        for lead in [chinese.summary.replace('公开了一段', '尚未公开一段'),
                     chinese.summary.replace('苹果新任 CEO', '三星新任 CEO')]:
            other = article_for(module, chinese.title, lead, facts=[lead])
            other.evidence = chinese.evidence
            self.assertFalse(any(k.startswith('primary-claim:embedded-video:')
                             for k in module.article_reconciliation_profile(other).event_keys))

    def test_embedded_preview_reference_is_source_bound_and_action_scoped(self):
        from dataclasses import asdict
        import json
        from test_relevance_rules import article_for
        module = load_module()
        rows = [('same-post-noun-publication', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The third X post from Apple CEO Casey Stone previews the upcoming iPhone 22 Pro camera. Before today's event, the executive shared a nine-second clip. The video shows a spotlight on dark glass. The light narrows into a small circle; the hardware itself has not been announced.", 'https://source-a.example/reports/teaser-video', '<html><article><h1>Casey Stone teases variable aperture in iPhone 22 Pro before event</h1><p>The third X post from Apple CEO Casey Stone previews the upcoming iPhone 22 Pro camera. Before today&#x27;s event, the executive shared a nine-second clip. The video shows a spotlight on dark glass. The light narrows into a small circle; the hardware itself has not been announced.</p><blockquote class="twitter-tweet"><p>Preview video</p><a href="https://x.com/caseystone/status/2110000000000000042">Posted today</a></blockquote></article></html>'), ('same-post-delayed-publication', '苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温', '苹果将在今晚举办发布会。开始前，苹果CEO凯西·斯通（Casey Stone）发布了一个九秒预告视频。一束光照在手机边缘，发光形状逐渐变小。外界猜测它暗示光圈变化，官方还没有公布规格。', 'https://source-b.example/news/preview-post', '<html><article><h1>苹果CEO发布神秘预告视频，iPhone 22 Pro与折叠屏传闻升温</h1><p>苹果将在今晚举办发布会。开始前，苹果CEO凯西·斯通（Casey Stone）发布了一个九秒预告视频。一束光照在手机边缘，发光形状逐渐变小。外界猜测它暗示光圈变化，官方还没有公布规格。</p><iframe title="X Post" src="https://platform.twitter.com/embed/Tweet.html?id=2110000000000000042&amp;lang=en"></iframe></article></html>'), ('same-reference-commentary', 'Opinion: Why Apple teaser videos are usually a distraction', 'This opinion revisits the earlier preview post and criticizes the marketing style. It reports no new video or camera announcement.', 'https://source-c.example/opinion/old-preview', '<article><h1>Opinion: Why Apple teaser videos are usually a distraction</h1><p>This opinion revisits the earlier preview post and criticizes the marketing style. It reports no new video or camera announcement.</p><a href="https://x.com/caseystone/status/2110000000000000042">earlier post</a></article>')]
        articles = []
        for source, title, lead, url, markup in rows:
            article = article_for(module, title, lead, source=source, facts=[lead])
            article.url = url
            article.evidence = module.capture_article_evidence(source, url, markup, title)
            articles.append(article)
        for article in articles[:2]:
            self.assertIn('2110000000000000042', json.dumps(asdict(article.evidence)))
            self.assertEqual(article.evidence.url, article.url)
        self.assertNotEqual(articles[0].evidence.article_id, articles[1].evidence.article_id)
        profiles = [module.article_reconciliation_profile(a) for a in articles]
        self.assertEqual(module.profile_pair_decision(profiles[0], profiles[1]), 'match')
        self.assertNotEqual(module.profile_pair_decision(profiles[0], profiles[2]), 'match')
        groups = module.cluster_articles(articles)
        self.assertEqual(sorted(len(g.articles) for g in groups), [1, 2])

        from dataclasses import replace
        # Same embed is evidence of an object, not of the article's action.
        for title, lead in [
            ('Apple CEO previews an iPhone camera in an old video',
             'Apple CEO Casey Stone previously published a preview video last year.'),
            ('Apple updates the preview video playback page',
             'Apple changed the web player today. Apple CEO Casey Stone published the preview video earlier.'),
            ('Apple removes the CEO preview video from its website',
             'Apple removed the preview from its site today. Apple CEO Casey Stone published the preview video today.'),
            ('Samsung CEO previews a camera video',
             'Samsung CEO Casey Stone posted a preview video today.'),
        ]:
            with self.subTest(title=title):
                other = article_for(module, title, lead, facts=[lead])
                other.evidence = articles[0].evidence
                other_profile = module.article_reconciliation_profile(other)
                self.assertFalse(any('embedded-video:' in k for k in other_profile.event_keys))
                self.assertNotEqual(module.profile_pair_decision(profiles[0], other_profile), 'match')
        different = replace(articles[1], evidence=replace(articles[1].evidence,
            embedded_references=tuple(replace(ref, object_id='2110000000000000099')
                                      for ref in articles[1].evidence.embedded_references)))
        self.assertNotEqual(module.profile_pair_decision(profiles[0],
            module.article_reconciliation_profile(different)), 'match')
        iframe = '<iframe src="https://platform.twitter.com/embed/Tweet.html?id=2110000000000000042"></iframe>'
        clean = module.capture_article_evidence('test', 'https://example.com/a',
            '<nav>' + iframe + '</nav><article><p>Actual article.</p>'
            '<aside>' + iframe + '</aside><div class="related">' + iframe + '</div></article>', 'Title')
        self.assertFalse(clean.embedded_references)
        malformed = module.capture_article_evidence('test', 'https://example.com/b',
            '<article><p>Actual source statement remains.</p><iframe src="http://[broken"></iframe></article>', 'Title')
        self.assertFalse(malformed.embedded_references)
        self.assertTrue(any('Actual source statement remains.' == u.text for u in malformed.units))
        for article in articles[:2]:
            ref = article.evidence.embedded_references[0]
            self.assertEqual(ref.origin, 'html:body')
            self.assertGreater(ref.body_element_index, 0)
            self.assertIn('2110000000000000042', ref.html_tag)

        # Exercise normal extraction, clustering and final serialization.
        sparse_title = '苹果CEO发布预热视频：暗示iPhone 22 Pro Max可变光圈'
        sparse_lead = '苹果CEO凯西·斯通今天在发布会前发了预热视频，视频中的光圈由大变小。这被解读为iPhone 22 Pro Max可能拥有可变光圈，但官方规格还未公布。'
        run_rows = rows[:2] + [('sparse', sparse_title, sparse_lead, 'https://source-d.example/preview',
                               '<article><h1>' + sparse_title + '</h1><p>' + sparse_lead + '</p></article>')]
        now = module.utc_now().isoformat()
        pages = {url: '<meta property="article:published_time" content="' + now + '">' + markup
                 for source, title, lead, url, markup in run_rows}
        candidates = [module.Candidate(name, row[3], row[1], summary=row[2])
                      for name, row in zip(('IT之家', '9to5Mac', 'MacRumors'), run_rows)]
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'fetch_url', side_effect=lambda url, *a, **kw: pages[url]):
                result = module.run(args)
        events = result['events'] + result['deferred_events']
        self.assertEqual(sorted(len(e['sources']) for e in events), [1, 2])
        self.assertEqual({v['url'] for e in events for v in e['sources']}, set(pages))
        evidence = list(result['source_evidence'].values())
        self.assertEqual(len(evidence), 3)
        self.assertEqual({v['url'] for v in evidence}, set(pages))
        for item in evidence:
            if item['url'] != run_rows[-1][3]:
                self.assertEqual(item['embedded_references'][0]['object_id'], '2110000000000000042')
            else:
                self.assertFalse(item['embedded_references'])
        reviews = [q for q in result['final_brief_queue'] if run_rows[-1][3] in q.get('source_urls', [])
                   and q.get('unprocessed_evidence')]
        self.assertTrue(reviews)
        self.assertTrue(any('original video' in q.get('reason', '') for q in reviews))
        self.assertIn('original video', module.render_brief_scaffold(result))
        for q in reviews:
            for u in q['unprocessed_evidence']:
                original = next(unit for e in evidence for unit in e['units'] if unit['unit_id'] == u['unit_id'])
                self.assertEqual(original['text'][u['start']:u['end']], u['text'])

    def test_multiaction_sources_keep_owned_facts_and_visible_remainder(self):
        module = load_module()
        now = module.utc_now().isoformat()
        records = [
            ('IT之家', 'https://www.ithome.com/1/123/456.htm', '苹果功能分批上线', [
                'Siri AI 十月新增法语、日语支持。',
                'Apple Watch 的 Live Rewind 和 Siri Recap 将于年底推出，需要配对 iPhone 16。',
                '密码应用将在后续更新中自动修复泄露密码。']),
            ('9to5Mac', 'https://9to5mac.com/2026/09/10/siri-languages/', 'Siri adds languages in October', [
                'Siri adds French and Japanese in October.']),
            ('The Verge', 'https://www.theverge.com/apple/watch-ultra/', 'Apple Watch Ultra 4 launches', [
                'Apple Watch Ultra 4 launches with 50 hours of battery life.',
                'Previously, Siri added French and Japanese in October.']),
        ]
        candidates = [module.Candidate(source, url, title) for source, url, title, _ in records]
        pages = {url: f'<meta property="article:published_time" content="{now}"><article><h1>{title}</h1>'
                 + ('<p>' + ' '.join(units) + '</p>' if url == records[0][1] else ''.join(f'<p>{text}</p>' for text in units)) + '</article>'
                 for _, url, title, units in records}
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'fetch_url', side_effect=lambda url, *args, **kwargs: pages[url]):
                result = module.run(args)
        events = result['events'] + result['deferred_events']
        language = [event for event in events if any(claim['object'] == 'languages'
                    for claim in event.get('claims', []))]
        self.assertEqual(len(language), 1, 'A bound language action must survive to final JSON')
        self.assertEqual({source['name'] for source in language[0]['sources']}, {'IT之家', '9to5Mac'})
        self.assertEqual(language[0]['relevance_tier'], 'strong')
        self.assertEqual(language[0]['category'], 'software_systems')
        self.assertTrue(any('French and Japanese in October' in fact for fact in language[0]['key_facts']))
        self.assertTrue(any('十月新增法语、日语' in fact for fact in language[0]['key_facts']))
        hardware = [event for event in events if any(source['name'] == 'The Verge' for source in event['sources'])]
        self.assertEqual(len(hardware), 1)
        self.assertNotEqual(hardware[0]['id'], language[0]['id'])
        self.assertTrue(any('50 hours' in fact for fact in hardware[0]['key_facts']))
        self.assertFalse(any('50 hours'  in fact or 'Live Rewind' in fact for fact in language[0]['key_facts']))
        watch = [event for event in events if any(claim['object'] == 'watch-audio'
                 for claim in event.get('claims', []))]
        self.assertEqual(len(watch), 1)
        self.assertTrue(any('iPhone 16' in fact for fact in watch[0]['key_facts']))
        review = [item for item in result['final_brief_queue'] if item.get('unprocessed_evidence')]
        self.assertTrue(any(unit['text'] == records[0][3][2] and item['source_urls'] == [records[0][1]]
                            for item in review for unit in item['unprocessed_evidence']))
        password_review = next(item for item in review if any(unit['text'] == records[0][3][2]
                               for unit in item['unprocessed_evidence']))
        self.assertNotEqual(password_review.get('relevance_tier'), 'weak')
        self.assertTrue(password_review['reason'])
        self.assertEqual([unit['text'] for unit in password_review['unprocessed_evidence']], [records[0][3][2]])
        evidence = result['source_evidence'][password_review['evidence_id']]
        self.assertLessEqual({unit['unit_id'] for unit in password_review['unprocessed_evidence']},
                             {unit['unit_id'] for unit in evidence['units']})
        for event in language + watch:
            for claim in event['claims']:
                self.assertTrue(claim['unit_ids'])
                evidence = result['source_evidence'][claim['article_id']]
                self.assertLessEqual(set(claim['unit_ids']), {unit['unit_id'] for unit in evidence['units']})
        self.assertIn(records[0][3][2], result['final_brief_markdown'])

    def test_language_subject_is_not_a_watch_feature_or_parenthetical_background(self):
        module = load_module()
        for title, body in [
            ('Apple Watch Ultra launches', 'Live Rewind shows recent conversations. Users can ask Siri for context. Siri Recap will be available with English support; additional languages will follow.'),
            ('Apple Intelligence update', 'Apple Intelligence (of which Siri AI is just a part of) will support sixteen languages.'),
        ]:
            evidence = module.capture_article_evidence('Source', 'https://example.com/a',
                f'<article><p>{body}</p></article>', title)
            projections, _, _ = module.project_article_evidence(evidence)
            self.assertFalse(projections, 'A nearby Siri mention cannot own another subject rollout')

    def test_owned_list_and_regional_limits_are_reachable_facts(self):
        module = load_module()
        page = '<article><p>Siri AI will roll out in English in September; other languages get support in October:</p><ul><li>French</li><li>Japanese</li></ul><p>Siri AI will not be available in China or the EU.</p></article>'
        evidence = module.capture_article_evidence('Source', 'https://example.com/siri', page,
                                                   'Siri language rollout')
        projections, remaining, excluded = module.project_article_evidence(evidence)
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)
        facts = [fact for projection in projections for fact in projection.key_facts]
        self.assertIn('French', facts)
        self.assertIn('Japanese', facts)
        self.assertTrue(any('China or the EU' in fact for fact in facts))
        self.assertFalse(remaining)
        restrictions = [q[:3] for projection in projections for q in projection.claim.qualifiers]
        self.assertIn(('languages', 'excluded-region', 'china'), restrictions)
        self.assertIn(('languages', 'excluded-region', 'eu'), restrictions)
        with self.assertRaises(ValueError):
            module.validate_evidence_dispositions(evidence, projections, [evidence.units[0].unit_id], excluded)

    def test_bound_partition_is_seed_independent_and_conflict_blocks_bridge(self):
        module = load_module()
        pages = ['Siri adds French in October.', 'Siri 十月新增法语支持。',
                 'Siri adds French.', 'Siri adds French in November.']
        articles = []
        for index, text in enumerate(pages):
            evidence = module.capture_article_evidence(str(index), f'https://example.com/{index}',
                                                       f'<article><p>{text}</p></article>', text)
            projection = module.project_article_evidence(evidence)[0][0]
            articles.append(module.Article(str(index), evidence.url, text, text, [text], '',
                module.utc_now(), '', '', '', set(), evidence=evidence, bound_claim=projection.claim))
        def partition(order, seeds):
            groups = module.reconcile_articles(order, profile_for=module.article_reconciliation_profile,
                                                initial_groups=seeds)
            return {frozenset(article.source for article in group) for group in groups}
        expected = partition(articles, [articles])
        self.assertEqual(expected, partition(list(reversed(articles)), [[a] for a in articles]))
        self.assertTrue(any({'0', '1'} <= group for group in expected))
        self.assertFalse(any({'0', '3'} <= group for group in expected))
        self.assertEqual(sum(map(len, expected)), len(articles))
        repeated = module.reconcile_articles(articles + [articles[0]],
            profile_for=module.article_reconciliation_profile, initial_groups=[articles])
        self.assertEqual(sum(map(len, repeated)), len(articles))

    def test_opinion_parent_is_not_promoted_by_its_feature_details(self):
        module = load_module()
        evidence = module.capture_article_evidence('Source', 'https://example.com/opinion',
            '<article><p>Siri adds French in October.</p></article>', 'Why I think Siri is disappointing')
        evidence = module.replace(evidence, content_form='opinion')
        projections, remaining, _ = module.project_article_evidence(evidence)
        self.assertFalse(projections)
        self.assertEqual(remaining, tuple((unit.unit_id, 0, len(unit.text)) for unit in evidence.units))

    def test_rollout_languages_keep_their_own_phase(self):
        module = load_module()
        evidence = module.capture_article_evidence('Source', 'https://example.com/phases',
            '<article><p>The new Siri AI will launch in English before expanding to five more languages in October.</p>'
            '<p>Siri AI will roll out in English alongside iOS 27, scheduled for September 14, while the following languages will get support in October:</p>'
            '<ul><li>French</li><li>Japanese</li></ul></article>', 'Siri language rollout')
        projections, _, _ = module.project_article_evidence(evidence)
        first = projections[0].claim.qualifiers
        self.assertTrue(any(q[:3] == ('english', 'rollout-time', 'unspecified') for q in first))
        self.assertFalse(any(q[:3] == ('english', 'rollout-time', 'month:10') for q in first))
        second = projections[1].claim.qualifiers
        self.assertTrue(any(q[:3] == ('english', 'rollout-time', 'month:9') for q in second))
        self.assertTrue(any(q[:3] == ('french', 'rollout-time', 'month:10') for q in second))
        self.assertTrue(any(q[:3] == ('japanese', 'rollout-time', 'month:10') for q in second))
        units = {unit.unit_id: unit.text for unit in evidence.units}
        for projection in projections:
            for qualifier in projection.claim.qualifiers:
                self.assertTrue(units[qualifier[3]][qualifier[4]:qualifier[5]])
        claim = projections[0].claim
        forged = module.replace(projections[0], claim=module.replace(claim,
            qualifiers=(('english', 'rollout-time', 'month:10', 'foreign-unit', 0, 1),)))
        with self.assertRaises(ValueError):
            module.validate_evidence_dispositions(evidence, (forged, *projections[1:]), (), ())

    def test_partial_paragraph_does_not_assign_the_unrecognized_action(self):
        module = load_module()
        text = 'Siri adds French in October. Passwords will repair leaked passwords in a future update.'
        evidence = module.capture_article_evidence('Source', 'https://example.com/mixed',
            f'<article><p>{text}</p></article>', 'Apple feature updates')
        projections, remaining, excluded = module.project_article_evidence(evidence)
        self.assertEqual(projections[0].key_facts, ('Siri adds French in October.',))
        self.assertTrue(remaining)
        unit = evidence.units[0]
        self.assertTrue(any(unit.text[start:end] == 'Passwords will repair leaked passwords in a future update.'
                            for key, start, end in remaining if key == unit.unit_id))
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)

    def test_unbound_seed_is_not_positive_event_evidence(self):
        module = load_module()
        articles = [module.Article(source, f'https://example.com/{source}', title, 'No action evidence.', [],
                                   '', module.utc_now(), '', '', '', set())
                    for source, title in [('A', 'Report alpha'), ('B', 'Report beta')]]
        profile = module.ReconciliationProfile(frozenset(), frozenset())
        combined = module.reconcile_articles(articles, profile_for=lambda article: profile, initial_groups=[articles])
        separate = module.reconcile_articles(articles, profile_for=lambda article: profile,
                                             initial_groups=[[article] for article in articles])
        self.assertEqual(len(combined), len(separate))
        self.assertEqual(len(combined), 2)

    def test_sparse_title_and_rich_bound_report_share_the_same_positive_pair(self):
        module = load_module()
        text = 'Siri adds French in October.'
        evidence = module.capture_article_evidence('Rich', 'https://example.com/rich',
            f'<article><p>{text}</p></article>', text)
        projection = module.project_article_evidence(evidence)[0][0]
        rich = module.Article('Rich', evidence.url, text, text, [text], '', module.utc_now(),
                              '', '', '', set(), evidence=evidence, bound_claim=projection.claim)
        for summary, facts in (('', []), ('Siri 十月新增法语支持。', []),
                               ('Siri 十月新增法语支持。', ['Siri 十月新增法语支持。'])):
            with self.subTest(summary=summary):
                sparse = module.Article('Sparse', 'https://example.com/sparse', 'Siri 十月新增法语支持。', summary, list(facts),
                                        'hardware_products', module.utc_now(), '', '', '', set(), relevance_tier='weak')
                events = module.cluster_articles([rich, sparse])
                self.assertEqual(len(events), 1, 'Sparse explicit source evidence must meet the bound report')
                self.assertEqual(events[0].category, 'software_systems')
                self.assertEqual(events[0].relevance_tier, 'strong')
                self.assertEqual({article.source for article in events[0].articles}, {'Rich', 'Sparse'})
                self.assertEqual(sparse.evidence.extraction_path, 'article_input')
                origins = {unit.origin for unit in sparse.evidence.units}
                self.assertIn('article:title', origins)
                if summary:
                    self.assertEqual(sparse.summary, summary)
                    self.assertIn('article:summary', origins)
                if facts:
                    self.assertEqual(sparse.key_facts, facts)
                    self.assertIn('article:key_facts:0', origins)

        for title, summary in (
            ('Siri 十一月新增法语支持。', 'Siri 十一月新增法语支持。'),
            ('Siri 十月新增法语支持。', 'Siri will not add French in October.'),
            ('Siri 语言计划', 'Siri adds French in November.'),
            ('Siri 十月新增法语支持。', 'Siri adds French in October on iOS 28.'),
        ):
            with self.subTest(negative=(title, summary)):
                sparse = module.Article('Sparse', 'https://example.com/sparse', title, summary, [],
                                        '', module.utc_now(), '', '', '', set())
                self.assertEqual(len(module.cluster_articles([rich, sparse])), 2)

    def test_feature_delay_parent_excludes_schedule_background_not_unprocessed_actions(self):
        module = load_module()
        page = ('<article><p>Siri adds French in October. Apple Watch opens preorders on Friday. '
                'Passwords will repair leaked passwords in a future update.</p>'
                '<p>用于展示新款 iPhone 游戏性能的《示例游戏》将在稍后上线。</p></article>')
        evidence = module.capture_article_evidence('Source', 'https://example.com/delays', page,
                                                   'Apple features delayed beyond launch')
        projections, remaining, excluded = module.project_article_evidence(evidence)
        units = {unit.unit_id: unit.text for unit in evidence.units}
        review = [units[key][start:end] for key, start, end in remaining]
        rejected = [units[key][start:end] for key, start, end, _ in excluded]
        self.assertEqual(review, ['Passwords will repair leaked passwords in a future update.'])
        self.assertTrue(any('preorders' in text for text in rejected))
        self.assertTrue(any('示例游戏' in text for text in rejected))
        ordinary = module.replace(evidence, title='Apple product announcements')
        _, retained, _ = module.project_article_evidence(ordinary)
        self.assertTrue(any('preorders' in units[key][start:end] for key, start, end in retained))
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)

    def test_explicit_watch_rollout_year_is_preserved_as_a_boundary(self):
        module = load_module()
        claims = []
        for year in ('2026', '2027'):
            evidence = module.capture_article_evidence('Source', 'https://example.com/watch',
                f'<article><p>Apple Watch 的 Live Rewind 将于 {year} 年底推出。</p></article>', 'Apple Watch features')
            claim = module.project_article_evidence(evidence)[0][0].claim
            self.assertTrue(any(q[:3] == ('watch-audio', 'rollout-year', year) for q in claim.qualifiers))
            claims.append(claim)
        self.assertEqual(module.identity_pair_decision(*claims), 'conflict')

    def test_hardware_launch_owns_specifications_without_a_nearby_software_action(self):
        module = load_module()
        page = ('<article><p>Apple announced the next Apple Watch Ultra at its event.</p>'
                '<p>The Apple Watch Ultra 4 takes heart rate readings at 5-second intervals. Heart rate variability is measured every five minutes.</p>'
                '<p>The Ultra 4 lasts 50 hours. In Low Power Mode, it lasts 84 hours. Passwords will repair leaked passwords in a future update.</p>'
                '<p>Previously, Siri added French in October.</p></article>')
        evidence = module.capture_article_evidence('Source', 'https://example.com/hardware', page,
                                                   'Apple Watch Ultra 4 is ready for Siri')
        projections, remaining, excluded = module.project_article_evidence(evidence)
        hardware = [p for p in projections if p.action == 'product-launch']
        self.assertEqual(len(hardware), 1)
        facts = ' '.join(hardware[0].key_facts)
        for value in ('5-second intervals', 'every five minutes', '50 hours', '84 hours'):
            self.assertIn(value, facts)
        self.assertNotIn('Passwords', facts)
        self.assertNotIn('French', facts)
        self.assertEqual(module.bound_reconciliation_profile(hardware[0].claim).category_hint, 'hardware_products')
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)

    def test_third_party_title_owner_cannot_borrow_apple_hardware_background(self):
        module = load_module()
        evidence = module.capture_article_evidence('Source', 'https://example.com/case',
            '<article><p>Apple announced iPhone 18 today. A vendor now launches its new protective case.</p></article>',
            'AccessoryCo launches a new case for iPhone 18')
        projections, remaining, _ = module.project_article_evidence(evidence)
        self.assertFalse(projections)
        self.assertTrue(remaining)

    def test_unbound_positive_relation_is_seed_independent_without_build_bridge(self):
        module = load_module()
        articles = [module.Article(source, f'https://example.com/{source}', 'Firmware release', 'Release report', [],
                                   '', module.utc_now(), '', '', '', set()) for source in ('A', 'B', 'C')]
        profiles = {id(article): module.ReconciliationProfile(frozenset(), frozenset(),
            exact_facets=frozenset({'firmware-release'}),
            separation_keys=frozenset({f'code-build:{build}'}) if build else frozenset())
            for article, build in zip(articles, ('build-one', '', 'build-two'))}
        def partition(seeds):
            groups = module.reconcile_articles(articles, profile_for=lambda article: profiles[id(article)], initial_groups=seeds)
            return {frozenset(article.source for article in group) for group in groups}
        first = partition([articles[:2], articles[2:]])
        second = partition([articles[:1], articles[1:]])
        self.assertEqual(first, second)
        self.assertTrue(any(len(group) == 2 for group in first), 'Keep positive shared release evidence')
        self.assertFalse(any({'A', 'C'} <= group for group in first))

    def test_sparse_release_version_requires_unique_platform_stage_support(self):
        module = load_module()
        titles = ['Apple Releases macOS Golden Gate Beta 5', 'Apple Releases macOS 27 Beta 5', 'Apple Releases macOS 26 Beta 5']
        articles = [module.Article(str(i), f'https://example.com/{i}', title, title, [], '', module.utc_now(),
                                   '', '', '', set()) for i, title in enumerate(titles)]
        profiles = {id(article): module.article_reconciliation_profile(article) for article in articles}
        groups = module.reconcile_articles(articles, profile_for=lambda article: profiles[id(article)], initial_groups=[articles])
        self.assertEqual(len(groups), 3, 'Two compatible numbered trains cannot supply a unique missing version')
        groups = module.reconcile_articles(articles[:2], profile_for=lambda article: profiles[id(article)], initial_groups=[])
        self.assertEqual(len(groups), 1)

    def test_compatibility_merge_entry_cannot_approve_without_profile_support(self):
        module = load_module()
        from test_relevance_rules import article_for
        left = article_for(module, 'Apple releases iOS 27 beta 5', 'Apple releases iOS 27 beta 5.')
        right = article_for(module, 'Apple releases iOS 27 beta 5', 'Apple releases iOS 27 beta 5.', source='MacRumors')
        empty = module.ReconciliationProfile(frozenset(), frozenset())
        with patch.object(module, 'article_reconciliation_profile', return_value=empty):
            self.assertFalse(module.should_merge(left, module.singleton_merge_event(right)))
            self.assertFalse(module.events_should_merge(module.singleton_merge_event(left), module.singleton_merge_event(right)))
            mixed = module.singleton_merge_event(left)
            mixed.articles = [left, right]
            self.assertEqual(len(module.split_mixed_topic_event(mixed)), 2)
        self.assertTrue(module.should_merge(left, module.singleton_merge_event(right)))

    def test_price_action_object_swap_stays_bound_through_final_json(self):
        module = load_module()
        texts = [
            ('Apple raises Apple Music prices and lowers Apple TV prices.', 'en-up'),
            ('苹果上调 Apple Music 价格，并下调 Apple TV 价格。', 'zh-up'),
            ('Apple lowers Apple Music prices and raises Apple TV prices.', 'en-down'),
            ('苹果下调 Apple Music 价格，并上调 Apple TV 价格。', 'zh-down'),
        ]
        now = module.utc_now().isoformat()
        candidates = [module.Candidate('9to5Mac', f'https://9to5mac.com/{slug}/', text) for text, slug in texts]
        pages = {candidate.url: f'<meta property="article:published_time" content="{now}"><article><p>{text}</p></article>'
                 for candidate, (text, _) in zip(candidates, texts)}
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'fetch_url', side_effect=lambda url, *args, **kwargs: pages[url]):
                result = module.run(args)
        prices = [event for event in result['events'] + result['deferred_events']
                  if any(claim['object'] == 'subscription-price' for claim in event.get('claims', []))]
        self.assertEqual(len(prices), 4)
        self.assertEqual({(claim['subject'], claim['action']) for event in prices for claim in event['claims']},
                         {(subject, action) for subject in ('apple-music', 'apple-tv') for action in ('price-increase', 'price-decrease')})
        for event in prices:
            self.assertEqual(len(event['sources']), 2)
            self.assertEqual(event['category'], 'software_systems')
            self.assertEqual(event['relevance_tier'], 'strong')
            for claim in event['claims']:
                evidence = result['source_evidence'][claim['article_id']]
                owned = [unit['text'][start:end] for unit_id, start, end in claim['evidence_spans']
                         for unit in evidence['units'] if unit['unit_id'] == unit_id]
                self.assertTrue(owned)
                opposite = 'Apple TV' if claim['subject'] == 'apple-music' else 'Apple Music'
                self.assertFalse(any(opposite in fact for fact in owned))
                verb = ('raises', '上调') if claim['action'] == 'price-increase' else ('lowers', '下调')
                self.assertTrue(any(any(word in fact for word in verb) for fact in owned))
                self.assertTrue(all(fact in event['key_facts'] for fact in owned))

    def test_price_binding_requires_local_owner_and_affirmative_action(self):
        module = load_module()
        for text in ('Apple does not raise Apple Music prices.',
                     'Apple may raise Apple Music prices.',
                     'Apple raises Apple Music prices in a phased schedule to be decided.'):
            evidence = module.capture_article_evidence('Source', 'https://example.com/price',
                '<article><p>' + text + '</p></article>', 'Apple pricing report')
            self.assertFalse(module.project_article_evidence(evidence)[0])
        evidence = module.capture_article_evidence('Source', 'https://example.com/price',
            '<article><p>Apple raises Apple Music prices and a retailer lowers Apple TV prices.</p></article>', 'Apple pricing report')
        projections, remaining, excluded = module.project_article_evidence(evidence)
        self.assertEqual([(p.claim.subject, p.claim.action) for p in projections], [('apple-music', 'price-increase')])
        self.assertTrue(any('retailer' in unit.text[start:end] for unit_id, start, end in remaining
                            for unit in evidence.units if unit.unit_id == unit_id))
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)

    def test_platform_performance_uses_source_metrics_in_all_pair_entries(self):
        module = load_module()
        from test_relevance_rules import article_for
        facts_en = ['Apple outlined more than 40 ways to improve performance.', 'Apps launch up to 30% faster, Photos loads up to 70% faster, and AirDrop transfers up to 80% faster.']
        facts_zh = ['超过 40 项底层性能优化。', 'App 启动最高提速 30%，相册加载最高提升 70%，隔空投送最高提升 80%。']
        left = article_for(module, 'iOS 27 makes your iPhone faster', 'Apple improves iPhone performance.', facts=facts_en)
        right = article_for(module, 'iOS 27 让 iPhone 更快，带来底层优化', '苹果改善 iPhone 性能。', facts=facts_zh, source='IT之家')
        self.assertTrue(module.should_merge(left, module.singleton_merge_event(right)))
        for summary in ('', 'Unrelated hardware background', ' '.join(reversed(facts_en))):
            a, b = module.singleton_merge_event(left), module.singleton_merge_event(right)
            a.summary = b.summary = summary
            for incoming, event in ((left, b), (right, a)):
                self.assertTrue(module.should_merge(incoming, event))
            self.assertTrue(module.events_should_merge(a, b))
            self.assertTrue(module.events_should_merge(b, a))
        self.assertEqual(len(module.cluster_articles([left, right])), 1)
        for title in ('iOS 28 让 iPhone 更快，带来底层优化', 'iOS 27 新增壁纸'):
            other = article_for(module, title, '背景回顾上一轮性能改善。', facts=facts_zh, source='Other')
            a, b = module.singleton_merge_event(left), module.singleton_merge_event(other)
            a.summary = b.summary = ' '.join(facts_en)
            self.assertFalse(module.should_merge(left, b))
            self.assertFalse(module.should_merge(other, a))
            self.assertFalse(module.events_should_merge(a, b))
            self.assertFalse(module.events_should_merge(b, a))
            self.assertEqual(len(module.cluster_articles([left, other])), 2)

    def test_price_values_and_effective_stages_remain_with_their_action(self):
        module = load_module()
        texts = ['Apple raises Apple Music prices to $12.99 in October 2026.',
                 '苹果上调 Apple Music 价格至 12.99 美元，将于 2026 年 10 月生效。',
                 'Apple raises Apple Music prices to $14.99 in October 2027.']
        now = module.utc_now().isoformat()
        candidates = [module.Candidate('9to5Mac', f'https://9to5mac.com/price-{i}/', text) for i, text in enumerate(texts)]
        pages = {candidate.url: f'<meta property="article:published_time" content="{now}"><article><p>{text}</p></article>'
                 for candidate, text in zip(candidates, texts)}
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'fetch_url', side_effect=lambda url, *args, **kwargs: pages[url]):
                result = module.run(args)
        events = [event for event in result['events'] + result['deferred_events'] if event.get('claims')]
        self.assertEqual(len(events), 2)
        self.assertEqual(sorted(len(event['sources']) for event in events), [1, 2])
        for event in events:
            years = {q[2] for claim in event['claims'] for q in claim['qualifiers'] if q[1] == 'rollout-year'}
            self.assertEqual(len(years), 1)
            year = years.pop()
            amount = 'usd:12.99' if year == '2026' else 'usd:14.99'
            for claim in event['claims']:
                self.assertIn(('apple-music', 'price-amount', amount), {tuple(q[:3]) for q in claim['qualifiers']})
                self.assertIn(('apple-music', 'rollout-time', 'month:10'), {tuple(q[:3]) for q in claim['qualifiers']})
            self.assertTrue(all(year in fact for fact in event['key_facts']))
        evidence = module.capture_article_evidence('Source', 'https://example.com/multi-price',
            '<article><p>Apple raises Apple Music prices to $12.99 in October 2026 and lowers Apple TV prices to $7.99 in November 2027.</p></article>', 'Apple service prices')
        projections, remaining, excluded = module.project_article_evidence(evidence)
        self.assertEqual(len(projections), 2)
        for projection in projections:
            qualifiers = {q[:3] for q in projection.claim.qualifiers}
            expected = ('2026', 'month:10', 'usd:12.99') if projection.claim.subject == 'apple-music' else ('2027', 'month:11', 'usd:7.99')
            self.assertEqual({q[2] for q in projection.claim.qualifiers if q[1] == 'rollout-year'}, {expected[0]})
            self.assertIn((projection.claim.subject, 'rollout-time', expected[1]), qualifiers)
            self.assertIn((projection.claim.subject, 'price-amount', expected[2]), qualifiers)
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)

    def test_unbound_source_outcome_ignores_observed_tier_and_category(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ('WebKit opens proposals for Interop 2027', 'Apple’s WebKit team opened proposals from September 3 to September 23.', 'strong', 'software_systems'),
            ('Apple wins 20 Creative Arts Emmy Awards', 'Apple won 20 awards across 19 categories.', 'strong', 'software_systems'),
            ('Apple may release a round Apple Watch', 'Mark Gurman reports Apple is considering a round screen; timing is unclear.', 'strong', 'hardware_products'),
            ('AccessoryCo launches a new case for iPhone 18', 'A third-party vendor launches a protective case.', 'weak', 'hardware_products'),
        ]
        for title, text, tier, category in cases:
            for observed_tier, observed_category in [('weak', 'hardware_products'), ('strong', 'software_systems')]:
                with self.subTest(title=title, observed_tier=observed_tier, observed_category=observed_category):
                    article = article_for(module, title, text)
                    article.relevance_tier, article.category = observed_tier, observed_category
                    article.relevance_reason = 'stale observation'
                    profile = module.article_reconciliation_profile(article)
                    module.reconcile_article_relevance(article, profile)
                    self.assertEqual((article.relevance_tier, article.category), (tier, category))

    def test_unbound_assembly_cannot_vote_or_reclassify_summary(self):
        module = load_module()
        from test_relevance_rules import article_for
        first = article_for(module, 'Apple wins 20 Creative Arts Emmy Awards', 'Apple won 20 awards across 19 categories.')
        second = article_for(module, 'Apple earns 20 Creative Arts Emmys', 'Apple earned 20 awards across 19 categories.', source='IT之家')
        for article in (first, second):
            article.category = 'hardware_products'
            article.relevance_tier = 'weak'
            article.relevance_reason = 'stale observation'
        event = module.singleton_merge_event(first)
        event.summary = 'MacBook hardware background'
        with patch.object(module, 'event_category_from_metadata', side_effect=AssertionError('assembly reclassified summary')):
            rebuilt = module.rebuild_event_from_articles(event, [first, second])
        self.assertEqual((rebuilt.category, rebuilt.relevance_tier), ('software_systems', 'strong'))
        self.assertEqual({article.source for article in rebuilt.articles}, {'9to5Mac', 'IT之家'})

    def test_singleton_outcome_uses_source_priority_once(self):
        load_module()
        from apple_news_core.models import ReconciliationProfile
        from apple_news_core.event_reconciler import resolve_reconciliation_outcome, resolve_event_outcome
        for excluded in ('', 'third-party background'):
            with self.subTest(excluded=excluded):
                profile = ReconciliationProfile(
                    event_keys=frozenset({'primary-claim:third-party-platform-native'}), boundary_keys=frozenset(),
                    trusted_direct_action=True, defer_reason=excluded,
                    category_hint='software_systems')
                source = resolve_reconciliation_outcome(profile, observed_tier="", observed_reason="", observed_category="")
                event = resolve_event_outcome([profile])
                self.assertEqual(event[:3], source)
                self.assertEqual(source[0], 'weak' if excluded else 'ecosystem')

    def test_later_configuration_keeps_same_configuration_recall(self):
        module = load_module()
        from test_relevance_rules import article_for
        for capacity in ('256GB', '1TB'):
            with self.subTest(capacity=capacity):
                first = article_for(module, f'Mac Studio with {capacity} RAM launches in October',
                                    f'The {capacity} configuration arrives later than the standard September launch.')
                second = article_for(module, f'Mac Studio {capacity} configuration launching in October',
                                     f'The {capacity} configuration arrives later than the standard September launch.', source='IT之家')
                standard = article_for(module, 'Apple launches new Mac Studio', 'Apple announced the new Mac Studio.')
                events = module.cluster_articles([first, standard, second])
                self.assertEqual(len(events), 2)
                self.assertTrue(any({item.url for item in event.articles} == {first.url, second.url}
                                    for event in events))

    def test_serialized_group_preserves_each_source_outcome(self):
        module = load_module()
        from test_relevance_rules import article_for
        direct = article_for(module, 'Apple wins 20 Emmy Awards', 'Apple won 20 awards across 19 categories.')
        context = article_for(module, 'Opinion: why Apple TV awards matter', 'I think Apple TV deserves more attention.', source='IT之家')
        event = module.rebuild_event_from_articles(module.singleton_merge_event(direct), [direct, context])
        result = module.event_to_dict(event, __import__('datetime').timezone.utc)
        self.assertEqual(result['relevance_tier'], 'strong')
        sources = {source['name']: source for source in result['sources']}
        self.assertEqual(sources[context.source]['relevance_tier'], 'weak')
        self.assertEqual(sources[context.source]['relevance_reason'], context.relevance_reason)
        self.assertTrue(sources[context.source]['relevance_reason'])
        self.assertEqual(sources[direct.source]['relevance_tier'], 'strong')

    def test_compatibility_classification_consumes_source_outcome(self):
        module = load_module()
        with patch.object(module, 'resolve_reconciliation_outcome', return_value=('weak', 'source exclusion', 'hardware_products')) as resolve:
            self.assertEqual(module.classify_relevance_tier('Apple introduces a service', 'Apple announces a service.'),
                             ('weak', 'source exclusion'))
            self.assertEqual(module.choose_category('Apple introduces a service', 'Apple announces a service.'),
                             'hardware_products')
            self.assertGreaterEqual(resolve.call_count, 2)

    def test_editorial_question_needs_an_asserted_source_action(self):
        module = load_module()
        title = 'Would you like iOS 27 to add widgets?'
        summary = 'This is a reader poll about desired changes; Apple has not announced a widget change.'
        self.assertEqual(module.classify_relevance_tier(title, summary)[0], 'weak')

    def test_organization_transfer_keeps_named_owner_and_action(self):
        module = load_module()
        from test_relevance_rules import article_for
        first = article_for(module, 'Cloud Package Hub joins Apple, stays open source',
                            'Cloud Package Hub is joining Apple and will remain open source.')
        second = article_for(module, '平台 Cloud Package Hub 官宣加入苹果，继续开源',
                             'Cloud Package Hub 加入苹果，平台保持开源。', source='IT之家')
        other = article_for(module, 'Studio Build Tools joins Apple, remains open source',
                            'Studio Build Tools is joining Apple.', source='The Verge')
        denial = article_for(module, 'Cloud Package Hub will not join Apple',
                             'The organization denies an ownership transfer.', source='AppleInsider')
        events = module.cluster_articles([first, second, other, denial])
        self.assertEqual(len(events), 3)
        self.assertTrue(any({article.url for article in event.articles} == {first.url, second.url} for event in events))

    def test_joint_participation_is_not_ownership_transfer(self):
        module = load_module()
        from test_relevance_rules import article_for
        coalition = article_for(module, 'Cloud Package Hub joins Apple, Microsoft and Google in open source standards group',
                                'Cloud Package Hub joins the standards coalition alongside Apple; ownership remains independent.')
        purchase = article_for(module, 'Cloud Package Hub acquired by Apple',
                               'Apple acquires Cloud Package Hub and takes ownership.', source='IT之家')
        self.assertEqual(len(module.cluster_articles([coalition, purchase])), 2)
        hardware = article_for(module, 'iPhone camera sensor supplier Optical Sensor Labs acquired by Apple',
                               'Apple takes ownership of Optical Sensor Labs, which builds camera sensors for iPhone.')
        self.assertEqual(module.cluster_articles([hardware])[0].category, 'hardware_products')

    def test_parent_evidence_constraint_survives_source_profile_and_clustering(self):
        module = load_module()
        from test_relevance_rules import article_for
        parent_title = "Shopping guide: Apple products worth buying this year"
        parent_lead = "This shopping guide compares existing products and retailer offers without a new Apple announcement."
        article = article_for(module, "Apple introduces a new iPad", "Apple introduces a new iPad with a brighter display.")
        article.evidence = module.capture_article_evidence(article.source, article.url,
            '<article><p>' + parent_lead + '</p></article>', parent_title)
        self.assertEqual(module.classify_relevance_tier(parent_title, parent_lead)[0], "weak")
        event = module.cluster_articles([article])[0]
        self.assertEqual(event.relevance_tier, "weak", "An unbound rewritten child cannot erase its actual parent evidence form")
        self.assertTrue(event.relevance_reason)

    def test_quantified_title_only_device_revenue_keeps_detail_recall(self):
        module = load_module()
        for title in (
            "Counterpoint：iPhone 17 系列首年批发营收超 1700 亿美元，创历代新高",
            "Research report: iPad wholesale revenue reaches $40 billion in its first year",
        ):
            with self.subTest(title=title):
                candidate = module.Candidate("Source", "https://example.com/report", title)
                self.assertEqual(module.classify_relevance_tier(title, "")[0], "strong")
                self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 70 if "批发营收" in title else 40)
        self.assertEqual(module.classify_relevance_tier("Supplier reports record wholesale revenue",
            "The supplier's own revenue reached $40 billion; Apple iPhone production is background.")[0], "weak")

    def test_discovery_sources_keep_asserted_actions_and_exclude_color_context(self):
        module = load_module()
        from test_relevance_rules import article_for
        for title, lead in (
            ("Apple Announces iOS 27 Release Date", ""),
            ("Apple reports third quarter results", "Apple today announced financial results for its fiscal third quarter."),
            ("Apple shares more details about Apple Intelligence usage limits and terms", "Apple today published a new support article on Apple Intelligence usage terms, limits, and restrictions."),
            ("Dynamic Island now shows three Live Activities", "Apple has updated its iPhone Dynamic Island to show three Live Activities simultaneously."),
        ):
            with self.subTest(title=title):
                self.assertEqual(module.classify_relevance_tier(title, lead)[0], "strong")
                self.assertEqual(module.cluster_articles([article_for(module, title, lead)])[0].relevance_tier, "strong")
        title = "荣耀手机首发体验：全新的设计"
        lead = "荣耀推出自己的安卓手机。" + "屏幕与电池带来均衡体验。" * 100 + "青苹果配色由设计团队主导，报道称组织进行了重组。"
        self.assertEqual(module.classify_relevance_tier(title, lead)[0], "weak")

    def test_detail_recall_does_not_grant_final_tier_to_apple_topics(self):
        module = load_module()
        source = module.build_sources(module.utc_now())[0]
        for title in ("macOS Golden Gate", "iOS 固件下载大全"):
            with self.subTest(title=title):
                candidate = module.Candidate("Source", "https://example.com/topic", title)
                self.assertEqual(module.classify_relevance_tier(title, "")[0], "weak")
                self.assertGreaterEqual(module.candidate_detail_priority(candidate)[0], 70)
                self.assertTrue(module.is_relevant_candidate(candidate, source))
        for title in ('iOS 27: 13 Ways the Messages App is Smarter and Less Annoying',
                      "10 iOS 27 Performance Improvements You'll Actually Notice"):
            candidate = module.Candidate('MacRumors', 'https://example.com/guide/features/', title)
            with self.subTest(guide=title):
                self.assertTrue(module.is_relevant_candidate(candidate, source))
        unrelated = module.Candidate("Source", "https://example.com/other", "Independent robotics company reports revenue", "Apple is only a historical customer.")
        self.assertLess(module.candidate_detail_priority(unrelated)[0], 40)
        feature = module.Candidate("MacRumors", "https://example.com/feature",
            "New Texture and Grain Controls Coming to Photographic Styles With iPhone 18 Pro")
        self.assertTrue(module.is_relevant_candidate(feature, source))
        announced = module.Candidate('MacRumors', 'https://example.com/announcement',
            'Apple Announces iPhone 18 Pro and iPhone 18 Pro Max')
        sparse = module.Candidate('MacRumors', 'https://example.com/battery',
            "iPhone 18 Pro Max Has Longest Battery Life in an iPhone")
        self.assertGreater(module.candidate_detail_priority(announced)[0],
                           module.candidate_detail_priority(sparse)[0])

    def test_independently_bound_action_survives_parent_shopping_form(self):
        module = load_module()
        from dataclasses import replace
        from test_relevance_rules import article_for
        evidence = module.capture_article_evidence("Source", "https://example.com/shopping",
            "<article><p>Siri adds French in October.</p><p>Compare existing accessories before buying.</p></article>",
            "Shopping guide: Apple products worth buying this year")
        evidence = replace(evidence, content_form="buying_advice")
        projections, remaining, excluded = module.project_article_evidence(evidence)
        self.assertEqual(len(projections), 1)
        projection = projections[0]
        article = article_for(module, projection.title, projection.summary, facts=list(projection.key_facts))
        article.source, article.url = evidence.source, evidence.url
        article.evidence, article.bound_claim = evidence, projection.claim
        event = module.cluster_articles([article])[0]
        self.assertEqual(event.relevance_tier, "strong")
        self.assertTrue(any("French in October" in fact for fact in event.key_facts))
        self.assertTrue(remaining)
        module.validate_evidence_dispositions(evidence, projections, remaining, excluded)

    def test_sparse_recall_preserves_known_third_party_and_retail_boundaries(self):
        module = load_module()
        cases = (
            ("王腾公司首款App内测近万人报名！专注睡眠监测：首期仅支持iOS", "独立开发团队发布自有睡眠应用，只有iOS版本，没有Apple平台动作。"),
            ("iPhone 18 Pro天猫全球首发 以旧换新补贴达900元 24期分期免息", "零售商推出iPhone促销补贴和免息分期，苹果没有调整官方价格。"),
        )
        for title, lead in cases:
            for summary in ("", lead):
                with self.subTest(title=title, has_lead=bool(summary)):
                    candidate = module.Candidate("Source", "https://example.com/listing", title, summary)
                    self.assertEqual(module.classify_relevance_tier(title, summary)[0], "weak")
                    self.assertLess(module.candidate_detail_priority(candidate)[0], 40)

    def test_source_profile_retains_its_authoritative_exclusion(self):
        module = load_module()
        from test_relevance_rules import article_for
        article = article_for(module, "iPhone 18 Pro天猫全球首发 以旧换新补贴达900元 24期分期免息",
            "零售商推出iPhone补贴与免息分期，苹果没有调整官方价格。")
        profile = module.article_reconciliation_profile(article)
        outcome = module.resolve_reconciliation_outcome(profile, observed_tier="strong", observed_reason="", observed_category="")
        self.assertEqual(outcome[0], "weak")
        self.assertEqual(profile.relevance_tier, outcome[0])

    def test_fact_selection_preserves_short_owned_spans_with_unbound_sources(self):
        module = load_module()
        from test_relevance_rules import article_for
        text = "Siri adds French in October."
        evidence = module.capture_article_evidence("Rich", "https://example.com/fact-rich",
            "<article><p>" + text + "</p></article>", text)
        projection = module.project_article_evidence(evidence)[0][0]
        rich = article_for(module, text, text, source="Rich", facts=[text])
        rich.url, rich.evidence, rich.bound_claim = evidence.url, evidence, projection.claim
        sparse = article_for(module, "Siri adds French support", "Apple is expanding Siri language support.", source="Sparse")
        facts = module.collect_event_key_facts([rich, sparse])
        self.assertIn(text, facts, "An owned source span must not be dropped by a display-length heuristic")
        event = module.rebuild_event_from_articles(module.singleton_merge_event(rich), [rich, sparse])
        self.assertIn(text, event.key_facts)

    def test_document_actions_bind_local_security_conditions_and_future_limits(self):
        module = load_module()
        now = module.utc_now().isoformat()
        records = [
            ("9to5Mac", "https://9to5mac.com/document-one", "Apple details Audio Intelligence privacy in a new paper", [
                "Apple is launching Audio Intelligence with new Apple Watch hardware. The company has published an 11-page privacy paper about Audio Intelligence on Apple Watch.",
                "Live Rewind shows only the last 15 seconds of speech, and Audio Intelligence includes four specific features.",
                "Audio data is processed inside the Secure Exclave."]),
            ("The Verge", "https://www.theverge.com/document-two", "Apple releases document on Audio Intelligence privacy", [
                "Apple released a document explaining privacy protections for Audio Intelligence on Apple Watch.",
                "Text from Audio Intelligence will sync with end-to-end encryption if you have a device passcode and use iCloud’s two-factor authentication. Passwords will repair leaked passwords in a future update."]),
            ("MacRumors", "https://www.macrumors.com/document-three", "Apple shares more details about Apple Intelligence usage limits and terms", [
                "Apple today published a new support article on Apple Intelligence usage terms and limits.",
                "Apple Intelligence",
                "Apple says it will implement usage limits on Apple Intelligence in the future, but does not offer specifics on the limits or when they take effect.",
                "Home camera video summaries allow up to 1 camera in the 2 TB plan, 2 cameras in the 6 TB plan and 5 cameras in the 12 TB plan."]),
        ]
        candidates = [module.Candidate(source, url, title) for source, url, title, _ in records]
        pages = {url: '<meta property="article:published_time" content="' + now + '"><article>'
                 + ''.join('<p>' + text + '</p>' for text in units) + '</article>' for _, url, _, units in records}
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'fetch_url', side_effect=lambda url, *args, **kwargs: pages[url]):
                result = module.run(args)
        events = result['events'] + result['deferred_events']
        docs = [event for event in events if any(claim['action'] == 'document-publication' for claim in event.get('claims', []))]
        self.assertEqual(len(docs), 2)
        privacy = next(event for event in docs if len(event['sources']) == 2)
        limits = next(event for event in docs if len(event['sources']) == 1)
        for event in docs:
            self.assertEqual((event['relevance_tier'], event['category']), ('strong', 'software_systems'))
            self.assertLessEqual(set(event['key_facts']), set(event['must_include_facts']))
            for fact in event['fact_sources']:
                for origin in fact['origins']:
                    self.assertEqual(origin['location_status'], 'located')
                    evidence = result['source_evidence'][origin['article_id']]
                    unit = next(unit for unit in evidence['units'] if unit['unit_id'] == origin['unit_id'])
                    self.assertEqual(unit['text'][origin['start']:origin['end']], fact['text'])
        self.assertIn('privacy', privacy['title'])
        self.assertIn('usage', limits['title'])
        privacy_facts = ' '.join(privacy['key_facts'])
        for required in ('11-page', '15 seconds', 'four specific features', 'Secure Exclave', 'end-to-end encryption', 'device passcode and use iCloud’s two-factor authentication'):
            self.assertIn(required, privacy_facts)
        self.assertNotIn('Passwords will repair', privacy_facts)
        self.assertIn(records[2][3][0], limits['key_facts'])
        limit_facts = ' '.join(limits['key_facts'])
        for required in ('future', 'does not offer specifics', '1 camera in the 2 TB', '2 cameras in the 6 TB', '5 cameras in the 12 TB'):
            self.assertIn(required, limit_facts)
        review = [unit for item in result['final_brief_queue'] for unit in item.get('unprocessed_evidence', [])]
        self.assertTrue(any(unit['text'] == records[1][3][-1].split('. ')[1] for unit in review))

    def test_document_binding_requires_apple_publication_and_specific_document_subject(self):
        module = load_module()
        for title, text in [
            ("Apple Intelligence usage limits could change", "A reporter expects Apple to publish a support article someday, but Apple has not announced a document."),
            ("Developer publishes Apple Intelligence usage limits analysis", "A developer published an independent paper about Apple Intelligence usage limits."),
            ("Apple releases a new privacy document", "Apple released a privacy document about an unrelated service. Audio Intelligence was discussed last year."),
        ]:
            with self.subTest(title=title):
                evidence = module.capture_article_evidence("Source", "https://example.com/document-negative",
                    '<article><p>' + text + '</p></article>', title)
                self.assertFalse(any(projection.claim.action == 'document-publication'
                                     for projection in module.project_article_evidence(evidence)[0]))

    def test_compatibility_event_keys_depend_on_source_profiles_not_assembled_summary(self):
        module = load_module()
        from test_relevance_rules import article_for
        article = article_for(module, "iPhone files stolen from a supplier", "Hackers stole iPhone logic board schematics and chip data sheets.")
        event = module.cluster_articles([article])[0]
        expected = module.event_summary_merge_keys(event)
        self.assertTrue(expected)
        event.title, event.summary, event.key_facts = "", "Unrelated marketing text", []
        self.assertEqual(module.event_summary_merge_keys(event), expected)

    def test_roundup_child_support_consumes_shared_source_outcome(self):
        module = load_module()
        text = "Apple releases iOS 27 with new system features."
        with patch.object(module, 'resolve_reconciliation_outcome', return_value=('weak', 'source lacks a current action', 'software_systems')) as resolver:
            self.assertFalse(module.is_apple_roundup_item(text))
            self.assertTrue(resolver.called)

    def test_named_service_rollouts_keep_family_claims_and_dual_sim_conditions(self):
        module = load_module()
        now = module.utc_now().isoformat()
        records = [
            ("MacRumors", "https://www.macrumors.com/family", "Apple Adds AppleCare One Family Plan", [
                "Apple adds an AppleCare One family plan for up to six people at $49.99 per month.",
                "An individual has three theft and loss claims each year, while the family shares six claims per year."]),
            ("IT之家", "https://www.ithome.com/1/123/400.htm", "苹果推出 AppleCare One 家庭版", [
                "苹果推出 AppleCare One 家庭版，支持六人共享。家庭每年合计可申请六次失窃或遗失理赔。"]),
            ("MacRumors", "https://www.macrumors.com/handoff", "iOS 27 iPhone Handoff launches with carrier support", [
                "Apple is adding iPhone Handoff in iOS 27 so two iPhones share the same phone number.",
                "With Dual SIM, both eSIMs must use supported carriers, switch together, and be configured separately.",
                "T-Mobile and Deutsche Telekom support it at launch. Carrier fees may apply."]),
            ("快科技", "https://news.mydrivers.com/1/123/400.htm", "苹果推出 iPhone Handoff 功能", [
                "苹果推出iPhone Handoff功能，两部iPhone共用同一个电话号码。", "同一时刻仅有一台设备处于蜂窝激活状态。"]),
        ]
        candidates = [module.Candidate(source, url, title) for source, url, title, _ in records]
        pages = {url: '<meta property="article:published_time" content="' + now + '"><article>'
                 + ''.join('<p>' + text + '</p>' for text in units) + '</article>' for _, url, _, units in records}
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                 patch.object(module, 'fetch_url', side_effect=lambda url, *args, **kwargs: pages[url]):
                result = module.run(args)
        events = result['events'] + result['deferred_events']
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertEqual(len(event['sources']), 2)
            self.assertEqual((event['relevance_tier'], event['category']), ('strong', 'software_systems'))
            self.assertLessEqual(set(event['key_facts']), set(event['must_include_facts']))
        family = next(event for event in events if 'AppleCare' in event['title'])
        handoff = next(event for event in events if 'Handoff' in event['title'])
        self.assertIn(records[0][3][1], family['key_facts'])
        self.assertIn(records[2][3][1], handoff['key_facts'])
        self.assertFalse(any('claims' in fact for fact in handoff['key_facts']))

    def test_source_report_and_personal_inference_remain_distinct(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ('A foldable Mac is years away, but Apple is still working on it',
             "There have long been reports and rumours about a foldable Mac. A recent report said the project was cancelled, but I don’t think that is accurate. Personally, I think the concept makes sense.", 'weak', 'hardware_products'),
            ('苹果或签铠侠NAND长期协议：3到5年合约无价格上限',
             '据TrendForce报道，苹果近期在NAND闪存采购上转向签订长期供应协议，有传闻称苹果与铠侠达成协议。', 'strong', 'hardware_products'),
            ('Supplier sues Apple over alleged Face ID patent infringement',
             'A biometric technology supplier alleges that Apple Face ID infringes its patents and seeks a jury trial.', 'strong', 'software_systems'),
        ]
        for title, summary, tier, category in cases:
            with self.subTest(title=title):
                event = module.cluster_articles([article_for(module, title, summary)])[0]
                self.assertEqual((event.relevance_tier, event.category), (tier, category))

    def test_new_bindings_do_not_own_another_actor_or_product_action(self):
        module = load_module()
        cases = [
            ('Apple adds AppleCare One Family plan', 'Apple adds an AppleCare One family plan at $49.99 per month.', 'Google raises the monthly price of its family plan to $29.99.'),
            ('Apple adds AppleCare One Family plan', 'Apple adds an AppleCare One family plan at $49.99 per month.', 'Apple raises the monthly price of Apple Music to $12.99.'),
            ('Apple releases Audio Intelligence privacy paper', 'Apple published a privacy paper about Audio Intelligence on Apple Watch.', 'Microsoft publishes a new document about Copilot usage limits.'),
        ]
        for title, owned, other in cases:
            with self.subTest(other=other):
                evidence = module.capture_article_evidence('Source', 'https://example.com/local-owner',
                    '<article><p>' + owned + ' ' + other + '</p></article>', title)
                projections, remaining, excluded = module.project_article_evidence(evidence)
                module.validate_evidence_dispositions(evidence, projections, remaining, excluded)
                self.assertTrue(projections)
                self.assertNotIn(other, [fact for projection in projections for fact in projection.key_facts])
                units = {unit.unit_id: unit.text for unit in evidence.units}
                self.assertIn(other, [units[key][start:end] for key, start, end in remaining])

    def test_specific_procurement_claim_overrides_generic_source_kind_hint(self):
        module = load_module()
        title = '苹果或签铠侠NAND长期协议：3到5年合约无价格上限'
        lead = '据TrendForce报道，苹果近期在NAND闪存采购上转向签订长期供应协议。'
        profile = module.build_reconciliation_profile(title=title, lead=lead,
            identity=module.build_event_identity(title, lead), exact_facets=(), regions=(),
            event_kind='third_party_ecosystem')
        self.assertEqual(profile.event_kind_hint, 'hardware_market')
        self.assertEqual(module.resolve_reconciliation_outcome(profile, observed_tier='', observed_reason='', observed_category='')[0], 'strong')

    def test_distinct_source_measurements_survive_display_fact_limit(self):
        module = load_module()
        from test_relevance_rules import article_for
        facts = ['Apple won 20 Creative Arts Emmy awards this year across its television shows.',
                 'Apple had 89 nominations across 15 programs at this year’s Emmy awards.']
        article = article_for(module, 'Apple wins 20 Creative Arts Emmy awards', facts[0], facts=facts)
        with patch.object(module, 'MAX_KEY_FACTS', 1), patch.object(module, 'MAX_OFFICIAL_KEY_FACTS', 1):
            event = module.rebuild_event_from_articles(module.singleton_merge_event(article), [article])
        self.assertIn(facts[1], event.key_facts)
        self.assertIn(facts[1], module.event_must_include_facts(event))

    def test_source_conditions_survive_frontend_fact_selection(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ('Apple Watch with a round display rumored', 'Apple reportedly considered a round display for Apple Watch.',
             'Apple considered a round screen for Apple Watch, though it is unclear if the design will ever reach the market.'),
            ('BASF subsidiary sues Apple over Face ID patent infringement', 'BASF subsidiary TrinamiX alleges Apple Face ID infringes its patents.',
             'The company is requesting a jury trial in the U.S. District Court for the Western District of Texas.'),
            ('长鑫存储回应与苹果合作计划', '长鑫存储表示正在探索与苹果的合作机会。',
             '长鑫存储表示，公司并未直接点名苹果，也没有披露任何具体客户信息。'),
        ]
        for title, summary, condition in cases:
            with self.subTest(title=title):
                article = article_for(module, title, summary, facts=[summary])
                article.evidence = module.capture_article_evidence(article.source, article.url,
                    '<article><p>' + summary + '</p><p>' + condition + '</p></article>', title)
                event = module.rebuild_event_from_articles(module.singleton_merge_event(article), [article])
                self.assertIn(condition, event.key_facts)
                self.assertIn(condition, module.event_must_include_facts(event))

    def test_deferred_internal_reporting_attribution_has_local_visible_review(self):
        module = load_module()
        now = module.utc_now().isoformat()
        title = '消息称苹果仍在探索折叠 Mac / iPad，触控键盘成最大挑战'
        attribution = '而该媒体从内部渠道获悉，虽然苹果调整研发优先级，暂缓发布其首款折叠产品，但内部并未取消该开发方向。'
        text = '科技媒体9to5Mac发布博文，讨论折叠Mac和iPad。该媒体认为触控键盘仍有挑战。'
        candidate = module.Candidate('IT之家', 'https://www.ithome.com/0/123/456.htm', title)
        page = '<meta property="article:published_time" content="' + now + '"><article><p>' + text + '</p><p>' + attribution + '</p></article>'
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), patch.object(module, 'fetch_url', return_value=page):
                result = module.run(args)
        review = [item for item in result['final_brief_queue'] if item.get('unprocessed_evidence')]
        self.assertTrue(any(unit['text'] == attribution for item in review for unit in item['unprocessed_evidence']))
        item = next(item for item in review if any(unit['text'] == attribution for unit in item['unprocessed_evidence']))
        self.assertIn('attribution', item['reason'])
        self.assertEqual(item['source_urls'], [candidate.url])
        self.assertIn(attribution, module.render_brief_scaffold(result))

    def test_unbound_compound_projections_keep_local_assignments_and_remainder(self):
        module = load_module()
        owned = ['Harbor premieres on Apple TV on October 9 with a ten-episode season.',
                 'Mountain premieres on Apple TV on November 12 with an eight-episode season.']
        remainder = 'Apple TV will introduce audio descriptions for additional languages in a future update.'
        for title in ('Apple TV announces two new shows', 'Apple TV announces streaming date for Harbor, new Mountain trailer'):
            candidate = module.Candidate('9to5Mac', 'https://9to5mac.com/two-shows/', title)
            now = module.utc_now().isoformat()
            page = f'<meta property="article:published_time" content="{now}"><article><h1>{title}</h1><p>' + ' '.join([*owned, remainder]) + '</p></article>'
            with tempfile.TemporaryDirectory() as directory:
                args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
                with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), patch.object(module, 'fetch_url', return_value=page):
                    result = module.run(args)
            events = result['events'] + result['deferred_events']
            self.assertEqual(len(events), 2)
            for fact in owned:
                event = next(event for event in events if fact in event['key_facts'])
                self.assertIn(fact, event['must_include_facts'])
                self.assertFalse(any(remainder in value for value in event['key_facts']))
                self.assertFalse(any(other in value for other in owned if other != fact for value in event['key_facts']))
                matches = [item for item in event['fact_sources'] if item['text'] == fact]
                self.assertTrue(matches)
                for item in matches:
                    self.assertTrue(item['origins'])
                    for origin in item['origins']:
                        self.assertEqual(origin['location_status'], 'located')
                        evidence = result['source_evidence'][origin['article_id']]
                        unit = next(unit for unit in evidence['units'] if unit['unit_id'] == origin['unit_id'])
                        self.assertEqual(unit['text'][origin['start']:origin['end']], fact)
            reviews = [item for item in result['final_brief_queue'] if item.get('unprocessed_evidence')]
            self.assertTrue(any(unit['text'] == remainder for item in reviews for unit in item['unprocessed_evidence']))
            review = next(item for item in reviews if any(unit['text'] == remainder for unit in item['unprocessed_evidence']))
            self.assertEqual(review['source_urls'], [candidate.url])
            self.assertTrue(review['reason'])
            self.assertEqual([unit['text'] for unit in review['unprocessed_evidence']], [remainder])
            for unit in review['unprocessed_evidence']:
                original = next(source_unit for source_unit in result['source_evidence'][review['evidence_id']]['units'] if source_unit['unit_id'] == unit['unit_id'])
                self.assertEqual(original['text'][unit['start']:unit['end']], unit['text'])
            self.assertTrue(result['evidence_dispositions'])
            self.assertIn(remainder, module.render_brief_scaffold(result))

    def test_hardware_disclosure_relations_keep_target_action_and_stage(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        def article(title, lead):
            return article_for(module, title, lead, facts=[lead])
        def merges(left, right):
            return module.should_merge(left, event_for(module, right))
        dimension = article('iPhone 21 Pro could be thicker than iPhone 20 Pro', 'A leak says the iPhone 21 Pro body and camera housing grow thicker.')
        same = article('iPhone 21 Pro 机身增厚', '爆料称 iPhone 21 Pro 机身和后置摄像头平台变厚。')
        self.assertTrue(merges(dimension, same))
        for title, lead in (
            ('iPhone 20 Pro could be thicker', 'A leak says the iPhone 20 Pro body and camera housing grow thicker.'),
            ('iPhone 21 Pro could be thinner', 'A leak says the iPhone 21 Pro body and camera housing get thinner.'),
            ('Apple announces a thicker iPhone 21 Pro body', 'Apple today officially announced that the iPhone 21 Pro body and camera housing are thicker.'),
            ('iPhone 21 Pro logic board diagrams leaked', 'The iPhone 21 Pro board schematics reveal chip packaging; the body may grow thicker.'),
        ):
            self.assertFalse(merges(dimension, article(title, lead)), title)
        weight = article('iPhone 21 Pro Max could be heavier', 'A leak says iPhone 21 Pro Max weight is about 250 grams.')
        different = article('iPhone 21 Pro Max could be heavier', 'A leak says iPhone 21 Pro Max weight is about 270 grams.')
        self.assertFalse(merges(weight, different))
        foreign_weight = article('iPhone 21 Pro Max could be heavier', 'Samsung says the Galaxy handset weight is about 250 grams.')
        with self.subTest(boundary="foreign-weight"):
            self.assertFalse(merges(weight, foreign_weight))
        filing = article('iPhone 21 Pro battery capacities leaked', 'Leaked filings list iPhone 21 Pro and iPhone 21 Pro Max battery capacities.')
        interpretation = article('iPhone 21 Pro vs iPhone 21 Pro Max: latest leak', 'If the leaked battery capacities are accurate, iPhone 21 Pro Max gains 10% and iPhone 21 Pro gains 1%.')
        self.assertTrue(merges(filing, interpretation))
        values = article('iPhone 21 Pro battery capacities leaked', 'Leaked filings list iPhone 21 Pro at 4000mAh in the U.S., while iPhone 21 Pro Max is 5000mAh in the U.S.')
        for swapped in (
            'Leaked filings list iPhone 21 Pro at 5000mAh in the U.S., while iPhone 21 Pro Max is 4000mAh in the U.S.',
            'Leaked filings list iPhone 21 Pro at 4500mAh in the U.S., while iPhone 21 Pro Max is 5000mAh in the U.S.',
        ):
            with self.subTest(capacity=swapped):
                self.assertFalse(merges(values, article(values.title, swapped)), swapped)

        for title, lead in (
            ('iPhone 21 Pro vs iPhone 21 Pro Max battery life review', 'We tested iPhone 21 Pro and iPhone 21 Pro Max battery life in daily use.'),
            ('iPhone 20 Pro battery capacities leaked', 'Leaked filings list iPhone 20 Pro and iPhone 20 Pro Max battery capacities.'),
        ):
            self.assertFalse(merges(filing, article(title, lead)), title)

    def test_source_stage_continues_across_neutral_clauses_and_inflection(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [('forecast', 'MacBook Neo preorders expected in November', 'A report claims MacBook Neo preorders will begin November 6.', False), ('adjacent-singular', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo has been revealed by Apple today. The newly announced model will be available for preorder that day.', True), ('background-singular', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo has been revealed by Apple today. Customers can compare finishes before placing orders. The newly announced model will be available for preorder that day.', True), ('adjacent-plural', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo has been revealed by Apple today. The newly announced models will be available for preorder that day.', True), ('background-plural', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo has been revealed by Apple today. Customers can compare finishes before placing orders. The newly announced models will be available for preorder that day.', True), ('foreign', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. Galaxy Book has been revealed by Samsung today. The newly announced model will be available for preorder that day.', False), ('historical', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo was revealed by Apple last year. The model will be available for preorder that day.', False), ('modal', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. A report claims MacBook Neo may be revealed by Apple. The model could be available for preorder that day.', False), ('name-report', 'Apple foldable iPhone reportedly named iPhone Prism', 'A report claims Apple will name its foldable iPhone iPhone Prism.', False), ('name-natural', '苹果 iPhone Prism 亮相，正式进入折叠屏市场', '苹果终于正式进入折叠屏手机市场，推出首款折叠式 iPhone，产品名称确定为 iPhone Prism。', True), ('name-modal', '苹果 iPhone Prism 或将亮相', '消息称苹果终于可能进入折叠屏手机市场，推出首款折叠式 iPhone，产品名称或将确定为 iPhone Prism。', False), ('name-history', '苹果 iPhone Prism 命名传闻', '苹果去年正式进入折叠屏手机市场，推出首款折叠式 iPhone。消息称后继产品名称可能为 iPhone Prism。', False)]
        profiles = [module.article_reconciliation_profile(article_for(module, title, lead, source='Synthetic'+str(index), facts=[lead]))
                    for index, (_, title, lead, _) in enumerate(rows)]
        for index, (label, title, lead, expected) in enumerate(rows):
            with self.subTest(label=label):
                actual = any(key.endswith(':announced') and '-stage:' in key for key in profiles[index].separation_keys)
                self.assertEqual(actual, expected)
                if expected:
                    report = profiles[8 if index >= 8 else 0]
                    self.assertEqual(module.profile_pair_decision(report, profiles[index]), 'conflict')
                    if index < 8:
                        self.assertEqual(module.profile_pair_decision(profiles[1], profiles[index]), 'match')
        for background in ('Apple announces MacBook Air today.', 'Samsung reveals Galaxy Book today.'):
            lead = rows[1][2].replace('The newly announced model', background + ' The newly announced models')
            profile = module.article_reconciliation_profile(article_for(module, rows[1][1], lead, facts=[lead]))
            with self.subTest(switched=background):
                self.assertNotIn('preorder-stage:announced', profile.separation_keys)
        for subject in ('苹果的竞争对手三星', '苹果供应商'):
            lead = rows[9][2].replace('苹果终于', subject + '终于')
            profile = module.article_reconciliation_profile(article_for(module, rows[8][1], lead, facts=[lead]))
            self.assertNotIn('product-disclosure-stage:announced', profile.separation_keys)

    def test_local_product_announcement_owns_preorder_and_naming_stage(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [('forecast', 'MacBook Neo preorders expected in November', 'A report claims MacBook Neo preorders will begin November 6.'), ('formal-product', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo has been revealed by Apple today. The newly announced model will be available for preorder that day.'), ('formal-preorder', 'MacBook Neo preorders officially announced', 'Apple announced MacBook Neo preorders will begin November 6.'), ('foreign-product', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. Galaxy Book has been revealed by Samsung today.'), ('historic-product', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. An earlier MacBook Neo was revealed by Apple last year.'), ('name-report', "Apple's foldable iPhone reportedly named iPhone Prism", 'A report claims Apple will name its foldable iPhone iPhone Prism.'), ('name-formal-chinese', '苹果 iPhone Prism 亮相，正式进入折叠屏市场', '苹果正式进入折叠屏手机市场，推出首款折叠式 iPhone，产品名称确定为 iPhone Prism。'), ('name-modal-chinese', '苹果 iPhone Prism 或将亮相', '消息称苹果可能进入折叠屏手机市场，推出首款折叠式 iPhone，产品名称或将确定为 iPhone Prism。')]
        profiles = [module.article_reconciliation_profile(article_for(module, title, lead, source='Synthetic'+str(index), facts=[lead]))
                    for index, (_, title, lead) in enumerate(rows)]
        self.assertEqual(module.profile_pair_decision(profiles[0], profiles[1]), 'conflict')
        self.assertEqual(module.profile_pair_decision(profiles[1], profiles[2]), 'match')
        for index in (3, 4):
            self.assertNotIn('preorder-stage:announced', profiles[index].separation_keys)
        self.assertEqual(module.profile_pair_decision(profiles[5], profiles[6]), 'conflict')
        self.assertEqual(module.profile_pair_decision(profiles[5], profiles[7]), 'match')
        for sentence in ('MacBook Air has been revealed by Apple today.',
                         'MacBook Neo may have been revealed by Apple today.',
                         'MacBook Neo was revealed by Apple last year.'):
            lead = rows[1][2].replace('MacBook Neo has been revealed by Apple today.', sentence)
            profile = module.article_reconciliation_profile(article_for(module, rows[1][1], lead, facts=[lead]))
            self.assertNotIn('preorder-stage:announced', profile.separation_keys)

    def test_navigation_outside_article_preserves_body_short_facts(self):
        module = load_module()
        title = 'Apple adds camera calibration controls to iOS 29'
        lead = 'Apple announced new camera calibration controls for iOS 29 today.'
        html = '<html><head><title>Apple adds camera calibration controls to iOS 29</title></head><body>\n<div class="top"><ul><li><a href="/mobile">Compact site</a></li><li><a href="/login">Member portal</a></li></ul></div>\n<div class="pathway"><ul><li><a href="/">Home</a> &gt; Updates &gt; Current article</li></ul></div>\n<div class="news_info"><h1>Apple adds camera calibration controls to iOS 29</h1>\n<p>Apple announced new camera calibration controls for iOS 29 today.</p>\n<p>The iOS 29 camera calibration controls provide the following modes:</p><ul><li>Grid</li><li>Waveform</li><li>0 ms preview delay</li></ul>\n<p>Apple lists the camera calibration limits below, in frames per second:</p><table><tr><td>Preview</td><td>48</td></tr><tr><td>Capture</td><td>96</td></tr></table></div>\n<div class="share-count"><ul><li>0</li></ul></div></body></html>'
        for heading in ('h1', 'div', 'nested'):
            with self.subTest(heading=heading):
                page = html.replace('<h1>', '<div>').replace('</h1>', '</div>') if heading != 'h1' else html
                if heading == 'nested':
                    page = page.replace('<p>Apple announced', '<div><p>Apple announced', 1).replace('today.</p>', 'today.</p></div>', 1)
                candidate = module.Candidate('9to5Mac', 'https://example.test/camera-calibration', title)
                now = module.utc_now()
                extracted = (title, lead, [lead], now, now.isoformat(), 'detail', 'detail')
                with tempfile.TemporaryDirectory() as directory:
                    args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
                    with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), \
                         patch.object(module, 'select_detail_candidates', return_value=[candidate]), \
                         patch.object(module, 'fetch_detail_page_texts', return_value=[page]), \
                         patch.object(module, 'extract_article', return_value=extracted):
                        result = module.run(args)
                facts = [fact['text'] for event in result['events'] + result['deferred_events'] for fact in event['fact_sources']]
                reviews = [unit['text'] for item in result['final_brief_queue'] for unit in item.get('unprocessed_evidence', [])]
                for noise in ('Compact site', 'Member portal', 'Home > Updates > Current article', '0'):
                    self.assertNotIn(noise, facts + reviews)
                for body in ('Grid', 'Waveform', '0 ms preview delay', 'Preview | 48', 'Capture | 96'):
                    self.assertIn(body, facts + reviews)
                    self.assertIn(body, result['final_brief_markdown'])
                self.assertTrue(any('frames per second' in value for value in facts + reviews))

    def test_prepared_normal_budget_keeps_unselected_source_fact_visible(self):
        module = load_module()
        from test_relevance_rules import article_for
        from dataclasses import replace
        title = 'Report: Apple tests camera calibration controls for iOS 29'
        lead = 'A new source report describes camera calibration controls Apple is testing for iOS 29.'
        target = 'The ability to preview layered histograms with “desktop-like controls”'
        views, articles, pages, extracted = [], [], [], []
        now = module.utc_now()
        for index, source in enumerate(['9to5Mac', 'The Verge']):
            numbers = [f'The iOS 29 camera calibration preset {index*12+n+1} allows a maximum exposure of {index*12+n+2} seconds.' for n in range(12)]
            facts = [lead, *numbers, *([target] if index == 0 else [])]
            article = article_for(module, title, lead, source=source, facts=facts)
            article.url = f'https://example.test/calibration-budget-{index}'
            html = '<article><h1>' + title + '</h1><p>' + lead + '</p>' + ''.join('<p>' + value + '</p>' for value in numbers)
            html += '<p>The same source report also describes this camera capability:</p>' + ('<ul><li>' + target + '</li></ul>' if index == 0 else '') + '</article>'
            article.evidence = module.capture_article_evidence(source, article.url, html, title)
            views.append(module.prepare_source_fact_view(article))
            articles.append(article); pages.append(html)
            extracted.append((title, lead, facts, now, now.isoformat(), 'detail', 'detail'))
        source_fact = next(fact for fact in views[0].normal if fact.text == target)
        single = module.resolve_event_fact_plan(views[:1], relevance_tier='strong', base_limit=module.MAX_KEY_FACTS, official_limit=module.MAX_OFFICIAL_KEY_FACTS)
        self.assertIn(target, [fact.text for fact in single.facts])
        plan = module.resolve_event_fact_plan(views, relevance_tier='strong', base_limit=module.MAX_KEY_FACTS, official_limit=module.MAX_OFFICIAL_KEY_FACTS)
        self.assertNotIn(target, [fact.text for fact in plan.facts])
        pending = [fact for fact in plan.unprocessed if fact.text == target]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].origins, source_fact.origins)
        self.assertTrue(pending[0].reason)
        # Supply an already reconciled group: this is the fact-budget/JSON
        # contract, not an assertion about this synthetic pair's identity.
        candidates = [module.Candidate(article.source, article.url, title) for article in articles]
        for located_output in (True, False):
            with self.subTest(located_output=located_output):
                def reconciled_group(sources):
                    event = module.rebuild_event_from_articles(module.singleton_merge_event(sources[0]), sources)
                    if not located_output:
                        # The serialization boundary must also handle a source
                        # prepared fact explicitly declared unlocated.
                        pending = tuple(replace(fact, origins=tuple((src, url, aid, '', 0, 0)
                            for src, url, aid, _unit, _start, _end in fact.origins))
                            if fact.text == target else fact for fact in event.fact_plan.unprocessed)
                        event.fact_plan = replace(event.fact_plan, unprocessed=pending)
                    return [event]
                with tempfile.TemporaryDirectory() as directory:
                    args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
                    with patch.object(module, 'collect_candidates_from_sources', return_value=candidates), \
                         patch.object(module, 'select_detail_candidates', return_value=candidates), \
                         patch.object(module, 'fetch_detail_page_texts', return_value=pages), \
                         patch.object(module, 'extract_article', side_effect=extracted), \
                         patch.object(module, 'cluster_articles', side_effect=reconciled_group):
                        result = module.run(args)
                matches = [(item, unit) for item in result['final_brief_queue'] for unit in item.get('unprocessed_evidence', []) if unit['text'] == target]
                self.assertEqual(len(matches), 1)
                item, span = matches[0]
                self.assertEqual(item['source_urls'], [articles[0].url])
                if located_output:
                    original = next(unit for unit in articles[0].evidence.units if unit.unit_id == span['unit_id'])
                    self.assertEqual(original.text[span['start']:span['end']], target)
                else:
                    self.assertEqual(span['location_status'], 'source-text-only')
                    self.assertFalse(span['unit_id'])
                    self.assertNotIn('start', span)
                    self.assertNotIn('end', span)
                self.assertIn(target, module.render_brief_scaffold(result))
        # Equal short keys and empty origins are not proof of text coverage.
        lead_fact = next(fact for fact in views[0].normal if fact.text == lead)
        for located in (True, False):
            with self.subTest(located=located):
                origin = source_fact.origins if located else ((articles[0].source, articles[0].url, articles[0].evidence.article_id, '', 0, 0),)
                first = replace(lead_fact, key='shared', origins=origin, roles=frozenset())
                later = replace(source_fact, key='shared', origins=origin, roles=frozenset())
                view = replace(views[0], normal=(first, later), structured=(), owned=(), price=(), responses=(), unprocessed=())
                collided = module.resolve_event_fact_plan([view], relevance_tier='strong', base_limit=12, official_limit=24)
                self.assertIn(target, [fact.text for fact in collided.unprocessed])

        # A same-text fact from another source does not cover an unlocated
        # origin that arrived only after the selection budget was filled.
        other_origin = ((articles[1].source, articles[1].url, articles[1].evidence.article_id, '', 0, 0),)
        duplicate = replace(lead_fact, origins=other_origin, roles=frozenset())
        duplicate_view = replace(views[1], normal=(*(fact for fact in views[1].normal if fact.text != duplicate.text), duplicate))
        duplicate_plan = module.resolve_event_fact_plan([views[0], duplicate_view], relevance_tier='strong', base_limit=1, official_limit=1)
        self.assertTrue(any(fact.text == duplicate.text and other_origin[0] in fact.origins
                            for fact in (*duplicate_plan.facts, *duplicate_plan.required, *duplicate_plan.unprocessed)))

    def test_preselected_short_source_facts_have_final_local_disposition(self):
        module = load_module()
        title = 'Report: Apple tests new iPhone camera controls'
        lead = 'A source claims Apple is testing new controls for the next iPhone.'
        short = ['Macro preview.', 'Quick zoom.']
        candidate = module.Candidate('9to5Mac', 'https://9to5mac.com/short-source-facts/', title)
        now = module.utc_now()
        html = '<article><h1>' + title + '</h1><p>' + lead + '</p><p>' + ' '.join(short) + '</p></article>'
        # Replay the already selected source-fact boundary; preserve its real
        # raw evidence and run the production projection/plan/JSON assembly.
        extracted = (title, lead, [lead, *short], now, now.isoformat(), 'detail', 'detail')
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=[candidate]), \
                 patch.object(module, 'fetch_url', return_value=html), \
                 patch.object(module, 'extract_article', return_value=extracted):
                result = module.run(args)
        events = result['events'] + result['deferred_events']
        self.assertTrue(events)
        scaffold = module.render_brief_scaffold(result)
        for value in short:
            matches = [(item, unit) for item in result['final_brief_queue']
                       for unit in item.get('unprocessed_evidence', []) if unit['text'] == value]
            self.assertTrue(matches, value)
            self.assertEqual(len(matches), 1)
            item, span = matches[0]
            self.assertEqual(item['source_urls'], [candidate.url])
            self.assertTrue(item['reason'])
            unit = next(unit for unit in result['source_evidence'][item['evidence_id']]['units']
                        if unit['unit_id'] == span['unit_id'])
            self.assertEqual(unit['text'][span['start']:span['end']], value)
            self.assertIn(value, scaffold)
            self.assertFalse(any(value in event.get('must_include_facts', []) for event in events))

    def test_unlocated_short_selected_fact_keeps_source_text_without_requirement(self):
        module = load_module()
        from test_relevance_rules import article_for
        text = 'Macro-preview.'
        article = article_for(module, 'Report: Apple tests new iPhone camera controls',
            'A source claims Apple is testing new controls for the next iPhone.', facts=[text])
        article.evidence = module.capture_article_evidence(article.source, article.url,
            '<article><p>Macro–preview.</p></article>', article.title)
        event = module.rebuild_event_from_articles(module.singleton_merge_event(article), [article])
        final = module.event_to_dict(event, module.ZoneInfo('Asia/Singapore'))
        self.assertIn(text, final['key_facts'])
        self.assertNotIn(text, final.get('must_include_facts', []))
        matches = [fact for fact in final['fact_sources'] if fact['text'] == text]
        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0]['owned'])
        self.assertTrue(matches[0]['origins'])
        self.assertTrue(all(origin['location_status'] == 'source-text-only' and not origin['unit_id']
                            for origin in matches[0]['origins']))

    def test_unlocated_projection_fact_is_preserved_without_invented_span(self):
        module = load_module()
        from test_relevance_rules import article_for
        fact = 'Harbor will premiere on Apple TV on October 9 with a ten-episode season.'
        article = article_for(module, 'Apple TV Harbor premiere', fact, facts=[fact])
        article.evidence = module.capture_article_evidence(article.source, article.url,
            '<article><p>Harbor will premiere on Apple TV on October 9 with a ten–episode season.</p></article>', article.title)
        assigned, _, _ = module.projected_source_dispositions(article.evidence, [article.key_facts], article.key_facts)
        self.assertEqual(assigned, ((),))
        article.projected_fact_spans = assigned[0]
        event = module.rebuild_event_from_articles(module.singleton_merge_event(article), [article])
        self.assertIn(fact, event.key_facts)
        self.assertIn(fact, module.event_must_include_facts(event))
        retained = next(item for item in event.fact_plan.facts if item.text == fact)
        self.assertFalse(retained.owned)
        self.assertTrue(retained.origins)
        self.assertTrue(all(not origin[3] for origin in retained.origins))

    def test_compound_release_facts_follow_platform_and_stage(self):
        module = load_module()
        title = 'Apple releases iOS 27 RC; Apple releases iPadOS 27 stable'
        facts = ['Apple releases iOS 27 RC build 24A335 for developers.',
                 'Apple releases iPadOS 27 stable build 24A336 for all users.']
        variants = module.compound_article_variants(title, ' '.join(facts), facts)
        self.assertEqual(len(variants), 2)
        for child_title, _summary, child_facts in variants:
            expected = facts[1] if 'ipados' in child_title.lower() else facts[0]
            self.assertIn(expected, child_facts)
            self.assertNotIn(facts[1] if expected == facts[0] else facts[0], child_facts)

    def test_compound_product_projection_does_not_reverse_price_direction(self):
        module = load_module()
        title = 'Apple cuts iPhone 18 Pro starting price and adds variable-aperture camera'
        facts = ['Apple cuts the iPhone 18 Pro starting price to $699.',
            'Apple adds a variable-aperture camera to iPhone 18 Pro.']
        variants = module.compound_product_action_variants(title, ' '.join(facts), facts)
        self.assertEqual(len(variants), 2)
        price = next(item for item in variants if facts[0] in item[2])
        self.assertNotIn('increase', price[0].lower())
        self.assertNotIn(facts[1], price[2])

    def test_localized_content_schedule_support_requires_source_facts(self):
        module = load_module()
        from test_relevance_rules import article_for
        english = article_for(module, 'Apple TV announces Harbor streaming date',
            'Harbor will premiere on January 22, 2027 with a ten-episode season.')
        cases = [
            ('苹果发布《海港》（Harbor）首支预告片', '该剧定于明年 1 月 22 日在 Apple TV 平台首播，首季共 10 集。', True),
            ('苹果发布《海港》（Harbor）首支预告片', '该剧定于明年 2 月 22 日在 Apple TV 平台首播，首季共 10 集。', False),
            ('苹果发布《海港》（Harbor）首支预告片', '该剧定于 2028 年 1 月 22 日在 Apple TV 平台首播，首季共 10 集。', False),
            ('Apple TV announces Mountain streaming date', 'Mountain will premiere on January 22, 2027 with a ten-episode season.', False),
            ('苹果发布《山峰》首支预告片', '该剧定于明年 1 月 22 日在 Apple TV 平台首播，首季共 10 集。', False),
            ('苹果发布《海港》（Harbor）首支预告片', '该剧发布新预告片。此前另一部作品定于 1 月 22 日在 Apple TV 平台首播，首季共 10 集。', False),
        ]
        for title, lead, expected in cases:
            with self.subTest(title=title, lead=lead):
                other = article_for(module, title, lead, 'Other Source')
                self.assertEqual(module.should_merge(english, module.singleton_merge_event(other)), expected)
                self.assertEqual(module.should_merge(other, module.singleton_merge_event(english)), expected)
                self.assertEqual(len(module.cluster_articles([english, other])), 1 if expected else 2)

    def test_source_written_number_results_keep_work_count_relations(self):
        module = load_module()
        from test_relevance_rules import article_for
        title = 'Apple TV leads Emmys wins so far'
        lead = 'Apple TV won 20 Creative Arts Emmy awards.'
        breakdown = ('As it stands right now, Widows Bay has earned eight wins, Pluribus got four, '
            'Margo’s Got Money Troubles won three, Palm Royale also got three, '
            'and documentary Mr Scorsese also earned one.')
        article = article_for(module, title, lead + ' ' + breakdown, facts=[lead])
        article.evidence = module.capture_article_evidence(article.source, article.url,
            '<article><p>' + lead + '</p><p>' + breakdown + '</p></article>', title)
        event = module.rebuild_event_from_articles(module.singleton_merge_event(article), [article])
        self.assertIn(breakdown, event.key_facts)
        self.assertIn(breakdown, module.event_must_include_facts(event))
        fact = next(fact for fact in event.fact_plan.facts if fact.text == breakdown)
        self.assertTrue(fact.origins)
        units = {unit.unit_id: unit.text for unit in article.evidence.units}
        self.assertTrue(all(units[key][start:end] == breakdown
            for _, _, _, key, start, end in fact.origins))

    def test_source_conditions_do_not_follow_pronouns_across_subject_changes(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ('Supplier sues Apple over Face ID patents', 'TrinamiX sues Apple over Face ID patents.',
             'Separately, Microsoft filed an unrelated contract case.', 'The company is requesting a jury trial in the New York court.'),
            ('Apple Watch round display rumored', 'Apple is considering a round Apple Watch.',
             'Samsung is testing a new foldable phone.', 'It is unclear whether this design will be released.'),
        ]
        for title, primary, foreign, condition in cases:
            with self.subTest(title=title):
                article = article_for(module, title, ' '.join((primary, foreign, condition)), facts=[primary])
                article.evidence = module.capture_article_evidence(article.source, article.url,
                    '<article><p>' + ' '.join((primary, foreign, condition)) + '</p></article>', title)
                event = module.rebuild_event_from_articles(module.singleton_merge_event(article), [article])
                self.assertNotIn(condition, event.key_facts)
                self.assertIn(condition, [fact.text for fact in event.fact_plan.unprocessed])

    def test_named_os_component_support_requires_local_source_action_and_version(self):
        module = load_module()
        title = "iOS 26.6: New features, release date, more"
        summary = "iOS 26.6 is coming soon after several developer and public betas."
        for fact, expected in (
            ("Apple says iOS 26.6 optimizes the Spotlight index to prepare for iOS 27.", "strong"),
            ("Apple says iOS 25.6 optimizes the Spotlight index to prepare for iOS 26.", "weak"),
            ("Microsoft says Windows optimizes the Spotlight index to prepare for a new release.", "weak"),
        ):
            with self.subTest(fact=fact):
                tier, reason = module.classify_relevance_tier(title, summary, [fact], "9to5Mac")
                self.assertEqual(tier, expected, reason)

    def test_supplier_capacity_support_requires_an_apple_allocation(self):
        module = load_module()
        title = "TSMC announces new chip plant capacity"
        for summary, tier in (
            ("Apple chipmaker TSMC announced new chip plants. Apple is expected to use capacity from these facilities.", "strong"),
            ("Apple chipmaker TSMC announced new chip plants. Nvidia will use the new capacity, while Apple is mentioned as an existing customer.", "weak"),
        ):
            with self.subTest(summary=summary):
                result, reason = module.classify_relevance_tier(title, summary, [], "MacRumors")
                self.assertEqual(result, tier, reason)

    def test_local_event_operations_and_trade_in_objects_stay_distinct(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [['resources', 'Apple releases design resources for iPhone 22 Pro', 'Apple released design resources to help developers prepare apps after its September event. The documentation describes adaptive layouts for iPhone 22 Pro.'], ['store', 'Apple Store goes offline before September event', 'Apple temporarily closed its online store to prepare pages before the September event for iPhone 22 Pro.'], ['values', 'Apple updates iPad trade-in values', 'Apple updated its trade-in values today. The iPad Pro is worth up to $540, down from $610.'], ['condition-policy', 'Apple reportedly offers better trade-in terms for scratched iPads', 'Apple reportedly increases trade-in offers for iPads with minor cosmetic scratches. Previously those devices required an inspection; the eligibility policy now accepts minor cosmetic damage.'], ['resources-paraphrase', 'Apple publishes design resources for iPhone 22 Pro', 'Apple released design resources to help developers prepare apps after its September event. The documentation describes adaptive layouts for iPhone 22 Pro.'], ['values-paraphrase', 'Apple adjusts iPad trade-in values', 'Apple updated its trade-in values today. The iPad Pro is worth up to $540, down from $610.'], ['preorder-control', 'MacBook Neo preorders begin November 6', 'Customers can place preorders for MacBook Neo beginning November 6. MacBook Neo has been revealed by Apple today. The newly announced model will be available for preorder that day.'], ['preorder-control-paraphrase', 'MacBook Neo preorders officially announced', 'Apple announced MacBook Neo preorders will begin November 6.']]
        articles = [article_for(module, title, summary, source="Synthetic" + str(index), facts=[summary])
                    for index, (_, title, summary) in enumerate(rows)]
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        for left, right, expected in ((0, 1, False), (2, 3, False), (0, 4, True), (2, 5, True), (6, 7, True)):
            with self.subTest(left=rows[left][0], right=rows[right][0]):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
                self.assertEqual(len(module.cluster_articles([articles[left], articles[right]])), 1 if expected else 2)

    def test_local_retail_and_event_actions_keep_background_and_owner_boundaries(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [
            ("Apple updates iPad Pro trade-in values", "Apple updated iPad Pro trade-in payouts to $540; the existing cosmetic eligibility policy is unchanged."),
            ("Apple lowers maximum iPad Pro trade-in payout to $540", "Apple updated iPad Pro trade-in values from $610 to $540 today."),
            ("Apple changes trade-in eligibility for scratched iPads", "Apple now accepts minor scratches without inspection. Existing maximum iPad Pro payouts remain $540."),
            ("Apple reportedly offers better trade-in terms for scratched iPads", "Apple reportedly increases trade-in offers for iPads with minor cosmetic scratches. Previously those devices required an inspection; the eligibility policy now accepts minor cosmetic damage."),
            ("Apple releases design resources for iPhone 22 Pro", "Apple released design resources to help developers prepare apps after its September event."),
            ("Microsoft publishes design resources for iPhone 22 Pro", "Microsoft published its own design resources to help developers prepare apps after Apple's September event."),
            ("Apple Store goes offline before September event", "Apple temporarily closed its online store to prepare pages before the September event for iPhone 22 Pro."),
            ("Apple closes online store ahead of September event", "Apple temporarily closed its online store before the September event for iPhone 22 Pro."),
        ]
        articles = [article_for(module, title, summary, source="Source" + str(i), facts=[summary])
                    for i, (title, summary) in enumerate(rows)]
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        for left, right, expected in ((0, 1, True), (2, 3, True), (0, 2, False), (4, 5, False), (6, 7, True)):
            with self.subTest(left=left, right=right):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
        staff = article_for(module, "Apple opens staff lottery for September event",
                            "Apple opened an internal lottery for retail staff to support the September event.")
        preorder = article_for(module, "Apple announces iPhone 22 Pro preorders for September 14",
                               "Apple announced iPhone 22 Pro preorders will begin September 14. Apple previously opened an internal lottery for retail staff to support the September event.")
        preorder_profile = module.article_reconciliation_profile(preorder)
        self.assertFalse(any(key.startswith("event-operation-action:") for key in preorder_profile.separation_keys))
        self.assertNotEqual(module.profile_pair_decision(module.article_reconciliation_profile(staff),
                                                        module.article_reconciliation_profile(preorder)), "match")
        groups = module.cluster_articles(articles[:4])
        self.assertEqual(sorted(len(event.articles) for event in groups), [2, 2])

    def test_retail_action_uses_owned_later_clause_not_campaign_context(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [['valuation', 'Apple updates iPad trade-in values', 'Apple updated its trade-in values today, lowering payouts for returning iPad models. The iPad Pro is worth up to $540, down from $610.'], ['later-policy', 'Apple reportedly offering a trade-in incentive for iPad upgrades', 'New iPads are expected to cost more this season. Apple is reportedly offering higher trade-in values for devices with minor cosmetic defects. Apple increased prices of other products earlier this year.'], ['first-policy', 'Apple reportedly offering a trade-in incentive for iPad upgrades', 'Apple is reportedly offering higher trade-in values for devices with minor cosmetic defects. New iPads are expected to cost more this season. Apple increased prices of other products earlier this year.'], ['store', 'Apple online store closes ahead of iPad event', 'Apple temporarily closed its online store to update pages before the iPad event. The store is expected to reopen following the presentation.'], ['store', 'Apple online store closes before "Radiant Horizon" iPad event', 'Apple temporarily closed its online store to update pages for the "Radiant Horizon" event. The store will reopen after the iPad presentation.'], ['values', 'Apple updates trade-in values following "Radiant Horizon" event', 'Apple updated its trade-in values today, lowering payouts for returning iPad models. The iPad Pro is worth up to $540, down from $610.']]
        articles = [article_for(module, title, summary, source="Synthetic" + str(i), facts=[summary])
                    for i, (_, title, summary) in enumerate(rows)]
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        for left, right, expected in ((0, 1, False), (0, 2, False), (1, 2, True), (0, 3, False), (4, 5, False)):
            with self.subTest(left=left, right=right):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
                self.assertEqual(len(module.cluster_articles([articles[left], articles[right]])), 1 if expected else 2)
        for unrelated in (
            "Microsoft is reportedly offering higher trade-in values for devices with minor cosmetic defects.",
            "Apple previously offered higher trade-in values for devices with minor cosmetic defects.",
            "Apple did not change trade-in eligibility for devices with minor cosmetic defects.",
        ):
            with self.subTest(unrelated=unrelated):
                article = article_for(module, rows[1][1], "New iPads are expected to cost more this season. " + unrelated)
                profile = module.article_reconciliation_profile(article)
                self.assertNotIn("retail-trade-in-action:eligibility-policy", profile.separation_keys)
        announcement = module.build_event_identity('Apple announces "Radiant Horizon" event',
                                                    'Apple scheduled the "Radiant Horizon" event for September 14.')
        self.assertIn("radiant-horizon", announcement.title_named_subjects)
        for campaign in ("晴空", "Radiant Horizon"):
            with self.subTest(chinese_campaign=campaign):
                shop = article_for(module, f'苹果在线商店在“{campaign}”发布会前暂停服务',
                                   f'苹果在线商店在“{campaign}”发布会前暂时关闭，正在更新 iPad 页面。')
                values = article_for(module, f'苹果在“{campaign}”发布会后调整 iPad 折抵价',
                                     '苹果调整 iPad 官方折抵估值，目前 iPad Pro 最高折抵价为540美元。')
                self.assertNotEqual(module.profile_pair_decision(module.article_reconciliation_profile(shop),
                                                                module.article_reconciliation_profile(values)), "match")
        direct_chinese = module.build_event_identity('苹果公布“Radiant Horizon”发布会', '苹果公布活动时间。')
        self.assertIn("radiant-horizon", direct_chinese.title_named_subjects)
        groups = module.cluster_articles([articles[4], articles[5], articles[1], articles[2]])
        self.assertEqual(sorted(len(event.articles) for event in groups), [1, 1, 2])

    def test_known_retail_actions_do_not_merge_through_body_named_subjects(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [['store-event-context', 'Apple online store closes before iPhone 21 Pro event', 'Apple temporarily closed its online store to update pages before the iPhone 21 Pro event. The page displays the "Radiant Horizon" event logo.'], ['value-event-context', 'Apple updates iPhone trade-in values', 'Apple updated trade-in payouts following its "Radiant Horizon" event, lowering iPhone values. The iPhone 20 Pro is worth up to $520, down from $580.'], ['store-product-background', 'Apple online store closes before iPhone 21 Pro event', 'Apple temporarily closed its online store to update pages before the iPhone 21 Pro event. The company also sells Apple Watch models.'], ['value-product-background', 'Apple updates iPhone trade-in values', 'Apple updated trade-in payouts today, lowering iPhone values. Apple Watch trade-in values were unchanged last month.']]
        articles = [article_for(module, title, summary, source="Synthetic" + str(i), facts=[summary])
                    for i, (_, title, summary) in enumerate(rows)]
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        for left, right, expected in ((0, 1, False), (2, 3, False), (0, 2, True), (1, 3, True)):
            with self.subTest(left=left, right=right):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
        self.assertEqual(sorted(len(event.articles) for event in module.cluster_articles(articles)), [2, 2])

    def test_source_action_authority_does_not_come_from_price_or_body_labels(self):
        module = load_module()
        from dataclasses import replace
        from test_relevance_rules import article_for
        rows = [['preorder', 'iPhone 19 Pro preorders expected to start this Friday', 'A carrier claims that preorders for iPhone 19 Pro will start on Friday, November 8. Apple has not announced the schedule.'], ['pricing', '有关“2400美元”的苹果折叠屏手机研发故事', '报道回顾苹果折叠屏手机研发经历。苹果曾考虑将价格定为2399美元，现在仍在讨论价格方案。'], ['policy', 'Apple reportedly offering a trade-in incentive to encourage iPhone upgrades', 'New iPhones are expected to cost more this season. Apple is reportedly softening the expense for returning customers by offering higher trade-in values for devices with cosmetic scratches. Apple increased prices of other products last winter. The upcoming iPhone 22 Pro models are expected to be more expensive. Customers are waiting for the final announcement. Apple will expand its trade-in program to offer better pricing for devices with cosmetic scratches.'], ['roadmap', 'Apple iPhone 22 roadmap update', 'Apple reportedly plans to launch the regular iPhone 22 next spring instead of the autumn. This is a change to the base model release schedule.'], ['store', 'Apple Store is down ahead of iPhone 22 Pro announcements', 'The Apple Store is down to update its product pages. Other products expected at the event include AirPods and Apple Watch Series 15.'], ['cases', '苹果为iPhone 22 Pro上线多款保护壳', '苹果今天推出iPhone 22 Pro保护壳，有两种材料可选。苹果同时更新了适用于 AirPods 的挂绳功能。'], ['store-cn', '苹果线上商店已下线维护，迎接iPhone 22 Pro发布会', '苹果已将在线Apple Store暂时关闭，以便更新页面。商店页面显示“Radiant Horizon”活动标识。发布会将展示iPhone 22 Pro 和 Apple Watch。'], ['design', 'Apple updates Design Resources with iPhone 22 Pro bezels', 'Following today’s “Radiant Horizon” event, Apple has updated its Design Resources portal with Photoshop and PNG product bezels for iPhone 22 Pro. Apple Watch assets are also listed in the portal.'], ['store-control', '苹果在线商店暂时关闭以更新iPhone 22 Pro页面', '苹果线上商店已下线维护，正在更新iPhone 22 Pro产品页面。页面显示“Radiant Horizon”活动标识。'], ['design-control', 'Apple has updated Design Resources for iPhone 22 Pro', 'Apple has updated its Design Resources portal with Photoshop and PNG bezels for iPhone 22 Pro after the “Radiant Horizon” event.'], ['roadmap-control', 'Apple iPhone 22 roadmap update', 'Apple is expected to launch the regular iPhone 22 next spring rather than autumn.'], ['policy-control', 'Apple reportedly offering a trade-in incentive to encourage iPhone upgrades', 'Apple is reportedly offering higher trade-in values for devices with cosmetic scratches. Returning customers now qualify despite these minor marks.'], ['preorder-control', 'iPhone 19 Pro preorders expected to start this Friday', 'Another carrier says iPhone 19 Pro preorders are expected to begin Friday, November 8. Apple has not confirmed this schedule.']]
        articles = []
        for i, (_, title, summary) in enumerate(rows):
            article = article_for(module, title, summary, source="Synthetic" + str(i), facts=[summary])
            article.evidence = replace(module.capture_article_title_evidence(
                article.source, article.url, article.title, article.summary, tuple(article.key_facts)), content_form="news")
            articles.append(article)
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        with self.subTest(field="preorder-not-price"):
            self.assertNotIn("price-change", profiles[0].identity.title_actions)
        with self.subTest(field="owned-eligibility"):
            self.assertIn("retail-trade-in-action:eligibility-policy", profiles[2].separation_keys)
        for left, right, expected in ((0, 1, False), (2, 3, False), (4, 5, False), (6, 7, False),
                                      (6, 8, True), (7, 9, True), (3, 10, True), (2, 11, True), (0, 12, True)):
            with self.subTest(left=rows[left][0], right=rows[right][0]):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
        expected_groups = [{0, 12}, {1}, {2, 11}, {3, 10}, {4, 6, 8}, {5}, {7, 9}]
        actual_groups = [{articles.index(article) for article in event.articles}
                         for event in module.cluster_articles(articles)]
        self.assertEqual({frozenset(group) for group in actual_groups},
                         {frozenset(group) for group in expected_groups})

    def test_source_predicate_extensions_preserve_owner_and_price_units(self):
        module = load_module()
        from test_relevance_rules import article_for
        title = "Apple reportedly offering a trade-in incentive to encourage iPhone upgrades"
        for summary, expected in (
            ("Apple is reportedly easing the cost for returning customers by offering higher trade-in values for devices with cosmetic scratches.", True),
            ("Apple will expand its trade-in program to offer better pricing for devices with cosmetic scratches.", True),
            ("Apple is preparing new iPhones while Microsoft is offering higher trade-in values for devices with cosmetic scratches.", False),
            ("Apple is preparing new iPhones, and Google offers higher trade-in values for devices with cosmetic scratches.", False),
            ("Apple previously expanded its trade-in program to offer higher values for devices with cosmetic scratches.", False),
            ("Apple will not expand its trade-in program to offer higher values for devices with cosmetic scratches.", False),
        ):
            with self.subTest(summary=summary):
                profile = module.article_reconciliation_profile(article_for(module, title, summary, facts=[summary]))
                self.assertEqual("retail-trade-in-action:eligibility-policy" in profile.separation_keys, expected)
        for title, expected in (
            ("iPhone 19 Pro preorders expected to start this Friday", False),
            ("iPhone 19 Pro production could start next spring", False),
            ("iPhone 19 Pro sales may start at 8 AM", False),
            ("iPhone 19 Pro could start at $1399", True),
            ("iPhone 19 Pro pricing expected to rise", True),
        ):
            with self.subTest(price_title=title):
                self.assertEqual(module.is_future_apple_product_price_forecast_story(title, title), expected)

    def test_concrete_body_actions_keep_named_targets_and_current_stage(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ("Apple retail tool trial report", "Apple is testing a new retail tool called Session Notes that transcribes conversations.",
             "primary-claim:first-party-tool:session-notes:pilot-testing", True),
            ("Apple retail tool trial report", "Google is testing a new retail tool called Session Notes that transcribes conversations.",
             "primary-claim:first-party-tool:session-notes:pilot-testing", False),
            ("Apple retail tool trial report", "Apple is updating its stores. Google is piloting Session Notes to transcribe conversations.",
             "primary-claim:first-party-tool:session-notes:pilot-testing", False),
            ("Apple retail tool trial report", "Apple previously tested a tool called Session Notes to transcribe conversations.",
             "primary-claim:first-party-tool:session-notes:pilot-testing", False),
            ("Apple tool roadmap mentions ‘Session Notes’", "Apple is testing Session Notes as a hardware prototype for its new tools.",
             "primary-claim:first-party-tool:session-notes:pilot-testing", False),
            ("Mac Pro project report", "Apple developed M8 Extreme and M9 Extreme chips for the Mac Pro but decided not to release them.",
             "primary-claim:mac-pro:cancelled-chip-configurations:m8-extreme+m9-extreme", True),
            ("Mac Pro project report", "Apple developed M8 Extreme and M9 Extreme chips for the Mac Pro and will release them next year.",
             "primary-claim:mac-pro:cancelled-chip-configurations:m8-extreme+m9-extreme", False),
            ("Mac Pro project report", "Apple developed M8 Extreme and M9 Extreme chips for Mac Studio but cancelled that project.",
             "primary-claim:mac-pro:cancelled-chip-configurations:m8-extreme+m9-extreme", False),
            ("Mac Pro project report", "Apple cancelled its camera app while continuing M8 Extreme and M9 Extreme development for Mac Pro.",
             "primary-claim:mac-pro:cancelled-chip-configurations:m8-extreme+m9-extreme", False),
            ("US senators urge Apple to abandon plans for Chinese-made chips", "During the memory shortage, Apple requested to buy processor chips from a new supplier.",
             "primary-claim:apple-memory-sourcing:component-procurement-policy-pressure", False),
            ("US senators urge Samsung to abandon plans for Chinese-made chips", "Apple requested to buy memory chips from CXMT.",
             "primary-claim:apple-memory-sourcing:component-procurement-policy-pressure", False),
            ("US senators urge Apple to abandon plans for Chinese-made chips", "Apple previously purchased memory chips from YMTC.",
             "primary-claim:apple-memory-sourcing:component-procurement-policy-pressure", False),
            ("Apple Watch Series 12 and Ultra 4: What to expect", "According to Gurman, Samsung watch models are in late-stage testing for September.",
             "primary-claim:apple-watch:series-12+ultra-4:late-stage-testing:september", False),
        ]
        for title, summary, key, expected in cases:
            with self.subTest(summary=summary):
                profile = module.article_reconciliation_profile(article_for(module, title, summary, facts=[summary]))
                self.assertEqual(key in profile.event_keys, expected)

    def test_body_named_occasion_does_not_authorize_an_unrelated_primary_action(self):
        module = load_module()
        from dataclasses import replace
        from test_relevance_rules import article_for
        rows = [['store', '苹果线上商店已下线维护 迎接 iPhone 22 Pro 发布会', '苹果已将在线 Apple Store 暂时关闭，以便更新产品页面。页面显示“Radiant Horizon”活动标识。苹果预计将在稍后推出 iPhone 22 Pro。'], ['launch', "The wait is over: Apple's iPhone 22 Pro is here", 'Apple has revealed iPhone 22 Pro during today’s “Radiant Horizon” event. The phone has a revised camera and a brighter display. Retail sales are expected to begin next month.'], ['store-control', '苹果在线商店暂时关闭以更新 iPhone 22 Pro 页面', '苹果线上商店已下线维护，正在更新 iPhone 22 Pro 产品页面。页面显示“Radiant Horizon”活动标识。'], ['launch-control', 'Apple reveals iPhone 22 Pro', 'Apple has revealed iPhone 22 Pro during today’s “Radiant Horizon” event. Its camera and display have been updated. Retail sales are expected to begin next month.']]
        articles = []
        for index, (_, title, summary) in enumerate(rows):
            article = article_for(module, title, summary, source="Synthetic" + str(index), facts=[summary])
            article.evidence = replace(module.capture_article_title_evidence(
                article.source, article.url, article.title, article.summary, tuple(article.key_facts)), content_form="news")
            articles.append(article)
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        from apple_news_core.event_matcher import identity_pair_decision
        self.assertNotEqual(identity_pair_decision(profiles[0].identity, profiles[1].identity), "match")
        self.assertIn("primary-claim-predicate:online-store-temporary-closure", profiles[0].separation_keys)
        for index in (1, 3):
            with self.subTest(announcement=index):
                self.assertIn("primary-claim:iphone-22-pro:product-announcement", profiles[index].event_keys)
                self.assertIn("delay-roadmap", profiles[index].identity.actions)
                self.assertNotIn("primary-claim-predicate:reported-launch-window", profiles[index].separation_keys)
        for left, right, expected in ((0, 1, False), (0, 2, True), (1, 3, True)):
            with self.subTest(pair=(left, right)):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
        events = module.cluster_articles(articles)
        self.assertEqual({frozenset(a.url for a in event.articles) for event in events},
                         {frozenset(articles[i].url for i in group) for group in ((0, 2), (1, 3))})
        for summary in (
            "Apple may have revealed iPhone 22 Pro. Retail sales are expected to begin next month.",
            "Apple previously revealed iPhone 22 Pro. Retail sales are expected to begin next month.",
            "Apple has revealed iPhone 22 Pro during last year's event. Retail sales are expected to begin next month.",
            "Microsoft has revealed iPhone 22 Pro. Retail sales are expected to begin next month.",
            "Apple has revealed iPhone 23 Pro. Retail sales are expected to begin next month.",
            "Apple has closed its online store. Apple has revealed iPhone 22 Pro during the event.",
        ):
            with self.subTest(unsupported=summary):
                profile = module.article_reconciliation_profile(article_for(module, rows[1][1], summary, facts=[summary]))
                self.assertNotIn("primary-claim:iphone-22-pro:product-announcement", profile.event_keys)

    def test_title_actions_require_title_evidence_and_configurations_keep_their_subject(self):
        module = load_module()
        from test_relevance_rules import article_for
        from apple_news_core.event_identity import build_event_identity
        for title, expected in (("Apple iPhone roadmap update", False),
                                ("Apple raises iPhone prices", True),
                                ("iPhone 19 Pro may launch at $1,399 starting price", True),
                                ("消息称苹果 iPhone 19 Pro 均为万元机", True),
                                ("苹果 iPhone Ultra 起步价突破1.5万元", True)):
            with self.subTest(title=title):
                identity = build_event_identity(title, "Last year Apple raised prices.",
                                                facets=("apple-product-price-increase",))
                self.assertEqual("price-change" in identity.title_actions, expected)
                self.assertEqual("primary-intent:product-price-change" in identity.title_components, expected)
        for title, name in (("Apple Invites App Updated With New Features", "apple-invites"),
                            ("Apple's Sports app expands soccer coverage", "apple-sports")):
            with self.subTest(app=title):
                identity = build_event_identity(title, "")
                self.assertIn(name, identity.title_named_subjects)
                self.assertIn("feature-change", identity.title_actions)
        sports = module.article_reconciliation_profile(article_for(module,
            "Apple's Sports app expands soccer coverage", "Apple Sports adds soccer leagues."))
        self.assertNotIn("changed-object:processor", sports.separation_keys)
        inputs = [
            ("Apple iPad roadmap update", "New entry-level iPad will use a faster chip and add Apple Intelligence."),
            ("Apple iPad roadmap update", "The entry-level iPad gets a faster chip and Apple Intelligence."),
            ("Apple iPad roadmap update", "New iPad Pro will use a faster chip and add Apple Intelligence."),
            ("Apple iPad roadmap update", "The entry-level iPad gets a new screen and a camera."),
            ("Apple iPad roadmap update", "The entry-level iPad will not get a faster chip or Apple Intelligence."),
        ]
        articles = [article_for(module, *item, source="Synthetic" + str(i)) for i, item in enumerate(inputs)]
        for other, expected in ((1, True), (2, False), (3, False), (4, False)):
            with self.subTest(configuration=other):
                events = module.cluster_articles([articles[0], articles[other]])
                self.assertEqual(len(events), 1 if expected else 2)

    def test_price_objects_and_preorder_stages_remain_distinct_through_cluster(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        cases = [
            (("Apple updates trade-in values for iPhone", "Apple raises trade-in values for iPhone this month."),
             ("Apple raises iPhone 21 Pro prices", "Apple raises the iPhone 21 Pro starting price to $1399."), False),
            (("iPhone 21 Pro preorders expected to start next Monday", "A source claims iPhone 21 Pro preorders will begin on August 17."),
             ("iPhone 21 Pro preorders officially announced", "Apple announced iPhone 21 Pro will be available to pre-order on August 17."), False),
            (("iPhone 21 Pro preorders officially announced", "Apple announced iPhone 21 Pro will be available to pre-order on August 17."),
             ("Apple confirms iPhone 21 Pro preorders open August 17", "Apple announced that iPhone 21 Pro preorders begin August 17."), True),
        ]
        forecast = ("iPhone 21 Pro preorders expected to start next Monday",
                    "A source claims iPhone 21 Pro preorders will begin on August 17.")
        official = ("Apple confirms iPhone 21 Pro preorders open August 17",
                    "Apple announced that iPhone 21 Pro preorders begin August 17.")
        passive = ("iPhone 21 Pro preorder dates revealed",
                   "Preorder dates for iPhone 21 Pro have been revealed by Apple. Customers will be able to pre-order on August 17.")
        cases.extend(((forecast, passive, False), (official, passive, True)))
        switched = ("iPhone 21 Pro preorder dates revealed",
                    "Preorder dates for iPhone 21 Pro have been revealed by Apple. Customers can pre-order MacBook Pro on August 17.")
        uncertain_passive = ("iPhone 21 Pro preorder dates revealed",
                             "Preorder dates for iPhone 21 Pro may have been revealed by Apple. Customers can pre-order on August 17.")
        cases.extend(((official, switched, False), (official, uncertain_passive, False)))
        for modifier in ("today", "has today", "has now officially", "recently"):
            announcement = ("iPhone 21 Pro preorders begin August 17",
                            f"Apple {modifier} announced iPhone 21 Pro will be available to pre-order on August 17.")
            cases.extend(((forecast, announcement, False), (official, announcement, True)))
        for left_input, right_input, expected in cases:
            with self.subTest(left=left_input[0], right=right_input[0]):
                left = article_for(module, *left_input, source="MacRumors")
                right = article_for(module, *right_input, source="9to5Mac")
                for a, b in ((left, right), (right, left)):
                    self.assertEqual(module.should_merge(a, event_for(module, b)), expected)
                self.assertEqual(len(module.cluster_articles([left, right])), 1 if expected else 2)


    def test_nonprice_prepared_response_keeps_its_own_qualification_visible(self):
        module = load_module()
        from apple_news_core.models import PreparedFact, SourceFactView
        from dataclasses import replace
        title = 'Supplier responds to Apple cooperation reports'
        target = 'The company says product quality and supply stability determine competitiveness; customer details remain subject to public disclosure.'
        other = 'On memory production, the company says performance improved; production details remain subject to public disclosure.'
        evidence = module.capture_article_evidence('Source', 'https://example.test/cooperation', '<article><p>'+target+'</p><p>'+other+'</p></article>', title)
        def prepared(text):
            unit = next(unit for unit in evidence.units if unit.text == text)
            return PreparedFact(text, 'public disclosure', origins=(('Source', evidence.url, evidence.article_id, unit.unit_id, 0, len(text)),))
        response, unrelated = prepared(target), prepared(other)
        view = SourceFactView('Source', evidence.url, 1, module.utc_now(), False, 2, False,
            normal=(unrelated,), responses=(response,), display_title=title)
        for views in ([view], [view, replace(view, compact_hardware_price=True, responses=(), normal=())]):
            with self.subTest(mixed_price=len(views)>1):
                plan = module.resolve_event_fact_plan(views, relevance_tier='strong', base_limit=1, official_limit=1)
                carried = [fact for fact in (*plan.facts, *plan.required, *plan.unprocessed) if fact.text == target]
                self.assertTrue(carried)
                self.assertTrue(all(fact.origins == response.origins for fact in carried))
                self.assertNotIn(target, [fact.text for fact in plan.required])
                self.assertEqual(sum(fact.text == target for fact in plan.unprocessed), 1)
                self.assertTrue(plan.unprocessed[0].reason)

    def test_compacted_price_response_origins_follow_selected_clauses(self):
        module = load_module()
        from apple_news_core.models import PreparedFact, SourceFactView
        from apple_news_core.event_reconciler import resolve_event_fact_plan
        def fact(text, article, roles=()):
            return PreparedFact(text, text.lower(), roles=frozenset(roles),
                origins=((article, 'https://example.test/' + article, article, 'unit', 0, len(text)),))
        unrelated = fact('The base phone is expected to arrive in the spring.', 'unrelated')
        cases = [
            ([fact('An analyst expects investors to consider pricing and demand.', 'analyst'), unrelated],
             {'analyst'}, ('An analyst expects',)),
            ([fact('Apple says it must begin raising prices on some products.', 'prices', ('begin-raising',)),
              fact('Apple says it is working tirelessly to find solutions.', 'solutions', ('solutions',)), unrelated],
             {'prices', 'solutions'}, ('begin raising prices', 'find solutions')),
        ]
        for responses, expected, clauses in cases:
            with self.subTest(expected=expected):
                view = SourceFactView('source', 'https://example.test/source', 1, module.utc_now(),
                    False, len(responses), True, responses=tuple(responses))
                plan = resolve_event_fact_plan([view], relevance_tier='strong', base_limit=24, official_limit=32)
                for output in (plan.facts, plan.required):
                    self.assertEqual(len(output), 1)
                    self.assertTrue(output[0].origins)
                    self.assertEqual({origin[2] for origin in output[0].origins}, expected)
                    for clause in clauses:
                        self.assertIn(clause, output[0].text)


    def test_safari_mcp_integration_requires_matching_platform_and_preview_version(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        left = article_for(module, "Safari MCP server lets coding agents inspect websites",
            "Apple says Safari Technology Preview 247 includes the Safari MCP server for coding agents.", source="9to5Mac")
        for title, lead, expected in (
            ("苹果 Safari 技术预览版 247 引入 MCP 服务", "苹果在 Safari Technology Preview 247 引入 Safari MCP Server，支持编程智能体检查网页。", True),
            ("苹果 Safari 技术预览版 248 引入 MCP 服务", "苹果在 Safari Technology Preview 248 引入 Safari MCP Server，支持编程智能体检查网页。", False),
            ("Chrome introduces MCP server for coding agents", "Google introduces a Chrome MCP server to inspect websites. Safari also has an MCP server.", False),
        ):
            with self.subTest(title=title):
                right = article_for(module, title, lead, source="IT之家")
                for a, b in ((left, right), (right, left)):
                    self.assertEqual(module.should_merge(a, event_for(module, b)), expected)
                self.assertEqual(len(module.cluster_articles([left, right])), 1 if expected else 2)


    def test_unbound_structural_rows_and_short_options_have_local_final_dispositions(self):
        module = load_module()
        rows = [f'iPhone Model {i}: ${100+i} (was ${150+i})' for i in range(1, 25)]
        cases = [
            ('Apple updates trade-in values for iPhone', 'All values are up to U.S. dollars.',
             '<ul>' + ''.join('<li>' + row + '</li>' for row in rows) + '</ul>', rows, True),
            ('Apple updates trade-in values for iPhone', 'All values are up to U.S. dollars.',
             '<table>' + ''.join('<tr><td>' + row + '</td></tr>' for row in rows) + '</table>', rows, True),
            ('Apple adds calibration modes to Camera', 'The new Camera calibration modes are:',
             '<ul><li>Amber</li><li>Slate</li><li>Pearl</li></ul>', ['Amber', 'Slate', 'Pearl'], True),
            ('Apple adds calibration modes to Camera', 'Separately, Google adds Camera calibration modes:',
             '<ul><li>Graphite</li><li>Ivory</li></ul>', ['Graphite', 'Ivory'], False),
            ('Apple adds calibration modes to Camera', "Google's existing Camera calibration modes include:",
             '<ul><li>Graphite</li><li>Ivory</li></ul>', ['Graphite', 'Ivory'], False),
        ]
        for title, context, markup, expected, assigned in cases:
            with self.subTest(title=title, context=context, markup=markup[:10]):
                url = 'https://9to5mac.com/2026/09/10/structured-source/'
                page = f'<meta property="article:published_time" content="{module.utc_now().isoformat()}"><article><h1>{title}</h1><p>{title} today.</p><p>{context}</p>{markup}</article>'
                with tempfile.TemporaryDirectory() as directory:
                    args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
                    with patch.object(module, 'collect_candidates_from_sources', return_value=[module.Candidate('9to5Mac', url, title)]), \
                         patch.object(module, 'fetch_url', return_value=page):
                        result = module.run(args)
                reviews = [item for item in result['final_brief_queue'] if item.get('unprocessed_evidence')]
                facts = [fact for event in result['events'] + result['deferred_events'] for fact in event['key_facts']]
                for value in expected:
                    matches = [(item, unit) for item in reviews for unit in item['unprocessed_evidence'] if unit['text'] == value]
                    if assigned:
                        self.assertIn(value, facts, "Explicit source list context should assign the entry")
                        sources = [item for event in result['events'] + result['deferred_events'] for item in event['fact_sources'] if item['text'] == value]
                        self.assertTrue(sources)
                        for item in sources:
                            self.assertTrue(item['origins'])
                            for origin in item['origins']:
                                unit = next(u for u in result['source_evidence'][origin['article_id']]['units'] if u['unit_id'] == origin['unit_id'])
                                self.assertEqual(unit['text'][origin['start']:origin['end']], value)
                    else:
                        self.assertNotIn(value, facts)
                        self.assertTrue(matches)
                    self.assertIn(value, module.render_brief_scaffold(result))
                    for item, unit in matches:
                        self.assertEqual(item['source_urls'], [url])
                        self.assertTrue(item['reason'])
                        original = next(u for u in result['source_evidence'][item['evidence_id']]['units'] if u['unit_id'] == unit['unit_id'])
                        self.assertEqual(original['text'][unit['start']:unit['end']], value)
                self.assertTrue(result['events'] or result['deferred_events'])
                if assigned:
                    self.assertIn(context, facts)
                    self.assertIn(context, module.render_brief_scaffold(result))


    def test_unbound_paragraph_enumerations_keep_context_and_exact_final_origins(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ("Apple adds camera calibration modes to iOS 29",
             "Apple added four calibration modes to the Camera app in iOS 29.",
             "The available calibration modes are:", "Quartz, Indigo, Copper, Jade.", True, "run"),
            ("Apple adds camera calibration modes to iOS 29",
             "Apple added four calibration modes to the Camera app in iOS 29.",
             "Google's existing Camera calibration modes include:", "Graphite, Ivory, Silver.", False, "run"),
            ("iPhone 21 Pro preorder schedule announced",
             "Apple today announced that iPhone 21 Pro will be available to pre-order starting Monday, August 17.",
             "", "The initial launch countries include Austria, Chile, Peru, Oman, and others.", True, "unbound"),
        ]
        cases = [(*case, "") for case in cases] + [
            ("Apple adds camera calibration modes to iOS 29",
             "Apple added four calibration modes to the Camera app in iOS 29.",
             "The available calibration modes are:", "Quartz, Indigo, Copper, Jade.", True, "run",
             "Separately, Microsoft adds enterprise controls to Teams."),
        ]
        for title, lead, context, enumeration, assigned, path, tail in cases:
            with self.subTest(path=path, context=context):
                url = "https://9to5mac.com/2026/09/10/paragraph-source/"
                page = (f'<meta property="article:published_time" content="{module.utc_now().isoformat()}">'
                        f'<article><h1>{title}</h1><p>{lead}</p><p>{context}</p><p>{enumeration}{(" " + tail) if tail else ""}</p></article>')
                if path == "run":
                    with tempfile.TemporaryDirectory() as directory:
                        args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
                        with patch.object(module, 'collect_candidates_from_sources', return_value=[module.Candidate('9to5Mac', url, title)]), \
                             patch.object(module, 'fetch_url', return_value=page):
                            result = module.run(args)
                    events = result['events'] + result['deferred_events']
                    reviews = [item for item in result['final_brief_queue'] if item.get('unprocessed_evidence')]
                    self.assertIn(enumeration, module.render_brief_scaffold(result))
                else:
                    article = article_for(module, title, lead, source='9to5Mac', facts=[lead])
                    article.url = url
                    article.evidence = module.capture_article_evidence('9to5Mac', url, page, title)
                    self.assertIsNone(article.bound_claim)
                    events = [module.event_to_dict(event, module.ZoneInfo('Asia/Singapore')) for event in module.cluster_articles([article])]
                    reviews = []
                facts = [fact for event in events for fact in event['key_facts']]
                if tail:
                    self.assertFalse(any(tail in fact for fact in facts))
                    local = [(item, unit) for item in reviews for unit in item['unprocessed_evidence'] if unit['text'] == tail]
                    self.assertTrue(local)
                    for item, unit in local:
                        self.assertEqual(item['source_urls'], [url])
                        self.assertTrue(item['reason'])
                        original = next(u for u in result['source_evidence'][item['evidence_id']]['units'] if u['unit_id'] == unit['unit_id'])
                        self.assertEqual(original['text'][unit['start']:unit['end']], tail)
                    self.assertIn(tail, module.render_brief_scaffold(result))
                if assigned:
                    self.assertIn(enumeration, facts)
                    origins = [origin for event in events for fact in event['fact_sources']
                               if fact['text'] == enumeration for origin in fact['origins']]
                    self.assertTrue(origins)
                    evidence = (article.evidence if path == 'unbound' else None)
                    for origin in origins:
                        text = (next(unit.text for unit in evidence.units if unit.unit_id == origin['unit_id'])
                                if evidence else next(unit['text'] for unit in result['source_evidence'][origin['article_id']]['units']
                                                      if unit['unit_id'] == origin['unit_id']))
                        self.assertEqual(text[origin['start']:origin['end']], enumeration)
                else:
                    self.assertNotIn(enumeration, facts)
                    matches = [(item, unit) for item in reviews for unit in item['unprocessed_evidence']
                               if unit['text'] == enumeration]
                    self.assertTrue(matches)
                    for item, unit in matches:
                        self.assertEqual(item['source_urls'], [url])
                        self.assertTrue(item['reason'])
                        original = next(u for u in result['source_evidence'][item['evidence_id']]['units'] if u['unit_id'] == unit['unit_id'])
                        self.assertEqual(original['text'][unit['start']:unit['end']], enumeration)


    def test_market_results_keep_share_roles_and_local_regions(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        left = article_for(module, "Apple bucks a slump in smartphone shipments",
            "Counterpoint reports Apple gained nine points to 34 percent in Europe and grew 5 percent in Latin America during Q2 2026.")
        for region, metric, expected in (
            ('Europe', 'market share reached 34%', True),
            ('Latin America', 'market share reached 34%', False),
            ('Europe', 'shipments grew 34%', False),
        ):
            with self.subTest(region=region, metric=metric):
                right = article_for(module, f"Apple smartphone {metric} in {region}",
                    f"Counterpoint reports Apple {metric} in {region} in Q2 2026.", source='MacRumors')
                self.assertEqual(module.should_merge(left, event_for(module, right)), expected)
                self.assertEqual(module.should_merge(right, event_for(module, left)), expected)


        reports = []
        for europe, latin in ((34, 5), (5, 34)):
            article = article_for(module, "Apple smartphone market share report",
                f"Counterpoint reports Apple held {europe} percent market share in Europe and held {latin} percent market share in Latin America during Q2 2026.")
            profile = module.article_reconciliation_profile(article)
            keys = profile.event_keys
            for region, value, wrong in (('europe', europe, latin), ('latin-america', latin, europe)):
                self.assertTrue(any(f':{region}:2026-q2:apple-share-current:{value}' in key for key in keys))
                self.assertFalse(any(f':{region}:2026-q2:apple-share-current:{wrong}' in key for key in keys))
            reports.append(article)
        self.assertFalse(module.should_merge(reports[0], event_for(module, reports[1])))
        self.assertFalse(module.should_merge(reports[1], event_for(module, reports[0])))

    def test_generic_product_update_keys_do_not_override_distinct_concrete_actions(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        inputs = [
            ('Apple delays HomeHub launch until 2028', 'Apple has delayed the HomeHub launch until 2028 because manufacturing is behind schedule.'),
            ('Apple HomeHub code reveals widget support', 'New macOS code reveals a widget gallery and Smart Stack for Apple HomeHub.'),
            ('Apple HomeHub code reveals automatic profile switching', 'Separate code files show Apple HomeHub will use a camera for automatic user profile switching.'),
            ('Apple HomeHub launch delayed to 2028', 'Apple has postponed the HomeHub launch to 2028 because of manufacturing delays.'),
            ('Code reveals a widget gallery for Apple HomeHub', 'Apple HomeHub will have a widget gallery and Smart Stack according to macOS code.'),
        ]
        articles = [article_for(module, title, lead, source=f'Source{i}', facts=[lead]) for i, (title, lead) in enumerate(inputs)]
        for left, right, expected in ((0, 1, False), (0, 2, False), (1, 2, False), (0, 3, True), (1, 4, True)):
            with self.subTest(pair=(left, right)):
                self.assertEqual(module.should_merge(articles[left], event_for(module, articles[right])), expected)
                self.assertEqual(module.should_merge(articles[right], event_for(module, articles[left])), expected)
        self.assertEqual(sorted(len(event.articles) for event in module.cluster_articles(articles)), [1, 2, 2])


    def test_detail_priority_consumes_bound_and_title_actions_before_topics(self):
        module = load_module()
        topics = [module.Candidate('IT之家', 'https://example.test/topic', 'Apple Pay'),
                  module.Candidate('IT之家', 'https://example.test/reaction', '苹果 iPhone Duo 即将登场，三星发布“欢迎来到折叠屏时代”视频')]
        for title in ('苹果发布 iPhone 18 Pro / Max：四种颜色、A20 Pro 芯片',
                      '苹果发布 iPhone Handoff：两台手机可共用号码',
                      '【IT之家实拍】苹果 iPhone 18 Pro 系列抢先看：新增可变光圈技术、首发 A20 Pro 芯片'):
            with self.subTest(title=title):
                current = module.Candidate('IT之家', 'https://example.test/current', title)
                for topic in topics:
                    self.assertGreater(module.candidate_detail_priority(current)[0], module.candidate_detail_priority(topic)[0])
        revenue = module.Candidate('IT之家', 'https://example.test/revenue',
            'Counterpoint：iPhone 17 系列首年批发营收超 1700 亿美元，创历代新高')
        feature = module.Candidate('IT之家', 'https://example.test/feature',
            '支持同时显示三个实时活动，苹果 iPhone 18 Pro 灵动岛新功能演示视频曝光')
        self.assertGreater(module.candidate_detail_priority(revenue)[0], module.candidate_detail_priority(feature)[0])
        for title in ('苹果 iPhone Duo 即将登场，三星发布“欢迎来到折叠屏时代”视频',
                      'Apple iPhone launch is coming, Samsung releases a response video'):
            profile = module.source_text_profile(title, '', [], 'IT之家')
            self.assertNotEqual(profile.identity.action_owner, 'apple')

    def test_accessory_offer_and_expansion_keep_current_value_and_model(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        cloth = article_for(module, 'Apple Releases New Polishing Cloth', 'Apple released a new Polishing Cloth for $9.')
        for price, expected in ((9, True), (19, False)):
            other = article_for(module, f"Apple's Polishing Cloth is back for ${price}",
                                f'Apple restored its Polishing Cloth to the store at ${price}.', source='Other')
            self.assertEqual(module.should_merge(cloth, event_for(module, other)), expected)
        adapter = article_for(module, "Apple's 40W Dynamic Power Adapter Expands to More Countries",
                              'Apple expanded the adapter to additional European markets.')
        for watts, expected in ((40, True), (60, False)):
            other = article_for(module, f'苹果 {watts}W 动态电源适配器登陆欧洲更多市场，支持最高 60W 短时充电功率',
                                '苹果把动态电源适配器扩展到更多市场。', source='Other')
            self.assertEqual(module.should_merge(adapter, event_for(module, other)), expected)

    def test_index_preparation_preserves_execution_and_target_versions(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        def make(current, target):
            return article_for(module, f'iOS {current} prepares devices for iOS {target}',
                'Apple is preparing the next system release.', facts=[f'Apple will start Spotlight indexing in iOS {current} so devices are ready for iOS {target}.'])
        base = make('26.6', '27')
        self.assertTrue(module.should_merge(base, event_for(module, make('26.6', '27'))))
        self.assertFalse(module.should_merge(base, event_for(module, make('27', '26.6'))))
        self.assertFalse(module.should_merge(base, event_for(module, make('26.5', '27'))))
        reordered = article_for(module, 'iOS 26.6 prepares the Spotlight index for iOS 27',
            'Apple starts indexing for the next release.', facts=['To prepare for iOS 27, Apple starts Spotlight indexing in iOS 26.6.'])
        self.assertTrue(module.should_merge(base, event_for(module, reordered)))
        ordinary = article_for(module, 'Apple releases iOS 26.6 RC', 'Apple released iOS 26.6 RC to developers.')
        self.assertFalse(module.should_merge(base, event_for(module, ordinary)))

    def test_sparse_accessory_refresh_support_does_not_bridge_explicit_features(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        from dataclasses import replace
        sparse = article_for(module, 'Apple releases new Magic Keyboards with one notable change',
                             'Apple launched minor updates to its Magic Keyboard accessories.')
        labels = article_for(module, 'Apple Quietly Refreshes Magic Keyboards',
                             'Apple refreshed four Magic Keyboard models with symbol-only labels.', source='Labels')
        self.assertTrue(module.should_merge(sparse, event_for(module, labels)))
        self.assertFalse(any('keyboard-key-labels' in key for key in module.article_reconciliation_profile(sparse).event_keys))
        forecast = article_for(module, 'Apple may refresh Magic Keyboards with new key symbols',
                               'Apple may update its Magic Keyboards with symbol-only labels next year.', source='Forecast')
        self.assertFalse(module.should_merge(labels, event_for(module, forecast)))
        # The external profile contract may supply a different explicit feature.
        # An underspecified refresh must never connect those two known actions.
        profiles = [module.article_reconciliation_profile(a) for a in (sparse, labels)]
        other = replace(profiles[1], event_keys=frozenset({'canonical-apple-action:magic-keyboard:keyboard-backlight-adoption'}),
                        separation_keys=frozenset({'source-accessory-refresh:magic-keyboard:announced',
                                                  'primary-claim-subject:magic-keyboard:keyboard-backlight',
                                                  'primary-claim-predicate:hardware-component-adoption'}))
        self.assertEqual(module.profile_pair_decision(profiles[1], other), 'conflict')
        other_article = article_for(module, 'Apple refreshes Magic Keyboards with backlit keys',
                                    'Apple adds backlit keys to Magic Keyboards.', source='Other')
        objects = [sparse, labels, other_article]
        lookup = dict(zip(map(id, objects), [*profiles, other]))
        for order in (objects, list(reversed(objects))):
            groups = module.reconcile_articles(order, profile_for=lambda a: lookup[id(a)], initial_groups=[order])
            self.assertFalse(any(labels in group and objects[2] in group for group in groups))

    def test_naming_stage_belongs_to_current_completed_action_not_historical_rumors(self):
        module = load_module()
        from dataclasses import replace
        from test_relevance_rules import article_for
        rows = [['forecast', "Apple's foldable will be named iPhone Horizon, says analyst", 'An analyst reports that Apple will name its foldable iPhone Horizon. Apple has not announced the device yet.'], ['current-retrospective', "Apple's foldable is here and it is called iPhone Horizon", 'Five years of rumors have culminated in Apple revealing the iPhone Horizon today. The foldable device is now official. Customers will be able to buy it next month.'], ['current-direct', 'Apple unveils foldable named iPhone Horizon', 'Apple unveiled its foldable, officially named iPhone Horizon, today. The phone will go on sale next month.'], ['forecast-control', 'Report: Apple foldable may be called iPhone Horizon', 'An analyst says the foldable iPhone will be named iPhone Horizon. Apple has not revealed the phone.'], ['future-only', "Apple's foldable may be called iPhone Horizon", 'Apple is expected to reveal a foldable called iPhone Horizon next month. The announcement has not happened.'], ['uncertain', "Apple's foldable may be called iPhone Horizon", 'It is unclear whether Apple has revealed a foldable called iPhone Horizon. The report provides no confirmation.']]
        articles = []
        for index, (_, title, summary) in enumerate(rows):
            article = article_for(module, title, summary, source="Synthetic" + str(index), facts=[summary])
            article.evidence = replace(module.capture_article_title_evidence(
                article.source, article.url, article.title, article.summary, tuple(article.key_facts)), content_form="news")
            articles.append(article)
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        for index in (1, 2):
            with self.subTest(current=index):
                self.assertIn("product-disclosure-stage:announced", profiles[index].separation_keys)
                self.assertNotIn("product-disclosure-stage:reported", profiles[index].separation_keys)
        for index in (0, 3, 4, 5):
            self.assertNotIn("product-disclosure-stage:announced", profiles[index].separation_keys)
        for left, right, expected in ((0, 1, False), (1, 2, True), (0, 3, True)):
            with self.subTest(pair=(left, right)):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == "match", expected)
        events = module.cluster_articles(articles)
        self.assertEqual({frozenset(a.url for a in event.articles) for event in events},
                         {frozenset(articles[i].url for i in group) for group in ((1, 2), (0, 3, 4, 5))})
        for summary, expected in (
            ("Years of speculation ended with Apple unveiling the iPhone Horizon today.", True),
            ("After years of rumors, Apple has now introduced the iPhone Horizon today.", True),
            ("Years of speculation ended with Apple unveiling the iPhone Horizon today, with retail sales expected next month.", True),
            ("Apple unveiled its foldable, officially named iPhone Horizon, today, and customers can buy it next month.", True),
            ("Years of rumors could culminate in Apple unveiling the iPhone Horizon next month.", False),
            ("It is unclear whether years of rumors have culminated in Apple revealing the iPhone Horizon.", False),
            ("Years of rumors have culminated in Samsung revealing the iPhone Horizon today.", False),
            ("Years of rumors have culminated in Apple revealing the iPhone Horizon last year.", False),
            ("Years of rumors have culminated in Apple revealing the iPhone Compass today.", False),
        ):
            with self.subTest(clause=summary):
                profile = module.article_reconciliation_profile(article_for(module, rows[1][1], summary, facts=[summary]))
                self.assertEqual("product-disclosure-stage:announced" in profile.separation_keys, expected)

    def test_natural_source_structure_preserves_current_action_and_stage(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [('preorder', 'iPhone 22 Pro预购预计10月17日开启', '据消息人士报道，iPhone 22 Pro预购将于10月17日开启，苹果尚未公布预购日期。', ['据消息人士报道，iPhone 22 Pro预购将于10月17日开启，苹果尚未公布预购日期。']), ('preorder-background', 'iPhone 22 Pro预购时间推迟至10月17日', '消息人士称iPhone 22 Pro预购时间预计推迟至10月17日，苹果尚未公布预购日期。', ['消息人士称iPhone 22 Pro预购时间预计推迟至10月17日，苹果尚未公布预购日期。', '作为既有产品背景，iPhone 22 Pro和Pro Max采用6.2英寸和6.8英寸显示屏。']), ('screen', 'iPhone 22 Pro系列正面屏幕亮相：首发小号灵动岛', '苹果今日公布iPhone 22 Pro系列的新屏幕设计，灵动岛变小了。', ['苹果今日公布iPhone 22 Pro系列的新屏幕设计，灵动岛变小了。', 'iPhone 22 Pro和Pro Max采用6.2英寸和6.8英寸显示屏。']), ('camera', 'Both iPhone 22 Pro models feature variable aperture camera', 'Apple has revealed that both iPhone 22 Pro models have a variable aperture camera system.', ['Apple has revealed that both iPhone 22 Pro models have a variable aperture camera system.']), ('camera-same', 'Apple adds variable aperture to the iPhone 22 Pro camera', 'Apple announced a variable aperture camera system for both iPhone 22 Pro models today.', ['Apple announced a variable aperture camera system for both iPhone 22 Pro models today.']), ('foldable', '苹果iPhone Horizon亮相 正式推出折叠屏产品 售价2499美元起', '苹果终于正式进入折叠屏手机市场，推出首款折叠式iPhone，产品名称确定为iPhone Horizon。该机后置双摄像头，主摄和超广角均为3600万像素。', ['苹果终于正式进入折叠屏手机市场，推出首款折叠式iPhone，产品名称确定为iPhone Horizon。该机后置双摄像头，主摄和超广角均为3600万像素。']), ('price-direct', 'Apple raises iPhone 21 and iPhone Air prices', 'Apple raised the official prices of iPhone 21 and iPhone Air by $80 today.', ['Apple raised the official prices of iPhone 21 and iPhone Air by $80 today.']), ('price-paraphrase', 'iPhone 21 and iPhone Air just got more expensive', 'Apple has applied an $80 price hike to iPhone 21 and iPhone Air today. The same hardware now costs more.', ['Apple has applied an $80 price hike to iPhone 21 and iPhone Air today. The same hardware now costs more.']), ('price-zh', '芯片成本上涨逼迫苹果上调iPhone 21及iPhone Air官方售价', '苹果今天宣布上调仍在销售的iPhone 21和iPhone Air官方零售价格，两款机型均上涨80美元。', ['苹果今天宣布上调仍在销售的iPhone 21和iPhone Air官方零售价格，两款机型均上涨80美元。']), ('price-long-model-list', '芯片成本飙升逼迫苹果上调iPhone 21、21e及iPhone Air官方售价', '在刚刚结束的发布会之后，苹果宣布逆势上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。', ['在刚刚结束的发布会之后，苹果宣布逆势上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。']), ('vision-release', 'visionOS 29 is here for Apple Vision Pro with these new features', 'Apple Vision Pro gets its next major software update today. visionOS 29 is available to the public now. Siri AI is its main new feature.', ['Apple Vision Pro gets its next major software update today. visionOS 29 is available to the public now. Siri AI is its main new feature.']), ('vision-features', 'visionOS 29 adds Siri AI to your spatial computing environment', 'Even as Apple reorganizes its hardware team, visionOS 29 is available for public download. After a summer of beta testing, the new release brings Siri AI and interface improvements.', ['Even as Apple reorganizes its hardware team, visionOS 29 is available for public download. After a summer of beta testing, the new release brings Siri AI and interface improvements.']), ('vision-same-release', 'Apple releases visionOS 29 to Vision Pro users', 'Apple released visionOS 29 to all Vision Pro users today with new Siri AI features.', ['Apple released visionOS 29 to all Vision Pro users today with new Siri AI features.']), ('vision-other-version', 'Apple releases visionOS 28 to Vision Pro users', 'Apple released visionOS 28 to all Vision Pro users today.', ['Apple released visionOS 28 to all Vision Pro users today.']), ('catalogue', 'More Than 1,400 Apple Watch Bands Have Been Released Since 2017', 'Apple has now released more than 1,400 official Apple Watch bands since 2017, according to Alex Morris, who develops the BandIndex catalogue.', ['Apple has now released more than 1,400 official Apple Watch bands since 2017, according to Alex Morris, who develops the BandIndex catalogue.']), ('catalogue-translation', '苹果 Apple Watch 官方表带累计已超1400款，最贵售价15999元', '科技媒体今天报道称，自2017年以来苹果已推出超过1400款官方Apple Watch表带。该消息来自Alex Morris开发的BandIndex目录应用，属于同一统计报告。', ['科技媒体今天报道称，自2017年以来苹果已推出超过1400款官方Apple Watch表带。该消息来自Alex Morris开发的BandIndex目录应用，属于同一统计报告。']), ('vision-rolling-current', 'visionOS 29 is here for Apple Vision Pro with these new features', "The next major update for Apple's headset is here. visionOS 29 is rolling out now to all Vision Pro models. visionOS 29 is now available for Apple Vision Pro. Siri AI is the biggest highlight. It also arrives in more regions.", ["The next major update for Apple's headset is here. visionOS 29 is rolling out now to all Vision Pro models. visionOS 29 is now available for Apple Vision Pro. Siri AI is the biggest highlight. It also arrives in more regions."]), ('catalogue-app-origin', 'More Than 1,400 Apple Watch Bands Have Been Released Since 2017', "Apple has reached a milestone: more than 1,400 official Apple Watch bands have appeared since the device debuted in May 2017, according to Alex Morris, who develops the BandIndex app for tracking Apple Watch bands. The latest bands arrived with this year's hardware announcements.", ["Apple has reached a milestone: more than 1,400 official Apple Watch bands have appeared since the device debuted in May 2017, according to Alex Morris, who develops the BandIndex app for tracking Apple Watch bands. The latest bands arrived with this year's hardware announcements."]), ('catalogue-app-translation', '苹果 Apple Watch 官方表带累计已超1400款，最贵售价15999元', '科技媒体今天报道称，自初代Apple Watch于2017年5月上市以来，苹果已推出超过1,400款官方表带。该消息源于Alex Morris开发的BandIndex应用，用于追踪苹果发布的Apple Watch表带。另有最贵款式售价15,999元。', ['科技媒体今天报道称，自初代Apple Watch于2017年5月上市以来，苹果已推出超过1,400款官方表带。该消息源于Alex Morris开发的BandIndex应用，用于追踪苹果发布的Apple Watch表带。另有最贵款式售价15,999元。']), ('price-natural-background', '芯片成本上涨促使苹果上调iPhone 21、21e及iPhone Air官方售价', '伴随新旗舰周期开启，苹果改变了手机定价安排。在新品发布会结束后，苹果没有继续旧款机型顺延降价80美元的惯例，反而宣布全面上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。往年新品上市后，旧机通常降价；今年芯片成本上涨，苹果此次提高了在售产品的价格。', ['伴随新旗舰周期开启，苹果改变了手机定价安排。在新品发布会结束后，苹果没有继续旧款机型顺延降价80美元的惯例，反而宣布全面上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。往年新品上市后，旧机通常降价；今年芯片成本上涨，苹果此次提高了在售产品的价格。']), ('price-current-with-consumer-background', '芯片成本上涨促使苹果上调iPhone 21、21e及iPhone Air官方售价', '苹果今日宣布上调仍在销售的iPhone 21、iPhone 21e及iPhone Air官方价格，每款增加80美元。新价格已在官方商店生效。这个调整打破了部分消费者的购机预期。', ['苹果今日宣布上调仍在销售的iPhone 21、iPhone 21e及iPhone Air官方价格，每款增加80美元。新价格已在官方商店生效。这个调整打破了部分消费者的购机预期。']), ('camera-pre-event-teaser', 'Apple CEO teases variable aperture in iPhone 22 Pro before event', 'Apple posted a short teaser video ahead of next week’s event. The clip hints at variable aperture for iPhone 22 Pro, but the company has not yet announced the camera specifications.', ['Apple posted a short teaser video ahead of next week’s event. The clip hints at variable aperture for iPhone 22 Pro, but the company has not yet announced the camera specifications.']), ('camera-same-teaser', 'Apple CEO teases iPhone 22 Pro variable aperture before event', 'Apple posted a short preview video ahead of next week’s event. It hints at variable aperture for iPhone 22 Pro, but the company has not yet announced the camera specifications.', ['Apple posted a short preview video ahead of next week’s event. It hints at variable aperture for iPhone 22 Pro, but the company has not yet announced the camera specifications.']), ('vision-future', 'visionOS 29 will be available next year', 'Apple says visionOS 29 will be available to the public next year. The current release remains visionOS 28.', ['Apple says visionOS 29 will be available to the public next year. The current release remains visionOS 28.']), ('price-current-action-consumer-context', '芯片成本飙升促使苹果上调iPhone 21、21e及iPhone Air官方售价', '本轮旗舰周期中，苹果公司改变了其手机的定价安排。苹果打破旧机顺延降价80美元的惯例，反而全面上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。三款旧机的官方标价现在都比原来高80美元。这一变化打破了用户的购机预期。', ['本轮旗舰周期中，苹果公司改变了其手机的定价安排。苹果打破旧机顺延降价80美元的惯例，反而全面上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。三款旧机的官方标价现在都比原来高80美元。这一变化打破了用户的购机预期。']), ('photo-authenticity', '苹果iPhone 22 Pro新增真实照片验证功能', '苹果在今天的发布会上推出真实照片验证功能。iPhone 22 Pro主摄在拍摄时为图像数据加上安全标记，由私有云处理后保存到照片应用。这项功能暂不在部分地区提供。', ['苹果在今天的发布会上推出真实照片验证功能。iPhone 22 Pro主摄在拍摄时为图像数据加上安全标记，由私有云处理后保存到照片应用。这项功能暂不在部分地区提供。']), ('same-model-camera-launch', 'Apple unveils iPhone 22 Pro with variable aperture camera', 'Apple today launched iPhone 22 Pro and confirmed its new variable aperture camera system. Both Pro models have this camera hardware.', ['Apple today launched iPhone 22 Pro and confirmed its new variable aperture camera system. Both Pro models have this camera hardware.']), ('price-identical-without-consumer-tail', '芯片成本飙升促使苹果上调iPhone 21、21e及iPhone Air官方售价', '本轮旗舰周期中，苹果公司改变了其手机的定价安排。苹果打破旧机顺延降价80美元的惯例，反而全面上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。三款旧机的官方标价现在都比原来高80美元。', ['本轮旗舰周期中，苹果公司改变了其手机的定价安排。苹果打破旧机顺延降价80美元的惯例，反而全面上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。三款旧机的官方标价现在都比原来高80美元。']), ('catalogue-natural-release-date', 'More Than 1,400 Apple Watch Bands Have Been Released Since 2017', 'Apple recently passed a milestone: more than 1,400 official Apple Watch bands since the device was released in May 2017, according to Alex Morris, who develops the BandIndex app for tracking Apple Watch bands.', ['Apple recently passed a milestone: more than 1,400 official Apple Watch bands since the device was released in May 2017, according to Alex Morris, who develops the BandIndex app for tracking Apple Watch bands.']), ('catalogue-natural-source-clause', '苹果 Apple Watch 官方表带累计已超1400款，最贵售价15999元', '媒体称自初代Apple Watch于2017年5月上市以来，官方表带累计超过1400款。苹果已推出超过1,400款官方表带。该消息源于 Alex Morris 开发的 BandIndex 应用，该应用主要用于追踪苹果公司发布的 Apple Watch 表带。', ['媒体称自初代Apple Watch于2017年5月上市以来，官方表带累计超过1400款。苹果已推出超过1,400款官方表带。该消息源于 Alex Morris 开发的 BandIndex 应用，该应用主要用于追踪苹果公司发布的 Apple Watch 表带。']), ('camera-executive-post-background', 'Apple CEO teases variable aperture in iPhone 22 Pro before event', "The latest social post from Apple's CEO appears to hint at the iPhone 22 Pro camera, which should be revealed at tomorrow's event. The short clip shows a beam of light but does not identify any camera specification. Existing rumors discuss the use of a variable aperture lens. This is a preview of the event, not an announcement of the camera hardware.", ["The latest social post from Apple's CEO appears to hint at the iPhone 22 Pro camera, which should be revealed at tomorrow's event. The short clip shows a beam of light but does not identify any camera specification. Existing rumors discuss the use of a variable aperture lens. This is a preview of the event, not an announcement of the camera hardware."]), ('catalogue-natural-year-spaces', '苹果 Apple Watch 官方表带累计已超1400款，最贵售价15999元', '媒体称自初代Apple Watch于 2017 年 5 月上市以来，官方表带累计超过1400款。苹果已推出超过1,400款官方表带。该消息源于 Alex Morris 开发的 BandIndex 应用，该应用主要用于追踪苹果公司发布的 Apple Watch 表带。', ['媒体称自初代Apple Watch于 2017 年 5 月上市以来，官方表带累计超过1400款。苹果已推出超过1,400款官方表带。该消息源于 Alex Morris 开发的 BandIndex 应用，该应用主要用于追踪苹果公司发布的 Apple Watch 表带。']), ('named-ceo-teaser', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', "The latest social post from Apple CEO Casey Stone is a preview of the iPhone 22 Pro camera before tomorrow's event. The video shows a changing beam of light and gives no camera specifications. Existing rumors discuss variable aperture, but the feature has not been announced.", ["The latest social post from Apple CEO Casey Stone is a preview of the iPhone 22 Pro camera before tomorrow's event. The video shows a changing beam of light and gives no camera specifications. Existing rumors discuss variable aperture, but the feature has not been announced."]), ('chinese-ceo-teaser', '苹果CEO凯西·斯通发布预热视频：暗示iPhone 22 Pro可变光圈', '苹果CEO凯西·斯通（Casey Stone）今天发布一段预热视频，片中的光束由大变小。外界猜测它暗示iPhone 22 Pro的可变光圈，但苹果尚未公布相机规格。', ['苹果CEO凯西·斯通（Casey Stone）今天发布一段预热视频，片中的光束由大变小。外界猜测它暗示iPhone 22 Pro的可变光圈，但苹果尚未公布相机规格。']), ('camera-current-claim-after-context', "iPhone 22 Pro's variable aperture looks delicate", "The adjustable opening offers new shooting options, while its tiny mechanism looks delicate. Apple says iPhone 22 Pro has a new variable aperture camera. The company has confirmed this hardware at today's launch, with a ring of thin moving blades controlling the opening.", ["The adjustable opening offers new shooting options, while its tiny mechanism looks delicate. Apple says iPhone 22 Pro has a new variable aperture camera. The company has confirmed this hardware at today's launch, with a ring of thin moving blades controlling the opening."]), ('same-video-pro-reading', 'Casey Stone teases variable aperture in iPhone 22 Pro before event', 'Apple CEO Casey Stone posted a short preview video today before the launch event. The video shows a light shrinking against dark glass. It may hint at variable aperture for iPhone 22 Pro, but specifications remain unannounced.', ['Apple CEO Casey Stone posted a short preview video today before the launch event. The video shows a light shrinking against dark glass. It may hint at variable aperture for iPhone 22 Pro, but specifications remain unannounced.']), ('same-video-max-reading', '苹果CEO凯西·斯通发布预热视频：暗示iPhone 22 Pro Max可变光圈', '苹果CEO凯西·斯通（Casey Stone）今天在发布会前分享了同一段预热视频，片中一束光在深色玻璃上逐渐缩小。外界猜测它暗示iPhone 22 Pro Max可变光圈，苹果尚未公布相机规格。', ['苹果CEO凯西·斯通（Casey Stone）今天在发布会前分享了同一段预热视频，片中一束光在深色玻璃上逐渐缩小。外界猜测它暗示iPhone 22 Pro Max可变光圈，苹果尚未公布相机规格。']), ('same-video-no-camera-title', '苹果发布神秘预告视频，iPhone Horizon与iPhone 22 Pro传闻升温', '在今天的发布会开始前，苹果CEO凯西·斯通（Casey Stone）分享了一段预热视频。视频里一束光在深色玻璃上逐渐缩小，外界猜测这暗示iPhone 22 Pro的可变光圈，官方尚未公布规格。', ['在今天的发布会开始前，苹果CEO凯西·斯通（Casey Stone）分享了一段预热视频。视频里一束光在深色玻璃上逐渐缩小，外界猜测这暗示iPhone 22 Pro的可变光圈，官方尚未公布规格。']), ('different-ceo-video', 'Apple CEO previews an iPhone 22 Pro charging cable', 'Apple CEO Casey Stone posted a different video showing the iPhone 22 Pro charging cable plugged into a power adapter. The clip demonstrates the cable and does not show a camera or aperture.', ['Apple CEO Casey Stone posted a different video showing the iPhone 22 Pro charging cable plugged into a power adapter. The clip demonstrates the cable and does not show a camera or aperture.']), ('camera-current-claim-with-article', "iPhone 22 Pro's variable aperture looks delicate", "The adjustable opening offers new shooting options, while its tiny mechanism looks delicate. Apple says the iPhone 22 Pro has a new variable aperture camera. The company has confirmed this hardware at today's launch, with a ring of thin moving blades controlling the opening.", ["The adjustable opening offers new shooting options, while its tiny mechanism looks delicate. Apple says the iPhone 22 Pro has a new variable aperture camera. The company has confirmed this hardware at today's launch, with a ring of thin moving blades controlling the opening."])]
        articles = {label: article_for(module, title, lead, source=label, facts=facts) for label,title,lead,facts in rows}
        profiles = {label: module.article_reconciliation_profile(a) for label,a in articles.items()}
        for left,right,expected in [('preorder', 'preorder-background', True), ('preorder-background', 'screen', False), ('camera', 'camera-same', True), ('camera', 'foldable', False), ('price-direct', 'price-paraphrase', True), ('price-direct', 'price-zh', True), ('price-direct', 'price-long-model-list', True), ('vision-release', 'vision-features', True), ('vision-release', 'vision-same-release', True), ('vision-release', 'vision-other-version', False), ('catalogue', 'catalogue-translation', True), ('vision-rolling-current', 'vision-features', True), ('catalogue-app-origin', 'catalogue-app-translation', True), ('price-direct', 'price-natural-background', True), ('price-direct', 'price-current-with-consumer-background', True), ('camera-pre-event-teaser', 'camera', False), ('camera-pre-event-teaser', 'camera-same-teaser', True), ('vision-rolling-current', 'vision-future', False), ('price-direct', 'price-current-action-consumer-context', True), ('camera-pre-event-teaser', 'photo-authenticity', False), ('camera', 'same-model-camera-launch', True), ('price-direct', 'price-identical-without-consumer-tail', True), ('catalogue-natural-release-date', 'catalogue-natural-source-clause', True), ('catalogue-natural-release-date', 'catalogue-app-origin', True), ('catalogue-natural-source-clause', 'catalogue-app-translation', True), ('camera-executive-post-background', 'camera', False), ('camera-executive-post-background', 'camera-pre-event-teaser', True), ('catalogue-natural-release-date', 'catalogue-natural-year-spaces', True), ('catalogue-natural-source-clause', 'catalogue-natural-year-spaces', True), ('named-ceo-teaser', 'camera-executive-post-background', True), ('named-ceo-teaser', 'chinese-ceo-teaser', True), ('named-ceo-teaser', 'camera', False), ('camera-current-claim-after-context', 'camera', True), ('camera-current-claim-after-context', 'camera-executive-post-background', False), ('same-video-pro-reading', 'same-video-max-reading', True), ('same-video-pro-reading', 'same-video-no-camera-title', True), ('same-video-max-reading', 'same-video-no-camera-title', True), ('same-video-pro-reading', 'different-ceo-video', False), ('camera-current-claim-with-article', 'camera-current-claim-after-context', True), ('camera-current-claim-with-article', 'camera', True), ('camera-current-claim-with-article', 'camera-executive-post-background', False)]:
            with self.subTest(pair=(left,right)):
                self.assertEqual(module.profile_pair_decision(profiles[left],profiles[right]) == 'match', expected)
        for label in ['price-direct', 'price-paraphrase', 'price-zh', 'price-long-model-list', 'price-natural-background', 'price-current-with-consumer-background', 'price-current-action-consumer-context', 'price-identical-without-consumer-tail']:
            with self.subTest(tier=label):
                self.assertEqual(profiles[label].relevance_tier, 'strong')
        for label in ('catalogue-natural-release-date','catalogue-natural-source-clause','catalogue-natural-year-spaces'):
            with self.subTest(field=label):
                self.assertTrue(any(key.startswith('primary-claim:apple-watch-bands-catalogue:') for key in profiles[label].event_keys))
        self.assertFalse(any(key.startswith('canonical-apple-action:') and key.endswith(':camera-system-adoption') for key in profiles['camera-executive-post-background'].event_keys))
        for labels, expected in (
            (('same-video-pro-reading','same-video-max-reading','same-video-no-camera-title','different-ceo-video','camera','camera-same','same-model-camera-launch'), (('same-video-pro-reading','same-video-max-reading','same-video-no-camera-title'),('different-ceo-video',),('camera','camera-same','same-model-camera-launch'))),
            (('camera-current-claim-with-article','camera-current-claim-after-context','camera','camera-same','same-model-camera-launch'), (('camera-current-claim-with-article','camera-current-claim-after-context','camera','camera-same','same-model-camera-launch'),)),
            (('catalogue-natural-release-date','catalogue-natural-year-spaces'), (('catalogue-natural-release-date','catalogue-natural-year-spaces'),)),
            (('named-ceo-teaser','chinese-ceo-teaser','camera-executive-post-background','camera-pre-event-teaser','camera-same-teaser'), (('named-ceo-teaser','chinese-ceo-teaser','camera-executive-post-background','camera-pre-event-teaser','camera-same-teaser'),)),
            (('camera-current-claim-after-context','camera','camera-same','same-model-camera-launch'), (('camera-current-claim-after-context','camera','camera-same','same-model-camera-launch'),)),
            (('catalogue-app-origin','catalogue-app-translation','catalogue-natural-release-date','catalogue-natural-source-clause'), (('catalogue-app-origin','catalogue-app-translation','catalogue-natural-release-date','catalogue-natural-source-clause'),)),
            (('camera-executive-post-background','camera-pre-event-teaser','camera-same-teaser','camera','camera-same','same-model-camera-launch'), (('camera-executive-post-background','camera-pre-event-teaser','camera-same-teaser'),('camera','camera-same','same-model-camera-launch'))),
            (('vision-rolling-current','vision-features','vision-same-release'), (('vision-rolling-current','vision-features','vision-same-release'),)),
            (('catalogue-app-origin','catalogue-app-translation'), (('catalogue-app-origin','catalogue-app-translation'),)),
            (('camera-pre-event-teaser','camera-same-teaser','photo-authenticity','camera','camera-same','same-model-camera-launch'),
             (('camera-pre-event-teaser','camera-same-teaser'),('photo-authenticity',),('camera','camera-same','same-model-camera-launch'))),
        ):
            with self.subTest(group=labels):
                events = module.cluster_articles([articles[label] for label in labels])
                self.assertEqual({frozenset(a.url for a in e.articles) for e in events},
                                 {frozenset(articles[label].url for label in group) for group in expected})

    def test_natural_release_and_citation_do_not_adopt_background_claims(self):
        module = load_module()
        from apple_news_core.event_identity import current_public_os_release
        from test_relevance_rules import article_for
        title = 'visionOS 29 is here for Apple Vision Pro'
        for lead in (
            'Previously, visionOS 29 is now available for Apple Vision Pro.',
            'visionOS 29 is not rolling out now to all Vision Pro models.',
            'visionOS 29 may be available for Apple Vision Pro.',
            'visionOS 28 is rolling out now to all Vision Pro models.',
            'A rumor claims visionOS 29 is rolling out now to all Vision Pro models.',
        ):
            with self.subTest(release=lead):
                self.assertIsNone(current_public_os_release(title, lead))
        title = 'More Than 1,400 Apple Watch Bands Have Been Released Since 2017'
        lead = 'Apple has reached a milestone: more than 1,400 official Apple Watch bands have appeared since the device debuted in May 2017, according to Alex Morris, who develops the BandIndex app for tracking Apple Watch bands.'
        original = module.article_reconciliation_profile(article_for(module, title, lead, facts=[lead]))
        self.assertTrue(any('cumulative-count-report' in key for key in original.event_keys))
        for old,new in (('Alex Morris','Casey Brooks'),('BandIndex','StrapBook'),('2017','2018'),('1,400','1,500')):
            other = module.article_reconciliation_profile(article_for(module, title.replace(old,new), lead.replace(old,new), source='Other', facts=[lead.replace(old,new)]))
            with self.subTest(citation=(old,new)):
                self.assertNotEqual(module.profile_pair_decision(original, other), 'match')
        predicted = module.article_reconciliation_profile(article_for(module,
            "The iPhone 22 Pro's Rumored Camera Upgrade, Explained",
            'Apple is expected to introduce a variable-aperture main camera on iPhone 22 Pro.'))
        announced = module.article_reconciliation_profile(article_for(module,
            'Apple adds variable aperture to iPhone 22 Pro',
            'Apple announced a variable aperture camera for iPhone 22 Pro today.', source='Other'))
        self.assertIn('camera-adoption-stage:reported', predicted.separation_keys)
        self.assertIn('camera-adoption-stage:announced', announced.separation_keys)
        self.assertNotEqual(module.profile_pair_decision(predicted, announced), 'match')
        wrong_target = module.article_reconciliation_profile(article_for(module,
            "The iPhone 22 Pro's Rumored Camera Upgrade, Explained",
            'Apple is expected to introduce a variable-aperture main camera on iPhone 21 Pro.'))
        self.assertNotIn('canonical-apple-action:iphone-22-pro:camera-system-adoption', wrong_target.event_keys)
        for title, lead in (
            ('Should you buy iPhone 21 after the price increase?', 'This buying guide compares alternatives and advises which phone you should buy.'),
            ('Samsung raises phone prices', 'Samsung changed its own official prices. Apple iPhone prices remain unchanged.'),
        ):
            with self.subTest(editorial=title):
                profile = module.source_text_profile(title,lead,[lead],'Synthetic')
                self.assertNotEqual(profile.relevance_tier, 'strong')

    def test_camera_local_continuity_keeps_role_model_and_history(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, facts=[lead]))
        title = "iPhone 22 Pro's variable aperture looks delicate"
        context = 'The adjustable opening offers new shooting options. '
        for sentence, expected in (
            ('Apple says iPhone 22 Pro has a new variable aperture camera.', True),
            ('Apple says iPhone 21 Pro has a new variable aperture camera.', False),
            ('Samsung says iPhone 22 Pro has a new variable aperture camera.', False),
            ('Previously, Apple says iPhone 22 Pro has a new variable aperture camera.', False),
            ('Apple says iPhone 22 Pro does not have a new variable aperture camera.', False),
            ('Existing rumors discuss the use of a variable aperture camera.', False),
        ):
            with self.subTest(statement=sentence):
                p = profile(title, context + sentence)
                self.assertEqual('canonical-apple-action:iphone-22-pro:camera-system-adoption' in p.event_keys, expected)
                if expected:
                    self.assertIn('camera-adoption-stage:announced', p.separation_keys)
        title = 'Morgan Lake teases variable aperture in iPhone 22 Pro before event'
        for lead, expected in (
            ('Apple CEO Morgan Lake shared a preview video for iPhone 22 Pro. No specifications have been announced.', True),
            ('Apple CEO Casey Stone shared a preview video for iPhone 22 Pro. No specifications have been announced.', False),
            ('Samsung CEO Morgan Lake shared a preview video for iPhone 22 Pro.', False),
            ('Last year Apple CEO Morgan Lake shared a preview video for iPhone 22 Pro.', False),
        ):
            with self.subTest(executive=lead):
                p = profile(title, lead)
                self.assertEqual(any('pre-event-preview-publication' in key for key in p.event_keys), expected)
                self.assertFalse(any(key.startswith('canonical-apple-action:') and key.endswith(':camera-system-adoption') for key in p.event_keys))

    def test_video_publication_uses_depicted_relation_and_publisher_not_predicted_model(self):
        module = load_module()
        from test_relevance_rules import article_for
        title = 'Morgan Lake teases variable aperture in iPhone 22 Pro before event'
        lead = 'Apple CEO Morgan Lake posted a short preview video today. The video shows a light shrinking against dark glass. Reporters speculate about the iPhone 22 Pro camera.'
        def profile(text):
            return module.article_reconciliation_profile(article_for(module, title, text, facts=[text]))
        original = profile(lead)
        subject = {key for key in original.separation_keys if key.startswith('primary-claim-subject:apple-ceo-video:')}
        self.assertEqual(len(subject), 1)
        for before, after in (('shrinking','growing'),('glass','metal'),('light','logo')):
            with self.subTest(content=(before,after)):
                other = profile(lead.replace(before, after))
                self.assertTrue(any(key.startswith('primary-claim-subject:apple-ceo-video:') for key in other.separation_keys))
                self.assertFalse(subject & other.separation_keys)
                self.assertNotEqual(module.profile_pair_decision(original,other), 'match')
        other_publisher = module.article_reconciliation_profile(article_for(module,
            title.replace('Morgan Lake','Casey Stone'), lead.replace('Morgan Lake','Casey Stone'),
            facts=[lead.replace('Morgan Lake','Casey Stone')]))
        self.assertNotEqual(module.profile_pair_decision(original, other_publisher), 'match')
        for text in (lead.replace('Apple CEO Morgan Lake','Samsung CEO Morgan Lake'),
                     lead.replace('Apple CEO Morgan Lake','Apple CEO Casey Stone'),
                     lead.replace('shows a light','does not show a light')):
            with self.subTest(publisher=text):
                self.assertFalse(any(key.startswith('primary-claim-subject:apple-ceo-video:') for key in profile(text).separation_keys))

    def test_current_action_authority_keeps_measurement_model_and_report_roles(self):
        module = load_module()
        from test_relevance_rules import article_for
        rows = [['preorder', 'iPhone 22 Pro预购预计10月17日开启', '据消息人士报道，iPhone 22 Pro预购将于10月17日开启，苹果尚未公布预购日期。'], ['preorder-background', 'iPhone 22 Pro预购时间推迟至10月17日', '消息人士称iPhone 22 Pro预购时间预计推迟至10月17日，苹果尚未公布预购日期。', ['消息人士称iPhone 22 Pro预购时间预计推迟至10月17日，苹果尚未公布预购日期。', '作为既有产品背景，iPhone 22 Pro和Pro Max采用6.2英寸和6.8英寸显示屏。']], ['screen', 'iPhone 22 Pro系列正面屏幕亮相：首发小号灵动岛', '苹果今日公布iPhone 22 Pro系列的新屏幕设计，灵动岛变小了。', ['苹果今日公布iPhone 22 Pro系列的新屏幕设计，灵动岛变小了。', 'iPhone 22 Pro和Pro Max采用6.2英寸和6.8英寸显示屏。']], ['camera', 'Both iPhone 22 Pro models feature variable aperture camera', 'Apple has revealed that both iPhone 22 Pro models have a variable aperture camera system.'], ['camera-same', 'Apple adds variable aperture to the iPhone 22 Pro camera', 'Apple announced a variable aperture camera system for both iPhone 22 Pro models today.'], ['foldable', '苹果iPhone Horizon亮相 正式推出折叠屏产品 售价2499美元起', '苹果终于正式进入折叠屏手机市场，推出首款折叠式iPhone，产品名称确定为iPhone Horizon。该机后置双摄像头，主摄和超广角均为3600万像素。'], ['price-direct', 'Apple raises iPhone 21 and iPhone Air prices', 'Apple raised the official prices of iPhone 21 and iPhone Air by $80 today.'], ['price-paraphrase', 'iPhone 21 and iPhone Air just got more expensive', 'Apple has applied an $80 price hike to iPhone 21 and iPhone Air today. The same hardware now costs more.'], ['price-zh', '芯片成本上涨逼迫苹果上调iPhone 21及iPhone Air官方售价', '苹果今天宣布上调仍在销售的iPhone 21和iPhone Air官方零售价格，两款机型均上涨80美元。'], ['price-long-model-list', '芯片成本飙升逼迫苹果上调iPhone 21、21e及iPhone Air官方售价', '在刚刚结束的发布会之后，苹果宣布逆势上调仍在销售序列中的iPhone 21、iPhone 21e以及iPhone Air的官方零售价格。'], ['vision-release', 'visionOS 29 is here for Apple Vision Pro with these new features', 'Apple Vision Pro gets its next major software update today. visionOS 29 is available to the public now. Siri AI is its main new feature.'], ['vision-features', 'visionOS 29 adds Siri AI to your spatial computing environment', 'Even as Apple reorganizes its hardware team, visionOS 29 is available for public download. After a summer of beta testing, the new release brings Siri AI and interface improvements.'], ['vision-same-release', 'Apple releases visionOS 29 to Vision Pro users', 'Apple released visionOS 29 to all Vision Pro users today with new Siri AI features.'], ['vision-other-version', 'Apple releases visionOS 28 to Vision Pro users', 'Apple released visionOS 28 to all Vision Pro users today.'], ['catalogue', 'More Than 1,400 Apple Watch Bands Have Been Released Since 2017', 'Apple has now released more than 1,400 official Apple Watch bands since 2017, according to Alex Morris, who develops the BandIndex catalogue.'], ['catalogue-translation', '苹果 Apple Watch 官方表带累计已超1400款，最贵售价15999元', '科技媒体今天报道称，自2017年以来苹果已推出超过1400款官方Apple Watch表带。该消息来自Alex Morris开发的BandIndex目录应用，属于同一统计报告。']]
        articles = {row[0]: article_for(module, row[1], row[2], source=row[0], facts=row[3] if len(row)>3 else [row[2]]) for row in rows}
        profiles = {label:module.article_reconciliation_profile(article) for label,article in articles.items()}
        for left, right, expected in [('preorder', 'preorder-background', True), ('preorder-background', 'screen', False), ('camera', 'camera-same', True), ('camera', 'foldable', False), ('price-direct', 'price-paraphrase', True), ('price-direct', 'price-zh', True), ('price-direct', 'price-long-model-list', True), ('vision-release', 'vision-features', True), ('vision-release', 'vision-same-release', True), ('vision-release', 'vision-other-version', False), ('catalogue', 'catalogue-translation', True)]:
            with self.subTest(pair=(left,right)):
                self.assertEqual(module.profile_pair_decision(profiles[left],profiles[right])=='match', expected)
        for expected_groups in (
            (('preorder','preorder-background'),('screen',)),
            (('camera','camera-same'),('foldable',)),
            (('price-direct','price-paraphrase','price-zh','price-long-model-list'),),
            (('vision-release','vision-features','vision-same-release'),),
            (('catalogue','catalogue-translation'),),
        ):
            with self.subTest(groups=expected_groups):
                selected=[articles[name] for group in expected_groups for name in group]
                events=module.cluster_articles(selected)
                self.assertEqual({frozenset(a.url for a in event.articles) for event in events},
                                 {frozenset(articles[name].url for name in group) for group in expected_groups})
        for name in ('price-direct','price-paraphrase','price-zh','price-long-model-list'):
            with self.subTest(price=name):
                self.assertEqual(profiles[name].relevance_tier,'strong')
                self.assertIn('price-change',profiles[name].identity.title_actions)

    def test_subsidy_amount_does_not_authorize_device_price_forecast(self):
        module = load_module()
        rows = (
            ('iPhone 19 Pro 星河商城首发：以旧换新补贴达800元，24期分期免息', '星河商城公布新机渠道活动，平台提供以旧换新补贴和分期优惠，苹果没有调整设备售价。', False),
            ('iPhone 19 Pro 起售价预计上涨800元', '分析师预测苹果新机起售价会上涨800元。', True),
            ('iPhone 19 Pro 预计周五开始预订', '该报道只预测预订开始日期，没有提供新价格。', False),
        )
        for title, lead, expected in rows:
            with self.subTest(title=title):
                self.assertEqual(module.is_future_apple_product_price_forecast_story(title+' '+lead,title), expected)
                profile=module.source_text_profile(title,lead,[],'Synthetic')
                if not expected:
                    self.assertNotIn('apple-future-product-price-forecast',profile.identity.facets)
                    self.assertNotIn('apple-product-price-increase',profile.identity.facets)

    def test_current_release_and_catalogue_relations_keep_local_scope(self):
        module = load_module()
        from test_relevance_rules import article_for
        from apple_news_core.event_identity import current_public_os_release
        title = 'visionOS 29 adds Siri AI to Vision Pro'
        self.assertEqual(current_public_os_release(title, 'visionOS 29 is available for public download.'), ('visionos', '29'))
        for other_title, lead in (
            (title, 'Previously, visionOS 29 is available for public download.'),
            (title, 'visionOS 29 is not yet available for public download.'),
            (title, 'visionOS 28 is available for public download.'),
            (title, 'If visionOS 29 is available for public download, users can upgrade.'),
            ('visionOS 29 beta adds Siri AI', 'visionOS 29 is available for public download.'),
            ('visionOS 29 will add Siri AI next year', 'visionOS 29 is available for public download.'),
            ('Siri AI adds a new voice', 'visionOS 29 is available for public download.'),
        ):
            with self.subTest(release=(other_title, lead)):
                self.assertIsNone(current_public_os_release(other_title, lead))
        band_title = 'More Than 1,400 Apple Watch Bands Have Been Released Since 2017'
        band_lead = 'Apple has now released more than 1,400 official Apple Watch bands since 2017, according to Alex Morris, who develops the BandIndex catalogue.'
        original = module.article_reconciliation_profile(article_for(module, band_title, band_lead, facts=[band_lead]))
        self.assertTrue(any('cumulative-count-report' in key for key in original.event_keys))
        for replacement in (('Alex Morris', 'Casey Brooks'), ('BandIndex', 'StrapBook'), ('2017', '2018'), ('1,400', '1,500')):
            lead = band_lead.replace(*replacement)
            other = module.article_reconciliation_profile(article_for(module, band_title.replace(*replacement), lead, source='Other', facts=[lead]))
            with self.subTest(catalogue=replacement):
                self.assertNotEqual(module.profile_pair_decision(original, other), 'match')
        camera = module.article_reconciliation_profile(article_for(module, 'Apple adds variable aperture to iPhone 22 Pro', 'Apple announced a variable aperture camera for iPhone 22 Pro today.'))
        other = module.article_reconciliation_profile(article_for(module, 'Apple adds variable aperture to iPhone 21 Pro', 'Apple announced a variable aperture camera for iPhone 21 Pro today.', source='Other'))
        self.assertNotEqual(module.profile_pair_decision(camera, other), 'match')
        for title, expected in (
            ('iPhone 19 Pro 起售价预计上涨800元，平台另提供分期优惠', True),
            ('iPhone 19 Pro 平台提供800元优惠券及分期免息', False),
            ('iPhone 19 Pro 以旧换新返现800元', False),
        ):
            with self.subTest(amount=title):
                self.assertEqual(module.is_future_apple_product_price_forecast_story(title, title), expected)

    def test_asset_transfer_and_named_threat_reports_keep_local_objects(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        asset = article_for(module, 'Apple acquires Northstar', 'Apple acquired Northstar assets and hired its employees.')
        transfer = article_for(module, 'SignalKit acquired by Apple', 'Apple bought assets from Northstar and brought members of the SignalKit team into Apple.', source='Other')
        self.assertTrue(module.should_merge(asset, event_for(module, transfer)))
        for lead in (
            'Google bought assets from Northstar and brought the SignalKit team into Google.',
            'Apple bought assets from Southstar and brought the SignalKit team into Apple.',
            'Apple may buy assets from Northstar and hire the SignalKit team.',
            'Apple bought assets from Northstar last year and hired the SignalKit team.',
        ):
            with self.subTest(asset=lead):
                other = article_for(module, 'SignalKit acquired by Apple', lead, source='Other')
                self.assertFalse(module.should_merge(asset, event_for(module, other)))
        threat = article_for(module, 'QuartzStealer Malware Steals Mac Passwords', 'QuartzStealer targets macOS and impersonates a crash reporter.')
        identified = article_for(module, 'Beware of fake Mac crash reports', 'Jamf identified the same malware as QuartzStealer after seeing active macOS infections.', source='Other')
        self.assertTrue(module.should_merge(threat, event_for(module, identified)))
        for lead in (
            'Jamf identified the same malware as PearlStealer after seeing active macOS infections.',
            'Jamf identified the same malware as QuartzStealer after seeing active Windows infections. macOS is only a comparison.',
            'Last year Jamf identified the same malware as QuartzStealer after seeing macOS infections.',
            'Jamf may identify the malware as QuartzStealer if macOS infections are confirmed.',
        ):
            with self.subTest(threat=lead):
                other = article_for(module, 'Beware of fake Mac crash reports', lead, source='Other')
                self.assertFalse(module.should_merge(threat, event_for(module, other)))
        for lead in (
            'PearlStealer 恶意软件窃取 macOS 密码。',
            '该恶意软件去年窃取 macOS 密码。',
            '该恶意软件并未窃取 macOS 密码。',
            '该恶意软件窃取 Windows 凭据。macOS 仅是背景比较。',
        ):
            with self.subTest(referred_threat=lead):
                other = article_for(module, 'QuartzStealer 攻击披露：针对苹果 Mac 用户', lead, source='Other')
                self.assertFalse(module.should_merge(threat, event_for(module, other)))
        vulnerability = article_for(module, 'Three AirDrop vulnerabilities discovered', 'Researchers found AirDrop vulnerabilities affecting iPhone and Mac.')
        feature = article_for(module, '苹果隔空投送新增进度指示器', '苹果为隔空投送新增传输进度指示器。', source='Other')
        self.assertFalse(module.should_merge(vulnerability, event_for(module, feature)))

    def test_completed_naming_results_keep_aspect_and_modal_scope(self):
        module = load_module()
        from dataclasses import replace
        from test_relevance_rules import article_for
        rows = [('forecast', "Apple's foldable will be named iPhone Horizon, says analyst", 'An analyst reports that Apple will name its foldable iPhone Horizon. Apple has not announced the device yet.'), ('current-retrospective', "Apple's foldable is here and it is called iPhone Horizon", 'Five years of rumors have now led to Apple revealing the iPhone Horizon today. The foldable device is now official. Customers will be able to buy it next month.'), ('current-direct', 'Apple unveils foldable named iPhone Horizon', 'Apple unveiled its foldable, officially named iPhone Horizon, today. The phone will go on sale next month.'), ('forecast-control', 'Report: Apple foldable may be called iPhone Horizon', 'An analyst says the foldable iPhone will be named iPhone Horizon. Apple has not revealed the phone.'), ('future-only', "Apple's foldable may be called iPhone Horizon", 'Apple is expected to reveal a foldable called iPhone Horizon next month. The announcement has not happened.'), ('uncertain', "Apple's foldable may be called iPhone Horizon", 'It is unclear whether Apple has revealed a foldable called iPhone Horizon. The report provides no confirmation.'), ('uncertain-result', "Apple's foldable may be called iPhone Horizon", 'It is unclear whether years of speculation have now led to Apple revealing iPhone Horizon.'), ('negative-result', "Apple's foldable may be called iPhone Horizon", 'Years of rumors have not led to Apple revealing iPhone Horizon. There is no current announcement.')]
        articles = []
        for index, (_, title, lead) in enumerate(rows):
            article = article_for(module, title, lead, source='Completed' + str(index), facts=[lead])
            article.evidence = replace(module.capture_article_title_evidence(
                article.source, article.url, article.title, article.summary, tuple(article.key_facts)), content_form='news')
            articles.append(article)
        profiles = [module.article_reconciliation_profile(article) for article in articles]
        for index, profile in enumerate(profiles):
            with self.subTest(stage=index):
                self.assertEqual('product-disclosure-stage:announced' in profile.separation_keys, index in (1, 2))
        for left, right, expected in ((0, 1, False), (1, 2, True), (0, 3, True)):
            with self.subTest(pair=(left, right)):
                self.assertEqual(module.profile_pair_decision(profiles[left], profiles[right]) == 'match', expected)
        self.assertEqual({frozenset(article.url for article in event.articles) for event in module.cluster_articles(articles)},
                         {frozenset(articles[i].url for i in group) for group in ((1, 2), (0, 3, 4, 5, 6, 7))})
        for lead, expected in (
            ('Several years of speculation have led to Apple unveiling iPhone Horizon today.', True),
            ('Several years of speculation have finally led to Apple unveiling iPhone Horizon today.', True),
            ('Several years of speculation have now culminated in Apple revealing iPhone Horizon today.', True),
            ('Several years of speculation could lead to Apple unveiling iPhone Horizon next month.', False),
            ('Several years of speculation could have finally led to Apple unveiling iPhone Horizon.', False),
            ('Several years of speculation have not led to Apple unveiling iPhone Horizon.', False),
            ('Several years of speculation have still not led to Apple unveiling iPhone Horizon.', False),
            ('Several years of speculation have reportedly led to Apple unveiling iPhone Horizon.', False),
            ('Several years of speculation have finally led to Samsung unveiling iPhone Horizon today.', False),
            ('Several years of speculation have finally led to Apple unveiling iPhone Compass today.', False),
            ('Several years of speculation have finally led to Apple unveiling iPhone Horizon last year.', False),
        ):
            with self.subTest(lead=lead):
                profile = module.article_reconciliation_profile(article_for(module, rows[1][1], lead, facts=[lead]))
                self.assertEqual('product-disclosure-stage:announced' in profile.separation_keys, expected)

    def test_product_naming_does_not_approve_reported_name_and_announced_launch(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        rumor = article_for(module, "Apple's foldable iPhone reportedly named iPhone Prism",
                            'A new analyst report claims Apple will name its foldable iPhone iPhone Prism.')
        launch = article_for(module, 'Apple unveils iPhone Prism, its first foldable iPhone',
                             'Apple announced its first foldable iPhone, named iPhone Prism, today, with prices starting at $2199.', source='Other')
        self.assertFalse(module.should_merge(rumor, event_for(module, launch)))
        self.assertFalse(module.should_merge(launch, event_for(module, rumor)))
        self.assertEqual(len(module.cluster_articles([rumor, launch])), 2)

    def test_photo_authentication_has_specific_action_support_not_camera_topic(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        left = article_for(module, 'iPhone 22 Pro verifies photo authenticity with cryptographic data',
                           'Apple adds cryptographic verification to photos captured by the iPhone 22 Pro camera.')
        right = article_for(module, 'Apple adds photo verification to iPhone 22 Pro',
                            'The iPhone 22 Pro camera now records cryptographic authenticity data for photographs.', source='Other')
        launch = article_for(module, 'Apple unveils iPhone Prism, its first foldable iPhone',
                             'Apple announced its first foldable iPhone, named iPhone Prism, today with a new camera system.', source='Launch')
        self.assertTrue(module.should_merge(left, event_for(module, right)))
        self.assertFalse(module.should_merge(left, event_for(module, launch)))
        self.assertEqual(sorted(len(e.articles) for e in module.cluster_articles([left, right, launch])), [1, 2])
        # A component label alone is only a topic, not a source action.
        from dataclasses import replace
        profile = module.article_reconciliation_profile(left)
        other = module.article_reconciliation_profile(launch)
        profile = replace(profile, event_keys=frozenset({'structured-component:camera-system:iphone'}))
        other = replace(other, event_keys=frozenset({'structured-component:camera-system:iphone'}))
        self.assertNotEqual(module.profile_pair_decision(profile, other), 'match')

    def test_local_paragraph_enumerations_preserve_each_owned_sentence(self):
        module = load_module()
        from test_relevance_rules import article_for
        cases = [
            ('苹果为 iOS 29 相机新增校准工具', '苹果为 iOS 29 的相机 App 新增校准工具。',
             ['校准工具提供石英、靛蓝、铜色、翡翠和琥珀五种预设。', '显示可切换为网格、轮廓或散点三种方式。']),
            ('苹果为 iOS 29 相机新增校准工具', '苹果为 iOS 29 的相机 App 新增校准工具。',
             ['校准预设可选石英或靛蓝或铜色。']),
            ('iPhone 21 Pro preorder schedule announced', 'Apple announced iPhone 21 Pro preorders will begin November 6.',
             ['The initial launch countries include St. Lucia, Austria, Chile, and Oman.']),
            ('Apple adds camera calibration modes to iOS 29', 'Apple added camera calibration modes to the Camera app in iOS 29.',
             ['These controls work during preview.', 'Available calibration modes include Jasper, Opal, Onyx, Garnet, and Topaz.']),
        ]
        for index, (title, lead, sentences) in enumerate(cases):
            with self.subTest(index=index):
                article = article_for(module, title, lead, source='Synthetic', facts=[lead])
                article.url = f'https://example.test/local-list-{index}'
                html = f'<article><h1>{title}</h1><p>{lead}</p><p>{" ".join(sentences)}</p></article>'
                article.evidence = module.capture_article_evidence(article.source, article.url, html, title)
                events = [module.event_to_dict(e, module.ZoneInfo('Asia/Singapore')) for e in module.cluster_articles([article])]
                for sentence in sentences:
                    if sentence.startswith('These controls'):
                        continue
                    self.assertTrue(any(sentence in e['key_facts'] for e in events), sentence)
                    origins = [o for e in events for f in e['fact_sources'] if f['text'] == sentence for o in f['origins']]
                    self.assertTrue(origins)
                    for origin in origins:
                        unit = next(u for u in article.evidence.units if u.unit_id == origin['unit_id'])
                        self.assertEqual(unit.text[origin['start']:origin['end']], sentence)

    def test_preorder_stage_uses_owned_current_statement_after_neutral_date(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        forecast = article_for(module, 'MacBook Neo preorders expected to open in November',
                               'A source claims MacBook Neo preorders will begin November 6.')
        official = article_for(module, 'MacBook Neo preorders officially announced',
                               'Apple announced MacBook Neo preorders will begin November 6.', source='Official')
        prefix = 'Customers can place preorders for MacBook Neo beginning November 6. '
        for tail, expected_stage in (
            ('Apple has now announced the MacBook Neo preorder schedule.', 'announced'),
            ('Samsung has now announced its Galaxy laptop preorder schedule.', None),
            ('Apple announced an earlier MacBook Neo preorder schedule last year.', None),
            ('Apple might have announced the MacBook Neo preorder schedule.', None),
            ('Apple has now announced the MacBook Pro preorder schedule.', None),
        ):
            with self.subTest(tail=tail):
                item = article_for(module, 'MacBook Neo preorders begin in November', prefix + tail, source='Other')
                stages = {key for key in module.article_reconciliation_profile(item).separation_keys if key.startswith('preorder-stage:')}
                self.assertEqual(stages, {'preorder-stage:' + expected_stage} if expected_stage else set())
                if expected_stage:
                    self.assertFalse(module.should_merge(forecast, event_for(module, item)))
                    self.assertTrue(module.should_merge(official, event_for(module, item)))
                    self.assertEqual(sorted(len(e.articles) for e in module.cluster_articles([forecast, official, item])), [1, 2])

    def test_hardware_launch_windows_keep_range_and_earliest_constraints(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        base = article_for(module, 'Apple HomeHub launch planned for October 2027',
                           'Apple plans to launch its HomeHub in October 2027.')
        for month, year, expected in (('October', 2027, True), ('March', 2027, False), ('October', 2028, False)):
            other = article_for(module, f'Apple HomeHub launch window is {month} {year}',
                                f'Apple plans to launch its HomeHub in {month} {year}.', source='Other')
            with self.subTest(month=month, year=year):
                self.assertEqual(module.should_merge(base, event_for(module, other)), expected)
        earliest = article_for(module, 'Apple HomeHub launch may start as early as October 2027',
                               'Apple plans to launch HomeHub as early as October 2027.')
        november = article_for(module, 'Apple HomeHub planned for November 2027',
                               'Apple plans to launch HomeHub in November 2027.', source='Other')
        self.assertTrue(module.should_merge(earliest, event_for(module, november)))
        self.assertIn('hardware-launch-window:apple-home-hub:2027:10:open', module.article_reconciliation_profile(earliest).separation_keys)
        foreign_year = article_for(module, 'Apple HomeHub launch planned for October',
                                   'Apple plans to launch MacBook Pro in March 2028.', source='Other')
        self.assertIn('hardware-launch-window:apple-home-hub:unspecified:10:10', module.article_reconciliation_profile(foreign_year).separation_keys)
        with self.subTest(modal='may still'):
            modal = article_for(module, 'Apple HomeHub may still launch in October 2027',
                                'Apple may still launch its HomeHub in October 2027.', source='Other')
            self.assertIn('hardware-launch-window:apple-home-hub:2027:10:10', module.article_reconciliation_profile(modal).separation_keys)
        for date_phrase, lower, upper in (('in May 2027', 5, 5), ('between March and May 2027', 3, 5)):
            with self.subTest(calendar_may=date_phrase):
                calendar = article_for(module, f'Apple HomeHub launch planned {date_phrase}',
                                       f'Apple plans to launch HomeHub {date_phrase}.', source='Other')
                self.assertIn(f'hardware-launch-window:apple-home-hub:2027:{lower}:{upper}', module.article_reconciliation_profile(calendar).separation_keys)
        with self.subTest(unknown_year_different_month=True):
            march = article_for(module, 'Apple HomeHub launch planned for March 2028',
                                'Apple plans to launch HomeHub in March 2028.', source='Other')
            self.assertFalse(module.should_merge(foreign_year, event_for(module, march)))
        for title, lead in (
            ('9月巅峰对决！华为Mate 90系列迎战iPhone 18 Pro', '华为 Mate 90 系列计划 9 月发布，报道将其与苹果 iPhone 18 Pro 发布窗口和市场竞争作比较。'),
            ('Apple HomeHub roadmap update', 'Apple plans to launch MacBook Pro in October 2027.'),
            ('Apple cancels HomeHub launch planned for October 2027', 'Apple canceled the HomeHub launch that was planned for October 2027.'),
        ):
            unrelated = article_for(module, title, lead, source='Other')
            self.assertFalse(any(key.startswith('hardware-launch-window:') for key in module.article_reconciliation_profile(unrelated).separation_keys))

    def test_planned_launch_is_not_a_product_capability_update(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        rows = [
            ("Apple Home hub roadmap update", "Apple's Home Hub remains planned for this year."),
            ("Apple Smart Home Display Still Coming This Year", "Apple still plans to release its smart home hub this year."),
            ("苹果 Home Hub 或将支持人脸识别自动切换个人资料", "苹果智能家居中枢将支持个人资料切换。"),
        ]
        articles = [article_for(module, title, lead, source=f'Source{i}') for i, (title, lead) in enumerate(rows)]
        self.assertTrue(module.should_merge(articles[0], event_for(module, articles[1])))
        self.assertFalse(module.should_merge(articles[0], event_for(module, articles[2])))
        self.assertCountEqual([tuple(sorted(a.source for a in e.articles)) for e in module.cluster_articles(articles)],
                              [('Source0', 'Source1'), ('Source2',)])

    def test_currency_amount_is_not_a_phone_production_target(self):
        module = load_module()
        from test_relevance_rules import article_for
        for title, lead in (
            ("奢侈定制品牌Caviar替苹果率先发布iPhone Ultra折叠机：售价10万起",
             "第三方厂商结合渲染图提前推出定制系列，苹果官方尚未发布该机型。"),
            ("A custom iPhone model costs $2 million",
             "An independent designer plans production of a custom case. Apple has not announced a new iPhone."),
        ):
            with self.subTest(title=title):
                article = article_for(module, title, lead, source='9to5Mac')
                profile = module.article_reconciliation_profile(article)
                self.assertFalse(any(':production-target:' in key for key in profile.event_keys))
                self.assertEqual(article.relevance_tier, 'weak')


    def test_camera_airpods_disclosed_capability_is_not_development_suspension(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        code = article_for(module, 'AirPods with cameras show up in iOS 27 beta code',
            "Code describes two images from cameras on either side of a user's head, pointing to camera-equipped AirPods.")
        pause = article_for(module, 'Camera-Equipped AirPods Pro Development Suspended, Leaker Claims',
            "Development of Apple's rumored camera-equipped AirPods Pro has been halted. Kosutami says the project was suspended.", source='MacRumors')
        for a, b in ((code, pause), (pause, code)):
            self.assertFalse(module.should_merge(a, event_for(module, b)))
        self.assertEqual(len(module.cluster_articles([code, pause])), 2)
        delayed = article_for(module, 'Camera-equipped AirPods reportedly delayed until 2027',
            'Apple is still developing camera-equipped AirPods; the previously planned model was canceled.')
        for year, expected in ((2027, True), (2028, False)):
            with self.subTest(delayed_until=year):
                other = article_for(module, f'消息称苹果摄像头 AirPods 延至 {year} 年推出',
                    '苹果仍在开发摄像头 AirPods，原项目已经取消。', source='IT之家')
                self.assertEqual(module.should_merge(delayed, event_for(module, other)), expected)
                self.assertEqual(module.should_merge(other, event_for(module, delayed)), expected)


    def test_editorial_conditional_conclusion_stays_visible_without_becoming_reported_fact(self):
        module = load_module()
        title = "A foldable Mac is still years away: my view"
        conclusion = "But I do think an all-screen foldable Mac will eventually arrive once a soft keyboard can replace a physical keyboard."
        timing = "That is not going to happen anytime soon."
        url = 'https://9to5mac.com/2026/09/10/foldable-opinion/'
        page = f'<meta property="article:published_time" content="{module.utc_now().isoformat()}"><article><h1>{title}</h1><p>Personally, I think the current foldable Mac concept is impractical. This is my opinion, with no new reporting.</p><p>{conclusion} {timing}</p></article>'
        with tempfile.TemporaryDirectory() as directory:
            args = module.parse_args(['--timezone', 'Asia/Singapore', '--cache-dir', directory])
            with patch.object(module, 'collect_candidates_from_sources', return_value=[module.Candidate('9to5Mac', url, title)]), \
                 patch.object(module, 'fetch_url', return_value=page):
                result = module.run(args)
        events = result['events'] + result['deferred_events']
        self.assertTrue(events)
        self.assertTrue(all(event['relevance_tier'] == 'weak' for event in events))
        reviews = [item for item in result['final_brief_queue'] if item.get('unprocessed_evidence')]
        for text in (conclusion, timing):
            matches = [(item, unit) for item in reviews for unit in item['unprocessed_evidence'] if unit['text'] == text]
            self.assertTrue(matches, text)
            self.assertIn(text, module.render_brief_scaffold(result))
            for item, unit in matches:
                self.assertEqual(item['source_urls'], [url])
                self.assertTrue(item['reason'])
                original = next(u for u in result['source_evidence'][item['evidence_id']]['units'] if u['unit_id'] == unit['unit_id'])
                self.assertEqual(original['text'][unit['start']:unit['end']], text)


    def test_content_contest_pairs_require_same_work_and_apple_action_owner(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        left = article_for(module, 'Apple announces Harbor Nights look-alike contest', 'Apple TV announced a Harbor Nights look-alike contest.')
        for title, lead, expected in (
            ("Apple is holding a 'Harbor Nights' look-alike contest", 'Apple is hosting the Harbor Nights contest.', True),
            ('Apple announces Northern Lights look-alike contest', 'Apple TV announced a Northern Lights look-alike contest.', False),
            ('Netflix is holding a Harbor Nights look-alike contest', 'Netflix is hosting the contest; Apple TV is mentioned as background.', False),
        ):
            with self.subTest(title=title):
                right = article_for(module, title, lead, source='MacRumors')
                for a, b in ((left, right), (right, left)):
                    self.assertEqual(module.should_merge(a, event_for(module, b)), expected)
                self.assertEqual(len(module.cluster_articles([left, right])), 1 if expected else 2)


    def test_market_percentage_ownership_and_report_period_constrain_pair(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        left = article_for(module, 'Omdia报告2026Q2全球智能手机份额：苹果占20%、三星占22%',
            'Omdia报告苹果2026年第二季度全球智能手机份额达到20%。')
        for title, lead, expected in (
            ('Omdia报告2026Q2全球智能手机份额：苹果占22%、三星占20%', 'Omdia报告苹果2026年第二季度全球智能手机份额达到22%。', False),
            ('Omdia报告2027Q2全球智能手机份额：苹果占20%、三星占22%', 'Omdia报告苹果2027年第二季度全球智能手机份额达到20%。', False),
            ('Omdia报告2026Q2全球智能手机份额：苹果占20%、三星占18%', 'Omdia报告苹果2026年第二季度全球智能手机份额达到20%。', True),
        ):
            with self.subTest(title=title):
                right = article_for(module, title, lead, source='IT之家')
                for a, b in ((left, right), (right, left)):
                    self.assertEqual(module.should_merge(a, event_for(module, b)), expected)
                self.assertEqual(len(module.cluster_articles([left, right])), 1 if expected else 2)


    def test_market_metrics_and_from_to_relations_are_not_flat_percentage_sets(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        cases = [
            (('Omdia报告2026Q2全球智能手机份额：苹果占20%', '苹果2026年第二季度全球智能手机市场份额为20%。'),
             ('Omdia报告2026Q2全球智能手机出货量：苹果增长20%', '苹果2026年第二季度全球智能手机出货量同比增长20%。')),
            (('Omdia报告2026Q2全球PC市场苹果Mac份额变化', '苹果Mac市场份额从8.5%升至9.9%。'),
             ('Omdia报告2026Q2全球PC市场苹果Mac份额变化', '苹果Mac市场份额从9.9%降至8.5%。')),
        ]
        for left_input, right_input in cases:
            with self.subTest(left=left_input, right=right_input):
                left = article_for(module, *left_input)
                right = article_for(module, *right_input, source='IT之家')
                for a, b in ((left, right), (right, left)):
                    self.assertFalse(module.should_merge(a, event_for(module, b)))
                self.assertEqual(len(module.cluster_articles([left, right])), 2)


    def test_supplier_contract_and_relief_claims_preserve_named_boundaries(self):
        module = load_module()
        from test_relevance_rules import article_for, event_for
        cases = [
            (('Apple and Broadcom extend chip supply agreement through 2031', 'Apple renewed its Broadcom chip supply contract until 2031.'),
             ('Apple and Broadcom extend chip supply agreement through 2032', 'Apple renewed its Broadcom chip supply contract until 2032.')),
            (('Apple and Broadcom extend chip supply agreement through 2031', 'Apple renewed its Broadcom chip supply contract until 2031.'),
             ('Apple and TSMC extend chip supply agreement through 2031', 'Apple renewed its TSMC chip supply contract until 2031.')),
            (('Apple pledges donations for flood relief in India', 'Apple will donate to flood relief and rebuilding in India.'),
             ('Apple pledges donations for earthquake relief in India', 'Apple will donate to earthquake relief and rebuilding in India.')),
        ]
        for left_input, right_input in cases:
            with self.subTest(left=left_input[0], right=right_input[0]):
                left = article_for(module, *left_input)
                right = article_for(module, *right_input, source='IT之家')
                for a, b in ((left, right), (right, left)):
                    self.assertFalse(module.should_merge(a, event_for(module, b)))
                self.assertEqual(len(module.cluster_articles([left, right])), 2)


    def test_board_file_disclosures_require_same_product_and_file_action(self):
        from test_relevance_rules import article_for
        module = load_module()
        main = article_for(module, "iPhone 18 Pro board schematics leak from supplier breach",
                           "Leaked supplier files include iPhone 18 Pro logic board diagrams and component documents.", "MacRumors")
        peer = article_for(module, "iPhone 18 Pro logic board leak reveals component layout",
                           "The iPhone 18 Pro logic board leak shows processor packaging and memory layout.", "IT之家")
        self.assertEqual(len(module.cluster_articles([main, peer])), 1)
        for title, summary in [
            ("iPhone 19 Pro logic board leak reveals component layout", "The iPhone 19 Pro logic board leak shows processor packaging and memory layout."),
            ("Apple removes leaked iPhone 18 Pro logic board files", "Apple sends takedown notices to sites hosting the iPhone 18 Pro logic board diagrams."),
        ]:
            with self.subTest(title=title):
                other = article_for(module, title, summary, "9to5Mac")
                self.assertEqual(len(module.cluster_articles([peer, other])), 2)

    def test_named_security_litigation_and_store_procedure_keep_case_boundaries(self):
        from test_relevance_rules import article_for
        module = load_module()
        base = article_for(module, "Lawsuit alleges Apple chip exploit used stolen research",
            "Orion Research sued Vector Labs over the probechip7 A12/A13 SecureROM vulnerability and unpatchable BootROM exploit.", "9to5Mac")
        same = article_for(module, "Legal fight over Apple's A12 and A13 exploit research",
            "The same probechip7 A12/A13 SecureROM vulnerability led Orion Research to sue Vector Labs over stolen research.", "MacRumors")
        self.assertEqual(len(module.cluster_articles([base, same])), 1)
        other = article_for(module, "Lawsuit alleges Apple chip exploit used stolen research files",
            "Falcon Research sued Delta Labs over the probechip7 A12/A13 SecureROM vulnerability and unpatchable BootROM exploit.", "IT之家")
        self.assertEqual(len(module.cluster_articles([base, other])), 2)
        legal = article_for(module, "Apple asks to pause App Store commission case against Epic",
            "Apple filed court papers in the App Store commission and anti-steering case against Epic Games.", "9to5Mac")
        profile = module.article_reconciliation_profile(legal)
        self.assertFalse(any(key.startswith("apple-service-security:") for key in profile.event_keys))
        security = article_for(module, "Apple investigates App Store account breach",
            "Apple is investigating compromised App Store accounts and stolen login codes.", "IT之家")
        self.assertEqual(len(module.cluster_articles([legal, security])), 2)

    def test_ai_policy_evaluation_and_internal_testing_keep_local_stages(self):
        from test_relevance_rules import article_for
        module = load_module()
        evaluation = article_for(module, "Cook says Siri AI allowance policy is still being evaluated",
            "Apple CEO Tim Cook discussed Siri AI usage limits.", "9to5Mac",
            ["Cook said Apple has not yet decided the allowance model and is considering paid add-ons."])
        for title, summary in [
            ("Apple announces paid Siri AI usage limits", "Apple officially announced paid Siri AI usage limits and charges for additional requests."),
            ("Cook says iCloud+ allowance policy is still being evaluated", "Apple CEO Tim Cook is considering iCloud+ usage limits and has not yet decided the allowance model."),
        ]:
            with self.subTest(title=title):
                other = article_for(module, title, summary, "IT之家")
                self.assertEqual(len(module.cluster_articles([evaluation, other])), 2)
        historical = article_for(module, "Apple officially announces paid Siri AI usage limits",
            "Apple announced paid Siri AI usage limits today. Apple CEO Tim Cook previously said the company had not yet decided the allowance model and was considering paid add-ons.", "MacRumors")
        self.assertEqual(len(module.cluster_articles([evaluation, historical])), 2)
        third_party = article_for(module, "Google announces paid Siri AI usage limits for its extension",
            "Google today announced charges for its independent extension. Apple CEO Tim Cook previously said Apple has not yet decided the Siri AI allowance model and is considering paid add-ons.", "IT之家")
        self.assertEqual(len(module.cluster_articles([evaluation, third_party])), 2)
        self.assertEqual(module.article_reconciliation_profile(third_party).relevance_tier, "weak")
        internal = article_for(module, "Apple already testing iOS 27.4",
            "Apple engineers are internally testing iOS 27.4 according to visitor logs.", "MacRumors")
        for title, summary in [
            ("Apple already testing iOS 27.5", "Apple engineers are internally testing iOS 27.5 according to visitor logs."),
            ("Apple releases iOS 27.4", "Apple released iOS 27.4 to all users with bug fixes."),
        ]:
            with self.subTest(title=title):
                other = article_for(module, title, summary, "IT之家")
                self.assertEqual(len(module.cluster_articles([internal, other])), 2)

    def test_education_promotion_occurrence_keeps_year_and_end_date(self):
        from test_relevance_rules import article_for
        module = load_module()
        main = article_for(module, "Apple 2026 Back to School offer is now live",
            "Apple's Back to School promotion is now live in China through August 27. Eligible Mac buyers receive an Apple gift card.", "MacRumors")
        for year, end in [(2027, "August 27"), (2026, "September 20")]:
            with self.subTest(year=year, end=end):
                other = article_for(module, f"Apple {year} Back to School offer is now live in China",
                    f"Apple's Back to School promotion is now live in China through {end}. Eligible Mac buyers receive an Apple gift card.", "IT之家")
                self.assertEqual(len(module.cluster_articles([main, other])), 2)

    def test_app_acquisition_targets_do_not_follow_awards_or_delisting(self):
        from test_relevance_rules import article_for
        module = load_module()
        first = article_for(module, "Apple acquires award-winning app 'Canvas'",
            "Apple announced the acquisition of the app design tool Canvas.", "MacRumors")
        same = article_for(module, "Apple just acquired an app that won a design award",
            "Apple has acquired several apps and the latest—Canvas—won an innovation award.", "IT之家")
        self.assertEqual(len(module.cluster_articles([first, same])), 1)
        for title, summary in [
            ("Apple acquires award-winning app 'Sketchpad'", "Apple announced the acquisition of the app design tool Sketchpad."),
            ("Apple in talks to acquire app 'Canvas'", "Apple is negotiating an acquisition of Canvas and has not reached an agreement."),
            ("Apple removes app 'Canvas' from the App Store", "Apple removed Canvas from the App Store for violating review guidelines."),
        ]:
            with self.subTest(title=title):
                other = article_for(module, title, summary, "9to5Mac")
                self.assertEqual(len(module.cluster_articles([first, other])), 2)

    def test_clinical_deployment_requires_same_institution_procedure_and_stage(self):
        from test_relevance_rules import article_for
        module = load_module()
        def report(hospital, procedure):
            return article_for(module, f"Apple Vision Pro assists {procedure} surgery with MediGuide app",
                f"The first {procedure} surgery using MediGuide Vision app on Apple Vision Pro has been completed at {hospital}. The FDA-authorized app supports the surgeon.", hospital)
        first = report("Orion Health", "hip")
        for hospital, procedure in [("Delta Health", "hip"), ("Orion Health", "knee")]:
            with self.subTest(hospital=hospital, procedure=procedure):
                self.assertEqual(len(module.cluster_articles([first, report(hospital, procedure)])), 2)
        approval = article_for(module, "FDA authorizes MediGuide app on Apple Vision Pro for hip surgery",
            "The FDA authorized the MediGuide app. Orion Health plans to use it in surgery next year.", "IT之家")
        self.assertEqual(len(module.cluster_articles([first, approval])), 2)

    def test_capacity_revision_keeps_before_after_relation_and_not_cancellation(self):
        from test_relevance_rules import article_for
        module = load_module()
        first = article_for(module, "Apple slashes iPhone 21 production capacity forecast",
            "A supplier report says iPhone 21 production moved from a 12% reduction to suspending one-third of capacity.", "MacRumors")
        same = article_for(module, "苹果部分产线砍掉 iPhone 21 三分之一产能",
            "消息称 iPhone 21 产线从减产 12% 调整为暂停三分之一产能。", "IT之家")
        self.assertNotIn("project-cancellation", module.article_reconciliation_profile(same).identity.title_actions)
        self.assertEqual(len(module.cluster_articles([first, same])), 1)
        reverse = article_for(module, "Apple revises iPhone 21 production capacity forecast",
            "A supplier report says iPhone 21 production moved from a one-third reduction to suspending 12% of capacity.", "9to5Mac")
        self.assertEqual(len(module.cluster_articles([first, reverse])), 2)
        canceled = article_for(module, "Apple cancels iPhone 21 project",
            "Apple canceled the entire iPhone 21 project; the model will not launch.", "9to5Mac")
        self.assertEqual(len(module.cluster_articles([same, canceled])), 2)

    def test_hardware_binder_preserves_forecast_and_delay_actions(self):
        from test_relevance_rules import article_for
        module = load_module()
        for title, lead in [
            ("分析师预估苹果 2028Q1 发布 iPhone Air 3", "分析师预估苹果 2028Q1 发布 iPhone Air 3，具体方案仍可能变化。"),
            ("iPhone 25 今年缺席：苹果基础款手机改到明年春季发布", "苹果将标准版 iPhone 25 延期到明年春季，Pro 系列仍在秋季发布。"),
            ("iPhone 25 expected to launch next spring", "Analysts expect Apple to launch iPhone 25 next spring."),
        ]:
            with self.subTest(title=title):
                evidence = module.capture_article_evidence("Source", "https://example.com/forecast", '<article><p>'+lead+'</p></article>', title)
                projections, remaining, excluded = module.project_article_evidence(evidence)
                self.assertFalse(any(p.action == "product-launch" for p in projections))
                article = article_for(module, title, lead, "IT之家")
                self.assertIsNone(module.article_reconciliation_profile(article).bound_claim)

    def test_specific_home_hub_is_not_a_generic_accessory_recap(self):
        module = load_module()
        for title, lead in [
            ('Home Hub code hints at face-based profile switching', "macOS code shows Apple's Home Hub can identify a face and switch personal profiles."),
            ('Ambient sensing and cameras to power Apple Home Hub personalization', 'Apple Home Hub code describes cameras, ambient sensing and automatic profile switching.'),
            ('苹果 Home Hub 或将支持人脸识别自动切换个人资料', '苹果智能家居中枢将支持个人资料切换。'),
        ]:
            with self.subTest(title=title):
                self.assertFalse(module.is_routine_recap_comparison_or_buying_advice(title, lead))
        for title, lead in [
            ('Anker hub adds ports for Apple MacBook', 'The accessory adds USB ports to a MacBook.'),
            ('Should you buy Apple Home Hub?', 'Our buying advice compares the planned device with existing hubs.'),
        ]:
            with self.subTest(title=title):
                self.assertTrue(module.is_routine_recap_comparison_or_buying_advice(title, lead))


    def test_unreleased_headphone_sighting_requires_same_person_and_action(self):
        module = load_module()
        from test_relevance_rules import article_for
        left = article_for(module, 'Jordan Ellis shows off unreleased Beats headphones',
            'Jordan Ellis shows off unreleased Beats over-ear headphones with a two-tone headband.', 'MacRumors')
        same = article_for(module, '球员展示尚未发布的 Beats 头戴式耳机',
            'Jordan Ellis 展示尚未发布的 Beats 头戴式耳机，配备双色头梁。', 'IT之家')
        other = article_for(module, 'Taylor Hayes shows off unreleased Beats headphones',
            'Taylor Hayes shows off unreleased Beats over-ear headphones with a two-tone headband.', '9to5Mac')
        campaign = article_for(module, 'Jordan Ellis appears in a Beats campaign',
            'Jordan Ellis stars in a commercial for existing Beats headphones without new product details.', 'The Verge')
        self.assertEqual(module.profile_pair_decision(module.article_reconciliation_profile(left), module.article_reconciliation_profile(same)), 'match')
        for article in (other, campaign):
            self.assertNotEqual(module.profile_pair_decision(module.article_reconciliation_profile(left), module.article_reconciliation_profile(article)), 'match')


    def test_launch_delay_reporting_keeps_reported_and_official_stages_separate(self):
        module = load_module()
        from test_relevance_rules import article_for
        reports = [
            article_for(module, 'Foldable iPhone may face a launch delay in 2027', "Apple's first foldable iPhone may be delayed until the fourth quarter of 2027.", 'MacRumors'),
            article_for(module, '供应链否认苹果折叠 iPhone 在2027年延期交付', '供应链人士称苹果首款折叠 iPhone 在2027年没有延期，可以正常交付。', 'IT之家'),
        ]
        official = article_for(module, 'Apple officially announces delayed foldable iPhone launch in 2027', 'Apple officially announced its foldable iPhone launch is delayed until December 2027.', '9to5Mac')
        other_year = article_for(module, 'Foldable iPhone may face a launch delay in 2028', "Apple's first foldable iPhone may be delayed until the fourth quarter of 2028.", 'AppleInsider')
        pair = lambda a, b: module.profile_pair_decision(module.article_reconciliation_profile(a), module.article_reconciliation_profile(b))
        self.assertEqual(pair(*reports), 'match')
        self.assertNotEqual(pair(reports[0], official), 'match')
        self.assertNotEqual(pair(reports[0], other_year), 'match')


    def test_subscription_bundle_background_removal_does_not_own_current_action(self):
        module = load_module()
        from test_relevance_rules import article_for
        article = article_for(module, 'Apple adds subscription bundles to App Store',
            'Apple announced App Store subscription bundles at WWDC, along with guidelines about removing opportunistic apps.', 'MacRumors')
        profile = module.article_reconciliation_profile(article)
        self.assertFalse(any(key.startswith('app-store-removal:') for key in profile.event_keys))
        self.assertTrue(any('subscription-bundles' in key for key in profile.event_keys))
        removal = article_for(module, 'Apple removes a subscription bundles app from App Store',
            'Apple removed the subscription bundles app for violating guidelines.', '9to5Mac')
        self.assertNotEqual(module.profile_pair_decision(profile, module.article_reconciliation_profile(removal)), 'match')

    def test_payment_rewards_require_same_partner_and_redemption_action(self):
        module = load_module()
        from test_relevance_rules import article_for
        left = article_for(module, 'American Express adds Apple Pay rewards redemption',
            'American Express cardholders can redeem Membership Rewards points during Apple Pay checkout.', 'MacRumors')
        same = article_for(module, 'Amex enables Membership Rewards for Apple Pay',
            'Amex cardholders can now use Membership Rewards points during Apple Pay checkout.', '9to5Mac')
        other_partner = article_for(module, 'Chase adds Apple Pay rewards redemption',
            'Chase cardholders can redeem Membership Rewards points during Apple Pay checkout.', 'IT之家')
        earn = article_for(module, 'Amex adds extra points for Apple Pay purchases',
            'Amex cardholders earn double Membership Rewards points when checking out with Apple Pay.', 'The Verge')
        pair = lambda a, b: module.profile_pair_decision(module.article_reconciliation_profile(a), module.article_reconciliation_profile(b))
        self.assertEqual(pair(left, same), 'match')
        for other in (other_partner, earn):
            self.assertNotEqual(pair(left, other), 'match')


    def test_named_product_updates_keep_object_and_action_boundaries(self):
        module = load_module()
        from test_relevance_rules import article_for
        groups = [
            ('Beats charging cables now available in "Ocean Blue"', 'Apple Beats charging cables are now available in Ocean Blue from Apple online store.',
             '苹果 Beats 充电线新配色 Ocean Blue 上架', '苹果官网上架 Beats 充电线 Ocean Blue 新配色。',
             'Beats charging cables now available in "Forest Green"', 'Apple Beats charging cables are now available in Forest Green from Apple online store.'),
            ('Apple Creator Studio gets new AI features', 'Apple updated Creator Studio with new Final Cut Pro and Logic Pro features.',
             '苹果升级 Apple 创作坊 AI 工具', 'Apple 创作坊更新 Final Cut Pro 和 Logic Pro。',
             'Apple raises Creator Studio subscription prices', 'Apple raised Creator Studio subscription prices without changing the apps.'),
            ('Apple Messages app gets a new AI agent', 'Third-party AI service Relay was approved for use in Apple Messages app.',
             '苹果批准 Relay 接入 iMessage 平台', '苹果批准 Relay 成为接入 Apple Messages for Business 平台的第三方 AI 智能体。',
             'Apple Messages app gets another AI agent', 'Third-party AI service Pilot was approved for use in Apple Messages app.'),
        ]
        for title, lead, same_title, same_lead, other_title, other_lead in groups:
            with self.subTest(title=title):
                articles = [article_for(module, t, text, source) for t, text, source in
                    [(title, lead, 'MacRumors'), (same_title, same_lead, 'IT之家'), (other_title, other_lead, '9to5Mac')]]
                profiles = [module.article_reconciliation_profile(article) for article in articles]
                self.assertEqual(module.profile_pair_decision(profiles[0], profiles[1]), 'match')
                self.assertNotEqual(module.profile_pair_decision(profiles[0], profiles[2]), 'match')


    def test_current_code_disclosure_is_not_an_evergreen_product_recap(self):
        module = load_module()
        title = 'AirPod cameras: everything we learned this week'
        current = 'Code in macOS 26.7 disclosed how camera-equipped AirPods capture paired still images.'
        old = 'We recapped previously reported AirPods rumors. There is no new reporting or new code disclosure.'
        self.assertFalse(module.is_routine_recap_comparison_or_buying_advice(title, current))
        self.assertTrue(module.is_routine_recap_comparison_or_buying_advice(title, old))
        self.assertEqual(module.classify_relevance_tier(title, current, [], 'MacRumors')[0], 'strong')
        self.assertEqual(module.classify_relevance_tier(title, old, [], 'MacRumors')[0], 'weak')


    def test_product_recall_requires_current_first_party_disposition(self):
        module = load_module()
        from test_relevance_rules import article_for
        current = article_for(module, 'Apple recalls iPhone batteries after overheating reports',
            'Apple announced a battery recall. An analyst predicts 80 million iPhones in 2027.', 'MacRumors')
        foreign = article_for(module, 'Anker recalls iPhone battery packs after overheating reports',
            'Anker recalled its battery packs. Apple is mentioned as a compatible phone maker.', '9to5Mac')
        history = article_for(module, 'Looking back at Apple battery recalls',
            'This retrospective revisits an old Apple recall, with no new recall or disposition.', 'The Verge')
        self.assertEqual(module.article_reconciliation_profile(current).relevance_tier, 'strong')
        for article in (foreign, history):
            profile = module.article_reconciliation_profile(article)
            self.assertNotEqual(profile.relevance_tier, 'strong')
            self.assertFalse(any(':product-recall' in key for key in profile.event_keys))


    def test_event_calendar_aliases_require_timezone_and_year_compatibility(self):
        module = load_module()
        from test_relevance_rules import article_for
        def report(day, year):
            return article_for(module, f'Apple event announced for September {day}, {year}',
                f'The Apple event will take place on September {day}, {year} at Apple Park.', 'MacRumors')
        local = report(9, 2026)
        beijing = article_for(module, '苹果发布会官宣定档2026年9月10日',
            '苹果发布会将于北京时间2026年9月10日举行。', 'IT之家')
        pair = lambda a, b: module.profile_pair_decision(module.article_reconciliation_profile(a), module.article_reconciliation_profile(b))
        self.assertEqual(pair(local, beijing), 'match')
        self.assertEqual(pair(local, report(10, 2026)), 'conflict')
        self.assertEqual(pair(local, report(9, 2027)), 'conflict')
        beijing_other = article_for(module, '苹果发布会官宣定档2026年9月11日',
            '苹果发布会将于北京时间2026年9月11日举行。', '9to5Mac')
        self.assertEqual(pair(beijing, beijing_other), 'conflict')


    def test_content_production_uses_explicit_work_alias_and_season(self):
        module = load_module()
        from test_relevance_rules import article_for
        def article(title, lead):
            return article_for(module, title, lead, 'MacRumors')
        english = article('Apple teases Harbor Lights season 3 in new update', 'Apple TV confirmed Harbor Lights season 3 has started filming.')
        chinese = article('苹果预热《港湾灯火》电视剧第三季', '苹果预热《港湾灯火》（Harbor Lights）第三季，并确认已经开拍。')
        other_season = article('Apple teases Harbor Lights season 4 in new update', 'Apple TV confirmed Harbor Lights season 4 has started filming.')
        other_work = article('苹果预热《远方山谷》电视剧第三季', '苹果预热《远方山谷》（Distant Valley）第三季，并确认已经开拍。')
        pair = lambda a,b: module.profile_pair_decision(module.article_reconciliation_profile(a), module.article_reconciliation_profile(b))
        self.assertEqual(pair(english, chinese), 'match')
        for other in (other_season, other_work):
            self.assertNotEqual(pair(english, other), 'match')


    def test_content_events_require_same_named_event_or_work(self):
        module = load_module()
        from test_relevance_rules import article_for
        groups = [
            ('F1 British Grand Prix will stream free on Apple TV', 'Apple will stream the British Grand Prix free on Apple TV.',
             'Watch the British Grand Prix for free on Apple TV', 'The entire Formula 1 British Grand Prix weekend will be free to Apple TV viewers.',
             'F1 Austrian Grand Prix will stream free on Apple TV', 'Apple will stream the Austrian Grand Prix free on Apple TV.'),
            ('Apple TV announces Comic-Con Hall H lineup', 'Apple TV will bring its shows to Comic-Con Hall H for a panel lineup.',
             'Apple TV takes over Comic-Con with new panels', 'Apple TV announced Comic-Con Hall H panels for its shows.',
             'Apple TV announces Comic-Con Hall D lineup', 'Apple TV announced a Comic-Con Hall D panel lineup.'),
            ('Apple TV reveals new comedy with Alex Parker', 'Apple TV announced the release date for Harbor Family, a new comedy starring Alex Parker.',
             'Apple TV comedy "Harbor Family" gets fall 2027 debut', 'The Apple TV comedy "Harbor Family" starring Alex Parker premieres in fall 2027.',
             'Apple TV comedy "Distant Family" gets fall 2027 debut', 'The Apple TV comedy "Distant Family" starring Alex Parker premieres in fall 2027.'),
        ]
        for title, lead, same_title, same_lead, other_title, other_lead in groups:
            with self.subTest(title=title):
                profiles = [module.article_reconciliation_profile(article_for(module, t, text, source)) for t, text, source in
                    [(title, lead, 'MacRumors'), (same_title, same_lead, 'IT之家'), (other_title, other_lead, '9to5Mac')]]
                self.assertEqual(module.profile_pair_decision(profiles[0], profiles[1]), 'match')
                self.assertNotEqual(module.profile_pair_decision(profiles[0], profiles[2]), 'match')


    def test_supply_constraints_and_factory_investigations_keep_primary_objects(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        shortage = profile('MacBook Air faces a major shortage despite a price increase', 'Apple online store shows weeks of delivery delays.')
        shortage_other = profile('MacBook Air supply is constrained', 'Apple online store shows weeks of delivery delays.')
        price = profile('Apple raises MacBook Air prices', 'Apple increased MacBook Air prices by $200.')
        self.assertEqual(module.profile_pair_decision(shortage, shortage_other), 'match')
        self.assertNotEqual(module.profile_pair_decision(shortage, price), 'match')
        first = profile('iPhone parts factory faces water contamination probe', "Officials are investigating alleged wastewater contamination from Tata's iPhone parts factory in India.")
        second = profile('iPhone parts plant under water pollution investigation', "Officials opened a water contamination investigation into Tata Electronics' iPhone parts factory in India.")
        other = profile('iPhone parts factory faces water contamination probe', "Officials are investigating alleged wastewater contamination from Foxconn's iPhone parts factory in India.")
        self.assertEqual(module.profile_pair_decision(first, second), 'match')
        self.assertNotEqual(module.profile_pair_decision(first, other), 'match')


    def test_app_acquisition_passive_source_preserves_target_and_stage(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        first = profile("Apple acquires app 'Canvas'", 'Apple acquired the application from its developer.')
        same = profile('Award-winning developer acquired by Apple', 'Apple has bought the developer which made a visual design tool called Canvas.')
        other = profile('Award-winning developer acquired by Apple', 'Apple has bought the developer which made a visual design tool called Mosaic.')
        proposal = profile("Apple plans to acquire app 'Canvas'", 'Apple is considering a deal for the application.')
        self.assertEqual(module.profile_pair_decision(first, same), 'match')
        self.assertNotEqual(module.profile_pair_decision(first, other), 'match')
        self.assertNotEqual(module.profile_pair_decision(first, proposal), 'match')


    def test_service_policy_and_car_key_keep_action_partner_and_phase(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        policy = profile("Apple won't allow these ad categories in the Maps app", 'The revised Apple Maps ad policy prohibits political advertising.')
        self.assertEqual(policy.relevance_tier, 'strong')
        rollout = profile('Apple Maps ads launch today', 'Apple begins advertising in Apple Maps today.')
        self.assertNotEqual(module.profile_pair_decision(policy, rollout), 'match')
        a = profile('iOS 29 code hints at Apple Wallet car key support', 'iOS 29 code references Apple Wallet car key support for BMW vehicles.')
        b = profile('iOS 29 code shows iPhone car key support for BMW', 'Apple Wallet car key support for BMW appears in iOS 29 beta code.')
        other = profile('iOS 29 code hints at Apple Wallet car key support', 'iOS 29 code references Apple Wallet car key support for Rivian vehicles.')
        live = profile('Apple launches Wallet car key support for BMW', 'Apple Wallet car keys for BMW are now available with iOS 29.')
        self.assertEqual(module.profile_pair_decision(a, b), 'match')
        self.assertNotEqual(module.profile_pair_decision(a, other), 'match')
        self.assertNotEqual(module.profile_pair_decision(a, live), 'match')


    def test_company_changes_keep_department_and_transaction_stage(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        design = profile("John Ternus may rebalance Apple's design team", 'John Ternus may restore design decision authority at Apple.')
        same = profile("Apple design decision authority may change under John Ternus", 'John Ternus may rebalance the design team decision authority.')
        engineering = profile("John Ternus may rebalance Apple's engineering team", 'John Ternus may restore engineering decision authority at Apple.')
        completed = profile("John Ternus restored Apple's design decision authority", 'John Ternus has restored design decision authority at Apple.')
        self.assertEqual(module.profile_pair_decision(design, same), 'match')
        self.assertNotEqual(module.profile_pair_decision(design, engineering), 'match')
        self.assertNotEqual(module.profile_pair_decision(design, completed), 'match')
        past = profile('Apple and Disney had conversations about merging', 'The former CEO says Apple and Disney had merger conversations years ago.')
        translated = profile('迪士尼前CEO称曾与苹果讨论合并', '迪士尼曾与苹果讨论过合并事宜。')
        announced = profile('Apple and Disney announce a merger', 'Apple and Disney have announced a merger after previous conversations.')
        self.assertEqual(module.profile_pair_decision(past, translated), 'match')
        self.assertNotEqual(module.profile_pair_decision(past, announced), 'match')


    def test_native_migration_and_regulatory_service_support_keep_source_owner(self):
        module = load_module()
        native = module.classify_relevance_tier('Google 升级 Android 数据迁移工具，支持从 iPhone 直接转移密码与 eSIM', 'Android 原生数据迁移现在支持 iPhone 凭据。', [], 'IT之家')[0]
        independent = module.classify_relevance_tier('Rivet app upgrades its iPhone to Android migration tool', 'The independent app now transfers passwords from iPhone to Android.', [], 'MacRumors')[0]
        policy = module.classify_relevance_tier('Apple reaches agreement with Chinese government on Apple Intelligence rollout', 'Apple Intelligence received regulatory clearance in China.', [], 'MacRumors')[0]
        background = module.classify_relevance_tier('Google launches its own AI app in China', 'Google launched its own service. Apple Intelligence also received regulatory clearance in China.', [], 'MacRumors')[0]
        self.assertEqual(native, 'ecosystem')
        self.assertEqual(independent, 'weak')
        self.assertEqual(policy, 'strong')
        self.assertEqual(background, 'weak')


    def test_security_bulletins_keep_platform_version_and_remediation_phase(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        current = profile('Apple details iOS 29.2 security fixes', 'Apple published the iOS 29.2 security bulletin.')
        same = profile('iOS 29.2 patches security flaws', 'The Apple iOS 29.2 security bulletin lists its fixes.')
        old = profile('Apple details iOS 28.2 security fixes', 'Apple published the iOS 28.2 security bulletin.')
        mac = profile('Apple details macOS 29.2 security fixes', 'Apple published the macOS 29.2 security bulletin.')
        self.assertEqual(module.profile_pair_decision(current, same), 'match')
        self.assertNotEqual(module.profile_pair_decision(current, old), 'match')
        self.assertNotEqual(module.profile_pair_decision(current, mac), 'match')
        partial = profile('AirDrop vulnerabilities discovered', 'Researchers found AirDrop flaws. Apple fixed one and is working on the remaining fixes.')
        reported = profile('苹果隔空投送曝安全漏洞', '研究人员发现 AirDrop 漏洞，苹果已修复其中一个漏洞并继续制作补丁。')
        fixed = profile('Apple fixes all AirDrop vulnerabilities', 'Apple completed fixes for all AirDrop vulnerabilities.')
        self.assertEqual(module.profile_pair_decision(partial, reported), 'match')
        self.assertNotEqual(module.profile_pair_decision(partial, fixed), 'match')

    def test_device_scoped_os_feature_keeps_generation_and_version(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        current = profile('visionOS 29 gives M7 Vision Pro new advantages', 'visionOS 29 gives M7 Vision Pro Siri voice customization, while M6 lacks it.')
        same = profile('visionOS 29 为 M7 Vision Pro 带来 Siri 语音定制', 'M7 Vision Pro 在 visionOS 29 中支持 Siri 语音定制。')
        other = profile('visionOS 29 gives M6 Vision Pro new advantages', 'visionOS 29 gives M6 Vision Pro Siri voice customization.')
        version = profile('visionOS 30 gives M7 Vision Pro new advantages', 'visionOS 30 gives M7 Vision Pro Siri voice customization.')
        self.assertEqual(module.profile_pair_decision(current, same), 'match')
        self.assertNotEqual(module.profile_pair_decision(current, other), 'match')
        self.assertNotEqual(module.profile_pair_decision(current, version), 'match')
        denied = profile('visionOS 29 does not give M7 Vision Pro Siri voice customization', 'M7 Vision Pro does not support Siri voice customization with visionOS 29.')
        self.assertNotEqual(module.profile_pair_decision(current, denied), 'match')


    def test_foldable_supply_and_cells_keep_stage_and_numeric_roles(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        early = profile('Suppliers begin small-batch production for the foldable iPhone', "Suppliers started small-batch production for Apple's first folding iPhone.")
        same = profile('苹果首款折叠 iPhone 已小批量供货', '供应商已经向苹果折叠 iPhone 小批量供货。')
        mass = profile('Suppliers begin mass production for the foldable iPhone', "Suppliers started mass production for Apple's first folding iPhone.")
        self.assertEqual(module.profile_pair_decision(early, same), 'match')
        self.assertNotEqual(module.profile_pair_decision(early, mass), 'match')
        cells = profile('Foldable iPhone battery capacity registered', 'The supplier registered 1,800mAh and 2,700mAh cells, for a combined 4,500mAh battery.')
        same_cells = profile('苹果折叠 iPhone 双电池容量曝光', '两块电芯为 1800mAh 和 2700mAh，合计 4500mAh。')
        other_cells = profile('Foldable iPhone battery capacity registered', 'The supplier registered 2,000mAh and 2,500mAh cells, for a combined 4,500mAh battery.')
        self.assertEqual(module.profile_pair_decision(cells, same_cells), 'match')
        self.assertNotEqual(module.profile_pair_decision(cells, other_cells), 'match')


    def test_executive_demand_and_tariff_arrangement_preserve_named_parties(self):
        module = load_module()
        from test_relevance_rules import article_for
        def profile(title, lead):
            return module.article_reconciliation_profile(article_for(module, title, lead, 'MacRumors'))
        demand = profile('Apple executive explains Mac mini AI demand', "Doug Brooks says Apple's Mac mini and Mac Studio are seeing strong demand for running AI agents.")
        same = profile('苹果高管谈 Mac mini 的 AI 需求', 'Doug Brooks 表示 Mac mini 和 Mac Studio 已成为运行 AI 智能体的首选设备。')
        forecast = profile('Apple executive predicts future Mac mini AI demand', "Tim Cook says Mac mini and Mac Studio might become popular for running AI agents next year.")
        self.assertEqual(demand.relevance_tier, 'strong')
        self.assertEqual(same.relevance_tier, 'strong')
        self.assertEqual(module.profile_pair_decision(demand, same), 'match')
        self.assertNotEqual(module.profile_pair_decision(demand, forecast), 'match')
        deal = profile('Apple avoids semiconductor tariffs through Intel foundry deal', "Apple's commitment to use Intel U.S. foundries reportedly helped secure a semiconductor tariff exemption.")
        translated = profile('苹果承诺采用英特尔美国代工厂，换取半导体关税豁免', '苹果同意使用英特尔美国晶圆厂，并据称因此获得半导体关税豁免。')
        other = profile('Apple avoids semiconductor tariffs through TSMC foundry deal', "Apple's commitment to use TSMC U.S. foundries reportedly helped secure a semiconductor tariff exemption.")
        procurement = profile('Apple agrees to use Intel foundries for chips', 'Apple committed to use Intel U.S. foundries for some chips.')
        self.assertEqual(deal.relevance_tier, 'strong')
        self.assertEqual(module.profile_pair_decision(deal, translated), 'match')
        self.assertNotEqual(module.profile_pair_decision(deal, other), 'match')
        self.assertNotEqual(module.profile_pair_decision(deal, procurement), 'match')


    def test_panel_report_percentages_keep_metric_owner_and_period(self):
        module = load_module()
        from test_relevance_rules import article_for
        def article(title, lead, source):
            return article_for(module, title, lead, source)
        share = article('iPhone Fold expected to take 23% of 2027 foldable screen orders', 'Counterpoint Research says Apple will take 23% of 2027 foldable panel orders, ahead of Huawei at 17%.', 'MacRumors')
        growth = article('iPhone Fold expected to lift foldable panel shipments', 'Counterpoint Research expects a 17% increase in foldable smartphone panel shipments after Apple enters the market.', '9to5Mac')
        bridge = article('Counterpoint预测苹果将占2027折叠面板订单23%', 'Counterpoint Research 预测苹果在2027年占折叠面板订单23%，全年折叠屏面板出货量预计约1500万片，同比增长17%。', 'IT之家')
        later = article('iPhone Fold expected to take 23% of 2028 foldable screen orders', 'Counterpoint Research says Apple will take 23% of 2028 foldable panel orders.', 'cnBeta')
        ps = [module.article_reconciliation_profile(a) for a in (share, growth, bridge, later)]
        self.assertNotEqual(module.profile_pair_decision(ps[0], ps[1]), 'match')
        self.assertEqual(module.profile_pair_decision(ps[0], ps[2]), 'match')
        self.assertEqual(module.profile_pair_decision(ps[1], ps[2]), 'match')
        self.assertNotEqual(module.profile_pair_decision(ps[0], ps[3]), 'match')
        self.assertFalse(any(k.startswith('panel-report-year:') for k in ps[1].separation_keys))
        self.assertFalse(any(':apple-order-share:17' in k for k in ps[0].event_keys))
        self.assertFalse(any(':production-target:' in k for k in ps[2].event_keys))
        self.assertEqual(len(module.cluster_articles([share, growth, bridge, later])), 2)


if __name__ == '__main__':
    unittest.main()
